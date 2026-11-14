"""Bounded/resumable policy comparisons in one shared-inventory environment."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import fcntl
import gzip
import hashlib
import json
import math
from pathlib import Path
import uuid

from .audit import Audit, BASE, sanitize
from .experiment import load_local_env
from .journey import _save, canonical
from .market_adapter import VERSION, PROMPTS, choose, legal_choices, public_observation
from backend.release_policy import RELEASE_DAYS, VERSION as RELEASE_VERSION

DEFAULT_POLICIES = [
    {"name": "NO_OFFER", "enabled": False, "member_fare": 0, "membership_fee": 0, "open_day": 28, "release_fraction": 0},
    {"name": "FIXED", "enabled": True, "member_fare": 70, "membership_fee": 399, "open_day": 28, "release_fraction": .5},
    {"name": "CANDIDATE", "enabled": True, "member_fare": 30, "membership_fee": 199, "open_day": 28, "release_fraction": .75},
]


def implementation_hashes():
    root = Path(__file__).resolve().parents[1]
    files = ("backend/shared_market.py", "backend/release_policy.py", "backend/nhpp.py", "simulation/generate.py", "simulation/generated/calibration_v2.json",
             "llm_agent/market_adapter.py", "llm_agent/population.py")
    return {name: hashlib.sha256((root/name).read_bytes()).hexdigest() for name in files}


def create_experiment(output, config=None, seeds=None, policies=None, modes=None, validation_seeds=None):
    from backend.shared_market import create_market
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    if (output / "experiment.json").exists():
        raise ValueError("Experiment already exists; resume instead of overwriting")
    config = config or {"horizon_days": 365, "flight_count": 9, "customer_count": 14, "occasions_per_customer": 3}
    seeds = list(seeds or [117])
    policies = policies or DEFAULT_POLICIES
    modes = list(modes or ["deterministic"])
    if any(mode not in ("deterministic", "live") for mode in modes):
        raise ValueError("Modes must be deterministic/live")
    if len(set(seeds)) != len(seeds) or not all(isinstance(x, int) and x >= 0 for x in seeds):
        raise ValueError("Seeds must be unique nonnegative integers")
    if len(seeds) > 100 or len(policies) > 20:
        raise ValueError("Experiment exceeds configured size bounds")
    cases = []
    for seed in seeds:
        for pindex, policy in enumerate(policies):
            for mode in modes:
                case_id = f"seed{seed}-policy{pindex}-{mode}"
                state = create_market(config, seed, policy)
                _save(output / f"{case_id}.json", state)
                cases.append({"case_id": case_id, "seed": seed, "policy": state["policy"], "mode": mode,
                              "split": "validation" if seed in (validation_seeds or []) else "development", "completed": False})
    experiment = {"experiment_id": "market-" + uuid.uuid4().hex[:16], "prompt_version": VERSION,
                  "implementation_hashes": implementation_hashes(),
                  "config": config, "seeds": seeds, "policies": policies, "modes": modes, "cases": cases,
                  "release_policy_version": RELEASE_VERSION, "release_days": list(RELEASE_DAYS),
                  "prompt_hashes": {lang: hashlib.sha256(path.read_bytes()).hexdigest() for lang, path in PROMPTS.items()},
                  "candidate_selection": "Predeclared policy configurations. CANDIDATE is a hypothesis, not a proven optimum.",
                  "validation_seeds": list(validation_seeds or [])}
    _save(output / "experiment.json", experiment)
    return {"experiment_id": experiment["experiment_id"], "cases": len(cases), "path": str(output)}


def run_batch(output, max_calls=12, max_steps=1000, language="en"):
    if not isinstance(max_calls, int) or not 0 <= max_calls <= 200:
        raise ValueError("max_calls must be 0..200")
    if not isinstance(max_steps, int) or not 1 <= max_steps <= 100000:
        raise ValueError("max_steps must be 1..100000")
    output = Path(output)
    with (output / ".run.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError("A batch is already running for this experiment") from None
        try:
            return _run_batch(output, max_calls, max_steps, language)
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def _run_batch(output, max_calls, max_steps, language):
    from backend.shared_market import next_observation, apply_decision, summarize
    spec = json.loads((output / "experiment.json").read_text())
    if {lang: hashlib.sha256(path.read_bytes()).hexdigest() for lang, path in PROMPTS.items()} != spec["prompt_hashes"]:
        raise ValueError("Prompt changed since experiment creation; create a new experiment")
    if spec.get("implementation_hashes") != implementation_hashes():
        raise ValueError("Market implementation changed since creation; create a new experiment")
    audit = Audit("shared_market_experiment", {"prompt_version": VERSION, "config": spec["config"], "cases": len(spec["cases"]),
                                              "experiment_path": str(output)}, run_id=spec["experiment_id"], resume=True)
    audit.update(status="running")
    states = {case["case_id"]: json.loads((output / f"{case['case_id']}.json").read_text()) for case in spec["cases"] if not case["completed"]}
    calls = steps = forced = cache_hits = failures = 0
    blocked = set()
    dirty = set()
    while steps < max_steps:
        progressed = False
        for case in spec["cases"]:
            cid = case["case_id"]
            if case["completed"] or cid in blocked or steps >= max_steps:
                continue
            state = states[cid]
            observation = next_observation(state)
            if observation is None:
                case["completed"] = True
                case["metrics"] = summarize(state)
                _save(output / f"{cid}.json", state)
                dirty.discard(cid)
                _save(output / "experiment.json", spec)
                audit.append({"event": "market_case_completed", "case_id": cid, "mode": case["mode"], "metrics": case["metrics"]})
                progressed = True
                continue
            is_forced = len(legal_choices(public_observation(observation))) == 1
            if case["mode"] == "live" and not is_forced and calls >= max_calls:
                continue
            audit.append({"event": "market_case_step", "case_id": cid, "mode": case["mode"],
                          "packet_id": observation.get("packet_id"), "split": case["split"]})
            try:
                choice = choose(observation, case["mode"], audit, language)
                transition = apply_decision(state, choice["decision"])
                # Deterministic transitions can be replayed; live choices must
                # be durable after each response, including cached responses.
                dirty.add(cid)
                if case["mode"] == "live" or len(state["records"]) % 25 == 0:
                    _save(output / f"{cid}.json", state)
                    dirty.discard(cid)
                audit.append({"event": "market_transition", "case_id": cid, "mode": case["mode"],
                              "source": choice["source"], "forced": choice["forced"], "decision": choice["decision"],
                              "cache_hit": choice["cache_hit"], "provider_call": choice["provider_call"],
                              "environment_record": transition})
                calls += int(choice["provider_call"])
                forced += int(choice["forced"])
                cache_hits += int(choice["cache_hit"])
                steps += 1
                progressed = True
            except Exception as error:
                failures += 1
                # Conservatively count a failed ambiguous live attempt against
                # the batch budget. Audit distinguishes actual transport calls.
                calls += int(case["mode"] == "live" and not is_forced)
                blocked.add(cid)
                audit.append({"event": "market_case_paused", "case_id": cid, "error": str(error), "no_fallback": True})
        if not progressed:
            break
    for cid in dirty:
        _save(output / f"{cid}.json", states[cid])
    _save(output / "experiment.json", spec)
    remaining = sum(not c["completed"] for c in spec["cases"])
    summary = {"run_id": spec["experiment_id"], "steps": steps, "provider_budget_used": calls, "environment_forced": forced,
               "cache_hits": cache_hits, "failures": failures, "remaining_cases": remaining,
               "completed_cases": len(spec["cases"]) - remaining}
    audit.update(status="completed" if not remaining else "paused_after_errors" if failures else "paused_at_budget", summary=summary)
    _save(output / "report.json", report(output))
    return summary


def _numeric_metrics(value, prefix=""):
    out = {}
    for key, item in value.items():
        if not prefix and key in ("seed", "config", "policy"):
            continue
        name = prefix + key
        if isinstance(item, dict):
            out.update(_numeric_metrics(item, name + "."))
        elif isinstance(item, (int, float)) and not isinstance(item, bool) and math.isfinite(item):
            out[name] = float(item)
    return out


def iter_audit(run_id):
    """Stream a trusted experiment audit; the HTTP inline 5,000 limit is separate."""
    from .audit import _path
    path = _path(run_id) / "events.jsonl"
    if path.exists():
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                yield json.loads(line)


def run_status(output):
    spec = json.loads((Path(output) / "experiment.json").read_text())
    from .audit import _path
    metadata = _path(spec["experiment_id"]) / "metadata.json"
    return json.loads(metadata.read_text()) if metadata.exists() else {"run_id": spec["experiment_id"], "status": "created"}


def runtime_counts(run_id):
    counts = Counter({"provider_calls": 0, "cache_hits": 0, "environment_forced": 0,
                      "deterministic_choices": 0, "validated_live_choices": 0, "failures": 0,
                      "provider_successes": 0, "transport_failures": 0, "response_validation_failures": 0,
                      "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0})
    for record in iter_audit(run_id):
        if record.get("event") not in ("market_choice", "market_choice_failed"):
            continue
        counts["provider_calls"] += int(record.get("provider_call", False))
        if record.get("event") == "market_choice_failed":
            counts["failures"] += 1
            counts["transport_failures" if record.get("error_type") in ("URLError", "TimeoutError", "OSError") else "response_validation_failures"] += 1
            continue
        counts["cache_hits"] += int(record.get("cache_hit", False))
        source = record.get("source")
        counts[{"environment_forced": "environment_forced", "deterministic_assumption": "deterministic_choices",
                "provider_live": "validated_live_choices"}.get(source, "other_choices")] += 1
        if record.get("provider_call"):
            counts["provider_successes"] += 1
            for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
                counts[key] += (record.get("usage") or {}).get(key, 0)
    counts["provider_attempts"] = counts["provider_calls"]
    return dict(counts)


def inspect_cases(output, case_id=None, event_limit=200):
    """Dashboard views of current accounting and memory, never latent futures."""
    from backend.shared_market import summarize, MONEY
    output = Path(output)
    spec = json.loads((output / "experiment.json").read_text())
    cases = [case for case in spec["cases"] if case_id is None or case["case_id"] == case_id]
    if case_id is not None and not cases:
        raise ValueError("Unknown case ID")
    if not isinstance(event_limit, int) or not 0 <= event_limit <= 2000:
        raise ValueError("event_limit must be 0..2000")
    result = []
    sources = {(record["case_id"], record["environment_record"]["packet_id"]): {key: record.get(key) for key in ("source", "cache_hit", "forced", "provider_call")}
               for record in iter_audit(spec["experiment_id"]) if record.get("event") == "market_transition"}
    for case in cases:
        state = json.loads((output / (case["case_id"] + ".json")).read_text())
        metrics = summarize(state)
        customers = [{"customer_id": cid, "person": c["person"], "remaining_budget": round(c["budget_cents"]/100, 2),
                      "joined_this_run": c["joined_this_run"], "membership_expires_day": c["membership_expires"],
                      "membership_fee_paid": round(c["membership_fee_cents"]/100, 2),
                      "ticket_spend": round(c["ticket_spend_cents"]/100, 2), "refund_received": round(c["refund_cents"]/100, 2),
                      "renewal_intention": c["renewal_intention"],
                      "bookings": [state["bookings"][bid] for bid in c["bookings"]]}
                     for cid, c in state["customers"].items()]
        ledger = [{k: round(v/100, 2) if k in MONEY else v for k, v in entry.items()}
                  for entry in (state["ledger_entries"][-event_limit:] if event_limit else [])]
        events = [{**record, **sources.get((case["case_id"],record["packet_id"]), {})} for record in (state["records"][-event_limit:] if event_limit else [])]
        result.append({**case, "day": state["day"], "metrics": metrics, "flights": metrics["flights"],
                       "customers": customers, "events": events,
                       "ledger_entries": ledger, "ledger_currency": "HKD", "events_total": len(state["records"]),
                       "ledger_entries_total": len(state["ledger_entries"]), "event_limit": event_limit})
    return sanitize(result)


def report(output):
    output = Path(output)
    spec = json.loads((output / "experiment.json").read_text())
    complete = [c for c in spec["cases"] if c["completed"]]
    groups = defaultdict(list)
    for c in complete:
        groups[(c["mode"], c["split"], c["policy"]["name"])].append(c)
    aggregate = []
    for (mode, split, name), cases in sorted(groups.items()):
        values = defaultdict(list)
        for case in cases:
            for metric, value in _numeric_metrics(case["metrics"]).items():
                values[metric].append(value)
        aggregate.append({"mode": mode, "split": split, "policy": name, "replicates": len(cases),
                          "mean_metrics": {k: sum(v)/len(v) for k, v in values.items()}})
    # Pair each policy against exactly the same seed and decision source.
    baselines = {(c["seed"], c["mode"]): c for c in complete if not c["policy"].get("enabled", True)}
    pairs = []
    for case in complete:
        baseline = baselines.get((case["seed"], case["mode"]))
        if not baseline or not case["policy"].get("enabled", True):
            continue
        current, base = _numeric_metrics(case["metrics"]), _numeric_metrics(baseline["metrics"])
        policy_state = json.loads((output / (case["case_id"] + ".json")).read_text())
        baseline_state = json.loads((output / (baseline["case_id"] + ".json")).read_text())
        baseline_normal = {(b["customer_id"], b["occasion_id"]): b for b in baseline_state["bookings"].values()
                           if b["customer_id"] is not None and b["status"] == "flown" and b["member_seats"] == 0}
        policy_member = {(b["customer_id"], b["occasion_id"]): b for b in policy_state["bookings"].values()
                         if b["customer_id"] is not None and b["status"] == "flown" and b["member_seats"] > 0}
        switched_keys = sorted(baseline_normal.keys() & policy_member.keys())
        switched = [{"customer_id": key[0], "occasion_id": key[1],
                     "baseline_flight_id": baseline_normal[key]["flight_id"], "policy_flight_id": policy_member[key]["flight_id"],
                     "baseline_party_normal_base_revenue": baseline_normal[key]["normal_base_cents"]/100,
                     "policy_party_base_revenue": (policy_member[key]["normal_base_cents"] + policy_member[key]["member_base_cents"])/100}
                    for key in switched_keys]
        pairs.append({"case_id": case["case_id"], "seed": case["seed"], "mode": case["mode"], "policy": case["policy"]["name"],
                      "split": case["split"], "metric_differences": {k: current[k] - base[k] for k in current.keys() & base.keys()},
                      "paired_switched_customers": len({key[0] for key in switched_keys}), "paired_switched_trips": len(switched),
                      "baseline_normal_revenue_for_switched": sum(r["baseline_party_normal_base_revenue"] for r in switched),
                      "policy_base_revenue_for_switched": sum(r["policy_party_base_revenue"] for r in switched),
                      "switched_trips": switched,
                      "extra_background_denied": case["metrics"]["background_denied"] - baseline["metrics"]["background_denied"],
                      "accounting_note": "Observed paired flown trips for the same person and occasion; changes of itinerary are retained. Ledger differences already include switching and displacement; do not subtract this descriptive amount again."})
    rankings = []
    rank_groups = defaultdict(list)
    for case in complete:
        rank_groups[(case["mode"], case["split"], case["seed"])].append(case)
    for (mode, split, seed), cases in sorted(rank_groups.items()):
        if len(cases) != len(spec["policies"]):
            continue
        if any(not all(c["metrics"].get("checks", {}).values()) for c in cases):
            continue
        ordered = sorted(cases, key=lambda c: (-c["metrics"]["contribution"], c["policy"]["name"]))
        best = ordered[0]["metrics"]["contribution"]
        rankings.append({"mode": mode, "split": split, "seed": seed,
                         "order": [c["policy"]["name"] for c in ordered],
                         "winners_including_ties": [c["policy"]["name"] for c in ordered if c["metrics"]["contribution"] == best],
                         "contributions": {c["policy"]["name"]: c["metrics"]["contribution"] for c in ordered}})
    ranking_groups = defaultdict(list)
    for row in rankings:
        ranking_groups[(row["mode"], row["split"])].append(row)
    stability = [{"mode": mode, "split": split, "replicates": len(rows),
                  "win_counts_including_ties": dict(Counter(name for row in rows for name in row["winners_including_ties"])),
                  "distinct_rankings": len({tuple(row["order"]) for row in rows})}
                 for (mode, split), rows in sorted(ranking_groups.items())]
    return {"run_id": spec["experiment_id"], "prompt_version": VERSION, "cases": len(spec["cases"]),
            "completed_cases": len(complete), "seeds": spec["seeds"], "validation_seeds": spec["validation_seeds"],
            "release_policy_version": spec.get("release_policy_version", "legacy"), "release_days": spec.get("release_days"),
            "aggregate": aggregate, "paired_differences": pairs, "case_results": spec["cases"],
            "seed_rankings": rankings, "ranking_stability": stability,
            "runtime": runtime_counts(spec["experiment_id"]), "status": run_status(output).get("status", "created"),
            "limitations": ["Synthetic shared market; common seeds pair people and exogenous opportunities, not real customers.",
                            "Forced actions are environment transitions, not independent LLM choices. Cached responses are not new model calls.",
                            "Policies were declared before validation; validation results must not select a replacement policy without a new holdout.",
                            "Renewal is conditional intent; no renewal revenue should be recognised without an executed charge.",
                            "A candidate's performance in this simulator is not an optimal real HK Express price."]}


def export_public(output, destination):
    output, destination = Path(output), Path(destination)
    spec = json.loads((output / "experiment.json").read_text())
    destination.mkdir(parents=True, exist_ok=True)
    _save(destination / "report.json", sanitize(report(output)))
    _save(destination / "experiment.json", sanitize(spec))
    count = 0
    with (destination / "audit.jsonl.gz").open("wb") as raw_file:
        with gzip.GzipFile(filename="", fileobj=raw_file, mode="wb", mtime=0) as compressed:
            for record in iter_audit(spec["experiment_id"]):
                compressed.write((canonical(sanitize(record)) + "\n").encode())
                count += 1
    _save(destination / "manifest.json", {"source": "shared_market_experiment", "run_id": spec["experiment_id"],
          "synthetic_only": True, "files": {name: hashlib.sha256((destination/name).read_bytes()).hexdigest()
          for name in ("report.json", "experiment.json", "audit.jsonl.gz")}})
    return {"run_id": spec["experiment_id"], "destination": str(destination), "records": count}


def main():
    load_local_env()
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create")
    create.add_argument("--output", type=Path, required=True)
    create.add_argument("--seeds", default="117")
    create.add_argument("--validation-seeds", default="")
    create.add_argument("--modes", default="deterministic")
    create.add_argument("--customers", type=int, default=14)
    create.add_argument("--flights", type=int, default=9)
    create.add_argument("--policy-file", type=Path)
    run = sub.add_parser("run")
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--max-calls", type=int, default=12)
    run.add_argument("--max-steps", type=int, default=1000)
    run.add_argument("--language", choices=list(PROMPTS), default="en")
    rep = sub.add_parser("report")
    rep.add_argument("--output", type=Path, required=True)
    exp = sub.add_parser("export")
    exp.add_argument("--output", type=Path, required=True)
    exp.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "create":
        result = create_experiment(args.output, {"horizon_days":365,"flight_count":args.flights,"customer_count":args.customers,"occasions_per_customer":3},
          [int(x) for x in args.seeds.split(",")], json.loads(args.policy_file.read_text()) if args.policy_file else None,
          args.modes.split(","), [int(x) for x in args.validation_seeds.split(",") if x])
    elif args.command == "run":
        result = run_batch(args.output, args.max_calls, args.max_steps, args.language)
    elif args.command == "report":
        result = report(args.output)
    else:
        result = export_public(args.output, args.destination)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()

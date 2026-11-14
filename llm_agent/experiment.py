"""Resumable, bounded real-provider experiments on synthetic customer journeys."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
import gzip
from .file_lock import exclusive_lock
import hashlib
import json
import os
from pathlib import Path

from .audit import Audit, read_run, sanitize
from .journey import PROMPT_VERSION, STAGES, _save, apply_decision, export_pending, export_suite, packet_for, require_current_suite, summarize
from .journey_runner import provider_decision


def load_local_env():
    """Read local literal settings without shell evaluation or credential output."""
    path = Path(__file__).resolve().parents[1] / ".env.local"
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip() or line.lstrip().startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            if key in ("LLM_API_URL", "LLM_API_KEY", "LLM_MODEL"):
                os.environ.setdefault(key, value.strip().strip("\"'"))


def create(output, full=False, seed=117):
    output = Path(output)
    result = export_suite(output, pilot=not full, seed=seed)
    suite = json.loads((output / "state.json").read_text(encoding="utf-8"))
    suite["source"] = "provider_live"
    suite["provider_model"] = os.environ.get("LLM_MODEL")
    _save(output / "state.json", suite)
    return {**result, "source": "provider_live", "maximum_decisions": len(suite["worlds"]) * len(STAGES)}


def run_batch(output, max_decisions=30, workers=3):
    """One writer per suite; the OS releases the lock even after interruption."""
    output = Path(output)
    with exclusive_lock(output / ".run.lock"):
        return _run_batch(output, max_decisions, workers)


def _run_batch(output, max_decisions=30, workers=3):
    if not isinstance(max_decisions, int) or not 1 <= max_decisions <= 168:
        raise ValueError("max_decisions must be 1..168")
    if not isinstance(workers, int) or not 1 <= workers <= 5:
        raise ValueError("workers must be 1..5")
    output = Path(output)
    suite = json.loads((output / "state.json").read_text(encoding="utf-8"))
    if suite["source"] != "provider_live":
        raise ValueError("Do not run provider calls on a Codex pilot suite")
    require_current_suite(output, suite)
    audit = Audit("provider_live", {"prompt_version": PROMPT_VERSION, "suite_path": str(output), "model": os.environ.get("LLM_MODEL"),
                                    "worlds": len(suite["worlds"]), "maximum_decisions": len(suite["worlds"]) * len(STAGES)},
                  run_id=suite["suite_id"], resume=True)
    attempts = applied = failures = 0
    failed_worlds = set()
    audit.update(status="running")
    while attempts < max_decisions:
        pending = sorted([w for w in suite["worlds"] if w["stage_index"] < len(STAGES) and w["world_id"] not in failed_worlds],
                         key=lambda w: (w["stage_index"], w["world_id"]))
        chosen = pending[:min(workers, max_decisions - attempts)]
        if not chosen:
            break
        with ThreadPoolExecutor(max_workers=workers) as executor:
            calls = {executor.submit(provider_decision, packet_for(w), audit): w for w in chosen}
            attempts += len(calls)
            for task in as_completed(calls):
                world = calls[task]
                packet = packet_for(world)
                try:
                    decision = task.result()
                    clean = apply_decision(world, decision)
                    # Checkpoint each completed state before starting the next
                    # stage. On restart successful cached calls need no network.
                    _save(output / "state.json", suite)
                    audit.append({"event": "state_transition", "source": "provider_live", "packet": packet,
                                  "validated_decision": clean, "state_after": world["state"], "validation": "passed"})
                    applied += 1
                except Exception as error:
                    failed_worlds.add(world["world_id"])
                    failures += 1
                    audit.append({"event": "world_paused", "world_id": world["world_id"], "error": str(error),
                                  "stage_index": world["stage_index"], "no_fallback": True})
    remaining = export_pending(output)
    summary = summarize(suite)
    _save(output / "summary.json", summary)
    audit.update(status="completed" if remaining == 0 else "paused_after_errors" if failures else "paused_at_budget",
                 summary=summary, last_batch_attempts=attempts, last_batch_failures=failures)
    return {"run_id": suite["suite_id"], "attempts": attempts, "applied": applied, "failures": failures,
            "remaining_worlds": remaining, "summary": summary}


def report(output):
    output = Path(output)
    suite = json.loads((output / "state.json").read_text(encoding="utf-8"))
    data = read_run(suite["suite_id"])
    conditions = defaultdict(list)
    for world in suite["worlds"]:
        config = world["offer_config"]
        conditions[f"P{config['member_base_fare']}-V{config['membership_fee']}"].append(world)
    summaries = {}
    for label, worlds in conditions.items():
        summaries[label] = {**summarize({**suite, "worlds": worlds}),
                            "existing_members": sum(w["person"]["membership_active"] for w in worlds),
                            "eligible_new_members": sum(not w["person"]["membership_active"] for w in worlds),
                            "action_counts": dict(Counter(h["action"] for w in worlds for h in w["state"]["history"]))}
    provider_records = [r for r in data["records"] if r.get("event") == "decision_validated"]
    usages = [r.get("usage") or {} for r in provider_records if not r.get("cache_hit")]
    return {"run_id": suite["suite_id"], "source": suite["source"], "summary": summarize(suite), "conditions": summaries,
            "provider_decisions": len(provider_records), "provider_cache_hits": sum(r.get("cache_hit", False) for r in provider_records),
            "provider_token_usage_reported": {k: sum(u.get(k, 0) or 0 for u in usages) for k in ("prompt_tokens", "completion_tokens", "total_tokens")},
            "failed_decisions": sum(r.get("event") in ("decision_failed", "external_batch_rejected") for r in data["records"]),
            "limitations": ["This is generated customer role-play, not observed customer data or payment.",
                            "The 28-world pilot changes fare and fee together, so it cannot identify their separate elasticities.",
                            "Four fares by two fees in the optional 112-world factorial support controlled comparisons, but still do not establish real market effects.",
                            "Each counterfactual world has independent inventory. Totals do not represent shared-flight capacity clearing.",
                            "One detailed trip is followed; annual benefit is an expectation and renewal is an uncharged intention.",
                            "Do not fit price-response coefficients or calibrate the revenue optimizer from this small pilot.",
                            "Original Codex pilot subscription packets v2 exposed a future change label; the agent was told to ignore it. v2.1 packets remove it."]}


def export_public(output, destination):
    """Export only synthetic, redacted artifacts for an explicitly requested share."""
    output, destination = Path(output), Path(destination)
    suite = json.loads((output / "state.json").read_text(encoding="utf-8"))
    data = read_run(suite["suite_id"])
    destination.mkdir(parents=True, exist_ok=True)
    public_report = sanitize(report(output))
    # Preserve exact redacted request/response text, rather than only choices.
    raw = "".join(json.dumps(sanitize(r), ensure_ascii=False) + "\n" for r in data["records"]).encode()
    compressed = gzip.compress(raw, mtime=0)
    (destination / "audit.jsonl.gz").write_bytes(compressed)
    _save(destination / "report.json", public_report)
    _save(destination / "worlds.json", sanitize(suite))
    _save(destination / "manifest.json", {"run_id": suite["suite_id"], "source": suite["source"],
           "synthetic_personas_only": True, "contains_authentication_headers": False,
           "files": {name: hashlib.sha256((destination / name).read_bytes()).hexdigest() for name in ("audit.jsonl.gz", "report.json", "worlds.json")}})
    return {"run_id": suite["suite_id"], "destination": str(destination), "audit_records": len(data["records"])}


def main():
    load_local_env()
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    create_cmd = sub.add_parser("create")
    create_cmd.add_argument("--output", type=Path, required=True)
    create_cmd.add_argument("--full", action="store_true")
    create_cmd.add_argument("--seed", type=int, default=117)
    batch = sub.add_parser("run")
    batch.add_argument("--output", type=Path, required=True)
    batch.add_argument("--max-decisions", type=int, default=30)
    batch.add_argument("--workers", type=int, default=3)
    rep = sub.add_parser("report")
    rep.add_argument("--output", type=Path, required=True)
    exp = sub.add_parser("export")
    exp.add_argument("--output", type=Path, required=True)
    exp.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "create":
        result = create(args.output, args.full, args.seed)
    elif args.command == "run":
        result = run_batch(args.output, args.max_decisions, args.workers)
    elif args.command == "report":
        result = report(args.output)
    else:
        result = export_public(args.output, args.destination)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()

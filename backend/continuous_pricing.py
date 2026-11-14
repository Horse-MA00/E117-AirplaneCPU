"""Adaptive cent-resolution fare search in the actual shared-market engine.

Membership fee and release fraction stay fixed. Feedback is complete simulated
market contribution, not an optimal-price label or a claim of human demand.
"""
from __future__ import annotations
import copy
import hashlib
import json
import math
from pathlib import Path
import statistics
from backend.probabilistic_customer import choose, VERSION as CUSTOMER_VERSION

VERSION = "continuous-shared-pricing-v1"


def _number(value, name, low, high, integer=False):
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or not low <= value <= high or (integer and int(value) != value):
        raise ValueError(f"{name} must be in {low}..{high}")
    return int(value) if integer else float(value)


def adaptive_search(evaluate, low, high, budget=15):
    """Bounded optimistic interval refinement; no global-optimum certificate."""
    left, right = round(low * 100), round(high * 100)
    observations = {}
    def sample(cents):
        if cents not in observations:
            observations[cents] = evaluate(cents / 100)
    sample(left)
    if right != left:
        sample(right)
    while len(observations) < budget:
        points = sorted(observations)
        intervals = [(a, b) for a, b in zip(points, points[1:]) if b - a > 1]
        if not intervals:
            break
        scores = [v["search_score"] for v in observations.values()]
        spread = max(1., max(scores) - min(scores))
        # Exploration bonus preserves broad coverage while feedback guides refinement.
        a, b = max(intervals, key=lambda pair: max(observations[pair[0]]["search_score"], observations[pair[1]]["search_score"])
                   + 2 * spread * (pair[1] - pair[0]) / max(1, right - left))
        sample((a + b) // 2)
    return list(observations.values())


def replay(state, scenario="base", keep_feedback=False):
    from backend.shared_market import next_observation, apply_decision, summarize
    feedback = []
    while (observation := next_observation(state)) is not None:
        result = choose(observation, scenario)
        transition = apply_decision(state, result["decision"])
        if keep_feedback:
            feedback.append({"packet_id": observation["packet_id"], "customer_id": observation["customer_id"],
                "stage": observation["stage"], "day": observation["day"], "options": observation["options"],
                "customer": observation["customer"], "visible_state": observation["visible_state"],
                "choice": result, "financial_delta": transition.get("financial_delta", {})})
    report = summarize(state)
    if not report["complete"] or not all(report["checks"].values()):
        raise ValueError("Incomplete market or failed accounting invariant")
    report["feedback"] = feedback
    return report


def optimize(config=None):
    from backend.shared_market import create_market
    src = config or {}
    if not isinstance(src, dict):
        raise ValueError("config must be an object")
    defaults = {"price_min": (0, 0, 2000, False), "price_max": (500, 0, 2000, False),
        "membership_fee": (399, 0, 5000, False), "release_fraction": (.5, 0, 1, False),
        "evaluations": (11, 3, 31, True), "replicates": (2, 1, 5, True),
        "seed": (117, 0, 2**31-100000, True), "customers": (14, 1, 100, True),
        "flights": (6, 6, 12, True), "min_service_rate": (.6, 0, 1, False),
        "program_cost": (1500, 0, 100000, False)}
    cfg = {k: _number(src.get(k, d), k, lo, hi, integer) for k, (d, lo, hi, integer) in defaults.items()}
    if cfg["price_min"] >= cfg["price_max"]:
        raise ValueError("price_min must be less than price_max")
    # Bound independent world counts; validation never selects the search winner.
    train_seeds = [cfg["seed"] + i * 101 for i in range(cfg["replicates"])]
    test_seeds = [cfg["seed"] + 50003 + i * 101 for i in range(2)]
    market_cfg = {"customer_count": cfg["customers"], "flight_count": cfg["flights"],
                  "occasions_per_customer": 3, "program_cost": cfg["program_cost"]}
    templates = {}
    def template(seed):
        if seed not in templates:
            templates[seed] = create_market(market_cfg, seed, {"name": "CONTINUOUS", "member_fare": 0,
                "membership_fee": cfg["membership_fee"], "open_day": 28, "release_fraction": cfg["release_fraction"]})
        return templates[seed]
    def run(seed, price, enabled=True, scenario="base", feedback=False):
        state = copy.deepcopy(template(seed))
        state["policy"].update(member_fare=price, enabled=enabled, name="CONTINUOUS" if enabled else "NO_OFFER")
        state["market_id"] = "continuous-" + str(seed) + "-" + str(round(price * 100)) + ("-offer" if enabled else "-baseline")
        # Initial setup entry belongs to the policy. No membership has yet been sold.
        if not enabled:
            state["ledger_cents"]["program_cost"] = 0
            state["ledger_entries"] = [e for e in state["ledger_entries"] if e["kind"] != "programme"]
        return replay(state, scenario, feedback)
    baselines = {}
    def baseline(seed, scenario):
        key = (seed, scenario)
        if key not in baselines:
            baselines[key] = run(seed, 0, False, scenario)
        return baselines[key]
    def evaluate(price, seeds=train_seeds, scenario="base", feedback=False):
        reports = [run(s, price, scenario=scenario, feedback=feedback) for s in seeds]
        deltas = [r["contribution"] - baseline(s, scenario)["contribution"] for s, r in zip(seeds, reports)]
        feasible = all(r["new_members"] > 0 and r["service_rate"] >= cfg["min_service_rate"] for r in reports)
        mean = statistics.mean(deltas)
        return {"member_fare": round(price, 2), "membership_fee": cfg["membership_fee"],
            "incremental_contribution": round(mean, 2), "paired_differences": deltas,
            "feasible": feasible, "search_score": mean if feasible else min(mean, 0) - 10000,
            "mean_members": statistics.mean(r["new_members"] for r in reports),
            "mean_member_trips": statistics.mean(r["member_flown"] for r in reports),
            "mean_service_rate": statistics.mean(r["service_rate"] for r in reports),
            "standard_error": statistics.stdev(deltas) / math.sqrt(len(deltas)) if len(deltas) > 1 else None,
            "scenario": scenario, "seeds": list(seeds),
            "checks_passed": all(all(r["checks"].values()) for r in reports),
            **({"markets": reports} if feedback else {})}
    candidates = adaptive_search(evaluate, cfg["price_min"], cfg["price_max"], cfg["evaluations"])
    valid = [c for c in candidates if c["feasible"] and c["incremental_contribution"] > 0]
    winner = max(valid, key=lambda c: (c["incremental_contribution"], -c["member_fare"])) if valid else None
    # Retain the strongest tested hypothesis even when NO_OFFER wins, for diagnosis.
    tested = winner or max(candidates, key=lambda c: c["search_score"])
    validation = evaluate(tested["member_fare"], test_seeds, feedback=True)
    stress = [evaluate(tested["member_fare"], test_seeds, scenario)
              for scenario in ("price_sensitive", "less_sensitive")]
    safe = winner is not None and validation["feasible"] and validation["incremental_contribution"] > 0
    files = ["backend/continuous_pricing.py", "backend/probabilistic_customer.py", "backend/shared_market.py",
             "backend/nhpp.py", "simulation/generate.py", "simulation/generated/calibration_v2.json", "backend/release_policy.py", "llm_agent/population.py", "llm_agent/output_contract.py"]
    root = Path(__file__).resolve().parents[1]
    provenance = {f: hashlib.sha256((root / f).read_bytes()).hexdigest() for f in files}
    return {"version": VERSION, "customer_model": CUSTOMER_VERSION, "config": cfg,
        "search_seeds": train_seeds, "validation_seeds": test_seeds, "implementation_hashes": provenance,
        "trace": candidates, "selected_candidate": tested,
        "best": {"decision": "OFFER" if winner else "NO_OFFER", **(winner or {"incremental_contribution": 0, "member_fare": None})},
        "validation": validation, "stress": stress, "ready_for_review": safe,
        "assumptions": ["Synthetic probabilistic feedback; not observed human willingness to pay.",
            "Adaptive bounded search at HKD cent resolution; best evaluated feasible price, not a certified global optimum.",
            "Membership fee and release share remain fixed. D28/D14/D7 quotas use the same shared-market engine.",
            "A constant fare policy is evaluated over the full finite catalogue. Re-running updates the recommendation; no autonomous live repricing or parameter training is claimed.",
            "Validation seeds never select another price. Stress results do not retune the frozen user law.",
            "Contribution excludes pass-through fees and aircraft fixed costs. NO_OFFER is the paired reference.",
            "New user assumptions invalidate earlier behavioural evidence; preserved historical reports are not overwritten."]}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--evaluations", type=int, default=11)
    parser.add_argument("--seed", type=int, default=117)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("Refusing to overwrite an existing experiment")
    result = optimize({"evaluations": args.evaluations, "seed": args.seed})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"best": result["best"], "ready_for_review": result["ready_for_review"]}))

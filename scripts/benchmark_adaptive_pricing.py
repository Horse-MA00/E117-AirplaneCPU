"""Reproducible offline price-search comparison; never calls an LLM provider.

Example:
    python scripts/benchmark_adaptive_pricing.py --output-dir data/private/benchmark-new

All policies are frozen before an independent weighted target panel is created.
The analytic response functions are synthetic test oracles, not airline evidence.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sys
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.thompson import PurchasePosterior, capacity_expectation, fare_cap, recommend
from llm_agent.weighted_population import population, metadata, LEGACY_PROFILE, LEGACY_WEIGHTS

VERSION = "weighted-member-thompson-benchmark-v2"
FAMILIES = ("heterogeneous_logistic", "reference_threshold")
CAPACITIES = ("ample", "scarce")
METHODS = ("thompson", "greedy_map")


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    allow_nan=False).encode()).hexdigest()


def _latent(customer_id, tag):
    digest = hashlib.sha256(f"{customer_id}:{tag}".encode()).digest()
    return int.from_bytes(digest[:8], "big") / 2**64


def response_probability(people, price, normal_fare, family):
    """Declared synthetic truth; only the observations enter the fitted model."""
    if family not in FAMILIES:
        raise ValueError("Unknown response family")
    probabilities = []
    offsets = {"urgent_trip": .7, "small_business": .4, "visiting_friends": .3,
               "student": -.3, "infrequent": -.3, "frequent_leisure": .2}
    for person in people:
        budget = person["base_fare_budget"]
        if not person["eligible"] or price > budget:
            probabilities.append(0.)
            continue
        if family == "heterogeneous_logistic":
            utility = (3. + offsets.get(person["segment"], 0.)
                       + .5 * math.log(max(.02, budget / normal_fare)) - 6. * price / normal_fare)
            probability = 1. / (1. + math.exp(-utility))
        else:
            # A discontinuity cannot be represented by the fitted smooth logit.
            # Individual reference prices remain hidden from the learning model.
            reference = normal_fare * (.25 + .35 * _latent(person["customer_id"], "reference"))
            probability = .9 if price <= reference else .25 if price <= 1.2 * reference else .04
        probabilities.append(probability)
    return np.asarray(probabilities)


class _MapOnly:
    """The same response learner with no posterior exploration at acquisition."""
    def __init__(self, model):
        self.model = model

    def sample(self, rng):
        return self.model.mean.copy()

    def predict(self, *args, **kwargs):
        return self.model.predict(*args, **kwargs)

    def summary(self):
        return self.model.summary()


def train_policy(people, normal_fare, quota, family, method, rounds, seed, revenue_fraction):
    if method not in METHODS:
        raise ValueError("Unknown search method")
    started = time.monotonic()
    model = PurchasePosterior(list(LEGACY_WEIGHTS))
    rng = np.random.default_rng(seed + 1907)
    latent = np.array([_latent(p["customer_id"], "purchase") for p in people])
    rows, trace = [], []
    seen_person_prices = set()
    for number in range(rounds):
        if number == 0:
            price = fare_cap(normal_fare)
        else:
            learner = model if method == "thompson" else _MapOnly(model)
            price = recommend(learner, people, normal_fare, quota, rng, draw=True)["price"]
        probabilities = response_probability(people, price, normal_fare, family)
        intents = latent < probabilities
        for person, bought in zip(people, intents):
            observation_key = (person["customer_id"], round(price * 100))
            if observation_key in seen_person_prices:
                continue
            seen_person_prices.add(observation_key)
            rows.append({"person": person, "price": price, "normal_fare": normal_fare,
                         "bought": bool(bought), "sample_weight": person["population_weight"] * len(people)})
        model.fit(rows)
        sold = min(quota, int(intents.sum()))
        trace.append({"round": number + 1, "price": price, "member_intents": int(intents.sum()),
                      "actual_member_sales": sold, "actual_panel_member_receipts": round(price * sold, 2),
                      "weighted_intent_rate": float(sum(p["population_weight"] for p, b in zip(people, intents) if b)),
                      "source": "synthetic_fixed_person_preferences"})
    # Both methods receive identical final-selection rules and posterior MC seed.
    final = recommend(model, people, normal_fare, quota, np.random.default_rng(seed + 90019),
                      draw=False, revenue_fraction=revenue_fraction,
                      candidate_prices=sorted({row["price"] for row in trace}))
    summary = model.summary()
    return {"method": method, "price": final["price"], "trace": trace,
            "synthetic_choice_opportunities": len(people) * rounds, "provider_calls": 0,
            "unique_person_price_observations": len(rows),
            "repeated_person_price_observations": len(people) * rounds - len(rows),
            "fit_observations": summary["observations"],
            "effective_likelihood_mass": summary["effective_likelihood_mass"],
            "fitted_price_sensitivity": summary["map_price_sensitivity"],
            "selection_rule": "Max expected buyers within configured fraction of best expected member revenue among tested prices.",
            "elapsed_seconds": round(time.monotonic() - started, 6)}


def score_price(people, price, normal_fare, quota, target_size, family):
    """Independent weighted-mixture expectation with exact inventory truncation."""
    probabilities = response_probability(people, price, normal_fare, family)
    q = float(sum(p["population_weight"] * probability for p, probability in zip(people, probabilities)))
    expected_sales = capacity_expectation(np.full(target_size, q), quota)
    return {"price": float(price), "weighted_purchase_probability": q,
            "expected_member_sales": expected_sales,
            "expected_member_revenue": price * expected_sales}


def _oracle_prices(people, normal_fare, family, included):
    cap = fare_cap(normal_fare)
    prices = {round(float(p), 2) for p in np.linspace(0., cap, 801)}
    prices.update(included)
    for person in people:
        boundaries = [person["base_fare_budget"]]
        if family == "reference_threshold":
            reference = normal_fare * (.25 + .35 * _latent(person["customer_id"], "reference"))
            boundaries.extend((reference, reference * 1.2))
        for boundary in boundaries:
            cent = math.floor(boundary * 100) / 100
            if 0 <= cent <= cap:
                prices.add(cent)
    return sorted(prices)


def run_case(seed, family, capacity, customers=28, rounds=10, holdout_customers=140,
             normal_fare=410., revenue_fraction=.95):
    if capacity not in CAPACITIES:
        raise ValueError("Unknown capacity regime")
    scope = {"as_of_day": 28}
    people = population(customers, seed, scope=scope, profile=LEGACY_PROFILE)
    quota = customers if capacity == "ample" else max(1, round(customers * .2))
    methods = [train_policy(people, normal_fare, quota, family, method, rounds, seed, revenue_fraction)
               for method in METHODS]
    # No holdout person or response exists until BOTH prices have been frozen.
    holdout_seed = seed + 50000003
    heldout = population(holdout_customers, holdout_seed, scope=scope, profile=LEGACY_PROFILE)
    assert {p["customer_id"] for p in people}.isdisjoint(p["customer_id"] for p in heldout)
    initial = score_price(heldout, fare_cap(normal_fare), normal_fare, quota, customers, family)
    candidates = _oracle_prices(heldout, normal_fare, family, [m["price"] for m in methods])
    oracle = max((score_price(heldout, p, normal_fare, quota, customers, family) for p in candidates),
                 key=lambda row: (row["expected_member_revenue"], row["price"]))
    for method in methods:
        score = score_price(heldout, method["price"], normal_fare, quota, customers, family)
        method.update(score)
        method["gain_vs_initial"] = score["expected_member_revenue"] - initial["expected_member_revenue"]
        method["volume_change_vs_initial"] = score["expected_member_sales"] - initial["expected_member_sales"]
        method["oracle_revenue_ratio"] = (score["expected_member_revenue"] / oracle["expected_member_revenue"]
                                            if oracle["expected_member_revenue"] else None)
        method["oracle_regret"] = oracle["expected_member_revenue"] - score["expected_member_revenue"]
        method["cap_violations"] = sum(not 0 <= row["price"] <= fare_cap(normal_fare) for row in method["trace"])
        method["cap_violations"] += int(not 0 <= method["price"] <= fare_cap(normal_fare))
    return {"seed": seed, "holdout_seed": holdout_seed, "family": family, "capacity": capacity,
            "quota": quota, "target_customers": customers, "training_panel_size": len(people),
            "holdout_support_size": len(heldout), "search_panel_sha256": _hash(people),
            "holdout_panel_sha256": _hash(heldout), "selection_frozen_before_holdout": True,
            "initial": initial, "oracle": oracle, "methods": methods,
            "thompson_minus_greedy_revenue": methods[0]["expected_member_revenue"] - methods[1]["expected_member_revenue"]}


def summarize(cases):
    summaries = []
    groups = [(family, capacity) for family in FAMILIES for capacity in CAPACITIES] + [("all", "all")]
    for family, capacity in groups:
        selected = [case for case in cases if family == "all" or (case["family"] == family and case["capacity"] == capacity)]
        if not selected:
            continue
        for method in METHODS:
            entries = [next(row for row in case["methods"] if row["method"] == method) for case in selected]
            mean = lambda key: float(np.mean([row[key] for row in entries]))
            initial_revenue = float(np.mean([case["initial"]["expected_member_revenue"] for case in selected]))
            ratios = [row["oracle_revenue_ratio"] for row in entries if row["oracle_revenue_ratio"] is not None]
            summaries.append({"family": family, "capacity": capacity, "method": method, "cases": len(selected),
                              "mean_member_revenue": mean("expected_member_revenue"),
                              "mean_initial_revenue": initial_revenue,
                              "mean_revenue_gain": mean("gain_vs_initial"),
                              "aggregate_revenue_gain_percent": 100 * mean("gain_vs_initial") / initial_revenue if initial_revenue else None,
                              "mean_member_sales": mean("expected_member_sales"),
                              "mean_volume_change": mean("volume_change_vs_initial"),
                              "mean_oracle_revenue_ratio": float(np.mean(ratios)) if ratios else None,
                              "mean_oracle_regret": mean("oracle_regret"),
                              "win_rate_vs_initial": sum(row["gain_vs_initial"] > 1e-8 for row in entries) / len(entries),
                              "cap_violations": sum(row["cap_violations"] for row in entries),
                              "mean_search_seconds": mean("elapsed_seconds")})
    differences = [case["thompson_minus_greedy_revenue"] for case in cases]
    return {"groups": summaries,
            "thompson_vs_greedy": {"mean_revenue_difference": float(np.mean(differences)),
                                    "win_rate": sum(value > 1e-8 for value in differences) / len(differences),
                                    "tie_rate": sum(abs(value) <= 1e-8 for value in differences) / len(differences),
                                    "comparison": "Matched search budgets and common synthetic preference draws; independent analytic holdout scoring."}}


def run_benchmark(seed_count=20, seed_start=2026111400, customers=28, rounds=10,
                  holdout_customers=140, normal_fare=410., revenue_fraction=.95,
                  families=FAMILIES, capacities=CAPACITIES, progress=None):
    for name, value, low, high in (("seed_count", seed_count, 1, 100), ("customers", customers, 14, 200),
                                  ("rounds", rounds, 2, 30), ("holdout_customers", holdout_customers, 14, 2000)):
        if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
            raise ValueError(f"{name} must be {low}..{high}")
    if not families or not capacities or any(f not in FAMILIES for f in families) or any(c not in CAPACITIES for c in capacities):
        raise ValueError("Invalid benchmark scenarios")
    if not math.isfinite(normal_fare) or not .01 <= normal_fare <= 2000 or not .5 <= revenue_fraction <= 1:
        raise ValueError("Invalid fare or revenue fraction")
    started = time.monotonic()
    cases = []
    for family in families:
        for capacity in capacities:
            for index in range(seed_count):
                seed = seed_start + index * 1009
                case = run_case(seed, family, capacity, customers, rounds, holdout_customers, normal_fare, revenue_fraction)
                cases.append(case)
                if progress:
                    progress({"completed": len(cases), "total": len(families) * len(capacities) * seed_count,
                              "family": family, "capacity": capacity, "seed": seed})
    sources = ["scripts/benchmark_adaptive_pricing.py", "backend/thompson.py", "llm_agent/weighted_population.py",
               "llm_agent/population.py"]
    return {"version": VERSION, "source": "offline_synthetic_response_benchmark", "provider_calls": 0,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "config": {"profile": LEGACY_PROFILE, "seeds": seed_count, "seed_start": seed_start, "seed_step": 1009,
                       "customers": customers, "rounds": rounds, "holdout_customers": holdout_customers,
                       "normal_fare": normal_fare, "member_fare_cap_ratio": .8,
                       "revenue_fraction": revenue_fraction, "families": list(families), "capacities": list(capacities)},
            "population": metadata(profile=LEGACY_PROFILE), "cases": cases, "summary": summarize(cases),
            "elapsed_seconds": round(time.monotonic() - started, 4),
            "provenance": {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in sources},
            "limitations": [
                "All response functions, customer budgets, segment shares and preferences are declared synthetic assumptions, not measured HK Express demand.",
                "The logistic family tests a near-model demand family; the discontinuous reference-price family is a deliberate misspecification check.",
                "Only member base-ticket revenue is optimized and scored. Normal-ticket displacement, membership fees, annual usage and operating costs are outside this benchmark.",
                "Search uses a stratified panel and clustered repeated preferences. Evaluation uses an independent finite support for the weighted iid target cohort; it is not a realized airline market.",
                "Both methods receive the same round/panel budget; repeated identical person-price observations are deduplicated before fitting and are not additional information. Unique observation counts can differ between methods.",
                "Capacity expectation is E[min(Q,K)] with K Binomial(N,q_weighted). Target cohort composition is random, unlike the fixed stratified search panel.",
                "The oracle is an evaluation-only numerical reference using independent synthetic truth; no holdout responses, optimum or scores enter either search.",
                "This finite benchmark does not prove global convergence or that Thompson Sampling outperforms greedy selection in every scenario.",
            ]}


def write_report(report, output_dir):
    folder = Path(output_dir)
    # Existing experiment evidence must never be overwritten or amended.
    folder.mkdir(parents=True, exist_ok=False)
    payload = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False).encode()
    (folder / "report.json").write_bytes(payload)
    manifest = {"source": "offline_synthetic_response_benchmark", "version": VERSION, "synthetic": True,
                "provider_calls": 0, "cases": len(report["cases"]),
                "files": {"report.json": {"sha256": hashlib.sha256(payload).hexdigest(), "bytes": len(payload)}}}
    (folder / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=int, default=20)
    parser.add_argument("--seed-start", type=int, default=2026111400)
    parser.add_argument("--customers", type=int, default=28)
    parser.add_argument("--rounds", type=int, default=10)
    parser.add_argument("--holdout-customers", type=int, default=140)
    parser.add_argument("--normal-fare", type=float, default=410.)
    parser.add_argument("--revenue-fraction", type=float, default=.95)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.output_dir.exists():
        parser.error("--output-dir must be a new directory; existing evidence is immutable")
    report = run_benchmark(args.seeds, args.seed_start, args.customers, args.rounds,
                           args.holdout_customers, args.normal_fare, args.revenue_fraction,
                           progress=lambda update: print(json.dumps(update), flush=True))
    write_report(report, args.output_dir)
    print(json.dumps({"output": str(args.output_dir), "elapsed_seconds": report["elapsed_seconds"],
                      "summary": report["summary"]}, indent=2), flush=True)


if __name__ == "__main__":
    main()

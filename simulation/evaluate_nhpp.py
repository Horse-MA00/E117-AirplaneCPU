"""As-of evaluation of NHPP forecasts on withheld synthetic future intervals.

No future row or truth variable is passed to forecast(). The result diagnoses
this simulator/forecaster combination; it does not establish real-world skill.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

from backend.nhpp import forecast


def _row(raw):
    integer_fields = {"days_to_departure", "capacity", "booked_seats", "available_seats",
                      "gross_bookings", "cancellations", "normal_base_fare", "mandatory_fees", "normal_total_fare"}
    float_fields = {"empty_rate", "interval_days"}
    out = dict(raw)
    for key in integer_fields:
        out[key] = int(raw[key]) if raw.get(key, "") != "" else None
    for key in float_fields:
        out[key] = float(raw[key])
    return out


def evaluate(data_dir: Path | str | None = None, count: int = 180, day: int = 28, seed: int = 9117,
             flight_ids: list[str] | None = None, protection_allowance: float = 0) -> dict:
    root = Path(data_dir) if data_dir else Path(__file__).parent / "generated"
    if not isinstance(count, int) or count < 1:
        raise ValueError("count must be positive")
    if not isinstance(day, int) or not 1 <= day <= 28:
        raise ValueError("evaluation day must be 1..28")
    flights = json.loads((root / "flights.json").read_text(encoding="utf-8"))
    rng = np.random.default_rng(seed)
    if flight_ids is None:
        chosen = rng.choice(len(flights), size=min(count, len(flights)), replace=False)
        selected = {flights[int(i)]["flight_id"]: flights[int(i)] for i in chosen}
    else:
        requested = set(flight_ids)
        selected = {f["flight_id"]: f for f in flights if f["flight_id"] in requested}
        if not selected or len(selected) != len(flight_ids):
            raise ValueError("flight_ids must be unique valid flight IDs")
    histories = defaultdict(list)
    future = defaultdict(lambda: {"gross": 0, "cancellations": 0, "final_available": None})
    with gzip.open(root / "snapshots.csv.gz", "rt", encoding="utf-8", newline="") as f:
        for raw in csv.DictReader(f):
            if raw["flight_id"] not in selected:
                continue
            row = _row(raw)
            fid = row["flight_id"]
            if row["days_to_departure"] >= day:
                # White-list only the observable public rows. Final outcome and
                # scenario from flights.json never join the predictor input.
                histories[fid].append(row)
            else:
                future[fid]["gross"] += row["gross_bookings"]
                future[fid]["cancellations"] += row["cancellations"]
                if row["days_to_departure"] == 0:
                    future[fid]["final_available"] = row["available_seats"]
    latent_future = defaultdict(int)
    with gzip.open(root / "truth.csv.gz", "rt", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            if row["flight_id"] in selected and int(row["interval_start_day"]) <= day:
                latent_future[row["flight_id"]] += int(row["demand_requests"])
    details = []
    for fid in sorted(selected):
        prediction = forecast(histories[fid], days_to_departure=day, seed=seed,
                              protection_allowance=protection_allowance)
        observed = future[fid]
        final_available = observed["final_available"]
        if final_available is None:
            raise ValueError("flight lacks an independently scoreable final snapshot")
        actual = latent_future[fid]
        # A simple rate baseline uses observed last-seven gross bookings and
        # deliberately shares the capacity-censoring limitation of naive baselines.
        recent = histories[fid][-7:]
        rate = sum(r["gross_bookings"] for r in recent) / max(1e-9, sum(r["interval_days"] for r in recent))
        simple_mean = rate * (day - 2 / 24)
        details.append({
            "flight_id": fid, "scenario_for_scoring_only": selected[fid]["scenario"],
            "as_of_day": day, "history_rows": len(histories[fid]),
            "predicted_demand": prediction["expected_remaining_demand"],
            "actual_latent_demand": actual, "actual_accepted_gross": observed["gross"],
            "demand_absolute_error": round(abs(prediction["expected_remaining_demand"] - actual), 4),
            "last7_rate_baseline_absolute_error": round(abs(simple_mean - actual), 4),
            "protection_p90": prediction["protection_p90"],
            "raw_protection_p90": prediction.get("raw_protection_p90", prediction["protection_p90"]),
            "raw_p90_covers_latent_demand": actual <= prediction.get("raw_protection_p90", prediction["protection_p90"]),
            "p90_covers_latent_demand": actual <= prediction["protection_p90"],
            "predicted_empty_seats": prediction["expected_empty_seats"],
            "actual_empty_seats": final_available,
            "empty_seats_absolute_error": round(abs(prediction["expected_empty_seats"] - final_available), 4),
            "releasable_seats": prediction["releasable_seats"],
            "censored_fraction": prediction["diagnostics"]["censored_fraction"],
        })

    def aggregate(items):
        return {
            "flights": len(items),
            "demand_mae": round(float(np.mean([r["demand_absolute_error"] for r in items])), 4),
            "last7_rate_baseline_demand_mae": round(float(np.mean([r["last7_rate_baseline_absolute_error"] for r in items])), 4),
            "empty_seats_mae": round(float(np.mean([r["empty_seats_absolute_error"] for r in items])), 4),
            "p90_empirical_coverage": round(float(np.mean([r["p90_covers_latent_demand"] for r in items])), 4),
            "raw_p90_empirical_coverage": round(float(np.mean([r["raw_p90_covers_latent_demand"] for r in items])), 4),
            "mean_censored_fraction": round(float(np.mean([r["censored_fraction"] for r in items])), 4),
        }

    groups = defaultdict(list)
    for row in details:
        groups[row["scenario_for_scoring_only"]].append(row)
    return {
        "evaluation_version": "1.0", "model": "regularized_exponential_nhpp",
        "source": "synthetic_assumed_demo", "as_of_day": day, "selection_seed": seed,
        "protection_allowance": protection_allowance, "flight_ids": sorted(selected),
        "overall": aggregate(details), "by_scenario": {k: aggregate(v) for k, v in sorted(groups.items())},
        "limitations": [
            "Future intervals are held out at the as-of time, not independent real-world customers or airlines.",
            "Forecast receives only public snapshots at or before the as-of date; hidden truth is used only to score latent demand.",
            "Latent demand counts include requests denied by capacity. Accepted gross bookings alone would understate true demand at sellout.",
            "P90 empirical coverage is a diagnostic on these synthetic flights, not a proven 90% commercial guarantee.",
            "The simple baseline uses the last seven observable gross counts and is also affected by capacity censoring.",
            "Unknown future jumps, exogenous price changes, and model misspecification can cause undercoverage.",
            "No forecast settings are changed by this script or selected using these evaluation outcomes.",
        ],
        "flights": details,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path(__file__).parent / "generated")
    parser.add_argument("--count", type=int, default=180)
    parser.add_argument("--day", type=int, default=28)
    parser.add_argument("--seed", type=int, default=9117)
    parser.add_argument("--protection-allowance", type=float, default=0)
    parser.add_argument("--output", type=Path, default=Path(__file__).parent / "generated" / "nhpp_evaluation.json")
    args = parser.parse_args()
    result = evaluate(args.data_dir, args.count, args.day, args.seed,
                      protection_allowance=args.protection_allowance)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"overall": result["overall"], "by_scenario": result["by_scenario"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()

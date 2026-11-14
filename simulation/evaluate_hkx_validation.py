"""Evaluate the active, frozen forecaster on the HK Express network catalogue.

This is an out-of-sample check only: no parameter, guard or threshold is fitted
or changed. For every flight and release day (D28/D14/D7) the forecaster sees
snapshots at or before that day; hidden truth (remaining demand requests and
internal fares) is used only for scoring. Output: simulation/hkx_validation/report.json.
"""
import csv
import gzip
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "simulation/hkx_generated"
OUTPUT = ROOT / "simulation/hkx_validation/report.json"
DAYS = (28, 14, 7)
FIELDS = ("flight_id", "days_to_departure", "capacity", "booked_seats", "available_seats", "gross_bookings",
          "cancellations", "normal_base_fare", "normal_total_fare", "mandatory_fees", "interval_days")
SOURCES = ("backend/forecast.py", "backend/nhpp.py", "backend/nhpp_v3.py", "simulation/generated/calibration_v2.json",
           "simulation/generated/calibration_v3_robust.json", "simulation/hkx_generated/snapshots.csv.gz",
           "simulation/hkx_generated/truth.csv.gz", "simulation/hkx_generated/flights.json")


def revenue(requests, capacity):
    total = 0.
    for count, fare in requests:
        sold = min(capacity, count)
        total += sold * fare
        capacity -= sold
    return total


def wilson(p, n, z=1.96):
    center = (p + z*z/(2*n)) / (1 + z*z/n)
    radius = z*math.sqrt(p*(1-p)/n + z*z/(4*n*n)) / (1 + z*z/n)
    return [round(center - radius, 4), round(center + radius, 4)]


def aggregate(rows):
    n = len(rows)
    covered = float(np.mean([r["covered"] for r in rows]))
    baseline = sum(r["baseline_revenue"] for r in rows)
    return {
        "n": n, "protection_coverage": round(covered, 4), "protection_coverage_wilson95": wilson(covered, n),
        "raw_p90_coverage": round(float(np.mean([r["raw_covered"] for r in rows])), 4),
        "demand_mae": round(float(np.mean([abs(r["predicted"] - r["actual"]) for r in rows])), 2),
        "mean_predicted_remaining_demand": round(float(np.mean([r["predicted"] for r in rows])), 2),
        "mean_actual_remaining_demand": round(float(np.mean([r["actual"] for r in rows])), 2),
        "release_rate": round(sum(r["release"] > 0 for r in rows) / n, 4),
        "mean_release_seats": round(float(np.mean([r["release"] for r in rows])), 2),
        "mean_released_seats_unused_by_normal_demand": round(float(np.mean([max(0, r["release"] - max(0, r["actual"] - (r["available"] - r["release"]))) for r in rows])), 2),
        "normal_base_revenue_loss_ratio": round(sum(r["loss"] for r in rows) / baseline, 5) if baseline else 0.,
    }


def run():
    from backend import data
    from backend.forecast import forecast
    with data.use_dataset("hkx"):
        histories = data.histories()
        flights = {f["flight_id"]: f for f in data.flights()}
    truth = defaultdict(list)
    with gzip.open(DATA / "truth.csv.gz", "rt", newline="") as stream:
        for row in csv.DictReader(stream):
            truth[row["flight_id"]].append((int(row["interval_start_day"]), int(row["demand_requests"]), float(row["internal_base_fare"])))
    rows = []
    for number, (flight_id, history) in enumerate(sorted(histories.items()), 1):
        for day in DAYS:
            public = [{k: r[k] for k in FIELDS} for r in history if r["days_to_departure"] >= day]
            future = [(count, fare) for start, count, fare in truth[flight_id] if start <= day]
            p = forecast(public, days_to_departure=day, seed=117)
            actual = sum(c for c, _ in future)
            available, release = p["available_seats"], p["releasable_seats"]
            baseline = revenue(future, available)
            flight = flights[flight_id]
            rows.append({"day": day, "season": flight["season"], "band": flight["demand_band"],
                         "direction": flight["direction"], "actual": actual, "predicted": p["expected_remaining_demand"],
                         "covered": actual <= p["protection_p90"], "raw_covered": actual <= p["raw_protection_p90"],
                         "available": available, "release": release, "baseline_revenue": baseline,
                         "loss": baseline - revenue(future, available - release)})
        if number % 300 == 0:
            print(f"forecast {number}/{len(histories)} flights", flush=True)
    groups = defaultdict(list)
    for row in rows:
        for group in ("all", f"band={row['band']}", f"season={row['season']}", f"direction={row['direction']}"):
            groups[f"D{row['day']}/{group}"].append(row)
    report = {
        "evaluation": "hkx-frozen-forecaster-check-v1", "phase": "out_of_sample_check_no_tuning",
        "flights": len(histories), "days": list(DAYS),
        "source_hashes": {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in SOURCES},
        "notes": ["No forecaster parameter, guard or threshold was fitted or changed for this report.",
                  "protection_coverage: share where remaining normal demand requests <= protected seats (decision coverage).",
                  "normal_base_revenue_loss_ratio: normal base revenue lost by releasing the forecaster's seats, replaying hidden requests at hidden fares.",
                  "Demand bands come from the display-only D28 index and are not forecaster inputs."],
        "results": {key: aggregate(values) for key, values in sorted(groups.items())},
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    result = run()
    for key in ("D28/all", "D14/all", "D7/all"):
        print(key, json.dumps(result["results"][key]))

#!/usr/bin/env python3
"""Generate reproducible synthetic sales histories, CSVs and comparison plots."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.simulator import load_config, simulate_flight, validate_flight


def write_csv(path, rows):
    if not rows:
        return
    with Path(path).open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def export_results(results, destination):
    destination.mkdir(parents=True, exist_ok=True)
    write_csv(destination / "snapshots.csv", [row for r in results for row in r["snapshots"]])
    # Latent demand is unobservable in actual sales data. Export separately.
    event_keys = ["flight_id", "interval_start_day", "interval_start_at", "interval_end_at", "interval_days",
                  "booked_before", "booked_after", "accepted_bookings", "cancellations"]
    write_csv(destination / "booking_events.csv", [{k: row[k] for k in event_keys} for r in results for row in r["events"]])
    write_csv(destination / "outcomes.csv", [r["outcome"] for r in results])
    write_csv(destination / "simulation_parameters_truth.csv", [r["truth"] for r in results])
    write_csv(destination / "simulation_events_truth.csv", [row for r in results for row in r["events"]])


def summary_row(result):
    row = {"flight_id": result["truth"]["flight_id"], "scenario": result["truth"]["scenario"]}
    states = {s["days_to_departure"]: s for s in result["snapshots"]}
    for day in (180, 90, 60, 28, 14, 7, 1, 0):
        if day in states:
            row[f"booked_D{day}"] = states[day]["net_booked_seats"]
            row[f"base_fare_D{day}"] = states[day]["base_fare"]
    row.update(result["outcome"])
    row["total_denied_demand"] = result["truth"]["total_denied_demand"]
    row["first_sold_out_day"] = next((s["days_to_departure"] for s in result["snapshots"] if s["quote_status"] == "sold_out"), None)
    return row


def run(args):
    config = load_config(args.config)
    if args.seed is not None:
        config["seed"] = args.seed
    if config["seed"] < 0 or args.replicates < 2:
        raise ValueError("seed must be >= 0 and replicates must be >= 2")
    if args.flights_csv:
        with Path(args.flights_csv).open(encoding="utf-8-sig", newline="") as handle:
            flights = list(csv.DictReader(handle))
        for flight in flights:
            flight["capacity"] = int(flight["capacity"])
    else:
        flights = [config["demo_flight"]]
    if not flights:
        raise ValueError("flights CSV must contain at least one flight")
    for flight in flights:
        validate_flight(flight)
    if len({f["flight_id"] for f in flights}) != len(flights):
        raise ValueError("flight_id must be unique in input")
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    representative, ensembles = [], []
    for flight_index, flight in enumerate(flights):
        for scenario in config["scenarios"]:
            tagged = {**flight, "flight_id": f"{flight['flight_id']}__{scenario['name']}__rep"}
            representative.append(simulate_flight(tagged, scenario, config, config["seed"] + flight_index * 100000))
            for replicate in range(args.replicates):
                # Same seed across scenario variants gives shared theta/price
                # shocks, but is NOT a paired individual-traveller experiment.
                tagged = {**flight, "flight_id": f"{flight['flight_id']}__{scenario['name']}__sim{replicate:04d}"}
                ensembles.append(simulate_flight(tagged, scenario, config,
                                                config["seed"] + flight_index * 100000 + replicate + 1))
    export_results(representative, output)
    if args.export_ensemble:
        export_results(ensembles, output / "ensemble")
    write_csv(output / "representative_summary.csv", [summary_row(r) for r in representative])
    write_csv(output / "ensemble_outcomes.csv", [{**r["outcome"], "scenario": r["truth"]["scenario"]} for r in ensembles])
    write_csv(output / "flights.csv", flights)
    stats = []
    for s in config["scenarios"]:
        group = [r for r in ensembles if r["truth"]["scenario"] == s["name"]]
        final = np.array([r["outcome"]["final_occupancy_rate"] for r in group])
        at28 = np.array([next(x["occupancy_rate"] for x in r["snapshots"] if x["days_to_departure"] == 28) for r in group])
        stats.append({"scenario": s["name"], "simulations": len(group), "mean_occupancy_D28": float(at28.mean()),
                      "mean_final_occupancy": float(final.mean()), "p10_final_occupancy": float(np.quantile(final, .1)),
                      "p90_final_occupancy": float(np.quantile(final, .9)), "fraction_final_sold_out": float((final == 1).mean())})
    write_csv(output / "ensemble_summary.csv", stats)
    images = []
    if not args.no_plots:
        from src.simulation_plots import plot_results
        for i, flight in enumerate(flights):
            subset = representative[i * len(config["scenarios"]):(i+1) * len(config["scenarios"])]
            prefix = flight["flight_id"] + "__"
            band = [r for r in ensembles if r["truth"]["flight_id"].startswith(prefix)]
            images.extend(str(p.relative_to(output)) for p in plot_results(subset, output if len(flights) == 1 else output / f"flight_{i:03d}", band))
    canonical = json.dumps(config, sort_keys=True, ensure_ascii=False)
    manifest = {
        "simulation_version": config["version"], "config_sha256": hashlib.sha256(canonical.encode()).hexdigest(),
        "seed": config["seed"], "python_version": platform.python_version(), "numpy_version": np.__version__,
        "representative_histories": len(representative), "ensemble_histories": len(ensembles),
        "snapshots_per_history": config["horizon_days"]+1, "ensemble_raw_exported": args.export_ensemble,
        "config": config, "input_flights": flights, "plots": images,
        "provenance": {"flight_background": "per flights.csv source_kind; default assumed_demo; no API request made",
                       "bookings": "simulated", "prices_and_fees": "simulated assumptions", "latent_parameters": "assumed distributions"},
        "semantics": {
            "snapshots": "Start-state and quote before next interval; 1d flows refer to previous completed interval.",
            "D0": "Sales-cutoff snapshot; no quote. Last interval shorter than 24h by cutoff offset.",
            "cancellations": "Previously booked passengers cancel at interval end; seats reopen next interval.",
            "prices": "Normal public fares, not member prices. Null at sellout/closure, never zero-filled.",
            "denied_demand": "Synthetic counterfactual requests at policy fare, not observed bookings.",
            "bands": "Cross-simulation P10-P90 scenario spread, not calibrated forecast intervals.",
            "model_features": "Exclude scenario, IDs encoding scenario, hidden truth and outcomes; group same-source replicas for splitting.",
            "scope": "Fixed capacity, 1 adult one way, no groups/no-shows/rebooking/overbooking/member offers; no true demand calibration.",
            "training": "CSV output is not yet a leakage-safe training split or a validated model."
        }
    }
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({"output": str(output.resolve()), "representative_histories": len(representative),
                      "ensemble_histories": len(ensembles), "summary": stats, "plots": images}, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "configs/simulation.json")
    parser.add_argument("--output", type=Path, default=ROOT / "outputs/simulation")
    parser.add_argument("--seed", type=int)
    parser.add_argument("--replicates", type=int, default=200, help="Independent histories per scenario and input flight")
    parser.add_argument("--flights-csv", type=Path, help="Normalized background CSV; not raw OAG JSON")
    parser.add_argument("--export-ensemble", action="store_true", help="Also export all ensemble snapshots and events")
    parser.add_argument("--no-plots", action="store_true")
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()

"""Generate an exact number of synthetic daily flight snapshots.

Conditional on sampled exogenous parameters, interval requests are independent
NHPP increments. Inventory limits and cancellations are a separate observation
layer. No booking, fare or customer preference here is observed HK Express data.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import math
import platform
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

FIELDS = [
    "flight_id", "snapshot_at", "days_to_departure", "capacity",
    "booked_seats", "available_seats", "empty_rate", "normal_base_fare",
    "mandatory_fees", "normal_total_fare", "gross_bookings", "cancellations",
    "interval_days", "origin", "destination", "departure_at", "source_kind",
    "currency", "cutoff_at", "quote_status",
]
TRUTH_FIELDS = [
    "flight_id", "interval_start_day", "interval_end_day", "beta",
    "latent_scale", "expected_demand", "demand_requests", "denied_demand",
    "internal_base_fare", "scenario",
]
SCENARIOS = ("low", "typical", "high", "surge", "pulse", "declining")
ROUTES = ("FUK", "KIX", "NRT", "TPE", "ICN", "BKK", "DAD", "OKA")
HKT = timezone(timedelta(hours=8))


def _integral(beta: float, start: float, end: float) -> float:
    """Integral of exp(beta * (u - 180)) without a beta=0 singularity."""
    if abs(beta) < 1e-10:
        return end - start
    return math.exp(beta * (start - 180)) * math.expm1(beta * (end - start)) / beta


def _schedule(index: int) -> dict:
    # Assumed timetable for simulator diversity, not an assertion of UO service.
    departure = datetime(2027, 5, 15, 7, 0, tzinfo=HKT) + timedelta(
        days=index // len(ROUTES), hours=(index % 4) * 3
    )
    return {
        "flight_id": f"SYN-{index + 1:05d}", "origin": "HKG",
        "destination": ROUTES[index % len(ROUTES)],
        "departure_at": departure.isoformat(),
        "capacity": (180, 188, 230, 236)[index % 4],
    }


def simulate_flight(index: int, seed: int = 117) -> dict:
    """Return all 181 snapshots, 180 truth increments and one flight summary."""
    flight = _schedule(index)
    rng = np.random.default_rng(np.random.SeedSequence([seed, index]))
    parameter_rng, arrival_rng, cancellation_rng = [
        np.random.default_rng(s) for s in np.random.SeedSequence([seed, index]).spawn(3)
    ]
    scenario = SCENARIOS[index % len(SCENARIOS)]
    beta_ranges = {
        "low": (.002, .018), "typical": (.008, .025), "high": (.012, .032),
        "surge": (.006, .018), "pulse": (.006, .018), "declining": (-.012, -.002),
    }
    beta = float(parameter_rng.uniform(*beta_ranges[scenario]))
    if index % 17 == 0:
        beta = 0.0
    latent_scale = float(parameter_rng.gamma(18.0, 1 / 18.0))
    multiplier = {"low": .55, "typical": 1.05, "high": 1.7,
                  "surge": 1.0, "pulse": .85, "declining": .85}[scenario]
    capacity = flight["capacity"]
    departure = datetime.fromisoformat(flight["departure_at"])
    cutoff = departure - timedelta(hours=2)
    # Normalize only baseline shape; late shocks then genuinely add demand.
    theta = capacity * multiplier * latent_scale / _integral(beta, 0, 180 - 2 / 24)
    reference_base = int(parameter_rng.choice([280, 380, 480, 580, 680, 780]))
    mandatory = 250
    # Draw all price noise in advance: prices cannot respond to future bookings.
    price_noise = rng.normal(0, .035, 181)
    step_day = int(parameter_rng.choice([28, 21, 14]))
    shock_day = int(parameter_rng.choice([21, 14, 7]))
    shock_multiplier = float(parameter_rng.uniform(2.2, 4.0))
    daily_cancel_probability = float(parameter_rng.uniform(.0002, .0014))
    snapshots, truth = [], []
    booked = previous_gross = previous_cancel = 0
    previous_exposure = 0.0
    for pos, day in enumerate(range(180, -1, -1)):
        observed = departure - timedelta(days=day) if day else cutoff
        factor = 1.0 + (.18 if day <= step_day else 0) + (.25 if day <= 7 else 0)
        if 42 <= day <= 48 or 16 <= day <= 19:
            factor *= .8
        base = max(100, int(round(reference_base * factor * math.exp(price_noise[pos]) / 10) * 10))
        available = capacity - booked
        quote_status = "closed" if day == 0 else ("sold_out" if available == 0 else "open")
        public_base = base if quote_status == "open" else None
        row = {
            **flight, "snapshot_at": observed.isoformat(), "days_to_departure": day,
            "booked_seats": booked, "available_seats": available,
            "empty_rate": round(available / capacity, 8),
            "normal_base_fare": public_base, "mandatory_fees": mandatory,
            "normal_total_fare": base + mandatory if public_base is not None else None,
            "gross_bookings": previous_gross, "cancellations": previous_cancel,
            "interval_days": previous_exposure, "source_kind": "assumed_demo",
            "currency": "HKD", "cutoff_at": cutoff.isoformat(), "quote_status": quote_status,
        }
        snapshots.append(row)
        if day == 0:
            break
        exposure = 22 / 24 if day == 1 else 1.0
        start_u = 180 - day
        mean = theta * _integral(beta, start_u, start_u + exposure)
        mean *= ((base + mandatory) / (reference_base + mandatory)) ** -.8
        if scenario == "surge" and day <= shock_day:
            mean *= shock_multiplier
        if scenario == "pulse" and shock_day - 2 <= day <= shock_day:
            mean *= shock_multiplier
        requests = int(arrival_rng.poisson(mean))
        gross = min(requests, available)
        cancel_p = 1 - (1 - daily_cancel_probability) ** exposure
        cancellations = int(cancellation_rng.binomial(booked, cancel_p))
        truth.append({
            "flight_id": flight["flight_id"], "interval_start_day": day,
            "interval_end_day": day - 1, "beta": round(beta, 10),
            "latent_scale": round(latent_scale, 10), "expected_demand": round(mean, 10),
            "demand_requests": requests, "denied_demand": requests - gross,
            "internal_base_fare": base, "scenario": scenario,
        })
        booked = booked + gross - cancellations
        previous_gross, previous_cancel, previous_exposure = gross, cancellations, exposure
    at28 = snapshots[152]
    summary = {
        **flight, "scenario": scenario, "source_kind": "assumed_demo",
        "snapshot_count": 181, "history_start_day": 180,
        "booked_d28": at28["booked_seats"], "available_d28": at28["available_seats"],
        "empty_rate_d28": at28["empty_rate"], "normal_base_fare_d28": at28["normal_base_fare"],
        "final_booked": booked, "final_empty_rate": round((capacity - booked) / capacity, 8),
    }
    return {"snapshots": snapshots, "truth": truth, "summary": summary}


@contextmanager
def _gzip_text(path: Path):
    # Zero timestamp and filename make the compressed artifact reproducible.
    with path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
            with io.TextIOWrapper(compressed, encoding="utf-8", newline="") as text:
                yield text


def generate(rows: int = 200_000, seed: int = 117, output: Path | str | None = None) -> dict:
    """Write exactly rows records, retaining complete final 28-day windows."""
    if isinstance(rows, bool) or not isinstance(rows, int) or rows < 29:
        raise ValueError("rows must be an integer >= 29")
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise ValueError("seed must be a non-negative integer")
    output = Path(output) if output else Path(__file__).parent / "generated"
    output.mkdir(parents=True, exist_ok=True)
    full, tail = divmod(rows, 181)
    # If a requested tail is too short for D28, redistribute over two flights.
    sizes = [181] * full
    if tail:
        if tail < 29 and sizes:
            sizes[-1] -= 29 - tail
            tail = 29
        sizes.append(tail)
    summaries, examples = [], []
    count = 0
    with _gzip_text(output / "snapshots.csv.gz") as sf, _gzip_text(output / "truth.csv.gz") as tf:
        snapshot_writer = csv.DictWriter(sf, fieldnames=FIELDS)
        truth_writer = csv.DictWriter(tf, fieldnames=TRUTH_FIELDS)
        snapshot_writer.writeheader()
        truth_writer.writeheader()
        for index, size in enumerate(sizes):
            result = simulate_flight(index, seed)
            history = result["snapshots"][-size:]
            snapshot_writer.writerows(history)
            truth_writer.writerows(result["truth"])
            summary = result["summary"]
            summary.update(snapshot_count=size, history_start_day=size - 1)
            summaries.append(summary)
            count += len(history)
            if index < len(SCENARIOS):
                examples.extend(history[-29:])
    (output / "flights.json").write_text(json.dumps(summaries, ensure_ascii=False, indent=2), encoding="utf-8")
    with (output / "sample.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(examples)
    manifest = {
        "schema_version": "1.0", "generator_version": "nhpp-exogenous-1",
        "python_version": platform.python_version(), "numpy_version": np.__version__,
        "seed": seed, "rows": count, "flights": len(summaries),
        "source_kind": "assumed_demo", "currency": "HKD", "timezone": "Asia/Hong_Kong",
        "interval_definition": "Counts and interval_days describe the interval completed into this snapshot; D180 has exposure 0. D0 is departure minus 2h, not boarding.",
        "price_definition": "Quote applies AFTER the snapshot. Missing when sold out or at cutoff; missing is not a zero fare.",
        "cutoff_hours": 2, "history_lengths": dict(Counter(sizes)),
        "row_count_note": "Exactly 200000 default: 1104 full D180-D0 paths and one D175-D0 path; all paths were generated from D180, omitted warmup is not an additional observation.",
        "scenarios": dict(Counter(s["scenario"] for s in summaries)),
        "scenario_is_hidden_provenance": True,
        "capacity_definition": "Assumed fixed sellable seat capacity, not observed aircraft occupancy.",
        "assumptions": [
            "Timetable, routes, capacities, fares, taxes, demand, and cancellation rates are synthetic; no observed HK Express booking or fare history was used.",
            "Conditional on latent parameters and exogenous fare paths, demand is an NHPP with exponential trend and piecewise shocks.",
            "Random flight parameters yield a mixture of NHPPs across flights; accepted bookings are capacity-censored and not themselves an uncensored NHPP.",
            "Cancellations occur at the end of each interval and release seats for the next interval.",
            "Fees of HK$250 and elasticity 0.8 are assumptions, not airline estimates.",
            "Flight-level scenario, final outcomes and truth.csv.gz must not be predictor features.",
            "One request represents one seat; group-arrival shocks require a separate compound-process stress test.",
        ],
        "files": {},
    }
    for name in ("snapshots.csv.gz", "truth.csv.gz", "flights.json", "sample.csv"):
        file = output / name
        manifest["files"][name] = {"bytes": file.stat().st_size, "sha256": hashlib.sha256(file.read_bytes()).hexdigest()}
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def validate(path: Path | str) -> dict:
    """Stream validation: inventory identities, times, price and row counts."""
    path = Path(path)
    count = flights = 0
    previous = None
    with gzip.open(path / "snapshots.csv.gz", "rt", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            count += 1
            capacity, booked, available = (int(row[k]) for k in ("capacity", "booked_seats", "available_seats"))
            day = int(row["days_to_departure"])
            if not (0 <= booked <= capacity and booked + available == capacity):
                raise ValueError(f"inventory identity failed at row {count}")
            if abs(float(row["empty_rate"]) - available / capacity) > 1e-7:
                raise ValueError(f"empty rate failed at row {count}")
            if row["normal_base_fare"] and int(row["normal_base_fare"]) + int(row["mandatory_fees"]) != int(row["normal_total_fare"]):
                raise ValueError(f"fare decomposition failed at row {count}")
            if day == 0 and (row["normal_base_fare"] or row["normal_total_fare"]):
                raise ValueError("cutoff must not expose a quote")
            if previous and previous["flight_id"] == row["flight_id"]:
                if int(previous["days_to_departure"]) - day != 1:
                    raise ValueError("non-daily trajectory")
                if booked != int(previous["booked_seats"]) + int(row["gross_bookings"]) - int(row["cancellations"]):
                    raise ValueError("booking conservation failed")
                elapsed = (datetime.fromisoformat(row["snapshot_at"]) - datetime.fromisoformat(previous["snapshot_at"])).total_seconds() / 86400
                if abs(elapsed - float(row["interval_days"])) > 1e-8:
                    raise ValueError("interval exposure mismatch")
            else:
                if previous and int(previous["days_to_departure"]) != 0:
                    raise ValueError("trajectory does not end at cutoff")
                flights += 1
            previous = row
    if previous is None or int(previous["days_to_departure"]) != 0:
        raise ValueError("last trajectory missing cutoff")
    manifest = json.loads((path / "manifest.json").read_text())
    if count != manifest["rows"] or flights != manifest["flights"]:
        raise ValueError("manifest counts disagree")
    for name, info in manifest["files"].items():
        if hashlib.sha256((path / name).read_bytes()).hexdigest() != info["sha256"]:
            raise ValueError(f"file checksum mismatch: {name}")
    return {"rows": count, "flights": flights, "inventory_conservation": "passed", "timestamps": "passed", "checksums": "passed"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=int, default=200_000)
    parser.add_argument("--seed", type=int, default=117)
    parser.add_argument("--output", type=Path, default=Path(__file__).parent / "generated")
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    if not args.validate_only:
        generate(args.rows, args.seed, args.output)
    print(json.dumps(validate(args.output), ensure_ascii=False))


if __name__ == "__main__":
    main()

"""Near-term HK Express departures for live-feeling demos (generator `hkx-recent-2`).

Reuses `simulation/hkx_generate.py` unchanged (same OAG weekday template, fleet,
fares, NHPP demand and cancellation mechanics) but samples departures 7, 14 and
28 days after an anchor date, so that on the anchor date each flight sits exactly
at one of the D7 / D14 / D28 release rounds.

Like a real airline feed, the published files stop at the anchor date ("today"):
snapshots dated after it, truth intervals ending after it and final outcomes are
removed. Each flight records `observed_through_day`, its days to departure on the
anchor date; later release rounds have not been reached and cannot be forecast.

The anchor date is part of the data: the files do not move with the clock. On a
later day the same flights are fewer days from departure; regenerate with a new
`--anchor` (into a new output directory) rather than overwriting published bytes.

All bookings, fares, demand and cancellations are synthetic.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path

from simulation import hkx_generate as hkx
from simulation.generate import FIELDS, TRUTH_FIELDS

VERSION = "hkx-recent-2"
DATASET = "hkx_recent_generated"
SEED = 20261115
ANCHOR = "2026-11-15"
HORIZONS = (7, 14, 28)
MAX_RELEASE_DAY = 28
OUTPUT = Path(__file__).parent / DATASET


def season(day: date) -> str:
    """Map a departure date to the generator's season labels (assumed, HK-centric)."""
    if (day.month, day.day) >= (12, 20) or (day.month, day.day) <= (1, 3):
        return "christmas"
    if day.month in (7, 8):
        return "summer_peak"
    if day.month == 10 and day.day <= 7:
        return "cn_golden_week"
    if day.month in (11,) and day.day >= 20 or day.month in (9, 10):
        return "autumn"
    if day.month in (4, 5):
        return "shoulder"
    return "low"


def dates(anchor: str, horizons=HORIZONS):
    start = date.fromisoformat(anchor)
    return tuple((str(start + timedelta(days=h)), season(start + timedelta(days=h))) for h in horizons)


def _read_rows(path):
    with gzip.open(path, "rt", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _write_rows(path, fields, rows):
    raw, gz = hkx._gzip_writer(path)
    writer = csv.DictWriter(hkx._Text(gz), fieldnames=fields, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    gz.close()
    raw.close()


def truncate(output, anchor):
    """Keep only what is observable on the anchor date; return {flight_id: observed_through_day}."""
    today = date.fromisoformat(anchor)
    snapshots = [r for r in _read_rows(output / "snapshots.csv.gz")
                 if datetime.fromisoformat(r["snapshot_at"]).date() <= today]
    through = {}
    for row in snapshots:
        day = int(row["days_to_departure"])
        through[row["flight_id"]] = min(day, through.get(row["flight_id"], day))
    # Flights that have not entered the D28 window yet have no release round and
    # cannot be forecast (the forecaster covers D28..D0); leave them out today.
    through = {k: v for k, v in through.items() if v <= MAX_RELEASE_DAY}
    snapshots = [r for r in snapshots if r["flight_id"] in through]
    truth = [r for r in _read_rows(output / "truth.csv.gz")
             if r["flight_id"] in through and int(r["interval_end_day"]) >= through[r["flight_id"]]]
    _write_rows(output / "snapshots.csv.gz", FIELDS, snapshots)
    _write_rows(output / "truth.csv.gz", TRUTH_FIELDS, truth)
    return through, len(snapshots), len(truth)


def generate(anchor=ANCHOR, seed=SEED, output=OUTPUT, horizons=HORIZONS):
    output = Path(output)
    hkx.DATES = dates(anchor, horizons)
    # Three dates are too few for the full-network realism ranges; record the facts
    # instead of rejecting the sample.
    hkx.TARGETS = {}
    full = hkx.generate(seed, output)
    through, rows, truth_rows = truncate(output, anchor)
    flights = [f for f in json.loads((output / "flights.json").read_text(encoding="utf-8")) if f["flight_id"] in through]
    for flight in flights:
        day = through[flight["flight_id"]]
        flight.update(dataset=DATASET, data_as_of=anchor, observed_through_day=day, snapshot_count=181 - day,
                      final_booked=None, final_empty_rate=None)
        if day > 28:  # D28 itself has not been observed yet
            flight.update(booked_d28=None, available_d28=None, empty_rate_d28=None, normal_base_fare_d28=None)
    # Always LF: .gitattributes stores text as LF, so manifest hashes must describe LF bytes.
    (output / "flights.json").write_text(json.dumps(flights, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    facts = manifest.pop("stylized_facts")
    manifest.update({
        "generator_version": VERSION, "base_generator_version": hkx.VERSION, "dataset": DATASET,
        "anchor_date": anchor, "horizons_days": list(horizons),
        "release_round_on_anchor": {d: f"D{h}" for (d, _), h in zip(hkx.DATES, horizons)},
        "rows": rows, "truth_rows": truth_rows, "flights": len(flights),
        "simulated_rows_before_truncation": full["rows"], "simulated_flights_before_truncation": full["flights"],
        "observed_through_day_counts": {f"D{k}": v for k, v in sorted(Counter(through.values()).items())},
        "generator_check_before_truncation": facts, "targets": {},
    })
    manifest["assumptions"] = [
        f"Departures are {', '.join(map(str, horizons))} days after the anchor date {anchor}; on that date each flight is at its matching release round.",
        f"Only data observable on {anchor} is published: later snapshots, later truth intervals and final outcomes are removed after simulation.",
        "Return legs of late-evening outbound flights depart after midnight, one day later (D8/D15 on the anchor date); "
        f"those beyond D{MAX_RELEASE_DAY} have not entered the release window and are left out.",
        "The files are fixed to the anchor date and do not move with the clock.",
        "Seasons for these dates are assumed labels; realism targets of the full catalogue are not enforced on three dates; "
        "generator_check_before_truncation describes the full simulated paths, which are not published.",
        *manifest.get("assumptions", []),
    ]
    manifest["files"] = {name: hashlib.sha256((output / name).read_bytes()).hexdigest()
                         for name in ("snapshots.csv.gz", "truth.csv.gz", "flights.json")}
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--anchor", default=ANCHOR, help="date treated as 'today' (YYYY-MM-DD)")
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--output", default=str(OUTPUT))
    args = parser.parse_args()
    manifest = generate(args.anchor, args.seed, args.output)
    print(json.dumps({k: manifest[k] for k in ("anchor_date", "release_round_on_anchor", "rows", "truth_rows",
                                                "flights", "directed_routes", "observed_through_day_counts")},
                     indent=2))


if __name__ == "__main__":
    main()

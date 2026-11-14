"""Verified D28 normal-demand bands for catalogue navigation, never model inputs.

The index is generated from as-of observations. Scenario names and realized
departure occupancy are deliberately excluded. The thresholds are UI grouping
assumptions, not fitted customer segments or guarantees of releasable capacity.
"""
from __future__ import annotations

from collections import Counter
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = "nhpp-d28-demand-catalog-v1"
REFERENCE_DAY = 28
FORECAST_SEED = 117
THRESHOLDS = {"low_below": .60, "high_at_least": .85}
INDEX_PATH = "simulation/demand_catalog.json"
SOURCE_FILES = (
    "backend/nhpp.py", "backend/nhpp_v3.py", "backend/forecast.py", "simulation/generated/calibration_v3_robust.json", "simulation/generated/nhpp_v3_robust_final.json", "simulation/evaluate_nhpp_v3.py", "simulation/calibrate_nhpp_v3_robust.py", "simulation/generated/calibration_v3.json", "backend/data.py", "backend/demand_catalog.py",
    "simulation/generated/calibration_v2.json",
    *tuple(f"simulation/{dataset}/{filename}"
           for dataset in ("generated", "network_generated", "member_demo_generated", "hkx_recent_generated")
           for filename in ("snapshots.csv.gz", "flights.json")),
)
OBSERVATION_FIELDS = (
    "flight_id", "days_to_departure", "capacity", "booked_seats",
    "available_seats", "gross_bookings", "cancellations", "normal_base_fare",
    "normal_total_fare", "mandatory_fees", "interval_days",
)


def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def classify(load_rate):
    """Return unknown rather than classify a missing or malformed forecast."""
    if not _finite(load_rate) or not 0 <= load_rate <= 1:
        return "unknown"
    return "low" if load_rate < THRESHOLDS["low_below"] else "high" if load_rate >= THRESHOLDS["high_at_least"] else "medium"


def records_digest(records):
    return hashlib.sha256(json.dumps(records, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def source_hashes(root=ROOT):
    root = Path(root)
    return {name: hashlib.sha256((root/name).read_bytes()).hexdigest() for name in SOURCE_FILES}


def forecast_record(flight_id, rows, predictor=None):
    if predictor is None:
        from .forecast import forecast
        predictor = forecast
    # Explicit pre-filter and field allowlist keep future rows and hidden labels
    # out even if a different loader later includes them in its records.
    observed = [{key: row[key] for key in OBSERVATION_FIELDS if key in row}
                for row in rows if row["days_to_departure"] >= REFERENCE_DAY]
    prediction = predictor(observed, days_to_departure=REFERENCE_DAY, seed=FORECAST_SEED)
    capacity, empty = prediction["capacity"], prediction["expected_empty_seats"]
    if not _finite(capacity) or capacity <= 0 or not _finite(empty) or not 0 <= empty <= capacity:
        raise ValueError(f"Invalid normal-demand forecast for {flight_id}")
    load = round(1-empty/capacity, 8)
    return {"flight_id": flight_id, "demand_band": classify(load),
            "demand_expected_load_rate": load, "demand_reference_day": REFERENCE_DAY,
            "d28_releasable": prediction.get("releasable_seats")}


def build_index(histories, root=ROOT, progress=None):
    before = source_hashes(root)
    records = []
    for number, (flight_id, rows) in enumerate(sorted(histories.items()), 1):
        records.append(forecast_record(flight_id, rows))
        if progress is not None:
            progress(number, len(histories))
    after = source_hashes(root)
    if before != after:
        raise ValueError("Demand-index sources changed during generation; rerun with stable sources")
    return {"version": VERSION, "reference_day": REFERENCE_DAY, "forecast_seed": FORECAST_SEED,
            "thresholds": THRESHOLDS, "source_files": after,
            "interpretation": "D28 NHPP expected final normal occupancy; display-only bands, not realized demand or member release quotas.",
            "flight_count": len(records), "counts": dict(sorted(Counter(row["demand_band"] for row in records).items())),
            "records_sha256": records_digest(records), "records": records}


def _signature(root):
    result = []
    for name in (INDEX_PATH, *SOURCE_FILES):
        try:
            stat = (root/name).stat()
            result.append((name, stat.st_mtime_ns, stat.st_size, stat.st_ctime_ns))
        except FileNotFoundError:
            result.append((name, None))
    return tuple(result)


@lru_cache(maxsize=4)
def _load(root_string, signature):
    root = Path(root_string)
    if not (root/INDEX_PATH).is_file():
        return {}, "missing"
    try:
        obj = json.loads((root/INDEX_PATH).read_text())
        if (not isinstance(obj, dict) or obj.get("version") != VERSION
                or obj.get("reference_day") != REFERENCE_DAY or obj.get("forecast_seed") != FORECAST_SEED
                or obj.get("thresholds") != THRESHOLDS):
            return {}, "invalid"
        if obj.get("source_files") != source_hashes(root):
            return {}, "stale"
        records = obj.get("records")
        if not isinstance(records, list) or obj.get("flight_count") != len(records) or obj.get("records_sha256") != records_digest(records):
            return {}, "invalid"
        indexed = {}
        for row in records:
            if not isinstance(row, dict):
                return {}, "invalid"
            fid = row.get("flight_id")
            band = classify(row.get("demand_expected_load_rate"))
            if (not isinstance(fid, str) or not fid or fid in indexed or band == "unknown"
                    or row.get("demand_band") != band or row.get("demand_reference_day") != REFERENCE_DAY):
                return {}, "invalid"
            indexed[fid] = row
        if obj.get("counts") != dict(Counter(row["demand_band"] for row in records)):
            return {}, "invalid"
        return indexed, "current"
    except FileNotFoundError:
        return {}, "stale"
    except (OSError, ValueError, TypeError, OverflowError):
        return {}, "invalid"


def enrich(flights, root=ROOT):
    """Return fresh catalogue objects; unavailable evidence stays unclassified."""
    root = Path(root).resolve()
    records, status = _load(str(root), _signature(root))
    # A partial index must not silently hide unclassified records from filters.
    if status == "current" and set(records) != {flight["flight_id"] for flight in flights}:
        records, status = {}, "invalid"
    result = []
    for flight in flights:
        item = {**flight, "demand_band": "unknown", "demand_expected_load_rate": None,
                "demand_reference_day": REFERENCE_DAY, "demand_source_status": status}
        row = records.get(flight["flight_id"])
        if row is not None:
            item.update({key: row[key] for key in ("demand_band", "demand_expected_load_rate", "demand_reference_day")})
        if row is not None and flight.get('dataset') == 'member_demo_generated':
            quota = row.get('d28_releasable')
            if isinstance(quota, int) and not isinstance(quota, bool) and 0 <= quota <= flight.get('capacity', 0):
                item['demo_d28_releasable'] = quota
        result.append(item)
    return result

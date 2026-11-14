"""HK Express network synthetic booking curves (generator `hkx-network-1`).

Covers every destination HK Express listed as currently served (Wikipedia,
March 2026) plus Wuxi (launched 17 July 2026), in both directions, on the
four fleet types and seat configurations HK Express publishes.

What is sourced versus assumed
------------------------------
Sourced: destination list and fleet seat counts (public, 2026); the weekly
departure template in simulation/hkx_schedule_profile.json (flight numbers,
departure times, aircraft codes and elapsed times of every UO departure from
HKG in one OAG sample week, 16-22 Nov 2026). Each sampled date reuses that
template for its weekday.

Assumed (synthetic): six seasonal destinations absent from the sample week
operate only in the IATA summer season with assumed frequencies and times;
return legs use the outbound number + 1 and depart after the outbound elapsed
time plus a 55-minute turn; fare levels, per-country passenger charges,
demand, seasonality, weekday effects and every booking/cancellation path.
No observed HK Express booking, fare or customer data is used.

The demand process is the same exogenous-fare NHPP as `simulation/generate.py`
(exponential trend, optional surge/pulse shocks, fare elasticity -0.8,
binomial cancellations, capacity censoring), so the frozen NHPP forecaster's
modelling assumptions still hold. Fare paths are drawn in advance and never
respond to bookings.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
import platform
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

from simulation.generate import FIELDS, TRUTH_FIELDS, _integral

VERSION = "hkx-network-2"
SEED = 2027
OUTPUT = Path(__file__).parent / "hkx_generated"
HKT = timezone(timedelta(hours=8))
HKG = (22.31, 113.92)
PROFILE = Path(__file__).parent / "hkx_schedule_profile.json"
AIRCRAFT_CODES = {"32Q": ("A321neo", 236), "321": ("A321", 230), "32N": ("A320neo", 188),
                  "320": ("A320", 180), "32A": ("A320", 180)}
SUMMER_SEASON = ("2027-03-28", "2027-10-30")  # IATA northern summer 2027

# (code, city, country, lat, lon, assumed weekly pairs, demand index)
# The weekly-pairs column is used only for destinations missing from the OAG
# sample week (seasonal routes); all others take frequencies from the profile.
DESTINATIONS = (
    ("NRT", "Tokyo Narita", "JP", 35.77, 140.39, 35, 1.00),
    ("HND", "Tokyo Haneda", "JP", 35.55, 139.78, 28, 1.02),
    ("KIX", "Osaka Kansai", "JP", 34.43, 135.24, 35, 1.00),
    ("NGO", "Nagoya", "JP", 34.86, 136.81, 14, .93),
    ("FUK", "Fukuoka", "JP", 33.59, 130.45, 14, .95),
    ("OKA", "Okinawa Naha", "JP", 26.20, 127.65, 14, .94),
    ("SDJ", "Sendai", "JP", 38.14, 140.92, 4, .86),
    ("HIJ", "Hiroshima", "JP", 34.44, 132.92, 4, .87),
    ("TAK", "Takamatsu", "JP", 34.21, 134.02, 4, .85),
    ("FSZ", "Shizuoka", "JP", 34.80, 138.19, 3, .83),
    ("KMQ", "Komatsu", "JP", 36.39, 136.41, 3, .84),
    ("ISG", "Ishigaki", "JP", 24.40, 124.25, 4, .88),
    ("SHI", "Shimojishima", "JP", 24.83, 125.14, 3, .86),
    ("ICN", "Seoul Incheon", "KR", 37.46, 126.44, 35, 1.00),
    ("PUS", "Busan", "KR", 35.18, 128.94, 14, .93),
    ("CJU", "Jeju", "KR", 33.51, 126.49, 7, .90),
    ("TAE", "Daegu", "KR", 35.89, 128.66, 4, .84),
    ("CJJ", "Cheongju", "KR", 36.72, 127.50, 3, .82),
    ("TPE", "Taipei Taoyuan", "TW", 25.08, 121.23, 28, 1.00),
    ("KHH", "Kaohsiung", "TW", 22.58, 120.35, 7, .90),
    ("RMQ", "Taichung", "TW", 24.26, 120.62, 14, .92),
    ("BKK", "Bangkok Suvarnabhumi", "TH", 13.69, 100.75, 21, .98),
    ("CNX", "Chiang Mai", "TH", 18.77, 98.96, 7, .88),
    ("HKT", "Phuket", "TH", 8.11, 98.32, 7, .90),
    ("DAD", "Da Nang", "VN", 16.04, 108.20, 14, .94),
    ("HAN", "Hanoi", "VN", 21.22, 105.81, 7, .88),
    ("CXR", "Nha Trang", "VN", 11.99, 109.22, 7, .87),
    ("PQC", "Phu Quoc", "VN", 10.17, 103.99, 7, .88),
    ("MNL", "Manila", "PH", 14.51, 121.02, 14, .95),
    ("CRK", "Clark", "PH", 15.19, 120.56, 7, .86),
    ("SZB", "Kuala Lumpur Subang", "MY", 3.13, 101.55, 7, .88),
    ("PEN", "Penang", "MY", 5.30, 100.28, 7, .86),
    ("BKI", "Kota Kinabalu", "MY", 5.94, 116.05, 7, .87),
    ("PKX", "Beijing Daxing", "CN", 39.51, 116.41, 7, .90),
    ("NGB", "Ningbo", "CN", 29.83, 121.46, 7, .86),
    ("SYX", "Sanya", "CN", 18.30, 109.41, 7, .88),
    ("CZX", "Changzhou", "CN", 31.92, 119.78, 4, .82),
    ("YIW", "Yiwu", "CN", 29.34, 120.03, 4, .82),
    ("KWE", "Guiyang", "CN", 26.54, 106.80, 4, .83),
    ("WUX", "Wuxi", "CN", 31.49, 120.43, 7, .84),
)

# Sourced seat configurations; fleet counts as of December 2025 (approximate).
FLEET = (
    ("A320", 180, 6), ("A320neo", 188, 10), ("A321", 230, 12), ("A321neo", 236, 16),
)
A321NEO_239_SHARE = 1 / 16  # one A321neo (B-KKR) carries 239 seats

# Assumed per-passenger charges collected at departure, HKD.
DEPARTURE_CHARGES = {"HK": 265, "JP": 190, "KR": 150, "TW": 140, "TH": 160,
                     "VN": 150, "PH": 170, "MY": 110, "CN": 110}
MARKET_FARE = {"JP": 1.10, "KR": 1.00, "TW": .95, "TH": .95, "VN": .90,
               "PH": .90, "MY": .95, "CN": .90}

# Thirteen departure dates spanning a year, mixing weekdays and seasons.
# Every flight operating on each date is generated.
DATES = (
    ("2027-05-18", "shoulder"), ("2027-05-22", "shoulder"), ("2027-06-15", "low"),
    ("2027-07-30", "summer_peak"), ("2027-08-08", "summer_peak"), ("2027-09-14", "low"),
    ("2027-10-01", "cn_golden_week"), ("2027-10-05", "cn_golden_week"),
    ("2027-11-16", "low"), ("2027-11-20", "autumn"), ("2027-12-23", "christmas"),
    ("2028-01-25", "lunar_new_year"), ("2028-01-29", "lunar_new_year"),
)
SEASON_DEMAND = {"low": .84, "shoulder": .95, "autumn": 1.0, "summer_peak": 1.12,
                 "christmas": 1.12, "cn_golden_week": 1.04, "lunar_new_year": 1.08}
SEASON_FARE = {"low": .86, "shoulder": 1.0, "autumn": 1.05, "summer_peak": 1.22,
               "christmas": 1.25, "cn_golden_week": 1.12, "lunar_new_year": 1.2}
# Market-specific holiday effects (multiplier on top of the season).
MARKET_SEASON = {("CN", "cn_golden_week"): 1.18, ("CN", "lunar_new_year"): 1.15,
                 ("JP", "autumn"): 1.08, ("KR", "cn_golden_week"): 1.04}
WEEKDAY_DEMAND = (.95, .92, .92, .97, 1.06, 1.02, 1.05)  # Mon..Sun
SCENARIO_WEIGHTS = {"typical": .42, "high": .14, "low": .14, "surge": .10, "pulse": .10, "declining": .10}
SCENARIO_SHAPE = {"low": .80, "typical": 1.0, "high": 1.08, "surge": .84, "pulse": .88, "declining": .98}
BETA_RANGES = {
    "low": (.002, .018), "typical": (.008, .025), "high": (.012, .032),
    "surge": (.006, .018), "pulse": (.006, .018), "declining": (-.012, -.002),
}
DEMAND_LEVEL = 1.04  # overall calibration constant towards LCC-like load factors
DEMAND_CAP = 1.10


def great_circle_km(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = math.sin((lat2-lat1)/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2
    return 2 * 6371 * math.asin(math.sqrt(h))


def block_minutes(km):
    """Assumed block time: 35 min taxi/climb allowance plus 760 km/h en route."""
    return int(round((35 + km / 760 * 60) / 5) * 5)


def _stable(*parts):
    return int(hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:12], 16)


def _operating_days(code, weekly):
    """Weekdays (0=Mon) a route operates; daily routes run every day."""
    if weekly >= 7:
        return set(range(7))
    offset = _stable(VERSION, code, "days") % 7
    step = 7 / weekly
    return {(offset + int(round(i * step))) % 7 for i in range(weekly)}


def _aircraft(rng, block, weekly):
    """Pick a fleet type for a rotation: share of fleet, bias A321neo to long/busy sectors."""
    weights = []
    for name, seats, count in FLEET:
        w = count
        if name.startswith("A321"):
            w *= 1.35 if block >= 200 or weekly >= 21 else .9
        if name == "A321neo" and block >= 240:
            w *= 1.4
        if name.startswith("A320") and weekly <= 4:
            w *= 1.5
        weights.append(w)
    weights = np.array(weights) / sum(weights)
    name, seats, _ = FLEET[int(rng.choice(len(FLEET), p=weights))]
    if name == "A321neo" and rng.random() < A321NEO_239_SHARE:
        seats = 239
    return name, seats


def _leg_pair(rng, date_text, season, meta, number, out_dep, aircraft, seats, block, weekly, source):
    code, city, country, lat, lon, _, demand_index = meta
    km = great_circle_km(HKG, (lat, lon))
    in_dep = out_dep + timedelta(minutes=block + 55)
    if aircraft == "A321neo" and rng.random() < A321NEO_239_SHARE:
        seats = 239
    for leg, origin, destination, departure, leg_number in (
            ("outbound", "HKG", code, out_dep, number), ("inbound", code, "HKG", in_dep, number + 1)):
        yield {
            "flight_id": f"UO{leg_number}-{departure:%Y%m%d}", "flight_number": f"UO{leg_number}",
            "origin": origin, "destination": destination, "departure_at": departure.isoformat(),
            "capacity": seats, "aircraft_type": aircraft, "destination_city": city, "country": country,
            "direction": leg, "block_minutes": block, "distance_km": round(km), "weekly_frequency": weekly,
            "season": season, "weekday": departure.strftime("%a"), "schedule_source": source,
            "_demand_index": demand_index,
        }


def schedule(seed=SEED):
    """Every flight on the sampled dates: OAG weekday template plus summer-only seasonal routes."""
    profile = json.loads(PROFILE.read_text(encoding="utf-8"))
    meta = {d[0]: d for d in DESTINATIONS}
    template, weekly = {}, Counter()
    for entry in profile["entries"]:
        if entry["destination"] not in meta:
            raise ValueError(f"profile destination {entry['destination']} missing from DESTINATIONS")
        template.setdefault(entry["weekday"], []).append(entry)
        weekly[entry["destination"]] += 1
    seasonal = [d for d in DESTINATIONS if d[0] not in weekly]
    flights = []
    for date_text, season in DATES:
        date = datetime.fromisoformat(date_text).replace(tzinfo=HKT)
        for entry in template[date.weekday()]:
            rng = np.random.default_rng(np.random.SeedSequence([seed, _stable(entry["flight_number"], date_text) % 2**32]))
            hour, minute = map(int, entry["departure_local"].split(":"))
            aircraft, seats = AIRCRAFT_CODES[entry["aircraft_iata"]]
            flights.extend(_leg_pair(rng, date_text, season, meta[entry["destination"]], int(entry["flight_number"][2:]),
                                     date + timedelta(hours=hour, minutes=minute), aircraft, seats,
                                     entry["elapsed_minutes"], weekly[entry["destination"]], "oag_weekly_template"))
        if not SUMMER_SEASON[0] <= date_text <= SUMMER_SEASON[1]:
            continue
        for index, destination in enumerate(seasonal):
            code, _, _, lat, lon, assumed_weekly, _ = destination
            if date.weekday() not in _operating_days(code, assumed_weekly):
                continue
            rng = np.random.default_rng(np.random.SeedSequence([seed, _stable(code, date_text) % 2**32]))
            block = block_minutes(great_circle_km(HKG, (lat, lon)))
            start = int(round((9*60 + int(rng.integers(0, 9*60))) / 5) * 5)
            aircraft, seats = _aircraft(rng, block, assumed_weekly)
            flights.extend(_leg_pair(rng, date_text, season, destination, 980 + 2 * index,
                                     date + timedelta(minutes=start), aircraft, seats, block, assumed_weekly,
                                     "assumed_summer_seasonal"))
    flights.sort(key=lambda f: (f["departure_at"], f["flight_id"]))
    ids = Counter(f["flight_id"] for f in flights)
    clash = Counter((f["origin"], f["destination"], f["departure_at"]) for f in flights)
    if max(ids.values()) > 1 or max(clash.values()) > 1:
        raise ValueError("schedule produced duplicate flights")
    return flights


def _reference_fare(flight, rng):
    country = flight["country"]
    base = (120 + 1.55 * flight["block_minutes"]) * MARKET_FARE[country]
    base *= SEASON_FARE[flight["season"]]
    base *= 1.08 if flight["weekday"] in ("Fri", "Sat", "Sun") else 1.0
    base *= float(rng.uniform(.92, 1.08)) if flight["direction"] == "inbound" else 1.0
    base *= float(np.exp(rng.normal(0, .12)))
    return int(max(150, round(base / 10) * 10))


def simulate(flight, seed=SEED):
    """181 daily snapshots D180..D0 with the same NHPP mechanics as simulation/generate.py."""
    key = _stable(VERSION, flight["flight_id"]) % 2**32
    parameter_rng, arrival_rng, cancellation_rng, price_rng = [
        np.random.default_rng(s) for s in np.random.SeedSequence([seed, key]).spawn(4)]
    names = list(SCENARIO_WEIGHTS)
    scenario = names[int(parameter_rng.choice(len(names), p=list(SCENARIO_WEIGHTS.values())))]
    beta = float(parameter_rng.uniform(*BETA_RANGES[scenario]))
    latent_scale = float(parameter_rng.gamma(18.0, 1 / 18.0))
    country = flight["country"]
    weekday = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun").index(flight["weekday"])
    demand = (DEMAND_LEVEL * flight["_demand_index"] * SEASON_DEMAND[flight["season"]]
              * MARKET_SEASON.get((country, flight["season"]), 1.0) * WEEKDAY_DEMAND[weekday]
              * float(np.exp(parameter_rng.normal(0, .05))))
    # Bound the combined route/season/weekday level: no sampled date is a sell-out certainty.
    demand = min(max(demand, .55), DEMAND_CAP)
    multiplier = demand * SCENARIO_SHAPE[scenario]
    capacity = flight["capacity"]
    departure = datetime.fromisoformat(flight["departure_at"])
    cutoff = departure - timedelta(hours=2)
    theta = capacity * multiplier * latent_scale / _integral(beta, 0, 180 - 2 / 24)
    reference_base = _reference_fare(flight, parameter_rng)
    mandatory = DEPARTURE_CHARGES["HK" if flight["origin"] == "HKG" else country]
    price_noise = price_rng.normal(0, .035, 181)
    step_day = int(parameter_rng.choice([28, 21, 14]))
    shock_day = int(parameter_rng.choice([21, 14, 7]))
    shock_multiplier = float(parameter_rng.uniform(2.2, 4.0))
    daily_cancel_probability = float(parameter_rng.uniform(.0002, .0014))
    public = {k: v for k, v in flight.items() if not k.startswith("_")}
    row_flight = {k: public[k] for k in ("flight_id", "origin", "destination", "departure_at", "capacity")}
    snapshots, truth = [], []
    booked = previous_gross = previous_cancel = 0
    previous_exposure = 0.0
    for position, day in enumerate(range(180, -1, -1)):
        observed = departure - timedelta(days=day) if day else cutoff
        factor = 1.0 + (.18 if day <= step_day else 0) + (.25 if day <= 7 else 0)
        if 42 <= day <= 48 or 16 <= day <= 19:
            factor *= .8
        base = max(100, int(round(reference_base * factor * math.exp(price_noise[position]) / 10) * 10))
        available = capacity - booked
        quote_status = "closed" if day == 0 else ("sold_out" if available == 0 else "open")
        public_base = base if quote_status == "open" else None
        snapshots.append({
            **row_flight, "snapshot_at": observed.isoformat(), "days_to_departure": day,
            "booked_seats": booked, "available_seats": available,
            "empty_rate": round(available / capacity, 8),
            "normal_base_fare": public_base, "mandatory_fees": mandatory,
            "normal_total_fare": base + mandatory if public_base is not None else None,
            "gross_bookings": previous_gross, "cancellations": previous_cancel,
            "interval_days": previous_exposure, "source_kind": "assumed_demo",
            "currency": "HKD", "cutoff_at": cutoff.isoformat(), "quote_status": quote_status,
        })
        if day == 0:
            break
        exposure = 22 / 24 if day == 1 else 1.0
        start = 180 - day
        mean = theta * _integral(beta, start, start + exposure)
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
            "flight_id": flight["flight_id"], "interval_start_day": day, "interval_end_day": day - 1,
            "beta": round(beta, 10), "latent_scale": round(latent_scale, 10),
            "expected_demand": round(mean, 10), "demand_requests": requests,
            "denied_demand": requests - gross, "internal_base_fare": base, "scenario": scenario,
        })
        booked = booked + gross - cancellations
        previous_gross, previous_cancel, previous_exposure = gross, cancellations, exposure
    at28 = snapshots[152]
    summary = {
        **public, "dataset": "hkx_generated", "scenario": scenario, "source_kind": "assumed_demo",
        "snapshot_count": 181, "history_start_day": 180,
        "booked_d28": at28["booked_seats"], "available_d28": at28["available_seats"],
        "empty_rate_d28": at28["empty_rate"], "normal_base_fare_d28": at28["normal_base_fare"],
        "final_booked": booked, "final_empty_rate": round((capacity - booked) / capacity, 8),
    }
    return {"snapshots": snapshots, "truth": truth, "summary": summary}


def stylized_facts(summaries, snapshots_by_flight):
    """Realism targets checked after generation (assumed LCC-like ranges)."""
    loads = np.array([s["final_booked"] / s["capacity"] for s in summaries])
    sold_out = np.array([s["final_booked"] >= s["capacity"] for s in summaries])
    first_sold_out = []
    for s in summaries:
        days = [r["days_to_departure"] for r in snapshots_by_flight[s["flight_id"]] if r["available_seats"] == 0]
        if days:
            first_sold_out.append(max(days))
    fares = {}
    for s in summaries:
        if s["normal_base_fare_d28"]:
            fares.setdefault((s["origin"], s["destination"]), []).append(s["normal_base_fare_d28"])
    block = {(s["origin"], s["destination"]): s["block_minutes"] for s in summaries}
    routes = sorted(fares)
    corr_fare_distance = float(np.corrcoef([block[r] for r in routes], [np.median(fares[r]) for r in routes])[0, 1])
    return {
        "mean_final_load_factor": round(float(loads.mean()), 4),
        "median_final_load_factor": round(float(np.median(loads)), 4),
        "share_sold_out_at_departure": round(float(sold_out.mean()), 4),
        "share_sold_out_more_than_30_days_out": round(sum(d > 30 for d in first_sold_out) / len(summaries), 4),
        "share_final_load_below_50pct": round(float((loads < .5).mean()), 4),
        "route_fare_vs_block_time_correlation": round(corr_fare_distance, 4),
        "directed_routes": len(routes),
        "aircraft_mix": dict(Counter(s["aircraft_type"] for s in summaries)),
        "seat_configs": dict(sorted(Counter(s["capacity"] for s in summaries).items())),
    }


TARGETS = {
    "mean_final_load_factor": (.78, .90),
    # With the frozen NHPP mechanics (gamma latent scale, surge/pulse shocks) a
    # ~82% mean load factor implies roughly a quarter of departures selling out.
    "share_sold_out_at_departure": (.10, .30),
    "share_sold_out_more_than_30_days_out": (0, .03),
    "route_fare_vs_block_time_correlation": (.6, 1.0),
}


def _gzip_writer(path):
    raw = path.open("wb")
    return raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0)


def generate(seed=SEED, output=OUTPUT):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    flights = schedule(seed)
    summaries, by_flight, truth_rows = [], {}, 0
    files = {}
    for name, fields in (("snapshots.csv.gz", FIELDS), ("truth.csv.gz", TRUTH_FIELDS)):
        raw, gz = _gzip_writer(output / name)
        files[name] = (raw, gz, csv.DictWriter(_Text(gz), fieldnames=fields, extrasaction="ignore", lineterminator="\n"))
        files[name][2].writeheader()
    for flight in flights:
        result = simulate(flight, seed)
        files["snapshots.csv.gz"][2].writerows(result["snapshots"])
        files["truth.csv.gz"][2].writerows(result["truth"])
        truth_rows += len(result["truth"])
        summaries.append(result["summary"])
        by_flight[flight["flight_id"]] = result["snapshots"]
    for raw, gz, _ in files.values():
        gz.close()
        raw.close()
    (output / "flights.json").write_text(json.dumps(summaries, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    facts = stylized_facts(summaries, by_flight)
    failed = {k: facts[k] for k, (low, high) in TARGETS.items() if not low <= facts[k] <= high}
    if failed:
        raise ValueError(f"stylized-fact targets not met: {failed}")
    rows = sum(len(v) for v in by_flight.values())
    manifest = {
        "schema_version": "1.0", "generator_version": VERSION, "dataset": "hkx_generated",
        "python_version": platform.python_version(), "numpy_version": np.__version__,
        "seed": seed, "rows": rows, "flights": len(summaries), "truth_rows": truth_rows,
        "source_kind": "assumed_demo", "currency": "HKD", "timezone": "Asia/Hong_Kong",
        "departure_dates": [d for d, _ in DATES], "seasons": dict(DATES),
        "destinations": len(DESTINATIONS), "directed_routes": facts["directed_routes"],
        "schedule_profile": {k: v for k, v in json.loads(PROFILE.read_text(encoding="utf-8")).items() if k != "entries"},
        "schedule_profile_sha256": hashlib.sha256(PROFILE.read_bytes()).hexdigest(),
        "summer_season": list(SUMMER_SEASON),
        "fleet": [{"type": n, "seats": s, "aircraft_assumed": c} for n, s, c in FLEET] + [{"type": "A321neo", "seats": 239, "aircraft_assumed": 1, "note": "one A321neo; share of A321neo rotations"}],
        "departure_charges_hkd": DEPARTURE_CHARGES,
        "stylized_facts": facts, "targets": {k: list(v) for k, v in TARGETS.items()},
        "interval_definition": "Counts and interval_days describe the interval completed into this snapshot; D180 has exposure 0. D0 is departure minus 2h, not boarding.",
        "price_definition": "Quote applies AFTER the snapshot. Missing when sold out or at cutoff; missing is not a zero fare.",
        "time_definition": "All timestamps are Hong Kong time (+08:00), including departures from outports.",
        "capacity_definition": "Published seat configuration of the assigned aircraft type, treated as fixed sellable capacity.",
        "sources": {
            "destinations": "Wikipedia HK Express article, destinations table (March 2026 snapshot); Wuxi from HK Express media release (route launched 17 July 2026).",
            "fleet": "HK Express Our Fleet page (A320 180, A320neo 188, A321 230 seats); HK Express seat page (A321neo 236 and one 239-seat aircraft); Wikipedia fleet table as of December 2025.",
            "schedule": "OAG Flight Info, UO departures from HKG, 16-22 Nov 2026 (410 departures), reduced to simulation/hkx_schedule_profile.json; raw responses are not published.",
        },
        "assumptions": [
            "Every sampled date reuses the OAG sample week's departures for its weekday; frequencies may differ by season in reality.",
            "Six seasonal destinations absent from the sample week (FSZ, ISG, SHI, CJJ, CXR, KWE) operate only in IATA summer 2027 with assumed frequencies, times and aircraft; their block time = 35 min + great-circle distance at 760 km/h.",
            "Return legs use outbound flight number + 1 and depart after the outbound elapsed time plus a 55-minute turn; return elapsed time equals outbound.",
            "Fares scale with block time and market.",
            "Passenger charges are assumed per departure country; demand, seasonality, weekday effects and cancellations are synthetic.",
            "Demand follows the exogenous-fare NHPP of simulation/generate.py; fares never respond to bookings.",
            "Hidden scenario and truth.csv.gz must not be predictor features.",
        ],
        "files": {name: hashlib.sha256((output / name).read_bytes()).hexdigest()
                  for name in ("snapshots.csv.gz", "truth.csv.gz", "flights.json")},
    }
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


class _Text:
    """Minimal text adapter so csv can write deterministic gzip bytes (mtime=0)."""
    def __init__(self, binary):
        self.binary = binary

    def write(self, text):
        return self.binary.write(text.encode("utf-8"))


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--output", default=str(OUTPUT))
    args = parser.parse_args()
    manifest = generate(args.seed, args.output)
    print(json.dumps({k: manifest[k] for k in ("rows", "flights", "directed_routes", "stylized_facts")}, indent=2))


if __name__ == "__main__":
    main()

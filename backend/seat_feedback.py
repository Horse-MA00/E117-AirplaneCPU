"""Run-local NHPP feedback calibration; the frozen NHPP and its files stay intact.

Only completed simulator worlds may supply evaluation labels. Background request
events include denied demand; foreground normal purchases are a lower bound on
normal demand (unavailable options do not reveal purchase intent). No member
purchase or LLM explanation is treated as a normal-demand label.
"""
from __future__ import annotations

import copy
import math
import statistics

VERSION = "nhpp-completed-market-feedback-v1"
DAYS = (28, 14, 7)


def initial_profile():
    return {"version": VERSION, "generation": 0, "horizons": {
        str(d): {"rate_scale": 1.0, "extra_protection": 0, "samples": 0} for d in DAYS}}


def validate_profile(profile):
    if not isinstance(profile, dict) or profile.get("version") != VERSION:
        raise ValueError("Unknown seat calibration version")
    generation = profile.get("generation")
    if isinstance(generation, bool) or not isinstance(generation, int) or generation < 0:
        raise ValueError("Invalid seat calibration generation")
    for d in DAYS:
        row = profile.get("horizons", {}).get(str(d), {})
        for key, low, high in (("rate_scale", .5, 2), ("extra_protection", 0, 400), ("samples", 0, 1000000)):
            value = row.get(key)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
                raise ValueError(f"Invalid seat calibration {key}")
    return profile


def apply_profile(prediction, profile, day):
    """Adjust the feedback layer, retaining the base model and all fail-closed gates."""
    validate_profile(profile)
    adjusted = dict(prediction)
    # Between-round refreshes use the next longer calibrated horizon, the same
    # convention as the NHPP protection guard.
    horizon = next((d for d in sorted(DAYS) if d >= day), max(DAYS))
    settings = profile["horizons"][str(horizon)]
    mean = float(prediction["expected_remaining_demand"])
    protection = float(prediction["protection_p90"])
    new_mean = mean * settings["rate_scale"]
    # Never shrink the frozen safety reserve to manufacture more membership seats.
    new_protection = protection + math.ceil(settings["extra_protection"])
    adjusted.update(base_expected_remaining_demand=mean, base_protection_p90=protection,
                    expected_remaining_demand=round(new_mean, 3), protection_p90=new_protection,
                    seat_feedback_version=VERSION, seat_feedback_generation=profile["generation"])
    available = prediction["available_seats"]
    adjusted["releasable_seats"] = min(prediction["releasable_seats"], max(0, math.floor(available-new_protection)))
    # A change in unconstrained demand is not a linear change in empty seats:
    # capacity truncation and cancellations need full path resimulation. Keep
    # the base Monte Carlo vacancy forecast/curve rather than invent that result.
    adjusted["empty_forecast_source"] = "frozen_base_nhpp"
    return adjusted


def collect_samples(state):
    """Evaluator-only: call after completion, never while constructing observations."""
    if state.get("pending") is not None or state["cursor"] != len(state["events"]):
        raise ValueError("Seat feedback requires a completed market")
    rows = []
    for fid, flight in state["flights"].items():
        for q in flight["quota_history"]:
            bg = sum(e["kind"] == "background" and e.get("flight_id") == fid and e["time"] > q["day"]
                     for e in state["events"])
            normal = sum(b["normal_seats"] for b in state["bookings"].values()
                         if b["flight_id"] == fid and b["customer_id"] is not None and b["booked_day"] > q["day"])
            rows.append({"sample_id": f'{state["seed"]}:{fid}:{q["days_to_departure"]}',
                         "seed": state["seed"], "flight_id": fid, "days_to_departure": q["days_to_departure"],
                         "actual_normal_requests": bg+normal, "background_requests": bg,
                         "accepted_foreground_normal_seats": normal,
                         "base_expected": q.get("base_expected_remaining_demand", q["expected_remaining_demand"]),
                         "expected": q["expected_remaining_demand"],
                         "base_protection": q.get("base_protection_p90", q["protection_p90"]),
                         # Compare like-for-like forecast reserves. A quality gate
                         # can independently protect all physical seats; it is not
                         # an improvement learned by this feedback layer.
                         "protection": q["protection_p90"]})
    return rows


def update_profile(previous, samples):
    """Shrink each horizon to its base forecast; repeated worlds aren't new samples."""
    validate_profile(previous)
    unique = {r["sample_id"]: r for r in samples}
    result = copy.deepcopy(previous)
    result["generation"] += 1
    for d in DAYS:
        rows = [r for r in unique.values() if r["days_to_departure"] == d]
        if not rows:
            continue
        actual = sum(r["actual_normal_requests"] for r in rows)
        predicted = sum(r["base_expected"] for r in rows)
        scale = max(.5, min(2., (actual+100.)/(predicted+100.)))
        residuals = sorted(max(0., r["actual_normal_requests"]-r["base_protection"]) for r in rows)
        p90 = residuals[min(len(rows)-1, math.ceil(.9*len(rows))-1)]
        extra = min(400, math.ceil(p90*len(rows)/(len(rows)+20)))
        result["horizons"][str(d)] = {"rate_scale": round(scale, 6), "extra_protection": extra, "samples": len(rows)}
    return result


def diagnostics(samples):
    result = {"version": VERSION, "sample_count": len(samples), "horizons": {},
              "label": "Simulated background requests plus accepted foreground normal seats; foreground unmet intent is unobserved."}
    for d in DAYS:
        rows = [r for r in samples if r["days_to_departure"] == d]
        if rows:
            result["horizons"][str(d)] = {
                "samples": len(rows),
                "base_mae": round(statistics.mean(abs(r["actual_normal_requests"]-r["base_expected"]) for r in rows), 3),
                "adjusted_mae": round(statistics.mean(abs(r["actual_normal_requests"]-r["expected"]) for r in rows), 3),
                "base_coverage": statistics.mean(r["actual_normal_requests"] <= r["base_protection"] for r in rows),
                "adjusted_coverage": statistics.mean(r["actual_normal_requests"] <= r["protection"] for r in rows)}
    return result

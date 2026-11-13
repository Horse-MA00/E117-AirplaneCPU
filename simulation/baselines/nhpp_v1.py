"""Regularized exponential NHPP fitted only to observable, as-of gross counts.

The beta grid and Gamma rate prior are explicit engineering assumptions. Counts
that hit available capacity are conservatively omitted, not treated as demand.
Prediction intervals include rate/beta uncertainty but not every model error.
"""
from __future__ import annotations

import math
import json
from pathlib import Path
import numpy as np


def _number(row, key, fallback=0.0):
    value = row.get(key, fallback)
    if value is None:
        return float(fallback)
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{key} must be finite")
    return result


def _integral(beta, start, end):
    """Stable integral of exp(beta*t), including beta=0."""
    b = np.asarray(beta, dtype=float)
    safe = np.where(np.abs(b) < 1e-9, 1.0, b)
    return np.where(np.abs(b) < 1e-9, end-start,
                    np.exp(b*start)*np.expm1(b*(end-start))/safe)


def forecast(rows: list[dict], days_to_departure: int = 28, seed: int = 117,
             protection_allowance: float | None = None) -> dict:
    if isinstance(days_to_departure, bool) or not 0 <= days_to_departure <= 28:
        raise ValueError("days_to_departure must be between 0 and 28")
    day = int(days_to_departure)
    if day != days_to_departure or not rows:
        raise ValueError("an integer day and at least one historical snapshot are required")
    history = sorted((r for r in rows if _number(r, "days_to_departure") >= day),
                     key=lambda r: -_number(r, "days_to_departure"))
    if not history or int(_number(history[-1], "days_to_departure")) != day:
        raise ValueError("no snapshot exists at the requested decision day")
    if len({str(r.get("flight_id", "")) for r in history}) > 1:
        raise ValueError("forecast requires one flight")
    if len({int(_number(r, "days_to_departure")) for r in history}) != len(history):
        raise ValueError("duplicate snapshot days")
    current = history[-1]
    capacity = int(_number(current, "capacity", current.get("sellable_capacity", 180)))
    booked = int(_number(current, "booked_seats", current.get("net_booked_seats", 0)))
    if capacity < 1 or not 0 <= booked <= capacity:
        raise ValueError("invalid capacity or booked seats")
    available = capacity-booked
    intervals, censored = [], 0
    for previous, row in zip(history[:-1], history[1:]):
        d = _number(row, "days_to_departure")
        if d > day+35:
            continue
        previous_day = _number(previous, "days_to_departure")
        if previous_day-d != 1:
            continue  # Daily counts cannot represent missing intervening rows.
        duration = _number(row, "interval_days", 1 if d else 22/24)
        if not 0 < duration <= 1:
            raise ValueError("interval_days must be positive and at most one day")
        count = _number(row, "gross_bookings", row.get("gross_new_bookings_1d", 0))
        cancels = _number(row, "cancellations", row.get("cancellations_1d", 0))
        if count < 0 or count != int(count) or cancels < 0 or cancels != int(cancels):
            raise ValueError("gross counts and cancellations must be nonnegative integers")
        prev_booked = _number(previous, "booked_seats", previous.get("net_booked_seats", 0))
        prev_available = capacity-prev_booked
        if prev_available <= 0 or count >= prev_available:
            censored += 1
            continue
        end = day-d
        # At D0 the end is the two-hour sales cutoff, not departure itself.
        intervals.append({"end": end, "start": end-duration, "count": int(count),
                          "cancellations": int(cancels), "duration": duration,
                          "booked_exposure": max(0, prev_booked)*duration})
    grid = np.linspace(-0.12, 0.12, 241)
    shape_prior, exposure_prior = 1.0, 2.0
    count_sum = sum(x["count"] for x in intervals)
    exposures = np.full(grid.shape, exposure_prior)
    log_likelihood = -0.5*((grid-0.015)/0.04)**2
    for item in intervals:
        g = _integral(grid, item["start"], item["end"])
        exposures += g
        log_likelihood += item["count"]*np.log(g)
    log_likelihood -= (shape_prior+count_sum)*np.log(exposures)
    weights = np.exp(log_likelihood-log_likelihood.max())
    weights /= weights.sum()
    rng = np.random.default_rng(seed)
    indices = rng.choice(len(grid), size=800, p=weights)
    sampled_beta = grid[indices]
    sampled_rate = rng.gamma(shape_prior+count_sum, 1/exposures[indices])
    beta = float(np.dot(weights, grid))
    rate = float(np.dot(weights, (shape_prior+count_sum)/exposures))
    cancellation_rate = (sum(x["cancellations"] for x in intervals)+0.1)/(sum(x["booked_exposure"] for x in intervals)+500)
    cancellation_rate = min(0.03, cancellation_rate)
    total_gross = np.zeros(800, dtype=int)
    seats = np.full(800, booked, dtype=int)
    curve = [{"day": day, "expected_booked": float(booked), "p10": float(booked), "p90": float(booked)}]
    for elapsed in range(day):
        duration = 22/24 if elapsed == day-1 else 1.0
        means = sampled_rate*_integral(sampled_beta, elapsed, elapsed+duration)
        arrivals = rng.poisson(np.minimum(means, 1e6))
        cancelled = rng.binomial(seats, 1-math.exp(-cancellation_rate*duration))
        # Cancellations at interval end reopen sales in the next interval.
        seats += np.minimum(arrivals, capacity-seats)-cancelled
        total_gross += arrivals
        curve.append({"day": day-elapsed-1, "expected_booked": round(float(seats.mean()), 3),
                      "p10": float(np.quantile(seats, .1)), "p90": float(np.quantile(seats, .9))})
    raw_protection = int(np.quantile(total_gross, .9, method="higher")) if day else 0
    calibrated = False
    if protection_allowance is None:
        calibration_path = Path(__file__).resolve().parents[1]/"simulation/generated/calibration.json"
        if calibration_path.is_file():
            with calibration_path.open(encoding="utf-8") as handle:
                calibration = json.load(handle)
            protection_allowance = float(calibration["allowance"])
            calibrated = True
        else:
            protection_allowance = 0.
    if not math.isfinite(protection_allowance) or protection_allowance < 0:
        raise ValueError("protection_allowance must be finite and nonnegative")
    allowance = int(math.ceil(protection_allowance)) if day else 0
    protection = raw_protection+allowance
    censor_fraction = censored/max(1, len(intervals)+censored)
    release = max(0, available-protection)
    if censor_fraction > .25 or len(intervals) < 7 or not day:
        release = 0
    recent = sum(x["count"] for x in intervals[-3:])/max(1, len(intervals[-3:]))
    older = sum(x["count"] for x in intervals[-14:-3])/max(1, len(intervals[-14:-3]))
    jump = recent > max(3, 2.5*older)
    if jump:
        release = 0  # A possible transient/group shock requires review, not extrapolation confidence.
    return {
        "model": "regularized_exponential_nhpp", "flight_id": current.get("flight_id", ""),
        "days_to_departure": day, "capacity": capacity, "booked_seats": booked,
        "available_seats": available, "beta": round(beta, 6), "rate_now": round(rate, 4),
        "expected_remaining_demand": round(float(total_gross.mean()), 3),
        "expected_empty_seats": round(float((capacity-seats).mean()), 3),
        "expected_empty_rate": round(float((capacity-seats).mean()/capacity), 5),
        "raw_protection_p90": raw_protection, "protection_allowance": allowance,
        "protection_p90": protection, "releasable_seats": release,
        "intervals": len(intervals), "forecast_curve": curve,
        "diagnostics": {"censored_intervals": censored, "censored_fraction": round(censor_fraction, 3),
                        "possible_jump": bool(jump), "observed_gross_count": count_sum,
                        "daily_cancellation_rate": round(cancellation_rate, 6),
                        "beta_prior_mean": .015, "beta_prior_sd": .04,
                        "beta_grid_bounds": [-.12, .12], "predictive_draws": 800,
                        "beta_boundary_mass": round(float(weights[:5].sum()+weights[-5:].sum()), 5),
                        "calibration_loaded": calibrated, "calibration_horizon_days": 28},
        "assumptions": ["Synthetic-market forecast, not calibrated to HK Express bookings.",
                        "Next 28 days extrapolate local exponential intensity; unknown shocks and price changes may break it.",
                        "Beta bounds and Gamma prior are engineering assumptions, not aviation industry limits.",
                        "Protection adds a fixed synthetic calibration allowance; raw P90 and forecast bands remain separately reported. The allowance is calibrated at D28 only.",
                        "Capacity-hit intervals are omitted; extensive censoring or a detected surge disables release.",
                        "P10/P90 include assumed rate and beta uncertainty, not a guarantee of airline protection."]}

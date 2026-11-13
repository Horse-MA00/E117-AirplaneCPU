"""Daily normal-fare sales simulator; no real booking/fare calibration.

Snapshots contain information available at the snapshot time. Hidden demand,
scenario parameters, and final outcomes are kept in separate result objects.
An event belongs to the interval AFTER its start snapshot and is observed at
the next snapshot. Sold-out flights can receive cancellations and reopen.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np


def _number(value, name, minimum=None, maximum=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    if minimum is not None and value < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    if maximum is not None and value > maximum:
        raise ValueError(f"{name} must be <= {maximum}")


def validate_config(config):
    h = config["horizon_days"]
    if isinstance(h, bool) or not isinstance(h, int) or h < 28:
        raise ValueError("horizon_days must be an integer >= 28")
    for key in ("reference_demand_per_seat", "booking_shape_floor", "price_elasticity"):
        _number(config[key], key, 0)
    for key in ("gamma_shape", "booking_shape_decay_days"):
        _number(config[key], key, 1e-9)
    _number(config["daily_cancellation_rate"], "daily_cancellation_rate", 0, 1)
    _number(config["cutoff_hours_before_departure"], "cutoff_hours_before_departure", 0, 23.99)
    p = config["price"]
    for key in ("reference_base_fare", "rounding_increment"):
        _number(p[key], key, 1e-9)
    for key in ("fuel_surcharge", "taxes_and_mandatory_fees", "minimum_base_fare", "maximum_base_fare",
                "last28_markup", "last7_markup", "daily_noise_sd", "slow_sales_gap"):
        _number(p[key], key, 0)
    if p["maximum_base_fare"] < p["minimum_base_fare"]:
        raise ValueError("maximum_base_fare must be >= minimum_base_fare")
    _number(p["noise_persistence"], "noise_persistence", 0, 0.999999)
    _number(p["slow_sales_discount"], "slow_sales_discount", 0, 1)
    _number(p["slow_sales_check_days"], "slow_sales_check_days", 0, h)
    tiers = p["occupancy_tiers"]
    if not tiers or tiers[0][0] != 0:
        raise ValueError("occupancy_tiers must start at zero")
    previous = -1
    for threshold, multiplier in tiers:
        _number(threshold, "tier threshold", 0, 1)
        _number(multiplier, "tier multiplier", 1e-9)
        if threshold <= previous:
            raise ValueError("occupancy thresholds must be strictly increasing")
        previous = threshold
    for promo in p["promotions"]:
        if not 1 <= promo["end_day"] <= promo["start_day"] <= h:
            raise ValueError("promotions require 1 <= end_day <= start_day <= horizon_days")
        _number(promo["discount"], "promotion discount", 0, 0.99)
    for scenario in config["scenarios"]:
        if not scenario["name"]:
            raise ValueError("scenario name must not be empty")
        _number(scenario["demand_multiplier"], "demand_multiplier", 0)
    if len({s["name"] for s in config["scenarios"]}) != len(config["scenarios"]):
        raise ValueError("scenario names must be unique")


def load_config(path):
    config = json.loads(Path(path).read_text(encoding="utf-8"))
    validate_config(config)
    return config


def validate_flight(flight):
    capacity = flight["capacity"]
    if isinstance(capacity, bool) or not isinstance(capacity, int) or capacity <= 0:
        raise ValueError("capacity must be a positive integer")
    for key in ("flight_id", "origin", "destination", "source_kind"):
        if not isinstance(flight[key], str) or not flight[key].strip():
            raise ValueError(f"{key} must be a nonempty string")
    departure = datetime.fromisoformat(flight["departure_at"].replace("Z", "+00:00"))
    if departure.utcoffset() is None:
        raise ValueError("departure_at must include a timezone offset")
    return departure


def _fare(day, occupancy, expected_pace, noise, config):
    p = config["price"]
    tier = next(m for threshold, m in reversed(p["occupancy_tiers"]) if occupancy >= threshold)
    markup = (p["last28_markup"] if day <= 28 else 0) + (p["last7_markup"] if day <= 7 else 0)
    slow = day <= p["slow_sales_check_days"] and occupancy < expected_pace - p["slow_sales_gap"]
    promotion = max([0.0] + [x["discount"] for x in p["promotions"] if x["end_day"] <= day <= x["start_day"]])
    price = p["reference_base_fare"] * (tier + markup)
    price *= (1 - p["slow_sales_discount"] if slow else 1) * (1 - promotion) * math.exp(noise)
    rounded = round(price / p["rounding_increment"]) * p["rounding_increment"]
    return int(min(p["maximum_base_fare"], max(p["minimum_base_fare"], rounded))), slow, promotion


def simulate_flight(flight: dict, scenario: dict, config: dict, seed: int) -> dict:
    """Simulate 181 observable states and 180 subsequent sales intervals.

    D180 starts empty; D0 is the exact sales cutoff, not boarding. Fare exposed
    at a snapshot governs the following interval. To keep this daily model
    unambiguous, cancellations at the end of an interval reopen sales NEXT day.
    """
    validate_config(config)
    departure = validate_flight(flight)
    _number(scenario["demand_multiplier"], "demand_multiplier", 0)
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise ValueError("seed must be a nonnegative integer")
    horizon, capacity = config["horizon_days"], flight["capacity"]
    cutoff = departure - timedelta(hours=config["cutoff_hours_before_departure"])
    latent_rng, demand_rng, cancel_rng, price_rng = [np.random.default_rng(s) for s in np.random.SeedSequence(seed).spawn(4)]
    theta = float(latent_rng.gamma(config["gamma_shape"], 1 / config["gamma_shape"]))
    days = np.arange(horizon, 0, -1)
    durations = np.ones(horizon)
    durations[-1] = 1 - config["cutoff_hours_before_departure"] / 24
    raw = (config["booking_shape_floor"] + np.exp(-days / config["booking_shape_decay_days"])) * durations
    weights = raw / raw.sum()
    p = config["price"]
    mandatory = p["fuel_surcharge"] + p["taxes_and_mandatory_fees"]
    reference_total = p["reference_base_fare"] + mandatory
    snapshots, events = [], []
    booked, noise = 0, 0.0
    for index, day in enumerate(range(horizon, -1, -1)):
        observed = departure - timedelta(days=day) if day else cutoff
        noise = p["noise_persistence"] * noise + float(price_rng.normal(0, p["daily_noise_sd"]))
        expected_pace = min(1.0, float(weights[:index].sum()))
        policy_price, slow, promotion = _fare(day, booked / capacity, expected_pace, noise, config)
        is_available = day > 0 and booked < capacity
        recent = events[-1] if events else None
        snapshot = {
            "flight_id": flight["flight_id"], "observed_at": observed.isoformat(), "available_at": observed.isoformat(),
            "departure_at": departure.isoformat(), "sales_cutoff_at": cutoff.isoformat(),
            "days_to_departure": day, "days_to_cutoff": max(0.0, (cutoff - observed).total_seconds() / 86400),
            "origin": flight["origin"], "destination": flight["destination"],
            "sellable_capacity": capacity, "net_booked_seats": booked, "available_to_sell": capacity - booked,
            "occupancy_rate": booked / capacity,
            "gross_new_bookings_1d": recent["accepted_bookings"] if recent else 0,
            "cancellations_1d": recent["cancellations"] if recent else 0,
            "net_pickup_1d": recent["accepted_bookings"] - recent["cancellations"] if recent else 0,
            "gross_new_bookings_7d": sum(e["accepted_bookings"] for e in events[-7:]),
            "cancellations_7d": sum(e["cancellations"] for e in events[-7:]),
            "net_pickup_7d": sum(e["accepted_bookings"] - e["cancellations"] for e in events[-7:]),
            "currency": p["currency"], "base_fare": policy_price if is_available else None,
            "fuel_surcharge": p["fuel_surcharge"] if is_available else None,
            "taxes_and_mandatory_fees": p["taxes_and_mandatory_fees"] if is_available else None,
            "total_payable": policy_price + mandatory if is_available else None,
            "is_available": is_available, "quote_status": "closed" if day == 0 else ("open" if is_available else "sold_out"),
            "fare_kind": "regular_quote", "journey_basis": "one_way", "passengers": 1,
            "promotion_discount": promotion, "slow_sales_discount_active": slow,
            "flight_source_kind": flight["source_kind"], "booking_source_kind": "simulated", "fare_source_kind": "simulated",
        }
        snapshots.append(snapshot)
        if day == 0:
            break
        # At sellout this is counterfactual willingness at the policy price,
        # not a publicly available quote. Kept only in simulation truth.
        mean_requests = capacity * config["reference_demand_per_seat"] * scenario["demand_multiplier"] * theta * float(weights[index])
        mean_requests *= ((policy_price + mandatory) / reference_total) ** (-config["price_elasticity"])
        requests = int(demand_rng.poisson(mean_requests))
        accepted = min(requests, capacity - booked)
        cancel_probability = 1 - (1 - config["daily_cancellation_rate"]) ** float(durations[index])
        cancellations = int(cancel_rng.binomial(booked, cancel_probability))
        new_booked = booked + accepted - cancellations
        next_time = departure - timedelta(days=day-1) if day > 1 else cutoff
        events.append({
            "flight_id": flight["flight_id"], "interval_start_day": day,
            "interval_start_at": observed.isoformat(), "interval_end_at": next_time.isoformat(),
            "interval_days": float(durations[index]), "booked_before": booked, "booked_after": new_booked,
            "accepted_bookings": accepted, "cancellations": cancellations,
            "demand_requests": requests, "denied_demand": requests - accepted,
            "expected_requests": mean_requests, "policy_base_fare": policy_price,
        })
        booked = new_booked
    outcome = {
        "flight_id": flight["flight_id"], "sales_cutoff_at": cutoff.isoformat(), "label_available_at": cutoff.isoformat(),
        "final_sellable_capacity": capacity, "final_net_booked_seats": booked,
        "final_unsold": capacity - booked, "final_occupancy_rate": booked / capacity,
        "total_accepted_bookings": sum(e["accepted_bookings"] for e in events),
        "total_cancellations": sum(e["cancellations"] for e in events), "source_kind": "simulated",
    }
    truth = {
        "flight_id": flight["flight_id"], "scenario": scenario["name"], "seed": seed, "latent_theta": theta,
        "demand_multiplier": scenario["demand_multiplier"], "price_elasticity": config["price_elasticity"],
        "total_demand_requests": sum(e["demand_requests"] for e in events),
        "total_denied_demand": sum(e["denied_demand"] for e in events),
    }
    return {"snapshots": snapshots, "events": events, "truth": truth, "outcome": outcome}

"""Reproducible full-membership-term, finite-supply pricing experiment.

This is an explicit synthetic market, not estimated HK Express price elasticity.
The paired baseline preserves identity, normal purchase intent and event times.
"""
from __future__ import annotations

import math
from itertools import product
import numpy as np


def _bounded(value, name, low, high, integer=False):
    if isinstance(value, bool):
        raise ValueError(f"{name} must be numeric")
    number = float(value)
    if not math.isfinite(number) or not low <= number <= high or (integer and int(number) != number):
        raise ValueError(f"{name} must be in [{low}, {high}]")
    return int(number) if integer else number


def _config(config):
    src = config or {}
    specs = {"seed": (117, 0, 2**31-1, True), "membership_days": (365, 30, 730, True),
             "customers": (300, 20, 1200, True), "flights": (24, 6, 100, True),
             "normal_base_fare": (500, 100, 3000, False), "mandatory_fees": (250, 0, 1000, False),
             "incremental_cost": (90, 0, 1000, False), "ancillary_margin": (45, 0, 500, False),
             "member_service_cost": (30, 0, 500, False), "program_cost": (1500, 0, 100000, False),
             "interest_multiplier": (1, .1, 3, False), "min_service_rate": (.6, 0, 1, False),
             "max_unused_member_rate": (.75, 0, 1, False), "replicates": (2, 1, 8, True)}
    return {key: _bounded(src.get(key, default), key, low, high, integer)
            for key, (default, low, high, integer) in specs.items()}


def _arrival_days(prediction, uniforms):
    """Draw request times from uncapped demand, not capacity-capped bookings."""
    day = max(1, int(prediction.get("days_to_departure", 28)))
    curve = prediction.get("demand_curve")
    if curve:
        points = sorted(curve, key=lambda row: -row["day"])
        remaining = np.array([row["expected_remaining_demand"] for row in points])
        increments = np.maximum(0, remaining[:-1]-remaining[1:])
        if len(increments) and increments.sum()>0:
            cdf = np.cumsum(increments)/increments.sum()
            positions = np.minimum(np.searchsorted(cdf, uniforms, side="right"), len(increments)-1)
            return np.array([row["day"] for row in points[:-1]], dtype=int)[positions]
    horizon = max(1/24, day-2/24)
    beta = float(prediction.get("beta", 0))
    elapsed = np.log1p(uniforms*math.expm1(beta*horizon))/beta if abs(beta)>1e-8 else uniforms*horizon
    return np.clip(np.ceil(day-elapsed), 1, day).astype(int)


def _world(prediction, cfg, seed, demand_multiplier=1.0, group_size=1):
    rng = np.random.default_rng(seed)
    n, flight_count = cfg["customers"], cfg["flights"]
    # Behaviour dimensions represent broad leisure, visiting friends/relatives,
    # business, student and family travel needs without claiming population shares.
    annual_frequency = rng.choice([1., 2., 3., 5., 8.], n, p=[.25, .3, .25, .15, .05])
    independent_trip_frequency = annual_frequency*cfg["membership_days"]/365
    flexibility = rng.beta(2.2, 2, n)
    min_notice = rng.choice([1, 3, 7, 14, 21], n, p=[.1, .15, .3, .3, .15])
    join_uniform = rng.random(n)
    friction = rng.uniform(40, 180, n)
    available = int(prediction.get("available_seats", 60))
    mu = max(0, float(prediction.get("expected_remaining_demand", 35)))*demand_multiplier
    # Ex-ante expected opportunities use the same frequency weights that assign
    # normal requests, rather than knowing each customer's future realized trips.
    expected_trips = (flight_count*min(mu, n)*annual_frequency/annual_frequency.sum()
                      + .45*independent_trip_frequency)
    departure_days = [int(29+(cfg["membership_days"]-29)*(flight+.5)/flight_count)
                      for flight in range(flight_count)]
    # The scenario assigns one itinerary opportunity per person per calendar
    # day, even if the synthetic catalogue contains several flights that day.
    expected_trips = np.minimum(expected_trips, len(set(departure_days)))
    decision_day = max(1, int(prediction.get("days_to_departure", 28)))
    # Potential normal requests include customers denied by capacity; never clip
    # the forecast mean itself to physical capacity when interpreting demand.
    events = []
    assigned_customer_days = set()
    for flight in range(flight_count):
        normal_count = min(n, int(rng.poisson(min(mu, n*2)/group_size))*group_size)
        normal_ids = rng.choice(n, normal_count, replace=False, p=annual_frequency/annual_frequency.sum())
        incremental_count = min(n-normal_count, int(rng.poisson(n*float(independent_trip_frequency.mean())/flight_count*.45)))
        incremental_pool = np.setdiff1d(np.arange(n), normal_ids, assume_unique=True)
        pool_weights = annual_frequency[incremental_pool]
        incremental_ids = (rng.choice(incremental_pool, incremental_count, replace=False,
                                     p=pool_weights/pool_weights.sum()) if incremental_count else np.array([], dtype=int))
        ids = np.concatenate([normal_ids, incremental_ids])
        normal = np.concatenate([np.ones(normal_count, bool), np.zeros(incremental_count, bool)])
        uniforms = rng.random(len(ids))
        if group_size > 1 and normal_count:
            uniforms[:normal_count] = np.repeat(rng.random(math.ceil(normal_count/group_size)), group_size)[:normal_count]
        days = _arrival_days(prediction, uniforms)
        willingness = rng.normal(cfg["mandatory_fees"]+85, 70, len(ids))
        order = np.argsort(-days, kind="stable")
        unique = []
        for position in order:
            identity = (int(ids[position]), departure_days[flight])
            if identity not in assigned_customer_days:
                assigned_customer_days.add(identity)
                unique.append(position)
        order = np.asarray(unique, dtype=int)
        events.append({"ids": ids[order], "normal": normal[order], "days": days[order],
                       "willingness": willingness[order], "available": available,
                       "departure_period_day": departure_days[flight]})
    baseline_normal = sum(min(e["available"], int(e["normal"].sum())) for e in events)
    baseline_profit = baseline_normal*(cfg["normal_base_fare"]+cfg["ancillary_margin"]-cfg["incremental_cost"])
    return {"events": events, "expected_trips": expected_trips, "flexibility": flexibility,
            "min_notice": min_notice, "join_uniform": join_uniform, "friction": friction,
            "baseline_normal": baseline_normal, "baseline_profit": baseline_profit,
            "forecast": prediction}


def _remaining_protection(prediction, opening):
    """Preserve regime-path tail risk; beta alone cannot describe the v2 mixture."""
    if "protection_curve" in prediction:
        for point in prediction["protection_curve"]:
            if point["day"] == opening:
                return max(0, math.ceil(point["protection_seats"]))
        # An incomplete curve must not silently reduce the protection reserve.
        return max(0, math.ceil(prediction.get("protection_p90", 0)))
    beta = float(prediction.get("beta", 0))
    decision_day = max(1, int(prediction.get("days_to_departure", 28)))
    horizon = decision_day-2/24
    remaining = min(opening, decision_day)-2/24
    ratio = (math.exp(beta*(horizon-remaining))*math.expm1(beta*remaining)/math.expm1(beta*horizon)) if abs(beta)>1e-8 else remaining/horizon
    raw = float(prediction.get("raw_protection_p90", prediction.get("protection_p90", 0)))
    return max(0, math.ceil(raw*max(0, ratio)+float(prediction.get("protection_allowance", 0))))


def _run(world, candidate, cfg, include_events=False):
    p, v, opening, fraction = candidate
    pred = world["forecast"]
    n = cfg["customers"]
    releasable = max(0, int(pred.get("releasable_seats", 0)))
    # Expected service is a public conservative scenario, not the user's future
    # realized seat assignment. It penalizes selling too many passes for supply.
    expected_requests = max(1., n*float(world["expected_trips"].mean())*.5)
    supply_probability = min(.7, cfg["flights"]*releasable*fraction/expected_requests)
    notice_match = np.minimum(1, opening/np.maximum(1, world["min_notice"]))
    value = world["expected_trips"]*world["flexibility"]*notice_match*supply_probability*max(0, cfg["normal_base_fare"]-p)*cfg["interest_multiplier"]
    probability = 1/(1+np.exp(np.clip(-(value-v-world["friction"])/100, -50, 50)))
    members = world["join_uniform"] < probability
    # Do not charge memberships if the model permits no member supply at all.
    if not releasable:
        members[:] = False
    used = np.zeros(n, bool)
    member_bookings = normal_bookings = member_requests = switched = 0
    flights, logs = [], []
    for flight_index, e in enumerate(world["events"]):
        seats, quota, opened = e["available"], 0, False
        sold_member = sold_normal = 0
        for customer, was_normal, d, willingness in zip(e["ids"], e["normal"], e["days"], e["willingness"]):
            if d <= opening and not opened:
                # One total allotment per flight. Current seats are observable;
                # remaining protection comes from the frozen baseline forecast.
                protection = _remaining_protection(pred, opening)
                quota = max(0, min(releasable, seats-protection))
                quota = int(math.floor(quota*fraction))
                opened = True
            eligible = bool(members[customer] and d <= opening and d >= world["min_notice"][customer])
            wants_member = eligible and (bool(was_normal) or willingness >= p+cfg["mandatory_fees"])
            action = "DECLINE"
            if wants_member:
                member_requests += 1
            if wants_member and quota > 0 and seats > 0:
                quota -= 1
                seats -= 1
                sold_member += 1
                used[customer] = True
                switched += int(was_normal)
                action = "BUY_MEMBER"
            elif was_normal and seats > 0:
                seats -= 1
                sold_normal += 1
                action = "BUY_REGULAR"
            if include_events and len(logs) < 100:
                logs.append({"customer_id": f"SYN-{customer:04d}", "trip_id": f"F{flight_index:03d}-C{customer:04d}",
                             "day": int(d), "action": action, "is_member": bool(members[customer]),
                             "baseline_normal_intent": bool(was_normal), "source": "synthetic_choice_model"})
        member_bookings += sold_member
        normal_bookings += sold_normal
        flights.append({"flight": flight_index, "departure_period_day": e["departure_period_day"],
                        "initial_available": e["available"], "member_bookings": sold_member,
                        "normal_bookings": sold_normal, "remaining": seats})
    joined = int(members.sum())
    service = member_bookings/member_requests if member_requests else 0.
    unused = 1-float(used.sum())/joined if joined else 0.
    ledger = {"membership_revenue": joined*v, "member_ticket_revenue": member_bookings*p,
              "normal_ticket_revenue": normal_bookings*cfg["normal_base_fare"],
              "ancillary_margin": (member_bookings+normal_bookings)*cfg["ancillary_margin"],
              "incremental_passenger_cost": (member_bookings+normal_bookings)*cfg["incremental_cost"],
              "membership_service_cost": joined*cfg["member_service_cost"],
              "program_cost": cfg["program_cost"] if joined else 0,
              "pass_through_fees_excluded": (member_bookings+normal_bookings)*cfg["mandatory_fees"]}
    profit = ledger["membership_revenue"]+ledger["member_ticket_revenue"]+ledger["normal_ticket_revenue"]+ledger["ancillary_margin"]-ledger["incremental_passenger_cost"]-ledger["membership_service_cost"]-ledger["program_cost"]
    feasible = bool(joined > 0 and service >= cfg["min_service_rate"] and unused <= cfg["max_unused_member_rate"])
    return {"member_fare": p, "membership_fee": v, "open_day": opening, "release_fraction": fraction,
            "members": joined, "member_bookings": member_bookings, "normal_bookings": normal_bookings,
            "member_requests": member_requests, "service_rate": round(service, 4),
            "unused_member_rate": round(unused, 4), "normal_to_member_switches": switched,
            "profit": round(profit, 2), "incremental_profit": round(profit-world["baseline_profit"], 2),
            "feasible": feasible, "ledger": ledger, "flights": flights, "events": logs,
            "decision": "OFFER" if feasible else "REJECTED",
            "reason": "Within synthetic service constraints" if feasible else "Insufficient membership uptake or usable seat supply"}


def _aggregate(results):
    out = dict(results[0])
    keys = ["members", "member_bookings", "normal_bookings", "member_requests", "service_rate",
            "unused_member_rate", "normal_to_member_switches", "profit", "incremental_profit"]
    for key in keys:
        out[key] = round(float(np.mean([r[key] for r in results])), 3)
    out["feasible"] = all(r["feasible"] for r in results)
    out["decision"] = "OFFER" if out["feasible"] else "REJECTED"
    out["reason"] = ("Within synthetic service constraints in every search replicate"
                     if out["feasible"] else "At least one replicate fails membership uptake or usable seat supply constraints")
    out["ledger"] = {k: round(float(np.mean([r["ledger"][k] for r in results])), 2) for k in out["ledger"]}
    out["profit_p10"] = round(float(np.quantile([r["incremental_profit"] for r in results], .1)), 2)
    out["profit_p90"] = round(float(np.quantile([r["incremental_profit"] for r in results], .9)), 2)
    out["loss_rate"] = float(np.mean([r["incremental_profit"] < 0 for r in results]))
    out.pop("flights", None)
    out.pop("events", None)
    return out


def optimize(forecast_result: dict, config: dict | None = None) -> dict:
    cfg = _config(config)
    worlds = [_world(forecast_result, cfg, cfg["seed"]+1009*i) for i in range(cfg["replicates"])]
    baseline = {"decision": "NO_OFFER", "incremental_profit": 0., "feasible": True,
                "profit": round(float(np.mean([w["baseline_profit"] for w in worlds])), 2),
                "normal_bookings": round(float(np.mean([w["baseline_normal"] for w in worlds])), 2),
                "member_bookings": 0, "members": 0, "membership_fee": 0, "member_fare": 0,
                "open_day": None, "release_fraction": 0, "service_rate": None,
                "reason": "Keep ordinary sales; no membership fees collected."}
    candidates, trace = [], []
    best = dict(baseline)
    if int(forecast_result.get("days_to_departure", 28)) == 0:
        return {"config": cfg, "baseline": baseline, "best": best, "fixed_offer": None,
                "candidates": [], "trace": [], "holdout": dict(baseline), "stress": [],
                "example_events": [], "example_flights": [],
                "assumptions": ["Sales cutoff reached. No future member offer may be issued."]}
    decision_day = max(1, int(forecast_result.get("days_to_departure", 28)))
    openings = sorted({min(d, decision_day) for d in [28, 14, 7]}, reverse=True)
    for index, candidate in enumerate(product([0, 30, 70, 100], [199, 399, 599, 799], openings, [.25, .5, .75, 1.])):
        result = _aggregate([_run(w, candidate, cfg) for w in worlds])
        result["candidate_id"] = index
        candidates.append(result)
        if result["feasible"] and result["incremental_profit"] > best["incremental_profit"]:
            best = dict(result)
        trace.append({"iteration": index+1, "candidate_profit": result["incremental_profit"],
                      "best_profit": best["incremental_profit"], "feasible": result["feasible"]})
    holdout, stress, detail = None, [], None
    if best["decision"] == "OFFER":
        selected = (best["member_fare"], best["membership_fee"], best["open_day"], best["release_fraction"])
        fresh = [_world(forecast_result, cfg, cfg["seed"]+500003+i*1009) for i in range(4)]
        holdout = _aggregate([_run(w, selected, cfg) for w in fresh])
        holdout["purpose"] = "Untouched seeds; never used to reselect the reported candidate"
        detail = _run(worlds[0], selected, cfg, include_events=True)
        for name, cost_mult, interest_mult, demand_mult, group_size in [("High passenger cost", 1.5, 1, 1, 1), ("Low member interest", 1, .6, 1, 1), ("Normal demand surge", 1, 1, 1.5, 1), ("Correlated four-person demand", 1, 1, 1, 4)]:
            alternate = dict(cfg, incremental_cost=cfg["incremental_cost"]*cost_mult,
                             interest_multiplier=cfg["interest_multiplier"]*interest_mult)
            result = _aggregate([_run(_world(forecast_result, alternate, cfg["seed"]+700001+i, demand_mult, group_size), selected, alternate) for i in range(3)])
            result["scenario"] = name
            stress.append(result)
    else:
        holdout = {**baseline, "purpose": "No offer is retained; no pass fees or incremental costs incurred."}
    fixed = _aggregate([_run(w, (70, 399, min(14, decision_day), .5), cfg) for w in worlds])
    return {"config": cfg, "baseline": baseline, "fixed_offer": fixed, "best": best,
            "candidates": candidates, "trace": trace, "holdout": holdout, "stress": stress,
            "example_events": detail["events"] if detail else [],
            "example_flights": detail["flights"] if detail else [],
            "assumptions": ["All demand, customer preferences and costs are synthetic; not a representative HK Express estimate.",
                            "Membership fee is collected once for the full configured term; all simulated flights occur within that term.",
                            "Same customer identities, normal purchase intent and event randomness are replayed for every candidate.",
                            "At most one exogenous itinerary per customer per departure calendar day is assigned before either policy runs.",
                            "Normal base fares stay fixed; mandatory fees are assumed pass-through and excluded from contribution.",
                            "Each flight receives one finite member allotment, after frozen NHPP protection; accepted bookings cannot exceed capacity.",
                            "Pre-existing flight bookings are held constant in both arms; the ledger covers remaining sales and the full-term programme.",
                            "This finite flight catalogue is a supply scenario, not HK Express annual route coverage.",
                            "Search-set P10/P90 across few repeats are simulation spread, not confidence intervals or real market guarantees.",
                            "Correlated group requests are stress-tested; all-or-nothing party acceptance is not implemented.",
                            "Renewals, future cancellations, competing carriers and paid acquisition are not modelled in this pricing experiment."]}

"""One chronological, finite-inventory synthetic airline market.

The environment owns truth, time, prices, inventory and accounting. Decision
providers receive an observation whitelist, never the future event queue. All
monetary ledger entries use integer HKD cents. No real traveller distribution or
causal demand response is claimed by this hackathon simulator.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from datetime import date, timedelta

import numpy as np

from backend.nhpp import forecast, surge_alarm
from backend.release_policy import RELEASE_DAYS, VERSION as RELEASE_VERSION, MONITOR_VERSION, release_budget
from llm_agent.population import population
from simulation.generate import simulate_flight

VERSION = "shared-market-v3"
DEFAULTS = {
    "horizon_days": 365, "membership_days": 365, "flight_count": 9,
    "customer_count": 24, "occasions_per_customer": 3,
    "start_date": "2027-01-01", "mandatory_fees": 250,
    "checked_bag_fee": 80, "checked_bag_cost": 15,
    "incremental_passenger_cost": 120, "cancellation_fee": 100,
    "membership_service_cost": 30, "program_cost": 1500,
    "background_cancellation_probability": .025,
}
POLICY_DEFAULTS = {"name": "candidate", "enabled": True, "member_fare": 70,
                   "membership_fee": 399, "open_day": 28, "release_days": list(RELEASE_DAYS), "release_fraction": .75}
MONEY = ("cash_collected", "refunds_paid", "membership_revenue", "normal_base_revenue",
         "member_base_revenue", "ancillary_revenue", "cancellation_revenue",
         "mandatory_liability", "mandatory_remitted", "passenger_cost", "ancillary_cost",
         "membership_service_cost", "program_cost")


def _cents(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError("Money must be finite and nonnegative")
    return int(round(value * 100))


def _money(value):
    return round(value / 100, 2)


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def _date(state, day):
    return (date.fromisoformat(state["config"]["start_date"]) + timedelta(days=int(day))).isoformat()


def _validate(config, policy):
    if policy.get("seat_calibration") is not None:
        from backend.seat_feedback import validate_profile
        validate_profile(policy["seat_calibration"])
    for key, low, high in (("horizon_days", 90, 730), ("membership_days", 1, 730),
                           ("flight_count", 6, 12), ("customer_count", 1, 500),
                           ("occasions_per_customer", 2, 3)):
        v = config[key]
        if isinstance(v, bool) or not isinstance(v, int) or not low <= v <= high:
            raise ValueError(f"{key} must be an integer in {low}..{high}")
    for key in ("mandatory_fees", "checked_bag_fee", "checked_bag_cost", "incremental_passenger_cost", "cancellation_fee", "membership_service_cost", "program_cost"):
        if _cents(config[key]) > 1000000:
            raise ValueError(f"{key} exceeds supported limit")
    if not 0 <= config["background_cancellation_probability"] <= 1:
        raise ValueError("Invalid cancellation probability")
    if not isinstance(policy["enabled"], bool):
        raise ValueError("enabled must be boolean")
    if policy["open_day"] != 28 or policy.get("release_days") != list(RELEASE_DAYS):
        raise ValueError("Release schedule is fixed at D28, D14 and D7; open_day must be 28")
    if isinstance(policy["release_fraction"], bool) or not 0 <= policy["release_fraction"] <= 1:
        raise ValueError("release_fraction must be in 0..1")
    for key in ("member_fare", "membership_fee"):
        if _cents(policy[key]) > 1000000:
            raise ValueError(f"{key} exceeds supported limit")
    date.fromisoformat(config["start_date"])


def create_market(config: dict | None = None, seed: int = 117, policy: dict | None = None) -> dict:
    """Create JSON-serializable state. Policies share identical exogenous worlds.

    Historical pre-D28 passengers are existing occupancy, with sunk payments and
    costs outside this experiment's contribution ledger. Future background demand
    and the agent cohort are separate synthetic populations, paired across policy.
    """
    cfg = {**DEFAULTS, **(config or {})}
    pol = copy.deepcopy({**POLICY_DEFAULTS, **(policy or {})})
    if str(pol["name"]).upper() in ("NO_OFFER", "BASELINE") and "enabled" not in (policy or {}):
        pol["enabled"] = False
    _validate(cfg, pol)
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise ValueError("seed must be a nonnegative integer")
    rng = np.random.default_rng(seed)
    state = {"version": VERSION, "seed": seed, "config": cfg, "policy": pol,
             "market_id": f"market-{seed}-{_digest(pol)[:10]}", "day": 0., "cursor": 0,
             "pending": None, "events": [], "flights": {}, "customers": {},
             "bookings": {}, "records": [], "ledger_cents": {k: 0 for k in MONEY},
             "ledger_entries": [], "forecast_calls": 0, "background_denied": 0,
             "background_requested": 0, "invalid_decisions": 0}
    if pol["enabled"]:
        _post(state, "programme", "programme", program_cost=_cents(cfg["program_cost"]))
    events = state["events"]
    clusters = [[] for _ in range(3)]
    centers = [round(35 + (cfg["horizon_days"] - 45) * x) for x in (.05, .49, .94)]
    for i in range(cfg["flight_count"]):
        cluster = i % 3
        slot = i // 3
        dep = centers[cluster] + slot
        generated = simulate_flight(i, seed)
        fid = f"MKT-{i + 1:03d}"
        history = []
        for row in generated["snapshots"]:
            if row["days_to_departure"] < 28:
                continue
            r = {k: row[k] for k in ("days_to_departure", "capacity", "booked_seats", "available_seats", "empty_rate", "normal_base_fare", "normal_total_fare", "gross_bookings", "cancellations", "interval_days")}
            r["flight_id"] = fid
            history.append(r)
        at28 = history[-1]
        truth = [t for t in generated["truth"] if t["interval_start_day"] <= 28]
        departure_time = ("10:30", "14:00", "19:00", "08:30")[slot]
        departure_at = dep + int(departure_time[:2]) / 24 + int(departure_time[3:]) / 1440
        flight = {"flight_id": fid, "origin": "HKG", "destination": ("FUK", "KIX", "TPE", "ICN")[slot],
                  "departure_day": dep, "departure_time": ("10:30", "14:00", "19:00", "08:30")[slot],
                  "departure_at": departure_at,
                  "capacity": at28["capacity"], "legacy_seats": at28["booked_seats"],
                  "occupied": at28["booked_seats"], "history": history, "active": False,
                  "departed": False, "member_remaining": 0, "member_active": 0, "protection_remaining": at28["capacity"],
                  "normal_since_snapshot": 0, "cancel_since_snapshot": 0,
                  "base_fare": truth[0]["internal_base_fare"], "forecast": None,
                  "quota_history": [], "quota_cohorts": [], "background_requested": 0, "background_denied": 0,
                  "scenario_scoring_only": generated["summary"]["scenario"]}
        state["flights"][fid] = flight
        clusters[cluster].append(fid)
        for d in range(28, -1, -1):
            # The last observation is exactly 2h before the displayed departure.
            time = departure_at - d if d else departure_at - 2 / 24
            price = next((t["internal_base_fare"] for t in truth if t["interval_start_day"] == d), truth[-1]["internal_base_fare"])
            events.append({"time": time, "kind": "snapshot", "flight_id": fid, "day_to_departure": d, "base_fare": price})
        for row in truth:
            d = row["interval_start_day"]
            duration = 22 / 24 if d == 1 else 1.
            for j in range(row["demand_requests"]):
                ticket = f"BG-{fid}-{d}-{j}"
                at = departure_at - d + float(rng.uniform(.005, duration - .005))
                events.append({"time": at, "kind": "background", "flight_id": fid, "booking_id": ticket, "base_fare": row["internal_base_fare"]})
                if rng.random() < cfg["background_cancellation_probability"] and departure_at - at > 1:
                    events.append({"time": float(rng.uniform(at + .05, departure_at - .1)), "kind": "background_cancel", "booking_id": ticket})
        events.append({"time": departure_at, "kind": "departure", "flight_id": fid})

    people = population(cfg["customer_count"], seed)
    for i, person in enumerate(people):
        party = 2 if person["segment"] == "couple" else person["party_size"]
        occasions = []
        for k in range(cfg["occasions_per_customer"]):
            choices = clusters[k]
            desired = state["flights"][choices[i % len(choices)]]
            routes = [desired["destination"]] if person["route_match"] else ["LAX"]
            if person["route_match"] and person["flexibility_days"] >= 2:
                routes = sorted({state["flights"][fid]["destination"] for fid in choices})
            occasion = {"occasion_id": f"TRIP-{i + 1}-{k + 1}", "desired_departure_day": desired["departure_day"],
                        "desired_destination": routes[0], "acceptable_destinations": routes,
                        "trip_budget": round(person["total_budget"] * party, 2), "booking_id": None,
                        "change_scoring_only": "cannot_travel" if rng.random() < .12 else "date_uncertain" if rng.random() < .15 else "unchanged"}
            occasions.append(occasion)
            jitter = float(rng.uniform(.03, .87))
            for d in RELEASE_DAYS:
                events.append({"time": desired["departure_at"] - d + jitter, "kind": "decision", "stage": "subscription", "customer_id": person["customer_id"], "occasion_id": occasion["occasion_id"]})
                events.append({"time": desired["departure_at"] - d + jitter + .00001, "kind": "decision", "stage": "quote", "customer_id": person["customer_id"], "occasion_id": occasion["occasion_id"]})
            events.append({"time": desired["departure_at"] - 3 + jitter, "kind": "decision", "stage": "plan_change", "customer_id": person["customer_id"], "occasion_id": occasion["occasion_id"]})
        budget = _cents(person["total_budget"] * party * cfg["occasions_per_customer"] * 1.15)
        existing = i % 14 in (2, 6)
        public = {**person, "party_size": party, "total_budget": _money(budget), "expected_trips": cfg["occasions_per_customer"],
                  "checked_bags": party if i % 3 == 1 else 0, "assistance_required": person["segment"] == "access_needs",
                  "departure_time_window": ["08:00", "22:00"], "membership_active": existing,
                  "next_period_budget": _money(budget), "next_period_budget_source": "explicit synthetic assumption; no renewal payment simulated"}
        customer = {"person": public, "budget_cents": budget, "initial_budget_cents": budget,
                    "joined_this_run": False, "membership_started": -245 if existing else None,
                    "membership_expires": 120 if existing else None, "membership_fee_cents": 0,
                    "bookings": [], "occasions": occasions, "renewal_intention": None,
                    "membership_term_closed": False,
                    "ticket_spend_cents": 0, "refund_cents": 0}
        state["customers"][person["customer_id"]] = customer
        events.append({"time": float(120 if existing else cfg["horizon_days"]), "kind": "decision", "stage": "term_end", "customer_id": person["customer_id"], "occasion_id": None})
    # Arrival times and same-time tie keys are entirely policy independent.
    events.sort(key=lambda e: (e["time"], {"snapshot": 0, "background_cancel": 1, "background": 2, "decision": 3, "departure": 4}[e["kind"]], e.get("customer_id", e.get("flight_id", e.get("booking_id", "")))))
    for i, event in enumerate(events):
        event["event_id"] = f"E{i:06d}"
    state["exogenous_sha256"] = _digest({"seed": seed, "events": events, "customers": state["customers"],
                                          "flights": state["flights"]})
    return state


def _active(customer, day):
    return customer["membership_expires"] is not None and day < customer["membership_expires"]


def _post(state, kind, identifier, **amounts):
    for key, value in amounts.items():
        if key not in MONEY or not isinstance(value, int):
            raise ValueError("Invalid ledger posting")
        state["ledger_cents"][key] += value
    state["ledger_entries"].append({"day": state["day"], "kind": kind, "id": identifier, **amounts})


def _member_sellable(f):
    if not f["active"] or f["departed"]:
        return 0
    reserve = f["protection_remaining"] if "quota_cohorts" in f else 0
    return min(f["member_remaining"], max(0, f["capacity"] - f["occupied"] - reserve))


def _buy(state, fid, bid, customer_id, occasion_id, party, bags, member, base_fare):
    f, cfg = state["flights"][fid], state["config"]
    if f["capacity"] - f["occupied"] < party or (member and _member_sellable(f) < 1):
        raise ValueError("Insufficient shared inventory")
    normal = _cents(base_fare) * (party - int(member))
    member_base = _cents(state["policy"]["member_fare"]) if member else 0
    ancillary = _cents(cfg["checked_bag_fee"]) * bags
    mandatory = _cents(cfg["mandatory_fees"]) * party
    total = normal + member_base + ancillary + mandatory
    booking = {"booking_id": bid, "flight_id": fid, "customer_id": customer_id, "occasion_id": occasion_id,
               "party_size": party, "bags": bags, "member_seats": int(member), "normal_seats": party - int(member),
               "normal_base_cents": normal, "member_base_cents": member_base, "ancillary_cents": ancillary,
               "mandatory_cents": mandatory, "total_cents": total, "status": "confirmed", "booked_day": state["day"], "refund_cents": 0}
    if customer_id is not None:
        c = state["customers"][customer_id]
        if c["budget_cents"] < total:
            raise ValueError("Insufficient budget")
        c["budget_cents"] -= total
        c["ticket_spend_cents"] += total
        c["bookings"].append(bid)
        next(o for o in c["occasions"] if o["occasion_id"] == occasion_id)["booking_id"] = bid
    state["bookings"][bid] = booking
    f["occupied"] += party
    f["normal_since_snapshot"] += booking["normal_seats"]
    f["protection_remaining"] = max(0, f["protection_remaining"] - booking["normal_seats"])
    f["member_active"] += int(member)
    if member:
        cohort = next(c for c in f["quota_cohorts"] if c["remaining"] > 0)
        cohort["remaining"] -= 1
        cohort["sold"] += 1
        booking["quota_round_day"] = cohort["round_day"]
        f["member_remaining"] -= 1
    # Normal sales change physical capacity, not the identity of valid unsold
    # quota. Such entitlements are executable only while protection leaves room.
    _post(state, "booking", bid, cash_collected=total, normal_base_revenue=normal, member_base_revenue=member_base,
          ancillary_revenue=ancillary, mandatory_liability=mandatory)
    return booking


def _cancel(state, bid):
    b = state["bookings"].get(bid)
    if not b or b["status"] != "confirmed":
        return None
    f = state["flights"][b["flight_id"]]
    if state["day"] >= f["departure_at"] - 2 / 24:
        raise ValueError("Cancellation cutoff passed")
    fee = min(b["mandatory_cents"], _cents(state["config"]["cancellation_fee"]))
    refund = b["mandatory_cents"] - fee
    b.update(status="cancelled", refund_cents=refund, cancelled_day=state["day"])
    f["occupied"] -= b["party_size"]
    f["member_active"] -= b["member_seats"]
    f["cancel_since_snapshot"] += b["normal_seats"]
    # Cancellation returns a physical seat, not a new member allocation.
    # A sold entitlement stays consumed; only a later scheduled round can add
    # quota. Existing unused entitlements can become executable again.
    if b["customer_id"] is not None:
        c = state["customers"][b["customer_id"]]
        c["budget_cents"] += refund
        c["refund_cents"] += refund
    _post(state, "cancellation", bid, refunds_paid=refund, cancellation_revenue=fee, mandatory_liability=-b["mandatory_cents"])
    return b


def _monitor(state, f, d, predict):
    """Between rounds: a weekday-matched surge alarm refreshes the forecast.

    Tighten-only. It may raise normal-demand protection, which blocks valid
    unsold quota from sale, but it never issues, cancels or resets quota.
    """
    alarm = surge_alarm(f["history"], d)
    if not alarm["alarm"]:
        return
    prediction = predict()
    state["monitor_forecast_calls"] = state.get("monitor_forecast_calls", 0) + 1
    available = f["capacity"] - f["occupied"]
    refreshed = max(prediction["protection_p90"], available - prediction["releasable_seats"])
    before = f["protection_remaining"]
    f["protection_remaining"] = max(before, refreshed)
    f.setdefault("monitor_history", []).append({
        "day": state["day"], "days_to_departure": d, "monitor_version": MONITOR_VERSION,
        "alarm": alarm, "refreshed_protection": refreshed, "protection_before": before,
        "protection_after": f["protection_remaining"], "tightened": f["protection_remaining"] > before,
        "member_remaining": f["member_remaining"], "member_sellable": _member_sellable(f)})


def _automatic(state, event):
    kind = event["kind"]
    if kind == "background":
        f = state["flights"][event["flight_id"]]
        state["background_requested"] += 1
        f["background_requested"] += 1
        if f["occupied"] >= f["capacity"]:
            state["background_denied"] += 1
            f["background_denied"] += 1
        else:
            _buy(state, f["flight_id"], event["booking_id"], None, None, 1, 0, False, event["base_fare"])
    elif kind == "background_cancel":
        _cancel(state, event["booking_id"])
    elif kind == "snapshot":
        f = state["flights"][event["flight_id"]]
        d = event["day_to_departure"]
        if d in RELEASE_DAYS and any(c["round_day"] == d for c in f["quota_cohorts"]):
            return  # Replayed round events cannot issue or reset another batch.
        f["active"] = d > 0
        f["base_fare"] = event["base_fare"]
        if d < f.get('history_as_of_day', 28):
            f["history"].append({"flight_id": f["flight_id"], "days_to_departure": d, "capacity": f["capacity"],
                                  "booked_seats": f["occupied"], "available_seats": f["capacity"] - f["occupied"],
                                  "empty_rate": (f["capacity"] - f["occupied"]) / f["capacity"],
                                  "normal_base_fare": f["base_fare"] if f["occupied"] < f["capacity"] and d else None,
                                  "normal_total_fare": f["base_fare"] + state["config"]["mandatory_fees"] if f["occupied"] < f["capacity"] and d else None,
                                  "gross_bookings": f["normal_since_snapshot"], "cancellations": f["cancel_since_snapshot"],
                                  "interval_days": 22 / 24 if d == 0 else 1.})
        f["normal_since_snapshot"] = f["cancel_since_snapshot"] = 0
        seed_offset = int(f['flight_id'][-3:]) if f['flight_id'][-3:].isdigit() else int(hashlib.sha256(f['flight_id'].encode()).hexdigest()[:6],16)

        def predict():
            prediction = forecast(f["history"], d, state["seed"] + seed_offset)
            if state["policy"].get("seat_calibration") is not None:
                from backend.seat_feedback import apply_profile
                prediction = apply_profile(prediction, state["policy"]["seat_calibration"], d)
            return prediction
        if 0 < d < max(RELEASE_DAYS) and d not in RELEASE_DAYS and f["member_remaining"] > 0:
            _monitor(state, f, d, predict)
        if d in RELEASE_DAYS and not any(c["round_day"] == d for c in f["quota_cohorts"]):
            prediction = predict()
            f["forecast"] = {k: prediction[k] for k in ("model", "days_to_departure", "expected_remaining_demand", "raw_protection_p90", "protection_p90", "releasable_seats", "expected_empty_seats")}
            f["forecast"].update({k: prediction[k] for k in ("base_expected_remaining_demand", "base_protection_p90", "seat_feedback_version", "seat_feedback_generation") if k in prediction})
            state["forecast_calls"] += 1
            available = f["capacity"] - f["occupied"]
            # Preserve NHPP's fail-closed quality gates as well as its risk reserve.
            f["protection_remaining"] = max(prediction["protection_p90"], available - prediction["releasable_seats"])
            fraction = state["policy"]["release_fraction"] if state["policy"]["enabled"] else 0.
            budget = release_budget(available, f["protection_remaining"], f["member_remaining"], fraction)
            cohort = {"round_day": d, "issued": budget["new_allocation"],
                      "remaining": budget["new_allocation"], "sold": 0, "expired": 0}
            f["quota_cohorts"].append(cohort)
            f["member_remaining"] = budget["remaining_quota"]
            f["quota_history"].append({"day": state["day"], "days_to_departure": d, **f["forecast"], **budget,
                                       "effective_normal_protection": f["protection_remaining"],
                                       "member_sellable": _member_sellable(f)})
        if not d:
            for cohort in f["quota_cohorts"]:
                cohort["expired"] += cohort["remaining"]
                cohort["remaining"] = 0
            f["member_remaining"] = 0
    elif kind == "departure":
        f = state["flights"][event["flight_id"]]
        f["departed"] = True
        for b in state["bookings"].values():
            if b["flight_id"] == f["flight_id"] and b["status"] == "confirmed":
                b["status"] = "flown"
                _post(state, "departure", b["booking_id"], mandatory_liability=-b["mandatory_cents"], mandatory_remitted=b["mandatory_cents"],
                      passenger_cost=_cents(state["config"]["incremental_passenger_cost"]) * b["party_size"],
                      ancillary_cost=_cents(state["config"]["checked_bag_cost"]) * b["bags"])


def _occasion(customer, oid):
    return next((o for o in customer["occasions"] if o["occasion_id"] == oid), None)


def _quotes(state, customer, occasion, *, include_ineligible=False):
    person = customer["person"]
    offers = []
    for f in state["flights"].values():
        if not f["active"] or f["departed"] or state["day"] >= f["departure_at"] - 2 / 24:
            continue
        if f["destination"] not in occasion["acceptable_destinations"] or abs(f["departure_day"] - occasion["desired_departure_day"]) > person["flexibility_days"]:
            continue
        if f["departure_at"] - state["day"] < person["minimum_notice_days"]:
            continue
        if not person["departure_time_window"][0] <= f["departure_time"] <= person["departure_time_window"][1]:
            continue
        if person["assistance_required"] and f["departure_at"] - state["day"] < 14:
            continue
        party = person["party_size"]
        if f["capacity"] - f["occupied"] < party:
            continue
        if any(state["bookings"][bid]["status"] in ("confirmed", "flown") and state["flights"][state["bookings"][bid]["flight_id"]]["departure_day"] == f["departure_day"] for bid in customer["bookings"]):
            continue
        for member in (False, True):
            if member and (not state["policy"]["enabled"] or _member_sellable(f) < 1):
                continue
            membership_valid = _active(customer, state["day"]) and f["departure_at"] < customer["membership_expires"]
            can_join = bool(state['policy']['enabled'] and not _active(customer,state['day']) and not customer['joined_this_run']
                            and _cents(state['policy']['membership_fee']) <= customer['budget_cents'])
            new_expiry = state['day']+state['config']['membership_days']
            valid_after_join = can_join and f['departure_at'] < new_expiry
            eligibility = ('not_required' if not member else 'already_valid' if membership_valid else
                           'eligible_if_join_now' if valid_after_join else 'new_pass_expires_before_departure' if can_join else
                           'existing_pass_expires_before_departure' if _active(customer,state['day']) else 'joining_not_currently_available')
            if member and not membership_valid and not include_ineligible:
                continue
            normal = f["base_fare"] * (party - int(member))
            base = state["policy"]["member_fare"] if member else 0
            ancillary = state["config"]["checked_bag_fee"] * person["checked_bags"]
            mandatory = state["config"]["mandatory_fees"] * party
            price = round(normal + base + ancillary + mandatory, 2)
            if _cents(price) > customer["budget_cents"] and not include_ineligible:
                continue
            offers.append({"id": f"{f['flight_id']}:{'member' if member else 'normal'}", "action": "BUY_MEMBER" if member else "BUY_REGULAR",
                           "flight_id": f["flight_id"], "origin": f["origin"], "destination": f["destination"],
                           "departure_day": f["departure_day"], "departure_date": _date(state, f["departure_day"]), "departure_time": f["departure_time"],
                           "party_size": party, "member_seats": int(member), "normal_seats": party - int(member),
                           "price": price, "currency": "HKD", "total_seats_available": f["capacity"] - f["occupied"],
                           "member_seats_available": _member_sellable(f), "days_to_departure": round(f["departure_at"] - state["day"], 3),
                           "price_breakdown": {"normal_base_fares": normal, "member_base_fare": base, "mandatory_fees": mandatory, "baggage": ancillary},
                           "membership_valid_for_departure": membership_valid, "checked_bags": person["checked_bags"],
                           'membership_required': bool(member),
                           'membership_eligibility': {'status':eligibility,
                               'current_pass_valid_for_departure':bool(membership_valid),
                               'joining_now_permitted':can_join,
                               'valid_if_join_now':bool(valid_after_join),
                               'new_pass_expires_day_if_join_now':round(new_expiry,6),
                               'current_validity_is_not_post_join_validity':True},
                           "cancellation_terms": {"base_fare_refundable": False, "baggage_refundable": False, "mandatory_fees_refundable": mandatory,
                                                  "cancellation_fee_per_booking": state["config"]["cancellation_fee"], "cutoff_hours": 2}})
    return offers


def subscription_comparisons(observation):
    """Current quote arithmetic only; no future inventory or behavior prediction."""
    references=observation.get('current_quote_reference',[])
    normal={o.get('flight_id'):o for o in references if o.get('action')=='BUY_REGULAR'}
    wallet=observation.get('visible_state',observation.get('state',{})).get('remaining_budget')
    if wallet is None:
        wallet=observation.get('person',observation.get('customer',{})).get('total_budget')
    fee=observation.get('membership',{}).get('fee',0)
    comparisons=[]
    for member in references:
        if member.get('action')!='BUY_MEMBER':continue
        regular=normal.get(member.get('flight_id'))
        valid=member.get('membership_eligibility',{}).get('current_pass_valid_for_departure',member.get('membership_valid_for_departure',False))
        due=0 if valid else _cents(fee)
        ticket=_cents(member['price']); total=ticket+due
        saving=None if regular is None else _cents(regular['price'])-ticket
        balance=None if wallet is None else _cents(wallet)-total
        comparisons.append({'member_option_id':member['id'],
            'regular_option_id':regular.get('id') if regular else None,
            'flight_id':member.get('flight_id'),'currency':'HKD',
            'member_ticket_total':_money(ticket),
            'regular_ticket_total':regular['price'] if regular else None,
            'additional_membership_fee':_money(due),
            'total_outlay_for_pass_and_ticket':_money(total),
            'ticket_savings_before_pass_fee':None if saving is None else _money(saving),
            'net_savings_after_membership_fee':None if saving is None else _money(saving-due),
            'membership_fee_vs_ticket_savings':None if saving is None else ('less_than' if due<saving else 'greater_than' if due>saving else 'equal_to'),
            'wallet_budget':wallet,'wallet_remaining_after_purchase':None if balance is None else _money(balance),
            'wallet_shortfall':None if balance is None else _money(max(0,-balance)),
            'affordable_with_current_wallet':None if balance is None else balance>=0,
            'trip_ticket_budget_preference':observation.get('trip',{}).get('trip_budget'),
            'budget_rule':'Wallet budget is the transaction limit; trip ticket budget is a spending preference, not a membership-expiry rule.',
            'eligibility':copy.deepcopy(member.get('membership_eligibility',{})),
            'current_seats_not_reserved':True,
            'scope':'This exact current itinerary and whole party only; no assumed future trips or guaranteed inventory.'})
    return comparisons


def _observation(state, event):
    c = state["customers"][event["customer_id"]]
    p = copy.deepcopy(c["person"])
    active = _active(c, state["day"])
    p["membership_active"] = active
    p["upcoming_trip_count"] = sum(o["desired_departure_day"] > state["day"] for o in c["occasions"])
    current = _occasion(c, event["occasion_id"])
    booking = state["bookings"].get(current["booking_id"]) if current and current["booking_id"] else None
    visible = {"remaining_budget": _money(c["budget_cents"]), "membership_active": active,
               "membership_expires_day": c["membership_expires"], "membership_fee_paid": _money(c["membership_fee_cents"]),
               "ticket_spend": _money(c["ticket_spend_cents"]), "refund_received": _money(c["refund_cents"]),
               "bookings": [{"booking_id": bid, "flight_id": state["bookings"][bid]["flight_id"], "status": state["bookings"][bid]["status"],
                             "total_paid": _money(state["bookings"][bid]["total_cents"]), "member_seats": state["bookings"][bid]["member_seats"]} for bid in c["bookings"]]}
    own_records = [r for r in state["records"] if r["customer_id"] == event["customer_id"]]
    visible["recent_history"] = [{k: r.get(k) for k in ("day", "stage", "action", "option_id", "booking_id", "reason_code", "remaining_budget")} for r in own_records[-20:]]
    visible["experience_counts"] = {
        "waits": sum(r["action"] == "WAIT" for r in own_records),
        "declines": sum(r["action"] == "DECLINE" for r in own_records),
        "searches_without_legal_offer": sum(r.get("no_legal_offer", False) for r in own_records),
        "searches_with_insufficient_party_seats": sum(r.get("insufficient_party_seats", False) for r in own_records),
    }
    membership = {"fee": state["policy"]["membership_fee"], "term_days": state["config"]["membership_days"],
                  "member_base_fare": state["policy"]["member_fare"], "personal_nontransferable": True,
                  "companions_pay_regular_fares": True, "fee_nonrefundable": True, "seat_availability_guaranteed": False,
                  "validity_rule": "Membership must be active at both booking and departure; expiry is exclusive.",
                  "future_offer_prices_and_quotas_unknown": True, "no_automatic_renewal": True}
    membership['current_validity_field_meaning']='membership_valid_for_departure describes the current pass only; it does not describe eligibility after buying a new pass.'
    membership['join_now']={'activation':'immediate_on_successful_payment',
                            'available':bool(state['policy']['enabled'] and not active and not c['joined_this_run']
                                             and _cents(state['policy']['membership_fee'])<=c['budget_cents']),
                            'new_expiry_day':round(state['day']+state['config']['membership_days'],6),
                            'fee_affordable':_cents(state['policy']['membership_fee'])<=c['budget_cents'],
                            'wallet_after_fee':_money(c['budget_cents']-_cents(state['policy']['membership_fee'])),
                            'reserves_a_seat':False}
    # Policy names/hashes are audit metadata, never a cue in the LLM prompt.
    out = {"packet_id": f"decision:{event['event_id']}", "stage": event["stage"], "customer_id": event["customer_id"],
           "customer": p, "person": p, "day": round(state["day"], 6), "date": _date(state, state["day"]),
           "visible_state": visible, "state": visible, "membership": membership, "allowed_actions": [], "options": [],
           "waiting_disclosure": "WAIT reserves no seat or price; later offers and other travellers' decisions are unknown.",
           "source": "synthetic shared market, not observed HK Express behaviour"}
    if current:
        out["trip"] = {k: copy.deepcopy(current[k]) for k in ("occasion_id", "desired_departure_day", "desired_destination", "acceptable_destinations", "trip_budget")}
    stage = event["stage"]
    if stage == "subscription":
        out["allowed_actions"] = ["KEEP_MEMBERSHIP"] if active else ["DECLINE"]
        if state["policy"]["enabled"] and not active and not c["joined_this_run"] and _cents(state["policy"]["membership_fee"]) <= c["budget_cents"]:
            out["allowed_actions"].append("JOIN_PASS")
            out["options"] = [{"id": "pass", "action": "JOIN_PASS", "price": state["policy"]["membership_fee"], "term_days": state["config"]["membership_days"]}]
        # A reference quote is a current offer, not a reservation. Unaffordable
        # references remain explicitly non-purchasable at this subscription step.
        out["current_quote_reference"] = _quotes(state, c, current, include_ineligible=True)
    elif stage == "quote":
        if booking:
            out["allowed_actions"] = ["KEEP_BOOKING"] if booking["status"] != "cancelled" else ["DECLINE"]
        else:
            remaining = current["desired_departure_day"] - state["day"]
            out["allowed_actions"] = ["DECLINE"] + (["WAIT"] if remaining > 7 else [])
            out["options"] = _quotes(state, c, current)
            out["allowed_actions"] += sorted({o["action"] for o in out["options"]})
            matching = [f for f in state["flights"].values() if f["active"] and f["destination"] in current["acceptable_destinations"]
                        and abs(f["departure_day"] - current["desired_departure_day"]) <= p["flexibility_days"]]
            out["search_result"] = {"no_legal_offer": not bool(out["options"]),
                                    "insufficient_party_seats": any(f["capacity"] - f["occupied"] < p["party_size"] for f in matching)}
    elif stage == "plan_change":
        out["changed_circumstances"] = current["change_scoring_only"]
        if booking and booking["status"] == "confirmed":
            # Plan changes are tied to the intended occasion; a traveller may
            # have booked an earlier alternative. Validate against THAT flight.
            actual_flight = state["flights"][booking["flight_id"]]
            cutoff = actual_flight["departure_at"] - 2 / 24
            cancellable = state["day"] < cutoff
            out["allowed_actions"] = ["KEEP_BOOKING"]
            out["cancellation_status"] = {"available": cancellable, "cutoff_day": cutoff,
                                           "reason": "Before actual booked-flight cutoff" if cancellable else "Actual booked-flight cancellation cutoff has passed"}
            if cancellable:
                out["allowed_actions"].append("CANCEL_BOOKING")
                fee = min(booking["mandatory_cents"], _cents(state["config"]["cancellation_fee"]))
                out["options"] = [{"id": booking["booking_id"], "action": "CANCEL_BOOKING", "price": 0,
                                   "refund": _money(booking["mandatory_cents"] - fee), "membership_refund": 0}]
        else:
            out["allowed_actions"] = ["DECLINE"]
    else:
        has_pass = c["joined_this_run"] or c["membership_started"] is not None
        out["allowed_actions"] = ["RENEW_INTENT", "DO_NOT_RENEW"] if has_pass and state["policy"]["enabled"] else ["CONSIDER_LATER", "DECLINE"]
        out["term_outcome"] = {"travel_completed": sum(state["bookings"][bid]["status"] == "flown" for bid in c["bookings"]),
                               "member_trips_completed": sum(state["bookings"][bid]["status"] == "flown" and state["bookings"][bid]["member_seats"] > 0 for bid in c["bookings"]),
                               "renewal_intention_only_no_charge": True, "next_period_budget": p["next_period_budget"],
                               "next_period_budget_source": p["next_period_budget_source"], "next_period_trips_expected": p["expected_trips"]}
        out["term_outcome"]["observed_until_membership_expiry"] = c["membership_expires"] is not None and state["day"] >= c["membership_expires"]
        out["term_outcome"]["catalogue_scope"] = "Every planned trip in this finite synthetic catalogue is explicitly listed; no unprocessed future trip is assumed. This is not an estimate of a full airline network."
    out["legal_options"] = out["options"]
    if stage=='subscription':
        out['subscription_comparisons']=subscription_comparisons(out)
    return out


def next_observation(state: dict) -> dict | None:
    """Advance automatic market events, then pause before one traveller action."""
    if state.get("version") != VERSION:
        raise ValueError("Saved market uses an older engine; inspect it or create a new experiment")
    if state["pending"] is not None:
        return _observation(state, state["events"][state["pending"]])
    while state["cursor"] < len(state["events"]):
        event = state["events"][state["cursor"]]
        state["day"] = event["time"]
        if event["kind"] == "decision":
            state["pending"] = state["cursor"]
            return _observation(state, event)
        _automatic(state, event)
        state["cursor"] += 1
    return None


def apply_decision(state: dict, decision: dict) -> dict:
    """Validate then atomically transact one currently pending decision."""
    if state.get("version") != VERSION:
        raise ValueError("Saved market uses an older engine; inspect it or create a new experiment")
    if state["pending"] is None:
        raise ValueError("No pending observation")
    event = state["events"][state["pending"]]
    observation = _observation(state, event)
    if not isinstance(decision, dict) or decision.get("action") not in observation["allowed_actions"]:
        raise ValueError("Illegal action")
    if decision.get("packet_id", observation["packet_id"]) != observation["packet_id"]:
        raise ValueError("Stale decision packet")
    action, oid = decision["action"], decision.get("option_id")
    options = [o for o in observation["options"] if o["id"] == oid and o["action"] == action]
    option = options[0] if options else None
    if action in ("JOIN_PASS", "BUY_MEMBER", "BUY_REGULAR", "CANCEL_BOOKING"):
        if option is None:
            raise ValueError("Invalid option for action")
    elif oid is not None:
        raise ValueError("Non-purchase action requires null option_id")
    customer = state["customers"][event["customer_id"]]
    before = dict(state["ledger_cents"])
    booking_id = None
    if action == "JOIN_PASS":
        fee = _cents(option["price"])
        if customer["budget_cents"] < fee:
            raise ValueError("Insufficient budget")
        customer["budget_cents"] -= fee
        customer["membership_fee_cents"] += fee
        customer["joined_this_run"] = True
        customer["membership_started"] = state["day"]
        customer["membership_expires"] = state["day"] + state["config"]["membership_days"]
        _post(state, "membership", event["customer_id"], cash_collected=fee, membership_revenue=fee,
              membership_service_cost=_cents(state["config"]["membership_service_cost"]))
        # Observe the complete purchased term, including the explicitly empty
        # tail after the last planned occasion; do not truncate at calendar365.
        tail = state["events"][state["cursor"] + 1:]
        end = next((e for e in tail if e.get("customer_id") == event["customer_id"] and e.get("stage") == "term_end"), None)
        if end is None:
            end = {"event_id": f"TERM-{event['customer_id']}", "kind": "decision", "stage": "term_end", "customer_id": event["customer_id"], "occasion_id": None}
            tail.append(end)
        end["time"] = customer["membership_expires"]
        tail.sort(key=lambda e: (e["time"], {"snapshot": 0, "background_cancel": 1, "background": 2, "decision": 3, "departure": 4}[e["kind"]], e["event_id"]))
        state["events"][state["cursor"] + 1:] = tail
    elif action in ("BUY_MEMBER", "BUY_REGULAR"):
        booking_id = f"AG-{event['event_id']}"
        flight = state["flights"][option["flight_id"]]
        _buy(state, option["flight_id"], booking_id, event["customer_id"], event["occasion_id"], customer["person"]["party_size"],
             customer["person"]["checked_bags"], action == "BUY_MEMBER", flight["base_fare"])
    elif action == "CANCEL_BOOKING":
        booking_id = option["id"]
        _cancel(state, booking_id)
    elif action in ("RENEW_INTENT", "DO_NOT_RENEW", "CONSIDER_LATER"):
        customer["renewal_intention"] = action
    if event["stage"] == "term_end" and customer["joined_this_run"] and state["day"] >= customer["membership_expires"]:
        customer["membership_term_closed"] = True
    record = {"packet_id": observation["packet_id"], "event_id": event["event_id"], "customer_id": event["customer_id"],
              "day": state["day"], "stage": event["stage"], "action": action, "option_id": oid,
              "booking_id": booking_id, "reason_code": str(decision.get("reason_code", "UNSPECIFIED"))[:80],
              "reason": str(decision.get("reason", ""))[:1200],
              "financial_delta": {k: _money(state["ledger_cents"][k] - before[k]) for k in MONEY},
              "remaining_budget": _money(customer["budget_cents"])}
    record.update(observation.get("search_result", {}))
    state["records"].append(record)
    state["cursor"] += 1
    state["pending"] = None
    return record


def deterministic_decision(observation: dict) -> dict:
    """Explicit comparison heuristic; not learned behaviour or LLM fallback."""
    allowed = observation["allowed_actions"]
    options = observation["options"]
    state = observation["visible_state"]
    person = observation["customer"]
    action, oid = allowed[0], None
    if "JOIN_PASS" in allowed:
        references = observation.get("current_quote_reference", [])
        ordinary = {o["flight_id"]: o for o in references if o["action"] == "BUY_REGULAR"}
        members = [o for o in references if o["action"] == "BUY_MEMBER"]
        savings = max((ordinary[o["flight_id"]]["price"] - o["price"] for o in members if o["flight_id"] in ordinary), default=0)
        fee = observation["membership"]["fee"]
        expected_saving = savings * max(1, person["upcoming_trip_count"]) * person["perceived_availability"]
        cheapest = min((o["price"] for o in members), default=math.inf)
        if expected_saving >= fee and fee + cheapest <= state["remaining_budget"]:
            action, oid = "JOIN_PASS", "pass"
    if observation["stage"] == "quote" and options:
        candidates = [o for o in options if o["price"] <= observation["trip"]["trip_budget"]]
        if candidates:
            choice = min(candidates, key=lambda o: (o["price"], abs(o["departure_day"] - observation["trip"]["desired_departure_day"]), o["id"]))
            # A declared, fixed cautious-wait heuristic creates no reservation.
            if "WAIT" in allowed and choice["price"] > observation["trip"]["trip_budget"] * .9 and person["flexibility_days"] >= 2:
                action = "WAIT"
            else:
                action, oid = choice["action"], choice["id"]
        elif "WAIT" in allowed:
            action = "WAIT"
    if observation["stage"] == "plan_change" and observation.get("changed_circumstances") == "cannot_travel" and "CANCEL_BOOKING" in allowed:
        action, oid = "CANCEL_BOOKING", options[0]["id"]
    if "RENEW_INTENT" in allowed:
        used = observation["term_outcome"]["member_trips_completed"]
        fee = observation["membership"]["fee"]
        action = "RENEW_INTENT" if used >= 2 and fee <= person["next_period_budget"] else "DO_NOT_RENEW"
    return {"action": action, "option_id": oid, "reason_code": "FIXED_HEURISTIC", "reason": "Explicit synthetic comparison rule using current legal options.", "confidence": "low"}


def summarize(state: dict) -> dict:
    ledger = {k: _money(v) for k, v in state["ledger_cents"].items()}
    revenue = sum(state["ledger_cents"][k] for k in ("membership_revenue", "normal_base_revenue", "member_base_revenue", "ancillary_revenue", "cancellation_revenue"))
    variable_cost = sum(state["ledger_cents"][k] for k in ("passenger_cost", "ancillary_cost", "membership_service_cost"))
    cost = variable_cost + state["ledger_cents"]["program_cost"]
    bookings = list(state["bookings"].values())
    agent = [b for b in bookings if b["customer_id"] is not None]
    flown = [b for b in bookings if b["status"] == "flown"]
    joined = [c for c in state["customers"].values() if c["joined_this_run"]]
    served = sum(any(state["bookings"][bid]["member_seats"] and state["bookings"][bid]["status"] == "flown" for bid in c["bookings"]) for c in joined)
    cash_identity = (state["ledger_cents"]["cash_collected"] - state["ledger_cents"]["refunds_paid"]
                     - state["ledger_cents"]["mandatory_liability"] - state["ledger_cents"]["mandatory_remitted"] == revenue)
    inventories = []
    for f in state["flights"].values():
        matching = [b for b in bookings if b["flight_id"] == f["flight_id"] and b["status"] != "cancelled"]
        inventories.append({"flight_id": f["flight_id"], "origin": f["origin"], "destination": f["destination"], "departure_day": f["departure_day"],
                            "capacity": f["capacity"], "legacy_seats": f["legacy_seats"], "occupied": f["occupied"], "available": f["capacity"] - f["occupied"],
                            "member_remaining": f["member_remaining"], "member_seats": sum(b["member_seats"] for b in matching),
                            "background_denied": f["background_denied"], "quota_history": copy.deepcopy(f["quota_history"]),
                            "monitor_history": copy.deepcopy(f.get("monitor_history", [])),
                            "quota_cohorts": copy.deepcopy(f.get("quota_cohorts", [])), "member_sellable": _member_sellable(f),
                            "inventory_conserved": f["occupied"] == f["legacy_seats"] + sum(b["party_size"] for b in matching)})
    checks = {"cash_identity": cash_identity, "inventory_conserved": all(f["inventory_conserved"] for f in inventories),
              "capacity_respected": all(0 <= f["occupied"] <= f["capacity"] and 0 <= f["member_sellable"] <= f["available"] for f in inventories),
              "quota_conserved": all(
                  f["member_remaining"] == sum(c["remaining"] for c in f.get("quota_cohorts", []))
                  and all(c["issued"] == c["remaining"] + c["sold"] + c["expired"] and min(c.values()) >= 0 for c in f.get("quota_cohorts", []))
                  for f in state["flights"].values()) if state.get("version") == VERSION else True,
              "budgets_nonnegative": all(c["budget_cents"] >= 0 for c in state["customers"].values()),
              "customer_cash_identity": all(c["initial_budget_cents"] - c["membership_fee_cents"] - c["ticket_spend_cents"] + c["refund_cents"] == c["budget_cents"] for c in state["customers"].values()),
              "membership_charged_once": all(sum(e["kind"] == "membership" and e["id"] == cid for e in state["ledger_entries"]) <= 1 for cid in state["customers"])}
    if state.get("version") != VERSION:
        checks.pop("quota_conserved", None)
    complete = state["cursor"] == len(state["events"]) and state["pending"] is None
    return {"version": state.get("version", VERSION), "release_policy_version": RELEASE_VERSION if state.get("version") == VERSION else "legacy", "market_id": state["market_id"], "exogenous_sha256": state["exogenous_sha256"], "seed": state["seed"],
            "policy": copy.deepcopy(state["policy"]), "config": copy.deepcopy(state["config"]), "complete": complete,
            "ledger": {**ledger, "revenue_excluding_mandatory_fees": _money(revenue), "total_variable_cost": _money(variable_cost),
                       "total_cost": _money(cost), "contribution": _money(revenue - cost)},
            "contribution": _money(revenue - cost), "profit": _money(revenue - cost),
            "members": len(joined), "new_members": len(joined), "member_bookings": sum(b["member_seats"] for b in agent),
            "member_flown": sum(b["member_seats"] for b in agent if b["status"] == "flown"), "service_rate": served / len(joined) if joined else 0.,
            "agent_bookings": len(agent), "agent_completed_trips": sum(b["status"] == "flown" for b in agent),
            "passengers_flown": sum(b["party_size"] for b in flown), "normal_seats_flown": sum(b["normal_seats"] for b in flown),
            "background_requested": state["background_requested"], "background_denied": state["background_denied"],
            "cancellations": sum(b["status"] == "cancelled" for b in agent),
            "renewal_intent_count": sum(c["renewal_intention"] == "RENEW_INTENT" for c in state["customers"].values()),
            "renewal_is_intention_only": True, "decision_count": len(state["records"]), "forecast_calls": state["forecast_calls"],
            "monitor_forecast_calls": state.get("monitor_forecast_calls", 0), "inter_round_monitor_version": MONITOR_VERSION,
            "charged_members_full_term_observed": sum(c["membership_term_closed"] for c in joined),
            "last_observed_calendar_day": round(state["day"], 4),
            "flights": inventories, "checks": checks,
            "assumptions": ["Flights, personas, schedules, preferences, prices, arrival and cancellation paths are synthetic assumptions, not actual HK Express market shares.",
                            "The same seed creates identical latent background demand and customer occasions across policies. Demand never reads forecast means or quotas.",
                            ("The NHPP receives completed as-of normal-booking intervals, excluding member seats. Fixed D28/D14/D7 rounds add max(0,total target minus all earlier valid unsold quota); FIFO consumption and cutoff expiry are explicit."
                             if state.get("version") == VERSION else "Legacy saved market: quotas were reset at each enabled checkpoint, without the new cross-round cohort rules."),
                            ("Unspent quotas persist until cutoff, but sales remain subject to physical capacity and normal-demand protection. Cancellation returns physical seats without minting quota. No new quota between rounds; a weekday-matched surge alarm between rounds may only refresh and raise protection."
                             if state.get("version") == VERSION else "Historical saved result; not reinterpreted as validation of the three-round additive policy."),
                            "A pass discounts only its holder; companions pay normal fares. Every party purchase succeeds completely or not at all.",
                            "Pre-D28 bookings are existing occupancy; their sunk payments and operating costs are outside the comparative ledger.",
                            "Contribution includes per-trip costs, per-new-member service cost and one enabled-programme setup cost. It excludes mandatory pass-through fees and fixed aircraft costs; it is not total airline net profit.",
                            "Base fares and baggage are nonrefundable. All mandatory fees are refunded less the explicit cancellation service fee before cutoff; variable travel costs accrue at departure.",
                            "Membership must be valid at booking and departure, fee charged once in this run; every purchased term is observed to expiry. Every planned occasion is in the finite catalogue; the tail after the last occasion has explicitly no further planned trips, not censored usage. Renewal is an intention with an assumed next-period budget, never a paid conversion.",
                            "Only current reference offers are disclosed. WAIT never reserves inventory and no future prices, quotas, latent demand or counterfactual decisions are sent to agents."]}

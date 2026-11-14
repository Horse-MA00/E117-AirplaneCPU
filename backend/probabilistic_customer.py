"""Frozen heterogeneous choice assumptions; synthetic feedback, not human truth."""
from __future__ import annotations
import hashlib
import math

VERSION = "probabilistic-customer-v1"
SCENARIOS = {"base": 1.0, "price_sensitive": 1.5, "less_sensitive": .65}


def uniform(*parts):
    # Keyed draws do not depend on price, policy name, option order or call order.
    raw = hashlib.sha256("|".join(map(str, parts)).encode()).digest()
    return (int.from_bytes(raw[:8], "big") + .5) / 2**64


def choose(observation, scenario="base"):
    if scenario not in SCENARIOS:
        raise ValueError("Unknown customer scenario")
    from backend.shared_market import deterministic_decision
    allowed, options = observation["allowed_actions"], observation.get("options", [])
    person, state = observation["customer"], observation["visible_state"]
    cid = observation.get("customer_id", person.get("customer_id", "customer"))
    sensitivity = (.65 + 1.1 * uniform(VERSION, cid, "sensitivity")) * SCENARIOS[scenario]
    budget = max(1., observation.get("trip", {}).get("trip_budget", person.get("total_budget", 1000)))
    utilities = {}
    if observation["stage"] == "quote" and "DECLINE" in allowed:
        for option in options:
            if option["action"] not in ("BUY_MEMBER", "BUY_REGULAR"):
                continue
            mismatch = abs(option["departure_day"] - observation["trip"]["desired_departure_day"])
            # Full party price includes tax, baggage and regular-fare companions.
            utilities[(option["action"], option["id"])] = (
                3.2 - 3 * sensitivity * option["price"] / budget
                - .2 * mismatch / max(1, person.get("flexibility_days", 0)))
        utilities[("DECLINE", None)] = 0.
        if "WAIT" in allowed:
            utilities[("WAIT", None)] = .15 + .5 * uniform(VERSION, cid, "patience")
    elif "JOIN_PASS" in allowed:
        references = observation.get("current_quote_reference", [])
        regular = {o["flight_id"]: o["price"] for o in references if o["action"] == "BUY_REGULAR"}
        member = [o for o in references if o["action"] == "BUY_MEMBER"]
        saving = max((regular.get(o["flight_id"], o["price"]) - o["price"] for o in member), default=0)
        fee = observation["membership"]["fee"]
        affordable = any(fee + o["price"] <= state["remaining_budget"] for o in member)
        expected = saving * max(1, person.get("upcoming_trip_count", 1)) * person.get("perceived_availability", .3)
        utilities[("DECLINE", None)] = 0.
        if affordable:
            utilities[("JOIN_PASS", "pass")] = (expected - sensitivity * fee) / 120 - .5
    else:
        result = deterministic_decision(observation)
        return {"decision": result, "probabilities": [], "version": VERSION, "scenario": scenario}
    # Softmax probabilities and keyed Gumbel shocks implement the same choice law.
    highest = max(utilities.values())
    weights = {key: math.exp(value - highest) for key, value in utilities.items()}
    total = sum(weights.values())
    packet = observation.get("packet_id", "decision")
    def score(key):
        u = min(1 - 1e-15, max(1e-15, uniform(VERSION, cid, packet, *key)))
        return utilities[key] - math.log(-math.log(u))
    action, oid = max(sorted(utilities, key=str), key=score)
    return {"decision": {"action": action, "option_id": oid,
            "reason_code": "PROBABILISTIC_RULE",
            "reason": "Synthetic choice from full price, stable preferences and current legal options; not a human observation.",
            "confidence": "low"},
            "probabilities": [{"action": key[0], "option_id": key[1], "probability": weights[key] / total}
                              for key in sorted(weights, key=str)],
            "version": VERSION, "scenario": scenario}

"""Stateful synthetic traveller journeys and immutable external decision packets."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import random
import uuid

from .population import population
from .output_contract import RESPONSE_LANGUAGE, CURRENCY, CONTRACT_VERSION

ROOT = Path(__file__).resolve().parents[1]
PROMPT = Path(__file__).parent / "prompts/journey_system.txt"
PROMPT_VERSION = "traveller-journey-v2.2-en"
STAGES = ("subscription", "quote_d28", "quote_d14", "quote_d7", "plan_change", "term_end")


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def enrich(person: dict, index: int) -> dict:
    """Concrete needs are hypothetical independent constraints, not demographics."""
    p = copy.deepcopy(person)
    party = int(p.get("party_size", 1))
    if p.get("segment") == "couple":
        party = 2
    base_budget = int(p["total_budget"])
    p.update(
        party_size=party,
        total_budget=max(base_budget, int(base_budget * party * 1.5)),
        desired_origin="HKG", desired_destination="LAX" if not p.get("route_match", True) else "FUK",
        acceptable_destinations=["LAX"] if not p.get("route_match", True) else (["FUK", "KIX"] if p.get("flexibility_days", 0) >= 2 else ["FUK"]),
        desired_departure_date="2027-05-30", departure_time_window=["08:00", "22:00"],
        checked_bags=party if index % 3 == 1 else 0,
        assistance_required=index % 14 == 11,
        membership_active=bool(p.get("membership_active", False) or index % 14 in (2, 6)),
        existing_membership_days_remaining=120,
        change_scenario=("cannot_travel" if index % 7 == 0 else "date_uncertain" if index % 7 == 3 else "unchanged"),
        repeat_membership_eligible=True,
    )
    return p


def initial_world(person: dict, fare: float, fee: float, variant: str = "A") -> dict:
    for value in (fare, fee):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0 or value > 10000:
            raise ValueError("Price must be finite and within 0..10000")
    pid = person["customer_id"]
    return {
        "world_id": f"{pid}-{variant}", "person": copy.deepcopy(person), "stage_index": 0,
        "offer_config": {"member_base_fare": fare, "membership_fee": fee, "mandatory_fees": 250,
                         "membership_term_days": 365, "checked_bag_fee": 80, "regular_base_fare": 600},
        "state": {"remaining_budget": float(person["total_budget"]), "membership_active": person["membership_active"],
                  "membership_fee_paid": 0., "joined_this_run": False, "booking": None, "booking_cancelled": False,
                  "ticket_spend": 0., "refund_received": 0., "history": [], "renewal_intention": None},
    }


def _offers(world, day):
    p, state, config = world["person"], world["state"], world["offer_config"]
    # This future schedule belongs to the environment. Only this round is exposed.
    regular = {28: 600, 14: 650, 7: 800}[day]
    member_available = {28: 4, 14: 0, 7: 1}[day]
    regular_available = {28: 8, 14: 6, 7: 2}[day]
    party = p["party_size"]
    baggage = config["checked_bag_fee"] * p["checked_bags"]
    alternatives = []
    for member in (False, True):
        base = config["member_base_fare"] if member else regular
        holder_base = base
        companions_base = (party - 1) * regular
        total = holder_base + companions_base + party * config["mandatory_fees"] + baggage
        action = "BUY_MEMBER" if member else "BUY_REGULAR"
        option = {"id": "member" if member else "regular", "action": action,
                  "origin": "HKG", "destination": "FUK", "departure_date": "2027-05-30", "departure_time": "10:30",
                  "day_offset": 0, "party_size": party, "price": total, "currency": "HKD",
                  "price_breakdown": {"holder_base_fare": holder_base, "companions_base_fare": companions_base,
                                      "mandatory_fees": party * config["mandatory_fees"], "baggage": baggage},
                  "member_seats_available": member_available, "total_seats_available": regular_available,
                  "checked_bags_included": p["checked_bags"], "assistance_confirmed": day >= 14,
                  "cancellation_terms": {"refundable_tax_per_person": 150, "cancellation_fee_per_booking": 100,
                                         "base_fare_refundable": False, "baggage_refundable": False}}
        alternatives.append(option)
    alt = copy.deepcopy(alternatives[0])
    alt.update(id="alternative", destination="KIX", departure_date="2027-05-31", departure_time="18:30",
               day_offset=1, total_seats_available=5)
    alt["price_breakdown"]["holder_base_fare"] -= 100
    alt["price_breakdown"]["companions_base_fare"] = (party - 1) * (regular - 100)
    alt["price"] = sum(alt["price_breakdown"].values())
    alternatives.append(alt)
    return alternatives


def _illegal_reason(option, world, day):
    p, s = world["person"], world["state"]
    if s["booking"]:
        return "ALREADY_BOOKED"
    if option["destination"] not in p["acceptable_destinations"]:
        return "ROUTE_MISMATCH"
    if abs(option["day_offset"]) > p["flexibility_days"]:
        return "DATE_MISMATCH"
    if day + option["day_offset"] < p["minimum_notice_days"]:
        return "INSUFFICIENT_NOTICE"
    if not p["departure_time_window"][0] <= option["departure_time"] <= p["departure_time_window"][1]:
        return "TIME_MISMATCH"
    if p["assistance_required"] and not option["assistance_confirmed"]:
        return "ASSISTANCE_NOT_CONFIRMED"
    if option["total_seats_available"] < p["party_size"]:
        return "INSUFFICIENT_PARTY_SEATS"
    if option["action"] == "BUY_MEMBER" and not s["membership_active"]:
        return "MEMBERSHIP_REQUIRED"
    if option["action"] == "BUY_MEMBER" and option["member_seats_available"] < 1:
        return "MEMBER_SOLD_OUT"
    if option["price"] > s["remaining_budget"]:
        return "INSUFFICIENT_BUDGET"
    return None


def context_for(world):
    stage = STAGES[world["stage_index"]]
    p, s, config = world["person"], world["state"], world["offer_config"]
    # No future quote schedule or airline financial objective enters this view.
    visible_person = {key: copy.deepcopy(value) for key, value in p.items() if key != "change_scenario"}
    if not p["membership_active"]:
        visible_person["existing_membership_days_remaining"] = None
    context = {
        "world_id": world["world_id"], "stage": stage, "source": "assumed_customer_journey",
        "person": visible_person, "state": copy.deepcopy(s),
        "response_language": RESPONSE_LANGUAGE, "currency": CURRENCY, "output_contract": CONTRACT_VERSION,
        "budget_scope": "The whole party's available budget for one detailed trip, including any new membership fee. Future term trips are expectations, not funded transactions.",
        "membership": {**config, "coverage": ["HKG-FUK", "HKG-KIX"], "personal_nontransferable": True,
                       "companions_require_regular_fares": True, "seat_availability_guaranteed": False,
                       "no_automatic_renewal": True, "membership_fee_nonrefundable": True,
                       "expected_availability_is_assumption": p["perceived_availability"]},
        "allowed_actions": [], "legal_options": [], "unavailable_options": [],
    }
    if stage == "subscription":
        context["allowed_actions"] = ["KEEP_MEMBERSHIP"] if s["membership_active"] else ["DECLINE"]
        if not s["membership_active"] and config["membership_fee"] <= s["remaining_budget"]:
            context["allowed_actions"].append("JOIN_PASS")
            context["legal_options"] = [{"id": "pass", "action": "JOIN_PASS", "price": config["membership_fee"], "term_days": 365, "currency": CURRENCY}]
        member_total = config["member_base_fare"] + (p["party_size"] - 1) * 600 + p["party_size"] * 250 + p["checked_bags"] * 80
        regular_total = p["party_size"] * 850 + p["checked_bags"] * 80
        new_fee = 0 if s["membership_active"] else config["membership_fee"]
        context["current_quote_comparison"] = {
            "currency": CURRENCY, "whole_party_regular_trip": regular_total,
            "whole_party_member_trip": member_total, "membership_fee_due_now": new_fee,
            "new_membership_plus_member_trip": new_fee + member_total,
            "saving_on_one_trip_before_membership_fee": regular_total - member_total,
            "saving_on_one_trip_after_new_membership_fee": regular_total - member_total - new_fee,
            "budget_after_fee_and_member_trip": s["remaining_budget"] - new_fee - member_total,
            "scope": "Illustrative D28 main-itinerary totals including required baggage. Eligibility and seats must still be checked at booking; future savings are not guaranteed.",
        }
        context["upcoming_trip_reference"] = {"regular_total_per_person_excluding_baggage": 850,
                                                "member_total_for_holder_excluding_baggage": config["member_base_fare"] + 250,
                                                "current_seats_not_reserved": True}
    elif stage.startswith("quote_"):
        day = int(stage[7:])
        context["days_to_departure"] = day
        context["allowed_actions"] = ["KEEP_BOOKING"] if s["booking"] else ["DECLINE"] + (["WAIT"] if day > 7 else [])
        for option in _offers(world, day):
            issue = _illegal_reason(option, world, day)
            if issue:
                context["unavailable_options"].append({**option, "unavailable_reason": issue})
            else:
                context["legal_options"].append(option)
                if option["action"] not in context["allowed_actions"]:
                    context["allowed_actions"].append(option["action"])
        context["waiting_disclosure"] = "Later fares and availability are unknown. WAIT gives no reservation or price guarantee."
    elif stage == "plan_change":
        context["days_to_departure"] = 3
        context["changed_circumstances"] = p["change_scenario"]
        if s["booking"]:
            terms = s["booking"]["cancellation_terms"]
            refund = max(0, p["party_size"] * terms["refundable_tax_per_person"] - terms["cancellation_fee_per_booking"])
            context["allowed_actions"] = ["KEEP_BOOKING", "CANCEL_BOOKING"]
            context["legal_options"] = [{"id": "cancel", "action": "CANCEL_BOOKING", "refund": refund,
                                          "subscription_refund": 0, "cancellation_terms": terms}]
        else:
            context["allowed_actions"] = ["DECLINE"]
    else:
        context["allowed_actions"] = ["RENEW_INTENT", "DO_NOT_RENEW"] if s["membership_active"] else ["CONSIDER_LATER", "DECLINE"]
        context["term_outcome"] = {"membership_fee_paid_this_run": s["membership_fee_paid"], "ticket_spend": s["ticket_spend"],
                                    "refund_received": s["refund_received"], "travel_completed": bool(s["booking"] and not s["booking_cancelled"]),
                                    "future_period_trips_expected": p["expected_trips"], "renewal_intention_only_no_charge": True,
                                    "scope": "One detailed journey; other annual trips are expectations, not fabricated transactions."}
    return context


def packet_for(world):
    context = context_for(world)
    context_hash = digest(context)
    return {"packet_id": f"{world['world_id']}:{STAGES[world['stage_index']]}",
            "world_id": world["world_id"], "stage_index": world["stage_index"],
            "prompt_version": PROMPT_VERSION, "system_prompt_sha256": hashlib.sha256(PROMPT.read_bytes()).hexdigest(),
            "state_sha256": digest(world),
            "context_sha256": context_hash, "context": context}


def validate_decision(decision, context):
    if not isinstance(decision, dict) or decision.get("action") not in context["allowed_actions"]:
        raise ValueError("Action is not legal at this stage")
    action, oid = decision["action"], decision.get("option_id")
    option = next((x for x in context["legal_options"] if x["id"] == oid), None)
    option_actions = {"JOIN_PASS", "BUY_MEMBER", "BUY_REGULAR", "CANCEL_BOOKING"}
    if action in option_actions:
        if option is None or option["action"] != action:
            raise ValueError("Option is not legal for this action")
        if action != "CANCEL_BOOKING" and option["price"] > context["state"]["remaining_budget"]:
            raise ValueError("Budget exceeded")
    elif oid is not None:
        raise ValueError("Non-option action must have option_id null")
    return {"action": action, "option_id": oid, "reason_code": str(decision.get("reason_code", "UNSPECIFIED"))[:80],
            "reason": str(decision.get("reason", ""))[:1200], "confidence": decision.get("confidence", "medium") if decision.get("confidence", "medium") in ("low", "medium", "high") else "low"}


def apply_decision(world, decision):
    context = context_for(world)
    clean = validate_decision(decision, context)
    state = world["state"]
    action = clean["action"]
    option = next((x for x in context["legal_options"] if x["id"] == clean["option_id"]), None)
    if action == "JOIN_PASS":
        if state["membership_active"] or state["membership_fee_paid"]:
            raise ValueError("Membership cannot be charged twice")
        state["remaining_budget"] -= option["price"]
        state["membership_fee_paid"] += option["price"]
        state["membership_active"] = state["joined_this_run"] = True
    elif action in ("BUY_MEMBER", "BUY_REGULAR"):
        if state["booking"]:
            raise ValueError("Trip already booked")
        state["remaining_budget"] -= option["price"]
        state["ticket_spend"] += option["price"]
        state["booking"] = copy.deepcopy(option)
    elif action == "CANCEL_BOOKING":
        state["remaining_budget"] += option["refund"]
        state["refund_received"] += option["refund"]
        state["booking_cancelled"] = True
        state["cancelled_booking"] = state["booking"]
        state["booking"] = None
    elif action in ("RENEW_INTENT", "DO_NOT_RENEW", "CONSIDER_LATER"):
        state["renewal_intention"] = action
    state["history"].append({"stage": context["stage"], **clean})
    world["stage_index"] += 1
    if state["remaining_budget"] < -1e-8:
        raise ValueError("Negative budget after transition")
    return clean


def deterministic(context):
    allowed = context["allowed_actions"]
    action, oid, reason = allowed[0], None, "Follow the supplied current state and feasible options."
    if context["stage"] == "subscription" and "JOIN_PASS" in allowed:
        p = context["person"]
        m = context["membership"]
        benefit = p["expected_trips"] * p["perceived_availability"] * max(0, 600 - m["member_base_fare"])
        upcoming = m["member_base_fare"] + 250 + (p["party_size"] - 1) * 850 + p["checked_bags"] * 80
        if benefit > m["membership_fee"] and context["state"]["remaining_budget"] >= m["membership_fee"] + upcoming and p["route_match"]:
            action, oid, reason = "JOIN_PASS", "pass", "Assumed usable savings exceed the fee while preserving the upcoming trip budget."
    elif context["stage"].startswith("quote_") and context["legal_options"]:
        chosen = min(context["legal_options"], key=lambda x: x["price"])
        action, oid, reason = chosen["action"], chosen["id"], "Choose the lowest full payable price among currently feasible itineraries."
    elif context["stage"].startswith("quote_") and "WAIT" in allowed:
        action, reason = "WAIT", "No currently feasible option; wait without assuming a future discount."
    elif context["stage"] == "plan_change" and context["changed_circumstances"] == "cannot_travel" and "CANCEL_BOOKING" in allowed:
        action, oid, reason = "CANCEL_BOOKING", "cancel", "Cannot travel; recover only the explicitly refundable taxes net of the cancellation fee."
    elif context["stage"] == "term_end":
        if "RENEW_INTENT" in allowed:
            action = "RENEW_INTENT" if context["term_outcome"]["travel_completed"] and context["person"]["expected_trips"] >= 3 else "DO_NOT_RENEW"
        reason = "Renewal is an intention based on this journey and future expectations; no fee is charged."
    return {"action": action, "option_id": oid, "reason_code": "DETERMINISTIC_RULE", "reason": reason, "confidence": "medium"}


def _save(path, value):
    target = Path(path)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(target)


def export_suite(output: Path | str, pilot=True, seed=117):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    if (output / "state.json").exists():
        raise ValueError("Suite already exists; resume it instead of overwriting decisions")
    offers = [(0, 199), (100, 599)] if pilot else [(p, v) for p in (0, 30, 70, 100) for v in (199, 599)]
    worlds = [initial_world(enrich(p, i), fare, fee, f"P{fare}-V{fee}") for i, p in enumerate(population(14, seed)) for fare, fee in offers]
    suite = {"suite_id": "journey-" + uuid.uuid4().hex[:12], "source": "codex_subagent_pilot", "prompt_version": PROMPT_VERSION,
             "system_prompt_sha256": hashlib.sha256(PROMPT.read_bytes()).hexdigest(),
             "seed": seed, "counterfactual_design": {"persons": 14, "offers": offers, "same_person_across_offers": True}, "worlds": worlds}
    _save(output / "state.json", suite)
    (output / "system_prompt.txt").write_text(PROMPT.read_text(), encoding="utf-8")
    export_pending(output)
    return {"suite_id": suite["suite_id"], "worlds": len(worlds), "packets": str(output / "pending.jsonl")}


def require_current_suite(output, suite):
    """Reject continuation across prompt contracts; historical reports stay readable."""
    current_hash = hashlib.sha256(PROMPT.read_bytes()).hexdigest()
    frozen_prompt = Path(output) / "system_prompt.txt"
    if (suite.get("prompt_version") != PROMPT_VERSION
            or suite.get("system_prompt_sha256") != current_hash
            or not frozen_prompt.is_file()
            or hashlib.sha256(frozen_prompt.read_bytes()).hexdigest() != current_hash):
        raise ValueError("Journey suite uses a different or unverified prompt contract. "
                         "Create a new suite; historical results remain available for reading.")


def export_pending(output):
    output = Path(output)
    suite = json.loads((output / "state.json").read_text())
    require_current_suite(output, suite)
    pending = [packet_for(w) for w in suite["worlds"] if w["stage_index"] < len(STAGES)]
    batch = max((p["stage_index"] for p in pending), default=len(STAGES))
    content = "".join(canonical(p) + "\n" for p in pending)
    (output / "pending.jsonl").write_text(content, encoding="utf-8")
    # Immutable per-batch snapshots remain available after pending advances.
    path = output / f"packets-stage-{batch}.jsonl"
    if not path.exists():
        path.write_text(content, encoding="utf-8")
    return len(pending)


def import_responses(output, responses):
    from .audit import Audit
    from .output_contract import validate_english_output
    output = Path(output)
    suite = json.loads((output / "state.json").read_text())
    require_current_suite(output, suite)
    audit = Audit("codex_subagent_pilot", {"prompt_version": suite["prompt_version"], "suite_path": str(output),
                                           "worlds": len(suite["worlds"])}, run_id=suite["suite_id"], resume=True)
    pending = {p["packet_id"]: p for p in (json.loads(line) for line in (output / "pending.jsonl").read_text().splitlines() if line)}
    raw_batch = Path(responses).read_text()
    batch_id = uuid.uuid4().hex[:12]
    audit.append({"event": "external_response_batch_received", "source": "codex_subagent_pilot", "batch_id": batch_id,
                  "raw_response_text": raw_batch, "model": "codex_session_model_not_exposed", "usage": None,
                  "latency_ms": None, "cache_hit": False})
    world_by_id = {w["world_id"]: w for w in suite["worlds"]}
    seen = set()
    records = []
    try:
        incoming = [json.loads(line) for line in raw_batch.splitlines() if line.strip()]
        for item in incoming:
            pid = item.get("packet_id")
            if pid not in pending or pid in seen:
                raise ValueError("Unknown, already applied, or duplicated packet_id")
            packet = pending[pid]
            if item.get("context_sha256") != packet["context_sha256"] or digest(packet["context"]) != packet["context_sha256"]:
                raise ValueError("Response does not match immutable context hash")
            world = world_by_id[packet["world_id"]]
            if packet["stage_index"] != world["stage_index"]:
                raise ValueError("Packet stage has already advanced")
            # v2 pilot packets predate state hashes. Their exported state still
            # binds the transition; context builder fixes never rewrite packets.
            if packet.get("state_sha256"):
                unchanged = digest(world) == packet["state_sha256"]
            else:
                unchanged = packet["context"]["state"] == world["state"]
            if not unchanged:
                raise ValueError("World changed after packet export")
            validate_english_output(item.get("decision"))
            validate_decision(item.get("decision"), packet["context"])
            clean = apply_decision(world, item.get("decision"))
            seen.add(pid)
            record = {"source": "codex_subagent_pilot", "packet": packet, "raw_response": item,
                      "validated_decision": clean, "validation": "passed", "state_after": copy.deepcopy(world["state"]),
                      "model": item.get("model", "codex_session_model_not_exposed"), "usage": item.get("usage"),
                      "latency_ms": item.get("latency_ms"), "cache_hit": False, "batch_id": batch_id}
            records.append(record)
            audit.append({"event": "external_decision_validated", **record})
    except Exception as error:
        audit.append({"event": "external_batch_rejected", "batch_id": batch_id, "validation": "failed",
                      "error_type": type(error).__name__, "error": str(error), "state_committed": False})
        audit.update(status="awaiting_corrected_responses", last_error=str(error))
        raise
    # Atomic state commit after all supplied transitions validate.
    _save(output / "state.json", suite)
    with (output / "audit.jsonl").open("a", encoding="utf-8") as f:
        for record in records:
            f.write(canonical(record) + "\n")
    remaining = export_pending(output)
    _save(output / "summary.json", summarize(suite))
    audit.append({"event": "external_batch_committed", "batch_id": batch_id, "state_committed": True, "imported": len(records)})
    audit.update(status="completed" if remaining == 0 else "awaiting_responses", summary=summarize(suite))
    return {"imported": len(records), "pending_worlds": remaining, "complete": remaining == 0}


def summarize(suite):
    worlds = suite["worlds"]
    return {"suite_id": suite["suite_id"], "source": suite["source"], "prompt_version": suite.get("prompt_version", "unknown"),
            "worlds": len(worlds), "completed_worlds": sum(w["stage_index"] == len(STAGES) for w in worlds),
            "joined": sum(w["state"]["joined_this_run"] for w in worlds),
            "booked": sum(w["state"]["ticket_spend"] > 0 for w in worlds),
            "cancelled": sum(w["state"]["booking_cancelled"] for w in worlds),
            "renewal_intent": sum(w["state"]["renewal_intention"] == "RENEW_INTENT" for w in worlds),
            "limitations": ["Synthetic role-play pilot, not observed customer conversion.", "One detailed journey per world; expected annual trips do not create unobserved transactions.", "Counterfactual worlds have separate scenario inventory; no live ticketing."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    export = sub.add_parser("export")
    export.add_argument("--output", type=Path, required=True)
    export.add_argument("--full", action="store_true")
    export.add_argument("--seed", type=int, default=117)
    imp = sub.add_parser("import")
    imp.add_argument("--output", type=Path, required=True)
    imp.add_argument("--responses", type=Path, required=True)
    pending = sub.add_parser("pending")
    pending.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = export_suite(args.output, not args.full, args.seed) if args.command == "export" else import_responses(args.output, args.responses) if args.command == "import" else {"pending": export_pending(args.output)}
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()

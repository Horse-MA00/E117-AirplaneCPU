"""Isolated, complimentary-access market for ticket-base-revenue experiments.

The shared engine still owns eligibility, chronological inventory, D28/D14/D7
releases, cancellations and integer-cent accounting. Only this experiment omits
membership, taxes, baggage charges and costs. Its objective is revenue, not profit.
"""
from __future__ import annotations

import copy

from backend.scoped_market import create_scoped_market
from backend.shared_market import _digest, _money, summarize, next_observation as shared_next_observation

VERSION = "fare-only-market-v1"
ZERO_CHARGES = (
    "mandatory_fees", "checked_bag_fee", "checked_bag_cost",
    "incremental_passenger_cost", "cancellation_fee",
    "membership_service_cost", "program_cost",
)


def create_world(scope, fare, customers, seed, release_fraction, offer_enabled=True):
    """Create a policy-independent starting world with free member eligibility.

    The normal-fare control gets the same complimentary status and customers,
    but has no discount inventory. No registration or renewal decisions are
    generated. Companions retain the existing one-discounted-seat-per-party rule.
    The supplied scope and the original product defaults are never mutated.
    """
    isolated_scope = copy.deepcopy(scope)
    isolated_scope["mandatory_fees"] = 0
    config = {key: 0 for key in ZERO_CHARGES}
    config["customer_count"] = customers
    policy = {"name": "FARE_ONLY" if offer_enabled else "NO_OFFER",
              "enabled": offer_enabled, "member_fare": fare,
              "membership_fee": 0, "release_fraction": release_fraction}
    state = create_scoped_market(isolated_scope, config, seed, policy)
    state["fare_only_version"] = VERSION
    state["config"]["experiment_scope"] = "ticket_base_revenue_only"
    for customer in state["customers"].values():
        customer.update(membership_started=0,
                        membership_expires=state["config"]["horizon_days"],
                        membership_fee_cents=0, joined_this_run=False)
        customer["person"]["membership_active"] = True
    state["events"] = [event for event in state["events"]
                       if event.get("stage") not in ("subscription", "term_end")]
    for i, event in enumerate(state["events"]):
        event["event_id"] = f"E{i:06d}"
    # Recompute after removing subscription/renewal and granting identical free
    # eligibility. Price, policy name and enabled flag are deliberately excluded.
    state["exogenous_sha256"] = _digest({
        "version": VERSION, "seed": seed, "events": state["events"],
        "customers": state["customers"], "flights": state["flights"],
        "config": state["config"],
    })
    return state


def next_observation(state):
    """Disclose this sandbox's actual checkout terms without an airline objective."""
    observation = shared_next_observation(state)
    if observation is None:
        return None
    # Idempotent at a pending decision, including a retried provider call.
    if any(option.get("action") == "BUY_MEMBER" for option in observation.get("options", [])):
        exposure = state["member_offer_exposure"]
        for key, value in (("packet_ids", observation["packet_id"]),
                           ("bookable_packet_ids", observation["packet_id"]),
                           ("customer_ids", observation["customer_id"])):
            if value not in exposure[key]:
                exposure[key].append(value)
    observation["checkout_terms"] = {
        "complimentary_member_access": True,
        "membership_payment_required": False,
        "membership_fee": 0,
        "taxes_and_fuel_surcharges": 0,
        "baggage_charges": 0,
        "price_scope": "Each quoted total is the complete base-ticket payment for your entire party in this sandbox.",
        "companions_rule": "Only the holder receives the member fare; companions pay normal base fares.",
        "cancellation_rule": "Base-ticket payments are nonrefundable; there are no additional cancellation charges.",
        "future_membership_charges": "None. There is no membership subscription or renewal in this experiment.",
    }
    return observation


def result(state):
    """Report net retained ticket-base receipts across both customer populations.

    Includes accepted tickets later cancelled because the shared engine's base
    fares are nonrefundable. Flown counts are reported separately. Pre-snapshot
    occupancy has sunk receipts outside every compared policy's ledger.
    """
    if state.get("fare_only_version") != VERSION:
        raise ValueError("Expected a fare-only market")
    summary = summarize(state)
    ledger = summary["ledger"]
    bookings = list(state["bookings"].values())
    foreground = [booking for booking in bookings if booking["customer_id"] is not None]
    background = [booking for booking in bookings if booking["customer_id"] is None]
    exposure = state.get("member_offer_exposure", {})
    cents = state["ledger_cents"]
    ticket_cents = cents["normal_base_revenue"] + cents["member_base_revenue"]

    def retained(group):
        return _money(sum(b["normal_base_cents"] + b["member_base_cents"] for b in group))

    def count(group, field="party_size", status=None):
        return sum(b[field] for b in group if status is None or b["status"] == status)

    checks = {**summary["checks"],
              "ticket_revenue_reconciled": ticket_cents == sum(
                  b["normal_base_cents"] + b["member_base_cents"] for b in bookings),
              "no_membership_or_extras": all(cents[key] == 0 for key in (
                  "membership_revenue", "ancillary_revenue", "cancellation_revenue",
                  "mandatory_liability", "mandatory_remitted", "passenger_cost",
                  "ancillary_cost", "membership_service_cost", "program_cost")),
              "no_subscription_events": not any(e.get("stage") in ("subscription", "term_end")
                                                 for e in state["events"])}
    return {
        "version": VERSION, "seed": state["seed"], "complete": summary["complete"],
        "exogenous_sha256": state["exogenous_sha256"],
        "policy": copy.deepcopy(state["policy"]),
        "base_ticket_revenue": _money(ticket_cents),
        "ticket_revenue": _money(ticket_cents),
        "regular_base_revenue": ledger["normal_base_revenue"],
        "member_base_revenue": ledger["member_base_revenue"],
        "agent_base_revenue": retained(foreground),
        "background_base_revenue": retained(background),
        "buyers": len({b["customer_id"] for b in foreground}),
        "member_buyers": len({b["customer_id"] for b in foreground if b["member_seats"]}),
        "regular_buyers": len({b["customer_id"] for b in foreground if b["normal_seats"]}),
        "tickets": count(foreground),
        "member_tickets": count(foreground, "member_seats"),
        "regular_tickets": count(foreground, "normal_seats"),
        "all_tickets": count(bookings),
        "tickets_sold": count(bookings),
        "background_tickets": count(background),
        "fulfilled_buyers": len({b["customer_id"] for b in foreground if b["status"] == "flown"}),
        "fulfilled_tickets": count(foreground, status="flown"),
        "member_flown": count(foreground, "member_seats", "flown"),
        "all_flown_tickets": count(bookings, status="flown"),
        "tickets_flown": count(bookings, status="flown"),
        "cancelled_tickets": count(foreground, status="cancelled"),
        "all_cancelled_tickets": count(bookings, status="cancelled"),
        "tickets_cancelled": count(bookings, status="cancelled"),
        "member_offer_observations": len(exposure.get("packet_ids", [])),
        "member_offer_customers": len(exposure.get("customer_ids", [])),
        "member_bookable_observations": len(exposure.get("bookable_packet_ids", [])),
        "member_supply_exposure": sum(c["issued"] for f in state["flights"].values()
                                      for c in f["quota_cohorts"]),
        "background_requested": summary["background_requested"],
        "background_denied": summary["background_denied"],
        "ledger": ledger, "flights": summary["flights"], "checks": checks,
        "assumptions": [
            "Ticket-base-revenue sandbox: no pass fee, taxes, baggage charges or costs; this is not profit.",
            "All panel customers have complimentary eligibility; no purchase or renewal of membership is simulated.",
            "One discounted seat per household; companions still pay the normal base fare.",
            "Total new ticket receipts include regular panel and background sales, so normal-fare displacement is counted.",
            "Accepted ticket counts include later cancellations; base fares remain nonrefundable and flown seats are reported separately.",
            "Existing pre-snapshot occupancy has sunk receipts outside this comparison. Future member trips are not modelled.",
            "The frozen NHPP and chronological D28/D14/D7 release rules are reused without retraining.",
        ],
    }

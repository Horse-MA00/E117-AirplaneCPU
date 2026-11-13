"""Financial, temporal and information-boundary tests for the shared market."""
import copy
import json
import unittest
from unittest.mock import patch

from backend.shared_market import (
    _automatic, apply_decision, create_market, deterministic_decision,
    next_observation, summarize,
)


def run_market(state):
    while (observation := next_observation(state)) is not None:
        apply_decision(state, deterministic_decision(observation))
    return summarize(state)


def quoted_market(party=1):
    state = create_market({"flight_count": 6, "customer_count": 1}, 117,
                          {"member_fare": 30, "membership_fee": 199})
    observation = next_observation(state)
    customer = state["customers"][observation["customer_id"]]
    customer["person"].update(party_size=party, checked_bags=party, minimum_notice_days=0)
    customer.update(membership_started=0, membership_expires=365,
                    budget_cents=10000000, initial_budget_cents=10000000)
    for flight in state["flights"].values():
        if flight["active"]:
            flight["member_remaining"] = 20
            flight["protection_remaining"] = 0
    observation = next_observation(state)
    apply_decision(state, {"action": "KEEP_MEMBERSHIP", "option_id": None})
    observation = next_observation(state)
    assert observation["stage"] == "quote"
    return state, customer, observation


class SharedMarketTests(unittest.TestCase):
    def test_policy_pairing_and_json_resume(self):
        config = {"flight_count": 6, "customer_count": 6}
        baseline = create_market(config, 117, {"name": "NO_OFFER"})
        candidate = create_market(config, 117, {"name": "candidate", "membership_fee": 199})
        self.assertEqual(baseline["exogenous_sha256"], candidate["exogenous_sha256"])
        self.assertEqual(baseline["events"], candidate["events"])
        first = next_observation(candidate)
        checkpoint = json.loads(json.dumps(candidate))
        self.assertEqual(first, next_observation(checkpoint))
        r1, r2 = run_market(candidate), run_market(checkpoint)
        self.assertEqual(r1, r2)
        rb = run_market(baseline)
        self.assertEqual(rb["background_requested"], r1["background_requested"])
        self.assertTrue(all(r1["checks"].values()))
        self.assertTrue(all(rb["checks"].values()))
        self.assertTrue(r1["complete"])

    def test_global_chronology_and_multiple_actual_journeys(self):
        state = create_market({"flight_count": 9, "customer_count": 8}, 305)
        result = run_market(state)
        times = [r["day"] for r in state["records"]]
        self.assertEqual(times, sorted(times))
        actors = [r["customer_id"] for r in state["records"]]
        self.assertGreater(sum(a != b for a, b in zip(actors, actors[1:])), 8)
        self.assertTrue(any(sum(state["bookings"][bid]["status"] == "flown" for bid in c["bookings"]) >= 2 for c in state["customers"].values()))
        self.assertEqual(result["forecast_calls"], 27)

    def test_party_atomicity_and_single_holder_discount(self):
        state, customer, observation = quoted_market(party=3)
        option = next(o for o in observation["options"] if o["action"] == "BUY_MEMBER")
        flight = state["flights"][option["flight_id"]]
        old = (flight["occupied"], flight["member_remaining"], customer["budget_cents"])
        expected = 30 + flight["base_fare"] * 2 + 250 * 3 + 80 * 3
        self.assertEqual(option["price"], expected)
        record = apply_decision(state, {"action": "BUY_MEMBER", "option_id": option["id"]})
        self.assertEqual(flight["occupied"], old[0] + 3)
        self.assertEqual(flight["member_remaining"], old[1] - 1)
        self.assertEqual(customer["budget_cents"], old[2] - round(expected * 100))
        self.assertEqual(record["financial_delta"]["member_base_revenue"], 30)
        self.assertEqual(record["financial_delta"]["normal_base_revenue"], 2 * flight["base_fare"])
        self.assertTrue(all(summarize(state)["checks"].values()))

    def test_stale_option_rejected_when_party_supply_disappears(self):
        state, _, observation = quoted_market(party=3)
        option = next(o for o in observation["options"] if o["action"] == "BUY_MEMBER")
        flight = state["flights"][option["flight_id"]]
        flight["occupied"] = flight["capacity"] - 2
        before = copy.deepcopy(state)
        with self.assertRaisesRegex(ValueError, "Illegal action|Invalid option"):
            apply_decision(state, {"action": "BUY_MEMBER", "option_id": option["id"]})
        self.assertEqual(state, before)

    def test_expiry_required_at_departure_and_wait_does_not_reserve(self):
        state, customer, observation = quoted_market()
        customer["membership_expires"] = state["day"] + 5
        observation = next_observation(state)
        self.assertNotIn("BUY_MEMBER", observation["allowed_actions"])
        supply = {fid: (f["occupied"], f["member_remaining"]) for fid, f in state["flights"].items()}
        apply_decision(state, {"action": "WAIT", "option_id": None})
        self.assertEqual(supply, {fid: (f["occupied"], f["member_remaining"]) for fid, f in state["flights"].items()})

    def test_cancellation_refund_ledger_and_no_cost_for_unflown_party(self):
        state, customer, observation = quoted_market(party=3)
        option = next(o for o in observation["options"] if o["action"] == "BUY_MEMBER")
        record = apply_decision(state, {"action": "BUY_MEMBER", "option_id": option["id"]})
        bid = record["booking_id"]
        occasion = customer["occasions"][0]
        event = {"event_id": "TEST-CANCEL", "kind": "decision", "stage": "plan_change",
                 "customer_id": customer["person"]["customer_id"], "occasion_id": occasion["occasion_id"], "time": state["day"] + 1}
        state["events"].insert(state["cursor"], event)
        observation = next_observation(state)
        self.assertEqual(observation["options"][0]["refund"], 650)
        apply_decision(state, {"action": "CANCEL_BOOKING", "option_id": bid})
        self.assertEqual(state["bookings"][bid]["status"], "cancelled")
        self.assertEqual(state["ledger_cents"]["mandatory_liability"], 0)
        self.assertEqual(state["ledger_cents"]["cancellation_revenue"], 10000)
        _automatic(state, {"kind": "departure", "flight_id": option["flight_id"]})
        self.assertEqual(state["ledger_cents"]["passenger_cost"], 0)
        self.assertEqual(state["ledger_cents"]["ancillary_cost"], 0)
        self.assertTrue(all(summarize(state)["checks"].values()))

    def test_future_truth_forecast_and_other_people_hidden(self):
        state = create_market({"flight_count": 6, "customer_count": 3}, 303)
        observation = next_observation(state)
        text = json.dumps(observation)
        for forbidden in ("scenario_scoring_only", "change_scoring_only", "background_requested", "forecast", "ledger", "expected_demand", "latent_scale", "seed", "events"):
            self.assertNotIn('"' + forbidden + '"', text)
        before = copy.deepcopy(observation)
        for event in state["events"][state["cursor"] + 1:]:
            if event["kind"] == "background":
                event["base_fare"] *= 5
        self.assertEqual(next_observation(state), before)

    def test_truth_creation_never_consults_forecast(self):
        with patch("backend.shared_market.forecast", side_effect=AssertionError("Prediction must not generate truth")):
            state = create_market({"flight_count": 6, "customer_count": 1}, 77)
        self.assertGreater(sum(e["kind"] == "background" for e in state["events"]), 0)

    def test_no_double_booking_or_duplicate_membership_payment(self):
        state = create_market({"flight_count": 6, "customer_count": 6}, 117, {"membership_fee": 0, "member_fare": 0})
        result = run_market(state)
        self.assertTrue(result["checks"]["membership_charged_once"])
        for c in state["customers"].values():
            occasions = [state["bookings"][bid]["occasion_id"] for bid in c["bookings"]]
            self.assertEqual(len(occasions), len(set(occasions)))
        self.assertEqual(result["ledger"]["membership_revenue"], 0)

    def test_renewal_intention_is_not_a_cash_transaction(self):
        state = create_market({"flight_count": 6, "customer_count": 1}, 117, {"membership_fee": 0})
        while (o := next_observation(state)) is not None:
            if o["stage"] == "term_end":
                before = copy.deepcopy(state["ledger_cents"])
                self.assertTrue(o["term_outcome"]["renewal_intention_only_no_charge"])
                self.assertGreater(o["term_outcome"]["next_period_budget"], 0)
                action = "RENEW_INTENT" if "RENEW_INTENT" in o["allowed_actions"] else o["allowed_actions"][0]
                apply_decision(state, {"action": action, "option_id": None})
                self.assertEqual(before, state["ledger_cents"])
            else:
                apply_decision(state, deterministic_decision(o))

    def test_normal_sales_decrement_outstanding_protection(self):
        state, _, observation = quoted_market()
        option = next(o for o in observation["options"] if o["action"] == "BUY_REGULAR")
        flight = state["flights"][option["flight_id"]]
        flight["protection_remaining"] = 10
        apply_decision(state, {"action": "BUY_REGULAR", "option_id": option["id"]})
        self.assertEqual(flight["protection_remaining"], 9)

    def test_costs_full_term_and_personal_memory(self):
        state = create_market({"flight_count": 6, "customer_count": 3}, 117, {"membership_fee": 0, "member_fare": 0})
        saw_memory = False
        while (o := next_observation(state)) is not None:
            saw_memory |= bool(o["visible_state"]["recent_history"])
            for entry in o["visible_state"]["recent_history"]:
                self.assertNotIn("financial_delta", entry)
                self.assertLessEqual(entry["day"], o["day"])
            apply_decision(state, deterministic_decision(o))
        r = summarize(state)
        self.assertTrue(saw_memory)
        self.assertGreater(r["members"], 0)
        self.assertEqual(r["ledger"]["membership_service_cost"], 30 * r["members"])
        self.assertEqual(r["ledger"]["program_cost"], 1500)
        self.assertEqual(r["members"], r["charged_members_full_term_observed"])
        self.assertGreater(r["last_observed_calendar_day"], 365)
        self.assertEqual(r["ledger"]["contribution"], r["ledger"]["revenue_excluding_mandatory_fees"] - r["ledger"]["total_cost"])
        baseline = run_market(create_market({"flight_count": 6, "customer_count": 1}, 117, {"name": "NO_OFFER"}))
        self.assertEqual(baseline["ledger"]["program_cost"], 0)

    def test_late_opening_has_subscription_opportunity(self):
        state = create_market({"flight_count": 6, "customer_count": 1}, 117, {"membership_fee": 0, "open_day": 14})
        joined_day = None
        while (o := next_observation(state)) is not None:
            decision = deterministic_decision(o)
            if decision["action"] == "JOIN_PASS":
                joined_day = o["day"]
            apply_decision(state, decision)
        self.assertIsNotNone(joined_day)
        self.assertGreater(joined_day, min(f["departure_at"] for f in state["flights"].values()) - 15)

    def test_cancellation_legal_options_use_actual_flight_cutoff_boundary(self):
        for offset, legal in ((-1e-6, True), (0., False), (.01, False)):
            with self.subTest(offset=offset):
                state, customer, o = quoted_market()
                option = next(x for x in o["options"] if x["action"] == "BUY_REGULAR")
                record = apply_decision(state, {"action": "BUY_REGULAR", "option_id": option["id"]})
                flight = state["flights"][option["flight_id"]]
                event = {"event_id": "CUTOFF-CHECK", "kind": "decision", "stage": "plan_change",
                         "customer_id": customer["person"]["customer_id"], "occasion_id": customer["occasions"][0]["occasion_id"],
                         "time": flight["departure_at"] - 2 / 24 + offset}
                state["events"].insert(state["cursor"], event)
                o = next_observation(state)
                self.assertEqual("CANCEL_BOOKING" in o["allowed_actions"], legal)
                self.assertEqual(o["cancellation_status"]["available"], legal)
                if not legal:
                    self.assertEqual(o["allowed_actions"], ["KEEP_BOOKING"])
                    before = copy.deepcopy(state)
                    with self.assertRaisesRegex(ValueError, "Illegal action"):
                        apply_decision(state, {"action": "CANCEL_BOOKING", "option_id": record["booking_id"]})
                    self.assertEqual(state, before)
                    apply_decision(state, {"action": "KEEP_BOOKING", "option_id": None})
                    self.assertEqual(state["ledger_cents"]["refunds_paid"], 0)

    def test_regression_20261234_earlier_alternative_after_cancellation_cutoff(self):
        policies = [
            {"name": "NO_OFFER"},
            {"name": "FIXED", "member_fare": 70, "membership_fee": 399, "open_day": 14, "release_fraction": .5},
            {"name": "CANDIDATE", "member_fare": 30, "membership_fee": 199, "open_day": 28, "release_fraction": .75},
        ]
        for policy in policies:
            with self.subTest(policy=policy["name"]):
                state = create_market({"flight_count": 9, "customer_count": 14}, 20261234, policy)
                seen_late = False
                while (o := next_observation(state)) is not None:
                    if o.get("cancellation_status", {}).get("available") is False:
                        seen_late = True
                        self.assertNotIn("CANCEL_BOOKING", o["allowed_actions"])
                    apply_decision(state, deterministic_decision(o))
                result = summarize(state)
                self.assertTrue(seen_late)
                self.assertTrue(result["complete"])
                self.assertTrue(all(result["checks"].values()))


if __name__ == "__main__":
    unittest.main()

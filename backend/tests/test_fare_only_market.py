"""Revenue-only scenario boundaries, pairing and existing ledger invariants."""
import copy
import unittest

from backend.fare_only_market import create_world, next_observation, result, ZERO_CHARGES
from backend.initial_policy import flight_scope
from backend.shared_market import (
    DEFAULTS, _cancel, apply_decision, deterministic_decision,
)


class FareOnlyMarketTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scope = flight_scope("NET-HKG-KMQ-20270518", 28)

    def world(self, fare=70, customers=1, enabled=True, seed=117):
        return create_world(self.scope, fare, customers, seed, .5, offer_enabled=enabled)

    def ready(self, fare=70, party=1, wallet=10000):
        state = self.world(fare)
        cid = next(iter(state["customers"]))
        customer = state["customers"][cid]
        customer["person"].update(party_size=party, checked_bags=party, minimum_notice_days=0)
        customer.update(budget_cents=round(wallet * 100), initial_budget_cents=round(wallet * 100))
        customer["occasions"][0]["change_scoring_only"] = "unchanged"
        observation = next_observation(state)
        self.assertEqual(observation["stage"], "quote")
        return state, customer, observation

    def test_complimentary_access_does_not_mutate_scope_or_existing_defaults(self):
        original_scope, original_defaults = copy.deepcopy(self.scope), copy.deepcopy(DEFAULTS)
        state = self.world(customers=14)
        self.assertEqual(self.scope, original_scope)
        self.assertEqual(DEFAULTS, original_defaults)
        self.assertEqual(DEFAULTS["mandatory_fees"], 250)
        self.assertEqual(state["policy"]["membership_fee"], 0)
        self.assertTrue(all(state["config"][key] == 0 for key in ZERO_CHARGES))
        self.assertFalse(any(e.get("stage") in ("subscription", "term_end") for e in state["events"]))
        self.assertTrue(all(c["membership_expires"] > 28 and c["membership_fee_cents"] == 0
                            and not c["joined_this_run"] for c in state["customers"].values()))

    def test_low_wallet_can_buy_without_399_fee_or_250_surcharge(self):
        state, customer, observation = self.ready(fare=70, wallet=80)
        option = next(o for o in observation["options"] if o["action"] == "BUY_MEMBER")
        self.assertEqual(option["price"], 70)
        self.assertEqual(option["price_breakdown"]["mandatory_fees"], 0)
        self.assertEqual(option["price_breakdown"]["baggage"], 0)
        self.assertFalse(observation["checkout_terms"]["membership_payment_required"])
        apply_decision(state, {"action": "BUY_MEMBER", "option_id": option["id"]})
        self.assertEqual(customer["budget_cents"], 1000)
        self.assertEqual(customer["membership_fee_cents"], 0)
        self.assertEqual(result(state)["ticket_revenue"],
                         result(state)["background_base_revenue"] + 70)

    def test_companions_still_pay_regular_base_fare_with_no_extras(self):
        state, customer, observation = self.ready(fare=70, party=3)
        option = next(o for o in observation["options"] if o["action"] == "BUY_MEMBER")
        normal = state["flights"][self.scope["flight_id"]]["base_fare"]
        self.assertEqual(option["price"], 70 + 2 * normal)
        self.assertEqual(option["member_seats"], 1)
        self.assertEqual(option["normal_seats"], 2)
        self.assertEqual(option["price_breakdown"]["baggage"], 0)

    def test_zero_member_fare_can_sell_a_seat_but_earns_no_base_revenue(self):
        state, customer, observation = self.ready(fare=0, wallet=0)
        option = next(o for o in observation["options"] if o["action"] == "BUY_MEMBER")
        self.assertEqual(option["price"], 0)
        apply_decision(state, {"action": "BUY_MEMBER", "option_id": option["id"]})
        report = result(state)
        self.assertEqual(report["member_tickets"], 1)
        self.assertEqual(report["member_base_revenue"], 0)
        self.assertEqual(report["ticket_revenue"], report["regular_base_revenue"])
        self.assertTrue(all(report["checks"].values()))

    def test_normal_ticket_replacement_reduces_total_revenue(self):
        state, customer, observation = self.ready(fare=70)
        regular_world = copy.deepcopy(state)
        member = next(o for o in observation["options"] if o["action"] == "BUY_MEMBER")
        normal = next(o for o in observation["options"] if o["action"] == "BUY_REGULAR")
        apply_decision(state, {"action": "BUY_MEMBER", "option_id": member["id"]})
        apply_decision(regular_world, {"action": "BUY_REGULAR", "option_id": normal["id"]})
        member_result, normal_result = result(state), result(regular_world)
        self.assertEqual(member_result["ticket_revenue"] - normal_result["ticket_revenue"],
                         member["price"] - normal["price"])
        self.assertLess(member_result["ticket_revenue"], normal_result["ticket_revenue"])
        self.assertEqual(member_result["buyers"], normal_result["buyers"])

    def test_matched_worlds_retain_identical_demand_and_people(self):
        low = self.world(0, customers=3)
        high = self.world(900, customers=3)
        control = self.world(410, customers=3, enabled=False)
        self.assertEqual(low["exogenous_sha256"], high["exogenous_sha256"])
        self.assertEqual(low["exogenous_sha256"], control["exogenous_sha256"])
        self.assertEqual(low["events"], control["events"])
        self.assertEqual(low["customers"], control["customers"])
        self.assertNotEqual(low["exogenous_sha256"], self.world(0, customers=3, seed=218)["exogenous_sha256"])

    def test_cancellation_retains_base_revenue_without_extra_income(self):
        state, customer, observation = self.ready(fare=70)
        option = next(o for o in observation["options"] if o["action"] == "BUY_MEMBER")
        transition = apply_decision(state, {"action": "BUY_MEMBER", "option_id": option["id"]})
        before = result(state)["ticket_revenue"]
        _cancel(state, transition["booking_id"])
        after = result(state)
        self.assertEqual(after["ticket_revenue"], before)
        self.assertEqual(after["cancelled_tickets"], 1)
        self.assertEqual(after["tickets_flown"], 0)
        self.assertEqual(after["ledger"]["cancellation_revenue"], 0)
        self.assertTrue(all(after["checks"].values()))

    def test_completed_shared_market_retains_invariants_and_actual_exposure(self):
        state = self.world(fare=70, customers=14)
        while (observation := next_observation(state)) is not None:
            # A repeated pending read must not double-count exposure.
            again = next_observation(state)
            self.assertEqual(observation, again)
            apply_decision(state, deterministic_decision(observation))
        report = result(state)
        self.assertTrue(report["complete"])
        self.assertTrue(all(report["checks"].values()), report["checks"])
        self.assertEqual(report["ticket_revenue"],
                         round(report["regular_base_revenue"] + report["member_base_revenue"], 2))
        self.assertEqual(report["ticket_revenue"],
                         round(report["agent_base_revenue"] + report["background_base_revenue"], 2))
        self.assertEqual(report["tickets_sold"], report["tickets_flown"] + report["tickets_cancelled"])
        self.assertGreater(report["member_offer_observations"], 0)
        self.assertEqual(len(state["member_offer_exposure"]["packet_ids"]),
                         len(set(state["member_offer_exposure"]["packet_ids"])))


if __name__ == "__main__":
    unittest.main()

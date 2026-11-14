"""Member-only experiment integration without network calls or private DB writes."""
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from backend import adaptive_pricing as pricing
from backend import adaptive_store
from backend.thompson import PurchasePosterior
from llm_agent.adaptive_customers import DecisionClient
from llm_agent.weighted_population import population


def selected_scope():
    return dict(flight_id="TEST-HKG-KMQ", origin="HKG", destination="KMQ",
                departure_date="2027-05-18", departure_time="10:30", as_of_day=28,
                normal_base_fare=410., initial_member_fare=328., available_seats=80,
                releasable_seats=30, history=[], history_sha256="test-history",
                capacity=180, booked_seats=100, member_fare_cap_ratio=.8)


def buyer(i, weight=1 / 3):
    return dict(customer_id=f"BUYER-{i}", segment="student", eligible=True,
                base_fare_budget=1000., population_weight=weight)


def request(action="BUY_MEMBER", fallback="BUY_REGULAR"):
    return {"decision": {"action": action, "fallback_action": fallback,
                         "reason": "This ticket fits my trip.", "reason_code": "VALUE"}}


class SettlementTests(unittest.TestCase):
    def test_inventory_is_integer_and_fallback_is_accounted_once(self):
        selected = {**selected_scope(), "releasable_seats": 1, "available_seats": 3}
        result = pricing.settle([buyer(i) for i in range(3)], [request() for _ in range(3)], selected, 328, 117)
        self.assertEqual(result["member_intents"], 3)
        self.assertEqual(result["member_buyers"], 1)
        self.assertEqual(result["regular_buyers"], 2)
        self.assertEqual(result["revenue"], 328 + 2 * 410)
        self.assertEqual(result["remaining_quota"], 0)
        self.assertEqual(result["remaining_seats"], 0)
        self.assertEqual(result["inventory_denials"], 2)
        self.assertEqual(sum(row["base_fare"] for row in result["executions"]), result["revenue"])

    def test_physical_capacity_and_weighted_estimates_do_not_mint_seats(self):
        selected = {**selected_scope(), "releasable_seats": 1, "available_seats": 2}
        people = [buyer(0, .7), buyer(1, .2), buyer(2, .1)]
        result = pricing.settle(people, [request() for _ in people], selected, 200, 117)
        self.assertEqual(result["buyers"], 2)
        self.assertEqual(result["member_buyers"], 1)
        self.assertEqual(result["regular_buyers"], 1)
        self.assertEqual(result["revenue"], 610)
        self.assertNotEqual(result["weighted_revenue"], result["revenue"])
        self.assertEqual(result["remaining_seats"], 0)

    def test_invalid_or_unaffordable_actions_cannot_execute(self):
        selected = selected_scope()
        for person in [{**buyer(0), "eligible": False}, {**buyer(0), "base_fare_budget": 20}]:
            with self.assertRaises(ValueError):
                pricing.settle([person], [request()], selected, 328, 117)
        with self.assertRaises(ValueError):
            pricing.settle([buyer(0)], [request()], selected, None, 117)

    def test_parallel_completion_order_does_not_change_allocation(self):
        selected = {**selected_scope(), "releasable_seats": 2, "available_seats": 5}
        people = population(28, 117, scope=selected)
        serial = DecisionClient(mode="synthetic", max_calls=0, concurrency=1, seed=117)
        parallel = DecisionClient(mode="synthetic", max_calls=0, concurrency=8, seed=117)
        original = parallel.choose

        def delayed(observation):
            cid = observation["person"]["customer_id"]
            time.sleep((int(cid.rsplit("-", 1)[1]) % 5) * .002)
            return original(observation)

        parallel.choose = delayed
        first = pricing.evaluate(serial, people, selected, 100, 117)
        second = pricing.evaluate(parallel, people, selected, 100, 117)
        self.assertEqual(first, second)
        self.assertEqual([x["person"]["customer_id"] for x in second["decisions"]],
                         [p["customer_id"] for p in people])

    def test_forced_decline_remains_distinct_from_model_demand(self):
        selected = selected_scope()
        people = population(14, 117, scope=selected)
        people[0] = {**people[0], "eligible": True, "base_fare_budget": 0}
        client = DecisionClient(mode="synthetic", max_calls=0, concurrency=2)
        result = pricing.evaluate(client, people, selected, 328, 117)
        record = result["decisions"][0]
        self.assertEqual(record["source"], "environment_forced")
        self.assertFalse(record["provider_call"])
        self.assertTrue(record["forced"])
        model = PurchasePosterior([people[0]["segment"]])
        model.fit([dict(person=people[0], price=328, normal_fare=410, bought=False)])
        self.assertEqual(model.summary()["unaffordable"], 1)
        self.assertEqual(model.summary()["effective_likelihood_mass"], 0)

    def test_public_quote_excludes_future_and_optimizer_information(self):
        selected = {**selected_scope(), "future_actual_bookings": 999, "optimizer_profit": 12000}
        person = {**population(14, 117, scope=selected)[0], "latent_willingness": 10,
                  "future_actions": ["BUY_MEMBER"]}
        client = DecisionClient(mode="synthetic", max_calls=0)
        record = client.choose(pricing.observations([person], selected, 200)[0])
        visible = record["observation"]
        self.assertNotIn("future_actual_bookings", visible["flight"])
        self.assertNotIn("optimizer_profit", visible["flight"])
        self.assertNotIn("latent_willingness", visible["person"])
        self.assertNotIn("population_weight", visible["person"])
        self.assertNotIn("future_actions", visible["person"])


class ExperimentTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.base_patch = patch.object(adaptive_store, "BASE", Path(self.temporary.name))
        self.base_patch.start()
        self.scope_patch = patch.object(pricing, "flight_scope", side_effect=lambda *args, **kwargs: selected_scope())
        self.scope_patch.start()
        self.addCleanup(self.temporary.cleanup)
        self.addCleanup(self.base_patch.stop)
        self.addCleanup(self.scope_patch.stop)

    def config(self, **changes):
        return dict(mode="synthetic", flight_id="TEST-HKG-KMQ", forecast_day=28,
                    customers=14, rounds=2, validation_repeats=2, max_calls=0,
                    concurrency=4, seed=117) | changes

    def test_complete_run_freezes_selection_and_never_fits_holdout(self):
        fit_ids = []

        class RecordingPosterior(PurchasePosterior):
            def fit(self, rows):
                fit_ids.append({row["person"]["customer_id"] for row in rows})
                return super().fit(rows)

        with patch.object(pricing, "PurchasePosterior", RecordingPosterior):
            report = pricing.start(self.config(), blocking=True)
        self.assertEqual(report["status"], "completed", report.get("error"))
        self.assertEqual(report['config']['profile'], 'flexible_deal_seekers')
        self.assertEqual(report['population']['profile'], 'flexible_deal_seekers')
        self.assertEqual(report["counts"]["provider_calls"], 0)
        self.assertGreater(report["counts"]["synthetic_choices"], 0)
        self.assertEqual(len(report["rounds"]), 2)
        self.assertTrue(all(0 <= r["price"] <= 328 for r in report["rounds"]))
        self.assertIn(report["recommendation"]["price"], [r["price"] for r in report["rounds"]])
        self.assertTrue(report["validation"]["selected_price_frozen_before_validation"])
        search_ids = {p["customer_id"] for p in report["panel"]}
        heldout_ids = {r["person"]["customer_id"] for w in report["validation_worlds"]
                       for r in w["result"]["decisions"]}
        self.assertFalse(search_ids & heldout_ids)
        self.assertEqual(len(fit_ids), 2)
        self.assertTrue(all(ids <= search_ids for ids in fit_ids))
        self.assertEqual(len({w["seed"] for w in report["validation_worlds"]}), 2)
        selected_worlds = [w for w in report["validation_worlds"] if w["policy"] == "selected"]
        self.assertTrue(all(w["price"] == report["recommendation"]["price"] for w in selected_worlds))
        self.assertEqual(adaptive_store.read(report["run_id"])["status"], "completed")
        self.assertGreater(len(adaptive_store.events(report["run_id"])["events"]), 0)

    def test_profile_is_validated_and_preserved_in_holdout_and_provenance(self):
        with self.assertRaises(ValueError):
            pricing.validate(self.config(profile='invented_profile'))
        report = pricing.start(self.config(profile='broad_coverage'), blocking=True)
        self.assertEqual(report['status'], 'completed', report.get('error'))
        self.assertEqual(report['config']['profile'], 'broad_coverage')
        self.assertEqual(len(report['population']['segments']), 14)
        self.assertEqual({p['segment'] for p in report['panel']},
                         {r['person']['segment'] for w in report['validation_worlds']
                          for r in w['result']['decisions']})
        self.assertIn('llm_agent/prompts/adaptive_customer_v3_en.txt', report['provenance']['files'])
        self.assertNotIn('llm_agent/prompts/adaptive_customer_v1_en.txt', report['provenance']['files'])

    def test_scope_returns_the_selected_profiles_weight_schema(self):
        self.assertEqual(len(pricing.scope({'profile':'broad_coverage'})['population']['segments']), 14)
        flexible = pricing.scope({'profile':'flexible_deal_seekers'})['population']
        self.assertEqual(len(flexible['segments']), 8)
        self.assertEqual(flexible['profile'], 'flexible_deal_seekers')

    def test_final_recommendation_is_not_automatically_last_draw(self):
        calls = []

        def controlled_recommend(model, people, normal_fare, quota, rng, **kwargs):
            calls.append(kwargs)
            if kwargs["draw"]:
                price = [111, 200, 150][len(calls) - 1]
            elif "candidate_prices" in kwargs:
                self.assertEqual(kwargs["candidate_prices"], [150, 200, 328])
                price = 200
            else:
                # A dense diagnostic curve may peak at an untested price;
                # it must not replace the frozen tested recommendation.
                price = 180
            return dict(price=price, curve=[], expected_member_revenue=1.)

        with patch.object(pricing, "recommend", side_effect=controlled_recommend):
            report = pricing.start(self.config(rounds=3), blocking=True)
        self.assertEqual(report["status"], "completed", report.get("error"))
        self.assertEqual([r["price"] for r in report["rounds"]], [328, 200, 150])
        self.assertEqual(report["recommendation"]["price"], 200)
        self.assertNotEqual(report["recommendation"]["price"], report["rounds"][-1]["price"])
        self.assertEqual(len(calls), 5)

    def test_repeated_identical_offer_adds_no_learning_observations(self):
        with patch.object(pricing, "recommend", return_value={"price": 328., "curve": []}):
            report = pricing.start(self.config(rounds=4), blocking=True)
        self.assertEqual(report["status"], "completed", report.get("error"))
        rounds = report["rounds"]
        self.assertGreater(rounds[0]["learning_updates"], 0)
        self.assertTrue(all(row["learning_updates"] == 0 for row in rounds[1:]))
        self.assertTrue(all(row["reused_analysis"] for row in rounds[1:]))
        self.assertEqual(len({row["posterior"]["observations"] for row in rounds}), 1)
        self.assertTrue(all(world["reused_identical_policy"] for world in report["validation_worlds"]
                            if world["policy"] == "selected"))

    def test_insufficient_live_budget_rejected_before_client_construction(self):
        with patch.object(pricing, "DecisionClient") as client:
            with self.assertRaisesRegex(ValueError, "upper bound"):
                pricing.start(self.config(mode="live", max_calls=1), blocking=True)
            client.assert_not_called()
        self.assertEqual(adaptive_store.list_runs(), [])

    def test_failed_decisions_are_saved_as_failure_without_fake_results(self):
        with patch.object(DecisionClient, "choose_many", side_effect=ValueError("Mock decision failure")):
            report = pricing.start(self.config(), blocking=True)
        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["rounds"], [])
        self.assertIsNone(report["validation"])
        self.assertIn("Mock decision failure", report["error"])
        self.assertEqual(adaptive_store.read(report["run_id"])["status"], "failed")


if __name__ == "__main__":
    unittest.main()

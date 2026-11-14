"""Member-only experiment integration without network calls or private DB writes."""
from pathlib import Path
import hashlib
import json
import tempfile
import time
import unittest
from unittest.mock import patch

from backend import adaptive_pricing as pricing
from backend import adaptive_store
from backend.member_response import PurchasePosterior, learner_view
from llm_agent.adaptive_customers import DecisionClient
from llm_agent.weighted_population import population


def selected_scope():
    return dict(flight_id="TEST-HKG-KMQ", origin="HKG", destination="KMQ",
                departure_date="2027-05-18", departure_time="10:30", as_of_day=28,
                normal_base_fare=410., initial_member_fare=328., available_seats=80,
                releasable_seats=30, history=[], history_sha256="test-history",
                capacity=180, booked_seats=100, member_fare_cap_ratio=.8, member_fare_cap=328)


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

    def test_fractional_fares_are_rejected_instead_of_display_rounded(self):
        with self.assertRaisesRegex(ValueError, 'whole HKD'):
            pricing.settle([buyer(0)], [request()], selected_scope(), 326.5, 117)
        with self.assertRaisesRegex(ValueError, 'whole HKD'):
            pricing.settle([buyer(0)], [request()],
                           dict(selected_scope(),normal_base_fare=410.5), 328, 117)

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

    def test_forced_decline_is_audited_and_learned_without_private_constraint(self):
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
        model.fit([dict(person=learner_view(people[0]), price=328, normal_fare=410, bought=False)])
        self.assertEqual(model.summary()["likelihood_rows"], 1)
        self.assertEqual(model.summary()["effective_likelihood_mass"], 1)
        self.assertFalse(model.summary()["private_constraints_used"])

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
                    customers=14, rounds=2, validation_repeats=3, max_calls=0,
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
        search_ids = {p["customer_id"] for panel in report["search_panels"] for p in panel["people"]}
        heldout_ids = {r["person"]["customer_id"] for w in report["validation_worlds"]
                       for r in w["result"]["decisions"]}
        self.assertFalse(search_ids & heldout_ids)
        self.assertEqual(len(fit_ids), 2)
        self.assertTrue(all(ids <= search_ids for ids in fit_ids))
        self.assertEqual(len({w["seed"] for w in report["validation_worlds"]}), 3)
        selected_worlds = [w for w in report["validation_worlds"] if w["policy"] == "selected"]
        self.assertTrue(all(w["price"] == report["recommendation"]["price"] for w in selected_worlds))
        self.assertEqual(adaptive_store.read(report["run_id"])["status"], "completed")
        self.assertGreater(len(adaptive_store.events(report["run_id"])["events"]), 0)
        support_ids = {p['customer_id'] for p in report['prediction_population']}
        self.assertEqual(len(support_ids), 128)
        self.assertTrue(support_ids.isdisjoint(search_ids | heldout_ids))
        public_fields = {'customer_id','segment','flexibility_days','population_weight'}
        self.assertTrue(all(set(p) == public_fields for p in report['prediction_population']))
        self.assertTrue(all(set(row['person']) == public_fields for row in report['training_observations']))
        self.assertTrue(all(row['phase'] == 'search' for row in report['training_observations']))
        for row in report['rounds']:
            candidate_ids = [x['person']['customer_id'] for x in row['decisions']]
            initial_ids = [x['person']['customer_id'] for x in row['initial_result']['decisions']]
            self.assertEqual(candidate_ids, initial_ids)
            self.assertIsInstance(row['price'], int)
            self.assertIn(row['comparison_order'][0], (row['price'],328))
        self.assertIn(report['validation']['adoption_result'],
                      ('ADOPT_CANDIDATE','KEEP_INITIAL','NO_OFFER','INCONCLUSIVE'))

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
        self.assertIn('llm_agent/prompts/adaptive_customer_v4_en.txt', report['provenance']['files'])
        self.assertNotIn('llm_agent/prompts/adaptive_customer_v1_en.txt', report['provenance']['files'])

    def test_provenance_covers_active_forecast_and_its_accepted_evidence(self):
        from backend import forecast
        files = pricing._provenance()['files']
        calibration = json.loads((pricing.ROOT / forecast.CALIBRATION).read_text())
        dependencies = {'backend/forecast.py', forecast.CALIBRATION,
                        forecast.VALIDATION, *calibration['source_hashes']}
        for name in dependencies:
            with self.subTest(path=name):
                self.assertIn(name, files)
                self.assertEqual(files[name], hashlib.sha256((pricing.ROOT / name).read_bytes()).hexdigest())

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

    def test_repeated_price_new_people_add_evidence_but_paired_identical_quote_is_reused(self):
        with patch.object(pricing, "recommend", return_value={"price": 328., "curve": []}):
            report = pricing.start(self.config(rounds=4), blocking=True)
        self.assertEqual(report["status"], "completed", report.get("error"))
        rounds = report["rounds"]
        self.assertGreater(rounds[0]["learning_updates"], 0)
        self.assertTrue(all(row["learning_updates"] == 14 for row in rounds))
        self.assertTrue(all(not row["reused_analysis"] for row in rounds))
        self.assertTrue(all(row["paired_identical_price_reused"] for row in rounds))
        self.assertEqual([row["posterior"]["observations"] for row in rounds], [14,28,42,56])
        ids = [{p["customer_id"] for p in panel["people"]} for panel in report["search_panels"]]
        self.assertEqual(len(set.union(*ids)), 56)
        self.assertEqual(report["rounds"][-1]["cumulative_unique_customers"], 56)
        self.assertTrue(all(world["reused_identical_policy"] for world in report["validation_worlds"]
                            if world["policy"] == "selected"))

    def test_new_panel_call_budget_and_minimum_confirmation_cohorts(self):
        cfg, _, _ = pricing.validate(self.config())
        self.assertEqual(cfg['estimated_calls_upper_bound'], 2*(2*14+1)+3*3*14)
        with self.assertRaisesRegex(ValueError, 'validation_repeats'):
            pricing.validate(self.config(validation_repeats=2))

    def test_fractional_candidate_stops_run_before_executing_it(self):
        with patch.object(pricing, 'recommend', return_value={'price':326.5,'curve':[]}):
            report = pricing.start(self.config(), blocking=True)
        self.assertEqual(report['status'], 'failed')
        self.assertEqual([row['price'] for row in report['rounds']], [328])
        self.assertIn('whole HKD', report['error'])
        self.assertIsNone(report['validation'])

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


class ConfirmationAndHypothesisTests(unittest.TestCase):
    @staticmethod
    def worlds(counts, selected_price=200):
        people = [buyer(i,1/20) for i in range(20)]
        selected = selected_scope()
        worlds = []
        for seed,(initial_n,selected_n,normal_n) in enumerate(counts,700):
            for policy,price,n in [('initial',328,initial_n),('selected',selected_price,selected_n),('no_offer',None,normal_n)]:
                action = 'BUY_REGULAR' if price is None else 'BUY_MEMBER'
                decisions = [request(action if i < n else 'DECLINE','DECLINE') for i in range(20)]
                result = pricing.settle(people,decisions,selected,price,seed)
                worlds.append(dict(seed=seed,policy=policy,price=price,result=result))
        return worlds

    def test_consistent_positive_confirmation_can_adopt(self):
        report = pricing.compare_validation(self.worlds([(10,18,6)]*3),328,200,117)
        self.assertEqual(report['adoption_result'],'ADOPT_CANDIDATE')
        self.assertEqual(report['retained_price'],200)
        self.assertGreater(report['confirmation_interval']['low'],0)
        self.assertGreater(report['confirmation_extra_interval']['low'],0)
        self.assertAlmostEqual(report['break_even_conversion'],.82)
        self.assertAlmostEqual(report['observed_conversion'],.9)
        self.assertIn('not a forecast',report['break_even_scope'])

    def test_positive_average_and_lower_bound_do_not_hide_a_losing_world(self):
        report = pricing.compare_validation(self.worlds([(10,16,6)]+[(10,18,6)]*3),328,200,117)
        self.assertGreater(report['decision_gain_vs_initial'],0)
        self.assertGreater(report['confirmation_interval']['low'],0)
        self.assertEqual(report['adoption_result'],'INCONCLUSIVE')
        self.assertEqual(report['retained_price'],328)

    def test_negative_candidate_keeps_initial_and_both_losing_means_no_offer(self):
        losing = pricing.compare_validation(self.worlds([(10,15,6)]*3),328,200,117)
        self.assertEqual(losing['adoption_result'],'KEEP_INITIAL')
        self.assertEqual(losing['retained_price'],328)
        both = pricing.compare_validation(self.worlds([(6,10,8)]*3),328,200,117)
        self.assertGreater(both['decision_gain_vs_initial'],0)
        self.assertLess(both['decision_gain_vs_no_offer'],0)
        self.assertEqual(both['adoption_result'],'NO_OFFER')
        self.assertIsNone(both['retained_price'])

    def test_binding_capacity_uses_actual_transactions_for_adoption(self):
        worlds = self.worlds([(10,15,6)]*3)
        for world in worlds:
            result = world['result']
            result['capacity_binding'] = True
            result['weighted_revenue'] = 9999 if world['policy']=='selected' else 1000
        report = pricing.compare_validation(worlds,328,200,117)
        self.assertEqual(report['decision_basis'],'actual_capacity_constrained_panel')
        self.assertLess(report['decision_gain_vs_initial'],0)
        self.assertEqual(report['adoption_result'],'KEEP_INITIAL')

    def test_zero_price_break_even_is_undefined_not_division_failure(self):
        report = pricing.compare_validation(self.worlds([(10,20,6)]*3,selected_price=0),328,0,117)
        self.assertIsNone(report['break_even_conversion'])
        self.assertEqual(report['adoption_result'],'KEEP_INITIAL')

    def test_reweighted_receipts_cannot_bypass_available_inventory(self):
        worlds = self.worlds([(10,15,6)]*3)
        for world in worlds:
            if world['policy'] == 'selected':
                world['result']['quota'] = 16
                world['result']['weighted_fulfilled_conversion'] = .95
                world['result']['weighted_revenue'] = 9999
        report = pricing.compare_validation(worlds,328,200,117)
        self.assertEqual(report['decision_basis'],'actual_capacity_constrained_panel')
        self.assertEqual(report['adoption_result'],'KEEP_INITIAL')
        self.assertFalse(report['break_even_attainable'])
        self.assertAlmostEqual(report['max_fulfilled_conversion'],.8)

    def test_free_price_can_match_an_already_zero_receipt_baseline(self):
        report = pricing.compare_validation(self.worlds([(0,20,0)]*3,selected_price=0),328,0,117)
        self.assertEqual(report['break_even_conversion'],0)
        self.assertTrue(report['break_even_attainable'])

    def test_feedback_is_bounded_test_only_on_reserved_rounds(self):
        proposal = {'price':100,'curve':[dict(price=p,expected_member_revenue=p*10)
                                       for p in (0,100,200,250,275,300,328)]}
        prior = {'price':300,'round':2,'analysis':{'suggested_direction':'lower','evidence_customer_ids':['C1']}}
        price,info = pricing._hypothesis_price(proposal,prior,3,328)
        self.assertEqual(price,275)
        self.assertGreaterEqual(price,300-82)
        self.assertLess(price,prior['price'])
        self.assertEqual(info['status'],'pending')
        self.assertEqual(info['source_round'],2)
        self.assertEqual(info['evidence_customer_ids'],['C1'])
        for number in (1,2,4,5):
            selected,info = pricing._hypothesis_price(proposal,prior,number,328)
            self.assertEqual(selected,100)
            self.assertEqual(info['status'],'not_tested')
        prior['analysis']['evidence_customer_ids'] = []
        selected,info = pricing._hypothesis_price(proposal,prior,3,328)
        self.assertEqual(selected,100)
        self.assertEqual(info['status'],'not_tested')

    def test_feedback_cannot_escape_domain_or_invent_unscored_price(self):
        proposal = {'price':100,'curve':[dict(price=p,expected_member_revenue=p*10)
                                       for p in (0,100,200,300,328)]}
        prior = {'price':328,'round':2,'analysis':{'suggested_direction':'higher','evidence_customer_ids':['C1']}}
        price,info = pricing._hypothesis_price(proposal,prior,3,328)
        self.assertEqual(price,100)
        self.assertEqual(info['status'],'not_tested')
        self.assertIn('no permitted',info['summary'])



if __name__ == "__main__":
    unittest.main()

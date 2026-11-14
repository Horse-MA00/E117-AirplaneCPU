import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backend import adaptive_pricing as pricing, adaptive_store
from backend.member_response import learner_view
from backend.pricing_scenarios import (
    apply_pricing_scenario, population_for_config, validate_scenario_request, VERSION,
)
from llm_agent.weighted_population import population


def source_scope():
    return {'flight_id':'SYN-00017', 'origin':'HKG', 'destination':'FUK',
            'departure_date':'2027-05-17', 'departure_time':'10:30', 'as_of_day':7,
            'normal_base_fare':690, 'observed_normal_base_fare':690,
            'initial_member_fare':552, 'member_fare_cap':552, 'member_fare_cap_ratio':.8,
            'initial_fare_source':'snapshot.normal_base_fare_x_member_cap',
            'capacity':180, 'booked_seats':70, 'available_seats':110,
            'releasable_seats':58, 'member_supply_exposure':58,
            'expected_remaining_demand':20, 'history_sha256':'frozen-input-hash',
            'history':[{'normal_base_fare':690, 'days_to_departure':7}]}


def config(**changes):
    return {'flight_id':'SYN-00017', 'forecast_day':7, 'mode':'synthetic',
            'demo_scenario':'low_fare_55', 'rounds':2, 'customers':16,
            'validation_repeats':3, 'concurrency':4, 'max_calls':0,
            'seed':26111501} | changes


class PricingScenarioTests(unittest.TestCase):
    def test_default_scope_and_population_are_unchanged(self):
        supplied = source_scope()
        self.assertIs(apply_pricing_scenario({}, supplied), supplied)
        plain = population(16, 26111501, scope=supplied)
        self.assertEqual(population_for_config({}, 16, 26111501, supplied), plain)
        with patch.object(pricing, 'flight_scope', return_value=supplied):
            ordinary = pricing.scope({'flight_id':'SYN-00017', 'forecast_day':7})
        self.assertNotIn('scenario', ordinary)
        self.assertEqual(ordinary['scope']['normal_base_fare'], 690)

    def test_only_enumerated_matching_flights_and_rounds_are_allowed(self):
        for invalid in ('', 'free', {}, True, 55):
            with self.subTest(invalid=invalid), self.assertRaisesRegex(ValueError, 'demo_scenario'):
                validate_scenario_request(config(demo_scenario=invalid))
        for changes in ({'flight_id':'SYN-00018'}, {'forecast_day':14}, {'forecast_day':True}):
            with self.subTest(changes=changes), self.assertRaisesRegex(ValueError, 'requires'):
                pricing.scope(config(**changes))
        expected = [('low_fare_55','SYN-00017',7,55,44),
                    ('low_fare_60','DEMO-HKG-OKA-20270515',14,60,48),
                    ('low_fare_65','DEMO-HKG-NGO-20270515',7,65,52)]
        for name, flight, day, normal, cap in expected:
            original = source_scope() | {'flight_id':flight, 'as_of_day':day}
            selected = apply_pricing_scenario(config(demo_scenario=name, flight_id=flight,
                                                     forecast_day=day), original)
            self.assertEqual((selected['normal_base_fare'],selected['initial_member_fare'],
                              selected['member_fare_cap']), (normal,cap,cap))
            self.assertGreater(cap, 30)

    def test_scenario_preserves_source_prices_inventory_history_and_hashes(self):
        original = source_scope()
        untouched = copy.deepcopy(original)
        selected = apply_pricing_scenario(config(), original)
        info = selected['scenario']
        self.assertEqual(original, untouched)
        self.assertEqual(info['source_scope'], {k:v for k,v in original.items() if k!='history'})
        digest = hashlib.sha256(json.dumps(info['source_scope'],sort_keys=True,
                               separators=(',',':'),allow_nan=False).encode()).hexdigest()
        self.assertEqual(info['source_scope_sha256'], digest)
        for key in ('available_seats','releasable_seats','expected_remaining_demand',
                    'observed_normal_base_fare','history','history_sha256'):
            self.assertEqual(selected[key], original[key])
        self.assertEqual(info['version'], VERSION)
        self.assertIn('held fixed', info['disclaimer'])
        self.assertEqual(selected['initial_fare_source'],'declared_scenario_normal_fare_x_member_cap')
        with self.assertRaisesRegex(ValueError, 'original matching'):
            apply_pricing_scenario(config(), selected)

    def test_private_budgets_scale_down_without_entering_public_learning(self):
        original = population(32, 26111501, scope=source_scope())
        scaled = population_for_config(config(), 32, 26111501, source_scope())
        self.assertEqual(len({p['segment'] for p in scaled}), 8)
        for before, after in zip(original, scaled):
            self.assertEqual(after['base_fare_budget'], before['base_fare_budget']//10)
            self.assertGreaterEqual(after['base_fare_budget'], 0)
            self.assertEqual(after['pricing_scenario']['source_base_fare_budget'], before['base_fare_budget'])
            self.assertEqual(learner_view(before), learner_view(after))
            self.assertEqual(set(learner_view(after)),
                             {'customer_id','segment','flexibility_days','population_weight'})

    def test_saved_scenario_precedes_decisions_and_covers_all_cohorts(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(adaptive_store,'BASE',Path(directory)), \
                patch.object(pricing,'flight_scope',return_value=source_scope()):
            original_evaluate = pricing.evaluate
            observed = []

            def inspect_first(client, people, selected, price, seed):
                saved = adaptive_store.list_runs()[0]
                self.assertEqual(saved['config']['demo_scenario'],'low_fare_55')
                report = adaptive_store.read(saved['run_id'])
                self.assertEqual(report['scenario'],selected['scenario'])
                self.assertIn('backend/pricing_scenarios.py',report['provenance']['files'])
                self.assertEqual(report['provenance']['scenario']['definition_sha256'],
                                 selected['scenario']['definition_sha256'])
                observed.extend(people)
                return original_evaluate(client,people,selected,price,seed)

            with patch.object(pricing,'evaluate',side_effect=inspect_first):
                report = pricing.start(config(),blocking=True)
            self.assertEqual(report['status'],'completed',report.get('error'))
            self.assertEqual(report['counts']['provider_calls'],0)
            self.assertEqual(len(report['validation_worlds']),9)
            self.assertTrue(all(p['pricing_scenario']['id']=='low_fare_55' for p in observed))
            self.assertTrue(all('pricing_scenario' not in p and 'base_fare_budget' not in p
                                for p in report['prediction_population']))
            self.assertEqual(report['scope']['releasable_seats'],58)

    def test_zero_formatted_candidate_does_not_force_revenue_adoption(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(adaptive_store,'BASE',Path(directory)), \
                patch.object(pricing,'flight_scope',return_value=source_scope()), \
                patch.object(pricing,'recommend',return_value={'price':25,'curve':[]}):
            report = pricing.start(config(),blocking=True)
        self.assertEqual(report['status'],'completed',report.get('error'))
        self.assertEqual(report['recommendation']['raw_price'],25)
        self.assertEqual(report['recommendation']['price'],0)
        self.assertNotEqual(report['validation']['retained_price'],0)
        self.assertNotEqual(report['validation']['adoption_result'],'ADOPT_CANDIDATE')
        self.assertTrue(all(w['result']['member_revenue']==0 for w in report['validation_worlds']
                            if w['policy']=='selected'))


if __name__ == '__main__':
    unittest.main()

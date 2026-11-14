import copy
import math
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from backend.probabilistic_customer import choose
from backend.continuous_pricing import adaptive_search, optimize, replay
from llm_agent.file_lock import exclusive_lock


def observation(price=100):
    return {"packet_id":"decision-1", "customer_id":"user-1", "stage":"quote",
        "customer":{"customer_id":"user-1","flexibility_days":3,"total_budget":1000},
        "visible_state":{"remaining_budget":1000},
        "trip":{"trip_budget":600,"desired_departure_day":30},
        "allowed_actions":["DECLINE","WAIT","BUY_MEMBER","BUY_REGULAR"],
        "options":[{"id":"flight:member","action":"BUY_MEMBER","price":price,"departure_day":30},
                   {"id":"flight:normal","action":"BUY_REGULAR","price":500,"departure_day":30}]}


class ProbabilisticCustomerTests(unittest.TestCase):
    def test_repeat_and_option_order_are_stable(self):
        o=observation(); original=copy.deepcopy(o)
        first=choose(o)
        o['options'].reverse()
        self.assertEqual(first,choose(o))
        self.assertEqual(choose(original),first)

    def test_member_probability_falls_when_full_price_rises(self):
        def probability(price):
            return next(r['probability'] for r in choose(observation(price))['probabilities'] if r['action']=='BUY_MEMBER')
        self.assertGreater(probability(100),probability(400))

    def test_probabilities_sum_to_one_and_choices_are_legal(self):
        for price in (0,83.61,400):
            o=observation(price);r=choose(o)
            self.assertAlmostEqual(sum(p['probability'] for p in r['probabilities']),1)
            self.assertIn(r['decision']['action'],o['allowed_actions'])

    def test_historical_booking_is_kept_not_declined(self):
        o=observation();o.update(options=[],allowed_actions=['KEEP_BOOKING'])
        self.assertEqual(choose(o)['decision']['action'],'KEEP_BOOKING')

    def test_hidden_airline_objective_does_not_affect_choice(self):
        o=observation();a=choose(o);o.update(airline_profit=999999,ground_truth={'beta':999})
        self.assertEqual(a,choose(o))

    def test_sensitivity_stress_changes_probabilities(self):
        self.assertNotEqual(choose(observation(),'price_sensitive')['probabilities'],choose(observation(),'less_sensitive')['probabilities'])


class ContinuousSearchTests(unittest.TestCase):
    def test_search_is_bounded_cent_resolved_and_finds_interior_price(self):
        def evaluate(p):return {'member_fare':p,'search_score':-(p-83.61)**2}
        rows=adaptive_search(evaluate,0,200,31)
        self.assertLessEqual(len(rows),31)
        self.assertLess(abs(max(rows,key=lambda r:r['search_score'])['member_fare']-83.61),3)
        self.assertTrue(all(0<=r['member_fare']<=200 and round(r['member_fare'],2)==r['member_fare'] for r in rows))
        self.assertEqual(rows,adaptive_search(evaluate,0,200,31))

    def test_bad_input_rejected_before_simulation(self):
        for config in ({'price_min':500,'price_max':10},{'price_max':float('nan')},
                       {'evaluations':1000},{'replicates':True},{'customers':-1}):
            with self.subTest(config=config),self.assertRaises(ValueError):optimize(config)

    def test_file_lock_releases_after_error(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'lock'
            with self.assertRaises(RuntimeError):
                with exclusive_lock(path):raise RuntimeError('test')
            with exclusive_lock(path):pass

    def test_probabilistic_adapter_records_probability_feedback(self):
        from llm_agent import audit, market_adapter
        with tempfile.TemporaryDirectory() as d, patch.object(audit, 'BASE', Path(d)):
            log=audit.Audit('test')
            result=market_adapter.choose(observation(), 'probabilistic', log)
            self.assertEqual(result['source'],'probabilistic_assumption')
            self.assertFalse(result['provider_call'])
            records=audit.read_run(log.run_id)['records']
            self.assertTrue(records[-1]['choice_probabilities'])

    def test_failed_background_job_clears_busy_state(self):
        from backend import pricing_jobs
        with tempfile.TemporaryDirectory() as d, patch.object(pricing_jobs,'BASE',Path(d)):
            rid='price-'+'a'*16
            folder=pricing_jobs._path(rid);folder.mkdir()
            pricing_jobs._active.add(rid)
            with patch('backend.continuous_pricing.optimize',side_effect=ValueError('invalid bounds')):
                pricing_jobs._worker(rid,{})
            self.assertEqual(pricing_jobs.read(rid)['status'],'failed')
            self.assertNotIn(rid,pricing_jobs._active)

    def test_baseline_programme_cost_and_independent_validation(self):
        # Inspect policy copies without expensive model work; checks actual setup ledger removal.
        from backend.shared_market import create_market
        calls=[]
        def fake_replay(state,scenario='base',keep_feedback=False):
            calls.append((state['seed'],state['policy']['enabled'],state['ledger_cents']['program_cost']))
            if not state['policy']['enabled']:
                self.assertFalse(any(e['kind']=='programme' for e in state['ledger_entries']))
            return {'complete':True,'contribution':1000 if not state['policy']['enabled'] else 900,
                    'new_members':1,'service_rate':1.,'member_flown':1,'checks':{'ok':True}}
        with patch('backend.continuous_pricing.replay',side_effect=fake_replay):
            result=optimize({'evaluations':3,'replicates':1,'customers':2,'seed':811})
        self.assertEqual(result['best']['decision'],'NO_OFFER')
        self.assertFalse(result['ready_for_review'])
        for row in [*result['trace'], result['validation'], *result['stress']]:
            self.assertEqual(row['mean_total_contribution'], 900)
            self.assertEqual(row['mean_baseline_contribution'], 1000)
            self.assertEqual(row['incremental_contribution'], -100)
        self.assertIsNone(result['trace'][0]['total_standard_error'])
        self.assertEqual(result['validation']['total_standard_error'], 0)
        self.assertFalse(set(result['search_seeds']) & set(result['validation_seeds']))
        self.assertTrue(all(cost==0 for seed,enabled,cost in calls if not enabled))
        self.assertTrue(all(cost==150000 for seed,enabled,cost in calls if enabled))


if __name__=='__main__':unittest.main()

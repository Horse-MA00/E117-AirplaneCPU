"""Independent checks of replay accounting and final posterior diagnostics.

Provider traffic is replaced with an in-memory transport. Tests never load
private environment files, real credentials or the persistent experiment DB.
"""
from contextlib import ExitStack
import copy
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from backend import adaptive_pricing as pricing
from backend import adaptive_store as store
from backend.thompson import PurchasePosterior
from llm_agent import adaptive_customers as adapter


ENV = {'LLM_API_URL': 'https://api.deepseek.com/chat/completions', 'LLM_MODEL': 'mock-replay-model',
       'LLM_API_KEY': 'fake-replay-primary-credential', 'LLM_API_KEY_SECONDARY': 'fake-replay-secondary-credential'}


def scope():
    return dict(flight_id='TEST-REPLAY', origin='HKG', destination='KMQ', departure_date='2027-05-18',
                departure_time='10:30', as_of_day=28, normal_base_fare=410., initial_member_fare=328.,
                available_seats=80, releasable_seats=30, history=[], history_sha256='test-history',
                capacity=180, booked_seats=100, member_fare_cap_ratio=.8)


class AdaptiveReplayTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        path = self.stack.enter_context(tempfile.TemporaryDirectory())
        self.stack.enter_context(patch.object(store, 'BASE', Path(path)))
        self.stack.enter_context(patch.object(pricing, 'flight_scope', side_effect=lambda *a, **k: scope()))
        self.stack.enter_context(patch.dict('os.environ', ENV))
        self.requests = []
        self.request_lock = threading.Lock()
        self.stack.enter_context(patch.object(adapter, '_transport', side_effect=self.transport))
        self.fit_rows = []
        seen_rows = self.fit_rows

        class RecordingPosterior(PurchasePosterior):
            def fit(self, rows):
                seen_rows.append(copy.deepcopy(rows))
                return super().fit(rows)

        self.stack.enter_context(patch.object(pricing, 'PurchasePosterior', RecordingPosterior))
        self.proposals = []
        self.draw_index = 0
        self.stack.enter_context(patch.object(pricing, 'recommend', side_effect=self.recommend))

    def transport(self, request):
        body = json.loads(request.data)
        context = json.loads(body['messages'][1]['content'])
        with self.request_lock:
            self.requests.append(copy.deepcopy(context))
        if 'feedback' in context:
            answer = {'summary': 'The observed decisions reflect this tested basic fare.',
                      'reason_counts': {'price': 0, 'date': 0, 'companions': 0, 'availability': 0,
                                        'other': len(context['feedback'])},
                      'hypothesis': 'A different fare may produce a different purchase rate.',
                      'evidence_customer_ids': [row['customer_id'] for row in context['feedback'][:1]]}
        else:
            actions = context['allowed_actions']
            action = 'BUY_MEMBER' if 'BUY_MEMBER' in actions else 'BUY_REGULAR' if 'BUY_REGULAR' in actions else 'DECLINE'
            answer = {'action': action,
                      'fallback_action': 'BUY_REGULAR' if action == 'BUY_MEMBER' and 'BUY_REGULAR' in actions else 'DECLINE',
                      'reason_code': 'AFFORDABLE', 'reason': 'This basic fare fits my trip and personal ticket budget.'}
        raw = {'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(answer)}}],
               'usage': {'total_tokens': 30}}
        return io.BytesIO(json.dumps(raw).encode())

    def recommend(self, model, people, normal_fare, quota, rng, **kwargs):
        self.proposals.append(copy.deepcopy(kwargs))
        if kwargs['draw']:
            self.draw_index += 1
            price = 123. if self.draw_index == 1 else 200.
            prices = [0., 123., 200., 328.]
        else:
            price = 200.
            prices = kwargs.get('candidate_prices') or [0., 100., 200., 300., 328.]
        curve = [{'price': p, 'expected_buyers': 10., 'expected_member_revenue': p * 10.,
                  'purchase_probability': .5, 'revenue_low': p * 8., 'revenue_high': p * 12.} for p in prices]
        return {'price': price, 'curve': curve, 'expected_member_revenue': price * 10.,
                'selection_kind': 'thompson_joint_posterior_draw' if kwargs['draw'] else 'posterior_mean_revenue_volume_rule'}

    def run_experiment(self):
        report = pricing.start({'mode': 'live', 'flight_id': 'TEST-REPLAY', 'forecast_day': 28,
                                'customers': 14, 'rounds': 3, 'validation_repeats': 2,
                                'max_calls': 200, 'concurrency': 4, 'seed': 117,
                                'revenue_fraction': .8}, blocking=True)
        self.assertEqual(report['status'], 'completed', report.get('error'))
        return report

    def test_same_price_replays_choices_without_new_calls_or_likelihood_rows(self):
        report = self.run_experiment()
        self.assertEqual([r['price'] for r in report['rounds']], [328., 200., 200.])
        repeated = report['rounds'][2]['decisions']
        self.assertTrue(any(row['source'] == 'provider_cache' for row in repeated))
        self.assertTrue(all(row['source'] in ('provider_cache', 'environment_forced') for row in repeated))
        self.assertFalse(any(row['provider_call'] for row in repeated))
        self.assertEqual(report['rounds'][2]['learning_updates'], 0)
        self.assertTrue(report['rounds'][2]['reused_analysis'])
        self.assertEqual(report['rounds'][2]['analysis_source'], 'reused_no_new_observations')
        self.assertFalse(report['rounds'][1]['reused_analysis'])
        self.assertGreater(report['counts']['cache_hits'], 0)
        self.assertEqual(report['counts']['analyst_calls'], 2)
        analyst_requests = [req for req in self.requests if 'feedback' in req]
        self.assertEqual([req['price'] for req in analyst_requests], [328., 200.])
        for rows in self.fit_rows:
            pairs = [(r['person']['customer_id'], round(r['price'] * 100)) for r in rows]
            self.assertEqual(len(pairs), len(set(pairs)), 'Cached same-price outcomes must not duplicate likelihood rows')
        final_pairs = {(r['person']['customer_id'], round(r['price'] * 100)) for r in self.fit_rows[-1]}
        expected = {(p['customer_id'], price) for p in report['panel'] if p['eligible'] for price in (32800, 20000)}
        self.assertEqual(final_pairs, expected)

    def test_final_diagnostics_use_full_posterior_grid_without_training_on_holdout(self):
        report = self.run_experiment()
        recommendation = report['recommendation']
        self.assertEqual(recommendation['revenue_fraction'], .8)
        self.assertNotIn('95', recommendation['selection'])
        tested = {r['price'] for r in report['rounds']}
        self.assertIn(recommendation['price'], tested)
        self.assertEqual({r['price'] for r in recommendation['curve']}, tested)
        self.assertGreater(len(recommendation['model_curve']), len(tested))
        self.assertTrue(any(not call['draw'] and call.get('candidate_prices') is None for call in self.proposals))
        training_ids = {p['customer_id'] for p in report['panel']}
        holdout_ids = {r['person']['customer_id'] for world in report['validation_worlds']
                       for r in world['result']['decisions']}
        self.assertFalse(training_ids & holdout_ids)
        self.assertTrue(all(row['person']['customer_id'] in training_ids for rows in self.fit_rows for row in rows))
        self.assertTrue(report['validation']['selected_price_frozen_before_validation'])


if __name__ == '__main__':
    unittest.main()

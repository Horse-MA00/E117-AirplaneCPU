"""Compact presentation data never replaces or rewrites saved audit evidence."""
import copy
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from backend import adaptive_store as store
from backend import experiment_views as views


def report():
    curve = [{'price': price, 'expected_buyers': 9.5, 'expected_member_revenue': price * 9.5,
              'purchase_probability': .95, 'revenue_low': 3, 'revenue_high': 90}
             for price in (0, 10, 20)]
    decision = {'decision': {'action': 'BUY_MEMBER', 'reason': 'A complete saved explanation.',
                             'reason_code': 'VALUE', 'fallback_action': 'BUY_REGULAR'},
                'person': {'customer_id': 'person-1', 'segment': 'weekender',
                           'segment_label': 'Weekend traveller', 'private_budget': 123},
                'observation': {'prompt': 'repeated full customer context' * 100},
                'source': 'provider_live', 'provider_call': True, 'forced': False, 'cache_hit': False,
                'settlement': {'status': 'fulfilled', 'accounting': {'raw': 'audit'}}}
    round_ = {'round': 1, 'price': 20, 'member_buyers': 2, 'member_revenue': 40,
              'weighted_conversion': .75, 'paired_delta_vs_initial': 0, 'unique_customers': 3,
              'learning_updates': 6, 'analysis': {'summary': 'Saved analyst explanation.'},
              'analysis_status': 'passed', 'analysis_error': None,
              'analysis_attempts': [{'attempt': 1, 'status': 'passed'}],
              'analysis_source': 'provider_live', 'hypothesis_test': {'status': 'not_tested'},
              'decisions': [decision], 'curve': curve, 'posterior': {'weights': [1, 2]},
              'proposal': {'posterior': 'audit'}, 'initial_result': {'decisions': [decision]}}
    return {'run_id': 'adaptive-compact', 'version': 'member-thompson-v5-marketing',
            'config': {'profile': 'flexible_deal_seekers', 'rounds': 2, 'name': 'Compact test'},
            'scope': {'flight_id': 'flight-1', 'as_of_day': 28}, 'created_at': 100., 'updated_at': 101.,
            'status': 'completed', 'error': None, 'rounds': [round_, {**round_, 'round': 2}],
            'progress': {'completed_rounds': 2, 'total_rounds': 2, 'phase': 'completed'},
            'counts': {'provider_calls': 8, 'failures': 0},
            'recommendation': {'price': 19, 'raw_price': 20, 'reason': 'Saved selection.',
                               'curve': curve, 'model_curve': curve, 'posterior': {'weights': [3, 4]}},
            'validation': {'adoption_result': 'KEEP_INITIAL', 'retained_price': 19},
            'population': {'segments': [{'id': 'weekender', 'weight': 1.}]},
            'search_panels': [decision], 'panel': [decision], 'prediction_population': [decision],
            'validation_worlds': [{'result': {'decisions': [decision]}}],
            'training_observations': [{'audit_marker': 'full report only'}]}


class ExperimentViewTests(unittest.TestCase):
    def test_detail_preserves_ui_values_and_omits_repeated_audit_data(self):
        saved = report()
        original = copy.deepcopy(saved)
        detail = views.detail(saved)
        for key in ('config', 'scope', 'population', 'counts', 'progress', 'validation'):
            self.assertEqual(detail[key], saved[key])
        for full, compact in zip(saved['rounds'], detail['rounds']):
            for key in ('price', 'member_buyers', 'member_revenue', 'analysis', 'analysis_status',
                        'analysis_attempts', 'hypothesis_test', 'learning_updates'):
                self.assertEqual(compact[key], full[key])
            self.assertEqual(compact['decisions'][0]['decision'], full['decisions'][0]['decision'])
            self.assertEqual(compact['decisions'][0]['person']['customer_id'], 'person-1')
            self.assertEqual(compact['decisions'][0]['settlement']['status'], 'fulfilled')
            for key in ('curve', 'posterior', 'initial_result', 'proposal'):
                self.assertNotIn(key, compact)
            self.assertNotIn('observation', compact['decisions'][0])
        for key in ('search_panels', 'panel', 'training_observations', 'prediction_population', 'validation_worlds'):
            self.assertNotIn(key, detail)
        self.assertNotIn('posterior', detail['recommendation'])
        self.assertNotIn('curve', detail['recommendation'])
        for original_point, point in zip(saved['recommendation']['model_curve'], detail['recommendation']['model_curve']):
            self.assertEqual(point, {key: original_point[key] for key in
                                    ('price', 'expected_buyers', 'expected_member_revenue')})
        self.assertLess(len(json.dumps(detail)), len(json.dumps(saved)) / 2)
        detail['rounds'][0]['decisions'][0]['decision']['reason'] = 'Caller mutation'
        self.assertEqual(saved, original)

    def test_active_view_keeps_latest_pre_round_curve_and_legacy_identity(self):
        saved = report()
        saved['recommendation'] = saved['validation'] = None
        decision = saved['rounds'][0]['decisions'][0]
        decision['observation']['person'] = decision.pop('person')
        detail = views.detail(saved)
        self.assertNotIn('curve', detail['rounds'][0])
        self.assertEqual(len(detail['rounds'][-1]['curve']), 3)
        self.assertEqual(detail['rounds'][0]['decisions'][0]['person']['segment_label'], 'Weekend traveller')

    def test_summary_and_failed_progress_do_not_invent_results(self):
        saved = report()
        compact = views.summary(saved)
        self.assertEqual(compact['recommendation'], {'price': 19, 'raw_price': 20, 'reason': 'Saved selection.'})
        self.assertNotIn('rounds', compact)
        saved.update(status='failed', error='Provider failed', recommendation=None, validation=None)
        heartbeat = views.progress(saved)
        self.assertEqual(heartbeat['status'], 'failed')
        self.assertEqual(heartbeat['error'], 'Provider failed')
        self.assertEqual(heartbeat['saved_rounds'], 2)
        self.assertFalse(heartbeat['has_recommendation'])
        self.assertFalse(heartbeat['has_validation'])
        self.assertNotIn('rounds', heartbeat)
        self.assertIsNone(views.detail(saved)['validation'])


class PersistedViewTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        for name, value in (('BASE', self.base), ('_published', None)):
            scope = patch.object(store, name, value)
            scope.start()
            self.addCleanup(scope.stop)

    def test_saved_list_and_poll_do_not_decode_reports(self):
        saved = report()
        store.save(saved)
        loads = json.loads
        decoded = []
        def small_only(value, *args, **kwargs):
            self.assertNotIn('training_observations', value)
            decoded.append(value)
            return loads(value, *args, **kwargs)
        with patch.object(store, 'read', side_effect=AssertionError('Full report read during polling')):
            with patch.object(store.json, 'loads', side_effect=small_only):
                for _ in range(3):
                    self.assertEqual(store.read_progress(saved['run_id'])['saved_rounds'], 2)
                    self.assertEqual(store.list_runs()[0]['recommendation']['price'], 19)
        self.assertEqual(len(decoded), 6)
        saved['progress']['completed_validation_worlds'] = 4
        saved['counts']['provider_calls'] = 12
        store.save(saved)
        self.assertEqual(store.read_progress(saved['run_id'])['counts']['provider_calls'], 12)
        self.assertEqual(store.read_progress(saved['run_id'])['progress']['completed_validation_worlds'], 4)

    def test_old_database_backfill_preserves_original_payload_and_audit(self):
        saved = report()
        raw = json.dumps(saved, indent=3)
        path = self.base / 'experiments.sqlite3'
        with closing(sqlite3.connect(path)) as db, db:
            db.execute('CREATE TABLE adaptive_runs (run_id TEXT PRIMARY KEY,payload TEXT NOT NULL,created_at REAL NOT NULL,updated_at REAL NOT NULL)')
            db.execute('INSERT INTO adaptive_runs VALUES (?,?,?,?)', (saved['run_id'], raw, 100, 101))
        self.assertEqual(store.list_runs()[0]['recommendation']['price'], 19)
        self.assertEqual(store.read_progress(saved['run_id'])['saved_rounds'], 2)
        store.record(saved['run_id'], {'event': 'saved', 'raw_response_text': 'full raw evidence'})
        self.assertEqual(store.export_run(saved['run_id'])['report'], saved)
        self.assertEqual(store.export_run(saved['run_id'])['events'][0]['record']['raw_response_text'], 'full raw evidence')
        self.assertEqual(store.read_view(saved['run_id'])['rounds'][0]['decisions'][0]['decision']['reason'],
                         'A complete saved explanation.')
        with store.connection() as db:
            self.assertEqual(db.execute('SELECT payload,updated_at FROM adaptive_runs').fetchone()[:], (raw, 101))
            self.assertEqual(db.execute('SELECT COUNT(*) FROM adaptive_run_views').fetchone()[0], 1)

    def test_legacy_update_with_same_timestamp_invalidates_the_projection(self):
        saved = report()
        store.save(saved)
        saved.update(status='failed', error='Legacy writer failed')
        with store.connection() as db:
            db.execute('UPDATE adaptive_runs SET payload=? WHERE run_id=?', (store.encode(saved), saved['run_id']))
        heartbeat = store.read_progress(saved['run_id'])
        self.assertEqual(heartbeat['status'], 'failed')
        self.assertEqual(heartbeat['error'], 'Legacy writer failed')
        self.assertEqual(store.list_runs()[0]['status'], 'failed')

    def test_outdated_projection_is_rebuilt_and_deleted_database_is_reinitialized(self):
        saved = report()
        store.save(saved)
        with store.connection() as db:
            db.execute('UPDATE adaptive_run_views SET view_version=0,progress=?', ('{}',))
        self.assertEqual(store.read_progress(saved['run_id'])['saved_rounds'], 2)
        (self.base / 'experiments.sqlite3').unlink()
        with self.assertRaisesRegex(ValueError, 'not found'):
            store.read_progress(saved['run_id'])
        self.assertEqual(store.list_runs(), [])
        store.save({**saved, 'run_id': 'adaptive-new'})
        self.assertEqual([row['run_id'] for row in store.list_runs()], ['adaptive-new'])


if __name__ == '__main__':
    unittest.main()

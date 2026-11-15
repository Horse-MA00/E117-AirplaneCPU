"""HTTP projection routes retain report/export access and safe orphan recovery."""
from contextlib import contextmanager
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backend import adaptive_pricing as pricing, adaptive_store as store, server
from backend.errors import NotFound
from backend.tests.test_experiment_views import report


class ExperimentViewApiTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        for module, name, value in ((store, 'BASE', self.base), (store, '_published', None),
                                    (pricing, '_active', set())):
            scope = patch.object(module, name, value)
            scope.start()
            self.addCleanup(scope.stop)
        self.saved = report()
        self.saved['created_at'] = 100
        self.path = '/api/adaptive-pricing/runs/' + self.saved['run_id']

    def save_at(self, timestamp=1000, **changes):
        self.saved.update(changes)
        with patch.object(store.time, 'time', return_value=timestamp):
            store.save(self.saved)
        return copy.deepcopy(self.saved)

    def test_status_does_not_read_local_credentials(self):
        with patch.object(pricing, 'configure_live_credentials', side_effect=AssertionError('Read-only status loaded keys')), \
                patch.object(Path, 'read_text', side_effect=AssertionError('Status read a local file')):
            result = server.get('/api/adaptive-pricing/status')
        self.assertEqual(result['version'], pricing.VERSION)
        self.assertEqual(len(result['population']['segments']), 8)

    def test_http_progress_view_full_and_export_have_distinct_boundaries(self):
        complete = self.save_at()
        store.record(complete['run_id'], {'event': 'customer_response', 'raw_response_text': 'Unabridged audit text'})
        heartbeat = server.get(self.path + '/progress')
        compact = server.get(self.path + '/view')
        full = server.get(self.path)
        exported = server.get(self.path + '/export')
        listing = server.get('/api/adaptive-pricing/runs')['runs'][0]
        self.assertEqual(heartbeat['saved_rounds'], len(full['rounds']))
        self.assertNotIn('rounds', heartbeat)
        self.assertNotIn('training_observations', compact)
        self.assertNotIn('model_curve', listing['recommendation'])
        self.assertEqual(compact['rounds'][0]['decisions'][0]['decision'],
                         full['rounds'][0]['decisions'][0]['decision'])
        self.assertEqual(full, complete)
        self.assertEqual(exported['report'], complete)
        self.assertEqual(exported['events'][0]['record']['raw_response_text'], 'Unabridged audit text')
        self.assertEqual(store.read(complete['run_id']), complete)

    def test_unknown_and_retired_runs_are_404_without_orphan_mutation(self):
        endpoints = ('', '/progress', '/view', '/export', '/events', '/analysis-attempts')
        for suffix in endpoints:
            with self.subTest(missing=suffix), self.assertRaises(NotFound):
                server.get('/api/adaptive-pricing/runs/missing' + suffix)
        for changes in ({'version': 'member-thompson-v4-integer'},
                        {'config': {'profile': 'broad_coverage'}}):
            self.saved = report()
            complete = self.save_at(100, status='queued', **changes)
            with patch.object(pricing.time, 'time', return_value=1000):
                with patch.object(store, 'save', side_effect=AssertionError('Retired evidence mutated')):
                    for suffix in endpoints:
                        with self.subTest(changes=changes, suffix=suffix), self.assertRaises(NotFound):
                            server.get(self.path + suffix)
            self.assertEqual(store.read(complete['run_id']), complete)
            self.assertEqual(server.get('/api/adaptive-pricing/runs')['runs'], [])

    def test_repeated_active_heartbeats_never_read_or_decode_full_report(self):
        self.save_at(status='running', recommendation=None, validation=None)
        loads = json.loads
        def small_only(value, *args, **kwargs):
            self.assertNotIn('training_observations', value)
            return loads(value, *args, **kwargs)
        with patch.object(pricing.time, 'time', return_value=1001):
            with patch.object(store, 'read', side_effect=AssertionError('Full report read during heartbeat')):
                with patch.object(store.json, 'loads', side_effect=small_only):
                    for _ in range(4):
                        heartbeat = server.get(self.path + '/progress')
                        self.assertEqual(heartbeat['status'], 'running')
                        self.assertEqual(heartbeat['elapsed_seconds'], 901)
                        self.assertEqual(heartbeat['saved_rounds'], 2)

    def test_stale_orphan_recovery_preserves_full_report_for_each_reader(self):
        for suffix in ('/progress', '/view', ''):
            with self.subTest(endpoint=suffix):
                self.saved = report()
                original = self.save_at(100, status='running', recommendation=None, validation=None)
                with patch.object(pricing.time, 'time', return_value=1000):
                    result = server.get(self.path + suffix)
                self.assertEqual(result['status'], 'interrupted')
                complete = store.read(original['run_id'])
                self.assertIn('process stopped', complete['error'])
                self.assertEqual(complete['updated_at'], 1000)
                for key, value in original.items():
                    if key not in ('status', 'error', 'updated_at'):
                        self.assertEqual(complete[key], value, key)
                self.assertNotIn('saved_rounds', complete)
                self.assertNotIn('has_recommendation', complete)

    def test_fresh_heartbeat_winning_orphan_lock_race_is_not_interrupted(self):
        original = self.save_at(100, status='running', recommendation=None, validation=None)
        refreshed = copy.deepcopy(original)
        refreshed['rounds'].append({**copy.deepcopy(refreshed['rounds'][-1]), 'round': 3})
        refreshed['progress']['completed_rounds'] = 3
        refreshed['counts']['provider_calls'] = 99
        real_lock = pricing.exclusive_lock

        @contextmanager
        def heartbeat_before_lock(path):
            with real_lock(path):
                store.save(refreshed)
                yield

        with patch.object(pricing.time, 'time', return_value=1000):
            with patch.object(pricing, 'exclusive_lock', heartbeat_before_lock):
                heartbeat = server.get(self.path + '/progress')
        self.assertEqual(heartbeat['status'], 'running')
        self.assertEqual(heartbeat['saved_rounds'], 3)
        self.assertEqual(heartbeat['counts']['provider_calls'], 99)
        self.assertEqual(heartbeat['elapsed_seconds'], 900)
        self.assertEqual(store.read(original['run_id']), refreshed)

    def test_locally_active_or_process_locked_run_is_not_interrupted(self):
        original = self.save_at(100, status='running', recommendation=None, validation=None)
        with patch.object(pricing.time, 'time', return_value=1000):
            with patch.object(pricing, '_active', {original['run_id']}):
                with patch.object(pricing, 'exclusive_lock', side_effect=AssertionError('Locally owned run lock')):
                    self.assertEqual(server.get(self.path + '/progress')['status'], 'running')
            with patch.object(pricing, 'exclusive_lock', side_effect=ValueError('A batch is already running')):
                with patch.object(store, 'read', side_effect=AssertionError('Locked report read')):
                    self.assertEqual(server.get(self.path + '/progress')['status'], 'running')
        self.assertEqual(store.read(original['run_id']), original)


if __name__ == '__main__':
    unittest.main()

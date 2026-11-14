"""Report and export boundaries redact even structurally valid provider text."""
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from backend import adaptive_store as store
from backend import adaptive_pricing


SECRET = 'sk-fake-adaptive-test-secret-123456789'


class AdaptiveStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path_patch = patch.object(store, 'BASE', Path(self.temp.name))
        self.env_patch = patch.dict('os.environ', {'LLM_API_KEY': SECRET})
        self.path_patch.start()
        self.env_patch.start()
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(self.path_patch.stop)
        self.addCleanup(self.env_patch.stop)

    def run_payload(self):
        return {'run_id': 'adaptive-safe-test', 'status': 'completed', 'created_at': time.time(),
                'rounds': [{'decision': {'action': 'BUY_MEMBER', 'reason': f'The fare is affordable; key {SECRET}.'}}],
                'recommendation': {'reason': SECRET}, 'config': {'Authorization': f'Bearer {SECRET}'}}

    def test_valid_provider_reason_is_redacted_in_database_and_api_payload(self):
        run = self.run_payload()
        store.save(run)
        store.record(run['run_id'], {'raw_response_text': f'Upstream echoes {SECRET}'})
        with store.connection() as db:
            row = db.execute('SELECT payload FROM adaptive_runs').fetchone()[0]
            event = db.execute('SELECT record FROM adaptive_events').fetchone()[0]
        self.assertNotIn(SECRET, row)
        self.assertNotIn(SECRET, event)
        self.assertIn('[REDACTED]', row)
        # These are the exact functions used by the HTTP GET routes.
        for payload in (adaptive_pricing.read(run['run_id']), adaptive_pricing.export_run(run['run_id']),
                        adaptive_pricing.events(run['run_id']), adaptive_pricing.list_runs()):
            self.assertNotIn(SECRET, json.dumps(payload))

    def test_read_boundaries_defend_against_legacy_unredacted_rows(self):
        run = self.run_payload()
        with store.connection() as db:
            db.execute('INSERT INTO adaptive_runs VALUES (?,?,?,?)',
                       (run['run_id'], store.encode(run), run['created_at'], run['created_at']))
            db.execute('INSERT INTO adaptive_events(run_id,recorded_at,record) VALUES (?,?,?)',
                       (run['run_id'], time.time(), store.encode({'raw_response_text': SECRET})))
        for payload in (store.read(run['run_id']), store.list_runs(), store.events(run['run_id']), store.export_run(run['run_id'])):
            self.assertNotIn(SECRET, json.dumps(payload))

    def test_inline_export_is_bounded_before_fetching_events(self):
        run = self.run_payload()
        store.save(run)
        store.record(run['run_id'], {'raw_response_text': 'x' * 1000})
        with patch.object(store, 'MAX_EXPORT_BYTES', 500):
            with self.assertRaisesRegex(ValueError, 'inline export limit'):
                store.export_run(run['run_id'])
            self.assertEqual(len(store.events(run['run_id'])['events']), 1)

    def test_pagination_requires_bounded_integers(self):
        run = self.run_payload()
        store.save(run)
        for limit, offset in ((True, 0), (1.5, 0), (1, .5), (1001, 0), (0, 0), (1, -1)):
            with self.assertRaises(ValueError): store.events(run['run_id'], limit, offset)
        for limit in (True, 1.5, 0, -1, 101):
            with self.assertRaises(ValueError): store.list_runs(limit)


if __name__ == '__main__':
    unittest.main()

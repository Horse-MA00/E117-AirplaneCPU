"""Read-only per-attempt analyst diagnostics, including pre-retry audits."""
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from backend import adaptive_store as store, adaptive_pricing, server
from backend.errors import NotFound


class AnalystAuditApiTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = patch.object(store, 'BASE', Path(temp.name))
        self.base.start()
        self.addCleanup(self.base.stop)
        self.run_id = 'adaptive-analyst-audit'
        store.save({'run_id': self.run_id, 'version': adaptive_pricing.VERSION,
                    'config': {'profile': 'flexible_deal_seekers'},
                    'status': 'completed', 'created_at': time.time(), 'rounds': []})

    def record(self, event, **fields):
        store.record(self.run_id, {'event': event, **fields})

    def test_attempts_are_grouped_and_raw_is_only_returned_for_selected_round(self):
        self.record('customer_response', raw_response_text='NEVER INCLUDE CUSTOMER RAW')
        raw = '<script>doNotExecute()</script>'
        self.record('analyst_request', round=1, attempt=1, context_sha256='a')
        self.record('analyst_response', round=1, attempt=1, raw_response_text=raw)
        self.record('analyst_failed', round=1, attempt=1, raw_response_text=raw,
                    error='A lower-price hypothesis needs a price objection',
                    error_type='ValueError', failure_kind='validation', provider_call=True)
        self.record('analyst_request', round=1, attempt=2, context_sha256='b')
        self.record('analyst_response', round=1, attempt=2, raw_response_text='{"corrected":true}')
        self.record('analyst_validated', round=1, attempt=2, validation='passed')
        self.record('analyst_request', round=2, attempt=1, context_sha256='c')

        summary = store.analysis_attempts(self.run_id)
        self.assertIsNone(summary['round'])
        self.assertEqual([(a['round'], a['attempt'], a['status']) for a in summary['attempts']],
                         [(1, 1, 'failed'), (1, 2, 'passed'), (2, 1, 'pending')])
        self.assertTrue(summary['attempts'][0]['raw_available'])
        self.assertNotIn('raw_response_text', json.dumps(summary))
        self.assertNotIn('request', json.dumps(summary))
        selected = store.analysis_attempts(self.run_id, 1)
        self.assertEqual(len(selected['attempts']), 2)
        self.assertEqual(selected['attempts'][0]['raw_response_text'], raw)
        self.assertEqual(selected['attempts'][0]['failure_kind'], 'validation')
        self.assertEqual(store.analysis_attempts(self.run_id, 3)['attempts'], [])

    def test_legacy_request_context_and_hash_recover_failed_uncompleted_round(self):
        request = {'messages': [{'role': 'system', 'content': 'private prompt'},
                               {'role': 'user', 'content': json.dumps({'round': 10, 'feedback': []})}]}
        self.record('analyst_request', request=request, context_sha256='legacy')
        self.record('analyst_response', request=request, context_sha256='legacy', raw_response_text='old original')
        self.record('analyst_failed', request=request, context_sha256='legacy',
                    raw_response_text='old original', error='Invalid analyst counts', error_type='ValueError')
        # A second old-style call is a separate attempt; its validated event only has a hash.
        self.record('analyst_request', request=request, context_sha256='legacy-second')
        self.record('analyst_response', request=request, context_sha256='legacy-second', raw_response_text='good')
        self.record('analyst_validated', context_sha256='legacy-second', validation='passed')
        result = store.analysis_attempts(self.run_id, 10)
        self.assertEqual([a['attempt'] for a in result['attempts']], [1, 2])
        self.assertEqual([a['status'] for a in result['attempts']], ['failed', 'passed'])
        self.assertEqual(result['attempts'][0]['error'], 'Invalid analyst counts')
        self.assertEqual(result['attempts'][0]['raw_response_text'], 'old original')
        self.assertNotIn('private prompt', json.dumps(result))

    def test_transport_and_budget_without_response_do_not_invent_raw_output(self):
        self.record('analyst_failed', round=2, attempt=1, error='timed out', error_type='TimeoutError',
                    provider_call=True, raw_response_text=None)
        self.record('analyst_failed', round=2, attempt=2, error='Live call budget exhausted',
                    error_type='CallBudgetExceeded', failure_kind='budget', provider_call=False)
        result = store.analysis_attempts(self.run_id, 2)['attempts']
        self.assertEqual([a['failure_kind'] for a in result], ['transport', 'budget'])
        self.assertEqual([a['provider_call'] for a in result], [True, False])
        self.assertTrue(all(not a['raw_available'] and a['raw_response_text'] is None for a in result))

    def test_cache_only_audit_is_passed_without_a_fresh_response(self):
        self.record('analyst_cache', round=3, attempt=1, context_sha256='cached-context',
                    source='provider_cache', provider_call=False, cache_hit=True,
                    analysis={'summary': 'A previously validated response.'})
        item = store.analysis_attempts(self.run_id, 3)['attempts'][0]
        self.assertEqual(item['status'], 'passed')
        self.assertFalse(item['provider_call'])
        self.assertFalse(item['raw_available'])
        self.assertIsNone(item['raw_response_text'])

    def test_legacy_unredacted_text_is_redacted_at_read_boundary(self):
        secret = 'sk-not-a-real-key-audit-test-123456789'
        value = {'event': 'analyst_failed', 'round': 1, 'attempt': 1,
                 'error': secret, 'error_type': 'ValueError', 'raw_response_text': secret}
        with store.connection() as db:
            db.execute('INSERT INTO adaptive_events(run_id,recorded_at,record) VALUES (?,?,?)',
                       (self.run_id, time.time(), store.encode(value)))
        with patch.dict('os.environ', {'LLM_API_KEY': secret}):
            for round_number in (None, 1):
                result = store.analysis_attempts(self.run_id, round_number)
                self.assertNotIn(secret, json.dumps(result))
                self.assertIn('[REDACTED]', json.dumps(result))

    def test_round_validation_unknown_run_and_bounded_response(self):
        for value in (True, False, 0, 31, -1, 1.5, '1'):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'round'):
                store.analysis_attempts(self.run_id, value)
        with self.assertRaisesRegex(ValueError, 'not found'):
            store.analysis_attempts('missing-run')
        self.record('analyst_response', round=1, attempt=1, raw_response_text='x' * 1000)
        with patch.object(store, 'MAX_EXPORT_BYTES', 500):
            self.assertEqual(len(store.analysis_attempts(self.run_id)['attempts']), 1)
            with self.assertRaisesRegex(ValueError, 'limit'):
                store.analysis_attempts(self.run_id, 1)

    def test_http_route_validates_current_run_and_round_query(self):
        self.record('analyst_failed', round=10, attempt=1, error='Invalid counts', error_type='ValueError')
        path = f'/api/adaptive-pricing/runs/{self.run_id}/analysis-attempts'
        self.assertEqual(server.get(path)['attempts'][0]['round'], 10)
        self.assertEqual(server.get(path, {'round': ['10']})['round'], 10)
        for value in ('bad', '0', '31', '1.5'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                server.get(path, {'round': [value]})
        with self.assertRaises(NotFound):
            server.get('/api/adaptive-pricing/runs/missing/analysis-attempts')
        old = store.read(self.run_id)
        old['version'] = 'retired-version'
        store.save(old)
        with self.assertRaises(NotFound):
            server.get(path)

    def test_payload_limit_counts_json_escaping_not_only_raw_text(self):
        self.record('analyst_response', round=1, attempt=1, raw_response_text='"' * 500)
        with patch.object(store, 'MAX_EXPORT_BYTES', 1000):
            self.assertEqual(len(store.analysis_attempts(self.run_id)['attempts']), 1)
            with self.assertRaisesRegex(ValueError, 'limit'):
                store.analysis_attempts(self.run_id, 1)


if __name__ == '__main__':
    unittest.main()

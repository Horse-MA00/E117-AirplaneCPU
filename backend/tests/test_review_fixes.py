"""Regression tests for the 2026-11-14 code-review fixes."""
import json
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

from backend import server
from backend.errors import NotFound
from backend.store import Store


class ServerHTTPFixes(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(Path(self.temp.name) / 'test.db')
        mock = patch.object(server, '_store', self.store)
        mock.start()
        self.addCleanup(mock.stop)
        self.http = server.Server(('127.0.0.1', 0), server.Handler)
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop)
        self.base = f'http://127.0.0.1:{self.http.server_port}'

    def stop(self):
        self.http.shutdown()
        self.http.server_close()
        self.thread.join(timeout=5)

    def status(self, path, body=None, headers=None):
        request = urllib.request.Request(self.base + path, data=None if body is None else json.dumps(body).encode(),
                                         headers={'Content-Type': 'application/json', **(headers or {})})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as error:
            return error.code, json.load(error)

    def test_backlog_is_raised(self):
        self.assertGreaterEqual(server.Server.request_queue_size, 64)

    def test_burst_of_concurrent_requests_is_not_reset(self):
        failures = []

        def hit():
            try:
                urllib.request.urlopen(self.base + '/api/health', timeout=30).read()
            except Exception as error:  # pragma: no cover - failure path
                failures.append(error)
        threads = [threading.Thread(target=hit) for _ in range(60)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        self.assertEqual(failures, [])

    def test_ipv6_loopback_host_is_allowed_and_foreign_host_rejected(self):
        self.assertEqual(self.status('/api/health', headers={'Host': f'[::1]:{self.http.server_port}'})[0], 200)
        self.assertEqual(self.status('/api/health', headers={'Host': 'evil.example:80'})[0], 403)
        self.assertEqual(self.status('/api/health', headers={'Host': '[bad'})[0], 403)

    def test_bad_query_is_400_and_missing_resource_is_404(self):
        code, body = self.status('/api/adaptive-pricing/runs/missing/events?limit=abc')
        self.assertEqual(code, 400)
        self.assertEqual(body['error'], 'limit must be an integer')
        self.assertEqual(self.status('/api/flights/NOPE')[0], 404)
        self.assertEqual(self.status('/api/optimization/runs/opt-0123456789abcdef')[0], 404)
        self.assertEqual(self.status('/api/agents/panels/panel-0123456789abcdef')[0], 404)
        self.assertEqual(self.status('/api/no-such-endpoint')[0], 404)
        self.assertEqual(self.status('/api/no-such-endpoint', {})[0], 404)

    def test_unexpected_key_error_is_a_logged_500_not_a_404(self):
        with patch.object(server, 'get', side_effect=KeyError('bug')), patch('traceback.print_exc'):
            self.assertEqual(self.status('/api/summary')[0], 500)

    def test_retired_offer_binding_is_rejected_before_forecasting(self):
        code, body = self.status('/api/offers', {'flight_id': 'SYN-00001', 'quantity': 1, 'base_fare': 70,
                                                 'optimization_run_id': 'opt-0123456789abcdef'})
        self.assertEqual(code, 400)
        self.assertIn('Retired optimization bindings', body['error'])

    def test_removed_methods_and_assets_return_404_without_redirects(self):
        routes = ('/api/optimize', '/api/pricing', '/api/pricing/status', '/api/pricing/runs',
                  '/api/optimization/status', '/api/optimization/runs', '/api/optimization/suggestions',
                  '/api/market', '/api/market/status', '/api/market/runs',
                  '/api/agents', '/api/agents/status', '/api/agents/panels',
                  '/api/personas', '/api/members', '/api/bookings',
                  '/api/agents/audits/old/export', '/api/continuous-pricing/status')
        for path in routes:
            for body in (None, {}):
                with self.subTest(path=path, method='GET' if body is None else 'POST'):
                    self.assertEqual(self.status(path, body)[0], 404)
        for path in ('/optimization.js', '/continuous.js', '/contribution-explanation.js',
                     '/price-chart.js', '/pricing-navigation.js'):
            with self.subTest(path=path):
                self.assertEqual(self.status(path)[0], 404)

    def test_current_status_exposes_only_eight_flexible_segments(self):
        code, status = self.status('/api/adaptive-pricing/status')
        self.assertEqual(code, 200)
        self.assertEqual(status['version'], server.adaptive_pricing.VERSION)
        self.assertEqual(len(status['populations']), 1)
        self.assertEqual(len(status['population']['segments']), 8)






if __name__ == '__main__':
    unittest.main()

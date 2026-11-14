"""Regression tests for the 2026-11-14 code-review fixes."""
import json
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

from backend import market_jobs, pricing, server
from backend.errors import NotFound
from backend.store import Store


# These tests pin flights, fares and expectations from the frozen legacy catalogue.
_legacy_dataset = None


def setUpModule():
    global _legacy_dataset
    from backend import data as _data
    _legacy_dataset = _data.use_dataset('legacy')
    _legacy_dataset.__enter__()


def tearDownModule():
    _legacy_dataset.__exit__(None, None, None)


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
        code, body = self.status('/api/optimization/suggestions?flight_id=SYN-00001&forecast_day=abc')
        self.assertEqual(code, 400)
        self.assertEqual(body['error'], 'forecast_day must be an integer')
        self.assertEqual(self.status('/api/optimization/suggestions?flight_id=SYN-00001&forecast_day=10')[0], 400)
        self.assertEqual(self.status('/api/flights/NOPE')[0], 404)
        self.assertEqual(self.status('/api/optimization/runs/opt-0123456789abcdef')[0], 404)
        self.assertEqual(self.status('/api/agents/panels/panel-0123456789abcdef')[0], 404)
        self.assertEqual(self.status('/api/no-such-endpoint')[0], 404)
        self.assertEqual(self.status('/api/no-such-endpoint', {})[0], 404)

    def test_unexpected_key_error_is_a_logged_500_not_a_404(self):
        with patch.object(server, 'get', side_effect=KeyError('bug')), patch('traceback.print_exc'):
            self.assertEqual(self.status('/api/summary')[0], 500)

    def test_bound_offer_without_day_uses_validated_default(self):
        code, body = self.status('/api/offers', {'flight_id': 'SYN-00001', 'quantity': 1, 'base_fare': 70,
                                                 'optimization_run_id': 'opt-0123456789abcdef'})
        self.assertEqual(code, 400)
        self.assertIn('stale', body['error'])


class LegacyBookingFixes(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(Path(self.temp.name) / 'demo.sqlite3')
        patcher = patch.object(server, 'store', return_value=self.store)
        patcher.start()
        self.addCleanup(patcher.stop)
        forecast = patch.object(server, 'forecast_for', side_effect=lambda *_: {'releasable_seats': 10})
        forecast.start()
        self.addCleanup(forecast.stop)
        self.offer = self.store.offer('SYN-00001', 28, 3, 70, 250, 10)
        self.store.join_plan('alice')
        self.store.join_plan('bob')

    def test_booking_cannot_move_the_simulation_clock(self):
        with self.assertRaisesRegex(ValueError, 'current simulation day D28'):
            server.post('/api/bookings', {'offer_id': self.offer['id'], 'customer_id': 'alice', 'days_to_departure': 20})
        self.assertEqual(self.store.release_status('SYN-00001', 28, 10)['simulation_day'], 28)
        booked = server.post('/api/bookings', {'offer_id': self.offer['id'], 'customer_id': 'alice', 'days_to_departure': 28})
        self.assertEqual(booked['booking']['total'], 320)

    def test_booking_checks_expected_total(self):
        with self.assertRaisesRegex(ValueError, 'price changed'):
            server.post('/api/bookings', {'offer_id': self.offer['id'], 'customer_id': 'bob', 'expected_total': 1})

    def test_unknown_offer_is_not_found(self):
        with self.assertRaises(NotFound):
            server.post('/api/bookings', {'offer_id': 'missing', 'customer_id': 'bob'})


class ValidationFixes(unittest.TestCase):
    def test_pricing_config_rejects_strings_and_null(self):
        for bad in ('300', 'many', None):
            with self.assertRaisesRegex(ValueError, 'customers must be a number'):
                pricing._config({'customers': bad})
        self.assertEqual(pricing._config({'customers': 300})['customers'], 300)

    def test_market_start_failure_releases_active_slot(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(market_jobs, 'BASE', Path(temporary)), \
                patch.object(market_jobs.threading, 'Thread', side_effect=RuntimeError('no threads')):
            with self.assertRaises(RuntimeError):
                market_jobs.start({'mode': 'deterministic'})
            self.assertEqual(market_jobs._active, set())


if __name__ == '__main__':
    unittest.main()

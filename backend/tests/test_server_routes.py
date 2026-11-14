"""Route-table behaviour of backend.server that callers rely on."""

import unittest
from unittest.mock import patch

from backend import server
from backend.errors import NotFound


class ServerRouteTests(unittest.TestCase):
    def test_unknown_paths_are_not_found(self):
        with self.assertRaisesRegex(NotFound, 'Not found'):
            server.get('/api/unknown')
        with self.assertRaisesRegex(NotFound, 'Not found'):
            server.post('/api/unknown', {})
        with self.assertRaisesRegex(NotFound, 'Adaptive pricing endpoint not found'):
            server.get('/api/adaptive-pricing/runs/abc/unknown-view')
        with self.assertRaisesRegex(NotFound, 'Account endpoint not found'):
            server.get('/api/member-portal/accounts/a/b')

    def test_offer_without_a_snapshot_for_the_day_is_a_client_error(self):
        # Previously a bare next() raised StopIteration and surfaced as HTTP 500.
        history = [{'days_to_departure': 28, 'normal_base_fare': 400, 'mandatory_fees': 250}]
        body = {'flight_id': 'NO-D14', 'days_to_departure': 14, 'quantity': 1, 'base_fare': 100}
        with (
            patch.object(server, 'forecast_for', return_value={'releasable_seats': 5}),
            patch.object(server.data, 'history', return_value=history),
        ):
            with self.assertRaisesRegex(ValueError, 'No booking snapshot for D14'):
                server.post('/api/offers', body)

    def test_flight_missing_from_catalogue_is_not_found(self):
        with (
            patch.object(server.data, 'history', return_value=[]),
            patch.object(server.data, 'flights', return_value=[]),
        ):
            with self.assertRaisesRegex(NotFound, 'Unknown flight'):
                server.get('/api/flights/GHOST')


if __name__ == '__main__':
    unittest.main()

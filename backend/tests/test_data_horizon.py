"""Release rounds a flight's booking data has not reached are rejected (backend/data_horizon.py)."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend import data, data_horizon, server
from backend.initial_policy import flight_scope
from backend.store import Store


def _stops_at_today(flight_id, today):
    """A feed that ends at `today` days to departure, like a real airline feed."""
    return [{'flight_id': flight_id, 'days_to_departure': day, 'capacity': 180, 'booked_seats': 40,
             'available_seats': 140} for day in range(180, today - 1, -1)]


class DataHorizonTests(unittest.TestCase):
    def setUp(self):
        real = data.histories()
        self.full = next(iter(real))
        histories = {**real, 'NEAR-TERM': _stops_at_today('NEAR-TERM', 28)}
        self.patch = patch.object(data, 'histories', return_value=histories)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def test_complete_histories_are_observed_through_departure(self):
        self.assertEqual(data_horizon.observed_through(self.full), 0)
        for day in (28, 14, 7, 0):
            self.assertEqual(data_horizon.require_observed(self.full, day), 0)

    def test_feed_stopping_today_rejects_later_rounds(self):
        self.assertEqual(data_horizon.observed_through('NEAR-TERM'), 28)
        self.assertEqual(data_horizon.require_observed('NEAR-TERM', 28), 28)
        with self.assertRaisesRegex(ValueError, r'D14 has not been reached yet .* runs to D28 \(dataset cutoff\); D14 is 14 days beyond that cutoff'):
            data_horizon.require_observed('NEAR-TERM', 14)
        with self.assertRaisesRegex(ValueError, 'D27 is 1 day beyond that cutoff'):
            data_horizon.require_observed('NEAR-TERM', 27)

    def test_unknown_flights_are_left_to_the_caller(self):
        self.assertIsNone(data_horizon.require_observed('NO-SUCH-FLIGHT', 7))

    def test_api_and_thompson_scope_apply_the_guard(self):
        with tempfile.TemporaryDirectory() as folder, \
                patch.object(server, 'store', return_value=Store(Path(folder) / 'test.sqlite3')), \
                patch.object(server, 'forecast_for', side_effect=AssertionError('must not forecast')):
            for path in ('/api/forecast', '/api/offers'):
                with self.assertRaisesRegex(ValueError, 'D7 has not been reached yet'):
                    server.post(path, {'flight_id': 'NEAR-TERM', 'days_to_departure': 7, 'quantity': 1, 'base_fare': 99})
        with patch.object(data, 'flights', return_value=[{'flight_id': 'NEAR-TERM'}]):
            with self.assertRaisesRegex(ValueError, 'D14 has not been reached yet'):
                flight_scope('NEAR-TERM', 14)

    def test_flight_detail_reports_the_horizon(self):
        self.assertEqual(server.get(f'/api/flights/{self.full}')['flight']['observed_through_day'], 0)


if __name__ == '__main__':
    unittest.main()

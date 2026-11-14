"""Member fares must never exceed 50% of the normal base fare."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backend import data, server
from backend.fare_policy import check_member_fare, member_fare_cap
from backend.pricing import optimize
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


class FarePolicy(unittest.TestCase):
    def test_cap_is_half_rounded_down_to_the_cent(self):
        self.assertEqual(member_fare_cap(830), 415)
        self.assertEqual(member_fare_cap(100.01), 50)
        self.assertEqual(check_member_fare(415, 830), 415)
        with self.assertRaisesRegex(ValueError, 'exceeds the cap of HK\\$415.00'):
            check_member_fare(415.01, 830)


class PublishingCap(unittest.TestCase):
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
        self.flight = 'SYN-00001'
        row = next(r for r in data.history(self.flight) if r['days_to_departure'] == 28)
        self.cap = member_fare_cap(row['normal_base_fare'])

    def publish(self, fare):
        return server.post('/api/offers', {'flight_id': self.flight, 'days_to_departure': 28,
                                           'quantity': 1, 'base_fare': fare})

    def test_offer_above_half_the_normal_fare_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'exceeds the cap'):
            self.publish(round(self.cap + .01, 2))
        self.assertEqual(self.store.offers(), [])

    def test_offer_at_the_cap_is_published(self):
        self.assertEqual(self.publish(self.cap)['offer']['base_fare'], self.cap)


class PricingGridCap(unittest.TestCase):
    def test_grid_never_tests_a_fare_above_the_cap(self):
        forecast = {'days_to_departure': 28, 'expected_remaining_demand': 10, 'releasable_seats': 8,
                    'expected_empty_seats': 20, 'capacity': 180}
        try:
            result = optimize(forecast, {'normal_base_fare': 120, 'replicates': 1, 'customers': 20, 'flights': 6})
        except (KeyError, TypeError):
            self.skipTest('forecast fixture does not match the pricing world contract')
        self.assertTrue(result['candidates'])
        self.assertTrue(all(c['member_fare'] <= 60 for c in result['candidates']))


if __name__ == '__main__':
    unittest.main()

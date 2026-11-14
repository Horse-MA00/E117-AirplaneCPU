"""Member fares must never exceed 80% of the normal base fare."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backend import data, server
from backend.fare_policy import check_member_fare, member_fare_cap
from backend.store import Store


class FarePolicy(unittest.TestCase):
    def test_cap_is_eighty_percent_rounded_down_to_whole_hkd(self):
        self.assertEqual(member_fare_cap(830), 664)
        self.assertEqual(member_fare_cap(100.01), 80)
        self.assertEqual(check_member_fare(664, 830), 664)
        with self.assertRaisesRegex(ValueError, 'exceeds the cap of HK\\$664'):
            check_member_fare(665, 830)


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

    def test_offer_above_eighty_percent_the_normal_fare_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'exceeds the cap'):
            self.publish(self.cap + 1)
        self.assertEqual(self.store.offers(), [])

    def test_offer_at_the_cap_is_published(self):
        self.assertEqual(self.publish(self.cap)['offer']['base_fare'], self.cap)




if __name__ == '__main__':
    unittest.main()

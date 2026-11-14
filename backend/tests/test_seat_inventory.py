import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend import server
from backend.store import Store


class SeatInventoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.inventory = Store(Path(self.temp.name) / 'demo.sqlite3')
        self.prediction = {'capacity':236, 'booked_seats':210, 'available_seats':26,
                           'protection_p90':19, 'releasable_seats':7, 'assumptions':[]}

    def response(self, day):
        with patch.object(server, 'store', return_value=self.inventory), patch.object(server, 'forecast_for', return_value=self.prediction):
            return server.post('/api/forecast', {'flight_id':'TEST-FLIGHT', 'days_to_departure':day})['forecast']

    def assert_partition(self, seats):
        self.assertEqual(sum(seats[k] for k in ('normal_booked','member_booked','normal_protected',
                                               'published_bookable','unpublished_headroom','held_seats')),
                         seats['capacity'])

    def test_seven_potential_seats_do_not_mean_seven_new_seats_off_round(self):
        f = self.response(13)
        seats = f['seat_inventory']
        self.assertEqual((seats['member_headroom'], seats['new_releasable_today'], seats['published_bookable']), (7,0,0))
        self.assertEqual(seats['next_release_day'],7)
        self.assertEqual(seats['release_state'],'not_release_day')
        self.assert_partition(seats)

    def test_prior_published_quota_is_bookable_without_issuing_it_again(self):
        self.inventory.offer('TEST-FLIGHT',28,7,70,250,7)
        seats = self.response(14)['seat_inventory']
        self.assertEqual((seats['member_headroom'],seats['published_bookable'],seats['new_releasable_today'],seats['unpublished_headroom']),(7,7,0,0))
        self.assertEqual(seats['release_state'],'published_quota_covers_headroom')
        self.assert_partition(seats)

    def test_sold_members_are_counted_once_in_physical_partition(self):
        offer = self.inventory.offer('TEST-FLIGHT',28,4,70,250,7)
        self.inventory.join_plan('customer')
        self.inventory.book(offer['id'],'customer',28,7)
        seats = self.response(14)['seat_inventory']
        self.assertEqual((seats['normal_booked'],seats['member_booked'],seats['occupied']),(210,1,211))
        self.assertEqual((seats['member_headroom'],seats['published_bookable'],seats['unpublished_headroom'],seats['new_releasable_today']),(6,3,3,3))
        self.assert_partition(seats)

    def test_zero_headroom_explains_risk_reserve_or_quality_hold(self):
        self.prediction.update(booked_seats=181,available_seats=55,protection_p90=145,releasable_seats=0)
        seats = self.response(28)['seat_inventory']
        self.assertEqual(seats['normal_protected'],55)
        self.assertEqual(seats['release_state'],'normal_demand_protected')
        self.assert_partition(seats)
        self.prediction.update(booked_seats=210,available_seats=26,protection_p90=19,releasable_seats=0)
        seats = self.response(28)['seat_inventory']
        self.assertEqual(seats['release_state'],'data_quality_hold')
        self.assertEqual(seats['held_seats'],7)
        self.assert_partition(seats)

    def test_issued_and_historical_rounds_have_explicit_reasons(self):
        self.inventory.offer('TEST-FLIGHT',14,3,70,250,7)
        self.assertEqual(self.response(14)['seat_inventory']['release_state'],'round_already_issued')
        self.assertEqual(self.response(28)['seat_inventory']['release_state'],'historical_view')

    def test_historical_held_quota_is_not_lost_from_headroom_breakdown(self):
        self.inventory.offer('TEST-FLIGHT',28,4,70,250,7)
        self.inventory.offer('TEST-FLIGHT',7,1,70,250,7)
        seats = self.response(13)['seat_inventory']
        self.assertEqual(seats['release_state'],'historical_view')
        self.assertIsNone(seats['next_release_day'])
        self.assertEqual((seats['member_headroom'],seats['unpublished_headroom'],seats['published_bookable'],seats['held_published_headroom']),(7,3,0,4))
        self.assert_partition(seats)

    def test_independent_snapshot_conflict_preserves_raw_confirmed_member_count(self):
        from backend.seat_inventory import describe
        prediction = {'capacity':180,'booked_seats':178,'protection_p90':20,'releasable_seats':0}
        release = {'member_sold':5,'currently_bookable':0,'remaining_risk_ceiling':0,
                   'total_active_unsold':0,'new_release_limit':0,'next_release_day':None,'round_already_issued':False}
        seats = describe(prediction,release,7)
        self.assertEqual((seats['confirmed_member_bookings'],seats['reported_occupied'],seats['member_inventory_overage']),(5,183,3))
        self.assertEqual(seats['new_releasable_today'],0)
        self.assert_partition(seats)


if __name__ == '__main__':
    unittest.main()

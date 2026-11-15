"""Flight simulation time stays independent of realtime membership/audit time."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend import member_portal, simulation_clock
from backend.store import Store, membership_expiry


class FlightSimulationClockTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'clock.sqlite3'
        # A historical departure remains usable in the synthetic simulation.
        self.schedule = {'departure_at': '2025-05-30T10:30:00+08:00', 'observed_through_day': 0}
        self.departure = simulation_clock.timestamp(self.schedule['departure_at'])
        self.cutoff = self.departure - 7200
        self.wall_now = simulation_clock.timestamp('2026-11-15T12:00:00+08:00')
        self.real_clock = patch('backend.store.time.time', return_value=self.wall_now)
        self.real_clock.start()
        self.addCleanup(self.real_clock.stop)
        self.store = Store(self.path, schedule_resolver=lambda _: self.schedule)

    def buy(self, offer, customer, day=None, limit=None):
        self.store.join_plan(customer)
        return self.store.book(offer['id'], customer, day=day, max_release=limit)

    def clock(self):
        with self.store.connect() as connection:
            return dict(connection.execute('SELECT * FROM flight_clocks WHERE flight_id=?', ('f',)).fetchone())

    def test_rounds_share_absolute_cutoff_and_count_carryover_and_sales_once(self):
        first = self.store.offer('f', 28, 4, 99, 0, 4)
        self.buy(first, 'a')
        d14 = self.store.release_status('f', 14, 7)
        self.assertEqual((d14['member_sold'], d14['previous_valid_unsold'], d14['new_release_limit']), (1, 3, 3))
        second = self.store.offer('f', 14, 3, 199, 0, 7)
        self.buy(first, 'b')
        d7 = self.store.release_status('f', 7, 10)
        self.assertEqual((d7['member_sold'], d7['previous_valid_unsold'], d7['new_release_limit']), (2, 5, 3))
        third = self.store.offer('f', 7, 3, 299, 0, 10)
        self.assertEqual({row['expires'] for row in (first, second, third)}, {self.cutoff})
        self.assertEqual({row['expires'] for row in self.store.offers()}, {self.cutoff})
        self.assertEqual(self.clock()['simulation_as_of'], self.departure - 7 * 86400)
        self.assertEqual(self.clock()['cutoff'], self.cutoff)
        state = self.store.release_status('f', 7, 10)
        self.assertEqual((state['member_sold'], state['total_active_unsold'], state['currently_bookable']), (2, 8, 8))
        self.assertEqual(first['created'], self.wall_now)
        self.assertLess(first['expires'], first['created'])  # Different, explicitly labelled time bases.

    def test_preview_does_not_advance_and_mutations_cannot_rewind(self):
        offer = self.store.offer('f', 28, 2, 99, 0, 4)
        self.store.release_status('f', 7, 4)
        self.assertEqual(self.clock()['day'], 28)
        self.buy(offer, 'a', day=14, limit=4)
        self.assertEqual(self.clock()['simulation_as_of'], self.departure - 14 * 86400)
        self.store.join_plan('b')
        with self.assertRaisesRegex(ValueError, 'rewind'):
            self.store.book(offer['id'], 'b', day=28, max_release=4)
        with self.assertRaisesRegex(ValueError, 'earlier dates'):
            self.store.offer('f', 28, 1, 99, 0, 4)
        self.assertEqual(self.clock()['day'], 14)

    def test_departure_day_is_past_sales_cutoff_and_expiry_boundary_is_exclusive(self):
        offer = self.store.offer('f', 7, 3, 99, 0, 3)
        self.store.join_plan('a')
        state = self.store.release_status('f', 0, 3)
        self.assertTrue(state['sales_cutoff_passed'])
        self.assertEqual(state['simulation_as_of'], state['sales_cutoff_at'])
        self.assertEqual(state['simulation_as_of'], '2025-05-30T08:30:00+08:00')
        metadata = simulation_clock.schedule_time(self.schedule, 0)
        self.assertEqual(metadata['simulation_as_of'], metadata['sales_cutoff_at'])
        self.assertEqual(metadata['simulation_as_of'], state['simulation_as_of'])
        self.assertEqual((state['currently_bookable'], state['total_active_unsold']), (0, 0))
        self.assertIsNone(state['next_release_day'])
        with self.assertRaisesRegex(ValueError, 'unavailable|closed'):
            self.store.book(offer['id'], 'a', day=0, max_release=3)
        # Explicit shorter entitlement: equality is expired in listing, status,
        # and checkout, while the flight's fixed sales cutoff is unchanged.
        with self.store.connect() as connection:
            connection.execute('UPDATE offers SET expires=? WHERE id=?', (self.departure - 7 * 86400, offer['id']))
        self.assertEqual(self.store.offers(), [])
        self.assertEqual(self.store.release_status('f', 7, 3)['currently_bookable'], 0)
        with self.assertRaisesRegex(ValueError, 'unavailable'):
            self.store.book(offer['id'], 'a')
        self.assertEqual(self.clock()['cutoff'], self.cutoff)

    def test_observed_data_bounds_previews_and_advancement_without_partial_writes(self):
        self.schedule['observed_through_day'] = 28
        offer = self.store.offer('f', 28, 2, 99, 0, 4)
        self.store.join_plan('a')
        before = self.clock()
        for operation in (
            lambda: self.store.release_status('f', 14, 4),
            lambda: self.store.offer('f', 14, 1, 99, 0, 4),
            lambda: self.store.book(offer['id'], 'a', day=14, max_release=4),
        ):
            with self.subTest(operation=operation), self.assertRaisesRegex(ValueError, 'D14 has not been reached'):
                operation()
        self.assertEqual(self.clock(), before)
        self.assertEqual(self.store.offer_info(offer['id'])['remaining'], 2)
        self.assertEqual(self.store.account('a')['bookings'], [])

    def test_wall_time_only_changes_membership_not_simulated_offer_availability(self):
        offer = self.store.offer('f', 28, 2, 99, 0, 3)
        member = self.store.join_plan('a')
        self.assertEqual(member['expires'], membership_expiry(self.wall_now))
        booking = self.store.book(offer['id'], 'a')['booking']
        self.assertEqual(booking['created'], self.wall_now)
        with patch('backend.store.time.time', return_value=member['expires']):
            self.assertFalse(self.store.account('a')['membership']['active'])
            self.assertEqual(len(self.store.offers()), 1)
            self.assertEqual(self.store.release_status('f', 28, 3)['currently_bookable'], 1)
            with self.assertRaisesRegex(ValueError, 'active demo membership'):
                self.store.book(offer['id'], 'a')

    def test_reload_preserves_prices_bookings_membership_and_absolute_clock(self):
        offer = self.store.offer('f', 28, 2, 99, 20, 3)
        booked = self.buy(offer, 'a')
        account = self.store.account('a')
        clock = self.clock()
        # Persisted absolute clocks stay absolute even in maintenance scripts
        # that do not pass the runtime catalogue resolver.
        reloaded = Store(self.path)
        self.assertEqual(reloaded.account('a'), account)
        self.assertEqual(reloaded.offer_info(offer['id'])['base_fare'], 99)
        self.assertEqual(reloaded.offer_info(offer['id'])['expires'], self.cutoff)
        self.assertEqual(reloaded.offer_info(offer['id'])['clock_version'], simulation_clock.VERSION)
        self.assertEqual(reloaded.account('a')['bookings'][0]['id'], booked['booking']['id'])
        self.assertEqual(self.clock(), clock)

    def test_member_portal_uses_current_flight_as_of_for_carried_offer(self):
        offer = self.store.offer('f', 28, 2, 99, 0, 4)
        self.store.offer('f', 14, 1, 199, 0, 4)
        self.store.join_plan('a')
        catalog = [{'flight_id': 'f', 'origin': 'HKG', 'destination': 'FUK',
                    'departure_at': self.schedule['departure_at'], 'capacity': 180}]
        seen = []
        def forecast(flight, day):
            seen.append((flight, day))
            return {'releasable_seats': 4}
        with patch.object(member_portal.data, 'flights', return_value=catalog), \
                patch.object(member_portal.data, 'history', return_value=[]):
            result = member_portal.flights(self.store, forecast)['flights'][0]
            self.assertEqual(result['offer_id'], offer['id'])
            self.assertEqual(result['simulation_as_of'], '2025-05-16T10:30:00+08:00')
            self.assertEqual(result['sales_cutoff_at'], '2025-05-30T08:30:00+08:00')
            self.assertEqual(result['membership_time_basis'], 'real_time')
            self.assertEqual(result['clock_version'], simulation_clock.VERSION)
            member_portal.book(self.store, forecast, 'a', offer['id'], expected_total=99)
        self.assertEqual({day for _, day in seen}, {14})


class SimulationClockMigrationTests(unittest.TestCase):
    def test_existing_database_retains_legacy_expiries_and_records(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'legacy.sqlite3'
            with sqlite3.connect(path) as connection:
                connection.executescript('''
                    CREATE TABLE offers(id TEXT PRIMARY KEY,flight_id TEXT,day INTEGER,quantity INTEGER,remaining INTEGER,base_fare REAL,fees REAL,created REAL,expires REAL);
                    CREATE TABLE members(customer_id TEXT PRIMARY KEY,fee REAL,created REAL,expires REAL);
                    CREATE TABLE bookings(id TEXT PRIMARY KEY,offer_id TEXT,flight_id TEXT,customer_id TEXT,total REAL,created REAL,UNIQUE(flight_id,customer_id));
                    CREATE TABLE flight_clocks(flight_id TEXT PRIMARY KEY,day INTEGER,risk_limit INTEGER,cutoff REAL);
                    INSERT INTO offers VALUES('old-offer','old-flight',28,3,2,123,45,1000,2000);
                    INSERT INTO members VALUES('old-member',299,1000,9000000);
                    INSERT INTO bookings VALUES('old-booking','old-offer','old-flight','old-member',168,1001);
                    INSERT INTO flight_clocks VALUES('old-flight',28,4,2000);
                ''')
            connection.close()
            schedule = {'departure_at': '2025-05-30T10:30:00+08:00', 'observed_through_day': 0}
            with patch('backend.store.time.time', return_value=1500):
                store = Store(path, schedule_resolver=lambda _: schedule)
                info = store.offer_info('old-offer')
                self.assertEqual((info['base_fare'], info['fees'], info['expires'], info['remaining']), (123, 45, 2000, 2))
                self.assertEqual(info['clock_version'], simulation_clock.LEGACY_VERSION)
                self.assertEqual(info['time_basis'], 'legacy_wall_clock')
                self.assertIsNone(info['simulation_as_of'])
                self.assertEqual(store.join_plan('old-member'), {'customer_id': 'old-member', 'fee': 299,
                                                                 'created': 1000, 'expires': 9000000})
                self.assertEqual(store.account('old-member')['bookings'][0]['id'], 'old-booking')
                self.assertEqual(store.release_status('old-flight', 14, 4)['member_sold'], 1)
                fresh = store.offer('new-flight', 28, 1, 99, 0, 3)
                self.assertEqual(fresh['clock_version'], simulation_clock.VERSION)
            with patch('backend.store.time.time', return_value=2000):
                self.assertNotIn('old-offer', [offer['id'] for offer in store.offers()])
                self.assertTrue(store.release_status('old-flight', 14, 4)['sales_cutoff_passed'])
                self.assertEqual(store.offer_info('old-offer')['expires'], 2000)

    def test_catalogue_schedule_uses_actual_departure_and_observed_horizon(self):
        from backend import data
        with patch.object(data, 'flights', return_value=[{'flight_id': 'f', 'departure_at': '2026-12-13T09:00:00+08:00'}]), \
                patch('backend.data_horizon.observed_through', return_value=28):
            metadata = simulation_clock.catalogue_time('f', 28)
            self.assertEqual(metadata['simulation_as_of'], '2026-11-15T09:00:00+08:00')
            with self.assertRaisesRegex(ValueError, 'has not been reached'):
                simulation_clock.catalogue_time('f', 14)
        with self.assertRaisesRegex(ValueError, 'timezone'):
            simulation_clock.timestamp('2026-12-13T09:00:00')

    def test_published_recent_catalogue_cannot_advance_past_observed_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(Path(directory) / 'recent.sqlite3',
                          schedule_resolver=simulation_clock.catalogue_schedule)
            flight_id = 'UO854-20261213'
            schedule = simulation_clock.catalogue_schedule(flight_id)
            self.assertEqual(schedule['observed_through_day'], 28)
            offer = store.offer(flight_id, 28, 1, 99, 0, 3)
            self.assertEqual(offer['simulation_as_of'], '2026-11-15T02:00:00+08:00')
            self.assertEqual(offer['sales_cutoff_at'], '2026-12-13T00:00:00+08:00')
            with self.assertRaisesRegex(ValueError, 'D14 has not been reached'):
                store.offer(flight_id, 14, 1, 99, 0, 3)
            self.assertEqual(store.offer_info(offer['id'])['sim_day'], 28)
            self.assertEqual(len(store.offers()), 1)


if __name__ == '__main__':
    unittest.main()

import concurrent.futures
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from backend.store import Store
from backend import server


class ThreeRoundStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.s = Store(Path(self.temp.name) / 'market.sqlite3')

    def buy(self, offer, start, count):
        for i in range(start, start + count):
            name = f'person-{i}'
            self.s.join_plan(name, 399)
            self.s.book(offer['id'], name)

    def test_second_and_third_round_deduct_all_valid_unsold_without_double_counting_sales(self):
        first = self.s.offer('f', 28, 40, 30, 250, 40)
        self.buy(first, 0, 10)
        second_state = self.s.release_status('f', 14, 60)
        self.assertEqual((second_state['member_sold'], second_state['previous_valid_unsold'], second_state['new_release_limit']), (10, 30, 20))
        second = self.s.offer('f', 14, 20, 30, 250, 60)
        self.buy(first, 10, 5)
        self.buy(second, 15, 2)
        third_state = self.s.release_status('f', 7, 80)
        self.assertEqual((third_state['member_sold'], third_state['previous_valid_unsold'], third_state['new_release_limit']), (17, 43, 20))
        self.s.offer('f', 7, 20, 30, 250, 80)
        state = self.s.release_status('f', 7, 80)
        self.assertEqual(state['total_active_unsold'], 63)
        self.assertEqual(state['member_sold'] + state['total_active_unsold'], 80)
        self.assertEqual(state['new_release_limit'], 0)
        self.assertTrue(state['round_already_issued'])
        self.assertEqual([r['day'] for r in state['round_history']], [28, 14, 7])

    def test_no_issuance_between_rounds_and_no_rewind(self):
        for day in (27, 15, 13, 8, 6, 1, 0):
            with self.subTest(day=day), self.assertRaisesRegex(ValueError, 'D28, D14 and D7'):
                self.s.offer('f', day, 1, 30, 250, 100)
        first = self.s.offer('f', 28, 10, 30, 250, 40)
        status = self.s.release_status('f', 13, 100)
        self.assertEqual(status['new_release_limit'], 0)
        self.assertEqual(status['previous_valid_unsold'], 10)
        self.assertEqual(status['next_release_day'], 7)
        # Read-only D13 preview does not skip the real D14 release round.
        self.s.offer('f', 14, 10, 30, 250, 40)
        with self.assertRaises(ValueError):
            self.s.offer('f', 28, 1, 30, 250, 100)
        self.s.join_plan('person', 399)
        with self.assertRaises(ValueError):
            self.s.book(first['id'], 'person', day=28, max_release=100)
        with self.assertRaises(ValueError):
            self.s.book(first['id'], 'person', day=0, max_release=100)

    def test_expired_unsold_not_deducted_but_sold_seats_remain_accounted(self):
        with patch('backend.store.time.time', return_value=1000):
            first = self.s.offer('f', 28, 10, 30, 250, 20)
            self.buy(first, 0, 2)
            # Simulate an explicitly shortened entitlement expiry, e.g. legacy offer.
            with self.s.connect() as c:
                c.execute('UPDATE offers SET expires=? WHERE id=?', (1001, first['id']))
        with patch('backend.store.time.time', return_value=1002):
            state = self.s.release_status('f', 14, 20)
            self.assertEqual((state['member_sold'], state['previous_valid_unsold'], state['new_release_limit']), (2, 0, 18))
            self.s.offer('f', 14, 18, 30, 250, 20)

    def test_shrinking_protection_preserves_entitlement_but_blocks_sale(self):
        first = self.s.offer('f', 28, 20, 30, 250, 20)
        self.buy(first, 0, 5)
        status = self.s.release_status('f', 14, 4)
        self.assertEqual(status['total_active_unsold'], 15)
        self.assertEqual(status['new_release_limit'], 0)
        self.assertEqual(status['currently_bookable'], 0)
        self.assertEqual(status['protection_shortfall'], 15)
        self.s.join_plan('extra', 399)
        with self.assertRaisesRegex(ValueError, 'protection'):
            self.s.book(first['id'], 'extra', day=14, max_release=4)
        self.assertEqual(self.s.offer_info(first['id'])['remaining'], 15)

    def test_passed_flight_cutoff_cannot_issue_an_expired_later_round(self):
        with patch('backend.store.time.time', return_value=1000):
            self.s.offer('f', 28, 10, 30, 250, 40)
        with patch('backend.store.time.time', return_value=1000 + 28 * 86400):
            state = self.s.release_status('f', 14, 40)
            self.assertEqual(state['new_release_limit'], 0)
            self.assertIsNone(state['next_release_day'])
            with self.assertRaisesRegex(ValueError, 'cutoff'):
                self.s.offer('f', 14, 10, 30, 250, 40)
            self.assertEqual(len(self.s.release_status('f', 14, 40)['round_history']), 1)

    def test_concurrent_same_round_publishes_only_once(self):
        def issue(_):
            try:
                return self.s.offer('f', 28, 1, 30, 250, 100)
            except ValueError:
                return None
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            offers = list(pool.map(issue, range(6)))
        self.assertEqual(sum(x is not None for x in offers), 1)

    def test_daily_forecast_separates_risk_ceiling_and_release_opportunity(self):
        f = {'capacity':180,'booked_seats':65,'available_seats':115,'protection_p90':57,
             'releasable_seats': 58, 'assumptions': []}
        with patch.object(server, 'store', return_value=self.s), patch.object(server, 'forecast_for', return_value=f):
            response = server.post('/api/forecast', {'flight_id': 'f', 'days_to_departure': 13})['forecast']
            self.assertEqual(response['risk_release_ceiling'], 58)
            self.assertEqual(response['releasable_seats'], 0)
            self.assertEqual(response['release_status']['next_release_day'], 7)
            self.assertNotIn('risk_release_ceiling', f)
            self.s.offer('f', 28, 10, 30, 250, 58)
            at14 = server.post('/api/forecast', {'flight_id': 'f', 'days_to_departure': 14})['forecast']
            self.assertEqual(at14['releasable_seats'], 48)

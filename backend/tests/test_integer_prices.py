"""Whole-HKD executable prices; observations and cost statistics keep precision."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from backend import server
from backend.initial_policy import flight_scope
from backend.fare_policy import integer_price, quoted_base_fare, member_fare_cap, final_member_fare
from backend.store import Store


class IntegerPriceTests(unittest.TestCase):
    def test_final_member_quote_threshold_and_ending_nine(self):
        cases = {0:0, 29:0, 29.99:0, 30:0, 38:0, 38.99:0,
                 39:39, 40:39, 99:99, 103:99, 249:249, 255:249,
                 259:259, 259.99:259, 328:319}
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(final_member_fare(raw), expected)
        for raw in range(5001):
            quote = final_member_fare(raw)
            self.assertIsInstance(quote, int)
            self.assertLessEqual(quote, raw)
            self.assertEqual(final_member_fare(quote), quote)
            self.assertTrue(quote == 0 or quote >= 30 and quote % 10 == 9)
        for invalid in (True, '255', -1, float('nan'), float('inf')):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                final_member_fare(invalid)
        # Marketing is an explicit final-offer operation, not ordinary quoting.
        self.assertEqual(quoted_base_fare(328.99), 328)
        self.assertEqual(member_fare_cap(410), 328)
        self.assertEqual(integer_price(399), 399)

    def test_decimal_observations_are_preserved_but_quotes_are_whole(self):
        self.assertEqual(quoted_base_fare(293.90), 293)
        self.assertEqual(member_fare_cap(410.99), 328)
        self.assertEqual(member_fare_cap(101.99), 80)
        self.assertEqual(integer_price(328.0), 328)
        for invalid in (True, '328', 328.01, float('nan'), float('inf'), -1):
            with self.subTest(value=invalid), self.assertRaisesRegex(ValueError, 'whole HKD'):
                integer_price(invalid)

    def test_scope_keeps_raw_quote_and_never_changes_nhpp_history(self):
        flight={'flight_id':'INTEGER-TEST','origin':'HKG','destination':'KMQ','departure_at':'2027-05-18T11:00:00+00:00'}
        history=[{'days_to_departure':28,'normal_base_fare':410.99,'capacity':180,'booked_seats':50,'available_seats':130,'empty_rate':130/180}]
        prediction={'expected_remaining_demand':10,'releasable_seats':100}
        with patch('backend.initial_policy.data.flights',return_value=[flight]), patch('backend.initial_policy.data.history',return_value=history), patch('backend.forecast.forecast',return_value=prediction) as forecast:
            result=flight_scope('INTEGER-TEST')
        self.assertEqual(result['normal_base_fare'],410)
        self.assertEqual(result['observed_normal_base_fare'],410.99)
        self.assertEqual(result['initial_member_fare'],328)
        self.assertEqual(forecast.call_args.args[0][0]['normal_base_fare'],410.99)
        self.assertEqual(history[0]['normal_base_fare'],410.99)


    def test_http_and_store_reject_fractional_new_quotes(self):
        with tempfile.TemporaryDirectory() as directory:
            store=Store(Path(directory)/'test.sqlite3')
            with patch.object(server,'store',return_value=store):
                with self.assertRaisesRegex(ValueError,'integer'):
                    server.post('/api/member-portal/plan',{'membership_fee':399.5})
            self.assertEqual(store.plan()['fee'],399)
            with self.assertRaisesRegex(ValueError,'whole HKD'):
                store.plan(399.5)
            with self.assertRaisesRegex(ValueError,'whole HKD'):
                store.offer('INTEGER-TEST',28,1,70.5,250.25,10)
            # Fees are separate pass-through amounts, not the executable base quote.
            offer=store.offer('INTEGER-TEST',28,1,70,250.25,10)
            self.assertEqual(offer['base_fare'],70)
            self.assertEqual(offer['fees'],250.25)

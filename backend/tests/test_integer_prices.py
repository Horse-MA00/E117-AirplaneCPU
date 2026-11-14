"""Whole-HKD executable prices; observations and cost statistics keep precision."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from backend import server, optimization
from backend.initial_policy import flight_scope, suggest
from backend.continuous_pricing import adaptive_search, optimize
from backend.fare_policy import integer_price, quoted_base_fare, member_fare_cap
from backend.pricing import _config as legacy_pricing_config
from backend.store import Store


class IntegerPriceTests(unittest.TestCase):
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
        with patch('backend.initial_policy.data.flights',return_value=[flight]), patch('backend.initial_policy.data.history',return_value=history), patch('backend.nhpp.forecast',return_value=prediction) as forecast:
            result=flight_scope('INTEGER-TEST')
        self.assertEqual(result['normal_base_fare'],410)
        self.assertEqual(result['observed_normal_base_fare'],410.99)
        self.assertEqual(result['initial_member_fare'],328)
        self.assertEqual(forecast.call_args.args[0][0]['normal_base_fare'],410.99)
        self.assertEqual(history[0]['normal_base_fare'],410.99)

    def test_submitted_fractional_quotes_rejected_before_simulation(self):
        for key in ('initial_member_fare','initial_membership_fee','fare_min','fare_max','fee_min','fee_max'):
            with self.subTest(key=key), self.assertRaisesRegex(ValueError,'whole HKD'):
                optimization.validate({key:70.5})
        for key in ('price_min','price_max','membership_fee'):
            with self.subTest(key=key), self.assertRaises(ValueError):
                optimize({key:70.5})
        with self.assertRaises(ValueError):
            adaptive_search(lambda p: {'search_score':p},0,70.5)
        with self.assertRaisesRegex(ValueError,'whole HKD'):
            suggest({'fare_max':500.5})
        with self.assertRaises(ValueError):
            legacy_pricing_config({'normal_base_fare':500.5})

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
        for endpoint in ('/api/agents/run','/api/agents/panels','/api/market/runs','/api/pricing/runs'):
            with self.subTest(endpoint=endpoint), self.assertRaisesRegex(ValueError,'whole HKD'):
                server.post(endpoint,{'member_fare':70.5})

    def test_whole_hkd_search_and_decimal_statistics_are_distinct(self):
        rows=adaptive_search(lambda p: {'price':p,'search_score':-(p-83.61)**2},0,200,31)
        self.assertTrue(all(type(r['price']) is int for r in rows))
        self.assertTrue(any(r['search_score'] != round(r['search_score']) for r in rows))

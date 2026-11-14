import unittest
from unittest.mock import patch
from backend.initial_policy import suggest


class InitialPolicyTests(unittest.TestCase):
    def test_scoped_suggestion_fixes_fee_even_when_request_overrides_it(self):
        scope = {'initial_member_fare': 245, 'history': []}
        for extra in ({}, {'initial_membership_fee': 49}, {'initial_membership_fee': 5001},
                      {'initial_membership_fee': None}, {'initial_membership_fee': '49'}):
            body = {'flight_id': 'selected-flight', **extra}
            with self.subTest(extra=extra), patch('backend.initial_policy.flight_scope', return_value=scope):
                result = suggest(body)
            self.assertEqual(result['initial_membership_fee'], 399)
            self.assertTrue(any('HK$399' in assumption for assumption in result['assumptions']))

    def test_only_as_of_quotes_used_and_costs_explicit(self):
        rows = {'a': [{'days_to_departure': 28, 'normal_base_fare': 400},
                      {'days_to_departure': 0, 'normal_base_fare': 99999}],
                'b': [{'days_to_departure': 28, 'normal_base_fare': 600}]}
        with patch('backend.initial_policy.data.histories', return_value=rows):
            result = suggest({'customers': 20})
        self.assertEqual(result['initial_member_fare'], 500)
        self.assertEqual(result['initial_membership_fee'], 180)
        self.assertEqual(result['source']['rows'], 2)
        self.assertEqual(result['cost_assumptions']['assumed_subscribers'], 10)

    def test_unavailable_quotes_are_not_zero_price(self):
        with patch('backend.initial_policy.data.histories', return_value={'a': [{'days_to_departure': 28, 'normal_base_fare': None}]}):
            with self.assertRaises(ValueError):
                suggest()

    def test_nonfinite_input_rejected(self):
        for value in (True, float('nan'), float('inf'), -1):
            with self.subTest(value=value), self.assertRaises(ValueError):
                suggest({'customers': value})

    def test_suggestion_respects_both_price_bounds(self):
        with patch('backend.initial_policy.data.histories', return_value={'a': [{'days_to_departure': 28, 'normal_base_fare': 400}]}):
            result = suggest({'fare_min': 200, 'fee_min': 1000})
        self.assertEqual(result['initial_member_fare'], 400)
        self.assertEqual(result['initial_membership_fee'], 1000)
        for value in ([], False, ''):
            with self.subTest(value=value), self.assertRaises(ValueError):
                suggest(value)

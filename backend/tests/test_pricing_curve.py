"""Pricing must retain the forecast's regime uncertainty when delaying opening."""
import unittest
import numpy as np
from backend import pricing


class ProtectionCurveTests(unittest.TestCase):
    def test_timing_preserves_late_shock_mass(self):
        prediction = {"days_to_departure": 3, "beta": 0,
                      "demand_curve": [
                          {"day": 3, "expected_remaining_demand": 10},
                          {"day": 2, "expected_remaining_demand": 9},
                          {"day": 1, "expected_remaining_demand": 8},
                          {"day": 0, "expected_remaining_demand": 0}]}
        np.testing.assert_array_equal(pricing._arrival_days(prediction, np.array([.05, .15, .5, .99])), [3, 2, 1, 1])

    def test_delayed_opening_uses_same_forecast_paths(self):
        prediction = {"days_to_departure": 28, "beta": 0,
                      "raw_protection_p90": 100, "protection_allowance": 16,
                      "protection_curve": [
                          {"day": 28, "protection_seats": 116},
                          {"day": 14, "protection_seats": 93},
                          {"day": 7, "protection_seats": 62}]}
        self.assertEqual(pricing._remaining_protection(prediction, 14), 93)
        self.assertEqual(pricing._remaining_protection(prediction, 7), 62)

    def test_incomplete_v2_curve_fails_closed(self):
        prediction = {"days_to_departure": 28, "protection_p90": 116,
                      "protection_curve": [{"day": 28, "protection_seats": 116}]}
        self.assertEqual(pricing._remaining_protection(prediction, 14), 116)

    def test_legacy_fallback_is_late_tail(self):
        prediction = {"days_to_departure": 28, "beta": .06,
                      "raw_protection_p90": 100, "protection_allowance": 16}
        self.assertGreater(pricing._remaining_protection(prediction, 14), 66)


if __name__ == '__main__':
    unittest.main()

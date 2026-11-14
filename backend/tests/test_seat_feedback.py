import copy
import unittest

from backend.seat_feedback import initial_profile, validate_profile, apply_profile, collect_samples, update_profile, diagnostics


class SeatFeedbackTests(unittest.TestCase):
    def test_adjustment_preserves_base_protection_and_quality_gate(self):
        p = initial_profile()
        p['horizons']['28'].update(rate_scale=.5, extra_protection=5)
        forecast = {'expected_remaining_demand': 20, 'protection_p90': 35,
                    'available_seats': 100, 'capacity': 180, 'releasable_seats': 0, 'expected_empty_seats': 80}
        a = apply_profile(forecast, p, 28)
        self.assertEqual(a['expected_remaining_demand'], 10)
        self.assertEqual(a['protection_p90'], 40)
        self.assertEqual(a['releasable_seats'], 0)
        self.assertEqual(forecast['expected_remaining_demand'], 20)

    def test_incomplete_world_cannot_supply_future_labels(self):
        with self.assertRaises(ValueError):
            collect_samples({'pending': None, 'cursor': 0, 'events': [{}]})

    def test_member_sales_excluded_and_denied_background_requests_retained(self):
        state = {'seed': 117, 'pending': None, 'cursor': 3,
                 'events': [{'kind': 'background', 'flight_id': 'F1', 'time': t} for t in (1, 3, 4)],
                 'flights': {'F1': {'quota_history': [{'day': 2, 'days_to_departure': 28,
                    'expected_remaining_demand': 10, 'protection_p90': 20, 'effective_normal_protection': 100}]}},
                 'bookings': {'member': {'flight_id': 'F1', 'customer_id': 'A', 'booked_day': 3, 'normal_seats': 0},
                              'party': {'flight_id': 'F1', 'customer_id': 'B', 'booked_day': 3, 'normal_seats': 2},
                              'background': {'flight_id': 'F1', 'customer_id': None, 'booked_day': 3, 'normal_seats': 1}}}
        samples = collect_samples(state)
        self.assertEqual(samples[0]['actual_normal_requests'], 4)
        self.assertEqual(samples[0]['background_requests'], 2)
        self.assertEqual(samples[0]['accepted_foreground_normal_seats'], 2)
        self.assertEqual(samples[0]['base_protection'], samples[0]['protection'])

    def test_replayed_worlds_not_counted_as_new_samples(self):
        row = {'sample_id': '1:F1:28', 'days_to_departure': 28, 'actual_normal_requests': 100,
               'base_expected': 10, 'base_protection': 20}
        profile = update_profile(initial_profile(), [row]*50)
        self.assertEqual(profile['horizons']['28']['samples'], 1)
        self.assertLessEqual(profile['horizons']['28']['rate_scale'], 2)
        self.assertEqual(profile['horizons']['28']['extra_protection'], 4)

    def test_no_negative_protection_even_under_overprediction(self):
        row = {'sample_id': '1:F1:28', 'days_to_departure': 28, 'actual_normal_requests': 0,
               'base_expected': 1000, 'base_protection': 2000}
        profile = update_profile(initial_profile(), [row])
        self.assertEqual(profile['horizons']['28']['rate_scale'], .5)
        self.assertEqual(profile['horizons']['28']['extra_protection'], 0)

    def test_invalid_profile_rejected(self):
        for bad in (float('nan'), float('inf'), -1, True, 10):
            profile = initial_profile()
            profile['horizons']['28']['rate_scale'] = bad
            with self.subTest(value=bad), self.assertRaises(ValueError):
                validate_profile(profile)

    def test_reduced_excess_demand_does_not_invent_empty_seats(self):
        profile = initial_profile()
        profile['horizons']['28']['rate_scale'] = .5
        forecast = {'expected_remaining_demand': 100, 'protection_p90': 130,
                    'available_seats': 5, 'capacity': 180, 'releasable_seats': 0, 'expected_empty_seats': 0}
        result = apply_profile(forecast, profile, 28)
        self.assertEqual(result['expected_empty_seats'], 0)
        self.assertEqual(result['empty_forecast_source'], 'frozen_base_nhpp')

    def test_diagnostics_do_not_modify_profile_or_claim_heldout_training(self):
        rows = [{'sample_id': '1:F1:28', 'days_to_departure': 28, 'actual_normal_requests': 20,
                 'base_expected': 10, 'expected': 15, 'base_protection': 18, 'protection': 21}]
        before = copy.deepcopy(rows)
        report = diagnostics(rows)['horizons']['28']
        self.assertEqual(report['base_mae'], 10)
        self.assertEqual(report['adjusted_mae'], 5)
        self.assertEqual(report['base_coverage'], 0)
        self.assertEqual(report['adjusted_coverage'], 1)
        self.assertEqual(rows, before)


if __name__ == '__main__':
    unittest.main()

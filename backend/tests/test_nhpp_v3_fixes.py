"""Regression tests for the three NHPP v3 fixes.

1. Weekend/holiday near-term surges: calendar prior plus a weekday-matched
   alarm that tightens protection between D28/D14/D7 (never issues quota).
2. Seven-day alignment: 35-day window, whole-week change points and a
   weekly-block slope likelihood.
3. Asymptotic significance gate on small releases.
"""
import copy
import unittest
from unittest.mock import patch

from backend import nhpp_v3 as nhpp
from backend.nhpp_v3 import forecast, surge_alarm, SETTINGS
from backend.shared_market import create_market, _automatic, _member_sellable, summarize

WEEK = [1, 1, 1, 1, 1.6, 1.8, .6]


def weekly_history(phase, base=10, days=100, capacity=5000, surge_last=0, surge=1.):
    """Flat trend, fixed weekday pattern; optional surge in the last N days."""
    rows, booked = [], 0
    for day in range(days, -1, -1):
        gross = 0 if day == days else round(base*WEEK[(day+phase) % 7])
        if 28 <= day < 28+surge_last:
            gross = round(gross*surge)
        booked += gross
        rows.append({'flight_id': 'WEEKLY', 'days_to_departure': day, 'capacity': capacity,
                     'booked_seats': booked, 'gross_bookings': gross, 'cancellations': 0,
                     'normal_total_fare': 500, 'interval_days': 22/24 if not day else 1})
    return rows


class SevenDayAlignmentTests(unittest.TestCase):
    def test_window_is_five_whole_weeks(self):
        result = forecast(weekly_history(0), 28, protection_allowance=0)
        self.assertEqual(result['intervals'], 35)
        self.assertEqual(result['intervals'] % 7, 0)

    def test_change_point_candidates_are_whole_weeks(self):
        self.assertTrue(all(k % 7 == 0 for k in SETTINGS['changepoint_candidate_days']))

    def test_pure_weekday_pattern_is_not_a_change_point(self):
        # v2 reported a 'down' change 5 days ago for this pattern at phase 0.
        for amplitude in (2., 2.5, 3.):
            pattern = [1, 1, 1, 1, 1, amplitude, amplitude]
            for phase in range(7):
                items = [{'start': -k-1, 'end': -k, 'count': round(6*pattern[(k+phase) % 7]), 'censored': False,
                          'price_factor': 1., 'block': k//7} for k in range(35)]
                self.assertIsNone(nhpp._change(items), (amplitude, phase))

    def test_slope_does_not_depend_on_weekday_phase(self):
        betas = {phase: forecast(weekly_history(phase), 28, protection_allowance=0)['beta'] for phase in range(7)}
        self.assertEqual(len(set(betas.values())), 1, betas)

    def test_real_weekly_level_shift_is_still_detected(self):
        rows = weekly_history(0, base=2, surge_last=7, surge=4)
        change = forecast(rows, 28, protection_allowance=0)['diagnostics']['change_point']
        self.assertEqual((change['days_ago'], change['direction']), (7, 'up'))


class ReleaseSignificanceTests(unittest.TestCase):
    def setUp(self):
        self.rows = weekly_history(0, base=6, capacity=900)
        for row in self.rows:
            row['booked_seats'] = min(row['booked_seats'], 700)
        self.raw = forecast(self.rows, 14, protection_allowance=0)
        self.available = self.raw['available_seats']

    def with_margin(self, margin):
        allowance = self.available-self.raw['raw_protection_p90']-margin
        return forecast(self.rows, 14, protection_allowance=allowance)

    def test_one_seat_margin_inside_sampling_error_is_held(self):
        result = self.with_margin(1)
        gate = result['diagnostics']['release_significance']
        self.assertEqual(gate['pre_threshold_release'], 1)
        self.assertGreater(gate['threshold_seats'], 1)
        self.assertEqual(result['releasable_seats'], 0)
        self.assertTrue(gate['held_by_threshold'])

    def test_clearly_significant_margin_is_released_unchanged(self):
        result = self.with_margin(20)
        self.assertEqual(result['releasable_seats'], 20)
        self.assertFalse(result['diagnostics']['release_significance']['held_by_threshold'])

    def test_every_release_exceeds_its_threshold(self):
        for seed in range(10):
            result = forecast(self.rows, 14, seed=seed)
            gate = result['diagnostics']['release_significance']
            self.assertTrue(result['releasable_seats'] == 0 or result['releasable_seats'] > gate['threshold_seats'])


class PeakDepartureTests(unittest.TestCase):
    def test_weekend_departure_uses_larger_near_term_shock_prior(self):
        rows = weekly_history(0, base=4, capacity=400)
        weekday = forecast(rows, 28, peak_departure_override=False)
        weekend = forecast(rows, 28, peak_departure_override=True)
        multiplier = SETTINGS['peak_departure_shock_prior_multiplier']
        self.assertAlmostEqual(weekend['diagnostics']['future_persistent_probability'],
                               round(weekday['diagnostics']['future_persistent_probability']*multiplier, 4))
        self.assertGreater(weekend['raw_protection_p90'], weekday['raw_protection_p90'])
        self.assertLessEqual(weekend['releasable_seats'], weekday['releasable_seats'])

    def test_calendar_is_read_from_schedule_or_explicit_holiday_flag(self):
        rows = weekly_history(0)
        saturday = [dict(r, departure_at='2027-05-15T07:00:00+08:00') for r in rows]
        tuesday = [dict(r, departure_at='2027-05-18T07:00:00+08:00') for r in rows]
        holiday = [dict(r, is_public_holiday='true') for r in tuesday]
        self.assertTrue(nhpp.peak_departure(saturday)['peak'])
        self.assertFalse(nhpp.peak_departure(tuesday)['peak'])
        self.assertTrue(nhpp.peak_departure(holiday)['peak'])
        self.assertEqual(nhpp.peak_departure(rows)['source'], 'unknown_calendar')


class SurgeAlarmTests(unittest.TestCase):
    def test_weekday_peaks_alone_never_alarm(self):
        for phase in range(7):
            rows = weekly_history(phase)
            for day in (27, 24, 20, 17):
                self.assertFalse(surge_alarm(rows, day)['alarm'], (phase, day))

    def test_recent_acceleration_alarms_before_next_round(self):
        rows, booked = [], 0
        for day in range(100, -1, -1):
            gross = 0 if day == 100 else (12 if 21 <= day <= 23 else 4)
            booked += gross
            rows.append({'flight_id': 'S', 'days_to_departure': day, 'capacity': 2000, 'booked_seats': booked,
                         'gross_bookings': gross, 'cancellations': 0, 'normal_total_fare': 500, 'interval_days': 1})
        self.assertFalse(surge_alarm(rows, 24)['alarm'])
        self.assertTrue(surge_alarm(rows, 21)['alarm'])


class InterRoundMonitorTests(unittest.TestCase):
    def setUp(self):
        self.state = create_market({'flight_count': 6, 'customer_count': 1}, 117, {'release_fraction': 1})
        self.flight = next(iter(self.state['flights'].values()))
        self.flight.update(capacity=100, occupied=20, legacy_seats=20)

    def snapshot(self, day, protection, alarm=False):
        f = self.flight
        prediction = {'model': 'test', 'days_to_departure': day, 'expected_remaining_demand': 0,
                      'raw_protection_p90': protection, 'protection_p90': protection,
                      'releasable_seats': max(0, f['capacity']-f['occupied']-protection), 'expected_empty_seats': 0}
        self.state['day'] = f['departure_at']-day
        with patch('backend.shared_market.forecast', return_value=prediction) as model, \
                patch('backend.shared_market.surge_alarm', return_value={'alarm': alarm}):
            _automatic(self.state, {'kind': 'snapshot', 'flight_id': f['flight_id'], 'day_to_departure': day, 'base_fare': 500})
        return model

    def test_alarm_between_rounds_blocks_unsold_quota_before_d14(self):
        self.snapshot(28, 40)                     # 40 member seats issued at D28.
        self.assertEqual(_member_sellable(self.flight), 40)
        model = self.snapshot(22, 75, alarm=True)  # Surge seen at D22, not D14.
        model.assert_called_once()
        self.assertEqual(self.flight['protection_remaining'], 75)
        self.assertEqual(_member_sellable(self.flight), 5)
        # Tighten-only: no new cohort, quota identity and checks preserved.
        self.assertEqual([c['round_day'] for c in self.flight['quota_cohorts']], [28])
        self.assertEqual(self.flight['member_remaining'], 40)
        self.assertTrue(self.flight['monitor_history'][-1]['tightened'])
        summary = summarize(self.state)
        self.assertTrue(all(summary['checks'].values()))
        self.assertEqual(summary['monitor_forecast_calls'], 1)

    def test_monitor_never_loosens_or_runs_without_alarm(self):
        self.snapshot(28, 40)
        self.assertFalse(self.snapshot(23, 0, alarm=False).called)
        before = copy.deepcopy(self.flight['protection_remaining'])
        self.snapshot(22, 5, alarm=True)          # Lower refreshed protection.
        self.assertEqual(self.flight['protection_remaining'], before)
        self.assertFalse(self.flight['monitor_history'][-1]['tightened'])
        self.assertEqual(len(self.flight['quota_history']), 1)


if __name__ == '__main__':
    unittest.main()

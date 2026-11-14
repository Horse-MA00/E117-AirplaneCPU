"""Cross-round quota conservation, capacity gating and fixed schedule regressions."""
import copy
import unittest
from unittest.mock import patch

from backend.release_policy import release_budget
from backend.shared_market import create_market, _automatic, _buy, _cancel, _member_sellable, summarize, next_observation, apply_decision
from backend.pricing import _config, _run, optimize
import numpy as np


class ReleaseRoundTests(unittest.TestCase):
    def setUp(self):
        self.state = create_market({'flight_count': 6, 'customer_count': 1}, 117, {'release_fraction': 1})
        self.flight = next(iter(self.state['flights'].values()))
        self.flight.update(capacity=100, occupied=20, legacy_seats=20)

    def issue(self, day, protection):
        f = self.flight
        forecast = {'model': 'test', 'days_to_departure': day, 'expected_remaining_demand': 0,
                    'raw_protection_p90': protection, 'protection_p90': protection,
                    'releasable_seats': max(0, f['capacity'] - f['occupied'] - protection), 'expected_empty_seats': 0}
        self.state['day'] = f['departure_at'] - day
        with patch('backend.shared_market.forecast', return_value=forecast):
            _automatic(self.state, {'kind': 'snapshot', 'flight_id': f['flight_id'], 'day_to_departure': day, 'base_fare': 500})

    def buy(self, count, member=True):
        for _ in range(count):
            _buy(self.state, self.flight['flight_id'], 'B' + str(len(self.state['bookings'])), None, None, 1, 0, member, 500)

    def test_second_and_third_subtract_all_valid_unsold_fifo(self):
        self.issue(28, 40)  # 80 physical - 40 protection = 40 first-round quota.
        self.buy(10)
        self.issue(14, 10)  # 70 physical - 10 protection - 30 carry = 30 NEW.
        self.buy(5)
        self.issue(7, 0)    # 65 physical - 0 protection - (25 + 30) carry = 10 NEW.
        records = self.flight['quota_history']
        self.assertEqual([r['new_allocation'] for r in records], [40, 30, 10])
        self.assertEqual([r['prior_valid_unsold'] for r in records], [0, 30, 55])
        self.assertEqual([c['remaining'] for c in self.flight['quota_cohorts']], [25, 30, 10])
        self.assertEqual(self.flight['member_remaining'], 65)
        self.assertTrue(all(summarize(self.state)['checks'].values()))

    def test_duplicate_round_and_between_round_never_issue(self):
        self.issue(28, 40)
        before = copy.deepcopy(self.flight)
        self.issue(28, 0)
        self.assertEqual(self.flight, before)
        self.issue(13, 0)
        self.assertEqual(len(self.flight['quota_history']), 1)
        self.assertEqual(self.flight['member_remaining'], 40)

    def test_cancel_returns_physical_seat_without_replenishing_quota(self):
        self.issue(28, 40)
        self.buy(1)
        _cancel(self.state, 'B0')
        self.assertEqual(self.flight['occupied'], 20)
        self.assertEqual(self.flight['member_remaining'], 39)
        self.assertEqual(self.flight['quota_cohorts'][0]['sold'], 1)
        self.assertTrue(all(summarize(self.state)['checks'].values()))

    def test_cutoff_expires_unsold_but_not_sold_and_no_resurrection(self):
        self.issue(28, 40)
        self.buy(3)
        self.issue(0, 0)
        self.assertEqual(self.flight['member_remaining'], 0)
        self.assertEqual(self.flight['quota_cohorts'][0], {'round_day': 28, 'issued': 40, 'remaining': 0, 'sold': 3, 'expired': 37})
        self.assertEqual(_member_sellable(self.flight), 0)
        self.assertTrue(all(summarize(self.state)['checks'].values()))

    def test_shrinking_target_preserves_entitlements_but_gates_sale(self):
        self.issue(28, 40)
        self.issue(14, 70)
        r = self.flight['quota_history'][-1]
        self.assertEqual((r['prior_valid_unsold'], r['target_quota'], r['new_allocation']), (40, 10, 0))
        self.assertEqual(r['protection_shortfall'], 30)
        self.assertEqual(_member_sellable(self.flight), 10)
        self.buy(10)
        with self.assertRaisesRegex(ValueError, 'Insufficient'):
            self.buy(1)
        self.assertEqual(self.flight['member_remaining'], 30)

    def test_fraction_is_total_target_before_carry_subtraction(self):
        result = release_budget(90, 30, 20, .5)
        self.assertEqual((result['target_quota'], result['new_allocation'], result['remaining_quota']), (30, 10, 30))

    def test_old_engine_state_is_inspectable_but_cannot_mutate(self):
        self.state['version'] = 'shared-market-v2'
        old = copy.deepcopy(self.state)
        self.assertEqual(summarize(self.state)['version'], 'shared-market-v2')
        for operation in (lambda: next_observation(self.state), lambda: apply_decision(self.state, {})):
            with self.assertRaisesRegex(ValueError, 'older engine'):
                operation()
        self.assertEqual(self.state, old)

    def test_quick_screen_three_round_cohorts_even_without_customer_arrivals(self):
        cfg = _config({'customers': 20, 'flights': 6, 'replicates': 1})
        pred = {'days_to_departure': 28, 'releasable_seats': 80, 'protection_p90': 20,
                'protection_curve': [{'day': 28, 'protection_seats': 60}, {'day': 14, 'protection_seats': 30}, {'day': 7, 'protection_seats': 10}]}
        world = {'forecast': pred, 'expected_trips': np.ones(20), 'flexibility': np.ones(20),
                 'min_notice': np.zeros(20), 'friction': np.zeros(20), 'join_uniform': np.zeros(20), 'baseline_profit': 0,
                 'events': [{'available': 100, 'departure_period_day': 50, 'ids': [], 'normal': [], 'days': [], 'willingness': []}]}
        result = _run(world, (30, 199, 28, 1), cfg, True)
        rounds = result['flights'][0]['quota_history']
        self.assertEqual([r['new_allocation'] for r in rounds], [40, 30, 20])
        self.assertEqual([r['prior_valid_unsold'] for r in rounds], [0, 40, 70])
        self.assertEqual(result['release_days'], [28, 14, 7])
        self.assertEqual(sum(c['expired'] for c in result['flights'][0]['quota_cohorts']), 90)

    def test_quick_screen_d13_waits_for_d7_and_d6_has_no_future_round(self):
        pred = {'available_seats': 100, 'releasable_seats': 70, 'protection_p90': 30,
                'expected_remaining_demand': 20, 'beta': .01, 'days_to_departure': 13}
        cfg = {'customers': 20, 'flights': 6, 'replicates': 1}
        report = optimize(pred, cfg)
        self.assertEqual(len(report['candidates']), 64)
        self.assertTrue(all(c['release_days'] == [7] and c['open_day'] == 7 for c in report['candidates']))
        report = optimize(dict(pred, days_to_departure=6), cfg)
        self.assertEqual(report['best']['decision'], 'NO_OFFER')
        self.assertEqual(report['candidates'], [])

    def test_zero_first_round_capacity_can_open_at_later_round(self):
        cfg = _config({'customers': 20, 'flights': 6, 'replicates': 1})
        pred = {'days_to_departure': 28, 'available_seats': 100, 'releasable_seats': 0, 'protection_p90': 120,
                'protection_curve': [{'day': 28, 'protection_seats': 120}, {'day': 14, 'protection_seats': 50}, {'day': 7, 'protection_seats': 20}]}
        world = {'forecast': pred, 'expected_trips': np.ones(20), 'flexibility': np.ones(20),
                 'min_notice': np.zeros(20), 'friction': np.zeros(20), 'join_uniform': np.zeros(20), 'baseline_profit': 0,
                 'events': [{'available': 100, 'departure_period_day': 50, 'ids': [0], 'normal': [False], 'days': [14], 'willingness': [1000]}]}
        result = _run(world, (30, 199, 28, 1), cfg, True)
        self.assertEqual([r['new_allocation'] for r in result['flights'][0]['quota_history']], [0, 50, 30])
        self.assertEqual(result['member_bookings'], 1)
        self.assertEqual(result['events'][0]['day'], 14)


if __name__ == '__main__':
    unittest.main()

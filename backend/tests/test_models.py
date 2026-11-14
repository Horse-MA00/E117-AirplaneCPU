import json
import unittest
from backend.nhpp import forecast


def history(decreasing=False):
    booked = 0
    rows = []
    for day in range(100, -1, -1):
        gross = (4 if day > 45 else 1) if decreasing else 1
        if day == 100:
            gross = 0
        booked += gross
        rows.append({"flight_id": "TEST", "days_to_departure": day,
                     "capacity": 600, "booked_seats": booked,
                     "gross_bookings": gross, "cancellations": 0,
                     "interval_days": 22/24 if not day else 1})
    return rows


class NHPPTests(unittest.TestCase):
    def test_asof_future_never_changes_prediction(self):
        rows = history()
        a = forecast(rows, 28)
        for r in rows:
            if r["days_to_departure"] < 28:
                r["gross_bookings"] = 999
                r["booked_seats"] = 500
        self.assertEqual(a, forecast(rows, 28))
        json.dumps(a, allow_nan=False)

    def test_negative_beta_and_bounds(self):
        result = forecast(history(True), 28)
        # This fixture is a step-down, now represented by a downward regime
        # change instead of forcing a permanently negative exponential slope.
        self.assertTrue(result["beta"] < 0 or result["diagnostics"]["change_point"]["direction"] == "down")
        self.assertGreaterEqual(result["expected_empty_rate"], 0)
        self.assertLessEqual(result["expected_empty_rate"], 1)
        self.assertLessEqual(result["releasable_seats"], result["available_seats"])

    def test_continuous_decline_still_allows_negative_beta(self):
        import math
        rows = history()
        booked = 0
        for index, row in enumerate(rows):
            row['gross_bookings'] = round(8*math.exp(-.035*index))
            booked += row['gross_bookings']
            row['booked_seats'] = booked
        result = forecast(rows, 28, protection_allowance=0)
        self.assertLess(result['beta'], 0)

    def test_regime_curves_use_uncapped_remaining_demand(self):
        result = forecast(history(), 28, protection_allowance=0)
        self.assertEqual(len(result['demand_curve']),29)
        self.assertAlmostEqual(result['demand_curve'][0]['expected_remaining_demand'], result['expected_remaining_demand'],places=2)
        self.assertEqual(result['demand_curve'][-1]['expected_remaining_demand'],0)
        values=[r['expected_remaining_demand'] for r in result['demand_curve']]
        self.assertEqual(values,sorted(values,reverse=True))

    def test_observed_level_jump_is_not_extrapolated_as_exponential_acceleration(self):
        rows=history();booked=0
        for row in rows:
            row['gross_bookings']=7 if 28<=row['days_to_departure']<35 else 1
            booked+=row['gross_bookings'];row['booked_seats']=booked
        result=forecast(rows,28,protection_allowance=0)
        self.assertEqual(result['diagnostics']['change_point']['direction'],'up')
        self.assertGreater(result['rate_now'],4)
        # A seven-day level shift should not be projected as continuing 6%/day
        # acceleration; V1 predicts 377 seats on this deterministic fixture.
        self.assertLess(result['expected_remaining_demand'],300)

    def test_right_censored_count_has_more_tail_mass_than_exact_count(self):
        import numpy as np
        from backend.nhpp import _sample
        record={'start':-1,'end':0,'count':5,'price_factor':1,'censored':False}
        exact=_sample([record],np.random.default_rng(117))[1]
        censored=_sample([dict(record,censored=True)],np.random.default_rng(117))[1]
        self.assertGreater(float(censored.mean()),float(exact.mean()))

    def test_stale_calibration_is_rejected(self):
        from unittest.mock import patch
        from backend.nhpp import _allowance
        with patch('backend.nhpp.Path.exists',return_value=True), patch('backend.nhpp.Path.read_text',return_value='{}'):
            with self.assertRaisesRegex(ValueError,'stale'):
                _allowance(28,None,50)

    def test_cancellations_are_not_negative_poisson_counts(self):
        rows = history()
        rows[-29]["cancellations"] = 4
        result = forecast(rows, 28)
        self.assertEqual(result["diagnostics"]["observed_gross_count"], 36)
        rows[-29]["gross_bookings"] = -1
        with self.assertRaises(ValueError):
            forecast(rows, 28)

    def test_cutoff_and_bad_inputs(self):
        result = forecast(history(), 0)
        self.assertEqual(result["expected_remaining_demand"], 0)
        self.assertEqual(result["releasable_seats"], 0)
        with self.assertRaises(ValueError):
            forecast([], 28)
        with self.assertRaises(ValueError):
            forecast(history(), 29)

    def test_calibration_changes_protection_not_prediction(self):
        raw = forecast(history(), 28, protection_allowance=0)
        guarded = forecast(history(), 28, protection_allowance=11.2)
        self.assertEqual(raw["expected_remaining_demand"], guarded["expected_remaining_demand"])
        self.assertEqual(raw["forecast_curve"], guarded["forecast_curve"])
        self.assertEqual(guarded["protection_p90"], raw["raw_protection_p90"]+12)
        self.assertLessEqual(guarded["releasable_seats"], raw["releasable_seats"])




if __name__ == "__main__":
    unittest.main()

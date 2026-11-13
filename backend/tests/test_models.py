import json
import unittest
from backend.nhpp import forecast
from backend.pricing import optimize, _config, _world, _run


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
        self.assertLess(result["beta"], 0)
        self.assertGreaterEqual(result["expected_empty_rate"], 0)
        self.assertLessEqual(result["expected_empty_rate"], 1)
        self.assertLessEqual(result["releasable_seats"], result["available_seats"])

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


class PricingTests(unittest.TestCase):
    def setUp(self):
        self.pred = {"available_seats": 100, "releasable_seats": 70,
                     "protection_p90": 30, "expected_remaining_demand": 20,
                     "beta": .01, "days_to_departure": 28}
        self.cfg = _config({"customers": 80, "flights": 6, "replicates": 1})

    def test_financial_identity_and_inventory(self):
        world = _world(self.pred, self.cfg, 117)
        result = _run(world, (70, 199, 28, 1), self.cfg, True)
        self.assertEqual(result["ledger"]["membership_revenue"], result["members"]*199)
        for f in result["flights"]:
            self.assertEqual(f["member_bookings"]+f["normal_bookings"]+f["remaining"], f["initial_available"])
            self.assertGreaterEqual(f["remaining"], 0)
        self.assertEqual(result, _run(world, (70, 199, 28, 1), self.cfg, True))

    def test_no_supply_no_membership_revenue(self):
        world = _world(dict(self.pred, releasable_seats=0), self.cfg, 117)
        result = _run(world, (0, 799, 28, 1), self.cfg)
        self.assertEqual(result["members"], 0)
        self.assertEqual(result["incremental_profit"], 0)

    def test_search_holds_best_and_term(self):
        result = optimize(self.pred, self.cfg)
        self.assertEqual(len(result["candidates"]), 192)
        best = [x["best_profit"] for x in result["trace"]]
        self.assertEqual(best, sorted(best))
        self.assertEqual(result["config"]["membership_days"], 365)
        json.dumps(result, allow_nan=False)

    def test_no_decisions_in_the_past(self):
        prediction = dict(self.pred, days_to_departure=7)
        result = optimize(prediction, self.cfg)
        self.assertTrue(all(r["open_day"] <= 7 for r in result["candidates"]))
        world = _world(prediction, self.cfg, 117)
        self.assertTrue(all(int(e["days"].max()) <= 7 for e in world["events"] if len(e["days"])))
        closed = optimize(dict(prediction, days_to_departure=0, expected_remaining_demand=0, releasable_seats=0), self.cfg)
        self.assertEqual(closed["best"]["decision"], "NO_OFFER")
        self.assertEqual(closed["candidates"], [])


if __name__ == "__main__":
    unittest.main()

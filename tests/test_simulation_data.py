import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from simulation.generate import generate, simulate_flight, validate


class SyntheticHistoryTests(unittest.TestCase):
    def test_reproducibility_inventory_and_cutoff(self):
        a = simulate_flight(3)
        self.assertEqual(a, simulate_flight(3))
        self.assertEqual(len(a["snapshots"]), 181)
        self.assertIsNone(a["snapshots"][-1]["normal_base_fare"])
        self.assertAlmostEqual(a["snapshots"][-1]["interval_days"], 22 / 24)
        for before, after in zip(a["snapshots"], a["snapshots"][1:]):
            self.assertEqual(after["booked_seats"], before["booked_seats"] + after["gross_bookings"] - after["cancellations"])
            self.assertGreaterEqual(after["available_seats"], 0)

    def test_demand_truth_not_in_public_features(self):
        a = simulate_flight(5)
        self.assertLess(a["truth"][0]["beta"], 0)
        for field in ("beta", "latent_scale", "demand_requests", "scenario"):
            self.assertNotIn(field, a["snapshots"][0])
        self.assertGreater(sum(x["demand_requests"] for x in simulate_flight(2)["truth"]), 0)

    def test_exact_rows_complete_last28_and_checksums(self):
        for rows in (29, 181, 182, 357, 500):
            with self.subTest(rows=rows), tempfile.TemporaryDirectory() as tmp:
                manifest = generate(rows, output=tmp)
                self.assertEqual(manifest["rows"], rows)
                self.assertEqual(validate(tmp)["rows"], rows)
                summaries = json.loads((Path(tmp) / "flights.json").read_text())
                self.assertTrue(all(s["history_start_day"] >= 28 for s in summaries))

    def test_compressed_bytes_reproduce(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            generate(362, output=a)
            generate(362, output=b)
            self.assertEqual((Path(a) / "snapshots.csv.gz").read_bytes(), (Path(b) / "snapshots.csv.gz").read_bytes())

    def test_bad_row_count(self):
        for count in (-1, 0, 28, True):
            with self.assertRaises(ValueError):
                generate(count)

    def test_evaluator_only_receives_asof_observations(self):
        from simulation.evaluate_nhpp import evaluate
        from backend.nhpp import forecast
        calls = []
        def observe(rows, **kwargs):
            self.assertTrue(all(r["days_to_departure"] >= 28 for r in rows))
            self.assertTrue(all("beta" not in r and "scenario" not in r for r in rows))
            calls.append(len(rows))
            return forecast(rows, **kwargs)
        with tempfile.TemporaryDirectory() as tmp:
            generate(724, output=tmp)
            with patch("simulation.evaluate_nhpp.forecast", side_effect=observe):
                result = evaluate(tmp, count=2)
        self.assertEqual(len(calls), 2)
        self.assertEqual(result["overall"]["flights"], 2)
        self.assertGreaterEqual(result["overall"]["p90_empirical_coverage"], 0)
        self.assertLessEqual(result["overall"]["p90_empirical_coverage"], 1)

    def test_calibration_and_holdout_are_disjoint(self):
        from simulation.calibrate_nhpp import calibrate
        with tempfile.TemporaryDirectory() as tmp:
            generate(20 * 181, output=tmp)
            result = calibrate(tmp, per_split=10)
            calibration = json.loads((Path(tmp) / "calibration.json").read_text())
            holdout = json.loads((Path(tmp) / "nhpp_holdout.json").read_text())
        self.assertTrue(result["disjoint"])
        self.assertEqual(len(calibration["calibration_flight_ids"]), 10)
        self.assertFalse(set(calibration["calibration_flight_ids"]) & set(holdout["flight_ids"]))
        self.assertGreaterEqual(calibration["allowance"], 0)
        self.assertEqual(holdout["protection_allowance"], calibration["allowance"])
        self.assertTrue(all(r["protection_p90"] == r["raw_protection_p90"] + calibration["allowance"] for r in holdout["flights"]))


if __name__ == "__main__":
    unittest.main()

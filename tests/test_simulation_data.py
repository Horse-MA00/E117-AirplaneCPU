import gzip
import json
import tempfile
import unittest
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


if __name__ == "__main__":
    unittest.main()

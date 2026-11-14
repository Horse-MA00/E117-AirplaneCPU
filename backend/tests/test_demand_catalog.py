import copy
import json
from pathlib import Path
import tempfile
import unittest

from backend import demand_catalog as demand


class DemandCatalogTests(unittest.TestCase):
    def test_thresholds_and_invalid_forecasts(self):
        for value, expected in [(0, "low"), (.599999, "low"), (.6, "medium"),
                                (.849999, "medium"), (.85, "high"), (1, "high")]:
            self.assertEqual(demand.classify(value), expected)
        for value in (None, True, "0.4", -1, 2, float("nan"), float("inf")):
            self.assertEqual(demand.classify(value), "unknown")

    def test_forecast_only_receives_as_of_allowed_observations(self):
        history = [{"flight_id": "f", "days_to_departure": 35, "capacity": 180, "scenario": "high"},
                   {"flight_id": "f", "days_to_departure": 28, "capacity": 180, "final_booked": 180},
                   {"flight_id": "f", "days_to_departure": 0, "normal_base_fare": 999999}]
        original = copy.deepcopy(history)
        def predictor(rows, days_to_departure, seed):
            self.assertEqual([r["days_to_departure"] for r in rows], [35, 28])
            self.assertFalse(any("scenario" in r or "final_booked" in r for r in rows))
            self.assertEqual((days_to_departure, seed), (28, 117))
            return {"capacity": 180, "expected_empty_seats": 90}
        row = demand.forecast_record("f", history, predictor)
        self.assertEqual(row["demand_band"], "low")
        self.assertEqual(row["demand_expected_load_rate"], .5)
        self.assertEqual(history, original)

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        for name in demand.SOURCE_FILES:
            path = self.root/name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("source")
        self.flights = [{"flight_id": "f", "scenario": "high", "final_empty_rate": 0}]
        self.record = {"flight_id": "f", "demand_band": "low", "demand_expected_load_rate": .4, "demand_reference_day": 28}

    def tearDown(self):
        self.directory.cleanup()

    def write_index(self, records=None):
        records = [self.record] if records is None else records
        counts = {}
        for row in records:
            counts[row["demand_band"]] = counts.get(row["demand_band"], 0)+1
        payload = {"version": demand.VERSION, "reference_day": 28, "forecast_seed": 117,
                   "thresholds": demand.THRESHOLDS, "source_files": demand.source_hashes(self.root),
                   "flight_count": len(records), "counts": counts,
                   "records_sha256": demand.records_digest(records), "records": records}
        (self.root/demand.INDEX_PATH).write_text(json.dumps(payload))

    def test_verified_index_enriches_without_mutating_catalogue_or_cached_records(self):
        self.write_index()
        result = demand.enrich(self.flights, self.root)
        self.assertEqual(result[0]["demand_band"], "low")
        self.assertEqual(result[0]["demand_source_status"], "current")
        self.assertNotIn("demand_band", self.flights[0])
        result[0]["demand_band"] = "high"
        self.assertEqual(demand.enrich(self.flights, self.root)[0]["demand_band"], "low")

    def test_missing_or_stale_index_remains_unknown(self):
        self.assertEqual(demand.enrich(self.flights, self.root)[0]["demand_source_status"], "missing")
        self.write_index()
        demand.enrich(self.flights, self.root)
        (self.root/demand.SOURCE_FILES[0]).write_text("changed model")
        result = demand.enrich(self.flights, self.root)[0]
        self.assertEqual(result["demand_source_status"], "stale")
        self.assertEqual(result["demand_band"], "unknown")
        self.assertIsNone(result["demand_expected_load_rate"])

    def test_corrupt_duplicate_and_partial_index_cannot_supply_bands(self):
        for records in ([{**self.record, "demand_band": "high"}], [self.record, self.record], []):
            self.write_index(records)
            result = demand.enrich(self.flights, self.root)[0]
            self.assertEqual(result["demand_band"], "unknown")
            self.assertEqual(result["demand_source_status"], "invalid")

    def test_published_catalogue_is_complete_and_matches_selected_fresh_forecasts(self):
        from backend import data
        flights = data.flights()
        self.assertEqual(len(flights), 1549)
        self.assertTrue(all(f["demand_source_status"] == "current" for f in flights))
        self.assertEqual({f["demand_band"] for f in flights}, {"low", "medium", "high"})
        for fid in ("SYN-00001", "NET-HKG-HND-20270515", "DEMO-HKG-HND-20270515"):
            expected = demand.forecast_record(fid, data.history(fid))
            actual = next(f for f in flights if f["flight_id"] == fid)
            self.assertEqual(actual["demand_band"], expected["demand_band"])
            self.assertEqual(actual["demand_expected_load_rate"], expected["demand_expected_load_rate"])


if __name__ == "__main__":
    unittest.main()

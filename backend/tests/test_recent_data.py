"""Near-term HK Express departures added to the catalogue (simulation/hkx_recent_generated, hkx-recent-2)."""
import hashlib
import json
import tempfile
import unittest
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch

from backend import data, data_horizon, server
from backend.initial_policy import flight_scope
from backend.store import Store
from simulation import hkx_recent_generate as generator

ROOT = data.ROOT
DIRECTORY = ROOT / "simulation/hkx_recent_generated"
EXISTING = ("simulation/generated", "simulation/network_generated", "simulation/member_demo_generated")


class RecentCatalogue(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((DIRECTORY / "manifest.json").read_text(encoding="utf-8"))
        cls.flights = json.loads((DIRECTORY / "flights.json").read_text(encoding="utf-8"))
        cls.anchor = date.fromisoformat(cls.manifest["anchor_date"])
        cls.recent_ids = {f["flight_id"] for f in cls.flights}

    def test_manifest_hashes_match_files(self):
        for name, digest in self.manifest["files"].items():
            self.assertEqual(hashlib.sha256((DIRECTORY / name).read_bytes()).hexdigest(), digest, name)
        self.assertEqual(self.manifest["flights"], len(self.flights))

    def test_existing_catalogue_is_kept_and_extended(self):
        existing = []
        for directory in EXISTING:
            existing += [f["flight_id"] for f in json.loads((ROOT / directory / "flights.json").read_text(encoding="utf-8"))]
        ids = [f["flight_id"] for f in data.flights()]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(set(ids), set(existing) | self.recent_ids)
        self.assertFalse(self.recent_ids & set(existing))
        manifest = data.manifest()
        self.assertEqual(manifest["catalog_flights"], len(ids))
        self.assertEqual(manifest["recent"]["generator_version"], "hkx-recent-2")
        # A current demand index labels every flight, old and new.
        self.assertTrue(all(f.get("demand_band") for f in data.flights()))

    def test_departures_sit_on_release_rounds_of_the_anchor_date(self):
        offsets = Counter(((datetime.fromisoformat(f["departure_at"]).date() - self.anchor).days, f["direction"])
                          for f in self.flights)
        self.assertEqual({d for d, leg in offsets if leg == "outbound"}, set(generator.HORIZONS))
        allowed = set(generator.HORIZONS) | {h + 1 for h in generator.HORIZONS}
        self.assertTrue({d for d, leg in offsets if leg == "inbound"} <= allowed)

    def test_nothing_after_the_anchor_date_is_published(self):
        for flight in self.flights:
            rows = data.history(flight["flight_id"])
            self.assertLessEqual(max(datetime.fromisoformat(r["snapshot_at"]).date() for r in rows), self.anchor)
            through = flight["observed_through_day"]
            self.assertEqual(data_horizon.observed_through(flight["flight_id"]), through)
            self.assertEqual(len(rows), 181 - through)
            self.assertLessEqual(through, generator.MAX_RELEASE_DAY)
            self.assertIsNone(flight["final_booked"])

    def test_rounds_not_reached_are_rejected_and_old_flights_are_not(self):
        d28 = next(f["flight_id"] for f in self.flights if f["observed_through_day"] == 28)
        d7 = next(f["flight_id"] for f in self.flights if f["observed_through_day"] == 7)
        with tempfile.TemporaryDirectory() as folder, \
                patch.object(server, "store", return_value=Store(Path(folder) / "test.sqlite3")):
            with self.assertRaisesRegex(ValueError, "D14 has not been reached yet"):
                server.post("/api/forecast", {"flight_id": d28, "days_to_departure": 14})
            with self.assertRaisesRegex(ValueError, "not been reached yet"):
                flight_scope(d28, 7)
            for flight_id in (d28, d7):
                result = server.post("/api/forecast", {"flight_id": flight_id, "days_to_departure": 28})
                self.assertEqual(result["forecast"]["days_to_departure"], 28)
            self.assertEqual(flight_scope(d7, 7)["as_of_day"], 7)
            # Flights used by the saved experiments keep complete histories.
            for flight_id in ("SYN-00017", "NET-HKG-KMQ-20270518", "DEMO-HKG-OKA-20270515"):
                self.assertEqual(data_horizon.observed_through(flight_id), 0)
                self.assertEqual(flight_scope(flight_id, 7)["as_of_day"], 7)


if __name__ == "__main__":
    unittest.main()

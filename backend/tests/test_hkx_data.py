"""HK Express network catalogue (simulation/hkx_generated, generator hkx-network-2)."""
import hashlib
import json
import unittest
from collections import Counter
from datetime import date, datetime

from backend import data
from simulation import hkx_generate as generator

ROOT = data.ROOT
DIRECTORY = ROOT / "simulation/hkx_generated"


class HkxCatalogue(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((DIRECTORY / "manifest.json").read_text())
        cls.flights = json.loads((DIRECTORY / "flights.json").read_text())

    def test_default_dataset_is_hkx(self):
        self.assertEqual(data.DATASET, "hkx")
        self.assertEqual(data.manifest()["dataset"], "hkx_generated")
        self.assertEqual(len(data.flights()), self.manifest["flights"])

    def test_manifest_hashes_match_committed_files(self):
        for name, digest in self.manifest["files"].items():
            self.assertEqual(hashlib.sha256((DIRECTORY / name).read_bytes()).hexdigest(), digest, name)
        profile = generator.PROFILE.read_bytes()
        self.assertEqual(hashlib.sha256(profile).hexdigest(), self.manifest["schedule_profile_sha256"])

    def test_every_destination_both_directions_and_every_fleet_type(self):
        routes = {(f["origin"], f["destination"]) for f in self.flights}
        for code, *_ in generator.DESTINATIONS:
            self.assertIn(("HKG", code), routes)
            self.assertIn((code, "HKG"), routes)
        self.assertEqual(len(generator.DESTINATIONS), 40)
        self.assertEqual({f["aircraft_type"] for f in self.flights}, {"A320", "A320neo", "A321", "A321neo"})
        self.assertEqual({f["capacity"] for f in self.flights}, {180, 188, 230, 236, 239})

    def test_no_duplicate_flights(self):
        self.assertEqual(len({f["flight_id"] for f in self.flights}), len(self.flights))
        physical = Counter((f["origin"], f["destination"], f["departure_at"]) for f in self.flights)
        self.assertEqual(max(physical.values()), 1)

    def test_schedule_is_reproducible_and_matches_the_weekday_template(self):
        self.assertEqual([f["flight_id"] for f in generator.schedule()], [f["flight_id"] for f in self.flights])
        profile = json.loads(generator.PROFILE.read_text())
        for date_text, _ in generator.DATES:
            weekday = date.fromisoformat(date_text).weekday()
            expected = {e["flight_number"] for e in profile["entries"] if e["weekday"] == weekday}
            actual = {f["flight_number"] for f in self.flights
                      if f["schedule_source"] == "oag_weekly_template" and f["direction"] == "outbound"
                      and f["departure_at"][:10] == date_text}
            self.assertEqual(actual, expected, date_text)

    def test_seasonal_routes_fly_only_in_summer(self):
        low, high = generator.SUMMER_SEASON
        seasonal = [f for f in self.flights if f["schedule_source"] == "assumed_summer_seasonal"]
        self.assertTrue(seasonal)
        for flight in seasonal:
            if flight["direction"] == "outbound":
                self.assertTrue(low <= flight["departure_at"][:10] <= high, flight["flight_id"])

    def test_inventory_identities_and_flows_on_every_flight(self):
        histories = data.histories()
        for flight in self.flights:
            rows = sorted(histories[flight["flight_id"]], key=lambda r: -r["days_to_departure"])
            self.assertEqual([r["days_to_departure"] for r in rows], list(range(180, -1, -1)))
            previous = None
            for row in rows:
                self.assertTrue(0 <= row["booked_seats"] <= row["capacity"])
                self.assertEqual(row["available_seats"], row["capacity"] - row["booked_seats"])
                if previous is not None:
                    self.assertEqual(row["booked_seats"],
                                     previous["booked_seats"] + row["gross_bookings"] - row["cancellations"])
                if row["normal_base_fare"] is not None:
                    self.assertEqual(row["quote_status"], "open")
                    self.assertEqual(row["normal_total_fare"], row["normal_base_fare"] + row["mandatory_fees"])
                previous = row
            self.assertEqual(flight["final_booked"], rows[-1]["booked_seats"])

    def test_stylized_fact_targets_hold(self):
        facts = self.manifest["stylized_facts"]
        for key, (low, high) in generator.TARGETS.items():
            self.assertTrue(low <= facts[key] <= high, (key, facts[key]))

    def test_departure_charges_follow_the_origin_country(self):
        for flight in self.flights[:200]:
            row = data.history(flight["flight_id"])[0]
            country = "HK" if flight["origin"] == "HKG" else flight["country"]
            self.assertEqual(row["mandatory_fees"], generator.DEPARTURE_CHARGES[country])

    def test_timestamps_are_hong_kong_time(self):
        for flight in self.flights[:200]:
            self.assertEqual(datetime.fromisoformat(flight["departure_at"]).utcoffset().total_seconds(), 8 * 3600)


if __name__ == "__main__":
    unittest.main()

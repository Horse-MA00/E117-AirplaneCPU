"""Behavioural checks for time ordering, inventory, provenance and reproducibility."""

from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
import unittest

from src.simulator import load_config, simulate_flight, validate_config


ROOT = Path(__file__).resolve().parents[1]


class SimulatorTests(unittest.TestCase):
    def setUp(self):
        self.config = load_config(ROOT / "configs" / "simulation.json")
        self.flight = deepcopy(self.config["demo_flight"])
        self.scenario = deepcopy(self.config["scenarios"][1])

    def simulate(self, config=None, scenario=None, seed=117, flight=None):
        return simulate_flight(
            self.flight if flight is None else flight,
            self.scenario if scenario is None else scenario,
            self.config if config is None else config,
            seed,
        )

    def test_seed_replays_all_data_and_different_seed_changes_path(self):
        original = self.simulate()
        self.assertEqual(original, self.simulate())
        self.assertNotEqual(original["events"], self.simulate(seed=118)["events"])

    def test_snapshots_and_sales_intervals_align_to_actual_cutoff(self):
        result = self.simulate()
        rows, events = result["snapshots"], result["events"]
        self.assertEqual([r["days_to_departure"] for r in rows], list(range(180, -1, -1)))
        self.assertEqual(len(events), 180)
        self.assertEqual(rows[0]["net_booked_seats"], 0)
        self.assertEqual(rows[0]["gross_new_bookings_1d"], 0)
        departure = datetime.fromisoformat(self.flight["departure_at"])
        cutoff = departure - timedelta(hours=self.config["cutoff_hours_before_departure"])
        self.assertEqual(datetime.fromisoformat(rows[-1]["observed_at"]), cutoff)
        self.assertEqual(rows[-1]["days_to_cutoff"], 0)
        for index, event in enumerate(events):
            self.assertEqual(event["interval_start_at"], rows[index]["observed_at"])
            self.assertEqual(event["interval_end_at"], rows[index + 1]["observed_at"])
            elapsed = (
                datetime.fromisoformat(event["interval_end_at"])
                - datetime.fromisoformat(event["interval_start_at"])
            ).total_seconds() / 86400
            self.assertAlmostEqual(elapsed, event["interval_days"])
            self.assertGreater(elapsed, 0)
        self.assertAlmostEqual(sum(e["interval_days"] for e in events), 180 - 2 / 24)

    def test_inventory_conservation_and_censoring_across_scenarios_and_seeds(self):
        for scenario in self.config["scenarios"]:
            for seed in (0, 1, 117, 999):
                with self.subTest(scenario=scenario["name"], seed=seed):
                    result = self.simulate(scenario=scenario, seed=seed)
                    rows = result["snapshots"]
                    capacity = self.flight["capacity"]
                    for index, event in enumerate(result["events"]):
                        self.assertEqual(event["booked_before"], rows[index]["net_booked_seats"])
                        self.assertEqual(event["booked_after"], rows[index + 1]["net_booked_seats"])
                        self.assertEqual(
                            event["booked_after"],
                            event["booked_before"] + event["accepted_bookings"] - event["cancellations"],
                        )
                        self.assertEqual(event["demand_requests"], event["accepted_bookings"] + event["denied_demand"])
                        self.assertLessEqual(event["accepted_bookings"], capacity - event["booked_before"])
                        self.assertLessEqual(event["cancellations"], event["booked_before"])
                        self.assertGreaterEqual(event["denied_demand"], 0)
                    for row in rows:
                        self.assertIsInstance(row["net_booked_seats"], int)
                        self.assertGreaterEqual(row["net_booked_seats"], 0)
                        self.assertLessEqual(row["net_booked_seats"], capacity)
                        self.assertEqual(row["available_to_sell"] + row["net_booked_seats"], capacity)
                        self.assertAlmostEqual(row["occupancy_rate"], row["net_booked_seats"] / capacity)
                    outcome = result["outcome"]
                    self.assertEqual(outcome["final_net_booked_seats"], rows[-1]["net_booked_seats"])
                    self.assertEqual(outcome["final_net_booked_seats"], outcome["total_accepted_bookings"] - outcome["total_cancellations"])
                    self.assertEqual(outcome["final_unsold"], capacity - rows[-1]["net_booked_seats"])

    def test_recent_features_are_past_flows_and_not_independent_draws(self):
        result = self.simulate()
        rows, events = result["snapshots"], result["events"]
        for index, row in enumerate(rows):
            past_week = events[max(0, index - 7):index]
            self.assertEqual(row["gross_new_bookings_7d"], sum(e["accepted_bookings"] for e in past_week))
            self.assertEqual(row["cancellations_7d"], sum(e["cancellations"] for e in past_week))
            self.assertEqual(row["net_pickup_7d"], row["net_booked_seats"] - rows[max(0, index - 7)]["net_booked_seats"])
            if index:
                self.assertEqual(row["net_pickup_1d"], row["net_booked_seats"] - rows[index - 1]["net_booked_seats"])
                self.assertEqual(row["gross_new_bookings_1d"], events[index - 1]["accepted_bookings"])
                self.assertEqual(row["cancellations_1d"], events[index - 1]["cancellations"])

    def test_quotes_have_consistent_components_and_close_at_d0(self):
        result = self.simulate()
        for row in result["snapshots"]:
            if row["is_available"]:
                self.assertGreaterEqual(row["base_fare"], self.config["price"]["minimum_base_fare"])
                self.assertLessEqual(row["base_fare"], self.config["price"]["maximum_base_fare"])
                self.assertEqual(row["total_payable"], row["base_fare"] + row["fuel_surcharge"] + row["taxes_and_mandatory_fees"])
                self.assertEqual(row["quote_status"], "open")
            else:
                for field in ("base_fare", "fuel_surcharge", "taxes_and_mandatory_fees", "total_payable"):
                    self.assertIsNone(row[field])
        self.assertFalse(result["snapshots"][-1]["is_available"])
        self.assertEqual(result["snapshots"][-1]["quote_status"], "closed")

    def test_extreme_demand_sells_out_without_erasing_denied_demand(self):
        config = deepcopy(self.config)
        config["daily_cancellation_rate"] = 0
        result = self.simulate(config=config, scenario={"name": "stress", "demand_multiplier": 100})
        self.assertEqual(result["outcome"]["final_unsold"], 0)
        self.assertGreater(result["truth"]["total_denied_demand"], 0)
        sold_out = [r for r in result["snapshots"] if r["quote_status"] == "sold_out"]
        self.assertTrue(sold_out)
        for row in sold_out:
            self.assertIsNone(row["base_fare"])
            self.assertIsNone(row["total_payable"])
            self.assertEqual(row["available_to_sell"], 0)

    def test_zero_demand_stays_empty_but_still_quotes_until_cutoff(self):
        config = deepcopy(self.config)
        config["reference_demand_per_seat"] = 0
        result = self.simulate(config=config)
        self.assertTrue(all(r["net_booked_seats"] == 0 for r in result["snapshots"]))
        self.assertTrue(all(r["is_available"] for r in result["snapshots"][:-1]))
        self.assertEqual(result["outcome"]["final_unsold"], self.flight["capacity"])
        self.assertEqual(result["truth"]["total_demand_requests"], 0)

    def test_full_cancellation_rate_respects_end_of_interval_order(self):
        config = deepcopy(self.config)
        config["daily_cancellation_rate"] = 1
        result = self.simulate(config=config)
        for event in result["events"]:
            self.assertEqual(event["cancellations"], event["booked_before"])
            self.assertEqual(event["booked_after"], event["accepted_bookings"])

    def test_future_promotion_does_not_change_prior_states(self):
        config = deepcopy(self.config)
        config["price"]["promotions"].append({"start_day": 5, "end_day": 1, "discount": 0.9})
        original, altered = self.simulate(), self.simulate(config=config)
        original_past = [r for r in original["snapshots"] if r["days_to_departure"] > 5]
        altered_past = [r for r in altered["snapshots"] if r["days_to_departure"] > 5]
        self.assertEqual(original_past, altered_past)
        self.assertNotEqual(original["events"][-5:], altered["events"][-5:])

    def test_observable_snapshots_exclude_latent_and_future_outcomes(self):
        result = self.simulate()
        forbidden = {"latent_theta", "demand_multiplier", "scenario", "seed", "expected_requests",
                     "demand_requests", "denied_demand", "final_net_booked_seats", "final_unsold"}
        for row in result["snapshots"]:
            self.assertFalse(forbidden.intersection(row))
            self.assertEqual(row["booking_source_kind"], "simulated")
            self.assertEqual(row["fare_source_kind"], "simulated")
            self.assertEqual(row["flight_source_kind"], "assumed_demo")
        self.assertIn("latent_theta", result["truth"])

    def test_invalid_config_values_are_rejected(self):
        for key, value in (("horizon_days", 27), ("horizon_days", True),
                           ("gamma_shape", 0), ("daily_cancellation_rate", 1.1),
                           ("price_elasticity", -1), ("reference_demand_per_seat", float("nan")),
                           ("cutoff_hours_before_departure", 24)):
            with self.subTest(key=key, value=value):
                config = deepcopy(self.config)
                config[key] = value
                with self.assertRaises(ValueError):
                    validate_config(config)
        config = deepcopy(self.config)
        config["price"]["promotions"] = [{"start_day": 3, "end_day": 8, "discount": 0.2}]
        with self.assertRaises(ValueError):
            validate_config(config)

    def test_invalid_capacity_timezone_scenario_and_seed_are_rejected(self):
        for capacity in (0, -1, 180.5, True):
            with self.subTest(capacity=capacity):
                flight = deepcopy(self.flight)
                flight["capacity"] = capacity
                with self.assertRaises(ValueError):
                    self.simulate(flight=flight)
        flight = deepcopy(self.flight)
        flight["departure_at"] = "2027-05-12T10:00:00"
        with self.assertRaises(ValueError):
            self.simulate(flight=flight)
        with self.assertRaises(ValueError):
            self.simulate(scenario={"name": "bad", "demand_multiplier": -1})
        with self.assertRaises(ValueError):
            self.simulate(seed=-1)


if __name__ == "__main__":
    unittest.main()

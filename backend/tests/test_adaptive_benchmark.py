"""Offline comparison protocol, disclosure and durable evidence checks."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from scripts.benchmark_adaptive_pricing import (
    run_benchmark, run_case, score_price, write_report, response_probability, train_policy,
)
from llm_agent.weighted_population import population


class AdaptiveBenchmarkTests(unittest.TestCase):
    def test_matched_budget_and_holdout_scores_are_reproducible(self):
        first = run_case(2026111400, "heterogeneous_logistic", "ample", customers=14,
                         rounds=3, holdout_customers=28)
        second = run_case(2026111400, "heterogeneous_logistic", "ample", customers=14,
                          rounds=3, holdout_customers=28)
        self.assertNotEqual(first["search_panel_sha256"], first["holdout_panel_sha256"])
        self.assertTrue(first["selection_frozen_before_holdout"])
        for a, b in zip(first["methods"], second["methods"]):
            self.assertEqual(a["trace"], b["trace"])
            self.assertEqual(a["price"], b["price"])
            self.assertEqual(a["expected_member_revenue"], b["expected_member_revenue"])
            self.assertEqual(a["synthetic_choice_opportunities"], 42)
            self.assertEqual(a["provider_calls"], 0)
            self.assertEqual(a["cap_violations"], 0)
            self.assertIn(a["price"], [row["price"] for row in a["trace"]])
            self.assertGreaterEqual(a["oracle_regret"], -1e-8)

    def test_exact_capacity_and_misspecified_family_are_exercised(self):
        people = population(28, 117, scope={"as_of_day": 28})
        ample = score_price(people, 150, 410, 28, 28, "reference_threshold")
        scarce = score_price(people, 150, 410, 1, 28, "reference_threshold")
        self.assertLessEqual(scarce["expected_member_sales"], 1)
        q = scarce["weighted_purchase_probability"]
        self.assertAlmostEqual(scarce["expected_member_sales"], 1 - (1 - q) ** 28)
        self.assertLess(scarce["expected_member_sales"], ample["expected_member_sales"])
        low = response_probability(people, 50, 410, "reference_threshold")
        high = response_probability(people, 300, 410, "reference_threshold")
        self.assertTrue(np.all(low >= high))

    def test_report_records_all_results_and_refuses_overwrite(self):
        report = run_benchmark(seed_count=1, customers=14, rounds=2, holdout_customers=14,
                               families=("reference_threshold",), capacities=("scarce",))
        self.assertEqual(len(report["cases"]), 1)
        self.assertEqual(report["provider_calls"], 0)
        self.assertEqual({m["method"] for m in report["cases"][0]["methods"]}, {"thompson", "greedy_map"})
        self.assertEqual(len(report["summary"]["groups"]), 4)  # family+capacity and all; both methods
        self.assertTrue(report["limitations"])
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "new-evidence"
            manifest = write_report(report, target)
            payload = (target / "report.json").read_bytes()
            self.assertEqual(manifest["files"]["report.json"]["sha256"], hashlib.sha256(payload).hexdigest())
            self.assertEqual(json.loads(payload)["config"]["member_fare_cap_ratio"], .8)
            with self.assertRaises(FileExistsError):
                write_report(report, target)

    def test_invalid_configuration_rejected(self):
        for changes in ({"seed_count": 0}, {"customers": 3}, {"rounds": 1}, {"families": ("fake",)}):
            with self.assertRaises(ValueError):
                run_benchmark(**changes)

    def test_repeated_person_price_does_not_reweight_training_data(self):
        people = population(14, 117, scope={"as_of_day": 28})
        with patch("scripts.benchmark_adaptive_pricing.recommend", return_value={"price": 328.}):
            result = train_policy(people, 410, 14, "heterogeneous_logistic", "thompson", 5, 117, .95)
        self.assertEqual(result["synthetic_choice_opportunities"], 70)
        self.assertEqual(result["unique_person_price_observations"], 14)
        self.assertEqual(result["fit_observations"], 14)
        self.assertEqual(result["repeated_person_price_observations"], 56)


if __name__ == "__main__":
    unittest.main()

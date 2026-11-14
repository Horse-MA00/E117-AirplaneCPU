"""Audience contracts for the optional, deal-triggered member experiment."""
import hashlib
import json
import unittest

from llm_agent.weighted_population import (
    DEFAULT_PROFILE, DEFAULT_WEIGHTS, LEGACY_PROFILE, LEGACY_WEIGHTS,
    allocate, metadata, population, validate_weights,
)


class FlexibleDealPopulationTests(unittest.TestCase):
    def test_default_excludes_mandatory_and_fixed_date_segments(self):
        people = population(80, 73119)
        excluded = {"fixed_holiday", "visiting_friends", "urgent_trip", "small_business", "family", "no_match"}
        self.assertEqual(len(DEFAULT_WEIGHTS), 8)
        self.assertFalse({p["segment"] for p in people} & excluded)
        self.assertTrue(all(p["trip_purpose"] == "optional_leisure" for p in people))
        self.assertTrue(all(p["trip_commitment"] == "not_planned_until_a_compelling_offer" for p in people))
        self.assertTrue(all(p["flexibility_days"] >= 7 for p in people))
        self.assertTrue(all(p["destination_openness"] == "any_served_destination" for p in people))
        self.assertTrue(all(p["price_sensitivity"] in {"high", "very_high"} for p in people))

    def test_traits_are_pre_price_and_do_not_read_optimizer_scope(self):
        first = population(28, 73120, scope={"as_of_day": 28, "member_fare": 80, "normal_fare": 410})
        second = population(28, 73120, scope={"as_of_day": 28, "member_fare": 320, "normal_fare": 900})
        self.assertEqual(first, second)
        self.assertTrue(all("willingness_to_pay" not in p and "desired_action" not in p for p in first))
        self.assertTrue(all(p["value_context"] and p["outside_option"] and p["booking_trigger"] for p in first))

    def test_all_release_days_are_usable_without_artificial_mandatory_demand(self):
        for day in (28, 14, 7):
            people = population(40, 73121, scope={"as_of_day": day})
            self.assertTrue(all(p["eligible"] and p["date_match"] and p["companions_confirmed"] for p in people))
        self.assertFalse(any(p["eligible"] for p in population(40, 73121, scope={"as_of_day": 0})))

    def test_existing_members_decide_for_only_one_person(self):
        people = population(28, 73122)
        self.assertTrue(all(p["membership_active"] and p["membership_valid_at_departure"] for p in people))
        self.assertTrue(all(p["party_size"] == 1 and p["own_ticket_only"] for p in people))
        self.assertTrue(all(p["response_language"] == "en" and p["currency"] == "HKD" for p in people))
        self.assertTrue(all(p["base_fare_budget"] > 0 for p in people))
        self.assertTrue(all("membership_fee" not in p and "taxes" not in p and "airline_cost" not in p for p in people))

    def test_target_weights_remain_exact_with_small_unequal_strata(self):
        people = population(20, 73123)
        self.assertEqual(len(people), 20)
        for key, share in DEFAULT_WEIGHTS.items():
            self.assertAlmostEqual(sum(p["population_weight"] for p in people if p["segment"] == key), share)
        self.assertAlmostEqual(sum(p["population_weight"] for p in people), 1.)
        only_students = {key: float(key == "student") for key in DEFAULT_WEIGHTS}
        self.assertEqual({p["segment"] for p in population(3, 117, weights=only_students)}, {"student"})
        self.assertEqual(sum(allocate(8).values()), 8)
        with self.assertRaises(ValueError):
            allocate(7)

    def test_legacy_generator_retains_exact_v1_people(self):
        people = population(28, 117, profile=LEGACY_PROFILE)
        digest = hashlib.sha256(json.dumps(people, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        self.assertEqual(digest, "796b4a78b642232290c07c6a46175197c86b24647bdd9be66b6f52dde8b4efa5")
        self.assertEqual(len({p["segment"] for p in people}), 14)
        self.assertEqual(validate_weights(profile=LEGACY_PROFILE), LEGACY_WEIGHTS)
        self.assertEqual(metadata(profile=LEGACY_PROFILE)["profile"], LEGACY_PROFILE)

    def test_profile_and_weight_mismatch_are_rejected(self):
        for call in (lambda: population(profile="invented"), lambda: metadata(profile="invented"),
                     lambda: allocate(28, profile="invented"),
                     lambda: population(weights=LEGACY_WEIGHTS),
                     lambda: population(weights=DEFAULT_WEIGHTS, profile=LEGACY_PROFILE)):
            with self.assertRaises(ValueError):
                call()

    def test_metadata_labels_assumptions_and_audience_selection(self):
        result = metadata(people=population(20, 73124))
        self.assertEqual(result["profile"], DEFAULT_PROFILE)
        self.assertEqual(sum(row["sample_count"] for row in result["segments"]), 20)
        self.assertEqual({row["id"] for row in result["available_profiles"]}, {DEFAULT_PROFILE, LEGACY_PROFILE})
        text = " ".join(result["limitations"])
        self.assertIn("test assumptions", text)
        self.assertIn("not a representative sample", text)
        self.assertTrue(all(row["weight"] == row["assumed_weight"] for row in result["segments"]))


if __name__ == "__main__":
    unittest.main()

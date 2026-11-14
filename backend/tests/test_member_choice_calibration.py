"""Pilot collection stays separate from synthetic evidence and model fitting."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from scripts.member_choice_calibration import make_study, response_template, summarize, write_study


def scope():
    return {"flight_id": "SYNTHETIC-HKG-KMQ", "origin": "HKG", "destination": "KMQ",
            "departure_date": "2027-05-18", "departure_time": "11:00", "as_of_day": 28,
            "normal_base_fare": 410, "releasable_seats": 73,
            "base_fare_budget": 999, "latent_willingness_to_pay": 123,
            "future_bookings": 77, "private_persona": "never display this"}


def completed(template, index=0, action="BUY_MEMBER"):
    value = copy.deepcopy(template)
    value["responses"][index].update(source="human_self_report", action=action,
                                     reason="An optional short break would appeal to me at this fare.",
                                     answered_at="2026-11-14T16:00:00+08:00")
    return value


class MemberChoiceCalibrationTests(unittest.TestCase):
    def setUp(self):
        self.study = make_study(scope(), participants=24, seed=120017)
        self.template = response_template(self.study)

    def test_cases_use_whole_quotes_and_exclude_private_simulator_personas(self):
        self.assertEqual(self.study, make_study(scope(), participants=24, seed=120017))
        prices = [case["context"]["member_base_fare_hkd"] for case in self.study["cases"]]
        self.assertEqual(prices, [164, 246, 328])
        self.assertTrue(all(isinstance(price, int) and 0 <= price <= 328 for price in prices))
        self.assertTrue(all(case["context"]["normal_base_fare_hkd"] == 410 for case in self.study["cases"]))
        contents = json.dumps(self.study)
        for private in ("base_fare_budget", "latent_willingness_to_pay", "future_bookings", "private_persona"):
            self.assertNotIn(private, contents)
        self.assertEqual(self.study["provider_calls"], 0)

    def test_assignment_is_balanced_and_one_quote_per_anonymous_participant(self):
        assignments = self.study["assignments"]
        self.assertEqual(len({row["participant_id"] for row in assignments}), 24)
        for case in self.study["cases"]:
            self.assertEqual(sum(row["case_id"] == case["case_id"] for row in assignments), 8)
        self.assertNotEqual(assignments, make_study(scope(), participants=24, seed=120018)["assignments"])
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)/"pilot"
            result = write_study(self.study, target)
            self.assertEqual(result["recorded_responses"], 0)
            files = list((target/"participants").glob("*.json"))
            self.assertEqual(len(files), 24)
            for path in files:
                person = json.loads(path.read_text())
                self.assertIn(person["case"]["case_id"], {case["case_id"] for case in self.study["cases"]})
                self.assertNotIn("cases", person)
                self.assertNotIn("assignments", person)
                self.assertIsNone(person["response"]["action"])
                self.assertIsNone(person["response"]["source"])
            with self.assertRaises(FileExistsError): write_study(self.study, target)

    def test_blank_template_is_not_human_data_or_negative_purchase_observations(self):
        result = summarize(self.study, self.template)
        self.assertEqual(result["status"], "awaiting_human_responses")
        self.assertEqual(result["recorded_responses"], 0)
        self.assertEqual(result["blank_rows"], 24)
        self.assertIsNone(result["response_source"])
        self.assertEqual(result["authenticity"], "no_observations")
        self.assertTrue(all(row["member_purchase_rate"] is None for row in result["by_price"]))
        self.assertFalse(result["automatic_model_updates"])

    def test_self_reports_aggregate_descriptively_without_reason_or_identity_leak(self):
        answers = completed(self.template)
        answers = completed(answers, 1, action="DECLINE")
        result = summarize(self.study, answers)
        self.assertEqual(result["recorded_responses"], 2)
        self.assertEqual(result["not_answered"], 22)
        self.assertEqual(result["response_source"], "human_self_report")
        self.assertEqual(result["authenticity"], "self_report_unverified")
        self.assertEqual(sum(row["BUY_MEMBER"] for row in result["by_price"]), 1)
        self.assertEqual(sum(row["DECLINE"] for row in result["by_price"]), 1)
        contents = json.dumps(result)
        self.assertNotIn(answers["responses"][0]["participant_id"], contents)
        self.assertNotIn(answers["responses"][0]["reason"], contents)

    def test_unknown_actions_sources_and_incomplete_answers_are_rejected(self):
        for changes in ({"source":"provider_live"}, {"source":"synthetic"}, {"source":None},
                        {"action":"WAIT"}, {"action":None}, {"answered_at":"2026-11-14T16:00:00"},
                        {"reason":None}, {"reason":"x"*1001}):
            answers = completed(self.template)
            answers["responses"][0].update(changes)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                summarize(self.study, answers)

    def test_duplicate_unknown_and_cross_context_responses_are_rejected(self):
        changed = completed(self.template)
        changed["responses"][1] = copy.deepcopy(changed["responses"][0])
        with self.assertRaises(ValueError): summarize(self.study, changed)
        for field, value in (("participant_id","unknown"), ("case_id","unknown"),
                             ("context_sha256","wrong-hash")):
            answers = completed(self.template)
            answers["responses"][0][field] = value
            with self.assertRaises(ValueError): summarize(self.study, answers)
        answers = completed(self.template)
        wrong_case = next(case for case in self.study["cases"] if case["case_id"] != answers["responses"][0]["case_id"])
        answers["responses"][0].update(case_id=wrong_case["case_id"], context_sha256=wrong_case["context_sha256"])
        with self.assertRaises(ValueError): summarize(self.study, answers)
        answers = completed(self.template)
        answers["study_id"] = "another-study"
        with self.assertRaises(ValueError): summarize(self.study, answers)

    def test_modified_displayed_study_is_rejected(self):
        changed = copy.deepcopy(self.study)
        changed["cases"][0]["context"]["member_base_fare_hkd"] += 1
        with self.assertRaises(ValueError): summarize(changed, self.template)
        with self.assertRaises(ValueError): make_study(scope() | {"releasable_seats":0})
        for count in (2, 301, True):
            with self.assertRaises(ValueError): make_study(scope(), participants=count)


if __name__ == "__main__":
    unittest.main()

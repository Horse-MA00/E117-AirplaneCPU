"""Exercise language/currency failures at the actual provider acceptance seam."""
import copy
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from llm_agent import audit, journey, journey_runner
from llm_agent.population import population
from llm_agent.output_contract import validate_english_output


class EnglishJourneyTests(unittest.TestCase):
    ENV = {"LLM_API_URL": "https://example.invalid/chat/completions", "LLM_API_KEY": "UNIT_TEST_ONLY", "LLM_MODEL": "test"}

    def test_provider_rejects_multilingual_or_foreign_currency_without_commit(self):
        for reason in ("會費399元不可退。", "会費399円は予算を圧迫します。", "The JPY 399 fee exceeds my budget."):
            with self.subTest(reason=reason), tempfile.TemporaryDirectory() as d:
                world = journey.initial_world(journey.enrich(population(1)[0], 0), 70, 399)
                before = copy.deepcopy(world)
                raw = {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps({"action": "DECLINE", "option_id": None, "reason": reason})}}]}
                with patch.object(audit, "BASE", Path(d)/"runs"), patch.dict("os.environ", self.ENV), patch.object(journey_runner, "_transport", return_value=io.BytesIO(json.dumps(raw).encode())):
                    record = audit.Audit("provider_live")
                    with self.assertRaises(ValueError):
                        choice = journey_runner.provider_decision(journey.packet_for(world), record)
                        journey.apply_decision(world, choice)
                    self.assertEqual(world, before)
                    events = audit.read_run(record.run_id)["records"]
                    self.assertTrue(any(x.get("raw_response") == raw for x in events))
                    self.assertTrue(any(x["event"] == "decision_failed" for x in events))
                    self.assertFalse(list((Path(d)/"llm_journey_cache").glob("*.json")))

    def test_valid_english_hkd_and_typographic_punctuation(self):
        validate_english_output({"reason": "The HKD 399 fee leaves HKD 408 — enough for the HKD 320 ticket, but availability isn’t guaranteed.", "reason_code": "AVAILABILITY_RISK"})
        validate_english_output({"reason": "I won't join because availability is uncertain; the bag weighs 20 pounds.", "reason_code": "AVAILABILITY_RISK"})

    def test_english_scenario_preserves_numeric_personas_and_makes_scope_explicit(self):
        people = [journey.enrich(p, i) for i, p in enumerate(population(5))]
        self.assertEqual([p["total_budget"] for p in people], [807, 853, 1270, 1258, 4387])
        self.assertEqual([p["language"] for p in people], ["zh-HK", "ja", "ja", "en", "en"])
        for person in people:
            self.assertTrue(person["segment_label"].isascii())
            context = journey.context_for(journey.initial_world(person, 70, 399))
            self.assertEqual(context["response_language"], "en")
            self.assertEqual(context["currency"], "HKD")
            self.assertIn("one detailed trip", context["budget_scope"])
            self.assertIn("current_quote_comparison", context)
        reference = journey.context_for(journey.initial_world(people[0], 70, 399))["current_quote_comparison"]
        self.assertEqual(reference["new_membership_plus_member_trip"], 719)
        self.assertEqual(reference["saving_on_one_trip_before_membership_fee"], 530)
        self.assertEqual(reference["saving_on_one_trip_after_new_membership_fee"], 131)

    def test_new_prompt_does_not_reuse_previous_cache(self):
        raw = {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps({"action": "DECLINE", "option_id": None, "reason": "I prefer to preserve my budget."})}}]}
        with tempfile.TemporaryDirectory() as d, patch.object(audit, "BASE", Path(d)/"runs"), patch.dict("os.environ", self.ENV), patch.object(journey_runner, "_transport", side_effect=lambda request: io.BytesIO(json.dumps(raw).encode())) as transport:
            packet = journey.packet_for(journey.initial_world(journey.enrich(population(1)[0], 0), 70, 399))
            journey_runner.provider_decision(packet, audit.Audit("provider_live"))
            # A changed system prompt creates a distinct request/cache identity.
            prompt = Path(d)/"changed.txt"
            prompt.write_text(journey.PROMPT.read_text()+"\nUse concise English.\n")
            with patch.object(journey_runner, "PROMPT", prompt):
                packet["system_prompt_sha256"] = __import__("hashlib").sha256(prompt.read_bytes()).hexdigest()
                journey_runner.provider_decision(packet, audit.Audit("provider_live"))
            self.assertEqual(transport.call_count, 2)

    def test_external_agent_import_rejects_non_english_without_state_commit(self):
        with tempfile.TemporaryDirectory() as d, patch.object(audit, "BASE", Path(d)/"runs"):
            suite = Path(d)/"suite"
            journey.export_suite(suite)
            before = (suite/"state.json").read_bytes()
            packet = json.loads((suite/"pending.jsonl").read_text().splitlines()[0])
            response = {"packet_id": packet["packet_id"], "context_sha256": packet["context_sha256"],
                        "decision": {"action": "DECLINE", "option_id": None, "reason": "不加入會員。"}}
            path = Path(d)/"response.jsonl"
            path.write_text(json.dumps(response))
            with self.assertRaisesRegex(ValueError, "English"):
                journey.import_responses(suite, path)
            self.assertEqual((suite/"state.json").read_bytes(), before)


if __name__ == "__main__":
    unittest.main()

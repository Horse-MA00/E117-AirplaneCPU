import copy
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from llm_agent import audit, journey, journey_runner
from llm_agent.population import population
from llm_agent.runner import run
from llm_agent import experiment


class JourneyTests(unittest.TestCase):
    def person(self, index=0):
        return journey.enrich(population(14)[index], index)

    def test_full_run_preserves_budget_and_existing_members(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(audit, "BASE", Path(temporary)/"runs"):
            result = run(count=14, scenario_mode="journey")
            self.assertEqual(result["summary"]["completed_stages"], 84)
            self.assertEqual(result["summary"]["existing_members"], 2)
            stored = audit.read_run(result["run_id"])
            self.assertEqual(stored["metadata"]["status"], "completed")
            self.assertTrue(stored["records"])
            for item in result["results"]:
                state = item["final_state"]
                self.assertAlmostEqual(state["remaining_budget"], item["person"]["total_budget"] - state["membership_fee_paid"] - state["ticket_spend"] + state["refund_received"])
                self.assertGreaterEqual(state["remaining_budget"], 0)
                if item["person"]["membership_active"]:
                    self.assertEqual(state["membership_fee_paid"], 0)
                before_end = item["events"][-2]["state_after"]["remaining_budget"]
                self.assertEqual(before_end, state["remaining_budget"])

    def test_future_event_hidden_and_no_member_soldout(self):
        w = journey.initial_world(self.person(), 0, 199)
        self.assertNotIn("change_scenario", journey.context_for(w)["person"])
        self.assertIsNone(journey.context_for(w)["person"]["existing_membership_days_remaining"])
        journey.apply_decision(w, {"action": "JOIN_PASS", "option_id": "pass"})
        journey.apply_decision(w, {"action": "WAIT", "option_id": None})
        c = journey.context_for(w)
        self.assertEqual(c["stage"], "quote_d14")
        self.assertTrue(any(x["unavailable_reason"] == "MEMBER_SOLD_OUT" for x in c["unavailable_options"]))
        self.assertFalse(any(x["action"] == "BUY_MEMBER" for x in c["legal_options"]))
        with self.assertRaises(ValueError):
            journey.apply_decision(w, {"action": "BUY_MEMBER", "option_id": "member"})

    def test_family_only_holder_discount_and_party_constraints(self):
        w = journey.initial_world(self.person(4), 30, 199)
        journey.apply_decision(w, {"action": "JOIN_PASS", "option_id": "pass"})
        c = journey.context_for(w)
        member = next(x for x in c["legal_options"] if x["id"] == "member")
        self.assertEqual(member["price_breakdown"]["companions_base_fare"], 1200)
        self.assertEqual(member["price"], sum(member["price_breakdown"].values()))
        journey.apply_decision(w, {"action": "WAIT", "option_id": None})
        c = journey.context_for(w)
        self.assertFalse(c["legal_options"])  # Family needs21days notice; D14too late.

    def test_cancellation_refund_and_no_double_purchase(self):
        w = journey.initial_world(self.person(), 0, 199)
        journey.apply_decision(w, {"action": "JOIN_PASS", "option_id": "pass"})
        journey.apply_decision(w, {"action": "BUY_MEMBER", "option_id": "member"})
        with self.assertRaises(ValueError):
            journey.apply_decision(w, {"action": "BUY_MEMBER", "option_id": "member"})
        journey.apply_decision(w, {"action": "KEEP_BOOKING", "option_id": None})
        journey.apply_decision(w, {"action": "KEEP_BOOKING", "option_id": None})
        c = journey.context_for(w)
        self.assertEqual(c["changed_circumstances"], "cannot_travel")
        journey.apply_decision(w, {"action": "CANCEL_BOOKING", "option_id": "cancel"})
        self.assertEqual(w["state"]["refund_received"], 50)
        self.assertEqual(w["state"]["membership_fee_paid"], 199)

    def test_export_import_hashes_and_failures_are_durable(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(audit, "BASE", Path(temporary)/"runs"):
            suite = Path(temporary)/"suite"
            journey.export_suite(suite)
            packets = [json.loads(x) for x in (suite/"pending.jsonl").read_text().splitlines()]
            self.assertEqual(len(packets), 28)
            responses = [{"packet_id": p["packet_id"], "context_sha256": p["context_sha256"],
                          "decision": journey.deterministic(p["context"])} for p in packets]
            bad = copy.deepcopy(responses)
            bad[0]["context_sha256"] = "WRONG"
            path = Path(temporary)/"responses.jsonl"
            path.write_text("\n".join(json.dumps(x) for x in bad))
            before = (suite/"state.json").read_bytes()
            with self.assertRaises(ValueError):
                journey.import_responses(suite, path)
            self.assertEqual((suite/"state.json").read_bytes(), before)
            run_id = json.loads(before)["suite_id"]
            self.assertTrue(any(r["event"] == "external_batch_rejected" for r in audit.read_run(run_id)["records"]))
            path.write_text("\n".join(json.dumps(x) for x in responses))
            result = journey.import_responses(suite, path)
            self.assertEqual(result["imported"], 28)
            self.assertTrue((suite/"packets-stage-0.jsonl").exists())
            self.assertTrue((suite/"packets-stage-1.jsonl").exists())
            with self.assertRaises(ValueError):
                journey.import_responses(suite, path)

    def test_audit_path_traversal_rejected(self):
        for value in ("../secret", "/tmp/a", "x/y", ""):
            with self.assertRaises(ValueError):
                audit.read_run(value)


class JourneyProviderTests(unittest.TestCase):
    ENV = {"LLM_API_URL": "https://example.invalid/chat/completions", "LLM_API_KEY": "UNIT_TEST_DUMMY_CREDENTIAL_123", "LLM_MODEL": "test-only"}

    def packet(self):
        w = journey.initial_world(journey.enrich(population(1)[0], 0), 0, 199)
        return journey.packet_for(w)

    def test_real_transport_and_cached_raw_record(self):
        raw = {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps({"action": "DECLINE", "option_id": None, "reason": "Keep budget"})}}], "usage": {"total_tokens": 123}}
        with tempfile.TemporaryDirectory() as temporary, patch.object(audit, "BASE", Path(temporary)/"runs"), patch.dict("os.environ", self.ENV), patch.object(journey_runner, "_transport", return_value=io.BytesIO(json.dumps(raw).encode())) as transport:
            first = audit.Audit("provider_live")
            result = journey_runner.provider_decision(self.packet(), first)
            second = audit.Audit("provider_live")
            repeat = journey_runner.provider_decision(self.packet(), second)
            self.assertEqual(result, repeat)
            self.assertEqual(transport.call_count, 1)
            records = audit.read_run(second.run_id)["records"]
            self.assertTrue(any(r.get("cache_hit") for r in records))
            self.assertTrue(any(r.get("raw_response") == raw for r in records))
            self.assertNotIn(self.ENV["LLM_API_KEY"], json.dumps(records))

    def test_invalid_provider_output_and_secret_recorded_safely(self):
        raw = {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps({"action": "BUY_MEMBER", "option_id": "member", "reason": self.ENV["LLM_API_KEY"]})}}]}
        with tempfile.TemporaryDirectory() as temporary, patch.object(audit, "BASE", Path(temporary)/"runs"), patch.dict("os.environ", self.ENV), patch.object(journey_runner, "_transport", return_value=io.BytesIO(json.dumps(raw).encode())):
            record = audit.Audit("provider_live")
            with self.assertRaises(ValueError):
                journey_runner.provider_decision(self.packet(), record)
            data = audit.read_run(record.run_id)
            self.assertTrue(any(r["event"] == "decision_failed" for r in data["records"]))
            self.assertTrue(any(r.get("raw_response_text") for r in data["records"]))
            self.assertNotIn(self.ENV["LLM_API_KEY"], json.dumps(data))

    def test_truncated_json_decision_is_rejected_and_preserved(self):
        raw = {"choices": [{"finish_reason": "length", "message": {"content": '{"action":"DECLINE","option_id":null}'}}]}
        with tempfile.TemporaryDirectory() as temporary, patch.object(audit, "BASE", Path(temporary)/"runs"), patch.dict("os.environ", self.ENV), patch.object(journey_runner, "_transport", return_value=io.BytesIO(json.dumps(raw).encode())):
            record = audit.Audit("provider_live")
            with self.assertRaises(ValueError):
                journey_runner.provider_decision(self.packet(), record)
            data = audit.read_run(record.run_id)
            self.assertTrue(any(r.get("raw_response") == raw for r in data["records"]))
            self.assertFalse(any(r.get("event") == "decision_validated" for r in data["records"]))


class ExperimentTests(unittest.TestCase):
    def test_bounded_batch_resumes_and_exports_records(self):
        def fake_provider(packet, record):
            decision = journey.deterministic(packet["context"])
            record.append({"event": "decision_validated", "source": "unit_test_mock", "packet": packet,
                           "raw_response": {"mock_decision": decision}, "usage": {"total_tokens": 1}})
            return decision
        with tempfile.TemporaryDirectory() as temporary, patch.object(audit, "BASE", Path(temporary)/"runs"):
            suite = Path(temporary)/"suite"
            experiment.create(suite)
            with patch.object(experiment, "provider_decision", side_effect=fake_provider):
                first = experiment.run_batch(suite, max_decisions=3, workers=2)
                second = experiment.run_batch(suite, max_decisions=2, workers=2)
            self.assertEqual(first["applied"], 3)
            self.assertEqual(second["applied"], 2)
            state = json.loads((suite/"state.json").read_text())
            self.assertEqual(sum(w["stage_index"] for w in state["worlds"]), 5)
            out = Path(temporary)/"public"
            exported = experiment.export_public(suite, out)
            self.assertGreater(exported["audit_records"], 0)
            self.assertTrue((out/"audit.jsonl.gz").exists())
            self.assertEqual(json.loads((out/"report.json").read_text())["provider_decisions"], 5)

    def test_failed_call_does_not_advance_world(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(audit, "BASE", Path(temporary)/"runs"):
            suite = Path(temporary)/"suite"
            experiment.create(suite)
            with patch.object(experiment, "provider_decision", side_effect=ValueError("Provider unavailable")):
                result = experiment.run_batch(suite, max_decisions=2, workers=1)
            self.assertEqual(result["failures"], 2)
            state = json.loads((suite/"state.json").read_text())
            self.assertEqual(sum(w["stage_index"] for w in state["worlds"]), 0)


if __name__ == "__main__":
    unittest.main()

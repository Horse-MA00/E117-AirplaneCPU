"""Background panels stay bounded, resumable and honest about partial results."""
import io
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from backend import panel_jobs
from llm_agent import audit, journey, journey_runner


class PanelJobTests(unittest.TestCase):
    ENV = {"LLM_API_URL": "https://example.invalid/chat/completions", "LLM_API_KEY": "UNIT_TEST_NOT_REAL", "LLM_MODEL": "test-model"}

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patches = [patch.object(panel_jobs, "BASE", Path(self.tmp.name)/"panels"),
                        patch.object(audit, "BASE", Path(self.tmp.name)/"audits")]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for thread in list(panel_jobs._threads.values()):
            thread.join(timeout=20)
        for item in reversed(self.patches):
            item.stop()
        self.tmp.cleanup()

    def wait(self, run_id):
        panel_jobs._threads[run_id].join(timeout=30)
        self.assertFalse(panel_jobs._threads[run_id].is_alive())
        result = panel_jobs.read(run_id)
        self.assertNotEqual(result["status"], "failed", result.get("error"))
        return result

    def provider(self, packet, record):
        record.append({"event": "request_prepared", "packet_id": packet["packet_id"]})
        record.append({"event": "provider_dispatched", "packet_id": packet["packet_id"]})
        decision = journey.deterministic(packet["context"])
        record.append({"event": "decision_validated", "packet_id": packet["packet_id"], "cache_hit": False})
        return decision

    def test_background_returns_before_provider_and_duplicate_batch_rejected(self):
        entered, release = threading.Event(), threading.Event()

        def slow(packet, record):
            entered.set()
            release.wait(timeout=10)
            return self.provider(packet, record)

        with patch.dict("os.environ", self.ENV), patch.object(journey_runner, "provider_decision", side_effect=slow):
            started = panel_jobs.start({"mode": "live", "count": 2, "max_calls": 1})
            run_id = started["run_id"]
            self.assertEqual(started["status"], "queued")
            self.assertTrue(entered.wait(timeout=5))
            snapshot = panel_jobs.read(run_id)
            self.assertEqual(snapshot["status"], "running")
            self.assertEqual(snapshot["summary"]["eligible_decided"], 0)
            with self.assertRaisesRegex(ValueError, "already running"):
                panel_jobs.start({"max_calls": 1}, run_id)
            release.set()
            result = self.wait(run_id)
            self.assertEqual(result["status"], "paused_at_budget")
            self.assertEqual(result["runtime"]["provider_calls"], 1)

    def test_100_person_deterministic_panel_preserves_accounting_and_compact_results(self):
        with patch.object(journey_runner, "provider_decision") as provider:
            run_id = panel_jobs.start({"count": 100})["run_id"]
            result = self.wait(run_id)
            provider.assert_not_called()
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["progress"]["completed_stages"], 600)
        self.assertEqual(result["summary"]["customers"], 100)
        self.assertEqual(result["runtime"]["provider_calls"], 0)
        self.assertGreater(result["runtime"]["forced_actions"], 0)
        self.assertEqual(sum(s["customers"] for s in result["segments"]), 100)
        self.assertEqual(sum(s["eligible_decided"] for s in result["segments"]), result["summary"]["eligible_decided"])
        for row in result["results"]:
            self.assertNotIn("events", row)
            p, s = row["person"], row["final_state"]
            self.assertAlmostEqual(s["remaining_budget"], p["total_budget"]-s["membership_fee_paid"]-s["ticket_spend"]+s["refund_received"])
            self.assertGreaterEqual(s["remaining_budget"], 0)
        person = panel_jobs.read_person(run_id, result["results"][0]["person"]["customer_id"])
        self.assertEqual(len(person["events"]), 6)
        self.assertEqual(len(panel_jobs.list_runs()), 1)
        with self.assertRaisesRegex(ValueError, "already complete"):
            panel_jobs.start({}, run_id)

    def test_live_budget_resume_and_forced_decisions_are_separate(self):
        with patch.dict("os.environ", self.ENV), patch.object(journey_runner, "provider_decision", side_effect=self.provider) as provider:
            run_id = panel_jobs.start({"mode": "live", "count": 5, "max_calls": 2})["run_id"]
            first = self.wait(run_id)
            self.assertEqual(provider.call_count, 2)
            self.assertEqual(first["status"], "paused_at_budget")
            self.assertEqual(first["runtime"]["provider_calls"], 2)
            self.assertGreater(first["runtime"]["forced_actions"], 0)  # Existing member.
            self.assertEqual(first["summary"]["eligible_decided"], 2)
            before = provider.call_count
            panel_jobs.read(run_id)
            panel_jobs.list_runs()
            self.assertEqual(provider.call_count, before)
            panel_jobs.start({"max_calls": 120}, run_id)
            final = self.wait(run_id)
            self.assertEqual(final["status"], "completed")
            self.assertEqual(final["progress"]["completed_stages"], 30)
            self.assertLess(final["runtime"]["provider_calls"], 30)
            self.assertEqual(final["runtime"]["provider_calls"], provider.call_count)

    def test_provider_errors_pause_without_fallback_or_state_change(self):
        def fail(packet, record):
            record.append({"event": "provider_dispatched", "packet_id": packet["packet_id"]})
            raise ValueError("Mock provider unavailable")

        with patch.dict("os.environ", self.ENV), patch.object(journey_runner, "provider_decision", side_effect=fail) as provider:
            run_id = panel_jobs.start({"mode": "live", "count": 10, "max_calls": 120})["run_id"]
            result = self.wait(run_id)
            self.assertEqual(result["status"], "paused_after_errors")
            self.assertLessEqual(provider.call_count, 5)
            self.assertGreaterEqual(result["runtime"]["failures"], 3)
            for row in result["results"]:
                if row["error"]:
                    self.assertEqual(row["completed_stages"], 0)
                    self.assertEqual(row["final_state"]["remaining_budget"], row["person"]["total_budget"])

    def test_real_adapter_cache_counts_and_raw_audit(self):
        raw = {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps({"action": "DECLINE", "option_id": None, "reason": "I prefer to preserve my budget."})}}]}
        with patch.dict("os.environ", self.ENV), patch.object(journey_runner, "_transport", side_effect=lambda request: io.BytesIO(json.dumps(raw).encode())) as transport:
            first = self.wait(panel_jobs.start({"mode": "live", "count": 1, "max_calls": 1})["run_id"])
            second = self.wait(panel_jobs.start({"mode": "live", "count": 1, "max_calls": 1})["run_id"])
            self.assertEqual(transport.call_count, 1)
            self.assertEqual(first["runtime"]["provider_calls"], 1)
            self.assertEqual(second["runtime"]["provider_calls"], 0)
            self.assertEqual(second["runtime"]["cache_hits"], 1)
            records = audit.read_run(first["audit_run_id"])["records"]
            self.assertTrue(any(x.get("raw_response") == raw for x in records))

    def test_resume_freezes_prompt_model_and_marks_interruption(self):
        with patch.dict("os.environ", self.ENV):
            run_id = panel_jobs.start({"mode": "live", "count": 1, "max_calls": 0})["run_id"]
            self.wait(run_id)
            with patch.dict("os.environ", {"LLM_MODEL": "different-model"}):
                with self.assertRaisesRegex(ValueError, "provider changed"):
                    panel_jobs.start({}, run_id)
            with patch.object(panel_jobs, "_provenance", return_value={}):
                with self.assertRaisesRegex(ValueError, "prompt or provider changed"):
                    panel_jobs.start({}, run_id)
        path = panel_jobs._folder(run_id)/"job.json"
        job = json.loads(path.read_text()); job["status"] = "running"
        path.write_text(json.dumps(job))
        self.assertEqual(panel_jobs.read(run_id)["status"], "interrupted")

    def test_interrupted_dispatch_is_counted_without_inventing_a_decision(self):
        with patch.dict("os.environ", self.ENV), patch.object(journey_runner, "provider_decision", side_effect=self.provider):
            run_id = panel_jobs.start({"mode": "live", "count": 1, "max_calls": 0})["run_id"]
            initial = self.wait(run_id)
            row = initial["results"][0]
            checkpoint = panel_jobs._read(panel_jobs._checkpoint_path(panel_jobs._folder(run_id), row["person"]["customer_id"]))
            packet = journey.packet_for(checkpoint["world"])
            record = audit.Audit("customer_panel", run_id=initial["audit_run_id"], resume=True)
            record.append({"event": "request_prepared", "packet_id": packet["packet_id"]})
            record.append({"event": "provider_dispatched", "packet_id": packet["packet_id"]})
            # Process interruption after dispatch: no result or state commit.
            panel_jobs.start({"max_calls": 1}, run_id)
            resumed = self.wait(run_id)
            self.assertEqual(resumed["runtime"]["provider_calls"], 2)
            self.assertEqual(resumed["runtime"]["provider_decision_attempts"], 2)
            self.assertEqual(resumed["progress"]["completed_stages"], 1)
            self.assertEqual(len(panel_jobs.read_person(run_id, row["person"]["customer_id"])["events"]), 1)

    def test_bounds_and_path_validation(self):
        for body in ({"count":1001}, {"count":True}, {"count":0}, {"max_calls":121}, {"seed":-1}):
            with self.subTest(body=body), self.assertRaises(ValueError):
                panel_jobs.start(body)
        with patch.dict("os.environ", self.ENV), self.assertRaises(ValueError):
            panel_jobs.start({"mode":"live", "count":101})
        for ident in ("../secret", "/tmp/a", "a/b"):
            with self.assertRaises(ValueError):
                panel_jobs.read(ident)


if __name__ == "__main__":
    unittest.main()

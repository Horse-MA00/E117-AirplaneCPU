"""No-network tests for live mode's two-step state and validation contract."""
import json
import io
import tempfile
import unittest
import urllib.request
import urllib.error
from pathlib import Path
from unittest.mock import patch

from llm_agent import runner


PERSON = {
    "customer_id": "SYN-TEST", "segment": "flexible_budget", "segment_label": "Test scenario",
    "source": "assumed_customer_scenario", "expected_trips": 4, "total_budget": 1500,
    "flexibility_days": 3, "party_size": 1, "minimum_notice_days": 3,
    "route_match": True, "language": "en", "perceived_availability": .5,
    "membership_active": False,
}


class LiveAgentContractTests(unittest.TestCase):
    def test_http_adapter_two_responses_then_cached_replay(self):
        dummy = "UNIT_TEST_NOT_A_REAL_CREDENTIAL"
        settings = {"LLM_API_KEY": dummy, "LLM_API_URL": "https://example.invalid/chat/completions", "LLM_MODEL": "test-model"}
        received = []

        def respond(request):
            self.assertEqual(request.get_header("Authorization"), "Bearer "+dummy)
            body = json.loads(request.data)
            self.assertNotIn(dummy, json.dumps(body))
            context = json.loads(body["messages"][1]["content"])
            received.append(context)
            decision = ({"action": "JOIN_PASS", "option_id": "pass"} if context["stage"] == "subscription"
                        else {"action": "BUY_MEMBER", "option_id": "member"})
            return io.BytesIO(json.dumps({"choices": [{"message": {"content": json.dumps(decision)}}]}).encode())

        with tempfile.TemporaryDirectory() as temporary, patch.dict("os.environ", settings), patch.object(runner, "__file__", str(Path(temporary)/"llm_agent/runner.py")), patch.object(runner, "population", return_value=[dict(PERSON)]), patch.object(runner, "_open", side_effect=respond) as transport:
            first = runner.run(mode="live", count=1)
            second = runner.run(mode="live", count=1)
            self.assertEqual(first, second)
            self.assertEqual(transport.call_count, 2)
            self.assertEqual(received[1]["person"]["total_budget"], 1101)
            cached = list(Path(temporary).rglob("*.json"))
            self.assertEqual(len(cached), 2)
            self.assertTrue(all(dummy not in path.read_text() for path in cached))

    def test_http_adapter_errors_are_sanitized(self):
        dummy = "UNIT_TEST_NOT_A_REAL_CREDENTIAL"
        settings = {"LLM_API_KEY": dummy, "LLM_API_URL": "https://example.invalid/chat/completions", "LLM_MODEL": "test-model"}
        with tempfile.TemporaryDirectory() as temporary, patch.dict("os.environ", settings), patch.object(runner, "__file__", str(Path(temporary)/"llm_agent/runner.py")), patch.object(runner, "_open", side_effect=urllib.error.URLError(dummy)):
            with self.assertRaises(ValueError) as raised:
                runner.live(runner.scenario(dict(PERSON)))
            self.assertNotIn(dummy, str(raised.exception))
            self.assertIn("no simulated result", str(raised.exception))

    def test_authenticated_redirect_is_rejected(self):
        request = urllib.request.Request("https://example.invalid/chat", headers={"Authorization": "Bearer test"})
        with self.assertRaises(urllib.error.HTTPError):
            runner.NoRedirect().redirect_request(request, None, 302, "Redirect", {}, "https://other.invalid/chat")

    def test_live_subscription_and_booking_use_updated_budget(self):
        contexts = []

        def provider(context):
            contexts.append(context)
            if context["stage"] == "subscription":
                return {"action": "JOIN_PASS", "option_id": "pass", "reason": "Expected value", "reason_code": "VALUE"}
            return {"action": "BUY_MEMBER", "option_id": "member", "reason": "Affordable", "reason_code": "PRICE"}

        with patch.object(runner, "population", return_value=[dict(PERSON)]), patch.object(runner, "live", side_effect=provider):
            result = runner.run(mode="live", count=1, membership_fee=399, member_fare=70)
        self.assertEqual(len(contexts), 2)
        self.assertEqual(contexts[1]["person"]["total_budget"], 1101)
        self.assertTrue(contexts[1]["person"]["membership_active"])
        self.assertEqual(result["source"], "llm_simulated")
        self.assertFalse(result["results"][0]["booking_decision"]["inventory_committed"])

    def test_failed_live_run_does_not_use_deterministic_fallback(self):
        with patch.object(runner, "population", return_value=[dict(PERSON)]), patch.object(runner, "live", side_effect=ValueError("Provider unavailable")), patch.object(runner, "deterministic") as fallback:
            with self.assertRaisesRegex(ValueError, "Provider unavailable"):
                runner.run(mode="live", count=1)
            fallback.assert_not_called()

    def test_illegal_live_purchase_after_declining_is_rejected(self):
        responses = [{"action": "DECLINE", "option_id": None}, {"action": "BUY_MEMBER", "option_id": "member"}]
        with patch.object(runner, "population", return_value=[dict(PERSON)]), patch.object(runner, "live", side_effect=responses):
            with self.assertRaises(ValueError):
                runner.run(mode="live", count=1)

    def test_membership_consumes_budget_before_booking_options(self):
        contexts = []

        def provider(context):
            contexts.append(context)
            return ({"action": "JOIN_PASS", "option_id": "pass"} if context["stage"] == "subscription"
                    else {"action": "DECLINE", "option_id": None})

        with patch.object(runner, "population", return_value=[dict(PERSON, total_budget=450)]), patch.object(runner, "live", side_effect=provider):
            result = runner.run(mode="live", count=1, membership_fee=399)
        self.assertEqual(contexts[1]["person"]["total_budget"], 51)
        self.assertEqual(contexts[1]["options"], [])
        self.assertEqual(result["results"][0]["booking_decision"]["action"], "DECLINE")

    def test_join_beyond_budget_is_rejected(self):
        with patch.object(runner, "population", return_value=[dict(PERSON, total_budget=100)]), patch.object(runner, "live", return_value={"action": "JOIN_PASS", "option_id": "pass"}):
            with self.assertRaisesRegex(ValueError, "budget"):
                runner.run(mode="live", count=1)

    def test_prompt_and_public_payload_exclude_environment_credentials(self):
        dummy = "UNIT_TEST_NOT_A_REAL_CREDENTIAL"
        with patch.dict("os.environ", {"LLM_API_KEY": dummy}):
            result = runner.run(mode="deterministic", count=1)
            payload = json.dumps(result)+json.dumps(runner.status())+runner.PROMPT.read_text()
        self.assertNotIn(dummy, payload)


if __name__ == "__main__":
    unittest.main()

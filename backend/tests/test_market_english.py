"""English/HKD contract at the shared-market live-provider boundary."""
import copy
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from llm_agent import audit, market_adapter


class SharedMarketEnglishTests(unittest.TestCase):
    ENV = {"LLM_API_URL": "https://example.invalid/chat/completions",
           "LLM_API_KEY": "UNIT_TEST_MARKET_CREDENTIAL", "LLM_MODEL": "test-only"}

    def observation(self):
        return {"customer_id": "SYN-ENGLISH", "stage": "subscription",
                "person": {"language": "ja", "total_budget": 807},
                "allowed_actions": ["DECLINE", "JOIN_PASS"],
                "options": [{"action": "JOIN_PASS", "id": "pass", "price": 399}]}

    def raw(self, reason):
        return {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(
            {"action": "DECLINE", "option_id": None, "reason_code": "BUDGET",
             "reason": reason, "confidence": "medium"})}}], "usage": {"total_tokens": 17}}

    def test_mixed_language_and_foreign_currency_rejected_before_cache(self):
        for reason in ("会費399円は予算を圧迫します。", "會費 HKD 399 會壓縮預算。",
                       "The JPY 399 fee consumes my travel budget."):
            with self.subTest(reason=reason), tempfile.TemporaryDirectory() as temporary, \
                    patch.object(audit, "BASE", Path(temporary)/"runs"), patch.dict("os.environ", self.ENV):
                observation = self.observation()
                before = copy.deepcopy(observation)
                raw = self.raw(reason)
                record = audit.Audit("provider_live")
                with patch.object(market_adapter, "_transport", return_value=io.BytesIO(json.dumps(raw).encode())):
                    with self.assertRaisesRegex(ValueError, "No fallback"):
                        market_adapter.choose(observation, "live", record)
                self.assertEqual(observation, before)
                records = audit.read_run(record.run_id)["records"]
                self.assertTrue(any(r.get("event") == "market_response" and r.get("raw_response") == raw for r in records))
                self.assertTrue(any(r.get("event") == "market_choice_failed" for r in records))
                self.assertFalse(any(r.get("event") == "market_choice" for r in records))
                self.assertEqual(list((Path(temporary)/"llm_shared_market_cache").glob("*.json")), [])

    def test_english_contract_applies_to_each_prompt_language_and_cached_replay(self):
        for language in ("en", "zh"):
            with self.subTest(language=language), tempfile.TemporaryDirectory() as temporary, \
                    patch.object(audit, "BASE", Path(temporary)/"runs"), patch.dict("os.environ", self.ENV):
                raw = self.raw("The HKD 399 fee leaves too little flexibility in my trip budget.")
                with patch.object(market_adapter, "_transport", return_value=io.BytesIO(json.dumps(raw).encode())) as transport:
                    first = market_adapter.choose(self.observation(), "live", audit.Audit("provider_live"), language)
                    repeat_record = audit.Audit("provider_live")
                    repeat = market_adapter.choose(self.observation(), "live", repeat_record, language)
                self.assertEqual(transport.call_count, 1)
                self.assertEqual(first["decision"], repeat["decision"])
                self.assertTrue(repeat["cache_hit"])
                records = audit.read_run(repeat_record.run_id)["records"]
                request = next(r for r in records if r["event"] == "market_request")
                visible = json.loads(request["request"]["messages"][1]["content"])
                self.assertEqual(visible["response_language"], "en")
                self.assertEqual(visible["currency"], "HKD")
                self.assertEqual(visible["output_contract"], "english-hkd-v1")
                self.assertEqual(visible["person"]["language"], "ja")
                self.assertNotIn(self.ENV["LLM_API_KEY"], json.dumps(records))

    def test_cached_raw_output_is_revalidated(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(audit, "BASE", Path(temporary)/"runs"), \
                patch.dict("os.environ", self.ENV):
            raw = self.raw("I need the remaining HKD 807 for the trip.")
            with patch.object(market_adapter, "_transport", return_value=io.BytesIO(json.dumps(raw).encode())):
                market_adapter.choose(self.observation(), "live", audit.Audit("provider_live"))
            cache = next((Path(temporary)/"llm_shared_market_cache").glob("*.json"))
            invalid_raw = self.raw("予算が足りません。")
            cache.write_text(json.dumps({"raw_response_text": json.dumps(invalid_raw)}))
            record = audit.Audit("provider_live")
            with patch.object(market_adapter, "_transport") as transport:
                with self.assertRaises(ValueError):
                    market_adapter.choose(self.observation(), "live", record)
                transport.assert_not_called()
            self.assertTrue(any(r.get("event") == "market_choice_failed" and r["cache_hit"]
                                for r in audit.read_run(record.run_id)["records"]))


if __name__ == "__main__":
    unittest.main()

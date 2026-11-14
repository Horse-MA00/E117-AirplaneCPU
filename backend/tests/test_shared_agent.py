import copy
import io
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from llm_agent import audit, market_adapter, market_experiment, behavior_probes


class SharedAdapterTests(unittest.TestCase):
    ENV={"LLM_API_URL":"https://example.invalid/chat/completions","LLM_API_KEY":"UNIT_TEST_DUMMY_123456789","LLM_MODEL":"fake-test"}

    def observation(self):
        return {"packet_id":"a", "stage":"subscription", "allowed_actions":["DECLINE","JOIN_PASS"],
                "options":[{"id":"pass","action":"JOIN_PASS","price":199}], "customer":{"total_budget":1000},
                "future_events":[{"profit":9000}],"visible_state":{"remaining_budget":1000,"latent_beta":.05}}

    def test_hidden_context_and_invalid_options(self):
        observation=market_adapter.public_observation(self.observation())
        self.assertNotIn("future_events",observation)
        self.assertNotIn("latent_beta",observation["visible_state"])
        with self.assertRaises(ValueError):
            market_adapter.validate_decision({"action":"JOIN_PASS","option_id":"invented"},observation)
        with self.assertRaises(ValueError):
            market_adapter.validate_decision({"action":"DECLINE","option_id":"pass"},observation)

    def test_forced_is_not_model_call(self):
        observation=self.observation();observation.update(allowed_actions=["DECLINE"],options=[])
        with tempfile.TemporaryDirectory() as temporary, patch.object(audit,"BASE",Path(temporary)/"runs"),patch.object(market_adapter,"_transport") as transport:
            log=audit.Audit("test")
            result=market_adapter.choose(observation,"live",log)
            self.assertEqual(result["source"],"environment_forced")
            self.assertFalse(result["provider_call"])
            transport.assert_not_called()

    def test_raw_live_cache_and_nonstop_rejection(self):
        raw={"choices":[{"finish_reason":"stop","message":{"content":json.dumps({"action":"DECLINE","option_id":None,"reason":"I prefer to preserve my budget."})}}],"usage":{"total_tokens":20}}
        with tempfile.TemporaryDirectory() as temporary,patch.object(audit,"BASE",Path(temporary)/"runs"),patch.dict("os.environ",self.ENV),patch.object(market_adapter,"_transport",return_value=io.BytesIO(json.dumps(raw).encode())) as transport:
            first=audit.Audit("test")
            market_adapter.choose(self.observation(),"live",first)
            second=audit.Audit("test")
            cached=market_adapter.choose(self.observation(),"live",second)
            self.assertTrue(cached["cache_hit"])
            self.assertEqual(transport.call_count,1)
            self.assertTrue(any(r.get("raw_response_text") for r in audit.read_run(second.run_id)["records"]))
            raw["choices"][0]["finish_reason"]="length"
            transport.return_value=io.BytesIO(json.dumps(raw).encode())
            bad=audit.Audit("test")
            with self.assertRaises(ValueError):market_adapter.choose(self.observation(),"live",bad,use_cache=False)
            self.assertEqual(audit.read_run(bad.run_id)["records"][-1]["event"],"market_choice_failed")

    def test_price_probe_updates_complete_party_payment(self):
        original=self.observation()
        original["legal_options"]=copy.deepcopy(original["options"])
        original["membership"]={"member_base_fare":0,"fee":199}
        original["current_quote_reference"]=[{"action":"BUY_MEMBER","price":1530,"price_breakdown":{"normal_base_fares":1200,"member_base_fare":0,"mandatory_fees":250,"baggage":80}}]
        changed=behavior_probes._price_fixture(original,70,599)
        self.assertEqual(changed["current_quote_reference"][0]["price"],1600)
        self.assertEqual(changed["options"][0]["price"],599)
        self.assertEqual(original["current_quote_reference"][0]["price"],1530)

    def test_probe_transport_circuit_stops_after_three_failures(self):
        with tempfile.TemporaryDirectory() as temporary,patch.object(audit,"BASE",Path(temporary)/"runs"):
            output=Path(temporary)/"probes";output.mkdir()
            spec={"run_id":"probe-circuit-test","design":"test only","caveat":"test", "prompt_version":market_adapter.VERSION,
                  "prompt_hashes":{lang:hashlib.sha256(path.read_bytes()).hexdigest() for lang,path in market_adapter.PROMPTS.items()},
                  "probes":[{"probe_id":str(i),"customer_id":"x","fare":0,"fee":199,"variant":"base_en","language":"en","observation":{},"completed":False} for i in range(60)]}
            (output/"probes.json").write_text(json.dumps(spec))
            with patch.object(behavior_probes,"choose",side_effect=ValueError("test transport unavailable")) as choose:
                result=behavior_probes.run_batch(output,60,workers=5)
            self.assertEqual(choose.call_count,3)
            self.assertEqual(result["completed"],0)


class SharedExperimentTests(unittest.TestCase):
    def test_partial_resume_complete_accounting_and_bounded_export(self):
        with tempfile.TemporaryDirectory() as temporary,patch.object(audit,"BASE",Path(temporary)/"runs"):
            output=Path(temporary)/"experiment"
            config={"customer_count":2,"flight_count":6,"horizon_days":90,"occasions_per_customer":2}
            result=market_experiment.create_experiment(output,config=config)
            first=market_experiment.run_batch(output,max_calls=0,max_steps=2)
            self.assertEqual(first["steps"],2)
            partial=market_experiment.report(output)
            self.assertEqual(len(partial["case_results"]),3)
            self.assertEqual(partial["completed_cases"],0)
            self.assertEqual(len(market_experiment.inspect_cases(output,event_limit=1)),3)
            finished=market_experiment.run_batch(output,max_calls=0,max_steps=1000)
            self.assertEqual(finished["remaining_cases"],0)
            report=market_experiment.report(output)
            self.assertEqual(report["runtime"]["provider_calls"],0)
            self.assertEqual(len(report["seed_rankings"]),1)
            for case in report["case_results"]:self.assertTrue(all(case["metrics"]["checks"].values()))
            self.assertEqual(len({c["metrics"]["exogenous_sha256"] for c in report["case_results"]}),1)
            exported=market_experiment.export_public(output,Path(temporary)/"public")
            self.assertGreater(exported["records"],0)
            self.assertEqual(market_experiment.run_status(output)["status"],"completed")
            # Public metadata-only status does not load or truncate audit JSONL.
            with patch.object(market_experiment,"iter_audit",side_effect=AssertionError("must not read audit")):
                self.assertEqual(market_experiment.run_status(output)["run_id"],result["experiment_id"])

    def test_resume_rejects_implementation_change(self):
        with tempfile.TemporaryDirectory() as temporary:
            output=Path(temporary)
            market_experiment.create_experiment(output,config={"customer_count":1,"flight_count":6})
            with patch.object(market_experiment,"implementation_hashes",return_value={"changed":"hash"}):
                with self.assertRaisesRegex(ValueError,"implementation changed"):
                    market_experiment.run_batch(output,0)


if __name__=="__main__":unittest.main()

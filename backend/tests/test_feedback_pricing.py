"""End-to-end replay/persistence contracts; all provider outputs are test fixtures.

Real shared-market worlds execute without HTTP. Fixture decisions use the
probabilistic customer only to exercise the transport seam, not as live evidence.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backend import feedback_pricing as engine, feedback_store as store
from backend.probabilistic_customer import choose as probability
from llm_agent.market_adapter import legal_choices

REAL_PROVENANCE = engine.provenance


class FeedbackPricingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        for context in (
            patch.object(store, "BASE", Path(self.tmp.name)),
            patch.dict(os.environ, {"LLM_API_URL": "https://example.invalid/chat",
                                    "LLM_API_KEY": "fixture-secret-not-real", "LLM_MODEL": "fixture-model"}),
            # Run synchronously so fixtures cannot outlive the test or touch HTTP.
            patch.object(engine, "_launch", side_effect=engine._worker),
            # Stable fixture provenance isolates concurrent implementation edits.
            patch.object(engine, "provenance", return_value={"test_source": "v1"}),
        ):
            context.start()
            self.addCleanup(context.stop)
        self.contexts = []
        self.choice_calls = []
        self.proposal_calls = []
        self.choice_patch = patch("llm_agent.market_adapter.choose", side_effect=self.choose_fixture)
        self.proposal_patch = patch("llm_agent.price_proposer.propose", side_effect=self.proposal_fixture)
        self.choice_patch.start()
        self.proposal_patch.start()
        self.addCleanup(self.choice_patch.stop)
        self.addCleanup(self.proposal_patch.stop)

    def start(self, **kwargs):
        return engine.start({"flight_id": "NET-HKG-KMQ-20270518", "forecast_day": 28,
                             "customers": 3, "rounds": 3, "replicates": 1,
                             "total_call_budget": 500, **kwargs})

    def choose_fixture(self, observation, mode, audit, **kwargs):
        self.assertEqual(mode, "live")
        self.assertEqual(kwargs["prompt_version"], "fare-only-customer-v1-en")
        self.assertTrue(kwargs["system_prompt"])
        self.assertFalse(observation["checkout_terms"]["membership_payment_required"])
        choices = legal_choices(observation)
        forced = len(choices) == 1
        decision = probability(observation)["decision"]
        source = "environment_forced" if forced else "test_fixture"
        raw = json.dumps({"fixture_only": True, "choices": [{"message": {"content": json.dumps(decision)}}]})
        audit.append({"event": "market_choice", "source": source, "provider_call": False,
                      "cache_hit": False, "decision": decision, "raw_response_text": raw})
        self.choice_calls.append((audit.world_id, observation["packet_id"], decision))
        return {"decision": decision, "source": source, "forced": forced,
                "provider_call": False, "cache_hit": False}

    def proposal_fixture(self, context, audit):
        self.contexts.append(copy.deepcopy(context))
        proposal = {"fare": round(context["initial_fare"] * (1 - .15 * (context["round"] - 1)), 2),
                    "reason": "Fixture explores a lower price after observed outcomes.",
                    "hypothesis": "Some simulated travellers may switch ticket type."}
        audit.append({"event": "price_proposal_response", "source": "test_fixture",
                      "request_context": context, "raw_response_text": json.dumps(proposal)})
        self.proposal_calls.append(context["round"])
        return {**proposal, "source": "test_fixture"}

    def assert_completed_worlds(self, report):
        self.assertEqual(report["status"], "completed", report["error"])
        worlds = store.all_worlds(report["run_id"])
        for world in worlds:
            result = world["result"]
            self.assertTrue(result["complete"])
            self.assertTrue(all(result["checks"].values()), result["checks"])
            self.assertEqual(result["ledger"]["membership_revenue"], 0)
            self.assertEqual(result["ledger"]["total_cost"], 0)
            self.assertEqual(result["ticket_revenue"],
                             round(result["regular_base_revenue"] + result["member_base_revenue"], 2))
            self.assertEqual(result["tickets_sold"], result["tickets_flown"] + result["tickets_cancelled"])
        return worlds

    def test_pause_resume_reuses_proposal_and_never_double_charges(self):
        original = self.proposal_fixture

        def stop_after_proposal(context, audit):
            proposal = original(context, audit)
            # Simulate reaching the exact budget boundary after this response.
            store.mutate(audit.run_id, lambda doc: doc["config"].update(
                total_call_budget=doc["counts"]["total_attempts"]))
            return proposal

        with patch("llm_agent.price_proposer.propose", side_effect=stop_after_proposal):
            paused = self.start(rounds=2)
        self.assertEqual(paused["status"], "paused", paused["error"])
        self.assertEqual(len(paused["rounds"]), 1)
        self.assertIn("2", paused["proposals"])
        self.assertEqual(paused["counts"]["total_attempts"], paused["config"]["total_call_budget"])
        saved_proposal = copy.deepcopy(paused["proposals"]["2"])
        report = engine.resume(paused["run_id"], {"additional_call_budget": 500})
        self.assert_completed_worlds(report)
        self.assertEqual(self.proposal_calls, [2])
        self.assertEqual(report["proposals"]["2"], saved_proposal)
        identities = [(world, packet) for world, packet, decision in self.choice_calls]
        self.assertEqual(len(identities), len(set(identities)))
        exported = engine.export_run(report["run_id"])
        self.assertTrue(any("raw_response_text" in row["record"] for row in exported["events"]))
        self.assertEqual(report["counts"]["proposer_calls"], 1)
        self.assertEqual(report["counts"]["total_attempts"],
                         report["counts"]["customer_calls"] + report["counts"]["proposer_calls"])
        self.assertEqual(report["counts"]["provider_calls"], 0)  # Fixtures were not live calls.
        with self.assertRaisesRegex(ValueError, "unfinished"):
            engine.resume(report["run_id"], {"additional_call_budget": 1})

    def test_data_p0_paired_worlds_and_holdout_never_enter_proposal_feedback(self):
        report = self.start(initial_member_fare=1, initial_fare=1, replicates=2)
        worlds = self.assert_completed_worlds(report)
        self.assertEqual(report["initial_fare"], report["scope"]["normal_base_fare"])
        self.assertEqual(report["rounds"][0]["fare"], report["initial_fare"])
        by_seed = {}
        for world in worlds:
            by_seed.setdefault(world["seed"], set()).add(world["result"]["exogenous_sha256"])
        self.assertTrue(all(len(hashes) == 1 for hashes in by_seed.values()))
        search_seeds = {w["seed"] for w in worlds if w["phase"] == "search"}
        holdout_seeds = set(report["validation"]["seeds"])
        self.assertTrue(search_seeds.isdisjoint(holdout_seeds))
        self.assertEqual(len(holdout_seeds), 2)
        self.assertEqual(len(self.contexts), 2)
        for context in self.contexts:
            self.assertEqual([row["round"] for row in context["history"]],
                             list(range(1, context["round"])))
            payload = json.dumps(context)
            self.assertNotIn("holdout", payload)
            self.assertNotIn("validation", payload)
            self.assertNotIn("future_events", payload)
            self.assertTrue(any(row["feedback"] for row in context["history"]))
        exports = engine.export_run(report["run_id"])
        proposal_records = [item["record"] for item in exports["events"]
                            if item["record"].get("event") == "price_proposal_response"]
        self.assertEqual(len(proposal_records), 2)
        self.assertEqual(json.loads(proposal_records[0]["raw_response_text"])["fare"], report["rounds"][1]["fare"])

    def test_provider_failure_preserves_raw_error_without_fallback(self):
        def failed(observation, mode, audit, **kwargs):
            audit.append({"event": "market_choice_failed", "source": "test_fixture",
                          "provider_call": False, "raw_response_text": "malformed fixture response",
                          "error": "Fixture rejection", "validation": "failed"})
            raise ValueError("Fixture provider output rejected")

        with patch("llm_agent.market_adapter.choose", side_effect=failed):
            report = self.start()
        self.assertEqual(report["status"], "failed")
        self.assertIn("rejected", report["error"])
        self.assertEqual(report["rounds"], [])
        self.assertEqual(report["counts"]["failures"], 1)
        world = store.all_worlds(report["run_id"])[0]
        self.assertIsNone(world["result"])
        self.assertIsNotNone(world["state"]["pending"])
        self.assertEqual(world["state"]["records"], [])
        records = engine.export_run(report["run_id"])["events"]
        self.assertEqual(records[-1]["record"]["raw_response_text"], "malformed fixture response")
        self.assertFalse(any(row["record"].get("event") == "feedback_transition" for row in records))

    def test_changed_provenance_rejects_resume_before_provider_or_budget_change(self):
        report = self.start(total_call_budget=0)
        self.assertEqual(report["status"], "paused")
        self.assertEqual(report["counts"]["total_attempts"], 0)
        with patch.object(engine, "provenance", return_value={"test_source": "changed"}):
            with self.assertRaisesRegex(ValueError, "changed"):
                engine.resume(report["run_id"], {"additional_call_budget": 20})
        self.assertEqual(store.read(report["run_id"])["config"]["total_call_budget"], 0)
        self.assertEqual(self.choice_calls, [])
        self.assertEqual(self.proposal_calls, [])

    def test_no_offer_delta_counts_lost_normal_sales_and_retained_cancelled_base(self):
        report = self.start(customers=14, rounds=2, total_call_budget=1000)
        worlds = self.assert_completed_worlds(report)
        by_key = {(w["phase"], w["round_number"], w["seed"]): w for w in worlds}
        seed = report["config"]["seed"]
        baseline = by_key[("baseline", 0, seed)]["result"]
        self.assertEqual(baseline["member_tickets"], 0)
        self.assertEqual(baseline["member_base_revenue"], 0)
        for row in report["rounds"]:
            candidate = by_key[("search", row["round"], seed)]["result"]
            self.assertEqual(row["delta_vs_no_offer"],
                             round(candidate["ticket_revenue"] - baseline["ticket_revenue"], 2))
        for world in worlds:
            bookings = list(world["state"]["bookings"].values())
            retained = sum(b["normal_base_cents"] + b["member_base_cents"] for b in bookings) / 100
            self.assertEqual(world["result"]["ticket_revenue"], round(retained, 2))
            self.assertFalse(any(e.get("stage") in ("subscription", "term_end") for e in world["state"]["events"]))
            self.assertEqual(world["result"]["ledger"]["membership_revenue"], 0)
            self.assertEqual(world["result"]["ledger"]["cancellation_revenue"], 0)

    def test_holdout_can_reject_improvement_but_cannot_pick_a_replacement(self):
        def fake_world(run_id, phase, number, seed, fare, enabled):
            # Search prefers round 2; independent holdout prefers P0. No extra
            # proposal may be solicited after this contrary validation evidence.
            revenue = {"baseline": 50, "holdout_no_offer": 300,
                       "holdout_initial": 500, "holdout_selected": 400}.get(phase, 100 if number == 1 else 200)
            row = {key: 0 for key in ("ticket_revenue", "tickets_sold", "tickets_flown", "tickets_cancelled",
                   "member_tickets", "regular_tickets", "background_tickets", "buyers", "member_buyers",
                   "member_flown", "member_offer_customers", "member_supply_exposure", "agent_base_revenue",
                   "background_base_revenue", "member_base_revenue", "regular_base_revenue")}
            row.update(seed=seed, exogenous_sha256=f"matched-{seed}", checks={"fixture": True},
                       ticket_revenue=revenue, member_tickets=1, member_offer_customers=1)
            return row

        with patch.object(engine, "_world", side_effect=fake_world):
            report = self.start(rounds=2)
        self.assertEqual(report["status"], "completed", report["error"])
        self.assertEqual(report["selected"]["round"], 2)
        self.assertEqual(report["validation"]["selected"]["fare"], report["rounds"][1]["fare"])
        self.assertEqual(report["validation"]["delta_vs_initial"], -100)
        self.assertEqual(report["validation"]["decision"], "KEEP_INITIAL")
        self.assertEqual(self.proposal_calls, [2])

    def test_unmatched_controls_are_rejected_and_fees_are_not_accepted(self):
        left = [{"seed": 117, "exogenous_sha256": "a", "ticket_revenue": 100}]
        with self.assertRaisesRegex(ValueError, "not matched"):
            engine.paired_delta(left, [{**left[0], "exogenous_sha256": "b"}])
        with self.assertRaisesRegex(ValueError, "no membership fee"):
            self.start(initial_membership_fee=399)
        self.assertEqual(self.choice_calls, [])

    def test_validation_requires_observed_sales_and_positive_control_delta(self):
        supported = {"member_offer_customers": 3, "member_tickets": 2}
        no_sales = {"member_offer_customers": 3, "member_tickets": 0}
        no_exposure = {"member_offer_customers": 0, "member_tickets": 0}
        cases = [
            (supported, supported, 200, 50, 150, 2, "RECOMMEND_TESTED_FARE"),
            (no_sales, no_exposure, 200, 50, 150, 2, "REJECT_OFFER"),
            (no_sales, supported, -50, 100, -150, 2, "KEEP_INITIAL"),
            (supported, supported, -50, -100, 50, 2, "REJECT_OFFER"),
            (no_exposure, supported, 0, 0, 0, 1, "REJECT_OFFER"),
        ]
        for selected, initial, selected_delta, initial_delta, change, number, expected in cases:
            with self.subTest(expected=expected, initial_delta=initial_delta, selected_delta=selected_delta):
                self.assertEqual(engine.validation_decision(
                    selected, initial, selected_delta, initial_delta, change, number), expected)

    def test_http_dispatches_new_experiment_routes_without_external_calls(self):
        from backend import server
        from backend.errors import NotFound

        run_id = "feedback-0123456789abcdef"
        path = f"/api/feedback-pricing/runs/{run_id}"
        body = {"flight_id": "NET-HKG-KMQ-20270518", "rounds": 2}
        with patch.object(engine, "start", return_value={"run_id": run_id}) as start:
            self.assertEqual(server.post("/api/feedback-pricing/runs", body), {"run_id": run_id})
            start.assert_called_once_with(body)
        with patch.object(engine, "resume", return_value={"status": "queued"}) as resume:
            self.assertEqual(server.post(path + "/resume", {"additional_call_budget": 10}), {"status": "queued"})
            resume.assert_called_once_with(run_id, {"additional_call_budget": 10})
        with patch.object(engine, "list_runs", return_value=[{"run_id": run_id}]):
            self.assertEqual(server.get("/api/feedback-pricing/runs"), {"runs": [{"run_id": run_id}]})
        with patch.object(engine, "read", return_value={"run_id": run_id}) as read:
            self.assertEqual(server.get(path), {"run_id": run_id})
            read.assert_called_once_with(run_id)
        with patch.object(engine, "export_run", return_value={"events": []}) as export:
            self.assertEqual(server.get(path + "/export"), {"events": []})
            export.assert_called_once_with(run_id)
        with patch.object(store, "events", return_value={"events": [], "total": 0}) as events:
            self.assertEqual(server.get(path + "/events", {"limit": ["7"], "offset": ["2"]}),
                             {"events": [], "total": 0})
            events.assert_called_once_with(run_id, 7, 2)
        with self.assertRaises(NotFound):
            server.get(path + "/unsupported")
        self.assertEqual(self.choice_calls, [])

    def test_validated_proposal_recovers_after_crash_without_another_attempt(self):
        from llm_agent.price_proposer import proposal_context, PROMPT, VERSION

        def crash_after_audit(context, audit):
            proposal = self.proposal_fixture(context, audit)
            visible = proposal_context(context)
            digest = hashlib.sha256(json.dumps(visible, ensure_ascii=False, sort_keys=True,
                separators=(",", ":"), allow_nan=False).encode()).hexdigest()
            validated = {key: proposal[key] for key in ("fare", "reason", "hypothesis")}
            audit.append({"event": "price_proposal_validated", "context_sha256": digest,
                          "prompt_version": VERSION, "prompt_sha256": hashlib.sha256(PROMPT.read_bytes()).hexdigest(),
                          "proposal": validated, "validation": "passed", "source": "test_fixture"})
            # A newer response from another context must never replace this one.
            audit.append({"event": "price_proposal_validated", "context_sha256": "wrong-context",
                          "proposal": {**validated, "fare": 0}, "validation": "passed", "source": "test_fixture"})
            raise engine.Paused("Fixture crash after durable validated output, before proposal checkpoint")

        with patch("llm_agent.price_proposer.propose", side_effect=crash_after_audit):
            paused = self.start(rounds=2)
        self.assertEqual(paused["status"], "paused")
        self.assertEqual(len(paused["rounds"]), 1)
        self.assertNotIn("2", paused["proposals"])
        counts = copy.deepcopy(paused["counts"])
        context = self.contexts[-1]
        recovered = engine.recovered_proposal(paused["run_id"], context)
        self.assertTrue(recovered["recovered_from_audit"])
        self.assertFalse(recovered["provider_call"])
        self.assertEqual(recovered["fare"], round(paused["initial_fare"] * .85, 2))
        self.assertIsNone(engine.recovered_proposal(paused["run_id"], {**context, "round": 3}))
        self.assertEqual(store.read(paused["run_id"])["counts"], counts)
        report = engine.resume(paused["run_id"], {"additional_call_budget": 0})
        self.assert_completed_worlds(report)
        self.assertEqual(self.proposal_calls, [2])
        self.assertEqual(report["counts"]["proposer_calls"], 1)
        self.assertTrue(report["proposals"]["2"]["recovered_from_audit"])
        self.assertEqual(report["proposals"]["2"]["fare"], recovered["fare"])

    def test_provenance_includes_actual_simulation_generator_bytes(self):
        provenance = REAL_PROVENANCE()
        relative = "simulation/generate.py"
        expected = hashlib.sha256((engine.ROOT / relative).read_bytes()).hexdigest()
        self.assertEqual(provenance["files"][relative], expected)


if __name__ == "__main__":
    unittest.main()

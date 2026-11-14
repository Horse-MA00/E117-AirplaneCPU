"""Historical journey runs remain readable without mixing new prompt contracts."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from llm_agent import audit, experiment, journey


class JourneyVersioningTests(unittest.TestCase):
    def write_suite(self, path, edit):
        suite = json.loads((path / "state.json").read_text())
        edit(suite)
        (path / "state.json").write_text(json.dumps(suite))
        return suite

    def test_new_suite_freezes_system_prompt(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "suite"
            journey.export_suite(path)
            suite = json.loads((path / "state.json").read_text())
            self.assertEqual(suite["system_prompt_sha256"], hashlib.sha256(journey.PROMPT.read_bytes()).hexdigest())
            self.assertEqual((path / "system_prompt.txt").read_bytes(), journey.PROMPT.read_bytes())

    def test_old_suite_cannot_regenerate_or_import_packets(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(audit, "BASE", Path(temporary) / "runs"):
            path = Path(temporary) / "suite"
            journey.export_suite(path)
            self.write_suite(path, lambda suite: suite.update(prompt_version="traveller-journey-v2.1"))
            state_before = (path / "state.json").read_bytes()
            pending_before = (path / "pending.jsonl").read_bytes()
            responses = Path(temporary) / "responses.jsonl"
            responses.write_text("")
            for operation in (lambda: journey.export_pending(path), lambda: journey.import_responses(path, responses)):
                with self.assertRaisesRegex(ValueError, "Create a new"):
                    operation()
            self.assertEqual((path / "state.json").read_bytes(), state_before)
            self.assertEqual((path / "pending.jsonl").read_bytes(), pending_before)
            self.assertFalse((Path(temporary) / "runs").exists())

    def test_current_version_with_changed_or_missing_prompt_hash_is_rejected(self):
        for frozen_hash in (None, "0" * 64):
            with self.subTest(frozen_hash=frozen_hash), tempfile.TemporaryDirectory() as temporary:
                path = Path(temporary) / "suite"
                journey.export_suite(path)
                self.write_suite(path, lambda suite: suite.update(system_prompt_sha256=frozen_hash))
                before = (path / "pending.jsonl").read_bytes()
                with self.assertRaisesRegex(ValueError, "Create a new"):
                    journey.export_pending(path)
                self.assertEqual((path / "pending.jsonl").read_bytes(), before)

    def test_changed_saved_system_prompt_is_rejected_before_provider_call(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(audit, "BASE", Path(temporary) / "runs"):
            path = Path(temporary) / "suite"
            experiment.create(path)
            (path / "system_prompt.txt").write_text("A different contract")
            state_before = (path / "state.json").read_bytes()
            with patch.object(experiment, "provider_decision") as provider:
                with self.assertRaisesRegex(ValueError, "Create a new"):
                    experiment.run_batch(path, max_decisions=1, workers=1)
                provider.assert_not_called()
            self.assertEqual((path / "state.json").read_bytes(), state_before)
            self.assertFalse((Path(temporary) / "runs").exists())

    def test_old_provider_suite_is_rejected_before_network(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "suite"
            experiment.create(path)
            self.write_suite(path, lambda suite: suite.update(prompt_version="traveller-journey-v2.1"))
            with patch.object(experiment, "provider_decision") as provider:
                with self.assertRaisesRegex(ValueError, "Create a new"):
                    experiment.run_batch(path, max_decisions=1, workers=1)
                provider.assert_not_called()

    def test_historical_summary_keeps_original_version(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "suite"
            journey.export_suite(path)
            suite = self.write_suite(path, lambda suite: suite.update(prompt_version="traveller-journey-v2.1"))
            self.assertEqual(journey.summarize(suite)["prompt_version"], "traveller-journey-v2.1")


if __name__ == "__main__":
    unittest.main()

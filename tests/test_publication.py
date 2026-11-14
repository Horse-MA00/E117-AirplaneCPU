"""Regression coverage for source packages which omit advertised evidence."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from scripts.check_publication import check_git_ref, check_publication, REQUIRED_FILES


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        for relative in REQUIRED_FILES:
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("{}", encoding="utf-8")
        (self.root / "README.md").write_text(
            "# Review copy\n[Evidence](docs/EXTENDED_VALIDATION.md)\n"
            "[Experiments](llm_agent/experiments/)\n[Extra](docs/extra.md)\n", encoding="utf-8")
        (self.root / "docs/extra.md").write_text("Evidence details", encoding="utf-8")
        experiment = self.root / "llm_agent/experiments/published"
        experiment.mkdir(parents=True)
        payload = b'{"run_id":"test-published","status":"completed","version":"member-thompson-v5-marketing","config":{"profile":"flexible_deal_seekers"}}'
        (experiment / "report.json").write_bytes(payload)
        (experiment / "manifest.json").write_text(json.dumps({"source":"adaptive_thompson_pricing", "run_id":"test-published", "files": {
            "report.json": {"sha256": hashlib.sha256(payload).hexdigest(), "bytes": len(payload)}}}))
        # Extended numerical consistency has its own real-data tests. These
        # fixtures exercise publication/link/archive paths without 400k CSV rows.
        verifier = patch("scripts.check_publication.verify_extended", return_value={"evaluated_flights": 1200})
        self.verifier = verifier.start()
        self.addCleanup(verifier.stop)

    def test_complete_review_copy_resolves_all_relative_links(self):
        report = check_publication(self.root)
        self.assertEqual(report["status"], "passed", report["errors"])
        self.assertEqual(report["relative_links"], 3)
        self.verifier.assert_called_once_with(self.root.resolve())

    def test_missing_readme_target_fails_even_if_not_required_by_name(self):
        (self.root / "docs/extra.md").unlink()
        report = check_publication(self.root)
        self.assertEqual(report["status"], "failed")
        self.assertTrue(any("README.md:4" in error and "docs/extra.md" in error for error in report["errors"]))

    def test_missing_entire_extended_directory_does_not_pass_an_empty_glob(self):
        shutil.rmtree(self.root / "simulation/validation_extended")
        report = check_publication(self.root)
        self.assertEqual(report["status"], "failed")
        self.assertIn("Missing required evidence directory: simulation/validation_extended", report["errors"])
        self.assertTrue(any("forecast_records.jsonl.gz" in error for error in report["errors"]))

    def test_missing_experiments_directory_fails(self):
        shutil.rmtree(self.root / "llm_agent/experiments")
        report = check_publication(self.root)
        self.assertEqual(report["status"], "failed")
        self.assertEqual(report["experiment_manifests"], 0)

    def test_manifest_file_missing_or_corrupt_fails(self):
        artifact = self.root / "llm_agent/experiments/published/report.json"
        artifact.write_text("tampered", encoding="utf-8")
        report = check_publication(self.root)
        self.assertTrue(any("SHA256 mismatch" in error for error in report["errors"]))
        artifact.unlink()
        report = check_publication(self.root)
        self.assertTrue(any("missing or outside-root artifact report.json" in error for error in report["errors"]))

    def test_nested_and_reference_links_resolve_from_document_folder(self):
        (self.root / "docs/extra.md").write_text(
            "[Data][data]\n[data]: ../simulation/README.md\n"
            "[Website](https://example.com/missing)\n[Section](#some-section)\n"
            "```md\n[Not a real link](missing.md)\n```\n", encoding="utf-8")
        report = check_publication(self.root)
        self.assertEqual(report["status"], "passed", report["errors"])
        self.assertEqual(report["relative_links"], 4)

    def test_valid_hash_cannot_publish_a_retired_thompson_version(self):
        folder = self.root / "llm_agent/experiments/published"
        payload = b'{"version":"member-thompson-v4-paired","config":{"profile":"flexible_deal_seekers"}}'
        (folder / "report.json").write_bytes(payload)
        manifest = json.loads((folder / "manifest.json").read_text())
        manifest["files"]["report.json"] = {"sha256": hashlib.sha256(payload).hexdigest(), "bytes": len(payload)}
        (folder / "manifest.json").write_text(json.dumps(manifest))
        report = check_publication(self.root)
        self.assertEqual(report["status"], "failed")
        self.assertTrue(any("retired experiment" in error for error in report["errors"]))

    @unittest.skipUnless(shutil.which("git"), "Git required for committed archive regression")
    def test_untracked_local_file_cannot_hide_missing_committed_evidence(self):
        def git(*args):
            return subprocess.run(["git", "-C", str(self.root), *args], check=True,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        git("init", "-q")
        git("config", "user.name", "Publication Test")
        git("config", "user.email", "publication@example.invalid")
        # Keep the linked file on disk, but deliberately omit it from the commit.
        extra = self.root / "docs/extra.md"
        extra.unlink()
        git("add", ".")
        git("commit", "-qm", "Incomplete review archive")
        extra.write_text("Available locally only", encoding="utf-8")
        self.assertEqual(check_publication(self.root)["status"], "passed")
        archived = check_git_ref(self.root, "HEAD")
        self.assertEqual(archived["status"], "failed")
        self.assertTrue(any("docs/extra.md" in error for error in archived["errors"]))
        git("add", "docs/extra.md")
        git("commit", "-qm", "Include review evidence")
        self.assertEqual(check_git_ref(self.root, "HEAD")["status"], "passed")


if __name__ == "__main__":
    unittest.main()

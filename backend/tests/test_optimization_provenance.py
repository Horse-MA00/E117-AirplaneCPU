import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backend import optimization


class OptimizationDataProvenanceTests(unittest.TestCase):
    def test_new_runs_pin_loader_and_member_demo_dataset_manifest(self):
        files = optimization.provenance()['files']
        for name in ('backend/data.py', 'simulation/member_demo_generated/manifest.json'):
            self.assertIn(name, files)
            self.assertEqual(files[name], hashlib.sha256((optimization.ROOT/name).read_bytes()).hexdigest())

    def test_changes_to_loader_or_future_price_manifest_change_provenance(self):
        paths = optimization.provenance()['files']
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in paths:
                target = root/name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(f'fixture:{name}')
            with patch.object(optimization, 'ROOT', root):
                for name in ('backend/data.py', 'simulation/member_demo_generated/manifest.json'):
                    before = optimization.provenance()
                    (root/name).write_text(f'changed:{name}')
                    self.assertNotEqual(before, optimization.provenance())

    def test_separate_attestation_does_not_claim_original_capture(self):
        path = optimization.ROOT/'docs/MEMBER_DEMO_DATA_ATTESTATION_2026-11-14.json'
        report = json.loads(path.read_text())
        self.assertEqual(report['attestation_type'], 'post_run_current_state_data_comparison')
        self.assertFalse(report['proves_original_run_time_data_manifest_capture'])
        self.assertEqual(len(report['experiments']), 2)
        for experiment in report['experiments']:
            for name, digest in experiment['original_artifact_sha256'].items():
                self.assertEqual(hashlib.sha256((optimization.ROOT/name).read_bytes()).hexdigest(), digest)
            self.assertTrue(experiment['saved_as_of_history_matches_current_data'])
            self.assertEqual(experiment['missing_original_provenance_files'],
                             ['backend/data.py', 'simulation/member_demo_generated/manifest.json'])


if __name__ == '__main__':
    unittest.main()

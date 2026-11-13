"""Regression: freeze the calibration artifact actually read by NHPP v2."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from llm_agent import audit, market_experiment


class MarketProvenanceTests(unittest.TestCase):
    def test_snapshot_contains_runtime_guard(self):
        guard = 'simulation/generated/calibration_v2.json'
        root = Path(market_experiment.__file__).resolve().parents[1]
        self.assertEqual(market_experiment.implementation_hashes().get(guard),
                         hashlib.sha256((root / guard).read_bytes()).hexdigest())

    def test_resume_rejects_changed_runtime_guard_without_mutating_file(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(audit, 'BASE', Path(temporary) / 'audits'):
            output = Path(temporary) / 'experiment'
            market_experiment.create_experiment(output, config={'customer_count': 1, 'flight_count': 6})
            original = Path.read_bytes
            def altered(path):
                raw = original(path)
                return raw + b'\n' if path.name == 'calibration_v2.json' else raw
            with patch.object(Path, 'read_bytes', altered):
                with self.assertRaisesRegex(ValueError, 'implementation changed'):
                    market_experiment.run_batch(output, 0, 1)

    def test_resume_rejects_missing_provenance(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(audit, 'BASE', Path(temporary) / 'audits'):
            output = Path(temporary) / 'experiment'
            market_experiment.create_experiment(output, config={'customer_count': 1, 'flight_count': 6})
            path = output / 'experiment.json'
            spec = json.loads(path.read_text())
            del spec['implementation_hashes']
            path.write_text(json.dumps(spec))
            with self.assertRaisesRegex(ValueError, 'implementation changed'):
                market_experiment.run_batch(output, 0, 1)


if __name__ == '__main__':
    unittest.main()

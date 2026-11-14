"""Frozen evaluation must be present in a downloaded or packaged application."""
import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from backend import server
from backend.evidence import EvidenceUnavailable, read_evaluation, verify_extended

ROOT = Path(__file__).resolve().parents[2]


class EvidenceTests(unittest.TestCase):
    def test_missing_extended_report_is_not_an_implicitly_pending_job(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(server, 'ROOT', Path(folder)):
            with self.assertRaisesRegex(ValueError, 'evidence unavailable'):
                server.get('/api/evaluation/extended')

    def test_http_handler_returns_503_for_missing_frozen_evidence(self):
        # Drive the real GET dispatch without starting a port or touching demo DBs.
        with tempfile.TemporaryDirectory() as folder, patch.object(server, 'ROOT', Path(folder)):
            for path in ('/api/evaluation', '/api/evaluation/extended'):
                handler = object.__new__(server.Handler)
                handler.headers = {'Host': 'localhost'}
                handler.path = path
                handler.json = Mock()
                handler.do_GET()
                status, body = handler.json.call_args.args
                self.assertEqual(status, 503)
                self.assertEqual(body['status'], 'unavailable')
                self.assertEqual(body['code'], 'evaluation_evidence_unavailable')
                self.assertIn('Restore the complete published repository', body['error'])

    def test_success_preserves_original_api_payload(self):
        expected = json.loads((ROOT / 'simulation/validation_extended/report.json').read_text())
        with patch.object(server, 'ROOT', ROOT):
            self.assertEqual(server.get('/api/evaluation/extended'), expected)
        result = verify_extended(ROOT)
        self.assertEqual(result['evaluated_flights'], 1200)
        self.assertEqual(result['scored_predictions'], 7200)
        self.assertEqual(result['surge_d28'], {'covered': 183, 'total': 200, 'coverage': .915})

    def evidence_copy(self, folder):
        root = Path(folder)
        shutil.copytree(ROOT / 'simulation/validation_extended', root / 'simulation/validation_extended')
        (root / 'backend').mkdir()
        shutil.copy2(ROOT / 'backend/nhpp_v2.py', root / 'backend/nhpp_v2.py')
        return root

    def test_missing_payload_cannot_pass_as_a_valid_report(self):
        with tempfile.TemporaryDirectory() as folder:
            root = self.evidence_copy(folder)
            (root / 'simulation/validation_extended/forecast_records.jsonl.gz').unlink()
            with self.assertRaisesRegex(EvidenceUnavailable, 'forecast_records'):
                read_evaluation(root, extended=True)
            with self.assertRaises(EvidenceUnavailable):
                verify_extended(root)

    def test_corrupt_report_is_rejected_by_api(self):
        with tempfile.TemporaryDirectory() as folder:
            root = self.evidence_copy(folder)
            (root / 'simulation/validation_extended/report.json').write_text('{')
            with self.assertRaisesRegex(EvidenceUnavailable, 'checksum'):
                read_evaluation(root, extended=True)

    def test_malformed_manifest_and_summary_are_explicitly_unavailable(self):
        with tempfile.TemporaryDirectory() as folder:
            root = self.evidence_copy(folder)
            base = root / 'simulation/validation_extended'
            original = json.loads((base / 'manifest.json').read_text())
            for files in (None, list(original['files'])):
                manifest = {**original, 'files': files}
                (base / 'manifest.json').write_text(json.dumps(manifest))
                with self.assertRaisesRegex(EvidenceUnavailable, 'inventory'):
                    read_evaluation(root, extended=True)
            report = json.loads((base / 'report.json').read_text())
            report['summary'] = ['not a summary object']
            raw = json.dumps(report).encode()
            (base / 'report.json').write_bytes(raw)
            original['files']['report.json'] = {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
            (base / 'manifest.json').write_text(json.dumps(original))
            with self.assertRaisesRegex(EvidenceUnavailable, 'summary'):
                read_evaluation(root, extended=True)

    def test_coverage_claim_is_recomputed_from_records(self):
        with tempfile.TemporaryDirectory() as folder:
            root = self.evidence_copy(folder)
            base = root / 'simulation/validation_extended'
            report = json.loads((base / 'report.json').read_text())
            report['summary']['v2/D28/surge']['coverage'] = .92
            raw = json.dumps(report).encode()
            (base / 'report.json').write_bytes(raw)
            manifest = json.loads((base / 'manifest.json').read_text())
            manifest['files']['report.json'] = {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
            (base / 'manifest.json').write_text(json.dumps(manifest))
            with self.assertRaisesRegex(EvidenceUnavailable, 'coverage disagrees'):
                verify_extended(root)


if __name__ == '__main__':
    unittest.main()

"""Windows path and locale regressions, exercised without a Windows host."""
from contextlib import contextmanager, redirect_stdout
import gzip
import hashlib
import io
import json
from pathlib import Path, PureWindowsPath
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from backend import adaptive_pricing
from llm_agent import adaptive_customers
from scripts import verify_artifacts


@contextmanager
def cp950_default_reads():
    """Emulate Windows' locale fallback while preserving explicit encodings."""
    read_text, gzip_open = Path.read_text, gzip.open

    def locale_read_text(path, *args, **kwargs):
        if not args and kwargs.get('encoding') is None:
            kwargs['encoding'] = 'cp950'
        return read_text(path, *args, **kwargs)

    def locale_gzip_open(path, mode='rb', *args, **kwargs):
        if 't' in mode and kwargs.get('encoding') is None:
            kwargs['encoding'] = 'cp950'
        return gzip_open(path, mode, *args, **kwargs)

    with patch.object(Path, 'read_text', locale_read_text), patch.object(gzip, 'open', locale_gzip_open):
        yield


def write_json(path, value):
    path.write_bytes(json.dumps(value, ensure_ascii=False).encode('utf-8'))


class ProvenancePathTests(unittest.TestCase):
    def test_prompt_metadata_serializes_windows_relative_paths_as_posix(self):
        prompt = Mock()
        prompt.relative_to.return_value = PureWindowsPath('llm_agent/prompts/adaptive_customer_v4_en.txt')
        prompt.read_bytes.return_value = b'unchanged prompt bytes'
        with patch.dict(adaptive_customers.PROMPTS, {'customer': prompt}, clear=True):
            metadata = adaptive_customers.prompt_metadata()['prompts']['customer']
        self.assertEqual(metadata['path'], 'llm_agent/prompts/adaptive_customer_v4_en.txt')
        self.assertEqual(metadata['sha256'], hashlib.sha256(prompt.read_bytes.return_value).hexdigest())

    def test_provenance_serializes_windows_manifest_keys_as_posix(self):
        class WindowsSource(PureWindowsPath):
            def glob(self, pattern):
                return iter([self / 'hkx_recent_generated/manifest.json'])

            def read_bytes(self):
                return b'unchanged source bytes'

        with patch.object(adaptive_pricing, 'ROOT', WindowsSource('C:/checkout')):
            files = adaptive_pricing._provenance()['files']
        self.assertIn('simulation/hkx_recent_generated/manifest.json', files)
        self.assertTrue(all('\\' not in name for name in files))


class ArtifactPortabilityTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def test_utf8_manifest_and_compressed_csv_ignore_cp950_locale(self):
        snapshots = self.root / 'snapshots.csv.gz'
        payload = 'flight_id,destination\nTEST,香港 ✈\n'.encode('utf-8')
        with self.assertRaises(UnicodeDecodeError):
            payload.decode('cp950')
        snapshots.write_bytes(gzip.compress(payload))
        manifest = self.root / 'manifest.json'
        write_json(manifest, {'note': '香港 ✈', 'rows': 1,
                             'files': {'snapshots.csv.gz': hashlib.sha256(snapshots.read_bytes()).hexdigest()}})
        with cp950_default_reads():
            result = verify_artifacts.verify(manifest)
        self.assertEqual(result['snapshot_rows'], 1)

    def test_utf8_report_ignores_cp950_locale_and_retains_audit_validation(self):
        source = verify_artifacts.ROOT / 'llm_agent/experiments/current_thompson_v5_749c60ea38b34eb2'
        report = json.loads((source / 'report.json').read_bytes())
        report['name'] = '香港 ✈'
        write_json(self.root / 'report.json', report)
        (self.root / 'audit.jsonl.gz').write_bytes((source / 'audit.jsonl.gz').read_bytes())
        manifest = json.loads((source / 'manifest.json').read_bytes())
        manifest['files'] = {name: hashlib.sha256((self.root / name).read_bytes()).hexdigest()
                             for name in ('report.json', 'audit.jsonl.gz')}
        write_json(self.root / 'manifest.json', manifest)
        with cp950_default_reads():
            result = verify_artifacts.verify(self.root / 'manifest.json')
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(result['audit_records'], manifest['audit_records'])

    def test_recent_dataset_is_required_by_full_verification(self):
        generated = self.root / 'simulation/generated'
        generated.mkdir(parents=True)
        write_json(generated / 'manifest.json', {'files': {}})
        with patch.object(verify_artifacts, 'ROOT', self.root), \
                patch('backend.evidence.verify_extended', return_value={}), \
                redirect_stdout(io.StringIO()), self.assertRaises(FileNotFoundError):
            verify_artifacts.main()

    def test_recent_dataset_checksums_are_verified_by_full_verification(self):
        for name in ('generated', 'hkx_recent_generated'):
            folder = self.root / 'simulation' / name
            folder.mkdir(parents=True)
            write_json(folder / 'manifest.json', {'files': {}})
        recent = self.root / 'simulation/hkx_recent_generated'
        (recent / 'flights.json').write_bytes(b'[]')
        write_json(recent / 'manifest.json', {'files': {'flights.json': '0' * 64}})
        with patch.object(verify_artifacts, 'ROOT', self.root), \
                patch('backend.evidence.verify_extended', return_value={}), \
                redirect_stdout(io.StringIO()), self.assertRaises(AssertionError):
            verify_artifacts.main()

    def test_pilot_cli_reads_utf8_response_reasons_under_cp950(self):
        from scripts import member_choice_calibration as pilot
        scope = {'flight_id': 'TEST-HKG-KMQ', 'origin': 'HKG', 'destination': 'KMQ',
                 'departure_date': '2027-05-18', 'departure_time': '10:00', 'as_of_day': 28,
                 'normal_base_fare': 410, 'releasable_seats': 10}
        study = pilot.make_study(scope, participants=3)
        responses = pilot.response_template(study)
        # Test fixture only, never published as collected human evidence.
        responses['responses'][0].update(source='human_self_report', action='DECLINE',
                                         reason='香港 ✈', answered_at='2026-11-15T10:00:00+08:00')
        write_json(self.root / 'study.json', study)
        write_json(self.root / 'responses.json', responses)
        output = self.root / 'summary.json'
        argv = ['member_choice_calibration.py', 'summarize', '--study', str(self.root / 'study.json'),
                '--responses', str(self.root / 'responses.json'), '--output', str(output)]
        with cp950_default_reads(), patch.object(sys, 'argv', argv), redirect_stdout(io.StringIO()):
            pilot.main()
        summary = json.loads(output.read_bytes())
        self.assertEqual(summary['recorded_responses'], 1)
        self.assertFalse(summary['automatic_model_updates'])


if __name__ == '__main__':
    unittest.main()

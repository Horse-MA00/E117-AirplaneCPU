"""Publication integrity, redaction and semantic checks; no live model calls."""
import copy
import gzip
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import export_feedback_pricing as exporter, verify_artifacts


class FeedbackExportTests(unittest.TestCase):
    def payload(self):
        run_id = 'feedback-0123456789abcdef'
        counts = {'provider_calls': 1, 'customer_calls': 1, 'proposer_calls': 0,
                  'total_attempts': 1, 'cache_hits': 0, 'forced': 0, 'failures': 0}
        report = {'run_id': run_id, 'status': 'completed', 'counts': counts,
                  'config': {'objective': 'base_ticket_revenue', 'membership_fee': 0},
                  'validation': {'seeds': [50120, 50221]}}
        ledger = {field: 0 for field in ('membership_revenue', 'ancillary_revenue', 'cancellation_revenue',
                  'mandatory_liability', 'mandatory_remitted', 'passenger_cost', 'ancillary_cost',
                  'membership_service_cost', 'program_cost', 'total_variable_cost', 'total_cost')}
        ledger.update(normal_base_revenue=100, member_base_revenue=20)
        worlds = []
        for phase, seed in [('baseline', 117), ('search', 117), ('holdout_no_offer', 50120),
                            ('holdout_initial', 50120), ('holdout_no_offer', 50221), ('holdout_initial', 50221)]:
            worlds.append({'world_id': f'{run_id}-{phase}-{seed}', 'run_id': run_id, 'phase': phase, 'seed': seed,
                'state': {'policy': {'membership_fee': 0}},
                'result': {'complete': True, 'checks': {'fixture_accounting': True}, 'ledger': copy.deepcopy(ledger),
                    'ticket_revenue': 120, 'tickets_sold': 3, 'tickets_flown': 2, 'tickets_cancelled': 1,
                    'exogenous_sha256': f'matched-{seed}'}})
        events = [{'id': 1, 'record': {'event': 'market_choice', 'source': 'provider_live',
                  'raw_response_text': 'Fixture only, never an actual provider response: SECRET_EXPORT_TEST_123'}}]
        return {'report': report, 'worlds': worlds, 'events': events}

    def test_export_redacts_preserves_checksums_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(exporter, 'load_local_env'), \
                patch.dict('os.environ', {'LLM_API_KEY': 'SECRET_EXPORT_TEST_123'}), \
                patch.object(verify_artifacts, 'ROOT', Path(temporary)):
            output = Path(temporary) / 'evidence'
            result = exporter.export_payload(self.payload(), output)
            self.assertEqual(result['worlds'], 6)
            verification = verify_artifacts.verify(output / 'manifest.json')
            self.assertEqual(verification['audit_records'], 1)
            self.assertEqual(verification['search_seeds'], [117])
            self.assertEqual(verification['holdout_seeds'], [50120, 50221])
            with gzip.open(output / 'audit.jsonl.gz', 'rt') as stream:
                text = stream.read()
            self.assertNotIn('SECRET_EXPORT_TEST_123', text)
            self.assertIn('[REDACTED]', text)
            before = (output / 'manifest.json').read_bytes()
            with self.assertRaisesRegex(ValueError, 'overwrite'):
                exporter.export_payload(self.payload(), output)
            self.assertEqual((output / 'manifest.json').read_bytes(), before)

    def test_incomplete_or_fixture_decisions_cannot_be_published(self):
        cases = []
        payload = self.payload(); payload['report']['status'] = 'running'; cases.append(payload)
        payload = self.payload(); payload['worlds'][0]['result']['complete'] = False; cases.append(payload)
        payload = self.payload(); payload['events'][0]['record']['source'] = 'test_fixture'; cases.append(payload)
        for payload in cases:
            with self.subTest(payload=payload), tempfile.TemporaryDirectory() as temporary, \
                    patch.object(exporter, 'load_local_env'):
                output = Path(temporary) / 'evidence'
                with self.assertRaises(ValueError): exporter.export_payload(payload, output)
                self.assertFalse(output.exists())

    def test_verifier_rejects_rehashed_semantic_corruption(self):
        for change in ('revenue', 'cost', 'seed_overlap', 'audit_count'):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as temporary, \
                    patch.object(exporter, 'load_local_env'), patch.object(verify_artifacts, 'ROOT', Path(temporary)):
                output = Path(temporary) / 'evidence'
                exporter.export_payload(self.payload(), output)
                manifest = json.loads((output / 'manifest.json').read_text())
                if change == 'audit_count':
                    manifest['audit_records'] = 2
                elif change == 'seed_overlap':
                    report = json.loads((output / 'report.json').read_text())
                    report['validation']['seeds'] = [117, 50221]
                    (output / 'report.json').write_text(json.dumps(report))
                else:
                    with gzip.open(output / 'worlds.json.gz', 'rt') as stream: worlds = json.load(stream)
                    if change == 'revenue': worlds[0]['result']['ticket_revenue'] = 999
                    else: worlds[0]['result']['ledger']['passenger_cost'] = 1
                    with gzip.open(output / 'worlds.json.gz', 'wt') as stream: json.dump(worlds, stream)
                # A matching checksum is not enough: verify economic/seed invariants.
                for name in manifest['files']:
                    raw = (output / name).read_bytes()
                    manifest['files'][name] = {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}
                (output / 'manifest.json').write_text(json.dumps(manifest))
                with self.assertRaises(AssertionError): verify_artifacts.verify(output / 'manifest.json')


if __name__ == '__main__':
    unittest.main()

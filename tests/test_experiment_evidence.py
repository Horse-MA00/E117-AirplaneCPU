"""Terminal saved evidence remains auditable even when analysis/execution failed."""
import copy
import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from scripts.verify_artifacts import ROOT, _audit_summary, verify


class ExperimentEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Immutable real v5 export supplies realistic population, pairing and
        # holdout structure; each test mutates only its temporary copy.
        source = ROOT / 'llm_agent/experiments/current_thompson_v5_749c60ea38b34eb2'
        cls.base_report = json.loads((source / 'report.json').read_text())
        cls.base_manifest = json.loads((source / 'manifest.json').read_text())
        with gzip.open(source / 'audit.jsonl.gz', 'rt') as stream:
            cls.base_events = [json.loads(line) for line in stream]

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.folder = Path(temporary.name)
        self.report = copy.deepcopy(self.base_report)
        self.manifest = copy.deepcopy(self.base_manifest)
        self.events = copy.deepcopy(self.base_events)

    def append(self, record):
        self.events.append({'id': self.events[-1]['id'] + 1 if self.events else 1,
                            'run_id': self.report['run_id'], 'recorded_at': 1, 'record': record})

    def write(self, recount=False):
        with gzip.open(self.folder / 'audit.jsonl.gz', 'wt') as stream:
            for event in self.events:
                stream.write(json.dumps(event) + '\n')
        if recount:
            audit = _audit_summary(self.folder / 'audit.jsonl.gz', self.report['run_id'])
            for key in ('provider_calls','fresh_responses','cache_hits','forced','failures','synthetic_choices',
                        'customer_calls','analyst_calls','total_tokens','analyst_retries','analyst_unavailable'):
                self.report['counts'][key] = audit['counts'][key]
            self.report['counts']['key_slots'] = dict(audit['key_slots'])
            self.report['counts']['remaining_calls'] = self.report['config']['max_calls'] - self.report['counts']['provider_calls']
        (self.folder / 'report.json').write_text(json.dumps(self.report))
        self.manifest['counts'] = self.report['counts']
        self.manifest['audit_records'] = len(self.events)
        self.manifest['files'] = {}
        for name in ('report.json','audit.jsonl.gz'):
            payload = (self.folder / name).read_bytes()
            self.manifest['files'][name] = {'sha256': hashlib.sha256(payload).hexdigest(), 'bytes': len(payload)}
        path = self.folder / 'manifest.json'
        path.write_text(json.dumps(self.manifest))
        return path

    def failed_prefix(self, status='failed'):
        stop = next(i for i,e in enumerate(self.events) if e['record']['event']=='round_completed') + 1
        self.events = self.events[:stop]
        self.report.update(status=status,error='Live analyst response failed validation or transport',
                           recommendation=None,validation=None,validation_worlds=[])
        self.report['rounds'] = self.report['rounds'][:1]
        self.report['search_panels'] = self.report['search_panels'][:2]
        ids = {p['customer_id'] for c in self.report['search_panels'] for p in c['people']}
        self.report['training_observations'] = [r for r in self.report['training_observations'] if r['person']['customer_id'] in ids]
        self.manifest['evidence_kind'] = 'execution_failure'
        self.manifest.pop('holdout_frozen_before_validation',None)
        if status=='failed':
            self.append({'event':'run_failed','error':self.report['error']})

    def test_legacy_completed_export_remains_valid(self):
        self.assertEqual(verify(self.write())['status'],'completed')

    def test_recovered_analyst_failure_is_valid_when_audit_counters_match(self):
        self.append({'event':'analyst_request','key_slot':'primary','attempt':2})
        self.append({'event':'analyst_response','usage':{'total_tokens':12}})
        self.append({'event':'analyst_failed','provider_call':True,'validation':'failed','error':'Invalid analysis'})
        result = verify(self.write(recount=True))
        self.assertEqual(result['status'],'completed')
        self.assertEqual(self.report['counts']['failures'],1)

    def test_report_failure_count_cannot_hide_or_invent_audited_failures(self):
        self.report['counts']['failures'] = 1
        with self.assertRaisesRegex(AssertionError,'failures disagrees with audit'):
            verify(self.write())

    def test_failed_prefix_preserves_incomplete_status_and_has_no_holdout(self):
        self.failed_prefix()
        result = verify(self.write(recount=True))
        self.assertEqual(result['status'],'failed')
        self.assertEqual(result['validated_price_rounds'],1)
        self.assertIsNone(self.report['validation'])

    def test_interrupted_prefix_does_not_need_a_fabricated_failure_event(self):
        self.failed_prefix('interrupted')
        self.assertEqual(verify(self.write(recount=True))['status'],'interrupted')

    def test_incomplete_cannot_claim_completed_evidence_or_frozen_holdout(self):
        self.failed_prefix()
        self.manifest['evidence_kind'] = 'completed'
        with self.assertRaisesRegex(AssertionError,'Evidence kind'):
            verify(self.write(recount=True))
        self.manifest['evidence_kind'] = 'execution_failure'
        self.manifest['holdout_frozen_before_validation'] = True
        with self.assertRaisesRegex(AssertionError,'holdout claim'):
            verify(self.write(recount=True))

    def test_active_status_cannot_be_published(self):
        for status in ('queued','running'):
            with self.subTest(status=status):
                self.report['status']=status
                with self.assertRaisesRegex(AssertionError,'Only terminal'):
                    verify(self.write())

    def test_corrupt_audit_bytes_and_wrong_run_are_rejected(self):
        manifest = self.write()
        with (self.folder/'audit.jsonl.gz').open('ab') as stream:stream.write(b'corrupt')
        with self.assertRaises(AssertionError):verify(manifest)
        self.events[0]['run_id']='another-run'
        with self.assertRaises(AssertionError):verify(self.write())

    def test_valid_hashes_cannot_hide_holdout_value_changes(self):
        self.report['validation_worlds'][0]['result']['remaining_seats'] += 1
        with self.assertRaisesRegex(AssertionError,'Validation worlds disagree'):
            verify(self.write())

    def test_failed_error_must_match_the_durable_audit(self):
        self.failed_prefix()
        self.report['error']='Different invented reason'
        with self.assertRaisesRegex(AssertionError,'Failure error disagrees'):
            verify(self.write(recount=True))


if __name__ == '__main__':
    unittest.main()

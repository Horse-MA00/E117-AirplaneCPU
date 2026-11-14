"""A clean deployment can replay shipped evidence without a DB import or calls."""
import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backend import adaptive_pricing, adaptive_store as store
from backend import published_experiments as published


class PublishedExperimentsTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.root = self.base / 'published'
        self.root.mkdir()
        for name, value in (('BASE', self.base / 'private'), ('_published', None)):
            scope = patch.object(store, name, value)
            scope.start()
            self.addCleanup(scope.stop)

    def write(self, name='demo', run_id='adaptive-published', status='completed',
              created_at=100, records=None, report_changes=None, manifest_changes=None):
        directory = self.root / name
        directory.mkdir(exist_ok=True)
        report = {'run_id': run_id, 'version': adaptive_pricing.VERSION,
                  'config': {'profile': 'flexible_deal_seekers', 'name': 'DEMO_LLM0'},
                  'status': status, 'created_at': created_at, 'updated_at': created_at + 1,
                  'rounds': [], 'recommendation': None, 'validation': None,
                  'error': 'Provider error' if status == 'failed' else None}
        report.update(report_changes or {})
        if records is None:
            records = [{'event': 'analyst_request', 'round': 1, 'attempt': 1, 'context_sha256': 'hash'},
                       {'event': 'analyst_response', 'round': 1, 'attempt': 1,
                        'raw_response_text': '{"original": true}'},
                       {'event': 'analyst_validated', 'round': 1, 'attempt': 1}]
        events = [{'id': 41 + 3 * index, 'run_id': run_id, 'recorded_at': 200 + index, 'record': record}
                  for index, record in enumerate(records)]
        (directory / 'report.json').write_text(json.dumps(report), encoding='utf-8')
        with gzip.open(directory / 'audit.jsonl.gz', 'wt', encoding='utf-8') as target:
            for event in events:
                target.write(json.dumps(event) + '\n')
        manifest = {'run_id': run_id, 'version': report['version'], 'profile': report['config']['profile'],
                    'source': 'adaptive_thompson_pricing', 'synthetic': True,
                    'audit_records': len(events),
                    'evidence_kind': 'completed' if status == 'completed' else 'execution_failure'}
        manifest.update(manifest_changes or {})
        self.remanifest(directory, manifest)
        return report, events, directory

    def remanifest(self, directory, manifest=None):
        if manifest is None:
            manifest = json.loads((directory / 'manifest.json').read_text())
        manifest['files'] = {name: {'bytes': (directory / name).stat().st_size,
                                    'sha256': hashlib.sha256((directory / name).read_bytes()).hexdigest()}
                             for name in ('report.json', 'audit.jsonl.gz')}
        (directory / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')

    def test_clean_deployment_reads_report_pages_and_analyst_without_import(self):
        report, events, directory = self.write()
        before = {p.name: p.read_bytes() for p in directory.iterdir()}
        with patch('backend.adaptive_pricing.start', side_effect=AssertionError('No live experiments')):
            self.assertEqual(store.enable_published_experiments(self.root), 1)
            self.assertEqual(adaptive_pricing.list_runs()[0]['run_id'], report['run_id'])
            loaded = adaptive_pricing.read(report['run_id'])
            self.assertEqual(loaded['storage'], {'source': 'published_export', 'read_only': True})
            self.assertEqual({k: v for k, v in loaded.items() if k != 'storage'}, report)
            self.assertEqual(adaptive_pricing.events(report['run_id'], 1, 1)['events'], events[1:2])
            self.assertEqual(store.events(report['run_id'], 2, 100)['events'], [])
            summary = store.analysis_attempts(report['run_id'])['attempts'][0]
            self.assertEqual(summary['status'], 'passed')
            self.assertNotIn('raw_response_text', summary)
            self.assertEqual(store.analysis_attempts(report['run_id'], 1)['attempts'][0]['raw_response_text'],
                             '{"original": true}')
            self.assertEqual(store.export_run(report['run_id'])['events'], events)
        with store.connection() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM adaptive_runs').fetchone()[0], 0)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM adaptive_events').fetchone()[0], 0)
        self.assertEqual({p.name: p.read_bytes() for p in directory.iterdir()}, before)
        self.assertEqual(store.enable_published_experiments(self.root), 1)
        self.assertEqual(len(store.list_runs()), 1)

    def test_local_same_id_wins_for_every_endpoint_and_list_is_sorted(self):
        report, _, _ = self.write(created_at=100)
        self.write('newer', 'adaptive-newer', created_at=200)
        store.enable_published_experiments(self.root)
        local = {**report, 'created_at': 50, 'rounds': [{'local': True}]}
        store.save(local)
        store.record(local['run_id'], {'event': 'analyst_response', 'round': 2, 'attempt': 1,
                                       'raw_response_text': 'local raw'})
        self.assertEqual([r['run_id'] for r in store.list_runs()], ['adaptive-newer', 'adaptive-published'])
        self.assertEqual([r['run_id'] for r in store.list_runs(1)], ['adaptive-newer'])
        self.assertEqual(store.read(local['run_id'])['rounds'], [{'local': True}])
        self.assertNotIn('storage', store.read(local['run_id']))
        self.assertEqual(len(store.events(local['run_id'])['events']), 1)
        self.assertEqual(store.analysis_attempts(local['run_id'], 2)['attempts'][0]['raw_response_text'], 'local raw')
        self.assertEqual(len(store.export_run(local['run_id'])['events']), 1)
        # A local record outside the list limit still hides its newer packaged copy.
        self.write('unused', 'adaptive-unused')  # Not loaded until explicit restart.
        store.save({**report, 'run_id': 'adaptive-local-newer', 'created_at': 150})
        self.assertEqual([r['run_id'] for r in store.list_runs(2)], ['adaptive-newer', 'adaptive-local-newer'])

    def test_failed_and_interrupted_evidence_is_readable_without_fake_validation(self):
        for index, status in enumerate(('failed', 'interrupted')):
            self.write(status, 'adaptive-' + status, status=status, created_at=100 + index)
        store.enable_published_experiments(self.root)
        with patch.object(store, 'save', side_effect=AssertionError('Terminal evidence is immutable')):
            for status in ('failed', 'interrupted'):
                run = adaptive_pricing.read('adaptive-' + status)
                self.assertEqual(run['status'], status)
                self.assertIsNone(run['recommendation'])
                self.assertIsNone(run['validation'])
        self.assertEqual(len(store.list_runs()), 2)

    def test_legacy_completed_manifest_is_accepted_but_failed_needs_evidence_kind(self):
        _, _, directory = self.write()
        manifest = json.loads((directory / 'manifest.json').read_text())
        del manifest['evidence_kind']
        self.remanifest(directory, manifest)
        self.assertEqual(len(published.PublishedExperiments(self.root).summaries()), 1)
        report = json.loads((directory / 'report.json').read_text())
        report['status'] = 'failed'
        (directory / 'report.json').write_text(json.dumps(report))
        self.remanifest(directory)
        with self.assertRaisesRegex(ValueError, 'evidence kind'):
            published.PublishedExperiments(self.root)

    def test_active_retired_or_wrong_population_exports_fail_closed(self):
        for changes in ({'status': 'running'}, {'status': 'queued'},
                        {'version': 'member-thompson-v4-integer'},
                        {'config': {'profile': 'broad_coverage'}}):
            with self.subTest(changes=changes):
                self.write(report_changes=changes)
                with self.assertRaises(ValueError):
                    store.enable_published_experiments(self.root)
                self.assertIsNone(store._published)

    def test_duplicate_ids_and_unsafe_paths_are_rejected(self):
        _, _, first = self.write()
        self.write('duplicate')
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            published.PublishedExperiments(self.root)
        for child in (self.root / 'duplicate').iterdir():
            child.unlink()
        (self.root / 'duplicate').rmdir()
        outside = self.base / 'external.json'
        outside.write_bytes((first / 'report.json').read_bytes())
        (first / 'report.json').unlink()
        (first / 'report.json').symlink_to(outside)
        with self.assertRaisesRegex(ValueError, 'Unsafe'):
            published.PublishedExperiments(self.root)

    def test_artifact_hash_missing_file_and_size_are_checked_before_exposure(self):
        _, _, directory = self.write()
        (directory / 'report.json').write_text('changed')
        with self.assertRaisesRegex(ValueError, 'byte count|SHA256'):
            published.PublishedExperiments(self.root)
        self.write()
        with patch.object(published, 'MAX_REPORT_BYTES', 5):
            with self.assertRaisesRegex(ValueError, 'oversized'):
                published.PublishedExperiments(self.root)
        (directory / 'audit.jsonl.gz').unlink()
        with self.assertRaisesRegex(ValueError, 'missing'):
            published.PublishedExperiments(self.root)

    def test_missing_deployment_directory_and_incomplete_exports_fail_closed(self):
        with self.assertRaisesRegex(ValueError, 'missing from the deployment'):
            published.PublishedExperiments(self.base / 'missing')
        # An intentionally empty directory remains a valid empty catalog.
        self.assertEqual(published.PublishedExperiments(self.root).summaries(), [])
        (self.root / 'incomplete').mkdir()
        with self.assertRaisesRegex(ValueError, 'missing published file'):
            published.PublishedExperiments(self.root)

    def test_nonfinite_json_numbers_are_rejected_even_in_nested_report_fields(self):
        _, _, directory = self.write()
        for invalid in ('NaN', 'Infinity', '1e999'):
            with self.subTest(invalid=invalid):
                self.write()
                path = directory / 'report.json'
                path.write_text(path.read_text().replace('"recommendation": null',
                    '"recommendation": {"price": ' + invalid + '}'))
                self.remanifest(directory)
                with self.assertRaisesRegex(ValueError, 'non-finite'):
                    published.PublishedExperiments(self.root)

    def test_catalog_detects_files_changed_after_validation(self):
        report, _, directory = self.write()
        catalog = published.PublishedExperiments(self.root)
        with (directory / 'report.json').open('a') as target:
            target.write(' ')
        for method in (catalog.summaries, lambda: catalog.read(report['run_id'])):
            with self.assertRaisesRegex(ValueError, 'changed after validation'):
                method()

    def test_audit_count_ids_run_id_and_gzip_integrity_checked_before_first_page(self):
        for issue in ('count', 'ordering', 'run_id', 'gzip'):
            with self.subTest(issue=issue):
                report, events, directory = self.write()
                if issue == 'gzip':
                    (directory / 'audit.jsonl.gz').write_bytes(b'not a gzip archive')
                else:
                    if issue == 'count':
                        events.pop()
                    elif issue == 'ordering':
                        events[-1]['id'] = events[0]['id']
                    elif issue == 'run_id':
                        events[-1]['run_id'] = 'adaptive-another'
                    with gzip.open(directory / 'audit.jsonl.gz', 'wt') as target:
                        target.writelines(json.dumps(e) + '\n' for e in events)
                self.remanifest(directory)
                catalog = published.PublishedExperiments(self.root)
                with self.assertRaises(ValueError):
                    catalog.events(report['run_id'], 1, 0, store.MAX_EXPORT_BYTES)

    def test_audit_decompression_line_and_record_limits(self):
        report, _, _ = self.write(records=[{'event': 'customer_response', 'raw_response_text': 'x' * 3000}])
        for name, limit in (('MAX_AUDIT_BYTES', 300), ('MAX_EVENT_BYTES', 300), ('MAX_AUDIT_RECORDS', 0)):
            with self.subTest(name=name):
                catalog = published.PublishedExperiments(self.root)
                with patch.object(published, name, limit), self.assertRaisesRegex(ValueError, 'decompression limit'):
                    catalog.events(report['run_id'], 1, 0, store.MAX_EXPORT_BYTES)

    def test_inline_export_page_and_raw_analyst_limits_preserve_paginated_access(self):
        report, _, _ = self.write(records=[{'event': 'analyst_response', 'round': 1, 'attempt': 1,
                                            'raw_response_text': '"' * 1000}])
        store.enable_published_experiments(self.root)
        with patch.object(store, 'MAX_EXPORT_BYTES', 1500):
            self.assertEqual(len(store.analysis_attempts(report['run_id'])['attempts']), 1)
            with self.assertRaisesRegex(ValueError, 'inline export limit'):
                store.analysis_attempts(report['run_id'], 1)
            with self.assertRaisesRegex(ValueError, 'inline export limit'):
                store.export_run(report['run_id'])
            with self.assertRaisesRegex(ValueError, 'smaller page'):
                store.events(report['run_id'], 1)
        self.assertEqual(len(store.events(report['run_id'], 1)['events']), 1)

    def test_packaged_legacy_analyst_projection_matches_sqlite(self):
        request = {'messages': [{'role': 'system', 'content': 'prompt'},
                               {'role': 'user', 'content': json.dumps({'round': 10})}]}
        records = [{'event': 'analyst_request', 'request': request, 'context_sha256': 'a'},
                   {'event': 'analyst_failed', 'context_sha256': 'a', 'raw_response_text': 'bad',
                    'error': 'timed out', 'error_type': 'TimeoutError'},
                   {'event': 'analyst_request', 'request': request, 'context_sha256': 'b'},
                   {'event': 'analyst_response', 'context_sha256': 'b', 'raw_response_text': 'good'},
                   {'event': 'analyst_validated', 'context_sha256': 'b'},
                   {'event': 'analyst_cache', 'round': 11, 'attempt': 1, 'provider_call': False}]
        report, _, _ = self.write(records=records)
        store.enable_published_experiments(self.root)
        summaries = [store.analysis_attempts(report['run_id'], number) for number in (None, 10, 11)]
        store.save(report)
        for record in records:
            store.record(report['run_id'], record)
        for expected, number in zip(summaries, (None, 10, 11)):
            self.assertEqual(store.analysis_attempts(report['run_id'], number), expected)

    def test_unknown_ids_and_invalid_pages_are_rejected_and_exports_are_redacted(self):
        secret = 'sk-fictional-published-key-123456789'
        report, _, _ = self.write(records=[{'event': 'analyst_response', 'round': 1, 'attempt': 1,
                                           'raw_response_text': secret}], report_changes={'error': secret})
        store.enable_published_experiments(self.root)
        with patch.dict('os.environ', {'LLM_API_KEY': secret}):
            for result in (store.list_runs(), store.read(report['run_id']), store.events(report['run_id']),
                           store.export_run(report['run_id']), store.analysis_attempts(report['run_id'], 1)):
                self.assertNotIn(secret, json.dumps(result))
        with self.assertRaisesRegex(ValueError, 'not found'):
            store.read('missing')
        for limit, offset in ((True, 0), (1001, 0), (1, -1)):
            with self.assertRaises(ValueError):
                store.events(report['run_id'], limit, offset)


if __name__ == '__main__':
    unittest.main()

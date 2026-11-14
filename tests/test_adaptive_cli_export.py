import gzip
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backend import adaptive_pricing as pricing, adaptive_store
from scripts.run_adaptive_pricing import export


class AdaptiveCLIExportTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name)
        base=patch.object(adaptive_store,'BASE',self.root/'database')
        base.start();self.addCleanup(base.stop)
        self.run_id='adaptive-cli-stream-test'
        self.report={'run_id':self.run_id,'version':pricing.VERSION,'status':'completed','created_at':1.,
                     'config':{'profile':'flexible_deal_seekers','mode':'synthetic'},
                     'counts':{'provider_calls':0},'population':{'source':'synthetic_test'},
                     'scenario':{'id':'low_fare_55','version':'zero-fare-stress-v1'},'validation':{}}
        adaptive_store.save(self.report)

    def add_events(self,count=205,reason='Synthetic audit content'):
        with adaptive_store.connection() as db:
            db.executemany('INSERT INTO adaptive_events(run_id,recorded_at,record) VALUES (?,?,?)',
                           [(self.run_id,float(i),json.dumps({'event':'test_record','index':i,'reason':reason}))
                            for i in range(count)])

    def assert_no_partial_export(self,output):
        self.assertFalse(output.exists())
        self.assertEqual(list(output.parent.glob(f'.{output.name}.export-*')),[])

    def test_streams_all_pages_above_inline_cap_and_preserves_manifest(self):
        self.add_events()
        output=self.root/'exports'/'complete'
        original_events=pricing.events
        with patch.object(adaptive_store,'MAX_EXPORT_BYTES',1), \
                patch.object(pricing,'events',wraps=original_events) as paged:
            with self.assertRaisesRegex(ValueError,'inline export limit'):
                adaptive_store.export_run(self.run_id)
            result=export(self.run_id,output)
            self.assertEqual([c.kwargs['offset'] for c in paged.call_args_list],[0,100,200,205])
            self.assertTrue(all(c.kwargs['limit']==100 for c in paged.call_args_list))
        self.assertEqual(result['run_id'],self.run_id)
        with gzip.open(output/'audit.jsonl.gz','rt',encoding='utf-8') as stream:
            records=[json.loads(line) for line in stream]
        self.assertEqual([r['record']['index'] for r in records],list(range(205)))
        manifest=json.loads((output/'manifest.json').read_text())
        self.assertEqual(manifest['audit_records'],205)
        self.assertEqual(manifest['counts'],self.report['counts'])
        self.assertEqual(manifest['scenario'],self.report['scenario'])
        self.assertEqual(manifest['evidence_kind'],'completed')
        self.assertNotIn('holdout_frozen_before_validation',manifest)
        for name,info in manifest['files'].items():
            content=(output/name).read_bytes()
            self.assertEqual(info,{'sha256':hashlib.sha256(content).hexdigest(),'bytes':len(content)})
        another=self.root/'exports'/'second'
        export(self.run_id,another)
        self.assertEqual((output/'audit.jsonl.gz').read_bytes(),(another/'audit.jsonl.gz').read_bytes())
        self.assertEqual(list(output.parent.glob('.complete.export-*')),[])

    def test_redacts_report_and_each_page_before_writing(self):
        secret='DUMMY-PRIVATE-TOKEN-NOT-A-REAL-KEY'
        self.report['description']=f'Provider echoed {secret}'
        adaptive_store.save(self.report)
        self.add_events(101,reason=f'Provider echoed {secret}')
        output=self.root/'redacted'
        with patch.dict(os.environ,{'LLM_API_KEY':secret}):
            export(self.run_id,output)
        report=(output/'report.json').read_text()
        with gzip.open(output/'audit.jsonl.gz','rt',encoding='utf-8') as stream:audit=stream.read()
        self.assertNotIn(secret,report+audit)
        self.assertIn('[REDACTED]',report)
        self.assertEqual(audit.count('[REDACTED]'),101)

    def test_rejects_unknown_credential_in_later_page_and_cleans_temporary(self):
        self.add_events(100)
        self.add_events(1,reason='sk-'+('Z'*24))
        output=self.root/'blocked'
        with self.assertRaisesRegex(ValueError,'Potential credential'):
            export(self.run_id,output)
        self.assert_no_partial_export(output)

    def test_page_failure_cleans_temporary_and_does_not_publish(self):
        self.add_events()
        original=pricing.events
        def failing_page(run_id,limit,offset):
            if offset>=100:raise OSError('Simulated page-read failure')
            return original(run_id,limit,offset)
        output=self.root/'failed'
        with patch.object(pricing,'events',side_effect=failing_page),self.assertRaisesRegex(OSError,'page-read'):
            export(self.run_id,output)
        self.assert_no_partial_export(output)

    def test_incomplete_and_existing_exports_are_never_overwritten(self):
        output=self.root/'existing';output.mkdir()
        marker=output/'manifest.json';marker.write_text('historical evidence')
        with self.assertRaisesRegex(ValueError,'overwrite'):
            export(self.run_id,output)
        self.assertEqual(marker.read_text(),'historical evidence')
        self.report['status']='failed';adaptive_store.save(self.report)
        incomplete=self.root/'incomplete'
        with self.assertRaisesRegex(ValueError,'Only completed'):
            export(self.run_id,incomplete)
        self.assert_no_partial_export(incomplete)

    def test_destination_created_during_streaming_is_preserved(self):
        self.add_events(1)
        output=self.root/'competing'
        original=pricing.events
        def creates_destination(run_id,limit,offset):
            if offset==0:
                output.mkdir();(output/'keep.txt').write_text('Do not replace')
            return original(run_id,limit,offset)
        with patch.object(pricing,'events',side_effect=creates_destination),self.assertRaisesRegex(ValueError,'overwrite'):
            export(self.run_id,output)
        self.assertEqual((output/'keep.txt').read_text(),'Do not replace')
        self.assertEqual(list(output.parent.glob('.competing.export-*')),[])

    def test_failed_and_interrupted_exports_require_opt_in_and_preserve_missing_results(self):
        for status in ('failed','interrupted'):
            with self.subTest(status=status):
                self.report.update(status=status,error='Audited execution stopped',validation=None)
                adaptive_store.save(self.report)
                output=self.root/status
                with self.assertRaisesRegex(ValueError,'Only completed'):
                    export(self.run_id,output)
                result=export(self.run_id,output,include_failed=True)
                saved=json.loads((output/'report.json').read_text())
                manifest=json.loads((output/'manifest.json').read_text())
                self.assertEqual(saved['status'],status)
                self.assertIsNone(saved['validation'])
                self.assertEqual(result['status'],status)
                self.assertEqual(manifest['evidence_kind'],'execution_failure')
                self.assertNotIn('holdout_frozen_before_validation',manifest)

    def test_include_failed_does_not_export_or_resume_active_runs(self):
        for status in ('queued','running'):
            with self.subTest(status=status):
                self.report['status']=status
                with patch.object(pricing,'read',return_value=self.report), \
                        patch.object(pricing,'start') as start, \
                        self.assertRaisesRegex(ValueError,'Only completed'):
                    export(self.run_id,self.root/status,include_failed=True)
                start.assert_not_called()
                self.assert_no_partial_export(self.root/status)


if __name__=='__main__':unittest.main()

"""Joint policy search, durable bounded replay, and frozen holdout contracts."""
import copy
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from backend import optimization as engine, optimization_store as store


class OptimizationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path_patch = patch.object(store, 'BASE', Path(self.tmp.name))
        self.path_patch.start()

    def tearDown(self):
        deadline = time.monotonic() + 30
        while engine._active and time.monotonic() < deadline:
            time.sleep(.05)
        self.path_patch.stop()
        self.tmp.cleanup()

    def finish(self, run_id):
        deadline = time.monotonic() + 60
        while run_id in engine._active and time.monotonic() < deadline:
            time.sleep(.05)
        self.assertNotIn(run_id, engine._active)
        return engine.read(run_id)

    def test_bounds_rejected_before_start(self):
        for body in ({'rounds':True}, {'rounds':0}, {'mode':'fake'}, {'fare_max':float('nan')},
                     {'initial_membership_fee':5001}, {'fare_min':90,'initial_member_fare':70},
                     {'max_calls':121}, {'fee_min':399,'fee_max':399}):
            with self.subTest(body=body), self.assertRaises(ValueError):
                engine.start(body)
        self.assertFalse((store.BASE/'experiments.sqlite3').exists())

    def test_feedback_search_moves_both_prices_and_uses_outcomes(self):
        config = engine.validate({'fare_max':200, 'fee_max':800})
        rows = []
        for number in range(10):
            prices = engine.propose(config, rows)
            score = -(prices['member_fare']-40)**2 - (prices['membership_fee']-200)**2/4
            rows.append({**prices, 'feasible':True, 'incremental_contribution':score})
        self.assertGreater(len({r['member_fare'] for r in rows}), 2)
        self.assertGreater(len({r['membership_fee'] for r in rows}), 2)
        self.assertGreater(engine.best_candidate(rows)['incremental_contribution'], rows[0]['incremental_contribution'])
        self.assertTrue(all(0 <= r['member_fare'] <= 200 and 0 <= r['membership_fee'] <= 800 for r in rows))
        self.assertEqual(len({(r['member_fare'],r['membership_fee']) for r in rows}),len(rows))
        bad = copy.deepcopy(rows)
        bad[0]['incremental_contribution'] = 1e9
        self.assertNotEqual(engine.propose(config, rows),engine.propose(config,bad))

    def test_real_math_run_is_durable_paired_and_holdout_profile_frozen(self):
        started = engine.start({'legacy_market':True, 'rounds':3, 'customers':2, 'seed':20261802})
        report = self.finish(started['run_id'])
        self.assertEqual(report['status'],'completed',report['error'])
        track = report['tracks'][0]
        self.assertEqual(len(track['rounds']),3)
        self.assertEqual([r['seat_calibration']['generation'] for r in track['rounds']],[0,1,2])
        self.assertEqual(track['validation']['seat_calibration'],track['best']['seat_calibration'])
        self.assertTrue(set(report['search_seeds']).isdisjoint(report['validation_seeds']))
        self.assertEqual(report['counts']['provider_calls'],0)
        self.assertTrue(track['validation']['checks_passed'])
        self.assertEqual(report['progress']['completed_worlds'],report['progress']['total_worlds'])
        exported = engine.export_run(started['run_id'])
        for world in exported['worlds']:
            self.assertTrue(all(world['result']['checks'].values()))
        self.assertTrue(engine.events(started['run_id'],limit=1)['total']>1)
        self.assertEqual(len(engine.events(started['run_id'],limit=1)['events']),1)
        self.assertEqual(engine.read(started['run_id'])['tracks'],report['tracks'])
        with self.assertRaises(ValueError):engine.resume(started['run_id'])

    def test_live_pause_resume_records_original_output_and_does_not_double_charge(self):
        from backend.probabilistic_customer import choose as probability
        from llm_agent.market_adapter import legal_choices
        def fake_provider(observation, mode, audit, **kwargs):
            # No HTTP is used. A synthetic provider emulates the actual adapter contract.
            choices = legal_choices(observation)
            forced = len(choices)==1
            decision = probability(observation)['decision']
            record={'event':'market_choice','source':'environment_forced' if forced else 'provider_live',
                    'provider_call':not forced,'cache_hit':False,'decision':decision,
                    'raw_response_text':json.dumps({'choices':[{'message':{'content':json.dumps(decision)}}]})}
            audit.append(record)
            return {'decision':decision,'source':record['source'],'provider_call':not forced,'cache_hit':False,'forced':forced}
        with patch.dict(os.environ,{'LLM_API_URL':'https://example.invalid/chat','LLM_API_KEY':'test-secret-only','LLM_MODEL':'fake-test'}), \
             patch('llm_agent.market_adapter.choose',side_effect=fake_provider):
            started=engine.start({'legacy_market':True, 'mode':'live','rounds':1,'customers':1,'max_calls':0,'seed':20261812})
            first=self.finish(started['run_id'])
            self.assertEqual(first['status'],'paused')
            self.assertEqual(first['counts']['provider_calls'],0)
            engine.resume(started['run_id'],{'max_calls':2})
            second=self.finish(started['run_id'])
            self.assertEqual(second['status'],'paused')
            self.assertEqual(second['counts']['provider_calls'],2)
            for _ in range(3):
                engine.resume(started['run_id'],{'max_calls':120})
                final=self.finish(started['run_id'])
                if final['status']=='completed':break
            self.assertEqual(final['status'],'completed',final.get('error'))
            self.assertEqual(final['counts']['live_attempts'],final['counts']['provider_calls'])
            records=engine.events(started['run_id'],500)['events']
            self.assertTrue(any('raw_response_text' in r['record'] for r in records))
            for world in engine.export_run(started['run_id'])['worlds']:
                self.assertTrue(world['result']['checks']['membership_charged_once'])
            transitions=[r for r in records if r['record']['event']=='optimization_transition']
            self.assertEqual(len(transitions),len({(r['world_id'],r['record']['transition']['packet_id']) for r in transitions}))

    def test_provider_failure_has_no_mathematical_fallback(self):
        def failed(observation, mode, audit, **kwargs):
            audit.append({'event':'market_choice_failed','source':'provider_live','provider_call':True,
                          'cache_hit':False,'raw_response_text':'invalid output'})
            raise ValueError('Provider rejected; no fallback')
        with patch.dict(os.environ,{'LLM_API_URL':'https://example.invalid/chat','LLM_API_KEY':'test-key','LLM_MODEL':'fake-test'}), \
             patch('llm_agent.market_adapter.choose',side_effect=failed):
            started=engine.start({'legacy_market':True, 'mode':'live','rounds':1,'customers':1,'max_calls':1})
            result=self.finish(started['run_id'])
        self.assertEqual(result['status'],'failed')
        self.assertEqual(result['counts']['provider_calls'],1)
        self.assertEqual(result['counts']['failures'],1)
        self.assertEqual(result['counts']['math_choices'],0)
        self.assertEqual(result['tracks'][0]['decision'],'PENDING')

    def test_provenance_change_refuses_resume(self):
        with patch.dict(os.environ,{'LLM_API_URL':'https://example.invalid/chat','LLM_API_KEY':'test-key','LLM_MODEL':'fake-test'}):
            started=engine.start({'legacy_market':True, 'mode':'live','rounds':1,'customers':1,'max_calls':0})
            self.finish(started['run_id'])
            with patch.object(engine,'provenance',return_value={'version':'modified'}):
                engine.resume(started['run_id'],{'max_calls':0})
                result=self.finish(started['run_id'])
        self.assertEqual(result['status'],'failed')
        self.assertIn('changed',result['error'])

    def test_no_offer_when_holdout_or_service_fails(self):
        cfg=engine.validate({})
        row={'seed':1,'exogenous_sha256':'same','contribution':100,'service_rate':.1,
             'new_members':2,'member_flown':1,'normal_seats_flown':2,'checks':{'cash':True}}
        base={**row,'contribution':0}
        result=engine.aggregate({'member_fare':70,'membership_fee':399},[row],[base],cfg)
        self.assertFalse(result['feasible'])
        self.assertEqual(result['incremental_contribution'],100)
        with self.assertRaises(ValueError):
            engine.aggregate({},[row],[{**base,'exogenous_sha256':'different'}],cfg)


if __name__=='__main__':unittest.main()

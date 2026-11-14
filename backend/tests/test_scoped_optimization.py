import copy
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from backend import data, optimization as engine, optimization_store as store
from backend.initial_policy import suggest


class ScopedOptimizationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path_patch = patch.object(store,'BASE',Path(self.tmp.name)); self.path_patch.start()

    def tearDown(self):
        while engine._active: time.sleep(.01)
        self.path_patch.stop(); self.tmp.cleanup()

    def finish(self, run):
        deadline=time.monotonic()+60
        while run in engine._active and time.monotonic()<deadline: time.sleep(.01)
        self.assertNotIn(run,engine._active)
        return engine.read(run)

    def test_missing_flight_rejected_and_snapshot_price_is_not_editable(self):
        with self.assertRaisesRegex(ValueError,'Select a flight'):engine.start({'mode':'math'})
        first=suggest({'flight_id':'NET-HKG-FUK-20270515','forecast_day':28})
        second=suggest({'flight_id':'NET-HKG-FUK-20270518','forecast_day':28})
        self.assertNotEqual(first['scope']['history_sha256'],second['scope']['history_sha256'])
        cfg=engine.validate({'flight_id':'NET-HKG-FUK-20270515','initial_member_fare':1999})
        self.assertEqual(cfg['initial_member_fare'],first['initial_member_fare'])
        self.assertEqual(cfg['scope']['initial_fare_source'],'snapshot.member_initial_base_fare')
        self.assertEqual(len(cfg['scope']['history']),153)
        self.assertEqual(cfg['scope']['departure_time'],'08:00')

    def test_single_selected_flight_fixed_fee_and_attributed_profit(self):
        run=engine.start({'flight_id':'NET-FUK-HKG-20270515','forecast_day':14,'rounds':3,
                          'customers':4,'initial_membership_fee':49,'program_cost':0})['run_id']
        report=self.finish(run)
        self.assertEqual(report['status'],'completed',report['error'])
        scope=report['config']['scope']
        self.assertEqual(report['config']['flights'],1)
        self.assertEqual(scope['departure_time'],'09:00')
        for world in engine.export_run(run)['worlds']:
            stored = store.world(world['world_id'])
            self.assertEqual(stored['state']['flights'][scope['flight_id']]['departure_time'],'09:00')
        self.assertEqual({r['membership_fee'] for r in report['tracks'][0]['rounds']},{49})
        for world in engine.export_run(run)['worlds']:
            result=world['result']
            self.assertEqual([f['flight_id'] for f in result['flights']],[scope['flight_id']])
            self.assertEqual(result['flights'][0]['legacy_seats'],scope['booked_seats'])
            self.assertEqual(result['annual_fee_allocation'],1/3)
            self.assertAlmostEqual(result['contribution'],result['attributed_revenue']-result['attributed_cost'],places=1)
            self.assertTrue(all(result['checks'].values()))
            self.assertTrue(all(q['days_to_departure']<=14 for q in result['flights'][0]['quota_history']))
        for row in report['tracks'][0]['rounds']:
            self.assertEqual(row['contribution'],row['total_contribution'])
            self.assertGreaterEqual(row['mean_buyers'],0)

    def test_auto_batches_remain_inside_total_cap_then_explicit_extension(self):
        from backend.probabilistic_customer import choose as probability
        from llm_agent.market_adapter import legal_choices
        def fake(observation,mode,audit,**kwargs):
            forced=len(legal_choices(observation))==1
            decision=probability(observation)['decision']
            record={'event':'market_choice','source':'environment_forced' if forced else 'provider_live',
                    'provider_call':not forced,'cache_hit':False,'decision':decision,'raw_response_text':json.dumps(decision)}
            audit.append(record)
            return {**record,'forced':forced}
        with patch.dict(os.environ,{'LLM_API_URL':'https://example.invalid','LLM_API_KEY':'fake','LLM_MODEL':'test'}),patch('llm_agent.market_adapter.choose',side_effect=fake):
            run=engine.start({'flight_id':'NET-HKG-FUK-20270515','mode':'live','rounds':1,'customers':1,
                              'max_calls':2,'total_live_budget':5})['run_id']
            report=self.finish(run)
            self.assertEqual(report['status'],'paused',report['error'])
            self.assertEqual(report['counts']['live_attempts'],5)
            self.assertGreaterEqual(report['progress']['automatic_batches'],2)
            with self.assertRaisesRegex(ValueError,'additional_live_budget'):engine.resume(run,{'max_calls':2})
            with self.assertRaisesRegex(ValueError,'at least 1'):engine.resume(run,{'max_calls':0,'additional_live_budget':200})
            self.assertEqual(store.run(run)['config']['total_live_budget'],5)
            with patch.object(engine,'_active',{run}):
                with self.assertRaisesRegex(ValueError,'already running'):engine.resume(run,{'max_calls':2,'additional_live_budget':200})
            self.assertEqual(store.run(run)['config']['total_live_budget'],5)
            engine.resume(run,{'max_calls':2,'additional_live_budget':200})
            report=self.finish(run)
            self.assertEqual(report['status'],'completed',report['error'])
            self.assertLessEqual(report['counts']['live_attempts'],205)
            records=engine.events(run,500)['events']
            self.assertTrue(any(r['record']['event']=='optimization_automatic_batch' for r in records))
            self.assertTrue(any('raw_response_text' in r['record'] for r in records))

    def test_sold_out_scope_uses_latest_past_quote_never_future(self):
        original=data.history('SYN-00001')
        rows=copy.deepcopy(original)
        for row in rows:
            if row['days_to_departure']==14:row['normal_base_fare']=None
            if row['days_to_departure']<14:row['normal_base_fare']=999999
        with patch('backend.initial_policy.data.history',return_value=rows):
            scope=suggest({'flight_id':'SYN-00001','forecast_day':14})['scope']
        self.assertGreater(scope['quote_age_days'],0)
        self.assertLess(scope['normal_base_fare'],999999)
        self.assertTrue(scope['departure_date'])

    def test_purchase_counts_include_later_cancelled_agent_bookings_only(self):
        from backend.scoped_market import attribute_result
        ledger={'membership_revenue':300,'membership_service_cost':30,
                'revenue_excluding_mandatory_fees':800,'total_cost':200}
        result={'ledger':ledger,'contribution':600,'assumptions':[]}
        state={'config':{'flight_scope':{'flight_id':'test'}},'bookings':{
            'cancelled':{'customer_id':'A','party_size':3,'status':'cancelled'},
            'replacement':{'customer_id':'A','party_size':2,'status':'flown'},
            'second_household':{'customer_id':'B','party_size':1,'status':'cancelled'},
            'background':{'customer_id':None,'party_size':1,'status':'flown'}}}
        attributed=attribute_result(result,state)
        self.assertEqual(attributed['buyers'],2)
        self.assertEqual(attributed['tickets'],6)
        self.assertEqual(attributed['fulfilled_buyers'],1)
        self.assertEqual(attributed['fulfilled_tickets'],2)
        self.assertEqual(attributed['contribution'],420)


if __name__=='__main__':unittest.main()

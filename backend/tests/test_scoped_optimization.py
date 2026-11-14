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
        self.assertEqual(cfg['scope']['initial_fare_source'],'snapshot.normal_base_fare_x_member_cap')
        self.assertAlmostEqual(cfg['initial_member_fare'], cfg['scope']['normal_base_fare']*.8, places=2)
        self.assertEqual(cfg['fare_max'], cfg['scope']['member_fare_cap'])
        self.assertEqual(len(cfg['scope']['history']),153)
        self.assertEqual(cfg['scope']['departure_time'],'08:00')

    def test_single_selected_flight_fixed_fee_and_attributed_profit(self):
        run=engine.start({'flight_id':'NET-ICN-HKG-20270521','forecast_day':14,'rounds':3,
                          'customers':4,'initial_membership_fee':49,'program_cost':0})['run_id']
        report=self.finish(run)
        self.assertEqual(report['status'],'completed',report['error'])
        scope=report['config']['scope']
        self.assertEqual(report['config']['flights'],1)
        self.assertFalse(report['economic_scope']['membership_term_evaluated'])
        self.assertIsNone(report['economic_scope']['future_member_trip_contribution'])
        self.assertIsNone(report['economic_scope']['future_renewal_contribution'])
        self.assertEqual(scope['departure_time'],'09:00')
        for world in engine.export_run(run)['worlds']:
            stored = store.world(world['world_id'])
            self.assertEqual(stored['state']['flights'][scope['flight_id']]['departure_time'],'09:00')
        self.assertEqual({r['membership_fee'] for r in report['tracks'][0]['rounds']},{49})
        self.assertTrue(all(r['member_fare']<=scope['normal_base_fare']*.8 for r in report['tracks'][0]['rounds']))
        self.assertTrue(all(r['seat_calibration']['generation']==0 for r in report['tracks'][0]['rounds']))
        self.assertTrue(all(r['next_seat_calibration']['generation']==1 for r in report['tracks'][0]['rounds']))
        self.assertEqual(report['tracks'][0]['seat_feedback_application'],'proposed_only_fixed_during_price_comparison')
        for world in engine.export_run(run)['worlds']:
            result=world['result']
            self.assertEqual([f['flight_id'] for f in result['flights']],[scope['flight_id']])
            self.assertEqual(result['flights'][0]['legacy_seats'],scope['booked_seats'])
            self.assertEqual(result['annual_fee_allocation'],1/3)
            self.assertAlmostEqual(result['contribution'],result['attributed_revenue']-result['attributed_cost'],places=1)
            self.assertTrue(all(result['checks'].values()))
            self.assertTrue(result['profit_attribution_reconciled'])
            self.assertEqual(result['member_tickets']+result['regular_tickets'],result['tickets'])
            self.assertTrue(all(q['days_to_departure']<=14 for q in result['flights'][0]['quota_history']))
        for row in report['tracks'][0]['rounds']:
            self.assertEqual(row['contribution'],row['total_contribution'])
            self.assertGreaterEqual(row['mean_buyers'],0)

    def test_original_fare_ignores_legacy_discount_and_uses_only_past_quote(self):
        flight_id = 'DEMO-HKG-TPE-20270515'
        rows = copy.deepcopy(data.history(flight_id))
        for row in rows:
            row['member_initial_base_fare'] = 1
            if row['days_to_departure'] == 15:
                row['normal_base_fare'] = 740
            elif row['days_to_departure'] == 14:
                row['normal_base_fare'] = None
            elif row['days_to_departure'] < 14:
                row['normal_base_fare'] = 1999
        with patch('backend.initial_policy.data.history', return_value=rows):
            scope = suggest({'flight_id': flight_id, 'forecast_day': 14})['scope']
        self.assertEqual(scope['initial_member_fare'], 592)
        self.assertEqual(scope['member_fare_cap'], 592)
        self.assertEqual(scope['quote_age_days'], 1)
        self.assertEqual(scope['initial_fare_source'], 'snapshot.normal_base_fare_x_member_cap')

    def test_member_fare_search_is_capped_at_eighty_percent_the_normal_fare(self):
        body = {'flight_id':'DEMO-HKG-TPE-20270515','forecast_day':28}
        config = engine.validate(body)
        self.assertEqual(config['scope']['normal_base_fare'], 830)
        self.assertEqual(config['initial_member_fare'], 664)
        self.assertEqual(config['fare_max'], 664)
        # A wider requested bound is narrowed to the cap, never honoured above it.
        self.assertEqual(engine.validate({**body, 'fare_max':2000})['fare_max'], 664)
        with self.assertRaisesRegex(ValueError, 'fare bounds'):
            engine.validate({**body, 'fare_max':300})
        rows = []
        for _ in range(12):
            proposal = engine.propose(config, rows)
            if proposal is None:break
            self.assertLessEqual(proposal['member_fare'], 664)
            rows.append({**proposal, 'feasible':True, 'incremental_contribution':0, 'total_contribution':0})

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
            run=engine.start({'flight_id':'NET-HKG-ICN-20270521','mode':'live','rounds':1,'customers':1,
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

    def test_zero_current_supply_blocks_start_before_provider_or_run_creation(self):
        suggested=suggest({'flight_id':'SYN-00004','forecast_day':28})
        self.assertFalse(suggested['scope']['optimization_eligible'])
        self.assertEqual(suggested['scope']['member_supply_exposure'],0)
        with patch('llm_agent.market_adapter.choose') as provider:
            with self.assertRaisesRegex(ValueError,'No releasable member seats at the selected round'):
                engine.start({'flight_id':'SYN-00004','forecast_day':28,'mode':'live'})
        provider.assert_not_called()
        self.assertFalse((store.BASE/'experiments.sqlite3').exists())

    def test_scoped_local_price_probes_and_later_explicit_boundary(self):
        cfg=engine.validate({'flight_id':'NET-HKG-ICN-20270521'})
        cfg['initial_member_fare']=74
        rows=[]
        for _ in range(5):
            p=engine.propose(cfg,rows)
            rows.append({**p,'feasible':True,'incremental_contribution':-(p['member_fare']-74)**2})
        self.assertEqual([r['member_fare'] for r in rows[:3]],[74,56,92])
        self.assertEqual(rows[3]['member_fare'],0)
        self.assertEqual(rows[3]['search_step'],'boundary_low')
        self.assertGreater(rows[4]['member_fare'],92)
        self.assertEqual(len({r['member_fare'] for r in rows}),5)

    def test_zero_supply_cancellation_difference_is_not_price_evidence(self):
        cfg=engine.validate({'flight_id':'NET-HKG-ICN-20270521'})
        baseline={'seed':117,'exogenous_sha256':'paired','contribution':26680,
                  'service_rate':0,'new_members':0,'member_flown':0,'normal_seats_flown':52,
                  'checks':{'cash':True},'member_supply_exposure':0,'member_tickets':0,
                  'ledger':{'cancellation_revenue':600,'passenger_cost':6240},
                  'profit_components':{'cancellation_revenue':600,'passenger_cost':6240}}
        actual={**baseline,'contribution':26460,'normal_seats_flown':53,
                'ledger':{'cancellation_revenue':500,'passenger_cost':6360},
                'profit_components':{'cancellation_revenue':500,'passenger_cost':6360}}
        row=engine.aggregate({'member_fare':0,'membership_fee':399},[actual],[baseline],cfg)
        self.assertEqual(row['price_evidence_status'],'uninformative_no_supply')
        self.assertFalse(row['price_evidence_qualified'])
        self.assertIsNone(engine.best_candidate([row]))
        self.assertEqual(row['paired_component_deltas']['cancellation_revenue'],-100)
        self.assertEqual(row['paired_component_deltas']['passenger_cost'],120)
        supplied={**actual,'member_supply_exposure':10,'member_offer_observations':1}
        row=engine.aggregate({'member_fare':0,'membership_fee':399},[supplied],[baseline],cfg)
        self.assertEqual(row['price_evidence_status'],'no_member_sales')
        unexposed={**actual,'member_supply_exposure':10,'member_offer_observations':0}
        row=engine.aggregate({'member_fare':0,'membership_fee':399},[unexposed],[baseline],cfg)
        self.assertEqual(row['price_evidence_status'],'uninformative_no_member_exposure')
        self.assertIsNone(engine.best_candidate([row]))

    def test_member_regular_buyers_overlap_and_cancelled_purchase_stays_counted(self):
        from backend.scoped_market import attribute_result
        result={'ledger':{'membership_revenue':0,'membership_service_cost':0,
                         'revenue_excluding_mandatory_fees':0,'total_cost':0},'contribution':0,'assumptions':[]}
        state={'config':{'flight_scope':{'flight_id':'test'}},'bookings':{
            'member_party':{'customer_id':'A','party_size':3,'member_seats':1,'normal_seats':2,'status':'cancelled'},
            'replacement':{'customer_id':'A','party_size':1,'member_seats':0,'normal_seats':1,'status':'flown'},
            'regular':{'customer_id':'B','party_size':1,'member_seats':0,'normal_seats':1,'status':'flown'},
            'background':{'customer_id':None,'party_size':1,'member_seats':0,'normal_seats':1,'status':'flown'}}}
        r=attribute_result(result,state)
        self.assertEqual((r['buyers'],r['member_buyers'],r['regular_buyers']),(2,1,2))
        self.assertEqual((r['member_tickets'],r['regular_tickets'],r['tickets']),(1,4,5))
        self.assertEqual((r['cancelled_bookings'],r['fulfilled_bookings']),(1,2))

    def test_all_uninformative_completed_worlds_have_no_retained_best_or_holdout(self):
        def no_supply(run_id,mode,phase,round_number,seed,prices,enabled,budget):
            return {'seed':seed,'exogenous_sha256':str(seed),'contribution':0,
                    'service_rate':0,'new_members':0,'member_flown':0,'normal_seats_flown':0,
                    'checks':{'cash':True},'member_supply_exposure':0,
                    'member_offer_observations':0,'member_tickets':0,'seat_feedback_samples':[]}
        with patch.object(engine,'_world',side_effect=no_supply) as worlds:
            run=engine.start({'flight_id':'NET-HKG-ICN-20270521','mode':'math','rounds':4})['run_id']
            report=self.finish(run)
        self.assertEqual(report['status'],'completed',report['error'])
        track=report['tracks'][0]
        self.assertEqual(len(track['rounds']),1)
        self.assertFalse(track['rounds'][0]['accepted'])
        self.assertIsNone(track['rounds'][0]['incumbent'])
        self.assertIsNone(track['best'])
        self.assertIsNone(track['validation'])
        self.assertEqual(track['decision'],'NO_OFFER')
        self.assertFalse(any(c.args[2].startswith('holdout') for c in worlds.call_args_list))

    def test_cancellation_ledger_decomposes_agent_background_and_actual_cost(self):
        from backend.scoped_market import create_scoped_market, attribute_result
        from backend.shared_market import _buy, _cancel, _automatic, summarize
        scope=suggest({'flight_id':'NET-HKG-ICN-20270521'})['scope']
        state=create_scoped_market(scope,{'customer_count':1,'program_cost':0},117,{'enabled':False})
        cid=next(iter(state['customers']))
        customer=state['customers'][cid]
        customer['budget_cents']=customer['initial_budget_cents']=1000000
        oid=customer['occasions'][0]['occasion_id']; fid=scope['flight_id']
        _buy(state,fid,'normal',cid,oid,1,0,False,490)
        _buy(state,fid,'background',None,None,1,0,False,340)
        cancelled=copy.deepcopy(state)
        _cancel(cancelled,'normal')
        for candidate in (state,cancelled):
            _automatic(candidate,{'kind':'departure','flight_id':fid})
        kept=attribute_result(summarize(state),state)
        dropped=attribute_result(summarize(cancelled),cancelled)
        self.assertEqual(kept['buyers'],dropped['buyers'])
        self.assertEqual(kept['contribution']-dropped['contribution'],-220)
        self.assertEqual(kept['profit_components']['normal_base_revenue'],830)
        self.assertEqual(dropped['profit_components']['normal_base_revenue'],830)
        self.assertEqual(dropped['profit_attribution']['agent']['cancellation_revenue'],100)
        self.assertEqual(kept['profit_attribution']['agent']['passenger_cost'],120)
        self.assertEqual(kept['profit_attribution']['background']['normal_base_revenue'],340)
        self.assertTrue(kept['profit_attribution_reconciled'])
        self.assertTrue(dropped['profit_attribution_reconciled'])


if __name__=='__main__':unittest.main()

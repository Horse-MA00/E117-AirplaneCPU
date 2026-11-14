import copy
import json
import unittest
from unittest.mock import patch
import numpy as np
from backend import nhpp_v3 as model
from backend.tests.test_models import history
from simulation.evaluate_nhpp_v3 import revenue, score_guard, select_guard


class SmoothForecastTests(unittest.TestCase):
    def test_asof_isolation_and_determinism(self):
        rows=history()
        result=model.forecast(rows,28,protection_allowance=0)
        for r in rows:
            if r['days_to_departure']<28:r.update(gross_bookings=999,booked_seats=599)
        self.assertEqual(result,model.forecast(rows,28,protection_allowance=0))
        json.dumps(result,allow_nan=False)

    def test_soft_weight_grows_with_evidence_and_sample_size(self):
        def items(n):return [{'count':n,'censored':False,'start':-k-1,'end':-k} for k in range(7)]
        low={'days_ago':7,'log_lr':5.001}
        high={'days_ago':7,'log_lr':25}
        self.assertLess(model._recent_weight(items(2),low),.001)
        self.assertLess(model._recent_weight(items(2),high),model._recent_weight(items(20),high))
        self.assertLess(model._recent_weight(items(20),high),.8)
        self.assertEqual(model._recent_weight(items(20),None),0)

    def test_full_history_retained_after_jump(self):
        rows=history();booked=0
        for r in rows:
            r['gross_bookings']=7 if 28<=r['days_to_departure']<35 else 1
            booked+=r['gross_bookings'];r['booked_seats']=booked
        p=model.forecast(rows,28,protection_allowance=0)
        d=p['diagnostics']
        self.assertIsNotNone(d['change_point'])
        self.assertEqual(d['full_window_intervals'],36)
        self.assertGreater(d['recent_component_weight'],0)
        self.assertGreater(d['full_window_weight'],.2)
        altered=copy.deepcopy(rows)
        # Same recent observations; a different older window still affects v3.
        for r in altered:
            if 40<=r['days_to_departure']<=60:r['gross_bookings']=2
        other=model.forecast(altered,28,protection_allowance=0)
        self.assertNotEqual(p['expected_remaining_demand'],other['expected_remaining_demand'])

    def test_ensemble_preserves_components_not_just_mean(self):
        full=(np.ones(800),np.ones(800)*10,100.)
        recent=(np.ones(800)*2,np.ones(800)*20,80.)
        with patch.object(model,'_sample',side_effect=[full,recent]),patch.object(model,'_recent_weight',return_value=.5):
            beta,rate,ess,weight=model._smooth_sample([],{'days_ago':7},np.random.default_rng(117))
        self.assertEqual(set(rate),{10.,20.})
        self.assertTrue(np.all(rate==10*beta))
        self.assertEqual(ess,80)

    def test_calibration_never_changes_distribution(self):
        a=model.forecast(history(),28,protection_allowance=0)
        b=model.forecast(history(),28,protection_allowance=20)
        self.assertEqual(a['forecast_curve'],b['forecast_curve'])
        self.assertEqual(a['demand_p90'],b['demand_p90'])
        self.assertEqual(b['protection_p90'],a['raw_protection_p90']+20)
        self.assertLessEqual(b['releasable_seats'],a['releasable_seats'])

    def test_missing_and_stale_calibration_fail_closed(self):
        with patch.object(model.Path,'exists',return_value=False):
            with self.assertRaisesRegex(ValueError,'missing'):model._allowance(28,None,20)
        with patch.object(model.Path,'exists',return_value=True),patch.object(model.Path,'read_text',return_value='{}'):
            with self.assertRaisesRegex(ValueError,'stale'):model._allowance(28,None,20)

    def test_negative_trend_and_cutoff(self):
        p=model.forecast(history(True),28,protection_allowance=0)
        self.assertTrue(p['beta']<0 or p['diagnostics']['change_point']['direction']=='down')
        self.assertTrue(0<=p['expected_empty_seats']<=p['capacity'])
        self.assertEqual(model.forecast(history(),0)['releasable_seats'],0)


class RevenueGuardTests(unittest.TestCase):
    def row(self):
        return {'raw_protection':5,'available':10,'quality_gate':True,'actual_demand':8,
                'future_requests_scoring_only':[(3,100),(5,200)],'scenario_for_scoring':'low',
                'raw_covered':False,'predicted_demand':5}

    def test_chronological_base_fare_revenue(self):
        self.assertEqual(revenue([(3,100),(5,200)],5),700)
        r=score_guard(self.row(),0)
        self.assertEqual(r['normal_base_revenue_baseline'],1300)
        self.assertEqual(r['normal_base_revenue_loss'],600)
        self.assertEqual(score_guard(self.row(),.5)['normal_base_revenue_loss'],0)

    def test_guard_selected_only_when_both_constraints_met(self):
        rows=[self.row() for _ in range(20)]
        guard=select_guard(rows)
        self.assertAlmostEqual(guard,.25) # ceil(.25*10)=3; retain 8 normal seats.
        self.assertTrue(all(score_guard(r,guard)['covered'] for r in rows))
        self.assertEqual(score_guard(rows[0],guard)['normal_base_revenue_loss'],0)

    def test_quality_gate_cannot_be_reopened(self):
        r=self.row();r['quality_gate']=False
        self.assertEqual(score_guard(r,0)['release'],0)


class ActiveForecastTests(unittest.TestCase):
    def test_git_newlines_preserve_evidence_but_content_changes_fail(self):
        import hashlib
        from backend.forecast import _calibration_digest_matches
        raw=b'{\r\n  "guard": 1.6\r\n}\r\n'
        digest=hashlib.sha256(raw).hexdigest()
        self.assertTrue(_calibration_digest_matches(digest,raw.replace(b'\r\n',b'\n')))
        self.assertFalse(_calibration_digest_matches(digest,raw.replace(b'1.6',b'0.1')))

    def test_accepted_horizons_and_rejected_horizon_fallback(self):
        from backend.forecast import forecast, _configuration
        from backend.nhpp import forecast as incumbent
        self.assertEqual(_configuration()['accepted_horizons'],[7,14])
        old=incumbent(history(),28)
        active=forecast(history(),28)
        self.assertEqual(active['forecast_curve'],old['forecast_curve'])
        self.assertLessEqual(active['releasable_seats'],old['releasable_seats'])
        self.assertEqual(active['protection_policy'],'nhpp-v2-robust-guard-v1')
        for day in (7,14):
            p=forecast(history(),day)
            raw=model.forecast(history(),day,protection_allowance=0)
            self.assertEqual(p['forecast_curve'],raw['forecast_curve'])
            self.assertEqual(p['model'],model.VERSION)
            self.assertGreater(p['protection_p90'],raw['raw_protection_p90'])
            self.assertLessEqual(p['releasable_seats'],raw['releasable_seats'])
            self.assertEqual(p['protection_curve'][0]['protection_seats'],p['protection_p90'])

    def test_missing_evidence_does_not_enable_uncalibrated_release(self):
        from backend.forecast import forecast
        with patch('backend.forecast._configuration',side_effect=ValueError('unavailable')):
            with self.assertRaisesRegex(ValueError,'unavailable'):forecast(history(),14)


if __name__=='__main__':unittest.main()

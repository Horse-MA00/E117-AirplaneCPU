import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backend import contribution_explanation, optimization, optimization_store

ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / 'llm_agent/experiments/member_supply_live_context_20261114/report.json'


class ContributionExplanationTests(unittest.TestCase):
    def setUp(self):
        self.report = json.loads(REPORT.read_text())
        self.track = self.report['tracks'][0]

    def explain(self, worlds=None):
        return contribution_explanation.describe_track(
            self.report['config'], self.track,
            self.report['worlds'] if worlds is None else worlds)

    def test_original_live_accounting_reconstructs_negative_increment(self):
        result = self.explain()
        search = result['search']
        self.assertTrue(search['available'])
        self.assertEqual(search['baseline_contribution'], 14785)
        self.assertEqual(search['offer_contribution'], 12421)
        self.assertEqual(search['incremental_contribution'], -2364)
        self.assertEqual(search['cash_view']['incremental_contribution'], -1380)
        self.assertEqual(search['cash_view']['offer_contribution'], 13405)
        self.assertEqual(search['cash_flow']['offer']['cash_collected'], 24700)
        self.assertEqual(search['cash_flow']['offer']['refunds_paid'], 800)
        self.assertEqual(search['cash_flow']['offer']['mandatory_remitted'], 7000)
        self.assertEqual(search['annual_fee_allocation'], 1/3)
        rows = {row['id']: row for row in search['components']}
        self.assertEqual(rows['normal_base_revenue']['contribution_effect'], -3360)
        self.assertEqual(rows['member_base_revenue']['contribution_effect'], 504)
        self.assertEqual(rows['membership_revenue']['contribution_effect'], 532)
        self.assertEqual(rows['membership_service_cost']['change'], 40)
        self.assertEqual(rows['membership_service_cost']['contribution_effect'], -40)
        self.assertEqual(sum(row['contribution_effect'] for row in rows.values()), -2364)
        self.assertEqual(search['buyers']['net_change'], 0)
        self.assertEqual(search['buyers']['baseline'], 6)
        self.assertTrue(search['reconciliation']['passed'])

    def test_holdout_checks_every_replica_not_mean_service_rate(self):
        result = self.explain()
        phase = result['validation']
        self.assertEqual(phase['baseline_contribution'], 11452.5)
        self.assertEqual(phase['offer_contribution'], 9088.5)
        self.assertEqual(phase['incremental_contribution'], -2364)
        service = phase['service_requirement']
        self.assertEqual(service['mean_rate'], .75)
        self.assertEqual(service['lowest_rate'], .5)
        self.assertFalse(service['passed'])
        self.assertEqual([r['seed'] for r in service['replicas'] if not r['passed']], [50221])
        self.assertTrue(any('50221' in r and '50%' in r and '60%' in r for r in result['no_offer_reasons']))
        self.assertTrue(any('Search' in r and '-2364' in r for r in result['no_offer_reasons']))
        self.assertTrue(any('Validation' in r and '-2364' in r for r in result['no_offer_reasons']))

    def test_pairing_uses_seeds_and_never_silently_drops_missing_world(self):
        shuffled = list(reversed(self.report['worlds']))
        self.assertEqual(self.explain(shuffled), self.explain())
        missing = [w for w in shuffled if not (w['phase']=='holdout_baseline' and w['seed']==50221)]
        phase = self.explain(missing)['validation']
        self.assertFalse(phase['available'])
        self.assertNotIn('incremental_contribution', phase)
        self.assertIn('matching', phase['reason'])

    def test_same_seed_different_or_missing_exogenous_world_is_not_paired(self):
        for replacement in ('0'*64, None):
            with self.subTest(exogenous_sha256=replacement):
                worlds = copy.deepcopy(self.report['worlds'])
                for world in worlds:
                    if world['phase']=='search':
                        if replacement is None:
                            world['result'].pop('exogenous_sha256')
                        else:
                            world['result']['exogenous_sha256'] = replacement
                phase = self.explain(worlds)['search']
                self.assertFalse(phase['available'])
                self.assertFalse(phase['pairing']['complete'])
                self.assertIn('exogenous', phase['reason'])
                self.assertNotIn('incremental_contribution', phase)

    def test_missing_accounting_is_unavailable_not_fabricated_zero(self):
        worlds = copy.deepcopy(self.report['worlds'])
        for world in worlds:
            if world['phase']=='search':
                del world['result']['ledger']['normal_base_revenue']
        phase = self.explain(worlds)['search']
        self.assertFalse(phase['available'])
        self.assertNotIn('components', phase)

    def test_reconciliation_reports_corrupted_saved_totals_without_rewriting(self):
        worlds = copy.deepcopy(self.report['worlds'])
        for world in worlds:
            if world['phase']=='search': world['result']['contribution'] += 1
        before = copy.deepcopy(worlds)
        phase = self.explain(worlds)['search']
        self.assertFalse(phase['reconciliation']['passed'])
        self.assertEqual(worlds, before)
        self.assertEqual(phase['incremental_contribution'], -2363)

    def test_read_adds_view_without_mutating_historical_rows_or_artifact(self):
        digest = hashlib.sha256(REPORT.read_bytes()).hexdigest()
        with tempfile.TemporaryDirectory() as folder, patch.object(optimization_store, 'BASE', Path(folder)):
            r = self.report
            with optimization_store.connection() as db:
                db.execute('INSERT INTO optimization_runs VALUES (?,?,?,?,?,?,?,?,?)',
                    (r['run_id'],r['status'],json.dumps(r['config']),json.dumps(r['provenance']),
                     json.dumps(r['progress']),json.dumps(r['counts']),r['created_at'],r['updated_at'],r['error']))
                for row in self.track['rounds']:
                    db.execute('INSERT INTO optimization_rounds VALUES (?,?,?,?)',
                        (r['run_id'],'live',row['round'],json.dumps(row)))
                for w in r['worlds']:
                    db.execute('INSERT INTO optimization_worlds VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                        (w['world_id'],r['run_id'],w['mode'],w['phase'],w['round_number'],w['seed'],
                         json.dumps(w['policy']),'{}',json.dumps(w['result']),w['status'],0))
                before = [tuple(x) for x in db.execute('SELECT * FROM optimization_worlds ORDER BY world_id')]
            viewed = optimization.read(r['run_id'])
            self.assertEqual(viewed['tracks'][0]['decision'], 'NO_OFFER')
            self.assertEqual(viewed['tracks'][0]['contribution_explanation']['search']['incremental_contribution'], -2364)
            self.assertEqual(viewed['tracks'][0]['best'], self.track['best'])
            with optimization_store.connection() as db:
                after = [tuple(x) for x in db.execute('SELECT * FROM optimization_worlds ORDER BY world_id')]
            self.assertEqual(before, after)
        self.assertEqual(hashlib.sha256(REPORT.read_bytes()).hexdigest(), digest)


if __name__ == '__main__':
    unittest.main()

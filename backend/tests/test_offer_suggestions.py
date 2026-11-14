import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from backend import offer_suggestions as subject, optimization_store as runs
from backend.store import Store


class OfferSuggestionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.paths = patch.object(runs, 'BASE', Path(self.temp.name)/'runs')
        self.paths.start(); self.addCleanup(self.paths.stop)
        self.inventory = Store(Path(self.temp.name)/'inventory.sqlite3')
        self.provenance = patch.object(subject.optimization, 'provenance', return_value={'version':'test'})
        self.provenance.start(); self.addCleanup(self.provenance.stop)
        self.reports = {}
        self.reader = patch.object(subject.optimization, 'read', side_effect=lambda run_id: self.reports[run_id])
        self.reader.start(); self.addCleanup(self.reader.stop)
        self.forecast = lambda *_: {'releasable_seats':100}

    def add(self, suffix, flight='SYN-A', day=14, decision='OFFER', stale=False):
        run_id = 'opt-'+suffix*16
        config = {'scope':{'flight_id':flight,'as_of_day':day},'release_fraction':.5}
        now = time.time()
        with runs.connection() as db:
            db.execute('INSERT INTO optimization_runs VALUES (?,?,?,?,?,?,?,?,?)',
                       (run_id,'completed',runs.encode(config),runs.encode({'version':'old' if stale else 'test'}),'{}','{}',now,now,None))
        self.reports[run_id] = {'tracks':[{'mode':'math','decision':decision,
             'best':{'member_fare':70,'membership_fee':399},
             'validation':{'incremental_contribution':100,'contribution':200}}]}
        return run_id

    def test_only_matching_flight_round_and_current_model_is_suggested(self):
        expected = self.add('a')
        self.add('b',flight='SYN-B'); self.add('c',day=7); self.add('d',stale=True)
        result = subject.suggestions('SYN-A',14,self.inventory,self.forecast)
        self.assertEqual([row['run_id'] for row in result['suggestions']],[expected])
        self.assertEqual(result['suggestions'][0]['release_seats'],50)

    def test_carry_forward_and_member_sales_are_deducted_once(self):
        self.add('a')
        offer = self.inventory.offer('SYN-A',28,20,70,250,100)
        self.inventory.join_plan('customer')
        self.inventory.book(offer['id'],'customer',28,100)
        result = subject.suggestions('SYN-A',14,self.inventory,self.forecast)
        self.assertEqual(result['current_release_limit'],80)
        self.assertEqual(result['suggestions'][0]['release_seats'],30)
        self.inventory.offer('SYN-A',14,1,70,250,100)
        self.assertEqual(subject.suggestions('SYN-A',14,self.inventory,self.forecast)['suggestions'],[])

    def test_newer_no_offer_supersedes_old_price(self):
        self.add('a'); self.add('b',decision='NO_OFFER')
        self.assertEqual(subject.suggestions('SYN-A',14,self.inventory,self.forecast)['suggestions'],[])

    def test_selected_profile_protection_limits_the_suggested_quota(self):
        from backend.seat_feedback import initial_profile
        run = self.add('a')
        profile = initial_profile()
        profile['horizons']['14']['extra_protection'] = 40
        self.reports[run]['tracks'][0]['best']['seat_calibration'] = profile
        prediction = lambda *_: {'releasable_seats':100,'available_seats':120,
                                 'expected_remaining_demand':10,'protection_p90':20}
        suggestion = subject.suggestions('SYN-A',14,self.inventory,prediction)['suggestions'][0]
        self.assertEqual(suggestion['validated_release_ceiling'],60)
        self.assertEqual(suggestion['release_seats'],30)

    def test_published_plan_must_match_tested_fee_even_at_transaction_time(self):
        run = self.add('a')
        draft = {'optimization_run_id':run,'optimization_mode':'math','flight_id':'SYN-A',
                 'days_to_departure':14,'base_fare':70,'quantity':50}
        self.inventory.plan(99)
        with self.assertRaisesRegex(ValueError,'membership fee'):
            subject.validate_draft(draft,self.inventory,self.forecast)
        with self.assertRaisesRegex(ValueError,'Membership fee'):
            self.inventory.offer('SYN-A',14,50,70,250,100,expected_plan_fee=399)
        self.assertEqual(self.inventory.offers(),[])
        self.inventory.plan(399)
        self.assertEqual(subject.validate_draft(draft,self.inventory,self.forecast)['run_id'],run)
        self.inventory.offer('SYN-A',14,50,70,250,100,expected_plan_fee=399)

    def test_publication_binding_rejects_wrong_flight_or_excess_quota(self):
        run_id = self.add('a')
        draft = {'optimization_run_id':run_id,'optimization_mode':'math','flight_id':'SYN-A',
                 'days_to_departure':14,'base_fare':70,'quantity':50}
        subject.validate_draft(draft,self.inventory,self.forecast)
        for change in ({'flight_id':'SYN-B'}, {'quantity':51}, {'base_fare':71}, {'days_to_departure':7}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                subject.validate_draft(draft|change,self.inventory,self.forecast)
        subject.validate_draft({'flight_id':'SYN-B'},self.inventory,self.forecast)


if __name__ == '__main__': unittest.main()

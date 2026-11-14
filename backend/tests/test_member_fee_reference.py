import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from backend import member_portal
from backend.store import Store
from scripts.apply_member_fee_reference import reference


class MemberFeeReferenceTests(unittest.TestCase):
    def test_direction_airport_and_fx_are_distinct(self):
        expected = {('HKG','NRT'):673,('HKG','HND'):673,('HKG','KIX'):673,
                    ('NRT','HKG'):959.67,('HND','HKG'):949.37,('KIX','HKG'):982.72}
        for route, amount in expected.items():
            detail=reference(*route)
            self.assertAlmostEqual(sum(l['amount'] for l in detail['lines']),amount)
            self.assertAlmostEqual(sum(c['amount'] for c in detail['components']),amount)
            self.assertEqual(detail['components'][0]['code'],'YR')
        with self.assertRaises(ValueError): reference('HKG','LHR')

    def test_quote_receipt_rounding_and_repricing_protection(self):
        with tempfile.TemporaryDirectory() as temp:
            store=Store(Path(temp)/'demo.sqlite3')
            offer=store.offer('DEMO',28,2,100,250,2)
            detail=reference('NRT','HKG')
            store.set_offer_fee_breakdown(offer['id'],detail)
            catalog=[dict(flight_id='DEMO',origin='NRT',destination='HKG',departure_at='2027-05-18T10:00:00+09:00',capacity=180)]
            history=[dict(days_to_departure=28,normal_base_fare=500,normal_total_fare=750)]
            with patch.object(member_portal.data,'flights',return_value=catalog),patch.object(member_portal.data,'history',return_value=history):
                row=member_portal.flights(store,lambda *_:{'releasable_seats':2})['flights'][0]
                self.assertEqual(row['total'],1059.67)
                self.assertEqual(row['normal_total'],1459.67)
                store.join_plan('person')
                with self.assertRaisesRegex(ValueError,'price changed'):
                    member_portal.book(store,lambda *_:{'releasable_seats':2},'person',offer['id'],350)
                result=member_portal.book(store,lambda *_:{'releasable_seats':2},'person',offer['id'],row['total'])
                self.assertEqual(result['booking']['total'],1059.67)
                reloaded=Store(store.path)
                receipt=member_portal.account(reloaded,'person')['bookings'][0]
                self.assertEqual(receipt['fee_breakdown'],detail)
                self.assertEqual(receipt['total'],1059.67)
                self.assertEqual(reloaded.set_offer_fee_breakdown(offer['id'],detail),959.67)
                changed=copy.deepcopy(detail);changed['lines'][0]['amount']+=1
                with self.assertRaisesRegex(ValueError,'existing bookings'):
                    reloaded.set_offer_fee_breakdown(offer['id'],changed)
                self.assertEqual(reloaded.offer_info(offer['id'])['fees'],959.67)

    def test_invalid_amounts_leave_offer_unchanged(self):
        with tempfile.TemporaryDirectory() as temp:
            store=Store(Path(temp)/'demo.sqlite3');offer=store.offer('demo',28,1,100,250,1)
            for value in [-1, float('inf'), .001]:
                with self.assertRaises(ValueError):
                    store.set_offer_fee_breakdown(offer['id'],{'currency':'HKD','lines':[{'amount':value}]})
            self.assertEqual(store.offer_info(offer['id'])['fees'],250)

    def test_price_change_between_quote_and_transaction_requires_review(self):
        with tempfile.TemporaryDirectory() as temp:
            store=Store(Path(temp)/'demo.sqlite3')
            offer=store.offer('DEMO',28,1,100,250,1)
            store.join_plan('person')
            def forecast(*_):
                store.set_offer_fee_breakdown(offer['id'],reference('HKG','NRT'))
                return {'releasable_seats':1}
            with self.assertRaisesRegex(ValueError,'price changed'):
                member_portal.book(store,forecast,'person',offer['id'],350)
            self.assertEqual(store.account('person')['bookings'],[])
            self.assertEqual(store.offer_info(offer['id'])['remaining'],1)

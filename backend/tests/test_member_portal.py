import concurrent.futures
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend import member_portal, server
from backend.store import Store


class MemberPortalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(Path(self.temp.name)/'demo.sqlite3')
        self.catalog = [{'flight_id':'SYN-TEST','origin':'HKG','destination':'FUK',
                         'departure_at':'2027-05-30T10:30:00+08:00','capacity':180}]
        self.history = [{'days_to_departure':28,'normal_total_fare':850},
                        {'days_to_departure':14,'normal_total_fare':900}]

    def test_member_fee_owned_by_server_and_paid_once(self):
        with patch.object(server, 'store', return_value=self.store):
            self.assertEqual(server.get('/api/member-portal/config')['membership']['fee'],399)
            joined = server.post('/api/member-portal/join', {'customer_id':'demo-person','membership_fee':0,'expected_fee':399})
            self.assertEqual(joined['member']['fee'],399)
            server.post('/api/member-portal/plan', {'membership_fee':599})
            again = server.post('/api/member-portal/join', {'customer_id':'demo-person','expected_fee':599})
            self.assertEqual(again['member'],joined['member'])
            with self.assertRaisesRegex(ValueError,'price changed'):
                server.post('/api/member-portal/join', {'customer_id':'another','expected_fee':399})
            self.assertIsNone(self.store.account('another')['membership'])

    def test_catalog_uses_published_supply_and_current_protection(self):
        with patch.object(member_portal.data,'flights',return_value=self.catalog), patch.object(member_portal.data,'history',return_value=self.history):
            self.assertEqual(member_portal.flights(self.store,lambda *_:{'releasable_seats':4})['flights'],[])
            first=self.store.offer('SYN-TEST',28,3,70,250,4)
            self.store.offer('SYN-TEST',14,1,100,250,4)
            rows=member_portal.flights(self.store,lambda *_:{'releasable_seats':2})['flights']
            self.assertEqual(len(rows),1)
            self.assertEqual(rows[0]['offer_id'],first['id'])
            self.assertEqual(rows[0]['total'],320)
            self.assertEqual(rows[0]['normal_total'],900)
            self.assertEqual(rows[0]['bookable_seats'],2)
            self.assertEqual(rows[0]['days_to_departure'],14)
            blocked=member_portal.flights(self.store,lambda *_:{'releasable_seats':0})['flights'][0]
            self.assertEqual(blocked['bookable_seats'],0)

    def test_checkout_rechecks_availability_and_survives_store_reload(self):
        offer=self.store.offer('SYN-TEST',28,1,70,250,1)
        self.store.join_plan('demo-person')
        with self.assertRaisesRegex(ValueError,'price changed'):
            member_portal.book(self.store,lambda *_:{'releasable_seats':1},'demo-person',offer['id'],70)
        with self.assertRaisesRegex(ValueError,'protection'):
            member_portal.book(self.store,lambda *_:{'releasable_seats':0},'demo-person',offer['id'],320)
        booking=member_portal.book(self.store,lambda *_:{'releasable_seats':1},'demo-person',offer['id'],320)
        self.assertEqual(booking['booking']['total'],320)
        self.assertEqual(booking['remaining'],0)
        reloaded=Store(self.store.path)
        with patch.object(member_portal.data,'flights',return_value=self.catalog):
            account=member_portal.account(reloaded,'demo-person')
        self.assertTrue(account['membership']['active'])
        self.assertEqual(account['bookings'][0]['mandatory_fees'],250)
        self.assertEqual(account['bookings'][0]['destination'],'FUK')
        self.assertEqual(account['bookings'][0]['id'],booking['booking']['id'])

    def test_portal_cannot_override_simulation_clock_or_price(self):
        offer=self.store.offer('SYN-TEST',28,1,70,250,2)
        self.store.offer('SYN-TEST',14,1,70,250,2)
        self.store.join_plan('person')
        seen=[]
        def forecast(flight,day):
            seen.append(day)
            return {'releasable_seats':2}
        with patch.object(server,'store',return_value=self.store),patch.object(server,'forecast_for',side_effect=forecast):
            result=server.post('/api/member-portal/book',{'customer_id':'person','offer_id':offer['id'],
                                                        'days_to_departure':28,'total':0,'expected_total':320})
        self.assertEqual(seen,[14])
        self.assertEqual(result['booking']['total'],320)

    def test_last_seat_competition_and_duplicate_do_not_oversell(self):
        offer=self.store.offer('SYN-TEST',28,1,0,250,1)
        for name in ('a','b'):self.store.join_plan(name)
        def buy(name):
            try:return member_portal.book(self.store,lambda *_:{'releasable_seats':1},name,offer['id'],250)
            except ValueError:return None
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(buy,('a','b')))
        self.assertEqual(sum(r is not None for r in results),1)
        self.assertEqual(self.store.offer_info(offer['id'])['remaining'],0)


if __name__=='__main__':unittest.main()

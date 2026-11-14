"""Verify member-supply gates, controlled fare search and synthetic checkout.

Creates bounded math experiments and one small simulated offer/booking. --live
adds one real-provider candidate experiment capped at 128 decision attempts.
"""
import argparse
import json
import time
import urllib.error
import urllib.request
import uuid


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url',default='http://127.0.0.1:8000')
    parser.add_argument('--live',action='store_true')
    args=parser.parse_args();base=args.url.rstrip('/')
    def call(path,body=None):
        request=urllib.request.Request(base+path,data=None if body is None else json.dumps(body).encode(),
            headers={'Content-Type':'application/json','Origin':base})
        with urllib.request.urlopen(request,timeout=90) as response:return json.load(response)
    def wait(run):
        deadline=time.monotonic()+900
        while time.monotonic()<deadline:
            report=call('/api/optimization/runs/'+run)
            if report['status']=='completed':return report
            if report['status'] not in ('queued','running'):raise AssertionError((report['status'],report.get('error')))
            time.sleep(1)
        raise TimeoutError(run)
    flights=call('/api/flights')['flights']
    demos=[f for f in flights if f['flight_id'].startswith('DEMO-')]
    assert len(demos)==222
    before={r['run_id'] for r in call('/api/optimization/runs')['runs']}
    try:
        call('/api/optimization/runs',{'flight_id':'SYN-00004','forecast_day':28,'mode':'live','rounds':6,'customers':14})
        raise AssertionError('Zero-supply optimization unexpectedly started')
    except urllib.error.HTTPError as error:
        assert error.code==400
        assert 'releasable member seats' in error.read().decode()
    assert {r['run_id'] for r in call('/api/optimization/runs')['runs']}==before
    fid='DEMO-HKG-ICN-20270515'
    initial=call('/api/optimization/initial-policy',{'flight_id':fid,'forecast_day':28})
    assert initial['scope']['releasable_seats']==44
    start=call('/api/optimization/runs',{'flight_id':fid,'forecast_day':28,'mode':'math',
        'rounds':4,'customers':8,'replicates':2,'initial_membership_fee':399,'program_cost':0,'max_calls':0})
    report=wait(start['run_id']);rows=report['tracks'][0]['rounds']
    assert rows[0]['member_fare']==84 and rows[1]['member_fare']==63 and rows[2]['member_fare']==105
    assert all(r['seat_calibration']==rows[0]['seat_calibration'] for r in rows)
    assert any(r['mean_member_buyers']>0 for r in rows)
    assert all(r['mean_member_seats_released']>0 for r in rows)
    exported=call('/api/optimization/runs/'+start['run_id']+'/export')
    assert all(all(w['result']['checks'].values()) and w['result']['profit_attribution_reconciled'] for w in exported['worlds'])
    results=[{'run_id':start['run_id'],'mode':'math','prices':[r['member_fare'] for r in rows],
        'member_buyers':[r['mean_member_buyers'] for r in rows],'regular_buyers':[r['mean_regular_buyers'] for r in rows],
        'decision':report['tracks'][0]['decision']}]
    # A separate flight keeps the default/optimized example's new quota intact.
    booked_flight=None
    for flight in demos:
        if flight['flight_id']==fid or flight.get('demo_priority')!=1:continue
        prediction=call('/api/forecast',{'flight_id':flight['flight_id'],'days_to_departure':28})['forecast']
        if prediction['seat_inventory']['new_releasable_today']>=5:
            booked_flight=flight['flight_id'];break
    assert booked_flight
    offer=call('/api/offers',{'flight_id':booked_flight,'days_to_departure':28,'quantity':5,'base_fare':70})['offer']
    customer='SUPPLY-'+uuid.uuid4().hex[:12]
    fee=call('/api/member-portal/config')['membership']['fee']
    call('/api/member-portal/join',{'customer_id':customer,'expected_fee':fee})
    call('/api/member-portal/book',{'customer_id':customer,'offer_id':offer['id'],'expected_total':320})
    after=call('/api/forecast',{'flight_id':booked_flight,'days_to_departure':28})['forecast']['seat_inventory']
    assert after['confirmed_member_bookings']==1 and after['new_releasable_today']==0 and after['published_bookable']==4
    next_round=call('/api/forecast',{'flight_id':booked_flight,'days_to_departure':14})['forecast']['seat_inventory']
    assert next_round['new_releasable_today']==max(0,next_round['member_headroom']-4)
    off=call('/api/forecast',{'flight_id':booked_flight,'days_to_departure':13})['forecast']['seat_inventory']
    assert off['new_releasable_today']==0 and off['next_release_day']==7
    assert sum(off[k] for k in ('normal_booked','member_booked','normal_protected','published_bookable','unpublished_headroom','held_seats'))==off['capacity']
    if args.live:
        start=call('/api/optimization/runs',{'flight_id':fid,'forecast_day':28,'mode':'live','rounds':1,
            'customers':2,'replicates':1,'initial_membership_fee':399,'program_cost':0,'max_calls':8,'total_live_budget':128})
        live=wait(start['run_id']);row=live['tracks'][0]['rounds'][0]
        assert 0<live['counts']['provider_calls']<=128 and live['counts']['failures']==0
        assert row['mean_member_offer_observations']>0
        results.append({'run_id':start['run_id'],'mode':'live','counts':live['counts'],
            'member_buyers':row['mean_member_buyers'],'regular_buyers':row['mean_regular_buyers'],
            'member_offer_observations':row['mean_member_offer_observations'],'decision':live['tracks'][0]['decision']})
    print(json.dumps({'status':'passed','demo_flights':222,'zero_supply_gate':'rejected_before_run_creation',
        'published_flight':booked_flight,'offer_id':offer['id'],'customer':customer,'bookable_after_purchase':4,'runs':results}))


if __name__=='__main__':main()

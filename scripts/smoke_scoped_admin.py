"""Exercise dated-flight optimization via HTTP; --live opts into <=64 decisions.

The default creates bounded mathematical experiments only. No offers are
published; existing inventory and paid demo memberships remain unchanged.
"""
import argparse
import json
import time
import urllib.request
import urllib.error


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://127.0.0.1:8000')
    parser.add_argument('--live', action='store_true')
    args = parser.parse_args()
    base = args.url.rstrip('/')
    def call(path, body=None):
        request = urllib.request.Request(base+path, data=None if body is None else json.dumps(body).encode(),
                   headers={'Content-Type':'application/json','Origin':base})
        with urllib.request.urlopen(request, timeout=90) as response: return json.load(response)
    def wait(run_id):
        limit = time.monotonic()+900
        while time.monotonic()<limit:
            report = call('/api/optimization/runs/'+run_id)
            if report['status']=='completed': return report
            if report['status'] not in ('queued','running'):
                raise AssertionError((report['status'],report.get('error'),report['counts']))
            time.sleep(1)
        raise TimeoutError(run_id)
    flights = call('/api/flights')['flights']
    network = [f for f in flights if f['flight_id'].startswith('NET-')]
    assert len(network)==222 and len({(f['origin'],f['destination']) for f in network})==74
    records=[]
    for flight_id in ('NET-HKG-HND-20270518','NET-HND-HKG-20270521'):
        suggestion = call('/api/optimization/initial-policy',{'flight_id':flight_id,'forecast_day':28})
        start = call('/api/optimization/runs',{'flight_id':flight_id,'forecast_day':28,'rounds':3,'customers':4,
            'mode':'math','max_calls':0,'initial_member_fare':1999,'initial_membership_fee':99,'program_cost':0})
        report=wait(start['run_id']); scope=report['config']['scope']
        assert scope['flight_id']==flight_id
        assert report['config']['initial_member_fare']==suggestion['initial_member_fare']
        assert report['config']['initial_membership_fee']==99
        assert report['counts']['provider_calls']==0
        assert all(row['membership_fee']==99 for row in report['tracks'][0]['rounds'])
        exported=call('/api/optimization/runs/'+start['run_id']+'/export')
        assert all(all(w['result']['checks'].values()) for w in exported['worlds'])
        offers=call('/api/optimization/suggestions?flight_id='+flight_id+'&forecast_day=28')
        assert all(s['flight_id']==flight_id and s['release_seats']<=offers['current_release_limit'] for s in offers['suggestions'])
        records.append({'run_id':start['run_id'],'scope':{k:scope[k] for k in ('flight_id','normal_base_fare','available_seats')},
                        'p0':suggestion['initial_member_fare'],'decision':report['tracks'][0]['decision']})
    if args.live:
        start=call('/api/optimization/runs',{'flight_id':'NET-HKG-HND-20270518','forecast_day':28,
            'rounds':1,'customers':1,'mode':'live','max_calls':2,'total_live_budget':64,
            'initial_membership_fee':99,'program_cost':0})
        report=wait(start['run_id'])
        assert 2<report['counts']['live_attempts']<=64
        assert report['counts']['failures']==0
        records.append({'run_id':start['run_id'],'mode':'live','counts':report['counts']})
    print(json.dumps({'status':'passed','flights':len(network),'directed_routes':74,'runs':records}))


if __name__=='__main__': main()

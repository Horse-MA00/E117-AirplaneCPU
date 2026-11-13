"""Run against a running local server; creates clearly synthetic demo transactions."""
import json,urllib.request,urllib.error,uuid
BASE='http://127.0.0.1:8000'
def call(path,body=None):
 req=urllib.request.Request(BASE+path,data=None if body is None else json.dumps(body).encode(),headers={'Content-Type':'application/json'})
 with urllib.request.urlopen(req,timeout=30) as response:return json.load(response)
summary=call('/api/summary');assert summary['dataset']['rows']==200000
flights=call('/api/flights')['flights'];assert len(flights)==1105
found=None
for f in flights[:20]:
 r=call('/api/forecast',{'flight_id':f['flight_id'],'days_to_departure':28})['forecast']
 if r['releasable_seats']>=2:found=f;break
assert found
id=found['flight_id']
result=call('/api/optimize',{'flight_id':id,'days_to_departure':28,'config':{'customers':100}})
assert len(result['candidates'])==192
cutoff=call('/api/optimize',{'flight_id':id,'days_to_departure':0,'config':{}})
assert cutoff['best']['decision']=='NO_OFFER'
assert call('/api/agents/run',{'count':14})['summary']['customers']==14
person='SMOKE-'+uuid.uuid4().hex[:12]
member=call('/api/members',{'customer_id':person,'membership_fee':399})['member'];assert member['fee']==399
try:
 offer=call('/api/offers',{'flight_id':id,'days_to_departure':28,'quantity':1,'base_fare':30})['offer']
 booking=call('/api/bookings',{'offer_id':offer['id'],'customer_id':person});assert booking['booking']['total']==280
except urllib.error.HTTPError as e:raise AssertionError(e.read())
try:call('/api/bookings',{'offer_id':offer['id'],'customer_id':person});raise AssertionError('duplicate accepted')
except urllib.error.HTTPError as e:assert e.code==400
for path in ('/.env.local','/%2e%2e/.env.local'):
 try:urllib.request.urlopen(BASE+path);raise AssertionError('private file exposed')
 except urllib.error.HTTPError as e:assert e.code==404
print(json.dumps({'status':'passed','rows':summary['dataset']['rows'],'flights':len(flights),'candidates':len(result['candidates']),'booking_total':booking['booking']['total']}))

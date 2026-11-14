import json,time,urllib.request,uuid
BASE='http://127.0.0.1:8000'
def req(path,body=None):
 request=urllib.request.Request(BASE+path,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json','Origin':BASE})
 with urllib.request.urlopen(request,timeout=60) as response:return json.load(response)
config=req('/api/member-portal/config')
flights=req('/api/member-portal/flights')['flights']
choice=next((f for f in flights if f['bookable_seats']>0),None)
if choice is None:
 for flight in req('/api/flights')['flights']:
  prediction=req('/api/forecast',{'flight_id':flight['flight_id'],'days_to_departure':28})['forecast']
  if prediction['releasable_seats']>=2:
   req('/api/offers',{'flight_id':flight['flight_id'],'days_to_departure':28,'quantity':2,'base_fare':70})
   choice=next(f for f in req('/api/member-portal/flights')['flights'] if f['flight_id']==flight['flight_id'])
   break
assert choice is not None
customer='portal-check-'+uuid.uuid4().hex[:10]
before=req('/api/member-portal/accounts/'+customer)
assert before['membership'] is None and before['bookings']==[]
member=req('/api/member-portal/join',{'customer_id':customer,'expected_fee':config['membership']['fee']})['member']
booking=req('/api/member-portal/book',{'customer_id':customer,'offer_id':choice['offer_id'],'expected_total':choice['total']})
after=req('/api/member-portal/accounts/'+customer)
assert len(after['bookings'])==1 and after['membership']['active']
assert after['bookings'][0]['total']==choice['base_fare']+choice['mandatory_fees']
assert after['bookings'][0]['id']==booking['booking']['id']
assert req('/api/member-portal/join',{'customer_id':customer})['member']==member
print(json.dumps({'status':'passed','flight_id':choice['flight_id'],'membership_fee':member['fee'],'ticket_total':choice['total'],'persisted_bookings':len(after['bookings']),'identity':customer}))

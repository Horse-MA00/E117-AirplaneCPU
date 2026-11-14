"""Local same-origin application server. Run: python -m backend.server."""
import json,math,mimetypes,re,traceback
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from urllib.parse import urlparse,unquote,parse_qs,urlsplit
from pathlib import Path
from functools import lru_cache
from . import data,member_portal,adaptive_pricing,adaptive_store,demo_auth
from .store import Store
from .evidence import EvidenceUnavailable,read_evaluation
from .errors import NotFound
from .oag import load_env
ROOT=Path(__file__).resolve().parents[1]; load_env()
_store=None

def store():
 global _store
 if _store is None:_store=Store(ROOT/'data/private/demo.sqlite3')
 return _store

def number(x,name,lo,hi,integer=False):
 if isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x) or not lo<=x<=hi or (integer and int(x)!=x):raise ValueError(f'{name} must be {lo}..{hi}' + (' (integer)' if integer else ''))
 return int(x) if integer else x

def ident(x):
 if not isinstance(x,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',x):raise ValueError('Invalid identifier')
 return x

def query_int(query,names,default):
 """First present query parameter as an integer; malformed input is a 400, not a 404."""
 for name in names:
  if name in query:
   raw=query[name][0]
   try:return int(raw)
   except ValueError:raise ValueError(f'{name} must be an integer') from None
 return default

@lru_cache(maxsize=96)
def forecast_for(flight,day):
 from .forecast import forecast
 return forecast(data.history(flight),days_to_departure=day,seed=117)

def get(path,query=None):
 if path=='/api/adaptive-pricing/status':
  return adaptive_pricing.status()
 if path=='/api/adaptive-pricing/runs':
  return {'runs':adaptive_pricing.list_runs()}
 if path.startswith('/api/adaptive-pricing/runs/'):
  parts=path.strip('/').split('/')
  try:
   if len(parts)==4:return adaptive_pricing.read(ident(parts[3]))
   if len(parts)==5 and parts[4]=='export':return adaptive_pricing.export_run(ident(parts[3]))
   if len(parts)==5 and parts[4]=='events':return adaptive_pricing.events(ident(parts[3]),query_int(query or {},('limit',),100),query_int(query or {},('offset',),0))
   if len(parts)==5 and parts[4]=='analysis-attempts':
    run_id=ident(parts[3]);adaptive_pricing.read(run_id)
    return adaptive_store.analysis_attempts(run_id,query_int(query or {},('round',),None))
  except ValueError as e:
   if str(e)=='Adaptive pricing run not found':raise NotFound(str(e)) from None
   raise
  raise NotFound('Adaptive pricing endpoint not found')
 if path=='/api/health':
  with store().connect() as connection:connection.execute('SELECT 1').fetchone()
  return {'status':'ok'}
 if path in ('/api/member-portal/config','/api/member-portal/plan'):return member_portal.config(store())
 if path=='/api/member-portal/flights':return member_portal.flights(store(),forecast_for)
 if path.startswith('/api/member-portal/accounts/'):
  if len(path.strip('/').split('/'))!=4:raise NotFound('Account endpoint not found')
  return member_portal.account(store(),ident(path.split('/')[-1]))
 if path=='/api/summary':return {'dataset':{'rows':data.manifest()['rows'],'catalog_rows':data.manifest().get('catalog_rows',data.manifest()['rows']),'flights':len(data.flights()),'source':'synthetic','manifest':data.manifest()},'model':'NHPP','llm':adaptive_pricing.status()}
 if path=='/api/evaluation':
  return read_evaluation(ROOT)
 if path=='/api/evaluation/extended':
  return read_evaluation(ROOT,extended=True)
 if path=='/api/oag':
  result=[]
  for p in (ROOT/'data/private').glob('oag-*.json'):
   cached=json.loads(p.read_text())
   for row in cached.get('records',[]):
    result.append({'carrier':row.get('carrier',{}).get('iata'),'flight_number':row.get('flightNumber'),'origin':row.get('departure',{}).get('airport',{}).get('iata'),'destination':row.get('arrival',{}).get('airport',{}).get('iata'),'date':row.get('departure',{}).get('date',{}).get('local'),'predicted_capacity':row.get('seatingCapacity',{}).get('predicted',{}).get('totalSeats'),'source':'oag_live_cached_capacity_estimate'})
  return {'flights':result,'limitation':'Capacity estimates only, no observed fares or occupancy.'}
 if path=='/api/status':
  records=[]
  for p in (ROOT/'data/private').glob('oag-*.json'):
   r=json.loads(p.read_text());records.append({'date':r['date'],'state':r['state'],'record_count':len(r['records']),'attempts':r['attempts']})
  return {'model':'NHPP','llm':adaptive_pricing.status(),'oag':records,'simulated_booking':True}
 if path=='/api/flights':return {'flights':data.flights()}
 if path.startswith('/api/flights/'):
  id=ident(path.split('/')[-1]);rows=data.history(id);f=next(f for f in data.flights() if f['flight_id']==id)
  return {'flight':f,'history':rows}
 if path=='/api/offers':return {'offers':store().offers()}
 raise NotFound('Not found')

def post(path,body):
 if path=='/api/offers' and any(key in body for key in ('optimization_run_id','optimization_mode')):
  raise ValueError('Retired optimization bindings are not accepted; submit a manual offer')
 if path=='/api/adaptive-pricing/scope':
  return adaptive_pricing.scope(body)
 if path=='/api/adaptive-pricing/runs':
  return adaptive_pricing.start(body)
 if path=='/api/member-portal/plan':
  store().plan(number(body.get('membership_fee'),'membership_fee',0,5000,True))
  return member_portal.config(store())
 if path=='/api/member-portal/join':
  expected=number(body['expected_fee'],'expected_fee',0,5000) if 'expected_fee' in body else None
  member=store().join_plan(ident(body.get('customer_id')),expected)
  return {'member':member,'simulated':True,'currency':'HKD'}
 if path=='/api/member-portal/book':
  expected=number(body['expected_total'],'expected_total',0,10000) if 'expected_total' in body else None
  return member_portal.book(store(),forecast_for,ident(body.get('customer_id')),ident(body.get('offer_id')),expected)
 if path in ('/api/forecast','/api/offers'):
  flight=ident(body.get('flight_id'));day=number(body.get('days_to_departure',28),'day',0,28,True)
  f=forecast_for(flight,day)
  if path=='/api/forecast':
   current=dict(f); release=store().release_status(flight,day,f['releasable_seats'])
   current['risk_release_ceiling']=f['releasable_seats']
   current['release_status']=release
   from .seat_inventory import describe
   current['seat_inventory']=describe(f,release,day)
   current['releasable_seats']=release['new_release_limit']
   current['committed_member_seats']=release['member_sold']+release['total_active_unsold']
   current['assumptions']=list(f['assumptions'])+['New member quota is issued once per round at D28, D14 and D7 only. Earlier valid unsold quotas carry forward; sold demo seats are accounted once.']+([release['blocked_reason']] if release['blocked_reason'] else [])
   return {'forecast':current}
  quantity=number(body.get('quantity'),'quantity',1,400,True);fare=number(body.get('base_fare'),'base_fare',0,3000,True)
  row=next(r for r in data.history(flight) if r['days_to_departure']==day)
  # Member fares may never exceed 80% of the normal base fare visible at this release day.
  quote=next((r for r in sorted(data.history(flight),key=lambda r:r['days_to_departure']) if r['days_to_departure']>=day and r.get('normal_base_fare') is not None),None)
  if quote is None:raise ValueError('No observable normal base fare to cap the member fare')
  from .fare_policy import check_member_fare
  check_member_fare(fare,quote['normal_base_fare'])
  maxq=int(f.get('releasable',f.get('releasable_seats',f.get('max_member_seats',0))))
  if day==0:raise ValueError('Sales are closed')
  return {'offer':store().offer(flight,day,quantity,fare,row['mandatory_fees'] if row['mandatory_fees'] is not None else 250,maxq),'simulated':True}
 raise NotFound('Not found')

class Handler(BaseHTTPRequestHandler):
 def log_message(self,format,*args):pass
 def send_response_headers(self,status,ctype,length,filename='snapshots.csv.gz',extra_headers=None):
  self.send_response(status)
  for key,value in (extra_headers or {}).items():self.send_header(key,value)
  if ctype=='application/gzip':self.send_header('Content-Disposition',f'attachment; filename="{filename}"')
  if length is not None:self.send_header('Content-Length',str(length))
  self.send_header('Content-Type',ctype);self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Referrer-Policy','no-referrer');self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'");self.end_headers()
 def json(self,status,payload,extra_headers=None):
  content=json.dumps(payload,ensure_ascii=False,allow_nan=False,default=lambda x:x.item() if hasattr(x,'item') else str(x)).encode();self.send_response_headers(status,'application/json; charset=utf-8',len(content),extra_headers=extra_headers);self.wfile.write(content)
 def allowed_host(self):
  try:host=urlsplit('//'+self.headers.get('Host','')).hostname
  except ValueError:return False
  return host in ('127.0.0.1','localhost','::1')
 def do_GET(self):
  if not self.allowed_host():return self.json(403,{'error':'Local host only'})
  path=unquote(urlparse(self.path).path)
  try:
   if path=='/api/member-portal/session':return self.json(200,demo_auth.current(store(),self.headers.get('Cookie')))
   if path.startswith('/api/member-portal/accounts/'):
    demo_auth.authorize_account(store(),self.headers.get('Cookie'),ident(path.split('/')[-1]))
   if path=='/api/export/snapshots':
    payload=(data.DATA/'snapshots.csv.gz').read_bytes();self.send_response_headers(200,'application/gzip',len(payload));self.wfile.write(payload);return
   if path.startswith('/api/'):return self.json(200,get(path,parse_qs(urlparse(self.path).query)))
   aliases={'/admin':'index.html','/admin/':'index.html','/members':'members/index.html','/members/':'members/index.html',
            '/members/login':'members/login.html','/members/login/':'members/login.html',
            '/adaptive-pricing':'adaptive-pricing.html','/adaptive-pricing/':'adaptive-pricing.html'}
   root=(ROOT/'frontend').resolve();file=(root/aliases.get(path,path.lstrip('/') or 'index.html')).resolve()
   if root not in file.parents or not file.is_file():return self.json(404,{'error':'Not found'})
   payload=file.read_bytes();self.send_response_headers(200,mimetypes.guess_type(file.name)[0] or 'application/octet-stream',len(payload));self.wfile.write(payload)
  except EvidenceUnavailable as e:self.json(503,{'status':'unavailable','code':'evaluation_evidence_unavailable','artifact':e.artifact,'error':str(e)})
  except demo_auth.AuthError as e:self.json(e.status,{'error':str(e)})
  except NotFound as e:self.json(404,{'error':str(e)})
  except (ValueError,TypeError) as e:self.json(400,{'error':str(e)})
  except Exception:
   traceback.print_exc();self.json(500,{'error':'Server error; inspect local terminal'})
 def do_POST(self):
  if not self.allowed_host():return self.json(403,{'error':'Local host only'})
  origin=self.headers.get('Origin')
  if origin and origin not in (f'http://localhost:{self.server.server_port}',f'http://127.0.0.1:{self.server.server_port}'):return self.json(403,{'error':'Origin not allowed'})
  if self.headers.get('Content-Type','').split(';')[0]!='application/json':return self.json(415,{'error':'JSON required'})
  try:
   length=int(self.headers.get('Content-Length','0'))
   if not 0<length<=65536:raise ValueError('Invalid request size')
   body=json.loads(self.rfile.read(length))
   if not isinstance(body,dict):raise ValueError('JSON object required')
   path=urlparse(self.path).path
   if path=='/api/member-portal/login':
    result,cookie=demo_auth.login(store(),body,self.headers.get('Cookie'));return self.json(200,result,{'Set-Cookie':cookie})
   if path=='/api/member-portal/logout':
    result,cookie=demo_auth.logout(store(),self.headers.get('Cookie'));return self.json(200,result,{'Set-Cookie':cookie})
   if path in ('/api/member-portal/join','/api/member-portal/book'):
    demo_auth.authorize_account(store(),self.headers.get('Cookie'),ident(body.get('customer_id')))
   self.json(200,post(path,body))
  except demo_auth.AuthError as e:self.json(e.status,{'error':str(e)})
  except NotFound as e:self.json(404,{'error':str(e)})
  except (ValueError,TypeError) as e:self.json(400,{'error':str(e)})
  except Exception:
   traceback.print_exc();self.json(500,{'error':'Server error; inspect local terminal'})

class Server(ThreadingHTTPServer):
 # The stdlib default backlog of 5 resets bursts of concurrent requests.
 request_queue_size=128
 daemon_threads=True

if __name__=='__main__':
 import argparse
 p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=8000);p.add_argument('--host',choices=('127.0.0.1','0.0.0.0'),default='127.0.0.1');a=p.parse_args()
 adaptive_store.enable_published_experiments()
 store()
 print(f'UOption Fly Pass: http://127.0.0.1:{a.port}',flush=True)
 Server((a.host,a.port),Handler).serve_forever()

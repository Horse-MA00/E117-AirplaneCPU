"""Local same-origin application server. Run: python -m backend.server."""
import gzip,json,math,mimetypes,os,re,threading,traceback
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from urllib.parse import urlparse,unquote,parse_qs,urlsplit
from pathlib import Path
from functools import lru_cache
from . import data,market_jobs,pricing_jobs,member_portal
from .store import Store
from .evidence import EvidenceUnavailable,read_evaluation
from .errors import NotFound
from .oag import load_env
from llm_agent import runner,audit
from llm_agent.population import coverage,population
ROOT=Path(__file__).resolve().parents[1]; load_env()
_store=None

def store():
 global _store
 if _store is None:_store=Store(ROOT/'data/private/demo.sqlite3')
 return _store

def number(x,name,lo,hi,integer=False):
 if isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x) or not lo<=x<=hi or (integer and int(x)!=x):raise ValueError(f'{name} must be {lo}..{hi}')
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

def _optimization_get(optimization,parts,query):
 if len(parts)==4:return optimization.read(ident(parts[3]))
 if len(parts)==5 and parts[4]=='events':
  return optimization.events(ident(parts[3]),query_int(query,('limit',),100),query_int(query,('offset',),0))
 if len(parts)==5 and parts[4]=='export':return optimization.export_run(ident(parts[3]))
 raise NotFound('Optimization endpoint not found')

@lru_cache(maxsize=96)
def forecast_for(flight,day):
 from .nhpp import forecast
 return forecast(data.history(flight),days_to_departure=day,seed=117)

def get(path,query=None):
 if path=='/api/health':
  with store().connect() as connection:connection.execute('SELECT 1').fetchone()
  return {'status':'ok'}
 if path=='/api/optimization/runs':
  from . import optimization
  return {'runs':optimization.list_runs()}
 if path=='/api/optimization/suggestions':
  from .offer_suggestions import suggestions
  query=query or {}
  flight=ident(query.get('flight_id',[''])[0])
  day=query_int(query,('forecast_day','day'),28)
  return suggestions(flight,day,store(),forecast_for)
 if path.startswith('/api/optimization/runs/'):
  from . import optimization
  parts=path.strip('/').split('/')
  try:return _optimization_get(optimization,parts,query or {})
  except ValueError as e:
   # optimization_store is provenance-hashed, so translate its message here.
   if str(e)=='Optimization run not found':raise NotFound(str(e)) from None
   raise
 if path.startswith('/api/pricing/runs/'):
  return pricing_jobs.read(ident(path.split('/')[-1]))
 if path in ('/api/member-portal/config','/api/member-portal/plan'):return member_portal.config(store())
 if path=='/api/member-portal/flights':return member_portal.flights(store(),forecast_for)
 if path.startswith('/api/member-portal/accounts/'):
  if len(path.strip('/').split('/'))!=4:raise NotFound('Account endpoint not found')
  return member_portal.account(store(),ident(path.split('/')[-1]))
 if path=='/api/agents/panels':
  from . import panel_jobs
  return {'runs':panel_jobs.list_runs()}
 if path.startswith('/api/agents/panels/'):
  from . import panel_jobs
  parts=path.strip('/').split('/')
  try:
   if len(parts)==6 and parts[4]=='people':return panel_jobs.read_person(ident(parts[3]),ident(parts[5]))
   if len(parts)==4:return panel_jobs.read(ident(parts[3]))
  except ValueError as e:
   # panel_jobs is provenance-hashed (unfinished panels must stay resumable), so translate here.
   if str(e) in ('Panel not found','Panel traveller not found'):raise NotFound(str(e)) from None
   raise
  raise NotFound('Panel endpoint not found')
 if path=='/api/summary':return {'dataset':{'rows':data.manifest()['rows'],'catalog_rows':data.manifest().get('catalog_rows',data.manifest()['rows']),'flights':len(data.flights()),'source':'synthetic','manifest':data.manifest()},'model':'NHPP','llm':runner.status()}
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
  return {'model':'NHPP','llm':runner.status(),'oag':records,'simulated_booking':True}
 if path=='/api/flights':return {'flights':data.flights()}
 if path.startswith('/api/flights/'):
  id=ident(path.split('/')[-1]);rows=data.history(id);f=next(f for f in data.flights() if f['flight_id']==id)
  return {'flight':f,'history':rows}
 if path=='/api/personas':return coverage()|{'personas':population(100)}
 if path=='/api/agents/runs':return {'runs':audit.list_runs()}
 if path.startswith('/api/agents/runs/'):return audit.read_run(ident(path.split('/')[-1]))
 if path=='/api/market/runs':return {'runs':market_jobs.list_runs()}
 if path.startswith('/api/market/runs/'):
  parts=path.strip('/').split('/')
  if len(parts)==6 and parts[4]=='cases':return market_jobs.read_case(ident(parts[3]),ident(parts[5]))
  if len(parts)==4:return market_jobs.read(ident(parts[3]))
  raise NotFound('Market endpoint not found')
 if path=='/api/offers':return {'offers':store().offers()}
 raise NotFound('Not found')

_optimizer_lock=threading.Lock()
def post(path,body):
 if path=='/api/optimization/initial-policy':
  from .initial_policy import suggest
  return suggest(body)
 if path=='/api/optimization/runs':
  from . import optimization
  return optimization.start(body)
 if path.startswith('/api/optimization/runs/') and path.endswith('/resume'):
  from . import optimization
  parts=path.strip('/').split('/')
  if len(parts)==5:return optimization.resume(ident(parts[3]),body)
  raise NotFound('Optimization endpoint not found')
 if path=='/api/pricing/runs':return pricing_jobs.start(body)
 if path=='/api/member-portal/plan':
  store().plan(number(body.get('membership_fee'),'membership_fee',0,5000))
  return member_portal.config(store())
 if path=='/api/member-portal/join':
  expected=number(body['expected_fee'],'expected_fee',0,5000) if 'expected_fee' in body else None
  member=store().join_plan(ident(body.get('customer_id')),expected)
  return {'member':member,'simulated':True,'currency':'HKD'}
 if path=='/api/member-portal/book':
  expected=number(body['expected_total'],'expected_total',0,10000) if 'expected_total' in body else None
  return member_portal.book(store(),forecast_for,ident(body.get('customer_id')),ident(body.get('offer_id')),expected)
 if path=='/api/agents/panels':
  from . import panel_jobs
  return panel_jobs.start(body)
 if path.startswith('/api/agents/panels/') and path.endswith('/resume'):
  from . import panel_jobs
  parts=path.strip('/').split('/')
  if len(parts)==5:return panel_jobs.start(body,ident(parts[3]))
  raise NotFound('Panel endpoint not found')
 if path=='/api/market/runs':return market_jobs.start(body)
 if path.startswith('/api/market/runs/') and path.endswith('/resume'):
  parts=path.strip('/').split('/')
  if len(parts)==5:return market_jobs.start(body,ident(parts[3]))
  raise NotFound('Market endpoint not found')
 if path in ('/api/forecast','/api/optimize','/api/offers'):
  flight=ident(body.get('flight_id'));day=number(body.get('days_to_departure',28),'day',0,28,True)
  f=forecast_for(flight,day)
  if path=='/api/forecast':
   current=dict(f); release=store().release_status(flight,day,f['releasable_seats'])
   current['risk_release_ceiling']=f['releasable_seats']
   current['release_status']=release
   current['releasable_seats']=release['new_release_limit']
   current['committed_member_seats']=release['member_sold']+release['total_active_unsold']
   current['assumptions']=list(f['assumptions'])+['New member quota is issued once per round at D28, D14 and D7 only. Earlier valid unsold quotas carry forward; sold demo seats are accounted once.']+([release['blocked_reason']] if release['blocked_reason'] else [])
   return {'forecast':current}
  if path=='/api/optimize':
   from .pricing import optimize
   config=body.get('config',{})
   if not isinstance(config,dict):raise ValueError('config must be an object')
   if not _optimizer_lock.acquire(False):raise ValueError('An optimization is already running; retry after it finishes')
   try:return optimize(f,config)
   finally:_optimizer_lock.release()
  quantity=number(body.get('quantity'),'quantity',1,400,True);fare=number(body.get('base_fare'),'base_fare',0,3000)
  row=next(r for r in data.history(flight) if r['days_to_departure']==day)
  maxq=int(f.get('releasable',f.get('releasable_seats',f.get('max_member_seats',0))))
  if day==0:raise ValueError('Sales are closed')
  from .offer_suggestions import validate_draft
  # Bind the optimization check to the already-validated values, never raw body fields.
  suggestion=validate_draft({**body,'flight_id':flight,'days_to_departure':day,'quantity':quantity,'base_fare':fare},store(),forecast_for)
  return {'offer':store().offer(flight,day,quantity,fare,row['mandatory_fees'] if row['mandatory_fees'] is not None else 250,maxq,expected_plan_fee=suggestion['membership_fee'] if suggestion else None),'simulated':True}
 if path=='/api/agents/run':
  mode=body.get('mode','deterministic')
  return runner.run(mode=mode,count=number(body.get('count',5 if mode=='live' else 14),'count',1,5 if mode=='live' else 100,True),membership_fee=body.get('membership_fee',399),member_fare=body.get('member_fare',70),scenario_mode='journey')
 if path=='/api/members':return {'member':store().join_plan(ident(body.get('customer_id'))),'simulated':True}
 if path=='/api/bookings':
  # Admin/smoke-test booking. It may not move the simulation clock: only an
  # issued release round advances time, exactly as on the member site.
  offer=store().offer_info(ident(body.get('offer_id')))
  day=number(body.get('days_to_departure',offer['sim_day']),'day',0,28,True)
  if day!=offer['sim_day']:raise ValueError(f"Bookings use the current simulation day D{offer['sim_day']}; publish a release round to advance time")
  expected=number(body['expected_total'],'expected_total',0,10000) if 'expected_total' in body else None
  return member_portal.book(store(),forecast_for,ident(body.get('customer_id')),offer['id'],expected)
 raise NotFound('Not found')

class Handler(BaseHTTPRequestHandler):
 def log_message(self,format,*args):pass
 def send_response_headers(self,status,ctype,length,filename='snapshots.csv.gz'):
  self.send_response(status)
  if ctype=='application/gzip':self.send_header('Content-Disposition',f'attachment; filename="{filename}"')
  if length is not None:self.send_header('Content-Length',str(length))
  self.send_header('Content-Type',ctype);self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Referrer-Policy','no-referrer');self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'");self.end_headers()
 def json(self,status,payload):
  content=json.dumps(payload,ensure_ascii=False,allow_nan=False,default=lambda x:x.item() if hasattr(x,'item') else str(x)).encode();self.send_response_headers(status,'application/json; charset=utf-8',len(content));self.wfile.write(content)
 def allowed_host(self):
  try:host=urlsplit('//'+self.headers.get('Host','')).hostname
  except ValueError:return False
  return host in ('127.0.0.1','localhost','::1')
 def do_GET(self):
  if not self.allowed_host():return self.json(403,{'error':'Local host only'})
  path=unquote(urlparse(self.path).path)
  try:
   if path=='/api/export/snapshots':
    payload=(data.DATA/'snapshots.csv.gz').read_bytes();self.send_response_headers(200,'application/gzip',len(payload));self.wfile.write(payload);return
   parts=path.strip('/').split('/')
   if len(parts)==5 and parts[:3]==['api','agents','runs'] and parts[-1]=='export':
    run_id=ident(parts[3]);source=audit.BASE/run_id/'events.jsonl'
    if not source.is_file():raise NotFound('Audit not found')
    remaining=source.stat().st_size
    self.close_connection=True
    self.send_response_headers(200,'application/gzip',None,filename=run_id+'.jsonl.gz')
    with source.open('rb') as handle,gzip.GzipFile(filename='',mode='wb',fileobj=self.wfile,mtime=0) as compressed:
     while remaining:
      line=handle.readline(remaining)
      if not line:break
      remaining-=len(line)
      # A live append may have been incomplete at the size snapshot.
      # Export only complete JSONL records; later downloads include the rest.
      if not line.endswith(b'\n'):break
      compressed.write(line)
    return
   if path.startswith('/api/'):return self.json(200,get(path,parse_qs(urlparse(self.path).query)))
   aliases={'/admin':'index.html','/admin/':'index.html','/members':'members/index.html','/members/':'members/index.html'}
   root=(ROOT/'frontend').resolve();file=(root/aliases.get(path,path.lstrip('/') or 'index.html')).resolve()
   if root not in file.parents or not file.is_file():return self.json(404,{'error':'Not found'})
   payload=file.read_bytes();self.send_response_headers(200,mimetypes.guess_type(file.name)[0] or 'application/octet-stream',len(payload));self.wfile.write(payload)
  except EvidenceUnavailable as e:self.json(503,{'status':'unavailable','code':'evaluation_evidence_unavailable','artifact':e.artifact,'error':str(e)})
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
   self.json(200,post(urlparse(self.path).path,body))
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
 p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=8000);p.add_argument('--host',choices=('127.0.0.1','0.0.0.0'),default='127.0.0.1');a=p.parse_args();store()
 print(f'UOption Fly Pass: http://127.0.0.1:{a.port}',flush=True)
 Server((a.host,a.port),Handler).serve_forever()

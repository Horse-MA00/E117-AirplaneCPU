"""Local same-origin application server. Run: python -m backend.server."""
import json,math,mimetypes,os,re,threading,traceback
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from urllib.parse import urlparse,unquote
from pathlib import Path
from functools import lru_cache
from . import data
from .store import Store
from .oag import load_env
from llm_agent import runner
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

@lru_cache(maxsize=96)
def forecast_for(flight,day):
 from .nhpp import forecast
 return forecast(data.history(flight),days_to_departure=day,seed=117)

def get(path):
 if path=='/api/summary':return {'dataset':{'rows':200000,'flights':len(data.flights()),'source':'synthetic','manifest':data.manifest()},'model':'NHPP','llm':runner.status()}
 if path=='/api/evaluation':
  p=ROOT/'simulation/generated/nhpp_evaluation.json'
  return json.loads(p.read_text()) if p.exists() else {'status':'pending'}
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
 if path=='/api/offers':return {'offers':store().offers()}
 raise KeyError('Not found')

_optimizer_lock=threading.Lock()
def post(path,body):
 if path in ('/api/forecast','/api/optimize','/api/offers'):
  flight=ident(body.get('flight_id'));day=number(body.get('days_to_departure',28),'day',0,28,True)
  f=forecast_for(flight,day)
  if path=='/api/forecast':return {'forecast':f}
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
  return {'offer':store().offer(flight,day,quantity,fare,row['mandatory_fees'] if row['mandatory_fees'] is not None else 250,maxq),'simulated':True}
 if path=='/api/agents/run':return runner.run(mode=body.get('mode','deterministic'),count=number(body.get('count',14),'count',1,100,True),membership_fee=body.get('membership_fee',399),member_fare=body.get('member_fare',70))
 if path=='/api/members':return {'member':store().member(ident(body.get('customer_id')),number(body.get('membership_fee',399),'membership_fee',0,10000)),'simulated':True}
 if path=='/api/bookings':return store().book(body.get('offer_id'),ident(body.get('customer_id')))
 raise KeyError('Not found')

class Handler(BaseHTTPRequestHandler):
 def log_message(self,format,*args):pass
 def headers(self,status,ctype,length):
  self.send_response(status);self.send_header('Content-Type',ctype);self.send_header('Content-Length',str(length));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Referrer-Policy','no-referrer');self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'");self.end_headers()
 def json(self,status,payload):
  content=json.dumps(payload,ensure_ascii=False,allow_nan=False,default=lambda x:x.item() if hasattr(x,'item') else str(x)).encode();self.headers(status,'application/json; charset=utf-8',len(content));self.wfile.write(content)
 def allowed_host(self):
  host=self.headers.get('Host','').split(':')[0]
  return host in ('127.0.0.1','localhost','[::1]')
 def do_GET(self):
  if not self.allowed_host():return self.json(403,{'error':'Local host only'})
  path=unquote(urlparse(self.path).path)
  try:
   if path=='/api/export/snapshots':
    payload=(data.DATA/'snapshots.csv.gz').read_bytes();self.headers(200,'application/gzip',len(payload));self.wfile.write(payload);return
   if path.startswith('/api/'):return self.json(200,get(path))
   root=(ROOT/'frontend').resolve();file=(root/(path.lstrip('/') or 'index.html')).resolve()
   if root not in file.parents or not file.is_file():return self.json(404,{'error':'Not found'})
   payload=file.read_bytes();self.headers(200,mimetypes.guess_type(file.name)[0] or 'application/octet-stream',len(payload));self.wfile.write(payload)
  except (KeyError,ValueError) as e:self.json(404,{'error':str(e)})
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
  except KeyError:self.json(404,{'error':'Not found'})
  except (ValueError,TypeError) as e:self.json(400,{'error':str(e)})
  except Exception:
   traceback.print_exc();self.json(500,{'error':'Server error; inspect local terminal'})

if __name__=='__main__':
 import argparse
 p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=8000);a=p.parse_args();store()
 print(f'UOption Fly Pass: http://127.0.0.1:{a.port}',flush=True)
 ThreadingHTTPServer(('127.0.0.1',a.port),Handler).serve_forever()

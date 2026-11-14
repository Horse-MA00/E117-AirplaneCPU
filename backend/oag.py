"""Small server-only, cached OAG integration. Licensed raw data stays private."""
import json,os,urllib.request,urllib.parse,urllib.error
from pathlib import Path
from datetime import datetime,timezone
from llm_agent.provider_transport import NoRedirect
ROOT=Path(__file__).resolve().parents[1]

def load_env():
    p=ROOT/'.env.local'
    if p.exists():
        for line in p.read_text().splitlines():
            if '=' in line and not line.lstrip().startswith('#'):
                k,v=line.split('=',1); os.environ.setdefault(k.strip(),v.strip().strip('\"').strip("'"))

def fetch(date='2026-11-15', refresh=False):
    from datetime import date as dt
    dt.fromisoformat(date)
    load_env(); target=ROOT/'data/private'/f'oag-{date}.json'; target.parent.mkdir(parents=True,exist_ok=True)
    if target.exists() and not refresh:return json.loads(target.read_text())
    keys=[os.environ.get(x) for x in ('OAG_FLIGHT_INFO_KEY','OAG_FLIGHT_INFO_FALLBACK_KEY') if os.environ.get(x)]
    status={'source':'oag_flight_info','date':date,'attempts':[],'records':[], 'limitation':'Schedules/capacity only; no booking history or airfare.'}
    params={'CarrierCode':'UO','DepartureAirport':'HKG','DepartureDateTime':date,'Content':'SEATS','CodeType':'IATA','Codeshare':'OPERATING','Limit':10,'version':'v2'}
    for key in keys:
        request=urllib.request.Request('https://api.oag.com/flight-instances/?'+urllib.parse.urlencode(params),headers={'Subscription-Key':key,'Accept':'application/json'})
        try:
            with urllib.request.build_opener(NoRedirect()).open(request,timeout=20) as response:
                raw=json.load(response)
            records=raw.get('data',[]) if isinstance(raw,dict) else raw
            status.update(state='available',records=records,fetched_at=datetime.now(timezone.utc).isoformat())
            status['attempts'].append({'status':200}); break
        except urllib.error.HTTPError as err:
            status['attempts'].append({'status':err.code})
            if err.code==429:break  # Never rotate credentials to bypass a quota.
            if err.code not in (401,403):break
        except (urllib.error.URLError,TimeoutError,ValueError):
            status['attempts'].append({'status':'network_or_response_error'}); break
    status.setdefault('state','unavailable' if keys else 'not_configured')
    target.write_text(json.dumps(status,ensure_ascii=False,indent=2));target.chmod(0o600)
    return status

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--date',default='2026-11-15');p.add_argument('--refresh',action='store_true');a=p.parse_args()
    r=fetch(a.date,a.refresh)
    print(json.dumps({k:r[k] for k in ('state','date','attempts','limitation')}|{'record_count':len(r['records'])}))

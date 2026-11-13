"""Provider-independent Chat Completions adapter with auditable deterministic fallback."""
import json, os, urllib.request, urllib.error, math, hashlib
from pathlib import Path
from .population import population,coverage
PROMPT=Path(__file__).parent/'prompts/customer_system.txt'

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, 'Redirect disabled for authenticated request', headers, fp)

def _open(request):
    return urllib.request.build_opener(NoRedirect()).open(request,timeout=30)

def status():
    return dict(live_configured=all(os.environ.get(k) for k in ('LLM_API_URL','LLM_API_KEY','LLM_MODEL')),
                default_mode='deterministic',prompt_version='customer-v1',coverage=coverage())

def scenario(person, fee=399, fare=70, mandatory=250):
    return dict(person=person,stage='subscription',membership_term_days=365,membership_fee=fee,
      regular_total=850,member_base_fare=fare,mandatory_fees=mandatory,member_total=fare+mandatory,
      source='assumed_scenario',allowed_actions=['JOIN_PASS','DECLINE'],options=[{'id':'pass','term_days':365,'price':fee}],
      rules=['No guaranteed availability','No real payment or ticketing','No renewal assumed'])

def validate(result, context):
    if not isinstance(result,dict) or result.get('action') not in context['allowed_actions']: raise ValueError('Agent returned an illegal action')
    if result.get('option_id') not in [None]+[x['id'] for x in context['options']]:raise ValueError('Unknown option')
    if result['action']=='JOIN_PASS':
        if result.get('option_id')!='pass':raise ValueError('Joining requires pass option')
        if context['membership_fee']>context['person']['total_budget']:raise ValueError('Insufficient budget')
    if result['action'] in ('BUY_MEMBER','BUY_REGULAR'):
        option=next((o for o in context['options'] if o['id']==result.get('option_id')),None)
        if not option or option['action']!=result['action'] or option['price']>context['person']['total_budget']:raise ValueError('Illegal purchase or insufficient budget')
    return {k:str(result.get(k,''))[:600] if k in ('reason','reason_code') else result.get(k) for k in ('action','option_id','reason_code','reason')}

def deterministic(context):
    p=context['person']; benefit=p['expected_trips']*p['perceived_availability']*max(0,context['regular_total']-context['member_total'])
    join=p['route_match'] and benefit>context['membership_fee'] and p['total_budget']>=context['membership_fee']+context['member_total']
    return dict(action='JOIN_PASS' if join else 'DECLINE',option_id='pass' if join else None,
      reason_code='EXPECTED_VALUE' if join else 'LIMITED_VALUE',reason='預期可用航班的節省高於會費。' if join else '在這組出行頻次、可用性與總預算假設下，會員不值得。')

def live(context):
    if not status()['live_configured']:raise ValueError('Live LLM is not configured. Set LLM_API_URL, LLM_API_KEY and LLM_MODEL on the server.')
    url=os.environ['LLM_API_URL']
    if not url.startswith('https://'):raise ValueError('Live provider requires HTTPS')
    body={'model':os.environ['LLM_MODEL'],'messages':[{'role':'system','content':PROMPT.read_text()},{'role':'user','content':json.dumps(context,ensure_ascii=False)}],'temperature':0,'max_tokens':350,'response_format':{'type':'json_object'}}
    cache_dir=Path(__file__).resolve().parents[1]/'data/private/llm_cache'; cache_dir.mkdir(parents=True,exist_ok=True)
    cache=cache_dir/(hashlib.sha256((url+json.dumps(body,sort_keys=True)).encode()).hexdigest()+'.json')
    if cache.exists():return json.loads(cache.read_text())
    request=urllib.request.Request(url,data=json.dumps(body).encode(),headers={'Authorization':'Bearer '+os.environ['LLM_API_KEY'],'Content-Type':'application/json'})
    try:
        with _open(request) as response: raw=json.load(response)
        result=json.loads(raw['choices'][0]['message']['content']);validate(result,context)
        cache.write_text(json.dumps(result,ensure_ascii=False));return result
    except (urllib.error.URLError,TimeoutError,IndexError,TypeError,KeyError,json.JSONDecodeError) as e:
        raise ValueError('LLM provider failed or returned invalid JSON; no simulated result was substituted.') from None

def run(mode='deterministic',count=14,seed=117,membership_fee=399,member_fare=70,scenario_mode='legacy'):
    if scenario_mode=='journey':
        from .journey_runner import run_journey
        return run_journey(mode,count,seed,membership_fee,member_fare)
    if scenario_mode!='legacy':raise ValueError('Unknown scenario mode')
    if mode not in ('deterministic','live'):raise ValueError('Unknown agent mode')
    limit=5 if mode=='live' else 100
    if not isinstance(count,int) or not 1<=count<=limit:raise ValueError(f'count must be 1..{limit} for this mode')
    for value in (membership_fee,member_fare):
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not 0<=value<=10000:raise ValueError('Invalid price')
    results=[]
    for person in population(count,seed):
        context=scenario(person,membership_fee,member_fare); decision=validate(live(context) if mode=='live' else deterministic(context),context)
        member=decision['action']=='JOIN_PASS'
        remaining=dict(person,total_budget=person['total_budget']-(membership_fee if member else 0),membership_active=member)
        booking_context={'person':remaining,'stage':'booking','days_to_departure':14,'source':'assumed_scenario','allowed_actions':['DECLINE'],'options':[]}
        if person['route_match'] and person['minimum_notice_days']<=14:
            options=[{'id':'regular','action':'BUY_REGULAR','price':context['regular_total']*person['party_size']}]
            if member and person['party_size']==1:options.append({'id':'member','action':'BUY_MEMBER','price':context['member_total']})
            booking_context['options']=[o for o in options if o['price']<=remaining['total_budget']]
            booking_context['allowed_actions'] += [o['action'] for o in booking_context['options']]
        if mode=='live': booking=validate(live(booking_context),booking_context)
        elif booking_context['options']:
            chosen=min(booking_context['options'],key=lambda o:o['price'])
            booking=validate({'action':chosen['action'],'option_id':chosen['id'],'reason_code':'FEASIBLE_PRICE','reason':'符合日期、預算和會員資格的較低總價選項。'},booking_context)
        else:booking={'action':'DECLINE','option_id':None,'reason_code':'NO_FEASIBLE_OPTION','reason':'沒有符合預算、同行人數或安排時間的選項。'}
        booking.update(source='llm_simulated' if mode=='live' else 'deterministic_assumption',inventory_committed=False)
        results.append(dict(person=person,context=context,decision=decision,booking_context=booking_context,booking_decision=booking))
    return dict(mode=mode,source='llm_simulated' if mode=='live' else 'deterministic_assumption',prompt_version='customer-v1',results=results,
      summary={'customers':len(results),'joined':sum(x['decision']['action']=='JOIN_PASS' for x in results)},
      limitations=['This panel audits individual decisions; pricing search uses the explicitly labelled mathematical market.','Live subscription and booking decisions both require provider credentials. Party members require separate eligibility; no group member discount is assumed.'])

"""Member-only, single-flight price learning with auditable parallel intentions.

The entire panel receives one simultaneous quote. LLM calls can run in parallel;
only the deterministic clearing engine changes inventory. Each price is a fresh
counterfactual market, not another charge against the previous round's wallet.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import threading
import time
import uuid

import numpy as np

from . import adaptive_store as store
from .fare_policy import member_fare_cap
from .initial_policy import flight_scope
from .thompson import PurchasePosterior, recommend
from llm_agent.adaptive_customers import DecisionClient
from llm_agent.weighted_population import population, metadata
from llm_agent.file_lock import exclusive_lock

VERSION = 'member-thompson-v2-replay'
ROOT = Path(__file__).resolve().parents[1]
_active = set()
_guard = threading.Lock()


def _number(body, key, default, low, high, integer=False):
    value = body.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f'{key} must be a finite number')
    if not low <= value <= high or (integer and int(value) != value):
        raise ValueError(f'{key} must be {low}..{high}')
    return int(value) if integer else float(value)


def status():
    secondary = ROOT/'data/private/adaptive-secondary.key'
    if secondary.is_file() and not os.environ.get('LLM_API_KEY_SECONDARY'):
        os.environ['LLM_API_KEY_SECONDARY'] = secondary.read_text().strip()
    return {'version':VERSION, 'live_configured':all(os.environ.get(k) for k in ('LLM_API_URL','LLM_API_KEY','LLM_MODEL')),
            'model':os.environ.get('LLM_MODEL'), 'population':metadata(),
            'member_fare_cap_ratio':.8, 'simulated':True,
            'scenario':'Existing members, one base-fare seat per member, simultaneous purchase intentions.'}


def scope(body):
    if not isinstance(body, dict):
        raise ValueError('JSON object required')
    result = flight_scope(body.get('flight_id'), body.get('forecast_day', 28))
    return {'scope':{k:v for k,v in result.items() if k != 'history'}, 'population':metadata(body.get('weights'))}


def validate(body):
    if not isinstance(body, dict):
        raise ValueError('JSON object required')
    mode = body.get('mode', 'synthetic')
    if mode not in ('synthetic', 'live'):
        raise ValueError('mode must be synthetic or live')
    cfg = {'mode':mode, 'rounds':_number(body,'rounds',10,2,30,True),
           'customers':_number(body,'customers',28,14,200,True),
           'concurrency':_number(body,'concurrency',4,1,8,True),
           'max_calls':_number(body,'max_calls',600,0,10000,True),
           'seed':_number(body,'seed',117,0,100000000,True),
           'validation_repeats':_number(body,'validation_repeats',2,2,8,True),
           'revenue_fraction':_number(body,'revenue_fraction',.95,.5,1),
           'flight_id':body.get('flight_id'), 'forecast_day':body.get('forecast_day',28),
           'weights':body.get('weights')}
    meta = metadata(cfg['weights'])
    selected = flight_scope(cfg['flight_id'], cfg['forecast_day'])
    if selected['releasable_seats'] < 1 or member_fare_cap(selected['normal_base_fare']) < .01:
        raise ValueError('This snapshot has no positive-price member inventory. Choose another flight or release day.')
    cfg['estimated_calls_upper_bound'] = cfg['rounds']*(cfg['customers']+1)+(1+3*cfg['validation_repeats'])*cfg['customers']
    if mode == 'live' and cfg['max_calls'] < cfg['estimated_calls_upper_bound']:
        raise ValueError(f"max_calls must cover this complete experiment's upper bound of {cfg['estimated_calls_upper_bound']} calls; reduce rounds/customers or increase the explicit budget")
    if mode == 'live' and not status()['live_configured']:
        raise ValueError('Live provider is not configured')
    return cfg, selected, meta


def _provenance():
    paths = ['backend/adaptive_pricing.py','backend/adaptive_store.py','backend/thompson.py',
             'backend/nhpp.py','backend/fare_policy.py','backend/initial_policy.py','backend/release_policy.py',
             'backend/data.py','llm_agent/weighted_population.py','llm_agent/adaptive_customers.py',
             'llm_agent/prompts/adaptive_customer_v1_en.txt','llm_agent/prompts/adaptive_analyst_v1_en.txt']
    paths += [str(p.relative_to(ROOT)) for p in (ROOT/'simulation').glob('*/manifest.json')]
    from urllib.parse import urlsplit
    return {'files':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths},
            'model':os.environ.get('LLM_MODEL'), 'customer_data':'synthetic_only',
            'provider_host':urlsplit(os.environ.get('LLM_API_URL','')).hostname,
            'weight_source':'assumed_scenario_weights_not_observed_market_shares'}


def observations(people, selected, price):
    flight = {k:selected[k] for k in ('flight_id','origin','destination','departure_date','departure_time','as_of_day')}
    return [{'person':p, 'flight':flight, 'member_fare':price,
             'normal_fare':selected['normal_base_fare'], 'quota':selected['releasable_seats'] if price is not None else 0}
            for p in people]


def settle(people, decisions, selected, price, seed):
    """Settle intentions once, in a fixed random priority order, using integer seats/cents."""
    if len(people) != len(decisions):
        raise ValueError('Every panel member must have exactly one decision')
    normal_cents = round(selected['normal_base_fare']*100)
    member_cents = None if price is None else round(price*100)
    quota = min(selected['releasable_seats'], selected['available_seats']) if price is not None else 0
    remaining = int(selected['available_seats'])
    initial_quota = int(quota)
    order = np.random.default_rng(seed).permutation(len(people))
    executions = [None]*len(people)
    for index in order:
        person, record = people[index], decisions[index]
        decision = record['decision']
        action = decision['action']
        budget = round(person['base_fare_budget']*100)
        if not person['eligible'] and action != 'DECLINE':
            raise ValueError('Ineligible purchase intention')
        requested = action
        denied = None
        if action == 'BUY_MEMBER':
            if member_cents is None or budget < member_cents:
                raise ValueError('Invalid or unaffordable member purchase')
            if quota <= 0 or remaining <= 0:
                denied = 'member_inventory_exhausted'
                action = decision.get('fallback_action','DECLINE')
                if action not in ('BUY_REGULAR','DECLINE'):
                    raise ValueError('Invalid inventory fallback')
        if action == 'BUY_REGULAR' and budget < normal_cents:
            raise ValueError('Unaffordable regular purchase')
        if action in ('BUY_MEMBER','BUY_REGULAR') and remaining <= 0:
            denied = 'physical_inventory_exhausted'
            action = 'DECLINE'
        paid = 0
        if action == 'BUY_MEMBER':
            remaining -= 1
            quota -= 1
            paid = member_cents
        elif action == 'BUY_REGULAR':
            remaining -= 1
            paid = normal_cents
        elif action != 'DECLINE':
            raise ValueError('Unknown terminal action')
        executions[index] = {'customer_id':person['customer_id'],'segment':person['segment'],
            'requested_action':requested,'action':action,'base_fare':paid/100,
            'inventory_denial':denied,'population_weight':person['population_weight']}
    member = [x for x in executions if x['action']=='BUY_MEMBER']
    regular = [x for x in executions if x['action']=='BUY_REGULAR']
    weights = [float(p['population_weight']) for p in people]
    weighted_intent = sum(w for w,r in zip(weights,decisions) if r['decision']['action']=='BUY_MEMBER')
    weighted_member = sum(x['population_weight'] for x in member)
    weighted_regular = sum(x['population_weight'] for x in regular)
    n = len(people)
    # Weighted metrics are estimates for the target customer mix. They NEVER
    # debit inventory or create fractional receipts in the actual panel ledger.
    weighted_revenue = n*sum(x['population_weight']*x['base_fare'] for x in executions)
    revenue = sum(round(x['base_fare']*100) for x in executions)/100
    return {'member_buyers':len(member),'regular_buyers':len(regular),'buyers':len(member)+len(regular),
            'member_revenue':sum(round(x['base_fare']*100) for x in member)/100,
            'regular_revenue':sum(round(x['base_fare']*100) for x in regular)/100,
            'revenue':revenue,'weighted_revenue':round(weighted_revenue,4),
            'weighted_member_revenue':round(n*weighted_member*(price or 0),4),
            'weighted_conversion':weighted_intent,'weighted_fulfilled_conversion':weighted_member,
            'weighted_buyers':n*(weighted_member+weighted_regular),
            'member_intents':sum(r['decision']['action']=='BUY_MEMBER' for r in decisions),
            'quota':initial_quota,'remaining_quota':int(quota),'remaining_seats':remaining,
            'inventory_denials':sum(x['inventory_denial'] is not None for x in executions),
            'capacity_binding':any(x['inventory_denial'] is not None for x in executions),
            'executions':executions,
            'accounting':'Base ticket receipts only; no membership fee, tax, fuel surcharge or operating costs.'}


def evaluate(client, people, selected, price, seed):
    records = client.choose_many(observations(people, selected, price))
    result = settle(people, records, selected, price, seed)
    result['decisions'] = [{**r,'person':p,'settlement':execution}
                           for p,r,execution in zip(people,records,result['executions'])]
    return result


def _interval(values, seed):
    """Descriptive paired-world bootstrap, never a human-market confidence claim."""
    if not values:
        return None
    arr = np.asarray(values,float)
    rng = np.random.default_rng(seed)
    means = rng.choice(arr, size=(2000,len(arr)), replace=True).mean(axis=1)
    return {'low':round(float(np.quantile(means,.025)),4),'high':round(float(np.quantile(means,.975)),4),
            'worlds':len(values),'method':'paired_world_bootstrap_descriptive',
            'warning':'Few synthetic worlds; this is not an airline revenue confidence interval.'}


def compare_validation(worlds, initial_price, selected_price, seed):
    comparisons = []
    for name, price in [('initial',initial_price),('selected',selected_price),('no_offer',None)]:
        rows = [w['result'] for w in worlds if w['policy']==name]
        mean = lambda key: float(np.mean([r[key] for r in rows]))
        comparisons.append({'policy':name,'price':price,'mean_buyers':mean('buyers'),
            'mean_weighted_buyers':mean('weighted_buyers'),
            'mean_member_buyers':mean('member_buyers'),'mean_revenue':mean('revenue'),
            'mean_member_revenue':mean('member_revenue'),'mean_weighted_revenue':mean('weighted_revenue'),
            'mean_weighted_conversion':mean('weighted_fulfilled_conversion')})
    by = {(w['seed'],w['policy']):w['result'] for w in worlds}
    seeds = sorted({w['seed'] for w in worlds})
    initial_deltas = [by[s,'selected']['revenue']-by[s,'initial']['revenue'] for s in seeds]
    baseline_deltas = [by[s,'selected']['revenue']-by[s,'no_offer']['revenue'] for s in seeds]
    weighted_deltas = [by[s,'selected']['weighted_revenue']-by[s,'initial']['weighted_revenue'] for s in seeds]
    weighted_baseline = [by[s,'selected']['weighted_revenue']-by[s,'no_offer']['weighted_revenue'] for s in seeds]
    member_deltas = [by[s,'selected']['member_revenue']-by[s,'initial']['member_revenue'] for s in seeds]
    mean = lambda xs:round(float(np.mean(xs)),4)
    binding = any(w['result']['capacity_binding'] for w in worlds)
    gain, extra = (mean(initial_deltas), mean(baseline_deltas)) if binding else (mean(weighted_deltas), mean(weighted_baseline))
    decision = ('REJECT_OFFER' if extra <= 0 else 'IMPROVED_IN_TEST' if gain > 0 else
                'KEEP_INITIAL' if abs(gain) < .005 else 'DID_NOT_IMPROVE')
    return {'comparisons':comparisons,'delta_vs_initial':mean(initial_deltas),'delta_vs_no_offer':mean(baseline_deltas),
            'weighted_delta_vs_initial':mean(weighted_deltas),'member_revenue_delta':mean(member_deltas),
            'weighted_delta_vs_no_offer':mean(weighted_baseline),
            'weighted_initial_delta_interval':_interval(weighted_deltas,seed+2),
            'decision_basis':'actual_capacity_constrained_panel' if binding else 'poststratified_target_mix',
            'decision_gain_vs_initial':gain,'decision_gain_vs_no_offer':extra,
            'initial_delta_interval':_interval(initial_deltas,seed),'no_offer_delta_interval':_interval(baseline_deltas,seed+1),
            'decision':decision,'selected_price_frozen_before_validation':True,
            'capacity_binding':binding,
            'scope':'One purchase opportunity per member at the chosen flight snapshot, not annual membership profit.',
            'caveat':'Classification is a descriptive simulation result, not a statistical proof of superiority.'}


def _worker(run):
    cfg, selected = run['config'], run['scope']
    run_id = run['run_id']
    client = None
    try:
        store.BASE.mkdir(parents=True,exist_ok=True)
        with exclusive_lock(store.BASE/'active.lock'):
            run['status'] = 'running'
            store.save(run)
            client = DecisionClient(mode=cfg['mode'], max_calls=cfg['max_calls'], concurrency=cfg['concurrency'],
                                    audit_callback=lambda record:store.record(run_id,record), seed=cfg['seed'],use_cache=True)
            people = population(cfg['customers'],cfg['seed'],weights=cfg['weights'],scope=selected)
            run['panel'] = people
            run['population'] = metadata(cfg['weights'],people)
            rng = np.random.default_rng(cfg['seed']+1907)
            model = PurchasePosterior([s['id'] for s in run['population']['segments']])
            rows = []
            seen_exposures, analyses_by_price = set(), {}
            run['progress']['phase'] = 'search_control'
            store.save(run)
            control = evaluate(client,people,selected,None,cfg['seed'])
            run['search_control'] = control
            store.record(run_id,{'event':'market_completed','phase':'search_control','result':control})
            for i in range(cfg['rounds']):
                run['progress'].update(phase='search',active_round=i+1)
                store.save(run)
                proposal = recommend(model,people,selected['normal_base_fare'],selected['releasable_seats'],rng,
                                     draw=True,revenue_fraction=cfg['revenue_fraction'])
                price = selected['initial_member_fare'] if i == 0 else proposal['price']
                if not 0 <= price <= member_fare_cap(selected['normal_base_fare']):
                    raise ValueError('Model proposed a price outside the 80% cap')
                result = evaluate(client,people,selected,price,cfg['seed'])
                learning_updates = 0
                for person, record in zip(people,result['decisions']):
                    # Simultaneous BUY_MEMBER is demand intent, even if clearing
                    # later rations the seat. Ineligibility is not price rejection.
                    exposure = (person['customer_id'],round(price*100))
                    if person['eligible'] and exposure not in seen_exposures:
                        seen_exposures.add(exposure)
                        learning_updates += 1
                        rows.append({'person':person,'price':price,'normal_fare':selected['normal_base_fare'],
                                     'bought':record['decision']['action']=='BUY_MEMBER',
                                     'sample_weight':person['population_weight']*cfg['customers']})
                model.fit(rows)
                feedback = [{'customer_id':r['person']['customer_id'],'decision':r['decision']} for r in result['decisions']]
                reused_analysis = price in analyses_by_price
                if reused_analysis:
                    analysis = analyses_by_price[price]
                else:
                    analysis = client.analyse({'round':i+1,'price':price,'metrics':{k:v for k,v in result.items() if k not in ('decisions','executions')},
                                               'feedback':feedback})
                    analyses_by_price[price] = analysis
                curve = []
                for point in proposal['curve']:
                    point = dict(point)
                    point.setdefault('expected_revenue',point.get('expected_member_revenue'))
                    curve.append(point)
                entry = {'round':i+1,'price':price,**result,'analysis':analysis.get('analysis',{}),
                         'analysis_source':'reused_no_new_observations' if reused_analysis else analysis.get('source'),
                         'learning_updates':learning_updates,'reused_analysis':reused_analysis,
                         'proposal':{k:v for k,v in proposal.items() if k!='curve'},
                         'curve':curve,'selection':'initial_80pct_cap' if i==0 else 'thompson_sample',
                         'delta_vs_no_offer':round(result['revenue']-control['revenue'],2),
                         'posterior':model.summary()}
                run['rounds'].append(entry)
                run['counts'] = client.stats()
                run['progress']['completed_rounds'] = i+1
                store.record(run_id,{'event':'round_completed','round':i+1,'price':price,'posterior':model.summary()})
                store.save(run)
            # Freeze selection using training data only. The final random draw
            # is never automatically published as the recommended price.
            final = recommend(model,people,selected['normal_base_fare'],selected['releasable_seats'],rng,
                              draw=False,revenue_fraction=cfg['revenue_fraction'],
                              candidate_prices=sorted({r['price'] for r in run['rounds']}))
            chosen = final['price']
            full_curve = recommend(model,people,selected['normal_base_fare'],selected['releasable_seats'],
                                   np.random.default_rng(cfg['seed']+900019),draw=False,
                                   revenue_fraction=cfg['revenue_fraction'])['curve']
            run['recommendation'] = {'price':chosen,'selection':'max_buyers_within_revenue_fraction',
                'revenue_fraction':cfg['revenue_fraction'], 'reason':'Posterior prediction over tested prices; selection frozen before independent validation.',
                'posterior':model.summary(),'curve':final['curve'],'model_curve':full_curve}
            run['progress']['phase'] = 'independent_validation'
            store.save(run)
            worlds = []
            for j in range(cfg['validation_repeats']):
                validation_seed = cfg['seed']+500003+1009*j
                heldout = population(cfg['customers'],validation_seed,weights=cfg['weights'],scope=selected)
                replayed = {}
                for policy,price in [('initial',selected['initial_member_fare']),('selected',chosen),('no_offer',None)]:
                    if price in replayed:
                        outcome = replayed[price]
                        reused = True
                    else:
                        outcome = evaluate(client,heldout,selected,price,validation_seed)
                        replayed[price] = outcome
                        reused = False
                    world = {'phase':'validation','policy':policy,'price':price,'seed':validation_seed,
                             'result':outcome,'reused_identical_policy':reused}
                    worlds.append(world)
                    store.record(run_id,{'event':'validation_world',**world})
                    run['counts'] = client.stats()
                    run['progress']['completed_validation_worlds'] = len(worlds)
                    store.save(run)
            run['validation'] = compare_validation(worlds,selected['initial_member_fare'],chosen,cfg['seed'])
            run['validation_worlds'] = worlds
            run['status'] = 'completed'
            run['progress']['phase'] = 'completed'
    except Exception as error:
        from llm_agent.audit import sanitize
        run['status'] = 'failed'
        run['error'] = sanitize(str(error))
        store.record(run_id,{'event':'run_failed','error':run['error']})
    finally:
        if client is not None:
            run['counts'] = client.stats()
        run['elapsed_seconds'] = round(time.time()-run['created_at'],3)
        try:
            store.save(run)
        finally:
            with _guard:
                _active.discard(run_id)


def start(body, *, blocking=False):
    cfg, selected, meta = validate(body)
    run_id = 'adaptive-'+uuid.uuid4().hex[:16]
    run = {'run_id':run_id,'version':VERSION,'status':'queued','created_at':time.time(),
           'config':cfg,'scope':{k:v for k,v in selected.items() if k!='history'},'population':meta,
           'provenance':_provenance(),'rounds':[],'recommendation':None,'validation':None,'error':None,
           'counts':{'provider_calls':0,'cache_hits':0,'forced':0,'failures':0,'peak_parallel':0},
           'progress':{'phase':'queued','completed_rounds':0,'total_rounds':cfg['rounds'],'completed_validation_worlds':0},
           'assumptions':['Only existing members; no joining or renewal decision and no fee deduction.',
                'Base fares only; all taxes/fuel/add-ons and operating costs excluded. Revenue is not airline profit.',
                'Population weights are explicit scenario assumptions, not measured HK Express market shares.',
                'One seat per member, one simultaneous offer at one flight/release snapshot. Companions are not purchased here.',
                'Parallel intent elicitation followed by fixed-priority integer inventory clearing; no seat is reserved by an LLM.',
                'Weighted demand estimates and actual panel cash/seat transactions are reported separately.',
                'Independent validation is read once after freezing the selected tested price; no refitting on holdout.']}
    with _guard:
        if _active:
            raise ValueError('An adaptive experiment is already running; wait for its results')
        _active.add(run_id)
    try:
        store.save(run)
    except Exception:
        with _guard:
            _active.discard(run_id)
        raise
    if blocking:
        _worker(run)
        return store.read(run_id)
    threading.Thread(target=_worker,args=(run,),daemon=True).start()
    return store.read(run_id)


def read(run_id):
    run = store.read(run_id)
    if run['status'] in ('queued','running'):
        run['elapsed_seconds'] = round(time.time()-run['created_at'],3)
        # Another process can legitimately own the active run. Only declare an
        # orphan after its heartbeat is stale and the cross-process lock is free.
        with _guard:
            local = run_id in _active
        if not local and time.time()-run['updated_at'] > 120:
            try:
                with exclusive_lock(store.BASE/'active.lock'):
                    run['status'] = 'interrupted'
                    run['error'] = 'The experiment process stopped. Completed decisions remain saved; no calls resume automatically.'
                    store.save(run)
            except ValueError:
                pass
    return run


list_runs = store.list_runs
events = store.events
export_run = store.export_run

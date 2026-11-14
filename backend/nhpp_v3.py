"""As-of NHPP regime forecast with explicit, synthetic future-shock uncertainty.

Conditional on a sampled rate, trend and piecewise regime path, arrivals have
NHPP increments. Across uncertain paths this is a mixture, not one deterministic
intensity. No scenario labels, future fares or latent generator values are read.

v3 keeps every trend/level estimate aligned to whole seven-day weeks (a 35-day
window, change points at 7/14/21/28 days and a weekly-block slope likelihood),
gates small releases by the Monte Carlo standard error of the protection
quantile, raises the explicit near-term shock prior for weekend/holiday
departures and exposes a weekday-matched early-warning test for use between
release rounds. This is the runtime forecaster; the frozen v2 model remains
byte-for-byte in ``backend/nhpp.py`` for its published evidence.
"""
from __future__ import annotations
from datetime import datetime
import json
import hashlib
import math
from pathlib import Path
import numpy as np

VERSION = 'nhpp-regime-mixture-v3'
CALIBRATION_FILE = 'simulation/generated/calibration_v3.json'
DRAWS = 800
SETTINGS = {'window_days':35,'beta_prior_mean':.012,'beta_prior_sd':.025,
            'price_elasticity':.8,'future_persistent_probability_28d':.22,
            'future_pulse_probability_28d':.10,'shock_multiplier_range':[2.,4.],
            'late_shock_prior_floor_fraction':.5,
            'changepoint_log_lr_threshold':5.,'max_beta':.10,'min_beta':-.08,
            'weekly_block_days':7,'changepoint_candidate_days':[7,14,21,28],
            'release_significance_z':1.645,'release_quantile_density_halfwidth':.05,
            'peak_departure_weekdays':[4,5,6],'peak_departure_shock_prior_multiplier':1.5,
            'surge_monitor_recent_days':3,'surge_monitor_reference_weeks':4,'surge_monitor_min_reference_weeks':2,
            'surge_monitor_ratio':1.8,'surge_monitor_log_lr_threshold':4.,'surge_monitor_min_recent_count':6}
WEEK=SETTINGS['weekly_block_days']


def _number(row,key,fallback=0.):
    v=row.get(key,fallback)
    if v is None:return float(fallback)
    x=float(v)
    if not math.isfinite(x):raise ValueError(f'{key} must be finite')
    return x


def _integral(beta,start,end):
    b=np.asarray(beta,dtype=float); safe=np.where(abs(b)<1e-9,1.,b)
    return np.where(abs(b)<1e-9,end-start,np.exp(b*start)*np.expm1(b*(end-start))/safe)


def _fit(items,sd=.025):
    grid=np.linspace(-.08,.10,181)
    count=sum(i['count'] for i in items if not i['censored'])
    exposure=np.full(grid.shape,1.)
    ll=-.5*((grid-.012)/sd)**2
    # The slope likelihood weights whole seven-day blocks, so a day-of-week
    # pattern cannot masquerade as a trend. Within-block day shares carry no
    # slope information here; Gamma shape/rate still use every exact count.
    blocks={}
    for n,i in enumerate(items):
        if i['censored']:continue
        g=_integral(grid,i['start'],i['end'])*i['price_factor']
        exposure+=g
        key=i.get('block',('item',n))
        c,e=blocks.get(key,(0,0.))
        blocks[key]=(c+i['count'],e+g)
    for c,e in blocks.values():
        if c:ll+=c*np.log(e)
    ll-=(1+count)*np.log(exposure)
    weights=np.exp(ll-ll.max());weights/=weights.sum()
    return grid,weights,1+count,exposure


def _log_poisson_survival(means,threshold):
    if threshold<=0:return np.zeros_like(means)
    if threshold==1:return np.log(-np.expm1(-means)).clip(-700,0)
    logs=np.array([-means+k*np.log(means)-math.lgamma(k+1) for k in range(threshold)])
    maximum=logs.max(axis=0)
    logcdf=maximum+np.log(np.exp(logs-maximum).sum(axis=0))
    return np.log(-np.expm1(np.minimum(logcdf,-1e-15))).clip(-700,0)


def _sample(items,rng,sd=.025):
    grid,weights,shape,exposures=_fit(items,sd)
    size=2400
    indices=rng.choice(len(grid),size=size,p=weights)
    beta=grid[indices]; base_rate=exposures[indices]
    censored=[i for i in items if i['censored']]
    factors=rng.choice([1.,2.,4.],size=size) if censored else np.ones(size)
    rates=rng.gamma(shape,factors/base_rate)
    if censored:
        # Broad rate proposals prevent missing high intensity after a capacity hit.
        # Correct proposal density before multiplying censored Poisson likelihood.
        logpdf=np.array([shape*np.log(base_rate/f)-base_rate/f*rates for f in [1.,2.,4.]])
        maximum=logpdf.max(axis=0)
        logmix=maximum+np.log(np.exp(logpdf-maximum).mean(axis=0))
        logw=logpdf[0]-logmix
        for i in censored:
            mean=rates*_integral(beta,i['start'],i['end'])*i['price_factor']
            logw+=_log_poisson_survival(np.maximum(mean,1e-10),i['count'])
        importance=np.exp(logw-logw.max());importance/=importance.sum()
    else:importance=np.full(size,1/size)
    chosen=rng.choice(size,size=DRAWS,p=importance)
    return beta[chosen],rates[chosen],float(1/np.square(importance).sum())


def _change(items):
    usable=[i for i in items if not i['censored']]
    best=None
    for k in SETTINGS['changepoint_candidate_days']:
        before=[i for i in usable if i['end']<=-k]
        after=[i for i in usable if i['end']>-k]
        if len(before)<7 or len(after)<3:continue
        c1=sum(i['count'] for i in before);c2=sum(i['count'] for i in after)
        if c1+c2<12:continue
        e1=sum(float(_integral(.012,i['start'],i['end']))*i['price_factor'] for i in before)
        e2=sum(float(_integral(.012,i['start'],i['end']))*i['price_factor'] for i in after)
        r1=(c1+.5)/(e1+.5);r2=(c2+.5)/(e2+.5)
        ratio=r2/r1
        ll=(c1*math.log(max(c1/e1,1e-12))+c2*math.log(max(c2/e2,1e-12))
            -(c1+c2)*math.log((c1+c2)/(e1+e2)))
        if ll>=SETTINGS['changepoint_log_lr_threshold'] and (ratio>=1.8 or ratio<=.55):
            if best is None or ll>best['log_lr']:best={'days_ago':k,'log_lr':round(ll,4),'ratio':round(ratio,4),'direction':'up' if ratio>1 else 'down'}
    return best


def _allowance(day,value,raw=0):
    if day==0:return 0,False,[]
    if value is not None:
        if not math.isfinite(value) or value<0:raise ValueError('protection_allowance must be finite and nonnegative')
        return math.ceil(value),False,[]
    path=Path(__file__).resolve().parents[1]/CALIBRATION_FILE
    if not path.exists():return 0,False,[]
    obj=json.loads(path.read_text())
    fingerprint=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    if obj.get('model_version')!=VERSION or obj.get('settings')!=SETTINGS or obj.get('forecast_code_sha256')!=fingerprint:
        raise ValueError('NHPP calibration is stale for this model version/settings; recalibrate before automatic protection')
    margins=obj.get('relative_guard_by_horizon')
    horizons=sorted(int(x) for x in (margins or obj['allowance_by_horizon']))
    selected=next((h for h in horizons if h>=day),horizons[-1])
    if margins is not None:return max(0,math.ceil(margins[str(selected)]*max(10,raw))),True,horizons
    return max(0,math.ceil(obj['allowance_by_horizon'][str(selected)])),True,horizons


def _truthy(value):
    return value is True or (isinstance(value,(int,float)) and not isinstance(value,bool) and value==1) or (isinstance(value,str) and value.strip().lower() in ('1','true','yes'))


def peak_departure(rows,override=None):
    """Weekend (Fri-Sun local departure) or explicitly flagged holiday departure.

    Holidays are never inferred: only an explicit, as-of-known
    ``is_public_holiday`` field (or the override) marks one.
    """
    if override is not None:
        return {'peak':bool(override),'source':'explicit_override'}
    if any(_truthy(r.get('is_public_holiday')) for r in rows):
        return {'peak':True,'source':'is_public_holiday'}
    for r in reversed(rows):
        value=r.get('departure_at')
        if not value:continue
        try:weekday=datetime.fromisoformat(str(value)).weekday()
        except ValueError:continue
        return {'peak':weekday in SETTINGS['peak_departure_weekdays'],'source':'departure_weekday','weekday':weekday}
    return {'peak':False,'source':'unknown_calendar'}


def _intervals(history,day,capacity,price,has_prices):
    """Completed daily intervals in the 35-day (five whole weeks) window."""
    intervals=[];unavailable=0
    for previous,row in zip(history[:-1],history[1:]):
        d=_number(row,'days_to_departure')
        if d>=day+SETTINGS['window_days'] or _number(previous,'days_to_departure')-d!=1:continue
        duration=_number(row,'interval_days',1 if d else 22/24)
        count=_number(row,'gross_bookings');cancels=_number(row,'cancellations')
        if not 0<duration<=1 or count<0 or count!=int(count) or cancels<0 or cancels!=int(cancels):raise ValueError('Invalid interval gross count or cancellations')
        prev_booked=_number(previous,'booked_seats');available=capacity-prev_booked
        if available<=0:unavailable+=1;continue
        prior_price=_number(previous,'normal_total_fare',price)
        factor=(max(prior_price,1)/price)**(-SETTINGS['price_elasticity']) if has_prices else 1.
        end=day-d
        intervals.append({'start':end-duration,'end':end,'count':int(count),'censored':count>=available,
                          'price_factor':factor,'cancellations':cancels,'booked_exposure':prev_booked*duration,
                          'block':int(-end//WEEK)})
    return intervals,unavailable


def _prepare(rows,day):
    if isinstance(day,bool) or not isinstance(day,int) or not 0<=day<=28 or not rows:raise ValueError('integer decision day 0..28 and history required')
    history=sorted((r for r in rows if _number(r,'days_to_departure')>=day),key=lambda r:-_number(r,'days_to_departure'))
    if not history or _number(history[-1],'days_to_departure')!=day:raise ValueError('No snapshot at decision day')
    if len({r.get('flight_id','') for r in history})!=1:raise ValueError('One flight required')
    if len({r['days_to_departure'] for r in history})!=len(history):raise ValueError('Duplicate days')
    current=history[-1];capacity=int(_number(current,'capacity',180));booked=int(_number(current,'booked_seats',0))
    if not 0<=booked<=capacity or capacity<1:raise ValueError('Invalid capacity/booked seats')
    prices=[_number(r,'normal_total_fare') for r in history if _number(r,'normal_total_fare')>0]
    price=prices[-1] if prices else 1.
    intervals,unavailable=_intervals(history,day,capacity,price,bool(prices))
    return history,current,capacity,booked,intervals,unavailable


def surge_alarm(rows:list[dict],days_to_departure:int)->dict:
    """Weekday-matched early warning for use between release rounds.

    Compares the latest few completed days with the same weekdays in earlier
    weeks, so an ordinary weekend peak is not an alarm. It only says that the
    forecast should be refreshed; it never creates or releases quota.
    """
    _,_,_,_,intervals,_=_prepare(rows,days_to_departure)
    recent_days=SETTINGS['surge_monitor_recent_days']
    by_end={-i['end']:i for i in intervals}
    def window(offset):
        chosen=[by_end.get(offset+k) for k in range(recent_days)]
        if any(i is None or i['censored'] for i in chosen):return None
        return sum(i['count'] for i in chosen),sum((i['end']-i['start'])*i['price_factor'] for i in chosen)
    recent=window(0)
    references=[w for w in (window(WEEK*n) for n in range(1,SETTINGS['surge_monitor_reference_weeks']+1)) if w is not None]
    result={'alarm':False,'recent_days':recent_days,'reference_weeks':len(references)}
    if recent is None or len(references)<SETTINGS['surge_monitor_min_reference_weeks']:
        return {**result,'reason':'insufficient_uncensored_history'}
    c1,e1=recent;c0=sum(c for c,_ in references);e0=sum(e for _,e in references)
    ratio=((c1+.5)/(e1+.5))/((c0+.5)/(e0+.5))
    ll=(c1*math.log(max(c1/e1,1e-12)) if c1 else 0.)+(c0*math.log(max(c0/e0,1e-12)) if c0 else 0.)
    ll-=(c1+c0)*math.log(max((c1+c0)/(e1+e0),1e-12)) if c1+c0 else 0.
    alarm=(c1>=SETTINGS['surge_monitor_min_recent_count'] and ratio>=SETTINGS['surge_monitor_ratio']
           and ll>=SETTINGS['surge_monitor_log_lr_threshold'])
    return {**result,'alarm':bool(alarm),'recent_count':int(c1),'reference_count':int(c0),
            'ratio':round(ratio,4),'log_lr':round(ll,4),'reason':'weekday_matched_acceleration' if alarm else 'no_acceleration'}


def _quantile_standard_error(values,q,effective_draws):
    """Asymptotic SE of a sample quantile: sqrt(q(1-q)/n) / f(Q(q))."""
    h=SETTINGS['release_quantile_density_halfwidth']
    spread=float(np.quantile(values,min(1.,q+h))-np.quantile(values,max(0.,q-h)))
    return spread/(2*h)*math.sqrt(q*(1-q)/max(1.,effective_draws))


def forecast(rows:list[dict],days_to_departure:int=28,seed:int=117,protection_allowance:float|None=None,
             peak_departure_override:bool|None=None)->dict:
    day=days_to_departure
    history,current,capacity,booked,intervals,unavailable=_prepare(rows,day)
    calendar=peak_departure(history,peak_departure_override)
    change=_change(intervals)
    selected=[i for i in intervals if i['end']>-change['days_ago']] if change else intervals
    rng=np.random.default_rng(seed)
    betas,rates,ess=_sample(selected,rng,sd=.018 if change else .025)
    cancellation_rate=min(.03,(sum(i['cancellations'] for i in intervals)+.1)/(sum(i['booked_exposure'] for i in intervals)+500))
    # Explicit future regime prior. Parameters are assumptions for sensitivity
    # analysis; seeing a recent jump reduces (does not remove) a second-jump prior.
    scale=(SETTINGS['late_shock_prior_floor_fraction']+(1-SETTINGS['late_shock_prior_floor_fraction'])*day/28)*(.4 if change else 1.) if day else 0
    u=rng.random(DRAWS)
    # Weekend/holiday departures get an explicitly larger near-term shock
    # prior (an assumption, not an estimate); D0 remains zero.
    scale*=SETTINGS['peak_departure_shock_prior_multiplier'] if calendar['peak'] else 1.
    persistent_probability=SETTINGS['future_persistent_probability_28d']*scale
    pulse_probability=SETTINGS['future_pulse_probability_28d']*scale
    persistent=u<persistent_probability;pulse=(u>=persistent_probability)&(u<persistent_probability+pulse_probability)
    onset=rng.uniform(.15,.8,DRAWS)*max(1,day-2/24)
    multiplier=rng.uniform(*SETTINGS['shock_multiplier_range'],DRAWS)
    # A detected upswing can be transient. Preserve uncertainty instead of
    # multiplying a steep fitted slope indefinitely after a single group event.
    revert=(rng.random(DRAWS)<.2) if change and change['direction']=='up' else np.zeros(DRAWS,bool)
    daily=[];seats=np.full(DRAWS,booked,dtype=int)
    curve=[{'day':day,'expected_booked':float(booked),'p10':float(booked),'p90':float(booked)}]
    for elapsed in range(day):
        duration=22/24 if elapsed==day-1 else 1.
        mean=rates*_integral(betas,elapsed,elapsed+duration)
        active=(persistent&(elapsed>=onset))|(pulse&(elapsed>=onset)&(elapsed<onset+3))
        mean*=np.where(active,multiplier,1.)
        if change and change['direction']=='up' and elapsed>=3:mean/=np.where(revert,max(1,change['ratio']),1.)
        arrivals=rng.poisson(np.minimum(mean,1e6));daily.append(arrivals)
        cancels=rng.binomial(seats,1-math.exp(-cancellation_rate*duration))
        seats+=np.minimum(arrivals,capacity-seats)-cancels
        curve.append({'day':day-elapsed-1,'expected_booked':round(float(seats.mean()),3),'p10':float(np.quantile(seats,.1)),'p90':float(np.quantile(seats,.9))})
    totals=np.sum(daily,axis=0) if daily else np.zeros(DRAWS,dtype=int)
    raw=int(np.quantile(totals,.9,method='higher'))
    allowance,calibrated,horizons=_allowance(day,protection_allowance,raw)
    protection=raw+allowance
    censored=sum(i['censored'] for i in intervals)+unavailable
    fraction=censored/max(1,len(intervals)+unavailable)
    available=capacity-booked
    release=max(0,available-protection) if day and len(intervals)>=7 and len(selected)>=3 else 0
    if fraction>.5 or ess<20:release=0
    # Asymptotic significance gate: a release no larger than z standard errors
    # of the Monte Carlo protection quantile is indistinguishable from zero.
    effective=min(DRAWS,ess)
    raw_se=_quantile_standard_error(totals,.9,effective)
    guarded=lambda x:x+_allowance(day,protection_allowance,x)[0] if day else x
    protection_se=max(raw_se,(guarded(raw+raw_se)-guarded(max(0.,raw-raw_se)))/2) if raw_se else 0.
    threshold=SETTINGS['release_significance_z']*protection_se
    pre_threshold=release
    significant=release>threshold
    if not significant:release=0
    significance={'z':SETTINGS['release_significance_z'],'effective_draws':round(effective,1),
                  'raw_quantile_standard_error':round(raw_se,4),'protection_standard_error':round(protection_se,4),
                  'threshold_seats':round(threshold,4),'pre_threshold_release':int(pre_threshold),
                  'passed':bool(significant),'held_by_threshold':bool(pre_threshold>0 and not significant)}
    protection_curve=[]
    demand_curve=[]
    for offset in range(day+1):
        remaining=day-offset
        suffix=np.sum(daily[offset:],axis=0) if remaining else np.zeros(DRAWS)
        q=int(np.quantile(suffix,.9,method='higher'))
        guard=_allowance(remaining,protection_allowance,q)[0]
        protection_curve.append({'day':remaining,'raw_protection_p90':q,'protection_allowance':guard,'protection_seats':q+guard})
        demand_curve.append({'day':remaining,'expected_remaining_demand':round(float(suffix.mean()),4)})
    return {'model':VERSION,'flight_id':current.get('flight_id',''),'days_to_departure':day,'capacity':capacity,'booked_seats':booked,'available_seats':available,
            'beta':round(float(betas.mean()),6),'rate_now':round(float(rates.mean()),4),'expected_remaining_demand':round(float(totals.mean()),3),
            'expected_empty_seats':round(float((capacity-seats).mean()),3),'expected_empty_rate':round(float((capacity-seats).mean()/capacity),5),
            'raw_protection_p90':raw,'protection_allowance':allowance,'protection_p90':protection,'releasable_seats':release,
            'intervals':len(intervals),'forecast_curve':curve,'protection_curve':protection_curve,'demand_curve':demand_curve,
            'demand_p10':float(np.quantile(totals,.1)),'demand_p90':float(np.quantile(totals,.9)),'demand_interval_width':round(float(np.quantile(totals,.9)-np.quantile(totals,.1)),3),
            'diagnostics':{'censored_intervals':censored,'censored_fraction':round(fraction,3),'possible_jump':bool(change and change['direction']=='up'),
                           'change_point':change,'observed_gross_count':sum(i['count'] for i in intervals),'daily_cancellation_rate':round(cancellation_rate,6),
                           'beta_prior_mean':.012,'beta_prior_sd':.018 if change else .025,'beta_grid_bounds':[-.08,.10],'predictive_draws':DRAWS,
                           'release_significance':significance,'calendar':calendar,
                           'window_days':SETTINGS['window_days'],'weekly_block_days':WEEK,
                           'calibration_loaded':calibrated,'calibration_horizon_days':horizons,'posterior_effective_samples':round(ess,1),
                           'future_persistent_probability':round(persistent_probability,4),'future_pulse_probability':round(pulse_probability,4),'price_elasticity_assumption':SETTINGS['price_elasticity']},
            'assumptions':['Synthetic-market forecast; no observed HK Express bookings or price elasticity calibration.',
                           'Conditional NHPP per sampled regime path; unknown future jumps are scenarios, not events predicted with certainty.',
                           'Observed prices normalize past exposure with assumed elasticity; future normal fare is held at its current level.',
                           'Capacity-hit counts use a right-censored likelihood; zero availability supplies no zero-demand observation.',
                           'Raw mixture bands and empirically guarded protection are separate; coverage is measured on disjoint synthetic flights.',
                           'Forecasted seat availability includes cancellations; normal-demand protection uses gross requests conservatively.',
                           'Trend, level and change points use five whole weeks; the slope likelihood weights seven-day blocks so weekday patterns are not read as trend.',
                           'A release is published only when it exceeds z standard errors of the protection quantile; smaller margins are sampling noise.',
                           'Weekend (Fri-Sun) or explicitly flagged holiday departures use a larger assumed near-term shock prior; holidays are never inferred.']}

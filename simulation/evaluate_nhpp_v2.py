"""Predeclared development/calibration/final NHPP v1/v2 comparison.

New generation seeds are separate from the already-inspected v1 data. Scenario
and latent demand are scoring-only; every forecast sees an as-of prefix only.
"""
from __future__ import annotations
import argparse, hashlib, json, math
from collections import defaultdict
from pathlib import Path
import numpy as np
from simulation.generate import simulate_flight, _integral
from simulation.baselines.nhpp_v1 import forecast as v1
from backend.nhpp import forecast as v2, SETTINGS, VERSION

ROOT=Path(__file__).resolve().parents[1]
OUTPUT=ROOT/'simulation/generated'
SEEDS={'development':20261114,'calibration':20261115,'final':20261116}
DAYS=(28,14,7)
FORECAST_SEED=117


def _onset(flight):
    truth=flight['truth'];norm=[]
    for r in truth:
        d=r['interval_start_day'];length=22/24 if d==1 else 1
        value=r['expected_demand']/_integral(r['beta'],180-d,180-d+length)*(r['internal_base_fare']+250)**.8
        norm.append(value)
    baseline=float(np.median(norm[:30]))
    return next((r['interval_start_day'] for r,x in zip(truth,norm) if x>1.8*baseline),None)


def evaluate(seed,count=180,allowances=None,methods=None):
    allowances=allowances or {};methods=methods or {'v1':v1,'v2':v2}
    records=[]
    for i in range(count):
        flight=simulate_flight(i,seed);onset=_onset(flight)
        for d in DAYS:
            prefix=[r for r in flight['snapshots'] if r['days_to_departure']>=d]
            # Explicit whitelist; generator labels/latent parameters never join X.
            allowed=('flight_id','days_to_departure','capacity','booked_seats','available_seats','gross_bookings','cancellations','interval_days','normal_total_fare')
            public=[{k:r[k] for k in allowed} for r in prefix]
            actual=sum(r['demand_requests'] for r in flight['truth'] if r['interval_start_day']<=d)
            actual_empty=flight['snapshots'][-1]['available_seats']
            for name,method in methods.items():
                allowance=allowances.get(name,{}).get(str(d),0)
                if isinstance(allowance,dict):
                    raw=method(public,d,FORECAST_SEED,protection_allowance=0)['raw_protection_p90']
                    allowance=math.ceil(allowance['relative']*max(10,raw))
                p=method(public,d,FORECAST_SEED,protection_allowance=allowance)
                available=p['available_seats'];q=p['releasable_seats'];raw=p['raw_protection_p90']
                displacement=max(0,actual-(available-q))-max(0,actual-available)
                records.append({'generator_seed':seed,'flight_id':flight['summary']['flight_id'],'model':name,'day':d,
                                'scenario_for_scoring':flight['summary']['scenario'],
                                'jump_state_for_scoring':('observed' if onset and onset>d else 'future' if onset else 'none'),
                                'predicted_demand':p['expected_remaining_demand'],'actual_demand':actual,
                                'demand_ae':abs(p['expected_remaining_demand']-actual),'empty_ae':abs(p['expected_empty_seats']-actual_empty),
                                'raw_protection':raw,'protection':p['protection_p90'],'covered':actual<=p['protection_p90'],
                                'raw_covered':actual<=raw,'release':q,'displacement_if_all_released_sell':displacement,
                                'mean_booked_band_width':float(np.mean([r['p90']-r['p10'] for r in p['forecast_curve']])),
                                'censored_fraction':p['diagnostics']['censored_fraction'],'detected_jump':p['diagnostics']['possible_jump']})
    return records


def aggregate(rows):
    if not rows:return {}
    mean=lambda k:round(float(np.mean([r[k] for r in rows])),4)
    return {'n':len(rows),'demand_mae':mean('demand_ae'),'empty_mae':mean('empty_ae'),'coverage':mean('covered'),'raw_coverage':mean('raw_covered'),
            'mean_protection':mean('protection'),'mean_release':mean('release'),
            'release_rate':round(float(np.mean([r['release']>0 for r in rows])),4),
            'mean_booked_band_width':mean('mean_booked_band_width'),
            'mean_displacement_if_all_released_sell':mean('displacement_if_all_released_sell'),
            'release_violation_rate':round(float(np.mean([r['displacement_if_all_released_sell']>0 for r in rows])),4)}


def summarize(rows):
    groups=defaultdict(list)
    for r in rows:
        groups[f"{r['model']}/D{r['day']}/all"].append(r)
        groups[f"{r['model']}/D{r['day']}/{r['scenario_for_scoring']}"].append(r)
        if r['scenario_for_scoring']=='surge':groups[f"{r['model']}/D{r['day']}/surge_{r['jump_state_for_scoring']}"].append(r)
    return {k:aggregate(v) for k,v in sorted(groups.items())}


def detection_probe(seed,count=60):
    results=[]
    for i in range(count):
        f=simulate_flight(i,seed);onset=_onset(f)
        if f['summary']['scenario']!='surge' or onset is None:continue
        detection=None;false_before=False
        for d in range(28,0,-1):
            p=v2(f['snapshots'],d,FORECAST_SEED,protection_allowance=0)
            if p['diagnostics']['possible_jump']:
                if d>=onset:false_before=True
                elif detection is None:detection=onset-d
        results.append({'flight_id':f['summary']['flight_id'],'onset_day_scoring_only':onset,'detection_delay_days':detection,'false_alarm_before_onset':false_before})
    detected=[r['detection_delay_days'] for r in results if r['detection_delay_days'] is not None]
    return {'flights':len(results),'detected_fraction':sum(r['detection_delay_days'] is not None for r in results)/max(1,len(results)),
            'median_detected_delay_days':float(np.median(detected)) if detected else None,
            'false_alarm_before_onset_rate':sum(r['false_alarm_before_onset'] for r in results)/max(1,len(results)), 'details':results}


def run(phase,count=None):
    OUTPUT.mkdir(exist_ok=True)
    count=count or (180 if phase=='development' else 240)
    model_hash=hashlib.sha256((ROOT/'backend/nhpp.py').read_bytes()).hexdigest()
    artifact=OUTPUT/f'nhpp_v2_{phase}.json'
    allowances={}
    if phase=='final':
        cfg=json.loads((OUTPUT/'calibration_v2.json').read_text())
        if cfg['forecast_code_sha256']!=model_hash:raise ValueError('Model changed after calibration; refreeze before opening a new final set')
        if artifact.exists():raise ValueError('Final report already exists; do not repeatedly inspect and retune this holdout')
        allowances=cfg['comparison_allowances']
    rows=evaluate(SEEDS[phase],count,allowances)
    report={'phase':phase,'generation_seed':SEEDS[phase],'forecast_seed':FORECAST_SEED,'flights':count,'horizons':DAYS,'model_sha256':model_hash,
            'settings':SETTINGS,'summary':summarize(rows),'records':rows,
            'notes':['V1 historical holdout is development only. New generation seeds separate these phases.',
                     'Same generated flights and forecast seed are used for differential comparison; different model sampling schemes need not give identical random paths.',
                     'Independent synthetic histories are not proof of real airline coverage. Scenario identity is scoring-only.',
                     'Displacement metric assumes every released member seat sells; it is a conservative capacity-risk diagnostic, not measured financial loss.']}
    if phase=='calibration':
        guard={}
        for name in ('v1','v2'):
            guard[name]={}
            for day in DAYS:
                subset=[r for r in rows if r['model']==name and r['day']==day]
                residual=sorted(r['actual_demand']-r['raw_protection'] for r in subset)
                rank=min(len(residual),math.ceil((len(residual)+1)*.9))
                # One global scale per horizon protects the worst synthetic
                # regime. Labels are used to calibrate aggregate robustness,
                # never to select a runtime flight-specific guard.
                subgroup_margins=[]
                for scenario in sorted({r['scenario_for_scoring'] for r in subset}):
                    residual=[(r['actual_demand']-r['raw_protection'])/max(10,r['raw_protection']) for r in subset if r['scenario_for_scoring']==scenario]
                    residual.sort();rank=min(len(residual),math.ceil((len(residual)+1)*.9))
                    subgroup_margins.append(residual[rank-1])
                guard[name][str(day)]={'relative':max(0,float(max(subgroup_margins)))}
        (OUTPUT/'calibration_v2.json').write_text(json.dumps({'version':2,'model_version':VERSION,'relative_guard_by_horizon':{d:g['relative'] for d,g in guard['v2'].items()},'comparison_allowances':guard,
             'generation_seed':SEEDS[phase],'final_generation_seed_reserved':SEEDS['final'],'flights':count,'target_coverage':.9,
             'forecast_code_sha256':model_hash,'settings':SETTINGS,'method':'worst synthetic regime upper order statistic of relative residual; one global scale per horizon',
             'notes':['Scoring labels calibrate one global guard shared by every runtime flight; no scenario label enters forecasting.',
                      'Guarded protection is not a probability P90. It trades release volume for robustness across these synthetic regimes.']},indent=2))
        report['chosen_allowances']=guard
    if phase=='final':report['detection']=detection_probe(SEEDS[phase],min(count,120))
    artifact.write_text(json.dumps(report,indent=2))
    print(json.dumps({'phase':phase,'summary':{k:v for k,v in report['summary'].items() if k.endswith('/all') or k.endswith('/surge')},'allowances':report.get('chosen_allowances')},indent=2))
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('phase',choices=SEEDS);p.add_argument('--count',type=int);a=p.parse_args();run(a.phase,a.count)

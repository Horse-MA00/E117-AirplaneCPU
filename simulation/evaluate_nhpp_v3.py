"""Frozen-protocol smoothing and revenue-aware guard calibration.

Revenue is a paired capacity stress: all released seats sell immediately, no
cancellations or customer switching, chronological normal requests at synthetic
base fares. It excludes taxes, member revenue and operating costs; not net profit.
"""
from __future__ import annotations
import argparse
from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path
import numpy as np
from backend import nhpp, nhpp_v3
from simulation.generate import simulate_flight

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'simulation/generated'
SEEDS = {'development':20261201, 'calibration':20261202, 'final':20261203}
DAYS = (28,14,7)
PROTOCOL = {'target_group_coverage':.9, 'max_normal_revenue_loss_ratio':.005,
            'guard_grid_step':.05, 'calibration_flights':360, 'final_flights':600,
            'revenue_stress':'all_member_seats_sell_immediately_no_cancellations_no_switching_base_fare_only'}
FIELDS = ('flight_id','days_to_departure','capacity','booked_seats','gross_bookings',
          'cancellations','interval_days','normal_total_fare')


def hashes():
    return {p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in
            ('backend/nhpp.py','backend/nhpp_v3.py','simulation/generate.py','simulation/evaluate_nhpp_v3.py')}


def revenue(requests, capacity):
    result = 0.
    for count, fare in requests:
        sold = min(capacity,count)
        result += sold*fare
        capacity -= sold
    return result


def score_guard(row, guard):
    protection = row['raw_protection']+math.ceil(guard*max(10,row['raw_protection']))
    release = max(0,row['available']-protection) if row['quality_gate'] else 0
    baseline = revenue(row['future_requests_scoring_only'],row['available'])
    loss = baseline-revenue(row['future_requests_scoring_only'],row['available']-release)
    return {**row, 'protection':protection, 'release':release,
            'covered':row['actual_demand']<=protection,
            'normal_base_revenue_baseline':baseline,'normal_base_revenue_loss':loss}


def collect(seed, count):
    rows=[]
    for index in range(count):
        flight=simulate_flight(index,seed)
        for day in DAYS:
            public=[{k:r[k] for k in FIELDS} for r in flight['snapshots'] if r['days_to_departure']>=day]
            future=[(r['demand_requests'],r['internal_base_fare']) for r in flight['truth'] if r['interval_start_day']<=day]
            for name,model in (('v2',nhpp),('v3',nhpp_v3)):
                p=model.forecast(public,day,117,protection_allowance=0)
                raw=p['raw_protection_p90']; diag=p['diagnostics']
                gate=(p['intervals']>=7 and diag['censored_fraction']<=.5 and diag['posterior_effective_samples']>=20)
                # V2's recent-window gate must also be preserved.
                change=diag['change_point']
                if name=='v2' and change:
                    gate=gate and sum(1 for a,b in zip(public[:-1],public[1:])
                        if day-b['days_to_departure']>-change['days_ago']
                        and a['days_to_departure']-b['days_to_departure']==1
                        and a['booked_seats']<p['capacity'])>=3
                row={'generator_seed':seed,'flight_id':flight['summary']['flight_id'],'model':name,'day':day,
                     'scenario_for_scoring':flight['summary']['scenario'],'actual_demand':sum(c for c,_ in future),
                     'predicted_demand':p['expected_remaining_demand'],'raw_protection':raw,
                     'available':p['available_seats'],'quality_gate':gate,
                     'future_requests_scoring_only':future,'recent_weight':diag.get('recent_component_weight'),
                     'raw_covered':sum(c for c,_ in future)<=raw}
                # Ensure score reproduction has identical release semantics at zero guard.
                assert score_guard(row,0)['release']==p['releasable_seats']
                rows.append(row)
        if (index+1)%60==0: print(f'generated and forecast {index+1}/{count}',flush=True)
    return rows


def aggregate(rows):
    def mean(k):return float(np.mean([r[k] for r in rows]))
    n=len(rows); covered=mean('covered'); z=1.96
    center=(covered+z*z/(2*n))/(1+z*z/n)
    radius=z*math.sqrt(covered*(1-covered)/n+z*z/(4*n*n))/(1+z*z/n)
    baseline=sum(r['normal_base_revenue_baseline'] for r in rows)
    return {'n':n,'raw_p90_coverage':mean('raw_covered'),'guarded_coverage':covered,
            'guarded_coverage_wilson95':[center-radius,center+radius],
            'demand_mae':float(np.mean([abs(r['predicted_demand']-r['actual_demand']) for r in rows])),
            'mean_release':mean('release'),'release_rate':sum(r['release']>0 for r in rows)/n,
            'mean_normal_base_revenue_loss_hkd':mean('normal_base_revenue_loss'),
            'normal_base_revenue_loss_ratio':sum(r['normal_base_revenue_loss'] for r in rows)/baseline if baseline else 0.}


def summary(rows):
    groups=defaultdict(list)
    for row in rows:
        for group in ('all',row['scenario_for_scoring']):
            groups[f"{row['model']}/D{row['day']}/{group}"].append(row)
    return {key:aggregate(values) for key,values in sorted(groups.items())}


def select_guard(rows):
    maximum=max(max(0,(r['actual_demand']-r['raw_protection'])/max(10,r['raw_protection'])) for r in rows)
    step=PROTOCOL['guard_grid_step']
    for index in range(math.ceil(maximum/step)+2):
        guard=round(index*step,8)
        scored=[score_guard(r,guard) for r in rows]
        groups=defaultdict(list)
        for r in scored:groups[r['scenario_for_scoring']].append(r)
        metrics=[aggregate(group) for group in groups.values()]
        if all(m['guarded_coverage']>=PROTOCOL['target_group_coverage'] and
               m['normal_base_revenue_loss_ratio']<=PROTOCOL['max_normal_revenue_loss_ratio'] for m in metrics):
            return guard
    raise ValueError('No feasible guard; do not deploy unvalidated protection')


def run(phase):
    artifact=OUT/f'nhpp_v3_{phase}.json'
    calibration=OUT/'calibration_v3.json'
    if artifact.exists() or (phase=='calibration' and calibration.exists()):
        raise ValueError('Evidence already exists; use a new version and reserved seeds, never overwrite')
    frozen=hashes()
    cfg=None
    if phase=='final':
        cfg=json.loads(calibration.read_text())
        if cfg['source_hashes']!=frozen or cfg['protocol']!=PROTOCOL or cfg['seeds']!=SEEDS:
            raise ValueError('Source or protocol changed after calibration')
    count=120 if phase=='development' else PROTOCOL[f'{phase}_flights']
    rows=collect(SEEDS[phase],count)
    if phase=='calibration':
        guards={name:{str(day):select_guard([r for r in rows if r['model']==name and r['day']==day])
                      for day in DAYS} for name in ('v2','v3')}
        cfg={'version':3,'model_version':nhpp_v3.VERSION,'settings':nhpp_v3.SETTINGS,
             'forecast_code_sha256':frozen['backend/nhpp_v3.py'],'source_hashes':frozen,
             'relative_guard_by_horizon':guards['v3'],'comparison_guards':guards,
             'protocol':PROTOCOL,'seeds':SEEDS,'generation_seed':SEEDS['calibration'],
             'method':'smallest global relative guard meeting per-scenario coverage and paired normal-base-revenue stress limits; labels never used at runtime'}
        calibration.write_text(json.dumps(cfg,indent=2)+'\n',encoding='utf-8')
    guards=cfg['comparison_guards'] if cfg else {name:{str(d):0 for d in DAYS} for name in ('v2','v3')}
    scored=[score_guard(r,guards[r['model']][str(r['day'])]) for r in rows]
    report={'phase':phase,'generation_seed':SEEDS[phase],'flights':count,'source_hashes':frozen,
            'protocol':PROTOCOL,'settings':nhpp_v3.SETTINGS,'guards':guards,
            'summary':summary(scored),'records':scored,
            'limitations':['Synthetic same-generator evidence, not real airline validation.',
                'Raw P90 is separate from guarded decision coverage.',
                'Revenue stress ignores cancellations, substitution, member revenue and costs; not realized losses or total profit.',
                'Each horizon is a separate single-release stress, not a combined D28/D14/D7 policy replay.',
                'Guard selection targets empirical calibration coverage, not a 90% statistical guarantee.']}
    if phase=='final':
        # Frozen incumbent as deployed is distinct from equally recalibrated v2.
        old=json.loads((OUT/'calibration_v2.json').read_text())['relative_guard_by_horizon']
        incumbent=[score_guard(r,old[str(r['day'])]) for r in rows if r['model']=='v2']
        report['frozen_v2_summary']=summary(incumbent)
    artifact.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'phase':phase,'guards':guards,'summary':{k:v for k,v in report['summary'].items() if k.endswith('/all')}},indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('phase',choices=SEEDS)
    run(parser.parse_args().phase)

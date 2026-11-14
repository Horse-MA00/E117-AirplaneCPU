"""Second, predeclared calibration protocol; preserve the failed first candidate.

The first final set is now development evidence ONLY. No second-final values
are used to fit guards. No search over seeds, and existing artifacts are immutable.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
from backend import nhpp_v3
from simulation.evaluate_nhpp_v3 import collect, score_guard, summary, hashes, DAYS

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'simulation/generated'
SEEDS={'calibration':20261211,'final':20261212}
PROTOCOL={'calibration_flights':1200,'final_flights':600,
          'calibration_group_quantile':.95,'calibration_max_revenue_loss':0.,
          'acceptance_group_coverage':.9,'acceptance_group_revenue_loss_ratio':.005,
          'guard_step':.05}


def provenance():
    return {**hashes(),'simulation/calibrate_nhpp_v3_robust.py':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}


def guard_for(rows):
    # Finite-sample upper order statistic, per synthetic regime; runtime global.
    bounds=[]
    for scenario in sorted({r['scenario_for_scoring'] for r in rows}):
        group=[r for r in rows if r['scenario_for_scoring']==scenario]
        residuals=sorted((r['actual_demand']-r['raw_protection'])/max(10,r['raw_protection']) for r in group)
        rank=min(len(group),math.ceil((len(group)+1)*PROTOCOL['calibration_group_quantile']))
        bounds.append(max(0,residuals[rank-1]))
    step=PROTOCOL['guard_step'];index=math.ceil(max(bounds)/step)
    maximum=max(max(0,(r['actual_demand']-r['raw_protection'])/max(10,r['raw_protection'])) for r in rows)
    for k in range(index,max(index,math.ceil(maximum/step))+2):
        guard=round(k*step,8)
        if all(score_guard(r,guard)['normal_base_revenue_loss']<=PROTOCOL['calibration_max_revenue_loss'] for r in rows):
            return guard
    raise ValueError('Unable to calibrate protection')


def run(phase):
    target=OUT/f'nhpp_v3_robust_{phase}.json'; calibration=OUT/'calibration_v3_robust.json'
    if target.exists() or (phase=='calibration' and calibration.exists()):raise ValueError('Never overwrite frozen evidence')
    source=provenance();cfg=None
    if phase=='final':
        cfg=json.loads(calibration.read_text())
        if cfg['source_hashes']!=source or cfg['protocol']!=PROTOCOL:raise ValueError('Changed after calibration')
    rows=collect(SEEDS[phase],PROTOCOL[f'{phase}_flights'])
    if phase=='calibration':
        guards={name:{str(day):guard_for([r for r in rows if r['model']==name and r['day']==day]) for day in DAYS} for name in ('v2','v3')}
        cfg={'model_version':nhpp_v3.VERSION,'settings':nhpp_v3.SETTINGS,'source_hashes':source,
             'relative_guard_by_horizon':guards['v3'],'comparison_guards':guards,
             'protocol':PROTOCOL,'seeds':SEEDS,'supersedes_candidate_only':'calibration_v3.json',
             'forecast_code_sha256':source['backend/nhpp_v3.py'],
             'method':'worst-regime finite-sample 95% upper relative residual, increased until calibration capacity-stress normal revenue loss is zero'}
        calibration.write_text(json.dumps(cfg,indent=2)+'\n',encoding='utf-8')
    scored=[score_guard(r,cfg['comparison_guards'][r['model']][str(r['day'])]) for r in rows]
    sums=summary(scored)
    report={'phase':phase,'seeds':SEEDS,'protocol':PROTOCOL,'source_hashes':source,
            'calibration_sha256':hashlib.sha256(calibration.read_bytes()).hexdigest(),
            'guards':cfg['comparison_guards'],'summary':sums,'records':scored,
            'limitations':['Same synthetic generator; no real airline performance claim.',
                'All member seats sell immediately, cancellations and switching excluded; base-fare displacement stress, not net profit.',
                'Single release per horizon, not a full three-round market replay.',
                'Raw P90 is not calibrated protection; point-estimate acceptance is not a coverage guarantee.',
                'First v3 final is retained as failed development evidence; this final uses a newly reserved seed.']}
    if phase=='final':
        report['accepted']=all(v['guarded_coverage']>=PROTOCOL['acceptance_group_coverage'] and
            v['normal_base_revenue_loss_ratio']<=PROTOCOL['acceptance_group_revenue_loss_ratio']
            for k,v in sums.items() if k.startswith('v3/'))
        old=json.loads((OUT/'calibration_v2.json').read_text())['relative_guard_by_horizon']
        report['frozen_v2_summary']=summary([score_guard(r,old[str(r['day'])]) for r in rows if r['model']=='v2'])
    target.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'phase':phase,'accepted':report.get('accepted'),'guards':report['guards'],
        'summary':{k:v for k,v in sums.items() if k.endswith('/all') or (k.startswith('v3/') and (v['guarded_coverage']<.9 or v['normal_base_revenue_loss_ratio']>.005))}},indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('phase',choices=SEEDS);run(p.parse_args().phase)

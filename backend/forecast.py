"""Active smooth NHPP with independently accepted revenue-aware protection.

The frozen model and both historical calibration attempts remain reproducible.
Only the decision guard changes here; predictive draws/quantiles are unchanged.
"""
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
from . import nhpp, nhpp_v3

ROOT=Path(__file__).resolve().parents[1]
CALIBRATION='simulation/generated/calibration_v3_robust.json'
VALIDATION='simulation/generated/nhpp_v3_robust_final.json'
POLICY='nhpp-v3-robust-guard-v1'


def _calibration_digest_matches(expected, raw):
    """Match original evidence across Git LF/Windows CRLF, with no content edits."""
    lf = raw.replace(b'\r\n', b'\n')
    return expected in {hashlib.sha256(value).hexdigest()
                        for value in (raw, lf, lf.replace(b'\n', b'\r\n'))}


@lru_cache(maxsize=4)
def _load(signature):
    cfg=json.loads((ROOT/CALIBRATION).read_text(encoding='utf-8'))
    report=json.loads((ROOT/VALIDATION).read_text(encoding='utf-8'))
    if cfg['model_version']!=nhpp_v3.VERSION or cfg['settings']!=nhpp_v3.SETTINGS:
        raise ValueError('NHPP calibration is stale')
    for name,digest in cfg['source_hashes'].items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=digest:
            raise ValueError('NHPP calibration source is stale: '+name)
    if (report.get('phase')!='final' or report.get('source_hashes')!=cfg['source_hashes']
            or report.get('seeds')!=cfg['seeds'] or report.get('protocol')!=cfg['protocol']
            or report.get('guards')!=cfg['comparison_guards']
            or not _calibration_digest_matches(report.get('calibration_sha256'), (ROOT/CALIBRATION).read_bytes())):
        raise ValueError('NHPP protection has no matching accepted independent validation')
    # A failed horizon falls back to the incumbent; never fit new guards on final.
    accepted=[];selected_models={}
    for day in (7,14,28):
        metrics=[v for k,v in report['summary'].items() if k.startswith(f'v3/D{day}/')]
        if len(metrics)!=7:raise ValueError('Incomplete NHPP independent validation')
        if all(v['guarded_coverage']>=cfg['protocol']['acceptance_group_coverage']
               and v['normal_base_revenue_loss_ratio']<=cfg['protocol']['acceptance_group_revenue_loss_ratio'] for v in metrics):
            accepted.append(day)
            selected_models[str(day)]='v3'
        else:
            incumbent=[v for k,v in report['summary'].items() if k.startswith(f'v2/D{day}/')]
            if len(incumbent)==7 and all(v['guarded_coverage']>=cfg['protocol']['acceptance_group_coverage']
                    and v['normal_base_revenue_loss_ratio']<=cfg['protocol']['acceptance_group_revenue_loss_ratio'] for v in incumbent):
                selected_models[str(day)]='v2'
    cfg['accepted_horizons']=accepted
    cfg['selected_models']=selected_models
    return cfg


def _configuration():
    paths=(CALIBRATION,VALIDATION,'backend/nhpp.py','backend/nhpp_v3.py','simulation/generate.py',
           'simulation/evaluate_nhpp_v3.py','simulation/calibrate_nhpp_v3_robust.py')
    try:
        signature=tuple((name,(ROOT/name).stat().st_mtime_ns,(ROOT/name).stat().st_size) for name in paths)
        return _load(signature)
    except (OSError,KeyError,TypeError,json.JSONDecodeError) as exc:
        raise ValueError('NHPP accepted calibration unavailable; automatic protection disabled') from exc


def forecast(rows, days_to_departure=28, seed=117, protection_allowance=None):
    if protection_allowance is not None or days_to_departure==0:
        return nhpp_v3.forecast(rows,days_to_departure,seed,protection_allowance)
    cfg=_configuration()
    horizons=sorted(map(int,cfg['relative_guard_by_horizon']))
    selected=next((h for h in horizons if h>=days_to_departure),horizons[-1])
    chosen=cfg['selected_models'].get(str(selected))
    if chosen is None:raise ValueError('No model passed independent protection criteria for this horizon')
    guards=cfg['comparison_guards'][chosen]
    predictor=nhpp_v3 if chosen=='v3' else nhpp
    p=predictor.forecast(rows,days_to_departure,seed,protection_allowance=0)
    def allowance(day,raw):
        if day==0:return 0
        selected=next((h for h in horizons if h>=day),horizons[-1])
        return math.ceil(guards[str(selected)]*max(10,raw))
    extra=allowance(days_to_departure,p['raw_protection_p90'])
    p['protection_allowance']=extra
    p['protection_p90']=p['raw_protection_p90']+extra
    p['releasable_seats']=min(p['releasable_seats'],max(0,p['available_seats']-p['protection_p90']))
    for row in p['protection_curve']:
        row['protection_allowance']=allowance(row['day'],row['raw_protection_p90'])
        row['protection_seats']=row['raw_protection_p90']+row['protection_allowance']
    p['protection_policy']=POLICY if chosen=='v3' else 'nhpp-v2-robust-guard-v1'
    p['diagnostics'].update(calibration_loaded=True,calibration_horizon_days=horizons,
                            calibration_artifact=CALIBRATION,independent_validation=VALIDATION,
                            smooth_candidate_accepted=chosen=='v3')
    if chosen=='v2':p['diagnostics']['fallback_reason']='Smooth candidate failed independent group revenue-loss gate; retain v2 distribution with independently validated v2 guard'
    p['assumptions'].append('Revenue-aware guard validated on independent synthetic flights; income metric is a no-cancellation capacity stress, not real profit.')
    return p

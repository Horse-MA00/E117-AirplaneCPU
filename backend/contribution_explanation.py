"""Derived contribution bridges from completed, paired market records.

This is a read-only explanation, not a new accounting policy, ranking or replay.
Old evidence stays unchanged. Missing pairs or accounting are unavailable rather
than silently replaced with zeros; inconsistencies remain visible as checks.
"""
from __future__ import annotations

import math
import statistics

VERSION = 'paired-contribution-explanation-v1'
COMPONENTS = (
    ('normal_base_revenue', 'Normal base fares', 'revenue'),
    ('member_base_revenue', 'Member base fares', 'revenue'),
    ('membership_revenue', 'Allocated new membership fees', 'revenue'),
    ('ancillary_revenue', 'Baggage and ancillary revenue', 'revenue'),
    ('cancellation_revenue', 'Cancellation fees retained', 'revenue'),
    ('passenger_cost', 'Incremental passenger costs', 'cost'),
    ('ancillary_cost', 'Baggage and ancillary costs', 'cost'),
    ('membership_service_cost', 'Allocated membership service costs', 'cost'),
    ('program_cost', 'Programme costs', 'cost'),
)
FLOW_FIELDS = ('cash_collected', 'refunds_paid', 'mandatory_remitted',
               'mandatory_liability', 'total_cost', 'contribution')
WORLD_TOLERANCE = .011
# Nine displayed component means and their displayed total each round to cents.
DISPLAY_TOLERANCE = (len(COMPONENTS) + 1) * .005


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _money_mean(values):
    return round(statistics.mean(values), 2)


def _close(left, right, tolerance=WORLD_TOLERANCE):
    return abs(left-right) <= tolerance + 1e-9


def _account(result):
    ledger = result.get('ledger', {})
    required = [key for key, _, _ in COMPONENTS] + list(FLOW_FIELDS)
    if any(not _number(ledger.get(key)) for key in required) or not _number(result.get('contribution')):
        return None
    allocation = result.get('annual_fee_allocation')
    if allocation is None:
        # Earlier full-market results use the unallocated cash contribution.
        if not _close(result['contribution'], ledger['contribution']):
            return None
        allocation = 1.
    if not _number(allocation) or not 0 <= allocation <= 1:
        return None
    components = {key: ledger[key] * (allocation if key in ('membership_revenue', 'membership_service_cost') else 1)
                  for key, _, _ in COMPONENTS}
    revenue = sum(components[key] for key, _, kind in COMPONENTS if kind == 'revenue')
    cost = sum(components[key] for key, _, kind in COMPONENTS if kind == 'cost')
    cash_revenue = sum(ledger[key] for key, _, kind in COMPONENTS if kind == 'revenue')
    checks = {
        'cash_identity': _close(ledger['cash_collected']-ledger['refunds_paid']-ledger['mandatory_remitted']-ledger['mandatory_liability'], cash_revenue),
        'cash_contribution': _close(cash_revenue-ledger['total_cost'], ledger['contribution']),
        'cash_costs': _close(sum(ledger[key] for key, _, kind in COMPONENTS if kind == 'cost'), ledger['total_cost']),
        'attributed_totals': _close(revenue-cost, result['contribution']),
        'reported_components': None,
        'group_attribution': None,
    }
    reported = result.get('profit_components')
    if reported is not None:
        checks['reported_components'] = all(_number(reported.get(key)) and _close(reported[key], value) for key,value in components.items())
    groups = result.get('profit_attribution')
    if groups is not None:
        checks['group_attribution'] = (all(_number(group.get('contribution')) for group in groups.values())
            and _close(sum(group['contribution'] for group in groups.values()), result['contribution']))
    return {'result':result, 'ledger':ledger, 'allocation':allocation, 'components':components,
            'revenue':revenue, 'cost':cost, 'checks':checks}


def _metric(reports, field):
    values = [report.get(field) for report in reports]
    return statistics.mean(values) if all(_number(value) for value in values) else None


def _service(reports, config, seeds):
    minimum = config['min_service_rate']
    if any(not all(_number(r.get(k)) for k in ('service_rate', 'new_members', 'member_flown')) for r in reports):
        return {'available':False, 'minimum_rate':minimum, 'rule':'every_replica', 'replicas':[], 'passed':None,
                'mean_rate':None, 'lowest_rate':None}
    replicas = []
    for seed, result in zip(seeds, reports):
        if config.get('scope'):
            passed = result['member_flown'] > 0 and (result['new_members'] == 0 or result['service_rate'] >= minimum)
        else:
            passed = result['new_members'] > 0 and result['service_rate'] >= minimum
        replicas.append({key:result[key] for key in ('new_members','service_rate','member_flown')} | {'seed':seed,'passed':passed})
    return {'available':True, 'minimum_rate':minimum, 'rule':'every_replica', 'replicas':replicas,
            'passed':all(row['passed'] for row in replicas),
            'mean_rate':statistics.mean(row['service_rate'] for row in replicas),
            'lowest_rate':min(row['service_rate'] for row in replicas)}


def _phase(config, worlds, expected_seeds, baseline_phase, offer_phase, round_number):
    selected = [w for w in worlds if w.get('status') == 'completed' and w.get('result') is not None]
    baseline = [w for w in selected if w['phase'] == baseline_phase]
    offer = [w for w in selected if w['phase'] == offer_phase and w.get('round_number') == round_number]
    expected_seeds = sorted(expected_seeds)
    pairing = {'seeds':expected_seeds, 'expected_replicas':len(expected_seeds), 'complete':False}
    if (sorted(w['seed'] for w in baseline) != expected_seeds or
            sorted(w['seed'] for w in offer) != expected_seeds):
        return {'available':False, 'reason':'Completed matching baseline and offer worlds are not available for every expected seed.', 'pairing':pairing}
    baseline.sort(key=lambda w:w['seed']); offer.sort(key=lambda w:w['seed'])
    if any(not isinstance(left['result'].get('exogenous_sha256'), str)
           or not left['result']['exogenous_sha256']
           or left['result']['exogenous_sha256'] != right['result'].get('exogenous_sha256')
           for left,right in zip(baseline,offer)):
        return {'available':False, 'reason':'Matching seeds refer to different or unverifiable exogenous markets; a paired contribution comparison is unavailable.', 'pairing':pairing}
    pairing['complete'] = True
    b = [_account(w['result']) for w in baseline]; o = [_account(w['result']) for w in offer]
    if not b or any(x is None for x in [*b,*o]):
        return {'available':False, 'reason':'Saved accounting or membership allocation is missing; no zero-filled explanation was generated.', 'pairing':pairing}
    rows = []
    for key, label, kind in COMPONENTS:
        change = _money_mean([right['components'][key]-left['components'][key] for left,right in zip(b,o)])
        rows.append({'id':key,'label':label,'kind':kind,
                     'baseline':_money_mean([x['components'][key] for x in b]),
                     'offer':_money_mean([x['components'][key] for x in o]),
                     'change':change,'contribution_effect':change if kind=='revenue' else -change})
    baseline_contribution = _money_mean([x['result']['contribution'] for x in b])
    offer_contribution = _money_mean([x['result']['contribution'] for x in o])
    incremental = _money_mean([right['result']['contribution']-left['result']['contribution'] for left,right in zip(b,o)])
    checks = {}
    for key in b[0]['checks']:
        values = [x['checks'][key] for x in [*b,*o]]
        checks[key] = False if False in values else None if None in values else True
    checks['component_bridge'] = _close(sum(row['contribution_effect'] for row in rows), incremental, DISPLAY_TOLERANCE)
    b_reports=[x['result'] for x in b]; o_reports=[x['result'] for x in o]
    b_buyers=_metric(b_reports,'buyers'); o_buyers=_metric(o_reports,'buyers')
    allocations=sorted(set(x['allocation'] for x in [*b,*o]))
    return {'available':True,'pairing':pairing,'baseline_contribution':baseline_contribution,
            'offer_contribution':offer_contribution,'incremental_contribution':incremental,'components':rows,
            'totals':{'baseline_revenue':_money_mean([x['revenue'] for x in b]),
                      'offer_revenue':_money_mean([x['revenue'] for x in o]),
                      'baseline_cost':_money_mean([x['cost'] for x in b]),
                      'offer_cost':_money_mean([x['cost'] for x in o])},
            'cash_view':{'baseline_contribution':_money_mean([x['ledger']['contribution'] for x in b]),
                         'offer_contribution':_money_mean([x['ledger']['contribution'] for x in o]),
                         'incremental_contribution':_money_mean([right['ledger']['contribution']-left['ledger']['contribution'] for left,right in zip(b,o)])},
            'cash_flow':{label:{key:_money_mean([x['ledger'][key] for x in accounts]) for key in FLOW_FIELDS}
                         for label,accounts in [('baseline',b),('offer',o)]},
            'annual_fee_allocation':allocations[0] if len(allocations)==1 else None,'allocation_values':allocations,
            'buyers':{'baseline':b_buyers,'offer':o_buyers,
                      'net_change':o_buyers-b_buyers if b_buyers is not None and o_buyers is not None else None,
                      'baseline_fulfilled':_metric(b_reports,'fulfilled_buyers'),
                      'offer_fulfilled':_metric(o_reports,'fulfilled_buyers')},
            'service_requirement':_service(o_reports,config,expected_seeds),
            'reconciliation':{'tolerance_hkd':DISPLAY_TOLERANCE,'individual_world_tolerance_hkd':WORLD_TOLERANCE,
                              'checks':checks,'passed':all(value is not False for value in checks.values())}}


def describe_track(config, track, worlds):
    """Explain the retained search candidate and independent validation, by seed."""
    worlds = [w for w in worlds if w.get('mode') == track['mode']]
    best = track.get('best')
    missing = {'available':False,'reason':'No retained candidate is available for a paired contribution explanation.'}
    if best is None:
        return {'version':VERSION,'search':dict(missing),'validation':dict(missing),
                'no_offer_reasons':[track.get('decision_reason') or 'No informative candidate was retained.'] if track.get('decision')=='NO_OFFER' else []}
    search_seeds = [config['seed']+i*101 for i in range(config['replicates'])]
    validation_seeds = [config['seed']+50003+i*101 for i in range(2)]
    search = _phase(config,worlds,search_seeds,'baseline','search',best['round'])
    validation = _phase(config,worlds,validation_seeds,'holdout_baseline','holdout',0)
    reasons = []
    if track.get('decision')=='NO_OFFER':
        for label,phase in [('Search',search),('Validation',validation)]:
            if not phase['available']:
                continue
            if phase['incremental_contribution'] <= 0:
                reasons.append(f"{label} incremental contribution is HK${phase['incremental_contribution']:.2f}; publication requires a positive improvement over the matched no-offer market.")
            service=phase['service_requirement']
            for replica in service['replicas']:
                if not replica['passed']:
                    if replica['new_members'] and replica['service_rate'] < service['minimum_rate']:
                        reasons.append(f"{label} seed {replica['seed']}: {replica['service_rate']:.0%} of new members flew versus the {service['minimum_rate']:.0%} minimum. Every replica must pass; the mean does not override this failure.")
                    else:
                        reasons.append(f"{label} seed {replica['seed']}: the per-replica member-use requirement was not met (new members: {replica['new_members']}; member seats flown: {replica['member_flown']}).")
        if not reasons:
            reasons.append('The saved policy was not accepted; complete paired accounting is unavailable or another saved feasibility requirement failed.')
    return {'version':VERSION,'search':search,'validation':validation,'no_offer_reasons':reasons}

"""Joint membership/fare feedback search with independent math and LLM tracks.

Finite, auditable pattern search in a synthetic market. Each iteration evaluates
one price pair, not a model-training epoch. NHPP remains frozen; world outcomes
are used for policy selection, never passed to the traveller decision provider.
"""
from __future__ import annotations
import hashlib
import json
import math
import os
from pathlib import Path
import re
import statistics
import threading
import time
import uuid

from . import optimization_store as store
from llm_agent.file_lock import exclusive_lock

VERSION = 'flight-policy-feedback-v6-formula-grid'
FORMULA_GRID = 'formula-p-star-fine-grid-v1'
CONTROLLED_PRICE_PROTOCOL = 'fixed-seat-profile-local-fare-v1'
ROOT = Path(__file__).resolve().parents[1]
_lock = threading.RLock()
_active = set()


def _number(value, name, low, high, integer=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high or (integer and int(value) != value):
        raise ValueError(f'{name} must be {low}..{high}' + (' (integer)' if integer else ''))
    return int(value) if integer else float(value)


def validate(body):
    if not isinstance(body, dict):
        raise ValueError('JSON object required')
    scope = None
    if body.get('flight_id'):
        from backend.initial_policy import flight_scope
        scope = flight_scope(body['flight_id'], body.get('forecast_day', 28))
        body = {**body, 'initial_member_fare': scope['initial_member_fare'], 'fee_min':0, 'fee_max':5000}
        # Member fares never exceed 50% of the normal base fare; a wider requested
        # upper bound is narrowed to the cap so no candidate can be proposed above it.
        cap = scope['member_fare_cap']
        requested = body.get('fare_max', cap)
        body['fare_max'] = min(requested, cap) if isinstance(requested, (int, float)) and not isinstance(requested, bool) else requested
    options = {
        'rounds': (5, 1, 12, True), 'customers': (14, 1, 100, True), 'flights': (6, 6, 12, True),
        'replicates': (1, 1, 3, True), 'seed': (117, 0, 2**31-100000, True),
        'initial_member_fare': (70, 0, 2000, False), 'initial_membership_fee': (399, 0, 5000, False),
        'fare_min': (0, 0, 2000, False), 'fare_max': (500, 0, 2000, False),
        'fee_min': (0, 0, 5000, False), 'fee_max': (1500, 0, 5000, False),
        'release_fraction': (.5, 0, 1, False), 'min_service_rate': (.6, 0, 1, False),
        'program_cost': (1500, 0, 10000, False), 'max_calls': (60, 0, 120, True),
    }
    cfg = {key: _number(body.get(key, default), key, low, high, integer)
           for key, (default, low, high, integer) in options.items()}
    cfg['mode'] = body.get('mode', 'math')
    if cfg['mode'] not in ('math', 'live', 'both'):
        raise ValueError('mode must be math, live or both')
    for axis, initial in (('fare', 'initial_member_fare'), ('fee', 'initial_membership_fee')):
        if not cfg[axis + '_min'] <= cfg[initial] <= cfg[axis + '_max'] or cfg[axis + '_min'] >= cfg[axis + '_max']:
            raise ValueError(f'{axis} bounds must contain the initial price and have nonzero width')
        if round(cfg[axis + '_max'] * 100) <= round(cfg[axis + '_min'] * 100):
            raise ValueError(f'{axis} interval must span at least one cent')
    for key in ('initial_member_fare', 'initial_membership_fee', 'fare_min', 'fare_max', 'fee_min', 'fee_max'):
        cfg[key] = round(cfg[key], 2)
    if scope:
        cfg.update(scope=scope, flight_id=scope['flight_id'], forecast_day=scope['as_of_day'], flights=1,
                   membership_fee_fixed=True, annual_fee_allocation=1/3,
                   price_comparison_protocol=CONTROLLED_PRICE_PROTOCOL)
    total = body.get('total_live_budget', 1500 if scope and cfg['mode'] != 'math' else None)
    if total is not None:
        cfg['total_live_budget'] = _number(total,'total_live_budget',0,10000,True)
        if total > 0 and cfg['mode'] != 'math' and cfg['max_calls'] == 0:
            raise ValueError('max_calls must be at least 1 for automatic live batches')
    return cfg


def _modes(config):
    return ['math', 'live'] if config['mode'] == 'both' else [config['mode']]


def _rounds(config, mode):
    """The mathematical track evaluates the formula estimate P* and a fixed fine grid around it."""
    if mode == 'math' and config.get('math_search') == FORMULA_GRID:
        return len(config['formula_estimate']['grid'])
    return config['rounds']


def _id(run_id):
    if not isinstance(run_id, str) or not re.fullmatch(r'opt-[a-f0-9]{16}', run_id):
        raise ValueError('Invalid optimization run ID')
    return run_id


def provenance():
    files = ['backend/optimization.py', 'backend/optimization_store.py', 'backend/shared_market.py', 'backend/scoped_market.py', 'backend/initial_policy.py', 'backend/data.py', 'backend/contribution_explanation.py',
             'backend/probabilistic_customer.py', 'backend/fare_estimate.py', 'backend/nhpp.py', 'backend/release_policy.py', 'backend/seat_feedback.py',
             'simulation/generate.py', 'simulation/generated/calibration_v2.json',
             'llm_agent/market_adapter.py', 'llm_agent/population.py', 'llm_agent/output_contract.py',
             'llm_agent/prompts/shared_market_v3_en.txt']
    if (ROOT/'simulation/network_generated/manifest.json').exists():
        files.append('simulation/network_generated/manifest.json')
    if (ROOT/'simulation/member_demo_generated/manifest.json').exists():
        files.append('simulation/member_demo_generated/manifest.json')
    return {'version': VERSION, 'files': {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in files},
            'provider_model': os.environ.get('LLM_MODEL'),
            'provider_endpoint_sha256': hashlib.sha256(os.environ.get('LLM_API_URL', '').encode()).hexdigest()}


def best_candidate(rows):
    rows = [r for r in rows if not r.get('price_evidence_status','').startswith('uninformative_')]
    if not rows:
        return None
    # Service feasibility outranks revenue; if none feasible, retain a diagnostic hypothesis.
    return max(rows, key=lambda row: (row['feasible'], row['incremental_contribution'],
                                      -row['membership_fee'], -row['member_fare']))


def propose(config, rows, mode=None):
    """Feedback-guided 2D pattern search, bounded and quantized to HKD cents."""
    if mode == 'math' and config.get('math_search') == FORMULA_GRID:
        grid = config['formula_estimate']['grid']
        if len(rows) >= len(grid):
            return None
        return {'member_fare': grid[len(rows)], 'membership_fee': config['initial_membership_fee'],
                'search_step': 'formula_p_star' if not rows else 'fine_grid'}
    if not rows:
        return {'member_fare': config['initial_member_fare'], 'membership_fee': config['initial_membership_fee'],
                **({'search_step':'initial_snapshot'} if config.get('price_comparison_protocol') else {})}
    if config.get('price_comparison_protocol') == CONTROLLED_PRICE_PROTOCOL:
        return _propose_scoped(config, rows)
    best = best_candidate(rows)
    seen = {(round(row['member_fare'] * 100), round(row['membership_fee'] * 100)) for row in rows}
    directions = [(-1, 0), (0, -1), (1, 0), (0, 1), (-1, -1), (1, 1), (-1, 1), (1, -1)]
    if config.get('membership_fee_fixed'):
        directions = [(-1, 0), (1, 0)]
    phase = (len(rows)-1) // len(directions)
    offset = (len(rows)-1) % len(directions)
    bounds = [(round(config['fare_min']*100), round(config['fare_max']*100)),
              (round(config['fee_min']*100), round(config['fee_max']*100))]
    steps = [max(1, round((hi-lo) / (4 * 2**phase))) for lo, hi in bounds]
    center = (round(best['member_fare']*100), round(best['membership_fee']*100))
    for shift in range(len(directions)):
        direction = directions[(offset+shift) % len(directions)]
        point = tuple(max(lo, min(hi, c + sign*step)) for c, sign, step, (lo, hi) in zip(center, direction, steps, bounds))
        if point not in seen:
            return {'member_fare': point[0]/100, 'membership_fee': point[1]/100}
    # On a bound, try progressively smaller moves before a deterministic broad probe.
    for divisor in (2, 4, 8, 16):
        for direction in directions:
            point = tuple(max(lo, min(hi, c+sign*max(1, step//divisor))) for c, sign, step, (lo, hi) in zip(center, direction, steps, bounds))
            if point not in seen:
                return {'member_fare': point[0]/100, 'membership_fee': point[1]/100}
    for left in range(bounds[0][0], min(bounds[0][1]+1, bounds[0][0]+13)):
        fees = [round(config['initial_membership_fee']*100)] if config.get('membership_fee_fixed') else range(bounds[1][0], min(bounds[1][1]+1,bounds[1][0]+13))
        for right in fees:
            if (left, right) not in seen:
                return {'member_fare': left/100, 'membership_fee': right/100}
    # A tiny complete domain may have fewer unique points than the requested budget.
    return None


def _propose_scoped(config, rows):
    """Local probes first, then explicit bounded exploration; never rewrite prior tests."""
    low, high = (round(config[k]*100) for k in ('fare_min','fare_max'))
    initial = round(config['initial_member_fare']*100)
    fee = config['initial_membership_fee']
    seen = {round(r['member_fare']*100) for r in rows}
    # A zero P0 has no relative scale; use 5% of the permitted span as its step.
    step = max(1,round(initial*.25) if initial else round((high-low)*.05))
    probes = [(initial-step,'local_lower'),(initial+step,'local_upper'),
              (low,'boundary_low'),(min(high,initial+max(step*2,round((high-low)*.25))),'wide_upper'),
              (high,'boundary_high')]
    for point,label in probes:
        point = max(low,min(high,point))
        if point not in seen:
            return {'member_fare':point/100,'membership_fee':fee,'search_step':label}
    best = best_candidate(rows)
    center = round(best['member_fare']*100) if best else initial
    for divisor in (2,4,8,16,32):
        for sign in (-1,1):
            point=max(low,min(high,center+sign*max(1,step//divisor)))
            if point not in seen:
                return {'member_fare':point/100,'membership_fee':fee,'search_step':'local_refinement'}
    for point in range(low,min(high+1,low+13)):
        if point not in seen:
            return {'member_fare':point/100,'membership_fee':fee,'search_step':'bounded_exploration'}
    return None


def _seeds(config, holdout=False):
    return [config['seed'] + (50003 if holdout else 0) + i*101
            for i in range(2 if holdout else config['replicates'])]


def _progress(run_id, **changes):
    current = store.run(run_id)['progress']
    current.update(changes)
    with store.connection() as db:
        current['completed_worlds'] = db.execute("SELECT COUNT(*) FROM optimization_worlds WHERE run_id=? AND status='completed'", (run_id,)).fetchone()[0]
        current['completed_rounds'] = db.execute('SELECT COUNT(*) FROM optimization_rounds WHERE run_id=?', (run_id,)).fetchone()[0]
    store.update(run_id, progress=current)


def _counts(run_id, **increments):
    counts = store.run(run_id)['counts']
    for key, value in increments.items():
        counts[key] = counts.get(key, 0) + value
    store.update(run_id, counts=counts)


class Paused(Exception):
    pass


def _world(run_id, mode, phase, round_number, seed, prices, enabled, budget):
    from backend.shared_market import create_market, next_observation, apply_decision, summarize
    from llm_agent.market_adapter import choose, legal_choices, public_observation
    cfg = store.run(run_id)['config']
    world_id = f'{run_id}-{mode}-{phase}-{round_number}-{seed}'
    stored = store.world(world_id)
    if stored and stored['result'] is not None:
        return stored['result']
    if stored:
        state = stored['state']
    else:
        policy = {'name': 'OPTIMIZATION' if enabled else 'NO_OFFER', 'enabled': enabled,
                  **prices, 'release_fraction': cfg['release_fraction'], 'open_day': 28}
        market_config = {'customer_count': cfg['customers'], 'flight_count': cfg['flights'],
                         'occasions_per_customer': 3, 'program_cost': cfg['program_cost']}
        if cfg.get('scope'):
            from backend.scoped_market import create_scoped_market
            state = create_scoped_market(cfg['scope'], market_config, seed, policy)
        else:
            state = create_market(market_config, seed, policy)
        with store.connection() as db:
            db.execute('INSERT INTO optimization_worlds VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                       (world_id, run_id, mode, phase, round_number, seed, store.encode(policy),
                        store.encode(state), None, 'running', time.time()))
    audit = store.SqlAudit(run_id, world_id)
    steps = 0
    _progress(run_id, active_mode=mode, phase=phase, active_round=round_number, active_world=world_id)
    while (observation := next_observation(state)) is not None:
        forced = len(legal_choices(public_observation(observation))) == 1
        if mode == 'live' and not forced:
            # Every non-forced attempt (including cache) uses a slot. Reserve before
            # transport so a crash cannot silently exceed a user-approved batch.
            if budget['used'] >= budget['max']:
                store.checkpoint(world_id, state)
                raise Paused('Internal live batch completed.')
            budget['used'] += 1
            _counts(run_id, live_attempts=1)
            store.checkpoint(world_id, state)
            audit.append({'event': 'optimization_live_attempt_reserved', 'packet_id': observation['packet_id']})
        try:
            choice = choose(observation, 'probabilistic' if mode == 'math' else 'live', audit)
            transition = apply_decision(state, choice['decision'])
            if cfg.get('scope'):
                exposure = state.setdefault('member_offer_exposure',{'packet_ids':[],'customer_ids':[],'bookable_packet_ids':[]})
                offered = any(o.get('action')=='BUY_MEMBER' for o in [*observation.get('options',[]),*observation.get('current_quote_reference',[])])
                if offered:
                    if observation['packet_id'] not in exposure['packet_ids']:
                        exposure['packet_ids'].append(observation['packet_id'])
                    if observation['customer_id'] not in exposure['customer_ids']:
                        exposure['customer_ids'].append(observation['customer_id'])
                    if 'BUY_MEMBER' in observation['allowed_actions'] and observation['packet_id'] not in exposure['bookable_packet_ids']:
                        exposure['bookable_packet_ids'].append(observation['packet_id'])
        except Exception:
            store.checkpoint(world_id, state)
            raise
        steps += 1
        # A result's complete feedback is durable independently of the snapshot.
        store.apply_transition(run_id, world_id, state, {'event': 'optimization_transition', 'mode': mode, 'phase': phase,
                      'round': round_number, 'observation': public_observation(observation),
                      'decision': choice['decision'], 'transition': transition, 'source': choice['source'],
                      'cache_hit': choice.get('cache_hit', False), 'provider_call': choice.get('provider_call', False)})
    result = summarize(state)
    if not result['complete'] or not all(result['checks'].values()):
        store.checkpoint(world_id, state)
        raise ValueError('Market accounting invariant failed; no candidate was ranked')
    from backend.seat_feedback import collect_samples, diagnostics
    result['seat_feedback_samples'] = collect_samples(state)
    result['forecast_feedback'] = diagnostics(result['seat_feedback_samples'])
    if cfg.get('scope'):
        from backend.scoped_market import attribute_result
        result = attribute_result(result, state)
    store.checkpoint(world_id, state, result)
    _progress(run_id)
    return result


def aggregate(prices, reports, baselines, config):
    for actual, baseline in zip(reports, baselines):
        if actual['exogenous_sha256'] != baseline['exogenous_sha256']:
            raise ValueError('Policy and no-offer worlds are not matched')
    deltas = [r['contribution']-b['contribution'] for r, b in zip(reports, baselines)]
    revenue = statistics.mean(r.get('attributed_revenue',r.get('ledger',{}).get('revenue_excluding_mandatory_fees',0)) for r in reports)
    cost = statistics.mean(r.get('attributed_cost',r.get('ledger',{}).get('total_cost',0)) for r in reports)
    contribution = round(statistics.mean(r['contribution'] for r in reports),2)
    result = {**prices, 'incremental_contribution': round(statistics.mean(deltas), 2),
            'total_contribution': contribution, 'profit':contribution,
            # Matched no-offer world: what this flight earns without the membership offer.
            'baseline_contribution': round(statistics.mean(b['contribution'] for b in baselines), 2),
            'attributed_revenue':round(revenue,2),'attributed_cost':round(cost,2),
            'profit_margin': contribution/revenue if revenue > 0 else None,
            'mean_buyers':statistics.mean(r.get('buyers',r.get('agent_completed_trips',0)) for r in reports),
            'mean_tickets':statistics.mean(r.get('tickets',r.get('passengers_flown',0)) for r in reports),
            'paired_differences': [round(x, 2) for x in deltas],
            'paired_variance': statistics.variance(deltas) if len(deltas)>1 else None,
            'standard_error': statistics.stdev(deltas)/math.sqrt(len(deltas)) if len(deltas)>1 else None,
            'service_rate': statistics.mean(r['service_rate'] for r in reports),
            'mean_members': statistics.mean(r['new_members'] for r in reports),
            'mean_member_trips': statistics.mean(r['member_flown'] for r in reports),
            'mean_normal_trips': statistics.mean(r['normal_seats_flown'] for r in reports),
            'contribution': round(statistics.mean(r['contribution'] for r in reports), 2),
            'feasible': all((r['member_flown'] > 0 and (r['new_members'] == 0 or r['service_rate'] >= config['min_service_rate']))
                            if config.get('scope') else (r['new_members'] > 0 and r['service_rate'] >= config['min_service_rate']) for r in reports),
            'checks_passed': all(all(r['checks'].values()) for r in reports),
            'seeds': [r['seed'] for r in reports]}
    if config.get('price_comparison_protocol') == CONTROLLED_PRICE_PROTOCOL:
        metric_fields = ('member_buyers','regular_buyers','member_tickets','regular_tickets',
                         'fulfilled_buyers','fulfilled_tickets','fulfilled_bookings','cancelled_bookings',
                         'cancelled_tickets','member_seats_released','member_offer_observations',
                         'member_offer_customers','member_bookable_observations')
        result.update({f'mean_{key}':statistics.mean(r.get(key,0) for r in reports) for key in metric_fields})
        result['mean_new_members'] = result['mean_members']
        result['member_supply_exposure'] = statistics.mean(r.get('member_supply_exposure',0) for r in reports)
        if not any(r.get('member_supply_exposure',0)>0 for r in reports):
            status = 'uninformative_no_supply'
        elif not any(r.get('member_offer_observations',0)>0 for r in reports):
            status = 'uninformative_no_member_exposure'
        elif not any(r.get('member_tickets',0)>0 for r in reports):
            status = 'no_member_sales'
        else:
            status = 'observed_member_sales'
        components = set().union(*(r.get('profit_components',{}) for r in [*reports,*baselines]))
        result.update(price_evidence_status=status, price_evidence_qualified=not status.startswith('uninformative_'),
            price_evidence_qualification=(
                'No member supply was offered; ordinary purchases and cancellation variation are not member-price evidence.' if status=='uninformative_no_supply' else
                'Quota was released but no matching agent saw a member offer; this is not a test of willingness to buy.' if status=='uninformative_no_member_exposure' else
                'Agents saw member offers but bought no member tickets. Ordinary sales or cancellation differences do not identify a member-fare effect.' if status=='no_member_sales' else
                'Synthetic paired policy outcomes, not observed price elasticity. LLM choices may vary across calls; paired component differences expose other behavioral changes.'),
            seat_feedback_application='proposed_only_fixed_during_price_comparison',
            profit_components={k:round(statistics.mean(r.get('profit_components',{}).get(k,0) for r in reports),2) for k in sorted(components)},
            paired_component_deltas={k:round(statistics.mean(r.get('profit_components',{}).get(k,0)-b.get('profit_components',{}).get(k,0)
                for r,b in zip(reports,baselines)),2) for k in sorted(components)})
        result['profit_attribution'] = {group:{key:round(statistics.mean(r.get('profit_attribution',{}).get(group,{}).get(key,0)
            for r in reports),2) for key in ('revenue','cost','contribution')} for group in ('agent','background','program')}
        if status.startswith('uninformative_'):
            result['feasible'] = False
    return result


def run_batch(run_id, max_calls=60):
    """Synchronous worker entry; HTTP uses start/resume to run it in background."""
    run_id = _id(run_id)
    max_calls = _number(max_calls, 'max_calls', 0, 120, True)
    saved = store.run(run_id)
    cfg = saved['config']
    if saved['provenance'] != provenance():
        raise ValueError('Implementation or provider changed; start a new run to preserve experiment provenance')
    from backend.seat_feedback import initial_profile, update_profile, diagnostics
    budget = {'used': 0, 'max': max_calls}
    for mode in _modes(cfg):
        initial = {'member_fare': cfg['initial_member_fare'], 'membership_fee': cfg['initial_membership_fee'], 'seat_calibration': initial_profile()}
        baseline = [_world(run_id, mode, 'baseline', 0, seed, initial, False, budget) for seed in _seeds(cfg)]
        for number in range(1, _rounds(cfg, mode)+1):
            rows = store.rounds(run_id, mode)
            if len(rows) >= number:
                continue
            prices = propose(cfg, rows, mode)
            if prices is None:
                break
            controlled = cfg.get('price_comparison_protocol') == CONTROLLED_PRICE_PROTOCOL
            prices['seat_calibration'] = initial_profile() if controlled or not rows else rows[-1]['next_seat_calibration']
            reports = [_world(run_id, mode, 'search', number, seed, prices, True, budget) for seed in _seeds(cfg)]
            result = aggregate(prices, reports, baseline, cfg)
            samples = [sample for report in reports for sample in report['seat_feedback_samples']]
            result.update(round=number, mode=mode, seat_feedback=diagnostics(samples),
                          next_seat_calibration=update_profile(prices['seat_calibration'], samples))
            best = best_candidate([*rows, result])
            result['accepted'] = best is result
            result['incumbent'] = {key: best[key] for key in ('member_fare', 'membership_fee', 'incremental_contribution', 'feasible')} if best else None
            with store.connection() as db:
                db.execute('INSERT INTO optimization_rounds VALUES (?,?,?,?)', (run_id, mode, number, store.encode(result)))
            store.record(run_id, None, {'event': 'optimization_round_completed', 'mode': mode, 'result': result})
            _progress(run_id)
            if controlled and result.get('price_evidence_status')=='uninformative_no_supply':
                store.record(run_id,None,{'event':'optimization_no_member_supply','mode':mode,
                    'reason':'All completed replicas released zero member seats through their remaining release rounds; no price hypothesis retained.'})
                break
        best = best_candidate(store.rounds(run_id, mode))
        if best is None:
            continue
        prices = {key: best[key] for key in ('member_fare', 'membership_fee', 'seat_calibration')}
        test_baseline = [_world(run_id, mode, 'holdout_baseline', 0, seed, initial, False, budget) for seed in _seeds(cfg, True)]
        tests = [_world(run_id, mode, 'holdout', 0, seed, prices, True, budget) for seed in _seeds(cfg, True)]
        result = aggregate(prices, tests, test_baseline, cfg)
        # Holdout only accepts/rejects a frozen hypothesis; it cannot replace it.
        store.record(run_id, None, {'event': 'optimization_holdout_completed', 'mode': mode, 'result': result})
    _progress(run_id, phase='completed', active_mode=None, active_world=None)
    if cfg.get('price_comparison_protocol') == CONTROLLED_PRICE_PROTOCOL:
        completed = store.run(run_id)['progress']
        if completed['completed_rounds'] < completed['total_rounds'] or completed['completed_worlds'] < completed['total_worlds']:
            _progress(run_id, planned_total_rounds=completed['total_rounds'],
                      planned_total_worlds=completed['total_worlds'],
                      total_rounds=completed['completed_rounds'], total_worlds=completed['completed_worlds'],
                      early_stopped=True)
    store.update(run_id, status='completed', error=None)


def _worker(run_id, max_calls, process_lock):
    try:
        store.update(run_id, status='running', error=None)
        while True:
            saved = store.run(run_id)
            total = saved['config'].get('total_live_budget')
            if total is not None and total > saved['counts']['live_attempts'] and max_calls == 0 and saved['config']['mode'] != 'math':
                raise ValueError('max_calls must be at least 1 for automatic live batches')
            limit = max_calls if total is None else min(max_calls,max(0,total-saved['counts']['live_attempts']))
            try:
                run_batch(run_id, limit)
                break
            except Paused:
                saved = store.run(run_id)
                remaining = None if total is None else max(0,total-saved['counts']['live_attempts'])
                _progress(run_id,live_budget_remaining=remaining,
                          automatic_batches=saved['progress'].get('automatic_batches',0)+1)
                if total is None or remaining <= 0:
                    raise Paused('Authorized live decision limit reached. Add decision budget to continue this saved run.')
                store.record(run_id,None,{'event':'optimization_automatic_batch','remaining_authorized_decisions':remaining})
    except Paused as error:
        store.update(run_id, status='paused', error=str(error))
    except Exception as error:
        from llm_agent.audit import sanitize
        store.update(run_id, status='failed', error=sanitize(str(error)))
    finally:
        process_lock.__exit__(None, None, None)
        with _lock:
            _active.discard(run_id)


def _launch(run_id, max_calls):
    with _lock:
        if _active:
            raise ValueError('An optimization batch is already running')
        process_lock = exclusive_lock(store.BASE / '.worker.lock')
        process_lock.__enter__()
        _active.add(run_id)
        try:
            store.update(run_id, status='queued', error=None)
            threading.Thread(target=_worker, args=(run_id, max_calls, process_lock), daemon=True).start()
        except Exception:
            _active.discard(run_id)
            process_lock.__exit__(None, None, None)
            raise
    return {'run_id': run_id, 'status': 'queued'}


def start(body):
    if not isinstance(body, dict) or not body.get('flight_id') and body.get('legacy_market') is not True:
        raise ValueError('Select a flight_id and forecast_day before starting optimization')
    cfg = validate(body)
    if cfg.get('scope'):
        if not cfg['scope']['optimization_eligible']:
            raise ValueError(cfg['scope']['optimization_unavailable_reason'])
        if math.floor(cfg['scope']['releasable_seats']*cfg['release_fraction']) < 1:
            raise ValueError('No releasable member seats at the selected round under this release fraction. Increase the fraction or choose another flight or release day.')
    from llm_agent.experiment import load_local_env
    load_local_env()
    if cfg['mode'] != 'math' and not all(os.environ.get(key) for key in ('LLM_API_URL', 'LLM_API_KEY', 'LLM_MODEL')):
        raise ValueError('Live provider is not configured')
    run_id = 'opt-' + uuid.uuid4().hex[:16]
    modes = _modes(cfg)
    if cfg.get('scope') and 'math' in modes:
        # Mathematical track: closed-form scan over every fare, then simulate P* and a fine grid.
        from backend.fare_estimate import estimate
        cfg['math_search'] = FORMULA_GRID
        cfg['formula_estimate'] = estimate(cfg, _seeds(cfg))
    progress = {'completed_rounds': 0, 'total_rounds': sum(_rounds(cfg, m) for m in modes), 'completed_worlds': 0,
                'total_worlds': sum(cfg['replicates']*(_rounds(cfg, m)+1)+4 for m in modes),
                'active_mode': None, 'phase': 'queued', 'active_round': 0}
    counts = dict.fromkeys(('provider_calls', 'cache_hits', 'forced', 'math_choices', 'failures', 'live_attempts'), 0)
    with store.connection() as db:
        db.execute('INSERT INTO optimization_runs VALUES (?,?,?,?,?,?,?,?,?)',
                   (run_id, 'created', store.encode(cfg), store.encode(provenance()), store.encode(progress),
                    store.encode(counts), time.time(), time.time(), None))
    try:
        return _launch(run_id, cfg['max_calls'])
    except Exception as error:
        store.update(run_id, status='failed', error=str(error))
        raise


def resume(run_id, body=None):
    run_id = _id(run_id)
    if body is not None and not isinstance(body, dict):
        raise ValueError('JSON object required')
    from llm_agent.experiment import load_local_env
    load_local_env()
    batch = _number((body or {}).get('max_calls',60),'max_calls',0,120,True)
    with _lock:
        if _active:
            raise ValueError('An optimization batch is already running')
        saved = store.run(run_id)
        if saved['status'] == 'completed':
            raise ValueError('Run already completed')
        cfg = saved['config']
        if cfg.get('total_live_budget') is not None:
            additional = _number((body or {}).get('additional_live_budget',0),'additional_live_budget',0,10000,True)
            total = cfg['total_live_budget']+additional
            if total > 10000:
                raise ValueError('Cumulative authorized live limit cannot exceed 10000')
            if total <= saved['counts']['live_attempts']:
                raise ValueError('Add additional_live_budget to continue after the authorized limit')
            if batch == 0 and cfg['mode'] != 'math':
                raise ValueError('max_calls must be at least 1 for automatic live batches')
            store.update(run_id,config={**cfg,'total_live_budget':total})
        try:
            return _launch(run_id,batch)
        except Exception:
            store.update(run_id,config=cfg)
            raise


def read(run_id):
    run_id = _id(run_id)
    saved = store.run(run_id)
    cfg = saved['config']
    if saved['status'] in ('queued', 'running') and run_id not in _active:
        saved['status'] = 'interrupted'
    tracks = []
    for mode in _modes(cfg):
        rows = store.rounds(run_id, mode)
        best = best_candidate(rows)
        with store.connection() as db:
            world_rows = db.execute("SELECT mode,phase,round_number,seed,result,status FROM optimization_worlds WHERE run_id=? AND mode=? AND status='completed' AND (phase IN ('baseline','holdout','holdout_baseline') OR (phase='search' AND round_number=?)) ORDER BY seed", (run_id, mode, best['round'] if best else -1)).fetchall()
        worlds = [{**dict(row), 'result':json.loads(row['result'])} for row in world_rows]
        actual = [row['result'] for row in worlds if row['phase']=='holdout']
        baseline = [row['result'] for row in worlds if row['phase']=='holdout_baseline']
        validation = None
        if best and len(actual) == len(baseline) == 2:
            validation = aggregate({key: best[key] for key in ('member_fare', 'membership_fee', 'seat_calibration')}, actual, baseline, cfg)
            from backend.seat_feedback import diagnostics
            validation['seat_feedback'] = diagnostics([sample for report in actual for sample in report['seat_feedback_samples']])
        decision = 'PENDING'
        if validation is not None:
            decision = 'OFFER' if best['feasible'] and best['incremental_contribution'] > 0 and validation['feasible'] and validation['incremental_contribution'] > 0 else 'NO_OFFER'
        elif rows and best is None and saved['status']=='completed':
            decision = 'NO_OFFER'
        track = {'mode': mode, 'rounds': rows, 'best': best, 'validation': validation, 'decision': decision}
        if cfg.get('price_comparison_protocol') == CONTROLLED_PRICE_PROTOCOL:
            track.update(price_comparison_protocol=CONTROLLED_PRICE_PROTOCOL,
                proposed_next_seat_calibration=rows[-1].get('next_seat_calibration') if rows else None,
                seat_feedback_application='proposed_only_fixed_during_price_comparison',
                decision_reason='No informative member offer exposure; no price recommendation retained.' if rows and best is None else None)
        from .contribution_explanation import describe_track
        track['contribution_explanation'] = describe_track(cfg, track, worlds)
        tracks.append(track)
    saved['tracks'] = tracks
    saved['version'] = saved['provenance'].get('version',VERSION)
    saved['search_seeds'] = _seeds(cfg)
    saved['validation_seeds'] = _seeds(cfg, True)
    if cfg.get('total_live_budget') is not None:
        saved['progress']['live_budget_remaining'] = max(0,cfg['total_live_budget']-saved['counts']['live_attempts'])
    if cfg.get('scope'):
        stages = 2*sum(d<=cfg['forecast_day'] for d in (28,14,7))+2
        saved['estimated_live_decisions_upper_bound'] = (cfg['replicates']*(cfg['rounds']+1)+4)*cfg['customers']*stages
    saved['assumptions'] = ['Synthetic feedback, not observed HK Express customer behavior.',
        'Best tested feasible price pair, not a certified global optimum. Each round evaluates one candidate per track.',
        'LLM and mathematical tracks have independent best prices; holdout only accepts or rejects each frozen candidate.',
        'Contribution excludes mandatory pass-through fees and aircraft fixed costs.',
        'Base NHPP parameters remain frozen. A run-local seat calibration layer learns only from completed training markets; holdout freezes the selected candidate profile.',
        'Live work automatically crosses internal batches only within the explicitly authorized total decision limit; provider failures and the total cap stop execution.']
    if cfg.get('scope'):
        saved['scope'] = {k:v for k,v in cfg['scope'].items() if k != 'history'}
        saved['economic_scope'] = {
            'kind': 'selected_flight_attributed_contribution',
            'membership_term_evaluated': False,
            'future_member_trip_contribution': None,
            'future_renewal_contribution': None,
            'explanation': 'Only the selected flight is simulated. Later member trips and renewals are not modelled; their contribution is unknown, not zero. OFFER/NO_OFFER is a decision for this flight, not the whole membership programme.'}
        saved['assumptions'] += ['One selected flight/date; V0 remains fixed while P is searched.',
            'Profit is flight-attributed contribution: one third of new annual pass revenue and service cost, full per-flight costs; fees/taxes and aircraft fixed costs excluded.',
            'Normal demand continuation is independently sampled from observed booking pace with random growth/jumps. The forecast does not generate its own evaluation labels.',
            'Highest profit, highest margin and most buyers may be different tested prices; these are separate objectives.']
    if cfg.get('price_comparison_protocol') == CONTROLLED_PRICE_PROTOCOL:
        saved['assumptions'] = [a for a in saved['assumptions'] if not a.startswith('Base NHPP parameters remain frozen.')]
        saved['assumptions'] += ['Base NHPP and the seat-feedback profile are fixed throughout this fare comparison and holdout. Completed outcomes produce a proposed next-run calibration, which is not applied within this experiment.',
            'Member and regular buyers are separate household groups and may overlap. Purchased tickets include subsequent cancellations; fulfilment and cancellation are reported separately.',
            'All-zero member supply or no member-offer exposure cannot support a member-price recommendation. Cancellation and normal-revenue differences remain visible as accounting outcomes only.']
    return saved


def list_runs():
    with store.connection() as db:
        ids = [row[0] for row in db.execute('SELECT run_id FROM optimization_runs ORDER BY created_at DESC LIMIT 50')]
    return [{key: value for key, value in read(run_id).items() if key in ('run_id', 'status', 'config', 'progress', 'counts', 'updated_at', 'error', 'tracks')} for run_id in ids]


def events(run_id, limit=100, offset=0):
    _id(run_id)
    store.run(run_id)
    limit = _number(limit, 'limit', 1, 500, True)
    offset = _number(offset, 'offset', 0, 10000000, True)
    with store.connection() as db:
        records = db.execute('SELECT id,world_id,recorded_at,record FROM optimization_events WHERE run_id=? ORDER BY id LIMIT ? OFFSET ?', (run_id, limit, offset)).fetchall()
        total = db.execute('SELECT COUNT(*) FROM optimization_events WHERE run_id=?', (run_id,)).fetchone()[0]
    return {'run_id': run_id, 'total': total, 'offset': offset, 'limit': limit,
            'events': [{**dict(row), 'record': json.loads(row['record'])} for row in records]}


def export_run(run_id):
    report = read(run_id)
    with store.connection() as db:
        worlds = db.execute('SELECT world_id,mode,phase,round_number,seed,policy,result,status FROM optimization_worlds WHERE run_id=? ORDER BY mode,phase,round_number,seed', (run_id,)).fetchall()
    report['worlds'] = [{**dict(row), 'policy': json.loads(row['policy']), 'result': json.loads(row['result']) if row['result'] else None} for row in worlds]
    return report

"""LLM proposes prices; independent traveller calls and integer ledger score them.

No preset price probes, joining fee or cost/profit objective. Search feedback is
strictly separated from untouched validation worlds. The original optimizer and
frozen NHPP calibration remain separate.
"""
import hashlib
import json
import math
import os
from pathlib import Path
import statistics
import threading
import time
import uuid

from . import feedback_store as store
from llm_agent.file_lock import exclusive_lock

VERSION = 'llm-feedback-base-revenue-v1'
ROOT = Path(__file__).resolve().parents[1]
CUSTOMER_PROMPT = ROOT / 'llm_agent/prompts/fare_only_customer_v1_en.txt'
_lock = threading.RLock()
_active = set()


class Paused(Exception):
    pass


def validate(body):
    from backend.initial_policy import flight_scope
    from backend.optimization import _number
    if not isinstance(body, dict) or not isinstance(body.get('flight_id'), str):
        raise ValueError('Select a flight_id and forecast_day')
    scope = flight_scope(body['flight_id'], body.get('forecast_day', 28))
    options = {'rounds': (3, 1, 8, True), 'customers': (14, 1, 50, True),
               'replicates': (1, 1, 3, True), 'seed': (117, 0, 2**31-100000, True),
               'release_fraction': (.5, .01, 1, False), 'fare_min': (0, 0, 2000, False),
               'fare_max': (max(500, scope['initial_member_fare']), 0, 2000, False),
               'total_call_budget': (300, 0, 2000, True)}
    cfg = {k: _number(body.get(k, default), k, lo, hi, integer)
           for k, (default, lo, hi, integer) in options.items()}
    for key in ('fare_min', 'fare_max'):
        if round(cfg[key], 2) != cfg[key]:
            raise ValueError('Fare bounds must use at most two decimal places')
    initial = scope['initial_member_fare']
    if not cfg['fare_min'] <= initial <= cfg['fare_max'] or cfg['fare_min'] >= cfg['fare_max']:
        raise ValueError('Fare bounds must contain dataset P0 and have nonzero width')
    if not scope['optimization_eligible'] or math.floor(scope['releasable_seats'] * cfg['release_fraction']) < 1:
        raise ValueError('No usable member seats at this round; choose another flight or release share')
    if any(body.get(key, 0) != 0 for key in ('membership_fee', 'initial_membership_fee', 'program_cost')):
        raise ValueError('This experiment has no membership fee or costs')
    cfg.update(flight_id=scope['flight_id'], forecast_day=scope['as_of_day'], scope=scope,
               initial_fare=initial, membership_fee=0, objective='base_ticket_revenue',
               customer_model='live', proposer='live_llm', price_scope='base_only')
    return cfg


def provenance():
    files = ['backend/feedback_pricing.py', 'backend/feedback_store.py', 'backend/fare_only_market.py',
             'backend/shared_market.py', 'backend/scoped_market.py', 'backend/initial_policy.py', 'backend/data.py',
             'backend/nhpp.py', 'backend/release_policy.py', 'backend/seat_feedback.py',
             'simulation/generated/calibration_v2.json', 'simulation/generate.py', 'llm_agent/population.py',
             'llm_agent/price_proposer.py', 'llm_agent/market_adapter.py', 'llm_agent/journey_runner.py',
             'llm_agent/output_contract.py', 'llm_agent/prompts/fare_only_customer_v1_en.txt',
             'llm_agent/prompts/price_optimizer_v1_en.txt']
    # Includes dataset content, not only a manifest's claimed checksum.
    files += [str(p.relative_to(ROOT)) for directory in ('generated', 'network_generated', 'member_demo_generated')
              for p in (ROOT / 'simulation' / directory).glob('*')
              if p.name in ('snapshots.csv.gz', 'flights.csv', 'flights.json', 'manifest.json')]
    return {'version': VERSION, 'files': {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in files},
            'model': os.environ.get('LLM_MODEL'),
            'endpoint_hash': hashlib.sha256(os.environ.get('LLM_API_URL', '').encode()).hexdigest()}


def _reserve(run_id, role):
    def change(doc):
        if doc['counts']['total_attempts'] >= doc['config']['total_call_budget']:
            raise Paused('Authorized LLM call allowance exhausted. Add a finite allowance to continue.')
        doc['counts']['total_attempts'] += 1
        doc['counts']['proposer_calls' if role == 'proposer' else 'customer_calls'] += 1
    store.mutate(run_id, change)


def _world(run_id, phase, number, seed, fare, enabled):
    from backend import fare_only_market as market
    from backend.shared_market import apply_decision
    from llm_agent.market_adapter import choose, legal_choices
    cfg = store.read(run_id)['config']
    wid = f'{run_id}-{phase}-{number}-{seed}'
    saved = store.world(wid)
    if saved and saved['result'] is not None:
        return saved['result']
    if saved:
        state = saved['state']
    else:
        state = market.create_world(cfg['scope'], fare, cfg['customers'], seed, cfg['release_fraction'], enabled)
        store.create_world(wid, run_id, phase, number, seed, fare, enabled, state)
    store.update(run_id, progress={'phase': phase, 'round': number, 'seed': seed, 'world_id': wid})
    audit = store.SqlAudit(run_id, wid)
    prompt = CUSTOMER_PROMPT.read_text(encoding='utf-8')
    while (observation := market.next_observation(state)) is not None:
        # next_observation also advances background events. Save before transport
        # or budget checks so pause/restart cannot lose that market progression.
        store.checkpoint(wid, state)
        if len(legal_choices(observation)) > 1:
            _reserve(run_id, 'customer')
        choice = choose(observation, 'live', audit, system_prompt=prompt,
                        prompt_version='fare-only-customer-v1-en')
        transition = apply_decision(state, choice['decision'])
        store.checkpoint(wid, state, event={'event': 'feedback_transition', 'phase': phase,
            'round': number, 'seed': seed, 'packet_id': observation['packet_id'],
            'observation': observation, 'decision': choice['decision'],
            'transition': transition, 'source': choice['source']})
    result = market.result(state)
    if not result['complete'] or not all(result['checks'].values()):
        raise ValueError('Market accounting failed; this world cannot be ranked')
    store.checkpoint(wid, state, result)
    return result


def aggregate(reports):
    keys = ('ticket_revenue', 'tickets_sold', 'tickets_flown', 'tickets_cancelled',
            'member_tickets', 'regular_tickets', 'background_tickets', 'buyers',
            'member_buyers', 'member_flown', 'member_offer_customers', 'member_supply_exposure',
            'agent_base_revenue', 'background_base_revenue', 'member_base_revenue', 'regular_base_revenue')
    return {**{key: round(statistics.mean(r[key] for r in reports), 4) for key in keys},
            'markets': len(reports), 'checks_passed': all(all(r['checks'].values()) for r in reports)}


def paired_delta(reports, controls):
    if len(reports) != len(controls) or not reports:
        raise ValueError('Paired evaluations require equal nonempty worlds')
    values = []
    for candidate, control in zip(reports, controls):
        if candidate['seed'] != control['seed'] or candidate['exogenous_sha256'] != control['exogenous_sha256']:
            raise ValueError('Counterfactual worlds are not matched')
        values.append(round(candidate['ticket_revenue'] - control['ticket_revenue'], 2))
    return {'mean': round(statistics.mean(values), 4), 'per_seed': values,
            'standard_error': statistics.stdev(values)/math.sqrt(len(values)) if len(values) > 1 else None}


def feedback(run_id, number):
    """Only executed search choices; compact all action counts + balanced reasons.

    Not filtered to support the incumbent. Deterministic first two examples per
    action, with original records available separately for full inspection.
    """
    with store.connection() as db:
        records = db.execute('SELECT e.record FROM events e JOIN worlds w ON w.world_id=e.world_id '
            "WHERE e.run_id=? AND w.phase='search' AND w.round_number=? ORDER BY e.id", (run_id, number)).fetchall()
    groups = {}
    for row in records:
        record = json.loads(row[0])
        if record.get('event') != 'feedback_transition' or record.get('source') == 'environment_forced':
            continue
        action = record['decision']['action']
        group = groups.setdefault(action, {'count': 0, 'examples': []})
        group['count'] += 1
        if len(group['examples']) < 2:
            obs = record['observation']
            group['examples'].append({'customer_id': obs['customer_id'], 'stage': obs['stage'],
                'reason': record['decision']['reason'], 'remaining_budget': obs['visible_state']['remaining_budget'],
                'legal_quotes': [{'action': o['action'], 'price': o['price']} for o in obs.get('options', [])]})
    return groups


def best_candidate(rows):
    # Keep P0 on a tie. Never claim a new optimum merely because it is cheaper.
    return max(rows, key=lambda row: (row['ticket_revenue'], -row['round']))


def validation_decision(selected, initial, selected_delta, initial_delta, change, selected_round):
    """Never recommend an unexposed offer or treat a rejected price as a win."""
    def supported(metrics, delta):
        return delta > 0 and metrics['member_offer_customers'] > 0 and metrics['member_tickets'] > 0
    if supported(selected, selected_delta) and selected_round != 1 and change > 0:
        return 'RECOMMEND_TESTED_FARE'
    if supported(initial, initial_delta):
        return 'KEEP_INITIAL'
    return 'REJECT_OFFER'


def recovered_proposal(run_id, context):
    """Recover a validated response after a crash before the proposal checkpoint."""
    from llm_agent.price_proposer import proposal_context, validate_proposal, VERSION as prompt_version
    visible = proposal_context(context)
    digest = hashlib.sha256(json.dumps(visible, ensure_ascii=False, sort_keys=True,
                                       separators=(',', ':'), allow_nan=False).encode()).hexdigest()
    with store.connection() as db:
        rows = db.execute('SELECT record FROM events WHERE run_id=? AND world_id IS NULL ORDER BY id DESC', (run_id,)).fetchall()
    for row in rows:
        record = json.loads(row[0])
        if record.get('event') == 'price_proposal_validated' and record.get('context_sha256') == digest:
            proposal = validate_proposal(record['proposal'], visible)
            return {**proposal, 'source': 'provider_live', 'provider_call': False, 'cache_hit': False,
                    'recovered_from_audit': True, 'context_sha256': digest, 'prompt_version': prompt_version}
    return None


def _execute(run_id):
    from llm_agent.price_proposer import propose
    doc = store.read(run_id)
    if doc['provenance'] != provenance():
        raise ValueError('Implementation, data or provider changed; start a new experiment')
    cfg = doc['config']
    p0 = cfg['initial_fare']
    seeds = [cfg['seed'] + i*101 for i in range(cfg['replicates'])]
    baselines = [_world(run_id, 'baseline', 0, seed, p0, False) for seed in seeds]
    for number in range(1, cfg['rounds']+1):
        doc = store.read(run_id)
        if len(doc['rounds']) >= number:
            continue
        proposal = doc['proposals'].get(str(number))
        if proposal is None:
            if number == 1:
                proposal = {'fare': p0, 'reason': 'Initial observed normal base fare from the selected flight.',
                            'hypothesis': 'Measure the starting fare before feedback.', 'source': 'dataset'}
            else:
                store.update(run_id, progress={'phase': 'proposing', 'round': number})
                context = {'fare_min': cfg['fare_min'], 'fare_max': cfg['fare_max'], 'initial_fare': p0,
                    'round': number, 'objective': cfg['objective'], 'history': doc['rounds'],
                    'baseline': aggregate(baselines), 'release_fraction': cfg['release_fraction'],
                    'scope': {k: cfg['scope'][k] for k in ('origin', 'destination', 'departure_date', 'as_of_day',
                              'capacity', 'available_seats', 'releasable_seats')},
                    'constraints': ['No membership purchase or renewal; base-ticket payment only.',
                        'Regular background arrivals and all exogenous events are fixed across prices.',
                        'Do not change seat policy, customer personas, budget, fees or costs.',
                        'Maximize total new base-ticket receipts, including lost normal sales; not profit.',
                        'Propose one new bounded cent-valued fare; there is no requirement to test zero.']}
                proposal = recovered_proposal(run_id, context)
                if proposal is None:
                    _reserve(run_id, 'proposer')
                    proposal = propose(context, store.SqlAudit(run_id))
                else:
                    store.SqlAudit(run_id).append({'event': 'price_proposal_recovered', 'round': number, 'proposal': proposal})
            store.mutate(run_id, lambda d: d['proposals'].update({str(number): proposal}))
        reports = [_world(run_id, 'search', number, seed, proposal['fare'], True) for seed in seeds]
        delta = paired_delta(reports, baselines)
        result = {'round': number, 'fare': proposal['fare'], 'proposal': proposal, 'reason': proposal['reason'],
                  **aggregate(reports), 'incremental_revenue': delta['mean'],
                  'delta_vs_no_offer': delta['mean'], 'standard_error': delta['standard_error'],
                  'feedback': feedback(run_id, number)}
        store.mutate(run_id, lambda d: d['rounds'].append(result))
    best = best_candidate(store.read(run_id)['rounds'])
    store.update(run_id, selected={'fare': best['fare'], 'round': best['round']})
    # Only after selection: two untouched seeds, and P0/control on those exact
    # worlds. These outcomes NEVER choose a replacement price or enter a prompt.
    holdout = [cfg['seed'] + 50003, cfg['seed'] + 50104]
    control = [_world(run_id, 'holdout_no_offer', 0, seed, p0, False) for seed in holdout]
    initial = [_world(run_id, 'holdout_initial', 1, seed, p0, True) for seed in holdout]
    selected = initial if best['round'] == 1 else [
        _world(run_id, 'holdout_selected', best['round'], seed, best['fare'], True) for seed in holdout]
    before, without = paired_delta(selected, initial), paired_delta(selected, control)
    evidence, initial_evidence = aggregate(selected), aggregate(initial)
    initial_delta = paired_delta(initial, control)
    decision = validation_decision(evidence, initial_evidence, without['mean'], initial_delta['mean'],
                                   before['mean'], best['round'])
    validation = {'seeds': holdout, 'initial': {'fare': p0, **initial_evidence},
        'selected': {'fare': best['fare'], **evidence}, 'no_offer': aggregate(control),
        'delta_vs_initial': before['mean'], 'delta_vs_no_offer': without['mean'],
        'initial_delta_vs_no_offer': initial_delta['mean'],
        'incremental_revenue': without['mean'], 'standard_error_vs_initial': before['standard_error'],
        'standard_error_vs_no_offer': without['standard_error'], 'paired_deltas_vs_initial': before['per_seed'],
        'paired_deltas_vs_no_offer': without['per_seed'], 'decision': decision,
        'interpretation': 'Two synthetic holdout worlds; a directional comparison, not statistical proof or a global optimum.'}
    store.update(run_id, validation=validation, status='completed', error=None,
                 progress={'phase': 'completed', 'round': cfg['rounds']})


def _worker(run_id, additional=0):
    try:
        with exclusive_lock(store.BASE / f'{run_id}.lock'):
            def begin(doc):
                if doc['config']['total_call_budget'] + additional > 10000:
                    raise ValueError('Lifetime attempt limit is 10000')
                doc['config']['total_call_budget'] += additional
                doc.update(status='running', error=None)
            store.mutate(run_id, begin)
            try:
                _execute(run_id)
            except Paused as error:
                store.update(run_id, status='paused', error=str(error))
            except Exception as error:
                from llm_agent.audit import sanitize
                store.update(run_id, status='failed', error=sanitize(str(error)))
    except ValueError:
        # Another process owns the lock. Do not change its status, budget or
        # results. The process-local active flag is cleared below.
        pass
    finally:
        with _lock:
            _active.discard(run_id)


def _launch(run_id, additional=0):
    with _lock:
        if run_id in _active:
            raise ValueError('This feedback experiment is already running')
        _active.add(run_id)
    threading.Thread(target=_worker, args=(run_id, additional), daemon=True).start()


def start(body):
    config = validate(body)
    if not all(os.environ.get(k) for k in ('LLM_API_URL', 'LLM_API_KEY', 'LLM_MODEL')):
        raise ValueError('A live LLM provider is required for both travellers and price proposals')
    run_id = 'feedback-' + uuid.uuid4().hex[:16]
    doc = {'run_id': run_id, 'status': 'queued', 'config': config, 'scope': config['scope'],
           'initial_fare': config['initial_fare'], 'provenance': provenance(), 'rounds': [], 'proposals': {},
           'selected': None, 'validation': None, 'progress': {'phase': 'queued', 'round': 0},
           'counts': dict.fromkeys(('total_attempts', 'proposer_calls', 'customer_calls', 'provider_calls',
                                    'cache_hits', 'forced', 'failures'), 0),
           'created_at': time.time(), 'updated_at': time.time(), 'error': None}
    store.create(doc)
    _launch(run_id)
    return read(run_id)


def read(run_id):
    doc = store.read(run_id)
    if run_id in _active and doc['status'] in ('paused', 'failed', 'interrupted'):
        doc['status'] = 'queued'
    if doc['status'] in ('queued', 'running') and run_id not in _active:
        # A different server process may still own this experiment's lock.
        try:
            with exclusive_lock(store.BASE / f'{run_id}.lock'):
                doc['status'] = 'interrupted'
        except ValueError:
            pass
    return doc


def resume(run_id, body):
    from backend.optimization import _number
    if not isinstance(body, dict):
        raise ValueError('JSON object required')
    with _lock:
        doc = read(run_id)
        if run_id in _active or doc['status'] in ('completed', 'running', 'queued'):
            raise ValueError('Only an unfinished inactive run can resume')
        if doc['provenance'] != provenance():
            raise ValueError('Implementation, data or provider changed; start a new experiment')
        additional = _number(body.get('additional_call_budget', 0), 'additional_call_budget', 0, 2000, True)
        if doc['config']['total_call_budget'] + additional > 10000:
            raise ValueError('Lifetime attempt limit is 10000')
        # The worker adds allowance only after acquiring the process lock.
        _launch(run_id, additional)
    return read(run_id)


def list_runs():
    return [{k: d[k] for k in ('run_id', 'status', 'config', 'created_at', 'updated_at')}
            for d in (read(item['run_id']) for item in store.list_runs())]


def export_run(run_id):
    from llm_agent.audit import sanitize
    with store.connection() as db:
        rows = db.execute('SELECT id,record FROM events WHERE run_id=? ORDER BY id', (run_id,)).fetchall()
    return sanitize({'report': read(run_id), 'worlds': store.all_worlds(run_id),
                     'events': [{'id': row[0], 'record': json.loads(row[1])} for row in rows]})

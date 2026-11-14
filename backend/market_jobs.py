"""Local background batches for shared-market experiments; never auto-extend spend."""
from __future__ import annotations
from .errors import NotFound
import json
import math
from pathlib import Path
import re
import threading
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'data/private/shared_market'
_lock = threading.Lock()
_active = set()


def _folder(run_id):
    if not isinstance(run_id, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}', run_id):
        raise ValueError('Invalid market run ID')
    return BASE / run_id


def _number(value, name, low, high, integer=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high or (integer and int(value) != value):
        raise ValueError(f'{name} must be {low}..{high}')
    return int(value) if integer else float(value)


def _save(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2))
    temporary.replace(path)


def _worker(run_id, options, resume):
    folder = _folder(run_id)
    metadata = {'run_id': run_id, 'status': 'running', 'updated_at': time.time()}
    _save(folder / 'job.json', metadata)
    try:
        from llm_agent import market_experiment as experiment
        from llm_agent.audit import BASE as audits
        if not resume:
            policies = [dict(p) for p in experiment.DEFAULT_POLICIES]
            policies[-1].update({key: options[key] for key in ('member_fare', 'membership_fee', 'open_day', 'release_fraction')})
            experiment.create_experiment(folder, seeds=[options['seed']], policies=policies, modes=[options['mode']])
        result = experiment.run_batch(folder, max_calls=options['max_calls'], max_steps=10000)
        audit_file = audits / result['run_id'] / 'metadata.json'
        status = json.loads(audit_file.read_text())['status'] if audit_file.exists() else 'paused_at_budget'
        metadata.update(status=status, batch=result, audit_run_id=result['run_id'])
    except Exception as error:
        metadata.update(status='failed', error=str(error))
    finally:
        metadata['updated_at'] = time.time()
        _save(folder / 'job.json', metadata)
        with _lock:
            _active.discard(run_id)


def start(body, run_id=None):
    resume = run_id is not None
    options = {'max_calls': _number(body.get('max_calls', 60), 'max_calls', 0, 100, True)}
    if not resume:
        mode = body.get('mode', 'deterministic')
        if mode not in ('deterministic', 'probabilistic', 'live'):
            raise ValueError('Unknown decision mode')
        from llm_agent.runner import status
        if mode == 'live' and not status()['live_configured']:
            raise ValueError('Live provider is not configured')
        options.update(mode=mode, seed=_number(body.get('seed', 117), 'seed', 0, 2**31-1, True),
                       member_fare=_number(body.get('member_fare', 30), 'member_fare', 0, 2000),
                       membership_fee=_number(body.get('membership_fee', 199), 'membership_fee', 0, 5000),
                       open_day=_number(body.get('open_day', 28), 'open_day', 1, 28, True),
                       release_fraction=_number(body.get('release_fraction', .75), 'release_fraction', 0, 1))
        if options['open_day'] != 28:
            raise ValueError('Release schedule is fixed at D28, D14 and D7; open_day must be 28')
        run_id = 'web-' + uuid.uuid4().hex[:16]
    folder = _folder(run_id)
    if resume and not (folder / 'experiment.json').is_file():
        raise NotFound('Market experiment not found')
    with _lock:
        if _active:
            raise ValueError('A market batch is already running; wait for its checkpoint')
        _active.add(run_id)
    try:
        folder.mkdir(parents=True, exist_ok=True)
        _save(folder / 'job.json', {'run_id': run_id, 'status': 'queued', 'updated_at': time.time()})
        threading.Thread(target=_worker, args=(run_id, options, resume), daemon=True).start()
    except Exception:
        # Never leave a phantom "running" batch that blocks every later start.
        with _lock:
            _active.discard(run_id)
        raise
    return {'run_id': run_id, 'status': 'queued'}


def read(run_id):
    folder = _folder(run_id)
    if not folder.is_dir():
        raise NotFound('Market experiment not found')
    status = json.loads((folder / 'job.json').read_text()) if (folder / 'job.json').exists() else {'run_id': run_id, 'status': 'recorded'}
    if status['status'] in ('running', 'queued') and run_id not in _active:
        status['status'] = 'interrupted'
    if (folder / 'report.json').exists():
        status['report'] = json.loads((folder / 'report.json').read_text())
    elif (folder / 'experiment.json').exists():
        spec = json.loads((folder / 'experiment.json').read_text())
        status['report'] = {'run_id': spec['experiment_id'], 'cases': len(spec['cases']),
                            'completed_cases': sum(c['completed'] for c in spec['cases']),
                            'case_results': [], 'aggregate': [], 'paired_differences': []}
    if not (folder / 'job.json').exists() and (folder / 'experiment.json').exists():
        from llm_agent.market_experiment import run_status
        status['status'] = run_status(folder).get('status', 'recorded')
    return status


def list_runs():
    if not BASE.exists():
        return []
    result = []
    for folder in sorted(BASE.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)[:50]:
        if folder.is_dir() and ((folder / 'job.json').exists() or (folder / 'experiment.json').exists()):
            obj = read(folder.name)
            report = obj.pop('report', {})
            result.append({**obj, 'cases': report.get('cases', 0), 'completed_cases': report.get('completed_cases', 0)})
    return result


def read_case(run_id, case_id):
    from llm_agent.market_experiment import inspect_cases
    folder = _folder(run_id)
    spec = json.loads((folder / 'experiment.json').read_text())
    if case_id not in {c['case_id'] for c in spec['cases']}:
        raise NotFound('Unknown market case')
    state = json.loads((folder / f'{case_id}.json').read_text())
    # This is an evaluator view. The customer adapter sees only its observation.
    return {'case_id': case_id, 'source': 'synthetic_evaluator_view', 'state': state,
            'inspection': inspect_cases(folder, case_id, event_limit=1000)[0]}

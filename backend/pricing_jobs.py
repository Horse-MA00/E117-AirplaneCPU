"""Bounded, durable local continuous-pricing jobs; never calls an LLM provider."""
import json
from pathlib import Path
import re
import threading
import time
import uuid

BASE = Path(__file__).resolve().parents[1] / 'data/private/continuous_pricing'
_lock = threading.Lock()
_active = set()


def _path(run_id):
    if not re.fullmatch(r'price-[a-f0-9]{16}', run_id):
        raise ValueError('Invalid pricing run id')
    return BASE / run_id


def _save(path, value):
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    tmp.replace(path)


def _worker(run_id, config):
    folder = _path(run_id)
    try:
        from .continuous_pricing import optimize
        _save(folder/'job.json', {'run_id':run_id, 'status':'running'})
        result = optimize(config)
        _save(folder/'report.json', result)
        _save(folder/'job.json', {'run_id':run_id, 'status':'completed'})
    except Exception as error:
        _save(folder/'job.json', {'run_id':run_id, 'status':'failed', 'error':str(error)})
    finally:
        with _lock:
            _active.discard(run_id)


def start(body):
    if not isinstance(body, dict):
        raise ValueError('JSON object required')
    run_id = 'price-' + uuid.uuid4().hex[:16]
    with _lock:
        if _active:
            raise ValueError('A continuous search is already running')
        folder = _path(run_id)
        folder.mkdir(parents=True)
        _save(folder/'config.json', body)
        _save(folder/'job.json', {'run_id':run_id, 'status':'queued'})
        _active.add(run_id)
    try:
        threading.Thread(target=_worker,args=(run_id,dict(body)),daemon=True).start()
    except Exception:
        with _lock:
            _active.discard(run_id)
        raise
    return {'run_id':run_id, 'status':'queued'}


def read(run_id):
    folder = _path(run_id)
    if not (folder/'job.json').is_file():
        raise ValueError('Pricing run not found')
    job = json.loads((folder/'job.json').read_text(encoding='utf-8'))
    if job['status'] in ('queued','running') and run_id not in _active:
        job['status'] = 'interrupted'
    if (folder/'report.json').exists():
        job['report'] = json.loads((folder/'report.json').read_text(encoding='utf-8'))
    return job

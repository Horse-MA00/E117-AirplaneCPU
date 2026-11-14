"""Durable SQLite ledger for bounded synthetic optimization experiments."""
from __future__ import annotations
from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
import time

BASE = Path(__file__).resolve().parents[1] / 'data/private/optimization'


def encode(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


@contextmanager
def connection():
    BASE.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(BASE / 'experiments.sqlite3', timeout=30)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA journal_mode=WAL')
    db.execute('PRAGMA foreign_keys=ON')
    db.executescript('''
        CREATE TABLE IF NOT EXISTS optimization_runs (
            run_id TEXT PRIMARY KEY, status TEXT NOT NULL, config TEXT NOT NULL,
            provenance TEXT NOT NULL, progress TEXT NOT NULL, counts TEXT NOT NULL,
            created_at REAL NOT NULL, updated_at REAL NOT NULL, error TEXT);
        CREATE TABLE IF NOT EXISTS optimization_worlds (
            world_id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES optimization_runs(run_id),
            mode TEXT NOT NULL, phase TEXT NOT NULL, round_number INTEGER NOT NULL,
            seed INTEGER NOT NULL, policy TEXT NOT NULL, state TEXT NOT NULL,
            result TEXT, status TEXT NOT NULL, updated_at REAL NOT NULL);
        CREATE INDEX IF NOT EXISTS optimization_world_run ON optimization_worlds(run_id, mode, phase, round_number);
        CREATE TABLE IF NOT EXISTS optimization_rounds (
            run_id TEXT NOT NULL REFERENCES optimization_runs(run_id), mode TEXT NOT NULL,
            round_number INTEGER NOT NULL, result TEXT NOT NULL,
            PRIMARY KEY(run_id, mode, round_number));
        CREATE TABLE IF NOT EXISTS optimization_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL REFERENCES optimization_runs(run_id),
            world_id TEXT, recorded_at REAL NOT NULL, record TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS optimization_event_run ON optimization_events(run_id, id);
    ''')
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def run(run_id):
    with connection() as db:
        row = db.execute('SELECT * FROM optimization_runs WHERE run_id=?', (run_id,)).fetchone()
    if row is None:
        raise ValueError('Optimization run not found')
    obj = dict(row)
    for key in ('config', 'provenance', 'progress', 'counts'):
        obj[key] = json.loads(obj[key])
    return obj


def update(run_id, **changes):
    allowed = {'status', 'config', 'provenance', 'progress', 'counts', 'error'}
    if set(changes) - allowed:
        raise ValueError('Invalid run field')
    values = {key: encode(value) if key in ('config', 'provenance', 'progress', 'counts') else value for key, value in changes.items()}
    values['updated_at'] = time.time()
    with connection() as db:
        db.execute('UPDATE optimization_runs SET ' + ','.join(key + '=?' for key in values) + ' WHERE run_id=?', (*values.values(), run_id))


def record(run_id, world_id, value):
    from llm_agent.audit import sanitize
    with connection() as db:
        db.execute('INSERT INTO optimization_events(run_id,world_id,recorded_at,record) VALUES (?,?,?,?)',
                   (run_id, world_id, time.time(), encode(sanitize(value))))


def rounds(run_id, mode):
    with connection() as db:
        rows = db.execute('SELECT result FROM optimization_rounds WHERE run_id=? AND mode=? ORDER BY round_number', (run_id, mode)).fetchall()
    return [json.loads(row['result']) for row in rows]


def world(world_id):
    with connection() as db:
        row = db.execute('SELECT * FROM optimization_worlds WHERE world_id=?', (world_id,)).fetchone()
    if row is None:
        return None
    obj = dict(row)
    for key in ('state', 'result', 'policy'):
        obj[key] = json.loads(obj[key]) if obj[key] else None
    return obj


def checkpoint(world_id, state, result=None):
    with connection() as db:
        db.execute('UPDATE optimization_worlds SET state=?,result=?,status=?,updated_at=? WHERE world_id=?',
                   (encode(state), encode(result) if result is not None else None,
                    'completed' if result is not None else 'running', time.time(), world_id))


class SqlAudit:
    """Adapter audit API; original requests and responses are redacted then stored."""
    def __init__(self, run_id, world_id):
        self.run_id, self.world_id = run_id, world_id
        self.path = BASE / run_id
        self.path.mkdir(exist_ok=True)

    def append(self, value):
        from llm_agent.audit import sanitize
        with connection() as db:
            db.execute('INSERT INTO optimization_events(run_id,world_id,recorded_at,record) VALUES (?,?,?,?)',
                       (self.run_id, self.world_id, time.time(), encode(sanitize(value))))
            if value.get('event') in ('market_choice', 'market_choice_failed'):
                counts = json.loads(db.execute('SELECT counts FROM optimization_runs WHERE run_id=?', (self.run_id,)).fetchone()[0])
                counts['provider_calls'] += int(value.get('provider_call', False))
                counts['cache_hits'] += int(value.get('cache_hit', False))
                counts['forced'] += int(value.get('source') == 'environment_forced')
                counts['math_choices'] += int(value.get('source') == 'probabilistic_assumption')
                counts['failures'] += int(value.get('event') == 'market_choice_failed')
                db.execute('UPDATE optimization_runs SET counts=?,updated_at=? WHERE run_id=?', (encode(counts), time.time(), self.run_id))


def apply_transition(run_id, world_id, state, record_value):
    """Commit an accepted action and resulting market state as one transaction."""
    from llm_agent.audit import sanitize
    with connection() as db:
        db.execute('INSERT INTO optimization_events(run_id,world_id,recorded_at,record) VALUES (?,?,?,?)',
                   (run_id, world_id, time.time(), encode(sanitize(record_value))))
        db.execute('UPDATE optimization_worlds SET state=?,updated_at=? WHERE world_id=?',
                   (encode(state), time.time(), world_id))

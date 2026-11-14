"""Isolated durable experiment store; never mixes with the membership optimizer."""
from contextlib import contextmanager
import json
from pathlib import Path
import re
import sqlite3
import time

from backend.errors import NotFound
from llm_agent.audit import sanitize

BASE = Path(__file__).resolve().parents[1] / 'data/private/feedback_pricing'


def encode(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def checked_id(run_id):
    if not isinstance(run_id, str) or not re.fullmatch(r'feedback-[a-f0-9]{16}', run_id):
        raise ValueError('Invalid feedback experiment ID')
    return run_id


@contextmanager
def connection():
    BASE.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(BASE / 'experiments.sqlite3', timeout=30)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA journal_mode=WAL')
    db.execute('PRAGMA foreign_keys=ON')
    db.executescript('''
        CREATE TABLE IF NOT EXISTS runs (run_id TEXT PRIMARY KEY, document TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS worlds (
            world_id TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(run_id),
            phase TEXT NOT NULL, round_number INTEGER NOT NULL, seed INTEGER NOT NULL,
            fare REAL NOT NULL, enabled INTEGER NOT NULL, state TEXT NOT NULL, result TEXT);
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL REFERENCES runs(run_id),
            world_id TEXT, recorded_at REAL NOT NULL, record TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS event_run ON events(run_id,id);
    ''')
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def read(run_id):
    checked_id(run_id)
    with connection() as db:
        row = db.execute('SELECT document FROM runs WHERE run_id=?', (run_id,)).fetchone()
    if not row:
        raise NotFound('Feedback experiment not found')
    return json.loads(row[0])


def create(document):
    with connection() as db:
        db.execute('INSERT INTO runs VALUES (?,?)', (document['run_id'], encode(document)))


def mutate(run_id, change):
    with connection() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT document FROM runs WHERE run_id=?', (run_id,)).fetchone()
        if not row:
            raise NotFound('Feedback experiment not found')
        document = json.loads(row[0])
        change(document)
        document['updated_at'] = time.time()
        db.execute('UPDATE runs SET document=? WHERE run_id=?', (encode(document), run_id))
    return document


def update(run_id, **fields):
    return mutate(run_id, lambda doc: doc.update(fields))


def world(world_id):
    with connection() as db:
        row = db.execute('SELECT * FROM worlds WHERE world_id=?', (world_id,)).fetchone()
    if not row:
        return None
    result = dict(row)
    for key in ('state', 'result'):
        result[key] = json.loads(result[key]) if result[key] else None
    return result


def create_world(world_id, run_id, phase, number, seed, fare, enabled, state):
    with connection() as db:
        db.execute('INSERT INTO worlds VALUES (?,?,?,?,?,?,?,?,NULL)',
                   (world_id, run_id, phase, number, seed, fare, int(enabled), encode(state)))


def checkpoint(world_id, state, result=None, event=None):
    """Accepted action and resulting inventory/ledger commit atomically."""
    with connection() as db:
        db.execute('UPDATE worlds SET state=?,result=? WHERE world_id=?',
                   (encode(state), encode(result) if result is not None else None, world_id))
        if event:
            run_id = db.execute('SELECT run_id FROM worlds WHERE world_id=?', (world_id,)).fetchone()[0]
            db.execute('INSERT INTO events(run_id,world_id,recorded_at,record) VALUES (?,?,?,?)',
                       (run_id, world_id, time.time(), encode(sanitize(event))))


class SqlAudit:
    def __init__(self, run_id, world_id=None):
        self.run_id, self.world_id = run_id, world_id
        self.path = BASE / run_id
        self.path.mkdir(parents=True, exist_ok=True)

    def append(self, value):
        with connection() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('INSERT INTO events(run_id,world_id,recorded_at,record) VALUES (?,?,?,?)',
                       (self.run_id, self.world_id, time.time(), encode(sanitize(value))))
            event = value.get('event')
            if event in ('market_choice', 'market_choice_failed', 'price_proposal_dispatched', 'price_proposal_failed'):
                doc = json.loads(db.execute('SELECT document FROM runs WHERE run_id=?', (self.run_id,)).fetchone()[0])
                counts = doc['counts']
                counts['provider_calls'] += int(event == 'price_proposal_dispatched' or
                                                (event in ('market_choice', 'market_choice_failed') and value.get('provider_call', False)))
                counts['cache_hits'] += int(event in ('market_choice', 'market_choice_failed') and value.get('cache_hit', False))
                counts['forced'] += int(event == 'market_choice' and value.get('source') == 'environment_forced')
                counts['failures'] += int(event.endswith('_failed'))
                doc['updated_at'] = time.time()
                db.execute('UPDATE runs SET document=? WHERE run_id=?', (encode(doc), self.run_id))


def events(run_id, limit=100, offset=0):
    read(run_id)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 500 or isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
        raise ValueError('Invalid event page')
    with connection() as db:
        rows = db.execute('SELECT * FROM events WHERE run_id=? ORDER BY id LIMIT ? OFFSET ?', (run_id, limit, offset)).fetchall()
        total = db.execute('SELECT COUNT(*) FROM events WHERE run_id=?', (run_id,)).fetchone()[0]
    return {'events': [{**dict(row), 'record': json.loads(row['record'])} for row in rows], 'total': total}


def all_worlds(run_id):
    with connection() as db:
        ids = db.execute('SELECT world_id FROM worlds WHERE run_id=? ORDER BY world_id', (run_id,)).fetchall()
    return [world(row[0]) for row in ids]


def list_runs():
    with connection() as db:
        return sorted((json.loads(row[0]) for row in db.execute('SELECT document FROM runs')), key=lambda doc: doc['created_at'], reverse=True)[:50]

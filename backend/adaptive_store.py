"""Private, durable audit trail for the member-only Thompson experiment."""
from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
import time

BASE = Path(__file__).resolve().parents[1] / 'data/private/adaptive_pricing'
MAX_EXPORT_BYTES = 32 * 1024 * 1024


def encode(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':'))


@contextmanager
def connection():
    BASE.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(BASE / 'experiments.sqlite3', timeout=30)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA journal_mode=WAL')
    db.executescript('''
      CREATE TABLE IF NOT EXISTS adaptive_runs (
        run_id TEXT PRIMARY KEY, payload TEXT NOT NULL, created_at REAL NOT NULL,
        updated_at REAL NOT NULL);
      CREATE TABLE IF NOT EXISTS adaptive_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL,
        recorded_at REAL NOT NULL, record TEXT NOT NULL);
      CREATE INDEX IF NOT EXISTS adaptive_event_run ON adaptive_events(run_id,id);
    ''')
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def save(run):
    from llm_agent.audit import sanitize
    run['updated_at'] = time.time()
    # Provider explanations are untrusted text. A well-formed decision may
    # still echo a credential; audit redaction alone does not protect reports.
    safe = sanitize(run)
    with connection() as db:
        db.execute('INSERT INTO adaptive_runs VALUES (?,?,?,?) ON CONFLICT(run_id) '
                   'DO UPDATE SET payload=excluded.payload,updated_at=excluded.updated_at',
                   (safe['run_id'], encode(safe), safe['created_at'], safe['updated_at']))


def read(run_id):
    from llm_agent.audit import sanitize
    with connection() as db:
        row = db.execute('SELECT payload FROM adaptive_runs WHERE run_id=?', (run_id,)).fetchone()
    if row is None:
        raise ValueError('Adaptive pricing run not found')
    return sanitize(json.loads(row['payload']))


def list_runs(limit=30):
    from llm_agent.audit import sanitize
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
        raise ValueError('Invalid run-list limit')
    with connection() as db:
        rows = db.execute('SELECT payload FROM adaptive_runs ORDER BY created_at DESC LIMIT ?', (limit,)).fetchall()
    return sanitize([{k: r.get(k) for k in ('run_id','status','created_at','updated_at','config','scope','counts','recommendation','validation')}
            for r in (json.loads(row['payload']) for row in rows)])


def record(run_id, value):
    from llm_agent.audit import sanitize
    with connection() as db:
        db.execute('INSERT INTO adaptive_events(run_id,recorded_at,record) VALUES (?,?,?)',
                   (run_id, time.time(), encode(sanitize(value))))


def events(run_id, limit=100, offset=0):
    from llm_agent.audit import sanitize
    if (isinstance(limit, bool) or isinstance(offset, bool) or not isinstance(limit, int)
            or not isinstance(offset, int) or not 1 <= limit <= 1000 or offset < 0):
        raise ValueError('Invalid event page')
    read(run_id)
    with connection() as db:
        rows = db.execute('SELECT * FROM adaptive_events WHERE run_id=? ORDER BY id LIMIT ? OFFSET ?',
                          (run_id, limit, offset)).fetchall()
    return sanitize({'events': [{**dict(row), 'record':json.loads(row['record'])} for row in rows]})


def export_run(run_id):
    from llm_agent.audit import sanitize
    report = read(run_id)
    with connection() as db:
        # Bound an inline API export before fetching all raw provider text.
        # Large private audits can still be inspected through paginated events.
        raw_bytes = db.execute('SELECT COALESCE(SUM(length(CAST(record AS BLOB))),0) '
                               'FROM adaptive_events WHERE run_id=?', (run_id,)).fetchone()[0]
        if raw_bytes + len(encode(report).encode('utf-8')) > MAX_EXPORT_BYTES:
            raise ValueError('Adaptive audit exceeds the inline export limit; use paginated events or inspect the private SQLite audit')
        rows = db.execute('SELECT * FROM adaptive_events WHERE run_id=? ORDER BY id', (run_id,)).fetchall()
    return sanitize({'report':report, 'events':[{**dict(row), 'record':json.loads(row['record'])} for row in rows]})

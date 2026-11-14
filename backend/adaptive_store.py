"""Private, durable audit trail for the member-only Thompson experiment."""
from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
import time

BASE = Path(__file__).resolve().parents[1] / 'data/private/adaptive_pricing'
MAX_EXPORT_BYTES = 32 * 1024 * 1024
_published = None


def enable_published_experiments(root=None):
    """Enable immutable deployment exports without hydrating the private DB.

    Server startup opts in explicitly; direct store users and isolated tests
    retain their own database namespace. Validation failure aborts startup.
    """
    from .published_experiments import PublishedExperiments
    global _published
    _published = PublishedExperiments(root)
    return len(_published.summaries())


def _has_local(run_id):
    with connection() as db:
        return db.execute('SELECT 1 FROM adaptive_runs WHERE run_id=?', (run_id,)).fetchone() is not None


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
        if _published is not None:
            return sanitize(_published.read(run_id))
        raise ValueError('Adaptive pricing run not found')
    return sanitize(json.loads(row['payload']))


def list_runs(limit=30):
    from llm_agent.audit import sanitize
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
        raise ValueError('Invalid run-list limit')
    with connection() as db:
        rows = db.execute('SELECT payload FROM adaptive_runs ORDER BY created_at DESC LIMIT ?', (limit,)).fetchall()
        local_ids = {row[0] for row in db.execute('SELECT run_id FROM adaptive_runs')} if _published is not None else set()
    runs = [{k: r.get(k) for k in ('run_id','version','status','created_at','updated_at','config','scope','counts','recommendation','validation')}
            for r in (json.loads(row['payload']) for row in rows)]
    if _published is not None:
        runs.extend(run for run in _published.summaries() if run['run_id'] not in local_ids)
        runs.sort(key=lambda run: (run['created_at'], run['run_id']), reverse=True)
    return sanitize(runs[:limit])


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
    if _published is not None and not _has_local(run_id):
        return sanitize(_published.events(run_id, limit, offset, MAX_EXPORT_BYTES))
    with connection() as db:
        rows = db.execute('SELECT * FROM adaptive_events WHERE run_id=? ORDER BY id LIMIT ? OFFSET ?',
                          (run_id, limit, offset)).fetchall()
    return sanitize({'events': [{**dict(row), 'record':json.loads(row['record'])} for row in rows]})


def analysis_attempts(run_id, round_number=None):
    """Project analyst audits without copying requests or raw text into reports.

    Old attempts have no round/attempt fields: their request context and hash
    recover the same grouping, including a round that failed before being saved.
    Raw output is fetched only for an explicitly selected round, after a byte
    limit check. Listing attempts never loads the potentially large raw bodies.
    """
    from llm_agent.audit import sanitize
    if round_number is not None and (isinstance(round_number, bool)
            or not isinstance(round_number, int) or not 1 <= round_number <= 30):
        raise ValueError('Analysis round must be an integer from 1 to 30')
    read(run_id)
    if _published is not None and not _has_local(run_id):
        return _analysis_result(run_id, round_number, _published.analyst_rows(run_id),
                                lambda ids: _published.raw_responses(run_id, ids))
    query = '''SELECT id, json_extract(record,'$.event') AS event,
        CASE WHEN json_type(record,'$.round') = 'integer'
             THEN json_extract(record,'$.round')
             WHEN json_valid(json_extract(record,'$.request.messages[1].content'))
             THEN json_extract(json_extract(record,'$.request.messages[1].content'),'$.round') END AS round_number,
        json_extract(record,'$.attempt') AS attempt,
        json_extract(record,'$.context_sha256') AS context_hash,
        json_extract(record,'$.error') AS error,
        json_extract(record,'$.error_type') AS error_type,
        json_extract(record,'$.failure_kind') AS failure_kind,
        json_extract(record,'$.provider_call') AS provider_call,
        json_type(record,'$.raw_response_text') = 'text' AS raw_available,
        length(CAST(json_quote(json_extract(record,'$.raw_response_text')) AS BLOB)) AS raw_bytes
        FROM adaptive_events WHERE run_id=? AND json_extract(record,'$.event') GLOB 'analyst_*'
        ORDER BY id'''
    with connection() as db:
        def raw_loader(ids):
            return {event_id: db.execute(
                "SELECT json_extract(record,'$.raw_response_text') FROM adaptive_events WHERE id=? AND run_id=?",
                (event_id, run_id)).fetchone()[0] for event_id in ids}
        return _analysis_result(run_id, round_number, db.execute(query, (run_id,)), raw_loader)


def _analysis_result(run_id, round_number, rows, raw_loader):
    """Share identical analyst grouping/byte limits for SQLite and published audits."""
    from llm_agent.audit import sanitize
    attempts, by_hash, latest, sequence = {}, {}, {}, {}
    for row in rows:
        event = row['event']
        if event not in ('analyst_request', 'analyst_response', 'analyst_failed', 'analyst_validated', 'analyst_cache'):
            continue
        number, attempt, context_hash = row['round_number'], row['attempt'], row['context_hash']
        key = by_hash.get(context_hash) if isinstance(context_hash, str) else None
        if not isinstance(number, int) or not 1 <= number <= 30:
            if key is None:
                continue
            number = key[0]
        if isinstance(attempt, int) and not isinstance(attempt, bool) and attempt > 0:
            key = (number, attempt)
        elif event == 'analyst_request':
            key = (number, sequence.get(number, 0) + 1)
        elif key is None:
            key = latest.get(number, (number, 1))
        sequence[number] = max(sequence.get(number, 0), key[1])
        latest[number] = key
        if isinstance(context_hash, str):
            by_hash[context_hash] = key
        if key not in attempts:
            attempts[key] = {'round': number, 'attempt': key[1], 'status': 'pending',
                             'error': None, 'error_type': None, 'failure_kind': None,
                             'provider_call': event != 'analyst_cache', 'raw_available': False,
                             '_raw_id': None, '_raw_bytes': 0}
        item = attempts[key]
        if row['provider_call'] is not None:
            item['provider_call'] = bool(row['provider_call'])
        if row['raw_available']:
            item.update(raw_available=True, _raw_id=row['id'], _raw_bytes=row['raw_bytes'] or 0)
        if event == 'analyst_failed':
            error = row['error'] if isinstance(row['error'], str) else 'Analyst attempt failed'
            error_type = row['error_type'] if isinstance(row['error_type'], str) else None
            kind = row['failure_kind']
            if not isinstance(kind, str):
                kind = ('budget' if 'budget' in error.lower() else 'transport'
                        if error_type in ('HTTPError', 'URLError', 'TimeoutError', 'ConnectionError', 'OSError')
                        else 'validation')
            item.update(status='failed', error=error, error_type=error_type, failure_kind=kind)
        elif event in ('analyst_validated', 'analyst_cache'):
            item['status'] = 'passed'
    chosen = [attempts[key] for key in sorted(attempts) if round_number is None or key[0] == round_number]
    result = {'run_id': run_id, 'round': round_number, 'attempts': [
        {k: v for k, v in item.items() if not k.startswith('_')} for item in chosen]}
    byte_count = len(encode(result).encode('utf-8'))
    if round_number is not None:
        # Include JSON escaping and the added property name, not only the
        # unescaped provider-text size (quotes/newlines can double it).
        byte_count += sum(item['_raw_bytes'] + 32 for item in chosen)
    if byte_count > MAX_EXPORT_BYTES:
        raise ValueError('Analysis attempts exceed the inline export limit; use paginated audit events')
    if round_number is not None:
        raw = raw_loader({item['_raw_id'] for item in chosen if item['_raw_id'] is not None})
        for item, target in zip(chosen, result['attempts']):
            target['raw_response_text'] = raw.get(item['_raw_id'])
    result = sanitize(result)
    if len(encode(result).encode('utf-8')) > MAX_EXPORT_BYTES:
        raise ValueError('Analysis attempts exceed the inline export limit; use paginated audit events')
    return result


def export_run(run_id):
    from llm_agent.audit import sanitize
    report = read(run_id)
    if _published is not None and not _has_local(run_id):
        return sanitize(_published.export(run_id, MAX_EXPORT_BYTES))
    with connection() as db:
        # Bound an inline API export before fetching all raw provider text.
        # Large private audits can still be inspected through paginated events.
        raw_bytes = db.execute('SELECT COALESCE(SUM(length(CAST(record AS BLOB))),0) '
                               'FROM adaptive_events WHERE run_id=?', (run_id,)).fetchone()[0]
        if raw_bytes + len(encode(report).encode('utf-8')) > MAX_EXPORT_BYTES:
            raise ValueError('Adaptive audit exceeds the inline export limit; use paginated events or inspect the private SQLite audit')
        rows = db.execute('SELECT * FROM adaptive_events WHERE run_id=? ORDER BY id', (run_id,)).fetchall()
    return sanitize({'report':report, 'events':[{**dict(row), 'record':json.loads(row['record'])} for row in rows]})

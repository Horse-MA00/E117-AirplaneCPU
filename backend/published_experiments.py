"""Read-only, integrity-checked saved experiments shipped with a deployment.

Reports stay in their published files; large audit streams are never imported
into the private SQLite database. Hashes are verified at catalog construction,
and audit structure/counts are checked lazily before returning its first page.
"""
import copy
from dataclasses import dataclass, field
import gzip
import hashlib
import json
import math
from pathlib import Path
import re
import threading


ROOT = Path(__file__).resolve().parents[1] / 'llm_agent/experiments'
VERSION = 'member-thompson-v5-marketing'
PROFILE = 'flexible_deal_seekers'
SUMMARY_KEYS = ('run_id', 'version', 'status', 'created_at', 'updated_at',
                'config', 'scope', 'counts', 'recommendation', 'validation')
MAX_MANIFEST_BYTES = 1024 * 1024
MAX_REPORT_BYTES = 64 * 1024 * 1024
MAX_COMPRESSED_BYTES = 128 * 1024 * 1024
MAX_AUDIT_BYTES = 512 * 1024 * 1024
MAX_EVENT_BYTES = 8 * 1024 * 1024
MAX_AUDIT_RECORDS = 250_000
MAX_EXPERIMENTS = 1000
_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_-]{0,127}\Z')
_HASH = re.compile(r'[0-9a-f]{64}\Z')
_ANALYST_EVENTS = {'analyst_request', 'analyst_response', 'analyst_failed',
                   'analyst_validated', 'analyst_cache'}


def _encode(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':'))


def _json(value):
    def invalid_constant(_):
        raise ValueError('non-finite JSON value')
    def finite_float(text):
        result = float(text)
        if not math.isfinite(result):
            raise ValueError('non-finite JSON value')
        return result
    return json.loads(value, parse_constant=invalid_constant, parse_float=finite_float)


def _integer(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _timestamp(value):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value) and value >= 0)


def _fingerprint(path):
    stat = path.stat()
    return stat.st_size, stat.st_mtime_ns, stat.st_ino


@dataclass
class _Entry:
    directory: Path
    manifest: dict
    summary: dict
    fingerprints: dict
    audit_checked: bool = False
    audit_record_bytes: int = 0
    analyst_rows: list = field(default_factory=list)
    lock: object = field(default_factory=threading.Lock)


class PublishedExperiments:
    def __init__(self, root=None):
        self.root = Path(ROOT if root is None else root).resolve()
        self._entries = {}
        if not self.root.exists():
            raise ValueError('Published experiments directory is missing from the deployment')
        if not self.root.is_dir():
            raise ValueError('Published experiments root must be a directory')
        for directory in sorted(self.root.iterdir()):
            if not directory.is_dir():
                continue
            # Every flat export directory must be complete. An empty or partly
            # published export must not silently disappear from the demo.
            if len(self._entries) >= MAX_EXPERIMENTS:
                raise ValueError('Published experiment count exceeds the catalog limit')
            try:
                self._load(directory)
            except (OSError, ValueError, TypeError, KeyError, RecursionError) as exc:
                raise ValueError(f'Invalid published experiment {directory.name}: {exc}') from exc

    def _file(self, directory, name):
        path = directory / name
        if (directory.is_symlink() or path.is_symlink()
                or directory.resolve().parent != self.root
                or path.resolve().parent != directory.resolve()
                or not path.is_file()):
            raise ValueError(f'Unsafe or missing published file: {name}')
        return path

    def _load(self, directory):
        manifest_path = self._file(directory, 'manifest.json')
        if manifest_path.stat().st_size > MAX_MANIFEST_BYTES:
            raise ValueError('Manifest exceeds the publication limit')
        manifest = _json(manifest_path.read_bytes())
        if not isinstance(manifest, dict):
            raise ValueError('Manifest must be an object')
        run_id = manifest.get('run_id')
        if not isinstance(run_id, str) or not _ID.fullmatch(run_id):
            raise ValueError('Invalid published run ID')
        if run_id in self._entries:
            raise ValueError(f'Duplicate published run ID: {run_id}')
        if manifest.get('source') != 'adaptive_thompson_pricing' or manifest.get('synthetic') is not True:
            raise ValueError('Only synthetic Thompson exports can be published')
        count = manifest.get('audit_records')
        if not _integer(count) or not 0 <= count <= MAX_AUDIT_RECORDS:
            raise ValueError('Invalid published audit record count')
        files = manifest.get('files')
        if not isinstance(files, dict) or set(files) != {'report.json', 'audit.jsonl.gz'}:
            raise ValueError('Manifest must name exactly report.json and audit.jsonl.gz')
        fingerprints = {'manifest.json': _fingerprint(manifest_path)}
        for name, limit in (('report.json', MAX_REPORT_BYTES), ('audit.jsonl.gz', MAX_COMPRESSED_BYTES)):
            path = self._file(directory, name)
            info = files[name]
            if not isinstance(info, dict) or not _integer(info.get('bytes')) or not 0 <= info['bytes'] <= limit:
                raise ValueError(f'Invalid or oversized published file: {name}')
            if not isinstance(info.get('sha256'), str) or not _HASH.fullmatch(info['sha256']):
                raise ValueError(f'Invalid published SHA256: {name}')
            before = _fingerprint(path)
            if before[0] != info['bytes']:
                raise ValueError(f'Published byte count mismatch: {name}')
            digest = hashlib.sha256()
            with path.open('rb') as source:
                for chunk in iter(lambda: source.read(1024 * 1024), b''):
                    digest.update(chunk)
            if digest.hexdigest() != info['sha256'] or before != _fingerprint(path):
                raise ValueError(f'Published SHA256 mismatch: {name}')
            fingerprints[name] = before
        report = _json((directory / 'report.json').read_bytes())
        if not isinstance(report, dict) or report.get('run_id') != run_id:
            raise ValueError('Published report and manifest run IDs differ')
        if (report.get('version') != VERSION
                or not isinstance(report.get('config'), dict)
                or report['config'].get('profile') != PROFILE
                or manifest.get('version', VERSION) != VERSION
                or manifest.get('profile', PROFILE) != PROFILE):
            raise ValueError('Published report is not the current v5 customer profile')
        status = report.get('status')
        if status not in ('completed', 'failed', 'interrupted'):
            raise ValueError('Only terminal experiments can be published; active runs cannot resume')
        expected_kind = 'completed' if status == 'completed' else 'execution_failure'
        if manifest.get('evidence_kind', 'completed') != expected_kind:
            raise ValueError('Published evidence kind does not match report status')
        if not _timestamp(report.get('created_at')) or not _timestamp(report.get('updated_at')):
            raise ValueError('Invalid published experiment timestamps')
        entry = _Entry(directory, manifest, {k: report.get(k) for k in SUMMARY_KEYS}, fingerprints)
        self._unchanged(entry)
        self._entries[run_id] = entry

    def _unchanged(self, entry):
        for name, original in entry.fingerprints.items():
            path = self._file(entry.directory, name)
            if _fingerprint(path) != original:
                raise ValueError('Published experiment changed after validation; restart to reload the catalog')

    def contains(self, run_id):
        return run_id in self._entries

    def _entry(self, run_id):
        if run_id not in self._entries:
            raise ValueError('Adaptive pricing run not found')
        entry = self._entries[run_id]
        self._unchanged(entry)
        return entry

    @staticmethod
    def _marked(report):
        return {**report, 'storage': {'source': 'published_export', 'read_only': True}}

    def summaries(self):
        return [self._marked(copy.deepcopy(self._entry(run_id).summary)) for run_id in self._entries]

    def read(self, run_id):
        entry = self._entry(run_id)
        report = _json((entry.directory / 'report.json').read_bytes())
        self._unchanged(entry)
        return self._marked(report)

    def _stream(self, entry):
        total, previous_id, count = 0, 0, 0
        run_id = entry.summary['run_id']
        try:
            with gzip.open(entry.directory / 'audit.jsonl.gz', 'rb') as source:
                while True:
                    line = source.readline(MAX_EVENT_BYTES + 1)
                    if not line:
                        break
                    total += len(line)
                    count += 1
                    if len(line) > MAX_EVENT_BYTES or total > MAX_AUDIT_BYTES or count > MAX_AUDIT_RECORDS:
                        raise ValueError('Published audit exceeds the decompression limit')
                    event = _json(line)
                    if (not isinstance(event, dict) or not _integer(event.get('id'))
                            or event['id'] <= previous_id or event.get('run_id') != run_id
                            or not _timestamp(event.get('recorded_at'))
                            or not isinstance(event.get('record'), dict)):
                        raise ValueError('Invalid published audit event or event ordering')
                    previous_id = event['id']
                    yield event
        except (OSError, EOFError, UnicodeError, RecursionError) as exc:
            raise ValueError('Invalid published compressed audit') from exc

    @staticmethod
    def _analyst_row(event):
        record = event['record']
        if not isinstance(record.get('event'), str) or record['event'] not in _ANALYST_EVENTS:
            return None
        number = record.get('round')
        if not _integer(number):
            try:
                context = _json(record['request']['messages'][1]['content'])
                number = context.get('round') if isinstance(context, dict) else None
            except (ValueError, TypeError, KeyError, IndexError, RecursionError):
                number = None
        raw = record.get('raw_response_text')
        return {'id': event['id'], 'event': record['event'], 'round_number': number,
                'attempt': record.get('attempt'), 'context_hash': record.get('context_sha256'),
                'error': record.get('error'), 'error_type': record.get('error_type'),
                'failure_kind': record.get('failure_kind'), 'provider_call': record.get('provider_call'),
                'raw_available': isinstance(raw, str),
                'raw_bytes': len(_encode(raw).encode('utf-8')) if isinstance(raw, str) else 0}

    def _audit(self, run_id):
        entry = self._entry(run_id)
        with entry.lock:
            if not entry.audit_checked:
                count, raw_bytes, rows = 0, 0, []
                for event in self._stream(entry):
                    count += 1
                    raw_bytes += len(_encode(event['record']).encode('utf-8'))
                    row = self._analyst_row(event)
                    if row is not None:
                        rows.append(row)
                if count != entry.manifest['audit_records']:
                    raise ValueError('Published audit record count mismatch')
                self._unchanged(entry)
                entry.audit_record_bytes, entry.analyst_rows = raw_bytes, rows
                entry.audit_checked = True
        return entry

    def events(self, run_id, limit, offset, max_bytes):
        entry = self._audit(run_id)
        page, size = [], 0
        for index, event in enumerate(self._stream(entry)):
            if index < offset:
                continue
            size += len(_encode(event).encode('utf-8')) + 1
            if size + 20 > max_bytes:
                raise ValueError('Published event page exceeds the inline export limit; request a smaller page')
            page.append(event)
            if len(page) == limit:
                break
        self._unchanged(entry)
        return {'events': page}

    def analyst_rows(self, run_id):
        return self._audit(run_id).analyst_rows

    def raw_responses(self, run_id, event_ids):
        if not event_ids:
            return {}
        entry = self._audit(run_id)
        raw = {}
        for event in self._stream(entry):
            if event['id'] in event_ids:
                raw[event['id']] = event['record'].get('raw_response_text')
                if len(raw) == len(event_ids):
                    break
        self._unchanged(entry)
        return raw

    def export(self, run_id, max_bytes):
        entry = self._audit(run_id)
        report = self.read(run_id)
        size = len(_encode(report).encode('utf-8')) + 30
        if entry.audit_record_bytes + size > max_bytes:
            raise ValueError('Adaptive audit exceeds the inline export limit; use paginated events')
        events = []
        for event in self._stream(entry):
            size += len(_encode(event).encode('utf-8')) + 1
            if size > max_bytes:
                raise ValueError('Adaptive audit exceeds the inline export limit; use paginated events')
            events.append(event)
        self._unchanged(entry)
        return {'report': report, 'events': events}

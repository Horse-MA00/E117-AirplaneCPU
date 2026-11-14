"""Local same-origin application server. Run: python -m backend.server.

The server is deliberately stdlib-only. ``get`` and ``post`` map an API path to
a JSON-serialisable payload; ``Handler`` adds HTTP concerns (host/origin
checks, security headers, static files and error-to-status mapping).
"""

import json
import math
import mimetypes
import re
import traceback
from functools import lru_cache
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse, urlsplit

from . import adaptive_pricing, adaptive_store, data, demo_auth, member_portal
from .errors import NotFound
from .evidence import EvidenceUnavailable, read_evaluation
from .fare_policy import check_member_fare
from .oag import load_env
from .seat_inventory import describe as describe_seat_inventory
from .store import Store

ROOT = Path(__file__).resolve().parents[1]
load_env()

LOCAL_HOSTS = ('127.0.0.1', 'localhost', '::1')
MAX_BODY_BYTES = 65536
DEFAULT_MANDATORY_FEES = 250
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'"
)
SECURITY_HEADERS = {
    'Cache-Control': 'no-store',
    'X-Content-Type-Options': 'nosniff',
    'Referrer-Policy': 'no-referrer',
    'Content-Security-Policy': CONTENT_SECURITY_POLICY,
}
PAGE_ALIASES = {
    '/admin': 'index.html',
    '/admin/': 'index.html',
    '/members': 'members/index.html',
    '/members/': 'members/index.html',
    '/members/login': 'members/login.html',
    '/members/login/': 'members/login.html',
    '/adaptive-pricing': 'adaptive-pricing.html',
    '/adaptive-pricing/': 'adaptive-pricing.html',
}
RELEASE_ROUND_ASSUMPTION = (
    'New member quota is issued once per round at D28, D14 and D7 only. '
    'Earlier valid unsold quotas carry forward; sold demo seats are accounted once.'
)

_store = None


def store():
    """Lazily open the private demo database (tests patch ``_store``)."""
    global _store
    if _store is None:
        _store = Store(ROOT / 'data/private/demo.sqlite3')
    return _store


# --- Input validation -------------------------------------------------------


def number(value, name, low, high, integer=False):
    """Return ``value`` if it is a finite number in ``low..high``; else raise ValueError."""
    valid = (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(value)
        and low <= value <= high
        and (not integer or int(value) == value)
    )
    if not valid:
        raise ValueError(f'{name} must be {low}..{high}' + (' (integer)' if integer else ''))
    return int(value) if integer else value


def ident(value):
    """Return ``value`` if it is a safe identifier (letters, digits, ``_`` or ``-``)."""
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', value):
        raise ValueError('Invalid identifier')
    return value


def query_int(query, names, default):
    """First present query parameter as an integer; malformed input is a 400, not a 404."""
    for name in names:
        if name in query:
            try:
                return int(query[name][0])
            except ValueError:
                raise ValueError(f'{name} must be an integer') from None
    return default


@lru_cache(maxsize=96)
def forecast_for(flight, day):
    from .forecast import forecast

    return forecast(data.history(flight), days_to_departure=day, seed=117)


def _path_parts(path):
    return path.strip('/').split('/')


# --- GET endpoints ----------------------------------------------------------


def _health(query):
    with store().connect() as connection:
        connection.execute('SELECT 1').fetchone()
    return {'status': 'ok'}


def _summary(query):
    manifest = data.manifest()
    return {
        'dataset': {
            'rows': manifest['rows'],
            'catalog_rows': manifest.get('catalog_rows', manifest['rows']),
            'flights': len(data.flights()),
            'source': 'synthetic',
            'manifest': manifest,
        },
        'model': 'NHPP',
        'llm': adaptive_pricing.status(),
    }


def _oag_cache_files():
    return (ROOT / 'data/private').glob('oag-*.json')


def _oag_capacity_row(row):
    departure = row.get('departure', {})
    return {
        'carrier': row.get('carrier', {}).get('iata'),
        'flight_number': row.get('flightNumber'),
        'origin': departure.get('airport', {}).get('iata'),
        'destination': row.get('arrival', {}).get('airport', {}).get('iata'),
        'date': departure.get('date', {}).get('local'),
        'predicted_capacity': row.get('seatingCapacity', {}).get('predicted', {}).get('totalSeats'),
        'source': 'oag_live_cached_capacity_estimate',
    }


def _oag(query):
    flights = []
    for path in _oag_cache_files():
        cached = json.loads(path.read_text())
        flights.extend(_oag_capacity_row(row) for row in cached.get('records', []))
    return {'flights': flights, 'limitation': 'Capacity estimates only, no observed fares or occupancy.'}


def _status(query):
    records = []
    for path in _oag_cache_files():
        cached = json.loads(path.read_text())
        records.append(
            {
                'date': cached['date'],
                'state': cached['state'],
                'record_count': len(cached['records']),
                'attempts': cached['attempts'],
            }
        )
    return {'model': 'NHPP', 'llm': adaptive_pricing.status(), 'oag': records, 'simulated_booking': True}


def _adaptive_run(path, query):
    parts = _path_parts(path)  # api / adaptive-pricing / runs / <id> [/ <view>]
    query = query or {}
    try:
        if len(parts) == 4:
            return adaptive_pricing.read(ident(parts[3]))
        if len(parts) == 5:
            run_id, view = ident(parts[3]), parts[4]
            if view == 'export':
                return adaptive_pricing.export_run(run_id)
            if view == 'events':
                return adaptive_pricing.events(
                    run_id, query_int(query, ('limit',), 100), query_int(query, ('offset',), 0)
                )
            if view == 'analysis-attempts':
                adaptive_pricing.read(run_id)  # 404 for an unknown run before listing attempts
                return adaptive_store.analysis_attempts(run_id, query_int(query, ('round',), None))
    except ValueError as error:
        if str(error) == 'Adaptive pricing run not found':
            raise NotFound(str(error)) from None
        raise
    raise NotFound('Adaptive pricing endpoint not found')


def _member_account(path, query):
    if len(_path_parts(path)) != 4:
        raise NotFound('Account endpoint not found')
    return member_portal.account(store(), ident(path.split('/')[-1]))


def _flight(path, query):
    flight_id = ident(path.split('/')[-1])
    history = data.history(flight_id)  # raises NotFound for an unknown flight
    flight = next((f for f in data.flights() if f['flight_id'] == flight_id), None)
    if flight is None:
        raise NotFound('Unknown flight')
    return {'flight': flight, 'history': history}


GET_ROUTES = {
    '/api/adaptive-pricing/status': lambda query: adaptive_pricing.status(),
    '/api/adaptive-pricing/runs': lambda query: {'runs': adaptive_pricing.list_runs()},
    '/api/health': _health,
    '/api/member-portal/config': lambda query: member_portal.config(store()),
    '/api/member-portal/plan': lambda query: member_portal.config(store()),
    '/api/member-portal/flights': lambda query: member_portal.flights(store(), forecast_for),
    '/api/summary': _summary,
    '/api/evaluation': lambda query: read_evaluation(ROOT),
    '/api/evaluation/extended': lambda query: read_evaluation(ROOT, extended=True),
    '/api/oag': _oag,
    '/api/status': _status,
    '/api/flights': lambda query: {'flights': data.flights()},
    '/api/offers': lambda query: {'offers': store().offers()},
}
GET_PREFIX_ROUTES = (
    ('/api/adaptive-pricing/runs/', _adaptive_run),
    ('/api/member-portal/accounts/', _member_account),
    ('/api/flights/', _flight),
)


def get(path, query=None):
    if path in GET_ROUTES:
        return GET_ROUTES[path](query)
    for prefix, handler in GET_PREFIX_ROUTES:
        if path.startswith(prefix):
            return handler(path, query)
    raise NotFound('Not found')


# --- POST endpoints ---------------------------------------------------------


def _optional_number(body, key, high):
    return number(body[key], key, 0, high) if key in body else None


def _set_plan(body):
    store().plan(number(body.get('membership_fee'), 'membership_fee', 0, 5000, True))
    return member_portal.config(store())


def _join(body):
    expected_fee = _optional_number(body, 'expected_fee', 5000)
    member = store().join_plan(ident(body.get('customer_id')), expected_fee)
    return {'member': member, 'simulated': True, 'currency': 'HKD'}


def _book(body):
    expected_total = _optional_number(body, 'expected_total', 10000)
    return member_portal.book(
        store(), forecast_for, ident(body.get('customer_id')), ident(body.get('offer_id')), expected_total
    )


def _flight_and_day(body):
    flight_id = ident(body.get('flight_id'))
    day = number(body.get('days_to_departure', 28), 'day', 0, 28, True)
    return flight_id, day


def _forecast(body):
    flight_id, day = _flight_and_day(body)
    prediction = forecast_for(flight_id, day)
    release = store().release_status(flight_id, day, prediction['releasable_seats'])
    current = dict(prediction)
    current['risk_release_ceiling'] = prediction['releasable_seats']
    current['release_status'] = release
    current['seat_inventory'] = describe_seat_inventory(prediction, release, day)
    current['releasable_seats'] = release['new_release_limit']
    current['committed_member_seats'] = release['member_sold'] + release['total_active_unsold']
    blocked = [release['blocked_reason']] if release['blocked_reason'] else []
    current['assumptions'] = list(prediction['assumptions']) + [RELEASE_ROUND_ASSUMPTION] + blocked
    return {'forecast': current}


def _visible_normal_fare(history, day):
    """Normal base fare at the release day, or the nearest earlier observed one."""
    by_day = sorted(history, key=lambda row: row['days_to_departure'])
    quote = next(
        (row for row in by_day if row['days_to_departure'] >= day and row.get('normal_base_fare') is not None), None
    )
    if quote is None:
        raise ValueError('No observable normal base fare to cap the member fare')
    return quote['normal_base_fare']


def _create_offer(body):
    if any(key in body for key in ('optimization_run_id', 'optimization_mode')):
        raise ValueError('Retired optimization bindings are not accepted; submit a manual offer')
    flight_id, day = _flight_and_day(body)
    prediction = forecast_for(flight_id, day)
    quantity = number(body.get('quantity'), 'quantity', 1, 400, True)
    fare = number(body.get('base_fare'), 'base_fare', 0, 3000, True)
    history = data.history(flight_id)
    snapshot = next((row for row in history if row['days_to_departure'] == day), None)
    if snapshot is None:
        raise ValueError(f'No booking snapshot for D{day}')
    # Member fares may never exceed 80% of the normal base fare visible at this release day.
    check_member_fare(fare, _visible_normal_fare(history, day))
    max_quantity = int(
        prediction.get('releasable', prediction.get('releasable_seats', prediction.get('max_member_seats', 0)))
    )
    if day == 0:
        raise ValueError('Sales are closed')
    fees = snapshot['mandatory_fees'] if snapshot['mandatory_fees'] is not None else DEFAULT_MANDATORY_FEES
    return {'offer': store().offer(flight_id, day, quantity, fare, fees, max_quantity), 'simulated': True}


POST_ROUTES = {
    '/api/adaptive-pricing/scope': adaptive_pricing.scope,
    '/api/adaptive-pricing/runs': adaptive_pricing.start,
    '/api/member-portal/plan': _set_plan,
    '/api/member-portal/join': _join,
    '/api/member-portal/book': _book,
    '/api/forecast': _forecast,
    '/api/offers': _create_offer,
}


def post(path, body):
    if path not in POST_ROUTES:
        raise NotFound('Not found')
    return POST_ROUTES[path](body)


# --- HTTP layer -------------------------------------------------------------


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def send_response_headers(self, status, ctype, length, filename='snapshots.csv.gz', extra_headers=None):
        self.send_response(status)
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)
        if ctype == 'application/gzip':
            self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
        if length is not None:
            self.send_header('Content-Length', str(length))
        self.send_header('Content-Type', ctype)
        for key, value in SECURITY_HEADERS.items():
            self.send_header(key, value)
        self.end_headers()

    def send_bytes(self, ctype, payload):
        self.send_response_headers(200, ctype, len(payload))
        self.wfile.write(payload)

    # Named ``json`` because tests replace it; inside methods ``json`` still
    # refers to the stdlib module, not this method.
    def json(self, status, payload, extra_headers=None):
        content = json.dumps(
            payload, ensure_ascii=False, allow_nan=False, default=lambda x: x.item() if hasattr(x, 'item') else str(x)
        ).encode()
        self.send_response_headers(status, 'application/json; charset=utf-8', len(content), extra_headers=extra_headers)
        self.wfile.write(content)

    def allowed_host(self):
        try:
            host = urlsplit('//' + self.headers.get('Host', '')).hostname
        except ValueError:
            return False
        return host in LOCAL_HOSTS

    def allowed_origin(self):
        origin = self.headers.get('Origin')
        port = self.server.server_port
        return not origin or origin in (f'http://localhost:{port}', f'http://127.0.0.1:{port}')

    def cookie(self):
        return self.headers.get('Cookie')

    def send_error_json(self, error):
        """Map a domain exception to an HTTP status; unknown errors become 500."""
        if isinstance(error, EvidenceUnavailable):
            self.json(
                503,
                {
                    'status': 'unavailable',
                    'code': 'evaluation_evidence_unavailable',
                    'artifact': error.artifact,
                    'error': str(error),
                },
            )
        elif isinstance(error, demo_auth.AuthError):
            self.json(error.status, {'error': str(error)})
        elif isinstance(error, NotFound):
            self.json(404, {'error': str(error)})
        elif isinstance(error, (ValueError, TypeError)):
            self.json(400, {'error': str(error)})
        else:
            traceback.print_exc()
            self.json(500, {'error': 'Server error; inspect local terminal'})

    def do_GET(self):
        if not self.allowed_host():
            return self.json(403, {'error': 'Local host only'})
        path = unquote(urlparse(self.path).path)
        try:
            self.route_get(path)
        except Exception as error:
            self.send_error_json(error)

    def route_get(self, path):
        if path == '/api/member-portal/session':
            return self.json(200, demo_auth.current(store(), self.cookie()))
        if path.startswith('/api/member-portal/accounts/'):
            demo_auth.authorize_account(store(), self.cookie(), ident(path.split('/')[-1]))
        if path == '/api/export/snapshots':
            return self.send_bytes('application/gzip', (data.DATA / 'snapshots.csv.gz').read_bytes())
        if path.startswith('/api/'):
            return self.json(200, get(path, parse_qs(urlparse(self.path).query)))
        self.send_static(path)

    def send_static(self, path):
        root = (ROOT / 'frontend').resolve()
        file = (root / PAGE_ALIASES.get(path, path.lstrip('/') or 'index.html')).resolve()
        if root not in file.parents or not file.is_file():
            return self.json(404, {'error': 'Not found'})
        self.send_bytes(mimetypes.guess_type(file.name)[0] or 'application/octet-stream', file.read_bytes())

    def do_POST(self):
        if not self.allowed_host():
            return self.json(403, {'error': 'Local host only'})
        if not self.allowed_origin():
            return self.json(403, {'error': 'Origin not allowed'})
        if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
            return self.json(415, {'error': 'JSON required'})
        try:
            self.route_post(urlparse(self.path).path, self.read_json_body())
        except Exception as error:
            self.send_error_json(error)

    def read_json_body(self):
        length = int(self.headers.get('Content-Length', '0'))
        if not 0 < length <= MAX_BODY_BYTES:
            raise ValueError('Invalid request size')
        body = json.loads(self.rfile.read(length))
        if not isinstance(body, dict):
            raise ValueError('JSON object required')
        return body

    def route_post(self, path, body):
        if path == '/api/member-portal/login':
            result, cookie = demo_auth.login(store(), body, self.cookie())
            return self.json(200, result, {'Set-Cookie': cookie})
        if path == '/api/member-portal/logout':
            result, cookie = demo_auth.logout(store(), self.cookie())
            return self.json(200, result, {'Set-Cookie': cookie})
        if path in ('/api/member-portal/join', '/api/member-portal/book'):
            demo_auth.authorize_account(store(), self.cookie(), ident(body.get('customer_id')))
        self.json(200, post(path, body))


class Server(ThreadingHTTPServer):
    # The stdlib default backlog of 5 resets bursts of concurrent requests.
    request_queue_size = 128
    daemon_threads = True


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--host', choices=('127.0.0.1', '0.0.0.0'), default='127.0.0.1')
    args = parser.parse_args()
    store()
    print(f'UOption Fly Pass: http://127.0.0.1:{args.port}', flush=True)
    Server((args.host, args.port), Handler).serve_forever()


if __name__ == '__main__':
    main()

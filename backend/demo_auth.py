"""Two public demonstration logins; not production customer authentication.

Credentials are deliberately published for the Hackathon. Cookie sessions bind
the two reserved demo identities; legacy arbitrary-ID developer APIs remain.
"""
import hashlib
import hmac
from http.cookies import CookieError, SimpleCookie
import re
import secrets
import time

COOKIE_NAME = 'uoption_demo_session'
SESSION_SECONDS = 24 * 60 * 60
DEMO_PASSWORD = 'FlyPass399!'
USERS = {
    'member@uoption.test': {'customer_id': 'demo-member', 'email': 'member@uoption.test',
                          'name': 'Member demo', 'prepaid': True},
    'guest@uoption.test': {'customer_id': 'demo-guest', 'email': 'guest@uoption.test',
                         'name': 'Guest demo', 'prepaid': False},
}
RESERVED_IDS = frozenset(user['customer_id'] for user in USERS.values())


class AuthError(ValueError):
    def __init__(self, message, status=401):
        super().__init__(message)
        self.status = status


def _table(connection):
    connection.execute('''CREATE TABLE IF NOT EXISTS demo_sessions(
        token_hash TEXT PRIMARY KEY, email TEXT NOT NULL, expires REAL NOT NULL)''')


def _digest(cookie_header):
    cookie = SimpleCookie()
    try:
        cookie.load(cookie_header or '')
    except CookieError:
        return None
    token = cookie.get(COOKIE_NAME)
    if token is None or not re.fullmatch(r'[A-Za-z0-9_-]{43}', token.value):
        return None
    return hashlib.sha256(token.value.encode()).hexdigest()


def _cookie(token='', max_age=0):
    return f'{COOKIE_NAME}={token}; Path=/; Max-Age={max_age}; HttpOnly; SameSite=Lax'


def _payload(store, user):
    return {'authenticated': True, 'simulated': True,
            'user': {key: user[key] for key in ('customer_id', 'email', 'name')},
            'account': store.account(user['customer_id'])}


def current(store, cookie_header):
    digest = _digest(cookie_header)
    if digest is None:
        return {'authenticated': False, 'simulated': True}
    with store.connect() as connection:
        _table(connection)
        connection.execute('DELETE FROM demo_sessions WHERE expires<=?', (time.time(),))
        row = connection.execute('SELECT email FROM demo_sessions WHERE token_hash=?', (digest,)).fetchone()
    user = USERS.get(row['email']) if row else None
    return _payload(store, user) if user else {'authenticated': False, 'simulated': True}


def login(store, body, cookie_header=''):
    email = body.get('email')
    email = email.strip().lower() if isinstance(email, str) else ''
    password = body.get('password')
    user = USERS.get(email)
    valid_password = (isinstance(password, str) and
                      hmac.compare_digest(password.encode(), DEMO_PASSWORD.encode()))
    if not user or not valid_password:
        raise AuthError('Email or password is incorrect. Use one of the displayed demo accounts.')
    # Seed a simulated paid membership only once. Login never renews or rewrites
    # an existing membership, nor erases a guest's subsequent purchase.
    if user['prepaid'] and store.account(user['customer_id'])['membership'] is None:
        store.join_plan(user['customer_id'])
    token = secrets.token_urlsafe(32)
    digest = hashlib.sha256(token.encode()).hexdigest()
    with store.connect() as connection:
        _table(connection)
        connection.execute('DELETE FROM demo_sessions WHERE expires<=?', (time.time(),))
        previous = _digest(cookie_header)
        if previous:
            connection.execute('DELETE FROM demo_sessions WHERE token_hash=?', (previous,))
        connection.execute('INSERT INTO demo_sessions VALUES(?,?,?)',
                           (digest, email, time.time() + SESSION_SECONDS))
    return _payload(store, user), _cookie(token, SESSION_SECONDS)


def logout(store, cookie_header):
    digest = _digest(cookie_header)
    if digest:
        with store.connect() as connection:
            _table(connection)
            connection.execute('DELETE FROM demo_sessions WHERE token_hash=?', (digest,))
    return {'authenticated': False, 'simulated': True}, _cookie()


def authorize_account(store, cookie_header, customer_id):
    session = current(store, cookie_header)
    if session['authenticated']:
        if customer_id != session['user']['customer_id']:
            raise AuthError('This account does not belong to the signed-in demo user.', 403)
    elif customer_id in RESERVED_IDS:
        raise AuthError('Sign in to access this demo account.')

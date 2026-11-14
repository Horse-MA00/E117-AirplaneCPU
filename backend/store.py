"""Transactional three-round demo inventory; no real payments or tickets."""
import math
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from .release_policy import RELEASE_DAYS, VERSION as RELEASE_VERSION, release_budget


class Store:
    def __init__(self, path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as c:
            c.executescript('''
                CREATE TABLE IF NOT EXISTS offers(id TEXT PRIMARY KEY,flight_id TEXT,day INTEGER,quantity INTEGER,remaining INTEGER,base_fare REAL,fees REAL,created REAL,expires REAL);
                CREATE TABLE IF NOT EXISTS members(customer_id TEXT PRIMARY KEY,fee REAL,created REAL,expires REAL);
                CREATE TABLE IF NOT EXISTS bookings(id TEXT PRIMARY KEY,offer_id TEXT,flight_id TEXT,customer_id TEXT,total REAL,created REAL,UNIQUE(flight_id,customer_id));
                CREATE TABLE IF NOT EXISTS flight_clocks(flight_id TEXT PRIMARY KEY,day INTEGER,risk_limit INTEGER,cutoff REAL);
            ''')
            columns = {row['name'] for row in c.execute('PRAGMA table_info(offers)')}
            if 'release_version' not in columns:
                c.execute("ALTER TABLE offers ADD COLUMN release_version TEXT NOT NULL DEFAULT 'legacy-daily-demo'")

    @contextmanager
    def connect(self):
        c = sqlite3.connect(self.path, timeout=10)
        c.row_factory = sqlite3.Row
        try:
            with c:
                yield c
        finally:
            c.close()

    @staticmethod
    def _day(day):
        if isinstance(day, bool) or not isinstance(day, int) or not 0 <= day <= 28:
            raise ValueError('Simulation day must be an integer from 0 to 28')

    def _status(self, c, flight, day, max_release):
        self._day(day)
        now = time.time()
        rows = c.execute('SELECT * FROM offers WHERE flight_id=? ORDER BY day DESC,created', (flight,)).fetchall()
        clock = c.execute('SELECT * FROM flight_clocks WHERE flight_id=?', (flight,)).fetchone()
        last_day = clock['day'] if clock else min((r['day'] for r in rows), default=28)
        sold = sum(r['quantity'] - r['remaining'] for r in rows)
        active = [r for r in rows if day > 0 and r['day'] >= day and r['expires'] > now]
        outstanding = sum(r['remaining'] for r in active)
        carry = sum(r['remaining'] for r in active if r['day'] > day)
        issued = any(r['day'] == day for r in rows)
        historical = bool(rows or clock) and day > last_day
        cutoff_passed = bool(clock and clock['cutoff'] <= now)
        reason = ('Sales cutoff has passed; no further release is allowed.' if cutoff_passed else
                  'This simulation has already advanced; earlier dates are read-only.' if historical else
                  'New quota is issued only at D28, D14 and D7.' if day not in RELEASE_DAYS else
                  'This release round has already been issued.' if issued else '')
        # max_release is the ceiling from a normal-only snapshot. Demo member
        # sales are absent from that snapshot and must be subtracted exactly once.
        remaining_ceiling = max(0, int(max_release) - sold)
        budget = release_budget(remaining_ceiling, 0, outstanding)
        limit = 0 if reason else budget['new_allocation']
        history = [{'day': r['day'], 'quantity': r['quantity'], 'sold': r['quantity'] - r['remaining'],
                    'remaining': r['remaining'], 'valid': r in active, 'expires': r['expires'],
                    'release_version': r['release_version']} for r in rows]
        return {'release_days': list(RELEASE_DAYS), 'release_version': RELEASE_VERSION,
                'is_release_day': day in RELEASE_DAYS, 'round_already_issued': issued,
                'previous_valid_unsold': carry, 'member_sold': sold,
                'total_active_unsold': outstanding, 'new_release_limit': limit,
                'remaining_risk_ceiling': remaining_ceiling,
                'safe_capacity': remaining_ceiling,
                'currently_bookable': 0 if historical or day == 0 or cutoff_passed else min(outstanding, remaining_ceiling),
                'protection_shortfall': max(0, outstanding - remaining_ceiling),
                'next_release_day': None if cutoff_passed else next((d for d in RELEASE_DAYS if d < day and d <= last_day and not any(r['day'] == d for r in rows)), None),
                'simulation_day': last_day, 'blocked_reason': reason, 'round_history': history}

    def release_status(self, flight, day, max_release):
        with self.connect() as c:
            return self._status(c, flight, day, max_release)

    def committed(self, flight, day):
        with self.connect() as c:
            status = self._status(c, flight, day, 0)
            if day > status['simulation_day']:
                return None
            return status['member_sold'] + status['total_active_unsold']

    def _advance(self, c, flight, day, risk_limit):
        now = time.time()
        clock = c.execute('SELECT * FROM flight_clocks WHERE flight_id=?', (flight,)).fetchone()
        cutoff = now + max(0, day * 86400 - 7200)
        if clock:
            if day > clock['day']:
                raise ValueError('Cannot rewind the simulation after an issued round or booking')
            cutoff = min(cutoff, clock['cutoff'])
        c.execute('INSERT OR REPLACE INTO flight_clocks VALUES(?,?,?,?)', (flight, day, risk_limit, cutoff))
        c.execute('UPDATE offers SET expires=MIN(expires,?) WHERE flight_id=?', (cutoff, flight))
        return cutoff

    def offers(self):
        with self.connect() as c:
            return [dict(r) for r in c.execute('''SELECT o.*, COALESCE(f.day,o.day) AS sim_day
                FROM offers o LEFT JOIN flight_clocks f ON f.flight_id=o.flight_id
                WHERE o.expires>? ORDER BY o.created DESC''', (time.time(),))]

    def offer_info(self, offer_id):
        with self.connect() as c:
            row = c.execute('''SELECT o.*, COALESCE(f.day,o.day) AS sim_day FROM offers o
                LEFT JOIN flight_clocks f ON f.flight_id=o.flight_id WHERE o.id=?''', (offer_id,)).fetchone()
            if row is None:
                raise ValueError('Offer not found')
            return dict(row)

    def offer(self, flight, day, quantity, fare, fees, max_release):
        self._day(day)
        if day not in RELEASE_DAYS:
            raise ValueError('New quota is issued only at D28, D14 and D7')
        if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 1:
            raise ValueError('Quantity must be a positive integer')
        if any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) or x < 0 for x in (fare, fees, max_release)):
            raise ValueError('Prices and release limit must be finite and nonnegative')
        now = time.time()
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            status = self._status(c, flight, day, max_release)
            if status['blocked_reason']:
                raise ValueError(status['blocked_reason'])
            if quantity > status['new_release_limit']:
                raise ValueError('Quantity exceeds the new round limit after sold seats and valid unsold quotas')
            cutoff = self._advance(c, flight, day, int(max_release))
            id = str(uuid.uuid4())
            c.execute('INSERT INTO offers(id,flight_id,day,quantity,remaining,base_fare,fees,created,expires,release_version) VALUES(?,?,?,?,?,?,?,?,?,?)',
                      (id, flight, day, quantity, quantity, fare, fees, now, cutoff, RELEASE_VERSION))
            return dict(c.execute('SELECT * FROM offers WHERE id=?', (id,)).fetchone())

    def member(self, customer_id, fee):
        now = time.time()
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            row = c.execute('SELECT * FROM members WHERE customer_id=?', (customer_id,)).fetchone()
            if row:
                if row['expires'] <= now:
                    raise ValueError('Membership expired; renewal is not implemented in this demo')
                return dict(row)
            c.execute('INSERT INTO members VALUES(?,?,?,?)', (customer_id, fee, now, now + 365 * 86400))
            return dict(c.execute('SELECT * FROM members WHERE customer_id=?', (customer_id,)).fetchone())

    def book(self, offer_id, customer_id, day=None, max_release=None):
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            member = c.execute('SELECT * FROM members WHERE customer_id=? AND expires>?', (customer_id, time.time())).fetchone()
            if not member:
                raise ValueError('An active demo membership is required')
            offer = c.execute('SELECT * FROM offers WHERE id=? AND expires>?', (offer_id, time.time())).fetchone()
            if not offer or offer['remaining'] < 1:
                raise ValueError('Offer unavailable or sold out')
            clock = c.execute('SELECT * FROM flight_clocks WHERE flight_id=?', (offer['flight_id'],)).fetchone()
            day = day if day is not None else clock['day'] if clock else offer['day']
            self._day(day)
            if day == 0 or day > (clock['day'] if clock else offer['day']):
                raise ValueError('Booking is closed or the simulation date would rewind')
            limit = max_release if max_release is not None else clock['risk_limit'] if clock else offer['quantity']
            status = self._status(c, offer['flight_id'], day, limit)
            if status['currently_bookable'] < 1:
                raise ValueError('Current normal-demand protection leaves no bookable member seats')
            if c.execute('SELECT 1 FROM bookings WHERE flight_id=? AND customer_id=?', (offer['flight_id'], customer_id)).fetchone():
                raise ValueError('This customer already booked this flight')
            self._advance(c, offer['flight_id'], day, int(limit))
            id = str(uuid.uuid4())
            total = offer['base_fare'] + offer['fees']
            c.execute('UPDATE offers SET remaining=remaining-1 WHERE id=? AND remaining>0', (offer_id,))
            c.execute('INSERT INTO bookings VALUES(?,?,?,?,?,?)', (id, offer_id, offer['flight_id'], customer_id, total, time.time()))
            return {'booking': dict(c.execute('SELECT * FROM bookings WHERE id=?', (id,)).fetchone()),
                    'remaining': offer['remaining'] - 1, 'simulated': True}

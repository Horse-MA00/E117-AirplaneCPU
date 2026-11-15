"""Transactional three-round demo inventory; no real payments or tickets."""
from .errors import NotFound
import calendar
import math
import sqlite3
import time
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from .release_policy import RELEASE_DAYS, VERSION as RELEASE_VERSION, release_budget
from . import simulation_clock


MEMBERSHIP_MONTHS = 6
MEMBERSHIP_TIMEZONE = ZoneInfo('Asia/Hong_Kong')


def membership_expiry(created):
    """Six Hong Kong calendar months, preserving time and clamping month-end.

    This is a purchase-time calculation; previously stored expiries are never
    recalculated when a plan is read or an existing member signs in again.
    """
    start = datetime.fromtimestamp(created, MEMBERSHIP_TIMEZONE)
    month_index = start.year * 12 + start.month - 1 + MEMBERSHIP_MONTHS
    year, month = divmod(month_index, 12)
    month += 1
    day = min(start.day, calendar.monthrange(year, month)[1])
    return start.replace(year=year, month=month, day=day).timestamp()


class Store:
    def __init__(self, path, schedule_resolver=None):
        self.path = str(path)
        # Runtime supplies the catalogue resolver. No resolver keeps standalone
        # legacy fixtures/scripts compatible; persisted absolute clocks remain
        # absolute even when opened without a resolver.
        self.schedule_resolver = schedule_resolver
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as c:
            c.executescript('''
                CREATE TABLE IF NOT EXISTS offers(id TEXT PRIMARY KEY,flight_id TEXT,day INTEGER,quantity INTEGER,remaining INTEGER,base_fare REAL,fees REAL,created REAL,expires REAL);
                CREATE TABLE IF NOT EXISTS members(customer_id TEXT PRIMARY KEY,fee REAL,created REAL,expires REAL);
                CREATE TABLE IF NOT EXISTS bookings(id TEXT PRIMARY KEY,offer_id TEXT,flight_id TEXT,customer_id TEXT,total REAL,created REAL,UNIQUE(flight_id,customer_id));
                CREATE TABLE IF NOT EXISTS flight_clocks(flight_id TEXT PRIMARY KEY,day INTEGER,risk_limit INTEGER,cutoff REAL);
                CREATE TABLE IF NOT EXISTS membership_plan(id INTEGER PRIMARY KEY CHECK(id=1),fee REAL NOT NULL);
                INSERT OR IGNORE INTO membership_plan VALUES(1,399);
            ''')
            columns = {row['name'] for row in c.execute('PRAGMA table_info(offers)')}
            if 'release_version' not in columns:
                c.execute("ALTER TABLE offers ADD COLUMN release_version TEXT NOT NULL DEFAULT 'legacy-daily-demo'")
            if 'fee_breakdown' not in columns:
                c.execute("ALTER TABLE offers ADD COLUMN fee_breakdown TEXT")
            clock_columns = {row['name'] for row in c.execute('PRAGMA table_info(flight_clocks)')}
            for name, definition in (
                ('clock_version', "TEXT NOT NULL DEFAULT 'legacy-wall-clock-v0'"),
                ('departure_at', 'REAL'), ('simulation_as_of', 'REAL'),
                ('observed_through_day', 'INTEGER'),
            ):
                if name not in clock_columns:
                    c.execute(f'ALTER TABLE flight_clocks ADD COLUMN {name} {definition}')

    def set_offer_fee_breakdown(self, offer_id, breakdown):
        """Apply a sourced demo estimate only while the offer has no receipts."""
        import json
        from decimal import Decimal, ROUND_HALF_UP
        lines = breakdown.get('lines', [])
        if not lines or breakdown.get('currency') != 'HKD':
            raise ValueError('An HKD fee breakdown with lines is required')
        amounts = [Decimal(str(line['amount'])) for line in lines]
        if any(not a.is_finite() or a < 0 or a != a.quantize(Decimal('.01')) for a in amounts):
            raise ValueError('Fee amounts must be nonnegative finite cents')
        total = float(sum(amounts).quantize(Decimal('.01'), rounding=ROUND_HALF_UP))
        payload = json.dumps(breakdown, sort_keys=True)
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            offer = c.execute('SELECT * FROM offers WHERE id=?', (offer_id,)).fetchone()
            if not offer:
                raise ValueError('Offer not found')
            if offer['fee_breakdown'] == payload and offer['fees'] == total:
                return total
            if c.execute('SELECT 1 FROM bookings WHERE offer_id=?', (offer_id,)).fetchone():
                raise ValueError('Cannot reprice an offer with existing bookings')
            c.execute('UPDATE offers SET fees=?,fee_breakdown=? WHERE id=?', (total, payload, offer_id))
        return total

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

    def _time_context(self, c, flight, day, rows=None, clock=None):
        """Resolve simulation time without mutating the clock on a preview."""
        self._day(day)
        if rows is None:
            rows = c.execute('SELECT * FROM offers WHERE flight_id=?', (flight,)).fetchall()
        if clock is None:
            clock = c.execute('SELECT * FROM flight_clocks WHERE flight_id=?', (flight,)).fetchone()
        absolute = (clock and clock['clock_version'] == simulation_clock.VERSION) or (
            not clock and not rows and self.schedule_resolver is not None)
        if absolute:
            schedule = self.schedule_resolver(flight) if self.schedule_resolver else {
                'departure_at': clock['departure_at'], 'observed_through_day': clock['observed_through_day']}
            departure = simulation_clock.timestamp(schedule['departure_at'])
            if clock and departure != clock['departure_at']:
                raise ValueError('Flight departure changed; an existing simulation clock cannot be reinterpreted')
            observed = schedule['observed_through_day']
            simulation_clock.require_observed(day, observed)
            return {'clock_version': simulation_clock.VERSION, 'departure_at': departure,
                    'as_of': simulation_clock.as_of_timestamp(departure, day),
                    'cutoff': departure - simulation_clock.SALES_CUTOFF_SECONDS,
                    'observed_through_day': observed}
        # Existing offers/clocks are not relabelled with catalogue timestamps:
        # their stored entitlement expiry keeps its original wall-clock meaning.
        return {'clock_version': simulation_clock.LEGACY_VERSION, 'departure_at': None,
                'as_of': time.time(), 'cutoff': clock['cutoff'] if clock else None,
                'observed_through_day': None}

    @staticmethod
    def _time_metadata(context):
        absolute = context['clock_version'] == simulation_clock.VERSION
        return {'clock_version': context['clock_version'],
                'time_basis': 'flight_simulation' if absolute else 'legacy_wall_clock',
                'simulation_as_of': simulation_clock.iso_timestamp(context['as_of']) if absolute else None,
                'sales_cutoff_at': simulation_clock.iso_timestamp(context['cutoff']),
                'observed_through_day': context['observed_through_day'],
                'membership_time_basis': 'real_time'}

    def _offer_info(self, c, row):
        clock = c.execute('SELECT * FROM flight_clocks WHERE flight_id=?', (row['flight_id'],)).fetchone()
        day = clock['day'] if clock else row['day']
        context = self._time_context(c, row['flight_id'], day, clock=clock)
        return {**dict(row), 'sim_day': day, **self._time_metadata(context)}

    def _status(self, c, flight, day, max_release):
        self._day(day)
        rows = c.execute('SELECT * FROM offers WHERE flight_id=? ORDER BY day DESC,created', (flight,)).fetchall()
        clock = c.execute('SELECT * FROM flight_clocks WHERE flight_id=?', (flight,)).fetchone()
        context = self._time_context(c, flight, day, rows, clock)
        now = context['as_of']
        last_day = clock['day'] if clock else min((r['day'] for r in rows), default=28)
        sold = sum(r['quantity'] - r['remaining'] for r in rows)
        active = [r for r in rows if day > 0 and r['day'] >= day and r['expires'] > now]
        outstanding = sum(r['remaining'] for r in active)
        carry = sum(r['remaining'] for r in active if r['day'] > day)
        issued = any(r['day'] == day for r in rows)
        historical = bool(rows or clock) and day > last_day
        cutoff_passed = context['cutoff'] is not None and context['cutoff'] <= now
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
                'simulation_day': last_day, 'blocked_reason': reason, 'round_history': history,
                'historical_view': historical, 'sales_cutoff_passed': cutoff_passed,
                **self._time_metadata(context)}

    def release_status(self, flight, day, max_release):
        with self.connect() as c:
            return self._status(c, flight, day, max_release)

    def _advance(self, c, flight, day, risk_limit):
        clock = c.execute('SELECT * FROM flight_clocks WHERE flight_id=?', (flight,)).fetchone()
        if clock and day > clock['day']:
            raise ValueError('Cannot rewind the simulation after an issued round or booking')
        context = self._time_context(c, flight, day, clock=clock)
        cutoff = context['cutoff']
        if context['clock_version'] == simulation_clock.LEGACY_VERSION:
            cutoff = context['as_of'] + max(0, day * 86400 - 7200)
            if clock:
                cutoff = min(cutoff, clock['cutoff'])
            c.execute('UPDATE offers SET expires=MIN(expires,?) WHERE flight_id=?', (cutoff, flight))
        c.execute('''INSERT OR REPLACE INTO flight_clocks
            (flight_id,day,risk_limit,cutoff,clock_version,departure_at,simulation_as_of,observed_through_day)
            VALUES(?,?,?,?,?,?,?,?)''', (flight, day, risk_limit, cutoff, context['clock_version'],
                context['departure_at'], context['as_of'] if context['departure_at'] is not None else None,
                context['observed_through_day']))
        return cutoff

    def offers(self):
        with self.connect() as c:
            rows = c.execute('''SELECT o.* FROM offers o LEFT JOIN flight_clocks f ON f.flight_id=o.flight_id
                WHERE o.expires > CASE WHEN f.clock_version=? THEN f.simulation_as_of ELSE ? END
                ORDER BY o.created DESC''', (simulation_clock.VERSION, time.time())).fetchall()
            return [self._offer_info(c, row) for row in rows]

    def offer_info(self, offer_id):
        with self.connect() as c:
            row = c.execute('SELECT * FROM offers WHERE id=?', (offer_id,)).fetchone()
            if row is None:
                raise NotFound('Offer not found')
            return self._offer_info(c, row)

    def offer(self, flight, day, quantity, fare, fees, max_release):
        self._day(day)
        if day not in RELEASE_DAYS:
            raise ValueError('New quota is issued only at D28, D14 and D7')
        if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 1:
            raise ValueError('Quantity must be a positive integer')
        if any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) or x < 0 for x in (fare, fees, max_release)):
            raise ValueError('Prices and release limit must be finite and nonnegative')
        from .fare_policy import integer_price
        fare = integer_price(fare, 'Member base fare')
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
            return self._offer_info(c, c.execute('SELECT * FROM offers WHERE id=?', (id,)).fetchone())

    def plan(self, fee=None):
        if fee is not None and (isinstance(fee, bool) or not isinstance(fee, (int, float)) or not math.isfinite(fee) or not 0 <= fee <= 5000):
            raise ValueError('Membership fee must be between HKD 0 and 5000')
        from .fare_policy import integer_price
        if fee is not None:
            fee = integer_price(fee, 'Membership fee', 0, 5000)
        now = time.time()
        with self.connect() as c:
            if fee is not None:
                c.execute('UPDATE membership_plan SET fee=? WHERE id=1', (fee,))
            return {'name': 'UOption Fly Pass', 'fee': c.execute('SELECT fee FROM membership_plan WHERE id=1').fetchone()['fee'],
                    'term_months': MEMBERSHIP_MONTHS, 'term_label': '6 months',
                    # Compatibility estimate for older clients; the purchased
                    # expiry is determined by calendar months, not this count.
                    'term_days': round((membership_expiry(now) - now) / 86400),
                    'personal_nontransferable': True}

    def join_plan(self, customer_id, expected_fee=None):
        """Member-facing signup takes the price from the stored plan atomically."""
        now = time.time()
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            existing = c.execute('SELECT * FROM members WHERE customer_id=?', (customer_id,)).fetchone()
            if existing:
                if existing['expires'] <= now:
                    raise ValueError('Membership expired; renewal is not implemented in this demo')
                return dict(existing)
            fee = c.execute('SELECT fee FROM membership_plan WHERE id=1').fetchone()['fee']
            if expected_fee is not None and expected_fee != fee:
                raise ValueError('The membership price changed. Refresh and review the current fee before joining.')
            c.execute('INSERT INTO members VALUES(?,?,?,?)', (customer_id, fee, now, membership_expiry(now)))
            return dict(c.execute('SELECT * FROM members WHERE customer_id=?', (customer_id,)).fetchone())

    def account(self, customer_id):
        with self.connect() as c:
            member = c.execute('SELECT * FROM members WHERE customer_id=?', (customer_id,)).fetchone()
            membership = {**dict(member), 'active': member['expires'] > time.time()} if member else None
            bookings = [dict(row) for row in c.execute('''SELECT b.*,o.base_fare,o.fees AS mandatory_fees,o.fee_breakdown
                FROM bookings b JOIN offers o ON o.id=b.offer_id WHERE b.customer_id=? ORDER BY b.created DESC''', (customer_id,))]
            return {'customer_id': customer_id, 'membership': membership, 'bookings': bookings, 'simulated': True}

    def book(self, offer_id, customer_id, day=None, max_release=None, expected_total=None):
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            member = c.execute('SELECT * FROM members WHERE customer_id=? AND expires>?', (customer_id, time.time())).fetchone()
            if not member:
                raise ValueError('An active demo membership is required')
            offer = c.execute('SELECT * FROM offers WHERE id=?', (offer_id,)).fetchone()
            if not offer or offer['remaining'] < 1:
                raise ValueError('Offer unavailable or sold out')
            if expected_total is not None and expected_total != round(offer['base_fare'] + offer['fees'], 2):
                raise ValueError('The flight price changed. Refresh and review the current total before booking.')
            clock = c.execute('SELECT * FROM flight_clocks WHERE flight_id=?', (offer['flight_id'],)).fetchone()
            day = day if day is not None else clock['day'] if clock else offer['day']
            self._day(day)
            context = self._time_context(c, offer['flight_id'], day, clock=clock)
            if offer['expires'] <= context['as_of']:
                raise ValueError('Offer unavailable or sold out')
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
            total = round(offer['base_fare'] + offer['fees'], 2)
            c.execute('UPDATE offers SET remaining=remaining-1 WHERE id=? AND remaining>0', (offer_id,))
            c.execute('INSERT INTO bookings VALUES(?,?,?,?,?,?)', (id, offer_id, offer['flight_id'], customer_id, total, time.time()))
            return {'booking': dict(c.execute('SELECT * FROM bookings WHERE id=?', (id,)).fetchone()),
                    'remaining': offer['remaining'] - 1, 'simulated': True}

"""Calendar-based membership terms without repricing existing purchases."""
from datetime import datetime
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backend.store import Store, MEMBERSHIP_TIMEZONE, membership_expiry


def stamp(value):
    return datetime.fromisoformat(value).replace(tzinfo=MEMBERSHIP_TIMEZONE).timestamp()


class MembershipTermTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(Path(self.temp.name) / 'members.sqlite3')

    def test_calendar_month_end_leap_year_and_local_clock(self):
        cases = [
            ('2026-11-15T00:45:12.125000', '2027-05-15T00:45:12.125000'),
            ('2026-08-31T22:30:00', '2027-02-28T22:30:00'),
            ('2027-08-31T22:30:00', '2028-02-29T22:30:00'),
            ('2028-02-29T09:00:00', '2028-08-29T09:00:00'),
            ('2026-03-31T00:15:00', '2026-09-30T00:15:00'),
        ]
        for start, expected in cases:
            with self.subTest(start=start):
                self.assertEqual(membership_expiry(stamp(start)), stamp(expected))

    def test_plan_and_new_purchase_use_six_months(self):
        start = stamp('2026-11-15T00:45:12')
        with patch('backend.store.time.time', return_value=start):
            plan = self.store.plan()
            member = self.store.join_plan('new-member', expected_fee=399)
        self.assertEqual(plan['fee'], 399)
        self.assertEqual(plan['term_months'], 6)
        self.assertEqual(plan['term_label'], '6 months')
        self.assertEqual(plan['term_days'], 181)
        self.assertEqual(member['created'], start)
        self.assertEqual(member['expires'], stamp('2027-05-15T00:45:12'))
        self.assertEqual(member['fee'], 399)
        with patch('backend.store.time.time', return_value=start + 30 * 86400):
            self.assertEqual(self.store.join_plan('new-member', expected_fee=999), member)

    def test_existing_purchase_and_admin_fee_survive_reload(self):
        start = stamp('2026-11-15T10:00:00')
        old_expiry = start + 365 * 86400
        with self.store.connect() as db:
            db.execute('INSERT INTO members VALUES(?,?,?,?)', ('old-member', 299, start, old_expiry))
        self.store.plan(599)
        reloaded = Store(self.store.path)
        with patch('backend.store.time.time', return_value=start + 1):
            old = reloaded.join_plan('old-member')
            new = reloaded.join_plan('new-member', expected_fee=599)
        self.assertEqual(old, {'customer_id': 'old-member', 'fee': 299, 'created': start, 'expires': old_expiry})
        self.assertEqual(reloaded.plan()['fee'], 599)
        self.assertEqual(new['fee'], 599)
        self.assertEqual(new['expires'], membership_expiry(start + 1))

    def test_expiry_is_exclusive_and_does_not_extend_on_reload(self):
        start = stamp('2027-08-31T23:59:59')
        with patch('backend.store.time.time', return_value=start):
            member = self.store.join_plan('boundary-member')
        with patch('backend.store.time.time', return_value=member['expires'] - 1):
            self.assertTrue(self.store.account('boundary-member')['membership']['active'])
        reloaded = Store(self.store.path)
        with patch('backend.store.time.time', return_value=member['expires']):
            self.assertFalse(reloaded.account('boundary-member')['membership']['active'])
            with self.assertRaisesRegex(ValueError, 'expired'):
                reloaded.join_plan('boundary-member')


if __name__ == '__main__':
    unittest.main()

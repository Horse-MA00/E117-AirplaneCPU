import hashlib
import http.client
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from backend import demo_auth, server
from backend.store import Store


class DemoAuthTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.store = Store(Path(temp.name) / 'demo.sqlite3')

    def login(self, email='member@uoption.test', cookie=''):
        return demo_auth.login(self.store, {'email': email, 'password': 'FlyPass399!'}, cookie)

    def test_paid_login_seeds_once_and_session_contains_no_password(self):
        first, cookie = self.login()
        self.assertTrue(first['account']['membership']['active'])
        self.assertEqual(first['account']['membership']['fee'], 399)
        second, new_cookie = self.login(cookie=cookie)
        self.assertEqual(second['account']['membership'], first['account']['membership'])
        self.assertNotEqual(cookie, new_cookie)
        self.assertFalse(demo_auth.current(self.store, cookie)['authenticated'])
        self.assertTrue(demo_auth.current(Store(self.store.path), new_cookie)['authenticated'])
        self.assertNotIn('FlyPass399!', json.dumps(first) + cookie)
        for attr in ('HttpOnly', 'SameSite=Lax', 'Max-Age=86400', 'Path=/'):
            self.assertIn(attr, cookie)
        token = new_cookie.split(';')[0].split('=', 1)[1]
        with self.store.connect() as connection:
            rows = connection.execute('SELECT * FROM demo_sessions').fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['token_hash'], hashlib.sha256(token.encode()).hexdigest())
        self.assertLessEqual(rows[0]['expires'], time.time() + 86400)

    def test_guest_purchase_and_membership_expiry_survive_login(self):
        guest, cookie = self.login('guest@uoption.test')
        self.assertIsNone(guest['account']['membership'])
        joined = self.store.join_plan('demo-guest', 399)
        demo_auth.logout(self.store, cookie)
        later, _ = self.login('guest@uoption.test')
        self.assertEqual(later['account']['membership']['created'], joined['created'])
        self.assertTrue(later['account']['membership']['active'])
        self.login()
        with self.store.connect() as connection:
            connection.execute('UPDATE members SET expires=1 WHERE customer_id=?', ('demo-member',))
        expired, _ = self.login()
        self.assertFalse(expired['account']['membership']['active'])
        self.assertEqual(expired['account']['membership']['expires'], 1)

    def test_invalid_credentials_do_not_create_membership(self):
        for credentials in ({}, {'email': 'member@uoption.test', 'password': 'wrong'},
                            {'email': 'other@uoption.test', 'password': 'FlyPass399!'},
                            {'email': [], 'password': None}):
            with self.assertRaises(demo_auth.AuthError):
                demo_auth.login(self.store, credentials)
        self.assertIsNone(self.store.account('demo-member')['membership'])

    def test_logout_and_expiry_revoke_sessions(self):
        _, cookie = self.login()
        response, cleared = demo_auth.logout(self.store, cookie)
        self.assertFalse(response['authenticated'])
        self.assertIn('Max-Age=0', cleared)
        self.assertFalse(demo_auth.current(self.store, cookie)['authenticated'])
        _, cookie = self.login()
        with self.store.connect() as connection:
            connection.execute('UPDATE demo_sessions SET expires=1')
        self.assertFalse(demo_auth.current(self.store, cookie)['authenticated'])
        for invalid in ('', 'uoption_demo_session=unknown', 'uoption_demo_session=' + 'a'*43):
            self.assertFalse(demo_auth.current(self.store, invalid)['authenticated'])


class DemoAuthHTTPTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.store = Store(Path(temp.name) / 'demo.sqlite3')
        store_patch = patch.object(server, 'store', return_value=self.store)
        store_patch.start()
        self.addCleanup(store_patch.stop)
        self.http = server.Server(('127.0.0.1', 0), server.Handler)
        thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(self.http.server_close)
        self.addCleanup(self.http.shutdown)

    def request(self, method, path, body=None, cookie=None, origin=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.http.server_port)
        headers = {'Content-Type': 'application/json'}
        if cookie:
            headers['Cookie'] = cookie.split(';')[0]
        if origin:
            headers['Origin'] = origin
        connection.request(method, path, json.dumps(body) if body is not None else None, headers)
        response = connection.getresponse()
        status, response_headers = response.status, dict(response.getheaders())
        payload = json.loads(response.read())
        connection.close()
        return status, payload, response_headers

    def login(self, email='member@uoption.test'):
        status, payload, headers = self.request('POST', '/api/member-portal/login',
                                               {'email': email, 'password': 'FlyPass399!'})
        self.assertEqual(status, 200)
        self.assertTrue(payload['authenticated'])
        return headers['Set-Cookie']

    def test_account_routes_enforce_cookie_identity(self):
        for customer_id in ('demo-member', 'demo-guest'):
            self.assertEqual(self.request('GET', f'/api/member-portal/accounts/{customer_id}')[0], 401)
            self.assertEqual(self.request('POST', '/api/member-portal/join', {'customer_id': customer_id})[0], 401)
        cookie = self.login()
        self.assertEqual(self.request('GET', '/api/member-portal/accounts/demo-member', cookie=cookie)[0], 200)
        self.assertEqual(self.request('GET', '/api/member-portal/accounts/demo-guest', cookie=cookie)[0], 403)
        for path in ('join', 'book'):
            self.assertEqual(self.request('POST', '/api/member-portal/' + path,
                                          {'customer_id': 'demo-guest'}, cookie=cookie)[0], 403)
        self.assertEqual(self.request('GET', '/api/member-portal/accounts/legacy-tool')[0], 200)

    def test_http_guest_join_session_and_logout(self):
        cookie = self.login('guest@uoption.test')
        status, payload, _ = self.request('GET', '/api/member-portal/session', cookie=cookie)
        self.assertEqual(status, 200)
        self.assertIsNone(payload['account']['membership'])
        status, joined, _ = self.request('POST', '/api/member-portal/join',
                                         {'customer_id': 'demo-guest', 'expected_fee': 399}, cookie=cookie)
        self.assertEqual(status, 200)
        self.assertEqual(joined['member']['fee'], 399)
        self.assertTrue(self.request('GET', '/api/member-portal/session', cookie=cookie)[1]['account']['membership']['active'])
        status, payload, headers = self.request('POST', '/api/member-portal/logout', {}, cookie=cookie)
        self.assertEqual(status, 200)
        self.assertIn('Max-Age=0', headers['Set-Cookie'])
        self.assertFalse(self.request('GET', '/api/member-portal/session', cookie=cookie)[1]['authenticated'])
        new_cookie = self.login('guest@uoption.test')
        self.assertTrue(self.request('GET', '/api/member-portal/session', cookie=new_cookie)[1]['account']['membership']['active'])

    def test_member_booking_is_owned_and_guest_requires_membership(self):
        offer = self.store.offer('SYN-TEST', 28, 2, 99, 250, 2)
        body = {'customer_id': 'demo-guest', 'offer_id': offer['id'], 'expected_total': 349}
        guest_cookie = self.login('guest@uoption.test')
        with patch.object(server, 'forecast_for', return_value={'releasable_seats': 2}):
            status, payload, _ = self.request('POST', '/api/member-portal/book', body, cookie=guest_cookie)
            self.assertEqual(status, 400)
            self.assertIn('active demo membership', payload['error'])
            member_cookie = self.login()
            body['customer_id'] = 'demo-member'
            status, payload, _ = self.request('POST', '/api/member-portal/book', body, cookie=member_cookie)
            self.assertEqual(status, 200)
            self.assertEqual(payload['booking']['customer_id'], 'demo-member')
        self.assertEqual(len(self.store.account('demo-member')['bookings']), 1)
        self.assertEqual(len(self.store.account('demo-guest')['bookings']), 0)
        with self.store.connect() as connection:
            connection.execute('UPDATE demo_sessions SET expires=1')
        self.assertEqual(self.request('GET', '/api/member-portal/accounts/demo-member', cookie=member_cookie)[0], 401)

    def test_invalid_login_and_cross_origin_requests_are_rejected(self):
        credentials = {'email': 'member@uoption.test', 'password': 'wrong'}
        self.assertEqual(self.request('POST', '/api/member-portal/login', credentials)[0], 401)
        credentials['password'] = 'FlyPass399!'
        for path in ('login', 'logout'):
            self.assertEqual(self.request('POST', '/api/member-portal/' + path, credentials,
                                          origin='https://other.example')[0], 403)
        self.assertIsNone(self.store.account('demo-member')['membership'])


if __name__ == '__main__':
    unittest.main()

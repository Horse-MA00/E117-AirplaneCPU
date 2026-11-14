"""HTTP contract under the container's wildcard bind and local host publishing."""
import json
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

from backend import server
from backend.store import Store


class ContainerHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.mock = patch.object(server, '_store', Store(Path(self.temp.name)/'test.db'))
        self.mock.start()
        self.addCleanup(self.mock.stop)
        self.http = server.ThreadingHTTPServer(('0.0.0.0', 0), server.Handler)
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop)
        self.base = f'http://127.0.0.1:{self.http.server_port}'

    def stop(self):
        self.http.shutdown()
        self.http.server_close()
        self.thread.join(timeout=5)

    def request(self, path, body=None, headers=None):
        request = urllib.request.Request(self.base+path,
            data=None if body is None else json.dumps(body).encode(),
            headers={'Content-Type': 'application/json', **(headers or {})})
        return urllib.request.urlopen(request, timeout=5)

    def test_health_and_both_sites_on_wildcard_listener(self):
        with self.request('/api/health') as response:
            self.assertEqual(json.load(response), {'status': 'ok'})
        for path in ('/admin', '/members', '/adaptive-pricing'):
            with self.request(path) as response:
                self.assertEqual(response.status, 200)
                self.assertTrue(response.read())

    def test_same_origin_writes_and_rejection_of_foreign_origin_or_host(self):
        with self.request('/api/member-portal/plan', {'membership_fee': 499},
                          {'Origin': self.base}) as response:
            self.assertEqual(json.load(response)['membership']['fee'], 499)
        for headers in ({'Origin': 'https://example.invalid'}, {'Host': 'example.invalid'}):
            with self.assertRaises(urllib.error.HTTPError) as error:
                self.request('/api/member-portal/plan', {'membership_fee': 0}, headers)
            self.assertEqual(error.exception.code, 403)
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.request('/api/health', headers={'Host': 'example.invalid'})
        self.assertEqual(error.exception.code, 403)


if __name__ == '__main__':
    unittest.main()

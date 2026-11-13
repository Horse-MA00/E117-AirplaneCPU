import gzip
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backend.server import Handler


class AuditExportTests(unittest.TestCase):
    def test_live_export_omits_a_partially_appended_jsonl_record(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary) / 'market-example'
            folder.mkdir()
            (folder / 'events.jsonl').write_bytes(b'{"event":"complete"}\n{"event":"pending')
            handler = Handler.__new__(Handler)
            handler.headers = {'Host': '127.0.0.1:8000'}
            handler.path = '/api/agents/runs/market-example/export'
            handler.wfile = io.BytesIO()
            headers = []
            handler.send_response_headers = lambda *args, **kwargs: headers.append((args, kwargs))
            with patch('backend.server.audit.BASE', Path(temporary)):
                handler.do_GET()
            self.assertEqual(gzip.decompress(handler.wfile.getvalue()), b'{"event":"complete"}\n')
            self.assertEqual(headers[0][0], (200, 'application/gzip', None))
            self.assertEqual(headers[0][1]['filename'], 'market-example.jsonl.gz')
            self.assertTrue(handler.close_connection)


if __name__ == '__main__':
    unittest.main()

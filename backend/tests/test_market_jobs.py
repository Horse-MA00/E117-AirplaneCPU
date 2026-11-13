import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from backend import market_jobs


class MarketJobBoundsTests(unittest.TestCase):
    def test_spend_and_policy_bounds_before_start(self):
        for body in ({'max_calls': 101}, {'max_calls': True}, {'seed': -1},
                     {'member_fare': float('nan')}, {'release_fraction': 2},
                     {'open_day': 29}, {'mode': 'unknown'}):
            with self.subTest(body=body), self.assertRaises(ValueError):
                market_jobs.start(body)

    def test_private_path_traversal_rejected(self):
        for name in ('../.env.local', '/tmp', '..', 'a/b', ''):
            with self.subTest(name=name), self.assertRaises(ValueError):
                market_jobs.read(name)

    def test_stopped_process_is_not_reported_running(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(market_jobs, 'BASE', Path(temporary)):
            folder = Path(temporary) / 'web-test'
            folder.mkdir()
            market_jobs._save(folder/'job.json', {'run_id': 'web-test', 'status': 'running'})
            self.assertEqual(market_jobs.read('web-test')['status'], 'interrupted')


if __name__ == '__main__':
    unittest.main()

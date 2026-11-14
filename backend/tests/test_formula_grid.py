"""Mathematical track: closed-form P* estimate, then a 9-point simulated fine grid."""
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from backend import optimization as engine
from backend import optimization_store as store
from backend.fare_estimate import GRID_POINTS, estimate, fine_grid


# These tests pin flights, fares and expectations from the frozen legacy catalogue.
_legacy_dataset = None


def setUpModule():
    global _legacy_dataset
    from backend import data as _data
    _legacy_dataset = _data.use_dataset('legacy')
    _legacy_dataset.__enter__()


def tearDownModule():
    _legacy_dataset.__exit__(None, None, None)

FLIGHT = 'DEMO-ISG-HKG-20270515'


class FineGrid(unittest.TestCase):
    def test_grid_starts_at_p_star_stays_in_bounds_and_is_unique(self):
        for p_star, low, high in ((100, 0, 220), (3, 0, 220), (220, 0, 220), (0, 0, 5)):
            grid = fine_grid(p_star, low, high)
            self.assertEqual(grid[0], p_star)
            self.assertEqual(len(grid), min(GRID_POINTS, high-low+1))
            self.assertEqual(len(set(grid)), len(grid))
            self.assertTrue(all(isinstance(p, int) for p in grid))
            self.assertTrue(all(low <= p <= high for p in grid))

    def test_nearby_fare_cap_is_always_tested(self):
        self.assertIn(250, fine_grid(248, 0, 250))
        self.assertNotIn(250, fine_grid(100, 0, 250))


class FormulaEstimate(unittest.TestCase):
    def test_scores_every_fare_up_to_the_cap_quickly(self):
        cfg = engine.validate({'flight_id': FLIGHT, 'forecast_day': 28})
        started = time.perf_counter()
        result = estimate(cfg, engine._seeds(cfg))
        self.assertLess(time.perf_counter() - started, 2)
        self.assertEqual(result['cap'], cfg['scope']['member_fare_cap'])
        self.assertEqual(result['prices_scored'], int(result['cap']) + 1)
        self.assertTrue(0 <= result['p_star'] <= result['cap'])
        self.assertEqual(result['grid'][0], result['p_star'])
        self.assertGreater(result['travellers_scored'], 0)

    def test_estimate_is_deterministic(self):
        cfg = engine.validate({'flight_id': FLIGHT, 'forecast_day': 28})
        self.assertEqual(estimate(cfg, engine._seeds(cfg)), estimate(cfg, engine._seeds(cfg)))


class OptimizerUsesFormulaGrid(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        patcher = patch.object(store, 'BASE', Path(self.temp.name)) if hasattr(store, 'BASE') else None
        if patcher:
            patcher.start()
            self.addCleanup(patcher.stop)

    def finish(self, run_id):
        for _ in range(600):
            report = engine.read(run_id)
            if report['status'] not in ('queued', 'running'):
                return report
            time.sleep(.1)
        self.fail('optimization did not finish')

    def test_math_run_simulates_p_star_then_the_fine_grid(self):
        run = engine.start({'flight_id': FLIGHT, 'forecast_day': 28, 'mode': 'math', 'rounds': 3})['run_id']
        report = self.finish(run)
        self.assertEqual(report['status'], 'completed', report['error'])
        formula = report['config']['formula_estimate']
        rows = report['tracks'][0]['rounds']
        # The user's round count applies to the live track only.
        self.assertEqual([r['member_fare'] for r in rows], formula['grid'])
        self.assertEqual(rows[0]['search_step'], 'formula_p_star')
        self.assertTrue(all(r['search_step'] == 'fine_grid' for r in rows[1:]))
        cap = report['config']['scope']['member_fare_cap']
        self.assertTrue(all(r['member_fare'] <= cap for r in rows))
        self.assertEqual(report['progress']['total_rounds'], len(formula['grid']))

    def test_live_track_keeps_the_existing_local_search(self):
        cfg = engine.validate({'flight_id': FLIGHT, 'forecast_day': 28, 'mode': 'live'})
        self.assertNotIn('math_search', cfg)
        self.assertEqual(engine.propose(cfg, [], 'live')['search_step'], 'initial_snapshot')


if __name__ == '__main__':
    unittest.main()

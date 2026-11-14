import copy
import csv
import gzip
import hashlib
import json
import math
from pathlib import Path
import tempfile
import unittest

from backend import data
from backend.nhpp import forecast
from simulation.generate import validate
from simulation.member_demo_generate import OUTPUT, SCENARIOS, generate
from simulation.network_generate import airport_catalog, DATES


class MemberDemoDataTests(unittest.TestCase):
    def test_catalog_and_full_trajectories(self):
        extra = [f for f in data.flights() if f.get('dataset') == 'member_demo_generated']
        expected = {(a, b, day) for airport in airport_catalog()
                    for a, b in (('HKG', airport['code']), (airport['code'], 'HKG')) for day in DATES}
        self.assertEqual({(f['origin'], f['destination'], f['departure_date']) for f in extra}, expected)
        self.assertEqual(len(extra), len(expected))
        self.assertEqual(validate(OUTPUT)['rows'], 222*181)
        self.assertEqual(len(data.flights()), 1549)
        self.assertEqual(len({f['flight_id'] for f in data.flights()}), 1549)
        for flight in extra:
            self.assertTrue(flight['flight_id'].startswith('DEMO-'))
            self.assertEqual(flight['scenario'], SCENARIOS[flight['demo_priority']]['name'])
            self.assertIn('demo_d28_releasable', flight)
            self.assertGreaterEqual(flight['demo_d28_releasable'], 0)
            rows = data.history(flight['flight_id'])
            self.assertEqual([r['days_to_departure'] for r in rows], list(range(180, -1, -1)))
            for row in rows:
                self.assertEqual(row['source_kind'], 'assumed_member_opportunity_demo')
                self.assertEqual(row['origin'], flight['origin'])
                self.assertEqual(row['destination'], flight['destination'])
                self.assertFalse({'scenario', 'demo_priority', 'beta', 'expected_demand', 'final_booked'} & row.keys())
                self.assertEqual(row['member_initial_base_fare'],
                                 round(.15*row['normal_base_fare'], 2) if row['normal_base_fare'] is not None else None)

    def test_true_poisson_requests_reconcile_to_observed_bookings(self):
        parameters = {p['flight_id']: p for p in json.loads((OUTPUT/'parameters.json').read_text())}
        expected_totals = {key: 0. for key in parameters}
        with gzip.open(OUTPUT/'truth.csv.gz', 'rt', newline='') as source:
            for truth in csv.DictReader(source):
                flight_id = truth['flight_id']
                start_day = int(truth['interval_start_day'])
                rows = data.history(flight_id)
                before, after = rows[180-start_day:182-start_day]
                self.assertEqual(after['gross_bookings'], min(int(truth['demand_requests']), before['available_seats']))
                self.assertEqual(int(truth['denied_demand']), int(truth['demand_requests'])-after['gross_bookings'])
                self.assertLessEqual(after['cancellations'], before['booked_seats'])
                expected_totals[flight_id] += float(truth['expected_demand'])
        for flight_id, total in expected_totals.items():
            self.assertAlmostEqual(total, parameters[flight_id]['expected_total_normal_requests'], places=7)

    def test_frozen_predictor_headroom_each_route_and_day(self):
        saved = json.loads((OUTPUT/'headroom_validation.json').read_text())
        expected_records = {(r['flight_id'], r['days_to_departure']): r for r in saved['records']}
        by_route = {}
        checked = 0
        for flight in (f for f in data.flights() if f.get('dataset') == 'member_demo_generated'):
            route = (flight['origin'], flight['destination'])
            for day in (28, 14, 7):
                history = [r for r in data.history(flight['flight_id']) if r['days_to_departure'] >= day]
                result = forecast(history, day)
                self.assertTrue(math.isfinite(result['expected_remaining_demand']))
                self.assertGreaterEqual(result['releasable_seats'], 0)
                self.assertLessEqual(result['releasable_seats'], result['available_seats'])
                self.assertEqual(result['releasable_seats'], expected_records[(flight['flight_id'], day)]['releasable_seats'])
                by_route.setdefault((route, day), []).append(result['releasable_seats'])
                checked += 1
        self.assertEqual(checked, 666)
        for day in (28, 14, 7):
            misses = {f'{route[0]}-{route[1]}': max(releases)
                      for (route, horizon), releases in by_route.items() if horizon == day and max(releases) < 25}
            self.assertEqual(misses, saved['by_day'][str(day)]['route_target_misses'])
        # The aim is broad opportunity coverage, not a license to alter an
        # unfavorable Poisson realization until every route passes a threshold.
        self.assertGreater(saved['by_day']['28']['routes_at_least_25'], 37)

    def test_future_data_cannot_change_a_demo_forecast(self):
        rows = copy.deepcopy(data.history('DEMO-HKG-FUK-20270515'))
        observed = forecast(rows, 28)
        for row in rows:
            if row['days_to_departure'] < 28:
                row.update(gross_bookings=900, cancellations=20, booked_seats=180,
                           normal_base_fare=1, available_seats=0)
        self.assertEqual(observed, forecast(rows, 28))

    def test_reproducible_generation_and_frozen_datasets(self):
        frozen = [path for folder in ('generated', 'validation_extended', 'network_generated')
                  for path in (data.ROOT/'simulation'/folder).rglob('*') if path.is_file()]
        frozen += [data.ROOT/'backend/nhpp.py', data.ROOT/'simulation/generate.py']
        before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in frozen}
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            a = generate(Path(first), catalog=airport_catalog()[:2])
            b = generate(Path(second), catalog=airport_catalog()[:2])
            self.assertEqual(a, b)
            self.assertEqual(validate(first)['rows'], 12*181)
        self.assertEqual(before, {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in frozen})
        manifest = json.loads((OUTPUT/'manifest.json').read_text())
        for name, expected in manifest['source_files'].items():
            self.assertEqual(hashlib.sha256((data.ROOT/name).read_bytes()).hexdigest(), expected)


if __name__ == '__main__':
    unittest.main()

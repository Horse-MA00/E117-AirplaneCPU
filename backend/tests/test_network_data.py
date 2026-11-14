import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from backend import data
from backend.nhpp import forecast
from simulation.generate import validate
from simulation.network_generate import airport_catalog, generate, OUTPUT, DATES


# These tests pin flights, fares and expectations from the frozen legacy catalogue.
_legacy_dataset = None


def setUpModule():
    global _legacy_dataset
    from backend import data as _data
    _legacy_dataset = _data.use_dataset('legacy')
    _legacy_dataset.__enter__()


def tearDownModule():
    _legacy_dataset.__exit__(None, None, None)


class NetworkDataTests(unittest.TestCase):
    def test_complete_catalog_has_each_direction_and_date(self):
        catalog = airport_catalog()
        extra = [flight for flight in data.flights() if flight.get('dataset') == 'network_generated']
        expected = {(origin, destination, day)
                    for airport in catalog
                    for origin, destination in (('HKG', airport['code']), (airport['code'], 'HKG'))
                    for day in DATES}
        actual = {(flight['origin'], flight['destination'], flight['departure_at'][:10]) for flight in extra}
        self.assertEqual(actual, expected)
        self.assertEqual(len(extra), len(expected))
        self.assertEqual(len({flight['flight_id'] for flight in data.flights()}), len(data.flights()))
        self.assertTrue(all(f['route_status'] == 'requested' for f in extra if f['catalog_airport'] == 'CTS'))
        self.assertTrue(all(f['route_status'] == 'announced' for f in extra if f['catalog_airport'] == 'HFE'))

    def test_histories_conserve_inventory_and_price_components(self):
        result = validate(OUTPUT)
        self.assertEqual(result['rows'], 222 * 181)
        self.assertEqual(result['flights'], 222)
        for flight in (f for f in data.flights() if f.get('dataset') == 'network_generated'):
            rows = data.history(flight['flight_id'])
            self.assertEqual([r['days_to_departure'] for r in rows], list(range(180, -1, -1)))
            for row in rows:
                self.assertEqual(row['origin'], flight['origin'])
                self.assertEqual(row['destination'], flight['destination'])
                self.assertEqual(row['departure_at'], flight['departure_at'])
                self.assertNotIn('expected_demand', row)
                self.assertNotIn('demand_requests', row)
                self.assertNotIn('scenario', row)
                if row['normal_base_fare'] is None:
                    self.assertIsNone(row['member_initial_base_fare'])
                else:
                    self.assertAlmostEqual(row['member_initial_base_fare'], round(.15 * row['normal_base_fare'], 2))
                    self.assertEqual(row['normal_base_fare'] + row['mandatory_fees'], row['normal_total_fare'])

    def test_catalog_totals_do_not_change_original_export_contract(self):
        manifest = data.manifest()
        self.assertEqual(manifest['rows'], 200000)
        self.assertEqual(manifest['flights'], 1105)
        self.assertEqual(manifest['catalog_rows'], 280364)
        self.assertEqual(manifest['catalog_flights'], len(data.flights()))
        self.assertEqual(sum(map(len, data.histories().values())), manifest['catalog_rows'])

    def test_future_network_observations_are_not_forecast_inputs(self):
        rows = copy.deepcopy(data.history('NET-HKG-FUK-20270515'))
        before = forecast(rows, 28)
        for row in rows:
            if row['days_to_departure'] < 28:
                row.update(gross_bookings=900, booked_seats=180, normal_base_fare=9000,
                           member_initial_base_fare=9000, available_seats=0)
        self.assertEqual(before, forecast(rows, 28))

    def test_date_and_direction_histories_are_not_duplicates(self):
        fingerprints = set()
        for origin, destination in (('HKG', 'FUK'), ('FUK', 'HKG')):
            for day in DATES:
                rows = data.history(f"NET-{origin}-{destination}-{day.replace('-', '')}")
                fingerprints.add(tuple((r['normal_base_fare'], r['available_seats']) for r in rows))
        self.assertEqual(len(fingerprints), 6)

    def test_generation_is_reproducible_and_preserves_frozen_inputs(self):
        frozen = [data.DATA/'snapshots.csv.gz', data.DATA/'truth.csv.gz',
                  data.DATA/'calibration_v2.json', data.ROOT/'simulation/generate.py']
        before = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in frozen}
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            a = generate(Path(first), catalog=airport_catalog()[:2], dates=DATES[:2])
            b = generate(Path(second), catalog=airport_catalog()[:2], dates=DATES[:2])
            self.assertEqual(a, b)
            self.assertEqual(a['files'], b['files'])
            self.assertEqual(validate(first)['rows'], 8*181)
        self.assertEqual(before, {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in frozen})
        manifest = json.loads((OUTPUT/'manifest.json').read_text())
        for name, expected in manifest['source_files'].items():
            self.assertEqual(hashlib.sha256((data.ROOT/name).read_bytes()).hexdigest(), expected)


if __name__ == '__main__':
    unittest.main()

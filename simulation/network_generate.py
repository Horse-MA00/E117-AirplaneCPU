"""Additive NHPP histories for the complete member-search airport catalog.

The frozen original datasets and generator are not modified. This dataset adds
three assumed departures in each direction between HKG and every catalog airport.
An airport's inclusion does not assert that an actual flight operates that day.
"""
from __future__ import annotations

import argparse
import csv
from datetime import date, datetime, timedelta
import hashlib
import json
from pathlib import Path
import re

from simulation.generate import FIELDS, TRUTH_FIELDS, HKT, _gzip_text, simulate_flight, validate

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'simulation/network_generated'
CATALOG = ROOT / 'frontend/members/airports.js'
DATES = ('2027-05-15', '2027-05-18', '2027-05-21')
VERSION = 'network-nhpp-supplement-v1'
SEED = 11720261114
NETWORK_FIELDS = FIELDS + ['member_initial_base_fare']


def airport_catalog():
    """Read the small, checked-in catalog; reject format drift rather than omit routes."""
    source = CATALOG.read_text(encoding='utf-8')
    rows = []
    for code, body in re.findall(r'^\s+([A-Z]{3}):\s*\{([^\n]+)\},?\s*$', source, re.MULTILINE):
        if re.search(r'catalog:\s*false', body) or code == 'HKG':
            continue
        values = dict(re.findall(r"(\w+):\s*'([^']*)'", body))
        if 'name' not in values or 'region' not in values:
            raise ValueError(f'Unrecognized catalog entry: {code}')
        rows.append({'code': code, **values, 'status': values.get('status', 'listed')})
    if len(rows) < 30 or len({row['code'] for row in rows}) != len(rows):
        raise ValueError('Airport catalog could not be parsed completely')
    return rows


def network_flight(airport, ordinal, inbound, departure_date, date_index, seed=SEED):
    # Distinct route, direction and date seeds produce different observed demand
    # and fare curves, while retaining the existing audited NHPP observation layer.
    source_index = 40000 + ordinal * len(DATES) * 2 + int(inbound) * len(DATES) + date_index
    generated = simulate_flight(source_index, seed)
    origin, destination = (airport['code'], 'HKG') if inbound else ('HKG', airport['code'])
    departure = datetime.combine(date.fromisoformat(departure_date), datetime.min.time(), HKT)
    departure += timedelta(hours=8 + (ordinal % 4) * 3 + int(inbound))
    old_departure = datetime.fromisoformat(generated['summary']['departure_at'])
    offset = departure - old_departure
    flight_id = f"NET-{origin}-{destination}-{departure_date.replace('-', '')}"
    common = {'flight_id': flight_id, 'origin': origin, 'destination': destination,
              'departure_at': departure.isoformat(), 'source_kind': 'assumed_network_demo'}
    for row in generated['snapshots']:
        row.update(common)
        for name in ('snapshot_at', 'cutoff_at'):
            row[name] = (datetime.fromisoformat(row[name]) + offset).isoformat()
        base = row['normal_base_fare']
        row['member_initial_base_fare'] = round(.15 * base, 2) if base is not None else None
    for row in generated['truth']:
        row['flight_id'] = flight_id
    generated['summary'].update(common)
    generated['summary'].update({
        'dataset': 'network_generated', 'departure_date': departure_date,
        'route_status': airport['status'], 'route_note': airport.get('note', ''),
        'catalog_airport': airport['code'], 'catalog_airport_name': airport['name'],
        'catalog_region': airport['region'],
        'member_initial_base_fare_d28': generated['snapshots'][152]['member_initial_base_fare'],
    })
    return generated


def generate(output=OUTPUT, seed=SEED, catalog=None, dates=DATES):
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise ValueError('seed must be a non-negative integer')
    if not dates or len(dates) > len(DATES) or len(set(dates)) != len(dates):
        raise ValueError('Provide one to three distinct departure dates')
    for value in dates:
        date.fromisoformat(value)
    catalog = airport_catalog() if catalog is None else catalog
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    summaries = []
    with _gzip_text(output/'snapshots.csv.gz') as sf, _gzip_text(output/'truth.csv.gz') as tf:
        snapshots = csv.DictWriter(sf, fieldnames=NETWORK_FIELDS)
        truth = csv.DictWriter(tf, fieldnames=TRUTH_FIELDS)
        snapshots.writeheader(); truth.writeheader()
        for ordinal, airport in enumerate(catalog):
            for inbound in (False, True):
                for date_index, day in enumerate(dates):
                    result = network_flight(airport, ordinal, inbound, day, date_index, seed)
                    snapshots.writerows(result['snapshots']); truth.writerows(result['truth'])
                    summaries.append(result['summary'])
    (output/'flights.json').write_text(json.dumps(summaries, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    (output/'catalog.json').write_text(json.dumps(catalog, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    manifest = {
        'schema_version': '1.1', 'generator_version': VERSION, 'seed': seed,
        'rows': len(summaries)*181, 'flights': len(summaries),
        'directed_routes': len(catalog)*2, 'remote_airports': len(catalog),
        'departure_dates': list(dates), 'history_lengths': {'181': len(summaries)},
        'source_kind': 'assumed_network_demo', 'currency': 'HKD', 'timezone': 'Asia/Hong_Kong',
        'catalog_checked_at': '2026-11-14',
        'catalog_sources': ['https://www.hkexpress.com/en/destinations',
                            'https://www.hkexpress.com/zh/sitemap/flights-from-cities/page-1'],
        'member_initial_base_fare_formula': 'round(0.15 * observed normal_base_fare, 2); null when no open quote',
        'source_files': {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                         for path in (Path(__file__), ROOT/'simulation/generate.py', CATALOG)},
        'assumptions': [
            'All dates, departure times, seat capacities, price paths, occupancy and fees are simulated, not airline observations.',
            'Every selected airport receives an HKG outbound and inbound scenario on each sample date; this does not assert actual route or seasonal availability.',
            'CTS is retained as a user-requested, schedule-unconfirmed scenario; HFE retains its announced status.',
            'Independent route/direction/date seeds use the existing NHPP generator; no empirical route-specific elasticity or willingness-to-pay is claimed.',
            'All timestamps use a common Hong Kong simulation clock, including inbound scenarios; this is not an actual local-airport timetable.',
            'P0 is an initial synthetic member-base-fare hypothesis (15% of that snapshot normal base), not an optimized target or ground truth.',
            'Gross bookings and cancellations describe the previous completed interval; prices apply after the snapshot. Future truth is not a predictor feature.',
            'Original generated and validation datasets and NHPP calibration remain unchanged.',
        ],
        'files': {},
    }
    for name in ('snapshots.csv.gz', 'truth.csv.gz', 'flights.json', 'catalog.json'):
        path = output/name
        manifest['files'][name] = {'bytes': path.stat().st_size, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    (output/'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    parser.add_argument('--seed', type=int, default=SEED)
    parser.add_argument('--validate-only', action='store_true')
    args = parser.parse_args()
    if not args.validate_only:
        generate(args.output, args.seed)
    print(json.dumps(validate(args.output)))


if __name__ == '__main__':
    main()

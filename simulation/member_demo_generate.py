"""Add explicit member-opportunity NHPP examples without changing frozen data.

Two low normal-demand flights and one higher-demand control are sampled for each
directed catalog route. Parameters are fixed before any forecasting; generation
does not inspect a release quota, select a favorable seed or edit realized sales.
"""
from __future__ import annotations

import argparse
import csv
from datetime import date, datetime, timedelta
import gzip
import hashlib
import json
import math
from pathlib import Path
import platform
import statistics

import numpy as np

from simulation.generate import FIELDS, TRUTH_FIELDS, HKT, _gzip_text, _integral, validate
from simulation.network_generate import airport_catalog, CATALOG, DATES

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'simulation/member_demo_generated'
VERSION = 'member-opportunity-nhpp-v1'
SEED = 11720261115
SCENARIOS = (
    {'name': 'member_opportunity_low', 'target_ratio': (.35, .40), 'beta': (.000, .003)},
    {'name': 'member_opportunity_moderate', 'target_ratio': (.46, .55), 'beta': (.001, .006)},
    {'name': 'normal_demand_control', 'target_ratio': (.95, 1.20), 'beta': (.014, .024)},
)
DEMO_FIELDS = FIELDS + ['member_initial_base_fare']


def simulate_member_flight(airport, ordinal, inbound, departure_date, scenario_index, seed=SEED):
    """Sample one exogenous NHPP; capacity censoring/cancellation form observations."""
    scenario = SCENARIOS[scenario_index]
    generators = np.random.SeedSequence([seed, ordinal, int(inbound), scenario_index]).spawn(4)
    params, pricing, arrivals, cancellations_rng = [np.random.default_rng(s) for s in generators]
    origin, destination = (airport['code'], 'HKG') if inbound else ('HKG', airport['code'])
    departure = datetime.combine(date.fromisoformat(departure_date), datetime.min.time(), HKT)
    departure += timedelta(hours=8 + (ordinal % 4) * 3 + int(inbound))
    cutoff = departure - timedelta(hours=2)
    capacity = (180, 188, 230, 236)[ordinal % 4]
    flight_id = f"DEMO-{origin}-{destination}-{departure_date.replace('-', '')}"
    flight = {'flight_id': flight_id, 'origin': origin, 'destination': destination,
              'departure_at': departure.isoformat(), 'capacity': capacity}
    beta = float(params.uniform(*scenario['beta']))
    target_ratio = float(params.uniform(*scenario['target_ratio']))
    cancel_probability = float(params.uniform(.0003, .0009))
    # Route/direction/date pricing assumptions, never actual airline quotations.
    reference_base = 320 + (ordinal % 9)*60 + int(inbound)*20 + scenario_index*30
    mandatory = 250
    noise = pricing.normal(0, .025, 181)
    prices = []
    exposure_weights = []
    for position, day in enumerate(range(180, -1, -1)):
        factor = 1 + (.08 if day <= 28 else 0) + (.12 if day <= 7 else 0)
        if 40 <= day <= 47 or 15 <= day <= 18:
            factor *= .90
        base = max(100, int(round(reference_base * factor * math.exp(noise[position])/10)*10))
        prices.append(base)
        if day:
            exposure = 22/24 if day == 1 else 1.
            weight = _integral(beta, 180-day, 180-day+exposure)
            weight *= ((base+mandatory)/(reference_base+mandatory))**-.8
            exposure_weights.append(weight)
    # Conditional on this exogenous fare path, total unconstrained expected
    # normal requests equal the declared target. Realized bookings remain random.
    theta = capacity*target_ratio/sum(exposure_weights)
    snapshots, truth = [], []
    booked = previous_gross = previous_cancel = 0
    previous_exposure = 0.
    for position, day in enumerate(range(180, -1, -1)):
        base = prices[position]
        available = capacity-booked
        status = 'closed' if day == 0 else ('sold_out' if available == 0 else 'open')
        public_base = base if status == 'open' else None
        snapshots.append({
            **flight, 'snapshot_at': (departure-timedelta(days=day) if day else cutoff).isoformat(),
            'days_to_departure': day, 'booked_seats': booked, 'available_seats': available,
            'empty_rate': round(available/capacity, 8), 'normal_base_fare': public_base,
            'mandatory_fees': mandatory, 'normal_total_fare': base+mandatory if public_base is not None else None,
            'gross_bookings': previous_gross, 'cancellations': previous_cancel,
            'interval_days': previous_exposure, 'source_kind': 'assumed_member_opportunity_demo',
            'currency': 'HKD', 'cutoff_at': cutoff.isoformat(), 'quote_status': status,
            'member_initial_base_fare': round(.15*base, 2) if public_base is not None else None,
        })
        if day == 0:
            break
        exposure = 22/24 if day == 1 else 1.
        mean = theta*exposure_weights[position]
        requests = int(arrivals.poisson(mean))
        gross = min(requests, available)
        cancellations = int(cancellations_rng.binomial(booked, 1-(1-cancel_probability)**exposure))
        truth.append({
            'flight_id': flight_id, 'interval_start_day': day, 'interval_end_day': day-1,
            'beta': round(beta, 10), 'latent_scale': round(target_ratio, 10),
            'expected_demand': round(mean, 10), 'demand_requests': requests,
            'denied_demand': requests-gross, 'internal_base_fare': base, 'scenario': scenario['name'],
        })
        booked += gross-cancellations
        previous_gross, previous_cancel, previous_exposure = gross, cancellations, exposure
    at28 = snapshots[152]
    summary = {
        **flight, 'scenario': scenario['name'], 'demo_priority': scenario_index,
        'source_kind': 'assumed_member_opportunity_demo', 'dataset': 'member_demo_generated',
        'departure_date': departure_date, 'snapshot_count': 181, 'history_start_day': 180,
        'route_status': airport['status'], 'route_note': airport.get('note', ''),
        'catalog_airport': airport['code'], 'catalog_airport_name': airport['name'], 'catalog_region': airport['region'],
        'booked_d28': at28['booked_seats'], 'available_d28': at28['available_seats'],
        'empty_rate_d28': at28['empty_rate'], 'normal_base_fare_d28': at28['normal_base_fare'],
        'member_initial_base_fare_d28': at28['member_initial_base_fare'],
        'final_booked': booked, 'final_empty_rate': round((capacity-booked)/capacity, 8),
    }
    parameters = {'flight_id': flight_id, 'scenario': scenario['name'], 'beta': beta,
                  'target_normal_requests_per_capacity': target_ratio,
                  'expected_total_normal_requests': capacity*target_ratio,
                  'daily_cancel_probability': cancel_probability, 'theta': theta,
                  'reference_base_fare': reference_base, 'price_elasticity_assumption': .8}
    return {'snapshots': snapshots, 'truth': truth, 'summary': summary, 'parameters': parameters}


def generate(output=OUTPUT, seed=SEED, catalog=None, dates=DATES):
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise ValueError('seed must be a non-negative integer')
    if not dates or len(dates) > 3 or len(set(dates)) != len(dates):
        raise ValueError('Provide one to three distinct departure dates')
    for value in dates:
        date.fromisoformat(value)
    catalog = airport_catalog() if catalog is None else catalog
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    summaries, parameters = [], []
    with _gzip_text(output/'snapshots.csv.gz') as sf, _gzip_text(output/'truth.csv.gz') as tf:
        sw = csv.DictWriter(sf, fieldnames=DEMO_FIELDS)
        tw = csv.DictWriter(tf, fieldnames=TRUTH_FIELDS)
        sw.writeheader(); tw.writeheader()
        for ordinal, airport in enumerate(catalog):
            for inbound in (False, True):
                for scenario_index, day in enumerate(dates):
                    result = simulate_member_flight(airport, ordinal, inbound, day, scenario_index, seed)
                    sw.writerows(result['snapshots']); tw.writerows(result['truth'])
                    summaries.append(result['summary']); parameters.append(result['parameters'])
    for name, value in (('flights.json', summaries), ('parameters.json', parameters), ('catalog.json', catalog)):
        (output/name).write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    manifest = {
        'schema_version': '1.1', 'generator_version': VERSION, 'seed': seed,
        'python_version': platform.python_version(), 'numpy_version': np.__version__,
        'rows': len(summaries)*181, 'flights': len(summaries), 'directed_routes': len(catalog)*2,
        'remote_airports': len(catalog), 'departure_dates': list(dates),
        'history_lengths': {'181': len(summaries)}, 'source_kind': 'assumed_member_opportunity_demo',
        'currency': 'HKD', 'timezone': 'Asia/Hong_Kong', 'catalog_checked_at': '2026-11-14',
        'catalog_sources': ['https://www.hkexpress.com/en/destinations',
                            'https://www.hkexpress.com/zh/sitemap/flights-from-cities/page-1'],
        'member_initial_base_fare_formula': 'round(0.15 * observed normal_base_fare, 2); null when no open quote',
        'scenarios': list(SCENARIOS), 'scenario_is_hidden_provenance': True,
        'source_files': {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                         for path in (Path(__file__), ROOT/'simulation/generate.py', ROOT/'simulation/network_generate.py', CATALOG)},
        'assumptions': [
            'An explicit opportunity-demo cohort, not a representative sample of HK Express or observed low-demand routes.',
            'Two prior low-normal-demand scenarios and one higher-demand control per route. No forecasts, quotas, outcome filtering or reseeding enter generation.',
            'Conditional on sampled parameters and exogenous quotes, requests are independent NHPP increments. Bookings are capacity-censored; cancellations release seats at interval end.',
            'Target ratios constrain expected normal requests, not final realized occupancy. Random requests and cancellations are retained without post-hoc changes.',
            'Quotes, fees, capacity, timings, elasticity, cancellation and route/date demand assumptions are synthetic. All timestamps use a common Hong Kong simulation clock.',
            'CTS is schedule-unconfirmed and HFE announced; dated inclusion does not assert operating service.',
            'P0 is an initial 15% normal-base-fare hypothesis, not an optimized price or customer ground truth.',
            'Scenario, demo_priority, final outcomes, parameters.json and truth.csv.gz are provenance/evaluation only, never prediction features.',
            'Original generated, validation, network_generated and NHPP calibration files remain unchanged.',
        ],
        'files': {},
    }
    for name in ('snapshots.csv.gz', 'truth.csv.gz', 'flights.json', 'parameters.json', 'catalog.json'):
        path = output/name
        manifest['files'][name] = {'bytes': path.stat().st_size, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    (output/'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    return manifest


def validate_forecast_headroom(output=OUTPUT):
    """Audit every sampled path with frozen NHPP; report misses without filtering."""
    from backend.nhpp import forecast

    output = Path(output)
    summaries = {f['flight_id']: f for f in json.loads((output/'flights.json').read_text())}
    histories = {key: [] for key in summaries}
    integer_fields = {'days_to_departure', 'capacity', 'booked_seats', 'available_seats', 'gross_bookings', 'cancellations'}
    float_fields = {'empty_rate', 'normal_base_fare', 'mandatory_fees', 'normal_total_fare', 'interval_days', 'member_initial_base_fare'}
    with gzip.open(output/'snapshots.csv.gz', 'rt', newline='') as source:
        for row in csv.DictReader(source):
            for key in integer_fields:
                row[key] = int(row[key])
            for key in float_fields:
                row[key] = float(row[key]) if row[key] else None
            histories[row['flight_id']].append(row)
    records = []
    for flight_id, flight in summaries.items():
        for day in (28, 14, 7):
            result = forecast([r for r in histories[flight_id] if r['days_to_departure'] >= day], day)
            if not math.isfinite(result['expected_remaining_demand']) or not 0 <= result['releasable_seats'] <= result['available_seats']:
                raise ValueError(f'Invalid forecast bounds: {flight_id} D{day}')
            records.append({
                'flight_id': flight_id, 'origin': flight['origin'], 'destination': flight['destination'],
                'departure_date': flight['departure_date'], 'scenario': flight['scenario'],
                'demo_priority': flight['demo_priority'],
                **{key: result[key] for key in ('days_to_departure', 'capacity', 'booked_seats', 'available_seats',
                    'expected_remaining_demand', 'raw_protection_p90', 'protection_allowance', 'protection_p90', 'releasable_seats')},
            })
    by_day = {}
    for day in (28, 14, 7):
        selected = [r for r in records if r['days_to_departure'] == day]
        route_best = {}
        for row in selected:
            route = f"{row['origin']}-{row['destination']}"
            route_best[route] = max(route_best.get(route, 0), row['releasable_seats'])
        by_day[str(day)] = {
            'flights': len(selected), 'positive': sum(r['releasable_seats'] > 0 for r in selected),
            'at_least_25': sum(r['releasable_seats'] >= 25 for r in selected),
            'routes_at_least_25': sum(value >= 25 for value in route_best.values()),
            'route_target_misses': {key: value for key, value in route_best.items() if value < 25},
            'by_scenario': {scenario['name']: {
                'flights': sum(r['scenario'] == scenario['name'] for r in selected),
                'positive': sum(r['scenario'] == scenario['name'] and r['releasable_seats'] > 0 for r in selected),
                'median_releasable_seats': statistics.median(r['releasable_seats'] for r in selected if r['scenario'] == scenario['name']),
            } for scenario in SCENARIOS if any(r['scenario'] == scenario['name'] for r in selected)},
        }
    source_paths = (Path(__file__), ROOT/'backend/nhpp.py', ROOT/'simulation/generated/calibration_v3.json')
    report = {
        'dataset': 'member_demo_generated', 'forecast_seed': 117, 'checks': len(records),
        'directed_routes': len({(r['origin'], r['destination']) for r in records}),
        'bounded_and_finite': True, 'by_day': by_day,
        'source_files': {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in source_paths},
        'snapshots_sha256': hashlib.sha256((output/'snapshots.csv.gz').read_bytes()).hexdigest(),
        'interpretation': 'Raw NHPP risk ceilings before sold member seats, existing valid quota or round issuance. Not incremental new quota and not empirical airline coverage. All generated outcomes retained; target misses reported, never filtered.',
        'records': records,
    }
    (output/'headroom_validation.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    parser.add_argument('--seed', type=int, default=SEED)
    parser.add_argument('--validate-only', action='store_true')
    parser.add_argument('--forecast-check', action='store_true', help='Write a complete frozen-NHPP headroom audit; never filters data')
    args = parser.parse_args()
    if not args.validate_only:
        generate(args.output, args.seed)
    print(json.dumps(validate(args.output)))
    if args.forecast_check:
        report = validate_forecast_headroom(args.output)
        print(json.dumps({key: value for key, value in report.items() if key not in ('records', 'source_files')}))


if __name__ == '__main__':
    main()

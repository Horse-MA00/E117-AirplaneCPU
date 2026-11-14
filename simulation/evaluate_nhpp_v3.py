"""NHPP v3 calibration and one-time final comparison against frozen v2.

v3 is recalibrated on the existing calibration seed (never a final holdout).
Its final comparison uses a new, previously unopened generation seed; the v2
final and extended reports stay frozen and are not overwritten. Scenario and
latent demand remain scoring-only. Departure time is public schedule data and
is the only field added to the v2 whitelist (for the weekend/holiday prior).
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
import numpy as np
from simulation.generate import simulate_flight
from simulation.evaluate_nhpp_v2 import _onset, summarize, FORECAST_SEED, DAYS
from backend.nhpp_v2 import forecast as v2
from backend import nhpp
from backend.nhpp import forecast as v3, surge_alarm, SETTINGS, VERSION, CALIBRATION_FILE
from backend.release_policy import RELEASE_DAYS

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT/'simulation/generated'
SEEDS = {'calibration': 20261115, 'final': 20261117}
ALLOWED = ('flight_id', 'days_to_departure', 'capacity', 'booked_seats', 'available_seats', 'gross_bookings',
           'cancellations', 'interval_days', 'normal_total_fare', 'departure_at')


def _model_hash():
    return hashlib.sha256((ROOT/'backend/nhpp.py').read_bytes()).hexdigest()


def evaluate(seed, count, phase):
    v2_cfg = json.loads((OUTPUT/'calibration_v2.json').read_text())['comparison_allowances']['v2']
    records = []
    for i in range(count):
        flight = simulate_flight(i, seed)
        onset = _onset(flight)
        for d in DAYS:
            prefix = [r for r in flight['snapshots'] if r['days_to_departure'] >= d]
            public = [{k: r[k] for k in ALLOWED} for r in prefix]
            actual = sum(r['demand_requests'] for r in flight['truth'] if r['interval_start_day'] <= d)
            actual_empty = flight['snapshots'][-1]['available_seats']
            raw_v2 = v2(public, d, FORECAST_SEED, protection_allowance=0)['raw_protection_p90']
            outputs = {'v2': v2(public, d, FORECAST_SEED, protection_allowance=math.ceil(v2_cfg[str(d)]['relative']*max(10, raw_v2)))}
            # Calibration fits the raw quantile only; the final phase uses the
            # exact runtime path, including calibration_v3.json and the gate.
            outputs['v3'] = v3(public, d, FORECAST_SEED, protection_allowance=0) if phase == 'calibration' else v3(public, d, FORECAST_SEED)
            for name, p in outputs.items():
                available = p['available_seats']; q = p['releasable_seats']; raw = p['raw_protection_p90']
                displacement = max(0, actual-(available-q))-max(0, actual-available)
                significance = p['diagnostics'].get('release_significance', {})
                records.append({'generator_seed': seed, 'flight_id': flight['summary']['flight_id'], 'model': name, 'day': d,
                                'scenario_for_scoring': flight['summary']['scenario'],
                                'jump_state_for_scoring': ('observed' if onset and onset > d else 'future' if onset else 'none'),
                                'predicted_demand': p['expected_remaining_demand'], 'actual_demand': actual,
                                'demand_ae': abs(p['expected_remaining_demand']-actual), 'empty_ae': abs(p['expected_empty_seats']-actual_empty),
                                'raw_protection': raw, 'protection': p['protection_p90'], 'covered': actual <= p['protection_p90'],
                                'raw_covered': actual <= raw, 'release': q, 'displacement_if_all_released_sell': displacement,
                                'held_by_significance_threshold': bool(significance.get('held_by_threshold')),
                                'peak_departure': bool(p['diagnostics'].get('calendar', {}).get('peak')),
                                'mean_booked_band_width': float(np.mean([r['p90']-r['p10'] for r in p['forecast_curve']])),
                                'censored_fraction': p['diagnostics']['censored_fraction'], 'detected_jump': p['diagnostics']['possible_jump']})
    return records


def monitor_probe(seed, count):
    """First weekday-matched alarm between rounds, by scoring-only onset."""
    details = []
    between = [d for d in range(max(RELEASE_DAYS)-1, 0, -1) if d not in RELEASE_DAYS]
    for i in range(count):
        flight = simulate_flight(i, seed)
        onset = _onset(flight)
        public = [{k: r[k] for k in ALLOWED} for r in flight['snapshots']]
        first = next((d for d in between if surge_alarm([r for r in public if r['days_to_departure'] >= d], d)['alarm']), None)
        details.append({'flight_id': flight['summary']['flight_id'], 'scenario_for_scoring': flight['summary']['scenario'],
                        'onset_day_scoring_only': onset, 'first_alarm_day': first})
    surge = [r for r in details if r['scenario_for_scoring'] == 'surge' and r['onset_day_scoring_only'] and 14 < r['onset_day_scoring_only'] < 28]
    early = [r for r in surge if r['first_alarm_day'] is not None and 14 < r['first_alarm_day'] < r['onset_day_scoring_only']]
    steady = [r for r in details if r['scenario_for_scoring'] in ('low', 'typical', 'high', 'declining')]
    return {'between_round_days': between,
            'surge_onset_between_d28_and_d14': len(surge),
            'alarm_before_d14_fraction': round(len(early)/max(1, len(surge)), 4),
            'median_alarm_lead_over_d14_days': float(np.median([r['first_alarm_day']-14 for r in early])) if early else None,
            'steady_scenario_any_alarm_rate': round(sum(r['first_alarm_day'] is not None for r in steady)/max(1, len(steady)), 4),
            'details': details}


def run(phase, count=240):
    model_hash = _model_hash()
    calibration_path = ROOT/CALIBRATION_FILE
    artifact = OUTPUT/f'nhpp_v3_{phase}.json'
    if phase == 'final':
        cfg = json.loads(calibration_path.read_text())
        if cfg['forecast_code_sha256'] != model_hash:
            raise ValueError('Model changed after v3 calibration; recalibrate before opening a new final set')
        if artifact.exists():
            raise ValueError('v3 final report already exists; do not repeatedly inspect and retune this holdout')
    rows = evaluate(SEEDS[phase], count, phase)
    report = {'phase': phase, 'model_version': VERSION, 'generation_seed': SEEDS[phase], 'forecast_seed': FORECAST_SEED,
              'flights': count, 'horizons': DAYS, 'model_sha256': model_hash, 'settings': SETTINGS,
              'summary': summarize(rows), 'records': rows,
              'notes': ['v2 is the frozen backend/nhpp_v2.py with its frozen calibration; v3 is backend/nhpp.py.',
                        'Calibration reuses the v2 calibration seed. The final seed was unopened before this run and is used once.',
                        'Displacement assumes every released member seat sells; it is a capacity-risk diagnostic, not financial loss.',
                        'The synthetic generator has no weekday or holiday effect; the weekend prior adds conservatism here, it is not validated as a gain.']}
    if phase == 'calibration':
        guard = {}
        for day in DAYS:
            subset = [r for r in rows if r['model'] == 'v3' and r['day'] == day]
            margins = []
            for scenario in sorted({r['scenario_for_scoring'] for r in subset}):
                residual = sorted((r['actual_demand']-r['raw_protection'])/max(10, r['raw_protection'])
                                  for r in subset if r['scenario_for_scoring'] == scenario)
                margins.append(residual[min(len(residual), math.ceil((len(residual)+1)*.9))-1])
            guard[str(day)] = max(0., float(max(margins)))
        calibration_path.write_text(json.dumps({
            'version': 3, 'model_version': VERSION, 'relative_guard_by_horizon': guard,
            'generation_seed': SEEDS['calibration'], 'final_generation_seed_reserved': SEEDS['final'], 'flights': count,
            'target_coverage': .9, 'forecast_code_sha256': model_hash, 'settings': SETTINGS,
            'method': 'worst synthetic regime upper order statistic of relative residual; one global scale per horizon',
            'notes': ['Scoring labels calibrate one global guard shared by every runtime flight; no scenario label enters forecasting.',
                      'Guarded protection is not a probability P90. It trades release volume for robustness across these synthetic regimes.']},
            indent=2))
        report['chosen_relative_guard'] = guard
    else:
        report['monitor'] = monitor_probe(SEEDS[phase], count)
    artifact.write_text(json.dumps(report, indent=2))
    print(json.dumps({'phase': phase, 'summary': {k: v for k, v in report['summary'].items() if k.endswith('/all') or k.endswith('/surge')},
                      'guard': report.get('chosen_relative_guard'),
                      'monitor': {k: v for k, v in report.get('monitor', {}).items() if k != 'details'}}, indent=2))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('phase', choices=SEEDS)
    parser.add_argument('--count', type=int, default=240)
    args = parser.parse_args()
    run(args.phase, args.count)

"""Read and verify committed evaluation evidence without running an experiment.

The frozen evaluation is a required publication artifact, not a background job.
HTTP reads check its report, manifest and required-file presence. Publication
checks additionally hash every payload and recompute the recorded coverage.
"""
from collections import Counter
import csv
import gzip
import hashlib
import json
from pathlib import Path


EXTENDED = 'simulation/validation_extended'
SEEDS = (20261121, 20261122)
REQUIRED_FILES = {'report.json', 'forecast_records.jsonl.gz'} | {
    f'seed-{seed}/{name}' for seed in SEEDS
    for name in ('manifest.json', 'snapshots.csv.gz', 'truth.csv.gz', 'flights.json', 'sample.csv')
}


class EvidenceUnavailable(ValueError):
    def __init__(self, artifact, reason):
        self.artifact = artifact
        super().__init__(f'Evaluation evidence unavailable: {artifact}: {reason}. Restore the complete published repository; no evaluation job is pending.')


def _fail(artifact, reason):
    raise EvidenceUnavailable(artifact, reason)


def _bytes(root, name):
    try:
        return (root / name).read_bytes()
    except OSError:
        _fail(name, 'required file is missing or unreadable')


def _json(root, name):
    raw = _bytes(root, name)
    try:
        result = json.loads(raw)
    except (ValueError, UnicodeError):
        _fail(name, 'invalid JSON')
    if not isinstance(result, dict):
        _fail(name, 'expected a JSON object')
    return result


def _manifest(root):
    name = f'{EXTENDED}/manifest.json'
    manifest = _json(root, name)
    files = manifest.get('files')
    if manifest.get('source') != 'extended_frozen_model_validation' or not isinstance(files, dict) or set(files) != REQUIRED_FILES:
        _fail(name, 'required evaluation payload inventory does not match')
    for child in REQUIRED_FILES:
        if not (root / EXTENDED / child).is_file():
            _fail(f'{EXTENDED}/{child}', 'required file is missing')
    return manifest


def _checked_bytes(root, name, expected):
    raw = _bytes(root, name)
    if not isinstance(expected, dict) or len(raw) != expected.get('bytes') or hashlib.sha256(raw).hexdigest() != expected.get('sha256'):
        _fail(name, 'checksum or byte count does not match the frozen manifest')
    return raw


def read_evaluation(root, extended=False):
    """Return the original success payload; fail explicitly for missing evidence."""
    root = Path(root)
    name = f'{EXTENDED}/report.json' if extended else 'simulation/generated/nhpp_v2_final.json'
    if extended:
        manifest = _manifest(root)
        _checked_bytes(root, name, manifest['files']['report.json'])
    report = _json(root, name)
    if not isinstance(report.get('summary'), dict) or not report['summary']:
        _fail(name, 'evaluation summary is absent')
    if extended and (report.get('kind') != 'extended_frozen_model_validation' or report.get('evaluated_flights') != 1200 or report.get('scored_predictions') != 7200):
        _fail(name, 'frozen evaluation scope does not match')
    return report


def verify_extended(root):
    """Validate all frozen extended evidence, including counts behind README claims."""
    root = Path(root)
    manifest = _manifest(root)
    for child, expected in manifest['files'].items():
        _checked_bytes(root, f'{EXTENDED}/{child}', expected)
    report = read_evaluation(root, extended=True)
    if report.get('generation_seeds') != list(SEEDS) or report.get('additional_snapshot_rows') != 400000 or report.get('additional_histories') != 2210:
        _fail(f'{EXTENDED}/report.json', 'dataset scope does not match')
    if hashlib.sha256(_bytes(root, 'backend/nhpp.py')).hexdigest() != report.get('forecast_code_sha256'):
        _fail('backend/nhpp.py', 'frozen forecast source differs from the evaluated version')
    for seed in SEEDS:
        folder = f'{EXTENDED}/seed-{seed}'
        dataset = _json(root, folder + '/manifest.json')
        if dataset.get('seed') != seed or dataset.get('rows') != 200000 or dataset.get('flights') != 1105:
            _fail(folder + '/manifest.json', 'dataset counts or seed do not match')
        names = {'snapshots.csv.gz', 'truth.csv.gz', 'flights.json', 'sample.csv'}
        if set(dataset.get('files', {})) != names:
            _fail(folder + '/manifest.json', 'dataset inventory does not match')
        for name in names:
            if dataset['files'][name] != manifest['files'][f'seed-{seed}/{name}']:
                _fail(folder + '/' + name, 'dataset and publication manifests disagree')
        try:
            with gzip.open(root / folder / 'snapshots.csv.gz', 'rt', newline='') as handle:
                count = sum(1 for _ in csv.DictReader(handle))
        except (OSError, EOFError, UnicodeError, csv.Error):
            _fail(folder + '/snapshots.csv.gz', 'invalid compressed snapshot data')
        if count != 200000:
            _fail(folder + '/snapshots.csv.gz', 'snapshot row count does not match')
    records_name = f'{EXTENDED}/forecast_records.jsonl.gz'
    if manifest['files']['forecast_records.jsonl.gz']['sha256'] != report.get('records_sha256'):
        _fail(records_name, 'report and publication checksums disagree')
    try:
        with gzip.open(root / records_name, 'rt') as handle:
            records = [json.loads(line) for line in handle]
        identities = [(r['generator_seed'], r['flight_id'], r['model'], r['day']) for r in records]
        flights = Counter((r['generator_seed'], r['flight_id']) for r in records)
        valid_records = all(r['generator_seed'] in SEEDS and r['model'] in ('v1', 'v2') and r['day'] in (28, 14, 7)
                            and isinstance(r['covered'], bool) and isinstance(r['raw_covered'], bool) for r in records)
    except (OSError, EOFError, UnicodeError, ValueError, KeyError, TypeError):
        _fail(records_name, 'invalid prediction records')
    if not valid_records or len(records) != 7200 or len(set(identities)) != 7200 or len(flights) != 1200 or set(flights.values()) != {6}:
        _fail(records_name, 'expected 1,200 unique histories and 7,200 unique scored predictions')
    if Counter(seed for seed, _ in flights) != Counter({seed: 600 for seed in SEEDS}):
        _fail(records_name, 'expected 600 evaluated histories per seed')
    for key, summary in report['summary'].items():
        try:
            model, horizon, group = key.split('/')
            rows = [r for r in records if r['model'] == model and r['day'] == int(horizon[1:])
                    and (group == 'all' or r['scenario_for_scoring'] == group or
                         group in ('surge_future', 'surge_observed') and r['scenario_for_scoring'] == 'surge'
                         and r['jump_state_for_scoring'] == group.removeprefix('surge_'))]
            agrees = len(rows) == summary['n'] and len(rows) > 0 and all(
                round(sum(r[field] for r in rows) / len(rows), 4) == summary[metric]
                for field, metric in [('covered', 'coverage'), ('raw_covered', 'raw_coverage')])
        except (ValueError, KeyError, TypeError, AttributeError):
            agrees = False
        if not agrees:
            _fail(f'{EXTENDED}/report.json', f'{key} coverage disagrees with scored predictions')
    surge = [r for r in records if r['model'] == 'v2' and r['day'] == 28 and r['scenario_for_scoring'] == 'surge']
    covered = sum(r['covered'] for r in surge)
    if len(surge) != 200 or covered != 183:
        _fail(records_name, 'README D28 surge claim does not match 183 of 200 flights')
    return {'kind': report['kind'], 'evaluated_flights': len(flights), 'scored_predictions': len(records),
            'surge_d28': {'covered': covered, 'total': len(surge), 'coverage': covered / len(surge)},
            'verified_files': len(REQUIRED_FILES), 'additional_snapshot_rows': 400000}

"""More synthetic test data, with the v2 model and guards kept frozen."""
from __future__ import annotations
import gzip
import hashlib
import json
from pathlib import Path
from .generate import generate, validate
from .evaluate_nhpp_v2 import evaluate, summarize

ROOT = Path(__file__).resolve().parents[1]
SEEDS = (20261121, 20261122)


def run():
    output = ROOT / 'simulation/validation_extended'
    output.mkdir(exist_ok=True)
    report_path = output / 'report.json'
    if report_path.exists():
        raise ValueError('Frozen extended report already exists; do not overwrite evaluation evidence')
    calibration = json.loads((ROOT / 'simulation/generated/calibration_v2.json').read_text())
    model_hash = hashlib.sha256((ROOT / 'backend/nhpp.py').read_bytes()).hexdigest()
    if model_hash != calibration['forecast_code_sha256']:
        raise ValueError('Model differs from the frozen calibration')
    manifests, records = [], []
    for seed in SEEDS:
        folder = output / f'seed-{seed}'
        manifest = generate(rows=200_000, seed=seed, output=folder)
        manifests.append({'seed': seed, 'manifest': manifest, 'validation': validate(folder)})
        print(json.dumps({'phase': 'data', 'seed': seed, 'rows': manifest['rows']}), flush=True)
        rows = evaluate(seed, count=600, allowances=calibration['comparison_allowances'])
        records.extend(rows)
        print(json.dumps({'phase': 'evaluated', 'seed': seed, 'flights': 600}), flush=True)
    payload = ''.join(json.dumps(row, separators=(',', ':'))+'\n' for row in records).encode()
    (output / 'forecast_records.jsonl.gz').write_bytes(gzip.compress(payload, mtime=0))
    report = {'kind': 'extended_frozen_model_validation', 'generation_seeds': SEEDS,
              'additional_snapshot_rows': 400_000, 'additional_histories': sum(m['manifest']['flights'] for m in manifests),
              'evaluated_flights': 1200, 'horizons': [28, 14, 7], 'scored_predictions': len(records),
              'forecast_code_sha256': model_hash, 'calibration_seed': calibration['generation_seed'],
              'summary': summarize(records), 'datasets': manifests,
              'records_sha256': hashlib.sha256((output / 'forecast_records.jsonl.gz').read_bytes()).hexdigest(),
              'limitations': ['All additional data are synthetic from the same generator family, not airline observations.',
                             'Model and calibration were frozen before these seeds were opened; no tuning on this report.',
                             'Seed plus flight ID identifies a history; display IDs repeat across independent datasets.']}
    report_path.write_text(json.dumps(report, indent=2))
    print(json.dumps({'report': str(report_path), 'summary': {k:v for k,v in report['summary'].items() if k.endswith('/surge')}}), flush=True)


if __name__ == '__main__':
    run()

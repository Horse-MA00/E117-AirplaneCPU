"""Prespecified synthetic robustness runs for the public-feature paired engine.

No provider calls. Each price is confirmed on fresh people; this is a check of
the declared synthetic response family, not human price elasticity evidence.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend import adaptive_pricing as engine, adaptive_store, data

PROTOCOL = 'paired-public-feature-robustness-v1'
SEEDS = [20261121+1009*i for i in range(12)]


def run(seeds=None):
    seeds = SEEDS if seeds is None else seeds
    started = time.monotonic()
    cases = []
    with tempfile.TemporaryDirectory(prefix='e117-paired-benchmark-') as directory:
        # Reproduces the saved runs on legacy flight NET-HKG-KMQ-20270518.
        with patch.object(adaptive_store,'BASE',Path(directory)), data.use_dataset('legacy'):
            for seed in seeds:
                report = engine.start({'mode':'synthetic','flight_id':'NET-HKG-KMQ-20270518',
                    'forecast_day':28,'rounds':6,'customers':16,'validation_repeats':3,
                    'max_calls':0,'concurrency':4,'seed':seed},blocking=True)
                if report['status'] != 'completed':
                    raise RuntimeError(report.get('error'))
                cases.append({'seed':seed,'prices':[r['price'] for r in report['rounds']],
                    'selected_price':report['recommendation']['price'],
                    'retained_price':report['validation']['retained_price'],
                    'unique_search_people':sum(len(c['people']) for c in report['search_panels']),
                    'hypothesis_tests':[r['hypothesis_test'] for r in report['rounds']],
                    'validation':report['validation'],'provider_calls':report['counts']['provider_calls']})
    files = ['backend/adaptive_pricing.py','backend/member_response.py','llm_agent/weighted_population.py',
             'llm_agent/adaptive_customers.py','scripts/benchmark_paired_pricing.py']
    outcomes = Counter(c['validation']['adoption_result'] for c in cases)
    deltas = [c['validation']['decision_gain_vs_initial'] for c in cases]
    return {'protocol':PROTOCOL,'source':'synthetic_assumed_motivation_utility','synthetic':True,
            'seeds':seeds,'cases':cases,'provider_calls':0,'elapsed_seconds':round(time.monotonic()-started,3),
            'summary':{'outcomes':dict(outcomes),'mean_selected_revenue_delta_vs_initial':sum(deltas)/len(deltas),
                       'positive_selected_cases':sum(d>0 for d in deltas),'negative_selected_cases':sum(d<0 for d in deltas)},
            'source_hashes':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in files},
            'limitations':['One declared response generator and one ample-inventory flight; no real customer data.',
                           'Confirmation cohorts were not used for fitting or candidate selection.',
                           'Retained-price policy uses confirmation evidence; its realised estimates are not a new third independent test.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Refusing to overwrite an existing experiment')
    report = run()
    args.output.mkdir(parents=True)
    payload = json.dumps(report,indent=2,allow_nan=False).encode()
    (args.output/'report.json').write_bytes(payload)
    manifest = {'source':PROTOCOL,'synthetic':True,'provider_calls':0,
                'files':{'report.json':{'sha256':hashlib.sha256(payload).hexdigest(),'bytes':len(payload)}}}
    (args.output/'manifest.json').write_text(json.dumps(manifest,indent=2))
    print(json.dumps({'elapsed_seconds':report['elapsed_seconds'],**report['summary']}))


if __name__ == '__main__':
    main()

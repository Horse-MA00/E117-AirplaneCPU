"""Reproduce V1 undercoverage and test one window-length hypothesis at a time.

The already inspected v1 holdout is development data from this point onward.
No credentials or network access are used.
"""
import argparse
import json
from pathlib import Path
from backend.data import history
from simulation.baselines.nhpp_v1 import forecast as v1

ROOT = Path(__file__).resolve().parents[1]


def replay(minimal=False,model='v1'):
    from backend.nhpp_v2 import forecast as v2
    method=v1 if model=='v1' else v2
    report = json.loads((ROOT/'simulation/generated/nhpp_holdout.json').read_text())
    cases = [f for f in report['flights'] if f['scenario_for_scoring_only']=='surge']
    if minimal:
        cases = [f for f in cases if f['flight_id']=='SYN-00016']
    correct = 0
    for case in cases:
        rows = [r for r in history(case['flight_id']) if 28 <= r['days_to_departure'] <= 64]
        pred = method(rows,28,117,protection_allowance=16 if model=='v1' else None)
        correct += case['actual_latent_demand'] <= pred['protection_p90']
        if minimal:
            print(json.dumps({'flight':case['flight_id'],'history_rows':len(rows),
                              'protection':pred['protection_p90'],'actual':case['actual_latent_demand']}))
    print(f'{model} development surge coverage: {correct}/{len(cases)} = {correct/len(cases):.4f}')
    assert correct/len(cases)>=.8, 'Development regression: surge coverage below 80%'


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--minimal',action='store_true');p.add_argument('--model',choices=['v1','v2'],default='v1');args=p.parse_args()
    replay(args.minimal,args.model)

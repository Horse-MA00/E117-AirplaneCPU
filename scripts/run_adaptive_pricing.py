"""Run one bounded experiment and export synthetic evidence, never credentials."""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def configure_provider():
    from backend.oag import load_env
    load_env()
    # Optional second user-authorized account. This private ignored file is not
    # included in provenance, logs, exports or source control.
    path = ROOT/'data/private/adaptive-secondary.key'
    if path.is_file() and not os.environ.get('LLM_API_KEY_SECONDARY'):
        os.environ['LLM_API_KEY_SECONDARY'] = path.read_text().strip()


def export(run_id, output):
    from backend.adaptive_pricing import export_run
    from llm_agent.audit import sanitize
    payload = sanitize(export_run(run_id))
    if payload['report']['status'] != 'completed':
        raise ValueError('Only completed experiments may be exported as validation evidence')
    output = Path(output)
    if output.exists():
        raise ValueError('Refusing to overwrite historical experiment evidence')
    serialized = json.dumps(payload,ensure_ascii=False,allow_nan=False)
    if re.search(r'\bsk-[A-Za-z0-9]{16,}', serialized):
        raise ValueError('Potential credential in export; publication stopped')
    output.mkdir(parents=True)
    report = payload['report']
    (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    with (output/'audit.jsonl.gz').open('wb') as target:
        with gzip.GzipFile(filename='',fileobj=target,mode='wb',mtime=0) as stream:
            for event in payload['events']:
                stream.write((json.dumps(event,ensure_ascii=False)+'\n').encode())
    files = {p.name:{'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size}
             for p in output.iterdir() if p.is_file()}
    manifest = {'source':'adaptive_thompson_pricing','run_id':run_id,'synthetic':True,
        'audit_records':len(payload['events']),'counts':report['counts'],'files':files,
        'customer_source':report['config']['mode'],'weight_source':report['population']['source'],
        'holdout_frozen_before_validation':True}
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    return {'run_id':run_id,'output':str(output),'counts':report['counts'],'validation':report['validation']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    from llm_agent.weighted_population import DEFAULT_PROFILE, LEGACY_PROFILE
    parser.add_argument('--profile', choices=(DEFAULT_PROFILE, LEGACY_PROFILE), default=DEFAULT_PROFILE)
    parser.add_argument('--flight-id',default='NET-HKG-KMQ-20270518')
    parser.add_argument('--day',type=int,choices=(28,14,7),default=28)
    parser.add_argument('--mode',choices=('synthetic','live'),default='synthetic')
    parser.add_argument('--rounds',type=int,default=10)
    parser.add_argument('--customers',type=int,default=28)
    parser.add_argument('--concurrency',type=int,default=4)
    parser.add_argument('--max-calls',type=int,default=None)
    parser.add_argument('--validation-repeats',type=int,default=2)
    parser.add_argument('--seed',type=int,default=117)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--export-run-id')
    args = parser.parse_args()
    if args.mode == 'live' and args.max_calls is None:
        parser.error('--mode live requires an explicit --max-calls finite budget')
    if args.mode == 'live' or args.export_run_id:
        configure_provider()
    from backend.adaptive_pricing import start
    if args.export_run_id:
        if not args.output:
            parser.error('--export-run-id requires --output')
        print(json.dumps(export(args.export_run_id,args.output),ensure_ascii=False),flush=True)
        return
    config = {'flight_id':args.flight_id,'forecast_day':args.day,'mode':args.mode,'rounds':args.rounds,
              'customers':args.customers,'concurrency':args.concurrency,'max_calls':args.max_calls or 0,
              'validation_repeats':args.validation_repeats,'seed':args.seed,'profile':args.profile}
    report = start(config,blocking=True)
    summary = {k:report.get(k) for k in ('run_id','status','elapsed_seconds','error','counts','validation')}
    summary['prices'] = [r['price'] for r in report['rounds']]
    summary['selected_price'] = (report.get('recommendation') or {}).get('price')
    print(json.dumps(summary,ensure_ascii=False),flush=True)
    if report['status'] != 'completed':
        sys.exit(1)
    if args.output:
        print(json.dumps(export(report['run_id'],args.output),ensure_ascii=False),flush=True)


if __name__ == '__main__':
    main()

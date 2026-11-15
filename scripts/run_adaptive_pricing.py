"""Run one bounded experiment and export synthetic evidence, never credentials."""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def configure_provider():
    from backend.oag import load_env
    load_env()
    # Optional second user-authorized account. This private ignored file is not
    # included in provenance, logs, exports or source control.
    path = ROOT/'data/private/adaptive-secondary.key'
    if path.is_file() and not os.environ.get('LLM_API_KEY_SECONDARY'):
        os.environ['LLM_API_KEY_SECONDARY'] = path.read_text(encoding='utf-8').strip()


def export(run_id, output, *, include_failed=False):
    from backend.adaptive_pricing import events, read
    from llm_agent.audit import sanitize
    report = sanitize(read(run_id))
    terminal_failure = report['status'] in ('failed', 'interrupted')
    if report['status'] != 'completed' and not (include_failed and terminal_failure):
        raise ValueError('Only completed experiments may be exported as validation evidence')
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise ValueError('Refusing to overwrite historical experiment evidence')

    def safe_json(value, *, indent=None):
        serialized = json.dumps(sanitize(value),ensure_ascii=False,allow_nan=False,indent=indent)
        if re.search(r'\bsk-[A-Za-z0-9]{16,}', serialized):
            raise ValueError('Potential credential in export; publication stopped')
        return serialized

    # CLI evidence can exceed the HTTP inline-export ceiling. Fetch bounded
    # pages, retaining the HTTP guard and never holding the entire audit in RAM.
    serialized_report = safe_json(report, indent=2)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f'.{output.name}.export-',dir=output.parent))
    try:
        (temporary/'report.json').write_text(serialized_report,encoding='utf-8')
        count, offset, last_id = 0, 0, 0
        with (temporary/'audit.jsonl.gz').open('wb') as target:
            with gzip.GzipFile(filename='',fileobj=target,mode='wb',mtime=0) as stream:
                while True:
                    page = events(run_id, limit=100, offset=offset)['events']
                    if not page:
                        break
                    for event in page:
                        if event.get('run_id') != run_id or not isinstance(event.get('id'), int) or event['id'] <= last_id:
                            raise ValueError('Audit page contains a mismatched or unordered event')
                        stream.write((safe_json(event)+'\n').encode('utf-8'))
                        last_id = event['id']
                        count += 1
                    offset += len(page)
        if safe_json(read(run_id), indent=2) != serialized_report:
            raise ValueError('Terminal report changed during export; publication stopped')
        files = {}
        for path in (temporary/'report.json', temporary/'audit.jsonl.gz'):
            with path.open('rb') as source:
                digest = hashlib.file_digest(source,'sha256').hexdigest()
            files[path.name] = {'sha256':digest,'bytes':path.stat().st_size}
        manifest = {'source':'adaptive_thompson_pricing','run_id':run_id,'synthetic':True,
            'audit_records':count,'counts':report['counts'],'files':files,
            'customer_source':report['config']['mode'],'weight_source':report['population']['source'],
            'evidence_kind':'execution_failure' if terminal_failure else 'completed'}
        validation = report.get('validation')
        if validation and validation.get('selected_price_frozen_before_validation') is True:
            manifest['holdout_frozen_before_validation'] = True
        if report.get('scenario'):
            manifest['scenario'] = report['scenario']
        (temporary/'manifest.json').write_text(safe_json(manifest,indent=2),encoding='utf-8')
        if output.exists() or output.is_symlink():
            raise ValueError('Refusing to overwrite historical experiment evidence')
        # Same-parent rename publishes only a complete export. A failed page,
        # redaction check or write leaves no apparently completed directory.
        temporary.rename(output)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return {'run_id':run_id,'output':str(output),'status':report['status'],
            'counts':report['counts'],'validation':report.get('validation')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    from llm_agent.weighted_population import DEFAULT_PROFILE
    parser.add_argument('--flight-id',default='NET-HKG-KMQ-20270518')
    parser.add_argument('--name', help='Optional saved experiment name (1..64 plain characters)')
    parser.add_argument('--demo-scenario', choices=('low_fare_55', 'low_fare_60', 'low_fare_65'),
                        help='Explicit hypothetical low-fare / low-budget pricing stress scenario')
    parser.add_argument('--day',type=int,choices=(28,14,7),default=28)
    parser.add_argument('--mode',choices=('synthetic','live'),default='synthetic')
    parser.add_argument('--rounds',type=int,default=10)
    parser.add_argument('--customers',type=int,default=16)
    parser.add_argument('--concurrency',type=int,default=4)
    parser.add_argument('--max-calls',type=int,default=None)
    parser.add_argument('--validation-repeats',type=int,default=3)
    parser.add_argument('--seed',type=int,default=117)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--export-run-id')
    parser.add_argument('--include-failed', action='store_true',
                        help='With --export-run-id, also export failed/interrupted evidence without inventing results')
    args = parser.parse_args()
    if args.include_failed and not args.export_run_id:
        parser.error('--include-failed requires --export-run-id')
    if args.mode == 'live' and not args.export_run_id and args.max_calls is None:
        parser.error('--mode live requires an explicit --max-calls finite budget')
    # Loading configured secrets also lets sanitize redact echoed credentials
    # during an export; this does not make a provider request.
    if args.mode == 'live' or args.export_run_id:
        configure_provider()
    from backend.adaptive_pricing import start
    if args.export_run_id:
        if not args.output:
            parser.error('--export-run-id requires --output')
        print(json.dumps(export(args.export_run_id,args.output,include_failed=args.include_failed),ensure_ascii=False),flush=True)
        return
    config = {'flight_id':args.flight_id,'forecast_day':args.day,'mode':args.mode,'rounds':args.rounds,
              'customers':args.customers,'concurrency':args.concurrency,'max_calls':args.max_calls or 0,
              'validation_repeats':args.validation_repeats,'seed':args.seed,'profile':DEFAULT_PROFILE}
    if args.name is not None:
        config['name'] = args.name
    if args.demo_scenario is not None:
        config['demo_scenario'] = args.demo_scenario
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

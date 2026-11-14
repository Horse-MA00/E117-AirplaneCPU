"""Publish a completed LLM feedback experiment with redacted raw evidence.

No provider calls are made. The output directory must not already exist.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from llm_agent.audit import sanitize
from llm_agent.experiment import load_local_env


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


def _write_gzip(path, chunks):
    with path.open('wb') as raw, gzip.GzipFile(filename='', mode='wb', fileobj=raw, mtime=0) as archive:
        for chunk in chunks:
            archive.write(chunk.encode('utf-8'))


def export_payload(payload, output):
    """Export the same envelope returned by /api/feedback-pricing/runs/{id}/export.

    Useful when the running Docker database is not mounted on the host. Input
    evidence is preserved, apart from standard credential redaction.
    """
    load_local_env()
    safe = sanitize(payload)
    report, worlds, events = (safe[key] for key in ('report', 'worlds', 'events'))
    if report.get('status') != 'completed' or not report.get('validation'):
        raise ValueError('Only completed, independently evaluated experiments can be exported')
    if not worlds or not all(world.get('result') and world['result'].get('complete') and
                             world['result'].get('checks') and all(world['result']['checks'].values())
                             for world in worlds):
        raise ValueError('All exported worlds must be complete with passing accounting checks')
    if report.get('config', {}).get('objective') != 'base_ticket_revenue':
        raise ValueError('Expected a ticket-base-revenue experiment')
    accepted = [item['record'] for item in events
                if item['record'].get('event') in ('market_choice', 'price_proposal_validated')]
    if not accepted or any(row.get('source') not in ('provider_live', 'environment_forced') for row in accepted):
        raise ValueError('Cannot publish fixture or mathematical choices as live LLM evidence')
    # These remain distinct: a provider-origin cache replay is not a fresh call.
    provider_choices = sum(row.get('source') == 'provider_live' for row in accepted)
    if not provider_choices:
        raise ValueError('No accepted provider-origin output exists in this experiment')
    output = Path(output)
    if output.exists():
        raise ValueError('Refusing to overwrite an experiment export')
    # Serialize before creating a directory; invalid/non-finite JSON fails closed.
    report_text, worlds_text = _json(report), _json(worlds)
    audit_lines = [_json(item) + '\n' for item in events]
    output.mkdir(parents=True, exist_ok=False)
    (output / 'report.json').write_text(report_text + '\n', encoding='utf-8')
    _write_gzip(output / 'worlds.json.gz', [worlds_text])
    _write_gzip(output / 'audit.jsonl.gz', audit_lines)
    files = {name: {'sha256': hashlib.sha256((output / name).read_bytes()).hexdigest(),
                    'bytes': (output / name).stat().st_size}
             for name in ('report.json', 'worlds.json.gz', 'audit.jsonl.gz')}
    manifest = {
        'source': 'llm_feedback_pricing', 'run_id': report['run_id'],
        'decision_source': 'provider_live', 'synthetic': True,
        'objective': 'base_ticket_revenue', 'completed_worlds': len(worlds),
        'audit_records': len(events), 'counts': report['counts'],
        'accepted_provider_origin_outputs': provider_choices,
        'credentials': 'No authorization headers; known credentials redacted.',
        'limitations': ['Generated traveller choices are not human observations.',
                        'Base-ticket revenue excludes all costs and is not profit.',
                        'Provider-origin cache replay is not a new independent call.'],
        'files': files,
    }
    (output / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return {'run_id': report['run_id'], 'worlds': len(worlds), 'audit_records': len(events),
            'counts': report['counts'], 'output': str(output)}


def export(run_id, output):
    load_local_env()
    from backend import feedback_pricing
    return export_payload(feedback_pricing.export_run(run_id), output)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(export(args.run_id, args.output)))

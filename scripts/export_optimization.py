"""Export a completed synthetic SQLite experiment, with redacted audit evidence."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend import optimization, optimization_store
from llm_agent.audit import sanitize
from llm_agent.experiment import load_local_env


def export(run_id, output):
    load_local_env()
    report = optimization.export_run(run_id)
    if report['status'] != 'completed':
        raise ValueError('Only completed experiments can be published as validation evidence')
    output = Path(output)
    if output.exists():
        raise ValueError('Refusing to overwrite an experiment export')
    output.mkdir(parents=True)
    (output/'report.json').write_text(json.dumps(sanitize(report), ensure_ascii=False, indent=2), encoding='utf-8')
    count = 0
    with optimization_store.connection() as db, (output/'audit.jsonl.gz').open('wb') as raw:
        with gzip.GzipFile(filename='', mode='wb', fileobj=raw, mtime=0) as archive:
            for row in db.execute('SELECT id,world_id,recorded_at,record FROM optimization_events WHERE run_id=? ORDER BY id', (run_id,)):
                entry = {**dict(row), 'record': json.loads(row['record'])}
                archive.write((json.dumps(sanitize(entry), ensure_ascii=False)+'\n').encode())
                count += 1
    files = {path.name: {'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'bytes': path.stat().st_size}
             for path in output.iterdir() if path.is_file()}
    manifest = {'source': 'joint_optimization', 'run_id': run_id, 'synthetic': True, 'completed_worlds': len(report['worlds']),
                'audit_records': count, 'counts': report['counts'], 'files': files}
    (output/'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    return {'run_id': run_id, 'worlds': len(report['worlds']), 'audit_records': count, 'counts': report['counts']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(export(args.run_id, args.output)))

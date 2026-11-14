"""Verify committed synthetic datasets and experiment exports without provider calls."""
from pathlib import Path
import csv
import gzip
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def verify(manifest_path):
    manifest = json.loads(manifest_path.read_text())
    folder = manifest_path.parent
    files = manifest.get("files", {})
    for name, expected in files.items():
        path = folder / name
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        assert digest == (expected["sha256"] if isinstance(expected, dict) else expected), path
        if isinstance(expected, dict) and "bytes" in expected:
            assert path.stat().st_size == expected["bytes"], path
    result = {"path": str(folder.relative_to(ROOT)), "verified_files": len(files)}
    snapshots = folder / "snapshots.csv.gz"
    if snapshots.exists():
        with gzip.open(snapshots, "rt", newline="") as stream:
            count = sum(1 for _ in csv.DictReader(stream))
        assert count == manifest["rows"], snapshots
        result["snapshot_rows"] = count
    audit = folder / "audit.jsonl.gz"
    if audit.exists():
        count = 0
        with gzip.open(audit, "rt") as stream:
            for line in stream:
                assert isinstance(json.loads(line), dict), audit
                count += 1
        result["audit_records"] = count
    report = folder / "report.json"
    if manifest.get("source") == "shared_market_experiment":
        contents = json.loads(report.read_text())
        assert contents["completed_cases"] == contents["cases"], report
        for case in contents["case_results"]:
            checks = case["metrics"]["checks"]
            assert checks and all(checks.values()), case["case_id"]
        result["completed_market_cases"] = contents["cases"]
    if manifest.get("source") == "joint_optimization":
        contents = json.loads(report.read_text())
        assert contents['status'] == 'completed', report
        assert len(contents['worlds']) == manifest['completed_worlds'], report
        assert set(contents['search_seeds']).isdisjoint(contents['validation_seeds']), report
        for world in contents['worlds']:
            assert world['status'] == 'completed' and all(world['result']['checks'].values()), world['world_id']
        for track in contents['tracks']:
            assert track['validation']['seat_calibration'] == track['best']['seat_calibration'], track['mode']
        assert result['audit_records'] == manifest['audit_records'], audit
        result['completed_market_cases'] = len(contents['worlds'])
    return result


if __name__ == "__main__":
    # Required evidence must not disappear silently when a directory glob is empty.
    from backend.evidence import verify_extended
    extended = verify_extended(ROOT)
    manifests = [ROOT / "simulation/generated/manifest.json"]
    manifests += sorted((ROOT / "simulation/network_generated").glob("manifest.json"))
    manifests += sorted((ROOT / "simulation/validation_extended").glob("seed-*/manifest.json"))
    manifests += sorted((ROOT / "llm_agent/experiments").glob("*/manifest.json"))
    manifests += sorted((ROOT / "simulation/continuous_price_validation").glob("manifest.json"))
    results = [verify(path) for path in manifests]
    print(json.dumps({"status": "passed", "extended_evaluation": extended, "artifacts": results}, indent=2))

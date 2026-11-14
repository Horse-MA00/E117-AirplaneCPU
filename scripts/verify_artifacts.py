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
            if track['best'] is None:
                assert contents['config'].get('price_comparison_protocol') == 'fixed-seat-profile-local-fare-v1', track['mode']
                assert track['decision'] == 'NO_OFFER' and track['validation'] is None and track['rounds'], track['mode']
                assert all(r.get('price_evidence_qualified') is False
                           and r.get('price_evidence_status') in ('uninformative_no_supply','uninformative_no_member_exposure')
                           and r.get('accepted') is False and r.get('incumbent') is None
                           for r in track['rounds']), track['mode']
            else:
                assert track['validation']['seat_calibration'] == track['best']['seat_calibration'], track['mode']
        assert result['audit_records'] == manifest['audit_records'], audit
        result['completed_market_cases'] = len(contents['worlds'])
    if manifest.get('source') == 'adaptive_thompson_pricing':
        contents = json.loads(report.read_text())
        assert contents['status'] == 'completed', report
        assert len(contents['rounds']) == contents['config']['rounds'], report
        assert contents['counts']['provider_calls'] <= contents['config']['max_calls'], report
        assert sum(contents['counts']['key_slots'].values()) == contents['counts']['provider_calls'], report
        assert contents['counts']['failures'] == 0, report
        cap = contents['scope']['member_fare_cap']
        assert all(0 <= row['price'] <= cap for row in contents['rounds']), report
        assert contents['recommendation']['price'] in {r['price'] for r in contents['rounds']}, report
        assert contents['validation']['selected_price_frozen_before_validation'], report
        training_ids = {p['customer_id'] for p in contents['panel']}
        assert abs(sum(p['population_weight'] for p in contents['panel'])-1) < 1e-8, report
        if contents['version'] == 'member-thompson-v4-paired':
            cohorts = contents['search_panels']
            assert len(cohorts) == contents['config']['rounds'], report
            ids = [p['customer_id'] for cohort in cohorts for p in cohort['people']]
            assert len(ids) == len(set(ids)) == contents['config']['rounds']*contents['config']['customers'], report
            training_ids = set(ids)
            allowed = {'customer_id','segment','flexibility_days','population_weight'}
            assert all(set(p) <= allowed for p in contents['prediction_population']), report
            assert training_ids.isdisjoint(p['customer_id'] for p in contents['prediction_population']), report
            for row in contents['training_observations']:
                assert set(row['person']) <= allowed and row['phase'] == 'search', report
                assert row['person']['customer_id'] in training_ids, report
                assert row['price'] == int(row['price']), report
            assert all(row['price'] == int(row['price']) for row in contents['rounds']), report
            assert contents['scope']['normal_base_fare'] == int(contents['scope']['normal_base_fare']), report
            assert contents['validation']['adoption_result'] in ('ADOPT_CANDIDATE','KEEP_INITIAL','INCONCLUSIVE','NO_OFFER'), report
        for world in contents['validation_worlds']:
            metrics = world['result']
            assert training_ids.isdisjoint(r['person']['customer_id'] for r in metrics['decisions']), report
            assert metrics['remaining_seats'] >= 0 and metrics['remaining_quota'] >= 0, report
            assert metrics['member_buyers'] <= metrics['quota'], report
            assert abs(metrics['member_revenue']+metrics['regular_revenue']-metrics['revenue']) < .01, report
        assert result['audit_records'] == manifest['audit_records'], audit
        result['validated_price_rounds'] = len(contents['rounds'])
    return result


if __name__ == "__main__":
    # Required evidence must not disappear silently when a directory glob is empty.
    from backend.evidence import verify_extended
    extended = verify_extended(ROOT)
    manifests = [ROOT / "simulation/generated/manifest.json"]
    manifests += sorted((ROOT / "simulation/network_generated").glob("manifest.json"))
    manifests += sorted((ROOT / "simulation/member_demo_generated").glob("manifest.json"))
    manifests += sorted((ROOT / "simulation/validation_extended").glob("seed-*/manifest.json"))
    manifests += sorted((ROOT / "llm_agent/experiments").glob("*/manifest.json"))
    manifests += sorted((ROOT / "simulation/continuous_price_validation").glob("manifest.json"))
    results = [verify(path) for path in manifests]
    print(json.dumps({"status": "passed", "extended_evaluation": extended, "artifacts": results}, indent=2))

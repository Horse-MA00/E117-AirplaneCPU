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
    if manifest.get("source") == "llm_feedback_pricing":
        required = {"report.json", "worlds.json.gz", "audit.jsonl.gz"}
        assert required <= set(files), manifest_path
        contents = json.loads(report.read_text())
        assert contents["status"] == "completed" and contents.get("validation"), report
        assert contents["run_id"] == manifest["run_id"], report
        assert contents["config"]["objective"] == "base_ticket_revenue", report
        assert contents["config"]["membership_fee"] == 0, report
        assert manifest.get("synthetic") is True and manifest.get("decision_source") == "provider_live", manifest_path
        assert manifest["counts"] == contents["counts"], report
        assert result["audit_records"] == manifest["audit_records"], audit
        with gzip.open(folder / "worlds.json.gz", "rt", encoding="utf-8") as stream:
            worlds = json.load(stream)
        assert worlds and len(worlds) == manifest["completed_worlds"], report
        search_seeds = {world["seed"] for world in worlds if world["phase"] == "search"}
        holdout_seeds = set(contents["validation"]["seeds"])
        assert search_seeds and len(holdout_seeds) == 2 and search_seeds.isdisjoint(holdout_seeds), report
        actual_holdout = {world["seed"] for world in worlds if world["phase"].startswith("holdout_")}
        assert actual_holdout == holdout_seeds, report
        hashes = {}
        zero_fields = ("membership_revenue", "ancillary_revenue", "cancellation_revenue",
                       "mandatory_liability", "mandatory_remitted", "passenger_cost", "ancillary_cost",
                       "membership_service_cost", "program_cost", "total_variable_cost", "total_cost")
        for world in worlds:
            metrics = world["result"]
            assert metrics["complete"] is True and metrics["checks"] and all(metrics["checks"].values()), world["world_id"]
            assert world["run_id"] == contents["run_id"], world["world_id"]
            ledger = metrics["ledger"]
            revenue = round(ledger["normal_base_revenue"] + ledger["member_base_revenue"], 2)
            assert metrics["ticket_revenue"] == revenue, world["world_id"]
            assert all(ledger[field] == 0 for field in zero_fields), world["world_id"]
            assert world["state"]["policy"]["membership_fee"] == 0, world["world_id"]
            assert metrics["tickets_sold"] == metrics["tickets_flown"] + metrics["tickets_cancelled"], world["world_id"]
            hashes.setdefault(world["seed"], set()).add(metrics["exogenous_sha256"])
        assert all(len(values) == 1 for values in hashes.values()), report
        accepted_provider = 0
        with gzip.open(audit, "rt", encoding="utf-8") as stream:
            for line in stream:
                record = json.loads(line)["record"]
                if record.get("event") in ("market_choice", "price_proposal_validated"):
                    assert record.get("source") in ("provider_live", "environment_forced"), audit
                    accepted_provider += int(record.get("source") == "provider_live")
        assert accepted_provider > 0 and accepted_provider == manifest["accepted_provider_origin_outputs"], audit
        result["completed_market_cases"] = len(worlds)
        result["search_seeds"] = sorted(search_seeds)
        result["holdout_seeds"] = sorted(holdout_seeds)
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

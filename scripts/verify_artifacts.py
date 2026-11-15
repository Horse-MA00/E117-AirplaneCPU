"""Verify committed synthetic datasets and experiment exports without provider calls."""
from collections import Counter
from pathlib import Path
import csv
import gzip
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def experiment_status(contents, manifest):
    """Legacy completed manifests are immutable; new failure evidence is explicit."""
    status = contents['status']
    assert status in ('completed', 'failed', 'interrupted'), 'Only terminal experiments may be published'
    expected = 'completed' if status == 'completed' else 'execution_failure'
    assert manifest.get('evidence_kind', 'completed') == expected, 'Evidence kind disagrees with terminal status'
    assert manifest['run_id'] == contents['run_id'], 'Experiment identity mismatch'
    if status != 'completed':
        assert isinstance(contents.get('error'), str) and contents['error'].strip(), 'Incomplete experiment must retain its error'
    return status


def _canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def _audit_summary(path, run_id):
    """Stream raw evidence, including failed attempts; never infer success from status."""
    counts, slots = Counter(), Counter()
    summary = {'counts': counts, 'key_slots': slots, 'rounds': [], 'worlds': [], 'errors': [], 'records': 0}
    last_id = 0
    with gzip.open(path, 'rt', encoding='utf-8') as stream:
        for line in stream:
            wrapper = json.loads(line)
            assert isinstance(wrapper, dict) and wrapper.get('run_id') == run_id, path
            event_id = wrapper.get('id')
            assert isinstance(event_id, int) and not isinstance(event_id, bool) and event_id > last_id, path
            last_id = event_id
            record = wrapper['record']
            assert isinstance(record, dict), path
            event = record['event']
            summary['records'] += 1
            if event in ('customer_request', 'analyst_request'):
                counts['provider_calls'] += 1
                counts['customer_calls' if event == 'customer_request' else 'analyst_calls'] += 1
                slots[record['key_slot']] += 1
                if event == 'analyst_request' and record.get('attempt', 1) > 1:
                    counts['analyst_retries'] += 1
            if event in ('customer_response', 'analyst_response'):
                counts['fresh_responses'] += 1
                usage = record.get('usage')
                tokens = usage.get('total_tokens', 0) if isinstance(usage, dict) else 0
                if isinstance(tokens, int) and not isinstance(tokens, bool) and tokens >= 0:
                    counts['total_tokens'] += tokens
            if event in ('customer_failed', 'analyst_failed') and record.get('provider_call', True):
                counts['failures'] += 1
            if event in ('customer_cache', 'analyst_cache'):
                counts['cache_hits'] += 1
            if event == 'customer_forced':
                counts['forced'] += 1
            if event == 'customer_synthetic':
                counts['synthetic_choices'] += 1
            if event == 'analyst_unavailable':
                counts['analyst_unavailable'] += 1
            if event == 'round_completed':
                summary['rounds'].append((record['round'], record['price']))
            if event == 'validation_world':
                world = {key: value for key, value in record.items() if key != 'event'}
                summary['worlds'].append(hashlib.sha256(_canonical(world).encode()).hexdigest())
            if event == 'run_failed':
                summary['errors'].append(record['error'])
    return summary


def _verify_experiment(contents, manifest, audit, label):
    from backend.fare_policy import final_member_fare, integer_price, member_fare_cap
    assert contents['version'] == 'member-thompson-v5-marketing', label
    cfg = contents['config']
    assert cfg['profile'] == 'flexible_deal_seekers', label
    assert len(contents['population']['segments']) == 8, label
    status = experiment_status(contents, manifest)
    complete = status == 'completed'
    rounds = contents['rounds']
    assert len(rounds) <= cfg['rounds'] and (not complete or len(rounds) == cfg['rounds']), label
    assert [(row['round'], row['price']) for row in rounds] == audit['rounds'], 'Completed rounds disagree with audit'
    assert [row['round'] for row in rounds] == list(range(1, len(rounds) + 1)), label
    if status == 'failed':
        assert audit['errors'] and audit['errors'][-1] == contents['error'], 'Failure error disagrees with audit'
    elif complete:
        assert not audit['errors'], 'Completed experiment contains a fatal run failure'
    counts = contents['counts']
    assert counts == manifest['counts'], 'Manifest and report counters disagree'
    assert counts['provider_calls'] <= cfg['max_calls'], label
    for key in ('provider_calls', 'fresh_responses', 'cache_hits', 'forced', 'failures', 'synthetic_choices',
                'customer_calls', 'analyst_calls', 'analyst_retries', 'analyst_unavailable', 'total_tokens'):
        # Older immutable reports predate the retry counters. An absent counter
        # is acceptable only when its actual event count is zero.
        assert counts.get(key, 0) == audit['counts'][key], f'{label}: {key} disagrees with audit'
    slots = counts.get('key_slots', {})
    assert {k: v for k, v in slots.items() if v} == dict(audit['key_slots']), 'Provider key-slot counts disagree with audit'
    assert sum(slots.values()) == counts['provider_calls'], label
    if 'remaining_calls' in counts:
        assert counts['remaining_calls'] == cfg['max_calls'] - counts['provider_calls'], label
    assert audit['records'] == manifest['audit_records'], 'Audit record count mismatch'

    scope = contents['scope']
    cap = scope['member_fare_cap']
    integer_price(scope['normal_base_fare'])
    assert cap == member_fare_cap(scope['normal_base_fare']), label
    assert scope['initial_member_fare'] == cap, label
    for row in rounds:
        integer_price(row['price'], high=cap)
    assert cfg.get('final_member_fare_policy') == 'member-marketing-fare-v1', label
    cohorts = contents.get('search_panels', [])
    # A failing round may already have exposed its cohort, but cannot invent a
    # completed round or omit a previous one. Early startup failure has none.
    assert len(rounds) <= len(cohorts) <= min(cfg['rounds'], len(rounds) + (not complete)), label
    assert [c['round'] for c in cohorts] == list(range(1, len(cohorts) + 1)), label
    ids = [p['customer_id'] for cohort in cohorts for p in cohort['people']]
    assert all(len(c['people']) == cfg['customers'] for c in cohorts), label
    assert len(ids) == len(set(ids)), label
    training_ids = set(ids)
    if contents.get('panel'):
        assert abs(sum(p['population_weight'] for p in contents['panel']) - 1) < 1e-8, label
    elif complete:
        raise AssertionError(f'{label}: completed run is missing its panel')
    allowed = {'customer_id', 'segment', 'flexibility_days', 'population_weight'}
    support = contents.get('prediction_population', [])
    assert all(set(p) <= allowed for p in support), label
    assert training_ids.isdisjoint(p['customer_id'] for p in support), label
    if complete:
        assert support, label
    for row in contents.get('training_observations', []):
        assert set(row['person']) <= allowed and row['phase'] == 'search', label
        assert row['person']['customer_id'] in training_ids, label
        integer_price(row['price'], high=cap)

    selected, validation = contents.get('recommendation'), contents.get('validation')
    worlds = contents.get('validation_worlds', [])
    if complete:
        assert selected and validation, 'Completed experiment is missing independent validation'
    if selected:
        assert len(rounds) == cfg['rounds'], 'Selection must follow all search rounds'
        assert selected['raw_price'] in {r['price'] for r in rounds}, label
        assert selected['price'] == final_member_fare(selected['raw_price']), label
    if validation:
        assert selected and validation['selected_price_frozen_before_validation'], label
        initial = final_member_fare(scope['initial_member_fare'])
        assert validation['comparison_reference'] == 'formatted_initial_fare', label
        assert validation['initial_price'] == initial and validation['selected_price'] == selected['price'], label
        assert validation['adoption_result'] in ('ADOPT_CANDIDATE', 'KEEP_INITIAL', 'INCONCLUSIVE', 'NO_OFFER'), label
        expected_prices = {'initial': initial, 'selected': selected['price'], 'no_offer': None}
        assert validation['retained_price'] in expected_prices.values(), label
        assert len(worlds) == cfg['validation_repeats'] * 3, 'Incomplete validation cannot be presented as an outcome'
        policies = Counter((world['seed'], world['policy']) for world in worlds)
        seeds = {world['seed'] for world in worlds}
        assert len(seeds) == cfg['validation_repeats'], label
        assert policies == Counter({(seed, policy): 1 for seed in seeds for policy in expected_prices}), label
        for world in worlds:
            assert world['price'] == expected_prices[world['policy']], label
            metrics = world['result']
            assert training_ids.isdisjoint(r['person']['customer_id'] for r in metrics['decisions']), label
            assert metrics['remaining_seats'] >= 0 and metrics['remaining_quota'] >= 0, label
            assert metrics['member_buyers'] <= metrics['quota'], label
            assert abs(metrics['member_revenue'] + metrics['regular_revenue'] - metrics['revenue']) < .01, label
            if world['price'] is not None:
                assert abs(metrics['member_revenue'] - world['price'] * metrics['member_buyers']) < .01, label
        assert [hashlib.sha256(_canonical(world).encode()).hexdigest() for world in worlds] == audit['worlds'], 'Validation worlds disagree with audit'
    else:
        assert not worlds, 'Partial holdout must stay in the audit, without an invented aggregate'
        assert manifest.get('holdout_frozen_before_validation') is not True, 'No validation evidence supports the holdout claim'
    return {'status': status, 'validated_price_rounds': len(rounds), 'audit_records': audit['records']}


def verify(manifest_path):
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    folder = manifest_path.parent
    files = manifest.get('files', {})
    for name, expected in files.items():
        path = folder / name
        assert path.resolve().is_relative_to(folder.resolve()), 'Artifact path escapes experiment directory'
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        assert digest == (expected['sha256'] if isinstance(expected, dict) else expected), path
        if isinstance(expected, dict) and 'bytes' in expected:
            assert path.stat().st_size == expected['bytes'], path
    label = folder.relative_to(ROOT).as_posix() if folder.is_relative_to(ROOT) else str(folder)
    result = {'path': label, 'verified_files': len(files)}
    snapshots = folder / 'snapshots.csv.gz'
    if snapshots.exists():
        with gzip.open(snapshots, 'rt', encoding='utf-8', newline='') as stream:
            count = sum(1 for _ in csv.DictReader(stream))
        assert count == manifest['rows'], snapshots
        result['snapshot_rows'] = count
    if manifest.get('source') == 'adaptive_thompson_pricing':
        assert {'report.json', 'audit.jsonl.gz'} <= files.keys(), 'Experiment manifest must hash report and audit'
        assert manifest.get('synthetic') is True, 'Experiment population provenance is missing'
        report = folder / 'report.json'
        contents = json.loads(report.read_text(encoding='utf-8'))
        audit = _audit_summary(folder / 'audit.jsonl.gz', contents['run_id'])
        result.update(_verify_experiment(contents, manifest, audit, report))
    return result


def main():
    # Required evidence must not disappear silently when a directory glob is empty.
    from backend.evidence import verify_extended
    extended = verify_extended(ROOT)
    manifests = [ROOT / 'simulation/generated/manifest.json',
                 ROOT / 'simulation/hkx_recent_generated/manifest.json']
    manifests += sorted((ROOT / 'simulation/network_generated').glob('manifest.json'))
    manifests += sorted((ROOT / 'simulation/member_demo_generated').glob('manifest.json'))
    manifests += sorted((ROOT / 'simulation/validation_extended').glob('seed-*/manifest.json'))
    manifests += sorted((ROOT / 'llm_agent/experiments').glob('*/manifest.json'))
    results = [verify(path) for path in manifests]
    print(json.dumps({'status': 'passed', 'extended_evaluation': extended, 'artifacts': results}, indent=2))


if __name__ == '__main__':
    main()

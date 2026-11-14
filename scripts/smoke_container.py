"""Real HTTP smoke and restart verification against a running demo container.

Creates synthetic members, one booking and bounded rule-only background jobs.
Run --verify-only after recreating the container to check persisted state.
"""
import argparse
import json
from pathlib import Path
import time
import urllib.request
import uuid


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://127.0.0.1:8000')
    parser.add_argument('--record', type=Path, default=Path('data/private/container-smoke.json'))
    parser.add_argument('--verify-only', action='store_true')
    args = parser.parse_args()
    base = args.url.rstrip('/')

    def call(path, body=None):
        request = urllib.request.Request(base+path,
            data=None if body is None else json.dumps(body).encode(),
            headers={'Content-Type': 'application/json', 'Origin': base})
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.load(response)

    def wait(path):
        deadline = time.monotonic()+180
        while time.monotonic() < deadline:
            result = call(path)
            if result['status'] == 'completed':
                return result
            if result['status'] in ('failed', 'paused_after_errors', 'interrupted'):
                raise AssertionError(result.get('error', result['status']))
            time.sleep(.5)
        raise TimeoutError(path)

    assert call('/api/health')['status'] == 'ok'
    for path in ('/admin', '/members', '/app.js', '/continuous.js', '/members/portal.js'):
        with urllib.request.urlopen(base+path, timeout=10) as response:
            assert response.status == 200 and response.read()
    if not args.verify_only:
        customer = 'CONTAINER-'+uuid.uuid4().hex[:12]
        flights = call('/api/flights')['flights']
        for flight in flights:
            forecast = call('/api/forecast', {'flight_id': flight['flight_id'], 'days_to_departure': 28})['forecast']
            if forecast['releasable_seats'] >= 1:
                break
        else:
            raise AssertionError('No new D28 quota remains in this demo volume')
        offer = call('/api/offers', {'flight_id': flight['flight_id'], 'days_to_departure': 28,
                                    'quantity': 1, 'base_fare': 43.25})['offer']
        fee = call('/api/member-portal/config')['membership']['fee']
        call('/api/member-portal/join', {'customer_id': customer, 'expected_fee': fee})
        booking = call('/api/member-portal/book', {'customer_id': customer, 'offer_id': offer['id']})['booking']
        panel = call('/api/agents/panels', {'mode': 'deterministic', 'count': 4})
        panel = wait('/api/agents/panels/'+panel['run_id'])
        assert panel['runtime']['provider_calls'] == 0
        pricing = call('/api/pricing/runs', {'evaluations': 3, 'replicates': 1, 'customers': 4})
        pricing = wait('/api/pricing/runs/'+pricing['run_id'])
        assert pricing['report']['validation']['checks_passed']
        args.record.parent.mkdir(parents=True, exist_ok=True)
        args.record.write_text(json.dumps({'customer_id': customer, 'booking_id': booking['id'],
            'total': booking['total'], 'panel_id': panel['run_id'], 'pricing_id': pricing['run_id']}, indent=2), encoding='utf-8')

    record = json.loads(args.record.read_text(encoding='utf-8'))
    account = call('/api/member-portal/accounts/'+record['customer_id'])
    assert account['membership']['active']
    assert any(b['id'] == record['booking_id'] and b['total'] == record['total'] for b in account['bookings'])
    assert call('/api/agents/panels/'+record['panel_id'])['status'] == 'completed'
    assert call('/api/pricing/runs/'+record['pricing_id'])['status'] == 'completed'
    print(json.dumps({'status': 'passed', 'verify_only': args.verify_only, **record}))


if __name__ == '__main__':
    main()

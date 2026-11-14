"""Read-only checks of current HTTP routes and retirement, without provider calls."""
import argparse
import json
import urllib.error
import urllib.request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://127.0.0.1:8000')
    args = parser.parse_args()
    base = args.url.rstrip('/')

    def call(path, body=None):
        request = urllib.request.Request(base + path,
            data=None if body is None else json.dumps(body).encode(),
            headers={'Content-Type': 'application/json', 'Origin': base})
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)

    assert call('/api/health')['status'] == 'ok'
    summary = call('/api/summary')
    flights = call('/api/flights')['flights']
    assert summary['dataset']['rows'] == 200000
    assert len(flights) == summary['dataset']['flights']
    status = call('/api/adaptive-pricing/status')
    assert status['version'] == 'member-thompson-v5-marketing'
    assert status['population']['profile'] == 'flexible_deal_seekers'
    assert len(status['population']['segments']) == 8
    flight_id = 'NET-HKG-KMQ-20270518'
    forecast = call('/api/forecast', {'flight_id': flight_id, 'days_to_departure': 28})['forecast']
    scope = call('/api/adaptive-pricing/scope', {'flight_id': flight_id, 'forecast_day': 28})['scope']
    assert scope['flight_id'] == flight_id
    assert scope['initial_member_fare'] == scope['member_fare_cap']
    assert scope['initial_member_fare'] <= .8 * scope['normal_base_fare']
    for path in ('/api/optimization/runs', '/api/pricing/runs', '/api/market/runs',
                 '/api/agents/panels', '/api/personas', '/optimization.js', '/continuous.js',
                 '/.env.local', '/%2e%2e/.env.local'):
        try:
            urllib.request.urlopen(base + path, timeout=10)
        except urllib.error.HTTPError as error:
            assert error.code == 404, (path, error.code)
        else:
            raise AssertionError('Retired or private endpoint exposed: ' + path)
    for run in call('/api/adaptive-pricing/runs')['runs']:
        assert run.get('config', {}).get('profile') == 'flexible_deal_seekers'
    print(json.dumps({'status': 'passed', 'flights': len(flights),
        'member_quota': scope['releasable_seats'], 'forecast_available': bool(forecast),
        'provider_calls': 0}))


if __name__ == '__main__':
    main()

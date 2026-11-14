"""Verify real HTTP three-round carryover; writes synthetic demo transactions only."""
import json
import urllib.error
import urllib.request
import uuid

BASE = 'http://127.0.0.1:8000'


def call(path, body=None):
    request = urllib.request.Request(BASE + path, data=None if body is None else json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def forecast(flight, day):
    return call('/api/forecast', {'flight_id': flight, 'days_to_departure': day})['forecast']


def publish(flight, day, count):
    return call('/api/offers', {'flight_id': flight, 'days_to_departure': day, 'quantity': count, 'base_fare': 30})['offer']


def rejected(body):
    try:
        call('/api/offers', body)
    except urllib.error.HTTPError as error:
        assert error.code == 400, error.read()
        return
    raise AssertionError('Invalid release was accepted')


flights = call('/api/flights')['flights']
selected = None
for flight in flights:
    fid = flight['flight_id']
    states = [forecast(fid, day) for day in (28, 14, 7)]
    if all(not f['release_status']['round_history'] and f['risk_release_ceiling'] >= 12 for f in states):
        selected = fid
        break
assert selected, 'No unused eligible demo flight in the inspected set'
first = publish(selected, 28, 5)
first_person = 'ROUND-' + uuid.uuid4().hex[:12]
call('/api/members', {'customer_id': first_person})
call('/api/bookings', {'offer_id': first['id'], 'customer_id': first_person, 'days_to_departure': 28})
at14 = forecast(selected, 14)
assert at14['release_status']['previous_valid_unsold'] == 4
assert at14['releasable_seats'] == at14['risk_release_ceiling'] - 1 - 4
second = publish(selected, 14, 3)
second_person = 'ROUND-' + uuid.uuid4().hex[:12]
call('/api/members', {'customer_id': second_person})
call('/api/bookings', {'offer_id': second['id'], 'customer_id': second_person, 'days_to_departure': 14})
at13 = forecast(selected, 13)
assert at13['releasable_seats'] == 0 and at13['release_status']['next_release_day'] == 7
rejected({'flight_id': selected, 'days_to_departure': 13, 'quantity': 1, 'base_fare': 30})
at7 = forecast(selected, 7)
assert at7['release_status']['previous_valid_unsold'] == 6
assert at7['release_status']['member_sold'] == 2
assert at7['releasable_seats'] == at7['risk_release_ceiling'] - 2 - 6
publish(selected, 7, 2)
final = forecast(selected, 7)['release_status']
assert final['new_release_limit'] == 0 and final['total_active_unsold'] == 8
assert [r['day'] for r in final['round_history']] == [28, 14, 7]
rejected({'flight_id': selected, 'days_to_departure': 7, 'quantity': 1, 'base_fare': 30})
rejected({'flight_id': selected, 'days_to_departure': 14, 'quantity': 1, 'base_fare': 30})
print(json.dumps({'status': 'passed', 'flight': selected, 'issued_by_round': [5, 3, 2], 'sold': 2, 'valid_unsold': 8, 'd14_carry': 4, 'd7_carry': 6, 'between_round_issue_rejected': True}))

"""Observed flight snapshot and NHPP quota for Thompson member pricing."""
import hashlib
import json
from datetime import datetime

from backend import data
from backend.fare_policy import MEMBER_FARE_CAP_RATIO, member_fare_cap, quoted_base_fare


def flight_scope(flight_id, day=28):
    if day not in (28, 14, 7) or isinstance(day, bool):
        raise ValueError('forecast_day must be 28, 14 or 7')
    flight = next((f for f in data.flights() if f['flight_id'] == flight_id), None)
    if flight is None:
        raise ValueError('Unknown flight')
    history = [dict(row) for row in data.history(flight_id) if row['days_to_departure'] >= day]
    row = next((r for r in history if r['days_to_departure'] == day), None)
    if row is None:
        raise ValueError('Selected flight has no snapshot at this release day')
    quote = next((r for r in reversed(history) if r.get('normal_base_fare') is not None), None)
    if quote is None:
        raise ValueError('Selected flight has no observed base-fare quote at or before this release day')
    from backend.forecast import forecast
    prediction = forecast(history, day, seed=117)
    # Start at the highest permitted member fare: 80% of the observable normal
    # base fare. Historical 15% member-price columns are kept for reproducibility only.
    normal_quote = quoted_base_fare(quote['normal_base_fare'])
    cap = member_fare_cap(normal_quote)
    fare = cap
    departure = datetime.fromisoformat(str(flight['departure_at']).replace('Z','+00:00'))
    eligible = prediction['releasable_seats'] > 0
    return {'flight_id': flight_id, 'origin': flight['origin'], 'destination': flight['destination'],
            'departure_date': flight.get('departure_date', str(flight.get('departure_at',''))[:10]), 'as_of_day': day,
            'departure_at': flight['departure_at'], 'departure_time':departure.strftime('%H:%M'),
            'capacity': row['capacity'], 'booked_seats': row['booked_seats'],
            'available_seats': row['available_seats'], 'empty_rate': row['empty_rate'],
            'normal_base_fare': normal_quote, 'observed_normal_base_fare': quote['normal_base_fare'], 'price_increment_hkd': 1, 'mandatory_fees': row.get('mandatory_fees', 250),
            'quote_age_days': quote['days_to_departure']-day,
            'initial_member_fare': fare,
            'initial_fare_source': 'snapshot.normal_base_fare_x_member_cap',
            'member_fare_cap': cap, 'member_fare_cap_ratio': MEMBER_FARE_CAP_RATIO,
            'expected_remaining_demand': prediction['expected_remaining_demand'],
            'releasable_seats': prediction['releasable_seats'],
            'member_supply_exposure': prediction['releasable_seats'],
            'optimization_eligible': eligible,
            'optimization_unavailable_reason': None if eligible else
                'No releasable member seats at the selected round. Choose another flight or release day; later rounds are assessed separately.',
            'history_sha256': hashlib.sha256(json.dumps(history, sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
            'history': history}

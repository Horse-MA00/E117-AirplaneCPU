"""Transparent data-based starting hypothesis, before market-feedback search."""
import math
import statistics
import hashlib
import json
from datetime import datetime

from backend import data
from backend.shared_market import DEFAULTS
from backend.fare_policy import MEMBER_FARE_CAP_RATIO, member_fare_cap, integer_price, quoted_base_fare


# Product policy for new flight-scoped Optimize requests only. Legacy unscoped
# experiments and previously saved runs keep their own membership fee.
SCOPED_MEMBERSHIP_FEE = 399


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


def _number(body, key, default, low, high):
    value = body.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f'{key} must be {low}..{high}')
    return value


def suggest(body=None):
    body = {} if body is None else body
    if not isinstance(body, dict):
        raise ValueError('JSON object required')
    if body.get('flight_id'):
        scope = flight_scope(body['flight_id'], body.get('forecast_day', 28))
        return {'initial_member_fare': scope['initial_member_fare'],
                'initial_membership_fee': SCOPED_MEMBERSHIP_FEE,
                'scope': scope, 'source': {**{k:v for k,v in scope.items() if k != 'history'}, 'kind':'selected_synthetic_flight_snapshot'},
                'assumptions': ['P0 is the member fare cap: 80% of the whole-HKD normal base fare at the selected snapshot. Member fares are never searched above it. Historical member-price columns are not used.',
                    f'P0 is fixed by the dataset, not a user price entry. V0 is fixed at HK${SCOPED_MEMBERSHIP_FEE} for this flight search.',
                    'One selected flight is evaluated; this is not an annual membership-fee optimum.']}
    customers = _number(body, 'customers', 14, 1, 100)
    setup = _number(body, 'program_cost', DEFAULTS['program_cost'], 0, 10000)
    fare_max = integer_price(_number(body, 'fare_max', 2000, 0, 2000), 'fare_max')
    fee_max = integer_price(_number(body, 'fee_max', 1500, 0, 5000), 'fee_max')
    fare_min = integer_price(_number(body, 'fare_min', 0, 0, 2000), 'fare_min')
    fee_min = integer_price(_number(body, 'fee_min', 0, 0, 5000), 'fee_min')
    if fare_min >= fare_max or fee_min >= fee_max:
        raise ValueError('Search intervals must span at least one HKD')
    fares = []
    for history in data.histories().values():
        # One as-of quote per flight; long histories do not receive extra weight.
        row = next((r for r in history if r['days_to_departure'] == 28), None)
        if row and row.get('normal_base_fare') is not None:
            fares.append(row['normal_base_fare'])
    if not fares:
        raise ValueError('No observed D28 normal fares are available')
    median = statistics.median(fares)
    fare = math.floor(min(fare_max, max(fare_min, median)))
    subscribers = max(1., customers*.5)
    trips = DEFAULTS['occasions_per_customer']
    raw_fee = DEFAULTS['membership_service_cost'] + trips*max(0, DEFAULTS['incremental_passenger_cost']-fare) + setup/subscribers
    fee = math.ceil(min(fee_max, max(fee_min, raw_fee)))
    return {'initial_member_fare': fare, 'initial_membership_fee': fee,
            'source': {'rows': len(fares), 'flights': len(fares), 'as_of_day': 28,
                       'median_normal_base_fare': round(median, 2), 'kind': 'synthetic_observed_quotes'},
            'cost_assumptions': {'passenger_cost': DEFAULTS['incremental_passenger_cost'],
                'membership_service_cost': DEFAULTS['membership_service_cost'], 'program_cost': setup,
                'planned_trips': trips, 'assumed_subscribers': subscribers, 'fare_fraction': 1.0},
            'fee_capped': raw_fee > fee_max,
            'assumptions': ['P0 is the median observed D28 normal base fare without an initial discount, subject to explicit search bounds.',
                'V0 covers the assumed three-trip marginal fare shortfall, membership service and programme cost at 50% assumed subscription, subject to the search bound.',
                'No allowance for displacement or failed availability is inferred here. Both are evaluated by the subsequent shared-market search.',
                'This is an editable starting hypothesis, not a recommended or validated price. No LLM calls were made.']}

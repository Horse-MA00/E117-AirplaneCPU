"""Transparent data-based starting hypothesis, before market-feedback search."""
import math
import statistics

from backend import data
from backend.shared_market import DEFAULTS


def _number(body, key, default, low, high):
    value = body.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f'{key} must be {low}..{high}')
    return value


def suggest(body=None):
    body = {} if body is None else body
    if not isinstance(body, dict):
        raise ValueError('JSON object required')
    customers = _number(body, 'customers', 14, 1, 100)
    setup = _number(body, 'program_cost', DEFAULTS['program_cost'], 0, 10000)
    fare_max = _number(body, 'fare_max', 500, 0, 2000)
    fee_max = _number(body, 'fee_max', 1500, 0, 5000)
    fare_min = _number(body, 'fare_min', 0, 0, 2000)
    fee_min = _number(body, 'fee_min', 0, 0, 5000)
    if round(fare_min*100) >= round(fare_max*100) or round(fee_min*100) >= round(fee_max*100):
        raise ValueError('Search intervals must span at least one cent')
    fares = []
    for history in data.histories().values():
        # One as-of quote per flight; long histories do not receive extra weight.
        row = next((r for r in history if r['days_to_departure'] == 28), None)
        if row and row.get('normal_base_fare') is not None:
            fares.append(row['normal_base_fare'])
    if not fares:
        raise ValueError('No observed D28 normal fares are available')
    median = statistics.median(fares)
    fare = round(min(fare_max, max(fare_min, .15*median)), 2)
    subscribers = max(1., customers*.5)
    trips = DEFAULTS['occasions_per_customer']
    raw_fee = DEFAULTS['membership_service_cost'] + trips*max(0, DEFAULTS['incremental_passenger_cost']-fare) + setup/subscribers
    fee = round(min(fee_max, max(fee_min, raw_fee)), 2)
    return {'initial_member_fare': fare, 'initial_membership_fee': fee,
            'source': {'rows': len(fares), 'flights': len(fares), 'as_of_day': 28,
                       'median_normal_base_fare': round(median, 2), 'kind': 'synthetic_observed_quotes'},
            'cost_assumptions': {'passenger_cost': DEFAULTS['incremental_passenger_cost'],
                'membership_service_cost': DEFAULTS['membership_service_cost'], 'program_cost': setup,
                'planned_trips': trips, 'assumed_subscribers': subscribers, 'fare_fraction': .15},
            'fee_capped': raw_fee > fee_max,
            'assumptions': ['P0 is 15% of the median observed D28 base fare, subject to the search bound; 15% is a starting assumption, not estimated price sensitivity.',
                'V0 covers the assumed three-trip marginal fare shortfall, membership service and programme cost at 50% assumed subscription, subject to the search bound.',
                'No allowance for displacement or failed availability is inferred here. Both are evaluated by the subsequent shared-market search.',
                'This is an editable starting hypothesis, not a recommended or validated price. No LLM calls were made.']}

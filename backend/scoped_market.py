"""One-flight synthetic replay using an immutable observed flight snapshot.

The future demand generator is independent of NHPP forecast outputs. A random
level/growth/jump continuation is anchored only to observed normal bookings.
Existing simulated future price paths are replayed as exogenous quotes. They
never enter the initial forecast or the traveller's pre-event observation.
"""
import copy
from datetime import date, timedelta
import math
import numpy as np

from backend import data
from backend.shared_market import create_market, _cents, _money, _digest
from backend.release_policy import RELEASE_DAYS


def create_scoped_market(scope, config, seed, policy):
    # Reuse the tested household, membership, ledger and state constructors,
    # then replace the entire flight/event catalogue before any event executes.
    state = create_market({**config, 'flight_count': 6, 'occasions_per_customer': 3}, seed, policy)
    rng = np.random.default_rng(seed)
    day = scope['as_of_day']
    fid = scope['flight_id']
    cfg = state['config']
    cfg.update(flight_count=1, occasions_per_customer=1,
               start_date=(date.fromisoformat(scope['departure_date'])-timedelta(days=day)).isoformat(),
               mandatory_fees=scope['mandatory_fees'], flight_scope={k:v for k,v in scope.items() if k!='history'})
    departure_time = scope['departure_time']
    hour,minute = map(int,departure_time.split(':'))
    departure_at = day + hour/24 + minute/1440
    history = copy.deepcopy(scope['history'])
    f = {'flight_id': fid, 'origin': scope['origin'], 'destination': scope['destination'],
         'departure_day': day, 'departure_time': departure_time, 'departure_at': departure_at,
         'capacity': scope['capacity'], 'legacy_seats': scope['booked_seats'], 'occupied': scope['booked_seats'],
         'history': history, 'history_as_of_day': day, 'active': False, 'departed': False,
         'member_remaining': 0, 'member_active': 0, 'protection_remaining': scope['capacity'],
         'normal_since_snapshot': 0, 'cancel_since_snapshot': 0, 'base_fare': scope['normal_base_fare'],
         'forecast': None, 'quota_history': [], 'quota_cohorts': [], 'background_requested': 0,
         'background_denied': 0, 'scenario_scoring_only': 'selected_flight_independent_continuation'}
    state['flights'] = {fid: f}
    events = []
    future_prices = {r['days_to_departure']: r.get('normal_base_fare') for r in data.history(fid)}
    recent = [r for r in history if day <= r['days_to_departure'] < day+14]
    empirical_rate = max(.15, sum(r.get('gross_bookings', 0) for r in recent)/max(1,len(recent)))
    level = empirical_rate * rng.gamma(4., .25)
    growth = float(rng.uniform(-.02, .06))
    jump_day = int(rng.integers(1, day+1))
    jump = float(rng.choice([1., 1., 1., 2., 4.]))
    last_price = scope['normal_base_fare']
    for d in range(day, -1, -1):
        price = future_prices.get(d) or last_price
        last_price = price
        at = departure_at-d if d else departure_at-2/24
        events.append({'time': at, 'kind':'snapshot', 'flight_id':fid, 'day_to_departure':d, 'base_fare':price})
        if not d:
            continue
        duration = 22/24 if d == 1 else 1.
        intensity = level*math.exp(growth*(day-d))*(jump if d <= jump_day else 1.)
        for j in range(int(rng.poisson(intensity*duration))):
            bid = f'BG-{fid}-{d}-{j}'
            when = departure_at-d+float(rng.uniform(.005,duration-.005))
            events.append({'time':when,'kind':'background','flight_id':fid,'booking_id':bid,'base_fare':price})
            if rng.random() < cfg['background_cancellation_probability'] and departure_at-when>1:
                events.append({'time':float(rng.uniform(when+.05,departure_at-.1)), 'kind':'background_cancel','booking_id':bid})
    events.append({'time':departure_at,'kind':'departure','flight_id':fid})
    for c in state['customers'].values():
        p = c['person']; cid = p['customer_id']
        c['budget_cents'] = c['initial_budget_cents'] = round(c['initial_budget_cents']/3)
        p.update(total_budget=_money(c['budget_cents']), next_period_budget=_money(c['budget_cents']), expected_trips=1)
        old = c['occasions'][0]
        target = scope['destination'] if p['route_match'] else 'LAX'
        occasion = {**old, 'desired_departure_day':day,'desired_destination':target,'acceptable_destinations':[target]}
        c['occasions'] = [occasion]
        jitter = float(rng.uniform(.03,.87))
        for d in RELEASE_DAYS:
            if d > day: continue
            for stage, offset in [('subscription',0),('quote',.00001)]:
                events.append({'time':departure_at-d+jitter+offset,'kind':'decision','stage':stage,
                               'customer_id':cid,'occasion_id':occasion['occasion_id']})
        events.append({'time':departure_at-3+jitter,'kind':'decision','stage':'plan_change','customer_id':cid,'occasion_id':occasion['occasion_id']})
        events.append({'time':float(120 if c['membership_expires'] is not None else cfg['horizon_days']),
                       'kind':'decision','stage':'term_end','customer_id':cid,'occasion_id':None})
    priority = {'snapshot':0,'background_cancel':1,'background':2,'decision':3,'departure':4}
    events.sort(key=lambda e:(e['time'],priority[e['kind']],e.get('customer_id',e.get('flight_id',e.get('booking_id','')))))
    for i,event in enumerate(events): event['event_id'] = f'E{i:06d}'
    state['events'] = events
    state['exogenous_sha256'] = _digest({'seed':seed,'events':events,'customers':state['customers'],'flights':state['flights']})
    return state


def attribute_result(result, state, term_trips=3):
    """Allocate only one share of annual fee/service to this flight; preserve cash ledger."""
    ledger = result['ledger']
    excluded_fee = ledger['membership_revenue']*(1-1/term_trips)
    excluded_service = ledger['membership_service_cost']*(1-1/term_trips)
    revenue = ledger['revenue_excluding_mandatory_fees']-excluded_fee
    costs = ledger['total_cost']-excluded_service
    purchased = [b for b in state['bookings'].values() if b['customer_id'] is not None]
    flown = [b for b in purchased if b['status']=='flown']
    result.update(full_cash_contribution=result['contribution'], contribution=round(revenue-costs,2),
                  profit=round(revenue-costs,2), attributed_revenue=round(revenue,2), attributed_cost=round(costs,2),
                  profit_margin=(revenue-costs)/revenue if revenue>0 else None,
                  buyers=len({b['customer_id'] for b in purchased}),
                  tickets=sum(b['party_size'] for b in purchased),
                  fulfilled_buyers=len({b['customer_id'] for b in flown}),
                  fulfilled_tickets=sum(b['party_size'] for b in flown),
                  scope_flight_id=state['config']['flight_scope']['flight_id'],
                  annual_fee_allocation=1/term_trips)
    result['assumptions'].append('Single selected-flight replay: one third of new annual pass income/service cost is attributed to this flight. Full fee is charged once; other trips are not simulated, so this is not annual profit or an optimal annual membership fee.')
    result['assumptions'].append('Buyers are distinct simulated customer households with an accepted booking, including later cancellations; tickets count their accepted party seats. Background requests are excluded. Fulfilled buyers/tickets count only flown bookings.')
    return result

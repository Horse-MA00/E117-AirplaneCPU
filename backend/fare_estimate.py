"""Closed-form expected-contribution scan for the mathematical customer model.

The full market simulation draws one keyed Gumbel shock per decision. This
module instead uses the same logit utilities as backend.probabilistic_customer
and takes expectations, so every member fare in [0, cap] can be scored at HK$1
resolution in milliseconds. It is a search aid only: the optimizer re-evaluates
the estimate and a fine grid around it with the full simulation.

Approximations (corrected by the follow-up simulation):
- member quota, background demand and seat rationing are not modelled;
- join and booking states are treated as independent across travellers;
- cancellations and plan changes are ignored.
"""
import math

import numpy as np

from backend import data
from backend.probabilistic_customer import SCENARIOS, VERSION as CUSTOMER_VERSION, uniform
from backend.release_policy import RELEASE_DAYS

VERSION = 'formula-scan-v1'
GRID_POINTS = 9
GRID_DIVISIONS = 32  # grid step = cap / 32, so the 9 points span +/- cap / 8


def _fare_by_day(flight_id, as_of_day, fallback):
    """Normal base fare quoted at each release day, replaying the simulator's exogenous path."""
    quotes = {r['days_to_departure']: r.get('normal_base_fare') for r in data.history(flight_id)}
    fares, last = {}, fallback
    for day in range(as_of_day, -1, -1):
        last = quotes.get(day) or last
        fares[day] = last
    return fares


def _travellers(cfg, seeds):
    from backend.scoped_market import create_scoped_market
    scope = cfg['scope']
    market_config = {'customer_count': cfg['customers'], 'flight_count': cfg['flights'],
                     'occasions_per_customer': 3, 'program_cost': cfg['program_cost']}
    policy = {'name': 'FORMULA_SCAN', 'enabled': True, 'member_fare': 0,
              'membership_fee': cfg['initial_membership_fee'], 'release_fraction': cfg['release_fraction'], 'open_day': 28}
    out = []
    for seed in seeds:
        state = create_scoped_market(scope, market_config, seed, policy)
        flight = next(iter(state['flights'].values()))
        market = state['config']
        for customer in state['customers'].values():
            person = customer['person']
            occasion = customer['occasions'][0]
            if not person['route_match'] or flight['destination'] not in occasion['acceptable_destinations']:
                continue  # never sees this flight
            cid = person['customer_id']
            expires = customer['membership_expires']
            out.append({
                'party': person['party_size'], 'bags': market['checked_bag_fee'] * person['checked_bags'],
                'fees': market['mandatory_fees'] * person['party_size'],
                'wallet': customer['budget_cents'] / 100, 'trip_budget': max(1., occasion['trip_budget']),
                'sensitivity': (.65 + 1.1 * uniform(CUSTOMER_VERSION, cid, 'sensitivity')) * SCENARIOS['base'],
                'patience': .15 + .5 * uniform(CUSTOMER_VERSION, cid, 'patience'),
                'perceived': person['perceived_availability'],
                'member': expires is not None and flight['departure_at'] < expires,
            })
        costs = {'passenger': market['incremental_passenger_cost'], 'service': market['membership_service_cost']}
    return out, costs


def _scan(prices, travellers, fares, days, fee, costs, allocation, offer):
    """Expected attributed contribution for each price (vector over prices)."""
    total = np.zeros_like(prices)
    member_tickets = np.zeros_like(prices)
    joins = np.zeros_like(prices)
    for t in travellers:
        unbooked = np.ones_like(prices)
        member = np.full_like(prices, 1. if t['member'] else 0.)
        party, scale = t['party'], 3 * t['sensitivity'] / t['trip_budget']
        for day in days:
            fare = fares[day]
            regular = fare * party + t['bags'] + t['fees']
            ticket = fare * (party - 1) + prices + t['bags'] + t['fees']
            if offer:
                # Subscription stage: JOIN_PASS vs DECLINE (same utility as the customer model).
                affordable = (fee + ticket) <= t['wallet']
                utility = ((fare - prices) * t['perceived'] - t['sensitivity'] * fee) / 120 - .5
                join = np.where(affordable & (fee <= t['wallet']), 1 / (1 + np.exp(-utility)), 0.)
                new = (1 - member) * join
                joins += new
                total += new * (fee - costs['service']) * allocation
                member = member + new
            # Quote stage: BUY_MEMBER (members only) / BUY_REGULAR / DECLINE / WAIT (> 7 days out).
            wait = math.exp(t['patience']) if day > 7 else 0.
            w_regular = math.exp(3.2 - scale * regular) if regular <= t['wallet'] else 0.
            w_member = np.where(ticket <= t['wallet'], np.exp(3.2 - scale * ticket), 0.) if offer else 0.
            p_member = w_member / (w_member + w_regular + 1 + wait)
            p_regular = member * w_regular / (w_member + w_regular + 1 + wait) + (1 - member) * w_regular / (w_regular + 1 + wait)
            buy_member, buy_regular = unbooked * member * p_member, unbooked * p_regular
            total += buy_member * (prices + fare * (party - 1) - costs['passenger'] * party)
            total += buy_regular * (fare * party - costs['passenger'] * party)
            member_tickets += buy_member
            unbooked = unbooked - buy_member - buy_regular
    return total, member_tickets, joins


def estimate(cfg, seeds):
    """Score every member fare in [0, cap] at HK$1 and return P* plus the simulation grid."""
    scope = cfg['scope']
    cap = round(float(scope['member_fare_cap']), 2)
    low = round(float(cfg['fare_min']), 2)
    high = min(cap, round(float(cfg['fare_max']), 2))
    prices = np.unique(np.append(np.arange(low, high, 1.0), high)).round(2)
    travellers, costs = _travellers(cfg, seeds)
    days = [d for d in RELEASE_DAYS if d <= scope['as_of_day']]
    fares = _fare_by_day(scope['flight_id'], scope['as_of_day'], scope['normal_base_fare'])
    fee, allocation = cfg['initial_membership_fee'], cfg.get('annual_fee_allocation', 1 / 3)
    with_offer, member_tickets, joins = _scan(prices, travellers, fares, days, fee, costs, allocation, True)
    without, _, _ = _scan(prices, travellers, fares, days, fee, costs, allocation, False)
    incremental = (with_offer - without) / max(1, len(seeds))
    # Ties go to the higher fare: an equal estimate never justifies a deeper discount.
    best = int(np.flatnonzero(incremental >= incremental.max() - 1e-9)[-1])
    p_star = float(prices[best])
    return {'version': VERSION, 'p_star': round(p_star, 2), 'cap': cap, 'search_low': low, 'search_high': high,
            'expected_incremental': round(float(incremental[best]), 2),
            'expected_member_tickets': round(float(member_tickets[best]) / max(1, len(seeds)), 3),
            'expected_joins': round(float(joins[best]) / max(1, len(seeds)), 3),
            'travellers_scored': len(travellers), 'prices_scored': int(len(prices)),
            'curve': [{'member_fare': float(p), 'expected_incremental': round(float(v), 2)}
                      for p, v in zip(prices[::max(1, len(prices) // 60)], incremental[::max(1, len(prices) // 60)])],
            'grid': fine_grid(p_star, low, high),
            'approximation': 'Expected logit choices on the same simulated travellers; ignores member quota, background demand, cancellations and seat rationing. The full simulation re-scores the grid.'}


def fine_grid(p_star, low, high):
    """P* first, then the nearest lattice points (step = span / 32), alternating sides.

    A search bound inside the grid window is always tested itself: when the
    estimate sits just below the fare cap, the cap is often the true optimum.
    """
    step = max(.01, round((high - low) / GRID_DIVISIONS, 2))
    points, seen = [round(p_star, 2)], {round(p_star * 100)}
    for bound in (high, low):
        if abs(bound - p_star) <= (GRID_POINTS // 2) * step and round(bound * 100) not in seen:
            points.append(round(bound, 2))
            seen.add(round(bound * 100))
    for k in range(1, 4 * GRID_POINTS):
        for sign in (-1, 1):
            value = round(p_star + sign * k * step, 2)
            if low - 1e-9 <= value <= high + 1e-9 and round(value * 100) not in seen:
                points.append(value)
                seen.add(round(value * 100))
            if len(points) == GRID_POINTS:
                return points
    return points

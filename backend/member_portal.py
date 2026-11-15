"""Member shopping view over the same published SQLite inventory as Admin.

Local prototype identities only: this module is not an authentication system.
"""
import json
from . import data


def config(store):
    return {'membership': store.plan(), 'currency': 'HKD', 'simulated': True,
            'booking_scope': 'One member seat per booking; baggage is not sold by this prototype.'}


def flights(store, forecast_for):
    catalog = {flight['flight_id']: flight for flight in data.flights()}
    choices = {}
    for offer in store.offers():
        flight = catalog.get(offer['flight_id'])
        if not flight:
            continue
        day = offer['sim_day']
        prediction = forecast_for(offer['flight_id'], day)
        status = store.release_status(offer['flight_id'], day, prediction['releasable_seats'])
        snapshot = next((r for r in data.history(offer['flight_id']) if r['days_to_departure'] == day), None)
        row = {'offer_id': offer['id'], 'flight_id': offer['flight_id'], 'origin': flight['origin'],
               'destination': flight['destination'], 'departure_at': flight['departure_at'], 'departure_date': flight['departure_at'][:10],
               'capacity': flight['capacity'], 'release_day': offer['day'], 'days_to_departure': day,
               'base_fare': offer['base_fare'], 'mandatory_fees': offer['fees'],
               'total': round(offer['base_fare'] + offer['fees'], 2),
               'bookable_seats': min(offer['remaining'], status['currently_bookable']),
               'normal_total': snapshot['normal_total_fare'] if snapshot else None,
               'normal_base_fare': snapshot.get('normal_base_fare') if snapshot else None,
               'expires': offer['expires'], 'source': 'synthetic',
               **{key: offer[key] for key in ('clock_version', 'time_basis', 'simulation_as_of',
                                              'sales_cutoff_at', 'membership_time_basis')}}
        row['fee_breakdown'] = json.loads(offer['fee_breakdown']) if offer.get('fee_breakdown') else None
        if row['fee_breakdown']:
            row['normal_total'] = (round(row['normal_base_fare'] + offer['fees'], 2)
                                   if row['normal_base_fare'] is not None else None)
        # One result per flight: choose the cheapest actually bookable cohort.
        # Cohorts share a risk ceiling; adding their counts would overstate supply.
        rank = (row['bookable_seats'] == 0, row['total'], -row['release_day'])
        previous = choices.get(offer['flight_id'])
        if previous is None or rank < previous[0]:
            choices[offer['flight_id']] = (rank, row)
    return {'flights': sorted((row for _, row in choices.values()), key=lambda row: (row['departure_date'], row['destination'], row['total'])),
            'currency': 'HKD', 'simulated': True}


def account(store, customer_id):
    result = store.account(customer_id)
    catalog = {flight['flight_id']: flight for flight in data.flights()}
    for booking in result['bookings']:
        booking['fee_breakdown'] = json.loads(booking['fee_breakdown']) if booking.get('fee_breakdown') else None
        flight = catalog.get(booking['flight_id'], {})
        booking.update(origin=flight.get('origin'), destination=flight.get('destination'),
                       departure_date=flight.get('departure_at', '')[:10], status='confirmed_simulation')
    result['currency'] = 'HKD'
    return result


def book(store, forecast_for, customer_id, offer_id, expected_total=None):
    offer = store.offer_info(offer_id)
    total = round(offer['base_fare'] + offer['fees'], 2)
    if expected_total is not None and expected_total != total:
        raise ValueError('The flight price changed. Refresh and review the current total before booking.')
    # Consumers cannot rewind the clock, supply a different price or change
    # normal-demand protection. Store.book rechecks capacity transactionally.
    prediction = forecast_for(offer['flight_id'], offer['sim_day'])
    return store.book(offer_id, customer_id, offer['sim_day'], prediction['releasable_seats'], expected_total=total)

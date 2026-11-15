"""Flight simulation time, separate from membership and audit wall-clock time.

A flight's selected D-day is an absolute timestamp relative to its published
departure. Advancing the simulation never moves the departure or sales cutoff.
The frozen D0 snapshot is the two-hour sales cutoff, not the departure instant.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

from .errors import NotFound


VERSION = 'flight-as-of-v1'
LEGACY_VERSION = 'legacy-wall-clock-v0'
DAY_SECONDS = 86400
SALES_CUTOFF_SECONDS = 7200
DISPLAY_TIMEZONE = ZoneInfo('Asia/Hong_Kong')


def timestamp(value):
    """Parse a catalogue departure without relying on the machine timezone."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        import math
        if not math.isfinite(value):
            raise ValueError('Flight departure must be a finite timestamp')
        return float(value)
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError('Flight departure must include an explicit timezone')
    return parsed.timestamp()


def iso_timestamp(value):
    return datetime.fromtimestamp(value, DISPLAY_TIMEZONE).isoformat() if value is not None else None


def as_of_timestamp(departure, day):
    return departure - (SALES_CUTOFF_SECONDS if day == 0 else day * DAY_SECONDS)


def require_observed(day, observed_through_day):
    if day < observed_through_day:
        gap = observed_through_day - day
        raise ValueError(f'D{day} has not been reached yet for this flight. Booking data runs to '
                         f'D{observed_through_day} (dataset cutoff); D{day} is {gap} day{"s" if gap != 1 else ""} beyond that cutoff.')


def catalogue_schedule(flight_id):
    """Resolver for runtime stores; isolated tests can supply their own schedule."""
    from . import data, data_horizon
    flight = next((row for row in data.flights() if row['flight_id'] == flight_id), None)
    if flight is None:
        raise NotFound('Unknown flight')
    return {'departure_at': flight['departure_at'],
            'observed_through_day': data_horizon.observed_through(flight_id)}


def schedule_time(schedule, day):
    if isinstance(day, bool) or not isinstance(day, int) or not 0 <= day <= 28:
        raise ValueError('Simulation day must be an integer from 0 to 28')
    observed = schedule['observed_through_day']
    require_observed(day, observed)
    departure = timestamp(schedule['departure_at'])
    return {'clock_version': VERSION, 'time_basis': 'flight_simulation',
            'departure_at': iso_timestamp(departure),
            'simulation_as_of': iso_timestamp(as_of_timestamp(departure, day)),
            'sales_cutoff_at': iso_timestamp(departure - SALES_CUTOFF_SECONDS),
            'observed_through_day': observed,
            'membership_time_basis': 'real_time'}


def catalogue_time(flight_id, day):
    return schedule_time(catalogue_schedule(flight_id), day)

"""How far each flight's published booking data reaches.

Synthetic catalogues carry complete D180..D0 histories, so every day is
observable. A truncated feed ends at its dataset cutoff; later release rounds
have not been observed and must not be forecast, published or priced. Wall-clock
time passing does not extend that frozen observation window.

Kept apart from backend/data.py so the loader, and the demand-index
fingerprint that hashes it, stay unchanged.
"""
from . import data


def observed_through(flight_id):
    """Days to departure of the latest published snapshot (0 for complete histories)."""
    return min(row['days_to_departure'] for row in data.history(flight_id))


def require_observed(flight_id, day):
    """Reject a view or release day that the flight's booking data has not reached yet.

    Unknown flights are left to the caller's own lookup (which raises NotFound)."""
    if flight_id not in data.histories():
        return None
    latest = observed_through(flight_id)
    if day < latest:
        gap = latest - day
        raise ValueError(f'D{day} has not been reached yet for this flight. Booking data runs to D{latest} (dataset cutoff); '
                         f'D{day} is {gap} day{"s" if gap != 1 else ""} beyond that cutoff.')
    return latest

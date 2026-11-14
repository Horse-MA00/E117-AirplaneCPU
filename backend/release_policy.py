"""Shared, auditable quota arithmetic for the three scheduled release rounds."""
import math

VERSION = 'three-round-release-v1'
RELEASE_DAYS = (28, 14, 7)


def release_budget(available, protection, outstanding, release_fraction=1.0):
    """Outstanding counts valid unsold quota only; sold seats are in occupancy.

    The fraction selects a TOTAL target, not an independent fresh allotment.
    Existing entitlements are retained if the target shrinks, but may be blocked
    from sale by physical capacity or protection until conditions permit.
    """
    for name, value in [('available', available), ('protection', protection), ('outstanding', outstanding)]:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise ValueError(f'{name} must be finite and nonnegative')
    if int(available) != available or int(outstanding) != outstanding:
        raise ValueError('Seat counts must be integers')
    if isinstance(release_fraction, bool) or not isinstance(release_fraction, (int, float)) or not math.isfinite(release_fraction) or not 0 <= release_fraction <= 1:
        raise ValueError('release_fraction must be finite in 0..1')
    safe = max(0, int(available) - math.ceil(protection))
    target = math.floor(safe * release_fraction)
    carry = int(outstanding)
    new = max(0, target - carry)
    return {'policy_rule_version': VERSION, 'safe_capacity': safe,
            'target_quota': target, 'prior_valid_unsold': carry,
            'new_allocation': new, 'remaining_quota': carry + new,
            'protection_shortfall': max(0, carry - safe)}

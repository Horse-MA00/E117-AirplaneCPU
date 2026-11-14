"""Whole-HKD quotes for the member discount product."""
import math
from decimal import Decimal, ROUND_FLOOR

MEMBER_FARE_CAP_RATIO = 0.8
PRICE_VERSION = 'whole-hkd-quotes-v1'


def integer_price(value, name='price', low=0, high=None):
    """Validate executable quotes; never silently change a submitted price."""
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or value != int(value) or value < low
            or (high is not None and value > high)):
        raise ValueError(f'{name} must be a whole HKD amount' + (f' in {low}..{high}' if high is not None else f' at least {low}'))
    return int(value)


def quoted_base_fare(observed):
    """Floor a source observation for a new quote; retain the observation separately."""
    if isinstance(observed, bool) or not isinstance(observed, (int, float)) or not math.isfinite(observed) or observed < 0:
        raise ValueError('A finite nonnegative observed base fare is required')
    return int(Decimal(str(observed)).to_integral_value(rounding=ROUND_FLOOR))


def member_fare_cap(normal_base_fare):
    """Highest whole-HKD member fare, at most 80% of the executable normal quote."""
    normal = quoted_base_fare(normal_base_fare)
    return int((Decimal(normal) * Decimal('0.8')).to_integral_value(rounding=ROUND_FLOOR))


def check_member_fare(fare, normal_base_fare):
    fare = integer_price(fare, 'Member base fare')
    normal = quoted_base_fare(normal_base_fare)
    cap = member_fare_cap(normal)
    if fare > cap:
        raise ValueError(f'Member base fare HK${fare:,} exceeds the cap of HK${cap:,} '
                         f'({MEMBER_FARE_CAP_RATIO:.0%} of the HK${normal:,} normal base fare)')
    return cap

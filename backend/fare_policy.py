"""Member fares are a discount product: never above half the normal base fare."""
import math

MEMBER_FARE_CAP_RATIO = 0.5


def member_fare_cap(normal_base_fare):
    """Highest allowed member base fare in HKD, rounded down to the cent."""
    value = float(normal_base_fare)
    if not math.isfinite(value) or value < 0:
        raise ValueError('A valid normal base fare is required to cap the member fare')
    return math.floor(round(value * MEMBER_FARE_CAP_RATIO * 100, 6)) / 100


def check_member_fare(fare, normal_base_fare):
    cap = member_fare_cap(normal_base_fare)
    if fare > cap:
        raise ValueError(f'Member base fare HK${fare:,.2f} exceeds the cap of HK${cap:,.2f} '
                         f'({MEMBER_FARE_CAP_RATIO:.0%} of the HK${float(normal_base_fare):,.2f} normal base fare)')
    return cap

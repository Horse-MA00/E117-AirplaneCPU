"""Explicit, conserving inventory presentation for an as-of forecast.

Forecast headroom is a risk bound. It is not a published offer and does not
override the three scheduled release days or the transactional quota ledger.
"""
import math

from .release_policy import RELEASE_DAYS


def describe(prediction, release, day):
    capacity = int(prediction['capacity'])
    normal = min(capacity, max(0, int(prediction['booked_seats'])))
    sold = max(0, int(release['member_sold']))
    member = min(capacity-normal, sold)
    occupied = normal+member
    physical = capacity-occupied
    protected = min(physical, max(0, math.ceil(prediction['protection_p90'])))
    surplus = physical-protected
    headroom = min(surplus, max(0, int(release['remaining_risk_ceiling'])))
    published = min(headroom, max(0, int(release['currently_bookable'])))
    unpublished = max(0, headroom-min(headroom, int(release['total_active_unsold'])))
    held_published = headroom-published-unpublished
    # Historical views can contain valid but currently unexecutable quota.
    held = physical-protected-published-unpublished
    new = min(unpublished, max(0, int(release['new_release_limit'])))
    next_day = release['next_release_day']
    if day == 0 or release.get('sales_cutoff_passed'):
        code, reason = 'sales_closed', 'Sales are closed; no new member seats can be published.'
    elif release.get('historical_view'):
        code, reason = 'historical_view', 'This is an earlier snapshot. The published inventory has already advanced; this view cannot issue new seats.'
    elif day not in RELEASE_DAYS:
        future = f' Next release round: D{next_day}; its allocation will be recalculated then.' if next_day is not None else ' No scheduled release rounds remain.'
        code, reason = 'not_release_day', f'{headroom} seats of forecast headroom, but D{day} is not a release day.'+future
    elif release['round_already_issued']:
        code, reason = 'round_already_issued', f'D{day} has already been published. {published} published member seats are currently bookable.'
    elif physical == 0:
        code, reason = 'no_physical_seats', 'All physical seats are occupied; no additional member seats can be issued.'
    elif headroom == 0 and prediction['releasable_seats'] > 0 and sold:
        code, reason = 'member_sales_consume_headroom', 'Previously sold member seats have used the current forecast headroom.'
    elif headroom == 0 and surplus == 0:
        code, reason = 'normal_demand_protected', f'All {physical} remaining seats are protected for normal demand under the current forecast.'
    elif headroom == 0:
        code, reason = 'data_quality_hold', 'The forecast holds the remaining space because its data-quality checks do not permit a release.'
    elif new == 0:
        code, reason = 'published_quota_covers_headroom', f'Existing valid quota already covers the {headroom}-seat forecast headroom. {published} published seats are currently bookable.'
    else:
        code, reason = 'available', f'{new} new seats may be published at D{day}, after deducting sold member seats and existing valid unsold quota.'
    return {'capacity':capacity, 'normal_booked':normal, 'member_booked':member,
            'confirmed_member_bookings':sold, 'reported_occupied':normal+sold,
            'occupied':occupied, 'physical_available':physical, 'normal_protected':protected,
            'member_headroom':headroom, 'published_bookable':published,
            'unpublished_headroom':unpublished, 'held_seats':held,
            'held_published_headroom':held_published,
            'new_releasable_today':new, 'next_release_day':next_day,
            'release_state':code, 'release_reason':reason,
            'member_inventory_overage':max(0,sold-member)}

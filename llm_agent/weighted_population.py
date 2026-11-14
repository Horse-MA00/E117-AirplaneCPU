"""Stratified, assumed audiences for a flexible, bargain-led membership offer.

The default is a deliberately targeted product audience, not an estimate of all
HK Express passengers. The original broad-coverage generator remains available
for reproducing historical experiments. Weights never mint physical seats.
"""
from __future__ import annotations

from collections import Counter
import math
import random

from .population import SEGMENTS as LEGACY_SEGMENTS

VERSION = "weighted-member-panel-v2-flexible"
DEFAULT_PROFILE = "flexible_deal_seekers"
LEGACY_PROFILE = "broad_coverage"
# key, label, assumed share, typical trips, basic-fare budget range, flexible days
SEGMENTS = [
    ("student", "Flexible university student", .24, 3, (160, 480), (14, 35)),
    ("destination_agnostic", "Destination-agnostic deal hunter", .20, 5, (220, 650), (21, 45)),
    ("spontaneous_solo", "Spontaneous solo short-break traveller", .16, 3, (180, 600), (7, 28)),
    ("frequent_bargain", "Frequent budget travel enthusiast", .12, 6, (260, 850), (14, 35)),
    ("flexible_weekday", "Flexible midweek bargain traveller", .10, 4, (200, 700), (14, 42)),
    ("flexible_friends", "Flexible friends planning a cheap escape", .08, 3, (200, 650), (14, 35)),
    ("flexible_couple", "Flexible couple seeking a cheap short break", .06, 3, (240, 750), (14, 35)),
    ("deal_only_occasional", "Deal-triggered occasional traveller", .04, 1, (180, 600), (21, 45)),
]
DEFAULT_WEIGHTS = {row[0]: row[2] for row in SEGMENTS}
LEGACY_WEIGHTS = {row[0]: row[2] for row in LEGACY_SEGMENTS}
SCENARIOS = {
    "student": {
        "trigger": "Browsing cheap flights during an open university break; no trip is booked and there is no exam or compulsory journey on the selected date.",
        "value": "Disposable cash is limited. A standout basic fare can turn a casual idea into a trip, but being able to pay is not a reason to spend the entire ticket budget.",
        "outside": "Skip this optional break and keep the ticket money for a later leisure opportunity.",
    },
    "destination_agnostic": {
        "trigger": "Browsing the route network without choosing a destination; an unusually attractive basic fare is the reason to consider travelling at all.",
        "value": "The destination is interchangeable. Compare the ticket's appeal with keeping the money, not with a need to reach this particular city.",
        "outside": "Make no booking now and stay open to another destination later; no cheaper future fare is guaranteed.",
    },
    "spontaneous_solo": {
        "trigger": "An unexpected pocket of free time makes a solo short break possible; a cheap flight advertisement started the search.",
        "value": "The traveller likes spontaneity and can adapt plans, but a small discount alone need not make an unplanned trip worthwhile.",
        "outside": "Stay home this time and keep the money; there is no obligation to travel.",
    },
    "frequent_bargain": {
        "trigger": "Enjoys many short leisure trips and checks offers regularly; this would be an additional optional trip, not a previously committed journey.",
        "value": "A good basic fare makes frequent travel possible. There is enthusiasm for travelling, alongside a habit of passing over offers that do not feel like good value.",
        "outside": "Save the ticket money for a different optional trip rather than adding this one.",
    },
    "flexible_weekday": {
        "trigger": "Can move leisure time to a weekday within a broad window and is browsing for a bargain rather than meeting a fixed appointment.",
        "value": "Willing to accept an inconvenient flight time for a genuinely attractive basic fare; schedule flexibility does not imply willingness to pay any affordable fare.",
        "outside": "Use the free time locally and leave the travel plan undecided.",
    },
    "flexible_friends": {
        "trigger": "Friends have agreed to be flexible about dates and destination if a cheap escape appears; nobody is obliged to make the trip.",
        "value": "The group enjoys bargain-led trips and can use this departure. This member chooses and pays only for their own ticket; a weak deal can still be declined.",
        "outside": "Suggest another leisure outing or save for a later trip; do not invent a quoted alternative fare.",
    },
    "flexible_couple": {
        "trigger": "A couple is casually browsing flexible dates and destinations for a low-price break, with no anniversary, event, or fixed-date commitment.",
        "value": "Both can use this departure and fund their tickets separately. This member values a cheap shared experience but is comfortable skipping an unconvincing offer.",
        "outside": "Postpone the optional break and keep this member's ticket money.",
    },
    "deal_only_occasional": {
        "trigger": "Does not normally plan frequent air travel; seeing a striking bargain can create interest in an otherwise unplanned leisure trip.",
        "value": "Has enough cash for some flights but little intention to fly without a compelling deal. Affordability is a ceiling, not a promise to buy.",
        "outside": "Do not travel and retain the money; no immediate replacement flight is needed.",
    },
}
SOURCES = [
    {"title": "Cathay Pacific Annual Report 2025 — HK Express operations",
     "url": "https://www1.hkexnews.hk/listedco/listconews/sehk/2026/0409/2026040901998.pdf",
     "supports": "Low-cost leisure positioning, Asian destinations and aggregate passenger statistics; not the assumed target-segment weights."},
    {"title": "Cathay Group December 2025 traffic figures",
     "url": "https://news.cathaypacific.com/the-cathay-group-releases-traffic-figures-for-december-2025-276edb",
     "supports": "Aggregate HK Express passenger counts and load factors; no matching membership conversion or segment-share table."},
]


def _segments(profile):
    if profile == DEFAULT_PROFILE:
        return SEGMENTS
    if profile == LEGACY_PROFILE:
        return LEGACY_SEGMENTS
    raise ValueError(f"Unknown customer profile: {profile!r}")


def validate_weights(weights=None, profile=DEFAULT_PROFILE):
    defaults = {row[0]: row[2] for row in _segments(profile)}
    weights = dict(defaults if weights is None else weights)
    if set(weights) != set(defaults):
        raise ValueError(f"Weights must specify all {len(defaults)} customer segments for {profile}")
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0
           for v in weights.values()):
        raise ValueError("Segment weights must be finite and nonnegative")
    if not math.isclose(sum(weights.values()), 1., abs_tol=1e-8):
        raise ValueError("Segment weights must sum to 1")
    return {key: float(weights[key]) for key in defaults}


def allocate(count, weights=None, profile=DEFAULT_PROFILE):
    """One per positive stratum, then Hamilton allocation of remaining slots."""
    weights = validate_weights(weights, profile)
    positive = [key for key, value in weights.items() if value > 0]
    if isinstance(count, bool) or not isinstance(count, int) or not len(positive) <= count <= 10000:
        raise ValueError(f"Panel size must be {len(positive)}..10000 to cover all positive-weight segments")
    remainder = count - len(positive)
    ideal = {key: remainder * weights[key] for key in positive}
    counts = {key: (1 + math.floor(ideal[key]) if key in ideal else 0) for key in weights}
    remaining = count - sum(counts.values())
    ranked = sorted(positive, key=lambda key: (-(ideal[key] - math.floor(ideal[key])), key))
    for key in ranked[:remaining]:
        counts[key] += 1
    return counts


def _legacy_population(count=28, seed=117, weights=None, scope=None):
    """Keep the v1 generation order and resulting people byte-for-byte reproducible."""
    weights = validate_weights(weights, LEGACY_PROFILE)
    counts = allocate(count, weights, LEGACY_PROFILE)
    scope = {} if scope is None else scope
    day = scope.get("as_of_day", 28)
    rng = random.Random(seed)
    people = []
    for key, label, _, trips, old_budget, flex in LEGACY_SEGMENTS:
        for _ in range(counts[key]):
            # A new, explicit ONE-ticket basic-fare budget; the old value was
            # a whole-travel budget and is only a scale assumption here.
            budget = round(old_budget * rng.uniform(.20, .72), 2)
            date_match = key != "no_match" and (flex > 1 or rng.random() < .85)
            notice = 21 if key == "access_needs" else 3
            companions = key not in ("family", "group", "couple") or rng.random() < .85
            eligible = date_match and companions and day >= notice
            reasons = []
            if not date_match:
                reasons.append("The selected route or departure date does not match this trip.")
            if not companions:
                reasons.append("Companions cannot confirm this departure; do not book separately.")
            if day < notice:
                reasons.append("The required booking notice for this trip has passed.")
            people.append({
                "customer_id": f"MEM-{seed}-{len(people)+1:05d}",
                "segment": key, "segment_label": label,
                "membership_active": True, "membership_valid_at_departure": True,
                "base_fare_budget": budget, "flexibility_days": flex,
                "expected_trips": trips, "minimum_notice_days": notice,
                "eligible": bool(eligible), "eligibility_reason": " ".join(reasons) or "This route and departure can be used.",
                "date_match": date_match, "companions_confirmed": companions,
                "party_size": 1, "own_ticket_only": True,
                "travel_party_context": "Companions arrange and fund their own tickets; this decision covers one existing member only.",
                "population_weight": weights[key] / counts[key],
                "target_segment_weight": weights[key], "sample_segment_count": counts[key],
                "source": "assumed_weighted_customer_scenario",
                "response_language": "en", "currency": "HKD",
            })
    # Do not let segment order determine who receives scarce inventory first.
    rng.shuffle(people)
    return people


def population(count=28, seed=117, weights=None, scope=None, profile=DEFAULT_PROFILE):
    if profile == LEGACY_PROFILE:
        return _legacy_population(count, seed, weights, scope)
    weights = validate_weights(weights, profile)
    counts = allocate(count, weights, profile)
    day = (scope or {}).get("as_of_day", 28)
    rng = random.Random(seed)
    people = []
    for key, label, _, trips, budget_range, flex_range in SEGMENTS:
        scenario = SCENARIOS[key]
        for _ in range(counts[key]):
            # Draw person traits before viewing any candidate price. No hidden
            # scalar willingness-to-pay threshold or prescribed buy rate exists.
            budget = round(rng.uniform(*budget_range), 2)
            flex = rng.randint(*flex_range)
            notice = rng.choice((1, 2, 3, 5, 7))
            eligible = day >= notice
            intensity = rng.choice(("very_high", "very_high", "high"))
            people.append({
                "customer_id": f"DEAL-{seed}-{len(people)+1:05d}",
                "segment": key, "segment_label": label,
                "scenario_profile": DEFAULT_PROFILE,
                "membership_active": True, "membership_valid_at_departure": True,
                "base_fare_budget": budget, "flexibility_days": flex,
                "expected_trips": trips, "minimum_notice_days": notice,
                "eligible": eligible,
                "eligibility_reason": ("This optional leisure departure fits the flexible travel window."
                                       if eligible else "This departure is too soon for the traveller to arrange the optional break."),
                "date_match": True, "companions_confirmed": True,
                "party_size": 1, "own_ticket_only": True,
                "travel_party_context": "Any companions can use this departure and independently arrange and fund their own tickets; this decision covers one existing member only.",
                "trip_purpose": "optional_leisure",
                "booking_trigger": scenario["trigger"],
                "trip_commitment": "not_planned_until_a_compelling_offer",
                "destination_openness": "any_served_destination",
                "travel_window_days": flex,
                "departure_time_tolerance": "Can adapt to the displayed departure time for a worthwhile deal; no fixed appointment requires this flight.",
                "price_sensitivity": intensity,
                "value_context": scenario["value"],
                "outside_option": scenario["outside"],
                "population_weight": weights[key] / counts[key],
                "target_segment_weight": weights[key], "sample_segment_count": counts[key],
                "source": "assumed_targeted_flexible_deal_seeker_scenario",
                "response_language": "en", "currency": "HKD",
            })
    rng.shuffle(people)
    return people


def metadata(weights=None, people=None, profile=DEFAULT_PROFILE):
    segments = _segments(profile)
    weights = validate_weights(weights, profile)
    counts = Counter(p["segment"] for p in people or [])
    return {
        "version": VERSION, "source": "project_test_mixture_not_observed_hkexpress_shares",
        "profile": profile,
        "profile_name": ("Flexible, price-sensitive deal seekers" if profile == DEFAULT_PROFILE
                         else "Historical broad customer coverage"),
        "available_profiles": [
            {"id": DEFAULT_PROFILE, "name": "Flexible, price-sensitive deal seekers", "segment_count": len(SEGMENTS)},
            {"id": LEGACY_PROFILE, "name": "Historical broad customer coverage", "segment_count": len(LEGACY_SEGMENTS)},
        ],
        "segments": [{"id": key, "name": label, "weight": weights[key], "assumed_weight": weights[key],
                      "sample_count": counts.get(key, 0),
                      "sample_share": counts.get(key, 0)/len(people) if people else None}
                     for key, label, *_ in segments],
        "allocation": "At least one per positive stratum, then largest remainder; individual estimate weight = target segment share / stratum sample count.",
        "sources": SOURCES,
        "limitations": [
            "The reviewed official reports do not publish these customer distributions; all numerical segment weights and budget distributions remain test assumptions.",
            ("This is a deliberately targeted audience for flexible bargain travel, not a representative sample of all HK Express passengers. Fixed-date mandatory, urgent and business travel are excluded."
             if profile == DEFAULT_PROFILE else "The historical broad profile preserves the v1 person generator, including fixed-date and mandatory-travel coverage cases."),
            "All sampled travellers are already valid members; no membership purchase, renewal, taxes, fuel fees or airline costs enter this experiment.",
            "Each sampled member decides about one personal ticket; companions' purchases are outside this experiment.",
            "Poststratified rates and expected revenue are estimates. Accepted ticket counts and cash revenue remain integer transactions in the cleared panel.",
            "An LLM persona is not an independent observed HK Express customer; repeated choices do not create additional people.",
        ],
    }

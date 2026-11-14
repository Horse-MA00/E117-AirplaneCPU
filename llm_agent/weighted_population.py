"""Stratified, explicitly assumed HK Express customer test scenarios.

The weights are the project's existing test mixture, not measured demographic
shares. Poststratification weights describe estimates; they never mint seats.
"""
from __future__ import annotations

from collections import Counter
import math
import random

from .population import SEGMENTS

VERSION = "weighted-member-panel-v1"
DEFAULT_WEIGHTS = {row[0]: row[2] for row in SEGMENTS}
SOURCES = [
    {"title": "Cathay Pacific Annual Report 2025 — HK Express operations",
     "url": "https://www1.hkexnews.hk/listedco/listconews/sehk/2026/0409/2026040901998.pdf",
     "supports": "Low-cost leisure positioning, Asian destinations and aggregate passenger statistics; not the 14 segment weights."},
    {"title": "Cathay Group December 2025 traffic figures",
     "url": "https://news.cathaypacific.com/the-cathay-group-releases-traffic-figures-for-december-2025-276edb",
     "supports": "Aggregate HK Express passenger counts and load factors; no matching membership conversion or segment-share table."},
]


def validate_weights(weights=None):
    weights = dict(DEFAULT_WEIGHTS if weights is None else weights)
    if set(weights) != set(DEFAULT_WEIGHTS):
        raise ValueError("Weights must specify all 14 known customer segments")
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0
           for v in weights.values()):
        raise ValueError("Segment weights must be finite and nonnegative")
    if not math.isclose(sum(weights.values()), 1., abs_tol=1e-8):
        raise ValueError("Segment weights must sum to 1")
    return {key: float(weights[key]) for key in DEFAULT_WEIGHTS}


def allocate(count, weights=None):
    """One per positive stratum, then Hamilton allocation of remaining slots."""
    weights = validate_weights(weights)
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


def population(count=28, seed=117, weights=None, scope=None):
    weights = validate_weights(weights)
    counts = allocate(count, weights)
    scope = {} if scope is None else scope
    day = scope.get("as_of_day", 28)
    rng = random.Random(seed)
    people = []
    for key, label, _, trips, old_budget, flex in SEGMENTS:
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


def metadata(weights=None, people=None):
    weights = validate_weights(weights)
    counts = Counter(p["segment"] for p in people or [])
    return {
        "version": VERSION, "source": "project_test_mixture_not_observed_hkexpress_shares",
        "segments": [{"id": key, "name": label, "weight": weights[key], "assumed_weight": weights[key],
                      "sample_count": counts.get(key, 0),
                      "sample_share": counts.get(key, 0)/len(people) if people else None}
                     for key, label, *_ in SEGMENTS],
        "allocation": "At least one per positive stratum, then largest remainder; individual estimate weight = target segment share / stratum sample count.",
        "sources": SOURCES,
        "limitations": [
            "The reviewed official reports do not publish this 14-segment customer distribution; all numerical segment weights and budget distributions remain test assumptions.",
            "All sampled travellers are already valid members; no membership purchase, renewal, taxes, fuel fees or airline costs enter this experiment.",
            "Each sampled member decides about one personal ticket. Family/group context is retained, but companions' purchases are outside this experiment.",
            "Poststratified rates and expected revenue are estimates. Accepted ticket counts and cash revenue remain integer transactions in the cleared panel.",
            "An LLM persona is not an independent observed HK Express customer; repeated choices do not create additional people.",
        ],
    }

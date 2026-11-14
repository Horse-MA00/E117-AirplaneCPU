# Joint price and seat-feedback experiments

**Historical whole-term engine specification.** The primary Admin now uses `flight-policy-feedback-v2`: selected flight/date, dataset P₀, fixed editable V₀, single-flight replay and automatic bounded live batches. See [the current contract](FLIGHT_SCOPED_OPTIMIZATION.md). The v1 behavior below remains available only for legacy experiments and reference tools.

Implemented 2026-11-14. Engine: `joint-policy-feedback-v1`. This supersedes the
one-dimensional fare-only search as the primary Admin workflow; the earlier
continuous-search module and its evidence remain available as historical tools.

The experiment starts from an editable member basic fare `P₀` and membership fee
`V₀`. It runs the existing chronological shared market, observes actual simulated
choices and costs, proposes a new pair, and repeats for the requested number of
rounds. The mathematical and live-LLM paths have separate histories and separate
recommendations. Their results are alternative synthetic behavior assumptions,
not interchangeable observations of real people.

## What a round means

One round evaluates **one price pair per selected track** across the configured
training seeds. It is not a model training epoch and it is not a full price grid.
The first round evaluates the starting pair. Later rounds follow a bounded
feedback-guided pattern search. Prices are represented at HKD-cent resolution.

The search explores negative/positive moves along both fare and fee dimensions,
then diagonal moves, centered on the best already evaluated candidate. Its step
is one quarter of the configured interval, halving after each eight-direction
cycle. It skips duplicate price pairs and uses smaller moves at a boundary.
Candidates that meet the new-member-use requirement outrank candidates that do
not; within that group, higher paired incremental contribution wins. Exact ties
prefer lower membership fee then lower fare. A one-round run therefore measures
P₀/V₀ only; three or more rounds can evaluate changes to both dimensions.

The optional **Suggest starting prices from data** button reads one available
normal-base-fare quote per flight at D28 from the original synthetic dataset.
P₀ starts at 15% of their median. V₀ starts at the membership service cost plus
three assumed trips' positive passenger-cost shortfall, plus programme cost
allocated across 50% of the configured travellers. Both values respect the
configured price bounds. The 15%, three trips and 50% subscription are disclosed
initialisation assumptions, not fitted willingness-to-pay or a profitability
guarantee. No future quotes or LLM calls are used by this helper.

The search is deliberately derivative-free: seat exhaustion, whole-party
purchases, membership decisions and refunds make the objective discontinuous.
No optimal-price labels, price-elasticity truth or LLM gradients are required.
The result is the **best tested candidate**, not a certified global optimum.
Small configured intervals may exhaust their unique cent-valued pairs early.

The two tracks are:

| Track | Decision mechanism | What feedback changes |
| --- | --- | --- |
| `math` | Existing probabilistic utility law and keyed Gumbel choices | Next fare/fee pair and next run-local seat profile |
| `live` | Real provider responses through the existing validated English/HKD adapter | Next fare/fee pair and next run-local seat profile |

Both use the same finite shared inventory, budgets, party booking, cancellation,
membership lifetime, mandatory fees, ancillary costs and integer-cent ledger.
They begin with the same exogenous seeds and P₀/V₀. Each candidate has its own
fresh market; nobody carries an earlier candidate's purchases into a new price
policy. Within a candidate all travellers compete on one chronological timeline.
`both` executes the mathematical track first and then the live track; progress
explicitly reports `active_mode` and phase.

## Objective and safeguards

For each seed:

```
Δ contribution = candidate contribution − matched NO_OFFER contribution
```

Contribution includes newly collected membership fees, base fares and ancillary
revenue, less passenger, ancillary, membership-service and programme costs. It
excludes mandatory fees treated as pass-through and aircraft fixed costs. It is
not total airline net profit. Background normal demand is generated independently
of the forecast. Matching is checked with the market's exogenous SHA-256.

A candidate is feasible only if every search replay has at least one newly paid
member and at least the configured fraction of those members complete a member
trip. This is a usage measure, not a per-request booking success rate. Zero
members cannot pass the requirement by having an empty denominator.

After the search, the strongest candidate is frozen and evaluated on two fresh
seeds (`seed + 50003` and `seed + 50104`). Search seeds use `seed + i × 101`;
validation seeds never select a replacement candidate. A track recommends OFFER
only when **both search and holdout** meet service requirements and have positive
mean incremental contribution. Otherwise it recommends NO_OFFER, while preserving
the strongest tested hypothesis for diagnosis. An unfinished track is PENDING.
A standard error is null when there is only one search replay.

## Seat prediction feedback

The base NHPP v2 model and frozen calibration files are not retrained or rewritten.
The new `backend/seat_feedback.py` adds a versioned per-run calibration layer:

1. After a training world has completely finished, collect per-flight D28/D14/D7
   forecast residuals. Background request events include denied requests. Add
   accepted foreground normal-ticket seats; these are a lower bound on foreground
   demand, since an unavailable option does not reveal a traveller's intent.
2. Exclude member seats and LLM reasons from normal-demand labels.
3. Shrink mean-rate corrections toward the base forecast; bound the rate factor
   to 0.5–2.0. Estimate nonnegative extra protection from positive residuals with
   sample-size shrinkage. Preserve all base NHPP fail-closed gates.
4. Apply the new profile only to the **next** search iteration. Replayed seeds
   retain the same sample IDs; repeats are not claimed as additional independent
   flight evidence.
5. Store the exact evaluated `seat_calibration`, the generated
   `next_seat_calibration`, and forecast diagnostic metrics with every round.
6. Holdout freezes the selected candidate's evaluated profile, not the latest
   profile. Holdout outcomes never update it.

The optimized policy is therefore jointly `(P, V, seat profile)`; a revenue change
cannot be attributed solely to a price change. A profile can only add to the
frozen seat-protection reserve. Correcting expected demand does not guarantee
better holdout accuracy or real airline calibration. The report retains base
and adjusted MAE/coverage so a deterioration remains visible.

The vacancy mean and occupancy curves retain the base NHPP Monte Carlo result.
The correction changes normal-demand means and protection; it does not pretend
that unconstrained demand changes translate linearly into empty seats. Coverage
compares base and adjusted forecast reserves consistently, excluding unrelated
fail-closed inventory gates.

## Persistence and audit

SQLite database: `data/private/optimization/experiments.sqlite3` (ignored by Git).
The schema uses WAL, foreign keys and parameterized statements.

| Table | Stored data |
| --- | --- |
| `optimization_runs` | Configuration, status, counters, progress, source/prompt hashes and provider identity hash |
| `optimization_worlds` | Track, phase, round, seed, exact policy, resumable market state and complete accounting result |
| `optimization_rounds` | Evaluated pair, score, service, incumbent, exact seat profile and next profile |
| `optimization_events` | Original redacted LLM requests/responses, mathematical choice probabilities, accepted actions, financial changes and round/holdout events |

Accepted actions and the resulting world state commit together in one SQL
transaction. Original model-output records are stored before applying a decision;
failed JSON or illegal choices never become a hidden mathematical fallback.
A response recorded just before a process interruption may appear again as a
cache replay, but the committed market state prevents double charging a purchase.
Provider records and cache replays retain separate provenance.

Each non-forced live attempt reserves one durable budget slot before transport.
The batch limit includes cached responses; forced single-option actions consume
no live slot. The worker pauses on exhaustion and only explicit Resume starts
another bounded batch. `provider_calls` counts provider-marked successful/failed
attempts whose output/failure reached the audit; `live_attempts` is the conservative
reserved count. An interrupted in-flight network call may have no confirmed
response record, so these counts are intentionally distinct. No automatic retry
loop spends beyond the configured batch.

A process lock and thread guard prevent concurrent optimizer writers. Restarted
jobs remain interrupted until explicitly resumed. Source, prompt, base calibration
and provider identity must match the frozen provenance; a changed implementation
requires a new experiment. Credentials are never stored in the database. Actual
provider text is passed through the existing secret redactor.

## HTTP contract

```
POST /api/optimization/runs
POST /api/optimization/initial-policy
GET  /api/optimization/runs
GET  /api/optimization/runs/{id}
POST /api/optimization/runs/{id}/resume
GET  /api/optimization/runs/{id}/events?limit=100&offset=0
GET  /api/optimization/runs/{id}/export
```

Creation body example (no provider calls):

```json
{
  "mode": "math",
  "rounds": 5,
  "initial_member_fare": 70,
  "initial_membership_fee": 399,
  "fare_min": 0,
  "fare_max": 500,
  "fee_min": 0,
  "fee_max": 1500,
  "release_fraction": 0.5,
  "customers": 14,
  "flights": 6,
  "replicates": 1,
  "seed": 117,
  "min_service_rate": 0.6,
  "program_cost": 1500,
  "max_calls": 60
}
```

`mode` is math/live/both; rounds 1–12, customers 1–100, flights 6–12, replicates
1–3, and max_calls 0–120 per batch. All numeric inputs must be finite; boolean
numbers and inconsistent bounds are rejected before running a simulation. Live
mode requires a configured provider. `max_calls: 0` can create a live experiment
and pause before the first non-forced provider choice.

The report exposes `tracks[].rounds`, `tracks[].best`, `tracks[].validation`,
`tracks[].decision`, global progress and source counters. Paginated events expose
the original decision evidence; export includes per-world accounting and seat
feedback but does not embed private credentials or unredacted network headers.
Existing Customer panel and one-off shared-market reports are independent of
these optimization jobs.

The final **Use these prices** action copies fare/fee into an Admin publishing
draft. Published Client Portal inventory continues to use the selected flight's
base NHPP allocation; the experimental seat profile is not silently deployed.

## Validation completed

Meaningful regression tests in `backend/tests/test_optimization.py` cover:

- finite bounds and integer limits before side effects;
- both price dimensions moving in response to evaluated feedback;
- a real three-round mathematical market, paired worlds, accounting invariants,
  disjoint holdout and the frozen selected seat profile;
- a fake-provider contract test for bounded pause/resume, original-output
  persistence, no duplicate accepted event and no repeated membership charge;
- dispatched provider failures without hidden mathematical fallback;
- implementation/provenance changes blocking resume;
- service failure and unmatched exogenous worlds rejecting an attractive score.

The fake-provider test is a transport-free integration test, not evidence of
actual LLM behavior. Real provider experiments, if executed, must be reported
separately with their run ID, completed rounds, call counts and validation status.

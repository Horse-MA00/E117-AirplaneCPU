# Continuous member-fare optimisation

New branch method, 2026-11-14. Earlier fixed-tier results are historical evidence;
they do not validate the new behavioural assumptions. NHPP parameters, calibration
and frozen reports have not been retuned.

## Method

1. Fix membership fee, release share, and the existing additive D28/D14/D7 quota
   rules. Search the allowed member base-fare interval at HKD-cent resolution.
2. Replay each fare in the **same shared market engine** and the same exogenous
   worlds: membership, companions, availability, full prices, cancellations,
   party acceptance and budgets use the existing environment and cent ledger.
3. Stable hypothetical preferences define a probabilistic choice law. Quote
   utility is `3.2 - 3 * sensitivity * full_party_price / trip_budget - date_cost`;
   decline and waiting are outside alternatives. Subscription utility compares
   currently visible savings, expected opportunities, perceived availability and
   fee, subject to affordability. These coefficients are explicit assumptions.
4. Keyed Gumbel draws generate categorical choices. Keys use customer identity,
   event and option identity, never price/policy/objective or option ordering.
   Replaying an identical observation repeats its result; across users and events
   it is stochastic. Users retain budgets and bookings in the environment. The
   model never receives latent future demand or airline contribution.
5. The optimiser observes simulated whole-term contribution feedback. It samples
   endpoints, then refines intervals using observed scores plus a width exploration
   bonus. It **does not** require optimal-price labels or preset HKD30/70/100 tiers.
   It is bounded numerical search, not certified global optimisation or ML training.
6. Reject policies that fail the configured new-member-use requirement in any
   search replay; compare positive mean paired contribution to NO_OFFER. The
   service measure is new members completing at least one member trip, not request
   fulfilment. With no feasible positive candidate, choose NO_OFFER.
7. Freeze the strongest hypothesis and evaluate independent holdout worlds and
   high/low sensitivity stresses. Holdout results never select a replacement fare.
   `ready_for_review` also requires positive, feasible holdout results. Few worlds
   provide only limited evidence; standard error is null for one replay.

## Scope of "continuous"

Continuous refers to the searched **price domain**, not automatic real-time
repricing. Each evaluation uses a constant member-fare policy over its finite
catalogue. Re-running with updated assumptions recomputes the recommendation;
already confirmed orders are never changed. A state-dependent D28/D14/D7 price
controller, observed-customer learning, population calibration and renewal-demand
learning remain future work. Do not call synthetic choices human ground truth.

## Feedback and provenance

The JSON report includes search trace, fixed configuration, disjoint seed lists,
source hashes, stress results and holdout quote/choice probabilities, customer
state, actions and financial deltas. No provider calls are required. Quote-stage
non-purchases are retained, including options that were available. Eligibility
and missing-stock effects belong to the environment, not invented price refusals.
Report labels describe **incremental contribution**, excluding pass-through fees
and aircraft fixed costs. All finite catalogue and normal-demand exposure limits
of `SHARED_MARKET.md` still apply.

## Run

Mac, Windows and Linux (Docker Desktop / Engine with Compose 2.30+):

```sh
docker compose up --build -d --wait
```

See [Docker instructions](DOCKER.md). The larger customer panel retains POSIX
`fcntl`; use the Linux container on Windows. Native Mac/Linux development remains
available through the README commands.

Open Fast screening: the new panel searches a range; the original tier screener
below remains an explicitly labelled legacy comparison. Shared market offers
`probabilistic` alongside `deterministic` and bounded `live` modes.

```sh
python -m backend.continuous_pricing --output data/private/continuous_pricing/example.json --evaluations 11
python -m unittest discover -s backend/tests -v
```

Web: `POST /api/pricing/runs` creates a bounded background experiment, then
`GET /api/pricing/runs/{id}` reads progress, failures and the completed report.
Only one continuous job runs at once; polling never creates more work.

## Portability and validation

Source/JSON/prompt files have LF checkout rules so frozen source hashes are stable
on Windows. CSV retains CRLF and binary files remain binary. NHPP source semantics
and calibration are unchanged. Resumable experiments use a nonblocking portable
process lock. Market initialisation/import errors are handled inside the job's
failure-and-cleanup boundary. Historical experiment exports remain unchanged;
new experiments freeze the new user-model and locking implementation hashes.

## Executed evidence

The committed synthetic development example is in
`simulation/continuous_price_validation/`. It uses 11 adaptive evaluations,
search seeds 20261411/20261512, then untouched seeds 20311414/20311515.
The strongest feasible tested fare was HKD46.87 at fixed fee HKD399 and release
share 50%, with search incremental contribution -HKD1,729.91. NO_OFFER wins.
Holdout mean was +HKD718.22 but failed service requirements (45.24% mean use);
this did not replace the search decision. Sensitivity stresses also failed
service requirements. These are finite synthetic examples, not human validation.
The compressed feedback archive and report have checksums and implementation
hashes. No external model calls were made.

Validation: full backend regression, original simulator/data tests, legacy and
new continuous browser smoke (desktop/390px), JavaScript syntax and historical
artifact checks. The new smoke uses actual background jobs, shared accounting,
independent validation and feedback. Run `npm run test:continuous` in frontend
against the running server (`APP_URL`; `CHROMIUM_EXECUTABLE_PATH` if needed).

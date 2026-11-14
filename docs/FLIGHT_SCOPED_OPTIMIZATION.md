# Flight-specific Admin workflow

> 状态：现行 · 对应代码：`flight-policy-feedback-v7-cap80`、`fixed-seat-profile-local-fare-v1`、`formula-scan-v1`、`backend/fare_policy.py`、`nhpp-completed-market-feedback-v1`、`nhpp-d28-demand-catalog-v1`、`member-thompson-v2-replay`、`member-purchase-thompson-v1`、`weighted-member-panel-v1`、`adaptive-member-decisions-v1`

Current specification, updated 2026-11-14 for engine `flight-policy-feedback-v7-cap80` (`backend/optimization.py`) with price protocol `fixed-seat-profile-local-fare-v1`. This document is the single current contract for the selected-flight Admin workflow. Change records are preserved unchanged: the v2→v3 supply and evidence diagnosis in [member supply and evidence corrections](MEMBER_SUPPLY_CORRECTIONS_2026-11-14.md), and the v3→v4 demand filter, original-fare P₀ and economic scope in [demand filter and original fare](DEMAND_FILTER_AND_ORIGINAL_FARE.md). v5 capped member fares at 50% of the normal base fare (superseding the v4 original-fare P₀); v6 replaced the mathematical track's search with a formula scan plus a simulated fine grid. v7 changes the shared cap to 80% and adds the separate member-only Thompson experiment described below; v5/v6 reports retain their original settings. Release rounds and quota carry-over follow [the three-round release rule](THREE_ROUND_RELEASE.md). Previous v2/v3 experiments retain their original settings and evidence.

## What each screen does

Forecast seats and Optimize prices share a **Demand filter** (All / Low / Medium / High / Unclassified) based on the D28 NHPP forecast of final normal load: Low < 60%, Medium 60% to < 85%, High ≥ 85%. It is precomputed in `simulation/demand_catalog.json` (rebuild with `python scripts/build_demand_catalog.py`, then restart); a missing or provenance-mismatched entry shows Unclassified. The band is a browsing aid only: it does not enter the NHPP, customer behaviour or contribution, and Low does not guarantee releasable quota.

1. **Forecast seats:** select a route, dated flight and observation day. The catalog includes 222 supplemental flights: 74 directed HKG routes on 15, 18 and 21 May 2027. Forecasting reads only observations available at that day. The seat forecast, protection, member allocation and observed normal base-fare chart remain separate quantities. Four seat cards use distinct definitions (see [Seat measures](#seat-measures)): **NHPP recommended member seats** (the model's own output, `available_seats − protection_p90`, where protection is the P90 normal-demand reserve plus its safety allowance, before earlier rounds and sold member seats are deducted), **Forecast headroom**, **New seats releasable today** and **Published seats bookable now**; a zero value states its concrete reason and the next release day. On a release round where NHPP leaves no member headroom, the page shows an explicit "do not release" decision and disables pricing.
2. **Optimize prices:** explicitly choose route, departure/flight and D28, D14 or D7. The immutable scope records capacity, booked and empty seats, observed price, fees, history hash and selected time. `P₀` is read-only and equals the member fare cap, 80% of that snapshot's latest observable normal base fare (see below). The page shows the same "do not release" decision, and disables Start, when NHPP allows no member seat or the release share rounds the allowance down to zero. `V₀` is editable and fixed throughout this flight's search. The actual mathematical and LLM worlds contain this one selected flight rather than a generic six-flight catalog.
3. **Review outcomes:** each point plots tested member base fare against mean flight-attributed contribution. Point size shows purchasing households; details include tickets and margin. Highest tested profit, highest margin and most buyers are reported separately. A dashed line shows the matched no-offer contribution (`baseline_contribution`), with a green or red stem per price for the gain or loss; the rounds table shows the same value and the signed difference. The fixed pass fee is not repeated in the results. Purple mathematical and cyan live-LLM tracks are different behavioral assumptions. An independent validation must accept the selected candidate before it becomes a publishable suggestion.
4. **Manage offers:** select the route, flight/date and release round independently. Matching validated results appear above the fare and quantity fields. Applying a suggestion copies its price, current permissible quantity and experiment ID. Changing flight or round clears the old draft. Publishing rechecks the experiment binding, current inventory and the member fare cap: a base fare above 80% of the normal base fare visible at that release day is rejected.
5. **Client:** primary prices are base fares. A smaller line shows mandatory charges and the total payable. Checkout still verifies the complete amount; no charge is removed from the ledger.

## Supplemental observations and initial price

`simulation/network_generated/` contains 40,182 additional D180–D0 snapshots and separate truth. All 37 remote airports in the member catalog have both directions and three dates. The requested CTS scenario remains schedule-unconfirmed; HFE retains its announced status. These simulated dates do not assert actual airline schedules.

`simulation/member_demo_generated/` adds a further 222 flights / 40,182 snapshots on the same 74 directions and dates, with deliberately low (15 May), medium (18 May) and high-demand control (21 May) normal demand, so that member supply exists on many default flights. Low-supply directions are retained; a positive member allocation is never guaranteed. These are designed business scenarios, not HK Express vacancy distributions.

The served catalog now contains 1,549 flights and 280,364 daily observations. Original 200,000 observations and the extra 400,000 validation rows remain unchanged. The original CSV download still exports exactly 200,000 rows; `catalog_rows` describes the expanded served catalog. Total stored simulation observations are 680,364.

**Member fare cap.** A member base fare never exceeds 80% of the normal base fare (`backend/fare_policy.py`, rounded down to the cent). New experiments start at the cap (`initial_policy.flight_scope`, `initial_fare_source = snapshot.normal_base_fare_x_member_cap`):

```
cap = floor(0.8 × latest observable normal_base_fare × 100) / 100
P₀  = cap;  fare_max = min(requested fare_max, cap)
```

Base fares exclude mandatory charges. P₀ is only the first tested candidate, not a recommended member fare or a willingness-to-pay estimate. A wider requested `fare_max` is narrowed to the cap; a narrower one must still contain P₀. The same cap filters the legacy pricing grid and is enforced again by `POST /api/offers`. The v4 rule (P₀ = full normal fare, ceiling `max(500, P₀)`) is superseded. The older `member_initial_base_fare = 0.15 × normal_base_fare` column and historical P₀ values (e.g. P84) are kept only for reproducing v2/v3 records. A sold-out snapshot uses the last available **earlier** quote and records `quote_age_days`; a missing price is never interpreted as HK$0. Spoofing P₀ in a request cannot override the data-derived value. User-selected search bounds must contain it.

## Adaptive member-only pricing

The separate `/adaptive-pricing` Admin page implements `member-thompson-v2-replay`. It is deliberately a **single purchase occasion for already-valid members at one flight/release snapshot**. The existing contribution/annual-fee engine below remains a separate reference workflow. Both share the current 80% normal-base-fare cap. NHPP, its frozen calibration, the source datasets and historical prompts/evidence remain unchanged.

### Customer population and what is being purchased

`llm_agent/weighted_population.py` uses the project's 14 test segments. These are **assumed test weights**, not measured HK Express passenger shares:

| Test segment | Target weight |
|---|---:|
| Flexible budget | 13% |
| Student | 9% |
| Fixed leave | 14% |
| Frequent leisure | 10% |
| Family | 12% |
| Couple | 10% |
| Visiting friends/relatives | 8% |
| Urgent trip | 4% |
| Self-funded business | 4% |
| Inbound/cross-market | 5% |
| Small group | 3% |
| Assistance needs | 2% |
| Infrequent/first-time | 4% |
| No matching route/date | 2% |

The reviewed [Cathay annual report](https://www1.hkexnews.hk/listedco/listconews/sehk/2026/0409/2026040901998.pdf) and [traffic release](https://news.cathaypacific.com/the-cathay-group-releases-traffic-figures-for-december-2025-276edb) describe the airline and aggregate traffic; they do not establish these 14 numerical weights or member purchase probabilities. The UI accepts a complete nonnegative weight vector summing to one. Each positive segment receives one coverage slot; remaining panel slots use largest-remainder allocation. A respondent in segment g has estimation weight `w_g / n_g`. Reports retain target shares, actual sample counts and these individual weights.

Each respondent purchases **one personal seat**. Family/group context can prevent travel, but companions arrange their own tickets outside this experiment. Everyone is already a valid member. There is no joining, renewal, HK$399 deduction, fee sunk-cost argument, tax, fuel surcharge or airline operating cost. Per-ticket base-fare budgets are explicit synthetic assumptions derived from the old scenario budget scales, not inferred willingness to pay. Budget, route/date, notice and companion constraints are visible to the customer. Responses are English JSON with BUY_MEMBER, BUY_REGULAR or DECLINE and a conditional regular-ticket fallback if member inventory is exhausted.

### Learning and Thompson Sampling

`backend/thompson.py` fits a small regularized purchase-intent model:

```
q_i(p) = sigmoid(a + segment_intercept[g]
                 + c * log(base_budget_i / normal_fare)
                 + d * flexibility_i / 7
                 - softplus(b) * p / normal_fare)
```

`softplus(b)` keeps price sensitivity nonnegative. Known affordability/eligibility constraints set purchase probability to zero. Those deterministic failures remain in the audit but supply no unconstrained price-slope likelihood. Priors shrink segment effects; a local Gaussian Laplace approximation represents parameter uncertainty. This is an approximation to a **persona-cluster-tempered likelihood**, not an exact independent-person posterior: all repeated trials for one persona have total likelihood power at most one, with relative poststratification weights preserved. V2 additionally keeps only one search observation per person/price exposure, so identical cached replies cannot change learning weights. The model learns synthetic choices, not human ground truth.

Round 1 tests the observed cap P0. Each subsequent round draws **one joint parameter vector** and uses it for every evaluated price and customer. Numerical evaluation uses 201 points over `[0, cap]` plus known budget discontinuities; these are inexpensive model evaluations, not a schedule of LLM candidate probes. It maximizes the drawn curve's expected member ticket receipts. Independent sampling of a conversion rate at every price would break the shared curve and is not used.

For a target cohort of N independently sampled members, `q_bar = sum_i weight_i*q_i`, and the target count is approximated by `K ~ Binomial(N,q_bar)`. The optimizer computes `E[min(Q,K)]` exactly for this conditional count model. It does **not** substitute `min(Q,E[K])`. Quota Q is frozen from the selected NHPP snapshot. This weighted-iid target approximation is separate from the actual stratified panel's integer seat ledger.

At search end, posterior-averaged member revenue is evaluated only at **tested prices**. Among prices reaching the configurable fraction (default 95%) of the best predicted member receipts, select the one with most expected member purchasers. This fraction is a business preference. The recommendation is frozen before holdout; the last Thompson draw is not automatically the recommendation. A separate full-domain posterior curve is displayed for explanation, including untested prices clearly as model estimates.

The analysis LLM classifies customer explanations and cites customer IDs. Its text is a diagnostic hypothesis, not a second purchase observation, a numeric willingness-to-pay label, or an instruction to override the mathematical price selection.

### Parallelism, inventory and audit

The panel sees a single simultaneous quote. At most eight customer calls are in flight (default four); two configured key slots can be used round-robin. A thread-safe counter reserves each attempt before dispatch. Both slots share the one explicit run budget. The first provider/validation failure stops new dispatches; in-flight requests may complete. There is no automatic retry or substitute synthetic answer. Raw responses, validated actions, reasons, prompt/context hashes, latency, token usage and slot labels are saved; authentication values are redacted at both the audit and durable run boundaries.

Only after intentions return does the program clear transactions in a seeded order, independent of HTTP completion order. It checks budgets and eligibility, subtracts integer member quota and physical seats, and applies an explicitly requested fallback. No overbooking or fractional seat allocation is allowed. An unsuccessful allocation does not turn a previously expressed purchase intention into a no-demand training label. Each new price resets the original population, wallets and inventory.

Exact repeated requests reuse a run-local cache. Cached replies, forced actions, fresh calls and failures have separate counters. Repeated-price analysis is reused and marked `reused_no_new_observations`; it produces zero new fit rows. Such repeats are valid Thompson selections, but are not new customers or independent evidence. API/model output is persisted in the ignored `data/private/adaptive_pricing/experiments.sqlite3`; exports are sanitized, bounded and written only to new evidence directories.

### Revenue comparison and limits

Independent holdout cohorts use disjoint seeds and IDs. Initial price, frozen selected price and NO_OFFER reuse the same people and allocation priority within each holdout. Identical selected/initial policies reuse one evaluated outcome and are marked as such. Holdout actions never refit the model.

Reports retain actual panel member/regular purchasers and base-fare cash receipts, plus poststratified target-mix estimates. If no allocation is rationed, the verdict uses weighted total base-fare revenue against initial and NO_OFFER. Under binding capacity it uses the actual capacity-feasible panel ledger and labels that change of basis; reweighting rationed transactions is not a new capacity-feasible market simulation. Descriptive bootstrap intervals resample paired worlds, not individual cached calls; two or three worlds are weak evidence, not an airline confidence interval.

The **search objective is member ticket revenue**. The holdout separately tests total base receipts including normal-ticket substitution. Consequently, more member buyers need not mean more incremental revenue; a candidate can be rejected. This system does not claim to solve optimal annual fees, full-horizon dynamic airline revenue management or actual net profit. It does not revise the NHPP seat model from these member choices.

### Running and inspecting

```
python -m backend.server --port 8001
python scripts/run_adaptive_pricing.py --mode synthetic --rounds 10 --customers 28 --max-calls 0
python scripts/run_adaptive_pricing.py --mode live --rounds 10 --customers 28 --concurrency 4 --max-calls 600
python scripts/run_adaptive_pricing.py --export-run-id RUN_ID --output llm_agent/experiments/NEW_DIRECTORY
python scripts/benchmark_adaptive_pricing.py --help
```

Live CLI execution requires an explicit finite `--max-calls`; the server checks the full worst-case call budget before starting. With N rounds, M members and H holdout cohorts, the upper bound is `N*(M+1) + (1+3*H)*M`. Forced actions/cache reuse can make actual calls much lower. Provider setup uses the existing server environment (`LLM_API_URL`, `LLM_MODEL`, `LLM_API_KEY`) and optional `LLM_API_KEY_SECONDARY`; an explicitly configured ignored private key file can supply the second slot. The UI never receives key values. Run state survives reload; orphaned work is marked interrupted after a stale heartbeat and free process lock, with no automatic paid resume.

API: GET `/api/adaptive-pricing/status`, GET/POST `/api/adaptive-pricing/runs`, POST `/api/adaptive-pricing/scope`, and GET `/api/adaptive-pricing/runs/{id}` with `/events` or `/export`. The new page is an experimental Admin view; it does not automatically publish an offer or change the Client Portal's live demo inventory.

### Executed results — 14 November 2026

The result is mixed: Thompson exploration helped in the prescribed mathematical benchmark, but the live LLM experiments did **not** validate an improvement in revenue. Both negative live results are retained.

| Evidence | Initial / comparator | Thompson result | Interpretation |
|---|---:|---:|---|
| 80 offline cases, mean expected member receipts | Greedy MAP HK$1,655.08 | HK$1,730.38 | +4.55% versus the same response model without Thompson exploration |
| Offline mean numerical-oracle ratio | Greedy 85.80% | TS 89.77% | Best attainable under the declared synthetic response, not airline truth |
| Live v1, weighted mean total base receipts | Initial HK$5,319.07 at P=328 | HK$4,948.90 at P=244.35 | −6.96%; selected candidate rejected |
| Live v2, weighted mean total base receipts | Initial HK$3,903.20 at P=328 | HK$3,489.92 at P=251.98 | −10.59%; selected candidate rejected |

The [offline benchmark report](../llm_agent/experiments/thompson_math_benchmark_20261114_v2/report.json) covers 20 prespecified seeds × two response families (heterogeneous Logistic and a discontinuous reference-price rule) × two capacity regimes, with 28 search members, 10 rounds and independent 140-person weighted support for analytic holdout scoring. Thompson won 37 cases, tied 25 and lost 18 against greedy. In the Logistic/scarce-capacity group it was slightly worse on average. Those 80 cases reuse 20 seed panels across conditions and are not 80 independent customer samples. The original-cap baseline is deliberately poor in several synthetic scenarios, so its much larger lift is not the headline. V2 repeats the prespecified V1 benchmark after correcting repeated-exposure handling; it is a method correction, not a newly unseen test suite. Runtime: 76.19 seconds, zero provider calls.

Both live experiments used synthetic flight `NET-HKG-KMQ-20270518`, HKG→Komatsu, D28, observed normal basic fare HK$410 and cap HK$328. Neither run retrained on holdout. The [v1 report](../llm_agent/experiments/thompson_live_20261114_v1/report.json) used 10 rounds × 28 members and two independent validation cohorts. It made 294 fresh calls in 130.93 seconds, with 4 peak concurrent requests, 147 calls per key slot, zero cache hits and zero failures. Validation averaged 16.5 buyers at the starting fare versus 20.5 at the selected fare; lower revenue despite more buyers caused rejection. V1 preserves its original source hashes, before the later durable-output redaction and replay hardening.

The [final v2 report](../llm_agent/experiments/thompson_live_20261114_v2/report.json) used a new search seed `20261114`, disjoint holdout IDs, 7 rounds × 20 members and two holdout cohorts. The tested fares were `[328,251.98,251.98,292.70,251.98,251.98,251.98]`; the selected tested fare was HK$251.98. Runtime was **52.28 seconds**, with **115 fresh provider calls, 56 cache replays, 112 forced decisions, 3 analyst calls and 0 failures**. Peak concurrency was 4; the primary/secondary slots handled 58/57 calls. Across both runs, **409 fresh calls** were used, below the 600-call task limit; the remaining budget was not spent just to seek a favorable result. The smaller V2 panel and caching both affect runtime, so these runs are not a controlled speed comparison.

| Final v2 independent validation, mean over 2 panels | Initial P=328 | Selected P=251.98 | No member offer |
|---|---:|---:|---:|
| Actual panel buyers | 11.5 | 13.0 | 9.0 |
| Actual base receipts | HK$3,772.00 | HK$3,275.74 | HK$3,690.00 |
| Weighted target-mix base receipts | HK$3,903.20 | HK$3,489.92 | HK$3,731.00 |
| Weighted member purchase rate | 59.50% | 69.25% | 0% |

![Saved synthetic benchmark and final live comparison](assets/thompson-pricing-comparison.png)

The rejection concerns the selected candidate, not proof that all discounted fares or the membership business are unviable. The starting fare can outperform both the candidate and NO_OFFER. With only two holdout cohorts, these are descriptive outcomes, not reliable significance estimates.

### Review findings and next improvements

All ten V1 Thompson draws were distinct, but nine selected the same HK$244.35 budget boundary. This was not a broken random generator: the small, fixed population made that threshold attractive across many plausible curves. V2 avoids paying again for those exact requests and prevents them changing the distribution of training evidence. Actual sampling and proposal parameters remain recorded.

Customer validity checks revealed a substantive limitation: **all 31 unique affordable member choices in V1 and all 36 in V2 chose BUY_MEMBER**. The effective live response was close to “buy whenever the stated budget permits.” The training panel's budget threshold did not generalize to the fresh holdout budget distribution. More iterations over the same people cannot repair that. Recommended next work is to validate the scenario with real respondent choices, model uncertain budget distributions across fresh cohorts, and test outside options and travel value without inventing known willingness-to-pay labels. Maintain independent holdouts and preserve negative results.

The purchase learner currently supports a monotone smooth response plus known budget jumps. The discontinuous benchmark demonstrates remaining model mismatch. A future comparison can add a monotone nonparametric response model or hierarchical budget distribution, using a new calibration set and new final seeds. Search still optimizes member receipts rather than a multinomial model of total incremental receipts; any upgrade to that objective must learn ordinary-ticket substitution explicitly.

Verification completed: 290 backend tests and 31 publication/data/documentation tests; native `scripts/check_container.py`, frozen hashes and new evidence invariants passed. Browser smoke covers weights, budgets, empty inventory, raw-text safety, replay labels, adaptive curves, read-only reload and mobile layout. Both real live runs were inspected through the UI without additional POSTs. No main-branch merge, PR, OAG call or frozen NHPP change was made.

## Market and search

`initial_policy.flight_scope` truncates history at the selected release day and freezes its SHA-256. `scoped_market.create_scoped_market` copies only this flight, its true simulated departure clock, occupancy and as-of history into the shared chronological environment. Inbound routes preserve their direction.

Future normal demand is independently sampled: its level uses the last approximately 14 observed daily gross-booking counts, a Gamma multiplier, random growth and a possible persistent jump. It does not take NHPP expected demand as its future truth. Future synthetic normal quotes are replayed only when their scheduled event arrives; they do not enter the initial forecast or earlier traveller observations. This continuation is still an assumption, not real route-calibrated demand.

The existing probabilistic or live-LLM traveller chooses whether to join, buy, wait or cancel. The environment applies budgets, full quotes, party constraints, release rounds, inventory and cash accounting. Same-seed worlds pair the candidate with NO_OFFER.

**Supply gate.** Before an experiment is created, `floor(releasable_seats × release_fraction)` for the selected round must be at least one seat; otherwise the request is rejected with no experiment record and no provider call. If every completed replica still releases zero member seats, the run records `optimization_no_member_supply` and retains no price hypothesis.

**Fare search — mathematical track (`formula-scan-v1`).** V remains fixed. Before the run starts, `backend/fare_estimate.py` scores every member fare from `fare_min` to the cap at HK$1 steps (plus the cap itself). It builds the same simulated travellers as the search replays (same seeds) and uses the probabilistic customer model's logit utilities in expectation: join probability, member/regular purchase or wait at each remaining D28/D14/D7 round, member and normal base revenue, passenger cost and the attributed share of fee and service cost, compared with the same travellers without the offer. The highest expected incremental contribution is `P*` (ties go to the higher fare). This takes about 20 ms and is stored as `config.formula_estimate`. It ignores member quota, background demand, cancellations and seat rationing, so it is only a search aid.

The full simulation then evaluates `P*` (`search_step = formula_p_star`) and 8 nearby fares (`fine_grid`): step = (cap − fare_min)/32, alternating sides, clipped to the bounds; a bound within ±4 steps is always included. The *Rounds per model* input applies to the Live LLM track only. On five demo flights the formula P* matched the best fare of a 9-point coarse simulated grid; on one HK$830-fare flight simulation moved the best tested fare from P* HK$370 to HK$344.06 within the grid. A run on DEMO-ISG-HKG took about 13.5 s.

**Fare search — Live LLM track.** Unchanged: cent-resolution local search around P₀ with a 25% step; a zero P₀ uses 5% of the permitted span. It then tries named exploration points (`boundary_low`, `wide_upper`, `boundary_high`), followed by halving refinements around the best informative candidate. Prior tests are never rewritten.

**Fixed seat profile.** Within one price search and its independent validation, every candidate uses the same initial seat profile, so supply-rule changes cannot leak into the price comparison. Completed markets still compute a proposed next seat-feedback profile from normal-demand error, but it is only a proposal for a later experiment and is labelled as not applied. The selected candidate is checked on two independent seeds.

Seat-feedback semantics (`backend/seat_feedback.py`, `nhpp-completed-market-feedback-v1`; the frozen NHPP model and calibration are never rewritten):

- Labels exist only after a simulated world completes: future background normal requests (including capacity-denied requests) plus accepted foreground normal seats, companions included. Member seats and LLM explanations are excluded; unmet foreground intent is unobserved, so labels are not a full unconstrained demand curve.
- Per D28/D14/D7: `rate_scale = (Σ actual + 100) / (Σ base mean + 100)`, clipped to `[0.5, 2]` (the 100-count prior is an explicit shrinkage assumption); `extra_protection = min(400, ceil(p90_residual × n / (n + 20)))`, where residuals are nonnegative excesses over the base reserve. Base safety reserve and fail-closed gates stay.
- A repeated seed/flight/horizon is one training sample, not new independent evidence. Expected empty seats and occupancy curves keep the frozen base NHPP Monte Carlo result; the forecast page shows the base NHPP.

**Exposure.** Each candidate records seats actually released, member-offer exposures (packets and distinct customers) and bookable exposures. A candidate with no supply (`uninformative_no_supply`) or no member-offer exposure (`uninformative_no_member_exposure`) is excluded from best-price ranking and the price curve; normal-revenue and cancellation differences remain visible only as accounting outcomes. A price line connects informative evaluated outcomes; it is still a small-sample synthetic comparison, not a calibrated price-elasticity curve.

The engine recommends OFFER only if both search and independent validation meet the member-use constraint and show positive incremental contribution. Otherwise NO_OFFER remains the result. NO_OFFER is a decision for this selected flight only, not a verdict on the whole membership programme. A one-round experiment only evaluates P₀. More rounds explore more prices, without certifying a global optimum.

## Profit, margin and buyers

```
attributed revenue = normal/member base fares + ancillary revenue
                     + one third of newly paid annual pass revenue
attributed costs   = passenger + ancillary + programme costs
                     + one third of new-membership service costs
flight contribution = attributed revenue - attributed costs
margin = flight contribution / attributed revenue   (undefined at zero revenue)
incremental contribution = candidate - paired NO_OFFER
```

The actual full membership fee is charged once and remains in the cash ledger; the one-third allocation is only an explicit accounting assumption for this flight's comparison. Other annual trips are not replayed, so this cannot determine an optimal annual fee. The full per-run programme cost is retained. Mandatory charges are assumed pass-through; aircraft fixed costs and already-booked passengers' historical income are excluded. Therefore the chart is future flight contribution, not airline net profit. Sales of the selected flight from the snapshot through cutoff are simulated; the same members' later trips and paid renewals are not. Each scoped result therefore returns `economic_scope` with `membership_term_evaluated: false` and `future_member_trip_contribution` / `future_renewal_contribution` set to `null` (unknown, not zero). Whole-term profitability or an optimal annual fee cannot be derived from it.

Buyers count distinct simulated customer households with accepted bookings, including later cancellations; anonymous background demand and every person in a party are not separate buyers. Tickets count accepted party seats, including replacement bookings. Separate fulfilled-buyer/ticket fields count flown bookings; cancellation does not erase the original purchase decision. Member buyers, normal-fare buyers, new memberships, member and normal tickets, flown bookings and cancellations are reported separately. Member and normal buyers can overlap (a member's companions pay normal fares), so they must not be added as independent people. Each result also stores revenue and cost components and their differences from paired NO_OFFER. Highest contribution, highest margin and highest buyer count can occur at different prices; service feasibility and holdout acceptance still control the recommendation.

## Seat measures

`forecast.seat_inventory` is the single API decomposition used by Forecast cards and the seat bar: capacity, normal bookings, confirmed member bookings, physically available seats, protected seats, member risk headroom, bookable published quota, unpublished headroom and held quota. For a consistent snapshot the bar segments sum to capacity.

```
NHPP recommended     = available seats − (P90 normal-demand reserve + safety allowance)   [risk_release_ceiling]
forecast headroom   = space left after normal-demand protection and member seats already sold
new releasable today = on a D28/D14/D7 round only: target quota minus earlier still-valid unsold quota
published bookable   = min(published valid unsold quota, current risk headroom)
```

Headroom on a non-release day does not create new quota, but earlier valid quota remains bookable. Normal-demand forecast curves and expected empty seats are labelled as the normal-demand baseline, not total inventory including members. If a synthetic normal snapshot plus member sales exceeds capacity, the raw `confirmed_member_bookings` / `reported_occupied` values are kept and the conflict is reported rather than hidden by truncation. Historical or already-advanced views disable publishing and purchase rather than showing a non-existent next round.

## Persistence and API

SQLite database `data/private/optimization/experiments.sqlite3` (ignored by Git), with WAL, foreign keys and parameterized statements (`backend/optimization_store.py`):

| Table | Stored data |
| --- | --- |
| `optimization_runs` | Configuration, status, counters, progress, source/prompt hashes and provider identity hash |
| `optimization_worlds` | Track, phase, round, seed, exact policy, resumable market state and complete accounting result |
| `optimization_rounds` | Evaluated pair, score, service, incumbent, exact seat profile and next profile |
| `optimization_events` | Redacted original LLM requests/responses, mathematical choice probabilities, accepted actions, financial changes and round/holdout events |

Accepted actions and the resulting world state commit in one SQL transaction. Original model output is stored before a decision is applied; invalid JSON or illegal choices never become a hidden mathematical fallback. A response recorded just before an interruption may reappear as a cache replay, but committed market state prevents double charging. Each non-forced live attempt reserves a durable budget slot before transport; `provider_calls` (confirmed in the audit) and `live_attempts` (conservative reserved count) are intentionally distinct. A process lock and thread guard prevent concurrent optimizer writers; interrupted jobs stay interrupted until resumed. Source, prompt, calibration and provider identity must match the frozen provenance, otherwise resume is refused and a new experiment is required. Credentials are never stored; provider text passes through the secret redactor.

Seeds: search replay `i` uses `seed + i×101`; independent validation uses `seed + 50003` and `seed + 50104` (`_seeds` in `backend/optimization.py`).

```
POST /api/optimization/runs
POST /api/optimization/initial-policy
GET  /api/optimization/runs
GET  /api/optimization/runs/{id}
POST /api/optimization/runs/{id}/resume
GET  /api/optimization/runs/{id}/events?limit=100&offset=0
GET  /api/optimization/runs/{id}/export
GET  /api/optimization/suggestions?flight_id=...&forecast_day=28
```

The older whole-term joint P/V engine (`joint-policy-feedback-v1`) is reachable only with `legacy_market: true`, which only `backend/tests/test_optimization.py` uses; no UI sends it. Its completed experiments remain in `llm_agent/experiments/joint_*` and [joint optimization validation](JOINT_OPTIMIZATION_VALIDATION.md).

## Provenance

Each new experiment freezes SHA-256 hashes of the optimizer, market, NHPP source, `calibration_v2.json`, customer prompt/contract and the `network_generated` and `member_demo_generated` manifests. Missing provenance fails closed. Completed earlier records are not backfilled; see `MEMBER_DEMO_DATA_ATTESTATION_2026-11-14.json`.

## Bounded automatic live execution

An internal `max_calls` batch (1–120) no longer forces manual continuation for new scoped runs. The worker saves state and automatically begins another internal batch while `total_live_budget` remains. Default total is 1,500 decision attempts; the validated maximum is 10,000. Fresh calls and cache replays both consume attempt slots; forced actions do not require a call. Counters distinguish calls, cache, forced actions, math decisions and failures.

The worker stops on the overall cap or provider failure. The UI shows the overall limit, remaining progress and an explicit additional-budget control. `additional_live_budget` extends the total rather than silently overriding it. A zero-sized automatic batch is rejected, and a running experiment cannot have its budget mutated by resume. Provider errors are preserved, never replaced with fabricated mathematical answers. Historical unscoped runs preserve their older batch semantics.

## Publishing safety

`GET /api/optimization/suggestions?flight_id=...&forecast_day=28` searches completed, current-provenance experiments for the exact flight and round. The newest completed result in each track supersedes older results, including a newer NO_OFFER. Only independently validated OFFER results become suggestions.

The suggestion quantity is recalculated using the current base NHPP and demo ledger:

```
validated ceiling = min(base NHPP ceiling, ceiling with selected seat profile)
remaining ceiling = max(0, validated ceiling - live demo member seats sold)
target unsold = floor(remaining ceiling * optimized release fraction)
new seats = max(0, target unsold - earlier still-valid unsold quota)
```

The existing release transaction still enforces D28/D14/D7, round idempotency and physical capacity. The selected candidate’s frozen seat profile can only reduce the suggestion below base NHPP capacity; it does not change the global forecast model. Source run/mode bindings reject stale, cross-flight, cross-round or changed-price drafts. The published membership plan must equal the tested V₀; the UI asks the user to save it first, and the offer transaction rechecks it atomically. Manual drafts remain possible within the existing inventory limits.

## Reproduce checks

```sh
docker compose up --build -d --wait
docker compose --profile test run --rm tests
python3 scripts/smoke_scoped_admin.py --url http://127.0.0.1:8000
# Explicitly runs a small real provider check, bounded to 64 attempts:
python3 scripts/smoke_scoped_admin.py --url http://127.0.0.1:8000 --live
cd frontend
APP_URL=http://127.0.0.1:8000 npm run test:flight-offers
```

The HTTP smoke creates synthetic saved experiments but does not publish offers. Private SQLite files and credentials remain excluded from Git. See [iteration progress](ITERATION_2_PROGRESS.md) for the final test counts and real-call evidence from this implementation.

## Executed verification — 14 November 2026 (v2 engine, historical)

The results below were produced by `flight-policy-feedback-v2` and are preserved unchanged. v3 verification is recorded in [member supply and evidence corrections](MEMBER_SUPPLY_CORRECTIONS_2026-11-14.md#驗證).

- Docker on native Apple Silicon: **168 backend + 19 simulator tests**, all passed. All 22 dataset/experiment artifact groups verified after exporting the three new runs.
- **666 forecasts** across 222 flights and D28/D14/D7: finite demand and bounded release; 232 positive allocations and 434 zero allocations. This is an operational sanity check, not a new forecast-coverage claim. [Recorded check](validation/network_forecasts_20261114.json).
- Chrome desktop/mobile: scoped optimizer, member checkout, flight-offer bindings, existing Admin smoke and historical price chart passed. The suggestion fixture specifically tests saving the matching pass fee before publication and clearing a draft on flight change.
- Actual HTTP math: outbound HKG–HND on 18 May starts at P₀85.50 with 102 empty seats; inbound HND–HKG on 21 May starts at P₀117 with 54 empty seats. Three search rounds each, V99 fixed, eight completed worlds each, all inventory/accounting checks passed. Both independently rejected the selected offer.
- Actual DeepSeek: same outbound flight, one traveller, one candidate round, six baseline/search/holdout worlds. **21 fresh calls, zero cache hits, zero failures, 27 forced actions**. With an intentionally small two-decision internal batch, the worker automatically continued ten times and completed within the 64-attempt total budget. NO_OFFER: holdout incremental contribution was −HK$11.50 despite full member use. This tiny experiment verifies execution and evidence preservation, not real customer demand or a price optimum.

Saved evidence: [HTTP summary](validation/flight_scoped_http_20261114.json), [outbound math](../llm_agent/experiments/flight_hnd_outbound_math_20261114/report.json), [inbound math](../llm_agent/experiments/flight_hnd_inbound_math_20261114/report.json), [live report](../llm_agent/experiments/flight_hnd_live_20261114/report.json) and each directory's redacted `audit.jsonl.gz`. Historical failed/unaccepted hypotheses are retained rather than relabelled as profitable solutions.

Final local runtime: the updated Docker app now binds `127.0.0.1:8000`. Health, Admin, Client, 222 supplemental flights and the completed 21-call experiment were rechecked after container recreation; the named data volume was preserved.

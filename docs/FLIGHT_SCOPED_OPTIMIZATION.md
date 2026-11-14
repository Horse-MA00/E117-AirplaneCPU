# Flight-specific Admin workflow

> 状态：现行 · 对应代码：`flight-policy-feedback-v6-formula-grid`、`fixed-seat-profile-local-fare-v1`、`formula-scan-v1`、`backend/fare_policy.py`、`nhpp-completed-market-feedback-v1`、`nhpp-d28-demand-catalog-v1`、`backend/forecast.py`

Current specification, updated 2026-11-14 for engine `flight-policy-feedback-v6-formula-grid` (`backend/optimization.py`) with price protocol `fixed-seat-profile-local-fare-v1`. This document is the single current contract for the selected-flight Admin workflow. Change records are preserved unchanged: the v2→v3 supply and evidence diagnosis in [member supply and evidence corrections](MEMBER_SUPPLY_CORRECTIONS_2026-11-14.md), and the v3→v4 demand filter, original-fare P₀ and economic scope in [demand filter and original fare](DEMAND_FILTER_AND_ORIGINAL_FARE.md). v5 capped member fares at 50% of the normal base fare (superseding the v4 original-fare P₀); v6 replaced the mathematical track's search with a formula scan plus a simulated fine grid. Both are described below. Release rounds and quota carry-over follow [the three-round release rule](THREE_ROUND_RELEASE.md). Previous v2/v3 experiments retain their original settings and evidence.

## What each screen does

Forecast seats and Optimize prices share a **Demand filter** (All / Low / Medium / High / Unclassified) based on the D28 NHPP forecast of final normal load: Low < 60%, Medium 60% to < 85%, High ≥ 85%. It is precomputed in `simulation/demand_catalog.json` (rebuild with `python scripts/build_demand_catalog.py`, then restart); a missing or provenance-mismatched entry shows Unclassified. The band is a browsing aid only: it does not enter the NHPP, customer behaviour or contribution, and Low does not guarantee releasable quota.

1. **Forecast seats:** select a route, dated flight and observation day. The catalog includes 222 supplemental flights: 74 directed HKG routes on 15, 18 and 21 May 2027. Forecasting reads only observations available at that day. The seat forecast, protection, member allocation and observed normal base-fare chart remain separate quantities. Four seat cards use distinct definitions (see [Seat measures](#seat-measures)): **NHPP recommended member seats** (the model's own output, `available_seats − protection_p90`, where protection is the P90 normal-demand reserve plus its safety allowance, before earlier rounds and sold member seats are deducted), **Forecast headroom**, **New seats releasable today** and **Published seats bookable now**; a zero value states its concrete reason and the next release day. On a release round where NHPP leaves no member headroom, the page shows an explicit "do not release" decision and disables pricing. The lower round-breakdown/published-rounds panel, model-parameter/source-download footnote and Admin footer have been removed; the four seat cards, allocation chart and two forecast/price charts remain. Release accounting and export/status APIs are unchanged.
2. **Optimize prices:** explicitly choose route, departure/flight and D28, D14 or D7. The immutable scope records capacity, booked and empty seats, observed price, fees, history hash and selected time. `P₀` is derived by the server (no setup input) and equals the member fare cap, 50% of that snapshot's latest observable normal base fare (see below). The page shows the same "do not release" decision, and disables Start, when NHPP allows no member seat or the release share rounds the allowance down to zero. New flight-scoped runs always use `V₀ = HK$399`, enforced in both initial-policy and run creation even if the request supplies another fee. The setup shows only demand/route/flight/round, customer model and bounded live-decision controls. Removed experiment controls now use explicit frontend defaults: 6 Live LLM rounds, 14 travellers per market, 2 search markets, seed 117, 50% release share, 60% minimum new-member use and HK$0 programme overhead. The mathematical track keeps its formula plus fine-grid evaluations. Search bounds are server-derived from zero to the flight cap. Saved historical fees and legacy unscoped experiments retain their original values. The actual mathematical and LLM worlds contain this one selected flight rather than a generic six-flight catalog.
3. **Review outcomes:** each point plots tested member base fare against mean flight-attributed contribution. Point size shows purchasing households; details include tickets and margin. Highest tested profit, highest margin and most buyers are reported separately. A dashed line shows the matched no-offer contribution (`baseline_contribution`), with a green or red stem per price for the gain or loss; the rounds table shows the same value and the signed difference. The fixed pass fee is not repeated in the results. Purple mathematical and cyan live-LLM tracks are different behavioral assumptions. An independent validation must accept the selected candidate before it becomes a publishable suggestion.
4. **Manage offers:** select the route, flight/date and release round independently. Matching validated results appear automatically above the fare and quantity fields, and refresh when returning to Manage offers. If no result exists, an inline **Optimize this flight** link opens Optimize with that exact flight and release round selected and focuses its heading. Pending, failed, completed NO_OFFER and historical-provenance results have distinct read-only summaries; they cannot become publishable price suggestions. Applying a suggestion copies its price, current permissible quantity and experiment ID. Changing flight or round clears the old draft. Publishing rechecks the experiment binding, current inventory and the member fare cap: a base fare above 50% of the normal base fare visible at that release day is rejected.
5. **Client:** primary prices are base fares. A smaller line shows mandatory charges and the total payable. Checkout still verifies the complete amount; no charge is removed from the ledger.

## Supplemental observations and initial price

`simulation/network_generated/` contains 40,182 additional D180–D0 snapshots and separate truth. All 37 remote airports in the member catalog have both directions and three dates. The requested CTS scenario remains schedule-unconfirmed; HFE retains its announced status. These simulated dates do not assert actual airline schedules.

`simulation/member_demo_generated/` adds a further 222 flights / 40,182 snapshots on the same 74 directions and dates, with deliberately low (15 May), medium (18 May) and high-demand control (21 May) normal demand, so that member supply exists on many default flights. Low-supply directions are retained; a positive member allocation is never guaranteed. These are designed business scenarios, not HK Express vacancy distributions.

The served catalog now contains 1,549 flights and 280,364 daily observations. Original 200,000 observations and the extra 400,000 validation rows remain unchanged. The original CSV download still exports exactly 200,000 rows; `catalog_rows` describes the expanded served catalog. Total stored simulation observations are 680,364.

**Member fare cap.** A member base fare never exceeds 50% of the normal base fare (`backend/fare_policy.py`, rounded down to the cent). New experiments start at the cap (`initial_policy.flight_scope`, `initial_fare_source = snapshot.normal_base_fare_x_member_cap`):

```
cap = floor(0.5 × latest observable normal_base_fare × 100) / 100
P₀  = cap;  fare_max = min(requested fare_max, cap)
```

Base fares exclude mandatory charges. P₀ is only the first tested candidate, not a recommended member fare or a willingness-to-pay estimate. A wider requested `fare_max` is narrowed to the cap; a narrower one must still contain P₀. The same cap filters the legacy pricing grid and is enforced again by `POST /api/offers`. The v4 rule (P₀ = full normal fare, ceiling `max(500, P₀)`) is superseded. The older `member_initial_base_fare = 0.15 × normal_base_fare` column and historical P₀ values (e.g. P84) are kept only for reproducing v2/v3 records. A sold-out snapshot uses the last available **earlier** quote and records `quote_age_days`; a missing price is never interpreted as HK$0. Spoofing P₀ in a request cannot override the data-derived value. User-selected search bounds must contain it.

## Active normal demand forecast

当前预测统一经 `backend/forecast.py`：D28 使用冻结 v2 需求分布及新校准的 v2 安全余量；D14/D7 使用完整窗口与近期窗口混合的 v3 及新余量。D28 的平滑候选未通过独立测试的突增组收入门槛，因此未启用。历史 v2 模型及报告保留，详见 [NHPP 平滑与校准](NHPP_V3_REVIEW.md) 和 [路演说明](PITCHING_BRIEF.md)。

The active protection gate is selected per horizon from independent synthetic validation. The base distribution and guard stay fixed during each price comparison and its holdout; proposed seat-feedback updates remain next-run proposals only.

## Market and search

`initial_policy.flight_scope` truncates history at the selected release day and freezes its SHA-256. `scoped_market.create_scoped_market` copies only this flight, its true simulated departure clock, occupancy and as-of history into the shared chronological environment. Inbound routes preserve their direction.

Future normal demand is independently sampled: its level uses the last approximately 14 observed daily gross-booking counts, a Gamma multiplier, random growth and a possible persistent jump. It does not take NHPP expected demand as its future truth. Future synthetic normal quotes are replayed only when their scheduled event arrives; they do not enter the initial forecast or earlier traveller observations. This continuation is still an assumption, not real route-calibrated demand.

The existing probabilistic or live-LLM traveller chooses whether to join, buy, wait or cancel. The environment applies budgets, full quotes, party constraints, release rounds, inventory and cash accounting. Same-seed worlds pair the candidate with NO_OFFER.

**Supply gate.** Before an experiment is created, `floor(releasable_seats × release_fraction)` for the selected round must be at least one seat; otherwise the request is rejected with no experiment record and no provider call. If every completed replica still releases zero member seats, the run records `optimization_no_member_supply` and retains no price hypothesis.

**Fare search — mathematical track (`formula-scan-v1`).** V remains fixed. Before the run starts, `backend/fare_estimate.py` scores every member fare from `fare_min` to the cap at HK$1 steps (plus the cap itself). It builds the same simulated travellers as the search replays (same seeds) and uses the probabilistic customer model's logit utilities in expectation: join probability, member/regular purchase or wait at each remaining D28/D14/D7 round, member and normal base revenue, passenger cost and the attributed share of fee and service cost, compared with the same travellers without the offer. The highest expected incremental contribution is `P*` (ties go to the higher fare). This takes about 20 ms and is stored as `config.formula_estimate`. It ignores member quota, background demand, cancellations and seat rationing, so it is only a search aid.

The full simulation then evaluates `P*` (`search_step = formula_p_star`) and 8 nearby fares (`fine_grid`): step = (cap − fare_min)/32, alternating sides, clipped to the bounds; a bound within ±4 steps is always included. The simplified Admin fixes the Live LLM track at 6 rounds; mathematical evaluations are determined by this fine grid. On five demo flights the formula P* matched the best fare of a 9-point coarse simulated grid; on one HK$830-fare flight simulation moved the best tested fare from P* HK$370 to HK$344.06 within the grid. A run on DEMO-ISG-HKG took about 13.5 s.

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

`GET /api/optimization/suggestions?flight_id=...&forecast_day=28` searches completed, current-provenance experiments for the exact flight and round. The newest completed result in each track supersedes older results, including a newer NO_OFFER. Only independently validated OFFER results become `suggestions`. The response also contains `latest_run` (newest matching run status and provenance) and `results` (latest completed outcome per mode, including NO_OFFER or historical provenance) for read-only display. These summaries remain available if current inventory blocks publication. They never authorize publication or silently turn an old price into a current recommendation.

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

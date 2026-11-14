# UOption Fly Pass

**Forecast normal demand. Release additional member seats at D28, D14 and D7, and compare fares and membership fees.**

A runnable **NHPP-based hackathon prototype** by Team Airplane CPU · E117 for Cathay Hackathon 2026, **Low-cost Travel — Smart Offer & Borderless Booking**. The proposed HK Express membership offers zero or low base fares plus mandatory charges.

## Quick start

Python 3.11+ is required. No Node build or external service is needed for the default demo.

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m backend.server
```

Open **[Admin](http://127.0.0.1:8000/admin)** to forecast seats, compare prices, run customer panels, and publish member offers. Open the separate **[member booking site](http://127.0.0.1:8000/members)** to search released flights, join the pass, review full prices and book a simulated seat. Both use the same SQLite inventory, memberships and saved trips. The committed compressed dataset loads automatically. No payment or real ticket is issued.

## What is implemented

- **600,000 daily snapshots** across **3,315 synthetic flight histories** (200,000 demo rows plus 400,000 additional validation rows), including fares, unsold-seat rates, gross bookings and cancellations; seeded, checksummed and reproducible.
- NHPP regime mixture with parameter uncertainty, change-point detection, right-censored count likelihood and explicit future-shock scenarios. **No LightGBM**.
- **Three fixed release rounds: D28, D14 and D7.** Each round subtracts all earlier still-valid unsold allotments before issuing new seats. Purchases consume existing allotments; cancellations do not create a fourth release round.
- Up to **64 fee × fare × allocation policies**; full-term hypothetical membership economics, paired ordinary-sales baseline, independent seeds and stress cases. The release schedule is fixed, and later as-of dates use only remaining rounds; after D7, a fresh screening experiment cannot issue a new offer.
- **Shared market:** chronological traveller events, 6–12 heterogeneous flights, common inventory, multi-trip membership state, cancellations and an integer-cent contribution ledger. LLM choices directly affect supply and policy rankings.
- **Separate Admin and member interfaces:** actionable analysis navigation, panel outcome summaries, segment comparisons, searchable/paginated traveller lists, and a member-facing flight search, price review, membership and My trips flow.
- **Larger background panels:** up to **100 live LLM travellers** or **1,000 rule-based travellers**, with a default of 100. Live batches default to 60 decision attempts (maximum120), checkpoint each traveller, show progress and resume only on explicit request. Sole legal actions need no model call.
- Fourteen assumed customer archetypes; audited **actual DeepSeek calls**, Codex subagent pilot outputs, bounded/resumable batches and repeated-choice/price/order/language probes. Forced actions, cache replay and fresh calls are separate.
- Optional OAG Flight Info integration, private caching, timeouts and quota-aware failure handling.

## Evidence and limitations

This is a **synthetic-market decision prototype**, not a calibrated production revenue-management system or a representative survey of HK Express customers. OAG Flight Info supplies schedules and capacity estimates, not daily bookings or airfare history. All 600,000 simulation rows remain synthetic even when an OAG connection is available.

On **240 fresh synthetic test flights**, v2's D28 sustained-surge protection coverage is **82.5%**. On the same flights, v1 with its original 16-seat margin scores **30.0%**, while v1 recalibrated using the same procedure scores **80.0%**. The historical 47.62% came from a different cohort. D14/D7 demand MAE improves, but D28 demand MAE worsens and D7 unseen-surges still have only 75% protection coverage. See the [full comparison and limitations](docs/NHPP_V2_REVIEW.md), [frozen final report](simulation/generated/nhpp_v2_final.json) and [calibration](simulation/generated/calibration_v2.json). Raw predictive bands and calibrated operational protection are separate.

An additional frozen-model evaluation on **1,200 fresh flights** yields **91.5% D28 surge protection coverage** (200 surge flights), versus **89.5%** for equivalently recalibrated v1. D7 unseen-surges remain only **81.48%** covered. [Expanded evidence](docs/EXTENDED_VALIDATION.md) preserves the earlier final result rather than replacing it.

The shared market independently generates future ordinary demand, pairs the same world across policies, and follows every purchased membership to expiry within an explicitly finite opportunity catalogue. It does not simulate the entire real airline network or real competitive responses; renewal is uncharged intention. Customer segment weights and costs are assumptions. “Best” means best among evaluated candidates in that world, not a proven real-world optimal price.

Historical **shared-market-v2** evidence includes **120 mathematical stress-test cases**, **12 additional matched rule cases**, and **12 live-policy cases**. The three independent live validation seeds produced **1,383 fresh valid DeepSeek choices**, zero cache hits and zero failures. Under those rules and costs, no membership offer had the highest contribution in all three seeds; the cheaper candidate attracted more members but often replaced normal-fare trips. These immutable reports predate the explicit three-round carry-over rule and do not validate the new policy. See the [historical paired results](docs/SHARED_MARKET_VALIDATION.md) and [current three-round rule and verification](docs/THREE_ROUND_RELEASE.md).

The current **shared-market-v3** three-round policy has a separate **40-seed / 120-case deterministic evaluation** with all seven accounting and inventory checks passing. Across its 30 held-out seeds, NO_OFFER wins 18 and FIXED wins 12; FIXED averages HK$195.57 more contribution than NO_OFFER, while the cheaper CANDIDATE averages HK$1,706.10 less. These synthetic rule-based choices are not new LLM calls or evidence of real-world price optimality. See the [new report](llm_agent/experiments/three_round_40seeds/report.json) and [interpretation](docs/THREE_ROUND_RELEASE.md#本次三輪規則的獨立市場重播).

## Repository structure

| Folder | Purpose |
| --- | --- |
| `frontend/` | Admin vanilla HTML/CSS/JS; separate member storefront in `frontend/members/` |
| `backend/` | NHPP, pricing simulation, local HTTP API, transactional SQLite |
| `simulation/` | Generator, 600k compressed rows, separate truth and frozen evaluations |
| `llm_agent/` | Journey/market prompts, real provider adapters, audits, experiments and probes |
| `docs/` | Current architecture, progress, review and plan deviations |
| `src/`, `configs/` | Preserved earlier standalone simulator and chart exporter |
| `data/private/` | Ignored local keys' responses, LLM cache and demo database |

## Regenerate and test

```sh
python -m simulation.generate
python -m unittest discover -s tests -v
python -m unittest discover -s backend/tests -v
python scripts/verify_artifacts.py
python -m backend.evaluate --flight SYN-00001 --day 28
# With the local server running; creates synthetic demo transactions:
python scripts/smoke_api.py
python scripts/smoke_member_portal.py
```

V2 calibration is a separate explicit operation: `python -m simulation.evaluate_nhpp_v2 calibration`. The committed final report must not be overwritten to retune against it. Do not repeatedly tune on the final holdout. Read [simulation instructions](simulation/README.md) before changing generator or forecast assumptions.

## Optional services

Copy `.env.example` to `.env.local`; real secrets and licensed responses are ignored by Git. Never put keys in frontend files. The app loads this file on startup.

- OAG: set `OAG_FLIGHT_INFO_KEY`, optionally an authentication fallback. Run `python -m backend.oag --date 2026-11-15`. HTTP429 stops requests; no credential rotation to bypass quota. Raw responses remain private.
- LLM: set `LLM_API_URL` to an HTTPS Chat Completions endpoint, `LLM_API_KEY`, and `LLM_MODEL`. DeepSeek was verified using `https://api.deepseek.com/chat/completions` and model `deepseek-flash`. The six-stage baseline contains **672 successful fresh provider decisions**; a further **60 uncached behavioural probes** are recorded. Shared-market calls apply actions to the same inventory and ledger used by rule decisions. The default mode needs no key. [Raw synthetic experiments](llm_agent/experiments/) are published without authentication headers or keys.

The local server binds to loopback, validates Origin and serves only `frontend/`. External deployment requires authentication, TLS, worker limits and a production server; it is not enabled by the demo.

## Shared-market workflow

Open **http://127.0.0.1:8000/#market**. Compare a no-offer baseline, a fixed offer and a candidate policy in the same world. A candidate from Fast screening can populate the controls; it is re-evaluated rather than assumed optimal. Inspect the policy ledger, each flight's inventory and each traveller's actual sequence of choices. Live batches pause at their call limit and require an explicit resume.

Enabled policies share the D28/D14/D7 schedule. For each flight and round, the audit separates the target outstanding quota, earlier unsold quota carried forward, newly issued quota and remaining bookable supply. Forecasts may still update between rounds; an updated forecast alone never publishes new inventory.

```sh
# No provider calls: one seeded shared market, three policies.
python -m llm_agent.market_experiment create --output data/private/shared_market/example --seeds 117
python -m llm_agent.market_experiment run --output data/private/shared_market/example --max-calls 0 --max-steps 10000
python -m llm_agent.market_experiment report --output data/private/shared_market/example
```

For live experiments, create with `--modes live`, then use a bounded `--max-calls`. Every case preserves its configuration and implementation hashes. The simulator's final contribution is the policy objective; the LLM is never shown that objective or future demand.

## Documentation

- [Admin and member flows, panel limits and APIs](docs/ADMIN_AND_MEMBER_UX.md)
- [Current technical architecture](docs/CURRENT_IMPLEMENTATION.md)
- [Three-round release rule and verification](docs/THREE_ROUND_RELEASE.md)
- [Latest progress](docs/ITERATION_2_PROGRESS.md)
- [Shared-market engine and financial rules](docs/SHARED_MARKET.md)
- [Shared-market agent, auditing and probes](docs/SHARED_MARKET_AGENT.md)
- [40-seed mathematical market results](docs/SHARED_MARKET_MATH_RESULTS.md)
- [Live shared-market validation](docs/SHARED_MARKET_VALIDATION.md)
- [English scenario, budget scope and six-stage walkthrough](docs/LLM_SCENARIO_DESIGN.md)
- [Actual baseline LLM experiments](docs/LLM_BASELINE_EXPERIMENTS.md)
- [Review, improvements and deviations from the original plan](docs/OPTIMIZATION_REVIEW.md)
- [Data generation and evaluation](simulation/README.md)
- [Customer-agent scope](llm_agent/README.md)

The earlier project and pricing planning documents are preserved as design history; the current implementation document records what actually runs.

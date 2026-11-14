# E117 — Agent handoff

Updated 2026-11-14, Asia/Hong_Kong. The app is implemented; the earlier November 7 proposal is history. This file is a handoff for background only. The automatically loaded, team-maintained rules are in [AGENTS.md](AGENTS.md) (imported by CLAUDE.md); follow AGENTS.md where they differ.

## Continue from evidence

1. Inspect Git status and preserve unrelated user files. The working repo is this directory; remote is Horse-MA00/E117-AirplaneCPU. Read [README](README.md) for runnable commands.
2. Before changing forecasts or data, read [NHPP review](docs/NHPP_V2_REVIEW.md) and [extended validation](docs/EXTENDED_VALIDATION.md). The v2 model and calibration are frozen. New development requires a new version and fresh validation seeds; retain existing reports.
3. Before changing customer behaviour, read [journey design](docs/LLM_SCENARIO_DESIGN.md), its historical baseline section, and the current shared-market documentation. Inspect `backend/shared_market.py` and `llm_agent/market_experiment.py` for the current contract.
4. Before changing UI or endpoints, read [current implementation](docs/CURRENT_IMPLEMENTATION.md). The user replaced the blue theme with purple `#6F2C91`, cyan `#24BCDC` and white. Admin uses Forecast / Optimize / Experiments / Manage offers; the separate Client Portal uses `/members`. Keep the requested long forecast disclosures, validation block and daily table off that page; retain APIs and documentation.
5. Record completed milestones in [iteration progress](docs/ITERATION_2_PROGRESS.md). Run meaningful model/accounting/HTTP/browser checks before publishing changed behaviour.

## Current task and authorization

The user authorized autonomous implementation, debugging, real DeepSeek experiments, synthetic data generation, documentation, commits and pushes. No renewed permission is needed for that scope. Never publish credentials or licensed OAG raw responses. User-provided DeepSeek credentials are in ignored `.env.local`; avoid printing them. Use explicit bounded provider batches and preserve raw outputs and failures.

The current release rule is fixed D28/D14/D7 rounds. Before editing inventory, pricing or UI allocation labels, read [three-round release](docs/THREE_ROUND_RELEASE.md). Each new round subtracts all earlier valid unsold quotas from the total target. Shared market v3 stores per-round cohorts; NHPP remains unchanged. The current fast screener has 64 policies; the isolated six-stage journey remains a labelled baseline.

Before changing the primary price optimizer, run persistence or feedback, read [the flight-specific workflow](docs/FLIGHT_SCOPED_OPTIMIZATION.md). `backend/optimization.py` owns separate mathematical/LLM tracks and SQLite rounds/worlds/events. Each evaluated policy freezes its own P/V/seat profile; holdout freezes the selected profile and only accepts/rejects it. `seat_feedback.py` uses completed normal-demand outcomes and preserves base NHPP protection and vacancy curves. Existing calibration files stay frozen. The UI's “Use these prices” copies a price draft; it does not deploy the experimental seat profile into member inventory.

## Evidence boundaries

- Use NHPP first; no LightGBM. New quota is issued only at D28/D14/D7; valid unsold quota can remain available between rounds until cutoff, subject to current capacity and protection.
- There are 200,000 original synthetic snapshots and 400,000 additional validation snapshots. OAG Flight Info provides schedule/capacity context, not daily airfare, bookings or customer willingness-to-pay truth.
- v2 D28 surge protection coverage is 82.5% on the first frozen final cohort and 91.5% on the larger fresh cohort. Cohorts and recalibration differ from the historical47.62%; preserve matched comparisons and remaining unknown-surge failure cases.
- Codex pilot decisions and actual DeepSeek outputs are synthetic roleplay, not real customers. Report new provider calls, cache hits, forced actions and failures separately. Preserve prompt/context hashes and secret-free raw responses.
- Customer groups and costs are assumptions. Revenue contribution excludes pass-through fees and fixed airline costs. Renewal intent is not a paid renewal. Do not label a candidate a real-world optimum.
- Historical v2 live validation has 1,383 fresh choices, 0 cache/failures. Preserve its original rules/results in `docs/SHARED_MARKET_VALIDATION.md`; it does not validate the v3 round policy. New three-round regression artifacts live in `llm_agent/experiments/three_round_40seeds/`.
- Historical shared-market specs omitted the active calibration file from their hash list. They are preserved unchanged with a separate post-run attestation; new runs freeze `calibration_v2.json` and missing provenance fails closed. Do not silently repair old specs or claim per-call historical proof.

## State locations

- `simulation/generated/`: original200k data, baseline and frozen v2 evaluation.
- `simulation/validation_extended/`: extra400k data and1200-flight evaluation.
- `llm_agent/experiments/`: publishable synthetic experiment evidence.
- `data/private/`: ignored provider caches, audits, shared-market checkpoints, OAG responses and SQLite demo state.
- `docs/`: architecture, per-area progress, model review and optimization deviations.

For exact latest completion, checks and commits, inspect Git and `docs/ITERATION_2_PROGRESS.md`; do not infer completion from an old handoff. Local keys must remain untracked. All UI purchases are simulated; no payment or airline ticket is issued.


## Branch continuation — 2026-11-14

The new continuous-price and probabilistic-user path is documented in [docs/CONTINUOUS_PRICING.md](docs/CONTINUOUS_PRICING.md). It uses the existing shared engine, a fixed membership fee/release share, bounded cent-resolution search, paired NO_OFFER, independent validation and sensitivity stresses. Historical fixed-tier and LLM reports remain unchanged. No online human learning or autonomous live repricing is implemented. Windows locks and frozen prompt byte copies are portable; checkout rules preserve frozen NHPP source bytes.

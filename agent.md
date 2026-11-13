# E117 — Agent handoff

Updated 2026-11-14, Asia/Hong_Kong. The app is implemented; the earlier November 7 proposal is history. This file is a handoff, not an automatically loaded AGENTS.md.

## Continue from evidence

1. Inspect Git status and preserve unrelated user files. The working repo is this directory; remote is Horse-MA00/E117-AirplaneCPU. Read [README](README.md) for runnable commands.
2. Before changing forecasts or data, read [NHPP review](docs/NHPP_V2_REVIEW.md) and [extended validation](docs/EXTENDED_VALIDATION.md). The v2 model and calibration are frozen. New development requires a new version and fresh validation seeds; retain existing reports.
3. Before changing customer behaviour, read [journey design](docs/LLM_SCENARIO_DESIGN.md), [actual baseline experiments](docs/LLM_BASELINE_EXPERIMENTS.md), and the current shared-market documentation. Inspect `backend/shared_market.py` and `llm_agent/market_experiment.py` for the current contract.
4. Before changing UI or endpoints, read [current implementation](docs/CURRENT_IMPLEMENTATION.md). Preserve the Swiss white/Helvetica/blue design and display actual results, provenance and limitations.
5. Record completed milestones in [iteration progress](docs/ITERATION_2_PROGRESS.md). Run meaningful model/accounting/HTTP/browser checks before publishing changed behaviour.

## Current task and authorization

The user authorized autonomous implementation, debugging, real DeepSeek experiments, synthetic data generation, documentation, commits and pushes. No renewed permission is needed for that scope. Never publish credentials or licensed OAG raw responses. User-provided DeepSeek credentials are in ignored `.env.local`; avoid printing them. Use explicit bounded provider batches and preserve raw outputs and failures.

The latest scope is a shared chronological market: all travellers compete for the same finite inventory; LLM choices update membership, budget and financial ledgers. Compare mathematical and LLM decisions in the same environment, with independently generated normal demand and predeclared candidate policies. Increase independent test data and evaluate behavioural stability. Keep the original 192-policy mathematical screener and six-stage single-person journey as labelled baselines.

## Evidence boundaries

- Use NHPP first; no LightGBM. The member-offer window is D28 to cutoff, with selected opening days inside it.
- There are 200,000 original synthetic snapshots and 400,000 additional validation snapshots. OAG Flight Info provides schedule/capacity context, not daily airfare, bookings or customer willingness-to-pay truth.
- v2 D28 surge protection coverage is 82.5% on the first frozen final cohort and 91.5% on the larger fresh cohort. Cohorts and recalibration differ from the historical47.62%; preserve matched comparisons and remaining unknown-surge failure cases.
- Codex pilot decisions and actual DeepSeek outputs are synthetic roleplay, not real customers. Report new provider calls, cache hits, forced actions and failures separately. Preserve prompt/context hashes and secret-free raw responses.
- Customer groups and costs are assumptions. Revenue contribution excludes pass-through fees and fixed airline costs. Renewal intent is not a paid renewal. Do not label a candidate a real-world optimum.
- All three live validation seeds are complete:1,383 fresh choices,0cache/failures. NO_OFFER wins under the declared costs; matched mathematical decisions rank differently. Read `docs/SHARED_MARKET_VALIDATION.md` before changing policies. Preserve this negative result.
- Historical shared-market specs omitted the active calibration file from their hash list. They are preserved unchanged with a separate post-run attestation; new runs freeze `calibration_v2.json` and missing provenance fails closed. Do not silently repair old specs or claim per-call historical proof.

## State locations

- `simulation/generated/`: original200k data, baseline and frozen v2 evaluation.
- `simulation/validation_extended/`: extra400k data and1200-flight evaluation.
- `llm_agent/experiments/`: publishable synthetic experiment evidence.
- `data/private/`: ignored provider caches, audits, shared-market checkpoints, OAG responses and SQLite demo state.
- `docs/`: architecture, per-area progress, model review and optimization deviations.

For exact latest completion, checks and commits, inspect Git and `docs/ITERATION_2_PROGRESS.md`; do not infer completion from an old handoff. Local keys must remain untracked. All UI purchases are simulated; no payment or airline ticket is issued.

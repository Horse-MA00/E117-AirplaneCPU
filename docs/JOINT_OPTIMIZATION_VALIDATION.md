# Joint optimisation validation — 14 November 2026

> 状态：记录（2026-11-14），内容不再修改

These are synthetic implementation checks, not observations of real HK Express customers. The original source/prompt/calibration hashes are saved in each report. No existing historical dataset or experiment was overwritten.

## Six-round mathematical experiment

Run `opt-e95e88dd7d144e32`: 14 hypothetical travellers per market, 6 flights, 3 planned trips per traveller, 6 candidate rounds, 2 search seeds and 2 independent holdout seeds. The initial suggestion came from 1,031 available D28 normal-fare quotes: median HKD570, starting member fare HKD85.50 and membership fee HKD347.79. Missing quotes were excluded rather than treated as zero fares.

- 18 completed worlds, 3,131 mathematical choices and 2,415 forced actions.
- Zero provider calls, cache hits or failures.
- The strongest service-feasible search candidate was fare **HKD210.50**, fee **HKD347.79**, with mean paired incremental contribution **−HKD1,653.57**.
- Its independent holdout contribution was **+HKD570.03**, but average member use was only **50%** and the service requirement failed. Holdout did not replace the search candidate.
- Final decision: **NO_OFFER**. A higher revenue candidate with inadequate member use was not silently promoted.

Evidence: [report](../llm_agent/experiments/joint_math_20261114/report.json), [audit](../llm_agent/experiments/joint_math_20261114/audit.jsonl.gz), [checksums](../llm_agent/experiments/joint_math_20261114/manifest.json).

## Actual DeepSeek integration experiment

Run `opt-4cc2a6cc812042fe`: both tracks, 2 hypothetical travellers per market, 6 flights, 3 planned trips each, 3 rounds per track, 1 search seed and 2 independent holdout seeds. Both started at member fare HKD70 and fee HKD399. Provider model: `deepseek-flash`.

This intentionally small cohort checks actual API decisions, the feedback loop, budget pauses, resumption and durable accounting. It cannot represent the full customer population or establish commercial viability; the fixed HKD1,500 programme cost is particularly material in a two-person trial.

- 16 completed worlds across both tracks.
- **169 actual new provider decisions**, **0 cache hits**, **0 failed choices**.
- 200 mathematical choices and 335 forced actions across the combined run.
- Live work completed in bounded batches of 60, 60 and 49 decision attempts, with pauses between batches. A resumed completed math track reuses saved worlds; repeated completion audit notifications do not represent new customer observations.
- All original provider requests/responses, choices, costs and accepted transitions are retained in the redacted audit.

| Track | Strongest tested fare / fee | Search incremental contribution | Holdout incremental contribution | Decision |
|---|---|---:|---:|---|
| Mathematical | HKD70 / HKD399 | −HKD1,101 | −HKD779.50 | NO_OFFER |
| Live LLM | HKD0 / HKD399 | −HKD1,500 | −HKD1,755.50 | NO_OFFER; member-use requirement failed |

The LLM row is a diagnostic hypothesis, not a feasible recommendation. The two tracks remain separate; their scores are not averaged into a claimed real-market optimum.

Evidence: [report](../llm_agent/experiments/joint_live_20261114/report.json), [original audit](../llm_agent/experiments/joint_live_20261114/audit.jsonl.gz), [checksums](../llm_agent/experiments/joint_live_20261114/manifest.json).

## Verified invariants and interfaces

- Every complete world passed cash identity, inventory conservation, physical capacity, cohort quota conservation, nonnegative budgets, customer cash identity and one-time membership charging.
- Search and holdout seeds are disjoint. Each holdout uses the selected candidate's evaluated seat profile, not its subsequently proposed profile.
- Seat feedback excludes member holder seats and reasons; it uses completed normal-demand outcomes. Coverage compares the same forecast-reserve definition. Frozen vacancy curves are preserved.
- 149 backend tests and 19 original simulator tests passed. Historical datasets and experiment checksums passed verification.
- Admin browser smoke passed forecast, 64-policy reference screen, customer panel, shared-market comparison, explicit resume and responsive layout checks.
- New optimizer browser smoke completed the real six-round run, verified both price axes changed, read the paginated events API, confirmed independent validation and reloaded saved results. No page errors or horizontal overflow at 390/768/1440 pixels.
- Client browser smoke passed membership/purchase confirmation, exact prices, sold-out/stale-price cases, refresh-failure recovery, native dialog focus and a real local SQLite booking. Additional widths 320/390/768/1024/1440 passed.

Publishable JSON and gzip audits contain synthetic evidence only. Credentials, provider caches, operational SQLite files and licensed OAG responses remain private.

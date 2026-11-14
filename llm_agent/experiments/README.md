# Saved Thompson v5 experiments

This collection contains **all 24 current v5 / eight-group runs saved on 15 November 2026**: 23 completed and one failed. Reports, redacted compressed audits and manifests preserve the original decisions, prices, source hashes and errors. Previously exported artifacts are byte-for-byte unchanged. Viewing or publishing this collection made **zero new provider calls**.

## Present from a fresh deployment

Start the application and open **Optimize prices → Saved experiments**. All 24 runs appear automatically without API keys or a pre-existing private database. **Member feedback** reads the same saved runs; **Analyst checks → View original responses** shows the original redacted text and errors. Nothing resumes, publishes an offer or starts a model call automatically.

For a normal live example, select **DEMO_LLM0** (Fukuoka) or **DEMO_LLM1** (Okinawa). For a promotional-zero example, select **DEMO_ZERO1** or **DEMO_ZERO2**: raw selected HK$29 becomes HK$0, while the independent revenue check retains HK$39 or HK$49. These low-fare/low-budget scenarios are explicitly hypothetical, with source NHPP quota held fixed. The zero is a candidate, not a validated revenue optimum. **DEMO_ZERO0** is the separate boundary case HK$30 → HK$29 → HK$0.

All prices below are **HKD base fares**. The raw selection, formatted promotional candidate and final retained fare are separate columns. `—` means no result was produced. Source `Live` means LLM role-play, not observed HK Express customers; `Offline` means simulated choices without provider calls.

| Saved name / ID | Source | Flight / day | Saved / planned rounds × people | Raw → promotional → retained | Status / confirmation | Historical calls / failures |
|---|---|---|---|---|---|---|
| [DEMO_LLM0](DEMO_LLM0/report.json) | Live | SYN-00017 / D7 | 10/10 × 16 | 238 → 229 → 229 | ADOPT_CANDIDATE | 217 / 1 |
| [DEMO_LLM1](DEMO_LLM1/report.json) | Live | DEMO-HKG-OKA-20270515 / D14 | 10/10 × 16 | 236 → 229 → 229 | ADOPT_CANDIDATE | 232 / 0 |
| [DEMO_LLM2](DEMO_LLM2/report.json) | Live | DEMO-HKG-NGO-20270515 / D7 | 10/10 × 16 | 281 → 279 → 279 | ADOPT_CANDIDATE | 255 / 0 |
| [DEMO_LLM3](DEMO_LLM3/report.json) | Live | DEMO-HKG-PUS-20270515 / D28 | 10/10 × 16 | 283 → 279 → 279 | ADOPT_CANDIDATE | 239 / 0 |
| [DEMO_LLM4](DEMO_LLM4/report.json) | Live | DEMO-HKG-PQC-20270515 / D28 | 10/10 × 16 | 288 → 279 → 279 | ADOPT_CANDIDATE | 251 / 0 |
| [DEMO_LLM5](DEMO_LLM5/report.json) | Live | DEMO-HKG-CTS-20270515 / D7 | 10/10 × 16 | 291 → 289 → 399 | INCONCLUSIVE | 281 / 0 |
| [DEMO_LLM6](DEMO_LLM6/report.json) | Live | DEMO-HKG-KIX-20270515 / D14 | 10/10 × 16 | 270 → 269 → 269 | ADOPT_CANDIDATE | 283 / 0 |
| [DEMO_LLM7](DEMO_LLM7/report.json) | Live | DEMO-HKG-NRT-20270515 / D7 | 10/10 × 16 | 268 → 259 → 259 | ADOPT_CANDIDATE | 291 / 0 |
| [DEMO_LLM8](DEMO_LLM8/report.json) | Live | NET-HKG-ICN-20270521 / D14 | 10/10 × 16 | 282 → 279 → 279 | ADOPT_CANDIDATE | 180 / 0 |
| [DEMO_LLM9](DEMO_LLM9/report.json) | Live | SYN-00367 / D28 | 10/10 × 16 | 282 → 279 → 279 | ADOPT_CANDIDATE | 257 / 0 |
| [DEMO_ZERO0](DEMO_ZERO0/report.json) | Live | SYN-00017 / D7 | 20/20 × 32 | 30 → 0 → 39 | KEEP_INITIAL | 692 / 1 |
| [DEMO_ZERO1](DEMO_ZERO1/report.json) | Live | DEMO-HKG-OKA-20270515 / D14 | 20/20 × 32 | 29 → 0 → 39 | KEEP_INITIAL | 659 / 1 |
| [DEMO_ZERO2](DEMO_ZERO2/report.json) | Live | DEMO-HKG-NGO-20270515 / D7 | 20/20 × 32 | 29 → 0 → 49 | KEEP_INITIAL | 731 / 0 |
| [DEMO_ZERO_PILOT0](DEMO_ZERO_PILOT0/report.json) | Offline | SYN-00017 / D7 | 20/20 × 32 | 18 → 0 → 39 | KEEP_INITIAL | 0 / 0 |
| [DEMO_ZERO_PILOT1](DEMO_ZERO_PILOT1/report.json) | Offline | DEMO-HKG-OKA-20270515 / D14 | 20/20 × 32 | 20 → 0 → 39 | KEEP_INITIAL | 0 / 0 |
| [DEMO_ZERO_PILOT2](DEMO_ZERO_PILOT2/report.json) | Offline | DEMO-HKG-NGO-20270515 / D7 | 20/20 × 32 | 18 → 0 → 49 | KEEP_INITIAL | 0 / 0 |
| [771981d0c8f84850](current_thompson_v5_771981d0c8f84850/report.json) | Offline | NET-HKG-KMQ-20270518 / D28 | 6/6 × 16 | 163 → 159 → 319 | INCONCLUSIVE | 0 / 0 |
| [14158362bab541cc](current_thompson_v5_14158362bab541cc/report.json) | Offline | NET-HKG-KMQ-20270518 / D28 | 3/3 × 16 | 163 → 159 → 319 | INCONCLUSIVE | 0 / 0 |
| [cd44adfcd5564d74](current_thompson_v5_cd44adfcd5564d74/report.json) | Offline | NET-HKG-KMQ-20270518 / D28 | 3/3 × 16 | 328 → 319 → 319 | KEEP_INITIAL | 0 / 0 |
| [db38e6e4495641ce](current_thompson_v5_db38e6e4495641ce/report.json) | Offline | NET-HKG-KMQ-20270518 / D28 | 3/3 × 16 | 328 → 319 → 319 | KEEP_INITIAL | 0 / 0 |
| [612add209e864fdc](current_thompson_v5_612add209e864fdc/report.json) | Offline | NET-HKG-KMQ-20270518 / D28 | 3/3 × 16 | 328 → 319 → 319 | KEEP_INITIAL | 0 / 0 |
| [749c60ea38b34eb2](current_thompson_v5_749c60ea38b34eb2/report.json) | Live | SYN-00017 / D7 | 10/10 × 16 | 273 → 269 → 269 | ADOPT_CANDIDATE | 213 / 0 |
| [c5c1ac811b2b4f9d](current_thompson_v5_c5c1ac811b2b4f9d/report.json) | Live | DEMO-HKG-OKA-20270515 / D28 | 9/14 × 16 | — → — → — | FAILED | 164 / 1 |
| [3858026a10104926](current_thompson_v5_3858026a10104926/report.json) | Offline | DEMO-HKG-OKA-20270515 / D28 | 10/10 × 16 | 211 → 209 → 209 | ADOPT_CANDIDATE | 0 / 0 |

## What this evidence establishes

- Completed outcomes: **11 ADOPT_CANDIDATE, 9 KEEP_INITIAL, 3 INCONCLUSIVE**. This is a collected history, not a prespecified random benchmark or a market success rate.
- **14 completed Live runs, 9 completed Offline runs and one failed Live run.** Historical totals are **4,945 provider calls** (4,762 customer, 183 Analyst), zero cache hits and four failed attempts. Three Analyst failures recovered; one older run stopped after nine of fourteen rounds. That failed run has no fabricated final confirmation.
- All six zero scenarios retain HK$39 / HK$39 / HK$49 within each source group. Five raw selections are strictly below HK$30; DEMO_ZERO0 is exactly HK$30. An unsuccessful demonstration target is not relabelled or rerun to force a favourable result.
- The original live `749c60ea38b34eb2` remains unchanged: normal fare690, raw initial552, formatted initial549, raw candidate273 and formatted/retained269. Its three fresh panels averaged weighted base receipts722.24 versus2,525.01 and member purchase rates8.22% versus58.67%.
- The weighted ticket receipts exclude membership fees, fuel, taxes and operating costs. They are not net profit or annual membership value. Simulated role-play cannot validate real customer willingness to pay.

## Artifact and deployment contract

Each folder has `report.json`, `audit.jsonl.gz` and `manifest.json`. Manifests specify SHA-256 hashes, sizes and audit counts. New failure exports use `evidence_kind: execution_failure`; completed exports with recovered failed attempts retain those counts. Old manifests and source hashes remain historical and are not rewritten to claim execution by later code.

The server reads these files through `backend/published_experiments.py`. Private same-ID records take precedence and list entries are deduplicated; loading public evidence does not copy audits into SQLite. New experiments still require local storage and explicit budgets. Private databases, account sessions, caches, keys and raw OAG responses are outside this collection. Published experiments never restore checkout inventory or orders.

HTTP inline export retains its 32MiB limit. Large audits can be read through paginated events or downloaded as the committed gzip file; do not rerun an experiment merely to export it. The CLI supports streaming exports of existing runs; `--include-failed` explicitly preserves failed/interrupted executions without pretending they completed.

Run `python scripts/check_publication.py` and `python scripts/verify_artifacts.py` to check the files, audit-derived call counts, terminal status and pricing/confirmation invariants. See [current pricing method](../../docs/FLIGHT_SCOPED_OPTIMIZATION.md), [deployment](../../docs/DOCKER.md) and [maintenance record](../../docs/ITERATION_2_PROGRESS.md).

# Current Thompson v5 evidence

This directory contains the retained **member-thompson-v5-marketing** experiments using the eight-group `flexible_deal_seekers` population. Every folder includes the original report, redacted compressed audit and a file manifest. Obsolete pricing/population experiments have been removed from the working tree; they remain in Git history. NHPP evaluation data lives separately under `simulation/`.

These six completed experiments were already present before this cleanup. Exporting them did **not** make new provider calls. Original prices, failed adoption attempts, source counts and provenance are retained; this is not a newly controlled six-case benchmark.

| Experiment | Customer source | Flight / day | Rounds × people | Candidate → retained fare | Confirmation |
|---|---|---|---:|---:|---|
| [771981d0c8f84850](current_thompson_v5_771981d0c8f84850/report.json) | Offline | NET-HKG-KMQ-20270518 / D28 | 6 × 16 | 159 → 319 | INCONCLUSIVE |
| [14158362bab541cc](current_thompson_v5_14158362bab541cc/report.json) | Offline | NET-HKG-KMQ-20270518 / D28 | 3 × 16 | 159 → 319 | INCONCLUSIVE |
| [cd44adfcd5564d74](current_thompson_v5_cd44adfcd5564d74/report.json) | Offline | NET-HKG-KMQ-20270518 / D28 | 3 × 16 | 319 → 319 | KEEP_INITIAL |
| [db38e6e4495641ce](current_thompson_v5_db38e6e4495641ce/report.json) | Offline | NET-HKG-KMQ-20270518 / D28 | 3 × 16 | 319 → 319 | KEEP_INITIAL |
| [612add209e864fdc](current_thompson_v5_612add209e864fdc/report.json) | Offline | NET-HKG-KMQ-20270518 / D28 | 3 × 16 | 319 → 319 | KEEP_INITIAL |
| [749c60ea38b34eb2](current_thompson_v5_749c60ea38b34eb2/report.json) | Live LLM | SYN-00017 / D7 | 10 × 16 | 269 → 269 | ADOPT_CANDIDATE |

All fares are base fares in HKD. The first two runs preserve raw selection163 → promotional159; their confirmation retained the formatted initial319. The next three retained319. Repeated offline scenarios are not independent evidence of market performance.

## Live example

The live run's normal base fare was690, starting search fare552 and formatted initial comparison549. Its raw selected273 became269 before three independent confirmation panels of16 new people each.

| Held-out measure | Initial549 | Selected269 |
|---|---:|---:|
| Weighted member purchase rate | 8.22% | 58.67% |
| Mean actual panel base receipts | HK$732.00 | HK$2,421.00 |
| Mean weighted target-mix base receipts | HK$722.24 | HK$2,525.01 |

The report records **213 fresh provider calls** (203 customer,10 analyst), **0 cache hits**, **245 forced actions**, **0 failures**, and peak concurrency4. The five offline runs each made0 provider calls; their forced and synthetic decision counts remain in their own reports.

`ADOPT_CANDIDATE` means this selected fare passed the implementation's descriptive confirmation rule on these synthetic panels. It does not establish real HK Express willingness to pay, global optimality, annual membership profit or a general improvement rate. No membership fee or operating cost is included in these base receipts.

The quoted values come from the saved report's `recommendation`, `validation` and `counts`, not a new replay. Provenance hashes preserve the source and prompts used when the run happened; they are not relabelled as a validation of later code refactoring.

See the [current method](../../docs/FLIGHT_SCOPED_OPTIMIZATION.md) for weighted learning, paired cohorts, marketing fares and adoption rules. Run `python scripts/verify_artifacts.py` from the repository root to check the committed artifacts.

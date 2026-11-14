# Published synthetic experiment evidence

The current three-round v3 policy is tested in `three_round_40seeds/` (40 seeds, 120 complete rule markets, no provider calls). The earlier `shared_*` exports retain historical v2 rules; their live choices are not evidence for the new release policy.

These files contain synthetic personas, model-generated choices and simulator outcomes. They are not observed HK Express customers. Authentication headers and keys are excluded. Each experiment manifest records SHA256 checksums; run `python scripts/verify_artifacts.py` from the repository root to verify exports without provider calls.

| Folder | Purpose | Actual decision provenance |
| --- | --- | --- |
| `codex_pilot_20261114` | 28 isolated six-stage worlds | 168 actual Codex subagent decisions; not DeepSeek API requests |
| `deepseek_factorial_20261114` | 14 personas × 4 base fares × 2 fees × 6 stages | 672 fresh successful DeepSeek choices, no cache; one transport failure retained |
| `behavior_probes_20261114` | Repeats, price, order and language checks | 60 fresh successful choices; earlier 60 transport failures retained separately |
| `three_round_40seeds` | Current fixed D28/D14/D7 additive quota policy | 120 complete rule markets, 3,240 checked round decisions; no provider requests |
| `shared_deterministic_40seeds` | 40 seeds × 3 policies, shared inventory | 120 complete rule markets; no provider requests |
| `shared_math_matched` | Same four worlds as live runs | 12 complete rule markets; exact exogenous hashes match live worlds |
| `shared_development` | One development seed × 3 policies | 265 fresh choices, 160 exact-context cache replays, 500 forced transitions |
| `shared_validation_20261311` | Independent holdout, 3 policies | 477 fresh choices, 447 forced transitions; no cache/failures |
| `shared_validation_20261312` | Independent holdout, 3 policies | 447 fresh choices, 477 forced transitions; no cache/failures |
| `shared_validation_20261313` | Independent holdout, 3 policies | 459 fresh choices, 466 forced transitions; no cache/failures |
| `superseded_shared_v1` | Interrupted development, retained for audit | 240 successful fresh responses and one request with no recorded response; excluded from validation |

Forced transitions have only one legal action. Cache replay is not an independent new answer. Some cached development contexts originate in the superseded run, so do not sum repeated answers as new model calls. The unfinished historical request's provider-side outcome and token usage are unknown.

`shared_validation_summary.json` combines the three holdouts and keeps development separate. See [analysis and cost sensitivity](../../docs/SHARED_MARKET_VALIDATION.md) and the [calibration provenance attestation](../../docs/SHARED_MARKET_CALIBRATION_ATTESTATION.json). Original experiment specifications were preserved; the attestation does not claim missing hashes were captured at request time.

Every `audit.jsonl.gz` is a gzip-compressed stream of JSON objects. Shared-market events include the customer-visible observation and request, raw provider response, parsed/validated action and resulting environment transition. Case IDs connect the records to `experiment.json` and `report.json`; only completed worlds with valid accounting checks enter rankings.

```python
import gzip, json
with gzip.open("llm_agent/experiments/shared_validation_20261311/audit.jsonl.gz", "rt") as stream:
    for line in stream:
        record = json.loads(line)
        if record.get("event") == "market_response":
            print(record)
            break
```

The earlier isolated journey has different inventory semantics from the shared market. Its conversion counts must not be combined with shared-market policy contribution. Three live holdouts give limited simulation evidence, not real-world price elasticity or an optimal membership fee.

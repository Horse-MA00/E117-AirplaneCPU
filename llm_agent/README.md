# Thompson customer simulation

This package supports the current **member-thompson-v5-marketing** pricing workflow only. Each traveller is already a member and considers one optional ticket on the selected dated flight. There is no membership purchase or six-stage journey. Previous shared-market, panel, journey and old pricing datasets have been removed.

`weighted_population.py` creates eight groups of flexible, price-sensitive travellers; their adjustable weights are scenario assumptions, not measured HK Express market shares. Private budgets, travel interest, destination appeal and the alternative of staying home can make an affordable trip unattractive. The price learner receives public segment and declared flexibility, not those private motives or budget thresholds.

`adaptive_customers.py` presents the candidate and initial prices in reset scenarios to each round's new people. Offline choices and live LLM choices feed the same Thompson learner. A deterministic clearing step validates actions, budgets and integer inventory. Purchase intention and a capacity denial are different observations.

Current English prompts:

- [Customer decisions](prompts/adaptive_customer_v4_en.txt): bounded legal actions, reasons and fallbacks for a ticket choice.
- [Feedback analyst](prompts/adaptive_analyst_v2_en.txt): cite actual customer IDs, classify objections and propose a testable price direction. It cannot invent a willingness-to-pay label or replace a recorded decision.

Both key slots share an explicit finite call budget; parallel calls are bounded. Customer-decision failures stop dispatch rather than becoming synthetic purchases. Under `analyst-retry-v1`, analyst validation or temporary transport failures permit at most two retries (three total attempts), each charged to that budget. A valid repair retains previous attempt errors; exhausted attempts return `analysis=null` with `analysis_status=unavailable`, and Thompson continues from recorded purchases without that analyst direction. Permanent errors or insufficient remaining budget can stop retries early; audit and internal errors remain fatal.

Fresh provider calls, cache hits, forced actions, failed attempts, analyst retries and unavailable analyses are counted separately. Raw requests/responses, concrete validation failures, round/attempt identifiers and context hashes are persisted and redacted on export. The v4 customer and v2 analyst prompt files stay frozen; retry metadata records the new policy. Diagnostics use the read-only analysis-attempts API; no raw response is mistaken for validated analysis and viewing it never calls a provider.

Optional server-only configuration uses `LLM_API_URL`, `LLM_API_KEY` and `LLM_MODEL`; credentials belong in the ignored local environment. Opening saved results never calls a model. Real calls require explicit authorization and `--max-calls`.

Current reports and audits are indexed in [experiments](experiments/README.md). These are synthetic role-play responses, not human purchase data or a validated demand elasticity. The complete learner, paired testing, final quote and adoption rules are in [the current specification](../docs/FLIGHT_SCOPED_OPTIMIZATION.md).

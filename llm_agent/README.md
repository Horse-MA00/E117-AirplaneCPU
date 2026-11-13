# Customer scenarios and LLM adapter

The current product flow uses `runner.run(..., scenario_mode="journey")`. It follows subscription, D28/D14/D7 quotes, a plan change and end-of-term intention, with durable raw request/response audit. See [the full scenario design](../docs/LLM_SCENARIO_DESIGN.md), `journey.py`, `journey_runner.py`, `audit.py` and the resumable `experiment.py` CLI. The original two-stage mode remains as `scenario_mode="legacy"` for compatibility.

Fourteen archetypes cover travel purpose, frequency, budget, flexibility, group size, booking notice, route fit and languages. Their weights are **assumptions**, not verified HK Express market shares. Coverage is not statistical representativeness.

`population.py` creates persistent IDs. `prompts/customer_system.txt` defines bounded, self-interested choices. `runner.py` validates actions and budget, labels deterministic versus live responses, and never silently replaces a failed LLM call. There is no passenger personal data.

Live mode requires server-only `LLM_API_URL` (an HTTPS Chat Completions endpoint), `LLM_API_KEY`, `LLM_MODEL`. The current `deepseek-flash` configuration has completed a real six-stage smoke test. The UI limits live batches; the experiment CLI has explicit decision and worker limits. Each journey has up to six provider decisions. Cached responses retain their original provider source and are not counted as new calls. Neither mode reserves real airline inventory.

The pricing optimizer uses the repeatable mathematical market; changing prompts does not change its evaluation world. Agent outputs are hypotheses, not purchase ground truth. Calibrate future versions against consented interviews, priced choice experiments, and a real trial. Do not infer individual preferences from protected demographic attributes.

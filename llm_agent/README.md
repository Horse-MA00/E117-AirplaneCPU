# Customer scenarios and LLM adapter

Fourteen archetypes cover travel purpose, frequency, budget, flexibility, group size, booking notice, route fit and languages. Their weights are **assumptions**, not verified HK Express market shares. Coverage is not statistical representativeness.

`population.py` creates persistent IDs. `prompts/customer_system.txt` defines bounded, self-interested choices. `runner.py` validates actions and budget, labels deterministic versus live responses, and never silently replaces a failed LLM call. There is no passenger personal data.

Live mode requires server-only `LLM_API_URL` (an HTTPS Chat Completions endpoint), `LLM_API_KEY`, `LLM_MODEL`. No provider credentials were supplied for implementation. Live runs are capped at five people per request (up to two provider calls per person, cached by prompt/model/scenario); deterministic runs support up to 100. Both subscription and subsequent booking decisions use the provider in live mode. Neither reserves inventory.

The pricing optimizer uses the repeatable mathematical market; changing prompts does not change its evaluation world. Agent outputs are hypotheses, not purchase ground truth. Calibrate future versions against consented interviews, priced choice experiments, and a real trial. Do not infer individual preferences from protected demographic attributes.

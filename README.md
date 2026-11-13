# UOption Fly Pass

**Forecast normal demand. Decide when to open member offers, how many seats to release, and what base fare to charge.**

A runnable **NHPP-based hackathon prototype** by Team Airplane CPU · E117 for Cathay Hackathon 2026, **Low-cost Travel — Smart Offer & Borderless Booking**. The proposed HK Express membership offers zero or low base fares plus mandatory charges.

## Quick start

Python 3.11+ is required. No Node build or external service is needed for the default demo.

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m backend.server
```

Open **http://127.0.0.1:8000**. The committed compressed dataset loads automatically. Choose a flight and D28–D0, inspect the forecast, compare membership policies, run hypothetical customers, and publish/join/book a **simulated** offer. SQLite enforces limited inventory and duplicate-booking prevention. No payment or real ticket is issued.

## What is implemented

- Exactly **200,000 daily snapshots** across **1,105 synthetic flight histories**, including fares, unsold-seat rates, gross bookings and cancellations; seeded, checksummed and reproducible.
- NHPP regime mixture with parameter uncertainty, change-point detection, right-censored count likelihood and explicit future-shock scenarios. **No LightGBM**.
- Up to **192 fee × fare × opening-day × allocation policies**; full-term hypothetical membership economics, paired ordinary-sales baseline, independent seeds and stress cases. Later as-of dates exclude past actions; cutoff returns no offer.
- Airline dashboard, pricing heatmap and CSV export, customer scenarios, and transactional member booking flow.
- Fourteen customer archetypes, bounded LLM prompts and a server-side live provider adapter; deterministic and live results are labelled separately.
- Optional OAG Flight Info integration, private caching, timeouts and quota-aware failure handling.

## Evidence and limitations

This is a **synthetic-market decision prototype**, not a calibrated production revenue-management system or a representative survey of HK Express customers. OAG Flight Info supplies schedules and capacity estimates, not daily bookings or airfare history. All 200,000 simulation rows remain synthetic even when an OAG connection is available.

On **240 fresh synthetic test flights**, v2's D28 sustained-surge protection coverage is **82.5%**. On the same flights, v1 with its original 16-seat margin scores **30.0%**, while v1 recalibrated using the same procedure scores **80.0%**. The historical 47.62% came from a different cohort. D14/D7 demand MAE improves, but D28 demand MAE worsens and D7 unseen-surges still have only 75% protection coverage. See the [full comparison and limitations](docs/NHPP_V2_REVIEW.md), [frozen final report](simulation/generated/nhpp_v2_final.json) and [calibration](simulation/generated/calibration_v2.json). Raw predictive bands and calibrated operational protection are separate.

The pricing market uses a finite hypothetical flight catalogue over the full membership term. It does not simulate the entire real airline network, renewals, or real competitive responses. Customer segment weights and costs are assumptions. “Best” means best among evaluated candidates in that world, not a proven real-world optimal price.

## Repository structure

| Folder | Purpose |
| --- | --- |
| `frontend/` | Responsive vanilla HTML/CSS/JS, Swiss visual direction |
| `backend/` | NHPP, pricing simulation, local HTTP API, transactional SQLite |
| `simulation/` | Generator, 200k compressed rows, separate truth, calibration/evaluation |
| `llm_agent/` | Customer coverage, prompts, validated live/deterministic decisions |
| `docs/` | Current architecture, progress, review and plan deviations |
| `src/`, `configs/` | Preserved earlier standalone simulator and chart exporter |
| `data/private/` | Ignored local keys' responses, LLM cache and demo database |

## Regenerate and test

```sh
python -m simulation.generate
python -m unittest discover -s tests -v
python -m unittest discover -s backend/tests -v
python -m backend.evaluate --flight SYN-00001 --day 28
# With the local server running; creates synthetic demo transactions:
python scripts/smoke_api.py
```

V2 calibration is a separate explicit operation: `python -m simulation.evaluate_nhpp_v2 calibration`. The committed final report must not be overwritten to retune against it. Do not repeatedly tune on the final holdout. Read [simulation instructions](simulation/README.md) before changing generator or forecast assumptions.

## Optional services

Copy `.env.example` to `.env.local`; real secrets and licensed responses are ignored by Git. Never put keys in frontend files. The app loads this file on startup.

- OAG: set `OAG_FLIGHT_INFO_KEY`, optionally an authentication fallback. Run `python -m backend.oag --date 2026-11-15`. HTTP429 stops requests; no credential rotation to bypass quota. Raw responses remain private.
- LLM: set `LLM_API_URL` to an HTTPS Chat Completions endpoint, `LLM_API_KEY`, and `LLM_MODEL`. Live mode performs bounded, cached subscription and booking decisions. No LLM credentials were available during implementation, so live provider execution remains unverified. The default mode works without a key and is explicitly mathematical simulation.

The local server binds to loopback, validates Origin and serves only `frontend/`. External deployment requires authentication, TLS, worker limits and a production server; it is not enabled by the demo.

## Documentation

- [Current technical architecture](docs/CURRENT_IMPLEMENTATION.md)
- [Implementation progress](docs/IMPLEMENTATION_PROGRESS.md)
- [Review, improvements and deviations from the original plan](docs/OPTIMIZATION_REVIEW.md)
- [Data generation and evaluation](simulation/README.md)
- [Customer-agent scope](llm_agent/README.md)

The earlier project and pricing planning documents are preserved as design history; the current implementation document records what actually runs.

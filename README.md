# UOption Fly Pass

**Forecast normal demand. Release member seats at D28, D14 and D7. Learn a member fare with Thompson Sampling.**

Team Airplane CPU · E117 — Cathay Hackathon 2026, **Low-cost Travel: Smart Offer & Borderless Booking**.

UOption is a runnable decision prototype for flexible, price-sensitive travellers. It uses synthetic booking histories to estimate which seats may remain unsold, protects normal demand, then tests member base fares. All bookings and customer choices are simulated; this is not a production airline revenue system.

## How it works

```text
Synthetic daily bookings, fares and capacity
    → NHPP normal-demand forecast and safety reserve
    → D28 / D14 / D7 member quota, after earlier unsold allocations
    → Thompson Sampling price experiments on one dated flight
    → Fresh customer panels independently confirm the selected fare
    → Admin reviews the result and manually publishes an offer
    → Member site searches and books the released demo inventory
```

**Thompson Sampling is the only pricing method in the application.** New experiments use eight groups of flexible bargain travellers with editable assumed weights. Offline simulated decisions or bounded live LLM decisions feed the same public-feature purchase-response model. Each search round compares a candidate and the initial fare on the same new customers in reset scenarios. Private budgets and motivations stay outside the price learner.

Every experimental traveller is already a member. The objective compares basic ticket receipts and member purchases; membership fees, taxes, fuel surcharges and operating costs are outside this experiment. Revenue is not net profit. Regular-ticket fallback and a no-member-offer control help distinguish additional receipts from a discounted replacement purchase.

The initial member fare is **80% of the observed normal base fare**, rounded down to whole HKD. Final quotes round down to an amount ending in **9**; an amount below **HK$30** becomes a promotional **HK$0** base fare, including raw HK$30–38 after rounding. Independent confirmation uses those actual adjusted prices. The system can keep the initial price, remain inconclusive or return `NO_OFFER`.

## Run locally

Python 3.11+; no frontend build is required.

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m backend.server
```

- [Admin](http://127.0.0.1:8000/admin): Forecast seats, Optimize prices, Publish offers, Results and Member feedback.
- [Optimize prices](http://127.0.0.1:8000/adaptive-pricing): Thompson setup, saved rounds, revenue curve and independent confirmation.
- [Member sign-in](http://127.0.0.1:8000/members/login): two demo accounts, flexible destination/date search and simulated booking.

The published plan defaults to **HK$399 for six calendar months**. Use `member@uoption.test` (membership already purchased) or `guest@uoption.test` (no membership initially), both with password `FlyPass399!`. These are public demonstration credentials. Account bookings and membership persist separately; buying a pass with the guest account remains saved after sign-out. Existing stored memberships retain their recorded expiry.

The backend serves static HTML/JS and persists inventory, memberships, bookings and experiments in SQLite. The default offline workflow needs no API key. Optional live LLM/OAG credentials belong in the ignored local environment; do not commit keys, private caches or raw OAG responses. A live experiment requires an explicit finite call budget.

Docker is also supported:

```sh
docker compose up --build -d --wait
```

See [Docker setup and persistence](docs/DOCKER.md). The member site charges its separately configured demo membership plan; the Thompson experiment does not change that plan or publish inventory automatically.

## Data and evidence

The repository retains **680,364 daily synthetic observations**: 200,000 original demo rows, two 40,182-row route/date supplements and 400,000 additional validation rows. The served catalogue contains 1,549 flights and 280,364 observations. Data generation, observation timing and hidden truth are described in [simulation](simulation/README.md).

The active forecast uses the frozen NHPP v2 distribution with a newer guard at D28, and smooth v3 at D14/D7. In the separate 600-flight synthetic test, calibrated protection covered **99.17%, 99.50% and 99.83%** of future normal demand at those horizons. These are protection-coverage figures, not prediction accuracy or real-market guarantees; higher protection also releases fewer seats. Failed candidate results remain available in the [NHPP review](docs/NHPP_V3_REVIEW.md).

Only the current Thompson v5 pricing evidence is published in [the experiment index](llm_agent/experiments/README.md). Reports preserve their actual prices, decisions, audit and provenance, including unfavourable or inconclusive outcomes. No old pricing method's live result is presented as evidence for the current algorithm. Synthetic LLM responses are not observed HK Express customer behaviour.

Old pricing engines, panels, shared-market tools, their APIs and old experiment datasets have been removed from the working tree. Earlier code remains in Git history. NHPP calibration and validation evidence remains because it supports the active seat forecast.

## Verify

```sh
python scripts/check_container.py
```

This runs the project tests, documentation/publication checks and artifact verification. With the native server running, optional Playwright checks are available in [frontend](frontend/README.md). Routine checks do not call paid providers.

## Project layout

| Directory | Responsibility |
|---|---|
| `backend/` | HTTP API, NHPP forecast, release/inventory rules, Thompson learning, SQLite and member checkout |
| `frontend/` | Admin and member interfaces; directly served static assets |
| `llm_agent/` | Eight-group customer generation, English choice/analyst prompts, bounded provider calls and current evidence |
| `simulation/` | Reproducible synthetic observations and frozen NHPP evaluation |
| `scripts/` | Tests, publication checks, current experiment runners and exports |
| `docs/` | Current design, data research and NHPP evidence |

## Documentation

- [Current Thompson specification](docs/FLIGHT_SCOPED_OPTIMIZATION.md)
- [D28/D14/D7 release accounting](docs/THREE_ROUND_RELEASE.md)
- [Technical walkthrough and presentation guide (Chinese)](docs/CURRENT_IMPLEMENTATION.md)
- [Admin and member guide](docs/ADMIN_AND_MEMBER_UX.md)
- [Pitching brief and evidence boundaries](docs/PITCHING_BRIEF.md)
- [Current maintenance record](docs/ITERATION_2_PROGRESS.md)

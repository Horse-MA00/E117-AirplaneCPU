# Frontend

The Python backend directly serves the committed HTML/CSS/JavaScript; no frontend build is required.

| Path | Purpose |
|---|---|
| `/admin#flights` | NHPP seat forecast, demand filter and observed normal fares |
| `/adaptive-pricing` | The only optimizer: Thompson Sampling on one dated flight |
| `/admin#customers` | Member feedback: saved current-v5 feedback and per-round reasons |
| `/admin#members` | Publish offers: manual publication with a Thompson reference and member preview, plus membership-plan settings |
| `/admin#results` | Member sales after publication: sold seats, remaining quota, member ticket revenue (no new API) |
| `/members` | Flexible search, simulated membership, checkout and saved trips |

Optimize fixes the population to eight flexible bargain groups, with editable weights. Offline simulated customer decisions and live LLM decisions use the same Thompson method. The page keeps rounds, price/revenue estimates, the final promotional quote and independent confirmation. Viewing results does not start experiments or spend provider budget.

Old Math/Math+LLM, panel, shared-market and continuous-pricing pages, scripts and data are removed. Retired hashes, including `#optimization`, show a page-unavailable state without redirecting. Removed experiment IDs and deleted assets return not found. Forecast and Manage offers preserve a selected flight and release day when opening Optimize.

Manage offers is manual: review a retained Thompson result, enter a draft, then publish after current inventory checks. Experiments do not change the member site's inventory or membership plan. Client checkout shows the base fare prominently and mandatory fees/total separately; the server validates the complete amount. No real payment or ticket is issued.

Member search supports a destination country/region and inclusive date range. `Next month` uses the Hong Kong calendar; `Any dates` clears date constraints. The airport catalog is independent of available inventory. See [flexible search](../docs/CLIENT_FLEXIBLE_SEARCH.md).

`members/search.js` uses native Temporal where available and otherwise imports the committed local fallback. After changing its pinned dependency, use `npm ci && npm run build:calendar`; ordinary startup needs neither npm nor a CDN.

Visual design, the frozen UI contract (`ui-contract.json`) and redesign rules live in [FRONTEND_UI](../docs/FRONTEND_UI.md). Admin and Optimize share `admin-shell.css` (Inter in `fonts/`, SIL Open Font License, served locally), a sidebar and one flight bar. Brand colours: purple `#6F2C91`, cyan `#24BCDC`, white. Controls have persistent labels, native keyboard behavior and explicit current-page navigation. API and LLM text is rendered as text, not untrusted HTML. Mobile layouts and checkout focus handling are covered by browser checks.

## Browser checks

With the native backend running:

```sh
cd frontend
npm ci
npm run test:adaptive-pricing
APP_URL=http://127.0.0.1:8000 npm run test:optimization
APP_URL=http://127.0.0.1:8000 npm run test:smoke
APP_URL=http://127.0.0.1:8000 npm run test:flight-offers
APP_URL=http://127.0.0.1:8000 npm run test:members
```

`CHROMIUM_EXECUTABLE_PATH` can select installed Chrome; otherwise install Playwright Chromium. The current scripts in `package.json` cover additional demand, seat and search checks. Mocked and offline tests do not call paid LLMs. Screenshots stay in ignored `test-results/`.

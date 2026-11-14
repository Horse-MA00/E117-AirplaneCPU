# Frontend

The Python backend directly serves the committed HTML/CSS/JavaScript; no frontend build is required.

| Path | Purpose |
|---|---|
| `/admin#flights` | NHPP seat forecast, demand filter and observed normal fares |
| `/adaptive-pricing` | The only optimizer: Thompson Sampling on one dated flight |
| `/admin#customers` | Member feedback: saved current-v5 choices and reasons |
| `/admin#members` | Publish offers: manual release, Thompson reference and member-card preview |
| `/admin#results` | Sold member seats, unused quota and base-fare receipts after publication |
| `/members/login` | Two public demo logins: prepaid member and initially nonmember |
| `/members` | Signed-in flexible search, six-month membership, checkout and saved trips |

Optimize fixes the population to eight flexible bargain groups, with editable weights. Offline simulated customer decisions and live LLM decisions use the same Thompson method. The page keeps rounds, price/revenue estimates, the final promotional quote and independent confirmation. Viewing results does not start experiments or spend provider budget.

Analyst failures permit two retries within the explicit budget, then show **Analysis unavailable** while Thompson continues on valid purchase decisions. Optimize and Member feedback show concrete attempt errors; native disclosures load redacted raw replies on demand through the read-only `analysis-attempts` API. Unavailable analysis is never presented as a successful summary. Customer failures still stop the experiment. The budget estimate includes all three possible analyst attempts per round.

Old Math/Math+LLM, panel, shared-market and continuous-pricing pages, scripts and data are removed. Retired hashes, including `#optimization`, show a page-unavailable state without redirecting. Removed experiment IDs and deleted assets return not found. Forecast and Manage offers preserve a selected flight and release day when opening Optimize.

Manage offers is manual: review a retained Thompson result, enter a draft, then publish after current inventory checks. Experiments do not change the member site's inventory or membership plan. Client checkout shows the base fare prominently and mandatory fees/total separately; the server validates the complete amount. No real payment or ticket is issued. The default plan is HK$399 for six calendar months; new purchases use an exact Hong Kong calendar expiry. Demo logins and their persistence rules are in the [member guide](../docs/ADMIN_AND_MEMBER_UX.md#client-portal).

Member search supports a destination country/region and inclusive date range. `Next month` uses the Hong Kong calendar; `Any dates` clears date constraints. The airport catalog is independent of available inventory. See [flexible search](../docs/CLIENT_FLEXIBLE_SEARCH.md).

`members/search.js` uses native Temporal where available and otherwise imports the committed local fallback. After changing its pinned dependency, use `npm ci && npm run build:calendar`; ordinary startup needs neither npm nor a CDN.

Admin and Optimize share a sidebar, flight selector and locally served Inter fonts in `admin-shell.css`; the member portal keeps its current Helvetica design. Colours remain purple `#6F2C91`, cyan `#24BCDC` and white. See [Admin UI specification and contract](../docs/FRONTEND_UI.md). Controls have persistent labels, native keyboard behavior and explicit current-page navigation. API and LLM text is rendered as text, not untrusted HTML. Mobile layouts and checkout focus handling are covered by browser checks.

`flight-picker.js` supplies Admin and Optimize with From / To filters using the full Client airport/country catalog. Both controls support Anywhere and country-wide choices; demand only filters matching flights. Flight labels contain the date and complete synthetic flight ID, plus the route when the place filters are broad. Empty matches keep the chosen filters and clear the previous flight scope.

## Browser checks

With the native backend running:

```sh
cd frontend
npm ci
npm run test:adaptive-pricing
npm run test:analyst-diagnostics
APP_URL=http://127.0.0.1:8000 npm run test:optimization
APP_URL=http://127.0.0.1:8000 npm run test:smoke
APP_URL=http://127.0.0.1:8000 npm run test:flight-offers
APP_URL=http://127.0.0.1:8000 npm run test:members
npm run test:member-login
```

`CHROMIUM_EXECUTABLE_PATH` can select installed Chrome; otherwise install Playwright Chromium. The current scripts in `package.json` cover additional demand, seat and search checks. Mocked and offline tests do not call paid LLMs. Screenshots stay in ignored `test-results/`.

`test:member-login` starts its own temporary native server/database to verify both real demo sessions, account isolation, guest upgrade persistence, six-month copy and responsive login/hero layout. It never consumes the local demo inventory or calls providers.

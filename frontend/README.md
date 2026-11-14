# Frontend

The Python backend serves two separate interfaces directly from committed static assets; no frontend build is needed to run the demo:

- `/admin` (also `/`): Forecast seats, Optimize prices, Experiments (customer panels/shared markets), and Manage offers. Legacy price tools remain secondary.
- `/members`: flight search, complete member pricing, membership signup, booking review and persistent My trips. Assets live in `members/`.

Admin panels default to100 travellers, up to100live or1,000rules. The browser starts a background job, polls progress, and displays outcome metrics, group comparisons, a searchable20-row page and one person's detailed six-stage journey. Partial decisions have explicit denominators. Resume requires an explicit action; polling never spends another provider budget.

Member offers, paid demo memberships and bookings use the same SQLite state as Admin. Published offers appear in the storefront, and booking reduces their available quota. Membership fee comes from the saved server plan. Prices include mandatory fees; new membership is a separate, explicitly confirmed step. This is a local simulated identity and checkout flow, not production authentication or real payment.

Member search accepts a destination country/region and an inclusive departure-date range, including open-ended ranges. `Next month` uses the Hong Kong calendar; `Any dates` clears date constraints. Exact airport/date refinements remain available in a disclosure. Search is explicit: editing criteria does not change the applied results until submission. Refresh preserves selected criteria, including when their final published offer disappears. See [flexible-search behavior and demo steps](../docs/CLIENT_FLEXIBLE_SEARCH.md).

`members/airports.js` supplies both airport selectors independently of inventory: 37 officially listed/announced airports as checked on 2026-11-14, plus the team's requested Sapporo (CTS) with an unconfirmed-schedule label. Kuala Lumpur uses SZB; Hefei carries its announced start date. Published unknown/legacy endpoints are added without fabricating flights. The optional exact-date control is a native calendar, not a list constrained to published flight dates.

`members/search.js` uses native Temporal calendar dates when supported and otherwise dynamically imports the committed, locally bundled `members/vendor/temporal.js`. No CDN access is needed. The fallback's MIT notice is alongside the bundle. After changing the pinned dependency, run `npm ci && npm run build:calendar` to regenerate it with esbuild; regular backend startup needs neither npm nor esbuild.

Visual direction: white surfaces, Helvetica Neue, purple `#6F2C91` and cyan `#24BCDC`, with explicit grids. This replaces the former blue design at the user's request. Admin prioritizes seat composition and iterative price/contribution charts; the member site uses flight cards, fare sorting, full-price breakdowns and a separate checkout. API values use `textContent`, SVG nodes and native controls, not untrusted HTML interpolation.

`optimization.js` uses the SQLite-backed `/api/optimization/runs` endpoints. Configure independent math/LLM tracks, rounds, the membership fee V₀ (the starting fare P₀ is read-only, set by the server from the selected snapshot's normal base fare), bounds and a live batch budget. Saved experiments retain current and best-tested prices, independent validation and raw decision records. A price draft does not apply a learned seat profile to published inventory; flight-specific base-NHPP allocation remains authoritative.

Accessibility includes labelled native progress, semantic keyboard-scrollable tables, non-colour decision labels, persistent form labels, a native checkout dialog, Escape/focus return and mobile layouts. No focusgroup or experimental animation dependency.

## Browser checks

With the backend running:

```sh
cd frontend
npm install
npx playwright install chromium
npm run test:smoke
npm run test:smoke -- --transactions
npm run test:optimization
npm run test:continuous
node smoke-english-journey.mjs
node smoke-member-portal.mjs
npm run test:flexible-search
npm run test:route-catalog
# Also completes a real local SQLite membership and simulated booking:
node smoke-member-portal.mjs --real
```

`APP_URL` overrides the local origin. `CHROMIUM_EXECUTABLE_PATH` selects installed Chromium. Screenshots remain ignored under `test-results/`. Admin transaction testing publishes an offer only; member checkout lives in its own smoke. All test-driven live/error states use intercepted fixtures; none of these checks calls a paid LLM. The dedicated panel check runs100real deterministic travellers and verifies600stages, filters, pagination, partial counts and manual resume.

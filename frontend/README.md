# Frontend

The Python backend serves two separate interfaces with no bundler or third-party browser dependency:

- `/admin` (also `/`): Forecast seats, Optimize prices, Experiments (customer panels/shared markets), and Manage offers. Legacy price tools remain secondary.
- `/members`: flight search, complete member pricing, membership signup, booking review and persistent My trips. Assets live in `members/`.

Admin panels default to100 travellers, up to100live or1,000rules. The browser starts a background job, polls progress, and displays outcome metrics, group comparisons, a searchable20-row page and one person's detailed six-stage journey. Partial decisions have explicit denominators. Resume requires an explicit action; polling never spends another provider budget.

Member offers, paid demo memberships and bookings use the same SQLite state as Admin. Published offers appear in the storefront, and booking reduces their available quota. Membership fee comes from the saved server plan. Prices include mandatory fees; new membership is a separate, explicitly confirmed step. This is a local simulated identity and checkout flow, not production authentication or real payment.

Visual direction: white surfaces, Helvetica Neue, purple `#6F2C91` and cyan `#24BCDC`, with explicit grids. This replaces the former blue design at the user's request. Admin prioritizes seat composition and iterative price/contribution charts; the member site uses flight cards, fare sorting, full-price breakdowns and a separate checkout. API values use `textContent`, SVG nodes and native controls, not untrusted HTML interpolation.

`optimization.js` uses the SQLite-backed `/api/optimization/runs` endpoints. Configure independent math/LLM tracks, rounds, starting fare/fee, bounds and a live batch budget. Saved experiments retain current and best-tested prices, independent validation and raw decision records. A price draft does not apply a learned seat profile to published inventory; flight-specific base-NHPP allocation remains authoritative.

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
# Also completes a real local SQLite membership and simulated booking:
node smoke-member-portal.mjs --real
```

`APP_URL` overrides the local origin. `CHROMIUM_EXECUTABLE_PATH` selects installed Chromium. Screenshots remain ignored under `test-results/`. Admin transaction testing publishes an offer only; member checkout lives in its own smoke. All test-driven live/error states use intercepted fixtures; none of these checks calls a paid LLM. The dedicated panel check runs100real deterministic travellers and verifies600stages, filters, pagination, partial counts and manual resume.

# Frontend implementation progress

2026-11-14 Asia/Hong_Kong

- Read the requested frontend-design skill and modern-web-guidance responsive-table, accessibility and tabs guides.
- Implemented Swiss visual system and responsive static HTML/CSS in frontend/.
- Implemented four API-connected views and native form flows in frontend/app.js.
- Implemented as-of flight/day request guards; historical chart excludes future observations.
- Implemented result-derived price heatmap, export, synthetic-customer action cards and offer/member/booking forms.
- JavaScript passes node --check. Full live server integration and browser review pending backend readiness.

## Integration and visual review completed

- Fixed backend contract mismatches: normal_total_fare, empty_rate, incremental_cost, live_configured, offer.fees, booking.total, and stored member.fee.
- Found and reported a server-blocking Handler.headers method collision; root repaired it.
- Prevented adopting a policy before its selected opening day. Non-365-day policies cannot be copied into the fixed-year demo membership. Experiment setting changes invalidate adoption until recalculated.
- Added baseline/fixed-policy/stress comparisons, a contribution ledger and independent evaluation diagnostics.
- Live LLM panels are limited to five requests; default deterministic panel covers all 14 configured customer scenarios.
- Chromium end-to-end verification passed on 2026-11-14: D28→D14 uses 15 known daily observations; 192 policy candidates returned; changed passenger cost 80 was verified in API config; heatmap selection works; 14 customer cards render; offer publication, membership and simulated booking succeed; HK$70 base plus HK$250 fees produces HK$320.
- Desktop (1440px) and mobile (390px) screenshots inspected. No horizontal page overflow and no JavaScript errors. Reworked SVG viewport sizing to retain readable mobile axis labels.
- Screenshots are local under frontend/test-results and ignored by Git. Tests created clearly identified demo customer/offer/booking records in the local demo database; no real payments or tickets.
- Live LLM provider execution remains unavailable without the configured external LLM credentials; the UI reports this rather than substituting a fabricated live result.

## Final backend regression

- Added portable frontend/smoke.mjs and a pinned Playwright development dependency with package-lock.json. Production remains build-free and dependency-free in the browser.
- Executed npm run test:smoke -- --transactions against the final backend successfully.
- Explicitly verified publishing one seat reduces the displayed maximum new allocation by one; confirmed the cached NHPP forecast is not mutated by the UI.
- Rechecked forecast time filtering, cost propagation, all 192 candidates, future-opening guard, 14 customer decisions, membership, fee-inclusive reservation and all four mobile layouts.
- Inspected final flight and pricing mobile screenshots after the regression; labels are readable and no horizontal page overflow occurs.
- Final validation disclosure reports both raw model P90 coverage and allowance-adjusted protection coverage, explicitly scoped to D28. It does not label adjusted protection as a posterior P90.
- Playwright 1.62.1 was verified against installed package metadata and successfully installed from npm; package-lock.json records resolved package integrity.
- Final root review also clears stale pricing results when changing the selected flight or as-of day; a new comparison is required before showing a recommendation under the new context.

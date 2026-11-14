# Frontend implementation progress

2026-11-14 Asia/Hong_Kong

Current state: five views, including Shared market; real DeepSeek is configured locally and its completed experiments are documented separately. The earlier entries below describe the first implementation stage. Journey live runs allow up to five people (six stages each); shared live batches have their own explicit call budget.

## English journey explanation — 2026-11-14

- The Journey baseline now states English response language and HKD currency for new v2.2-en results, and identifies the exact prompt version. Historical result text is preserved in its original language rather than translated and mislabelled as a fresh model response.
- Added a keyboard-operable native disclosure explaining all six stages, the single-trip budget including a new membership fee, expected annual trips versus recorded transactions, existing members, cancellation and unpaid renewal intention. It explicitly distinguishes the isolated scripted 4 / 0 / 1 member-seat checkpoints from Shared market's D28 / D14 / D7 releases and carried quotas.
- Customer cards use English population labels and show trip-plus-fee budget, singular/plural party size, existing membership and each stage's remaining budget, fee paid, ticket spend and refunds. Independent disclosures can remain open together for comparison; the existing Swiss design is preserved.
- `frontend/smoke-english-journey.mjs` passed with 14 current deterministic personas / 84 stages, English card and coverage text, HKD budgets, keyboard disclosure behavior, preserved historical Chinese fixture text and no overflow at 390px. It intercepts only the panel response using output generated from current Python code and makes zero live-provider calls. Desktop, mobile and expanded-card screenshots were visually checked; no JavaScript errors were reported. `node --check` and `git diff --check` also passed.
- Applied modern-web-guidance `accordion`: text-only native summaries and non-exclusive disclosures, allowing scenario instructions and multiple traveller histories to stay visible together.

## Initial implementation

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

## Shared-market implementation — 2026-11-14

- Preserved the existing isolated six-stage journey audit and NHPP v2 validation work. Renamed their navigation context to Journey baseline and Fast screening, and added clear links to Shared market.
- Built the fifth view with three-policy paired comparison, saved runs, seed and candidate price/timing/allocation controls, explicit live budget (default60, maximum100), read-only progress polling and manual resume. Partial runs cannot produce a winning-policy claim.
- Connected full-term inspections to actual per-policy ledger, finite seat inventory, customer budget and membership status, renewal intention and event provenance. Forced, deterministic, cached and live counts remain separate. Added programme/member-service costs and total costs after the engine accounting revision.
- Candidate transfer copies only the chosen 365-day hypothesis into experiment inputs; it never launches a paid run or claims real-market optimality. The original member-demo publish/join/reserve journey remains separate.
- Added the additional frozen-model evaluation statement from `/api/evaluation/extended`, preserving the first holdout and exposing the D7 still-unobserved-surge limitation.
- Read and applied the modern-web-guidance `accordion` guide before changes: native independent disclosures, text-only summaries and keyboard-accessible standard data tables.
- First Chromium integration pass completed: three deterministic worlds, nine flights, fourteen synthetic travellers, multi-trip term journeys, zero provider calls, and five mobile layouts without page overflow. A mocked pause/resume fixture verifies that a pause never starts another budget automatically.
- Browser review found and repaired a malformed existing live-mode `<option>` that caused initialization to fail when the provider was configured.
- Desktop and mobile Shared market screenshots inspected; captures remain local under the ignored `frontend/test-results/` directory. Final frozen-engine regression passed, including simulated publishing, joining, fee-inclusive reservation and inventory decrement. A targeted follow-up verified current-view skip navigation, the shared-market raw-audit link and the extended D7 future-surge coverage statement. Added a mobile scroll hint to the wide comparison and inventory tables.
- Hardened comparisons for saved multi-seed experiments: policy rows now show group means, paired differences average matched seeds, and mixed decision modes/splits never share one winning headline. The regression fixture verifies that fixed deltas +100/+100 beat candidate deltas +1000/−900; the best individual seed cannot select the winner.
- Re-ran the full frontend smoke after this change successfully. Static checks also pass (`node --check`, `git diff --check`, no duplicate HTML IDs, no malformed option closers). No live provider requests were made by frontend QA; the pause/resume and ranking edge cases use intercepted test fixtures only.
- Final independent review passed frontend and API smoke tests, real CLI-running status and polling, incomplete ranking disclosure, and the streaming gzip audit download (2,775 complete records). No automatic market POST or provider spending was triggered by polling.


## Admin and member storefront — 2026-11-14

- Reworked Admin information hierarchy with action-oriented navigation and separate `/members` entry. Customer panels now show outcomes first, segment comparison bars,20-row searchable/filterable tables and one selected six-stage journey. Live size100/offline1000 is independent of the bounded decision budget.
- Native labelled progress and polite status preserve keyboard focus; manual resume never auto-starts another paid batch. Published-price drafts survive navigation and require explicit saving; currency inputs accept cents.
- Moved member signup/reservation out of Admin. New `members/` storefront searches actual published synthetic offers, explains full price and new-pass fee, reviews two explicit transactions, and shows persisted My trips. The same SQLite inventory and canonical membership plan power both interfaces.
- Native modal review supports Escape and focus return. Submit controls prevent duplicate posts, price/availability changes require re-review, and a successful mutation followed by failed GET retains success rather than encouraging another charge.
- Verified real100-person600-stage panel,14groups,partialdenominators,pagination,filtering,manualresume fixture,fee draft599.75,desktop390/768px. Updated fullAdmin smoke and actualSQLite portal join/book/reload both passed. New portal fixtures cover empty/no-match,exact cents,changedfee,soldout,accountswitch,successwithrefreshfailure. Screenshots inspected and remain ignored.
- Applied modern-web-guidance `progress`, `responsive-table`, `forms`, `dialog` and maintained Swiss white/Helvetica/blue tokens. No provider calls made by browser QA.

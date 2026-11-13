# Frontend

No bundler or third-party browser dependency is required. The Python backend serves this folder at the origin root. Start the repository server and open http://127.0.0.1:8000.

The four hash-navigation views connect directly to same-origin APIs: flight decisions, pricing experiments, synthetic customer decisions, and inventory-backed member transactions. There is no hard-coded revenue, forecast, or customer output. Synthetic data, assumed customer weights and unavailable live LLM mode remain explicit.

Visual direction: Swiss. White / neutral #F7F7F8, Helvetica Neue, Yves Klein Blue #002FA7, hairline grids. The D28-to-cutoff date scrubber is the primary interaction. API content is inserted using textContent, SVG DOM nodes, or native form options rather than HTML interpolation.

Accessibility: semantic navigation (not ARIA tabs for page navigation), persistent form labels, native controls, keyboard focus, reduced-motion support, chart captions and an observed-data table. Wide comparison tables retain semantic headers inside labeled keyboard-scrollable regions. Mobile layout reflows major panels without horizontal page overflow.

Modern web guidance consulted:
- responsive-table: "Use standard `<table>` elements with `<thead>`, `<tbody>`, and `<th>` elements." Tables preserve column semantics in keyboard-scrollable regions; fixed-width mini-cards would hide comparable values.
- accessibility: "Provide semantic data tables as accessible alternatives" and "Prefer HTML elements and attributes to ARIA" shaped the observation table, native controls and non-colour state cues.
- tabs: "DO NOT use this or the WAI-ARIA tabs pattern for page navigation" led to hash links with aria-current instead of unsupported focusgroup tab semantics.

Browser support: modern Chrome, Safari and Firefox using established DOM, fetch, CSS Grid and SVG; no focusgroup, scroll-driven-animation or hidden-until-found dependency.

## Repeat the browser smoke checks

With the backend already running:

```sh
cd frontend
npm install
npx playwright install chromium
npm run test:smoke
# Optional: also creates test offers, a demo membership and a simulated booking.
npm run test:smoke -- --transactions
```

`APP_URL` can override the default local origin. `CHROMIUM_EXECUTABLE_PATH` can select an already-installed Chromium binary. Screenshots are saved under the Git-ignored `test-results/` folder. The optional transaction check requires remaining member inventory on the first synthetic flight; use a fresh local demo database when repeating it many times. Neither mode calls a paid LLM provider.

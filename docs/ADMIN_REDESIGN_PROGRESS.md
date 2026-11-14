# Admin redesign — 2026-11-14

## Implemented

The Admin Portal now uses the requested dark purple `#6F2C91`, cyan `#24BCDC` and white palette. The design retains a readable sans-serif grid and distinct numeric hierarchy. Four primary destinations replace the earlier five equally weighted tools:

- **Forecast seats**: selected flight and as-of day, expected unsold seats, additional member allocation, physical normal-demand protection, a labelled seat composition bar, booking forecast, and observed total-fare history. Three-round quota details are below the main visuals. The former model-assumption list, validation block and daily-observation table have been removed from this view and their rendering requests removed.
- **Optimize prices**: editable P0/V0, simulated-data starting suggestion, mathematical / live LLM / both tracks, round and population controls, bounded provider calls, saved SQLite experiments, live progress, independent price paths and contribution plots, per-round candidate table, and holdout decision. A validated candidate can be copied into offer management as a draft; copying does not publish or charge anything.
- **Experiments**: Customer panel and Shared market are secondary tabs. Existing independent six-stage panel and shared-inventory market functionality is preserved.
- **Manage offers**: existing inventory publishing and canonical membership plan controls remain, visually separated from the consumer Client Portal.

Earlier continuous-fare and fixed-grid price tools remain reachable through a secondary link at the bottom of Optimize. They are labelled reference methods rather than competing primary workflows.

## Data and state handling

All displayed charts and metrics are generated from current API results. The price chart excludes quotes after the selected observation date. Physical seat protection is capped to remaining capacity; the member-capacity segment is also capped by the forecast's actual release ceiling, with any withheld capacity shown separately. A failed-quality forecast cannot imply member availability through the chart.

Optimization uses the new `/api/optimization/runs` API. Opening, polling or restoring a report does not start additional work. Paused batches require an explicit continue action. Candidate output is labelled pending until holdout completion; NO_OFFER remains a valid recommendation. A provider failure is visible, with no fabricated result. Raw event and report links remain accessible below the main graphs.

## Checks performed

- `node --check frontend/app.js` and `frontend/optimization.js` passed.
- Updated and passed `frontend/smoke.mjs`: actual as-of forecasts, forbidden disclosure removal, seat composition, current price caption, 64 legacy three-round candidates, a 14-person independent panel, full shared-market replay, preserved manual pause/resume, and mobile layouts.
- Desktop 1440px and mobile 390px screenshots inspected for Forecast and Optimize. No page-level overflow or uncaught browser errors in that pass.
- Root integration checks cover the new optimizer API, actual saved round results, initial-price suggestion, final report, and transactional Client Portal flow.

## Guidance applied

- `responsive-design`: rem-bounded `clamp()` typography and dynamic viewport height; viewport layouts preserve controls on small screens.
- `responsive-table`: semantic table headers and keyboard-focusable named overflow regions; tables retain their column relationships rather than compressing text into unreadable cells.
- `html`: semantic navigation/main landmarks, labelled input controls, native `details` for secondary settings, named SVG charts, and text legends for chart colours.

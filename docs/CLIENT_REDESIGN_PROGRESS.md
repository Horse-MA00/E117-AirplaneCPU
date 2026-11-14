# Client portal redesign — 14 November 2026

## Completed

The `/members` experience now uses the requested HK Express-inspired palette: purple `#6F2C91`, cyan `#24BCDC`, and white. The structure uses a Helvetica family, an explicit grid, and a boarding-pass motif for real published flight offers. This intentionally replaces the previous blue theme; the user's brand specification takes priority over the earlier design tokens. It remains an independent UOption concept, with no claim of airline affiliation or real ticket fulfilment.

The primary journey is visible as three steps: browse a flight, join the pass when needed, then explicitly confirm the ticket. The search form sits beneath the purple introduction and accepts origin, destination, and available departure date. The results provide the actual complete ticket price, base-fare/mandatory-fee breakdown, current normal fare, and positive ticket saving before the separate membership fee. Sorting by total ticket price and an available-seats-only filter are new. Flight cards adapt to their results-column width through container queries.

The pass panel displays the server's current membership fee and term, plus this account's actual membership status. My trips displays saved bookings. Test-account switching is inside a native disclosure; generating a fresh test identity remains available without placing account tools in the shopping flow. The empty-inventory state no longer directs a consumer into Admin offer management. The Admin link is confined to the footer.

The native checkout dialog, explicit join-then-book steps, authoritative server price checks, stale-fee re-review, unavailable-seat handling, and successful-mutation receipt handling are preserved. New booking UI does not create offers, modify optimisation policies, or invoke an LLM. Mandatory fees remain included in displayed ticket totals. The interface remains English-only.

## Validation performed

- JavaScript syntax check passed.
- Existing `frontend/smoke-member-portal.mjs` passed unchanged using fixture responses: filter submission, exact HKD cents, modal focus/Escape, separate membership and booking confirmations, account persistence, changed fee, sold-out inventory, idempotent membership receipts, and failed post-purchase refresh recovery.
- The same smoke passed with `--real` against the local backend: one new simulated membership and one persistent `SYN-00001` ticket at HKD320, confirmed after reload. No real payment or airline ticket.
- Additional browser checks confirmed ascending actual ticket-price sorting, availability filtering, no page errors, and no horizontal overflow at widths 320, 390, 768, 1024, and 1440 pixels.
- Desktop, mobile, and mobile checkout screenshots were inspected. Screenshots remain local in the ignored `frontend/test-results/` directory and are not represented as real customer evidence.
- Zero LLM/provider calls were made for this redesign.

## Guidance applied

- `responsive-design`: component-level `@container` rules adapt flight cards to the available results-column width; `dvh` bounds the checkout dialog and `clamp()` combines relative and font units for hero type. Guide: "Use `@container` queries to create component-driven responsive layouts".
- `html`: retained a native `dialog.showModal()`, an explicit form-based Close control, labelled search/filter controls, semantic headings, and actual text next to colour status indicators. Guide: "DON'T convey state, interaction, or information using color alone."

## Remaining scope

The consumer portal is still the local single-member-seat prototype described in the existing implementation document. It does not introduce production authentication, payment capture, checked-baggage sales, a normal-fare checkout, or a refund workflow. These capabilities were not invented to support the visual redesign.

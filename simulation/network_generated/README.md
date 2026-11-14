# Supplemental route/date simulations

This additive dataset contains **222 flights and 40,182 daily snapshots**:

- 37 remote airports in the member-search catalog, each paired with HKG in both directions.
- Three assumed departure dates per directed route: 15, 18 and 21 May 2027.
- Complete D180–D0 histories with capacity, available seats, bookings, cancellations, normal base fare, mandatory fees and an initial member base fare.

The 37-airport set includes Sapporo (CTS), retained at the team's request with
`route_status=requested` and an unconfirmed-schedule note. Hefei (HFE) retains its
announced status. These scenarios do **not** establish actual airline service on
the assumed dates. All flights, prices, capacities and bookings are synthetic.

`member_initial_base_fare = round(0.15 × normal_base_fare, 2)` is stored on each
open-quote snapshot. It is an initial pricing hypothesis, not willingness-to-pay
ground truth or an optimized label. Closed/sold-out quotes retain missing prices,
not zero fares. P0 must be read from the selected flight's as-of snapshot.

The original NHPP generator is called without edits; a unique seed index is used
for each route/direction/date. Its output schedule is then relabelled, retaining
all inventory and exposure identities. Dates are expressed on a common Hong Kong
simulation clock, including inbound flights; they are not actual local airport
timetables. Demand diversity is assumed, not calibrated to specific routes.

Regenerate and validate from the repository root:

```sh
python -m simulation.network_generate
python -m simulation.network_generate --validate-only
python -m unittest backend.tests.test_network_data -v
```

The manifest records input-source and output-file SHA-256 hashes. Truth remains
separate from observable snapshots. Original `simulation/generated` and the
400,000-row additional validation cohorts remain unchanged.

The served catalog is now 1,327 flights / 240,182 snapshots: original 1,105 flights
and 200,000 rows plus this supplement. `backend.data.manifest().rows` still means
the original CSV export's 200,000 rows; `catalog_rows` and `catalog_flights` describe
the complete searchable catalog. The 400,000 validation rows are not served as
bookable demo flights.

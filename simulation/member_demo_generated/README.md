# Member-opportunity NHPP demonstrations

This additive dataset supplies **222 synthetic flights / 40,182 daily snapshots**: all 74 directed catalog routes, each on 15, 18 and 21 May 2027. Flight IDs start with `DEMO-`; existing `SYN-` and `NET-` histories retain their original meaning.

These are deliberately chosen **scenario assumptions**, not estimates of how often HK Express has spare capacity. May 15 uses expected normal requests of 35–40% of capacity with a slow trend; May 18 uses 46–55%; May 21 is a higher-demand control with 95–120% expected requests. Realized occupancy is random and additionally affected by capacity and cancellations. Requested CTS and announced HFE retain their catalog statuses; inclusion does not establish actual service on these dates.

## Generation

```sh
python -m simulation.member_demo_generate --forecast-check
python -m simulation.member_demo_generate --validate-only --forecast-check
```

The generator samples independent parameter, exogenous price, arrival and cancellation streams from fixed seed `11720261115`. For each interval, requests are Poisson draws with an integrated NHPP rate and assumed price response. Accepted requests are capped by available capacity. Cancellations release seats at interval end. No release forecast, seed search, rejection sampling or post-hoc booking adjustment is used.

`snapshots.csv.gz` has observed D180–D0 inventory, quotes and completed-interval counts. D0 is sales cutoff two hours before departure. `member_initial_base_fare` is 15% of the observed normal base fare, rounded to cents, and is missing when no quote is open. Fees remain separate. This is a starting-price assumption, not optimized customer willingness to pay.

`parameters.json`, `truth.csv.gz`, scenario labels and final outcomes are hidden provenance/evaluation data. The predictor only receives observations through its decision day. Metadata `demo_priority` is for presentation ordering, never forecasting.

## Frozen-model checks

`headroom_validation.json` retains all 666 forecasts and SHA-256 references to the model, calibration and data. It describes risk-releasable inventory **before** member purchases, outstanding earlier quotas and release-round bookkeeping. It is not incremental new quota or evidence of real-world forecast coverage.

| Decision day | Positive flights / 222 | Flights with at least 25 seats | Routes with an option of at least 25 seats / 74 |
| --- | ---: | ---: | ---: |
| D28 | 126 | 105 | 70 |
| D14 | 148 | 144 | 74 |
| D7 | 148 | 148 | 74 |

D28 low-demand examples have 71/74 positive forecasts and median headroom 65 seats. The moderate cohort has 54/74 positive forecasts and median 28; the higher-demand control has only 1/74 positive forecasts and median 0. These results intentionally include failures: the best D28 headroom is 0 for HKG–FUK, 18 for ICN–HKG, 9 for NGB–HKG and 0 for CRK–HKG. The 25-seat design aim was therefore not met on those four directions; no outcomes were discarded or regenerated.

The API joins verified `demo_d28_releasable` display hints from the report only when model/data hashes still match. The UI can prefer an actual positive example while keeping all flights selectable. Actual release decisions always run the current predictor and quota ledger.

## Preservation and reproduction

`manifest.json` records generator/input versions, hashes and output hashes. It preserves the original 200,000 demo snapshots, 400,000 extended validation snapshots and 40,182 network supplement snapshots unchanged. The served catalog now has **1,549 flights / 280,364 snapshots**; the original CSV export still contains 200,000 rows. Forecast-check reports are separate from generated data hashes so rerunning an audit cannot silently change the cohort.

Run the focused tests with:

```sh
python -m unittest backend.tests.test_network_data backend.tests.test_member_demo_data -v
```

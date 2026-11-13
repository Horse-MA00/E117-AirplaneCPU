# NHPP and pricing implementation progress

2026-11-14: Implemented `backend/nhpp.py` and `backend/pricing.py` with no LightGBM dependency. The NHPP uses as-of gross counts, exact interval exposure, a beta-grid posterior and Gamma rate uncertainty. Negative beta is allowed. Capacity-hit intervals are excluded and heavy censoring or an abrupt surge prevents member release.

The pricing search evaluates 192 full-term candidate policies against identity-paired ordinary sales. Fees are counted once, costs include every accepted trip, quotas and total capacity are enforced, and service constraints prevent charging for an unusable programme. Holdout seeds and cost/interest/demand stress scenarios are reported separately from selection. All customer behaviour parameters remain explicit synthetic assumptions.

Model test suite has been added at `backend/tests/test_models.py`; validation status will be recorded after execution. The annual flight catalogue is deliberately a finite scenario; it is not a claim to reproduce HK Express actual market share, schedules or price elasticity.

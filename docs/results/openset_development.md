Recorded on 2026-10-20. This is a small execution check, not a benchmark.

Reproduction: see [P11](../plan/P11_openset_development.md) and [configuration](../../configs/stage_b_openset.json).

# Open-set development experiment

Protocol: `B1-dev/1`. Held-out family: `swept_cw`.
Known classes: clean, cw, unauthorized, overdrive.

Development run using single-polarization A1 observations; not the final eight-class benchmark.
Unknown-family samples are excluded from optimization, model selection and rejection calibration.
Validation scenario groups for model selection and calibration are disjoint.

| Method | Known acceptance | Accepted-known accuracy | Held-out rejection | Clean false alarm |
|---|---|---|---|---|
| msp | 87.5% | 23.8% | 16.7% | 100.0% |
| energy | 100.0% | 25.0% | 0.0% | 100.0% |

Known acceptance counts all known test events; accepted-known accuracy is conditional on acceptance.
Clean false alarm includes rejection of clean samples and predictions of a non-clean known class.
JSON includes counts and scenario-bootstrap intervals at a fixed trained model and threshold.
A validation acceptance target does not guarantee the same test acceptance.

## Partitions

| Role | Samples | Scenario groups |
|---|---|---|
| train | 24 | 6 |
| validation | 12 | 3 |
| calibration | 12 | 3 |
| known_test | 24 | 6 |
| unknown_test | 6 | 6 |

Source data complete: `False`.
Experiment fingerprint: `d69e1e7461a6d37008b3813efc5afa85665e1ed60d7dcef691e1e1d5fc74e2cd`.

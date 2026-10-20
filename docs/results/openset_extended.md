Recorded on 2026-10-20. This three-epoch smoke run generated 108 simulated observations; recognition remains weak. It validates execution, not research performance.

Reproduce with [P13](../plan/P13_extended_openset.md). [Full metrics and curves](openset_extended.json); [per-event predictions](openset_extended_predictions.json).

# Open-set development experiment

Protocol: `B1-dev/2`. Held-out family: `swept_cw`.
Known classes: clean, cw, unauthorized, overdrive.

Unknown families: intermittent_bursts, pulsed, swept_cw, wideband_noise.

Development run using single-polarization A1 observations; not the final eight-class benchmark.
Unknown-family samples are excluded from optimization, model selection and rejection calibration.
Validation scenario groups for model selection and calibration are disjoint.

| Method | Known acceptance | Accepted-known accuracy | Unknown rejection | Clean false alarm |
|---|---|---|---|---|
| msp | 87.5% | 23.8% | 4.2% | 100.0% |
| energy | 100.0% | 25.0% | 0.0% | 100.0% |
| mahalanobis | 83.3% | 25.0% | 16.7% | 100.0% |

## Unknown ranking and open-set classification

AUROC and average precision use unknown as positive. OSCR combines correct known classification with unknown false acceptance.
The curves summarize test ranking; deployment thresholds remain fixed from known calibration data.

| Population | Method | Unknown AUROC | Unknown AP | OSCR AUC |
|---|---|---|---|---|
| pooled | msp | 0.517 | 0.536 | 0.115 |
| pooled | energy | 0.580 | 0.525 | 0.144 |
| pooled | mahalanobis | 0.408 | 0.480 | 0.108 |
| intermittent_bursts | msp | 0.514 | 0.233 | 0.111 |
| intermittent_bursts | energy | 0.604 | 0.255 | 0.146 |
| intermittent_bursts | mahalanobis | 0.347 | 0.180 | 0.097 |
| pulsed | msp | 0.507 | 0.231 | 0.111 |
| pulsed | energy | 0.611 | 0.258 | 0.146 |
| pulsed | mahalanobis | 0.340 | 0.179 | 0.090 |
| swept_cw | msp | 0.479 | 0.346 | 0.104 |
| swept_cw | energy | 0.444 | 0.219 | 0.118 |
| swept_cw | mahalanobis | 0.556 | 0.379 | 0.139 |
| wideband_noise | msp | 0.569 | 0.269 | 0.132 |
| wideband_noise | energy | 0.660 | 0.301 | 0.167 |
| wideband_noise | mahalanobis | 0.389 | 0.193 | 0.104 |

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
| unknown_test | 24 | 12 |

Source data complete: `False`.
Experiment fingerprint: `ae8f9181586ab419d685868231a3e4cfd2a6d5242b24924251a4edcc9d5b14f8`.

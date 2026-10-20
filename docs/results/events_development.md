# Phase-noise and interference development run

Protocol `E1-dev/1`; labels: clean, carrier_under_carrier, adjacent_satellite.

All paired labels share carrier plans, link settings and phase-noise realizations.
Carrier-under-carrier is injected before the wanted payload; adjacent-satellite interference is added at the receiver.
These simulator causes are not uniquely identifiable from PSD observations. No orbital or antenna model is fitted.

| View | Channels | Classification accuracy | Macro-F1 | Clean false alarm | Pooled event detection |
|---|---|---|---|---|---|
| co | 2 | 33.3% | 0.167 | 16.7% | 16.7% |
| dual | 4 | 33.3% | 0.167 | 66.7% | 66.7% |

Classification uses argmax. Event alarms use sum of non-clean softmax probabilities,
with a threshold fitted only on separate clean calibration groups. This is a closed-set development task.
Detection positive class is any event; denominators below contain only that event family.

| View | Event family | Alarm rate | Samples | Scenario groups |
|---|---|---|---|---|
| co | carrier_under_carrier | 16.7% | 6 | 6 |
| co | adjacent_satellite | 16.7% | 6 | 6 |
| dual | carrier_under_carrier | 66.7% | 6 | 6 |
| dual | adjacent_satellite | 66.7% | 6 | 6 |

Intervals in JSON resample scenario groups at fixed weights/thresholds; training-seed uncertainty is not included.
Tiny calibration sets cannot establish the requested operational false-alarm rate. This pilot checks execution, not recognition quality.
The final eight-known-class dual-polarization open-set benchmark remains outstanding.

## Partitions

| Role | Samples | Scenario groups |
|---|---|---|
| train | 18 | 6 |
| validation | 9 | 3 |
| calibration | 9 | 3 |
| test | 18 | 6 |

Experiment fingerprint: `00e01cc0592adb31c03d8f7e4b08867fd9b22dab5e7c64404c5e69ffe71a2ea2`.

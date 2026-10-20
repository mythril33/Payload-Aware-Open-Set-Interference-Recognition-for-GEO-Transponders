Recorded on 2026-10-20. This three-epoch physical smoke run generated 36 paired dual-polarization observations. It validates execution, not recognition quality.

Reproduce with [P14](../plan/P14_dual_polarization.md). [Full metrics](dual_development.json), [per-event predictions](dual_predictions.json), [synthetic calibration diagnostic](dual_calibration_check.json).

# Dual-polarization leakage development run

Protocol `D1-dev/1`; known labels: clean, cross_pol.

The labels describe a controlled uplink-XPD change in the simulator, not a uniquely identified operational cause.
Receiver calibration is fitted from independent instrument pilots; physical propagation leakage is retained.
Both spectra share the co-polarization power reference. Dual input uses both spectra and both carrier-plan masks.

| View | Input channels | Classification accuracy | Macro-F1 | Clean false alarm | Cross-pol detection |
|---|---|---|---|---|---|
| co | 2 | 50.0% | 0.333 | 50.0% | 50.0% |
| dual | 4 | 50.0% | 0.333 | 50.0% | 66.7% |

Classification uses argmax. Alarm rates use a separate threshold fitted to clean calibration groups.
The target clean false-alarm rate need not hold on new test samples, especially with tiny calibration sets.
Intervals in JSON resample scenario groups at fixed trained weights and thresholds; multiple training seeds are still needed.
This small matched-input comparison validates execution, not a claim that dual-pol recognition is superior.

## Partitions

| Role | Samples | Scenario groups |
|---|---|---|
| train | 12 | 6 |
| validation | 6 | 3 |
| calibration | 6 | 3 |
| test | 12 | 6 |

Experiment fingerprint: `9541c31f7aacaa89441cea3de7de709913481edccf9f8dd0c0eaa8c63dfa864c`.

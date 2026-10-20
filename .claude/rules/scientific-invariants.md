---
description: Frozen scientific contracts that no implementation convenience may override
---

# Scientific invariants

1. **No oracle inputs.** Observable model channels are calibrated PSDs, operator plan
   masks and the observation-based cancellation residual (`geosim.cancellation`,
   inputs: co-pol monitor IQ + co-pol operator plan). Activity masks, realized
   IBO/OBO, XPD, C/I, linewidths, labels, event parameters and transmitted
   symbols are simulator truth and stay in metadata.
2. **Frozen protocols.** A1 (P5), B1-dev, D1-dev, E1-dev, R1-eval/1 (P17), B2/1 (P18)
   and the artifact stages B2-base/1 (P19) and B2-feat/1 (P20) keep their seeds,
   labels, counts and request layouts. Changed semantics need a new version name
   and a P18 §10 log entry; frozen commitments need researcher approval.
3. **Roles.** train → weights and Mahalanobis statistics; val-select → checkpoint
   only; val-calib → thresholds from known classes only; test → evaluated once.
   Test-only families never touch training, selection or calibration.
4. **Metric hygiene.** Unknown scores: larger = more unknown-like. Every reported
   rate names its positive class, denominator and sample/group counts. Missing
   metrics are `null` with counts. Grouped (scenario) bootstrap, never i.i.d. CIs
   on paired variants.
5. **Honest status.** A pilot is a pilot. Passing tests prove execution, not
   recognition quality. Negative or inconclusive results are kept.

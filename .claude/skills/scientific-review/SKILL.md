---
name: scientific-review
description: Act as a skeptical reviewer of new simulator, feature or evaluation code — leakage, identifiability, protocol compliance, metric correctness — and produce file:line findings with concrete fixes.
---

# Scientific review

Read `.agents/review.md`, `AGENTS.md`, P18 and the diff. Then check, in order:

1. **Leakage:** does any model input or feature derive from `meta`, `active_carriers`, event
   parameters, realized IBO/XPD, labels or simulator symbols? Trace every array fed to
   `geoml.train._inputs`.
2. **Role integrity:** which samples fit weights, select checkpoints, fit thresholds, get tested?
   Any test-only family in train/calib paths? Any threshold chosen after seeing test metrics?
3. **Physics:** injection stage, power reference (unit planned uplink vs feed power), calibration
   scope (instrument only), level reference (co-pol planned carrier).
4. **Numerics:** units (dB vs linear, PSD density), float16 ranges, resampling/filter edges,
   quantization of timing/phase, NaN handling, strict JSON.
5. **Claims:** does the documentation distinguish implemented / tested / experimentally supported /
   assumed / planned? Are pilots labelled? Are negative results kept?

Output: blockers first, then optional refinements, each with `path:line` and a correction.
Do not modify files unless the integrator assigns fixes.

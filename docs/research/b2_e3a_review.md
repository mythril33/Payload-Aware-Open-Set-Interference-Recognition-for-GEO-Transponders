# E3a independent scientific review — 2026-10-22

Scope: read-only review of `edsc.py`, `b2_edsc.py`,
`b2_edsc_metrics.py`, their tests and [P26](../plan/P26_b2_e3a_edsc_baseline.md),
following [.agents/review.md](../../.agents/review.md). A separate agent inspected
the resulting code and ran focused tests; it did not implement fixes.

Material findings resolved before delivery:

1. Evaluation provenance originally checked only the known-data fingerprint,
   physics and cancellation. The runner now compares the complete kind-specific
   known binding (request, protocol, test groups or known roles, independent
   receiver calibration) and direct calibration equality. Negative tests mutate
   each binding component and refuse it before evaluation scoring.
2. Comparison bundles originally lacked a mandatory scorer identity. They now
   require a method-specific identity and check binary metric protocol,
   clean-calibration identity, threshold equality and report denominators against
   ordered sample IDs. This rejects foreign known-acceptance/classifier reports.
3. Integration inspection caught omitted optional sample-ID keys and threshold
   metadata; these were fixed and exercised in known-only and comparator runs.

The independent re-review found no remaining material blocker in the bounded
slice. Verified boundaries: scoring sees only observed arrays; labels select
clean val-calib rows only; no test fit/tuning; larger scores mean more anomalous;
alarms use strict `>`; unknown rankings use all known test scenes as negatives;
bootstrap preserves scenario pairing; matched detection preserves global labels
and frozen bins; unsupported classifier metrics remain null.

Independent command:

```bash
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 \
  /workspace/.venvs/geosim/bin/python -m pytest -q \
  tests/test_edsc.py tests/test_b2_edsc_metrics.py tests/test_b2_edsc.py
```

Result: **46 passed in 15.89 s**. `git diff --check` passed. This is a separate
focused verification, not the full-suite result in the [results note](../results/b2_edsc_baseline.md).

Remaining scientific limits: two clean calibration samples cannot verify a 5%
population Pfa; group bootstrap excludes calibration/physics uncertainty;
P20 cancellation errors and phase-noise depth ceiling remain. External neural
providers must supply a truthful identity for their frozen model/scorer; this
interface does not authenticate a third party's asserted checkpoint contents.

An additional numerical audit recomputed every saved evaluation score directly
from raw NPZ arrays, without importing geosim/geoml/scorer helpers. It used a
manually constructed frequency grid, direct float64 linear-power means and a
sorted higher-quantile index. All 32 evaluation scores and ordered IDs matched;
maximum difference was **2.13e-14 dB**. Threshold difference was **7.11e-15 dB**;
calibration 0/2, test-clean 1/2 and event 13/14 alarms were independently confirmed.
The reviewer's original process took 0.811 s / 27,756 KiB peak RSS. Its exact
body is retained as [check_b2_edsc_smoke.py](../../scripts/check_b2_edsc_smoke.py).

The integrator executed that retained script separately:

```bash
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 \
  /workspace/.venvs/geosim/bin/python scripts/check_b2_edsc_smoke.py
```

Exit 0; subprocess wall **0.316785 s**, peak RSS **27,736 KiB**. This script is
specific to the documented existing smoke artifacts and their recorded counts;
it is arithmetic evidence after artifact validation, not an alternative artifact
validator or a population-performance test. Neither audit reruns the detector,
generates observations or fits a model.

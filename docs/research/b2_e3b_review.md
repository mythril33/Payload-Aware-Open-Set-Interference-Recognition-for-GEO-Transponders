# E3b independent scientific review — 2026-10-23

Scope: read-only review of `b2_expert.py`, `b2_xgb_model.py`,
`b2_xgb.py`, `b2_xgb_metrics.py`, their tests, fixed configuration and
[P27](../plan/P27_b2_e3b_xgboost_baseline.md), following
[.agents/review.md](../../.agents/review.md). The feature, model and metric
implementers were separate from the reviewer. This is engineering review
within the agent workflow, not external scientific endorsement.

P27 was registered in commit `c58572c47ee02c050916eb3abcce84a22e858f0f`
before implementation, fitting or test evaluation. The review checks its
26-feature order, units and arithmetic; the observation-only input boundary;
train-only statistics/fitting; val-select-only fixed prefix choice; clean
val-calib calibration; distinct binary and MSP/OSCR scores; denominators,
paired bootstrap, dependency/budget caps and native-checkpoint provenance.

The reviewer found no material formula or score-direction blocker in the
initial source inspection. The integrator strengthened reuse by comparing
the saved fitted train/selection populations against the exact current
verified source IDs before calibration, beyond the model's internal
metadata/native binding. A negative test covers this cross-check. Final
read-only re-review found **no remaining material blocker** in the bounded
slice. It confirmed observation-only features, the fixed CPU budget,
train/selection/calibration boundaries, score directions, class-versus-alarm
semantics, group bootstrap and failure on corrupt/incompatible state.

Independent command actually executed:

```bash
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 MPLBACKEND=Agg \
  /workspace/.venvs/geosim/bin/python -m pytest -q \
  tests/test_b2_expert.py tests/test_b2_xgb_model.py \
  tests/test_b2_xgb_metrics.py tests/test_b2_xgb.py
```

Result: **63 passed in 12.67 s**, exit 0. Subprocess wall was
**13.675130 s**, peak RSS **565,668 KiB**. This is the independent focused
verification, separate from the integrator's run, full suite and bounded
pilot in the [results note](../results/b2_xgb_baseline.md).

The integrator separately completed the full repository regression:
**1086 passed, 1 skipped, 0 failed in 316.76 s**. The existing E1 RSS test
was skipped because `/proc/self/clear_refs` reset is unsupported on this
runner. This is not claimed as an independent full-suite rerun; its exact
command and resource evidence are in the results note.

A separate numerical audit checked all 26 features on the first three
existing raw train observations. Its independent reference used direct
float64 power sums/log-ratios, direct `sum(P*f)/sum(P)` centroids,
temporal SD/mean and geometric means, without feature helpers. Maximum
absolute discrepancy was **1.1324274851176597e-14**, at
`residual_steady_peak_db`. No fitting, calibration or test selection occurred.
The original computation took **0.043693 s**; original whole-process wall
was **1.672313 s**, peak RSS **85,672 KiB**, exit 0. This is arithmetic
validation, not detection-performance evidence. Its reference computations
use no extractor helpers; the separately called production extractor is
compared with those independently calculated values.

The exact retained body is
[check_b2_xgb_features.py](../../scripts/check_b2_xgb_features.py). The
integrator separately executed:

```bash
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 \
  /workspace/.venvs/geosim/bin/python scripts/check_b2_xgb_features.py
```

Exit 0; subprocess wall **1.947051 s**, peak RSS **85,668 KiB**, with the
same maximum discrepancy. This script checks three existing train rows,
not test-selected scenes. It fits neither a model nor a threshold and
does not generate observations or rerun the detector pilot.

Remaining scientific limits are unchanged: two clean calibration samples
cannot validate a 5% population Pfa; bootstrap fixes the already fitted
scorer/threshold and omits training/calibration/physics uncertainty; P20
cancellation depth/errors and missing-carrier normalization remain. No
researcher or production gate is approved by this review.

The reviewer also inspected actual PR14 CI job120327984394 logs:
run39927676691 failed before tests because Python3.11 cannot install the
pinned xgboost-cpu3.4.1 (requires Python>=3.12). Read-only review of the
follow-up confirmed that only the CI Python version and environment
documentation changed: dependency pin, gate assertions, compile and full
test commands, source/tests, features, score/threshold and budget stayed
intact. No conditional dependency skip or weakened check was introduced.
Final-head remote verification is reported separately in the PR.

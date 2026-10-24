# E10 change note — R10 clean-alarm threshold: higher empirical quantile

**Finding:** PR #30 audit item M-1 (`docs/research/B2_E9_INDEPENDENT_SCIENTIFIC_AUDIT.md`).
**Baseline:** `origin/main` `e43987e`.
**Approved rule:** `docs/plan/b2_e9_approved_scientific_protocol.json:334` — "higher empirical quantile, inclusive acceptance";
alarm strictly `score > threshold` (`docs/plan/B2_E9_SCIENTIFIC_DECISION_APPROVAL_2026-10-24.md`, R10).

## What was wrong

`src/geoml/metrics.py` `threshold_at_pfa` returned `np.quantile(clean_scores, 1 - pfa)` with NumPy's default linear
interpolation. The E9 calibrate path (`src/geoml/b2_execution.py`, the clean-alarm threshold written to `alarm_<view>.json`)
used that helper. The approved rule is the higher empirical quantile, which never interpolates between samples.
Rejection thresholds already used `method="higher"` (`src/geoml/calibration.py:131`), so the two thresholds were computed
differently.

## What changed

| File | Change |
|---|---|
| `src/geoml/metrics.py` | New `clean_alarm_threshold(clean_scores, pfa)`: explicit `method="higher"`; refuses empty, multi-dimensional, non-finite scores and `pfa` outside (0,1), booleans and strings. New constant `CLEAN_ALARM_QUANTILE_METHOD = "higher"`. `threshold_at_pfa` is **unchanged** in value and labelled HISTORICAL. |
| `src/geoml/b2_execution.py` | The E9 calibrate path imports and calls `clean_alarm_threshold` (line 313). The alarm score is `clean_alarm_score` (defined at line 43): the sum of the non-clean probabilities, which equals `1 - P(clean)` without the subtraction. The subtraction rounds to exactly 0 once the clean margin exceeds about 37 nats, so confidently clean samples would tie. The evaluate path (line 520) uses the same helper. `ALARM_RULE` changes to `"R10 higher empirical quantile at 1-pfa (clean_alarm_threshold); alarm strictly score > threshold"`. |
| `tests/test_b2_execution.py` | The isolation test that forbids calibration during evaluation now also monkeypatches `clean_alarm_threshold`. |
| `tests/test_b2_e10_calibration.py` | New regression tests (see below). |

No threshold value was tuned, and no test result was used to choose the method.

## Historical behaviour and labelling (not relabelled)

- Archived results produced with the linear rule keep their meaning. Their alarm records carry the old `rule` string
  (`"P20 threshold_at_pfa; alarm strictly score > threshold"`), so `_verify_calibration` refuses them under the new
  `ALARM_RULE`. Nothing is silently reinterpreted; a historical calibration must be regenerated in a fresh directory.
- Frozen stages keep `threshold_at_pfa` by design, because changing it would relabel frozen protocols (A1, R1-eval/1,
  B2-A5-eval/1, B2-observed-dev/1, dual development). Their call sites are listed below and remain historical:

| Call site | Stage | Status |
|---|---|---|
| `src/geoml/pipeline.py:67` | stage A learning pipeline (P6/P7) | historical, linear |
| `src/geoml/robustness.py:129` | R1-eval/1 robustness | frozen protocol, linear |
| `src/geoml/dual_experiment.py:172` | dual development (D1-dev) | historical, linear |
| `src/geoml/b2_observed_experiment.py:180` | B2-observed-dev/1 | historical, linear |
| `src/geoml/b2_a5.py:220` | B2-A5-eval/1 (E4 dual-pol A5) | frozen; the linear helper is applied to the subtraction score `1 - P(clean)` (closure E-10). A5 results hold only under their recorded rule |
| `src/geoml/b2_experiment.py:522` | legacy coupled pilot (the default of `--mode`, `b2_experiment.py:788–789`) | historical, not the E9 path. The default mode reads the test role (packet D-7) |
| `tests/test_ml.py:46` | asserts the linear value 94.05 | kept to guard the historical behaviour |

- The change alters the source fingerprint of `src/geoml`. Earlier checkpoint reuse is refused by the existing provenance
  checks; that is the intended behaviour, not a new failure mode.
- The committed P31 evidence (`docs/results/b2_e7b_execution.json`) records the SHA-256 of `src/geoml/b2_execution.py` as
  `edd4fb81…800265` (lines 18 and 78). That equals the `e43987e` file, which uses `threshold_at_pfa` and the rule string
  `P20 threshold_at_pfa` (verified with `sha256sum`). The E7b evidence was therefore produced by the linear-rule executor and is
  historical (closure E-11). Source-hash provenance refuses any reuse of its checkpoints under this branch.

## Regression tests (`tests/test_b2_e10_calibration.py`)

- Hand value: `clean_alarm_threshold(arange(100), 0.05) == 95.0` (index `ceil(0.95 * 99) = 95`), while the historical helper gives 94.05.
- Result is an order statistic of the calibration scores (never interpolated); strict alarm rate on calibration scores is at most Pfa.
- Monotone in Pfa.
- Equal scores: threshold equals that score and strict `>` raises no alarm on ties; plateau at the threshold is not an alarm.
- Small samples (n = 1, 2, 20) give the largest value at the higher index.
- Order of inputs does not matter.
- Refusals: empty, two-dimensional, NaN, +inf, -inf scores; Pfa of 0, 1, -0.05, 1.5, NaN, True, a string, None.
- Acceptance and clean-alarm thresholds are computed on distinct populations (a worked example where they differ).
- Leakage: `b2_stream._require` refuses val-calib, test and test-matched sources as training data, and refuses val-select
  as training data.
- Calibrate path: `open_b2_known_roles` is called exactly once, with `("val-calib",)`, and the calibrate body contains no
  test-role literal. The calibrate body calls `clean_alarm_threshold` and not `threshold_at_pfa`.
- The alarm rule label changed, so historical alarm records fail verification.
- Saturation: a clean sample with a 40-nat and a 45-nat clean margin gets a strictly positive, ordered score, while
  `1 - P(clean)` by subtraction returns exactly 0 (`test_saturated_clean_margin_keeps_a_positive_score_and_its_ordering`).
- Both alarm call sites (calibrate and evaluate) use `clean_alarm_score` and not `1.-probabilities`
  (`test_both_alarm_call_sites_use_the_saturation_free_score`).

## Non-goals

No change to R1–R10, to any frozen protocol, to any approved configuration, or to any gate. The change does not start,
enable or authorize any executor, and it does not make any historical result pass the new rule.

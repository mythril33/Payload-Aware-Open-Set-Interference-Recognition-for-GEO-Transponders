# B2 E3b expert-feature/XGBoost baseline — bounded verification

Date: 2026-10-23. Branch: `feature/b2-e3b-xgboost-baseline`.
Protocol: [P27 B2-XGB/1](../plan/P27_b2_e3b_xgboost_baseline.md),
feature schema `B2-expert/1`. P27 was committed as
`c58572c47ee02c050916eb3abcce84a22e858f0f` before E3b implementation,
fitting or test evaluation. The feature definitions, score meanings,
selection budget and role rules were fixed before pilot outcomes.

This is an engineering baseline and tiny CPU pilot. Arithmetic checks,
successful execution and fitted predictions are distinct from statistically
meaningful detection or generalization performance. `benchmark_complete=false`.

## Scope and scientific boundary

`geoml.b2_expert` computes exactly 26 fixed features from calibrated co/cross
spectra, their operator masks and the stored P20 `obs-cancel/1` residual.
The extractor accepts those three arrays only. It uses linear PSD means on
the canonical 128 × 512 grid and 193 in-band bin centres; all three streams
share the observed co-pol operator-core power reference. Simulator truth,
event/source parameters, activity, symbols, true IBO/XPD/C-I and geometry
are excluded from features. P21b is not substituted for the P20 receiver.

`geoml.b2_xgb_model` uses pinned `xgboost-cpu==3.4.1`, CPU histogram trees,
one XGBoost thread, seed 0 and the fixed
[`configs/b2_xgb_smoke.json`](../../configs/b2_xgb_smoke.json) budget.
Only train rows fit per-feature means/population SDs and one 16-round
booster. A zero train SD maps to scale 1. Only the predetermined 8/16-round
prefixes are compared on val-select macro-F1; ties select 8 rounds. There
is no test-driven feature, hyperparameter or threshold choice.

`geoml.b2_xgb` streams verified E1 shards into small feature tables. It
requires complete role-bound paired groups and the canonical P20 artifact
stage, cancellation settings and known/test/matched provenance. Whole-role
spectrogram concatenation is absent. The cap is 32 groups per role and
256 observations per shard; smoke is capped at two groups per role.

Native UBJ model and strict JSON metadata bind feature/class order,
normalizer, selected prefix, dependency/configuration, populations, source
and artifact identities. Reuse checks file and native-model hashes,
attributes and expected provenance; it also compares fitted population IDs
and train statistics against the current verified sources. Incompatible,
corrupt, partial or foreign outputs fail closed. Checkpoints, raw data and
runtime predictions remain outside Git.

## Predictions and comparison semantics

The eight-class predictor is the first argmax in frozen P18 label order.
Closed known-test accuracy, macro-F1, confusion and per-class recall use
explicit counts. Matched classifier decisions use the actual global
clean/ASI/unauthorized labels and eight possible prediction columns.

The operational binary score is **A = 1 − P(clean)**, higher means more
anomalous. Its threshold uses only clean known val-calib rows: the higher
empirical 95th percentile, with alarm strictly above threshold. Nominal
Pfa is 5%; achieved calibration and test-clean alarm counts are separate.
Two clean calibration samples have 50-percentage-point empirical resolution
and cannot establish empirical/population Pfa = 5%.

EDSC and planned/blind CA-CFAR use the same bounded artifacts, ordered
evaluation rows, clean calibration IDs and threshold rule through the P26
score-bundle contract. Unknown-positive binary rankings compare unknowns
with all known test scenes, including known interference. Near families
are pooled; benign CID and equivalence-limited noise retain separate rows.
Neural known-acceptance thresholds are not treated as clean-Pfa thresholds.

Classifier open-set reporting instead uses **U = 1 − max P**, the fixed MSP
unknown score. Its OSCR uses actual eight-class correctness and all known
test scenes as denominator. No operating threshold is fitted for U. These
MSP/OSCR results are labelled separately from A-based anomaly rankings.
EDSC retains null class predictions, multiclass accuracy and OSCR.

Scenario-group bootstrap resamples paired variants together with scorer and
threshold fixed. It excludes training, calibration and physical-model
uncertainty. Empty or insufficient-group metrics are strict JSON nulls with
counts/reasons. Tiny or degenerate intervals are not population guarantees.

## Verification evidence

Environment: Linux 6.18.55 x86_64, three allocated CPUs; Python 3.12.14,
NumPy 2.5.4, SciPy 1.18.1, PyTorch 2.14.1+cpu, pytest 9.1.1 and
`xgboost-cpu==3.4.1`. OMP/OpenBLAS/MKL threads were capped at two; XGBoost
itself uses the fixed single CPU thread. No GPU was used.

Focused command actually executed:

```bash
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 MPLBACKEND=Agg \
  /workspace/.venvs/geosim/bin/python -m pytest -q \
  tests/test_b2_expert.py tests/test_b2_xgb_model.py \
  tests/test_b2_xgb_metrics.py tests/test_b2_xgb.py
```

Result: **63 passed in 10.74 s**, exit 0. Measured subprocess wall was
**11.564690 s**, peak RSS **565,524 KiB** (552.27 MiB). The measurement
includes interpreter/import overhead and is not a production memory ceiling.
The focused evidence also records SHA-256 values for the exact four source
modules, four test modules, fixed config, dependency file and CI workflow.
During test-driven implementation, missing-module collection errors occurred
before modules existed; an intermediate integration run had 62 passes and
one temporary test `NameError`. It was corrected before the final passing
run. No failed check is represented as a pass.

Full repository command actually executed:

```bash
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 MPLBACKEND=Agg \
  /workspace/.venvs/geosim/bin/python -m pytest -q -rs
```

Result: **1086 passed, 1 skipped, 0 failed in 316.76 s**, exit 0.
Subprocess wall including startup was **318.507409 s** (5 min 19 s), maximum
process RSS including waited descendants **1,285,020 KiB** (1254.90 MiB),
not simultaneous aggregate memory. The same 11 source/test/config/dependency/
workflow hashes recorded by the final focused run remained unchanged through
this full-suite check. Exact measurements are retained from
`/tmp/b2-e3b-evidence/full.json` and the `-rs` log.

The one skip was the existing
`tests/test_b2_stream.py::test_streaming_peak_memory_stays_below_the_whole_dataset_footprint`,
at line 421: this runner does not permit resetting its peak RSS through
`/proc/self/clear_refs`. It is a skipped E1 comparative memory check,
not a pass. The separately measured E3b pilot RSS does not replace that
comparison. No new E3b test was skipped. This full regression was run by
the integrator; the independent reviewer's separate check was focused.

Disk integration fixtures use the real artifact writer/validator/streaming
reader with stand-in physics and cancellation; their results are not RF
evidence. A separate bounded pilot uses existing verified physical artifacts
and does not generate a new dataset.

The [independent review record](../research/b2_e3b_review.md) separates
read-only source review, focused verification and direct feature arithmetic
from pilot measurements. The standalone numerical audit checked all 26
features on three existing raw train observations, without fitting,
calibration or test-based selection; the reported maximum discrepancy was
`1.1324274851176597e-14`. Its original process wall was 1.672313 s and peak
RSS 85,672 KiB. The retained audit is
[`scripts/check_b2_xgb_features.py`](../../scripts/check_b2_xgb_features.py).
The integrator executed it with the prepared Python and thread caps:
exit 0, subprocess wall **1.947051 s**, peak RSS **85,668 KiB**. It reads
existing train arrays and checks arithmetic without model fitting.

Independent final focused verification used the same four-test-file command:
**63 passed in 12.67 s**, exit 0; subprocess wall **13.675130 s**, peak RSS
**565,668 KiB**. Read-only re-review found no remaining material blocker
after the fitted-population/source cross-check was strengthened. See the
review record for the scope and remaining scientific limits.

## Strictly bounded existing-artifact pilot

Command actually executed:

```bash
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 MPLBACKEND=Agg \
  /workspace/.venvs/geosim/bin/python -m geoml.b2_xgb \
  --config configs/b2_xgb_smoke.json --data data/b2-readiness-known \
  --unknown-data data/b2-readiness-test --matched-data data/b2-readiness-matched \
  --out runs/b2-e3b-xgb-smoke --smoke --with-baselines --bootstrap 200
```

Exit **0**, subprocess wall **5.535426 s**, peak RSS **258,400 KiB**
(252.34 MiB). The runner's internal timer was **2.205541 s** and reached
the frozen model at **0.563917 s**, excluding interpreter/import startup.
The high-water mark includes imports, validation and inference; it is not
a production memory ceiling. Evidence is retained from
`/tmp/b2-e3b-evidence/pilot.json`; raw results, model and predictions remain
outside Git under the run directory.

This command reused existing physically simulated observations, with no new
RF waveform or dataset generation: 64 known observations, comprising 16 in
each of train, val-select, val-calib and test; ten test-only observations
and six matched observations. Each role has two scenario groups. Only 16
train rows fit the normalizer/booster; 16 val-select rows choose its prefix.
Only the **two clean** rows within val-calib calibrate the alarm. No rows
were silently truncated.

Run identity:
`c06131ba304023f17a0bce6f3f1963eb63d3f52bf6d9be26402bbcd8c4a6029a`.
Fitted scorer identity:
`04470e870756e2aa26ab06c1fe2e2f7065da7e7c2a42a716eb1b44bb326e09d9`.
All artifact/source identities are in the strict JSON record. The fixed
val-select candidates had macro-F1 **0.591667** at 8 rounds and **0.650000**
at 16 rounds; the prescribed rule selected **16 rounds**. This is execution
of the registered selection rule, not a quality claim or a further search.

## Pilot outputs, not recognition-performance evidence

The XGBoost A-score threshold was **0.7279759645462036**, with strict
`A > threshold`. Nominal Pfa remains **5%**; achieved calibration alarms
were **0/2**, while test-clean alarms were **1/2**. Neither rate verifies
population Pfa = 5%.

| XGBoost A-score population | Alarms / denominator | Conditional bootstrap 95% interval |
|---|---:|---|
| Known test clean | 1/2 | [0,1] |
| Known test non-clean | 13/14 | [0.8571,1] |
| Pooled near unknowns | 4/6 | [0.3333,1] |
| Benign CID control | 2/2 | [1,1] |
| Separate wideband noise | 2/2 | [1,1] |

Each known non-clean class had 2/2 alarms except ASI, with 1/2. Family
alarms were pulsed 1/2, intermittent bursts 2/2 and downlink ASI 1/2.
The benign CID false alarms remain visible rather than being counted as
correct unknown detections. Degenerate intervals arise from identical
outcomes in the observed groups and do not establish perfect sensitivity.

For binary A ranking of six near unknowns against all 16 known test scenes,
AUROC was **0.375000** (bootstrap **[0.1667,0.5833]**), AP **0.293831**
(**[0.2374,0.5536]**) and FPR@95TPR **1.000000** (**[0.625,1]**).
Known interference is a negative population for this unknown-identity
ranking while being a positive anomaly case at the operating threshold;
these are distinct questions.

| Common binary scorer | Test-clean alarms / n | Event detections / n | Near AUROC / AP / FPR95 | Matched ASI / unauthorized detections |
|---|---:|---:|---|---|
| XGBoost A | 1/2 | 13/14 | 0.375000 / 0.293831 / 1.0000 | 2/2 / 2/2 |
| EDSC | 1/2 | 13/14 | 0.343750 / 0.280612 / 0.9375 | 0/2 / 0/2 |
| Planned CA-CFAR | 1/2 | 11/14 | 0.270833 / 0.217444 / 0.8125 | 0/2 / 2/2 |
| Blind CA-CFAR | 2/2 | 11/14 | 0.541667 / 0.327859 / 0.6875 | 1/2 / 1/2 |

All four scorers used the same two clean calibration rows and achieved
0/2 calibration alarms, with their own frozen thresholds. These are common
interface execution outputs, not a statistically supported method ordering.
The XGBoost matched unauthorized-minus-ASI alarm difference was **0**,
with descriptive interval **[0,0]**. There was one complete pair in each of
`[4,7)` and `[7,10)` dB and none in `[10,13]`; individual-bin intervals
are null for insufficient groups, and empty rates are null. Score gaps
retain method-specific units and are not compared across scorers.

The separate eight-class predictor correctly labelled **6/16** known test
observations (**0.375**, interval **[0.25,0.5]**), with macro-F1 **0.255556**
(**[0.1190,0.3750]**). Per-class correct counts were clean 1/2, CW 0/2,
swept CW 0/2, unauthorized 1/2, overdrive 2/2, cross-pol 2/2, ASI 0/2 and
carrier-under-carrier 0/2. Matched closed-set accuracy was **2/6**. These
class decisions are separate from the matched anomaly alarms.

For **U = 1 − max P**, the same near/all-known population gave AUROC
**0.614583**, AP **0.413194**, FPR95 **0.750000** and OSCR AUC **0.322917**,
using actual multiclass correctness and all 16 known scenes in the OSCR
denominator. Its conditional OSCR interval was **[0.25,0.4583]**. No U
operating threshold was fitted. EDSC's classifier fields remain null.
These tiny-population MSP values do not justify changing A's direction,
features, thresholds or the frozen tree budget.

## E3a evidence retained separately

E3a implementation PR #11 and four-document delivery PR #12 are merged.
Their actual remote CI results were independently checked:

| Evidence | Head | Run / job | Actual result |
|---|---|---|---|
| E3a implementation | `ec47a90…` | 39921568709 / 120307794277 | 1024 passed, 0 skipped, 249.90 s |
| E3a delivery records | `bb589b4…` | 39922726893 / 120311592843 | 1024 passed, 0 skipped, 223.50 s |
| E3a status corrections | `8603336…` | 39924198169 / 120316469704 | 1024 passed, 0 skipped, 236.38 s |

The earlier local E3a result remains 1023 passed plus one skipped E1 RSS
comparison: that environment could not reset `/proc/self/clear_refs`.
GitHub supported the RSS check. No local skip is rewritten as a pass.
See the [E3a report](b2_edsc_baseline.md) for the distinct recorded runs.
Adding E3b modules changes the broad source-identity map; it does not make
the historical E3a smoke or checkpoint provenance equal to the expanded tree.

## Limits and remaining work

The physical simulator, observed cancellation and operator-plan assumptions
are inherited. The P20 residual includes cancellation error, nonlinear
payload distortion, leakage and its approximately 21–25 dB phase-noise depth
ceiling. Carrier normalization can change with interference or missing
planned carriers, and whole-band features can dilute short/local events.
No result establishes field performance, unique physical origin,
authorization inference or a completed eight-class benchmark.

K18, K17d and OBS-CANCEL/2 remain pending researcher decisions. Full data
generation, GPU training, full LOKO and A5 development were not authorized
or run. E3b implementation and a successful bounded pilot do not grant
production approval. Larger representative calibration/evaluation populations,
approved full-scale work and physical-model sensitivity analysis remain.

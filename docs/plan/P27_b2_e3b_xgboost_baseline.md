# P27 — E3b observation-only expert features and XGBoost baseline

Registered 2026-10-23 before E3b implementation, fitting or test evaluation.
Parent: frozen P18, P23 and P26 section9. Protocol **B2-XGB/1**;
feature schema **B2-expert/1**. This is a bounded engineering pilot, not a
completed benchmark. `benchmark_complete=false`. K18, K17d and OBS-CANCEL/2
remain pending; no full generation, GPU, full LOKO or A5 work is authorized.

## 1. Inputs and fixed feature schema

Only canonical verified B2-feat/1 and its bound B2-test/1/B2-match/1 stages
are accepted. Cancellation remains the exact P20 obs-cancel/1 settings.
The pure extractor signature is `extract_features(spec, mask, residual)`:
spec[N,2,128,512], mask[N,2,512], residual[N,128,512]. Simulator metadata,
symbols, activity, source/event parameters, true IBO/XPD/C-I, geometry and
oracle residuals cannot enter the extractor. P21b is incompatible.

Grid: 96MHz/512 FFT, all128 snapshots equally weighted, 193 bin centres
with |f|<=18MHz. Convert dB PSD to strictly positive finite float64 linear
PSD; average powers, never dB. Operator core is mask>-3dB within this band;
noncore is its complement, including roll-off bins. Both regions are
required for both plans. The common reference R is observed co-pol PSD
averaged over its core and time. No clipping/floor or learned band selection.

For streams in exact order **co, cross, residual**, residual uses the co
operator mask. Each contributes these eight features in this exact order:

| Suffix | Definition | Unit |
|---|---|---|
| band_level_db | 10log10(mean over time/band PSD / R) | dB |
| core_level_db | 10log10(mean over time/operator-core PSD / R) | dB |
| noncore_level_db | 10log10(mean over time/noncore PSD / R) | dB |
| steady_peak_db | 10log10(max frequency of time-mean PSD / band mean PSD) | dB |
| transient_peak_db | 10log10(max time-frequency PSD / band mean PSD) | dB |
| temporal_cv | population SD of per-snapshot band-mean PSD / its mean | dimensionless |
| spectral_flatness | geometric mean of time-mean PSD across band / arithmetic mean | dimensionless |
| centroid_std_mhz | population SD across snapshots of PSD-weighted frequency centroid | MHz |

Full names are stream + underscore + suffix, followed by
**co_core_fraction**, **cross_core_fraction** (core-bin count/193,
dimensionless). Thus exactly26 features with fixed order, names and units.
All calculations are observation-derived. Unsupported/empty/nonfinite powers,
grids or feature rows fail closed. Whole-band averages may dilute localized
events; normalization can change under interference or missing carriers.

## 2. Roles, CPU dependency and fixed budget

Frozen P18 roles/groups/classes are unchanged. All eight paired known
variants remain in their single role. Feature matrices and identifiers are
small O(N*26); verified E1 shards are processed separately and spectra are
never concatenated across a role. The stage readers/checks from E3a may be
reused without changing their semantics. Cap32 groups/role and256 samples/shard;
executed smoke cap2 groups/role. No data generation path or GPU option.

Pin **xgboost-cpu==3.4.1**, imported as xgboost. Runtime version must match.
Seed0, nthread1, CPU hist, objective multi:softprob, num_class8, max_depth2,
eta0.3, max_bin64, subsample1, colsample_bytree1, min_child_weight1,
lambda1 and alpha0. Train one16-round booster, using only train rows.
Only the predetermined prefix candidates8 and16 rounds are eligible.
Select largest known-class macro-F1 on val-select; ties choose8 rounds.
No other parameter/candidate search, unknown proxy or test-based choice.
The exact budget is stored in configs/b2_xgb_smoke.json.

Train-only per-feature mean and population SD standardization is frozen
before val-select inference. Zero SD maps to scale1. No validation/test
feature enters these statistics or fitting. Validation affects only the
fixed prefix selection. Clean val-calib affects only the alarm threshold.
All test/unknown/matched rows are final scoring/reporting only.

## 3. Predictions and separate score meanings

The fitted booster outputs eight probabilities in P18 LABELS order.
Multiclass prediction is the first argmax (fixed class-order tie rule).
Report known-test accuracy, macro-F1, confusion, per-class recall and counts;
calibrated confidence must not be claimed from this tiny pilot.

The **binary anomaly score is A=1-P(clean)**, larger is more anomalous.
Use P26's exact clean-only val-calib higher empirical95th percentile;
alarm strictly A>threshold. Nominal Pfa0.05 and achieved calibration alarms
are separate. Minimum2 distinct clean groups is only an engineering guard;
two samples cannot establish empirical/population Pfa5%.

Binary rates, operating strata, unknown-positive ranking against all known
test scenes, near-only pooling, separate noise/CID and paired K17c detection
use the existing P26 metric and score-bundle interface. EDSC and planned/blind
CFAR may be recomputed on the identical bounded artifacts with the same
clean rows/rule; no neural known-acceptance threshold is compared as clean Pfa.

For classifier open-set description only, define **U=1-max_k P(k)** (MSP,
larger more unknown-like). Use actual multiclass correctness for OSCR and
all known test scenes as its denominator, grouped score ties. Family/near
ranking and OSCR based on U are labelled separately from the binary A score.
No operational threshold is fitted for U. EDSC remains without class
predictions/OSCR; its unsupported outputs stay null. No eight-class score
is inferred from a binary detector.

## 4. Frozen state and reuse

Bind feature version/order/units, class order, train-only mean/scale,
selected prefix, complete fixed config, tested dependency version, train and
selection populations, artifact fingerprints and relevant source identities.
Persist a native XGBoost model (no pickle) plus strict JSON metadata and
checksums. Reuse verifies all binding fields, model feature order/count,
round count, native model checksum and expected provenance. Partial, foreign,
corrupt or nonempty incompatible output is refused, never silently refitted.
Calibrators/results additionally bind common calibration/evaluation IDs and
frozen scorer identity. There is no test-driven feature or threshold tuning.

## 5. Verification and reporting requirements

Tests cover observable-only input boundaries, feature arithmetic/order,
train-only statistics/fitting, role and complete-group isolation, deterministic
replay, val-select-only prefix choice, exact threshold equality, known clean
calibration, corrupt artifacts/model/reuse, strict JSON, P26 bundle identity
and metric denominators, and matched scenario-group bootstrap. Use stand-in
fixtures for integration tests and label them; no production generation.

Run focused tests, necessary full regression and one tiny CPU pilot using
existing verified physical artifacts. Record actual commands, environment,
wall time, peak RSS, feature/model/scorer identities and all population counts.
Preserve E3a's historical smoke and local RSS skip; adding E3b modules changes
the broad source-identity map and does not retroactively revalidate old reuse.
Independent read-only review precedes delivery; material findings are fixed.
All missing metrics are strict JSON null with counts/reasons. Group bootstrap
conditions on the fitted scorer/threshold and excludes training/calibration
and physics uncertainty. Tiny pilot metrics establish execution only.

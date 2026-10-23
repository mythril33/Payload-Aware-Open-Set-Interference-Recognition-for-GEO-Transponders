# P26 — E3a: observation-only EDSC baseline

Date: 2026-10-22. Protocol: **EDSC/1**. Base: verified remote
`main@2cc473fad07fc08984c17e212a06ddb26409a9cd` (PR #10 merged).
Branch: `feature/b2-e3a-edsc-baseline`. This engineering definition was written
before evaluating the bounded smoke observations. It implements the EDSC
baseline already required by [P18](P18_b2_protocol.md) §5 and
[P23](P23_b2_production_readiness.md) E3; frozen B2 physical sampling, role
definitions, labels, source artifact versions and approvals are unchanged.

## 1. Observable inputs and artifact boundary

The anomaly evidence is exclusively the receiver-observed cancellation residual
stored by [P20](P20_b2_cancellation_residual.md): `B2-feat/1`,
`obs-cancel/1`, using the frozen `configs/cancellation.json` settings. The
observed co-pol spectrum supplies only the shared planned-carrier power
reference. The operator co-pol mask defines that reference and diagnostic
regions. There is no fitted feature extractor or selected frequency band.

The separate P21b `B2-features/1` observed receiver is incompatible. It must not
be used as a substitute for P20. Optional `B2-test/1` and `B2-match/1` artifacts
must be bound to the same verified known artifact, receiver calibration,
physics and cancellation settings, and carry the same observation-derived
residual. Missing residuals, unsupported stages, inconsistent plans/provenance,
corrupt shards and invalid normalization fail closed through the E1 validators
and EDSC checks.

The scorer accepts only `spec`, `mask` and `residual` arrays. It never accepts
symbols, actual activity, labels, true IBO/XPD, source parameters, geometry,
event metadata or a clean twin. Labels select the authorized clean calibration
population; scenario IDs enforce role/pairing rules; simulator metadata is
used after scoring only for explicitly labelled reporting strata.

## 2. Fixed residual-energy statistic

The input grid is the existing P20 grid: 128 time snapshots, 512 fftshifted
frequency bins at a 96 MHz monitor sample rate, spacing 187.5 kHz. Spectra and
residuals are calibrated dB(power/Hz); no clipping or neural preprocessing is
applied. Time aggregation averages **linear power**, not dB.

For sample `i`, let `R_i(t,f) = 10^(residual_db_i(t,f)/10)` and
`S_i(t,f) = 10^(observed_co_db_i(t,f)/10)`. Define fixed sets:

- `B = {f : |f| <= 18 MHz}`, the 193 bin centres within the nominal
  36 MHz transponder, including both edge centres;
- `C_i = {f in B : co_plan_mask_i(f) > -3 dB}`, the operator carrier cores;
- `U_i = B \\ C_i`, the complementary non-core bins.

The per-observation reference is
`P_ref_i = mean_{t,f in C_i} S_i(t,f)`. The sole operating score is

```text
score_db_i = 10 log10(mean_{t,f in B} R_i(t,f) / P_ref_i).
```

Higher scores mean more residual energy relative to the observed planned-core
level and therefore more anomaly evidence. Increasing residual power at fixed
reference increases the score; a shared spectrum/residual gain offset cancels.
This is a dimensionless ratio of mean PSDs expressed in dB. Multiplying its
numerator and denominator by the same represented bandwidth leaves it
unchanged; the denominator is a core-derived reference density, not the
measured total carrier power. It is not an estimate of interference-to-noise
ratio or absolute received watts.

`planned_db` and `unplanned_db` report the same normalized residual mean over
`C_i` and `U_i`, respectively. Those names identify **core/non-core** regions:
`U_i` includes carrier roll-off and is not a claim that every bin is an empty
gap. Neither diagnostic changes the score, threshold or feature selection.
Both regions and the reference must be nonempty and all converted/averaged
powers finite and positive. Zero, underflow, overflow and malformed grids are
rejected rather than repaired with an arbitrary floor.

## 3. Calibration and role isolation

EDSC fits no train statistics or model weights and performs no val-select
selection. The four known roles are nevertheless checked for complete paired
groups and frozen role ranges through the existing B2 infrastructure.
Train/val-select observations cannot affect EDSC scores or thresholds.

The operating rule is fixed before test scoring:

```python
threshold = np.quantile(clean_val_calib_scores, 0.95, method="higher")
alarm = score > threshold
```

Only `clean` observations from the known `val-calib` role enter the quantile.
All known event variants are excluded from that threshold population. All
`test`, test-only unknown and `test-matched` observations are excluded from
fitting, calibration, feature selection and threshold tuning. Equality is a
non-alarm. Nominal Pfa is 0.05; the achieved calibration false-alarm numerator
and denominator are reported separately. Ties and the higher empirical
quantile can produce fewer alarms than the nominal target.

At least two distinct clean calibration scenario groups are an **engineering
guard**, not a statistical sufficiency claim. Below 20 clean samples the
empirical rate resolution `1/n` exceeds 5%; a two-group fixture usually gives
0/2 calibration alarms and cannot validate a 5% population false-alarm rate.
Even larger calibration populations provide an empirical operating point,
not a distribution-free guarantee of population Pfa. No fixture metric is
evidence of recognition performance.

## 4. Binary evaluation and uncertainty

Every thresholded rate reports its alarm count, sample denominator and group
count. Known `clean` is the false-alarm population; each non-clean known class
is a detection population. Test-only families retain the P18 grouping:
`pulsed`, `intermittent_bursts` and `adjacent_satellite_downlink` form the
pooled near-unknown population; equivalence-limited `wideband_noise` is
separate; benign `cid_overlay` contributes a false-alarm/control rate and is
excluded from unknown pooling.

Unknown-positive AUROC, AUPR (average precision, recall-weighted step
integral) and FPR@95TPR rank unknowns against **all known test observations**.
FPR@95TPR means the fraction of those known observations at the first grouped
score threshold reaching at least 95% unknown TPR. It is a descriptive ranking
metric and never replaces the frozen clean-calibrated operating threshold.
Because EDSC detects anomaly energy rather than unknown identity, a known
interference event can score higher than an unknown; this is a valid limit of
the baseline, not a reason to reverse direction or relabel populations.

Per-family and fixed operating-condition strata are reporting only. Simulator
IBO/C/N/C-I values used to describe those strata never enter scoring or
calibration. The fixed dB strata, recorded before smoke evaluation, are:

| Report-only quantity | Bins |
|---|---|
| Configured co-pol IBO | `[1,4)`, `[4,9)`, `[9,11)`, `[11,13]` |
| Co-pol uplink C/N | `[15,20)`, `[20,25)`, `[25,30]` |
| Co-pol downlink C/N | `[15,20)`, `[20,25)`, `[25,30]` |
| CuC C/I relative to the total plan | `[5,15)`, `[15,25)`, `[25,30]` |
| ASI/unauthorized C/I_psd | `[4,7)`, `[7,10)`, `[10,13]` |

Configured IBO is `config.co.ibo_db`, not realized `actual_ibo_db`; under
the frozen fixed-gain missing-carrier convention the realized back-off can
differ. CuC total-plan C/I and matched C/I_psd are separate quantities and
must not share labels. Values outside the fixed bins and missing values are
counted explicitly. Unavailable quantities, empty strata and insufficient group
counts are `null` with an explicit reason and counts. EDSC has no eight-class
prediction, multiclass accuracy, class confusion matrix or OSCR. Those
unsupported results are `null`; an alarm must not be interpreted as an ASI,
unauthorized or unknown-family class prediction.

Confidence intervals use a deterministic scenario-group percentile bootstrap
with fixed scorer and threshold (default 200 replicates, seed 20261022).
Known and unknown variants sharing a scenario remain together in each draw;
all rows of a selected group are resampled together. Fewer than two groups
gives a null interval. The output states usable replicate counts. These
intervals exclude calibration estimation uncertainty, physical-model
uncertainty and training-seed variation, and are descriptive in tiny pilots.

## 5. Matched ASI versus unauthorized detection

The [P22](P22_b2_matched_asi.md) intervention remains test-only, with complete
`clean`/ASI/unauthorized triples. Stored labels are global known indices
0/6/3. The frozen C/I_psd bins are `[4,7)`, `[7,10)` and `[10,13]` dB, with
7–10 dB the main bin. Both event detection rates and the paired
`unauthorized alarm - ASI alarm` difference use the same clean-calibrated
threshold. Bootstrap resamples whole pairs/triples, preserving group and bin
identity; unmatched rows or inconsistent bins are rejected.

Raw score-gap magnitudes retain each scorer's units (EDSC dB versus CFAR
standardized features). They are within-method diagnostics; only the paired
alarm-rate difference and common ranking/rate metrics support cross-method
comparison.

This compares **detection**, not the ability to classify one member as ASI
and the other as unauthorized. Both are positive anomaly cases. The natural
test distribution and the matched intervention are reported separately;
natural C/I_psd rows keep their own counts. The matched set has a restricted
carrier-width distribution and can include ASI over a dropped planned carrier
(P22 §7), so the level-matched comparison is not a natural prevalence claim.

## 6. Fair score-comparison interface

Optional CA-CFAR uses the existing `geoml.cfar` features, including its fixed
frequency/guard/training-cell convention. Its two feature scales are fitted
on the same clean `val-calib` observations, then frozen; its operating
threshold follows the identical higher-quantile/strict-`>` rule. Planned and
blind variants remain distinct named scorers. Their use of raw spectra and
local peak evidence is documented, rather than presented as the EDSC statistic.

The score-bundle comparison interface requires matching evaluation artifact
identities, ordered sample/group IDs, score direction, calibration data IDs,
clean-only population, nominal Pfa and threshold rule. Each bundle must also
carry a nonempty method-specific `scorer_identity` binding its frozen feature
definition and fitted state; each method has its own threshold value.
AUROC/AUPR/FPR@95TPR compare rankings
on identical populations; thresholded detection compares the shared clean
false-alarm operating rule. Incompatible bundles fail closed.

Existing neural MSP/energy/Mahalanobis **95% known-acceptance** thresholds
cannot be compared as if they were clean-Pfa thresholds. A neural binary
score must be generated from a frozen, provenance-verified model/scorer and
recalibrated on the same clean `val-calib` rows before operating-point
comparison. Neural multiclass accuracy or OSCR may remain in that model's own
report but cannot populate EDSC's unavailable fields. This slice provides
the common interface; it does not train a neural comparator or claim a
performance ordering from smoke runs.

## 7. Bounded execution and reproducibility

The runner reuses [E1](P24_b2_e1_streaming_loader.md) verification and shard
iteration. It retains only small score/index/reporting arrays across shards;
no whole-role spectrogram concatenation is permitted. Limits are at most
32 groups per role, at most 256 observations per shard and 1–1000 bootstrap
replicates; smoke mode requires at most two groups per role. Oversized
artifacts are refused rather than silently truncated. Execution is CPU-only,
with no dataset generator, model optimizer, GPU fitting or full LOKO path.

Calibrators, score bundles and results use strict JSON (`allow_nan=False`).
Provenance binds the EDSC protocol, artifact fingerprints, sample IDs,
cancellation settings, configuration and relevant source hashes. Reuse must
verify bound identities and checksums and refuse partial/incompatible output;
it must not silently overwrite a foreign calibrator or rerun threshold
selection on test observations. There is no EDSC model checkpoint to train.
Actual smoke commands, environment, measured time/memory, counts and review
findings belong in the [results note](../results/b2_edsc_baseline.md).

The capped real-artifact smoke command is:

```bash
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 \
  python -m geoml.b2_edsc --data data/b2-readiness-known \
    --unknown-data data/b2-readiness-test --matched-data data/b2-readiness-matched \
    --smoke --with-cfar --bootstrap 200 --out runs/b2-e3a-edsc-smoke
```

This command consumes existing artifacts and generates no RF observations.
Successful execution and measured results must be recorded separately; the
command's presence in this protocol is not execution evidence.

## 8. Scientific limits and pending gates

The P20 residual is not noise-only: decision errors, nonlinear payload
distortion, leakage, ISI, timing quantization and phase noise all remain.
`obs-cancel/1` uses one complex gain per 42.7 µs block and has an approximately
21–25 dB depth ceiling at the frozen 150 Hz effective linewidth. Its guarded
residual PSD uses 3072 samples/11 Welch segments, versus 4096/15 for the
observed spectrum: grid and density units agree but estimator variances
differ. EDSC does not remove this limitation or assert an exponential-noise
null law. Whole-band averaging may dilute localized/brief interference.

The observed carrier reference can be affected by an interferer or by a
missing planned carrier; common gain invariance does not imply immunity to
those changes. Operator MODCOD/frequency knowledge and the simulator's
waveform assumptions are inherited from P20. No result establishes unique
physical origin, authorization or field generalization.

K18, K17d and OBS-CANCEL/2 remain **pending researcher decisions**. Full B2
generation, GPU training and full LOKO remain unauthorized and unexecuted.
`benchmark_complete=false`; this engineering slice grants no production
approval and does not implement `obs-cancel/2`.

## 9. Proposed E3b XGBoost follow-up

Use the same verified E1 sources and a versioned observation-only expert
feature extractor with a fixed feature-name order. An explicit interface
should separate `extract(spec, mask, residual)` from
`fit(train_features, train_labels, provenance)`, val-select-only checkpoint
selection, clean-only `calibrate(val_calib_scores, ...)`, and
`score(test_features)` with frozen state. Feature statistics and supervised
boosted-tree fitting use train only; validation and all test roles cannot fit
normalizers, select features or tune thresholds. No simulator metadata is an
expert feature.

Pin the added dependency/version, deterministic seed/CPU/thread/tree budgets
and feature/scorer/checkpoint hashes. Export higher-anomaly score bundles
through §6 so EDSC, CFAR and learned models share populations and operating
calibration. Freeze an explicit binary score definition before test scoring;
multiclass outputs, if supported by E3b, remain separately labelled. The E3a
diagnostic regions are not a test-selected feature shortlist. E3b is proposed,
not implemented or approved by this document.

# B2 E9 — open-set statistical review

**Status:** review document, read-only. Companion to
[the independent scientific audit](B2_E9_INDEPENDENT_SCIENTIFIC_AUDIT.md) (finding IDs there are cited as C-, M-, Mo-, Mi-).
**Baseline:** `origin/main` `d7df413`. No data generated; no held-out observation opened; no tests run.
**Evidence tags:** **[V]** verified by the lead auditor by re-reading the line or re-computing a number; **[E]** extracted with
file:line by a read-only pass and not re-read by the lead.

## 1. Scope

This review covers: the eight-class closed set and the unknown families; the training objective; the three
rejection scores; the unknown-positive metrics (AUROC, AUPR, FPR@95TPR); the known-class acceptance and clean-alarm
calibration; the Mahalanobis fit; checkpoint selection; the bootstrap and seed structure; and the K17c / K17d
reporting rules.

## 2. Class and family definitions

- **Known classes (8):** `clean`, `cw`, `swept_cw`, `unauthorized`, `overdrive`, `cross_pol`, `adjacent_satellite`,
  `carrier_under_carrier` (`src/geosim/b2_protocol.py:29` [E]; `docs/plan/P18_b2_protocol.md` §2).
- **Unknown families (test only):** `pulsed`, `intermittent_bursts`, `adjacent_satellite_downlink` (near group),
  `cid_overlay` (expected clean, excluded from the unknown count), `wideband_noise` (equivalence-limited, reported separately)
  (`docs/plan/P18_b2_protocol.md` §3).

**Assessment.**

- The known set is partly *designed* to be confusable. P18 §6 pre-registers `adjacent_satellite` ↔ `unauthorized` as a
  "tasarım gereği karışabilir çift" (confusable by design). That is honest. It also means the 8-way accuracy is partly a
  placement question rather than a recognition question, and must be reported that way.
- `overdrive` vs `clean` depends on an unverified amplifier model (audit M-12). Until that is validated, the
  `overdrive` row is conditional.
- `adjacent_satellite_downlink` is a level-fixed construct with uplink-equivalent geometry (audit M-13). Its
  unknown-positive AUROC therefore tests *input-point ambiguity at a fixed level*, not a physical downlink threat.
- **Limitation to state in any publication:** "unknown" is defined by the simulator's family list. The benchmark
  measures recognition of the listed unknowns only.

## 3. Training objective

- **Approved:** `CE + 0.005 × center_sum + 1.0 × plan BCE`, with `center_sum` the batch mean of the sum of squared
  256-dimensional embedding distances (`docs/plan/b2_e9_approved_scientific_protocol.json:253–259`).
- **Implemented on the E9 chain:** `src/geoml/b2_stream.py:546–551` adds `center_weighted` and `plan_weighted` to the CE
  loss [E]; `src/geoml/model.py:77` takes the sum over embedding dimensions and the mean over the batch [E]. The sum is
  over `16 × width` dimensions (`model.py:44`), which equals 256 only at width 16. The approved width is 16 (R2), so the
  scale is correct on the approved path [E].
- **Discrepancy:** `src/geoml/b2_model.py:79` takes the mean over features *and* samples, which is 1/256 of the approved
  scale [V]. It is used by `b2_train.fit` (`b2_train.py:149–150`), not by the E9 chain [E]. It is a reuse trap (audit Mo-1).
- **Auxiliary plan head.** The target is the stored `plan_consistency` integer (`b2_stream.py:424`), and it is **not**
  recomputed after the K17b plan shift (`train.py:186–208` rebuilds masks only) [E]. Audit M-9 discusses the consequence.
- **Optimizer and schedule.** One AdamW parameter group with centers included, weight decay 1e-4 (`b2_stream.py:511–512`)
  [E]. OneCycleLR is constructed with only `max_lr` and `total_steps` (`b2_stream.py:515`); the other settings are PyTorch
  defaults that match the approved record but are implicit [E]. The approval (`…protocol.json:201–224`) states them
  explicitly, which is the right choice for a future executor.
- **Gradient clipping and autocast:** none in the B2 path [E].
- **TF32:** no flag set or recorded anywhere [V by grep]. The approved profile requires both off (audit M-2).

**Statistical note.** The center loss is a regulariser on the embedding. Its weight 0.005 was fixed in P20 before any
recognition result and is not tuned. That is consistent with the protocol and should be stated as an *untuned* choice.
The approval itself records the evidence on the center/CE ratio as an observation-only diagnostic.

## 4. Augmentation and leakage of augmentation

- **Mirror:** frequency-axis flip with probability 0.5 per sample (`b2_stream.py:534–537`) [E].
- **Roll:** one circular time shift per mini-batch (`b2_stream.py:534–537`; `train.py:378–381`) [E].
- **Plan shift:** training only, 15 % Bernoulli per sample, uniform ±0.5 MHz (`b2_execution.py` via `train.py:186–208`) [E].
- **Inference** applies no augmentation (`b2_stream.py:584–612`) [E], and validation, calibration and test inputs are
  unshifted [E].
- **Assessment:** augmentation is correctly restricted to training. The only open question is the plan-consistency target
  (audit M-9).

## 5. Rejection scores

All three scores are defined so that **larger = more unknown-like**, and the direction is consistent across
methods [E]:

| Method | Definition | Source |
|---|---|---|
| MSP | `1 − max_k softmax(z/T)_k` | `src/geoml/openset.py:55` |
| Energy | `−T · logsumexp(z/T)` | `src/geoml/openset.py:57` |
| Mahalanobis | `min_k` squared whitened distance to class means | `src/geoml/mahalanobis.py:95–106` |
| Clean-alarm score | `1 − P(clean)` | `src/geoml/b2_execution.py:306`, `src/geoml/b2_experiment.py:519–520` |

**Note.** The clean-alarm score is 1 − softmax(clean), not MSP. A clean-alarm event is `score > threshold` (strict),
while acceptance is `score ≤ threshold` (inclusive) [E].

## 6. Unknown-positive metrics

- **Positive class:** unknown = positive. `_roc(known, unknown)` in `src/geoml/openset_metrics.py:97` [E].
- **FPR denominator:** `n_known` (`openset_metrics.py:51`) [E]. This matches P18 §7 ("payda: bilinen test olayları").
- **TPR denominator:** `n_unknown` [E].
- **AUROC:** trapezoid over a grouped-tie ROC (`openset_metrics.py:109`) [E].
- **AUPR:** step-wise average precision (`openset_metrics.py:99–100`), not a trapezoid [E].
- **FPR@95TPR:** the TPR level `0.95` is applied to the unknown-positive ROC. The threshold is the first grouped threshold
  with TPR ≥ 0.95 (`openset_metrics.py:57, 112`) [E].

### 6.1 The two 0.95 values are different quantities

This was the explicit check requested by the brief.

| Quantity | Literal | Role | Positive class | Where |
|---|---|---|---|---|
| FPR@95TPR | 0.95 | TPR level on the unknown-positive ROC | unknown | `openset_metrics.py:112` [E] |
| Known acceptance target | 0.95 | quantile level for the rejection threshold, fitted on known val-calib | known (accepted) | `b2_experiment.py:63` [E]; `calibration.py:131` [V] |

**Conclusion.** They are computed on different populations (known test events for the FPR denominator; known val-calib
scores for the acceptance quantile) and answer different questions. The brief's worry is resolved in the code [E].
**Residual risk:** the identical literal `0.95` in two roles is a naming hazard (audit Mi-1). Any table must print the
concept, not the number.

### 6.2 Tie handling

Rejection alarms use strict `>` (`calibration.py:79`). ROC counts equal scores as detections (`openset_metrics.py:47`) [E].
These are different quantities. They should be documented side by side (audit Mo-10).

## 7. Calibration

### 7.1 Known acceptance (rejection threshold)

- **Data:** known val-calib only, all eight known classes. For G val-calib groups this gives 8·G samples [E]
  (`b2_execution.py:286, 319, 335`).
- **Quantile:** `np.quantile(scores, 0.95, method="higher")` (`calibration.py:131`) [V]. This matches the approved "higher" rule.
- **Acceptance:** `score ≤ threshold` (`calibration.py:79`) [V].

### 7.2 Clean-alarm threshold

- **Data:** clean val-calib only, G samples [E] (`b2_execution.py:300, 310`).
- **Quantile:** `np.quantile(clean_scores, 1 − pfa)` with **no method argument** (`src/geoml/metrics.py:38`) [V].
- **Approved:** "higher empirical quantile" (`b2_e9_approved_scientific_protocol.json:334`) [V].
- **Finding M-1.** NumPy's default linear method can place the threshold below the approved order statistic, raising the
  empirical clean-alarm rate on the same calibration set. The size of the difference depends on the score gaps near the
  quantile and was not quantified here. It is a protocol deviation and must be fixed before any executor runs.

### 7.3 Two thresholds, two populations

Both numerical targets are 0.95 (acceptance) and 0.05 (clean alarm, i.e. 1 − 0.95 on clean). They are fitted on different
populations (8·G versus G) and on different scores (rejection score versus `1 − P(clean)`). The approval records both
(JSON:330–336). They are two operating points, not one, and should be reported as two operating points.

### 7.4 Precision of the calibration thresholds (analytical, not data-derived)

For an exceedance rate near 5 %, the binomial standard error is √(p(1−p)/n):

| Sample (side) | n | SE of exceedance rate | Approximate 95 % half-width |
|---|---:|---:|---:|
| Clean val-calib (threshold source) | 150 groups | 1.78 pp | ±3.5 pp |
| Clean test (evaluation side) | 500 groups | 0.97 pp | ±1.9 pp |

[V] arithmetic; approximation for the rate, not an interval on the data. Two consequences:

1. The threshold, and therefore the clean-alarm rate actually observed on test, has a precision of a few percentage points.
   Any reported Pfa must carry that uncertainty, or the reader will take 5.0 % as exact.
2. The effective number of independent clean samples is G (one per group), because the eight variants of a group share
   plan, link and noise (audit Mo-3). The 8·G acceptance sample is also clustered.

**Remedy.** Bootstrap the val-calib threshold over groups and report its interval, or state the empirical clean-alarm rate
on test with the group-bootstrap interval. This is computed on val-calib only, before test, so it does not consume the test
role (proposal V-7 in the audit).

## 8. Mahalanobis fit

- **Statistics:** train-role embeddings of the selected checkpoint, eval mode, class-conditional (`b2_execution.py:264–268`
  [E]; `b2_experiment.py:514–515` [E]). **Train role only** [E].
- **Covariance:** `S` is the residual Gram over `max(N−K, 1)`; `Σ = (1−a)S + a·(tr S / D)·I + floor·I` with `a = 0.1`,
  `floor = max(1e-6·tr S / D, 1e-8)` (`src/geoml/mahalanobis.py:171–176`) [E].
- **Shrinkage target:** the **trace-scaled identity**, not the diagonal. The approval records only "shrinkage 0.1". The target
  must be recorded in the approved record (audit Mo-12).
- **Inversion:** Cholesky with triangular solves (`mahalanobis.py:177, 99`), no pseudo-inverse and no ridge retry.
  Failure raises `ValueError` (`mahalanobis.py:178–179`) [E]. This is fail-closed, which is correct.
- **Few-sample behaviour:** each class must be present (`mahalanobis.py:164–165`) [E]. If `N = K` (one group) then `S = 0`
  and `Σ = 1e-8·I`, which is numerically extreme. The docstring acknowledges this (`:153–155`). At the approved scale
  (N ≈ 12 000) this is not an issue.
- **Numerical stability** at approved scale is not tested in this review. It needs a CPU check on a fixture, which is a
  proposal, not a claim.

## 9. Checkpoint selection

- **Rule:** best macro-F1 over the eight known classes on val-select, strict `>` so the first epoch reaching the maximum
  is kept (`src/geoml/b2_stream.py:568` [E], `best = −1.0` at `:518` [E]).
- **Auxiliary head:** only recorded (`b2_stream.py:565–566`) [E], not selected on.
- **Class presence:** macro-F1 averages over classes present in `y_true` (`src/geoml/metrics.py:17` [E]). The eight-class
  presence is enforced by the executor (`b2_execution.py:156`), not by `fit_streaming` [E]. Without that check, a
  macro-F1 could silently be computed over fewer than eight classes.
- **Assessment:** correct on the isolated path. Note that a single-epoch first-max rule on 150 val-select groups is a
  noisy selector. Its variability should be reported per seed.

## 10. Role discipline (summary; detail in the audit §8)

- **Isolated path (P31):** fit reads train and val-select only (`b2_execution.py:242`); calibration reads val-calib only
  (`:286`); evaluation validates the full nine-cell inventory before opening test (`:431, 488`) [E].
- **Legacy path:** opens all roles including test before training (`b2_experiment.py:436`) and infers test inside the view
  loop (`:493–501`) [E]. Not on the E9 chain, but reachable (audit M-10).
- **Structural, not ledgered:** nothing records that no earlier test read occurred, and the pilots did read the test
  role (audit C-1) [V on `b2_full_pilot.json`].

## 11. Bootstrap and seed structure

### 11.1 Scenario-group bootstrap

- `cluster_ci`: 2000 resamples, seed 0, percentile method (`src/geoml/metrics.py:21–35`) [E].
- It resamples whole scenario groups, which is correct for paired variants (approval: "Group bootstrap resamples whole
  scenario groups").
- **It is conditional on the frozen bundle.** It captures test sampling variability for one checkpoint, one scorer, one
  threshold. It does **not** capture training-seed variability or calibration variability (audit M-7).

### 11.2 Seed-level uncertainty

- **Design:** 3 training seeds per view (R1), so 9 fits.
- **Estimability:** a seed SD from 3 values has 2 degrees of freedom. The 95 % t-multiplier is 4.303, so the half-width of
  a 95 % CI for the seed mean is 4.303 × SD / √3 ≈ 2.5 × SD. The seed SD itself is very imprecise at 2 df. Seed-level CIs
  from three seeds are not informative (audit M-6).
- **Code:** a cross-seed SD with ddof=1 exists (`src/geoml/b2_loko_matrix.py:372–373`) [E], but no committed output
  contains it. The atlas states "No uncertainty is drawn" (`docs/results/B2_SCIENTIFIC_RESULTS_ATLAS.md:162`) [E]. The two
  statements should be made consistent.
- **Recommended reporting:** each seed individually, the range across seeds, and the group-bootstrap interval per seed.
  A combined interval needs a pre-registered method and more seeds (proposal V-8).

### 11.3 Combined uncertainty

Scenario-bootstrap and seed variability are not additive, and no combined method is pre-registered. Until one is,
report them separately and do not sum them.

## 12. Reporting rules for the specific sub-analyses

### 12.1 K17d (ASI level drift, 35 co-feed groups)

- **Headline:** 500 test groups (`docs/plan/b2_e9_approved_scientific_protocol.json:21–23`).
- **Sensitivity:** 465 groups excluding the 35 co-feed missing-carrier groups.
- **Verified counts:** 500 / 78 missing / 35 co-feed / 43 cross-feed (`docs/results/k17d_drift_audit.json`) [V].
- **Drift:** co-feed median 0.71 dB, p90 2.93 dB, max 5.91 dB [V].
- **Problem:** the predicate and row set cannot be reproduced from committed artifacts (audit C-2).
- **Required table:** headline and sensitivity rows side by side, with the drift histogram of the 35 groups and the
  unchanged-group control. Every rate must carry its n.

### 12.2 K17c (matched ASI vs unauthorized)

- **Design:** 150 matched groups, C/I_psd ~ U(4, 13) dB shared, placement the only difference (`docs/plan/P18_b2_protocol.md`
  §7a K17c, lines 190–208).
- **Level:** imposed by intervention (`level_source: matched_intervention`, `asi.py:233` [E]). This is controlled, not
  natural.
- **Verified check:** 2 groups, 6 observations, no recognition metrics (`docs/results/b2_matched_check.json`) [V].
- **Finding M-8:** observed in-band PSD differs by 2.36 dB on group 3300001 (ASI 3.50 dB vs unauthorized 10.07 dB, check
  file lines 25–29) [E]. The level match holds for injected power only.
- **Required table:** the 2×2 and full confusion matrix, per-class recall and precision, n, scenario bootstrap interval,
  the natural-distribution 7–10 dB slice for comparison, and the observed-PSD matched diagnostic (V-6).

### 12.3 Test-only families

- Generated only for the test role (`src/geosim/b2_scenarios.py:376–377` [E]); their own RNG namespace
  `[group, 1830, family]` (`:337–339` [E]); documented exception for the downlink ASI stream (`:351–356` [E]).
- Not admitted to train, val-select or val-calib (`src/geoml/b2_stream.py:353–354`; `src/geoml/b2_test_dataset.py:379–380`) [E].

## 13. Multiplicity

The protocol specifies many comparisons: 3 views × 3 seeds × 3 methods (MSP, energy, Mahalanobis) × 8 classes × families × bins
× ablations. No family-wise correction or primary endpoint is pre-registered (audit Mo-5). Recommended: one primary endpoint
(the headline `dual_residual` FPR@95TPR on the 500-group test set), and every other comparison labelled exploratory.

## 14. Statistical summary by claim type

| Claim type | Admissible evidence | Current status |
|---|---|---|
| Recognition performance of a method | Final benchmark, nine frozen cells, one read | **Not available.** No final read has occurred; pilots only. |
| Method A vs method B difference | Paired scenario bootstrap on the frozen bundle | **Not available.** |
| Robustness across training seeds | Per-seed results over ≥ 3 seeds, reported as a range | **Not available.** Three seeds would give a range only. |
| Pfa operating point | Val-calib threshold and test clean-alarm rate, with threshold uncertainty | **Partly designed**; threshold quantile method not yet approved-compliant (M-1). |
| K17c level-matched separability | Full 150-group matched evaluation, observed-PSD diagnostic | **Not available**; 2-group check only. |
| K17d drift effect | Headline vs 465-group sensitivity | **Designed**; identity not reproducible (C-2). |
| Cancellation ceiling | Analytical 21.74 dB; Monte Carlo 22.82 dB | **Analytical and simulated**, not measured. |

## 15. Proposals requiring researcher approval

None of these is authorized by this review and none is a change to R1–R10.

1. Bootstrap of val-calib thresholds over groups, with the interval reported (V-7). CPU, val-calib only.
2. Seed replication beyond three seeds for the headline comparison (V-8). Has a compute cost and must be a researcher decision.
3. Pre-registration of one primary endpoint and of the family structure for multiplicity (Mo-5).
4. Clarification of the intent of the plan-consistency head under the K17b shift (M-9).
5. A pre-registered method for combining seed and scenario-bootstrap variability, or a decision to report them separately.

## 16. Limits of this review

- No numeric result was reproduced. The statistical arithmetic above was re-derived; the simulator's outputs were not.
- The bin counts 50/54/46 for 150 matched groups were not reproduced (no committed record).
- The interaction between the center-loss weight and the plan-consistency head was not analysed quantitatively.
- The effect size of the CuC victim-conditioning shortcut (audit Mo-6) was not quantified.

# B2 E9 — independent scientific audit (red-team review)

**Status:** review document, read-only. No `src/`, `configs/`, test, workflow or readiness-gate file was edited.
No data was generated, no model trained, no GPU probe run, no held-out observation opened, no LOKO performed.
**Reviewed baseline:** `origin/main` = `d7df413` (includes PR #26, #27, #28). The brief named `d14f31d` as the
starting point; `main` has since moved past it. Findings below refer to `d7df413` unless stated.
**Branch:** `research/b2-e9-independent-scientific-audit`.
**Companion documents:** [open-set statistical review](B2_E9_OPEN_SET_STATISTICAL_REVIEW.md),
[publication readiness checklist](B2_E9_PUBLICATION_READINESS_CHECKLIST.md).

## 0. How the evidence was gathered (read this before trusting the findings)

- Three read-only extraction passes covered (A) RF physics and cancellation, (B) learning, losses, scores,
  metrics and calibration, and (C) roles, leakage and the K17d/K17c data records. Each extraction returned
  file:line citations with short quotes. Those citations are tagged **[E]** below.
- The lead auditor re-read the decisive lines and checked the decisive numbers. Those are tagged **[V]**.
  Verified items: `src/geoml/metrics.py:38`, `src/geoml/calibration.py:131`, `src/geoml/b2_model.py:79`,
  `src/geoml/b2_execution.py:305-307`, a repository-wide grep for `allow_tf32`/`set_float32_matmul_precision`
  (no hits), `docs/results/k17d_drift_audit.json` counts, `docs/results/b2_matched_check.json` (`n_groups: 2`),
  `docs/results/b2_full_pilot.json` test/test-matched partitions, the depth-ceiling arithmetic
  (`2π·150·4096/96e6/6` gives 21.74 dB), the pilot-run specifications, and `src/geosim/b2_scenarios.py:84-92`.
- Nothing was executed. The test suite was not run. Statements about runtime behaviour are not claimed.

## 1. Scientific validity verdict

**The protocol design is internally careful and mostly well documented, but the benchmark is not yet
scientifically valid as a held-out evaluation.** Three conditions block a production-grade claim:

1. The held-out test role has already been read by pilot runs (Finding C-1), and the pre-test K17d re-derivation
   that the approval requires is not implemented or reproducible from committed artifacts (Finding C-2).
2. Several approved numerical and metric rules are not what the code implements (for example the
   clean-alarm quantile, F-1 below), and the approved TF32 policy is not enforced anywhere.
3. Several central interpretive claims go beyond the evidence: "observation-based" cancellation assumes an exact
   declared plan, the "level-matched" ASI/unauthorized set is verified only on two groups, and the 3-seed design
   cannot support seed-level uncertainty.

None of these is a fatal flaw in the simulator physics. Most are fixable by documentation, engineering and
explicit pre-test procedures. Two need a **new researcher decision** (the dual-pol receiver contract, and how to
handle pilot exposure of the test role).

**Evidence class for the verdict itself:** requires full benchmark verification for every performance statement.
No recognition performance is claimed or implied by this review.

## 2. Severity legend

- **Critical** — threatens scientific validity or leakage protection.
- **Major** — likely affects reproducibility or interpretation.
- **Moderate** — methodology or reporting weakness.
- **Minor** — editorial clarification.

"Researcher decision" = the fix changes an approved or open scientific choice and needs explicit researcher sign-off.
"Engineering" = the fix brings code in line with an existing approved record and needs no new scientific decision.

## 3. Critical findings

### C-1 — The held-out test role has already been read in pilots  [V]
- **Evidence.** `docs/results/b2_full_pilot.json` contains `partitions.test` (line 111) and `partitions.test_matched`
  (line 144), produced by pilot checkpoints on the frozen seed ranges (test `3200000–`, test-matched `3300000–`).
  `docs/results/b2_test_pilot.md` ("frozen-role open-set evaluation") and `docs/results/b2_matched_pilot.md` describe
  the same. The pilots covered 2 test groups and 2 test-matched groups.
- **Contrary text.** P18 §4 specifies test as a single final evaluation ("test → evaluated once",
  `docs/plan/B2_E9_SCIENTIFIC_DECISION_APPROVAL_2026-10-24.md:33–39`). The approval states that all nine fits must
  be frozen "prior to the first held-out **observation** read" (line 39). That condition is violated for the pilot
  groups, even though the nine-cell checkpoints did not exist then.
- **Impact.** The 500-group test role and the 150-group matched role are no longer a pristine held-out sample.
  The effect on any final number is probably small (2 of 500 and 2 of 150 groups), but the protection
  principle is broken, and any design decision made after a pilot result could be contaminated. The pilot
  reports do state "no recognition-quality claim", which limits the damage.
- **Remedy.** (a) Disclose the pilot test read in the approval record and in P18 §10. (b) Quarantine the pilot test
  group IDs in the E9 freeze record. (c) Either accept the disclosed exposure explicitly, or re-version the test
  role (for example `B2-test/2` with new seeds) before any final read. Do not silently regenerate `B2-test/2`
  (approval line 16 forbids silent regeneration).
- **Needs researcher decision:** yes (accept disclosed exposure vs re-version the test role).

### C-2 — The K17d 35-group split is not verifiable from committed artifacts, and the required pre-test re-derivation is not implemented  [V]+[E]
- **Evidence.** `docs/results/k17d_drift_audit.json` reports `n_test_groups: 500`, `n_missing_groups: 78`,
  `n_missing_co_feed: 35`, `n_missing_cross_feed: 43` [V]. The JSON has no predicate field, no commit or hash, and no
  timestamp. The row generator is not committed. P22 cites `runs/k17d_drift_audit.json` (`docs/plan/P22_b2_matched_asi.md:125–126`).
  No code in `src/` or `scripts/` implements the re-derivation the approval requires
  (`B2_E9_SCIENTIFIC_DECISION_APPROVAL_2026-10-24.md:16`: "Re-derive group identities from committed production
  generation metadata before any test observation is opened").
  The only consumer is `scripts/b2_e6_decision_evidence.py:32–45`, which recomputes from the same JSON (a
  self-consistency check, not a re-derivation).
- **Contrary text.** The approval requires the 35 co-feed groups to be "predeclared" and their predicate to be
  verified against the committed JSON. That verification is not possible from the committed JSON alone, because the
  JSON does not show whether the row set is complete.
- **Impact.** The headline 500 / sensitivity 465 split is the protection against outcome-driven group removal. The
  split is pre-declared in words, but its *identity* depends on a procedure nobody can currently replay.
  Combined with C-1, a reviewer cannot confirm the split was fixed before any test read.
- **Remedy.** Commit the generator (or a pure metadata-only script) that emits the 35 and 465 identity lists from the
  frozen test generation metadata. Record its source hash and an input-metadata checksum in a file committed
  **before** any test observation is read. Engineering, not a new decision, once the procedure is agreed.

## 4. Major findings

### M-1 — Clean-alarm threshold uses linear quantile, not the approved "higher" method  [V]
- **Evidence.** `src/geoml/metrics.py:38` `np.quantile(clean_scores, 1 - pfa)` (no `method` argument; NumPy default
  is linear). The approved rule is "higher empirical quantile, inclusive acceptance"
  (`docs/plan/b2_e9_approved_scientific_protocol.json:334`). The rejection quantile does use
  `method="higher"` (`src/geoml/calibration.py:131`), so the two thresholds are computed differently.
  The clean-alarm path is called from `src/geoml/b2_execution.py:307` and `src/geoml/b2_experiment.py:522`.
- **Impact.** Linear interpolation can place the threshold below the sample order statistic, which raises the
  empirical clean-alarm rate on the same calibration set. This directly changes the nominal Pfa = 0.05 operating point.
- **Remedy.** Use `method="higher"` for the clean-alarm quantile in the approved executor and add a unit test
  asserting the approved method. Engineering. Note that the historical pilot numbers must not be relabelled.

### M-2 — TF32 policy in the approved R6 is not implemented or pinned  [V]
- **Evidence.** A repository-wide grep for `allow_tf32` and `set_float32_matmul_precision` returns nothing in `src/`,
  `scripts/`, `configs/` [V]. The approval requires both flags off and an effective-flag record
  (`b2_e9_approved_scientific_protocol.json:81–82`; `B2_E9_SCIENTIFIC_DECISION_APPROVAL_2026-10-24.md:31`).
  P18 §10 records that E8 PyTorch cuDNN had TF32 enabled by default (`docs/plan/P18_b2_protocol.md:252`).
  `_runtime()` in `src/geoml/b2_execution.py:43–52` does not record TF32 state [E].
- **Impact.** Any future GPU run would not satisfy R6 as written. Precision policy affects reproducibility of
  every checkpoint.
- **Remedy.** Engineering: set and assert both flags, record them in the checkpoint provenance, refuse execution on
  mismatch. No new scientific decision.

### M-3 — "Observation-based" cancellation assumes exact declared plan frequency, rate and modulation  [E]
- **Evidence.** `src/geosim/cancellation.py:150–151` ("Nothing else is used"); inputs are the co-pol IQ and plan
  fields `f0, symbol_rate, alpha, mod, code_rate` (166–170). The sample-per-symbol comes from the declared rate
  (167). `docs/plan/P20_b2_cancellation_residual.md:120–121` states "the plan frequency is assumed exact".
  The simulator passes the nominal plan (`src/geosim/b2_dataset.py:449–451`), which equals the transmitted plan by
  construction.
- **Impact.** The residual channel (the fifth input) is computed under the same plan that generated the signal. Real
  operator plans can be wrong, and P28 A5 tests exactly this only for frozen models. Calling the canceller
  "observation-based" is accurate for symbols and activity, but its frequency/rate/modulation inputs are exact
  upper-bound conditions. Cancellation depth and classifier gains are therefore optimistic where the plan is wrong.
- **Remedy.** Report the residual channel as "conditional on declared plan parameters" in every claim. Add a
  plan-parameter-error sweep on the receiver (frequency offset, rate error, mod error) as a pre-registered proposal.
- **Needs researcher decision:** yes (whether the plan-error sweep is in scope and how it is reported).

### M-4 — The five-channel "dual" input requires a cross-pol monitor the co-pol invariant does not list  [E]
- **Evidence.** Channel 1 is the calibrated cross-pol spectrum, computed from cross-pol IQ (`src/geoml/b2_data.py:49–83`;
  P18 §1, `docs/plan/P18_b2_protocol.md:30–35`). Channel 3 is the cross-pol operator plan mask, which requires a declared
  second-feed plan. `.claude/rules/scientific-invariants.md` item 1 names co-pol monitor IQ and co-pol operator plan as
  the canceller inputs and does not list cross-pol IQ. `CLAUDE.md` lists the model inputs without naming a
  receiver polarization. The cross-pol channels are therefore outside the rule's explicit list, or the rule must be widened.
- **Impact.** The C2 claim ("dual-polarization open-set recognition") depends on information a single-feed
  co-pol receiver does not have. That is a valid research question, but only if the operator receiver is assumed to
  have a dual-polarization monitor. The benchmark does not state this receiver contract.
- **Remedy.** Write an explicit operator-receiver contract: which polarizations are monitored, whether the
  cross-feed plan is declared, and whether the cross-feed IQ is available. Then either widen the invariant or drop
  channels 1 and 3 for a co-pol-only benchmark variant (already the `co` ablation).
- **Needs researcher decision:** yes.

### M-5 — Two canceller implementations are live, and the mapping to approved results is unclear  [E]
- **Evidence.** `geosim.cancellation` (`obs-cancel/1`) is imported by `src/geosim/b2_dataset.py:31` and
  `src/geosim/b2_test_dataset.py:31`. `src/geosim/b2_features.py:47` imports `observed_receiver.py`
  (`ALGORITHM = "observed-dd-rrc-fir/1"`, `observed_receiver.py:27`). `docs/plan/P21_b2_observed_receiver.md:11`
  describes the B2-features/1 stage as using the observed receiver. `docs/results/b2_feat_pilot.json:126` records
  `obs-cancel/1` under protocol B2-feat/1. P20 documents only `geosim.cancellation`.
- **Impact.** The approval retains `obs-cancel/1` as the primary receiver (`B2_E9_SCIENTIFIC_DECISION_APPROVAL_2026-10-24.md:12`).
  A reader cannot tell from the stage names which implementation produced a given number.
- **Remedy.** A single table in P20/P21 mapping stage → canceller → algorithm version → artifact. Engineering.

### M-6 — Seed-level uncertainty is not estimable from 3 seeds, and the code's cross-seed statistic is not reported  [E]
- **Evidence.** Three training seeds are fixed (`B2_E9_SCIENTIFIC_DECISION_APPROVAL_2026-10-24.md:26`, R1).
  `src/geoml/b2_loko_matrix.py:372–373` computes a cross-seed sample SD with ddof=1, but no committed JSON contains
  `seed_sample_sd`. `docs/results/B2_SCIENTIFIC_RESULTS_ATLAS.md:162` says "No uncertainty is drawn", and
  `src/geoml/b2_loko.py:266` sets `training_seed_uncertainty_included` to False.
  `docs/results/pilot_A.md:47–67` reports "±" values over training seeds [0, 1] without defining them.
- **Impact.** A 3-seed SD has 2 degrees of freedom. With t(0.975, 2) = 4.303, the 95% CI half-width for the seed
  mean is 4.303 × SD / √3, about 2.5 times the sample SD, and the SD itself is very imprecise. Reporting mean ± SD
  over 3 seeds would look more precise than it is.
- **Remedy.** Report every seed individually (already required by R1) and state the range. Do not report a
  seed-level CI unless the seed count is increased (a proposal, not a decision here). Fix the atlas statement to
  match the code, or the reverse.

### M-7 — Scenario bootstrap is conditional on fixed models and thresholds  [E]
- **Evidence.** `src/geoml/metrics.py:21–35` (`cluster_ci`, 2000 resamples, seed 0, percentile) is applied by
  `_rate` (`src/geoml/b2_experiment.py:142–148`). The model, the scorer and the threshold are held fixed; training and
  calibration variance are not in the interval.
- **Impact.** The scenario CI is a conditional interval for one trained bundle. It understates total uncertainty.
  Stating it as the uncertainty of the method would be an overclaim.
- **Remedy.** Label every CI as "scenario-bootstrap, conditional on the frozen bundle". Report seed and calibration
  variability separately. Do not combine them without a pre-registered method.

### M-8 — The "level-matched" ASI/unauthorized claim is verified only for injected power, on two groups  [V]+[E]
- **Evidence.** `docs/results/b2_matched_check.json` has `n_groups: 2`, `n_observations: 6`, and `recognition_metrics: null`
  [V]. The 50 / 54 / 46 bin counts for 150 groups appear only in prose (`docs/plan/P22_b2_matched_asi.md:30`,
  `docs/results/b2_matched_pilot.md:16–17`); no machine-readable 150-group record is committed [E]. The check file
  records oracle injected-power equality (requested-power ratio 0.04 dB and 0.17 dB) but also an observed in-band
  ΔPSD gap on group 3300001: 3.50 dB for ASI versus 10.07 dB for unauthorized (lines 25–29). The file attributes the gap
  to placement (line 157) [E].
- **Impact.** "Level-matched" holds for the injected power by construction (`level_source: matched_intervention`).
  It does not hold for observed in-band PSD. The K17c result interprets the ASI/unauthorized confusion as
  placement-only, but the observed levels differ.
- **Remedy.** Restate the claim as "injected-power matched" and add an observed-PSD matched-diagnostic table over the
  full 150-group matched role, computed without any recognition outcome, before the evaluation reads. Engineering plus
  a clarification of the claim.

### M-9 — The auxiliary plan-consistency target is not recomputed under the K17b plan shift  [E]
- **Evidence.** `src/geoml/b2_stream.py:424, 533` uses the stored `plan_consistency` integer as the target;
  `src/geoml/train.py:186–208` rebuilds only the masks. The target comes from `src/geosim/b2_scenarios.py:195`
  (`consistency = int(dropped is not None)`). P18 §7a calls the shift label-preserving (`docs/plan/P18_b2_protocol.md:171`).
- **Impact.** In 15 % of training samples the plan is moved by up to 0.5 MHz, yet the head is told the plan is
  consistent. The head is therefore trained to ignore plan misalignment of this size. That is a defensible robustness
  choice, but it weakens the head as a detector of plan errors. A5 `shift_plus/minus` is a plan error of the same size.
  The protocol does not say which of the two intents governs the head.
- **Remedy.** State the intent explicitly in P18 §7a: the head reports the simulator's activity state and is blind to
  the augmentation. Alternatively recompute the target, which changes the protocol and needs a new version. Needs
  researcher decision about the intent.

### M-10 — The legacy coupled path opens and evaluates the test role before freeze  [E]
- **Evidence.** `src/geoml/b2_experiment.py:436` opens every role including test. Per-view test inference happens
  inside the loop at `:493–501`, before later views train. Reachable through `--mode legacy` (`:822–826`), capped only
  by `LEGACY_MAX_GROUPS = 12` (`:54, 437`). The isolated path (P31) enforces role scoping in code
  (`src/geoml/b2_execution.py:242, 286, 431, 488`).
- **Impact.** Not on the E9 production chain, but a reachable route to exactly the ordering R8 forbids.
- **Remedy.** Refuse legacy mode when a freeze manifest exists, or remove test loading from the legacy path. Engineering.

### M-11 — Resource and GPU-hour figures disagree across documents, and one ratio is arithmetically wrong  [V]
- **Evidence.** The approval JSON gives 7.0 h for nine fits and calls it "roughly 1.9x the reservation"
  (`docs/plan/b2_e9_approved_scientific_protocol.json:430`). 7.0 / 6 = 1.17. The 1.9x figure is the upper bound of the
  earlier range (11.5 h / 6 = 1.9; `docs/plan/B2_E7_TRAINING_SPEC_PROPOSAL.md:176`). `docs/plan/P33_b2_e9_production_executor_readiness.md:17`
  cites an "unmeasured 10–22h width16 nine-fit estimate", which appears in no other committed document [V via grep].
- **Impact.** Five different GPU-hour figures (5.88, 6.8–10.4, 7.0, 7.9–11.5 and 10–22) are in circulation.
  None is measured. This is a reporting-clarity problem, but it feeds a resource decision.
- **Remedy.** One table with source, basis and status for each figure. The 1.9x claim should read 1.17x for the
  7.0 h point estimate and 1.9x only for the upper bound.

### M-12 — Overdrive label depends on an unverified amplifier model  [E]
- **Evidence.** `src/geosim/payload.py:78` says the Saleh coefficients are "not yet checked against the paper";
  `payload.py:221` labels the default TWTA "Ka-band" for a Ku-band system. P18 §2 (`docs/plan/P18_b2_protocol.md:67–71`)
  already records that the overdrive label is amplifier-dependent.
- **Impact.** The `overdrive` class and the K17a "observed-nominal" subrow depend on AM/AM and AM/PM behaviour that
  has not been validated against a source. These are classes in the 8-way benchmark.
- **Remedy.** Validate the amplifier curve against its cited source, or report the overdrive class as conditional on a
  stated, unvalidated amplifier model. Proposal.

### M-13 — The ASI downlink geometry reuses the uplink earth-station geometry at 14.25 GHz  [E]
- **Evidence.** `src/geosim/asi.py:250` calls `draw_geometry` with default ranges, so the downlink event uses the
  uplink earth-station geometry at 14.25 GHz. A downlink interferer would come from a satellite near 11–12 GHz.
  P18 §7a K17d (`docs/plan/P18_b2_protocol.md:216–219`) acknowledges the frequency is not modelled and reports the 11.7 GHz case
  only as a sensitivity row.
- **Impact.** The K17d distribution is a deliberate level-fixed design, so the geometry error does not change the
  level-matched design. It does mean the "physical" description of `adjacent_satellite_downlink` is a construct, not
  a measured or geometry-consistent threat.
- **Remedy.** Describe the class as a level-matched construct. Keep the 11.7 GHz sensitivity row and make its
  geometry explicit. Documentation.

### M-14 — 35 test groups have a systematic ASI level shift that the headline reports include  [V]
- **Evidence.** `docs/results/k17d_drift_audit.json`: co-feed missing drift median 0.71 dB, p90 2.93 dB, max 5.91 dB [V].
  The audit note explains the drift as `10·log10(1/active co power)` [V].
- **Impact.** For the 35 co-feed groups, the downlink event level is shifted relative to the nominal distribution.
  The 500-group headline mixes shifted and unshifted groups. The 465-group sensitivity row removes them, which is
  correct per the approval. The headline should still be read with the shift in mind.
- **Remedy.** Report both rows and the drift histogram in the same table. Already partly required by the approval.

## 5. Moderate findings

| ID | Finding | Evidence | Remedy | Researcher decision? |
|---|---|---|---|---|
| Mo-1 | Center-loss scale differs between `B2Model` (mean over features and samples, `b2_model.py:79`) and the approved sum convention (`model.py:77`). Not on the E9 chain, but a reuse trap. | [V] `b2_model.py:79` | Rename or document; add a test pinning the approved scale | No |
| Mo-2 | `TrainConfig` defaults silently disable center and plan terms (`train.py:37, 50`), and pilot configs differ from the approved values (epochs 3, batch 8, width 8; `b2_experiment.py:66`, `configs/b2_feat.json`). | [E] | Explicit-only config for E9 (already in P33 §1) | No |
| Mo-3 | Calibration effective sample size is smaller than the nominal count. The 8 variants of each group share plan, link and noise, so the rejection quantile uses 8·G samples from G clusters, and the clean-alarm quantile uses G samples. | [E] | Report G and the cluster structure; consider a cluster-aware bootstrap of thresholds | No |
| Mo-4 | Threshold precision: the 5 % clean-alarm threshold is fitted on 150 clean val-calib groups. A binomial approximation gives a standard error of about 1.8 percentage points for an exceedance rate of 5 % at n = 150 (about 1.0 pp at n = 500 for the test side). This is an approximation, not a data-derived interval. | [V] arithmetic | Report threshold uncertainty; bootstrap the val-calib threshold over groups | No |
| Mo-5 | Multiplicity: no correction or pre-declared family structure across families × views × methods × bins. The P18 §8 ablation set is large. | [E] | Pre-register primary endpoint and a family-level correction plan | Yes (pre-registration) |
| Mo-6 | CuC victim-conditioning: `carrier_under_carrier` placement requires the victim to be active after the shared missing-carrier event (`src/geosim/b2_scenarios.py:84–92`). ASI and unauthorized are not restricted in the same way. This is a possible shortcut between the CuC class and the missing-carrier state. Size not quantified. | [V] `b2_scenarios.py:84–92` | Quantify the rejection rate of inactive-victim draws per group; report it | No |
| Mo-7 | Plan-level redraws (up to 64 for the common plan; four matched groups redrawn) introduce population-level conditioning. It is shared within a group, so not a within-group leak, but it changes the plan distribution. | [E] `b2_scenarios.py:111–116, 227–244` | Report redraw counts per role | No |
| Mo-8 | ASI C/I is referenced to the plan-average PSD, not the victim carrier's PSD (`asi.py:278–280`), so per-carrier C/I depends on plan mix and on IBO. | [E] | Report the reference used in every per-class table | No |
| Mo-9 | The only P18 §7a claim that the matched set is "not natural" (a controlled intervention) is documented. The downstream interpretation must keep it that way. | [E] `asi.py:233` | Keep the caveat in every matched-set result | No |
| Mo-10 | Ties: rejection uses `score > threshold` for alarms (`calibration.py:79`), ROC counts equal scores as detections (`openset_metrics.py:47`). Different quantities, but undocumented side by side. | [E] | Document the convention in each table | No |
| Mo-11 | CID EUI-64 field uses `0xFFFF` where the MAC-48-derived convention normally uses `0xFFFE` (`src/geosim/cid.py:226`). This is test-only and the family is labelled "legitimate, expected clean", so impact is small. | [E] | Check against the cited clause; document if intentional | No |
| Mo-12 | Mahalanobis shrinkage target (trace-scaled identity, `mahalanobis.py:171–176`) is not stated in the approval, which says only "shrinkage 0.1". | [E] | State the target in the approved record | No (clarification) |

## 6. Minor findings

| ID | Finding | Evidence |
|---|---|---|
| Mi-1 | Literal `0.95` appears as the FPR@95TPR TPR level (`openset_metrics.py:112`) and as the known-acceptance target (`b2_experiment.py:63`). The concepts are separate, but the same number in two roles is a naming hazard. The approval already notes they differ. | [E] |
| Mi-2 | The `payload.py:221` band label is wrong for a Ku-band system. | [E] |
| Mi-3 | Seed ranges of other development stages may overlap: D1 path seeds `2g+p` (`dual_dataset.py:122`) fall in 2.0M–2.4M, which overlaps E1 group IDs 2.0M–2.2M. B2 ranges are clear of these (`b2_protocol.py:32–34`). Not in B2 scope; not assessed further. | [E] |
| Mi-4 | Pilot-A reports use "±" over seeds without definition (`docs/results/pilot_A.md:47–67`). | [E] |
| Mi-5 | The approved-parameters JSON carries the "1.9x" resource wording (line 430) that should be corrected (see M-11). The Markdown approval record does not contain it. | [V] |

## 7. Physics assessment (distinguished by evidence class)

| Claim | Class | Basis |
|---|---|---|
| Uplink/downlink Jones coupling is unitary in each block; total power over both feeds is conserved (`src/geosim/polarization.py:59–75`). Per-feed co power is not conserved (an isolated co input leaks into cross). | **Established analytical derivation** (checked by hand for J^H J = I) | [E] |
| Phase-noise increment variance `2π·Δν·dt` is the correct Wiener model for a Lorentzian FWHM linewidth (`src/geosim/phase_noise.py:40–104`). | **Established analytical derivation** | [E] |
| Phase-noise-only residual depth ceiling `−10·log10(2π·Δν·T/6)`, with Δν = 150 Hz and T = 4096/96 MHz, equals 21.74 dB. The 1/6 factor is the time-averaged variance of a Wiener phase about its block mean. | **Established analytical derivation**, reproduced by the lead auditor | [V] arithmetic; [E] `scripts/b2_e6_decision_evidence.py:65–67` |
| 22.82 dB stored-window value. | **Seeded Monte Carlo** on one realization configuration. Not a bound. | [E] `scripts/b2_e6_decision_evidence.py:78–84, 101` |
| The 150 Hz linewidth (100 Hz satellite + 50 Hz receiver) is the approved value. It is a default, not measured GEO data, and its source is not cited. | **Unverified design assumption** | `docs/plan/P15_phase_noise_and_events.md:62–64`; `src/geosim/b2_protocol.py:77–78` |
| P20's "caps depth at ≈ 21–25 dB regardless of C/N" (`P20_b2_cancellation_residual.md:122–124`). The 25 dB upper figure is not derived. | **Unverified** (only 21.7 is derived) | [E] |
| Pilot depths: 24–25 dB synthetic, about 21 dB from a reviewer, and cw minimum depth 4.5 dB in one realization (`docs/results/b2_feat_pilot.md:42–47`). | **Pilot observation** (single realizations) | [E] |
| Cancellation depth is an *upper bound* when the declared plan is exact (M-3). | **Established analytical consequence of the simulator's construction** | [E] |
| Uplink ASI geometry, C/I range and the S.465/S.1428 split. | **Prior literature evidence** cited by the docs; **not checked** here against the standard texts (not in the repo) | [E] `asi.py:1–45, 67–72`; `P18 §2` |
| CID parameters (RRC 0.35, UW values, chip rate, Table 6 PSD). | **Prior literature evidence** cited (ETSI TS 103 129, not in repo) | [E] `cid.py:36–50, 149–157` |
| Overdrive label behaviour. | **Unverified** (amplifier model unchecked, M-12) | [E] |
| The 0.7 dB Gmax step at D/λ = 100 in ASI. | **Established from code**; accuracy against ITU not checked | [E] `asi.py:103–106` |

## 8. Statistical and leakage risks (summary)

Detailed analysis is in [the statistical review](B2_E9_OPEN_SET_STATISTICAL_REVIEW.md). Key points:

- **Role isolation is sound in the isolated path.** Train-only normalization and Mahalanobis fitting [V in part, E otherwise].
  All variants of a group share a role, enforced by shard construction and cross-role checks (`b2_dataset.py:129–132,
  354–364`; `b2_experiment.py:128–132`) [E].
- **Input leakage is clean.** Model input is spec, mask and residual only (`b2_stream.py:69`; `train.py:73–98`) [E].
  Labels and `plan_consistency` are targets only [E]. No path from activity, IBO, XPD or symbols into inputs was found [E].
- **Barrier before test read is structural, not ledgered.** The isolated path opens test only after inventory
  validation (`b2_execution.py:431, 488`) [E]. Nothing records earlier test reads (C-1).
- **Seeds and CIs** are discussed in M-6 and M-7.

## 9. Required future validation experiments (proposals; each needs approval)

None of these is authorized by this review. Each is a proposal for a researcher decision.

| ID | Proposal | Stage | Compute? | Blocks |
|---|---|---|---|---|
| V-1 | Commit the K17d identity generator and emit the 35/465 lists from frozen metadata with checksums, before any test read | pre-test | metadata only | Final test read |
| V-2 | Disclose and quarantine pilot test exposure; decide accept vs re-version (C-1) | governance | none | Final test read |
| V-3 | Unit tests asserting the approved clean-alarm `higher` quantile and the TF32 flags (M-1, M-2) | engineering | CPU only | Any GPU work |
| V-4 | Receiver-level plan-parameter error sweep (frequency, rate, modulation) for the residual channel (M-3) | development | CPU, bounded | Interpretation of residual results |
| V-5 | Operator-receiver contract decision for cross-pol inputs (M-4) | governance | none | Interpretation of `dual` results |
| V-6 | Machine-readable 150-group matched-role diagnostics for observed in-band PSD, computed before evaluation (M-8) | pre-test | metadata + spectra, no outcomes | Matched-claim wording |
| V-7 | Threshold stability: bootstrap of val-calib thresholds over groups (Mo-4) | calibration | CPU, val-calib only | Pfa claims |
| V-8 | Seed replication beyond 3 seeds (proposal, cost-bearing) | statistics | GPU if run | Seed-level CIs |
| V-9 | Amplifier validation against the cited source (M-12) | physics | CPU | Overdrive claims |
| V-10 | Linewidth sourcing, or a sensitivity sweep over linewidth for the depth ceiling (M-3, Section 7) | physics | analytic | Ceiling claims |
| V-11 | Sensitivity of uplink/downlink ASI to geometry and frequency (M-13) | physics | CPU | ASI claims |
| V-12 | Ablation table completion per P18 §8 with a single pre-registered primary endpoint (Section 9 of the publication checklist) | statistics | GPU if run | Publication |

## 10. Go / no-go recommendation

- **Production data generation:** **NO-GO.** Blocked by C-1, C-2, M-1 and M-2.
- **GPU probe, nine-fit training, held-out evaluation, LOKO:** **NO-GO.** Blocked by the same plus the unresolved
  resource figures (M-11). The approval record already keeps these NOT_AUTHORIZED.
- **Engineering review of this document's findings:** **GO.** The findings are concrete and file-referenced. The
  Critical and Major engineering items (M-1, M-2, M-5, C-2 procedure, V-3) can be reviewed without any compute or
  data action.
- **Scientific claims in any future report:** do not state any recognition performance. No pilot, fixture or
  analytical result in this review supports a performance claim.

## 11. Evidence matrix

| Ref | Claim | Location | Class | Verified by lead |
|---|---|---|---|---|
| E-01 | Clean-alarm quantile is linear | `src/geoml/metrics.py:38` | Code fact | Yes |
| E-02 | Rejection quantile is "higher" | `src/geoml/calibration.py:131` | Code fact | Yes |
| E-03 | Approved clean-alarm method is "higher" | `docs/plan/b2_e9_approved_scientific_protocol.json:334` | Approved record | Yes (earlier read) |
| E-04 | Center loss mean vs sum scale | `src/geoml/b2_model.py:79`, `src/geoml/model.py:77` | Code fact | Yes (b2_model); model.py extracted |
| E-05 | No TF32 flags anywhere | repository grep | Code fact | Yes |
| E-06 | Approved TF32 requirement | `docs/plan/b2_e9_approved_scientific_protocol.json:81–82` | Approved record | Yes |
| E-07 | P18 records E8 cuDNN TF32 default | `docs/plan/P18_b2_protocol.md:252` | Documented fact | Yes (earlier read) |
| E-08 | K17d counts 500/78/35/43 | `docs/results/k17d_drift_audit.json` | Committed result | Yes |
| E-09 | K17d drift median/p90/max 0.71/2.93/5.91 dB | same JSON | Committed result | Yes |
| E-10 | Matched check is 2 groups, no recognition metrics | `docs/results/b2_matched_check.json` | Committed result | Yes |
| E-11 | Pilot test/test-matched partitions exist | `docs/results/b2_full_pilot.json:111, 144` | Committed result | Yes (grep) |
| E-12 | Pilot test families ran on test role | `docs/results/b2_test_pilot.md` | Committed doc | Yes (head) |
| E-13 | CuC victim conditioning | `src/geosim/b2_scenarios.py:84–92` | Code fact | Yes |
| E-14 | Depth ceiling 21.74 dB | `scripts/b2_e6_decision_evidence.py:65–67`; `docs/results/b2_e6_decision_evidence.json:61` | Analytical + code | Arithmetic yes |
| E-15 | Exact plan assumption | `docs/plan/P20_b2_cancellation_residual.md:120–121`; `src/geosim/cancellation.py:150–151, 166–170` | Doc + code | Doc yes (earlier read) |
| E-16 | Two cancellers imported | `src/geosim/b2_dataset.py:31`; `src/geosim/b2_features.py:47` | Code fact | No (extracted) |
| E-17 | Cross-pol channels in model input | `docs/plan/P18_b2_protocol.md:30–35`; `src/geoml/b2_data.py:49–83` | Doc + code | Doc yes |
| E-18 | Co-pol invariant text | `.claude/rules/scientific-invariants.md` item 1 | Governance doc | Yes (given at session start) |
| E-19 | Freeze barrier in isolated path | `src/geoml/b2_execution.py:242, 286, 431, 488` | Code fact | No (extracted) |
| E-20 | Legacy path opens test | `src/geoml/b2_experiment.py:436, 493–501, 822–826` | Code fact | No (extracted) |
| E-21 | Seed-level SD in code, not in outputs | `src/geoml/b2_loko_matrix.py:372–373`; `docs/results/B2_SCIENTIFIC_RESULTS_ATLAS.md:162` | Code + doc | No (extracted) |
| E-22 | Scenario bootstrap conditional | `src/geoml/metrics.py:21–35`; `src/geoml/b2_experiment.py:142–148` | Code fact | No (extracted) |
| E-23 | Plan-consistency target not recomputed under shift | `src/geoml/b2_stream.py:424, 533`; `src/geoml/train.py:186–208` | Code fact | No (extracted) |
| E-24 | Amplifier unverified | `src/geosim/payload.py:78, 221` | Code comment | No (extracted) |
| E-25 | ASI downlink geometry | `src/geosim/asi.py:250` | Code fact | No (extracted) |
| E-26 | GPU-hour figures | `docs/plan/b2_e9_approved_scientific_protocol.json:430`; `docs/plan/B2_E7_TRAINING_SPEC_PROPOSAL.md:176`; `docs/plan/P33_b2_e9_production_executor_readiness.md:17` | Docs | Yes (grep) |
| E-27 | Approval K17d re-derivation requirement | `docs/plan/B2_E9_SCIENTIFIC_DECISION_APPROVAL_2026-10-24.md:16` | Approved record | Yes (earlier read) |
| E-28 | Three-seed design | `docs/plan/b2_e9_approved_scientific_protocol.json:38–41` | Approved record | Yes (earlier read) |
| E-29 | Approved clean-alarm and acceptance numbers | `docs/plan/b2_e9_approved_scientific_protocol.json:330–336` | Approved record | Yes (earlier read) |

## 12. Items not checked

- Standards texts (ETSI TS 103 129, EN 302 307, ITU-R S.1428/S.465/F.699, R19-WRS20-C-0013, FCC Part 25) are not in the
  repository. Any citation of them here is taken from the docs, not from the standards.
- No data, checkpoints, or tests were produced or run. The `data/` and `runs/` trees were absent.
- The K17d row generator (not committed) and its run date were not found.
- Whether E9 pre-test re-derivation is implemented outside this repository was not checked.
- Pilot-run commit provenance was taken from JSON fields, not re-executed.

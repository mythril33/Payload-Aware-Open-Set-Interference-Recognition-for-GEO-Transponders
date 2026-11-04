# B2 E9 — publication readiness checklist

**Reconciled status — 2026-11-04, baseline `3f26393`.** This checklist began as an
E9 audit at `d7df413`. The rows below now distinguish later engineering fixes,
E12 scientific decisions and work still awaiting production evidence. Historical
findings remain in [the independent audit](B2_E9_INDEPENDENT_SCIENTIFIC_AUDIT.md),
[the statistical review](B2_E9_OPEN_SET_STATISTICAL_REVIEW.md) and
[E10 closure](B2_E10_CRITICAL_FINDINGS_CLOSURE.md). Later authority comes from
[the E12 D-1–D-8 record](../plan/B2_E12_D1_D8_SCIENTIFIC_APPROVAL_2026-10-24.md),
not from this checklist. No final benchmark has been run.

**Question answered:** could the methodology support a reproducible publication
**after separately authorized experiments**? The design and explicit limitations
can support a methods/protocol manuscript; recognition-performance claims still
need the full experiment and its remaining checks. **Publication-ready: No.**
Full generation, GPU qualification/training, LOKO and final held-out evaluation
remain unauthorized; `benchmark_complete=false`.

**Status key:** PASS (met by the cited committed evidence), PARTIAL, FAIL
(contradicted by evidence), OPEN (requires additional evidence or execution), N/A.
A resolved wording or decision issue does not certify production execution.

## 1. Reproducibility and provenance

| # | Item | Status | Evidence / note |
|---|---|---|---|
| R-1 | Source revision pinned for every result | PARTIAL | Pilot provenance exists; the later real-execution adapters bind source/configuration identities. No full production result or qualified host evidence exists; see `../operations/B2_E18_STAGE_BOUNDARY_CHECKLIST.md`. |
| R-2 | Data fingerprints for every role | PASS for pilots | `data_fingerprint` and `experiment_fingerprint` in `docs/results/b2_full_pilot.json` [V]. Not yet for the full benchmark. |
| R-3 | Prior exposure disclosed; future final read frozen | PARTIAL (D-1 ratified) | Existing test is not pristine. E12 D-1 preserves 500/150 headline groups and requires 498/148 exposure-excluded rows. Future freeze and final read remain NOT RUN; the historical exposure cannot be undone. |
| R-4 | K17d identities re-derivable from committed artifacts | PASS for accepted metadata; production OPEN | E10 added metadata derivation; E12 D-8 accepted the source/audit-bound 500/35/465 identity. `../results/B2_E12_D1_D8_VERIFICATION.md` records verification. The actual production-metadata cross-check is NOT RUN. |
| R-5 | Configuration explicit (no implicit defaults) | PARTIAL | Approved record lists all settings. `TrainConfig` defaults silently disable center and plan terms (`src/geoml/train.py:37, 50`) [E]. Pilot configs differ. |
| R-6 | Numeric policy enforced (TF32, precision, autocast) | PARTIAL (M-2) | `src/geoml/b2_production_training.py` now sets and verifies the R6 flags in its scoped adapter; `tests/test_b2_production_training.py` checks them. GPU qualification and production enforcement evidence remain absent. |
| R-7 | Reproducible environment pinned (Torch, CUDA, cuDNN, driver, GPU) | FAIL | Approved record requires it; no lock exists yet (`b2_e9_approved_scientific_protocol.json:245`). |
| R-8 | Result reproduction from a documented command | PARTIAL | Commands and bounded adapter handoff exist in P20/P31 and the E18 stage-boundary checklist; the full campaign has not run. |
| R-9 | Negative and inconclusive results kept | PASS | Pilots report chance-level accuracy and physical misses (`docs/results/b2_observed_pilot.md`, `b2_feat_pilot.md`) [E]. |
| R-10 | Interrupted-run policy | PARTIAL | R9 approved; isolated resume and later lifecycle/durability adapters are tested at bounded scale. Independent production backup/restore qualification remains open. |

## 2. Protocol and design

| # | Item | Status | Evidence / note |
|---|---|---|---|
| P-1 | Known classes defined by a generative rule | PASS | `docs/plan/P18_b2_protocol.md` §2. |
| P-2 | Unknown families defined before results | PASS | P18 §3, grouping fixed before results. |
| P-3 | Confusable pairs pre-registered | PASS | P18 §6 (ASI ↔ unauthorized as "design-confusable"). |
| P-4 | Primary endpoint pre-registered | PARTIAL | D-4 designates near-family pooled unknown-positive FPR@95TPR on `dual_residual`. One primary scorer is still NOT DESIGNATED; it must be fixed before the final read. |
| P-5 | Multiplicity and claim scope stated | PASS for descriptive scope | D-4 makes other metrics and contrasts exploratory; no confirmatory superiority or unadjusted multiple-testing significance claim is approved. No multiplicity-adjusted inference is claimed. |
| P-6 | Operator-receiver contract for dual-pol inputs | PASS as conditional assumption | E12 D-2 requires calibrated co/cross monitors and two separately declared plans. It is not a claim that every GEO receiver provides these inputs. |
| P-7 | Physical threat model stated for each class | PARTIAL | Physics in P14/P15; ASI geometry is uplink-equivalent for downlink (M-13); overdrive depends on unvalidated amplifier (M-12). |
| P-8 | Level-matched controls for confusable pairs | PARTIAL | K17c exists; only two groups checked; observed PSD not matched (M-8). |
| P-9 | Plan error and shortcut controls | PARTIAL | A5 counterfactuals exist; receiver-level plan-error sweep not run (M-3). |
| P-10 | Shortcut audit (labels encoded in inputs) | PARTIAL | No activity/IBO/XPD in inputs (audit §8) [E]. CuC victim-conditioning shortcut not quantified (Mo-6). |

## 3. Models and training

| # | Item | Status | Evidence / note |
|---|---|---|---|
| T-1 | Loss implemented as approved | PARTIAL | Correct on the isolated chain (`b2_stream.py:546–551`); `B2Model` center scale differs (Mo-1). |
| T-2 | Optimizer, scheduler, precision as approved | PARTIAL | E9 recipe retained; R6 enforcement now exists in the real-training adapter (R-6). A pinned, qualified GPU execution of that recipe is still NOT RUN. |
| T-3 | Augmentation restricted to training | PASS | `b2_stream.py:534–537`; inference unaugmented [E]. |
| T-4 | Plan-shift label semantics clarified | PASS | E12 D-3 defines the target as physical missing-carrier state, preserved under mask shifts; it is not general plan–spectrum alignment. |
| T-5 | Checkpoint selection on validation only | PASS | Val-select only (`b2_execution.py:242`; `b2_stream.py:568`) [E]. |
| T-6 | Baselines with equal budget | PARTIAL | P26 (EDSC), P27 (XGBoost) have bounded results only [E]. |
| T-7 | Untuned hyperparameters stated as untuned | PARTIAL | Center weight 0.005 fixed in P20 (stated). Epoch and width choices in the pilot differ from the approved values. |
| T-8 | Seed count and permitted claims explicit | PASS for descriptive scope; results OPEN | D-4 retains seeds 0/1/2 and reports individual values plus descriptive mean; no seed-level CI or best-seed selection. |

## 4. Calibration and metrics

| # | Item | Status | Evidence / note |
|---|---|---|---|
| C-1 | Rejection threshold from known val-calib only | PASS | `b2_execution.py:286, 319`; `calibration.py:131` [V] (`higher`). |
| C-2 | Clean-alarm threshold per approved quantile rule | PASS on E9 path | E10 fixed `clean_alarm_threshold`; E12 D-6 ratifies NumPy `higher`, stable summed non-clean probabilities and strict `score > threshold`. Historical linear/subtraction results retain their old meaning. |
| C-3 | Threshold uncertainty reported | FAIL | No interval (Mo-4). |
| C-4 | Unknown-positive AUROC, AUPR, FPR@95TPR defined with denominators | PASS | `openset_metrics.py:51, 97, 109–112` [E]; `docs/plan/P18_b2_protocol.md` §7. |
| C-5 | FPR@95TPR distinct from 0.95 known acceptance | PASS | Separate code paths (see statistical review §6.1). Naming hazard noted (Mi-1). |
| C-6 | Scores with declared direction | PASS | MSP, energy, Mahalanobis, clean-alarm all larger = more unknown-like [E]. |
| C-7 | Ties and strict/inclusive rules stated | PARTIAL | E12 D-6 states strict clean alarm (equality is non-alarm); R10 states inclusive known acceptance. A single consolidated metric/tie table remains a reporting task. |
| C-8 | Mahalanobis regularization target stated | PARTIAL | Target is trace-scaled identity in code, not in approval (Mo-12). |
| C-9 | Counts and denominators in every table | OPEN | Required for the final report; pilots comply. |

## 5. Statistics and uncertainty

| # | Item | Status | Evidence / note |
|---|---|---|---|
| S-1 | Scenario-group bootstrap for paired variants | PASS | `src/geoml/metrics.py:21–35` [E]; approval states the rule. |
| S-2 | Bootstrap labelled as conditional on the frozen bundle | PASS as reporting rule; final reporting OPEN | D-4 requires conditioning on frozen models/calibrators. The atlas explicitly excludes training/calibration/simulator uncertainty; future full tables are NOT RUN. |
| S-3 | Seed-level variation separated from scenario uncertainty | PARTIAL | D-4 states the distinction and descriptive seed reporting. The final three-seed result table does not yet exist. |
| S-4 | Seed-level CI only with adequate seed count | PASS as reporting restriction | No seed-level CI from the three planned seeds is permitted by D-4; no such CI is claimed. |
| S-5 | Combined uncertainty method pre-registered | N/A for current scope | Scenario uncertainty remains conditional; D-4 authorizes no combined training/calibration/simulator uncertainty claim. |
| S-6 | Null and small-count handling | PASS | `null` plus counts used in pilots (`b2_observed_pilot.md`) [E]. |
| S-7 | Significance tests | N/A | No confirmatory claim is approved. The later C2 comparison specifies paired whole-group resampling for exploratory contrasts; full experiments remain NOT RUN. |

## 6. Ablations

P18 §8 lists these ablations. Status against the committed record:

| Ablation | Purpose | Status |
|---|---|---|
| A0 co-only | baseline with no plan or cross-pol | Pilot only |
| A1 + plan | value of plan masks | Pilot only |
| A2 + dual-pol (main) | value of cross-pol | Pilot only |
| A3 linear chain, nonlinear test (C3) | linear-nonlinear generalization | Not run |
| A4 minus cancellation residual; A4b + SCF | value of the residual channel; SCF alternative | Not run (A4 is the 4-channel pilot only) |
| A5 plan corruption (stale, shifted, missing) | plan-shortcut robustness | Partly run on frozen checkpoints (P28 capped smoke) |
| A6 amplifier transfer (R1) | amplifier generalization | Not run |
| A7 FiLM conditioning | alternative input fusion | Not run |
| A8 unknown families and LOKO | open-set and leave-one-out | Bounded LOKO harness only; full sweep NOT_AUTHORIZED |

**Missing for publication (proposal, needs researcher approval):**

- A4 and A4b run on the full benchmark, with paired bootstrap on the residual-channel contribution.
- A6 with a validated amplifier model (depends on M-12).
- A plan-error sweep at receiver level (M-3).
- A "no-plan" version of the residual, to separate the cancellation gain from the plan gain.

## 7. Likely reviewer objections and the honest answer

| Objection | Current answer | What would be needed |
|---|---|---|
| "The unknowns are variants of the known classes, so open-set is easy or artificially hard." | Stated in P18 §9; families grouped before results. | Leave-one-known-out results with the same budget (A8, currently NOT_AUTHORIZED). |
| "ASI and unauthorized are the same signal; eight classes are artificial." | Pre-registered as design-confusable; matched check exists. | Full 150-group matched evaluation and observed-PSD diagnostics (M-8). |
| "Your cancellation uses the exact plan. This is an oracle." | Partly: symbols and activity are excluded; plan parameters are exact. | Plan-error sweep (M-3); explicit "conditional on declared plan" wording. |
| "Cross-pol is available to a real receiver?" | D-2 explicitly assumes calibrated dual monitors and two declared plans. | State this conditional capability in every deployment claim. |
| "Three seeds are not enough to say anything about variability." | D-4 permits individual values and descriptive summaries only. | Populate the final seed table; no seed-level CI. |
| "Your Pfa of 5 % is not 5 %." | E10/D-6 fixed the E9 quantile; calibration target is not a test-population guarantee. | Realized test rates/counts and threshold uncertainty reporting (Mo-4 still open). |
| "Test was read in pilots." | D-1 ratified disclosure and retained roles; existing test is not pristine. | Report mandatory 498/148 exclusions alongside 500/150 headlines in the authorized final read. |
| "Is the simulator physical?" | Simulator constants partly from literature; many `[VARSAYIM]` (P18 §2). | Sensitivity analysis (R2-eval/1 proposal in P18 §9) and sourced linewidths (V-10). |
| "Why does the cancellation ceiling not match your depth?" | Analytical 21.74 dB; Monte Carlo 22.82 dB; pilot values single realizations. | Bounded Monte Carlo over Wiener realizations, reported as a distribution. |
| "The GPU budget claim is inconsistent." | [Consolidated source-backed table](../results/B2_RESOURCE_RECONCILIATION.md) separates measured anchors, assumptions, 9/15/21 fits and the M-11 erratum. | Qualify the designated GPU/loader and set an approved run-specific budget. |
| "Multiple comparisons." | D-4 fixes endpoint/view and restricts other comparisons to exploratory reporting. | Designate the scorer before the final read; no confirmatory multiple-comparison claim. |

## 8. Recommended reporting tables (for a future publication)

1. **Protocol and provenance table:** protocol version, role counts, seed ranges, source hash, data fingerprint, environment lock.
2. **Physics table:** class, entry point, parameter ranges, source per parameter (literature or `[VARSAYIM]`).
3. **Closed-set table:** 8-class accuracy, macro-F1, confusion matrix, ECE. Counts and denominators.
4. **Open-set table:** per family, unknown-positive AUROC, AUPR, FPR@95TPR, with n and group-bootstrap intervals.
5. **Operating-point table:** known acceptance (0.95 quantile on known val-calib) and clean alarm (Pfa 0.05 on clean val-calib),
   with the realized test rates, n, and threshold uncertainty. Two operating points, labelled separately.
6. **Seed table:** every seed separately for the headline method, with the range. No CI from 3 seeds.
7. **K17d table:** headline (500) and sensitivity (465), the [committed 35-group drift table](../results/B2_K17D_M14_DRIFT_TABLE.md), and future metric differences. Separately report D-1 exposure exclusions (498/148 versus 500/150); these are different populations.
8. **K17c table:** 2×2 and confusion matrix; recall and precision per class; the 7–10 dB natural slice for comparison;
   observed-PSD matched diagnostic.
9. **Cancellation table:** depth distribution per class (not just the mean), gap-floor shift, decision SNR, and the
   analytical ceiling with its assumptions (linewidth, duration, plan exactness).
10. **Ablation table:** every P18 §8 ablation with the same budget, primary endpoint marked.
11. **Limitations table:** each simulator assumption with its status (sourced / `[VARSAYIM]` / unverified).

## 9. What the publication may and may not claim (now)

**May claim (after the required experiments, with the caveats stated):**

- A reproducible simulation benchmark with a frozen protocol, its provenance chain and its pilot record.
- Separate analytical bounds (for example the 21.74 dB phase-noise-only ceiling under stated assumptions).
- The pre-registered confusability of ASI and unauthorized by design, and a level-matched diagnostic if the 150-group
  evaluation is completed.

**May not claim (today, or without the final read):**

- Any recognition accuracy, AUROC, FPR@95TPR, or Pfa figure for the B2 benchmark.
- That the dual-polarization input improves recognition over co-pol (requires the final ablation).
- That the cancellation residual is a practical observation-based receiver, while plan parameters are exact (M-3).
- Any seed-level confidence interval from three seeds.
- Any claim about real GEO data. None exists (DURUM §5.5).

## 10. Current dispositions and remaining delivery work

The old E9 totals "0 of 2 Critical" and "0 of 14 Major" describe that historical
audit, not today's status. A single closure count would mix decision ratification,
engineering fixes, reporting corrections and unrun production checks. Use these
scoped dispositions instead:

| Audit item | Current disposition | Remaining evidence |
|---|---|---|
| Critical C-1 | D-1 scientific disposition ratified; prior exposure disclosed | Existing test remains non-pristine; future 500/150 and 498/148 reporting, freeze and authorized final read |
| Critical C-2 | E10 metadata derivation implemented; D-8 source/audit-bound identity accepted | Actual production-metadata cross-check NOT RUN |
| M-1 | E9 quantile and saturation fix implemented; D-6 ratified | Final operating-point reporting; historical results not rewritten |
| M-2 | R6 flag enforcement implemented in later training adapter | Qualified GPU runtime and production evidence NOT RUN |
| M-3 | D-5 sensitivity design preregistered only | SNR/modulation-pair/sampling/budget details and execution remain open |
| M-4 | D-2 conditional receiver contract ratified | Preserve the input-availability limitation in claims |
| M-5 | E10 stage-to-canceller mapping documented | Preserve primary `obs-cancel/1` versus development-receiver distinction |
| M-6 | D-4 descriptive seed reporting specified | Final per-seed values unavailable; no seed CI |
| M-7 | D-4 conditional-bootstrap reporting rule ratified | Apply it to final tables; no combined-uncertainty claim |
| M-8 | Injected-power versus observed-PSD distinction documented | Full 150-group observed-PSD diagnostic and evaluation NOT RUN |
| M-9 | D-3 missing-carrier target semantics ratified | Preserve the physical-state interpretation under mask shifts |
| M-10 | E12 default-deny legacy CLI/API guard implemented and tested | Production final-read authority and freeze remain separate |
| M-11 | Dated arithmetic erratum and consolidated table supplied | Target-host measurements and approved 15-fit ceiling absent |
| M-12 | Saleh/amplifier validation still OPEN | Physics validation; no validated transfer claim |
| M-13 | Uplink-equivalent downlink-ASI assumption documented | Retain limitation; no independently validated downlink geometry claim |
| M-14 | All 35 co-feed drift rows disclosed from committed audit metadata | D-8 production cross-check and final 500/465 metric comparison NOT RUN |
| Final experiments / publication | **0 final experiments; publication-ready: No** | Full campaign, reporting and remaining provenance/publication decisions |

Evidence: [E10 closure](B2_E10_CRITICAL_FINDINGS_CLOSURE.md),
[E12 ratification](../plan/B2_E12_D1_D8_SCIENTIFIC_APPROVAL_2026-10-24.md),
[E12 verification](../results/B2_E12_D1_D8_VERIFICATION.md),
[later adapter handoff](../operations/B2_E18_STAGE_BOUNDARY_CHECKLIST.md),
[M-14 table](../results/B2_K17D_M14_DRIFT_TABLE.md),
[M-11 erratum](../results/B2_P1_RESOURCE_ERRATA.md) and
[resource reconciliation](../results/B2_RESOURCE_RECONCILIATION.md).

**Next work:** designate the primary scorer; qualify the actual generation/GPU/
backup hosts and budgets; finish the remaining receiver sensitivity design and
physics/provenance items. The declared minimum C2 campaign is **15 fits** (nine
canonical plus six matched dual controls), not nine alone. Execution still needs
the separate DR-04/DR-05 and final-read records. Neither this reconciliation nor
scientific-method ratification opens those gates.

## 11. Limits

- This checklist is a judgement built from committed evidence. Items marked PASS are pass on the evidence seen, not verified by re-running.
- No external reviewer endorsement is implied. The reviewing agents are internal read-only passes.
- The publication path depends on decisions this review does not make.

# B2 E9 — publication readiness checklist

**Status:** review checklist, read-only. Companion to
[the independent audit](B2_E9_INDEPENDENT_SCIENTIFIC_AUDIT.md) and
[the open-set statistical review](B2_E9_OPEN_SET_STATISTICAL_REVIEW.md).
**Baseline:** `origin/main` `d7df413`. **No performance claim is made or implied.** No final benchmark has been run.

**Question answered:** could the *current methodology* support a reproducible publication **after separately
authorized experiments**? Answer: **not yet.** The design is publishable as a protocol paper or a simulation-benchmark
paper with honest negative or inconclusive results. It is not publishable as a recognition-performance paper until the
Critical and Major items in the audit are closed and the final benchmark has been run once under the frozen protocol.

**Status key:** PASS (met by committed evidence), PARTIAL, FAIL (contradicted by committed evidence), OPEN (not yet
evaluable, requires full benchmark), N/A.

## 1. Reproducibility and provenance

| # | Item | Status | Evidence / note |
|---|---|---|---|
| R-1 | Source revision pinned for every result | PARTIAL | Pilot JSON carries a revision (`docs/results/b2_full_pilot.json`); the audit found a source-identity fingerprint pattern in the E4/E5 work, but the approved executor does not yet exist. |
| R-2 | Data fingerprints for every role | PASS for pilots | `data_fingerprint` and `experiment_fingerprint` in `docs/results/b2_full_pilot.json` [V]. Not yet for the full benchmark. |
| R-3 | Protocol frozen before the final read | FAIL (C-1) | Pilots read two test and two test-matched groups. Must be disclosed and resolved. |
| R-4 | K17d identities re-derivable from committed artifacts | FAIL (C-2) | No committed generator. Counts are reproducible only from the JSON. |
| R-5 | Configuration explicit (no implicit defaults) | PARTIAL | Approved record lists all settings. `TrainConfig` defaults silently disable center and plan terms (`src/geoml/train.py:37, 50`) [E]. Pilot configs differ. |
| R-6 | Numeric policy enforced (TF32, precision, autocast) | FAIL (M-2) | No flags set or recorded [V by grep]. |
| R-7 | Reproducible environment pinned (Torch, CUDA, cuDNN, driver, GPU) | FAIL | Approved record requires it; no lock exists yet (`b2_e9_approved_scientific_protocol.json:245`). |
| R-8 | Result reproduction from a documented command | PARTIAL | Commands in `CLAUDE.md` and P20/P31; executor for full scale not built. |
| R-9 | Negative and inconclusive results kept | PASS | Pilots report chance-level accuracy and physical misses (`docs/results/b2_observed_pilot.md`, `b2_feat_pilot.md`) [E]. |
| R-10 | Interrupted-run policy | PARTIAL | R9 approved; isolated executor has resume checks; full executor absent. |

## 2. Protocol and design

| # | Item | Status | Evidence / note |
|---|---|---|---|
| P-1 | Known classes defined by a generative rule | PASS | `docs/plan/P18_b2_protocol.md` §2. |
| P-2 | Unknown families defined before results | PASS | P18 §3, grouping fixed before results. |
| P-3 | Confusable pairs pre-registered | PASS | P18 §6 (ASI ↔ unauthorized as "design-confusable"). |
| P-4 | Primary endpoint pre-registered | FAIL | None designated (audit Mo-5). |
| P-5 | Family-wise multiplicity control | FAIL | None (Mo-5). |
| P-6 | Operator-receiver contract for dual-pol inputs | FAIL | Cross-pol channels without an explicit receiver contract (M-4). |
| P-7 | Physical threat model stated for each class | PARTIAL | Physics in P14/P15; ASI geometry is uplink-equivalent for downlink (M-13); overdrive depends on unvalidated amplifier (M-12). |
| P-8 | Level-matched controls for confusable pairs | PARTIAL | K17c exists; only two groups checked; observed PSD not matched (M-8). |
| P-9 | Plan error and shortcut controls | PARTIAL | A5 counterfactuals exist; receiver-level plan-error sweep not run (M-3). |
| P-10 | Shortcut audit (labels encoded in inputs) | PARTIAL | No activity/IBO/XPD in inputs (audit §8) [E]. CuC victim-conditioning shortcut not quantified (Mo-6). |

## 3. Models and training

| # | Item | Status | Evidence / note |
|---|---|---|---|
| T-1 | Loss implemented as approved | PARTIAL | Correct on the isolated chain (`b2_stream.py:546–551`); `B2Model` center scale differs (Mo-1). |
| T-2 | Optimizer, scheduler, precision as approved | PARTIAL | OneCycleLR settings implicit (`b2_stream.py:515`); TF32 unset (M-2). |
| T-3 | Augmentation restricted to training | PASS | `b2_stream.py:534–537`; inference unaugmented [E]. |
| T-4 | Plan-shift label semantics clarified | FAIL | Plan-consistency target not recomputed under shift (M-9). |
| T-5 | Checkpoint selection on validation only | PASS | Val-select only (`b2_execution.py:242`; `b2_stream.py:568`) [E]. |
| T-6 | Baselines with equal budget | PARTIAL | P26 (EDSC), P27 (XGBoost) have bounded results only [E]. |
| T-7 | Untuned hyperparameters stated as untuned | PARTIAL | Center weight 0.005 fixed in P20 (stated). Epoch and width choices in the pilot differ from the approved values. |
| T-8 | Seed count sufficient for seed-level claims | FAIL | 3 seeds (R1). Not sufficient for seed-level intervals (M-6). |

## 4. Calibration and metrics

| # | Item | Status | Evidence / note |
|---|---|---|---|
| C-1 | Rejection threshold from known val-calib only | PASS | `b2_execution.py:286, 319`; `calibration.py:131` [V] (`higher`). |
| C-2 | Clean-alarm threshold per approved quantile rule | FAIL | Linear default at `src/geoml/metrics.py:38` [V] (M-1). |
| C-3 | Threshold uncertainty reported | FAIL | No interval (Mo-4). |
| C-4 | Unknown-positive AUROC, AUPR, FPR@95TPR defined with denominators | PASS | `openset_metrics.py:51, 97, 109–112` [E]; `docs/plan/P18_b2_protocol.md` §7. |
| C-5 | FPR@95TPR distinct from 0.95 known acceptance | PASS | Separate code paths (see statistical review §6.1). Naming hazard noted (Mi-1). |
| C-6 | Scores with declared direction | PASS | MSP, energy, Mahalanobis, clean-alarm all larger = more unknown-like [E]. |
| C-7 | Ties and strict/inclusive rules stated | PARTIAL | Documented in code; not in one table (Mo-10). |
| C-8 | Mahalanobis regularization target stated | PARTIAL | Target is trace-scaled identity in code, not in approval (Mo-12). |
| C-9 | Counts and denominators in every table | OPEN | Required for the final report; pilots comply. |

## 5. Statistics and uncertainty

| # | Item | Status | Evidence / note |
|---|---|---|---|
| S-1 | Scenario-group bootstrap for paired variants | PASS | `src/geoml/metrics.py:21–35` [E]; approval states the rule. |
| S-2 | Bootstrap labelled as conditional on the frozen bundle | FAIL | Not labelled that way in the atlas (M-7). |
| S-3 | Seed-level uncertainty separated from scenario uncertainty | PARTIAL | Stated in approval; the code computes a seed SD that no committed output reports (M-6). |
| S-4 | Seed-level CI only with adequate seed count | FAIL | 3 seeds (M-6). |
| S-5 | Combined uncertainty method pre-registered | FAIL | None. |
| S-6 | Null and small-count handling | PASS | `null` plus counts used in pilots (`b2_observed_pilot.md`) [E]. |
| S-7 | Significance tests | N/A | None present. A claim of difference needs a paired bootstrap with a stated method, which does not exist yet. |

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
| "Cross-pol is available to a real receiver?" | Not stated as a contract. | Operator-receiver contract (M-4). |
| "Three seeds are not enough to say anything about variability." | Agreed; reported as range. | More seeds (proposal) or no seed-level claim. |
| "Your Pfa of 5 % is not 5 %." | Threshold uncertainty not reported; quantile method deviates (M-1). | Fix quantile method; report threshold interval (Mo-4). |
| "Test was read in pilots." | Disclosed here (C-1). | Disclosure in the approval record and a decision on re-versioning. |
| "Is the simulator physical?" | Simulator constants partly from literature; many `[VARSAYIM]` (P18 §2). | Sensitivity analysis (R2-eval/1 proposal in P18 §9) and sourced linewidths (V-10). |
| "Why does the cancellation ceiling not match your depth?" | Analytical 21.74 dB; Monte Carlo 22.82 dB; pilot values single realizations. | Bounded Monte Carlo over Wiener realizations, reported as a distribution. |
| "The GPU budget claim is inconsistent." | Yes, across documents (M-11). | One reconciled resource table. |
| "Multiple comparisons." | Not controlled (Mo-5). | Primary endpoint and family-wise plan. |

## 8. Recommended reporting tables (for a future publication)

1. **Protocol and provenance table:** protocol version, role counts, seed ranges, source hash, data fingerprint, environment lock.
2. **Physics table:** class, entry point, parameter ranges, source per parameter (literature or `[VARSAYIM]`).
3. **Closed-set table:** 8-class accuracy, macro-F1, confusion matrix, ECE. Counts and denominators.
4. **Open-set table:** per family, unknown-positive AUROC, AUPR, FPR@95TPR, with n and group-bootstrap intervals.
5. **Operating-point table:** known acceptance (0.95 quantile on known val-calib) and clean alarm (Pfa 0.05 on clean val-calib),
   with the realized test rates, n, and threshold uncertainty. Two operating points, labelled separately.
6. **Seed table:** every seed separately for the headline method, with the range. No CI from 3 seeds.
7. **K17d table:** headline (500) and sensitivity (465), the 35-group drift histogram, and their difference.
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

## 10. Gate summary

| Gate | Result |
|---|---|
| Critical findings closed | 0 of 2 (C-1, C-2) |
| Major findings closed | 0 of 14 (M-1 … M-14) |
| Experiments run | 0 final; pilots only |
| Publication-ready | **No** |

**Recommended next step (for researcher decision, not an action taken here):** close C-1 and C-2 first (disclosure and
reproducible K17d procedure), then the engineering items M-1 and M-2 with their unit tests, then decide the receiver
contract (M-4) and the plan-error sweep (M-3). Only then consider a separately approved final read.

## 11. Limits

- This checklist is a judgement built from committed evidence. Items marked PASS are pass on the evidence seen, not verified by re-running.
- No external reviewer endorsement is implied. The reviewing agents are internal read-only passes.
- The publication path depends on decisions this review does not make.

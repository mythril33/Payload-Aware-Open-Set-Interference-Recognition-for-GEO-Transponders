# B2 E10 — closure of the PR #30 critical and major findings

**Date:** 2026-10-24. **Baseline:** `origin/main` `e43987e`, which contains PR #30 (`a4dbe4d`, scientific audit),
PR #31 (`3927df2`, CI integration) and PR #32 (`e43987e`, E9 guarded-executor contract).
**Branch:** `fix/b2-e10-scientific-integrity-hardening`.
**Companions:** [researcher decision packet](../plan/B2_E10_RESEARCHER_DECISION_PACKET.md),
[verification report](../results/B2_E10_VERIFICATION_REPORT.md), [R10 change note](../engineering/B2_E10_R10_CLEAN_ALARM_CHANGE.md).

**Gates:** unchanged. Full generation, GPU probe, full GPU training and full LOKO remain `NOT_AUTHORIZED`;
`benchmark_complete=false`; production launch disabled. No held-out observation was opened and no dataset was generated.

## 1. Verified baseline

| Item | Verified value |
|---|---|
| `origin/main` at start | `e43987ea8b6a50d0df9b6969e69e80d36d03f182` |
| PR #30 merge | `a4dbe4d` (adds three documents under `docs/research/`, 836 insertions, no code) |
| PR #31 merge | `3927df2` (recovery document, `docs/plan/DURUM.md`, one test edit) |
| PR #32 merge | `e43987e` (`src/geoml/b2_e9_contract.py` 958 lines, `tests/test_b2_e9_contract.py` 748 lines, `P34` 63 lines) |
| Quantile in main before this PR | `src/geoml/metrics.py:38` linear NumPy default (confirmed) |
| TF32 flags in main before this PR | none in `src/`, `scripts/`, `configs/` (repository grep) |

## 2. Evidence matrix (Critical and Major items, plus the decision and reporting items)

Classifications are the lead auditor's, checked against the frozen snapshot of `e43987e`. The independent workflow
verdicts are recorded in section 2.1. Status columns: **before** = `e43987e`; **after** = this branch.

| ID | Finding | Classification | Before | After | Action in this PR |
|---|---|---|---|---|---|
| C-1 | Prior held-out exposure of test and test-matched roles | **Confirmed defect** (barrier not kept; decision needed) | OPEN | OPEN, decision D-1 | Exposure ledger (section 3.1), disclosure statement, three-option packet |
| C-2 | K17d 35/465/500 subset not reproducible | **Reproducibility gap** (now reproduced from frozen generator metadata) | OPEN | ENGINEERING CLOSED; scientific acceptance pending | Metadata-only validator, derivation script, committed identity record, audit cross-check |
| M-1 | Clean-alarm quantile is linear, not the approved higher quantile | **Confirmed defect** | OPEN | **CLOSED** on the E9 path; historical stages kept as HISTORICAL | `clean_alarm_threshold` (method `higher`), `ALARM_RULE` relabelled, regression tests, change note |
| M-2 | TF32 policy not enforced anywhere | **Researcher-approved design; enforcement deferred** to a reviewed executor (approval line 31; P33 §3). Not a defect in this PR. | DEFERRED | DEFERRED, guarded | No runtime code added; the repository tripwires `tests/test_b2_e8_tools.py:237` and `tests/test_b2_training_footprint.py:553` stay in force and pass; `APPROVED_CONFIG` declares both flags off (PR #32) |
| M-3 | Observation-based cancellation assumes exact plan parameters | **Researcher assumption** (partly covered by P28 A5) | OPEN | OPEN, decision D-5 | Records what A5 covers and what it does not (rate, roll-off, magnitude) |
| M-4 | Dual-pol operator-receiver contract undocumented | **Researcher assumption** (P14:24 documents a dual monitor, not as a contract) | OPEN | OPEN, decision D-2 | Availability table drafted for decision |
| M-5 | Two canceller implementations, no stage mapping | **Reporting limitation** | OPEN | DOCUMENTED (section 5) | Stage-to-canceller mapping verified against imports and identifiers |
| M-6 | Cross-seed SD computed in code but reported nowhere; atlas says "no uncertainty" | **Reporting limitation** | OPEN | OPEN (errata, section 6) | Statement corrected in this document; no CI from 3 seeds |
| M-7 | Scenario bootstrap is conditional on the frozen bundle | **Reporting limitation** | OPEN | DOCUMENTED; labelling rule in D-4 | Required label stated |
| M-8 | "Level-matched" verified for injected power only, on 2 groups | **Reporting limitation** | OPEN | OPEN (errata, section 6) | Wording corrected here; observed-PSD diagnostic not computed |
| M-9 | Meaning of `plan_consistency` under the K17b shift | **Researcher assumption** | OPEN | OPEN, decision D-3 | Evidence that the target is the activity state (`b2_scenarios.py:195`) |
| M-10 | Legacy coupled path reads test before freeze | **Confirmed defect** (reachable route; not the E9 chain) | OPEN | OPEN (follow-up) | Documented; not changed, because the legacy pilot path must keep its behaviour |
| M-11 | Resource arithmetic: "7.0 h ≈ 1.9× the reservation" and an unsourced "10–22 h" | **Reporting limitation** (confirmed arithmetic error) | OPEN | P33 corrected; approved JSON wording recorded as errata | `docs/plan/P33_b2_e9_production_executor_readiness.md` line 17 corrected; approved JSON not edited |
| M-12 | Amplifier (Saleh) coefficients unvalidated; Ka-band label on a Ku system | **Researcher assumption** (physics validation) | OPEN | OPEN, proposal V-9 | Not changed |
| M-13 | ASI downlink geometry reuses uplink 14.25 GHz ranges | **Reporting limitation** | OPEN | OPEN (documented) | Not changed |
| M-14 | 35 co-feed groups carry a level shift inside the 500 headline | **Reporting limitation**; the approval already requires both rows (A+C) | OPEN | PARTIAL (rule in approval; table not yet produced) | Identity record carries both sets; drift table is a reporting task |
| REP-1 | FPR@95TPR must not be confused with the R10 known acceptance 0.95 | **Already resolved in main** (separate code paths) | — | RESOLVED, verified | Section 4 |
| REP-2 | Analytical, Monte Carlo and measured cancellation depth must be distinguished | **Reporting limitation** | OPEN | DOCUMENTED (section 6) | Labels stated |
| Mo-3 | Calibration samples are clustered (8 variants per group) | **Reporting limitation** | OPEN | OPEN | Noted in D-4 |
| Mo-4 | Threshold uncertainty not reported | **Reporting limitation** | OPEN | OPEN | Bootstrap of val-calib thresholds is proposal V-7 |
| Mo-5 | No primary endpoint or multiplicity plan | **Researcher assumption** | OPEN | OPEN, decision D-4 | Options and the advisory recommendation |
| Mo-6 | Carrier-under-carrier victim conditioning not quantified | **Reporting limitation** | OPEN | OPEN | Not changed |

### 2.1 Independent workflow verdicts

An evidence-matrix workflow (`b2-e10-evidence-matrix-v2`, run `wf_40562391-242`) classified the items above against a
frozen `git archive` snapshot of `e43987e`, with a separate adversarial agent for each Critical and Major item. Its
results are recorded in the verification report, section 4. Where a verdict differed from the lead classification, the
difference is stated there and the classification in this table was re-checked by the lead before any change was made.

## 3. Critical findings in detail

### 3.1 C-1 — prior held-out exposure

**Exposed scenes, verified by a scan of every committed `docs/results/*.json`:** test-role groups 3200000 and 3200001,
and test-matched groups 3300000 and 3300001. These carry outcome-level content (predictions, accuracy, alarm rates,
FPR@95TPR, counterfactual changes). A scan also found 78 test groups with drop metadata only (`k17d_drift_audit.json`,
committed in `ba98d6b`); the same four groups also appear in physics-only checks. The exposed outcome groups are not in the 78-group drop
set. The full ledger, with commit dates, is in the decision packet, section D-1.1.

**Influence.** No decision-stage document quotes a test-role outcome. `docs/plan/B2_E8_DECISION_APPROVAL.md:11` disclaims influence of val-calib outcomes only. `docs/plan/B2_E6_RESEARCHER_DECISION_PACKET.md:44–46` used three-epoch training behaviour, not test metrics, to argue against tuning the center weight. The earliest test-role outcome (B2-feat pilot, groups 3200000 and 3200001) was committed in `46b13fc` on 2026-10-20, in the same commit that introduces the center-loss value `0.005`. The record cannot show which came first inside that commit. The K17b plan-shift augmentation was implemented in `a09429b`, in the same commit as a later test-role outcome. These are process overlaps that must be disclosed.

**Status:** the exposure is a confirmed fact. Its effect on decisions cannot be excluded by the record. The choice among
Options A, B and C is a researcher decision (packet D-1). This PR records the mandatory disclosure statement and changes no
protocol.

### 3.2 C-2 — K17d subset reproducibility

**What was missing before:** the committed audit (`docs/results/k17d_drift_audit.json`) had no generator, predicate or
hash, and nothing in `src/` or `scripts/` derived the 35/465 identity lists.

**What this PR adds:**

- `src/geosim/b2_k17d.py`: a pure validator and derivation. It accepts only metadata records with exactly the fields
  `scenario_id, role, protocol, plan_consistency, dropped_carrier, missing_carrier_override`. Any other key, including a
  prediction, score or accuracy, is refused. It fails closed on: a count other than 500, duplicates, an ID outside the frozen
  test range, a non-test role, a non-`B2-base/1` protocol, any diagnostic override, a malformed or out-of-range drop, a
  `plan_consistency` that disagrees with the drop, a co-feed count other than 35, a sensitivity count other than 465, and a
  partition that is not exact. It produces canonical sorted IDs and SHA-256 fingerprints.
- `derive_from_generator` resolves the 500 test scenes through `prepare_scene`, which draws plans, link and carrier
  activity from the group seeds. A test patches `simulate_dual` to fail, and the run records zero waveform calls.
- `scripts/b2_e10_k17d_identity.py` derives the identities, cross-checks them against the committed audit, and writes
  `docs/results/b2_e10_k17d_identity.json` only when the cross-check agrees exactly. Otherwise it exits non-zero and writes
  nothing.

**Result of the run:** headline 500, co-feed missing 35, sensitivity 465, cross-feed missing 43, total missing 78. The
derived co-feed, cross-feed and sensitivity IDs equal the committed audit exactly (78 of 78 group IDs and polarizations
agree). The record carries `observation_reads: 0`, `waveform_synthesis_calls: 0`, and the source hashes of the three
modules.

**What remains:** no committed *production* generation metadata exists, because production generation is not authorized.
The identity list is therefore a candidate derived from the frozen generator at these source hashes. The status is
`PENDING_RESEARCHER_ACCEPTANCE`. Acceptance is a researcher decision, and any change to the three source modules requires
regenerating the record.

## 4. Major findings in detail

### 4.1 M-1 — clean-alarm quantile (closed on the E9 path)

- Call chain verified: `metrics.threshold_at_pfa` (linear) was used by the E9 calibrate path
  (`src/geoml/b2_execution.py:307` before this PR) and by frozen stages A, R1, A5, observed-dev and dual-dev, and the legacy
  pilot. The rejection quantile already used `method="higher"` (`src/geoml/calibration.py:131`).
- Change: `clean_alarm_threshold` (method `higher`) is now used by the E9 path. `threshold_at_pfa` is unchanged in value and
  labelled HISTORICAL, so archived results keep their meaning. `ALARM_RULE` changes, so historical alarm files fail
  verification. Details and the call-site list are in the [R10 change note](../engineering/B2_E10_R10_CLEAN_ALARM_CHANGE.md).
- Thresholds were not tuned on any result. The method was set by the approved record.

### 4.2 M-2 — TF32 (deferred by the approval, not closed)

The approved record says the R6 numeric change is "to be enforced only in a later reviewed executor"
(`docs/plan/B2_E9_SCIENTIFIC_DECISION_APPROVAL_2026-10-24.md`, R6). P33 §3 places the implementation before the source lock.
The repository already encodes this sequence as tripwires: `tests/test_b2_e8_tools.py:237` fails if any source file pins TF32
or deterministic algorithms, and `tests/test_b2_training_footprint.py:553` fails if any source uses autocast or TF32 tokens.

This PR first added a helper that sets and asserts the flags. The tripwires rightly failed on it, and it was removed, because
adding enforcement now would move a step the approval reserves for the reviewed executor. The M-2 finding therefore stands as
**deferred**, not closed. The control that prevents unenforced execution is that no executor exists: `guard_execution` still
refuses every action and `runtime_permitted()` is false.

### 4.3 REP-1 — FPR@95TPR versus the R10 known-acceptance quantile (resolved in main)

- `src/geoml/openset_metrics.py:112` computes FPR at a TPR level of 0.95 on the **unknown-positive** ranking. Its FPR
  denominator is known events (`openset_metrics.py:51`).
- `src/geoml/calibration.py:131` computes a quantile at level 0.95 on **known val-calib** scores, to set the acceptance threshold.
- The two use different populations and answer different questions. The literal `0.95` appears in both, which is a naming hazard
  only (audit Mi-1). Every table must print the concept, not the number.

## 5. Stage-to-canceller mapping (M-5)

Verified against imports and identifiers in `e43987e`:

| Stage | Canceller module | Algorithm identifier | Source |
|---|---|---|---|
| B2-base/1, B2-feat/1 (primary) | `geosim.cancellation` | `obs-cancel/1` | `src/geosim/cancellation.py:36`; `b2_dataset.py:31` |
| B2-test/1 | `geosim.cancellation` | `obs-cancel/1` | `src/geosim/b2_test_dataset.py:31` |
| B2-match/1 | `geosim.cancellation` | `obs-cancel/1` | `src/geosim/b2_matched_dataset.py:37` |
| B2-features/1 (separate development stage, P21b) | `geosim.observed_receiver` | `observed-dd-rrc-fir/1` | `src/geosim/observed_receiver.py:27`; `b2_features.py:33, 41` |

The approval retains `obs-cancel/1` as the primary receiver (`docs/plan/B2_E9_SCIENTIFIC_DECISION_APPROVAL_2026-10-24.md`).
The observed receiver is a development variant.

## 6. Reporting corrections and errata (no approved definition changed)

Each item below was checked against the code or the committed file. The approved record itself is not edited.

| Item | Incorrect or ambiguous statement | Correct statement | Where |
|---|---|---|---|
| E-1 | "7.0 h for nine fits is roughly 1.9× the 6 GPU-h reservation" | 7.0 / 6 = **1.17×** for the point estimate. The 1.9× figure is the upper bound 11.5 h / 6 from the E7 proposal. | `docs/plan/b2_e9_approved_scientific_protocol.json:430` (approved record, not edited); `docs/plan/B2_E7_TRAINING_SPEC_PROPOSAL.md:176`; `docs/plan/B2_E6_PRODUCTION_READINESS_CHECKLIST.md:57`; `docs/plan/b2_e6_audit_findings.json:355` |
| E-2 | "An unmeasured 10–22 h width-16 nine-fit estimate" | No committed source; withdrawn | `docs/plan/P33_b2_e9_production_executor_readiness.md` line 17 **corrected in this PR** |
| E-3 | "No uncertainty is drawn" | Committed outputs report no training-seed uncertainty. The code computes a cross-seed SD (`src/geoml/b2_loko_matrix.py:372–373`) that no committed output uses. The scenario bootstrap is conditional on the frozen bundle. | `docs/results/B2_SCIENTIFIC_RESULTS_ATLAS.md:162` |
| E-4 | "The P20 cancellation caps depth at ≈ 21–25 dB" | **Analytical** 21.74 dB (Wiener phase, 150 Hz, 4096-sample block; `scripts/b2_e6_decision_evidence.py:65–67`). **Seeded Monte Carlo** 22.82 dB (stored inner window; same script, lines 78–84). The 25 dB upper bound is not derived. Pilot depths are single realizations. | `docs/plan/P20_b2_cancellation_residual.md:122–124` |
| E-5 | "Level-matched" ASI and unauthorized | **Injected-power matched** by construction (requested power equal to 1e-12; oracle injected-power error +0.04 dB and +0.17 dB). **Observed in-band PSD is not matched**: on group 3300001 the ASI in-band ΔPSD is 3.50 dB and the unauthorized is 10.07 dB. The 2-group check is not a 150-group result. | `docs/results/b2_matched_check.json` (lines 25–29); `docs/plan/P22_b2_matched_asi.md` |

## 7. Open items after this PR

**Critical:** C-1 (decision D-1). C-2 scientific acceptance of the identity record (researcher).

**Major:** M-2 (deferred by the approval to the reviewed executor milestone; the tripwires stay in force). M-3 (decision D-5). M-4 (decision D-2). M-9 (decision D-3).
M-10 (legacy path, engineering follow-up). M-12 (physics validation). Mo-5 (decision D-4).

**Not done here, by design:** no test protocol is chosen (D-1); no generation, probe, training, held-out evaluation or LOKO is
run; the 150-group observed-PSD matched diagnostic (M-8) is a pre-evaluation metadata-and-spectra computation that needs a
decision on its roles before it is run.

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
| TF32 flags in main before this PR | no runtime setter in `src/`, `scripts/`, `configs/`. The approved record and the PR #32 contract declare both TF32 flags **false** as values (`docs/plan/b2_e9_approved_scientific_protocol.json:81–82`; `src/geoml/b2_e9_contract.py:66–67`). Nothing enforces them at run time. |

## 2. Evidence matrix (Critical and Major items, plus the decision and reporting items)

Classifications are the lead auditor's, checked against the frozen snapshot of `e43987e`. The independent workflow
verdicts are recorded in section 2.1. Status columns: **before** = `e43987e`; **after** = this branch.

| ID | Finding | Classification | Before | After | Action in this PR |
|---|---|---|---|---|---|
| C-1 | Prior held-out exposure of test and test-matched roles | **Confirmed defect** (barrier not kept; exposure wider than first stated; decision needed) | OPEN | OPEN, decision D-1 | Exposure ledger in D-1.1 (at least seven pipelines and observation-level content, not only outcomes), disclosure statement, three-option packet |
| C-2 | K17d 35/465/500 subset not reproducible | **Reproducibility gap** (now reproduced from frozen generator metadata) | OPEN | ENGINEERING CLOSED; scientific acceptance pending (packet D-8: the approval asks for committed production metadata) | Metadata-only validator, derivation script, committed identity record, audit cross-check |
| M-1 | Clean-alarm quantile is linear, not the approved higher quantile | **Confirmed defect** | OPEN | **CLOSED** on the E9 path; historical stages kept as HISTORICAL | `clean_alarm_threshold` (method `higher`), `ALARM_RULE` relabelled, regression tests, change note |
| M-2 | TF32 policy not enforced anywhere | **Reproducibility gap** (no runtime enforcement); **deferred by the approval** to a reviewed executor (approval line 31; P33, "Required E9 future implementation interfaces", item 3). Verifier downgraded the earlier 'confirmed defect' label. | DEFERRED | DEFERRED, guarded | No runtime code added; tripwires `tests/test_b2_e8_tools.py:237` and `tests/test_b2_training_footprint.py:553` stay in force; `APPROVED_CONFIG` declares both flags off (PR #32) |
| M-3 | Observation-based cancellation assumes exact plan parameters | **Researcher assumption** (partly covered by P28 A5) | OPEN | OPEN, decision D-5 | Records what A5 covers and what it does not (rate, roll-off, magnitude) |
| M-4 | Dual-pol operator-receiver contract undocumented | **Researcher assumption** (P14:24 documents a dual monitor, not as a contract) | OPEN | OPEN, decision D-2 | Availability table drafted for decision |
| M-5 | Two canceller implementations, no stage mapping | **Reporting limitation**; verified in main as no single table | OPEN | RESOLVED here (documented mapping, section 5) | Stage-to-canceller mapping verified against imports and identifiers |
| M-6 | Cross-seed SD computed in code but reported nowhere; atlas says "No uncertainty is drawn" | **Reporting limitation** | OPEN | OPEN (errata, section 6) | Statement corrected in this document; no CI from 3 seeds |
| M-7 | Scenario bootstrap is conditional on the frozen bundle | **Reporting limitation** (partly labelled in main; `cluster_ci` itself takes no model input) | OPEN | PARTIAL; labelling rule in D-4 | Required label stated |
| M-8 | "Level-matched" verified for injected power only, on 2 groups | **Reporting limitation** | OPEN | OPEN (errata, section 6) | Wording corrected here; observed-PSD diagnostic not computed |
| M-9 | Meaning of `plan_consistency` under the K17b shift | **Researcher assumption** | OPEN | OPEN, decision D-3 | Evidence that the target is the activity state (`b2_scenarios.py:195`) |
| M-10 | Legacy coupled path reads test before freeze | **Confirmed defect** (verified; the docstring at `src/geoml/b2_experiment.py:9` says test is evaluated once, while the code loads test at :480 and infers it per view at :501; reachable by default, because `--mode` defaults to `legacy` (`b2_experiment.py:788–789`), not the E9 chain) | OPEN | OPEN (follow-up, errata E-9; decision D-7) | Documented; not changed, because the legacy pilot path keeps its behaviour until D-7 is decided |
| M-11 | Resource arithmetic: "7.0 h for nine (roughly 1.9x the whole 6 GPU-h reservation)" (`docs/plan/B2_E6_PRODUCTION_READINESS_CHECKLIST.md:57`; arithmetic error, still in main). The '10–22 h' range is **sourced** (`B2_E8_HOST_RESOURCE_ASSESSMENT.md:23`), so the finder's 'unsourced' label was wrong. | **Reporting limitation** | OPEN in main | OPEN; errata E-1 and E-2 | Approved JSON not edited. P33 is restored to its approved text (the `4efb7f0` withdrawal was itself wrong) |
| M-12 | Amplifier (Saleh) coefficients unvalidated; Ka-band label on a Ku system | **Researcher assumption** (physics validation) | OPEN | OPEN, proposal V-9 | Not changed |
| M-13 | ASI downlink geometry reuses uplink 14.25 GHz ranges | **Reporting limitation** | OPEN | OPEN (documented) | Not changed |
| M-14 | 35 co-feed groups carry a level shift inside the 500 headline | **Reporting limitation**; the approval already requires both rows (A+C) | PARTIAL | PARTIAL (rule in approval; drift table not yet produced) | Identity record carries both sets; drift table is a reporting task |
| REP-1 | FPR@95TPR must not be confused with the R10 known acceptance 0.95 | **Already resolved in main** (separate code paths) | — | RESOLVED, verified | Section 4 |
| REP-2 | Analytical, Monte Carlo and measured cancellation depth must be distinguished | **Reporting limitation**; the three values reproduced bit-for-bit (analytic 21.7379 dB; full-block Monte Carlo 21.7577 dB; stored-window Monte Carlo 22.8204 dB); the 25 dB figure in P20 is not derived | PARTIAL | DOCUMENTED (section 6, errata E-4) | Labels stated |
| Mo-3 | Calibration samples are clustered (8 variants per group) | **Reporting limitation** (verified: rejection uses 8G rows, clean alarm uses G, each as a flat quantile with no group unit) | OPEN | OPEN | Noted in D-4 |
| Mo-4 | Threshold uncertainty not reported | **Researcher assumption** (no interval computed anywhere; EDSC, XGB and neural thresholds are point estimates) | OPEN | OPEN | Bootstrap of val-calib thresholds is proposal V-7 |
| Mo-5 | No primary endpoint or multiplicity plan | **Researcher assumption**; partly stated in P18 section 7 (combined number from near families only), but no endpoint or correction is designated | OPEN | OPEN, decision D-4 | Options and the advisory recommendation |
| Mo-6 | Carrier-under-carrier victim conditioning not quantified | **Reproducibility gap**: the redraw count is written to event metadata (`inactive_victim_rejected_draws`) but no rate is computed or reported | OPEN | OPEN | Not changed; proposal to report the per-group rate |

### 2.1 Independent workflow verdicts

An evidence-matrix workflow (`b2-e10-evidence-matrix-v2`, run `wf_40562391-242`) classified the items above against a
frozen `git archive` snapshot of `e43987e`, with a separate adversarial agent for each Critical and Major item. Its
per-item verdicts are recorded only in the table below; the workflow output is not committed to the repository. Where a verdict differed from the lead classification, the
difference is stated in that table, and the classification in section 2 was re-checked by the lead before any change was made.

Workflow `wf_40562391-242`: 22 finder classifications, and 16 adversarial re-checks for every Critical and Major item and for M-series items. Reporting items marked 'not re-checked' were classified by the finder only.

The labels in this table are the finder's and verifier's own taxonomy on the `e43987e` snapshot. They are not the same scale as the 'Before' column in section 2, and they differ from it for M-2, M-3, M-5, M-7, M-9, M-11, M-13 and Mo-5. Section 2 governs.

| ID | Finder classification / status on e43987e | Adversarial verifier |
|---|---|---|
| C-1 | CONFIRMED_DEFECT / OPEN | agreed |
| C-2 | REPRODUCIBILITY_GAP / OPEN | agreed |
| M-1 | CONFIRMED_DEFECT / OPEN | agreed |
| M-2 | CONFIRMED_DEFECT / OPEN | revised to REPRODUCIBILITY_GAP / OPEN |
| M-3 | RESEARCHER_ASSUMPTION / PARTIALLY_RESOLVED | agreed |
| M-4 | RESEARCHER_ASSUMPTION / OPEN | agreed |
| M-5 | REPORTING_LIMITATION / PARTIALLY_RESOLVED | agreed |
| M-6 | REPORTING_LIMITATION / OPEN | agreed |
| M-7 | REPORTING_LIMITATION / PARTIALLY_RESOLVED | agreed |
| M-8 | REPORTING_LIMITATION / OPEN | agreed |
| M-9 | RESEARCHER_ASSUMPTION / PARTIALLY_RESOLVED | agreed |
| M-10 | CONFIRMED_DEFECT / OPEN | agreed |
| M-11 | REPORTING_LIMITATION / PARTIALLY_RESOLVED | revised to REPORTING_LIMITATION / OPEN |
| M-12 | REPRODUCIBILITY_GAP / OPEN | agreed |
| M-13 | RESEARCHER_ASSUMPTION / PARTIALLY_RESOLVED | agreed |
| M-14 | REPRODUCIBILITY_GAP / PARTIALLY_RESOLVED | revised to REPORTING_LIMITATION / PARTIALLY_RESOLVED |
| Mo-3 | REPORTING_LIMITATION / OPEN | not re-checked (reporting item; Critical and Major items were re-checked) |
| Mo-4 | RESEARCHER_ASSUMPTION / OPEN | not re-checked (reporting item; Critical and Major items were re-checked) |
| Mo-5 | RESEARCHER_ASSUMPTION / PARTIALLY_RESOLVED | not re-checked (reporting item; Critical and Major items were re-checked) |
| Mo-6 | REPRODUCIBILITY_GAP / OPEN | not re-checked (reporting item; Critical and Major items were re-checked) |
| REP-1 | RESOLVED_IN_MAIN / RESOLVED | not re-checked (reporting item; Critical and Major items were re-checked) |
| REP-2 | REPORTING_LIMITATION / PARTIALLY_RESOLVED | not re-checked (reporting item; Critical and Major items were re-checked) |

## 3. Critical findings in detail

### 3.1 C-1 — prior held-out exposure

**Scope, corrected by the verification workflow.** At least seven pipelines read or reported held-out groups, and the exposure is not only outcome-level:

- B2-feat/1 pilot (`46b13fc`, `b2_feat_pilot.json`): test accuracy 2/16 = 0.125 per view, macro-F1, ECE, rejection and clean false alarm; its open-set block is null (`n_unknown = 0`). Full pilot (`ba98d6b`, `b2_full_pilot.json`): the same metrics, plus test-only and matched metrics.
- B2-test/1 and B2-match/1 pilots (`a09429b`, `ba98d6b`).
- P21b observed-development stage (`24feaa6`): **per-observation** predictions, probabilities and event alarms for group 3200000.
- E3a EDSC baseline (`ec47a90`, evidence date 2026-10-22): test sample counts and metric blocks.
- E3b XGBoost baseline (`d88c689`): known-test accuracy 6/16; the status file publishes it (`docs/plan/DURUM.md:82`).
- E4 A5 pilots (`3c0068e`, `5e824fe`): alarms, logits and counterfactual outcomes on known and matched scenes; 870 scored samples across 25 invocations.
- Atlas figures (`7108ee8`): spectrogram arrays of held-out group 3200000 (clean and carrier-under-carrier) in `docs/results/b2_physical_figure_data.json`. This is **observation-level** content. The atlas rule was "clean and CuC, before examining outputs" (`docs/results/B2_SCIENTIFIC_RESULTS_ATLAS.md:36–37`), but the arrays were opened.
- Markdown summaries that carry the same test-role numbers, checked separately: `docs/results/b2_feat_pilot.md` (`46b13fc`; 12.5 % accuracy per view, IDs 3200000 and 3200001), `docs/results/B2_SCIENTIFIC_RESULTS_ATLAS.md` (`7108ee8`; "have12.5%known-test accuracy" and "bounded XGBoost has6/16correct", line 152) and `docs/results/b2_a5_dual_pol_pilot.md` (`3c0068e`; IDs 3200000, 3200001, 3300000, 3300001).

Two governance texts do not record these reads. The approval (`docs/plan/B2_E9_SCIENTIFIC_DECISION_APPROVAL_2026-10-24.md:39`) requires a freeze before the first held-out read. The approved JSON (`test_evaluation_coupling`) and the contract (`src/geoml/b2_e9_contract.py:264–265`) repeat the barrier without any field for prior reads. `docs/plan/P32_b2_e8_freeze_preparation.md:23` says that no test, test-only, matched or val-calib outcome was read; that is accurate for P32's own work only, and the errata below scope it.

**Exposed scenes, verified by a scan of every committed `docs/results/*.json`:** test-role groups 3200000 and 3200001,
and test-matched groups 3300000 and 3300001. These carry outcome-level content (predictions, accuracy, alarm rates,
FPR@95TPR, counterfactual changes). A scan also found 78 test groups with drop metadata only (`k17d_drift_audit.json`,
committed in `ba98d6b`); the same four groups also appear in physics-only checks. The exposed outcome groups are not in the 78-group drop
set. The full ledger, with commit dates, is in the decision packet, section D-1.1.

**Influence.** The E8 approval states, verbatim: "No test, test-only, matched or val-calib outcome informed any recommendation; they follow P18/P20/P6, the pilots' pre-registered configs and committed analytic evidence only" (`docs/plan/B2_E8_DECISION_APPROVAL.md:10–11`). That statement covers the E8 recommendations. It does not address the earlier committed reads listed above, and no document checked here records whether those reads preceded the design choices they bear on. `docs/plan/B2_E6_RESEARCHER_DECISION_PACKET.md:44–46` used three-epoch training behaviour, not test metrics, to argue against tuning the center weight. The earliest test-role outcome (B2-feat pilot, groups 3200000 and 3200001) was committed in `46b13fc` on 2026-10-20, in the same commit that introduces the center-loss value `0.005`. The record cannot show which came first inside that commit. The K17b plan-shift augmentation was implemented in `a09429b`, in the same commit as a later test-role outcome. These are process overlaps that must be disclosed.

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
  `plan_consistency` that disagrees with the drop, a co-feed count other than 35, a sensitivity count other than 465. The sensitivity set is the complement of the co-feed set inside the headline, so the
  partition is exact by construction. Accepted records are normalised to plain integers. Audit rows that are not mappings and
  audit header counts that disagree are refused. It produces canonical sorted IDs and SHA-256 fingerprints over the full
  normalised records.
- `derive_from_generator` resolves the 500 test scenes through `prepare_scene`, which draws plans, link and carrier
  activity from the group seeds. A test patches `simulate_dual` to fail, and the run records zero waveform calls.
- `scripts/b2_e10_k17d_identity.py` derives the identities, cross-checks them against the committed audit, and writes
  `docs/results/b2_e10_k17d_identity.json` only when the cross-check agrees exactly. Otherwise it exits non-zero and writes
  nothing.

**Result of the run:** headline 500, co-feed missing 35, sensitivity 465, cross-feed missing 43, total missing 78. The
derived co-feed and cross-feed IDs equal the committed audit exactly (78 of 78 group IDs and polarizations agree). The
465 sensitivity IDs are the complement of the co-feed set inside the headline and have no counterpart in the audit. The record carries `observation_reads: 0`, `waveform_synthesis_calls: 0`, the SHA-256 of all 28 `src/geosim` modules (`package_sha256`), the audit file SHA-256, and the
hashes of the three key modules.

**What remains:** no committed *production* generation metadata exists, because production generation is not authorized.
The identity list is therefore a candidate derived from the frozen generator at these source hashes. The status field ends in
`PENDING_RESEARCHER_ACCEPTANCE` (full value `DERIVED_FROM_FROZEN_GENERATOR_METADATA_CROSS_CHECKED_PENDING_RESEARCHER_ACCEPTANCE`). Acceptance is a researcher decision, and any change under `src/geosim` requires
regenerating the record. The records test fails until it is regenerated.

## 4. Major findings in detail

### 4.1 M-1 — clean-alarm quantile (closed on the E9 path)

- Call chain verified: `metrics.threshold_at_pfa` (linear) was used by the E9 calibrate path
  (`src/geoml/b2_execution.py:307` before this PR) and by frozen stages A, R1, A5, observed-dev and dual-dev, and the legacy
  pilot. The rejection quantile already used `method="higher"` (`src/geoml/calibration.py:131`).
- Change: `clean_alarm_threshold` (method `higher`) is now used by the E9 path. `threshold_at_pfa` is unchanged in value and
  labelled HISTORICAL, so archived results keep their meaning. `ALARM_RULE` changes, so historical alarm files fail
  verification. Details and the call-site list are in the [R10 change note](../engineering/B2_E10_R10_CLEAN_ALARM_CHANGE.md).
- Thresholds were not tuned on any result. The method was set by the approved record.
- **Score saturation (N-1, found in review, fixed in `9f99f3e` on `main`; its tree is identical to the pre-merge branch commit `68b13bb`).** The alarm score was `1 - P(clean)` by subtraction. Once the
  clean margin exceeds about 37 nats, the subtraction rounds to exactly 0 in float64. The ordering of confidently clean samples
  is then lost, and the clean quantile can be 0. `clean_alarm_score` sums the non-clean probabilities instead. The value is
  mathematically identical. Both the calibrate and evaluate paths use it. Regression test:
  `tests/test_b2_e10_calibration.py::test_saturated_clean_margin_keeps_a_positive_score_and_its_ordering`.

### 4.2 M-2 — TF32 (deferred by the approval, not closed)

The approved record says the R6 numeric change is "to be enforced only in a later reviewed executor"
(`docs/plan/B2_E9_SCIENTIFIC_DECISION_APPROVAL_2026-10-24.md`, R6). P33, "Required E9 future implementation interfaces", item 3 (line 15), places the implementation before the source lock.
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
| E-1 | "7.0 h for nine fits, roughly 1.9x the reservation" | 7.0 / 6 = **1.17×** for the point estimate. The 1.9× figure is the upper bound 11.5 h / 6 from the E7 proposal. | `docs/plan/b2_e9_approved_scientific_protocol.json:430` (approved record, not edited); `docs/plan/B2_E7_TRAINING_SPEC_PROPOSAL.md:176`; `docs/plan/B2_E6_PRODUCTION_READINESS_CHECKLIST.md:57`; `docs/plan/b2_e6_audit_findings.json:355` |
| E-2 | P33 line 17 as edited in `4efb7f0`: the earlier "10–22 h width-16 nine-fit" figure "had no committed source and is withdrawn" | **Sourced and unmeasured.** `B2_E8_HOST_RESOURCE_ASSESSMENT.md:23` gives 10.0–21.9 h for the main 3 × 3 campaign at width 16 (compute plus synchronous loader). The withdrawal in `4efb7f0` was wrong, and P33 is restored to its approved text. | `docs/plan/B2_E8_HOST_RESOURCE_ASSESSMENT.md:23`; `docs/plan/P33_b2_e9_production_executor_readiness.md:17` (restored; approved wording "An unmeasured 10–22h width16 nine-fit estimate is not a reservation.", also in `docs/research/B2_E9_INDEPENDENT_SCIENTIFIC_AUDIT.md:216`) |
| E-3 | "No uncertainty is drawn" | Committed outputs report no training-seed uncertainty. The code computes a cross-seed SD (`src/geoml/b2_loko_matrix.py:372–373`) that no committed output uses. The scenario bootstrap is conditional on the frozen bundle. | `docs/results/B2_SCIENTIFIC_RESULTS_ATLAS.md:162` |
| E-4 | "The P20 cancellation caps depth at ≈ 21–25 dB" | **Analytical** 21.74 dB (Wiener phase, 150 Hz, 4096-sample block; `scripts/b2_e6_decision_evidence.py:65–67`). **Seeded Monte Carlo** 22.82 dB (stored inner window; same script, lines 78–84). The 25 dB upper bound is not derived. Pilot depths are single realizations. | `docs/plan/P20_b2_cancellation_residual.md:122–124` |
| E-5 | "Level-matched" ASI and unauthorized | **Injected-power matched** by construction (requested power equal to the target within a relative tolerance of 1e-12, `src/geosim/b2_matched_dataset.py:134`, `rtol=1e-12, atol=0`; oracle injected-power error +0.04 dB and +0.17 dB). **Observed in-band PSD is not matched**: on group 3300001 the ASI in-band ΔPSD is 3.50 dB and the unauthorized is 10.07 dB. The 2-group check is not a 150-group result. | `docs/results/b2_matched_check.json` (lines 25–29); `docs/plan/P22_b2_matched_asi.md` |
| E-6 | Audit text attributes the phrase 'test → evaluated once' to P18 section 4 and approval lines 33–39 | The phrase is in `.claude/rules/scientific-invariants.md:17`. P18 section 4 (lines 95–96) has no once-only wording. | `docs/research/B2_E9_INDEPENDENT_SCIENTIFIC_AUDIT.md:61` (merged PR #30; not edited, corrected here) |
| E-7 | EDSC baseline dated 2026-10-22 | Evidence date 2026-10-22; committed in `ec47a90` on 2026-10-23 | `docs/results/b2_edsc_baseline.json` |
| E-8 | P32 rule 2: 'no test, test-only, matched or val-calib outcome was read' | Accurate for P32's own preparation work. Not a statement about the program: the pilots and bounded baselines in section 3.1 read test-role outcomes. | `docs/plan/P32_b2_e8_freeze_preparation.md:23` |
| E-9 | `b2_experiment` docstring: '``test`` is evaluated once' | The legacy code infers test once per view (three times per run) and on every reuse. The docstring is wrong and should be corrected in the legacy path. | `src/geoml/b2_experiment.py:9`, `:480`, `:501` |
| E-10 | Frozen stages described as if they used the approved rule | Frozen A5 (`src/geoml/b2_a5.py:220`) uses `threshold_at_pfa` (linear) on the subtraction score. Observed-dev and dual-dev calibrate paths also use `threshold_at_pfa` (`b2_observed_experiment.py:180`, `dual_experiment.py:172`). E3b (`src/geoml/b2_xgb.py:158`) uses the subtraction score. These archived values are kept. Only the E9 path uses the approved rule and the summed score. | `src/geoml/b2_a5.py:220`; `src/geoml/b2_xgb.py:158` |
| E-11 | E7b CPU evidence described as produced on the approved rule | `docs/results/b2_e7b_execution.json` records `src/geoml/b2_execution.py` SHA-256 `edd4fb81…800265`. This equals the `e43987e` file, which uses the linear helper (verified by `sha256sum`). The evidence is historical. A rerun on `ALARM_RULE` of this branch is needed before any E9 claim relies on it. | `docs/results/b2_e7b_execution.json:18`, `:78` |

## 7. Open items after this PR

**Critical:** C-1 (decision D-1). C-2 scientific acceptance of the identity record (researcher; packet D-8).

**Major:** M-2 (deferred by the approval to the reviewed executor milestone; the tripwires stay in force). M-3 (decision D-5). M-4 (decision D-2). M-9 (decision D-3).
M-10 (legacy path, engineering follow-up; decision D-7 on the default CLI mode). M-12 (physics validation).

**Moderate:** Mo-5 (decision D-4).
New decisions from the review: D-6 (order-statistic convention of the approved "higher empirical quantile"), D-7 (default CLI mode reads test), D-8 (identity source for K17d).
Historical, not changed: frozen A5 and E3b subtraction and linear-rule records (E-10); E7b evidence produced on the linear-rule executor (E-11).

**Not done here, by design:** no test protocol is chosen (D-1); no generation, probe, training, held-out evaluation or LOKO is
run; the 150-group observed-PSD matched diagnostic (M-8) is a pre-evaluation metadata-and-spectra computation that needs a
decision on its roles before it is run.

## 8. Independent review of this change set: dispositions

Three independent reviewers (scientific and statistical; leakage and safety; code) reviewed the E10 change set. A second agent
re-checked each material finding against the cited file. Dispositions:

| Ref | Finding | Disposition |
|---|---|---|
| N-1 | Alarm score `1 - P(clean)` saturates to 0 for clean margins above about 37 nats | **Fixed** in `9f99f3e` (`clean_alarm_score`), regression test in section 4.1 |
| N-2 | Default CLI mode `legacy` reads test (`src/geoml/b2_experiment.py:788–789`) | **Not changed.** Decision D-7 in the packet |
| N-3 | Frozen A5 (`src/geoml/b2_a5.py:220`) uses the linear helper on the subtraction score | **Historical.** Errata E-10; not changed |
| N-4 | E7b CPU evidence was produced by the linear-rule executor (hash verified, E-11) | **Historical.** A rerun on the new rule is needed before any E9 claim relies on it |
| N-5 | The approved wording "higher empirical quantile, inclusive acceptance" admits more than one order-statistic convention | **Decision D-6** in the packet. Implemented: NumPy `method="higher"`, index `ceil((n−1)q)` |
| N-6 | Validator: numpy-typed fields broke canonical JSON; mixed-type keys raised `TypeError`; non-mapping audit rows raised `AttributeError`; audit header counts were unchecked; fingerprints covered two of six fields; the partition check was tautological; the script printed its output path after writing | **Fixed** in `9f99f3e`, with negative tests (K17d 43 test cases, records 11) |
| N-7 | The identity record bound three source modules and no audit hash | **Fixed.** `package_sha256` covers every `src/geosim` module; `audit_sha256` added; the records test recomputes the derivation from the generator with `simulate_dual` patched to fail |
| N-8 | Errors in this PR's own text: "10–22 h has no committed source" (wrong, E-2); the E8 disclaimer "val-calib only" (wrong, §3.1); TF32 baseline "none" (wrong, §1); "1e-12 requested power" (a relative tolerance, E-5); packet citations to `b2_stream.py` and `train.py` | **Corrected** in this document and in the packet. P33 restored to its approved text |

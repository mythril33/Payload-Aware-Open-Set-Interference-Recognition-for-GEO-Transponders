# B2 E10 — researcher decision packet

**Status:** DECISIONS PENDING. Nothing in this packet is approved, implemented or authorized.
**Baseline:** `origin/main` `e43987e` (PR #30 scientific audit, PR #31 CI integration, PR #32 E9 guarded-executor contract).
**Companion:** [E10 critical findings closure](../research/B2_E10_CRITICAL_FINDINGS_CLOSURE.md),
[E10 verification report](../results/B2_E10_VERIFICATION_REPORT.md).
**Compute gates:** unchanged. Full generation, GPU probe, full GPU training and full LOKO remain `NOT_AUTHORIZED`;
`benchmark_complete=false`; production launch disabled. Scientific approvals (R1–R10, K18, K17d, OBS-CANCEL-2) are unchanged.

This packet asks for explicit researcher decisions on questions that are scientific, not engineering. It does not choose
a protocol, change an approved parameter, or start any run. "Recommended" entries are advisory and label what the
recommendation depends on.

## Index

| ID | Question | Finding | Decision type |
|---|---|---|---|
| D-1 | How to handle prior held-out exposure of the test and test-matched roles | C-1 | protocol-level, three options |
| D-2 | Explicit operator-receiver contract for the dual-polarization inputs | M-4 | scientific assumption |
| D-3 | Meaning of the auxiliary plan-consistency target under the K17b plan shift | M-9 | scientific clarification (possible protocol change) |
| D-4 | Primary endpoint, multiplicity and statistical reporting plan | Mo-5 | scientific reporting decision |
| D-5 | Receiver plan-error sensitivity experiment for observation-based cancellation | M-3 | scientific assumption and optional experiment |
| D-6 | Order-statistic convention of the approved "higher empirical quantile" (R10 clean alarm) | N-5 | scientific clarification (dated amendment) |
| D-7 | Whether the default CLI mode (`--mode legacy`) may read the test role | N-2, M-10 | engineering-scientific policy |
| D-8 | Identity source for the K17d 500/35/465 record (generator metadata versus committed production metadata) | C-2 | researcher acceptance; affects the approval text |
| D-9 | Items deliberately not decided | — | — |

## D-1 — C-1: prior held-out test exposure (test and test-matched roles)

**Decision needed:** choose one of three options below, or state a different one. No option has been implemented. Until a
decision is recorded, the test role must be treated as **not pristine**, and every held-out number must carry the exposure
statement in section D-1.4.

### D-1.1 What was exposed (verified from committed artifacts only)

The exposed scene IDs are the union of scene IDs that carry outcome-level content (predictions, probabilities, accuracy,
alarm rates, FPR@95TPR, AUROC/AUPR, counterfactual changes) in committed files:

| Role | Exposed scene IDs | Count |
|---|---|---|
| test | 3200000, 3200001 | 2 of 500 headline groups |
| test-matched | 3300000, 3300001 | 2 of 150 matched groups |

Verified by a scan of every `docs/results/*.json` (test-role IDs 32xxxxx and 33xxxxx, classified by content). The scan
found no other outcome-bearing test or matched scene. A numeric false positive (`3240000` in `b2_e8_resource_budget.json`,
a sample-pass count) was excluded.

Committed artifacts carrying outcome-level content on these IDs:

| Artifact | Git commit (date) | Exposed IDs | Outcome-level content |
|---|---|---|---|
| `docs/results/b2_feat_pilot.json` | 46b13fc (2026-10-20) and later | 3200000, 3200001 | accuracy, FPR@95TPR, ECE, confusion, alarm |
| `docs/results/b2_observed_pilot.json` | 24feaa6 (2026-10-21) | 3200000 | accuracy, macro-F1, clean false alarm, confusion |
| `docs/results/b2_observed_predictions.json` | 24feaa6 (2026-10-21) | 3200000 | **per-observation** predictions, probabilities, event alarm |
| `docs/results/b2_test_pilot.json` | a09429b (2026-10-21) | 3200000, 3200001 | accuracy, FPR@95TPR, alarm, known-closed accuracy |
| `docs/results/b2_full_pilot.json` | ba98d6b (2026-10-21) | 3200000, 3200001, 3300000, 3300001 | accuracy, macro-F1, per-class recall, ECE, alarm, matched-pair alarms |
| `docs/results/b2_matched_pilot.md` | ba98d6b (2026-10-21) | 3300000, 3300001 | matched-pair physics and pilot evaluation summary |
| `docs/results/b2_xgb_baseline.json` | d88c689 (2026-10-23) | 3200000, 3200001 | accuracy, AUPR, class predictions, binary score; the status file publishes known-test 6/16 and clean test alarm 1/2 (`docs/plan/DURUM.md:82`) |
| `docs/results/b2_edsc_baseline.json` | ec47a90 (2026-10-23; evidence date 2026-10-22) | test-role counts and metric blocks | E3a EDSC baseline on the test role |
| `docs/results/b2_physical_figure_data.json` (atlas figures) | 7108ee8 (2026-10-23) | 3200000 | **observation-level**: spectrogram arrays of the held-out group, clean and carrier-under-carrier; the atlas selection rule was 'clean and CuC, before examining outputs' (`docs/results/B2_SCIENTIFIC_RESULTS_ATLAS.md:36`) |
| `docs/results/b2_a5_dual_pol_pilot.json` | 3c0068e (2026-10-23) | 3200000, 3200001, 3300000, 3300001 | alarm, logits, counterfactual agreement |
| `docs/results/b2_a5_postmerge_partial_pilot.json` | 5e824fe (2026-10-23) | 3200000, 3200001, 3300000, 3300001 | change vs original prediction, clean false alarm |
| `docs/results/b2_figure_manifest.json` (figures C1, C3, unknown AUROC/AUPR rows) | 7108ee8 (2026-10-23) | 3200000 | figure values derived from test-scene outcomes |

Metadata or physics-only exposure (no model output), which is weaker but not zero:

| Artifact | Exposed IDs | What it holds |
|---|---|---|
| `docs/results/k17d_drift_audit.json` (committed ba98d6b, 2026-10-21) | 78 test groups | drop identity, polarization, drift in dB |
| `docs/results/b2_feat_cancellation_check.json`, `b2_test_family_check.json` | 3200000, 3200001 | residual and PSD physics of test scenes |
| `docs/results/b2_matched_check.json` | 3300000, 3300001 | injected-power and placement physics |

**Verified scope (verification workflow `wf_40562391-242`).** At least seven pipelines read or reported held-out groups, and at least one of them (the atlas figure data for group 3200000) contains observation-level arrays, not only outcomes. The two governance texts that state the freeze barrier (`approval:39`; `b2_e9_approved_scientific_protocol.json` `test_evaluation_coupling`) do not record any prior read. The statement that no decision cites a test outcome is therefore weaker than it reads: it is a statement about decision documents only.

**What was exposed to a reader:** for the outcome-bearing set, the per-scene predictions and summary metrics of pilot
checkpoints (width 8, three epochs, batch 8, seed 0; per `b2_full_pilot.json` config) and of bounded E3b/E4 baselines.
These models are not the nine frozen production cells. No held-out observation array was opened for this review.
Groups 3200000 and 3200001 are not in the 78-group drop set (`k17d_drift_audit.json`), so the K17d split is unaffected by
the exposure of those two groups.

### D-1.2 Did the exposure influence later decisions? (documentary evidence only)

Timeline (git commit dates, UTC):

- 2026-10-20 22:26 — `46b13fc` introduces `center_loss_weight = 0.005` and `plan_loss_weight = 1.0` in
  `configs/b2_feat.json`. The `TrainConfig` default (`src/geoml/train.py:37`) is `0.0`, with the comment "frozen before training". **In the same commit it commits
  `docs/results/b2_feat_pilot.json`, whose test partition (groups 3200000, 3200001) already reports test accuracy 0.125
  and open-set metrics.** The first committed test-role outcome is therefore contemporaneous with the center-weight value.
  The commit cannot show which came first inside it.
- 2026-10-20 — K17a–d decisions dated in P18 §7a, which states that they were written before results. This is the same day
  as the first test-role outcome; the order within the day is not recorded.
- 2026-10-21 — P18 §10 records that the K18 values were frozen in `configs/b2_feat.json` before B2 training and that no
  search was run.
- 2026-10-21 04:39 onwards — further test-role outcomes (`24feaa6`, `a09429b`, `ba98d6b`). `a09429b` introduces the K17b
  plan-shift augmentation in the same commit as its test-role outcome.
- 2026-10-23 — EDSC (E3a, `ec47a90`), XGBoost (E3b, `d88c689`), A5 (E4, `3c0068e`, `5e824fe`) and the atlas figures (`7108ee8`) commit outcomes or observation-level content of test scenes.
- 2026-10-24 — approval record (R1–R10, K18, K17d, OBS-CANCEL-2) committed in `d3f71d6`.

Findings from reading the decision-stage documents:

1. `docs/plan/B2_E8_DECISION_APPROVAL.md:10–11` states, verbatim: "No test, test-only, matched or val-calib outcome informed any
   recommendation; they follow P18/P20/P6, the pilots' pre-registered configs and committed analytic evidence only." This
   covers the E8 recommendations. It does not address the earlier committed reads in the table above, and it does not say
   whether they preceded the design choices they bear on.
2. `docs/plan/B2_E6_RESEARCHER_DECISION_PACKET.md:44–46` used the behaviour of "degenerate three-epoch pilots" to argue
   that the center weight cannot be calibrated, and recommended keeping `0.005`. The argument relies on training-role
   behaviour, not on test metrics, and it argues against tuning. It is still a documented use of pilot results in a
   decision.
3. `docs/plan/B2_E9_SCIENTIFIC_DECISION_APPROVAL_2026-10-24.md` cites no test-role outcome number. Its rationales are
   engineering and protocol rationales.
4. `docs/results/B2_SCIENTIFIC_RESULTS_ATLAS.md` and `docs/plan/DURUM.md` publish the test-role pilot numbers
   (for example "12.5 % known-test accuracy", "6/16 correct"). Those numbers are visible to every later reader. `docs/plan/P20_b2_cancellation_residual.md:143` also publishes the 12.5 % pilot
   accuracy and the zero-positive plan-consistency observation.

**Assessment:** the committed record shows **no decision that cites a test-role outcome**. The earliest test-role outcome (`46b13fc`, 2026-10-20) is contemporaneous with the K17 and K18 values, and the record cannot establish the order within that commit. That is a real limitation, not a finding of influence. It does **not** prove that no
decision-maker saw those outcomes, because the outcomes were public in the repository and in figures before the approval.
The residual influence risk is small in magnitude (2 + 2 groups, pilot checkpoints) but cannot be excluded by the record.

### D-1.3 Options

**Option A — disclosed exposure, existing role and version preserved.**

- *Scientific defensibility:* moderate. The final test read is still one read of the frozen `B2-test/1` role, but the
  four exposed scenes are not pristine. Any reviewer can see that test-role numbers were published earlier, so
  disclosure is necessary. Defensible only with an explicit contamination statement and a sensitivity analysis that
  excludes the exposed scenes.
- *Compatibility with researcher decisions:* compatible with K17d (the exposed groups are outside the 78-group drop set),
  with R8 (nine cells still frozen before the single read) and with the approval's frozen seeds. Requires an added
  disclosure to the approval record (P18 section 10 log entry).
- *Statistical cost:* small. Two of 500 headline groups and two of 150 matched groups. A sensitivity row excluding them
  (498 / 148) costs one more row per table.
- *Reproducibility:* no change to generation; the exposed IDs are listed in D-1.1.
- *Implementation scope:* documentation only, plus one committed exposure ledger (this packet).
- *New generation authorization:* not required.

**Option B — re-version the held-out evaluation protocol.**

- *Scientific defensibility:* highest. A new test and test-matched role with new seeds and new scene IDs restores a
  pristine held-out read. It also removes any doubt about pilot-driven choices.
- *Compatibility with researcher decisions:* requires a new protocol version (`B2-test/2`, matched `B2-match/2`) and a
  P18 section 10 entry. The approval forbids silent regeneration of `B2-test/2` (approval line 16). An explicit new
  decision is required. K17d would have to be re-declared on the new identities, which means re-deriving the 35/465
  split with the new seeds before any read.
- *Statistical cost:* none on the old data, but the new role must be sized the same (500 + 150 groups). The K17d subrow
  becomes a new prediction with a new realized count, so the "35" figure is no longer pre-declared.
- *Reproducibility:* good. New seeds, new fingerprints, new generator run.
- *Implementation scope (estimate, not executed):*
  - Generation: the pilot cost (about 4 s per observation, `docs/results/b2_test_pilot.md`) applied to 6,500 test
    observations (500 groups x 13 variants) and 450 matched observations (6,950 in total) gives about 7.7 core-hours.
    This is an extrapolation from a two-group pilot, not a measurement at scale.
  - Storage: the pilot measured about 0.4 MiB per test-only observation (`b2_test_pilot.md`); the same scale gives about
    2.8 GB.
  - Engineering: a new frozen role and seed range, metadata-only identity validation (the K17d module in this PR can be
    reused), a new configuration version and tests.
- *New generation authorization:* **required.** Option B needs an explicit DR-04 generation authorization and a separate
  decision on the working disk and host ceilings.

**Option C — prespecified quarantine of exposed groups.**

- *Scientific defensibility:* moderate. Removing four exposed scenes is simple, but it is a protocol change: the approval
  forbids outcome-driven removal, and the removal must be fixed now, before the final read.
- *Compatibility with researcher decisions:* conflicts with the approval's rule "do not remove groups on the basis of
  outcomes". It is compatible only if the removal rule is defined by exposure (a metadata fact), not by outcome.
  The approval would need a new version or a dated amendment.
- *Statistical cost:* the two exposed test groups are not drop groups, so they sit in the 465 sensitivity row. Removing
  them gives headline 500 → 498, sensitivity 465 → 463, and the 35 co-feed subrow unchanged at 35. The matched role goes
  150 → 148. The K17d arithmetic must be re-verified with `b2_k17d.derive` on the reduced headline list, and the
  exclusion must be committed before any read.
- *Reproducibility:* good, provided the exclusion list is committed before the read and is derived from the exposure ledger.
- *Implementation scope:* one exclusion list, one validator update, and reporting rows that state the exclusions.
- *New generation authorization:* not required.

### D-1.4 Mandatory disclosure statement (applies under every option until a decision is recorded)

> The test role `B2-test/1` (500 groups) and the test-matched role (150 groups) are **not pristine**. Pilot checkpoints
> produced per-scene metrics and predictions on test groups 3200000 and 3200001 and matched groups 3300000 and 3300001
> (commits 46b13fc, 24feaa6, a09429b, ba98d6b, ec47a90, d88c689, 3c0068e, 5e824fe and 7108ee8; the last holds observation-level spectrogram arrays of group 3200000). The E9 approval recorded no decision
> citing those outcomes, but the record cannot exclude their influence. Any final result must report a sensitivity row
> that excludes these four groups. Nothing in this disclosure is a recognition-performance claim.

### D-1.5 Recommendation (advisory; the researcher decides)

Document the exposure now (done by this packet). Record Option A with the mandatory sensitivity row as the minimum. Consider
Option B only if the researcher wants a claim that holds without any disclosure. Option C is not recommended as the
first step, because it changes the approved reporting rule and gains little, since the removal is only four scenes.

## D-2 — M-4: operator-receiver contract for the dual-polarization inputs

**Decision needed:** state the receiver contract for the five-channel model, including which streams the operator actually
monitors and which plans are declared.

### D-2.1 Evidence

- `docs/plan/P14_dual_polarization.md:24` already assumes "two monitored IQ / PSD streams and two operator plans". The
  architecture therefore presupposes a dual-polarization monitor. It is not written as a contract with availability
  assumptions.
- `docs/plan/P18_b2_protocol.md:30–35` lists five channels, 1-based: 1 calibrated co-pol spectrum, 2 calibrated cross-pol
  spectrum, 3 co-pol plan mask, 4 cross-pol plan mask, 5 co-pol cancellation residual. The table in D-2.2 uses 0-based model
  indices, so the cross-pol spectrum is index 1 and the cross-pol plan is index 3.
- `src/geosim/b2_protocol.py` (the `FIFTH_CHANNEL` definition) states that the canceller input is "calibrated co-pol monitor
  IQ and the co-pol operator plan only", and lists "cross-pol observations" among its excluded inputs.
- `.claude/rules/scientific-invariants.md` item 1 allows "calibrated PSDs, operator plan masks" in general. It names only
  co-pol IQ and co-pol plan for the canceller. Cross-pol IQ is not forbidden by the invariant, but it is not listed as observable.
- `docs/plan/P14_dual_polarization.md:81` notes that operator plans differ between feeds, so a cross plan is a distinct
  declared object, not a copy of the co plan.

**Assessment.** The invariant is consistent with the dual monitor. What is missing is an explicit availability table saying
which quantity an operator would hold, with what precision and under which error model.

### D-2.2 Availability assumptions to be stated (proposed table, not yet approved)

| Quantity | Model channel | Assumed available to the operator | Basis | Error model stated? |
|---|---|---|---|---|
| Co-pol monitor IQ | 0, 4 (via canceller) | yes | P14:24 | no |
| Co-pol calibrated PSD | 0 | yes, after instrument calibration | P19 | calibration only |
| Cross-pol monitor IQ | 1 | **assumed** (P14:24, not a documented capability) | P14:24 | no |
| Cross-pol calibrated PSD | 1 | same as cross IQ | P18:30–35 | no |
| Co-pol operator plan | 2, 4 (canceller) | declared | P14:81 | **no** (exact in P20:120–121) |
| Cross-pol operator plan | 3 | declared | P14:24, P14:81 | **no** |
| Co-pol residual | 4 | derived from co IQ and co plan only | P20 and `FIFTH_CHANNEL` | plan exactness (see D-5) |

Channel numbers in this table are 0-based model indices. P18 numbers the same five channels 1 to 5 (see D-2.1).

### D-2.3 Options

- **Option 1 — explicit dual monitor, documented.** Keep the five-channel model. Add the table above as the operator
  contract. Report every `dual` and `dual_residual` result as "conditional on a dual-polarization monitor with declared
  cross plan". *Consequence:* the C2 claim is scoped to dual-pol operators; no change to the frozen data.
- **Option 2 — co-pol operator (the `co` view).** Report the `co` view (plus plan and residual) as the operator-realistic
  headline, and the dual views as an upper bound on what a dual monitor adds. *Consequence:* changes the reported headline.
  The approval R1 headline is `dual_residual`, so this is a change to the approved headline and needs an explicit decision.
- **Option 3 — dual IQ without cross plan.** Remove channel 3 (cross plan mask) and keep channel 1. *Consequence:* a new
  view and a new ablation; not a frozen view.

**Recommended (advisory):** Option 1, plus the `co` view reported alongside as the operator-realistic baseline. Option 2
changes the approved headline and must not be applied silently.

**Researcher decision still needed:** confirm the availability table in D-2.2 (in particular whether a cross-pol monitor
and a declared cross plan are assumed), and state whether `co` is reported alongside the `dual_residual` headline.

## D-3 — M-9: meaning of the auxiliary plan-consistency target under the K17b plan shift

**Decision needed:** confirm what the second output represents.

### D-3.1 Evidence

- The target is the simulator's activity state: `consistency = int(dropped is not None)` (`src/geosim/b2_scenarios.py:195`),
  where `dropped` is the removed planned carrier (`b2_scenarios.py:125–140`). It is therefore "a planned carrier is absent in
  the transmitted scene", i.e. the frozen activity state.
- The K17b shift changes only the operator plan mask. `_apply_plan_shift` rebuilds masks and leaves the target unchanged
  (`src/geoml/train.py:186–208`; in the streaming trainer the target is read at `src/geoml/b2_stream.py:424` and `:549`, and the
  shift is applied at `:533`).
- `docs/plan/P18_b2_protocol.md:170–188` (K17b) defines the second output as `plan_consistency ∈ {tutarlı, planlı taşıyıcı
  yok}` (consistent, planned carrier missing), states that it is independent of the main label, and calls the shift
  "kaydırma, etiketi koruyan artırım" (label-preserving augmentation).
- `docs/plan/P28_b2_e4_dual_pol_a5.md:44–45` notes that the K17b shift is the training augmentation, so the A5 `shift_*`
  perturbations are in-distribution for training.

**Assessment.** The name `plan_consistency` suggests plan–spectrum alignment, but the target is activity state. Under the
shift, the training input is a misaligned plan while the target says "not missing". The head is therefore trained to
read the spectrum, not the plan, for the missing-carrier decision. That is coherent with the frozen intent, but the name
and the documentation do not say so.

### D-3.2 Options

- **Option A — activity-state semantics, documented (recommended, advisory).** Keep the target and the shift. State in P18
  §7a and in the metric tables that the head reports whether a planned carrier is absent in the transmitted scene. Rename
  nothing in frozen artifacts. *Consequence:* no change to any frozen target, count or artifact. The head cannot be
  described as a plan-alignment detector.
- **Option B — plan–spectrum alignment target.** Recompute the target as "shifted plan is misaligned with the spectrum".
  *Consequence:* changes the target for about 15 % of training samples, so the frozen B2-feat/B2-base targets and every
  checkpoint change. Needs a new version name and a P18 section 10 entry.
- **Option C — decouple the head from the shift.** Exclude shifted samples from the auxiliary loss. *Consequence:* changes the
  training objective (the approved CE + center + plan BCE record would need a new clause).

**Researcher decision still needed:** confirm Option A (activity-state semantics), or choose B or C, which would be a
protocol change.

## D-4 — Mo-5: primary endpoint, family-wise multiplicity and statistical reporting plan

**Decision needed:** designate one primary endpoint and state the multiplicity rule for everything else.

### D-4.1 Evidence

- `docs/plan/P18_b2_protocol.md:147` states that the open-set metrics are per family and per predeclared group, and that
  the combined number comes only from the near families. P18 does not say which metric (AUROC/AP, OSCR or FPR@95TPR) is the
  combined number.
- `docs/plan/P18_b2_protocol.md:144–152` lists closed-set, open-set, operating-point, detection, leave-one-known-out,
  cost and statistics blocks without a primary endpoint.
- `docs/plan/P18_b2_protocol.md` §8 lists ablations A0–A8 with no family structure or correction. §6 says each expectation
  is tested "en az bir ablasyonla" (by at least one ablation).
- The approval record (`docs/plan/B2_E9_SCIENTIFIC_DECISION_APPROVAL_2026-10-24.md`) fixes the headline model
  (`dual_residual`, R1), the seeds (0, 1, 2), the scenario bootstrap and FPR@95TPR as separate from 0.95 known acceptance.
  It names no primary endpoint and no multiplicity rule.

### D-4.2 Options

- **Option 1 — one primary endpoint, everything else exploratory.** Designate the near-family pooled unknown-positive
  AUROC (or FPR@95TPR, to be chosen) for the `dual_residual` headline across the three seeds, with the scenario bootstrap
  interval. All other comparisons are labelled exploratory, with no p-value and no correction. *Consequence:* the claim
  rests on one number; the other results are descriptive.
- **Option 2 — a hierarchical test.** Primary endpoint first; secondary endpoints tested in a fixed order (fixed-sequence
  gatekeeping) only if the primary passes. *Consequence:* needs a pre-declared order and a pre-declared alpha.
- **Option 3 — family-wise correction (Holm) across a declared family.** Declare the family (for example the eight class
  recalls per view) and apply Holm. *Consequence:* a stated correction, but the family choice is itself a decision.

**Recommended (advisory):** Option 1 with FPR@95TPR named as the endpoint (it is already the approval's named open-set
metric), and every other comparison labelled exploratory. Option 2 is the next step if the researcher wants comparative
claims.

**Researcher decision still needed:** choose the primary metric (AUROC or FPR@95TPR), the population (near families, pooled),
the seed handling (all three seeds reported, endpoint on the seed mean or per seed), and the multiplicity rule for any
secondary claim. These are not engineering choices.

## D-5 — M-3: exact operator-plan assumptions in observation-based cancellation

**Decision needed:** whether a receiver plan-error sensitivity experiment should be preregistered, and with which
magnitudes.

### D-5.1 Evidence

- `src/geosim/cancellation.py:150–151` ("nothing else is used"); inputs are co IQ and the plan's `f0`, `symbol_rate`,
  `alpha`, `mod`, `code_rate` (`cancellation.py:166–170`).
- `docs/plan/P20_b2_cancellation_residual.md:120–121` states the plan frequency is assumed exact.
- `docs/plan/P28_b2_e4_dual_pol_a5.md:66–71` covers plan perturbations for the frozen checkpoint, with the residual recomputed
  from the corrupted co belief (`RECEIVER_CONSISTENT`, P28:41): `shift_plus/minus` (±0.5 MHz on every `f0`), `drop_one`,
  `phantom`, `authorize_intruder` and `stale_plan`.
- **Not covered by any committed perturbation:** symbol-rate error, modulation or roll-off error, frequency errors other than
  ±0.5 MHz, and a magnitude sweep. The canceller's depth dependence on these is therefore unmeasured.
- P28:44–45 notes that the ±0.5 MHz shift is also the training augmentation (in-distribution for training).

**Assessment.** A plan-perturbation experiment exists (P28 A5), but it is capped, uses frozen checkpoints, and does not
sweep symbol-rate, roll-off or modulation. So M-3 is **partially resolved** in the sense that a plan-error test exists; it is
**open** for the rate, roll-off and magnitude dimensions.

### D-5.2 Options

- **Option 1 — preregister a receiver-level plan-error sweep on cancellation depth only (recommended, advisory).** Sweep
  frequency error {0, ±0.25, ±0.5, ±1 MHz}, symbol-rate error {0, ±1, ±2 %}, roll-off error {0, ±0.05} and modulation
  mismatch on the known classes. Measure residual depth and decision SNR only, with no classifier. Use `train` and
  `val-select` groups only. *Consequence:* CPU-only and bounded. It produces a depth-versus-error curve and does not read the
  test role.
- **Option 2 — keep the A5 scope.** Report the ±0.5 MHz result and state that the rate, roll-off and magnitude dimensions
  are untested. *Consequence:* the "observation-based" claim carries an explicit exactness condition.
- **Option 3 — full classifier sensitivity.** Retrain or re-evaluate the classifier under each plan error. *Consequence:*
  requires new training and is not authorized.

**Recommended (advisory):** Option 1 for the depth curve (CPU only, no held-out read), together with the explicit exactness
condition of Option 2 in every residual-based claim. Option 3 is not recommended before the depth curve exists.

**Researcher decision still needed:** approve or decline the sweep, its magnitudes and its roles, and state whether the
depth curve may be reported in main results or only in a supplement.

## D-6 — N-5: order-statistic convention of the approved "higher empirical quantile"

**Decision needed:** confirm which order statistic the R10 clean-alarm threshold denotes. The approved wording does not settle it.

### D-6.1 Evidence

- Approved record: `docs/plan/b2_e9_approved_scientific_protocol.json:334` reads "higher empirical quantile, inclusive
  acceptance". The approval markdown fixes Pfa 0.05 (R10, line 35) and names no convention.
- Implemented in E10: `clean_alarm_threshold` uses NumPy `method="higher"`, the 0-based index `ceil((n-1)(1-Pfa))`, and the
  alarm is strictly `score > threshold`. The known-acceptance quantile already uses the same method
  (`src/geoml/calibration.py:131`), so the two thresholds share one convention.
- Numerical check on the scores 0 to 99 (n = 100, Pfa = 0.05), run in this PR:

  | Method | Threshold | Clean scores above it | Calibration alarm rate |
  |---|---|---|---|
  | `higher` (implemented) | 95.0 | 4 of 100 | 4 % |
  | `inverted_cdf` (smallest order statistic with at most n·Pfa scores above) | 94.0 | 5 of 100 | 5 % |
  | linear (historical `threshold_at_pfa`) | 94.05 | 5 of 100 | 5 % |

- The calibration unit is a flat clean sample, not a scenario group (Mo-3). The choice of convention does not change that.

### D-6.2 Options

- **Option A — NumPy `higher` (implemented).** Conservative: the calibration alarm rate is at most Pfa, and one order
  statistic below the tighter rule in general. Matches the acceptance quantile in `calibration.py:131`.
- **Option B — smallest order statistic with at most n·Pfa clean scores above it (`inverted_cdf`).** The most sensitive
  threshold that still meets Pfa on the calibration set. Changes the E9 threshold by one order statistic (95 to 94 in the
  example). No frozen artifact depends on the E9 path.
- **Option C — linear interpolation.** The historical rule, kept for frozen stages. It is not the approved wording and is
  not an option for the E9 path.

**Recommended (advisory):** Option A. The code already uses it for the acceptance quantile, and it is the conservative
reading. Choose Option B only if "higher" is meant as the tightest order statistic that attains Pfa.

**Researcher decision still needed:** A or B. Either choice is recorded by a dated amendment to the approved text, not by a
silent change.

## D-7 — N-2 / M-10: the default CLI mode reads the test role

**Decision needed:** whether the default `--mode legacy` of `python -m geoml.b2_experiment` may keep reading the test role.

### D-7.1 Evidence

- `src/geoml/b2_experiment.py:788–789`: `--mode` defaults to `legacy` ("legacy preserves capped small pilots").
- The legacy coupled path opens the known roles at `:436`, loads the test partition at `:480`, and runs per-view test
  inference at `:501`. Its docstring at `:9` says "``test`` is evaluated once", which the code does not do.
- The legacy path is capped at 12 groups per role (`LEGACY_MAX_GROUPS`, `:54`). The committed pilots use it.
- The E9 chain (`src/geoml/b2_execution.py`) is a separate path. Its calibration reads only the val-calib role, and tests
  enforce that.

### D-7.2 Options

- **Option A — keep the default and document it.** The committed pilots reproduce unchanged. The risk remains that a user
  who runs the default command reads the test role.
- **Option B — refuse test reads by default.** The default requires an explicit flag, for example `--allow-test-read`, to
  reach the legacy path. Pilot reproduction needs one extra flag. No committed result changes.
- **Option C — retire the legacy mode** after archiving the committed pilots. This removes the route for reproducing them, so
  it needs its own decision.

**Recommended (advisory):** Option B. It removes an accidental held-out read at the cost of one flag, and it changes no
committed result.

**Researcher decision still needed:** A, B or C. Option B is an engineering change and is not implemented here.

## D-8 — C-2: identity source for the K17d 500 / 35 / 465 record

**Decision needed:** whether the candidate identity record, derived from the frozen generator's scene metadata, may serve as
the K17d identity list, or whether the approval's requirement must be met first.

### D-8.1 Evidence

- The approval (`docs/plan/B2_E9_SCIENTIFIC_DECISION_APPROVAL_2026-10-24.md:16`) says: "Re-derive group identities from
  committed production generation metadata before any test observation is opened; verify the co-feed drop predicate against
  `docs/results/k17d_drift_audit.json`."
- No committed production generation metadata exists, because production generation is `NOT_AUTHORIZED`.
- The E10 candidate (`docs/results/b2_e10_k17d_identity.json`) is derived by `prepare_scene` metadata from the frozen
  generator at the recorded source hashes, with zero waveform calls. It reproduces the committed audit exactly: 500 / 35 /
  465 / 43 / 78, and every one of the 78 group IDs and polarizations agrees.
- The audit records no generator, predicate or hash (`k17d_drift_audit.json`, committed in `ba98d6b`). Its agreement is
  therefore evidence of consistency, not of an independent source.

### D-8.2 Options

- **Option A — accept the generator-derived candidate.** The approval wording is amended by a dated entry to "re-derive
  from the frozen generator metadata at the recorded source hashes". The production run would use the same generator. The
  record binds all 28 `src/geosim` modules and the audit hash, so any change forces a re-derivation. No generation is
  needed.
- **Option B — require committed production generation metadata first.** This needs a generation authorization (DR-04), which
  is not granted. K17d stays pending, and no test observation is opened.

**Recommended (advisory):** Option A, with the amendment recorded, because the generator is the one a production run would
use and the record binds its source. Choose Option B if the researcher wants production metadata to exist before any test
read.

**Researcher decision still needed:** accept A or require B. Until one is recorded, no K17d test observation is opened.

## D-9 — Items deliberately not decided here

- R1–R10 and the K18, K17d and OBS-CANCEL-2 records are unchanged. No new approval is recorded in this packet.
- No test protocol is chosen or implemented (see D-1).
- No generation, GPU probe, training, held-out evaluation or LOKO is authorized or started.
- Production launch remains disabled; `benchmark_complete` remains `false`.
- The R6 TF32 enforcement stays deferred to the reviewed executor, as the approval requires (M-2).
- Frozen A5 and E3b values, which use the linear helper or the subtraction score, are kept as archived (closure E-10). No
  re-run is made here.
- The E7b CPU evidence was produced by the linear-rule executor (closure E-11). A bounded rerun on this branch's
  `ALARM_RULE` is engineering work and is not run in this PR.

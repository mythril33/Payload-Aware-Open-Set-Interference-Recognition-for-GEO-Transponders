# B2-C2-ablation/1 — the C2 comparison: controls, contrasts, bounded verification and exact blockers

Date: 2026-10-26. Base `main` `47795c41dde586420e1732b2f64b22a09e63d639` (PR #46 merged). `benchmark_complete=false`. **Nothing here is approved,
nothing was run at production scale, and no recognition-quality result exists.** Every number below is labelled *measured*, *analytic* or
*extrapolation*; two-group fixtures establish functional and arithmetic correctness only.

## 0. Verdict

**C2 BLOCKED** — not by the comparison design, which is complete, source-isolated and tested at bounded scale, but by items that are not C2-specific and
that this work was not allowed to lift (section 9): no production-scope training executor (caps and the E9 guard refuse width 16 / 30 epochs / GPU by
design; the GPU path was never run), no authorized full data generation or launcher (DR-04 NO-GO), no designated hosts, no designated primary scorer, and no
approved final held-out read. Once those are resolved by the researcher's separate authorizations, the 21 declared fits run through the existing
`train-only → calibrate → freeze → evaluate` modes and `python -m geoml.b2_c2 contrasts` with **no further architecture development in the comparison**.
No performance claim for C2 or C3 is made.

## 1. What already worked, and what was missing

| Capability | State before this change | Evidence |
|---|---|---|
| Three canonical views `co`, `dual`, `dual_residual`; streaming trainer; isolated `train-only/calibrate/freeze/evaluate` | works, bounded CPU only | P24, P31, `tests/test_b2_execution*.py` |
| Closed-set and open-set metrics per model (scenario-group bootstrap), near-family pooled FPR@95TPR | works, per model | `geoml.openset_metrics`, `b2_execution._rejection_metrics` |
| Removing the operator plan from a model | **impossible**: every canonical view takes plan masks; the level reference is the planned-carrier core; `plan_consistency` and the K17b shift are plan-derived | `data.reference_level`, `train._inputs` |
| A matched control that isolates plan availability | **missing** | - |
| Cross-arm paired contrasts | **missing**: only per-model intervals; per-sample family scores were not persisted | - |
| A5 plan corruption | works, but is a *test-time stress of a frozen plan-trained model*, not evidence of learned plan benefit | P28 |

## 2. Hypotheses: three separate questions

| Id | Question | Contrast (richer − baseline) | What differs between the arms | What it does **not** show |
|---|---|---|---|---|
| H1 | Does the cross-pol channel help? | `dual` − `co` (primary, canonical recipe); `dual_noplan` − `co_noplan` (secondary, no plan anywhere) | the cross-pol spectrum (and its mask in the canonical pair) | plan benefit |
| H2 | Does the observed cancellation residual add beyond the dual-pol observations? | `dual_residual` − `dual` (primary, canonical recipe) | the fifth channel. **The residual is computed from the co-pol IQ and the operator plan**, so H2 lives inside the plan-available regime by construction | residual benefit without a plan |
| H3 | Does access to the operator plan help? | `dual_planmask` − `dual_noplan` (primary); `co_planmask` − `co_noplan` (secondary) | **only** the operator-plan mask channels | benefit of the plan-derived level reference, plan-consistency target or plan shift (see D1/D2) |
| D1/D2 | Descriptive decomposition | `dual` − `dual_planmask`; `dual` − `dual_noplan` | everything the canonical recipe derives from the plan | confirmatory statements |

A plan-corruption (A5) result is not interpreted as H3 evidence anywhere in this repository; H3 is answered only by the matched pair.
Two interpretation limits are part of the design, not footnotes: (i) some labels are **defined relative to the plan** (`unauthorized` versus `adjacent_satellite` by placement relative to
the operator plan, P18), so a model without the plan cannot separate them by construction and part of any H3 gap on those classes (and on the ASI-like `adjacent_satellite_downlink` near family)
is definitional rather than learned; (ii) the matched arms use one global plan-free level reference, whereas the canonical recipe normalizes each sample by its planned-carrier core, so the
descriptive D2 contrast upper-bounds the value of plan access. A plan-free per-sample normalization variant is **not** in the declared roster; if the researcher wants H3 against that stronger
plan-free baseline it must be pre-declared as a sensitivity arm before any test read.
Metric: `near_fpr95` = known-test fraction scored unknown at the first threshold that detects 95 % of the pooled near-family unknowns (`pulsed`,
`intermittent_bursts`, `adjacent_satellite_downlink`; unknown = positive; larger score = more unknown-like); lower is better; contrast = richer − baseline,
so negative favours the richer arm. AUROC, closed-set accuracy and macro-F1 are exploratory. The D-4 headline is `dual_residual` `near_fpr95`,
reported per seed with a descriptive seed mean (`b2_c2.endpoint`).

## 3. The no-plan control (`B2-C2-ablation/1`, versioned separately; canonical models untouched)

Views (`geoml.data.C2_VIEWS`): `co_noplan` (1 channel), `dual_noplan` (2), `co_planmask` (2), `dual_planmask` (4).
`*_planmask` = the `*_noplan` spectral channels, bit for bit, plus the plan-mask channels in the canonical order.

| Plan-information path | How it is closed for `*_noplan` | Test |
|---|---|---|
| Plan mask channels | not part of the view; `preprocess_c2` raises if a mask is passed | `test_noplan_preprocessing_refuses_masks…`, `test_noplan_inputs_are_bitwise_independent…` |
| Level reference (carrier-core of the plan) | plan-free `observed_level_db` (90th percentile over frequency of the time-averaged co-pol PSD), training mean only; arithmetic pinned by an independent computation | `test_observed_level_follows_its_declared_definition…`, `test_plan_free_reference_ignores_the_plan…` |
| Plan-dependent residual channel | not an input of any C2 view | input-invariance test with a junk residual |
| `plan_consistency` auxiliary target and head | `TrainConfig` refuses it for C2 views | `test_c2_views_refuse_plan_derived_settings` |
| K17b plan-shift augmentation | refused for C2 views (it perturbs plan masks only) | same |
| Streaming layer | `_shard_arrays` drops `mask`/`residual` before any builder sees the shard; a strict-access spy shard fails if a plan key is even probed | `test_noplan_view_reads_no_plan_key_in_any_path`, `…streaming_layer_drops…` |
| Evaluation time | held-out masks/residuals/targets changed ⇒ `*_noplan` frozen scores and predictions are bit-identical; `*_planmask` ones change (non-vacuous control) | `test_a_plan_change_at_evaluation_cannot_move_the_noplan_cells…` |
| Training weights | altering every plan-derived array of train/val-select leaves weights, history, reference and embeddings bit-identical; the plan-mask arm changes | `test_changing_every_plan_derived_array_cannot_change_a_noplan_model` |

## 4. Fairness of the matched pair, and the three declared deltas to the canonical recipe

`*_planmask` and `*_noplan` share: seed, data order, augmentation RNG stream, AdamW/OneCycle, epochs, batch, width, time-pool, CE + center loss,
the plan-free reference, checkpoint selection (val-select macro-F1), Mahalanobis fit (train only), calibration populations (known val-calib only) and the **initialization of every
non-stem tensor** (`train._fresh_model`: the review found that a different stem size shifted the RNG stream so all later layers started differently; for C2 views the non-stem modules are now
re-initialized from a seed that depends on the run seed only, and the global RNG is re-seeded afterwards; canonical models start bit-identically to before — tested). The stem convolution
differs in shape by construction, so its draw differs.
They differ in the mask channels and therefore only in the stem convolution: `dual_planmask` − `dual_noplan` = 400 parameters at width 8 and 800 at
width 16 of ≈ 79 k / 311 k (analytic; `docs/results/b2_c2_bounded_verification.json`). Capacity is therefore matched except for the input being tested;
the canonical arms carry 79 177 (`dual`) and 79 377 (`dual_residual`) parameters at width 8 and 311 305 / 311 705 at width 16 (the latter equals the E8 figure).

The matched recipe differs from the canonical (approved R1–R10) recipe in exactly three declared settings (`b2_c2.matched_deltas`): `training.level`
(`absolute` plan-free vs `carrier`), `plan_consistency` (false vs true), `training.plan_shift_fraction` (0 vs 0.15). Canonical production parameters
(width 16, 30 epochs, batch 32, lr 1e-3, weight decay 1e-4, center 0.005, plan loss 1.0) are asserted equal to the approved E9 configuration in a test.

## 5. Declared roster and resource budget (fixed before any execution)

| Tier | Fits | Role |
|---|---:|---|
| 1 — `co`, `dual`, `dual_residual` × seeds 0,1,2 | 9 | approved primary design (R1); unchanged |
| 2 — `dual_planmask`, `dual_noplan` × seeds 0,1,2 | 6 | **required for H3** |
| 3 — `co_planmask`, `co_noplan` × seeds 0,1,2 | 6 | optional secondary controls |
| Total / required for H3 primary | 21 / 15 | `docs/plan/b2_c2_experiment_matrix.json` (generated by `python -m geoml.b2_c2 matrix`; a plan, not loadable by any runner) |

Smoke configurations: `configs/c2/smoke_{canonical,dual_matched,co_matched}_seed{0,1,2}.json` (width 8, 2 epochs, batch 32), equal to their generator by test.

## 6. Run protocol and statistics

1. `train-only` per seed (fit and Mahalanobis on train only; val-select picks the checkpoint) → 2. `calibrate` (known val-calib only) →
3. `freeze --profile {proposed-full|c2-h3-dual|c2-h3-co}`: complete inventory, hashes of every checkpoint/scorer/calibrator, no held-out source opened →
4. `evaluate` once (test, test-only families and matched set read after the inventory verified; per-sample `unknown_families` scores persisted) →
5. `python -m geoml.b2_c2 contrasts --evaluation DIR… [--primary-scorer S]` (offline; opens no dataset; refuses unequal populations or artifacts, a different source revision, runtime or
known-data identity between evaluations, unequal training budgets (`epochs, batch, width, time_pool, lr, weight_decay, augment, center_loss_weight`; only the declared recipe deltas may differ),
duplicate cells, tampered outputs, and any stored point estimate it cannot reproduce; each evaluated model now records its `TrainConfig`). `--primary-scorer` only records a designation approved
before the final read; without it the table says NOT DESIGNATED. A metric that is undefined (for example no near-family unknowns) is reported `UNAVAILABLE` with a reason, never `MEASURED` with nulls.

**Forking-path rule.** Canonical, `c2-h3-dual` and (optionally) `c2-h3-co` are three separate `evaluate` calls that each read the test role. Each call is individually gated, but the optional
co-pol roster could be chosen after seeing primary results. The final-evaluation approval (checklist item 8) must therefore name all evaluate calls in a fixed order and decide tier 3 *before the
first test read*; the code does not enforce this ordering.

Uncertainty: whole scenario groups (all paired variants and test-only families) are resampled once per replicate and shared by every arm and seed;
intervals are conditional on the frozen models and calibrators and contain **no training-seed uncertainty**. Seed-level values are reported individually with
descriptive mean/min/max/SD (n = 3); no seed CI, no multiplicity adjustment, no confirmatory superiority claim (D-4). All three scorers are always reported.

## 7. Primary-scorer decision request (OPEN — needs explicit researcher approval before any final test read)

D-4 fixes the endpoint and the model view but not the scorer. Options: **MSP** (`1 − max softmax`), **energy** (`−logsumexp`), **Mahalanobis** (train-only class means,
shared shrunk covariance 0.1, penultimate embedding). Pre-test recommendation, made without any held-out result: **Mahalanobis**, on design grounds only — the
center loss (K17/K18) exists to make class prototypes the geometry of the embedding, which distance-based scoring uses directly; MSP/energy depend on
logit confidence, which near-family unknowns that physically resemble a known class are expected to keep high. The pilots are at chance and cannot inform
the choice. If the researcher prefers MSP or energy, the contrasts and table are unchanged. `b2_c2` keeps `primary_scorer = null`; the table prints
"NOT DESIGNATED". Required approval text: *"The primary scorer for B2-C2 and decision D-4 is `<msp|energy|mahalanobis>`; all three remain reported; this
designation precedes any authorized final test read."* Selecting or switching the scorer after seeing protected results is forbidden. The code cannot bind the designation into the frozen inventory; the approval record must predate the first `evaluate`
call and be passed to `contrasts --primary-scorer`.

## 8. Bounded verification actually performed (measured; functional and arithmetic only)

| Check | Result |
|---|---|
| C2 test modules (`tests/test_b2_c2_{noplan,contrasts,configs}.py`) | 97 passed (57 + 35 + 5) after the red-team fixes; every invariance test has a positive control |
| Mutation check of 32 defenses (plan-key reads, reference, stream drop, TrainConfig refusals, channel concatenation, contrast sign/direction/pairing, population/stored-estimate/roster checks, matched recipe) | 32/32 killed: 22 on the first version (three survivors closed with new tests: percentile pin, stored-estimate tamper, re-signed incomplete inventory) plus 10 for the red-team fixes (merge provenance/budget/training-required, alignment, UNAVAILABLE, training config recorded, matched init, downstream re-seed, canonical init unchanged, fixture roster) |
| Real-physics 2-group fixture `data/b2-feat-pilot` (B2-feat/1, 16 observations per role): 12 view-fits (6 `train-only` runs: 3 seeds × {dual, co} matched bundles) → 6 `calibrate` → 2 `freeze` | all succeeded; `c2-h3-dual` and `c2-h3-co` inventories have six cells each, `full_protocol_admission=false`, `production_authorized=false`; train/val-select/val-calib opened, **test role not opened** |
| Cost on that fixture (measured, CPU, 2 threads) | `train-only` 9.0–10.4 s wall, peak RSS 0.93–0.98 GiB; `calibrate` 4.2–4.9 s, 0.68–0.70 GiB (run on the post-review code; the recorded `source_revision` is the parent commit of a dirty working tree, the exact source is bound by the training markers' file hashes). RSS is dominated by the torch import at this size; **not** extrapolable |
| `evaluate` + `contrasts` end to end | on the deterministic stand-in fixture only (tests); the real-physics fixture's test role was deliberately not read |

```bash
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 PYTHONHASHSEED=0 CUDA_VISIBLE_DEVICES=
for b in dual_matched co_matched; do for s in 0 1 2; do
  python -m geoml.b2_experiment --mode train-only --config configs/c2/smoke_${b}_seed${s}.json --data data/b2-feat-pilot --out runs/c2-bounded/${b}_seed${s}
  python -m geoml.b2_experiment --mode calibrate --data data/b2-feat-pilot --runs runs/c2-bounded/${b}_seed${s}
done; done
python -m geoml.b2_experiment --mode freeze --profile c2-h3-dual --seeds 0 1 2 --bundle runs/c2-bounded/dual_matched_seed{0,1,2} --out runs/c2-bounded/inventory_c2_h3_dual.json
python -m geoml.b2_experiment --mode freeze --profile c2-h3-co   --seeds 0 1 2 --bundle runs/c2-bounded/co_matched_seed{0,1,2}   --out runs/c2-bounded/inventory_c2_h3_co.json
```

(`--bundle` is repeated once per directory in the real invocation.) Validation macro-F1 on the fixture is 0.03–0.11 (chance); selected epoch 0. Nothing is concluded from it. Evidence: [`b2_c2_bounded_verification.json`](../results/b2_c2_bounded_verification.json).

## 9. Production feasibility — exact blockers and resources

**Blockers (none of them is a missing C2 component; all are shared with the canonical nine fits):**

| # | Blocker | Evidence | Needs |
|---|---|---|---|
| 1 | No production-scope training executor | `src/geoml/b2_execution.py` `CAPS` (2 groups/role, 2 epochs, width 8, batch 32), `_cpu()` refuses `cuda`; `b2_e9_contract.guard_execution` always refuses; E8 NO-GO | separately reviewed change after the researcher's training authorization; a GPU probe (spec exists, no executor) |
| 2 | GPU path never executed; R6 numerics (fp32, TF32 off) enforced only as a recorded contract | `docs/plan/b2_e8_gpu_probe_spec.json`; "GPU parity untested" | authorized GPU probe on the designated host |
| 3 | Full data generation not authorized and no launcher | E7a supervisor ≤ 2 groups; `PRODUCTION_LAUNCH_ENABLED=False`; E13–E18 are validators/synthetic lifecycle; DR-04 NO-GO | DR-04 record, trust/revocation/CI evidence, release decision |
| 4 | No designated hosts or independent backup | E8 inventory of this sandbox: FAIL (disk 19.7 GiB free, one device, no GPU, 15 GiB RAM) | generation host, training GPU host, backup device |
| 5 | Primary scorer undesignated | section 7 | researcher |
| 6 | Final held-out read not approved; B2-test/1 and matched groups carry prior-exposure disclosure (D-1; 498/148 sensitivity rows mandatory) | E12 | frozen-evaluation approval |

**Resources** (matched arms reuse the same dataset: **no additional generation**; generation figures are the E5/E8 ones, unchanged):

| Item | Value | Basis |
|---|---|---|
| Generation, 21 350 observations, one process | 23.0 / 26.6 / 30.2 h; 8.7 GB | extrapolation from a 60-observation profile (E5/E8) |
| Sample passes, 30 epochs × 12 000 | 360 000 per fit; 3.24 M (9 canonical); 4.32 M (12 matched); 7.56 M (21) | analytic |
| GPU, width 16, compute + un-overlapped loader | canonical 9: 9.95–21.87 h; 12 matched: 13.27–29.16 h; **all 21: 23.2–51.0 h** | extrapolation: E8 arithmetic (`scripts/b2_e8_budget.py campaign`) with dual_residual MACs for every arm, hence conservative for 1–4-channel inputs; the width-8 "6 GPU-h" figure stays withdrawn |
| CPU-only fallback, 21 fits | ≈ 82 h compute before the loader | measured_cpu_noisy rate × passes; not realistic |
| Training host RAM / disk / GPU memory | ≥ 16 GiB / 25 GiB + own verified copy ≥ 9 GB / ≥ 8 GiB (12 GiB preferred) | plan_assumption (E8); GPU memory analytic only |
| C2 additions | 12 checkpoints ≈ 1.2 MiB each at width 16; `predictions.json` grows by the per-sample family scores (order of 10 MB for 21 cells) | analytic order of magnitude |

**Ordered approval checklist** (each item is the researcher's or operator's, none is implied by this work): (1) designate the primary scorer; (2) designate generation,
training/GPU and backup hosts and measure them; (3) DR-04 generation record with run-bound ceilings, then a separate release decision; (4) authorize and run the bounded GPU
probe, replacing the screening bands; (5) review and merge a production-scope training executor that consumes the approved R1–R10 matrix; (6) authorize training of the 21
(or the 15 required) fits; (7) verify the frozen 9/6/6-cell inventories; (8) approve the final held-out evaluation with the D-1 disclosures, naming **all** evaluate calls (canonical, `c2-h3-dual`, and whether `c2-h3-co` is included) in a fixed order, decided before the first test read; (9) run `contrasts` once and fill the template.

## 10. Independent scientific red-team (Phase 7)

A separate model agent (not a human approval) reviewed commit `50d4b41` read-only. **No blocker; no path by which plan information reaches a `*_noplan` model; no hidden test-role read.**
It re-derived the contrast arithmetic and the paired bootstrap independently (point estimates and per-seed intervals reproduced) and ran the old and new source trees against each other:
config fingerprints and in-memory/streaming fits of `co`, `dual`, `dual_residual` (with and without `plan_consistency`) were identical, so canonical behaviour is unchanged. Its findings and their disposition:

| # | Severity | Finding | Disposition |
|---|---|---|---|
| 1 | MAJOR | Cross-evaluation contrasts (H1, H2, D1, D2 mix a canonical and a `c2-h3-*` evaluation) did not check that arms were fitted by the same code, runtime or training budget | **Fixed**: `results.json` records each model's `TrainConfig`; `merge_cells` refuses differing source/runtime/data identity and differing budget fields; tests with a control that allows the declared recipe deltas |
| 2 | MINOR | Matched arms did not start identically outside the stem (stem size shifted the RNG stream) | **Fixed** for C2 views only (`_fresh_model`); canonical init bit-identical (tested); control test shows the old behaviour differed |
| 3 | MINOR | `paired_contrasts`/`endpoint` applied one cell's group index to all cells without asserting alignment | **Fixed**: public functions refuse differing populations |
| 4 | MINOR | `endpoint` reported `MEASURED` with null values and no reason (D-4 requires null with reason) | **Fixed**: `UNAVAILABLE` + `unavailable_reason`; the table prints it |
| 5 | unverified | Three evaluate calls = forking path against "test evaluated once" | **Procedural** (section 6 forking-path rule, checklist item 8); not code-enforced |
| 6 | unverified | Primary-scorer designation cannot be bound before the read | **Partly**: `--primary-scorer` records it; binding into the frozen inventory is not implemented (procedural) |
| 7 | unverified | `CONTRASTS` strings overstated isolation (H1 also adds the cross-pol mask channel; D2 baseline lacks per-sample normalization) | **Fixed** (wording; section 2) |
| 8 | unverified | Plan-relative labels make part of an H3 gap definitional | **Documented** (section 2) |
| 9 | unverified | FPR@95TPR operating point is chosen from test unknowns (not deployable) | **Documented** (module docstring, section 2/D-4) |
| 10 | unverified | Observed-level 90th percentile is fragile near ≈10 % carrier occupancy (11–13 % on the fixture) | **Documented**; only one global training mean is used, identically by both arms |
| 11 | unverified | `fixture` profile accepted all seven views | **Reverted** to the canonical views (behaviour unchanged) |

Negative and inconclusive results are kept: this review found the cross-evaluation gap in the first version; the fixes are tested but the review is a model review, not an independent human audit.

## 11. The single comparison table

[`docs/results/b2_c2_comparison_table_template.md`](../results/b2_c2_comparison_table_template.md) is `python -m geoml.b2_c2 template` output: every row reads **NOT RUN**.
A filled table is produced only by `contrasts --table` from completed frozen evaluations and carries its scope line. Until then the C2 outcome is unmeasured.

## 12. Smallest controlled C3 experiment (recommendation only — not started)

C3 is the payload gap: a model trained without the nonlinear payload chain degrades when the chain is present. The smallest controlled test is a 2 × 2 regime matrix on
**one** fixed recipe and view (suggest `dual_noplan`, to keep C3 free of plan effects): train on {linear payload, nonlinear payload} × evaluate on {linear, nonlinear}, using
the same scenario groups, seeds 0,1,2, the same known classes and the same frozen-model protocol, so the C3 quantity is the paired off-diagonal degradation (train-linear →
test-nonlinear) relative to the diagonals, with scenario-group intervals. It needs only the existing chain switch (`geosim.dual`) to render each scene twice and no new model
architecture. It must be authorized and budgeted separately (4 regimes × 3 seeds = 12 small-recipe fits), after C2's production blockers are resolved.

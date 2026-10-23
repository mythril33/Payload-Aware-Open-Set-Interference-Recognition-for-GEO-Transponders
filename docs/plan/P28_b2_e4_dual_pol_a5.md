# P28 — E4 dual-polarization A5 operator-plan corruption

Registered 2026-10-23 on `main@ff81cae1b4e2563cc88271566665e9feae7cd44e`, **before** any E4 code,
physical replay, model inference on corrupted plans or inspection of A5 outcomes.
Parent: frozen P18 §7a/§8 (A5, K17b), P20 (`obs-cancel/1`), P23 §E4 and the E1–E3b records.
Contract names: **`B2-A5-eval/1`** (evaluation artifact) and **`B2-A5-plan/1`** (perturbation definitions).
`benchmark_complete=false`. K18, K17d and OBS-CANCEL/2 stay `PENDING_RESEARCHER`; full generation, full GPU
training and the full LOKO sweep stay `NOT_AUTHORIZED`. This is a bounded engineering harness, not evidence of
robustness, deployment capability or recognition quality.

Nothing below may be changed after seeing A5 outcomes. Changes need a new contract version (`B2-A5-eval/2`)
and a §10 entry.

## 1. Question and causal design

> How do frozen payload-aware, plan-conditioned recognizers behave when the operator plan presented to the
> monitoring system is wrong, stale, incomplete or falsely authorizes an observed carrier?

Three objects are kept apart:

| Object | Meaning | Changes under A5? |
|---|---|---|
| **Physical truth** | transmitted carriers, event, payload, dual-pol coupling, noise, receiver calibration, calibrated IQ | **never** |
| **Operator belief** | co-pol and cross-pol carrier descriptors given to the monitor (`OperatorPlans`) | **yes** (the intervention) |
| **Model observation** | co/cross PSD, the two plan masks built from the belief, the observation-derived residual | derived from the other two |

The experiment intervenes on the operator belief only. No RF carrier is moved, inserted, removed or
re-modulated; no random stream, TWTA load, oscillator, coupling matrix or receiver calibration changes.
The operator belief is its own type and is **not** a physical `Carrier` plan: it is not required to sum to unit
power, is never renormalized, and is never passed to `simulate_dual`.

## 2. Evaluation conditions

For every scene and every applicable perturbation exactly three conditions are evaluated with the **same**
frozen checkpoint, scorers and thresholds:

| Condition | PSD | Masks | Residual (fifth channel) |
|---|---|---|---|
| `original` | stored | stored (from the true plan) | stored |
| `MASK_ONLY` (weaker control) | stored | rebuilt from the corrupted belief | **stored, unchanged** |
| `RECEIVER_CONSISTENT` (primary) | replayed (verified against the stored shard under the §5 parity policy; bit-equal when `exact`) | rebuilt from the corrupted belief | **recomputed**: frozen `cancel_planned_carriers(replayed calibrated co-pol IQ, corrupted co-pol belief, CancellationConfig of the source)` |

`MASK_ONLY` is labelled as the weaker control and is never described as a consistent receiver response.
Consequences that are reported, not hidden: the `co` and `dual` views do not read the residual, so their
`MASK_ONLY` and `RECEIVER_CONSISTENT` outputs differ at most through the replayed PSD (identical when the §5 parity is
exact; the result records `psd_identical`/`logits_identical`); only `dual_residual` differs through the residual, and
only when the co-pol belief changes. For `cross_only` scope the co-pol residual is identical in all conditions.

Mask pipeline: `geosim.plan.plan_mask_db(belief_carriers)` then `float16`, the same convention as the stored
masks. The preprocessing, including the carrier-level reference computed from the co-pol mask, is rerun on the
new masks exactly as `geoml.plan_shortcut` and the K17b augmentation do.

## 3. Pre-registered perturbations (`B2-A5-plan/1`)

Index order (also the RNG key): `none`=0, `shift_plus`=1, `shift_minus`=2, `drop_one`=3, `phantom`=4,
`authorize_intruder`=5, `stale_plan`=6. Each descriptor (co, cross) is transformed **independently** from its
own plan with `numpy.random.default_rng([scenario_id, 1850, index, polarization])` (polarization co=0,
cross=1). Namespace 1850 is unused by every frozen namespace (1801, 1810, 1813, 1820, 1830, 1840; simulator
7051/7052). Scope `both` is exactly the union of `co_only` and `cross_only` results (tested) and is applicable only if both
descriptor transformations are applicable.

| Perturbation | Definition | Not applicable when |
|---|---|---|
| `none` | exact original belief | never |
| `shift_plus` / `shift_minus` | every carrier `f0` of the selected descriptor ±0.5 MHz exactly (the P18 K17b / `plan_shortcut` value, ≈2.7 bins); other fields untouched | never; a carrier whose shifted band leaves ±18 MHz is **kept** and flagged `exceeds_transponder_edge` |
| `drop_one` | remove carrier `i = rng.integers(len(plan))` from the descriptor; remaining powers unchanged, **no** renormalization; the carrier is still transmitted | descriptor has fewer than 2 carriers |
| `phantom` | append `geosim.interferers.random_unauthorized(rng, plan, 36 MHz, 0.0)`: one extra declared carrier in a free gap of the belief, PSD equal to the plan mean; it is not transmitted | `InfeasibleCarrierError` (no free gap) |
| `authorize_intruder` | append the physically present unauthorized carrier (`f0`, `symbol_rate`, `alpha`, `mod`, `power = 10**(-c_over_i_db/10)`) to the selected descriptor(s) | scene label is not `unauthorized` (known and matched stages); the carrier description comes only from the replay layer's controlled **test intervention**, exactly like `plan_shortcut` |
| `stale_plan` | replace the selected descriptor by `geosim.scenario.default_plan(2*(scenario_id-1)+polarization, 36 MHz)`: the initial-draw plan of the *preceding scenario id* (a pure function of the seed; no observation or label of another group is read). It is a formula, not history: the preceding id may lie outside the reserved B2 roles, and that group's own plan may have needed redraws, so the replacement is not necessarily the plan that group held | the replacement equals the original (`not_applicable`); a replacement rejected by §4 is `blocked` |

`authorize_intruder` is restricted to `unauthorized` because that is the frozen A5 definition; an analogous
"authorized ASI" intervention is **not** part of `B2-A5-plan/1` (PLANNED, new perturbation name required).
Perturbation choices never use scores, labels' model outputs or favourable-case selection. A non-applicable
or invalid case is **recorded with its reason and excluded from that perturbation's paired population**; no
resampling, no replacement draw.

Scopes: `co_only`, `cross_only`, `both`. `authorize_intruder` in the cross descriptor is a counterfactual
declaration of the same carrier parameters (the intruder leaks into the cross feed through the physical XPD);
it is allowed and flagged `declared_on_cross_feed`.

## 4. Validity checks

Every resulting descriptor must: be a nonempty list of `Carrier`; have finite positive `symbol_rate`,
`alpha ∈ (0,1]`, `power > 0`, finite `f0` (Hz); have a supported modulation/code rate; satisfy
`FS_SIM/symbol_rate` integer ≥ 8; lie inside the monitor band (these are exactly the checks of
`geosim.cancellation._validate_plan`, which is called as the oracle of validity); yield a finite plan mask with
at least one core bin (> −3 dB). Total power is **not** required to be 1. A descriptor failing a check is
`blocked` with the validator's message and counted; the frozen canceller is never modified or bypassed.
Additional informational flags: `exceeds_transponder_edge`, `dropped_carrier_transmitted` (replay-layer
metadata, reporting only), `phantom_overlaps_physical_event`.

## 5. Physical replay and parity

Replay reconstructs a scene with the artifact's own request, never with new settings:

- the scene constructor of the artifact stage (`sample_scene` for B2-feat/1 known, `sample_matched_scene` for
  B2-match/1) with the artifact's `B2Config`, the artifact's verified `receiver_calibration.npz`
  (bound to its request, checksum-verified) and `keep_iq=True`; no calibration is fitted on test scenes;
- the artifact's `CancellationConfig` (`obs-cancel/1`); a different version/config fails closed;
- generator-source drift (`geosim` source hashes recorded in the request versus the current tree) fails closed:
  regenerate the pilot in a fresh directory, never relax the check.

Before any A5 number is produced the `none` replay of every **applicable** selected scene (scenes where the perturbation is not
applicable are not replayed and not parity-checked; they are counted) is compared with the stored shard
(arrays and metadata): scenario id, label, role, plan-consistency, plans, activity, stored masks (exact),
stored PSD and stored residual. Policy: float16 arrays must be **equal**; on a different machine/library build
at most `PARITY_ATOL_DB = 0.125` dB (two float16 ulps at |x| in [64,128)) maximum absolute difference is
tolerated and reported with `exact=false`; anything larger raises and aborts (`fail closed`, no
receiver-consistent claim). Raw IQ is transient, never stored, never committed.

Physical invariants (each has a test): **A** received IQ identical for every belief (it holds by construction: `replay_scene` has no belief parameter; the tests hash the IQ before and after and spy on the simulator); **B** `cross_only`
leaves the co residual identical (the canceller is not even invoked); **C** a changed co belief is recomputed
by the frozen canceller (call counted, output equal to a direct call); **D** `none` equals the stored fifth
channel; **E** the canceller receives only IQ, co-pol belief and its config; **F** replay never receives a
belief and `simulate_dual` is never called with one.

## 6. Frozen models and the model boundary

Views `co`, `dual`, `dual_residual` use the checkpoints, Mahalanobis scorers, rejection calibrations and
alarm threshold produced by `geoml.b2_experiment` on the same known artifact. Nothing is trained, fitted,
calibrated or selected on A5 populations. A missing view is reported unavailable (`null` + reason).

Checkpoint reuse rule (required because `b2_experiment` provenance hashes every `src/**/*.py`): the checkpoint
provenance must equal the known artifact (protocol, data fingerprint, role groups); every source file recorded
in the checkpoint must be **byte-identical** in the current tree; files that exist now but not at training
time must be a subset of the declared E4 additions. E4 modifies no existing source file. Any other drift
fails closed. Mahalanobis and rejection provenance strings are recomputed from the checkpoint hash and known
data and compared; the clean alarm threshold is recomputed from known val-calib only (and compared with the
run's `results.json` when present).

The model-facing function receives an `ObservedInputs` value holding exactly `spec`, `mask` and `residual`.
Labels, groups and plan-consistency targets are evaluation bookkeeping that cannot influence outputs
(tested by permuting them).

## 7. Label semantics

Four layers stay separate: (1) original physical scenario label, (2) original operator-relative label
(plan-consistency target), (3) the counterfactual intervention, (4) the classifier output. A plan corruption
changes the operator-relative **meaning** of an observation, not its physics, so counterfactual outputs are
**not** scored as conventional accuracy. Reported against the original labels they are named
`agreement_with_original_label`; `accuracy` exists only for the `original` condition. Descriptive operational
readings (no truth claim): `drop_one` of a transmitted carrier is observationally an unplanned carrier
(P18 §7a); `phantom` declares a carrier that is absent; `authorize_intruder` removes the intruder's
unauthorized status; `shift_*`/`stale_plan` have no frozen counterfactual label (`null`).

## 8. Metrics (all paired by scene; group = scenario id)

Per view × condition × (perturbation, scope): `n_scenes`, `n_groups`; `agreement_with_original_label` and
`macro_f1_vs_original_label` (macro over classes present in the evaluated truth, as `geoml.metrics.macro_f1`);
8×8 confusion against the original label; `prediction_change_vs_original` (fraction of scenes whose argmax
differs from the `original` condition) and the full 8×8 `transition_matrix` (rows: original-condition
prediction, columns: corrupted-condition prediction); `clean_false_alarm` (positive class: any alarm,
denominator: clean-labelled scenes) and `event_detection` (denominator: non-clean scenes) at the clean-val-calib
alarm threshold; `known_acceptance` per method at the known-only val-calib thresholds; paired
`score_displacement` per method (corrupted − original unknown score, larger = more unknown-like);
plan-consistency head predicted-positive rate and descriptive agreement; for the matched stage the ASI-versus-
unauthorized 2×2 with clean / other-known / rejected predictions kept in the denominator; and residual
diagnostics from observable data only: `residual_total_db`, `cancellation_depth_db = spec_co_total_db −
residual_total_db` (mean linear power over time and the full 96 MHz band, then dB) and its displacement.
`clean_false_alarm` / `event_detection` are alarm rates among scenes whose ORIGINAL label is clean / not clean; under a counterfactual
condition they are **not** false-alarm or detection rates whenever the intervention changes what an alarm means (for example a transmitted
carrier removed from the plan is observationally unplanned, P18 §7a). Rates are `null` with counts when the denominator is empty; intervals are the scenario-group bootstrap of
`geoml.metrics.cluster_ci` (2000 resamples, seed 0, groups resampled together) and `null` below two groups.
Training-seed uncertainty is separate and absent here (single frozen checkpoint). Unknown-family
metrics (AUROC/OSCR) are not produced: the known and matched stages contain no unknown families.

## 9. Caps (enforced in code and tests)

CPU only; no training; ≤2 scenario groups per evaluated role; ≤2 physical classes; one perturbation
configuration (perturbation × scope) per invocation; ≤16 physical replays and ≤24 cancellation evaluations per
invocation (the parity cancellation counts); no data generation, no checkpoint writing. There is no
unrestricted mode; lifting a cap requires a code change, a new contract version and researcher authorization
of the corresponding gate.

## 10. Baselines (E4.5)

EDSC, planned/blind CA-CFAR and XGBoost consume only (spec, mask, residual). With the corrupted arrays of §2
their *inputs* can be recomputed, but no frozen baseline artifact exists on `main` and baseline fitting on a
pilot would be training. Their model-level A5 evaluation is therefore `PLANNED` and, in this slice, limited to
documenting which stream each baseline reads (blind CA-CFAR ignores the plan; EDSC reads the residual and an
observed-carrier reference; XGBoost reads both masks and the residual). Binary detection, eight-class
recognition and open-set rejection tasks are never compared with one another.

## 11. Artifact identity

`results.json` (strict JSON, no NaN/Infinity) records: contract names; source artifact stage, fingerprint and
request fingerprint; B2 protocol; HEAD Git SHA, the full current source-file hashes and library versions; calibration and cancellation
identities; checkpoint hash per view; scorer/threshold identities; perturbation, scope, modes and scene ids;
original and corrupted plan identities (`sha256` of canonical JSON); applicable/non-applicable/blocked counts
with reasons; parity report; counts of replays, cancellations and scored samples; elapsed time, peak RSS and
the reproduction command; `benchmark_complete=false`.

### 11a. Resumability and reuse

An interrupted invocation continues instead of restarting. Each completed applicable scene writes its replayed PSD and recomputed
residual (float16), parity report and work counts under `out/state/`, JSON committed last with the SHA-256 of the arrays and bound to the
experiment fingerprint. That fingerprint covers the configuration, known/matched artifact identities, request, the run directory's
`config.json` and frozen-file hashes (checkpoints, scorers, rejection calibrations, run results) and the full source tree. On restart
`*.tmp` files and array files without their JSON (never committed) are discarded; committed entries are verified and reused; a modified
entry, or any binding to a different identity, is rejected (fail closed). A result without its checksum sidecar is rebuilt from the verified
state without any replay; a complete checksummed result with the same fingerprint is reused as is. A resumed run reports the same logical
totals as an uninterrupted one (`counts`) and, separately, what was done in this process (`resume`); caps apply to the logical totals.
`scripts/run_b2_a5_pilot_matrix.sh` is resumable at invocation level the same way.

## 12. Exclusions and gates

Not authorized and not started: full B2 generation, full GPU training, full 7×3 LOKO, K18, K17d, OBS-CANCEL/2,
merge. A small passing run proves execution, not robustness. A mask-only result must never be cited as
receiver-consistent. Test-only unknown families (B2-test/1) are outside this slice.

## 13. Change log

| Date | Change |
|---|---|
| 2026-10-23 | Registered before implementation and before any A5 outcome inspection. |
| 2026-10-23 | Post-review clarifications (independent red-team review of the implemented harness, before the final pilot record): `stale_plan` is a formula (initial-draw plan of id-1), not a history, and an invalid replacement is `blocked`; only applicable scenes are replayed and parity-checked; parity wording is conditional on the §5 policy; alarm columns are rates among original-clean/original-event scenes, not false-alarm/detection rates under counterfactuals; the experiment fingerprint also covers the run directory's frozen files and the full source tree; §11a resumability added. No perturbation definition, RNG key, metric definition or cap changed. |
| 2026-10-23 | Implementation clarifications, added after three engineering wiring smokes of the runner (`drop_one`/`co_only` known, `shift_plus`/`cross_only` known, `authorize_intruder`/`both` matched; 4, 2 and 4 scenes; used only to check that the code runs) and **before** the recorded pilot matrix: (a) scope `both` is applicable only when the transformation is applicable to both descriptors; (b) additive observable diagnostics `spec_co_core_db`, `residual_core_db`, `cancellation_depth_core_db` over the bins above -3 dB of the ORIGINAL co-pol mask (fixed across conditions) next to the registered full-band diagnostics, because the full-band ratio is dominated by the noise floor; (c) `original`-condition fields `prediction_change_vs_original` and `max_abs_logit_difference_vs_original` are `null` (trivial); (d) `mask_only_vs_receiver_consistent` reports whether PSD, residual and logits are identical per view. No definition of §3-§9 changed. |

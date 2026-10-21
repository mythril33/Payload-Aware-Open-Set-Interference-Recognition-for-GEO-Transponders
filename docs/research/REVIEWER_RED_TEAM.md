# Independent reviewer red team — B2-feat/1 slice

Date: 2026-10-21. Reviewed commit: `46b13fc`. Reviewer: an independent Claude Code subagent acting
under `.agents/review.md` and `.claude/skills/scientific-review`, read-only, with the brief to find
leakage, role violations, physical/numerical errors, misleading metrics and weak tests. It ran the new
test files (61 + 15 passed), collected the full suite (741) and made several multi-second numerical
probes of the canceller. The integrator (this session) reproduced the key finding and applied the
fixes listed under "Resolution"; the follow-up commit is recorded in DURUM.

## Blockers

None. No simulator-truth leakage into model inputs; frozen roles implemented as stated; B2-base/1
artifacts remain readable with unchanged fingerprints.

## Should fix (all resolved in the follow-up commit)

| # | Finding (reviewer) | Resolution (integrator) |
|---|---|---|
| 1 | **Over-claim "depth is noise-limited".** `obs-cancel/1` fits one complex gain per 42.7 µs snapshot without phase tracking; with the frozen 150 Hz effective LO linewidth the Wiener phase walk caps depth at ≈ 21 dB (reviewer: 9.6 Mbaud QPSK, C/N 25 and 40 dB both ≈ 21 dB; 0 Hz: 30.7 / 44.2 dB). For C/N above ≈ 20 dB the algorithm, not the noise floor, bounds the residual. | Reproduced: 23.8 / 24.9 dB at C/N 25 / 40 with 150 Hz versus 30.7 / 43.8 dB without (different realization). Reworded `docs/results/b2_feat_pilot.md`, P20 §7–§8, DURUM and PROJECT_AUDIT §7; added `test_untracked_phase_noise_caps_depth_independently_of_cn`. `obs-cancel/1` stays frozen (artifacts bound to it); a per-segment phase-tracking `obs-cancel/2` is proposed as a separately versioned stage. |
| 2 | Plan-consistency accuracy reported as 100 % with zero positives in JSON and the table; a constant head scores perfectly. | `_plan_metrics` now returns `accuracy.mean = null` with counts and a note when only one class is present; `report()` prints `n/a (positives n=0 of N; undefined)`. Test added. |
| 3 | `test_checkpoint_selection_ignores_plan_head` was tautological; `fit()` did not expose the chosen epoch. | `fit()` returns `best_epoch` and `best_val_macro_f1` (persisted in checkpoints); the test now asserts `best_epoch == 1` and that the restored weights equal the epoch-2 snapshot. |
| 4 | DURUM and PROJECT_AUDIT linked a non-existent `REVIEWER_RED_TEAM.md`. | This file. |
| 5 | K17b training-time plan-shift augmentation (15 %, Δf ~ U(−0.5, +0.5) MHz) is not implemented and was not listed as missing; P20 §5 read as complete. | P20 §8 and DURUM now state it explicitly; models from the current `b2_experiment` are not the P18 main model. It is the next training-side task. |

## Optional (documented or fixed)

| # | Finding | Resolution |
|---|---|---|
| 6 | Grid-aligned timing: the simulator places symbols on the 288 MHz grid, so timing quantization is never exercised with a fractional offset. | Stated in P20 §8; a fractional-delay test belongs to `obs-cancel/2`. |
| 7 | Welch variance mismatch: channel 5 uses 3072 guarded samples (11 segments) versus 4096 (15) for channel 1. | Stated in P20 §8. |
| 8 | Center-loss centers share the AdamW weight decay, unlike Wen et al.'s separate update. | Stated in P20 §8; frozen convention. |
| 9 | APSK ring start angles "from memory" now feed decisions; self-consistent but unverified against EN 302 307-1. | [VERIFY] kept visible in P20 §8 and PROJECT_AUDIT §8. |
| 10 | `_stage` could raise `KeyError` for a request with `fifth_channel` but no `cancellation`. | Now a `ValueError` with a clear message. |
| 11 | The signature test is a parameter-name check, not a leakage test. | Prose no longer calls it the leakage test; the artifact test asserting the plan passed equals `record["plans"][0]` and the determinism test carry that role. |

## Verified OK (reviewer, abridged)

- No leakage: `b2_dataset._residual` → `cancel_planned_carriers(result.iq[0], plans[0], cancellation)` on
  calibrated co-pol IQ and operator plans rebuilt from `meta["plans"]`; canceller reads only `f0`,
  `symbol_rate`, `alpha`, `mod`, `code_rate`; `geoml.train._inputs` consumes `spec`, `mask`, `residual`;
  diagnostics in `check_b2_cancellation.py` are downstream of the stored residual.
- Roles: selection by known macro-F1 on val-select; Mahalanobis on train; MSP/energy/Mahalanobis and
  clean alarm thresholds on val-calib (known / clean only); test inferred once; `_check_roles` enforces
  frozen ranges and disjointness; reuse bound to checkpoint hash, data fingerprint, groups, source hashes.
- Backward compatibility of the B2-base/1 request layout and fingerprints; cross-stage and corruption
  rejection tested.
- Canceller numerics: SRRC unit energy and RC peak 1.0000, ISI 2e-4; Oerder–Meyr recovers all tested
  offsets; phase sectors match `constellation()`; LS gain absorbs scale and rotation; resampling round
  trip asserted; edge guard adequate down to 1 Mbaud; dB/PSD conventions identical to `spec`; float16
  range safe.
- Metrics: positive classes and denominators stated; `cluster_ci` null with one group; unknown metrics
  null with `n_unknown = 0`; the pilot markdown states that the learning slice is at chance.
- Tests exercise failures (unplanned carrier survives, missing carrier does not raise the residual,
  −25 dB under-carrier becomes visible, corrupt/tampered artifacts rejected, role leakage rejected).

## Open items for the researcher

- K18: confirm the pre-registered center-loss weight 0.005 and plan BCE weight 1.0.
- Decide whether an `obs-cancel/2` with per-segment phase tracking should be pre-registered before the
  full B2 production, since the residual channel is bound to the canceller version.

---

# Independent reviewer red team — B2-test/1, K17b, K17d and open-set evaluation

Date: 2026-10-21. Reviewed commit: `a09429b` (versus `a595484`). Same reviewer role and brief as
above, read-only. The reviewer ran the new test files (54 passed) and executed the pre-refactor
`b2_scenarios.py` side by side with the new one: `prepare_scene` bit-identical over 6 groups × 8 labels
× 3 missing-carrier states (144 cases, 0 mismatches). The integrator reproduced the findings and applied
the resolutions below in the follow-up commit recorded in DURUM.

## Blockers

None. Test-only samples cannot reach weights, checkpoint selection, Mahalanobis fitting or thresholds;
families are restricted to frozen test groups; the test artifact is bound to the known data fingerprint.

## Should fix (all resolved)

| # | Finding (reviewer) | Resolution (integrator) |
|---|---|---|
| 1 | K17d control was distribution-matched, not pair-matched: the downlink ASI used its own RNG namespace, so per group its C/I_psd, carrier and placement differed from the known uplink ASI (e.g. 6.2 vs 26.0 dB), while P18 §7a K17d requires "scenario, plan, link and C/I_psd matched" and the docs said "identical draws". | The downlink family now consumes the known uplink ASI's stream `[group, 1820, 6]`; metadata records the pairing; test asserts equal carrier, geometry and C/I_psd per group. Logged in P18 §10. The other families keep the separate namespace. |
| 2 | `results.md` printed "No unknown families … exist; their metrics are null" and a hardcoded `null (n_unknown=0)` column even when `--unknown-data` was supplied. | Header conditioned on the test-only protocol; the column prints the pooled-near rejection rate. Test asserts the old strings are absent. |
| 3 | `n_unknown` in the compact `open_set` summary counted all non-benign families (8) while pooled AUROC/AP/OSCR used near families only (6). | `n_unknown` = pooled near count, with `n_known`, `n_unknown_equivalence_limited` and `n_unknown_all_families` as separate fields and an explicit `unknown_rejection_denominator`. |
| 4 | K17b augmentation replaced the mask channels only, while the A5 corruption rebuilds the mask and re-runs the full preprocessing, so the carrier-level reference moved at test time but not at train time (median 0.10 dB, p95 0.48 dB, max 0.99 dB). | Selected rows are now re-preprocessed from the raw spectra, residual and shifted masks with `_inputs`, i.e. the same transform as `geoml.plan_shortcut`. Test asserts equality with `preprocess_dual` on the shifted masks. |
| 5 | `docs/results/b2_test_pilot.json` was a hand-trimmed copy without a reproducible rule (`source: null`, 1156 key paths missing, including `unknown_rejection`). | `b2_experiment` writes `results_summary.json` with a fixed `SUMMARY_DROPPED` key list (curves, histories, per-class acceptance, ECE bins, source hashes, generation/calibration/Mahalanobis blocks, confusion); the committed copy is that file, keeping fingerprints, counts, rates and nulls. |
| 6 | Downlink ASI is scaled by the realized feed power (lower after a dropped carrier) while the uplink ASI is referenced to the nominal unit load; P21 called them "the same definition". | Metadata now records `feed_reference_power`, `active_planned_power_co` and `effective_c_over_i_psd_db`; P21 §2 states the ≈ 15 %-of-groups level drift explicitly; the family check reports it. |

## Optional (resolved or documented)

- Dead `mean_delta_psd_cross_db` code in `scripts/check_b2_test_families.py` removed.
- `test_only_alarm` (event-alarm rate on the benign CID control) is now rendered in `results.md`.
- Bernoulli-per-epoch selection and the ≈ 2.7 % of shifted carriers spilling past ±18 MHz are stated in P21 §3.
- A real-chain integration test on one test group now checks that the downlink family raises its band on the co feed, leaves the far spectrum at Welch-leakage level (median < 0.02 dB, max < 0.2 dB) and records the effective level.
- Not changed: `_rate` still returns a degenerate CI with two groups (consider `null` below three groups when K17c slices arrive); `check_b2_test_families.py` has no unit test yet.

## Verified OK (reviewer, abridged)

Role refusal for non-test groups and foreign role directories; binding of groups, configuration,
cancellation setting and calibration to the known artifact; unknown split used only in `infer` after
`fit`; Mahalanobis on train, thresholds on val-calib; K17b applied inside the training loop before
mirror/roll, never to validation (spy test), both feeds together, zero shift within 0.02 dB; downlink and
uplink ASI generators consume the RNG identically; unknown seed derivation valid; CID muting keeps GUIDs;
pre-registered groups match P18 §3; pooled near excludes `wideband_noise` and `cid_overlay`;
`ranking_metrics` called with known test scores as negatives and argmax-correctness before rejection.

---

# Independent reviewer red team — B2-match/1 (K17c matched set)

Date: 2026-10-21. Reviewed state: working tree of `ba98d6b` versus `82d6e7a`. Same role and brief as above,
read-only; the reviewer ran `tests/test_b2_matched.py` (12 passed) and resolved all 150 frozen matched groups
without waveforms to check the pairing, placement, bin and feasibility claims. The integrator reproduced the
findings and applied the resolutions below in the follow-up commit recorded in DURUM.

## Blockers

None in code correctness. The pairing is real: within a group the three variants share link draws
`[g,1801]`, plans (`default_plan(2g)` / `[g,1810,retry]`), activity `[g,1813]`, the full
`DualScenarioConfig`, the carrier/noise streams, the copied calibration and canceller; the matched draw uses
only `[g,1840]`; both events use the same power formula and reference and the same co-uplink injection; the
reader enforces pair equality on read. Over the 150 groups: bins 50/54/46, 4 plan redraws, 46 targets above
the natural unauthorized range, none outside the natural ASI range.

## Should fix (all resolved)

| # | Finding (reviewer) | Resolution (integrator) |
|---|---|---|
| 1 | In 5 of 150 groups the ASI overlaps only a carrier muted by the shared missing-carrier draw (4 fully, 1 partly); observationally an unauthorized-like carrier under a "planned" mask (the K17c "fazla/eksik taşıyıcı" intersection). The pilot report explained group 3300000's smaller ASI rise by planned-carrier power that is not there. The runner did not split by `plan_consistency`. | `matched` block now records `asi_overlap_fraction_plan`, `asi_overlap_fraction_active`, `asi_overlaps_only_absent_carrier` (validated on read); `_matched_metrics` reports pair metrics per `plan_consistency` and for the absent-carrier subset; P22 §3/§7 and the pilot report rewritten (group 3300000's rises differ by the clean-twin level difference, 1.45 dB). Test pins the flag on 3300000 and the retry on 3300002. |
| 2 | "Widest-gap IM floor shift" measured the unauthorized carrier itself (the carrier lay inside the widest gap); the +11.4/+6.1 dB values were interpreted as nonlinear interaction. | The gap is now the widest free gap disjoint from both event bands; shifts are ≤ 0.2 dB in the pilot and the sentence was corrected. |
| 3 | Report column "Pair accuracy (MSP threshold)" was the threshold-free argmax rate. | Renamed "Pair accuracy (argmax, no rejection)"; an "among accepted (MSP)" column added; conventions string states both. |
| 4 | K18 audit cited "three random initializations" but the JSON held single means; quoted the init value where trained checkpoints are an order larger. | Per-seed values recorded (`k18_init_scale.json`); P22 cites both init and trained ranges (sum 6·10⁻⁴ init, 2·10⁻⁴–5·10⁻³ trained; weighted terms ≤ 3·10⁻⁵ and ≤ 4·10⁻⁷). |
| 5 | Narrow-carrier skew understated: matched Rs ≤ 6 Mbaud always (1.0/1.5 Mbaud in 75/150) versus natural ASI 1–28.8 Mbaud; the natural-vs-matched comparison therefore also differs in carrier width. | Stated in P22 §7, in the natural-comparison denominator string and conventions; the physics check writes the matched Rs histogram. |
| 6 | Natural-comparison bin logic untested (fake test role had no `c_over_i_psd_db`); `_pair_metrics` had no direct unit test. | Tests added: bins with values at 7.0, 13.0, 6.99 and 15.0; hand-built predictions with rejected-but-correct, predicted-clean and predicted-other cases. |
| 7 | Placeholders left in DURUM. | Replaced. |

## Optional (resolved or documented)

- Empty-mask `_pair_metrics` now returns the full schema with nulls.
- `SUMMARY_DROPPED` drops the unconditional 3 × 8 `confusion` and the former `bins` key; the conventions key
  was renamed `bin_edges` so it survives, and P22 §4 qualifies what the summary keeps.
- Reader now checks `f_lo`/`f_hi` against the reconstructed carrier edges for both matched events; the
  1e-12 power tolerance covers the log round-trip of `c_over_i_db`.
- Dead code and the precedence-dependent assertion in `tests/test_b2_matched.py` removed; the
  `InfeasibleCarrierError` path of `adjacent_satellite_uplink_at_level` and the plan-retry path are tested.
- Residual wording changed to "within ≈ 1.5 dB".

## Verified OK (reviewer, abridged)

Pairing (see Blockers); same power formula and reference for both events and equality in the pilot JSON;
identical injection stage; role refusal and frozen 150-group cap; bin edges with 13.0 inclusive mirrored in
the natural comparison; thresholds from val-calib only, Mahalanobis from train, nothing fitted on the matched
set; `null` CIs below two groups; reader validations (duplicate (group, label), bin vs metadata, power 1e-12,
geometry null, overlap 0.2–0.8, gap guard, foreign roles, atomic writes, calibration equality); known and
test-only artifacts still verify; K17d audit numbers (78/500, 35 co, median 0.71 dB, p90 2.93 dB, max 5.91 dB)
and K18 arithmetic (D/2 = 64/128) match the recorded JSON.

# Independent reviewer red team — E1 streaming data path (P24)

Date: 2026-10-21. Reviewed state: working tree of `be485d0`…`d3f72ad` on `feature/b2-e1-streaming-loader`
(base `main` `0f75dea`), partly before the results note and the DURUM entry were committed. Same role and
brief as above, read-only; the reviewer ran `tests/test_b2_stream.py` + `tests/test_b2_experiment.py`
(25 passed), a 343-case brute-force search of `_batches` (every sample once, exactly `ceil(N/batch)` steps,
at most one short batch at the end; 0 failures), legacy-versus-streaming parity on the real pilot (single
window identical; `window_shards=1` different, as declared; inference difference 0.0) and the per-shard
re-verification cost on the synthetic fixture (0.18 s per 64-observation shard). The integrator applied the
resolutions below in the follow-up commit recorded in DURUM.

## Blockers

One, already moot when reported: the measurement note `docs/results/b2_streaming_memory.md` and the DURUM
entry were referenced before they were in the tree; both were committed in `d3f72ad` with the JSON records.

## Should fix (all resolved)

| # | Finding | Resolution |
|---|---|---|
| 1 | `fit_streaming` ignored the role carried by a `B2Source`: `test`, `val-calib` or a matched source could be passed as train/val (the runner never did; the legacy `fit` had the same gap). | `_require` now demands kind `known` and role `train` / `val-select` (in-memory sources without a role stay allowed); four role-mismatch cases and a matched source are tested. |
| 2 | Memory model overstated: the raw shard buffer stayed alive through the whole window and, with K17b on, `_window` holds a second contiguous raw copy; docs spoke of a "gathered window copy" that does not exist. | `buffer.clear()` after preprocessing; `del` of the finished shard in `_training_reference` and `infer_streaming`; module docstring, P24 §2 and the profile script's bound formula rewritten to the actual allocation pattern (raw shards during preprocessing, then inputs + one raw copy only when K17b is on). |
| 3 | Multi-window runs are a blocked (shard-window) shuffle, not merely "a different order": batch diversity ≤ `window_shards × groups_per_shard`, paired variants always co-occur, BatchNorm/augmentation streams differ; the production run will be multi-window. | Stated explicitly in the docstring, P24 §5 and the runner's `runtime.loader.note`; `window_shards` declared a recorded engineering choice (experiment fingerprint + checkpoint), default 4 not tuned. |
| 4 | DURUM still described streaming as planned. | E1 implementation appendix added (committed with the results note). |
| 5 | Memory test would crash instead of skip where `/proc/self/clear_refs` is not writable; CLAUDE.md suite time stale. | Subprocess reports `peak_reset`; test skips when the reset failed; CLAUDE.md now says ≈ 5.5 min / 969 tests. |

## Optional (resolved or documented)

- `B2Source.shards` validated indices only after `int()` (booleans slipped through) → type check first; tested.
- "Inference holds one shard" → "one raw shard plus one preprocessed batch, two shards transiently"; `del` added.
- "Bit for bit" qualified: weights, history and reference exact; checkpoint selection identical up to argmax
  ties on 1e-5-level logit differences at inference batch boundaries.
- Per-epoch I/O restated from the measurement: 188 shards ≈ 4.8 GB read twice ≈ 9.5 GB, ≈ 34 s per epoch
  (estimate), replacing the earlier "≈ 7.5 GB".
- The checkpoint's `streaming` block is informational and outside the metadata fingerprint (documented in P24).
- Added tests: single window with `N % batch != 0`; role refusals. Not changed: fixtures imported by module
  name from `test_b2_artifacts` (works under pytest's default import mode; a `conftest.py` is a possible
  follow-up); `_paired_figures` fetches per group (≤ 9 shard reads).

## Verified OK (reviewer, abridged)

No path by which test, val-calib, test-only or matched data reach weights, selection, Mahalanobis statistics
or thresholds through the runner; `_check_roles`, per-source frozen-range and duplicate checks run before
training. Single-window parity holds (generator order, model init, per-sample reference values and float32
mean, `_apply_plan_shift` with batch-local indices, augmentation, scheduler steps, BatchNorm composition).
Every `shards()`/`fetch()` read re-verifies descriptor, sha256, arrays and metadata and compares against the
open-time index; tampering, missing files, missing manifest, swapped order, duplicates and foreign stage/role
fail. No O(N) materialization of spectra remains in the runner. Reader signatures are additive; `window_shards`
is outside `TrainConfig`, so checkpoint configuration checks are unchanged.

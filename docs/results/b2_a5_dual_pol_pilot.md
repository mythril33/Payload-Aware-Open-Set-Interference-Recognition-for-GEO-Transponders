# B2 E4 dual-pol A5 plan corruption — bounded pilot (2026-10-23)

**Evidence class: `BOUNDED_PILOT`.** Contract [P28](../plan/P28_b2_e4_dual_pol_a5.md) (`B2-A5-eval/1`, `B2-A5-plan/1`).
`benchmark_complete=false`. This note documents execution and physical consistency of the harness on two scenario groups
per stage. It is **not** a recognition, robustness or false-alarm result: the frozen checkpoints are chance-level stand-ins.

`FULL B2 PRODUCTION NOT AUTHORIZED — NOT STARTED` · `FULL GPU TRAINING NOT AUTHORIZED — NOT STARTED` ·
`FULL LOKO NOT AUTHORIZED — NOT STARTED` · K18 / K17d / OBS-CANCEL/2 `PENDING_RESEARCHER` · `benchmark_complete = false`.

## 1. What was run, on what, with which identities

| Item | Value |
|---|---|
| Code under test | `7ec5eeeebed96485b71986e30aa0506e9ad2692d` = PR [#17](https://github.com/mythril33/Payload-Aware-Open-Set-Interference-Recognition-for-GEO-Transponders/pull/17) (resumability/driver hardening after review round 2) on top of the E4 harness merged in PR [#15](https://github.com/mythril33/Payload-Aware-Open-Set-Interference-Recognition-for-GEO-Transponders/pull/15) (merge `4b736a6`, implementation `a595bcf`). The same 25-invocation matrix was first run on `a595bcf`; its scientific content (every population, count, displacement and rate) is identical to the one reported here, only hashes and timings differ. Source-tree fingerprint `3428a3257bcfcf63…`; E4 files `b2_a5.py` `ec9fb13e6078…`, `b2_a5_plan.py` `938622a6f558…`, `b2_a5_replay.py` `5bfbb4d188b1…` |
| Environment | container, 4 CPUs, 15 GiB, no GPU; Python 3.13.16, NumPy 2.5.4, SciPy 1.18.1, torch 2.14.1; `OMP_NUM_THREADS=2` |
| Known pilot artifact (`B2-feat/1`) | 2 groups per role (train, val-select, val-calib, test) = 64 observations, generated with `geosim.b2_dataset --config configs/b2_base.json --cancellation configs/cancellation.json --limit-groups 2 --groups-per-shard 1` in 4 min 49 s wall (4.5 s/observation); data fingerprint `6c2b95ed84cc0e51…`, request `87f80561c86b4ec1…` |
| Matched pilot artifact (`B2-match/1`) | 2 groups × 3 variants = 6 observations bound to the known artifact; fingerprint `406166d86becc7e8…` (generation not separately timed) |
| Calibration / cancellation | the artifact's own independent-pilot calibration (`B2-feat/1:87f80561c86b4ec1ade80498eca8ee…`); `obs-cancel/1`, {'srrc_span_symbols': 10, 'phase_grid': 16, 'iterations': 3, 'edge_guard': 512, 'version': 'obs-cancel/1'} |
| Frozen checkpoints | `geoml.b2_experiment --config configs/b2_feat.json` (3 epochs, width 8, K17b plan-shift augmentation on, 16 training observations, 9.6 s), trained on the **unmodified `main` source before any E4 file existed** (training revision `b58c658`): co `c3f2a1e66d9c…`, dual `1c409d45db78…`, dual_residual `10ac1f53472d…`. They are at chance (accuracy 12.5 % on the 16 known test observations) — **stand-ins that exercise the interface**, not trained recognizers |
| Provenance rule exercised | each checkpoint's recorded source files are byte-identical in the tested tree; only the three declared E4 files were added since training (P28 §6) |
| Invocations | 25 separate CLI invocations of `scripts/run_b2_a5_pilot_matrix.sh` (known: `none` + 6 perturbations × 3 scopes; matched: 3 perturbations × 2 scopes), each within the caps (≤2 groups, ≤2 classes, one configuration, ≤16 replays, ≤24 cancellations) |

Machine-readable summary: [b2_a5_dual_pol_pilot.json](b2_a5_dual_pol_pilot.json) (strict JSON; every invocation's `results.json` is
referenced by SHA-256 and `experiment_fingerprint`); full tables: [b2_a5_dual_pol_pilot_tables.md](b2_a5_dual_pol_pilot_tables.md).

## 2. Evidence by class (kept separate)

| Class | What it is | Result |
|---|---|---|
| **A. Synthetic / stand-in fixtures** (unit tests) | deterministic stand-in simulator and canceller on real B2 artifact writers; pure plan tests; leakage / corruption / statistics matrix | 102 E4 tests; see §6 |
| **B. Actual deterministic physical replay** | real payload chain and real `obs-cancel/1`: 90 scene replays (25 invocations) each compared with the stored shard, plus the two real-physics test fixtures (one known test group, one matched group) | **90 / 90 scenes bit-exact**: PSD, masks, residual and the 31-key metadata record equal, maximum absolute difference 0.0 dB (generation and replay on the same machine; cross-machine parity is untested and covered only by the 0.125 dB fail-closed tolerance) |
| **C. Model inference** | frozen stand-in checkpoints, scorers and thresholds on original / MASK_ONLY / RECEIVER_CONSISTENT | wiring and pairing verified; **no recognition information** (§4) |
| **D. Baseline inputs** | EDSC score, planned/blind CA-CFAR statistics and the 26 XGBoost features recomputed per condition | inputs only; no baseline model, threshold or decision exists (P28 §10) |
| **E. Resumption** | real kill-and-resume exercises with SIGKILL | on `a595bcf`: killed after 2 of 4 scenes, the matrix driver resumed it (`resumed 2/4 scenes from verified state; computed 2 now`) and skipped the 3 finished invocations; on the hardened `7ec5eee`: killed after 3 of 4 scenes, resumed (`resumed 3/4 scenes from verified state; computed 1 now`) and the final result equals the uninterrupted matrix run in **every field except** `cost`, `resume` and `reproduction_command` (experiment fingerprint included) |

## 3. Receiver-level results (model independent; RC = `RECEIVER_CONSISTENT`)

Populations: known stage = test groups 3200000–3200001 × {`clean`, `unauthorized`} (4 scenes; `authorize_intruder` applies to the 2
`unauthorized` scenes only); matched stage = test-matched groups 3300000–3300001 × {`adjacent_satellite`, `unauthorized`}. n = 4 or 2
scenes in 2 groups: these are descriptive pilot values, **not** estimates with usable intervals. "Core depth Δ" is the change of the
cancellation depth (observed co-pol PSD over residual) in the bins above −3 dB of the ORIGINAL co mask; "Residual Δ" is the change of the
full-band residual power. Both come from observable data only.

| Invocation | Applied / selected | Replays | Cancellations | Parity exact | Core depth Δ (dB) | Residual Δ (dB) | EDSC score Δ MASK_ONLY / RC (dB) | CFAR planned scenes changed | CFAR blind scenes changed | XGB features changed MASK_ONLY / RC |
|---|---|---|---|---|---|---|---|---|---|---|
| `known_authorize_intruder_both` | 2 / 4 | 2 | 4 | True | -0.00 | -0.87 | +0.00 / -1.17 | 2 | 0 | 3 / 11 of 26 |
| `known_authorize_intruder_co_only` | 2 / 4 | 2 | 4 | True | -0.00 | -0.87 | +0.00 / -1.17 | 2 | 0 | 0 / 8 of 26 |
| `known_authorize_intruder_cross_only` | 2 / 4 | 2 | 2 | True | +0.00 | +0.00 | +0.00 / +0.00 | 0 | 0 | 3 / 3 of 26 |
| `known_drop_one_both` | 4 / 4 | 4 | 8 | True | -6.16 | +6.95 | +0.15 / +7.95 | 3 | 0 | 10 / 15 of 26 |
| `known_drop_one_co_only` | 4 / 4 | 4 | 8 | True | -6.16 | +6.95 | +0.15 / +7.95 | 3 | 0 | 9 / 14 of 26 |
| `known_drop_one_cross_only` | 4 / 4 | 4 | 4 | True | +0.00 | +0.00 | +0.00 / +0.00 | 0 | 0 | 3 / 3 of 26 |
| `known_none_both` | 4 / 4 | 4 | 4 | True | +0.00 | +0.00 | +0.00 / +0.00 | 0 | 0 | 0 / 0 of 26 |
| `known_phantom_both` | 4 / 4 | 4 | 8 | True | +0.00 | -0.24 | +0.29 / -0.06 | 2 | 0 | 10 / 15 of 26 |
| `known_phantom_co_only` | 4 / 4 | 4 | 8 | True | +0.00 | -0.24 | +0.29 / -0.06 | 2 | 0 | 9 / 14 of 26 |
| `known_phantom_cross_only` | 4 / 4 | 4 | 4 | True | +0.00 | +0.00 | +0.00 / +0.00 | 0 | 0 | 3 / 3 of 26 |
| `known_shift_minus_both` | 4 / 4 | 4 | 8 | True | -8.01 | +5.53 | +0.39 / +6.66 | 3 | 0 | 10 / 15 of 26 |
| `known_shift_minus_co_only` | 4 / 4 | 4 | 8 | True | -8.01 | +5.53 | +0.39 / +6.66 | 3 | 0 | 9 / 14 of 26 |
| `known_shift_minus_cross_only` | 4 / 4 | 4 | 4 | True | +0.00 | +0.00 | +0.00 / +0.00 | 0 | 0 | 3 / 3 of 26 |
| `known_shift_plus_both` | 4 / 4 | 4 | 8 | True | -8.19 | +5.53 | +0.39 / +6.63 | 4 | 0 | 10 / 15 of 26 |
| `known_shift_plus_co_only` | 4 / 4 | 4 | 8 | True | -8.19 | +5.53 | +0.39 / +6.63 | 4 | 0 | 9 / 14 of 26 |
| `known_shift_plus_cross_only` | 4 / 4 | 4 | 4 | True | +0.00 | +0.00 | +0.00 / +0.00 | 0 | 0 | 3 / 3 of 26 |
| `known_stale_plan_both` | 4 / 4 | 4 | 8 | True | -12.96 | +9.26 | +2.70 / +12.94 | 4 | 0 | 10 / 15 of 26 |
| `known_stale_plan_co_only` | 4 / 4 | 4 | 8 | True | -12.96 | +9.26 | +2.70 / +12.94 | 4 | 0 | 9 / 14 of 26 |
| `known_stale_plan_cross_only` | 4 / 4 | 4 | 4 | True | +0.00 | +0.00 | +0.00 / +0.00 | 0 | 0 | 3 / 3 of 26 |
| `matched_authorize_intruder_both` | 2 / 4 | 2 | 4 | True | -0.00 | -2.02 | +0.00 / -2.28 | 2 | 0 | 3 / 11 of 26 |
| `matched_authorize_intruder_co_only` | 2 / 4 | 2 | 4 | True | -0.00 | -2.02 | +0.00 / -2.28 | 2 | 0 | 0 / 8 of 26 |
| `matched_drop_one_both` | 4 / 4 | 4 | 8 | True | -8.46 | +5.16 | -0.14 / +5.31 | 3 | 0 | 10 / 15 of 26 |
| `matched_drop_one_co_only` | 4 / 4 | 4 | 8 | True | -8.46 | +5.16 | -0.14 / +5.31 | 3 | 0 | 9 / 14 of 26 |
| `matched_phantom_both` | 4 / 4 | 4 | 8 | True | -0.00 | -0.93 | +0.40 / -0.64 | 2 | 0 | 10 / 15 of 26 |
| `matched_phantom_co_only` | 4 / 4 | 4 | 8 | True | -0.00 | -0.93 | +0.40 / -0.64 | 2 | 0 | 9 / 14 of 26 |

Reading, within those limits:

- **A wrong co-pol plan degrades cancellation exactly where the frozen canceller was told the wrong thing.** ±0.5 MHz shifts lower the core
  cancellation depth by about 8 dB, `stale_plan` by about 13 dB, `drop_one` of a transmitted carrier by 6–8 dB (the dropped carrier stays in
  the residual at about its observed level; real-physics test). `cross_only` never changes any co-pol statistic (the canceller is not invoked).
- **`authorize_intruder` hides the intruder from residual evidence.** Declaring the physical intruder makes the canceller remove it: the
  full-band residual falls (−0.9 dB known, −2.0 dB matched) and the EDSC score falls by 1.2 / 2.3 dB, while the original-core depth is
  unchanged because the intruder lies outside the planned carriers. `MASK_ONLY` cannot show this effect (stored residual).
- **`phantom` adds almost nothing to the residual** (a declared carrier in a free gap only remodulates noise: −0.2 to −0.9 dB full band) but
  changes the mask, hence every plan-relative level.
- **The plan couples into every channel through the normalization.** Rebuilding only the co mask (`MASK_ONLY`, no physical change at all) shifts the
  carrier-level reference, so the co, cross *and* residual band levels of the XGBoost features all move by the same amount (e.g. +2.7 dB
  for `stale_plan`/`co_only`). The neural preprocessing uses the same reference (`level="carrier"`).
- **Blind CA-CFAR is unchanged in all 25 invocations** (0 scenes changed), as it must be: it does not read the plan. EDSC and planned CA-CFAR
  read the co mask; XGBoost reads both masks and the residual (3 of 26 features react to `cross_only`).
- With `RECEIVER_CONSISTENT` the recomputed residual differs from the `MASK_ONLY` (stored) one exactly when the co belief changed
  (64 recomputations in 90 replays; 0 for `none` and every `cross_only`).

## 4. Model-level pairing (stand-in checkpoints; execution evidence only)

150 (invocation × view × condition) cells compare `MASK_ONLY` / `RECEIVER_CONSISTENT` with `original` on the same scenes. The argmax changed in 2
cells (both `known_drop_one_cross_only`, `dual` view, 2 of 4 scenes, |Δlogit| = 0.0059: a near-tie of an untrained network); the largest
logit change anywhere is 0.009. The alarm rate (any non-clean prediction above the stand-in's clean-val-calib threshold) changed in 83 of 246
cells with a defined denominator, because logit shifts of 10⁻³ cross a threshold that these networks hover around. **None of this is a
statement about robustness.** Counterfactual columns are agreement with the original label, not accuracy, and alarm columns are rates among
scenes whose original label is clean / not clean (P28 §7–§8); under `drop_one` or `authorize_intruder` an alarm can be the operationally
correct reading. The full per-view tables are in [the tables file](b2_a5_dual_pol_pilot_tables.md).

Training confound to keep in mind for real checkpoints: the stand-ins were trained with the P18 K17b mask-shift augmentation (15 % of training
samples, ±0.5 MHz, masks only), so `MASK_ONLY` shifts are in-distribution for them while `RECEIVER_CONSISTENT` shifts additionally move the
residual channel, which the augmentation (applied to the stored residual) never did.

## 5. Inconclusive, blocked, not done

- No frozen trained checkpoint exists on `main`; the recognition-level questions of P28 (closed-set agreement, ASI-versus-unauthorized
  confusion under wrong plans, plan-consistency head) remain **open** until compatible checkpoints are supplied (`PLANNED`, authorization gates
  unchanged).
- Baselines: input displacement only. No frozen EDSC/CA-CFAR/XGBoost model or clean-only threshold artifact is available; fitting on a pilot would be
  training (P28 §10).
- Two groups per stage: no interval is meaningful; test-only unknown families (`B2-test/1`) are outside this slice.
- Cross-machine bit-parity untested (same-machine exactness only); numpy/scipy versions of generation and replay are not compared beyond the
  parity check itself.
- Wall time of the matched pilot generation was not separately recorded; the per-invocation `elapsed_s` is the work of that process only.

## 6. Tests, CI and cost (measured, scope stated)

| Measurement | Value |
|---|---|
| E4 test files (`tests/test_b2_a5_*.py`) | 102 tests: plan 25, replay 17 (real physics), eval 22, negative 19, resume 15, summary 4 |
| Local full suite on `7ec5eee` | **1189 passed, 0 failed, 0 skipped reported**, pytest 567.97 s (subprocess 570.16 s), peak child RSS 1 724 880 KiB, exit 0 (on `a595bcf`: 1182 passed, 475.02 s, peak 1 716 256 KiB; main before E4: 1086 passed + 1 environment skip; the +7 since `a595bcf` are the hardening tests; wall times vary with machine load) |
| GitHub Actions, PR head `a595bcf` | run [39947778403](https://github.com/mythril33/Payload-Aware-Open-Set-Interference-Recognition-for-GEO-Transponders/actions/runs/39947778403) / job 120394555595, Python 3.12.15, conclusion **success**: E4 step 95 passed in 116.27 s, remaining suite 1087 passed in 234.45 s. Earlier head `8bedd2b`: run 39946563917 success |
| One replay of one scene | about 5 s (3.0 s simulator + 1.3 s parity cancellation + I/O); each recomputation adds about 1.3 s |
| Pilot matrix | 25 invocations, 90 replays, 154 cancellation evaluations, 64 receiver recomputations, 870 scored samples; sum of in-process elapsed 641 s; about 11–33 s per invocation; peak RSS 1100940 KiB; driver finished with `MATRIX_DONE expected=25 failed=0` |
| Mutation checks (manual) | forcing a stale residual or feeding the cross-pol IQ to the canceller makes the targeted tests fail |

## 7. Independent review

Read-only red-team review, two rounds (round 1 on `8bedd2b`, round 2 on `main@4b736a6`; no blocker, round-2 findings fixed in this PR): [b2_e4_red_team_review.md](../research/b2_e4_red_team_review.md). The hardening itself was not re-reviewed by a third round.

## 8. Reproduction

```bash
source /workspace/.venvs/geosim/bin/activate; export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2
python -m geosim.b2_dataset --config configs/b2_base.json --cancellation configs/cancellation.json \
    --out data/b2-feat-pilot --limit-groups 2 --groups-per-shard 1
python -m geosim.b2_matched_dataset --out data/b2-match-pilot --known data/b2-feat-pilot --config configs/b2_base.json \
    --cancellation configs/cancellation.json --limit-groups 2 --groups-per-shard 1
python -m geoml.b2_experiment --config configs/b2_feat.json --data data/b2-feat-pilot --out runs/b2-feat-pilot   # stand-in checkpoints
scripts/run_b2_a5_pilot_matrix.sh            # resumable; one capped invocation per configuration
python scripts/summarize_b2_a5_pilot.py --runs runs/b2-a5-pilot --out docs/results/b2_a5_dual_pol_pilot.json \
    --markdown docs/results/b2_a5_dual_pol_pilot_tables.md --checkpoint-note "<what the checkpoints are>"
```

Note: the stand-in checkpoints must be trained on a tree whose existing source files are byte-identical to the tested tree (E4 only adds files);
a checkpoint trained after any edit of an existing `src` file is refused by design (regenerate it in a fresh run directory).

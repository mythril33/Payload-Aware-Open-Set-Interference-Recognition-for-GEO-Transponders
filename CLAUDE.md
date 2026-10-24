# CLAUDE.md — Claude Code context for this repository

**Current state (2026-10-24):** E8 decision/resource preparation (P32, NO-GO, nothing approved) sits on main `4a1cc95` (PR #24 merged, exact-head CI 1771 passed / 7 skipped); see the E8 paragraph below.

**E7b execution scope (2026-10-24):** base main
`ed65eb54632fc4373accebc88452ddf0ff9fadfe`, PR22/23 merged. Read
[P31](docs/plan/P31_b2_e7b_isolated_execution.md) for the additive canonical
`train-only` → `calibrate` → `freeze` → `evaluate` modes. Train/val-select
only fit/select; Mahalanobis fits train only; separate known-val-calib
freezes thresholds; the complete three-view × three-seed inventory is
verified before test observations/inference. New execution is CPU-only,
≤2groups/role, ≤2epochs, width≤8, batch≤32. The legacy coupled pilot is
retained with ≤12groups/role. LOKO orchestration plans seven non-clean
holdouts × three seeds × explicit views, while each immutable selection
may execute at most two CPU smoke cells. No unrestricted production or
21/63-fit GPU launch is added. Source hashes change and historical
checkpoints must be refused, never relabelled. Actual E7b validation is
recorded in [delivery evidence](docs/results/b2_e7b_execution.md).

R1–R10 and all29 candidate parameters stay unapproved; consult the
[recommendations](docs/plan/B2_E7B_DECISION_RECOMMENDATIONS.md). Width16
is not authorized by the width8 smoke cap. K18/K17d/OBS-CANCEL/2 remain
pending, full generation/GPU/LOKO remain unauthorized, benchmark_complete=false.
Verified base-head CI is run40047344666/job120731984575 on
`7a46f5774ddcf9f99af425265a6b0cc2b0ebdb57`:107passed106.48s and
1525passed/7skipped716.07s (1632passed total). The raw `-q` log did not
print skip reasons; do not infer their node IDs or causes. Earlier
readiness/count snapshots below are historical, not E7b test evidence.

**Readiness status (2026-10-24, E7a merged, post-merge hotfix):** actual main `0e8c467` contains merged PR #22 (the independent-review hardening of E7a; Actions [run 40035525938](https://github.com/mythril33/Payload-Aware-Open-Set-Interference-Recognition-for-GEO-Transponders/actions/runs/40035525938) on head `8d5bf9b`: 1486 passed, 7 skipped (the historical raw -q log did not identify skip reasons) + E4 step) on top of PR #21 (the first, pre-review E7a state `5903637`; run 40017354368), PR #20 (E6 preflight; run 40004028017: 1333 passed), PR #19 (E5 atlas) and PR #18. E7a adds the fail-closed staged production supervisor ([P30](docs/plan/P30_b2_e7a_production_supervisor.md), `scripts/b2_production_supervisor.py`: dry run by default, known -> test-only -> matched, lock/identity/anchored hash-chained journal, ceilings, heartbeats, first-shard timing gate, interruption, orphan quarantine, completion marker only after a clean supervised attempt; bounded to `--limit-groups` 1..2 - **the production launch is not implemented**), observation-only K18 training diagnostics (`train_diagnostics`, `best_epoch`; training is bit-identical on CPU fp32, GPU parity untested; editing `src/geoml` changes checkpoint source provenance, earlier checkpoints are refused for reuse, never relabelled), a candidate production-training proposal ([not frozen, not approved](docs/plan/B2_E7_TRAINING_SPEC_PROPOSAL.md), decisions R1-R10) and a capped real-physics verification ([2 groups/stage, interrupted and SIGKILLed once](docs/results/b2_e7a_supervisor_verification.md)). The hotfix branch records a second read-only audit of the merged state (P30 section 9). Readiness [checklist](docs/plan/B2_E6_PRODUCTION_READINESS_CHECKLIST.md): PASS 31, FAIL 1 (LOKO dispatcher, out of scope), BLOCKED 15, NOT_RUN 1; full suite 1639 tests. K18/K17d/OBS-CANCEL/2 remain PENDING_RESEARCHER; full generation/GPU/LOKO remain NOT_AUTHORIZED; benchmark_complete=false. Older milestone sections below are historical; consult DURUM's top appendix for current status.


Read `AGENTS.md` first; it holds the binding repository rules. This file adds
navigation, commands and the current milestone. It never overrides frozen
protocols. Progress and final explanations to the researcher are in Turkish;
code, docs and commit messages are in English.

## What this project is

Payload-aware, plan-conditioned, dual-polarization **open-set interference
recognition** for GEO bent-pipe transponders, from operator downlink spectrum
monitoring. Everything is simulation; there is no field data (DURUM §5.5).
Contributions: C1 payload-realistic simulator, C2 plan-conditioned dual-pol
open-set recognition, C3 payload gap under operating conditions.

## Where things are

| Need | Location |
|---|---|
| Honest current status, next step | `docs/plan/DURUM.md` (top appendix = latest) |
| Frozen final benchmark protocol (B2/1, K17) | `docs/plan/P18_b2_protocol.md` — change only via its §10 log |
| B2 artifact stages | `docs/plan/P19_b2_base_observations.md` (B2-base/1), `docs/plan/P20_b2_cancellation_residual.md` (B2-feat/1), `docs/plan/P21_b2_test_families.md` (P21a, B2-test/1), `docs/plan/P22_b2_matched_asi.md` (B2-match/1); the parallel observed-receiver stage is `docs/plan/P21_b2_observed_receiver.md` (P21b, B2-features/1) |
| Production preflight / supervisor | `docs/plan/P29_b2_e6_production_preflight.md` (`scripts/b2_production_preflight.py`: read-only inventory, gates, lock, audit, drill), `docs/plan/P30_b2_e7a_production_supervisor.md` (`scripts/b2_production_supervisor.py`: bounded staged supervisor), `docs/plan/B2_E6_RESEARCHER_DECISION_PACKET.md`, `docs/plan/B2_E7_TRAINING_SPEC_PROPOSAL.md` (candidate, not frozen), `docs/plan/B2_E6_PRODUCTION_READINESS_CHECKLIST.md` |
| Production readiness | `docs/plan/P23_b2_production_readiness.md` (gates, work packages), `docs/plan/P24_b2_e1_streaming_loader.md` (E1 streaming data path, `geoml.b2_stream`), `docs/results/b2_streaming_memory.md` |
| E4 dual-pol A5 plan corruption | `docs/plan/P28_b2_e4_dual_pol_a5.md` (contract), `docs/engineering/B2_E4_CONTEXT.md`, `src/geoml/b2_a5_plan.py` (pure belief corruption), `b2_a5_replay.py` (privileged replay + frozen receiver), `b2_a5.py` (frozen-model paired evaluation), `docs/results/b2_a5_dual_pol_pilot.md` |
| Repository/scientific audit | `docs/research/PROJECT_AUDIT.md` |
| Simulator | `src/geosim/` (`dual.py` chain, `b2_scenarios.py` known / test-only / matched scenes, `b2_dataset.py` / `b2_test_dataset.py` / `b2_matched_dataset.py` artifacts, `cancellation.py` fifth channel; `observed_receiver.py` + `b2_features.py` are the separate P21b stage) |
| Learning | `src/geoml/` (`train.py`, `model.py`, `b2_stream.py` streaming sources/trainer, `b2_experiment.py`, `openset.py`, `mahalanobis.py`, `calibration.py`) |
| Results (small, honest) | `docs/results/*.md` + `.json`; raw data/checkpoints stay out of Git |
| Agent role briefs | `.agents/*.md`; scoped rules `.claude/rules/`; skills `.claude/skills/` |

## Commands

```bash
source /workspace/.venvs/geosim/bin/activate   # or: scripts/setup_cloud.sh (PyPI torch if the PyTorch index is blocked)
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2
python -m pytest -q                            # full suite, ~5.5 min on 4 CPUs (969 tests, 2026-10-21)
python -m geosim.b2_dataset --config configs/b2_base.json --cancellation configs/cancellation.json \
    --out data/b2-feat-pilot --limit-groups 2 --groups-per-shard 1          # B2-feat/1 pilot, ~4 min
python scripts/check_b2_cancellation.py --data data/b2-feat-pilot --out runs/b2-feat-pilot/cancellation_check.json
python -m geoml.b2_experiment --config configs/b2_feat.json --data data/b2-feat-pilot --out runs/b2-feat-pilot
```

## Scientific invariants (short form; details in `.claude/rules/`)

- Model inputs = calibrated spectra, operator plan masks, observation-derived
  cancellation residual. Never activity masks, true IBO/XPD/C-I, labels, event
  parameters or simulator symbols. Oracle cancellation is a labelled upper bound only.
- Roles: train (weights, Mahalanobis) / val-select (checkpoint) / val-calib
  (thresholds, known only) / test (once). All variants of a scenario group share one role.
- Frozen seeds and counts live in `geosim.b2_protocol`; A1, B1/D1/E1-dev, R1-eval and
  B2-base/1 identities must not change. New semantics → new version name.
- Unknown score: larger = more unknown-like. State positive class, denominator, n.
- Strict JSON, `null` + counts for unavailable metrics. Pilots are pilots.

## Current milestone (2026-10-24, through E8 preparation)

All frozen B2/1 data stages exist: B2-feat/1 (known + fifth channel), B2-test/1
(test-only families), B2-match/1 (K17c level-matched ASI ↔ unauthorized).
`geoml.b2_experiment` trains matched co/dual/dual_residual models and, with
`--unknown-data` / `--matched-data`, reports open-set and matched-pair metrics with
frozen thresholds. Pilots are at chance. Production cost is profiled
(`scripts/profile_b2_generation.py`, `docs/results/b2_production_budget.md`).
E1 (P24): the runner streams verified shards (`geoml.b2_stream`, `window_shards` in the
experiment config); single-window runs are bit-identical to the former in-memory path
(`scripts/profile_b2_experiment_memory.py` measures legacy vs streaming).
Blocked on researcher decisions: K18 loss weights, K17d drift handling,
OBS-CANCEL/2, compute authorization for full production and GPU training.
E2 first slice (P25, 2026-10-22): `geoml.b2_loko` plans all A8 folds and supports a capped single CPU smoke fold. Production dispatcher and multi-seed aggregation remain unimplemented.
E3a ([P26](docs/plan/P26_b2_e3a_edsc_baseline.md)): `geoml.b2_edsc` is a bounded E1-streamed binary EDSC baseline using only P20 observed residual evidence and observed carrier normalization, clean-only val-calib thresholds and paired evaluation. Optional CA-CFAR shares the binary metric/calibration interface; neural known-acceptance thresholds are incompatible. No multiclass EDSC predictions or OSCR. See [verification](docs/results/b2_edsc_baseline.md).
E3b ([P27](docs/plan/P27_b2_e3b_xgboost_baseline.md)): `geoml.b2_xgb` streams 26 fixed observation-only features and trains the pinned `xgboost-cpu==3.4.1` baseline. One CPU thread, seed0, one16-round fit, fixed8/16 val-select prefixes; train-only feature normalization, clean-only alarm calibration. Binary `1-P(clean)` shares P26 bundles; actual eight-class decisions and MSP `1-max(P)`/OSCR are separate. Install `.[dev,ml,xgb]`; evidence is in [bounded results](docs/results/b2_xgb_baseline.md).
The optional pinned XGBoost extra requires Python >=3.12; readiness CI uses 3.12, matching the locally validated minor version. Core geosim retains its existing Python requirement.
E4 ([P28](docs/plan/P28_b2_e4_dual_pol_a5.md)): `geoml.b2_a5` evaluates frozen checkpoints/scorers/thresholds against counterfactual **operator beliefs** (shift ±0.5 MHz, drop_one, phantom, authorize_intruder, stale_plan; co/cross/both) while the physical IQ is replayed unchanged. `MASK_ONLY` (stored residual) is only the weaker control; `RECEIVER_CONSISTENT` recomputes the residual with the frozen `obs-cancel/1` from the co-pol IQ and the corrupted co belief, after the `none` replay matched the stored shard. E4 edits no existing source file (checkpoint provenance hashes every `src/**/*.py`; additions are allow-listed). Capped CPU smoke only (2 groups, 2 classes, one configuration, 16 replays, 24 cancellations); counterfactual outputs are agreement with the original label, not accuracy; baselines are input-recomputation only (no frozen baseline artifacts). An interrupted A5 invocation resumes from verified per-scene state (`out/state/`: `B2-A5-scene-state/2` metadata checksum, array checksums, experiment-identity and library-environment binding; modified or foreign state is refused, digests detect accidental modification only), concurrent runs on one `--out` are refused, and `scripts/run_b2_a5_pilot_matrix.sh` (wrapper over `scripts/b2_a5_matrix.py`) re-hands every invocation to the identity-checked CLI, exits non-zero on failed or missing results and records explicit partial coverage; see the resume table in `docs/engineering/B2_E4_CONTEXT.md`.
E8 ([P32](docs/plan/P32_b2_e8_freeze_preparation.md), 2026-10-24): decision/resource preparation only. [B2_E8_DECISION_APPROVAL.md](docs/plan/B2_E8_DECISION_APPROVAL.md) (K18, K17d, OBS-CANCEL/2, R1–R10 recommendations, nothing approved), the UNAPPROVED non-loadable [candidate config](docs/plan/b2_e8_candidate_production_config.json), [host/resource assessment](docs/plan/B2_E8_HOST_RESOURCE_ASSESSMENT.md) (`scripts/b2_e8_budget.py`; the width-8 6 GPU-h figure is withdrawn, width 16 is not budgeted by it), read-only `scripts/b2_host_inventory.py`, the [GPU probe spec](docs/plan/b2_e8_gpu_probe_spec.json) (no executor, nothing run) and the [go/no-go report](docs/plan/B2_E8_GO_NO_GO.md): **NO-GO**. No executor exists for width 16 / 30 epochs / GPU (`src/geoml/b2_execution.py:39` caps; `--device cuda` refused), and `TrainConfig` defaults have `center_loss_weight=0` and `plan_shift_fraction=0` (the P20 values live in `configs/b2_feat.json`). PR #24 exact-head CI: run 40064513568, 1771 passed / 7 skipped.
Remaining code work: production LOKO execution/aggregation and full-scale validation (including A5 on real checkpoints). Research/compute gates remain pending.

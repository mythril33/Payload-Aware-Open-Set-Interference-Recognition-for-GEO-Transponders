# CLAUDE.md — Claude Code context for this repository

**Readiness status (2026-10-23):** E1, bounded E2, E3a, E3b (PR #14, merge `ff81cae1b4e2563cc88271566665e9feae7cd44e`) and bounded E4 (PR #15, merge/current main `4b736a6c425ab532e7c8e1bccc7c906f86ebe0be`) are merged. [P28](docs/plan/P28_b2_e4_dual_pol_a5.md) defines the E4 dual-pol A5 harness (`geoml.b2_a5*`); its post-merge evidence recovery does not restart E4. Remaining work is governed by [P23 B2 Production Readiness](docs/plan/P23_b2_production_readiness.md) and the [bounded master prompt](docs/agent_prompts/B2_PRODUCTION_READINESS_MASTER_PROMPT.md). K18/K17d/OBS-CANCEL/2 remain pending; no full production authorization is implied.


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

## Current milestone (2026-10-23, E4 post-merge evidence recovery)

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
E4 ([P28](docs/plan/P28_b2_e4_dual_pol_a5.md)): `geoml.b2_a5` evaluates frozen checkpoints/scorers/thresholds against counterfactual **operator beliefs** (shift ±0.5 MHz, drop_one, phantom, authorize_intruder, stale_plan; co/cross/both) while the physical IQ is replayed unchanged. `MASK_ONLY` (stored residual) is only the weaker control; `RECEIVER_CONSISTENT` recomputes the residual with the frozen `obs-cancel/1` from the co-pol IQ and the corrupted co belief, after the `none` replay satisfies P28 parity checks. The merged E4 implementation introduced three source modules; post-merge commit `2ee03c5` hardens scene-evidence binding and matrix execution without changing frozen physical/cancellation/perturbation semantics. Checkpoint source identity still fails closed on incompatible state. Capped CPU invocation only (2 groups, 2 classes, one configuration, 16 replays, 24 cancellations); counterfactual outputs are agreement with the original label, not accuracy; baselines are input-recomputation only. An interrupted invocation resumes from verified per-scene state (`out/state/`, bound to the experiment fingerprint; modified state is refused). The matrix always enters the bounded CLI for current provenance validation, retains attempt logs and returns exit 3 for a completed subset; checksum-only skipping is not permitted. See the resume table in `docs/engineering/B2_E4_CONTEXT.md`.
PR #15 head `a595bcfae465e30dd8263cbeb57fae29b7dc9102` passed [CI run39947778403/job120394555595](https://github.com/mythril33/Payload-Aware-Open-Set-Interference-Recognition-for-GEO-Transponders/actions/runs/39947778403/job/120394555595): 95 E4 tests in116.27s plus1087 remaining tests in234.45s, no skips/failures. This is merge-head CI evidence, not a recovery pilot result. The merge lacked the referenced result/review files and the named local pilot artifacts were absent in recovery. The predeclared [execution plan](docs/engineering/B2_E4_POSTMERGE_EXECUTION.json) selects9 of25 invocations before outcomes;16 remain pending even if the selected subset succeeds. Consult the [result note](docs/results/b2_a5_dual_pol_pilot.md) for actual measured recovery status.
Measured recovery:9/25 PARTIAL,16pending,32exact replay parity checks;1220 local tests passed with1existing /proc/self/clear_refs RSS skip. Two summary-only paths changed after that full-suite launch; final affected7tests and independent4cases passed separately. See the evidence note for exact scopes, timing and limitations.
Remaining code work: production LOKO execution/aggregation and full-scale validation (including A5 on real checkpoints). Research/compute gates remain pending.

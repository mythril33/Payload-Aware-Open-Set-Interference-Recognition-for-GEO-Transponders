# CLAUDE.md — Claude Code context for this repository

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
| B2 artifact stages | `docs/plan/P19_b2_base_observations.md` (B2-base/1), `docs/plan/P20_b2_cancellation_residual.md` (B2-feat/1) |
| Separate observed-receiver development | `docs/plan/P21_b2_observed_receiver.md` (B2-features/1, B2-observed-dev/1); `geosim.observed_receiver`, `geoml.b2_observed_experiment` |
| Repository/scientific audit | `docs/research/PROJECT_AUDIT.md` |
| Simulator | `src/geosim/` (`dual.py` chain, `b2_scenarios.py` scenes, `b2_dataset.py` artifacts, `cancellation.py` fifth channel) |
| Learning | `src/geoml/` (`train.py`, `model.py`, `b2_experiment.py`, `openset.py`, `mahalanobis.py`, `calibration.py`) |
| Results (small, honest) | `docs/results/*.md` + `.json`; raw data/checkpoints stay out of Git |
| Agent role briefs | `.agents/*.md`; scoped rules `.claude/rules/`; skills `.claude/skills/` |

## Commands

```bash
source /workspace/.venvs/geosim/bin/activate   # or: scripts/setup_cloud.sh (PyPI torch if the PyTorch index is blocked)
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2
python -m pytest -q                            # full suite, ~70 s on 4 CPUs
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

## Current milestone (2026-10-21)

B2-feat/1 stores the fifth channel; `geoml.b2_experiment` trains matched
co/dual/dual_residual models with an independent `plan_consistency` head and
frozen center-loss weight 0.005 (pre-registered, see P20). Next: test-only
families (`pulsed`, `intermittent_bursts`, `adjacent_satellite_downlink`,
`cid_overlay`, `wideband_noise`) and the matched ASI set, then full
production in the cloud and training on the researcher's GPU.

P21 preserves those P20 APIs and adds a separately named receiver/streaming
training stage, including 15% model-mask jitter. Its two-logit auxiliary CE and
mean-over-features center weight 0.01 differ from P20's BCE/summed loss. Do not
interchange configs, artifacts or reports, or treat the tiny pilots as a receiver
comparison. Full operator-plan-error tests still require recomputed residuals.
Read DURUM's newest appendix before choosing or extending either runner.

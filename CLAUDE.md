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
| B2 artifact stages | `docs/plan/P19_b2_base_observations.md` (B2-base/1), `docs/plan/P20_b2_cancellation_residual.md` (B2-feat/1), `docs/plan/P21_b2_test_families.md` (B2-test/1) |
| Repository/scientific audit | `docs/research/PROJECT_AUDIT.md` |
| Simulator | `src/geosim/` (`dual.py` chain, `b2_scenarios.py` known + test-only scenes, `b2_dataset.py` / `b2_test_dataset.py` artifacts, `cancellation.py` fifth channel) |
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

## Current milestone (2026-10-21, third slice)

B2-feat/1 stores the fifth channel; B2-test/1 adds the five test-only families
bound to a known artifact; `geoml.b2_experiment` trains matched
co/dual/dual_residual models (independent `plan_consistency` head, center-loss
weight 0.005, K17b plan-shift augmentation 15 % / ±0.5 MHz) and, with
`--unknown-data`, reports per-family open-set metrics. Pilots are at chance.
Next: the matched ASI ↔ unauthorized set (K17c, `test-matched` generator), LOKO
(A8), EDSC baseline, then full production in the cloud and training on the
researcher's GPU. K18 (center-loss weight) awaits researcher confirmation.

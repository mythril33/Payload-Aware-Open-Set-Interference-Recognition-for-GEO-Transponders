# P23 — B2 Production Readiness: bounded engineering plan and researcher gates

**Date:** 2026-10-21  
**Starting point:** `main` at `ff1418f2936c5c01c1f171c38c6804b9023cd064` (PR #7 merged).  
**Status:** **PROPOSED PLAN, NOT AN IMPLEMENTED OR APPROVED BENCHMARK.** This document records the latest researcher/agent work plan; it does not modify frozen P18 or authorize full production.

## Source of truth and provenance

Read [AGENTS.md](../../AGENTS.md), [CLAUDE.md](../../CLAUDE.md), [DURUM](DURUM.md), frozen [P18](P18_b2_protocol.md), [P19](P19_b2_base_observations.md), [P20](P20_b2_cancellation_residual.md), [P21a](P21_b2_test_families.md), [P21b](P21_b2_observed_receiver.md), [P22](P22_b2_matched_asi.md) and [production budget](../results/b2_production_budget.md) before edits. P21a and P21b are distinct development stages; do not silently exchange their data formats, receiver algorithms or loss conventions. Any protocol change requires a new version and P18 §10 entry **before** test evaluation. This document is a transcription/implementation plan of recent discussions; it is not evidence of a newly executed experiment.

## Verified repository baseline versus open work

| Area | Current evidence at starting commit | Next requirement |
|---|---|---|
| Eight known classes / B2-feat/1 | Simulator, observation-derived cancellation residual and 2/4/5-channel interfaces exist | Memory-bounded end-to-end loader for canonical `geoml.b2_experiment` |
| Test-only B2-test/1 / K17b | Frozen unknown/CID test roles, plan jitter and integrity checks exist | Do not leak held-out variants into training or calibration |
| K17c B2-match/1 | Level-matched ASI vs unauthorized stage, test-only matched evaluation, physics pilot and production profile merged in PR #7 | Treat matched data as test only; keep natural and intervention distributions separate |
| Evaluation | MSP, energy, Mahalanobis, known-only calibration; 955 tests reported after B2-match/1 review | LOKO A8, EDSC and engineered-feature XGBoost baselines, full A5 dual-pol plan-error tests, CI |
| Evidence | Tiny pilots are at chance; full benchmark explicitly incomplete | Real scientific evidence requires approved production and separate analysis |

**Do not infer** trained full-scale model performance, robustness, completed LOKO, or successful CI from an implementation plan. The reported 955 tests are historical repository evidence, not a fresh test run by this documentation-only change.

## Decision gates — stop before any full generation or GPU training

| Gate | Evidence and proposed disposition | Status / authority |
|---|---|---|
| **K18 — loss convention** | P22 §6: P20 uses `0.005 × sum_d squared-distance`; P21b uses `0.01 × mean_d squared-distance` (D/2 scaling difference). Proposed: preserve P20's pre-registered **sum, 0.005** and BCE **1.0**, log center/CE ratio on train only, no parameter search or test feedback. | **PENDING RESEARCHER APPROVAL** |
| **K17d — downlink ASI level drift** | 35 of 500 held-out groups have missing co-feed carrier; median 0.71 dB, max 5.91 dB drift (P22). Proposed: retain frozen K17d, report affected 35 as labeled sub-row plus predeclared sensitivity; `B2-test/2` only after new approval/version. | **PENDING RESEARCHER APPROVAL** |
| **OBS-CANCEL/2 — phase tracking** | `obs-cancel/1` has ≈21–25 dB depth ceiling at 150 Hz effective linewidth. Proposed separately versioned 64–128-symbol phase tracker: synthetic depth ≥35 dB at 150 Hz/CN 40 dB; gap-floor shift ≤0.1 dB; no P20 paired-CuC visibility regression; runtime ≤2×; no test-family tuning. Not implemented. | **PENDING RESEARCHER APPROVAL** |
| **Full generation budget** | Estimated 21,350 observations, ≈23–30 hours single-process, ≈8.7 GB artifacts outside Git (P22/budget); estimates are not bookings. | **NOT AUTHORIZED** |
| **Full multi-seed GPU/LOKO** | Hardware, runtime, storage and thresholds need explicit approval. | **NOT AUTHORIZED** |

A gate's proposal is **not** approval. Record the researcher's explicit decision and timestamp, or mark `BLOCKED`. Small smoke fixtures, unit tests and measured bounded pilots are allowed; do not start full B2 generation, full 3-seed training, all-class LOKO, production GPU runs, auto-merge or non-versioned protocol changes without authorization.

## Engineering work packages (recommended PR-sized slices)

### E1 — Streaming/memory bounded canonical B2 loader

- Audit `geoml.b2_experiment`, `geoml.b2_data`, B2 artifact manifests, group/role checks, and the *separate* shard-streaming P21b stage. Build a canonical loader that iterates validated shards/groups without eagerly expanding all float32 tensors. Do **not** replace the P20 canceller with the P21b receiver.
- Preserve `train`, `val-select`, `val-calib`, `test`, `test-matched` boundaries, paired-group integrity, view/reference normalization, fifth-channel source provenance, deterministic epoch shuffling and model/checkpoint signatures. Scorers fit **train** embeddings only; calibration sees known-only **val-calib**.
- Unit tests: in-memory vs streaming value parity and output parity on small approved fixtures; single group crossing a shard; last partial shard; deterministic batch order; nonfinite/duplicate/corrupt/checksum-mismatched/foreign-role/foreign-stage fail-closed; memory ceiling measured, no unbounded concatenation. Add a compact memory benchmark with measured peak RSS.
- The loader must be backward-compatible with existing versioned P20 artifacts; if impossible, use a new stage and report the incompatibility rather than masking it.

### E2 — LOKO (A8) protocol and execution

- Leave one known interference class out per run (**seven non-clean classes**), keep `clean` known, and prevent the held-out class from *any* weights, checkpoint selection, Mahalanobis fit or known-only threshold calibration. Do not contaminate roles by group or label remapping.
- Produce deterministic planned splits/config fingerprints, empty/null with counts rather than fabricated metrics. Unknown-positive AUROC/AP/OSCR, acceptance/rejection at frozen val-calib threshold, per-left-out-class metrics and CIs with group-aware resampling; write the *exact* definition of denominators.
- Test 1–2 group fixtures and integrity checks only until full-scale approval. A8 multi-seed execution is authorization-gated.

### E3 — Strong baselines

- **EDSC:** energy detection **after the same observation-derived cancellation** and matched observation grid; use a val-calib clean-only threshold at frozen Pfa 5%, not simulator truth or oracle cancellation.
- **XGBoost:** deterministic expert features from calibrated co/cross spectra, operator plans and optional **observed** residual only; no true plan activity, symbols, IBO, XPD, event geometry, class metadata or test thresholds. Add the dependency explicitly and pin in the reproducibility manifest.
- Use shared role/seed/budget conventions and independent fit/calibration; avoid data leakage and hyperparameter search on tests. Comparisons against CA-CFAR, MSP/energy/Mahalanobis should have n, uncertainty and paired scenario-group definitions.

### E4 — Full A5 dual-pol operator-plan corruption

**Status (2026-10-23): bounded harness implemented** — [P28](P28_b2_e4_dual_pol_a5.md), `geoml.b2_a5*`, tests `tests/test_b2_a5_*.py`; capped CPU pilot only, checkpoints are chance-level stand-ins, no production authorization implied (see [results](../results/b2_a5_dual_pol_pilot.md)).

- Go beyond the existing A1 mask-only shortcut. Perturb **both** operator plan descriptors and reconstruct both masks under shifts (±0.5 MHz), dropped carrier, phantom carrier, and unauthorized-as-authorized cases as applicable. On the 5-channel path **recompute the observation-based cancellation residual from the perturbed plan**; merely altering saved masks is an explicitly labeled weaker control.
- Freeze checkpoints/calibrators, do not retrain on tests, never modify the physical received observation, preserve group IDs and prohibit simulator-truth inputs. Test independent perturbation of co/cross plans and confirm changed residual/unchanged observation, provenance and deterministic replay.

### E5 — GitHub Actions, scientific quality and reproducibility

- Start with lightweight automated installation + existing `pytest` suite, **not** data production or model training. Additional jobs: artifact corruption/role isolation, known-only calibration checks, deterministic replay, metric denominators, strict JSON, cancellation provenance, matched-bin edges, and leak/negative controls.
- Fail CI on missing required checks; no automatic fallback to `benchmark_complete=true`. Stage smoke tests under tight CPU/time/data caps and do not store generated data/checkpoints in Git.
- Record environment, seed, version/fingerprint, command, elapsed/peak RSS, pass/fail and scientific limitations. Red-team the diff independently and resolve critical comments before requesting review.

## Delivery / acceptance

1. One or more **new feature branches and draft PRs against current `main`**; use normal fast-forward pushes, never force-push, never merge or mutate frozen protocols silently. Start with E1, then E2–E5 as separable reviewable slices.
2. Provide code, focused tests, guarded smoke runs, documented exact commands, and a summary of tests **actually executed** (distinguish them from baseline's historical 955).
3. Update `docs/plan/DURUM.md` **when implementation actually lands**, not for planning alone. Put scientific/evidence caveats in `docs/results/` and immutable decision records alongside P23.
4. PR checklist: role/leakage, scientific metrics and group bootstrap, reproducibility/provenance, backward compatibility, bounded resources, CI status, independent review, explicit unresolved decision gates, and `benchmark_complete=false`.
5. Hand the researcher a **Turkish** update distinguishing completed engineering, approved decisions, pending approvals, and what was **not run**.

See the [agent execution prompt](../agent_prompts/B2_PRODUCTION_READINESS_MASTER_PROMPT.md) and [machine-readable gates](b2_readiness_gates_2026-10-21.json).
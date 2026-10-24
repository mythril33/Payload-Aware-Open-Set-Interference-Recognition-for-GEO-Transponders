# P23 — B2 Production Readiness: bounded engineering plan and researcher gates

> E7a current-status update (2026-10-23): PR #20 (E6) merged as `755b474` (Actions run 40004028017: 107 E4 + 1226 other = 1333 passed); E7a followed as PR #21 (`5d3f1a3`) and PR #22 (`0e8c467`, run 40035525938: 1486 passed, 7 skipped + E4 step). E7a added the bounded [production supervisor (P30)](P30_b2_e7a_production_supervisor.md), observation-only K18 diagnostics and a candidate (not frozen) [training proposal](B2_E7_TRAINING_SPEC_PROPOSAL.md); gates and benchmark_complete=false are unchanged.

> E6 current-status update (2026-10-23): PR #19 (E5) merged as `59ed11d`; exact-head Actions run 39991726439 (head `7108ee8`) passed 107 E4 + 1132 other tests; the E5 PR text still said 'pending'. The E6 draft adds the read-only [production preflight](P29_b2_e6_production_preflight.md), a [decision packet](B2_E6_RESEARCHER_DECISION_PACKET.md) and a [readiness checklist](B2_E6_PRODUCTION_READINESS_CHECKLIST.md); gates and benchmark_complete=false are unchanged.

> E5 current-status update (2026-10-23): PR #18 merged as `79a17cc`; raw Actions run39967494290 logs confirm107E4+1121other tests passed. Unified evidence is complete25/25; the9/25recovery remains a separate historical fixture. See [E5 execution plan](B2_E5_PRODUCTION_EXECUTION_PLAN.md) and the E5 scientific atlas/review. Earlier recovery/implementation snapshots below are historical, not current merge/CI/coverage status. Research/compute gates and benchmark_complete=false are unchanged.


**Date:** 2026-10-21  
**Starting point:** `main` at `ff1418f2936c5c01c1f171c38c6804b9023cd064` (PR #7 merged).  
**Status (updated 2026-10-23):** Bounded E1/E2/E3a/E3b/E4 engineering has merged; the full benchmark remains incomplete and unapproved. The original plan and its starting-point evidence are retained below. Post-merge E4 evidence recovery is a separate bounded task; this document does not modify frozen P18 or authorize full production.

## Verified post-merge status (2026-10-23)

- E3b [PR #14](https://github.com/mythril33/Payload-Aware-Open-Set-Interference-Recognition-for-GEO-Transponders/pull/14) merged as `ff81cae1b4e2563cc88271566665e9feae7cd44e`.
- E4 [PR #15](https://github.com/mythril33/Payload-Aware-Open-Set-Interference-Recognition-for-GEO-Transponders/pull/15) merged as verified current main `4b736a6c425ab532e7c8e1bccc7c906f86ebe0be`. At recovery start its PR body described work in progress; the verified merge and raw Actions evidence supersede that historical wording.
- Exact E4 head `a595bcfae465e30dd8263cbeb57fae29b7dc9102`, [run39947778403/job120394555595](https://github.com/mythril33/Payload-Aware-Open-Set-Interference-Recognition-for-GEO-Transponders/actions/runs/39947778403/job/120394555595): **95 E4 tests passed in116.27s and1087 remaining tests passed in234.45s**, no skips or failures. Checkout was synthetic merge `2d570bf26e99e94325a543d4da3cdcbb82c399d4`; CPython3.12.15. This historical CI is separate from post-merge validation.
- The merge referenced pilot/review files that were absent from its tree. Recovery therefore verifies or recreates only the documented small fixture, preserves the merged implementation, and publishes measured evidence separately. [The predeclared recovery plan](../engineering/B2_E4_POSTMERGE_EXECUTION.json) selects9 of25 capped invocations before outcomes;16 unselected invocations remain pending. A completed selected subset is **partial coverage**, never a complete matrix or a robustness result. Actual measurements belong in the [pilot report](../results/b2_a5_dual_pol_pilot.md) and [independent review](../research/b2_e4_red_team_review.md).
- Post-merge reliability hardening (`2ee03c5`) binds scene evidence, propagates Python failures with per-attempt logs, validates current provenance through the bounded CLI before any reuse, and distinguishes full completion from partial/missing/blocked coverage. P18/P20/P28 physical semantics and every researcher decision remain unchanged; `benchmark_complete=false`.
- Measured recovery subset:9/25 PARTIAL,16pending,32exact applicable-scene parity checks;32replays/56cancellations in272.103641s, maximum process RSS742884KiB. Local full regression:1220passed+1environment RSS skip718.13s; final summary-only changes were covered by7affected tests and4independent cases after the full-suite launch. Exact new-PR-head CI remains separate evidence in that PR.

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

**Status (2026-10-23): bounded harness merged in PR #15; post-merge scientific evidence recovery is separate** — [P28](P28_b2_e4_dual_pol_a5.md), `geoml.b2_a5*`, tests `tests/test_b2_a5_*.py`. The predeclared recovery pilot covers9 of25 invocations with tiny CPU stand-in checkpoints; unselected coverage remains pending. Its actual status and measurements are in the [partial recovery record](../results/b2_a5_postmerge_partial_pilot.md). A later, separate record on the unified code covers the complete 25-invocation inventory (`COMPLETE 25/25`, 90 exact parity checks, tiny stand-in checkpoints): [results](../results/b2_a5_dual_pol_pilot.md). Neither carries a recognition/robustness or production claim.

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

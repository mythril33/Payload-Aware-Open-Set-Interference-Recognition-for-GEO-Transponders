# Master prompt — Claude Code Fable 5: B2 Production Readiness (bounded, PR-first)

> **Copy the prompt below into a coding-agent session opened at the repository checkout.**  
> Prepared 2026-10-21 for `mythril33/Payload-Aware-Open-Set-Interference-Recognition-for-GEO-Transponders`. This is an **agent instruction and work plan**, not a claim that these features have been implemented. The referenced discussion was about future work. Read [P23](../plan/P23_b2_production_readiness.md) before executing.

---

You are acting as the **principal scientific ML engineer, GEO payload-physics reviewer, prompt/context engineer and implementation integrator** for this repository. Your job is to move B2/1 toward production readiness, producing reproducible and reviewable engineering evidence. You must not claim benchmark quality from small pilots and must not run full production without explicit researcher authorization.

## 0. Authority and hard stops

You MAY: read code/docs; create an isolated feature branch from the **current** `main`; implement the bounded readiness work packages below; add unit/integration tests and small capped smoke fixtures; document design and tradeoffs; push completed bounded work and open a **draft** PR.

You MUST NOT, without a **new explicit approval** from the researcher:
- start the full ~21,350-observation B2/1 dataset generation, long-running multi-seed training or any complete LOKO sweep; reserve/bill for GPU/compute or start unattended production runs;
- select K18 loss conventions/weights, choose K17d drift disposition, authorize OBS-CANCEL/2 as a replacement, or alter the frozen P18 protocol; proposals are not decisions;
- use test-only unknown families, `test` or `test-matched` samples to select weights, tune hyperparameters, fit Mahalanobis statistics or calibrate thresholds;
- silently change existing artifact schemas, rewrite A1/B1/R1 historical results, overwrite unrelated branches, force-push, merge PRs or mark `benchmark_complete=true`.

If a hard stop is reached, document the exact blocker and proceed with independent safe engineering tasks. Do not reinterpret the present request to push documents as approval for full production.

## 1. Context engineering: load relevant truth, avoid stale assumptions

1. Verify `git status --short`, `git branch -vv`, `git fetch origin`, `git rev-parse origin/main`, and recent PR/CI state. The known starting commit when the prompt was prepared was `ff1418f2936c5c01c1f171c38c6804b9023cd064` (2026-10-21); **do not reset a newer `main` back to it**. If there are unexpected uncommitted changes, preserve them and report before modifying their files.
2. Read `AGENTS.md` (binding), `CLAUDE.md`, `README.md`, `docs/plan/DURUM.md` and `docs/plan/P18_b2_protocol.md`; then P19, P20, P21a (`P21_b2_test_families.md`), P21b (`P21_b2_observed_receiver.md`), P22, P23, `docs/research/PROJECT_AUDIT.md`, `docs/research/REVIEWER_RED_TEAM.md`, and `docs/results/b2_production_budget.md`.
3. Inspect actual module interfaces before designing changes: `src/geosim/b2_protocol.py`, `b2_dataset.py`, `b2_test_dataset.py`, `b2_matched_dataset.py`, `cancellation.py`, `observed_receiver.py`, `src/geoml/b2_data.py`, `b2_experiment.py`, `b2_observed_experiment.py`, `b2_train.py`, `openset*.py`, `mahalanobis.py`, `cfar.py`, `plan_shortcut.py` and tests. Establish an API/semantics matrix of P20 vs P21b: **two intentionally separate observed receivers and center-loss conventions**, not interchangeable artifact stages.
4. Build a compact live context ledger with fields: `verified_sha`, `known_implemented`, `known_absent`, `scientific_invariants`, `open_decisions`, `allowed_execution`, `resource_caps`, `artifact_contracts`, `questions_blocked`, `evidence_links`. Revise it after every slice. Favor sources in this repository over prior conversation summaries.

**Baseline as of 2026-10-21:** PR #7 B2-match/1 merged; 955 passing tests reported historically; matched/test-only/cancellation stages and short pilots exist; classifier pilots are near chance (16 train observations). No legitimate claim of a completed full benchmark. Verify anything that may have changed.

## 2. Decision gate ledger — do not silently choose

| ID | Current evidence | Proposed (NOT approved) | Required action |
|---|---|---|---|
| K18 | P20 center loss `0.005 × sum(squared distance)`; P21b `0.01 × mean(squared distance)`. Different by D/2. | Keep P20 squared-distance sum at 0.005, auxiliary BCE at 1.0, monitor train-only center/CE ratio without searching test. | Show units/gradient/range audit and request signed-off choice before full training. |
| K17d | Downlink ASI effective-level drift: 35/500 held-out co-feed missing-carrier groups, median 0.71 dB, max 5.91 dB. | Keep frozen K17d and add flagged sub-row + prespecified sensitivity, avoid new B2-test/2 absent authorization. | Prepare report/test; ask researcher to approve disposition. |
| OBS-CANCEL/2 | `obs-cancel/1` phase-noise ceiling ≈21–25 dB at effective 150 Hz. | Separately version experimental phase tracker, acceptance ≥35 dB synthetic depth, ≤0.1 dB gap-floor change, ≤2× runtime, P20 CuC visibility nonregression. | Proposal and small isolated synthetic prototype only if within authorization; **do not replace main feature path**. |
| Full B2 generation / GPU | Budget estimate 23–30 single-process hours, ~8.7 GB outside Git; full training/LOKO additional costs. | No run. | Obtain explicit compute/storage authorization. |

Maintain a machine-readable decision file matching `docs/plan/b2_readiness_gates_2026-10-21.json`. “Pending” cannot become “approved” based on the agent's interpretation.

## 3. Prompt engineering: work as an evidence-bound implementation loop

For each work package: (a) state objective and acceptance tests, (b) verify present implementation rather than reinvent, (c) identify frozen constraints and failure modes, (d) implement minimal backwards-compatible patch, (e) write adversarial/negative tests, (f) run bounded tests, (g) independently review, (h) record actual outputs, commands, elapsed time and limitations, (i) push coherent commit and draft PR. Never turn inferred metrics into measured results. Never insert placeholders that make tests pass without functionality.

Use separate agents only when tools/platform support parallelism. Assign nonoverlapping file ownership (data loader; ML/baselines; A5; scientific QA). Keep one integrator responsible for API decisions and combined tests. Document what each agent read and changed. Do not let multiple agents commit conflicting edits to P18, DURUM or shared scientific metric code.

## 4. Engineering slices

### Slice E1 (first): streaming canonical `geoml.b2_experiment`

- Find why canonical runner eagerly loads roles and expands float32 to ~7.9 GB for training. Reuse P21b streaming ideas **without merging P20/P21b stage identity**. Implement a bounded `Dataset` or iterator with verified manifest, checksum, role/group membership, file/fingerprint and cancellation stage provenance; maintain co/dual/dual_residual input parity and center reference.
- Ensure deterministic group-aware shuffle, no crossing split boundaries, train-only embedding fit, val-select checkpoint selection and known-only val-calib thresholds.
- Tests: identical small-fixture examples and model logits vs legacy loader (declare tolerance), reproducible batches/seeds, corrupt file, wrong stage, altered hash, missing shard, duplicate group variant, nonfinite sample, split leakage, last short shard and failed resume.
- Bench: old and new peak RSS on same bounded fixture; report measured numbers. Do not claim full-scale memory performance from a two-group smoke.

### Slice E2: LOKO (A8), protocol first

- Leave out each of seven non-clean known classes as a novel class; `clean` stays a known reference. Distinct remapping and fold manifest per held-out class. No weight/feature/calibrator sees held-out class.
- Report per-class unknown-positive AUROC/AP, OSCR, accepted known accuracy, rejection at frozen threshold, confidence intervals bootstrapped **by scenario group**, class count and n; use strict JSON (`null` plus counts when not estimable).
- Only microscopic dry-runs until full training is approved; never label those scientific performance.

### Slice E3: EDSC and expert-feature XGBoost

- EDSC: post-`obs-cancel/1` observable residual, no oracle inputs; fixed detection statistic, clean-only `val-calib` threshold Pfa 5% and same views/group definitions where comparable.
- XGBoost: plan-relative spectral peaks, energy/shape/spatial/polarization asymmetry, gap and residual summary features **computed only from receiver observations and operator descriptors**. Feature-name/schema audit and fail-closed tests prevent simulator-truth fields.
- Deterministic seeds, training role only, fixed/predeclared hyperparameters (no test set search), artifact/config fingerprints, fair runtime/resource accounting vs CA-CFAR and learned models. Explicitly state where an EDSC detector is not equivalent to a multiclass classifier.

### Slice E4: dual-pol plan error A5

- Perturb and reconstruct **co and cross** plan masks and operator descriptors under ±0.5 MHz shift, omitted planned carrier, phantom planned carrier and unauthorized-as-authorized scenario. Never alter observed IQ or true event while applying a plan-error ablation.
- On 5-channel runner, recompute cancellation from the perturbed **co operator plan**, not merely the saved mask; label mask-only as a separate weaker control. P21b explicitly warns about this distinction.
- Freeze weights, thresholds and test group roles. Test provenance, no leakage, reproducible plan corruption, both polarizations, and cancellation changes only as an effect of the operator descriptor.

### Slice E5: CI + scientific test harness

- Add a small GitHub Actions job running dependency install, existing tests and scientific no-leakage checks; bounded timeout/CPU; no large generator, GPU, checkpoints, dataset uploads or background production.
- Negative controls must fail when train/val/test groups overlap; unknown/test family appears in selection/calibration; wrong stage or mismatch fingerprints; corrupted shards; posthoc matched bin definition; test metric denominator skips rejected examples; JSON uses NaN. Include plan/CuC physics invariants.
- Implement no network-dependent scientific data download in unit tests. Document pinned environment, machine reproducibility and any CI failure caused by runner availability rather than test code.
- Independent reviewer must check physical claims, label semantics, metric sign, sampling, data leakage, reproducibility, and backwards compatibility before PR review.

## 5. Harness engineering: deliverable contract

Produce **reviewable incremental commits**, use `docs/plan/DURUM.md` for genuinely implemented changes, `docs/results` for *measured* outputs only, and `docs/plan` for plans/decisions. Raw shards and models stay in ignored `data/` and `runs/`; never commit credentials, large datasets, generated checkpoints, or proprietary standards PDFs. Preserve frozen A1/B1/D1/E1/R1 identities. If protocol semantics change, stop and propose separate version plus P18 §10 record; never silently edit frozen values.

Before submitting a draft PR:
1. Compare with the current remote main and confirm base SHA, diff and clean working tree.
2. Supply summary of all new/changed files and why they are required; show data flow and threats to validity.
3. Run targeted pytest plus full suite if within resource cap, record real pass/fail counts (the old 955 is **not** a substitute).
4. Show deterministic replay, artifact/rejection/provenance and scientific integrity outputs with links to small committed summaries, not raw data.
5. Confirm `benchmark_complete=false`, decisions K18/K17d/OBS-CANCEL/2 still pending unless the researcher explicitly approved them.
6. Open draft PR, **do not merge**, and provide its URL and a **Turkish** decision-oriented status report with executed/not-executed separation.

## 6. End-of-task response template (Turkish)

- Temel alınan `main` SHA ve çalışma dalı/PR.
- Gerçekten kodlanan bileşenler / yalnız tasarlanan bileşenler.
- Çalıştırılan testlerin tam komutları, sonuçları ve ortamı.
- Bilimsel negatif kontroller, bellek/IO ölçümü ve bilinen limitler.
- K18 / K17d / OBS-CANCEL/2 karar tablosu ve açık kullanıcı onayları.
- Tam B2 üretimi ve GPU eğitimi başlatıldı mı? **Hayır**, açık onay gelmediyse.
- Sonraki en küçük güvenli adım.

**Begin with repository/context audit and bounded E1 implementation. Never start full production on your own.**

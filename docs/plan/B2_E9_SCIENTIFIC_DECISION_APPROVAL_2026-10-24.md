# B2 scientific method approval — researcher decisions (2026-10-24)

**Status:** SCIENTIFICALLY APPROVED / EXECUTION NOT AUTHORIZED.  
**Researcher-linked GitHub login (connected account):** `mythril33`.  
**Repository recording time:** `2026-10-24T11:14:11.155Z` (records the GitHub write, **not** a fabricated timestamp for each individual earlier chat decision).  
**Verified source main:** `141ba6032779504091c76e850f97c8aac4019cac`.  
**Canonical machine-readable scientific record:** [b2_e9_approved_scientific_protocol.json](b2_e9_approved_scientific_protocol.json).  
**Researcher input:** sequential explicit user choices in the conversation (OBS-CANCEL/2 A, K17d A+C, K18/R3 A, R1 A, R2 A, R4 A, R5 A, R6 A, R7 A, R8 A, R9 A, R10 A). This is a provenance claim based on the actual conversation; it is not a cryptographic electronic signature.

## OBS-CANCEL/2 — primary receiver

**A:** Retain observation-based `obs-cancel/1` as the primary P20 canceller and fifth input-channel source. Report frozen 150 Hz phase-noise-only theoretical cancellation limits ~21.7 dB (4096-sample snapshot) and ~22.8 dB (stored inner window). These are not imposed clipping ceilings, not empirical full-run model results. A phase-tracking receiver is not a precondition or authorized study.

## K17d — ASI level drift

**A+C:** Keep `B2-test/1` and natural headline over **all 500 test scenario groups**. Predeclare **35 co-feed (`pol==0`) missing-carrier groups** as a labelled subrow, plus a **465-group sensitivity** row excluding these 35. Re-derive group identities from committed production generation metadata before any test observation is opened; verify the co-feed drop predicate against `docs/results/k17d_drift_audit.json`. Do not remove groups on the basis of outcomes; do not silently regenerate `B2-test/2`.

## K18 / R3 — model loss

**A:** Keep P20 `CE + 0.005 × center_sum + 1.0 × plan BCE`; `center_sum` is the batch mean of the sum of squared 256-dimensional embedding distances to the known-class trainable center. Explicitly turn on `center_loss_weight=0.005`, `plan_loss_weight=1.0`, `plan_consistency=true`; keep AdamW center updates and the **observation-only** train diagnostics, especially center/CE ratio. K17b train-only plan shift stays 15% and uniform ±0.5 MHz. Bare `TrainConfig` defaults silently disable these terms; a later production config must set them explicitly.

## R1–R10 — training, evaluation and numerics

| Decision | Researcher-approved requirement |
|---|---|
| **R1** | `co`, `dual`, `dual_residual`, seeds `0,1,2`: **nine** independent main fits. Headline `dual_residual`; report every seed; no test-based seed choice. |
| **R2** | `width=16`, `time_pool=2`, `level=carrier`; headline embedding `D=256`. |
| **R3** | P20 loss and auxiliary plan head as K18 above. |
| **R4** | Exactly **30 epochs** and fixed OneCycle schedule, **no early stopping** and no epoch search. First highest val-select known-class macro-F1 checkpoint wins. |
| **R5** | Batch **32** in all nine cells, model-specific 11,250 optimizer steps per 30-epoch fit with 12,000 known training observations. No automatic batch reduction if host probe fails. |
| **R6** | AdamW LR peak `1e-3`, decay `1e-4` on existing full parameter group including BatchNorm/centers, OneCycleLR cosine + cycled momentum, no clipping, no autocast; FP32; **both cuDNN TF32 and matmul TF32 explicitly off**. Pin Torch/CUDA/cuDNN/GPU/driver and effective flags under `B2-R6-fp32-tf32-off/1`; current non-strict determinism remains (no bit-exact GPU guarantee). Preserve existing mirror, roll and K17b augmentation. P18 §10 numeric change recorded in this PR, to be enforced only in a later reviewed executor. |
| **R7** | `groups_per_shard=4`, `window_shards=4` with seeded blocked shuffle (up to 16 scenario groups/128 training observations per window); carry short batch remainder across windows; log shard orders and hashes. Do not claim global-shuffle equivalence. |
| **R8** | P31 `train-only → known-only val-calib → freeze all nine checkpoint/scorer/calibrator cells → once-only read-only test/test-only/matched evaluation`. Never use held-out outcomes for fitting, checkpoint, thresholds or search. |
| **R9** | On interruption mark one (view,seed) fit `INCOMPLETE`; restart at epoch 0 under new `attempt_id`, same source/data/environment lock; do not splice partial optimizer/scheduler/RNG/weights. No freeze unless nine valid complete fits. |
| **R10** | Known-class acceptance **0.95**, clean-only alarm Pfa **0.05**, Mahalanobis within-class covariance shrinkage **0.1** from train embeddings. MSP/energy/Mahalanobis rejection scores use independent known-only val-calib higher empirical quantiles; acceptance `score<=threshold`, clean-alarm `score>threshold` using 1-P(clean). Targets are not test guarantees. |

## Evaluation and provenance safeguards

- All nine fits must be frozen prior to the first held-out **observation** read. Check data fingerprints, role membership, source and configuration locks, selected epoch, scorer and calibrator identities.
- Group bootstrap resamples whole scenario groups; three-seed variability is separate from scenario bootstrap. Metrics FPR@95TPR (unknown-positive ranking) and 0.95 known acceptance are different concepts.
- The approved parameters are in a **document-only** record in `docs/plan/`. The E7 and E8 `UNAPPROVED` candidate proposals remain historical proposals by design and must **not** be promoted to `configs/` or passed to a runner in this PR. Production activation requires a later separately reviewed source/config lock and an explicit execution gate.

## Fail-closed authorization — not granted

- `benchmark_complete=false`.
- `full_generation=NOT_AUTHORIZED`, `full_gpu_training=NOT_AUTHORIZED`, `full_loko_sweep=NOT_AUTHORIZED`; all approvals stay `null`.
- **GPU probe: NOT_AUTHORIZED**. No dataset generation, training, inference over held-out, LOKO or GPU workloads are permitted by this record.
- Production caps and `PRODUCTION_LAUNCH_ENABLED=False` remain unchanged. No release/merge to main is authorized by scientific approval.
- All resource host identities, wall/core/disk ceilings, backup and GPU reservations are unresolved (DR-04/DR-05/DR-06).
- Current P31 isolated executor remains capped CPU-only; no production executor is added by this PR.

**E9 engineering preparation:** [P33_b2_e9_production_executor_readiness.md](P33_b2_e9_production_executor_readiness.md).  
**Historical decision context:** [E8 decision recommendations](B2_E8_DECISION_APPROVAL.md), [E8 NO-GO](B2_E8_GO_NO_GO.md), [P18 protocol](P18_b2_protocol.md).

# E8 decision-approval document — recommendations only, nothing approved

Date: 2026-10-24. Verified base `main` `4a1cc95913b430fee5c5e7d2e54cf48c9feeb8d8` (PR #24 merged; Actions run
[40064513568](https://github.com/mythril33/Payload-Aware-Open-Set-Interference-Recognition-for-GEO-Transponders/actions/runs/40064513568),
job 120784837702, head `d1e0898`: E4 step 107 + repository step 1664 = **1771 passed, 7 skipped, 0 failed**).
`benchmark_complete=false`. Every status in the [gates](b2_readiness_gates_2026-10-21.json) is unchanged: K18, K17d and OBS-CANCEL/2
`PENDING_RESEARCHER`; full generation, GPU training and the full LOKO sweep `NOT_AUTHORIZED`; all 29 parameter records of the
[E7 proposal](b2_e7_training_proposal.json) carry `approval: null`. **Recommendation is not decision.** Every row below is mine and carries no
authority; a gate changes only when the researcher writes the decision in their own words and the record is entered in the gates JSON with
`approved_by`, `approved_at`, `decision`, `record` (for `full_*` gates also wall/core/disk ceilings). No test, test-only, matched or
val-calib outcome informed any recommendation; they follow P18/P20/P6, the pilots' pre-registered configs and committed analytic evidence only.

## 1. Recommended primary protocol (one paragraph)

Train the three views (`co`, `dual`, `dual_residual`) with seeds 0/1/2 using the P6 / `TrainConfig` recipe exactly as implemented (width 16,
`time_pool` 2, 30 epochs fixed-length OneCycle, batch 32, AdamW 1e-3 / 1e-4, no clipping, mirror/roll plus the frozen K17b shift), the P20 loss
(`CE + 0.005 x sum_d d^2 + 1.0 x plan BCE`), `obs-cancel/1` as the primary receiver, checkpoint = best val-select macro-F1 (first maximum),
Mahalanobis from train embeddings (regularization 0.1), thresholds from known val-calib only (acceptance 0.95, clean-alarm Pfa 0.05), and the
P31 phase order (train-only, known val-calib, freeze, evaluate) with all nine cells frozen before the first test read. Headline model:
`dual_residual`; `co` and `dual` are the matched ablations; seeds are reported separately and none is selected by outcome. Test-only and matched
sets are evaluated once, K17d rows are predeclared (section 3). **With this choice no value departs from the P6 / `TrainConfig` recipe defaults or from the P20 pre-registered
loss/shift values (`configs/b2_feat.json`: centre 0.005, plan BCE 1.0, K17b 15 % / 0.5 MHz; these are config values, not `TrainConfig` code defaults), so no P18 section 10
entry is needed for any hyperparameter**; a section 10 *decision-log* entry recording the researcher's approvals is optional and the
researcher's call. The nine-fit scope is consistent with P18 (five-channel main model, co as ablation) and K17 (three seeds).

## 2. Decision matrix

"Unlocks" = the next engineering or compute stage that the decision is a precondition of. None of these decisions authorizes DR-04 / DR-05 / DR-06.

| # | Decision | Recommendation | Alternatives (consequence) | Unlocks | Departs from a frozen/default value? |
|---|---|---|---|---|---|
| **K18** | Loss convention | **A**: keep P20 `0.005 x sum`, plan BCE 1.0, keep the observation-only train diagnostic | B P21b `0.01 x mean` (64x weaker at width 8, 128x at width 16: effectively CE-only); C pre-register another weight (a search, extra fits); D disable the centre loss | production training config | B-D: P18 section 10 entry |
| **K17d** | ASI level drift | **A + C**: keep B2-test/1, report all 500 groups, plus a predeclared sub-row of the 35 co-feed missing-carrier groups and a sensitivity row excluding them | B new `B2-test/2` (regenerates 2,500 observations, about 3.5 h, new fingerprints, P18 section 10) | final reporting plan; DR-04 only if B | B only |
| **OBS-CANCEL/2** | Primary receiver | **A**: keep `obs-cancel/1`; state its 21.7-25 dB (22.8 dB stored-window) phase-noise depth ceiling next to every residual-based result | B separate versioned phase-tracking study with rate-dependent criteria (study cost in no budget; a later switch = a second full generation); C tracker as primary (needs B first, delays DR-04) | **DR-04 generation** (the residual is computed at generation time from IQ that is never stored) | B, C: new stage name + section 10 |
| **R1** | Views, seeds | three views x seeds **0, 1, 2** (nine fits) | `dual_residual` only (3 fits, changes the comparison scope; cannot weaken P31's nine-cell admission) | training scope | no |
| **R2** | Width, time_pool | **width 16, time_pool 2**, carrier reference | width 8 (cheaper pilot size), width 32 / time_pool 1 (costlier) | budget, K18 ratio, probe | width != 16: section 10 |
| **R3** | K18 weights (with R2) | option A weights 0.005 / 1.0 | see K18 | config | see K18 |
| **R4** | Epochs | **30**, fixed-length OneCycle, no early stopping, no sizing run | other N or a train/val-select sizing rule (a search under P18 section 5) | cost 12,000 x N per fit | N != 30 or any rule: section 10 |
| **R5** | Batch | **32** (subject to the probe) | 8 (4x the steps, different BatchNorm statistics) | VRAM, steps | batch != 32: section 10 |
| **R6** | Recipe and numerics | P6 recipe as implemented; **pin cuDNN TF32 off** (fp32 as documented); pin torch in the lock | leave TF32 at the torch default (on, cuDNN) = faster, not the documented fp32 | lock content | any non-default constant: section 10 |
| **R7** | Sample order | 4 groups/shard x 4 shards/window (blocked shuffle, at most 16 groups/window) | generator default 8 groups/shard (window 256 MiB, 2x interruption loss) | generation request, E1 | no |
| **R8** | Test coupling | P31 isolated phases; nine cells frozen before the first test read | legacy coupled runner (capped at 12 groups/role) | evaluation | no |
| **R9** | Interruption | restart the interrupted view/seed from epoch 0, record the parent checkpoint hash, never splice | reviewed snapshot (optimizer/scheduler/RNG/cursor; needs a bit-exact CPU resume test) | long GPU runs | no |
| **R10** | Constants | confirm acceptance 0.95, clean Pfa 0.05, Mahalanobis regularization 0.1 (0.95 and 0.1 are P20/pilot values, not P18 numbers) | other values (a prior section 10 step; new scorer identity invalidates frozen bundles) | calibration | different value: section 10 |
| DR-04 | Full generation | **only after** OBS-CANCEL/2, K17d (and K18/R2 if the lock is to cover training) and the engineering milestone of section 5; name host, wall/core/disk ceilings | - | data | - |
| DR-05 | GPU probe, then fits | probe first on an identified host under explicit caps ([spec](b2_e8_gpu_probe_spec.json)); fits are a second approval | - | models | - |
| DR-06 | Full LOKO | defer until production fits exist and the executor is reviewed; 21 fits (primary view) or 63 (three views) are separate budgets | - | LOKO | - |

## 3. K17d predeclaration the researcher would be approving

Rows fixed now, before any test read: (i) all 500 test groups; (ii) the 35 co-feed missing-carrier groups as a labelled sub-row (group list =
the 35 rows with `pol == 0` of [`k17d_drift_audit.json`](../results/k17d_drift_audit.json), derived from generation metadata, not from outcomes);
(iii) a sensitivity row excluding them. Cross-feed drops (43 groups) move no downlink event level. No outcome-driven removal.

## 4. Sentences the researcher would write (templates; copying them approves nothing)

> K18: I choose option [A]. OBS-CANCEL/2: I choose [A]. K17d: I choose [A+C] with the rows of section 3.
> R1 [co, dual, dual_residual; seeds 0, 1, 2]. R2 [width 16, time_pool 2]. R3 [A weights]. R4 [30 epochs, fixed]. R5 [32].
> R6 [P6 recipe as implemented; cuDNN TF32 pinned off; torch pinned in the lock]. R7 [4 x 4]. R8 [P31 isolated phases]. R9 [restart from epoch 0].
> R10 [0.95 / 0.05 / 0.1]. (Separate message, only later) DR-04: authorize generation on [host] with ceilings [wall h / core-h / disk GiB / backup GB].

## 5. What the approvals still do not unlock (engineering preconditions)

The merged code has **no executor for the approved recipe**: the isolated modes force CPU and cap `groups_per_role=2, epochs=2, width=8, batch=32`
(`src/geoml/b2_execution.py:39`, `_cpu` at `:92`; `--device cuda` is refused for every non-legacy mode, `src/geoml/b2_experiment.py:819`); the legacy
coupled runner stops at 12 groups/role (`:54`) and couples test evaluation. Lifting these caps is a `src/geoml` edit, which changes every checkpoint
provenance and the production lock, so it must be a separately reviewed milestone **before** the lock and before any data or fit. See the
[go/no-go report](B2_E8_GO_NO_GO.md) for the sequence and the exact next command.

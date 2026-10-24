# B2 resource budget reconciliation (E11-B)

**Status: PROPOSAL / ANALYSIS ONLY. Nothing in this document is an authorization, a reservation or an approved ceiling.**
Date: 2026-10-24. Base: `origin/main` `293c487d2fd236286e59f6a0ef941feb8ff1b708` (PR #33 merged). `benchmark_complete=false`.
Documentation only: no source, config, gate, protocol file or test is changed; no data was generated, no model trained, no GPU
touched, no held-out observation read. Companions: [pre-run checklist](B2_PRE_RUN_CHECKLIST.md),
[compute approval requirements](B2_COMPUTE_APPROVAL_REQUIREMENTS.md).

Current gate state, read-only (`python scripts/b2_production_preflight.py gates`, exit 4): `K18`, `K17d`, `OBS-CANCEL-2` are `APPROVED`
(scientific protocol); `full_generation`, `full_gpu_training`, `full_loko_sweep` are `NOT_AUTHORIZED`; `PRODUCTION_LAUNCH_ENABLED` is `False`
(`scripts/b2_production_supervisor.py:58`). Scientific approval and compute authorization are different things.

## 1. Provenance classes used below

| Class | Meaning | May it set a ceiling? |
|---|---|---|
| **analytic** | closed-form from array shapes, counts or the approved configuration | yes, as arithmetic, once the configuration is fixed |
| **measured (pilot)** | observed on this repository's pilots, on a small, loaded 4-vCPU sandbox | only as a lower-confidence anchor; it is not the target host |
| **extrapolation** | a measured or assumed rate scaled to production size | no: needs the probe / first-shard gate |
| **plan assumption** | a number chosen in a plan (E5) with no measurement behind it | no |
| **unmeasured** | no number exists | n/a |

## 2. Approved dataset inventory (analytic)

Sources: `src/geosim/b2_protocol.py` (`ROLE_STARTS`, `ROLE_COUNTS`), [E5 plan](../plan/B2_E5_PRODUCTION_EXECUTION_PLAN.md) inventory table,
`docs/results/b2_e10_k17d_identity.json`. Bytes: 395,264 B of float16 arrays per observation (analytic from array shapes + one measured artifact).

| Role / stage | Group IDs | Groups | Variants/group | Observations | Array bytes (GB / GiB) |
|---|---|---:|---:|---:|---|
| B2-feat/1 `train` | 3,000,000 + | 1,500 | 8 | 12,000 | 4.743 / 4.417 |
| B2-feat/1 `val-select` | 3,100,000 + | 150 | 8 | 1,200 | 0.474 / 0.442 |
| B2-feat/1 `val-calib` | 3,150,000 + | 150 | 8 | 1,200 | 0.474 / 0.442 |
| B2-feat/1 known-`test` | 3,200,000 + | 500 | 8 | 4,000 | 1.581 / 1.472 |
| B2-test/1 (shares the 500 `test` groups) | 3,200,000 + | (500) | 5 | 2,500 | 0.988 / 0.920 |
| B2-match/1 `test-matched` | 3,300,000 + | 150 | 3 | 450 | 0.178 / 0.166 |
| **Total** | | **2,450 distinct** | | **21,350** | **8.439 / 7.859** (about 8.7 GB / 8.1 GiB with metadata) |

* 18,400 known + 2,500 test-only + 450 matched = 21,350. Test groups carry 13 variants in total (8 known + 5 test-only); this is the same 6,500 test
  observations the E10 packet uses for its option-B arithmetic, plus 450 matched = 6,950.
* Fit data per view: 12,000 train, 1,200 val-select (checkpoint only), 1,200 val-calib (known-only thresholds). 4,000 + 2,500 + 450 = 6,950 are held out.
* K17d identity (candidate list, **pending researcher acceptance** per the record's status field): headline 500, sensitivity 465, co-feed-missing 35,
  cross-feed-missing 43, missing total 78. K17d changes reporting rows, not the number of groups to generate.
* Shards: 4 groups per shard (32 known / 20 test-only / 12 matched observations; 12.06 / 7.54 / 4.52 MiB of arrays). The training window is 4 shards =
  16 groups. Final shards of 150-group roles are partial. A hard interruption loses at most one in-flight shard.
* **Held-out exposure (E10 decision D-1, still open):** test groups 3200000, 3200001 and matched groups 3300000, 3300001 carry published pilot
  outcomes. The test role is not pristine until the researcher records D-1. Option B (re-versioning) would require regenerating 6,950 observations
  (about 7.7 core-hours at the 4 s/observation pilot rate; extrapolation) and a new generation authorization, so **D-1 should be decided before the
  test-role stages are generated**.

## 3. Generation cost

| Item | Figure | Class | Source |
|---|---|---|---|
| Per-observation band used by the supervisor | 3.8 - 5.0 s | plan assumption (60-observation matched profile, 262 s wall / 300.2 CPU-s) | `scripts/b2_production_supervisor.py` `DEFAULT_TIMING`, E5 plan |
| Wall time, 21,350 observations, one process, 2 BLAS threads | 22.5 / 26.6 / 29.7 h (3.8 s / central 4.49 s / 5.0 s) | extrapolation | E5 plan reports 23.0 / 26.6 / 30.2 h; recomputed here from the band |
| E7a capped real-physics run, whole-attempt wall including start-up | 4.58 s (known), 5.27 s (test-only), 4.83 s (matched) per observation | measured (pilot), 2 groups per stage | [E7a verification](../results/b2_e7a_supervisor_verification.md) |
| Illustration only: those E7a rates applied to the production mix | about 4.67 s average, about 27.7 h (23.4 h known, 3.7 h test-only, 0.6 h matched) | extrapolation of a start-up-inflated pilot | arithmetic here; it neither confirms nor refutes the band |
| CPU consumption | about 26 - 35 core-h if the 300.2/262 ratio holds | extrapolation | E5 plan |
| Generator memory | 566 - 582 MiB peak child RSS at 2 groups (E7a); about 601 MiB single process (E5 profile) | measured (pilot) | no production-size peak exists |
| Storage | 8.44 GB arrays, about 8.7 GB with metadata (8.1 GiB) | analytic + one measured artifact | E5 plan, `b2_e8_resource_budget.json` |
| Raw IQ (not stored) | about 170 GB if it were saved | plan assumption | E5 plan; raw IQ stays transient |

Proposed generation ceilings (36 h wall, 42 core-h, 25 GiB working disk, 9 GB backup, 2 GiB per process, 8 GiB host RAM) are **E5 proposals carried
forward unchanged**; they are listed in the [approval requirements](B2_COMPUTE_APPROVAL_REQUIREMENTS.md). No multiprocess writer exists, so the
wall time cannot be shortened by adding workers; a faster host is the only lever and the supervisor's first-shard timing gate is the only runtime check.

## 4. Training cost: structure (analytic) and the five-figure confusion

Approved recipe (`docs/plan/b2_e9_approved_scientific_protocol.json`): 3 views x seeds 0/1/2 = **nine fits**, width 16, batch 32, 30 epochs,
12,000 train observations per fit, `B2-R6-fp32-tf32-off/1`.

| Quantity | Value | Class |
|---|---|---|
| Steps per fit | 375 per epoch x 30 = 11,250; nine fits 101,250 | analytic |
| Training sample passes | 9 x 30 x 12,000 = 3,240,000 | analytic |
| Val-select forward passes | 9 x 30 x 1,200 = 324,000 | analytic |
| Width-16 / width-8 multiply-accumulates | 0.321 / 0.097 GMAC per sample, ratio 3.31 | analytic (`scripts/b2_e8_budget.py`) |
| Width-16 `dual_residual` parameters | 311,705; weights + gradients + AdamW + buffers 4.79 MiB; checkpoint about 1.2 MiB per fit | analytic |
| Width-16 batch-32 GPU memory | 452.9 - 881.0 MiB, excluding CUDA context, workspaces and allocator fragmentation | analytic, **not measured on a GPU** |
| Restart cost after an interrupted fit (R9) | 360,000 sample passes plus 30 epochs of loader time (0.65 - 0.78 h) | analytic from the above and the loader basis |

### 4.1 Register of every GPU-hour figure in circulation

All ratios are recomputed here. "Reservation" is the E5 6 GPU-h figure, which was written for **width 8**.

| # | Figure | Where | What it is | Class | Ratio to 6 h |
|---|---|---|---|---|---|
| F1 | 6 GPU-h | E5 plan; `PROPOSED_CEILINGS["main_training_gpu_hours"]` in `scripts/b2_production_preflight.py:78` | width-8 reservation: assumed 200 - 1,000 samples/s -> 0.9 - 4.5 h pure compute, plus allowance | plan assumption | 1.00 |
| F2 | 0.9 - 4.5 h | E5, E7, approved record | width-8 pure compute at an **assumed** 200 - 1,000 samples/s; no GPU throughput was ever measured | plan assumption | 0.15 - 0.75 |
| F3 | 5.88 h | approved record; E7 proposal; E6 audit | synchronous loader only: (34 s read + 12,000/270 s preprocessing) = 78.4 s/epoch; omits val-select read (about 4 s), val-select preprocessing (about 4.4 s) and K17b re-preprocessing (about 6.7 s) | extrapolation (E1 rates on a different loaded CPU) | 0.98 |
| F4 | 6.8 - 10.4 h | E7 proposal | width-8 compute (0.9 - 4.5) + F3 (5.88): the "older partial accounting" | extrapolation | 1.13 - 1.73 |
| F5 | 7.0 h (6.97) | E7 proposal; approved record; E8 | complete loader accounting: 93 s/epoch x 30 x 9 | extrapolation | **1.17** |
| F6 | 7.9 - 11.5 h | E7 proposal; E8 | width-8 compute (0.9 - 4.5) + F5 (6.97) | extrapolation | 1.32 - 1.92 |
| F7 | 3.0 - 14.9 h | E8 budget | width-16 pure compute: F2's throughput band divided by the MAC ratio 3.31 (302 - 60 samples/s) | extrapolation of an assumption | 0.50 - 2.48 |
| F8 | 10.0 - 21.9 h (9.95 - 21.87) | E8 host assessment (rounded "10 - 22 h" is this band) | **the only width-16 nine-fit band**: F7 + F5 | extrapolation of an assumption | **1.66 - 3.65** |
| F9 | 35.2 h (3.91 h per fit) | E7 proposal, E8 | CPU-only compute at a measured warm 25.6 samples/s; excludes loader | measured (pilot, loaded sandbox) x assumed 30 epochs | n/a (fallback bound) |
| F10 | 20.3 - 44.6 h / 61.0 - 133.9 h | E8 | width-16 LOKO, 21 fits (10,500 train observations) / 63 fits | extrapolation | not part of the main campaign |

**Findings from the audit (E11-B):**

1. **Ratio error (E10 finding M-11, confirmed).** The sentence "7.0 h for nine fits ... roughly 1.9x the reservation" appears in
   `docs/plan/B2_E7_TRAINING_SPEC_PROPOSAL.md:52-53`, `docs/plan/b2_e7_training_proposal.json:636` and the approved record
   `docs/plan/b2_e9_approved_scientific_protocol.json:430` (approved record not edited; E10 recorded it as errata E-1). 7.0 / 6 = **1.17**. The 1.9x
   figure is the upper end of F6 (11.5 / 6 = 1.92), which includes width-8 compute. This document treats 1.17x as correct and edits none of those files.
2. **"10 - 22 h".** P33 line 17 cited it without a source and E10 withdrew it from P33. A literal grep for "10-22" finds no source, but the rounded
   F8 band of the E8 assessment (10.0 - 21.9 h) has the same value, so it is most plausibly F8 rounded. It is treated here as F8: an extrapolation, not
   a measurement and not a reservation.
3. **The 6 GPU-h reservation does not apply to the approved recipe.** It was written for width 8 (F1/F2). The approved width is 16 (3.31x the
   multiply-accumulates). The E8 budget withdraws it and proposes no replacement until the probe runs. The stale constant
   `main_training_gpu_hours: 6` still sits in `scripts/b2_production_preflight.py:78`; it is not changed here and **must not be read as an approved ceiling**.
4. **Loader dominates and is width-independent.** F5 (6.97 h) is more than F2's upper end (4.5 h) and is 32 - 70 % of F8. It rests on CPU rates
   from "a different, loaded CPU" (P24 section 2 read estimate and the 270 observations/s preprocessing rate) and scales them linearly; the trainer has
   no prefetch, so it is added without overlap. A faster storage/CPU path or an async loader (not implemented) would change F5 but not F7.
5. **F7's width depends on one assumed throughput band.** 200 - 1,000 samples/s was never measured on any GPU. The spread of F7 and F8 (a factor of
   5 between ends) is the width of that assumption, not an uncertainty interval. GPU utilization does not scale with MACs alone (E8 caveat), so the real
   value can lie outside the band, in either direction.
6. **Omitted costs in every figure:** the val-select forward pass is counted in F5 (read) but not as GPU compute in F7 (324,000 forward-only
   passes, small); calibration, scorer fitting (train-only Mahalanobis), nine-cell freeze and the one test evaluation are not budgeted at all;
   checkpoint writes and the ~1.2 MiB per fit are negligible. Restart cost (R9, up to one fit lost per interruption) is not in any total.
7. **LOKO inconsistency.** E5's 2.1 - 10.5 GPU-h LOKO range uses 12,000 train observations per fit; E8 uses the correct 10,500. LOKO is outside this
   plan's scope and `full_loko_sweep` stays `NOT_AUTHORIZED`.
8. **CPU-only is not a fallback.** F9 (35.2 h compute at width 16 before the loader, measured on a loaded sandbox) is shown only to bound the option.

### 4.2 Reconciled statement (what may be said today)

> For the approved nine width-16 fits, the committed record contains **no measured GPU-hour figure**. The only width-16 band is an extrapolation of
> 10 - 22 GPU-hours (9.95 - 21.87), which is 1.7 - 3.7 times the 6 GPU-hour width-8 reservation; its loader part (about 7.0 h, width-independent) is a
> linear extrapolation from CPU pilot rates and its compute part (3.0 - 14.9 h) rests on an assumed throughput. The 6 GPU-hour figure is not a
> valid ceiling for the approved recipe. A ceiling can be proposed only after the bounded probe has produced an end-to-end rate.

## 5. Three-way separation

| Analytic (usable as arithmetic) | Historical pilot measurements (anchors only) | Not yet measured (blocks a ceiling) |
|---|---|---|
| observation / group / shard / byte counts; 3.24 M passes; 101,250 steps; MAC ratio 3.31; parameter counts; 4.79 MiB state; 452.9 - 881.0 MiB VRAM *bounds*; restart cost per fit | 60-observation matched profile (262 s); E7a capped real-physics 4.58 / 5.27 / 4.83 s per observation; 566 - 601 MiB generator RSS (2 groups / 60 observations); CPU warm rates 50.8 (w8) and 25.6 (w16) samples/s; step peaks about 0.69 GiB; E1 loader rates; artifact size per observation | GPU throughput; GPU peak memory (allocated, reserved, nvidia-smi); end-to-end rate with the real loader at production window size; K17b re-preprocessing cost on target CPU; val-select forward-only rate; production-size generation time and peak RSS; streaming memory over a full epoch; storage read rate for 4.7 GB per epoch; GPU-vs-CPU fp32 parity and TF32-off cost; interrupted-run recovery time |

## 6. Open measurements and who closes them

| ID | Measurement | Closed by | Needs |
|---|---|---|---|
| M-1 | width-16 batch-32 throughput and peak VRAM, TF32 off | bounded GPU probe | executor (not built), identified GPU host, researcher authorization |
| M-2 | end-to-end rate with the synchronous loader | probe, real-layout part | a verified B2-feat/1 train/val-select artifact |
| M-3 | production generation rate and peak RSS | supervisor first-shard gate during DR-04 | `full_generation` authorization, launch milestone |
| M-4 | full-epoch streaming memory | probe or first training epoch | as M-2 |
| M-5 | GPU/CPU fp32 parity on a fixed batch | probe | pre-registered tolerance (see approval requirements, decision P-1) |
| M-6 | val-select forward-only rate, K17b re-preprocessing cost | probe (not in the current spec; see approval requirements, gap G-1/G-2) | spec extension before authorization |

Nothing in this document can close M-1 to M-6; they remain `unmeasured`.

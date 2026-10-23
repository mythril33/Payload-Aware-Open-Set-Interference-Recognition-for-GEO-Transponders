# Researcher decision packet — K18, K17d, OBS-CANCEL/2 (E6)

Date: 2026-10-23. Base: merged `main` `59ed11d60ace609a826f6379491c9a8dbd26d64d`. `benchmark_complete=false`.
**This packet records no decision.** Every status in [the readiness gates](b2_readiness_gates_2026-10-21.json) stays
`PENDING_RESEARCHER` / `NOT_AUTHORIZED`; every recommendation below is a proposal that only the researcher can adopt, in
their own words (templates in §6). It refines the E5 [memorandum](B2_E5_RESEARCHER_DECISIONS.md); where it differs the
difference is stated. All numbers are reproduced by `scripts/b2_e6_decision_evidence.py` into
[`docs/results/b2_e6_decision_evidence.json`](../results/b2_e6_decision_evidence.json) from committed evidence only (no new
experiment, no data generation, no training). Readiness status (computed checks plus audited findings with named verifiers): the
[production-readiness checklist](B2_E6_PRODUCTION_READINESS_CHECKLIST.md) and the [preflight contract (P29)](P29_b2_e6_production_preflight.md).

## 1. What must be decided, in what order

| Order | Gate | Why this position | What it unlocks | Cost of deciding late |
|---|---|---|---|---|
| 1 | **OBS-CANCEL/2** (primary receiver) | The fifth channel is computed at generation time from IQ that is never stored | DR-04 (generation) | Any later change of the primary receiver means regenerating every residual-bearing stage: about 26.6 h central (range 23.0–30.2 h) |
| 2 | **K18** (loss convention) **together with the unfrozen training width/epochs/optimizer** | The center term scales with the embedding size D = 16 x width, so K18 cannot be judged apart from the width | The production training configuration; the source/config lock (the K18 diagnostic edits `src/geoml`) | A change after the lock invalidates the lock and every checkpoint's source identity |
| 3 | **K17d** | Mostly a reporting rule; only the option "B2-test/2" touches generation | Final reporting plan; DR-04 only if B2-test/2 is chosen | Choosing B2-test/2 after generation costs about 3.5 h (the 2,500 test-only observations) |
| 4 | DR-04 full generation | Needs 1-3 recorded plus explicit ceilings and a designated host | Data | - |
| 5 | DR-05 GPU probe, then DR-05 training; DR-06 LOKO | Separate approvals; the probe authorizes no full fit | Models, LOKO | - |

## 2. K18 — primary training-loss convention

**Evidence (verified here).** P20 (`geoml.train`, `configs/b2_feat.json`) uses `0.005 x sum_d (e_d - c_d)^2` plus plan-BCE 1.0;
the separate P21b stage uses `0.01 x mean_d`. The committed scale audit gives a P20-to-P21b term ratio of exactly D/2 in all
three views: 64 at the pilot width 8 (D = 128) and 128 at width 16 (D = 256). On the degenerate three-epoch pilots the weighted
center term is 1.0e-6 to 2.6e-5 against a cross-entropy of about 2.08 (at most 1.2e-5 of CE), negligible in **both** conventions;
the pilots therefore cannot calibrate the weight, in either direction. Two facts the E5 memorandum did not state:
(i) the effective strength depends on the production width, which is not frozen anywhere (`audit.production_training_config_missing`);
(ii) the recommended train-only center/CE diagnostic did not exist in either trainer when this packet was written
(`audit.k18_diagnostic_missing`), so "log it and keep lambda unless it exceeds 50 % of CE" could not be executed on that code.
*E7a update:* the observation-only diagnostic now exists (`TrainDiagnostics`, always on, no `TrainConfig` field, bit-identical
training on CPU fp32; GPU parity is untested and is part of the DR-05 probe). It changes the checkpoint source hashes of
`train.py`, `b2_stream.py`, `b2_experiment.py` and `b2_loko.py`; earlier checkpoints are not relabelled.

| Option | Description | Scientific consequence | Engineering consequence |
|---|---|---|---|
| **A (recommended)** | Keep P20: `0.005 x sum`, BCE 1.0, AdamW center updates unchanged | Continuity with all pilots and the pre-registered configs; the center term is expected to be weak early and grow with embedding scale, which is exactly what the diagnostic must show | Add the train-only per-epoch center/CE ratio log (diagnostic only, no effect on training) before the source lock; freeze a production training config |
| B | Adopt P21b `0.01 x mean` | The term is 64x (width 8) or 128x (width 16) weaker: effectively CE-only training, which equals the pilots' practical behavior but gives up the pre-registered mechanism | Needs a new config version and a P18 section 10 entry; P20 checkpoints are no longer comparable |
| C | Pre-register a different weight chosen on train/val-select only | A search; legitimate only if registered before use and never touching val-calib or test | Extra fits and a P18 section 10 entry; adds compute not in the DR-05 budget |
| D | Disable the center loss (lambda = 0) as the primary | Removes the center-loss mechanism of the pre-registered recipe; its effect on the Mahalanobis scorer is unmeasured here, so this must be reported as a change of method | New config version; the center loss becomes an ablation |

**Approval must state:** the option (A-D); the production width, epochs, batch, optimizer/scheduler and seed list the plan
assumes (3 views x 3 seeds x 30 epochs is an assumption, not a frozen value); whether the center/CE diagnostic is to be added
before the lock. Any option other than A also needs a P18 section 10 entry before any test evaluation. A-D do not decide the
training budget, GPU use or the LOKO scope.

## 3. K17d — missing-carrier level drift of the downlink ASI family

**Evidence (recomputed from the 78 committed audit rows).** Of 500 test groups, 78 (15.6 %) drop a carrier: 35 on the co feed, 43 on
the cross feed. Only co-feed drops move the downlink event level: median 0.71 dB, 90th percentile 2.93 dB, maximum 5.91 dB;
cross-feed drift is zero by construction of the audit formula (the physical bound through the 30 dB uplink coupling is below 0.01 dB, P22). Affected groups by size: 19 are at least 0.5 dB, 15 at least 1 dB, and **4 (0.8 % of the 500)
at least 3 dB**, the width of one matched bin. K17c's level-matched set (B2-match/1) is generated separately and is not affected;
K17d concerns the natural near-family `adjacent_satellite_downlink` row and its pairing with the known uplink ASI.

| Option | Description | Scientific consequence | Engineering consequence |
|---|---|---|---|
| **A + C (recommended)** | Keep B2-test/1 as frozen, report all 500 groups, plus the 35 co-feed groups as a labelled sub-row and a sensitivity row excluding them | No change to frozen generation; the bias (at most 5.9 dB, 0.8 % of groups above 3 dB) is bounded and visible; no outcome-driven removal | Reporting rules only, to be registered before the test role is evaluated |
| B | New `B2-test/2` that scales the downlink event by the nominal unit load instead of the realized feed power | Restores exact pairing in all groups but changes the P15 "wanted feed power" convention | New stage name, P18 section 10 entry, regeneration of 2,500 observations (about 3.5 h), new fingerprints |
| C only | Exclusion row without the labelled sub-row | Hides the affected groups from the headline | Reporting only; weaker than A + C |

**Approval must state:** A + C, B, or another option; that the sub-row/sensitivity row is predeclared (names and group lists fixed
now, not after seeing outcomes). Only option B alters generation and must be decided before DR-04.

## 4. OBS-CANCEL/2 — phase tracking in the observation-based canceller

**Evidence.** `obs-cancel/1` fits one complex gain per 4096-sample snapshot (42.7 us). For a block-constant estimate and Wiener
phase noise of the frozen 150 Hz effective linewidth (100 Hz satellite + 50 Hz receiver) the depth ceiling is
`-10 log10(2 pi dv T / 6)` = **21.7 dB** over the full block; the stored PSD drops 512 samples per side (`edge_guard`), which
gives **22.8 dB** for the stored window (seeded Monte Carlo, same assumptions). The formula was checked against a seeded Monte
Carlo (agreement within 0.05 dB at 42.7, 6.4 and 1.78 us). The E5 memorandum already stated the formula, the 25.5 versus 35.5 dB
figures and that 35 dB is "not universal", and scoped the target to a 36 Mbaud, 64-symbol reference, which is feasible. What E6
adds is where that reference sits relative to the frozen scenes: a 35 dB ceiling needs a segment of at most **2.01 us**, i.e. at
least **31.8 Mbaud** with 64 symbols (63.6 Mbaud with 128, impossible inside the 36 MHz band), whereas the widest carrier the frozen
plan generator can place is **24 Mbaud** (`rs x (1 + roll-off + 5 % guard) <= 0.95 x 36 MHz`; the natural ASI family reaches 28.8
Mbaud). At 24 Mbaud the 64-symbol ceiling is 33.8 dB. So 35 dB is unreachable for every carrier of the frozen scenes; the 36 Mbaud
column below is a synthetic reference only. The ceiling per carrier rate with the proposed segments (capped at one snapshot):

| Symbol rate (Mbaud) | 1 / 1.5 | 3.6 | 6 | 10 | 20 | 28.8 | 36 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 64-symbol segment, ceiling dB | 21.7 | 25.5 | 27.8 | 30.0 | 33.0 | 34.6 | **35.5** |
| 128-symbol segment, ceiling dB | 21.7 | 22.5 | 24.7 | 27.0 | 30.0 | 31.6 | 32.5 |

So a universal 35 dB target is reachable only at the synthetic 36 Mbaud reference; the frozen scenes span 1-24 Mbaud (natural ASI up to
28.8 Mbaud, P22 section 7). The ceiling is the phase-noise term only (ideal block mean, no
estimation noise); real decision-directed tracking is worse. The ceiling bounds sensitivity to weak in-band events, not validity.
Cost: the canceller adds 1.34 s per observation; a tracker at the proposed at-most-2x runtime adds at most about 7.95 h over
21,350 observations.

| Option | Description | Scientific consequence | Engineering consequence |
|---|---|---|---|
| **A (recommended)** | Keep `obs-cancel/1` as the primary receiver; state the 21.7-25 dB ceiling (22.8 dB for the stored window) in every residual-based result | Frozen, consistent with all pilots; results are lower bounds on residual visibility for weak events | None before DR-04 |
| B | Authorize a **separate** versioned design/validation study with rate-dependent acceptance criteria (target = ceiling formula minus a stated margin per carrier rate; no universal 35 dB), preregistered synthetic feasibility, no test-family tuning | Could raise the ceiling for wide carriers (64-symbol segments: +3.8 dB at 3.6 Mbaud, up to +13.8 dB at 36 Mbaud) but not for carriers of about 1.5 Mbaud or less, where one segment already spans a snapshot | Study cost not in any budget; a later switch to the new receiver means a second full generation |
| C | Adopt a tracker as the **primary** receiver before production | Changes the receiver for the headline benchmark | Needs the study first; delays DR-04; new artifact stage name and P18 section 10 entry |

**Approval must state:** A, B or C. If B, the revised criteria (the universal 35 dB wording of P22 section 6 is infeasible for every carrier of the frozen scenes
and would be replaced; the E5 memorandum's 36 Mbaud, 64-symbol reference criterion remains a synthetic-feasibility target) and an explicit statement that the study's outputs are not mixed with B2-feat/1 fingerprints.

## 5. Proposed resource ceilings and the start-up gate for DR-04 (proposals only)

| Resource | Proposed ceiling | Basis | Status |
|---|---|---|---|
| Generation wall time | 36 h (one process, two BLAS threads) | 23.0-30.2 h estimate, 19 % margin over the high end | Extrapolated from a 60-observation profile |
| CPU time | 42 core-h | 34.6 core-h at the high estimate, 20 % allowance | Extrapolated |
| Working disk | 25 GiB, plus a separate 9 GB verified backup | 8.7 GB estimated artifacts (8.44 GB raw arrays) | Estimated |
| Host RAM | 8 GiB generation, 16 GiB training | 2 GiB per generator process; 4-shard windows | Unmeasured at scale |
| GPU | 8 GiB minimum, 12 GiB preferred; 6 GPU-h for the main nine fits | Assumed 200-1000 sample-passes/s | **Not measured**; probe first |
| LOKO | 2.1-10.5 GPU-h for 21 fits (63 fits for three views: 6.3-31.5 GPU-h) | Same assumption | Not implemented |

DR-04 should be granted only with: the production lock created from a clean tree (`lock-create`), `audit --production` of each
stage root (all roles, no group limit, four groups per shard, `obs-cancel/1`), the resource probe run on the **designated** host, and a
**first-shard timing gate** that stops the run if the first committed shards fall outside 3.8-5.0 s per observation (the
extrapolation's validity band). The first two are tested here; the gate and a supervisor are not implemented
(`audit.stage_supervisor_missing`).

## 6. Approval wording (templates only — filling or copying them approves nothing)

Each gate changes only when the researcher writes the decision and the record is entered in the gates JSON with approver, time,
decision and record reference (`approved_by`, `approved_at`, `decision`, `record`; for `full_*` gates also `wall_hours`, `core_hours`,
`working_disk_gib`, `backup_disk_gb`). The preflight reports an approval lacking any of these, or a status that disagrees with the
memorandum, as FAIL.

> K18: I choose option [A/B/C/D]. Production training configuration: width [..], epochs [..], batch [..], optimizer/scheduler [..],
> seeds [..]. Keep the train-only center/CE diagnostic (implemented in E7a, always on): [keep/remove before the lock].
> K17d: I choose [A+C / B / ...]. Predeclared rows: [names].
> OBS-CANCEL/2: I choose [A / B / C]. [If B: criteria].
> (Separate message, only after the above) DR-04: authorize generation of the frozen 21,350 observations on [host] with ceilings
> [wall h / core-h / disk GiB / backup GB]; benchmark_complete stays false.

## 7. Not done in E6

No decision recorded; no gate status changed; no B2 data beyond the capped two-group drill; no model trained; no GPU used; no LOKO;
no protocol, frozen config, loss or canceller edited. The recommendations above are mine; they carry no authority.

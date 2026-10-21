# B2/1 production budget — measured pilot costs and estimates

Date: 2026-10-21. Commit of the measurements: `82d6e7a` (working tree with the B2-match/1 slice; the
follow-up commit is recorded in DURUM). Hardware: this cloud container, 4 CPUs (x86-64, Linux 6.18),
15 GiB RAM, no GPU, Python 3.13.16, NumPy 2.5.4, SciPy 1.18.1, `OMP_NUM_THREADS=2`,
`OPENBLAS_NUM_THREADS=2`, single generator process. Measurements come from
`scripts/profile_b2_generation.py` (monkeypatched timers around `simulate_dual`,
`cancel_planned_carriers` and `numpy.savez`, `resource` peak RSS); the JSON records are
[with cancellation](b2_profile_matched_20_cancel.json), [without cancellation](b2_profile_matched_20_nocancel.json)
and [resume](b2_profile_matched_20_resume.json). **Everything in §1 is measured; everything in §2 is an
estimate and says so.** No full-scale production or GPU training was launched.

## 1. Measured

### 1.1 Matched set, 20 groups × 3 variants = 60 observations (`B2-match/1`, bins 4–7/7–10/10–13 dB)

| Quantity | With cancellation (`obs-cancel/1`) | Without cancellation |
|---|---:|---:|
| Wall time | 262.0 s | 178.2 s |
| CPU time | 300.2 s | 214.2 s |
| Startup + calibration copy before the first observation | 0.19 s | 0.04 s |
| Simulator time per observation (`simulate_dual`) | 3.00 s | 2.95 s |
| Canceller time per observation | 1.34 s | – |
| Shard write per observation (`np.savez`, 4 groups/shard) | 0.4 ms | 0.3 ms |
| Wall per observation (steady state) | 4.36 s | 2.97 s |
| Peak resident memory (generator process) | 601 MiB | 570 MiB |
| Artifact size | 24.36 MB (0.406 MB/obs) | 16.25 MB (0.271 MB/obs) |
| Resume validation of the finished artifact (checksums + full re-validation) | 0.31 s | 0.28 s |

Cancellation overhead: +1.34 s per observation (+47 % wall), +0.135 MB per observation (+50 % storage, the
float16 residual). Shard writing and startup are negligible; the cost is the physical chain itself
(IMUX/TWTA/OMUX at 288 MHz for 128 snapshots × 2 feeds) plus the canceller. The earlier pilots give the
spread of the per-observation cost under other loads and group mixes: 3.81 s/obs (B2-feat/1 pilot, test
suite running concurrently), ≈ 4.0 s/obs (B2-test/1 families; `cid_overlay` ≈ 8 s), 4.36 s/obs here. The
range 3.8–5.0 s/obs is used below as low/central(4.4)/high.

### 1.2 Earlier pilots (same container, recorded in their reports)

| Stage | Observations | Wall | Peak RSS | Artifact |
|---|---:|---:|---:|---:|
| B2-base/1 (no residual) | 64 | 109.6 s | 546 MiB | 16.5 MB |
| B2-feat/1 | 64 | 243.8 s | 585 MiB | 24.8 MB |
| B2-test/1 | 10 | ≈ 40 s | – | 4.0 MB |
| B2-match/1 pilot | 6 | ≈ 26 s | – | 2.4 MB |

### 1.3 Evaluation pilot

Three views × 3 epochs on 16 training observations plus inference on 16 + 10 + 6 test observations:
≈ 2–3 min wall on CPU including Mahalanobis fitting, calibration and figure writing (not profiled
separately; dominated by preprocessing and model start-up at this size).

## 2. Estimates for the full frozen B2/1 (single generator process, 2 threads, this container)

| Item | Observations | Low (3.8 s/obs) | Central (4.4 s/obs) | High (5.0 s/obs) | Storage (0.406 MB/obs) |
|---|---:|---:|---:|---:|---:|
| Known classes, 4 roles (2 300 groups × 8) | 18 400 | 19.4 h | 22.5 h | 25.6 h | 7.5 GB |
| Test-only families (500 × 5; `cid_overlay` ≈ 8 s) | 2 500 | 3.1 h | 3.5 h | 4.0 h | 1.0 GB |
| Matched set (150 × 3) | 450 | 0.5 h | 0.55 h | 0.6 h | 0.18 GB |
| **Total generation** | 21 350 | **23.0 h** | **26.6 h** | **30.2 h** | **8.7 GB** |

Caveats (all ESTIMATE): costs scale linearly with observations in the pilots; the known stage's group mix
(carrier counts, modulations) differs from the matched set's narrow-carrier bias, which is why the range
rather than the matched point estimate is used; wall time assumes no concurrent load. Peak memory stays
≈ 0.6 GiB per generator process. The generators are **single-process**: on this 4-CPU container two
processes with 2 threads each would halve wall time only if run on separate requests (for example the
known stage with `--roles train` in one directory and the three evaluation roles in another), but
`geoml.b2_experiment` currently loads one artifact root with all four roles, so a merge step or a
multi-process shard writer would be needed first (not implemented; listed as a production-readiness gap).

### 2.1 Training and evaluation (researcher's GPU; assumptions explicit)

| Item | Assumption | Low | Central | High |
|---|---|---:|---:|---:|
| Main models: 3 views × 3 seeds × 30 epochs on 12 000 observations | 200–1 000 sample-passes/s on one mid-range GPU for the ≈ 80 k-parameter ResNet at 5 × 64 × 512 input; data in host RAM | 0.9 h | 2.3 h | 4.5 h |
| LOKO (A8): 7 held-out classes × 3 seeds, same budget | 7 × the main cost per view, 3 views | 6.3 h | 16 h | 32 h |
| Inference on all test sets, Mahalanobis, calibration, figures | negligible against training | < 0.5 h | < 0.5 h | < 0.5 h |

Host-RAM caveat: `geoml.b2_experiment` loads whole roles into memory and preprocesses to float32
(train role at full scale: 12 000 × 5 × 64 × 512 × 4 B ≈ 7.9 GB after time pooling, plus the float16
source ≈ 7.9 GB). A streaming loader (the P21b stage already streams shards) or role-wise memory mapping
is required before the full-scale run; this is a production-readiness gap, not a cost item.

## 3. What remains before full production can be authorized

1. Researcher decisions: K18 (loss weights and convention), K17d drift handling, OBS-CANCEL/2 (P22 §6).
2. Engineering: streaming/memory-bounded loading in `geoml.b2_experiment` (or adoption of the P21b
   streaming loader for the P20 artifacts), optional multi-process generation, LOKO runner, EDSC/XGBoost
   baselines, A5 dual-pol test corruption.
3. Budget approval: ≈ 23–30 h of single-process generation on this container (≈ 12–15 h with two
   processes once the merge step exists) and ≈ 8.7 GB of storage outside Git; GPU time per §2.1.

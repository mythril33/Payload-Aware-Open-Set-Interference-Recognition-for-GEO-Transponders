# E1 streaming data path — measured memory, throughput and parity (bounded fixtures)

Date: 2026-10-21. Branch `feature/b2-e1-streaming-loader` on `main` `0f75dea`. Hardware: this cloud container,
4 CPUs, 15 GiB RAM, no GPU, Python 3.13.16, NumPy 2.5.4, torch 2.14.1 (CPU), `OMP_NUM_THREADS=2`.
Tool: `scripts/profile_b2_experiment_memory.py`; every mode runs in a fresh subprocess; the peak is the
resident high-water mark **after the imports** (`/proc/self/clear_refs` reset, `VmHWM`), so the
≈ 549 MiB Python/torch import footprint is reported separately. Records:
[real pilot](b2_streaming_memory_pilot.json), [synthetic 48-group fixture](b2_streaming_memory_synthetic_48.json).
**Everything in §1–§3 is measured on bounded fixtures; §4 is reasoning, not measurement. No production run.**

Legacy = the pre-E1 data flow (`load_b2_split` of the four roles, `geoml.train.fit` on whole tensors,
`geoml.train.infer`). Streaming = `geoml.b2_stream` (`open_b2_known` verification pass, `fit_streaming`,
`infer_streaming`). Same training configuration (`dual_residual`, plan head, center loss 0.005, K17b
plan shift 0.15, augmentation, width 8, batch 8, seed 0) on the same artifact.

## 1. Real pilot artifact (`data/b2-feat-pilot`, 16 observations per role, 2 shards of 8, 3.0 MiB each; 3 epochs)

| Mode | Peak RSS | Increment after imports | Verify | Fit (3 epochs) | Inference | Weights vs legacy |
|---|---:|---:|---:|---:|---:|---|
| legacy | 926 MiB | +377 MiB | 0.19 s (+0.17 s load) | 2.4 s | 119 obs/s | – |
| streaming, window 1 | 869 MiB | +320 MiB | 0.17 s | 2.4 s | 123 obs/s | different order (2 windows) |
| streaming, window 4 | 885 MiB | +335 MiB | 0.16 s | 3.8 s | 129 obs/s | **identical** (single window; identical history) |

At this size the increment is almost entirely the fixed torch kernel/optimizer state (≈ 320 MiB on this CPU
build); the data are 6 MiB float16 + 10 MiB float32 per role. The pilot proves parity, not memory.

Full-runner parity on the same pilot (`python -m geoml.b2_experiment … --unknown-data … --matched-data …`,
`runs/b2-e1-stream-pilot` versus the pre-E1 run `runs/b2-full-pilot`, 3 views): identical training history
in all three views, 48 of 48 test predictions identical, maximum absolute difference of the MSP/energy/
Mahalanobis unknown scores 0.0; wall 13.9 s, lifetime peak RSS 914 MiB including figure writing.

## 2. Synthetic-layout fixture (48 groups per role = 384 observations per role, 6 shards of 64 = 24.1 MiB each, 590 MiB artifact; 1 epoch)

The fixture is written and verified by the real `geosim.b2_dataset` writer with a stand-in simulator
(random spectra, fake canceller): exact B2-feat/1 layout, sizes and validation, **no physics**. Build 4.4 s.

| Mode | Peak RSS | Increment after imports | After open/load | Verify pass | Fit (1 epoch) | Inference | Total |
|---|---:|---:|---:|---:|---:|---:|---:|
| legacy | 3005 MiB | **+2456 MiB** | 1324 MiB (four float16 roles loaded) | 3.9 s (+7.1 s load) | 20.2 s (19.0 obs/s) | 45.7 obs/s | 39.5 s |
| streaming, window 1 | 1040 MiB | **+491 MiB** | 612 MiB (index only) | 3.6 s | 16.1 s (23.9 obs/s) | 78.1 obs/s | 24.6 s |
| streaming, window 4 | 1230 MiB | **+681 MiB** | 612 MiB | 3.9 s | 17.3 s (22.2 obs/s) | 73.1 obs/s | 26.4 s |

Reading of the numbers. The legacy increment is the sum of the four float16 roles (4 × 145 MiB), the float32
inputs of train and val-select (2 × 240 MiB), the preprocessing temporaries of a whole role and the batch-64
inference activations. The streaming increment is the fixed torch state (≈ 320 MiB, see §1) plus the window:
going from one to four shards adds 190 MiB, i.e. ≈ 63 MiB per 64-observation shard (24 MiB float16 raw + 42
MiB float32 inputs, as the layout predicts), while the dataset size (384 → any N) does not enter. Verified
reading runs at ≈ 430 observations/s (1 536 observations in 3.6 s; sha256 + per-record metadata validation);
preprocessing to five channels at ≈ 270 observations/s (measured under concurrent test load). Streaming was
not slower than the legacy path on this CPU; the per-epoch re-read of the training shards (145 MiB here)
costs well under a second.

Weights differ from legacy in both streaming runs because 6 shards exceed both windows (different, deterministic
sample order; same algorithm). The single-window identity was shown in §1 and in `tests/test_b2_stream.py`.

## 3. Unit-level memory check (`tests/test_b2_stream.py::test_streaming_peak_memory_stays_below_the_whole_dataset_footprint`)

96 + 96 observations (train + val-select), 6 shards of 16, width 4, 1 epoch, subprocesses with the same
reset-based peak: legacy +704 MiB versus streaming (window 1) +301 MiB in the run recorded during
development; the test asserts that the gap exceeds half of the preprocessed training tensor (30 MiB), a
bound implied by the allocation pattern, not a tuned threshold.

## 4. What the measurements imply for the full frozen scale (reasoning, not measured)

Production layout: 8 groups per shard = 64 observations per shard, 0.406 MB per observation
([budget](b2_production_budget.md)); train 12 000 observations = 188 shards ≈ 4.7 GB float16.

| Quantity | Legacy (pre-E1) | Streaming (E1) |
|---|---|---|
| Resident data for training | all four roles float16 (≈ 8.4 GB) + float32 inputs of train and val-select (≈ 7.9 + 0.8 GB) + temporaries → does not fit the budgeted hosts | `window_shards` × 63 MiB + one gathered window copy + one batch: ≈ 0.25 GB (window 4), independent of N |
| Resident for the whole run | – | index arrays and projected metadata O(N) (a few MB at N = 21 350); logits/embeddings/plan logits per role (train: 12 000 × 137 × 4 B ≈ 6.6 MB at width 8) |
| Fixed | torch state ≈ 0.55 GB imports + ≈ 0.3 GB kernels (CPU build; GPU builds differ) | same |
| I/O per epoch | none after load | re-read and re-verify the training role: ≈ 4.7 GB per epoch; at the measured ≈ 430 obs/s verification this is ≈ 30 s per epoch on this container's disk (**estimate**) |

The bound rests on three code facts, each covered by a test: the open pass keeps only small arrays
(`_small`), training reads shards through a generator and keeps at most `window_shards` of them
(`_batches`), inference preprocesses one batch at a time (`infer_streaming`). It is not a measurement of a
12 000-observation run, which was not executed (not authorized, and the data do not exist yet).

## 5. Limitations

- Fixtures up to 384 training observations; no GPU; CPU timings vary with concurrent load (the §2 runs were
  alone on the machine, the §3 and preprocessing figures were taken while the test suite ran).
- NPZ shards are read with `numpy.load`, not memory-mapped; the artifact format is unchanged.
- The legacy path remains in `geoml.train` for other experiments and as the parity reference; it is no longer
  used by `geoml.b2_experiment`.

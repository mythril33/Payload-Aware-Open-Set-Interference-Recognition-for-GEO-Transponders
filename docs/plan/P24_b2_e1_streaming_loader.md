# P24 — E1: memory-bounded streaming data path for the canonical `geoml.b2_experiment`

Date: 2026-10-21. Work package E1 of [P23](P23_b2_production_readiness.md). Base `main`
`0f75dea9d2a87a43b71c168ff31f9dbfcf0e9280`; branch `feature/b2-e1-streaming-loader`. Engineering only:
no protocol, label, role, seed, loss or threshold semantics change; `benchmark_complete` stays `false`;
K18, K17d and OBS-CANCEL/2 remain **pending researcher decisions** and are not touched here.

## 1. Problem (verified in code at the base commit)

`geoml.b2_experiment.run_b2_experiment` called `load_b2_split` for all four roles (`iter_b2_shards` →
`np.concatenate`), then `geoml.train.fit` turned the whole training and validation roles into float32
tensors (`_inputs`) and `geoml.train.infer` did the same for every role and for the bound test-only and
matched artifacts. At the frozen scale (train 12 000 observations) this is ≈ 4.7 GB of float16 source per
role in memory plus ≈ 7.9 GB of float32 inputs for the training role alone (budget §2.1), which does not
fit the production plan. The separate P21b stage (`geoml.b2_data.FeatureRole`, `iter_batches`) already
streams `B2-features/1` shards; its format, receiver and loss convention differ from P20 and were used as
a reference design, **not** adopted (P23: "do not replace the P20 canceller with the P21b receiver").

## 2. Design (`src/geoml/b2_stream.py`)

| Component | Behaviour |
|---|---|
| `open_b2_known(root)` → `(manifest, identity, {role: B2Source})` | One bounded verification pass over the whole artifact (`read_b2_manifest(root, on_shard=…)`: descriptors, checksums, arrays, metadata, calibration, request/manifest consistency, reserved-role directories). Only small per-sample arrays survive the pass: `label`, `seed`, `plan_consistency` and a projection of the metadata (`scenario_id`, `event.kind`, `event.c_over_i_psd_db`, `matched` block). `identity` equals `geosim.b2_dataset.b2_fingerprint(root)` (tested). |
| `open_b2_test(root)`, `open_b2_matched(root)` | Same for the bound B2-test/1 (`family`) and B2-match/1 (`label`, `matched_bin`) artifacts. |
| `B2Source` | `shards(order)` re-reads verified shards in canonical or in a caller-given order (every shard verified again on each read: descriptor, sha256, arrays, metadata, and consistency with the index built at open time); `fetch(indices)` reads only the shards holding the requested rows (used for the paired spectrogram figures); `split()` exposes the small arrays with the keys the metric code already used; `from_arrays(split)` wraps an in-memory split as a single shard (tests, parity). Duplicate `(group, label)` pairs, out-of-range labels/bins/targets, groups outside the role's frozen range and shard/index drift fail closed. |
| `fit_streaming(train, val, cfg, window_shards)` | Same algorithm as `geoml.train.fit` (model, AdamW, OneCycle, CE + frozen center loss + plan BCE, K17b plan shift with full re-preprocessing, mirror/roll augmentation, val-select macro-F1 selection, training-only absolute reference computed from the identical per-sample values). Sample order: whole shards permuted per epoch when `n_shards > window_shards`; samples permuted inside each window of `window_shards` shards; a short remainder is carried into the next window so every epoch has exactly `ceil(N/batch)` optimizer steps (asserted at run time). With a single window the trainer is **bit-identical** to `geoml.train.fit` (tested, including K17b and augmentation). The checkpoint records the policy (`streaming` block); `save`/`load`, `expected_config` and `expected_provenance` are unchanged. |
| `infer_streaming(fitted, source)` | One shard resident; logits, embeddings, plan logits in canonical order (per-sample identical to legacy `infer` up to batch-boundary float effects; tolerance 1e-5 declared and tested). |
| `geosim.b2_dataset.iter_b2_shards(root, role, indices=None)` and the test/matched iterators | Optional sequence of distinct shard indices (permutation or subset); `read_*_manifest(path, on_shard=None)` callback. Both are additive; every existing call site and artifact layout is unchanged. |

`geoml.b2_experiment` now opens the three artifacts through these functions, trains with `fit_streaming`,
infers with `infer_streaming`, and keeps every role boundary, metric, threshold, reuse check, strict-JSON
output and report section. New configuration key `window_shards` (default 4) is part of `resolved()` and
therefore of the experiment fingerprint; it is **not** part of `TrainConfig`, so existing checkpoints
keep validating. `results.json` gains `runtime.loader` (mode, window, per-role shard counts).

### Memory model (what is and is not bounded)

Resident during training: `window_shards` raw float16 shards (spec, mask, residual, metadata records of
those shards) + their float32 model inputs + one gathered copy of a window during the in-window
permutation + one mini-batch and its augmented copy + model/optimizer/center state. For the production
layout (8 groups = 64 observations per shard) one shard is ≈ 25 MB raw and ≈ 42 MB preprocessed; the
default window of 4 shards is therefore ≈ 0.3 GB of data per window (plus the fixed torch overhead, ≈ 0.3
GB on this CPU build), independent of the number of observations. Resident for the whole run: per-sample
index arrays and projected metadata (O(N), a few MB at N = 21 350), logits (N × 8), embeddings (N × 16·width)
and plan logits per role — explicitly materialized because the metrics, Mahalanobis fit and calibration
need them; at full scale with width 8 this is ≈ 12 000 × 136 × 4 B ≈ 6.5 MB for the training role.

What is **not** zero-copy: `numpy.load` decompresses/reads every NPZ member into memory per shard. This is
bounded reading, not memory mapping; the artifact format was not changed to allow `mmap` (that would be a
new stage name under the artifact rules).

Cost of the design: every epoch re-reads and re-verifies the training shards (sha256 of each part file plus
the per-record metadata validation). On the pilot this is 0.2 s per 16-observation role; at full scale it is
≈ 7.5 GB of I/O and hashing per epoch for the training role (measured per-shard costs in
[b2_streaming_memory.md](../results/b2_streaming_memory.md)). A preprocessed cache was deliberately not
added (it would be a new derived artifact with its own provenance); it is listed as an option, not a gap.

## 3. Scientific invariants preserved (tests in `tests/test_b2_stream.py`, `tests/test_b2_experiment.py`)

- Roles: `train` → weights and Mahalanobis statistics; `val-select` → checkpoint only; `val-calib` →
  known-only thresholds; `test` once; `test-matched` and test-only families → frozen evaluation only.
  Sources carry their role; groups outside the role's frozen range, overlapping train/val groups,
  duplicated groups and test-only sources offered for fitting are refused.
- Channels and normalization: `_inputs`/`preprocess_dual` are called unchanged per shard; co/dual/
  dual_residual channel order and the shared co-pol carrier reference are untouched (sample parity test).
- Determinism: sample order depends only on `cfg.seed`, the shard counts and `window_shards`; two runs give
  identical weights and histories; the per-epoch shard orders are stored in the checkpoint.
- Fail-closed artifacts: checksum mismatch, missing files, missing manifest (incomplete generation),
  tampered request/manifest, mixed stages, wrong protocol, missing residual for `dual_residual`, index
  drift between open and stream.
- Outputs: `results.json`, `results_summary.json` (same drop rule), `predictions.json`, `results.md`
  keep their structure; `--reuse` validates checkpoints, scorers and calibrators exactly as before.

## 4. Measured (see [results](../results/b2_streaming_memory.md); bounded fixtures, no production run)

Numbers are in the results note; in short: on the real 64-observation pilot the streaming run reproduces the
legacy run **exactly** (identical training history for the three views, 48/48 identical test predictions,
unknown-score difference 0.0); on a 96 + 96-observation synthetic-layout fixture the data-dependent
resident increment of the streaming path is a fraction of the legacy one; on a 384-observation
synthetic-layout fixture the gap scales with the dataset while the streaming increment does not.

## 5. Limitations and honest scope

- The parity claim is exact only for a single window; with several windows the trainer is the same
  algorithm under a different, deterministic sample order. Full-scale training (30 epochs, 12 000
  observations) was **not** run; the memory bound is reasoned from the allocation pattern and measured on
  fixtures up to 384 training observations.
- The memory fixtures use the real writer, validator and layout with a stand-in simulator; they measure
  bytes and I/O, never recognition.
- Peak RSS includes the fixed Python/torch footprint (≈ 0.55 GB after imports, ≈ 0.3 GB of lazy kernel
  state on first use); the results note separates the import baseline, the post-import high-water mark and
  the implied data-dependent part.
- Multi-process generation, LOKO (E2), EDSC/XGBoost (E3), A5 dual-pol corruption (E4) and the CI job
  extensions (E5) are untouched.

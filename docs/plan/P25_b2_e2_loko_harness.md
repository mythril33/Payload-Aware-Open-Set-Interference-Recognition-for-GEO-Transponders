# P25 — E2: bounded A8 LOKO harness

Date: 2026-10-22. Base: `main@5a65062` (E1 merged in PR #9).
Stage: `B2-LOKO-harness/1`. Engineering implementation, **not a completed A8 benchmark**.

`geoml.b2_loko` implements the existing P18 A8 partition semantics without
changing B2 sampling, source artifact formats, cancellation, losses or gates.
It builds seven folds (each non-clean class held out, clean always retained),
with three explicitly recorded planned training seeds (0, 1, 2). There are 21
planned fits **per view**; planning multiple views multiplies the count.
Seed values are a deterministic harness choice, not a test-selected result.

## Data and fitting contract

- Verify the original B2-base/1 or B2-feat/1 artifact through E1. Check all four
  role ranges, complete paired groups and unique (group, label) rows.
- Remove the held-out variant from train, val-select and val-calib **before**
  preprocessing/reference estimation, optimizer/auxiliary loss updates, checkpoint
  selection, Mahalanobis statistics and rejection thresholds.
- A derived streaming view filters each verified shard and maps the remaining
  seven labels to contiguous indices in original label order. The clean index
  stays zero. The manifest and underlying arrays remain unchanged. Empty
  derived shards are omitted; raw shard checksums are still checked per read.
- Keep all eight variants of every test group. The held-out class is unknown;
  the other seven are known. P21a unknown families and K17c matched data are
  excluded from this slice, so their metrics cannot be confused with LOKO.
- Freeze Mahalanobis and all rejection thresholds before test inference.
  Provenance binds data identity, fold/row selection, roles, training config,
  window size and source hashes. Derived scorers/calibrators additionally bind
  checkpoint SHA256. Reuse validates existing derived files, rather than
  replacing incompatible ones. Nonempty directories without a checkpoint fail.

## Metrics

Unknown-positive AUROC, average precision, OSCR and known FPR at 95% unknown
TPR use the existing grouped-tie implementation. OSCR's known denominator is
all retained known test samples, including classification errors. Acceptance
and rejection use only known val-calib thresholds (inclusive acceptance).
Every rate carries sample/group counts. Accepted-known accuracy uses accepted
known samples only; an empty denominator is null.

Ranking CIs use a deterministic percentile bootstrap (200 replicates, seed
20261022): resample whole scenario groups once, with all seven known and the
held-out variant together. The model, scorer and threshold stay fixed.
Thresholded rate CIs use the existing scenario-cluster bootstrap. Fewer than
two groups gives null CIs. Training-seed variation is **not** included in these
intervals; no cross-seed summary is claimed.

## Bounded commands

```bash
# Planning only, reads/verifies existing artifacts; no fitting or evaluation.
python -m geoml.b2_loko --config configs/b2_feat.json \
  --data data/b2-feat-pilot --out runs/b2-loko-plan

# One CPU fold/view on <=2 groups/role; <=2 epochs, width<=8, batch<=32.
# Use a separately recorded smoke config; the full multi-view config is rejected.
python -m geoml.b2_loko --config configs/b2_loko_smoke.json \
  --data data/b2-feat-pilot --out runs/b2-loko-smoke --smoke-holdout cw
```

No production/sweep execution switch exists. Large artifacts are accepted for
planning, but refused for smoke execution; **use a separately generated bounded
pilot artifact**, rather than silently truncating the production data. Artifact
verification may read a large dataset before the execution cap rejects it.
Smoke execution saves a checkpoint, fitted scorer, thresholds, fold plan,
prediction rows and strict JSON results outside Git. A fresh output directory
is required when switching from planning to execution. `--reuse` validates a
checkpoint and deterministically reproduces the reports; it does not retune.

## Remaining E2 work and gates

This is the first E2 engineering slice. A production execution dispatcher,
authorized multi-fold/multi-seed scheduling/resumption, cross-seed aggregation
and full-scale resource measurements remain unimplemented. Resource caps
limit one invocation; they are not an authorization mechanism for launching
many smoke invocations as a sweep. No full A8 run was launched.

K18, K17d, OBS-CANCEL/2 and full compute decisions remain pending. The recorded
full-generation, full GPU and full LOKO authorizations remain absent.
`benchmark_complete=false`. E3 EDSC/XGBoost and E4 dual-pol A5 remain next
engineering slices; see P23. Verification and limitations are in
[`b2_loko_harness.md`](../results/b2_loko_harness.md).

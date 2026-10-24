# E7b independent read-only scientific review

Date: 2026-10-24. Base: `ed65eb54632fc4373accebc88452ddf0ff9fadfe`.
Two independent read-only reviewers examined the combined isolated-phase,
scoped-loader, CLI and LOKO code/tests. They edited no files and ran no
experiments or pytest commands. A separate AST/Git/JSON integrity audit and
`git diff --check` exited0. Implementation test evidence is recorded in
[the results ledger](../results/b2_e7b_execution.json), not attributed to
these reviewers.

## Findings and resolution

| Finding | Resolution and verification scope |
|---|---|
| Optional test-only/matched populations were not identified in final receipts; consistently re-signed data could drift during evaluation | Opening snapshots, artifact/role/sample identities and final bounded integrity verification precede result publication; optional drift negatives |
| Output paths could overlap read-only data/model/inventory inputs | Resolved-path overlap/alias checks in fitting, calibration, evaluation and LOKO; negative tests |
| LOKO lacked final source/runtime/frozen-file drift checks | Guards before held-out opening and after scoring, plus artifact-byte checks; drift negatives |
| Aggregation trusted saved point metrics | Ranking and threshold-rate point estimates and denominators are recomputed from frozen paired prediction rows; consistently re-signed wrong values are refused |
| A receipt could be aggregated despite RUNNING/FAILED cell status | COMPLETE status and matching cell identity are required; receipt is committed last |
| Mahalanobis native inspection checked too little fitted-population information | Seven-class dimensions, per-class train counts and configured regularization are checked |
| Aggregate CLI report could overwrite input data or existing work | Separate resolved report path, no data/matrix overlap and no overwrite |
| Rewriting the selection declaration could append cells beyond the output-root cap | Actual existing cell directories and matrix status must agree with the immutable selection; an adversarial re-entry test checks refusal |

All eight fixes were statically re-reviewed as resolved, including the final
selection-cap hardening on matrix SHA-256
`9c23f19d91e54752d112e4de926bf68bcb01a958a8c7dcfa2f6854398989a7d7`.
**No material finding remains open.** Exact delivered source hashes are
included in the machine-readable results ledger.

## Positive scientific checks

- Fitting reads train/val-select only; Mahalanobis uses selected-checkpoint
  train embeddings. Known-only val-calib calibration is separately invoked.
- Every native checkpoint/scorer/calibrator in the nine-cell inventory is
  verified before the first held-out source opens. Evaluation never fits,
  selects or calibrates. An explicit fixture inventory cannot impersonate
  full-protocol admission.
- The model receives calibrated spectra/operator-plan evidence and the
  existing P20 observation-derived residual. Artifact validation of simulator
  metadata is not an added model feature. No P21b substitution is introduced.
- LOKO removes held-out variants before preprocessing/fitting/selection/
  calibration/statistics. Scenario variants remain paired in evaluation.
- Aggregation uses separate seed metrics and a common scenario-group draw
  across fixed seed models. It does not pool cross-seed or cross-holdout
  score populations or present a cross-holdout CI.
- Existing streaming trainer definitions, `train.py`, `model.py`, configs,
  simulator/cancellation sources, frozen P18/P20 and authoritative decisions
  remain unchanged. The existing numerical K18 noninterference tests remain
  required; source edits invalidate historical checkpoint reuse.

## Qualification and boundaries

Saved **per-cell** confidence intervals/bootstrap metadata are verified by
their artifact hashes; their point estimates and denominators are recomputed.
This review does not claim independent regeneration of those saved intervals.
Complete aggregate group intervals are recomputed from frozen rows.

Nine-cell admission is bounded-fixture engineering evidence, not nine
production-trained checkpoints. CPU caps do not authorize repeated smoke
invocations as a sweep. GPU parity and production-scale performance remain
unverified. R1–R10, K18, K17d, OBS-CANCEL/2 and production compute gates remain
pending. `benchmark_complete=false`.

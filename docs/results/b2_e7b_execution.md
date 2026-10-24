# E7b — isolated execution and bounded LOKO verification

Date: 2026-10-24. Delivery base: `ed65eb54632fc4373accebc88452ddf0ff9fadfe`.
Contract: [P31](../plan/P31_b2_e7b_isolated_execution.md).
`benchmark_complete=false`; no production authorization is granted.

## Scope and verified starting evidence

PR22 and PR23 were already merged. PR23 head
`7a46f5774ddcf9f99af425265a6b0cc2b0ebdb57`,
[Actions run40047344666/job120731984575](https://github.com/mythril33/Payload-Aware-Open-Set-Interference-Recognition-for-GEO-Transponders/actions/runs/40047344666/job/120731984575)
completed successfully. Raw logs show 107 passed in106.48s and1525 passed,
7 skipped in716.07s: **1632 passed, seven skips, zero failures**. The old
quiet log does not list skip node IDs/reasons. These are historical CI
results, not tests of the new E7b source. E7a's refreshed raw journal/head
and capped physics evidence are preserved; the supervisor was not redeveloped
or rerun for this work.

The previous uncommitted E7b work was preserved in a named Git stash, and
selected engineering changes were integrated onto the newer main on
`feature/b2-e7b-isolated-execution`. Superseded local supervisor-evidence
edits were retained in the stash rather than applied over PR23's evidence.

## Execution guarantees and limits

- The canonical runner offers separately invoked `train-only`, `calibrate`,
  `freeze` and `evaluate` modes. Train/val-select content alone is opened for
  fitting; selected-checkpoint Mahalanobis statistics use train only.
- Known val-calib is opened in a separate frozen-model calibration phase.
  P20's clean-alarm arithmetic and known-acceptance calibration remain
  distinct. Clean alarm uses strict `score > threshold`. Two clean fixture
  observations cannot establish population Pfa=5%.
- Proposed-full admission verifies all nine distinct view/seed native
  checkpoints, scorers and calibrators before opening any held-out source.
  The explicit fixture profile cannot claim full-protocol admission. Every
  evaluation input is read-only and output paths must be disjoint.
- Phase markers bind exact bytes, data/role/source/configuration identities,
  library versions, CPU/thread settings and selected checkpoints. Optional
  test-only/matched identities and sample populations are also recorded and
  reverified before publishing results. Incompatible historical checkpoints
  are refused, never relabelled.
- New execution is **CPU-only, at most two groups/role, two epochs, width8,
  batch32**. The nine-cell gate is tested with tiny stand-in models. This is
  not a production-width16/30-epoch launcher or a completed benchmark.
  The legacy coupled pilot is retained under a12-group/role limit.
- LOKO plans seven non-clean holdouts × three seeds × explicit views.
  Held-out rows leave fitting, selection, calibration and train-derived
  statistics before preprocessing. An immutable selection executes at most
  two CPU cells per output root; no21/63-fit sweep command is enabled.
- Aggregation validates native artifacts and paired prediction populations.
  Missing cells fail closed by default; explicit partial summaries have null
  full-matrix metrics. Seed variation and shared-scenario bootstrap intervals
  are separate; neither cross-seed nor cross-holdout scores are pooled.

## Validation ledger

The machine-readable [verification record](b2_e7b_execution.json) records
actual commands, source identities, environment, elapsed time, peak process
RSS and outcomes. Earlier local/remote results are kept separate from this
session's runs. The full regression and final PR-head CI are reported only
after execution; a pending check is never called a pass.

The native composition fixture uses the canonical writer/validator, real
streaming trainer and real source/native-artifact identities, with deterministic
stand-in RF/cancellation. It has64 observations (16 per role), one CPU fit,
separate calibration, a one-cell fixture freeze and separately invoked test
evaluation. It checks actual file reads and unchanged input bytes. The
separate nine-cell adversarial test uses tiny synthetic arrays. Neither uses
the real held-out test population to choose this implementation.

Focused implementation subsets passed separately: isolated phases42,
CLI/legacy47, scoped loader25 and final LOKO44. These overlap and must not
be added into a unique-test total. On the final source, native composition
plus both LOKO suites passed45 tests in93.49s (process97.024902s,
peak557596KiB). Three corrected ledger-reference/rendering checks passed
in2.28s (process3.090984s, peak90220KiB).

The broader combined focused command reached its600s cap (exit124,
process600.113988s, peak653532KiB) without a final pytest summary, after
showing one malformed verifier-reference failure and seven skip markers.
It is **not a pass**. The verifier references were corrected and checked
separately; no scientific assertion was weakened. The full regression is
an independently recorded command. Final matrix-cap changes are covered
by the final45-test run and full regression rather than the earlier
combined command's imported module snapshot.

K18 noninterference was also checked separately on the final source:
**15 passed in29.15s** (process30.328044s, peak374024KiB), covering original
training-loop bit identity, gradients, loss-call counts, validation-role
exclusion and detached autograd accounting. No test in this subset skipped.
The source-files fingerprint is
`38dda15e6c626d8ef1c155276a16efa66abf319856fa1c0efb908635be3f3bae`;
individual source SHA-256 values are in the JSON ledger.

The first full-regression attempt was invalidated by an integration error:
the integrator updated the gate JSON after the module-scoped supervisor
fixture had locked it. Its recorded and current hashes differ, and the
journal explicitly names that drift. A fresh stable supervisor baseline
passed1 test in24.33s. The contaminated run was stopped at1167.736448s
(peak923788KiB), without a final pytest summary; it is not a passed suite.
Its fixtures/logs are preserved outside Git. The final rerun uses a fixed
commit, source, tests and gate file throughout. No assertion was relaxed.

## Scientific review and production blockers

Independent read-only review is recorded in
[the E7b review](../research/b2_e7b_review.md). Material findings are fixed
and verified before delivery; read-only review itself is not test execution.

K18, K17d and OBS-CANCEL/2 remain pending. All29 candidate parameters and
R1–R10 remain unapproved, as does production compute. The
[recommendation table](../plan/B2_E7B_DECISION_RECOMMENDATIONS.md) explains
the width8/16 budget discrepancy and alternatives without freezing choices.
Source changes create a new checkpoint provenance identity; old checkpoints
cannot be reused under it. Production host/backup designation, approved
recipe and interruption policy, target-host throughput/memory/GPU parity,
authorized generation and full LOKO execution remain outstanding. No new
recognition-performance or cancellation-quality claim is made.

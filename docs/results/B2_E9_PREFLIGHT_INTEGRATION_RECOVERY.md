# E9-Preflight — concurrent-merge integration recovery

Date: 2026-10-24. This is bounded CPU test/documentation maintenance only.

## Independently verified chronology

- Scientific approval main: `d14f31de35ca9de3b88c0c0f8e55d99bbfd98bb7`.
- Initial recovery PR27 was merged externally before its two remaining
  full-regression failures were repaired. Those failures remain failures in
  the [original report](B2_E9_PREFLIGHT_CI_RECOVERY.md).
- Recovery PR28 head `1539831995b637a187330fd9ac937ee46bf364dc` passed its
  complete exact-head CI: [run40095376387/job120876380654](https://github.com/mythril33/Payload-Aware-Open-Set-Interference-Recognition-for-GEO-Transponders/actions/runs/40095376387/job/120876380654).
  Raw logs: E4 **107 passed117.82s**; remaining repository **1718 passed,
  zero failed/skipped,46 warnings747.71s**. Total **1825 passed**.
  Synthetic merge69278f5eff4ea04fe832487a12c237ea524aeb3a, Python3.12.15.
  Raw log SHA256:
  `481a10102e68cf735514f5c71ccbc4f728367803c84aaba472bacdeb192bb084`.
- Local complete repository command on that same immutable head:
  **1710 passed,8 skipped,46 warnings1323.91s**, exit0,
  process1326.607244s, child peak RSS1313528KiB. Python3.12.14.
  One E1 RSS test cannot reset `/proc/self/clear_refs`; seven golden-capture
  cases do not reproduce on this machine/Torch build. Live original-loop
  parity tests still apply. Skips are not passes and do not apply to the
  zero-skip final remote run.
- PR28 was created as a draft and then merged by mythril33 externally at
  2026-10-24T12:59:11Z as d7df413e04032f7abdbb3bb7134b037d680908b7.
  The agent did not merge or mark it ready.
- A subsequent external PR29 merge advanced main to
  **a1d0afc522d2207739dc31f352cd9511f8c0a4bc**. This is this fix's base.
  PR28's success cannot certify that later tree.

## Root cause and minimal repair

The concurrent merge renamed the CLI test's local report from `blocked`
to `gate_report` but retained a later `== blocked` assertion. The full
JSON equality introduced by PR28 therefore raised NameError on the merged
main. This was reproduced before editing: **one failed10.35s**,
process10.894690s, peak134868KiB, exact base a1d0afc.

Only the test is repaired: compare with `gate_report`, retain PR29's
explicit blocked-key set and approved-science checks, and explicitly
require verdict BLOCKED and both production_authorized/benchmark_complete
false. The complete normal/allow-blocked JSON must match. Inspection's
exit-code override is not compute authorization.

The repaired working-tree target passed **one test10.95s**,
process11.762923s, peak258728KiB. This precommit evidence is identified by
base a1d0afc and exact test SHA256 in the JSON ledger; it is not labelled as
a future commit run. No production defect or source edit is required.

The focused safety/freeze/historical-candidate/P31 selection passed
**68 tests12.06s**, process13.517731s, peak376356KiB, no warnings/skips.
A broader three-file attempt hit its explicit300s cap (exit124,
process300.101124s, peak318928KiB); it produced no final pytest summary
and is **not a passed suite**. The complete exact-head CI commands below
must still execute. Syntax compilation and whitespace checks passed.

## Safety state: unchanged before and after

| Control | Before | After |
|---|---|---|
| K18/K17d/OBS-CANCEL-2 | APPROVED, complete provenance | unchanged |
| R1–R10 | approved scientific record, activation=false | unchanged |
| full_generation/full_gpu_training/full_loko_sweep | NOT_AUTHORIZED, approval=null | unchanged |
| GPU probe | NOT_AUTHORIZED | unchanged |
| PRODUCTION_LAUNCH_ENABLED | False | unchanged |
| benchmark_complete | False | unchanged |

No source, config, script, workflow, official approval/memorandum,
RF/label/observation/loss definition, resource ceiling or P31
nine-cell/test-isolation rule changes. Source/control and official-record
hashes are checked around every local test command. Historical candidate
records remain non-executable. R6 TF32-off is a scientific requirement,
not a claim that an executable GPU runner already enforces it.

The read-only independent reviewer confirmed the integration root cause,
recommended the explicit NO-GO guards retained here, and found no
safety-control weakening. The reviewer edited nothing and ran no
experiments. The legacy A5 static PENDING report annotation is still a
known presentation limitation; canonical approved records are authoritative.

## Validation and delivery

The [JSON ledger](b2_e9_preflight_integration_recovery.json) records actual
commands, base/test identities, counts, timings and environment. This
commit-time snapshot distinguishes completed precommit checks from final
exact-head local/remote checks. Completed exact-head results and raw-log
references are published in the new draft PR after execution.

Existing CI is CPU-only and bounded. Full remaining-repository command:
`python -m pytest -q -rs --ignore=tests/test_b2_a5_plan.py --ignore=tests/test_b2_a5_replay.py --ignore=tests/test_b2_a5_eval.py --ignore=tests/test_b2_a5_negative.py --ignore=tests/test_b2_a5_resume.py --ignore=tests/test_b2_a5_summary.py`.
The separate E4 step runs those six files explicitly. Syntax compilation
and whitespace checks are also required; no lint tool is configured.
Warnings are recorded rather than suppressed.

No full generation, GPU probe/training, production held-out inference,
full LOKO or E9 executor development was authorized or run. The generated
readiness snapshot remains **39PASS/0FAIL/16BLOCKED/1NOT_RUN**, overall
BLOCKED. E9 engineering is a separate future milestone after this recovery
and independent review; operational execution remains NO-GO.


# E9-Preflight — post-approval CI recovery and safety audit

Date: 2026-10-24. Verified remote main:
`d14f31de35ca9de3b88c0c0f8e55d99bbfd98bb7` (PR26 merged).
This is a test/documentation recovery, not E9 executor implementation.
During validation, PR27 was merged externally as
`a5e3b7b8a87ed7b9fb41f513ddb8bb6b685ec4b1` before its two remaining
test failures were fixed. The agent did not invoke merge. That main tree
equals recovery head29db36a; the follow-up advances from it by fast-forward,
preserving local work and all source/scientific records.

## Root cause, verified before modifications

[Failed run40089480035/job120859075834](https://github.com/mythril33/Payload-Aware-Open-Set-Interference-Recognition-for-GEO-Transponders/actions/runs/40089480035/job/120859075834)
tested PR26 head `204c835df72858ef46bb146deaa78eee77124fb1`.
Raw logs show **106 passed, one failed in136.98s** in the E4 step;
the subsequent repository-wide step was **skipped**, not passed.
`test_a_pilot_never_changes_the_readiness_gates` expected scientific gates
to remain PENDING_RESEARCHER after those gates had legitimately been
approved. It also never invoked a pilot, so did not test its named invariant.

The audit found further previously unreached test regressions:

| Location | Incorrect current-state assumption | Repair |
|---|---|---|
| A5 negative test | Scientific PENDING/null; no pilot invocation | Actual bounded stand-in pilot, full gate bytes/JSON before/after, independent approval provenance and closed compute checks |
| Scientific figures | Current gate state treated as a historical pilot snapshot | Preserve historical result checks; validate current scientific APPROVED separately from compute NOT_AUTHORIZED/null |
| E8 record test | Current six gates all pending/null | Keep historical E7/E8 candidate unchanged; distinguish current scientific approval from operational NO-GO |
| Preflight approval test | Requires consistency PASS entries that the checker never emits | Compare the twins explicitly and reject consistency failures; retain mismatch negatives |
| Two supervisor tests | Four blocked production prerequisites, first reason K18 | Three scientific prerequisites now pass; generation authorization remains blocked and no child may spawn |
| Generated checklist | Three scientific rows still BLOCKED/PENDING | Regenerate with the unchanged checker;39PASS/0FAIL/16BLOCKED/1NOT_RUN, overall BLOCKED |
| Full-regression CLI case | Six BLOCKED gates | Require four PASS/three BLOCKED and identical closed-authority JSON with or without --allow-blocked |
| Full-regression E7 proposal case | Historical candidate gate snapshot equals today's gate state | Preserve historical PENDING/null candidate; separately check current scientific approval and closed compute |

The final two rows were exposed by the subsequent complete regression,
not the initial search. They were independently diagnosed and repaired only
in tests; the historical E7 proposal JSON was not rewritten or activated.

The original test failed locally before editing (one failure,3.44s).
Five related current-state tests also failed before editing (five failures,
4.51s). The stale checklist was separately reproduced (one failure,1.23s).
These are baseline failures, not successful checks. Full commands, exact
HEADs, timing, peak RSS and outcomes are recorded in the
[machine-readable ledger](b2_e9_preflight_ci_recovery.json).

## Classification of pending-state references

The repository-wide search initially found48 PENDING_RESEARCHER references.
Historical E7/E8 candidate records, historical result/plan text and
deliberately constructed pending/memorandum-mismatch fixtures remain valid.
They are preserved. Critical pending-with-approval, missing-provenance,
compute-ceiling, no-spawn, production-disable and unbounded-command
rejections remain intact. The existing workflow already correctly checks
scientific provenance and closed compute gates, so it is unchanged.

Known presentation limitation: `src/geoml/b2_a5.py` still emits static legacy
PENDING scientific labels in its pilot authorization annotation. Those
labels are not the authoritative readiness JSON or an execution control;
its compute labels remain NOT_AUTHORIZED_NOT_STARTED. This recovery does
not change that source annotation. The test compares the actual canonical
gate file and does not reinterpret legacy report annotations as current
scientific decisions.

## Gate status before and after this recovery

| State | Verified main before | Recovery after |
|---|---|---|
| K18, K17d, OBS-CANCEL-2 | APPROVED with researcher provenance | Unchanged |
| R1–R10 scientific protocol | Approved, activation=false | Unchanged |
| Full generation / GPU training / full LOKO | NOT_AUTHORIZED, approval=null | Unchanged |
| GPU probe | NOT_AUTHORIZED | Unchanged |
| PRODUCTION_LAUNCH_ENABLED | False | Unchanged |
| benchmark_complete | False | Unchanged |

No `src/`, production config, supervisor/preflight script, workflow,
authoritative approval record, frozen RF/loss/observation protocol or P31
isolation rule is changed. New negative tests cover all three scientific
gates' missing provenance, pending approvals and memorandum mismatches;
all three compute gates reject bare status changes or copied scientific
approval. Historical candidates and the approved document-only scientific
record must all be rejected as executable B2 configs.

R6's TF32-off policy remains a recorded scientific requirement. It is not
enforced by a new GPU runner here; existing tests check that distinction.
No production dataset, GPU probe/training, full LOKO or production held-out
inference is authorized or executed. Existing CPU unit fixtures are bounded
and are not recognition-performance evidence.

## Verification and review

The read-only audit independently identified the stale assertions and the
missing checklist regeneration. Review of the patch found no weakened
safety control. One test-quality finding was fixed: pending-gate negatives
clear memorandum actor fields while retaining the gate's approval record,
so that rejection cannot pass only because of unrelated memorandum fields.
The reviewer edited nothing and ran no tests/experiments.

Completed evidence on recovery revision
`29db36ae17c7af15e8eb904a3b1e8ca59e484e72`:

| Check | Passed | Failed | Skipped | Warnings | Pytest seconds |
|---|---:|---:|---:|---:|---:|
| Originally failing target |1|0|0|0|19.97|
| Focused safety/freeze/candidate/P31 |68|0|0|0|13.56|
| Local exact E4 matrix |107|0|0|0|216.76|
| Local complete repository CI command |1708|2|8|46|1212.55|
| GitHub E4, run40092535088/job120867990644 |107|0|0|0|143.84|
| GitHub repository command, same run |1709|2|7|46|943.80|

Both complete runs found the same CLI count and historical-proposal
comparison failures. They are not passed suites. The final two-function
repair plus candidate/freeze checks passed **11 tests in12.16s** before
the follow-up commit; the ledger identifies the parent HEAD and exact
modified test hashes rather than claiming that working-tree run tested a
future commit. No source, config or scientific record changed.

Local skips: one E1 peak-RSS check could not reset
`/proc/self/clear_refs`; seven golden-capture comparisons do not reproduce
on this machine/Torch build. Remote skips were the seven capture cases;
the live original-loop parity tests remain applicable. The46 warnings are
the existing Matplotlib `set_bad` PendingDeprecationWarning, not suppressed.

Syntax compilation and diff checks passed. No separate lint tool is
configured. The follow-up runs the complete repository CI command again
with a fixed HEAD and immutable source/test/approval files. This file is
a commit-time diagnostic snapshot. Current exact-head local/GitHub results,
including final run/job links, are published in
the successor draft PR for
[the recovery branch](https://github.com/mythril33/Payload-Aware-Open-Set-Interference-Recognition-for-GEO-Transponders/tree/fix/b2-e9-postmerge-ci-gate-regression)
after execution. PR27 records the initial failed recovery revision;
pending or skipped checks are never called successful.

E9 executor engineering remains a separate future milestone after this
recovery and independent review. All compute and release controls remain
NO-GO, including the separate GPU probe authorization.

## Post-merge addendum — exact-head CI of PR #27 failed; follow-up fix

PR #27 was merged as `a5e3b7bd` while its own exact-head run was red:
[run 40092535088 / job 120867990644](https://github.com/mythril33/Payload-Aware-Open-Set-Interference-Recognition-for-GEO-Transponders/actions/runs/40092535088/job/120867990644),
head `29db36ae17c7af15e8eb904a3b1e8ca59e484e72`. The gate step, compile step and
E4 step passed; the repository step ended **2 failed, 1709 passed, 7 skipped in 943.80 s**
(the 7 skips are the runner-specific K18 golden captures,
`tests/test_b2_train_diagnostics.py:392`). Both failures reproduced on main
`a5e3b7bd` (2 failed in 58.65 s) and are stale current-state assumptions, not
safety defects:

| Test | Stale assumption | Repair |
|---|---|---|
| `test_b2_production_preflight.py::test_command_line_exit_codes_strict_json_and_no_overwrite` | `gates` reports 6 BLOCKED | exactly the three compute gates are BLOCKED, none FAIL, and K18/K17d/OBS-CANCEL-2 are PASS |
| `test_b2_training_footprint.py::test_proposal_is_an_unfrozen_unapproved_candidate` | the live gate file equals the E7a proposal's snapshot | the proposal stays a fixed historical snapshot that authorizes nothing; live compute gates must equal it (NOT_AUTHORIZED, approval null); live scientific gates must be APPROVED with a complete record |

Mutation check (gate file temporarily altered, then restored byte for byte): a
compute gate set APPROVED with a copied scientific approval, and a scientific
gate reverted to PENDING, each fail both repaired tests. No `src/`, `scripts/`,
`configs/`, workflow, approval record or gate JSON changed; no negative test
was weakened or removed.

Verified gate state on main `a5e3b7bd` (audited, unchanged by this fix):
K18, K17d and OBS-CANCEL-2 `APPROVED` with `approved_by` `mythril33`, ISO
`approved_at` 2026-10-24T11:14:11.155Z and the record
`docs/plan/B2_E9_SCIENTIFIC_DECISION_APPROVAL_2026-10-24.md`, mirrored in the
E5 memorandum (status, actor, time, record equal); `full_generation`,
`full_gpu_training`, `full_loko_sweep` `NOT_AUTHORIZED` with `approval: null`
in both files; GPU probe `NOT_AUTHORIZED`; `PRODUCTION_LAUNCH_ENABLED=False`;
`benchmark_complete=false`. Local full suite on the fix: **1825 passed, 0
failed, 0 skipped** (1058.92 s, CPU, Python 3.13). Exact-head CI for the
follow-up is recorded in its pull request.

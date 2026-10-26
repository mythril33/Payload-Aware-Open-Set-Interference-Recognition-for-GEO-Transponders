# B2 E18 — synthetic executor lifecycle verification

2026-10-25. Engineering only. **DR-04 NO-GO — NO COMPUTE AUTHORIZED.**
No production dataset, GPU discovery/probe/training, D-5 sweep, LOKO or held-out inference was performed. No real signing
credential, grant or revocation was created. Every key, signature, record, device and shard used by the E18 tests is fabricated, lives
in a temporary directory and is discarded with it. This report records evidence about **documents, fabricated bytes and control flow**;
passing tests prove execution of the lifecycle, not recognition quality and not permission to run anything.

## Baseline and preserved work

| Item | Value |
|---|---|
| Verified base at E18 start | `ad3e241d63875c4603b5843d8ba7a9fe15532253` (PR #41 merged) |
| E18 delivery PR | [#42](https://github.com/mythril33/Payload-Aware-Open-Set-Interference-Recognition-for-GEO-Transponders/pull/42), final head `1cbbcc5ebb334b84e0d076f09261abb2262233a3`, **merged by the researcher** as `5efa287` while the follow-up below was still open |
| Follow-up [#43](https://github.com/mythril33/Payload-Aware-Open-Set-Interference-Recognition-for-GEO-Transponders/pull/43) | head `8c26490f3a16ed3106b28030c9bf761676c788aa`, **also merged by the researcher** as `4ea511b` at 20:44:29 UTC — before the verification results, the DURUM entry and the fix of one new test (`357c15d`, pushed 27 s later) existed on the branch |
| This change | a further draft PR carrying exactly those unmerged files, branch restarted from `4ea511b` (the merged PRs were not reused); nothing is merged automatically |

The merge happened before this report, the DURUM entry and the second review's fixes existed, and the readiness CI on the merged head
was red (below). Those facts are recorded here rather than rewritten: the merged state is a fully working synthetic lifecycle whose
**test suite exhausted the CI runner's disk**; PR #43 fixed that and the findings of the second independent review. It too was merged
before its own readiness run had been repaired: `main` at `4ea511b` therefore contains one new test with a fixture-order defect (the full
readiness suite is red on it: 1 failed, 4538 passed) and a report whose results sections still read "pending". This change repairs both.

## Delivered (all synthetic-only; none is a production path)

| File | Role |
|---|---|
| `scripts/b2_e18_lifecycle.py` | `SyntheticExecutorLifecycle`: PREPARED → EVIDENCE_VERIFIED → ADMISSION_CHECKED → SYNTHETIC_STAGE_RUNNING → SYNTHETIC_STAGE_VERIFIED → SYNTHETIC_BACKUP_VERIFIED → SYNTHETIC_STAGE_COMPLETE; BLOCKED / STOPPED / QUARANTINED; `recover()`; `production_gate()` (always BLOCKED). No production-running state. |
| `scripts/b2_e18_synthetic.py` | fake clock and resources, fabricated-device/K17d attestor, bounded fabricated-shard producer |
| `scripts/b2_e18_ci_policy.py`, `.github/workflows/b2-e18-lifecycle-ci.yml` | PR-relative scope guard, workflow lint, gate-decision matrix; judge taken from the base copy |
| `tests/e18_support.py`, `tests/test_b2_e18_{lifecycle,trust_resources,recovery,acceptance,ci_policy}.py` | fabricated world, 5 test modules |
| `docs/plan/B2_E18_EXECUTOR_LIFECYCLE.md`, `docs/operations/B2_E18_{STAGE_BOUNDARY_CHECKLIST,FAILURE_RECOVERY_RUNBOOK}.md` | design with the before/after matrix, checklist, runbook |
| this report, `docs/plan/DURUM.md` entry | status |

No E9–E17 module, `src/`, `configs/`, scientific record, canonical gate, memorandum or older workflow is edited. `PRODUCTION_LAUNCH_ENABLED`
stays `False`, the two-group fixture cap, `PINNED_TRUST_ROOT=None` and the E9/E14/E16/E17 refusals are unchanged and re-asserted by tests.
The follow-up touches only E18-scoped files (the guard enforces this against the PR merge base).

## What the lifecycle was shown to do (fabricated bytes)

* A complete known (576 shards / 18,400 observations) → test-only (125 / 2,500) → matched (38 / 450) run: 739 shards, durable
  descriptor-last publication, E16 admission barrier, per-role backup with byte-checked restore, journaled hash-chained ledger with an
  independent anchor, fresh signed (fabricated-root) evidence at every stage start/end and on a schedule, E16 boundary reports at
  `pre_launch`, `after_known`, `after_test`, `after_matched`. Later request identities are derived from completed predecessor manifests.
* Controlled interruption and crash recovery that never produces a shard twice; restart allowance; durable quarantine of corrupt,
  orphaned, substituted or non-synthetic shards with evidence preserved byte for byte.
* Fail-closed behavior on revoked/expired/stale/forged evidence, altered source or data, a changed execution-boundary canary, stage-order
  and role-isolation violations, K17d deviations, resource/timing breaches, journal or anchor tampering, backup rot or outage.
* `production_gate` evaluates the public E17 entry and always returns BLOCKED; `PRODUCTION_LAUNCH_ENABLED` is observed, never set.

## Environments

Local: `/workspace/.venvs/geosim`, Python 3.13.16 (CI uses 3.12.15 on `ubuntu-latest`), `OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2
MKL_NUM_THREADS=2 PYTHONHASHSEED=0 CUDA_VISIBLE_DEVICES=''`, `ssh-keygen` from the OS package for the fabricated ephemeral ed25519 keys.
These are test settings, not a qualified production environment or a resource grant.

## Test and mutation evidence

| Check | Result |
|---|---|
| E18 suite on the final code (5 modules; local, Python 3.13.16, fixed `--basetemp`) | **421 passed** in 790.32 s: lifecycle 75, trust/resources 86, recovery 114, acceptance 12, CI policy 134; peak temp footprint 108,200 KiB in 22,718 entries |
| Same five modules at the merged head `1cbbcc5` (before the disk fix) | 382 passed locally (724.08 s on the pre-fix run recorded in the previous session); the E18 workflow ran 2703 tests (382 + the 2321-test E13–E17 regression selection) |
| Mutation testing, rounds 1–2 (earlier in the work) | 48 hand-written mutants of the lifecycle defences; 4 survivors were found, tests were added, all 48 killed |
| Mutation testing, round 3 (this follow-up) | 19 mutants of the new defences (signed-expiry bound, expiry taken as the later one, no pre-shard revocation recheck, observer skew final or not blocked at resume, several or out-of-order shards adopted, adoption not journaled, backup outage quarantined at recovery or at a boundary, missing backup counted as outage, each standing resume check removed, resumable without a journal, K17d/clock errors escaping): **19 of 19 killed**; every pattern applies exactly once and the harness restores the file (`git diff` empty afterwards) |
| CI-policy module | 134 passed; the real E15/E16/E17/E18/readiness workflows still lint clean (their reviewed `python - <<` checks stay acceptable) |
| `python scripts/b2_e18_ci_policy.py lint .github/workflows`, `gate-decision` | ok; `CLOSED_CANONICAL` accepted, `execution_permitted=false` |

Failures retained during development (none was a production execution): a docstring that named the signer tool tripped the source
tripwire (reworded; the tripwire is right), the heredoc ban in the first lint draft rejected the reviewed older workflows (narrowed to
`from/import geosim|geoml` and `git+` installs), and an interim local run was discarded after that docstring failure and repeated on the
final code; and the fixture-order defect in one new test described under *CI evidence*. Earlier-session failures and their fixes are
recorded in the commit history.

## Independent reviews (model agents — **not** human approval)

Two read-only red-team reviews were run by a separate model agent. A model-agent review is engineering evidence only; it approves nothing
and does not replace the human decisions listed in the lifecycle design.

**Round 1** (before the merge; 18 findings R1–R18 on custody, backup freshness, trust staleness, the execution-boundary canary,
adopted shards, resource observation and CI judging): fixed in `8dbdd87` with tests; R12 (AST tripwire) is documented as a tripwire.

**Round 2** (read-only, against `1cbbcc5`/`5efa287`): **no BLOCKER or HIGH finding, and no path to real production generation, GPU work,
training, a real credential, or to flipping `PRODUCTION_LAUNCH_ENABLED` / `FIXTURE_MAX_GROUPS` / `PINNED_TRUST_ROOT` or weakening the
E9/E13–E17 contracts.** Findings and dispositions:

| # | Sev | Finding | Disposition |
|---|---|---|---|
| S1 | MED | the CI judge can still be rewritten by the PR it judges (the workflow file is the PR's own) | partly fixed: the workflow is outside the E18 scope, the lint requires the guard steps, docs no longer overclaim; **the real protection is repository settings (required reviews / rulesets / CODEOWNERS), which this repository cannot configure or verify — external** |
| S2 | MED | recovery adopted any number of form-valid unjournaled shards | fixed: only the single in-flight, next-planned shard is adopted and journaled (`adopted_at_recovery`); several or out-of-order are `QUARANTINED` |
| S3 | MED | the 300 s staleness bound ignored the signed answers' own `expires_at` | fixed: the earlier expiry bounds the verification |
| S4 | LOW | an observer/clock disagreement killed a legitimate run for good | fixed: `BLOCKED` at a resume, resumable interruption (`OBSERVER_CLOCK_SKEW`) mid-run; downtime counting against the wall budget is documented |
| S5 | LOW | backup outage mislabelled `backup_mismatch` at recovery and at boundaries | fixed: recovery refuses without writing; at a boundary it is `backup_unavailable`; a missing backup stays a mismatch |
| S6 | LOW | revocation rechecked after, not before, the next shard | fixed |
| S7 | LOW | per-stage ceilings enforced run-wide | accepted (conservative), documented |
| S8 | LOW | a resume skipped the boundary checks | fixed: standing checks (canary, later stages empty, consumers, K17d) before any byte |
| S9 | LOW | workflow lint is a text tripwire | extra patterns (`git+` installs, `from/import geosim|geoml`, computed `python -m`), docstrings and docs softened |
| S10 | INFO | AST tripwire can be evaded; module docstring over-claimed | documented as a tripwire; docstring corrected |
| S11 | INFO | design doc linked a missing report; handoff said "not started" | this report; handoff carries a status note |
| S12 | INFO | one trailing unanchored entry can be injected by a ledger-only writer | accepted residual (denial of service only), documented |
| S13 | INFO | early interrupt claimed resumable; K17d source / malformed clock escaped as raw errors | fixed |
| S14 | INFO | scratch fixture deleted failing trees; CI-policy module not covered; `ignore_errors` hides leftovers | failing trees are kept; the module is covered; `ignore_errors` accepted |
| gaps | — | two unanchored entries and the inode alias to a declared production root were untested | tests added |

Both reviews are **model-agent assessments, not human approval**; no human review of E18 has taken place in this work.

## CI evidence (raw logs inspected, not inferred from a merge)

| Head | E18 workflow | Readiness workflow |
|---|---|---|
| `1f5b631` | [40208970152](https://github.com/mythril33/Payload-Aware-Open-Set-Interference-Recognition-for-GEO-Transponders/actions/runs/40208970152) success | [40208970151](https://github.com/mythril33/Payload-Aware-Open-Set-Interference-Recognition-for-GEO-Transponders/actions/runs/40208970151) success: 4419 passed, 7 skipped, 1344.32 s |
| `8dbdd87` | [40212609279](https://github.com/mythril33/Payload-Aware-Open-Set-Interference-Recognition-for-GEO-Transponders/actions/runs/40212609279) success | [40212609212](https://github.com/mythril33/Payload-Aware-Open-Set-Interference-Recognition-for-GEO-Transponders/actions/runs/40212609212) cancelled (superseded by the next push; not a result) |
| `1cbbcc5` (merged) | [40213947602](https://github.com/mythril33/Payload-Aware-Open-Set-Interference-Recognition-for-GEO-Transponders/actions/runs/40213947602) success: **2703 passed**, 918.26 s | [40213947636](https://github.com/mythril33/Payload-Aware-Open-Set-Interference-Recognition-for-GEO-Transponders/actions/runs/40213947636) **FAILURE**: 4 failed, 9 errors, 4487 passed, 7 skipped, 1820.29 s |
| `2011ba5` (follow-up, disk fix only) | [40228237203](https://github.com/mythril33/Payload-Aware-Open-Set-Interference-Recognition-for-GEO-Transponders/actions/runs/40228237203) success | [40228237194](https://github.com/mythril33/Payload-Aware-Open-Set-Interference-Recognition-for-GEO-Transponders/actions/runs/40228237194) cancelled (superseded by the next push; not a result) |
| `8c26490` (follow-up, code head) | [40229859614](https://github.com/mythril33/Payload-Aware-Open-Set-Interference-Recognition-for-GEO-Transponders/actions/runs/40229859614) success: **2742 passed** (421 E18 + 2321 regression), 985.25 s | [40229859599](https://github.com/mythril33/Payload-Aware-Open-Set-Interference-Recognition-for-GEO-Transponders/actions/runs/40229859599) **FAILURE**: 1 failed, 4538 passed, 7 skipped, 1356.59 s — **no disk error**; the one failure is a test added in this follow-up (below) |
| final head | see the pull request description (a docs-only commit cannot cite its own CI) | see the pull request description |

### The one failure on `8c26490` (a defect of this follow-up's own new test)

`test_a_resumed_test_stage_notices_a_k17d_deviation_before_it_produces_another_shard` restarted the run with this module's `custody` /
`integrated` fixtures while the cached `known` world had been built under another module's fixtures (the full repository suite runs the
acceptance module first; locally the recovery module built the world itself, so the pair matched by luck). Different fabricated keys →
the signed evidence was refused → `BLOCKED`. The E18 workflow's test order did not expose it. Reproduced deterministically by building
the world from a probe module first, fixed by restarting under the world's own `custody`/`bundle` (as `copy_world` already does), and
verified under both orders. No production code was involved.

### Root cause of the red readiness run on the merged head

All 13 failing/erroring tests (`test_training.py` ×3, the R1 evaluator ×1, A5/setup fixtures ×9) died with
`OSError: [Errno 122] Disk quota exceeded` or the equivalent `torch.save … iostream error` while writing under
`/tmp/pytest-of-runner/…`; none was an assertion failure, and they ran at the end of the suite. Pytest keeps every passing test's
`tmp_path` for the whole session. Each E18 recovery/lifecycle test copies a cached synthetic world (measured: complete 21.8 MB / 5,309
entries, known 16.9 MB / 4,129, admitted 9.9 MB / 2,389), so a session left about 1.2 GB and several hundred thousand directory entries
behind. The head before the review fixes (`1f5b631`) still fit (4419 passed); the added review-remediation tests did not.

Fix: an autouse `scratch` fixture (`tests/e18_support.py`) removes each passing test's tree after teardown (read-only directories made
writable first; symbolic links unlinked, never followed; a **failing** test's tree is kept for the post-mortem), imported by all five
E18 modules. The cached worlds, assertions and scientific checks are unchanged. Measured with the same suite and a fixed `--basetemp`:

| | peak temp size | peak entries |
|---|---|---|
| before (merged head, per session, local `du`, measured earlier in this work) | ≈ 1.2 GB | not recorded |
| after (this follow-up, full E18 run of 421 tests) | 108,200 KiB (≈106 MB) | 22,718 |

## Honest limits

* Everything above the injected ports is real code over **fabricated** bytes and attestations. The K17d comparison, device records
  and journal-location checks are fabricated (`k17d_production_cross_check` stays `NOT_RUN`; summaries say `FABRICATED_SYNTHETIC`).
* The AST/text tripwires and the workflow lint are regression tripwires, not proofs. The CI scope guard cannot protect the workflow file
  that runs it; that needs repository settings (required reviews / rulesets / CODEOWNERS on `.github/workflows`), which this repository
  cannot configure or verify.
* Local runs used Python 3.13, CI uses 3.12; the timing figures differ accordingly.
* This pull request edits the E18 workflow's explanatory comment (it overclaimed that a PR cannot rewrite its own judge). CI judges it with the
  **base** policy, which still allows that file, so the guard passes; under the policy introduced here the same edit would be out of scope
  (`check-diff` with the new script flags exactly that one path). This is a one-time, human-reviewable exception, not a precedent.
* The readiness workflow was not modified. Its pre-existing 7 skips (`test_b2_train_diagnostics.py:392`, machine/torch dependent) are
  unrelated to E18.

## Not integrated (all need human decisions; recommended E19 scope in the lifecycle design)

Real trust root and signer/issuer custody; independent revocation/CI authority; designated host with a real CPU/RSS/disk observer;
independent persistent backup, restore drill and retention; an external append-only journal sink and replay custodian; the production K17d
metadata cross-check; the DR-04 record and a separate launch decision; branch protection for workflow files; the physical generators.
**DR-04 remains NO-GO and no compute is authorized.**

## Reproduction

```bash
source /workspace/.venvs/geosim/bin/activate
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 PYTHONHASHSEED=0 CUDA_VISIBLE_DEVICES=
python -m pytest -q -p no:cacheprovider --basetemp=/tmp/e18-bt tests/test_b2_e18_lifecycle.py tests/test_b2_e18_trust_resources.py \
  tests/test_b2_e18_recovery.py tests/test_b2_e18_acceptance.py tests/test_b2_e18_ci_policy.py
python scripts/b2_e18_ci_policy.py lint .github/workflows && python scripts/b2_e18_ci_policy.py gate-decision
```

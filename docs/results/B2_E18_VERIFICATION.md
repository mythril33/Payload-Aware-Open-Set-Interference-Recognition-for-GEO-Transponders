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
| This follow-up | [#43](https://github.com/mythril33/Payload-Aware-Open-Set-Interference-Recognition-for-GEO-Transponders/pull/43) (draft), same branch name restarted from the merged main (the merged PR was not reused); nothing was merged automatically |

The merge happened before this report, the DURUM entry and the second review's fixes existed, and the readiness CI on the merged head
was red (below). Those facts are recorded here rather than rewritten: the merged state is a fully working synthetic lifecycle whose
**test suite exhausted the CI runner's disk**; this follow-up fixes that and the findings of the second independent review.

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

_Pending: this section is completed by the final commit of this pull request (draft)._

## Independent reviews (model agents — **not** human approval)

Two read-only red-team reviews were run by a separate model agent. A model-agent review is engineering evidence only; it approves nothing
and does not replace the human decisions listed in the lifecycle design.

_Pending: this section is completed by the final commit of this pull request (draft)._

## CI evidence (raw logs inspected, not inferred from a merge)

| Head | E18 workflow | Readiness workflow |
|---|---|---|
| `1f5b631` | [40208970152](https://github.com/mythril33/Payload-Aware-Open-Set-Interference-Recognition-for-GEO-Transponders/actions/runs/40208970152) success | [40208970151](https://github.com/mythril33/Payload-Aware-Open-Set-Interference-Recognition-for-GEO-Transponders/actions/runs/40208970151) success: 4419 passed, 7 skipped, 1344.32 s |
| `8dbdd87` | [40212609279](https://github.com/mythril33/Payload-Aware-Open-Set-Interference-Recognition-for-GEO-Transponders/actions/runs/40212609279) success | [40212609212](https://github.com/mythril33/Payload-Aware-Open-Set-Interference-Recognition-for-GEO-Transponders/actions/runs/40212609212) cancelled (superseded by the next push; not a result) |
| `1cbbcc5` (merged) | [40213947602](https://github.com/mythril33/Payload-Aware-Open-Set-Interference-Recognition-for-GEO-Transponders/actions/runs/40213947602) success: **2703 passed**, 918.26 s | [40213947636](https://github.com/mythril33/Payload-Aware-Open-Set-Interference-Recognition-for-GEO-Transponders/actions/runs/40213947636) **FAILURE**: 4 failed, 9 errors, 4487 passed, 7 skipped, 1820.29 s |
| follow-up head | pending | pending |

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
| before (merged head, per session, local `du`) | ≈ 1.2 GB | several 10⁵ |
| after (this follow-up, full E18 run) | pending | pending |

## Honest limits

* Everything above the injected ports is real code over **fabricated** bytes and attestations. The K17d comparison, device records
  and journal-location checks are fabricated (`k17d_production_cross_check` stays `NOT_RUN`; summaries say `FABRICATED_SYNTHETIC`).
* The AST/text tripwires and the workflow lint are regression tripwires, not proofs. The CI scope guard cannot protect the workflow file
  that runs it; that needs repository settings (required reviews / rulesets / CODEOWNERS on `.github/workflows`), which this repository
  cannot configure or verify.
* Local runs used Python 3.13, CI uses 3.12; the timing figures differ accordingly.
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

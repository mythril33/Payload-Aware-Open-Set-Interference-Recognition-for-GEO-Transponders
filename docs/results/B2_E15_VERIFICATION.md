# B2 E15 — operational dossier verification

2026-10-25. **E15 OPERATIONAL DOSSIER COMPLETE — DR-04 NO-GO — NO COMPUTE AUTHORIZED.**
This is decision-package engineering, not host qualification, production release
or a recognition-performance result. No generation host or backup was designated;
all target-host measurements remain null / NOT MEASURED / BLOCKED.

## Ground truth and intended delivery

Fetched main: `9e176ad20aa1f355adac06e5a22c77b38a616099`; PR #38 is merged.
Its exact reviewed PR head was `03b01972102074b055fee3624f4ddb03757d389c`.
Both trees equal `27c83a3f2daf3bbdbfc231111ba7b6fd095be65b`.
PR #38 CI [run40161909630/job121075064242](https://github.com/mythril33/Payload-Aware-Open-Set-Interference-Recognition-for-GEO-Transponders/actions/runs/40161909630/job/121075064242)
was independently re-read: E4 107 passed /137.55s; repository 3125 passed,
7 skipped, 46 warnings /972.80s; total3232 passed, zero failures. Seven skips:
`tests/test_b2_train_diagnostics.py:392`, runner/torch does not reproduce the
historical capture even with the original loop. This is baseline evidence,
not E15-head CI and not an E15 re-execution of the RF suite.

Worktree was initially clean. Local/remote branch search, untracked-file search
and all three stash filename inventories found no existing E15 work to recover.
The E13/E7b/observed-receiver stashes and older branches were preserved. The new
branch is `feature/b2-e15-operational-qualification` from fetched current main.

Seven intended changed files:

- `docs/operations/B2_E15_HOST_QUALIFICATION.md`
- `docs/operations/B2_E15_RESOURCE_AND_BACKUP_ASSESSMENT.md`
- `docs/plan/B2_E15_DR04_DECISION_DOSSIER.md`
- `docs/plan/B2_E15_RELEASE_SEQUENCE.md`
- `docs/results/B2_E15_VERIFICATION.md`
- `docs/plan/DURUM.md`
- `.github/workflows/b2-e15-operational-ci.yml`

The dossier supplies the 12-control matrix: **VERIFIED4 / PARTIAL5 / MISSING1 /
BLOCKED—EXTERNAL DEPENDENCY1 / NOT AUTHORIZED1**. These are scoped dossier
classifications, not measured host passes or the E13 validator's finding counts.

## Actual local verification

The existing implementation/test bytes at source HEAD
`9e176ad20aa1f355adac06e5a22c77b38a616099` were tested while new documentation
was being drafted as untracked files. No tracked file or HEAD changed during the
measured run. No product code or tests are changed by E15.

```bash
env OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 PYTHONHASHSEED=0 MPLBACKEND=Agg \
 /workspace/.venvs/geosim/bin/python -m pytest -q -rs \
 tests/test_b2_e14_launch_contract.py tests/test_b2_e14_storage.py \
 tests/test_b2_e14_metadata.py tests/test_b2_e13_generation_plan.py \
 tests/test_b2_e9_contract.py tests/test_b2_e9_scientific_freeze.py \
 tests/test_b2_e12_k17d_integrity.py tests/test_b2_e12_legacy_access.py
```

**1328 passed, 0 failed, 0 skipped, 0 warnings; pytest51.36s, measured wall52.872s;
peak child high-water RSS279764KiB (273.21MiB).** Linux child maximum RSS is not
aggregate concurrent memory. The wrapper captured all tracked SHA-256 values and
HEAD before/after: unchanged. Logs/measurement JSON are ephemeral local evidence
under `/tmp/b2-e15-evidence/`; no dataset/checkpoint is committed.

Test environment only: Python3.12.14, NumPy2.5.4, SciPy1.18.1,
torch2.14.1+cpu, pytest9.1.1; xgboost-cpu3.4.1 was installed but not required by
the selected tests. This describes the sandbox test process, not a production
host measurement or environment lock.

| Required negative check | Existing executed coverage / limit |
|---|---|
| Missing/fabricated host measurements | E14 missing/live-device/fabricated-report cases; consistent invented JSON still grants no authority and proves no hardware facts |
| Inconsistent device, disk deficit, volatile backup | E14 strict device comparison and synthetic storage negative matrix; no actual backup device qualified |
| Environment/source/config drift | E13 identity, lock and environment negatives; E14 binding/request provenance negatives |
| Missing/inconsistent/expired approval | E13 committed-record/scope/expiry checks; no real approval was added |
| Production activation or green CI as authority | E9 unconditional guard, E14 unconditional denial and approval-shaped/green-CI negative tests; existing two-group cap preserved |
| K17d identity drift | E12 immutable identity integrity plus E14 fabricated metadata membership/polarization/checksum negatives; no observation arrays opened |
| Premature test-role access / incomplete freeze | E12 legacy-access readers/fit/inference are stand-ins; E9 complete nine-cell metadata checks; no real held-out read or fit |

No new test was added merely to increase count. Existing coverage meets the
bounded document/metadata scope. The full repository RF/regression suite is
**NOT RUN in E15**, locally or by E15 CI, because it includes real-waveform replay
fixtures and this milestone forbids them. Its earlier E14 success is kept separate.

## Dedicated exact-head CI boundary

The old readiness workflow filters out these documents and runs real RF replay
when invoked. A separate narrow E15 workflow is therefore necessary to obtain
permitted exact-head evidence without changing its authorization policy. New
workflow triggers only its own path or the five E15-named documents; the shared
DURUM path alone does not activate it. It has a 15-minute limit, read-only GitHub
permissions, CPU-only torch2.14.1+cpu, hidden CUDA devices, the fixed eight-file
synthetic/metadata test list, syntax compilation, protected baseline comparison,
strict JSON/null-field/document checks and no production command or artifact upload.

The final PR head, run/job IDs, actual results and logs belong in the draft PR
after publication; they are not fabricated here before this commit exists.
The existing `b2-readiness-ci.yml` is unchanged and is not dispatched for E15.
This new coverage workflow is not the future approved-generation CI policy.

Actual local document/CI checks also passed (exit0): YAML shape and exclusive
trigger paths parsed with the available YAML loader; inline workflow Python
syntax parsed; that exact document/null-field/gate-check body executed;
`python -m compileall -q src scripts tests`; and protected source/config/authority
comparison against the base. Staged whitespace checks are performed before commit.

## Independent read-only review and dispositions

A separate model agent reviewed the four authored host/resource/dossier/sequence
documents, verified the six pinned scientific/config hashes, and independently
recalculated resource arithmetic. It identified two precision improvements, both
incorporated: CID-corrected lost test-shard work is132s rather than the uniform125s
illustration; the12GB proposal describes one copy, while retaining a good copy
plus staging another needs at least17.3362GB before overhead. These remain
unapproved capacity/retention choices, not newly adopted ceilings.

Final seven-file read-only review: **NO OPEN MATERIAL FINDING**, including this
report, DURUM and the dedicated CI. R15-CI-1 identified a generic DURUM trigger
that would have run the frozen-base E15 check on unrelated future source work;
it was removed while retaining DURUM validation inside the E15 bundle. The reviewer
actually executed static negative path checks: this E15 bundle triggers the new
workflow only; future DURUM+src changes trigger the original workflow only;
DURUM alone does not trigger E15. No unit-test count is added for these static
checks. The reviewer ran no unit suite or host/GPU/RF work; the1328-test result
above is the integrator's run. Model-agent review is not human approval or
authorization authentication. Final-head CI is separately recorded in the PR.

## Integrity and remaining blockers

`src/`, all existing `scripts/` and `tests/`, `configs/`, `pyproject.toml`, P18,
scientific approvals/registers, gates/memorandum, historical identity/results and
the old readiness workflow remain byte-identical to the verified base. Only the
new E15 coverage workflow changes `.github/`. Source/config/tool identity is
unchanged; no historical artifact/checkpoint is relabelled. Future executor or
durability edits still require new provenance, review and any required D-8
metadata re-derivation/acceptance before design freeze.

Host and persistent independent backup are **NOT QUALIFIED**. Estimates are
conditional: 8.4388864GB arrays,8.6681GB artifact allowance,33.880076930GiB startup
free space; CID-corrected23.119444–30.069444h /26.490295–34.453615core-h.
36h/42core-h,4vCPU,8GiB RAM,2GiB RSS and12GB backup are proposals, not authority.
A6.25s first-shard pass can project37.309028h/42.748741core-h, so runtime remaining
budget enforcement is still required. No target production throughput was measured.

Production executor, physical-generator fsync/immutable publication, active backup/
restore/journal integration, final lock, explicit ceilings/expiry and DR-04 remain
missing or blocked. CI's current closed-gate assertions conflict with a future
approved gate; post-approval flag/guard/source edits invalidate the design/lock.
The release sequence exposes these dependencies rather than bypassing them.

D-1 remains non-pristine with mandatory498/148 exclusion rows. D-8 exact
500/co35/cross43/total78/complement465 identity remains accepted; actual production
cross-check is NOT RUN. All compute gates remain NOT_AUTHORIZED;
`PRODUCTION_LAUNCH_ENABLED=False`, `benchmark_complete=false`. No waveform,
production artifact, GPU query/probe/training, LOKO, D-5 or held-out inference was
generated or executed by E15.

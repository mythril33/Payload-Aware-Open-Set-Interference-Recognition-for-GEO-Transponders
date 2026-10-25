# B2 E14 — verification and independent review

2026-10-25. Engineering preparation only. **DR-04 NO-GO — NO COMPUTE AUTHORIZED.**
No production generation, GPU discovery/probe/training, held-out observation,
LOKO or D-5 sweep was used. `benchmark_complete=false`.

## Identity and delivery scope

Verified fetched base: `5ba972da6d3dee097cfee9cb79a5c1b27a1c139b`, PR #37 merged.
Branch: `feature/b2-e14-production-launcher-safety`.
Code commit tested: **`edf1d929d5d40c310242a68bf5b3e3f7daa7c412`**.
This report is an evidence-only follow-up. The final PR head and its own GitHub
Actions outcome are recorded in the PR body and delivery report; they cannot be
the result of this report's own not-yet-created commit.

| Delivered files | Purpose |
|---|---|
| `scripts/b2_e14_launch_contract.py`, `tests/test_b2_e14_launch_contract.py` | Sealed non-runnable specification, strict admission reuse, unknown-option/path/hash rejection, unconditional execution refusal |
| `scripts/b2_e14_storage.py`, `tests/test_b2_e14_storage.py` | Capped synthetic reference durability, integrity/quarantine/restore, measured-device record checks |
| `scripts/b2_e14_verify_metadata.py`, `tests/test_b2_e14_metadata.py` | Future production K17d metadata-only comparison, separately labelled fabricated fixtures |
| `docs/plan/B2_E14_PRODUCTION_LAUNCHER_ARCHITECTURE.md` | Pre-implementation ADR, before/after gap matrix and boundaries |
| `docs/operations/B2_E14_RELEASE_GATE_CHECKLIST.md` | Eleven future release controls, resource provenance, missing decisions |
| `docs/operations/B2_E14_BACKUP_RECOVERY_PROCEDURE.md` | Future backup/restore/quarantine procedure; no copier or transfer |
| `docs/plan/DURUM.md`, this file | Dated status and actual evidence |

The old unfinished local E13 files were preserved in a named Git stash before
switching from the old checkout to current remote main; they were not overwritten,
discarded, reapplied to E14 or published.

## Local exact-code verification

All commands below used code head `edf1d929d5d40c310242a68bf5b3e3f7daa7c412`.
Test environment: Python 3.12.14; NumPy 2.5.4; SciPy 1.18.1;
torch 2.14.1+cpu; pytest 9.1.1; xgboost-cpu 3.4.1; Linux 6.18.55.
No torch/GPU workload was required by the new tests. Four explicit environment
pins: `OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 PYTHONHASHSEED=0`;
`MPLBACKEND=Agg`. These are test settings, not a production environment lock.

```bash
env OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 PYTHONHASHSEED=0 MPLBACKEND=Agg \
 /workspace/.venvs/geosim/bin/python -m pytest -q -rs \
 tests/test_b2_e14_launch_contract.py tests/test_b2_e14_storage.py \
 tests/test_b2_e14_metadata.py tests/test_b2_e13_generation_plan.py \
 tests/test_b2_e9_contract.py tests/test_b2_e9_scientific_freeze.py \
 tests/test_b2_e12_k17d_integrity.py
```

**1284 passed, 0 failed, 0 skipped, 0 warnings; pytest 48.06 s; measured wall
49.083 s; peak child high-water RSS 279,268 KiB (272.72 MiB).** The measurement
wrapper captured exact HEAD and SHA-256 of every tracked file before/after;
both HEAD and all bytes were unchanged. Peak RSS is Linux child high-water memory,
not the sum of concurrent processes. The raw log and measurement JSON are local
ephemeral evidence under `/tmp/b2-e14-evidence/`, not datasets or Git artifacts.

The three new E14 modules contain **294 cases** (82 launch, 126 storage, 86
metadata). Broader local regression deliberately selected only synthetic CPU and
metadata suites. The entire repository suite is reserved for the existing bounded
GitHub workflow, whose final outcome must be checked independently; it was **not
run locally**. No skipped test is counted as passed.

`/workspace/.venvs/geosim/bin/python -m compileall -q scripts tests src`: exit 0.
`git diff 5ba972da6d3dee097cfee9cb79a5c1b27a1c139b --check`: exit 0.
No separate lint tool is configured in the existing workflow.

### Data-free checkout smoke

The measured wrapper ran `/workspace/.venvs/geosim/bin/python
/tmp/b2-e14-evidence/smoke.py` on the same clean code commit. The script called
`G.collect_reference()`, `G.make_template(reference)`,
`C.build_specification(plan)` and `C.admit(specification, plan, reference)`;
it asserted every compute gate stayed `NOT_AUTHORIZED` with null approval.

**Exit 0 for smoke assertions; 6.771 s wall; 89,040 KiB peak child RSS.**
The assertion harness exit is not an admission exit or execution permission.
The actual admission verdict was **NO-GO**, `execution_permitted=false`,
`document_consistent=false`, E13 **35 PASS / 0 FAIL / 9 BLOCKED** (five missing
prerequisites plus four structural execution blockers). Inventory: 21,350
observations, 739 shards. Metadata-only K17d re-derivation: 500 headline, co35,
cross43, total78, complement465; zero observation reads and waveform calls.
No host/GPU collector, generator or production process was called. Actual
production metadata comparison remains **NOT RUN**. All tracked bytes and HEAD
were unchanged throughout this smoke.

### Development and independent review

Interim author runs are not final-commit evidence. Initial launch tests reported
80 passed / 1 failed because the new test used the wrong E9 action name
`full_generation` instead of the existing API's `generation`; the test was fixed.
A storage test-edit error reported 86 passed / 1 failed (`NameError`); it was
corrected before the final tests. Interim successful runs overlapped additional
test additions, so only the exact-code run above is used for integrated counts.

A separate read-only model agent reviewed the actual patch and ran only the three
new synthetic suites. It reported **294 passed, 0 failed/skipped/warnings,
12.29 s**, with all six source/test hashes stable before/after. Three material
findings were reproduced and resolved:

| Finding | Correction and regression |
|---|---|
| R14-1: matched declared known as its immediate predecessor | Explicit `[None, known, test]` chain plus separate known-artifact binding; exact dependency assertion |
| R14-2: renamed metadata root could leave the reader anchored to a different path | Reopen root namespace and compare directory identities; rename/substitution negative test |
| R14-3: quarantine could report an old renamed root or altered evidence | Before/after root and file-entry snapshots; preservation/substitution negative tests |

Final read-only review: **NO OPEN MATERIAL FINDING**, explicitly confirmed for
`edf1d929d5d40c310242a68bf5b3e3f7daa7c412`. A single EOF blank line in the storage
test was removed after the agent's run; the reviewer verified this was the sole
byte difference and the integrated exact-code run above includes that cleanup.
Model-agent review is independent of the implementation author; it is not human
researcher approval, authorization authentication or power-loss certification.

## Source and scientific integrity

All protected existing files are byte-identical to base: `src/`, `configs/`,
`.github/`, `pyproject.toml`, existing supervisor/preflight/E13 validator,
P18, scientific approvals and registers, gates/memorandum, historical K17d identity
and audit. The `src` tree stays `3da115d27898dc8a009c5ddb0fdfab4c34e084a7`.
The accepted 28-module geosim identity remains unchanged. New script hashes change
tool-bound plan/release identity; future locks must bind the final reviewed release.
No historical result or checkpoint is relabelled.

| New implementation | SHA-256 at code commit |
|---|---|
| launch contract | `7e88838a5a9b5a8a59b69fc88c675a28f973c482eb597ca3d74bfd240e33b9bf` |
| storage reference | `5e3c4a85eae162f38ad9908e5975517eed6110e8b6c416e3ba0412f836570e5f` |
| metadata verifier | `9abd2e3e3877c4941041d8ce892ae8fef887569a5288541bcf95145d147ca70e` |

| Gate/state | Before | After |
|---|---|---|
| K18, K17d, OBS-CANCEL-2; R1–R10, D-1–D-8 | Scientifically approved | Unchanged |
| Full generation / GPU probe / GPU training / LOKO / final held-out evaluation | NOT_AUTHORIZED | NOT_AUTHORIZED |
| Production activation | False | False |
| Existing runnable fixture cap | Two groups | Two groups |
| Benchmark complete | False | False |

D-1 remains non-pristine with mandatory 498/148 exposure-exclusion sensitivity
rows. D-8 exact accepted identity is preserved. Metadata checks are not feature
inputs or performance-based selection; no test-informed tuning occurred.

## CI and remaining limits

Baseline PR #37 exact-head run **40144143316**, job **121021801383**, head
`5bf3c9abd92b656cfc202594bee4d72f14a7dada`, succeeded: E4 107 passed (137.40 s),
repository 2831 passed / 7 skipped / 46 warnings (968.79 s), total **2938 passed,
0 failed, 7 skipped**. Raw logs independently inspected. All seven skips were
`tests/test_b2_train_diagnostics.py:392`: the runner/torch build did not reproduce
the original golden capture with the verbatim original loop; they are not passes.
Existing warnings concern Matplotlib colormap deprecation. This is baseline
evidence, **not E14 CI evidence**. E14 exact-head run/job, actual counts and logs
must be recorded in the draft PR after this evidence commit is published.

Production executor, actual generator durable-commit integration, active backup
supervision, production restore and runtime release remain absent. Host and
persistent physically independent backup designation, approved ceilings, DR-04,
clean final lock and release review remain blocking. Storage JSON/physical IDs
and embedded CI/review evidence are not authenticated hardware or human proof.
An admission snapshot cannot eliminate later hostile filesystem changes; future
runtime must recheck at boundaries with an external journal and immutable roots.
Payload byte integrity is deliberately outside the K17d metadata verifier.

**E14 PRODUCTION LAUNCH ARCHITECTURE PREPARED — DR-04 NO-GO — NO COMPUTE AUTHORIZED.**

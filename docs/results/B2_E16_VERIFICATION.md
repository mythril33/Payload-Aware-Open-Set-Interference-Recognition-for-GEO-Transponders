# B2 E16 — verification and independent review

2026-10-25. Engineering preparation only. **DR-04 NO-GO — NO COMPUTE AUTHORIZED.**
No production generation, GPU discovery/probe/training, held-out observation, LOKO or D-5 sweep was used.
`PRODUCTION_LAUNCH_ENABLED=False`, `benchmark_complete=false`; `full_generation`, `full_gpu_training`,
`full_loko_sweep`, GPU probe and held-out final evaluation remain `NOT_AUTHORIZED`.

## Identity and delivery scope

Verified base: `origin/main` = `09dd104acdde119f5b38098775dc8ee7c9d2e42a` (PR #39 merged; E15 exact-head CI succeeded).
Branch: `feature/b2-e16-production-integration`. Draft PR: [#40](https://github.com/mythril33/Payload-Aware-Open-Set-Interference-Recognition-for-GEO-Transponders/pull/40) (not merged, E17 not started).
No earlier E16 work, branch, stash or staged file existed at the start.

| Commit | Content |
|---|---|
| `8d4eef6` | checkpoint: four modules, five test suites, scoped workflow, plan / release-policy / safety-checklist documents |
| `27a2f89` | fixes for the first independent review (two MATERIAL, ten MINOR findings) with regression tests |
| `4230289` | fixes for the re-review's minor findings (allow-listed gate fields, journal volume, overflow, limits) |
| `8fd4e47` | `isolation.roles` is `NOT_RUN` without evidence; this report and the DURUM entry (the code head that CI evaluated) |
| evidence-only follow-up | this report's CI section; documents only, no code |

The final PR head and its own GitHub Actions outcome cannot be recorded inside the commit that carries this report: they are
recorded in the PR body and the delivery report.

| Delivered file | Purpose |
|---|---|
| `scripts/b2_e16_durability.py` | durable-admission barrier, classification, quarantine note, manifest, restore re-verification, immutability findings, generator-identity impact |
| `scripts/b2_e16_ledger.py` | hash-chained external ledger, incident specification, pure stop-condition evaluator |
| `scripts/b2_e16_policy.py` | scoped DR-04 operational-authorization policy, `ci-gate`, release-order check |
| `scripts/b2_e16_integration.py` | release-boundary report over injected evidence |
| `tests/test_b2_e16_{durability,ledger,policy,integration,safety}.py` | synthetic suites (fabricated bytes in temporary directories, fake adapters) |
| `.github/workflows/b2-e16-integration-ci.yml` | scoped workflow; the readiness and E15 workflows are untouched |
| `docs/plan/B2_E16_PRODUCTION_INTEGRATION.md` | architecture, gap and before/after matrices, hash-order and durability decisions, limits |
| `docs/operations/B2_E16_RELEASE_POLICY.md`, `B2_E16_RUNTIME_SAFETY_CHECKLIST.md` | release policy and future-executor checklist |
| `docs/plan/DURUM.md`, this file | dated status and evidence |

## Local verification

Environment: Python 3.13.16 venv (`/workspace/.venvs/geosim`), NumPy 2.5.4, SciPy 1.18.1, Linux 6.18, 4 CPUs; test settings
`OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 MKL_NUM_THREADS=2 PYTHONHASHSEED=0 MPLBACKEND=Agg` (test settings, not a production
lock). GitHub Actions uses Python 3.12.

| Run | Result |
|---|---|
| E16 suites (durability, ledger, policy, integration, safety), final code | **712 passed, 0 failed, 0 skipped** (113.6 s; run concurrently with the full-suite job) |
| Related E9 / E12 / E13 / E14 contract suites (checkpoint code) | 1328 passed (117 s), identical to the pre-E16 count: the new scripts changed no existing test |
| Entire repository suite on code head `4230289` | **3951 passed, 0 failed, 0 skipped**, 46 Matplotlib colormap warnings, 1970.6 s wall (shared with other jobs). The later code change (`8fd4e47`: `isolation.roles` without evidence) touches only the integration module and its test; it was verified by the 712 E16 tests above and by GitHub's full suite below |
| `python scripts/b2_e16_policy.py ci-gate` on the real files | exit 0, `CLOSED_CANONICAL`, NO-GO |

### Data-free checkout smoke (clean committed tree, head `4230289`)

`G.collect_reference()` (real git queries, metadata-only K17d re-derivation), `G.make_template`, `C.build_specification`
and `I.evaluate_release_boundary` for all four boundaries with **no adapter**: 9.3 s wall, 111,184 KiB peak RSS, 68 hashed source
files, 38 tool hashes, 739 shards, 8,668,100,000 estimated artifact bytes. Every boundary: `NO-GO`, `execution_permitted=false`,
`document_conditions_met=false`, 0 FAIL, 5 BLOCKED (`authorization.policy`, `plan.dr04`, `identity.source_config_environment`
(no lock), `runtime.stop_conditions`, permanent `execution.boundary`), the evidence conditions `NOT_RUN`. With the thread variables
unset the same run reports `environment.pin` as a genuine FAIL, as designed. No host collector, generator or production process
was called.

### Mutation testing of the E16 modules

Targeted source mutations were applied to a scratch copy (never the real tree) and the matching suites run with `-x`:
**100 mutants** (durability 23, ledger 26, policy 23, integration 28; including the round that followed the reviews). 96 were
killed by the final suites. Four are equivalent or unreachable and are not counted as test gaps: the size pre-check in
`_read_regular` and the streaming loop cap beside it (the post-read size comparison enforces the same bound), a projection guard
that the 1e15 reading bound makes unreachable, and `bool(document)` in `document_conditions_met` (the list is never empty).
Survivors found along the way were closed by strengthening tests: the
post-barrier re-verification (tamper at each fsync call), classification state labels, the all-gates-open-consistently case,
the held-out consumer message, the inventory cross-check, the working-directory-device check and the request-aliasing guard.

## Independent review (model agent; not human release approval)

Two read-only rounds by a separate agent that did not write the patch; it recorded SHA-256 of every file before and after
(identical both times), worked only in private copies, reproduced each finding, and ran only the synthetic suites.

**Round 1** — MATERIAL: **E16-01** the standalone authorization API silently dropped extra plan stages and still reached
`DR04_GENERATION_RECORD_VALID` (now the sealed E14 plan check runs first); **E16-02** the journal trusted an entry's
self-declared incident action (the incident specification is now enforced in `verify_chain`, `make_entry`, `Ledger.append` and
the integration). MINOR: **E16-03** overflowing / non-finite readings raised instead of stopping and
`evaluate_release_boundary` could raise; **E16-04** a missing consumer declaration did not count against the boundary;
**E16-05** `ci-gate` tolerated duplicate keys and was only a partial enumeration; **E16-06** a volatile journal location was
accepted; **E16-07** parser limits escaped as `ValueError`; **E16-08** K17d zero reads accepted `false` / `0.0`; **E16-09**
workflow guard list and E15 interplay; **E16-10** doc inaccuracies (missing report, wrong check name, backup-ceiling wording);
**E16-11** coverage gaps and weak OR-assertions; **E16-12** small validations (`recorded_at`, symlinked generator module,
zero rate, totals, unbounded reads). Every item was fixed or documented, each with a regression test.

**Round 2** (fix commit `27a2f89`) — verdict **`NO OPEN MATERIAL FINDING`**. Seven MINOR items were reported and addressed in
`4230289`: allow-listed decision fields, memorandum / record fields and controls (N-01); datetime-limit overflow in timestamps
and a huge-int timing policy (N-02); unhashable incident names (N-03); a known `resume_state` for quarantine notes (N-04); the
journal volume's filesystem type must be in the reviewed durable list (N-05); a valid-JSON oversize test (N-06); incident
fields reserved for incident entries (N-07). The living gates document's *top-level* keys remain deny-listed rather than
allow-listed because that document legitimately grows; this is stated in the plan (§7.1).

The review confirmed: no path traversal from shard ordinals, forged classification names, manifest entries or roots; the record's
hash-versus-parse TOCTOU is closed; no exception turns into an allow; the E16 scripts contain no unlink / rename / remove /
truncate / chmod and the only writes are `Ledger.append`'s `os.write` and the no-clobber publication of new evidence notes.

## Source and scientific integrity

| Item | State |
|---|---|
| `src/` git tree | `3da115d27898dc8a009c5ddb0fdfab4c34e084a7`, byte-identical to base |
| 28-module geosim package digest | `01c4f2697a9ff80e5bd7e644bdbf27562cb33d303685ace6f362c868b607fc4b`, unchanged (asserted by a test) |
| `configs/`, `pyproject.toml`, readiness and E15 workflows, gates JSON, memorandum, scientific protocol and records, K17d identity and audit, E13–E15 documents | byte-identical to base (guarded by the new workflow's `git diff --exit-code` step) |
| Existing `scripts/` and `tests/` | unchanged; only `b2_e16_*` files are added |
| Scientific parameters / thresholds / protocols | unchanged; no test-informed tuning |
| Compute gates and flags | all `NOT_AUTHORIZED`; launch disabled; fixture cap two groups |

Four new scripts change the tool hashes (`tools_sha256`, therefore `approved_plan_digest`) of any plan derived on or after this
branch: intended; a plan made before it must be re-derived. SHA-256 of the final modules and suites are in the PR delivery
report. D-1 remains non-pristine with mandatory 498 / 148 exposure-exclusion sensitivity rows; D-8 keeps the accepted K17d
identity `ccdf0a8f…c49c6d` and 500 / 35 / 43 / 78 / 465 counts.

## CI evidence

Exact-head runs on code head **`8fd4e476d844a9001c45d1aabc6bf902c494d1f3`** (pull request #40), read from the raw job logs:

| Workflow | Run / job | Result |
|---|---|---|
| B2 readiness CI (unchanged workflow) | [40182340185](https://github.com/mythril33/Payload-Aware-Open-Set-Interference-Recognition-for-GEO-Transponders/actions/runs/40182340185) / 121136038122 | success; the approvals-and-closed-gates step, compile and the E4 step passed; repository step **3837 passed, 7 skipped, 46 warnings (716.53 s)** |
| B2 E16 integration CI (new, scoped) | [40182340188](https://github.com/mythril33/Payload-Aware-Open-Set-Interference-Recognition-for-GEO-Transponders/actions/runs/40182340188) / 121135825050 | success; protected-path `git diff --exit-code`, added-files allow-list, `ci-gate` (`CLOSED_CANONICAL`, exit 0), compile, **2040 passed (129.24 s)** |

All seven skips are `tests/test_b2_train_diagnostics.py:392` (the runner's torch build does not reproduce the original golden
capture with the verbatim original loop); they are skips, not passes, and are identical to the pre-E16 baseline. Earlier heads
(`8d4eef6` checkpoint: readiness run 40178704238 and E16 run 40178704235, both success) are superseded by the run above. Superseded
intermediate heads `27a2f89` / `4230289` had their readiness run cancelled by the concurrency group when the next commit was pushed;
that is not a failure. This evidence commit changes documents only; the final PR head and its own E16-workflow outcome are recorded
in the PR body.

## What this does not establish

* No executor exists; none of the E16 controls is called by a production path.
* Evidence is as truthful as the adapter that returned it. `st_dev`, `media_verified`, `worm_proven` and
  `physical_independence_proven` are reported literally; fsync and a post-eviction re-read are evidence, mode bits are
  accident protection, a different device number is not a different failure domain.
* Real signature, ancestry and revocation sources, a designated host, an independent persistent backup with a restore drill, the
  external journal location with anchor custody, run-bound ceilings, a DR-04 record, a final lock and the launch decision are
  all absent. The test and matched request fingerprints are taken from the shards and the external journal, not recomputed
  from a real known artifact. The E15 workflow's snapshot guard will report the added E16 files after merge (follow-up).
* A model-agent review is an engineering check, not human approval, authentication or power-loss certification.

**E16 PRE-AUTHORIZATION INTEGRATION COMPLETE — DR-04 NO-GO — NO COMPUTE AUTHORIZED.**

# P30 — B2/1 fail-closed production supervisor (E7a)

Date: 2026-10-23. Base `main` `755b474b7a2c506ec03441a7d15ed365c47addb1`. `benchmark_complete=false`.
Tool: [`scripts/b2_production_supervisor.py`](../../scripts/b2_production_supervisor.py) (separate from the E4 matrix runner);
tests: [`tests/test_b2_production_supervisor.py`](../../tests/test_b2_production_supervisor.py) with the stand-in child
[`tests/b2_supervisor_standin.py`](../../tests/b2_supervisor_standin.py). It builds on the read-only
[preflight (P29)](P29_b2_e6_production_preflight.md) and closes its finding `audit.stage_supervisor_missing`.
**It does not start the production run:** the full launch is not implemented in this build (§2). Nothing here approves a
researcher gate or touches a frozen protocol, config, seed, count or artifact layout.

## 1. What it supervises

The three existing generator CLIs as child processes, in this order and only in this order: `geosim.b2_dataset` (known
B2-feat/1, four roles) then `geosim.b2_test_dataset` then `geosim.b2_matched_dataset`, each bound to the finished known root.
It adds no generation logic; shards, descriptors, manifests and their validators are the generators' own. It audits every
stage root with the preflight (`audit_artifact`, `--known` binding, lock) before it starts, after every attempt and before the
next stage, so a damaged earlier stage can never be built upon.

## 2. Bounded by construction

| Control | Behavior |
|---|---|
| Dry run is the default | `plan` and `run` without `--execute` validate and print the exact commands; they create nothing and spawn nothing |
| Fixture cap | `run --execute` requires `--max-groups 1..2` (groups per role, `--groups-per-shard` 1 or 2); anything else is refused |
| No unbounded child | every spawned argv must contain `--limit-groups` of 1..2 (`assert_bounded`, checked again inside `run_child`); `stage_argv` refuses to build a command for an unbounded plan |
| Production is validation only | `plan --production` reports lock, caps, estimated wall/disk, host, authorization and the disabled launch (all BLOCKED/FAIL as appropriate); `run --production --execute` is refused with the exact missing gates; with every gate approved it is still refused ("not implemented in this build"); a production plan handed to `Supervisor.run()` is refused before the workdir is touched. `PRODUCTION_LAUNCH_ENABLED` is False and flipping it enables nothing because the command builder and the spawn guard stay bounded |
| Authorization | `authorization(gates, memo)` needs `K18`, `K17d`, `OBS-CANCEL-2` and `full_generation` to PASS the preflight gate check (structured approval record, finite positive ceilings, gates/memorandum agreement). It never infers approval |

## 3. Run identity, lock, journal

`run.json` (created once) holds the plan: limits, shard size, relative stage roots (a workdir can be moved or restored and keep
its identity), expected inventory per role, ceilings, timing band, config paths. A restart must present the identical plan or it
is refused. `lock.json` is the P29 production lock (git commit, hashes of every `src/**/*.py`, bundled data, frozen configs and
gates file, generator provenance, Python/NumPy/SciPy, BLAS/hash-seed environment); it is created once, re-verified before every
stage and every attempt, and any drift (including a source edit made while a run is in progress) fails the run before a child is
started. A fixture lock may record a dirty tree (`--allow-dirty-fixture`); a production lock may not.

`journal.jsonl` is append-only, fsynced per record and hash-chained (`seq`, `prev`, `sha256`). A broken chain, gap, reordering,
blank line, torn last line or non-strict JSON makes every restart refuse; the supervisor never repairs or appends to a damaged
journal, and a refusal that happens before the journal is verified writes nothing. Events: `supervisor_start`, `host_checked`,
`stage_start`, `stage_audit`, `quarantine`, `attempt_start`, `timing_gate`, `attempt_end`, `attempt_failed`, `stage_complete`,
`stages_complete`, `interrupted`, `run_failed`. The chain detects accidental modification, not forgery.

## 4. Child supervision and resource safeguards

Each attempt is a child in its own process group (`start_new_session`) that dies with the supervisor (`PR_SET_PDEATHSIG`,
Linux), logs to a new exclusive `logs/<stage>-NN.log`, runs with `CUDA_VISIBLE_DEVICES=""` and the lock's BLAS/hash-seed
environment. Its exit status, elapsed time, user/system CPU and peak RSS come from `wait4` and are journaled exactly (a signal
death is `exit_code` -N plus the signal name). Ceilings (defaults in `FIXTURE_CEILINGS` / `PRODUCTION_CEILINGS`; production values
are the E5 proposals and remain proposals): wall hours and core hours are cumulative across attempts and restarts and enforced
live (a child over budget gets SIGTERM, then SIGKILL after `grace_s`; reasons `timeout` / `cpu_limit`); RSS is polled live from
`/proc` and also checked from `wait4` afterwards (`rss_limit`); attempts per stage are bounded; free disk is checked before the
run and before every attempt against the remaining observations x measured artifact size + 10 % + reserve. A non-zero child exit is
retried only while the attempt budget lasts; every supervisor-initiated stop (timeout, CPU, RSS, timing gate, interrupt) is final
for that run.

**First-shard timing gate.** For the first newly committed shard of an attempt the supervisor computes seconds per observation
`(commit time - attempt start - startup allowance) / observations`, with an allowance that grows with the number of observations
the child must re-verify on resume. Slower than `high x (1 + tolerance)` stops the child (`timing_gate`, outcome `too_slow`); no
committed shard before the deadline does the same (`no_shard_before_deadline`); faster than the band is journaled
(`faster_than_band`) but not stopped, because a faster host only makes the extrapolated budget conservative. The default production
band 3.8-5.0 s/observation is the validity band of the E6 extrapolation, not a measurement of this plan.

## 5. Interruption, orphans, restart

SIGINT/SIGTERM stop the child group (SIGTERM, grace, SIGKILL), journal `attempt_end` with reason `interrupted`, leave the root
RESUMABLE and exit 6; a signal that arrives between attempts is honoured at the next decision point. If the supervisor itself is
SIGKILLed the child dies with it; the next start records the missing end as `supervisor_lost` (resources unknown), refuses to
start if that pid is still alive, and continues from the audited state. A kill inside the rename window leaves part/meta files
without a committed descriptor: the next audit reports `NEEDS_QUARANTINE` and the supervisor moves exactly those files to
`quarantine/<stamp>-<seq>/<role>/` with a `QUARANTINE.json` (sizes, SHA-256), journals them, re-audits and resumes. Nothing is ever
deleted; `INVALID` roots (modified bytes, wrong or repeated groups, tampered request or manifest, source drift) are never touched
and are not resumed. One supervisor per workdir (`flock`).

## 6. Completion

`complete` writes `completion.json` exactly once and only if the journal chain, the lock and all three stages verify COMPLETE at
checksum depth with a deep-verified sample, every role holds exactly the planned inventory, every manifest exists and the journal
contains `stages_complete`. The marker states `generation_complete`, `scope` (`fixture`), `production_complete=false`,
`benchmark_complete=false` and `production_authorized=false`. A missing stage, role or manifest, a short inventory or a missing
final record refuses it and writes nothing.

## 7. Exit codes

0 success; 2 refused (usage, plan/identity mismatch, damaged journal, authorization, concurrent supervisor, production request);
3 failed (child failure, invalid or drifted artifacts, ceiling or timing-gate stop, incomplete scope); 4 dry-run/plan BLOCKED;
5 verify/status found stages not yet complete; 6 interrupted (resumable).

## 8. Limits

Single host and single child process; RSS polling looks at the child only (descendants are covered by `wait4` afterwards); PDEATHSIG
and `/proc` are Linux-specific; the timing band is an extrapolation; the hash chain and all digests detect accidental modification
only; the stand-in child exercises the real generator CLIs but not the physics, and the capped real-physics verification covers two
groups per stage, not production-size behavior (memory, throughput, disk). Enabling a real launch is a later, separately authorized
milestone and would need its own review: authorization record, unbounded command builder, production-size timing validation.

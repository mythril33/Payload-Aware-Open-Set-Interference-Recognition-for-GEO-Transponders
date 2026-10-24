# P30 — B2/1 fail-closed production supervisor (E7a)

Date: 2026-10-24. First state merged as PR #21 (`5d3f1a3`), independent-review hardening merged as PR #22 (`0e8c467`), post-merge audit fixes in the hotfix after it (section 9). `benchmark_complete=false`.
Tool: [`scripts/b2_production_supervisor.py`](../../scripts/b2_production_supervisor.py) (separate from the E4 matrix runner);
tests: [`tests/test_b2_production_supervisor.py`](../../tests/test_b2_production_supervisor.py) with the stand-in child
[`tests/b2_supervisor_standin.py`](../../tests/b2_supervisor_standin.py). It builds on the read-only
[preflight (P29)](P29_b2_e6_production_preflight.md) and closes its finding `audit.stage_supervisor_missing`.
**It does not start the production run:** the full launch is not implemented in this build (§2). Nothing here approves a
researcher gate or touches a frozen protocol, config, seed, count or artifact layout.

## 1. What it supervises

The three existing generator CLIs as child processes (or, for fixtures only, the hashed diagnostic stand-in
`tests/b2_supervisor_standin.py` alone; see §2), in this order and only in this order: `geosim.b2_dataset` (known
B2-feat/1, four roles) then `geosim.b2_test_dataset` then `geosim.b2_matched_dataset`, each bound to the finished known root.
It adds no generation logic; shards, descriptors, manifests and their validators are the generators' own. It audits every
stage root with the preflight (`audit_artifact`, `--known` binding, lock) before it starts, after every attempt and before the
next stage, so a damaged earlier stage can never be built upon.

## 2. Bounded by construction

| Control | Behavior |
|---|---|
| Dry run is the default | `plan` and `run` without `--execute` validate and print the exact commands; they create no workdir and spawn no generator child (the lock reads git state with read-only `git` commands, and the atomic-rename probe creates and removes one transient file in the nearest existing directory) |
| Fixture cap | `run --execute` requires `--max-groups 1..2` (groups per role, `--groups-per-shard` 1 or 2); anything else is refused |
| Ceilings cannot stretch a fixture | a `--ceilings` file may only lower or modestly raise the fixture defaults: at most 4 wall hours, 16 core hours, 5 failed attempts, 50 interruptions, 16 GiB RSS, 120 s grace (`FIXTURE_CEILING_LIMITS`); integer ceilings must be whole numbers; the timing band, tolerance, startup allowance and gate size are range-checked |
| No unbounded child | every spawned argv must contain `--limit-groups` of 1..2 (`assert_bounded`, checked again inside `run_child`); `stage_argv` refuses to build a command for an unbounded plan |
| No arbitrary program | `--child-wrapper` (fixture diagnostic) accepts only this repository's `tests/b2_supervisor_standin.py`; it is hashed into the run identity and refused for `--production`. Children run with `PYTHONPATH=<repo>/src` first, so they import the locked tree |
| Production ceilings only go down | a `--production` plan may lower the proposed ceilings but never raise them (`PRODUCTION_CEILING_LIMITS`; the free-disk reserve is a floor and may only go up); raising needs a researcher-approved record that this build cannot consume |
| Production is validation only | `plan --production` reports lock, caps, estimated wall/disk, host, authorization and the disabled launch (all BLOCKED/FAIL as appropriate); `run --production --execute` is refused with the exact missing gates; with every gate approved it is still refused ("not implemented in this build"); a production plan handed to `Supervisor.run()` is refused before the workdir is touched. `PRODUCTION_LAUNCH_ENABLED` is False and flipping it enables nothing because the command builder and the spawn guard stay bounded |
| Authorization | `authorization(gates, memo)` needs `K18`, `K17d`, `OBS-CANCEL-2` and `full_generation` to PASS the preflight gate check (structured approval record, finite positive ceilings, gates/memorandum agreement). It never infers approval |

## 3. Run identity, lock, journal

`run.json` (created once) holds the plan: limits, shard size, relative stage roots (a workdir can be moved or restored and keep
its identity), expected inventory per role, ceilings, timing band, heartbeat interval, config paths and the **launcher** (`generators`
for the real CLIs, or `child-wrapper:<name>:<sha256 prefix>` for a hashed diagnostic wrapper, fixtures only). A restart must present
the identical plan or it is refused, so a stand-in workdir can never be continued, verified or stamped as a real-generator one. `lock.json` is the P29 production lock (git commit, hashes of every `src/**/*.py`, bundled data, frozen configs and
gates file, generator provenance, Python/NumPy/SciPy, BLAS/hash-seed environment); it is created once, re-verified before every
stage and every attempt, and any drift (including a source edit made while a run is in progress) fails the run before a child is
started. A fixture lock may record a dirty tree (`--allow-dirty-fixture`); a production lock may not.

`journal.jsonl` is append-only, fsynced per record and hash-chained (`seq`, `prev`, `sha256`). A broken chain, gap, reordering,
blank line, torn last line or non-strict JSON makes every restart refuse; the supervisor never repairs, resets or appends to a
damaged journal, and a refusal that happens before the journal is verified writes nothing. A chain alone cannot show that its tail
or the whole file is still there, so `journal.head` (sequence number and hash of the newest record, replaced atomically after
every append) anchors it, and every append first checks that the file still ends with the record this supervisor wrote last (a journal
changed during a run is never appended to, not even to record the failure): a missing, emptied, tail-truncated or rewritten journal is refused, and a crash between an append and its
anchor update (a lag of one record) is tolerated once. The journal must also belong to the run: its first record is the original
`supervisor_start`, and every `supervisor_start` must carry the plan and lock fingerprints of `run.json` / `lock.json`, so a
hand-edited plan with a recomputed fingerprint, or a journal moved aside, is refused by restart, `verify` and `complete`. (Only a
workdir that crashed before its first journal record, i.e. holding nothing but `run.json` / `lock.json`, may start again.) Damage
that is introduced while a run is in progress is caught by the tail check at the next append and by the full chain verification
before every attempt, ends the run (exit 3) and stops the child; records written between the damage and its detection are ordinary
chain records after the damaged one. Events:
`supervisor_start`, `host_checked`, `stage_start`, `stage_audit`, `quarantine`, `attempt_start`, `heartbeat`, `timing_gate`,
`attempt_end`, `attempt_failed`, `stage_needs_supervised_attempt`, `stage_complete`, `stages_complete`, `interrupted`,
`run_failed`. The chain and the anchor detect accidental modification, not forgery: someone who rewrites both files consistently
is not stopped.

## 4. Child supervision and resource safeguards

Each attempt is a child in its own process group (`start_new_session`) that dies with the supervisor (`PR_SET_PDEATHSIG` with SIGKILL,
so even a child that ignores SIGTERM cannot outlive it; Linux), logs to a new exclusive `logs/<stage>-NN.log`, runs with `CUDA_VISIBLE_DEVICES=""` and the lock's BLAS/hash-seed
environment. The supervisor resets an inherited `SIGCHLD=SIG_IGN` to the default for the run (otherwise every status would be
lost); if an exit status is nevertheless unobservable the attempt ends `wait_failed` and fails the stage without a retry. Exit
status, user/system CPU and `ru_maxrss` come from `wait4` and are journaled exactly (a signal death is `exit_code` -N plus the
signal name); elapsed time and all deadlines use the monotonic clock, so a wall-clock step cannot lengthen or negate a budget.
`ru_maxrss` is an **upper bound** (fork copies the supervisor's own peak into it), so the journal also records the polled
`VmHWM` of the child (`peak_rss_polled_kib`, a lower bound, reset by exec) and the supervisor's own peak at spawn
(`supervisor_peak_rss_kib`); the live RSS ceiling uses the polled value and `ru_maxrss` counts after the fact only when it exceeds
the supervisor's own peak. A running child writes a `heartbeat` record every `heartbeat_s` seconds (10 s fixtures, 60 s production).
A signal that arrives before the spawn creates no log and no attempt. If supervision itself fails (for example a journal write), the
child group is SIGKILLed and reaped before the error propagates, and once the leader has exited the process group is emptied too: nothing
may outlive an attempt (`stragglers_killed` records it when something did). Ceilings (defaults in `FIXTURE_CEILINGS` / `PRODUCTION_CEILINGS`; production values
are the E5 proposals and remain proposals): wall hours and core hours are cumulative across attempts and restarts and enforced
live (a child over budget gets SIGTERM, then SIGKILL after `grace_s`; reasons `timeout` / `cpu_limit`); RSS is polled live from
`/proc` and also checked from `wait4` afterwards (`rss_limit`); free disk is checked before the run and before every attempt
against the remaining observations x measured artifact size + 10 % + reserve; a host probe that cannot be read (for example
`MemAvailable`) is `NOT_RUN` and fails the run, because an unknown host is not a safe one. Attempts are budgeted by kind:
`max_failed_attempts_per_stage` counts attempts that ended in a child failure or a supervisor-enforced stop (a non-zero exit is
retried only while it lasts), `max_interruptions_per_stage` counts operator interruptions and lost supervisors (so pausing a
healthy run twice does not dead-end it), and a backstop of 60 attempts per stage applies regardless. Every supervisor-initiated
stop (timeout, CPU, RSS, timing gate, interrupt) is final for that run.

**First-shard timing gate.** (Defaults: startup allowance 30 s, tolerance 0.25, `faster_than_band` below `low / (1 + tolerance)`, i.e. 3.04 s for the 3.8 s lower edge.) For the first newly committed shard of an attempt the supervisor computes seconds per observation
`(commit time - attempt start - startup allowance) / observations`, with an allowance that grows with the number of observations
the child must re-verify on resume. Slower than `high x (1 + tolerance)` stops the child (`timing_gate`, outcome `too_slow`); no
committed shard before the deadline does the same (`no_shard_before_deadline`); faster than the band is journaled
(`faster_than_band`) but not stopped, because a faster host only makes the extrapolated budget conservative; an attempt that ends
before the gate saw a committed shard is journaled `not_evaluated`. The default production band 3.8-5.0 s/observation is the
validity band of the E6 extrapolation, not a measurement of this plan.

## 5. Interruption, orphans, restart

SIGINT/SIGTERM stop the child group (SIGTERM, grace, SIGKILL), journal `attempt_end` with reason `interrupted`, leave the root
RESUMABLE and exit 6; a signal that arrives between attempts is honoured at the next decision point. If the supervisor itself is
SIGKILLed the child dies with it; the next start records the missing end as `supervisor_lost`, refuses to start if that pid is
still alive, and continues from the audited state. A lost attempt is **charged**, not forgiven: its wall time is the last
heartbeat's elapsed time plus one heartbeat interval plus one second, and its CPU is the last heartbeat's CPU plus that interval
times the locked thread count; the record says `estimated: true` and the note calls it an upper-bound estimate from the last
heartbeat, not a measurement (its `peak_rss_kib` is the last heartbeat's polled peak). Repeated losses therefore cannot buy extra wall or core hours. A kill inside the rename window leaves part/meta files
without a committed descriptor: the next audit reports `NEEDS_QUARANTINE` and the supervisor moves exactly those files to
`quarantine/<stamp>-<seq>/<role>/` with a `QUARANTINE.json` (sizes, SHA-256), journals them, re-audits and resumes. Nothing is ever
deleted; `INVALID` roots (modified bytes, wrong or repeated groups, tampered request or manifest, source drift) are never touched
and are not resumed. One supervisor per workdir (`flock`).

## 6. Completion

`complete` writes `completion.json` exactly once and only if the journal chain, anchor and run identity, the lock and all three
stages verify COMPLETE at checksum depth with a deep-verified sample, every role holds exactly the planned inventory **and** was
requested under the plan (`limit_groups` and `groups_per_shard` equal the plan's), every manifest exists, the **last supervised
attempt of every stage exited 0** and the
journal contains `stages_complete`. A root that verifies but was never produced by a clean supervised attempt (a child that did
the work and then exited non-zero, or foreign data copied in) is not accepted, and neither is a root whose last attempt was interrupted or lost (the root may have been replaced meanwhile): the
supervisor gives it one supervised attempt (the generators treat a finished root as a no-op), retries within the failure budget, and
fails the stage if the child keeps failing. `run.json` also records the SHA-256 of the supervisor and preflight scripts, so editing
either between restarts is refused, and `verify` checks that `completion.json` names this plan, lock and a journal head in the chain.
The marker states `generation_complete`, `scope` (`fixture`), `production_complete=false`, `benchmark_complete=false`,
`production_authorized=false` and the `child_launcher` (a diagnostic-wrapper run says so in its note). A missing stage, role or
manifest, a short inventory, a plan/root mismatch or a missing final record refuses it and writes nothing.

## 7. Exit codes

0 success; 2 refused (usage, plan/identity mismatch, damaged journal, authorization, concurrent supervisor, production request, a
wrapper outside `tests/`); 3 failed (child failure, invalid or drifted artifacts, ceiling or timing-gate stop, incomplete scope, a
dry-run/plan check that FAILs, an unexpected I/O error); 4 dry-run/plan BLOCKED, or verify/status with an orphan awaiting quarantine
(`NEEDS_QUARANTINE` maps to BLOCKED); 5 verify/status found stages not yet complete; 6 interrupted (resumable).

Evidence: the capped real-physics run is in [`docs/results/b2_e7a_supervisor_verification.md`](../results/b2_e7a_supervisor_verification.md) (driver
`scripts/b2_e7a_capped_verification.py`, raw journal committed and verified by a test).

## 8. Limits

Single host and single child process; any move of `HEAD` (even a docs-only commit) fails the lock check, so a long run must not be restarted
across commits; `verify` reads the journal without the workdir lock and can show a transient FAIL on a half-written last line during a live
run; building the lock imports torch and xgboost only to read their versions; `generation_complete` in the marker means the planned fixture
scope only (see `scope`, `production_complete`); RSS polling looks at the child only (descendants are covered by `wait4` afterwards, as an
upper bound); a lost attempt's charge is an estimate; PDEATHSIG and `/proc` are Linux-specific; the dry run creates and removes
one transient `.b2_preflight_probe_*` file in the nearest existing directory (the atomic-rename probe) and nothing else; temporary
`*.tmp` files a killed generator leaves behind are overwritten by the generator's own resume rather than quarantined; the timing band is an extrapolation; the hash chain and all digests detect accidental modification
only; the stand-in child exercises the real generator CLIs but not the physics, and the capped real-physics verification covers two
groups per stage, not production-size behavior (memory, throughput, disk). Enabling a real launch is a later, separately authorized
milestone and would need its own review: authorization record, unbounded command builder, production-size timing validation.

## 9. Independent review and what it changed (E7a)

A read-only multi-lens review (fail-closed supervisor, K18 equivalence, supervisor tests by mutation, training proposal, documentation
honesty) found the following in the first version of this tool; all are fixed or documented, each with a regression test.

| Finding | Fix |
|---|---|
| A child that did the work and then exited non-zero, an inherited `SIGCHLD=SIG_IGN`, or foreign roots with another shard size were reported `STAGES_COMPLETE` / exit 0 | completion needs a clean supervised last attempt; SIGCHLD reset and `wait_failed`; the root's request must match the plan; the launcher is part of the run identity |
| A missing, emptied or tail-truncated journal, or a hand-edited `run.json`, was accepted | `journal.head` anchor, genesis and fingerprint cross-checks, tail check on every append |
| A lost attempt was charged 0 s / 0 CPU; durations used the wall clock | heartbeats and an estimated upper-bound charge; monotonic clock |
| Pausing a healthy run twice dead-ended it | failed attempts, interruptions and lost supervisors are budgeted separately |
| `ru_maxrss` inflated by the supervisor's own memory (570-583 MiB journaled for a ~160 MiB child) | polled `VmHWM` of the child is the measured value, `ru_maxrss` an upper bound, with the blame rule in `rss_exceeded` |
| An unreadable host probe let the run proceed; a ceilings file could stretch a fixture | `NOT_RUN` fails the run; fixture and production ceiling limits |
| Grandchildren that ignore SIGTERM outlived an exited leader | the process group is emptied after every attempt |
| 27 mutants survived the first test suite (signal escalation, gate arithmetic, cumulative budgets, live/after-the-fact RSS, inventory, completion depth, environment scrub, marker, log exclusivity, ...) | the added tests kill all of them except two equivalent ones (a leader-only kill is rescued by the group sweep; the cross-role check in the preflight audit is unreachable behind `role_groups`) |

Not changed: `--child-wrapper` children are still audited only through their output root; stand-in roots carry real source hashes, which is why
the launcher is recorded in the identity and the completion marker.

### Post-merge audit (hotfix after PR #22)

A second read-only review of the merged state (supervisor, K18, gates, documentation) found no path to an unbounded spawn, a production
launch, GPU training or LOKO, no change to any gate or frozen value, and the following, all fixed with regression tests:

| Finding | Fix |
|---|---|
| A lost attempt's CPU charge multiplied by the largest value in the thread environment, which includes `PYTHONHASHSEED` (a seed of 100000 dead-ended a workdir) | only `OMP/OPENBLAS/MKL_NUM_THREADS` count |
| Damage in the middle of the journal during the last attempt still ended `STAGES_COMPLETE` / exit 0 | the whole chain is verified before `stages_complete` |
| A failed spawn left `logs/<stage>-NN.log` behind and every restart collided with it | attempt numbers skip existing logs |
| A SIGTERM-ignoring child survived a killed supervisor | `PR_SET_PDEATHSIG` is SIGKILL |
| A verifying root was accepted after an interrupted or lost last attempt (foreign data could be adopted) | only an attempt that exited 0 accepts a verifying root |
| Children imported whatever `geosim` the environment offered | `PYTHONPATH=<repo>/src` first |
| A production plan could pass its sub-checks with a loosened timing band or disk reserve | timing options refused, reserve has a floor |
| The supervisor scripts were not part of any identity | SHA-256 of supervisor and preflight in `run.json` and the marker |
| A one-record journal without its anchor erased the history | tolerated only while the workdir holds nothing but `run.json`, `lock.json` and the journal |
| `completion.json` was never validated; malformed state files crashed with a traceback; real-time signals crashed the signal naming; `--child-wrapper` accepted any file under `tests/` | checked by `verify`; refused with exit 2; `SIG<n>`; stand-in only |
| A second independent read (same branch): a finished root whose last attempt was the n-th interruption was refused for good; a crash between writing `journal.head.tmp` and its rename dead-ended a one-record journal; an internal `KeyError`/`TypeError` during `run` was reported as a refusal without a `run_failed` record; attempt ids ignored journaled numbers once logs were gone | the no-op verification attempt of a finished root is exempt from the interruption ceiling (failed-attempt count and total backstop still apply); the temp head is tolerated; internal errors end the run as `run_failed` (exit 3); ids skip journaled numbers |
| Mutants that survived (limits at their boundary, `fsync`, lost supervisors in the interruption budget, children's CPU, the disk margin, the tail hash, genesis and fingerprint checks) | tests added, constants pinned to literals |

# E7a supervisor - capped real-physics verification

Status: **fixture execution/recovery demonstration, not production behavior.** `benchmark_complete=false`, `production_complete=false`; no
researcher gate was touched. Two scenario groups per stage (80 observations in total: 64 known, 10 test-only, 6 matched), real generator
CLIs and the real physics chain (no stand-in), driven by [`scripts/b2_e7a_capped_verification.py`](../../scripts/b2_e7a_capped_verification.py)
through [`scripts/b2_production_supervisor.py`](../../scripts/b2_production_supervisor.py) ([P30](../plan/P30_b2_e7a_production_supervisor.md)).
Machine-readable twin: [`b2_e7a_supervisor_verification.json`](b2_e7a_supervisor_verification.json); the raw journal is committed byte for
byte ([`b2_e7a_supervisor_journal.jsonl`](b2_e7a_supervisor_journal.jsonl) + [`b2_e7a_supervisor_journal.head`](b2_e7a_supervisor_journal.head), sha256 `0110afaff4ba321e...`,
112 records, head `78d4d81b56456f83...`); copied into one directory as `journal.jsonl` / `journal.head` it verifies with `Journal.load`
(a test does exactly that). Its argv/log fields hold scratch paths.

Lock: git commit `bda315161775`, tree clean, lock `d081aa2cb17956a6...`.

## Steps (one workdir, three supervisor starts)

| # | Step | Exit | t (s) |
|---|---|---|---|
| 1 | dry_run | 4 | 4.1 |
| 2 | interrupted_after_first_shard | 6 | 45.1 |
| 3 | verify_while_unfinished | 5 | 47.9 |
| 4 | complete_refused_while_unfinished | 3 | 50.8 |
| 5 | supervisor_sigkilled_mid_attempt | -9 | 63.3 |
| 6 | resumed_to_completion | 0 | 392.0 |
| 7 | verify_complete | 0 | 394.9 |
| 8 | complete | 0 | 398.0 |

Exit codes: 4 = dry run BLOCKED (authorization), 6 = interrupted and resumable, 5 = verify found unfinished stages, 3 = `complete` refused,
-9 = the SIGKILLed supervisor, 0 = success. The SIGKILLed supervisor's child died with it; the next start recorded the missing end as
`supervisor_lost` and charged an upper-bound estimate (`estimated` below).

## Attempts

`peak (polled)` is the child's own `VmHWM` sampled while it ran (a lower bound); `peak (ru_maxrss)` is `wait4`'s figure, an **upper bound** that
can also carry the supervisor's own memory at fork (here it equals the polled value in the four measured attempts, so the real generator's peak is about 506-572 MiB; in general the polled value is the child's own).

| Attempt | Reason | Exit | Wall (s) | CPU (s) | Peak polled (MiB) | Peak ru_maxrss (MiB) | Estimated |
|---|---|---|---|---|---|---|---|
| known-01 | interrupted | -15 | 38.037 | 44.8 | 571 | 571 | no |
| known-02 | supervisor_lost | None | 16.119 | 24.1 | 506 (last heartbeat) | - | yes (upper-bound estimate) |
| known-03 | exited | 0 | 244.475 | 286.0 | 591 | 591 | no |
| test-01 | exited | 0 | 52.478 | 60.5 | 578 | 578 | no |
| matched-01 | exited | 0 | 28.553 | 33.3 | 506 | 506 | no |

Whole-attempt cost per stage (start-up and the repeated start-up of every restart included, and the estimated charge of the lost attempt; **this is not a validation of the 3.8-5.0 s/observation band**):

| Stage | Attempts | Observations | Attempt wall (s) | CPU (s) | Wall per observation (s) |
|---|---|---|---|---|---|
| known | 3 | 64 | 298.6 | 354.9 | 4.67 |
| test | 1 | 10 | 52.5 | 60.5 | 5.25 |
| matched | 1 | 6 | 28.6 | 33.3 | 4.76 |

First-shard timing gate records (each subtracts a fixed `--timing-startup-s 6` from a 3-8 observation first shard, so the per-observation figure is
distorted; they show that the gate evaluates, not what a stage costs):

| Attempt | Outcome | s/observation after allowance | Allowance (s) | Observations |
|---|---|---|---|---|
| known-03 | within_band | 3.99 | 6.08 | 8 |
| test-01 | within_band | 4.5 | 6.0 | 5 |
| matched-01 | faster_than_band | 2.97 | 6.0 | 3 |

## Limitations (also in the JSON)

- The journal holds scratch paths in argv/log fields; its chain verifies as committed (Journal.load on the two committed files).
- peak_rss_kib is ru_maxrss, an upper bound that carries the supervisor's own peak at fork; peak_rss_polled_kib is a lower bound.
- The timing-gate figures subtract a fixed --timing-startup-s from 3-8 observation first shards; they are not per-observation costs and do not validate the 3.8-5.0 s/observation band. Use per_stage_attempts for whole-attempt wall per observation.
- A supervisor_lost attempt is charged by an upper-bound estimate (last heartbeat + one interval), not measured.
- Two groups per stage say nothing about production-size memory, throughput or disk.
- The run was driven by this script at the lock commit; the later `--render-only` mode and the `estimated`-row layout of this report changed the rendering only, not what was run.

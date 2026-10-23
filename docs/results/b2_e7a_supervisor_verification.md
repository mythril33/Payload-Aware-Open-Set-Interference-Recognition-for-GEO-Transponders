# E7a supervisor — capped real-physics verification

Date: 2026-10-23. Base `main` `755b474`. `benchmark_complete=false`; nothing here approves a gate. Strict-JSON record with the full hash-chained
journal: [`b2_e7a_supervisor_verification.json`](b2_e7a_supervisor_verification.json). Contract: [P30](../plan/P30_b2_e7a_production_supervisor.md).

**Scope (and nothing more).** `scripts/b2_production_supervisor.py` driving the real generators (`obs-cancel/1`, real physics) with
`--max-groups 2 --groups-per-shard 1`: 80 observations (known 4 roles x 16, test-only 10, matched 6) on this 4-CPU sandbox, CPU only
(Python 3.13.17, NumPy 2.5.4, SciPy 1.18.1, torch 2.14.1), threads 2. No production data, no model training, no GPU, no LOKO.

| Step | Result |
|---|---|
| Dry run (`plan`) | BLOCKED (authorization), 8 checks PASS; working directory not created, no process spawned |
| Run, SIGINT after the first committed known shard | exit 6 `INTERRUPTED`; child ended with SIGTERM (`exit_code` -15, reason `interrupted`); journal intact |
| `verify` | exit 5 (stages incomplete, nothing failed) |
| `complete` while incomplete | refused (exit 3); no `completion.json` written |
| Restart with the identical plan | exit 0 `STAGES_COMPLETE` in 353.5 s; known shard 0 was kept, the remaining 7 known shards, test-only and matched were generated |
| `verify` | exit 0, all three stages COMPLETE with the exact planned inventory |
| `complete` | `completion.json`: `generation_complete=true`, `scope=fixture`, `production_complete=false`, `benchmark_complete=false`, `production_authorized=false` |

| Attempt | Exit | Elapsed s | CPU user+sys s | Peak RSS MiB | First-shard s/observation (band 3.8-5.0, startup allowance 6 s) |
|---|---:|---:|---:|---:|---|
| known-01 (interrupted) | -15 (SIGTERM, reason `interrupted`) | 38.1 | 44.1 | 571.5 | 3.92 within band |
| known-02 (resume) | 0 | 266.0 | 310.0 | 582.7 | 4.53 within band |
| test-01 | 0 | 55.3 | 63.1 | 582.2 | 4.75 within band |
| matched-01 | 0 | 28.9 | 33.5 | 569.8 | 2.99 faster than band (journaled, not stopped) |

Cumulative from the journal: wall 388.3 s, CPU 450.7 s, attempts known 2 / test 1 / matched 1. The journal chain verifies (`Journal.read` -> no problems).

**Reading.** The supervisor's interruption, resume, status, completion and refusal behavior works on the real generators, and the first-shard gate
measured the real per-observation cost of this host: 3.9-4.8 s for the known and test-only stages (consistent with the 3.8-5.0 band behind the
E6 wall-time extrapolation) and 3.0 s for the matched stage, whose narrow carriers are cheaper. That is a handful of shards on one host, not a
production-size measurement: memory and disk at scale, the full 26.6 h estimate and any GPU question remain open
(checklist items `audit.wall_time_unmeasured_at_scale`, `audit.streaming_unmeasured_at_scale`).

The corruption, wrong-role, duplicate-group, orphan, drift, budget, slow-first-shard, exit-code and authorization scenarios are exercised by the 69
stand-in tests (`tests/test_b2_production_supervisor.py`), which run the real generator CLIs with fast fake physics so that each fault can be injected
deterministically.

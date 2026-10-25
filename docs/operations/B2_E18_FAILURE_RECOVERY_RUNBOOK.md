# B2 E18 — failure and recovery runbook (synthetic lifecycle)

Version 1, 2026-10-25. **DR-04 NO-GO — NO COMPUTE AUTHORIZED.** This describes what the *synthetic* lifecycle does and what a human
must decide. It is a design record for a future operator procedure, not an instruction for a production run (none exists).

## Rules that never bend

1. Evidence is never repaired, overwritten, moved or deleted by the controller. Quarantine writes a note **outside** the data tree.
2. A restart rebuilds from the journal and the bytes on disk, or refuses. Memory of the previous process is never trusted.
3. A restart needs the **identical** plan and specification identities, the same source identity, a journal that verifies against
   the independently retained anchor, and fresh signed evidence.
4. Silence is not success: a missing, stale, nonfinite or inconsistent reading, answer or document stops or blocks the run.
5. No fault is ever a reason to relax a validator, to relabel an artifact or to start with `--force`; there is no such option.

## Fault table

| Fault | What the controller does | Evidence left | Human decision |
|---|---|---|---|
| Evidence source unreachable, signature refused, replayed answer, CI not green, gates closed | `BLOCKED`; challenge burned; no shard; `retry()` reruns with fresh evidence | events; journal untouched if not yet opened | fix the source; retry |
| Explicit revocation, unknown status, expired approval | `STOPPED` (final); incident `authorization_revoked`/`authorization_expired` | journal incident + `stop` | new authorization record; new run |
| Mid-stage revocation (every 64 shards or 3600 s, and again before the next shard if the run sat idle) | `STOPPED` (after the shard in flight, or before the next one) | as above | as above |
| Revocation source unreachable at a mid-stage refresh | `STOPPED` **resumable** (`interruption`, signal `REVOCATION_UNAVAILABLE`) | complete shards | `recover` once the source is back (fresh evidence is verified again) |
| Revocation answer present but invalid (forged, wrong grant, stale) | `STOPPED` (final), `resource_observation_missing` | journal | treat as an integrity incident |
| Source/plan/specification/root identity changed | `STOPPED`, incident `identity_mismatch` | journal | investigate; new reviewed run |
| Producer error or contract breach | `STOPPED` **resumable**; `failed_attempts+1` | nothing published for that shard | `recover` (the counters are run-wide: 2 failed attempts in the whole run, a conservative reading of "per stage") |
| `interrupt()` / process killed | `STOPPED` resumable / nothing recorded | complete shards, no temp files if controlled | `recover` |
| Torn write, orphan temp, descriptor lost, bit flip, substituted shard, shard missing, role directory swapped | `QUARANTINED` (final) + note; incident `orphan_files` / `partial_commit` / `shard_corruption` | every byte as found; `quarantine/quarantine-*.json` | human inspects; a new run needs new evidence |
| Disk full / fsync error during publication | `QUARANTINED`, incident `partial_commit` | the partial shard in place | free space; human decides |
| Backup differs from manifest (flip, missing, extra file, role removed) — also when it happens *after* verification, because every boundary re-verifies the backup | `QUARANTINED`, incident `backup_mismatch`; **never re-copied** | both trees as found | human restores from an independent copy |
| Backup device unreachable or full while copying, or failing at a later boundary | `STOPPED` (final), incident `backup_unavailable` (E16's own action is `stop`); `backup_verified` is not journaled | the working tree | free or replace the device; new run under human decision |
| Backup device cannot be read **at recovery** | `recover` refuses (`LifecycleRefused`); **nothing is written**, so it can be retried | the journal as found | make the device reachable; `recover` again |
| Backup of a completed stage is *missing* or different at recovery | `QUARANTINED`, `backup_mismatch` | both trees as found | human restores from an independent copy |
| An admitted shard was replaced by a self-consistent one between publication and verification | `QUARANTINED`, `shard_corruption`; `stage_completed` is **not** journaled | trees as found | human inspects |
| A shard that was never journaled is found at recovery and is not fabricated-bytes-only | `QUARANTINED`, `shard_corruption` | trees as found | find out who wrote it |
| More than one unjournaled committed shard at recovery, or one that is not the next planned shard | `QUARANTINED`, `orphan_files` (only the one in flight at a crash can be adopted; it is then journaled) | trees as found | find out who wrote them |
| Working role changed between verification and backup | `QUARANTINED` | trees as found | as above |
| Data present for a later stage | `STOPPED`, incident `stage_order_violation`; data untouched | the planted files | investigate the producer of those files |
| K17d identity/counts/disclosure differ | `STOPPED`, incident `k17d_mismatch` | journal | D-8 re-derivation and review; never relabel |
| Held-out role in a training/selection/calibration declaration | `STOPPED`, incident `identity_mismatch` | journal | fix the consumer |
| Ledger edited, truncated, rewritten, deleted, unwritable; anchor missing, rolled back, advanced or unwritable — **including while the run is live** | in-memory `STOPPED`, `journal_ok=false`; further steps refused; a new controller refuses to recover | the journal as found | treat as an integrity incident |
| More than one ledger entry beyond the newest anchor at recovery | recovery refused | the journal as found | integrity incident (one trailing entry is the legitimate crash window) |
| Cumulative counters decrease across a restart, or the clock runs backwards | restart refused (`STOPPED` / `LifecycleRefused`) | journal | fix the observer / clock |
| Wall time reported by the observer is shorter than the journal's own span, **at a resume** (reset counters, long outage) | `BLOCKED` (no verdict is written) | journal | give the observer the journaled counters; note that downtime counts against the wall-time budget |
| The same disagreement **during a run** (clock step, VM suspend) | `STOPPED` **resumable** (`interruption`, signal `OBSERVER_CLOCK_SKEW`) | complete shards | `recover` |
| Verification older than 300 s, or past the earlier expiry the signed answers state, at admission or stage start | `BLOCKED`; `retry()` re-verifies from scratch | — | retry |
| A resumed run finds later-stage data, a changed consumer declaration, a K17d deviation or a changed execution-boundary canary | `STOPPED` (final) before it produces anything | journal; planted files untouched | investigate |
| E16 `execution.boundary` no longer BLOCKED | `STOPPED`, `identity_mismatch` | journal | a guard was changed: investigate before anything else |
| Restart allowance exhausted (the plan's ceilings: 2 failed attempts and 20 interruptions per stage, and the supervisor backstop of 60 total attempts, as enforced by the E16 evaluator) | `STOPPED`, incident `ceiling_breach` | journal | a human decides whether a new run is justified |

## Recovery procedure (synthetic)

1. Make sure the old process is gone (the run lock is released when its controller is closed).
2. Build a new profile (fresh clock, producer, resource observer; the same plan, specification and workspace).
3. `SyntheticExecutorLifecycle.recover(profile)`. Refusal → read the message; the journal and data are unchanged. `QUARANTINED` after
   recovery → read the note in the quarantine directory; do not move files.
4. A successful recovery returns a controller in `PREPARED`: call `advance()`; it re-verifies evidence, resumes the stage via
   `check_admission` (mode `resume`) without producing any shard twice, then verifies, backs up and completes.

## What the synthetic run cannot show

Real disk, controller and power-failure behaviour; a different failure domain for backup and journal; a real observer's honesty; any
real signer or revocation authority; production generators. These stay external prerequisites listed in the
[E18 handoff](../plan/B2_E18_EXECUTOR_INTEGRATION_HANDOFF.md) and the [lifecycle design](../plan/B2_E18_EXECUTOR_LIFECYCLE.md).

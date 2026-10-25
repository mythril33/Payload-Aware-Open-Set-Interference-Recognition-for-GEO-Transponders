# B2 E18 — synthetic executor lifecycle

Version 1, 2026-10-25. Verified base: `ad3e241d63875c4603b5843d8ba7a9fe15532253` (PR #41 merged).
**Engineering only — DR-04 NO-GO — NO COMPUTE AUTHORIZED.** Nothing in this milestone generates data, trains, probes a GPU or
starts a production child. Fabricated bytes only; every lifecycle result says `execution_permitted=false`.

## What E18 is

E13–E17 delivered separately verified contracts: the plan validator and sealed specification, the durable-admission
barrier, the hash-chained ledger and stop evaluator, the boundary report, and cryptographic release evidence. Nobody had
shown that they work **together**, in order, across stage boundaries, interruptions and faults. E18 does that with a
dependency-injected lifecycle controller that can only move fabricated synthetic bytes, so the integration is exercised by
executable tests rather than by documents.

It is a *production-executor candidate*, not an executor: it has no production-running state, no flag, environment variable,
record or signature that grants permission, and no entry point that reaches a generator. The only function for real work,
`production_gate`, evaluates the **public** E17 entry (unconfigured trust root) and always returns `BLOCKED`.

| Item | Code |
|---|---|
| Lifecycle controller, custody ports, `production_gate` | [`scripts/b2_e18_lifecycle.py`](../../scripts/b2_e18_lifecycle.py) |
| Fake clock/resources, fabricated-device attestor, bounded synthetic producer | [`scripts/b2_e18_synthetic.py`](../../scripts/b2_e18_synthetic.py) |
| PR-relative scope guard, workflow lint, gate-state decision matrix | [`scripts/b2_e18_ci_policy.py`](../../scripts/b2_e18_ci_policy.py), [workflow](../../.github/workflows/b2-e18-lifecycle-ci.yml) |
| Tests | `tests/test_b2_e18_{lifecycle,trust_resources,recovery,acceptance,ci_policy}.py`, `tests/e18_support.py` |

No E13–E17 module, `src/`, `configs/`, scientific record, canonical gate, memorandum or existing workflow is edited.
`PRODUCTION_LAUNCH_ENABLED=False`, the two-group runnable fixture cap, the E9 guard, E14/E16 refusals and
`PINNED_TRUST_ROOT=None` are unchanged and re-asserted by tests.

## Before / after

| Capability | Before E18 | Real integrated code now | Synthetic-only in E18 | External dependency (absent) |
|---|---|---|---|---|
| Plan, sealed specification, 739-shard inventory | E13/E14 validators | controller refuses a plan/specification that is not the sealed pair | fabricated plan from the E17 test history | researcher DR-04 record; designated host |
| Signature, Git lineage, revocation, CI evidence | E17 verifiers, one-off | **re-run at every stage start and stage end and on a schedule mid-stage** under a one-time challenge; results feed the E16 policy adapters | fabricated ephemeral ed25519 test authority (`SYNTHETIC_TEST_ROOT`) | real signer/issuer keys, `PINNED_TRUST_ROOT`, credentialed CI evidence |
| Stage order known → test-only → matched | boundary report on supplied documents | controller computes the evidence from the bytes on disk and the journal; later request identities are **derived from completed predecessor manifests** | the shard bytes | production generators |
| Durable admission | E16 `admit_shard` primitive | every shard published descriptor-last (no-clobber, 0444), then admitted (verify → fsync files and directory chain → re-verify) | synthetic payload | real storage behaviour; `media_verified` stays false |
| Backup and restore | manifests, `verify_restore` | copy + byte-checked restore per role; drift between verification and backup is refused; recovery re-verifies backups without repairing them | same-volume temporary copy relabelled to the plan's devices | independent persistent device, retention, restore drill |
| External journal | ledger + anchor *format* | journal **is the durable state**: hash chain, independent anchor store, replay custody, run lock; restart rebuilds from it or refuses | reference stores in temp dirs | independent persistent sink/anchor and replay custodian |
| Resource supervision | stop evaluator on supplied readings | evaluated after every admitted shard and at every boundary, counters journaled so a restart cannot reset them | injected CPU/RSS/disk readings | real observer on the designated host |
| Interruption / recovery | none | controlled `interrupt`, crash recovery, restart allowance, durable quarantine | — | operator procedure and human decision |
| CI | historical fixed-SHA guards | PR-relative scope guard + lint + gate decision matrix | — | production trust root for a DR-04-approved state |
| Real production generation | unreachable | **still unreachable** | — | everything above plus a separate launch decision |

## States

`PREPARED → EVIDENCE_VERIFIED → ADMISSION_CHECKED → SYNTHETIC_STAGE_RUNNING → SYNTHETIC_STAGE_VERIFIED →
SYNTHETIC_BACKUP_VERIFIED → SYNTHETIC_STAGE_COMPLETE`, then `PREPARED` for the next stage; plus `BLOCKED`, `STOPPED`,
`QUARANTINED`. Every name that touches data carries `SYNTHETIC`; there is deliberately no `PRODUCTION_*` state. The
transition table is explicit (`TRANSITIONS`); an operation called in the wrong state raises `InvalidTransition` without side
effects.

* **BLOCKED** — a required fact is missing, stale or unproven (evidence source unreachable, signature refused, gates closed, journal
  not yet open, boundary facts incomplete). Nothing ran beyond the point of refusal; `retry()` repeats the blocked step with fresh
  evidence. Before `run_opened` is written the journal is never touched, so a blocked start cannot corrupt the chain.
* **STOPPED** — a stop condition or a tamper signal. `interrupt()` and a producer failure are *resumable* stops (incident
  `interruption`, E16's `resume_only_under_identical_request`); everything else is final and journals its incident plus a `stop`
  entry.
* **QUARANTINED** — evidence integrity is in doubt (corrupt, orphaned, partial, substituted or unreadable shard state; backup that no
  longer equals its manifest). Evidence is preserved byte for byte; an evidence note is written **outside** the data tree; nothing
  is moved, repaired or deleted. Terminal for the controller *and* durable: the journal's `stop` entry makes every later `recover`
  refuse.

`STOPPED`/`QUARANTINED` have no outgoing transitions. Continuing a run is only possible by constructing a **new** controller
with `SyntheticExecutorLifecycle.recover(profile)`.

## The per-stage cycle

1. **`verify_evidence`** — fresh challenge from the replay custody, fresh reference, fresh signed revocation/CI snapshots, E17
   evaluation. Only a `DR04_GENERATION_RECORD_VALID`, `SYNTHETIC_TEST_ROOT`, `execution_permitted=false` result passes. Opens the
   journal (`run_opened`, `authorization_snapshot`) on first success. The challenge is consumed whether the answer was good or not.
2. **`check_admission`** — builds the E16 boundary report for the coming stage (`pre_launch`, `after_known`, `after_test`) from the
   *real* work tree, journal, backup evidence and a fabricated K17d comparison; all adapters answer from one instant. Unmet
   conditions are mapped to a disposition (below). On success: `admission` marker, then `stage_bound` (test/matched) with the request
   fingerprint **derived from the completed predecessors' manifests**.
3. **`run_stage`** — asks the injected bounded producer for one planned shard at a time (≤64 KiB payload, explicitly synthetic
   rows, count must equal the plan), publishes `part`, `meta`, then `descriptor` (last), admits it through the E16 barrier,
   journals `shard_admitted` (with the last cumulative CPU/wall reading), then evaluates the E16 stop conditions. Every 64 admitted
   shards source identity and a fresh signed revocation are rechecked.
4. **`verify_stage`** — deep classification must be `COMPLETE`, manifests are rebuilt (and must equal any manifest the journal already
   holds), files must be read-only; `stage_completed` is journaled once.
5. **`backup_stage`** — copy descriptor-last without overwriting (an existing file must be byte-identical), `verify_restore` per
   role, `backup_verified` (and, after `known`, `k17d_check`) journaled once.
6. **`complete_stage`** — fresh evidence again, then the `after_*` boundary report; only if every document condition passes does the
   stage become complete and the next one `PREPARED`.

## Dispositions of unmet boundary conditions

| Condition (E16 id) | State | Incident journaled |
|---|---|---|
| `durability.<later stage>` has data | STOPPED | `stage_order_violation` |
| `durability.<this or earlier stage>`, `backup.*` | QUARANTINED | `backup_mismatch` (backup) |
| `k17d.metadata` | STOPPED | `k17d_mismatch` |
| `journal.external` (checked after K17d) | STOPPED, journal marked failed | none (the journal is the problem) |
| `isolation.roles` / `isolation.consumers` | STOPPED | `identity_mismatch` |
| `runtime.stop_conditions` | STOPPED | `ceiling_breach` / `projection_breach` / `timing_gate_failure` / `authorization_*` / `resource_observation_missing` |
| any other failed document condition | STOPPED | `identity_mismatch` |
| only missing facts (`NOT_RUN`/blocked) | BLOCKED | — |

Resource faults after a shard follow the same incident mapping. A passing first-shard timing gate does **not** override the
remaining wall/core budget: the projection (`elapsed + remaining × measured rate`) is evaluated independently and is tested to stop
a run whose measured rate is inside the tolerance but whose remaining work no longer fits.

## Recovery

The journal is the durable state; memory is never trusted. `recover(profile)`:

1. refuses unless the ledger verifies against the independently retained anchor, begins with the same plan/specification identity,
   contains no `stop`, no halting incident, one authorization record, and a completed-stage prefix of `known, test, matched`;
2. re-derives later request bindings from the journaled manifests and refuses a mismatch;
3. classifies every role directory; any orphan, partial, corrupt, unplanned or unreadable state, a shard that differs from its
   journaled admission digest, a journaled shard that is missing, or a completed role that differs from its manifest → `QUARANTINED`;
4. re-admits committed shards (verify → fsync → verify), verifies completed stages' backups **read-only**, and continues the
   cumulative CPU/wall floor from the journal;
5. records an unannounced exit as an inferred `interruption` and appends `resume` with the identical identity; a clock that runs
   backwards or a journal that cannot be extended is a refusal.

A restart starts at `PREPARED`: fresh signed evidence is required again, and the restart allowance (failed attempts, interruptions,
total attempts) is enforced by the E16 evaluator with `restarting=true`.

## Why real production stays unreachable

* No state, method or flag means "production"; AST tests forbid launch-like names, subprocess/threading/network/numeric imports,
  environment reads and eval in the core, and forbid the core importing the synthetic module.
* `production_gate` calls only the public E17 entry; with `PINNED_TRUST_ROOT=None` the answer is `BLOCKED_TRUST_ROOT_MISSING`, and
  the function never touches a port.
* The controller's own trust path is the E17 *test-root* harness and labels every result `SYNTHETIC_TEST_ROOT`. The profile has no
  mode/permission field and rejects unknown ones.
* The producer is a bounded callable returning ≤64 KiB of explicitly synthetic rows; the controller never calls a generator.
* The acceptance test asserts all of this **with every fabricated record valid** and a fully completed three-stage run.

## CI and provenance

See [stage-boundary checklist](../operations/B2_E18_STAGE_BOUNDARY_CHECKLIST.md) and [verification](../results/B2_E18_VERIFICATION.md).
Historical guards of the E15/E16/E17 workflows (fixed commits `290f9d5…`, `d828739…`) are untouched and re-asserted. The E18
workflow compares against the **PR merge base**, so a legitimately merged earlier change is never an "alteration of history", while a
changed scientific record, canonical gate, historical dossier, reviewed contract module or any path outside the E18 scope fails.
`b2_e18_ci_policy.py gate-decision` accepts only `CLOSED_CANONICAL` today; an approved-shaped gate is rejected whenever no production
trust root is configured, and a `SYNTHETIC_TEST_ROOT` report never validates a real branch.

## Not integrated (E19 candidates, all need human decisions)

Real trust-root provisioning and signer/issuer custody; the designated host, real CPU/RSS/disk observer and independent persistent
backup; an external append-only journal sink and replay custodian; the production K17d metadata cross-check; the DR-04 record,
final lock on the approval commit and a separate launch decision; the guard/activation mechanism for a reviewed release; and the
physical generators (changing `src/geosim` would re-open the D-8 re-derivation sequence).

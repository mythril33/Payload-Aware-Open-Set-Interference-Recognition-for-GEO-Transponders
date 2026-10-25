# B2 E16 — runtime safety checklist

2026-10-25. A checklist for a future, separately reviewed executor. **No executor exists; DR-04 is NO-GO; nothing here
authorizes or runs anything.** Every box is unchecked on purpose: E16 delivered the *contracts* and their synthetic tests,
not the real host, device, ledger, backup or adapter facts.

Legend — **C**: contract implemented and tested against synthetic evidence in this repository. **N**: not wired to any
production executor (none exists). **X**: external fact that only an operator can establish; E16 has nothing for it.

## A. Standing conditions (all boundaries)

| ☐ | Condition (report id) | What it enforces | C | N | X |
|---|---|---|---|---|---|
| ☐ | `execution.boundary` | launch flag False; fixture cap 2; E9, E14, E16 refusals raise; supervisor builds no unbounded command (permanent BLOCKED) | ✔ | ✔ | |
| ☐ | `inventory.frozen`, `spec.sealed`, `sequence.stages` | 21,350 observations / 739 shards / 2,450 groups; submitted specification equals the one sealed from the plan; known → test → matched | ✔ | | |
| ☐ | `identity.source_config_environment` | clean tree, per-file source hashes, configs, generator provenance, parsed physics, tools, pinned environment, lock | ✔ | | |
| ☐ | `plan.dr04`, `reporting.d1_d8` | E13 plan complete and consistent; D-1 (test not pristine, 498/148 rows) and D-8 (500/35/43/78/465) preserved | ✔ | | |
| ☐ | `authorization.scope`, `authorization.policy` | exactly `full_generation` for the three stages; record valid with signer, reviewed-commit ancestry, revocation, expiry, freshness | ✔ | ✔ | ✔ real signer/ancestry/revocation sources |
| ☐ | `runtime.stop_conditions` | wall/core/RSS/disk/backup ceilings, attempts, restart allowance, first-shard timing, projection, expiry, revocation | ✔ | ✔ | ✔ real resource observer |
| ☐ | `journal.external` | hash-chained, anchored, outside the working tree, entries bound to the working-tree manifests | ✔ | ✔ | ✔ separate persistent location, anchor custody, immutable sink |

## B. Per boundary

| Boundary | Must already hold | Must not exist yet | Next stage admitted only if |
|---|---|---|---|
| `pre_launch` | all A conditions; resource reading for `known`; roles absent or empty | any shard, temp file or role data in any stage | all above `PASS` (never an execution permission) |
| `after_known` | `known` COMPLETE (deep classification, one durable admission per shard, manifest = admitted bytes, read-only files, restore re-verified on the planned backup device); production K17d comparison `PASS`; journal `known: completed → backed up`, `k17d_check` | any `test` or `matched` data | resources for `test`; `test` request binding journaled before its first shard |
| `after_test` | `known`, `test` COMPLETE and backed up; deferred `test` fingerprint ≠ `known` | any `matched` data | resources for `matched`; `matched` binding journaled |
| `after_matched` | all three COMPLETE, backed up, journaled; K17d still `PASS` | — | generation *complete as a document*; D-1/D-8 disclosure mandatory in every later report; K17d cross-check remains mandatory before any separately authorized final evaluation |

## C. Stop and quarantine actions (derived, never supplied)

| Incident | Mandatory action |
|---|---|
| shard corruption, orphan files, partial commit, backup mismatch | stop **and quarantine in place** (evidence note outside the data tree; nothing moved, deleted or repaired) |
| identity mismatch, ceiling or projection breach, timing-gate failure, expired or revoked authorization, stage-order violation, missing resource reading, journal integrity failure, backup unavailable | stop |
| K17d mismatch | fail closed; re-derive with independent review |
| interruption | resume only under the identical plan and specification, recorded in the journal |

A non-resumable incident halts the run for good; a new run needs a new authorization.

## D. Facts E16 cannot supply (all open)

☐ designated production host with measured CPU/RAM/disk · ☐ persistent, physically independent backup (and a recorded
restore drill) · ☐ external journal location with anchor custody and an immutable sink · ☐ run-bound ceilings approved in a
DR-04 record · ☐ signature, ancestry and revocation sources · ☐ final clean lock · ☐ a reviewed executor that calls the
durable-admission barrier · ☐ researcher DR-04 authorization · ☐ separate launch decision.

## E. Limits (read before relying on any box)

* `st_dev` differences, `media_verified=false`, `worm_proven=false` and `physical_independence_proven=false` are reported
  literally: fsync and a post-eviction re-read are evidence, mode bits are accident protection, a different device number is
  not a different failure domain.
* Evidence is as truthful as the adapter that returned it; E16 binds independent records to each other and to the sealed
  plan so that a forgery must be consistent everywhere, but it cannot authenticate hardware.
* An admission snapshot cannot stop a later hostile writer: boundaries must be re-checked at runtime.

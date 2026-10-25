# B2 E18 — stage-boundary checklist

Version 1, 2026-10-25. **Engineering checklist for the synthetic lifecycle — DR-04 NO-GO — NO COMPUTE AUTHORIZED.** Passing every
item below is evidence about *documents and fabricated bytes*; it is not permission to run anything. The "Automated" column says what
`SyntheticExecutorLifecycle` already checks at the boundary; the "Human / external" column lists what no code in this repository can
supply today.

Boundaries: `pre_launch` (before `known`), `after_known` (before and after `test`), `after_test` (before and after `matched`),
`after_matched`. The lifecycle evaluates one E16 boundary report before a stage starts and one when it completes.

| # | Boundary item | Automated check (E16 condition id) | Human / external dependency (absent) |
|---|---|---|---|
| 1 | Trusted evidence is fresh: signature of the exact committed record, Git lineage reviewed R → approval A, scoped DR-04 block, signed revocation `ACTIVE` for this grant, signed exact-head CI, one-time challenge | E17 evaluation before each stage start and end; `authorization.policy`, `authorization.scope` | real signer/issuer keys, `PINNED_TRUST_ROOT`, credentialed CI evidence, durable replay custodian |
| 2 | Source, configuration, environment, lock identity equals the sealed plan; no untracked importable file | `identity.source_config_environment`, `plan.dr04`; E17 clean-checkout verification; source recheck every 64 shards | clean production lock on the approval commit, designated host |
| 3 | Approval has not expired and is not revoked | `authorization.unexpired`, `authorization.not_revoked`, `runtime.stop_conditions` | a genuine DR-04 record with run-bound expiry |
| 4 | Frozen inventory and sealed specification | `inventory.frozen`, `spec.sealed`, `sequence.stages` | — |
| 5 | D-1 non-pristine disclosure (498/148 rows) and D-8 K17d identity (500/co35/cross43/total78/complement465) preserved | `reporting.d1_d8`; from `after_known`: `k17d.metadata` + a journaled `k17d_check` with the same identity | the **production** K17d metadata cross-check (fabricated here; summaries say `NOT_RUN`) |
| 6 | Predecessor stages complete; **no data exists for any later stage** | `durability.<stage>` (stage-order data → STOPPED) | — |
| 7 | Every planned shard committed: descriptor, payload and metadata hash-verified, durably admitted, read-only, unaliased, no orphan | `durability.<stage>` (deep classification `COMPLETE`, admissions, manifest, immutability) | behaviour of the real storage; `media_verified` is always false |
| 8 | Role isolation: stage roots and role directories are distinct; train/val-select/val-calib read only their own known roles; test and matched roles never reach training, selection or calibration | `isolation.roles`, `isolation.consumers` | an enforcing runtime for real consumers (none exist yet) |
| 9 | Later request identity is bound to the completed predecessor artifacts, not to a fixture, and does not alias another stage | journal `stage_bound` derived from predecessor manifests; alias check | — |
| 10 | Backup: byte-verified restore of every role; working and backup devices distinct, durable filesystems, enough capacity | `backup.<stage>` (restore re-verification; device validation over **fabricated** device records) | independent persistent backup, capacity/retention choice, restore drill |
| 11 | External journal: hash chain, independent anchor, ordered stage entries bound to the working-tree manifests, no unresolved interruption or halting incident | `journal.external` | independent append-only sink and anchor custody on a different failure domain |
| 12 | Resources within ceilings and projections (wall, core, RSS, disk, backup space, attempts, interruptions, first-shard timing) | `runtime.stop_conditions` + per-shard evaluation, counters journaled | a real CPU-only observer on the designated host and approved ceilings |
| 13 | Execution boundary | `execution.boundary` — **permanently BLOCKED** | a separate, reviewed launch decision and executor (not part of E18) |

## Disposition if an item fails

STOPPED (final): stage order, K17d, role isolation, resource/timing/authorization stop conditions, identity or journal faults.
QUARANTINED (final, evidence frozen): integrity of shard state or backup. BLOCKED (retry): missing or unproven facts.
STOPPED by `interrupt()` or a producer failure is the only resumable stop. See the
[failure and recovery runbook](B2_E18_FAILURE_RECOVERY_RUNBOOK.md).

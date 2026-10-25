# B2 E18 — executor integration handoff

Prepared by E17, version 1, 2026-10-25. **HANDOFF ONLY — E18 NOT STARTED.**
**DR-04 NO-GO — NO COMPUTE AUTHORIZED.** This is not a production command,
approval, release transition or instruction to bypass an existing guard.

## Smallest next engineering package

Build a separately reviewed, initially non-launching integration boundary that
obtains the E17 trusted evidence from operator-controlled sources, revalidates it
at every stage, and connects the E16 source/lock/durability/backup/journal/resource
contracts to an execution design. Prove the entire boundary with capped synthetic
fixtures before considering any separately approved production release.

| Engineering work remaining | Concrete acceptance evidence before a release |
|---|---|
| Trusted configuration entry point | No caller-supplied boolean verifier or mutable approval-owned trust root; configured signer/issuer policy pins and independently controlled challenge/replay state |
| Source and approval lineage | Exact reviewedR → approvalA object verification, strict changed-file set, canonical record bytes, unchanged tools/config/science, clean source and final lock on A |
| Stage-boundary state machine | known → test-only → matched; no later data before its predecessor; full21,350/2,450/739 inventory; verify later request identity against the completed known artifact rather than a fixture |
| Durable admission and failure handling | E16 classify → validate → fsync → revalidate barrier, descriptor/payload/metadata integrity, immutable completed roots, no silent repair/deletion, external quarantine evidence |
| Persistent backup and restore | Actual approved device/host evidence, byte-bound manifests and source/config/environment identity, sufficient staging/retention capacity, restore re-verification and a separately scoped drill |
| External journal custody | Independent persistent sink, append-only/anchor policy and replay state surviving working-volume failure; stage, incident and evidence bindings |
| Resource and timing supervision | Real CPU-only observer, approved wall/core/RSS/disk/restart ceilings, first-shard timing plus remaining-budget projection, stop on missing/stale/expired/revoked evidence |
| CI and review evidence | Exact final source and required workflow conclusions verified independently; no older green head or synthetic success claim substituted |
| Separate release design | Guard/activation mechanism finalized and reviewed before design approval; no late source edit under a previous approval or lock; no automatic launch decision |

E17 implements evidence verification, not these runtime connections. The existing
two-group runnable fixture ceiling and E9/E14/E16 refusals remain in force until a
future separately reviewed release process explicitly addresses them. This handoff
does not lift them.

## External operational prerequisites

All of the following are absent or unqualified; E17 cannot create them:

- Researcher-approved real signer identity/public-key association and independently
  reviewed allowed-signer trust policy.
- Independent authenticated revocation authority, trusted current time and durable
  request-challenge/replay custody.
- Credentialed read-only CI access or an independently authenticated reviewed CI
  snapshot for the actual final head and required workflows.
- Explicitly designated generation host with fresh CPU/RAM/environment/device
  measurements, not the sandbox or a CI runner.
- Persistent physically independent backup, external journal/anchor location,
  capacity and retention choices, and the required restore evidence.
- Run-bound ceilings, scope and expiry in a genuine DR-04 researcher record; final
  clean production lock after that approval commit; separate launch decision.

The E15 proposals remain proposals:4vCPU,8GiB host RAM,2GiB process RSS,36wall
hours,42core-hours, approximately33.880GiB startup free space and12GB single-copy
backup. Two-copy retention/staging requires at least17.3362GB before overhead.
These are not measured production requirements or authorization. No ceiling is
adopted by this handoff.

## Ordered dependencies

1. Resolve trust/host/storage evidence and design the integration without running
   production or making a real approval.
2. Finish the executor/release-policy source, tests and independent review. If any
   geosim file changes, keep old records immutable and complete metadata-only D-8
   re-derivation/review and required explicit acceptance before reusing that binding.
3. Obtain green exact-head CI and freeze the final reviewed code/config/tool design.
4. Present the host-bound plan/design digest and scoped resource/expiry proposal to
   the researcher for a separate DR-04 decision.
5. If granted, verify exact approval lineage and signatures; create the final lock
   on the approval commit, because the gates JSON is part of the lock.
6. Revalidate host, devices, identity, freshness, revocation, replay state, budgets,
   CI and lock. Request a separate release/launch decision; do not infer one.

Changing the launcher, guard, workflow or covered tool identity after approval
requires renewed identity/review and possibly renewed approval. Never break a hash
cycle by dropping a protected field or relabelling an artifact/checkpoint.

## Scientific and execution limits

R1–R10, D-1–D-8, labels, roles, seeds, P20 observation-only cancellation and physical
models remain frozen. D-1's non-pristine disclosure and498/148 sensitivity rows
remain mandatory. D-8 requires exact500/co35/cross43/total78/complement465 identity
and later production-metadata verification before separately authorized final
evaluation. No test-informed tuning is allowed.

No production dataset, GPU discovery/probe/training, D-5 sweep, LOKO, held-out
inference or E18 implementation is authorized by this document.
`PRODUCTION_LAUNCH_ENABLED=False`, `benchmark_complete=false`; all real canonical
compute gates remain `NOT_AUTHORIZED` and every E17 report keeps
`execution_permitted=false`.

# B2 E14 — future production release checklist

Version 1, 2026-10-25. Verified base: `5ba972da6d3dee097cfee9cb79a5c1b27a1c139b`.
**DR-04 NO-GO — NO COMPUTE AUTHORIZED.** This checklist records requirements;
it grants nothing and supplies no production command.

## Current boundary

Scientific K18, K17d, OBS-CANCEL-2, R1–R10 and D-1–D-8 records remain approved.
`full_generation`, GPU probe, `full_gpu_training`, `full_loko_sweep` and final
held-out evaluation remain unauthorized. `benchmark_complete=false`,
`PRODUCTION_LAUNCH_ENABLED=False`, E9 `guard_execution` always refuses and the
existing runnable supervisor still permits at most two fixture groups.

E14's sealed specification binds the E13 plan to exact identities and keeps
known → test-only → matched ordering. Admission always reports `NO-GO`, even
for internally consistent synthetic approval records. No production argv,
subprocess adapter, activation flag or automatic approval transition exists.

## Requirements for a separate future release

Every row must be evidenced for the same proposed run. An unchecked row blocks
release; a checked engineering row is not an authorization.

| ID | Required evidence | Executable E14 control / remaining blocker |
|---|---|---|
| L-01 | Researcher's explicit DR-04 written compute authorization, in both gate and memorandum twin | E13 validates committed-record provenance, plan/code/host/storage/ceiling bindings, scope and expiry. Actual authorization remains absent. Scientific ratification or CI cannot substitute. |
| L-02 | Exact independently reviewed source HEAD | Sealed stage identities carry source/config/tool digests and commit. A future executable path has not been reviewed or released. |
| L-03 | Successful CI for that exact HEAD | Admission checks the evidence's head; an embedded record is self-asserted and must be checked against GitHub independently. E14 CI is engineering evidence only. |
| L-04 | Independent review of the actual production execution path | Production execution is deliberately unavailable. Model-agent review is not human approval or a release decision. |
| L-05 | Explicit ceilings approved and bound to the run | E13 checks the finite field set and approval equality. E11-B values below remain proposals; no ceiling is adopted by this document. |
| L-06 | Designated, measured generation host | Host identity, CPU/RAM, environment pins and fresh path measurements are required. No target host is designated by E14. |
| L-07 | Verified persistent independent backup device and restore procedure | E14 storage contracts compare fresh measured records, identity, free space and capacity, and refuse volatile/unknown filesystems, aliases and same-device/nested roots. Physical independence still requires operator evidence. No production backup was made. |
| L-08 | Clean pinned source/config/environment lock | Create only after the final reviewed source and authorization commit; the gate JSON itself is hashed. Reuse after any covered identity change is refused. No production lock is created here. |
| L-09 | First-shard timing and resource-stop controls | Specification preserves the timing band and requires remaining wall/core projections. Enforcement at production scale is not implemented or measured. |
| L-10 | External append-only run journal, durable publication and failure quarantine | Existing capped supervisor journal remains unchanged; E14 verifies durability with bounded synthetic bytes only. Physical generator fsync integration and production journal integration remain open. |
| L-11 | Expiry, immediate stop conditions and separately reviewed activation | Expired/mismatched records fail admission; no running/released state is reachable. A future release must recheck before each stage/commit and stop on identity, resource, timing, integrity or authorization failure. |

## Resource interpretation

| Evidence class | Figure | Meaning |
|---|---|---|
| Analytic inventory | 21,350 observations; 2,450 distinct groups; 739 four-group shards | Frozen counts, not permission to generate them. |
| Analytic arrays | 395,264 bytes/observation; 8,438,886,400 bytes total | Excludes metadata and filesystem overhead. |
| Historical pilot basis | 406,000 bytes/observation; 8,668,100,000 bytes estimated artifacts | Production-size storage is not measured. |
| Startup arithmetic | `25 GiB + 1.1 × 8,668,100,000 bytes` = approximately **33.880 GiB** free | The 25 GiB is a remaining reserve. The older preflight's 25 GiB free check alone is insufficient. |
| Historical pilot | Roughly 566–601 MiB process RSS and 4.58/5.27/4.83 s per observation in capped generation | These are earlier pilot measurements, not E14 results or target-host evidence. |
| Extrapolation | About 23–30 h wall and 26–35 core-hours | Host throughput and production-size peak RSS remain unmeasured. |
| Ceiling proposals | 36 h wall; 42 core-hours; 2 GiB process RSS; 8 GiB host RAM; 4 vCPU | E11-B planning envelope; researcher must explicitly choose ceilings. |
| Backup proposal | 9 GB floor, 12 GB preferred | Must cover actual artifacts, manifests, evidence and recovery margin on a distinct persistent device. |

No GPU probe or GPU discovery is needed for CPU-generation preparation. Do not
use a host collector that queries GPU tooling merely to populate this checklist.

## Future sequence and scientific obligations

1. Complete and independently review the future executor and durable generator
   integration without weakening the current caps in this milestone.
2. Designate host, independent storage and ceilings; collect fresh CPU/storage
   facts and operator evidence of persistence and physical independence.
3. Seal the final plan and obtain the separate researcher DR-04 record. Commit
   it in the gate/memorandum before creating the production lock.
4. Obtain exact-head CI and review evidence; revalidate the sealed plan and lock
   on the designated host. A subsequent release review must enable execution;
   E14 cannot do so.
5. Only a separately authorized future run may produce known, then test-only,
   then matched artifacts. Later request fingerprints must bind the verified
   known artifact; they cannot be invented before it exists.
6. Before any separately authorized final evaluation, run the metadata-only
   K17d cross-check against accepted exact group/polarization identity and the
   separate payload/backup integrity audit. The real production check is
   **NOT RUN**. Preserve D-1's non-pristine-test disclosure and mandatory 498/148
   exclusion-sensitivity reporting alongside headline 500/150 groups.

`src/` and scientific configurations remain unchanged by the isolated E14
scripts. New tool hashes invalidate an earlier tool-bound plan/approval identity;
future locks must bind the final release. Historical results and checkpoints are
never relabelled. See [architecture](../plan/B2_E14_PRODUCTION_LAUNCHER_ARCHITECTURE.md),
[backup procedure](B2_E14_BACKUP_RECOVERY_PROCEDURE.md) and
[verification](../results/B2_E14_VERIFICATION.md).

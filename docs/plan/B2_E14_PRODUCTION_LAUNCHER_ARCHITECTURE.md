# B2 E14 — sealed production launch architecture

Version 1, 2026-10-25. Baseline `5ba972da6d3dee097cfee9cb79a5c1b27a1c139b`.
Engineering preparation only: DR-04 NO-GO; no compute authorized.

## Architecture decision (recorded before implementation)

Reuse the E13 plan validator; add isolated, scripts-only components. Planning
returns immutable, hashed JSON specifications, admission returns evidence and
NO-GO, and execution is unavailable. No argv, callable generator, subprocess
launcher or activation option is introduced. Existing supervisor, E9 guard,
two-group cap, scientific records, source physics and configurations stay intact.

Durable publication is demonstrated by a separately capped, explicitly synthetic
byte-fixture utility, not wired into the physical generators. Production
integration requires a separate release review: changing the frozen geosim source
would invalidate the accepted E12 generator identity. Metadata verification reads
only future manifest/request/descriptors/JSONL, never observation arrays or
performance outputs. Backup checks distinguish measured filesystem facts from
operator claims of physically independent persistent storage.

An admission snapshot cannot prevent a later filesystem or host change. A future
executor must revalidate source/environment/host/authorization before every stage
and use descriptor-relative no-follow paths, durable commits and an external
append-only journal. This milestone provides no such executor.

## Gap matrix at the decision point

| Control | Before E14 | E14 scope / remaining limit |
|---|---|---|
| Inventory, role separation, four-group planning | IMPLEMENTED AND VERIFIED in E13 | Reuse exact 21,350 observations, 2,450 groups, 739 shards |
| Immutable launch specification | DOCUMENTED ONLY | Sealed JSON specification, exact source/config/environment binding |
| Production launcher | MISSING / BLOCKED BY AUTHORIZATION | Deliberately unavailable; fixture supervisor unchanged |
| DR-04 and release admission | IMPLEMENTED BUT INCOMPLETE | Reuse E13 authorization checks; require separate release; always NO-GO |
| Disk reserve | IMPLEMENTED BUT INCOMPLETE | Reserve means remaining 25 GiB; startup >= 33.880 GiB using 1.1 x estimated bytes |
| Source/environment lock | IMPLEMENTED BUT INCOMPLETE | Bind plan/spec to exact identity; actual clean production lock absent |
| Persistent independent backup | IMPLEMENTED BUT INCOMPLETE | Strict measurement/identity/checksum contract; operator designation absent |
| Atomic commits / recovery | IMPLEMENTED BUT INCOMPLETE | Synthetic fsync/no-clobber/quarantine verification; generator wiring absent |
| Production K17d metadata comparison | MISSING | Metadata-only future-artifact verifier; actual production verification NOT RUN |
| Timing / stop / journal | IMPLEMENTED BUT INCOMPLETE | Fixed specification; production enforcement and scale measurement absent |
| D-1 exposure / D-8 acceptance | IMPLEMENTED AND VERIFIED | Preserve 498/148 disclosure and accepted exact K17d identity |
| Runtime release | BLOCKED BY AUTHORIZATION | No release transition; no gates changed |

## Verification and limitations

Final implementation controls, independent findings and exact commands are recorded
in `docs/results/B2_E14_VERIFICATION.md`. No green test, consistent approval-shaped
JSON or scientific ratification is an execution authorization. Future test/matched
request fingerprints depend on a verified known artifact and cannot be fabricated
in advance. Synthetic metadata acceptance is not production cross-verification.

## Implemented boundary after E14

| Component | Implemented and tested | Still unavailable |
|---|---|---|
| `b2_e14_launch_contract.py` | Hashed JSON specification with 739 explicit shard identities, per-stage source/config/environment/lock identity; strict plan/options; independent predecessor chain; E13 admission reuse; unconditional execution refusal | No production argv, subprocess adapter, generator callback or runtime transition; release records remain externally verified evidence |
| `b2_e14_storage.py` | At most two explicitly synthetic groups and 64 KiB labelled bytes, no-clobber descriptor-last durable reference publication, directory sync, corrupt/orphan refusal and evidence-preserving quarantine, exact-identity restore verification; measured-device record comparison and CPU/storage-only observer | Not wired into generators or launch admission; no production committer/copier/restore, physical independence not proved, no WORM access-control guarantee |
| `b2_e14_verify_metadata.py` | Future known-artifact test-role manifest/descriptor/JSONL comparison with accepted E12 identity, exact group/polarization/index predicates and all eight variants; metadata checksum/source/request bindings | Real production cross-check NOT RUN; NPZ/calibration arrays and non-test-role shard contents deliberately unopened; separate full byte-integrity audit required |

The before/after status for production execution, durable production commits,
active backup supervision and runtime release remains **BLOCKED BY AUTHORIZATION**
and **IMPLEMENTED BUT INCOMPLETE / DOCUMENTED ONLY** as applicable. Synthetic
reference tests close implementation gaps in the isolated contracts; they do not
turn them into a released production workflow. The generation host, persistent
backup, ceilings, DR-04 record, clean final lock and separate activation review
remain missing for any run.

Independent model-agent review found and resolved three material contract issues:
R14-1 (matched predecessor named known instead of test), R14-2 (metadata root
namespace substitution), R14-3 (quarantine root/entry substitution). Each has a
bounded negative regression test. This review is not human approval. Exact final
review/test evidence is in the verification report.

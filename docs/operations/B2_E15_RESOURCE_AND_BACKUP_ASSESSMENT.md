# B2 E15 — resource and backup assessment

Version 1, 2026-10-25. Reviewed baseline
`9e176ad20aa1f355adac06e5a22c77b38a616099`.
**PROPOSALS / ARITHMETIC ONLY — DR-04 NO-GO — NO COMPUTE AUTHORIZED.**
No designated-host measurement, generation, backup, restore, GPU query or benchmark
was performed. E15 recomputes committed constants; it changes no scientific count,
ceiling, gate or historical result.

## Evidence classes and inventory

High confidence below means arithmetic conditional on the frozen layout, not
confidence in production performance. Historical pilots are small, on other hosts;
extrapolations have no statistical confidence interval. A proposal needs a separate
researcher choice and cannot be silently adopted by this assessment.

| Stage/role | Groups | Variants/group | Observations | Four-group shards |
|---|---:|---:|---:|---:|
| Known/train | 1500 | 8 | 12000 | 375 |
| Known/val-select | 150 | 8 | 1200 | 38 |
| Known/val-calib | 150 | 8 | 1200 | 38 |
| Known/test | 500 | 8 | 4000 | 125 |
| Test-only/test, same 500 test IDs | 500 shared | 5 | 2500 | 125 |
| Matched/test-matched | 150 distinct | 3 | 450 | 38 |
| **Total** | **2450 distinct** | — | **21350** | **739** |

Sources: `b2_protocol` frozen roles and labels;
`b2_production_preflight.py:derive_inventory`, independent E5 table, and E13/E14
contracts. Shards in the 150-group roles end with two groups. Roles, seeds and
known → test-only → matched dependencies remain unchanged.

## Storage and resource table

GB means 10^9 bytes; GiB means 2^30 bytes. Values are for one working copy unless
explicitly stated otherwise.

| Quantity | Recomputed figure | Evidence class / confidence / limitation |
|---|---|---|
| Stored float16 arrays | 395264 B/observation ×21350 = **8438886400 B**, 8.4388864 GB / **7.859325409 GiB** | Analytical layout, high conditional confidence; excludes metadata/filesystem overhead |
| Artifact allowance used by supervisor | 406000 B/observation ×21350 = **8668100000 B**, 8.6681 GB / **8.072797209 GiB** | Historical pilot-derived estimate, not full-scale measurement |
| Implied metadata/artifact increment | 229213600 B, **2.716159%** above array bytes | Difference of estimates; not measured production metadata size |
| Data-volume start condition | 25 GiB remaining reserve +1.1×artifact estimate = **36378455600 B**, **33.880076930 GiB** free | Analytical application of supervisor's rule; round to >=34 GiB for procurement only |
| Backup floor | 9 GB: only 331900000 B above estimated artifacts | E5 unapproved proposal; narrow allowance does not prove room for actual files/evidence |
| Preferred backup proposal | 12 GB: 3331900000 B above estimated artifacts | E11-B unapproved proposal; independent persistent device, actual capacity/free checks required |
| CPU profile | >=4 usable vCPU, one generator process; historical runs used two BLAS threads | Unapproved profile, not measured target capacity; extra cores do not imply a parallel writer exists |
| Host RAM / process RSS | >=8 GiB host / <=2 GiB generator RSS | Unapproved proposals; historical generator peaks approximately 566–601 MiB at small counts |
| Generation wall / CPU ceilings | 36 h wall / 42 core-h | Unapproved proposals; include all attempts/verification overhead within cumulative budget |
| Failed attempts / interruptions | <=2 failed attempts and <=20 interruptions per stage; existing hard attempt backstop 60 | Supervisor planning constants, not researcher-approved restart allowance or evidence of sufficient time |

The older preflight's comparison with **25 GiB free** is not the supervisor's
**25 GiB remaining reserve**. E15 uses the stricter startup arithmetic above;
`1.1×7.86 GiB` in earlier E11-B prose uses array bytes, while executable supervisor
code uses the 406000-B artifact estimate. Neither is a measured disk requirement.
Quarantine evidence, journal, calibration, temporary commits, filesystem allocation,
backup staging and any additional incident copies must fit the eventual approved
capacity policy. Do not assume the 10% artifact margin covers every failure mode.
The 12-GB proposal covers one estimated copy only. Retaining the last good backup
while creating a fresh staging copy on the same backup device requires at least
**2 ×8668100000 =17336200000 B (17.3362 GB)** before additional overhead/evidence.
Choose and budget retention, staging and rotation explicitly; this arithmetic does
not raise the proposed ceiling or authorize another copy/device.

## Time, CPU and restart uncertainty

`b2_production_preflight.wall_hours(s)` treats 500 CID observations at 8 s each:

`wall_hours(s) = (20850 × s + 500 × 8) / 3600`.

| Seconds/non-CID observation | Uniform 21350×s wall h | CID-corrected wall h | CPU core-h at 300.2/262 |
|---:|---:|---:|---:|
| 3.8 | 22.536111 | **23.119444** | **26.490295** |
| 4.4, code's central constant | 26.094444 | **26.594444** | **30.471955** |
| 5.0 | 29.652778 | **30.069444** | **34.453615** |

These are extrapolations from planning assumptions, not measurements or confidence
intervals. The historical 60-observation matched profile supplied 300.2 CPU-s /
262 wall-s = **1.145801527** core-seconds per wall-second. Two BLAS threads do not
mean two fully utilized CPU cores; the ratio must be measured on the designated
host during a separately authorized run. CPU quota, contention, numerical-library
builds, storage, compression and verification may change it.

Historical E7a whole-attempt pilot rates were 4.58 known / 5.27 test-only / 4.83 matched
s/observation; weighting by 18400/2500/450 gives **27.672361 h**. This is another
extrapolation of startup-inflated tiny pilots, not a new throughput measurement.
E11-B's uniform 4.49-s central illustration gives 26.628194 h; it differs from the
code's 4.4-s central constant plus explicit CID correction (26.594444 h). Keep the
bases named rather than presenting their rounding differences as measured changes.

Relative to the CID-corrected high estimate, proposed 36/42 ceilings leave
**5.930556 wall h / 7.546385 core-h**. This is unallocated model margin, not a
validated restart budget. A single lost four-group shard is at most 32 known / 20
test-only / 12 matched observations. At a uniform 6.25 s/observation those are
200/125/75 s; retaining four CID samples at 8 s raises the test-only shard to
132 s (16 ×6.25 +4 ×8), before startup, revalidation, quarantine or storage costs.
Existing timing
parameters add 30 s startup and 0.01 s per committed observation for resume checking;
the latter is a planning allowance, not a measured checksum-scan rate.

The first-shard gate allows up to 5 ×1.25 = **6.25 s/observation**. Uniformly this
projects 37.065972 h; retaining CID at 8 s gives **37.309028 h / 42.748741 core-h**,
already beyond proposed 36/42. Therefore a first-shard pass alone cannot establish
budget feasibility. Remaining wall/core projection, cumulative attempts and strict
stops require production integration and measurement. No ceiling is raised here.
These extrapolations illustrate budget sensitivity; they do not assert that every
later stage's first shard would pass under the CID-corrected example.
Backup, restore and full checksum pass durations are unmeasured and not priced
into the per-observation band; their inclusion in the approved run scope/budget
must be explicit.

## Backup and recovery qualification

**Verdict: NOT QUALIFIED — BLOCKED — EXTERNAL DEPENDENCY.** No working or backup
device was designated or measured. The following table separates software evidence
from missing operational evidence.

| Control | Existing evidence | Actual operational state |
|---|---|---|
| Persistent independent physical backing | E14 compares filesystem device and declared physical IDs/evidence digest | NOT MEASURED; operator backing-device/failure-domain evidence absent |
| Different devices, disjoint paths | Strict record checks; CPU/storage-only no-follow observer available | NOT MEASURED; no root/mount/inode/device facts |
| Refuse volatile storage | E14 durable allowlist: ext4, xfs, btrfs, zfs; tmpfs/overlay/unknown refused | Contract exists; no target filesystem qualified; other filesystem needs review |
| Capacity and current free space | Proposed and fresh observed records, explicit byte floors and age <=14 days | NOT MEASURED; 9/ 12 GB are proposals only |
| SHA-256 external manifest and identity | E14 synthetic restore verifier binds bytes plus request/source/config/environment | Synthetic reference only; no production manifest/copy/restore |
| Read-only completed artifacts | Synthetic no-clobber publication and 0444 file mode | Production ACL/immutability integration missing; owner/root can change mode |
| External incident journal | Existing capped supervisor has a hash-chained fsynced journal | Append-only independently stored production journal/location/retention absent |
| Quarantine | Synthetic evidence-preserving logical quarantine with root/entry rechecks | Production policy/access controls/integration absent; no silent repair/deletion permitted |
| Durable descriptor-last commit | File/directory fsync demonstrated on capped labelled bytes | Physical generator fsync integration missing; actual power-loss behavior untested |
| Restore / disaster recovery | Procedure in E14 backup/recovery document | NOT RUN; synthetic tests do not qualify disaster recovery |

Pure record consistency does not authenticate measurements. The live observer
rejects symlink/path substitution when used; a caller's invented JSON cannot prove
that collection occurred. Different `st_dev` values do not prove separate disks,
controllers, power or remote persistence. The eventual admission path must use
trusted fresh observations and independently retained operator evidence.

No production copy, backup transfer, restore or durability fault experiment was
performed by E15. The smallest external step is researcher designation of the
generation host and independent persistent backup, followed by read-only evidence
collection. Production execution/durability/backup/journal integration remains a
separate reviewed engineering milestone before any DR-04 launch decision.

See [host qualification](B2_E15_HOST_QUALIFICATION.md),
[DR-04 dossier](../plan/B2_E15_DR04_DECISION_DOSSIER.md),
[release sequence](../plan/B2_E15_RELEASE_SEQUENCE.md), E11-B reconciliation and
the unchanged E14 release/backup contracts.

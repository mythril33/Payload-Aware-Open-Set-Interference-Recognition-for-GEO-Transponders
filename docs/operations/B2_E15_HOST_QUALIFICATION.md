# B2 E15 — generation-host qualification

Version 1, 2026-10-25. Reviewed repository baseline:
`9e176ad20aa1f355adac06e5a22c77b38a616099` (PR #38 merged).
**BLOCKED — EXTERNAL DEPENDENCY: no explicitly designated generation host.**
DR-04 remains NO-GO; this document authorizes nothing.

## Evidence and qualification verdict

The current E15 instruction supplies no hostname, asset identifier, access target,
working volume or persistent backup designation. The committed gate and E5
memorandum contain no DR-04 approval. E13 readiness U-2/U-3 and E14 release
checklist L-06/L-07 explicitly leave host and backup designation open. Repository
examples such as synthetic host/storage IDs are fixtures, not researcher choices.

No target-host inventory was collected in E15. The Codex sandbox and GitHub CI
runner are not designated production hosts; their test environments, historical
inventories, available disk and test RSS must not fill this qualification form.
No CPU/GPU benchmark, GPU discovery, waveform, observation or backup transfer was
performed for host qualification.

| Required evidence | Current value | State / condition before qualification |
|---|---|---|
| Researcher host designation and record | `null` | NOT MEASURED / BLOCKED; name intended generation host explicitly |
| Hostname and stable host/asset identity | `null` | NOT MEASURED / BLOCKED; match designation and operator inventory |
| OS/kernel and architecture | `null` | NOT MEASURED / BLOCKED; record actual host facts |
| Physical/logical CPUs, affinity and effective CPU quota | `null` | NOT MEASURED / BLOCKED; assess usable capacity against proposed >=4 vCPU |
| Total/available RAM and memory/cgroup limits | `null` | NOT MEASURED / BLOCKED; effective host RAM against proposed >=8 GiB, not physical total alone |
| Exact Python/NumPy/SciPy versions | `null` | NOT MEASURED / BLOCKED; exact pins, not ranges or local-test versions |
| OMP/OPENBLAS/MKL thread settings and PYTHONHASHSEED | `null` | NOT MEASURED / BLOCKED; capture four named variables only, no environment/credential dump |
| Working root, filesystem type and mount relationship | `null` | NOT MEASURED / BLOCKED; existing, non-aliased, no-follow path |
| Working capacity/free space, filesystem device and physical backing identity | `null` | NOT MEASURED / BLOCKED; proposed startup free >=33.880 GiB plus any larger approved reserve |
| Persistent backup root, type, mount/device/backing identity, capacity/free space | `null` | NOT MEASURED / BLOCKED; independently persistent and nonnested; 12 GB proposed, not approved |
| External incident-journal location and backing-device independence | `null` | NOT MEASURED / BLOCKED; retain evidence outside the working volume |
| Operator evidence of physical independence/persistence | `null` | NOT MEASURED / BLOCKED; different device numbers alone are insufficient |
| Measurement time, collector source hash and evidence record hash | `null` | NOT MEASURED / BLOCKED; traceable fresh snapshot from the designated host |

Qualification verdict: **NOT QUALIFIED**. The requirements above are an evidence
request template, not fabricated measurements or approval fields.

## Blank measurement template

This strict-JSON example is deliberately incomplete and is **not** an executable
host record or an input accepted by the E13/E14 validators. Every measurement is
`null`; the review date above is not a host collection timestamp.

```json
{
  "schema": "B2-E15-host-qualification-template/1",
  "status": "BLOCKED_NO_DESIGNATED_HOST",
  "designation_record": null,
  "host_identity": null,
  "hostname": null,
  "operating_system": null,
  "physical_cpus": null,
  "logical_cpus": null,
  "effective_cpu_limits": null,
  "memory_limits_bytes": null,
  "total_ram_bytes": null,
  "available_ram_bytes": null,
  "python": null,
  "numpy": null,
  "scipy": null,
  "thread_environment": null,
  "working_storage": null,
  "backup_storage": null,
  "incident_journal_storage": null,
  "physical_independence_evidence": null,
  "measured_at": null,
  "collector_source_sha256": null,
  "measurement_record_sha256": null,
  "production_authorized": false,
  "benchmark_complete": false
}
```

## Future read-only collection boundary

After explicit designation and access, collect only CPU/OS/memory, exact numerical
library versions, the four allowed environment variables, and filesystem/mount
facts. `scripts/b2_e14_storage.py:observe_directory` can observe an existing
directory without a subprocess or GPU query; its physical-storage ID, evidence
digest and timestamp are caller attestations, not independently authenticated
hardware facts. Pair the proposed and fresh observed records through
`validate_backup_devices`, retaining the operator evidence separately.

The older `b2_host_inventory.collect` includes GPU discovery even for a generation
profile; do not invoke it merely to populate this CPU-only form without a reviewed
CPU-only collection path. No generation, write-speed test, allocation benchmark
or GPU probe is authorized by designation or by read-only inventory permission.
An inventory cannot select or approve ceilings.

E13 host snapshots have a maximum age of 14 days; E14 device comparison requires
an explicit age limit of at most 14 days. A production release must choose a fresh
measurement policy, remeasure immediately at admission/stage boundaries and stop
on changed identity, inadequate resources, stale evidence or clock ambiguity.
Current software does not authenticate operator JSON or prove physical failure
domain independence. This remains an external operational dependency.

See [resource and backup assessment](B2_E15_RESOURCE_AND_BACKUP_ASSESSMENT.md),
[DR-04 dossier](../plan/B2_E15_DR04_DECISION_DOSSIER.md) and
[release sequence](../plan/B2_E15_RELEASE_SEQUENCE.md).

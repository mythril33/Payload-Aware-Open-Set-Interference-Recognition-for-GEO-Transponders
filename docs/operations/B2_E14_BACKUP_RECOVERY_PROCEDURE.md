# B2 E14 — backup and recovery contract

Version 1, 2026-10-25. **Procedure for a future separately authorized release;
not an instruction to transfer, generate or open production observations now.**
DR-04 remains NO-GO; all compute gates remain closed.

## What E14 actually implements

`scripts/b2_e14_storage.py` supplies strict storage-record comparison, a read-only
CPU/storage-only directory observer, and an explicitly synthetic reference writer,
verifier, logical quarantine and restore verifier. The writer accepts only labelled
bytes of at most 64 KiB, group IDs 0/1, and fixed synthetic filenames incompatible
with real B2 artifacts. It has no generator callback, production CLI or backup
copier. It is **not wired into physical generators**.

The reference writer fsyncs payload and metadata before publishing the descriptor,
syncs the directory, refuses overwrite, and preserves failed-write evidence.
Synthetic restore verification compares checksums, the external manifest and exact
request/source/config/environment identity. It does not perform a real backup or
prove power-loss recovery on a production filesystem. Existing physical generators
still need separately reviewed fsync/directory-sync and immutable-publication
integration; their checksum and descriptor-last logic alone is not a durability
guarantee. A total device failure can also prevent persistence of a failure note.

## Storage admission evidence

The exact `B2-E14-storage-device/1` record carries host, normalized root,
measurement time, filesystem device/type, declared physical storage ID, operator
identity-evidence digest, capacity and available bytes. Both proposed and fresh
observed records are required. Admission must reject:

- Missing, stale, future, mistyped or unexpected fields; a freshness ceiling above
  14 days; missing positive byte floors; insufficient capacity or current free space.
- Symlink components, traversal, aliasing, substituted roots and nested working/backup roots.
- Equal filesystem devices, equal physical IDs or foreign-host measurements.
- Volatile/pseudo filesystems and filesystems outside the module's reviewed
  durable allowlist. Overlay and tmpfs are not independent persistent backups.
- A mismatch between the approved device identity and the current observation.

Software can measure a filesystem device number, type, directory identity and free
space at an instant. It cannot prove that two partitions, virtual disks or remote
mounts have independent physical failure domains, power, controllers, snapshots or
persistence. The operator must identify the backing devices and retain that evidence
outside the working volume. Physical IDs and their hashes remain attestations;
checksums and unsigned JSON do not authenticate an operator or approval.

## Future backup procedure (not executed in E14)

1. Stop generation at a verified committed-shard boundary. Retain the external
   append-only journal, clean source/config/environment lock and exact run identity.
   Do not treat a temporary file, descriptor without matching payload/metadata, or
   a completion marker alone as a valid shard.
2. Verify the complete inventory, stage/role/group/shard identities, request
   fingerprints and every descriptor/payload/metadata checksum with reviewed
   production tooling. Verify no duplicate path or inode, symlink substitution,
   path traversal, orphan temporary, partial shard or unexpected file exists.
   This byte-integrity audit requires its own future authorization/tooling; the
   E14 K17d metadata-only verifier deliberately does not open NPZ payloads.
3. On a newly measured, approved persistent independent device, copy to a fresh
   nonnested staging root. Never overwrite the last good backup. Capacity must
   cover the actual artifact set and evidence, not merely the analytic estimate.
   No transfer command or production copier is supplied by E14.
4. Recompute all checksums at the destination against the externally retained
   manifest, not a manifest rebuilt from the destination alone. Verify source,
   config, environment, request and known-artifact bindings and exact relative paths.
   Durable publication of the backup and its manifest needs the same reviewed
   fsync/no-clobber discipline as the working artifact.
5. Record device identity, measured free space, manifest hash, run identity and
   verification outcome in the external journal. Only after verification may
   the finished working root and backup be made read-only under an operator
   access-control policy. File mode bits alone are not WORM storage.

## Future interruption and restore procedure (not executed in E14)

1. Fail closed on interruption, a checksum mismatch, an incomplete commit,
   identity drift, a changed device, expiry or resource/timing failure. Retain
   partial files and journal entries. Do not silently repair or delete evidence.
2. Inventory and hash corrupt/orphan files into a no-clobber quarantine record.
   E14's synthetic quarantine is logical and in-place; a future production
   quarantine needs reviewed access controls and journal integration.
3. Resume only when the exact original request, source, config, environment,
   host/storage/approval/lock identities and remaining budgets are revalidated.
   Changed source requires a newly reviewed run identity, not relabelling an old
   artifact or accepting its checkpoint under the new fingerprint.
4. Restore a verified backup into a fresh empty root, preserving the original.
   Recheck the external manifest and every shard checksum, exact role/group
   inventory and known→test-only→matched dependency chain before reuse. A
   syntactically correct descriptor or matching counts alone is insufficient.
5. Run the separately authorized metadata-only K17d verifier before any final
   evaluation: exact 500 headline IDs, co35/cross43/total78 drop predicates and
   the complementary465 IDs, with source/generator provenance. Its success
   cannot authorize observation reading or replace payload integrity checks.
   The actual production cross-verification remains **NOT RUN**.

No production data, backup or restore was created in this milestone. Synthetic
temporary files demonstrate the reference utility's contract only. Target host,
backup device, ceilings, DR-04 authorization, production integration, release
review and exact-head release evidence remain required. See the
[release checklist](B2_E14_RELEASE_GATE_CHECKLIST.md) and
[verification report](../results/B2_E14_VERIFICATION.md).

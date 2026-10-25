"""E16 external durable-admission barrier for generator shards. Reads and syncs; it never generates.

The accepted generators (``src/geosim``, whose package digest is part of the accepted K17d identity) write a
shard as part -> meta -> descriptor with ``write_text``/``replace`` and *no* fsync. E16 does not edit them: any edit
would change the accepted generator identity (see ``source_identity_impact``). Instead a shard is *admitted* by this
external barrier only after

  1. its descriptor, payload and metadata hash to exactly what the descriptor and the sealed plan say,
  2. every file and every directory on the path has been fsynced, and
  3. an identical re-verification (after evicting the cached pages where Linux allows it) finds no change.

Nothing downstream (stage completion, backup, the next stage) may count a shard that was not admitted. A power
loss before admission leaves a shard whose hashes either still match (nothing lost) or do not (``CORRUPT``/``PARTIAL``,
quarantined, never repaired, never silently regenerated). What this cannot do: prove media persistence, authenticate
who wrote a file, or turn mode bits into WORM. It authorizes nothing and executes nothing.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import b2_e14_storage as S

SCHEMA_ADMISSION = "B2-E16-shard-admission/1"
SCHEMA_CLASSIFICATION = "B2-E16-shard-directory-classification/1"
SCHEMA_MANIFEST = "B2-E16-backup-manifest/1"
SCHEMA_RESTORE = "B2-E16-restore-reverification/1"
SCHEMA_QUARANTINE = "B2-E16-quarantine-note/1"
MAX_PAYLOAD_BYTES = 128 * 2 ** 20          # measured shards are ~13 MB (4 groups x 8 variants x 406 kB); anything larger is not a shard
MAX_METADATA_BYTES = 64 * 2 ** 20
MAX_DESCRIPTOR_BYTES = 64 * 1024
MAX_ENTRIES = 4096
BLOCK = 1 << 20
MAX_ORDINAL = 99999
DESCRIPTOR_KEYS = frozenset({"part", "meta", "role", "scenario_seeds", "n_samples", "request_fingerprint", "sha256"})
EXPECTED_KEYS = frozenset({"role", "scenario_seeds", "n_samples", "request_fingerprint"})
FINAL = re.compile(r"(part|meta|shard)-(\d{5})\.(npz|jsonl|json)\Z")
TEMPORARY = re.compile(r"(part)-(\d{5})\.tmp\.npz\Z|(meta)-(\d{5})\.jsonl\.tmp\Z|(shard)-(\d{5})\.json\.tmp\Z")
SUFFIX = {"part": "npz", "meta": "jsonl", "shard": "json"}
ROLE = re.compile(r"[a-z][a-z0-9_-]{0,31}\Z")
STATES = ("ABSENT", "COMMITTED", "PARTIAL", "CORRUPT", "TEMPORARY_ORPHAN", "UNPLANNED")
ACCEPTED_GEOSIM_PACKAGE_SHA256 = "01c4f2697a9ff80e5bd7e644bdbf27562cb33d303685ace6f362c868b607fc4b"
ACCEPTED_GEOSIM_FILE_COUNT = 28
NO_AUTHORITY = {"authorizes_nothing": True, "execution_permitted": False, "dr_qualified": False}


class DurabilityRefused(S.StorageRefused):
    """Evidence is missing, inconsistent or unsafe: stop, preserve every file, repair nothing."""


# ---- low-level, no-follow, bounded access -----------------------------------------------------------------------

def _chain(raw):
    """Open every component of an absolute path without following symlinks; returns the fds root-first."""
    try:
        path = S._absolute(raw)
    except S.StorageRefused as error:
        raise DurabilityRefused(str(error)) from error
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    fds = [os.open("/", flags)]
    try:
        for component in path.parts[1:]:
            fds.append(os.open(component, flags, dir_fd=fds[-1]))
    except BaseException:
        for fd in fds:
            os.close(fd)
        raise
    return fds


def _close(fds):
    for fd in fds:
        try:
            os.close(fd)
        except OSError:
            pass


def _key(value):
    return (value.st_dev, value.st_ino, value.st_nlink, value.st_size, value.st_mtime_ns, value.st_ctime_ns)


def _read_regular(dir_fd, name, cap, *, keep=False):
    """Stream a regular, singly linked file once; returns (sha256, size, snapshot[, bytes]) and checks it stayed put."""
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=dir_fd)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise DurabilityRefused("only regular, non-aliased files are accepted")
        if before.st_size > cap:
            raise DurabilityRefused("file exceeds the byte bound for its kind")
        digest, total, chunks = hashlib.sha256(), 0, []
        while True:
            block = os.read(fd, BLOCK)
            if not block:
                break
            total += len(block)
            if total > cap:
                raise DurabilityRefused("file grew beyond its byte bound while read")
            digest.update(block)
            if keep:
                chunks.append(block)
        after = os.fstat(fd)
        linked = os.stat(name, dir_fd=dir_fd, follow_symlinks=False)
        if (total != before.st_size or _key(before) != _key(after)
                or (linked.st_dev, linked.st_ino, linked.st_nlink) != (after.st_dev, after.st_ino, after.st_nlink)):
            raise DurabilityRefused("file changed or was substituted during verification")
        result = (digest.hexdigest(), total, _key(after))
        return (*result, b"".join(chunks)) if keep else result
    finally:
        os.close(fd)


def shard_names(ordinal):
    if type(ordinal) is not int or not 0 <= ordinal <= MAX_ORDINAL:
        raise DurabilityRefused("shard ordinal must be an integer in 0..99999")
    return (f"part-{ordinal:05d}.npz", f"meta-{ordinal:05d}.jsonl", f"shard-{ordinal:05d}.json")


def temporary_names(ordinal):
    shard_names(ordinal)
    return (f"part-{ordinal:05d}.tmp.npz", f"meta-{ordinal:05d}.jsonl.tmp", f"shard-{ordinal:05d}.json.tmp")


def _expected(value):
    if not isinstance(value, dict) or set(value) != EXPECTED_KEYS:
        raise DurabilityRefused("expected shard identity must hold exactly role, scenario_seeds, n_samples, request_fingerprint")
    seeds = value["scenario_seeds"]
    if (not isinstance(value["role"], str) or not ROLE.fullmatch(value["role"])
            or not isinstance(seeds, list) or not seeds or any(type(s) is not int or s < 0 for s in seeds)
            or seeds != sorted(set(seeds)) or type(value["n_samples"]) is not int or value["n_samples"] < 1
            or not isinstance(value["request_fingerprint"], str) or not S.HEX.fullmatch(value["request_fingerprint"])):
        raise DurabilityRefused("malformed expected shard identity")
    return value


def _same(left, right):
    return S._canonical(left) == S._canonical(right)


# ---- shard verification -----------------------------------------------------------------------------------------

def _verify_open(dir_fd, ordinal, expected, *, check_order):
    part, meta, descriptor_name = shard_names(ordinal)
    expected = _expected(expected)
    present = set(os.listdir(dir_fd))
    if set(temporary_names(ordinal)) & present:
        raise DurabilityRefused("orphaned temporary file for this shard")
    if not {part, meta, descriptor_name} <= present:
        raise DurabilityRefused("incomplete shard: payload, metadata and descriptor must all exist")
    d_hash, d_size, d_key, raw = _read_regular(dir_fd, descriptor_name, MAX_DESCRIPTOR_BYTES, keep=True)
    try:
        descriptor = S._strict(raw)
    except S.StorageRefused as error:
        raise DurabilityRefused("descriptor is not strict JSON") from error
    if not isinstance(descriptor, dict) or set(descriptor) != DESCRIPTOR_KEYS:
        raise DurabilityRefused("descriptor fields differ from the generator contract")
    sha = descriptor["sha256"]
    if (descriptor["part"] != part or descriptor["meta"] != meta or not isinstance(sha, dict) or set(sha) != {part, meta}
            or not all(isinstance(v, str) and S.HEX.fullmatch(v) for v in sha.values())):
        raise DurabilityRefused("descriptor names or checksum map do not belong to this shard")
    if (descriptor["role"] != expected["role"] or not _same(descriptor["scenario_seeds"], expected["scenario_seeds"])
            or type(descriptor["n_samples"]) is not int or descriptor["n_samples"] != expected["n_samples"]
            or descriptor["request_fingerprint"] != expected["request_fingerprint"]):
        raise DurabilityRefused("descriptor role, groups, sample count or request identity differ from the sealed plan")
    files = {descriptor_name: {"bytes": d_size, "sha256": d_hash}}
    keys = {descriptor_name: d_key}
    for name, cap in ((part, MAX_PAYLOAD_BYTES), (meta, MAX_METADATA_BYTES)):
        digest, size, key = _read_regular(dir_fd, name, cap)
        if size == 0 or digest != sha[name]:
            raise DurabilityRefused("payload or metadata does not match its descriptor checksum")
        files[name], keys[name] = {"bytes": size, "sha256": digest}, key
    if check_order and keys[descriptor_name][4] < max(keys[part][4], keys[meta][4]):
        # mtime ordering is a coarse tripwire for a descriptor older than the data it names; a copy that lost mtimes
        # (restore) must be checked with check_order=False, by hash only.
        raise DurabilityRefused("descriptor is older than the payload or metadata it names")
    if set(os.listdir(dir_fd)) != present or any(
            _key(os.stat(n, dir_fd=dir_fd, follow_symlinks=False)) != keys[n] for n in keys):
        raise DurabilityRefused("shard changed during verification")
    return {"role": expected["role"], "ordinal": ordinal, "n_samples": expected["n_samples"],
            "scenario_seeds": list(expected["scenario_seeds"]), "request_fingerprint": expected["request_fingerprint"],
            "files": files, "descriptor_sha256": d_hash}, keys


def verify_shard(directory, ordinal, expected, *, check_order=True):
    """Byte-level verification of one shard against the sealed plan. Raises DurabilityRefused; never repairs."""
    fds = _chain(directory)
    try:
        report, _ = _verify_open(fds[-1], ordinal, expected, check_order=check_order)
        return report
    finally:
        _close(fds)


def _sync_file(dir_fd, name, snapshot):
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=dir_fd)
    try:
        if _key(os.fstat(fd)) != snapshot:
            raise DurabilityRefused("file changed before it could be synchronized")
        os.fsync(fd)
        advise = getattr(os, "posix_fadvise", None)
        if advise is not None:
            try:
                advise(fd, 0, 0, os.POSIX_FADV_DONTNEED)        # best effort: make the re-read come from the device
            except OSError:
                pass
    finally:
        os.close(fd)


def admit_shard(directory, ordinal, expected):
    """Durable-admission barrier: verify, fsync files and every directory on the path, then verify identically again.

    Returns the admission record, the only thing downstream stages may rely on. ``media_verified`` is always False:
    a re-read after eviction is evidence, not a certificate of what the storage device holds.
    """
    fds = _chain(directory)
    try:
        before, keys = _verify_open(fds[-1], ordinal, expected, check_order=True)
        for name, snapshot in keys.items():
            _sync_file(fds[-1], name, snapshot)
        for fd in reversed(fds):                                 # shard directory first, then each ancestor
            os.fsync(fd)
        after, _ = _verify_open(fds[-1], ordinal, expected, check_order=True)
        if not _same(before, after):
            raise DurabilityRefused("shard differs after the durability barrier")
        status = os.fstat(fds[-1])
        return dict(before, schema=SCHEMA_ADMISSION, directory_identity={"st_dev": status.st_dev, "st_ino": status.st_ino},
                    barrier="fsync_files_then_directory_chain_then_reverify", media_verified=False,
                    limitation="fsync and a post-eviction re-read are evidence of persistence, not proof of device behaviour",
                    **NO_AUTHORITY)
    finally:
        _close(fds)


# ---- directory classification and quarantine --------------------------------------------------------------------

def classify_directory(directory, expected_by_ordinal, *, deep=True):
    """Classify every entry of one role directory against the plan. Read-only; resumable only when nothing is orphaned."""
    if not isinstance(expected_by_ordinal, dict) or not expected_by_ordinal or len(expected_by_ordinal) > MAX_ENTRIES:
        raise DurabilityRefused("a bounded, non-empty plan of shards is required")
    for ordinal, value in expected_by_ordinal.items():
        shard_names(ordinal)
        _expected(value)
    fds = _chain(directory)
    try:
        dir_fd = fds[-1]
        names = sorted(os.listdir(dir_fd))
        if len(names) > 4 * MAX_ENTRIES:
            raise DurabilityRefused("directory holds more entries than any plan can")
        unexpected, temporary, finals = [], {}, {}
        for name in names:
            status = os.stat(name, dir_fd=dir_fd, follow_symlinks=False)
            match_final, match_temp = FINAL.fullmatch(name), TEMPORARY.fullmatch(name)
            if not stat.S_ISREG(status.st_mode) or not (match_final or match_temp):
                unexpected.append(name)
            elif match_temp:
                kind, number = next((a, b) for a, b in zip(match_temp.groups()[::2], match_temp.groups()[1::2]) if a)
                temporary.setdefault(int(number), []).append(name)
            elif SUFFIX[match_final.group(1)] != match_final.group(3):
                unexpected.append(name)
            else:
                finals.setdefault(int(match_final.group(2)), []).append(name)
        shards = {}
        for ordinal in sorted(set(finals) | set(temporary) | set(expected_by_ordinal)):
            entry = {"files": sorted(finals.get(ordinal, []) + temporary.get(ordinal, [])), "reason": None}
            if ordinal not in expected_by_ordinal:
                entry["state"] = "UNPLANNED"
            elif not entry["files"]:
                entry["state"] = "ABSENT"
            elif ordinal in temporary:
                entry["state"] = "TEMPORARY_ORPHAN"
            elif len(finals.get(ordinal, [])) < 3:
                entry["state"] = "PARTIAL"
            elif not deep:
                entry["state"] = "COMMITTED"
                entry["reason"] = "descriptor not re-hashed (deep=False); not admissible"
            else:
                try:
                    _verify_open(dir_fd, ordinal, expected_by_ordinal[ordinal], check_order=True)
                    entry["state"] = "COMMITTED"
                except (DurabilityRefused, OSError) as error:
                    entry["state"], entry["reason"] = "CORRUPT", type(error).__name__ + ": " + str(error)[:160]
            shards[ordinal] = entry
        states = [value["state"] for value in shards.values()]
        if not names:
            resume = "NOT_STARTED"
        elif unexpected or any(s in ("PARTIAL", "CORRUPT", "TEMPORARY_ORPHAN", "UNPLANNED") for s in states):
            resume = "NEEDS_QUARANTINE"
        elif all(s == "COMMITTED" for s in states):
            resume = "COMPLETE"
        else:
            resume = "RESUMABLE"
        identity = os.fstat(dir_fd)
        return {"schema": SCHEMA_CLASSIFICATION, "resume_state": resume, "deep": bool(deep),
                "counts": {name: states.count(name) for name in STATES}, "planned": len(expected_by_ordinal),
                "unexpected_entries": unexpected,
                "shards": {str(k): v for k, v in shards.items()},
                "quarantine_required": sorted(str(k) for k, v in shards.items() if v["state"] in ("PARTIAL", "CORRUPT", "TEMPORARY_ORPHAN", "UNPLANNED")),
                "directory_identity": {"st_dev": identity.st_dev, "st_ino": identity.st_ino},
                "cleanup_may_delete_evidence": False, **NO_AUTHORITY}
    finally:
        _close(fds)


def directory_identity(path):
    """(st_dev, st_ino) of a directory reached without following any symlink; aliases share an identity."""
    fds = _chain(path)
    try:
        status = os.fstat(fds[-1])
        return {"path": str(S._absolute(path)), "st_dev": status.st_dev, "st_ino": status.st_ino}
    finally:
        _close(fds)


def write_quarantine_note(evidence_directory, directory, classification, *, reason, recorded_at):
    """Publish a no-clobber evidence note in a *separate* directory. Moves, deletes and repairs nothing."""
    if not isinstance(classification, dict) or classification.get("schema") != SCHEMA_CLASSIFICATION:
        raise DurabilityRefused("a classification report is required")
    if not isinstance(reason, str) or not reason or len(reason) > 200:
        raise DurabilityRefused("a short reason is required")
    shard_path, note_path = S._absolute(directory), S._absolute(evidence_directory)
    if note_path == shard_path or shard_path in note_path.parents or note_path in shard_path.parents:
        raise DurabilityRefused("quarantine evidence must live outside the data directory tree")
    fds = _chain(directory)
    try:
        present = set(os.listdir(fds[-1]))                    # a directory entry never contains a separator
        try:
            named = [(name, False) for ordinal in classification["quarantine_required"] for name in classification["shards"][ordinal]["files"]]
            named += [(name, True) for name in classification["unexpected_entries"]]
        except (KeyError, TypeError) as error:
            raise DurabilityRefused("classification report is malformed") from error
        if any(not isinstance(name, str) or name not in present for name, _ in named):
            raise DurabilityRefused("classification names a file that is not an entry of this directory (stale or forged report)")
        entries = {}
        for name, unexpected in named:
            if unexpected:
                entries[name] = {"bytes": None, "sha256": None, "unexpected": True}
                continue
            try:
                digest, size, _ = _read_regular(fds[-1], name, MAX_PAYLOAD_BYTES)
                entries[name] = {"bytes": size, "sha256": digest}
            except (DurabilityRefused, OSError) as error:
                entries[name] = {"bytes": None, "sha256": None, "unreadable": type(error).__name__}
    finally:
        _close(fds)
    note = {"schema": SCHEMA_QUARANTINE, "reason": reason, "recorded_at": recorded_at,
            "resume_state": classification["resume_state"], "evidence": entries,
            "evidence_preserved_in_place": True, "files_moved_or_deleted": 0, **NO_AUTHORITY}
    raw = S._canonical(note)
    name = "quarantine-" + hashlib.sha256(raw).hexdigest()[:32] + ".json"
    evidence_fds = _chain(evidence_directory)
    try:
        if name in os.listdir(evidence_fds[-1]):
            # Same name means same content hash prefix; still compare, never overwrite and leave no temporary behind.
            digest, _, _ = _read_regular(evidence_fds[-1], name, MAX_DESCRIPTOR_BYTES * 16)
            if digest != hashlib.sha256(raw).hexdigest():
                raise DurabilityRefused("an unrelated evidence note already exists under that name")
        else:
            S._publish(evidence_fds[-1], name, raw)
        return dict(note, note_name=name)
    finally:
        _close(evidence_fds)


# ---- backup manifests, restore re-verification, immutability ---------------------------------------------------

def build_manifest(directory, expected_by_ordinal):
    """Checksummed manifest of admitted shards. Every named shard must verify first; nothing is copied."""
    entries, total = [], 0
    role = None
    for ordinal in sorted(expected_by_ordinal):
        report = verify_shard(directory, ordinal, expected_by_ordinal[ordinal])
        role = report["role"] if role is None else role
        if report["role"] != role:
            raise DurabilityRefused("one manifest covers one role directory")
        for name in sorted(report["files"]):
            info = report["files"][name]
            entries.append({"name": name, "bytes": info["bytes"], "sha256": info["sha256"]})
            total += info["bytes"]
    if not entries:
        raise DurabilityRefused("empty manifest")
    manifest = {"schema": SCHEMA_MANIFEST, "role": role, "shards": sorted(expected_by_ordinal), "entries": entries, "total_bytes": total}
    manifest["manifest_sha256"] = hashlib.sha256(S._canonical(manifest)).hexdigest()
    return manifest


def _manifest_check(manifest):
    keys = {"schema", "role", "shards", "entries", "total_bytes", "manifest_sha256"}
    if not isinstance(manifest, dict) or set(manifest) != keys or manifest["schema"] != SCHEMA_MANIFEST:
        raise DurabilityRefused("not an E16 backup manifest")
    body = {k: v for k, v in manifest.items() if k != "manifest_sha256"}
    if manifest["manifest_sha256"] != hashlib.sha256(S._canonical(body)).hexdigest():
        raise DurabilityRefused("manifest checksum differs from its content")
    entries = manifest["entries"]
    if (not isinstance(entries, list) or not entries or len(entries) > 3 * MAX_ENTRIES
            or any(not isinstance(e, dict) or set(e) != {"name", "bytes", "sha256"} or not isinstance(e["name"], str)
                   or not FINAL.fullmatch(e["name"]) or type(e["bytes"]) is not int or e["bytes"] < 0
                   or not isinstance(e["sha256"], str) or not S.HEX.fullmatch(e["sha256"]) for e in entries)
            or len({e["name"] for e in entries}) != len(entries)
            or sum(e["bytes"] for e in entries) != manifest["total_bytes"]):
        raise DurabilityRefused("malformed manifest entries")
    return manifest


def verify_restore(directory, manifest, expected_by_ordinal=None):
    """Re-verify an operator-made copy against the manifest retained elsewhere. Reads only; copies and repairs nothing.

    Success means byte consistency of that copy with the manifest. It is not a disaster-recovery qualification
    (no independent device, restore drill or retention is demonstrated by it).
    """
    _manifest_check(manifest)
    fds = _chain(directory)
    try:
        listed = sorted(os.listdir(fds[-1]))
        wanted = sorted(e["name"] for e in manifest["entries"])
        if listed != wanted:
            raise DurabilityRefused("restored directory holds missing or extra files compared with the manifest")
        for entry in manifest["entries"]:
            digest, size, _ = _read_regular(fds[-1], entry["name"], MAX_PAYLOAD_BYTES)
            if size != entry["bytes"] or digest != entry["sha256"]:
                raise DurabilityRefused("restored file differs from the manifest")
        if expected_by_ordinal is not None:
            for ordinal in manifest["shards"]:
                _verify_open(fds[-1], ordinal, expected_by_ordinal[ordinal], check_order=False)
        return {"schema": SCHEMA_RESTORE, "ok": True, "manifest_sha256": manifest["manifest_sha256"],
                "files": len(wanted), "bytes": manifest["total_bytes"], "restore_reverified": True,
                "disaster_recovery_qualified": False, "limitation": "a byte-consistent copy is not a qualified backup", **NO_AUTHORITY}
    finally:
        _close(fds)


def immutability_findings(directory, ordinals):
    """Findings (empty = none) about write bits, aliases and writable directories. Mode bits are not WORM."""
    findings = []
    fds = _chain(directory)
    try:
        status = os.fstat(fds[-1])
        if status.st_mode & 0o022:
            findings.append("shard directory is group- or world-writable")
        for ordinal in ordinals:
            for name in shard_names(ordinal):
                try:
                    value = os.stat(name, dir_fd=fds[-1], follow_symlinks=False)
                except FileNotFoundError:
                    findings.append(f"{name} is missing")
                    continue
                if not stat.S_ISREG(value.st_mode) or value.st_nlink != 1:
                    findings.append(f"{name} is not a singly linked regular file")
                if value.st_mode & 0o222:
                    findings.append(f"{name} still has a write permission bit")
        return findings
    finally:
        _close(fds)


def immutable_publication_report(directory, ordinals):
    findings = immutability_findings(directory, ordinals)
    return {"ok": not findings, "findings": findings, "worm_proven": False,
            "limitation": "owner can chmod again and a root process can change anything; read-only bits are accident protection only",
            **NO_AUTHORITY}


# ---- generator identity ----------------------------------------------------------------------------------------

def geosim_package_digest(source_root):
    """The accepted K17d formula (scripts/b2_e10_k17d_identity.py::package_digest) on an arbitrary checkout."""
    root = Path(source_root)
    files = sorted((root / "src" / "geosim").glob("*.py"))
    digest = hashlib.sha256()
    for path in files:
        digest.update(path.relative_to(root).as_posix().encode("utf-8") + b"\0"
                      + hashlib.sha256(path.read_bytes()).hexdigest().encode("ascii") + b"\n")
    return digest.hexdigest(), len(files)


def source_identity_impact(source_root, *, accepted_sha256=ACCEPTED_GEOSIM_PACKAGE_SHA256, accepted_files=ACCEPTED_GEOSIM_FILE_COUNT):
    """Does this tree still carry the accepted generator? A change is never absorbed silently."""
    observed, count = geosim_package_digest(source_root)
    unchanged = observed == accepted_sha256 and count == accepted_files
    result = {"unchanged": unchanged, "accepted_sha256": accepted_sha256, "observed_sha256": observed,
              "accepted_files": accepted_files, "observed_files": count, "production_blocked": not unchanged,
              "historical_identity_records_preserved": True, **NO_AUTHORITY}
    if not unchanged:
        result["required_before_any_use"] = [
            "keep the accepted K17d identity record, audit and every earlier checkpoint unchanged",
            "metadata-only re-derivation of the K17d identity with no observation read and no waveform call",
            "independent review of the changed modules",
            "explicit researcher acceptance of the new identity; an unreviewed digest is not an acceptance",
            "re-hash of the generator provenance fingerprint and every sealed plan/specification built on it"]
    return result

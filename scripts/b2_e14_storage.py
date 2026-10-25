"""E14 sealed storage reference controls; no production generator integration.

The only writer accepts explicitly labelled synthetic bytes, at most two fixture
groups (0 and 1), and fixed names incompatible with B2 artifacts. It is not a
production shard committer, backup copier or executable entry point. Existing
generators remain unchanged; their durability integration needs a separate review.
Checksums prove byte identity, not authenticity or physical device independence.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from datetime import datetime, timezone


SCHEMA = "B2-E14-synthetic-storage/1"
DEVICE_SCHEMA = "B2-E14-storage-device/1"
FIXTURE_MAX_GROUPS = 2
MAX_BYTES = 65536
PREFIX = b"E14-SYNTHETIC-FIXTURE\n"
PAYLOAD, METADATA, DESCRIPTOR = "synthetic-payload.bin", "synthetic-metadata.json", "synthetic-commit.json"
FILES = (PAYLOAD, METADATA, DESCRIPTOR)
IDENTITY_KEYS = frozenset({"request_sha256", "source_sha256", "config_sha256", "environment_sha256"})
DEVICE_KEYS = frozenset({"schema", "host_id", "root", "measured_at", "filesystem_device", "filesystem_type",
                         "physical_storage_id", "physical_identity_evidence_sha256", "capacity_bytes", "free_bytes"})
REFUSED_FS = frozenset({"tmpfs", "ramfs", "devtmpfs", "proc", "sysfs", "cgroup", "cgroup2", "devpts", "mqueue",
                        "securityfs", "debugfs", "tracefs", "fusectl", "pstore", "configfs", "overlay", "squashfs", "autofs"})
# Deliberately narrow; another filesystem needs an explicit engineering review,
# not merely an unfamiliar type omitted from a blacklist. This list is no claim
# about a drive's persistence, truthful reporting or power-failure guarantees.
DURABLE_FILESYSTEMS = frozenset({"ext4", "xfs", "btrfs", "zfs"})
HEX = re.compile(r"[0-9a-f]{64}\Z")


class StorageRefused(ValueError):
    """Invalid or incomplete storage evidence: stop, preserve files, do not repair."""


def _canonical(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    except (TypeError, ValueError, OverflowError, RecursionError) as error:
        raise StorageRefused("not strict JSON") from error


def _strict(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise StorageRefused("duplicate JSON key")
            result[key] = value
        return result
    try:
        value = json.loads(raw, object_pairs_hook=pairs, parse_constant=lambda _: (_ for _ in ()).throw(StorageRefused("nonfinite JSON")))
        _canonical(value)
        return value
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as error:
        raise StorageRefused("invalid strict JSON") from error


def _hash(raw):
    return hashlib.sha256(raw).hexdigest()


def _text(value):
    return isinstance(value, str) and bool(value) and value.strip() == value and all(ord(c) >= 32 for c in value)


def _integer(value, *, minimum=0):
    return type(value) is int and minimum <= value <= 2**63 - 1


def _identity(value):
    if not isinstance(value, dict) or set(value) != IDENTITY_KEYS or not all(isinstance(v, str) and HEX.fullmatch(v) for v in value.values()):
        raise StorageRefused("exact request/source/config/environment SHA-256 identities required")
    return value


def _metadata(value):
    if not isinstance(value, dict) or set(value) != {"schema", "synthetic", "groups"}:
        raise StorageRefused("synthetic metadata shape")
    groups = value["groups"]
    if (value["schema"] != SCHEMA or value["synthetic"] is not True or not isinstance(groups, list)
            or not 1 <= len(groups) <= FIXTURE_MAX_GROUPS or any(type(g) is not int or g not in (0, 1) for g in groups)
            or groups != sorted(set(groups))):
        raise StorageRefused("explicit synthetic groups 0/1 only, at most two")
    return value


def _absolute(raw):
    if not isinstance(raw, (str, Path)):
        raise StorageRefused("root must be an absolute path")
    text = str(raw)
    if (not text.startswith("/") or text == "/" or str(Path(text)) != text or "\\" in text
            or any(ord(c) < 32 or ord(c) == 127 for c in text) or ".." in Path(text).parts):
        raise StorageRefused("root must be normalized, absolute and traversal-free")
    return Path(text)


def _open_root(raw):
    """Anchor every component without following symlinks; no mkdir or path retry."""
    path = _absolute(raw)
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    fd = os.open("/", flags)
    try:
        for component in path.parts[1:]:
            child = os.open(component, flags, dir_fd=fd)
            os.close(fd)
            fd = child
        return fd
    except BaseException:
        os.close(fd)
        raise


def _read(fd, name):
    opened = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
    try:
        before = os.fstat(opened)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > MAX_BYTES:
            raise StorageRefused("only bounded, regular, non-aliased files are accepted")
        with os.fdopen(opened, "rb", closefd=False) as stream:
            raw = stream.read(MAX_BYTES + 1)
        after = os.fstat(opened)
        if (len(raw) != before.st_size or len(raw) > MAX_BYTES or before.st_size != after.st_size
                or before.st_mtime_ns != after.st_mtime_ns or before.st_ctime_ns != after.st_ctime_ns):
            raise StorageRefused("file changed during verification")
        linked = os.stat(name, dir_fd=fd, follow_symlinks=False)
        if (linked.st_dev, linked.st_ino, linked.st_nlink) != (after.st_dev, after.st_ino, 1):
            raise StorageRefused("file substituted during verification")
        return raw
    finally:
        os.close(opened)


def _root_unchanged(fd, root):
    again = _open_root(root)
    try:
        before, after = os.fstat(fd), os.fstat(again)
        if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
            raise StorageRefused("root substituted during operation")
    finally:
        os.close(again)


def _file_snapshot(fd, name):
    value = os.stat(name, dir_fd=fd, follow_symlinks=False)
    return (value.st_dev, value.st_ino, value.st_nlink, value.st_size, value.st_mtime_ns, value.st_ctime_ns)


def _publish(fd, name, raw):
    temporary = "." + name + ".tmp"
    out = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
    try:
        with os.fdopen(out, "wb", closefd=False) as stream:
            stream.write(raw)
            stream.flush()
            os.fchmod(out, 0o444)
            os.fsync(out)
        stable, linked = os.fstat(out), os.stat(temporary, dir_fd=fd, follow_symlinks=False)
        if (stable.st_dev, stable.st_ino, 1) != (linked.st_dev, linked.st_ino, linked.st_nlink):
            raise StorageRefused("temporary file substituted before publication")
        # link+unlink provides no-clobber publication; replace would overwrite.
        os.link(temporary, name, src_dir_fd=fd, dst_dir_fd=fd, follow_symlinks=False)
        published = os.stat(name, dir_fd=fd, follow_symlinks=False)
        if (published.st_dev, published.st_ino, published.st_nlink) != (stable.st_dev, stable.st_ino, 2):
            raise StorageRefused("file substituted during publication")
        os.unlink(temporary, dir_fd=fd)
        os.fsync(fd)
    finally:
        os.close(out)


def _failure_note(fd):
    """Best-effort visible failure evidence even when fsync itself is failing."""
    try:
        out = os.open("SYNTHETIC_FAILED.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o444, dir_fd=fd)
        try:
            os.write(out, b'{"schema":"B2-E14-synthetic-storage/1","synthetic":true,"failed":true}')
            os.fsync(out)
        finally:
            os.close(out)
        os.fsync(fd)
    except OSError:
        # An unavailable filesystem cannot promise to persist even the failure
        # note. Caller must retain the original exception and stop externally.
        pass


def commit_synthetic_fixture(root, payload, metadata, identity):
    """Commit one <=64-KiB labelled fixture; errors preserve partial evidence.

    Descriptor publication happens only after durable payload and metadata.
    A final directory-sync failure may leave a visible descriptor: a failure
    note makes subsequent verification refuse it, provided the device still
    accepts writes. Total device loss requires an external journal/stop rule.
    The owner can chmod files again; this is no-clobber discipline, not a WORM ACL.
    """
    _identity(identity)
    _metadata(metadata)
    if type(payload) is not bytes or not payload.startswith(PREFIX) or not len(PREFIX) < len(payload) <= MAX_BYTES:
        raise StorageRefused("only capped explicitly labelled synthetic bytes accepted")
    meta = _canonical(metadata)
    descriptor = {"schema": SCHEMA, "synthetic": True, "identity": identity,
                  "files": {PAYLOAD: {"bytes": len(payload), "sha256": _hash(payload)},
                            METADATA: {"bytes": len(meta), "sha256": _hash(meta)}}}
    encoded = _canonical(descriptor)
    fd = _open_root(root)
    try:
        if os.listdir(fd):
            raise StorageRefused("fixture root must be empty; no overwrite or implicit resume")
        try:
            _publish(fd, PAYLOAD, payload)
            _publish(fd, METADATA, meta)
            _publish(fd, DESCRIPTOR, encoded)
            if _canonical(_verify(fd, identity)) != encoded:
                raise StorageRefused("committed descriptor differs from proposed synthetic fixture")
            _root_unchanged(fd, root)
        except BaseException:
            _failure_note(fd)
            raise
        return descriptor
    finally:
        os.close(fd)


def _verify(fd, identity):
    _identity(identity)
    if set(os.listdir(fd)) != set(FILES):
        raise StorageRefused("incomplete shard, unexpected file or orphaned temporary")
    snapshots = {name: _file_snapshot(fd, name) for name in FILES}
    descriptor_raw = _read(fd, DESCRIPTOR)
    descriptor = _strict(descriptor_raw)
    if (not isinstance(descriptor, dict) or set(descriptor) != {"schema", "synthetic", "identity", "files"}
            or descriptor["schema"] != SCHEMA or descriptor["synthetic"] is not True
            or _canonical(descriptor["identity"]) != _canonical(identity)
            or not isinstance(descriptor["files"], dict) or set(descriptor["files"]) != {PAYLOAD, METADATA}):
        raise StorageRefused("descriptor or request/source/config/environment identity mismatch")
    for name in (PAYLOAD, METADATA):
        raw = _read(fd, name)
        entry = descriptor["files"][name]
        if (not isinstance(entry, dict) or set(entry) != {"bytes", "sha256"} or type(entry["bytes"]) is not int
                or entry["bytes"] != len(raw) or entry["sha256"] != _hash(raw)):
            raise StorageRefused("corrupt payload or metadata checksum")
        if name == PAYLOAD and (not raw.startswith(PREFIX) or len(raw) <= len(PREFIX)):
            raise StorageRefused("not a synthetic payload")
        if name == METADATA:
            _metadata(_strict(raw))
    if (_read(fd, DESCRIPTOR) != descriptor_raw or set(os.listdir(fd)) != set(FILES)
            or any(_file_snapshot(fd, name) != snapshots[name] for name in FILES)):
        raise StorageRefused("payload, descriptor or directory changed during verification")
    return descriptor


def verify_synthetic_fixture(root, identity):
    """Read bounded synthetic files only; never opens a B2 observation archive."""
    fd = _open_root(root)
    try:
        result = _verify(fd, identity)
        _root_unchanged(fd, root)
        return result
    finally:
        os.close(fd)


def verify_synthetic_restore(root, manifest, identity):
    """Re-verify an operator-created synthetic copy against an external manifest.

    Does not copy, transfer, overwrite or repair a file. A successful result is
    checksum consistency only, never production backup completion or authority.
    """
    actual = verify_synthetic_fixture(root, identity)
    if _canonical(actual) != _canonical(manifest):
        raise StorageRefused("restored manifest differs from the externally retained original")
    return {"schema": SCHEMA, "ok": True, "restored_manifest_sha256": _hash(_canonical(actual)),
            "synthetic": True, "authorizes_nothing": True, "execution_permitted": False}


def quarantine_synthetic_fixture(root, identity):
    """Seal an invalid bounded fixture with a no-clobber evidence note in place.

    No rename/delete/repair of evidence. This is a logical quarantine, not an
    access-control or production-journal mechanism. It rejects nonfixture trees,
    aliases, subdirectories and oversized files before writing anything.
    """
    _identity(identity)
    fd = _open_root(root)
    try:
        try:
            _verify(fd, identity)
        except (StorageRefused, OSError, TypeError):
            pass
        else:
            raise StorageRefused("valid committed fixture must not be quarantined")
        names = sorted(os.listdir(fd))
        allowed = set(FILES) | {"." + name + ".tmp" for name in FILES} | {"SYNTHETIC_FAILED.json"}
        if not names or not set(names) <= allowed:
            raise StorageRefused("only recognized incomplete synthetic fixture files may be quarantined")
        snapshots = {name: _file_snapshot(fd, name) for name in names}
        entries = {}
        for name in names:
            raw = _read(fd, name)
            # Prevent writing an evidence note into arbitrary pre-existing data.
            if name in (PAYLOAD, "." + PAYLOAD + ".tmp") and not raw.startswith(PREFIX):
                raise StorageRefused("quarantine requires explicitly labelled synthetic payload")
            entries[name] = {"bytes": len(raw), "sha256": _hash(raw)}
        note = {"schema": SCHEMA, "synthetic": True, "quarantined": True, "reason": "INVALID_OR_INCOMPLETE",
                "expected_identity": identity, "files": entries, "authorizes_nothing": True}
        if sorted(os.listdir(fd)) != names or any(_file_snapshot(fd, name) != snapshots[name] for name in names):
            raise StorageRefused("evidence changed during quarantine snapshot")
        _root_unchanged(fd, root)
        _publish(fd, "SYNTHETIC_QUARANTINE.json", _canonical(note))
        if (set(os.listdir(fd)) != set(names) | {"SYNTHETIC_QUARANTINE.json"}
                or any(_file_snapshot(fd, name) != snapshots[name] for name in names)):
            raise StorageRefused("evidence changed during quarantine publication")
        _root_unchanged(fd, root)
        return note
    finally:
        os.close(fd)


def _instant(value):
    if not isinstance(value, str):
        raise StorageRefused("timestamp must include timezone")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise StorageRefused("invalid timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise StorageRefused("timestamp must include timezone")
    return parsed.astimezone(timezone.utc)


def _device(record, now, age):
    if not isinstance(record, dict) or set(record) != DEVICE_KEYS or record["schema"] != DEVICE_SCHEMA:
        raise StorageRefused("exact measured storage-device schema required")
    for field in ("host_id", "physical_storage_id", "filesystem_type"):
        if not _text(record[field]):
            raise StorageRefused("missing storage identity")
    root = _absolute(record["root"])
    if any(root == Path(p) or Path(p) in root.parents for p in ("/dev", "/proc", "/sys", "/run", "/tmp", "/var/tmp", "/var/run")):
        raise StorageRefused("volatile or system-managed storage root")
    if not isinstance(record["physical_identity_evidence_sha256"], str) or not HEX.fullmatch(record["physical_identity_evidence_sha256"]):
        raise StorageRefused("operator physical-identity evidence digest required")
    if not all(_integer(record[k]) for k in ("filesystem_device", "capacity_bytes", "free_bytes")):
        raise StorageRefused("integer device/capacity/free-space measurements required")
    if record["capacity_bytes"] <= 0 or record["free_bytes"] > record["capacity_bytes"]:
        raise StorageRefused("inconsistent capacity")
    if record["filesystem_type"].lower() not in DURABLE_FILESYSTEMS:
        raise StorageRefused("volatile, pseudo, unknown or unreviewed storage filesystem")
    if not 0 <= (now - _instant(record["measured_at"])).total_seconds() <= age:
        raise StorageRefused("missing, future or stale host measurement")


def validate_backup_devices(working, backup, *, observed_working=None, observed_backup=None, now,
                            max_age_seconds, working_floor_bytes, backup_floor_bytes):
    """Validate proposed and independently re-measured device records, not authority.

    A caller-supplied physical storage id/evidence hash is still an operator
    attestation. Different st_dev values alone cannot prove independent disks,
    shared controller/power failure domains, remote persistence or truthful JSON.
    """
    failures = []
    try:
        if not _integer(max_age_seconds, minimum=1) or max_age_seconds > 14 * 86400:
            raise StorageRefused("explicit freshness bound of at most 14 days required")
        if not _integer(working_floor_bytes, minimum=1) or not _integer(backup_floor_bytes, minimum=1):
            raise StorageRefused("explicit integer resource floors required")
        clock = _instant(now)
        for record in (working, backup, observed_working, observed_backup):
            _device(record, clock, max_age_seconds)
        paths = [_absolute(record["root"]) for record in (working, backup)]
        if paths[0] == paths[1] or paths[0] in paths[1].parents or paths[1] in paths[0].parents:
            raise StorageRefused("working and backup roots must be disjoint and nonnested")
        if (working["host_id"] != backup["host_id"] or working["filesystem_device"] == backup["filesystem_device"]
                or working["physical_storage_id"] == backup["physical_storage_id"]):
            raise StorageRefused("independently identified working and persistent backup devices required")
        same = DEVICE_KEYS - {"measured_at", "free_bytes"}
        for planned, observed, floor in ((working, observed_working, working_floor_bytes), (backup, observed_backup, backup_floor_bytes)):
            if any(planned[key] != observed[key] for key in same):
                raise StorageRefused("live measurement differs from approved device identity")
            if min(planned["capacity_bytes"], planned["free_bytes"], observed["capacity_bytes"], observed["free_bytes"]) < floor:
                raise StorageRefused("insufficient capacity or current free space")
    except (StorageRefused, TypeError, OverflowError, ValueError) as error:
        failures.append(str(error))
    return {"schema": DEVICE_SCHEMA, "ok": not failures, "failures": failures,
            "authorizes_nothing": True, "execution_permitted": False,
            "physical_independence_proven": False,
            "limitation": "physical identities and persistence still require operator verification; records are not authenticated"}


def observe_directory(root, *, host_id, physical_storage_id, physical_identity_evidence_sha256, measured_at):
    """Read-only local filesystem snapshot, no subprocess, GPU query or file write.

    Physical identity and timestamp are explicit caller attestations, not inferred
    from paths. This cannot designate a production host or authorize a backup.
    """
    path = _absolute(root)
    fd = _open_root(path)
    try:
        status, usage = os.fstat(fd), os.fstatvfs(fd)
        best = None
        # Linux mount metadata only: never a GPU or external process probe.
        for line in Path("/proc/self/mountinfo").read_text().splitlines():
            left, separator, right = line.partition(" - ")
            fields, tail = left.split(), right.split()
            if not separator or len(fields) < 5 or not tail:
                continue
            mount = Path(re.sub(r"\\([0-7]{3})", lambda m: chr(int(m.group(1), 8)), fields[4]))
            if (mount == path or mount in path.parents) and (best is None or len(str(mount)) > len(str(best[0]))):
                best = mount, tail[0]
        record = {"schema": DEVICE_SCHEMA, "host_id": host_id, "root": str(path), "measured_at": measured_at,
                  "filesystem_device": status.st_dev, "filesystem_type": best[1] if best else "",
                  "physical_storage_id": physical_storage_id, "physical_identity_evidence_sha256": physical_identity_evidence_sha256,
                  "capacity_bytes": usage.f_blocks * usage.f_frsize, "free_bytes": usage.f_bavail * usage.f_frsize}
        # Verify the pathname still resolves to the anchored directory.
        again = _open_root(path)
        try:
            other = os.fstat(again)
            if (status.st_dev, status.st_ino) != (other.st_dev, other.st_ino):
                raise StorageRefused("root substituted during measurement")
        finally:
            os.close(again)
        return record
    finally:
        os.close(fd)

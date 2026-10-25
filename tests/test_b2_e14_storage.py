"""E14 storage controls: fabricated metadata and <=64 KiB synthetic bytes only.

No real B2 archive, backup device, waveform, model, GPU or held-out sample is used.
The reference writer deliberately emits an incompatible synthetic-only format.
"""
import ast
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("e14_storage", ROOT / "scripts/b2_e14_storage.py")
S = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(S)
H = lambda value: hashlib.sha256(value.encode()).hexdigest()  # noqa: E731
IDENTITY = {key: H(key) for key in S.IDENTITY_KEYS}
META = {"schema": S.SCHEMA, "synthetic": True, "groups": [0, 1]}
DATA = S.PREFIX + b"fabricated bytes, no waveform"
NOW = "2026-10-25T12:00:00+00:00"


@pytest.fixture
def committed(tmp_path):
    manifest = S.commit_synthetic_fixture(tmp_path, DATA, META, IDENTITY)
    return tmp_path, manifest


def write(path, raw):
    if path.exists():
        path.chmod(0o600)
    path.write_bytes(raw)


def assert_refused(root, identity=IDENTITY):
    with pytest.raises((S.StorageRefused, OSError)):
        S.verify_synthetic_fixture(root, identity)


def test_commit_and_readonly_restore_verify_no_copy(committed):
    root, manifest = committed
    before = {p.name: p.read_bytes() for p in root.iterdir()}
    assert S.verify_synthetic_fixture(root, IDENTITY) == manifest
    report = S.verify_synthetic_restore(root, manifest, IDENTITY)
    assert report["ok"] is True
    assert report["execution_permitted"] is False
    assert report["authorizes_nothing"] is True
    assert {p.name: p.read_bytes() for p in root.iterdir()} == before
    assert all(p.stat().st_mode & 0o222 == 0 for p in root.iterdir())


def test_descriptor_never_precedes_payload_and_metadata_fsync(tmp_path, monkeypatch):
    events = []
    original_fsync, original_link = S.os.fsync, S.os.link
    def sync(fd):
        events.append(("fsync", os.readlink(f"/proc/self/fd/{fd}")))
        return original_fsync(fd)
    def link(src, dst, **kwargs):
        if dst == S.DESCRIPTOR:
            assert any(kind == "fsync" and name.endswith("." + S.PAYLOAD + ".tmp") for kind, name in events)
            assert any(kind == "fsync" and name.endswith("." + S.METADATA + ".tmp") for kind, name in events)
            assert sum(kind == "fsync" and name == str(tmp_path) for kind, name in events) >= 2
        events.append(("link", dst))
        return original_link(src, dst, **kwargs)
    monkeypatch.setattr(S.os, "fsync", sync)
    monkeypatch.setattr(S.os, "link", link)
    S.commit_synthetic_fixture(tmp_path, DATA, META, IDENTITY)
    assert [name for kind, name in events if kind == "link"] == list(S.FILES)
    assert events[-1] == ("fsync", str(tmp_path))


@pytest.mark.parametrize("fail_at", range(1, 7))
def test_each_file_or_directory_fsync_failure_is_not_a_committed_fixture(tmp_path, monkeypatch, fail_at):
    original = S.os.fsync
    calls = 0
    def fail(fd):
        nonlocal calls
        calls += 1
        if calls == fail_at:
            raise OSError("synthetic fsync failure")
        return original(fd)
    monkeypatch.setattr(S.os, "fsync", fail)
    with pytest.raises(OSError, match="synthetic fsync failure"):
        S.commit_synthetic_fixture(tmp_path, DATA, META, IDENTITY)
    assert_refused(tmp_path)
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    note = S.quarantine_synthetic_fixture(tmp_path, IDENTITY)
    assert note["quarantined"] is True
    assert all((tmp_path / name).read_bytes() == raw for name, raw in before.items())
    assert_refused(tmp_path)


def test_completely_failed_device_cannot_be_claimed_durable(tmp_path, monkeypatch):
    monkeypatch.setattr(S.os, "fsync", lambda _: (_ for _ in ()).throw(OSError("device unavailable")))
    with pytest.raises(OSError, match="device unavailable"):
        S.commit_synthetic_fixture(tmp_path, DATA, META, IDENTITY)
    assert not (tmp_path / S.DESCRIPTOR).exists()
    assert_refused(tmp_path)


@pytest.mark.parametrize("target", S.FILES)
def test_corrupt_bytes_fail_and_quarantine_preserves_evidence(committed, target):
    root, _ = committed
    original = (root / target).read_bytes()
    write(root / target, original + b"modified")
    assert_refused(root)
    snapshot = {p.name: p.read_bytes() for p in root.iterdir()}
    note = S.quarantine_synthetic_fixture(root, IDENTITY)
    assert note["files"][target]["sha256"] == hashlib.sha256(original + b"modified").hexdigest()
    assert all((root / name).read_bytes() == raw for name, raw in snapshot.items())


@pytest.mark.parametrize("missing", S.FILES)
def test_incomplete_commit_is_rejected(committed, missing):
    root, _ = committed
    (root / missing).unlink()
    assert_refused(root)


@pytest.mark.parametrize("name", [".synthetic-payload.bin.tmp", ".synthetic-metadata.json.tmp", ".synthetic-commit.json.tmp", "extra", "SYNTHETIC_FAILED.json"])
def test_orphans_and_failure_records_refuse_resume(committed, name):
    root, _ = committed
    (root / name).write_bytes(b"synthetic interrupted output")
    assert_refused(root)


@pytest.mark.parametrize("key", sorted(S.IDENTITY_KEYS))
def test_different_identity_rejects_resume_and_restore(committed, key):
    root, manifest = committed
    identity = {**IDENTITY, key: H("changed-" + key)}
    assert_refused(root, identity)
    with pytest.raises(S.StorageRefused):
        S.verify_synthetic_restore(root, manifest, identity)


def test_modified_external_manifest_refuses_restore(committed):
    root, manifest = committed
    external = copy.deepcopy(manifest)
    external["files"][S.PAYLOAD]["sha256"] = "0" * 64
    with pytest.raises(S.StorageRefused, match="externally retained"):
        S.verify_synthetic_restore(root, external, IDENTITY)


@pytest.mark.parametrize("field,value", [("groups", [0, 1, 2]), ("groups", [True]), ("groups", []), ("groups", [1, 0]), ("groups", [0, 0]), ("groups", [3200000]), ("synthetic", False), ("schema", "B2-feat/1")])
def test_synthetic_cap_and_format_are_nonbypassable(tmp_path, field, value):
    with pytest.raises(S.StorageRefused):
        S.commit_synthetic_fixture(tmp_path, DATA, {**META, field: value}, IDENTITY)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("root", ["relative", "/", "/mnt/a/../b", "/mnt/a/./b", "/mnt//b", "/mnt/a\nb", "/mnt/a\x00b", "/mnt/a\x7fb"])
def test_unsafe_roots_refused_before_any_write(root):
    with pytest.raises(S.StorageRefused):
        S.commit_synthetic_fixture(root, DATA, META, IDENTITY)


@pytest.mark.parametrize("payload", [b"unlabelled", S.PREFIX, S.PREFIX + b"a" * S.MAX_BYTES, "text", bytearray(DATA)])
def test_production_or_oversized_payload_refused(tmp_path, payload):
    with pytest.raises(S.StorageRefused):
        S.commit_synthetic_fixture(tmp_path, payload, META, IDENTITY)
    assert not list(tmp_path.iterdir())


def test_no_overwrite_of_existing_committed_fixture(committed):
    root, manifest = committed
    before = {p.name: p.read_bytes() for p in root.iterdir()}
    with pytest.raises(S.StorageRefused):
        S.commit_synthetic_fixture(root, DATA + b"new", META, IDENTITY)
    assert {p.name: p.read_bytes() for p in root.iterdir()} == before
    assert S.verify_synthetic_fixture(root, IDENTITY) == manifest


def test_concurrent_destination_is_not_overwritten(tmp_path, monkeypatch):
    original = S.os.link
    def raced_link(src, dst, **kwargs):
        if dst == S.PAYLOAD:
            (tmp_path / dst).write_bytes(b"race evidence")
        return original(src, dst, **kwargs)
    monkeypatch.setattr(S.os, "link", raced_link)
    with pytest.raises(FileExistsError):
        S.commit_synthetic_fixture(tmp_path, DATA, META, IDENTITY)
    assert (tmp_path / S.PAYLOAD).read_bytes() == b"race evidence"
    assert_refused(tmp_path)


def test_temporary_path_substitution_before_publication_is_refused(tmp_path, monkeypatch):
    original = S.os.link
    def raced_link(src, dst, **kwargs):
        if dst == S.PAYLOAD:
            temporary = tmp_path / src
            temporary.unlink()
            temporary.write_bytes(b"substituted evidence")
        return original(src, dst, **kwargs)
    monkeypatch.setattr(S.os, "link", raced_link)
    with pytest.raises(S.StorageRefused, match="substituted during publication"):
        S.commit_synthetic_fixture(tmp_path, DATA, META, IDENTITY)
    assert_refused(tmp_path)
    assert (tmp_path / ("." + S.PAYLOAD + ".tmp")).read_bytes() == b"substituted evidence"


def test_symlink_ancestor_and_root_are_refused(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    with pytest.raises(OSError):
        S.commit_synthetic_fixture(link, DATA, META, IDENTITY)
    nested = real / "nested"
    nested.mkdir()
    with pytest.raises(OSError):
        S.commit_synthetic_fixture(link / "nested", DATA, META, IDENTITY)
    assert not list(nested.iterdir())


@pytest.mark.parametrize("name", S.FILES)
def test_committed_file_symlink_or_hardlink_alias_refused(committed, tmp_path, name):
    root, _ = committed
    outside = root.parent / (root.name + "-aliased")
    outside.write_bytes((root / name).read_bytes())
    (root / name).unlink()
    (root / name).symlink_to(outside)
    assert_refused(root)
    (root / name).unlink()
    os.link(outside, root / name)
    assert_refused(root)


def test_root_substitution_during_commit_is_detected(tmp_path, monkeypatch):
    root = tmp_path / "fixture"
    root.mkdir()
    displaced = tmp_path / "displaced"
    original = S._publish
    def publish(fd, name, raw):
        original(fd, name, raw)
        if name == S.DESCRIPTOR:
            root.rename(displaced)
            root.mkdir()
    monkeypatch.setattr(S, "_publish", publish)
    with pytest.raises(S.StorageRefused, match="root substituted"):
        S.commit_synthetic_fixture(root, DATA, META, IDENTITY)
    assert list(root.iterdir()) == []
    assert (displaced / "SYNTHETIC_FAILED.json").exists()
    assert_refused(displaced)


def test_payload_modified_after_initial_hash_is_detected(committed, monkeypatch):
    root, _ = committed
    original = S._read
    changed = False
    def read(fd, name):
        nonlocal changed
        raw = original(fd, name)
        if name == S.METADATA and not changed:
            changed = True
            write(root / S.PAYLOAD, DATA + b"race")
        return raw
    monkeypatch.setattr(S, "_read", read)
    assert_refused(root)


@pytest.mark.parametrize("raw", [b'{"schema":"duplicate","schema":"duplicate"}', b'{"value":NaN}', b'{"value":Infinity}', b'{"value":1e999}', b'{"x":'])
def test_malformed_descriptor_is_never_accepted(committed, raw):
    root, _ = committed
    write(root / S.DESCRIPTOR, raw)
    assert_refused(root)


def test_oversized_file_and_fifo_refused_without_blocking(committed):
    root, _ = committed
    write(root / S.PAYLOAD, b"x" * (S.MAX_BYTES + 1))
    assert_refused(root)
    (root / S.PAYLOAD).unlink()
    os.mkfifo(root / S.PAYLOAD)
    assert_refused(root)


def test_no_quarantine_of_good_or_unrecognized_data(committed, tmp_path):
    root, _ = committed
    with pytest.raises(S.StorageRefused, match="valid committed"):
        S.quarantine_synthetic_fixture(root, IDENTITY)
    (root / "unknown.bin").write_bytes(b"unrelated user data")
    with pytest.raises(S.StorageRefused, match="recognized"):
        S.quarantine_synthetic_fixture(root, IDENTITY)
    assert not (root / "SYNTHETIC_QUARANTINE.json").exists()


def test_root_substitution_during_quarantine_is_detected(committed, monkeypatch):
    root, _ = committed
    write(root / S.METADATA, b"synthetic corruption")
    displaced = root.parent / (root.name + "-displaced")
    original = S._publish
    def publish(fd, name, raw):
        original(fd, name, raw)
        if name == "SYNTHETIC_QUARANTINE.json":
            root.rename(displaced)
            root.mkdir()
    monkeypatch.setattr(S, "_publish", publish)
    with pytest.raises(S.StorageRefused, match="root substituted"):
        S.quarantine_synthetic_fixture(root, IDENTITY)
    assert list(root.iterdir()) == []
    assert (displaced / S.METADATA).read_bytes() == b"synthetic corruption"
    assert (displaced / "SYNTHETIC_QUARANTINE.json").exists()


def test_quarantine_rejects_concurrently_modified_evidence(committed, monkeypatch):
    root, _ = committed
    write(root / S.METADATA, b"synthetic corruption")
    original = S._read
    def read(fd, name):
        raw = original(fd, name)
        if name == S.METADATA:
            write(root / S.METADATA, b"different concurrent corruption")
        return raw
    monkeypatch.setattr(S, "_read", read)
    with pytest.raises(S.StorageRefused, match="evidence changed"):
        S.quarantine_synthetic_fixture(root, IDENTITY)
    assert not (root / "SYNTHETIC_QUARANTINE.json").exists()


def device(root, index):
    return {"schema": S.DEVICE_SCHEMA, "host_id": "synthetic-host", "root": root,
            "measured_at": NOW, "filesystem_device": index, "filesystem_type": "ext4",
            "physical_storage_id": f"synthetic-disk-{index}", "physical_identity_evidence_sha256": H(str(index)),
            "capacity_bytes": 100_000_000_000, "free_bytes": 50_000_000_000}


def backup_report(work=None, backup=None, **kwargs):
    work = device("/mnt/synthetic-work", 10) if work is None else work
    backup = device("/mnt/synthetic-backup", 20) if backup is None else backup
    return S.validate_backup_devices(work, backup, observed_working=copy.deepcopy(work), observed_backup=copy.deepcopy(backup),
                                     now=NOW, max_age_seconds=86400, working_floor_bytes=35_000_000_000,
                                     backup_floor_bytes=12_000_000_000, **kwargs)


def test_consistent_fabricated_device_report_still_grants_nothing():
    report = backup_report()
    assert report["ok"] is True
    assert report["execution_permitted"] is False
    assert report["physical_independence_proven"] is False
    assert report["authorizes_nothing"] is True
    json.dumps(report, allow_nan=False)


@pytest.mark.parametrize("field,value", [("filesystem_device", 10), ("physical_storage_id", "synthetic-disk-10"), ("root", "/mnt/synthetic-work/backup"), ("root", "/mnt"), ("root", "/mnt/../backup"), ("root", "/tmp/backup"), ("root", "/mnt//backup"), ("root", "/mnt\\backup"), ("filesystem_type", "tmpfs"), ("filesystem_type", "overlay"), ("filesystem_type", "proc"), ("filesystem_type", "ramfs"), ("filesystem_type", "squashfs"), ("filesystem_type", ""), ("free_bytes", 11_999_999_999), ("capacity_bytes", 11_999_999_999), ("free_bytes", True), ("free_bytes", float("nan")), ("filesystem_device", True), ("physical_identity_evidence_sha256", "modified"), ("measured_at", "2026-09-01T00:00:00+00:00"), ("measured_at", "2026-10-26T00:00:00+00:00"), ("measured_at", "2026-10-25T12:00:00"), ("host_id", "other-host")])
def test_invalid_backup_negative_cases(field, value):
    backup = {**device("/mnt/synthetic-backup", 20), field: value}
    report = backup_report(backup=backup)
    assert report["ok"] is False
    assert report["execution_permitted"] is False
    json.dumps(report, allow_nan=False)


def test_missing_live_measurement_fails_closed():
    report = S.validate_backup_devices(device("/mnt/work", 10), device("/mnt/backup", 20), now=NOW,
                                      max_age_seconds=86400, working_floor_bytes=1, backup_floor_bytes=1)
    assert report["ok"] is False


@pytest.mark.parametrize("filesystem", sorted(S.REFUSED_FS | {"unknown", "bpf", "hugetlbfs", "binfmt_misc", "efivarfs", "fuse.fake"}))
def test_every_volatile_or_unreviewed_filesystem_fails_closed(filesystem):
    backup = {**device("/mnt/synthetic-backup", 20), "filesystem_type": filesystem}
    assert backup_report(backup=backup)["ok"] is False


@pytest.mark.parametrize("filesystem", sorted(S.DURABLE_FILESYSTEMS))
def test_reviewed_filesystem_still_does_not_prove_physical_independence(filesystem):
    backup = {**device("/mnt/synthetic-backup", 20), "filesystem_type": filesystem}
    result = backup_report(backup=backup)
    assert result["ok"] is True
    assert result["physical_independence_proven"] is False


@pytest.mark.parametrize("field,value", [("filesystem_device", 21), ("filesystem_type", "tmpfs"), ("physical_storage_id", "changed"), ("free_bytes", 1), ("measured_at", "2026-09-01T00:00:00+00:00")])
def test_changed_live_device_snapshot_fails(field, value):
    work, backup = device("/mnt/work", 10), device("/mnt/backup", 20)
    report = S.validate_backup_devices(work, backup, observed_working=work, observed_backup={**backup, field: value},
                                      now=NOW, max_age_seconds=86400, working_floor_bytes=1, backup_floor_bytes=2)
    assert report["ok"] is False


def test_observe_local_temp_directory_is_readonly_and_not_independent_storage(tmp_path, monkeypatch):
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **kw: pytest.fail("no process may be spawned"))
    first, second = tmp_path / "work", tmp_path / "backup"
    first.mkdir()
    second.mkdir()
    before = {p.name for p in tmp_path.iterdir()}
    kwargs = {"host_id": "synthetic-host", "measured_at": NOW, "physical_identity_evidence_sha256": H("synthetic-proof")}
    a = S.observe_directory(first, physical_storage_id="synthetic-first", **kwargs)
    b = S.observe_directory(second, physical_storage_id="synthetic-second", **kwargs)
    assert a["filesystem_device"] == b["filesystem_device"]
    assert a["capacity_bytes"] > 0
    assert a["filesystem_type"]
    assert {p.name for p in tmp_path.iterdir()} == before
    assert not list(first.iterdir()) and not list(second.iterdir())
    assert backup_report(a, b)["ok"] is False


def test_readonly_directory_observation_refuses_symlink(tmp_path):
    target = tmp_path / "real"
    target.mkdir()
    link = tmp_path / "link"
    link.symlink_to(target, target_is_directory=True)
    with pytest.raises(OSError):
        S.observe_directory(link, host_id="synthetic", physical_storage_id="synthetic", physical_identity_evidence_sha256=H("proof"), measured_at=NOW)


def test_no_process_generator_or_gpu_entry_point(tmp_path, monkeypatch):
    for name in ("Popen", "run", "call", "check_call", "check_output"):
        monkeypatch.setattr(subprocess, name, lambda *a, **k: pytest.fail("forbidden process spawn"))
    for name in ("system", "fork", "popen", "execv", "execve", "spawnv", "posix_spawn"):
        if hasattr(os, name):
            monkeypatch.setattr(os, name, lambda *a, **k: pytest.fail("forbidden process spawn"))
    manifest = S.commit_synthetic_fixture(tmp_path, DATA, META, IDENTITY)
    assert S.verify_synthetic_restore(tmp_path, manifest, IDENTITY)["ok"] is True
    assert backup_report()["execution_permitted"] is False
    tree = ast.parse(Path(SPEC.origin).read_text())
    imports = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    imports |= {name.name for node in ast.walk(tree) if isinstance(node, ast.Import) for name in node.names}
    assert not any(name and name.split(".")[0] in {"subprocess", "numpy", "torch", "geosim", "multiprocessing", "threading"} for name in imports)

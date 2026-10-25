"""E16 durable-admission barrier: synthetic non-RF bytes in temporary directories only.

No generator is run and no waveform, observation, model or GPU is touched. Shards are fabricated byte strings laid out
exactly like the accepted generators lay them out (part/meta/descriptor with the same names and descriptor keys).
"""
import ast
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location("b2_e16_durability", ROOT / "scripts/b2_e16_durability.py")
D = importlib.util.module_from_spec(SPEC)
sys.modules["b2_e16_durability"] = D
SPEC.loader.exec_module(D)
H = lambda text: hashlib.sha256(text.encode()).hexdigest()           # noqa: E731
REQUEST = H("request")


def expected(ordinal, role="train", request=REQUEST):
    base = 1000 + 4 * ordinal
    return {"role": role, "scenario_seeds": [base, base + 1], "n_samples": 16, "request_fingerprint": request}


def make_shard(directory, ordinal, *, role="train", request=REQUEST, descriptor_extra=None, ordered=True):
    """Fabricated bytes in the generator's layout; payload is not an RF array and not even an npz."""
    part, meta, descriptor_name = D.shard_names(ordinal)
    exp = expected(ordinal, role, request)
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    payload = b"E16-SYNTHETIC-NON-RF-PAYLOAD\n" + bytes([ordinal % 256]) * 2048
    lines = b"".join(json.dumps({"i": i, "synthetic": True}).encode() + b"\n" for i in range(exp["n_samples"]))
    (directory / part).write_bytes(payload)
    (directory / meta).write_bytes(lines)
    descriptor = {"part": part, "meta": meta, "role": role, "scenario_seeds": exp["scenario_seeds"], "n_samples": exp["n_samples"],
                  "request_fingerprint": request,
                  "sha256": {part: hashlib.sha256(payload).hexdigest(), meta: hashlib.sha256(lines).hexdigest()}}
    descriptor.update(descriptor_extra or {})
    (directory / descriptor_name).write_text(json.dumps(descriptor, indent=1, allow_nan=False))
    if ordered:
        base = 1_700_000_000
        for step, name in enumerate((part, meta, descriptor_name)):
            os.utime(directory / name, ns=((base + step) * 10 ** 9,) * 2)
    return exp


@pytest.fixture
def shard(tmp_path):
    directory = tmp_path / "train"
    return directory, make_shard(directory, 0)


def refused(callable_, *args, **kwargs):
    with pytest.raises((D.DurabilityRefused, OSError)):
        callable_(*args, **kwargs)


def snapshot(directory):
    return {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in sorted(Path(directory).iterdir()) if p.is_file()}


def assert_no_authority(report):
    assert report["authorizes_nothing"] is True
    assert report["execution_permitted"] is False
    assert report["dr_qualified"] is False


# ---- admission barrier ------------------------------------------------------------------------------------------

def test_admission_verifies_syncs_and_reverifies_without_changing_bytes(shard, monkeypatch):
    directory, exp = shard
    before = snapshot(directory)
    events = []
    real_fsync = os.fsync
    monkeypatch.setattr(D.os, "fsync", lambda fd: (events.append(os.fstat(fd).st_mode), real_fsync(fd))[1])
    record = D.admit_shard(directory, 0, exp)
    assert record["schema"] == D.SCHEMA_ADMISSION
    assert record["media_verified"] is False
    assert_no_authority(record)
    assert set(record["files"]) == set(D.shard_names(0))
    # three regular files first, then the shard directory and every ancestor up to the root
    kinds = ["file" if stat.S_ISREG(mode) else "dir" for mode in events]
    assert kinds[:3] == ["file"] * 3 and set(kinds[3:]) == {"dir"} and len(kinds) >= 5
    assert snapshot(directory) == before
    assert record["descriptor_sha256"] == hashlib.sha256((directory / "shard-00000.json").read_bytes()).hexdigest()


@pytest.mark.parametrize("call", [1, 3, 4, 5])
def test_barrier_reverifies_after_syncing(shard, monkeypatch, call):
    """Calls 1-3 sync the descriptor/payload/metadata, 4+ sync the directory chain: a change at any point is caught."""
    directory, exp = shard
    real_fsync = os.fsync
    state = {"calls": 0}

    def tampering(fd):
        state["calls"] += 1
        real_fsync(fd)
        if state["calls"] == call:                   # the payload changes after it was verified, while the barrier is still syncing
            with open(directory / "part-00000.npz", "ab") as stream:
                stream.write(b"x")
    monkeypatch.setattr(D.os, "fsync", tampering)
    refused(D.admit_shard, directory, 0, exp)


def test_file_replaced_before_it_can_be_synchronized_is_refused(shard, monkeypatch):
    directory, exp = shard
    real = D._sync_file

    def swap(dir_fd, name, snap):
        if name == "part-00000.npz":
            (directory / name).write_bytes(b"E16-SYNTHETIC-NON-RF-PAYLOAD\nother")
        return real(dir_fd, name, snap)
    monkeypatch.setattr(D, "_sync_file", swap)
    refused(D.admit_shard, directory, 0, exp)


@pytest.mark.parametrize("name,mutate", [
    ("part-00000.npz", lambda raw: raw[:-1] + bytes([raw[-1] ^ 1])),
    ("part-00000.npz", lambda raw: raw[:-1]),
    ("part-00000.npz", lambda raw: raw + b"x"),
    ("meta-00000.jsonl", lambda raw: raw.replace(b"true", b"fals", 1)),
    ("meta-00000.jsonl", lambda raw: b""),
])
def test_any_byte_change_to_payload_or_metadata_is_refused(shard, name, mutate):
    directory, exp = shard
    path = directory / name
    path.write_bytes(mutate(path.read_bytes()))
    refused(D.verify_shard, directory, 0, exp)
    refused(D.admit_shard, directory, 0, exp)


def descriptor_edit(directory, change):
    path = directory / "shard-00000.json"
    value = json.loads(path.read_text())
    change(value)
    path.write_text(json.dumps(value, indent=1))
    os.utime(path, ns=(1_700_000_009 * 10 ** 9,) * 2)


@pytest.mark.parametrize("change", [
    lambda d: d.update(extra=1),
    lambda d: d.pop("n_samples"),
    lambda d: d.update(role="test"),
    lambda d: d.update(scenario_seeds=[1000, 1002]),
    lambda d: d.update(scenario_seeds=[1001, 1000]),
    lambda d: d.update(n_samples=15),
    lambda d: d.update(n_samples=True),
    lambda d: d.update(n_samples=16.0),
    lambda d: d.update(request_fingerprint=H("other")),
    lambda d: d.update(part="part-00001.npz"),
    lambda d: d["sha256"].update({"part-00000.npz": "0" * 64}),
    lambda d: d["sha256"].update({"part-00000.npz": "A" * 64}),
    lambda d: d["sha256"].update(extra="0" * 64),
    lambda d: d.update(sha256=[]),
])
def test_descriptor_must_match_the_generator_contract_and_the_sealed_plan(shard, change):
    directory, exp = shard
    descriptor_edit(directory, change)
    refused(D.verify_shard, directory, 0, exp)


@pytest.mark.parametrize("raw", [b"{", b'{"part": NaN}', b'{"a":1,"a":2}', b"[]", b"\xff\xfe", b"x" * (D.MAX_DESCRIPTOR_BYTES + 1)])
def test_hostile_descriptor_text_is_refused(shard, raw):
    directory, exp = shard
    (directory / "shard-00000.json").write_bytes(raw)
    refused(D.verify_shard, directory, 0, exp)


def test_identity_mismatch_is_not_a_regeneration_signal(shard):
    directory, exp = shard
    other = dict(exp, request_fingerprint=H("a different request"))
    refused(D.verify_shard, directory, 0, other)
    assert snapshot(directory)                       # nothing was removed or rewritten


@pytest.mark.parametrize("bad", [
    {}, {"role": "train"}, {"role": "Train", "scenario_seeds": [1], "n_samples": 1, "request_fingerprint": REQUEST},
    {"role": "train", "scenario_seeds": [], "n_samples": 1, "request_fingerprint": REQUEST},
    {"role": "train", "scenario_seeds": [True], "n_samples": 1, "request_fingerprint": REQUEST},
    {"role": "train", "scenario_seeds": [2, 1], "n_samples": 1, "request_fingerprint": REQUEST},
    {"role": "train", "scenario_seeds": [1], "n_samples": 0, "request_fingerprint": REQUEST},
    {"role": "train", "scenario_seeds": [1], "n_samples": 1, "request_fingerprint": "abc"},
    {"role": "train", "scenario_seeds": [1], "n_samples": 1, "request_fingerprint": REQUEST, "extra": 1},
])
def test_malformed_expected_identity_is_refused(shard, bad):
    directory, _ = shard
    refused(D.verify_shard, directory, 0, bad)


@pytest.mark.parametrize("ordinal", [-1, 100000, True, "0", 1.0, None])
def test_bad_ordinals_are_refused(shard, ordinal):
    directory, exp = shard
    refused(D.verify_shard, directory, ordinal, exp)


def test_symlink_hardlink_fifo_and_directory_substitutions_are_refused(tmp_path):
    for case in ("symlink", "hardlink", "fifo", "directory"):
        directory = tmp_path / case
        exp = make_shard(directory, 0)
        victim = directory / "part-00000.npz"
        if case == "symlink":
            real = tmp_path / (case + "-target")
            victim.rename(real)
            victim.symlink_to(real)
        elif case == "hardlink":
            os.link(victim, tmp_path / (case + "-alias"))
        elif case == "fifo":
            victim.unlink()
            os.mkfifo(victim)
        else:
            victim.unlink()
            victim.mkdir()
        refused(D.verify_shard, directory, 0, exp)
        refused(D.admit_shard, directory, 0, exp)


def test_symlinked_shard_directory_is_not_followed(tmp_path):
    real = tmp_path / "real"
    exp = make_shard(real, 0)
    (tmp_path / "link").symlink_to(real)
    D.verify_shard(real, 0, exp)
    refused(D.verify_shard, tmp_path / "link", 0, exp)
    refused(D.verify_shard, "relative/path", 0, exp)
    refused(D.verify_shard, str(tmp_path) + "/../" + tmp_path.name + "/real", 0, exp)


def test_size_bounds_are_enforced(shard, monkeypatch):
    directory, exp = shard
    monkeypatch.setattr(D, "MAX_PAYLOAD_BYTES", 100)
    refused(D.verify_shard, directory, 0, exp)


def test_temporary_orphan_for_this_shard_blocks_admission_but_not_other_shards(shard):
    directory, exp = shard
    other = make_shard(directory, 1)
    (directory / "part-00001.tmp.npz").write_bytes(b"partial")
    refused(D.verify_shard, directory, 1, other)
    D.verify_shard(directory, 0, exp)


def test_descriptor_older_than_its_data_is_refused_unless_ordering_is_unavailable(shard):
    directory, exp = shard
    os.utime(directory / "shard-00000.json", ns=(1_600_000_000 * 10 ** 9,) * 2)
    refused(D.verify_shard, directory, 0, exp)
    assert D.verify_shard(directory, 0, exp, check_order=False)["role"] == "train"


# ---- classification, quarantine ---------------------------------------------------------------------------------

def plan(*ordinals, role="train"):
    return {o: expected(o, role) for o in ordinals}


def test_states_not_started_resumable_complete(tmp_path):
    directory = tmp_path / "train"
    directory.mkdir()
    assert D.classify_directory(directory, plan(0, 1))["resume_state"] == "NOT_STARTED"
    make_shard(directory, 0)
    report = D.classify_directory(directory, plan(0, 1))
    assert report["resume_state"] == "RESUMABLE"
    assert report["counts"]["COMMITTED"] == 1 and report["counts"]["ABSENT"] == 1
    make_shard(directory, 1)
    complete = D.classify_directory(directory, plan(0, 1))
    assert complete["resume_state"] == "COMPLETE" and complete["quarantine_required"] == []
    assert complete["cleanup_may_delete_evidence"] is False
    assert_no_authority(complete)
    json.dumps(complete, allow_nan=False)


@pytest.mark.parametrize("label,damage,state", [
    ("no_descriptor", lambda d: (d / "shard-00001.json").unlink(), ("1", "PARTIAL")),
    ("descriptor_only", lambda d: [(d / n).unlink() for n in ("part-00001.npz", "meta-00001.jsonl")], ("1", "PARTIAL")),
    ("temp_payload", lambda d: (d / "part-00001.tmp.npz").write_bytes(b"x"), ("1", "TEMPORARY_ORPHAN")),
    ("temp_meta", lambda d: (d / "meta-00001.jsonl.tmp").write_bytes(b"x"), ("1", "TEMPORARY_ORPHAN")),
    ("temp_descriptor", lambda d: (d / "shard-00001.json.tmp").write_bytes(b"{}"), ("1", "TEMPORARY_ORPHAN")),
    ("temp_only", lambda d: [[(d / n).unlink() for n in D.shard_names(1)], (d / "part-00001.tmp.npz").write_bytes(b"x")], ("1", "TEMPORARY_ORPHAN")),
    ("corrupt", lambda d: (d / "part-00001.npz").write_bytes(b"E16-corrupt"), ("1", "CORRUPT")),
    ("unplanned", lambda d: make_shard(d, 7), ("7", "UNPLANNED")),
    ("stray_file", lambda d: (d / "notes.txt").write_text("x"), None),
    ("stray_directory", lambda d: (d / "scratch").mkdir(), None),
    ("symlink_entry", lambda d: (d / "part-00009.npz").symlink_to(d / "part-00000.npz"), None),
    ("wrong_suffix", lambda d: (d / "part-00001.json").write_bytes(b"{}"), None),
])
def test_every_unsafe_leftover_requires_quarantine_and_is_never_deleted(tmp_path, label, damage, state):
    directory = tmp_path / "train"
    make_shard(directory, 0)
    make_shard(directory, 1)
    damage(directory)
    before = sorted(p.name for p in directory.iterdir())
    report = D.classify_directory(directory, plan(0, 1))
    assert report["resume_state"] == "NEEDS_QUARANTINE", label
    assert sorted(p.name for p in directory.iterdir()) == before
    assert report["cleanup_may_delete_evidence"] is False
    if state:
        assert report["shards"][state[0]]["state"] == state[1], label
        assert state[0] in report["quarantine_required"]
    else:
        assert report["unexpected_entries"], label


def test_resume_under_a_different_request_is_quarantine_not_regeneration(tmp_path):
    directory = tmp_path / "train"
    make_shard(directory, 0)
    changed = {0: expected(0, request=H("changed config"))}
    report = D.classify_directory(directory, changed)
    assert report["resume_state"] == "NEEDS_QUARANTINE" and report["shards"]["0"]["state"] == "CORRUPT"


def test_a_plan_must_be_bounded_and_wellformed(tmp_path):
    directory = tmp_path / "train"
    directory.mkdir()
    refused(D.classify_directory, directory, {})
    refused(D.classify_directory, directory, {0: {}})
    refused(D.classify_directory, directory, {"0": expected(0)})
    refused(D.classify_directory, tmp_path / "missing", plan(0))


def test_quarantine_note_is_outside_the_data_and_preserves_evidence(tmp_path):
    directory, evidence = tmp_path / "train", tmp_path / "evidence"
    evidence.mkdir()
    make_shard(directory, 0)
    (directory / "part-00001.tmp.npz").write_bytes(b"partial payload")
    (directory / "stray.txt").write_text("x")
    before = snapshot(directory)
    report = D.classify_directory(directory, plan(0, 1))
    note = D.write_quarantine_note(evidence, directory, report, reason="orphan from interrupted attempt", recorded_at="2026-10-30T00:00:00Z")
    assert snapshot(directory) == before
    assert note["files_moved_or_deleted"] == 0 and note["evidence_preserved_in_place"] is True
    assert note["evidence"]["part-00001.tmp.npz"]["sha256"] == hashlib.sha256(b"partial payload").hexdigest()
    assert note["evidence"]["stray.txt"]["unexpected"] is True
    names = sorted(p.name for p in evidence.iterdir())
    assert len(names) == 1 and names[0].startswith("quarantine-") and not any(n.startswith(".") for n in names)
    again = D.write_quarantine_note(evidence, directory, report, reason="orphan from interrupted attempt", recorded_at="2026-10-30T00:00:00Z")
    assert again["note_name"] == note["note_name"] and sorted(p.name for p in evidence.iterdir()) == names
    refused(D.write_quarantine_note, directory / "nested", directory, report, reason="x", recorded_at="t")
    refused(D.write_quarantine_note, tmp_path, directory, report, reason="x", recorded_at="t")
    refused(D.write_quarantine_note, evidence, directory, {}, reason="x", recorded_at="t")
    refused(D.write_quarantine_note, evidence, directory, report, reason="", recorded_at="t")


def test_quarantine_note_refuses_forged_or_stale_classifications(tmp_path):
    directory, evidence = tmp_path / "train", tmp_path / "evidence"
    evidence.mkdir()
    make_shard(directory, 0)
    (directory / "part-00001.tmp.npz").write_bytes(b"partial")
    report = D.classify_directory(directory, plan(0, 1))
    for hostile in ("../escape", "/etc/passwd", "sub/part-00001.tmp.npz", "missing.tmp", "", None, 5):
        forged = json.loads(json.dumps(report))
        forged["shards"]["1"]["files"] = [hostile]
        refused(D.write_quarantine_note, evidence, directory, forged, reason="x", recorded_at="t")
        forged = json.loads(json.dumps(report))
        forged["unexpected_entries"] = [hostile]
        refused(D.write_quarantine_note, evidence, directory, forged, reason="x", recorded_at="t")
    (directory / "part-00001.tmp.npz").unlink()                      # the report is now stale
    refused(D.write_quarantine_note, evidence, directory, report, reason="x", recorded_at="t")
    broken = json.loads(json.dumps(report))
    broken.pop("shards")
    refused(D.write_quarantine_note, evidence, directory, broken, reason="x", recorded_at="t")
    assert list(evidence.iterdir()) == []


# ---- manifests, restore, immutability --------------------------------------------------------------------------

def test_manifest_restore_roundtrip_and_every_difference_is_found(tmp_path):
    source, copy = tmp_path / "train", tmp_path / "restored"
    for ordinal in (0, 1):
        make_shard(source, ordinal)
    exps = plan(0, 1)
    manifest = D.build_manifest(source, exps)
    assert manifest["schema"] == D.SCHEMA_MANIFEST and len(manifest["entries"]) == 6 and manifest["shards"] == [0, 1]
    shutil.copytree(source, copy)
    for item in copy.iterdir():                       # a copy that lost its mtimes is still byte-verifiable
        os.utime(item, ns=(1_500_000_000 * 10 ** 9,) * 2)
    report = D.verify_restore(copy, manifest, exps)
    assert report["ok"] and report["restore_reverified"] is True and report["disaster_recovery_qualified"] is False
    assert_no_authority(report)
    # differences
    (copy / "notes.txt").write_text("x")
    refused(D.verify_restore, copy, manifest)
    (copy / "notes.txt").unlink()
    (copy / "meta-00001.jsonl").unlink()
    refused(D.verify_restore, copy, manifest)
    shutil.copy2(source / "meta-00001.jsonl", copy / "meta-00001.jsonl")
    D.verify_restore(copy, manifest, exps)
    (copy / "part-00000.npz").write_bytes(b"E16-different-bytes")
    refused(D.verify_restore, copy, manifest)


@pytest.mark.parametrize("change", [
    lambda m: m["entries"][0].update(sha256="0" * 64),
    lambda m: m["entries"][0].update(bytes=m["entries"][0]["bytes"] + 1),
    lambda m: m["entries"].pop(),
    lambda m: m["entries"].append(dict(m["entries"][0])),
    lambda m: m.update(total_bytes=m["total_bytes"] + 1),
    lambda m: m.update(role="test"),
    lambda m: m.update(extra=1),
    lambda m: m["entries"][0].update(name="../escape.npz"),
    lambda m: m.update(manifest_sha256="0" * 64),
])
def test_tampered_manifest_is_refused_even_if_files_are_intact(tmp_path, change):
    source = tmp_path / "train"
    make_shard(source, 0)
    manifest = D.build_manifest(source, plan(0))
    change(manifest)
    refused(D.verify_restore, source, manifest)


def test_manifest_requires_verified_single_role_shards(tmp_path):
    source = tmp_path / "train"
    make_shard(source, 0)
    (source / "part-00000.npz").write_bytes(b"E16-bad")
    refused(D.build_manifest, source, plan(0))
    refused(D.build_manifest, source, {})
    mixed = tmp_path / "mixed"
    make_shard(mixed, 0)
    make_shard(mixed, 1, role="test")
    refused(D.build_manifest, mixed, {0: expected(0), 1: expected(1, "test")})


def test_restore_with_wrong_identity_is_refused(tmp_path):
    source = tmp_path / "train"
    make_shard(source, 0)
    manifest = D.build_manifest(source, plan(0))
    refused(D.verify_restore, source, manifest, {0: expected(0, request=H("other"))})


def test_immutability_findings_and_honest_limits(tmp_path):
    directory = tmp_path / "train"
    make_shard(directory, 0)
    directory.chmod(0o755)
    for path in directory.iterdir():
        path.chmod(0o444)
    report = D.immutable_publication_report(directory, [0])
    assert report["ok"] is True and report["worm_proven"] is False and "limitation" in report
    (directory / "part-00000.npz").chmod(0o644)
    os.link(directory / "meta-00000.jsonl", tmp_path / "alias")
    directory.chmod(0o775)
    findings = D.immutability_findings(directory, [0, 1])
    assert any("write permission" in f for f in findings)
    assert any("singly linked" in f for f in findings)
    assert any("group- or world-writable" in f for f in findings)
    assert any("part-00001.npz is missing" in f for f in findings)


# ---- generator identity ---------------------------------------------------------------------------------------

def test_package_digest_formula_equals_the_accepted_k17d_formula_and_value():
    import b2_e10_k17d_identity as K
    digest, count = D.geosim_package_digest(ROOT)
    assert (digest, count) == K.package_digest()
    assert digest == D.ACCEPTED_GEOSIM_PACKAGE_SHA256 and count == D.ACCEPTED_GEOSIM_FILE_COUNT
    record = json.loads((ROOT / "docs/results/b2_e10_k17d_identity.json").read_text())
    assert record["package_sha256"] == digest and record["package_files"] == count
    impact = D.source_identity_impact(ROOT)
    assert impact["unchanged"] is True and impact["production_blocked"] is False


def test_any_generator_edit_blocks_production_and_names_the_required_reacceptance(tmp_path):
    shutil.copytree(ROOT / "src" / "geosim", tmp_path / "src" / "geosim", ignore=shutil.ignore_patterns("__pycache__", "data"))
    assert D.source_identity_impact(tmp_path)["unchanged"] is True
    target = tmp_path / "src" / "geosim" / "dataset.py"
    target.write_text(target.read_text() + "\n# fsync added\n")
    impact = D.source_identity_impact(tmp_path)
    assert impact["unchanged"] is False and impact["production_blocked"] is True
    assert impact["historical_identity_records_preserved"] is True
    assert any("re-derivation" in step for step in impact["required_before_any_use"])
    assert any("researcher acceptance" in step for step in impact["required_before_any_use"])
    (tmp_path / "src" / "geosim" / "extra.py").write_text("x = 1\n")
    assert D.source_identity_impact(tmp_path)["observed_files"] == D.ACCEPTED_GEOSIM_FILE_COUNT + 1


def test_the_repository_generator_is_untouched_by_this_branch():
    assert D.source_identity_impact(ROOT)["unchanged"] is True


def test_directory_identity_detects_symlink_aliases(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    (tmp_path / "alias").symlink_to(tmp_path / "a")
    assert D.directory_identity(tmp_path / "a")["st_ino"] != D.directory_identity(tmp_path / "b")["st_ino"]
    refused(D.directory_identity, tmp_path / "alias")


# ---- structure: this module only reads and syncs ---------------------------------------------------------------

def test_module_cannot_launch_delete_rename_or_read_the_environment():
    tree = ast.parse((ROOT / "scripts/b2_e16_durability.py").read_text())
    imported = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    imported |= {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    assert not imported & {"subprocess", "multiprocessing", "socket", "shutil", "ctypes", "importlib", "pty", "signal"}
    attributes = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    assert not attributes & {"system", "popen", "Popen", "run", "execv", "execve", "fork", "spawn", "unlink", "remove", "rmdir",
                              "rename", "renames", "rmtree", "truncate", "ftruncate", "environ", "getenv", "putenv", "chmod", "fchmod"}
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    assert not names & {"eval", "exec", "compile", "__import__", "open"}

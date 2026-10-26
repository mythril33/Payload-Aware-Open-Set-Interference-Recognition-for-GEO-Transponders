"""Real adapter tests: contracts use actual disk bytes; RF execution is a separate bounded exercise."""
import copy
import hashlib
import json
import os
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import b2_real_generation as M
from test_b2_e13_generation_plan import reference, decision_record, k17d_report


def world(tmp_path):
    paths = {name: tmp_path / name for name in ("work", "backup", "journal", "anchors")}
    for path in paths.values():
        path.mkdir()
    role = paths["work"] / "train"
    role.mkdir()
    payload, metadata = b"actual-on-disk-bytes", b'{"seed":3000000}\n'
    (role / "part-00000.npz").write_bytes(payload)
    (role / "meta-00000.jsonl").write_bytes(metadata)
    expected = {"role": "train", "scenario_seeds": [3000000], "n_samples": 8, "request_fingerprint": "a" * 64}
    descriptor = dict(expected, part="part-00000.npz", meta="meta-00000.jsonl",
                      sha256={"part-00000.npz": hashlib.sha256(payload).hexdigest(), "meta-00000.jsonl": hashlib.sha256(metadata).hexdigest()})
    (role / "shard-00000.json").write_text(json.dumps(descriptor))
    for name in ("request.json", "calibration.json", "receiver_calibration.npz", "manifest.json"):
        (paths["work"] / name).write_bytes(b'{}')
    return paths, {"train": {0: expected}}, {"scope": "UNIT_DISK_CONTRACT"}


def adapter(paths, expected, identity):
    return M.DurableStage(paths["work"], paths["backup"], paths["journal"], paths["anchors"], expected, identity)


def test_actual_disk_admission_backup_and_restart(tmp_path):
    paths, expected, identity = world(tmp_path)
    stage = adapter(paths, expected, identity)
    report = stage.finish()
    assert report["restores"]["train"]["ok"]
    assert report["dr_qualified"] is False
    assert stage.admitted[("train", 0)]["barrier"] == "fsync_files_then_directory_chain_then_reverify"
    before = len(stage.entries)
    restarted = adapter(paths, expected, identity)
    assert restarted.finish() == report
    assert len(restarted.entries) == before


@pytest.mark.parametrize("damage", ["root_meta", "backup_meta", "backup_shard", "role", "anchor", "journal"])
def test_recovery_refuses_missing_or_changed_evidence(tmp_path, damage):
    paths, expected, identity = world(tmp_path)
    adapter(paths, expected, identity).finish()
    if damage == "root_meta":
        (paths["work"] / "request.json").write_bytes(b'changed')
    elif damage == "backup_meta":
        (paths["backup"] / "calibration.json").unlink()
    elif damage == "backup_shard":
        (paths["backup"] / "train" / "meta-00000.jsonl").unlink()
    elif damage == "role":
        import shutil
        shutil.rmtree(paths["work"] / "train")
    elif damage == "anchor":
        for item in paths["anchors"].iterdir():
            item.unlink()
    elif damage == "journal":
        raw = paths["journal"] / M.L.LEDGER_NAME
        raw.write_bytes(raw.read_bytes()[:-10])
    with pytest.raises((M.GenerationRefused, M.D.DurabilityRefused, OSError)):
        adapter(paths, expected, identity)


def test_recovery_refuses_source_identity_and_partial_shard(tmp_path):
    paths, expected, identity = world(tmp_path)
    stage = adapter(paths, expected, identity)
    stage.admit_ready()
    with pytest.raises(M.GenerationRefused, match="identity"):
        adapter(paths, expected, dict(identity, changed=True))
    (paths["work"] / "train" / "part-00000.npz").unlink()
    with pytest.raises(M.GenerationRefused, match="unsafe"):
        adapter(paths, expected, identity)


@pytest.mark.parametrize("groups", [None, True, 0, 3, 100])
def test_development_cap_cannot_be_bypassed(tmp_path, groups):
    with pytest.raises(M.GenerationRefused, match="capped"):
        M.run_development(*(tmp_path / n for n in ("work", "backup", "journal", "anchors")), groups=groups)
    assert not list(tmp_path.iterdir())


def test_development_request_has_no_test_role():
    request, expected = M._known_request(2)
    assert request["roles"] == ["train", "val-select", "val-calib"]
    assert set(expected) == set(M.DEVELOPMENT_ROLES)
    assert all(len(value) == 2 for value in expected.values())
    assert M.D.source_identity_impact(ROOT)["unchanged"]


def test_current_production_gate_refuses_before_paths_or_evidence(tmp_path):
    def forbidden(*args):
        pytest.fail("closed gates reached evidence source")
    with pytest.raises(M.GenerationRefused, match="DR-04 remains closed"):
        M.run_production_stage({}, {}, reference={}, evidence=forbidden,
            replay_directory=tmp_path / "missing", boundary="pre_launch", adapters={}, journal=tmp_path / "journal",
            anchors=tmp_path / "anchors", resource_source=forbidden)
    assert not list(tmp_path.iterdir())


def test_generated_journal_meets_e16_stage_contract(tmp_path):
    paths, expected, _ = world(tmp_path)
    identity = {"plan_fingerprint": "b" * 64, "specification_sha256": "c" * 64}
    stage = adapter(paths, expected, identity)
    stage.append("authorization_snapshot", {"record_sha256": "d" * 64})
    result = stage.finish()
    stage.append("k17d_check", {"identity_sha256": "e" * 64})
    evidence = {"schema": M.I.SCHEMA_JOURNAL, "collected_at": M.sup.utc_now(), "entries": stage.entries,
                "anchor": stage.anchors.latest(), "location": {"ok": True, "physical_independence_proven": False}}
    problems = M.I._journal_problems(evidence, ("known",), {"plan_fingerprint": identity["plan_fingerprint"]},
        {"specification_sha256": identity["specification_sha256"]},
        {"known": {"roles": {role: {"manifest": manifest} for role, manifest in result["manifests"].items()}}},
        {"identity_sha256": "e" * 64}, {"known": "a" * 64}, M.sup.utc_now(), 3600, "d" * 64)
    assert problems == []


def test_production_sized_manifest_lives_outside_bounded_ledger_entry(tmp_path, monkeypatch):
    paths, expected, identity = world(tmp_path)
    stage = adapter(paths, expected, identity)
    # Metadata-only size exercise: no RF data and no actual375-shard production.
    entries = [{"name": f"part-{i:05d}.npz", "bytes": 1, "sha256": "a" * 64} for i in range(375)]
    manifest = {"schema": M.D.SCHEMA_MANIFEST, "role": "train", "shards": list(range(375)), "entries": entries,
                "total_bytes": 375, "manifest_sha256": "f" * 64}
    monkeypatch.setattr(M.D, "build_manifest", lambda *args: manifest)
    real_copy = M._copy_verified
    monkeypatch.setattr(M, "_copy_verified", lambda source, target, names:
                        real_copy(source, target, names) if source == paths["work"] else None)
    monkeypatch.setattr(M.D, "verify_restore", lambda *args: {"ok": True})
    monkeypatch.setattr(M.os, "chmod", lambda *args: None)
    stage.finish()
    completed = next(e for e in stage.entries if e["kind"] == "stage_completed")
    assert len(M.L.canonical(completed).encode()) < M.L.MAX_ENTRY_BYTES
    name = completed["data"]["manifest_files"]["train"]
    assert (paths["journal"] / name).stat().st_size > 30_000
    assert "manifest_documents" not in completed["data"]


def test_sealed_argv_uses_existing_three_stage_commands(reference):
    from test_b2_e13_generation_plan import complete
    plan = complete(reference)
    spec = M.C.build_specification(plan)
    for stage in ("known", "test", "matched"):
        argv = M.sealed_stage_argv(plan, spec, stage)
        assert argv[1:3] == ["-m", M.sup.MODULES[stage]]
        assert "--limit-groups" not in argv
        assert argv[argv.index("--groups-per-shard") + 1] == "4"
    changed = copy.deepcopy(spec)
    changed["plan_fingerprint"] = "0" * 64
    with pytest.raises(M.GenerationRefused, match="sealed"):
        M.sealed_stage_argv(plan, changed, "known")


def test_recovery_after_admission_crash_before_attempt_start(tmp_path):
    paths, expected, identity = world(tmp_path)
    stage = adapter(paths, expected, identity)
    assert M._retained_stage_admission(stage.entries, "known") is None
    stage.append("boundary_check", {"admission_report_file": "retained-admission.json",
                                   "admission_report_sha256": "f" * 64,
                                   "boundary_prefix_head": stage.anchors.latest()})
    # Simulate loss immediately after durable admission, before any resume/child.
    recovered = adapter(paths, expected, identity)
    assert not any(e["kind"] == "resume" for e in recovered.entries)
    assert M._retained_stage_admission(recovered.entries, "known") == recovered.entries[-1]
    recovered.append("boundary_check", {"admission_report_file": "duplicate-admission.json"})
    with pytest.raises(M.GenerationRefused, match="unique retained admission"):
        M._retained_stage_admission(recovered.entries, "known")

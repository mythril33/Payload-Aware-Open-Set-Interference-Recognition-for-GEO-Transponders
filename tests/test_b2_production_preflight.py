"""E6 production preflight: fail-closed gates, locks, checksum/role audit, resumability and the capped drill.

Everything runs on the two-group fake-simulator fixtures of the existing artifact tests; no B2 data is generated
beyond a handful of stand-in observations and no gate is ever approved.
"""
import copy
import importlib.util
import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from geosim import b2_dataset as known_ds
from geosim import b2_matched_dataset as matched_ds
from geosim import b2_test_dataset as test_ds
from geosim.b2_protocol import B2Config
from geosim.cancellation import CancellationConfig
from test_b2_test_dataset import fakes  # noqa: F401  (pytest fixture reused by name)

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location("b2_production_preflight", ROOT / "scripts" / "b2_production_preflight.py")
pre = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pre)

FIXTURE_PROVENANCE = {"unit_fixture": "0" * 64}


def strict(text):
    def reject(constant):
        raise ValueError(constant)
    return json.loads(text, parse_constant=reject)


def codes(result):
    return {item["code"] for item in result["problems"]}


@pytest.fixture
def stages(tmp_path, fakes, monkeypatch):
    monkeypatch.setattr(matched_ds, "_generator_provenance", lambda: FIXTURE_PROVENANCE)
    cancellation = CancellationConfig()
    known = tmp_path / "known"
    known_ds.generate_b2_dataset(known, roles=("train", "test"), limit_groups=2, groups_per_shard=1, cancellation=cancellation)
    test = tmp_path / "test"
    test_ds.generate_b2_test_dataset(test, known, limit_groups=2, groups_per_shard=1, cancellation=cancellation)
    matched = tmp_path / "matched"
    matched_ds.generate_b2_matched_dataset(matched, known, limit_groups=2, groups_per_shard=1, cancellation=cancellation)
    return SimpleNamespace(known=known, test=test, matched=matched, tmp=tmp_path)


def regenerate_known(root):
    known_ds.generate_b2_dataset(root, roles=("train", "test"), limit_groups=2, groups_per_shard=1,
                                 cancellation=CancellationConfig())


def flip_byte(path):
    data = bytearray(Path(path).read_bytes())
    data[len(data) // 2] ^= 0xFF
    Path(path).write_bytes(bytes(data))


# ---- inventory, estimates, gates ---------------------------------------------------------------------------

def test_inventory_is_derived_from_frozen_code_and_matches_the_plan_document():
    rows = pre.derive_inventory()
    assert sum(row["observations"] for row in rows) == 21350
    assert [row["observations"] for row in rows] == [12000, 1200, 1200, 4000, 2500, 450]
    plan = (ROOT / pre.PLAN_PATH).read_text()
    checks = pre.check_inventory(plan)
    assert {item["id"] for item in checks} >= {"inventory.counts", "inventory.roles", "inventory.plan_document"}
    assert [item["status"] for item in checks] == [pre.PASS] * len(checks)
    drifted = pre.check_inventory(plan.replace("|12000|", "|12001|"))
    assert {item["id"]: item["status"] for item in drifted}["inventory.plan_document"] == pre.FAIL


def test_estimates_reproduce_from_array_shapes_and_measured_costs(monkeypatch):
    checks = pre.check_estimates()
    assert [item["status"] for item in checks] == [pre.PASS] * 5
    storage = pre.storage_estimate()
    assert storage["float16_bytes_per_observation"] == 395264 and storage["observations"] == 21350
    monkeypatch.setitem(pre.BUDGET, "documented_wall_hours", {"low": 10.0, "central": 11.0, "high": 12.0})
    assert {item["id"]: item["status"] for item in pre.check_estimates()}["estimates.wall"] == pre.FAIL


def test_committed_gates_are_blocked_never_passed_and_benchmark_stays_incomplete():
    gates = json.loads((ROOT / pre.GATES_PATH).read_text())
    memo = json.loads((ROOT / pre.MEMO_PATH).read_text())
    status = {item["id"]: item["status"] for item in pre.check_gates(gates, memo)}
    assert status["gates.benchmark_complete"] == pre.PASS
    assert {status[f"gates.{key}"] for key in pre.GATE_KEYS} == {pre.BLOCKED}


def test_an_approval_needs_provenance_and_a_pending_gate_may_not_carry_one():
    gates = json.loads((ROOT / pre.GATES_PATH).read_text())
    memo = json.loads((ROOT / pre.MEMO_PATH).read_text())

    def run(mutate_gates=None, mutate_memo=None):
        g, m = copy.deepcopy(gates), copy.deepcopy(memo)
        (mutate_gates or (lambda x: None))(g)
        (mutate_memo or (lambda x: None))(m)
        return {item["id"]: item["status"] for item in pre.check_gates(g, m)}

    bare = run(lambda g: g["decisions"]["K18"].update(status="APPROVED"),
               lambda m: m["decisions"]["K18"].update(status="APPROVED"))
    assert bare["gates.K18"] == pre.FAIL                                            # approved, no approval record
    full = {"approved_by": "researcher", "approved_at": "2026-10-24T00:00:00Z", "decision": "retain P20", "record": "DR-E5-01"}
    both = run(lambda g: g["decisions"]["K18"].update(status="APPROVED", approval=full),
               lambda m: m["decisions"]["K18"].update(status="APPROVED"))
    assert both["gates.K18"] == pre.PASS
    assert run(lambda g: g["decisions"]["K18"].update(status="APPROVED", approval=full))["gates.K18.consistency"] == pre.FAIL
    assert run(lambda g: g["decisions"]["K17d"].update(approval=full))["gates.K17d"] == pre.FAIL
    no_ceiling = run(lambda g: g["decisions"]["full_generation"].update(status="AUTHORIZED", approval=full),
                     lambda m: m["decisions"]["full_generation"].update(status="AUTHORIZED"))
    assert no_ceiling["gates.full_generation"] == pre.FAIL                          # no wall/core/disk ceilings
    ceilings = {**full, "wall_hours": 36, "core_hours": 42, "working_disk_gib": 25, "backup_disk_gb": 9}
    ok = run(lambda g: g["decisions"]["full_generation"].update(status="AUTHORIZED", approval=ceilings),
             lambda m: m["decisions"]["full_generation"].update(status="AUTHORIZED"))
    assert ok["gates.full_generation"] == pre.PASS
    assert run(lambda g: g["decisions"]["K18"].update(status="MAYBE"))["gates.K18"] == pre.FAIL
    assert run(lambda g: g.update(benchmark_complete=True))["gates.benchmark_complete"] == pre.FAIL
    assert run(lambda g: g["decisions"].pop("full_loko_sweep"))["gates.full_loko_sweep"] == pre.FAIL


def test_the_static_checklist_never_authorizes_or_completes_the_benchmark():
    checks = pre.static_checks()
    assert all(item["status"] in pre.STATUSES for item in checks)
    assert len({item["id"] for item in checks}) == len(checks)
    result = pre.report(checks)
    assert result["production_authorized"] is False and result["benchmark_complete"] is False
    assert result["verdict"] in (pre.BLOCKED, pre.FAIL) and result["counts"][pre.BLOCKED] >= 6
    strict(json.dumps(result, allow_nan=False))
    assert "**BLOCKED**" in pre.render_markdown(checks)


def test_findings_are_well_formed_and_every_pass_names_an_existing_test_or_command():
    data = pre.load_findings()
    for item in data["items"]:
        if item["status"] != pre.PASS:
            continue
        verifier = item["verified_by"]
        if verifier.startswith("tests/"):
            path, _, name = verifier.partition("::")
            assert name and f"def {name}(" in (ROOT / path).read_text(), verifier
        else:
            assert verifier.startswith(("inspection:", "ci:")), verifier


def test_a_pass_finding_without_a_verifier_is_rejected(tmp_path):
    data = pre.load_findings()
    broken = copy.deepcopy(data)
    broken["items"][0].update(status=pre.PASS)
    broken["items"][0].pop("verified_by", None)
    target = tmp_path / "findings.json"
    target.write_text(json.dumps(broken))
    with pytest.raises(ValueError, match="verifier"):
        pre.load_findings(target)
    duplicate = copy.deepcopy(data)
    duplicate["items"].append(copy.deepcopy(duplicate["items"][0]))
    target.write_text(json.dumps(duplicate))
    with pytest.raises(ValueError, match="unique"):
        pre.load_findings(target)


# ---- source/environment/config lock ------------------------------------------------------------------------

@pytest.fixture
def mini_repo(tmp_path):
    repo = tmp_path / "repo"
    (repo / "src/geosim/data").mkdir(parents=True)
    (repo / "src/geoml").mkdir(parents=True)
    (repo / "configs").mkdir()
    (repo / "docs/plan").mkdir(parents=True)
    (repo / "src/geosim/chain.py").write_text("x = 1\n")
    (repo / "src/geosim/data/curve.csv").write_text("0,1\n")
    (repo / "src/geoml/model.py").write_text("y = 2\n")
    for name in ("configs/b2_base.json", "configs/cancellation.json", "configs/b2_feat.json", "pyproject.toml", pre.GATES_PATH):
        shutil.copy(ROOT / name, repo / name)
    state = {"commit": "a" * 40, "status": "", "env": {"python": "3.12.1", "numpy": "2.5.4", "scipy": "1.18.1",
                                                        "threads": {"OMP_NUM_THREADS": "2"}}}

    def git(*args, repo=None):
        if args[:2] == ("rev-parse", "HEAD"):
            return state["commit"]
        return state["status"] if args[0] == "status" else "main"

    hooks = {"git": git, "provenance": lambda: {"chain.py": pre._file_hash(repo / "src/geosim/chain.py")},
             "env": lambda: copy.deepcopy(state["env"])}
    return SimpleNamespace(root=repo, state=state, hooks=hooks)


def test_lock_round_trips_and_names_every_kind_of_drift(mini_repo):
    lock = pre.build_lock(mini_repo.root, **mini_repo.hooks)
    strict(json.dumps(lock, allow_nan=False))
    assert lock["benchmark_complete"] is False and lock["git"]["clean"] is True
    assert set(lock["source_sha256"]) == {"src/geosim/chain.py", "src/geosim/data/curve.csv", "src/geoml/model.py"}
    assert pre.verify_lock(lock, mini_repo.root, require_clean=True, **mini_repo.hooks) == []

    def drift(mutation, expected):
        copy_root = mini_repo.root.parent / f"drift-{abs(hash(expected))}"
        shutil.copytree(mini_repo.root, copy_root)
        hooks = dict(mini_repo.hooks, provenance=lambda: {"chain.py": pre._file_hash(copy_root / "src/geosim/chain.py")})
        mutation(copy_root)
        problems = pre.verify_lock(lock, copy_root, **hooks)
        assert any(expected in problem for problem in problems), (expected, problems)

    drift(lambda r: (r / "src/geoml/model.py").write_text("y = 3\n"), "source file modified: src/geoml/model.py")
    drift(lambda r: (r / "src/geoml/new.py").write_text("z = 0\n"), "source file added: src/geoml/new.py")
    drift(lambda r: (r / "src/geosim/data/curve.csv").unlink(), "source file removed: src/geosim/data/curve.csv")
    drift(lambda r: (r / "src/geosim/chain.py").write_text("x = 2\n"), "generator file modified: chain.py")
    drift(lambda r: (r / "configs/cancellation.json").write_text(
        json.dumps({**json.loads((ROOT / "configs/cancellation.json").read_text()), "iterations": 4})), "config file modified")
    drift(lambda r: (r / "configs/cancellation.json").write_text(
        json.dumps({**json.loads((ROOT / "configs/cancellation.json").read_text()), "iterations": 4})), "parsed physical or canceller")
    mini_repo.state["commit"] = "b" * 40
    assert any("git commit" in p for p in pre.verify_lock(lock, mini_repo.root, **mini_repo.hooks))
    mini_repo.state["commit"] = "a" * 40
    mini_repo.state["env"]["numpy"] = "2.5.5"
    assert any("environment numpy" in p for p in pre.verify_lock(lock, mini_repo.root, **mini_repo.hooks))
    mini_repo.state["env"]["numpy"] = "2.5.4"
    mini_repo.state["env"]["threads"]["OMP_NUM_THREADS"] = "8"
    assert any("thread environment" in p for p in pre.verify_lock(lock, mini_repo.root, **mini_repo.hooks))
    mini_repo.state["env"]["threads"]["OMP_NUM_THREADS"] = "2"


def test_lock_refuses_dirty_trees_foreign_documents_and_edited_fingerprints(mini_repo):
    mini_repo.state["status"] = " M src/geosim/chain.py"
    dirty = pre.build_lock(mini_repo.root, **mini_repo.hooks)
    assert dirty["git"]["clean"] is False
    assert any("not clean" in p for p in pre.verify_lock(dirty, mini_repo.root, require_clean=True, **mini_repo.hooks))
    mini_repo.state["status"] = ""
    lock = pre.build_lock(mini_repo.root, **mini_repo.hooks)
    forged = copy.deepcopy(lock)
    forged["git"]["clean"] = False
    assert any("own fingerprint" in p for p in pre.verify_lock(forged, mini_repo.root, **mini_repo.hooks))
    assert pre.verify_lock({"schema": "other"}, mini_repo.root, **mini_repo.hooks) == ["not a B2-production-lock/1 document"]
    assert pre.verify_lock([], mini_repo.root, **mini_repo.hooks)


def test_the_real_lock_is_self_consistent_and_the_preflight_adds_no_hashed_source():
    lock = pre.build_lock()
    assert pre.verify_lock(lock) == []
    assert lock["parsed"]["b2_config"] == B2Config().to_dict()
    assert lock["production"]["groups_per_shard"] == 4 and lock["benchmark_complete"] is False
    assert not [name for name in lock["source_sha256"] if "preflight" in name or "decision_evidence" in name]
    assert not [name for name in lock["generator_provenance"] if "preflight" in name]


# ---- artifact audit ----------------------------------------------------------------------------------------

def test_every_stage_audits_complete_with_full_checksum_and_deep_verification(stages):
    known = pre.audit_artifact(stages.known, "known", depth="full", max_full=None)
    assert known["state"] == "COMPLETE" and known["problems"] == [] and known["hashed_bytes"] > 0
    assert {role: info["committed"] for role, info in known["roles"].items()} == {"train": 2, "test": 2}
    assert known["deep_verified"] == {"train": [0, 1], "test": [0, 1]}
    for stage, root in (("test", stages.test), ("matched", stages.matched)):
        result = pre.audit_artifact(root, stage, depth="full", max_full=None, known=stages.known)
        assert result["state"] == "COMPLETE" and result["problems"] == [], (stage, result["problems"])
    assert pre.audit_check(known)["status"] == pre.PASS
    strict(json.dumps(pre.report([pre.audit_check(known)]), allow_nan=False))


def test_missing_or_empty_roots_are_not_started(tmp_path):
    assert pre.audit_artifact(tmp_path / "absent", "known")["state"] == "NOT_STARTED"
    (tmp_path / "empty").mkdir()
    assert pre.audit_artifact(tmp_path / "empty", "test")["state"] == "NOT_STARTED"
    (tmp_path / "foreign").mkdir()
    (tmp_path / "foreign" / "notes.txt").write_text("x")
    result = pre.audit_artifact(tmp_path / "foreign", "matched")
    assert result["state"] == "INVALID" and "request_invalid" in codes(result)


def test_an_interrupted_root_is_resumable_and_the_generator_keeps_verified_shards(stages):
    root = stages.tmp / "interrupted"
    shutil.copytree(stages.known, root)
    for name in ("manifest.json", "train/shard-00001.json", "train/part-00001.npz", "train/meta-00001.jsonl"):
        (root / name).unlink()
    audit = pre.audit_artifact(root, "known")
    assert audit["state"] == "RESUMABLE" and audit["problems"] == []
    assert audit["roles"]["train"]["committed"] == 1 and audit["roles"]["train"]["missing"] == 1
    kept = {path.name: pre._file_hash(path) for path in (root / "train").glob("*-00000.*")}
    regenerate_known(root)
    assert {path.name: pre._file_hash(path) for path in (root / "train").glob("*-00000.*")} == kept
    assert pre.audit_artifact(root, "known", depth="full", max_full=None)["state"] == "COMPLETE"


def test_leftover_temporaries_are_reported_but_do_not_block_resume(stages):
    root = stages.tmp / "temporaries"
    shutil.copytree(stages.known, root)
    (root / "train" / "part-00007.tmp.npz").write_bytes(b"partial")
    (root / "train" / "meta-00007.jsonl.tmp").write_text("{")
    audit = pre.audit_artifact(root, "known")
    assert audit["state"] == "COMPLETE"
    assert sorted(audit["leftover_temporaries"]) == ["train/meta-00007.jsonl.tmp", "train/part-00007.tmp.npz"]


def test_an_orphaned_shard_needs_quarantine_and_the_generator_refuses_it(stages):
    root = stages.tmp / "orphan"
    shutil.copytree(stages.known, root)
    for name in ("manifest.json", "train/shard-00001.json"):
        (root / name).unlink()
    audit = pre.audit_artifact(root, "known")
    assert audit["state"] == "NEEDS_QUARANTINE" and audit["roles"]["train"]["orphan"] == [1]
    assert pre.audit_check(audit)["status"] == pre.BLOCKED
    with pytest.raises(ValueError, match="unverified partial B2 shard"):
        regenerate_known(root)
    quarantine = root / "quarantine"
    quarantine.mkdir()
    for name in ("part-00001.npz", "meta-00001.jsonl"):
        shutil.move(str(root / "train" / name), str(quarantine / name))
    assert pre.audit_artifact(root, "known")["state"] == "RESUMABLE"
    regenerate_known(root)
    assert pre.audit_artifact(root, "known", depth="full", max_full=None)["state"] == "COMPLETE"


def test_modified_shards_are_invalid_only_when_checksums_are_read(stages):
    root = stages.tmp / "corrupt"
    shutil.copytree(stages.known, root)
    flip_byte(root / "train" / "part-00000.npz")
    structure = pre.audit_artifact(root, "known", depth="structure")
    assert structure["state"] == "COMPLETE" and structure["hashed_bytes"] == 0       # the cheap depth cannot see this
    for depth in ("checksum", "full"):
        audit = pre.audit_artifact(root, "known", depth=depth)
        assert audit["state"] == "INVALID" and "checksum_mismatch" in codes(audit)
        assert pre.audit_check(audit)["status"] == pre.FAIL
    with pytest.raises(ValueError):
        regenerate_known(root)
    metadata = stages.tmp / "meta"
    shutil.copytree(stages.test, metadata)
    (metadata / "test" / "meta-00000.jsonl").write_text("{}\n")
    assert "checksum_mismatch" in codes(pre.audit_artifact(metadata, "test"))


def test_deep_verification_uses_the_generators_own_validator(stages, monkeypatch):
    seen = []
    original = known_ds._verify_part
    monkeypatch.setattr(known_ds, "_verify_part", lambda *a, **k: seen.append(a[2:4]) or original(*a, **k))
    pre.audit_artifact(stages.known, "known", depth="full", max_full=None)
    assert sorted(seen) == [("test", 0), ("test", 1), ("train", 0), ("train", 1)]
    seen.clear()
    pre.audit_artifact(stages.known, "known", depth="full", max_full=1)
    assert len(seen) == 2                                                          # one bounded sample per role
    monkeypatch.setattr(known_ds, "_verify_part", lambda *a, **k: (_ for _ in ()).throw(ValueError("semantic")))
    assert "deep_verification" in codes(pre.audit_artifact(stages.known, "known", depth="full"))


def test_source_drift_since_generation_is_detected_as_a_refused_resume(stages, monkeypatch):
    monkeypatch.setattr(known_ds, "_generator_provenance", lambda: {"unit_fixture": "1" * 64})
    audit = pre.audit_artifact(stages.known, "known")
    assert audit["state"] == "INVALID"
    problem = next(item for item in audit["problems"] if item["code"] == "generator_would_refuse_resume")
    assert "source_sha256:unit_fixture" in problem["keys"]
    with pytest.raises(ValueError, match="request changed"):
        regenerate_known(stages.known)                                              # what the audit predicts


def test_a_tampered_request_or_a_role_crossing_is_invalid(stages):
    root = stages.tmp / "tampered"
    shutil.copytree(stages.known, root)
    request = json.loads((root / "request.json").read_text())
    request["scenario_groups"]["test"] = request["scenario_groups"]["train"]
    (root / "request.json").write_text(json.dumps(request))
    audit = pre.audit_artifact(root, "known")
    assert audit["state"] == "INVALID" and {"role_groups", "generator_would_refuse_resume"} <= codes(audit)
    request = json.loads((stages.known / "request.json").read_text())
    request["benchmark_complete"] = True
    other = stages.tmp / "complete-flag"
    shutil.copytree(stages.known, other)
    (other / "request.json").write_text(json.dumps(request))
    assert "protocol_contract" in codes(pre.audit_artifact(other, "known"))
    nan = stages.tmp / "nan"
    shutil.copytree(stages.known, nan)
    (nan / "request.json").write_text((stages.known / "request.json").read_text().replace('"limit_groups": 2', '"limit_groups": NaN'))
    assert "request_invalid" in codes(pre.audit_artifact(nan, "known"))


def test_a_modified_calibration_artifact_is_invalid(stages):
    root = stages.tmp / "calibration"
    shutil.copytree(stages.known, root)
    flip_byte(root / "receiver_calibration.npz")
    assert "calibration" in codes(pre.audit_artifact(root, "known"))


def test_a_stray_file_or_a_wrong_descriptor_is_invalid(stages):
    root = stages.tmp / "stray"
    shutil.copytree(stages.known, root)
    (root / "train" / "extra.bin").write_bytes(b"x")
    assert "unexpected_files" in codes(pre.audit_artifact(root, "known"))
    other = stages.tmp / "descriptor"
    shutil.copytree(stages.known, other)
    path = other / "train" / "shard-00000.json"
    descriptor = json.loads(path.read_text())
    descriptor["scenario_seeds"] = [3_100_000]                                      # a val-select group in the train shard
    path.write_text(json.dumps(descriptor))
    audit = pre.audit_artifact(other, "known")
    assert audit["state"] == "INVALID" and "descriptor_mismatch" in codes(audit)
    manifest = stages.tmp / "manifest"
    shutil.copytree(stages.known, manifest)
    document = json.loads((manifest / "manifest.json").read_text())
    document["roles"]["train"]["shards"] = document["roles"]["train"]["shards"][:1]
    (manifest / "manifest.json").write_text(json.dumps(document))
    assert "manifest_shards" in codes(pre.audit_artifact(manifest, "known"))
    early = stages.tmp / "early-manifest"
    shutil.copytree(stages.known, early)
    for name in ("train/shard-00001.json", "train/part-00001.npz", "train/meta-00001.jsonl"):
        (early / name).unlink()
    assert "manifest_incomplete" in codes(pre.audit_artifact(early, "known"))


def test_the_production_flag_rejects_every_pilot_request(stages):
    audit = pre.audit_artifact(stages.known, "known", production=True)
    assert audit["state"] == "INVALID" and "not_production_request" in codes(audit)
    assert "not_production_request" not in codes(pre.audit_artifact(stages.known, "known"))
    assert "not_production_request" in codes(pre.audit_artifact(stages.test, "test", production=True))


def test_the_lock_binds_source_config_canceller_and_library_versions(stages):
    lock = pre.build_lock(provenance=lambda: FIXTURE_PROVENANCE)
    assert pre.audit_artifact(stages.known, "known", lock=lock)["problems"] == []
    for field, mutate in (("generator source", lambda l: l.update(generator_provenance={"unit_fixture": "2" * 64})),
                          ("numpy version", lambda l: l["environment"].update(numpy="0.0")),
                          ("scipy version", lambda l: l["environment"].update(scipy="0.0")),
                          ("physical config", lambda l: l["parsed"].update(b2_config={})),
                          ("canceller config", lambda l: l["parsed"].update(cancellation={}))):
        changed = copy.deepcopy(lock)
        mutate(changed)
        problem = next(item for item in pre.audit_artifact(stages.known, "known", lock=changed)["problems"]
                       if item["code"] == "lock_mismatch")
        assert problem["fields"] == [field]


def test_test_and_matched_roots_must_bind_to_the_given_known_root_and_its_code(stages, monkeypatch):
    assert pre.audit_artifact(stages.test, "test", known=stages.known)["state"] == "COMPLETE"
    other = stages.tmp / "other-known"
    known_ds.generate_b2_dataset(other, roles=("train", "test"), limit_groups=2, groups_per_shard=2,
                                 cancellation=CancellationConfig())
    for stage, root in (("test", stages.test), ("matched", stages.matched)):
        audit = pre.audit_artifact(root, stage, known=other)
        problem = next(item for item in audit["problems"] if item["code"] == "known_binding")
        assert {"known_request_fingerprint", "known_data_fingerprint"} <= set(problem["fields"])
    # The generators bind fingerprints only: a stage generated from different code still verifies on its own.
    drifted = stages.tmp / "drifted-test"
    monkeypatch.setattr(test_ds, "_generator_provenance", lambda: {"unit_fixture": "9" * 64})
    test_ds.generate_b2_test_dataset(drifted, stages.known, limit_groups=2, groups_per_shard=1, cancellation=CancellationConfig())
    assert test_ds.read_b2_test_manifest(drifted)["benchmark_complete"] is False          # accepted by the generator
    audit = pre.audit_artifact(drifted, "test", known=stages.known)
    problem = next(item for item in audit["problems"] if item["code"] == "known_binding")
    assert problem["fields"] == ["cross_stage_source_sha256"]
    missing = pre.audit_artifact(stages.test, "test", known=stages.tmp / "absent")
    assert "known_binding" in codes(missing)


# ---- transfer manifest, resources, drill, command line -----------------------------------------------------

def test_transfer_manifest_detects_missing_extra_resized_and_modified_files(stages):
    manifest = pre.create_transfer_manifest(stages.known)
    assert manifest["n_files"] == len(manifest["files"]) > 8 and manifest["artifact_fingerprint"]
    strict(json.dumps(manifest, allow_nan=False))
    copy_root = stages.tmp / "copied"
    shutil.copytree(stages.known, copy_root)
    assert pre.verify_transfer_manifest(manifest, copy_root) == []
    flip_byte(copy_root / "train" / "part-00000.npz")
    (copy_root / "train" / "meta-00001.jsonl").write_text("short\n")
    (copy_root / "calibration.json").unlink()
    (copy_root / "stray.txt").write_text("x")
    problems = pre.verify_transfer_manifest(manifest, copy_root)
    assert {"sha256 differs: train/part-00000.npz", "size differs: train/meta-00001.jsonl",
            "missing: calibration.json", "extra: stray.txt"} <= set(problems)
    assert pre.verify_transfer_manifest({"schema": "x"}, copy_root)
    with pytest.raises(ValueError):
        pre.create_transfer_manifest(stages.tmp / "absent")


def test_resource_probe_fails_closed_and_blocks_the_gpu(tmp_path):
    ok = pre.probe_resources(tmp_path, disk_usage=lambda p: SimpleNamespace(free=100 * 2 ** 30),
                             memory_gib=lambda: 32.0, cpu_count=lambda: 4, rename_probe=lambda p: True)
    status = {item["id"]: item["status"] for item in ok}
    assert status == {"resources.disk": pre.PASS, "resources.atomic_rename": pre.PASS, "resources.ram": pre.PASS,
                      "resources.cpu": pre.PASS, "resources.gpu": pre.BLOCKED}
    bad = pre.probe_resources(tmp_path, disk_usage=lambda p: SimpleNamespace(free=2 ** 30), memory_gib=lambda: None,
                              cpu_count=lambda: 1, rename_probe=lambda p: False)
    status = {item["id"]: item["status"] for item in bad}
    assert status == {"resources.disk": pre.FAIL, "resources.atomic_rename": pre.FAIL, "resources.ram": pre.NOT_RUN,
                      "resources.cpu": pre.FAIL, "resources.gpu": pre.BLOCKED}
    assert pre.PROPOSED_CEILINGS["authorized"] is False


def test_atomic_rename_probe_cleans_up_after_itself(tmp_path):
    assert pre.atomic_rename_probe(tmp_path) is True
    assert list(tmp_path.iterdir()) == []
    assert pre.atomic_rename_probe(tmp_path / "does-not-exist") is False


def test_capped_resume_drill_passes_on_the_fixture_generator(fakes, tmp_path):
    generate, load = pre.real_drill_hooks()
    checks = pre.resume_drill(tmp_path / "drill", generate, load)
    assert [item["id"] for item in checks] == ["drill.complete", "drill.resume", "drill.corruption", "drill.orphan",
                                              "drill.request_lock"]
    assert [item["status"] for item in checks] == [pre.PASS] * 5, [item["message"] for item in checks]
    with pytest.raises(ValueError, match="exactly two groups"):
        pre.resume_drill(tmp_path / "other", generate, load, groups=3)


def test_the_drill_fails_when_a_generator_silently_repairs_corruption(fakes, tmp_path, monkeypatch):
    generate, load = pre.real_drill_hooks()

    def repairing(root, groups_per_shard=1):
        """A defective generator that discards a modified shard instead of refusing the root."""
        for descriptor_path in sorted((root / "train").glob("shard-*.json")):
            descriptor = json.loads(descriptor_path.read_text())
            part = root / "train" / descriptor["part"]
            if pre._file_hash(part) != descriptor["sha256"][part.name]:
                for path in (descriptor_path, part, root / "train" / descriptor["meta"], root / "manifest.json"):
                    path.unlink(missing_ok=True)
        generate(root, groups_per_shard)

    checks = pre.resume_drill(tmp_path / "bad", repairing, load)
    assert {item["id"]: item["status"] for item in checks}["drill.corruption"] == pre.FAIL


def test_command_line_exit_codes_strict_json_and_no_overwrite(tmp_path, capsys, stages):
    capsys.readouterr()                                                             # discard the fixture generators' progress lines
    assert pre.main(["inventory"]) == 0
    result = strict(capsys.readouterr().out)
    assert result["benchmark_complete"] is False and result["production_authorized"] is False and result["verdict"] == "PASS"
    assert pre.main(["gates"]) == 4
    assert strict(capsys.readouterr().out)["counts"]["BLOCKED"] == 6
    assert pre.main(["--allow-blocked", "gates"]) == 0
    capsys.readouterr()
    out = tmp_path / "report.json"
    assert pre.main(["audit", "--stage", "known", "--root", str(stages.known), "--out", str(out)]) == 0
    assert strict(out.read_text())["checks"][0]["evidence"]["state"] == "COMPLETE"
    with pytest.raises(SystemExit) as refused:
        pre.main(["audit", "--stage", "known", "--root", str(stages.known), "--out", str(out)])
    assert refused.value.code == 2
    flip_byte(stages.known / "train" / "part-00000.npz")
    assert pre.main(["audit", "--stage", "known", "--root", str(stages.known)]) == 3
    capsys.readouterr()
    manifest = tmp_path / "transfer.json"
    assert pre.main(["transfer-manifest", "--root", str(stages.test), "--out", str(manifest)]) == 0
    assert pre.main(["transfer-manifest", "--root", str(stages.test), "--verify", str(manifest)]) == 0
    capsys.readouterr()
    lock_file = tmp_path / "lock.json"
    lock = pre.build_lock()
    lock["git"]["commit"] = "0" * 40
    lock_file.write_text(json.dumps(lock))
    assert pre.main(["lock-verify", "--lock", str(lock_file)]) == 3
    with pytest.raises(SystemExit):
        pre.main(["audit", "--stage", "nonsense", "--root", str(tmp_path)])


def test_checklist_command_renders_markdown_and_refuses_overwrites(tmp_path, capsys):
    markdown = tmp_path / "checklist.md"
    assert pre.main(["--allow-blocked", "checklist", "--markdown", str(markdown)]) in (0, 3)
    capsys.readouterr()
    assert markdown.read_text().startswith("# B2/1 production-readiness checklist (E6)")
    with pytest.raises(SystemExit) as refused:
        pre.main(["checklist", "--markdown", str(markdown)])
    assert refused.value.code == 2


def test_the_committed_checklist_equals_a_fresh_rendering():
    committed = ROOT / "docs/plan/B2_E6_PRODUCTION_READINESS_CHECKLIST.md"
    assert committed.read_text() == pre.render_markdown(pre.static_checks())


def test_lock_create_refuses_a_dirty_tree_without_the_explicit_flag(tmp_path, monkeypatch):
    dirty = pre.build_lock()
    dirty["git"]["clean"] = False
    monkeypatch.setattr(pre, "build_lock", lambda *a, **k: dirty)
    with pytest.raises(SystemExit) as refused:
        pre.main(["lock-create", "--out", str(tmp_path / "lock.json")])
    assert refused.value.code == 2 and not (tmp_path / "lock.json").exists()
    assert pre.main(["lock-create", "--allow-dirty", "--out", str(tmp_path / "lock.json")]) == 0
    assert strict((tmp_path / "lock.json").read_text())["git"]["clean"] is False

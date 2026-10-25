"""E14 sealed launch architecture: synthetic documents, no real generation."""
import ast
import copy
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import b2_e14_launch_contract as C
from test_b2_e13_generation_plan import reference, decision_record, k17d_report, complete


@pytest.fixture
def ready(reference):
    # Approval-shaped dictionaries exist only in this synthetic fixture.
    return complete(reference), reference


def reseal(plan):
    plan["plan_fingerprint"] = C.G.plan_fingerprint(plan)
    return plan


def assert_closed(report):
    assert report["verdict"] == "NO-GO"
    assert report["execution_permitted"] is False
    assert report["authorizes_nothing"] is True
    assert report["production_launch_enabled"] is False
    assert report["executor_implemented"] is False
    assert report["benchmark_complete"] is False
    json.dumps(report, allow_nan=False)


def test_consistent_approval_and_green_ci_still_cannot_execute(ready):
    plan, reference = ready
    spec = C.build_specification(plan)
    report = C.admit(spec, plan, reference)
    assert_closed(report)
    assert report["document_consistent"] is True
    assert report["e13_report"]["plan_status"] == C.G.DOCUMENT_OK
    assert report["production_metadata_cross_verification"] == "NOT_RUN"
    with pytest.raises(C.ExecutionUnavailable):
        C.deny_execution(spec, approval=plan["authorization"], ci="green", execute=True)


def test_inventory_shards_and_deferred_request_binding(ready):
    plan, _ = ready
    spec = C.build_specification(plan)
    stages = spec["stages"]
    assert [s["name"] for s in stages] == ["known", "test", "matched"]
    assert [s["requires_completed_stage"] for s in stages] == [None, "known", "test"]
    assert [s["known_artifact_binding_required"] for s in stages] == [False, True, True]
    assert [len(s["shards"]) for s in stages] == [576, 125, 38]
    assert sum(s["observations"] for stage in stages for s in stage["shards"]) == 21350
    assert len({g for stage in stages for s in stage["shards"] for g in s["groups"]}) == 2450
    assert all(1 <= len(s["groups"]) <= 4 for stage in stages for s in stage["shards"])
    assert stages[0]["request_binding"]["status"] == "FROZEN"
    assert all(stage["request_binding"] == {"status": "DEFERRED_UNTIL_KNOWN_VERIFIED", "fingerprint": None} for stage in stages[1:])
    assert all(s["payload_checksum"] is s["metadata_checksum"] is None for stage in stages for s in stage["shards"])
    assert spec["disk_policy"]["estimated_artifact_bytes"] == 8668100000
    assert spec["disk_policy"]["startup_free_gib"] == pytest.approx(33.8800769299)


def test_hashes_bind_all_shards_and_input_copy_isolation(ready):
    plan, _ = ready
    original = copy.deepcopy(plan)
    first = C.build_specification(plan)
    assert plan == original
    changed = copy.deepcopy(plan)
    changed["source"]["git_commit"] = "c" * 40
    reseal(changed)
    second = C.build_specification(changed)
    assert first["specification_sha256"] != second["specification_sha256"]
    assert all(a["planned_identity_sha256"] != b["planned_identity_sha256"]
               for x, y in zip(first["stages"], second["stages"]) for a, b in zip(x["shards"], y["shards"]))
    first["stages"][0]["identity"]["source"]["git_commit"] = "d" * 40
    assert plan == original


@pytest.mark.parametrize("key", ["execute", "argv", "launcher", "override", "limit_groups", "callback", "shell", "bypass"])
def test_unknown_execution_options_refused(ready, key):
    plan, _ = ready
    plan["stages"]["known"]["options"][key] = "anything"
    reseal(plan)
    with pytest.raises(C.PlanError):
        C.build_specification(plan)


@pytest.mark.parametrize("field,value", [("groups_per_shard", 8), ("groups_per_shard", True), ("out", "../test"), ("out", "/tmp/test"),
                                        ("out", "test"), ("config", "configs/other.json"), ("cancellation", "configs/other.json")])
def test_paths_and_frozen_generator_options(ready, field, value):
    plan, _ = ready
    plan["stages"]["known"]["options"][field] = value
    reseal(plan)
    with pytest.raises(C.PlanError):
        C.build_specification(plan)


@pytest.mark.parametrize("field,value", [("groups", 1499), ("role", "test"), ("first_group", 3200000),
                                        ("variants_per_group", 7), ("shards", 374), ("groups", 1500.0)])
def test_wrong_role_group_shard_counts(ready, field, value):
    plan, _ = ready
    plan["inventory"]["rows"][0][field] = value
    reseal(plan)
    with pytest.raises(C.PlanError):
        C.build_specification(plan)


@pytest.mark.parametrize("field", ["authorization", "lock", "host", "backup", "release_evidence"])
def test_missing_admission_prerequisite(ready, field):
    plan, reference = ready
    plan[field] = None
    reseal(plan)
    report = C.admit(C.build_specification(plan), plan, reference)
    assert_closed(report)
    assert not report["document_consistent"]


@pytest.mark.parametrize("field,value", [("expires_at", "2020-01-01T00:00:00Z"), ("git_commit", "b" * 40),
                                        ("basis", "green_ci"), ("basis", "scientific_approval"),
                                        ("approved_by", "forged-actor"), ("record_sha256", "0" * 64),
                                        ("approved_plan_digest", "0" * 64), ("grants", ["full_generation", "full_gpu_training"])])
def test_forged_expired_mismatched_approval(ready, field, value):
    plan, reference = ready
    plan["authorization"][field] = value
    reseal(plan)
    report = C.admit(C.build_specification(plan), plan, reference)
    assert_closed(report)
    assert not report["document_consistent"]


@pytest.mark.parametrize("area,key,value", [("source", "git_commit", "b" * 40),
    ("source", "generator_provenance_fingerprint", "0" * 64), ("source", "configs_sha256", {}),
    ("environment", "python", "3.99.0"), ("environment", "thread_environment", {}),
    ("source", "tree_clean", False)])
def test_source_config_environment_reuse_refused(ready, area, key, value):
    plan, reference = ready
    plan[area][key] = value
    reseal(plan)
    report = C.admit(C.build_specification(plan), plan, reference)
    assert_closed(report)
    assert not report["document_consistent"]


@pytest.mark.parametrize("decision", ["R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8", "R9", "R10"])
def test_scientific_training_decisions_not_retuned(ready, decision):
    plan, reference = ready
    reference["scientific_protocol"]["decisions"][decision]["choice"] = "RETUNED"
    report = C.admit(C.build_specification(plan), plan, reference)
    assert_closed(report)
    assert not report["document_consistent"]


@pytest.mark.parametrize("obligation", ["exposure_disclosure", "k17d_production_metadata_cross_check", "backup_checksum_verified_before_data_is_made_read_only"])
def test_obligations_cannot_be_removed(ready, obligation):
    plan, _ = ready
    del plan["post_generation_obligations"][obligation]
    reseal(plan)
    with pytest.raises(C.PlanError):
        C.build_specification(plan)


@pytest.mark.parametrize("change", ["runtime", "stage", "shard", "hash", "release", "extra"])
def test_rehashed_specification_tampering_fails(ready, change):
    plan, reference = ready
    spec = C.build_specification(plan)
    if change == "runtime": spec["runtime_policy"]["execution_available"] = True
    if change == "stage": spec["stages"].reverse()
    if change == "shard": spec["stages"][0]["shards"][0]["groups"][0] += 1
    if change == "release": spec["required_future_release_controls"] = []
    if change == "extra": spec["execute"] = True
    if change == "hash": spec["specification_sha256"] = "0" * 64
    else: spec["specification_sha256"] = C.digest({k: v for k, v in spec.items() if k != "specification_sha256"})
    report = C.admit(spec, plan, reference)
    assert_closed(report)
    assert not report["document_consistent"]


@pytest.mark.parametrize("value", [None, [], {}, {"bad": float("nan")}, {"bad": float("inf")}, {1: "non-string"}, {"tuple": (1, 2)}])
def test_malformed_metadata_returns_strict_closed_report(ready, value):
    plan, reference = ready
    report = C.admit(value, plan, reference)
    assert_closed(report)
    assert not report["document_consistent"]


def test_no_process_waveform_array_or_execution_callback(ready, monkeypatch):
    plan, reference = ready
    def forbidden(*args, **kwargs):
        pytest.fail("forbidden execution/observation API reached")
    for name in ("Popen", "run", "call", "check_call", "check_output"):
        monkeypatch.setattr(subprocess, name, forbidden)
    for name in ("system", "popen", "fork", "execv", "execve", "spawnv"):
        monkeypatch.setattr(os, name, forbidden)
    import numpy as np
    from geosim import b2_dataset, b2_scenarios, b2_test_dataset, b2_matched_dataset
    monkeypatch.setattr(np, "load", forbidden)
    for module in (b2_dataset, b2_test_dataset, b2_matched_dataset):
        for name in dir(module):
            if name.startswith("generate_"):
                monkeypatch.setattr(module, name, forbidden)
    monkeypatch.setattr(b2_scenarios, "simulate_dual", forbidden)
    monkeypatch.setattr(C.G.sup, "run_child", forbidden)
    assert_closed(C.admit(C.build_specification(plan), plan, reference))
    with pytest.raises(C.ExecutionUnavailable): C.deny_execution(forbidden, approval=plan["authorization"])


def test_existing_fixture_cap_and_guard_unchanged():
    assert C.G.sup.PRODUCTION_LAUNCH_ENABLED is False
    assert C.G.sup.FIXTURE_MAX_GROUPS == 2
    production = C.G.sup.build_plan(Path("/nonexistent-e14"), mode="production", groups_per_shard=4)
    with pytest.raises(C.G.sup.SupervisorError): C.G.sup.stage_argv("known", production, Path("/nonexistent-e14"))
    for count in (3, 21, 21350):
        with pytest.raises(C.G.sup.SupervisorError): C.G.sup.assert_bounded(["generator", "--limit-groups", str(count)])
    with pytest.raises(C.G.e9.ExecutionNotAuthorized): C.G.e9.guard_execution("generation")


@pytest.mark.parametrize("flag", ["execute", "launch", "run", "--execute", "--launch", "--max-groups", "--override"])
def test_cli_cannot_expose_production_path(flag, monkeypatch):
    monkeypatch.setattr(C.G, "collect_reference", lambda **kwargs: pytest.fail("CLI reached reference on forbidden flag"))
    with pytest.raises(SystemExit) as error: C.main([flag])
    assert error.value.code == 2


def test_bounded_reader_rejects_symlink_alias_and_traversal(tmp_path):
    target = tmp_path / "input.json"
    target.write_text('{"metadata":true}')
    assert C._read(target) == {"metadata": True}
    link = tmp_path / "link.json"
    link.symlink_to(target)
    with pytest.raises(OSError): C._read(link)
    alias = tmp_path / "alias.json"
    os.link(target, alias)
    with pytest.raises(C.PlanError): C._read(alias)
    with pytest.raises(C.PlanError): C._read(str(tmp_path / "unused" / ".." / "input.json"))


def test_serialized_specification_round_trip_and_cli_exit4(ready, tmp_path, capsys):
    plan, _ = ready
    file = tmp_path / "plan.json"
    file.write_text(json.dumps(plan))
    assert C.main(["specification", "--plan", str(file)]) == 4
    output = json.loads(capsys.readouterr().out)
    assert output["execution_permitted"] is False
    assert output["specification"] == C.build_specification(plan)


def test_reader_rejects_parent_namespace_substitution(tmp_path, monkeypatch):
    original = tmp_path / "original"
    original.mkdir()
    target = original / "input.json"
    target.write_text('{"original":true}')
    actual_open = C._parent_handle
    count = 0
    def substitute(path):
        nonlocal count
        count += 1
        if count == 2:
            original.rename(tmp_path / "preserved")
            original.mkdir()
            (original / "input.json").write_text('{"substituted":true}')
        return actual_open(path)
    monkeypatch.setattr(C, "_parent_handle", substitute)
    with pytest.raises(C.PlanError, match="substituted"):
        C._read(target)


def test_no_process_import_or_runner_in_new_module():
    tree = ast.parse(Path(C.__file__).read_text())
    forbidden = {"subprocess", "multiprocessing", "threading", "socket", "torch"}
    assert not any(isinstance(node, ast.Import) and any(n.name in forbidden for n in node.names) for node in ast.walk(tree))
    assert not any(isinstance(node, ast.ImportFrom) and node.module in forbidden for node in ast.walk(tree))

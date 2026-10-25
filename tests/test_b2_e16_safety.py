"""E16 safety properties, one named test per required property, exercised through the public integration surface.

Each test states the property it protects. Evidence and documents are synthetic; no process is started, no generator is run and
no held-out observation is read. Where a property is also covered in depth by a module suite, this file re-asserts it end to end
so that a regression in the wiring (not only in a validator) is caught.
"""
import ast
import copy
import hashlib
import json
import os
import sys
from pathlib import Path
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import b2_e16_integration as I  # noqa: E402
from test_b2_e13_generation_plan import reference, decision_record, k17d_report, complete, H, HEAD  # noqa: E402,F401
from test_b2_e16_integration import (world, World, status, failing, assert_closed, CLOCK, SCOPE, WORKING, BACKUP,  # noqa: E402,F401
                                     build_world, KNOWN_FP, FINGERPRINTS, mutate_stage)
from test_b2_e16_durability import make_shard, plan as shard_plan, expected as shard_expected  # noqa: E402

D, L, P, C, G, S = I.D, I.L, I.P, I.C, I.G, I.S
E16_SCRIPTS = sorted((ROOT / "scripts").glob("b2_e16_*.py"))


def tree_of(path):
    return ast.parse(path.read_text())


def run_all_boundaries(world):
    for boundary in I.BOUNDARIES:
        assert_closed(world.run(boundary))


# 1 -------------------------------------------------------------------------------------------------------------------
def test_01_no_production_subprocess_can_be_launched(world):
    forbidden_modules = {"subprocess", "multiprocessing", "socket", "ctypes", "pty", "signal", "threading", "concurrent", "asyncio"}
    forbidden_attributes = {"system", "popen", "Popen", "run", "call", "check_call", "check_output", "execv", "execve", "execvp", "execl", "execlp",
                            "fork", "forkpty", "spawnl", "spawnv", "posix_spawn", "startfile", "kill", "killpg"}
    assert E16_SCRIPTS and len(E16_SCRIPTS) == 4
    for path in E16_SCRIPTS:
        tree = tree_of(path)
        modules = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        modules |= {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
        assert not modules & forbidden_modules, path.name
        assert not {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)} & forbidden_attributes, path.name
    traps = [mock.patch("subprocess.Popen", side_effect=AssertionError("process")), mock.patch("os.system", side_effect=AssertionError("shell")),
             mock.patch("os.fork", side_effect=AssertionError("fork")), mock.patch("os.execv", side_effect=AssertionError("exec")),
             mock.patch("os.posix_spawn", side_effect=AssertionError("spawn"))]
    for trap in traps:
        trap.start()
    try:
        run_all_boundaries(world)
        assert P.main(["ci-gate"]) == 0
    finally:
        for trap in traps:
            trap.stop()


# 2 -------------------------------------------------------------------------------------------------------------------
def test_02_no_full_generation_command_is_reachable():
    sup = G.sup
    probe = Path("/nonexistent-e16-safety-probe")
    with pytest.raises(sup.SupervisorError):
        sup.stage_argv("known", sup.build_plan(probe, mode="production", groups_per_shard=4), probe)
    for path in E16_SCRIPTS:
        tree = tree_of(path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                assert "--limit-groups" not in node.value and "python -m" not in node.value, (path.name, node.value[:60])
            if isinstance(node, (ast.FunctionDef, ast.Name)):
                name = node.name if isinstance(node, ast.FunctionDef) else node.id
                assert name.lower() not in {"build_command", "stage_argv", "launch", "run_stage", "execute", "start_generation", "spawn"}, (path.name, name)
    assert G.sup.PRODUCTION_LAUNCH_ENABLED is False
    with pytest.raises(G.e9.ExecutionNotAuthorized):
        G.e9.guard_execution("generation")


# 3 -------------------------------------------------------------------------------------------------------------------
def test_03_two_group_fixture_cap_is_intact():
    sup = G.sup
    assert sup.FIXTURE_MAX_GROUPS == 2 and S.FIXTURE_MAX_GROUPS == 2 and I.C.RUNTIME_POLICY["fixture_max_groups"] == 2
    with pytest.raises(sup.SupervisorError):
        sup.build_plan(Path("/nonexistent-e16-cap"), mode="fixture", max_groups=3, groups_per_shard=1)
    for path in E16_SCRIPTS:
        for node in ast.walk(tree_of(path)):
            targets = [t for a in ast.walk(node) if isinstance(a, ast.Assign) for t in a.targets] if isinstance(node, ast.Module) else []
            assert not [t for t in targets if isinstance(t, ast.Attribute) and "FIXTURE" in t.attr], path.name
        assert "FIXTURE_MAX_GROUPS =" not in path.read_text()


# 4 -------------------------------------------------------------------------------------------------------------------
def test_04_missing_dr04_approval_is_rejected(reference):
    plan = G.make_template(reference)
    spec = C.build_specification(plan)
    report = P.evaluate_operational_authorization(plan, reference, requested_scope=SCOPE, now=CLOCK)
    assert report["state"] == P.STATE_CLOSED and report["execution_permitted"] is False
    integration = I.evaluate_release_boundary(plan, reference, spec, boundary="pre_launch", requested_scope=SCOPE, now=CLOCK)
    assert status(integration)["authorization.policy"] == I.BLOCKED and integration["document_conditions_met"] is False
    real = tuple(json.loads((ROOT / path).read_text()) for path in (P.pre.GATES_PATH, P.pre.MEMO_PATH, G.PROTOCOL_JSON))
    assert P.classify_gates(*real)["state"] == P.STATE_CLOSED


# 5 -------------------------------------------------------------------------------------------------------------------
def test_05_green_ci_alone_cannot_authorize(reference):
    plan = complete(reference)                            # exact-head CI, independent review and a consistent plan are all present
    assert plan["release_evidence"]["exact_head_ci"]["conclusion"] == "success"
    reference["gates"]["decisions"]["full_generation"].update(status="NOT_AUTHORIZED", approval=None)
    reference["memo"]["decisions"]["full_generation"].update(status="NOT_AUTHORIZED", approved_by=None, approved_at=None, record=None)
    report = P.evaluate_operational_authorization(plan, reference, requested_scope=SCOPE, now=CLOCK)
    assert report["state"] == P.STATE_DENIED and report["execution_permitted"] is False
    plan["release_evidence"] = None
    plan["authorization"] = None
    plan["plan_fingerprint"] = G.plan_fingerprint(plan)
    assert P.evaluate_operational_authorization(plan, reference, requested_scope=SCOPE, now=CLOCK)["state"] == P.STATE_CLOSED


# 6 -------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("label,change", [
    ("missing_field", lambda a: a.pop("expires_at")), ("other_commit", lambda a: a.update(git_commit="d" * 40)),
    ("other_host", lambda a: a.update(host_id="rogue")), ("other_lock", lambda a: a.update(lock_fingerprint=H("rogue"))),
    ("extra_grant", lambda a: a.update(grants=["full_generation", "full_gpu_training"])), ("other_digest", lambda a: a.update(approved_plan_digest=H("rogue"))),
    ("scientific_record_as_basis", lambda a: a.update(record="docs/plan/B2_E12_D1_D8_SCIENTIFIC_APPROVAL_2026-10-24.md")),
])
def test_06_incomplete_or_forged_approvals_are_rejected(world, label, change):
    change(world.plan["authorization"])
    report = I.evaluate_release_boundary(world.plan, world.ref, world.spec, boundary="after_known", requested_scope=SCOPE, now=CLOCK,
                                         adapters=world.adapters("after_known"))
    assert_closed(report)
    assert report["document_conditions_met"] is False and status(report)["authorization.policy"] == I.FAIL


# 7 -------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("label,change", [
    ("head", lambda p, r: r.update(head="e" * 40)), ("dirty", lambda p, r: r.update(tree_clean=False)),
    ("source_file", lambda p, r: r["files_sha256"].update({"src/geosim/alpha.py": "0" * 64})),
    ("config", lambda p, r: r["configs_sha256"].update({next(iter(r["configs_sha256"])): "0" * 64})),
    ("generator_provenance", lambda p, r: r.update(generator_provenance_fingerprint=H("edited generator"))),
    ("tools", lambda p, r: r["tools_sha256"].update({next(iter(r["tools_sha256"])): "0" * 64})),
    ("host_node", lambda p, r: r["host_measurements"].update(node="another-host")),
    ("host_ram", lambda p, r: r["host_measurements"].update(ram_gib=2.0)),
    ("environment", lambda p, r: r["environment"].update(numpy="9.9.9")),
])
def test_07_source_config_and_host_mismatches_are_rejected(world, label, change):
    change(world.plan, world.ref)
    report = world.run("after_known")
    assert report["document_conditions_met"] is False
    assert {"identity.source_config_environment", "plan.dr04", "authorization.policy"} & set(failing(report)), label


# 8 -------------------------------------------------------------------------------------------------------------------
def test_08_stale_environment_locks_and_references_are_rejected(world):
    world.ref["lock_problems"] = ["lock no longer verifies against the clean checkout"]
    assert status(world.run("after_known"))["identity.source_config_environment"] == I.FAIL
    world.ref["lock_problems"] = []
    assert world.run("after_known", now="2026-10-30T14:00:00+00:00")["document_conditions_met"] is False      # reference is two hours old
    world.plan["lock"] = None
    assert world.run("after_known")["document_conditions_met"] is False


# 9 -------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("label,change", [
    ("same_device", lambda d: d["devices"]["backup"].update(filesystem_device=11)), ("tmp_root", lambda d: d["devices"]["backup"].update(root="/tmp/b2-backup")),
    ("tmpfs", lambda d: d["devices"]["backup"].update(filesystem_type="tmpfs")), ("overlay", lambda d: d["devices"]["backup"].update(filesystem_type="overlay")),
    ("dev_shm", lambda d: d["devices"]["working"].update(root="/dev/shm/b2")),
])
def test_09_backup_on_the_same_or_a_volatile_device_is_rejected(world, label, change):
    def backup_state(stage):
        doc = world.backup_doc(stage)
        change(doc)
        return doc
    report = world.run("after_known", backup_state=backup_state)
    assert "backup.known" in failing(report) and report["document_conditions_met"] is False


# 10 ------------------------------------------------------------------------------------------------------------------
def test_10_shard_corruption_and_interrupted_commits_are_rejected(tmp_path):
    directory = tmp_path / "train"
    for ordinal in range(3):
        make_shard(directory, ordinal)
    plan3 = shard_plan(0, 1, 2)
    assert D.classify_directory(directory, plan3)["resume_state"] == "COMPLETE"
    (directory / "shard-00001.json").unlink()                              # interrupted between payload/metadata and the descriptor
    assert D.classify_directory(directory, plan3)["resume_state"] == "NEEDS_QUARANTINE"
    (directory / "part-00002.npz").write_bytes(b"corrupted")
    report = D.classify_directory(directory, plan3)
    assert report["shards"]["2"]["state"] == "CORRUPT" and report["shards"]["1"]["state"] == "PARTIAL"
    with pytest.raises(D.DurabilityRefused):
        D.admit_shard(directory, 2, shard_expected(2))
    assert (directory / "part-00002.npz").read_bytes() == b"corrupted"      # evidence preserved, nothing repaired or regenerated


# 11 ------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("boundary,early", [("pre_launch", "known"), ("pre_launch", "matched"), ("after_known", "matched"), ("after_test", "known_missing")])
def test_11_stage_order_violations_are_rejected(world, boundary, early):
    if early == "known_missing":
        report = world.run(boundary, shard_state=lambda stage: world.not_started(stage))
        assert "durability.known" in failing(report)
        return
    report = world.run(boundary, shard_state=lambda stage: copy.deepcopy(world.cached["stage"][stage]) if stage == early else world.stage_doc(stage, boundary))
    assert f"durability.{early}" in failing(report) and report["document_conditions_met"] is False


# 12 ------------------------------------------------------------------------------------------------------------------
def test_12_expired_authorization_is_rejected(world):
    expiry = world.plan["authorization"]["expires_at"]
    late = "2026-11-20T00:00:00+00:00"
    assert expiry.startswith("2026-11-20")
    world.ref["evaluated_at"] = late
    adapters = world.adapters("after_known", revocation_checker=lambda rid: {"revoked": False, "checked_at": late})
    report = I.evaluate_release_boundary(world.plan, world.ref, world.spec, boundary="after_known", requested_scope=SCOPE, now=late, adapters=adapters)
    assert status(report)["authorization.policy"] == I.FAIL and report["document_conditions_met"] is False
    stop = L.evaluate_stop_conditions(world.resource, world.plan["ceilings"], {"expires_at": expiry, "revoked": False, "revocation_id": "r"},
                                      now="2026-11-20T00:00:00+00:00", stage="test")
    assert "authorization.expired" in stop["reasons"] or stop["decision"] == "STOP"


# 13 ------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("field,value,reason", [
    ("elapsed_wall_s", 36 * 3600.0, "ceiling.wall_hours"), ("cpu_core_s", 42 * 3600.0, "ceiling.core_hours"), ("peak_rss_gib", 3.0, "ceiling.max_rss_gib"),
    ("failed_attempts", 3, "ceiling.failed_attempts"), ("interruptions", 21, "ceiling.interruptions"), ("working_free_gib", 25.1, "projection.working_disk"),
])
def test_13_resource_budget_exhaustion_stops_admission(world, field, value, reason):
    observation = copy.deepcopy(world.resource)
    observation[field] = value
    stop = L.evaluate_stop_conditions(observation, world.plan["ceilings"], {"expires_at": world.plan["authorization"]["expires_at"], "revoked": False, "revocation_id": "r"},
                                      now=CLOCK, stage="known")
    assert stop["decision"] == "STOP" and reason in stop["reasons"] and stop["execution_permitted"] is False
    report = world.run("after_known", resource_state=lambda stage: observation)
    assert status(report)["runtime.stop_conditions"] == I.FAIL


# 14 ------------------------------------------------------------------------------------------------------------------
def test_14_d1_exposed_group_reporting_is_mandatory(world):
    report = world.run("after_matched")
    assert report["mandatory_reporting"]["d1_exclusion_rows"] == {"test": 498, "test-matched": 148}
    assert report["mandatory_reporting"]["d1_existing_test_pristine"] is False
    world.plan["scientific"]["d1_exposure"]["existing_test_pristine"] = True
    world.plan["plan_fingerprint"] = G.plan_fingerprint(world.plan)
    world.spec = C.build_specification(world.plan)
    assert status(world.run("after_known"))["reporting.d1_d8"] == I.FAIL
    world.plan["scientific"]["d1_exposure"]["existing_test_pristine"] = False
    world.plan["post_generation_obligations"]["exposure_disclosure"]["status"] = "OPTIONAL"       # softening a mandatory disclosure
    world.plan["plan_fingerprint"] = G.plan_fingerprint(world.plan)
    with pytest.raises(C.PlanError):                       # the sealed specification refuses a plan that softens the obligation
        C.build_specification(world.plan)
    report = I.evaluate_release_boundary(world.plan, world.ref, world.spec, boundary="after_known", requested_scope=SCOPE, now=CLOCK,
                                         adapters=world.adapters("after_known"))
    assert "input" in failing(report) and report["document_conditions_met"] is False


@pytest.mark.parametrize("change", [lambda d: d["d1_obligations"].update(existing_test_pristine=True), lambda d: d.pop("d1_obligations"),
                                    lambda d: d["d1_obligations"]["exposure_excluded_groups"].update({"test": 0}),
                                    lambda d: d["d1_obligations"]["exposure_excluded_groups"].pop("test-matched"),
                                    lambda d: d["d1_obligations"].update(exposed_test_ids=[3200000])])
def test_14b_the_k17d_comparison_must_carry_the_d1_disclosure(world, change):
    def k17d_metadata():
        doc = copy.deepcopy(world.k17d)
        change(doc)
        return doc
    assert "k17d.metadata" in failing(world.run("after_known", k17d_metadata=k17d_metadata))


# 15 ------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("change", [lambda d: d["counts"].update(headline=499), lambda d: d.update(identity_sha256=H("another identity")),
                                    lambda d: d.update(metadata_status="NOT_MATCHING"), lambda d: d.update(production_cross_verification_performed=False)])
def test_15_k17d_identity_mismatch_fails_closed(world, change):
    def k17d_metadata():
        doc = copy.deepcopy(world.k17d)
        change(doc)
        return doc
    report = world.run("after_known", k17d_metadata=k17d_metadata)
    assert "k17d.metadata" in failing(report) and report["document_conditions_met"] is False
    assert world.plan["scientific"]["d8_k17d"]["identity_sha256"] == "ccdf0a8f40e71d7ddb388068e455a77a131214f5644ab332a16c8268cfc49c6d"


# 16 ------------------------------------------------------------------------------------------------------------------
def test_16_test_and_matched_data_cannot_leak_into_training_or_calibration(world):
    assert I.check_consumer_isolation(I.ALLOWED_CONSUMERS) == []
    for consumer in I.ALLOWED_CONSUMERS:
        for held_out in I.HELD_OUT:
            declaration = copy.deepcopy(I.ALLOWED_CONSUMERS)
            declaration[consumer] = declaration[consumer] + [list(held_out)]
            assert I.check_consumer_isolation(declaration), (consumer, held_out)
    def alias(stage):
        doc = world.stage_doc(stage, "after_matched")
        if stage == "matched":
            doc["roles"]["test-matched"]["directory"] = copy.deepcopy(world.stage_doc("known", "after_matched")["roles"]["train"]["directory"])
        return doc
    assert "isolation.roles" in failing(world.run("after_matched", shard_state=alias))
    def foreign_role(stage):
        doc = world.stage_doc(stage, "after_matched")
        if stage == "known":
            doc["roles"]["test-matched"] = copy.deepcopy(doc["roles"]["train"])
        return doc
    assert "durability.known" in failing(world.run("after_matched", shard_state=foreign_role))


# boundaries stated by the task ---------------------------------------------------------------------------------------
def test_no_environment_override_or_hidden_launch_flag_exists():
    for path in E16_SCRIPTS:
        tree = tree_of(path)
        assert not {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)} & {"environ", "getenv", "putenv"}, path.name
    arguments = [n for n in ast.walk(tree_of(ROOT / "scripts/b2_e16_policy.py")) if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "add_argument"]
    assert sorted(a.args[0].value for a in arguments) == ["--repo"]


def test_canonical_state_is_unchanged_and_closed():
    gates = json.loads((ROOT / P.pre.GATES_PATH).read_text())
    for key in ("full_generation", "full_gpu_training", "full_loko_sweep"):
        assert gates["decisions"][key]["status"] == "NOT_AUTHORIZED" and gates["decisions"][key]["approval"] is None
    assert gates["benchmark_complete"] is False
    assert G.sup.PRODUCTION_LAUNCH_ENABLED is False
    assert D.source_identity_impact(ROOT)["unchanged"] is True

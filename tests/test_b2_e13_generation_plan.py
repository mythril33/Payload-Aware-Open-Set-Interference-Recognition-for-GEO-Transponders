"""E13 DR-04 generation launch-plan validation: synthetic metadata-only tests.

No generator is run, no waveform is synthesized, no observation, model or GPU is touched and no real held-out data is
read. Plans and references are synthetic dictionaries built from the frozen code constants; the only repository files
read are small committed metadata records (decision register, K17d identity, audit) and source/config files for hashing.
A report that says the plan is complete and consistent must still say NO-GO: every test about authorization checks that.
"""
import ast
import copy
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SCRIPT = ROOT / "scripts" / "b2_e13_generation_plan.py"
spec = importlib.util.spec_from_file_location("b2_e13_generation_plan", SCRIPT)
G = importlib.util.module_from_spec(spec)
sys.modules["b2_e13_generation_plan"] = G
spec.loader.exec_module(G)
pre, sup, e9 = G.pre, G.sup, G.e9

H = lambda text: hashlib.sha256(text.encode()).hexdigest()           # noqa: E731
HEAD = "a" * 40
NOW = "2026-10-30T12:00:00+00:00"
RECORD = "docs/operations/B2_E13_TEST_DR04_RECORD.md"                  # a synthetic compute-authorization record path
THREADS = {"OMP_NUM_THREADS": "2", "OPENBLAS_NUM_THREADS": "2", "MKL_NUM_THREADS": "2", "PYTHONHASHSEED": "0"}
SCIENTIFIC_HASHES = [H("scientific-a"), H("scientific-b")]


def fake_git(head=HEAD, dirty="", blob_ok=True):
    """Stands in for run_git: only the read-only queries collect_reference makes, with the -c prefix stripped."""
    def run(*args, repo=None):
        assert args[:2] == ("-c", "core.fsmonitor=false"), args
        args = args[2:]
        if args[:2] == ("rev-parse", "HEAD"):
            return head
        if args[0] == "rev-parse":
            return "blob-1"
        if args[0] == "hash-object":
            return "blob-1" if blob_ok else "blob-2"
        if args[0] == "ls-files":
            return args[-1]
        if args[0] == "status":
            return dirty
        raise AssertionError(f"unexpected git query {args}")
    return run


# ---- synthetic fixtures ----------------------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def decision_record():
    raw = (ROOT / G.DECISIONS).read_bytes()
    return {"path": G.DECISIONS, "sha256": hashlib.sha256(raw).hexdigest(), "document": G.k17d_check._strict(raw)}


@pytest.fixture(scope="module")
def k17d_report():
    report = G.k17d_check.verify_identity(root=ROOT, acceptance_path=G.DECISIONS, rederive=False)    # metadata files only
    return dict(report, generator_rederived=True)         # a synthetic stand-in for the complete re-derivation (see the live test)


def gates_with_dr04(approved):
    gates, memo = (json.loads((ROOT / path).read_text()) for path in (pre.GATES_PATH, pre.MEMO_PATH))
    if approved:
        record = {"approved_by": "researcher", "approved_at": "2026-10-29T08:00:00Z", "decision": "DR-04 generation of 21,350 observations",
                  "record": RECORD, "wall_hours": 36, "core_hours": 42, "working_disk_gib": 25, "backup_disk_gb": 9}
        gates["decisions"]["full_generation"].update(status="AUTHORIZED", approval=record)
        memo["decisions"]["full_generation"].update(status="AUTHORIZED")
    return gates, memo


@pytest.fixture()
def reference(decision_record, k17d_report):
    gates, memo = gates_with_dr04(False)
    files = {f"src/geosim/{name}.py": H(name) for name in ("alpha", "beta", "gamma")}
    return {"schema": G.SCHEMA_REFERENCE, "evaluated_at": NOW, "head": HEAD, "tree_clean": True, "files_sha256": files,
            "configs_sha256": {name: H(name) for name in pre.LOCKED_CONFIGS}, "generator_provenance_fingerprint": H("generator"),
            "parsed_config_sha256": {"b2_config": H("b2"), "cancellation": H("cancel")}, "known_request_fingerprint": H("request"),
            "environment": {"python": "3.12.14", "numpy": "2.5.4", "scipy": "1.18.1", "threads": dict(THREADS)},
            "tools_sha256": {name: H(name) for name in G.TOOLS}, "records_sha256": {name: H(name) for name in G.INPUT_FILES if name != pre.GATES_PATH},
            "committed_inputs": {name: True for name in G.INPUT_FILES}, "scientific_protocol": json.loads((ROOT / G.PROTOCOL_JSON).read_text()),
            "scientific_record_sha256": list(SCIENTIFIC_HASHES),
            "gates": gates, "memo": memo, "decision_record": copy.deepcopy(decision_record),
            "k17d_verification": copy.deepcopy(k17d_report), "record_files": {}, "record_texts": {}, "lock": None, "lock_problems": None}


def host_report(**override):
    inventory = {"node": "gen-host-01", "collected_at": "2026-10-29T09:00:00+00:00", "python": "3.12.14",
                 "libraries": {"numpy": "2.5.4", "scipy": "1.18.1", "torch": None}, "environment": dict(THREADS, CUDA_VISIBLE_DEVICES=None),
                 "cpu": {"logical_cpus": 8, "schedulable_cpus": 8, "model": "synthetic", "cgroup_cpu_quota": None},
                 "memory": {"total_gib": 32.0, "available_gib": 30.0, "cgroup_limit_gib": None},
                 "disks": [{"path": "/data/b2", "queried": "/data/b2", "device": 11, "fstype": "xfs", "total_gib": 500.0, "free_gib": 400.0},
                           {"path": "/mnt/backup/b2", "queried": "/mnt/backup/b2", "device": 22, "fstype": "ext4", "total_gib": 100.0, "free_gib": 90.0}]}
    report = {"schema": G.host_inventory.SCHEMA, "role": "generation", "read_only": True, "gpu_computation_performed": False,
              "production_authorized": False, "benchmark_complete": False, "inventory": inventory}
    report.update(override)
    return report


def finish(plan):
    plan["plan_fingerprint"] = G.plan_fingerprint(plan)
    return plan


def complete(reference):
    """A fully populated, internally consistent synthetic plan with a DR-04 record and the matching gate. Still NO-GO."""
    plan = G.make_template(reference)
    plan["lock"] = {"lock_fingerprint": H("lock")}
    reference["lock"] = {"lock_fingerprint": H("lock")}
    reference["lock_problems"] = []
    plan["host"] = {"host_id": "gen-host-01", "inventory": host_report()}
    plan["working"] = {"root": "/data/b2", "storage_id": "disk-A"}
    plan["backup"] = {"root": "/mnt/backup/b2", "storage_id": "disk-B", "capacity_gb": 100}
    plan["ceilings_status"] = G.CEILINGS_STATUS[1]
    plan["release_evidence"] = {"independent_review": {"path": "docs/research/b2_e13_review.md", "reviewed_head": HEAD, "open_material_findings": 0},
                                "exact_head_ci": {"run_id": 1, "job_id": 2, "head_sha": HEAD, "conclusion": "success"}, "self_asserted": True}
    finish(plan)
    reference["gates"], reference["memo"] = gates_with_dr04(True)
    reference["record_files"] = {RECORD: H("record")}
    digest = G.approved_plan_digest(plan)
    reference["record_texts"] = {RECORD: f"Approved by researcher. approved_plan_digest {digest}; host_id gen-host-01; expires_at 2026-11-20T00:00:00Z."}
    plan["authorization"] = {
        "schema": G.SCHEMA_AUTHORIZATION, "kind": "compute_generation", "gate": "full_generation", "stage": "DR-04", "observations": 21350,
        "basis": G.AUTH_BASIS, "approved_by": "researcher", "approved_at": "2026-10-29T08:00:00Z", "expires_at": "2026-11-20T00:00:00Z",
        "decision": "DR-04 generation of 21,350 observations", "record": RECORD, "record_sha256": H("record"),
        "plan_fingerprint": plan["plan_fingerprint"], "approved_plan_digest": digest, "git_commit": HEAD, "lock_fingerprint": H("lock"), "host_id": "gen-host-01",
        "working_storage_id": "disk-A", "backup_storage_id": "disk-B",
        "ceilings": {"wall_hours": 36.0, "core_hours": 42.0, "working_disk_gib": 25.0, "backup_disk_gb": 9},
        "grants": ["full_generation"], "does_not_grant": list(G.NOT_GRANTED)}
    return plan


def status(report):
    return {item["id"]: item["status"] for item in report["findings"]}


def run(plan, reference):
    report = G.validate_plan(plan, reference)
    json.dumps(report, allow_nan=False)                                    # always strict JSON
    assert report["verdict"] == "NO-GO" and report["execution_permitted"] is False and report["authorizes_nothing"] is True
    assert report["executor_implemented"] is False and report["benchmark_complete"] is False
    return report


def failing(report):
    return sorted(i["id"] for i in report["findings"] if i["status"] == G.FAIL)


def blocked(report):
    return sorted(i["id"] for i in report["findings"] if i["status"] == G.BLOCKED)


def mutate(plan, path, value):
    target = plan
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    return plan


# ---- the success path never grants permission ------------------------------------------------------------------------

def test_complete_consistent_plan_is_still_no_go(reference):
    plan = complete(reference)
    report = run(plan, reference)
    assert report["plan_status"] == G.DOCUMENT_OK and failing(report) == [] and blocked(report) == []
    assert report["counts"]["PASS"] >= 45 and report["counts"]["FAIL"] == 0 and report["counts"]["BLOCKED"] == 4          # the four structural blockers
    assert {b["id"] for b in report["structural_blockers"]} == {"release.launch_disabled", "release.no_unbounded_launcher",
                                                                 "release.fixture_cap", "release.e9_guard"}
    assert all(b["status"] == G.BLOCKED for b in report["structural_blockers"]) and report["production_launch_enabled"] is False


def test_template_has_no_failures_but_five_blocked_external_facts(reference):
    report = run(G.make_template(reference), reference)
    assert failing(report) == [] and report["plan_status"] == "INCOMPLETE_OR_INCONSISTENT"
    assert blocked(report) == ["authorization.dr04", "backup.device", "host.inventory", "lock.document", "release.evidence"]


def test_validation_is_deterministic_and_does_not_mutate_inputs(reference):
    plan = complete(reference)
    before = (copy.deepcopy(plan), copy.deepcopy(reference))
    first, second = run(plan, reference), run(plan, reference)
    assert first == second and (plan, reference) == before


# ---- DR-04 authorization: missing, forged, incomplete, wrongly based ------------------------------------------------

def test_missing_dr04_authorization_is_blocked_even_with_every_other_input_correct(reference):
    plan = complete(reference)
    plan["authorization"] = None
    report = run(plan, reference)
    assert blocked(report) == ["authorization.dr04"] and report["plan_status"] == "INCOMPLETE_OR_INCONSISTENT"


@pytest.mark.parametrize("key", G.AUTH_KEYS)
def test_authorization_missing_any_field_fails(reference, key):
    plan = complete(reference)
    del plan["authorization"][key]
    assert "authorization.shape" in failing(run(plan, reference))


def test_authorization_unexpected_field_fails(reference):
    plan = complete(reference)
    plan["authorization"]["approved_automatically"] = True
    assert "authorization.shape" in failing(run(plan, reference))


@pytest.mark.parametrize("path,value", [
    (("approved_by",), ""), (("approved_by",), None), (("decision",), "  "), (("approved_at",), "not-a-time"), (("approved_at",), "2026-10-29T08:00:00"),
    (("approved_at",), "2099-01-01T00:00:00Z"), (("expires_at",), "2026-10-01T00:00:00Z"), (("expires_at",), None),
])
def test_forged_or_incomplete_provenance_fails(reference, path, value):
    plan = complete(reference)
    mutate(plan["authorization"], path, value)
    assert "authorization.provenance" in failing(run(plan, reference))


@pytest.mark.parametrize("key,value", [
    ("schema", "B2-E13-dr04-authorization-record/2"), ("kind", "scientific_approval"), ("gate", "full_gpu_training"), ("stage", "DR-05"),
    ("observations", 18400), ("observations", 21350.0), ("basis", "exact_head_ci_green"), ("basis", "scientific_decision_ratification"),
])
def test_scientific_approval_or_ci_cannot_be_the_basis_of_a_compute_authorization(reference, key, value):
    plan = complete(reference)
    plan["authorization"][key] = value
    assert "authorization.basis" in failing(run(plan, reference))


@pytest.mark.parametrize("record", list(G.SCIENTIFIC_RECORDS))
def test_scientific_records_are_refused_as_the_compute_record(reference, record):
    plan = complete(reference)
    plan["authorization"]["record"] = record
    reference["record_files"][record] = plan["authorization"]["record_sha256"]
    assert "authorization.record" in failing(run(plan, reference))


@pytest.mark.parametrize("record", ["../../etc/passwd", "/etc/passwd", "docs/../../etc/passwd", "src/geoml/b2_e9_contract.py", "docs//x", "", None])
def test_record_paths_with_traversal_or_outside_docs_fail(reference, record):
    plan = complete(reference)
    plan["authorization"]["record"] = record
    assert "authorization.record" in failing(run(plan, reference))


def test_record_hash_must_match_the_committed_file(reference):
    plan = complete(reference)
    plan["authorization"]["record_sha256"] = H("other")
    assert "authorization.record" in failing(run(plan, reference))
    plan = complete(reference)
    reference["record_files"] = {}                           # the record is not a committed file at all
    assert "authorization.record" in failing(run(plan, reference))


@pytest.mark.parametrize("key", ["plan_fingerprint", "git_commit", "lock_fingerprint", "host_id", "working_storage_id", "backup_storage_id"])
def test_authorization_must_bind_this_plan_commit_lock_host_and_storage(reference, key):
    plan = complete(reference)
    plan["authorization"][key] = "0" * 64 if key.endswith("fingerprint") else "0" * 40 if key == "git_commit" else "other"
    assert "authorization.binding" in failing(run(plan, reference))


def test_authorization_does_not_survive_editing_the_plan_it_approved(reference):
    plan = complete(reference)
    plan["environment"]["thread_environment"]["OMP_NUM_THREADS"] = "3"       # edit after approval, fingerprint recomputed by a careful forger
    reference["environment"]["threads"]["OMP_NUM_THREADS"] = "3"
    finish(plan)
    assert "authorization.binding" in failing(run(plan, reference))


@pytest.mark.parametrize("mapping", [{"wall_hours": 30.0}, {"core_hours": 1.0}, {"working_disk_gib": 99.0}, {"backup_disk_gb": 1}])
def test_authorization_ceilings_must_equal_the_plan_ceilings(reference, mapping):
    plan = complete(reference)
    plan["authorization"]["ceilings"].update(mapping)
    assert "authorization.ceilings" in failing(run(plan, reference))


def test_ceilings_must_be_marked_as_recorded_when_an_authorization_exists(reference):
    plan = complete(reference)
    plan["ceilings_status"] = "PROPOSED_NOT_APPROVED"
    finish(plan)
    plan["authorization"]["plan_fingerprint"] = plan["plan_fingerprint"]
    assert "authorization.ceilings" in failing(run(plan, reference))


@pytest.mark.parametrize("grants,not_granted", [(["full_generation", "full_gpu_training"], None), (["full_generation", "gpu_probe"], None),
                                                (["full_loko_sweep"], None), ([], None), (None, ["gpu_probe"]), (None, [])])
def test_authorization_scope_is_generation_only(reference, grants, not_granted):
    plan = complete(reference)
    if grants is not None:
        plan["authorization"]["grants"] = grants
    if not_granted is not None:
        plan["authorization"]["does_not_grant"] = not_granted
    assert "authorization.scope" in failing(run(plan, reference))


def test_a_record_in_the_plan_is_not_a_gate(reference):
    plan = complete(reference)
    reference["gates"], reference["memo"] = gates_with_dr04(False)           # the readiness JSON still says NOT_AUTHORIZED
    assert "authorization.gate" in failing(run(plan, reference))


def test_gate_and_memorandum_twin_must_agree_and_match_the_record(reference):
    plan = complete(reference)
    reference["memo"]["decisions"]["full_generation"]["status"] = "NOT_AUTHORIZED"
    assert "authorization.gate" in failing(run(plan, reference))
    plan = complete(reference)
    reference["gates"]["decisions"]["full_generation"]["approval"]["approved_by"] = "someone-else"
    assert "authorization.gate" in failing(run(plan, reference))
    plan = complete(reference)
    reference["gates"]["decisions"]["full_generation"]["approval"]["wall_hours"] = 12
    assert "authorization.gate" in failing(run(plan, reference))


@pytest.mark.parametrize("gate", ["K18", "K17d", "OBS-CANCEL-2"])
def test_scientific_prerequisites_are_required_but_never_sufficient(reference, gate):
    plan = complete(reference)
    reference["gates"]["decisions"][gate]["status"] = "PENDING_RESEARCHER"
    assert "authorization.scientific_prerequisites" in failing(run(plan, reference))


def test_scientific_approval_green_ci_and_a_consistent_plan_without_a_record_stay_blocked(reference):
    plan = complete(reference)
    plan["authorization"] = None
    reference["gates"], reference["memo"] = gates_with_dr04(False)
    assert all(reference["gates"]["decisions"][k]["status"] == "APPROVED" for k in ("K18", "K17d", "OBS-CANCEL-2"))
    report = run(plan, reference)
    assert status(report)["authorization.dr04"] == G.BLOCKED and status(report)["release.evidence"] == G.PASS
    assert status(report)["scientific.ratified_no_execution"] == G.PASS and report["plan_status"] != G.DOCUMENT_OK


def test_the_real_gates_authorize_nothing_today():
    gates = json.loads((ROOT / pre.GATES_PATH).read_text())["decisions"]
    assert {k: gates[k]["status"] for k in ("full_generation", "full_gpu_training", "full_loko_sweep")} == {k: "NOT_AUTHORIZED" for k in
                                                                                                          ("full_generation", "full_gpu_training", "full_loko_sweep")}
    assert all(gates[k]["approval"] is None for k in ("full_generation", "full_gpu_training", "full_loko_sweep"))


# ---- identity: source, configuration, inventory, K17d --------------------------------------------------------------

def test_modified_source_file_hash_fails(reference):
    plan = complete(reference)
    name = next(iter(plan["source"]["files_sha256"]))
    plan["source"]["files_sha256"][name] = H("tampered")
    plan["source"]["source_tree_sha256"] = G.sha256_of(plan["source"]["files_sha256"])
    assert "source.files" in failing(run(finish(plan), reference))


def test_added_or_removed_source_file_fails(reference):
    plan = complete(reference)
    plan["source"]["files_sha256"]["src/geosim/new_module.py"] = H("new")
    plan["source"]["source_tree_sha256"] = G.sha256_of(plan["source"]["files_sha256"])
    assert "source.files" in failing(run(finish(plan), reference))
    plan = complete(reference)
    del plan["source"]["files_sha256"]["src/geosim/alpha.py"]
    plan["source"]["source_tree_sha256"] = G.sha256_of(plan["source"]["files_sha256"])
    assert "source.files" in failing(run(finish(plan), reference))


def test_source_tree_digest_must_match_the_file_map(reference):
    plan = complete(reference)
    plan["source"]["source_tree_sha256"] = H("wrong")
    assert "source.tree_digest" in failing(run(finish(plan), reference))


@pytest.mark.parametrize("name", list(pre.LOCKED_CONFIGS))
def test_each_locked_configuration_hash_is_checked(reference, name):
    plan = complete(reference)
    plan["source"]["configs_sha256"][name] = H("edited")
    assert "source.configs" in failing(run(finish(plan), reference))


@pytest.mark.parametrize("key,value", [("git_commit", "b" * 40), ("git_commit", "abc"), ("tree_clean", False), ("tree_clean", "yes"),
                                       ("generator_provenance_fingerprint", H("x")), ("known_request_fingerprint", H("y"))])
def test_commit_cleanliness_and_generator_identity(reference, key, value):
    plan = complete(reference)
    plan["source"][key] = value
    wrong = {"git_commit": "source.git", "tree_clean": "source.clean", "generator_provenance_fingerprint": "source.generator",
             "known_request_fingerprint": "source.known_request"}[key]
    assert wrong in failing(run(finish(plan), reference))


def test_dirty_reference_tree_fails_even_when_the_plan_claims_clean(reference):
    plan = complete(reference)
    reference["tree_clean"] = False
    assert "source.clean" in failing(run(plan, reference))


def test_parsed_physical_configuration_is_frozen(reference):
    plan = complete(reference)
    plan["source"]["parsed_config_sha256"]["b2_config"] = H("other physics")
    assert "source.generator" in failing(run(finish(plan), reference))


def inventory_mutations():
    return [("groups", lambda r: r.__setitem__("groups", r["groups"] + 1)), ("variants", lambda r: r.__setitem__("variants_per_group", 7)),
            ("observations", lambda r: r.__setitem__("observations", r["observations"] - 8)), ("first_group", lambda r: r.__setitem__("first_group", r["first_group"] + 1)),
            ("last_group", lambda r: r.__setitem__("last_group", r["last_group"] - 1)), ("shards", lambda r: r.__setitem__("shards", r["shards"] + 1)),
            ("role", lambda r: r.__setitem__("role", "val-calib" if r["role"] != "val-calib" else "train")),
            ("stage", lambda r: r.__setitem__("stage", "B2-base/1")), ("loss_bound", lambda r: r.__setitem__("max_loss_observations", 1))]


@pytest.mark.parametrize("label,change", inventory_mutations(), ids=[m[0] for m in inventory_mutations()])
@pytest.mark.parametrize("row", range(6))
def test_wrong_role_group_variant_or_shard_inventory_fails(reference, label, change, row):
    plan = complete(reference)
    change(plan["inventory"]["rows"][row])
    assert "plan.inventory" in failing(run(finish(plan), reference))


def test_inventory_structure_changes_fail(reference):
    for edit in (lambda p: p["inventory"]["rows"].pop(), lambda p: p["inventory"]["rows"].reverse(), lambda p: p["inventory"].__setitem__("total_observations", 21351),
                 lambda p: p["inventory"].__setitem__("groups_per_shard", 8), lambda p: p["inventory"].__setitem__("stage_order", ["test", "known", "matched"]),
                 lambda p: p["inventory"]["rows"].append(dict(p["inventory"]["rows"][0])), lambda p: p["inventory"].__setitem__("groups_per_shard", 4.0)):
        plan = complete(reference)
        edit(plan)
        assert "plan.inventory" in failing(run(finish(plan), reference))


@pytest.mark.parametrize("key,value", [("role_starts", {"train": 1, "val-select": 3100000, "val-calib": 3150000, "test": 3200000, "test-matched": 3300000}),
                                       ("role_counts", {"train": 1499, "val-select": 150, "val-calib": 150, "test": 500, "test-matched": 150}),
                                       ("groups_per_shard", 2), ("window_shards", 8), ("canceller_version", "obs-cancel/2"),
                                       ("known_protocol", "B2-base/1"), ("group_limit", 2), ("labels", ["clean"]), ("test_families", ["cid_overlay"]),
                                       ("protocol_contract_sha256", H("contract"))])
def test_frozen_seeds_roles_and_generator_assumptions_cannot_change(reference, key, value):
    plan = complete(reference)
    plan["generator_assumptions"][key] = value
    assert "plan.generator_assumptions" in failing(run(finish(plan), reference))


def test_stage_order_roots_and_modules_are_fixed(reference):
    plan = complete(reference)
    plan["stages"] = {k: plan["stages"][k] for k in ("test", "known", "matched")}
    assert "plan.stage_order" in failing(run(finish(plan), reference))
    plan = complete(reference)
    plan["stages"]["test"]["module"] = "geosim.b2_dataset"
    assert "plan.stage_options" in failing(run(finish(plan), reference))
    plan = complete(reference)
    plan["stages"]["matched"]["options"]["out"] = "test"                 # two stages sharing one root: role mixing
    assert "plan.stage_options" in failing(run(finish(plan), reference))
    plan = complete(reference)
    plan["stages"]["test"]["options"]["known"] = "matched"
    assert "plan.stage_options" in failing(run(finish(plan), reference))


@pytest.mark.parametrize("stage,option,value", [("known", "limit_groups", 2), ("known", "roles", ["train"]), ("known", "execute", True), ("test", "dry_run", False),
                                                ("matched", "workers", 8), ("known", "groups_per_shard", 8), ("known", "groups_per_shard", 4.0),
                                                ("known", "config", "configs/other.json"), ("test", "cancellation", "../cancellation.json"),
                                                ("known", "out", "/abs/known"), ("known", "out", "../known"), ("test", "known", "./known")])
def test_unknown_flags_wrong_values_and_unsafe_paths_in_stage_options_fail(reference, stage, option, value):
    plan = complete(reference)
    plan["stages"][stage]["options"][option] = value
    assert {"plan.stage_options", "plan.forbidden_key"} & set(failing(run(finish(plan), reference)))


def test_missing_stage_option_fails(reference):
    plan = complete(reference)
    del plan["stages"]["test"]["options"]["known"]
    assert "plan.stage_options" in failing(run(finish(plan), reference))


def test_modified_k17d_metadata_identity_fails(reference):
    changes = [("counts", {"headline": 500, "co_feed_missing": 36, "sensitivity": 464, "cross_feed_missing": 43, "missing_total": 79}),
               ("identity_sha256", H("x")), ("audit_sha256", H("y")), ("package_sha256", H("z")), ("fingerprints", {"headline_ids": H("a")}),
               ("source_sha256", {"src/geosim/b2_k17d.py": H("b")}), ("generator_rederived", False), ("observation_reads", 1),
               ("waveform_synthesis_calls", 3), ("execution_authorized", True), ("production_metadata_cross_check", "PASSED")]
    for key, value in changes:
        plan = complete(reference)
        plan["scientific"]["k17d_verification"][key] = value
        assert "scientific.k17d_verification" in failing(run(finish(plan), reference)), key
    plan = complete(reference)
    del plan["scientific"]["k17d_verification"]["counts"]
    assert "scientific.k17d_verification" in failing(run(finish(plan), reference))


@pytest.mark.parametrize("key,value", [("generator_rederived", False), ("observation_reads", 1), ("waveform_synthesis_calls", 2),
                                       ("execution_authorized", True), ("production_metadata_cross_check", "PASSED")])
def test_k17d_invariants_hold_even_if_plan_and_reference_agree_on_a_violation(reference, key, value):
    plan = complete(reference)
    reference["k17d_verification"][key] = value
    plan["scientific"]["k17d_verification"][key] = value                              # the two documents agree; the invariant still fails
    assert "scientific.k17d_verification" in failing(run(finish(plan), reference))


def test_incomplete_rederivation_in_the_reference_fails(reference):
    plan = complete(reference)
    reference["k17d_verification"]["generator_rederived"] = False
    plan["scientific"]["k17d_verification"]["generator_rederived"] = False
    assert "scientific.k17d_verification" in failing(run(finish(plan), reference))


def test_k17d_drift_from_the_ratified_bindings_fails(reference):
    plan = complete(reference)
    reference["decision_record"]["document"]["k17d_bindings"]["package_sha256"] = H("drift")
    assert "scientific.k17d_bindings" in failing(run(plan, reference))


def test_d8_counts_and_identity_hash_are_preserved(reference):
    for path, value in ((("counts", "headline"), 499), (("counts", "co_feed_missing"), 34), (("identity_sha256",), H("a")),
                        (("future_production_metadata_cross_check",), "NOT_REQUIRED"), (("choice",), "B")):
        plan = complete(reference)
        mutate(plan["scientific"]["d8_k17d"], path, value)
        assert "scientific.d8_identity" in failing(run(finish(plan), reference)), path


def test_d1_exposure_disclosure_is_preserved(reference):
    for path, value in ((("existing_test_pristine",), True), (("exposed_test_ids",), [3200000]), (("exposed_test_ids",), [3200000, 3200001, 3200002]),
                        (("exposed_matched_ids",), []), (("mandatory_exclusion_rows",), {"test": 500, "test-matched": 150}), (("choice",), "B")):
        plan = complete(reference)
        mutate(plan["scientific"]["d1_exposure"], path, value)
        assert "scientific.d1_exposure" in failing(run(finish(plan), reference)), path


def test_decision_register_hash_and_content_are_bound(reference):
    plan = complete(reference)
    plan["scientific"]["decision_record"]["sha256"] = H("edited register")
    assert "scientific.record" in failing(run(finish(plan), reference))
    plan = complete(reference)
    reference["decision_record"]["document"]["execution_authorized"] = True       # a register that itself authorizes execution is refused
    assert "scientific.ratified_no_execution" in failing(run(plan, reference))
    plan = complete(reference)
    reference["decision_record"]["document"]["compute_gates"]["full_generation"]["approval"] = {"approved_by": "x"}
    assert "scientific.ratified_no_execution" in failing(run(plan, reference))


def test_post_generation_obligations_cannot_be_dropped_or_softened(reference):
    for path, value in ((("k17d_production_metadata_cross_check", "status"), "NOT_REQUIRED"), (("k17d_production_metadata_cross_check", "must_agree"), []),
                        (("exposure_disclosure", "existing_test_pristine"), True), (("exposure_disclosure", "mandatory_exclusion_rows"), {}),
                        (("backup_checksum_verified_before_data_is_made_read_only",), False)):
        plan = complete(reference)
        mutate(plan["post_generation_obligations"], path, value)
        assert "obligations.post_generation" in failing(run(finish(plan), reference)), path
    plan = complete(reference)
    del plan["post_generation_obligations"]["exposure_disclosure"]
    assert "obligations.post_generation" in failing(run(finish(plan), reference))


# ---- environment, host, resources, backup ----------------------------------------------------------------------------

@pytest.mark.parametrize("edit", [lambda e: e.pop("python"), lambda e: e.pop("numpy"), lambda e: e.pop("scipy"), lambda e: e.pop("thread_environment"),
                                  lambda e: e.__setitem__("python", ">=3.12"), lambda e: e.__setitem__("numpy", "latest"), lambda e: e.__setitem__("scipy", "1.*"),
                                  lambda e: e.__setitem__("python", ""), lambda e: e.__setitem__("numpy", 2.5),
                                  lambda e: e["thread_environment"].pop("OMP_NUM_THREADS"), lambda e: e["thread_environment"].pop("PYTHONHASHSEED"),
                                  lambda e: e["thread_environment"].__setitem__("MKL_NUM_THREADS", "0"), lambda e: e["thread_environment"].__setitem__("OPENBLAS_NUM_THREADS", "two"),
                                  lambda e: e["thread_environment"].__setitem__("PYTHONHASHSEED", None), lambda e: e["thread_environment"].__setitem__("EXTRA", "1")])
def test_missing_or_unpinned_environment_fails(reference, edit):
    plan = complete(reference)
    edit(plan["environment"])
    assert "environment.pin" in failing(run(finish(plan), reference))


def test_environment_must_equal_the_environment_it_was_checked_in(reference):
    plan = complete(reference)
    plan["environment"]["numpy"] = "2.5.5"
    assert "environment.matches_host" in failing(run(finish(plan), reference))
    plan = complete(reference)
    plan["environment"]["thread_environment"]["OMP_NUM_THREADS"] = "4"
    assert "environment.matches_host" in failing(run(finish(plan), reference))


def test_lock_is_required_verified_and_bound(reference):
    plan = complete(reference)
    reference["lock"], plan["lock"] = None, None
    assert "lock.document" in blocked(run(finish(plan), reference))
    plan = complete(reference)
    reference["lock_problems"] = ["source file modified: src/geosim/alpha.py"]
    assert "lock.verify" in failing(run(plan, reference))
    plan = complete(reference)
    plan["lock"]["lock_fingerprint"] = H("another lock")
    assert "lock.verify" in failing(run(finish(plan), reference))
    plan = complete(reference)
    plan["lock"] = {"lock_fingerprint": "short"}
    assert "lock.shape" in failing(run(finish(plan), reference))


@pytest.mark.parametrize("key,value", [("wall_hours", 10.0), ("core_hours", 5.0), ("min_free_disk_gib", 10.0), ("max_rss_gib", 0.1), ("host_ram_gib", 4.0),
                                       ("backup_disk_gb", 3), ("wall_hours", 100.0), ("core_hours", 100.0), ("max_rss_gib", 8.0), ("max_failed_attempts_per_stage", 9),
                                       ("max_interruptions_per_stage", 200), ("max_interruptions_per_stage", 2.5), ("grace_s", 6000.0),
                                       ("wall_hours", 0), ("wall_hours", -1), ("wall_hours", True), ("core_hours", "42")])
def test_insufficient_or_unbounded_ceilings_fail(reference, key, value):
    plan = complete(reference)
    plan["ceilings"][key] = value
    assert {"ceilings.explicit", "ceilings.values"} & set(failing(run(finish(plan), reference)))


def test_ceilings_need_every_explicit_key_and_no_extra(reference):
    for edit in (lambda c: c.pop("backup_disk_gb"), lambda c: c.pop("host_ram_gib"), lambda c: c.__setitem__("gpu_hours", 6)):
        plan = complete(reference)
        edit(plan["ceilings"])
        assert "ceilings.shape" in failing(run(finish(plan), reference))
    plan = complete(reference)
    plan["ceilings_status"] = "AUTHORIZED"
    assert "ceilings.status" in failing(run(finish(plan), reference))


def test_estimated_requirements_are_the_documented_arithmetic():
    assert G.required_free_gib(21350, 25) == pytest.approx(33.88, abs=0.01)
    estimate = G.estimated_hours()
    assert estimate["observations"] == 21350 and estimate["wall_high_hours"] == pytest.approx(30.07, abs=0.01)     # preflight rate (CID at 8 s)
    assert estimate["wall_high_hours"] > 21350 * 5.0 / 3600 == pytest.approx(29.65, abs=0.01)                      # the supervisor's flat rate is lower
    assert estimate["core_high_hours"] == pytest.approx(34.45, abs=0.02)
    proposals = G.proposed_ceilings()
    assert proposals["wall_hours"] == 36.0 and proposals["core_hours"] == 42.0 and proposals["backup_disk_gb"] == 9 and proposals["host_ram_gib"] == 8


def test_proposed_ceilings_stay_proposals(reference):
    plan = G.make_template(reference)
    assert plan["ceilings_status"] == "PROPOSED_NOT_APPROVED" and plan["authorization"] is None
    assert G.proposed_ceilings() == plan["ceilings"] and pre.PROPOSED_CEILINGS["authorized"] is False


@pytest.mark.parametrize("edit,expected", [
    (lambda h: h["inventory"]["disks"][0].__setitem__("free_gib", 30.0), "host.disk"),
    (lambda h: h["inventory"]["disks"][0].__setitem__("free_gib", 33.8), "host.disk"),
    (lambda h: h["inventory"]["memory"].__setitem__("available_gib", 6.0), "host.ram"),
    (lambda h: h["inventory"]["memory"].__setitem__("cgroup_limit_gib", 4.0), "host.ram"),
    (lambda h: h["inventory"]["memory"].__setitem__("available_gib", None), "host.ram"),
    (lambda h: h["inventory"]["cpu"].__setitem__("logical_cpus", 2), "host.cpu"),
    (lambda h: h["inventory"]["cpu"].__setitem__("cgroup_cpu_quota", 1.5), "host.cpu"),
    (lambda h: h.__setitem__("role", "training"), "host.inventory"), (lambda h: h.__setitem__("read_only", False), "host.inventory"),
    (lambda h: h.__setitem__("gpu_computation_performed", True), "host.inventory"), (lambda h: h.__setitem__("schema", "other"), "host.inventory"),
    (lambda h: h["inventory"].pop("cpu"), "host.inventory")])
def test_host_resource_shortfalls_fail(reference, edit, expected):
    plan = complete(reference)
    edit(plan["host"]["inventory"])
    assert expected in failing(run(finish(plan), reference))


def test_exactly_enough_disk_passes_and_one_gib_less_fails(reference):
    need = G.required_free_gib(21350, 25)
    plan = complete(reference)
    plan["host"]["inventory"]["inventory"]["disks"][0]["free_gib"] = need + 0.01
    assert "host.disk" not in failing(run(finish(plan), reference))
    plan["host"]["inventory"]["inventory"]["disks"][0]["free_gib"] = need - 1
    assert "host.disk" in failing(run(finish(plan), reference))


def test_a_higher_declared_reserve_raises_the_required_free_space(reference):
    plan = complete(reference)
    plan["ceilings"]["min_free_disk_gib"] = 60.0
    plan["host"]["inventory"]["inventory"]["disks"][0]["free_gib"] = 50.0                           # enough for the 25 GiB proposal (33.9 needed), not for a 60 GiB reserve (68.9 needed)
    assert "host.disk" in failing(run(finish(plan), reference))


def test_backup_on_the_same_device_fails(reference):
    plan = complete(reference)
    plan["host"]["inventory"]["inventory"]["disks"][1]["device"] = 11
    assert "backup.device" in failing(run(finish(plan), reference))


def test_backup_with_the_same_declared_storage_id_fails(reference):
    plan = complete(reference)
    plan["backup"]["storage_id"] = plan["working"]["storage_id"]
    assert "backup.device" in failing(run(finish(plan), reference))


@pytest.mark.parametrize("working,backup", [("/data/b2", "/data/b2/backup"), ("/data/b2/run", "/data/b2"), ("/data/b2", "/data/b2")])
def test_nested_or_identical_roots_fail(reference, working, backup):
    plan = complete(reference)
    plan["working"]["root"], plan["backup"]["root"] = working, backup
    disks = plan["host"]["inventory"]["inventory"]["disks"]
    disks[0]["path"], disks[1]["path"] = working, backup
    assert "backup.device" in failing(run(finish(plan), reference))


def test_backup_capacity_and_free_space_are_checked(reference):
    plan = complete(reference)
    plan["backup"]["capacity_gb"] = 5
    assert "backup.capacity" in failing(run(finish(plan), reference))
    plan = complete(reference)
    plan["backup"]["capacity_gb"] = 5000                                  # claims more than the device has
    assert "backup.capacity" in failing(run(finish(plan), reference))
    plan = complete(reference)
    plan["host"]["inventory"]["inventory"]["disks"][1]["free_gib"] = 2.0
    assert "backup.capacity" in failing(run(finish(plan), reference))


def test_inventory_must_describe_both_declared_roots(reference):
    plan = complete(reference)
    plan["host"]["inventory"]["inventory"]["disks"].pop()
    assert "backup.device" in failing(run(finish(plan), reference))
    plan = complete(reference)
    plan["working"]["root"] = "/elsewhere/b2"
    assert "backup.device" in failing(run(finish(plan), reference))


@pytest.mark.parametrize("root", ["/data/../etc", "data/b2", "/data/b2/", "/data//b2", "/data/./b2", "/", "/x", "/data/b2\x00", "", None, 5, "/" + "a/" * 3000])
def test_unsafe_working_roots_fail(reference, root):
    plan = complete(reference)
    plan["working"]["root"] = root
    assert "plan.paths_host" in failing(run(finish(plan), reference))


@pytest.mark.parametrize("root", ["/mnt/../backup", "backup", "/mnt/backup/", "/mnt//backup", None])
def test_unsafe_backup_roots_fail(reference, root):
    plan = complete(reference)
    plan["backup"]["root"] = root
    assert "plan.paths_host" in failing(run(finish(plan), reference))


def test_first_shard_gate_and_stop_rules_are_fixed(reference):
    for edit in (lambda t: t.__setitem__("enabled", False), lambda t: t.__setitem__("band_s_per_observation", [0.1, 100.0]), lambda t: t.__setitem__("tolerance", 2.0),
                 lambda t: t.__setitem__("gate_shards", 4), lambda t: t.pop("startup_s")):
        plan = complete(reference)
        edit(plan["timing"])
        assert "timing.first_shard" in failing(run(finish(plan), reference))
    for key, value in (("on_damaged_committed_shard", "ignore"), ("cleanup_may_delete_evidence", True), ("max_failed_attempts_per_stage", 50),
                       ("resume_requires_identical_request_source_environment", False), ("orphan_shard_files", "delete"), ("on_first_shard_timing_gate_failure", "continue")):
        plan = complete(reference)
        plan["stop_rules"][key] = value
        assert "stop_rules.defined" in failing(run(finish(plan), reference)), key


def test_release_evidence_must_refer_to_the_exact_plan_head(reference):
    for path, value in ((("independent_review", "reviewed_head"), "c" * 40), (("independent_review", "open_material_findings"), 1), (("exact_head_ci", "head_sha"), "c" * 40),
                        (("exact_head_ci", "conclusion"), "failure"), (("self_asserted",), False), (("independent_review", "path"), "../review.md")):
        plan = complete(reference)
        mutate(plan["release_evidence"], path, value)
        assert "release.evidence" in failing(run(finish(plan), reference)), path
    plan = complete(reference)
    plan["release_evidence"] = None
    assert "release.evidence" in blocked(run(finish(plan), reference))


# ---- execution and cap-bypass attempts ----------------------------------------------------------------------------------

@pytest.mark.parametrize("key", sorted(G.FORBIDDEN_KEYS))
def test_any_execution_launcher_callback_or_group_limit_field_is_refused(reference, key):
    plan = complete(reference)
    plan["stages"]["known"]["options"][key] = True
    assert "plan.forbidden_key" in failing(run(finish(plan), reference))
    plan = complete(reference)
    plan["host"]["inventory"][key.upper()] = ["python", "-m", "geosim.b2_dataset"]            # case-insensitive, nested anywhere
    assert "plan.forbidden_key" in failing(run(finish(plan), reference))


def test_a_production_command_cannot_be_smuggled_in_as_a_top_level_field(reference):
    plan = complete(reference)
    plan["command"] = ["python", "-m", "geosim.b2_dataset", "--out", "known"]
    report = run(finish(plan), reference)
    assert "plan.forbidden_key" in failing(report) and "plan.shape" in failing(report)
    assert report["plan_status"] == "INCOMPLETE_OR_INCONSISTENT"


@pytest.mark.parametrize("mode", ["fixture", "production", "execute", "dry-run", "", None, 1])
def test_only_the_data_free_production_plan_mode_exists(reference, mode):
    plan = complete(reference)
    plan["mode"] = mode
    assert "plan.mode" in failing(run(finish(plan), reference))


@pytest.mark.parametrize("limit", [1, 2, 3, 12, 150, None])
def test_the_two_group_fixture_limit_cannot_be_bypassed_through_the_plan_or_the_supervisor(reference, limit, tmp_path):
    plan = complete(reference)
    plan["inventory"]["limit_groups"] = limit
    assert "plan.forbidden_key" in failing(run(finish(plan), reference))
    if limit is not None and limit > 2:
        with pytest.raises(sup.SupervisorError, match="--max-groups 1"):
            sup.build_plan(tmp_path, mode="fixture", max_groups=limit, groups_per_shard=1)
        with pytest.raises(sup.SupervisorError, match="--limit-groups"):
            sup.assert_bounded(["python", "-m", "geosim.b2_dataset", "--limit-groups", str(limit)])
    with pytest.raises(sup.SupervisorError, match="without --limit-groups"):
        sup.assert_bounded(["python", "-m", "geosim.b2_dataset", "--out", "known"])


def test_the_supervisor_production_path_still_refuses_to_build_a_command(tmp_path):
    production = sup.build_plan(tmp_path, mode="production", groups_per_shard=4)
    with pytest.raises(sup.SupervisorError, match="unbounded stage command"):
        sup.stage_argv("known", production, tmp_path)
    assert sup.PRODUCTION_LAUNCH_ENABLED is False and sup.FIXTURE_MAX_GROUPS == 2
    with pytest.raises(sup.SupervisorError, match="--max-groups"):
        sup.build_plan(tmp_path, mode="fixture", max_groups=None, groups_per_shard=1)


def test_e9_guard_is_unchanged_and_always_raises():
    for action in e9.ACTIONS:
        with pytest.raises(e9.ExecutionNotAuthorized):
            e9.guard_execution(action)
    with pytest.raises(e9.ContractError):
        e9.guard_execution("production_generation_now")


def test_a_changed_release_boundary_is_reported_as_a_failure_and_still_no_go(reference, monkeypatch):
    plan = complete(reference)
    monkeypatch.setattr(sup, "PRODUCTION_LAUNCH_ENABLED", True)
    report = run(plan, reference)
    assert report["plan_status"] == "INCOMPLETE_OR_INCONSISTENT" and report["production_launch_enabled"] is True
    assert {"release.launch_flag_changed"} <= {b["id"] for b in report["structural_blockers"]}


def test_a_removed_unbounded_command_refusal_is_reported(reference, monkeypatch):
    plan = complete(reference)
    monkeypatch.setattr(sup, "stage_argv", lambda *args, **kwargs: ["python", "-m", "geosim.b2_dataset"])
    report = run(plan, reference)
    assert "release.boundary_changed" in {b["id"] for b in report["structural_blockers"]} and report["plan_status"] == "INCOMPLETE_OR_INCONSISTENT"


def test_a_changed_guard_or_fixture_cap_is_reported(reference, monkeypatch):
    plan = complete(reference)
    monkeypatch.setattr(e9, "guard_execution", lambda action, **evidence: None)
    assert "release.e9_guard_changed" in {b["id"] for b in run(plan, reference)["structural_blockers"]}
    monkeypatch.undo()
    monkeypatch.setattr(sup, "FIXTURE_MAX_GROUPS", 12)
    cap = {b["id"]: b for b in run(plan, reference)["structural_blockers"]}["release.fixture_cap"]
    assert cap["status"] == G.FAIL


def test_the_command_line_has_no_way_to_execute_anything(tmp_path):
    for argv in (["run"], ["execute"], ["launch", "--plan", "x"], ["validate", "--plan", "x", "--execute"], ["status", "--production"],
                 ["status", "--limit-groups", "3"], ["template", "--run"], []):
        with pytest.raises(SystemExit) as stop:
            G.main(argv)
        assert stop.value.code == 2, argv
    assert not [n for n in dir(G) if n.lower().startswith(("run", "launch", "execute", "spawn", "start", "exec_", "popen", "build_argv", "stage_argv"))]


def test_module_source_has_no_process_creation_synthesis_or_gpu_surface():
    source = SCRIPT.read_text()
    tree = ast.parse(source)
    imported = {alias.name.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    imported |= {node.module.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}
    assert not imported & {"subprocess", "multiprocessing", "threading", "concurrent", "asyncio", "signal", "ctypes", "torch", "xgboost", "socket"}
    called = {node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "") for node in ast.walk(tree) if isinstance(node, ast.Call)}
    assert not called & {"Popen", "system", "execv", "execvp", "fork", "spawn", "run", "check_output", "check_call", "popen", "sample_scene", "simulate_dual",
                         "generate_b2_dataset", "generate_b2_test_dataset", "generate_b2_matched_dataset", "load", "loadtxt", "genfromtxt", "savez", "save"}
    for token in ("allow_tf32", "autocast", "cuda", "DataLoader", "--execute", "--limit-groups", "--production"):
        assert token not in source, token
    assigned = {t.id if isinstance(t, ast.Name) else t.attr for node in ast.walk(tree) if isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign))
                for t in (node.targets if isinstance(node, ast.Assign) else [node.target]) if isinstance(t, (ast.Name, ast.Attribute))}
    assert not assigned & {"PRODUCTION_LAUNCH_ENABLED", "FIXTURE_MAX_GROUPS", "PRODUCTION_CEILINGS", "DEFAULT_TIMING", "CAPS"}      # constants are read, never assigned


def test_validation_invokes_no_generator_process_waveform_or_array_loader(reference, decision_record, k17d_report, monkeypatch):
    from geosim import b2_dataset, b2_matched_dataset, b2_scenarios, b2_test_dataset

    def forbidden(name):
        def refuse(*args, **kwargs):
            raise AssertionError(f"{name} must not be called by plan validation")
        return refuse

    for owner, names in ((subprocess, ("Popen", "run", "call", "check_call", "check_output")), (os, ("system", "execv", "execve", "execvp", "fork", "spawnv", "popen")),
                         (b2_scenarios, ("simulate_dual", "sample_scene")), (b2_dataset, ("generate_b2_dataset", "sample_scene")),
                         (b2_test_dataset, ("generate_b2_test_dataset",)), (b2_matched_dataset, ("generate_b2_matched_dataset",)),
                         (sup, ("run_child", "default_launcher", "wrapper_launcher"))):
        for name in names:
            if hasattr(owner, name):
                monkeypatch.setattr(owner, name, forbidden(f"{owner.__name__}.{name}"))
    real_load = np.load

    def guarded_load(path, *args, **kwargs):
        assert "geosim/data" in str(path).replace("\\", "/"), f"observation array load attempted: {path}"
        return real_load(path, *args, **kwargs)
    monkeypatch.setattr(np, "load", guarded_load)
    plan = complete(reference)
    assert run(plan, reference)["plan_status"] == G.DOCUMENT_OK
    for broken in (None, [], {"schema": G.SCHEMA_PLAN}, G.make_template(reference)):
        run(broken, reference)
    calls, inner = [], fake_git(head="b" * 40)
    snapshot = G.collect_reference(rederive=False, git=lambda *a, **k: calls.append(a[2:]) or inner(*a, **k), evaluated_at=NOW,
                                   record_paths=["docs/../../etc/passwd", "/etc/passwd", "docs/plan/DURUM.md"])
    assert calls and all(call[0] in ("rev-parse", "status", "ls-files", "hash-object") for call in calls)
    assert snapshot["head"] == "b" * 40 and snapshot["tree_clean"] is True and snapshot["lock"] is None
    assert set(snapshot["record_files"]) == {"docs/plan/DURUM.md"}                     # traversal and absolute paths are never opened
    assert snapshot["k17d_verification"]["generator_rederived"] is False and snapshot["k17d_verification"]["waveform_synthesis_calls"] == 0


# ---- robustness against hostile or malformed documents -------------------------------------------------------------

HOSTILE = [None, 0, 1.5, True, "text", [], [1], {}, {"x": 1}, "", -1, 10 ** 30]


@pytest.mark.parametrize("key", G.PLAN_KEYS)
@pytest.mark.parametrize("value", HOSTILE, ids=lambda v: repr(v)[:12])
def test_every_section_survives_any_replacement_without_crashing_or_granting(reference, key, value):
    plan = complete(reference)
    plan[key] = copy.deepcopy(value)
    assert run(plan, reference)["plan_status"] == "INCOMPLETE_OR_INCONSISTENT"


@pytest.mark.parametrize("plan", [None, 0, "plan", [], [{"schema": G.SCHEMA_PLAN}], {}, {"schema": G.SCHEMA_PLAN}, {"a": {"b": {"command": 1}}}])
def test_non_plan_documents_are_failures_not_crashes(reference, plan):
    report = run(plan, reference)
    assert report["plan_status"] == "INCOMPLETE_OR_INCONSISTENT" and "plan.shape" in failing(report)


def test_unknown_top_level_and_nested_fields_fail(reference):
    plan = complete(reference)
    plan["note"] = "hello"
    assert "plan.shape" in failing(run(plan, reference))
    plan = complete(reference)
    plan["source"]["extra"] = 1
    assert "source.shape" in failing(run(finish(plan), reference))
    plan = complete(reference)
    plan["host"]["extra"] = 1
    assert "host.shape" in failing(run(finish(plan), reference))


def test_stale_plan_fingerprint_fails_after_any_edit(reference):
    plan = complete(reference)
    plan["environment"]["python"] = "3.12.15"
    assert "plan.fingerprint" in failing(run(plan, reference))                          # edited without re-fingerprinting
    assert G.plan_fingerprint(plan) != plan["plan_fingerprint"]
    plan = complete(reference)
    before = plan["plan_fingerprint"]
    plan["authorization"]["approved_by"] = "someone"
    assert G.plan_fingerprint(plan) == before                                           # the authorization is outside the fingerprint


def test_benchmark_complete_and_schema_are_fixed(reference):
    for key, value in (("benchmark_complete", True), ("schema", "B2-E13-generation-plan/2"), ("stage", "DR-05")):
        plan = complete(reference)
        plan[key] = value
        assert "plan.shape" in failing(run(finish(plan), reference))


def test_report_strings_stay_bounded_for_hostile_values(reference):
    plan = complete(reference)
    plan["source"]["files_sha256"] = {"x" * 100000: "y" * 100000}
    report = run(finish(plan), reference)
    assert len(json.dumps(report)) < 200_000


def test_load_plan_rejects_duplicate_keys_nan_and_oversized_files(tmp_path):
    for name, text in (("dup.json", '{"a": 1, "a": 2}'), ("nan.json", '{"a": NaN}'), ("inf.json", '{"a": 1e999}'), ("list.json", "[1]"), ("bad.json", "{")):
        path = tmp_path / name
        path.write_text(text)
        with pytest.raises(Exception):
            G._load_plan(path)
    big = tmp_path / "big.json"
    big.write_text('{"a": "' + "x" * (G.MAX_PLAN_BYTES + 10) + '"}')
    with pytest.raises(ValueError, match="larger than"):
        G._load_plan(big)
    ok = tmp_path / "ok.json"
    ok.write_text('{"a": 1}')
    assert G._load_plan(ok) == {"a": 1}


# ---- the real checkout (metadata files only) ---------------------------------------------------------------------------

def test_real_checkout_template_is_no_go_with_only_external_facts_missing(monkeypatch):
    fake = fake_git(head="d" * 40)
    monkeypatch.setenv("OMP_NUM_THREADS", "2")
    for name in ("OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        monkeypatch.setenv(name, "2")
    monkeypatch.setenv("PYTHONHASHSEED", "0")
    snapshot = G.collect_reference(rederive=False, git=fake, evaluated_at=NOW)
    plan = G.make_template(snapshot)
    snapshot["k17d_verification"]["generator_rederived"] = True                           # the live test below runs the complete re-derivation
    plan["scientific"]["k17d_verification"]["generator_rederived"] = True
    report = run(finish(plan), snapshot)
    assert failing(report) == [], [i for i in report["findings"] if i["status"] == G.FAIL]
    assert blocked(report) == ["authorization.dr04", "backup.device", "host.inventory", "lock.document", "release.evidence"]
    assert snapshot["gates"]["decisions"]["full_generation"]["status"] == "NOT_AUTHORIZED"
    assert [row["observations"] for row in plan["inventory"]["rows"]] == [12000, 1200, 1200, 4000, 2500, 450]
    assert sum(row["observations"] for row in plan["inventory"]["rows"]) == 21350


def test_real_checkout_k17d_rederivation_uses_metadata_only(monkeypatch):
    from geosim import b2_scenarios
    calls = []
    real = b2_scenarios.simulate_dual
    monkeypatch.setattr(b2_scenarios, "simulate_dual", lambda *a, **k: calls.append(1) or real(*a, **k))
    real_load = np.load
    monkeypatch.setattr(np, "load", lambda path, *a, **k: (_ for _ in ()).throw(AssertionError(f"array load {path}")) if "geosim/data" not in str(path) else real_load(path, *a, **k))
    snapshot = G.collect_reference(rederive=True, git=fake_git(head="d" * 40), evaluated_at=NOW)
    report = snapshot["k17d_verification"]
    assert report["generator_rederived"] is True and report["counts"]["headline"] == 500 and report["counts"]["co_feed_missing"] == 35
    assert report["production_metadata_cross_check"] == "NOT_RUN_REQUIRES_SEPARATE_AUTHORIZATION" and report["waveform_synthesis_calls"] == 0


def test_cli_exit_codes_are_exact_and_never_zero_for_validation(tmp_path, monkeypatch, reference):
    template = G.make_template(reference)
    monkeypatch.setattr(G, "collect_reference", lambda **kwargs: reference)
    out = tmp_path / "status.json"
    assert G.main(["status", "--out", str(out)]) == 4                                      # consistent-or-incomplete but never a failure: NO-GO
    assert json.loads(out.read_text())["verdict"] == "NO-GO"
    good = tmp_path / "good.json"
    good.write_text(json.dumps(template))
    assert G.main(["validate", "--plan", str(good), "--out", str(tmp_path / "r1.json")]) == 4
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(dict(template, mode="fixture")))
    assert G.main(["validate", "--plan", str(bad), "--out", str(tmp_path / "r2.json")]) == 3     # a FAIL finding
    plan = complete(reference)
    ok = tmp_path / "complete.json"
    ok.write_text(json.dumps(plan))
    assert G.main(["validate", "--plan", str(ok), "--out", str(tmp_path / "r3.json")]) == 4      # a consistent document is still NO-GO, not 0
    assert json.loads((tmp_path / "r3.json").read_text())["plan_status"] == G.DOCUMENT_OK
    assert G.main(["template", "--out", str(tmp_path / "t.json")]) == 0
    flipped = json.loads(json.dumps(template))
    monkeypatch.setattr(sup, "PRODUCTION_LAUNCH_ENABLED", True)
    assert G.main(["status", "--out", str(tmp_path / "r4.json")]) == 3                       # a changed structural boundary is a FAIL (exit 3), not 4
    assert flipped


def test_cli_status_is_no_go_exit_4_and_refuses_to_overwrite(tmp_path, monkeypatch):
    for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        monkeypatch.setenv(name, "2")
    monkeypatch.setenv("PYTHONHASHSEED", "0")
    out = tmp_path / "status.json"
    code = G.main(["status", "--out", str(out)])
    report = json.loads(out.read_text())
    assert code in (3, 4) and report["verdict"] == "NO-GO" and report["execution_permitted"] is False
    assert report["findings"] and {"authorization.dr04", "host.inventory"} <= {i["id"] for i in report["findings"] if i["status"] == G.BLOCKED}
    with pytest.raises(SystemExit) as stop:
        G.main(["status", "--out", str(out)])
    assert stop.value.code == 2
    template = tmp_path / "template.json"
    assert G.main(["template", "--out", str(template)]) == 0
    assert json.loads(template.read_text())["authorization"] is None
    plan_out = tmp_path / "validated.json"
    assert G.main(["validate", "--plan", str(template), "--out", str(plan_out)]) in (3, 4)
    assert json.loads(plan_out.read_text())["verdict"] == "NO-GO"


# ---- review round: committed inputs, approver-authored binding, scope, volatile storage, hostile input -----------------

def test_record_text_must_carry_the_approved_digest_host_expiry_and_approver(reference):
    for token in ("approved_plan_digest", "host_id", "expires_at", "approved_by"):
        plan = complete(reference)
        text = reference["record_texts"][RECORD]
        replacement = {"approved_plan_digest": plan["authorization"]["approved_plan_digest"], "host_id": plan["authorization"]["host_id"],
                       "expires_at": plan["authorization"]["expires_at"], "approved_by": plan["authorization"]["approved_by"]}[token]
        reference["record_texts"][RECORD] = text.replace(replacement, "redacted")
        assert "authorization.record_content" in failing(run(plan, reference)), token
    plan = complete(reference)
    del reference["record_texts"][RECORD]
    assert "authorization.record_content" in failing(run(plan, reference))


def test_approved_plan_digest_changes_with_the_design_but_not_with_the_commit_or_lock(reference):
    plan = complete(reference)
    base = G.approved_plan_digest(plan)
    for change in (lambda p: p["ceilings"].__setitem__("wall_hours", 35.0), lambda p: p["host"].__setitem__("host_id", "other"),
                   lambda p: p["working"].__setitem__("root", "/data/other"), lambda p: p["backup"].__setitem__("storage_id", "disk-C"),
                   lambda p: p["environment"].__setitem__("numpy", "2.5.5"), lambda p: p["stages"]["known"]["options"].__setitem__("groups_per_shard", 8)):
        changed = complete(reference)
        change(changed)
        assert G.approved_plan_digest(changed) != base
    for change in (lambda p: p["source"].__setitem__("git_commit", "c" * 40), lambda p: p.__setitem__("lock", {"lock_fingerprint": H("z")}),
                   lambda p: p["host"].__setitem__("inventory", host_report()), lambda p: p["source"]["configs_sha256"].clear()):
        changed = complete(reference)
        change(changed)
        assert G.approved_plan_digest(changed) == base


def test_a_stale_digest_in_the_authorization_fails_binding(reference):
    plan = complete(reference)
    plan["authorization"]["approved_plan_digest"] = H("older design")
    assert "authorization.binding" in failing(run(plan, reference))


def test_record_hash_equal_to_a_scientific_record_is_refused_even_under_another_path(reference):
    plan = complete(reference)
    plan["authorization"]["record_sha256"] = SCIENTIFIC_HASHES[0]
    reference["record_files"][RECORD] = SCIENTIFIC_HASHES[0]
    assert "authorization.record" in failing(run(plan, reference))


def test_authorization_validity_window_and_register_date(reference):
    plan = complete(reference)
    plan["authorization"]["approved_at"] = "2026-10-01T00:00:00Z"                    # before the E12 register
    plan["authorization"]["expires_at"] = "2026-10-20T00:00:00Z"
    assert "authorization.provenance" in failing(run(plan, reference))
    plan = complete(reference)
    plan["authorization"]["expires_at"] = "2026-12-31T00:00:00Z"                     # longer than 30 days
    assert "authorization.provenance" in failing(run(plan, reference))
    plan = complete(reference)
    plan["authorization"]["expires_at"] = NOW                                         # expires exactly now: still valid (<=)
    assert "authorization.provenance" not in failing(run(plan, reference))
    plan["authorization"]["expires_at"] = "2026-10-30T11:59:59+00:00"
    assert "authorization.provenance" in failing(run(plan, reference))
    plan = complete(reference)
    plan["authorization"]["approved_at"] = NOW                                        # approved exactly now: not yet in the past (<)
    assert "authorization.provenance" in failing(run(plan, reference))


@pytest.mark.parametrize("name", list(G.INPUT_FILES))
def test_uncommitted_or_untracked_inputs_fail(reference, name):
    plan = complete(reference)
    reference["committed_inputs"][name] = False
    assert "source.committed_inputs" in failing(run(plan, reference))


def test_committed_check_requires_tracked_regular_file_equal_to_head(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "r.md").write_text("record")
    (tmp_path / "docs" / "link.md").symlink_to(tmp_path / "docs" / "r.md")
    assert G._committed(fake_git(), tmp_path, "docs/r.md") is True
    assert G._committed(fake_git(blob_ok=False), tmp_path, "docs/r.md") is False             # edited since HEAD
    assert G._committed(fake_git(), tmp_path, "docs/link.md") is False                       # symlink
    assert G._committed(fake_git(), tmp_path, "docs/absent.md") is False
    assert G._committed(fake_git(), tmp_path, "docs") is False                               # not a regular file

    def untracked(*args, repo=None):
        if "ls-files" in args:
            raise RuntimeError("not tracked")
        return fake_git()(*args, repo=repo)
    assert G._committed(untracked, tmp_path, "docs/r.md") is False


def test_a_dirty_or_untracked_working_tree_is_not_clean(monkeypatch):
    snapshot = G.collect_reference(rederive=False, git=fake_git(dirty="?? scripts/new.py"), evaluated_at=NOW)
    assert snapshot["tree_clean"] is False
    snapshot = G.collect_reference(rederive=False, git=fake_git(head="unknown-no-git"), evaluated_at=NOW)
    assert snapshot["tree_clean"] is True and not G.HEX40.fullmatch(snapshot["head"])        # an unusable head is caught by source.git


def test_unknown_head_fails_source_git(reference):
    plan = complete(reference)
    reference["head"] = plan["source"]["git_commit"] = "unknown"
    assert "source.git" in failing(run(finish(plan), reference))


def test_checkout_changing_during_collection_is_refused():
    heads = iter(["a" * 40, "b" * 40])                                                    # HEAD is read once per snapshot
    inner = fake_git()

    def moving(*args, repo=None):
        if args[2:4] == ("rev-parse", "HEAD"):
            return next(heads)
        return inner(*args, repo=repo)
    with pytest.raises(ValueError, match="changed while the reference was collected"):
        G.collect_reference(rederive=False, git=moving, evaluated_at=NOW)


@pytest.mark.parametrize("key", ["tools_sha256", "records_sha256"])
def test_tool_and_record_hashes_are_bound(reference, key):
    plan = complete(reference)
    name = sorted(plan["source"][key])[0]
    plan["source"][key][name] = H("edited")
    assert {"tools_sha256": "source.tools", "records_sha256": "source.records"}[key] in failing(run(finish(plan), reference))


def test_the_supervisor_view_and_scientific_gates_are_required(reference):
    plan = complete(reference)
    reference["gates"]["decisions"]["K18"]["approval"] = None
    report = run(plan, reference)
    assert {"authorization.supervisor_view", "authorization.scientific_prerequisites"} <= set(failing(report))
    plan = complete(reference)
    reference["memo"]["decisions"]["K18"]["status"] = "PENDING_RESEARCHER"
    assert "authorization.scientific_prerequisites" in failing(run(plan, reference))
    plan = complete(reference)
    reference["gates"]["decisions"]["K17d"]["approval"]["approved_by"] = "someone-else"
    assert "authorization.scientific_prerequisites" in failing(run(plan, reference))


@pytest.mark.parametrize("gate", ["full_gpu_training", "full_loko_sweep"])
@pytest.mark.parametrize("where", ["gates", "memo"])
def test_other_compute_gates_must_not_be_approved_while_dr04_is_validated(reference, gate, where):
    plan = complete(reference)
    reference[where]["decisions"][gate]["status"] = "AUTHORIZED"
    assert "authorization.scope_isolation" in failing(run(plan, reference))


def test_ceilings_cannot_claim_a_record_that_is_absent(reference):
    plan = G.make_template(reference)
    plan["ceilings_status"] = G.CEILINGS_STATUS[1]
    assert "ceilings.status" in failing(run(finish(plan), reference))


def test_register_without_null_compute_approvals_is_not_ratification_only(reference):
    plan = complete(reference)
    del reference["decision_record"]["document"]["compute_gates"]
    assert "scientific.ratified_no_execution" in failing(run(plan, reference))
    plan = complete(reference)
    reference["decision_record"]["document"]["compute_gates"] = {"full_generation": {"status": "NOT_AUTHORIZED"}}     # approval key absent
    assert "scientific.ratified_no_execution" in failing(run(plan, reference))


def test_k17d_bindings_must_exist_in_the_register(reference):
    plan = complete(reference)
    reference["decision_record"]["document"].pop("k17d_bindings")
    plan["scientific"]["k17d_verification"].pop("package_sha256")
    reference["k17d_verification"].pop("package_sha256")
    assert "scientific.k17d_bindings" in failing(run(plan, reference))                    # None == None no longer passes


def test_independent_inventory_baseline_is_enforced(reference, monkeypatch):
    plan = complete(reference)
    monkeypatch.setattr(pre, "PLAN_TOTAL", 21351)
    assert "plan.inventory" in failing(run(plan, reference)) or "plan.inventory_independent" in failing(run(plan, reference))
    monkeypatch.undo()
    monkeypatch.setattr(pre, "PLAN_INVENTORY", (("B2-feat/1", "train", 1501, 8, 12008),) + pre.PLAN_INVENTORY[1:])
    assert "plan.inventory_independent" in failing(run(complete(reference), reference))


@pytest.mark.parametrize("working,backup", [("/data/b2", "/dev/shm/b2"), ("/dev/shm/b2", "/mnt/backup/b2"), ("/proc/b2", "/sys/b2"), ("/tmp/b2", "/mnt/backup/b2"),
                                            ("/data/b2", "/run/backup"), ("/data/b2", "/var/tmp/backup")])
def test_volatile_trees_are_refused_for_both_roots(reference, working, backup):
    plan = complete(reference)
    plan["working"]["root"], plan["backup"]["root"] = working, backup
    disks = plan["host"]["inventory"]["inventory"]["disks"]
    disks[0].update(path=working, queried=working)
    disks[1].update(path=backup, queried=backup)
    assert "plan.paths_host" in failing(run(finish(plan), reference))


@pytest.mark.parametrize("working_fs,backup_fs,expected", [("tmpfs", "ext4", "host.filesystems"), ("xfs", "tmpfs", "host.filesystems"), ("xfs", "overlay", "host.filesystems"),
                                                           ("xfs", "ramfs", "host.filesystems"), ("xfs", None, "host.filesystems"), (None, "ext4", "host.filesystems"),
                                                           ("xfs", 7, "host.filesystems")])
def test_filesystem_types_must_be_reported_and_durable(reference, working_fs, backup_fs, expected):
    plan = complete(reference)
    disks = plan["host"]["inventory"]["inventory"]["disks"]
    disks[0]["fstype"], disks[1]["fstype"] = working_fs, backup_fs
    assert expected in failing(run(finish(plan), reference))
    plan = complete(reference)
    del plan["host"]["inventory"]["inventory"]["disks"][1]["fstype"]
    assert "host.filesystems" in failing(run(finish(plan), reference))


def test_roots_must_be_measured_themselves_not_an_ancestor(reference):
    plan = complete(reference)
    plan["host"]["inventory"]["inventory"]["disks"][1]["queried"] = "/mnt/backup"
    assert "host.roots_exist" in failing(run(finish(plan), reference))


def test_inventory_must_describe_the_declared_host_and_pins(reference):
    mutations = [lambda i: i.__setitem__("node", "other-host"), lambda i: i.__setitem__("python", "2.7.0"), lambda i: i["libraries"].__setitem__("numpy", "0.1"),
                 lambda i: i["libraries"].__setitem__("scipy", "0.1"), lambda i: i["environment"].__setitem__("OMP_NUM_THREADS", "16"),
                 lambda i: i["environment"].__setitem__("PYTHONHASHSEED", "1"), lambda i: i.__setitem__("collected_at", "2026-09-01T00:00:00+00:00"),
                 lambda i: i.__setitem__("collected_at", "2026-10-31T00:00:00+00:00"), lambda i: i.__setitem__("collected_at", "not-a-time"),
                 lambda i: i.pop("collected_at"), lambda i: i.pop("node")]
    for change in mutations:
        plan = complete(reference)
        change(plan["host"]["inventory"]["inventory"])
        assert "host.identity" in failing(run(finish(plan), reference))
    for key, value in (("production_authorized", True), ("benchmark_complete", True)):
        plan = complete(reference)
        plan["host"]["inventory"][key] = value
        assert "host.inventory" in failing(run(finish(plan), reference))


def test_exact_boundaries_of_cpu_ram_and_device_identity(reference):
    plan = complete(reference)
    inventory = plan["host"]["inventory"]["inventory"]
    inventory["cpu"].update(logical_cpus=4, schedulable_cpus=4)
    inventory["memory"].update(available_gib=8.0)
    report = run(finish(plan), reference)
    assert "host.cpu" not in failing(report) and "host.ram" not in failing(report)                  # the very profile passes
    inventory["cpu"].update(logical_cpus=3, schedulable_cpus=3)
    inventory["memory"].update(available_gib=7.99)
    report = run(finish(plan), reference)
    assert {"host.cpu", "host.ram"} <= set(failing(report))
    plan = complete(reference)
    plan["host"]["inventory"]["inventory"]["disks"][0]["device"] = True                              # a bool is not a device id
    plan["host"]["inventory"]["inventory"]["disks"][1]["device"] = False
    assert "backup.device" in failing(run(finish(plan), reference))


def test_hostile_depth_is_a_finding_not_a_crash(reference):
    plan = complete(reference)
    nested = value = []
    for _ in range(G.MAX_DEPTH + 5):
        inner = []
        value.append(inner)
        value = inner
    plan["host"]["inventory"]["deep"] = nested
    report = run(plan, reference)
    assert failing(report) == ["plan.depth"]
    plan = complete(reference)
    chain = {}
    cursor = chain
    for _ in range(3000):                                                                            # beyond the interpreter's recursion limit
        cursor["a"] = {}
        cursor = cursor["a"]
    plan["host"]["inventory"]["deep"] = chain
    assert failing(run(plan, reference)) == ["plan.depth"]


def test_report_fingerprint_is_echoed_only_when_it_is_a_digest(reference):
    plan = complete(reference)
    assert run(plan, reference)["plan_fingerprint"] == plan["plan_fingerprint"]
    plan["plan_fingerprint"] = "x" * 100000
    report = run(plan, reference)
    assert report["plan_fingerprint"] is None and len(json.dumps(report)) < 100_000


def test_report_counts_include_the_structural_blockers_and_bind_the_reference(reference):
    report = run(G.make_template(reference), reference)
    assert report["counts"]["BLOCKED"] == 5 + 4 and report["counts"]["FAIL"] == 0
    assert report["reference_sha256"] == G.sha256_of(reference) and report["plan_status"] == "INCOMPLETE_OR_INCONSISTENT"
    other = copy.deepcopy(reference)
    other["head"] = "e" * 40
    assert run(G.make_template(reference), other)["reference_sha256"] != report["reference_sha256"]


def test_load_plan_is_bounded_and_survives_hostile_nesting(tmp_path):
    deep = tmp_path / "deep.json"
    deep.write_text("[" * 200000 + "]" * 200000)
    with pytest.raises(ValueError):
        G._load_plan(deep)
    if Path("/dev/zero").exists():
        with pytest.raises(ValueError, match="larger than"):
            G._load_plan("/dev/zero")                                                                 # bounded read, not an endless one


def test_cli_turns_bad_input_into_exit_2_never_a_traceback(tmp_path, monkeypatch, reference):
    monkeypatch.setattr(G, "collect_reference", lambda **kwargs: reference)
    for name, text in (("deep.json", "[" * 100000 + "]" * 100000), ("dup.json", '{"a": 1, "a": 2}'), ("nan.json", "NaN"), ("empty.json", "")):
        path = tmp_path / name
        path.write_text(text)
        with pytest.raises(SystemExit) as stop:
            G.main(["validate", "--plan", str(path)])
        assert stop.value.code == 2, name
    with pytest.raises(SystemExit) as stop:
        G.main(["validate", "--plan", str(tmp_path / "missing.json")])
    assert stop.value.code == 2
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps(G.make_template(reference)))
    lock = tmp_path / "lock.json"
    lock.write_text(json.dumps({"schema": "B2-production-lock/1", "environment": 5, "source_sha256": [], "lock_fingerprint": "x"}))
    monkeypatch.undo()
    with pytest.raises(SystemExit) as stop:
        G.main(["validate", "--plan", str(plan), "--lock", str(lock)])                               # malformed lock content
    assert stop.value.code == 2


def test_fstype_of_reads_the_longest_mount_prefix():
    mountinfo = "\n".join(["22 1 8:1 / / rw - ext4 /dev/sda1 rw", "30 22 0:25 / /dev/shm rw - tmpfs tmpfs rw", "31 22 0:26 / /mnt/back\\040up rw - xfs /dev/sdb1 rw",
                           "32 22 0:27 / /mnt rw - nfs4 server:/x rw"])
    read = lambda path: mountinfo                                                                  # noqa: E731
    assert G.host_inventory.fstype_of("/dev/shm/x", read=read) == "tmpfs"
    assert G.host_inventory.fstype_of("/home/user", read=read) == "ext4"
    assert G.host_inventory.fstype_of("/mnt/back up/data", read=read) == "xfs"
    assert G.host_inventory.fstype_of("/mnt/other", read=read) == "nfs4"
    assert G.host_inventory.fstype_of("/home/user", read=lambda path: None) is None
    assert G.host_inventory.disk_facts(["/dev/shm"])[0]["fstype"] in (None, "tmpfs") and "fstype" in G.host_inventory.disk_facts(["/nonexistent/path"])[0]
    facts = G.host_inventory.collect(["/nonexistent/path"], facts={"cpu": {"x": 1}, "memory": {"x": 1}, "disks": [{"x": 1}], "gpu": {"x": 1}, "libraries": {"x": 1}})
    assert facts["node"] and _instant_ok(facts["collected_at"])


def _instant_ok(text):
    return G._instant(text) is not None

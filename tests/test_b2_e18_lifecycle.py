"""E18 synthetic executor lifecycle over fabricated bytes: state machine, stage isolation, trusted evidence, resource supervision.

All keys, records, devices and shards are fabricated and live in temporary directories. Nothing here generates waveforms, trains a
model, touches a GPU or starts a process, and no test can make the lifecycle reach real generation: its only real-work entry is
``production_gate`` and it always ends BLOCKED.
"""
import ast
import copy
import dataclasses
import json
import os
from pathlib import Path
import re
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))
import e18_support as T  # noqa: E402
from test_b2_e17_evidence import custody, integrated  # noqa: E402,F401
from e18_support import admitted, complete, known, make, scratch  # noqa: E402,F401
from test_b2_e13_generation_plan import decision_record, k17d_report, reference  # noqa: E402,F401

M, X, L, I, D, S, E, P, G, C = T.M, T.X, T.L, T.M.I, T.M.D, T.M.S, T.M.E, T.M.P, T.M.G, T.C


# ---- state machine ---------------------------------------------------------------------------------------------------

def test_there_is_no_production_running_state_and_halts_are_terminal():
    assert set(M.STATES) == set(M.TRANSITIONS)
    assert [s for s in M.STATES if "RUNNING" in s] == ["SYNTHETIC_STAGE_RUNNING"]
    assert not [s for s in M.STATES if any(word in s for word in ("PRODUCTION", "LAUNCH", "EXECUT", "GENERAT"))]
    assert M.TRANSITIONS["STOPPED"] == set() and M.TRANSITIONS["QUARANTINED"] == set()
    assert all(targets <= set(M.STATES) for targets in M.TRANSITIONS.values())
    assert all("SYNTHETIC" in state for state in M.STATES if state.startswith("SYNTHETIC"))


@pytest.mark.parametrize("method", ["check_admission", "run_stage", "verify_stage", "backup_stage", "complete_stage", "retry"])
def test_operations_out_of_order_raise_without_side_effects(make, method):
    life, profile, _ = make()
    before = (life.state, life.summary(), life.events)
    with pytest.raises(M.InvalidTransition):
        getattr(life, method)()
    assert (life.state, life.summary(), life.events) == before
    assert not life._ledger_exists() and profile.producer.calls == 0


def test_a_fresh_controller_authorizes_nothing_and_says_so(make):
    life, _, _ = make()
    summary = life.summary()
    T.assert_no_authority(summary)
    assert summary["state"] == "PREPARED" and summary["synthetic"] is True and summary["production_gate"] == "BLOCKED"
    assert summary["k17d_production_cross_check"] == "NOT_RUN" and summary["evidence_scope"] == "SYNTHETIC_TEST_ROOT"


def test_blocked_is_not_terminal_and_a_retry_with_fixed_evidence_opens_the_journal_correctly(make):
    life, _, authority = make()
    authority.available = False
    life.verify_evidence()
    assert life.state == "BLOCKED" and not life._ledger_exists()            # nothing may be journaled before run_opened
    authority.available = True
    life.retry()
    assert life.state == "PREPARED"
    life.verify_evidence()
    assert life.state == "EVIDENCE_VERIFIED"
    entries = life.journal_entries()
    assert entries[0]["kind"] == "run_opened" and sum(e["kind"] == "run_opened" for e in entries) == 1


# ---- the finished synthetic run ---------------------------------------------------------------------------------------

def test_the_whole_inventory_runs_through_three_isolated_stages(complete):
    summary = complete["summary"]
    T.assert_no_authority(summary)
    assert summary["state"] == "SYNTHETIC_STAGE_COMPLETE" and summary["completed_stages"] == ["known", "test", "matched"]
    assert summary["admitted_shards"] == 739 and summary["attempt"] == 1 and summary["failed_attempts"] == summary["interruptions"] == 0
    spec = C.build_specification(complete["plan"])
    sizes = {s["name"]: (len(s["shards"]), sum(x["observations"] for x in s["shards"])) for s in spec["stages"]}
    assert sizes == {"known": (576, 18400), "test": (125, 2500), "matched": (38, 450)}


def test_the_stage_cycle_is_the_same_for_every_stage(complete):
    path = [(e["action"], e["to"]) for e in complete["events"] if e["action"] != "init"]
    cycle = [("verify_evidence", "EVIDENCE_VERIFIED"), ("check_admission", "ADMISSION_CHECKED"), ("start_stage", "SYNTHETIC_STAGE_RUNNING"),
             ("verify_stage", "SYNTHETIC_STAGE_VERIFIED"), ("backup_stage", "SYNTHETIC_BACKUP_VERIFIED"), ("complete_stage", "SYNTHETIC_STAGE_COMPLETE")]
    assert path == cycle + [("next_stage", "PREPARED")] + cycle + [("next_stage", "PREPARED")] + cycle


def test_every_boundary_report_met_its_document_conditions_and_only_the_permanent_condition_stayed_blocked(complete):
    reports = complete["boundary_reports"]
    assert [r["boundary"] for r in reports] == ["pre_launch", "after_known", "after_known", "after_test", "after_test", "after_matched"]
    for report in reports:
        assert report["document_conditions_met"] is True, report
        assert [k for k, v in report["conditions"].items() if v == I.BLOCKED] == [I.PERMANENT]
        assert report["conditions"]["isolation.consumers"] == report["conditions"]["isolation.roles"] == I.PASS
    assert reports[-1]["conditions"]["k17d.metadata"] == I.PASS and reports[0]["conditions"].get("k17d.metadata") is not None


def test_the_journal_is_a_verified_anchored_chain_with_ordered_stage_entries(complete):
    base = complete["base"]
    anchors = M.AnchorStore(base / "anchors").latest()
    report = L.verify_chain((base / "journal" / L.LEDGER_NAME).read_bytes(), expected_head=anchors)
    assert report["ok"] and report["count"] == anchors["seq"] + 1
    entries = report["entries"]
    order = [(e["stage"], e["kind"]) for e in entries if e["kind"] in ("run_opened", "authorization_snapshot", "stage_bound", "stage_completed", "backup_verified", "k17d_check")]
    assert order == [(None, "run_opened"), (None, "authorization_snapshot"), ("known", "stage_completed"), ("known", "backup_verified"), (None, "k17d_check"),
                     ("test", "stage_bound"), ("test", "stage_completed"), ("test", "backup_verified"),
                     ("matched", "stage_bound"), ("matched", "stage_completed"), ("matched", "backup_verified")]
    assert sum(e["kind"] == "shard_admitted" for e in entries) == 739
    assert not [e for e in entries if e["kind"] in ("incident", "stop", "resume")]
    assert entries[0]["data"] == {"plan_fingerprint": complete["plan"]["plan_fingerprint"], "specification_sha256": C.build_specification(complete["plan"])["specification_sha256"]}


def test_later_request_bindings_are_derived_from_the_completed_predecessors_not_from_a_fixture(complete):
    entries = L.verify_chain((complete["base"] / "journal" / L.LEDGER_NAME).read_bytes())["entries"]
    manifests = {e["stage"]: e["data"]["manifests"] for e in entries if e["kind"] == "stage_completed"}
    bound = {e["stage"]: e["data"]["request_fingerprint"] for e in entries if e["kind"] == "stage_bound"}
    plan = complete["plan"]
    for stage, order in (("test", ["known"]), ("matched", ["known", "test"])):
        expected = M._digest({"schema": "B2-E18-synthetic-deferred-request/1", "stage": stage, "plan_fingerprint": plan["plan_fingerprint"],
                              "known_request_fingerprint": plan["source"]["known_request_fingerprint"],
                              "predecessor_manifests": {s: manifests[s] for s in order}})
        assert bound[stage] == expected
    assert len({bound["test"], bound["matched"], plan["source"]["known_request_fingerprint"]}) == 3


def test_published_files_are_synthetic_read_only_and_descriptor_last(complete):
    work = complete["base"] / "work"
    seen = 0
    for stage_dir in sorted(work.iterdir()):
        assert sorted(p.name for p in stage_dir.iterdir()) == sorted(I.STAGE_ROLES[stage_dir.name])
        for role_dir in sorted(stage_dir.iterdir()):
            assert (role_dir.stat().st_mode & 0o022) == 0
            for ordinal in sorted({int(re.search(r"-(\d{5})\.", p.name).group(1)) for p in role_dir.iterdir()})[:6]:
                part, meta, descriptor = (role_dir / name for name in D.shard_names(ordinal))
                for path in (part, meta, descriptor):
                    assert path.stat().st_mode & 0o777 == 0o444 and path.stat().st_nlink == 1
                assert descriptor.stat().st_mtime_ns >= max(part.stat().st_mtime_ns, meta.stat().st_mtime_ns)
                assert part.read_bytes().startswith(M.SYNTHETIC_PREFIX)
                assert all(json.loads(line)["synthetic"] is True for line in meta.read_text().splitlines())
                seen += 1
    assert seen >= 6
    leftovers = [p for p in (complete["base"]).rglob("*") if p.name.endswith(".tmp") or p.name.startswith(".")]
    assert not leftovers


def test_every_completed_role_has_a_byte_verified_backup_copy(complete):
    spec = C.build_specification(complete["plan"])
    fp = complete["plan"]["source"]["known_request_fingerprint"]
    shards = [s for s in spec["stages"] if s["name"] == "known"][0]["shards"]
    role = "train"
    expected = {s["ordinal"]: {"role": role, "scenario_seeds": list(s["groups"]), "n_samples": s["observations"], "request_fingerprint": fp}
                for s in shards if s["role"] == role}
    source, copy_dir = complete["base"] / "work" / "known" / role, complete["base"] / "backup" / "known" / role
    manifest = D.build_manifest(source, expected)
    restored = D.verify_restore(copy_dir, manifest, expected)
    assert restored["ok"] and restored["restore_reverified"] and restored["disaster_recovery_qualified"] is False
    assert source.stat().st_dev == copy_dir.stat().st_dev                    # same temporary volume: the attestor, not this test, claims otherwise


# ---- real production remains unreachable ----------------------------------------------------------------------------------

@pytest.mark.parametrize("args,kwargs", [((), {}), (("generate",), {}), ((1, 2, 3), {"mode": "production"}), ((object(),), {"confirm": True, "gate": "full_generation"})])
def test_deny_production_raises_for_every_input(args, kwargs):
    with pytest.raises(M.ProductionExecutionUnavailable):
        M.deny_production(*args, **kwargs)


def test_production_gate_blocks_even_when_every_fabricated_authority_is_valid(complete):
    bundle = complete["bundle"]
    authority = T.Authority(complete["custody"], bundle)
    now = T.CLOCK
    evidence = authority("c" * 64, 7, now)
    result = M.production_gate(bundle["plan"], bundle["reference"], repo=bundle["repo"], evidence=evidence, now=now, challenge="c" * 64,
                               revocation_floor=7, ci_floor=7)
    T.assert_no_authority(result)
    assert result["lifecycle_state"] == "BLOCKED" and result["reason"] == "PRODUCTION_EXECUTION_UNAVAILABLE"
    assert result["trusted_evidence_ok"] is False and result["trust_root_configured"] is False and result["ports_called"] == 0
    assert result["trusted_evidence_status"] == "BLOCKED_TRUST_ROOT_MISSING" and result["trusted_evidence_scope"] == "PRODUCTION_ROOT"
    assert E.PINNED_TRUST_ROOT is None and G.sup.PRODUCTION_LAUNCH_ENABLED is False and G.sup.FIXTURE_MAX_GROUPS == 2


def test_the_existing_fail_closed_contracts_are_untouched():
    permanent = I._execution_boundary()
    assert permanent["id"] == I.PERMANENT and permanent["status"] == I.BLOCKED and permanent["details"]["permanent"] is True
    for call, refusal in ((lambda: G.e9.guard_execution("generation"), G.e9.ExecutionNotAuthorized), (C.deny_execution, C.ExecutionUnavailable),
                          (I.deny_execution, I.ExecutionUnavailable), (M.deny_production, M.ProductionExecutionUnavailable)):
        with pytest.raises(refusal):
            call()
    probe = Path("/nonexistent-e18-probe")
    with pytest.raises(G.sup.SupervisorError):
        G.sup.stage_argv("known", G.sup.build_plan(probe, mode="production", groups_per_shard=4), probe)


def test_the_lifecycle_module_has_no_launch_surface():
    tree = ast.parse((ROOT / "scripts/b2_e18_lifecycle.py").read_text())
    imported = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    imported |= {(n.module or "").split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert not imported & {"subprocess", "multiprocessing", "threading", "socket", "ctypes", "numpy", "scipy", "torch", "geosim", "geoml", "b2_e18_synthetic",
                           "b2_production_supervisor", "requests", "urllib", "http", "pty", "asyncio", "importlib", "runpy", "posix", "concurrent", "builtins",
                           "code", "codeop", "sched", "signal", "pickle", "marshal", "shelve"}
    # A regression tripwire, not a proof: the injected ports are caller code. It does catch the obvious reachings through other modules.
    attributes = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    assert not attributes & {"subprocess", "Popen", "system", "popen", "fork", "forkpty", "execv", "execve", "execvp", "spawnv", "posix_spawn", "import_module"}
    for node in ast.walk(tree):                                   # of the supervisor / E9 / preflight modules the core may read exactly one constant each
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Attribute) and isinstance(node.value.value, ast.Name) and node.value.value.id == "G":
            allowed = {"sup": {"PRODUCTION_LAUNCH_ENABLED"}, "pre": {"PLAN_TOTAL"}}
            assert node.value.attr in allowed and node.attr in allowed[node.value.attr], ast.unparse(node)
    source = ast.unparse(tree)
    for needle in ("os.environ", "getenv", "os.system", "os.exec", "os.spawn", "os.fork", "popen", "eval(", "exec(", "__import__", "PRODUCTION_LAUNCH_ENABLED ="):
        assert needle not in source, needle
    public = {n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and not n.name.startswith("_")}
    assert not [name for name in public if any(w in name.lower() for w in ("launch", "generate", "execute", "start_production", "unlock", "enable"))]
    methods = {f.name for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "SyntheticExecutorLifecycle" for f in n.body if isinstance(f, ast.FunctionDef)}
    assert not [name for name in methods if any(w in name.lower() for w in ("launch", "generate", "unlock", "enable", "authorize", "approve", "force", "override"))]


def test_the_synthetic_module_is_not_imported_by_the_core_and_imports_no_generator_or_signer():
    tree = ast.parse((ROOT / "scripts/b2_e18_synthetic.py").read_text())
    imported = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    imported |= {(n.module or "").split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert not imported & {"subprocess", "numpy", "scipy", "torch", "geosim", "geoml", "b2_e17_signatures", "b2_e17_evidence", "b2_e18_lifecycle"}
    assert "ssh-keygen" not in (ROOT / "scripts/b2_e18_synthetic.py").read_text() and "ssh-keygen" not in (ROOT / "scripts/b2_e18_lifecycle.py").read_text()


def test_the_profile_has_no_permission_flag_and_rejects_unknown_fields(make):
    names = {f.name for f in dataclasses.fields(M.SyntheticProfile)}
    assert names == {"plan", "specification", "repo", "trust_root", "reference_source", "evidence_source", "producer", "clock", "resources",
                     "attestor", "workspace", "consumers"}
    life, profile, _ = make()
    fields = {f.name: getattr(profile, f.name) for f in dataclasses.fields(profile)}
    for extra in ({"production": True}, {"allow_real_generation": True}, {"mode": "production"}, {"enabled": True}):
        with pytest.raises(TypeError):
            M.SyntheticProfile(**fields, **extra)


# ---- workspace and profile validation --------------------------------------------------------------------------------------

def test_workspace_roots_may_not_overlap_each_other_or_the_declared_production_roots(tmp_path, integrated):
    plan = integrated["plan"]
    ok = T.make_workspace(tmp_path / "ok")
    assert set(ok.validate(plan)) == set(M.Workspace.ROLES)
    base = {name: tmp_path / "ok" / name for name in M.Workspace.ROLES}
    for left, right in (("work", "backup"), ("journal", "anchors"), ("replay", "quarantine")):
        with pytest.raises(M.LifecycleRefused, match="overlap"):
            M.Workspace(**{**base, right: base[left]}).validate(plan)
    with pytest.raises(M.LifecycleRefused, match="overlap"):
        M.Workspace(**{**base, "journal": base["work"] / "journal"}).validate(plan)
    for forbidden in ("/data/b2", "/data/b2/e18", "/data", "/mnt/backup/b2", "/mnt/backup/b2/x", "/mnt/backup"):
        with pytest.raises(M.LifecycleRefused, match="production root"):
            M.Workspace(**{**base, "work": Path(forbidden)}).validate(plan)
    with pytest.raises(M.LifecycleRefused):
        M.Workspace(**{**base, "work": Path("relative/path")}).validate(plan)
    with pytest.raises(M.LifecycleRefused):
        M.Workspace(**{**base, "work": tmp_path / "ok" / ".." / "x"}).validate(plan)


def test_a_symlinked_or_missing_workspace_root_is_refused(tmp_path, integrated):
    plan = integrated["plan"]
    workspace = T.make_workspace(tmp_path / "w")
    real = tmp_path / "elsewhere"
    real.mkdir()
    os.rmdir(workspace.replay)
    os.symlink(real, workspace.replay)
    with pytest.raises(M.LifecycleRefused, match="symlink|missing"):
        workspace.validate(plan)
    os.unlink(workspace.replay)
    with pytest.raises(M.LifecycleRefused, match="symlink|missing"):
        workspace.validate(plan)


@pytest.mark.parametrize("field,value", [("trust_root", object()), ("trust_root", None), ("producer", None), ("producer", "generate"), ("evidence_source", 1),
                                         ("reference_source", None), ("clock", object()), ("resources", object()), ("attestor", object()),
                                         ("workspace", "/tmp/x"), ("consumers", "all")])
def test_profile_ports_must_be_the_expected_kinds(make, field, value):
    _, profile, _ = make()
    with pytest.raises(M.LifecycleRefused):
        dataclasses.replace(profile, **{field: value})


def test_only_a_profile_builds_a_controller_and_a_foreign_specification_is_refused(make):
    _, profile, _ = make()
    for bad in (None, {}, {"plan": profile.plan}, "profile", profile.plan):
        with pytest.raises(M.LifecycleRefused):
            M.SyntheticExecutorLifecycle(bad)
    forged = dict(profile.specification, specification_sha256="0" * 64)
    with pytest.raises(Exception):
        M.SyntheticExecutorLifecycle(dataclasses.replace(profile, specification=forged))
    altered = copy.deepcopy(profile.plan)
    altered["ceilings"]["wall_hours"] = 999.0
    with pytest.raises(Exception):
        M.SyntheticExecutorLifecycle(dataclasses.replace(profile, plan=altered))


def test_one_controller_per_workspace_and_an_existing_journal_demands_recover(make):
    life, profile, _ = make()
    with pytest.raises(M.LifecycleRefused, match="another controller"):
        M.SyntheticExecutorLifecycle(profile)
    life.verify_evidence()
    life.close()
    with pytest.raises(M.LifecycleRefused, match="journal already exists"):
        M.SyntheticExecutorLifecycle(profile)


def rows(request, count=None, **row):
    return b"".join(json.dumps({"i": i, "synthetic": True, **row}).encode() + b"\n" for i in range(request["observations"] if count is None else count))


GOOD_PAYLOAD = M.SYNTHETIC_PREFIX + b"fabricated"
CONTRACT_BREAKERS = {
    "nothing": lambda r: None, "text": lambda r: "payload", "metadata_missing": lambda r: {"payload": GOOD_PAYLOAD},
    "extra_key": lambda r: {"payload": GOOD_PAYLOAD, "metadata": rows(r), "gpu": True}, "payload_not_bytes": lambda r: {"payload": "text", "metadata": rows(r)},
    "no_synthetic_marker": lambda r: {"payload": b"\x93NUMPY real-looking archive", "metadata": rows(r)},
    "payload_over_the_bound": lambda r: {"payload": GOOD_PAYLOAD + b"x" * M.MAX_SYNTHETIC_PAYLOAD, "metadata": rows(r)},
    "metadata_over_the_bound": lambda r: {"payload": GOOD_PAYLOAD, "metadata": rows(r, pad="x" * 4000)},
    "one_row_short": lambda r: {"payload": GOOD_PAYLOAD, "metadata": rows(r, count=r["observations"] - 1)},
    "one_row_too_many": lambda r: {"payload": GOOD_PAYLOAD, "metadata": rows(r, count=r["observations"] + 1)},
    "a_row_is_not_synthetic": lambda r: {"payload": GOOD_PAYLOAD, "metadata": rows(r).replace(b'"synthetic": true', b'"synthetic": false', 1)},
    "a_row_is_not_json": lambda r: {"payload": GOOD_PAYLOAD, "metadata": b"not json\n" * r["observations"]},
}


@pytest.mark.parametrize("name", sorted(CONTRACT_BREAKERS))
def test_a_producer_that_breaks_the_contract_is_stopped_resumably_before_anything_is_published(make, name):
    life, profile, _ = make(producer_factory=lambda clock: CONTRACT_BREAKERS[name])
    admitted(life)
    life.run_stage(shard_budget=1)
    assert life.state == "STOPPED" and life.events[-1]["resumable"] is True and life.summary()["failed_attempts"] == 1
    assert life.summary()["admitted_shards"] == 0 and T.incidents(life) == ["interruption"]
    assert not [p for p in life.paths["work"].rglob("*") if p.is_file()]


def timed(clock, build):
    """A producer that takes (fake) time like a real one; a shard measured at zero seconds is not a valid timing sample."""
    def produce(request):
        clock.advance(4.4 * request["observations"])
        return build(request)
    return produce


def test_a_compliant_producer_is_accepted_by_the_same_checks(make):
    life, profile, _ = make(producer_factory=lambda clock: timed(clock, lambda r: {"payload": GOOD_PAYLOAD, "metadata": rows(r)}))
    admitted(life)
    life.run_stage(shard_budget=1)
    assert life.state == "SYNTHETIC_STAGE_RUNNING" and life.summary()["admitted_shards"] == 1


def test_the_producer_is_given_no_scenario_seeds_no_request_identity_and_only_a_bounded_synthetic_task(make):
    seen = []

    def spy(request):
        seen.append(request)
        return {"payload": GOOD_PAYLOAD, "metadata": rows(request)}
    life, profile, _ = make(producer_factory=lambda clock: timed(clock, spy))
    admitted(life)
    life.run_stage(shard_budget=2)
    assert len(seen) == 2
    for request in seen:
        assert set(request) == {"stage", "role", "ordinal", "observations", "max_payload_bytes", "max_metadata_bytes"}
        assert request["max_payload_bytes"] == M.MAX_SYNTHETIC_PAYLOAD <= 64 * 1024 and request["stage"] == "known"


def test_the_profile_of_a_running_controller_cannot_be_replaced(make):
    life, profile, _ = make()
    with pytest.raises(AttributeError):
        life.profile = dataclasses.replace(profile, producer=lambda request: None)
    assert life.profile is profile


# ---- stage-order and role isolation ------------------------------------------------------------------------------------------

@pytest.mark.parametrize("later", ["test", "matched"])
def test_data_of_a_later_stage_before_its_predecessor_is_complete_stops_the_run_and_is_left_untouched(make, later):
    life, profile, _ = make()
    life.verify_evidence()
    role = I.STAGE_ROLES[later][0]
    planted = life.paths["work"] / later / role
    planted.mkdir(parents=True)
    (planted / "part-00000.npz").write_bytes(b"premature later-stage data")
    snapshot = T.tree_digest(planted)
    life.check_admission()
    assert life.state == "STOPPED" and profile.producer.calls == 0
    assert T.incidents(life) == ["stage_order_violation"] and T.kinds(life)[-1] == "stop"
    assert T.tree_digest(planted) == snapshot
    with pytest.raises(M.InvalidTransition):
        life.run_stage()


def test_unexpected_entries_beside_the_role_directories_quarantine_the_stage(make):
    life, profile, _ = make()
    life.verify_evidence()
    (life.paths["work"] / "known").mkdir()
    (life.paths["work"] / "known" / "notes.txt").write_bytes(b"stray")
    life.check_admission()
    assert life.state == "QUARANTINED" and profile.producer.calls == 0 and T.kinds(life)[-1] == "stop"


@pytest.mark.parametrize("declaration", [
    {"train": [["known", "train"], ["known", "test"]], "val_select": [["known", "val-select"]], "val_calib": [["known", "val-calib"]]},
    {"train": [["known", "train"]], "val_select": [["matched", "test-matched"]], "val_calib": [["known", "val-calib"]]},
    {"train": [["known", "train"]], "val_select": [["known", "val-select"]], "val_calib": [["test", "test"]]},
    {"train": [["known", "train"]], "val_select": [["known", "val-select"]], "val_calib": [["known", "val-calib"]], "evaluate": [["known", "test"]]},
    {"train": [["known", "val-calib"]], "val_select": [["known", "val-select"]], "val_calib": [["known", "val-calib"]]},
    {"train": "everything", "val_select": [], "val_calib": []},
])
def test_held_out_roles_can_never_reach_training_selection_or_calibration(make, declaration):
    life, profile, _ = make(consumers=lambda: copy.deepcopy(declaration))
    life.verify_evidence()
    life.check_admission()
    assert life.state == "STOPPED" and profile.producer.calls == 0 and T.incidents(life) == ["identity_mismatch"]


def test_the_default_consumers_are_exactly_the_three_known_training_roles(make):
    life, _, _ = make()
    admitted(life)
    assert life.state == "ADMISSION_CHECKED"
    assert life.boundary_reports[0]["conditions"]["isolation.consumers"] == I.PASS and I.ALLOWED_CONSUMERS == {
        "train": [["known", "train"]], "val_select": [["known", "val-select"]], "val_calib": [["known", "val-calib"]]}


# ---- review remediation: locks, canary, honesty, stale verification ---------------------------------------------------------------------

def test_a_second_controller_with_fresh_journal_directories_still_cannot_share_the_work_or_backup_root(make, tmp_path, custody, integrated):
    life, profile, _ = make()
    other = T.make_workspace(tmp_path / "other")
    clash = M.Workspace(work=profile.workspace.work, backup=other.backup, journal=other.journal, anchors=other.anchors, replay=other.replay, quarantine=other.quarantine)
    with pytest.raises(M.LifecycleRefused, match="another controller"):
        M.SyntheticExecutorLifecycle(T.make_profile(None, custody, integrated, workspace=clash)[0])
    clash = M.Workspace(work=other.work, backup=profile.workspace.backup, journal=other.journal, anchors=other.anchors, replay=other.replay, quarantine=other.quarantine)
    with pytest.raises(M.LifecycleRefused, match="another controller"):
        M.SyntheticExecutorLifecycle(T.make_profile(None, custody, integrated, workspace=clash)[0])
    life.close()
    M.SyntheticExecutorLifecycle(T.make_profile(None, custody, integrated, workspace=other)[0]).close()           # nothing is left locked behind


def test_the_permanent_execution_boundary_condition_is_a_canary_the_lifecycle_will_not_ignore(make, monkeypatch):
    life, profile, _ = make()
    life.verify_evidence()
    monkeypatch.setattr(I, "deny_execution", lambda *a, **k: None)                   # the E16 refusal silently returns instead of refusing
    life.check_admission()
    assert life.state == "STOPPED" and profile.producer.calls == 0 and T.incidents(life) == ["identity_mismatch"]
    assert "execution boundary changed" in life.events[-1]["reason"]


def test_production_gate_reports_the_canary_and_never_claims_a_closed_state_as_an_approval(complete, monkeypatch):
    bundle, authority = complete["bundle"], T.Authority(complete["custody"], complete["bundle"])
    args = dict(repo=bundle["repo"], now=T.CLOCK, challenge="c" * 64, revocation_floor=9, ci_floor=9)
    ok = M.production_gate(bundle["plan"], bundle["reference"], evidence=authority("c" * 64, 9, T.CLOCK), **args)
    assert ok["execution_boundary"] == I.BLOCKED and ok["trusted_evidence_ok"] is False and ok["closed_state_verified"] is False
    monkeypatch.setattr(I, "deny_execution", lambda *a, **k: None)
    broken = M.production_gate(bundle["plan"], bundle["reference"], evidence=authority("c" * 64, 9, T.CLOCK), **args)
    assert broken["execution_boundary"] == I.FAIL and broken["lifecycle_state"] == "BLOCKED"
    T.assert_no_authority(broken)


def test_a_verified_closed_state_is_reported_as_closed_not_as_trusted_evidence(tmp_path, reference):
    """The real, closed canonical state verifies cleanly and must never be read as an approval."""
    import subprocess
    for name, document in ((P.pre.GATES_PATH, reference["gates"]), (P.pre.MEMO_PATH, reference["memo"]), (G.PROTOCOL_JSON, reference["scientific_protocol"])):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(S._canonical(document).decode())
    git = lambda *a: subprocess.run(["git", "-c", "user.name=E18fixture", "-c", "user.email=fixture@example.invalid", *a], cwd=tmp_path, check=True, capture_output=True, text=True).stdout.strip()   # noqa: E731
    git("init", "-q")
    git("add", ".")
    git("commit", "-qm", "closed metadata fixture")
    reference["head"] = git("rev-parse", "HEAD")
    result = M.production_gate(G.make_template(reference), reference, repo=tmp_path, evidence=None, now=T.CLOCK, challenge="c" * 64, revocation_floor=1, ci_floor=1)
    assert result["trusted_evidence_state"] == P.STATE_CLOSED and result["closed_state_verified"] is True
    assert result["trusted_evidence_ok"] is False and result["lifecycle_state"] == "BLOCKED" and result["ports_called"] == 0
    T.assert_no_authority(result)


def test_the_summary_observes_the_launch_flag_instead_of_asserting_it(make, monkeypatch):
    life, _, _ = make()
    assert life.summary()["production_launch_enabled"] is False
    monkeypatch.setattr(G.sup, "PRODUCTION_LAUNCH_ENABLED", True)
    summary = life.summary()
    assert summary["production_launch_enabled"] is True and summary["execution_permitted"] is False and summary["verdict"] == "NO-GO"
    life.verify_evidence()
    assert life.state in ("STOPPED", "BLOCKED") and life.summary()["admitted_shards"] == 0                      # the changed flag is caught, not tolerated


def test_a_retry_always_verifies_the_evidence_again_so_a_withdrawn_grant_cannot_be_walked_past(make):
    life, profile, authority = make()
    authority.available = False
    life.verify_evidence()
    assert life.state == "BLOCKED"
    authority.available, authority.status = True, "REVOKED"
    profile.clock.advance(1500)
    life.retry()
    assert life.state == "PREPARED"
    life.verify_evidence()
    assert life.state == "STOPPED" and "revoked" in life.events[-1]["reason"] and profile.producer.calls == 0


def test_admission_refuses_a_verification_older_than_the_signed_answers_may_be(make):
    life, profile, authority = make()
    life.verify_evidence()
    profile.clock.advance(M.TRUST_MAX_AGE_S + 1)
    life.check_admission()
    assert life.state == "BLOCKED" and "older" in life.events[-1]["reason"] and profile.producer.calls == 0
    life.retry()
    life.verify_evidence()
    life.check_admission()
    assert life.state == "ADMISSION_CHECKED"


def test_a_stage_may_not_start_on_a_verification_that_went_stale_after_admission(make):
    life, profile, _ = make()
    admitted(life)
    profile.clock.advance(M.TRUST_MAX_AGE_S + 1)
    life.run_stage()
    assert life.state == "BLOCKED" and profile.producer.calls == 0 and "stale" in life.events[-1]["reason"]
    life.retry()
    assert life.state == "PREPARED"


def test_interrupt_refuses_the_reserved_producer_failure_signal(make):
    life, _, _ = make()
    with pytest.raises(M.LifecycleRefused):
        life.interrupt("PRODUCER_FAILURE")
    assert life.state == "PREPARED"


def test_scratch_purge_removes_read_only_trees_and_never_follows_a_link_out(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep.txt").write_text("evidence stays")
    scratch_root = tmp_path / "scratch"
    sealed = scratch_root / "a" / "sealed"
    sealed.mkdir(parents=True)
    (sealed / "shard.bin").write_bytes(b"x")
    os.chmod(sealed / "shard.bin", 0o444)
    os.chmod(sealed, 0o555)
    os.chmod(scratch_root / "a", 0o555)
    (scratch_root / "link").symlink_to(outside, target_is_directory=True)
    T.discard(scratch_root)
    assert not scratch_root.exists()
    assert (outside / "keep.txt").read_text() == "evidence stays"

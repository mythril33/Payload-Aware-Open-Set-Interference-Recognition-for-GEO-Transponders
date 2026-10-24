"""E9 guarded-executor contract (P34): pure validators, fail-closed state model, nine-cell freeze, restart provenance and
resource/lock schemas. CPU-only, synthetic metadata and fake artifacts; no real held-out observation, no GPU, no file written.
"""
import ast
import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest

from geoml import b2_e9_contract as c

ROOT = Path(__file__).parents[1]
PLAN = ROOT / "docs" / "plan"
PROTOCOL = json.loads((PLAN / "b2_e9_approved_scientific_protocol.json").read_text())
LIVE_GATES = json.loads((PLAN / "b2_readiness_gates_2026-10-21.json").read_text())
MEMO = json.loads((PLAN / "b2_e5_decision_recommendations.json").read_text())
HEAD = "a" * 40
H = lambda ch: ch * 64        # noqa: E731


def fields(report):
    return {f["field"] for f in report["failures"]}


def codes(report):
    return {(f["field"], f["code"]) for f in report["failures"]}


def mutate(base, path, value=None, *, delete=False):
    out = copy.deepcopy(base)
    node = out
    for part in path[:-1]:
        node = node[part]
    if delete:
        del node[path[-1]]
    else:
        node[path[-1]] = value
    return out


def synthetic_gates():
    """Independent of the live gates file, which other workstreams may legitimately change."""
    approval = {"approved_by": PROTOCOL["approved_by"], "approved_at": PROTOCOL["approved_at"], "decision": "A", "record": PROTOCOL["approval_record"]}
    decisions = {k: {"status": "APPROVED", "approval": dict(approval)} for k in c.SCIENTIFIC_GATES}
    decisions.update({k: {"status": "NOT_AUTHORIZED", "approval": None} for k in ("full_generation", "full_gpu_training", "full_loko_sweep")})
    return {"benchmark_complete": False, "decisions": decisions}


GATES = synthetic_gates()


def with_approvals(gates, *keys, full=True):
    gates = copy.deepcopy(gates)
    record = {"approved_by": "researcher", "approved_at": "2026-11-01T00:00:00Z", "decision": "x", "record": "r"}
    for key in keys:
        needs = key.startswith("full_") and full
        gates["decisions"][key].update(status="AUTHORIZED" if key == "full_generation" else "APPROVED",
                                       approval=dict(record, wall_hours=36, core_hours=42, working_disk_gib=25, backup_disk_gb=9) if needs else record)
    return gates


EVIDENCE = {"source_head": HEAD, "independent_review": {"reviewed_head": HEAD, "open_material_findings": 0, "record": "docs/research/x.md"},
            "exact_head_ci": {"head": HEAD, "conclusion": "success", "run_id": 1}}
APPROVED = c.approved_config()


# ---- the approved record and the explicit configuration -------------------------------------------------------------

def test_the_approved_record_validates_and_derives_exactly_the_reference_configuration():
    assert c.validate_protocol_record(PROTOCOL)["ok"] is True
    assert c.config_from_protocol(PROTOCOL) == APPROVED
    report = c.validate_scientific_config(c.approved_config())
    assert report["ok"] and report["authorizes_nothing"] is True and len(report["config_sha256"]) == 64
    assert report["executor_implemented"] is False
    assert c.APPROVED_CONFIG_SHA256 == c.sha256_of(c.config_from_protocol(PROTOCOL)) == report["config_sha256"]      # literal digest pinned in the source


@pytest.mark.parametrize("path,value", [
    (("views",), ["co", "dual"]), (("seeds",), [0, 1, 3]), (("model", "width"), 8), (("model", "time_pool"), 1), (("model", "level"), "global"),
    (("training", "epochs"), 3), (("training", "batch_size"), 8), (("training", "early_stopping"), True),
    (("loss", "center_loss_weight"), 0.0), (("loss", "center_loss_weight"), 0.01), (("loss", "plan_loss_weight"), 0.0),
    (("loss", "plan_consistency"), False), (("augmentation", "plan_shift_fraction"), 0.0), (("augmentation", "plan_shift_max_hz"), 250000.0),
    (("optimizer", "name"), "SGD"), (("optimizer", "weight_decay"), 0.0), (("optimizer", "gradient_clipping"), "norm_1.0"),
    (("scheduler", "name"), "CosineAnnealingLR"), (("scheduler", "pct_start"), 0.25),
    (("numerics", "cudnn_tf32_enabled"), True), (("numerics", "matmul_tf32_enabled"), True), (("numerics", "mixed_precision_enabled"), True),
    (("numerics", "precision"), "bf16"), (("numerics", "deterministic_algorithms"), True),
    (("streaming", "groups_per_shard"), 8), (("streaming", "window_shards"), 2),
    (("isolation", "heldout_read_before_freeze"), True), (("isolation", "test_driven_retuning"), True),
    (("restart", "carry_partial_state"), True), (("restart", "restart_epoch"), 7),
    (("calibration", "known_acceptance_target"), 0.9), (("calibration", "clean_alarm_pfa"), 0.01), (("calibration", "mahalanobis_shrinkage"), 0.0),
    (("receiver",), "obs-cancel/2"), (("profile",), "B2-R6-fp32-tf32-on/1")])
def test_every_critical_conflict_is_an_explicit_failure(path, value):
    report = c.validate_scientific_config(mutate(APPROVED, path, value))
    assert report["ok"] is False and any(f["field"].startswith("$." + ".".join(path)) and f["code"] in ("CONFLICT", "TYPE") for f in report["failures"])


@pytest.mark.parametrize("path", [("views",), ("seeds",), ("model",), ("numerics", "cudnn_tf32_enabled"), ("numerics", "matmul_tf32_enabled"),
                                  ("numerics", "mixed_precision_enabled"), ("loss", "center_loss_weight"), ("loss", "plan_consistency"),
                                  ("augmentation",), ("streaming", "window_shards"), ("restart",), ("calibration", "mahalanobis_shrinkage"), ("profile",)])
def test_every_missing_critical_field_is_an_explicit_failure(path):
    report = c.validate_scientific_config(mutate(APPROVED, path, delete=True))
    assert ("$." + ".".join(path), "MISSING") in codes(report)


def test_unexpected_wrongly_typed_and_nonfinite_values_are_failures():
    assert ("$.numerics.fast_math", "UNEXPECTED") in codes(c.validate_scientific_config(mutate(APPROVED, ("numerics", "fast_math"), True)))
    assert ("$.numerics.cudnn_tf32_enabled", "TYPE") in codes(c.validate_scientific_config(mutate(APPROVED, ("numerics", "cudnn_tf32_enabled"), 0)))
    assert ("$.loss.plan_consistency", "TYPE") in codes(c.validate_scientific_config(mutate(APPROVED, ("loss", "plan_consistency"), 1)))
    assert ("$.loss.center_loss_weight", "NONFINITE") in codes(c.validate_scientific_config(mutate(APPROVED, ("loss", "center_loss_weight"), float("nan"))))
    assert ("$.model.width", "TYPE") in codes(c.validate_scientific_config(mutate(APPROVED, ("model", "width"), True)))
    for not_a_config in (None, [], "x", 3):
        assert c.validate_scientific_config(not_a_config)["ok"] is False
    assert c.validate_scientific_config(mutate(APPROVED, ("loss", "plan_loss_weight"), 1))["ok"]     # 1 equals 1.0; booleans never equal numbers
    json.dumps(c.validate_scientific_config(mutate(APPROVED, ("loss", "center_loss_weight"), float("nan"))), allow_nan=False)


def test_derived_consistency_checks_catch_a_config_that_agrees_field_by_field_but_not_with_itself():
    wrong_steps = mutate(APPROVED, ("training", "train_observations"), 12001)
    assert any(f["code"] == "CONFLICT" for f in c.validate_scientific_config(wrong_steps)["failures"])
    lr = mutate(APPROVED, ("scheduler", "max_lr"), 0.002)
    assert "$.scheduler.max_lr" in fields(c.validate_scientific_config(lr))
    assert APPROVED["training"]["optimizer_steps_per_fit"] == 30 * 375 == 11250


def test_the_reference_equals_the_markdown_record_and_the_bare_traincfg_defaults_would_fail_it():
    approval = (PLAN / "B2_E9_SCIENTIFIC_DECISION_APPROVAL_2026-10-24.md").read_text()
    for phrase in ("`width=16`, `time_pool=2`, `level=carrier`", "Exactly **30 epochs** and fixed OneCycle schedule, **no early stopping**",
                   "Batch **32** in all nine cells", "11,250 optimizer steps per 30-epoch fit", "No automatic batch reduction if host probe fails",
                   "`groups_per_shard=4`, `window_shards=4` with seeded blocked shuffle", "carry short batch remainder across windows",
                   "log shard orders and hashes", "Known-class acceptance **0.95**, clean-only alarm Pfa **0.05**",
                   "shrinkage **0.1**", "**both cuDNN TF32 and matmul TF32 explicitly off**", "restart at epoch 0 under new `attempt_id`",
                   "acceptance `score<=threshold`, clean-alarm `score>threshold` using 1-P(clean)", "`center_loss_weight=0.005`"):
        assert phrase in approval, phrase
    ref = c.approved_config()                      # the markdown-only (pinned) items of the reference
    assert ref["streaming"]["remainder_policy"] == "carry_short_batch_across_windows" and ref["streaming"]["log_shard_orders_and_hashes"] is True
    assert ref["calibration"]["acceptance_rule"] == "score_le_threshold" and ref["calibration"]["alarm_rule"] == "score_gt_threshold_on_one_minus_p_clean"
    from geoml.train import TrainConfig
    bare = TrainConfig(labels=("a", "b"))
    config = c.approved_config()
    config["loss"].update(center_loss_weight=bare.center_loss_weight, plan_consistency=bare.plan_consistency)
    config["augmentation"]["plan_shift_fraction"] = bare.plan_shift_fraction
    failed = fields(c.validate_scientific_config(config))
    assert {"$.loss.center_loss_weight", "$.loss.plan_consistency", "$.augmentation.plan_shift_fraction"} <= failed


@pytest.mark.parametrize("path,value", [(("scientific_approval",), False), (("activation",), True), (("production_authorized",), True),
                                        (("benchmark_complete",), True), (("status",), "RUNNABLE"), (("profile_id",), "other"),
                                        (("approved_by",), ""), (("source_main_sha",), "abc"),
                                        (("decisions", "K17d", "choice"), "B"), (("decisions", "R6", "choice"), "B"),
                                        (("unresolved_operational_decisions", "gpu_probe"), "AUTHORIZED"),
                                        (("unresolved_operational_decisions", "production_launch"), "ENABLED"),
                                        (("controls", "no_gpu_use"), False)])
def test_a_malformed_or_over_reaching_scientific_record_is_rejected(path, value):
    assert c.validate_protocol_record(mutate(PROTOCOL, path, value))["ok"] is False


def test_the_scientific_record_cannot_drift_from_the_configuration_it_derives():
    drifted = mutate(PROTOCOL, ("parameter_records", "model_width", "value"), 32)
    assert c.validate_protocol_record(drifted)["ok"] is False
    missing = mutate(PROTOCOL, ("parameter_records", "optimizer"), delete=True)
    assert c.validate_protocol_record(missing)["ok"] is False
    with pytest.raises(c.ContractError):
        c.config_from_protocol({})
    for decision in c.PROTOCOL_DECISIONS:
        assert c.validate_protocol_record(mutate(PROTOCOL, ("decisions", decision), delete=True))["ok"] is False
    assert len(c.PROTOCOL_DECISIONS) == 13


# ---- execution-state contract ---------------------------------------------------------------------------------------

def state(**kw):
    args = dict(protocol=PROTOCOL, gates=GATES, config=c.approved_config(), evidence=EVIDENCE)
    args.update(kw)
    return c.evaluate_state(**args)


def test_the_committed_gates_reach_awaiting_separate_approval_with_every_runtime_authorization_closed():
    result = state()
    assert result["state"] == c.AWAITING_SEPARATE_APPROVAL and result["runtime_permitted"] is False
    assert {a: v["status"] for a, v in result["authorizations"].items()} == {a: c.NOT_AUTHORIZED for a in c.ACTIONS}
    assert all(v["runnable"] is False for v in result["authorizations"].values()) and result["benchmark_complete"] is False
    json.dumps(result, allow_nan=False)


def test_engineering_ready_needs_no_evidence_and_awaiting_needs_exact_head_evidence():
    assert state(evidence=None)["state"] == c.ENGINEERING_READY
    for broken in (mutate(EVIDENCE, ("independent_review", "reviewed_head"), "b" * 40), mutate(EVIDENCE, ("independent_review", "open_material_findings"), 1),
                   mutate(EVIDENCE, ("exact_head_ci", "head"), "b" * 40), mutate(EVIDENCE, ("exact_head_ci", "conclusion"), "failure"),
                   mutate(EVIDENCE, ("source_head",), "short"), mutate(EVIDENCE, ("independent_review",), delete=True), {}, "x"):
        assert state(evidence=broken)["state"] == c.ENGINEERING_READY


@pytest.mark.parametrize("bad", ["protocol", "config", "gates", "launch_flag"])
def test_any_scientific_or_consistency_problem_forces_not_authorized(bad):
    if bad == "protocol":
        result = state(protocol=mutate(PROTOCOL, ("activation",), True))
    elif bad == "config":
        result = state(config=mutate(APPROVED, ("numerics", "cudnn_tf32_enabled"), True))
    elif bad == "gates":
        result = state(gates=mutate(GATES, ("decisions", "K18", "status"), "PENDING_RESEARCHER"))
    else:
        result = state(production_launch_enabled=True)
    assert result["state"] == c.NOT_AUTHORIZED and result["reasons"] and result["runtime_permitted"] is False


def test_malformed_scientific_approvals_are_rejected():
    for key in c.SCIENTIFIC_GATES:
        for field in c.APPROVAL_FIELDS:
            gates = mutate(GATES, ("decisions", key, "approval", field), delete=True)
            assert state(gates=gates)["state"] == c.NOT_AUTHORIZED, (key, field)
        assert state(gates=mutate(GATES, ("decisions", key, "approval", "approved_by"), "someone-else"))["state"] == c.NOT_AUTHORIZED
        assert state(gates=mutate(GATES, ("decisions", key, "approval", "approved_at"), "yesterday"))["state"] == c.NOT_AUTHORIZED
        assert state(gates=mutate(GATES, ("decisions", key, "approval"), None))["state"] == c.NOT_AUTHORIZED
    assert state(gates=mutate(GATES, ("benchmark_complete",), True))["state"] == c.NOT_AUTHORIZED
    assert state(gates={})["state"] == c.NOT_AUTHORIZED


def test_each_runtime_authorization_is_separate_and_none_becomes_runnable():
    base = state()["authorizations"]
    for action, gate in (("generation", "full_generation"), ("full_training", "full_gpu_training"), ("loko", "full_loko_sweep")):
        result = state(gates=with_approvals(GATES, gate))
        for other in c.ACTIONS:
            expected = "APPROVAL_RECORDED_NOT_RUNNABLE" if other == action else c.NOT_AUTHORIZED
            assert result["authorizations"][other]["status"] == expected, (action, other)
        assert result["state"] == c.AWAITING_SEPARATE_APPROVAL and result["runtime_permitted"] is False
        assert all(v["runnable"] is False for v in result["authorizations"].values())
    everything = state(gates=with_approvals(GATES, "full_generation", "full_gpu_training", "full_loko_sweep"))
    assert everything["authorizations"]["gpu_probe"]["status"] == c.NOT_AUTHORIZED          # the probe has no gate: never implied by the others
    assert base["gpu_probe"]["status"] == c.NOT_AUTHORIZED and everything["runtime_permitted"] is False


def test_malformed_compute_approvals_and_scientific_pass_never_imply_a_compute_approval():
    no_ceilings = with_approvals(GATES, "full_generation", full=False)
    result = state(gates=no_ceilings)
    assert result["state"] == c.NOT_AUTHORIZED and result["authorizations"]["generation"]["status"] == c.NOT_AUTHORIZED
    pending_with_material = mutate(GATES, ("decisions", "full_gpu_training", "approval"), {"approved_by": "x"})
    assert state(gates=pending_with_material)["state"] == c.NOT_AUTHORIZED
    unknown = mutate(GATES, ("decisions", "full_loko_sweep", "status"), "GO")
    assert state(gates=unknown)["state"] == c.NOT_AUTHORIZED
    scientific_only = state()
    assert all(v["status"] == c.NOT_AUTHORIZED for v in scientific_only["authorizations"].values())


def test_transitions_allow_only_the_three_state_chain_and_name_runnable_targets_as_refused():
    assert c.transition(c.NOT_AUTHORIZED, c.ENGINEERING_READY) == c.ENGINEERING_READY
    assert c.transition(c.ENGINEERING_READY, c.AWAITING_SEPARATE_APPROVAL) == c.AWAITING_SEPARATE_APPROVAL
    for current, target in ((c.NOT_AUTHORIZED, c.AWAITING_SEPARATE_APPROVAL), (c.AWAITING_SEPARATE_APPROVAL, c.ENGINEERING_READY)):
        with pytest.raises(c.ContractError, match="not allowed"):
            c.transition(current, target)
    for target in ("RUNNABLE", "RUNNING", "AUTHORIZED", "LAUNCHED", "anything"):
        for current in c.STATES:
            with pytest.raises(c.ContractError, match="no transition to runnable"):
                c.transition(current, target)
    with pytest.raises(c.ContractError, match="unknown state"):
        c.transition("RUNNING", c.NOT_AUTHORIZED)
    assert set(c.TRANSITIONS) == set(c.STATES) and len(c.STATES) == 3


def test_the_guard_always_refuses_whatever_is_passed_or_patched(monkeypatch):
    for action in c.ACTIONS:
        with pytest.raises(c.ExecutionNotAuthorized, match="not runnable"):
            c.guard_execution(action)
        with pytest.raises(c.ExecutionNotAuthorized):
            c.guard_execution(action, gates=with_approvals(GATES, "full_generation", "full_gpu_training", "full_loko_sweep"), evidence=EVIDENCE)
    with pytest.raises(c.ContractError, match="unknown action"):
        c.guard_execution("train")
    monkeypatch.setattr(c, "TRANSITIONS", {s: tuple(c.STATES) + ("RUNNABLE",) for s in c.STATES})        # a widened table ...
    monkeypatch.setattr(c, "ACTION_GATES", {a: None for a in c.ACTIONS})
    monkeypatch.setattr(c, "STATES", c.STATES + ("RUNNABLE",))
    with pytest.raises(c.ContractError, match="no transition to runnable"):                             # ... still names runnable targets as refused
        c.transition(c.AWAITING_SEPARATE_APPROVAL, "RUNNABLE")
    for action in c.ACTIONS:
        with pytest.raises(c.ExecutionNotAuthorized):
            c.guard_execution(action)
    assert c.runtime_permitted() is False and not hasattr(c, "EXECUTION_ENABLED") and not hasattr(c, "RUNNABLE")


def test_the_supervisors_launch_flag_stays_false_and_the_gates_stay_closed(monkeypatch):
    sup = load_script("b2_production_supervisor", monkeypatch)
    assert sup.PRODUCTION_LAUNCH_ENABLED is False and state(production_launch_enabled=sup.PRODUCTION_LAUNCH_ENABLED)["state"] == c.AWAITING_SEPARATE_APPROVAL
    assert {k: LIVE_GATES["decisions"][k]["status"] for k in ("full_generation", "full_gpu_training", "full_loko_sweep")} == {
        "full_generation": "NOT_AUTHORIZED", "full_gpu_training": "NOT_AUTHORIZED", "full_loko_sweep": "NOT_AUTHORIZED"}    # live-file pin
    assert LIVE_GATES["benchmark_complete"] is False and LIVE_GATES["decisions"]["full_generation"]["approval"] is None
    live = state(gates=LIVE_GATES, memo=MEMO)
    assert live["state"] == c.AWAITING_SEPARATE_APPROVAL and not any(v["runnable"] for v in live["authorizations"].values())
    from geoml import b2_execution
    assert b2_execution.CAPS == {"groups_per_role": 2, "epochs": 2, "width": 8, "batch": 32}      # CPU fixture caps untouched


def load_script(name, monkeypatch):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    return module


def test_the_structural_approval_check_agrees_with_the_preflight_gate_check(monkeypatch):
    pre = load_script("b2_production_preflight", monkeypatch)
    memo = copy.deepcopy(MEMO)
    base = with_approvals(GATES, "full_generation", "full_gpu_training")
    cases = [GATES, with_approvals(GATES, "full_generation"), with_approvals(GATES, "full_generation", full=False),
             mutate(with_approvals(GATES, "full_gpu_training"), ("decisions", "full_gpu_training", "approval", "approved_at"), "never"),
             mutate(base, ("decisions", "full_generation", "approval", "approved_at"), "2026-99-99T99:99:99Z"),
             mutate(base, ("decisions", "full_gpu_training", "approval", "approved_at"), "2026-02-30T00:00:00Z"),
             mutate(base, ("decisions", "full_generation", "approval", "wall_hours"), float("nan")),
             mutate(base, ("decisions", "full_gpu_training", "approval", "approved_by"), "  ")]
    for gates in cases:
        for key in ("full_generation", "full_gpu_training"):
            gates_for_twin = copy.deepcopy(gates)
            memo["decisions"][key]["status"] = gates_for_twin["decisions"][key]["status"]
            ours = c.authorization_status({"full_generation": "generation", "full_gpu_training": "full_training"}[key], gates)
            record = gates["decisions"][key]
            theirs = [x for x in pre.check_gates(gates, memo) if x["id"] == f"gates.{key}"][0]
            if record["status"] in pre.PENDING_STATUSES:
                assert ours["status"] == c.NOT_AUTHORIZED and theirs["status"] in (pre.BLOCKED, pre.FAIL)
            else:
                assert (ours["status"] == "APPROVAL_RECORDED_NOT_RUNNABLE") == (theirs["status"] == pre.PASS), (key, ours, theirs)


# ---- nine-cell freeze --------------------------------------------------------------------------------------------

def nine_cells():
    cells = []
    for v, view in enumerate(c.VIEWS):
        for s, seed in enumerate(c.SEEDS):
            n = v * 3 + s + 1
            cells.append({"view": view, "seed": seed, "attempt_id": f"attempt-{view}-{seed}", "status": "COMPLETE", "epochs_completed": 30,
                          "selected_epoch": (7 * n) % 30, "model_sha256": f"{n:x}1".rjust(64, "0"), "scorer_sha256": f"{n:x}2".rjust(64, "0"),
                          "calibrator_sha256": f"{n:x}3".rjust(64, "0"), "training_config_sha256": c.approved_config_sha256(), "data_identity": H("d"),
                          "source_tree_sha256": H("e"), "environment_id": H("f"), "profile": c.PROFILE,
                          "calibration": c.cell_calibration(), "heldout_reads": 0})
    return cells


def test_a_complete_compatible_nine_cell_roster_is_admissible_by_the_contract_only():
    report = c.validate_nine_cell_freeze(nine_cells())
    assert report["ok"] and report["freeze_contract_satisfied"] is True and report["cells_checked"] == 9 and report["authorizes_nothing"] is True


@pytest.mark.parametrize("edit,field", [
    (lambda cells: cells.pop(), "cells"),
    (lambda cells: cells.append(copy.deepcopy(cells[0])), "cells"),
    (lambda cells: cells[3].update(view="co", seed=0), "cells[3]"),
    (lambda cells: cells[0].update(status="INCOMPLETE"), "cells[0].status"),
    (lambda cells: cells[1].update(epochs_completed=29), "cells[1].epochs_completed"),
    (lambda cells: cells[2].update(selected_epoch=30), "cells[2].selected_epoch"),
    (lambda cells: cells[4].update(heldout_reads=1), "cells[4].heldout_reads"),
    (lambda cells: cells[5].update(profile="B2-R6-fp32-tf32-on/1"), "cells[5].profile"),
    (lambda cells: cells[6].update(data_identity=H("9")), "data_identity"),
    (lambda cells: cells[6].update(source_tree_sha256=H("9")), "source_tree_sha256"),
    (lambda cells: cells[7].update(environment_id=H("9")), "environment_id"),
    (lambda cells: cells[7].update(training_config_sha256=H("9")), "training_config_sha256"),
    (lambda cells: [cell.update(training_config_sha256=H("9")) for cell in cells], "training_config_sha256"),      # consistent but not the approved config
    (lambda cells: cells[1].update(attempt_id=cells[0]["attempt_id"]), "attempt_id"),
    (lambda cells: cells[2].update(model_sha256=cells[2]["source_tree_sha256"]), "artifacts"),
    (lambda cells: cells[3].update(selected_epoch=True), "cells[3].selected_epoch"),
    (lambda cells: cells[3].update(epochs_completed=30.0), "cells[3].epochs_completed"),
    (lambda cells: cells[3].update(data_identity=H("d") + "\n"), "cells[3].data_identity"),
    (lambda cells: cells[8]["calibration"].update(clean_alarm_pfa=0.1), "cells[8].calibration.clean_alarm_pfa"),
    (lambda cells: cells[8]["calibration"].update(mahalanobis_shrinkage=0.0), "cells[8].calibration.mahalanobis_shrinkage"),
    (lambda cells: cells[1].update(model_sha256=cells[0]["model_sha256"]), "artifacts"),
    (lambda cells: cells[2].update(scorer_sha256=cells[0]["scorer_sha256"]), "artifacts"),
    (lambda cells: cells[3].update(calibrator_sha256=cells[0]["calibrator_sha256"]), "artifacts"),
    (lambda cells: cells[4].update(scorer_sha256=cells[4]["model_sha256"]), "artifacts"),
    (lambda cells: cells[0].update(model_sha256="not-a-hash"), "cells[0].model_sha256"),
    (lambda cells: cells[0].pop("scorer_sha256"), "cells[0].scorer_sha256"),
    (lambda cells: cells[0].update(extra_state="x"), "cells[0].extra_state"),
    (lambda cells: cells[0].update(attempt_id="x"), "cells[0].attempt_id"),
])
def test_every_incomplete_or_incompatible_cell_blocks_the_freeze(edit, field):
    cells = nine_cells()
    edit(cells)
    report = c.validate_nine_cell_freeze(cells)
    assert report["ok"] is False and report["freeze_contract_satisfied"] is False and any(field in name for name in fields(report))


def test_a_renamed_checkpoint_does_not_satisfy_another_seed_or_view_and_bad_shapes_fail():
    cells = nine_cells()
    cells[8].update(model_sha256=cells[0]["model_sha256"], view=cells[0]["view"], seed=cells[0]["seed"])
    assert not c.validate_nine_cell_freeze(cells)["ok"]
    for bad in (None, {}, "x", [None] * 9, [1] * 9):
        assert not c.validate_nine_cell_freeze(bad)["ok"]
    missing_seed = nine_cells()
    missing_seed[0]["seed"] = True                                            # a bool is not the integer seed 1
    assert not c.validate_nine_cell_freeze(missing_seed)["ok"]


# ---- restart provenance ---------------------------------------------------------------------------------------------

def chain():
    first = c.make_attempt_record(attempt_id="attempt-000001", view="co", seed=0, status="INCOMPLETE", epochs_completed=11,
                                  source_tree_sha256=H("e"), data_identity=H("d"), environment_id=H("f"))
    second = c.make_attempt_record(attempt_id="attempt-000002", view="co", seed=0, status="COMPLETE", epochs_completed=30,
                                   source_tree_sha256=H("e"), data_identity=H("d"), environment_id=H("f"), parent=first)
    return [first, second]


def test_a_strict_epoch_zero_restart_chain_validates():
    report = c.validate_attempt_chain(chain())
    assert report["ok"] and report["completed_cells"] == ["co/0"]
    assert chain()[1]["start_epoch"] == 0 and chain()[1]["carried_state"] == c.carried_none() and chain()[1]["parent_hash"] == c.record_hash(chain()[0])
    assert c.validate_attempt_chain(chain()[:1])["ok"]                                           # an INCOMPLETE tail is legal; it just blocks the freeze


def rehash(record):
    record["record_hash"] = c.record_hash(record)
    return record


@pytest.mark.parametrize("edit,needle", [
    (lambda r: r[1].update(start_epoch=11), "start_epoch"),
    (lambda r: r[1]["carried_state"].update(optimizer="a" * 64), "carried_state.optimizer"),
    (lambda r: r[1]["carried_state"].update(scheduler="a" * 64), "carried_state.scheduler"),
    (lambda r: r[1]["carried_state"].update(rng="a" * 64), "carried_state.rng"),
    (lambda r: r[1]["carried_state"].update(weights="a" * 64), "carried_state.weights"),
    (lambda r: r[1]["carried_state"].update(data_cursor=4), "carried_state.data_cursor"),
    (lambda r: r[1].update(optimizer_state_sha256="a" * 64), "optimizer_state_sha256"),
    (lambda r: r[1].update(resume_from_epoch=11), "resume_from_epoch"),
    (lambda r: r[1].update(parent_hash=H("0")), "parent_hash"),
    (lambda r: r[1].update(parent_attempt_id="attempt-missing"), "parent_attempt_id"),
    (lambda r: r[1].update(view="dual"), "view"),
    (lambda r: r[1].update(seed=1), "seed"),
    (lambda r: r[1].update(source_tree_sha256=H("0")), "source_tree_sha256"),
    (lambda r: r[1].update(data_identity=H("0")), "data_identity"),
    (lambda r: r[1].update(environment_id=H("0")), "environment_id"),
    (lambda r: r[1].update(attempt_id=r[0]["attempt_id"]), "attempt_id"),
    (lambda r: r[0].update(status="COMPLETE"), "epochs_completed"),
    (lambda r: r[1].update(epochs_completed=29), "epochs_completed"),
    (lambda r: r[1].update(status="RUNNING"), "status"),
    (lambda r: r[1].update(record_hash=H("0")), "record_hash"),
    (lambda r: r[1].pop("parent_hash"), "parent_hash"),
])
def test_partial_continuation_and_broken_lineage_are_rejected(edit, needle):
    records = chain()
    edit(records)
    report = c.validate_attempt_chain(records)
    assert report["ok"] is False and any(needle in f["field"] for f in report["failures"]), report["failures"]


def test_restart_rules_around_completion_branching_roots_and_cycles(monkeypatch):
    first, second = chain()
    kwargs = dict(view="co", seed=0, source_tree_sha256=H("e"), data_identity=H("d"), environment_id=H("f"))
    with pytest.raises(c.ContractError):                                                 # the builder refuses a restart of a COMPLETE attempt
        c.make_attempt_record(attempt_id="attempt-000003", status="COMPLETE", epochs_completed=30, parent=second, **kwargs)
    sibling = c.make_attempt_record(attempt_id="attempt-000009", status="INCOMPLETE", epochs_completed=3, parent=first, **kwargs)
    assert not c.validate_attempt_chain([first, second, sibling])["ok"]                  # two restarts of one incomplete attempt
    other = c.make_attempt_record(attempt_id="attempt-100001", status="COMPLETE", epochs_completed=30, **kwargs)
    assert not c.validate_attempt_chain([first, second, other])["ok"]                    # two COMPLETE attempts for one view/seed
    unlinked = c.make_attempt_record(attempt_id="attempt-100002", status="INCOMPLETE", epochs_completed=2, **kwargs)
    report = c.validate_attempt_chain([first, unlinked])
    assert not report["ok"] and any("exactly one root" in str(f["expected"]) for f in report["failures"])      # a retry that drops its lineage
    # INCOMPLETE may record a full 30 epochs when persistence failed; COMPLETE may not claim fewer
    assert c.validate_attempt_chain([c.make_attempt_record(attempt_id="attempt-300001", status="INCOMPLETE", epochs_completed=30, **kwargs)])["ok"]
    # a lineage cycle, reachable only if the hash rules are neutralised: the defensive walk must still fire
    monkeypatch.setattr(c, "record_hash", lambda record: H("0"))
    a = {**first, "attempt_id": "attempt-cyc-a", "parent_attempt_id": "attempt-cyc-b", "parent_hash": H("0"), "record_hash": H("0")}
    b = {**first, "attempt_id": "attempt-cyc-b", "parent_attempt_id": "attempt-cyc-a", "parent_hash": H("0"), "record_hash": H("0")}
    assert any(f["actual"] == "cycle" for f in c.validate_attempt_chain([a, b])["failures"])
    for bad in (None, {}, [None], ["x"]):
        assert not c.validate_attempt_chain(bad)["ok"]


def test_unhashable_or_wrongly_typed_chain_fields_are_reported_not_raised():
    first, _ = chain()
    for edit in ({"parent_attempt_id": ["x"]}, {"view": ["x"]}, {"seed": [1]}, {"attempt_id": ["x"]}, {"status": {"a": 1}}):
        report = c.validate_attempt_chain([{**first, **edit}])
        assert report["ok"] is False
        json.dumps(report, allow_nan=False)
    assert not c.validate_attempt_chain([{**first, "attempt_id": H("1") + "\n"}])["ok"]          # a trailing newline is not an attempt id
    assert not c.validate_attempt_chain([{**first, "source_tree_sha256": H("1") + "\n"}])["ok"]


def test_freeze_can_be_bound_to_its_restart_chains():
    cells, records = nine_cells(), []
    for cell in cells:
        kw = dict(view=cell["view"], seed=cell["seed"], source_tree_sha256=cell["source_tree_sha256"], data_identity=cell["data_identity"],
                  environment_id=cell["environment_id"])
        records.append(c.make_attempt_record(attempt_id=cell["attempt_id"], status="COMPLETE", epochs_completed=30, **kw))
    assert c.validate_nine_cell_freeze(cells, attempts=records)["ok"]
    assert not c.validate_nine_cell_freeze(cells, attempts=records[:-1])["ok"]                       # a cell without its attempt
    wrong = copy.deepcopy(records)
    wrong[0] = c.make_attempt_record(attempt_id=cells[0]["attempt_id"], status="INCOMPLETE", epochs_completed=5, view=cells[0]["view"], seed=cells[0]["seed"],
                                     source_tree_sha256=cells[0]["source_tree_sha256"], data_identity=cells[0]["data_identity"], environment_id=cells[0]["environment_id"])
    assert not c.validate_nine_cell_freeze(cells, attempts=wrong)["ok"]                              # the cell's attempt is not COMPLETE
    swapped = copy.deepcopy(records)
    swapped[1] = c.make_attempt_record(attempt_id=cells[1]["attempt_id"], status="COMPLETE", epochs_completed=30, view=cells[2]["view"], seed=cells[2]["seed"],
                                       source_tree_sha256=cells[1]["source_tree_sha256"], data_identity=cells[1]["data_identity"], environment_id=cells[1]["environment_id"])
    assert not c.validate_nine_cell_freeze(cells, attempts=swapped)["ok"]                            # attempt belongs to another view/seed


# ---- resources, environment, lock requirements -------------------------------------------------------------------

def environment():
    return {"schema": c.ENVIRONMENT_SCHEMA, "profile": c.PROFILE, "python": "3.12.15", "numpy": "2.5.4", "scipy": "1.18.1", "torch": "2.14.1+cu130",
            "cuda": "13.0", "cudnn": "9.24.0", "gpu": {"model": "Example GPU", "count": 1, "vram_gib": 24.0, "driver": "580.00"},
            "numerics": {k: v for k, v in APPROVED["numerics"].items() if k != "cuda_cudnn_gpu_driver_pinned"},
            "source": {"git_commit": HEAD, "tree_clean": True, "source_tree_sha256": H("e"), "files_sha256": {"src/geoml/train.py": H("1")}},
            "thread_environment": {name: "2" for name in c.THREAD_VARIABLES}}


CEILINGS = {"wall_hours": 36, "core_hours": 42, "gpu_hours": 30, "working_disk_gib": 25, "backup_disk_gb": 9, "host_ram_gib": 16}
BACKUP = {"path": "/mnt/backup/b2", "device_id": 2, "capacity_gb": 100.0, "verified_manifest_sha256": H("a")}


def lock_requirements():
    return {"schema": c.LOCK_REQUIREMENTS_SCHEMA, "created": False, "authorized": False, "config_sha256": c.approved_config_sha256(),
            "environment": environment(), "ceilings": dict(CEILINGS), "backup": dict(BACKUP), "working_device_id": 1}


def test_complete_environment_and_resource_records_validate_and_authorize_nothing():
    for report in (c.validate_environment_record(environment()), c.validate_resource_ceilings(CEILINGS),
                   c.validate_backup_location(BACKUP, 1), c.validate_lock_requirements(lock_requirements())):
        assert report["ok"] and report["authorizes_nothing"] is True


@pytest.mark.parametrize("path", [("torch",), ("cuda",), ("cudnn",), ("python",), ("gpu",), ("gpu", "model"), ("gpu", "driver"), ("gpu", "vram_gib"),
                                  ("numerics",), ("numerics", "cudnn_tf32_enabled"), ("numerics", "matmul_tf32_enabled"),
                                  ("source",), ("source", "git_commit"), ("source", "source_tree_sha256"), ("source", "files_sha256"),
                                  ("thread_environment",), ("profile",), ("schema",)])
def test_missing_environment_metadata_is_rejected(path):
    assert not c.validate_environment_record(mutate(environment(), path, delete=True))["ok"]


@pytest.mark.parametrize("path,value", [(("torch",), "unknown"), (("cuda",), ""), (("cudnn",), None), (("gpu", "count"), 2), (("gpu", "vram_gib"), 0),
                                        (("gpu", "vram_gib"), float("inf")), (("numerics", "cudnn_tf32_enabled"), True),
                                        (("numerics", "matmul_tf32_enabled"), True), (("numerics", "mixed_precision_enabled"), True),
                                        (("source", "tree_clean"), False), (("source", "git_commit"), "g" * 40),
                                        (("source", "files_sha256"), {}), (("source", "files_sha256"), {"scripts/x.py": H("1")}),
                                        (("thread_environment",), {}), (("profile",), "B2-R6-fp32-tf32-on/1")])
def test_conflicting_environment_metadata_and_tf32_pins_are_rejected(path, value):
    assert not c.validate_environment_record(mutate(environment(), path, value))["ok"]


def test_resource_ceilings_and_backup_must_be_explicit_and_separate():
    for name in c.CEILING_FIELDS:
        assert not c.validate_resource_ceilings(mutate(CEILINGS, (name,), delete=True))["ok"]
        for bad in (0, -1, True, None, float("nan"), "36"):
            assert not c.validate_resource_ceilings(mutate(CEILINGS, (name,), bad))["ok"], (name, bad)
    assert not c.validate_resource_ceilings(mutate(CEILINGS, ("approved",), True))["ok"]
    assert not c.validate_backup_location(BACKUP, 2)["ok"]                                      # same device as the working root
    assert not c.validate_backup_location(mutate(BACKUP, ("capacity_gb",), 4.0), 1)["ok"]
    assert c.validate_backup_location(mutate(BACKUP, ("capacity_gb",), 4.0), 1, minimum_gb=2.0)["ok"]
    assert not c.validate_backup_location(mutate(BACKUP, ("verified_manifest_sha256",), None), 1)["ok"]
    assert not c.validate_backup_location(None, 1)["ok"]


def test_a_lock_requirements_document_can_never_be_or_create_a_lock():
    assert not c.validate_lock_requirements(mutate(lock_requirements(), ("created",), True))["ok"]
    assert not c.validate_lock_requirements(mutate(lock_requirements(), ("lock_fingerprint",), H("1")))["ok"]
    assert not c.validate_lock_requirements(mutate(lock_requirements(), ("authorized",), True))["ok"]
    assert not c.validate_lock_requirements(mutate(lock_requirements(), ("config_sha256",), H("2")))["ok"]
    assert not c.validate_lock_requirements(mutate(lock_requirements(), ("working_device_id",), 2))["ok"]      # backup on the working device
    assert not c.validate_lock_requirements(mutate(lock_requirements(), ("environment", "numerics", "cudnn_tf32_enabled"), True))["ok"]
    assert not c.validate_lock_requirements(mutate(lock_requirements(), ("ceilings", "gpu_hours"), delete=True))["ok"]
    assert not c.validate_lock_requirements(None)["ok"]
    nested = c.validate_lock_requirements(mutate(lock_requirements(), ("environment", "gpu", "model"), ""))
    assert "$.environment.gpu.model" in fields(nested)


# ---- no side effects, no execution path ----------------------------------------------------------------------------

SOURCE = ROOT / "src" / "geoml" / "b2_e9_contract.py"


def test_the_module_imports_only_the_standard_library_and_has_no_io_or_execution_calls():
    tree = ast.parse(SOURCE.read_text())
    imported = {n.names[0].name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import)}
    imported |= {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    assert imported <= {"copy", "hashlib", "json", "math", "re", "types"}, imported
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    for forbidden in ("open", "Path", "subprocess", "os", "sys", "environ", "socket", "torch", "cuda", "Popen", "system", "write_text", "mkdir", "getenv",
                      "time", "datetime", "random", "exec", "eval", "__import__", "input"):
        assert forbidden not in names, forbidden
    builtin_calls = {n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert not builtin_calls & {"exec", "eval", "compile", "open", "__import__", "input"}      # re.compile is an attribute call and harmless
    text = SOURCE.read_text()
    for token in ("clip_grad", "autocast", "GradScaler", "DataLoader", "num_workers", "use_deterministic_algorithms", "cudnn.deterministic",
                  "allow_tf32", "set_float32_matmul_precision"):
        assert token not in text, token


def test_validators_do_not_mutate_their_inputs_or_the_filesystem(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    inputs = [c.approved_config(), PROTOCOL, GATES, nine_cells(), chain(), environment(), dict(CEILINGS), lock_requirements()]
    before = copy.deepcopy(inputs)
    c.validate_scientific_config(inputs[0])
    c.validate_protocol_record(inputs[1])
    c.evaluate_state(protocol=inputs[1], gates=inputs[2], config=inputs[0], evidence=EVIDENCE)
    c.validate_nine_cell_freeze(inputs[3])
    c.validate_attempt_chain(inputs[4])
    c.validate_environment_record(inputs[5])
    c.validate_resource_ceilings(inputs[6])
    c.validate_lock_requirements(inputs[7])
    assert inputs == before and list(tmp_path.iterdir()) == []


def test_the_contract_leaves_existing_caps_profiles_and_names_untouched():
    from geoml import b2_execution
    assert b2_execution.PROFILES == ("proposed-full", "fixture") and b2_execution.CAPS["width"] == 8
    assert c.CONTRACT == "B2-E9-guarded-executor-contract/1" and c.PROFILE == PROTOCOL["profile_id"]


# ---- review-driven hardening: reference immutability, strictness, record cross-checks --------------------------

def test_the_reference_cannot_be_rewritten_in_process():
    c.APPROVED_CONFIG["numerics"]["cudnn_tf32_enabled"] = True           # a careless fixture mutating the convenience copy
    c.APPROVED_CONFIG["model"]["width"] = 8
    try:
        assert c.validate_scientific_config(c.approved_config())["ok"] is True
        assert c.validate_scientific_config(mutate(c.approved_config(), ("numerics", "cudnn_tf32_enabled"), True))["ok"] is False
        assert c.approved_config_sha256() == c.APPROVED_CONFIG_SHA256
        fresh = c.approved_config()
        fresh["model"]["width"] = 4
        assert c.approved_config()["model"]["width"] == 16
    finally:
        c.APPROVED_CONFIG.update(c.approved_config())
    with pytest.raises(TypeError):
        c.TRANSITIONS["NOT_AUTHORIZED"] = ("RUNNABLE",)
    with pytest.raises(TypeError):
        c.ACTION_GATES["gpu_probe"] = "x"
    cells = nine_cells()
    c.cell_calibration()["clean_alarm_pfa"] = 1.0                       # copies, not shared state
    assert c.validate_nine_cell_freeze(cells)["ok"]


def test_integer_and_boolean_fields_are_not_interchangeable_with_floats():
    for path, value in ((("model", "width"), 16.0), (("training", "epochs"), 30.0), (("streaming", "window_shards"), 4.0), (("restart", "restart_epoch"), 0.0),
                        (("scheduler", "div_factor"), 25.0)):
        assert not c.validate_scientific_config(mutate(APPROVED, path, value))["ok"], path
    assert not c.validate_scientific_config(mutate(APPROVED, ("seeds",), [0.0, 1.0, 2.0]))["ok"]
    assert c.validate_scientific_config(mutate(APPROVED, ("loss", "plan_loss_weight"), 1))["ok"]            # a float field accepts an exact integer


def test_reports_stay_strict_json_for_every_kind_of_hostile_value():
    hostile = float("nan")
    for report in (c.validate_scientific_config(mutate(APPROVED, ("numerics", "foo"), hostile)), c.validate_scientific_config(mutate(APPROVED, ("views",), [hostile])),
                   c.validate_scientific_config(mutate(APPROVED, ("model",), {"width": hostile})), c.validate_scientific_config({"x": object}),
                   c.validate_nine_cell_freeze([{**nine_cells()[0], "extra": hostile}] * 9), c.validate_environment_record(mutate(environment(), ("gpu", "x"), hostile))):
        json.dumps(report, allow_nan=False)
        assert report["ok"] is False


@pytest.mark.parametrize("value", ["2026-99-99T99:99:99Z", "2026-02-30T00:00:00Z", "2026-13-01T00:00:00Z", "2026-01-01T24:00:00Z", "2026-01-01T00:60:00Z",
                                   "2026-01-01T00:00:00", "yesterday", "2026-01-01T00:00:00Z\n", "", None, 5])
def test_approval_timestamps_must_be_real_calendar_instants(value):
    gates = mutate(with_approvals(GATES, "full_generation"), ("decisions", "full_generation", "approval", "approved_at"), value)
    assert c.authorization_status("generation", gates)["status"] == c.NOT_AUTHORIZED
    assert c.approval_problems({"approved_by": "x", "approved_at": value, "decision": "d", "record": "r"})


def test_leap_days_are_handled_and_valid_instants_pass():
    for ok in ("2028-02-29T10:00:00Z", "2026-12-31T23:59:59.123+02:00", "2026-10-24T11:14:11.155Z"):
        assert not c.approval_problems({"approved_by": "x", "approved_at": ok, "decision": "d", "record": "r"})
    assert c.approval_problems({"approved_by": "x", "approved_at": "2026-02-29T10:00:00Z", "decision": "d", "record": "r"})
    assert c.approval_problems({"approved_by": "x", "approved_at": "1900-02-29T10:00:00Z", "decision": "d", "record": "r"})
    assert not c.approval_problems({"approved_by": "x", "approved_at": "2000-02-29T10:00:00Z", "decision": "d", "record": "r"})


@pytest.mark.parametrize("flag", [True, 1, 0, None, "no", [], {}])
def test_any_launch_flag_other_than_false_is_an_inconsistency(flag):
    assert state(production_launch_enabled=flag)["state"] == c.NOT_AUTHORIZED


def test_the_scientific_gate_approval_must_name_the_same_approver_and_record():
    for field, other in (("record", "docs/plan/other.md"), ("approved_by", "someone")):
        gates = mutate(GATES, ("decisions", "K17d", "approval", field), other)
        assert any("does not match" in item for item in c.scientific_gate_problems(gates, PROTOCOL)) and state(gates=gates)["state"] == c.NOT_AUTHORIZED


def test_evidence_must_be_positive_integer_runs_and_the_result_says_no_executor_exists():
    for broken in (mutate(EVIDENCE, ("exact_head_ci", "run_id"), 0), mutate(EVIDENCE, ("exact_head_ci", "run_id"), True),
                   mutate(EVIDENCE, ("exact_head_ci", "run_id"), -3), mutate(EVIDENCE, ("independent_review", "open_material_findings"), False)):
        assert state(evidence=broken)["state"] == c.ENGINEERING_READY
    result = state()
    assert result["executor_implemented"] is False and "no executor exists" in result["caveat"] and result["state"] == c.AWAITING_SEPARATE_APPROVAL


def test_the_memorandum_twin_must_agree_when_it_is_supplied():
    assert state(memo=MEMO)["state"] == c.AWAITING_SEPARATE_APPROVAL
    twin = mutate(MEMO, ("decisions", "K18", "status"), "PENDING_RESEARCHER")
    result = state(memo=twin)
    assert result["state"] == c.NOT_AUTHORIZED and any("memorandum twin" in item for item in result["reasons"])
    assert c.memo_twin_problems(GATES, {}) and c.memo_twin_problems({}, MEMO)


def test_decisions_must_agree_with_the_reference_and_the_parameter_records():
    for path, value in ((("decisions", "R2", "width"), 32), (("decisions", "R5", "batch_size"), 8), (("decisions", "R5", "auto_fallback"), True),
                        (("decisions", "R6", "cudnn_allow_tf32"), True), (("decisions", "R6", "autocast"), True), (("decisions", "R6", "matmul_allow_tf32"), True),
                        (("decisions", "K17d", "co_feed_missing_groups"), 99), (("decisions", "K17d", "headline_groups"), 499),
                        (("decisions", "K17d", "remaining_sensitivity_groups"), 400), (("decisions", "K17d", "rule"), "carrier dropped"),
                        (("decisions", "R1", "n_fits"), 3), (("decisions", "R1", "seeds"), [0, 1]), (("decisions", "R4", "early_stopping"), True),
                        (("decisions", "R4", "epochs"), 20), (("decisions", "R7", "window_shards"), 2), (("decisions", "R9", "restart_epoch"), 5),
                        (("decisions", "R8", "phases"), ["train-only"]), (("decisions", "R3", "plan_consistency"), False),
                        (("decisions", "K18", "loss"), "CE"), (("decisions", "OBS-CANCEL-2", "receiver"), "obs-cancel/2")):
        assert not c.validate_protocol_record(mutate(PROTOCOL, path, value))["ok"], path
    for path in (("parameter_records", "checkpoint_selection_rule", "value"), ("parameter_records", "epochs_selection_procedure", "value"),
                 ("parameter_records", "interruption_policy", "value"), ("parameter_records", "test_evaluation_coupling", "value"),
                 ("parameter_records", "loss_composition", "value")):
        assert not c.validate_protocol_record(mutate(PROTOCOL, path, "reworded"))["ok"], path
    for path, value in ((("parameter_records", "calibration", "value", "quantile"), "lower"),
                        (("parameter_records", "optimizer", "value", "decay_applies_to"), "only convolutions"),
                        (("parameter_records", "learning_rate_schedule", "value", "base_momentum"), 0.5),
                        (("parameter_records", "learning_rate_schedule", "value", "initial_lr"), 1),
                        (("parameter_records", "precision_and_determinism", "value", "worker_policy"), "dataloader workers 8"),
                        (("parameter_records", "plan_shift_augmentation", "value", "scope"), "also test"),
                        (("parameter_records", "mirror_roll_augmentation", "value", "roll"), "per sample"),
                        (("parameter_records", "mahalanobis_fit", "value", "statistics"), "test embeddings")):
        assert not c.validate_protocol_record(mutate(PROTOCOL, path, value))["ok"], path


def test_every_requirement_of_the_markdown_and_json_records_is_a_configuration_field():
    for path in (("training", "auto_batch_reduction"), ("training", "checkpoint_tie_rule"), ("optimizer", "weight_decay_scope"), ("scheduler", "base_momentum"),
                 ("scheduler", "max_momentum"), ("scheduler", "initial_lr"), ("scheduler", "final_lr"), ("augmentation", "plan_shift_scope"),
                 ("augmentation", "plan_shift_distribution"), ("augmentation", "plan_shift_selection"), ("streaming", "remainder_policy"),
                 ("streaming", "log_shard_orders_and_hashes"), ("streaming", "worker_policy"), ("streaming", "global_shuffle_equivalence_claimed"),
                 ("calibration", "acceptance_rule"), ("calibration", "alarm_rule"), ("calibration", "calibration_data"),
                 ("calibration", "mahalanobis_statistics"), ("numerics", "cuda_cudnn_gpu_driver_pinned")):
        assert ("$." + ".".join(path), "MISSING") in codes(c.validate_scientific_config(mutate(APPROVED, path, delete=True))), path
        assert not c.validate_scientific_config(mutate(APPROVED, path, "changed" if isinstance(_get(APPROVED, path), str) else (not _get(APPROVED, path)
                                                      if isinstance(_get(APPROVED, path), bool) else 99)))["ok"], path


def _get(base, path):
    for part in path:
        base = base[part]
    return base


def test_environment_and_lock_documents_are_strict_about_extra_keys_and_pinned_versions():
    for edit in (("allow", True), ("numerics_extra", 1)):
        assert not c.validate_environment_record({**environment(), edit[0]: edit[1]})["ok"]
    assert not c.validate_environment_record(mutate(environment(), ("gpu", "tf32"), True))["ok"]
    assert not c.validate_environment_record(mutate(environment(), ("source", "dirty_ok"), True))["ok"]
    for name in ("torch", "cuda", "cudnn", "python", "numpy", "scipy"):
        for bad in ("latest", "x", "2", "2.14.1 ", "2.14.1\n", "v2.14"):
            assert not c.validate_environment_record(mutate(environment(), (name,), bad))["ok"], (name, bad)
    assert not c.validate_environment_record(mutate(environment(), ("gpu", "driver"), "latest"))["ok"]
    assert not c.validate_environment_record(mutate(environment(), ("thread_environment",), {"OMP_NUM_THREADS": "2"}))["ok"]
    assert not c.validate_environment_record(mutate(environment(), ("source", "files_sha256"), {"src/../../etc/x": H("1")}))["ok"]
    for extra in ("run_token", "approved", "lock", "lock_fingerprint"):
        assert not c.validate_lock_requirements({**lock_requirements(), extra: True})["ok"], extra
    assert not c.validate_backup_location({**BACKUP, "mounted": True}, 1)["ok"]
    assert not c.validate_backup_location(mutate(BACKUP, ("verified_manifest_sha256",), H("a") + "\n"), 1)["ok"]
    assert not c.validate_resource_ceilings({**CEILINGS, "approved": True})["ok"]

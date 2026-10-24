"""B2 E9 guarded-executor contract: pure, non-executing validation (P34).

Nothing in this module starts, enables or prepares production work. It holds the approved scientific configuration as
data, validates records that a FUTURE executor and lock must satisfy, and offers one guard that always refuses. It imports
only the standard library, reads no file, environment variable, network, GPU or clock, and writes nothing.

* Scientific approval (OBS-CANCEL/2, K17d, K18, R1-R10) is one thing; permission to run generation, a GPU probe, full
  training or LOKO is four other things. Each runtime authorization is evaluated on its own gate and none can become
  runnable here: the state model ends at ``AWAITING_SEPARATE_APPROVAL`` and :func:`guard_execution` always raises.
* Field names for numeric flags differ on purpose from the torch attribute names (``cudnn_tf32_enabled`` rather than the
  library attribute), so that the repository fact scan that proves "no source pins numerics yet" keeps its meaning: the
  executor milestone that really sets the flags must trip that scan and update it deliberately.
* ``PRODUCTION_LAUNCH_ENABLED`` of the supervisor is not touched; callers may pass its value in and a True value is
  treated as an inconsistency, not as a permission.
"""
import copy
import hashlib
import json
import math
import re

CONTRACT = "B2-E9-guarded-executor-contract/1"
PROFILE = "B2-R6-fp32-tf32-off/1"
CONFIG_SCHEMA = "B2-E9-production-config-contract/1"

NOT_AUTHORIZED = "NOT_AUTHORIZED"
ENGINEERING_READY = "ENGINEERING_READY"
AWAITING_SEPARATE_APPROVAL = "AWAITING_SEPARATE_APPROVAL"
STATES = (NOT_AUTHORIZED, ENGINEERING_READY, AWAITING_SEPARATE_APPROVAL)
# No runnable or running state exists. A transition to one is a code change of a later, separately reviewed milestone.
TRANSITIONS = {NOT_AUTHORIZED: (ENGINEERING_READY,), ENGINEERING_READY: (AWAITING_SEPARATE_APPROVAL, NOT_AUTHORIZED),
               AWAITING_SEPARATE_APPROVAL: (NOT_AUTHORIZED,)}

ACTIONS = ("generation", "gpu_probe", "full_training", "loko")
ACTION_GATES = {"generation": "full_generation", "gpu_probe": None, "full_training": "full_gpu_training", "loko": "full_loko_sweep"}
SCIENTIFIC_GATES = ("K18", "K17d", "OBS-CANCEL-2")
CEILING_FIELDS = ("wall_hours", "core_hours", "gpu_hours", "working_disk_gib", "backup_disk_gb", "host_ram_gib")
APPROVAL_FIELDS = ("approved_by", "approved_at", "decision", "record")
NEEDS_CEILINGS = ("wall_hours", "core_hours", "working_disk_gib", "backup_disk_gb")     # as in the preflight gate check
BACKUP_MIN_GB = 9.0                                  # E5 proposal, a plan figure and not an approved ceiling
ATTEMPT_STATUSES = ("INCOMPLETE", "COMPLETE")
VIEWS = ("co", "dual", "dual_residual")
SEEDS = (0, 1, 2)

APPROVED_CONFIG = {
    "schema": CONFIG_SCHEMA, "profile": PROFILE, "receiver": "obs-cancel/1",
    "views": ["co", "dual", "dual_residual"], "seeds": [0, 1, 2],
    "model": {"width": 16, "time_pool": 2, "level": "carrier"},
    "training": {"epochs": 30, "batch_size": 32, "early_stopping": False, "train_observations": 12000,
                 "optimizer_steps_per_fit": 11250, "checkpoint_rule": "first_best_val_select_macro_f1"},
    "loss": {"center_loss_weight": 0.005, "plan_loss_weight": 1.0, "plan_consistency": True,
             "center_term": "batch_mean_of_summed_squared_distance", "train_diagnostics": "observation_only"},
    "augmentation": {"plan_shift_fraction": 0.15, "plan_shift_max_hz": 500000.0, "mirror_probability": 0.5,
                     "roll": "one_circular_time_shift_per_batch"},
    "optimizer": {"name": "AdamW", "peak_lr": 0.001, "weight_decay": 0.0001, "betas": [0.9, 0.999], "eps": 1e-08,
                  "param_groups": 1, "gradient_clipping": "none"},
    "scheduler": {"name": "OneCycleLR", "max_lr": 0.001, "pct_start": 0.3, "anneal_strategy": "cos", "div_factor": 25,
                  "final_div_factor": 10000, "three_phase": False, "cycle_momentum": True, "step": "per_optimizer_step"},
    "numerics": {"precision": "fp32", "mixed_precision_enabled": False, "cudnn_tf32_enabled": False,
                 "matmul_tf32_enabled": False, "deterministic_algorithms": False},
    "streaming": {"groups_per_shard": 4, "window_shards": 4, "sample_order": "seeded_blocked_shuffle"},
    "isolation": {"phases": ["train-only", "known-only-calibrate", "freeze-nine-cells", "once-only-read-only-evaluate"],
                  "heldout_read_before_freeze": False, "test_driven_retuning": False},
    "restart": {"policy": "restart_epoch_zero", "restart_epoch": 0, "new_attempt_id": True, "carry_partial_state": False,
                "incomplete_status": "INCOMPLETE"},
    "calibration": {"known_acceptance_target": 0.95, "clean_alarm_pfa": 0.05, "mahalanobis_shrinkage": 0.1,
                    "quantile": "higher_empirical_known_only_val_calib"},
}

HEX64, HEX40 = re.compile(r"^[0-9a-f]{64}$"), re.compile(r"^[0-9a-f]{40}$")
ATTEMPT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{5,63}$")


class ContractError(ValueError):
    """A contract was malformed or violated."""


class ExecutionNotAuthorized(ContractError):
    """Raised by every execution guard in this build: there is no runnable state."""


def approved_config():
    return copy.deepcopy(APPROVED_CONFIG)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def sha256_of(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


# ---- findings --------------------------------------------------------------------------------------------------

def _fail(out, field, code, expected=None, actual=None):
    out.append({"field": field, "code": code, "expected": expected, "actual": actual})


def _report(kind, failures, **extra):
    """Strict-JSON report. ``authorizes_nothing`` is fixed: a valid record is never a permission."""
    return {"contract": CONTRACT, "kind": kind, "ok": not failures, "failures": failures, "authorizes_nothing": True, **extra}


def require_ok(report):
    if not report["ok"]:
        raise ContractError(f"{report['kind']}: " + "; ".join(f"{f['field']} {f['code']}" for f in report["failures"][:8]))
    return report


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _compare(path, actual, expected, out):
    """Exact structural comparison: missing, unexpected, conflicting and wrongly typed fields are separate findings."""
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return _fail(out, path, "TYPE", "object", type(actual).__name__)
        for key, want in expected.items():
            if key not in actual:
                _fail(out, f"{path}.{key}", "MISSING", want)
            else:
                _compare(f"{path}.{key}", actual[key], want, out)
        for key in actual:
            if key not in expected:
                _fail(out, f"{path}.{key}", "UNEXPECTED", None, actual[key])
    elif isinstance(expected, list):
        if not isinstance(actual, list) or len(actual) != len(expected):
            return _fail(out, path, "CONFLICT", expected, actual)
        for index, (have, want) in enumerate(zip(actual, expected)):
            _compare(f"{path}[{index}]", have, want, out)
    elif isinstance(expected, bool):
        if not isinstance(actual, bool):
            _fail(out, path, "TYPE", "bool", type(actual).__name__)
        elif actual is not expected:
            _fail(out, path, "CONFLICT", expected, actual)
    elif expected is None:
        if actual is not None:
            _fail(out, path, "CONFLICT", None, actual)
    elif isinstance(expected, str):
        if not isinstance(actual, str):
            _fail(out, path, "TYPE", "string", type(actual).__name__)
        elif actual != expected:
            _fail(out, path, "CONFLICT", expected, actual)
    elif _number(expected):
        if not _number(actual):
            _fail(out, path, "TYPE", "number", type(actual).__name__)
        elif not math.isfinite(actual):
            _fail(out, path, "NONFINITE", expected, repr(actual))
        elif actual != expected:
            _fail(out, path, "CONFLICT", expected, actual)
    else:                                                                # pragma: no cover - the reference holds no other types
        _fail(out, path, "INVALID", repr(expected), repr(actual))


# ---- 1. scientific configuration -------------------------------------------------------------------------------

def validate_scientific_config(config):
    """The explicit production configuration must equal the approved one in every critical field. Pure; runs nothing."""
    failures = []
    if not isinstance(config, dict):
        _fail(failures, "$", "TYPE", "object", type(config).__name__)
    else:
        _compare("$", config, APPROVED_CONFIG, failures)
        training = config.get("training")
        if isinstance(training, dict) and _number(training.get("batch_size")) and _number(training.get("epochs")) \
                and training.get("batch_size") and _number(training.get("train_observations")):
            steps = training["epochs"] * -(-training["train_observations"] // training["batch_size"])
            if training.get("optimizer_steps_per_fit") != steps:
                _fail(failures, "$.training.optimizer_steps_per_fit", "CONFLICT", steps, training.get("optimizer_steps_per_fit"))
        optimizer, scheduler = config.get("optimizer"), config.get("scheduler")
        if isinstance(optimizer, dict) and isinstance(scheduler, dict) and optimizer.get("peak_lr") != scheduler.get("max_lr"):
            _fail(failures, "$.scheduler.max_lr", "CONFLICT", optimizer.get("peak_lr"), scheduler.get("max_lr"))
    return _report("scientific_config", failures, config_sha256=sha256_of(config) if _is_jsonable(config) else None)


def _is_jsonable(value):
    try:
        canonical(value)
        return True
    except (TypeError, ValueError):
        return False


def _by_stem(record, stem):
    """The approved record names its numeric flags after the library attributes; they are matched by stem here so that this
    module never spells those attribute names (the repository scan for 'no source pins numerics yet' stays meaningful)."""
    hits = [value for key, value in record.items() if key.startswith(stem)]
    if len(hits) != 1:
        raise ContractError(f"the approved numerics record must hold exactly one field starting with {stem!r}")
    return hits[0]


def config_from_protocol(protocol):
    """Build the explicit configuration from the approved scientific record (so that the record, not a copy, is the source)."""
    try:
        records, decisions = protocol["parameter_records"], protocol["decisions"]
        value = lambda key: records[key]["value"]                                    # noqa: E731
        optimizer, schedule, numerics = value("optimizer"), value("learning_rate_schedule"), value("precision_and_determinism")
        shift, mirror = value("plan_shift_augmentation"), value("mirror_roll_augmentation")
        calibration, restart, isolation = decisions["R10"], decisions["R9"], decisions["R8"]
        return {
            "schema": CONFIG_SCHEMA, "profile": protocol["profile_id"], "receiver": decisions["OBS-CANCEL-2"]["receiver"],
            "views": value("views"), "seeds": value("training_seed_values"),
            "model": {"width": value("model_width"), "time_pool": value("time_pool"), "level": value("level")},
            "training": {"epochs": value("epochs"), "batch_size": value("batch_size"), "early_stopping": decisions["R4"]["early_stopping"],
                         "train_observations": 12000, "optimizer_steps_per_fit": value("epochs") * -(-12000 // value("batch_size")),
                         "checkpoint_rule": "first_best_val_select_macro_f1" if "first" in decisions["R4"]["checkpoint"] else decisions["R4"]["checkpoint"]},
            "loss": {"center_loss_weight": value("center_loss_weight"), "plan_loss_weight": value("plan_loss_weight"),
                     "plan_consistency": decisions["R3"]["plan_consistency"],
                     "center_term": "batch_mean_of_summed_squared_distance", "train_diagnostics": "observation_only"},
            "augmentation": {"plan_shift_fraction": shift["fraction"], "plan_shift_max_hz": float(shift["max_hz"]),
                             "mirror_probability": 0.5 if mirror["enabled"] and "probability 0.5" in mirror["mirror"] else None,
                             "roll": "one_circular_time_shift_per_batch" if "ONE random shift per mini-batch" in mirror["roll"] else None},
            "optimizer": {"name": optimizer["name"], "peak_lr": optimizer["peak_lr"], "weight_decay": optimizer["weight_decay"],
                          "betas": optimizer["betas"], "eps": optimizer["eps"], "param_groups": optimizer["param_groups"],
                          "gradient_clipping": value("gradient_clipping")},
            "scheduler": {"name": schedule["name"], "max_lr": schedule["max_lr"], "pct_start": schedule["pct_start"],
                          "anneal_strategy": schedule["anneal_strategy"], "div_factor": schedule["div_factor"],
                          "final_div_factor": schedule["final_div_factor"], "three_phase": schedule["three_phase"],
                          "cycle_momentum": schedule["cycle_momentum"],
                          "step": "per_optimizer_step" if "optimizer step" in schedule["step"] else schedule["step"]},
            "numerics": {"precision": numerics["precision"], "mixed_precision_enabled": _by_stem(numerics, "auto"),
                         "cudnn_tf32_enabled": _by_stem(numerics, "cudnn_"), "matmul_tf32_enabled": _by_stem(numerics, "matmul_"),
                         "deterministic_algorithms": numerics["deterministic_algorithms"]},
            "streaming": {"groups_per_shard": value("streaming_groups_per_shard"), "window_shards": value("streaming_window_shards"),
                          "sample_order": "seeded_blocked_shuffle" if "blocked shuffle" in decisions["R7"]["sample_order"] else None},
            "isolation": {"phases": ["train-only", "known-only-calibrate", "freeze-nine-cells", "once-only-read-only-evaluate"]
                          if isolation["phases"] == ["train-only", "known-only calibrate", "freeze nine cells", "one-time read-only evaluate"]
                          else isolation["phases"], "heldout_read_before_freeze": False, "test_driven_retuning": isolation["test_driven_retuning"]},
            "restart": {"policy": "restart_epoch_zero" if restart["restart_epoch"] == 0 else None, "restart_epoch": restart["restart_epoch"],
                        "new_attempt_id": restart["new_attempt_id"], "carry_partial_state": restart["carry_partial_state"],
                        "incomplete_status": restart["incomplete_status"]},
            "calibration": {"known_acceptance_target": calibration["known_acceptance_target"], "clean_alarm_pfa": calibration["clean_alarm_pfa"],
                            "mahalanobis_shrinkage": calibration["mahalanobis_regularization"],
                            "quantile": "higher_empirical_known_only_val_calib"}}
    except (KeyError, TypeError, AttributeError) as error:
        raise ContractError(f"the approved scientific record is incomplete or malformed: {type(error).__name__}: {error}") from error


PROTOCOL_DECISIONS = ("OBS-CANCEL-2", "K17d", "K18") + tuple(f"R{n}" for n in range(1, 11))
PROTOCOL_CHOICES = {"K17d": "A+C"}


def validate_protocol_record(protocol):
    """The researcher's scientific record must say approved, not executable, not production-authorized."""
    failures = []
    if not isinstance(protocol, dict):
        _fail(failures, "$", "TYPE", "object", type(protocol).__name__)
        return _report("protocol_record", failures)
    expectations = {"schema": "B2-E9-scientific-freeze/1", "status": "SCIENTIFIC_PROTOCOL_APPROVED_NOT_EXECUTABLE",
                    "scientific_approval": True, "activation": False, "production_authorized": False, "benchmark_complete": False,
                    "profile_id": PROFILE}
    for key, want in expectations.items():
        if key not in protocol:
            _fail(failures, key, "MISSING", want)
        elif type(protocol[key]) is not type(want) or protocol[key] != want:
            _fail(failures, key, "CONFLICT", want, protocol[key])
    for key in ("approved_by", "approved_at", "approval_record"):
        if not (isinstance(protocol.get(key), str) and protocol[key].strip()):
            _fail(failures, key, "MISSING", "non-empty string", protocol.get(key))
    if not (isinstance(protocol.get("source_main_sha"), str) and HEX40.match(protocol["source_main_sha"])):
        _fail(failures, "source_main_sha", "INVALID", "40 hex characters", protocol.get("source_main_sha"))
    decisions = protocol.get("decisions")
    if not isinstance(decisions, dict):
        _fail(failures, "decisions", "MISSING", "object", type(decisions).__name__)
    else:
        for name in PROTOCOL_DECISIONS:
            record = decisions.get(name)
            if not isinstance(record, dict):
                _fail(failures, f"decisions.{name}", "MISSING", "object", type(record).__name__)
            elif record.get("choice") != PROTOCOL_CHOICES.get(name, "A"):
                _fail(failures, f"decisions.{name}.choice", "CONFLICT", PROTOCOL_CHOICES.get(name, "A"), record.get("choice"))
    open_items = protocol.get("unresolved_operational_decisions")
    expected_open = {"full_generation": "NOT_AUTHORIZED", "gpu_probe": "NOT_AUTHORIZED", "full_gpu_training": "NOT_AUTHORIZED",
                     "full_loko_sweep": "NOT_AUTHORIZED", "production_launch": "DISABLED"}
    if not isinstance(open_items, dict):
        _fail(failures, "unresolved_operational_decisions", "MISSING", expected_open)
    else:
        for key, want in expected_open.items():
            if open_items.get(key) != want:
                _fail(failures, f"unresolved_operational_decisions.{key}", "CONFLICT", want, open_items.get(key))
    controls = protocol.get("controls")
    if not (isinstance(controls, dict) and controls and all(value is True for value in controls.values())):
        _fail(failures, "controls", "CONFLICT", "every control true", controls)
    if not failures:
        try:
            derived = validate_scientific_config(config_from_protocol(protocol))
            failures += derived["failures"]
        except ContractError as error:
            _fail(failures, "parameter_records", "INVALID", None, str(error))
    return _report("protocol_record", failures)


# ---- 2. execution-state contract -------------------------------------------------------------------------------

def transition(current, target):
    """The only legal edges; anything that looks runnable is refused by name."""
    if current not in STATES:
        raise ContractError(f"unknown state {current!r}")
    if target in ("RUNNABLE", "RUNNING", "AUTHORIZED", "LAUNCHED") or target not in STATES:
        raise ContractError(f"{target!r} is not a state of this contract: no transition to runnable execution exists in this build")
    if target not in TRANSITIONS[current]:
        raise ContractError(f"transition {current} -> {target} is not allowed")
    return target


def _iso(value):
    return isinstance(value, str) and re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$", value.strip()) is not None


def approval_problems(approval, needs_ceilings=False):
    """Structural only, like the preflight gate check: it cannot judge whether a person really approved."""
    if not isinstance(approval, dict):
        return ["no approval record"]
    problems = [f"{name} must be a non-empty string" for name in ("approved_by", "decision", "record")
                if not (isinstance(approval.get(name), str) and approval[name].strip())]
    if not _iso(approval.get("approved_at")):
        problems.append("approved_at must be an ISO-8601 timestamp")
    if needs_ceilings:
        for name in NEEDS_CEILINGS:
            value = approval.get(name)
            if not _number(value) or not math.isfinite(value) or value <= 0:
                problems.append(f"{name} must be a finite positive number")
    return problems


def _gate(gates, key):
    decisions = gates.get("decisions") if isinstance(gates, dict) else None
    record = decisions.get(key) if isinstance(decisions, dict) else None
    return record if isinstance(record, dict) else None


def authorization_status(action, gates):
    """Per-action verdict from that action's own gate only. Never runnable: at best an approval record is on file."""
    if action not in ACTIONS:
        raise ContractError(f"unknown action {action!r}")
    key = ACTION_GATES[action]
    if key is None:
        return {"status": NOT_AUTHORIZED, "runnable": False,
                "reasons": ["no gate exists for the bounded GPU probe; it needs its own explicit authorization record"]}
    record = _gate(gates, key)
    if record is None:
        return {"status": NOT_AUTHORIZED, "runnable": False, "reasons": [f"gate {key} is missing"]}
    status, approval = record.get("status"), record.get("approval")
    if status in ("NOT_AUTHORIZED", "PENDING_RESEARCHER"):
        extra = [] if approval in (None, {}) else ["approval material is attached to a gate that is not approved"]
        return {"status": NOT_AUTHORIZED, "runnable": False, "reasons": [f"gate {key} is {status}", *extra], "malformed": bool(extra)}
    if status in ("APPROVED", "AUTHORIZED"):
        problems = approval_problems(approval, needs_ceilings=key.startswith("full_"))
        if problems:
            return {"status": NOT_AUTHORIZED, "runnable": False, "malformed": True,
                    "reasons": [f"gate {key} approval is incomplete: " + "; ".join(problems)]}
        return {"status": "APPROVAL_RECORDED_NOT_RUNNABLE", "runnable": False,
                "reasons": ["an approval record is on file but this build has no executor and no runnable state"]}
    return {"status": NOT_AUTHORIZED, "runnable": False, "malformed": True, "reasons": [f"gate {key} has unknown status {status!r}"]}


def scientific_gate_problems(gates, protocol):
    """K18, K17d and OBS-CANCEL-2 must carry the researcher's recorded approval that the scientific record names."""
    problems = []
    if not isinstance(gates, dict) or gates.get("benchmark_complete") is not False:
        problems.append("gates: benchmark_complete is not false")
    for key in SCIENTIFIC_GATES:
        record = _gate(gates, key)
        if record is None:
            problems.append(f"gate {key} is missing")
            continue
        if record.get("status") != "APPROVED":
            problems.append(f"gate {key} is {record.get('status')!r}, not APPROVED")
            continue
        found = approval_problems(record.get("approval"))
        problems += [f"gate {key}: {item}" for item in found]
        approval = record.get("approval") if isinstance(record.get("approval"), dict) else {}
        if not found and (approval.get("approved_by") != protocol.get("approved_by") or approval.get("record") != protocol.get("approval_record")):
            problems.append(f"gate {key}: approval does not match the scientific record's approver/record")
    return problems


def evaluate_state(*, protocol, gates, config, evidence=None, production_launch_enabled=False):
    """NOT_AUTHORIZED -> ENGINEERING_READY -> AWAITING_SEPARATE_APPROVAL. The result never contains a runnable state."""
    reasons = []
    for label, report in (("protocol", validate_protocol_record(protocol)), ("config", validate_scientific_config(config))):
        reasons += [f"{label}: {f['field']} {f['code']}" for f in report["failures"][:6]]
    reasons += scientific_gate_problems(gates, protocol if isinstance(protocol, dict) else {})
    if production_launch_enabled is not False:
        reasons.append("production launch flag is not False: this contract has no runnable state, so the flag is an inconsistency")
    authorizations = {action: authorization_status(action, gates) for action in ACTIONS}
    reasons += [f"{action}: {item}" for action, verdict in authorizations.items() if verdict.get("malformed") for item in verdict["reasons"]]
    state = NOT_AUTHORIZED
    if not reasons:
        state = transition(NOT_AUTHORIZED, ENGINEERING_READY)
        problems = evidence_problems(evidence)
        if not problems:
            state = transition(state, AWAITING_SEPARATE_APPROVAL)
        else:
            reasons += problems
    return {"contract": CONTRACT, "state": state, "reasons": reasons, "authorizations": authorizations,
            "runtime_permitted": runtime_permitted(), "benchmark_complete": False}


def evidence_problems(evidence):
    """Engineering evidence for the exact source head: independent review without open material findings and exact-head CI."""
    if not isinstance(evidence, dict):
        return ["engineering evidence is missing: no independent review or exact-head CI record"]
    head = evidence.get("source_head")
    problems = [] if isinstance(head, str) and HEX40.match(head) else ["source_head must be 40 hex characters"]
    review, ci = evidence.get("independent_review"), evidence.get("exact_head_ci")
    if not (isinstance(review, dict) and review.get("reviewed_head") == head and review.get("open_material_findings") == 0
            and type(review.get("open_material_findings")) is int and isinstance(review.get("record"), str) and review["record"].strip()):
        problems.append("independent review must name the exact source head, a record, and zero open material findings")
    if not (isinstance(ci, dict) and ci.get("head") == head and ci.get("conclusion") == "success" and type(ci.get("run_id")) is int):
        problems.append("exact-head CI must name the same head with conclusion success and an integer run id")
    return problems


def runtime_permitted():
    """Always False: scientific approval, engineering readiness and any recorded approval never make execution runnable here."""
    return False


def guard_execution(action, **evidence):
    """The call a future executor must make first. In this build it always refuses, after validating the request name."""
    if action not in ACTIONS:
        raise ContractError(f"unknown action {action!r}; known actions: {ACTIONS}")
    raise ExecutionNotAuthorized(f"{action} is not runnable: this contract has no transition to a runnable state; execution needs a "
                                 "later, separately reviewed executor, a source lock, resource ceilings and its own authorization")


# ---- 3. nine-cell freeze contract ------------------------------------------------------------------------------

CELL_FIELDS = ("view", "seed", "attempt_id", "status", "epochs_completed", "selected_epoch", "model_sha256", "scorer_sha256",
               "calibrator_sha256", "training_config_sha256", "data_identity", "source_tree_sha256", "environment_id", "profile",
               "calibration", "heldout_reads")
CELL_COMMON = ("training_config_sha256", "data_identity", "source_tree_sha256", "environment_id", "profile", "calibration")
CELL_CALIBRATION = {"known_acceptance_target": 0.95, "clean_alarm_pfa": 0.05, "mahalanobis_shrinkage": 0.1}


def _hex64(out, path, value):
    if not (isinstance(value, str) and HEX64.match(value)):
        _fail(out, path, "INVALID", "64 lowercase hex characters", value)


def validate_nine_cell_freeze(cells, *, epochs=30):
    """Three views x three seeds with compatible provenance and no held-out read, from metadata only (no artifact is opened)."""
    failures, seen = [], {}
    if not isinstance(cells, list):
        _fail(failures, "cells", "TYPE", "list", type(cells).__name__)
        return _report("nine_cell_freeze", failures, evaluation_admissible=False)
    if len(cells) != 9:
        _fail(failures, "cells", "CONFLICT", 9, len(cells))
    for index, cell in enumerate(cells):
        path = f"cells[{index}]"
        if not isinstance(cell, dict):
            _fail(failures, path, "TYPE", "object", type(cell).__name__)
            continue
        for name in CELL_FIELDS:
            if name not in cell:
                _fail(failures, f"{path}.{name}", "MISSING")
        for name in cell:
            if name not in CELL_FIELDS:
                _fail(failures, f"{path}.{name}", "UNEXPECTED", None, cell[name])
        key = (cell.get("view"), cell.get("seed"))
        if cell.get("view") not in VIEWS or type(cell.get("seed")) is not int or cell.get("seed") not in SEEDS:
            _fail(failures, path, "INVALID", "view in co/dual/dual_residual and seed in 0/1/2", key)
        elif key in seen:
            _fail(failures, path, "CONFLICT", "each view/seed once", f"duplicate {key}")
        else:
            seen[key] = cell
        if "status" in cell and cell["status"] != "COMPLETE":
            _fail(failures, f"{path}.status", "CONFLICT", "COMPLETE", cell["status"])
        if "epochs_completed" in cell and (type(cell["epochs_completed"]) is not int or cell["epochs_completed"] != epochs):
            _fail(failures, f"{path}.epochs_completed", "CONFLICT", epochs, cell["epochs_completed"])
        selected = cell.get("selected_epoch")
        if "selected_epoch" in cell and (type(selected) is not int or not 0 <= selected < epochs):
            _fail(failures, f"{path}.selected_epoch", "INVALID", f"integer in [0, {epochs - 1}]", selected)
        if "heldout_reads" in cell and (type(cell["heldout_reads"]) is not int or cell["heldout_reads"] != 0):
            _fail(failures, f"{path}.heldout_reads", "CONFLICT", 0, cell["heldout_reads"])
        if "attempt_id" in cell and not (isinstance(cell["attempt_id"], str) and ATTEMPT_ID.match(cell["attempt_id"])):
            _fail(failures, f"{path}.attempt_id", "INVALID", "attempt id", cell["attempt_id"])
        if "profile" in cell and cell["profile"] != PROFILE:
            _fail(failures, f"{path}.profile", "CONFLICT", PROFILE, cell["profile"])
        if "calibration" in cell:
            _compare(f"{path}.calibration", cell["calibration"], CELL_CALIBRATION, failures)
        for name in ("model_sha256", "scorer_sha256", "calibrator_sha256", "training_config_sha256", "data_identity",
                     "source_tree_sha256", "environment_id"):
            if name in cell:
                _hex64(failures, f"{path}.{name}", cell[name])
    required = {(view, seed) for view in VIEWS for seed in SEEDS}
    if len(cells) == 9 and set(seen) != required:
        _fail(failures, "cells", "CONFLICT", "all nine view/seed cells", sorted(map(str, required - set(seen))))
    dicts = [c for c in cells if isinstance(c, dict)]
    for name in CELL_COMMON:
        values = {canonical(c[name]) for c in dicts if name in c and _is_jsonable(c[name])}
        if len(values) > 1:
            _fail(failures, name, "CONFLICT", "identical across all nine cells", sorted(values)[:3])
    repeated = False
    for name in ("model_sha256", "scorer_sha256", "calibrator_sha256"):
        hashes = [c[name] for c in dicts if isinstance(c.get(name), str)]
        if len(set(hashes)) != len(hashes):
            repeated = True
            _fail(failures, name, "CONFLICT", "distinct per cell (a renamed or reused artifact is not a new fit)", len(hashes) - len(set(hashes)))
    every = [c[n] for c in dicts for n in ("model_sha256", "scorer_sha256", "calibrator_sha256") if isinstance(c.get(n), str)]
    if not repeated and len(set(every)) != len(every):
        _fail(failures, "artifacts", "CONFLICT", "model, scorer and calibrator hashes all distinct", len(every) - len(set(every)))
    return _report("nine_cell_freeze", failures, evaluation_admissible=not failures, cells_checked=len(dicts))


# ---- 4. restart provenance -------------------------------------------------------------------------------------

ATTEMPT_FIELDS = ("attempt_id", "view", "seed", "status", "start_epoch", "epochs_completed", "parent_attempt_id", "parent_hash",
                  "source_tree_sha256", "data_identity", "environment_id", "carried_state", "record_hash")
CARRIED_NONE = {"optimizer": None, "scheduler": None, "rng": None, "weights": None, "data_cursor": None}


def record_hash(record):
    return sha256_of({k: v for k, v in record.items() if k != "record_hash"})


def make_attempt_record(*, attempt_id, view, seed, status, epochs_completed, source_tree_sha256, data_identity, environment_id,
                        parent=None):
    """Pure builder: always epoch 0, nothing carried, parent hash bound. It validates what it builds."""
    record = {"attempt_id": attempt_id, "view": view, "seed": seed, "status": status, "start_epoch": 0,
              "epochs_completed": epochs_completed, "parent_attempt_id": parent["attempt_id"] if parent else None,
              "parent_hash": record_hash(parent) if parent else None, "source_tree_sha256": source_tree_sha256,
              "data_identity": data_identity, "environment_id": environment_id, "carried_state": dict(CARRIED_NONE)}
    record["record_hash"] = record_hash(record)
    return record


def validate_attempt_chain(records, *, epochs=30):
    """R9: a failed fit is INCOMPLETE; the next attempt restarts at epoch 0 with nothing carried, same source/data/environment."""
    failures, by_id = [], {}
    if not isinstance(records, list):
        _fail(failures, "records", "TYPE", "list", type(records).__name__)
        return _report("attempt_chain", failures)
    for index, record in enumerate(records):
        path = f"records[{index}]"
        if not isinstance(record, dict):
            _fail(failures, path, "TYPE", "object", type(record).__name__)
            continue
        for name in ATTEMPT_FIELDS:
            if name not in record:
                _fail(failures, f"{path}.{name}", "MISSING")
        for name in record:
            if name not in ATTEMPT_FIELDS:
                _fail(failures, f"{path}.{name}", "UNEXPECTED", None, record[name])      # e.g. optimizer_state_sha256, resume_epoch
        attempt_id = record.get("attempt_id")
        if not (isinstance(attempt_id, str) and ATTEMPT_ID.match(attempt_id)):
            _fail(failures, f"{path}.attempt_id", "INVALID", "attempt id", attempt_id)
        elif attempt_id in by_id:
            _fail(failures, f"{path}.attempt_id", "CONFLICT", "unique attempt id", attempt_id)
        else:
            by_id[attempt_id] = record
        if record.get("status") not in ATTEMPT_STATUSES:
            _fail(failures, f"{path}.status", "INVALID", ATTEMPT_STATUSES, record.get("status"))
        if type(record.get("start_epoch")) is not int or record.get("start_epoch") != 0:
            _fail(failures, f"{path}.start_epoch", "CONFLICT", 0, record.get("start_epoch"))
        done = record.get("epochs_completed")
        if type(done) is not int or not 0 <= done <= epochs or (record.get("status") == "COMPLETE") != (done == epochs):
            _fail(failures, f"{path}.epochs_completed", "CONFLICT", f"{epochs} exactly when COMPLETE, otherwise 0..{epochs - 1}", done)
        if "carried_state" in record:
            _compare(f"{path}.carried_state", record["carried_state"], CARRIED_NONE, failures)
        for name in ("source_tree_sha256", "data_identity", "environment_id"):
            if name in record:
                _hex64(failures, f"{path}.{name}", record[name])
        if "record_hash" in record and record["record_hash"] != record_hash(record):
            _fail(failures, f"{path}.record_hash", "CONFLICT", "hash of the record", record["record_hash"])
    children = {}
    for index, record in enumerate(r for r in records if isinstance(r, dict)):
        path, parent_id = f"attempt {record.get('attempt_id')}", record.get("parent_attempt_id")
        if parent_id is None:
            if record.get("parent_hash") is not None:
                _fail(failures, f"{path}.parent_hash", "CONFLICT", None, record["parent_hash"])
            continue
        parent = by_id.get(parent_id)
        if parent is None:
            _fail(failures, f"{path}.parent_attempt_id", "MISSING", "an attempt in the chain", parent_id)
            continue
        children.setdefault(parent_id, []).append(record.get("attempt_id"))
        if record.get("parent_hash") != record_hash(parent):
            _fail(failures, f"{path}.parent_hash", "CONFLICT", "hash of the parent record", record.get("parent_hash"))
        if parent.get("status") != "INCOMPLETE":
            _fail(failures, f"{path}.parent_attempt_id", "CONFLICT", "a restart follows an INCOMPLETE attempt only", parent.get("status"))
        for name in ("view", "seed", "source_tree_sha256", "data_identity", "environment_id"):
            if record.get(name) != parent.get(name):
                _fail(failures, f"{path}.{name}", "CONFLICT", f"same as parent ({parent.get(name)})", record.get(name))
    for parent_id, kids in children.items():
        if len(kids) > 1:
            _fail(failures, f"attempt {parent_id}", "CONFLICT", "at most one restart per incomplete attempt", kids)
    complete = {}
    for record in (r for r in records if isinstance(r, dict) and r.get("status") == "COMPLETE"):
        key = (record.get("view"), record.get("seed"))
        if key in complete:
            _fail(failures, f"cell {key}", "CONFLICT", "at most one COMPLETE attempt per view/seed", [complete[key], record.get("attempt_id")])
        complete[key] = record.get("attempt_id")
    for record in (r for r in records if isinstance(r, dict)):                       # no cycles: walk each chain with a bound
        node, steps = record, 0
        while node and node.get("parent_attempt_id") is not None and steps <= len(records):
            node, steps = by_id.get(node["parent_attempt_id"]), steps + 1
        if steps > len(records):
            _fail(failures, f"attempt {record.get('attempt_id')}", "CONFLICT", "acyclic lineage", "cycle")
            break
    return _report("attempt_chain", failures, completed_cells=sorted(map(str, complete)))


# ---- 5. resources, environment and lock requirements -----------------------------------------------------------

ENVIRONMENT_SCHEMA = "B2-E9-environment-record/1"
LOCK_REQUIREMENTS_SCHEMA = "B2-E9-lock-requirements/1"


def _text(out, path, value):
    if not (isinstance(value, str) and value.strip() and value.strip().lower() not in ("unknown", "none", "null", "n/a")):
        _fail(out, path, "MISSING", "a pinned version or identifier", value)


def validate_environment_record(env):
    """Pinned GPU/CUDA/cuDNN/torch/driver identities and the effective numerics flags. Schema only; reads no machine."""
    failures = []
    if not isinstance(env, dict):
        _fail(failures, "$", "TYPE", "object", type(env).__name__)
        return _report("environment_record", failures)
    shape = {"schema": ENVIRONMENT_SCHEMA, "profile": PROFILE}
    _compare("$", {k: env.get(k) for k in shape}, shape, failures)
    for name in ("python", "numpy", "scipy", "torch", "cuda", "cudnn"):
        _text(failures, f"$.{name}", env.get(name))
    gpu = env.get("gpu")
    if not isinstance(gpu, dict):
        _fail(failures, "$.gpu", "MISSING", "object", gpu)
    else:
        for name in ("model", "driver"):
            _text(failures, f"$.gpu.{name}", gpu.get(name))
        if type(gpu.get("count")) is not int or gpu.get("count") != 1:
            _fail(failures, "$.gpu.count", "CONFLICT", 1, gpu.get("count"))
        vram = gpu.get("vram_gib")
        if not _number(vram) or not math.isfinite(vram) or vram <= 0:
            _fail(failures, "$.gpu.vram_gib", "INVALID", "finite positive number", vram)
    numerics = env.get("numerics")
    if not isinstance(numerics, dict):
        _fail(failures, "$.numerics", "MISSING", "the effective flags", numerics)
    else:
        _compare("$.numerics", numerics, APPROVED_CONFIG["numerics"], failures)
    source = env.get("source")
    if not isinstance(source, dict):
        _fail(failures, "$.source", "MISSING", "object", source)
    else:
        if not (isinstance(source.get("git_commit"), str) and HEX40.match(source["git_commit"])):
            _fail(failures, "$.source.git_commit", "INVALID", "40 hex characters", source.get("git_commit"))
        if source.get("tree_clean") is not True:
            _fail(failures, "$.source.tree_clean", "CONFLICT", True, source.get("tree_clean"))
        _hex64(failures, "$.source.source_tree_sha256", source.get("source_tree_sha256"))
        files = source.get("files_sha256")
        if not (isinstance(files, dict) and files and all(isinstance(k, str) and k.startswith("src/") for k in files)
                and all(isinstance(v, str) and HEX64.match(v) for v in files.values())):
            _fail(failures, "$.source.files_sha256", "INVALID", "non-empty mapping of src/ paths to sha256", files if not isinstance(files, dict) else len(files))
    threads = env.get("thread_environment")
    if not (isinstance(threads, dict) and threads):
        _fail(failures, "$.thread_environment", "MISSING", "recorded thread variables", threads)
    return _report("environment_record", failures)


def validate_resource_ceilings(ceilings):
    """Explicit positive ceilings. Well-formed numbers are a request for review, not a reservation."""
    failures = []
    if not isinstance(ceilings, dict):
        _fail(failures, "$", "TYPE", "object", type(ceilings).__name__)
        return _report("resource_ceilings", failures)
    for name in CEILING_FIELDS:
        value = ceilings.get(name)
        if name not in ceilings:
            _fail(failures, f"$.{name}", "MISSING", "finite positive number")
        elif not _number(value) or not math.isfinite(value) or value <= 0:
            _fail(failures, f"$.{name}", "INVALID", "finite positive number", value)
    for name in ceilings:
        if name not in CEILING_FIELDS:
            _fail(failures, f"$.{name}", "UNEXPECTED", None, ceilings[name])
    return _report("resource_ceilings", failures)


def validate_backup_location(backup, working_device, *, minimum_gb=BACKUP_MIN_GB):
    """A backup on the working device is no backup; the minimum is the E5 proposal and is passed in, not assumed approved."""
    failures = []
    if not isinstance(backup, dict):
        _fail(failures, "$", "TYPE", "object", type(backup).__name__)
        return _report("backup_location", failures)
    if not (isinstance(backup.get("path"), str) and backup["path"].strip()):
        _fail(failures, "$.path", "MISSING", "a path", backup.get("path"))
    if type(backup.get("device_id")) is not int:
        _fail(failures, "$.device_id", "INVALID", "integer device id", backup.get("device_id"))
    elif backup["device_id"] == working_device:
        _fail(failures, "$.device_id", "CONFLICT", f"a device other than {working_device}", backup["device_id"])
    capacity = backup.get("capacity_gb")
    if not _number(capacity) or not math.isfinite(capacity) or capacity < minimum_gb:
        _fail(failures, "$.capacity_gb", "INVALID", f"at least {minimum_gb} GB", capacity)
    _hex64(failures, "$.verified_manifest_sha256", backup.get("verified_manifest_sha256"))
    return _report("backup_location", failures)


def validate_lock_requirements(document):
    """What a FUTURE production lock must contain. A document that claims to be a lock is refused: none is created here."""
    failures = []
    if not isinstance(document, dict):
        _fail(failures, "$", "TYPE", "object", type(document).__name__)
        return _report("lock_requirements", failures)
    if document.get("schema") != LOCK_REQUIREMENTS_SCHEMA:
        _fail(failures, "$.schema", "CONFLICT", LOCK_REQUIREMENTS_SCHEMA, document.get("schema"))
    if "lock_fingerprint" in document or document.get("created") is not False:
        _fail(failures, "$.created", "CONFLICT", "created=false and no lock_fingerprint: this contract creates no lock", document.get("created"))
    _hex64(failures, "$.config_sha256", document.get("config_sha256"))
    if document.get("config_sha256") != sha256_of(APPROVED_CONFIG):
        _fail(failures, "$.config_sha256", "CONFLICT", "hash of the approved explicit configuration", document.get("config_sha256"))
    for name, check in (("environment", validate_environment_record), ("ceilings", validate_resource_ceilings)):
        sub = check(document.get(name))
        failures += [{**f, "field": f"$.{name}{f['field'][1:]}"} for f in sub["failures"]]
    backup = document.get("backup")
    working = document.get("working_device_id")
    if type(working) is not int:
        _fail(failures, "$.working_device_id", "INVALID", "integer device id", working)
    else:
        sub = validate_backup_location(backup, working)
        failures += [{**f, "field": f"$.backup{f['field'][1:]}"} for f in sub["failures"]]
    if document.get("authorized") is not False:
        _fail(failures, "$.authorized", "CONFLICT", False, document.get("authorized"))
    return _report("lock_requirements", failures)

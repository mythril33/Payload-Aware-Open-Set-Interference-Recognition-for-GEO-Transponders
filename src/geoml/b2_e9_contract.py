"""B2 E9 guarded-executor contract: pure, non-executing validation (P34).

Nothing in this module starts, enables or prepares production work. It holds the approved scientific configuration as
data, validates records that a FUTURE executor and lock must satisfy, and offers one guard that always refuses. It imports
only the standard library, reads no file, environment variable, network, GPU or clock, and writes nothing.

* Scientific approval (OBS-CANCEL/2, K17d, K18, R1-R10) is one thing; permission to run generation, a GPU probe, full
  training or LOKO is four other things. Each runtime authorization is evaluated on its own gate and none can become
  runnable here: the state model ends at ``AWAITING_SEPARATE_APPROVAL`` and :func:`guard_execution` always raises.
  Those state names mean "the records are consistent", never "an executor exists": every result says so.
* Field names for numeric flags differ on purpose from the torch attribute names (``cudnn_tf32_enabled`` rather than the
  library attribute), so that the repository fact scan that proves "no source pins numerics yet" keeps its meaning: the
  executor milestone that really sets the flags must trip that scan and update it deliberately.
* The reference configuration is stored as an immutable canonical string with a literal digest; validators always work on
  a fresh copy, so no caller can rewrite what "approved" means in-process.
* Validators check records, not machines or artifacts. Hashes, heads, reviews and approvals inside them are self-asserted
  JSON; digests detect accident, not forgery.
"""
import copy
import hashlib
import json
import math
import re
from types import MappingProxyType

CONTRACT = "B2-E9-guarded-executor-contract/1"
PROFILE = "B2-R6-fp32-tf32-off/1"
CONFIG_SCHEMA = "B2-E9-production-config-contract/1"

NOT_AUTHORIZED = "NOT_AUTHORIZED"
ENGINEERING_READY = "ENGINEERING_READY"
AWAITING_SEPARATE_APPROVAL = "AWAITING_SEPARATE_APPROVAL"
STATES = (NOT_AUTHORIZED, ENGINEERING_READY, AWAITING_SEPARATE_APPROVAL)
# No runnable or running state exists. A transition to one is a code change of a later, separately reviewed milestone.
TRANSITIONS = MappingProxyType({NOT_AUTHORIZED: (ENGINEERING_READY,), ENGINEERING_READY: (AWAITING_SEPARATE_APPROVAL, NOT_AUTHORIZED),
                                AWAITING_SEPARATE_APPROVAL: (NOT_AUTHORIZED,)})

ACTIONS = ("generation", "gpu_probe", "full_training", "loko")
ACTION_GATES = MappingProxyType({"generation": "full_generation", "gpu_probe": None, "full_training": "full_gpu_training",
                                 "loko": "full_loko_sweep"})
SCIENTIFIC_GATES = ("K18", "K17d", "OBS-CANCEL-2")
CEILING_FIELDS = ("wall_hours", "core_hours", "gpu_hours", "working_disk_gib", "backup_disk_gb", "host_ram_gib")
APPROVAL_FIELDS = ("approved_by", "approved_at", "decision", "record")
NEEDS_CEILINGS = ("wall_hours", "core_hours", "working_disk_gib", "backup_disk_gb")     # as in the preflight gate check
BACKUP_MIN_GB = 9.0                                  # E5 proposal, a plan figure and not an approved ceiling
ATTEMPT_STATUSES = ("INCOMPLETE", "COMPLETE")
VIEWS = ("co", "dual", "dual_residual")
SEEDS = (0, 1, 2)

# The approved explicit configuration, as canonical JSON. Fields marked (pinned) are not machine-readable in the approved
# JSON record (they come from its markdown or from the frozen protocol) and are pinned here; the tests compare them with the
# markdown record. Everything else is derived from the JSON record by config_from_protocol and compared in the tests.
_APPROVED_JSON = (
    '{"augmentation":{"mirror_probability":0.5,"plan_shift_distribution":"continuous_uniform_symmetric","plan_shift_fraction":0.15,'
    '"plan_shift_max_hz":500000.0,"plan_shift_scope":"training_only","plan_shift_selection":"bernoulli_per_sample_per_batch",'
    '"roll":"one_circular_time_shift_per_batch"},'
    '"calibration":{"acceptance_rule":"score_le_threshold","alarm_rule":"score_gt_threshold_on_one_minus_p_clean",'
    '"calibration_data":"known_val_calib_only","clean_alarm_pfa":0.05,"known_acceptance_target":0.95,'
    '"mahalanobis_shrinkage":0.1,"mahalanobis_statistics":"train_role_eval_mode_class_conditional_embeddings",'
    '"quantile":"higher_empirical_known_only_val_calib"},'
    '"isolation":{"heldout_read_before_freeze":false,'
    '"phases":["train-only","known-only-calibrate","freeze-nine-cells","once-only-read-only-evaluate"],"test_driven_retuning":false},'
    '"loss":{"center_loss_weight":0.005,"center_term":"batch_mean_of_summed_squared_distance","plan_consistency":true,'
    '"plan_loss_weight":1.0,"train_diagnostics":"observation_only"},'
    '"model":{"level":"carrier","time_pool":2,"width":16},'
    '"numerics":{"cuda_cudnn_gpu_driver_pinned":true,"cudnn_tf32_enabled":false,"deterministic_algorithms":false,'
    '"matmul_tf32_enabled":false,"mixed_precision_enabled":false,"precision":"fp32"},'
    '"optimizer":{"betas":[0.9,0.999],"eps":1e-08,"gradient_clipping":"none","name":"AdamW","param_groups":1,"peak_lr":0.001,'
    '"weight_decay":0.0001,"weight_decay_scope":"all_parameters"},'
    '"profile":"B2-R6-fp32-tf32-off/1","receiver":"obs-cancel/1",'
    '"restart":{"carry_partial_state":false,"incomplete_status":"INCOMPLETE","new_attempt_id":true,"policy":"restart_epoch_zero",'
    '"restart_epoch":0},'
    '"scheduler":{"anneal_strategy":"cos","base_momentum":0.85,"cycle_momentum":true,"div_factor":25,"final_div_factor":10000,'
    '"final_lr":4e-09,"initial_lr":4e-05,"max_lr":0.001,"max_momentum":0.95,"name":"OneCycleLR","pct_start":0.3,'
    '"step":"per_optimizer_step","three_phase":false},'
    '"schema":"B2-E9-production-config-contract/1","seeds":[0,1,2],'
    '"streaming":{"global_shuffle_equivalence_claimed":false,"groups_per_shard":4,"log_shard_orders_and_hashes":true,'
    '"remainder_policy":"carry_short_batch_across_windows","sample_order":"seeded_blocked_shuffle","window_shards":4,'
    '"worker_policy":"synchronous"},'
    '"training":{"auto_batch_reduction":false,"batch_size":32,"checkpoint_rule":"first_best_val_select_macro_f1",'
    '"checkpoint_tie_rule":"strict_greater_keeps_first_maximum","early_stopping":false,"epochs":30,"optimizer_steps_per_fit":11250,'
    '"train_observations":12000},'
    '"views":["co","dual","dual_residual"]}')
APPROVED_CONFIG_SHA256 = "75864cc6d1a16c6d39cf5218862f1d5166641b6260424b8e922cb6332c0b50fc"      # literal digest of the canonical approved configuration; tests compare it with the record
HEX64, HEX40 = re.compile(r"[0-9a-f]{64}"), re.compile(r"[0-9a-f]{40}")
ATTEMPT_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{5,63}")
VERSION = re.compile(r"[0-9]+(\.[0-9]+)+([+.][0-9A-Za-z]+)*")
THREAD_VARIABLES = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "PYTHONHASHSEED")


class ContractError(ValueError):
    """A contract was malformed or violated."""


class ExecutionNotAuthorized(ContractError):
    """Raised by every execution guard in this build: there is no runnable state."""


def approved_config():
    """A fresh copy of the approved explicit configuration; mutating it affects nothing."""
    return json.loads(_APPROVED_JSON)


APPROVED_CONFIG = approved_config()     # convenience copy for readers and tests only: validators never read this name


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def sha256_of(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def approved_config_sha256():
    return sha256_of(approved_config())


def cell_calibration():
    return {k: approved_config()["calibration"][k] for k in ("known_acceptance_target", "clean_alarm_pfa", "mahalanobis_shrinkage")}


def carried_none():
    return {"optimizer": None, "scheduler": None, "rng": None, "weights": None, "data_cursor": None}


# ---- findings --------------------------------------------------------------------------------------------------

def _safe(value):
    """Keep reports strict JSON whatever was submitted: scalars stay, anything else becomes a short repr."""
    if value is None or isinstance(value, (bool, int, str)):
        return value if not isinstance(value, str) else value[:200]
    if isinstance(value, float):
        return value if math.isfinite(value) else repr(value)
    return repr(value)[:200]


def _fail(out, field, code, expected=None, actual=None):
    out.append({"field": field, "code": code, "expected": _safe(expected) if not isinstance(expected, (list, dict, tuple)) else expected,
                "actual": _safe(actual)})


def _report(kind, failures, **extra):
    """Strict-JSON report. ``authorizes_nothing`` is fixed: a valid record is never a permission."""
    return {"contract": CONTRACT, "kind": kind, "ok": not failures, "failures": failures, "authorizes_nothing": True,
            "executor_implemented": False, **extra}


def require_ok(report):
    if not report["ok"]:
        raise ContractError(f"{report['kind']}: " + "; ".join(f"{f['field']} {f['code']}" for f in report["failures"][:8]))
    return report


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _compare(path, actual, expected, out, subset=False):
    """Exact structural comparison: missing, unexpected, conflicting and wrongly typed fields are separate findings.
    ``subset`` checks only the keys of ``expected`` (used for decision records that carry extra prose)."""
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return _fail(out, path, "TYPE", "object", type(actual).__name__)
        for key, want in expected.items():
            if key not in actual:
                _fail(out, f"{path}.{key}", "MISSING", want)
            else:
                _compare(f"{path}.{key}", actual[key], want, out, subset)
        if not subset:
            for key in actual:
                if key not in expected:
                    _fail(out, f"{path}.{key}", "UNEXPECTED", None, actual[key])
    elif isinstance(expected, list):
        if not isinstance(actual, list) or len(actual) != len(expected):
            return _fail(out, path, "CONFLICT", expected, actual)
        for index, (have, want) in enumerate(zip(actual, expected)):
            _compare(f"{path}[{index}]", have, want, out, subset)
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
        elif isinstance(expected, int) and not isinstance(actual, int):
            _fail(out, path, "TYPE", "integer", type(actual).__name__)
        elif actual != expected:
            _fail(out, path, "CONFLICT", expected, actual)
    else:                                                                # pragma: no cover - the reference holds no other types
        _fail(out, path, "INVALID", repr(expected), repr(actual))


def _normalized(actual, expected):
    """Coerce exactly-equal integers to the reference's float type so that equal configurations hash alike (1 and 1.0)."""
    if isinstance(expected, dict) and isinstance(actual, dict):
        return {k: _normalized(v, expected[k]) if k in expected else v for k, v in actual.items()}
    if isinstance(expected, list) and isinstance(actual, list) and len(expected) == len(actual):
        return [_normalized(a, e) for a, e in zip(actual, expected)]
    if isinstance(expected, float) and isinstance(actual, int) and not isinstance(actual, bool):
        return float(actual)
    return actual


def _jsonable(value):
    try:
        canonical(value)
        return True
    except (TypeError, ValueError):
        return False


def _hex64(out, path, value):
    if not (isinstance(value, str) and HEX64.fullmatch(value)):
        _fail(out, path, "INVALID", "64 lowercase hex characters", value)


# ---- 1. scientific configuration -------------------------------------------------------------------------------

def validate_scientific_config(config):
    """The explicit production configuration must equal the approved one in every critical field. Pure; runs nothing."""
    failures = []
    if not isinstance(config, dict):
        _fail(failures, "$", "TYPE", "object", type(config).__name__)
    else:
        _compare("$", config, approved_config(), failures)
        training = config.get("training")
        if isinstance(training, dict) and all(_number(training.get(k)) and math.isfinite(training[k]) for k in ("batch_size", "epochs", "train_observations")) \
                and training["batch_size"] > 0:
            steps = int(training["epochs"] * -(-training["train_observations"] // training["batch_size"]))
            if training.get("optimizer_steps_per_fit") != steps:
                _fail(failures, "$.training.optimizer_steps_per_fit", "CONFLICT", steps, training.get("optimizer_steps_per_fit"))
        optimizer, scheduler = config.get("optimizer"), config.get("scheduler")
        if isinstance(optimizer, dict) and isinstance(scheduler, dict) and optimizer.get("peak_lr") != scheduler.get("max_lr"):
            _fail(failures, "$.scheduler.max_lr", "CONFLICT", optimizer.get("peak_lr"), scheduler.get("max_lr"))
    return _report("scientific_config", failures, config_sha256=sha256_of(_normalized(config, approved_config())) if _jsonable(config) else None)


def _by_stem(record, stem):
    """The approved record names its numeric flags after the library attributes; they are matched by stem here so that this
    module never spells those attribute names (the repository scan for 'no source pins numerics yet' stays meaningful)."""
    hits = [value for key, value in record.items() if key.startswith(stem)]
    if len(hits) != 1:
        raise ContractError(f"the approved numerics record must hold exactly one field starting with {stem!r}")
    return hits[0]


# Prose fields of the approved JSON record, pinned verbatim: a reworded record is a protocol change and must fail loudly.
PINNED_PROSE = MappingProxyType({
    ("epochs_selection_procedure",): "Fixed 30 epochs for every view/seed, no sizing run, no early stopping; first best val-select macro-F1 checkpoint",
    ("checkpoint_selection_rule",): "best val-select macro-F1 over the 8 known classes (clean + 7), evaluated after every epoch; strict '>' so the first "
                                   "epoch reaching the maximum is kept; the auxiliary plan head is monitored, not selected on",
    ("test_evaluation_coupling",): "P31 isolated train-only → known-only calibration → freeze all nine independent view/seed "
                                  "checkpoint+scorer+calibrator bundles before any held-out read → one-time read-only evaluation",
    ("interruption_policy",): "Incomplete interrupted (view,seed) fit; new attempt_id and restart epoch 0 from same seed/data/source/environment; "
                              "no partial model/optimizer/scheduler/RNG carry-over",
    ("loss_composition",): "cross-entropy (unweighted, mean) + center_loss_weight x centre loss + plan_loss_weight x plan BCE (auxiliary head, "
                           "independent of the label)",
    ("mahalanobis_fit", "statistics"): "train-role embeddings of the selected checkpoint (eval mode), class-conditional",
    ("optimizer", "decay_applies_to"): "all parameters: convolutions, BatchNorm affine, linear heads, auxiliary head and the CenterLoss centres",
    ("plan_shift_augmentation", "distribution"): "continuous U(-max, +max) per selected sample",
    ("plan_shift_augmentation", "selection"): "Bernoulli per sample per batch (expected fraction, not exact)",
    ("plan_shift_augmentation", "scope"): "training only; val-select, val-calib and test masks are never shifted",
    ("mirror_roll_augmentation", "mirror"): "frequency-axis flip with probability 0.5 per sample",
    ("mirror_roll_augmentation", "roll"): "circular time shift, ONE random shift per mini-batch (not per sample)",
    ("learning_rate_schedule", "step"): "once per optimizer step",
    ("calibration", "quantile"): "higher empirical quantile, inclusive acceptance",
    ("calibration", "data"): "val-calib, known classes only",
    ("precision_and_determinism", "worker_policy"): "synchronous streaming",
})
PHASES_RECORD = ["train-only", "known-only calibrate", "freeze nine cells", "one-time read-only evaluate"]


def _record_value(records, path):
    node = records[path[0]]["value"] if path[0] in records else None
    for part in path[1:]:
        node = node[part]
    return node


def config_from_protocol(protocol):
    """Build the explicit configuration from the approved scientific record. Numbers and flags are read from it; the prose
    fields are checked against PINNED_PROSE by validate_protocol_record, and the few (pinned) items that exist only in the
    markdown record are taken from the reference."""
    try:
        records, decisions = protocol["parameter_records"], protocol["decisions"]
        value = lambda key: records[key]["value"]                                    # noqa: E731
        optimizer, schedule, numerics = value("optimizer"), value("learning_rate_schedule"), value("precision_and_determinism")
        shift = value("plan_shift_augmentation")
        calibration, restart, isolation = decisions["R10"], decisions["R9"], decisions["R8"]
        ref = approved_config()
        return {
            "schema": CONFIG_SCHEMA, "profile": protocol["profile_id"], "receiver": decisions["OBS-CANCEL-2"]["receiver"],
            "views": value("views"), "seeds": value("training_seed_values"),
            "model": {"width": value("model_width"), "time_pool": value("time_pool"), "level": value("level")},
            "training": {"epochs": value("epochs"), "batch_size": value("batch_size"), "early_stopping": decisions["R4"]["early_stopping"],
                         "train_observations": ref["training"]["train_observations"],
                         "optimizer_steps_per_fit": value("epochs") * -(-ref["training"]["train_observations"] // value("batch_size")),
                         "checkpoint_rule": "first_best_val_select_macro_f1" if decisions["R4"]["checkpoint"] == "first best val-select macro-F1" else None,
                         "checkpoint_tie_rule": "strict_greater_keeps_first_maximum" if records["checkpoint_selection_rule"]["value"]
                         == PINNED_PROSE[("checkpoint_selection_rule",)] else None,
                         "auto_batch_reduction": decisions["R5"]["auto_fallback"]},
            "loss": {"center_loss_weight": value("center_loss_weight"), "plan_loss_weight": float(value("plan_loss_weight")),
                     "plan_consistency": decisions["R3"]["plan_consistency"], "center_term": ref["loss"]["center_term"],
                     "train_diagnostics": "observation_only" if decisions["R3"]["diagnostics"] == "train-only, observation-only" else None},
            "augmentation": {"plan_shift_fraction": shift["fraction"], "plan_shift_max_hz": float(shift["max_hz"]),
                             "plan_shift_distribution": "continuous_uniform_symmetric" if shift["distribution"] == PINNED_PROSE[("plan_shift_augmentation", "distribution")] else None,
                             "plan_shift_selection": "bernoulli_per_sample_per_batch" if shift["selection"] == PINNED_PROSE[("plan_shift_augmentation", "selection")] else None,
                             "plan_shift_scope": "training_only" if shift["scope"] == PINNED_PROSE[("plan_shift_augmentation", "scope")] else None,
                             "mirror_probability": 0.5 if value("mirror_roll_augmentation")["enabled"] is True
                             and value("mirror_roll_augmentation")["mirror"] == PINNED_PROSE[("mirror_roll_augmentation", "mirror")] else None,
                             "roll": "one_circular_time_shift_per_batch" if value("mirror_roll_augmentation")["roll"] == PINNED_PROSE[("mirror_roll_augmentation", "roll")] else None},
            "optimizer": {"name": optimizer["name"], "peak_lr": optimizer["peak_lr"], "weight_decay": optimizer["weight_decay"],
                          "betas": optimizer["betas"], "eps": optimizer["eps"], "param_groups": optimizer["param_groups"],
                          "gradient_clipping": value("gradient_clipping"),
                          "weight_decay_scope": "all_parameters" if optimizer["decay_applies_to"] == PINNED_PROSE[("optimizer", "decay_applies_to")] else None},
            "scheduler": {"name": schedule["name"], "max_lr": schedule["max_lr"], "pct_start": schedule["pct_start"],
                          "anneal_strategy": schedule["anneal_strategy"], "div_factor": schedule["div_factor"],
                          "final_div_factor": schedule["final_div_factor"], "three_phase": schedule["three_phase"],
                          "cycle_momentum": schedule["cycle_momentum"], "base_momentum": schedule["base_momentum"],
                          "max_momentum": schedule["max_momentum"], "initial_lr": schedule["initial_lr"], "final_lr": schedule["final_lr"],
                          "step": "per_optimizer_step" if schedule["step"] == PINNED_PROSE[("learning_rate_schedule", "step")] else None},
            "numerics": {"precision": numerics["precision"], "mixed_precision_enabled": _by_stem(numerics, "auto"),
                         "cudnn_tf32_enabled": _by_stem(numerics, "cudnn_"), "matmul_tf32_enabled": _by_stem(numerics, "matmul_"),
                         "deterministic_algorithms": numerics["deterministic_algorithms"],
                         "cuda_cudnn_gpu_driver_pinned": decisions["R6"]["environment_pin_required"]},
            "streaming": {"groups_per_shard": value("streaming_groups_per_shard"), "window_shards": value("streaming_window_shards"),
                          "sample_order": "seeded_blocked_shuffle" if decisions["R7"]["sample_order"] == "seeded blocked shuffle" else None,
                          "worker_policy": "synchronous" if numerics["worker_policy"] == PINNED_PROSE[("precision_and_determinism", "worker_policy")] else None,
                          "remainder_policy": ref["streaming"]["remainder_policy"],
                          "log_shard_orders_and_hashes": ref["streaming"]["log_shard_orders_and_hashes"],
                          "global_shuffle_equivalence_claimed": ref["streaming"]["global_shuffle_equivalence_claimed"]},
            "isolation": {"phases": ref["isolation"]["phases"] if isolation["phases"] == PHASES_RECORD else isolation["phases"],
                          "heldout_read_before_freeze": ref["isolation"]["heldout_read_before_freeze"],
                          "test_driven_retuning": isolation["test_driven_retuning"]},
            "restart": {"policy": "restart_epoch_zero" if restart["restart_epoch"] == 0 else None, "restart_epoch": restart["restart_epoch"],
                        "new_attempt_id": restart["new_attempt_id"], "carry_partial_state": restart["carry_partial_state"],
                        "incomplete_status": restart["incomplete_status"]},
            "calibration": {"known_acceptance_target": calibration["known_acceptance_target"], "clean_alarm_pfa": calibration["clean_alarm_pfa"],
                            "mahalanobis_shrinkage": calibration["mahalanobis_regularization"],
                            "quantile": "higher_empirical_known_only_val_calib" if value("calibration")["quantile"] == PINNED_PROSE[("calibration", "quantile")] else None,
                            "calibration_data": "known_val_calib_only" if calibration["calibration_source"] == "known val-calib only"
                            and value("calibration")["data"] == PINNED_PROSE[("calibration", "data")] else None,
                            "mahalanobis_statistics": "train_role_eval_mode_class_conditional_embeddings"
                            if value("mahalanobis_fit")["statistics"] == PINNED_PROSE[("mahalanobis_fit", "statistics")] else None,
                            "acceptance_rule": ref["calibration"]["acceptance_rule"], "alarm_rule": ref["calibration"]["alarm_rule"]}}
    except (KeyError, TypeError, AttributeError, IndexError) as error:
        raise ContractError(f"the approved scientific record is incomplete or malformed: {type(error).__name__}: {error}") from error


PROTOCOL_DECISIONS = ("OBS-CANCEL-2", "K17d", "K18") + tuple(f"R{n}" for n in range(1, 11))


def _decision_reference():
    """Scalar content each decision record must carry; the same facts must also hold in the parameter records and the reference."""
    ref = approved_config()
    return {
        "OBS-CANCEL-2": {"choice": "A", "receiver": ref["receiver"]},
        "K17d": {"choice": "A+C", "benchmark": "B2-test/1", "headline_groups": 500, "co_feed_missing_groups": 35, "remaining_sensitivity_groups": 465},
        "K18": {"choice": "A", "loss": "CE + 0.005*center_sum + 1.0*plan_BCE"},
        "R1": {"choice": "A", "views": ref["views"], "seeds": ref["seeds"], "n_fits": 9, "headline": "dual_residual"},
        "R2": {"choice": "A", **ref["model"]},
        "R3": {"choice": "A", "center_loss_weight": ref["loss"]["center_loss_weight"], "plan_loss_weight": ref["loss"]["plan_loss_weight"],
               "plan_consistency": True, "plan_shift_fraction": ref["augmentation"]["plan_shift_fraction"],
               "plan_shift_max_hz": ref["augmentation"]["plan_shift_max_hz"], "diagnostics": "train-only, observation-only"},
        "R4": {"choice": "A", "epochs": ref["training"]["epochs"], "early_stopping": False, "checkpoint": "first best val-select macro-F1"},
        "R5": {"choice": "A", "batch_size": ref["training"]["batch_size"], "auto_fallback": False},
        "R6": {"choice": "A", "optimizer": "AdamW", "peak_lr": ref["optimizer"]["peak_lr"], "weight_decay": ref["optimizer"]["weight_decay"],
               "scheduler": "OneCycleLR", "gradient_clipping": False, "precision": "fp32", "deterministic_algorithms": False,
               "environment_pin_required": True, "p18_change_required": True},
        "R7": {"choice": "A", "groups_per_shard": 4, "window_shards": 4, "sample_order": "seeded blocked shuffle"},
        "R8": {"choice": "A", "phases": PHASES_RECORD, "test_driven_retuning": False},
        "R9": {"choice": "A", "restart_epoch": 0, "new_attempt_id": True, "carry_partial_state": False, "incomplete_status": "INCOMPLETE"},
        "R10": {"choice": "A", "known_acceptance_target": 0.95, "clean_alarm_pfa": 0.05, "mahalanobis_regularization": 0.1,
                "calibration_source": "known val-calib only"}}


def validate_protocol_record(protocol):
    """The researcher's scientific record must say approved, not executable, not production-authorized, and must agree with
    itself (decisions, parameter records, pinned prose) and with the reference configuration."""
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
    if not (isinstance(protocol.get("source_main_sha"), str) and HEX40.fullmatch(protocol["source_main_sha"])):
        _fail(failures, "source_main_sha", "INVALID", "40 hex characters", protocol.get("source_main_sha"))
    decisions = protocol.get("decisions")
    if not isinstance(decisions, dict):
        _fail(failures, "decisions", "MISSING", "object", type(decisions).__name__)
    else:
        for name, expected in _decision_reference().items():
            _compare(f"decisions.{name}", decisions.get(name), expected, failures, subset=True)
        if isinstance(decisions.get("R6"), dict):
            _compare("decisions.R6", {"flags": [_flag(decisions["R6"], s) for s in ("auto", "cudnn_", "matmul_")]}, {"flags": [False, False, False]},
                     failures, subset=True)
        if isinstance(decisions.get("K17d"), dict) and not (isinstance(decisions["K17d"].get("rule"), str) and "pol==0" in decisions["K17d"]["rule"]):
            _fail(failures, "decisions.K17d.rule", "CONFLICT", "a rule naming pol==0", decisions["K17d"].get("rule"))
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
    records = protocol.get("parameter_records")
    if not isinstance(records, dict):
        _fail(failures, "parameter_records", "MISSING", "object", type(records).__name__)
    elif not failures:
        for path, text in PINNED_PROSE.items():
            try:
                actual = _record_value(records, path)
            except (KeyError, TypeError, IndexError):
                _fail(failures, "parameter_records." + ".".join(path), "MISSING", text)
                continue
            if actual != text:
                _fail(failures, "parameter_records." + ".".join(path), "CONFLICT", text, actual)
        try:
            derived = validate_scientific_config(config_from_protocol(protocol))
            failures += derived["failures"]
        except ContractError as error:
            _fail(failures, "parameter_records", "INVALID", None, str(error))
    return _report("protocol_record", failures)


def _flag(record, stem):
    try:
        return _by_stem(record, stem)
    except ContractError:
        return None


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


DAYS = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
TIMESTAMP = re.compile(r"(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(\.\d+)?(Z|[+-]\d{2}:\d{2})")


def _iso(value):
    """A real calendar date and clock time (no datetime import: the contract reads no clock)."""
    found = TIMESTAMP.fullmatch(value) if isinstance(value, str) else None
    if not found:
        return False
    year, month, day, hour, minute, second = (int(found.group(i)) for i in range(1, 7))
    leap = year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
    if not 1 <= month <= 12 or year < 1:
        return False
    limit = DAYS[month - 1] + (1 if month == 2 and leap else 0)
    return 1 <= day <= limit and hour < 24 and minute < 60 and second < 60


def approval_problems(approval, needs_ceilings=False):
    """Structural only, like the preflight gate check: it cannot judge whether a person really approved."""
    if not isinstance(approval, dict):
        return ["no approval record"]
    problems = [f"{name} must be a non-empty string" for name in ("approved_by", "decision", "record")
                if not (isinstance(approval.get(name), str) and approval[name].strip())]
    if not _iso(approval.get("approved_at")):
        problems.append("approved_at must be an ISO-8601 timestamp with a valid calendar date")
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
    if not isinstance(status, str):
        return {"status": NOT_AUTHORIZED, "runnable": False, "malformed": True, "reasons": [f"gate {key} has no valid status"]}
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


def memo_twin_problems(gates, memo):
    """The preflight and the supervisor also require the E5 memorandum twin to agree with the gates; optional here."""
    problems = []
    for key in SCIENTIFIC_GATES + tuple(g for g in ACTION_GATES.values() if g):
        record, twin = _gate(gates, key), _gate(memo, key)
        if record is None or twin is None or record.get("status") != twin.get("status"):
            problems.append(f"gate {key} disagrees with its memorandum twin")
    return problems


def evaluate_state(*, protocol, gates, config, evidence=None, memo=None, production_launch_enabled=False):
    """NOT_AUTHORIZED -> ENGINEERING_READY -> AWAITING_SEPARATE_APPROVAL. The result never contains a runnable state."""
    reasons = []
    for label, report in (("protocol", validate_protocol_record(protocol)), ("config", validate_scientific_config(config))):
        reasons += [f"{label}: {f['field']} {f['code']}" for f in report["failures"][:6]]
    reasons += scientific_gate_problems(gates, protocol if isinstance(protocol, dict) else {})
    if memo is not None:
        reasons += memo_twin_problems(gates, memo)
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
            "runtime_permitted": runtime_permitted(), "executor_implemented": False, "benchmark_complete": False,
            "caveat": "States describe the consistency of records only: no executor exists, nothing is runnable, and the evidence "
                      "(review, CI, heads) is self-asserted metadata that this module cannot verify."}


def evidence_problems(evidence):
    """Engineering evidence for the exact source head: independent review without open material findings and exact-head CI."""
    if not isinstance(evidence, dict):
        return ["engineering evidence is missing: no independent review or exact-head CI record"]
    head = evidence.get("source_head")
    problems = [] if isinstance(head, str) and HEX40.fullmatch(head) else ["source_head must be 40 hex characters"]
    review, ci = evidence.get("independent_review"), evidence.get("exact_head_ci")
    if not (isinstance(review, dict) and review.get("reviewed_head") == head and type(review.get("open_material_findings")) is int
            and review["open_material_findings"] == 0 and isinstance(review.get("record"), str) and review["record"].strip()):
        problems.append("independent review must name the exact source head, a record, and zero open material findings")
    if not (isinstance(ci, dict) and ci.get("head") == head and ci.get("conclusion") == "success" and type(ci.get("run_id")) is int
            and ci["run_id"] > 0):
        problems.append("exact-head CI must name the same head with conclusion success and a positive integer run id")
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
ARTIFACT_HASHES = ("model_sha256", "scorer_sha256", "calibrator_sha256")
CELL_HASHES = ARTIFACT_HASHES + ("training_config_sha256", "data_identity", "source_tree_sha256", "environment_id")


def validate_nine_cell_freeze(cells, *, epochs=30, attempts=None):
    """Three views x three seeds with compatible provenance and no held-out read, from metadata only (no artifact is opened).
    With ``attempts`` each cell must also be the COMPLETE attempt of a valid restart chain for its view/seed."""
    failures, seen = [], {}
    if not isinstance(cells, list):
        _fail(failures, "cells", "TYPE", "list", type(cells).__name__)
        return _report("nine_cell_freeze", failures, freeze_contract_satisfied=False)
    if len(cells) != 9:
        _fail(failures, "cells", "CONFLICT", 9, len(cells))
    config_hash = approved_config_sha256()
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
        view, seed = cell.get("view"), cell.get("seed")
        if not isinstance(view, str) or view not in VIEWS or type(seed) is not int or seed not in SEEDS:
            _fail(failures, path, "INVALID", "view in co/dual/dual_residual and seed in 0/1/2", f"{view!r}/{seed!r}")
        elif (view, seed) in seen:
            _fail(failures, path, "CONFLICT", "each view/seed once", f"duplicate {(view, seed)}")
        else:
            seen[(view, seed)] = cell
        if "status" in cell and cell["status"] != "COMPLETE":
            _fail(failures, f"{path}.status", "CONFLICT", "COMPLETE", cell["status"])
        if "epochs_completed" in cell and (type(cell["epochs_completed"]) is not int or cell["epochs_completed"] != epochs):
            _fail(failures, f"{path}.epochs_completed", "CONFLICT", epochs, cell["epochs_completed"])
        selected = cell.get("selected_epoch")
        if "selected_epoch" in cell and (type(selected) is not int or not 0 <= selected < epochs):
            _fail(failures, f"{path}.selected_epoch", "INVALID", f"integer in [0, {epochs - 1}]", selected)
        if "heldout_reads" in cell and (type(cell["heldout_reads"]) is not int or cell["heldout_reads"] != 0):
            _fail(failures, f"{path}.heldout_reads", "CONFLICT", 0, cell["heldout_reads"])
        if "attempt_id" in cell and not (isinstance(cell["attempt_id"], str) and ATTEMPT_ID.fullmatch(cell["attempt_id"])):
            _fail(failures, f"{path}.attempt_id", "INVALID", "attempt id", cell["attempt_id"])
        if "profile" in cell and cell["profile"] != PROFILE:
            _fail(failures, f"{path}.profile", "CONFLICT", PROFILE, cell["profile"])
        if "calibration" in cell:
            _compare(f"{path}.calibration", cell["calibration"], cell_calibration(), failures)
        for name in CELL_HASHES:
            if name in cell:
                _hex64(failures, f"{path}.{name}", cell[name])
        if cell.get("training_config_sha256") not in (None, config_hash) and isinstance(cell.get("training_config_sha256"), str):
            _fail(failures, f"{path}.training_config_sha256", "CONFLICT", "hash of the approved explicit configuration", cell["training_config_sha256"])
    required = {(view, seed) for view in VIEWS for seed in SEEDS}
    if len(cells) == 9 and set(seen) != required:
        _fail(failures, "cells", "CONFLICT", "all nine view/seed cells", sorted(map(str, required - set(seen))))
    dicts = [c for c in cells if isinstance(c, dict)]
    for name in CELL_COMMON:
        values = {canonical(c[name]) for c in dicts if name in c and _jsonable(c[name])}
        if len(values) > 1:
            _fail(failures, name, "CONFLICT", "identical across all nine cells", sorted(values)[:3])
    ids = [c["attempt_id"] for c in dicts if isinstance(c.get("attempt_id"), str)]
    if len(set(ids)) != len(ids):
        _fail(failures, "attempt_id", "CONFLICT", "nine distinct attempt ids", len(ids) - len(set(ids)))
    shared = {n: [c[n] for c in dicts if isinstance(c.get(n), str)] for n in CELL_COMMON if n != "profile" and n != "calibration"}
    per_cell = [c[n] for c in dicts for n in ARTIFACT_HASHES if isinstance(c.get(n), str)]
    common_values = {v for name, vals in shared.items() for v in vals}
    if len(set(per_cell)) != len(per_cell):
        _fail(failures, "artifacts", "CONFLICT", "model, scorer and calibrator hashes all distinct "
              "(a renamed or reused artifact is not a new fit)", len(per_cell) - len(set(per_cell)))
    if set(per_cell) & common_values:
        _fail(failures, "artifacts", "CONFLICT", "artifact hashes differ from the shared config/data/source/environment hashes", None)
    if attempts is not None:
        chain = validate_attempt_chain(attempts, epochs=epochs)
        failures += [{**f, "field": f"attempts.{f['field']}"} for f in chain["failures"]]
        index = {r.get("attempt_id"): r for r in attempts if isinstance(r, dict) and isinstance(r.get("attempt_id"), str)}
        for cell in dicts:
            record = index.get(cell.get("attempt_id"))
            if record is None or record.get("status") != "COMPLETE" or (record.get("view"), record.get("seed")) != (cell.get("view"), cell.get("seed")):
                _fail(failures, f"cell {cell.get('view')}/{cell.get('seed')}.attempt_id", "CONFLICT", "a COMPLETE attempt of the same view/seed",
                      cell.get("attempt_id"))
            elif any(record.get(a) != cell.get(b) for a, b in (("source_tree_sha256",) * 2, ("data_identity",) * 2, ("environment_id",) * 2)):
                _fail(failures, f"cell {cell.get('view')}/{cell.get('seed')}", "CONFLICT", "attempt source/data/environment equal the cell's", None)
    return _report("nine_cell_freeze", failures, freeze_contract_satisfied=not failures, cells_checked=len(dicts))


# ---- 4. restart provenance -------------------------------------------------------------------------------------

ATTEMPT_FIELDS = ("attempt_id", "view", "seed", "status", "start_epoch", "epochs_completed", "parent_attempt_id", "parent_hash",
                  "source_tree_sha256", "data_identity", "environment_id", "carried_state", "record_hash")


def record_hash(record):
    return sha256_of({k: v for k, v in record.items() if k != "record_hash"})


def make_attempt_record(*, attempt_id, view, seed, status, epochs_completed, source_tree_sha256, data_identity, environment_id,
                        parent=None):
    """Pure builder: always epoch 0, nothing carried, parent hash bound. It validates what it builds and raises otherwise."""
    record = {"attempt_id": attempt_id, "view": view, "seed": seed, "status": status, "start_epoch": 0,
              "epochs_completed": epochs_completed, "parent_attempt_id": parent["attempt_id"] if parent else None,
              "parent_hash": record_hash(parent) if parent else None, "source_tree_sha256": source_tree_sha256,
              "data_identity": data_identity, "environment_id": environment_id, "carried_state": carried_none()}
    record["record_hash"] = record_hash(record)
    require_ok(validate_attempt_chain([parent, record] if parent else [record]))
    return record


def validate_attempt_chain(records, *, epochs=30):
    """R9: a failed fit is INCOMPLETE; the next attempt restarts at epoch 0 with nothing carried, same source/data/environment.
    Every view/seed has exactly one root; a retry without a parent link is a second root and is refused."""
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
        if not (isinstance(attempt_id, str) and ATTEMPT_ID.fullmatch(attempt_id)):
            _fail(failures, f"{path}.attempt_id", "INVALID", "attempt id", attempt_id)
        elif attempt_id in by_id:
            _fail(failures, f"{path}.attempt_id", "CONFLICT", "unique attempt id", attempt_id)
        else:
            by_id[attempt_id] = record
        if not isinstance(record.get("view"), str) or record["view"] not in VIEWS or type(record.get("seed")) is not int or record["seed"] not in SEEDS:
            _fail(failures, f"{path}.view", "INVALID", "view in co/dual/dual_residual and seed in 0/1/2", f"{record.get('view')!r}/{record.get('seed')!r}")
        if record.get("status") not in ATTEMPT_STATUSES:
            _fail(failures, f"{path}.status", "INVALID", ATTEMPT_STATUSES, record.get("status"))
        if type(record.get("start_epoch")) is not int or record.get("start_epoch") != 0:
            _fail(failures, f"{path}.start_epoch", "CONFLICT", 0, record.get("start_epoch"))
        done = record.get("epochs_completed")
        if type(done) is not int or not 0 <= done <= epochs or (record.get("status") == "COMPLETE" and done != epochs):
            _fail(failures, f"{path}.epochs_completed", "CONFLICT", f"{epochs} when COMPLETE, otherwise 0..{epochs}", done)
        if "carried_state" in record:
            _compare(f"{path}.carried_state", record["carried_state"], carried_none(), failures)
        for name in ("source_tree_sha256", "data_identity", "environment_id"):
            if name in record:
                _hex64(failures, f"{path}.{name}", record[name])
        if "parent_hash" in record and record["parent_hash"] is not None:
            _hex64(failures, f"{path}.parent_hash", record["parent_hash"])
        if "record_hash" in record and record["record_hash"] != record_hash(record):
            _fail(failures, f"{path}.record_hash", "CONFLICT", "hash of the record", record["record_hash"])
    children, roots = {}, {}
    for record in (r for r in records if isinstance(r, dict)):
        path, parent_id = f"attempt {record.get('attempt_id')}", record.get("parent_attempt_id")
        cell = f"{record.get('view')}/{record.get('seed')}"
        if parent_id is None:
            if record.get("parent_hash") is not None:
                _fail(failures, f"{path}.parent_hash", "CONFLICT", None, record["parent_hash"])
            roots.setdefault(cell, []).append(record.get("attempt_id"))
            continue
        if not isinstance(parent_id, str):
            _fail(failures, f"{path}.parent_attempt_id", "INVALID", "an attempt id", parent_id)
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
    for cell, ids in roots.items():
        if len(ids) != 1:
            _fail(failures, f"cell {cell}", "CONFLICT", "exactly one root attempt per view/seed (a retry must link its parent)", ids)
    for parent_id, kids in children.items():
        if len(kids) > 1:
            _fail(failures, f"attempt {parent_id}", "CONFLICT", "at most one restart per incomplete attempt", kids)
    complete = {}
    for record in (r for r in records if isinstance(r, dict) and r.get("status") == "COMPLETE"):
        key = f"{record.get('view')}/{record.get('seed')}"
        if key in complete:
            _fail(failures, f"cell {key}", "CONFLICT", "at most one COMPLETE attempt per view/seed", [complete[key], record.get("attempt_id")])
        complete[key] = record.get("attempt_id")
    for record in (r for r in records if isinstance(r, dict)):                       # defensive: no cycles
        node, steps = record, 0
        while node and isinstance(node.get("parent_attempt_id"), str) and steps <= len(records):
            node, steps = by_id.get(node["parent_attempt_id"]), steps + 1
        if steps > len(records):
            _fail(failures, f"attempt {record.get('attempt_id')}", "CONFLICT", "acyclic lineage", "cycle")
            break
    return _report("attempt_chain", failures, completed_cells=sorted(complete))


# ---- 5. resources, environment and lock requirements -----------------------------------------------------------

ENVIRONMENT_SCHEMA = "B2-E9-environment-record/1"
LOCK_REQUIREMENTS_SCHEMA = "B2-E9-lock-requirements/1"
ENVIRONMENT_KEYS = ("schema", "profile", "python", "numpy", "scipy", "torch", "cuda", "cudnn", "gpu", "numerics", "source", "thread_environment")
LOCK_KEYS = ("schema", "created", "authorized", "config_sha256", "environment", "ceilings", "backup", "working_device_id")


def _pin(out, path, value):
    if not (isinstance(value, str) and VERSION.fullmatch(value)):
        _fail(out, path, "MISSING", "an exact pinned version such as 2.14.1+cu130", value)


def _only(out, path, record, allowed):
    for key in record:
        if key not in allowed:
            _fail(out, f"{path}.{key}", "UNEXPECTED", None, record[key])


def validate_environment_record(env):
    """Pinned GPU/CUDA/cuDNN/torch/driver identities and the effective numerics flags. Schema only; reads no machine."""
    failures = []
    if not isinstance(env, dict):
        _fail(failures, "$", "TYPE", "object", type(env).__name__)
        return _report("environment_record", failures)
    _only(failures, "$", env, ENVIRONMENT_KEYS)
    shape = {"schema": ENVIRONMENT_SCHEMA, "profile": PROFILE}
    _compare("$", {k: env.get(k) for k in shape}, shape, failures)
    for name in ("python", "numpy", "scipy", "torch", "cuda", "cudnn"):
        _pin(failures, f"$.{name}", env.get(name))
    gpu = env.get("gpu")
    if not isinstance(gpu, dict):
        _fail(failures, "$.gpu", "MISSING", "object", gpu)
    else:
        _only(failures, "$.gpu", gpu, ("model", "count", "vram_gib", "driver"))
        if not (isinstance(gpu.get("model"), str) and gpu["model"].strip()):
            _fail(failures, "$.gpu.model", "MISSING", "a GPU model name", gpu.get("model"))
        _pin(failures, "$.gpu.driver", gpu.get("driver"))
        # One device is a conservative engineering constraint (batch-32 single-device semantics); the approved record is silent.
        if type(gpu.get("count")) is not int or gpu.get("count") != 1:
            _fail(failures, "$.gpu.count", "CONFLICT", 1, gpu.get("count"))
        vram = gpu.get("vram_gib")
        if not _number(vram) or not math.isfinite(vram) or vram <= 0:
            _fail(failures, "$.gpu.vram_gib", "INVALID", "finite positive number", vram)
    numerics = env.get("numerics")
    if not isinstance(numerics, dict):
        _fail(failures, "$.numerics", "MISSING", "the effective flags", numerics)
    else:
        expected = {k: v for k, v in approved_config()["numerics"].items() if k != "cuda_cudnn_gpu_driver_pinned"}
        _compare("$.numerics", numerics, expected, failures)
    source = env.get("source")
    if not isinstance(source, dict):
        _fail(failures, "$.source", "MISSING", "object", source)
    else:
        _only(failures, "$.source", source, ("git_commit", "tree_clean", "source_tree_sha256", "files_sha256"))
        if not (isinstance(source.get("git_commit"), str) and HEX40.fullmatch(source["git_commit"])):
            _fail(failures, "$.source.git_commit", "INVALID", "40 hex characters", source.get("git_commit"))
        if source.get("tree_clean") is not True:
            _fail(failures, "$.source.tree_clean", "CONFLICT", True, source.get("tree_clean"))
        _hex64(failures, "$.source.source_tree_sha256", source.get("source_tree_sha256"))
        files = source.get("files_sha256")
        if not (isinstance(files, dict) and files and all(isinstance(k, str) and k.startswith("src/") and ".." not in k.split("/")
                                                          for k in files)
                and all(isinstance(v, str) and HEX64.fullmatch(v) for v in files.values())):
            _fail(failures, "$.source.files_sha256", "INVALID", "non-empty mapping of src/ paths to sha256", files if not isinstance(files, dict) else len(files))
    threads = env.get("thread_environment")
    if not (isinstance(threads, dict) and all(isinstance(threads.get(k), str) and threads[k].strip() for k in THREAD_VARIABLES)):
        _fail(failures, "$.thread_environment", "MISSING", f"string values for {THREAD_VARIABLES}", threads if not isinstance(threads, dict) else sorted(threads))
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
    _only(failures, "$", ceilings, CEILING_FIELDS)
    return _report("resource_ceilings", failures)


def validate_backup_location(backup, working_device, *, minimum_gb=BACKUP_MIN_GB):
    """A backup on the working device is no backup; the minimum is the E5 proposal and is passed in, not assumed approved."""
    failures = []
    if not isinstance(backup, dict):
        _fail(failures, "$", "TYPE", "object", type(backup).__name__)
        return _report("backup_location", failures)
    _only(failures, "$", backup, ("path", "device_id", "capacity_gb", "verified_manifest_sha256"))
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
    _only(failures, "$", document, LOCK_KEYS)
    if document.get("schema") != LOCK_REQUIREMENTS_SCHEMA:
        _fail(failures, "$.schema", "CONFLICT", LOCK_REQUIREMENTS_SCHEMA, document.get("schema"))
    if "lock_fingerprint" in document or document.get("created") is not False:
        _fail(failures, "$.created", "CONFLICT", "created=false and no lock_fingerprint: this contract creates no lock", document.get("created"))
    _hex64(failures, "$.config_sha256", document.get("config_sha256"))
    if document.get("config_sha256") != approved_config_sha256():
        _fail(failures, "$.config_sha256", "CONFLICT", "hash of the approved explicit configuration", document.get("config_sha256"))
    for name, check in (("environment", validate_environment_record), ("ceilings", validate_resource_ceilings)):
        sub = check(document.get(name))
        failures += [{**f, "field": f"$.{name}{f['field'][1:]}"} for f in sub["failures"]]
    working = document.get("working_device_id")
    if type(working) is not int:
        _fail(failures, "$.working_device_id", "INVALID", "integer device id", working)
    else:
        sub = validate_backup_location(document.get("backup"), working)
        failures += [{**f, "field": f"$.backup{f['field'][1:]}"} for f in sub["failures"]]
    if document.get("authorized") is not False:
        _fail(failures, "$.authorized", "CONFLICT", False, document.get("authorized"))
    return _report("lock_requirements", failures)

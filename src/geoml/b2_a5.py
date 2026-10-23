"""E4 dual-pol A5 operator-plan corruption: frozen-model paired evaluation (P28, ``B2-A5-eval/1``).

    python -m geoml.b2_a5 --config configs/b2_a5_smoke.json --data data/b2-feat-pilot \
        --runs runs/b2-feat-pilot --out runs/b2-a5-smoke

The received signal belongs to physics, the plan belongs to the monitor. For each selected scene the
``none`` replay is first verified against the stored shard (fail closed), then the operator belief is
corrupted and three conditions are scored with the *same* frozen checkpoints, scorers and thresholds:
``original`` (stored), ``MASK_ONLY`` (stored PSD and residual, rebuilt masks; the weaker control) and
``RECEIVER_CONSISTENT`` (replayed PSD, rebuilt masks, residual recomputed by the frozen ``obs-cancel/1``
from the co-pol IQ and the corrupted co-pol belief). Nothing is trained, fitted, calibrated or selected
here; the module only loads what ``geoml.b2_experiment`` produced. Counterfactual outputs are
descriptive agreement with the original labels, not accuracy (P28 §7). Execution is capped (P28 §9):
CPU only, <= 2 groups, <= 2 classes, one perturbation configuration, <= 16 replays, <= 24 cancellations.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import resource
import time
from dataclasses import asdict, dataclass
from pathlib import Path

try:                                    # advisory lock; absent on platforms without fcntl
    import fcntl
except ImportError:                     # pragma: no cover
    fcntl = None

import numpy as np
import scipy
import torch

from geosim.b2_protocol import LABELS, role_for_group
from geosim.b2_scenarios import MATCHED_LABELS
from geosim.dataset import _file_hash

from .artifacts import fingerprint
from . import cfar
from .b2_a5_plan import CONTRACT as PLAN_CONTRACT
from .b2_a5_plan import PERTURBATIONS, SCOPES, corrupt_operator_plan, rebuild_masks
from .b2_a5_replay import (Budget, BudgetExceeded, FrozenReceiver, ObservedInputs, ReplayError, ReplaySource,
                           SceneObservation, build_conditions, check_parity, open_replay_source, replay_scene,
                           reporting_flags)
from .b2_expert import FEATURE_NAMES, extract_features
from .b2_experiment import ROLES, VIEWS, B2ExperimentConfig, _pair_metrics, _rate, _softmax
from .b2_stream import B2Source, infer_streaming, open_b2_known, open_b2_matched
from .calibration import RejectionCalibration
from .data import CORE_DB
from .edsc import FREQUENCIES_HZ, residual_energy
from .experiment import _sha256, _source_identity
from .mahalanobis import MahalanobisScorer
from .metrics import confusion, macro_f1, threshold_at_pfa
from .openset import unknown_scores
from .train import load

CONTRACT = "B2-A5-eval/1"
CONDITIONS = ("original", "MASK_ONLY", "RECEIVER_CONSISTENT")
STAGES = ("known", "matched")
E4_ADDED_FILES = ("geoml/b2_a5.py", "geoml/b2_a5_plan.py", "geoml/b2_a5_replay.py")
CAPS = {"max_groups": 2, "max_classes": 2, "max_configurations": 1, "max_replays": 16, "max_cancellations": 24}
STATE_CONTRACT = "B2-A5-scene-state/2"  # checksummed envelope; earlier unsigned state is refused
DEFAULT_LABELS = {"known": ("clean", "unauthorized"), "matched": ("adjacent_satellite", "unauthorized")}
AUTHORIZATION = {"full_b2_production": "NOT_AUTHORIZED_NOT_STARTED", "full_gpu_training": "NOT_AUTHORIZED_NOT_STARTED",
                 "full_loko_sweep": "NOT_AUTHORIZED_NOT_STARTED", "K18": "PENDING_RESEARCHER",
                 "K17d": "PENDING_RESEARCHER", "OBS-CANCEL-2": "PENDING_RESEARCHER"}


@dataclass(frozen=True)
class A5Config:
    """One perturbation configuration (perturbation x scope) on a bounded paired population."""

    perturbation: str
    scope: str
    stage: str = "known"
    n_groups: int = 2
    labels: tuple = ()
    views: tuple = VIEWS

    def __post_init__(self):
        if self.perturbation not in PERTURBATIONS:
            raise ValueError(f"perturbation must be one of {PERTURBATIONS}")
        if self.scope not in SCOPES:
            raise ValueError(f"scope must be one of {SCOPES}")
        if self.stage not in STAGES:
            raise ValueError(f"stage must be one of {STAGES}")
        if isinstance(self.n_groups, bool) or not isinstance(self.n_groups, int) or not 1 <= self.n_groups <= CAPS["max_groups"]:
            raise ValueError(f"n_groups must be an integer in [1, {CAPS['max_groups']}] (bounded smoke cap)")
        labels = tuple(self.labels) if self.labels else DEFAULT_LABELS[self.stage]
        allowed = LABELS if self.stage == "known" else MATCHED_LABELS
        if (not 1 <= len(labels) <= CAPS["max_classes"] or len(set(labels)) != len(labels)
                or any(label not in allowed for label in labels)):
            raise ValueError(f"labels must be 1-{CAPS['max_classes']} distinct choices from {tuple(allowed)}")
        views = tuple(self.views)
        if not views or len(set(views)) != len(views) or any(view not in VIEWS for view in views):
            raise ValueError(f"views must be unique choices from {VIEWS}")
        object.__setattr__(self, "labels", labels)
        object.__setattr__(self, "views", views)
        self.plan_budget()      # fails before any expensive work when a cap would be exceeded

    def plan_budget(self) -> dict:
        """Pre-flight replay/cancellation count (upper bound: every selected scene is applicable)."""
        replays = self.n_groups * len(self.labels)
        recompute = self.perturbation != "none" and self.scope in ("co_only", "both")
        cancellations = replays * (2 if recompute else 1)
        if replays > CAPS["max_replays"] or cancellations > CAPS["max_cancellations"]:
            raise BudgetExceeded(f"{replays} replays / {cancellations} cancellations exceed the caps "
                                 f"{CAPS['max_replays']} / {CAPS['max_cancellations']}")
        return {"replays": replays, "cancellations": cancellations}

    @classmethod
    def from_file(cls, path):
        raw = json.loads(Path(path).read_text())
        if not isinstance(raw, dict) or set(raw) - {"perturbation", "scope", "stage", "n_groups", "labels", "views"}:
            raise ValueError("A5 configuration must be a JSON object with the A5Config fields only")
        return cls(**raw)

    def to_dict(self) -> dict:
        return {**asdict(self), "labels": list(self.labels), "views": list(self.views)}


def _json_safe(value):
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (np.floating, float)):
        return float(value)
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.ndarray):
        return _json_safe(value.tolist())
    return value


def _durable_text(path: Path, text: str) -> None:
    """Write-then-rename with the data flushed to disk before the rename, so a crash leaves old or complete content."""
    temporary = path.with_name(path.name + ".tmp")
    with open(temporary, "w") as stream:
        stream.write(text)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def _write_json(path: Path, value) -> None:
    _durable_text(path, json.dumps(_json_safe(value), indent=1, sort_keys=False, allow_nan=False) + "\n")


# ---------------------------------------------------------------- frozen models


@dataclass
class FrozenView:
    name: str
    fitted: dict
    scorer: MahalanobisScorer
    calibrations: dict
    alarm_threshold: float
    checkpoint_sha256: str
    identity: dict


def check_source_rule(trained: dict, current: dict, allowed_added=E4_ADDED_FILES) -> dict:
    """P28 §6: every file the checkpoint was trained with is byte-identical; only E4 additions are new."""
    modified = sorted(name for name, digest in trained.items() if name in current and current[name] != digest)
    removed = sorted(name for name in trained if name not in current)
    added = sorted(name for name in current if name not in trained)
    unexpected = sorted(set(added) - set(allowed_added))
    if modified or removed or unexpected:
        raise ReplayError(f"checkpoint source identity differs from the current tree: modified={modified}, "
                          f"removed={removed}, unexpected additions={unexpected}")
    return {"modified": modified, "removed": removed, "added_since_training": added, "rule": "P28 §6"}


def load_frozen_views(runs: Path, config: B2ExperimentConfig, identity: str, sources: dict, views, log=print) -> dict:
    """Frozen checkpoint, scorer, calibrations and alarm threshold per view; nothing is trained or refit."""
    summary = {role: [int(s) for s in sources[role].groups] for role in ROLES}
    expected = {"protocol": config.protocol, "data_fingerprint": identity, "roles": summary}
    current = _source_identity()
    results_path = runs / "results.json"
    reported = json.loads(results_path.read_text()) if results_path.exists() else None
    if reported is not None and reported.get("data_fingerprint") != identity:
        raise ReplayError("the run directory was produced from a different known dataset")
    frozen, unavailable = {}, {}
    for view in views:
        path = runs / f"model_{view}.pt"
        if view not in config.views or not path.exists():
            unavailable[view] = f"no frozen checkpoint {path.name} in the run directory (nothing is trained here)"
            continue
        cfg = config.train_config(view)
        fitted = load(path, device="cpu", expected_config=cfg)
        provenance = fitted.get("provenance")
        if not isinstance(provenance, dict) or {k: v for k, v in provenance.items() if k != "source_files_sha256"} != expected:
            raise ReplayError(f"{view}: checkpoint provenance does not match the known artifact and roles")
        rule = check_source_rule(provenance.get("source_files_sha256", {}), current["files_sha256"])
        checkpoint_sha = _sha256(path)
        scorer_provenance = fingerprint({"checkpoint_sha256": checkpoint_sha, "data": identity, "groups": summary["train"],
                                         "regularization": config.mahalanobis_regularization})
        scorer = MahalanobisScorer.load(runs / f"mahalanobis_{view}.npz")
        if scorer.provenance != scorer_provenance:
            raise ReplayError(f"{view}: Mahalanobis scorer is not bound to this checkpoint and training data")
        calibrations = {}
        for method in config.methods:
            calibration = RejectionCalibration.load(runs / f"rejection_{view}_{method}.json")
            expected_calibration = fingerprint({"checkpoint_sha256": checkpoint_sha, "data": identity, "method": method,
                                                "groups": summary["val-calib"], "target_acceptance": config.target_acceptance})
            if calibration.provenance != expected_calibration:
                raise ReplayError(f"{view}/{method}: rejection calibration is not bound to this checkpoint and val-calib groups")
            calibrations[method] = calibration
        # Clean alarm threshold: recomputed from known val-calib only, exactly as the experiment did.
        outputs = infer_streaming(fitted, sources["val-calib"])
        clean = sources["val-calib"].index["label"] == 0
        threshold = threshold_at_pfa((1.0 - _softmax(outputs["logits"])[:, 0])[clean], config.pfa)
        if reported is not None and view in reported.get("methods", {}):
            stored = reported["methods"][view]["alarm"]["threshold"]
            if not np.isclose(stored, threshold, rtol=0, atol=1e-9) or reported["methods"][view]["checkpoint_sha256"] != checkpoint_sha:
                raise ReplayError(f"{view}: recomputed alarm threshold or checkpoint hash differs from the run's results.json")
        frozen[view] = FrozenView(view, fitted, scorer, calibrations, float(threshold), checkpoint_sha,
                                  {"checkpoint_sha256": checkpoint_sha, "training_source_revision": fitted.get("source_revision"),
                                   "source_rule": rule, "mahalanobis_provenance": scorer.provenance,
                                   "rejection_provenance": {m: c.provenance for m, c in calibrations.items()},
                                   "rejection_thresholds": {m: c.threshold for m, c in calibrations.items()},
                                   "alarm_threshold": float(threshold), "n_clean_calibration": int(clean.sum()),
                                   "n_parameters": fitted["n_parameters"]})
        log(f"loaded frozen {view} checkpoint {checkpoint_sha[:12]} (alarm threshold {threshold:.4f})")
    return {"views": frozen, "unavailable": unavailable}


# ---------------------------------------------------------------- scoring (model boundary)


@dataclass(frozen=True)
class EvalKeys:
    """Evaluation bookkeeping; never reaches a model (outputs are invariant to it)."""

    label: np.ndarray
    group: np.ndarray
    plan_consistency: np.ndarray
    matched_bin: np.ndarray | None = None


def score_observed(view: FrozenView, observed: ObservedInputs, keys: EvalKeys, stage: str) -> dict:
    """Frozen-model outputs for observed channels only. ``keys`` only builds the source index."""
    if not isinstance(observed, ObservedInputs):
        raise ValueError("models accept ObservedInputs only")
    split = {"spec": observed.spec, "mask": observed.mask, "residual": observed.residual,
             "label": keys.label, "seed": keys.group, "plan_consistency": keys.plan_consistency}
    if stage == "matched":
        split["matched_bin"] = keys.matched_bin
    source = B2Source.from_arrays(split, kind="known" if stage == "known" else "matched",
                                  role="test" if stage == "known" else "test-matched")
    out = infer_streaming(view.fitted, source)
    logits = out["logits"]
    scores = {method: (view.scorer.score(out["embedding"]) if method == "mahalanobis" else unknown_scores(logits, method))
              for method in view.calibrations}
    probability = _softmax(logits)
    event_probability = 1.0 - probability[:, 0]
    return {"logits": logits, "prediction": logits.argmax(axis=1), "scores": scores,
            "accepted": {method: view.calibrations[method].accept(values) for method, values in scores.items()},
            "event_probability": event_probability, "alarm": event_probability > view.alarm_threshold,
            "plan_logit": None if out["plan_logits"] is None else out["plan_logits"][:, 0]}


# ---------------------------------------------------------------- metrics


def _db_power(values) -> np.ndarray:
    """Mean linear power over time and frequency, in dB, per leading index."""
    power = 10.0 ** (np.asarray(values, dtype=np.float64) / 10.0)
    return 10.0 * np.log10(power.reshape(len(power), -1).mean(axis=1))


def _core_power_db(values, core) -> np.ndarray:
    """Mean linear power over time and the bins of ``core`` (``[n, 512]`` boolean), in dB, per scene."""
    power = 10.0 ** (np.asarray(values, dtype=np.float64) / 10.0)
    return 10.0 * np.log10((power * core[:, None, :]).sum(axis=(1, 2)) / (core.sum(axis=1) * power.shape[1]))


def _residual_diagnostics(observations, original_core):
    """Observable-only cancellation visibility. ``original_core``: bins above -3 dB in the ORIGINAL co-pol
    mask, fixed across conditions so the displacement compares the same bins (the P28 diagnostic is the
    full-band one; the core-band one is an additive diagnostic logged in P28 section 13)."""
    spec_co = np.stack([o.spec[0] for o in observations])
    residual = np.stack([o.residual for o in observations])
    full_spec, full_residual = _db_power(spec_co), _db_power(residual)
    core_spec, core_residual = _core_power_db(spec_co, original_core), _core_power_db(residual, original_core)
    return {"spec_co_total_db": full_spec, "residual_total_db": full_residual,
            "cancellation_depth_db": full_spec - full_residual,
            "spec_co_core_db": core_spec, "residual_core_db": core_residual,
            "cancellation_depth_core_db": core_spec - core_residual}


def _summary(values, groups):
    return _rate(np.asarray(values, dtype=float), groups)


def _view_metrics(keys, outputs, original, diagnostics):
    """Per-condition metrics of one view on the paired population (``outputs`` and ``original`` are aligned)."""
    labels, groups = keys.label.astype(np.int64), keys.group
    prediction, base = outputs["prediction"], original["prediction"]
    clean = labels == 0
    n_classes = len(LABELS)
    out = {"n_scenes": int(len(labels)), "n_groups": int(len(np.unique(groups))),
           "agreement_with_original_label": _summary(prediction == labels, groups),
           "macro_f1_vs_original_label": macro_f1(labels, prediction, n_classes) if len(labels) else None,
           "confusion_original_label": confusion(labels, prediction, n_classes).tolist(),
           "prediction_change_vs_original": None if outputs is original else _summary(prediction != base, groups),
           "transition_matrix": confusion(base, prediction, n_classes).tolist(),
           "max_abs_logit_difference_vs_original": None if outputs is original else float(np.max(np.abs(outputs["logits"] - original["logits"]))),
           "clean_false_alarm": _summary(outputs["alarm"][clean], groups[clean]),
           "event_detection": _summary(outputs["alarm"][~clean], groups[~clean]),
           "alarm_base_rate_original": _summary(original["alarm"], groups),
           "known_acceptance": {method: _summary(values, groups) for method, values in outputs["accepted"].items()},
           "score_displacement": {method: _summary(outputs["scores"][method] - original["scores"][method], groups)
                                  for method in outputs["scores"]},
           "class_called_rate": {LABELS[c]: _summary(prediction == c, groups) for c in sorted(set(prediction.tolist()) | set(labels.tolist()))}}
    if outputs["plan_logit"] is not None:
        positive = outputs["plan_logit"] > 0
        out["plan_consistency"] = {
            "positive_class": "planned_carrier_missing",
            "predicted_positive_rate": _summary(positive, groups),
            "agreement_with_original_target": _summary(positive == (keys.plan_consistency == 1), groups),
            "change_vs_original_prediction": _summary(positive != (original["plan_logit"] > 0), groups),
            "note": "descriptive: the target is relative to the original operator plan; counterfactual meaning is undefined"}
    else:
        out["plan_consistency"] = None
    asi, unauthorized = LABELS.index("adjacent_satellite"), LABELS.index("unauthorized")
    if {asi, unauthorized} <= set(labels.tolist()):
        pair_mask = np.isin(labels, [asi, unauthorized])
        out["asi_vs_unauthorized"] = {method: _pair_metrics(prediction, outputs["accepted"][method], labels, groups, pair_mask)
                                      for method in outputs["accepted"]}
        if outputs is not original:
            out["asi_vs_unauthorized"] = {
                method: {key.replace("pair_accuracy", "pair_agreement_with_original_label"): value
                         for key, value in values.items()}
                for method, values in out["asi_vs_unauthorized"].items()}
    else:
        out["asi_vs_unauthorized"] = None
    out["residual"] = {key: _summary(values, groups) for key, values in diagnostics.items()}
    return out


# ---------------------------------------------------------------- observation-only baselines (inputs only)

BASELINE_READS = {
    "edsc_score_db": ["co-pol PSD (core-bin reference)", "co-pol operator mask (core bins)", "co-pol residual"],
    "ca_cfar_planned": ["co-pol PSD", "co-pol operator mask"],
    "ca_cfar_blind": ["co-pol PSD only: ignores the operator plan and the residual by construction"],
    "xgboost_features_26": ["co and cross PSD", "co and cross operator masks", "co-pol residual"]}


def _changed(values) -> int:
    return int(np.count_nonzero(np.asarray(values)))


def baseline_inputs(conditions: dict, groups) -> dict:
    """Recompute the input statistics of the observation-only baselines on every condition (P28 section 10).

    ``conditions`` maps a condition name to ``ObservedInputs`` of the paired population. No baseline model,
    threshold or decision exists here: EDSC, CA-CFAR and XGBoost are only evaluated as *input* displacement, so
    nothing is refit, recalibrated or compared across the binary, eight-class and open-set tasks.
    """
    def edsc(o):
        return residual_energy(o.spec, o.mask, o.residual)["score_db"]

    def cfar_columns(o, use_plan):
        return cfar.features(o.spec[:, 0], o.mask[:, 0], FREQUENCIES_HZ, np.full(len(o.spec), 36e6), use_plan)

    statistics = {"edsc_score_db": edsc, "ca_cfar_planned": lambda o: cfar_columns(o, True),
                  "ca_cfar_blind": lambda o: cfar_columns(o, False), "xgboost_features_26": lambda o: extract_features(o.spec, o.mask, o.residual)}
    values, failures = {}, {}
    for method, function in statistics.items():
        try:
            values[method] = {name: np.asarray(function(observed), dtype=np.float64) for name, observed in conditions.items()}
        except ValueError as error:
            failures[method] = str(error)
    out = {}
    for method in statistics:
        if method in failures:
            out[method] = {"available": False, "reason": failures[method], "reads": BASELINE_READS[method]}
            continue
        entry = {"available": True, "reads": BASELINE_READS[method], "displacement_vs_original": {}}
        for name in ("MASK_ONLY", "RECEIVER_CONSISTENT"):
            delta = values[method][name] - values[method]["original"]
            if method == "xgboost_features_26":
                entry["displacement_vs_original"][name] = {
                    "mean_abs_by_feature": {feature: float(np.abs(delta[:, i]).mean()) for i, feature in enumerate(FEATURE_NAMES)},
                    "n_features_changed": int(np.count_nonzero(np.abs(delta).max(axis=0))), "n_features": len(FEATURE_NAMES),
                    "n_scenes": int(len(delta))}
            elif method.startswith("ca_cfar"):
                entry["displacement_vs_original"][name] = {
                    column: {"displacement": _summary(delta[:, i], groups), "n_scenes_changed": _changed(delta[:, i])}
                    for i, column in enumerate(("time_averaged_cell_db", "single_cell_db"))}
            else:
                entry["displacement_vs_original"][name] = {"displacement_db": _summary(delta, groups), "n_scenes_changed": _changed(delta)}
        out[method] = entry
    return {"status": "INPUTS_RECOMPUTED_NO_MODEL",
            "note": "no frozen baseline model or clean-only threshold artifact exists on main; no baseline decision, alarm, "
                    "accuracy or OSCR is computed. EDSC (binary), CA-CFAR (binary) and XGBoost (eight-class) are different "
                    "tasks and are never compared with each other or with the neural views.",
            "methods": out}


# ---------------------------------------------------------------- orchestration


def _selected_scenes(source: ReplaySource, config: A5Config):
    groups = list(source.groups[:config.n_groups])
    if len(groups) < config.n_groups:
        raise ValueError(f"the artifact role holds only {len(groups)} groups")
    return [(group, label) for group in groups for label in config.labels]


def _reproduction_command(args) -> str:
    """The CLI call that reproduces this exact invocation (config file plus any overrides that were passed)."""
    parts = ["python -m geoml.b2_a5", f"--config {args['config']}"]
    for flag, key in (("--perturbation", "perturbation"), ("--scope", "scope")):
        if args.get(key):
            parts.append(f"{flag} {args[key]}")
    parts += [f"--data {args['data']}", f"--runs {args['runs']}", f"--out {args['out']}"]
    if args.get("matched_data"):
        parts.append(f"--matched-data {args['matched_data']}")
    return " \\\n    ".join(parts)


def _atomic_text(path: Path, text: str) -> None:
    _durable_text(path, text)


def _environment() -> dict:
    """Library/platform identity of the process that wrote cached replay arrays (they are bit-comparable only within it)."""
    return {"python": platform.python_version(), "numpy": np.__version__, "scipy": scipy.__version__,
            "torch": str(torch.__version__), "machine": platform.machine(), "system": platform.system()}


class _InvocationLock:
    """Exclusive advisory lock on an output directory; the OS releases it if the process dies, so a crash never blocks resumption."""

    def __init__(self, directory: Path):
        self.stream = None
        if fcntl is None:                                   # pragma: no cover
            return
        stream = open(directory / ".a5.lock", "a+")
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            stream.close()
            raise ValueError(f"another process is running this invocation ({directory}); wait for it or use a new "
                             "output directory") from error
        self.stream = stream

    def release(self):
        if self.stream is not None:
            self.stream.close()
            self.stream = None


STATE_KEYS = ("state_contract", "experiment_fingerprint", "scenario_id", "label", "record", "parity", "work",
              "arrays_sha256")
OWN_TEMPORARIES = ("results.json.tmp", "results.json.sha256.tmp", "results.md.tmp", "a5_config.json.tmp")


def _unique_pairs(pairs):
    values = {}
    for key, value in pairs:
        if key in values:
            raise ValueError(f"duplicate key {key}")
        values[key] = value
    return values


def _reject_constant(value):
    raise ValueError(f"nonfinite constant {value}")


def _read_object(path: Path, what: str) -> dict:
    """Strict JSON object: duplicate keys and NaN/Infinity constants are rejected, never silently resolved."""
    try:
        value = json.loads(path.read_text(), object_pairs_hook=_unique_pairs, parse_constant=_reject_constant)
    except (OSError, ValueError) as error:
        raise ValueError(f"{path} is not a valid {what}; use a new output directory") from error
    if not isinstance(value, dict):
        raise ValueError(f"{path} is not a valid {what}; use a new output directory")
    return value


class SceneState:
    """Verified per-scene progress of one invocation, so an interrupted run continues instead of restarting.

    Every completed scene stores its replayed PSD and recomputed residual (float16, the expensive part) in
    ``state/``; a small JSON committed last carries the scene record, the parity report, the work done and the
    SHA-256 of the arrays, and is itself covered by a digest of its whole payload and bound to the experiment
    identity and to the library/platform environment that produced the arrays. A leftover ``*.tmp`` file or an
    array file without its JSON is an interrupted write: it was never committed and is discarded. A committed
    entry that fails its binding, digest or checksum was modified and is rejected (fail closed), never silently
    recomputed over. The digests detect accidental or partial modification; they do not authenticate the writer.
    """

    def __init__(self, directory: Path, identity: str, log=print):
        self.directory, self.identity, self.log = directory, identity, log
        directory.mkdir(parents=True, exist_ok=True)
        marker = directory / "identity.json"
        if marker.exists():
            stored = _read_object(marker, "A5 state marker")
            if stored.get("experiment_fingerprint") != identity:
                raise ValueError(f"{directory} belongs to a different experiment identity; use a new output directory")
            if stored.get("environment") != _environment():
                raise ValueError(f"{directory} was written under a different library/platform environment; use a new "
                                 "output directory")
        else:
            if any(path.name != "identity.json.tmp" for path in directory.iterdir()):
                raise ValueError(f"{directory} is not an A5 state directory (no identity marker); use a new output directory")
            _write_json(marker, {"experiment_fingerprint": identity, "contract": CONTRACT, "environment": _environment()})
        for leftover in sorted(directory.glob("*.tmp")):
            leftover.unlink()
            log(f"discarded interrupted write {leftover.name}")
        for orphan in sorted(directory.glob("scene-*.npz")):
            if not orphan.with_suffix(".json").exists():
                orphan.unlink()
                log(f"discarded uncommitted arrays {orphan.name}")

    def _paths(self, group, label):
        stem = self.directory / f"scene-{int(group)}-{label}"
        return stem.with_suffix(".json"), stem.with_suffix(".npz")

    def _payload(self, group, label, record, parity, work, arrays_sha256) -> dict:
        return _json_safe({"state_contract": STATE_CONTRACT, "experiment_fingerprint": self.identity,
                           "scenario_id": int(group), "label": label, "record": record, "parity": parity, "work": work,
                           "arrays_sha256": arrays_sha256})

    @staticmethod
    def _check_work_binding(meta_path, meta) -> None:
        """Logical work, parity, arrays and the record must tell one consistent story (a consistent re-sign is still caught)."""
        work, record = meta["work"], meta["record"]
        if (not isinstance(work, dict) or set(work) != {"replays", "cancellations", "recomputations"}
                or any(type(value) is not int for value in work.values())
                or work["replays"] not in (0, 1) or work["recomputations"] not in (0, 1)
                or work["cancellations"] != work["replays"] + work["recomputations"]
                or work["recomputations"] > work["replays"]):
            raise ValueError(f"{meta_path}: invalid metadata logical work counts; use a new output directory")
        if work["replays"]:
            if (not isinstance(meta["parity"], dict) or type(meta["parity"].get("exact")) is not bool
                    or not isinstance(meta["arrays_sha256"], str) or len(meta["arrays_sha256"]) != 64
                    or not isinstance(record, dict) or record.get("status") != "applied"
                    or type(record.get("residual_recomputed")) is not bool
                    or record["residual_recomputed"] != bool(work["recomputations"])):
                raise ValueError(f"{meta_path}: invalid metadata parity/recomputation binding (replayed arrays must exist "
                                 "exactly for applied scenes); use a new output directory")
        elif (meta["parity"] is not None or meta["arrays_sha256"] is not None or not isinstance(record, dict)
              or record.get("status") not in ("not_applicable", "blocked") or record.get("residual_recomputed") is not None):
            raise ValueError(f"{meta_path}: invalid metadata for an unapplied scene; use a new output directory")

    def load(self, group, label):
        meta_path, array_path = self._paths(group, label)
        if not meta_path.exists():
            return None
        meta = _read_object(meta_path, "A5 scene state")
        if set(meta) != set(STATE_KEYS) | {"metadata_sha256"} or meta["state_contract"] != STATE_CONTRACT:
            raise ValueError(f"{meta_path}: incompatible metadata schema; use a new output directory")
        if (meta["experiment_fingerprint"] != self.identity or meta["scenario_id"] != int(group) or meta["label"] != label):
            raise ValueError(f"{meta_path} is bound to a different scene or experiment identity; use a new output directory")
        if fingerprint({key: meta[key] for key in STATE_KEYS}) != meta["metadata_sha256"]:
            raise ValueError(f"{meta_path}: metadata checksum mismatch (the committed state was modified); use a new "
                             "output directory")
        self._check_work_binding(meta_path, meta)
        arrays = None
        if meta["arrays_sha256"] is not None:
            if not array_path.exists() or _file_hash(array_path) != meta["arrays_sha256"]:
                raise ValueError(f"{array_path} is missing or modified; use a new output directory")
            with np.load(array_path, allow_pickle=False) as archive:
                arrays = {key: archive[key] for key in archive.files}
            if (set(arrays) != {"spec", "residual"} or arrays["spec"].shape != (2, 128, 512) or arrays["spec"].dtype != np.float16
                    or arrays["residual"].shape != (128, 512) or arrays["residual"].dtype != np.float16
                    or not np.isfinite(arrays["spec"]).all() or not np.isfinite(arrays["residual"]).all()):
                raise ValueError(f"{array_path} does not hold a valid replayed observation; use a new output directory")
        return {**meta, "arrays": arrays}

    def save(self, group, label, *, record, parity, work, arrays):
        meta_path, array_path = self._paths(group, label)
        digest = None
        if arrays is not None:
            temporary = array_path.with_name(array_path.name + ".tmp")
            with open(temporary, "wb") as stream:
                np.savez(stream, spec=arrays["spec"], residual=arrays["residual"])
                stream.flush()
                os.fsync(stream.fileno())
            temporary.replace(array_path)
            digest = _file_hash(array_path)
        payload = self._payload(group, label, record, parity, work, digest)
        _write_json(meta_path, {**payload, "metadata_sha256": fingerprint(payload)})


def _output_state(out: Path, identity: str, log=print):
    """Reuse only a complete, checksummed result with this experiment identity (P28 §11).

    Returns the stored result, or ``None`` when the final write was interrupted (results without their
    checksum sidecar but with this identity): the result is then rebuilt from the verified per-scene state.
    Anything else that does not verify is rejected. Only this module's own temporary file names are discarded,
    and only after the directory has been shown to be this experiment's output (or to hold no result at all).
    """
    results, sidecar = out / "results.json", out / "results.json.sha256"
    stored, rebuild = None, False
    if results.exists() or sidecar.exists():
        if not results.exists():
            raise ValueError(f"{sidecar} has no results.json; use a new output directory")
        try:
            stored = json.loads(results.read_text())
        except ValueError as error:
            raise ValueError(f"{results} is incomplete or modified; use a new output directory") from error
        if not isinstance(stored, dict) or stored.get("experiment_fingerprint") is None:
            raise ValueError(f"{results} is incomplete or modified; use a new output directory")
        if stored["experiment_fingerprint"] != identity:
            raise ValueError(f"{results} was produced by a different experiment identity; use a new output directory")
        if not sidecar.exists():
            log("final result lacked its checksum (interrupted); rebuilding it from the verified per-scene state")
            stored, rebuild = None, True
        elif sidecar.read_text().strip() != _file_hash(results):
            raise ValueError(f"{results} is incomplete or modified; use a new output directory")
    for name in OWN_TEMPORARIES:
        leftover = out / name
        if leftover.exists():
            leftover.unlink()
            log(f"discarded interrupted write {name}")
    return None if rebuild else stored


def _frozen_file_hashes(runs: Path, experiment: B2ExperimentConfig, views) -> dict:
    """SHA-256 of every frozen file an evaluation reads, so reuse cannot outlive a changed run directory."""
    names = ["config.json", "results.json"]
    for view in views:
        names += [f"model_{view}.pt", f"mahalanobis_{view}.npz"] + [f"rejection_{view}_{m}.json" for m in experiment.methods]
    return {name: _sha256(runs / name) for name in names if (runs / name).exists()}


def _scene_conditions(stored, corruption, arrays) -> dict:
    """The three observations of a scene rebuilt from cached replay arrays (identical to a fresh replay)."""
    masks = rebuild_masks(corruption.plans)
    return {"original": SceneObservation(stored.spec, stored.mask, stored.residual),
            "MASK_ONLY": SceneObservation(stored.spec, masks, stored.residual),
            "RECEIVER_CONSISTENT": SceneObservation(arrays["spec"], masks, arrays["residual"])}


def run_a5(config: A5Config, data, runs, out, *, matched_data=None, command_args=None, log=print) -> dict:
    """Evaluate one perturbation configuration; an interrupted invocation continues from verified state (P28 §11a)."""
    held = []
    try:
        return _run_a5(config, data, runs, out, matched_data=matched_data, command_args=command_args, log=log, held=held)
    finally:
        for lock in held:
            lock.release()


def _run_a5(config, data, runs, out, *, matched_data, command_args, log, held) -> dict:
    started, clock = time.time(), time.perf_counter()
    data, runs, out = Path(data), Path(runs), Path(out)
    for other in (data, runs) + (() if matched_data is None else (Path(matched_data),)):
        here, there = out.resolve(), other.resolve()
        if here == there or here in there.parents or there in here.parents:
            raise ValueError(f"--out must be separate from the input directory {other}")
    if (config.stage == "matched") != (matched_data is not None):
        raise ValueError("the matched stage needs --matched-data (and only it)")
    plan_budget = config.plan_budget()
    experiment = B2ExperimentConfig.from_file(runs / "config.json")
    manifest, identity, sources = open_b2_known(data)
    if manifest["protocol"] != experiment.protocol or manifest["benchmark_complete"] is not False or set(sources) != set(ROLES):
        raise ReplayError("known artifact does not match the frozen experiment configuration or role set")
    replay_root, matched_identity = data, None
    if config.stage == "matched":
        matched_manifest, matched_identity, matched_source = open_b2_matched(matched_data)
        if (matched_manifest["request"]["known"]["known_data_fingerprint"] != identity
                or matched_manifest["config"] != manifest["config"]
                or matched_manifest.get("cancellation") != manifest.get("cancellation")):
            raise ReplayError("the matched artifact is not bound to this known dataset, physics and cancellation")
        if any(role_for_group(int(g)) != "test-matched" for g in matched_source.groups):
            raise ReplayError("matched groups must belong to the frozen test-matched role")
        replay_root = matched_data
    source = open_replay_source(replay_root, config.stage, "test")
    if source.config.to_dict() != manifest["config"] or source.cancellation.to_dict() != manifest.get("cancellation"):
        raise ReplayError("replay source physics or cancellation differ from the known artifact")
    scenes = _selected_scenes(source, config)
    implementation = _source_identity()
    frozen_files = _frozen_file_hashes(runs, experiment, config.views)
    experiment_fingerprint = fingerprint({
        "contract": CONTRACT, "plan_contract": PLAN_CONTRACT, "config": config.to_dict(), "data": identity,
        "matched": matched_identity, "request": source.request_fingerprint, "runs_config": experiment.resolved(),
        "frozen_files": frozen_files, "source_tree": implementation["files_sha256"]})
    out.mkdir(parents=True, exist_ok=True)
    held.append(_InvocationLock(out))
    reused = _output_state(out, experiment_fingerprint, log)
    if reused is not None:
        log(f"reusing verified A5 result {experiment_fingerprint[:12]}")
        return reused
    loaded = load_frozen_views(runs, experiment, identity, sources, config.views, log)   # fail closed before any state is written
    frozen = loaded["views"]
    state = SceneState(out / "state", experiment_fingerprint, log)
    _atomic_text(out / "a5_config.json", json.dumps(config.to_dict(), indent=1) + "\n")
    budget = Budget(CAPS["max_replays"], CAPS["max_cancellations"])
    receiver = FrozenReceiver(source.cancellation, budget)
    records, parity, rows, from_state, work = [], [], [], 0, {"replays": 0, "cancellations": 0, "recomputations": 0}
    for group, label in scenes:
        stored = source.stored(group, label)
        corruption = corrupt_operator_plan(
            stored.original_plans(), perturbation=config.perturbation, scope=config.scope, scenario_id=group,
            allowed_intervention_context=stored.intervention_context() if config.perturbation == "authorize_intruder" else None)
        record = {"scenario_id": group, "label": label, **corruption.to_dict(), "flags": {}, "residual_recomputed": None}
        cached = state.load(group, label)
        if cached is not None:                                   # verified progress of an interrupted run
            expected = {k: record[k] for k in ("original_identity", "corrupted_identity", "status", "reason", "co_changed", "cross_changed")}
            if {k: cached["record"][k] for k in expected} != expected:
                raise ValueError(f"cached scene {group}/{label} no longer matches its recomputed corruption; use a new output directory")
            record = cached["record"]
            conditions = None if cached["arrays"] is None else _scene_conditions(stored, corruption, cached["arrays"])
            if conditions is not None:
                parity.append(cached["parity"])
            from_state += 1
            scene_work = cached["work"]
        elif not corruption.applied:
            conditions, scene_work = None, {"replays": 0, "cancellations": 0, "recomputations": 0}
            state.save(group, label, record=record, parity=None, work=scene_work, arrays=None)
        else:
            replay = replay_scene(source, label, group, budget)
            report_parity = {"scenario_id": group, "label": label, **check_parity(replay, stored)}
            calls_before = receiver.calls
            built = build_conditions(replay, stored, corruption, receiver)
            record["flags"], record["residual_recomputed"] = reporting_flags(replay, corruption), built["residual_recomputed"]
            conditions = {name: built[name] for name in CONDITIONS}
            scene_work = {"replays": 1, "cancellations": 1 + (receiver.calls - calls_before), "recomputations": receiver.calls - calls_before}
            state.save(group, label, record=record, parity=report_parity, work=scene_work,
                       arrays={"spec": conditions["RECEIVER_CONSISTENT"].spec, "residual": conditions["RECEIVER_CONSISTENT"].residual})
            parity.append(report_parity)
            del replay                                            # raw IQ is transient
        for key in work:
            work[key] += scene_work[key]
        if work["replays"] > CAPS["max_replays"] or work["cancellations"] > CAPS["max_cancellations"]:
            raise BudgetExceeded("resumed logical work exceeds invocation caps")
        records.append(record)
        rows.append({"stored": stored, "corruption": corruption, "conditions": conditions})
    if from_state:
        log(f"resumed {from_state}/{len(rows)} scenes from verified state; computed {len(rows) - from_state} now")
    applicable = [row for row in rows if row["conditions"] is not None]
    populations = {"selected": len(rows), "applied": len(applicable),
                   "not_applicable": _tally(records, "not_applicable"), "blocked": _tally(records, "blocked")}
    keys_all = _keys([row["stored"] for row in rows], config.stage)
    keys_app = _keys([row["stored"] for row in applicable], config.stage)
    views, scored = {}, 0
    for name in config.views:
        if name not in frozen:
            views[name] = {"available": False, "reason": loaded["unavailable"].get(name, "view not loaded")}
            continue
        view = frozen[name]
        original_all = score_observed(view, ObservedInputs.stack(
            [SceneObservation(r["stored"].spec, r["stored"].mask, r["stored"].residual) for r in rows]), keys_all, config.stage)
        scored += len(rows)
        entry = {"available": True, "identity": view.identity,
                 "original_selected_population": _original_summary(original_all, keys_all, config.stage)}
        if applicable:
            entry["paired_population"] = {"n_scenes": len(applicable)}
            original_core = np.stack([r["stored"].mask[0] > CORE_DB for r in applicable])
            entry["conditions"], scored_outputs = {}, {}
            for condition in CONDITIONS:
                observations = [r["conditions"][condition] for r in applicable]
                # Every condition of the paired population is scored with the same batching (incl. `original`).
                outputs = original_all if (condition == "original" and len(applicable) == len(rows)) else score_observed(
                    view, ObservedInputs.stack(observations), keys_app, config.stage)
                if not (condition == "original" and len(applicable) == len(rows)):
                    scored += len(observations)
                scored_outputs[condition] = outputs
                diagnostics = _residual_diagnostics(observations, original_core)
                entry["conditions"][condition] = _view_metrics(keys_app, outputs, scored_outputs["original"], diagnostics)
                entry["conditions"][condition]["_residual_raw"] = diagnostics
            _residual_displacement(entry["conditions"], keys_app.group)
            entry["mask_only_vs_receiver_consistent"] = _identical_outputs(name, scored_outputs, applicable)
        else:
            entry["paired_population"] = {"n_scenes": 0}
            entry["conditions"] = None
        views[name] = entry
    for entry in views.values():
        for condition in (entry.get("conditions") or {}).values():
            condition.pop("_residual_raw", None)
    baseline = None
    if applicable:
        baseline = baseline_inputs({condition: ObservedInputs.stack([r["conditions"][condition] for r in applicable])
                                    for condition in CONDITIONS}, keys_app.group)
    elapsed = time.perf_counter() - clock
    result = {
        "contract": CONTRACT, "plan_contract": PLAN_CONTRACT, "benchmark_complete": False,
        "evidence_class": "BOUNDED_PILOT",
        "authorization": AUTHORIZATION, "experiment_fingerprint": experiment_fingerprint,
        "configuration": config.to_dict(), "caps": CAPS, "planned_budget_upper_bound": plan_budget,
        "source": {"stage": config.stage, "protocol": source.protocol, "role": source.role,
                   "known_data_fingerprint": identity, "matched_data_fingerprint": matched_identity,
                   "request_fingerprint": source.request_fingerprint, "receiver_calibration": source.manifest["calibration"],
                   "cancellation": source.cancellation.to_dict(), "generation_config": manifest["config"],
                   "generator_source_matches_artifact": True},
        "implementation": {"git_sha": implementation["revision"], "source_tree_fingerprint": fingerprint(implementation["files_sha256"]),
                           "source_files_sha256": implementation["files_sha256"],
                           "e4_source_files_sha256": {name: implementation["files_sha256"][name] for name in E4_ADDED_FILES},
                           "frozen_run_files_sha256": frozen_files},
        "frozen_models": {name: (frozen[name].identity if name in frozen else {"available": False,
                          "reason": loaded["unavailable"].get(name)}) for name in config.views},
        "experiment_reference": {"runs_config": experiment.resolved(), "labels": list(LABELS)},
        "populations": populations, "scenes": records, "parity": parity,
        "parity_summary": {"n_scenes_checked": len(parity), "all_exact": all(p["exact"] for p in parity) if parity else None,
                           "max_abs_diff_db": max((max(p[k]["max_abs_diff_db"] for k in ("spec", "mask", "residual"))
                                                    for p in parity), default=None)},
        "views": views,
        "counts": {"physical_replays": work["replays"], "cancellation_evaluations": work["cancellations"],
                   "receiver_recomputations": work["recomputations"], "scored_samples": scored,
                   "scenes_selected": len(rows), "scenes_applicable": len(applicable)},
        "label_policy": {"layers": ["original physical label", "original operator-relative target (plan_consistency)",
                                    "counterfactual operator-plan intervention", "frozen classifier output"],
                         "counterfactual_metric_name": "agreement_with_original_label (descriptive, not accuracy)",
                         "alarm_rates": "clean_false_alarm / event_detection are alarm rates among scenes whose ORIGINAL label is clean / not clean; "
                                        "under a counterfactual condition they are not false-alarm or detection rates when the intervention changes what an alarm means",
                         "mask_only": "weaker control: stored residual, rebuilt masks; never receiver-consistent",
                         "co_dual_views": "co and dual views do not read the residual; MASK_ONLY and RECEIVER_CONSISTENT differ only through the replayed PSD"},
        "baselines": baseline if baseline is not None else {"status": "INPUTS_RECOMPUTED_NO_MODEL", "methods": None,
                                                             "note": "empty paired population"},
        "resume": {"scenes_selected": len(rows), "scenes_from_state": from_state, "scenes_computed_now": len(rows) - from_state,
                   "replays_now": budget.replays, "cancellations_now": budget.cancellations,
                   "note": "counts above are the logical invocation total; a resumed run reports the same totals as an uninterrupted one"},
        "cost": {"elapsed_s": elapsed, "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss, "cpu_count": os.cpu_count(),
                 "device": "cpu", "python": platform.python_version(), "numpy": np.__version__, "scipy": scipy.__version__,
                 "torch": str(torch.__version__), "started_unix": started},
        "reproduction_command": _reproduction_command(command_args or {"config": str(out / "a5_config.json"), "data": str(data),
                                                                       "runs": str(runs), "out": str(out), "matched_data": matched_data}),
        "limitations": ["bounded pilot: at most two scenario groups and two classes; no population-level inference",
                        "checkpoints are whatever the run directory supplies; the pilot ones are chance-level stand-ins",
                        "counterfactual outputs are descriptive agreement, not accuracy",
                        "simulator-only evidence; no field data"]}
    _write_json(out / "results.json", result)
    _atomic_text(out / "results.json.sha256", _file_hash(out / "results.json") + "\n")
    _atomic_text(out / "results.md", report(result))
    log(f"wrote {out / 'results.json'}")
    return json.loads((out / "results.json").read_text())


def _take(outputs, keep):
    """Rows ``keep`` of a ``score_observed`` result."""
    return {key: (None if value is None else {m: s[keep] for m, s in value.items()} if isinstance(value, dict) else value[keep])
            for key, value in outputs.items()}


def _tally(records, status):
    tally = {}
    for record in records:
        if record["status"] == status:
            tally[record["reason"]] = tally.get(record["reason"], 0) + 1
    return tally


def _keys(stored_rows, stage) -> EvalKeys:
    label = np.array([LABELS.index(s.label) for s in stored_rows], dtype=np.int64)
    group = np.array([s.group for s in stored_rows], dtype=np.int64)
    consistency = np.array([s.plan_consistency for s in stored_rows], dtype=np.int64)
    bins = None
    if stage == "matched":
        bins = np.array([int(s.record["matched"]["bin"]) for s in stored_rows], dtype=np.int64)
    return EvalKeys(label, group, consistency, bins)


def _original_summary(outputs, keys, stage):
    labels, groups = keys.label.astype(np.int64), keys.group
    return {"n_scenes": int(len(labels)), "n_groups": int(len(np.unique(groups))),
            "accuracy": _summary(outputs["prediction"] == labels, groups),
            "macro_f1": macro_f1(labels, outputs["prediction"], len(LABELS)),
            "note": "stored arrays and original plans: accuracy is defined here (conventional B2 labels)"}


def _residual_displacement(conditions, groups):
    base = conditions["original"]["_residual_raw"]
    for name in ("MASK_ONLY", "RECEIVER_CONSISTENT"):
        raw = conditions[name]["_residual_raw"]
        conditions[name]["residual_displacement_vs_original"] = {
            key: _summary(raw[key] - base[key], groups) for key in raw}


def _identical_outputs(name, scored, applicable):
    """Whether MASK_ONLY and RECEIVER_CONSISTENT feed this view identical inputs and produce identical logits."""
    a = [r["conditions"]["MASK_ONLY"] for r in applicable]
    b = [r["conditions"]["RECEIVER_CONSISTENT"] for r in applicable]
    spec_same = all(np.array_equal(x.spec, y.spec) for x, y in zip(a, b))
    residual_same = all(np.array_equal(x.residual, y.residual) for x, y in zip(a, b))
    return {"view_reads_residual": name == "dual_residual", "psd_identical": bool(spec_same),
            "residual_identical": bool(residual_same),
            "logits_identical": bool(np.array_equal(scored["MASK_ONLY"]["logits"], scored["RECEIVER_CONSISTENT"]["logits"])),
            "note": "co/dual views never read the residual; an unchanged co descriptor reuses the replay residual without a cancellation call; equality to stored residual requires exact replay parity"}


def report(result: dict) -> str:
    cfg = result["configuration"]
    lines = [f"# B2 A5 plan corruption ({result['contract']}) — {cfg['perturbation']} / {cfg['scope']} / {cfg['stage']}", "",
             f"Evidence class **{result['evidence_class']}**; benchmark complete: **{result['benchmark_complete']}**. "
             f"Selected {result['populations']['selected']} scenes, applied {result['populations']['applied']}; "
             f"not applicable {result['populations']['not_applicable']}; blocked {result['populations']['blocked']}.",
             f"Replays {result['counts']['physical_replays']}, cancellations {result['counts']['cancellation_evaluations']}, "
             f"scored samples {result['counts']['scored_samples']}; parity all-exact: {result['parity_summary']['all_exact']}.", "",
             "Counterfactual columns are **agreement with the original label**, not accuracy. MASK_ONLY is the weaker control. "
             "Alarm columns are alarm rates among scenes whose ORIGINAL label is clean / not clean; under a counterfactual "
             "condition they are not false-alarm or detection rates.", "",
             "| View | Condition | n | Agreement with original label | Prediction changed | Alarm among original-clean | Alarm among original-event |",
             "|---|---|---|---|---|---|---|"]
    def pct(rate):
        return "n/a" if rate is None or rate.get("mean") is None else f"{100 * rate['mean']:.1f}% (n={rate['n_samples']})"
    for name, entry in result["views"].items():
        if not entry.get("available") or not entry.get("conditions"):
            lines.append(f"| {name} | – | 0 | n/a | n/a | n/a | n/a |")
            continue
        for condition, metrics in entry["conditions"].items():
            lines.append(f"| {name} | {condition} | {metrics['n_scenes']} | {pct(metrics['agreement_with_original_label'])} | "
                         f"{pct(metrics['prediction_change_vs_original'])} | {pct(metrics['clean_false_alarm'])} | "
                         f"{pct(metrics['event_detection'])} |")
    lines += ["", f"Reproduction:\n\n```\n{result['reproduction_command']}\n```", ""]
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", required=True, help="A5 JSON configuration (one perturbation x scope)")
    parser.add_argument("--data", required=True, help="verified B2-feat/1 known artifact")
    parser.add_argument("--runs", required=True, help="geoml.b2_experiment output with frozen checkpoints")
    parser.add_argument("--out", required=True)
    parser.add_argument("--matched-data", help="verified B2-match/1 artifact (stage 'matched')")
    parser.add_argument("--perturbation", choices=PERTURBATIONS, help="override the configuration's perturbation")
    parser.add_argument("--scope", choices=SCOPES, help="override the configuration's scope")
    args = parser.parse_args(argv)
    try:
        raw = json.loads(Path(args.config).read_text())
        if args.perturbation:
            raw["perturbation"] = args.perturbation
        if args.scope:
            raw["scope"] = args.scope
        config = A5Config(**{**raw, "labels": tuple(raw.get("labels", ())), "views": tuple(raw.get("views", VIEWS))})
        run_a5(config, args.data, args.runs, args.out, matched_data=args.matched_data,
               command_args={"config": args.config, "perturbation": args.perturbation, "scope": args.scope,
                             "data": args.data, "runs": args.runs, "out": args.out, "matched_data": args.matched_data})
    except (ValueError, FileNotFoundError, TypeError) as error:
        parser.exit(2, f"error: {error}\n")


if __name__ == "__main__":
    main()

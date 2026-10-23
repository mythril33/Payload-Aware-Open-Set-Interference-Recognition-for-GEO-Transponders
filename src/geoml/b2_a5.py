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

import numpy as np
import torch

from geosim.b2_protocol import LABELS, role_for_group
from geosim.b2_scenarios import MATCHED_LABELS
from geosim.dataset import _file_hash

from .artifacts import fingerprint
from . import cfar
from .b2_a5_plan import CONTRACT as PLAN_CONTRACT
from .b2_a5_plan import PERTURBATIONS, SCOPES, corrupt_operator_plan
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


def _write_json(path: Path, value) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(_json_safe(value), indent=1, sort_keys=False, allow_nan=False) + "\n")
    temporary.replace(path)


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
    parts = ["python -m geoml.b2_a5", f"--config {args['config']}", f"--data {args['data']}", f"--runs {args['runs']}",
             f"--out {args['out']}"]
    if args.get("matched_data"):
        parts.append(f"--matched-data {args['matched_data']}")
    return " \\\n    ".join(parts)


def _output_state(out: Path, identity: str):
    """Reuse only a complete, checksummed result with the same experiment identity (P28 §11)."""
    results, sidecar = out / "results.json", out / "results.json.sha256"
    leftovers = sorted(path.name for path in out.glob("*.tmp")) if out.exists() else []
    if leftovers:
        raise ValueError(f"incomplete derived output ({leftovers}); use a new output directory")
    if not results.exists() and not sidecar.exists():
        return None
    if not results.exists() or not sidecar.exists() or sidecar.read_text().strip() != _file_hash(results):
        raise ValueError(f"{results} is incomplete or modified; use a new output directory")
    stored = json.loads(results.read_text())
    if stored.get("experiment_fingerprint") != identity:
        raise ValueError(f"{results} was produced by a different experiment identity; use a new output directory")
    return stored


def run_a5(config: A5Config, data, runs, out, *, matched_data=None, command_args=None, log=print) -> dict:
    started, clock = time.time(), time.perf_counter()
    data, runs, out = Path(data), Path(runs), Path(out)
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
    models_identity = {view: _sha256(runs / f"model_{view}.pt") for view in config.views if (runs / f"model_{view}.pt").exists()}
    implementation = _source_identity()
    experiment_fingerprint = fingerprint({
        "contract": CONTRACT, "plan_contract": PLAN_CONTRACT, "config": config.to_dict(), "data": identity,
        "matched": matched_identity, "request": source.request_fingerprint, "checkpoints": models_identity,
        "e4_sources": {name: implementation["files_sha256"][name] for name in E4_ADDED_FILES}})
    out.mkdir(parents=True, exist_ok=True)
    reused = _output_state(out, experiment_fingerprint)
    if reused is not None:
        log(f"reusing verified A5 result {experiment_fingerprint[:12]}")
        return reused
    loaded = load_frozen_views(runs, experiment, identity, sources, config.views, log)
    frozen = loaded["views"]
    budget = Budget(CAPS["max_replays"], CAPS["max_cancellations"])
    receiver = FrozenReceiver(source.cancellation, budget)
    records, parity, rows = [], [], []
    for group, label in scenes:
        stored = source.stored(group, label)
        corruption = corrupt_operator_plan(
            stored.original_plans(), perturbation=config.perturbation, scope=config.scope, scenario_id=group,
            allowed_intervention_context=stored.intervention_context() if config.perturbation == "authorize_intruder" else None)
        record = {"scenario_id": group, "label": label, **corruption.to_dict(), "flags": {}, "residual_recomputed": None}
        records.append(record)
        if not corruption.applied:
            rows.append({"stored": stored, "corruption": corruption, "conditions": None})
            continue
        replay = replay_scene(source, label, group, budget)
        parity.append({"scenario_id": group, "label": label, **check_parity(replay, stored)})
        conditions = build_conditions(replay, stored, corruption, receiver)
        record["flags"] = reporting_flags(replay, corruption)
        record["residual_recomputed"] = conditions["residual_recomputed"]
        rows.append({"stored": stored, "corruption": corruption, "conditions": conditions})
        del replay                                            # raw IQ is transient
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
            keep = [i for i, r in enumerate(rows) if r["conditions"] is not None]
            original = _take(original_all, keep)
            entry["paired_population"] = {"n_scenes": len(keep)}
            original_core = np.stack([r["stored"].mask[0] > CORE_DB for r in applicable])
            entry["conditions"], scored_outputs = {}, {}
            for condition in CONDITIONS:
                observations = [r["conditions"][condition] for r in applicable]
                outputs = original if condition == "original" else score_observed(
                    view, ObservedInputs.stack(observations), keys_app, config.stage)
                scored_outputs[condition] = outputs
                if condition != "original":
                    scored += len(observations)
                diagnostics = _residual_diagnostics(observations, original_core)
                entry["conditions"][condition] = _view_metrics(keys_app, outputs, original, diagnostics)
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
        "implementation": {"git_sha": implementation["revision"], "e4_source_files_sha256": {
            name: implementation["files_sha256"][name] for name in E4_ADDED_FILES}},
        "frozen_models": {name: (frozen[name].identity if name in frozen else {"available": False,
                          "reason": loaded["unavailable"].get(name)}) for name in config.views},
        "experiment_reference": {"runs_config": experiment.resolved(), "labels": list(LABELS)},
        "populations": populations, "scenes": records, "parity": parity,
        "parity_summary": {"n_scenes_checked": len(parity), "all_exact": all(p["exact"] for p in parity) if parity else None,
                           "max_abs_diff_db": max((max(p[k]["max_abs_diff_db"] for k in ("spec", "mask", "residual"))
                                                    for p in parity), default=None)},
        "views": views,
        "counts": {"physical_replays": budget.replays, "cancellation_evaluations": budget.cancellations,
                   "receiver_recomputations": receiver.calls, "scored_samples": scored,
                   "scenes_selected": len(rows), "scenes_applicable": len(applicable)},
        "label_policy": {"layers": ["original physical label", "original operator-relative target (plan_consistency)",
                                    "counterfactual operator-plan intervention", "frozen classifier output"],
                         "counterfactual_metric_name": "agreement_with_original_label (descriptive, not accuracy)",
                         "mask_only": "weaker control: stored residual, rebuilt masks; never receiver-consistent",
                         "co_dual_views": "co and dual views do not read the residual; MASK_ONLY and RECEIVER_CONSISTENT differ only through the replayed PSD"},
        "baselines": baseline if baseline is not None else {"status": "INPUTS_RECOMPUTED_NO_MODEL", "methods": None,
                                                             "note": "empty paired population"},
        "cost": {"elapsed_s": elapsed, "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss, "cpu_count": 0,
                 "device": "cpu", "python": platform.python_version(), "numpy": np.__version__, "torch": str(torch.__version__),
                 "started_unix": started},
        "reproduction_command": _reproduction_command(command_args or {"config": "<config>", "data": str(data), "runs": str(runs),
                                                                       "out": str(out), "matched_data": matched_data}),
        "limitations": ["bounded pilot: at most two scenario groups and two classes; no population-level inference",
                        "checkpoints are whatever the run directory supplies; the pilot ones are chance-level stand-ins",
                        "counterfactual outputs are descriptive agreement, not accuracy",
                        "simulator-only evidence; no field data"]}
    result["cost"]["cpu_count"] = os.cpu_count()
    _write_json(out / "results.json", result)
    (out / "results.json.sha256").write_text(_file_hash(out / "results.json") + "\n")
    (out / "results.md").write_text(report(result))
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
            "note": "co/dual views never read the residual; with an unchanged co descriptor the residual is identical by construction"}


def report(result: dict) -> str:
    cfg = result["configuration"]
    lines = [f"# B2 A5 plan corruption ({result['contract']}) — {cfg['perturbation']} / {cfg['scope']} / {cfg['stage']}", "",
             f"Evidence class **{result['evidence_class']}**; benchmark complete: **{result['benchmark_complete']}**. "
             f"Selected {result['populations']['selected']} scenes, applied {result['populations']['applied']}; "
             f"not applicable {result['populations']['not_applicable']}; blocked {result['populations']['blocked']}.",
             f"Replays {result['counts']['physical_replays']}, cancellations {result['counts']['cancellation_evaluations']}, "
             f"scored samples {result['counts']['scored_samples']}; parity all-exact: {result['parity_summary']['all_exact']}.", "",
             "Counterfactual columns are **agreement with the original label**, not accuracy. MASK_ONLY is the weaker control.", "",
             "| View | Condition | n | Agreement with original label | Prediction changed | Clean false alarm | Event detection |",
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
               command_args={"config": args.config, "data": args.data, "runs": args.runs, "out": args.out,
                             "matched_data": args.matched_data})
    except (ValueError, FileNotFoundError, TypeError) as error:
        parser.exit(2, f"error: {error}\n")


if __name__ == "__main__":
    main()

"""Known-class B2 learning slice on frozen roles with the five-channel model.

    python -m geoml.b2_experiment --config configs/b2_feat.json \
        --data data/b2-feat-pilot --out runs/b2-feat-pilot

Roles follow P18 §4 exactly: ``train`` fits weights and Mahalanobis statistics,
``val-select`` picks the checkpoint, ``val-calib`` (known classes only) sets the
MSP/energy/Mahalanobis acceptance thresholds and the clean alarm threshold, and
``test`` is evaluated once. Matched views (``co``, ``dual``, ``dual_residual``)
share data, budget and seeds. The optional independent ``plan_consistency``
head is trained and reported separately (P18 §7a).

This slice contains known classes only. Unknown families, benign CID overlays
and the matched ASI set are later stages; their metrics are reported as
``null`` with zero counts, never estimated from known data.
"""
from __future__ import annotations

import argparse
import json
import platform
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
import torch

from geosim.b2_dataset import b2_fingerprint, load_b2_split, read_b2_manifest
from geosim.b2_protocol import BASE_PROTOCOL, FEATURE_PROTOCOL, LABELS, PLAN_CONSISTENCY, role_for_group

from .artifacts import fingerprint
from .calibration import RejectionCalibration, calibrate_scores
from .data import VIEW_CHANNELS
from .experiment import _sha256, _source_identity, _write_json
from .mahalanobis import MahalanobisScorer, fit_mahalanobis
from .metrics import cluster_ci, confusion, expected_calibration_error, macro_f1, threshold_at_pfa
from .openset import unknown_scores
from .train import TrainConfig, fit, infer, load, save

ROLES = ("train", "val-select", "val-calib", "test")
METHODS = ("msp", "energy", "mahalanobis")
VIEWS = ("co", "dual", "dual_residual")


@dataclass(frozen=True)
class B2ExperimentConfig:
    protocol: str = FEATURE_PROTOCOL
    views: tuple[str, ...] = VIEWS
    plan_consistency: bool = True
    methods: tuple[str, ...] = METHODS
    target_acceptance: float = 0.95
    pfa: float = 0.05
    mahalanobis_regularization: float = 0.1
    training: dict = field(default_factory=lambda: {"epochs": 3, "batch": 8, "width": 8, "seed": 0,
                                                    "center_loss_weight": 0.005})

    def __post_init__(self):
        if self.protocol not in (BASE_PROTOCOL, FEATURE_PROTOCOL):
            raise ValueError(f"protocol must be {BASE_PROTOCOL} or {FEATURE_PROTOCOL}")
        if (not isinstance(self.views, (list, tuple)) or not self.views
                or any(view not in VIEWS for view in self.views) or len(set(self.views)) != len(self.views)):
            raise ValueError(f"views must be unique choices from {VIEWS}")
        if self.protocol == BASE_PROTOCOL and "dual_residual" in self.views:
            raise ValueError("the dual_residual view requires the B2-feat/1 stage with a stored residual")
        if (not isinstance(self.methods, (list, tuple)) or not self.methods
                or any(method not in METHODS for method in self.methods) or len(set(self.methods)) != len(self.methods)):
            raise ValueError(f"methods must be unique choices from {METHODS}")
        for name in ("target_acceptance", "pfa"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 < value < 1:
                raise ValueError(f"{name} must be between 0 and 1")
        if (isinstance(self.mahalanobis_regularization, bool) or not isinstance(self.mahalanobis_regularization, (int, float))
                or not 0 < self.mahalanobis_regularization <= 1):
            raise ValueError("mahalanobis_regularization must be in (0, 1]")
        if not isinstance(self.plan_consistency, bool):
            raise ValueError("plan_consistency must be a boolean")
        if not isinstance(self.training, dict) or set(self.training) & {"labels", "input_mode", "plan_consistency"}:
            raise ValueError("labels, input_mode and plan_consistency are set by the experiment, not the training block")
        if "center_loss_weight" not in self.training:
            raise ValueError("center_loss_weight must be frozen explicitly in the training configuration before training")
        object.__setattr__(self, "views", tuple(self.views))
        object.__setattr__(self, "methods", tuple(self.methods))
        for view in self.views:
            self.train_config(view)

    def train_config(self, view: str) -> TrainConfig:
        return TrainConfig(labels=LABELS, input_mode=view, plan_consistency=self.plan_consistency, **self.training)

    def resolved(self) -> dict:
        training = asdict(self.train_config(self.views[0]))
        for name in ("labels", "input_mode", "plan_consistency"):
            training.pop(name)
        return {**asdict(self), "training": training}

    @classmethod
    def from_file(cls, path):
        try:
            raw = json.loads(Path(path).read_text())
            if not isinstance(raw, dict):
                raise ValueError("experiment configuration must be a JSON object")
            return cls(**raw)
        except TypeError as error:
            raise ValueError(f"invalid experiment configuration: {error}") from error


def _check_roles(parts):
    for role, part in parts.items():
        seeds = np.unique(part["seed"])
        if any(role_for_group(int(seed)) != role for seed in seeds):
            raise ValueError(f"{role} contains scenario groups outside its frozen B2/1 range")
        if set(part["label"].tolist()) != set(range(len(LABELS))):
            raise ValueError(f"{role} must include every known label")
    names = list(parts)
    for i, left in enumerate(names):
        for right in names[i + 1:]:
            if np.intersect1d(parts[left]["seed"], parts[right]["seed"]).size:
                raise ValueError(f"scenario group leakage between {left} and {right}")


def _summary(parts):
    return {role: {"n_samples": int(len(part["label"])), "scenario_ids": [int(s) for s in np.unique(part["seed"])],
                   "per_label": {label: int(np.sum(part["label"] == index)) for index, label in enumerate(LABELS)},
                   "n_planned_carrier_missing": int(np.sum(part["plan_consistency"] == 1))}
            for role, part in parts.items()}


def _rate(values, groups):
    values = np.asarray(values, dtype=float)
    if not len(values):
        return {"mean": None, "ci95": None, "n_samples": 0, "n_scenarios": 0}
    ci = list(cluster_ci(values, groups)) if len(np.unique(groups)) > 1 else None
    return {"mean": float(values.mean()), "ci95": ci, "n_samples": int(len(values)),
            "n_scenarios": int(len(np.unique(groups)))}


def _softmax(logits):
    shifted = logits.astype(np.float64) - logits.max(axis=1, keepdims=True)
    exponent = np.exp(shifted)
    return exponent / exponent.sum(axis=1, keepdims=True)


def _plan_metrics(plan_logits, targets, groups):
    if plan_logits is None:
        return None
    predicted = plan_logits[:, 0] > 0
    actual = targets == 1
    positives = int(actual.sum())
    both_classes = 0 < positives < len(targets)
    # A constant head scores 100 % when one class is absent; report null instead (AGENTS.md).
    accuracy = _rate(predicted == actual, groups) if both_classes else {
        "mean": None, "ci95": None, "n_samples": int(len(targets)), "n_scenarios": int(len(np.unique(groups))),
        "note": "undefined: only one plan-consistency class present"}
    return {"positive_class": PLAN_CONSISTENCY[1], "decision_rule": "auxiliary logit > 0",
            "accuracy": accuracy,
            "recall": None if not positives else float(np.mean(predicted[actual])),
            "precision": None if not predicted.any() else float(np.mean(actual[predicted])),
            "n_positive": positives, "n_predicted_positive": int(predicted.sum()), "n_samples": int(len(targets))}


def _rejection(method, calib_scores, test_scores, labels, predictions, groups, provenance, config):
    calibration = calibrate_scores(calib_scores, method, config.target_acceptance, provenance=provenance)
    accepted = calibration.accept(test_scores)
    return calibration, {
        "calibration": calibration.to_dict(),
        "known_acceptance": _rate(accepted, groups),
        "accepted_known_accuracy": _rate((predictions == labels)[accepted], groups[accepted]),
        "per_class_acceptance": {label: _rate(accepted[labels == index], groups[labels == index])
                                 for index, label in enumerate(LABELS)},
        "unknown_rejection": None, "n_unknown": 0,
        "note": "no unknown or benign test-only families exist in this known-only stage"}


def run_b2_experiment(config: B2ExperimentConfig, data, out, *, reuse=False, device="cpu", log=print):
    data, out = Path(data), Path(out)
    manifest = read_b2_manifest(data)
    if manifest["protocol"] != config.protocol or list(manifest["labels"]) != list(LABELS):
        raise ValueError(f"dataset protocol {manifest['protocol']!r} does not match the experiment {config.protocol!r}")
    if manifest["benchmark_complete"] is not False:
        raise ValueError("B2 artifacts must declare benchmark_complete=false in this stage")
    identity = b2_fingerprint(data)
    parts = {role: load_b2_split(data, role) for role in ROLES}
    if config.protocol == FEATURE_PROTOCOL and any("residual" not in part for part in parts.values()):
        raise ValueError("B2-feat/1 splits must carry the stored residual")
    _check_roles(parts)
    summary = _summary(parts)
    source = _source_identity()
    provenance = {"protocol": config.protocol, "data_fingerprint": identity,
                  "roles": {role: summary[role]["scenario_ids"] for role in ROLES},
                  "source_files_sha256": source["files_sha256"]}
    experiment_identity = fingerprint({"config": config.resolved(), "data": identity,
                                       "source_files_sha256": source["files_sha256"]})
    out.mkdir(parents=True, exist_ok=True)
    methods, decisions = {}, {}
    test = parts["test"]
    labels, groups = test["label"].astype(np.int64), test["seed"]
    clean = labels == 0
    for view in config.views:
        cfg = config.train_config(view)
        path = out / f"model_{view}.pt"
        if path.exists():
            if not reuse:
                raise ValueError(f"{path} already exists; use --reuse or a new output directory")
            fitted = load(path, device=device, expected_config=cfg, expected_provenance=provenance)
            log(f"reusing compatible {view} checkpoint")
        else:
            log(f"training {view} model ({VIEW_CHANNELS[view]} channels)")
            fitted = fit(parts["train"], parts["val-select"], cfg, device=device, log=log)
            fitted.update(provenance=provenance, source_revision=source["revision"])
            save(fitted, path)
            fitted = load(path, device=device, expected_config=cfg, expected_provenance=provenance)
        checkpoint_sha = _sha256(path)
        train_out = infer(fitted, parts["train"])
        calib_out = infer(fitted, parts["val-calib"])
        test_out = infer(fitted, test)
        scorer_path = out / f"mahalanobis_{view}.npz"
        scorer_provenance = fingerprint({"checkpoint_sha256": checkpoint_sha, "data": identity,
                                         "groups": summary["train"]["scenario_ids"],
                                         "regularization": config.mahalanobis_regularization})
        if scorer_path.exists():
            scorer = MahalanobisScorer.load(scorer_path)
            if scorer.provenance != scorer_provenance:
                raise ValueError(f"{scorer_path} is not bound to this checkpoint and training data")
        else:
            scorer = fit_mahalanobis(train_out["embedding"], parts["train"]["label"].astype(np.int64), len(LABELS),
                                     config.mahalanobis_regularization, provenance=scorer_provenance)
            scorer.save(scorer_path)
        probabilities = _softmax(test_out["logits"])
        predictions = test_out["logits"].argmax(axis=1)
        event_probability = 1.0 - probabilities[:, 0]
        calib_probability = 1.0 - _softmax(calib_out["logits"])[:, 0]
        clean_calibration = parts["val-calib"]["label"] == 0
        alarm_threshold = threshold_at_pfa(calib_probability[clean_calibration], config.pfa)
        alarm = event_probability > alarm_threshold
        rejection = {}
        for method in config.methods:
            if method == "mahalanobis":
                calib_scores, test_scores = scorer.score(calib_out["embedding"]), scorer.score(test_out["embedding"])
            else:
                calib_scores, test_scores = unknown_scores(calib_out["logits"], method), unknown_scores(test_out["logits"], method)
            rejection_provenance = fingerprint({"checkpoint_sha256": checkpoint_sha, "data": identity, "method": method,
                                                "groups": summary["val-calib"]["scenario_ids"],
                                                "target_acceptance": config.target_acceptance})
            calibration, metrics = _rejection(method, calib_scores, test_scores, labels, predictions, groups,
                                              rejection_provenance, config)
            calibration_path = out / f"rejection_{view}_{method}.json"
            if calibration_path.exists():
                if RejectionCalibration.load(calibration_path) != calibration:
                    raise ValueError(f"{calibration_path} is incompatible with this checkpoint/calibration data")
            else:
                calibration.save(calibration_path)
            rejection[method] = metrics
            decisions.setdefault(view, {})[method] = test_scores
        methods[view] = {"input_channels": VIEW_CHANNELS[view],
                         "accuracy": _rate(predictions == labels, groups),
                         "macro_f1": macro_f1(labels, predictions, len(LABELS)),
                         "confusion": confusion(labels, predictions, len(LABELS)).tolist(),
                         "per_class_recall": {label: _rate((predictions == labels)[labels == index], groups[labels == index])
                                              for index, label in enumerate(LABELS)},
                         "ece": expected_calibration_error(probabilities, labels, 15),
                         "clean_false_alarm": _rate(alarm[clean], groups[clean]),
                         "event_detection": _rate(alarm[~clean], groups[~clean]),
                         "alarm": {"score": "one_minus_softmax_clean", "threshold": alarm_threshold,
                                   "target_clean_pfa": config.pfa, "n_clean_calibration": int(clean_calibration.sum())},
                         "plan_consistency": _plan_metrics(test_out["plan_logits"], test["plan_consistency"], groups),
                         "rejection": rejection, "mahalanobis": scorer.to_dict(),
                         "open_set": {"unknown_auroc": None, "unknown_ap": None, "oscr": None, "fpr_at_95_tpr": None,
                                      "n_unknown": 0, "note": "unknown families are a later B2 stage"},
                         "checkpoint_sha256": checkpoint_sha, "training_source_revision": fitted.get("source_revision"),
                         "n_parameters": fitted["n_parameters"], "history": fitted["history"]}
        decisions[view]["prediction"] = predictions
        decisions[view]["event_probability"] = event_probability
        decisions[view]["alarm"] = alarm
        decisions[view]["plan_logit"] = None if test_out["plan_logits"] is None else test_out["plan_logits"][:, 0]
    result = {"protocol": config.protocol, "parent_protocol": manifest["parent_protocol"], "benchmark_complete": False,
              "labels": list(LABELS), "config": config.resolved(), "experiment_fingerprint": experiment_identity,
              "data_fingerprint": identity, "source": source, "partitions": summary, "methods": methods,
              "generation": manifest["config"], "cancellation": manifest.get("cancellation"),
              "receiver_calibration": manifest["calibration"],
              "runtime": {"python": platform.python_version(), "numpy": np.__version__,
                          "torch": str(torch.__version__), "device": device},
              "scope": "Known-class learning slice on frozen B2/1 roles; not the complete open-set benchmark."}
    rows = []
    for index, (label, group, target) in enumerate(zip(labels, groups, test["plan_consistency"])):
        rows.append({"scenario_id": int(group), "true_label": LABELS[int(label)],
                     "plan_consistency": PLAN_CONSISTENCY[int(target)],
                     "views": {view: {"prediction": LABELS[int(values["prediction"][index])],
                                       "event_probability": float(values["event_probability"][index]),
                                       "alarm": bool(values["alarm"][index]),
                                       "plan_logit": None if values["plan_logit"] is None else float(values["plan_logit"][index]),
                                       "unknown_scores": {method: float(values[method][index]) for method in config.methods}}
                               for view, values in decisions.items()}})
    _write_json(out / "config.json", config.resolved())
    _write_json(out / "results.json", result)
    _write_json(out / "predictions.json", rows)
    (out / "results.md").write_text(report(result))
    log(f"wrote {out / 'results.md'}")
    return result


def _percent(rate):
    return "n/a" if rate is None or rate.get("mean") is None else f"{100 * rate['mean']:.1f}% (n={rate['n_samples']})"


def _plan_cell(plan):
    if plan is None:
        return "n/a"
    if plan["accuracy"]["mean"] is None:
        return f"n/a (positives n={plan['n_positive']} of {plan['n_samples']}; undefined)"
    return f"{_percent(plan['accuracy'])} (positives n={plan['n_positive']})"


def report(result):
    lines = [f"# B2 known-class learning slice ({result['protocol']})", "",
             f"Parent protocol `{result['parent_protocol']}`; eight known labels; benchmark complete: **{result['benchmark_complete']}**.", "",
             "Roles are the frozen P18 §4 groups: train fits weights and Mahalanobis statistics, val-select picks the",
             "checkpoint, val-calib (known only) fits acceptance and alarm thresholds, test is evaluated once.",
             "No unknown families, CID overlays or matched ASI sets exist in this stage; their metrics are null.", "",
             "| View | Channels | Accuracy | Macro-F1 | ECE | Clean false alarm | Event detection | Plan-consistency accuracy |",
             "|---|---|---|---|---|---|---|---|"]
    for view, values in result["methods"].items():
        plan = values["plan_consistency"]
        lines.append(f"| {view} | {values['input_channels']} | {_percent(values['accuracy'])} | {values['macro_f1']:.3f} | "
                     f"{values['ece']['ece']:.3f} | {_percent(values['clean_false_alarm'])} | {_percent(values['event_detection'])} | "
                     f"{_plan_cell(plan)} |")
    lines += ["", "| View | Method | Known acceptance at calibrated threshold | Accuracy on accepted | Unknown rejection |",
              "|---|---|---|---|---|"]
    for view, values in result["methods"].items():
        for method, metrics in values["rejection"].items():
            lines.append(f"| {view} | {method} | {_percent(metrics['known_acceptance'])} | "
                         f"{_percent(metrics['accepted_known_accuracy'])} | null (n_unknown=0) |")
    lines += ["", "Positive class of the alarm is any non-clean label; its threshold comes from clean val-calib scenes only.",
              "Plan-consistency positive class is `planned_carrier_missing` (auxiliary logit > 0); it does not affect checkpoint selection.",
              "Intervals in JSON resample scenario groups with fixed weights and thresholds; training-seed uncertainty is separate.",
              "A pilot with few scenario groups validates execution and data flow, not recognition quality.", "",
              "## Partitions", "", "| Role | Samples | Scenario groups | Planned carrier missing |", "|---|---|---|---|"]
    for role, values in result["partitions"].items():
        lines.append(f"| {role} | {values['n_samples']} | {len(values['scenario_ids'])} | {values['n_planned_carrier_missing']} |")
    lines += ["", f"Experiment fingerprint: `{result['experiment_fingerprint']}`; data fingerprint: `{result['data_fingerprint']}`.", ""]
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", required=True)
    parser.add_argument("--data", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--reuse", action="store_true")
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    args = parser.parse_args(argv)
    try:
        run_b2_experiment(B2ExperimentConfig.from_file(args.config), args.data, args.out,
                          reuse=args.reuse, device=args.device)
    except (ValueError, FileNotFoundError) as error:
        parser.exit(2, f"error: {error}\n")


if __name__ == "__main__":
    main()

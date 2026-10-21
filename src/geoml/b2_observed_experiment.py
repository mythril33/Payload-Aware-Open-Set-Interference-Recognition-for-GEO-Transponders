"""Matched four/five-channel, two-output B2 known-class development run.

python -m geoml.b2_observed_experiment --config configs/b2_observed_experiment.json \
    --data data/b2-features-pilot --out runs/b2-observed-pilot

This run does not evaluate final unknown families or establish cancellation
quality from classification scores. Instrument/receiver and model identities
are bound to immutable feature artifacts and actual source file hashes.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, field
from pathlib import Path
import platform

import numpy as np
import torch

from geosim.b2_features import PROTOCOL as FEATURE_PROTOCOL
from geosim.b2_features import feature_fingerprint, iter_feature_shards, read_feature_manifest
from geosim.b2_protocol import BASE_ROLES, LABELS, PROTOCOL
from geosim.event_dataset import _strict_json

from .artifacts import fingerprint
from .b2_train import B2TrainConfig, fit, infer, load, save
from .experiment import _sha256, _source_identity, _write_json
from .metrics import cluster_ci, confusion, expected_calibration_error, macro_f1, threshold_at_pfa

EXPERIMENT_PROTOCOL = "B2-observed-dev/1"


@dataclass(frozen=True)
class B2ExperimentConfig:
    protocol: str = EXPERIMENT_PROTOCOL
    pfa: float = 0.05
    views: tuple[str, ...] = ("dual", "b2")
    training: dict = field(default_factory=lambda: {
        "epochs": 3, "batch": 8, "width": 8, "time_pool": 2, "seed": 0,
        "center_weight": 0.01, "consistency_weight": 1.0})

    def __post_init__(self):
        if self.protocol != EXPERIMENT_PROTOCOL:
            raise ValueError(f"supported experiment protocol is {EXPERIMENT_PROTOCOL}")
        if isinstance(self.pfa, bool) or not np.isfinite(self.pfa) or not 0 < self.pfa < 1:
            raise ValueError("pfa must be finite and between zero and one")
        if (not isinstance(self.views, (tuple, list)) or not self.views
                or any(view not in ("co", "dual", "b2") for view in self.views)
                or len(set(self.views)) != len(self.views)):
            raise ValueError("views must be unique choices from co, dual and b2")
        object.__setattr__(self, "views", tuple(self.views))
        if not isinstance(self.training, dict) or set(self.training) & {"view", "labels"}:
            raise ValueError("training must be an object; view and labels are derived")
        for view in self.views:
            self.train_config(view)

    def train_config(self, view):
        return B2TrainConfig(view=view, labels=LABELS, **self.training)

    def resolved(self):
        training = asdict(self.train_config(self.views[0]))
        for key in ("labels", "view"):
            training.pop(key)
        return {**asdict(self), "training": training}

    @classmethod
    def from_file(cls, path):
        raw = _strict_json(Path(path).read_text())
        if not isinstance(raw, dict):
            raise ValueError("B2 experiment configuration must be a JSON object")
        try:
            return cls(**raw)
        except TypeError as error:
            raise ValueError(f"invalid B2 experiment configuration: {error}") from error


def _partitions(data, manifest):
    if set(manifest["roles"]) != set(BASE_ROLES):
        raise ValueError("the experiment requires train, val-select, val-calib and test roles")
    summary, seen = {}, set()
    for role in BASE_ROLES:
        groups = set(manifest["roles"][role]["scenario_seeds"])
        if not groups or groups & seen:
            raise ValueError("empty role or scenario group leakage")
        seen.update(groups)
        counts = [0, 0]
        for shard in iter_feature_shards(data, role):
            counts[0] += int(np.sum(shard["plan_consistency"] == 0))
            counts[1] += int(np.sum(shard["plan_consistency"] == 1))
        summary[role] = {"scenario_ids": sorted(groups), "n_scenarios": len(groups),
                         "n_samples": manifest["roles"][role]["n_samples"],
                         "per_label": manifest["roles"][role]["per_label"],
                         "plan_consistency_counts": {"consistent": counts[0], "planned_carrier_missing": counts[1]}}
    return summary


def _probabilities(logits, n_classes):
    values = np.asarray(logits)
    if (values.ndim != 2 or not len(values) or values.shape[1] != n_classes
            or values.dtype.kind not in "iuf" or not np.isfinite(values).all()):
        raise ValueError(f"expected finite nonempty [N,{n_classes}] logits")
    values = values.astype(np.float64) - values.max(axis=1, keepdims=True)
    exp = np.exp(values)
    return exp / exp.sum(axis=1, keepdims=True)


def _rate(values, groups):
    values, groups = np.asarray(values, dtype=float), np.asarray(groups)
    n_groups = len(np.unique(groups))
    return {"mean": float(values.mean()) if len(values) else None,
            "ci95": list(cluster_ci(values, groups)) if n_groups >= 2 else None,
            "n_samples": len(values), "n_scenarios": n_groups}


def _evaluate(output, threshold):
    labels, groups, auxiliary = output["label"], output["seed"], output["plan_consistency"]
    probabilities = _probabilities(output["logits"], len(LABELS))
    auxiliary_probabilities = _probabilities(output["consistency_logits"], 2)
    predictions = probabilities.argmax(1)
    consistency = auxiliary_probabilities.argmax(1)
    # Summation avoids cancellation for highly confident clean predictions.
    score = probabilities[:, 1:].sum(1)
    alarm, clean, missing = score > threshold, labels == 0, auxiliary == 1
    metrics = {"classification": {"accuracy": _rate(predictions == labels, groups),
                                  "macro_f1": macro_f1(labels, predictions, len(LABELS)),
                                  "confusion": confusion(labels, predictions, len(LABELS)).tolist(),
                                  "calibration": expected_calibration_error(probabilities, labels)},
               "plan_consistency": {"accuracy": _rate(consistency == auxiliary, groups),
                                    "macro_f1_present_classes": macro_f1(auxiliary, consistency, 2),
                                    "confusion": confusion(auxiliary, consistency, 2).tolist(),
                                    "missing_recall": _rate(consistency[missing] == 1, groups[missing]),
                                    "false_missing_alarm": _rate(consistency[~missing] == 1, groups[~missing])},
               "clean_false_alarm": _rate(alarm[clean], groups[clean]),
               "event_detection": {name: _rate(alarm[labels == index], groups[labels == index])
                                   for index, name in enumerate(LABELS) if index > 0}}
    rows = [{"scenario_id": int(group), "true_label": LABELS[int(label)],
             "prediction": LABELS[int(pred)], "true_plan_consistency": int(aux),
             "plan_consistency_prediction": int(aux_pred), "missing_probability": float(aux_prob),
             "event_probability": float(event_score), "event_alarm": bool(event_alarm)}
            for group, label, pred, aux, aux_pred, aux_prob, event_score, event_alarm in zip(
                groups, labels, predictions, auxiliary, consistency, auxiliary_probabilities[:, 1], score, alarm)]
    return metrics, rows


def run_b2_experiment(config: B2ExperimentConfig, data, out, *, reuse=False, device="cpu", log=print):
    data, out = Path(data), Path(out)
    manifest = read_feature_manifest(data)
    if manifest["protocol"] != FEATURE_PROTOCOL or tuple(manifest["labels"]) != LABELS:
        raise ValueError("incompatible observed B2 feature artifact")
    summary = _partitions(data, manifest)
    identity, source = feature_fingerprint(data), _source_identity()
    provenance = {"protocol": EXPERIMENT_PROTOCOL, "parent_protocol": PROTOCOL,
                  "data_fingerprint": identity, "source_files_sha256": source["files_sha256"],
                  "training_groups": summary["train"]["scenario_ids"],
                  "selection_groups": summary["val-select"]["scenario_ids"]}
    experiment_id = fingerprint({"config": config.resolved(), "data": identity,
                                 "source_files_sha256": source["files_sha256"]})
    out.mkdir(parents=True, exist_ok=True)
    methods, predictions = {}, {}
    for view in config.views:
        train_config = config.train_config(view)
        path = out / f"model_{view}.pt"
        if path.exists():
            if not reuse:
                raise ValueError(f"{path} already exists; use --reuse or a fresh directory")
            fitted = load(path, device=device, expected_config=train_config, expected_provenance=provenance)
            log(f"reusing compatible {view} model")
        else:
            log(f"training {view} two-output model")
            fitted = fit((data, "train"), (data, "val-select"), train_config,
                         device=device, provenance=provenance, log=log)
            fitted["source_revision"] = source["revision"]
            save(fitted, path)
            fitted = load(path, device=device, expected_config=train_config, expected_provenance=provenance)
        calibration = infer(fitted, (data, "val-calib"))
        clean = calibration["label"] == 0
        clean_scores = _probabilities(calibration["logits"], len(LABELS))[clean, 1:].sum(1)
        if not len(clean_scores):
            raise ValueError("event-alarm calibration requires clean calibration observations")
        threshold = threshold_at_pfa(clean_scores, config.pfa)
        detector = {"score": "sum_nonclean_softmax", "threshold": threshold,
                    "target_clean_pfa": config.pfa, "n_clean_calibration": len(clean_scores),
                    "provenance": fingerprint({"checkpoint_sha256": _sha256(path), "data": identity,
                                                "groups": summary["val-calib"]["scenario_ids"], "pfa": config.pfa})}
        detector_path = out / f"detector_{view}.json"
        if detector_path.exists() and _strict_json(detector_path.read_text()) != detector:
            raise ValueError("stored event detector differs from the model/calibration configuration")
        _write_json(detector_path, detector)
        metrics, rows = _evaluate(infer(fitted, (data, "test")), threshold)
        methods[view] = {**metrics, "input_channels": {"co": 2, "dual": 4, "b2": 5}[view],
                         "n_parameters": fitted["n_parameters"], "history": fitted["history"],
                         "checkpoint_sha256": _sha256(path), "training_source_revision": fitted.get("source_revision"),
                         "event_detector": detector}
        predictions[view] = rows
    result = {"protocol": EXPERIMENT_PROTOCOL, "parent_protocol": PROTOCOL, "benchmark_complete": False,
              "labels": list(LABELS), "config": config.resolved(), "partitions": summary, "methods": methods,
              "data_fingerprint": identity, "experiment_fingerprint": experiment_id, "source": source,
              "feature_stage": {key: manifest[key] for key in ("protocol", "config", "calibration", "cancellation")},
              "n_final_unknown_test_samples": 0,
              "runtime": {"python": platform.python_version(), "numpy": np.__version__,
                          "torch": str(torch.__version__), "device": device}}
    _write_json(out / "config.json", config.resolved())
    _write_json(out / "results.json", result)
    _write_json(out / "predictions.json", predictions)
    (out / "results.md").write_text(report(result))
    return result


def report(result):
    lines = ["# Observed receiver and two-output B2 development", "",
             f"Protocol `{result['protocol']}`; parent `{result['parent_protocol']}`.", "",
             "Known classes only. Final unknown/CID/matched tests and multi-seed benchmark results remain outstanding.",
             "The receiver uses observed IQ plus declared operator frequency/rate/roll-off/modulation information.",
             "No true symbols, powers, timing, active state or event labels enter cancellation.", "",
             "| View | Channels | Primary accuracy | Primary macro-F1 | Consistency accuracy | Missing recall | Clean false alarm |",
             "|---|---|---|---|---|---|---|"]
    for view, method in result["methods"].items():
        recall = method["plan_consistency"]["missing_recall"]
        missing_text = f"{100 * recall['mean']:.1f}%" if recall["n_samples"] else "not measured (n=0)"
        lines.append(f"| {view} | {method['input_channels']} | {100 * method['classification']['accuracy']['mean']:.1f}% | "
                     f"{method['classification']['macro_f1']:.3f} | {100 * method['plan_consistency']['accuracy']['mean']:.1f}% | "
                     f"{missing_text} | {100 * method['clean_false_alarm']['mean']:.1f}% |")
    lines += ["", "Model selection uses val-select primary macro-F1. Clean val-calib samples alone set the event threshold.",
              "Consistency uses argmax over its independent two-state head. Missing recall is null when there are no positive targets.",
              "Scenario-bootstrap intervals are null with fewer than two test groups; training-seed uncertainty is not estimated here.",
              "Small known-class runs check the connection, not a recognition advantage or unknown-rejection quality.",
              "Model-mask jitter leaves stored residuals unchanged; full operator-plan-error experiments require recomputed receiver features.", "",
              "| Role | Groups | Samples | Missing targets |", "|---|---|---|---|"]
    for role, part in result["partitions"].items():
        lines.append(f"| {role} | {part['n_scenarios']} | {part['n_samples']} | {part['plan_consistency_counts']['planned_carrier_missing']} |")
    lines += ["", f"Experiment fingerprint: `{result['experiment_fingerprint']}`.", ""]
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
    except (ValueError, OSError) as error:
        parser.exit(2, f"error: {error}\n")


if __name__ == "__main__":
    main()

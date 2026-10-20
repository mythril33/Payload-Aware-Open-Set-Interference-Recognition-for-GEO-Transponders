"""Matched co-only and dual-polarization development experiments.

    python -m geoml.dual_experiment --config configs/dual_polarization.json \
        --data data/dual-pilot --out runs/dual-pilot

D1-dev/1 and E1-dev/1 are controlled tasks, not the final open-set benchmark.
Receiver calibration is estimated from independent instrument pilots during
generation. Clean validation groups alone set the event alarm threshold.
"""
from __future__ import annotations

import argparse
import json
import platform
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
import torch

from geosim.dual_dataset import LABELS, PROTOCOL, dual_fingerprint, load_dual_split, read_dual_manifest

from .artifacts import fingerprint
from .experiment import _sha256, _source_identity, _write_json
from .metrics import cluster_ci, confusion, macro_f1, threshold_at_pfa
from .train import TrainConfig, fit, infer, load, save

EVENT_PROTOCOL = "E1-dev/1"


def _dataset_api(protocol):
    if protocol == PROTOCOL:
        return LABELS, read_dual_manifest, dual_fingerprint, load_dual_split
    from geosim.event_dataset import LABELS as event_labels, read_event_manifest, event_fingerprint, load_event_split
    return event_labels, read_event_manifest, event_fingerprint, load_event_split


@dataclass(frozen=True)
class DualExperimentConfig:
    protocol: str = PROTOCOL
    calibration_fraction: float = 0.5
    split_seed: int = 0
    pfa: float = 0.05
    views: tuple[str, ...] = ("co", "dual")
    training: dict = field(default_factory=lambda: {"epochs": 3, "batch": 8, "width": 8, "seed": 0})

    def __post_init__(self):
        if self.protocol not in (PROTOCOL, EVENT_PROTOCOL):
            raise ValueError(f"supported dual-polarization protocols are {PROTOCOL} and {EVENT_PROTOCOL}")
        if isinstance(self.calibration_fraction, bool) or not 0 < self.calibration_fraction < 1:
            raise ValueError("calibration_fraction must be between 0 and 1")
        if isinstance(self.split_seed, bool) or not isinstance(self.split_seed, int) or self.split_seed < 0:
            raise ValueError("split_seed must be a nonnegative integer")
        if isinstance(self.pfa, bool) or not 0 < self.pfa < 1:
            raise ValueError("pfa must be between 0 and 1")
        if (not isinstance(self.views, (list, tuple)) or not self.views
                or any(view not in ("co", "dual") for view in self.views) or len(set(self.views)) != len(self.views)):
            raise ValueError("views must be unique choices from co and dual")
        object.__setattr__(self, "views", tuple(self.views))
        if not isinstance(self.training, dict) or set(self.training) & {"labels", "input_mode"}:
            raise ValueError("labels and input_mode are derived from the dataset and selected view")
        for view in self.views:
            self.train_config(view)

    def train_config(self, view: str) -> TrainConfig:
        return TrainConfig(labels=self.labels, input_mode=view, **self.training)

    @property
    def labels(self):
        return _dataset_api(self.protocol)[0]

    def resolved(self) -> dict:
        training = asdict(self.train_config(self.views[0]))
        for name in ("labels", "input_mode"):
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


def _subset(data, selected):
    return {key: data[key][selected] for key in ("spec", "mask", "label", "seed")} | {
        "meta": [meta for meta, keep in zip(data["meta"], selected) if keep]}


def _partitions(data, config):
    groups = {role: np.unique(value["seed"]) for role, value in data.items()}
    for left, right in (("train", "validation"), ("train", "test"), ("validation", "test")):
        if np.intersect1d(groups[left], groups[right]).size:
            raise ValueError(f"scenario group leakage between {left} and {right}")
    if len(groups["validation"]) < 2:
        raise ValueError("at least two validation scenario groups are required")
    ordered = np.random.default_rng(config.split_seed).permutation(groups["validation"])
    n = max(1, min(len(ordered) - 1, int(np.ceil(len(ordered) * config.calibration_fraction))))
    selected = np.isin(data["validation"]["seed"], ordered[:n])
    parts = {"train": data["train"], "validation": _subset(data["validation"], ~selected),
             "calibration": _subset(data["validation"], selected), "test": data["test"]}
    for role, value in parts.items():
        if set(value["label"].tolist()) != set(range(len(config.labels))):
            raise ValueError(f"{role} must include every label: {', '.join(config.labels)}")
    return parts


def _summary(parts, labels=LABELS):
    return {role: {"n_samples": len(value["label"]), "scenario_ids": [int(seed) for seed in np.unique(value["seed"])],
                   "per_label": {label: int(np.sum(value["label"] == index)) for index, label in enumerate(labels)}}
            for role, value in parts.items()}


def _rate(values, groups):
    return {"mean": float(np.mean(values)), "ci95": list(cluster_ci(values.astype(float), groups)),
            "n_samples": len(values), "n_scenarios": len(np.unique(groups))}


def _cross_probability(logits):
    return _event_probability(logits, 2)


def _event_probability(logits, n_classes):
    logits = np.asarray(logits)
    if (logits.ndim != 2 or logits.shape[1] != n_classes or not len(logits)
            or logits.dtype.kind not in "iuf" or not np.isfinite(logits).all()):
        raise ValueError(f"event detector requires finite [N,{n_classes}] logits")
    shifted = logits.astype(np.float64) - logits.max(axis=1, keepdims=True)
    exponent = np.exp(shifted)
    return exponent[:, 1:].sum(axis=1) / exponent.sum(axis=1)


def run_dual_experiment(config: DualExperimentConfig, data, out, *, reuse=False, device="cpu", log=print):
    data, out = Path(data), Path(out)
    label_names, read_manifest, data_fingerprint, load_split = _dataset_api(config.protocol)
    manifest = read_manifest(data)
    if manifest["protocol"] != config.protocol or tuple(manifest["labels"]) != label_names:
        raise ValueError("incompatible dual-polarization dataset")
    identity = data_fingerprint(data)
    sources = {role: load_split(data, role) for role in ("train", "validation", "test")}
    parts = _partitions(sources, config)
    summary = _summary(parts, label_names)
    source = _source_identity()
    provenance = {"protocol": config.protocol, "data_fingerprint": identity,
                  "validation_groups": summary["validation"]["scenario_ids"],
                  "source_files_sha256": source["files_sha256"]}
    experiment_identity = fingerprint({"config": config.resolved(), "data": identity,
                                       "source_files_sha256": source["files_sha256"]})
    out.mkdir(parents=True, exist_ok=True)
    methods, decisions = {}, {}
    for view in config.views:
        cfg = config.train_config(view)
        path = out / f"model_{view}.pt"
        if path.exists():
            if not reuse:
                raise ValueError(f"{path} already exists; use --reuse or a new output directory")
            fitted = load(path, device=device, expected_config=cfg, expected_provenance=provenance)
            log(f"reusing compatible {view} checkpoint")
        else:
            log(f"training {view} observation model")
            fitted = fit(parts["train"], parts["validation"], cfg, device=device, log=log)
            fitted.update(provenance=provenance, source_revision=source["revision"])
            save(fitted, path)
            fitted = load(path, device=device, expected_config=cfg, expected_provenance=provenance)
        calibration_scores = _event_probability(infer(fitted, parts["calibration"])["logits"], len(label_names))
        clean_calibration = parts["calibration"]["label"] == 0
        clean_scores = calibration_scores[clean_calibration]
        threshold = threshold_at_pfa(clean_scores, config.pfa)
        detector = {"score": "softmax_cross_pol" if config.protocol == PROTOCOL else "one_minus_softmax_clean",
                    "threshold": threshold, "target_clean_pfa": config.pfa,
                    "n_clean_calibration": len(clean_scores),
                    "provenance": fingerprint({"checkpoint_sha256": _sha256(path), "data": identity,
                                                "groups": summary["calibration"]["scenario_ids"], "pfa": config.pfa})}
        detector_path = out / f"detector_{view}.json"
        if detector_path.exists():
            if json.loads(detector_path.read_text()) != detector:
                raise ValueError(f"{detector_path} is incompatible with this checkpoint/calibration configuration")
        else:
            _write_json(detector_path, detector)
        # Test labels have not selected weights or set the clean alarm threshold.
        logits = infer(fitted, parts["test"])["logits"]
        scores = _event_probability(logits, len(label_names))
        predictions = logits.argmax(axis=1)
        alarm = scores > threshold
        labels, groups = parts["test"]["label"], parts["test"]["seed"]
        clean = labels == 0
        methods[view] = {"input_channels": 4 if view == "dual" else 2,
                         "accuracy": _rate(predictions == labels, groups),
                         "macro_f1": macro_f1(labels, predictions, len(label_names)),
                         "confusion": confusion(labels, predictions, len(label_names)).tolist(),
                         "clean_false_alarm": _rate(alarm[clean], groups[clean]),
                         "calibration_clean_false_alarm": float(np.mean(clean_scores > threshold)),
                         "detector": detector, "checkpoint_sha256": _sha256(path),
                         "training_source_revision": fitted.get("source_revision"),
                         "n_parameters": fitted["n_parameters"], "history": fitted["history"]}
        if config.protocol == PROTOCOL:
            cross = labels == 1
            methods[view]["cross_pol_detection"] = _rate(alarm[cross], groups[cross])
        else:
            methods[view]["event_detection"] = {
                name: _rate(alarm[labels == index], groups[labels == index])
                for index, name in enumerate(label_names) if index > 0}
            methods[view]["pooled_event_detection"] = _rate(alarm[~clean], groups[~clean])
        decisions[view] = (predictions, scores, alarm)
    result = {"protocol": config.protocol, "labels": list(label_names), "config": config.resolved(),
              "experiment_fingerprint": experiment_identity, "data_fingerprint": identity,
              "source": source, "partitions": summary, "methods": methods,
              "generation": manifest["config"], "receiver_calibration": manifest["calibration"],
              "runtime": {"python": platform.python_version(), "numpy": np.__version__,
                          "torch": str(torch.__version__), "device": device}}
    rows = []
    for index, (label, group) in enumerate(zip(parts["test"]["label"], parts["test"]["seed"])):
        probability_name = "cross_pol_probability" if config.protocol == PROTOCOL else "event_probability"
        rows.append({"scenario_id": int(group), "true_label": label_names[int(label)],
                     "views": {view: {"prediction": label_names[int(values[0][index])],
                                       probability_name: float(values[1][index]),
                                       "alarm": bool(values[2][index])} for view, values in decisions.items()}})
    _write_json(out / "config.json", config.resolved())
    _write_json(out / "results.json", result)
    _write_json(out / "predictions.json", rows)
    (out / "results.md").write_text(report(result))
    log(f"wrote {out / 'results.md'}")
    return result


def report(result):
    if result["protocol"] == EVENT_PROTOCOL:
        return event_report(result)
    lines = ["# Dual-polarization leakage development run", "",
             f"Protocol `{result['protocol']}`; known labels: clean, cross_pol.", "",
             "The labels describe a controlled uplink-XPD change in the simulator, not a uniquely identified operational cause.",
             "Receiver calibration is fitted from independent instrument pilots; physical propagation leakage is retained.",
             "Both spectra share the co-polarization power reference. Dual input uses both spectra and both carrier-plan masks.", "",
             "| View | Input channels | Classification accuracy | Macro-F1 | Clean false alarm | Cross-pol detection |",
             "|---|---|---|---|---|---|"]
    for view, values in result["methods"].items():
        lines.append(f"| {view} | {values['input_channels']} | {100 * values['accuracy']['mean']:.1f}% | "
                     f"{values['macro_f1']:.3f} | {100 * values['clean_false_alarm']['mean']:.1f}% | "
                     f"{100 * values['cross_pol_detection']['mean']:.1f}% |")
    lines += ["", "Classification uses argmax. Alarm rates use a separate threshold fitted to clean calibration groups.",
              "The target clean false-alarm rate need not hold on new test samples, especially with tiny calibration sets.",
              "Intervals in JSON resample scenario groups at fixed trained weights and thresholds; multiple training seeds are still needed.",
              "This small matched-input comparison validates execution, not a claim that dual-pol recognition is superior.", "", "## Partitions", "",
              "| Role | Samples | Scenario groups |", "|---|---|---|"]
    for role, values in result["partitions"].items():
        lines.append(f"| {role} | {values['n_samples']} | {len(values['scenario_ids'])} |")
    lines += ["", f"Experiment fingerprint: `{result['experiment_fingerprint']}`.", ""]
    return "\n".join(lines)


def event_report(result):
    lines = ["# Phase-noise and interference development run", "",
             f"Protocol `{result['protocol']}`; labels: {', '.join(result['labels'])}.", "",
             "All paired labels share carrier plans, link settings and phase-noise realizations.",
             "Carrier-under-carrier is injected before the wanted payload; adjacent-satellite interference is added at the receiver.",
             "These simulator causes are not uniquely identifiable from PSD observations. No orbital or antenna model is fitted.", "",
             "| View | Channels | Classification accuracy | Macro-F1 | Clean false alarm | Pooled event detection |",
             "|---|---|---|---|---|---|"]
    for view, values in result["methods"].items():
        lines.append(f"| {view} | {values['input_channels']} | {100 * values['accuracy']['mean']:.1f}% | "
                     f"{values['macro_f1']:.3f} | {100 * values['clean_false_alarm']['mean']:.1f}% | "
                     f"{100 * values['pooled_event_detection']['mean']:.1f}% |")
    lines += ["", "Classification uses argmax. Event alarms use sum of non-clean softmax probabilities,",
              "with a threshold fitted only on separate clean calibration groups. This is a closed-set development task.",
              "Detection positive class is any event; denominators below contain only that event family.", "",
              "| View | Event family | Alarm rate | Samples | Scenario groups |", "|---|---|---|---|---|"]
    for view, values in result["methods"].items():
        for family, rate in values["event_detection"].items():
            lines.append(f"| {view} | {family} | {100 * rate['mean']:.1f}% | {rate['n_samples']} | {rate['n_scenarios']} |")
    lines += ["", "Intervals in JSON resample scenario groups at fixed weights/thresholds; training-seed uncertainty is not included.",
              "Tiny calibration sets cannot establish the requested operational false-alarm rate. This pilot checks execution, not recognition quality.",
              "The final eight-known-class dual-polarization open-set benchmark remains outstanding.", "", "## Partitions", "",
              "| Role | Samples | Scenario groups |", "|---|---|---|"]
    for role, values in result["partitions"].items():
        lines.append(f"| {role} | {values['n_samples']} | {len(values['scenario_ids'])} |")
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
        run_dual_experiment(DualExperimentConfig.from_file(args.config), args.data, args.out,
                            reuse=args.reuse, device=args.device)
    except (ValueError, FileNotFoundError) as error:
        parser.exit(2, f"error: {error}\n")


if __name__ == "__main__":
    main()

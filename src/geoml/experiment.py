"""First open-set development experiment using frozen A1 observations.

    python -m geoml.experiment --config configs/stage_b_openset.json \
        --data data/openset-pilot --out runs/openset-pilot

Only a non-clean interference family is held out. Final unknowns do not select
weights or rejection thresholds. This is B1-dev/1, not the eight-class benchmark.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
import torch

from geosim.classes import LABELS
from geosim.dataset import PROTOCOL as SOURCE_PROTOCOL, load_split, read_manifest, split_fingerprint
from geosim.protocol import PROTOCOL, HoldoutProtocol, partition_summary

from .artifacts import fingerprint
from .calibration import RejectionCalibration, calibrate
from .evaluation import evaluate, report
from .openset import METHODS, unknown_scores
from .train import TrainConfig, fit, infer, load, save

SOURCE_SPLITS = ("train_nl", "val_nl", "test_id_nl")


@dataclass(frozen=True)
class ExperimentConfig:
    protocol: str = PROTOCOL
    holdout_label: str = "swept_cw"
    calibration_fraction: float = 0.5
    split_seed: int = 0
    target_acceptance: float = 0.95
    temperature: float = 1.0
    training: dict = field(default_factory=lambda: {"epochs": 3, "batch": 16, "seed": 0})

    def __post_init__(self):
        if self.protocol != PROTOCOL:
            raise ValueError(f"supported experiment protocol is {PROTOCOL}")
        self.holdout_protocol()
        if isinstance(self.target_acceptance, bool) or not 0 < self.target_acceptance <= 1:
            raise ValueError("target_acceptance must be in (0, 1]")
        if isinstance(self.temperature, bool) or not np.isfinite(self.temperature) or self.temperature <= 0:
            raise ValueError("temperature must be finite and positive")
        if not isinstance(self.training, dict) or "labels" in self.training:
            raise ValueError("training must be an object; labels are derived from the holdout protocol")
        self.train_config()

    def holdout_protocol(self) -> HoldoutProtocol:
        return HoldoutProtocol(self.holdout_label, self.calibration_fraction, self.split_seed)

    def train_config(self) -> TrainConfig:
        return TrainConfig(labels=self.holdout_protocol().known_labels, **self.training)

    @classmethod
    def from_file(cls, path) -> "ExperimentConfig":
        raw = json.loads(Path(path).read_text())
        if not isinstance(raw, dict):
            raise ValueError("experiment configuration must be a JSON object")
        try:
            return cls(**raw)
        except TypeError as error:
            raise ValueError(f"invalid experiment configuration: {error}") from error

    def resolved(self) -> dict:
        training = asdict(self.train_config())
        training.pop("labels")  # Derived from holdout_label; keep saved config directly reusable.
        return {**asdict(self), "training": training}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source_identity() -> dict:
    root = Path(__file__).resolve().parents[1]
    files = sorted(root.glob("**/*.py")) + sorted((root / "geosim" / "data").glob("*"))
    hashes = {str(path.relative_to(root)): _sha256(path) for path in files if path.is_file()}
    revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=True).stdout.strip()
    return {"revision": revision, "files_sha256": hashes}


def _write_json(path: Path, value) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def run_experiment(config: ExperimentConfig, data, out, *, reuse: bool = False,
                   device: str = "cpu", log=print) -> dict:
    """Fit/load a compatible model, calibrate on known groups, then test once.

    A1 source datasets may contain the held-out family. It is filtered from
    training, weight-selection validation and calibration before any model call.
    Partial source data are allowed for development and explicitly reported.
    """
    data, out = Path(data), Path(out)
    manifests = {name: read_manifest(data / name) for name in SOURCE_SPLITS}
    for name, manifest in manifests.items():
        if manifest["protocol"] != SOURCE_PROTOCOL or tuple(manifest["labels"]) != LABELS:
            raise ValueError(f"{name} is not a compatible frozen A1 source dataset")
        if manifest["split"]["name"] != name:
            raise ValueError(f"{name} declares split {manifest['split']['name']}; source roles cannot be swapped")
    identities = {name: split_fingerprint(data / name) for name in SOURCE_SPLITS}
    datasets = {name: load_split(data / name) for name in SOURCE_SPLITS}
    protocol = config.holdout_protocol()
    parts = protocol.partition(*(datasets[name] for name in SOURCE_SPLITS))
    summary = partition_summary(parts)
    cfg = config.train_config()
    source = _source_identity()
    # Checkpoint identity deliberately excludes final test data and rejection
    # targets: they cannot influence optimization or weight selection.
    provenance = {"protocol": PROTOCOL, "holdout_label": config.holdout_label,
                  "training_data": identities["train_nl"], "validation_data": identities["val_nl"],
                  "validation_groups": summary["validation"]["scenario_ids"], "source": source}
    experiment_identity = fingerprint({"config": config.resolved(), "data": identities, "source": source})
    out.mkdir(parents=True, exist_ok=True)
    checkpoint = out / "model.pt"
    if checkpoint.exists():
        if not reuse:
            raise ValueError(f"{checkpoint} already exists; use --reuse or a new output directory")
        fitted = load(checkpoint, device=device, expected_config=asdict(cfg), expected_provenance=provenance)
        log(f"reusing compatible checkpoint {checkpoint}")
    else:
        fitted = fit(parts["train"], parts["validation"], cfg, device=device, log=log)
        fitted["provenance"] = provenance
        save(fitted, checkpoint)
        # Exercise the exact checkpoint that a later process will use.
        fitted = load(checkpoint, device=device, expected_config=asdict(cfg), expected_provenance=provenance)
    model_hash = _sha256(checkpoint)
    calibration_logits = infer(fitted, parts["calibration"])["logits"]
    calibrators = {}
    for method in METHODS:
        calibration_identity = fingerprint({"method": method, "checkpoint_sha256": model_hash,
                                            "validation_data": identities["val_nl"],
                                            "groups": summary["calibration"]["scenario_ids"],
                                            "target_acceptance": config.target_acceptance,
                                            "temperature": config.temperature})
        fitted_calibration = calibrate(calibration_logits, method, config.target_acceptance,
                                       config.temperature, calibration_identity)
        path = out / f"calibration_{method}.json"
        if path.exists():
            existing = RejectionCalibration.load(path)
            if existing != fitted_calibration:
                raise ValueError(f"{path} is incompatible with this checkpoint/calibration configuration; use a new output directory")
            calibrators[method] = existing
        else:
            fitted_calibration.save(path)
            calibrators[method] = RejectionCalibration.load(path)
    # No test inference occurs until both rejection thresholds are frozen.
    known_logits = infer(fitted, parts["known_test"])["logits"]
    unknown_logits = infer(fitted, parts["unknown_test"])["logits"]
    methods = {method: evaluate(known_logits, unknown_logits, parts["known_test"]["label"],
                                parts["known_test"]["seed"], parts["unknown_test"]["seed"], calibration)
               for method, calibration in calibrators.items()}
    for method, calibration in calibrators.items():
        scores = unknown_scores(calibration_logits, method, config.temperature)
        methods[method]["calibration_acceptance"] = float(np.mean(calibration.accept(scores)))
    result = {"protocol": PROTOCOL, "source_protocol": SOURCE_PROTOCOL,
              "holdout_label": config.holdout_label, "known_labels": list(protocol.known_labels),
              "config": config.resolved(), "partitions": summary, "methods": methods,
              "source_data_complete": all(manifest["complete"] for manifest in manifests.values()),
              "data_fingerprints": identities, "source": source,
              "experiment_fingerprint": experiment_identity, "checkpoint_sha256": model_hash,
              "calibrators": {method: calibration.to_dict() for method, calibration in calibrators.items()},
              "n_parameters": fitted["n_parameters"], "training_history": fitted["history"],
              "runtime": {"python": platform.python_version(), "numpy": np.__version__,
                          "torch": str(torch.__version__), "device": device}}
    predictions = []
    for role, logits in (("known_test", known_logits), ("unknown_test", unknown_logits)):
        current = parts[role]
        predicted = logits.argmax(axis=1)
        decisions = {method: (unknown_scores(logits, method, config.temperature),
                              calibrators[method]) for method in METHODS}
        for i in range(len(logits)):
            truth = (protocol.known_labels[int(current["label"][i])]
                     if role == "known_test" else config.holdout_label)
            row = {"scenario_id": int(current["seed"][i]), "role": role, "true_family": truth,
                   "known_prediction": protocol.known_labels[int(predicted[i])], "methods": {}}
            for method, (scores, calibration) in decisions.items():
                accepted = bool(scores[i] <= calibration.threshold)
                row["methods"][method] = {"unknown_score": float(scores[i]), "accepted": accepted,
                                           "prediction": row["known_prediction"] if accepted else "unknown"}
            predictions.append(row)
    _write_json(out / "config.json", config.resolved())
    _write_json(out / "results.json", result)
    _write_json(out / "predictions.json", predictions)
    (out / "results.md").write_text(report(result))
    log(f"wrote {out / 'results.md'}")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", required=True)
    parser.add_argument("--data", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--reuse", action="store_true", help="reuse a matching checkpoint and calibration")
    parser.add_argument("--device", default="cpu", choices=("cpu", "cuda"))
    args = parser.parse_args(argv)
    try:
        run_experiment(ExperimentConfig.from_file(args.config), args.data, args.out,
                       reuse=args.reuse, device=args.device)
    except (ValueError, FileNotFoundError) as error:
        parser.exit(2, f"error: {error}\n")


if __name__ == "__main__":
    main()

"""Open-set development experiments using frozen A1 observations.

    python -m geoml.experiment --config configs/stage_b_openset.json \
        --data data/openset-pilot --out runs/openset-pilot

B1-dev/1 holds out a non-clean A1 family. B1-dev/2 adds explicit test-only U1
sources and training-only Mahalanobis scoring. Final unknowns never select
weights or rejection thresholds. Neither is the final eight-class benchmark.
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
from geosim.unknowns import load_unknowns, read_unknown_manifest, unknown_fingerprint

from .artifacts import fingerprint
from .calibration import RejectionCalibration, calibrate_scores
from .evaluation import evaluate_scores, report
from .mahalanobis import MahalanobisScorer, fit_mahalanobis
from .openset import METHODS, unknown_scores
from .train import TrainConfig, fit, infer, load, save

SOURCE_SPLITS = ("train_nl", "val_nl", "test_id_nl")
EXTENDED_PROTOCOL = "B1-dev/2"


@dataclass(frozen=True)
class ExperimentConfig:
    protocol: str = PROTOCOL
    holdout_label: str = "swept_cw"
    calibration_fraction: float = 0.5
    split_seed: int = 0
    target_acceptance: float = 0.95
    temperature: float = 1.0
    methods: tuple[str, ...] = METHODS
    mahalanobis_regularization: float = 0.1
    training: dict = field(default_factory=lambda: {"epochs": 3, "batch": 16, "seed": 0})

    def __post_init__(self):
        if self.protocol not in (PROTOCOL, EXTENDED_PROTOCOL):
            raise ValueError(f"supported experiment protocols are {PROTOCOL} and {EXTENDED_PROTOCOL}")
        self.holdout_protocol()
        if isinstance(self.target_acceptance, bool) or not 0 < self.target_acceptance <= 1:
            raise ValueError("target_acceptance must be in (0, 1]")
        if isinstance(self.temperature, bool) or not np.isfinite(self.temperature) or self.temperature <= 0:
            raise ValueError("temperature must be finite and positive")
        if (not isinstance(self.methods, (tuple, list)) or not self.methods
                or any(not isinstance(method, str) or method not in (*METHODS, "mahalanobis") for method in self.methods)
                or len(set(self.methods)) != len(self.methods)):
            raise ValueError("methods must be unique names from msp, energy, mahalanobis")
        object.__setattr__(self, "methods", tuple(self.methods))
        if self.protocol == PROTOCOL and self.methods != METHODS:
            raise ValueError("changed scoring methods require B1-dev/2")
        if (isinstance(self.mahalanobis_regularization, bool) or not np.isfinite(self.mahalanobis_regularization)
                or not 0 < self.mahalanobis_regularization <= 1):
            raise ValueError("mahalanobis_regularization must be in (0, 1]")
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
                   device: str = "cpu", unknown_data=None, log=print) -> dict:
    """Fit/load a compatible model, calibrate on known groups, then test once.

    A1 source datasets may contain the held-out family. It is filtered from
    training, weight-selection validation and calibration before any model call.
    Partial source data are allowed for development and explicitly reported.
    """
    data, out = Path(data), Path(out)
    if (config.protocol == EXTENDED_PROTOCOL) != (unknown_data is not None):
        raise ValueError("B1-dev/2 requires --unknown-data; B1-dev/1 evaluates only the A1 held-out family")
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
    families = np.full(len(parts["unknown_test"]["label"]), config.holdout_label, dtype=object)
    unknown_manifest = None
    if unknown_data is not None:
        unknown_manifest = read_unknown_manifest(unknown_data)
        if unknown_manifest["bandwidth"] != manifests["test_id_nl"]["split"]["bandwidth"]:
            raise ValueError("external unknown bandwidth must match the known test bandwidth for B1-dev/2")
        external = load_unknowns(unknown_data)
        forbidden = np.concatenate([parts[role]["seed"] for role in ("train", "validation", "calibration")])
        if np.intersect1d(external["seed"], forbidden).size:
            raise ValueError("external unknown scenario group leakage into training or validation")
        if set(external["family"]) & set(protocol.known_labels):
            raise ValueError("external unknown families overlap the known label set")
        heldout = parts["unknown_test"]
        parts["unknown_test"] = {key: np.concatenate((heldout[key], external[key])) for key in ("spec", "mask", "seed")}
        parts["unknown_test"].update(label=np.zeros(len(heldout["label"]) + len(external["label"]), dtype=np.int64),
                                      meta=heldout["meta"] + external["meta"])
        families = np.concatenate((families, external["family"]))
        identities["external_unknowns"] = unknown_fingerprint(unknown_data)
    summary = partition_summary(parts)
    cfg = config.train_config()
    source = _source_identity()
    # Checkpoint identity deliberately excludes final test data and rejection
    # targets: they cannot influence optimization or weight selection.
    provenance = {"protocol": config.protocol, "holdout_label": config.holdout_label,
                  "training_data": identities["train_nl"], "validation_data": identities["val_nl"],
                  "validation_groups": summary["validation"]["scenario_ids"], "source_files_sha256": source["files_sha256"]}
    experiment_identity = fingerprint({"config": config.resolved(), "data": identities, "source_files_sha256": source["files_sha256"]})
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
        fitted["source_revision"] = source["revision"]
        save(fitted, checkpoint)
        # Exercise the exact checkpoint that a later process will use.
        fitted = load(checkpoint, device=device, expected_config=asdict(cfg), expected_provenance=provenance)
    model_hash = _sha256(checkpoint)
    scorer = None
    if "mahalanobis" in config.methods:
        scorer_identity = fingerprint({"checkpoint_sha256": model_hash, "training_data": identities["train_nl"],
                                       "regularization": config.mahalanobis_regularization,
                                       "source_files_sha256": source["files_sha256"]})
        scorer_path = out / "mahalanobis.npz"
        if scorer_path.exists():
            scorer = MahalanobisScorer.load(scorer_path)
            if scorer.provenance != scorer_identity:
                raise ValueError("Mahalanobis scorer is incompatible with this checkpoint/training configuration")
        else:
            training_embedding = infer(fitted, parts["train"])["embedding"]
            scorer = fit_mahalanobis(training_embedding, parts["train"]["label"], len(protocol.known_labels),
                                     config.mahalanobis_regularization, scorer_identity)
            scorer.save(scorer_path)
            scorer = MahalanobisScorer.load(scorer_path)

    def score(outputs: dict, method: str) -> np.ndarray:
        if method == "mahalanobis":
            return scorer.score(outputs["embedding"])
        return unknown_scores(outputs["logits"], method, config.temperature)

    calibration_output = infer(fitted, parts["calibration"])
    calibrators = {}
    for method in config.methods:
        calibration_identity = fingerprint({"method": method, "checkpoint_sha256": model_hash,
                                            "validation_data": identities["val_nl"],
                                            "groups": summary["calibration"]["scenario_ids"],
                                            "target_acceptance": config.target_acceptance,
                                            "temperature": config.temperature,
                                            "scorer_sha256": _sha256(out / "mahalanobis.npz") if method == "mahalanobis" else None})
        fitted_calibration = calibrate_scores(score(calibration_output, method), method, config.target_acceptance,
                                              1.0 if method == "mahalanobis" else config.temperature, calibration_identity)
        path = out / f"calibration_{method}.json"
        if path.exists():
            existing = RejectionCalibration.load(path)
            if existing != fitted_calibration:
                raise ValueError(f"{path} is incompatible with this checkpoint/calibration configuration; use a new output directory")
            calibrators[method] = existing
        else:
            fitted_calibration.save(path)
            calibrators[method] = RejectionCalibration.load(path)
    # No test inference occurs until every rejection threshold is frozen.
    known_output = infer(fitted, parts["known_test"])
    unknown_output = infer(fitted, parts["unknown_test"])
    known_scores = {method: score(known_output, method) for method in config.methods}
    test_scores = {method: score(unknown_output, method) for method in config.methods}

    def evaluate_population(selected: np.ndarray) -> dict:
        return {method: evaluate_scores(known_output["logits"], known_scores[method], test_scores[method][selected],
                                        parts["known_test"]["label"], parts["known_test"]["seed"],
                                        parts["unknown_test"]["seed"][selected], calibration)
                for method, calibration in calibrators.items()}

    methods = evaluate_population(np.ones(len(families), dtype=bool))
    methods_by_family = {family: evaluate_population(families == family) for family in sorted(set(families))}
    for method, calibration in calibrators.items():
        scores = score(calibration_output, method)
        methods[method]["calibration_acceptance"] = float(np.mean(calibration.accept(scores)))
    result = {"protocol": config.protocol, "source_protocol": SOURCE_PROTOCOL,
              "holdout_label": config.holdout_label, "known_labels": list(protocol.known_labels),
              "config": config.resolved(), "partitions": summary, "methods": methods,
              "unknown_families": sorted(set(families)), "methods_by_family": methods_by_family,
              "unknown_data_protocol": unknown_manifest["protocol"] if unknown_manifest else None,
              "unknown_data_summary": {key: unknown_manifest[key] for key in ("bandwidth", "families", "first_seed", "n_seeds", "n_samples")} if unknown_manifest else None,
              "unknown_family_counts": {family: int(np.sum(families == family)) for family in sorted(set(families))},
              "source_data_complete": all(manifest["complete"] for manifest in manifests.values()),
              "data_fingerprints": identities, "source": source,
              "experiment_fingerprint": experiment_identity, "checkpoint_sha256": model_hash,
              "calibrators": {method: calibration.to_dict() for method, calibration in calibrators.items()},
              "mahalanobis": scorer.to_dict() if scorer else None,
              "training_source_revision": fitted.get("source_revision"),
              "n_parameters": fitted["n_parameters"], "training_history": fitted["history"],
              "runtime": {"python": platform.python_version(), "numpy": np.__version__,
                          "torch": str(torch.__version__), "device": device}}
    predictions = []
    for role, outputs in (("known_test", known_output), ("unknown_test", unknown_output)):
        logits = outputs["logits"]
        current = parts[role]
        predicted = logits.argmax(axis=1)
        decisions = {method: (known_scores[method] if role == "known_test" else test_scores[method],
                              calibrators[method]) for method in config.methods}
        for i in range(len(logits)):
            truth = (protocol.known_labels[int(current["label"][i])]
                     if role == "known_test" else str(families[i]))
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
    parser.add_argument("--unknown-data", help="test-only U1-dev/1 artifacts required by B1-dev/2")
    parser.add_argument("--reuse", action="store_true", help="reuse a matching checkpoint and calibration")
    parser.add_argument("--device", default="cpu", choices=("cpu", "cuda"))
    args = parser.parse_args(argv)
    try:
        run_experiment(ExperimentConfig.from_file(args.config), args.data, args.out,
                       reuse=args.reuse, device=args.device, unknown_data=args.unknown_data)
    except (ValueError, FileNotFoundError) as error:
        parser.exit(2, f"error: {error}\n")


if __name__ == "__main__":
    main()

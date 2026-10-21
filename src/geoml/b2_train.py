"""Two-head B2 training with observed residuals and train-only centers.

Feature artifacts stream one shard at a time. Checkpoint selection uses only
val-select class macro-F1; val-calib and test never update weights or centers.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from numbers import Real
from pathlib import Path
import time

import numpy as np
import torch
from torch import nn

from geosim.b2_protocol import LABELS, role_for_group

from .artifacts import fingerprint
from .b2_data import CHANNELS, as_role, iter_batches
from .b2_model import B2Model
from .data import reference_level
from .metrics import macro_f1
from .model import n_parameters


def _real(value, name, *, minimum=0, maximum=None, strict=False):
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real) or not np.isfinite(value):
        raise ValueError(f"{name} must be a finite real number")
    value = float(value)
    if value < minimum or (strict and value == minimum) or (maximum is not None and value > maximum):
        raise ValueError(f"{name} is outside the supported range")
    return value


@dataclass(frozen=True)
class B2TrainConfig:
    labels: tuple[str, ...] = LABELS
    view: str = "b2"
    level: str = "carrier"
    time_pool: int = 2
    width: int = 8
    epochs: int = 3
    batch: int = 8
    lr: float = 1e-3
    weight_decay: float = 1e-4
    seed: int = 0
    augment: bool = True
    center_weight: float = 0.01
    consistency_weight: float = 1.0
    plan_shift_probability: float = 0.15
    max_plan_shift_hz: float = 0.5e6

    def __post_init__(self):
        if not isinstance(self.labels, (tuple, list)) or tuple(self.labels) != LABELS:
            raise ValueError("B2 labels must retain the frozen eight-label order")
        object.__setattr__(self, "labels", tuple(self.labels))
        if not isinstance(self.view, str) or self.view not in CHANNELS:
            raise ValueError("B2 view must be b2, dual or co")
        if self.level not in ("carrier", "absolute"):
            raise ValueError("B2 level must be carrier or absolute")
        for name in ("time_pool", "width", "epochs", "batch"):
            value = getattr(self, name)
            if isinstance(value, (bool, np.bool_)) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        if isinstance(self.seed, (bool, np.bool_)) or not isinstance(self.seed, int) or self.seed < 0:
            raise ValueError("seed must be a nonnegative integer")
        if not isinstance(self.augment, bool):
            raise ValueError("augment must be a boolean")
        for name in ("lr", "weight_decay", "center_weight", "consistency_weight", "plan_shift_probability", "max_plan_shift_hz"):
            value = _real(getattr(self, name), name, strict=name == "lr",
                          maximum=1 if name == "plan_shift_probability" else None)
            object.__setattr__(self, name, value)


def _fit_role(source, expected):
    if source.role is not None and source.role != expected:
        raise ValueError(f"weight fitting requires role {expected!r}, not {source.role!r}")
    for group in source.groups:
        try:
            reserved_role = role_for_group(int(group))
        except ValueError:
            continue  # Small in-memory diagnostics may use non-artifact IDs.
        if reserved_role != expected:
            raise ValueError(f"weight fitting cannot consume reserved role {reserved_role!r}")


def _training_reference(source):
    total, count, labels = 0.0, 0, set()
    for shard in source.shards():
        values = reference_level(shard["spec"][:, 0], shard["mask"][:, 0])
        if not np.isfinite(values).all():
            raise ValueError("training co-feed reference must be finite")
        total += float(np.sum(values.astype(np.float64)))
        count += len(values)
        labels.update(int(label) for label in shard["label"])
    if not count or labels != set(range(len(LABELS))):
        raise ValueError("B2 training must contain every known class")
    return total / count


@torch.no_grad()
def _infer(model, source, cfg, reference, device, batch):
    model.eval()
    outputs = {key: [] for key in ("logits", "consistency_logits", "embedding", "label", "plan_consistency", "seed")}
    for item in iter_batches(source, cfg, reference, batch=batch):
        prediction = model(torch.from_numpy(item["x"]).to(device))
        for key in ("logits", "consistency_logits", "embedding"):
            values = prediction[key].detach().cpu().numpy()
            if not np.isfinite(values).all():
                raise ValueError("B2 inference produced nonfinite values")
            outputs[key].append(values)
        for key in ("label", "plan_consistency", "seed"):
            outputs[key].append(item[key].astype(np.int64, copy=False))
    if not outputs["label"]:
        raise ValueError("B2 inference requires observations")
    return {key: np.concatenate(values) for key, values in outputs.items()}


def fit(train, val, config: B2TrainConfig, *, device="cpu", provenance=None, log=print):
    """Fit both heads and centers, selecting by val-select class macro-F1."""
    if not isinstance(config, B2TrainConfig):
        raise ValueError("config must be B2TrainConfig")
    cache = {}
    train, val = as_role(train, manifest_cache=cache), as_role(val, manifest_cache=cache)
    _fit_role(train, "train")
    _fit_role(val, "val-select")
    if np.intersect1d(train.groups, val.groups).size:
        raise ValueError("training and validation scenario groups must be disjoint")
    torch.manual_seed(config.seed)
    reference = _training_reference(train)
    model = B2Model(len(config.labels), config.width, CHANNELS[config.view]).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=config.lr, weight_decay=config.weight_decay)
    steps = config.epochs * train.n_batches(config.batch)
    scheduler = torch.optim.lr_scheduler.OneCycleLR(optimizer, max_lr=config.lr, total_steps=steps)
    rng = np.random.default_rng(config.seed)
    best, best_state, history = -1.0, None, []
    for epoch in range(config.epochs):
        model.train()
        sums = {key: 0.0 for key in ("loss", "class_loss", "consistency_loss", "center_loss")}
        count, started = 0, time.perf_counter()
        for item in iter_batches(train, config, reference, shuffle=True, rng=rng, augment=config.augment):
            inputs = torch.from_numpy(item["x"]).to(device)
            labels = torch.as_tensor(item["label"].astype(np.int64), device=device)
            consistency = torch.as_tensor(item["plan_consistency"].astype(np.int64), device=device)
            result = model(inputs)
            primary_loss = nn.functional.cross_entropy(result["logits"], labels)
            auxiliary_loss = nn.functional.cross_entropy(result["consistency_logits"], consistency)
            center_loss = model.center_loss(result["embedding"], labels)
            loss = primary_loss + config.consistency_weight * auxiliary_loss + config.center_weight * center_loss
            if not torch.isfinite(loss):
                raise ValueError("B2 training produced a nonfinite loss")
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            scheduler.step()
            n = len(labels)
            for key, value in zip(sums, (loss, primary_loss, auxiliary_loss, center_loss)):
                sums[key] += float(value.detach()) * n
            count += n
        evaluated = _infer(model, val, config, reference, device, config.batch)
        f1 = macro_f1(evaluated["label"], evaluated["logits"].argmax(1), len(config.labels))
        row = {"epoch": epoch, **{f"train_{key}": value / count for key, value in sums.items()},
               "val_macro_f1": f1,
               "val_plan_consistency_accuracy": float(np.mean(evaluated["consistency_logits"].argmax(1) == evaluated["plan_consistency"]))}
        history.append(row)
        if f1 > best:
            best, best_state = f1, {key: value.detach().cpu().clone() for key, value in model.state_dict().items()}
        log(f"  epoch {epoch + 1}/{config.epochs} loss {row['train_loss']:.3f} "
            f"val macro-F1 {f1:.3f} ({time.perf_counter() - started:.1f} s)")
    model.load_state_dict(best_state)
    fitted = {"model": model, "config": asdict(config), "absolute_ref_db": float(reference),
              "history": history, "n_parameters": n_parameters(model), "device": device,
              "selection_metric": "val_select_class_macro_f1",
              "training_groups": train.groups.astype(np.int64).tolist(),
              "selection_groups": val.groups.astype(np.int64).tolist()}
    if provenance is not None:
        fingerprint(provenance)  # Reject non-JSON/NaN provenance before saving.
        fitted["provenance"] = provenance
    return fitted


def infer(fitted, data, batch=None):
    """Return both logits, embeddings and targets in exact source iteration order."""
    config = B2TrainConfig(**fitted["config"])
    batch = config.batch if batch is None else batch
    if isinstance(batch, (bool, np.bool_)) or not isinstance(batch, int) or batch < 1:
        raise ValueError("batch must be a positive integer")
    return _infer(fitted["model"], as_role(data), config, fitted["absolute_ref_db"], fitted["device"], batch)


def _metadata_fingerprint(artifact):
    return fingerprint({"kind": artifact["kind"], "config": artifact["config"],
                        "provenance": artifact.get("provenance"), "absolute_ref_db": artifact["absolute_ref_db"]})


def save(fitted, path):
    metadata = {key: value for key, value in fitted.items() if key not in ("model", "device")}
    metadata.update(kind="b2_two_head", artifact_version=1)
    metadata["metadata_fingerprint"] = _metadata_fingerprint(metadata)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    torch.save({"state": fitted["model"].state_dict(), **metadata}, temporary)
    temporary.replace(path)


def load(path, *, device="cpu", expected_config=None, expected_provenance=None):
    try:
        artifact = torch.load(path, map_location="cpu", weights_only=True)
        if (artifact["kind"] != "b2_two_head" or artifact["artifact_version"] != 1
                or artifact["metadata_fingerprint"] != _metadata_fingerprint(artifact)):
            raise ValueError("B2 checkpoint metadata is invalid or has changed")
        config = B2TrainConfig(**artifact["config"])
        _real(artifact["absolute_ref_db"], "absolute_ref_db", minimum=-np.finfo(float).max)
        if expected_config is not None:
            expected = expected_config if isinstance(expected_config, B2TrainConfig) else B2TrainConfig(**expected_config)
            if fingerprint(asdict(config)) != fingerprint(asdict(expected)):
                raise ValueError("B2 checkpoint training configuration does not match")
        if expected_provenance is not None and fingerprint(artifact.get("provenance")) != fingerprint(expected_provenance):
            raise ValueError("B2 checkpoint provenance does not match")
        model = B2Model(len(config.labels), config.width, CHANNELS[config.view]).to(device)
        model.load_state_dict(artifact.pop("state"))
        if artifact["n_parameters"] != n_parameters(model):
            raise ValueError("B2 checkpoint parameter count differs from its model")
        if not all(torch.isfinite(value).all() for value in model.state_dict().values()):
            raise ValueError("B2 checkpoint has nonfinite model parameters")
        return {"model": model, "device": device, **artifact}
    except (KeyError, TypeError, RuntimeError) as error:
        raise ValueError(f"invalid B2 checkpoint: {error}") from error

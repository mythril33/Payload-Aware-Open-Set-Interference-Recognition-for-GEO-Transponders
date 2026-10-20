"""Training and inference for the stage-A classifiers (P6 §4)."""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import torch
from torch import nn

from .artifacts import fingerprint
from .data import CORE_DB, preprocess, reference_level
from .metrics import macro_f1
from .model import SmallResNet, n_parameters


@dataclass
class TrainConfig:
    labels: tuple
    level: str = "carrier"       # "carrier" or "absolute", see data.preprocess
    time_pool: int = 2
    width: int = 16
    epochs: int = 30
    batch: int = 32
    lr: float = 1e-3
    augment: bool = True         # random frequency mirror and circular time shift
    weight_decay: float = 1e-4
    seed: int = 0

    def __post_init__(self):
        if (not isinstance(self.labels, (tuple, list)) or len(self.labels) < 2
                or any(not isinstance(label, str) or not label for label in self.labels)
                or len(set(self.labels)) != len(self.labels)):
            raise ValueError("labels must contain at least two distinct nonempty names")
        if self.level not in ("carrier", "absolute"):
            raise ValueError("level must be 'carrier' or 'absolute'")
        for name in ("time_pool", "width", "epochs", "batch"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        if not np.isfinite(self.lr) or self.lr <= 0:
            raise ValueError("lr must be finite and positive")
        if not np.isfinite(self.weight_decay) or self.weight_decay < 0:
            raise ValueError("weight_decay must be finite and nonnegative")
        if isinstance(self.seed, bool) or not isinstance(self.seed, int) or self.seed < 0:
            raise ValueError("seed must be a nonnegative integer")
        if not isinstance(self.augment, bool):
            raise ValueError("augment must be a boolean")


def _inputs(d: dict, cfg: TrainConfig, absolute_ref_db):
    spec, mask = np.asarray(d["spec"]), np.asarray(d["mask"])
    if spec.ndim != 3 or not len(spec) or not spec.shape[1] or not spec.shape[2]:
        raise ValueError("spec must be a nonempty (N, time, frequency) array")
    if mask.shape != (len(spec), spec.shape[2]):
        raise ValueError("mask must match the sample and frequency dimensions of spec")
    if spec.shape[1] % cfg.time_pool:
        raise ValueError("time_pool must divide the spectrogram time dimension")
    if not np.isfinite(spec).all() or not np.isfinite(mask).all():
        raise ValueError("model inputs must be finite")
    if np.any(~np.any(mask > CORE_DB, axis=1)):
        raise ValueError("each plan mask must contain at least one planned carrier core bin")
    x = preprocess(spec, mask, cfg.level, cfg.time_pool, absolute_ref_db)
    if not np.isfinite(x).all():
        raise ValueError("preprocessed model inputs must be finite")
    return torch.from_numpy(x)


def _labels(d: dict, n_classes: int, name: str) -> np.ndarray:
    labels = np.asarray(d["label"])
    if labels.shape != (len(d["spec"]),) or not np.issubdtype(labels.dtype, np.integer):
        raise ValueError(f"{name} labels must be one integer class index per sample")
    if np.any((labels < 0) | (labels >= n_classes)):
        raise ValueError(f"{name} labels contain an out-of-range class index")
    return labels.astype(np.int64, copy=False)


@torch.no_grad()
def predict(model: nn.Module, x: torch.Tensor, device: str, batch: int = 64) -> np.ndarray:
    """Class probabilities, (N, n_classes)."""
    if isinstance(batch, bool) or not isinstance(batch, int) or batch < 1:
        raise ValueError("batch must be a positive integer")
    if not len(x):
        raise ValueError("prediction requires at least one sample")
    model.eval()
    out = [torch.softmax(model(x[i:i + batch].to(device)), dim=1).cpu() for i in range(0, len(x), batch)]
    return torch.cat(out).numpy()


def fit(train: dict, val: dict, cfg: TrainConfig, device: str | None = None, log=print) -> dict:
    """Train on `train`, keep the weights with the best validation macro-F1.

    Returns {"model", "config", "absolute_ref_db", "history", "n_parameters"}.
    """
    device = device or ("cuda" if torch.cuda.is_available() else "cpu")
    _labels(train, len(cfg.labels), "training")
    _labels(val, len(cfg.labels), "validation")
    if not len(train["spec"]) or not len(val["spec"]):
        raise ValueError("training and validation data must be nonempty")
    torch.manual_seed(cfg.seed)
    ref = float(reference_level(train["spec"], train["mask"]).mean())      # training data only
    xt, xv = _inputs(train, cfg, ref), _inputs(val, cfg, ref)
    yt = torch.from_numpy(_labels(train, len(cfg.labels), "training"))
    model = SmallResNet(len(cfg.labels), cfg.width).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=cfg.lr, weight_decay=cfg.weight_decay)
    steps = cfg.epochs * -(-len(xt) // cfg.batch)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=cfg.lr, total_steps=steps)
    gen = torch.Generator().manual_seed(cfg.seed)
    best, best_state, history = -1.0, None, []
    for epoch in range(cfg.epochs):
        model.train()
        t, loss_sum = time.time(), 0.0
        perm = torch.randperm(len(xt), generator=gen)
        for i in range(0, len(perm), cfg.batch):
            idx = perm[i:i + cfg.batch]
            xb = xt[idx]
            if cfg.augment:
                flip = torch.rand(len(idx), generator=gen) < 0.5
                xb = torch.where(flip[:, None, None, None], xb.flip(-1), xb)
                xb = xb.roll(int(torch.randint(xb.shape[2], (1,), generator=gen)), dims=2)
            loss = nn.functional.cross_entropy(model(xb.to(device)), yt[idx].to(device))
            opt.zero_grad()
            loss.backward()
            opt.step()
            sched.step()
            loss_sum += loss.item() * len(idx)
        f1 = macro_f1(val["label"], predict(model, xv, device).argmax(1), len(cfg.labels))
        history.append({"epoch": epoch, "train_loss": loss_sum / len(xt), "val_macro_f1": f1})
        if f1 > best:
            best, best_state = f1, {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
        log(f"  epoch {epoch + 1:2d}/{cfg.epochs}  loss {loss_sum / len(xt):.3f}  val macro-F1 {f1:.3f}  "
            f"({time.time() - t:.0f} s)")
    model.load_state_dict(best_state)
    return {"model": model, "config": asdict(cfg), "absolute_ref_db": ref, "history": history,
            "n_parameters": n_parameters(model), "device": device}


def save(fitted: dict, path) -> None:
    keep = {k: v for k, v in fitted.items() if k not in ("model", "device")}
    keep["artifact_version"] = 1
    keep["metadata_fingerprint"] = _metadata_fingerprint(keep)
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    torch.save({"state": fitted["model"].state_dict(), **keep}, temporary)
    temporary.replace(path)


def _metadata_fingerprint(artifact: dict) -> str:
    return fingerprint({"config": artifact["config"], "provenance": artifact.get("provenance"),
                        "absolute_ref_db": artifact["absolute_ref_db"]})


def load(path, device: str | None = None, expected_config: TrainConfig | dict | None = None,
         expected_provenance: dict | None = None) -> dict:
    """Load a trusted local checkpoint, optionally enforcing experiment compatibility.

    Existing checkpoints remain readable without expectations. Reuse with provenance
    requirements deliberately rejects legacy checkpoints that cannot establish identity.
    """
    ck = torch.load(path, map_location="cpu", weights_only=True)
    if ck.get("artifact_version") is not None:
        if ck["artifact_version"] != 1 or ck.get("metadata_fingerprint") != _metadata_fingerprint(ck):
            raise ValueError("checkpoint artifact metadata is invalid or has changed")
    if expected_config is not None:
        config = asdict(expected_config) if isinstance(expected_config, TrainConfig) else expected_config
        if fingerprint(ck["config"]) != fingerprint(config):
            raise ValueError("checkpoint training configuration does not match this experiment")
    if expected_provenance is not None:
        if "provenance" not in ck or fingerprint(ck["provenance"]) != fingerprint(expected_provenance):
            raise ValueError("checkpoint provenance does not match this experiment's data")
    cfg = TrainConfig(**ck["config"])
    device = device or ("cuda" if torch.cuda.is_available() else "cpu")
    model = SmallResNet(len(cfg.labels), cfg.width).to(device)
    model.load_state_dict(ck.pop("state"))
    return {"model": model, "device": device, **ck}


def run(fitted: dict, d: dict) -> np.ndarray:
    cfg = TrainConfig(**{**fitted["config"], "labels": tuple(fitted["config"]["labels"])})
    return predict(fitted["model"], _inputs(d, cfg, fitted["absolute_ref_db"]), fitted["device"])


@torch.no_grad()
def infer(fitted: dict, d: dict, batch: int = 64) -> dict:
    """Return known-class logits and embeddings using the checkpoint's normalization."""
    if isinstance(batch, bool) or not isinstance(batch, int) or batch < 1:
        raise ValueError("batch must be a positive integer")
    cfg = TrainConfig(**fitted["config"])
    x = _inputs(d, cfg, fitted["absolute_ref_db"])
    model = fitted["model"].eval()
    logits, embeddings = [], []
    for start in range(0, len(x), batch):
        features = model.embed(x[start:start + batch].to(fitted["device"]))
        embeddings.append(features.cpu())
        logits.append(model.head(features).cpu())
    return {"logits": torch.cat(logits).numpy(), "embedding": torch.cat(embeddings).numpy()}

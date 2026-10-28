"""Training loop, prediction helpers, and the closed-set loss and score.

Three things a learner usually gets wrong, and how this file handles them:

* Eval mode. BatchNorm uses running statistics and Dropout is disabled only
  after model.eval(). Validation and every predict_* call switch to eval,
  then restore the previous mode, so the next epoch still trains normally.
  Forgetting eval() makes predictions depend on batch composition and on
  random dropout masks.

* Best-state restore. model.state_dict() returns references to the live
  parameter tensors, and the optimizer keeps updating them in place. A
  "best" state stored as a reference would silently become the last epoch,
  so the checkpoint is a deep copy.

* The -1 outlier convention. Outliers flow through the DataLoader like any
  other sample. The loss function decides what to do with them: ce_loss
  ignores them, and the Objectosphere loss in openset.py uses them.

Leakage: val_ds drives model selection only. It never produces gradients,
and the scores computed on it are not used to set thresholds. Thresholds
come from known val-calib data, handled in the experiment code.
"""

from __future__ import annotations

import copy
import math
import random
from dataclasses import dataclass
from typing import Callable

import numpy as np
import torch
import torch.nn.functional as F
from torch import nn
from torch.utils.data import DataLoader, Dataset

LossFn = Callable[[nn.Module, torch.Tensor, torch.Tensor], torch.Tensor]
ScoreFn = Callable[[nn.Module, Dataset], float]


def set_seed(seed: int) -> None:
    """Seed Python, NumPy and torch. This resets the global RNG state."""
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)


@dataclass
class TrainConfig:
    epochs: int = 20
    lr: float = 1e-3
    weight_decay: float = 1e-4  # L2 penalty applied through Adam
    batch_size: int = 64
    patience: int = 5  # epochs without validation gain before stopping
    seed: int = 0


def train_model(
    model: nn.Module,
    train_ds: Dataset,
    val_ds: Dataset,
    loss_fn: LossFn,
    cfg: TrainConfig,
    val_score_fn: ScoreFn,
) -> dict:
    """Train with Adam, keep the best validation state, and stop early.

    Returns a history dict with 'train_loss' and 'val_score' (one entry per
    completed epoch) and 'best_epoch' (0-based index of the restored state).
    On return the model holds the best state and is in eval mode.
    """
    if cfg.epochs < 1:
        raise ValueError("cfg.epochs must be >= 1")
    set_seed(cfg.seed)
    opt = torch.optim.Adam(model.parameters(), lr=cfg.lr, weight_decay=cfg.weight_decay)
    loader = DataLoader(train_ds, batch_size=cfg.batch_size, shuffle=True)

    history: dict = {"train_loss": [], "val_score": [], "best_epoch": -1}
    best_score = -math.inf
    best_state: dict | None = None
    epochs_without_gain = 0

    for epoch in range(cfg.epochs):
        model.train()  # dropout on, BatchNorm uses batch statistics
        loss_sum, n_seen = 0.0, 0
        for x, y in loader:
            loss = loss_fn(model, x, y)  # y may hold -1; loss_fn decides
            if not torch.isfinite(loss):
                raise FloatingPointError(f"non-finite training loss at epoch {epoch}")
            opt.zero_grad()
            loss.backward()
            opt.step()
            loss_sum += float(loss.detach()) * len(y)
            n_seen += len(y)
        history["train_loss"].append(loss_sum / n_seen)

        model.eval()  # deterministic validation: no dropout, BatchNorm uses running stats
        score = float(val_score_fn(model, val_ds))
        if not math.isfinite(score):
            raise ValueError(f"val_score_fn returned a non-finite value at epoch {epoch}")
        history["val_score"].append(score)

        if score > best_score:  # strict '>' keeps the earliest of tied epochs
            best_score = score
            history["best_epoch"] = epoch
            best_state = copy.deepcopy(model.state_dict())  # copy, not reference
            epochs_without_gain = 0
        else:
            epochs_without_gain += 1
            if epochs_without_gain >= cfg.patience:
                break

    assert best_state is not None  # epoch 0 always sets it, since scores are finite
    model.load_state_dict(best_state)
    model.eval()
    return history


def _to_float_tensor(x: torch.Tensor | np.ndarray) -> torch.Tensor:
    if isinstance(x, np.ndarray):
        return torch.as_tensor(np.asarray(x, dtype=np.float32))
    return x.to(torch.float32)


@torch.no_grad()
def _predict(model: nn.Module, x, batch_size: int, fn, out_dim: int) -> np.ndarray:
    """Run fn over x in chunks in eval mode, then restore the previous mode."""
    x = _to_float_tensor(x)
    was_training = model.training
    model.eval()  # eval() is required: Dropout off, BatchNorm running stats
    try:
        if len(x) == 0:
            return np.zeros((0, out_dim), dtype=np.float32)
        chunks = [fn(x[i : i + batch_size]) for i in range(0, len(x), batch_size)]
        return torch.cat(chunks).numpy()
    finally:
        model.train(was_training)


def predict_logits(
    model: nn.Module,
    x: torch.Tensor | np.ndarray,
    batch_size: int = 512,
) -> np.ndarray:
    """Logits for (N, 2, L) input as a float32 array of shape (N, C)."""
    return _predict(model, x, batch_size, model, model.fc.out_features)


def predict_embeddings(
    model: nn.Module,
    x: torch.Tensor | np.ndarray,
    batch_size: int = 512,
) -> np.ndarray:
    """Penultimate embeddings for (N, 2, L) input as a float32 array (N, D)."""
    return _predict(model, x, batch_size, model.embed, model.embed_dim)


def ce_loss(model: nn.Module, x: torch.Tensor, y: torch.Tensor) -> torch.Tensor:
    """Cross entropy over known samples (y >= 0). Outliers (y == -1) are ignored.

    With no known samples in the batch the result is 0. It still comes from
    the logits, so backward() works and the graph stays connected.
    """
    logits = model(x)
    known = y >= 0
    if not bool(known.any()):
        return logits.sum() * 0.0
    return F.cross_entropy(logits[known], y[known])


def accuracy_val_score(model: nn.Module, val_ds: Dataset) -> float:
    """Closed-set accuracy on known validation samples (label >= 0).

    This is the model-selection score. Outliers are excluded because the
    closed-set classifier has no notion of an unknown class. Raises if the
    validation set has no known samples, since a silent 0.0 would mislead
    model selection.
    """
    correct, total = 0, 0
    for xb, yb in DataLoader(val_ds, batch_size=512, shuffle=False):
        yb_np = yb.numpy()
        known = yb_np >= 0
        if not known.any():
            continue
        pred = predict_logits(model, xb).argmax(axis=1)
        correct += int((pred[known] == yb_np[known]).sum())
        total += int(known.sum())
    if total == 0:
        raise ValueError("validation set has no known-class samples (label >= 0)")
    return correct / total

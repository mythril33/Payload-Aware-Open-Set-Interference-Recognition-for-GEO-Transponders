"""Training loop, prediction helpers and closed-set loss/score checks.

Datasets here are random tensors wrapped in TensorDataset. They have no
dependency on the simulator, so a failure points at the training code.
"""

from __future__ import annotations

import copy
import random

import numpy as np
import pytest
import torch
import torch.nn.functional as F
from torch import nn
from torch.utils.data import TensorDataset

from rfml.models import CNN1D, MLP
from rfml.train import (
    TrainConfig,
    accuracy_val_score,
    ce_loss,
    predict_embeddings,
    predict_logits,
    set_seed,
    train_model,
)


class _Scripted:
    """val_score_fn that returns a fixed score per epoch and records the weights.

    The snapshot taken at epoch e is the state that the score was computed on,
    so it is the exact checkpoint that best-state restore should return.
    """

    def __init__(self, scores: list[float]) -> None:
        self.scores = list(scores)
        self.snapshots: list[dict] = []

    def __call__(self, model: nn.Module, ds) -> float:
        self.snapshots.append(copy.deepcopy(model.state_dict()))
        return self.scores[len(self.snapshots) - 1]


def _separable_split(n: int, L: int, seed: int) -> TensorDataset:
    """Two classes whose mean on channel 0 is +1 or -1, plus noise. Linearly separable."""
    g = torch.Generator().manual_seed(seed)
    y = torch.arange(n) % 2
    x = torch.randn(n, 2, L, generator=g) * 0.5
    x[:, 0, :] += torch.where(y == 1, -1.0, 1.0).unsqueeze(1)
    return TensorDataset(x, y.long())


def test_set_seed_makes_torch_and_numpy_repeatable() -> None:
    set_seed(7)
    a = (torch.rand(3), np.random.rand(3), random.random())
    set_seed(7)
    b = (torch.rand(3), np.random.rand(3), random.random())
    assert torch.equal(a[0], b[0])
    assert np.array_equal(a[1], b[1])
    assert a[2] == b[2]


def test_train_reaches_high_val_accuracy_on_separable_toy_problem() -> None:
    torch.manual_seed(0)
    L = 16
    train_ds = _separable_split(200, L, seed=1)
    val_ds = _separable_split(100, L, seed=2)
    model = MLP(2, n_samples=L, hidden=(8,), dropout=0.0)
    cfg = TrainConfig(epochs=10, lr=1e-2, batch_size=32, patience=10, seed=0)

    history = train_model(model, train_ds, val_ds, ce_loss, cfg, accuracy_val_score)

    assert max(history["val_score"]) >= 0.9
    # The returned model holds the best weights, so re-scoring it reproduces the best epoch.
    assert accuracy_val_score(model, val_ds) == pytest.approx(
        history["val_score"][history["best_epoch"]]
    )
    assert history["train_loss"][-1] < history["train_loss"][0]


def test_history_lengths_and_best_epoch_are_recorded() -> None:
    torch.manual_seed(0)
    train_ds = _separable_split(32, 8, seed=3)
    val_ds = _separable_split(16, 8, seed=4)
    model = MLP(2, n_samples=8, hidden=(4,), dropout=0.0)
    scores = [0.5, 0.9, 0.8, 0.7, 0.6]
    cfg = TrainConfig(epochs=5, lr=1e-3, batch_size=16, patience=10)

    history = train_model(model, train_ds, val_ds, ce_loss, cfg, _Scripted(scores))

    assert len(history["train_loss"]) == 5
    assert len(history["val_score"]) == 5
    assert history["val_score"] == scores
    assert history["best_epoch"] == 1  # index of the 0.9 score, not a count


def test_early_stopping_after_patience_epochs_without_gain() -> None:
    torch.manual_seed(0)
    train_ds = _separable_split(32, 8, seed=5)
    val_ds = _separable_split(16, 8, seed=6)
    model = MLP(2, n_samples=8, hidden=(4,), dropout=0.0)
    # Best is at epoch 1. Epochs 2 and 3 fail to beat it, which exhausts patience=2.
    scores = [0.5, 0.6, 0.55, 0.54, 0.53, 0.52]
    cfg = TrainConfig(epochs=6, lr=1e-3, batch_size=16, patience=2)

    history = train_model(model, train_ds, val_ds, ce_loss, cfg, _Scripted(scores))

    assert len(history["val_score"]) == 4
    assert len(history["train_loss"]) == 4
    assert history["best_epoch"] == 1


def test_best_weights_are_restored_not_last_epoch_weights() -> None:
    # Best is epoch 1, after which the weights keep changing. Without a deep
    # copy, the "best" state would alias the live tensors, and this test
    # would show the last epoch's weights instead.
    torch.manual_seed(0)
    train_ds = _separable_split(64, 32, seed=7)
    val_ds = _separable_split(32, 32, seed=8)
    model = CNN1D(2, width=4)  # has BatchNorm, so running stats must be restored too
    scores = [0.6, 0.95, 0.7, 0.65, 0.6]
    cfg = TrainConfig(epochs=5, lr=1e-2, batch_size=16, patience=10)
    scripted = _Scripted(scores)

    history = train_model(model, train_ds, val_ds, ce_loss, cfg, scripted)

    best = history["best_epoch"]
    assert best == 1
    final = model.state_dict()
    checkpoint = scripted.snapshots[best]
    assert set(final) == set(checkpoint)
    for key in checkpoint:
        assert torch.equal(final[key], checkpoint[key]), key
    # Sanity: the last epoch really did differ, so the equality above is meaningful.
    last = scripted.snapshots[-1]
    assert any(not torch.equal(final[k], last[k]) for k in final if final[k].is_floating_point())


def test_train_rejects_zero_epochs() -> None:
    ds = _separable_split(8, 8, seed=9)
    model = MLP(2, n_samples=8, hidden=(4,))
    with pytest.raises(ValueError, match="epochs"):
        train_model(model, ds, ds, ce_loss, TrainConfig(epochs=0), _Scripted([]))


def test_predict_restores_training_mode_and_is_batch_size_invariant() -> None:
    torch.manual_seed(0)
    model = MLP(3, n_samples=16, hidden=(8,), dropout=0.5)
    x = torch.randn(10, 2, 16)
    model.train()
    logits_small = predict_logits(model, x, batch_size=3)
    assert model.training  # the previous mode is restored after predicting
    logits_big = predict_logits(model, x.numpy(), batch_size=512)
    assert logits_small.shape == (10, 3) and logits_small.dtype == np.float32
    # Batch size must not change the output. Dropout is off in eval mode, so
    # chunking cannot change which units are dropped.
    np.testing.assert_allclose(logits_small, logits_big, rtol=1e-5, atol=1e-6)


def test_predict_embeddings_shape_and_empty_input() -> None:
    model = CNN1D(3, width=4)
    emb = predict_embeddings(model, torch.randn(5, 2, 32))
    assert emb.shape == (5, 16)
    empty = predict_embeddings(model, np.zeros((0, 2, 32), dtype=np.float32))
    assert empty.shape == (0, 16)
    empty_logits = predict_logits(model, np.zeros((0, 2, 32), dtype=np.float32))
    assert empty_logits.shape == (0, 3)


def test_ce_loss_ignores_outliers() -> None:
    torch.manual_seed(0)
    model = MLP(3, n_samples=8, hidden=(6,), dropout=0.0)  # no dropout: deterministic
    x = torch.randn(6, 2, 8)
    y = torch.tensor([0, -1, 2, -1, 1, -1])
    known = y >= 0
    logits = model(x)
    expected = F.cross_entropy(logits[known], y[known])
    got = ce_loss(model, x, y)
    assert torch.allclose(got, expected, atol=1e-6)


def test_ce_loss_all_outliers_is_finite_zero_and_backprops() -> None:
    torch.manual_seed(0)
    model = MLP(3, n_samples=8, hidden=(6,), dropout=0.0)
    x = torch.randn(4, 2, 8)
    y = torch.full((4,), -1, dtype=torch.long)
    loss = ce_loss(model, x, y)
    assert loss.dim() == 0
    assert torch.isfinite(loss)
    assert float(loss.detach()) == 0.0
    loss.backward()  # graph must stay connected even though the value is 0
    assert all(torch.isfinite(p.grad).all() for p in model.parameters() if p.grad is not None)


class _MeanModel(nn.Module):
    """Logits are the per-channel means of the input. Gives known answers for metric tests."""

    def __init__(self) -> None:
        super().__init__()
        self.embed_dim = 2
        self.fc = nn.Linear(2, 2)  # only out_features is read by predict_logits

    def embed(self, x: torch.Tensor) -> torch.Tensor:
        return x.mean(dim=-1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.embed(x)


def test_accuracy_val_score_counts_known_samples_only() -> None:
    def frame(channel0: float, channel1: float) -> torch.Tensor:
        x = torch.zeros(2, 4)
        x[0] = channel0
        x[1] = channel1
        return x

    # Argmax over the means picks class 0 when channel 0 is larger.
    # Known: 2 correct of 4 => 0.5. The outlier (-1) would be wrong if counted,
    # so the result stays 0.5 only if it is excluded.
    xs = torch.stack([
        frame(1.0, 0.0),  # label 0 -> pred 0, correct
        frame(0.0, 1.0),  # label 0 -> pred 1, wrong
        frame(0.0, 1.0),  # label 1 -> pred 1, correct
        frame(1.0, 0.0),  # label 1 -> pred 0, wrong
        frame(0.0, 1.0),  # outlier, excluded
    ])
    ys = torch.tensor([0, 0, 1, 1, -1])
    score = accuracy_val_score(_MeanModel(), TensorDataset(xs, ys))
    assert score == pytest.approx(0.5)


def test_accuracy_val_score_raises_without_known_samples() -> None:
    xs = torch.randn(3, 2, 4)
    ys = torch.full((3,), -1, dtype=torch.long)
    with pytest.raises(ValueError, match="no known-class"):
        accuracy_val_score(_MeanModel(), TensorDataset(xs, ys))

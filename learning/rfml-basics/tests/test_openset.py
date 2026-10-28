"""Checks for open-set scores, the Objectosphere loss, threshold calibration and metrics.

The metric tests live in this file because no separate test_metrics.py is
assigned. Each check uses either a hand-computed value or an independent
brute-force computation, not the function under test.
"""

from __future__ import annotations

import json
import math

import numpy as np
import pytest
import torch
import torch.nn.functional as F

from rfml.metrics import accuracy, auroc, confusion_matrix, open_set_report
from rfml.openset import (
    calibrate_threshold,
    class_centroids,
    distance_unknown_score,
    msp_unknown_score,
    objectosphere_loss,
    softmax_np,
)


# --------------------------------------------------------------------------- softmax / MSP


def test_softmax_rows_sum_to_one_and_match_naive_formula() -> None:
    rng = np.random.default_rng(0)
    logits = rng.normal(size=(6, 4))
    naive = np.exp(logits) / np.exp(logits).sum(axis=1, keepdims=True)
    p = softmax_np(logits)
    np.testing.assert_allclose(p.sum(axis=1), 1.0, rtol=1e-12)
    np.testing.assert_allclose(p, naive, rtol=1e-10, atol=1e-12)


def test_softmax_is_stable_for_large_logits() -> None:
    # Naive exp(1000) overflows to inf and gives NaN. Shifting by the row max keeps it finite.
    p = softmax_np(np.array([[1000.0, 1001.0, 1002.0]]))
    assert np.all(np.isfinite(p))
    np.testing.assert_allclose(p, softmax_np(np.array([[0.0, 1.0, 2.0]])), rtol=1e-12)


def test_msp_score_range_and_limits() -> None:
    rng = np.random.default_rng(1)
    C = 4
    scores = msp_unknown_score(rng.normal(scale=3.0, size=(200, C)))
    assert scores.shape == (200,)
    assert np.all(scores >= 0.0)
    assert np.all(scores <= 1.0 - 1.0 / C + 1e-12)

    # A confident one-hot-like logit means the classifier is sure, so the unknown score is near 0.
    assert msp_unknown_score(np.array([[50.0, 0.0, 0.0, 0.0]]))[0] < 1e-9
    # A flat logit is maximally uncertain, so the score attains the upper bound 1 - 1/C.
    np.testing.assert_allclose(msp_unknown_score(np.zeros((1, C))), 1.0 - 1.0 / C, rtol=1e-12)


# --------------------------------------------------------------------------- centroids / distance


def test_class_centroids_ignore_outliers() -> None:
    emb = np.array([
        [1.0, 1.0],
        [3.0, 1.0],   # class 0 mean -> (2, 1)
        [-2.0, 4.0],
        [-4.0, 6.0],  # class 1 mean -> (-3, 5)
        [1e6, -1e6],  # outlier: must not move any centroid
    ])
    labels = np.array([0, 0, 1, 1, -1])
    cent = class_centroids(emb, labels, n_classes=2)
    np.testing.assert_allclose(cent, np.array([[2.0, 1.0], [-3.0, 5.0]]))


def test_class_centroids_raise_when_a_known_class_is_missing() -> None:
    emb = np.zeros((3, 2))
    labels = np.array([0, 0, -1])  # class 1 never appears among known samples
    with pytest.raises(ValueError, match=r"\[1\]"):
        class_centroids(emb, labels, n_classes=2)


def test_distance_is_zero_at_centroid_and_matches_bruteforce() -> None:
    rng = np.random.default_rng(2)
    cent = rng.normal(size=(3, 5))
    emb = rng.normal(size=(12, 5))
    # Exact zero at a centroid is what the direct-difference formula gives.
    # The expansion |a|^2 - 2ab + |b|^2 could leave a tiny residual.
    got_at_centroid = distance_unknown_score(cent[[1]], cent)
    assert got_at_centroid[0] == 0.0

    got = distance_unknown_score(emb, cent)
    brute = np.array([min(math.dist(e, c) for c in cent) for e in emb])
    np.testing.assert_allclose(got, brute, rtol=1e-12, atol=1e-12)
    assert np.all(got >= 0.0)


# --------------------------------------------------------------------------- Objectosphere


def test_objectosphere_is_finite_for_known_outlier_and_mixed_batches() -> None:
    torch.manual_seed(0)
    logits = torch.randn(8, 4) * 5
    known_only = torch.tensor([0, 1, 2, 3, 0, 1, 2, 3])
    outlier_only = torch.full((8,), -1, dtype=torch.long)
    mixed = torch.tensor([0, -1, 2, -1, 1, -1, 3, -1])
    for labels in (known_only, outlier_only, mixed):
        loss = objectosphere_loss(logits.clone().requires_grad_(True), labels)
        assert loss.dim() == 0
        assert torch.isfinite(loss)


def test_objectosphere_hand_computed_value() -> None:
    # Sample A: label 0, logits [3, 4]. Norm 5, which is below xi=10.
    #   CE = -log softmax_0 = 1 + log(1 + e^-1), penalty = 0.1 * (10 - 5)^2 = 2.5.
    # Sample B: outlier, logits [0, 0]. Uniform CE = log 2, norm penalty 0.
    # Total = (A + B) / batch size 2.
    logits = torch.tensor([[3.0, 4.0], [0.0, 0.0]])
    labels = torch.tensor([0, -1])
    expected = (1.0 + math.log(1.0 + math.exp(-1.0)) + 2.5 + math.log(2.0)) / 2.0
    got = objectosphere_loss(logits, labels, xi=10.0, lam=0.1)
    assert float(got) == pytest.approx(expected, rel=1e-6)


def test_objectosphere_known_magnitude_term_vanishes_above_xi() -> None:
    logits = torch.tensor([[10.0, 0.0, 0.0], [0.0, 25.0, 0.0]])  # norms 10 and 25, both >= xi
    labels = torch.tensor([0, 1])
    got = objectosphere_loss(logits, labels, xi=10.0, lam=0.1)
    assert float(got) == pytest.approx(float(F.cross_entropy(logits, labels)), rel=1e-6)


def test_objectosphere_known_penalty_grows_as_magnitude_shrinks() -> None:
    direction = torch.tensor([1.0, 0.0, 0.0])
    labels = torch.tensor([0])

    def penalty(scale: float) -> float:
        # Isolate the magnitude term: the CE part does not depend on lam.
        z = (scale * direction).unsqueeze(0)
        with_lam = float(objectosphere_loss(z, labels, xi=10.0, lam=0.1))
        without = float(objectosphere_loss(z, labels, xi=10.0, lam=0.0))
        return with_lam - without

    p10, p8, p5, p2 = penalty(10.0), penalty(8.0), penalty(5.0), penalty(2.0)
    assert p10 == pytest.approx(0.0, abs=1e-7)
    assert 0.0 < p8 < p5 < p2


def test_objectosphere_outlier_term_small_when_uniform_and_small() -> None:
    labels = torch.full((1,), -1, dtype=torch.long)
    # For a 4-class outlier with logits s*[1,-1,0,0], the value is
    # log(2 cosh s + 2) + 0.1 * 2 s^2, which is strictly increasing in s >= 0.
    values = []
    for s in (0.0, 0.5, 1.0, 2.0):
        z = torch.tensor([[s, -s, 0.0, 0.0]])
        values.append(float(objectosphere_loss(z, labels, lam=0.1)))
    assert values[0] == pytest.approx(math.log(4.0), rel=1e-6)  # uniform, zero norm
    assert values == sorted(values)
    assert len(set(values)) == len(values)  # strictly increasing


def test_objectosphere_gradients_finite_at_zero_logits() -> None:
    # At zero logits the norm is non-differentiable. vector_norm returns a
    # zero subgradient there, so the optimizer still gets a finite gradient.
    logits = torch.zeros(3, 4, requires_grad=True)
    labels = torch.tensor([0, -1, 2])
    objectosphere_loss(logits, labels).backward()
    assert torch.isfinite(logits.grad).all()


def test_objectosphere_rejects_invalid_labels() -> None:
    logits = torch.zeros(2, 3)
    with pytest.raises(ValueError, match="-1"):
        objectosphere_loss(logits, torch.tensor([0, -2]))


# --------------------------------------------------------------------------- calibrate_threshold


@pytest.mark.parametrize("target", [0.5, 0.9, 0.95, 1.0])
def test_calibrated_threshold_meets_target_and_is_smallest(target: float) -> None:
    rng = np.random.default_rng(3)
    scores = rng.exponential(size=137)
    t = calibrate_threshold(scores, target_known_accept=target)
    frac = float(np.mean(scores <= t))
    assert frac >= target - 1e-12
    # Smallest: the next lower observed score must fall short of the target.
    lower = scores[scores < t]
    if lower.size:
        assert float(np.mean(scores <= lower.max())) < target


def test_calibrated_threshold_holds_with_ties() -> None:
    scores = np.array([1.0, 1.0, 1.0, 2.0, 2.0, 3.0])
    t50 = calibrate_threshold(scores, 0.5)
    assert t50 == 1.0 and np.mean(scores <= t50) >= 0.5
    t60 = calibrate_threshold(scores, 0.6)
    assert t60 == 2.0 and np.mean(scores <= t60) >= 0.6
    # All-equal scores: any target is met exactly at that value.
    assert calibrate_threshold(np.full(10, 4.2), 0.95) == 4.2


def test_calibrated_threshold_is_not_pushed_up_by_float_error() -> None:
    # 0.95 * 100 is 95.00000000000001 in floating point. The correct answer is
    # the 95th of 100 scores, not the 96th.
    scores = np.arange(1.0, 101.0)
    assert calibrate_threshold(scores, 0.95) == 95.0


def test_calibrate_threshold_rejects_bad_inputs() -> None:
    with pytest.raises(ValueError):
        calibrate_threshold(np.array([]), 0.9)
    with pytest.raises(ValueError):
        calibrate_threshold(np.array([1.0, np.nan]), 0.9)
    with pytest.raises(ValueError):
        calibrate_threshold(np.array([1.0]), 0.0)


# --------------------------------------------------------------------------- metrics: auroc


def _brute_auroc(pos: np.ndarray, neg: np.ndarray) -> float:
    wins = 0.0
    for p in pos:
        for n in neg:
            if p > n:
                wins += 1.0
            elif p == n:
                wins += 0.5
    return wins / (len(pos) * len(neg))


@pytest.mark.parametrize("seed", [0, 1, 2])
def test_auroc_matches_bruteforce_pair_count_with_ties(seed: int) -> None:
    rng = np.random.default_rng(seed)
    pos = rng.integers(0, 5, size=37).astype(float)  # small integer range => many ties
    neg = rng.integers(0, 5, size=53).astype(float)
    got = auroc(pos, neg)
    assert got == pytest.approx(_brute_auroc(pos, neg), abs=1e-12)


def test_auroc_perfect_separation_is_one() -> None:
    assert auroc(np.array([2.0, 3.0]), np.array([0.0, 1.0])) == 1.0
    assert auroc(np.array([0.0, 1.0]), np.array([2.0, 3.0])) == 0.0


def test_auroc_is_none_for_empty_inputs() -> None:
    assert auroc(np.array([]), np.array([1.0, 2.0])) is None
    assert auroc(np.array([1.0]), np.array([])) is None


def test_auroc_rejects_nan_scores() -> None:
    with pytest.raises(ValueError):
        auroc(np.array([np.nan]), np.array([1.0]))


# --------------------------------------------------------------------------- metrics: open-set report


def test_open_set_report_hand_example() -> None:
    known = np.array([0.1, 0.4, 0.6, 0.9])
    unknown = np.array([0.5, 0.7, 0.95])
    rep = open_set_report(known, unknown, threshold=0.6)
    assert rep["n_known"] == 4 and rep["n_unknown"] == 3
    # Known accepted (score <= 0.6): 0.1, 0.4, 0.6 => 3/4.
    assert rep["known_accept_rate"] == pytest.approx(3 / 4)
    # Unknown rejected (score > 0.6): 0.7, 0.95 => 2/3.
    assert rep["unknown_reject_rate"] == pytest.approx(2 / 3)
    # Pairs with unknown > known: 2 + 3 + 4 = 9 of 12 => 0.75.
    assert rep["auroc"] == pytest.approx(0.75)
    assert rep["threshold"] == 0.6
    assert set(rep) == {
        "n_known", "n_unknown", "known_accept_rate", "unknown_reject_rate", "auroc", "threshold",
    }


def test_open_set_report_uses_none_not_nan_for_empty_side() -> None:
    rep = open_set_report(np.array([0.2, 0.3]), np.array([]), threshold=0.25)
    assert rep["n_unknown"] == 0
    assert rep["unknown_reject_rate"] is None
    assert rep["auroc"] is None
    assert rep["known_accept_rate"] == pytest.approx(0.5)
    # allow_nan=False makes json raise on NaN or inf, so this checks strict JSON too.
    json.dumps(rep, allow_nan=False)

    empty = open_set_report(np.array([]), np.array([]), threshold=0.0)
    assert empty["known_accept_rate"] is None and empty["unknown_reject_rate"] is None
    json.dumps(empty, allow_nan=False)


def test_open_set_report_rejects_non_finite_threshold() -> None:
    with pytest.raises(ValueError):
        open_set_report(np.array([0.1]), np.array([0.9]), threshold=float("inf"))


# --------------------------------------------------------------------------- metrics: accuracy / confusion


def test_accuracy_is_none_on_empty_and_correct_otherwise() -> None:
    assert accuracy(np.array([], dtype=int), np.array([], dtype=int)) is None
    assert accuracy(np.array([0, 1, 1]), np.array([0, 1, 0])) == pytest.approx(2 / 3)


def test_confusion_matrix_rows_are_true_labels() -> None:
    pred = np.array([0, 1, 1, 2])
    labels = np.array([0, 0, 1, 2])
    cm = confusion_matrix(pred, labels, n_classes=3)
    assert cm.dtype == np.int64
    np.testing.assert_array_equal(cm, np.array([[1, 1, 0], [0, 1, 0], [0, 0, 1]]))
    # Row sums must equal the number of samples per true class.
    np.testing.assert_array_equal(cm.sum(axis=1), np.bincount(labels, minlength=3))


def test_confusion_matrix_rejects_out_of_range_labels() -> None:
    with pytest.raises(ValueError):
        confusion_matrix(np.array([0, 1]), np.array([0, -1]), n_classes=2)
    with pytest.raises(ValueError):
        confusion_matrix(np.array([0, 2]), np.array([0, 1]), n_classes=2)

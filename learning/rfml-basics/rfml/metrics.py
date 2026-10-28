"""Metrics for closed-set and open-set evaluation.

Conventions used everywhere in this file:
  * Unknown score: larger = more unknown-like.
  * Every rate names its positive class and denominator, and the report
    carries the counts that define the denominators.
  * Undefined values are None, never NaN, so the output stays strict JSON.
"""

from __future__ import annotations

import math

import numpy as np


def _finite_1d(values: np.ndarray, name: str) -> np.ndarray:
    arr = np.asarray(values, dtype=np.float64).ravel()
    if not np.all(np.isfinite(arr)):
        raise ValueError(f"{name} contains NaN or inf")
    return arr


def accuracy(pred: np.ndarray, labels: np.ndarray) -> float | None:
    """Fraction of pred == labels. None when there are no samples."""
    pred = np.asarray(pred)
    labels = np.asarray(labels)
    if pred.shape != labels.shape:
        raise ValueError(f"shape mismatch: pred {pred.shape} vs labels {labels.shape}")
    if pred.size == 0:
        return None
    return float(np.mean(pred == labels))


def auroc(scores_positive: np.ndarray, scores_negative: np.ndarray) -> float | None:
    """Area under the ROC curve via the Mann-Whitney U statistic.

    AUROC = P(s_pos > s_neg) + 0.5 * P(s_pos == s_neg), over all pairs.
    Positive class = unknown, and larger score = more unknown-like. Returns
    None if either side is empty, because the statistic is undefined there.
    """
    pos = _finite_1d(scores_positive, "scores_positive")
    neg = _finite_1d(scores_negative, "scores_negative")
    if pos.size == 0 or neg.size == 0:
        return None
    # Sorting the negatives lets each positive be ranked with two binary
    # searches, so the cost is O((n+m) log m) rather than the O(n*m) pair loop.
    neg_sorted = np.sort(neg)
    n_below = np.searchsorted(neg_sorted, pos, side="left")  # negatives < s_pos
    n_not_above = np.searchsorted(neg_sorted, pos, side="right")  # negatives <= s_pos
    wins = n_below.sum() + 0.5 * (n_not_above - n_below).sum()  # ties count as half
    return float(wins / (pos.size * neg.size))


def open_set_report(
    known_scores: np.ndarray,
    unknown_scores: np.ndarray,
    threshold: float,
) -> dict:
    """Summarise an open-set decision at a fixed threshold.

    Acceptance rule: a sample is accepted as known if score <= threshold, and
    rejected as unknown if score > threshold.

    known_accept_rate: positive class = known,   denominator = n_known.
    unknown_reject_rate: positive class = unknown, denominator = n_unknown.
    auroc: positive class = unknown (larger score = more unknown-like).
    """
    t = float(threshold)
    if not math.isfinite(t):
        raise ValueError("threshold must be finite for strict JSON output")
    known = _finite_1d(known_scores, "known_scores")
    unknown = _finite_1d(unknown_scores, "unknown_scores")
    n_known, n_unknown = int(known.size), int(unknown.size)
    return {
        "n_known": n_known,
        "n_unknown": n_unknown,
        "known_accept_rate": float(np.mean(known <= t)) if n_known else None,
        "unknown_reject_rate": float(np.mean(unknown > t)) if n_unknown else None,
        "auroc": auroc(unknown, known),
        "threshold": t,
    }


def confusion_matrix(pred: np.ndarray, labels: np.ndarray, n_classes: int) -> np.ndarray:
    """int64 (C, C) matrix: rows = true label, cols = predicted label."""
    pred = np.asarray(pred, dtype=np.int64).ravel()
    labels = np.asarray(labels, dtype=np.int64).ravel()
    if pred.shape != labels.shape:
        raise ValueError(f"shape mismatch: pred {pred.shape} vs labels {labels.shape}")
    for name, arr in (("pred", pred), ("labels", labels)):
        # -1 (outlier/unknown) is not a valid column here. Failing loudly is
        # better than silently dropping samples from the matrix.
        if arr.size and (arr.min() < 0 or arr.max() >= n_classes):
            raise ValueError(f"{name} must lie in [0, {n_classes})")
    flat = labels * n_classes + pred
    return np.bincount(flat, minlength=n_classes * n_classes).reshape(n_classes, n_classes).astype(np.int64)

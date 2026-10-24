"""Metrics for stage A (P7 §2). NumPy only."""
from __future__ import annotations

import numpy as np


def confusion(y_true: np.ndarray, y_pred: np.ndarray, n: int) -> np.ndarray:
    m = np.zeros((n, n), int)
    np.add.at(m, (y_true, y_pred), 1)
    return m


def macro_f1(y_true: np.ndarray, y_pred: np.ndarray, n: int) -> float:
    m = confusion(y_true, y_pred, n)
    tp = np.diag(m).astype(float)
    denom = m.sum(0) + m.sum(1)
    present = m.sum(1) > 0                          # classes absent from y_true do not count
    return float(np.mean(np.where(denom > 0, 2 * tp / np.maximum(denom, 1), 0.0)[present]))


def cluster_ci(values: np.ndarray, groups: np.ndarray, n_boot: int = 2000, seed: int = 0) -> tuple:
    """95 % bootstrap interval of the mean, resampling whole groups (scenario seeds), not samples.

    Samples of one seed share the plan and the noise, so they are not independent.
    """
    ids, inv = np.unique(groups, return_inverse=True)
    sums = np.bincount(inv, weights=values, minlength=len(ids))
    counts = np.bincount(inv, minlength=len(ids))
    rng = np.random.default_rng(seed)
    pick = rng.integers(0, len(ids), size=(n_boot, len(ids)))
    means = sums[pick].sum(1) / counts[pick].sum(1)
    lo, hi = np.percentile(means, [2.5, 97.5])
    return float(lo), float(hi)


CLEAN_ALARM_QUANTILE_METHOD = "higher"


def clean_alarm_threshold(clean_scores: np.ndarray, pfa: float) -> float:
    """Approved R10 clean-alarm threshold: the higher empirical quantile at level 1 - pfa.

    The alarm rule is applied by the caller as strictly ``score > threshold``. Inputs must be a
    non-empty finite vector of clean known-only calibration scores; anything else is refused.
    Used by the E9 calibrate path only (src/geoml/b2_execution.py).
    """
    values = np.asarray(clean_scores, dtype=float)
    if values.ndim != 1 or values.size == 0:
        raise ValueError("clean calibration scores must be a non-empty one-dimensional vector")
    if not np.all(np.isfinite(values)):
        raise ValueError("clean calibration scores must be finite")
    if isinstance(pfa, (bool, np.bool_)) or not isinstance(pfa, (int, float, np.floating)) or not 0.0 < float(pfa) < 1.0:
        raise ValueError("pfa must be a number in (0, 1)")
    return float(np.quantile(values, 1.0 - float(pfa), method=CLEAN_ALARM_QUANTILE_METHOD))


def threshold_at_pfa(clean_scores: np.ndarray, pfa: float) -> float:
    """HISTORICAL linear-quantile threshold used by frozen stages (stage A, R1, A5, observed receiver, legacy coupled path).

    Kept bit-for-bit so that archived results keep their meaning. It is NOT the approved R10 rule;
    the E9 calibrate path uses ``clean_alarm_threshold``.
    """
    return float(np.quantile(clean_scores, 1 - pfa))


def expected_calibration_error(probs: np.ndarray, labels: np.ndarray, n_bins: int = 15) -> dict:
    """Top-label ECE with equal-width confidence bins (Guo et al., 2017).

    Bin b covers (lo, hi]; the first bin also includes 0. ECE is the
    sample-weighted mean of |accuracy - mean confidence| over nonempty bins.
    Empty bins report null accuracy and confidence with a zero count.
    """
    probs, labels = np.asarray(probs, float), np.asarray(labels)
    if probs.ndim != 2 or not len(probs) or labels.shape != (len(probs),) or not np.isfinite(probs).all():
        raise ValueError("probs must be a finite nonempty (N, K) array with one label per row")
    if isinstance(n_bins, bool) or not isinstance(n_bins, int) or n_bins < 1:
        raise ValueError("n_bins must be a positive integer")
    confidence, correct = probs.max(1), probs.argmax(1) == labels
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    index = np.clip(np.searchsorted(edges, confidence, side="left") - 1, 0, n_bins - 1)
    bins, ece = [], 0.0
    for b in range(n_bins):
        sel = index == b
        n = int(sel.sum())
        acc = float(correct[sel].mean()) if n else None
        conf = float(confidence[sel].mean()) if n else None
        if n:
            ece += n / len(probs) * abs(acc - conf)
        bins.append({"lo": float(edges[b]), "hi": float(edges[b + 1]), "n": n, "accuracy": acc, "confidence": conf})
    return {"ece": float(ece), "n_bins": n_bins, "n_samples": int(len(probs)), "bins": bins}

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


def threshold_at_pfa(clean_scores: np.ndarray, pfa: float) -> float:
    """Score threshold exceeded by a fraction `pfa` of the given clean (validation) scores."""
    return float(np.quantile(clean_scores, 1 - pfa))

"""Threshold-independent open-set ranking metrics, with explicit score ties.

Unknown scores are larger for more unknown-like events. Unknown is the positive
population for ROC and precision/recall. ``unknown_aupr`` is average precision
(a recall-weighted step integral), not trapezoidal area under the PR points.

OSCR accepts events from low to high unknown score. Its x axis is the fraction
of unknown test events falsely accepted as known; its y axis is the fraction of
*all* known test events both accepted and correctly classified. Incorrect known
predictions therefore reduce the curve's maximum height. Equal-score events
enter together. A mixed tie is represented by a straight line between its two
endpoints, so trapezoidal integration gives half credit within the tie.

These metrics describe ranking on a final test population. They do not select
the operating rejection threshold or estimate uncertainty across scenarios.
"""
from __future__ import annotations

import numpy as np


def _scores(values, name: str) -> np.ndarray:
    raw = np.asarray(values)
    if raw.dtype.kind not in "iuf" or raw.ndim != 1 or raw.size == 0:
        raise ValueError(f"{name} must be a nonempty finite real numeric vector")
    result = raw.astype(np.float64)
    if not np.isfinite(result).all():
        raise ValueError(f"{name} must contain only finite scores")
    return result


def _group_ends(ordered_scores: np.ndarray) -> np.ndarray:
    """Indices of the final item in each equal-score group."""
    return np.flatnonzero(np.r_[ordered_scores[1:] != ordered_scores[:-1], True])


def _trapezoid(y: np.ndarray, x: np.ndarray) -> float:
    # Keep compatibility with NumPy >=1.24, before np.trapezoid was introduced.
    return float(np.sum((x[1:] - x[:-1]) * (y[1:] + y[:-1]) * 0.5))


def ranking_metrics(known_scores: np.ndarray, unknown_scores: np.ndarray,
                    known_correct: np.ndarray) -> dict:
    """Return AUROC, average precision, OSCR AUC and their finite curve points.

    ``known_correct`` must contain one boolean per known event from the
    classifier's known-class argmax, *before* rejection. Known/unknown scores
    must come from the same scorer. Both populations must be nonempty.

    ROC/PR scan descending score (unknown positive); OSCR scans ascending score
    (accept as known). Each scan starts by accepting/detecting no events and
    ends with all events. Equal-score groups are processed as a single step,
    making every result invariant to permutations within tied groups.
    """
    known = _scores(known_scores, "known_scores")
    unknown = _scores(unknown_scores, "unknown_scores")
    correct = np.asarray(known_correct)
    if correct.dtype.kind != "b" or correct.shape != known.shape:
        raise ValueError("known_correct must be a boolean vector matching known_scores")
    nk, nu = len(known), len(unknown)
    scores = np.concatenate((known, unknown))
    is_unknown = np.r_[np.zeros(nk, dtype=bool), np.ones(nu, dtype=bool)]

    descending = np.argsort(scores, kind="stable")[::-1]
    ends = _group_ends(scores[descending])
    true_positive = np.cumsum(is_unknown[descending], dtype=np.int64)[ends]
    detected = ends + 1
    false_positive = detected - true_positive
    fpr = np.r_[0.0, false_positive / nk]
    tpr = np.r_[0.0, true_positive / nu]
    recall = tpr.copy()
    precision = np.r_[1.0, true_positive / detected]
    average_precision = float(np.sum(np.diff(recall) * precision[1:]))

    ascending = np.argsort(scores, kind="stable")
    ends = _group_ends(scores[ascending])
    is_correct_known = np.r_[correct, np.zeros(nu, dtype=bool)]
    false_acceptance = np.r_[0.0, np.cumsum(is_unknown[ascending], dtype=np.int64)[ends] / nu]
    correct_acceptance = np.r_[0.0, np.cumsum(is_correct_known[ascending], dtype=np.int64)[ends] / nk]

    return {
        "unknown_auroc": _trapezoid(tpr, fpr),
        "unknown_aupr": average_precision,
        "oscr_auc": _trapezoid(correct_acceptance, false_acceptance),
        "n_known": nk,
        "n_unknown": nu,
        "known_closed_accuracy": float(np.mean(correct)),
        "unknown_prevalence": nu / (nk + nu),
        "conventions": {
            "positive_population": "unknown",
            "unknown_score_direction": "higher_is_more_unknown_like",
            "unknown_aupr": "average_precision_step_integral",
            "ties": "equal_score_events_enter_together",
            "oscr_interpolation": "linear_between_grouped_tie_endpoints",
            "oscr_known_denominator": "all_known_test_events",
        },
        "curves": {
            "unknown_roc": {"fpr": fpr.tolist(), "tpr": tpr.tolist()},
            "unknown_pr": {"recall": recall.tolist(), "precision": precision.tolist()},
            "oscr": {"unknown_false_acceptance": false_acceptance.tolist(),
                     "known_correct_acceptance": correct_acceptance.tolist()},
        },
    }

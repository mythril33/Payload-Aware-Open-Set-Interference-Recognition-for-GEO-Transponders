"""Open-set scores, the Objectosphere loss and threshold calibration.

Open-set recognition asks for a score that is large for signals from classes
never seen in training. Three scores are compared here:
  * MSP: 1 - max softmax probability. Softmax is trained only to be confident
    on known classes, so it is a weak unknown detector.
  * Distance: min Euclidean distance from the embedding to a known-class
    centroid. Unknowns tend to land away from every centroid.
  * Objectosphere (Dhamija et al., 2018): a training loss that pushes known
    samples to large logit norms and outliers to small norms with a uniform
    softmax, so the two groups separate in logit space.

Thresholds are calibrated on KNOWN validation samples only (val-calib role).
Unknown classes never enter calibration, since that would leak the test
split into the decision rule.
"""

from __future__ import annotations

import math

import numpy as np
import torch
import torch.nn.functional as F


def softmax_np(logits: np.ndarray) -> np.ndarray:
    """Row-wise softmax over (N, C) logits.

    Subtracting the row max first keeps exp() from overflowing. The result is
    the same as the naive formula, but it also works for logits near 1000.
    """
    z = np.asarray(logits, dtype=np.float64)
    z = z - z.max(axis=1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(axis=1, keepdims=True)


def msp_unknown_score(logits: np.ndarray) -> np.ndarray:
    """1 - max softmax probability, shape (N,). Range [0, 1 - 1/C]."""
    return 1.0 - softmax_np(logits).max(axis=1)


def class_centroids(embeddings: np.ndarray, labels: np.ndarray, n_classes: int) -> np.ndarray:
    """Mean embedding of each known class, shape (C, D).

    Samples with label -1 (outliers) are excluded. Each known class must have
    at least one sample. A missing class would give a NaN centroid, which would
    then silently propagate into every distance, so raise instead.
    """
    emb = np.asarray(embeddings, dtype=np.float64)
    lab = np.asarray(labels, dtype=np.int64).ravel()
    if emb.shape[0] != lab.shape[0]:
        raise ValueError("embeddings and labels disagree on N")
    if lab.size and lab.max() >= n_classes:
        raise ValueError(f"label {int(lab.max())} >= n_classes={n_classes}")
    known = lab >= 0
    counts = np.bincount(lab[known], minlength=n_classes)
    missing = np.flatnonzero(counts == 0)
    if missing.size:
        raise ValueError(f"no known samples for classes {missing.tolist()}")
    sums = np.zeros((n_classes, emb.shape[1]), dtype=np.float64)
    np.add.at(sums, lab[known], emb[known])
    return sums / counts[:, None]


def distance_unknown_score(embeddings: np.ndarray, centroids: np.ndarray) -> np.ndarray:
    """Min Euclidean distance to any centroid, shape (N,). Larger = more unknown.

    The difference is computed directly rather than with the expansion
    |a|^2 - 2ab + |b|^2. The expansion can go slightly negative through
    cancellation, so it would not give an exact 0 at a centroid. It also
    materialises an (N, C, D) array, which is fine at this scale.
    """
    emb = np.asarray(embeddings, dtype=np.float64)
    cent = np.asarray(centroids, dtype=np.float64)
    diff = emb[:, None, :] - cent[None, :, :]
    return np.sqrt((diff * diff).sum(axis=-1)).min(axis=1)


def objectosphere_loss(
    logits: torch.Tensor,
    labels: torch.Tensor,
    xi: float = 10.0,
    lam: float = 0.1,
) -> torch.Tensor:
    """Objectosphere loss (Dhamija et al., 2018), averaged over the batch.

    Known samples (label >= 0):
        CE(logits, label) + lam * relu(xi - ||logits||)^2
        The magnitude term is zero once ||logits|| >= xi, so it pushes only
        small-norm known samples outward.
    Outlier samples (label == -1):
        -(1/C) * sum_c log_softmax_c + lam * ||logits||^2
        The first term is the cross entropy to a uniform target, which is
        minimal when the softmax is flat. The second shrinks the logits.

    Both parts are summed over the batch and divided by the batch size B
    (outliers included). A part with no samples contributes 0.
    """
    if logits.dim() != 2:
        raise ValueError(f"logits must be (B, C), got {tuple(logits.shape)}")
    if labels.dim() != 1 or labels.shape[0] != logits.shape[0]:
        raise ValueError("labels must be (B,) and match the logits batch size")
    if labels.numel() and int(labels.min()) < -1:
        raise ValueError("labels must be >= 0 (known) or -1 (outlier)")

    n_batch = labels.shape[0]
    if n_batch == 0:
        return logits.sum() * 0.0  # zero, but keeps the graph connected

    known = labels >= 0
    outlier = labels == -1
    log_p = F.log_softmax(logits, dim=1)
    norms = torch.linalg.vector_norm(logits, dim=1)  # ||logits||, safe grad at 0

    # gather() needs a valid index, so clamp the -1 outliers to class 0 and let
    # the mask discard that term.
    ce = -log_p.gather(1, labels.clamp(min=0).unsqueeze(1)).squeeze(1)
    known_term = ce + lam * F.relu(xi - norms) ** 2
    uniform_ce = -log_p.mean(dim=1)  # -(1/C) * sum_c log p_c
    outlier_term = uniform_ce + lam * norms**2

    # torch.where (not multiplication by a 0/1 mask) so that a non-finite value
    # in the unselected branch cannot leak NaN into the result.
    zero = torch.zeros_like(ce)
    total = torch.where(known, known_term, zero).sum() + torch.where(outlier, outlier_term, zero).sum()
    return total / n_batch


def calibrate_threshold(known_scores: np.ndarray, target_known_accept: float = 0.95) -> float:
    """Smallest t such that at least `target_known_accept` of known scores are <= t.

    Acceptance rule: accept if score <= t, reject as unknown if score > t.
    Calibration uses known-class validation scores only, so the threshold
    cannot depend on unknown classes.

    With ties, the chosen t is a score value, so every tied sample is counted
    together. The bound still holds: fraction(<= t) >= target.
    """
    if not (0.0 < target_known_accept <= 1.0):
        raise ValueError("target_known_accept must lie in (0, 1]")
    s = np.sort(np.asarray(known_scores, dtype=np.float64).ravel())
    if s.size == 0:
        raise ValueError("no known scores to calibrate on")
    if not np.all(np.isfinite(s)):
        raise ValueError("known_scores contains NaN or inf")
    # k = ceil(target * n) is the number of samples that must be accepted. The
    # 1e-9 guards against float error such as 0.07 * 100 = 7.000000000000001,
    # which would otherwise push the threshold one sample too high.
    k = int(math.ceil(target_known_accept * s.size - 1e-9))
    k = min(max(k, 1), s.size)
    return float(s[k - 1])

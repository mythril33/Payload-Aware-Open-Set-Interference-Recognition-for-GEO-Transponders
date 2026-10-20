"""Post-hoc unknown scores for known-class logits. NumPy only.

Larger values always mean more unknown-like. These scores do not establish that
an event has a new physical cause; a separate known-validation calibrator sets
the acceptance threshold. Embedding-based Mahalanobis scoring lives in the
separate ``mahalanobis`` module; training-time open-set methods remain future work.
"""
from __future__ import annotations

from numbers import Real

import numpy as np


METHODS = ("msp", "energy")


def _method_temperature(method: str, temperature: float) -> float:
    if not isinstance(method, str) or method not in METHODS:
        raise ValueError(f"unknown scoring method {method!r}; choose from {METHODS}")
    if isinstance(temperature, (bool, np.bool_)) or not isinstance(temperature, Real):
        raise ValueError("temperature must be a finite positive number")
    temperature = float(temperature)
    if not np.isfinite(temperature) or temperature <= 0:
        raise ValueError("temperature must be a finite positive number")
    return temperature


def unknown_scores(logits: np.ndarray, method: str, temperature: float = 1.0) -> np.ndarray:
    """Return one unknown score per row of finite ``[N, K]`` known-class logits.

    ``msp`` is ``1 - max(softmax(logits / temperature))``; ``energy`` is
    ``-temperature * logsumexp(logits / temperature)``. MSP is invariant to a
    shared offset in a row, while energy is not. The latter should not be
    compared between unrelated models without recalibration.

    Both N and K must be nonzero, with at least two known classes. Stable
    maximum subtraction avoids exponentiating large positive values. Results
    that cannot be represented as finite float64 values are rejected.
    """
    temperature = _method_temperature(method, temperature)
    raw = np.asarray(logits)
    if raw.dtype.kind not in "iuf" or raw.ndim != 2 or raw.shape[0] == 0 or raw.shape[1] < 2:
        raise ValueError("logits must be a nonempty numeric [N, K] array with K >= 2")
    z = raw.astype(np.float64)
    if not np.isfinite(z).all():
        raise ValueError("logits must contain only finite values")
    maximum = z.max(axis=1)
    # Overflow to -inf is harmless here: its exponential is exactly zero at
    # float64 precision. Subtract before dividing to handle very small T.
    with np.errstate(over="ignore", under="ignore"):
        relative = (z - maximum[:, None]) / temperature
        total = np.exp(relative).sum(axis=1)
        if method == "msp":
            scores = 1.0 - 1.0 / total
        else:
            scores = -maximum - temperature * np.log(total)
    if not np.isfinite(scores).all():
        raise ValueError("unknown scores exceed finite float64 range")
    return scores

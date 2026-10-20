"""Known-validation rejection thresholds and their reusable provenance.

The caller must pass only known-class validation logits. This module never
selects a threshold using unknown test events. The empirical acceptance target
is not a population guarantee; ties can increase the observed acceptance.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from numbers import Integral, Real
from pathlib import Path

import numpy as np

from .openset import _method_temperature, unknown_scores


def _fraction(value: float) -> float:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real):
        raise ValueError("target_acceptance must be in (0, 1]")
    value = float(value)
    if not np.isfinite(value) or not 0 < value <= 1:
        raise ValueError("target_acceptance must be in (0, 1]")
    return value


@dataclass(frozen=True)
class RejectionCalibration:
    """Accept scores at or below ``threshold``; reject strictly above it."""

    method: str
    threshold: float
    target_acceptance: float
    n_calibration: int
    temperature: float = 1.0
    provenance: str = ""

    def __post_init__(self):
        temperature = _method_temperature(self.method, self.temperature)
        target = _fraction(self.target_acceptance)
        if (isinstance(self.threshold, (bool, np.bool_)) or not isinstance(self.threshold, Real)
                or not np.isfinite(self.threshold)):
            raise ValueError("threshold must be finite")
        if (isinstance(self.n_calibration, (bool, np.bool_)) or not isinstance(self.n_calibration, Integral)
                or self.n_calibration < 1):
            raise ValueError("n_calibration must be a positive integer")
        if not isinstance(self.provenance, str):
            raise ValueError("provenance must be a string")
        if self.method == "msp" and not 0 <= self.threshold <= 1:
            raise ValueError("MSP threshold must be in [0, 1]")
        # Canonical Python scalars ensure strict JSON serialization also works
        # when calibration was constructed with NumPy numeric scalars.
        object.__setattr__(self, "temperature", temperature)
        object.__setattr__(self, "target_acceptance", target)
        object.__setattr__(self, "threshold", float(self.threshold))
        object.__setattr__(self, "n_calibration", int(self.n_calibration))

    def accept(self, scores: np.ndarray) -> np.ndarray:
        """Return a boolean vector; equality to the threshold is accepted."""
        raw = np.asarray(scores)
        if raw.dtype.kind not in "iuf" or raw.ndim != 1 or not np.isfinite(raw).all():
            raise ValueError("scores must be a finite numeric vector")
        if self.method == "msp" and np.any((raw < 0) | (raw > 1)):
            raise ValueError("MSP scores must be in [0, 1]")
        return raw <= self.threshold

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "RejectionCalibration":
        """Validate all required fields and reject missing or extra fields."""
        fields = {"method", "threshold", "target_acceptance", "n_calibration", "temperature", "provenance"}
        if not isinstance(data, dict) or set(data) != fields:
            raise ValueError("invalid rejection calibration fields")
        return cls(**data)

    def save(self, path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2, allow_nan=False) + "\n")

    @classmethod
    def load(cls, path) -> "RejectionCalibration":
        return cls.from_dict(json.loads(Path(path).read_text()))


def calibrate(logits: np.ndarray, method: str, target_acceptance: float = 0.95,
              temperature: float = 1.0, provenance: str = "") -> RejectionCalibration:
    """Fit a threshold from known-only validation logits.

    The higher empirical quantile and inclusive acceptance ensure at least the
    requested fraction of these calibration samples is accepted. For very
    small samples or tied scores this can accept every calibration sample.
    Unknown-test labels or logits must not be used to fit this threshold.
    """
    target_acceptance = _fraction(target_acceptance)
    scores = unknown_scores(logits, method, temperature)
    threshold = float(np.quantile(scores, target_acceptance, method="higher"))
    return RejectionCalibration(method, threshold, target_acceptance, len(scores), temperature, provenance)

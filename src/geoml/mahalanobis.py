"""Training-only, regularized class-conditional Mahalanobis unknown scores.

The score is the smallest squared distance to any known-class mean. Larger is
more unknown-like. The pooled within-class covariance is shrunk toward its
trace-scaled identity, with a positive diagonal floor. Small-sample invertibility
is a numerical property, not evidence that the covariance estimate generalizes.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from numbers import Integral, Real
from pathlib import Path
from zipfile import BadZipFile
import zlib

import numpy as np
from scipy.linalg import solve_triangular

ARTIFACT_VERSION = 1


def _matrix(values, name: str) -> np.ndarray:
    raw = np.asarray(values)
    if raw.dtype.kind not in "iuf" or raw.ndim != 2 or not all(raw.shape):
        raise ValueError(f"{name} must be a nonempty numeric [N, D] array")
    matrix = np.array(raw, dtype=np.float64, copy=True)
    if not np.isfinite(matrix).all():
        raise ValueError(f"{name} must contain only finite values")
    return matrix


def _regularization(value: float) -> float:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real):
        raise ValueError("regularization must be in (0, 1]")
    value = float(value)
    if not np.isfinite(value) or not 0 < value <= 1:
        raise ValueError("regularization must be in (0, 1]")
    return value


def _parameter_hash(means, cholesky, class_counts) -> str:
    digest = hashlib.sha256()
    # Arrays are canonical float64/int64 and C contiguous after construction.
    for array in (means, cholesky, class_counts):
        digest.update(str(array.shape).encode("ascii"))
        digest.update(array.dtype.str.encode("ascii"))
        digest.update(array.tobytes(order="C"))
    return digest.hexdigest()


@dataclass(frozen=True)
class MahalanobisScorer:
    means: np.ndarray
    cholesky: np.ndarray
    class_counts: np.ndarray
    regularization: float
    covariance_floor: float
    provenance: str = ""

    def __post_init__(self):
        means = _matrix(self.means, "class means")
        if len(means) < 2:
            raise ValueError("at least two known classes are required")
        cholesky = _matrix(self.cholesky, "Cholesky factor")
        d = means.shape[1]
        if cholesky.shape != (d, d) or not np.array_equal(cholesky, np.tril(cholesky)) or np.any(np.diag(cholesky) <= 0):
            raise ValueError("Cholesky factor must be lower triangular with a positive diagonal and match feature width")
        raw_counts = np.asarray(self.class_counts)
        if raw_counts.dtype.kind not in "iu" or raw_counts.shape != (len(means),) or np.any(raw_counts < 1):
            raise ValueError("class_counts must contain a positive integer for every class")
        if np.any(raw_counts > np.iinfo(np.int64).max):
            raise ValueError("class_counts exceed supported integer range")
        counts = np.array(raw_counts, dtype=np.int64, copy=True)
        regularization = _regularization(self.regularization)
        if (isinstance(self.covariance_floor, (bool, np.bool_)) or not isinstance(self.covariance_floor, Real)
                or not np.isfinite(self.covariance_floor) or self.covariance_floor <= 0):
            raise ValueError("covariance_floor must be finite and positive")
        if not isinstance(self.provenance, str):
            raise ValueError("provenance must be a string")
        for array in (means, cholesky, counts):
            array.setflags(write=False)
        object.__setattr__(self, "means", means)
        object.__setattr__(self, "cholesky", cholesky)
        object.__setattr__(self, "class_counts", counts)
        object.__setattr__(self, "regularization", regularization)
        object.__setattr__(self, "covariance_floor", float(self.covariance_floor))

    def score(self, embeddings: np.ndarray) -> np.ndarray:
        """Squared distance to the nearest training-class mean, one per row."""
        x = _matrix(embeddings, "embeddings")
        if x.shape[1] != self.means.shape[1]:
            raise ValueError("embedding feature width does not match the fitted scorer")
        scores = np.full(len(x), np.inf)
        try:
            with np.errstate(over="raise", invalid="raise"):
                for mean in self.means:
                    whitened = solve_triangular(self.cholesky, (x - mean).T, lower=True, check_finite=False)
                    distances = np.einsum("ij,ij->j", whitened, whitened)
                    scores = np.minimum(scores, distances)
        except (FloatingPointError, ValueError) as error:
            raise ValueError("Mahalanobis distances exceed finite numeric range") from error
        if not np.isfinite(scores).all():
            raise ValueError("Mahalanobis distances exceed finite numeric range")
        return scores

    def to_dict(self) -> dict:
        """Small metadata summary; array parameters are persisted in the NPZ file."""
        metadata = {"artifact_version": ARTIFACT_VERSION, "n_classes": len(self.means),
                    "n_features": self.means.shape[1], "n_training": sum(map(int, self.class_counts)),
                    "class_counts": self.class_counts.tolist(), "regularization": self.regularization,
                    "covariance_floor": self.covariance_floor, "provenance": self.provenance,
                    "parameter_sha256": _parameter_hash(self.means, self.cholesky, self.class_counts)}
        payload = json.dumps(metadata, sort_keys=True, separators=(",", ":"), allow_nan=False)
        return {**metadata, "artifact_sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest()}

    def save(self, path) -> None:
        """Atomically persist plain numeric arrays and strict JSON, without pickle."""
        path = Path(path)
        temporary = path.with_suffix(path.suffix + ".tmp")
        with temporary.open("wb") as stream:
            np.savez_compressed(stream, means=self.means, cholesky=self.cholesky,
                                class_counts=self.class_counts,
                                metadata=np.array(json.dumps(self.to_dict(), sort_keys=True, allow_nan=False)))
        temporary.replace(path)

    @classmethod
    def load(cls, path) -> "MahalanobisScorer":
        try:
            with np.load(path, allow_pickle=False) as artifact:
                if set(artifact.files) != {"means", "cholesky", "class_counts", "metadata"}:
                    raise ValueError("unexpected artifact arrays")
                metadata_array = artifact["metadata"]
                if metadata_array.shape != () or metadata_array.dtype.kind not in "US":
                    raise ValueError("metadata must be a JSON string scalar")
                metadata = json.loads(metadata_array.item())
                scorer = cls(artifact["means"], artifact["cholesky"], artifact["class_counts"],
                             metadata["regularization"], metadata["covariance_floor"], metadata["provenance"])
                if metadata != scorer.to_dict():
                    raise ValueError("artifact metadata or parameter checksum does not match")
                return scorer
        except (OSError, KeyError, TypeError, ValueError, EOFError, BadZipFile, zlib.error) as error:
            raise ValueError(f"invalid Mahalanobis artifact {path}: {error}") from error


def fit_mahalanobis(embeddings: np.ndarray, labels: np.ndarray, n_classes: int,
                    regularization: float = 0.1, provenance: str = "") -> MahalanobisScorer:
    """Fit from known training embeddings and their contiguous class indices only.

    Covariance uses residuals about each training-class mean and denominator
    ``max(N-K, 1)``. Shrinkage is ``(1-a)*S + a*trace(S)/D*I``. The added floor
    is ``max(trace(S)/D * 1e-6, 1e-8)``. Even one observation per class can be
    represented, but then within-class variation is unestimated and the floor
    dominates; retain this limitation in experiment interpretation.
    """
    x = _matrix(embeddings, "training embeddings")
    regularization = _regularization(regularization)
    if isinstance(n_classes, (bool, np.bool_)) or not isinstance(n_classes, Integral) or n_classes < 2:
        raise ValueError("n_classes must be an integer >= 2")
    y = np.asarray(labels)
    if y.dtype.kind not in "iu" or y.shape != (len(x),) or np.any(y < 0) or np.any(y >= n_classes):
        raise ValueError("labels must contain one in-range integer class index per training row")
    if set(y.tolist()) != set(range(n_classes)):
        raise ValueError("every known class must have training observations")
    counts = np.bincount(y.astype(np.int64), minlength=n_classes)
    try:
        with np.errstate(over="raise", invalid="raise"):
            means = np.stack([x[y == label].mean(axis=0) for label in range(n_classes)])
            residuals = x - means[y]
            covariance = residuals.T @ residuals / max(len(x) - n_classes, 1)
            variance = float(np.trace(covariance) / x.shape[1])
            floor = max(variance * 1e-6, 1e-8)
            covariance *= 1 - regularization
            diagonal = np.diag_indices_from(covariance)
            covariance[diagonal] += regularization * variance + floor
            cholesky = np.linalg.cholesky(covariance)
    except (FloatingPointError, np.linalg.LinAlgError) as error:
        raise ValueError("training covariance cannot be represented as a finite positive-definite matrix") from error
    return MahalanobisScorer(means, cholesky, counts, regularization, floor, provenance)

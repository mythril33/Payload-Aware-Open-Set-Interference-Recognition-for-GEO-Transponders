"""Two-polarization coupling and independently measured receiver calibration.

``jones_matrix`` is a unitary symmetric-coupling approximation: it represents
an ideal change of polarization basis with a specified isolated-source XPD.
It is not a general antenna-loss or depolarizing propagation model. An
independently measured receiver response may include unequal gain and leakage.
Correcting that response must not invert the separate physical channel matrix.

Arrays use polarization on axis zero, in the declared [co, cross] order.
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

ARTIFACT_VERSION = 1


def _real(value, name: str, *, allow_positive_infinity: bool = False) -> float:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real):
        raise ValueError(f"{name} must be a real number")
    value = float(value)
    if not np.isfinite(value) and not (allow_positive_infinity and value == np.inf):
        raise ValueError(f"{name} must be finite")
    return value


def _complex_array(values, name: str) -> np.ndarray:
    raw = np.asarray(values)
    if raw.dtype.kind not in "iufc" or not raw.size:
        raise ValueError(f"{name} must be a nonempty numeric array")
    result = np.array(raw, dtype=np.complex128, copy=True)
    if not np.isfinite(result).all():
        raise ValueError(f"{name} must contain only finite values")
    return result


def _response(values) -> np.ndarray:
    result = _complex_array(values, "response")
    if result.shape != (2, 2):
        raise ValueError("response must be a 2x2 matrix in [co, cross] order")
    return result


def _iq(values) -> np.ndarray:
    result = _complex_array(values, "IQ")
    if result.ndim < 1 or result.shape[0] != 2:
        raise ValueError("IQ must have polarization on axis zero with length two")
    return result


def jones_matrix(xpd_db: float, phase_rad: float = 0.0) -> np.ndarray:
    """Return a power-conserving 2x2 complex128 polarization mixer.

    ``J = [[c, exp(j*phase)*s], [-exp(-j*phase)*s, c]]`` with
    ``c**2/s**2 = 10**(XPD_dB/10)``. An isolated input therefore has the
    requested co/cross output-power ratio. Positive infinity gives identity.
    XPD must be nonnegative; negative values would reverse the co/cross labels.
    """
    xpd_db = _real(xpd_db, "xpd_db", allow_positive_infinity=True)
    phase_rad = _real(phase_rad, "phase_rad")
    if xpd_db < 0:
        raise ValueError("xpd_db must be nonnegative or positive infinity")
    voltage_ratio = 10.0 ** (-xpd_db / 20.0)
    co = 1.0 / np.sqrt(1.0 + voltage_ratio**2)
    cross = voltage_ratio * co
    phased_cross = np.exp(1j * phase_rad) * cross
    return np.array([[co, phased_cross], [-np.conj(phased_cross), co]], dtype=np.complex128)


def apply_jones(matrix: np.ndarray, iq: np.ndarray) -> np.ndarray:
    """Apply any finite 2x2 response to leading-axis polarization samples.

    Arbitrary trailing dimensions (snapshots, time samples, etc.) are retained.
    Output is complex128. Only matrices made by ``jones_matrix`` are guaranteed
    unitary; arbitrary measured instrument responses can change signal power.
    """
    response, values = _response(matrix), _iq(iq)
    try:
        with np.errstate(over="raise", invalid="raise"):
            result = response @ values.reshape(2, -1)
    except FloatingPointError as error:
        raise ValueError("polarization response exceeds finite numeric range") from error
    if not np.isfinite(result).all():
        raise ValueError("polarization response exceeds finite numeric range")
    return result.reshape(values.shape)


def _parameter_hash(response: np.ndarray) -> str:
    return hashlib.sha256(response.tobytes(order="C")).hexdigest()


@dataclass(frozen=True)
class ReceiverCalibration:
    """Estimated instrument response ``measured = H @ reference``.

    Correction removes H only. Physical uplink/downlink coupling is a separate
    simulation block and must remain in the corrected observations. ``n_pilots``
    zero denotes an externally supplied response rather than a fit performed by
    this module. Receiver noise after H is transformed, not removed, by inversion.
    """

    response: np.ndarray
    n_pilots: int = 0
    max_condition: float = 1e6
    reference_condition: float = 1.0
    residual_rms: float = 0.0
    provenance: str = ""

    def __post_init__(self):
        response = _response(self.response)
        maximum = _real(self.max_condition, "max_condition")
        reference_condition = _real(self.reference_condition, "reference_condition")
        residual = _real(self.residual_rms, "residual_rms")
        if maximum < 1:
            raise ValueError("max_condition must be at least one")
        if not 1 <= reference_condition <= maximum:
            raise ValueError("reference_condition must be between one and max_condition")
        if residual < 0:
            raise ValueError("residual_rms must be nonnegative")
        if (isinstance(self.n_pilots, (bool, np.bool_)) or not isinstance(self.n_pilots, Integral)
                or self.n_pilots < 0 or self.n_pilots == 1):
            raise ValueError("n_pilots must be zero (external response) or an integer >= 2")
        if not isinstance(self.provenance, str):
            raise ValueError("provenance must be a string")
        condition = float(np.linalg.cond(response))
        if not np.isfinite(condition) or condition > maximum:
            raise ValueError("receiver response is singular or exceeds max_condition")
        response.setflags(write=False)
        object.__setattr__(self, "response", response)
        object.__setattr__(self, "n_pilots", int(self.n_pilots))
        object.__setattr__(self, "max_condition", maximum)
        object.__setattr__(self, "reference_condition", reference_condition)
        object.__setattr__(self, "residual_rms", residual)

    def correct(self, iq: np.ndarray) -> np.ndarray:
        """Correct instrument response while retaining physical channel effects."""
        values = _iq(iq)
        try:
            with np.errstate(over="raise", invalid="raise"):
                corrected = np.linalg.solve(self.response, values.reshape(2, -1))
        except (FloatingPointError, np.linalg.LinAlgError) as error:
            raise ValueError("receiver correction cannot be represented finitely") from error
        if not np.isfinite(corrected).all():
            raise ValueError("receiver correction cannot be represented finitely")
        return corrected.reshape(values.shape)

    def to_dict(self) -> dict:
        """Strict-JSON calibration metadata, including independently fitted H."""
        metadata = {"artifact_version": ARTIFACT_VERSION, "n_pilots": self.n_pilots,
                    "max_condition": self.max_condition, "reference_condition": self.reference_condition,
                    "response_condition": float(np.linalg.cond(self.response)), "residual_rms": self.residual_rms,
                    "provenance": self.provenance, "response_real": self.response.real.tolist(),
                    "response_imag": self.response.imag.tolist(), "parameter_sha256": _parameter_hash(self.response)}
        canonical = json.dumps(metadata, sort_keys=True, separators=(",", ":"), allow_nan=False)
        return {**metadata, "artifact_sha256": hashlib.sha256(canonical.encode()).hexdigest()}

    def save(self, path) -> None:
        """Atomically save numeric response plus JSON; no pickle is used."""
        path = Path(path)
        temporary = path.with_suffix(path.suffix + ".tmp")
        with temporary.open("wb") as stream:
            np.savez_compressed(stream, response=self.response,
                                metadata=np.array(json.dumps(self.to_dict(), sort_keys=True, allow_nan=False)))
        temporary.replace(path)

    @classmethod
    def load(cls, path) -> "ReceiverCalibration":
        try:
            with np.load(path, allow_pickle=False) as artifact:
                if set(artifact.files) != {"response", "metadata"}:
                    raise ValueError("unexpected calibration arrays")
                metadata = artifact["metadata"]
                if metadata.shape != () or metadata.dtype.kind not in "US":
                    raise ValueError("calibration metadata must be a JSON scalar")
                metadata = json.loads(metadata.item())
                result = cls(artifact["response"], metadata["n_pilots"], metadata["max_condition"],
                             metadata["reference_condition"], metadata["residual_rms"], metadata["provenance"])
                if metadata != result.to_dict():
                    raise ValueError("calibration checksum or metadata does not match")
                return result
        except (OSError, ValueError, KeyError, TypeError, EOFError, BadZipFile, zlib.error) as error:
            raise ValueError(f"invalid receiver calibration {path}: {error}") from error


def fit_receiver_calibration(reference: np.ndarray, measured: np.ndarray,
                             max_condition: float = 1e6, provenance: str = "") -> ReceiverCalibration:
    """Fit complex least squares from independent known reference pilots.

    Both arrays have shape [2,N], N>=2. Reference pilots must excite both
    polarizations independently; source-classification/test observations are not
    calibration references. A bad reference or estimated H is rejected before
    correction can amplify near-singular uncertainty arbitrarily.
    """
    reference, measured = _iq(reference), _iq(measured)
    maximum = _real(max_condition, "max_condition")
    if maximum < 1:
        raise ValueError("max_condition must be at least one")
    if reference.ndim != 2 or reference.shape[1] < 2 or measured.shape != reference.shape:
        raise ValueError("reference and measured pilots must have matching shape [2,N], N >= 2")
    singular = np.linalg.svd(reference, compute_uv=False)
    tolerance = np.finfo(float).eps * max(reference.shape) * singular[0]
    if singular[-1] <= tolerance:
        raise ValueError("reference pilots must have full row rank")
    condition = float(singular[0] / singular[-1])
    if not np.isfinite(condition) or condition > maximum:
        raise ValueError("reference pilots exceed max_condition")
    try:
        with np.errstate(over="raise", invalid="raise"):
            coefficients, _, rank, _ = np.linalg.lstsq(reference.T, measured.T, rcond=None)
            if rank != 2:
                raise ValueError("reference pilots must have full row rank")
            response = coefficients.T
            residual = measured - response @ reference
            residual_rms = float(np.sqrt(np.mean(np.abs(residual)**2)))
    except (FloatingPointError, np.linalg.LinAlgError) as error:
        raise ValueError("receiver calibration cannot be represented finitely") from error
    return ReceiverCalibration(response, reference.shape[1], maximum, condition, residual_rms, provenance)

"""Effective oscillator phase noise at sparsely observed sample times.

The Wiener model has Lorentzian effective linewidth ``linewidth_hz`` and
``Var(phi(t + dt) - phi(t)) = 2*pi*linewidth_hz*dt``. This is not a complete
measured single-sideband phase-noise mask. A caller that models a common local
oscillator should generate one phase array and rotate both polarizations with
that same array; this module makes no class-dependent or polarization-specific
random choices.
"""
from __future__ import annotations

from numbers import Integral, Real

import numpy as np


def _real(value, name: str) -> float:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real):
        raise ValueError(f"{name} must be a finite real number")
    try:
        value = float(value)
    except OverflowError as error:
        raise ValueError(f"{name} must be a finite real number") from error
    if not np.isfinite(value):
        raise ValueError(f"{name} must be a finite real number")
    return value


def _real_array(values, name: str) -> np.ndarray:
    raw = np.asarray(values)
    if raw.dtype.kind not in "iuf" or not raw.size:
        raise ValueError(f"{name} must be a nonempty finite real array")
    with np.errstate(over="ignore", invalid="ignore"):
        result = np.asarray(raw, dtype=np.float64)
    if not np.isfinite(result).all():
        raise ValueError(f"{name} must contain only finite real values")
    return result


def _increment_scale(linewidth_hz: float, elapsed) -> np.ndarray:
    # Taking square roots before multiplying avoids overflowing an otherwise
    # representable standard deviation merely because its variance is large.
    with np.errstate(over="raise", invalid="raise"):
        return np.sqrt(linewidth_hz) * np.sqrt(elapsed) * np.sqrt(2 * np.pi)


def wiener_phase(rng: np.random.Generator, t0: np.ndarray, n: int, fs: float,
                 linewidth_hz: float) -> np.ndarray:
    """Return unwrapped float64 phase with shape ``[len(t0), n]``.

    Snapshot ``k`` samples times ``t0[k] + arange(n)/fs`` in seconds. Starts
    must be finite, nonnegative, strictly increasing and nonoverlapping; the
    next start must be later than the previous window's last sample. The first
    observed phase is exactly zero, even when ``t0[0]`` is positive.

    The walk continues over unobserved gaps through one Gaussian increment
    per gap. Runtime and memory depend on observed samples, not skipped time.
    Different observation layouts give the same Brownian increment laws, but
    need not produce the same realization from the same RNG seed. A zero
    linewidth returns exact zeros without consuming RNG state.
    """
    if not isinstance(rng, np.random.Generator):
        raise ValueError("rng must be a numpy.random.Generator")
    if (isinstance(n, (bool, np.bool_)) or not isinstance(n, Integral)
            or n <= 0 or n > np.iinfo(np.intp).max):
        raise ValueError("n must be a positive representable integer")
    n = int(n)
    fs = _real(fs, "fs")
    linewidth_hz = _real(linewidth_hz, "linewidth_hz")
    if fs <= 0:
        raise ValueError("fs must be positive")
    if linewidth_hz < 0:
        raise ValueError("linewidth_hz must be nonnegative")
    starts = _real_array(t0, "t0")
    if starts.ndim != 1 or np.any(starts < 0):
        raise ValueError("t0 must be one-dimensional and nonnegative")
    if starts.size > np.iinfo(np.intp).max // n:
        raise ValueError("phase array shape exceeds the supported numeric range")
    try:
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            duration = np.float64(n - 1) / fs
            last_time = starts[-1] + duration
            gaps = np.diff(starts) - duration
    except FloatingPointError as error:
        raise ValueError("snapshot times exceed finite numeric range") from error
    if not np.isfinite(last_time) or np.any(gaps <= 0):
        raise ValueError("t0 windows must be strictly increasing and nonoverlapping")
    if linewidth_hz == 0:
        return np.zeros((starts.size, n), dtype=np.float64)

    increments = np.zeros((starts.size, n), dtype=np.float64)
    try:
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            if n > 1:
                scale = _increment_scale(linewidth_hz, np.float64(1) / fs)
                increments[:, 1:] = rng.standard_normal((starts.size, n - 1)) * scale
            if starts.size > 1:
                increments[1:, 0] = rng.standard_normal(starts.size - 1) * _increment_scale(linewidth_hz, gaps)
            np.cumsum(increments.reshape(-1), out=increments.reshape(-1))
    except FloatingPointError as error:
        raise ValueError("phase walk exceeds finite numeric range") from error
    if not np.isfinite(increments).all():
        raise ValueError("phase walk exceeds finite numeric range")
    return increments


def rotate_phase(iq: np.ndarray, phase: np.ndarray) -> np.ndarray:
    """Rotate finite complex IQ by ``exp(1j*phase)`` without changing power.

    ``phase`` is a real ``[T,n]`` array and must match the last two IQ axes.
    Leading axes, including polarization, share the same oscillator phase.
    The output retains the IQ shape and complex dtype; neither input changes.
    """
    values = np.asarray(iq)
    angles = _real_array(phase, "phase")
    if (values.ndim < 2 or not values.size or values.dtype.kind != "c"
            or not np.isfinite(values).all()):
        raise ValueError("iq must be a nonempty finite complex array with at least two dimensions")
    if angles.ndim != 2 or values.shape[-2:] != angles.shape:
        raise ValueError("phase must have shape [T,n] matching the last two iq axes")
    try:
        with np.errstate(over="raise", invalid="raise"):
            phasor = np.exp(1j * angles).astype(values.dtype, copy=False)
            result = values * phasor
    except FloatingPointError as error:
        raise ValueError("rotated iq exceeds finite numeric range") from error
    if not np.isfinite(result).all():
        raise ValueError("rotated iq exceeds finite numeric range")
    return result

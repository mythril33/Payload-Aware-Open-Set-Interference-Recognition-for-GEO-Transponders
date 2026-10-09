"""Transponder blocks: IMUX, channel amplifier, TWTA, OMUX (spec §2.4-§2.7)."""
from __future__ import annotations

import numpy as np
from scipy.signal import cheby1, cheby2, ellip, sosfilt

# Saleh 1981 TWT coefficients as commonly quoted; not yet checked against the paper.
A_A, B_A, A_P, B_P = 2.1587, 1.1517, 4.0033, 9.1040
R_SAT = 1 / np.sqrt(B_A)
A_MAX = A_A * R_SAT / (1 + B_A * R_SAT ** 2)


def imux_sos(bandwidth: float, fs: float, model: str = "dvbs2x") -> np.ndarray:
    """Low-pass equivalent of the input multiplexer filter.

    "dvbs2x": 7th-order Chebyshev II, 34 dB, 23 MHz stop-band edge for a 36 MHz transponder --
    the approximation of the ETSI TR 102 376-2 reference IMUX given by Dimitrov (2016),
    scaled in frequency by bandwidth/36 MHz as EN 302 307-1 H.7 prescribes.
    "generic": the project's earlier elliptic placeholder.
    """
    k = bandwidth / 36e6
    if model == "dvbs2x":
        return cheby2(7, 34, 23e6 * k / (fs / 2), output="sos")
    if model == "generic":
        return ellip(6, 0.1, 40, (bandwidth / 2) / (fs / 2), output="sos")
    raise ValueError(f"unknown filter model {model!r}")


def omux_sos(bandwidth: float, fs: float, model: str = "dvbs2x") -> np.ndarray:
    """Output multiplexer; "dvbs2x" is 5th-order Chebyshev II, 38 dB, 28.6 MHz edge at 36 MHz."""
    k = bandwidth / 36e6
    if model == "dvbs2x":
        return cheby2(5, 38, 28.6e6 * k / (fs / 2), output="sos")
    if model == "generic":
        return cheby1(4, 0.1, 1.1 * (bandwidth / 2) / (fs / 2), output="sos")
    raise ValueError(f"unknown filter model {model!r}")


def apply_filter(sos: np.ndarray, x: np.ndarray) -> np.ndarray:
    return sosfilt(sos, x, axis=-1).astype(np.complex64)


def saleh(x: np.ndarray) -> np.ndarray:
    r2 = np.abs(x) ** 2
    return (x * (A_A / (1 + B_A * r2)) * np.exp(1j * A_P * r2 / (1 + B_P * r2))).astype(x.dtype)


def linear_amp(x: np.ndarray) -> np.ndarray:
    """Linear reference: Saleh small-signal gain, no compression, no AM/PM."""
    return (A_A * x).astype(x.dtype)


def drive_gain(nominal_power: float, ibo_db: float) -> float:
    """Fixed channel-amplifier voltage gain putting `nominal_power` at the given IBO.

    IBO = 10 log10(R_SAT^2 / E|x|^2), referenced to single-carrier saturation.
    """
    return float(np.sqrt(R_SAT ** 2 * 10 ** (-ibo_db / 10) / nominal_power))


def obo_db(y: np.ndarray) -> float:
    return float(10 * np.log10(A_MAX ** 2 / np.mean(np.abs(y) ** 2)))

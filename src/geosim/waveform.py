"""Carrier generation: constellations, SRRC shaping, frequency placement (spec §2.1)."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.signal import upfirdn

# Ring ratios from EN 302 307-1 Tables 9 and 10, keyed by code rate.
GAMMA_16APSK = {"2/3": 3.15, "3/4": 2.85, "4/5": 2.75, "5/6": 2.70, "8/9": 2.60, "9/10": 2.57}
GAMMA_32APSK = {"3/4": (2.84, 5.27), "4/5": (2.72, 4.87), "5/6": (2.64, 4.64),
                "8/9": (2.54, 4.33), "9/10": (2.53, 4.30)}
MODULATIONS = ("QPSK", "8PSK", "16APSK", "32APSK")
ROLLOFFS = (0.20, 0.25, 0.35)
SRRC_SPAN = 16  # symbols each side


def _ring(n: int, radius: float, phase0: float) -> np.ndarray:
    return radius * np.exp(1j * (phase0 + 2 * np.pi * np.arange(n) / n))


def constellation(mod: str, code_rate: str | None = None) -> np.ndarray:
    """Unit-average-energy constellation points.

    Ring start angles for APSK are from memory of the standard's figures and are
    not yet checked against it; they do not affect spectrum or envelope statistics.
    """
    if mod == "QPSK":
        pts = _ring(4, 1.0, np.pi / 4)
    elif mod == "8PSK":
        pts = _ring(8, 1.0, np.pi / 4)
    elif mod == "16APSK":
        g = GAMMA_16APSK[code_rate or "3/4"]
        pts = np.concatenate([_ring(4, 1.0, np.pi / 4), _ring(12, g, np.pi / 12)])
    elif mod == "32APSK":
        g1, g2 = GAMMA_32APSK[code_rate or "3/4"]
        pts = np.concatenate([_ring(4, 1.0, np.pi / 4), _ring(12, g1, np.pi / 12), _ring(16, g2, 0.0)])
    else:
        raise ValueError(f"unknown modulation {mod!r}")
    return pts / np.sqrt(np.mean(np.abs(pts) ** 2))


def srrc_taps(alpha: float, sps: int, span: int = SRRC_SPAN) -> np.ndarray:
    """Square-root raised-cosine taps, unit energy, length 2*span*sps + 1."""
    t = np.arange(-span * sps, span * sps + 1) / sps
    h = np.empty_like(t)
    zero = np.isclose(t, 0.0)
    sing = np.isclose(np.abs(t), 1 / (4 * alpha))
    reg = ~(zero | sing)
    h[zero] = 1 - alpha + 4 * alpha / np.pi
    h[sing] = (alpha / np.sqrt(2)) * ((1 + 2 / np.pi) * np.sin(np.pi / (4 * alpha))
                                      + (1 - 2 / np.pi) * np.cos(np.pi / (4 * alpha)))
    tr = t[reg]
    h[reg] = (np.sin(np.pi * tr * (1 - alpha)) + 4 * alpha * tr * np.cos(np.pi * tr * (1 + alpha))) / (
        np.pi * tr * (1 - (4 * alpha * tr) ** 2))
    return h / np.sqrt(np.sum(h ** 2))


def samples_per_symbol(symbol_rate: float, fs: float) -> int:
    sps = fs / symbol_rate
    if abs(sps - round(sps)) > 1e-9 or round(sps) < 8:
        raise ValueError(f"fs/Rs must be an integer >= 8, got {sps}")
    return int(round(sps))


def shape(symbols: np.ndarray, alpha: float, sps: int) -> np.ndarray:
    """Pulse-shape symbols (last axis). Output power is E|a|^2 / sps."""
    return upfirdn(srrc_taps(alpha, sps), symbols, up=sps, axis=-1)


@dataclass(frozen=True)
class Carrier:
    f0: float            # centre frequency offset from transponder centre, Hz
    symbol_rate: float   # baud
    alpha: float
    mod: str
    power: float         # linear, relative; a plan's carriers sum to 1
    code_rate: str | None = None

    @property
    def occupied_bw(self) -> float:
        return self.symbol_rate * (1 + self.alpha)


def generate_carrier(rng: np.random.Generator, c: Carrier, n_snap: int, n: int, fs: float) -> np.ndarray:
    """(n_snap, n) complex64 baseband samples of one carrier; snapshots are independent."""
    sps = samples_per_symbol(c.symbol_rate, fs)
    pts = constellation(c.mod, c.code_rate)
    n_sym = -(-n // sps) + 2 * SRRC_SPAN + 2
    sym = pts[rng.integers(0, len(pts), size=(n_snap, n_sym))]
    x = shape(sym, c.alpha, sps)
    start = 2 * SRRC_SPAN * sps + int(rng.integers(0, sps))  # skip filter ramp-up, random timing
    x = x[:, start:start + n] * np.sqrt(sps * c.power)
    phase0 = rng.uniform(0, 2 * np.pi, size=(n_snap, 1))
    x = x * np.exp(1j * (2 * np.pi * c.f0 * np.arange(n) / fs + phase0))
    return x.astype(np.complex64)

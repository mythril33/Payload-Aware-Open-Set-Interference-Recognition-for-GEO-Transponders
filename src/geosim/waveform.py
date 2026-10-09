"""Carrier generation: constellations, SRRC shaping, frequency placement (spec §2.1)."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# Ring ratios from EN 302 307-1 Tables 9 and 10, keyed by code rate.
GAMMA_16APSK = {"2/3": 3.15, "3/4": 2.85, "4/5": 2.75, "5/6": 2.70, "8/9": 2.60, "9/10": 2.57}
GAMMA_32APSK = {"3/4": (2.84, 5.27), "4/5": (2.72, 4.87), "5/6": (2.64, 4.64),
                "8/9": (2.54, 4.33), "9/10": (2.53, 4.30)}
MODULATIONS = ("QPSK", "8PSK", "16APSK", "32APSK")
ROLLOFFS = (0.20, 0.25, 0.35)


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


def srrc_response(f: np.ndarray, symbol_rate: float, alpha: float) -> np.ndarray:
    """Square-root raised-cosine frequency response (peak 1) at frequencies f, Hz."""
    d = np.abs(f)
    lo, hi = (1 - alpha) * symbol_rate / 2, (1 + alpha) * symbol_rate / 2
    roll = np.sqrt(0.5 * (1 + np.cos(np.pi * (np.clip(d, lo, hi) - lo) / (alpha * symbol_rate))))
    return np.where(d <= lo, 1.0, np.where(d < hi, roll, 0.0))


def samples_per_symbol(symbol_rate: float, fs: float) -> int:
    sps = fs / symbol_rate
    if abs(sps - round(sps)) > 1e-9 or round(sps) < 8:
        raise ValueError(f"fs/Rs must be an integer >= 8, got {sps}")
    return int(round(sps))


def modulate(symbols: np.ndarray, alpha: float, sps: int, shift_bins: int = 0, delay: int = 0) -> np.ndarray:
    """Pulse-shape symbols (last axis) in the frequency domain; returns len(symbols) * sps samples.

    The block is treated as periodic, so the shaping is the ideal (untruncated) SRRC and every
    sample is a valid steady-state sample. Unit-power symbols give unit-power output.
    shift_bins moves the carrier by that many FFT bins; delay is a circular delay in samples.
    """
    n_sym = symbols.shape[-1]
    length = n_sym * sps
    k = np.fft.fftfreq(length, 1 / length).astype(int)            # signed bin index
    used = np.abs(k) <= np.ceil((1 + alpha) * n_sym / 2)          # bins inside the occupied bandwidth
    h = srrc_response(k[used] / sps, n_sym / sps, alpha) * np.exp(-2j * np.pi * k[used] * delay / length)
    spec = np.zeros(symbols.shape[:-1] + (length,), np.complex64)
    spec[..., (k[used] + shift_bins) % length] = np.fft.fft(symbols, axis=-1)[..., k[used] % n_sym] * h
    return np.fft.ifft(spec, axis=-1) * sps


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
    n_sym = -(-n // sps)
    length = n_sym * sps
    sym = pts[rng.integers(0, len(pts), size=(n_snap, n_sym))].astype(np.complex64)
    bins = c.f0 * length / fs
    whole = int(np.round(bins))
    x = modulate(sym, c.alpha, sps, shift_bins=whole, delay=int(rng.integers(0, sps)))[:, :n]
    residual = np.exp(2j * np.pi * (bins - whole) * np.arange(n) / length)        # sub-bin part of f0
    phase0 = np.exp(1j * rng.uniform(0, 2 * np.pi, size=(n_snap, 1)))
    return (x * (np.sqrt(c.power) * residual)[None, :] * phase0).astype(np.complex64)

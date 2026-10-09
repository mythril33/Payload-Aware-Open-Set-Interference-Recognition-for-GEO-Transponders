"""Uplink interferer waveforms for stage A (spec: docs/plan/P3_taksonomi.md).

Each factory returns (generate, meta). generate(rng, t0, n, fs) gives (n_snap, n) complex samples
at the uplink; power is relative to the total planned carrier power, which is 1.
"""
from __future__ import annotations

import numpy as np

from .plan import SYMBOL_RATES
from .waveform import MODULATIONS, ROLLOFFS, Carrier, generate_carrier


def _tone(rng, inst_freq, fs, power):
    """Constant-envelope signal with the given per-sample instantaneous frequency (n_snap, n)."""
    phase = 2 * np.pi * np.cumsum(inst_freq, axis=-1) / fs + rng.uniform(0, 2 * np.pi, (inst_freq.shape[0], 1))
    return (np.sqrt(power) * np.exp(1j * phase)).astype(np.complex64)


def cw(f0: float, c_over_i_db: float, drift_hz_per_s: float = 0.0):
    power = 10 ** (-c_over_i_db / 10)

    def generate(rng, t0, n, fs):
        t = t0[:, None] + np.arange(n)[None, :] / fs
        return _tone(rng, f0 + drift_hz_per_s * t, fs, power)
    return generate, {"kind": "cw", "f0": f0, "c_over_i_db": c_over_i_db, "drift_hz_per_s": drift_hz_per_s,
                      "f_lo": f0, "f_hi": f0}


def sweep_frequency(t, f_lo, f_hi, period, shape, t_offset=0.0):
    """Instantaneous frequency of a periodic linear sweep; shape is "sawtooth" or "triangle"."""
    u = ((t + t_offset) / period) % 1.0
    if shape == "triangle":
        u = 1 - np.abs(2 * u - 1)
    return f_lo + (f_hi - f_lo) * u


def swept_cw(f_lo: float, f_hi: float, period: float, c_over_i_db: float, shape: str = "sawtooth",
             t_offset: float = 0.0):
    power = 10 ** (-c_over_i_db / 10)

    def generate(rng, t0, n, fs):
        t = t0[:, None] + np.arange(n)[None, :] / fs
        return _tone(rng, sweep_frequency(t, f_lo, f_hi, period, shape, t_offset), fs, power)
    return generate, {"kind": "swept_cw", "f_lo": f_lo, "f_hi": f_hi, "period": period, "shape": shape,
                      "t_offset": t_offset, "c_over_i_db": c_over_i_db}


def modulated(carrier: Carrier):
    """A modulated carrier that is not in the plan."""
    def generate(rng, t0, n, fs):
        return generate_carrier(rng, carrier, len(t0), n, fs)
    return generate, {"kind": "unauthorized", "f0": carrier.f0, "symbol_rate": carrier.symbol_rate,
                      "alpha": carrier.alpha, "mod": carrier.mod, "c_over_i_db": float(-10 * np.log10(carrier.power)),
                      "f_lo": carrier.f0 - carrier.occupied_bw / 2, "f_hi": carrier.f0 + carrier.occupied_bw / 2}


def free_gaps(plan: list[Carrier], bandwidth: float) -> list[tuple[float, float]]:
    """Unoccupied intervals (Hz) inside the transponder, left to right."""
    edges = sorted((c.f0 - c.occupied_bw / 2, c.f0 + c.occupied_bw / 2) for c in plan)
    gaps, left = [], -bandwidth / 2
    for lo, hi in edges:
        if lo > left:
            gaps.append((left, lo))
        left = max(left, hi)
    if bandwidth / 2 > left:
        gaps.append((left, bandwidth / 2))
    return gaps


def random_unauthorized(rng: np.random.Generator, plan: list[Carrier], bandwidth: float,
                        psd_offset_db: float) -> Carrier:
    """Draw a carrier that fits a free gap; its PSD is psd_offset_db relative to the plan's mean PSD.

    Raises ValueError when no gap can hold even the narrowest carrier.
    """
    options = []
    for lo, hi in free_gaps(plan, bandwidth):
        for rs in SYMBOL_RATES:
            for a in ROLLOFFS:
                need = rs * (1 + a) + 2 * 0.05 * rs          # carrier plus a guard on each side
                if need <= hi - lo:
                    options.append((lo, hi, rs, a, need))
    if not options:
        raise ValueError("no free gap wide enough for an unauthorized carrier")
    lo, hi, rs, a, need = options[rng.integers(len(options))]
    f0 = rng.uniform(lo + need / 2, hi - need / 2)
    mean_psd = sum(c.power for c in plan) / sum(c.symbol_rate for c in plan)
    mod = MODULATIONS[rng.integers(len(MODULATIONS))]
    return Carrier(f0=float(f0), symbol_rate=rs, alpha=a, mod=mod, power=float(mean_psd * rs * 10 ** (psd_offset_db / 10)))


def overlaps_plan(f_lo: float, f_hi: float, plan: list[Carrier]) -> bool:
    return any(f_hi >= c.f0 - c.occupied_bw / 2 and f_lo <= c.f0 + c.occupied_bw / 2 for c in plan)

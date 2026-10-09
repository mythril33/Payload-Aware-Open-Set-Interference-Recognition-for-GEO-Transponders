"""Random multicarrier plans and the plan mask (spec §2.2, §3.3)."""
from __future__ import annotations

import numpy as np

from . import FS_MON, FS_SIM
from .waveform import GAMMA_16APSK, GAMMA_32APSK, MODULATIONS, ROLLOFFS, Carrier

# Symbol rates with integer samples/symbol >= 8 at 288 MHz (spec §2.1), baud.
SYMBOL_RATES = tuple(r * 1e6 for r in (1, 1.5, 2, 2.4, 3, 3.6, 4, 4.5, 4.8, 6, 7.2, 8, 9, 9.6,
                                        12, 14.4, 18, 24, 28.8, 36))
MAX_CARRIERS = {36e6: 8, 72e6: 12}
GUARD_FRACTION = 0.05
N_BINS = 512


def random_plan(rng: np.random.Generator, bandwidth: float) -> list[Carrier]:
    """Carriers filling roughly 50-95 % of the transponder, equal PSD +/- 2 dB, powers summing to 1."""
    target = rng.uniform(0.50, 0.95) * bandwidth
    max_n = MAX_CARRIERS.get(bandwidth, 8)
    options = [(rs, a) for rs in SYMBOL_RATES for a in ROLLOFFS]

    def width(p):  # occupied bandwidth plus this carrier's share of guard band
        return p[0] * (1 + p[1] + GUARD_FRACTION)

    chosen: list[tuple[float, float]] = []
    used = 0.0
    while len(chosen) < max_n:
        fits = [p for p in options if width(p) <= min(target, bandwidth) - used]
        if not fits:
            break
        last = len(chosen) == max_n - 1
        pick = max(fits, key=width) if last else fits[rng.integers(len(fits))]
        chosen.append(pick)
        used += width(pick)
    chosen = [chosen[i] for i in rng.permutation(len(chosen))]
    guards = [GUARD_FRACTION * min(chosen[i][0], chosen[i + 1][0]) for i in range(len(chosen) - 1)]
    slack = bandwidth - sum(rs * (1 + a) for rs, a in chosen) - sum(guards)
    extra = rng.dirichlet(np.ones(len(chosen) + 1)) * slack
    carriers, edge = [], -bandwidth / 2
    for i, (rs, a) in enumerate(chosen):
        edge += extra[i] + (guards[i - 1] if i else 0.0)
        w = rs * (1 + a)
        mod = MODULATIONS[rng.integers(len(MODULATIONS))]
        rate = None
        if mod == "16APSK":
            rate = list(GAMMA_16APSK)[rng.integers(len(GAMMA_16APSK))]
        elif mod == "32APSK":
            rate = list(GAMMA_32APSK)[rng.integers(len(GAMMA_32APSK))]
        power = rs * 10 ** (rng.uniform(-2, 2) / 10)
        carriers.append(Carrier(f0=edge + w / 2, symbol_rate=rs, alpha=a, mod=mod, power=power, code_rate=rate))
        edge += w
    total = sum(c.power for c in carriers)
    return [Carrier(c.f0, c.symbol_rate, c.alpha, c.mod, c.power / total, c.code_rate) for c in carriers]


def raised_cosine_psd(f: np.ndarray, c: Carrier) -> np.ndarray:
    """Expected PSD of an SRRC-shaped carrier (power / Hz), integrating to c.power."""
    d = np.abs(f - c.f0)
    lo, hi = (1 - c.alpha) * c.symbol_rate / 2, (1 + c.alpha) * c.symbol_rate / 2
    rc = np.where(d <= lo, 1.0, 0.0)
    roll = (d > lo) & (d < hi)
    rc = np.where(roll, 0.5 * (1 + np.cos(np.pi * (d - lo) / (c.alpha * c.symbol_rate))), rc)
    return c.power / c.symbol_rate * rc


def monitor_freqs(n_bins: int = N_BINS, fs_mon: float = FS_MON) -> np.ndarray:
    return np.fft.fftshift(np.fft.fftfreq(n_bins, 1 / fs_mon))


def plan_mask_db(carriers: list[Carrier], floor_db: float = -60.0) -> np.ndarray:
    """Expected planned PSD on the monitor grid, dB relative to its peak, floored."""
    f = monitor_freqs()
    psd = sum(raised_cosine_psd(f, c) for c in carriers)
    return np.maximum(10 * np.log10(np.maximum(psd / psd.max(), 1e-30)), floor_db).astype(np.float32)


__all__ = ["random_plan", "plan_mask_db", "raised_cosine_psd", "monitor_freqs", "SYMBOL_RATES", "FS_SIM"]

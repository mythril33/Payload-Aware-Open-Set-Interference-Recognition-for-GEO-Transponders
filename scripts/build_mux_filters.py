"""Build FIR models of the reference IMUX/OMUX from the ETSI TR 102 376-2 Annex E tables.

Usage: python scripts/build_mux_filters.py <dir with 36_MHz_IMUX.txt and 36_MHz_OMUX.txt>
Writes src/geosim/data/mux_fir.npz with complex taps at 288 MHz for 36 and 72 MHz transponders.
Other bandwidths follow EN 302 307-1 H.7 / TR 102 376-2 4.4.1.2:
R(f) = Rejection(f * 36/BW), G(f) = (36/BW) * GroupDelay(f * 36/BW).
"""
import sys
from pathlib import Path

import numpy as np

FS = 288e6
N_TAPS = 1024
BULK_DELAY = 256        # samples; makes the truncated impulse response causal


def read_table(path):
    rows = []
    for line in Path(path).read_text().splitlines()[4:]:
        parts = line.split()
        if len(parts) >= 3:
            rows.append([float(v) for v in parts[:3]])
    t = np.array(rows)
    return t[:, 0] * 1e6, t[:, 1], t[:, 2] * 1e-9      # Hz, dB, s


def response(table, bandwidth, f):
    """Complex response at frequencies f (Hz) for a transponder of the given bandwidth."""
    ft, gain_db, gd = table
    k = 36e6 / bandwidth
    order = np.argsort(f)
    fs_sorted = f[order]
    g = np.interp(fs_sorted * k, ft, gain_db)
    tau = k * np.interp(fs_sorted * k, ft, gd)
    tau -= np.interp(0.0, fs_sorted, tau)
    phase = -2 * np.pi * np.concatenate([[0.0], np.cumsum(0.5 * (tau[1:] + tau[:-1]) * np.diff(fs_sorted))])
    phase -= np.interp(0.0, fs_sorted, phase)
    h = np.empty(len(f), complex)
    h[order] = 10 ** (g / 20) * np.exp(1j * phase)
    return h


def fir(table, bandwidth):
    f = np.fft.fftfreq(N_TAPS, 1 / FS)
    h = response(table, bandwidth, f) * np.exp(-2j * np.pi * f * BULK_DELAY / FS)
    return np.fft.ifft(h).astype(np.complex64)


if __name__ == "__main__":
    src = Path(sys.argv[1])
    out = {"fs": FS, "bulk_delay": BULK_DELAY}
    for name in ("IMUX", "OMUX"):
        table = read_table(src / f"36_MHz_{name}.txt")
        for bw in (36, 72):
            taps = fir(table, bw * 1e6)
            out[f"{name.lower()}_{bw}"] = taps
            e = np.abs(taps) ** 2
            print(f"{name} {bw} MHz: energy in first/last 32 taps {e[:32].sum() / e.sum():.1e} / {e[-32:].sum() / e.sum():.1e}")
    target = Path("src/geosim/data/mux_fir.npz")
    target.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(target, **out)
    print("wrote", target, target.stat().st_size, "bytes")

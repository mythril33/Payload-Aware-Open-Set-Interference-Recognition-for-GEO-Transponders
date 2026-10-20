"""Noise power ratio (NPR) versus input back-off for every amplifier model.

    python scripts/npr_check.py --out docs/results/npr_check.json

The amplifier alone (no IMUX/OMUX) is driven by complex Gaussian noise,
band-limited to BANDWIDTH with a NOTCH removed, at the same fixed-gain back-off
definition as the chain (IBO referenced to single-carrier saturation, noise
power as the nominal load). NPR = mean output PSD in the occupied band outside
the notch (with a guard) / mean PSD in the notch centre. For memory-polynomial
models the fraction of drive samples above the measured amplitude is reported.

Physics check: when third-order products dominate, NPR rises about 2 dB per
dB of back-off. The linear chain gives the measurement floor.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from scipy.signal import welch

from geosim import FS_SIM
from geosim import payload as pl

AMPLIFIERS = ("dvbs2_nl", "dvbs2_lin", "saleh", "rapp_p2", "opendpd_apa", "opendpd_dpa")
BANDWIDTH = 32e6               # occupied noise band inside a 36 MHz transponder [assumption]
NOTCH = (2.0e6, 3.0e6)         # Hz, notch inside the band [assumption]
GUARD = 0.5e6                  # Hz excluded on each side of the notch and at the band edges
IBOS = tuple(float(i) for i in range(15))
N, NPERSEG, SEED = 2 ** 19, 4096, 0


def notched_noise(rng: np.random.Generator, n: int = N, fs: float = FS_SIM) -> np.ndarray:
    f = np.fft.fftfreq(n, 1 / fs)
    keep = (np.abs(f) <= BANDWIDTH / 2) & ~((f >= NOTCH[0]) & (f < NOTCH[1]))
    x = np.fft.ifft(np.fft.fft(rng.standard_normal(n) + 1j * rng.standard_normal(n)) * keep)
    return x / np.sqrt(np.mean(np.abs(x) ** 2))


def npr_db(y: np.ndarray, fs: float = FS_SIM) -> float:
    f, p = welch(y, fs=fs, window="hann", nperseg=NPERSEG, return_onesided=False, detrend=False)
    width = NOTCH[1] - NOTCH[0]
    centre = (f >= NOTCH[0] + 0.2 * width) & (f < NOTCH[1] - 0.2 * width)
    band = ((np.abs(f) <= BANDWIDTH / 2 - GUARD)
            & ~((f >= NOTCH[0] - GUARD) & (f < NOTCH[1] + GUARD)))
    return float(10 * np.log10(np.mean(p[band]) / np.mean(p[centre])))


def sweep(names=AMPLIFIERS, ibos=IBOS) -> dict:
    x = notched_noise(np.random.default_rng(SEED))
    out = {"bandwidth_hz": BANDWIDTH, "notch_hz": list(NOTCH), "guard_hz": GUARD, "n_samples": N,
           "nperseg": NPERSEG, "seed": SEED, "ibo_db": list(ibos), "amplifiers": {}}
    floor = npr_db(x)
    out["input_npr_db"] = floor
    for name in names:
        amp = pl.amplifier(name)
        rows = []
        for ibo in ibos:
            drive = amp.drive_gain(1.0, ibo) * x
            beyond = amp.out_of_range_fraction(drive) if hasattr(amp, "out_of_range_fraction") else None
            rows.append({"ibo_db": ibo, "npr_db": npr_db(amp(drive)), "linear_npr_db": npr_db(amp.linear(drive)),
                         "input_beyond_measured": beyond})
        hi = [r for r in rows if r["ibo_db"] >= 10]
        slope = float(np.polyfit([r["ibo_db"] for r in hi], [r["npr_db"] for r in hi], 1)[0])
        out["amplifiers"][name] = {"rows": rows, "slope_db_per_db_ibo_10_14": slope}
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    result = sweep()
    a.out.write_text(json.dumps(result, indent=1, allow_nan=False) + "\n")
    print(f"input notch depth {result['input_npr_db']:.1f} dB")
    for name, v in result["amplifiers"].items():
        cells = " ".join(f"{r['npr_db']:5.1f}" for r in v["rows"])
        print(f"{name:12s} {cells}  slope(10-14 dB) {v['slope_db_per_db_ibo_10_14']:.2f} dB/dB")

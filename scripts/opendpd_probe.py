"""Probe OpenDPD measured PA datasets before deriving amplifier models (P15 K11).

For each dataset directory (``train/test_{input,output}.csv`` with I,Q columns)
fit least-squares models on the train split and report test-split NMSE:
single linear gain, linear FIR (memory, no nonlinearity), memoryless odd/even
polynomial, and memory polynomials. Also reports gain compression and AM/PM of
the memoryless fit at the 99th-percentile input amplitude relative to the
median. Prints one strict-JSON line per dataset.

Raw OpenDPD data is not part of this repository; clone it outside Git:
    git clone https://github.com/lab-emi/OpenDPD data/external/opendpd
    python scripts/opendpd_probe.py data/external/opendpd/datasets/APA_200MHz ...
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import sys

import numpy as np

MODELS = {"linear_gain": (1, 0), "linear_fir_M8": (1, 8), "memoryless_K5": (5, 0),
          "memory_poly_K5_M4": (5, 4), "memory_poly_K5_M8": (5, 8)}


def load(path: pathlib.Path) -> np.ndarray:
    a = np.loadtxt(path, delimiter=",", skiprows=1)
    return a[:, 0] + 1j * a[:, 1]


def basis(x: np.ndarray, order: int, memory: int) -> np.ndarray:
    """Columns x[n-m] |x[n-m]|^k for k < order, m <= memory (zero initial state)."""
    cols = []
    for m in range(memory + 1):
        xm = np.concatenate([np.zeros(m, x.dtype), x[:len(x) - m]])
        cols += [xm * np.abs(xm) ** k for k in range(order)]
    return np.stack(cols, 1)


def nmse_db(y: np.ndarray, y_hat: np.ndarray) -> float:
    return float(10 * np.log10(np.sum(np.abs(y - y_hat) ** 2) / np.sum(np.abs(y) ** 2)))


def probe(d: pathlib.Path) -> dict:
    xs, ys, xt, yt = (load(d / f"{s}_{io}.csv") for s in ("train", "test") for io in ("input", "output"))
    out = {"dataset": d.name, "n_train": len(xs), "n_test": len(xt),
           "sha256_train_input": hashlib.sha256((d / "train_input.csv").read_bytes()).hexdigest(),
           "papr_in_db": float(10 * np.log10(np.max(np.abs(xs) ** 2) / np.mean(np.abs(xs) ** 2)))}
    for name, (k, m) in MODELS.items():
        c, *_ = np.linalg.lstsq(basis(xs, k, m), ys, rcond=None)
        out[f"nmse_{name}_db"] = nmse_db(yt, basis(xt, k, m) @ c)
    c0, *_ = np.linalg.lstsq(basis(xs, 5, 0), ys, rcond=None)
    gain = lambda a: np.polyval(c0[::-1], a)        # complex gain at input amplitude a
    r = np.abs(xs)
    g_hi, g_lo = gain(np.quantile(r, 0.99)), gain(np.median(r))
    out["gain_change_db_p99_vs_median"] = float(20 * np.log10(abs(g_hi) / abs(g_lo)))
    out["am_pm_deg_p99_vs_median"] = float(np.degrees(np.angle(g_hi / g_lo)))
    return out


if __name__ == "__main__":
    for arg in sys.argv[1:]:
        print(json.dumps(probe(pathlib.Path(arg))))

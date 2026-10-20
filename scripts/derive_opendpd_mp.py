"""Fit memory polynomials to OpenDPD PA measurements -> src/geosim/data/opendpd_mp.json.

    git clone https://github.com/lab-emi/OpenDPD data/external/opendpd
    python scripts/derive_opendpd_mp.py data/external/opendpd

Input is normalized to the train-split RMS input, output to the train-split
best linear gain. The (order, memory) pair is chosen on the validation split
only: the smallest model within TOLERANCE_DB of the best validation NMSE.
Test-split NMSE is computed once, after selection, and only reported.
Raw OpenDPD files are not copied; their SHA-256 and the repository commit are
stored. OpenDPD is Apache-2.0 (https://github.com/lab-emi/OpenDPD); cite
Wu et al., ISCAS 2024 (doi:10.1109/ISCAS58744.2024.10558162) and OpenDPDv2
(arXiv:2507.06849).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

import numpy as np

from geosim.payload import mp_basis

MODELS = {
    "opendpd_apa": ("APA_200MHz", "Ampleon GaN Doherty PA, 3.5 GHz, 41.5 dBm average output "
                                  "(OpenDPD docs/whats-new.md); 5 x 20 MHz LTE TM3.1a"),
    "opendpd_dpa": ("DPA_200MHz", "40 nm CMOS digital Doherty transmitter, 2.4 GHz "
                                  "(OpenDPD docs/whats-new.md); 10 x 20 MHz, 64QAM"),
}
ORDERS = (1, 3, 5, 7)
MEMORIES = (0, 1, 2, 3, 4, 6, 8, 12, 16)
TOLERANCE_DB = 0.1
SPLITS = ("train", "val", "test")


def _load(path: Path) -> np.ndarray:
    a = np.loadtxt(path, delimiter=",", skiprows=1)
    if a.ndim != 2 or a.shape[1] != 2 or not np.isfinite(a).all():
        raise ValueError(f"{path}: expected finite I,Q columns")
    return a[:, 0] + 1j * a[:, 1]


def _nmse_db(y, y_hat) -> float:
    return float(10 * np.log10(np.sum(np.abs(y - y_hat) ** 2) / np.sum(np.abs(y) ** 2)))


def fit_model(data: dict, orders=ORDERS, memories=MEMORIES, tolerance_db=TOLERANCE_DB) -> dict:
    """data: {split: (input, output)} complex arrays. Returns the selected normalized model."""
    x_tr, y_tr = data["train"]
    rms = float(np.sqrt(np.mean(np.abs(x_tr) ** 2)))
    gain = complex(np.vdot(x_tr, y_tr) / np.vdot(x_tr, x_tr))
    norm = {s: (x / rms, y / (gain * rms)) for s, (x, y) in data.items()}
    u_tr, v_tr = norm["train"]
    grid, fits = [], {}
    for order in orders:
        for memory in memories:
            delays = range(memory + 1)
            c, *_ = np.linalg.lstsq(mp_basis(u_tr, order, delays), v_tr, rcond=None)
            u_va, v_va = norm["val"]
            grid.append({"order": order, "memory": memory,
                         "n_coefficients": order * (memory + 1),
                         "val_nmse_db": _nmse_db(v_va, mp_basis(u_va, order, delays) @ c)})
            fits[order, memory] = c
    best = min(g["val_nmse_db"] for g in grid)
    chosen = min((g for g in grid if g["val_nmse_db"] <= best + tolerance_db),
                 key=lambda g: (g["n_coefficients"], g["val_nmse_db"]))
    order, memory = chosen["order"], chosen["memory"]
    c = fits[order, memory]
    u_te, v_te = norm["test"]
    return {"order": order, "memory": memory,
            "coefficients_re": c.real.tolist(), "coefficients_im": c.imag.tolist(),
            "rms_input": rms, "linear_gain_re": gain.real, "linear_gain_im": gain.imag,
            "clip_amplitude": float(np.max(np.abs(u_tr))),
            "val_nmse_db": chosen["val_nmse_db"],
            "test_nmse_db": _nmse_db(v_te, mp_basis(u_te, order, range(memory + 1)) @ c),
            "selection": {"criterion": f"smallest model within {tolerance_db} dB of the best validation NMSE",
                          "grid": grid},
            "n_samples": {s: int(len(x)) for s, (x, _) in data.items()}}


def derive(repo: Path) -> dict:
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True,
                            check=True).stdout.strip()
    out = {"source": {"repository": "https://github.com/lab-emi/OpenDPD", "commit": commit,
                      "license": "Apache-2.0",
                      "citation": "Wu et al., ISCAS 2024, doi:10.1109/ISCAS58744.2024.10558162; OpenDPDv2, arXiv:2507.06849",
                      "note": "Coefficients derived in this project; measured devices are solid-state PAs, not TWTAs."},
           "basis": "y[n] = sum_m sum_k c[m*order+k] x[n-m] |x[n-m]|^k at the measurement rate, k < order",
           "models": {}}
    for name, (dataset, device) in MODELS.items():
        d = repo / "datasets" / dataset
        spec = json.loads((d / "spec.json").read_text())
        files = {f"{s}_{io}.csv": d / f"{s}_{io}.csv" for s in SPLITS for io in ("input", "output")}
        data = {s: (_load(files[f"{s}_input.csv"]), _load(files[f"{s}_output.csv"])) for s in SPLITS}
        model = fit_model(data)
        model.update(dataset=dataset, device=device, fs_hz=float(spec["input_signal_fs"]),
                     occupied_bandwidth_hz=float(spec["bw_main_ch"]),
                     files_sha256={k: hashlib.sha256(p.read_bytes()).hexdigest() for k, p in files.items()})
        out["models"][name] = model
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("opendpd", type=Path, help="local OpenDPD clone")
    ap.add_argument("--out", type=Path, default=Path(__file__).resolve().parents[1] / "src/geosim/data/opendpd_mp.json")
    a = ap.parse_args()
    result = derive(a.opendpd)
    a.out.write_text(json.dumps(result, indent=1, allow_nan=False) + "\n")
    for name, m in result["models"].items():
        print(f"{name}: order {m['order']}, memory {m['memory']}, val {m['val_nmse_db']:.2f} dB, "
              f"test {m['test_nmse_db']:.2f} dB, clip {m['clip_amplitude']:.2f} x RMS")

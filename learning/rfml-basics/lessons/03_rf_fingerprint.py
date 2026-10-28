"""Lesson 03: RF fingerprinting. Can a 1D ResNet tell devices apart by their hardware?

Question: every device sends the same QPSK, so only the hardware impairments (IQ gain
and phase, PA compression, phase noise, DC offset) can identify it. Does the network
recognise known devices from new frames, and does the ideal-device control stay at chance?
Look at: the impaired column against the ideal control. With identical devices the accuracy
should sit near chance, 1/10 at full size. Binomial SE = sqrt(p(1-p)/n) with p = 0.1: about
0.044 per SNR row (n of 30 to 62 per row in the full run) and 0.012 overall (n = 600),
so gaps of that size are noise. The split is by FRAME on purpose.
Run: python lessons/03_rf_fingerprint.py [--quick]
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))  # makes `import rfml` work from any cwd

import matplotlib  # noqa: E402

matplotlib.use("Agg")  # headless; the figure helpers draw on Figure, so pyplot is not needed

import torch  # noqa: E402

from rfml import experiments as ex  # noqa: E402

# RFML_RESULTS_DIR lets the tests write elsewhere. The default is the committed results/.
RESULTS_DIR = Path(os.environ.get("RFML_RESULTS_DIR") or REPO / "results")
NAME = "03_rf_fingerprint"
SEED = 3  # the Streamlit app's default; both runs share it, so `impaired` is the only difference

# Why this lesson splits by FRAME (the one exception to the device-level rule):
# the device IS the label, so every device must appear in training, and a split by device
# would leave nothing to classify. Frames of one device share its hardware, so the test
# measures recognition of KNOWN devices from NEW frames, not transfer to a new device.
# The split (60/20/20 within each device) is made inside rfml/experiments.py.


def _fmt(value: float | None) -> str:
    return "   null" if value is None else f"{value:7.3f}"


def print_table(impaired: dict, ideal: dict) -> None:
    """Per-SNR accuracy for both runs. Each run has its own frames, so n is shown per column."""
    chance = impaired["chance_level"]
    print(f"RF fingerprinting, {impaired['devices_in_test']} test devices, chance = {chance:.3f}")
    print(f"{'SNR dB':>7} {'n':>5} {'impaired':>9} {'n':>5} {'ideal':>9}")
    for a, b in zip(impaired["per_snr"], ideal["per_snr"]):
        print(
            f"{a['snr_db']:>7.0f} {a['n']:>5} {_fmt(a['accuracy']):>9} "
            f"{b['n']:>5} {_fmt(b['accuracy']):>9}"
        )
    print(
        f"{'overall':>7} {impaired['overall']['n']:>5} {_fmt(impaired['overall']['accuracy']):>9} "
        f"{ideal['overall']['n']:>5} {_fmt(ideal['overall']['accuracy']):>9}"
    )
    print(f"ideal control (identical devices) should sit near chance {chance:.3f}")
    print(
        f"best epoch {impaired['best_epoch'] + 1} of {impaired['epochs_run']} (impaired); "
        f"val-select accuracy {_fmt(impaired['val_select_accuracy_best']).strip()}"
    )


def _log(tag: str):
    """Progress callback that prefixes each status line with the run it belongs to."""
    return lambda message: print(f"[{tag}] {message}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Lesson 03: RF fingerprinting with a 1D ResNet.")
    parser.add_argument("--quick", action="store_true", help="quick preset: 4 devices, few frames, 2 epochs")
    args = parser.parse_args()
    scale = ex.get_scale("quick" if args.quick else "full")
    mode = "quick" if args.quick else "default"  # "default" is the full preset
    torch.set_num_threads(4)
    t0 = time.perf_counter()

    impaired = ex.run_fingerprint(scale, impaired=True, seed=SEED, progress=_log("impaired"))
    ideal = ex.run_fingerprint(scale, impaired=False, seed=SEED, progress=_log("ideal control"))
    print_table(impaired, ideal)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_json = RESULTS_DIR / f"{NAME}.json"
    payload = {"lesson": NAME, "mode": mode, "runs": {"impaired": impaired, "ideal_ablation": ideal}}
    out_json.write_text(ex.to_strict_json(payload))
    ex.fig_fingerprint([impaired, ideal]).savefig(RESULTS_DIR / f"{NAME}.png", dpi=110)
    print(f"mode={mode} elapsed={time.perf_counter() - t0:.1f}s")
    print(f"wrote {out_json}")


if __name__ == "__main__":
    main()

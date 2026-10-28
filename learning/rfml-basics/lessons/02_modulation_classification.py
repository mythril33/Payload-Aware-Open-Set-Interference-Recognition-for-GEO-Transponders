"""Lesson 02: closed-set modulation classification with hardware impairments.

Question: trained on BPSK, QPSK, 8PSK and 16QAM from devices it has seen, does a
classifier recognise the same modulations from NEW devices, and how does accuracy fall
with SNR (including -6 dB, below the training range)?
Look at: the per-SNR table (n on every row; chance 1/4), the CNN1D curve against the
MLP curve, and the 'overall' row. The split is by device, so no test device was seen in
training. Frames of one device are correlated, so n overstates independent samples.
Run: python lessons/02_modulation_classification.py [--quick]
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
NAME = "02_modulation_classification"
SEED = 2  # the Streamlit app's default, so the lesson and the app print the same numbers

# Role split (seeds and leakage rules live in rfml/experiments.py):
#   train      -> weights only: 40 devices per modulation at full size, 20 frames each
#   val-select -> checkpoint choice only: 10 other devices per modulation
#   test       -> reported once per SNR: 10 more devices per modulation, reused at every SNR
# A device is a modulation plus its hardware (IQ gain and phase, DC offset, phase noise,
# PA saturation). impaired=True gives each device its own hardware, so the device split is
# a real split. Each device lands in exactly one role.


def _fmt(value: float | None) -> str:
    return "   null" if value is None else f"{value:7.3f}"


def print_table(result: dict) -> None:
    """Per-SNR accuracy for each model, the pooled row, then checkpoint-selection numbers."""
    runs = result["models"]
    names = list(runs)
    chance = result["chance_level"]
    print(f"Closed-set modulation classification, chance = {chance:.3f} ({len(result['classes'])} classes)")
    print(f"{'SNR dB':>7} {'n':>5} " + " ".join(f"{m:>7}" for m in names))
    first_train_snr = min(result["train_snr_db"])
    for i, row in enumerate(runs[names[0]]["per_snr"]):
        cells = " ".join(_fmt(runs[m]["per_snr"][i]["accuracy"]) for m in names)
        note = "  <- below training SNRs" if row["snr_db"] < first_train_snr else ""
        print(f"{row['snr_db']:>7.0f} {row['n']:>5} {cells}{note}")
    overall_cells = " ".join(_fmt(runs[m]["overall"]["accuracy"]) for m in names)
    print(f"{'overall':>7} {runs[names[0]]['overall']['n']:>5} {overall_cells}")
    print()
    print(f"{'model':>7} {'val-sel':>7} {'best ep':>8} {'epochs':>7}   (val-select scored the checkpoint)")
    for m in names:
        r = runs[m]
        print(f"{m:>7} {_fmt(r['val_select_accuracy_best'])} {r['best_epoch'] + 1:>8} {r['epochs_run']:>7}")


def progress(message: str) -> None:
    print(message, flush=True)  # one status line per epoch, flushed for long runs


def main() -> None:
    parser = argparse.ArgumentParser(description="Lesson 02: closed-set modulation classification.")
    parser.add_argument("--quick", action="store_true", help="quick preset, a smoke test of about a minute")
    args = parser.parse_args()
    scale = ex.get_scale("quick" if args.quick else "full")
    mode = "quick" if args.quick else "default"  # "default" is the full preset
    torch.set_num_threads(4)
    t0 = time.perf_counter()

    # impaired=True: every device has its own hardware. The seed fixes devices, frames and weights.
    result = ex.run_modulation(scale, impaired=True, seed=SEED, progress=progress)
    print_table(result)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_json = RESULTS_DIR / f"{NAME}.json"
    out_json.write_text(ex.to_strict_json({"lesson": NAME, "mode": mode, **result}))
    ex.fig_modulation(result).savefig(RESULTS_DIR / f"{NAME}.png", dpi=110)
    print(f"mode={mode} elapsed={time.perf_counter() - t0:.1f}s")
    print(f"wrote {out_json}")


if __name__ == "__main__":
    main()

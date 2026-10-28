"""Lesson 04: open-set recognition. Can a classifier say "none of the above"?

Question: trained on BPSK, QPSK, 8PSK and 16QAM only, can a score separate frames of
two never-seen modulations (64QAM, 4PAM) from known frames? Three variants are compared
at a threshold calibrated on KNOWN data only (95% known acceptance).
Look at: the known-accept and unknown-reject rates (each with its count), AUROC with
positive class = unknown, the closed-set accuracy on accepted frames, and the histograms
in the PNG. The Objectosphere variant trains on 16PSK and 8PAM outliers, so its
rejection rates are an optimistic bound.
Run: python lessons/04_open_set.py [--quick]
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
NAME = "04_open_set"
SEED = 4  # the Streamlit app's default; each variant trains with SEED plus its offset

# Role split (seeds and leakage rules live in rfml/experiments.py):
#   train        -> weights and distance centroids: known devices, plus 16PSK/8PAM outliers
#                   (label -1) for the Objectosphere variant only
#   val-select   -> checkpoint choice, known frames only
#   val-calib    -> threshold, KNOWN frames only
#   test-known   -> known devices never seen in training
#   test-unknown -> 64QAM and 4PAM devices, scored only after the threshold is fixed
# The known validation devices are halved BY DEVICE into val-select and val-calib.
# The threshold is the smallest value that accepts 95% of val-calib frames. It never sees
# unknown frames, so the unknown-reject rate is an honest test.


def _rate(k: int, n: int) -> str:
    return f"{k / n:.3f} ({k}/{n})" if n else "null (0/0)"


def print_table(result: dict) -> None:
    """One row per variant: threshold, the two rates with counts, AUROC, closed-set accuracy."""
    print(f"Open-set recognition, threshold at {result['target_known_accept']:.0%} known acceptance on val-calib")
    header = (
        f"{'variant':<22}{'threshold':>10}  {'known accepted (k/n)':<24}"
        f"{'unknown rejected (k/n)':<26}{'AUROC':>7}  closed-set acc on accepted (k/n)"
    )
    print(header)
    for name, v in result["variants"].items():
        rep = v["report"]
        cs = v["closed_set_on_accepted"]
        auroc = "null" if rep["auroc"] is None else f"{rep['auroc']:.3f}"
        print(
            f"{name:<22}{v['threshold']:>10.4f}  "
            f"{_rate(v['known_accepted'], rep['n_known']):<24}"
            f"{_rate(v['unknown_rejected'], rep['n_unknown']):<26}{auroc:>7}  "
            f"{_rate(cs['n_correct'], cs['n'])}"
        )
    print(
        "Rates are on test devices; the threshold is fixed on val-calib, so they can differ from 95%. "
        "AUROC positive class = unknown; AUROC < 0.5 means unknown frames are more confident than "
        "known frames (not a sign error)."
    )


def progress(message: str) -> None:
    print(message, flush=True)  # one status line per epoch and variant, flushed for long runs


def main() -> None:
    parser = argparse.ArgumentParser(description="Lesson 04: open-set recognition with unknown modulations.")
    parser.add_argument("--quick", action="store_true", help="quick preset, a smoke test of about a minute")
    args = parser.parse_args()
    scale = ex.get_scale("quick" if args.quick else "full")
    mode = "quick" if args.quick else "default"  # "default" is the full preset
    torch.set_num_threads(4)
    t0 = time.perf_counter()

    # xi and lam are the Objectosphere defaults (Dhamija et al., 2018); the target is 95%.
    result = ex.run_open_set(
        scale,
        SEED,
        ex.DEFAULT_XI,
        ex.DEFAULT_LAM,
        ex.DEFAULT_TARGET_KNOWN_ACCEPT,
        progress=progress,
    )
    print_table(result)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_json = RESULTS_DIR / f"{NAME}.json"
    out_json.write_text(ex.to_strict_json({"lesson": NAME, "mode": mode, **result}))
    ex.fig_open_set(result).savefig(RESULTS_DIR / f"{NAME}.png", dpi=110)
    print(f"mode={mode} elapsed={time.perf_counter() - t0:.1f}s")
    print(f"wrote {out_json}")


if __name__ == "__main__":
    main()

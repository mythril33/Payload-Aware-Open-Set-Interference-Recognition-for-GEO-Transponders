"""Lesson 03: RF fingerprinting. Can a 1D ResNet tell devices apart by their hardware?

Question: every device sends the same QPSK, so only the hardware impairments (IQ
gain and phase, PA compression, phase noise, DC offset) can identify the device.
Look at: the impaired-device accuracy against the ideal-device ablation. With identical
devices the accuracy must sit near chance, 1/N_DEVICES, which the output states. The
split is FRAME-level on purpose, because the device is the label (see the comment in
run_fingerprint before you compare these numbers with lesson 02).

Run: python lessons/03_rf_fingerprint.py [--quick]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # makes `import rfml` work from any cwd

import matplotlib  # noqa: E402

matplotlib.use("Agg")  # headless; must come before pyplot is imported
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import torch  # noqa: E402

from rfml.dataset import ModulationDataset, build_frames, make_transmitters, split_frames_stratified  # noqa: E402
from rfml.metrics import accuracy  # noqa: E402
from rfml.models import ResNet1D  # noqa: E402
from rfml.train import TrainConfig, accuracy_val_score, ce_loss, predict_logits, set_seed, train_model  # noqa: E402

RESULTS = Path(__file__).resolve().parents[1] / "results"
N_SAMPLES = 512
TRAIN_SNRS = tuple(float(s) for s in np.arange(-4, 21, 2))  # same SNR grid as lesson 02 training
SPLIT_FRACTIONS = (0.6, 0.2, 0.2)  # train / val-select / test, frame-level within each device
SEED = 3


# ---------------------------------------------------------------------------
# Why this lesson splits by FRAME (the one exception to the device-level rule)
# In lesson 02 the device is a nuisance: the label is the modulation, so unseen devices
# are the honest test. Here the device IS the label, so every device must appear in
# train, and a split by device would leave nothing to classify. Frames of one device
# share its hardware fingerprint, so the test measures recognition of KNOWN devices
# from NEW frames. It does NOT test generalisation to a new device. Read these numbers
# as "can the hardware be recognised", not "does the recogniser transfer".
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Sizes:
    mode: str
    n_devices: int
    frames_per_device: int
    epochs: int


DEFAULT = Sizes("default", n_devices=10, frames_per_device=300, epochs=25)
QUICK = Sizes("quick", n_devices=4, frames_per_device=40, epochs=2)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Lesson 03: RF fingerprinting with a 1D ResNet.")
    parser.add_argument("--quick", action="store_true", help="4 devices, few frames and 2 epochs")
    return parser.parse_args()


def run_fingerprint(sz: Sizes, impaired: bool, seed: int) -> dict:
    """Train and evaluate one fingerprinting run with impaired or identical devices."""
    rng = np.random.default_rng(seed)
    devices = make_transmitters(["QPSK"], sz.n_devices, rng, impaired=impaired)
    data = build_frames(devices, sz.frames_per_device, N_SAMPLES, TRAIN_SNRS, rng, class_names=("QPSK",))

    # build_frames labels every frame 0 (QPSK). The fingerprint target is the DEVICE,
    # so use tx_id as the label. dict(...) copies the mapping; `data` itself is unchanged.
    fp = dict(data, label=data["tx_id"])
    train_idx, val_idx, test_idx = split_frames_stratified(data["tx_id"], SPLIT_FRACTIONS, rng)
    assert train_idx.size and val_idx.size and test_idx.size, "frames_per_device too small to split"

    set_seed(seed)
    model = ResNet1D(n_classes=sz.n_devices, base_width=16)
    hist = train_model(
        model,
        ModulationDataset(fp, train_idx),
        ModulationDataset(fp, val_idx),
        ce_loss,  # cross entropy over device IDs, no outliers in this stage
        TrainConfig(epochs=sz.epochs, seed=seed),
        accuracy_val_score,  # model selection on val-select frames only
    )

    # Test is evaluated once, per SNR. Bins come from the frame-level test split, so the
    # n on each row is the number of test frames at that exact SNR.
    per_snr = []
    for snr in TRAIN_SNRS:
        sel = test_idx[np.isclose(data["snr_db"][test_idx], snr, atol=1e-3)]
        pred = predict_logits(model, data["iq"][sel]).argmax(axis=1)
        per_snr.append({"snr_db": snr, "n": int(sel.size), "accuracy": accuracy(pred, data["tx_id"][sel])})
    pred_all = predict_logits(model, data["iq"][test_idx]).argmax(axis=1)
    overall = {"n": int(test_idx.size), "accuracy": accuracy(pred_all, data["tx_id"][test_idx])}

    best = hist["best_epoch"]
    return {
        "impaired": impaired,
        "chance_level": 1.0 / sz.n_devices,
        "frames": {"train": int(train_idx.size), "val_select": int(val_idx.size), "test": int(test_idx.size)},
        "devices_in_test": int(np.unique(data["tx_id"][test_idx]).size),
        "epochs_run": len(hist["train_loss"]),
        "best_epoch": best,
        "val_select_accuracy_best": hist["val_score"][best],
        "per_snr": per_snr,
        "overall": overall,
    }


def _fmt(value: float | None) -> str:
    return "   null" if value is None else f"{value:7.3f}"


def print_table(impaired: dict, ideal: dict) -> None:
    chance = impaired["chance_level"]
    print(f"RF fingerprinting, {impaired['devices_in_test']} test devices, chance = {chance:.3f}")
    print(f"{'SNR dB':>7} {'n':>5} {'impaired':>9} {'ideal':>9}")
    for a, b in zip(impaired["per_snr"], ideal["per_snr"]):
        print(f"{a['snr_db']:>7.0f} {a['n']:>5} {_fmt(a['accuracy']):>9} {_fmt(b['accuracy']):>9}")
    print(
        f"{'overall':>7} {impaired['overall']['n']:>5} "
        f"{_fmt(impaired['overall']['accuracy']):>9} {_fmt(ideal['overall']['accuracy']):>9}"
    )
    print(f"ideal ablation (identical devices) should sit near chance {chance:.3f}")


def save_plot(impaired: dict, ideal: dict, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(6.4, 4.0))
    for run, label in ((impaired, "impaired devices"), (ideal, "ideal devices (ablation)")):
        xs = [r["snr_db"] for r in run["per_snr"]]
        ys = [np.nan if r["accuracy"] is None else r["accuracy"] for r in run["per_snr"]]
        ax.plot(xs, ys, marker="o", label=label)
    chance = impaired["chance_level"]
    ax.axhline(chance, color="grey", ls="--", label=f"chance 1/{round(1 / chance)}")
    ax.set(
        xlabel="SNR (dB)",
        ylabel="test accuracy (frame-level split)",
        ylim=(0.0, 1.02),
        title="RF fingerprinting, one QPSK per device",
    )
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


def main() -> None:
    args = parse_args()
    sz = QUICK if args.quick else DEFAULT
    torch.set_num_threads(4)
    t0 = time.perf_counter()

    impaired = run_fingerprint(sz, impaired=True, seed=SEED)
    ideal = run_fingerprint(sz, impaired=False, seed=SEED + 1)
    print_table(impaired, ideal)

    payload = {
        "lesson": "03_rf_fingerprint",
        "mode": sz.mode,
        "n_devices": sz.n_devices,
        "modulation": "QPSK",
        "n_samples": N_SAMPLES,
        "frames_per_device": sz.frames_per_device,
        "split": "frame-level within each device (device is the label), fractions train/val/test = 0.6/0.2/0.2",
        "train_snr_db": list(TRAIN_SNRS),
        "chance_level": 1.0 / sz.n_devices,
        "runs": {"impaired": impaired, "ideal_ablation": ideal},
    }
    RESULTS.mkdir(exist_ok=True)
    # allow_nan=False: a NaN would raise here instead of writing invalid JSON.
    (RESULTS / "03_rf_fingerprint.json").write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n")
    save_plot(impaired, ideal, RESULTS / "03_rf_fingerprint.png")
    print(f"mode={sz.mode} elapsed={time.perf_counter() - t0:.1f}s")
    print(f"wrote {RESULTS / '03_rf_fingerprint.json'}")


if __name__ == "__main__":
    main()

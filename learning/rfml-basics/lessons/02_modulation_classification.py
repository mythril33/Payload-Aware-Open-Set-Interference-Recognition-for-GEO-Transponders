"""Lesson 02: closed-set modulation classification with hardware impairments.

Question: trained on BPSK, QPSK, 8PSK and 16QAM from devices it has seen, does a
classifier recognise the same modulations from NEW devices, and how does accuracy fall
with SNR (including -6 dB, below the training range)?
Look at: the per-SNR table (n on every row; chance 1/4), the CNN1D curve against the
MLP curve, and the 'overall' row. Then compare each model's train accuracy with its test
accuracy. An MLP has no shift or phase invariance, so it can memorise its training devices:
train near 1.0 with test near chance is memorisation, not a broken pipeline. Frames of one
device are correlated, so n overstates independent samples.
Run: python lessons/02_modulation_classification.py [--quick]
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

from rfml.dataset import ModulationDataset, build_frames, make_transmitters  # noqa: E402
from rfml.metrics import accuracy, confusion_matrix  # noqa: E402
from rfml.models import CNN1D, MLP  # noqa: E402
from rfml.signals import KNOWN_MODULATIONS  # noqa: E402
from rfml.train import TrainConfig, accuracy_val_score, ce_loss, predict_logits, set_seed, train_model  # noqa: E402

RESULTS = Path(__file__).resolve().parents[1] / "results"
N_SAMPLES = 512
N_CLASSES = len(KNOWN_MODULATIONS)
CHANCE = 1.0 / N_CLASSES
TRAIN_SNRS = tuple(float(s) for s in np.arange(-4, 21, 2))  # training and val-select frames
TEST_SNRS = tuple(float(s) for s in np.arange(-6, 21, 2))  # -6 dB is below the training range
SEED = 2


# ---------------------------------------------------------------------------
# Role split (leakage rules: see rfml/dataset.py and rfml/train.py)
#   train      -> weights only: 40 devices per modulation, 20 frames each
#   val-select -> checkpoint choice only: 10 other devices per modulation
#   test       -> reported once per SNR: 10 more devices per modulation
# The split is BY DEVICE, not by frame. A device's modulation and its hardware
# (IQ gain and phase, DC offset, phase noise, PA saturation) form one fingerprint.
# If frames of one device were in both train and test, the network could memorise
# the device, and test accuracy would measure memorisation, not modulation recognition.
# Test devices are drawn once and reused at every SNR, so the per-SNR curve compares
# the same devices.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Sizes:
    mode: str
    tx_train: int  # devices per modulation
    tx_val: int
    tx_test: int
    frames_train: int  # frames per device
    frames_val: int
    frames_test: int  # per device and per SNR
    epochs: int


DEFAULT = Sizes("default", 40, 10, 10, 20, 10, 10, epochs=25)
QUICK = Sizes("quick", 6, 3, 3, 5, 3, 3, epochs=2)

MODEL_BUILDERS = {
    "MLP": lambda: MLP(n_classes=N_CLASSES, n_samples=N_SAMPLES),
    "CNN1D": lambda: CNN1D(n_classes=N_CLASSES),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Lesson 02: closed-set modulation classification.")
    parser.add_argument("--quick", action="store_true", help="tiny sizes and 2 epochs, for a smoke test")
    return parser.parse_args()


def build_data(sz: Sizes) -> tuple[dict, dict[float, dict]]:
    """Generate train, val-select and per-SNR test frames from disjoint devices."""
    rng = np.random.default_rng(SEED)
    tx_train = make_transmitters(KNOWN_MODULATIONS, sz.tx_train, rng)
    tx_val = make_transmitters(KNOWN_MODULATIONS, sz.tx_val, rng)
    tx_test = make_transmitters(KNOWN_MODULATIONS, sz.tx_test, rng)  # reused at every SNR

    train = build_frames(tx_train, sz.frames_train, N_SAMPLES, TRAIN_SNRS, rng, KNOWN_MODULATIONS)
    val = build_frames(tx_val, sz.frames_val, N_SAMPLES, TRAIN_SNRS, rng, KNOWN_MODULATIONS)
    test_by_snr = {
        snr: build_frames(tx_test, sz.frames_test, N_SAMPLES, [snr], rng, KNOWN_MODULATIONS) for snr in TEST_SNRS
    }
    # Sanity: every frame of a known modulation must carry a real class label.
    assert (train["label"] >= 0).all() and (val["label"] >= 0).all()
    return train, val, test_by_snr


def evaluate(model: torch.nn.Module, test_by_snr: dict[float, dict]) -> tuple[list[dict], dict, list]:
    """Accuracy per SNR, pooled accuracy, and the pooled confusion matrix (rows = true)."""
    per_snr = []
    preds, labels = [], []
    for snr in TEST_SNRS:
        d = test_by_snr[snr]
        pred = predict_logits(model, d["iq"]).argmax(axis=1)
        per_snr.append({"snr_db": snr, "n": int(d["label"].size), "accuracy": accuracy(pred, d["label"])})
        preds.append(pred)
        labels.append(d["label"])
    pred_all, label_all = np.concatenate(preds), np.concatenate(labels)
    overall = {"n": int(label_all.size), "accuracy": accuracy(pred_all, label_all)}
    cm = confusion_matrix(pred_all, label_all, N_CLASSES).tolist()
    return per_snr, overall, cm


def run_model(name: str, sz: Sizes, train: dict, val: dict, test_by_snr: dict[float, dict]) -> dict:
    set_seed(SEED)  # fixes the weight initialisation
    model = MODEL_BUILDERS[name]()
    # Only val-select frames feed the checkpoint choice. Test is touched after training ends.
    hist = train_model(
        model,
        ModulationDataset(train),
        ModulationDataset(val),
        ce_loss,  # cross entropy on known classes
        TrainConfig(epochs=sz.epochs, seed=SEED),  # Adam, early stop after 5 flat epochs
        accuracy_val_score,  # closed-set accuracy on val-select, higher is better
    )
    per_snr, overall, cm = evaluate(model, test_by_snr)
    # Diagnostic only: train accuracy is never used for selection. It exposes memorisation,
    # since a large train-test gap means the model learned the training devices.
    train_accuracy = accuracy(predict_logits(model, train["iq"]).argmax(axis=1), train["label"])
    best = hist["best_epoch"]
    return {
        "epochs_run": len(hist["train_loss"]),
        "best_epoch": best,
        "train_accuracy": train_accuracy,
        "val_select_accuracy_best": hist["val_score"][best],
        "per_snr": per_snr,
        "overall": overall,
        "confusion_overall": cm,
    }


def _fmt(value: float | None) -> str:
    return "   null" if value is None else f"{value:7.3f}"


def print_table(runs: dict[str, dict]) -> None:
    names = list(runs)
    print(f"Closed-set modulation classification, chance = {CHANCE:.3f} ({N_CLASSES} classes)")
    print(f"{'SNR dB':>7} {'n':>5} " + " ".join(f"{name:>7}" for name in names))
    for i, snr in enumerate(TEST_SNRS):
        n = runs[names[0]]["per_snr"][i]["n"]
        cells = " ".join(_fmt(runs[m]["per_snr"][i]["accuracy"]) for m in names)
        note = "  <- below training SNRs" if snr < TRAIN_SNRS[0] else ""
        print(f"{snr:>7.0f} {n:>5} {cells}{note}")
    overall_n = runs[names[0]]["overall"]["n"]
    cells = " ".join(_fmt(runs[m]["overall"]["accuracy"]) for m in names)
    print(f"{'overall':>7} {overall_n:>5} {cells}")
    # Train and val-select sit next to test so a memorising model is visible at a glance.
    print()
    print(f"{'model':>7} {'train':>7} {'val-sel':>7} {'test':>7}   (accuracy; train >> test means memorisation)")
    for m in names:
        r = runs[m]
        print(
            f"{m:>7} {_fmt(r['train_accuracy'])} {_fmt(r['val_select_accuracy_best'])} "
            f"{_fmt(r['overall']['accuracy'])}"
        )


def save_plot(runs: dict[str, dict], path: Path) -> None:
    fig, ax = plt.subplots(figsize=(6.4, 4.0))
    for name, run in runs.items():
        xs = [r["snr_db"] for r in run["per_snr"]]
        ys = [np.nan if r["accuracy"] is None else r["accuracy"] for r in run["per_snr"]]
        ax.plot(xs, ys, marker="o", label=name)
    ax.axhline(CHANCE, color="grey", ls="--", label="chance 1/4")
    ax.axvspan(TEST_SNRS[0] - 1, TRAIN_SNRS[0], color="0.92", label="below training SNRs")
    ax.set(
        xlabel="SNR (dB)",
        ylabel="test accuracy (unseen devices)",
        ylim=(0.0, 1.02),
        title="Closed-set modulation classification",
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

    train, val, test_by_snr = build_data(sz)
    runs = {name: run_model(name, sz, train, val, test_by_snr) for name in MODEL_BUILDERS}
    print_table(runs)

    payload = {
        "lesson": "02_modulation_classification",
        "mode": sz.mode,
        "classes": list(KNOWN_MODULATIONS),
        "chance_level": CHANCE,
        "n_samples": N_SAMPLES,
        "train_snr_db": list(TRAIN_SNRS),
        "test_snr_db": list(TEST_SNRS),
        "devices_per_class": {"train": sz.tx_train, "val_select": sz.tx_val, "test": sz.tx_test},
        "frames_per_device": {"train": sz.frames_train, "val_select": sz.frames_val, "test_per_snr": sz.frames_test},
        "frames": {"train": int(train["label"].size), "val_select": int(val["label"].size)},
        "models": runs,
    }
    RESULTS.mkdir(exist_ok=True)
    # allow_nan=False: a NaN would raise here instead of writing invalid JSON.
    (RESULTS / "02_modulation_classification.json").write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n")
    save_plot(runs, RESULTS / "02_modulation_classification.png")
    print(f"mode={sz.mode} elapsed={time.perf_counter() - t0:.1f}s")
    print(f"wrote {RESULTS / '02_modulation_classification.json'}")


if __name__ == "__main__":
    main()

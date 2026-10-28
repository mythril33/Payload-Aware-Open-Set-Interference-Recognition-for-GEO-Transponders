"""Lesson 04: open-set recognition. Can a classifier say "none of the above"?

Question: trained on BPSK, QPSK, 8PSK and 16QAM only, can a score separate frames of
two never-seen modulations (64QAM, 4PAM) from known frames? Three variants are compared
at a threshold calibrated on KNOWN data only (95% known acceptance).
Look at: the known-accept and unknown-reject rates (each with its count), AUROC with
positive class = unknown, the closed-set accuracy on accepted frames, and the histograms
in the PNG. Variant (c) uses 8PAM outliers in training, so its result is optimistic.

Run: python lessons/04_open_set.py [--quick]
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
from torch import nn  # noqa: E402

from rfml.dataset import ModulationDataset, build_frames, make_transmitters  # noqa: E402
from rfml.metrics import accuracy, open_set_report  # noqa: E402
from rfml.models import CNN1D  # noqa: E402
from rfml.openset import (  # noqa: E402
    calibrate_threshold,
    class_centroids,
    distance_unknown_score,
    msp_unknown_score,
    objectosphere_loss,
)
from rfml.signals import AUX_OUTLIER_MODULATIONS, KNOWN_MODULATIONS, UNKNOWN_MODULATIONS  # noqa: E402
from rfml.train import (  # noqa: E402
    TrainConfig,
    accuracy_val_score,
    ce_loss,
    predict_embeddings,
    predict_logits,
    set_seed,
    train_model,
)

RESULTS = Path(__file__).resolve().parents[1] / "results"
KNOWN = KNOWN_MODULATIONS
AUX = AUX_OUTLIER_MODULATIONS
UNKNOWN = UNKNOWN_MODULATIONS
N_CLASSES = len(KNOWN)
N_SAMPLES = 512
SNRS = tuple(float(s) for s in np.arange(-4, 21, 2))  # one SNR grid for every split
TARGET_KNOWN_ACCEPT = 0.95
XI, LAM = 10.0, 0.1  # Objectosphere defaults from Dhamija et al. (2018)
SEED = 4


# ---------------------------------------------------------------------------
# Roles (leakage rules: see rfml/openset.py and rfml/train.py)
#   train        -> weights and distance centroids: known devices, plus aux outliers
#                   (label -1) for variant (c) ONLY
#   val-select   -> checkpoint choice (accuracy on known frames, no outliers)
#   val-calib    -> threshold calibration, KNOWN frames only
#   test-known   -> known devices never seen in training
#   test-unknown -> 64QAM and 4PAM devices, never used for training, selection or
#                   calibration. They are generated only to score the final decision.
# Known devices are drawn once and split BY DEVICE: the known validation devices are
# halved into val-select and val-calib, so the checkpoint and the threshold never share
# data. Sizes default to 40/10/10 known devices per class (train/val/test), as in
# lesson 02. Unknown and aux device counts are our choice (see Sizes).
# ---------------------------------------------------------------------------

# OPTIMISM WARNING for variant (c). 8PAM (aux outliers) and 4PAM (test unknown) are both
# PAM families with the same real-valued level structure, so "PAM-like is not my class"
# learned from 8PAM transfers to 4PAM more easily than to an arbitrary unseen modulation
# such as 64QAM. Treat (c)'s unknown-reject rate as an optimistic bound on what outlier
# exposure buys in general. 64QAM is also a close relative of the known 16QAM.


@dataclass(frozen=True)
class Sizes:
    mode: str
    tx_train: int  # known devices per class
    tx_val: int  # per class; halved into val-select and val-calib
    tx_test: int
    tx_aux: int  # per aux class (train-only outlier pool)
    tx_unknown: int  # per unknown class (test-only)
    frames_train: int  # per device
    frames_val: int
    frames_test: int
    epochs: int


DEFAULT = Sizes("default", 40, 10, 10, 20, 10, 20, 10, 10, epochs=25)
QUICK = Sizes("quick", 6, 3, 3, 3, 3, 5, 3, 3, epochs=2)


@dataclass(frozen=True)
class VariantSpec:
    name: str
    loss: str  # "ce" or "objectosphere"
    score: str  # "msp" or "distance"
    use_aux: bool  # True only if the training set includes the -1 outliers
    seed: int


# Each variant is its own training run with its own seed, as specified. (a) and (b) share
# the CE recipe but differ in seed too, so their gap mixes score and seed effects. A
# seed-matched rerun would isolate the score.
VARIANTS = (
    VariantSpec("CE + MSP", "ce", "msp", use_aux=False, seed=0),
    VariantSpec("CE + distance", "ce", "distance", use_aux=False, seed=1),
    VariantSpec("Objectosphere + MSP", "objectosphere", "msp", use_aux=True, seed=2),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Lesson 04: open-set recognition with unknown modulations.")
    parser.add_argument("--quick", action="store_true", help="tiny sizes and 2 epochs, for a smoke test")
    return parser.parse_args()


def split_val_devices(tx_val: list, per_class: int) -> tuple[list, list]:
    """Halve the known validation devices BY DEVICE within each class (select, calib)."""
    n_calib = per_class // 2
    n_select = per_class - n_calib
    select: list = []
    calib: list = []
    for c in range(N_CLASSES):  # make_transmitters returns devices grouped by class
        block = tx_val[c * per_class : (c + 1) * per_class]
        select += block[:n_select]
        calib += block[n_select:]
    return select, calib


def concat_frames(parts: list[dict]) -> dict:
    """Stack build_frames() outputs. tx_id is offset so device IDs stay unique."""
    iq, label, tx_id, snr = [], [], [], []
    offset = 0
    for p in parts:
        iq.append(p["iq"])
        label.append(p["label"])
        snr.append(p["snr_db"])
        tx_id.append(p["tx_id"] + offset)
        offset += (int(p["tx_id"].max()) + 1) if p["tx_id"].size else 0
    return {
        "iq": np.concatenate(iq),
        "label": np.concatenate(label),
        "tx_id": np.concatenate(tx_id),
        "snr_db": np.concatenate(snr),
    }


def build_data(sz: Sizes, rng: np.random.Generator) -> dict[str, dict]:
    """Generate every split. Labels are checked so no unknown frame can carry a class."""
    tx_train = make_transmitters(KNOWN, sz.tx_train, rng)
    tx_val = make_transmitters(KNOWN, sz.tx_val, rng)
    select_tx, calib_tx = split_val_devices(tx_val, sz.tx_val)
    tx_test = make_transmitters(KNOWN, sz.tx_test, rng)
    tx_aux = make_transmitters(AUX, sz.tx_aux, rng)
    tx_unknown = make_transmitters(UNKNOWN, sz.tx_unknown, rng)

    # class_names=KNOWN: aux (16PSK/8PAM) and unknown (64QAM/4PAM) get label -1 automatically.
    frames = {
        "train_known": build_frames(tx_train, sz.frames_train, N_SAMPLES, SNRS, rng, KNOWN),
        "train_aux": build_frames(tx_aux, sz.frames_train, N_SAMPLES, SNRS, rng, KNOWN),
        "val_select": build_frames(select_tx, sz.frames_val, N_SAMPLES, SNRS, rng, KNOWN),
        "val_calib": build_frames(calib_tx, sz.frames_val, N_SAMPLES, SNRS, rng, KNOWN),
        "test_known": build_frames(tx_test, sz.frames_test, N_SAMPLES, SNRS, rng, KNOWN),
        "test_unknown": build_frames(tx_unknown, sz.frames_test, N_SAMPLES, SNRS, rng, KNOWN),
    }
    assert (frames["train_known"]["label"] >= 0).all()
    assert (frames["train_aux"]["label"] == -1).all()
    assert (frames["val_select"]["label"] >= 0).all() and (frames["val_calib"]["label"] >= 0).all()
    assert (frames["test_known"]["label"] >= 0).all()
    assert (frames["test_unknown"]["label"] == -1).all()
    return frames


def objectosphere_fn(model: nn.Module, x: torch.Tensor, y: torch.Tensor) -> torch.Tensor:
    """Training loss for variant (c): known CE plus logit-norm terms, outliers pushed to a flat softmax."""
    return objectosphere_loss(model(x), y, xi=XI, lam=LAM)


def train_variant(v: VariantSpec, sz: Sizes, train_frames: dict, val_select: dict) -> tuple[nn.Module, dict]:
    set_seed(v.seed)
    model = CNN1D(n_classes=N_CLASSES)
    loss_fn = ce_loss if v.loss == "ce" else objectosphere_fn
    hist = train_model(
        model,
        ModulationDataset(train_frames),
        ModulationDataset(val_select),  # known only, so no outliers in model selection
        loss_fn,
        TrainConfig(epochs=sz.epochs, seed=v.seed),
        accuracy_val_score,  # closed-set accuracy on known val-select
    )
    return model, hist


def score_frames(v: VariantSpec, model: nn.Module, iq: np.ndarray, centroids: np.ndarray | None) -> np.ndarray:
    """Unknown score for each frame. Larger = more unknown-like."""
    if v.score == "msp":
        return msp_unknown_score(predict_logits(model, iq))
    assert centroids is not None
    return distance_unknown_score(predict_embeddings(model, iq), centroids)


def evaluate_variant(v: VariantSpec, model: nn.Module, frames: dict, train_known: dict) -> tuple[dict, dict]:
    """Calibrate on known val-calib, then score the test splits once.

    Returns (JSON-safe summary, raw scores for the histogram).
    """
    centroids = None
    if v.score == "distance":
        # Centroids come from KNOWN TRAIN embeddings only. Outliers are not in train_known.
        train_emb = predict_embeddings(model, train_known["iq"])
        centroids = class_centroids(train_emb, train_known["label"], N_CLASSES)

    calib_scores = score_frames(v, model, frames["val_calib"]["iq"], centroids)
    thr = calibrate_threshold(calib_scores, TARGET_KNOWN_ACCEPT)  # uses known frames only

    known_s = score_frames(v, model, frames["test_known"]["iq"], centroids)
    unknown_s = score_frames(v, model, frames["test_unknown"]["iq"], centroids)
    report = open_set_report(known_s, unknown_s, thr)

    # Closed-set accuracy uses the classifier head (argmax of logits) for every variant,
    # restricted to known test frames accepted by the threshold (score <= thr).
    y = frames["test_known"]["label"]
    pred = predict_logits(model, frames["test_known"]["iq"]).argmax(axis=1)
    accepted = known_s <= thr
    closed_on_accepted = accuracy(pred[accepted], y[accepted])
    summary = {
        "threshold": thr,
        "known_accepted": int(accepted.sum()),
        "unknown_rejected": int((unknown_s > thr).sum()),
        "report": report,
        "closed_set_on_accepted": {
            "positive_denominator": "known test frames accepted (score <= threshold)",
            "n": int(accepted.sum()),
            "n_correct": int((pred[accepted] == y[accepted]).sum()),
            "accuracy": closed_on_accepted,
        },
        "closed_set_all_known_test": {"n": int(y.size), "accuracy": accuracy(pred, y)},
        "n_calib_known": int(calib_scores.size),
    }
    raw = {"known": known_s, "unknown": unknown_s, "threshold": thr}
    return summary, raw


def _rate(k: int, n: int) -> str:
    return f"{k / n:.3f} ({k}/{n})" if n else "null (0/0)"


def print_table(results: dict[str, dict]) -> None:
    print(f"Open-set recognition, threshold at {TARGET_KNOWN_ACCEPT:.0%} known acceptance on val-calib")
    header = (
        f"{'variant':<22}{'threshold':>10}  {'known accepted (k/n)':<24}"
        f"{'unknown rejected (k/n)':<26}{'AUROC':>7}  {'closed-set acc on accepted (k/n)'}"
    )
    print(header)
    for name, r in results.items():
        rep = r["report"]
        cs = r["closed_set_on_accepted"]
        auroc = "null" if rep["auroc"] is None else f"{rep['auroc']:.3f}"
        print(
            f"{name:<22}{rep['threshold']:>10.4f}  "
            f"{_rate(r['known_accepted'], rep['n_known']):<24}"
            f"{_rate(r['unknown_rejected'], rep['n_unknown']):<26}{auroc:>7}  "
            f"{_rate(cs['n_correct'], cs['n'])}"
        )
    print(
        "Rates are on test devices; the threshold is fixed on val-calib, so they can differ from 95%. "
        "AUROC positive class = unknown; AUROC < 0.5 means unknown frames are more confident than "
        "known frames (not a sign error)."
    )


def save_plot(raw: dict[str, dict], path: Path) -> None:
    fig, axes = plt.subplots(1, len(raw), figsize=(4.0 * len(raw), 3.6), sharey=False)
    for ax, (name, s) in zip(np.atleast_1d(axes), raw.items()):
        hi = float(max(s["known"].max(), s["unknown"].max(), s["threshold"]))
        lo = float(min(s["known"].min(), s["unknown"].min()))
        bins = np.linspace(lo, hi if hi > lo else lo + 1e-6, 41)
        ax.hist(s["known"], bins=bins, alpha=0.6, label="known test (unseen devices)")
        ax.hist(s["unknown"], bins=bins, alpha=0.6, label="unknown test (64QAM, 4PAM)")
        ax.axvline(s["threshold"], color="k", ls="--", label=f"threshold {s['threshold']:.3f}")
        ax.set(title=name, xlabel="unknown score (larger = more unknown)", ylabel="frames")
    np.atleast_1d(axes)[0].legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


def main() -> None:
    args = parse_args()
    sz = QUICK if args.quick else DEFAULT
    torch.set_num_threads(4)
    t0 = time.perf_counter()

    rng = np.random.default_rng(SEED)
    frames = build_data(sz, rng)
    train_known = frames["train_known"]
    train_c = concat_frames([frames["train_known"], frames["train_aux"]])  # used by variant (c) only

    results: dict[str, dict] = {}
    raw: dict[str, dict] = {}
    val_select_ds = frames["val_select"]
    for v in VARIANTS:
        train_frames = train_c if v.use_aux else train_known
        model, hist = train_variant(v, sz, train_frames, val_select_ds)
        summary, raw_scores = evaluate_variant(v, model, frames, train_known)
        best = hist["best_epoch"]
        summary.update(
            {
                "loss": v.loss,
                "score": v.score,
                "seed": v.seed,
                "train_frames": int(train_frames["label"].size),
                "train_outliers": int((train_frames["label"] == -1).sum()),
                "epochs_run": len(hist["train_loss"]),
                "best_epoch": best,
                "val_select_accuracy_best": hist["val_score"][best],
            }
        )
        results[v.name] = summary
        raw[v.name] = raw_scores

    print_table(results)

    payload = {
        "lesson": "04_open_set",
        "mode": sz.mode,
        "known_classes": list(KNOWN),
        "aux_outlier_classes_train_only": list(AUX),
        "unknown_classes_test_only": list(UNKNOWN),
        "target_known_accept": TARGET_KNOWN_ACCEPT,
        "objectosphere": {"xi": XI, "lam": LAM},
        "n_samples": N_SAMPLES,
        "snr_db": list(SNRS),
        "devices": {
            "known_train_per_class": sz.tx_train,
            "known_val_per_class": sz.tx_val,
            "known_val_select_per_class": sz.tx_val - sz.tx_val // 2,
            "known_val_calib_per_class": sz.tx_val // 2,
            "known_test_per_class": sz.tx_test,
            "aux_outlier_per_class": sz.tx_aux,
            "unknown_test_per_class": sz.tx_unknown,
        },
        "frames": {name: int(f["label"].size) for name, f in frames.items()},
        "variants": results,
    }
    RESULTS.mkdir(exist_ok=True)
    # allow_nan=False: a NaN would raise here instead of writing invalid JSON.
    (RESULTS / "04_open_set.json").write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n")
    save_plot(raw, RESULTS / "04_open_set.png")
    print(f"mode={sz.mode} elapsed={time.perf_counter() - t0:.1f}s")
    print(f"wrote {RESULTS / '04_open_set.json'}")


if __name__ == "__main__":
    main()

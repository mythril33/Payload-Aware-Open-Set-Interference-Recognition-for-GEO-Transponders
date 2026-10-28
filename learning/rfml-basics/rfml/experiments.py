"""Stage logic for the interactive learning app, shared with the lessons.

Every stage is one function that takes explicit sizes and a seed, does no file or
plot I/O, and returns a JSON-strict dict: json.dumps(result, allow_nan=False) succeeds,
and undefined metrics are None next to their counts. The app (app.py) calls these
functions; the lessons will call the same functions so that the protocol lives in one
place.

Stages (protocol mirrors lessons 02-04; see those files for the reasoning):
  1. run_gradient_demo  line fit by gradient descent, hand gradient vs autograd
     show_frames        IQ frame as a tensor: time samples, constellation, spectrum
  2. run_modulation     closed-set modulation classification on unseen devices
  3. run_fingerprint    closed-set RF fingerprinting, frame-level split
  4. run_open_set       open-set rejection of 64QAM and 4PAM, threshold on known data

Roles and seeds
  Every role draws from its own numpy Generator, derived with
  np.random.SeedSequence(seed).spawn(len(ROLES)). Child i depends only on the seed and
  its position i, so ROLES is append-only: adding a role at the end leaves every
  existing stream unchanged. Within one role, devices are drawn before frames. Changing
  the size of one role therefore never changes the data another role generates.

Splits (leakage rules)
  Device-level splits for stages 2 and 4: one device is one modulation plus one
  hardware fingerprint, and it appears in exactly one split. Stage 3 is the exception:
  the device is the label, so it splits by frame within each device.
  Stage 4 thresholds come from known val-calib frames only. Unknown test frames are
  scored once, after calibration, and never influence training, selection or the
  threshold.

Progress callbacks receive Turkish status text for the UI. Torch thread count is left
to the caller.

Synthetic data only. Nothing here measures recognition quality on real signals.
"""

from __future__ import annotations

import json
import math
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass

import numpy as np
import torch
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from torch import nn

from rfml.dataset import (
    ModulationDataset,
    build_frames,
    make_transmitters,
    split_frames_stratified,
)
from rfml.metrics import accuracy, confusion_matrix, open_set_report
from rfml.models import CNN1D, MLP, ResNet1D
from rfml.openset import (
    calibrate_threshold,
    class_centroids,
    distance_unknown_score,
    msp_unknown_score,
    objectosphere_loss,
)
from rfml.signals import (
    AUX_OUTLIER_MODULATIONS,
    KNOWN_MODULATIONS,
    MODULATIONS,
    UNKNOWN_MODULATIONS,
    Transmitter,
    constellation,
    make_frame,
)
from rfml.train import (
    TrainConfig,
    accuracy_val_score,
    ce_loss,
    predict_embeddings,
    predict_logits,
    set_seed,
    train_model,
)

ProgressFn = Callable[[str], None]

KNOWN = KNOWN_MODULATIONS  # ("BPSK", "QPSK", "8PSK", "16QAM"): training classes
UNKNOWN = UNKNOWN_MODULATIONS  # ("64QAM", "4PAM"): test-only unknowns
AUX = AUX_OUTLIER_MODULATIONS  # ("16PSK", "8PAM"): train-only outliers, objectosphere variant
N_CLASSES = len(KNOWN)
N_SAMPLES = 512
TRAIN_SNRS = tuple(float(s) for s in np.arange(-4, 21, 2))  # train, val and open-set SNR grid
MOD_TEST_SNRS = tuple(float(s) for s in np.arange(-6, 21, 2))  # stage 2 adds -6 dB, below training
FP_MODULATION = "QPSK"  # every fingerprint device sends the same modulation
FP_SPLIT = (0.6, 0.2, 0.2)  # train / val-select / test, frame-level within each device
FP_WIDTH = 16  # ResNet1D base width
MODULATION_MODELS = ("MLP", "CNN1D")
TRUE_W, TRUE_B = 2.5, -1.0  # ground truth of the line-fit demo
GRAD_N = 100  # samples in the line-fit demo
GRAD_NOISE = 0.1  # std of the label noise in the line-fit demo
DEFAULT_TARGET_KNOWN_ACCEPT = 0.95
DEFAULT_XI, DEFAULT_LAM = 10.0, 0.1  # Objectosphere defaults from Dhamija et al. (2018)
CHANCE_CLOSED_SET = 1.0 / N_CLASSES
CHANCE_AUROC = 0.5

# Append-only: see the module docstring before changing this tuple.
ROLES: tuple[str, ...] = (
    "gradient",
    "frames",
    "mod.train",
    "mod.val",
    "mod.test",
    "fingerprint",
    "os.train",
    "os.aux",
    "os.val",
    "os.test_known",
    "os.test_unknown",
)


def role_rngs(seed: int) -> dict[str, np.random.Generator]:
    """One independent Generator per role, spawned from SeedSequence(seed)."""
    _check_seed(seed)
    children = np.random.SeedSequence(int(seed)).spawn(len(ROLES))
    return {name: np.random.default_rng(child) for name, child in zip(ROLES, children)}


@dataclass(frozen=True)
class Scale:
    """Sizes for one preset. Names follow lessons 02-04; per-role counts are noted below.

    tx_*        devices per modulation (stage 4: tx_val is halved into select and calib)
    tx_aux      outlier devices per aux modulation (stage 4, train only)
    tx_unknown  devices per unknown modulation (stage 4, test only)
    frames_*    frames per device (stage 2: frames_test per device and per SNR)
    fp_*        stage 3 device count and frames per device
    """

    name: str
    description: str
    tx_train: int
    tx_val: int
    tx_test: int
    tx_aux: int
    tx_unknown: int
    frames_train: int
    frames_val: int
    frames_test: int
    fp_devices: int
    fp_frames: int
    epochs: int
    patience: int = 5

    def __post_init__(self) -> None:
        for field in (
            "tx_train", "tx_val", "tx_test", "tx_aux", "tx_unknown", "frames_train",
            "frames_val", "frames_test", "fp_devices", "fp_frames", "epochs", "patience",
        ):
            if int(getattr(self, field)) < 1:
                raise ValueError(f"{field} must be >= 1, got {getattr(self, field)}")
        if self.tx_val < 2:
            raise ValueError("tx_val must be >= 2: validation devices are split into select and calib")


# Quick mirrors the --quick sizes of lessons 02-04 (duman testi, about a minute in total).
QUICK = Scale(
    name="quick",
    description="smoke test",
    tx_train=6, tx_val=3, tx_test=3, tx_aux=3, tx_unknown=3,
    frames_train=5, frames_val=3, frames_test=3,
    fp_devices=4, fp_frames=40, epochs=2,
)
# Standard costs about a third of full. Measured on one torch thread under load from other
# processes: full about 450 s, standard about 137 s. Chosen by compute, not to match a
# wall-clock target.
STANDARD = Scale(
    name="standard",
    description="about a third of full's compute",
    tx_train=24, tx_val=8, tx_test=8, tx_aux=12, tx_unknown=8,
    frames_train=12, frames_val=8, frames_test=8,
    fp_devices=8, fp_frames=150, epochs=15,
)
# Full equals the default sizes of lessons 02-04 and lesson 03.
FULL = Scale(
    name="full",
    description="lesson defaults",
    tx_train=40, tx_val=10, tx_test=10, tx_aux=20, tx_unknown=10,
    frames_train=20, frames_val=10, frames_test=10,
    fp_devices=10, fp_frames=300, epochs=25,
)
SCALES: dict[str, Scale] = {s.name: s for s in (QUICK, STANDARD, FULL)}


def get_scale(name: str) -> Scale:
    try:
        return SCALES[name]
    except KeyError:
        raise ValueError(f"unknown scale {name!r}; expected one of {tuple(SCALES)}") from None


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _check_seed(seed: int) -> None:
    if isinstance(seed, bool) or not isinstance(seed, (int, np.integer)) or seed < 0:
        raise ValueError(f"seed must be a non-negative integer, got {seed!r}")


def _emit(progress: ProgressFn | None, message: str) -> None:
    if progress is not None:
        progress(message)


def _epoch_scorer(progress: ProgressFn | None, label: str, epochs: int):
    """Wrap accuracy_val_score so that each finished epoch reports progress.

    train_model calls the score function exactly once per epoch, so the count is exact.
    """
    count = [0]

    def score(model: nn.Module, val_ds) -> float:
        count[0] += 1
        _emit(progress, f"{label}: dönem {count[0]}/{epochs}")
        return accuracy_val_score(model, val_ds)

    return score


def _scale_dict(scale: Scale) -> dict:
    return asdict(scale)


def to_strict_json(result: dict) -> str:
    """Serialise a result for download. Raises ValueError on NaN or inf."""
    return json.dumps(result, indent=2, allow_nan=False, ensure_ascii=False) + "\n"


# ---------------------------------------------------------------------------
# Stage 1a: line-fit gradient descent with a hand-derived gradient
# ---------------------------------------------------------------------------


def _mse(w: torch.Tensor, b: torch.Tensor, x: torch.Tensor, y: torch.Tensor) -> float:
    return float(((w * x + b - y) ** 2).mean())


def _hand_gradients(w: torch.Tensor, b: torch.Tensor, x: torch.Tensor, y: torch.Tensor):
    """Closed-form gradients of L = mean((w*x + b - y)^2): dL/dw and dL/db."""
    residual = w * x + b - y
    return (2 * residual * x).mean(), (2 * residual).mean()


def run_gradient_demo(lr: float, steps: int, seed: int) -> dict:
    """Fit y = w*x + b by gradient descent from zero, checking each hand gradient.

    loss_history[k] is the MSE after k updates, so it has steps + 1 entries when the run
    does not diverge. grad_check_max_abs_diff is the largest |hand - autograd| over all
    steps and both parameters.

    If an update produces a non-finite value (divergence), the run stops early. Then
    diverged is True, diverged_at_step names the step, and w and b are None.
    """
    lr = float(lr)
    if not (math.isfinite(lr) and lr > 0.0):
        raise ValueError(f"lr must be a positive finite number, got {lr!r}")
    if int(steps) != steps or steps < 1:
        raise ValueError(f"steps must be an integer >= 1, got {steps!r}")
    steps = int(steps)
    _check_seed(seed)

    rng = role_rngs(seed)["gradient"]
    x_np = rng.uniform(-1.0, 1.0, size=GRAD_N)
    y_np = TRUE_W * x_np + TRUE_B + GRAD_NOISE * rng.standard_normal(GRAD_N)

    # Curvature of the MSE is (2/N) X^T X with X = [x, 1]. Gradient descent is stable
    # when lr < 2 / lambda_max, which is the bound the app shows next to the controls.
    design = np.column_stack([x_np, np.ones(GRAD_N)])
    hessian = (2.0 / GRAD_N) * design.T @ design
    stability_bound = 2.0 / float(np.linalg.eigvalsh(hessian).max())
    ls_w, ls_b = (float(v) for v in np.linalg.lstsq(design, y_np, rcond=None)[0])

    x = torch.as_tensor(x_np, dtype=torch.float32)
    y = torch.as_tensor(y_np, dtype=torch.float32)
    w = torch.zeros((), dtype=torch.float32)
    b = torch.zeros((), dtype=torch.float32)
    history = [_mse(w, b, x, y)]
    max_diff = 0.0
    diverged_at: int | None = None

    for step in range(steps):
        with torch.no_grad():
            gw, gb = _hand_gradients(w, b, x, y)
            if not (bool(torch.isfinite(gw)) and bool(torch.isfinite(gb))):
                diverged_at = step
                break
        # Autograd on fresh leaves: this is the check that the hand formula is right.
        wa = w.clone().requires_grad_(True)
        ba = b.clone().requires_grad_(True)
        ((wa * x + ba - y) ** 2).mean().backward()
        max_diff = max(max_diff, abs(float(gw) - float(wa.grad)), abs(float(gb) - float(ba.grad)))
        with torch.no_grad():
            w = w - lr * gw  # step against the gradient
            b = b - lr * gb
            finite = bool(torch.isfinite(w)) and bool(torch.isfinite(b))
            value = _mse(w, b, x, y) if finite else math.nan
        if not finite or not math.isfinite(value):
            diverged_at = step
            break
        history.append(value)

    diverged = diverged_at is not None
    return {
        "stage": "gradient",
        "lr": lr,
        "steps": steps,
        "steps_run": len(history) - 1,
        "seed": int(seed),
        "n_samples": GRAD_N,
        "true_w": TRUE_W,
        "true_b": TRUE_B,
        "w": None if diverged else float(w),
        "b": None if diverged else float(b),
        "least_squares": {"w": ls_w, "b": ls_b},
        "loss_history": history,
        "grad_check_max_abs_diff": max_diff,
        "stability_lr_bound": stability_bound,
        "diverged": diverged,
        "diverged_at_step": diverged_at,
        "x": x_np.tolist(),
        "y": y_np.tolist(),
    }


# ---------------------------------------------------------------------------
# Stage 1b: one IQ frame as a tensor (time, constellation, spectrum)
# ---------------------------------------------------------------------------


def _device_summary(tx: Transmitter) -> dict:
    """Hardware fields of one device. Simulator truth, shown for learning only."""
    saturation = None if math.isinf(tx.pa_saturation) else float(tx.pa_saturation)
    return {
        "modulation": tx.modulation,
        "iq_gain": float(tx.iq_gain),
        "iq_phase_deg": float(tx.iq_phase_deg),
        "dc_offset_re": float(complex(tx.dc_offset).real),
        "dc_offset_im": float(complex(tx.dc_offset).imag),
        "phase_noise_std": float(tx.phase_noise_std),
        "pa_saturation": saturation,  # None means no compression (ideal device)
        "pa_smoothness": float(tx.pa_smoothness),
    }


def show_frames(
    modulations: tuple[str, ...],
    snr_db: float,
    impaired: bool,
    n_samples: int,
    seed: int,
) -> dict:
    """One simulated frame per modulation, as arrays for plotting.

    Each frame is generated with make_frame (sps = 8, RRC pulse, CFO, AWGN), so the
    spectrum shows the pulse shape. The frequency axis is normalised to cycles per
    sample, in [-0.5, 0.5). The spectrum is a Hann-windowed FFT power, in dB.
    Returns numpy arrays, not JSON.
    """
    mods = tuple(modulations)
    if not mods:
        raise ValueError("modulations must not be empty")
    unknown = [m for m in mods if m not in MODULATIONS]
    if unknown:
        raise ValueError(f"unknown modulations {unknown}; expected a subset of {MODULATIONS}")
    if not (16 <= int(n_samples) <= 8192):
        raise ValueError(f"n_samples must lie in [16, 8192], got {n_samples}")
    _check_seed(seed)
    n = int(n_samples)

    rng = role_rngs(seed)["frames"]
    window = np.hanning(n)
    window_power = float(np.sum(window**2))
    frames = []
    for mod in mods:
        tx = Transmitter.random(mod, rng, impaired=impaired)
        rx = make_frame(tx, n, float(snr_db), rng)
        spectrum = np.fft.fftshift(np.fft.fft(rx * window))
        psd = np.abs(spectrum) ** 2 / window_power
        frames.append(
            {
                "modulation": mod,
                "i": rx.real.copy(),
                "q": rx.imag.copy(),
                "rx": rx,
                "ideal": constellation(mod),
                "psd_db": 10.0 * np.log10(psd + 1e-12),
                "device": _device_summary(tx),
            }
        )
    return {
        "modulations": list(mods),
        "snr_db": float(snr_db),
        "impaired": bool(impaired),
        "n_samples": n,
        "seed": int(seed),
        "sample_index": np.arange(n),
        "freq": np.fft.fftshift(np.fft.fftfreq(n)),
        "frames": frames,
    }


# ---------------------------------------------------------------------------
# Stage 2: closed-set modulation classification (lesson 02)
# ---------------------------------------------------------------------------

MODEL_BUILDERS: dict[str, Callable[[], nn.Module]] = {
    "MLP": lambda: MLP(n_classes=N_CLASSES, n_samples=N_SAMPLES),
    "CNN1D": lambda: CNN1D(n_classes=N_CLASSES),
}


def _check_models(models: Sequence[str]) -> tuple[str, ...]:
    names = tuple(models)
    if not names:
        raise ValueError("models must not be empty")
    unknown = [m for m in names if m not in MODEL_BUILDERS]
    if unknown:
        raise ValueError(f"unknown models {unknown}; expected a subset of {tuple(MODEL_BUILDERS)}")
    return tuple(dict.fromkeys(names))  # drop repeats, keep order


def build_modulation_data(scale: Scale, impaired: bool, seed: int) -> tuple[dict, dict, dict[float, dict]]:
    """Train, val-select and per-SNR test frames, from disjoint devices.

    Returns (train, val, test_by_snr). Test devices are drawn once and reused at every
    SNR, so the curve compares the same devices.
    """
    rngs = role_rngs(seed)
    tx_train = make_transmitters(KNOWN, scale.tx_train, rngs["mod.train"], impaired=impaired)
    train = build_frames(tx_train, scale.frames_train, N_SAMPLES, TRAIN_SNRS, rngs["mod.train"], KNOWN)
    tx_val = make_transmitters(KNOWN, scale.tx_val, rngs["mod.val"], impaired=impaired)
    val = build_frames(tx_val, scale.frames_val, N_SAMPLES, TRAIN_SNRS, rngs["mod.val"], KNOWN)
    tx_test = make_transmitters(KNOWN, scale.tx_test, rngs["mod.test"], impaired=impaired)
    test_by_snr = {
        snr: build_frames(tx_test, scale.frames_test, N_SAMPLES, (snr,), rngs["mod.test"], KNOWN)
        for snr in MOD_TEST_SNRS
    }
    if (train["label"] < 0).any() or (val["label"] < 0).any():
        raise RuntimeError("known training or validation frame has no class label")
    return train, val, test_by_snr


def _evaluate_modulation(model: nn.Module, test_by_snr: dict[float, dict]) -> tuple[list[dict], dict, list]:
    per_snr, preds, labels = [], [], []
    for snr in MOD_TEST_SNRS:
        d = test_by_snr[snr]
        pred = predict_logits(model, d["iq"]).argmax(axis=1)
        per_snr.append({"snr_db": snr, "n": int(d["label"].size), "accuracy": accuracy(pred, d["label"])})
        preds.append(pred)
        labels.append(d["label"])
    pred_all, label_all = np.concatenate(preds), np.concatenate(labels)
    overall = {"n": int(label_all.size), "accuracy": accuracy(pred_all, label_all)}
    cm = confusion_matrix(pred_all, label_all, N_CLASSES).tolist()
    return per_snr, overall, cm


def run_modulation(
    scale: Scale,
    impaired: bool,
    seed: int,
    models: tuple[str, ...] = MODULATION_MODELS,
    progress: ProgressFn | None = None,
) -> dict:
    """Train each model on known devices and score unseen devices at each test SNR.

    impaired=False gives identical devices per modulation (an ablation: the modulation
    is still learnable). Chance level is 1/4. Accuracies are None when n is 0.
    """
    model_names = _check_models(models)
    _check_seed(seed)
    _emit(progress, "Veri üretiliyor (eğitim, doğrulama, test)…")
    train, val, test_by_snr = build_modulation_data(scale, impaired, seed)

    runs: dict[str, dict] = {}
    for name in model_names:
        _emit(progress, f"{name} eğitiliyor…")
        set_seed(seed)  # fixes the weight initialisation
        model = MODEL_BUILDERS[name]()
        hist = train_model(
            model,
            ModulationDataset(train),
            ModulationDataset(val),  # val-select only: the checkpoint choice
            ce_loss,
            TrainConfig(epochs=scale.epochs, patience=scale.patience, seed=seed),
            _epoch_scorer(progress, name, scale.epochs),
        )
        _emit(progress, f"{name}: test değerlendiriliyor…")
        per_snr, overall, cm = _evaluate_modulation(model, test_by_snr)
        best = hist["best_epoch"]
        runs[name] = {
            "epochs_run": len(hist["train_loss"]),
            "best_epoch": best,
            "val_select_accuracy_best": hist["val_score"][best],
            "per_snr": per_snr,
            "overall": overall,
            "confusion_overall": cm,
        }

    return {
        "stage": "modulation",
        "scale": _scale_dict(scale),
        "impaired": bool(impaired),
        "seed": int(seed),
        "split": "device-level: train, val-select and test devices are disjoint",
        "classes": list(KNOWN),
        "chance_level": CHANCE_CLOSED_SET,
        "n_samples": N_SAMPLES,
        "train_snr_db": list(TRAIN_SNRS),
        "test_snr_db": list(MOD_TEST_SNRS),
        "devices_per_class": {"train": scale.tx_train, "val_select": scale.tx_val, "test": scale.tx_test},
        "frames_per_device": {
            "train": scale.frames_train,
            "val_select": scale.frames_val,
            "test_per_snr": scale.frames_test,
        },
        "frames": {"train": int(train["label"].size), "val_select": int(val["label"].size)},
        "models": runs,
    }


# ---------------------------------------------------------------------------
# Stage 3: RF fingerprinting, one QPSK per device (lesson 03)
# ---------------------------------------------------------------------------


def build_fingerprint_data(scale: Scale, impaired: bool, seed: int) -> tuple[dict, tuple[np.ndarray, ...]]:
    """fp_devices QPSK devices, frame-level split. Returns (data, (train, val, test) indices)."""
    rng = role_rngs(seed)["fingerprint"]
    devices = make_transmitters((FP_MODULATION,), scale.fp_devices, rng, impaired=impaired)
    data = build_frames(devices, scale.fp_frames, N_SAMPLES, TRAIN_SNRS, rng, (FP_MODULATION,))
    train_idx, val_idx, test_idx = split_frames_stratified(data["tx_id"], FP_SPLIT, rng)
    if not (train_idx.size and val_idx.size and test_idx.size):
        raise ValueError("fp_frames is too small: every split needs at least one frame")
    return data, (train_idx, val_idx, test_idx)


def run_fingerprint(
    scale: Scale,
    impaired: bool,
    seed: int,
    progress: ProgressFn | None = None,
) -> dict:
    """Closed-set device identification with ResNet1D.

    The split is FRAME-level within each device, because the device is the label. The
    test therefore measures recognition of known devices from new frames, not
    generalisation to a new device. impaired=False gives identical devices, whose
    expected accuracy is chance, 1/fp_devices.
    """
    _check_seed(seed)
    _emit(progress, "Cihazlar ve çerçeveler üretiliyor…")
    data, (train_idx, val_idx, test_idx) = build_fingerprint_data(scale, impaired, seed)
    fp = dict(data, label=data["tx_id"])  # the device is the label in this stage

    set_seed(seed)
    model = ResNet1D(n_classes=scale.fp_devices, base_width=FP_WIDTH)
    hist = train_model(
        model,
        ModulationDataset(fp, train_idx),
        ModulationDataset(fp, val_idx),
        ce_loss,
        TrainConfig(epochs=scale.epochs, patience=scale.patience, seed=seed),
        _epoch_scorer(progress, "ResNet1D", scale.epochs),
    )

    _emit(progress, "Test değerlendiriliyor…")
    per_snr = []
    for snr in TRAIN_SNRS:
        sel = test_idx[np.isclose(data["snr_db"][test_idx], snr, atol=1e-3)]
        pred = predict_logits(model, data["iq"][sel]).argmax(axis=1)
        per_snr.append({"snr_db": snr, "n": int(sel.size), "accuracy": accuracy(pred, data["tx_id"][sel])})
    pred_all = predict_logits(model, data["iq"][test_idx]).argmax(axis=1)
    overall = {"n": int(test_idx.size), "accuracy": accuracy(pred_all, data["tx_id"][test_idx])}

    best = hist["best_epoch"]
    return {
        "stage": "fingerprint",
        "scale": _scale_dict(scale),
        "impaired": bool(impaired),
        "seed": int(seed),
        "modulation": FP_MODULATION,
        "n_samples": N_SAMPLES,
        "n_devices": scale.fp_devices,
        "frames_per_device": scale.fp_frames,
        "split": "frame-level within each device (device is the label); fractions train/val/test 0.6/0.2/0.2",
        "train_snr_db": list(TRAIN_SNRS),
        "chance_level": 1.0 / scale.fp_devices,
        "frames": {
            "train": int(train_idx.size),
            "val_select": int(val_idx.size),
            "test": int(test_idx.size),
        },
        "devices_in_test": int(np.unique(data["tx_id"][test_idx]).size),
        "epochs_run": len(hist["train_loss"]),
        "best_epoch": best,
        "val_select_accuracy_best": hist["val_score"][best],
        "per_snr": per_snr,
        "overall": overall,
    }


# ---------------------------------------------------------------------------
# Stage 4: open-set recognition (lesson 04)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VariantSpec:
    name: str
    loss: str  # "ce" or "objectosphere"
    score: str  # "msp" or "distance"
    use_aux: bool  # True only if the training set includes the -1 outliers
    seed_offset: int  # variant trains with seed + seed_offset (seed=0 gives lesson 04's 0, 1, 2)


VARIANTS = (
    VariantSpec("CE + MSP", "ce", "msp", use_aux=False, seed_offset=0),
    VariantSpec("CE + distance", "ce", "distance", use_aux=False, seed_offset=1),
    VariantSpec("Objectosphere + MSP", "objectosphere", "msp", use_aux=True, seed_offset=2),
)


def split_val_devices(tx_val: list, per_class: int) -> tuple[list, list]:
    """Halve the known validation devices BY DEVICE within each class: (select, calib)."""
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
    """Stack build_frames() outputs. tx_id is offset so device ids stay unique."""
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


def build_open_set_data(scale: Scale, seed: int) -> dict[str, dict]:
    """Every split of stage 4, each drawn from its own role.

    test_unknown is built here only so that it exists; run_open_set reads it after the
    threshold is fixed. Its role draws nothing that any other split uses.
    """
    rngs = role_rngs(seed)
    tx_train = make_transmitters(KNOWN, scale.tx_train, rngs["os.train"])
    train_known = build_frames(tx_train, scale.frames_train, N_SAMPLES, TRAIN_SNRS, rngs["os.train"], KNOWN)
    tx_aux = make_transmitters(AUX, scale.tx_aux, rngs["os.aux"])
    train_aux = build_frames(tx_aux, scale.frames_train, N_SAMPLES, TRAIN_SNRS, rngs["os.aux"], KNOWN)
    tx_val = make_transmitters(KNOWN, scale.tx_val, rngs["os.val"])
    select_tx, calib_tx = split_val_devices(tx_val, scale.tx_val)
    val_select = build_frames(select_tx, scale.frames_val, N_SAMPLES, TRAIN_SNRS, rngs["os.val"], KNOWN)
    val_calib = build_frames(calib_tx, scale.frames_val, N_SAMPLES, TRAIN_SNRS, rngs["os.val"], KNOWN)
    tx_test = make_transmitters(KNOWN, scale.tx_test, rngs["os.test_known"])
    test_known = build_frames(tx_test, scale.frames_test, N_SAMPLES, TRAIN_SNRS, rngs["os.test_known"], KNOWN)
    tx_unknown = make_transmitters(UNKNOWN, scale.tx_unknown, rngs["os.test_unknown"])
    test_unknown = build_frames(tx_unknown, scale.frames_test, N_SAMPLES, TRAIN_SNRS, rngs["os.test_unknown"], KNOWN)

    # class_names=KNOWN gives label -1 to aux and unknown frames automatically. Check it.
    checks = (
        (train_known["label"] >= 0).all(),
        (train_aux["label"] == -1).all(),
        (val_select["label"] >= 0).all() and (val_calib["label"] >= 0).all(),
        (test_known["label"] >= 0).all(),
        (test_unknown["label"] == -1).all(),
    )
    if not all(bool(c) for c in checks):
        raise RuntimeError("open-set label convention violated")
    return {
        "train_known": train_known,
        "train_aux": train_aux,
        "val_select": val_select,
        "val_calib": val_calib,
        "test_known": test_known,
        "test_unknown": test_unknown,
    }


def _objectosphere_fn(xi: float, lam: float) -> Callable:
    def loss(model: nn.Module, x: torch.Tensor, y: torch.Tensor) -> torch.Tensor:
        return objectosphere_loss(model(x), y, xi=xi, lam=lam)

    return loss


def _unknown_score(spec: VariantSpec, model: nn.Module, iq: np.ndarray, centroids: np.ndarray | None) -> np.ndarray:
    """Unknown score per frame, larger = more unknown-like."""
    if spec.score == "msp":
        return msp_unknown_score(predict_logits(model, iq))
    assert centroids is not None
    return distance_unknown_score(predict_embeddings(model, iq), centroids)


def _evaluate_variant(
    spec: VariantSpec,
    model: nn.Module,
    frames: dict[str, dict],
    train_known: dict,
    target_known_accept: float,
) -> tuple[dict, dict]:
    """Calibrate on known val-calib frames, then score the test splits once.

    Returns (JSON-safe summary, raw scores for the histograms).
    """
    centroids = None
    if spec.score == "distance":
        # Centroids come from known training embeddings only (no outliers, no unknowns).
        centroids = class_centroids(predict_embeddings(model, train_known["iq"]), train_known["label"], N_CLASSES)

    calib = _unknown_score(spec, model, frames["val_calib"]["iq"], centroids)
    thr = calibrate_threshold(calib, target_known_accept)  # known val-calib frames only

    known_s = _unknown_score(spec, model, frames["test_known"]["iq"], centroids)
    unknown_s = _unknown_score(spec, model, frames["test_unknown"]["iq"], centroids)  # first use
    report = open_set_report(known_s, unknown_s, thr)

    y = frames["test_known"]["label"]
    pred = predict_logits(model, frames["test_known"]["iq"]).argmax(axis=1)
    accepted = known_s <= thr
    summary = {
        "loss": spec.loss,
        "score": spec.score,
        "threshold": thr,
        "report": report,
        "known_accepted": int(accepted.sum()),
        "unknown_rejected": int((unknown_s > thr).sum()),
        "closed_set_on_accepted": {
            "positive_denominator": "known test frames accepted (score <= threshold)",
            "n": int(accepted.sum()),
            "n_correct": int((pred[accepted] == y[accepted]).sum()),
            "accuracy": accuracy(pred[accepted], y[accepted]),
        },
        "closed_set_all_known_test": {"n": int(y.size), "accuracy": accuracy(pred, y)},
        "n_calib_known": int(calib.size),
    }
    return summary, {"known": known_s.tolist(), "unknown": unknown_s.tolist()}


def run_open_set(
    scale: Scale,
    seed: int,
    xi: float,
    lam: float,
    target_known_accept: float,
    progress: ProgressFn | None = None,
) -> dict:
    """Three variants, each trained on its own seed, scored on unknown modulations.

    Variant i trains with seed + seed_offset. xi and lam apply to the Objectosphere
    variant only. The threshold is set on known val-calib frames at target_known_accept.
    Unknown frames (64QAM, 4PAM) are used only after the threshold is fixed.
    The Objectosphere variant trains on the 16PSK and 8PAM outliers, so its rejection
    rates are an optimistic bound (see lesson 04).
    """
    _check_seed(seed)
    if not (math.isfinite(xi) and xi > 0.0):
        raise ValueError(f"xi must be a positive finite number, got {xi!r}")
    if not (math.isfinite(lam) and lam >= 0.0):
        raise ValueError(f"lam must be a non-negative finite number, got {lam!r}")
    if not (0.0 < target_known_accept <= 1.0):
        raise ValueError("target_known_accept must lie in (0, 1]")

    _emit(progress, "Veri üretiliyor (her rol ayrı)…")
    frames = build_open_set_data(scale, seed)
    train_known = frames["train_known"]
    train_c = concat_frames([train_known, frames["train_aux"]])  # used by the aux variant only

    variants: dict[str, dict] = {}
    for spec in VARIANTS:
        v_seed = seed + spec.seed_offset
        train_frames = train_c if spec.use_aux else train_known
        loss_fn = ce_loss if spec.loss == "ce" else _objectosphere_fn(xi, lam)
        set_seed(v_seed)
        model = CNN1D(n_classes=N_CLASSES)
        hist = train_model(
            model,
            ModulationDataset(train_frames),
            ModulationDataset(frames["val_select"]),  # known only: no outliers in selection
            loss_fn,
            TrainConfig(epochs=scale.epochs, patience=scale.patience, seed=v_seed),
            _epoch_scorer(progress, spec.name, scale.epochs),
        )
        _emit(progress, f"{spec.name}: eşik ve test değerlendiriliyor…")
        summary, scores = _evaluate_variant(spec, model, frames, train_known, target_known_accept)
        best = hist["best_epoch"]
        summary.update(
            {
                "seed": v_seed,
                "use_aux": spec.use_aux,
                "train_frames": int(train_frames["label"].size),
                "train_outliers": int((train_frames["label"] == -1).sum()),
                "epochs_run": len(hist["train_loss"]),
                "best_epoch": best,
                "val_select_accuracy_best": hist["val_score"][best],
                "scores": scores,
            }
        )
        variants[spec.name] = summary

    return {
        "stage": "open_set",
        "scale": _scale_dict(scale),
        "seed": int(seed),
        "split": "device-level; threshold from known val-calib frames; unknown test frames scored after calibration",
        "known_classes": list(KNOWN),
        "aux_outlier_classes_train_only": list(AUX),
        "unknown_classes_test_only": list(UNKNOWN),
        "target_known_accept": float(target_known_accept),
        "objectosphere": {"xi": float(xi), "lam": float(lam)},
        "n_samples": N_SAMPLES,
        "snr_db": list(TRAIN_SNRS),
        "chance": {"closed_set": CHANCE_CLOSED_SET, "auroc": CHANCE_AUROC},
        "devices": {
            "known_train_per_class": scale.tx_train,
            "known_val_per_class": scale.tx_val,
            "known_val_select_per_class": scale.tx_val - scale.tx_val // 2,
            "known_val_calib_per_class": scale.tx_val // 2,
            "known_test_per_class": scale.tx_test,
            "aux_outlier_per_class": scale.tx_aux,
            "unknown_test_per_class": scale.tx_unknown,
        },
        "frames": {name: int(f["label"].size) for name, f in frames.items()},
        "variants": variants,
    }


# ---------------------------------------------------------------------------
# Figures: built directly on Figure (no pyplot global state), so Streamlit can render them
# ---------------------------------------------------------------------------


def _figure(width: float, height: float) -> Figure:
    fig = Figure(figsize=(width, height), layout="constrained")
    FigureCanvasAgg(fig)  # attaches a canvas without touching pyplot
    return fig


def fig_gradient(result: dict) -> Figure:
    """Loss per update (log scale), and the data with the true and fitted lines."""
    fig = _figure(9.5, 3.8)
    ax_loss = fig.add_subplot(1, 2, 1)
    history = np.asarray(result["loss_history"], dtype=np.float64)
    ax_loss.semilogy(np.arange(history.size), np.maximum(history, 1e-16), color="C0")
    if result["diverged"]:
        ax_loss.axvline(result["diverged_at_step"], color="C3", ls=":", label="iraksama")
        ax_loss.legend(fontsize=8)
    ax_loss.set(title="Kayıp (MSE) güncellemelere göre", xlabel="güncelleme", ylabel="MSE (log)")
    ax_loss.grid(alpha=0.3)

    ax_fit = fig.add_subplot(1, 2, 2)
    ax_fit.scatter(result["x"], result["y"], s=10, alpha=0.6, label="gürültülü örnekler")
    xs = np.array([-1.0, 1.0])
    ax_fit.plot(xs, result["true_w"] * xs + result["true_b"], "k--", label="gerçek doğru")
    if result["w"] is not None:
        ax_fit.plot(xs, result["w"] * xs + result["b"], "C3", label="gradyan inişi")
    ax_fit.set(title="Doğrusal uyum", xlabel="x", ylabel="y")
    ax_fit.legend(fontsize=8)
    ax_fit.grid(alpha=0.3)
    return fig


def fig_frames(frames: dict) -> Figure:
    """One row per modulation: I and Q against time, the constellation, and the spectrum."""
    n_rows = len(frames["frames"])
    fig = _figure(11.0, 2.9 * n_rows)
    for r, frame in enumerate(frames["frames"]):
        mod = frame["modulation"]
        ax_t = fig.add_subplot(n_rows, 3, 3 * r + 1)
        ax_t.plot(frames["sample_index"], frame["i"], lw=0.8, label="I")
        ax_t.plot(frames["sample_index"], frame["q"], lw=0.8, label="Q")
        ax_t.set(title=f"{mod}: zaman", xlabel="örnek", ylabel="genlik")
        ax_t.legend(fontsize=7)

        ax_c = fig.add_subplot(n_rows, 3, 3 * r + 2)
        ax_c.scatter(frame["rx"].real, frame["rx"].imag, s=3, alpha=0.3, label="alınan örnekler")
        ax_c.scatter(frame["ideal"].real, frame["ideal"].imag, marker="x", s=50, color="C3", label="ideal noktalar")
        ax_c.set(title=f"{mod}: takımyıldız", xlabel="I", ylabel="Q")
        ax_c.set_aspect("equal")
        ax_c.legend(fontsize=7, loc="upper right")

        ax_p = fig.add_subplot(n_rows, 3, 3 * r + 3)
        ax_p.plot(frames["freq"], frame["psd_db"], lw=0.8)
        ax_p.set(title=f"{mod}: güç spektrumu", xlabel="frekans (döngü/örnek)", ylabel="dB")
        ax_p.grid(alpha=0.3)
    return fig


def fig_modulation(result: dict) -> Figure:
    """Test accuracy against SNR for each model, with chance level and the training range."""
    fig = _figure(7.0, 4.2)
    ax = fig.add_subplot(1, 1, 1)
    for name, run in result["models"].items():
        xs = [r["snr_db"] for r in run["per_snr"]]
        ys = [np.nan if r["accuracy"] is None else r["accuracy"] for r in run["per_snr"]]
        ax.plot(xs, ys, marker="o", label=name)
    chance = result["chance_level"]
    ax.axhline(chance, color="grey", ls="--", label=f"şans = {chance:.2f}")
    ax.axvspan(min(result["test_snr_db"]) - 1, min(result["train_snr_db"]), color="0.9", label="eğitim SNR aralığı dışı")
    ax.set(
        xlabel="SNR (dB)",
        ylabel="test doğruluğu (görülmemiş cihazlar)",
        ylim=(0.0, 1.02),
        title="Kapalı küme modülasyon sınıflandırma",
    )
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)
    return fig


def fig_fingerprint(runs: Sequence[dict]) -> Figure:
    """Fingerprint accuracy against SNR, one curve per run (impaired and ideal control)."""
    fig = _figure(7.0, 4.2)
    ax = fig.add_subplot(1, 1, 1)
    for run in runs:
        label = "bozulmalı cihazlar" if run["impaired"] else "ideal cihazlar (kontrol)"
        xs = [r["snr_db"] for r in run["per_snr"]]
        ys = [np.nan if r["accuracy"] is None else r["accuracy"] for r in run["per_snr"]]
        ax.plot(xs, ys, marker="o", label=label)
    chance = runs[0]["chance_level"]
    ax.axhline(chance, color="grey", ls="--", label=f"şans = 1/{runs[0]['n_devices']}")
    ax.set(
        xlabel="SNR (dB)",
        ylabel="test doğruluğu (çerçeve düzeyinde bölme)",
        ylim=(0.0, 1.02),
        title="RF parmak izi: cihaz tanıma",
    )
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)
    return fig


def fig_open_set(result: dict) -> Figure:
    """Per variant: histograms of known and unknown scores, with the threshold line."""
    variants = result["variants"]
    n_panels = len(variants)
    fig = _figure(4.3 * n_panels, 3.9)
    for k, (name, v) in enumerate(variants.items(), start=1):
        ax = fig.add_subplot(1, n_panels, k)
        known = np.asarray(v["scores"]["known"], dtype=np.float64)
        unknown = np.asarray(v["scores"]["unknown"], dtype=np.float64)
        thr = float(v["threshold"])
        values = np.concatenate([known, unknown, np.array([thr])])
        lo, hi = float(values.min()), float(values.max())
        if hi <= lo:
            hi = lo + 1e-6
        bins = np.linspace(lo, hi, 41)
        if known.size:
            ax.hist(known, bins=bins, alpha=0.6, label=f"bilinen test (n = {known.size})")
        if unknown.size:
            ax.hist(unknown, bins=bins, alpha=0.6, label=f"bilinmeyen test (n = {unknown.size})")
        ax.axvline(thr, color="k", ls="--", label=f"eşik = {thr:.3f}")
        ax.set(title=name, xlabel="bilinmeyen skoru (büyük = daha bilinmeyen)", ylabel="çerçeve sayısı")
        ax.legend(fontsize=7)
    return fig

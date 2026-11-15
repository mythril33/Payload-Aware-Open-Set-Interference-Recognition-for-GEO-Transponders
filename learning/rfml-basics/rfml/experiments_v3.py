"""Campaign-3 stages (experiments/PREREGISTRATION_V3.md).

Additive: nothing in rfml.experiments is changed, so campaigns 1 and 2 stay
reproducible bit for bit. Two stages:

- run_arm_control: the three Objectosphere arms of campaign 2 retrained at ONE
  shared training seed (so they differ only in the auxiliary-outlier pool),
  plus the Mahalanobis shrinkage sweep on the same CE model as campaign 2.
- run_split_counterfactual: the campaign-1 MLP and CNN1D scored on frames of
  unseen devices (campaign 1's test set) AND on new frames of the training
  devices, to tell device memorisation from frame memorisation.

Honesty rules are those of rfml.experiments: unknown test classes influence no
fit, selection or threshold; centroids and covariances come from known TRAIN
embeddings; thresholds from known val-calib frames; larger score = more
unknown-like.
"""

from __future__ import annotations

import numpy as np

from rfml import experiments as ex
from rfml.dataset import ModulationDataset, build_frames, make_transmitters
from rfml.metrics import accuracy
from rfml.models import CNN1D
from rfml.openset import (
    class_centroids,
    distance_unknown_score,
    fit_shared_covariance,
    mahalanobis_unknown_score,
    msp_unknown_score,
)
from rfml.train import (
    TrainConfig,
    ce_loss,
    predict_embeddings,
    predict_logits,
    set_seed,
    train_model,
)

ARM_SHARED_OFFSET = 101  # every arm trains at seed + 101 (campaign 2's full-arm seed)
SHRINKAGE_SWEEP = (0.01, 0.1, 0.5, 0.9, 1.0)  # 1.0 = scaled identity = Euclidean ranking
SEEN_FRAMES_PER_DEVICE = 3  # new frames per training device per test SNR
SEEN_SPAWN_KEY = (3, 1)  # SeedSequence spawn key of the seen-device stream; no role uses it

_SPLITS = ("val_calib", "test_known", "test_unknown")


def run_arm_control(
    scale: ex.Scale,
    seed: int,
    xi: float = 10.0,
    lam: float = 0.1,
    target_known_accept: float = 0.95,
    progress: ex.ProgressFn | None = None,
) -> dict:
    """Shared-seed Objectosphere arms (H7s) and the Mahalanobis shrinkage sweep.

    Data and the CE model are exactly campaign 2's (build_open_set_data, CE at
    set_seed(seed)). The three arms all train at seed + ARM_SHARED_OFFSET, so
    the only difference between them is which auxiliary frames they see.
    """
    ex._check_seed(seed)
    frames = ex.build_open_set_data(scale, seed)
    train_known = frames["train_known"]
    unknown_names = ex._frame_class_names(frames["test_unknown"]["tx_id"], ex.UNKNOWN, scale.tx_unknown)
    aux_names = ex._frame_class_names(frames["train_aux"]["tx_id"], ex.AUX, scale.tx_aux)
    known_labels = frames["test_known"]["label"]

    def variant(kind, calib_s, known_s, unknown_s, known_pred, hist, n_train, n_outlier):
        return ex._scorer_bench_variant(
            kind, calib_s, known_s, unknown_s, known_pred, known_labels,
            frames["test_known"]["snr_db"], frames["test_unknown"]["snr_db"], unknown_names,
            target_known_accept, hist, n_train, n_outlier,
        )

    # --- CE model (identical to campaign 2's) and the shrinkage sweep --------
    ex._emit(progress, "CE modeli eğitiliyor…")
    set_seed(seed)
    ce_model = CNN1D(n_classes=ex.N_CLASSES)
    ce_hist = train_model(
        ce_model,
        ModulationDataset(train_known),
        ModulationDataset(frames["val_select"]),
        ce_loss,
        TrainConfig(epochs=scale.epochs, patience=scale.patience, seed=seed),
        ex._epoch_scorer(progress, "CE", scale.epochs),
    )
    embed = {k: predict_embeddings(ce_model, frames[k]["iq"]) for k in _SPLITS}
    ce_pred = predict_logits(ce_model, frames["test_known"]["iq"]).argmax(axis=1)
    train_emb = predict_embeddings(ce_model, train_known["iq"])
    n_train = int(train_known["label"].size)

    centroids = class_centroids(train_emb, train_known["label"], ex.N_CLASSES)
    variants: dict[str, dict] = {
        "CE+distance": variant(
            "posthoc", *(distance_unknown_score(embed[k], centroids) for k in _SPLITS),
            ce_pred, ce_hist, n_train, 0,
        )
    }
    for shrinkage in SHRINKAGE_SWEEP:
        means, precision = fit_shared_covariance(
            train_emb, train_known["label"], ex.N_CLASSES, shrinkage=shrinkage
        )
        variants[f"CE+mahalanobis@{shrinkage:g}"] = variant(
            "posthoc", *(mahalanobis_unknown_score(embed[k], means, precision) for k in _SPLITS),
            ce_pred, ce_hist, n_train, 0,
        )

    # --- three arms, one training seed ---------------------------------------
    arm_seed = seed + ARM_SHARED_OFFSET
    for arm_name, aux_classes, _campaign2_offset in ex.SCORER_BENCH_ARMS:
        mask = np.isin(aux_names, aux_classes)
        train_c = ex.concat_frames([train_known, {k: v[mask] for k, v in frames["train_aux"].items()}])
        ex._emit(progress, f"{arm_name} (ortak tohum) eğitiliyor…")
        set_seed(arm_seed)
        model = CNN1D(n_classes=ex.N_CLASSES)
        hist = train_model(
            model,
            ModulationDataset(train_c),
            ModulationDataset(frames["val_select"]),  # known only: no outliers in selection
            ex._objectosphere_fn(xi, lam),
            TrainConfig(epochs=scale.epochs, patience=scale.patience, seed=arm_seed),
            ex._epoch_scorer(progress, arm_name, scale.epochs),
        )
        logits = {k: predict_logits(model, frames[k]["iq"]) for k in _SPLITS}
        variants[arm_name] = variant(
            "objectosphere", *(msp_unknown_score(logits[k]) for k in _SPLITS),
            logits["test_known"].argmax(axis=1), hist,
            int(train_c["label"].size), int((train_c["label"] == -1).sum()),
        )
        variants[arm_name]["train_seed"] = int(arm_seed)

    return {
        "stage": "arm_control",
        "scale": ex._scale_dict(scale),
        "seed": int(seed),
        "arm_train_seed": int(arm_seed),
        "split": (
            "device-level; campaign-2 data and CE model; the three Objectosphere arms share "
            "one training seed and differ only in the auxiliary-outlier pool; unknown test "
            "frames (64QAM, 4PAM) influence no fit, selection or threshold"
        ),
        "shrinkage_sweep": list(SHRINKAGE_SWEEP),
        "target_known_accept": float(target_known_accept),
        "objectosphere": {"xi": float(xi), "lam": float(lam)},
        "chance": {"closed_set": ex.CHANCE_CLOSED_SET, "auroc": ex.CHANCE_AUROC},
        "frames": {name: int(f["label"].size) for name, f in frames.items()},
        "variants": variants,
    }


def run_split_counterfactual(scale: ex.Scale, seed: int, progress: ex.ProgressFn | None = None) -> dict:
    """Campaign-1 models scored on unseen devices and on new frames of seen devices.

    Training, data and model selection are exactly run_modulation's (impaired
    devices). The seen-device test frames come from the TRAINING devices,
    rebuilt from the same role stream (checked bit for bit against the
    training frames) and drawn from a stream no role uses.
    """
    ex._check_seed(seed)
    train, val, test_by_snr = ex.build_modulation_data(scale, True, seed)

    # Rebuild the training devices: the first draws of the mod.train stream.
    rng = ex.role_rngs(seed)["mod.train"]
    tx_train = make_transmitters(ex.KNOWN, scale.tx_train, rng, impaired=True)
    rebuilt = build_frames(tx_train, scale.frames_train, ex.N_SAMPLES, ex.TRAIN_SNRS, rng, ex.KNOWN)
    if not np.array_equal(rebuilt["iq"], train["iq"]):
        raise RuntimeError("rebuilt training devices do not reproduce the training frames")

    seen_rng = np.random.default_rng(np.random.SeedSequence(entropy=int(seed), spawn_key=SEEN_SPAWN_KEY))
    seen_by_snr = {
        snr: build_frames(tx_train, SEEN_FRAMES_PER_DEVICE, ex.N_SAMPLES, (snr,), seen_rng, ex.KNOWN)
        for snr in ex.MOD_TEST_SNRS
    }

    models: dict[str, dict] = {}
    for name in ex.MODULATION_MODELS:
        ex._emit(progress, f"{name} eğitiliyor…")
        set_seed(seed)
        model = ex.MODEL_BUILDERS[name]()
        hist = train_model(
            model,
            ModulationDataset(train),
            ModulationDataset(val),  # unseen validation devices, as in campaign 1
            ce_loss,
            TrainConfig(epochs=scale.epochs, patience=scale.patience, seed=seed),
            ex._epoch_scorer(progress, name, scale.epochs),
        )
        unseen_per_snr, unseen_overall, _ = ex._evaluate_modulation(model, test_by_snr)
        seen_per_snr, seen_overall, _ = ex._evaluate_modulation(model, seen_by_snr)
        train_pred = predict_logits(model, train["iq"]).argmax(axis=1)
        models[name] = {
            "epochs_run": len(hist["train_loss"]),
            "best_epoch": hist["best_epoch"],
            "train_accuracy": accuracy(train_pred, train["label"]),
            "unseen_devices": {"per_snr": unseen_per_snr, "overall": unseen_overall},
            "seen_devices_new_frames": {"per_snr": seen_per_snr, "overall": seen_overall},
        }

    return {
        "stage": "split_counterfactual",
        "scale": ex._scale_dict(scale),
        "seed": int(seed),
        "split": (
            "trained and selected as campaign 1 (device-level); scored on unseen devices and "
            "on new frames of the training devices"
        ),
        "classes": list(ex.KNOWN),
        "chance_level": ex.CHANCE_CLOSED_SET,
        "test_snr_db": list(ex.MOD_TEST_SNRS),
        "devices_per_class": {"train": scale.tx_train, "val_select": scale.tx_val, "test": scale.tx_test},
        "seen_frames_per_device_per_snr": SEEN_FRAMES_PER_DEVICE,
        "rate_definitions": {
            "accuracy": "positive = predicted class equals the true class; denominator = the frames of that row",
        },
        "models": models,
    }

"""Turning stored spectrograms into model inputs (P6 §2)."""
from __future__ import annotations

import numpy as np

CORE_DB = -3.0          # mask level above which a bin counts as "inside a planned carrier"
CLIP_DB = (-60.0, 20.0)
SCALE_DB = 20.0


def reference_level(spec_db: np.ndarray, mask_db: np.ndarray) -> np.ndarray:
    """Per-sample mean PSD (dB) over the planned carriers' core bins: the level everything is referred to."""
    psd = np.mean(10 ** (spec_db.astype(np.float32) / 10), axis=1)            # (N, F), time-averaged
    core = mask_db > CORE_DB
    return 10 * np.log10((psd * core).sum(axis=1) / core.sum(axis=1))


def preprocess(spec_db: np.ndarray, mask_db: np.ndarray, level: str = "carrier", time_pool: int = 2,
               absolute_ref_db: float | None = None) -> np.ndarray:
    """(N,128,512) dB spectrograms and (N,512) masks -> (N,2,128/time_pool,512) float32.

    level="carrier":  each sample is referred to its own planned-carrier level, so absolute power
                      (downlink fade, amplifier compression, calibration) is not visible to the model.
    level="absolute": one fixed reference for all samples (absolute_ref_db, taken from training data).
    """
    spec = spec_db.astype(np.float32)
    if level == "carrier":
        ref = reference_level(spec_db, mask_db)[:, None, None]
    elif level == "absolute":
        if absolute_ref_db is None:
            raise ValueError("absolute level needs absolute_ref_db from the training split")
        ref = np.float32(absolute_ref_db)
    else:
        raise ValueError(f"unknown level mode {level!r}")
    n, t, f = spec.shape
    if time_pool > 1:                      # longer integration: average power, not dB
        spec = 10 * np.log10(np.mean(10 ** (spec.reshape(n, t // time_pool, time_pool, f) / 10), axis=2))
    x = np.clip(spec - ref, *CLIP_DB) / SCALE_DB
    m = np.broadcast_to((mask_db.astype(np.float32) / SCALE_DB)[:, None, :], x.shape)
    return np.stack([x, m], axis=1).astype(np.float32)


def select(d: dict, labels: tuple, all_labels: tuple) -> dict:
    """Keep the samples whose label is in `labels` and re-index labels to that order."""
    keep_idx = [all_labels.index(lab) for lab in labels]
    keep = np.isin(d["label"], keep_idx)
    remap = {old: new for new, old in enumerate(keep_idx)}
    return {"spec": d["spec"][keep], "mask": d["mask"][keep], "seed": d["seed"][keep],
            "label": np.array([remap[v] for v in d["label"][keep]], np.int64),
            "meta": [m for m, k in zip(d["meta"], keep) if k]}

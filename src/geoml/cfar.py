"""Cell-averaging CFAR baseline on the spectrogram (P6 §5). NumPy only."""
from __future__ import annotations

import numpy as np

GUARD, TRAIN = 1, 4          # cells on each side (cell = 187.5 kHz)


def ratio_db(spec_db: np.ndarray) -> np.ndarray:
    """CA-CFAR test statistic per cell along frequency: cell power over the mean of its training cells."""
    p = 10 ** (spec_db.astype(np.float32) / 10)
    c = np.cumsum(np.pad(p, [(0, 0)] * (p.ndim - 1) + [(1, 0)]), axis=-1)
    n = p.shape[-1]
    i = np.arange(n)
    win = lambda a, b: c[..., np.clip(b + 1, 0, n)] - c[..., np.clip(a, 0, n)]      # sum over cells a..b
    left = win(i - GUARD - TRAIN, i - GUARD - 1)
    right = win(i + GUARD + 1, i + GUARD + TRAIN)
    cells = (np.clip(i - GUARD, 0, n) - np.clip(i - GUARD - TRAIN, 0, n)) + \
            (np.clip(i + GUARD + TRAIN + 1, 0, n) - np.clip(i + GUARD + 1, 0, n))
    return 10 * np.log10(p / ((left + right) / cells))


def testable_cells(mask_db: np.ndarray, freqs: np.ndarray, bandwidth: np.ndarray, use_plan: bool) -> np.ndarray:
    """Cells the detector looks at: inside the transponder, and (plan-aware) away from carrier edges.

    Plan-aware: a cell is skipped when the planned level changes by more than 1 dB inside its window,
    which is where a plain CFAR fires on the carrier edge itself.
    """
    ok = np.abs(freqs)[None, :] <= 0.48 * np.asarray(bandwidth)[:, None]
    if use_plan:
        half = GUARD + TRAIN
        pad = np.pad(mask_db.astype(np.float32), ((0, 0), (half, half)), mode="edge")
        w = np.lib.stride_tricks.sliding_window_view(pad, 2 * half + 1, axis=1)
        ok &= (w.max(-1) - w.min(-1)) <= 1.0
    return ok


def features(spec_db: np.ndarray, mask_db: np.ndarray, freqs: np.ndarray, bandwidth: np.ndarray,
             use_plan: bool) -> np.ndarray:
    """(N,2): strongest time-averaged cell (steady interferers) and strongest single cell (moving ones)."""
    out = np.empty((len(spec_db), 2), np.float32)
    ok = testable_cells(mask_db, freqs, bandwidth, use_plan)
    for k in range(len(spec_db)):
        r = ratio_db(spec_db[k])[:, ok[k]]
        avg = ratio_db(10 * np.log10(np.mean(10 ** (spec_db[k].astype(np.float32) / 10), axis=0)))[ok[k]]
        out[k] = (avg.max(), r.max()) if ok[k].any() else (0.0, 0.0)     # nothing testable: no evidence
    return out


def scores(feat: np.ndarray, clean_val_feat: np.ndarray) -> np.ndarray:
    """One detection score: each feature in units of its clean-validation spread, then the larger."""
    mu, sd = clean_val_feat.mean(0), clean_val_feat.std(0) + 1e-6
    return ((feat - mu) / sd).max(axis=1)

"""Frame datasets built from simulated transmitters.

Leakage rule: every frame of one transmitter (its modulation plus its impairments)
belongs to one split. The one exception is the RF fingerprinting stage, where the
device IS the label, so split_frames_stratified splits at frame level. Callers must
not use that function for modulation-classification splits.
"""

from __future__ import annotations

from typing import Sequence

import numpy as np
import torch
from torch.utils.data import Dataset

from rfml.signals import Transmitter, iq_channels, make_frame


def make_transmitters(
    modulations: Sequence[str],
    n_per_modulation: int,
    rng: np.random.Generator,
    impaired: bool = True,
) -> list[Transmitter]:
    """Draw n_per_modulation devices per modulation, grouped by modulation in input order."""
    transmitters: list[Transmitter] = []
    for modulation in modulations:
        for _ in range(n_per_modulation):
            transmitters.append(Transmitter.random(modulation, rng, impaired=impaired))
    return transmitters


def build_frames(
    transmitters: Sequence[Transmitter],
    frames_per_transmitter: int,
    n_samples: int,
    snr_db_values: Sequence[float],
    rng: np.random.Generator,
    class_names: Sequence[str],
) -> dict:
    """Generate frames for every transmitter, in transmitter-major order.

    Returns numpy arrays keyed by 'iq' (float32 (N, 2, n)), 'label' (int64, -1 when
    the modulation is not in class_names, so it is an unknown), 'tx_id' (int64,
    index into `transmitters`) and 'snr_db' (float32, drawn uniformly per frame).
    """
    snr_values = np.asarray(snr_db_values, dtype=np.float64)
    if snr_values.size == 0:
        raise ValueError("snr_db_values must not be empty")
    class_index = {name: i for i, name in enumerate(class_names)}

    n_total = len(transmitters) * frames_per_transmitter
    iq = np.zeros((n_total, 2, n_samples), dtype=np.float32)
    label = np.full(n_total, -1, dtype=np.int64)
    tx_id = np.zeros(n_total, dtype=np.int64)
    snr = np.zeros(n_total, dtype=np.float32)

    row = 0
    for t, tx in enumerate(transmitters):
        tx_label = class_index.get(tx.modulation, -1)
        for _ in range(frames_per_transmitter):
            snr_frame = float(snr_values[rng.integers(snr_values.size)])
            frame = make_frame(tx, n_samples, snr_frame, rng)
            iq[row] = iq_channels(frame)
            label[row] = tx_label
            tx_id[row] = t
            snr[row] = snr_frame
            row += 1
    return {"iq": iq, "label": label, "tx_id": tx_id, "snr_db": snr}


class ModulationDataset(Dataset):
    """Torch view of a build_frames() dict, optionally restricted to `indices`.

    Arrays are not copied; only the selected rows are indexed on access. Labels are
    returned as-is, so -1 (unknown or outlier) must be handled by the loss function.
    """

    def __init__(self, data: dict, indices: np.ndarray | None = None) -> None:
        if indices is None:
            indices = np.arange(len(data["label"]))
        self.indices = np.asarray(indices, dtype=np.int64).reshape(-1)
        self._iq = data["iq"]
        self.label = data["label"][self.indices]
        self.tx_id = data["tx_id"][self.indices]
        self.snr_db = data["snr_db"][self.indices]

    def __len__(self) -> int:
        return int(self.indices.size)

    def __getitem__(self, i: int) -> tuple[torch.Tensor, torch.Tensor]:
        j = int(self.indices[i])
        x = torch.from_numpy(np.array(self._iq[j], dtype=np.float32))  # copy: safe for workers
        y = torch.tensor(int(self.label[i]), dtype=torch.int64)
        return x, y


def split_frames_stratified(
    tx_id: np.ndarray,
    fractions: tuple[float, float, float],
    rng: np.random.Generator,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Split frame indices into (train, val, test) within each transmitter.

    This is a FRAME-level split, meant only for RF fingerprinting, where the device is
    the label. Each transmitter contributes at least one frame to train, so every class
    is learnable. Small transmitters can leave val or test empty; callers must report
    the counts. Returns sorted int64 index arrays that are disjoint and cover all frames.
    """
    tx_id = np.asarray(tx_id)
    if tx_id.ndim != 1:
        raise ValueError("tx_id must be 1-D")
    f_train, f_val, f_test = (float(f) for f in fractions)
    if min(f_train, f_val, f_test) < 0.0 or abs(f_train + f_val + f_test - 1.0) > 1e-9:
        raise ValueError("fractions must be non-negative and sum to 1")

    train_parts: list[np.ndarray] = []
    val_parts: list[np.ndarray] = []
    test_parts: list[np.ndarray] = []
    for tx in np.unique(tx_id):
        idx = rng.permutation(np.flatnonzero(tx_id == tx))
        n = idx.size
        # Cut points on a shuffled per-device list. Round half up, and keep the cuts
        # ordered and inside [0, n]. The max(1, ...) forces one train frame per device.
        cut_train = min(n, max(1, int(np.floor(f_train * n + 0.5))))
        cut_val = min(n, max(cut_train, int(np.floor((f_train + f_val) * n + 0.5))))
        train_parts.append(idx[:cut_train])
        val_parts.append(idx[cut_train:cut_val])
        test_parts.append(idx[cut_val:])

    def _collect(parts: list[np.ndarray]) -> np.ndarray:
        if not parts:
            return np.zeros(0, dtype=np.int64)
        return np.sort(np.concatenate(parts)).astype(np.int64)

    return _collect(train_parts), _collect(val_parts), _collect(test_parts)

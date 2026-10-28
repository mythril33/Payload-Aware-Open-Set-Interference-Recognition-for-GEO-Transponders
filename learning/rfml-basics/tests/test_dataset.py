"""Tests for rfml.dataset: transmitter lists, frame building, torch view and splits."""

from __future__ import annotations

import numpy as np
import pytest
import torch

from rfml.dataset import (
    ModulationDataset,
    build_frames,
    make_transmitters,
    split_frames_stratified,
)

N_SAMPLES = 128
SNR_VALUES = (0.0, 10.0, 20.0)
CLASS_NAMES = ("BPSK", "QPSK", "8PSK")
MODS = ("BPSK", "QPSK", "64QAM")  # 64QAM is outside CLASS_NAMES -> label -1


@pytest.fixture(scope="module")
def frames() -> dict:
    rng = np.random.default_rng(0)
    txs = make_transmitters(MODS, 2, rng)  # 6 transmitters
    return build_frames(txs, 3, N_SAMPLES, SNR_VALUES, rng, CLASS_NAMES)


def test_make_transmitters_order_and_count() -> None:
    rng = np.random.default_rng(1)
    txs = make_transmitters(["BPSK", "64QAM"], 3, rng)
    assert [t.modulation for t in txs] == ["BPSK"] * 3 + ["64QAM"] * 3


def test_make_transmitters_ideal_when_not_impaired() -> None:
    txs = make_transmitters(["QPSK"], 2, np.random.default_rng(2), impaired=False)
    assert all(t.iq_gain == 1.0 and t.phase_noise_std == 0.0 for t in txs)


def test_build_frames_shapes_and_dtypes(frames: dict) -> None:
    n_total = 6 * 3
    assert frames["iq"].shape == (n_total, 2, N_SAMPLES)
    assert frames["iq"].dtype == np.float32
    assert frames["label"].shape == (n_total,)
    assert frames["label"].dtype == np.int64
    assert frames["tx_id"].shape == (n_total,)
    assert frames["tx_id"].dtype == np.int64
    assert frames["snr_db"].shape == (n_total,)
    assert frames["snr_db"].dtype == np.float32
    assert set(frames) == {"iq", "label", "tx_id", "snr_db"}


def test_build_frames_labels_and_unknown_minus_one(frames: dict) -> None:
    # Per modulation: 2 transmitters x 3 frames = 6 frames. BPSK -> 0, QPSK -> 1,
    # and 64QAM is not in CLASS_NAMES, so it must be -1 (unknown) rather than an index.
    expected = np.array([0] * 6 + [1] * 6 + [-1] * 6, dtype=np.int64)
    np.testing.assert_array_equal(frames["label"], expected)


def test_build_frames_tx_id_and_snr_ranges(frames: dict) -> None:
    # Transmitter-major order: 3 consecutive frames per transmitter, ids 0..5.
    np.testing.assert_array_equal(frames["tx_id"], np.repeat(np.arange(6), 3))
    allowed = np.asarray(SNR_VALUES, dtype=np.float32)
    assert np.all(np.isin(frames["snr_db"], allowed))
    # With 18 draws from 3 values, every SNR should appear at least once.
    assert set(np.unique(frames["snr_db"]).tolist()) == set(allowed.tolist())


def test_build_frames_iq_is_finite(frames: dict) -> None:
    assert np.all(np.isfinite(frames["iq"]))


def test_build_frames_rejects_empty_snr_list() -> None:
    txs = make_transmitters(["BPSK"], 1, np.random.default_rng(3))
    with pytest.raises(ValueError):
        build_frames(txs, 1, 64, [], np.random.default_rng(3), CLASS_NAMES)


def test_modulation_dataset_item_types_and_shape(frames: dict) -> None:
    ds = ModulationDataset(frames)
    assert len(ds) == 18
    x, y = ds[0]
    assert isinstance(x, torch.Tensor) and isinstance(y, torch.Tensor)
    assert x.dtype == torch.float32
    assert tuple(x.shape) == (2, N_SAMPLES)
    assert y.dtype == torch.int64
    assert y.ndim == 0


def test_modulation_dataset_returns_matching_rows(frames: dict) -> None:
    ds = ModulationDataset(frames)
    x, y = ds[10]
    np.testing.assert_array_equal(x.numpy(), frames["iq"][10])
    assert int(y) == frames["label"][10]


def test_modulation_dataset_indices_subset(frames: dict) -> None:
    idx = np.array([17, 2, 9])
    ds = ModulationDataset(frames, indices=idx)
    assert len(ds) == 3
    # Subset order is preserved and the metadata arrays are restricted to it.
    np.testing.assert_array_equal(ds.tx_id, frames["tx_id"][idx])
    np.testing.assert_array_equal(ds.snr_db, frames["snr_db"][idx])
    np.testing.assert_array_equal(ds.label, frames["label"][idx])
    x, y = ds[1]
    np.testing.assert_array_equal(x.numpy(), frames["iq"][2])
    assert int(y) == frames["label"][2]


def test_split_frames_stratified_disjoint_and_covering() -> None:
    rng = np.random.default_rng(4)
    tx_id = np.repeat(np.arange(5), [10, 7, 3, 1, 12])
    train, val, test = split_frames_stratified(tx_id, (0.6, 0.2, 0.2), rng)
    all_idx = np.concatenate([train, val, test])
    assert len(np.unique(all_idx)) == all_idx.size  # disjoint
    np.testing.assert_array_equal(np.sort(all_idx), np.arange(tx_id.size))  # covers all
    for dtype_arr in (train, val, test):
        assert dtype_arr.dtype == np.int64


def test_split_every_transmitter_present_in_train() -> None:
    rng = np.random.default_rng(5)
    tx_id = np.repeat(np.arange(4), [10, 2, 1, 6])
    train, _, _ = split_frames_stratified(tx_id, (0.5, 0.25, 0.25), rng)
    assert set(np.unique(tx_id[train]).tolist()) == {0, 1, 2, 3}


def test_split_is_stratified_per_transmitter() -> None:
    # With 10 frames per device and fractions (0.6, 0.2, 0.2) each device gives
    # exactly 6 train, 2 val and 2 test frames.
    rng = np.random.default_rng(6)
    tx_id = np.repeat(np.arange(3), 10)
    train, val, test = split_frames_stratified(tx_id, (0.6, 0.2, 0.2), rng)
    for t in range(3):
        assert np.sum(tx_id[train] == t) == 6
        assert np.sum(tx_id[val] == t) == 2
        assert np.sum(tx_id[test] == t) == 2


def test_split_single_frame_device_goes_to_train() -> None:
    rng = np.random.default_rng(7)
    tx_id = np.array([0, 0, 0, 1])  # device 1 has one frame
    train, val, test = split_frames_stratified(tx_id, (0.6, 0.2, 0.2), rng)
    assert 3 in train.tolist()
    assert 3 not in val.tolist() and 3 not in test.tolist()


def test_split_is_deterministic_with_seed() -> None:
    tx_id = np.repeat(np.arange(4), 8)
    a = split_frames_stratified(tx_id, (0.6, 0.2, 0.2), np.random.default_rng(8))
    b = split_frames_stratified(tx_id, (0.6, 0.2, 0.2), np.random.default_rng(8))
    for x, y in zip(a, b):
        np.testing.assert_array_equal(x, y)


def test_split_rejects_bad_fractions() -> None:
    with pytest.raises(ValueError):
        split_frames_stratified(np.arange(4), (0.5, 0.5, 0.5), np.random.default_rng(9))

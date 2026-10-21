"""B2 observed-channel normalization, augmentation and lazy batch contracts."""
from copy import deepcopy

import numpy as np
import pytest

pytest.importorskip("torch")

from geosim import FS_MON
from geosim.b2_protocol import LABELS
from geoml.b2_data import (ARRAY_KEYS, FeatureRole, augment_inputs, iter_batches,
                           preprocess_b2, validate_observations)
from geoml.b2_train import B2TrainConfig
from geoml.data import preprocess_dual


def observations(group=100, *, t=8, f=64):
    n = len(LABELS)
    spec = np.full((n, 2, t, f), -80, np.float32)
    spec[:, 1] = -86
    mask = np.full((n, 2, f), -60, np.float32)
    mask[:, 0, f // 4:f // 4 + 5] = 0
    mask[:, 1, f // 2:f // 2 + 5] = 0
    return {"spec": spec, "mask": mask,
            "residual": np.full((n, t, f), -100, np.float32),
            "label": np.arange(n, dtype=np.int64),
            "seed": np.full(n, group, np.int64),
            "plan_consistency": np.arange(n, dtype=np.int64) % 2,
            "meta": [{"hidden_event": label, "true_ibo": 1} for label in LABELS]}


def inputs(data, **kwargs):
    return preprocess_b2(data["spec"], data["mask"], data["residual"], **kwargs)


def test_fifth_channel_retains_residual_level_and_common_polarization_reference():
    data = observations()
    output = inputs(data, time_pool=2)
    assert output.shape == (8, 5, 4, 64) and output.dtype == np.float32
    np.testing.assert_allclose(output[:, 0], 0, atol=1e-6)
    np.testing.assert_allclose(output[:, 1], -0.3, atol=1e-6)
    np.testing.assert_allclose(output[:, 4], -1, atol=1e-6)
    np.testing.assert_array_equal(output[:, 2], np.broadcast_to(data["mask"][:, 0, None] / 20, output[:, 2].shape))
    np.testing.assert_array_equal(output[:, 3], np.broadcast_to(data["mask"][:, 1, None] / 20, output[:, 3].shape))
    # A residual-specific power reference would erase this 20 dB reduction.
    assert not np.allclose(output[:, 4], output[:, 0])


def test_level_shift_invariance_and_matched_existing_views():
    data = observations()
    shifted = deepcopy(data)
    shifted["spec"] += 7.5
    shifted["residual"] += 7.5
    np.testing.assert_allclose(inputs(data), inputs(shifted), atol=1e-6)
    for view in ("dual", "co"):
        np.testing.assert_array_equal(inputs(data, view=view),
                                      preprocess_dual(data["spec"], data["mask"], view=view))
    absolute = inputs(data, level="absolute", absolute_ref_db=-90)
    np.testing.assert_allclose(absolute[:, 0], .5, atol=1e-6)
    np.testing.assert_allclose(absolute[:, 4], -.5, atol=1e-6)


def test_residual_pooling_averages_physical_power_before_db():
    data = observations(t=4)
    data["residual"][:, 0::2] = -100
    data["residual"][:, 1::2] = -80
    expected_db = 10 * np.log10((1e-10 + 1e-8) / 2)
    output = inputs(data, time_pool=2)
    np.testing.assert_allclose(output[:, 4], (expected_db + 80) / 20, atol=1e-6)
    assert not np.isclose(output[0, 4, 0, 0], -.5)  # Arithmetic dB averaging.


@pytest.mark.parametrize("change", [
    {"view": "oracle"}, {"time_pool": 3}, {"time_pool": True},
    {"level": "absolute"}, {"level": "absolute", "absolute_ref_db": np.nan},
])
def test_invalid_preprocessing_settings_fail(change):
    with pytest.raises(ValueError):
        inputs(observations(), **change)


@pytest.mark.parametrize("key,mutation", [
    ("spec", lambda x: x[:, 0]), ("mask", lambda x: x[:, 0]),
    ("residual", lambda x: x[:, :, :-1]),
    ("spec", lambda x: np.full_like(x, np.nan)),
    ("residual", lambda x: np.full_like(x, np.inf)),
    ("mask", lambda x: np.full_like(x, -60)),
    ("label", lambda x: x.astype(float)), ("label", lambda x: np.full_like(x, 8)),
    ("seed", lambda x: np.full_like(x, -1)),
    ("plan_consistency", lambda x: np.full_like(x, 2)),
    ("plan_consistency", lambda x: x[:, None]),
])
def test_invalid_observation_or_target_contract_fails(key, mutation):
    data = observations()
    data[key] = mutation(data[key])
    with pytest.raises(ValueError):
        validate_observations(data)


def test_only_observed_arrays_and_explicit_targets_enter_batches():
    data = observations()
    original = next(iter_batches(FeatureRole(data), B2TrainConfig(batch=8), -80))
    data["meta"] = object()
    data["true_symbols"] = object()
    data["true_xpd"] = np.full(8, np.nan)
    changed = next(iter_batches(FeatureRole(data), B2TrainConfig(batch=8), -80))
    assert set(validate_observations(data)) == set(ARRAY_KEYS)
    assert set(changed) == {"x", "label", "seed", "plan_consistency"}
    for key in changed:
        np.testing.assert_array_equal(changed[key], original[key])


def test_continuous_mask_jitter_leaves_psd_and_residual_unchanged_without_wrap():
    data = observations(t=4, f=512)
    x = inputs(data)
    before = x.copy()
    shifted, offsets = augment_inputs(x, view="b2", rng=np.random.default_rng(14),
                                     plan_shift_probability=1, mirror=False, time_shift=False,
                                     return_shifts=True)
    np.testing.assert_array_equal(x, before)
    np.testing.assert_array_equal(shifted[:, [0, 1, 4]], before[:, [0, 1, 4]])
    assert np.all(np.abs(offsets) <= .5e6) and np.all(offsets != 0)
    assert len(np.unique(offsets)) == len(offsets)
    bin_hz = FS_MON / 512
    assert np.any(np.abs(offsets / bin_hz - np.round(offsets / bin_hz)) > 0.1)
    assert np.any(shifted[:, 2:4] != before[:, 2:4])
    assert np.min(shifted[:, 2:4]) >= -3 and np.max(shifted[:, 2:4]) <= 1e-6
    np.testing.assert_array_equal(shifted[:, 2:4, 0], shifted[:, 2:4, -1])
    edge = np.zeros((8, 5, 4, 512), np.float32)
    edge[:, 2:4] = -3
    edge[:, 2:4, :, 0] = 0
    moved = augment_inputs(edge, view="b2", rng=np.random.default_rng(14),
                           plan_shift_probability=1, mirror=False, time_shift=False)
    np.testing.assert_array_equal(moved[:, 2:4, :, -1], -3)


def test_mirror_and_time_augmentation_remain_aligned_and_reproducible():
    signal = np.arange(8 * 4 * 32, dtype=np.float32).reshape(8, 4, 32) / 1024
    x = np.stack([signal + offset for offset in range(5)], axis=1)
    first = augment_inputs(x, view="b2", rng=np.random.default_rng(18), plan_shift_probability=0)
    second = augment_inputs(x, view="b2", rng=np.random.default_rng(18), plan_shift_probability=0)
    np.testing.assert_array_equal(first, second)
    assert not np.array_equal(first, x)
    for channel in range(1, 5):
        np.testing.assert_allclose(first[:, channel] - first[:, 0], channel, atol=5e-7)


def test_lazy_feature_batches_read_only_one_shard_before_yielding(tmp_path, monkeypatch):
    from geosim import b2_features

    shards = [observations(3_000_000), observations(3_000_001)]
    reads, orders, header_reads = [], [], []
    manifest = {"protocol": "B2-features/1", "labels": list(LABELS), "roles": {
        "train": {"scenario_seeds": [3_000_000, 3_000_001], "n_samples": 16,
                  "shards": [{"n_samples": 8}, {"n_samples": 8}]}}}

    def header(root):
        header_reads.append(root)
        return manifest

    def iterator(root, role, *, indices=None):
        assert role == "train"
        order = list(range(2)) if indices is None else list(indices)
        orders.append(order)
        for index in order:
            reads.append(index)
            yield shards[index]

    monkeypatch.setattr(b2_features, "read_feature_manifest", header)
    monkeypatch.setattr(b2_features, "iter_feature_shards", iterator)
    cache = {}
    source = FeatureRole((tmp_path, "train"), manifest_cache=cache)
    same = FeatureRole((tmp_path, "train"), manifest_cache=cache)
    assert len(header_reads) == 1 and len(same) == 16
    assert source.n_batches(3) == 6
    batches = iter_batches(source, B2TrainConfig(batch=3), -80)
    first = next(batches)
    assert reads == [0] and first["x"].shape == (3, 5, 4, 64)
    assert len(next(batches)["label"]) == 3 and reads == [0]
    assert len(next(batches)["label"]) == 2 and reads == [0]
    assert len(next(batches)["label"]) == 3 and reads == [0, 1]
    assert sum(len(item["label"]) for item in batches) == 5
    assert orders == [[0, 1]]

    def epoch(seed):
        return list(iter_batches(source, B2TrainConfig(batch=3), -80,
                                 shuffle=True, rng=np.random.default_rng(seed)))

    first_epoch, second_epoch = epoch(5), epoch(5)
    first_pairs = [(int(seed), int(label)) for batch in first_epoch for seed, label in zip(batch["seed"], batch["label"])]
    second_pairs = [(int(seed), int(label)) for batch in second_epoch for seed, label in zip(batch["seed"], batch["label"])]
    assert first_pairs == second_pairs
    assert set(first_pairs) == {(group, label) for group in (3_000_000, 3_000_001) for label in range(8)}
    assert len(first_pairs) == len(set(first_pairs)) == 16
    assert all(sorted(order) == [0, 1] for order in orders)


@pytest.mark.parametrize("bad", [None, {}, ("path", "test-matched"), ("path", "unknown")])
def test_invalid_feature_source_fails(bad):
    with pytest.raises(ValueError):
        FeatureRole(bad)

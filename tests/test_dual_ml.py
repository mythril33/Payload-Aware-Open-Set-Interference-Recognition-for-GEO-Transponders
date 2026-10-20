"""Dual-polarization observables, shared normalization and model compatibility."""
from dataclasses import asdict, replace

import numpy as np
import pytest

from geoml.data import preprocess, preprocess_dual, reference_level


def _data(n=6, seed=0):
    rng = np.random.default_rng(seed)
    spec = (-85 + rng.normal(size=(n, 2, 8, 32))).astype(np.float32)
    spec[:, 0, :, 8:16] += 25
    spec[:, 1, :, 20:28] += 23
    labels = np.arange(n, dtype=np.int64) % 2
    spec[labels == 1, 0, :, 24] += 18
    mask = np.full((n, 2, 32), -60., np.float32)
    mask[:, 0, 8:16] = 0
    mask[:, 1, 20:28] = 0
    return {"spec": spec, "mask": mask, "label": labels}


def test_dual_channels_use_separate_plans_and_one_co_pol_reference():
    d = _data(2)
    x = preprocess_dual(d["spec"], d["mask"], time_pool=1)
    assert x.dtype == np.float32 and x.shape == (2, 4, 8, 32)
    ref = reference_level(d["spec"][:, 0], d["mask"][:, 0])[:, None, None]
    np.testing.assert_allclose(x[:, 0], np.clip(d["spec"][:, 0] - ref, -60, 20) / 20)
    np.testing.assert_allclose(x[:, 1], np.clip(d["spec"][:, 1] - ref, -60, 20) / 20)
    np.testing.assert_array_equal(x[:, 2], np.broadcast_to(d["mask"][:, 0, None, :] / 20, (2, 8, 32)))
    np.testing.assert_array_equal(x[:, 3], np.broadcast_to(d["mask"][:, 1, None, :] / 20, (2, 8, 32)))


def test_common_fade_is_removed_but_relative_cross_power_is_retained():
    d = _data(2)
    original = preprocess_dual(d["spec"], d["mask"], time_pool=1)
    faded = preprocess_dual(d["spec"] + 7.5, d["mask"], time_pool=1)
    np.testing.assert_allclose(faded, original, atol=1e-6)
    changed = d["spec"].copy()
    changed[:, 1] += 3
    cross_gain = preprocess_dual(changed, d["mask"], time_pool=1)
    np.testing.assert_allclose(cross_gain[:, 1] - original[:, 1], 3 / 20, atol=1e-6)
    np.testing.assert_array_equal(cross_gain[:, (0, 2, 3)], original[:, (0, 2, 3)])


def test_dual_time_pooling_averages_linear_power_and_co_matches_legacy():
    d = _data(2)
    d["spec"][:, :, ::2] = -80
    d["spec"][:, :, 1::2] = -60
    dual = preprocess_dual(d["spec"], d["mask"], level="absolute", absolute_ref_db=-60, time_pool=2)
    expected = (10 * np.log10((10 ** -8 + 10 ** -6) / 2) + 60) / 20
    np.testing.assert_allclose(dual[:, :2], expected, atol=1e-6)
    co = preprocess_dual(d["spec"], d["mask"], time_pool=2, view="co")
    np.testing.assert_array_equal(co, preprocess(d["spec"][:, 0], d["mask"][:, 0], time_pool=2))


@pytest.mark.parametrize("change", ["wrong_spec", "wrong_mask", "no_cross_core", "complex", "nan", "empty"])
def test_dual_input_contract_rejects_malformed_observations(change):
    d = _data(2)
    if change == "wrong_spec":
        d["spec"] = d["spec"][:, 0]
    elif change == "wrong_mask":
        d["mask"] = d["mask"][:, 0]
    elif change == "no_cross_core":
        d["mask"][:, 1] = -60
    elif change == "complex":
        d["spec"] = d["spec"].astype(np.complex64)
    elif change == "nan":
        d["spec"][0, 1, 0, 0] = np.nan
    elif change == "empty":
        d["spec"], d["mask"] = d["spec"][:0], d["mask"][:0]
    with pytest.raises(ValueError):
        preprocess_dual(d["spec"], d["mask"])


@pytest.mark.parametrize("kwargs", [{"time_pool": 3}, {"time_pool": 0}, {"time_pool": True},
                                    {"view": "cross"}, {"level": "unknown"},
                                    {"level": "absolute"}, {"level": "absolute", "absolute_ref_db": np.inf}])
def test_invalid_dual_preprocessing_parameters(kwargs):
    d = _data(2)
    with pytest.raises(ValueError):
        preprocess_dual(d["spec"], d["mask"], **kwargs)


@pytest.mark.parametrize("mode,channels", [("dual", 4), ("co", 2)])
def test_dual_training_checkpoint_and_inference_roundtrip(mode, channels, tmp_path):
    torch = pytest.importorskip("torch")
    from geoml.train import TrainConfig, fit, infer, load, run, save

    train, validation = _data(), _data(4, 1)
    cfg = TrainConfig(labels=("clean", "cross_pol"), input_mode=mode, level="absolute",
                      width=2, epochs=1, batch=4, time_pool=1, augment=False)
    fitted = fit(train, validation, cfg, device="cpu", log=lambda _: None)
    assert fitted["model"].stem[0].in_channels == channels
    assert fitted["config"]["input_mode"] == mode
    assert fitted["absolute_ref_db"] == pytest.approx(reference_level(train["spec"][:, 0], train["mask"][:, 0]).mean())
    path = tmp_path / "model.pt"
    save(fitted, path)
    restored = load(path, device="cpu", expected_config=asdict(cfg))
    original, reloaded = infer(fitted, validation), infer(restored, validation)
    for key in original:
        np.testing.assert_array_equal(reloaded[key], original[key])
    assert reloaded["logits"].shape == (4, 2) and reloaded["embedding"].shape == (4, 32)
    np.testing.assert_allclose(run(restored, validation), torch.softmax(torch.from_numpy(reloaded["logits"]), dim=1).numpy(),
                               rtol=1e-6, atol=1e-7)
    with pytest.raises(ValueError, match="configuration"):
        load(path, expected_config=replace(cfg, input_mode="co" if mode == "dual" else "dual"))


def test_legacy_checkpoint_missing_input_mode_still_verifies_and_loads(tmp_path):
    torch = pytest.importorskip("torch")
    from geoml.artifacts import fingerprint
    from geoml.model import SmallResNet
    from geoml.train import TrainConfig, infer, load

    cfg = TrainConfig(labels=("clean", "cw"), width=2, time_pool=1, epochs=1)
    legacy_config = asdict(cfg)
    legacy_config.pop("input_mode")
    metadata = {"config": legacy_config, "provenance": None, "absolute_ref_db": -60.}
    artifact = {"state": SmallResNet(2, width=2).state_dict(), **metadata,
                "artifact_version": 1, "metadata_fingerprint": fingerprint(metadata)}
    path = tmp_path / "legacy.pt"
    torch.save(artifact, path)
    fitted = load(path, device="cpu", expected_config=cfg)
    dual = _data(2)
    single = {"spec": dual["spec"][:, 0], "mask": dual["mask"][:, 0]}
    assert infer(fitted, single)["logits"].shape == (2, 2)
    # The historical identity is checked before a missing mode is defaulted.
    artifact["config"]["input_mode"] = "co"
    torch.save(artifact, path)
    with pytest.raises(ValueError, match="metadata"):
        load(path)


def test_wrong_raw_observation_mode_is_rejected_before_training():
    pytest.importorskip("torch")
    from geoml.train import TrainConfig, fit

    d = _data(2)
    with pytest.raises(ValueError, match="training observations"):
        fit(d, d, TrainConfig(labels=("clean", "cross_pol"), width=2, epochs=1), device="cpu")
    single = {**d, "spec": d["spec"][:, 0], "mask": d["mask"][:, 0]}
    with pytest.raises(ValueError, match="dual/co"):
        fit(single, single, TrainConfig(labels=("clean", "cross_pol"), input_mode="dual", width=2, epochs=1), device="cpu")

"""Training/checkpoint interoperability and experiment artifact compatibility."""
from dataclasses import asdict, replace
import json

import numpy as np
import pytest

torch = pytest.importorskip("torch")

from geoml.artifacts import fingerprint
from geoml.pipeline import _binned_detection
from geoml.train import TrainConfig, fit, infer, load, predict, run, save


def _data(n=6, seed=0):
    rng = np.random.default_rng(seed)
    labels = np.arange(n, dtype=np.int64) % 2
    spec = (-80 + rng.normal(size=(n, 8, 32))).astype(np.float32)
    spec[:, :, 8:24] += 20
    spec[labels == 1, :, 2] += 25
    mask = np.full((n, 32), -60, np.float32)
    mask[:, 8:24] = 0
    return {"spec": spec, "mask": mask, "label": labels}


@pytest.fixture
def fitted():
    cfg = TrainConfig(labels=("clean", "cw"), width=2, time_pool=1, epochs=1, batch=4,
                      augment=False)
    result = fit(_data(), _data(4, 1), cfg, device="cpu", log=lambda _: None)
    result["provenance"] = {"protocol": "test", "train": "a", "validation": "b"}
    return result


def test_fit_checkpoint_inference_roundtrip(fitted, tmp_path):
    path = tmp_path / "model.pt"
    save(fitted, path)
    restored = load(path, device="cpu", expected_config=fitted["config"],
                    expected_provenance=fitted["provenance"])
    before = infer(fitted, _data(4, 2), batch=2)
    after = infer(restored, _data(4, 2), batch=2)
    assert before["logits"].shape == (4, 2)
    assert before["embedding"].shape == (4, 32)
    assert len(restored["history"]) == 1
    for key in before:
        np.testing.assert_array_equal(before[key], after[key])
    shifted = after["logits"] - after["logits"].max(axis=1, keepdims=True)
    probs = np.exp(shifted) / np.exp(shifted).sum(axis=1, keepdims=True)
    np.testing.assert_allclose(run(restored, _data(4, 2)), probs, rtol=1e-6, atol=1e-7)


def test_checkpoint_reuse_requires_matching_config_and_provenance(fitted, tmp_path):
    path = tmp_path / "model.pt"
    save(fitted, path)
    wrong = {**fitted["config"], "time_pool": 2}
    with pytest.raises(ValueError, match="configuration"):
        load(path, expected_config=wrong)
    with pytest.raises(ValueError, match="provenance"):
        load(path, expected_provenance={**fitted["provenance"], "train": "changed"})
    # JSON round-tripping converts the label tuple to a list, without changing identity.
    load(path, expected_config=json.loads(json.dumps(fitted["config"])))


def test_metadata_tampering_and_unidentified_legacy_reuse(fitted, tmp_path):
    path = tmp_path / "model.pt"
    save(fitted, path)
    checkpoint = torch.load(path, weights_only=True)
    checkpoint["config"]["time_pool"] = 2
    torch.save(checkpoint, path)
    with pytest.raises(ValueError, match="metadata"):
        load(path)
    checkpoint.pop("artifact_version")
    checkpoint.pop("metadata_fingerprint")
    checkpoint.pop("provenance")
    torch.save(checkpoint, path)
    assert load(path)["config"]["time_pool"] == 2
    with pytest.raises(ValueError, match="provenance"):
        load(path, expected_provenance=fitted["provenance"])


def test_empty_and_invalid_training_inputs_fail_before_training(fitted):
    cfg = TrainConfig(**fitted["config"])
    with pytest.raises(ValueError, match="nonempty"):
        fit(_data(0), _data(2), cfg)
    with pytest.raises(ValueError, match="at least one sample"):
        predict(fitted["model"], torch.empty(0, 2, 8, 32), "cpu")
    with pytest.raises(ValueError, match="batch"):
        infer(fitted, _data(2), batch=0)
    with pytest.raises(ValueError, match="divide"):
        infer({**fitted, "config": {**fitted["config"], "time_pool": 3}}, _data(2))
    bad = _data(2)
    bad["label"][0] = 2
    with pytest.raises(ValueError, match="out-of-range"):
        fit(bad, _data(2), cfg)
    bad = _data(2)
    bad["mask"][:] = -60
    with pytest.raises(ValueError, match="carrier core"):
        infer(fitted, bad)


@pytest.mark.parametrize("field,value", [("epochs", 0), ("batch", -1), ("width", True),
                                         ("lr", np.nan), ("time_pool", 0)])
def test_invalid_training_configuration(field, value):
    with pytest.raises(ValueError, match=field):
        replace(TrainConfig(labels=("clean", "cw")), **{field: value})


def test_empty_ci_bins_are_explicit_missing_measurements():
    hits = {"detector": [np.array([True, False, True])]}
    rates, counts = _binned_detection(hits, np.array([True, True, False]),
                                     np.array([6., 8., 24.]), [5, 15, 25, 35])
    assert counts == [2, 0, 0]
    assert rates == {"detector": [0.5, None, None]}
    encoded = json.dumps({"rates": rates, "counts": counts}, allow_nan=False)
    assert "null" in encoded and "NaN" not in encoded


def test_fingerprint_normalizes_json_representations():
    assert fingerprint({"labels": ("a", "b"), "epochs": 1}) == fingerprint(
        {"epochs": 1, "labels": ["a", "b"]})
    assert fingerprint({"epochs": 1}) != fingerprint({"epochs": 2})
    with pytest.raises(ValueError):
        fingerprint({"loss": np.inf})

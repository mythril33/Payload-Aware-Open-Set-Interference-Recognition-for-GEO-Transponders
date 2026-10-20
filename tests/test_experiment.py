"""Functional training, calibration, checkpoint reload and report integration."""
import json
from types import SimpleNamespace

import numpy as np
import pytest

pytest.importorskip("torch")

from geosim import dataset
from geoml import experiment
from geoml.calibration import RejectionCalibration
from geoml.experiment import ExperimentConfig, run_experiment


def test_small_experiment_trains_reloads_and_rejects_incompatible_reuse(tmp_path, monkeypatch):
    def fake_sample(label, bandwidth, seed, ranges, linear=False, amplifier="dvbs2_nl"):
        # Real on-disk contract and real model training, with cheap synthetic PSDs.
        rng = np.random.default_rng(seed + dataset.LABELS.index(label))
        spec = (-85 + rng.normal(size=(128, 512))).astype(np.float32)
        spec[:, 200:260] += 25
        spec[:, 30 + 20 * dataset.LABELS.index(label)] += 15
        mask = np.full(512, -60., np.float32)
        mask[200:260] = 0
        return SimpleNamespace(spec_db=spec, mask_db=mask,
                               meta={"label": label, "config": {"seed": seed, "bandwidth": bandwidth,
                                                              "linear": linear, "amplifier": amplifier}})

    monkeypatch.setattr(dataset, "sample", fake_sample)
    data, out = tmp_path / "data", tmp_path / "run"
    dataset.generate(str(data), list(experiment.SOURCE_SPLITS), limit_seeds=2)
    seen = []
    real_fit = experiment.fit

    def checked_fit(train, val, *args, **kwargs):
        seen.extend(meta["label"] for d in (train, val) for meta in d["meta"])
        return real_fit(train, val, *args, **kwargs)

    monkeypatch.setattr(experiment, "fit", checked_fit)
    cfg = ExperimentConfig(training={"epochs": 1, "width": 2, "batch": 8, "time_pool": 8, "augment": False})
    result = run_experiment(cfg, data, out, log=lambda _: None)
    assert cfg.holdout_label not in seen
    assert result["source_data_complete"] is False
    assert result["partitions"]["known_test"]["n_samples"] == 8
    assert result["partitions"]["unknown_test"]["n_samples"] == 2
    for method in ("msp", "energy"):
        calibration = RejectionCalibration.load(out / f"calibration_{method}.json")
        assert calibration.n_calibration == 4
        assert calibration.provenance
        assert result["methods"][method]["unknown_rejection"]["n_samples"] == 2
    source_hashes = result["source"]["files_sha256"]
    assert "geosim/data/dvbs2_twta.json" in source_hashes
    assert "geoml/model.py" in source_hashes
    predictions = json.loads((out / "predictions.json").read_text())
    assert len(predictions) == 10
    assert {row["true_family"] for row in predictions if row["role"] == "unknown_test"} == {cfg.holdout_label}
    assert all(row["methods"]["msp"]["prediction"] in (*result["known_labels"], "unknown") for row in predictions)
    original_checkpoint = (out / "model.pt").read_bytes()
    original_predictions = (out / "predictions.json").read_text()
    saved_config = ExperimentConfig.from_file(out / "config.json")
    repeated = run_experiment(saved_config, data, out, reuse=True, log=lambda _: None)
    assert repeated["experiment_fingerprint"] == result["experiment_fingerprint"]
    assert repeated["methods"] == result["methods"]
    assert (out / "model.pt").read_bytes() == original_checkpoint
    assert (out / "predictions.json").read_text() == original_predictions
    with pytest.raises(ValueError, match="already exists"):
        run_experiment(cfg, data, out, log=lambda _: None)
    changed = ExperimentConfig(holdout_label="cw", training=cfg.training)
    with pytest.raises(ValueError, match="config|provenance"):
        run_experiment(changed, data, out, reuse=True, log=lambda _: None)
    calibration_path = out / "calibration_energy.json"
    calibration = json.loads(calibration_path.read_text())
    calibration["threshold"] += 1
    calibration_path.write_text(json.dumps(calibration))
    with pytest.raises(ValueError, match="incompatible"):
        run_experiment(cfg, data, out, reuse=True, log=lambda _: None)
    # A valid artifact under the wrong role must fail before any training.
    (data / "train_nl").rename(data / "temporary")
    (data / "test_id_nl").rename(data / "train_nl")
    (data / "temporary").rename(data / "test_id_nl")
    with pytest.raises(ValueError, match="declares split"):
        run_experiment(cfg, data, tmp_path / "wrong_roles", log=lambda _: None)
    assert not (tmp_path / "wrong_roles").exists()


@pytest.mark.parametrize("change", [{"protocol": "B1"}, {"holdout_label": "clean"},
                                    {"target_acceptance": 0}, {"temperature": 0},
                                    {"calibration_fraction": 1}, {"training": {"labels": ["clean", "cw"]}}])
def test_rejects_invalid_experiment_contract(change):
    with pytest.raises(ValueError):
        ExperimentConfig(**change)

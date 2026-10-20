"""Matched-view training and independent clean-threshold calibration integration."""
import json

import numpy as np
import pytest

pytest.importorskip("torch")

from geoml import dual_experiment as ex


def _observations(groups):
    labels = np.tile(np.array([0, 1], np.int64), len(groups))
    seeds = np.repeat(groups, 2)
    rng = np.random.default_rng(int(groups[0]))
    spec = (-90 + rng.normal(size=(len(labels), 2, 128, 512))).astype(np.float16)
    mask = np.full((len(labels), 2, 512), -60., np.float16)
    mask[:, 0, 180:220] = 0
    mask[:, 1, 290:330] = 0
    spec[:, 0, :, 180:220] += 25
    spec[:, 1, :, 290:330] += 25
    spec[labels == 1, 0, :, 290:330] += 10
    return {"spec": spec, "mask": mask, "label": labels, "seed": seeds,
            "meta": [{"hidden_xpd_db": 10 if label else 30} for label in labels]}


@pytest.fixture
def sources():
    return {"train": _observations([100, 101]), "validation": _observations([200, 201, 202, 203]),
            "test": _observations([300, 301])}


def test_matched_views_reload_and_keep_selection_calibration_test_groups_separate(tmp_path, monkeypatch, sources):
    # Artifact corruption and physical generation have their own tests. This
    # integration runs real optimizer steps/checkpoints on small observed data.
    manifest = {"protocol": ex.PROTOCOL, "labels": ex.LABELS,
                "config": {"bandwidth": 36e6, "nominal_xpd_db": 30, "event_xpd_db": 10},
                "calibration": {"provenance": "independent-pilots"}}
    monkeypatch.setattr(ex, "read_dual_manifest", lambda _: manifest)
    monkeypatch.setattr(ex, "dual_fingerprint", lambda _: "validated-artifact-identity")
    monkeypatch.setattr(ex, "load_dual_split", lambda _, role: sources[role])
    calls, real_fit = [], ex.fit

    def checked_fit(train, val, cfg, **kwargs):
        calls.append((cfg.input_mode, set(train["seed"]), set(val["seed"])))
        return real_fit(train, val, cfg, **kwargs)

    monkeypatch.setattr(ex, "fit", checked_fit)
    config = ex.DualExperimentConfig(training={"epochs": 1, "width": 2, "batch": 4, "time_pool": 8, "augment": False})
    out = tmp_path / "run"
    result = ex.run_dual_experiment(config, tmp_path / "data", out, log=lambda _: None)
    assert {call[0] for call in calls} == {"co", "dual"}
    assert calls[0][1:] == calls[1][1:]
    summary = result["partitions"]
    assert set(summary["validation"]["scenario_ids"]).isdisjoint(summary["calibration"]["scenario_ids"])
    assert set(summary["test"]["scenario_ids"]) == {300, 301}
    assert all(call[2].isdisjoint({300, 301}) for call in calls)
    assert result["methods"]["co"]["input_channels"] == 2
    assert result["methods"]["dual"]["input_channels"] == 4
    for view in config.views:
        assert result["methods"][view]["detector"]["n_clean_calibration"] == 2
        assert result["methods"][view]["clean_false_alarm"]["n_samples"] == 2
        assert result["methods"][view]["cross_pol_detection"]["n_samples"] == 2
    predictions = (out / "predictions.json").read_bytes()
    restored = ex.DualExperimentConfig.from_file(out / "config.json")
    again = ex.run_dual_experiment(restored, tmp_path / "data", out, reuse=True, log=lambda _: None)
    assert len(calls) == 2
    assert again["methods"] == result["methods"]
    assert (out / "predictions.json").read_bytes() == predictions
    with pytest.raises(ValueError, match="already exists"):
        ex.run_dual_experiment(config, tmp_path / "data", out, log=lambda _: None)
    changed = ex.DualExperimentConfig(training={**config.training, "time_pool": 4})
    with pytest.raises(ValueError, match="configuration"):
        ex.run_dual_experiment(changed, tmp_path / "data", out, reuse=True, log=lambda _: None)
    detector_path = out / "detector_dual.json"
    detector = json.loads(detector_path.read_text())
    detector["threshold"] += 0.1
    detector_path.write_text(json.dumps(detector))
    with pytest.raises(ValueError, match="incompatible"):
        ex.run_dual_experiment(config, tmp_path / "data", out, reuse=True, log=lambda _: None)


def test_partition_rejects_group_leakage_and_insufficient_validation(sources):
    sources["test"]["seed"][:] = 100
    with pytest.raises(ValueError, match="leakage"):
        ex._partitions(sources, ex.DualExperimentConfig())
    sources["test"] = _observations([300])
    sources["validation"] = _observations([200])
    with pytest.raises(ValueError, match="at least two"):
        ex._partitions(sources, ex.DualExperimentConfig())


@pytest.mark.parametrize("change", [{"protocol": "A1"}, {"pfa": 0}, {"pfa": 1}, {"calibration_fraction": 1},
                                    {"views": []}, {"views": ["single"]}, {"views": ["co", "co"]},
                                    {"training": {"input_mode": "dual"}}, {"training": {"labels": ["secret"]}}])
def test_invalid_experiment_contract_fails(change):
    with pytest.raises(ValueError):
        ex.DualExperimentConfig(**change)


def test_detector_handles_extreme_logits_and_rejects_invalid_output():
    np.testing.assert_allclose(ex._cross_probability([[1000., -1000.], [-1000., 1000.], [0., 0.]]), [0, 1, 0.5])
    for logits in ([[np.nan, 0]], [[1., 2., 3.]], [], [["1", "2"]]):
        with pytest.raises(ValueError, match="logits"):
            ex._cross_probability(logits)

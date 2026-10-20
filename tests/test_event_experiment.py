"""Three-class matched models and clean-only event calibration."""
import json

import numpy as np
import pytest

pytest.importorskip("torch")
from geoml import dual_experiment as ex

LABELS = ("clean", "carrier_under_carrier", "adjacent_satellite")


def observations(groups):
    labels = np.tile(np.arange(3), len(groups))
    rng = np.random.default_rng(groups[0])
    spec = (-90 + rng.normal(size=(len(labels), 2, 128, 512))).astype(np.float16)
    mask = np.full((len(labels), 2, 512), -60, np.float16)
    mask[:, 0, 160:220] = 0
    mask[:, 1, 280:340] = 0
    spec[:, 0, :, 160:220] += 25
    spec[:, 1, :, 280:340] += 25
    spec[labels == 1, 0, :, 180:200] += 5
    spec[labels == 2, 0, :, 350:380] += 10
    return {"spec": spec, "mask": mask, "label": labels, "seed": np.repeat(groups, 3),
            "meta": [{"simulator_truth": int(label)} for label in labels]}


def test_three_class_real_training_calibration_reload_and_per_family_metrics(tmp_path, monkeypatch):
    sources = {"train": observations([100, 101]), "validation": observations([200, 201, 202, 203]),
               "test": observations([300, 301])}
    manifest = {"protocol": ex.EVENT_PROTOCOL, "labels": LABELS,
                "config": {"satellite_linewidth_hz": 100, "receiver_linewidth_hz": 50},
                "calibration": {"provenance": "independent-instrument-pilots"}}
    monkeypatch.setattr(ex, "_dataset_api", lambda _: (
        LABELS, lambda _: manifest, lambda _: "validated-events", lambda _, role: sources[role]))
    seen, real_fit = [], ex.fit

    def checked_fit(train, val, cfg, **kwargs):
        assert cfg.labels == LABELS
        seen.append((cfg.input_mode, set(val["seed"])))
        return real_fit(train, val, cfg, **kwargs)

    monkeypatch.setattr(ex, "fit", checked_fit)
    config = ex.DualExperimentConfig(protocol=ex.EVENT_PROTOCOL,
                                    training={"epochs": 1, "width": 2, "batch": 3, "time_pool": 8, "augment": False})
    out = tmp_path / "run"
    result = ex.run_dual_experiment(config, tmp_path / "data", out, log=lambda _: None)
    assert [item[0] for item in seen] == ["co", "dual"]
    assert seen[0][1] == seen[1][1]
    cal_groups = set(result["partitions"]["calibration"]["scenario_ids"])
    assert cal_groups.isdisjoint(seen[0][1])
    for view in config.views:
        method = result["methods"][view]
        assert np.shape(method["confusion"]) == (3, 3)
        assert method["detector"]["n_clean_calibration"] == 2
        assert method["detector"]["score"] == "one_minus_softmax_clean"
        assert method["pooled_event_detection"]["n_samples"] == 4
        assert set(method["event_detection"]) == set(LABELS[1:])
        assert all(value["n_samples"] == 2 for value in method["event_detection"].values())
    original = (out / "predictions.json").read_bytes()
    rows = json.loads(original)
    assert {row["true_label"] for row in rows} == set(LABELS)
    assert "event_probability" in rows[0]["views"]["co"]
    again = ex.run_dual_experiment(ex.DualExperimentConfig.from_file(out / "config.json"),
                                   tmp_path / "data", out, reuse=True, log=lambda _: None)
    assert len(seen) == 2
    assert again["methods"] == result["methods"]
    assert (out / "predictions.json").read_bytes() == original
    assert "closed-set development" in ex.report(result)


def test_event_score_sums_nonclean_probabilities_stably():
    np.testing.assert_allclose(ex._event_probability([[1000., -1000., -1000.],
                                                     [-1000., 1000., 1000.], [0, 0, 0]], 3), [0, 1, 2 / 3])
    with pytest.raises(ValueError, match="logits"):
        ex._event_probability([[1, 2]], 3)

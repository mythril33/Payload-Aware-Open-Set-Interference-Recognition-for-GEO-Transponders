"""Two-output runner integration with real optimization and frozen role use."""
from copy import deepcopy
import json

import numpy as np
import pytest

torch = pytest.importorskip("torch")
from geoml import b2_observed_experiment as ex
from geoml.b2_train import infer as infer_observations


def _observations(groups, role, *, missing_group=None):
    labels = np.tile(np.arange(len(ex.LABELS), dtype=np.int64), len(groups))
    seeds = np.repeat(groups, len(ex.LABELS)).astype(np.int64)
    auxiliary = (seeds == missing_group).astype(np.int64)
    rng = np.random.default_rng(int(groups[0]))
    spec = (-90 + rng.normal(size=(len(labels), 2, 128, 512))).astype(np.float16)
    mask = np.full((len(labels), 2, 512), -60, np.float16)
    mask[:, 0, 160:220] = 0
    mask[:, 1, 280:340] = 0
    spec[:, 0, :, 160:220] += 25
    spec[:, 1, :, 280:340] += 25
    spec[auxiliary == 1, 1, :, 280:340] -= 12
    # Different known-class observations exercise both input views; recognition
    # quality is deliberately not asserted from this optimizer smoke test.
    for label in range(1, len(ex.LABELS)):
        spec[labels == label, 0, :, 350 + 6 * label:354 + 6 * label] += 5
    residual = (spec[:, 0].astype(np.float32) - 8).astype(np.float16)
    return {"spec": spec, "mask": mask, "residual": residual, "label": labels,
            "seed": seeds, "plan_consistency": auxiliary, "role": role,
            "meta": [{"hidden_class": int(label), "hidden_missing": int(aux)}
                     for label, aux in zip(labels, auxiliary)]}


@pytest.fixture
def sources():
    return {
        "train": _observations([3_000_000, 3_000_008], "train", missing_group=3_000_008),
        "val-select": _observations([3_100_000], "val-select"),
        "val-calib": _observations([3_150_000], "val-calib"),
        "test": _observations([3_200_000], "test"),
    }


@pytest.fixture
def runner_data(monkeypatch, sources):
    manifest = {"protocol": ex.FEATURE_PROTOCOL, "labels": list(ex.LABELS),
                "config": {"satellite_linewidth_hz": 100, "receiver_linewidth_hz": 50},
                "calibration": {"provenance": "independent-observed-feature-pilots"},
                "receiver": {"algorithm": "observed-dd-rrc-fir/1"},
                "cancellation": {"algorithm": "observed-dd-rrc-fir/1",
                                 "receiver_fields": ["f0", "symbol_rate", "alpha", "mod", "code_rate"],
                                 "config": {}},
                "roles": {role: {"scenario_seeds": np.unique(data["seed"]).tolist(),
                                  "n_samples": len(data["label"]),
                                  "per_label": {name: int(np.sum(data["label"] == index))
                                                for index, name in enumerate(ex.LABELS)}}
                          for role, data in sources.items()}}
    monkeypatch.setattr(ex, "read_feature_manifest", lambda _: manifest)
    monkeypatch.setattr(ex, "feature_fingerprint", lambda _: "verified-feature-identity")
    monkeypatch.setattr(ex, "iter_feature_shards", lambda _, role: iter([sources[role]]))
    # Other agents may edit source during this test. Bind this controlled data
    # fixture to a fixed source snapshot rather than racing working-tree hashes.
    monkeypatch.setattr(ex, "_source_identity", lambda: {
        "revision": "controlled-test-source", "files_sha256": {"fixture.py": "fixed-hash"}})
    calls = {"fit": [], "infer": [], "threshold": []}
    real_fit, real_infer, real_threshold = ex.fit, ex.infer, ex.threshold_at_pfa

    def fit(train, validation, config, **kwargs):
        assert train[1] == "train" and validation[1] == "val-select"
        calls["fit"].append((config.view, set(sources[train[1]]["seed"]),
                             set(sources[validation[1]]["seed"])))
        return real_fit(sources[train[1]], sources[validation[1]], config, **kwargs)

    def infer(fitted, data, **kwargs):
        calls["infer"].append((fitted["config"]["view"], data[1]))
        return real_infer(fitted, sources[data[1]], **kwargs)

    def threshold(scores, pfa):
        calls["threshold"].append(np.asarray(scores).copy())
        return real_threshold(scores, pfa)

    monkeypatch.setattr(ex, "fit", fit)
    monkeypatch.setattr(ex, "infer", infer)
    monkeypatch.setattr(ex, "threshold_at_pfa", threshold)
    return manifest, calls


def test_matched_real_training_reload_calibration_and_empty_auxiliary_denominators(tmp_path, monkeypatch,
                                                                                  sources, runner_data):
    manifest, calls = runner_data
    config = ex.B2ExperimentConfig(training={"epochs": 1, "width": 2, "batch": 4,
                                           "time_pool": 8, "augment": False})
    out = tmp_path / "run"
    result = ex.run_b2_experiment(config, tmp_path / "data", out, log=lambda _: None)
    assert [call[0] for call in calls["fit"]] == ["dual", "b2"]
    assert calls["fit"][0][1:] == calls["fit"][1][1:]
    assert calls["fit"][0][1] == {3_000_000, 3_000_008}
    assert calls["fit"][0][2] == {3_100_000}
    assert calls["infer"] == [("dual", "val-calib"), ("dual", "test"),
                              ("b2", "val-calib"), ("b2", "test")]
    assert all(scores.shape == (1,) and np.isfinite(scores).all() for scores in calls["threshold"])
    assert result["partitions"]["train"]["plan_consistency_counts"] == {
        "consistent": 8, "planned_carrier_missing": 8}
    assert result["benchmark_complete"] is False and result["n_final_unknown_test_samples"] == 0
    assert result["config"]["training"]["center_weight"] == 0.01
    assert result["config"]["training"]["consistency_weight"] == 1.0
    assert result["feature_stage"]["cancellation"] == manifest["cancellation"]
    for view, channels in (("dual", 4), ("b2", 5)):
        method = result["methods"][view]
        assert method["input_channels"] == channels
        assert np.shape(method["classification"]["confusion"]) == (8, 8)
        assert sum(map(sum, method["classification"]["confusion"])) == 8
        assert method["classification"]["accuracy"]["ci95"] is None
        assert np.shape(method["plan_consistency"]["confusion"]) == (2, 2)
        assert method["plan_consistency"]["missing_recall"] == {
            "mean": None, "ci95": None, "n_samples": 0, "n_scenarios": 0}
        assert method["plan_consistency"]["false_missing_alarm"]["n_samples"] == 8
        assert method["event_detector"]["n_clean_calibration"] == 1
        assert method["clean_false_alarm"]["n_samples"] == 1
        assert set(method["event_detection"]) == set(ex.LABELS[1:])
        fitted = ex.load(out / f"model_{view}.pt", expected_config=config.train_config(view))
        assert fitted["model"].stem[0].in_channels == channels
        assert torch.count_nonzero(fitted["model"].class_centers) > 0
        expected = infer_observations(fitted, sources["test"])
        without_truth = {**sources["test"], "meta": object()}
        actual = infer_observations(fitted, without_truth)
        np.testing.assert_array_equal(actual["logits"], expected["logits"])
        np.testing.assert_array_equal(actual["consistency_logits"], expected["consistency_logits"])
    original = (out / "predictions.json").read_bytes()
    rows = json.loads(original)
    assert set(rows) == {"dual", "b2"}
    assert all({row["true_label"] for row in view_rows} == set(ex.LABELS) for view_rows in rows.values())
    assert "missing_probability" in rows["b2"][0]
    restored = ex.B2ExperimentConfig.from_file(out / "config.json")
    again = ex.run_b2_experiment(restored, tmp_path / "data", out, reuse=True, log=lambda _: None)
    assert len(calls["fit"]) == 2
    assert again["methods"] == result["methods"]
    assert (out / "predictions.json").read_bytes() == original
    report = ex.report(result)
    assert "Known classes only" in report
    assert "not measured (n=0)" in report
    assert "require recomputed receiver features" in report
    with pytest.raises(ValueError, match="already exists"):
        ex.run_b2_experiment(config, tmp_path / "data", out, log=lambda _: None)
    changed = ex.B2ExperimentConfig(training={**config.training, "center_weight": 0.02})
    with pytest.raises(ValueError, match="configuration"):
        ex.run_b2_experiment(changed, tmp_path / "data", out, reuse=True, log=lambda _: None)
    with monkeypatch.context() as context:
        context.setattr(ex, "feature_fingerprint", lambda _: "different-data-identity")
        with pytest.raises(ValueError, match="provenance"):
            ex.run_b2_experiment(config, tmp_path / "data", out, reuse=True, log=lambda _: None)
    detector_path = out / "detector_b2.json"
    detector = json.loads(detector_path.read_text())
    detector["threshold"] += 0.01
    detector_path.write_text(json.dumps(detector))
    with pytest.raises(ValueError, match="stored event detector"):
        ex.run_b2_experiment(config, tmp_path / "data", out, reuse=True, log=lambda _: None)


def test_partition_rejects_role_leakage_or_missing_role(runner_data):
    manifest, _ = runner_data
    bad = deepcopy(manifest)
    bad["roles"]["test"]["scenario_seeds"] = bad["roles"]["train"]["scenario_seeds"]
    with pytest.raises(ValueError, match="leakage"):
        ex._partitions("unused", bad)
    bad = deepcopy(manifest)
    del bad["roles"]["val-calib"]
    with pytest.raises(ValueError, match="requires"):
        ex._partitions("unused", bad)


def test_probability_extremes_and_unmeasured_rates_are_explicit():
    np.testing.assert_array_equal(ex._probabilities([[1000., -1000.], [-1000., 1000.]], 2),
                                  [[1, 0], [0, 1]])
    np.testing.assert_allclose(ex._probabilities([[0.] * 8], 8), np.full((1, 8), 1 / 8))
    assert ex._rate([], []) == {"mean": None, "ci95": None, "n_samples": 0, "n_scenarios": 0}
    assert ex._rate([1, 0], [5, 5])["ci95"] is None
    for logits in ([], [[1, 2, 3]], [[np.nan, 0]], [["1", "2"]]):
        with pytest.raises(ValueError, match="logits"):
            ex._probabilities(logits, 2)


@pytest.mark.parametrize("change", [{"protocol": "B2/1"}, {"pfa": 0}, {"pfa": 1},
                                    {"pfa": np.nan}, {"views": []}, {"views": ["b2", "b2"]},
                                    {"training": {"labels": ["hidden"]}}, {"training": {"view": "b2"}}])
def test_invalid_runner_configuration_fails(change):
    with pytest.raises(ValueError):
        ex.B2ExperimentConfig(**change)

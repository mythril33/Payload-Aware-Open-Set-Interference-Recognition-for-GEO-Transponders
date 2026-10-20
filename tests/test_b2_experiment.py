"""Frozen-role B2 learning slice: role integrity, known-only calibration, reuse and reports."""
import json

import numpy as np
import pytest

from geoml import b2_experiment as ex
from geoml.b2_experiment import B2ExperimentConfig, run_b2_experiment
from geosim.b2_protocol import LABELS, ROLE_STARTS


def _split(role, n_groups, seed, with_residual=True):
    rng = np.random.default_rng(seed)
    groups = np.repeat(np.arange(ROLE_STARTS[role], ROLE_STARTS[role] + n_groups), len(LABELS))
    labels = np.tile(np.arange(len(LABELS)), n_groups)
    n = len(labels)
    spec = rng.normal(-80, 2, (n, 2, 8, 32)).astype(np.float16)
    for index in range(len(LABELS)):
        spec[labels == index, 0, :, 4 + 3 * index] += 20
    mask = np.full((n, 2, 32), -60, np.float16)
    mask[:, :, 8:16] = 0
    data = {"spec": spec, "mask": mask, "label": labels.astype(np.int8), "seed": groups.astype(np.int64),
            "plan_consistency": (groups % 2).astype(np.int8), "meta": [{"scenario_id": int(g)} for g in groups]}
    if with_residual:
        data["residual"] = (spec[:, 0].astype(np.float32) - 12).astype(np.float16)
    return data


@pytest.fixture
def dataset(monkeypatch, tmp_path):
    splits = {role: _split(role, 2, index) for index, role in enumerate(ex.ROLES)}
    manifest = {"protocol": "B2-feat/1", "parent_protocol": "B2/1", "labels": list(LABELS), "benchmark_complete": False,
                "config": {"bandwidth": 36e6}, "cancellation": {"version": "obs-cancel/1"},
                "calibration": {"n_pilots": 64}}
    monkeypatch.setattr(ex, "read_b2_manifest", lambda path: manifest)
    monkeypatch.setattr(ex, "b2_fingerprint", lambda path: "f" * 64)
    monkeypatch.setattr(ex, "load_b2_split", lambda path, role: splits[role])
    monkeypatch.setattr(ex, "_source_identity", lambda: {"revision": "test", "files_sha256": {"x.py": "0" * 64}})
    return splits, manifest, tmp_path / "data"


def _config(**overrides):
    training = {"epochs": 1, "batch": 8, "width": 4, "seed": 0, "center_loss_weight": 0.005, "augment": False}
    return B2ExperimentConfig(**{"views": ("co", "dual_residual"), "training": training, **overrides})


def test_config_requires_frozen_center_loss_and_consistent_views():
    with pytest.raises(ValueError, match="center_loss_weight"):
        B2ExperimentConfig(training={"epochs": 1})
    with pytest.raises(ValueError, match="dual_residual"):
        B2ExperimentConfig(protocol="B2-base/1", views=("dual_residual",), training={"center_loss_weight": 0.0})
    with pytest.raises(ValueError):
        B2ExperimentConfig(methods=("knn",), training={"center_loss_weight": 0.0})
    with pytest.raises(ValueError, match="set by the experiment"):
        B2ExperimentConfig(training={"center_loss_weight": 0.0, "input_mode": "co"})
    resolved = _config().resolved()
    assert resolved["training"]["center_loss_weight"] == 0.005 and "labels" not in resolved["training"]


def test_run_reports_roles_rejection_plan_head_and_reuses_artifacts(dataset, tmp_path):
    _, _, data = dataset
    out = tmp_path / "run"
    config = _config()
    logs = []
    result = run_b2_experiment(config, data, out, log=logs.append)
    assert result["benchmark_complete"] is False and set(result["methods"]) == {"co", "dual_residual"}
    assert result["methods"]["dual_residual"]["input_channels"] == 5 and result["methods"]["co"]["input_channels"] == 2
    for view in config.views:
        values = result["methods"][view]
        assert set(values["rejection"]) == {"msp", "energy", "mahalanobis"}
        for metrics in values["rejection"].values():
            assert metrics["unknown_rejection"] is None and metrics["n_unknown"] == 0
            assert metrics["calibration"]["n_calibration"] == 16            # val-calib known samples only
        assert values["plan_consistency"]["positive_class"] == "planned_carrier_missing"
        assert values["plan_consistency"]["n_samples"] == 16
        assert values["open_set"]["unknown_auroc"] is None
        assert values["alarm"]["n_clean_calibration"] == 2
        assert sum(sum(row) for row in values["confusion"]) == 16
    assert result["partitions"]["train"]["scenario_ids"] == [3000000, 3000001]
    assert result["partitions"]["test"]["n_planned_carrier_missing"] == 8
    for name in ("results.json", "results.md", "predictions.json", "config.json", "model_co.pt",
                 "model_dual_residual.pt", "mahalanobis_co.npz", "rejection_dual_residual_mahalanobis.json"):
        assert (out / name).exists()
    rows = json.loads((out / "predictions.json").read_text())
    assert len(rows) == 16 and set(rows[0]["views"]["co"]["unknown_scores"]) == {"msp", "energy", "mahalanobis"}
    assert rows[0]["views"]["dual_residual"]["plan_logit"] is not None
    text = (out / "results.md").read_text()
    assert "null (n_unknown=0)" in text and "benchmark complete: **False**" in text
    with pytest.raises(ValueError, match="already exists"):
        run_b2_experiment(config, data, out, log=logs.append)
    again = run_b2_experiment(config, data, out, reuse=True, log=logs.append)
    assert again["methods"]["co"]["checkpoint_sha256"] == result["methods"]["co"]["checkpoint_sha256"]
    assert any("reusing compatible co checkpoint" in line for line in logs)
    with pytest.raises(ValueError, match="does not match"):
        run_b2_experiment(_config(training={**config.training, "seed": 1}), data, out, reuse=True, log=logs.append)


def test_role_leakage_and_out_of_range_groups_are_rejected(dataset, tmp_path):
    splits, _, data = dataset
    splits["val-calib"]["seed"][:] = splits["test"]["seed"][0]
    with pytest.raises(ValueError, match="outside its frozen|leakage"):
        run_b2_experiment(_config(), data, tmp_path / "leak", log=lambda *_: None)


def test_dataset_protocol_and_residual_requirements(dataset, tmp_path):
    splits, manifest, data = dataset
    with pytest.raises(ValueError, match="does not match"):
        run_b2_experiment(_config(protocol="B2-base/1", views=("co",)), data, tmp_path / "p", log=lambda *_: None)
    for split in splits.values():
        split.pop("residual")
    with pytest.raises(ValueError, match="stored residual"):
        run_b2_experiment(_config(), data, tmp_path / "r", log=lambda *_: None)


def test_plan_consistency_accuracy_is_null_when_one_class_is_absent():
    groups = np.repeat([3200000, 3200001], 4)
    logits = np.full((8, 1), -2.0)
    single = ex._plan_metrics(logits, np.zeros(8, np.int64), groups)
    assert single["accuracy"]["mean"] is None and single["n_positive"] == 0 and single["recall"] is None
    both = ex._plan_metrics(logits, np.array([0, 1] * 4), groups)
    assert both["accuracy"]["mean"] == 0.5 and both["recall"] == 0.0 and both["precision"] is None
    assert "undefined" in ex._plan_cell(single) and ex._plan_cell(both).startswith("50.0%")

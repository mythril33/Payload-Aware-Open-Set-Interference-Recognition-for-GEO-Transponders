"""Frozen-role B2 learning slice: role integrity, known-only calibration, reuse and reports."""
import json

import numpy as np
import pytest

from geoml import b2_experiment as ex
from geoml.b2_experiment import B2ExperimentConfig, run_b2_experiment
from geoml.b2_stream import B2Source
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
    # The runner opens artifacts through geoml.b2_stream; in-memory splits become single-shard sources
    # at call time, so tests may mutate the splits before running.
    monkeypatch.setattr(ex, "open_b2_known", lambda path: (
        manifest, "f" * 64, {role: B2Source.from_arrays(splits[role], role=role) for role in splits}))
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
        assert all(entry["unknown_auroc"] is None and entry["n_unknown"] == 0 for entry in values["open_set"].values())
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
    original = splits["val-calib"]["seed"].copy()
    # Test groups relabelled as val-calib: the source refuses groups outside the role's frozen range.
    splits["val-calib"]["seed"][:] = splits["test"]["seed"]
    with pytest.raises(ValueError, match="outside its frozen"):
        run_b2_experiment(_config(), data, tmp_path / "leak", log=lambda *_: None)
    # Two groups collapsed onto one id: duplicate (group, label) pairs are refused before anything else.
    splits["val-calib"]["seed"][:] = original[0]
    with pytest.raises(ValueError, match="duplicate scenario-group/label"):
        run_b2_experiment(_config(), data, tmp_path / "dup", log=lambda *_: None)
    # Same group id in two roles (no duplicates inside a role): the role cross-check catches the leakage.
    splits["val-calib"]["seed"][:] = original
    splits["val-select"]["seed"][:] = original
    with pytest.raises(ValueError, match="outside its frozen|leakage"):
        run_b2_experiment(_config(), data, tmp_path / "leak2", log=lambda *_: None)


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


# ---- test-only families (B2-test/1) ----

def _unknown_split(n_groups, seed):
    from geosim.b2_scenarios import TEST_FAMILIES
    rng = np.random.default_rng(seed)
    groups = np.repeat(np.arange(ROLE_STARTS["test"], ROLE_STARTS["test"] + n_groups), len(TEST_FAMILIES))
    family = np.tile(np.arange(len(TEST_FAMILIES)), n_groups)
    n = len(family)
    spec = rng.normal(-80, 2, (n, 2, 8, 32)).astype(np.float16)
    spec[:, 0, :, 30] += 40                                     # a signature no known class carries
    mask = np.full((n, 2, 32), -60, np.float16)
    mask[:, :, 8:16] = 0
    return {"spec": spec, "mask": mask, "family": family.astype(np.int8), "seed": groups.astype(np.int64),
            "plan_consistency": np.zeros(n, np.int8), "residual": (spec[:, 0].astype(np.float32) - 12).astype(np.float16),
            "meta": [{"scenario_id": int(g)} for g in groups], "families": list(TEST_FAMILIES)}


@pytest.fixture
def unknown_dataset(monkeypatch, dataset):
    _, manifest, data = dataset
    unknown = _unknown_split(2, 99)
    test_manifest = {"protocol": "B2-test/1", "config": manifest["config"], "cancellation": manifest["cancellation"],
                     "request": {"known": {"known_data_fingerprint": "f" * 64}}}
    monkeypatch.setattr(ex, "open_b2_test", lambda path: (
        test_manifest, "e" * 64, B2Source.from_arrays(unknown, kind="test", role="test")))
    return unknown, test_manifest, data


def test_test_only_families_are_scored_with_frozen_thresholds_and_reported_per_group(unknown_dataset, tmp_path):
    unknown, _, data = unknown_dataset
    result = run_b2_experiment(_config(views=("dual_residual",)), data, tmp_path / "os", log=lambda *_: None,
                               unknown_data=tmp_path / "unknown")
    assert result["test_only_protocol"] == "B2-test/1" and result["partitions"]["test_only"]["n_samples"] == 10
    values = result["methods"]["dual_residual"]
    for method, metrics in values["rejection"].items():
        families = metrics["families"]
        assert set(families) == set(unknown["families"])
        assert metrics["n_unknown"] == 6 and metrics["n_unknown_all_families"] == 8 and metrics["n_unknown_equivalence_limited"] == 2
        for name, entry in families.items():
            assert entry["n"] == 2 and entry["rejection_at_threshold"]["n_samples"] == 2
            if entry["pre_registered_group"] == "benign":
                assert name == "cid_overlay" and entry["expected_decision"] == "clean"
                assert {"clean_acceptance", "carrier_under_carrier_calls", "rejected_as_unknown"} <= set(entry)
            else:
                assert entry["ranking"]["n_known"] == 16 and entry["ranking"]["n_unknown"] == 2
                assert entry["ranking"]["conventions"]["positive_population"] == "unknown"
        pooled = metrics["pooled_near"]
        assert set(pooled["families"]) == {"pulsed", "intermittent_bursts", "adjacent_satellite_downlink"}
        assert pooled["ranking"]["n_unknown"] == 6
        assert metrics["unknown_rejection"] == pooled["rejection_at_threshold"]
        # The threshold is the val-calib one; its calibration count is unchanged by the unknown families.
        assert metrics["calibration"]["n_calibration"] == 16
    assert set(values["open_set"]) == {"msp", "energy", "mahalanobis"}
    assert values["open_set"]["msp"]["n_unknown"] == 6 and values["open_set"]["msp"]["n_unknown_all_families"] == 8
    assert values["open_set"]["msp"]["unknown_auroc"] is not None and values["open_set"]["msp"]["n_known"] == 16
    assert (tmp_path / "os" / "results_summary.json").exists()
    summary = json.loads((tmp_path / "os" / "results_summary.json").read_text())
    assert summary["experiment_fingerprint"] == result["experiment_fingerprint"]
    assert "curves" not in json.dumps(summary["methods"]) and summary["methods"]["dual_residual"]["rejection"]["msp"]["unknown_rejection"] is not None
    # The scorer parameter block is dropped, but every method's metrics survive the trimming.
    assert set(summary["methods"]["dual_residual"]["open_set"]) == {"msp", "energy", "mahalanobis"}
    assert set(summary["methods"]["dual_residual"]["rejection"]) == {"msp", "energy", "mahalanobis"}
    assert "mahalanobis_scorer" not in summary["methods"]["dual_residual"] and "mahalanobis_scorer" in result["methods"]["dual_residual"]
    assert set(values["test_only_alarm"]) == set(unknown["families"])
    text = (tmp_path / "os" / "results.md").read_text()
    assert "Test-only families (B2-test/1" in text and "pooled near" in text and "benign (expect clean)" in text
    assert "null (n_unknown=0)" not in text and "were supplied; their metrics are null" not in text and "event alarm" in text


def test_test_only_artifact_must_be_bound_to_the_same_known_data(unknown_dataset, tmp_path):
    unknown, test_manifest, data = unknown_dataset
    test_manifest["request"]["known"]["known_data_fingerprint"] = "0" * 64
    with pytest.raises(ValueError, match="different known dataset"):
        run_b2_experiment(_config(views=("co",)), data, tmp_path / "a", log=lambda *_: None, unknown_data="x")
    test_manifest["request"]["known"]["known_data_fingerprint"] = "f" * 64
    test_manifest["cancellation"] = {"version": "other"}
    with pytest.raises(ValueError, match="cancellation differ"):
        run_b2_experiment(_config(views=("co",)), data, tmp_path / "b", log=lambda *_: None, unknown_data="x")
    test_manifest["cancellation"] = {"version": "obs-cancel/1"}
    unknown["seed"] += 7                     # still test-role groups, but not the known test groups in use
    with pytest.raises(ValueError, match="known test groups"):
        run_b2_experiment(_config(views=("co",)), data, tmp_path / "c", log=lambda *_: None, unknown_data="x")


# ---- K17c matched set (B2-match/1) ----

def _matched_split(n_groups, seed):
    rng = np.random.default_rng(seed)
    label_index = [0, 6, 3]
    groups = np.repeat(np.arange(ROLE_STARTS["test-matched"], ROLE_STARTS["test-matched"] + n_groups), 3)
    labels = np.tile(np.array(label_index), n_groups)
    n = len(labels)
    spec = rng.normal(-80, 2, (n, 2, 8, 32)).astype(np.float16)
    spec[labels == 6, 0, :, 22] += 20
    spec[labels == 3, 0, :, 13] += 20
    mask = np.full((n, 2, 32), -60, np.float16)
    mask[:, :, 8:16] = 0
    bins = np.repeat(np.arange(n_groups) % 3, 3).astype(np.int8)
    meta = []
    for g, l, b in zip(groups, labels, bins):
        ci = [5.5, 8.5, 11.5][int(b)]
        meta.append({"scenario_id": int(g), "label": LABELS[int(l)],
                     "matched": {"pair_id": f"B2-match/1:{int(g)}", "target_c_over_i_psd_db": ci, "bin": int(b)},
                     "event": {"kind": LABELS[int(l)], "c_over_i_psd_db": ci} if l else {"kind": "clean"}})
    return {"spec": spec, "mask": mask, "label": labels.astype(np.int8), "seed": groups.astype(np.int64),
            "plan_consistency": np.zeros(n, np.int8), "matched_bin": bins,
            "residual": (spec[:, 0].astype(np.float32) - 12).astype(np.float16), "meta": meta,
            "labels": ["clean", "adjacent_satellite", "unauthorized"]}


@pytest.fixture
def matched_dataset(monkeypatch, dataset):
    _, manifest, data = dataset
    matched = _matched_split(4, 7)
    matched_manifest = {"protocol": "B2-match/1", "config": manifest["config"], "cancellation": manifest["cancellation"],
                        "request": {"known": {"known_data_fingerprint": "f" * 64}}}
    monkeypatch.setattr(ex, "open_b2_matched", lambda path: (
        matched_manifest, "d" * 64, B2Source.from_arrays(matched, kind="matched", role="test-matched")))
    return matched, matched_manifest, data


def test_matched_set_is_evaluated_with_frozen_thresholds_and_full_denominators(matched_dataset, tmp_path):
    matched, _, data = matched_dataset
    result = run_b2_experiment(_config(views=("dual_residual",)), data, tmp_path / "m", log=lambda *_: None,
                               matched_data=tmp_path / "matched")
    assert result["matched_protocol"] == "B2-match/1" and result["partitions"]["test_matched"]["n_samples"] == 12
    assert result["partitions"]["test_matched"]["per_label"] == {"clean": 4, "adjacent_satellite": 4, "unauthorized": 4}
    m = result["methods"]["dual_residual"]["matched"]
    assert m["n_samples"] == 12 and m["n_groups"] == 4 and m["per_bin_groups"] == {"4-7": 2, "7-10": 1, "10-13": 1}
    assert set(m["confusion"]) == {"clean", "unauthorized", "adjacent_satellite"}
    assert all(sum(row.values()) == 4 for row in m["confusion"].values())
    for method in ("msp", "energy", "mahalanobis"):
        by = m["by_method"][method]
        pair = by["pair"]
        assert pair["n_samples"] == 8 and pair["denominator"].startswith("all matched")
        bd = pair["prediction_breakdown"]
        for name in ("adjacent_satellite", "unauthorized"):
            assert bd[name]["predicted_clean"] + bd[name]["predicted_other_known"] + bd[name]["predicted_pair_class"] == 4
            assert bd[name]["n"] == 4
        assert sum(sum(r.values()) for r in pair["two_by_two"].values()) == sum(v["predicted_pair_class"] for v in bd.values())
        assert all(sum(row.values()) == 4 for row in by["confusion_with_rejection"].values())
        assert by["per_bin"]["4-7"]["n_samples"] == 4 and by["per_bin"]["10-13"]["n_samples"] == 2
        # Thresholds are the val-calib ones (16 known samples), untouched by the matched set.
        assert result["methods"]["dual_residual"]["rejection"][method]["calibration"]["n_calibration"] == 16
    assert m["per_class"]["adjacent_satellite"]["n_true"] == 4
    assert m["natural_comparison"]["classes"]["unauthorized"]["recall_overall"]["n_samples"] == 2
    assert m["natural_comparison"]["classes"]["unauthorized"]["recall_by_matched_bin"]["7-10"]["n_samples"] == 0
    reps = m["representatives"]
    assert reps["rule"].startswith("numpy default_rng([20261021])")
    assert len(reps["groups"]["4-7"]) == 2 and len(reps["groups"]["7-10"]) == 1
    assert "figures" in reps and (reps["figures"].get("written") is not None)
    text = (tmp_path / "m" / "results.md").read_text()
    assert "K17c level-matched" in text and "7-10" in text
    summary = json.loads((tmp_path / "m" / "results_summary.json").read_text())
    assert summary["methods"]["dual_residual"]["matched"]["by_method"]["msp"]["pair"]["pair_accuracy"] is not None


def test_matched_artifact_binding_and_role_are_enforced(matched_dataset, tmp_path):
    matched, matched_manifest, data = matched_dataset
    matched_manifest["request"]["known"]["known_data_fingerprint"] = "0" * 64
    with pytest.raises(ValueError, match="different known dataset"):
        run_b2_experiment(_config(views=("co",)), data, tmp_path / "a", log=lambda *_: None, matched_data="x")
    matched_manifest["request"]["known"]["known_data_fingerprint"] = "f" * 64
    matched["seed"][:3] = ROLE_STARTS["test"]
    with pytest.raises(ValueError, match="test-matched role"):
        run_b2_experiment(_config(views=("co",)), data, tmp_path / "b", log=lambda *_: None, matched_data="x")


def test_pair_metrics_count_clean_other_and_rejected_predictions_explicitly():
    asi, un, cuc = LABELS.index("adjacent_satellite"), LABELS.index("unauthorized"), LABELS.index("carrier_under_carrier")
    labels = np.array([asi, asi, asi, un, un, un, 0, 0])
    predictions = np.array([asi, un, 0, un, cuc, asi, 0, 0])
    accepted = np.array([True, True, True, False, True, True, True, True])
    groups = np.array([1, 2, 3, 1, 2, 3, 1, 2])
    pair = ex._pair_metrics(predictions, accepted, labels, groups, labels != 0)
    assert pair["n_samples"] == 6 and pair["two_by_two"] == {"adjacent_satellite": {"adjacent_satellite": 1, "unauthorized": 1},
                                                             "unauthorized": {"adjacent_satellite": 1, "unauthorized": 1}}
    bd = pair["prediction_breakdown"]
    assert bd["adjacent_satellite"] == {"predicted_clean": 1, "predicted_other_known": 0, "predicted_pair_class": 2, "rejected_as_unknown": 0, "n": 3}
    assert bd["unauthorized"] == {"predicted_clean": 0, "predicted_other_known": 1, "predicted_pair_class": 2, "rejected_as_unknown": 1, "n": 3}
    assert pair["pair_accuracy"]["mean"] == pytest.approx(2 / 6)                 # threshold-free argmax
    assert pair["pair_accuracy_among_pair_predictions"]["mean"] == pytest.approx(2 / 4)
    assert pair["pair_accuracy_accepted_only"]["mean"] == pytest.approx(1 / 5)   # the correct unauthorized was rejected
    assert pair["rejected_fraction"]["mean"] == pytest.approx(1 / 6)
    empty = ex._pair_metrics(predictions, accepted, labels, groups, np.zeros(8, bool))
    assert empty["pair_accuracy"] is None and empty["pair_accuracy_accepted_only"] is None and empty["rejected_fraction"] is None


def test_natural_comparison_bins_follow_the_frozen_edges(matched_dataset, tmp_path, dataset):
    splits, _, data = dataset
    test_meta = splits["test"]["meta"]
    labels = splits["test"]["label"]
    # Attach natural C/I_psd values to the ASI and unauthorized test samples: 7.0 belongs to 7-10, 13.0 to 10-13, 6.99 to 4-7.
    values = iter([7.0, 13.0])
    unauth_values = iter([6.99, 15.0])
    for record, label in zip(test_meta, labels):
        if LABELS[int(label)] == "adjacent_satellite":
            record["event"] = {"kind": "adjacent_satellite", "c_over_i_psd_db": next(values)}
        elif LABELS[int(label)] == "unauthorized":
            record["event"] = {"kind": "unauthorized", "c_over_i_psd_db": next(unauth_values)}
    result = run_b2_experiment(_config(views=("co",)), data, tmp_path / "n", log=lambda *_: None, matched_data="x")
    natural = result["methods"]["co"]["matched"]["natural_comparison"]["classes"]
    asi = natural["adjacent_satellite"]["recall_by_matched_bin"]
    assert asi["7-10"]["n_samples"] == 1 and asi["10-13"]["n_samples"] == 1 and asi["4-7"]["n_samples"] == 0
    un = natural["unauthorized"]["recall_by_matched_bin"]
    assert un["4-7"]["n_samples"] == 1 and un["7-10"]["n_samples"] == 0 and un["10-13"]["n_samples"] == 0   # 15 dB is outside every bin
    assert natural["unauthorized"]["recall_overall"]["n_samples"] == 2

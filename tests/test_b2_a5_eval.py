"""E4 frozen-model paired A5 evaluation: pairing, conditions, caps, metrics, strict JSON, reuse.

Fast tests on real B2-feat/1 / B2-match/1 artifacts with deterministic stand-in physics (see
``b2_a5_support``). They prove data flow and arithmetic, not recognition quality.
"""
import json

import numpy as np
import pytest

import b2_a5_support as support
from geoml import b2_a5 as a5
from geoml import b2_a5_replay as rp
from geoml.b2_stream import open_b2_known
from geosim.b2_protocol import LABELS


@pytest.fixture(autouse=True)
def fakes(monkeypatch):
    support.install_fakes(monkeypatch)


def _config(**overrides):
    base = {"perturbation": "drop_one", "scope": "co_only", "stage": "known", "n_groups": 2,
            "labels": ("clean", "unauthorized"), "views": ("co", "dual_residual")}
    return a5.A5Config(**{**base, **overrides})


def _strict(path):
    def refuse(constant):
        raise AssertionError(f"non-finite JSON constant {constant}")
    return json.loads(path.read_text(), parse_constant=refuse)


def _run(tmp_path, config=None, name="out", **kwargs):
    ws = support.workspace()
    return a5.run_a5(config or _config(), ws / "known", ws / "runs", tmp_path / name, log=lambda *_: None, **kwargs)


def test_config_enforces_the_bounded_smoke_caps():
    assert a5.CAPS == {"max_groups": 2, "max_classes": 2, "max_configurations": 1, "max_replays": 16, "max_cancellations": 24}
    with pytest.raises(ValueError, match="n_groups"):
        _config(n_groups=3)
    with pytest.raises(ValueError, match="n_groups"):
        _config(n_groups=0)
    with pytest.raises(ValueError, match="labels"):
        _config(labels=("clean", "cw", "swept_cw"))
    with pytest.raises(ValueError, match="labels"):
        _config(labels=("clean", "clean"))
    with pytest.raises(ValueError, match="labels"):
        _config(labels=("clean", "adjacent"))
    with pytest.raises(ValueError, match="perturbation"):
        _config(perturbation="everything")
    with pytest.raises(ValueError, match="scope"):
        _config(scope="all")
    with pytest.raises(ValueError, match="views"):
        _config(views=("co", "co"))
    assert _config().plan_budget() == {"replays": 4, "cancellations": 8}
    assert _config(scope="cross_only").plan_budget() == {"replays": 4, "cancellations": 4}
    assert _config(perturbation="none").plan_budget() == {"replays": 4, "cancellations": 4}


def test_no_unrestricted_mode_exists_and_caps_trip_before_work(monkeypatch):
    monkeypatch.setitem(a5.CAPS, "max_replays", 3)
    with pytest.raises(rp.BudgetExceeded, match="exceed the caps"):
        _config()
    monkeypatch.setitem(a5.CAPS, "max_replays", 16)
    monkeypatch.setitem(a5.CAPS, "max_cancellations", 5)
    with pytest.raises(rp.BudgetExceeded):
        _config()
    assert set(a5.A5Config.__dataclass_fields__) == {"perturbation", "scope", "stage", "n_groups", "labels", "views"}


def test_cli_exposes_no_way_to_lift_a_cap(capsys):
    with pytest.raises(SystemExit):
        a5.main(["--help"])
    text = capsys.readouterr().out
    assert "--config" in text and "--data" in text
    assert not any(word in text for word in ("unrestricted", "--no-cap", "--full", "--train", "--generate", "--n-groups"))


def test_config_file_rejects_unknown_fields(tmp_path):
    path = tmp_path / "c.json"
    path.write_text(json.dumps({"perturbation": "none", "scope": "both", "production": True}))
    with pytest.raises(ValueError, match="fields only"):
        a5.A5Config.from_file(path)


def test_end_to_end_conditions_pairing_counts_and_strict_json(tmp_path):
    result = _run(tmp_path)
    saved = _strict(tmp_path / "out" / "results.json")
    assert saved == result
    assert result["contract"] == "B2-A5-eval/1" and result["plan_contract"] == "B2-A5-plan/1"
    assert result["benchmark_complete"] is False and result["evidence_class"] == "BOUNDED_PILOT"
    assert result["authorization"]["full_b2_production"] == "NOT_AUTHORIZED_NOT_STARTED"
    assert result["counts"]["physical_replays"] == 4 and result["counts"]["cancellation_evaluations"] == 8
    assert result["counts"]["receiver_recomputations"] == 4 and result["counts"]["scenes_applicable"] == 4
    assert result["parity_summary"]["all_exact"] is True and result["parity_summary"]["n_scenes_checked"] == 4
    assert [(s["scenario_id"], s["label"]) for s in result["scenes"]] == [
        (3200000, "clean"), (3200000, "unauthorized"), (3200001, "clean"), (3200001, "unauthorized")]
    for view in ("co", "dual_residual"):
        entry = result["views"][view]
        assert set(entry["conditions"]) == {"original", "MASK_ONLY", "RECEIVER_CONSISTENT"}
        for name, metrics in entry["conditions"].items():
            assert metrics["n_scenes"] == 4 and metrics["n_groups"] == 2
            assert sum(map(sum, metrics["confusion_original_label"])) == 4
            assert sum(map(sum, metrics["transition_matrix"])) == 4
            assert "accuracy" not in metrics                              # counterfactuals are agreement, not accuracy
            assert metrics["clean_false_alarm"]["n_samples"] == 2 and metrics["event_detection"]["n_samples"] == 2
        original = entry["conditions"]["original"]
        assert original["prediction_change_vs_original"] is None and original["max_abs_logit_difference_vs_original"] is None
        assert entry["original_selected_population"]["accuracy"]["n_samples"] == 4        # accuracy only on stored arrays
    assert result["views"]["co"]["mask_only_vs_receiver_consistent"]["logits_identical"] is True
    assert result["views"]["co"]["mask_only_vs_receiver_consistent"]["view_reads_residual"] is False
    consistent = result["views"]["dual_residual"]["mask_only_vs_receiver_consistent"]
    assert consistent["view_reads_residual"] is True and consistent["residual_identical"] is False
    assert consistent["logits_identical"] is False
    assert (tmp_path / "out" / "results.json.sha256").exists() and (tmp_path / "out" / "results.md").exists()
    assert "agreement with the original label" in (tmp_path / "out" / "results.md").read_text().lower()


def test_residual_diagnostics_compare_the_same_bins_and_move_only_for_receiver_consistent(tmp_path):
    result = _run(tmp_path)
    conditions = result["views"]["dual_residual"]["conditions"]
    assert conditions["original"]["residual"]["spec_co_total_db"]["n_samples"] == 4
    for name in ("MASK_ONLY", "RECEIVER_CONSISTENT"):
        shift = conditions[name]["residual_displacement_vs_original"]
        assert shift["spec_co_total_db"]["mean"] == 0.0                          # the physical PSD never moves
    assert conditions["MASK_ONLY"]["residual_displacement_vs_original"]["residual_total_db"]["mean"] == 0.0
    assert conditions["RECEIVER_CONSISTENT"]["residual_displacement_vs_original"]["residual_total_db"]["mean"] != 0.0
    assert "cancellation_depth_core_db" in conditions["original"]["residual"]


def test_cross_only_never_recomputes_the_residual(tmp_path):
    result = _run(tmp_path, _config(scope="cross_only"))
    assert result["counts"]["receiver_recomputations"] == 0 and result["counts"]["cancellation_evaluations"] == 4
    assert all(s["residual_recomputed"] is False and s["cross_changed"] and not s["co_changed"] for s in result["scenes"])
    for view in ("co", "dual_residual"):
        assert result["views"][view]["mask_only_vs_receiver_consistent"]["logits_identical"] is True
        shift = result["views"][view]["conditions"]["RECEIVER_CONSISTENT"]["residual_displacement_vs_original"]
        assert shift["residual_total_db"]["mean"] == 0.0


def test_none_condition_reproduces_the_original_exactly(tmp_path):
    result = _run(tmp_path, _config(perturbation="none", scope="both"))
    assert result["counts"]["receiver_recomputations"] == 0
    for view in ("co", "dual_residual"):
        for name in ("MASK_ONLY", "RECEIVER_CONSISTENT"):
            metrics = result["views"][view]["conditions"][name]
            assert metrics["prediction_change_vs_original"]["mean"] == 0.0
            assert metrics["max_abs_logit_difference_vs_original"] < 1e-4


def test_not_applicable_scenes_are_counted_and_excluded_from_the_paired_population(tmp_path):
    result = _run(tmp_path, _config(perturbation="authorize_intruder", scope="co_only"))
    reason = "authorize_intruder applies to unauthorized scenes only (frozen A5 definition)"
    assert result["populations"] == {"selected": 4, "applied": 2, "not_applicable": {reason: 2}, "blocked": {}}
    assert result["counts"]["physical_replays"] == 2 and result["counts"]["scenes_applicable"] == 2
    for view in ("co", "dual_residual"):
        paired = result["views"][view]["conditions"]["original"]
        assert paired["n_scenes"] == 2 and paired["clean_false_alarm"]["mean"] is None      # no clean scene in the paired set
        assert paired["clean_false_alarm"]["n_samples"] == 0
        assert result["views"][view]["original_selected_population"]["n_scenes"] == 4


def test_empty_paired_population_gives_null_rates_with_counts_and_no_replay(tmp_path):
    result = _run(tmp_path, _config(perturbation="authorize_intruder", labels=("clean",)))
    assert result["counts"]["physical_replays"] == 0 and result["counts"]["cancellation_evaluations"] == 0
    for view in ("co", "dual_residual"):
        assert result["views"][view]["conditions"] is None and result["views"][view]["paired_population"] == {"n_scenes": 0}
    assert result["parity_summary"] == {"n_scenes_checked": 0, "all_exact": None, "max_abs_diff_db": None}
    _strict(tmp_path / "out" / "results.json")


def test_single_group_intervals_are_null_not_nan(tmp_path):
    result = _run(tmp_path, _config(n_groups=1))
    metrics = result["views"]["co"]["conditions"]["MASK_ONLY"]
    assert metrics["n_groups"] == 1 and metrics["agreement_with_original_label"]["ci95"] is None
    assert metrics["agreement_with_original_label"]["mean"] is not None
    two = _run(tmp_path, _config(n_groups=2), name="two")
    assert two["views"]["co"]["conditions"]["MASK_ONLY"]["agreement_with_original_label"]["ci95"] is not None


def test_missing_view_is_reported_unavailable_and_nothing_is_trained(tmp_path):
    ws = support.workspace()
    result = _run(tmp_path, _config(views=("co", "dual")))
    assert result["views"]["dual"] == {"available": False, "reason": "no frozen checkpoint model_dual.pt in the run directory (nothing is trained here)"}
    assert result["frozen_models"]["dual"]["available"] is False
    assert not (ws / "runs" / "model_dual.pt").exists()


def test_stage_matched_replays_the_matched_artifact(tmp_path):
    ws = support.workspace()
    config = _config(stage="matched", perturbation="authorize_intruder", scope="both", labels=("adjacent_satellite", "unauthorized"))
    result = a5.run_a5(config, ws / "known", ws / "runs", tmp_path / "m", matched_data=ws / "matched", log=lambda *_: None)
    assert result["source"]["stage"] == "matched" and result["source"]["role"] == "test-matched"
    assert result["source"]["matched_data_fingerprint"] and result["populations"]["applied"] == 2
    assert result["parity_summary"]["all_exact"] is True
    with pytest.raises(ValueError, match="matched stage"):
        a5.run_a5(config, ws / "known", ws / "runs", tmp_path / "m2", log=lambda *_: None)
    with pytest.raises(ValueError, match="matched stage"):
        a5.run_a5(_config(), ws / "known", ws / "runs", tmp_path / "m3", matched_data=ws / "matched", log=lambda *_: None)


def test_pair_denominators_keep_clean_other_and_rejected_predictions():
    labels = np.array([LABELS.index("adjacent_satellite")] * 2 + [LABELS.index("unauthorized")] * 2)
    predictions = np.array([LABELS.index("clean"), LABELS.index("unauthorized"), LABELS.index("cw"), LABELS.index("unauthorized")])
    accepted = np.array([True, True, False, True])
    from geoml.b2_experiment import _pair_metrics
    pair = _pair_metrics(predictions, accepted, labels, np.array([1, 1, 2, 2]), labels != 0)
    assert pair["n_samples"] == 4
    assert pair["prediction_breakdown"]["adjacent_satellite"] == {"predicted_clean": 1, "predicted_other_known": 0,
                                                                 "predicted_pair_class": 1, "rejected_as_unknown": 0, "n": 2}
    assert pair["prediction_breakdown"]["unauthorized"]["rejected_as_unknown"] == 1
    assert pair["pair_accuracy"]["mean"] == 0.25 and pair["two_by_two"]["adjacent_satellite"]["unauthorized"] == 1


def test_score_direction_and_binary_multiclass_are_not_conflated(tmp_path):
    result = _run(tmp_path)
    metrics = result["views"]["co"]["conditions"]["RECEIVER_CONSISTENT"]
    assert set(metrics["score_displacement"]) == {"msp", "energy", "mahalanobis"}       # larger = more unknown-like
    assert "oscr" not in json.dumps(result["views"]).lower() and "auroc" not in json.dumps(result["views"]).lower()
    assert result["baselines"]["status"] == "INPUTS_RECOMPUTED_NO_MODEL"
    assert "never compared" in result["baselines"]["note"] and "no baseline decision" in result["baselines"]["note"]
    assert len(metrics["confusion_original_label"]) == 8 and len(metrics["confusion_original_label"][0]) == 8


def test_reuse_is_verified_deterministic_and_refuses_stale_or_incomplete_output(tmp_path):
    first = _run(tmp_path)
    logs = []
    ws = support.workspace()
    again = a5.run_a5(_config(), ws / "known", ws / "runs", tmp_path / "out", log=logs.append)
    assert again == first and any("reusing verified A5 result" in line for line in logs)
    fresh = _run(tmp_path, name="fresh")
    drop = lambda r: {k: v for k, v in r.items() if k not in ("cost", "reproduction_command")}
    assert drop(fresh) == drop(first)                                                  # same identities, same result
    assert fresh["experiment_fingerprint"] == first["experiment_fingerprint"]
    with pytest.raises(ValueError, match="different experiment identity"):
        a5.run_a5(_config(perturbation="shift_plus"), ws / "known", ws / "runs", tmp_path / "out", log=lambda *_: None)
    (tmp_path / "out" / "results.json").write_text((tmp_path / "out" / "results.json").read_text().replace("BOUNDED", "BOUNDEX"))
    with pytest.raises(ValueError, match="incomplete or modified"):
        a5.run_a5(_config(), ws / "known", ws / "runs", tmp_path / "out", log=lambda *_: None)
    (tmp_path / "partial").mkdir()
    (tmp_path / "partial" / "results.json.tmp").write_text("{}")
    with pytest.raises(ValueError, match="incomplete derived output"):
        a5.run_a5(_config(), ws / "known", ws / "runs", tmp_path / "partial", log=lambda *_: None)
    (tmp_path / "orphan").mkdir()
    (tmp_path / "orphan" / "results.json").write_text("{}")
    with pytest.raises(ValueError, match="incomplete or modified"):
        a5.run_a5(_config(), ws / "known", ws / "runs", tmp_path / "orphan", log=lambda *_: None)


def test_frozen_run_files_are_not_modified_by_an_evaluation(tmp_path):
    ws = support.workspace()
    snapshot = {p.name: p.read_bytes() for p in sorted((ws / "runs").iterdir()) if p.is_file()}
    _run(tmp_path, _config(perturbation="phantom", scope="both"))
    assert snapshot == {p.name: p.read_bytes() for p in sorted((ws / "runs").iterdir()) if p.is_file()}
    assert not list((ws / "runs").glob("*.tmp"))


def test_thresholds_come_from_known_val_calib_only_and_nothing_is_fitted(tmp_path, monkeypatch):
    import geoml.b2_stream as stream
    calls = {"threshold": [], "fit": 0}
    real_threshold = a5.threshold_at_pfa

    def threshold(scores, pfa):
        calls["threshold"].append(len(scores))
        return real_threshold(scores, pfa)

    monkeypatch.setattr(a5, "threshold_at_pfa", threshold)
    monkeypatch.setattr(stream, "fit_streaming", lambda *a, **k: calls.__setitem__("fit", calls["fit"] + 1))
    import geoml.mahalanobis as mah
    monkeypatch.setattr(mah, "fit_mahalanobis", lambda *a, **k: calls.__setitem__("fit", calls["fit"] + 1))
    result = _run(tmp_path)
    assert calls["fit"] == 0
    assert calls["threshold"] == [2, 2]            # one per view; the two clean val-calib scenes of the known artifact
    thresholds = {v: result["frozen_models"][v]["alarm_threshold"] for v in ("co", "dual_residual")}
    reported = json.loads((support.workspace() / "runs" / "results.json").read_text())["methods"]
    assert all(thresholds[v] == pytest.approx(reported[v]["alarm"]["threshold"], abs=1e-9) for v in thresholds)


def test_evaluation_scenes_are_test_role_groups_disjoint_from_training_roles(tmp_path):
    from geosim.b2_protocol import role_for_group
    ws = support.workspace()
    _, _, sources = open_b2_known(ws / "known")
    result = _run(tmp_path)
    groups = {s["scenario_id"] for s in result["scenes"]}
    assert {role_for_group(g) for g in groups} == {"test"} and result["source"]["role"] == "test"
    for role in ("train", "val-select", "val-calib"):
        assert not groups & set(sources[role].groups.tolist())


def test_cli_reports_errors_without_traceback(tmp_path, capsys):
    ws = support.workspace()
    config = tmp_path / "c.json"
    config.write_text(json.dumps({"perturbation": "drop_one", "scope": "co_only", "n_groups": 9}))
    with pytest.raises(SystemExit) as exit_info:
        a5.main(["--config", str(config), "--data", str(ws / "known"), "--runs", str(ws / "runs"), "--out", str(tmp_path / "x")])
    assert exit_info.value.code == 2 and "n_groups" in capsys.readouterr().err
    config.write_text(json.dumps({"perturbation": "drop_one", "scope": "co_only", "n_groups": 1, "labels": ["clean"]}))
    a5.main(["--config", str(config), "--data", str(ws / "known"), "--runs", str(ws / "runs"), "--out", str(tmp_path / "ok"),
             "--perturbation", "shift_plus", "--scope", "both"])
    saved = _strict(tmp_path / "ok" / "results.json")
    assert saved["configuration"]["perturbation"] == "shift_plus" and saved["configuration"]["scope"] == "both"
    assert "python -m geoml.b2_a5" in saved["reproduction_command"]


def test_baseline_inputs_are_recomputed_from_the_counterfactual_streams_without_any_model(tmp_path):
    co = _run(tmp_path, _config(scope="co_only"))["baselines"]["methods"]
    cross = _run(tmp_path, _config(scope="cross_only"), name="cross")["baselines"]["methods"]
    for methods in (co, cross):
        assert set(methods) == {"edsc_score_db", "ca_cfar_planned", "ca_cfar_blind", "xgboost_features_26"}
        assert all(entry["available"] and entry["reads"] for entry in methods.values())
        blind = methods["ca_cfar_blind"]["displacement_vs_original"]
        for condition in ("MASK_ONLY", "RECEIVER_CONSISTENT"):                       # the blind detector ignores the plan
            assert all(column["n_scenes_changed"] == 0 for column in blind[condition].values())
    # co_only: the co mask moves the EDSC reference/core and the planned CFAR; only the recomputed residual moves EDSC under RECEIVER_CONSISTENT
    edsc = co["edsc_score_db"]["displacement_vs_original"]
    assert edsc["RECEIVER_CONSISTENT"]["n_scenes_changed"] == 4                  # recomputed residual AND rebuilt mask
    assert 1 <= edsc["MASK_ONLY"]["n_scenes_changed"] <= edsc["RECEIVER_CONSISTENT"]["n_scenes_changed"]   # mask alone moves the core reference
    # cross_only: nothing the co-pol statistics read changes; XGBoost sees the cross mask through cross_core_fraction
    assert cross["edsc_score_db"]["displacement_vs_original"]["RECEIVER_CONSISTENT"]["n_scenes_changed"] == 0
    assert cross["ca_cfar_planned"]["displacement_vs_original"]["RECEIVER_CONSISTENT"]["time_averaged_cell_db"]["n_scenes_changed"] == 0
    features = cross["xgboost_features_26"]["displacement_vs_original"]["RECEIVER_CONSISTENT"]
    assert features["n_features"] == 26 and features["n_features_changed"] >= 1 and features["mean_abs_by_feature"]["cross_core_fraction"] > 0
    assert features["mean_abs_by_feature"]["co_core_fraction"] == 0.0 and features["mean_abs_by_feature"]["residual_band_level_db"] == 0.0

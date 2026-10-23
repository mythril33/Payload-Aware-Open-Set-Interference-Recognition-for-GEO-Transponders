"""E4 negative and adversarial matrix (P28): leakage, artifact and checkpoint security, statistics.

Deliberately corrupted fixtures, not only well-formed ones. Uses the deterministic stand-in physics of
``b2_a5_support``; the real-physics invariants are in ``test_b2_a5_replay.py``.
"""
import json
import shutil
from pathlib import Path

import numpy as np
import pytest
import torch

import b2_a5_support as support
from geoml import b2_a5 as a5
from geoml import b2_a5_replay as rp
from geoml.b2_a5_plan import corrupt_operator_plan, validate_belief
from geoml.train import load, save
from geosim import b2_dataset as ds
from geosim.cancellation import CancellationConfig
from geosim.polarization import fit_receiver_calibration
from geosim.waveform import Carrier

GATES = Path(__file__).parent.parent / "docs" / "plan" / "b2_readiness_gates_2026-10-21.json"


@pytest.fixture(autouse=True)
def fakes(monkeypatch):
    support.install_fakes(monkeypatch)


def _config(**overrides):
    base = {"perturbation": "drop_one", "scope": "co_only", "n_groups": 1, "labels": ("clean", "unauthorized"),
            "views": ("co", "dual_residual")}
    return a5.A5Config(**{**base, **overrides})


def _run(known, runs, tmp_path, config=None, name="out"):
    return a5.run_a5(config or _config(), known, runs, tmp_path / name, log=lambda *_: None)


def _flip_byte(path):
    data = bytearray(Path(path).read_bytes())
    data[len(data) // 2] ^= 0xFF
    Path(path).write_bytes(bytes(data))


# ------------------------------------------------------------------ A. physical integrity


def test_replay_metadata_and_physical_configuration_never_change_with_the_belief(tmp_path):
    ws = support.workspace()
    source = rp.open_replay_source(ws / "known", "known", "test")
    replay = rp.replay_scene(source, "unauthorized", source.groups[0])
    before = json.dumps(replay.record, sort_keys=True)
    stored = source.stored(replay.group, "unauthorized")
    for perturbation in ("shift_plus", "drop_one", "phantom", "authorize_intruder", "stale_plan"):
        context = replay.intervention_context() if perturbation == "authorize_intruder" else None
        corruption = corrupt_operator_plan(replay.plans, perturbation=perturbation, scope="both", scenario_id=replay.group,
                                           allowed_intervention_context=context)
        assert corruption.applied
        rp.build_conditions(replay, stored, corruption, rp.FrozenReceiver(source.cancellation))
    assert json.dumps(replay.record, sort_keys=True) == before
    config = replay.record["config"]
    assert config["uplink_xpd_db"] == 30.0 and config["downlink_xpd_db"] == 35.0                             # RF coupling fixed
    assert json.dumps(replay.record["paths"], sort_keys=True) == json.dumps(json.loads(before)["paths"], sort_keys=True)  # TWTA loading fixed
    assert replay.active_carriers == tuple(tuple(m) for m in replay.record["active_carriers"])


# ------------------------------------------------------------------ B. plan and receiver integrity


def test_empty_or_unsupported_beliefs_never_silently_succeed(tmp_path, monkeypatch):
    from geosim.cancellation import cancel_planned_carriers as real_canceller
    monkeypatch.setattr(rp, "cancel_planned_carriers", real_canceller)       # the frozen validator, not the stand-in
    ws = support.workspace()
    source = rp.open_replay_source(ws / "known", "known", "test")
    with pytest.raises(ValueError):
        validate_belief(())
    receiver = rp.FrozenReceiver(source.cancellation)
    with pytest.raises(rp.ReplayError, match="rejected the operator belief"):
        receiver.residual_db(np.zeros((128, 4096), np.complex64), [])
    with pytest.raises(ValueError, match="obs-cancel/1"):
        CancellationConfig(version="obs-cancel/2")
    with pytest.raises(rp.ReplayError):
        rp.FrozenReceiver(None)


# ------------------------------------------------------------------ C. data leakage


def test_model_outputs_ignore_labels_groups_and_targets_and_only_accept_observed_inputs():
    ws = support.workspace()
    manifest, identity, sources = a5.open_b2_known(ws / "known")
    experiment = a5.B2ExperimentConfig.from_file(ws / "runs" / "config.json")
    frozen = a5.load_frozen_views(ws / "runs", experiment, identity, sources, ("dual_residual",), lambda *_: None)["views"]["dual_residual"]
    shard = next(iter(sources["test"].shards()))
    observed = rp.ObservedInputs(shard["spec"], shard["mask"], shard["residual"])
    keys = a5.EvalKeys(shard["label"].astype(np.int64), shard["seed"].astype(np.int64), shard["plan_consistency"].astype(np.int64))
    scrambled = a5.EvalKeys(keys.label[::-1].copy(), keys.group, 1 - keys.plan_consistency)
    first = a5.score_observed(frozen, observed, keys, "known")
    second = a5.score_observed(frozen, observed, scrambled, "known")
    for key in ("logits", "prediction", "alarm", "event_probability", "plan_logit"):
        assert np.array_equal(first[key], second[key])
    for method in first["scores"]:
        assert np.array_equal(first["scores"][method], second["scores"][method])
    with pytest.raises(ValueError, match="ObservedInputs only"):
        a5.score_observed(frozen, {"spec": shard["spec"], "mask": shard["mask"], "residual": shard["residual"]}, keys, "known")
    assert set(rp.ObservedInputs.__dataclass_fields__) == {"spec", "mask", "residual"}


def test_observed_inputs_reject_bad_shapes_dtypes_and_nonfinite_values():
    good = dict(spec=np.zeros((1, 2, 128, 512), np.float16), mask=np.zeros((1, 2, 512), np.float16),
                residual=np.zeros((1, 128, 512), np.float16))
    rp.ObservedInputs(**good)
    for key, bad in (("spec", np.zeros((1, 2, 128, 512), np.float32)), ("mask", np.zeros((1, 2, 511), np.float16)),
                     ("residual", np.full((1, 128, 512), np.nan, np.float16)), ("spec", np.zeros((0, 2, 128, 512), np.float16))):
        with pytest.raises(ValueError):
            rp.ObservedInputs(**{**good, key: bad})


def test_the_canceller_never_receives_truth_only_iq_belief_and_config(monkeypatch):
    ws = support.workspace()
    source = rp.open_replay_source(ws / "known", "known", "test")
    seen = []
    monkeypatch.setattr(rp, "cancel_planned_carriers", lambda iq, plan, config=None: seen.append((iq, plan, config)) or support.fake_cancel(iq, plan, config))
    replay = rp.replay_scene(source, "clean", source.groups[0])
    corruption = corrupt_operator_plan(replay.plans, perturbation="shift_plus", scope="co_only", scenario_id=replay.group)
    rp.build_conditions(replay, source.stored(replay.group, "clean"), corruption, rp.FrozenReceiver(source.cancellation))
    assert len(seen) == 1 and set(map(type, seen[0])) == {np.ndarray, list, CancellationConfig}
    assert seen[0][0].shape == (128, 4096) and all(isinstance(c, Carrier) for c in seen[0][1])


# ------------------------------------------------------------------ D. artifact and checkpoint security


def test_corrupted_source_checksums_fail_closed(tmp_path):
    ws = support.workspace()
    known = support.copy_of("known", tmp_path)
    source = rp.open_replay_source(known, "known", "test")
    _flip_byte(known / "test" / "part-00000.npz")
    with pytest.raises(rp.ReplayError, match="could not be verified"):
        source.stored(source.groups[0], "clean")
    with pytest.raises(ValueError, match="invalid B2 base dataset"):
        _run(known, ws / "runs", tmp_path)
    meta_copy = support.copy_of("known", tmp_path / "meta")
    path = meta_copy / "test" / "meta-00000.jsonl"
    path.write_text(path.read_text().replace('"scenario_id": 3200000', '"scenario_id": 3200009', 1))
    with pytest.raises(rp.ReplayError, match="could not be verified"):
        rp.open_replay_source(meta_copy, "known", "test").stored(3200000, "clean")


def test_wrong_artifact_stage_fails_closed(tmp_path):
    ws = support.workspace()
    base = tmp_path / "base"
    ds.generate_b2_dataset(base, roles=("test",), limit_groups=1, groups_per_shard=1)
    with pytest.raises(rp.ReplayError, match="B2-feat/1 stage"):
        rp.open_replay_source(base, "known", "test")
    with pytest.raises(rp.ReplayError, match="stage must be one of"):
        rp.open_replay_source(ws / "known", "test-only", "test")
    with pytest.raises(rp.ReplayError, match="was not generated"):
        rp.open_replay_source(ws / "known", "known", "val-select" if False else "test-matched")
    with pytest.raises(rp.ReplayError):
        rp.open_replay_source(ws / "known", "matched", "test")           # a known artifact is not a matched artifact


def test_wrong_receiver_calibration_fails_closed(tmp_path):
    known = support.copy_of("known", tmp_path)
    rng = np.random.default_rng(5)
    reference = (rng.standard_normal((2, 64)) + 1j * rng.standard_normal((2, 64))) / np.sqrt(2)
    other = fit_receiver_calibration(reference, np.array([[1.3, 0.1], [0.0, 0.9]]) @ reference, provenance="other")
    other.save(known / "receiver_calibration.npz")
    with pytest.raises(rp.ReplayError, match="calibration"):
        rp.open_replay_source(known, "known", "test")
    descriptor = json.loads((known / "calibration.json").read_text())
    from geosim.dataset import _file_hash
    descriptor["sha256"] = _file_hash(known / "receiver_calibration.npz")
    descriptor["metadata"] = other.to_dict()
    (known / "calibration.json").write_text(json.dumps(descriptor))
    with pytest.raises(rp.ReplayError, match="calibration"):
        rp.open_replay_source(known, "known", "test")


def test_wrong_cancellation_version_or_settings_fail_closed(tmp_path):
    for edit in ({"version": "obs-cancel/2"}, {"iterations": 4}):
        known = support.copy_of("known", tmp_path / f"c{len(edit)}{list(edit)[0]}")
        for name in ("request.json", "manifest.json"):
            data = json.loads((known / name).read_text())
            target = data["cancellation"] if name == "request.json" else data["cancellation"]
            target.update(edit)
            if name == "manifest.json":
                data["request"]["cancellation"].update(edit)
            (known / name).write_text(json.dumps(data))
        with pytest.raises(rp.ReplayError):
            rp.open_replay_source(known, "known", "test")


def test_generator_source_drift_fails_closed(monkeypatch):
    ws = support.workspace()
    monkeypatch.setattr(ds, "_generator_provenance", lambda: {"unit_fixture": "1" * 64})
    with pytest.raises(rp.ReplayError, match="simulator source has changed"):
        rp.open_replay_source(ws / "known", "known", "test")


def test_source_rule_allows_only_declared_e4_additions():
    trained = {"geoml/a.py": "1" * 64, "geosim/b.py": "2" * 64}
    ok = a5.check_source_rule(trained, {**trained, "geoml/b2_a5.py": "3" * 64})
    assert ok["added_since_training"] == ["geoml/b2_a5.py"] and ok["modified"] == []
    for current, word in (({**trained, "geoml/a.py": "9" * 64}, "modified"), ({"geoml/a.py": "1" * 64}, "removed"),
                          ({**trained, "geoml/other.py": "3" * 64}, "unexpected additions")):
        with pytest.raises(rp.ReplayError, match=word):
            a5.check_source_rule(trained, current)


def _load_and_resave(runs, view, edit):
    fitted = load(runs / f"model_{view}.pt", device="cpu")
    edit(fitted)
    save(fitted, runs / f"model_{view}.pt")


def test_incompatible_checkpoint_provenance_fails_closed(tmp_path):
    ws = support.workspace()
    runs = support.copy_of("runs", tmp_path)
    _load_and_resave(runs, "co", lambda f: f["provenance"].update(data_fingerprint="0" * 64))
    with pytest.raises(rp.ReplayError, match="provenance does not match"):
        _run(ws / "known", runs, tmp_path, _config(views=("co",)))
    runs2 = support.copy_of("runs", tmp_path / "second")
    _load_and_resave(runs2, "co", lambda f: f["provenance"]["roles"].update(test=[1, 2]))
    with pytest.raises(rp.ReplayError, match="provenance does not match"):
        _run(ws / "known", runs2, tmp_path, _config(views=("co",)))
    runs3 = support.copy_of("runs", tmp_path / "third")
    _load_and_resave(runs3, "co", lambda f: f["provenance"]["source_files_sha256"].update({"geoml/metrics.py": "0" * 64}))
    with pytest.raises(rp.ReplayError, match="source identity differs"):
        _run(ws / "known", runs3, tmp_path, _config(views=("co",)))


def test_tampered_or_swapped_frozen_state_fails_closed(tmp_path):
    ws = support.workspace()
    runs = support.copy_of("runs", tmp_path / "bytes")
    torch_state = torch.load(runs / "model_co.pt", weights_only=True)
    torch_state["absolute_ref_db"] += 1.0                       # metadata no longer matches its fingerprint
    torch.save(torch_state, runs / "model_co.pt")
    with pytest.raises(ValueError, match="metadata is invalid"):
        _run(ws / "known", runs, tmp_path, _config(views=("co",)))
    swapped = support.copy_of("runs", tmp_path / "scorer")
    shutil.copy(swapped / "mahalanobis_co.npz", swapped / "mahalanobis_dual_residual.npz")
    with pytest.raises(rp.ReplayError, match="Mahalanobis scorer is not bound"):
        _run(ws / "known", swapped, tmp_path, _config(views=("dual_residual",), ))
    calibration = support.copy_of("runs", tmp_path / "rejection")
    shutil.copy(calibration / "rejection_co_msp.json", calibration / "rejection_dual_residual_msp.json")
    with pytest.raises(rp.ReplayError, match="rejection calibration is not bound"):
        _run(ws / "known", calibration, tmp_path, _config(views=("dual_residual",)))
    threshold = support.copy_of("runs", tmp_path / "threshold")
    reported = json.loads((threshold / "results.json").read_text())
    reported["methods"]["co"]["alarm"]["threshold"] += 0.01
    (threshold / "results.json").write_text(json.dumps(reported))
    with pytest.raises(rp.ReplayError, match="alarm threshold or checkpoint hash differs"):
        _run(ws / "known", threshold, tmp_path, _config(views=("co",)))
    other_data = support.copy_of("runs", tmp_path / "data")
    reported = json.loads((other_data / "results.json").read_text())
    reported["data_fingerprint"] = "0" * 64
    (other_data / "results.json").write_text(json.dumps(reported))
    with pytest.raises(rp.ReplayError, match="different known dataset"):
        _run(ws / "known", other_data, tmp_path, _config(views=("co",)))
    missing = support.copy_of("runs", tmp_path / "missing")
    (missing / "config.json").unlink()
    with pytest.raises(FileNotFoundError):
        _run(ws / "known", missing, tmp_path, _config(views=("co",)))


def test_matched_artifact_must_be_bound_to_the_same_known_data(tmp_path):
    ws = support.workspace()
    matched = support.copy_of("matched", tmp_path)
    for name in ("request.json", "manifest.json"):
        data = json.loads((matched / name).read_text())
        (data["request"] if name == "manifest.json" else data)["known"]["known_data_fingerprint"] = "0" * 64
        (matched / name).write_text(json.dumps(data))
    config = _config(stage="matched", perturbation="authorize_intruder", labels=("unauthorized",))
    with pytest.raises(ValueError):
        a5.run_a5(config, ws / "known", ws / "runs", tmp_path / "x", matched_data=matched, log=lambda *_: None)


# ------------------------------------------------------------------ E. statistical correctness and gates


def test_paired_metrics_are_computed_on_aligned_rows():
    keys = a5.EvalKeys(np.array([0, 0, 3, 3]), np.array([1, 1, 2, 2]), np.zeros(4, np.int64))
    flat = np.zeros((4, 8))
    base_logits = flat.copy()
    base_logits[np.arange(4), [0, 0, 3, 3]] = 5
    changed = flat.copy()
    changed[np.arange(4), [3, 0, 0, 3]] = 5                       # scenes 0 and 2 change class
    output = lambda logits: {"logits": logits, "prediction": logits.argmax(1),
                             "scores": {"msp": 1 - np.exp(logits - logits.max(1, keepdims=True)).max(1) / np.exp(logits - logits.max(1, keepdims=True)).sum(1)},
                             "accepted": {"msp": np.ones(4, bool)}, "event_probability": np.linspace(0, 1, 4),
                             "alarm": np.array([True, False, False, True]), "plan_logit": None}
    original, condition = output(base_logits), output(changed)
    metrics = a5._view_metrics(keys, condition, original, a5._residual_diagnostics(
        [rp.SceneObservation(np.zeros((2, 128, 512), np.float16), np.zeros((2, 512), np.float16), np.zeros((128, 512), np.float16))] * 4,
        np.ones((4, 512), bool)))
    assert metrics["prediction_change_vs_original"]["mean"] == 0.5 and metrics["prediction_change_vs_original"]["n_scenarios"] == 2
    assert metrics["transition_matrix"][0][3] == 1 and metrics["transition_matrix"][3][0] == 1
    assert metrics["transition_matrix"][0][0] == 1 and metrics["transition_matrix"][3][3] == 1
    assert metrics["confusion_original_label"][0][3] == 1 and metrics["agreement_with_original_label"]["mean"] == 0.5
    assert metrics["clean_false_alarm"]["n_samples"] == 2 and metrics["event_detection"]["n_samples"] == 2
    assert metrics["clean_false_alarm"]["mean"] == 0.5                  # scene 0 of the two clean scenes alarms
    assert metrics["plan_consistency"] is None and metrics["asi_vs_unauthorized"] is None


def test_unknown_score_direction_is_larger_means_more_unknown_like():
    from geoml.openset import unknown_scores
    peaked, flat = np.array([[9.0, 0, 0, 0]]), np.array([[1.0, 1, 1, 1]])
    for method in ("msp", "energy"):
        assert unknown_scores(flat, method)[0] > unknown_scores(peaked, method)[0]


def test_results_contain_no_nan_and_no_unknown_family_metrics(tmp_path):
    ws = support.workspace()
    result = _run(ws / "known", ws / "runs", tmp_path, _config(perturbation="phantom", scope="both"))
    text = json.dumps(result, allow_nan=False)
    assert "NaN" not in text and "Infinity" not in text
    assert result["benchmark_complete"] is False and all("NOT_AUTHORIZED" in v or "PENDING" in v for v in result["authorization"].values())


def test_a_pilot_never_changes_the_readiness_gates():
    gates = json.loads(GATES.read_text())
    assert gates["benchmark_complete"] is False
    for key in ("K18", "K17d", "OBS-CANCEL-2"):
        assert gates["decisions"][key]["status"] == "PENDING_RESEARCHER" and gates["decisions"][key]["approval"] is None
    for key in ("full_generation", "full_gpu_training", "full_loko_sweep"):
        assert gates["decisions"][key]["status"] == "NOT_AUTHORIZED"

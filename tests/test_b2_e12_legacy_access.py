"""D7 boundary tests: synthetic descriptors/arrays only; no RF, fitting or inference."""
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from geoml import b2_experiment as ex
from geoml.b2_stream import B2Source
from geosim import b2_dataset as known_ds, b2_test_dataset as test_ds, b2_matched_dataset as matched_ds
from geosim.b2_protocol import LABELS, ROLE_STARTS


@pytest.fixture
def cfg():
    return ex.B2ExperimentConfig(views=("co",), methods=("msp",), plan_consistency=False,
        training={"epochs": 1, "batch": 8, "width": 4, "seed": 0, "center_loss_weight": 0.005})


@pytest.fixture
def headers(monkeypatch):
    known = {"roles": {r: {"n_scenarios": 2, "scenario_seeds": [ROLE_STARTS[r], ROLE_STARTS[r] + 1]}
                       for r in ex.ROLES}}
    unknown = {"role": "test", "scenario_seeds": [3200000, 3200001]}
    matched = {"role": "test-matched", "scenario_seeds": [3300000, 3300001]}
    calls = []
    def header(kind, value, path):
        calls.append((kind, str(path)))
        return value, None
    monkeypatch.setattr(known_ds, "_header", lambda p: header("known", known, p))
    monkeypatch.setattr(test_ds, "_header", lambda p: header("unknown", unknown, p))
    monkeypatch.setattr(matched_ds, "_header", lambda p: header("matched", matched, p))
    return known, unknown, matched, calls


@pytest.fixture
def no_observation_read(monkeypatch):
    for name in ("open_b2_known", "open_b2_test", "open_b2_matched", "fit_streaming", "infer_streaming"):
        monkeypatch.setattr(ex, name, lambda *a, _name=name, **k: pytest.fail(f"unexpected {_name}"))


@pytest.mark.parametrize("intent", [False, None, 1, "true", np.bool_(True)])
@pytest.mark.parametrize("extra", [{}, {"unknown_data": "u"}, {"matched_data": "m"},
                                  {"unknown_data": "known-alias", "matched_data": "known-alias"}])
def test_api_default_and_nonboolean_intent_fail_before_any_header_or_observation(
        cfg, headers, no_observation_read, tmp_path, intent, extra):
    with pytest.raises(ValueError, match="denied by default"):
        ex.run_b2_experiment(cfg, "known", tmp_path / "never", allow_test_read=intent, **extra)
    assert headers[3] == [] and not (tmp_path / "never").exists()


@pytest.mark.parametrize("device", ["cuda", "cuda:0", "gpu", None])
def test_explicit_historical_intent_cannot_authorize_gpu(cfg, headers, no_observation_read, tmp_path, device):
    with pytest.raises(ValueError, match="CPU-only"):
        ex.run_b2_experiment(cfg, "known", tmp_path / "never", allow_test_read=True, device=device)
    assert headers[3] == []


@pytest.mark.parametrize("kind", ["known", "unknown", "matched", "wrong-role", "missing-role", "cap"])
def test_metadata_admission_rejects_unexposed_roles_before_all_observation_readers(
        cfg, headers, no_observation_read, tmp_path, kind):
    known, unknown, matched, calls = headers
    if kind == "known": known["roles"]["test"]["scenario_seeds"] = [3200002]
    if kind == "unknown": unknown["scenario_seeds"] = [3200002]
    if kind == "matched": matched["scenario_seeds"] = [3300002]
    if kind == "wrong-role": matched["role"] = "train"
    if kind == "missing-role": known["roles"].pop("test")
    if kind == "cap": known["roles"]["train"]["n_scenarios"] = 13
    with pytest.raises(ValueError, match="historical|pilot"):
        ex.run_b2_experiment(cfg, "known", tmp_path / "never", allow_test_read=True,
                             unknown_data="unknown", matched_data="matched")
    assert calls and not (tmp_path / "never").exists()


@pytest.mark.parametrize("role", ["train-only", "calibrate", "freeze", "evaluate"])
def test_historical_flag_is_rejected_for_isolated_modes(role, tmp_path, no_observation_read):
    arguments = {"train-only": ["--config", "c", "--data", "d", "--out", "o"],
                 "calibrate": ["--data", "d", "--runs", "r"],
                 "freeze": ["--bundle", "b", "--out", "o"],
                 "evaluate": ["--data", "d", "--inventory", "i", "--out", "o"]}
    with pytest.raises(SystemExit) as error:
        ex.main(["--mode", role, *arguments[role], "--allow-test-read"])
    assert error.value.code == 2


@pytest.mark.parametrize("extra", [[], ["--unknown-data", "known-alias"], ["--matched-data", "known-alias"]])
def test_default_cli_refuses_even_if_dispatcher_is_replaced(monkeypatch, headers, extra):
    monkeypatch.setattr(ex, "run_b2_experiment", lambda *a, **k: pytest.fail("default legacy dispatched"))
    with pytest.raises(SystemExit) as error:
        ex.main(["--config", "unused", "--data", "known", "--out", "never", *extra])
    assert error.value.code == 2 and headers[3] == []


@pytest.mark.parametrize("training", [{"epochs": 30}, {"width": 16}, {"batch": 33}])
def test_historical_flag_cannot_launch_production_sized_fit(cfg, headers, no_observation_read, tmp_path, training):
    config = ex.B2ExperimentConfig(views=("co",), training={**cfg.training, **training})
    with pytest.raises(ValueError, match="historical.*CPU budget"):
        ex.run_b2_experiment(config, "known", tmp_path / "never", allow_test_read=True)
    assert not (tmp_path / "never").exists()


def test_bound_artifact_path_aliases_cannot_disguise_an_unexposed_manifest(
        cfg, headers, no_observation_read, monkeypatch, tmp_path):
    target = tmp_path / "future"
    target.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(target, target_is_directory=True)
    def header(path):
        assert path.resolve() == target
        return {"roles": {r: {"n_scenarios": 1, "scenario_seeds": [3200002] if r == "test" else [ROLE_STARTS[r]]}
                          for r in ex.ROLES}}, None
    monkeypatch.setattr(known_ds, "_header", header)
    for path in (target, alias):
        with pytest.raises(ValueError, match="already exposed"):
            ex.run_b2_experiment(cfg, path, tmp_path / "never", allow_test_read=True)


@pytest.mark.parametrize("kind", ["unknown_data", "matched_data"])
def test_explicit_flag_does_not_allow_known_artifact_alias_as_other_stage(
        cfg, headers, no_observation_read, monkeypatch, tmp_path, kind):
    module = test_ds if kind == "unknown_data" else matched_ds
    monkeypatch.setattr(module, "_header", lambda p: (headers[0], None))
    with pytest.raises(ValueError, match="invalid legacy pilot artifact"):
        ex.run_b2_experiment(cfg, "known", tmp_path / "never", allow_test_read=True,
                             **{kind: "known-alias"})


def test_explicit_historical_synthetic_flow_has_provenance_but_no_execution_authority(
        cfg, headers, monkeypatch, tmp_path):
    # Every fit, checkpoint and inference operation is a stand-in. The only
    # arrays are fabricated in memory; no waveform, external data or real model.
    sources = {}
    for role in ex.ROLES:
        groups = np.repeat([ROLE_STARTS[role], ROLE_STARTS[role] + 1], len(LABELS))
        labels = np.tile(np.arange(len(LABELS)), 2).astype(np.int8)
        arrays = {"seed": groups, "label": labels, "plan_consistency": np.zeros(16, np.int8),
                  "spec": np.full((16, 2, 8, 32), -80, np.float16),
                  "mask": np.zeros((16, 2, 32), np.float16),
                  "residual": np.full((16, 8, 32), -90, np.float16),
                  "meta": [{"scenario_id": int(g)} for g in groups]}
        sources[role] = B2Source.from_arrays(arrays, role=role)
    manifest = {"protocol": "B2-feat/1", "parent_protocol": "B2/1", "benchmark_complete": False,
                "labels": list(LABELS), "config": {}, "calibration": {}, "cancellation": {}}
    monkeypatch.setattr(ex, "open_b2_known", lambda p: (manifest, "a" * 64, sources))
    monkeypatch.setattr(ex, "_source_identity", lambda: {"revision": "synthetic", "files_sha256": {}})
    fitted = {"n_parameters": 0, "history": []}
    fit_roles = []
    monkeypatch.setattr(ex, "fit_streaming", lambda train, select, *a, **k:
                        (fit_roles.append((train.role, select.role)) or fitted))
    monkeypatch.setattr(ex, "save", lambda fitted, p: p.write_bytes(b"synthetic-checkpoint-not-a-model"))
    monkeypatch.setattr(ex, "load", lambda *a, **k: fitted)
    def infer(fitted, source):
        labels = source.split()["label"]
        logits = np.eye(8)[labels] * 2
        return {"logits": logits, "embedding": logits, "plan_logits": None}
    monkeypatch.setattr(ex, "infer_streaming", infer)
    scorer = SimpleNamespace(provenance="synthetic", save=lambda p: p.write_bytes(b"synthetic-scorer"),
                             to_dict=lambda: {"synthetic_only": True})
    monkeypatch.setattr(ex, "fit_mahalanobis", lambda *a, **k: scorer)
    result = ex.run_b2_experiment(cfg, "known", tmp_path / "out", allow_test_read=True, log=lambda *a: None)
    assert fit_roles == [("train", "val-select")]
    access = result["historical_test_access"]
    assert access["explicit_intent"] is True and access["test_groups"] == [3200000, 3200001]
    assert result["benchmark_complete"] is result["production_authorized"] is access["production_authorized"] is False
    assert "not pristine" in (tmp_path / "out/results.md").read_text()
    assert json.loads((tmp_path / "out/results.json").read_text())["historical_test_access"] == access

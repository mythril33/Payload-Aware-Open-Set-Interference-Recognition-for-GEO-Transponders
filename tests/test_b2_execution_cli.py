"""Phase-aware canonical CLI dispatch; all fixtures are stubs, no fitting or held-out reads."""
import json
import subprocess
import sys
from types import SimpleNamespace

import numpy as np
import pytest

from geoml import b2_experiment as ex
from geoml import b2_execution as execution
from geosim.b2_protocol import LABELS


@pytest.fixture
def calls(monkeypatch):
    out = []
    monkeypatch.setattr(ex, "_legacy_cli_preflight", lambda data:out.append(("preflight", data)))
    for name in ("fit_b2_models", "calibrate_b2_models", "freeze_inventory", "evaluate_b2_inventory"):
        monkeypatch.setattr(execution, name, lambda *a, _name=name, **k:out.append((_name,a,k)))
    monkeypatch.setattr(ex, "run_b2_experiment", lambda *a, **k:out.append(("legacy",a,k)))
    return out


@pytest.fixture
def config(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"views":["co"], "training":{"epochs":1,"batch":8,"width":4,
                                                           "seed":0,"center_loss_weight":0.005}}))
    return str(path)


def test_default_cli_preserves_legacy_dispatch_and_options(calls, config):
    ex.main(["--config",config,"--data","known","--out","result","--reuse",
             "--unknown-data","unknown","--matched-data","matched"])
    assert calls[0] == ("preflight","known")
    name,args,kwargs = calls[1]
    assert name == "legacy" and isinstance(args[0],ex.B2ExperimentConfig)
    assert args[1:] == ("known","result")
    assert kwargs == {"reuse":True,"device":"cpu","unknown_data":"unknown","matched_data":"matched"}


def test_train_only_dispatch_uses_canonical_config_type(calls, config):
    ex.main(["--mode","train-only","--config",config,"--data","known","--out","fit","--reuse"])
    name,args,kwargs = calls[0]
    assert name == "fit_b2_models" and type(args[0]) is ex.B2ExperimentConfig
    assert args[1:] == ("known","fit") and kwargs == {"reuse":True,"device":"cpu"}


def test_module_entry_point_uses_canonical_class_before_artifact_reads(config, tmp_path):
    # A real `python -m` creates a second __main__ class. The caps error proves
    # that its config reached the canonical API instead of failing isinstance.
    path = tmp_path / "over-cap.json"
    with open(config) as stream:
        raw = json.load(stream)
    raw["training"]["epochs"] = 3
    path.write_text(json.dumps(raw))
    out = tmp_path / "must-not-be-created"
    result = subprocess.run([sys.executable, "-m", "geoml.b2_experiment", "--mode", "train-only",
                             "--config", str(path), "--data", str(tmp_path / "absent"),
                             "--out", str(out)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 2
    assert "training exceeds the bounded CPU smoke caps" in result.stderr
    assert "config must be a B2ExperimentConfig" not in result.stderr
    assert not out.exists()


def test_calibrate_loads_its_configuration_from_existing_runs(calls):
    ex.main(["--mode","calibrate","--data","known","--runs","fit","--reuse"])
    assert calls == [("calibrate_b2_models",("known","fit"),{"reuse":True,"device":"cpu"})]


def test_freeze_defaults_to_full_admission_profile(calls):
    ex.main(["--mode","freeze","--bundle","seed0","--bundle","seed1","--bundle","seed2","--out","inventory.json"])
    assert calls == [("freeze_inventory",(["seed0","seed1","seed2"],"inventory.json"),
                      {"seeds":(0,1,2),"profile":"proposed-full"})]


def test_freeze_fixture_requires_explicit_profile_and_keeps_declared_seed(calls):
    ex.main(["--mode","freeze","--bundle","seed7","--out","fixture.json","--profile","fixture","--seeds","7"])
    assert calls == [("freeze_inventory",(["seed7"],"fixture.json"),{"seeds":[7],"profile":"fixture"})]


def test_evaluate_is_separate_and_only_receives_frozen_inventory(calls):
    ex.main(["--mode","evaluate","--data","known","--inventory","frozen.json","--out","evaluation",
             "--unknown-data","unknown","--matched-data","matched"])
    assert calls == [("evaluate_b2_inventory",("known","frozen.json","evaluation"),
                      {"unknown_data":"unknown","matched_data":"matched","profile":"proposed-full"})]


@pytest.mark.parametrize("argv", [
    ["--mode","train-only","--data","known","--out","fit"],
    ["--mode","calibrate","--data","known"],
    ["--mode","freeze","--out","inventory.json"],
    ["--mode","evaluate","--data","known","--out","evaluation"],
])
def test_missing_phase_inputs_refuse_before_any_function(calls, argv):
    with pytest.raises(SystemExit) as error: ex.main(argv)
    assert error.value.code == 2 and calls == []


@pytest.mark.parametrize("mode,extra", [
    ("train-only",["--unknown-data","unknown"]),
    ("train-only",["--matched-data","matched"]),
    ("train-only",["--inventory","frozen.json"]),
    ("train-only",["--runs","oldfit"]),
    ("train-only",["--profile","fixture"]),
    ("calibrate",["--out","elsewhere"]),
    ("calibrate",["--config","unused.json"]),
    ("calibrate",["--unknown-data","unknown"]),
    ("freeze",["--reuse"]),
    ("freeze",["--data","known"]),
    ("evaluate",["--reuse"]),
    ("evaluate",["--config","unused.json"]),
    ("evaluate",["--seeds","0","1","2"]),
    ("legacy",["--inventory","frozen.json"]),
])
def test_phase_inappropriate_options_fail_before_artifact_access(calls, config, mode, extra):
    base={"legacy":["--config",config,"--data","known","--out","legacy"],
          "train-only":["--config",config,"--data","known","--out","fit"],
          "calibrate":["--data","known","--runs","fit"],
          "freeze":["--bundle","fit","--out","inventory.json"],
          "evaluate":["--data","known","--inventory","frozen.json","--out","eval"]}
    with pytest.raises(SystemExit) as error: ex.main(["--mode",mode,*base[mode],*extra])
    assert error.value.code == 2 and calls == []


@pytest.mark.parametrize("mode", ["train-only","calibrate","freeze","evaluate"])
def test_new_phase_cuda_request_is_refused_before_call(calls, config, mode):
    argv={"train-only":["--config",config,"--data","known","--out","fit"],
          "calibrate":["--data","known","--runs","fit"],
          "freeze":["--bundle","fit","--out","inventory.json"],
          "evaluate":["--data","known","--inventory","inventory.json","--out","eval"]}[mode]
    with pytest.raises(SystemExit) as error: ex.main(["--mode",mode,*argv,"--device","cuda"])
    assert error.value.code == 2 and calls == []


def test_cli_legacy_size_check_uses_header_before_the_full_reader(monkeypatch):
    from geosim import b2_dataset as ds
    monkeypatch.setattr(ds,"_header",lambda path:({"roles":{"train":{"n_scenarios":13}}},None))
    with pytest.raises(ValueError,match="legacy.*pilot"):
        ex._legacy_cli_preflight("metadata-only")


def test_cli_legacy_guard_rejects_before_dispatch_or_observation_read(monkeypatch, config):
    from geosim import b2_dataset as ds
    monkeypatch.setattr(ds,"_header",lambda path:({"roles":{"train":{"n_scenarios":13}}},None))
    monkeypatch.setattr(ex,"run_b2_experiment",lambda *a,**k:pytest.fail("coupled reader was invoked"))
    with pytest.raises(SystemExit) as error:
        ex.main(["--config",config,"--data","metadata-only","--out","not-created"])
    assert error.value.code == 2


@pytest.mark.parametrize("error", [KeyError("request"), TypeError("invalid roles"), OSError("unreadable calibration")])
def test_cli_corrupt_header_is_an_artifact_refusal_without_dispatch(monkeypatch, config, error, capsys):
    from geosim import b2_dataset as ds
    def corrupt(path):
        raise error
    monkeypatch.setattr(ds,"_header",corrupt)
    monkeypatch.setattr(ex,"run_b2_experiment",lambda *a,**k:pytest.fail("corrupt artifact was dispatched"))
    with pytest.raises(SystemExit) as exit_error:
        ex.main(["--config",config,"--data","corrupt","--out","not-created"])
    assert exit_error.value.code == 2
    assert "invalid legacy pilot artifact" in capsys.readouterr().err


def test_legacy_api_twelve_groups_pass_size_guard_without_training(monkeypatch,tmp_path):
    cfg=ex.B2ExperimentConfig(views=("co",),training={"center_loss_weight":0.005})
    manifest={"protocol":"wrong-protocol","labels":list(LABELS),"benchmark_complete":False}
    sources={role:SimpleNamespace(groups=np.arange(12),has_residual=True) for role in ex.ROLES}
    monkeypatch.setattr(ex,"open_b2_known",lambda data:(manifest,"a"*64,sources))
    # Reaching the pre-existing protocol check proves the exact 12-group cap
    # accepts the E1 memory fixture without fitting or using held-out content.
    with pytest.raises(ValueError,match="does not match the experiment"):
        ex.run_b2_experiment(cfg,"not-read",tmp_path/"out")
    assert not (tmp_path/"out").exists()


def test_legacy_api_refuses_large_coupled_work_before_any_fitting(monkeypatch,tmp_path):
    cfg=ex.B2ExperimentConfig(views=("co",),training={"epochs":1,"batch":8,"width":4,"seed":0,
                                                   "center_loss_weight":0.005})
    manifest={"protocol":"B2-feat/1","labels":list(LABELS),"benchmark_complete":False}
    sources={role:SimpleNamespace(groups=np.arange(13),has_residual=True) for role in ex.ROLES}
    monkeypatch.setattr(ex,"open_b2_known",lambda data:(manifest,"a"*64,sources))
    monkeypatch.setattr(ex,"fit_streaming",lambda *a,**k:pytest.fail("fitting began before pilot guard"))
    with pytest.raises(ValueError,match="legacy.*pilot"):
        ex.run_b2_experiment(cfg,"not-read",tmp_path/"out")
    assert not (tmp_path/"out").exists()

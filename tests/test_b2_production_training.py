"""Production adapter policy tests and bounded actual training kernels on stand-in RF."""
from dataclasses import replace
import json

import pytest
import torch

from geosim import b2_dataset as ds
from geosim.b2_protocol import LABELS, scenario_ids
from geosim.cancellation import CancellationConfig
from geoml import b2_production_training as p
from geoml import b2_execution as old
from geoml.b2_experiment import B2ExperimentConfig
from test_b2_artifacts import feature_generator, generator  # noqa: F401
from test_b2_role_loader import _refuse_unrequested_reads


def test_approved_recipe_is_explicit_and_retains_matched_arm_semantics():
    cfg = p.production_config()
    train = cfg.train_config("dual_residual")
    assert (train.width,train.epochs,train.batch,train.time_pool) == (16,30,32,2)
    assert (train.lr,train.weight_decay,train.center_loss_weight,train.plan_loss_weight) == (.001,.0001,.005,1.)
    assert train.plan_consistency and train.plan_shift_fraction == .15 and train.augment
    assert cfg.window_shards == 4 and cfg.methods == ("msp","energy","mahalanobis")
    pair = p.production_config(("dual_planmask","dual_noplan"),2)
    assert pair.training["level"] == "absolute" and pair.training["plan_shift_fraction"] == 0
    assert pair.plan_consistency is False
    assert p._config(json.loads(json.dumps(cfg.resolved()))).resolved() == cfg.resolved()


@pytest.mark.parametrize("change",[{"width":8},{"epochs":2},{"batch":16},{"lr":.01},{"center_loss_weight":0.}])
def test_production_recipe_rejects_unapproved_numerical_changes(change):
    raw = json.loads(json.dumps(p.production_config().resolved()))
    raw["training"].update(change)
    with pytest.raises(ValueError,match="approved production recipe"):
        p._config(raw)


@pytest.mark.parametrize("views,seed",[((),0),(("co","dual_noplan"),0),(("co",),True),(("co",),3)])
def test_invalid_roster_and_seed_refused(views,seed):
    with pytest.raises(ValueError):
        p.production_config(views,seed)


def test_canonical_closed_gate_cannot_be_overridden_by_an_authorization_callback(tmp_path,monkeypatch):
    class Fake:
        def require(self,*_):
            pytest.fail("a caller port cannot override a closed canonical gate")
    monkeypatch.setattr(p,"runtime_identity",lambda *_:pytest.fail("unauthorized device query"))
    monkeypatch.setattr(p,"_open",lambda *_:pytest.fail("unauthorized data read"))
    for device in ("cpu","cuda:0"):
        with pytest.raises(p.AuthorizationRequired,match="gate CLOSED"):
            p.fit_models(tmp_path/"missing",tmp_path/"run",authorization=Fake(),device=device)
        with pytest.raises(p.AuthorizationRequired,match="gate CLOSED"):
            p.calibrate_models(tmp_path/"missing",tmp_path/"run",authorization=Fake(),device=device)
    assert not (tmp_path/"run").exists()


def test_authorization_port_default_denies_and_actions_are_separate():
    with pytest.raises(p.AuthorizationRequired):
        p._require(None,"training","identity")
    seen = []
    class Port:
        def require(self,action,identity):
            seen.append((action,identity))
    for action in ("training","gpu_qualification","gpu_training"):
        p._require(Port(),action,"identity")
    assert [x[0] for x in seen] == ["training","gpu_qualification","gpu_training"]


def test_r6_context_enforces_and_restores_effective_flags_without_gpu_probe(monkeypatch):
    monkeypatch.setattr(torch.cuda,"get_device_properties",lambda *_:pytest.fail("CPU path probed GPU"))
    previous = torch.backends.cudnn.allow_tf32,torch.backends.cuda.matmul.allow_tf32
    try:
        torch.backends.cudnn.allow_tf32 = True
        torch.backends.cuda.matmul.allow_tf32 = True
        with p.r6_fp32():
            runtime = p.runtime_identity("cpu")
            assert runtime["profile"] == p.R6_PROFILE
            assert runtime["cudnn_allow_tf32"] is False and runtime["matmul_allow_tf32"] is False
            assert runtime["device"] == "cpu" and runtime["gpu"] is None and runtime["driver"] is None
        assert torch.backends.cudnn.allow_tf32 and torch.backends.cuda.matmul.allow_tf32
    finally:
        torch.backends.cudnn.allow_tf32,torch.backends.cuda.matmul.allow_tf32 = previous


def test_production_role_metadata_requires_exact_groups_and_r7_shards():
    manifest = {"roles":{r:{"scenario_seeds":scenario_ids(r)} for r in old.ROLES},"protocol":"B2-feat/1",
        "labels":list(LABELS),"benchmark_complete":False,"cancellation":CancellationConfig().to_dict(),
        "request":{"groups_per_shard":4}}
    assert len(p._role_plan(manifest)["train"]) == 1500
    manifest["roles"]["train"]["scenario_seeds"] = scenario_ids("train",2)
    with pytest.raises(ValueError,match="canonical groups"):
        p._role_plan(manifest)


def test_bounded_three_role_train_validation_calibration_and_freeze(tmp_path,monkeypatch,feature_generator):
    data = tmp_path/"data"
    ds.generate_b2_dataset(data,roles=("train","val-select","val-calib"),limit_groups=1,
        groups_per_shard=1,cancellation=CancellationConfig())
    allowed = {"train","val-select"}
    seen = _refuse_unrequested_reads(monkeypatch,data,allowed)
    original = p.open_b2_known_roles
    def scoped(root,roles):
        allowed.clear();allowed.update(roles)
        assert "test" not in roles
        return original(root,roles)
    monkeypatch.setattr(p,"open_b2_known_roles",scoped)
    cfg = B2ExperimentConfig(views=("dual_residual",),training={"epochs":1,"width":1,"time_pool":8,
        "batch":8,"seed":0,"augment":False,"plan_shift_fraction":0.,"center_loss_weight":.005})
    result = p.development_train_calibrate_freeze(cfg,data,tmp_path/"runs",tmp_path/"freeze.json",log=lambda *_:None)
    assert set(seen) == {"train","val-select","val-calib"}
    assert len(result["training"]["dual_residual"]["history"]) == 1
    assert result["training"]["dual_residual"]["selected_epoch"] == 0
    assert result["calibration"]["dual_residual"]["alarm"]["n_clean_calibration"] == 1
    assert result["inventory"]["heldout_reads"] == 0 and result["inventory"]["scope"] == "BOUNDED_DEVELOPMENT"
    assert "test" not in result["development"]["roles"]
    assert result["development"]["source"] == p._source_identity()
    assert result["development"]["runtime"]["device"] == "cpu"
    old._files(tmp_path/"runs",result["inventory"]["files"])
    with pytest.raises(ValueError,match="marker"):
        p._marker(tmp_path/"runs","development")


def test_development_never_widens_existing_caps_or_accepts_full_data(tmp_path):
    cfg = p.production_config()
    with pytest.raises(ValueError,match="bounded CPU smoke caps"):
        p.development_train_calibrate_freeze(cfg,tmp_path/"missing",tmp_path/"runs",tmp_path/"freeze.json")
    assert old.CAPS == {"groups_per_role":2,"epochs":2,"width":8,"batch":32}

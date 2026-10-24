"""P31 isolated phases on deterministic stand-in observations, never real held-out data."""
from dataclasses import replace
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
import torch

from geosim.b2_protocol import LABELS, ROLE_STARTS
from geosim.cancellation import CancellationConfig
from geoml import b2_execution as execution
from geoml.b2_experiment import B2ExperimentConfig
from geoml.b2_stream import B2Source
from geoml.artifacts import fingerprint


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@pytest.fixture
def fixture(monkeypatch, tmp_path):
    splits = {}
    for index, role in enumerate(execution.ROLES):
        rng = np.random.default_rng(index)
        groups = np.repeat(np.arange(ROLE_STARTS[role], ROLE_STARTS[role] + 2), len(LABELS))
        labels = np.tile(np.arange(len(LABELS)), 2).astype(np.int8)
        spec = rng.normal(-80, 2, (16, 2, 8, 32)).astype(np.float16)
        mask = np.full((16, 2, 32), -60, np.float16)
        mask[:, :, 8:16] = 0
        splits[role] = {"spec": spec, "mask": mask, "residual": (spec[:, 0] - 12).astype(np.float16),
                        "seed": groups, "label": labels, "plan_consistency": (groups % 2).astype(np.int8),
                        "meta": [{"scenario_id": int(g)} for g in groups]}
    manifest = {"protocol": "B2-feat/1", "parent_protocol": "B2/1", "labels": list(LABELS),
                "benchmark_complete": False, "config": {"bandwidth": 36e6},
                "cancellation": CancellationConfig().to_dict(), "calibration": {"n_pilots": 64},
                "roles": {role: {"scenario_seeds": np.unique(part["seed"]).tolist()} for role,part in splits.items()}}
    calls = []
    def scoped(data, roles):
        calls.append(tuple(roles))
        return manifest, "f" * 64, {role:B2Source.from_arrays(splits[role], role=role) for role in roles}
    monkeypatch.setattr(execution, "open_b2_known_roles", scoped)
    monkeypatch.setattr(execution, "_known_header",lambda data:(manifest,None))
    monkeypatch.setattr(execution, "_source_identity", lambda: {"revision":"stand-in", "files_sha256":{"standin.py":"0"*64}})
    return splits, manifest, calls, tmp_path / "data"


def config(seed=0, views=("co",)):
    return B2ExperimentConfig(views=views, training={"epochs":1,"batch":8,"width":2,"seed":seed,
         "center_loss_weight":0.005,"plan_loss_weight":1.,"plan_shift_fraction":0.,"augment":False})


def trained(fixture, tmp_path, *, seed=0, views=("co",)):
    out=tmp_path/f"seed-{seed}"
    execution.fit_b2_models(config(seed,views),fixture[3],out,log=lambda *_:None)
    return out


def calibrated(fixture,tmp_path,*,seed=0,views=("co",)):
    out=trained(fixture,tmp_path,seed=seed,views=views)
    execution.calibrate_b2_models(fixture[3],out,log=lambda *_:None)
    return out


def test_fit_reads_train_selection_only_and_fits_train_statistics(fixture,tmp_path,monkeypatch):
    seen=[];fit=execution.fit_mahalanobis
    def spy(embeddings, labels, *args, **kwargs):
        seen.append(np.array(labels));return fit(embeddings,labels,*args,**kwargs)
    monkeypatch.setattr(execution,"fit_mahalanobis",spy)
    out=trained(fixture,tmp_path)
    assert fixture[2]==[("train","val-select")]
    np.testing.assert_array_equal(seen[0],fixture[0]["train"]["label"])
    assert (out/"training.json").exists() and not (out/"calibration.json").exists()
    assert not (out/"results.json").exists()


def test_calibration_is_a_separate_known_only_phase_with_immutable_models(fixture,tmp_path,monkeypatch):
    out=trained(fixture,tmp_path);before={p.name:_sha(p) for p in out.iterdir()}
    monkeypatch.setattr(execution,"fit_streaming",lambda *_a,**_k:pytest.fail("fit during calibration"))
    monkeypatch.setattr(execution,"fit_mahalanobis",lambda *_a,**_k:pytest.fail("statistics fit during calibration"))
    result=execution.calibrate_b2_models(fixture[3],out,log=lambda *_:None)
    assert fixture[2][-1]==("val-calib",)
    assert all(_sha(out/name)==digest for name,digest in before.items())
    assert result["benchmark_complete"] is False
    assert (out/"calibration.json").exists()


def test_phase_reuse_refuses_incomplete_corrupt_or_changed_source(fixture,tmp_path,monkeypatch):
    out=trained(fixture,tmp_path)
    with pytest.raises(ValueError,match="nonempty|exists"):
        execution.fit_b2_models(config(),fixture[3],out,log=lambda *_:None)
    monkeypatch.setattr(execution,"fit_streaming",lambda *_a,**_k:pytest.fail("reuse refitted"))
    execution.fit_b2_models(config(),fixture[3],out,reuse=True,log=lambda *_:None)
    model=out/"model_co.pt";raw=model.read_bytes();model.write_bytes(raw[:-1]+bytes([raw[-1]^1]))
    with pytest.raises(ValueError,match="hash|checksum|modified"):
        execution.calibrate_b2_models(fixture[3],out,log=lambda *_:None)
    model.write_bytes(raw)
    monkeypatch.setattr(execution,"_source_identity",lambda:{"revision":"new","files_sha256":{"standin.py":"1"*64}})
    with pytest.raises(ValueError,match="source|provenance"):
        execution.calibrate_b2_models(fixture[3],out,log=lambda *_:None)


@pytest.mark.parametrize("override",[{"epochs":3},{"width":16},{"batch":64}])
def test_new_fit_execution_is_capped(fixture,tmp_path,override):
    cfg=config();cfg=replace(cfg,training={**cfg.training,**override})
    with pytest.raises(ValueError,match="cap|bounded"):
        execution.fit_b2_models(cfg,fixture[3],tmp_path/"out",log=lambda *_:None)
    assert not (tmp_path/"out").exists()


def test_gpu_and_unbounded_modes_are_refused(fixture,tmp_path):
    with pytest.raises(ValueError,match="CPU|cpu"):
        execution.fit_b2_models(config(),fixture[3],tmp_path/"out",device="cuda")
    with pytest.raises(ValueError,match="bounded|smoke"):
        execution.fit_b2_models(config(),fixture[3],tmp_path/"out",smoke=False)


def test_incomplete_inventory_is_rejected_before_any_test_read(fixture,tmp_path,monkeypatch):
    out=calibrated(fixture,tmp_path)
    with pytest.raises(ValueError,match="nine|9|inventory|views"):
        execution.freeze_inventory([out],tmp_path/"inventory.json")
    fixture_inventory=tmp_path/"fixture.json"
    execution.freeze_inventory([out],fixture_inventory,seeds=(0,),profile="fixture")
    fixture[2].clear()
    with pytest.raises(ValueError,match="profile|nine|inventory"):
        execution.evaluate_b2_inventory(fixture[3],fixture_inventory,tmp_path/"eval")
    assert fixture[2]==[] and not (tmp_path/"eval").exists()


def test_fixture_evaluation_uses_only_frozen_objects_and_readonly_inputs(fixture,tmp_path,monkeypatch):
    out=calibrated(fixture,tmp_path);inventory=tmp_path/"inventory.json"
    execution.freeze_inventory([out],inventory,seeds=(0,),profile="fixture")
    before={str(p):_sha(p) for p in out.rglob("*") if p.is_file()};before[str(inventory)]=_sha(inventory)
    fixture[2].clear()
    for name in ["fit_streaming","fit_mahalanobis","calibrate_scores","clean_alarm_threshold"]:
        monkeypatch.setattr(execution,name,lambda *_a,**_k:pytest.fail("evaluation fitted/calibrated"))
    result=execution.evaluate_b2_inventory(fixture[3],inventory,tmp_path/"eval",profile="fixture",log=lambda *_:None)
    assert fixture[2]==[("test",),("test",)]  # opening and final artifact snapshot verification
    assert result["benchmark_complete"] is False and result["profile"]=="fixture"
    assert all(_sha(path)==digest for path,digest in before.items())
    with pytest.raises(ValueError,match="overlap|read-only|separate"):
        execution.evaluate_b2_inventory(fixture[3],inventory,out/"evaluation",profile="fixture")


def test_all_nine_inventory_cells_are_validated_before_test_access(fixture,tmp_path,monkeypatch):
    runs=[calibrated(fixture,tmp_path,seed=seed,views=("co","dual","dual_residual")) for seed in (0,1,2)]
    inventory=tmp_path/"inventory.json"
    frozen=execution.freeze_inventory(runs,inventory,seeds=(0,1,2))
    assert frozen["profile"]=="proposed-full"
    assert len(frozen["cells"])==9
    raw=(runs[-1]/"model_dual_residual.pt").read_bytes()
    (runs[-1]/"model_dual_residual.pt").write_bytes(raw[:-1]+bytes([raw[-1]^1]))
    fixture[2].clear()
    with pytest.raises(ValueError,match="hash|checksum|modified"):
        execution.evaluate_b2_inventory(fixture[3],inventory,tmp_path/"bad")
    assert fixture[2]==[] and not (tmp_path/"bad").exists()
    (runs[-1]/"model_dual_residual.pt").write_bytes(raw)
    result=execution.evaluate_b2_inventory(fixture[3],inventory,tmp_path/"good",log=lambda *_:None)
    assert result["inventory_cells"]==9 and len(result["models"])==9
    assert fixture[2]==[("test",),("test",)]


def test_strict_json_markers_reject_duplicate_or_nonfinite_payload(fixture,tmp_path):
    out=trained(fixture,tmp_path)
    path=out/"training.json";raw=path.read_text()
    path.write_text(raw.rstrip()[:-1]+',"bad":NaN}')
    with pytest.raises(ValueError):execution.calibrate_b2_models(fixture[3],out)
    path.write_text(raw.rstrip()[:-1]+',"benchmark_complete":false}')
    with pytest.raises(ValueError,match="duplicate"):
        execution.calibrate_b2_models(fixture[3],out)


def test_inventory_rejects_duplicate_seed_and_missing_calibration(fixture,tmp_path):
    out=trained(fixture,tmp_path)
    with pytest.raises(ValueError,match="calibration|incomplete|missing"):
        execution.freeze_inventory([out],tmp_path/"inventory.json",seeds=(0,),profile="fixture")
    execution.calibrate_b2_models(fixture[3],out,log=lambda *_:None)
    with pytest.raises(ValueError,match="seed|distinct|duplicate"):
        execution.freeze_inventory([out,out],tmp_path/"duplicate.json",seeds=(0,),profile="fixture")


def resign(path,payload):
    payload["artifact_id"]=fingerprint({k:v for k,v in payload.items() if k!="artifact_id"})
    path.write_text(json.dumps(payload,allow_nan=False))


def test_threshold_rule_matches_independent_power_probability_arithmetic(fixture,tmp_path):
    out=calibrated(fixture,tmp_path)
    trained_marker,cfg,loaded=execution._verify_training(out)
    fitted,scorer=loaded["co"]
    source=B2Source.from_arrays(fixture[0]["val-calib"],role="val-calib")
    outputs=execution.infer_streaming(fitted,source)
    logits=outputs["logits"].astype(np.float64);p=np.exp(logits-logits.max(1,keepdims=True));p/=p.sum(1,keepdims=True)
    clean=source.index["label"]==0
    alarm=json.loads((out/"alarm_co.json").read_text())
    # E10 (docs/engineering/B2_E10_R10_CLEAN_ALARM_CHANGE.md): the approved R10 clean-alarm rule is the higher
    # empirical quantile. The earlier interpolated expectation was the historical linear rule and is retired here.
    expected=float(np.quantile(1.-p[clean,0],.95,method="higher"))
    assert alarm["threshold"]==pytest.approx(expected,abs=1e-12)
    assert alarm["n_clean_calibration"]==2
    assert alarm["calibration_false_alarms"]==int(((1.-p[clean,0])>expected).sum())
    for method in cfg.methods:
        values=scorer.score(outputs["embedding"]) if method=="mahalanobis" else execution.unknown_scores(outputs["logits"],method)
        rejection=json.loads((out/f"rejection_co_{method}.json").read_text())
        assert rejection["threshold"]==float(np.quantile(values,.95,method="higher"))
        assert execution.RejectionCalibration.from_dict(rejection).accept(np.array([rejection["threshold"]])).item()


def test_fitting_is_deterministic_and_heldout_observations_cannot_change_it(fixture,tmp_path):
    first=trained(fixture,tmp_path/"first")
    fixture[0]["test"]["spec"][:]=np.nan
    fixture[0]["val-calib"]["spec"][:]=1000
    torch.manual_seed(999)
    second=trained(fixture,tmp_path/"second")
    a=execution.load(first/"model_co.pt",device="cpu");b=execution.load(second/"model_co.pt",device="cpu")
    assert a["history"]==b["history"] and a["best_epoch"]==b["best_epoch"]
    assert all(torch.equal(v,b["model"].state_dict()[k]) for k,v in a["model"].state_dict().items())
    x=execution.MahalanobisScorer.load(first/"mahalanobis_co.npz");y=execution.MahalanobisScorer.load(second/"mahalanobis_co.npz")
    np.testing.assert_array_equal(x.means,y.means);np.testing.assert_array_equal(x.cholesky,y.cholesky)


@pytest.mark.parametrize("role",["train","val-select","val-calib","test"])
def test_metadata_role_isolation_and_group_caps_are_enforced_before_fit(fixture,tmp_path,role):
    fixture[1]["roles"][role]["scenario_seeds"]=[ROLE_STARTS[role]+n for n in range(3)]
    with pytest.raises(ValueError,match="cap|bounded"):
        trained(fixture,tmp_path)
    assert not (tmp_path/"seed-0").exists()
    assert fixture[2]==[]  # oversized metadata is refused before opening any spectrum/residual rows


@pytest.mark.parametrize("case",["runtime","data","role","selected"])
def test_resigned_foreign_training_metadata_is_rejected(fixture,tmp_path,case):
    out=trained(fixture,tmp_path);path=out/"training.json";payload=json.loads(path.read_text())
    if case=="runtime":payload["runtime"]["numpy"]="foreign"
    if case=="data":payload["data_identity"]="a"*64
    if case=="role":payload["roles"]["val-calib"]=[ROLE_STARTS["test"]]
    if case=="selected":payload["views"]["co"]["selected_epoch"]=999
    resign(path,payload)
    with pytest.raises(ValueError):execution.calibrate_b2_models(fixture[3],out)


@pytest.mark.parametrize("case",["direction","threshold","false_alarms","population"])
def test_resigned_invalid_calibration_contract_is_rejected(fixture,tmp_path,case):
    out=calibrated(fixture,tmp_path);apath=out/"alarm_co.json";alarm=json.loads(apath.read_text())
    if case=="direction":alarm["direction"]="lower_is_more_anomalous"
    if case=="threshold":alarm["threshold"]=-1
    if case=="false_alarms":alarm["calibration_false_alarms"]=3
    if case=="population":alarm["population"]="all known val-calib"
    apath.write_text(json.dumps(alarm));path=out/"calibration.json";payload=json.loads(path.read_text())
    payload["files"][apath.name]=_sha(apath);payload["views"]["co"]["alarm"]=alarm;resign(path,payload)
    with pytest.raises(ValueError,match="calibration"):
        execution.freeze_inventory([out],tmp_path/"inventory.json",seeds=(0,),profile="fixture")


def test_copying_native_checkpoint_cannot_impersonate_a_different_seed(fixture,tmp_path):
    left=calibrated(fixture,tmp_path,seed=0);right=trained(fixture,tmp_path,seed=1)
    (right/"model_co.pt").write_bytes((left/"model_co.pt").read_bytes())
    path=right/"training.json";payload=json.loads(path.read_text());payload["files"]["model_co.pt"]=_sha(right/"model_co.pt")
    payload["views"]["co"]["checkpoint_sha256"]=payload["files"]["model_co.pt"];resign(path,payload)
    with pytest.raises(ValueError,match="configuration|config"):
        execution.calibrate_b2_models(fixture[3],right)


def test_partial_calibration_and_incomplete_training_never_resume_by_refitting(fixture,tmp_path):
    out=trained(fixture,tmp_path);(out/"alarm_co.json").write_text('{}')
    with pytest.raises(ValueError,match="incomplete calibration"):
        execution.calibrate_b2_models(fixture[3],out)
    (out/"training.json").unlink()
    with pytest.raises(ValueError,match="missing|invalid|incomplete"):
        execution.fit_b2_models(config(),fixture[3],out,reuse=True)


@pytest.mark.parametrize("placement",["same","inside","ancestor","symlink"])
def test_training_output_cannot_overlap_or_alias_input_data(fixture,tmp_path,placement):
    data=fixture[3]
    data.mkdir();(data/"preserved.txt").write_text("input artifact remains untouched")
    if placement=="same":out=data
    elif placement=="inside":out=data/"training"
    elif placement=="ancestor":out=data.parent
    else:
        out=tmp_path/"alias";out.symlink_to(data,target_is_directory=True)
    with pytest.raises(ValueError,match="separate|overlap"):
        execution.fit_b2_models(config(),data,out)
    assert (data/"preserved.txt").read_text()=="input artifact remains untouched"
    assert fixture[2]==[]


def test_calibration_refuses_a_training_bundle_overlapping_data(fixture,tmp_path):
    with pytest.raises(ValueError,match="separate|overlap"):
        execution.calibrate_b2_models(fixture[3],fixture[3]/"training")
    assert fixture[2]==[]


@pytest.mark.parametrize("kind",["known","unknown","matched"])
def test_evaluation_output_cannot_overlap_any_input_artifact(fixture,tmp_path,kind):
    out=calibrated(fixture,tmp_path);inventory=tmp_path/"inventory.json"
    execution.freeze_inventory([out],inventory,seeds=(0,),profile="fixture")
    roots={"known":fixture[3],"unknown":tmp_path/"unknown","matched":tmp_path/"matched"}
    fixture[2].clear()
    with pytest.raises(ValueError,match="separate|overlap"):
        execution.evaluate_b2_inventory(roots["known"],inventory,roots[kind]/"evaluation",
            unknown_data=roots["unknown"],matched_data=roots["matched"],profile="fixture")
    assert fixture[2]==[]


def install_optional_artifacts(fixture,monkeypatch):
    from test_b2_experiment import _unknown_split,_matched_split
    parts={"test_only":_unknown_split(2,55),"matched":_matched_split(2,66)}
    states={}
    for name,protocol in (("test_only","B2-test/1"),("matched","B2-match/1")):
        states[name]={"identity":("a" if name=="test_only" else "b")*64,
          "manifest":{"protocol":protocol,"config":fixture[1]["config"],"cancellation":fixture[1]["cancellation"],
            "scenario_seeds":np.unique(parts[name]["seed"]).tolist(),
            "request":{"known":{"known_data_fingerprint":"f"*64},"source_sha256":{"stand-in":"0"*64}},
            "request_fingerprint":("c" if name=="test_only" else "d")*64,"calibration":{"stand-in":True}}}
    def opened(name):
        def call(path):
            kind="test" if name=="test_only" else "matched"
            role="test" if kind=="test" else "test-matched"
            state=states[name]
            return state["manifest"],state["identity"],B2Source.from_arrays(parts[name],kind=kind,role=role)
        return call
    monkeypatch.setattr(execution.ex,"open_b2_test",opened("test_only"))
    monkeypatch.setattr(execution.ex,"open_b2_matched",opened("matched"))
    monkeypatch.setattr(execution,"_test_header",lambda path:(states["test_only"]["manifest"],None))
    monkeypatch.setattr(execution,"_matched_header",lambda path:(states["matched"]["manifest"],None))
    return states


def test_optional_evaluation_population_identities_are_bound_into_result_and_receipt(fixture,tmp_path,monkeypatch):
    states=install_optional_artifacts(fixture,monkeypatch)
    run=calibrated(fixture,tmp_path);inventory=tmp_path/"inventory.json"
    execution.freeze_inventory([run],inventory,seeds=(0,),profile="fixture")
    out=tmp_path/"evaluation"
    result=execution.evaluate_b2_inventory(fixture[3],inventory,out,profile="fixture",
        unknown_data=tmp_path/"unknown",matched_data=tmp_path/"matched",log=lambda *_:None)
    artifacts=result["evaluation_artifacts"]
    assert artifacts["known"]["data_identity"]=="f"*64 and artifacts["known"]["n_samples"]==16
    assert artifacts["test_only"]["data_identity"]==states["test_only"]["identity"] and artifacts["test_only"]["n_samples"]==10
    assert artifacts["matched"]["data_identity"]==states["matched"]["identity"] and artifacts["matched"]["n_samples"]==6
    assert artifacts["test_only"]["index_name"]=="family" and artifacts["matched"]["role"]=="test-matched"
    receipt=json.loads((out/"completion.json").read_text())
    assert receipt["evaluation_artifacts"]==artifacts
    assert receipt["evaluation_artifacts_sha256"]==fingerprint(artifacts)


@pytest.mark.parametrize("stage",["test_only","matched"])
def test_consistently_resigned_optional_input_drift_is_refused_before_publication(fixture,tmp_path,monkeypatch,stage):
    states=install_optional_artifacts(fixture,monkeypatch)
    run=calibrated(fixture,tmp_path);inventory=tmp_path/"inventory.json"
    execution.freeze_inventory([run],inventory,seeds=(0,),profile="fixture")
    original=execution.infer_streaming
    def mutate_after_inference(fitted,source):
        values=original(fitted,source)
        target="test" if stage=="test_only" else "matched"
        if source.kind==target:
            # A valid new artifact may keep the same sample index yet have
            # different spectra and re-signed descriptors/provenance.
            states[stage]["manifest"]["revision"]="valid-but-different"
            states[stage]["identity"]="e"*64
        return values
    monkeypatch.setattr(execution,"infer_streaming",mutate_after_inference)
    out=tmp_path/"evaluation"
    with pytest.raises(ValueError,match="artifact identity changed"):
        execution.evaluate_b2_inventory(fixture[3],inventory,out,profile="fixture",
            unknown_data=tmp_path/"unknown",matched_data=tmp_path/"matched",log=lambda *_:None)
    assert not out.exists()


@pytest.mark.parametrize("stage",["test_only","matched"])
def test_optional_group_caps_precede_optional_observation_open(fixture,tmp_path,monkeypatch,stage):
    states=install_optional_artifacts(fixture,monkeypatch)
    run=calibrated(fixture,tmp_path);inventory=tmp_path/"inventory.json"
    execution.freeze_inventory([run],inventory,seeds=(0,),profile="fixture")
    role="test" if stage=="test_only" else "test-matched"
    states[stage]["manifest"]["scenario_seeds"]=[ROLE_STARTS[role]+i for i in range(3)]
    name="open_b2_test" if stage=="test_only" else "open_b2_matched"
    monkeypatch.setattr(execution.ex,name,lambda *_a:pytest.fail("oversized optional observation bytes opened"))
    kwargs={"unknown_data":tmp_path/"unknown"} if stage=="test_only" else {"matched_data":tmp_path/"matched"}
    with pytest.raises(ValueError,match="bounded group cap"):
        execution.evaluate_b2_inventory(fixture[3],inventory,tmp_path/"evaluation",profile="fixture",**kwargs)


def test_cpu_thread_and_determinism_state_are_recorded_and_bound(fixture,tmp_path,monkeypatch):
    out=trained(fixture,tmp_path)
    marker=json.loads((out/"training.json").read_text())
    runtime=marker["runtime"]
    assert runtime["torch_threads"]==torch.get_num_threads()
    assert runtime["torch_interop_threads"]==torch.get_num_interop_threads()
    assert runtime["torch_deterministic_algorithms"]==torch.are_deterministic_algorithms_enabled()
    assert "OMP_NUM_THREADS" in runtime["thread_environment"]
    monkeypatch.setattr(execution,"_runtime",lambda:{**runtime,"torch_threads":runtime["torch_threads"]+1})
    with pytest.raises(ValueError,match="runtime"):
        execution.calibrate_b2_models(fixture[3],out)

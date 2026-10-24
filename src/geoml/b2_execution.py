"""P31 isolated, capped CPU training/calibration/frozen evaluation.

The legacy small coupled experiment is unchanged. These explicit phases never
open held-out observations while fitting or calibrating, and evaluation cannot
fit any state. The proposed-full admission profile checks nine frozen cells;
it does not authorize or execute production training or a full benchmark.
"""
from __future__ import annotations

from dataclasses import asdict
import json
import os
from pathlib import Path
import platform

import numpy as np
import scipy
import torch

from geosim.b2_protocol import LABELS, FEATURE_PROTOCOL, role_for_group
from geosim.cancellation import CancellationConfig
from geosim.b2_dataset import _header as _known_header
from geosim.b2_test_dataset import _header as _test_header
from geosim.b2_matched_dataset import _header as _matched_header
from . import b2_experiment as ex
from .artifacts import fingerprint
from .b2_stream import fit_streaming, infer_streaming, open_b2_known_roles
from .calibration import RejectionCalibration, calibrate_scores
from .experiment import _sha256, _source_identity, _write_json
from .mahalanobis import MahalanobisScorer, fit_mahalanobis
from .metrics import confusion, expected_calibration_error, macro_f1, threshold_at_pfa
from .openset import unknown_scores
from .train import load, save

CONTRACT = "B2-isolated-execution/1"
ROLES = ex.ROLES
VIEWS = ex.VIEWS
PROFILES = ("proposed-full", "fixture")
CAPS = {"groups_per_role":2, "epochs":2, "width":8, "batch":32}
ALARM_RULE = "P20 threshold_at_pfa; alarm strictly score > threshold"


def _runtime():
    return {"python":platform.python_version(), "numpy":np.__version__,
            "scipy":scipy.__version__, "torch":str(torch.__version__), "device":"cpu",
            "torch_threads":torch.get_num_threads(),"torch_interop_threads":torch.get_num_interop_threads(),
            "torch_deterministic_algorithms":torch.are_deterministic_algorithms_enabled(),
            "torch_deterministic_debug_mode":torch.get_deterministic_debug_mode(),
            "mkldnn_enabled":torch.backends.mkldnn.enabled,
            "mkldnn_deterministic":getattr(torch.backends.mkldnn,"deterministic",None),
            "thread_environment":{name:os.environ.get(name) for name in
                ("OMP_NUM_THREADS","OPENBLAS_NUM_THREADS","MKL_NUM_THREADS","NUMEXPR_NUM_THREADS","PYTHONHASHSEED")}}


def _strict(path):
    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                raise ValueError(f"duplicate JSON key {key} in {path}")
            out[key] = value
        return out
    def reject(value):
        raise ValueError(f"nonfinite JSON value {value} in {path}")
    try:
        value = json.loads(Path(path).read_text(), object_pairs_hook=pairs, parse_constant=reject)
        json.dumps(value, allow_nan=False)
        return value
    except (OSError, TypeError) as error:
        raise ValueError(f"missing or invalid artifact {path}: {error}") from error


def _marker(path, phase, fields):
    value = _strict(path)
    common = {"contract", "phase", "benchmark_complete", "scope", "artifact_id"}
    if (not isinstance(value, dict) or set(value) != common | set(fields)
            or value.get("contract") != CONTRACT or value.get("phase") != phase
            or value.get("benchmark_complete") is not False or value.get("scope") != "BOUNDED_FIXTURE"
            or value.get("artifact_id") != fingerprint({k:v for k,v in value.items() if k != "artifact_id"})):
        raise ValueError(f"incomplete, modified or incompatible {phase} marker {path}")
    return value


def _commit(path, phase, payload):
    value = {"contract":CONTRACT, "phase":phase, "benchmark_complete":False,
             "scope":"BOUNDED_FIXTURE", **payload}
    value["artifact_id"] = fingerprint(value)
    _write_json(Path(path), value)
    return value


def _cpu(device="cpu", smoke=True):
    if device != "cpu":
        raise ValueError("isolated execution is CPU-only; production GPU training is not authorized")
    if smoke is not True:
        raise ValueError("only bounded smoke execution is implemented")


def _caps(config):
    if not isinstance(config, ex.B2ExperimentConfig):
        raise ValueError("config must be a B2ExperimentConfig")
    for view in config.views:
        cfg = config.train_config(view)
        if cfg.epochs > CAPS["epochs"] or cfg.width > CAPS["width"] or cfg.batch > CAPS["batch"]:
            raise ValueError(f"training exceeds the bounded CPU smoke caps {CAPS}")


def _role_plan(manifest):
    if set(manifest.get("roles", {})) != set(ROLES):
        raise ValueError("the known artifact must declare all four canonical role populations")
    out = {}
    for role in ROLES:
        values = manifest["roles"][role]["scenario_seeds"]
        if (not isinstance(values, list) or not 1 <= len(values) <= CAPS["groups_per_role"]
                or any(type(v) is not int or role_for_group(v) != role for v in values)
                or values != sorted(set(values))):
            raise ValueError("artifact role population exceeds bounded group caps or violates role isolation")
        out[role] = values
    if len(set(sum(out.values(), []))) != sum(map(len, out.values())):
        raise ValueError("scenario group leakage between roles")
    return out


def _preflight_known(data):
    """Reject oversized metadata before any role's observation bytes are read."""
    try:
        manifest,_=_known_header(Path(data))
        _role_plan(manifest)
    except (OSError,KeyError,TypeError) as error:
        raise ValueError(f"invalid bounded known artifact metadata: {error}") from error


def _preflight_optional(path,stage):
    header=_test_header if stage=="test_only" else _matched_header
    try:
        manifest,_=header(Path(path))
        groups=manifest["scenario_seeds"]
        if not 1<=len(groups)<=CAPS["groups_per_role"]:
            raise ValueError("optional evaluation population exceeds bounded group cap")
    except (OSError,KeyError,TypeError) as error:
        raise ValueError(f"invalid bounded optional artifact metadata: {error}") from error


def _data(config, manifest, sources, roles):
    _caps(config)
    role_plan = _role_plan(manifest)
    if (manifest.get("protocol") != config.protocol or manifest.get("benchmark_complete") is not False
            or manifest.get("labels") != list(LABELS) or set(sources) != set(roles)):
        raise ValueError("artifact protocol, labels, completion flag or scoped roles differ")
    if config.protocol == FEATURE_PROTOCOL:
        if manifest.get("cancellation") != CancellationConfig().to_dict():
            raise ValueError("isolated B2-feat/1 requires frozen P20 obs-cancel/1 normalization/cancellation")
        if any(not source.has_residual for source in sources.values()):
            raise ValueError("B2-feat/1 requires the stored residual")
    parts = {role:source.split() for role,source in sources.items()}
    ex._check_roles(parts)
    for role, source in sources.items():
        if source.kind != "known" or source.role != role or source.groups.tolist() != role_plan[role]:
            raise ValueError("source kind, role or group identity differs from its artifact")
        for group in source.groups:
            labels = source.index["label"][source.index["seed"] == group]
            if sorted(labels.tolist()) != list(range(len(LABELS))):
                raise ValueError("each scenario group must retain all eight paired known variants")
    return role_plan, parts


def _config(raw):
    cfg = ex.B2ExperimentConfig(**raw)
    if fingerprint(cfg.resolved()) != fingerprint(raw):
        raise ValueError("training configuration is not canonical")
    _caps(cfg)
    return cfg


def _files(root, expected):
    if not isinstance(expected, dict) or not expected:
        raise ValueError("empty frozen file inventory")
    for name, digest in expected.items():
        path = root / name
        if (Path(name).name != name or not isinstance(digest, str) or len(digest) != 64
                or not path.is_file() or path.is_symlink() or _sha256(path) != digest):
            raise ValueError(f"missing or modified frozen file/checksum {path}")


def _training_names(config):
    return {"config.json", *[f"model_{v}.pt" for v in config.views],
            *[f"mahalanobis_{v}.npz" for v in config.views]}


def _calibration_names(config):
    return {*[f"alarm_{v}.json" for v in config.views],
            *[f"rejection_{v}_{m}.json" for v in config.views for m in config.methods]}


def _verify_training(root, *, config=None, identity=None):
    root = Path(root)
    value = _marker(root/"training.json", "training", {"config", "data_identity", "roles", "source", "runtime", "provenance", "files", "views"})
    cfg = _config(value["config"])
    if config is not None and fingerprint(config.resolved()) != fingerprint(value["config"]):
        raise ValueError("training configuration differs from the frozen training artifact")
    if identity is not None and identity != value["data_identity"]:
        raise ValueError("training artifact has a different data identity")
    if value["source"]["files_sha256"] != _source_identity()["files_sha256"]:
        raise ValueError("training source provenance differs; historical checkpoints cannot be relabelled")
    if value["runtime"] != _runtime():
        raise ValueError("training runtime differs from frozen provenance")
    roles = value["roles"]
    _role_plan({"roles":{r:{"scenario_seeds":groups} for r,groups in roles.items()}})
    expected = {"protocol":cfg.protocol, "data_fingerprint":value["data_identity"], "roles":roles,
                "source_files_sha256":value["source"]["files_sha256"]}
    if value["provenance"] != expected or set(value["files"]) != _training_names(cfg) or set(value["views"]) != set(cfg.views):
        raise ValueError("incompatible training provenance, views or frozen file inventory")
    _files(root,value["files"])
    if fingerprint(_strict(root/"config.json")) != fingerprint(cfg.resolved()):
        raise ValueError("frozen config file differs from the training marker")
    loaded = {}
    for view in cfg.views:
        fitted = load(root/f"model_{view}.pt", device="cpu", expected_config=cfg.train_config(view), expected_provenance=expected)
        scorer = MahalanobisScorer.load(root/f"mahalanobis_{view}.npz")
        scorer_provenance = fingerprint({"checkpoint_sha256":value["files"][f"model_{view}.pt"], "data":value["data_identity"],
            "groups":roles["train"], "regularization":cfg.mahalanobis_regularization})
        if (scorer.provenance != scorer_provenance or len(scorer.means) != len(LABELS)
                or scorer.regularization != cfg.mahalanobis_regularization
                or scorer.class_counts.tolist() != [len(roles["train"])]*len(LABELS)):
            raise ValueError("Mahalanobis statistics are not bound to this train-only population/checkpoint")
        recorded = value["views"][view]
        if (recorded.get("checkpoint_sha256") != value["files"][f"model_{view}.pt"]
                or recorded.get("selected_epoch") != fitted["best_epoch"]
                or fingerprint(recorded.get("history")) != fingerprint(fitted["history"])
                or fingerprint(recorded.get("train_diagnostics")) != fingerprint(fitted.get("train_diagnostics"))):
            raise ValueError("selected checkpoint/history/diagnostics differ from frozen training metadata")
        loaded[view] = (fitted,scorer)
    return value,cfg,loaded


def fit_b2_models(config, data, out, *, reuse=False, device="cpu", smoke=True, log=print):
    """Fit weights/select checkpoints and train-derived statistics, without calibration or test reads."""
    _cpu(device,smoke);_caps(config)
    out = Path(out)
    _separate(out,[data])
    _preflight_known(data)
    manifest,identity,sources = open_b2_known_roles(data,("train","val-select"))
    roles,parts = _data(config,manifest,sources,("train","val-select"))
    if out.exists() and any(out.iterdir()):
        if not reuse:
            raise ValueError("refusing nonempty training output; use verified reuse or a fresh directory")
        result,_,_ = _verify_training(out,config=config,identity=identity)
        if result["roles"] != roles:
            raise ValueError("training role identity differs")
        return result
    source,runtime = _source_identity(),_runtime()
    provenance = {"protocol":config.protocol,"data_fingerprint":identity,"roles":roles,
                  "source_files_sha256":source["files_sha256"]}
    out.mkdir(parents=True,exist_ok=True)
    _write_json(out/"config.json",config.resolved())
    views = {}
    for view in config.views:
        fitted = fit_streaming(sources["train"],sources["val-select"],config.train_config(view),
                               window_shards=config.window_shards,device="cpu",log=log)
        fitted.update(provenance=provenance,source_revision=source["revision"])
        save(fitted,out/f"model_{view}.pt")
        checkpoint_sha = _sha256(out/f"model_{view}.pt")
        fitted = load(out/f"model_{view}.pt",device="cpu",expected_config=config.train_config(view),expected_provenance=provenance)
        outputs = infer_streaming(fitted,sources["train"])
        scorer_provenance = fingerprint({"checkpoint_sha256":checkpoint_sha,"data":identity,"groups":roles["train"],
                                        "regularization":config.mahalanobis_regularization})
        scorer = fit_mahalanobis(outputs["embedding"],parts["train"]["label"],len(LABELS),
                                config.mahalanobis_regularization,provenance=scorer_provenance)
        scorer.save(out/f"mahalanobis_{view}.npz")
        views[view] = {"checkpoint_sha256":checkpoint_sha,"selected_epoch":fitted["best_epoch"],
                       "selection":"val-select macro-F1, strict improvement; first maximum",
                       "history":fitted["history"],"train_diagnostics":fitted.get("train_diagnostics")}
    if source["files_sha256"] != _source_identity()["files_sha256"] or runtime != _runtime():
        raise ValueError("source/runtime changed during fitting; partial output is not a complete artifact")
    return _commit(out/"training.json","training",{"config":config.resolved(),"data_identity":identity,"roles":roles,
        "source":source,"runtime":runtime,"provenance":provenance,"views":views,
        "files":{name:_sha256(out/name) for name in sorted(_training_names(config))}})


def calibrate_b2_models(data, runs, *, reuse=False, device="cpu", log=print):
    """Read known val-calib only and freeze thresholds without fitting a model or train statistics."""
    _cpu(device);runs=Path(runs)
    _separate(runs,[data])
    trained,config,loaded = _verify_training(runs)
    _preflight_known(data)
    manifest,identity,sources = open_b2_known_roles(data,("val-calib",))
    roles,parts = _data(config,manifest,sources,("val-calib",))
    if identity != trained["data_identity"] or roles != trained["roles"]:
        raise ValueError("calibration data/role identity differs from frozen training")
    marker = runs/"calibration.json"
    if marker.exists():
        if not reuse:
            raise ValueError("calibration already exists; use verified reuse")
        result,_,_,_ = _verify_calibration(runs)
        return result
    if any((runs/name).exists() or (runs/name).with_suffix((runs/name).suffix+".tmp").exists()
           for name in _calibration_names(config)):
        raise ValueError("incomplete calibration output; use a fresh training bundle")
    calibrations = {}
    clean = parts["val-calib"]["label"] == 0
    if not clean.any():
        raise ValueError("clean known-only val-calib population is empty")
    for view,(fitted,scorer) in loaded.items():
        outputs = infer_streaming(fitted,sources["val-calib"])
        probabilities = ex._softmax(outputs["logits"])
        scores = 1.-probabilities[:,0]
        threshold = threshold_at_pfa(scores[clean],config.pfa)
        alarm = {"score":"one_minus_softmax_clean","direction":"higher_is_more_anomalous",
                 "threshold":float(threshold),"target_clean_pfa":config.pfa,"rule":ALARM_RULE,
                 "population":"clean-only known val-calib","n_clean_calibration":int(clean.sum()),
                 "calibration_false_alarms":int((scores[clean]>threshold).sum()),
                 "calibration_role":"val-calib","calibration_groups":roles["val-calib"]}
        _write_json(runs/f"alarm_{view}.json",alarm)
        rejections = {}
        for method in config.methods:
            values = scorer.score(outputs["embedding"]) if method=="mahalanobis" else unknown_scores(outputs["logits"],method)
            provenance = fingerprint({"checkpoint_sha256":trained["files"][f"model_{view}.pt"],"data":identity,"method":method,
                                     "groups":roles["val-calib"],"target_acceptance":config.target_acceptance})
            rejection = calibrate_scores(values,method,config.target_acceptance,provenance=provenance)
            rejection.save(runs/f"rejection_{view}_{method}.json")
            rejections[method] = rejection.to_dict()
        calibrations[view] = {"alarm":alarm,"rejection":rejections}
    _verify_training(runs,config=config,identity=identity)
    log("calibration frozen from known-only val-calib; no test source opened")
    return _commit(marker,"calibration",{"training_sha256":_sha256(runs/"training.json"),"data_identity":identity,
        "calibration_groups":roles["val-calib"],"n_calibration":len(sources["val-calib"]),"views":calibrations,
        "files":{name:_sha256(runs/name) for name in sorted(_calibration_names(config))}})


def _verify_calibration(root):
    root=Path(root);trained,config,loaded=_verify_training(root)
    value=_marker(root/"calibration.json","calibration",{"training_sha256","data_identity","calibration_groups","n_calibration","views","files"})
    if (value["training_sha256"] != _sha256(root/"training.json") or value["data_identity"] != trained["data_identity"]
            or value["calibration_groups"] != trained["roles"]["val-calib"]
            or value["n_calibration"] != len(trained["roles"]["val-calib"])*len(LABELS)
            or set(value["views"]) != set(config.views) or set(value["files"]) != _calibration_names(config)):
        raise ValueError("incompatible calibration population, training binding or file inventory")
    _files(root,value["files"])
    for view in config.views:
        item=value["views"][view]
        alarm=_strict(root/f"alarm_{view}.json")
        fields={"score","direction","threshold","target_clean_pfa","rule","population","n_clean_calibration",
                "calibration_false_alarms","calibration_role","calibration_groups"}
        if (set(alarm)!=fields or alarm!=item["alarm"] or alarm["population"]!="clean-only known val-calib"
                or alarm["calibration_role"]!="val-calib" or alarm["calibration_groups"]!=value["calibration_groups"]
                or type(alarm["n_clean_calibration"]) is not int or alarm["n_clean_calibration"]!=len(value["calibration_groups"])
                or alarm["target_clean_pfa"]!=config.pfa or not np.isfinite(alarm["threshold"])
                or not 0<=alarm["threshold"]<=1 or alarm["score"]!="one_minus_softmax_clean"
                or alarm["direction"]!="higher_is_more_anomalous" or alarm["rule"]!=ALARM_RULE
                or type(alarm["calibration_false_alarms"]) is not int
                or not 0<=alarm["calibration_false_alarms"]<=alarm["n_clean_calibration"]):
            raise ValueError("invalid clean calibration identity/threshold")
        if set(item["rejection"]) != set(config.methods):
            raise ValueError("missing rejection calibration methods")
        for method in config.methods:
            calibration=RejectionCalibration.from_dict(_strict(root/f"rejection_{view}_{method}.json"))
            expected=fingerprint({"checkpoint_sha256":trained["files"][f"model_{view}.pt"],"data":trained["data_identity"],"method":method,
                "groups":trained["roles"]["val-calib"],"target_acceptance":config.target_acceptance})
            if (calibration.to_dict()!=item["rejection"][method] or calibration.provenance!=expected
                    or calibration.n_calibration!=value["n_calibration"] or calibration.target_acceptance!=config.target_acceptance):
                raise ValueError("rejection calibration is not bound to this known val-calib population/checkpoint")
    return value,trained,config,loaded


def _profile(profile,seeds):
    if profile not in PROFILES:
        raise ValueError(f"profile must be one of {PROFILES}")
    if (not isinstance(seeds,(list,tuple)) or not seeds or any(type(v) is not int or v<0 for v in seeds)
            or len(set(seeds))!=len(seeds) or (profile=="proposed-full" and len(seeds)!=3)):
        raise ValueError("inventory requires explicit distinct seeds; proposed-full requires three seeds")
    return list(seeds)


def _base_config(config):
    value=config.resolved();value.pop("views");value["training"].pop("seed")
    return json.loads(json.dumps(value,allow_nan=False))


def _separate(out,inputs):
    out=Path(out).resolve()
    for item in inputs:
        path=Path(item).resolve()
        if out==path or out in path.parents or path in out.parents:
            raise ValueError("output must be separate from read-only input bundles/inventory; overlapping paths refused")


def freeze_inventory(runs_list,out,*,seeds=(0,1,2),profile="proposed-full"):
    """Commit a verified complete nine-cell roster, or an explicitly labelled small fixture roster."""
    seeds=_profile(profile,seeds);out=Path(out)
    if not isinstance(runs_list,(list,tuple)) or not runs_list:
        raise ValueError("inventory needs calibrated training bundles")
    roots=[Path(root).resolve() for root in runs_list]
    if len(set(roots))!=len(roots):
        raise ValueError("duplicate training bundle/seed in inventory")
    _separate(out,roots)
    if out.exists():
        raise ValueError("inventory already exists; never overwrite a frozen roster")
    cells=[];reference=None;keys=set()
    for root in roots:
        calibrated,trained,config,_=_verify_calibration(root)
        common={"config":_base_config(config),"data_identity":trained["data_identity"],"roles":trained["roles"],
                "source":trained["source"]["files_sha256"],"runtime":trained["runtime"]}
        if reference is None:reference=common
        if common!=reference:raise ValueError("inventory mixes incompatible data, source, runtime or base configuration")
        seed=config.train_config(config.views[0]).seed
        if seed not in seeds:raise ValueError("bundle seed is not in the declared inventory seed roster")
        for view in config.views:
            if (seed,view) in keys:raise ValueError("duplicate seed/view inventory cell")
            keys.add((seed,view))
            cells.append({"seed":seed,"view":view,"runs":str(root),"training_sha256":_sha256(root/"training.json"),
                          "calibration_sha256":_sha256(root/"calibration.json"),"training_id":trained["artifact_id"],
                          "calibration_id":calibrated["artifact_id"]})
    required={(seed,view) for seed in seeds for view in VIEWS}
    if profile=="proposed-full" and keys!=required:
        raise ValueError("proposed-full inventory must contain all nine cells: three views x three seeds")
    if profile=="fixture" and (len(keys)>9 or {s for s,_ in keys}!=set(seeds)):
        raise ValueError("fixture inventory is incomplete for its declared seeds or exceeds nine cells")
    out.parent.mkdir(parents=True,exist_ok=True)
    return _commit(out,"inventory",{"profile":profile,"seeds":seeds,"cells":sorted(cells,key=lambda x:(x["seed"],x["view"])),
        "common":reference,"full_protocol_admission":profile=="proposed-full","production_authorized":False})


def _load_inventory(path,profile):
    inventory=_marker(path,"inventory",{"profile","seeds","cells","common","full_protocol_admission","production_authorized"})
    if inventory["profile"]!=profile or inventory["production_authorized"] is not False:
        raise ValueError("evaluation profile differs from frozen inventory")
    seeds=_profile(profile,inventory["seeds"]);cells=inventory["cells"]
    if not isinstance(cells,list) or not cells:
        raise ValueError("empty inventory")
    required={(s,v) for s in seeds for v in VIEWS};seen=set();loaded=[];bundles={}
    # Every cell is validated before any held-out source is opened.
    for cell in cells:
        if set(cell)!={"seed","view","runs","training_sha256","calibration_sha256","training_id","calibration_id"}:
            raise ValueError("invalid inventory cell schema")
        key=(cell["seed"],cell["view"])
        if key in seen or key not in required:raise ValueError("duplicate or foreign seed/view inventory cell")
        seen.add(key);root=Path(cell["runs"]).resolve()
        if root not in bundles:bundles[root]=_verify_calibration(root)
        calibrated,trained,config,views=bundles[root]
        common={"config":_base_config(config),"data_identity":trained["data_identity"],"roles":trained["roles"],
                "source":trained["source"]["files_sha256"],"runtime":trained["runtime"]}
        if (cell["seed"]!=config.train_config(config.views[0]).seed or cell["view"] not in views or common!=inventory["common"]
                or cell["training_id"]!=trained["artifact_id"] or cell["calibration_id"]!=calibrated["artifact_id"]
                or cell["training_sha256"]!=_sha256(root/"training.json") or cell["calibration_sha256"]!=_sha256(root/"calibration.json")):
            raise ValueError("inventory cell checkpoint/configuration/provenance hash mismatch")
        loaded.append((cell,trained,config,views[cell["view"]],calibrated["views"][cell["view"]]))
    if profile=="proposed-full" and (seen!=required or len(cells)!=9 or inventory["full_protocol_admission"] is not True):
        raise ValueError("evaluation requires the complete nine-cell inventory")
    if profile=="fixture" and (len(cells)>9 or inventory["full_protocol_admission"] is not False or {s for s,_ in seen}!=set(seeds)):
        raise ValueError("fixture inventory cannot claim full-protocol admission")
    return inventory,loaded,bundles


def _rejection_metrics(calibration,scores,labels,predictions,groups,families):
    accepted=calibration.accept(scores)
    out={"calibration":calibration.to_dict(),"known_acceptance":ex._rate(accepted,groups),
         "accepted_known_accuracy":ex._rate((predictions==labels)[accepted],groups[accepted]),
         "per_class_acceptance":{label:ex._rate(accepted[labels==i],groups[labels==i]) for i,label in enumerate(LABELS)},
         "unknown_rejection":None,"n_unknown":0,"families":None,"note":"no unknown or benign test-only families were supplied"}
    if families is not None:out.update(ex._family_metrics(calibration.method,calibration,scores,labels,predictions,families))
    return out


def _evaluation_artifact(stage,manifest,identity,source):
    """Persist the exact evaluated population, including optional artifact identities."""
    index_name="family" if source.kind=="test" else "label"
    record={"stage":stage,"protocol":manifest.get("protocol"),"data_identity":identity,
        "manifest_sha256":fingerprint(manifest),"request_fingerprint":manifest.get("request_fingerprint"),
        "generator_source_sha256":manifest.get("request",{}).get("source_sha256"),
        "generation_config":manifest.get("config"),"cancellation":manifest.get("cancellation"),
        "receiver_calibration":manifest.get("calibration"),"role":source.role,
        "n_samples":len(source),"scenario_ids":source.groups.tolist(),"index_name":index_name,
        "sample_ids":[[int(group),int(label)] for group,label in zip(source.index["seed"],source.index[index_name])]}
    # Keep the opening snapshot independent of mutable manifest dictionaries.
    return json.loads(json.dumps(record,allow_nan=False))


def evaluate_b2_inventory(data,inventory,out,*,unknown_data=None,matched_data=None,profile="proposed-full",log=print):
    """Read-only frozen-input evaluation; all admission checks precede test opening/inference."""
    out=Path(out);inventory_path=Path(inventory).resolve()
    frozen,loaded,bundles=_load_inventory(inventory_path,profile)
    _separate(out,[*bundles,inventory_path,data,
                   *[root for root in (unknown_data,matched_data) if root is not None]])
    if out.exists() and any(out.iterdir()):raise ValueError("refusing nonempty evaluation output")
    inventory_hash=_sha256(inventory_path)
    first=loaded[0];config=first[2]
    _preflight_known(data)
    manifest,identity,sources=open_b2_known_roles(data,("test",))
    roles,parts=_data(config,manifest,sources,("test",))
    if identity!=frozen["common"]["data_identity"] or roles!=frozen["common"]["roles"]:
        raise ValueError("test artifact/group identity differs from the frozen inventory")
    evaluation_artifacts={"known":_evaluation_artifact("known",manifest,identity,sources["test"]),
                          "test_only":None,"matched":None}
    unknown=unknown_source=matched=matched_source=None
    if unknown_data is not None:
        _preflight_optional(unknown_data,"test_only")
        unknown_manifest,unknown_identity,unknown_source=ex._load_unknown(unknown_data,manifest,identity,config)
        if not set(unknown_source.groups.tolist())<=set(roles["test"]):raise ValueError("test-only group leakage")
        unknown=unknown_source.split()
        evaluation_artifacts["test_only"]=_evaluation_artifact("test_only",unknown_manifest,unknown_identity,unknown_source)
    if matched_data is not None:
        _preflight_optional(matched_data,"matched")
        matched_manifest,matched_identity,matched_source=ex._load_matched(matched_data,manifest,identity,config)
        if len(matched_source.groups)>CAPS["groups_per_role"]:raise ValueError("matched population exceeds bounded group cap")
        matched=matched_source.split()
        evaluation_artifacts["matched"]=_evaluation_artifact("matched",matched_manifest,matched_identity,matched_source)
    labels,groups=parts["test"]["label"].astype(np.int64),parts["test"]["seed"]
    models=[];predictions_json=[]
    for cell,trained,cfg,(fitted,scorer),calibrated in loaded:
        values=infer_streaming(fitted,sources["test"])
        unknown_out=infer_streaming(fitted,unknown_source) if unknown_source is not None else None
        matched_out=infer_streaming(fitted,matched_source) if matched_source is not None else None
        probabilities=ex._softmax(values["logits"]);prediction=values["logits"].argmax(1)
        event=1.-probabilities[:,0];threshold=calibrated["alarm"]["threshold"];alarm=event>threshold;clean=labels==0
        calibrations={m:RejectionCalibration.from_dict(c) for m,c in calibrated["rejection"].items()}
        rejection={};scores={}
        for method,calibration in calibrations.items():
            scores[method]=scorer.score(values["embedding"]) if method=="mahalanobis" else unknown_scores(values["logits"],method)
            families=None
            if unknown_out is not None:
                unknown_values=scorer.score(unknown_out["embedding"]) if method=="mahalanobis" else unknown_scores(unknown_out["logits"],method)
                families={"scores":unknown_values,"groups":unknown["seed"],"info":ex._unknown_families(unknown),
                          "predictions":unknown_out["logits"].argmax(1)}
            rejection[method]=_rejection_metrics(calibration,scores[method],labels,prediction,groups,families)
        metrics={"accuracy":ex._rate(prediction==labels,groups),"macro_f1":macro_f1(labels,prediction,len(LABELS)),
            "confusion":confusion(labels,prediction,len(LABELS)).tolist(),"ece":expected_calibration_error(probabilities,labels,15),
            "per_class_recall":{name:ex._rate((prediction==labels)[labels==i],groups[labels==i]) for i,name in enumerate(LABELS)},
            "clean_false_alarm":ex._rate(alarm[clean],groups[clean]),"event_detection":ex._rate(alarm[~clean],groups[~clean]),
            "alarm":calibrated["alarm"],"rejection":rejection,"plan_consistency":ex._plan_metrics(values["plan_logits"],parts["test"]["plan_consistency"],groups),
            "matched":None if matched_out is None else ex._matched_metrics(matched,matched_out,calibrations,scorer,threshold,parts["test"],prediction)}
        models.append({"seed":cell["seed"],"view":cell["view"],"checkpoint_sha256":trained["files"][f"model_{cell['view']}.pt"],"metrics":metrics})
        predictions_json.append({"seed":cell["seed"],"view":cell["view"],"sample_ids":[[int(g),int(l)] for g,l in zip(groups,labels)],
            "prediction":prediction.tolist(),"event_probability":event.tolist(),"alarm":alarm.tolist(),
            "unknown_scores":{m:s.tolist() for m,s in scores.items()}})
    if _sha256(inventory_path)!=inventory_hash:raise ValueError("inventory changed during evaluation")
    for root in bundles:_verify_calibration(root)  # catches changed inputs; never modifies them
    # The optional legacy readers validate their current manifest on each pass.
    # Re-verify all opening identities after inference, before publishing ANY
    # result, so a consistently re-signed same-index artifact drift is refused.
    end_manifest,end_identity,end_sources=open_b2_known_roles(data,("test",))
    actual={"known":_evaluation_artifact("known",end_manifest,end_identity,end_sources["test"]),
            "test_only":None,"matched":None}
    for stage,path,opener in (("test_only",unknown_data,ex._load_unknown),("matched",matched_data,ex._load_matched)):
        if path is not None:
            final_manifest,final_identity,final_source=opener(path,end_manifest,end_identity,config)
            actual[stage]=_evaluation_artifact(stage,final_manifest,final_identity,final_source)
    if actual!=evaluation_artifacts:
        raise ValueError("evaluation artifact identity changed during inference; no result may be published")
    out.mkdir(parents=True,exist_ok=True)
    _write_json(out/"predictions.json",predictions_json)
    result={"contract":CONTRACT,"benchmark_complete":False,"scope":"BOUNDED_FIXTURE","profile":profile,
        "inventory_sha256":inventory_hash,"inventory_cells":len(loaded),"full_protocol_admission":profile=="proposed-full",
        "production_authorized":False,"data_identity":identity,"source":_source_identity(),"runtime":_runtime(),
        "partitions":ex._summary(parts),"evaluation_artifacts":evaluation_artifacts,"models":models,
        "limitations":["Bounded stand-in/pilot execution is not recognition performance or a completed benchmark.",
                       "No fitting, checkpoint selection, statistic fitting or threshold calibration occurs during evaluation.",
                       "Per-model metrics stay separate; scores from independently fitted seeds are never pooled."]}
    _write_json(out/"results.json",result)
    _write_json(out/"completion.json",{"results_sha256":_sha256(out/"results.json"),"predictions_sha256":_sha256(out/"predictions.json"),
                                     "inventory_sha256":inventory_hash,"evaluation_artifacts":evaluation_artifacts,
                                     "evaluation_artifacts_sha256":fingerprint(evaluation_artifacts),"benchmark_complete":False})
    log("frozen inventory evaluated; training/calibration inputs remained read-only")
    return result

"""Production artifact/device adapter over the existing B2 numerical kernels.

This module does not widen E7b fixture limits. Real execution requires a host
integration port with ``require(action, request_identity)``; absence denies before
observation or CUDA access. E17's DR-04 authority is not a DR-05 training authority.
No production held-out reader exists here. The separately named development
exercise always delegates to the existing bounded CPU executor.
"""
from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import subprocess
import uuid

import numpy as np
import torch

from geosim.b2_protocol import FEATURE_PROTOCOL, LABELS, ROLE_COUNTS, scenario_ids
from geosim.cancellation import CancellationConfig
from . import b2_execution as bounded
from . import b2_e9_contract as e9
from .b2_experiment import B2ExperimentConfig, METHODS, VIEWS, _check_roles, _softmax
from .b2_stream import fit_streaming, infer_streaming, open_b2_known_roles
from .artifacts import fingerprint
from .calibration import RejectionCalibration, calibrate_scores
from .experiment import _sha256, _source_identity, _write_json
from .mahalanobis import MahalanobisScorer, fit_mahalanobis
from .metrics import clean_alarm_threshold
from .train import load, save

CONTRACT = "B2-production-training/1"
R6_PROFILE = "B2-R6-fp32-tf32-off/1"
PROFILES = {"proposed-full": VIEWS, "c2-h3-dual": ("dual_planmask", "dual_noplan")}


class AuthorizationRequired(PermissionError):
    pass


def _require(authorization, action, identity):
    if authorization is None or not callable(getattr(authorization, "require", None)):
        raise AuthorizationRequired(f"separate {action} authorization and host integration required")
    # This port must verify real authority, scope, expiry/revocation and the exact
    # source/environment/data lock; a readiness report is not such a port.
    authorization.require(action, identity)


def production_config(views=VIEWS, seed=0):
    """Explicit approved recipe; no caller-selected epochs, width or batch fallback."""
    views = tuple(views)
    if type(seed) is not int or seed not in (0, 1, 2):
        raise ValueError("production seed must be 0, 1 or 2")
    canonical = all(v in VIEWS for v in views)
    matched = all(v in PROFILES["c2-h3-dual"] for v in views)
    if not views or not (canonical or matched):
        raise ValueError("choose canonical views or the required matched dual pair")
    return B2ExperimentConfig(views=views, methods=METHODS, plan_consistency=canonical,
        target_acceptance=.95, pfa=.05, mahalanobis_regularization=.1, window_shards=4,
        training={"epochs":30, "width":16, "time_pool":2, "batch":32, "seed":seed,
            "level":"carrier" if canonical else "absolute", "lr":1e-3, "weight_decay":1e-4,
            "augment":True, "center_loss_weight":.005, "plan_loss_weight":1.,
            "plan_shift_fraction":.15 if canonical else 0., "plan_shift_max_hz":.5e6})


def _config(raw):
    cfg = B2ExperimentConfig(**raw)
    expected = production_config(cfg.views, cfg.train_config(cfg.views[0]).seed)
    if fingerprint(cfg.resolved()) != fingerprint(expected.resolved()):
        raise ValueError("configuration differs from the approved production recipe")
    return cfg


@contextmanager
def r6_fp32():
    """Enforce the approved effective settings around unchanged training/inference."""
    previous = (torch.backends.cudnn.allow_tf32, torch.backends.cuda.matmul.allow_tf32,
                torch.are_deterministic_algorithms_enabled(), torch.get_default_dtype())
    if torch.get_default_dtype() != torch.float32:
        raise ValueError("R6 requires the FP32 default dtype")
    try:
        torch.backends.cudnn.allow_tf32 = False
        torch.backends.cuda.matmul.allow_tf32 = False
        torch.use_deterministic_algorithms(False)
        # Both contexts are disabled; neither probes or allocates a CUDA device.
        with torch.autocast("cpu", enabled=False), torch.autocast("cuda", enabled=False):
            yield
    finally:
        torch.backends.cudnn.allow_tf32, torch.backends.cuda.matmul.allow_tf32 = previous[:2]
        torch.use_deterministic_algorithms(previous[2])


def runtime_identity(device):
    """Call for CUDA only *after* the separate GPU authorization check."""
    if device != "cpu" and not (isinstance(device, str) and (device == "cuda" or device.startswith("cuda:"))):
        raise ValueError("device must be cpu or an explicit CUDA device")
    if (torch.backends.cudnn.allow_tf32 or torch.backends.cuda.matmul.allow_tf32
            or torch.are_deterministic_algorithms_enabled() or torch.get_default_dtype() != torch.float32
            or torch.is_autocast_enabled() or torch.is_autocast_enabled("cpu")):
        raise ValueError("effective runtime violates R6")
    runtime = {**bounded._runtime(), "device":device, "profile":R6_PROFILE,
        "precision":"fp32", "autocast":False, "cudnn_allow_tf32":False, "matmul_allow_tf32":False,
        "cuda":None, "cudnn":None, "gpu":None, "driver":None}
    if device != "cpu":
        index = torch.device(device).index
        index = torch.cuda.current_device() if index is None else index
        prop = torch.cuda.get_device_properties(index)
        # nvidia-smi supplies the driver identity torch does not expose. Fail if
        # unavailable rather than recording an invented/unpinned driver.
        driver = subprocess.run(["nvidia-smi", f"--id={index}", "--query-gpu=driver_version,uuid",
            "--format=csv,noheader,nounits"], check=True, capture_output=True, text=True).stdout.strip()
        if len(driver.splitlines()) != 1 or "," not in driver:
            raise ValueError("GPU driver/UUID identity unavailable")
        runtime.update(cuda=torch.version.cuda, cudnn=torch.backends.cudnn.version(),
            gpu={"index":index,"name":prop.name,"total_memory":prop.total_memory},driver=driver)
    return runtime


def _role_plan(manifest):
    roles = manifest.get("roles", {})
    if set(roles) != set(bounded.ROLES):
        raise ValueError("all canonical role metadata is required")
    result = {r:roles[r]["scenario_seeds"] for r in bounded.ROLES}
    if any(result[r] != scenario_ids(r) for r in bounded.ROLES):
        raise ValueError("production role populations must match the frozen canonical groups")
    if (manifest.get("protocol") != FEATURE_PROTOCOL or manifest.get("labels") != list(LABELS)
            or manifest.get("benchmark_complete") is not False
            or manifest.get("cancellation") != CancellationConfig().to_dict()
            or manifest.get("request", {}).get("groups_per_shard") != 4):
        raise ValueError("production data protocol/cancellation/R7 shard policy differs")
    return result


def _open(data, requested, expected_identity=None):
    # Header checks precede any role observation read. The scoped reader never
    # opens test observations while fitting or calibrating.
    manifest, _ = bounded._known_header(Path(data))
    roles = _role_plan(manifest)
    if expected_identity is not None and fingerprint(manifest) != expected_identity:
        raise ValueError("data metadata differs from the authorized request")
    manifest, identity, sources = open_b2_known_roles(data, requested)
    if (expected_identity is not None and identity != expected_identity) or roles != _role_plan(manifest):
        raise ValueError("data metadata changed while opening roles")
    parts = {r:s.split() for r,s in sources.items()}
    _check_roles(parts)
    for role, source in sources.items():
        if (source.kind != "known" or source.role != role or source.groups.tolist() != roles[role]
                or not source.has_residual or len(source) != ROLE_COUNTS[role]*len(LABELS)):
            raise ValueError("role-scoped source differs from production metadata")
        for group in source.groups:
            labels = source.index["label"][source.index["seed"] == group]
            if sorted(labels.tolist()) != list(range(len(LABELS))):
                raise ValueError("each production scenario must retain all eight known variants")
    return identity, roles, sources, parts


def _sync(root):
    """Durable payloads before marker acceptance; no asynchronous artifact queue."""
    for path in Path(root).iterdir():
        if path.is_symlink() or not path.is_file():
            raise ValueError("artifact bundle must contain regular files only")
        with path.open("rb") as stream:
            os.fsync(stream.fileno())
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _commit(root, phase, payload):
    root = Path(root)
    _sync(root)
    value = {"contract":CONTRACT,"phase":phase,"scope":"PRODUCTION","benchmark_complete":False, **payload}
    value["artifact_id"] = fingerprint(value)
    _write_json(root/f"{phase}.json", value)
    _sync(root)
    return value


def _marker(root, phase):
    value = bounded._strict(Path(root)/f"{phase}.json")
    if (value.get("contract") != CONTRACT or value.get("phase") != phase or value.get("scope") != "PRODUCTION"
            or value.get("benchmark_complete") is not False
            or value.get("artifact_id") != fingerprint({k:v for k,v in value.items() if k != "artifact_id"})):
        raise ValueError("invalid production artifact marker; fixtures cannot be relabelled")
    return value


def _request(phase, data, out, config=None, environment_lock=None, data_identity=None):
    manifest,_ = bounded._known_header(Path(data))
    if data_identity is not None and fingerprint(manifest) != data_identity:
        raise ValueError("data metadata changed before authorization")
    return fingerprint({"phase":phase,"data":str(Path(data).resolve()),"out":str(Path(out).resolve()),
        "config":None if config is None else config.resolved(),"source":_source_identity(),
        "data_identity":fingerprint(manifest),"environment_lock":environment_lock})


def _canonical_training_gate():
    repo = Path(__file__).resolve().parents[2]
    gates = bounded._strict(repo/"docs/plan/b2_readiness_gates_2026-10-21.json")
    memo = bounded._strict(repo/"docs/plan/b2_e5_decision_recommendations.json")
    status = e9.authorization_status("full_training",gates)
    if status["status"] != "APPROVAL_RECORDED_NOT_RUNNABLE" or e9.memo_twin_problems(gates,memo):
        raise AuthorizationRequired("canonical full_gpu_training gate CLOSED; separate DR-05 approval required")


def fit_models(data, out, *, views=VIEWS, seed=0, device="cpu", environment_lock=None, authorization=None, log=print):
    """Run one fresh approved view/seed bundle; incomplete fits restart in a new directory."""
    _canonical_training_gate()
    cfg = production_config(views, seed)
    if not isinstance(environment_lock,dict) or environment_lock.get("device") != device:
        raise ValueError("explicit pinned environment lock required before authorization")
    data_identity = fingerprint(bounded._known_header(Path(data))[0])
    request = _request("training", data, out, cfg,environment_lock,data_identity)
    _require(authorization, "training", request)
    if device != "cpu":
        _require(authorization, "gpu_qualification", request)
        _require(authorization, "gpu_training", request)
    out = Path(out)
    bounded._separate(out, [data])
    if out.exists():
        raise ValueError("fresh attempt directory required; no partial-state reuse")
    with r6_fp32():
        runtime, source = runtime_identity(device), _source_identity()
        if runtime != environment_lock:
            raise ValueError("actual device/runtime differs from the authorized environment lock")
        identity, roles, sources, parts = _open(data, ("train", "val-select"),data_identity)
        provenance = {"protocol":cfg.protocol,"data_fingerprint":identity,"roles":roles,
            "source_files_sha256":source["files_sha256"],"runtime_identity":fingerprint(runtime),"scope":"PRODUCTION"}
        out.mkdir(parents=True)
        attempt = uuid.uuid4().hex
        _write_json(out/"attempt.json", {"attempt_id":attempt,"status":"INCOMPLETE","request_identity":request})
        _write_json(out/"config.json", cfg.resolved())
        _sync(out)
        records = {}
        for view in cfg.views:
            fitted = fit_streaming(sources["train"], sources["val-select"], cfg.train_config(view),
                window_shards=cfg.window_shards, device=device, log=log)
            fitted.update(provenance=provenance, source_revision=source["revision"])
            save(fitted, out/f"model_{view}.pt")
            checkpoint = _sha256(out/f"model_{view}.pt")
            outputs = infer_streaming(fitted, sources["train"])
            scorer_id = fingerprint({"checkpoint_sha256":checkpoint,"data":identity,"groups":roles["train"],"regularization":.1})
            scorer = fit_mahalanobis(outputs["embedding"], parts["train"]["label"],len(LABELS),.1,provenance=scorer_id)
            scorer.save(out/f"mahalanobis_{view}.npz")
            records[view] = {"checkpoint_sha256":checkpoint,"selected_epoch":fitted["best_epoch"],
                "history":fitted["history"],"train_diagnostics":fitted.get("train_diagnostics"),"streaming":fitted["streaming"]}
        if runtime != runtime_identity(device) or source != _source_identity():
            raise ValueError("source/runtime changed during training; attempt remains INCOMPLETE")
        return _commit(out,"training",{"config":cfg.resolved(),"data_identity":identity,"roles":roles,"source":source,
            "runtime":runtime,"provenance":provenance,"views":records,"attempt_id":attempt,"status":"COMPLETE",
            "files":{name:_sha256(out/name) for name in sorted(bounded._training_names(cfg))}})


def _training(root, device="cpu"):
    root = Path(root)
    trained = _marker(root,"training")
    cfg = _config(trained["config"])
    if trained["source"]["files_sha256"] != _source_identity()["files_sha256"]:
        raise ValueError("source changed; historical checkpoints cannot be relabelled")
    roles = trained["roles"]
    if any(roles[r] != scenario_ids(r) for r in bounded.ROLES):
        raise ValueError("training role identity differs from canonical population")
    expected = {"protocol":cfg.protocol,"data_fingerprint":trained["data_identity"],"roles":roles,
        "source_files_sha256":trained["source"]["files_sha256"],"runtime_identity":fingerprint(trained["runtime"]),"scope":"PRODUCTION"}
    if (trained["status"] != "COMPLETE" or trained["provenance"] != expected or set(trained["files"]) != bounded._training_names(cfg)
            or set(trained["views"]) != set(cfg.views) or fingerprint(bounded._strict(root/"config.json")) != fingerprint(cfg.resolved())):
        raise ValueError("incomplete production training provenance/files/config")
    bounded._files(root,trained["files"])
    loaded = {}
    for view in cfg.views:
        fitted = load(root/f"model_{view}.pt",device=device,expected_config=cfg.train_config(view),expected_provenance=expected)
        scorer = MahalanobisScorer.load(root/f"mahalanobis_{view}.npz")
        scorer_id = fingerprint({"checkpoint_sha256":trained["files"][f"model_{view}.pt"],"data":trained["data_identity"],
            "groups":roles["train"],"regularization":.1})
        record = trained["views"][view]
        if (scorer.provenance != scorer_id or scorer.regularization != .1 or scorer.class_counts.tolist() != [ROLE_COUNTS["train"]]*len(LABELS)
                or record["selected_epoch"] != fitted["best_epoch"] or record["history"] != fitted["history"]
                or record["streaming"] != fitted["streaming"] or record["train_diagnostics"] != fitted.get("train_diagnostics")
                or len(fitted["history"]) != 30):
            raise ValueError("production checkpoint/scorer/history differs")
        loaded[view] = fitted,scorer
    return trained,cfg,loaded


def calibrate_models(data, runs, *, device="cpu", authorization=None, log=print):
    _canonical_training_gate()
    trained_marker = _marker(runs,"training")
    request = _request("calibration",data,runs,environment_lock=trained_marker["runtime"],data_identity=trained_marker["data_identity"])
    _require(authorization,"training",request)
    if device != "cpu":
        _require(authorization,"gpu_qualification",request)
        _require(authorization,"gpu_training",request)
    runs = Path(runs)
    bounded._separate(runs,[data])
    if (runs/"calibration.json").exists():
        raise ValueError("calibration is already frozen")
    with r6_fp32():
        trained,cfg,loaded = _training(runs,device)
        if trained["runtime"] != runtime_identity(device):
            raise ValueError("calibration runtime differs from training lock")
        identity,roles,sources,parts = _open(data,("val-calib",),trained["data_identity"])
        if identity != trained["data_identity"] or roles != trained["roles"]:
            raise ValueError("calibration data differs from training lock")
        if any((runs/name).exists() for name in bounded._calibration_names(cfg)):
            raise ValueError("partial calibration exists; a new attempt is required")
        records = {}
        clean = parts["val-calib"]["label"] == 0
        for view,(fitted,scorer) in loaded.items():
            outputs = infer_streaming(fitted,sources["val-calib"])
            scores = bounded.clean_alarm_score(_softmax(outputs["logits"]))
            alarm = {"threshold":float(clean_alarm_threshold(scores[clean],cfg.pfa)),"target_clean_pfa":cfg.pfa,
                "rule":bounded.ALARM_RULE,"n_clean_calibration":int(clean.sum()),"calibration_groups":roles["val-calib"]}
            _write_json(runs/f"alarm_{view}.json",alarm)
            rejections = {}
            for method in cfg.methods:
                values = scorer.score(outputs["embedding"]) if method == "mahalanobis" else bounded.unknown_scores(outputs["logits"],method)
                provenance = fingerprint({"checkpoint_sha256":trained["files"][f"model_{view}.pt"],"data":identity,
                    "method":method,"groups":roles["val-calib"],"target_acceptance":cfg.target_acceptance})
                rejection = calibrate_scores(values,method,cfg.target_acceptance,provenance=provenance)
                rejection.save(runs/f"rejection_{view}_{method}.json")
                rejections[method] = rejection.to_dict()
            records[view] = {"alarm":alarm,"rejection":rejections}
        if trained["runtime"] != runtime_identity(device):
            raise ValueError("runtime changed during calibration")
        _training(runs,device)
        log("known-only val-calib complete; no held-out source opened")
        return _commit(runs,"calibration",{"training_sha256":_sha256(runs/"training.json"),"data_identity":identity,
            "calibration_groups":roles["val-calib"],"n_calibration":len(sources["val-calib"]),"views":records,
            "files":{name:_sha256(runs/name) for name in sorted(bounded._calibration_names(cfg))}})


def _calibration(root):
    root = Path(root)
    trained,cfg,_ = _training(root)  # CPU inspection, no CUDA probe or held-out observation access.
    calibrated = _marker(root,"calibration")
    if (calibrated["training_sha256"] != _sha256(root/"training.json") or calibrated["data_identity"] != trained["data_identity"]
            or calibrated["calibration_groups"] != trained["roles"]["val-calib"]
            or calibrated["n_calibration"] != ROLE_COUNTS["val-calib"]*len(LABELS)
            or set(calibrated["files"]) != bounded._calibration_names(cfg) or set(calibrated["views"]) != set(cfg.views)):
        raise ValueError("calibration population or artifact binding differs")
    bounded._files(root,calibrated["files"])
    for view in cfg.views:
        item = calibrated["views"][view]
        if item["alarm"] != bounded._strict(root/f"alarm_{view}.json"):
            raise ValueError("alarm calibration differs")
        for method in cfg.methods:
            rejection = RejectionCalibration.from_dict(bounded._strict(root/f"rejection_{view}_{method}.json"))
            expected = fingerprint({"checkpoint_sha256":trained["files"][f"model_{view}.pt"],"data":trained["data_identity"],
                "method":method,"groups":trained["roles"]["val-calib"],"target_acceptance":cfg.target_acceptance})
            if (rejection.to_dict() != item["rejection"][method] or rejection.provenance != expected
                    or rejection.n_calibration != calibrated["n_calibration"] or rejection.target_acceptance != .95):
                raise ValueError("rejection calibration differs")
    return calibrated,trained,cfg


def _common(trained,cfg):
    return {"config":bounded._base_config(cfg),"data_identity":trained["data_identity"],"roles":trained["roles"],
        "source":trained["source"]["files_sha256"],"runtime":trained["runtime"]}


def freeze_inventory(runs_list, out, *, profile="proposed-full"):
    if profile not in PROFILES:
        raise ValueError("production inventory profile must be canonical or matched dual")
    out = Path(out)
    if out.exists():
        raise ValueError("frozen inventory already exists")
    roots = [Path(p).resolve() for p in runs_list]
    bounded._separate(out,roots)
    cells, common = [],None
    for root in roots:
        calibrated,trained,cfg = _calibration(root)
        candidate = _common(trained,cfg)
        if common is None:
            common = candidate
        if candidate != common:
            raise ValueError("inventory mixes data/source/runtime/configuration")
        for view in cfg.views:
            cells.append({"seed":cfg.train_config(view).seed,"view":view,"runs":str(root),
                "training_sha256":_sha256(root/"training.json"),"calibration_sha256":_sha256(root/"calibration.json"),
                "training_id":trained["artifact_id"],"calibration_id":calibrated["artifact_id"]})
    _roster(cells,profile)
    out.parent.mkdir(parents=True,exist_ok=True)
    value = {"contract":CONTRACT,"phase":"inventory","scope":"PRODUCTION","benchmark_complete":False,
        "profile":profile,"seeds":[0,1,2],"cells":sorted(cells,key=lambda c:(c["seed"],c["view"])),"common":common,
        "full_protocol_admission":profile == "proposed-full","production_authorized":False}
    value["artifact_id"] = fingerprint(value)
    _write_json(out,value)
    with out.open("rb") as stream:
        os.fsync(stream.fileno())
    fd = os.open(out.parent,os.O_RDONLY|os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    return value


def _roster(cells,profile):
    expected = {(s,v) for s in (0,1,2) for v in PROFILES[profile]}
    if len(cells) != len(expected) or {(c["seed"],c["view"]) for c in cells} != expected:
        raise ValueError("inventory requires exactly nine canonical or six matched cells")


def verify_inventory(path, profile):
    value = bounded._strict(path)
    if (profile not in PROFILES or value.get("contract") != CONTRACT or value.get("phase") != "inventory"
            or value.get("scope") != "PRODUCTION" or value.get("profile") != profile
            or value.get("benchmark_complete") is not False or value.get("production_authorized") is not False
            or value.get("seeds") != [0,1,2] or value.get("full_protocol_admission") is not (profile == "proposed-full")
            or value.get("artifact_id") != fingerprint({k:v for k,v in value.items() if k != "artifact_id"})):
        raise ValueError("invalid production inventory")
    _roster(value["cells"],profile)
    bundles = {}
    for cell in value["cells"]:
        root = Path(cell["runs"])
        if root not in bundles:
            bundles[root] = _calibration(root)
        calibrated,trained,cfg = bundles[root]
        if (cell["view"] not in cfg.views or cell["seed"] != cfg.train_config(cell["view"]).seed
                or cell["training_sha256"] != _sha256(root/"training.json") or cell["calibration_sha256"] != _sha256(root/"calibration.json")
                or cell["training_id"] != trained["artifact_id"] or cell["calibration_id"] != calibrated["artifact_id"]
                or value["common"] != _common(trained,cfg)):
            raise ValueError("production inventory cell binding differs")
    return value


def development_train_calibrate_freeze(config, data, runs, inventory, *, log=print):
    """Bounded development-only three-role exercise; no held-out role is generated/read.

    A separate entry point with fixed CPU and the same E7b caps. It cannot create
    a production artifact or satisfy a production inventory.
    """
    bounded._caps(config)
    if config.protocol != FEATURE_PROTOCOL:
        raise ValueError("development adapter requires the frozen feature protocol")
    data,runs,inventory = Path(data),Path(runs),Path(inventory)
    bounded._separate(runs,[data,inventory])
    bounded._separate(inventory,[data,runs])
    if runs.exists() or inventory.exists():
        raise ValueError("fresh development output paths required")
    manifest,_ = bounded._known_header(data)
    requested = ("train","val-select","val-calib")
    if set(manifest.get("roles",{})) != set(requested):
        raise ValueError("development data must contain exactly train/val-select/val-calib and no test role")
    roles = {role:manifest["roles"][role]["scenario_seeds"] for role in requested}
    if any(not 1 <= len(groups) <= bounded.CAPS["groups_per_role"] or groups != scenario_ids(role,len(groups))
           for role,groups in roles.items()):
        raise ValueError("development role groups exceed bounded fixture restrictions")
    if (manifest.get("protocol") != FEATURE_PROTOCOL or manifest.get("labels") != list(LABELS)
            or manifest.get("cancellation") != CancellationConfig().to_dict() or manifest.get("benchmark_complete") is not False):
        raise ValueError("development feature protocol/cancellation differs")
    source = _source_identity()
    with r6_fp32():
        runtime = runtime_identity("cpu")
        _,identity,sources = open_b2_known_roles(data,("train","val-select"))
        _check_roles({r:s.split() for r,s in sources.items()})
        provenance = {"protocol":config.protocol,"data_fingerprint":identity,"roles":roles,
            "source_files_sha256":source["files_sha256"],"scope":"BOUNDED_DEVELOPMENT"}
        runs.mkdir(parents=True)
        _write_json(runs/"config.json",config.resolved())
        models,training = {},{}
        for view in config.views:
            fitted = fit_streaming(sources["train"],sources["val-select"],config.train_config(view),
                window_shards=config.window_shards,device="cpu",log=log)
            fitted.update(provenance=provenance,source_revision=source["revision"])
            save(fitted,runs/f"model_{view}.pt")
            checkpoint = _sha256(runs/f"model_{view}.pt")
            fitted = load(runs/f"model_{view}.pt",device="cpu",expected_config=config.train_config(view),expected_provenance=provenance)
            outputs = infer_streaming(fitted,sources["train"])
            scorer = fit_mahalanobis(outputs["embedding"],sources["train"].index["label"],len(LABELS),
                config.mahalanobis_regularization,provenance=checkpoint)
            scorer.save(runs/f"mahalanobis_{view}.npz")
            models[view] = fitted,scorer
            training[view] = {"checkpoint_sha256":checkpoint,"selected_epoch":fitted["best_epoch"],"history":fitted["history"]}
        _,current,calib_sources = open_b2_known_roles(data,("val-calib",))
        if current != identity:
            raise ValueError("development data changed during execution")
        source_calib = calib_sources["val-calib"]
        _check_roles({"val-calib":source_calib.split()})
        calibration = {}
        for view,(fitted,scorer) in models.items():
            outputs = infer_streaming(fitted,source_calib)
            scores = bounded.clean_alarm_score(_softmax(outputs["logits"]))
            clean = source_calib.index["label"] == 0
            alarm = {"threshold":float(clean_alarm_threshold(scores[clean],config.pfa)),
                "rule":bounded.ALARM_RULE,"n_clean_calibration":int(clean.sum())}
            _write_json(runs/f"alarm_{view}.json",alarm)
            rejections = {}
            for method in config.methods:
                scores = scorer.score(outputs["embedding"]) if method == "mahalanobis" else bounded.unknown_scores(outputs["logits"],method)
                rejection = calibrate_scores(scores,method,config.target_acceptance,provenance=identity)
                rejection.save(runs/f"rejection_{view}_{method}.json")
                rejections[method] = rejection.to_dict()
            calibration[view] = {"alarm":alarm,"rejection":rejections}
        if source != _source_identity() or runtime != runtime_identity("cpu"):
            raise ValueError("development source/runtime changed")
        files = {p.name:_sha256(p) for p in runs.iterdir()}
        value = {"contract":"B2-production-adapter-development/1","scope":"BOUNDED_DEVELOPMENT",
            "benchmark_complete":False,"production_authorized":False,"heldout_reads":0,
            "config":config.resolved(),"data_identity":identity,"roles":roles,"source":source,"runtime":runtime,
            "training":training,"calibration":calibration,"files":files}
        value["artifact_id"] = fingerprint(value)
        _sync(runs)
        _write_json(runs/"development.json",value)
        _sync(runs)
        if any(_sha256(runs/name) != digest for name,digest in files.items()):
            raise ValueError("development payload changed before freeze")
        inventory.parent.mkdir(parents=True,exist_ok=True)
        frozen = {"contract":"B2-production-adapter-development-freeze/1","scope":"BOUNDED_DEVELOPMENT",
            "benchmark_complete":False,"production_authorized":False,"heldout_reads":0,
            "development_sha256":_sha256(runs/"development.json"),"files":files,"roles":roles}
        frozen["artifact_id"] = fingerprint(frozen)
        _write_json(inventory,frozen)
        with inventory.open("rb") as stream:
            os.fsync(stream.fileno())
        fd = os.open(inventory.parent,os.O_RDONLY|os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        return {"training":training,"calibration":calibration,"inventory":frozen,"development":value}

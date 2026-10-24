"""P31 deterministic LOKO inventory, two-cell CPU execution and read-only aggregation.

Planning covers seven folds by three seeds by explicit views. Execution is
limited to one immutable selection of at most two cells per output root;
there is no production, GPU or unrestricted sweep switch.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import replace
import fcntl
import json
from pathlib import Path

import numpy as np

from geosim.b2_protocol import LABELS
from . import b2_loko as lk
from .artifacts import fingerprint
from .b2_experiment import B2ExperimentConfig, VIEWS
from .calibration import RejectionCalibration
from .mahalanobis import MahalanobisScorer
from .openset_metrics import ranking_metrics
from .train import load

PROTOCOL = "B2-LOKO-matrix/1"
MAX_CELLS = 2


def _json(value):
    return json.loads(json.dumps(value, allow_nan=False))


def _write(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def _seal(body, key):
    return {**body, key: fingerprint(body)}


def _unseal(value, key):
    if not isinstance(value, dict) or value.get(key) != fingerprint({k:v for k,v in value.items() if k != key}):
        raise ValueError(f"invalid {key} binding")
    return value


@contextmanager
def _lock(out, *, read_only=False):
    path = Path(out) / ".matrix.lock"
    with path.open("r" if read_only else "a+") as stream:
        try:
            fcntl.flock(stream, (fcntl.LOCK_SH if read_only else fcntl.LOCK_EX) | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ValueError("LOKO matrix output is already in use") from error
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def build_matrix_plan(config, data, *, views=None, seeds=(0, 1, 2)):
    """Read small header metadata only; neither fitting nor test observations are read."""
    chosen = tuple(config.views if views is None else views)
    if not chosen or len(set(chosen)) != len(chosen) or any(v not in VIEWS for v in chosen):
        raise ValueError("explicit views must be unique registered B2 views")
    chosen = tuple(v for v in VIEWS if v in chosen)
    config = replace(config, views=chosen)
    manifest, identity, base = lk.metadata_plan(data, config, seeds=seeds)
    source, runtime = lk._source_identity(), lk._runtime_identity()
    cells = []
    for fold in base["folds"]:
        for view in chosen:
            for seed in seeds:
                cell_config = replace(config, views=(view,), training={**config.training, "seed": seed})
                body = {"id": f"{fold['holdout_label']}__{view}__seed-{seed}",
                        "holdout_label": fold["holdout_label"], "view": view, "seed": seed,
                        "config": _json(cell_config.resolved()), "fold": fold,
                        "data_fingerprint": identity, "source_files_sha256": source["files_sha256"],
                        "runtime_identity": runtime}
                cells.append(_seal(body, "cell_fingerprint"))
    body = {"protocol": PROTOCOL, "parent_protocol": "B2/1", "benchmark_complete": False,
            "full_sweep_authorized": False, "execution_cap_unique_cells": MAX_CELLS,
            "data_fingerprint": identity, "source": source, "runtime_identity": runtime,
            "config": _json(config.resolved()), "views": list(chosen), "training_seeds": list(seeds),
            "declared_role_groups": {r:manifest["roles"][r]["scenario_seeds"] for r in lk.ROLES},
            "planning_verification": "request, calibration and shard descriptors only; no role observation bytes",
            "cells": cells, "total_planned_fits": len(cells),
            "uncertainty": "per-cell paired scenario bootstrap; training-seed spread separate; no score pooling"}
    return _seal(body, "plan_fingerprint")


def write_plan(config, data, out, *, views=None, seeds=(0, 1, 2), reuse=False):
    lk._check_output_path(data, out)
    plan = build_matrix_plan(config, data, views=views, seeds=seeds)
    out = Path(out)
    if out.exists() and any(out.iterdir()) and not (out / "plan.json").exists():
        raise ValueError("nonempty output has no matrix plan; existing work is preserved")
    out.mkdir(parents=True, exist_ok=True)
    with _lock(out):
        path = out / "plan.json"
        if path.exists():
            if not reuse or lk._read_json(path) != plan:
                raise ValueError("matrix plan exists or differs; use matching --reuse or a fresh output")
        else:
            _write(path, plan)
    return plan


def _current_plan(config, data, out):
    plan = _unseal(lk._read_json(Path(out) / "plan.json"), "plan_fingerprint")
    expected = build_matrix_plan(config, data, views=plan["views"], seeds=tuple(plan["training_seeds"]))
    if plan != expected:
        raise ValueError("matrix data, source, runtime or configuration identity mismatch")
    return plan


def _files(config):
    return ("model.pt", "mahalanobis.npz", "freeze.json", "results.json", "predictions.json", "plan.json",
            *(f"rejection_{method}.json" for method in config.methods))


def _native_provenance(plan, cell):
    config = B2ExperimentConfig(**cell["config"])
    return {"protocol": lk.PROTOCOL, "data_fingerprint": plan["data_fingerprint"],
            "holdout_label": cell["holdout_label"], "fold": cell["fold"], "config": config.resolved(),
            "window_shards": config.window_shards, "source_files_sha256": plan["source"]["files_sha256"],
            "runtime_identity": plan["runtime_identity"]}


def _inspect_native(plan, cell, root):
    """Load frozen artifacts and score rows only; never fit, calibrate or infer."""
    root = Path(root)
    config = B2ExperimentConfig(**cell["config"])
    names = lk.known_labels(cell["holdout_label"])
    provenance = _native_provenance(plan, cell)
    experiment = fingerprint(provenance)
    try:
        fitted = load(root / "model.pt", device="cpu", expected_config=replace(config.train_config(cell["view"]), labels=names),
                      expected_provenance=provenance)
    except Exception as error:
        raise ValueError("invalid or incompatible frozen LOKO checkpoint") from error
    checkpoint = lk._sha256(root / "model.pt")
    derived = fingerprint({"experiment": experiment, "checkpoint_sha256": checkpoint})
    scorer = MahalanobisScorer.load(root / "mahalanobis.npz")
    train_groups = len(cell["fold"]["partitions"]["train"]["scenario_ids"])
    if (scorer.provenance != derived or scorer.means.shape != (len(names), 16 * config.train_config(cell["view"]).width)
            or scorer.class_counts.tolist() != [train_groups] * len(names)
            or scorer.regularization != config.mahalanobis_regularization):
        raise ValueError("LOKO scorer provenance, class population or regularization mismatch")
    calibrations = {m:RejectionCalibration.from_dict(lk._read_json(root / f"rejection_{m}.json")) for m in config.methods}
    expected_calib = cell["fold"]["partitions"]["val-calib"]["n_retained_known"]
    if any(c.provenance != derived or c.method != m or c.n_calibration != expected_calib
           or c.target_acceptance != config.target_acceptance for m,c in calibrations.items()):
        raise ValueError("LOKO calibration provenance or population mismatch")
    freeze = _unseal(lk._read_json(root / "freeze.json"), "freeze_fingerprint")
    expected_files = ("model.pt", "mahalanobis.npz", *(f"rejection_{m}.json" for m in config.methods))
    expected_freeze = {"schema": "B2-LOKO-frozen/1", "benchmark_complete": False,
        "experiment_fingerprint": experiment, "data_fingerprint": plan["data_fingerprint"],
        "holdout_label": cell["holdout_label"], "known_labels": list(names), "fold": cell["fold"],
        "config": cell["config"], "runtime_identity": plan["runtime_identity"],
        "files_sha256": {name:lk._sha256(root / name) for name in expected_files}}
    if freeze != _seal(expected_freeze, "freeze_fingerprint"):
        raise ValueError("LOKO frozen-file receipt mismatch")
    native_plan = lk._read_json(root / "plan.json")
    _unseal(native_plan, "plan_fingerprint")
    if (native_plan["data_fingerprint"] != plan["data_fingerprint"] or native_plan["config"] != cell["config"]
            or next(f for f in native_plan["folds"] if f["holdout_label"] == cell["holdout_label"]) != cell["fold"]):
        raise ValueError("LOKO per-fold plan identity mismatch")
    result = lk._read_json(root / "results.json")
    expected = {"protocol":lk.PROTOCOL, "benchmark_complete":False, "mode":"BOUNDED_CPU_SMOKE",
        "holdout_label":cell["holdout_label"], "known_labels":list(names), "fold":cell["fold"],
        "data_fingerprint":plan["data_fingerprint"], "config":cell["config"], "experiment_fingerprint":experiment,
        "plan_fingerprint":native_plan["plan_fingerprint"], "checkpoint_sha256":checkpoint,
        "runtime_identity":plan["runtime_identity"], "freeze_manifest_sha256":lk._sha256(root / "freeze.json"),
        "frozen_files_sha256":freeze["files_sha256"],
        "n_mahalanobis_training":cell["fold"]["partitions"]["train"]["n_retained_known"]}
    if any(result.get(k) != v for k,v in expected.items()) or result["source"]["files_sha256"] != plan["source"]["files_sha256"]:
        raise ValueError("LOKO result identity or fitted population mismatch")
    if result["history"] != fitted["history"] or set(result["methods"]) != set(config.methods):
        raise ValueError("LOKO result history or methods mismatch")
    rows = lk._read_json(root / "predictions.json")
    expected_ids = [(int(g), label) for g in plan["declared_role_groups"]["test"] for label in LABELS]
    if not isinstance(rows, list) or [(r.get("scenario_id"),r.get("true_label")) for r in rows] != expected_ids:
        raise ValueError("LOKO paired prediction population mismatch")
    for row in rows:
        if (row.get("is_unknown") is not (row["true_label"] == cell["holdout_label"])
                or row.get("prediction") not in names or set(row.get("unknown_scores", {})) != set(config.methods)):
            raise ValueError("invalid LOKO prediction class or score columns")
    for method, calibration in calibrations.items():
        scores = np.asarray([r["unknown_scores"][method] for r in rows])
        accepted = calibration.accept(scores)
        held = np.asarray([r["is_unknown"] for r in rows])
        report = result["methods"][method]
        if report["calibration"] != calibration.to_dict():
            raise ValueError("LOKO result calibration mismatch")
        groups = np.asarray([r["scenario_id"] for r in rows])
        correct = np.asarray([r["prediction"] == r["true_label"] for r in rows])
        rates = {"known_acceptance":accepted[~held], "accepted_known_accuracy":correct[~held & accepted],
                 "known_correct_acceptance":correct[~held] & accepted[~held], "unknown_rejection":~accepted[held]}
        for field, mask in (("known_acceptance", ~held), ("accepted_known_accuracy", ~held & accepted),
                            ("known_correct_acceptance", ~held), ("unknown_rejection", held)):
            if report[field]["n_samples"] != int(mask.sum()) or report[field]["n_scenarios"] != len(np.unique(groups[mask])):
                raise ValueError("LOKO result metric denominator mismatch")
            expected_mean = float(rates[field].mean()) if len(rates[field]) else None
            actual_mean = report[field]["mean"]
            if (isinstance(actual_mean, bool) or actual_mean != expected_mean):
                raise ValueError("LOKO threshold rate differs from its frozen prediction rows")
        if report["ranking"]["n_known"] != int((~held).sum()) or report["ranking"]["n_unknown"] != int(held.sum()):
            raise ValueError("LOKO ranking denominator mismatch")
        expected_rank = ranking_metrics(scores[~held], scores[held], correct[~held])
        if any(isinstance(report["ranking"].get(k), bool) or report["ranking"].get(k) != expected_rank[k]
               for k in lk.RANKING_KEYS):
            raise ValueError("LOKO ranking metric differs from its frozen prediction rows")
    return result, rows


def _verify_cell(plan, cell, out):
    parent = Path(out) / "cells" / cell["id"]
    if lk._read_json(parent / "status.json") != {"state":"COMPLETE", "cell_fingerprint":cell["cell_fingerprint"]}:
        raise ValueError("LOKO cell status is not complete or has a foreign identity")
    receipt = _unseal(lk._read_json(parent / "cell.json"), "receipt_fingerprint")
    config = B2ExperimentConfig(**cell["config"])
    if (receipt.get("schema") != "B2-LOKO-cell/1" or receipt.get("plan_fingerprint") != plan["plan_fingerprint"]
            or receipt.get("cell_fingerprint") != cell["cell_fingerprint"] or receipt.get("id") != cell["id"]
            or set(receipt.get("files_sha256", {})) != set(_files(config))):
        raise ValueError("LOKO cell identity or artifact inventory mismatch")
    root = parent / "run"
    if any(lk._sha256(root / name) != digest for name,digest in receipt["files_sha256"].items()):
        raise ValueError("LOKO cell artifact checksum mismatch")
    result, rows = _inspect_native(plan, cell, root)
    if (lk._read_json(parent / "cell.json") != receipt
            or lk._read_json(parent / "status.json") != {"state":"COMPLETE", "cell_fingerprint":cell["cell_fingerprint"]}
            or any(lk._sha256(root / name) != digest for name,digest in receipt["files_sha256"].items())):
        raise ValueError("LOKO cell artifacts changed during read-only verification")
    return {"cell":cell, "receipt":receipt, "result":result, "rows":rows}


def run_bounded(config, data, out, *, selected, reuse=False, bootstrap=200, log=print):
    """Execute <=2 declared cells; selection is immutable across every re-entry."""
    lk._check_output_path(data, out)
    if type(reuse) is not bool or type(bootstrap) is not int or not 1 <= bootstrap <= 1000:
        raise ValueError("reuse must be boolean and bootstrap must be an integer in [1,1000]")
    out = Path(out)
    with _lock(out):
        plan = _current_plan(config, data, out)
        ids = [c["id"] for c in plan["cells"]]
        if (not isinstance(selected, (list, tuple)) or not 1 <= len(selected) <= MAX_CELLS
                or any(not isinstance(name, str) for name in selected)
                or len(set(selected)) != len(selected) or not set(selected) <= set(ids)):
            raise ValueError("execution selection must contain one or two unique planned cells")
        selection = [name for name in ids if name in selected]
        prior_cells = list((out / "cells").iterdir()) if (out / "cells").exists() else []
        if (any(not path.is_dir() or path.name not in selection for path in prior_cells)
                or len(prior_cells) > MAX_CELLS):
            raise ValueError("immutable selection conflicts with previously attempted cells; the two-cell cap cannot be reset")
        status_path = out / "matrix_status.json"
        if status_path.exists():
            previous = lk._read_json(status_path)
            if previous.get("selected") != selection or previous.get("plan_fingerprint") != plan["plan_fingerprint"]:
                raise ValueError("immutable selection conflicts with the completed matrix status")
        if any(len(g) > lk.SMOKE_MAX_GROUPS for g in plan["declared_role_groups"].values()):
            raise ValueError("bounded matrix execution requires at most two groups per role")
        for cell in plan["cells"]:
            if cell["id"] in selection:
                cfg = B2ExperimentConfig(**cell["config"]).train_config(cell["view"])
                if cfg.epochs > 2 or cfg.width > 8 or cfg.batch > 32:
                    raise ValueError("bounded matrix caps: CPU epochs<=2, width<=8, batch<=32")
        declaration = _seal({"schema":"B2-LOKO-selection/1", "plan_fingerprint":plan["plan_fingerprint"],
            "selected":selection, "max_unique_cells":MAX_CELLS, "bootstrap":bootstrap}, "selection_fingerprint")
        path = out / "selection.json"
        if path.exists():
            if lk._read_json(path) != declaration:
                raise ValueError("immutable LOKO selection or budget differs from the existing declaration")
        else:
            _write(path, declaration)
        completed = []
        for cell in plan["cells"]:
            if cell["id"] not in selection:
                continue
            parent = out / "cells" / cell["id"]
            if (parent / "cell.json").exists():
                if not reuse:
                    raise ValueError("completed cell exists; matching --reuse is required")
                _verify_cell(plan, cell, out)
            else:
                if parent.exists() and any(parent.iterdir()):
                    raise ValueError("incomplete LOKO cell; no implicit refit or optimizer resume is allowed")
                parent.mkdir(parents=True, exist_ok=True)
                _write(parent / "status.json", {"state":"RUNNING", "cell_fingerprint":cell["cell_fingerprint"]})
                try:
                    child = B2ExperimentConfig(**cell["config"])
                    lk.run_smoke(child, data, parent / "run", holdout=cell["holdout_label"], bootstrap=bootstrap, log=log)
                    _inspect_native(plan, cell, parent / "run")
                    receipt = _seal({"schema":"B2-LOKO-cell/1", "id":cell["id"],
                        "plan_fingerprint":plan["plan_fingerprint"], "cell_fingerprint":cell["cell_fingerprint"],
                        "files_sha256":{name:lk._sha256(parent / "run" / name) for name in _files(child)}}, "receipt_fingerprint")
                    if _current_plan(config, data, out) != plan:
                        raise ValueError("LOKO execution plan changed during fitting/evaluation")
                    _write(parent / "status.json", {"state":"COMPLETE", "cell_fingerprint":cell["cell_fingerprint"]})
                    _write(parent / "cell.json", receipt)  # completion committed last
                except BaseException:
                    _write(parent / "status.json", {"state":"FAILED", "cell_fingerprint":cell["cell_fingerprint"]})
                    raise
            completed.append(cell["id"])
        if _current_plan(config, data, out) != plan:
            raise ValueError("LOKO execution identity changed before completion")
        lk._verify_artifact_snapshot(data, plan["data_fingerprint"])
        report = {"protocol":PROTOCOL, "benchmark_complete":False, "status":"PARTIAL",
                  "plan_fingerprint":plan["plan_fingerprint"], "selected":selection,
                  "planned_cells":len(ids), "completed_cells":len(completed), "missing_cells":len(ids)-len(completed),
                  "full_sweep_complete":False, "full_sweep_authorized":False, "execution_cap_unique_cells":MAX_CELLS}
        _write(out / "matrix_status.json", report)
        return report


def paired_seed_group_ci(seed_values, *, replicates=200, seed=20261022):
    """Shared group draws; average seed metrics, never pooled cross-model scores."""
    if type(replicates) is not int or not 1 <= replicates <= 1000 or not seed_values:
        raise ValueError("paired bootstrap needs seed values and replicates in [1,1000]")
    first = seed_values[0]
    groups, held = np.asarray(first["groups"]), np.asarray(first["held"])
    ids = np.unique(groups)
    if any(not np.array_equal(v["groups"], groups) or not np.array_equal(v["held"], held) for v in seed_values):
        raise ValueError("training seeds do not share identical paired scenario populations")
    out = {"n_scenarios":len(ids), "n_seeds":len(seed_values), "replicates":replicates,
           "unit":"one common scenario-group draw across fixed training seeds", "ci95":None,
           "training_seed_uncertainty_included":False}
    if len(ids) < 2 or not held.any() or held.all():
        return {**out, "reason":"at least two scenario groups and both known/held-out populations are required"}
    by_group = {g:np.flatnonzero(groups == g) for g in ids}
    rng = np.random.default_rng(seed)
    samples = {key:[] for key in lk.RANKING_KEYS}
    for _ in range(replicates):
        positions = np.concatenate([by_group[g] for g in rng.choice(ids, len(ids), replace=True)])
        h = held[positions]
        seed_metrics = []
        for value in seed_values:
            correct = np.zeros(len(groups), bool)
            correct[~held] = value["known_correct"]
            scores = np.asarray(value["scores"])[positions]
            seed_metrics.append(ranking_metrics(scores[~h], scores[h], correct[positions][~h]))
        for key in samples:
            samples[key].append(float(np.mean([m[key] for m in seed_metrics])))
    return {**out, "ci95":{k:np.quantile(v,[.025,.975]).tolist() for k,v in samples.items()}}


def _complete_summary(plan, verified, *, bootstrap):
    grouped = []
    for holdout in LABELS[1:]:
        for view in plan["views"]:
            values = sorted([v for v in verified if v["cell"]["holdout_label"] == holdout and v["cell"]["view"] == view],
                            key=lambda v:v["cell"]["seed"])
            if sorted(v["cell"]["seed"] for v in values) != sorted(plan["training_seeds"]):
                raise ValueError("complete fold/view requires every registered training seed")
            methods = {}
            for method in B2ExperimentConfig(**plan["config"]).methods:
                per_seed = [v["result"]["methods"][method]["ranking"] for v in values]
                ci_inputs = []
                for value in values:
                    rows = value["rows"]
                    h = np.asarray([r["is_unknown"] for r in rows])
                    ci_inputs.append({"groups":np.asarray([r["scenario_id"] for r in rows]), "held":h,
                        "scores":np.asarray([r["unknown_scores"][method] for r in rows]),
                        "known_correct":np.asarray([r["prediction"] == r["true_label"] for r in rows])[~h]})
                methods[method] = {"n_training_seeds":len(values), "seed_values":{str(v["cell"]["seed"]):
                    {k:v["result"]["methods"][method]["ranking"][k] for k in lk.RANKING_KEYS} for v in values},
                    "seed_mean":{k:float(np.mean([x[k] for x in per_seed])) for k in lk.RANKING_KEYS},
                    "seed_sample_sd":{k:float(np.std([x[k] for x in per_seed],ddof=1)) for k in lk.RANKING_KEYS},
                    "fixed_seed_models_group_ci":paired_seed_group_ci(ci_inputs,replicates=bootstrap)}
            grouped.append({"holdout_label":holdout,"view":view,"methods":methods})
    return {"fold_view_summaries":grouped, "across_holdout_scores_pooled":False,
            "across_holdout_ci":None,
            "across_holdout_ci_reason":"different held-out tasks; report fold/view rows rather than pool incompatible score populations",
            "training_seed_sd_is_not_group_ci":True}


def aggregate(config, data, out, *, allow_partial=False, bootstrap=200):
    """Read-only artifact validation/aggregation; no fitting, selection or inference."""
    lk._check_output_path(data, out)
    if type(allow_partial) is not bool or type(bootstrap) is not int or not 1 <= bootstrap <= 1000:
        raise ValueError("partial must be boolean and bootstrap must be an integer in [1,1000]")
    out = Path(out)
    with _lock(out, read_only=True):
        plan = _current_plan(config, data, out)
        verified, missing = [], []
        for cell in plan["cells"]:
            parent = out / "cells" / cell["id"]
            if not (parent / "cell.json").exists():
                if parent.exists() and any(parent.iterdir()):
                    raise ValueError("incomplete LOKO cell artifacts cannot be aggregated")
                missing.append(cell["id"])
            else:
                verified.append(_verify_cell(plan, cell, out))
        if missing and not allow_partial:
            raise ValueError(f"missing {len(missing)} LOKO cell results; full inventory is required")
        if verified:
            lk._verify_artifact_snapshot(data, plan["data_fingerprint"])
        summary = None if missing else _complete_summary(plan, verified, bootstrap=bootstrap)
        if _current_plan(config, data, out) != plan:
            raise ValueError("LOKO aggregation identity changed during validation")
        return {"protocol":PROTOCOL,"benchmark_complete":False,"status":"PARTIAL" if missing else "COMPLETE_INVENTORY",
            "full_sweep_authorized":False,"plan_fingerprint":plan["plan_fingerprint"],
            "counts":{"planned_cells":len(plan["cells"]),"completed_cells":len(verified),"missing_cells":len(missing)},
            "missing":missing,"summary_metrics":summary,
            "summary_unavailable_reason":"complete seven-fold/three-seed/view inventory is missing" if missing else None,
            "cells":[{"id":v["cell"]["id"],"seed":v["cell"]["seed"],"view":v["cell"]["view"],
                      "holdout_label":v["cell"]["holdout_label"],"metrics":v["result"]["methods"],
                      "receipt_fingerprint":v["receipt"]["receipt_fingerprint"]} for v in verified]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("plan","run","aggregate"))
    parser.add_argument("--config",required=True);parser.add_argument("--data",required=True);parser.add_argument("--out",required=True)
    parser.add_argument("--views",nargs="+",choices=VIEWS)
    parser.add_argument("--cell",action="append",dest="selected")
    parser.add_argument("--reuse",action="store_true");parser.add_argument("--partial",action="store_true")
    parser.add_argument("--report",help="aggregate report outside the frozen matrix output root")
    args=parser.parse_args(argv);config=B2ExperimentConfig.from_file(args.config)
    if args.mode=="plan":
        if args.views is None:parser.error("plan requires explicit --views")
        result=write_plan(config,args.data,args.out,views=args.views,reuse=args.reuse)
    elif args.mode=="run":result=run_bounded(config,args.data,args.out,selected=args.selected,reuse=args.reuse)
    else:
        result=aggregate(config,args.data,args.out,allow_partial=args.partial)
        if args.report:
            report=Path(args.report).resolve();root=Path(args.out).resolve()
            lk._check_output_path(args.data, report)
            if report==root or root in report.parents or report in root.parents:
                raise ValueError("aggregate report must be outside frozen matrix inputs")
            if report.exists():raise ValueError("aggregate report already exists; existing work is preserved")
            _write(report,result)
    print(json.dumps(result,indent=2,allow_nan=False))


if __name__=="__main__":
    main()

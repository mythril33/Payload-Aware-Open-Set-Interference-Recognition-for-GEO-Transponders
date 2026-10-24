"""Bounded LOKO orchestration on deterministic array stand-ins, never held-out RF."""
import json
from dataclasses import replace

import numpy as np
import pytest

from geoml import b2_loko as lk
from geoml import b2_loko_matrix as mx
from geoml.artifacts import fingerprint
from geosim.b2_protocol import LABELS
from test_b2_loko import dataset  # noqa: F401
from test_b2_experiment import _config
from geoml import train as train_module
from geoml.mahalanobis import MahalanobisScorer
import torch


def cfg():
    base = _config(views=("co",))
    return replace(base, training={**base.training, "width": 1, "batch": 7})


def test_planner_is_deterministic_seven_by_three_per_view_and_never_reads_observations(dataset, tmp_path, monkeypatch):
    _, _, data = dataset
    monkeypatch.setattr(lk, "open_b2_known_roles", lambda *_: pytest.fail("planning read observations"))
    monkeypatch.setattr(lk, "fit_streaming", lambda *_a, **_k: pytest.fail("planning fit"))
    plan = mx.build_matrix_plan(cfg(), data, views=("co", "dual"))
    assert plan == mx.build_matrix_plan(cfg(), data, views=("co", "dual"))
    assert len(plan["cells"]) == 42 and plan["training_seeds"] == [0, 1, 2]
    assert plan["benchmark_complete"] is False and plan["full_sweep_authorized"] is False
    assert len({c["cell_fingerprint"] for c in plan["cells"]}) == 42
    assert {c["holdout_label"] for c in plan["cells"]} == set(LABELS[1:])
    written = mx.write_plan(cfg(), data, tmp_path / "matrix", views=("co", "dual"))
    assert written == plan
    with pytest.raises(ValueError):
        mx.write_plan(cfg(), data, tmp_path / "matrix", views=("co",))


def test_global_two_cell_selection_cap_precedes_any_fit(dataset, tmp_path, monkeypatch):
    _, _, data = dataset
    out = tmp_path / "matrix"
    plan = mx.write_plan(cfg(), data, out)
    monkeypatch.setattr(lk, "run_smoke", lambda *_a, **_k: pytest.fail("cap failed before execution"))
    with pytest.raises(ValueError, match="two"):
        mx.run_bounded(cfg(), data, out, selected=[c["id"] for c in plan["cells"][:3]])
    assert not (out / "selection.json").exists()
    assert not (out / "cells").exists()


def test_two_seed_smoke_freezes_each_cell_and_partial_summary_is_not_complete(dataset, tmp_path, monkeypatch):
    _, _, data = dataset
    out = tmp_path / "matrix"
    plan = mx.write_plan(cfg(), data, out)
    selected = [c["id"] for c in plan["cells"][:2]]
    result = mx.run_bounded(cfg(), data, out, selected=selected, bootstrap=10, log=lambda *_: None)
    assert result["status"] == "PARTIAL" and result["completed_cells"] == 2
    assert result["planned_cells"] == 21 and result["missing_cells"] == 19
    for name in selected:
        receipt = json.loads((out / "cells" / name / "cell.json").read_text())
        assert receipt["plan_fingerprint"] == plan["plan_fingerprint"]
        run = out / "cells" / name / "run"
        assert (run / "freeze.json").exists()
        native = json.loads((run / "results.json").read_text())
        assert native["n_mahalanobis_training"] == 14
        assert native["methods"]["msp"]["calibration"]["n_calibration"] == 14
        assert native["methods"]["msp"]["ranking"]["n_known"] == 14
        assert native["methods"]["msp"]["ranking"]["n_unknown"] == 2
    with pytest.raises(ValueError, match="missing"):
        mx.aggregate(cfg(), data, out)
    partial = mx.aggregate(cfg(), data, out, allow_partial=True)
    assert partial["summary_metrics"] is None and partial["status"] == "PARTIAL"
    assert partial["counts"] == {"planned_cells": 21, "completed_cells": 2, "missing_cells": 19}
    assert len(partial["missing"]) == 19
    before = {str(p): (p.read_bytes(), p.stat().st_mtime_ns) for p in (out / "cells").rglob("*") if p.is_file()}
    monkeypatch.setattr(lk, "fit_streaming", lambda *_a, **_k: pytest.fail("completed reuse refit"))
    monkeypatch.setattr(lk, "infer_streaming", lambda *_a, **_k: pytest.fail("completed reuse inferred"))
    reused = mx.run_bounded(cfg(), data, out, selected=selected, reuse=True, bootstrap=10, log=lambda *_: None)
    assert reused["completed_cells"] == 2
    assert before == {str(p): (p.read_bytes(), p.stat().st_mtime_ns) for p in (out / "cells").rglob("*") if p.is_file()}
    with pytest.raises(ValueError, match="selection"):
        mx.run_bounded(cfg(), data, out, selected=[plan["cells"][2]["id"]], reuse=True)


def test_common_group_draw_preserves_cross_seed_covariance_without_pooling():
    groups = np.repeat([3200000, 3200001], 8)
    labels = np.tile(np.arange(8), 2)
    held = labels == LABELS.index("cw")
    scores = np.where(groups == groups[0], held.astype(float), (~held).astype(float))
    correct = np.ones(14, bool)
    values = [{"groups": groups, "held": held, "scores": s, "known_correct": correct}
              for s in (scores, 1 - scores, scores)]
    result = mx.paired_seed_group_ci(values, replicates=200)
    assert result["n_scenarios"] == 2 and result["n_seeds"] == 3
    assert result["unit"] == "one common scenario-group draw across fixed training seeds"
    assert result["ci95"]["unknown_auroc"] == pytest.approx([1 / 3, 2 / 3])
    assert mx.paired_seed_group_ci([{k:v[:8] if k != "known_correct" else v[:7]
                                   for k,v in value.items()} for value in values])["ci95"] is None


@pytest.fixture
def completed(dataset, tmp_path):
    _, _, data = dataset
    out = tmp_path / "matrix"
    plan = mx.write_plan(cfg(), data, out)
    cell = plan["cells"][0]
    mx.run_bounded(cfg(), data, out, selected=[cell["id"]], bootstrap=10, log=lambda *_: None)
    return data, out, plan, cell


def _resign_cell(out, cell):
    parent = out / "cells" / cell["id"]
    path = parent / "cell.json"
    receipt = json.loads(path.read_text())
    receipt["files_sha256"] = {name:lk._sha256(parent / "run" / name) for name in receipt["files_sha256"]}
    receipt["receipt_fingerprint"] = fingerprint({k:v for k,v in receipt.items() if k != "receipt_fingerprint"})
    path.write_text(json.dumps(receipt))


@pytest.mark.parametrize("filename", ["model.pt", "mahalanobis.npz", "results.json", "rejection_msp.json", "predictions.json"])
def test_corrupt_completed_artifact_is_rejected(completed, filename):
    data, out, _, cell = completed
    path = out / "cells" / cell["id"] / "run" / filename
    path.write_bytes(path.read_bytes() + b"corrupt")
    with pytest.raises(ValueError, match="checksum"):
        mx.aggregate(cfg(), data, out, allow_partial=True)


@pytest.mark.parametrize("change", ["ranking", "fraction", "denominator", "seed_checkpoint", "scorer_population", "status"])
def test_consistently_resigned_foreign_or_invalid_cell_fails_closed(completed, change):
    data, out, _, cell = completed
    parent = out / "cells" / cell["id"]
    root = parent / "run"
    if change in ("ranking", "fraction", "denominator"):
        path = root / "results.json"
        result = json.loads(path.read_text())
        if change == "ranking": result["methods"]["msp"]["ranking"]["unknown_auroc"] = 2.0
        if change == "fraction":
            rate = result["methods"]["msp"]["known_acceptance"]
            rate["mean"] = 0.5 if rate["mean"] != 0.5 else 0.25
        if change == "denominator": result["methods"]["msp"]["unknown_rejection"]["n_samples"] = 100
        path.write_text(json.dumps(result))
    elif change == "seed_checkpoint":
        path = root / "model.pt"
        artifact = torch.load(path, map_location="cpu", weights_only=True)
        artifact["config"]["seed"] = 1
        artifact["metadata_fingerprint"] = train_module._metadata_fingerprint(artifact)
        torch.save(artifact, path)
    elif change == "scorer_population":
        path = root / "mahalanobis.npz"
        scorer = MahalanobisScorer.load(path)
        MahalanobisScorer(scorer.means,scorer.cholesky,scorer.class_counts+1,
                         scorer.regularization,scorer.covariance_floor,scorer.provenance).save(path)
    else:
        (parent / "status.json").write_text(json.dumps({"state":"FAILED", "cell_fingerprint":cell["cell_fingerprint"]}))
    _resign_cell(out, cell)
    with pytest.raises(ValueError):
        mx.aggregate(cfg(), data, out, allow_partial=True)


@pytest.mark.parametrize("drift", ["source", "data", "config", "runtime"])
def test_plan_identity_drift_prevents_any_execution(dataset, tmp_path, monkeypatch, drift):
    _, _, data = dataset
    out = tmp_path / "matrix"
    plan = mx.write_plan(cfg(), data, out)
    configuration = cfg()
    if drift == "source":
        monkeypatch.setattr(lk,"_source_identity",lambda:{"revision":"other", "files_sha256":{"fixture":"1"*64}})
    elif drift == "data":
        original = lk._plan_header
        monkeypatch.setattr(lk,"_plan_header",lambda p:(original(p)[0],"e"*64))
    elif drift == "runtime":
        original = lk._runtime_identity()
        monkeypatch.setattr(lk,"_runtime_identity",lambda:{**original,"torch_threads":original["torch_threads"]+1})
    else: configuration = replace(configuration,training={**configuration.training,"width":2})
    monkeypatch.setattr(lk,"run_smoke",lambda *_a,**_k:pytest.fail("identity drift reached fitting"))
    with pytest.raises(ValueError, match="identity mismatch"):
        mx.run_bounded(configuration,data,out,selected=[plan["cells"][0]["id"]])
    assert not (out / "selection.json").exists()


def test_incomplete_cell_is_not_silently_refit_or_aggregated(dataset, tmp_path, monkeypatch):
    _, _, data = dataset
    out = tmp_path / "matrix"
    plan = mx.write_plan(cfg(),data,out)
    cell = plan["cells"][0]
    parent = out / "cells" / cell["id"]
    parent.mkdir(parents=True)
    (parent / "status.json").write_text('{"state":"RUNNING"}')
    monkeypatch.setattr(lk,"run_smoke",lambda *_a,**_k:pytest.fail("incomplete cell refitted"))
    with pytest.raises(ValueError,match="incomplete"):
        mx.run_bounded(cfg(),data,out,selected=[cell["id"]],reuse=True)
    with pytest.raises(ValueError,match="incomplete"):
        mx.aggregate(cfg(),data,out,allow_partial=True)


def test_resigned_selection_cannot_reset_the_global_cell_budget(completed, monkeypatch):
    data,out,plan,cell=completed
    replacement=[plan["cells"][1]["id"],plan["cells"][2]["id"]]
    path=out / "selection.json"
    declaration=json.loads(path.read_text())
    declaration["selected"]=replacement
    declaration["selection_fingerprint"]=fingerprint({k:v for k,v in declaration.items() if k!="selection_fingerprint"})
    path.write_text(json.dumps(declaration))
    monkeypatch.setattr(lk,"run_smoke",lambda *_a,**_k:pytest.fail("global two-cell budget was reset"))
    with pytest.raises(ValueError,match="previously attempted"):
        mx.run_bounded(cfg(),data,out,selected=replacement,reuse=True,bootstrap=10)
    assert sorted(p.name for p in (out / "cells").iterdir()) == [cell["id"]]


@pytest.mark.parametrize("mutation", ['"benchmark_complete": true,', '"bad": NaN,', '"bad": 1e400,'])
def test_strict_json_plan_rejects_duplicates_nonfinite_and_flags(dataset, tmp_path, mutation):
    _, _, data = dataset
    out = tmp_path / "matrix"
    mx.write_plan(cfg(),data,out)
    path = out / "plan.json"
    path.write_text('{'+mutation+path.read_text()[1:])
    with pytest.raises(ValueError):
        mx.aggregate(cfg(),data,out,allow_partial=True)


@pytest.mark.parametrize("target", ["data", "matrix", "existing"])
def test_read_only_aggregate_cli_cannot_overwrite_inputs_or_existing_work(completed, tmp_path, target):
    data, out, _, _ = completed
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(cfg().resolved()))
    path = data / "manifest.json" if target == "data" else out / "replacement.json" if target == "matrix" else tmp_path / "report.json"
    path.parent.mkdir(parents=True,exist_ok=True)
    if target == "existing": path.write_text("preserve")
    before = path.read_bytes() if path.exists() else None
    with pytest.raises(ValueError):
        mx.main(["aggregate","--config",str(config_path),"--data",str(data),"--out",str(out),"--partial","--report",str(path)])
    assert (path.read_bytes() if path.exists() else None) == before


def test_complete_statistical_summary_uses_seed_statistics_not_pooled_scores(dataset, monkeypatch):
    # Frozen stand-in score rows only: no model fits/sweep is executed.
    _, _, data = dataset
    plan = mx.build_matrix_plan(cfg(),data)
    verified = []
    for cell in plan["cells"]:
        rows = []
        for group in plan["declared_role_groups"]["test"]:
            for name in LABELS:
                held = name == cell["holdout_label"]
                rows.append({"scenario_id":group,"true_label":name,"is_unknown":held,
                             "prediction":"clean" if held else name,
                             "unknown_scores":{m:float(held) for m in cfg().methods}})
        methods = {m:{"ranking":{k:1.0 if k != "unknown_fpr_at_95_tpr" else 0.0 for k in lk.RANKING_KEYS}} for m in cfg().methods}
        verified.append({"cell":cell,"rows":rows,"result":{"methods":methods}})
    summary = mx._complete_summary(plan,verified,bootstrap=10)
    assert summary == mx._complete_summary(plan,list(reversed(verified)),bootstrap=10)
    assert len(summary["fold_view_summaries"]) == 7
    first = summary["fold_view_summaries"][0]["methods"]["msp"]
    assert first["n_training_seeds"] == 3 and first["seed_mean"]["unknown_auroc"] == 1.0
    assert first["seed_sample_sd"]["unknown_auroc"] == 0.0
    assert first["fixed_seed_models_group_ci"]["ci95"]["unknown_auroc"] == [1.0,1.0]
    assert summary["across_holdout_scores_pooled"] is False and summary["across_holdout_ci"] is None


def test_complete_summary_seed_spread_uses_sample_sd_separate_from_group_ci(dataset):
    _, _, data = dataset
    plan = mx.build_matrix_plan(cfg(),data)
    verified = []
    for cell in plan["cells"]:
        rows = []
        for group in plan["declared_role_groups"]["test"]:
            for name in LABELS:
                held = name == cell["holdout_label"]
                score = float(not held) if cell["seed"] == 0 else 0.5 if cell["seed"] == 1 else float(held)
                rows.append({"scenario_id":group,"true_label":name,"is_unknown":held,
                             "prediction":"clean" if held else name,
                             "unknown_scores":{m:score for m in cfg().methods}})
        h=np.asarray([r["is_unknown"] for r in rows]);s=np.asarray([r["unknown_scores"]["msp"] for r in rows])
        point=mx.ranking_metrics(s[~h],s[h],np.ones(int((~h).sum()),bool))
        verified.append({"cell":cell,"rows":rows,"result":{"methods":{m:{"ranking":point} for m in cfg().methods}}})
    result=mx._complete_summary(plan,verified,bootstrap=10)["fold_view_summaries"][0]["methods"]["msp"]
    assert result["seed_mean"]["unknown_auroc"] == 0.5
    assert result["seed_sample_sd"]["unknown_auroc"] == 0.5
    # Two identical physical groups cannot explain variation across trained models.
    assert result["fixed_seed_models_group_ci"]["ci95"]["unknown_auroc"] == [0.5,0.5]

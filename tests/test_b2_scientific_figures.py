"""Offline regeneration and independent source-to-figure arithmetic checks."""
import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("b2_atlas", ROOT / "scripts/plot_b2_scientific_results.py")
atlas = importlib.util.module_from_spec(spec)
spec.loader.exec_module(atlas)


@pytest.mark.parametrize("text", ['{"x":NaN}', '{"x":1e999}', '{"x":0,"x":1}'])
def test_plot_sources_reject_non_strict_json(tmp_path, text):
    path = tmp_path / "bad.json"
    path.write_text(text)
    with pytest.raises(ValueError):
        atlas.strict_json(path)


def test_source_tampering_fails_before_plotting(tmp_path, monkeypatch):
    name = "b2_a5_dual_pol_pilot.json"
    (tmp_path / name).write_text('{}')
    monkeypatch.setattr(atlas, "RESULTS", tmp_path)
    renderer = atlas.Atlas(tmp_path / "figures", tmp_path / "manifest.json")
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        renderer.read(name)


def test_representative_figures_regenerate_exactly_and_preserve_denominators(tmp_path):
    selected = ["A2_psd_plan_residual", "B1_cancellation_displacement", "C1_binary_baselines"]
    manifests = []
    for run in ("first", "second"):
        folder = tmp_path / run
        atlas.main(["--out", str(folder), "--manifest", str(tmp_path / (run + ".json")), "--only", *selected])
        manifests.append(atlas.strict_json(tmp_path / (run + ".json")))
    assert manifests[0] == manifests[1]
    figures = {f["id"]: f for f in manifests[0]["figures"]}
    assert set(figures) == set(selected)
    for f in figures.values():
        assert f["sources"] and f["dataset_identity"]
        assert f["n_groups"] and f["evidence_class"] == "BOUNDED_PILOT"
        for output in f["outputs"]:
            path = tmp_path / "first" / output["path"]
            assert atlas.sha(path) == output["sha256"]
            assert path.read_bytes() == (tmp_path / "second" / output["path"]).read_bytes()
            if path.suffix == ".png":
                with Image.open(path) as image:
                    assert image.width >= 2000 and abs(image.info["dpi"][0] - 300) < .1
            elif path.suffix == ".pdf":
                assert path.read_bytes().startswith(b"%PDF-")
            else:
                assert b"<svg" in path.read_bytes()
    source = atlas.strict_json(ROOT / "docs/results/b2_a5_dual_pol_pilot.json")
    index = {(i["perturbation"], i["scope"]): i for i in source["invocations"] if i["stage"] == "known"}
    delta = figures["B1_cancellation_displacement"]["plotted_values"]
    for p, row in zip(atlas.PERTURBATIONS, delta["RECEIVER_CONSISTENT"]):
        for scope, value in zip(atlas.SCOPES, row):
            if (p, scope) not in index:
                assert value is None
            else:
                i = index[(p, scope)]
                assert value == i["views"]["dual_residual"]["conditions"]["RECEIVER_CONSISTENT"]["cancellation_depth_core_db_displacement"]
                assert figures["B1_cancellation_displacement"]["n_scenes"][i["name"]] == i["populations"]["applied"]
    binary = atlas.strict_json(ROOT / "docs/results/b2_xgb_baseline.json")["binary"]
    values = figures["C1_binary_baselines"]["plotted_values"]
    for row, method in zip(values, binary.values()):
        for rate, entry in zip(row, method["known"]["per_class"].values()):
            assert entry["n"] == 2 and rate == entry["count"] / entry["n"]
    assert np.asarray(delta["MASK_ONLY"], dtype=float)[3, 0] == 0


def test_historical_fixtures_remain_separate_and_gates_closed():
    unified = atlas.strict_json(ROOT / "docs/results/b2_a5_dual_pol_pilot.json")
    partial = atlas.strict_json(ROOT / "docs/results/b2_a5_postmerge_partial_pilot.json")
    assert unified["source"]["known_data_fingerprint"] != partial["source"]["known_data_fingerprint"]
    assert unified["totals"]["invocations"] == 25 and partial["totals"]["invocations"] == 9
    for report in (unified, partial):
        assert report["benchmark_complete"] is False
        invocations = report["invocations"]
        assert sum(i["parity"]["n_scenes_checked"] for i in invocations) == report["totals"]["scenes_parity_checked"]
        assert len({(s["scenario_id"],s["label"]) for i in invocations for s in i["scenes"]}) == 8
    gates = atlas.strict_json(ROOT / "docs/plan/b2_readiness_gates_2026-10-21.json")
    assert gates["benchmark_complete"] is False
    for key in ("K18", "K17d", "OBS-CANCEL-2"):
        assert gates["decisions"][key]["status"] == "PENDING_RESEARCHER"
    for key in ("full_generation", "full_gpu_training", "full_loko_sweep"):
        assert gates["decisions"][key]["status"] == "NOT_AUTHORIZED"

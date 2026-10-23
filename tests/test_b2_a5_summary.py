"""Strict, traceable summary of bounded A5 invocations (scripts/summarize_b2_a5_pilot.py)."""
import importlib.util
import json
from pathlib import Path

import pytest

import b2_a5_support as support
from geoml import b2_a5 as a5

SCRIPT = Path(__file__).parent.parent / "scripts" / "summarize_b2_a5_pilot.py"
spec = importlib.util.spec_from_file_location("summarize_b2_a5_pilot", SCRIPT)
summary_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(summary_module)


@pytest.fixture(autouse=True)
def fakes(monkeypatch):
    support.install_fakes(monkeypatch)


def _invoke(tmp_path, name, **overrides):
    ws = support.workspace()
    config = a5.A5Config(**{"perturbation": "drop_one", "scope": "co_only", "n_groups": 1, "labels": ("clean", "unauthorized"),
                            "views": ("co", "dual_residual"), **overrides})
    a5.run_a5(config, ws / "known", ws / "runs", tmp_path / "runs" / name, log=lambda *_: None)


def test_summary_is_strict_json_traceable_and_labelled_as_a_pilot(tmp_path):
    _invoke(tmp_path, "a")
    _invoke(tmp_path, "b", scope="cross_only")
    out = tmp_path / "summary.json"
    summary_module.main(["--runs", str(tmp_path / "runs"), "--out", str(out), "--markdown", str(tmp_path / "t.md")])
    data = json.loads(out.read_text(), parse_constant=lambda c: pytest.fail(f"non-finite constant {c}"))
    assert data["benchmark_complete"] is False and data["evidence_class"] == "BOUNDED_PILOT"
    assert data["totals"]["invocations"] == 2 and data["totals"]["all_parity_exact"] is True
    assert data["totals"]["physical_replays"] == 4 and data["totals"]["receiver_recomputations"] == 2
    assert [i["name"] for i in data["invocations"]] == ["a", "b"] and len(data["invocations"][0]["results_sha256"]) == 64
    assert "recognition-quality evidence" in data["interpretation"]["what_this_is_not"]
    assert "MASK_ONLY" in (tmp_path / "t.md").read_text()


def test_summary_refuses_modified_or_foreign_results(tmp_path):
    _invoke(tmp_path, "a")
    path = tmp_path / "runs" / "a" / "results.json"
    path.write_text(path.read_text().replace("BOUNDED_PILOT", "BOUNDED_PILOX"))
    with pytest.raises(SystemExit):
        summary_module.main(["--runs", str(tmp_path / "runs"), "--out", str(tmp_path / "s.json")])
    with pytest.raises(SystemExit):
        summary_module.main(["--runs", str(tmp_path / "empty"), "--out", str(tmp_path / "s.json")])

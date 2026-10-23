"""Strict, traceable summary of bounded A5 invocations (scripts/summarize_b2_a5_pilot.py)."""
import importlib.util
import json
import shutil
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
    assert data["totals"]["invocations"] == 2 and data["totals"]["all_checked_parity_exact"] is True
    assert data["totals"]["invocations_with_parity_check"] == 2 and data["totals"]["invocations_without_parity_check"] == 0
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


def test_summary_compares_every_shared_identity_across_stages_and_orders(tmp_path):
    ws = support.workspace()
    _invoke(tmp_path, "b_known")
    config = a5.A5Config(perturbation="authorize_intruder", scope="co_only", stage="matched", n_groups=1,
                         labels=("unauthorized",), views=("co", "dual_residual"))
    a5.run_a5(config, ws / "known", ws / "runs", tmp_path / "runs" / "a_matched", matched_data=ws / "matched", log=lambda *_: None)
    _invoke(tmp_path, "c_known", scope="cross_only")
    out = tmp_path / "ok.json"
    summary_module.main(["--runs", str(tmp_path / "runs"), "--out", str(out), "--checkpoint-note", "unit-test stand-ins"])
    data = json.loads(out.read_text())
    assert set(data["source"]["stage_identities"]) == {"known", "matched"} and data["interpretation"]["checkpoints"] == "unit-test stand-ins"
    assert data["totals"]["invocations_without_parity_check"] == 0
    for name, field, value in (("a_matched", ("frozen_models", "dual_residual", "checkpoint_sha256"), "0" * 64),
                               ("c_known", ("source", "known_data_fingerprint"), "0" * 64),
                               ("b_known", ("implementation", "source_tree_fingerprint"), "0" * 64),
                               ("a_matched", ("source", "matched_data_fingerprint"), None)):
        copy = tmp_path / f"tampered-{name}-{field[-1]}"
        shutil.copytree(tmp_path / "runs", copy)
        results = copy / name / "results.json"
        payload = json.loads(results.read_text())
        node = payload
        for key in field[:-1]:
            node = node[key]
        node[field[-1]] = value
        results.write_text(json.dumps(payload))
        (copy / name / "results.json.sha256").write_text(summary_module._sha(results) + "\n")     # a consistent re-sign: only identity checks can catch it
        with pytest.raises(SystemExit):
            summary_module.main(["--runs", str(copy), "--out", str(tmp_path / "bad.json")])


def test_invocations_without_scenes_are_counted_not_called_exact(tmp_path):
    _invoke(tmp_path, "a", perturbation="authorize_intruder", labels=("clean",))
    out = tmp_path / "s.json"
    summary_module.main(["--runs", str(tmp_path / "runs"), "--out", str(out)])
    totals = json.loads(out.read_text())["totals"]
    assert totals["invocations_without_parity_check"] == 1 and totals["invocations_with_parity_check"] == 0
    assert totals["all_checked_parity_exact"] is None and totals["scenes_parity_checked"] == 0


def test_uninventoried_or_partial_results_never_claim_full_matrix_completion(tmp_path):
    name = "known_drop_one_co_only"
    _invoke(tmp_path, name)
    summary = summary_module.summarize(tmp_path / "runs")
    assert summary["matrix_coverage"]["matrix_complete"] is False
    assert summary["matrix_coverage"]["matrix_status"] == "UNINVENTORIED"
    result = summary_module._load(tmp_path / "runs" / name)
    coverage = {"schema": "B2-A5-matrix-status/1", "benchmark_complete": False,
                "matrix_complete": False, "matrix_status": "PARTIAL",
                "totals": {"inventory": 25, "completed": 1, "pending": 24, "failed": 0, "missing": 0},
                "invocations": [{"name": name, "status": "completed", "results_sha256": result["sha256"],
                                 "experiment_fingerprint": result["data"]["experiment_fingerprint"]},
                                *[{"name": n, "status": "skipped"} for n in summary_module.EXPECTED_INVOCATIONS - {name}]]}
    path = tmp_path / "runs" / "matrix_status.json"
    path.write_text(json.dumps(coverage))
    summary = summary_module.summarize(tmp_path / "runs")
    assert summary["matrix_coverage"]["matrix_status"] == "PARTIAL"
    assert "pending=24" in summary_module.markdown(summary)
    coverage["matrix_status"] = "COMPLETE"
    path.write_text(json.dumps(coverage))
    with pytest.raises(ValueError, match="completion status"):
        summary_module.summarize(tmp_path / "runs")
    coverage["matrix_status"] = "PARTIAL"
    coverage["totals"]["completed"] = 25
    path.write_text(json.dumps(coverage))
    with pytest.raises(ValueError, match="totals"):
        summary_module.summarize(tmp_path / "runs")
    coverage["totals"]["completed"] = 1
    coverage["matrix_complete"] = True
    path.write_text(json.dumps(coverage))
    with pytest.raises(ValueError, match="completion flag"):
        summary_module.summarize(tmp_path / "runs")
    coverage["invocations"] = coverage["invocations"][:1]
    path.write_text(json.dumps(coverage))
    with pytest.raises(ValueError, match="25 canonical"):
        summary_module.summarize(tmp_path / "runs")


@pytest.mark.parametrize("extra", [', "benchmark_complete": false', ', "bad": NaN'])
def test_checksummed_non_strict_json_is_rejected(tmp_path, extra):
    _invoke(tmp_path, "a")
    path = tmp_path / "runs" / "a" / "results.json"
    path.write_text(path.read_text().rstrip()[:-1] + extra + '}')
    path.with_name('results.json.sha256').write_text(summary_module._sha(path))
    with pytest.raises(ValueError):
        summary_module.summarize(tmp_path / "runs")

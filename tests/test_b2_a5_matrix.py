"""Orchestration failures must not become successful A5 matrix evidence."""
import importlib.util
import json
import hashlib
from pathlib import Path
from types import SimpleNamespace
import subprocess
import os
import sys

import pytest

SCRIPT = Path(__file__).parents[1] / "scripts" / "b2_a5_matrix.py"
spec = importlib.util.spec_from_file_location("b2_a5_matrix", SCRIPT)
matrix = importlib.util.module_from_spec(spec)
spec.loader.exec_module(matrix)


def _result(command, **overrides):
    out = Path(command[command.index("--out") + 1])
    stage = "matched" if "--matched-data" in command else "known"
    value = {
        "contract": "B2-A5-eval/1", "benchmark_complete": False,
        "experiment_fingerprint": "a" * 64,
        "configuration": {"stage": stage, "perturbation": command[command.index("--perturbation") + 1],
                          "scope": command[command.index("--scope") + 1], "n_groups": 2,
                          "labels": ["adjacent_satellite", "unauthorized"] if stage == "matched" else ["clean", "unauthorized"]},
        "populations": {"selected": 4, "applied": 4, "not_applicable": {}, "blocked": {}},
        "counts": {"physical_replays": 4, "cancellation_evaluations": 8},
        "views": {"co": {"available": True}, "dual": {"available": False, "reason": "fixture"}},
        **overrides,
    }
    out.mkdir(parents=True, exist_ok=True)
    path = out / "results.json"
    path.write_text(json.dumps(value, allow_nan=False))
    (out / "results.json.sha256").write_text(hashlib.sha256(path.read_bytes()).hexdigest() + "\n")


def _success(command, **kwargs):
    _result(command)
    kwargs["stdout"].write("completed fixture\n")
    return SimpleNamespace(returncode=0)


def _run(tmp_path, **kwargs):
    return matrix.run_matrix("data", "matched", "runs", tmp_path, **kwargs)


def test_inventory_preserves_existing_25_invocation_semantics():
    entries = matrix.inventory()
    assert len(entries) == 25 and len({v["name"] for v in entries}) == 25
    assert sum(v["stage"] == "known" for v in entries) == 19
    assert sum(v["stage"] == "matched" for v in entries) == 6
    assert entries[0]["name"] == "known_none_both"


def test_python_failure_preserves_full_log_and_exit_without_tail_masking(tmp_path):
    def failure(command, **kwargs):
        kwargs["stdout"].write("first diagnostic\nsecond diagnostic\nthird\nfourth\n")
        return SimpleNamespace(returncode=17)
    result, code = _run(tmp_path, only=["known_none_both"], runner=failure)
    assert code == 1 and result["matrix_status"] == "FAILED" and not result["matrix_complete"]
    failed = next(v for v in result["invocations"] if v["selected"])
    assert failed["exit_code"] == 17 and failed["status"] == "failed"
    assert "first diagnostic" in Path(failed["log_path"]).read_text()
    assert "fourth" in Path(failed["log_path"]).read_text()


def test_successful_subset_is_partial_with_explicit_unexecuted_inventory(tmp_path):
    result, code = _run(tmp_path, only=["known_none_both"], runner=_success)
    assert code == 3 and result["matrix_status"] == "PARTIAL" and not result["matrix_complete"]
    assert result["selection_complete"] and result["totals"]["completed"] == 1
    assert result["totals"]["skipped"] == 24 and result["totals"]["pending"] == 24
    assert len(result["invocations"]) == 25
    assert result["totals"]["unavailable_views"] == 1
    assert json.loads((tmp_path / "matrix_status.json").read_text())["matrix_status"] == "PARTIAL"


def test_checksum_valid_foreign_result_is_never_skipped(tmp_path):
    name = "known_none_both"
    fake = ["--out", str(tmp_path/name), "--perturbation", "none", "--scope", "both"]
    _result(fake, experiment_fingerprint="foreign")
    calls = []
    def rejects_current_provenance(command, **kwargs):
        calls.append(command)
        kwargs["stdout"].write("different experiment identity\n")
        return SimpleNamespace(returncode=2)
    result, code = _run(tmp_path, only=[name], runner=rejects_current_provenance)
    assert len(calls) == 1 and code == 1 and result["totals"]["failed"] == 1


def test_zero_exit_without_complete_result_is_missing_not_success(tmp_path):
    result, code = _run(tmp_path, only=["known_none_both"], runner=lambda *a, **kw: SimpleNamespace(returncode=0))
    assert code == 1 and result["totals"]["missing"] == 1 and result["totals"]["completed"] == 0
    assert not result["selection_complete"]


def test_result_configuration_mismatch_after_zero_exit_is_rejected(tmp_path):
    def wrong_config(command, **kwargs):
        _result(command, configuration={"stage": "known", "perturbation": "phantom", "scope": "both", "n_groups": 2,
                                       "labels": ["clean", "unauthorized"]})
        return SimpleNamespace(returncode=0)
    result, code = _run(tmp_path, only=["known_none_both"], runner=wrong_config)
    assert code == 1 and result["totals"]["failed"] == 1


@pytest.mark.parametrize("budget", [{"max_invocations": 0}, {"max_physical_replays": 15}, {"max_cancellations": 23}])
def test_budget_rejection_occurs_before_any_python_call(tmp_path, budget):
    calls = []
    result, code = _run(tmp_path, only=["known_none_both"], runner=lambda *a, **k: calls.append(a), **budget)
    assert calls == [] and code == 2 and result["matrix_status"] == "BUDGET_REJECTED"
    assert result["totals"]["blocked"] == 1


def test_default_budget_refuses_unselected_full_matrix_before_start(tmp_path):
    calls = []
    result, code = _run(tmp_path, runner=lambda *a, **k: calls.append(a))
    assert calls == [] and code == 2 and result["planned_upper_bounds"]["physical_replays"] == 400


def test_interruption_resumes_through_existing_cli_and_preserves_attempt_logs(tmp_path):
    calls = []
    def interrupted(command, **kwargs):
        calls.append(command)
        kwargs["stdout"].write("interrupted after state commit\n")
        raise KeyboardInterrupt
    first, code = _run(tmp_path, only=["known_none_both"], runner=interrupted)
    assert code == 130 and first["matrix_status"] == "INTERRUPTED"
    second, code = _run(tmp_path, only=["known_none_both"], runner=_success)
    item = next(v for v in second["invocations"] if v["selected"])
    assert code == 3 and item["attempt"] == 2
    assert (tmp_path / "known_none_both" / "matrix_attempt_0001.log").is_file()
    assert (tmp_path / "known_none_both" / "matrix_attempt_0002.log").is_file()


def test_timeout_is_failed_and_remaining_budget_explicit(tmp_path):
    def timeout(command, **kwargs):
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])
    result, code = _run(tmp_path, only=["known_none_both"], runner=timeout)
    assert code == 1 and result["totals"]["failed"] == 1
    assert next(v for v in result["invocations"] if v["selected"])["exit_code"] == 124


def test_nonapplicable_blocked_and_unavailable_counts_are_not_missing(tmp_path):
    def special(command, **kwargs):
        _result(command, populations={"selected": 4, "applied": 1, "not_applicable": {"no gap": 2}, "blocked": {"validator": 1}})
        return SimpleNamespace(returncode=0)
    result, code = _run(tmp_path, only=["known_none_both"], runner=special)
    assert code == 3 and result["totals"]["not_applicable_scenes"] == 2
    assert result["totals"]["blocked_scenes"] == 1 and result["totals"]["applied_scenes"] == 1
    assert result["totals"]["missing"] == 0


def test_plan_only_writes_inventory_without_starting_any_python(tmp_path):
    calls = []
    result, code = _run(tmp_path, only=["known_none_both"], plan=True, runner=lambda *a, **k: calls.append(a))
    assert calls == [] and code == 0 and result["matrix_status"] == "PLANNED"
    assert not result["matrix_complete"] and result["planned_upper_bounds"]["physical_replays"] == 16


def test_full_matrix_requires_explicit_overall_budget_and_all_verified_results(tmp_path):
    result, code = _run(tmp_path, runner=_success, max_invocations=25, max_physical_replays=400, max_cancellations=600)
    assert code == 0 and result["matrix_complete"] and result["totals"]["completed"] == 25


@pytest.mark.parametrize("names", [["typo"], ["known_none_both", "known_none_both"]])
def test_invalid_or_duplicate_selection_cannot_silently_change_coverage(tmp_path, names):
    with pytest.raises(ValueError):
        _run(tmp_path, only=names, runner=_success)


def test_real_shell_python_failure_propagates_and_keeps_early_stderr(tmp_path):
    """Actual subprocesses, with a non-RF stand-in module, exercise the wrapper."""
    package = tmp_path / "stub" / "geoml"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    (package / "b2_a5.py").write_text(
        "import sys\nprint('first Python diagnostic', file=sys.stderr)\n"
        "print('middle')\nprint('end')\nraise SystemExit(17)\n")
    out = tmp_path / "out"
    command = ["bash", str(SCRIPT.with_name("run_b2_a5_pilot_matrix.sh")), "data", "matched", "runs", str(out),
               "--only", "known_none_both"]
    result = subprocess.run(command, env={**os.environ, "PYTHON": sys.executable, "PYTHONPATH": str(package.parent)},
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 1 and "MATRIX_FAILED" in result.stdout
    status = json.loads((out / "matrix_status.json").read_text())
    invocation = next(v for v in status["invocations"] if v["selected"])
    assert invocation["exit_code"] == 17
    assert "first Python diagnostic" in Path(invocation["log_path"]).read_text()


@pytest.mark.parametrize("changes", [
    {"views": []}, {"counts": {"physical_replays": 17, "cancellation_evaluations": 0}},
    {"populations": {"selected": 4, "applied": 3, "not_applicable": {}, "blocked": {}}},
])
def test_checksum_valid_corrupt_result_shape_caps_or_denominators_fail(tmp_path, changes):
    def corrupt(command, **kwargs):
        _result(command, **changes)
        return SimpleNamespace(returncode=0)
    result, code = _run(tmp_path, only=["known_none_both"], runner=corrupt)
    assert code == 1 and result["totals"]["failed"] == 1 and not result["matrix_complete"]


@pytest.mark.parametrize("corrupt", [lambda text: '{"contract":"foreign",' + text[1:],
                                       lambda text: text.replace('false', 'NaN', 1)])
def test_strict_json_rejects_duplicate_keys_and_nonfinite_values(tmp_path, corrupt):
    def invalid_json(command, **kwargs):
        _result(command)
        path = Path(command[command.index("--out") + 1]) / "results.json"
        path.write_text(corrupt(path.read_text()))
        path.with_name("results.json.sha256").write_text(hashlib.sha256(path.read_bytes()).hexdigest())
        return SimpleNamespace(returncode=0)
    result, code = _run(tmp_path, only=["known_none_both"], runner=invalid_json)
    assert code == 1 and result["totals"]["failed"] == 1


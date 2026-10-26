"""Command safety for the local dashboard: allowlist, typed parameters, argv templates and environment.

CPU-only and synthetic. No command is executed here; argv and environments are built and inspected.
"""
import ast
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "dashboard"), str(ROOT / "src"), str(ROOT)]

from geodash import commands as C  # noqa: E402
from geodash.paths import LocationError  # noqa: E402

JOB_DIR = Path("/tmp/geo-dashboard-test-run/jobs/20260101T000000-abcdef")


def _python():
    return sys.executable


# ---- the allowlist itself -------------------------------------------------------------------------------

def test_every_registered_command_has_an_allowed_scope_and_a_fixed_title():
    assert set(C.REGISTRY) == {"real-exercise", "preflight-gates", "host-inventory", "test-dashboard",
                               "test-cpu-execution"}
    for key, spec in C.REGISTRY.items():
        assert spec.key == key
        assert spec.scope in (C.SCOPE_DEVELOPMENT, C.SCOPE_READ_ONLY, C.SCOPE_CPU_TEST)
        assert spec.title and spec.description
        assert 0 < spec.timeout_s <= 6 * 3600


@pytest.mark.parametrize("word", ["production", "gpu", "loko", "cuda", "launch", "authoriz", "held-out", "heldout"])
def test_no_command_key_or_title_names_a_protected_capability(word):
    for key, spec in C.REGISTRY.items():
        assert word not in key.lower()
        assert word not in spec.title.lower()


def test_only_the_expected_parameters_exist_and_each_is_an_enumerated_choice():
    for spec in C.REGISTRY.values():
        for param in spec.params:
            assert param.choices, f"{spec.key}.{param.name} must enumerate its choices"
            assert param.default in param.choices
    groups = C.REGISTRY["real-exercise"].params[0]
    assert groups.name == "groups" and groups.choices == (1, 2)


# ---- parameter validation --------------------------------------------------------------------------------

@pytest.mark.parametrize("values", [
    {"groups": 3}, {"groups": 0}, {"groups": -1}, {"groups": "1"}, {"groups": True}, {"groups": 1.0},
    {"groups": None}, {"groups": "1; rm -rf /"}, {"groups": "--device cuda"}, {"out": "/etc"},
    {"groups": 1, "extra": "x"},
])
def test_real_exercise_refuses_every_value_outside_its_enumerated_choices(values):
    with pytest.raises(C.CommandRefused):
        C.validate("real-exercise", values)


def test_unknown_command_names_are_refused_even_when_they_look_plausible():
    for key in ("b2_real_execution", "scripts/b2_real_execution.py", "real-exercise --groups 2", "", None,
                "preflight-gates; echo x", "../real-exercise"):
        with pytest.raises(C.CommandRefused):
            C.validate(key)


@pytest.mark.parametrize("role", ["test", "test-matched", "--role=test", "train; echo", "", None, 1])
def test_host_inventory_role_is_only_generation_or_training(role):
    with pytest.raises(C.CommandRefused):
        C.validate("host-inventory", {"role": role})


def test_defaults_are_accepted_and_typed():
    spec, resolved = C.validate("real-exercise")
    assert resolved == {"groups": 1} and type(resolved["groups"]) is int
    spec, resolved = C.validate("host-inventory")
    assert resolved == {"role": "generation"}


# ---- argv templates -----------------------------------------------------------------------------------

def test_real_exercise_argv_is_the_fixed_template_with_a_job_folder_output():
    argv = C.build_argv("real-exercise", {"groups": 2}, JOB_DIR, python=_python())
    assert argv == [_python(), "scripts/b2_real_execution.py", "--out", str(JOB_DIR / "exercise"),
                    "--groups", "2"]


def test_outputs_of_real_exercise_must_lie_outside_the_repository():
    inside_repo = ROOT / "runs" / "gui-test-job"
    with pytest.raises(LocationError):
        C.build_argv("real-exercise", {"groups": 1}, inside_repo, python=_python())


def test_read_only_commands_never_contain_an_output_outside_their_job_folder():
    argv = C.build_argv("host-inventory", {"role": "training"}, JOB_DIR, python=_python())
    assert argv[-1] == str(JOB_DIR / "host.json")
    assert argv[1] == "scripts/b2_host_inventory.py" and "training" in argv


def test_preflight_gates_is_read_only_and_takes_no_user_input():
    argv = C.build_argv("preflight-gates", {}, JOB_DIR, python=_python())
    assert argv == [_python(), "scripts/b2_production_preflight.py", "gates"]


def test_test_commands_run_only_pytest_on_named_files():
    dashboard = C.build_argv("test-dashboard", {}, JOB_DIR, python=_python())
    assert dashboard[1:3] == ["-m", "pytest"]
    assert [p for p in dashboard if p.startswith("tests/")] == list(C.DASHBOARD_TESTS)
    cpu = C.build_argv("test-cpu-execution", {}, JOB_DIR, python=_python())
    assert [p for p in cpu if p.startswith("tests/")] == list(C.CPU_EXECUTION_TESTS)


def test_every_argv_is_free_of_user_strings_beyond_enumerated_values():
    for key, spec in C.REGISTRY.items():
        choices = [{p.name: p.default} for p in spec.params] or [{}]
        for values in choices:
            for item in C.build_argv(key, values, JOB_DIR, python=_python()):
                assert not item.startswith("--device") and "cuda" not in item.lower()
                assert "--stage" not in item and "--authorize" not in item and "--execute" not in item


# ---- second-line guard: refusals -------------------------------------------------------------------------

@pytest.mark.parametrize("argv", [
    [_python(), "scripts/b2_production_supervisor.py", "run", "--execute"],
    [_python(), "scripts/b2_e10_k17d_identity.py", "--out", "x.json"],
    [_python(), "scripts/b2_real_generation.py", "--work", "w"],
    [_python(), "scripts/b2_training_footprint.py", "--out", "x"],
    [_python(), "-c", "import os"],
    [_python(), "-m", "geoml.b2_experiment", "--device", "cuda"],
    [_python(), "scripts/b2_real_execution.py", "--out", "x", "--device", "cuda"],
    [_python(), "scripts/b2_real_execution.py", "--out", "x", "--groups", "2", "--allow-test"],
    [_python(), "scripts/b2_real_execution.py", "--out", "x; rm -rf /"],
    [_python(), "scripts/b2_real_execution.py", "--out", "x && echo y"],
    [_python(), "scripts/b2_real_execution.py", "--out", "$(whoami)"],
    [_python(), "scripts/b2_real_execution.py", "--out", "x\nrm"],
    [_python(), "scripts/b2_real_execution.py", "--out", "x", "--roles", "test"],
    [],
    ["python", "-m", "os"],
])
def test_second_line_guard_refuses_unlisted_or_dangerous_argv(argv):
    spec = C.REGISTRY["real-exercise"]
    with pytest.raises(C.CommandRefused):
        C.assert_safe_argv(argv, spec)


def test_second_line_guard_accepts_each_allowlisted_template():
    for key in C.REGISTRY:
        spec = C.REGISTRY[key]
        values = {p.name: p.default for p in spec.params}
        C.assert_safe_argv(C.build_argv(key, values, JOB_DIR, python=_python()), spec)


def test_script_allowlist_matches_the_scripts_the_commands_can_run():
    used = set()
    for key, spec in C.REGISTRY.items():
        values = {p.name: p.default for p in spec.params}
        for item in C.build_argv(key, values, JOB_DIR, python=_python()):
            if item.startswith("scripts/"):
                used.add(item)
    assert used == set(C.SCRIPT_ALLOWLIST)
    for script in C.SCRIPT_ALLOWLIST:
        assert (ROOT / script).is_file(), f"allowlisted script is missing: {script}"


# ---- environment --------------------------------------------------------------------------------------

def test_environment_is_rebuilt_from_a_fixed_list_and_hides_cuda():
    base = {"PATH": "/usr/bin", "HOME": "/home/x", "SECRET_TOKEN": "do-not-pass", "CUDA_VISIBLE_DEVICES": "0",
            "LD_PRELOAD": "/tmp/evil.so", "PYTHONPATH": "/somewhere/else"}
    env = C.build_environment(base)
    assert "SECRET_TOKEN" not in env and "LD_PRELOAD" not in env
    assert env["CUDA_VISIBLE_DEVICES"] == ""
    assert env["PYTHONPATH"] == str(ROOT / "src")
    assert env["PYTHONHASHSEED"] == "0"
    assert env["OMP_NUM_THREADS"] == "2" and env["OPENBLAS_NUM_THREADS"] == "2"
    assert set(env) <= {"PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "USER", "LOGNAME", "PYTHONPATH",
                        "PYTHONHASHSEED", "PYTHONDONTWRITEBYTECODE", "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS",
                        "MKL_NUM_THREADS", "CUDA_VISIBLE_DEVICES"}


# ---- the runner's test files exist and do not read generated data --------------------------------------

@pytest.mark.parametrize("relative", list(C.CPU_EXECUTION_TESTS))
def test_allowlisted_cpu_test_files_exist_and_read_no_generated_directory(relative):
    """The runner executes these files, so none may read the generated run folders."""
    path = ROOT / relative
    assert path.is_file(), relative
    tree = ast.parse(path.read_text(encoding="utf-8"))
    literals = [node.value for node in ast.walk(tree) if isinstance(node, ast.Constant) and isinstance(node.value, str)]
    assert not [s for s in literals if s.startswith("data/") or s.startswith("runs/")], relative

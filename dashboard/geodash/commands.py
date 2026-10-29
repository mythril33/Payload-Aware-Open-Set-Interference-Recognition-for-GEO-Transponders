"""Allowlisted bounded development commands.

The dashboard can start only the commands below. Each one is a fixed template. The only user-chosen
values are members of enumerated choices (for example groups 1 or 2). There is no free text, no shell,
no path typed by the user, and no production, GPU, LOKO or held-out option. A command that is not in
REGISTRY cannot be started at all.
"""
from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping

from .paths import REPO_ROOT, assert_outside_repo

SCOPE_DEVELOPMENT = "BOUNDED_DEVELOPMENT"
SCOPE_READ_ONLY = "READ_ONLY"
SCOPE_CPU_TEST = "CPU_TEST"

DASHBOARD_TESTS = (
    "tests/test_dashboard_commands.py",
    "tests/test_dashboard_jobs.py",
    "tests/test_dashboard_portable.py",
    "tests/test_dashboard_results.py",
    "tests/test_dashboard_evidence.py",
    "tests/test_dashboard_rf.py",
    "tests/test_dashboard_diagnostics.py",
    "tests/test_dashboard_app.py",
)
CPU_EXECUTION_TESTS = (
    "tests/test_b2_execution.py",
    "tests/test_b2_e10_calibration.py",
)
# Scripts that may appear in an argv. Anything else is refused even if a template is changed by mistake.
SCRIPT_ALLOWLIST = frozenset({
    "scripts/b2_real_execution.py",
    "scripts/b2_production_preflight.py",
    "scripts/b2_host_inventory.py",
})
# Substrings that must never appear in a generated argv (no production, GPU or authority flags).
FORBIDDEN_ARGV_TOKENS = ("cuda", "--device", "--production", "--execute", "--authorize", "--allow",
                         "--acceptance", "loko", "gpu", "--stage", "--role-test", "test-matched", "--roles")
SHELL_METACHARACTERS = re.compile(r"[;&|`$<>\n\r]")
EXERCISE_SCHEMA = "B2-real-kernel-exercise/1"


class CommandRefused(ValueError):
    """A request that the allowlist does not accept."""


@dataclass(frozen=True)
class Param:
    name: str
    choices: tuple
    default: object
    label: str


@dataclass(frozen=True)
class CommandSpec:
    key: str
    title: str
    scope: str
    description: str
    params: tuple[Param, ...]
    builder: Callable[[dict, Path, str], list[str]]
    timeout_s: int
    success: Callable[[Path], tuple[bool, str]]
    outputs: tuple[str, ...] = ()
    # True for commands whose governed script chain uses POSIX-only mechanisms (fcntl file locks),
    # so they run on Linux or WSL2 but not on native Windows. Checked at call time by validate().
    requires_posix: bool = False


def current_platform_is_posix() -> bool:
    """Platform check consulted at call time by validate() and is_available().

    A module-level function so tests can monkeypatch geodash.commands.current_platform_is_posix
    to exercise the non-POSIX refusal on any platform.
    """
    return os.name == "posix"


def is_available(spec: CommandSpec) -> tuple[bool, str]:
    """Whether the command can run on this platform, and the reason when it cannot."""
    if spec.requires_posix and not current_platform_is_posix():
        return False, (f"{spec.key} requires a POSIX system (Linux or WSL2); not available on native Windows, "
                       "because its governed script chain uses POSIX-only file locks")
    return True, ""


def _python(python: str | None) -> str:
    return python or sys.executable


def _groups_choice() -> Param:
    return Param("groups", (1, 2), 1, "groups per development role (capped at 2)")


def _build_real_exercise(values: dict, job_dir: Path, python: str) -> list[str]:
    out = job_dir / "exercise"
    assert_outside_repo(out)
    return [_python(python), "scripts/b2_real_execution.py", "--out", str(out), "--groups", str(values["groups"])]


def _build_preflight_gates(values: dict, job_dir: Path, python: str) -> list[str]:
    return [_python(python), "scripts/b2_production_preflight.py", "gates"]


def _build_host_inventory(values: dict, job_dir: Path, python: str) -> list[str]:
    out = job_dir / "host.json"
    assert_outside_repo(out)
    return [_python(python), "scripts/b2_host_inventory.py", "--role", values["role"], "--out", str(out)]


def _build_test_dashboard(values: dict, job_dir: Path, python: str) -> list[str]:
    return [_python(python), "-m", "pytest", "-q", "-p", "no:cacheprovider", *DASHBOARD_TESTS]


def _build_test_cpu(values: dict, job_dir: Path, python: str) -> list[str]:
    return [_python(python), "-m", "pytest", "-q", "-p", "no:cacheprovider", *CPU_EXECUTION_TESTS]


def _exit_zero(job_dir: Path) -> tuple[bool, str]:
    return True, "exit status 0 is the only success criterion"


def _exercise_success(job_dir: Path) -> tuple[bool, str]:
    path = job_dir / "exercise" / "exercise.json"
    if not path.is_file():
        return False, "exercise.json was not written"
    report = json.loads(path.read_text(encoding="utf-8"))
    checks = {
        "schema": report.get("schema") == EXERCISE_SCHEMA,
        "scope": report.get("scope") == SCOPE_DEVELOPMENT,
        "heldout_reads": report.get("heldout_reads") == 0,
        "gpu_exercised": report.get("gpu_exercised") is False,
        "production_authorized": report.get("production_authorized") is False,
        "benchmark_complete": report.get("benchmark_complete") is False,
    }
    failed = sorted(name for name, ok in checks.items() if not ok)
    if failed:
        return False, "exercise.json fails its boundary fields: " + ", ".join(failed)
    return True, "exercise.json matches the bounded-development boundary"


def _host_success(job_dir: Path) -> tuple[bool, str]:
    return ((job_dir / "host.json").is_file(), "host.json written" if (job_dir / "host.json").is_file()
            else "host.json was not written")


REGISTRY: dict[str, CommandSpec] = {
    "real-exercise": CommandSpec(
        key="real-exercise",
        title="Bounded real RF to train to calibrate to freeze exercise",
        scope=SCOPE_DEVELOPMENT,
        description=("Runs scripts/b2_real_execution.py on CPU. It generates one or two development groups per "
                     "role (train, val-select, val-calib), trains a tiny dual_residual model, calibrates on "
                     "val-calib and freezes. It reads no held-out role and grants no production or GPU authority. "
                     "It needs Linux or WSL2, because its governed script chain uses POSIX-only file locks."),
        params=(_groups_choice(),),
        builder=_build_real_exercise,
        timeout_s=5400,
        success=_exercise_success,
        outputs=("exercise/exercise.json", "exercise/freeze.json"),
        requires_posix=True,
    ),
    "preflight-gates": CommandSpec(
        key="preflight-gates",
        title="Read-only gate inventory",
        scope=SCOPE_READ_ONLY,
        description="Runs scripts/b2_production_preflight.py gates. Reads the gate and memo files; writes nothing.",
        params=(),
        builder=_build_preflight_gates,
        timeout_s=300,
        success=_exit_zero,
    ),
    "host-inventory": CommandSpec(
        key="host-inventory",
        title="Read-only host inventory",
        scope=SCOPE_READ_ONLY,
        description="Runs scripts/b2_host_inventory.py for one role and writes host.json into the job folder.",
        params=(Param("role", ("generation", "training"), "generation", "host role"),),
        builder=_build_host_inventory,
        timeout_s=300,
        success=_host_success,
        outputs=("host.json",),
    ),
    "test-dashboard": CommandSpec(
        key="test-dashboard",
        title="Dashboard unit tests",
        scope=SCOPE_CPU_TEST,
        description="Runs the dashboard's own tests (adapters, readers, command safety, app smoke tests).",
        params=(),
        builder=_build_test_dashboard,
        timeout_s=1800,
        success=_exit_zero,
    ),
    "test-cpu-execution": CommandSpec(
        key="test-cpu-execution",
        title="CPU execution tests (synthetic fixtures)",
        scope=SCOPE_CPU_TEST,
        description=("Runs tests/test_b2_execution.py and tests/test_b2_e10_calibration.py. Both use synthetic "
                     "fixtures and do not read data/ or runs/."),
        params=(),
        builder=_build_test_cpu,
        timeout_s=1800,
        success=_exit_zero,
    ),
}


def validate(key: str, values: Mapping | None = None, registry: Mapping | None = None) -> tuple[CommandSpec, dict]:
    """Return the spec and the complete, typed parameter set, or refuse."""
    registry = REGISTRY if registry is None else registry
    if not isinstance(key, str) or key not in registry:
        raise CommandRefused(f"command {key!r} is not in the allowlist")
    spec = registry[key]
    available, why = is_available(spec)
    if not available:
        raise CommandRefused(why)
    values = dict(values or {})
    known = {p.name: p for p in spec.params}
    unknown = sorted(set(values) - set(known))
    if unknown:
        raise CommandRefused(f"parameters not accepted by {key}: {unknown}")
    resolved: dict = {}
    for param in spec.params:
        value = values.get(param.name, param.default)
        if isinstance(value, bool) or value not in param.choices or type(value) is not type(param.default):
            raise CommandRefused(f"{param.name}={value!r} is not one of {list(param.choices)}")
        resolved[param.name] = value
    return spec, resolved


def build_argv(key: str, values: Mapping | None, job_dir: Path, python: str | None = None,
               registry: Mapping | None = None) -> list[str]:
    spec, resolved = validate(key, values, registry)
    argv = spec.builder(resolved, Path(job_dir), python or sys.executable)
    assert_safe_argv(argv, spec)
    return argv


def assert_safe_argv(argv: list[str], spec: CommandSpec) -> None:
    """Second line of defence: refuse any argv that does not match an allowlisted shape."""
    if not argv or not all(isinstance(item, str) for item in argv):
        raise CommandRefused("argv must be a non-empty list of strings")
    for item in argv:
        if SHELL_METACHARACTERS.search(item):
            raise CommandRefused(f"shell metacharacters are not allowed in argv: {item!r}")
        # Paths are built by the server from the job folder, so only flags are checked for forbidden tokens.
        if item.startswith("-") and any(token in item.lower() for token in FORBIDDEN_ARGV_TOKENS):
            raise CommandRefused(f"argv contains a forbidden flag: {item!r}")
    if len(argv) >= 3 and argv[1] == "-m":
        if argv[2] != "pytest":
            raise CommandRefused(f"only pytest may run as a module, not {argv[2]!r}")
        return
    if len(argv) >= 2 and argv[1] in SCRIPT_ALLOWLIST:
        return
    raise CommandRefused(f"argv does not match an allowlisted template for {spec.key}")


def build_environment(base: Mapping[str, str] | None = None) -> dict[str, str]:
    """A fixed environment. Only listed variables are inherited; CUDA is hidden; no secrets are passed."""
    base = os.environ if base is None else base
    inherited = {k: base[k] for k in ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "USER", "LOGNAME") if k in base}
    inherited.update({
        "PYTHONPATH": str(REPO_ROOT / "src"),
        "PYTHONHASHSEED": "0",
        "PYTHONDONTWRITEBYTECODE": "1",
        "OMP_NUM_THREADS": "2",
        "OPENBLAS_NUM_THREADS": "2",
        "MKL_NUM_THREADS": "2",
        "CUDA_VISIBLE_DEVICES": "",
    })
    return inherited


__all__ = ["REGISTRY", "CommandSpec", "Param", "CommandRefused", "validate", "build_argv", "assert_safe_argv",
           "build_environment", "is_available", "current_platform_is_posix", "SCOPE_DEVELOPMENT",
           "SCOPE_READ_ONLY", "SCOPE_CPU_TEST", "DASHBOARD_TESTS", "CPU_EXECUTION_TESTS"]

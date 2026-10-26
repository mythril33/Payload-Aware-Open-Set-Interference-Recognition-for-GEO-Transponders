"""Environment diagnostics: Python, dependencies, CPU, memory, storage, GPU presence, last test results.

Read-only. No GPU context is created, no model is loaded and no data directory is opened.
"""
from __future__ import annotations

import os
import platform
import re
import shutil
import sys
from importlib import metadata
from pathlib import Path

from .paths import REPO_ROOT

DEPENDENCIES = ("numpy", "scipy", "matplotlib", "pytest", "torch", "xgboost", "streamlit")
REQUIRED_FOR_GUI = ("numpy", "scipy", "matplotlib", "streamlit")
REQUIRED_FOR_RUNNER = ("torch",)


def python_info() -> dict:
    return {"version": platform.python_version(), "executable": sys.executable,
            "implementation": platform.python_implementation(), "platform": platform.platform()}


def dependency_versions(names: tuple[str, ...] = DEPENDENCIES) -> dict[str, str | None]:
    found: dict[str, str | None] = {}
    for name in names:
        try:
            found[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            found[name] = None
    return found


def memory_facts(meminfo: Path = Path("/proc/meminfo")) -> dict:
    """Total and available RAM in GiB from /proc/meminfo. None where the file is not available."""
    if not meminfo.is_file():
        return {"total_gib": None, "available_gib": None, "source": "/proc/meminfo not available"}
    values = {}
    for line in meminfo.read_text(encoding="utf-8").splitlines():
        match = re.match(r"(MemTotal|MemAvailable):\s+(\d+)\s+kB", line)
        if match:
            values[match.group(1)] = int(match.group(2)) / (1024 ** 2)
    return {"total_gib": round(values.get("MemTotal"), 2) if "MemTotal" in values else None,
            "available_gib": round(values.get("MemAvailable"), 2) if "MemAvailable" in values else None,
            "source": "/proc/meminfo"}


def storage_facts(paths: dict[str, Path]) -> dict:
    facts = {}
    for label, path in paths.items():
        probe = path
        while not probe.exists() and probe != probe.parent:
            probe = probe.parent
        try:
            usage = shutil.disk_usage(probe)
            facts[label] = {"path": str(path), "free_gib": round(usage.free / 1024 ** 3, 2),
                            "total_gib": round(usage.total / 1024 ** 3, 2)}
        except OSError as error:
            facts[label] = {"path": str(path), "free_gib": None, "error": type(error).__name__}
    return facts


def cpu_facts() -> dict:
    return {"logical_cpus": os.cpu_count(), "architecture": platform.machine()}


def gpu_facts(which=shutil.which, device_dir: Path = Path("/dev")) -> dict:
    """Presence only. The dashboard never runs nvidia-smi queries that create a CUDA context."""
    smi = which("nvidia-smi")
    devices = sorted(p.name for p in device_dir.glob("nvidia*")) if device_dir.is_dir() else []
    if smi is None and not devices:
        return {"status": "no NVIDIA driver tool or device found", "mode": "CPU only"}
    return {"status": "NVIDIA tooling present; no GPU work is run by this dashboard", "mode": "CPU only",
            "device_nodes": devices}


def readiness(deps: dict[str, str | None]) -> dict:
    gui_missing = [name for name in REQUIRED_FOR_GUI if deps.get(name) is None]
    runner_missing = [name for name in REQUIRED_FOR_RUNNER if deps.get(name) is None]
    return {
        "gui_ready": not gui_missing,
        "gui_missing": gui_missing,
        "runner_ready": not runner_missing,
        "runner_missing": runner_missing,
        "note": "the runner needs torch (the .[ml] extra); install it as described in dashboard/README.md",
    }


def last_test_results(job_statuses: list, keys=("test-dashboard", "test-cpu-execution")) -> list[dict]:
    """The most recent result of each test command, with the pass count when pytest printed one."""
    out = []
    for key in keys:
        latest = next((job for job in job_statuses if job.key == key), None)
        if latest is None:
            out.append({"key": key, "state": "never run", "summary": ""})
            continue
        summary = ""
        for line in reversed(latest.log_tail):
            match = re.search(r"(\d+) passed(?:, (\d+) failed)?(?:, (\d+) skipped)?", line)
            if match:
                summary = line.strip()
                break
        out.append({"key": key, "state": latest.state, "summary": summary, "job_id": latest.job_id,
                    "finished_reason": latest.reason})
    return out


def snapshot(home: Path, repo: Path = REPO_ROOT) -> dict:
    deps = dependency_versions()
    return {
        "python": python_info(),
        "dependencies": deps,
        "readiness": readiness(deps),
        "cpu": cpu_facts(),
        "memory": memory_facts(),
        "storage": storage_facts({"repository": repo, "run folder (outside the repository)": home}),
        "gpu": gpu_facts(),
    }


__all__ = ["snapshot", "dependency_versions", "readiness", "memory_facts", "storage_facts", "cpu_facts",
           "gpu_facts", "last_test_results", "python_info", "DEPENDENCIES"]

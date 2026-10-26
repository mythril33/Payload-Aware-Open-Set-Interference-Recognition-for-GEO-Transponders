"""Repository version and gate status, read from committed files and git. Read-only."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from .paths import PLAN_DIR, REPO_ROOT, ensure_import_paths

GIT_TIMEOUT_S = 20
APPROVED_PROTOCOL = PLAN_DIR / "b2_e9_approved_scientific_protocol.json"
READINESS_GATES = PLAN_DIR / "b2_readiness_gates_2026-10-21.json"
EXPECTED_UNRESOLVED = {
    "full_generation": "NOT_AUTHORIZED",
    "gpu_probe": "NOT_AUTHORIZED",
    "full_gpu_training": "NOT_AUTHORIZED",
    "full_loko_sweep": "NOT_AUTHORIZED",
    "production_launch": "DISABLED",
    "merge_to_main": "REVIEW_REQUIRED",
}


def _git(args: list[str], cwd: Path = REPO_ROOT) -> str | None:
    try:
        done = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True,
                              timeout=GIT_TIMEOUT_S, check=False, shell=False)
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout.strip() if done.returncode == 0 else None


def git_state(cwd: Path = REPO_ROOT) -> dict:
    status = _git(["status", "--porcelain"], cwd)
    return {
        "branch": _git(["rev-parse", "--abbrev-ref", "HEAD"], cwd),
        "head": _git(["rev-parse", "--short", "HEAD"], cwd),
        "head_subject": _git(["log", "-1", "--format=%s"], cwd),
        "head_date": _git(["log", "-1", "--format=%ci"], cwd),
        "describe": _git(["describe", "--tags", "--always", "--dirty"], cwd),
        "uncommitted_files": None if status is None else len([line for line in status.splitlines() if line.strip()]),
    }


def project_version(repo: Path = REPO_ROOT) -> str | None:
    text = (repo / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', text, flags=re.MULTILINE)
    return match.group(1) if match else None


def runtime_permitted() -> tuple[bool | None, str]:
    """The execution contract's answer, read from the module. None if the import fails."""
    ensure_import_paths()
    try:
        from geoml import b2_e9_contract as contract
    except Exception as error:  # the dashboard must still start when the scientific stack is absent
        return None, f"contract could not be imported: {type(error).__name__}"
    return bool(contract.runtime_permitted()), "geoml.b2_e9_contract.runtime_permitted()"


def _load(path: Path) -> dict | None:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def gate_rows(repo: Path = REPO_ROOT) -> list[dict]:
    """One row per gate value. Values are copied from the committed records, never edited here."""
    rows: list[dict] = []
    protocol = _load(repo / "docs" / "plan" / APPROVED_PROTOCOL.name)
    if protocol is None:
        rows.append({"gate": "approved protocol", "value": "file absent", "source": APPROVED_PROTOCOL.name})
    else:
        for key in ("status", "scientific_approval", "activation", "production_authorized", "benchmark_complete"):
            rows.append({"gate": key, "value": protocol.get(key, "absent"),
                         "source": f"{APPROVED_PROTOCOL.name}: {key}"})
        unresolved = protocol.get("unresolved_operational_decisions", {})
        for key, expected in EXPECTED_UNRESOLVED.items():
            actual = unresolved.get(key, "absent")
            rows.append({"gate": f"operational: {key}", "value": actual,
                         "source": f"{APPROVED_PROTOCOL.name}: unresolved_operational_decisions.{key}",
                         "matches_expected": actual == expected})
    readiness = _load(repo / "docs" / "plan" / READINESS_GATES.name)
    if readiness is not None:
        rows.append({"gate": "readiness: benchmark_complete", "value": readiness.get("benchmark_complete", "absent"),
                     "source": f"{READINESS_GATES.name}: benchmark_complete"})
    return rows


CLOSURE_GATES = ("activation", "production_authorized", "benchmark_complete", "readiness: benchmark_complete")


def gate_summary(rows: list[dict]) -> str:
    """Closed only when every closure gate is False and every operational decision matches its expectation."""
    if not rows or any(r["value"] == "absent" for r in rows):
        return "gate records incomplete"
    closure = [r for r in rows if r["gate"] in CLOSURE_GATES]
    operational = [r for r in rows if "matches_expected" in r]
    if closure and all(r["value"] is False for r in closure) and all(r["matches_expected"] for r in operational):
        return "no compute or production gate is open"
    return "review the gate rows: a value differs from the closed state"


__all__ = ["git_state", "project_version", "runtime_permitted", "gate_rows", "gate_summary", "EXPECTED_UNRESOLVED"]

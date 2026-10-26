"""Filesystem roots and import paths for the local dashboard.

Pure Python: no Streamlit import. Generated artifacts (job outputs, logs, GUI state) live
outside the repository, the same rule that scripts/b2_real_execution.py enforces.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = REPO_ROOT / "src"
DASHBOARD_DIR = REPO_ROOT / "dashboard"
EVIDENCE_MAP_PATH = DASHBOARD_DIR / "data" / "evidence_map.json"
RESULTS_DIR = REPO_ROOT / "docs" / "results"
PLAN_DIR = REPO_ROOT / "docs" / "plan"


class LocationError(ValueError):
    """A path that must be outside the repository is inside it."""


def assert_outside_repo(path) -> Path:
    resolved = Path(path).expanduser().resolve()
    if resolved == REPO_ROOT or REPO_ROOT in resolved.parents:
        raise LocationError(f"{resolved} is inside the repository; generated artifacts must be outside it")
    return resolved


def run_home() -> Path:
    """Directory for job outputs and GUI state. Outside the repository by construction."""
    configured = os.environ.get("GEO_DASHBOARD_HOME")
    base = Path(configured) if configured else Path.home() / ".local" / "share" / "geo-dashboard"
    return assert_outside_repo(base)


def ensure_import_paths() -> None:
    """Make `geosim` and `geoml` importable from the source tree, without installing the package."""
    for path in (str(SRC_DIR), str(REPO_ROOT)):
        if path not in sys.path:
            sys.path.insert(0, path)

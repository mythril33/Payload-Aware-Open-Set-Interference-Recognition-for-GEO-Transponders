"""Shared Streamlit state. Imports Streamlit; keep UI-free logic in geodash/."""
from __future__ import annotations

from pathlib import Path

import streamlit as st

from geodash.jobs import JobManager
from geodash.paths import run_home


@st.cache_resource(show_spinner=False)
def _manager_for(home: str) -> JobManager:
    return JobManager(Path(home))


def job_manager() -> JobManager:
    """One manager per server process and run folder, so a running job survives page reruns. Keyed on the
    run folder, so a changed GEO_DASHBOARD_HOME never reuses a manager bound to another folder."""
    return _manager_for(str(run_home()))


def badge(text: str) -> str:
    return f"`{text}`"


CLASS_LABELS = {
    "VERIFIED_HISTORICAL": "Verified historical",
    "DEVELOPMENT_PILOT": "Development pilot",
    "UNEXECUTED": "Unexecuted",
    "GATE_OR_APPROVAL": "Gate or approval record",
    "DERIVED_DOCUMENTATION": "Derived documentation",
    "VERIFICATION_LOG": "Verification log",
    "RESTRICTED_HELDOUT_OBSERVATION": "Restricted: held-out observations",
    "PROTECTED_PRODUCTION": "Protected production evaluation",
    "UNCLASSIFIED": "Unclassified (unverified)",
    "STALE_MAP_ENTRY": "Stale map entry",
    "DEVELOPMENT_RUN": "Local development run",
}

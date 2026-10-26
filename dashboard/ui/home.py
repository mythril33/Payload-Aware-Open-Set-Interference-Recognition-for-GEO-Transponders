"""Dashboard: repository version, environment, datasets, models, records and execution gates."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from geodash import diagnostics, evidence, repo_status
from geodash.paths import REPO_ROOT, run_home

from .state import CLASS_LABELS, job_manager


def render() -> None:
    st.title("GEO research dashboard")
    st.caption("Simulation-only research repository. There is no field data (see DURUM section 5.5). "
               "Nothing on this page is a recognition-performance claim.")

    git = repo_status.git_state()
    version = repo_status.project_version()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Package version", version or "unknown")
    c2.metric("Branch", git.get("branch") or "unknown")
    c3.metric("Commit", git.get("head") or "unknown")
    dirty = git.get("uncommitted_files")
    c4.metric("Uncommitted files", "unknown" if dirty is None else dirty)
    if git.get("head_subject"):
        st.caption(f"HEAD: {git['head_subject']} ({git.get('head_date')})")

    st.subheader("Execution gates")
    rows = repo_status.gate_rows()
    st.info(repo_status.gate_summary(rows))
    runtime, source = repo_status.runtime_permitted()
    st.write(f"Execution contract: `{source}` returns **{runtime}**." if runtime is not None
             else f"Execution contract: {source}.")
    gate_table = pd.DataFrame(rows)
    gate_table["value"] = gate_table["value"].astype(str)
    st.dataframe(gate_table, hide_index=True, width="stretch")
    st.caption("Values are copied from the committed gate records. This application cannot change them, and it has "
               "no production launch control.")

    st.subheader("Environment readiness")
    deps = diagnostics.dependency_versions()
    ready = diagnostics.readiness(deps)
    e1, e2 = st.columns(2)
    e1.metric("Dashboard runs here", "yes" if ready["gui_ready"] else "missing: " + ", ".join(ready["gui_missing"]))
    e2.metric("Development runner", "yes" if ready["runner_ready"] else "missing: " + ", ".join(ready["runner_missing"]))
    st.caption(ready["note"])

    st.subheader("Datasets")
    data_dir = REPO_ROOT / "data"
    if data_dir.exists():
        st.write(f"`data/` exists in this checkout ({sum(1 for _ in data_dir.iterdir())} entries). Not tracked by Git.")
    else:
        st.write("No generated dataset in this checkout: `data/` is absent. Datasets produced by the development "
                 "runner are listed under Development runner, in the run folder outside the repository.")
    st.write(f"Run folder (outside the repository): `{run_home()}`")

    st.subheader("Models and experiment records")
    inventory = evidence.inventory()
    counts = evidence.counts_by_class(inventory)
    table = pd.DataFrame([{"class": CLASS_LABELS.get(k, k), "files": v} for k, v in counts.items()])
    st.dataframe(table, hide_index=True, width="stretch")
    protected = [e for e in inventory if e.evidence_class == evidence.PROTECTED_PRODUCTION]
    st.write(f"Protected production evaluations recorded: **{len(protected)}**. None exists, and none is "
             "authorized (gates above).")
    local_models = [j for j in job_manager().list_jobs() if j.key == "real-exercise" and j.stage == "complete"]
    st.write(f"Completed local development exercises (committed records are not affected): **{len(local_models)}**.")

    with st.expander("How to read these labels"):
        for key, legend in evidence.classes_legend().items():
            st.write(f"**{CLASS_LABELS.get(key, key)}** (`{key}`): {legend}")

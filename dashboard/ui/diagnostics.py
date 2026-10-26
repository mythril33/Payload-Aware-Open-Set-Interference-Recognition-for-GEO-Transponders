"""System diagnostics: Python, dependencies, CPU, memory, storage, GPU presence, tests and provenance."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from geodash import commands as C
from geodash import diagnostics, provenance
from geodash import jobs as J
from geodash.paths import LocationError, run_home

from .state import job_manager


def render() -> None:
    st.title("System diagnostics")
    st.caption("Read-only checks. Starting a test below runs an allowlisted command as a normal job.")
    snap = diagnostics.snapshot(run_home())

    st.subheader("Python and dependencies")
    st.write(f"Python {snap['python']['version']} ({snap['python']['implementation']}) at `{snap['python']['executable']}`")
    deps = [{"package": name, "version": version or "not installed"} for name, version in snap["dependencies"].items()]
    st.dataframe(pd.DataFrame(deps), hide_index=True, width="stretch")
    ready = snap["readiness"]
    st.write(f"Dashboard: {'ready' if ready['gui_ready'] else 'missing ' + ', '.join(ready['gui_missing'])}. "
             f"Runner: {'ready' if ready['runner_ready'] else 'missing ' + ', '.join(ready['runner_missing'])}.")
    if ready["gui_missing"] or ready["runner_missing"]:
        st.warning("Install the missing packages as described in the Setup guide, then restart the dashboard.")

    st.subheader("CPU, memory and storage")
    mem = snap["memory"]
    c1, c2, c3 = st.columns(3)
    c1.metric("Logical CPUs", snap["cpu"]["logical_cpus"])
    c2.metric("RAM total (GiB)", "unknown" if mem["total_gib"] is None else mem["total_gib"])
    c3.metric("RAM available (GiB)", "unknown" if mem["available_gib"] is None else mem["available_gib"])
    st.dataframe(pd.DataFrame(list(snap["storage"].values())), hide_index=True, width="stretch")
    st.write(f"GPU: {snap['gpu']['status']}. Mode: **{snap['gpu']['mode']}**.")

    st.subheader("Tests")
    manager = job_manager()
    jobs = manager.list_jobs()
    latest = diagnostics.last_test_results(jobs)
    st.dataframe(pd.DataFrame(latest), hide_index=True, width="stretch")
    running = [j for j in jobs if j.state == J.RUNNING]
    b1, b2 = st.columns(2)
    refusals = (C.CommandRefused, LocationError, J.ActiveJobError)
    if b1.button("Run dashboard tests", disabled=bool(running)):
        try:
            manager.start("test-dashboard")
            st.rerun()
        except refusals as error:  # refusals are shown, never hidden
            st.error(str(error))
    if b2.button("Run CPU execution tests", disabled=bool(running)):
        try:
            manager.start("test-cpu-execution")
            st.rerun()
        except refusals as error:
            st.error(str(error))
    if running:
        st.info(f"Job {running[0].job_id} ({running[0].title}) is running; test buttons are disabled until it ends.")

    st.subheader("Provenance and integrity")
    checks = provenance.all_checks()
    st.dataframe(pd.DataFrame([{"check": c.name, "status": c.status, "detail": c.detail} for c in checks]),
                 hide_index=True, width="stretch")
    st.caption("STALE means a record was generated from different source. It must be re-derived, not edited. "
               "Stale records are reported as found; this page does not change them.")

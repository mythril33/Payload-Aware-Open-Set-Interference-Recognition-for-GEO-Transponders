"""Safe development runner: allowlisted bounded commands only, with start, progress, logs and outputs."""
from __future__ import annotations

import json
import sys

import pandas as pd
import streamlit as st

from geodash import commands as C
from geodash import jobs as J
from geodash.paths import LocationError, run_home

from .state import job_manager

SCOPE_NOTE = {
    C.SCOPE_DEVELOPMENT: "Bounded development: CPU only, development roles only, fixed caps. No production or GPU authority.",
    C.SCOPE_READ_ONLY: "Read-only: reads files and writes at most one new file in the run folder.",
    C.SCOPE_CPU_TEST: "CPU test: synthetic fixtures; does not read data/ or runs/ and does not touch held-out roles.",
}


def _preview_argv(key: str, values: dict) -> list[str]:
    """The argv a start would use. Nothing is created: the job folder is a placeholder."""
    spec, resolved = C.validate(key, values)
    placeholder = run_home() / "jobs" / "<new-job-folder>"
    return spec.builder(resolved, placeholder, sys.executable)


@st.fragment(run_every=2)
def _active_panel(job_id: str) -> None:
    manager = job_manager()
    status = manager.status(job_id)
    st.markdown(f"**{status.title}**  ·  state: `{status.state}`  ·  elapsed {status.elapsed_s:.0f} s "
                f"of {status.timeout_s} s GUI timeout")
    if not status.is_final:
        st.progress(min(1.0, status.elapsed_s / max(1, status.timeout_s)),
                    text=f"time used: {status.elapsed_s:.0f} s of the {status.timeout_s} s limit "
                         f"(this bar measures time, not completion)")
        st.write(f"Stage (inferred from output files): **{status.stage or 'running'}**"
                 + (f" — {status.stage_detail}" if status.stage_detail else ""))
        if st.button("Cancel this job", key=f"cancel-{job_id}"):
            manager.cancel(job_id)
            st.rerun()
    else:
        st.info(f"Finished: `{status.state}`. {status.reason}")
    if status.generator_log_tail:
        st.write("RF generator log (written by the generator itself):")
        st.code("\n".join(status.generator_log_tail), language="text")
    st.write("Command output:")
    st.code("\n".join(status.log_tail[-60:]) or "(no output yet)", language="text")


def _show_outputs(status: J.JobStatus) -> None:
    if status.key == "real-exercise":
        report_path = status.job_dir / "exercise" / "exercise.json"
        if report_path.is_file():
            report = json.loads(report_path.read_text(encoding="utf-8"))
            st.subheader("Exercise report (exercise.json)")
            st.write("Boundary fields as recorded by the script:")
            st.table(pd.DataFrame([{
                "heldout_reads": report.get("heldout_reads"),
                "gpu_exercised": report.get("gpu_exercised"),
                "production_authorized": report.get("production_authorized"),
                "benchmark_complete": report.get("benchmark_complete"),
                "independent_backup_verified": report.get("independent_backup_verified"),
            }]))
            history = _find_history(report)
            if history is not None:
                st.subheader("Training history (as stored in the report)")
                st.line_chart(pd.DataFrame(history))
            else:
                st.caption("The report stores no per-epoch training history, so none is plotted.")
            st.download_button("Download exercise.json", report_path.read_bytes(), file_name="exercise.json")
            with st.expander("Full report"):
                st.json(report, expanded=False)
    host_path = status.job_dir / "host.json"
    if host_path.is_file():
        st.download_button("Download host.json", host_path.read_bytes(), file_name="host.json")
    if status.key == "real-exercise":
        st.caption(f"Output folder (outside the repository): `{status.job_dir / 'exercise'}`")


def _find_history(report: dict) -> list[dict] | None:
    """A per-epoch list of numeric dicts, if the report stores one. Nothing is synthesised."""
    for container in (report.get("training", {}), report):
        if isinstance(container, dict):
            value = container.get("history")
            if isinstance(value, list) and value and all(isinstance(row, dict) for row in value):
                numeric = [{k: v for k, v in row.items() if isinstance(v, (int, float)) and not isinstance(v, bool)}
                           for row in value]
                if all(numeric):
                    return numeric
    return None


def render() -> None:
    st.title("Development runner")
    st.caption("Starts only the allowlisted commands below, without a shell. The only user choices are the listed "
               "options. There is no free-text argument, no production option and no GPU option.")
    manager = job_manager()

    keys = list(C.REGISTRY)
    key = st.selectbox("Command", keys, format_func=lambda k: C.REGISTRY[k].title)
    spec = C.REGISTRY[key]
    st.write(SCOPE_NOTE[spec.scope])
    st.write(spec.description)

    values = {}
    for param in spec.params:
        values[param.name] = st.selectbox(param.label, list(param.choices),
                                          index=list(param.choices).index(param.default),
                                          key=f"param-{key}-{param.name}")
    st.caption(f"Timeout: {spec.timeout_s} s (enforced by this dashboard). Output folder: a new job folder under the "
               f"run folder, never inside the repository.")
    with st.expander("Exact command that would run"):
        try:
            st.code(" ".join(_preview_argv(key, values)), language="bash")
        except (C.CommandRefused, LocationError) as error:
            st.error(str(error))

    active = [job for job in manager.list_jobs() if job.state == J.RUNNING]
    if active:
        st.warning("A job is running. Only one bounded job runs at a time.")
        _active_panel(active[0].job_id)
    elif st.button("Start", type="primary", key=f"start-{key}"):
        try:
            job_id = manager.start(key, values)
        except (C.CommandRefused, LocationError, J.ActiveJobError) as error:
            st.error(str(error))
        else:
            st.success(f"Started job {job_id}.")
            st.rerun()

    st.subheader("Recent jobs")
    jobs = manager.list_jobs()
    if not jobs:
        st.write("No jobs have been run from this dashboard yet.")
        return
    table = pd.DataFrame([{"job": j.job_id, "command": j.key, "state": j.state, "elapsed (s)": round(j.elapsed_s),
                           "reason": j.reason} for j in jobs])
    st.dataframe(table, hide_index=True, width="stretch")

    chosen = st.selectbox("Inspect a job", [j.job_id for j in jobs], index=0)
    status = manager.status(chosen)
    st.write(f"State `{status.state}`, exit status {status.returncode}, stage `{status.stage or 'n/a'}`.")
    if status.state in (J.FAILED, J.TIMED_OUT, J.CANCELLED):
        st.error(f"Error details: {status.reason}")
    st.write("Command (argv, no shell):")
    st.code(" ".join(status.argv), language="bash")
    st.write("Log (last lines):")
    st.code("\n".join(status.log_tail) or "(empty)", language="text")
    _show_outputs(status)

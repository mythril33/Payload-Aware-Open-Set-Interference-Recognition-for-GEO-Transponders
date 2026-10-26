"""Experiment browser: every committed record and local run, labelled by its evidence class."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from geodash import evidence

from .state import CLASS_LABELS, job_manager


def render() -> None:
    st.title("Experiment browser")
    st.caption("Each file is labelled by its evidence class. Restricted files are listed but their values are never "
               "shown. Unclassified files are treated as unverified.")
    entries = evidence.inventory()
    classes = sorted({e.evidence_class for e in entries})
    chosen = st.multiselect("Show classes", classes, default=classes,
                            format_func=lambda c: CLASS_LABELS.get(c, c))
    rows = [{
        "class": CLASS_LABELS.get(e.evidence_class, e.evidence_class),
        "file": e.path,
        "held-out content in file": "yes (indicative count)" if e.has_heldout_content else "no",
        "values shown here": "yes" if e.values_displayable else "no (restricted)",
        "rationale": e.rationale,
    } for e in entries if e.evidence_class in chosen]
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

    st.subheader("Unexecuted experiments")
    unexecuted = [e for e in entries if e.evidence_class == evidence.UNEXECUTED]
    st.write("Proposals, specifications and matrices that have not been run. They show no results.")
    st.dataframe(pd.DataFrame([{"file": e.path, "why it is unexecuted": e.rationale} for e in unexecuted]),
                 hide_index=True, width="stretch")

    st.subheader("Protected production evaluations")
    protected = [e for e in entries if e.evidence_class == evidence.PROTECTED_PRODUCTION]
    st.write(f"Recorded: **{len(protected)}**. Production evaluation is NOT_AUTHORIZED in the gate records, so no such "
             "evaluation exists and none can be started from this application.")

    st.subheader("Local development runs (outside the repository)")
    runs = [j for j in job_manager().list_jobs() if j.key == "real-exercise"]
    if not runs:
        st.write("None yet.")
    else:
        st.dataframe(pd.DataFrame([{
            "class": CLASS_LABELS["DEVELOPMENT_RUN"], "job": j.job_id, "state": j.state, "stage": j.stage or "n/a",
            "started": j.started_at, "reason": j.reason,
        } for j in runs]), hide_index=True, width="stretch")

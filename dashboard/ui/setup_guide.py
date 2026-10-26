"""Setup guide: renders dashboard/README.md, so the page and the written guide cannot drift apart."""
from __future__ import annotations

from pathlib import Path

import streamlit as st

README = Path(__file__).resolve().parents[1] / "README.md"


def render() -> None:
    st.title("Setup guide")
    st.caption("Same text as dashboard/README.md in the repository.")
    st.markdown(README.read_text(encoding="utf-8"))

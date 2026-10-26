"""Local research dashboard entry point.

Start it from the repository folder with the virtual environment active:

    python -m streamlit run dashboard/app.py --server.address 127.0.0.1 --server.port 8501

See dashboard/README.md for the Windows WSL2 and Ubuntu instructions.
"""
from __future__ import annotations

import sys
from pathlib import Path

DASHBOARD_DIR = Path(__file__).resolve().parent
if str(DASHBOARD_DIR) not in sys.path:
    sys.path.insert(0, str(DASHBOARD_DIR))

from geodash.paths import ensure_import_paths  # noqa: E402

ensure_import_paths()

import streamlit as st  # noqa: E402

from ui import diagnostics, experiments, home, models, rf_explorer, runner, setup_guide  # noqa: E402

st.set_page_config(page_title="GEO research dashboard", layout="wide")

PAGES = [
    st.Page(home.render, title="Dashboard", url_path="dashboard", icon=":material/dashboard:", default=True),
    st.Page(rf_explorer.render, title="RF Explorer", url_path="rf-explorer", icon=":material/cell_tower:"),
    st.Page(runner.render, title="Development runner", url_path="development-runner", icon=":material/play_circle:"),
    st.Page(models.render, title="Model analysis", url_path="model-analysis", icon=":material/query_stats:"),
    st.Page(experiments.render, title="Experiment browser", url_path="experiment-browser", icon=":material/science:"),
    st.Page(diagnostics.render, title="System diagnostics", url_path="system-diagnostics", icon=":material/monitor_heart:"),
    st.Page(setup_guide.render, title="Setup guide", url_path="setup-guide", icon=":material/menu_book:"),
]

st.navigation(PAGES).run()

"""App smoke tests: every page renders headlessly, the runner offers exactly the allowlist, and no production control exists."""
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = ROOT / "dashboard"
sys.path[:0] = [str(DASHBOARD), str(ROOT / "src"), str(ROOT)]

from streamlit.testing.v1 import AppTest  # noqa: E402

from geodash import commands as C  # noqa: E402

PAGES = {
    "home": "from ui import home; home.render()",
    "rf": "from ui import rf_explorer; rf_explorer.render()",
    "runner": "from ui import runner; runner.render()",
    "models": "from ui import models; models.render()",
    "experiments": "from ui import experiments; experiments.render()",
    "diagnostics": "from ui import diagnostics; diagnostics.render()",
    "setup": "from ui import setup_guide; setup_guide.render()",
}
PREAMBLE = f"import sys; sys.path[:0] = [{str(DASHBOARD)!r}, {str(ROOT / 'src')!r}, {str(ROOT)!r}]\n"


def _run_page(name, tmp_path, monkeypatch):
    monkeypatch.setenv("GEO_DASHBOARD_HOME", str(tmp_path / "run-home"))
    return AppTest.from_string(PREAMBLE + PAGES[name], default_timeout=240).run()


@pytest.mark.parametrize("name", sorted(PAGES))
def test_each_page_renders_without_an_exception(name, tmp_path, monkeypatch):
    at = _run_page(name, tmp_path, monkeypatch)
    assert [str(e.value) for e in at.exception] == []


def test_the_full_application_entry_point_loads_with_all_seven_pages(tmp_path, monkeypatch):
    monkeypatch.setenv("GEO_DASHBOARD_HOME", str(tmp_path / "run-home"))
    at = AppTest.from_file(str(DASHBOARD / "app.py"), default_timeout=240).run()
    assert [str(e.value) for e in at.exception] == []
    assert at.title and at.title[0].value == "GEO research dashboard"


def test_the_runner_offers_exactly_the_allowlisted_commands(tmp_path, monkeypatch):
    at = _run_page("runner", tmp_path, monkeypatch)
    command_box = next(box for box in at.selectbox if box.label == "Command")
    assert sorted(command_box.options) == sorted(spec.title for spec in C.REGISTRY.values())


def test_the_runner_parameter_controls_are_only_the_enumerated_choices(tmp_path, monkeypatch):
    at = _run_page("runner", tmp_path, monkeypatch)
    groups = [box for box in at.selectbox if box.label.startswith("groups")]
    assert len(groups) == 1, "the real-exercise command must expose its groups control"
    assert list(groups[0].options) == ["1", "2"]


def test_no_button_in_the_application_is_a_production_control(tmp_path, monkeypatch):
    for name in PAGES:
        at = _run_page(name, tmp_path, monkeypatch)
        labels = [button.label for button in at.button]
        for label in labels:
            assert not re.search(r"production|launch|gpu|loko|train full|authori[sz]e", label, re.IGNORECASE), label


def test_the_source_of_the_ui_contains_no_production_launch_call():
    for path in sorted((DASHBOARD / "ui").glob("*.py")):
        source = path.read_text(encoding="utf-8")
        assert not re.search(r"st\.button\(\s*[\"'][^\"']*(production|launch)", source, re.IGNORECASE), path.name
        assert "--execute" not in source and "--device" not in source, path.name


def test_the_setup_page_renders_the_readme_exactly(tmp_path, monkeypatch):
    at = _run_page("setup", tmp_path, monkeypatch)
    readme = (DASHBOARD / "README.md").read_text(encoding="utf-8")
    assert readme.strip() in [md.value.strip() for md in at.markdown]
    assert "streamlit run dashboard/app.py" in readme

"""App smoke tests: every page renders headlessly, the runner offers exactly the allowlist, and no production control exists."""
import json
import re
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = ROOT / "dashboard"
sys.path[:0] = [str(DASHBOARD), str(ROOT / "src"), str(ROOT)]

from streamlit.testing.v1 import AppTest  # noqa: E402

from geodash import commands as C  # noqa: E402
from geodash import jobs as J  # noqa: E402
from geodash import pilot as P  # noqa: E402
from geodash.portable import popen_kwargs, process_start_token  # noqa: E402

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
    assert at.title and at.title[0].value == "GEO PAYLOAD AWARE — RESEARCH WORKBENCH"
    assert "GEO research dashboard" in [header.value for header in at.header]


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
            assert not re.search(r"production|launch|gpu|loko|train full|authori[sz]e|full benchmark|21[.,]?350|"
                                 r"complete research", label, re.IGNORECASE), label


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


# ---- the one-click pilot workbench on the home page --------------------------------------------------------

REPORT = {"schema": C.EXERCISE_SCHEMA, "scope": C.SCOPE_DEVELOPMENT, "heldout_reads": 0, "gpu_exercised": False,
          "production_authorized": False, "benchmark_complete": False}
LINUX = {"id": "linux", "label": "Linux", "label_tr": "Linux", "pilot_capable": True}
NATIVE = {"id": "native-windows", "label": "native Windows (inspection only)",
          "label_tr": "Yerel Windows (yalnız inceleme)", "pilot_capable": False}
VERIFIED = {"mode": "git", "commit": "a" * 40, "verified": True, "problems": [], "manifest_sha256": None,
            "limitations": "test"}
UNVERIFIED = {"mode": "git", "commit": "b" * 40, "verified": False,
              "problems": ["governed files modified: src/x.py"], "manifest_sha256": None, "limitations": "test"}


def _texts(at, *kinds):
    return [str(element.value) for kind in kinds for element in getattr(at, kind)]


def _no_spawn(*args, **kwargs):
    raise AssertionError("a UI test must not start a supervisor")


@pytest.fixture
def workbench(monkeypatch):
    """A capable engine with a verified source; no supervisor or preflight can reach a real process."""
    monkeypatch.setattr(P, "engine", lambda *a, **k: dict(LINUX))
    # The command layer checks the platform independently of engine(); pin it to the same POSIX engine so
    # the enabled-button tests also hold on a native-Windows test runner.
    monkeypatch.setattr(C, "current_platform_is_posix", lambda: True)
    monkeypatch.setattr(P, "source_identity", lambda *a, **k: dict(VERIFIED))
    monkeypatch.setattr(P, "spawn_supervisor", _no_spawn)
    monkeypatch.setattr(P, "preflight", lambda *a, **k: pytest.fail("preflight must not run without a click"))
    return monkeypatch


def _job_record(home: Path, job_id: str, state: str, pid: int | None, **extra) -> Path:
    job_dir = home / "jobs" / job_id
    (job_dir / "exercise").mkdir(parents=True)
    record = {"job_id": job_id, "key": P.PILOT_KEY, "title": "pilot", "scope": C.SCOPE_DEVELOPMENT, "state": state,
              "values": {"groups": 1}, "argv": ["python", "scripts/b2_real_execution.py"],
              "started_at": "2026-11-05T00:00:00+00:00", "started_epoch": time.time() - 30, "timeout_s": 5400,
              "pid": pid, "pid_start_token": process_start_token(pid), "returncode": None, "reason": "", **extra}
    (job_dir / "job.json").write_text(json.dumps(record), encoding="utf-8")
    return job_dir


@pytest.fixture
def sleeper():
    """A real, harmless process to stand for a running pilot; it is never the supervisor."""
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(300)"], **popen_kwargs())
    try:
        yield proc
    finally:
        proc.kill()
        proc.wait(timeout=30)


def test_home_shows_the_workbench_header_status_line_and_closed_state_badges(tmp_path, monkeypatch):
    monkeypatch.setattr(P, "spawn_supervisor", _no_spawn)
    at = _run_page("home", tmp_path, monkeypatch)
    assert [str(e.value) for e in at.exception] == []
    assert at.title[0].value == "GEO PAYLOAD AWARE — RESEARCH WORKBENCH"
    markdown = _texts(at, "markdown")
    assert any("Engine: " in text and "Benchmark: INCOMPLETE" in text for text in markdown)
    assert any("Research gates: CLOSED / NO PRODUCTION AUTHORITY" in text for text in markdown)
    badges = next(text for text in markdown if "`APP_READY`" in text)
    for state in ("BENCHMARK_NOT_RUN", "COMPUTE_GATES_CLOSED", "HOST_NOT_QUALIFIED"):
        assert f"`{state}`" in badges
    assert not [state for state in ("PILOT_COMPLETE", "PILOT_RUNNING") if state in badges]
    for note in ("YALNIZ PİLOT (21.350 gözlemlik benchmark değil)", "Üretim 21.350 / GPU / LOKO / held-out: KİLİTLİ",
                 "exercise.json işlevsel akışı kanıtlar, tanıma performansını değil"):
        assert any(note in text for text in markdown), note
    assert any("RF üretimi → eğitim → val-calib → dondurma → rapor" in text for text in markdown)
    assert list(at.radio(key="pilot-groups").options) == ["1 grup (varsayılan)", "2 grup (sınırlı)"]
    assert {b.label for b in at.button} >= {"GEO PİLOT BAŞLAT", "DURUMU YENİLE", "GÜVENLİ İPTAL"}
    assert at.button(key="pilot-cancel").disabled  # nothing runs


def test_on_native_windows_the_pilot_start_is_disabled_with_the_wsl2_guidance(tmp_path, workbench):
    workbench.setattr(P, "engine", lambda *a, **k: dict(NATIVE))
    at = _run_page("home", tmp_path, workbench)
    assert [str(e.value) for e in at.exception] == []
    assert at.button(key="pilot-start").disabled
    warnings = _texts(at, "warning")
    assert any("WSL2 Ubuntu gerektirir" in text and "GEO WSL Kurulumu" in text for text in warnings)
    assert any("Engine: native Windows (inspection only)" in text for text in _texts(at, "markdown"))
    assert any("`PILOT_UNAVAILABLE`" in text for text in _texts(at, "markdown"))


def test_an_unverified_source_disables_the_start_and_lists_its_problems(tmp_path, workbench):
    workbench.setattr(P, "source_identity", lambda *a, **k: dict(UNVERIFIED))
    at = _run_page("home", tmp_path, workbench)
    assert at.button(key="pilot-start").disabled
    assert any("Kaynak doğrulanmadı" in text and "governed files modified: src/x.py" in text
               for text in _texts(at, "warning"))


def test_a_running_pilot_shows_its_job_id_and_offers_no_second_start(tmp_path, workbench, sleeper):
    job_id = "20261105T000000-abc123"
    _job_record(tmp_path / "run-home", job_id, J.RUNNING, sleeper.pid)
    at = _run_page("home", tmp_path, workbench)
    assert [str(e.value) for e in at.exception] == []
    assert any(job_id in text for text in _texts(at, "info"))
    assert not [b for b in at.button if b.label == "GEO PİLOT BAŞLAT" and not b.disabled]
    assert not at.button(key="pilot-cancel").disabled
    assert any("`PILOT_RUNNING`" in text for text in _texts(at, "markdown"))
    assert any("time, not completion" in str(bar.proto.text) for bar in at.get("progress"))
    assert sleeper.poll() is None


def test_safe_cancel_calls_cancel_pilot_for_the_running_job_and_reports_in_turkish(tmp_path, workbench, sleeper):
    job_id = "20261105T000000-abc124"
    _job_record(tmp_path / "run-home", job_id, J.RUNNING, sleeper.pid)
    calls = []

    def fake_cancel(requested, *, manager=None, out=print):
        calls.append(requested)
        out(f"CANCELLED JOB_ID={requested}")
        return P.EXIT_OK

    workbench.setattr(P, "cancel_pilot", fake_cancel)
    at = _run_page("home", tmp_path, workbench)
    at.button(key="pilot-cancel").click().run()
    assert [str(e.value) for e in at.exception] == []
    assert calls == [job_id]
    assert any("İptal edildi" in text for text in _texts(at, "success"))


def test_the_start_button_runs_preflight_then_spawns_the_supervisor_with_the_chosen_groups(tmp_path, workbench):
    spawned, checked = [], []

    class FakeProc:
        pid = 4242

    def fake_preflight(groups, *args, **kwargs):
        checked.append(groups)
        return {"ok": True, "exit_code": 0, "codes": [], "reasons": [], "running_job": None}

    def fake_spawn(groups, **kwargs):
        spawned.append(groups)
        return FakeProc()

    workbench.setattr(P, "preflight", fake_preflight)
    workbench.setattr(P, "spawn_supervisor", fake_spawn)
    at = _run_page("home", tmp_path, workbench)
    assert not at.button(key="pilot-start").disabled
    at.radio(key="pilot-groups").set_value(2).run()
    at.button(key="pilot-start").click().run()
    assert [str(e.value) for e in at.exception] == []
    assert checked == [2] and spawned == [2]
    assert any("4242" in text for text in _texts(at, "success"))


def test_a_refused_preflight_starts_nothing_and_explains_in_turkish(tmp_path, workbench):
    def refused(groups, *args, **kwargs):
        return {"ok": False, "exit_code": 22, "codes": ["DEPENDENCIES_MISSING"], "reasons": ["not importable: torch"],
                "running_job": None}

    workbench.setattr(P, "preflight", refused)
    at = _run_page("home", tmp_path, workbench)
    at.button(key="pilot-start").click().run()
    assert [str(e.value) for e in at.exception] == []
    errors = _texts(at, "error")
    assert any("Gerekli paketler eksik" in text and "DEPENDENCIES_MISSING" in text and "22" in text
               for text in errors)


def _finished_pilot(home: Path, job_id: str, state: str, report: dict | None) -> Path:
    job_dir = _job_record(home, job_id, state, None, returncode=0 if state == J.SUCCEEDED else 5,
                          finished_at="2026-11-05T00:10:00+00:00")
    if report is not None:
        (job_dir / "exercise" / "exercise.json").write_text(json.dumps(report), encoding="utf-8")
    (job_dir / "pilot.json").write_text(json.dumps({
        "schema": P.PILOT_SCHEMA, "job_id": job_id, "state": state, "finished_at": "2026-11-05T00:10:00+00:00",
        "engine": LINUX, "source": VERIFIED}), encoding="utf-8")
    return job_dir


def test_a_verified_finished_pilot_is_complete_with_the_functional_flow_caveat(tmp_path, workbench):
    _finished_pilot(tmp_path / "run-home", "20261105T000000-ok0001", J.SUCCEEDED, REPORT)
    at = _run_page("home", tmp_path, workbench)
    assert [str(e.value) for e in at.exception] == []
    assert any("`PILOT_COMPLETE`" in text for text in _texts(at, "markdown"))
    assert any("tanıma performansını değil" in text for text in _texts(at, "success"))
    assert any("Çıktı klasörü" in text and "20261105T000000-ok0001" in text for text in _texts(at, "markdown"))


def test_a_succeeded_pilot_whose_report_breaks_the_boundary_is_not_complete(tmp_path, workbench):
    _finished_pilot(tmp_path / "run-home", "20261105T000000-bad001", J.SUCCEEDED,
                    {**REPORT, "benchmark_complete": True})
    at = _run_page("home", tmp_path, workbench)
    markdown = _texts(at, "markdown")
    assert any("`PILOT_FAILED`" in text for text in markdown)
    assert not any("`PILOT_COMPLETE`" in text for text in markdown)
    assert not _texts(at, "success")


def test_the_runner_lists_pilot_history_from_job_and_pilot_records(tmp_path, workbench):
    home = tmp_path / "run-home"
    _finished_pilot(home, "20261105T000000-ok0002", J.SUCCEEDED, REPORT)
    _finished_pilot(home, "20261105T000001-fail01", J.FAILED, None)
    at = _run_page("runner", tmp_path, workbench)
    assert [str(e.value) for e in at.exception] == []
    assert "Pilot geçmişi" in _texts(at, "subheader")
    history = next(frame.value for frame in at.dataframe if "verified" in frame.value.columns)
    rows = {row["job"]: row for row in history.to_dict("records")}
    assert bool(rows["20261105T000000-ok0002"]["verified"]) is True
    assert bool(rows["20261105T000001-fail01"]["verified"]) is False
    assert rows["20261105T000000-ok0002"]["engine"] == "linux"
    assert rows["20261105T000000-ok0002"]["source"] == "git " + "a" * 12


def test_home_tolerates_a_corrupt_job_record(tmp_path, workbench):
    broken = tmp_path / "run-home" / "jobs" / "20261105T000000-broken"
    broken.mkdir(parents=True)
    (broken / "job.json").write_text("{corrupt", encoding="utf-8")
    for name in ("home", "runner"):
        at = _run_page(name, tmp_path, workbench)
        assert [str(e.value) for e in at.exception] == [], name
    assert (broken / "job.json").read_text(encoding="utf-8") == "{corrupt"

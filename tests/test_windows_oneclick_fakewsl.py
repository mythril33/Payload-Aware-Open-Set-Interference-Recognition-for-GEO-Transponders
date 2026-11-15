"""geo_workbench.ps1 driven end to end against a scripted wsl.exe (windows/tests/fake_wsl.cmd).

Windows only: needs ``powershell.exe``. The scripts run from a temporary copy of ``windows/*.ps1``
(so logs, pid files and an optional ``VERSION.json`` stay in ``tmp_path``), with ``LOCALAPPDATA``
pointing at a temporary folder that holds the backend state file. The fake answers every WSL call
from a scenario JSON file and logs it; no real WSL distribution is ever started.
"""
from __future__ import annotations

import http.server
import json
import os
import shutil
import subprocess
import sys
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WIN = ROOT / "windows"
FAKE_WSL = WIN / "tests" / "fake_wsl.cmd"
POWERSHELL = shutil.which("powershell.exe")

pytestmark = pytest.mark.skipif(os.name != "nt" or POWERSHELL is None,
                                reason="needs native Windows with powershell.exe")

COMMIT = "a" * 40
OTHER_COMMIT = "b" * 40
DISTRO = "Ubuntu-24.04"
SRC = "/home/geo/geo-workbench-src"
RUN_HOME = "/home/geo/.local/share/geo-dashboard"


def preflight_report(exit_code: int, codes: list[str], running_job: str | None = None,
                     running_key: str | None = None) -> dict:
    return {"ok": exit_code == 0, "exit_code": exit_code, "codes": codes,
            "reasons": [f"fake reason for {code}" for code in codes],
            "engine": {"id": "wsl2", "label": "WSL2 Linux", "label_tr": "WSL2 Linux", "pilot_capable": True},
            "source": {"mode": "git", "commit": COMMIT, "verified": exit_code != 20, "problems": [],
                       "manifest_sha256": None, "limitations": "fake"},
            "running_job": running_job, "running_job_key": running_key, "unreadable_job_dirs": [],
            "disk_free_gib": 100.0, "runner_ready": True, "groups": 1}


def pilot_status(job_id: str, state: str) -> dict:
    return {"found": True, "job_id": job_id, "state": state, "returncode": None, "stage": "rf",
            "stage_detail": "", "elapsed_s": 4.0, "timeout_s": 5400, "job_dir": f"{RUN_HOME}/jobs/{job_id}",
            "reason": "", "report_path": None, "pilot_record_path": None, "verified": False}


NO_PILOT = {"exit": 3, "stdout": {"found": False, "job_id": None, "state": None}}


def ui_serving(port: int, expect_commit: str = COMMIT) -> dict:
    return {"exit": 0, "stdout": {"running": True, "state": "serving", "pid": 4242, "port": port, "engine": "wsl2",
                                  "started_at": "2026-11-05T00:00:00Z", "expect_commit": expect_commit,
                                  "expect_manifest_sha256": None, "ui_record": f"{RUN_HOME}/workbench/ui.json"}}


class _Health(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 - http.server API
        body = b"ok" if self.path.startswith("/_stcore/health") else b"fake workbench"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture
def health_port():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Health)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server.server_address[1]
    server.shutdown()
    server.server_close()


class Workbench:
    def __init__(self, tmp: Path):
        self.tmp = tmp
        self.pkg = tmp / "pkg"
        (self.pkg / "windows").mkdir(parents=True)
        for ps1 in WIN.glob("*.ps1"):
            shutil.copy2(ps1, self.pkg / "windows" / ps1.name)
        self.localappdata = tmp / "localappdata"
        self.scenario_path = tmp / "scenario.json"
        self.log_path = tmp / "fake_wsl.log"

    def write_state(self, commit: str = COMMIT) -> None:
        state = {"schema": "GEO-workbench-wsl-backend/1", "distro": DISTRO, "src": SRC,
                 "python": SRC + "/.venv/bin/python", "commit": commit, "source_mode": "git",
                 "manifest_sha256": None, "linux_user": "geo", "uid": 1000,
                 "package_root": str(self.pkg), "configured_at": "2026-11-05T00:00:00Z"}
        path = self.localappdata / "GEO-Workbench" / "wsl_backend.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state), encoding="utf-8")

    def write_version(self, commit: str = COMMIT) -> None:
        version = {"version": "0.1.0-test", "commit": commit, "source_manifest_sha256": "c" * 64,
                   "source_bundle": "geo-source.bundle", "source_bundle_sha256": "d" * 64,
                   "source_bundle_head": commit}
        (self.pkg / "VERSION.json").write_text(json.dumps(version), encoding="utf-8")

    def scenario(self, commands: dict) -> None:
        self.scenario_path.write_text(json.dumps({"commands": commands}), encoding="utf-8")

    def run(self, action: str, *extra: str, stdin: str = "") -> subprocess.CompletedProcess:
        env = {**os.environ, "LOCALAPPDATA": str(self.localappdata), "GEO_FAKE_WSL_SCENARIO": str(self.scenario_path),
               "GEO_FAKE_WSL_LOG": str(self.log_path), "GEO_FAKE_WSL_PYTHON": sys.executable,
               "GEO_DASHBOARD_HOME": str(self.tmp / "native-run-home")}
        argv = [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                str(self.pkg / "windows" / "geo_workbench.ps1"), "-Action", action, "-NoBrowser",
                "-WslExe", str(FAKE_WSL), *extra]
        return subprocess.run(argv, env=env, input=stdin, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=300)

    def calls(self, key: str | None = None) -> list[dict]:
        if not self.log_path.is_file():
            return []
        calls = [json.loads(line) for line in self.log_path.read_text(encoding="utf-8").splitlines() if line]
        return calls if key is None else [call for call in calls if call["key"] == key]


@pytest.fixture
def bench(tmp_path):
    wb = Workbench(tmp_path)
    wb.write_state()
    wb.write_version()
    return wb


def _explain(done: subprocess.CompletedProcess, wb: Workbench) -> str:
    return f"exit {done.returncode}\nstdout:\n{done.stdout}\nstderr:\n{done.stderr}\ncalls: {wb.calls()}"


def test_pilot_already_running_exits_10_prints_the_job_id_and_never_runs(bench, health_port):
    bench.scenario({"preflight": {"exit": 10, "stdout": preflight_report(10, ["PILOT_ALREADY_RUNNING"],
                                                                          "job-running-1", "real-exercise")},
                    "ui-status": ui_serving(health_port),
                    "status": {"exit": 0, "stdout": pilot_status("job-running-1", "running")}})
    done = bench.run("pilot")
    assert done.returncode == 10, _explain(done, bench)
    assert "JOB_ID=job-running-1" in done.stdout
    assert bench.calls("run") == []
    assert bench.calls("serve") == []
    preflight = bench.calls("preflight")
    assert len(preflight) == 1
    assert preflight[0]["args"][-3:] == ["--expect-commit", COMMIT, "--json"]


@pytest.mark.parametrize("code,name", [(20, "SOURCE_NOT_VERIFIED"), (23, "DISK_INSUFFICIENT")])
def test_pilot_preflight_refusal_exits_with_its_code_and_never_runs(bench, code, name):
    bench.scenario({"preflight": {"exit": code, "stdout": preflight_report(code, [name])}})
    done = bench.run("pilot")
    assert done.returncode == code, _explain(done, bench)
    assert bench.calls("run") == []
    assert bench.calls("serve") == []
    assert "fake reason for " + name in done.stdout


@pytest.mark.parametrize("mode", ["package", "developer"])
def test_pilot_preflight_ok_starts_exactly_one_run_with_the_expected_commit(tmp_path, health_port, mode):
    wb = Workbench(tmp_path)
    wb.write_state()
    if mode == "package":
        wb.write_version()
    wb.scenario({"preflight": {"exit": 0, "stdout": preflight_report(0, [])},
                 "ui-status": ui_serving(health_port),
                 "status": {**NO_PILOT, "after_run": {"exit": 0, "stdout": pilot_status("job-new-1", "running")}},
                 "run": {"exit": 0}})
    done = wb.run("pilot")
    assert done.returncode == 0, _explain(done, wb)
    runs = wb.calls("run")
    assert len(runs) == 1, _explain(done, wb)
    args = runs[0]["args"]
    assert args[args.index("--groups") + 1] == "1"
    assert args[args.index("--expect-commit") + 1] == COMMIT
    assert "--expect-manifest-sha256" not in args
    assert runs[0]["distro"] == DISTRO and runs[0]["cd"] == SRC and runs[0]["exec"] == SRC + "/.venv/bin/python"
    assert "JOB_ID=job-new-1" in done.stdout
    assert wb.calls("serve") == []


def test_stop_pilot_ownership_refusal_exits_41(bench):
    bench.scenario({"cancel": {"exit": 41,
                               "stdout": "OWNERSHIP_UNVERIFIED job job-1: pid 77 now belongs to another process"}})
    done = bench.run("stop-pilot")
    assert done.returncode == 41, _explain(done, bench)
    assert len(bench.calls("cancel")) == 1


def test_close_with_a_running_pilot_declined_exits_5_without_ui_stop(bench):
    bench.scenario({"status": {"exit": 0, "stdout": pilot_status("job-running-1", "running")},
                    "ui-stop": {"exit": 0, "stdout": "STOPPED"}})
    done = bench.run("close", stdin="H\n")
    assert done.returncode == 5, _explain(done, bench)
    assert "JOB_ID=job-running-1" in done.stdout
    assert bench.calls("ui-stop") == []


def test_commit_mismatch_open_falls_back_and_pilot_exits_20(tmp_path, health_port):
    wb = Workbench(tmp_path)
    wb.write_state(COMMIT)
    wb.write_version(OTHER_COMMIT)
    wb.scenario({"preflight": {"exit": 0, "stdout": preflight_report(0, [])}, "ui-status": ui_serving(health_port),
                 "serve": {"exit": 0}, "run": {"exit": 0}, "status": NO_PILOT})
    done = wb.run("open")
    assert done.returncode == 20, _explain(done, wb)
    assert wb.calls("serve") == [] and wb.calls("ui-status") == []
    assert OTHER_COMMIT in done.stdout
    done = wb.run("pilot")
    assert done.returncode == 20, _explain(done, wb)
    assert wb.calls("preflight") == [] and wb.calls("run") == []


def test_open_refuses_a_ui_served_for_another_commit(bench, health_port):
    bench.scenario({"ui-status": ui_serving(health_port, OTHER_COMMIT), "serve": {"exit": 0}})
    done = bench.run("open")
    assert done.returncode == 20, _explain(done, bench)
    assert bench.calls("serve") == []
    assert len(bench.calls("ui-status")) == 1

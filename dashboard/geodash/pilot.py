"""One-click bounded GEO pilot: engine and source identity, preflight, a persistent supervisor, the UI service.

Library only; no Streamlit import. The pilot is the existing allowlisted ``real-exercise`` command, started
through the same JobManager and argv guard as the Development runner, with one or two groups per development
role. The supervisor (run_pilot) owns the job until its process exits, so the exit status is recorded rather
than inferred, and it writes a versioned pilot.json next to job.json. Nothing here can request production,
GPU, LOKO or held-out work, and no state is ever upgraded: pilot.json copies the JobManager's verdict.

Exit codes are stable; the Windows scripts map them to messages:
0 OK, 3 nothing running/found, 10 pilot already running, 11 UI already running, 12 port busy,
18 another job running, 19 a job record is unreadable, 20 source not verified, 21 platform not POSIX,
22 dependencies missing, 23 disk insufficient, 24 groups refused, 25 source not a Git checkout,
30 failed, 31 cancelled, 32 timed out, 33 finished unrecorded, 34 record unreadable,
40 command refused, 41 ownership unverified, 42 the UI still serves after the stop wait.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import platform
import re
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from importlib import metadata
from importlib.util import find_spec
from pathlib import Path

from . import commands as C
from . import jobs as J
from .paths import REPO_ROOT, run_home
from .portable import IS_POSIX, pid_alive, popen_kwargs, process_start_token, terminate_tree

PILOT_KEY = "real-exercise"
PILOT_SCHEMA = "GEO-workbench-pilot-record/1"
MANIFEST_SCHEMA = "GEO-workbench-source-manifest/1"
MANIFEST_NAME = "SOURCE_MANIFEST.json"
MANIFEST_SOURCE = "git archive HEAD"
DEVELOPMENT_ROLES = ("train", "val-select", "val-calib")
GOVERNED_PATHS = ("src", "scripts", "configs", "dashboard", "pyproject.toml")
SNAPSHOT_TREES = ("src", "scripts", "configs", "dashboard")
RUNNER_MODULES = ("torch", "numpy", "scipy")
PILOT_NOTE = ("Bounded development pilot: proves the functional RF->train->calibrate->freeze flow; not a "
              "recognition-performance result and not the 21,350-observation benchmark.")
BOUNDARY = {"scope": C.SCOPE_DEVELOPMENT, "cpu_only": True, "heldout_reads": 0, "production_authorized": False,
            "benchmark_complete": False}
# The exercise.json fields copied into pilot.json's observed_boundary, as the run reported them.
OBSERVED_BOUNDARY_FIELDS = ("schema", "scope", "gpu_exercised", "heldout_reads", "production_authorized",
                            "benchmark_complete")
HEX_IDENTITY = re.compile(r"[0-9a-fA-F]{7,64}")
ENV_EXPECT_COMMIT = "GEO_EXPECT_COMMIT"
ENV_EXPECT_MANIFEST = "GEO_EXPECT_MANIFEST_SHA256"
PILOT_OUTPUTS = ("exercise/exercise.json", "exercise/freeze.json")
GIT_TIMEOUT_S = 30

EXIT_OK = 0
EXIT_NONE = 3
EXIT_PILOT_RUNNING = 10
EXIT_UI_RUNNING = 11
EXIT_PORT_BUSY = 12
EXIT_OTHER_JOB = 18
EXIT_JOB_RECORD = 19
EXIT_SOURCE = 20
EXIT_PLATFORM = 21
EXIT_DEPENDENCIES = 22
EXIT_DISK = 23
EXIT_GROUPS = 24
EXIT_NOT_GIT = 25
EXIT_REFUSED = 40
EXIT_OWNERSHIP = 41
EXIT_STOP_TIMEOUT = 42

PREFLIGHT_CODES = {
    "PILOT_ALREADY_RUNNING": EXIT_PILOT_RUNNING,
    "OTHER_JOB_RUNNING": EXIT_OTHER_JOB,
    "PLATFORM_NOT_POSIX": EXIT_PLATFORM,
    "GROUPS_REFUSED": EXIT_GROUPS,
    "DEPENDENCIES_MISSING": EXIT_DEPENDENCIES,
    "SOURCE_NOT_VERIFIED": EXIT_SOURCE,
    "SOURCE_NOT_GIT": EXIT_NOT_GIT,
    "JOB_RECORD_UNREADABLE": EXIT_JOB_RECORD,
    "DISK_INSUFFICIENT": EXIT_DISK,
}
# Reporting precedence when several apply; the first one is the exit code.
PREFLIGHT_PRECEDENCE = tuple(PREFLIGHT_CODES)

FINAL_EXIT = {
    J.SUCCEEDED: 0,
    J.FAILED: 30,
    J.CANCELLED: 31,
    J.TIMED_OUT: 32,
    J.FINISHED_UNRECORDED: 33,
    J.RECORD_UNREADABLE: 34,
}
# A record read while another process replaces it can fail once on Windows; only a repeated failure counts.
UNREADABLE_CONFIRMATIONS = 3

WORKBENCH_STATES = ("APP_READY", "PILOT_RUNNING", "PILOT_COMPLETE", "PILOT_FAILED", "BENCHMARK_NOT_RUN",
                    "COMPUTE_GATES_CLOSED", "HOST_NOT_QUALIFIED", "PILOT_UNAVAILABLE")
AUTHORIZING_VALUES = frozenset({"AUTHORIZED", "APPROVED_FOR_EXECUTION", "ENABLED", "GRANTED", "OPEN"})

ENGINES = {
    "wsl2": ("WSL2 Linux", "WSL2 Linux", True),
    "wsl1": ("WSL1 (the pilot needs WSL2; convert the distribution with wsl --set-version)",
             "WSL1 (pilot WSL2 gerektirir; dağıtımı wsl --set-version ile dönüştürün)", False),
    "linux": ("Linux", "Linux", True),
    "native-windows": ("native Windows (inspection only)", "Yerel Windows (yalnız inceleme)", False),
    "other": ("unsupported platform", "desteklenmeyen platform", False),
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def dumps(value) -> str:
    """One strict ASCII JSON line."""
    return json.dumps(value, ensure_ascii=True, allow_nan=False, sort_keys=True)


def _write_json_atomic(path: Path, value: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=True, allow_nan=False), encoding="utf-8")
    os.replace(tmp, path)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _default_manager() -> J.JobManager:
    return J.JobManager(run_home())


# ---- engine and source identity ------------------------------------------------------------------------

def engine(osrelease: str | None = None, os_name: str | None = None, environ=None) -> dict:
    """Which engine this process runs on. Only Linux and WSL2 can run the governed pilot.

    WSL2 is recognised from the kernel release alone ("microsoft-standard" or "wsl2"). WSL1 also exports
    WSL_INTEROP, so environ is accepted for callers but never upgrades a WSL1 kernel to WSL2.
    """
    os_name = os.name if os_name is None else os_name
    if os_name == "nt":
        key = "native-windows"
    elif os_name != "posix":
        key = "other"
    else:
        if osrelease is None:
            try:
                osrelease = Path("/proc/sys/kernel/osrelease").read_text(encoding="utf-8", errors="replace")
            except OSError:
                osrelease = ""
        release = osrelease.lower()
        if "microsoft-standard" in release or "wsl2" in release:
            key = "wsl2"
        elif "microsoft" in release:
            key = "wsl1"
        else:
            key = "linux"
    label, label_tr, capable = ENGINES[key]
    return {"id": key, "label": label, "label_tr": label_tr, "pilot_capable": capable}


def _git(args: list[str], cwd: Path) -> str | None:
    try:
        done = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True,
                              timeout=GIT_TIMEOUT_S, check=False, shell=False)
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout if done.returncode == 0 else None


def _identity(mode: str, commit, problems: list[str], manifest_sha256, limitations: str) -> dict:
    return {"mode": mode, "commit": commit, "verified": not problems, "problems": problems,
            "manifest_sha256": manifest_sha256, "limitations": limitations}


def _snapshot_extra_files(root: Path, listed: set[str]) -> list[str]:
    extra = []
    for tree in SNAPSHOT_TREES:
        base = root / tree
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if not path.is_file() or path.suffix == ".pyc":
                continue
            rel = path.relative_to(root)
            # pip install -e writes src/<name>.egg-info into the snapshot; it is build metadata, not source.
            if any(part == "__pycache__" or part.endswith(".egg-info") for part in rel.parts):
                continue
            if rel.as_posix() not in listed:
                extra.append(rel.as_posix())
    return sorted(extra)


def _package_identity(root: Path, expect_commit, expect_manifest_sha256) -> dict:
    limitations = ("Integrity is relative to the CI-built package manifest (SOURCE_MANIFEST.json); there is no "
                   "Git history in this tree, and this check is not a production lock.")
    manifest_path = root / MANIFEST_NAME
    problems: list[str] = []
    raw = manifest_path.read_bytes()
    manifest_sha = hashlib.sha256(raw).hexdigest()
    try:
        manifest = json.loads(raw.decode("utf-8"))
    except ValueError:
        return _identity("package-snapshot", None, ["SOURCE_MANIFEST.json is not readable JSON"], manifest_sha,
                         limitations)
    if not isinstance(manifest, dict):
        return _identity("package-snapshot", None, ["SOURCE_MANIFEST.json is not a JSON object"], manifest_sha,
                         limitations)
    commit = manifest.get("commit") if isinstance(manifest.get("commit"), str) else None
    files = manifest.get("files")
    if manifest.get("schema") != MANIFEST_SCHEMA:
        problems.append(f"manifest schema is {manifest.get('schema')!r}, expected {MANIFEST_SCHEMA!r}")
    if manifest.get("source") != MANIFEST_SOURCE:
        problems.append(f"manifest source is {manifest.get('source')!r}, expected {MANIFEST_SOURCE!r}: "
                        "the package was not built from a committed tree")
    if commit is None:
        problems.append("manifest names no commit")
    if not isinstance(files, dict) or not files:
        problems.append("manifest lists no files")
        files = {}
    resolved_root = root.resolve()
    for rel, expected in sorted(files.items()):
        path = (root / rel).resolve()
        if not isinstance(rel, str) or rel.startswith("/") or ".." in Path(rel).parts \
                or resolved_root not in path.parents:
            problems.append(f"manifest path outside the tree: {rel!r}")
            continue
        if not path.is_file():
            problems.append(f"missing file: {rel}")
        elif _sha256_file(path) != expected:
            problems.append(f"modified file: {rel}")
    for rel in _snapshot_extra_files(root, set(files)):
        problems.append(f"unexpected file: {rel}")
    if expect_commit is not None and commit != expect_commit:
        problems.append(f"commit {commit} does not match the expected {expect_commit}")
    if expect_manifest_sha256 is not None and manifest_sha != expect_manifest_sha256.lower():
        problems.append(f"manifest sha256 {manifest_sha} does not match the expected {expect_manifest_sha256}")
    return _identity("package-snapshot", commit, problems, manifest_sha, limitations)


def source_identity(repo_root: Path = REPO_ROOT, expect_commit: str | None = None,
                    expect_manifest_sha256: str | None = None) -> dict:
    """Identify the source the pilot would run, from Git or from the package manifest. Fail closed."""
    root = Path(repo_root)
    if (root / ".git").exists():
        commit = _git(["rev-parse", "HEAD"], root)
        commit = commit.strip() if commit is not None else None
        if commit:
            problems: list[str] = []
            dirty = _git(["status", "--porcelain", "--untracked-files=no", "--", *GOVERNED_PATHS], root)
            if dirty is None:
                problems.append("git status failed for the governed paths")
            elif dirty.strip():
                problems.append("governed files modified: " + ", ".join(
                    line[3:] for line in dirty.splitlines()[:10] if line.strip()))
            if expect_commit is not None and commit != expect_commit:
                problems.append(f"commit {commit} does not match the expected {expect_commit}")
            if expect_manifest_sha256 is not None:
                problems.append("an expected manifest sha256 was given, but this is a Git checkout")
            return _identity("git", commit, problems, None,
                             "Git checkout; tracked governed paths (" + ", ".join(GOVERNED_PATHS) +
                             ") must match HEAD. Untracked files are not inspected. Not a production lock.")
    if (root / MANIFEST_NAME).is_file():
        return _package_identity(root, expect_commit, expect_manifest_sha256)
    return _identity("unverified", None, ["no Git checkout and no SOURCE_MANIFEST.json: the source cannot be "
                                          "identified"], None, "The source tree could not be identified.")


# ---- preflight ------------------------------------------------------------------------------------------

def _disk_free_gib(path: Path) -> float:
    probe = Path(path)
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    try:
        return round(shutil.disk_usage(probe).free / 1024 ** 3, 2)
    except OSError:
        return 0.0


def _running_pilot(manager: J.JobManager) -> J.JobStatus | None:
    return next((job for job in manager.list_jobs() if job.key == PILOT_KEY and job.state == J.RUNNING), None)


def _running_job(manager: J.JobManager) -> J.JobStatus | None:
    """Any running job: JobManager.start refuses while one runs, whatever its key."""
    return next((job for job in manager.list_jobs() if job.state == J.RUNNING), None)


def expected_identity(environ=None) -> tuple[str | None, str | None]:
    """The package identity that serve exported to the UI process (commit, manifest sha256), or None."""
    environ = os.environ if environ is None else environ
    return (environ.get(ENV_EXPECT_COMMIT) or None, environ.get(ENV_EXPECT_MANIFEST) or None)


def preflight(groups=1, expect_commit: str | None = None, expect_manifest_sha256: str | None = None, *,
              manager: J.JobManager | None = None, min_free_gib: float = 5.0) -> dict:
    """Every check the pilot needs, all reported; exit_code is the first by PREFLIGHT_PRECEDENCE."""
    manager = _default_manager() if manager is None else manager
    registry = manager.registry
    eng = engine()
    source = source_identity(REPO_ROOT, expect_commit, expect_manifest_sha256)
    found: dict[str, str] = {}
    jobs = manager.list_jobs()
    running = next((job for job in jobs if job.state == J.RUNNING), None)
    if running is not None:
        code = "PILOT_ALREADY_RUNNING" if running.key == PILOT_KEY else "OTHER_JOB_RUNNING"
        found[code] = f"job {running.job_id} ({running.key}) is running"
    spec = registry.get(PILOT_KEY)
    if spec is None:
        found["PLATFORM_NOT_POSIX"] = f"{PILOT_KEY} is not in the command registry"
    else:
        available, why = C.is_available(spec)
        if not eng["pilot_capable"] or not available:
            found["PLATFORM_NOT_POSIX"] = why or f"engine {eng['id']} cannot run the pilot; WSL2 or Linux is needed"
        # The groups check must not repeat the platform refusal, so it validates against a POSIX-neutral copy.
        try:
            C.validate(PILOT_KEY, {"groups": groups}, {PILOT_KEY: dataclasses.replace(spec, requires_posix=False)})
        except C.CommandRefused as error:
            found["GROUPS_REFUSED"] = str(error)
    missing = [name for name in RUNNER_MODULES if find_spec(name) is None]
    if missing:
        found["DEPENDENCIES_MISSING"] = "not importable: " + ", ".join(missing)
    if not source["verified"]:
        found["SOURCE_NOT_VERIFIED"] = "; ".join(source["problems"])
    elif source["mode"] != "git":
        found["SOURCE_NOT_GIT"] = (f"the source is a verified {source['mode']}, not a Git checkout; training "
                                   "records the Git commit as checkpoint provenance, so the pilot cannot run here")
    unreadable = [job for job in jobs if job.state == J.RECORD_UNREADABLE]
    if unreadable:
        found["JOB_RECORD_UNREADABLE"] = "; ".join(
            f"{job.job_dir / 'job.json'} cannot be read; move the folder {job.job_dir} aside" for job in unreadable)
    free = _disk_free_gib(manager.home)
    if free < min_free_gib:
        found["DISK_INSUFFICIENT"] = f"{free} GiB free at {manager.home}; at least {min_free_gib} GiB required"
    codes = [code for code in PREFLIGHT_PRECEDENCE if code in found]
    return {
        "ok": not codes,
        "exit_code": PREFLIGHT_CODES[codes[0]] if codes else EXIT_OK,
        "codes": codes,
        "reasons": [found[code] for code in codes],
        "engine": eng,
        "source": source,
        "running_job": running.job_id if running is not None else None,
        "running_job_key": running.key if running is not None else None,
        "unreadable_job_dirs": [str(job.job_dir) for job in unreadable],
        "disk_free_gib": free,
        "runner_ready": not missing,
        "groups": groups,
    }


# ---- the supervisor -------------------------------------------------------------------------------------

def _python_identity() -> dict:
    return {"version": platform.python_version(), "executable": sys.executable, "platform": platform.platform()}


def _dependency_versions() -> dict:
    found = {}
    for name in RUNNER_MODULES:
        try:
            found[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            found[name] = None
    return found


def _finished_at(job_dir: Path) -> str | None:
    try:
        value = json.loads((job_dir / "job.json").read_text(encoding="utf-8")).get("finished_at")
    except (OSError, ValueError, AttributeError):
        return None
    return value if isinstance(value, str) else None


def _outputs(job_dir: Path) -> dict:
    return {rel: (_sha256_file(job_dir / rel) if (job_dir / rel).is_file() else None) for rel in PILOT_OUTPUTS}


def _scalar(value):
    """A strict-JSON scalar as reported, else None (pilot.json is written with allow_nan=False)."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float) and value == value and abs(value) != float("inf"):
        return value
    return None


def _observed_boundary(job_dir: Path) -> dict:
    """The boundary fields exercise.json actually reports; every field null when it is missing or unreadable."""
    report = _read_record(job_dir / "exercise" / "exercise.json")
    report = report if report is not None else {}
    return {name: _scalar(report.get(name)) for name in OBSERVED_BOUNDARY_FIELDS}


def write_pilot_record(status: J.JobStatus, *, groups, source: dict, eng: dict, returncode=None) -> Path:
    """pilot.json beside job.json. Its state is the JobManager's, copied, never upgraded."""
    final = status.state in J.FINAL_STATES
    boundary_ok, boundary_reason = C._exercise_success(status.job_dir)
    record = {
        "schema": PILOT_SCHEMA,
        "job_id": status.job_id,
        "state": status.state,
        "returncode": status.returncode if returncode is None else returncode,
        "reason": status.reason,
        "groups": status.values.get("groups", groups),
        "roles": list(DEVELOPMENT_ROLES),
        "argv": list(status.argv),
        "started_at": status.started_at,
        "finished_at": (_finished_at(status.job_dir) or _now_iso()) if final else None,
        "engine": eng,
        "source": source,
        "python": _python_identity(),
        "dependencies": _dependency_versions(),
        "outputs": _outputs(status.job_dir),
        "verified": status.state == J.SUCCEEDED and boundary_ok,
        "requested_boundary": dict(BOUNDARY),
        "observed_boundary": _observed_boundary(status.job_dir),
        "boundary_check": {"ok": boundary_ok, "reason": boundary_reason},
        "note": PILOT_NOTE,
    }
    path = status.job_dir / "pilot.json"
    _write_json_atomic(path, record)
    return path


def _signals() -> list:
    names = ("SIGTERM", "SIGINT", "SIGHUP") if IS_POSIX else ("SIGINT", "SIGBREAK")
    return [getattr(signal, name) for name in names if hasattr(signal, name)]


class _StopFlag:
    """Set by a signal handler; the handler itself does no work, the poll loop acts on it."""

    def __init__(self):
        self.signum = None
        self._previous: dict = {}

    def __enter__(self):
        if threading.current_thread() is threading.main_thread():
            for sig in _signals():
                self._previous[sig] = signal.signal(sig, self._handle)
        return self

    def __exit__(self, *exc):
        for sig, previous in self._previous.items():
            signal.signal(sig, previous)
        return False

    def _handle(self, signum, frame):
        self.signum = signum

    @property
    def set(self) -> bool:
        return self.signum is not None

    def sleep(self, seconds: float) -> None:
        deadline = time.monotonic() + seconds
        while not self.set and time.monotonic() < deadline:
            time.sleep(min(0.1, max(0.0, deadline - time.monotonic())))


def _emit(out, line: str) -> None:
    # After SIGHUP the relaying wsl.exe is gone and writing to its pty or pipe raises; output is best effort.
    try:
        out(line)
        sys.stdout.flush()
    except (OSError, ValueError):
        pass


def _refused_by_running_job(manager: J.JobManager, out, error: Exception) -> int:
    running = _running_job(manager)
    if running is not None:
        _emit(out, f"JOB_ID={running.job_id}")
    _emit(out, f"ACTIVE_JOB {error}")
    return EXIT_OTHER_JOB if running is not None and running.key != PILOT_KEY else EXIT_PILOT_RUNNING


def run_pilot(groups=1, expect_commit: str | None = None, expect_manifest_sha256: str | None = None, *,
              manager: J.JobManager | None = None, poll_s: float = 2.0, out=print) -> int:
    """Preflight, start the pilot and own it until its process exits. Returns the stable exit code."""
    manager = _default_manager() if manager is None else manager
    pre = preflight(groups, expect_commit, expect_manifest_sha256, manager=manager)
    if not pre["ok"]:
        if pre["running_job"] is not None:
            _emit(out, f"JOB_ID={pre['running_job']}")
        _emit(out, f"PREFLIGHT_REFUSED exit={pre['exit_code']} codes={','.join(pre['codes'])}")
        return pre["exit_code"]
    with _StopFlag() as stop:
        try:
            job_id = manager.start(PILOT_KEY, {"groups": groups})
        except J.RecordUnreadable as error:
            _emit(out, f"JOB_RECORD_UNREADABLE {error}")
            return EXIT_JOB_RECORD
        except J.ActiveJobError as error:
            return _refused_by_running_job(manager, out, error)
        except C.CommandRefused as error:
            _emit(out, f"REFUSED {error}")
            return EXIT_REFUSED
        _emit(out, f"JOB_ID={job_id}")
        status = manager.status(job_id)
        # The deadline outlives job.json: if the record becomes unreadable or vanishes, this supervisor still
        # enforces the command's timeout on the process it owns.
        deadline = time.time() - status.elapsed_s + status.timeout_s
        write_pilot_record(status, groups=groups, source=pre["source"], eng=pre["engine"])
        cancelled = False
        unreadable = 0
        while True:
            if stop.set and not cancelled:
                cancelled = True
                try:
                    manager.cancel(job_id)
                except J.UnknownJobError:
                    pass  # job.json vanished; the next status() hands the owned process to _wait_owned_process
                _emit(out, f"SIGNAL {stop.signum}: cancelled job {job_id}")
            try:
                status = manager.status(job_id)
            except J.UnknownJobError:
                status = dataclasses.replace(status, state=J.RECORD_UNREADABLE,
                                             reason=f"job.json of {job_id} disappeared; the record cannot be read")
                returncode = _wait_owned_process(manager, job_id, stop, deadline, out)
                _write_pilot_record_if_possible(status, groups, pre, returncode)
                _emit(out, f"STATE {J.RECORD_UNREADABLE}: job.json of {job_id} disappeared")
                return FINAL_EXIT[J.RECORD_UNREADABLE]
            if status.state == J.RECORD_UNREADABLE:
                unreadable += 1
                if unreadable >= UNREADABLE_CONFIRMATIONS:
                    break
            else:
                unreadable = 0
                if status.is_final:
                    break
            stop.sleep(poll_s)
        returncode = None
        if status.state == J.RECORD_UNREADABLE:
            returncode = _wait_owned_process(manager, job_id, stop, deadline, out)
        write_pilot_record(status, groups=groups, source=pre["source"], eng=pre["engine"], returncode=returncode)
        _emit(out, f"STATE {status.state}: {status.reason}")
        return FINAL_EXIT[status.state]


def _write_pilot_record_if_possible(status: J.JobStatus, groups, pre: dict, returncode) -> None:
    if status.job_dir.is_dir():
        try:
            write_pilot_record(status, groups=groups, source=pre["source"], eng=pre["engine"], returncode=returncode)
        except OSError:
            pass


def _wait_owned_process(manager: J.JobManager, job_id: str, stop: _StopFlag, deadline: float,
                        out=print) -> int | None:
    """job.json is unreadable or gone: still wait for the owned process, so it is not left unsupervised, and
    stop its tree on a signal or once the command's timeout (started_epoch + timeout_s) has passed."""
    proc = manager.owned_process(job_id)
    if proc is None:
        return None
    while proc.poll() is None:
        if stop.set:
            terminate_tree(proc.pid, proc, J.TERMINATE_GRACE_S)
            break
        if time.time() > deadline:
            terminate_tree(proc.pid, proc, J.TERMINATE_GRACE_S)
            _emit(out, f"TIMEOUT job {job_id} exceeded its timeout with an unreadable record; process tree stopped")
            break
        stop.sleep(0.5)
    return proc.poll()


# ---- status and cancellation ----------------------------------------------------------------------------

def latest_pilot(manager: J.JobManager | None = None) -> J.JobStatus | None:
    manager = _default_manager() if manager is None else manager
    return next((job for job in manager.list_jobs() if job.key == PILOT_KEY), None)


def pilot_status_dict(status: J.JobStatus) -> dict:
    report = status.job_dir / "exercise" / "exercise.json"
    record = status.job_dir / "pilot.json"
    return {
        "job_id": status.job_id,
        "state": status.state,
        "returncode": status.returncode,
        "groups": status.values.get("groups"),
        "stage": status.stage,
        "stage_detail": status.stage_detail,
        "elapsed_s": round(status.elapsed_s, 1),
        "timeout_s": status.timeout_s,
        "job_dir": str(status.job_dir),
        "reason": status.reason,
        "report_path": str(report) if report.is_file() else None,
        "pilot_record_path": str(record) if record.is_file() else None,
        "verified": status.state == J.SUCCEEDED and C._exercise_success(status.job_dir)[0],
    }


def _read_record(path: Path) -> dict | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def _recorded_running_pilots(manager: J.JobManager) -> list[tuple[str, dict]]:
    """Pilot records that say running, read as written: reading status() first could settle the very job
    whose pid ownership has to be checked."""
    found = []
    for path in sorted(manager.jobs_dir.iterdir(), reverse=True):
        record = _read_record(path / "job.json")
        if record is not None and record.get("key") == PILOT_KEY and record.get("state") == J.RUNNING:
            found.append((path.name, record))
    return found


def cancel_pilot(job_id: str | None = None, *, manager: J.JobManager | None = None, out=print) -> int:
    """0 cancelled, 3 no running pilot, 41 the recorded pid now belongs to another process (not signalled)."""
    manager = _default_manager() if manager is None else manager
    candidates = _recorded_running_pilots(manager)
    if job_id is not None:
        candidates = [(name, record) for name, record in candidates if name == job_id]
    if not candidates:
        _emit(out, "NO_RUNNING_PILOT" + (f" job {job_id}" if job_id else ""))
        return EXIT_NONE
    job_id, record = candidates[0]
    if J.pid_recycled(record.get("pid"), record.get("pid_start_token")):
        _emit(out, f"OWNERSHIP_UNVERIFIED job {job_id}: pid {record.get('pid')} now belongs to another process; "
                   "it was not signalled")
        return EXIT_OWNERSHIP
    after = manager.cancel(job_id)
    if after.state == J.CANCELLED:
        _emit(out, f"CANCELLED JOB_ID={job_id}")
        return EXIT_OK
    _emit(out, f"NO_RUNNING_PILOT job {job_id} is {after.state}: {after.reason}")
    return EXIT_NONE


def _identity_argv(expect_commit: str | None, expect_manifest_sha256: str | None) -> list[str]:
    argv = []
    for flag, value in (("--expect-commit", expect_commit), ("--expect-manifest-sha256", expect_manifest_sha256)):
        if value is None:
            continue
        if not isinstance(value, str) or not HEX_IDENTITY.fullmatch(value):
            raise C.CommandRefused(f"{flag} must be a hexadecimal digest, got {value!r}")
        argv += [flag, value]
    return argv


def spawn_supervisor(groups, *, python: str = sys.executable, expect_commit: str | None = None,
                     expect_manifest_sha256: str | None = None) -> subprocess.Popen:
    """Start ``geo_pilot.py run`` detached (own session), logging to the workbench folder. For the UI button.
    The package identity the UI was served with is forwarded, so the supervisor's preflight checks it too."""
    eng = engine()
    if not eng["pilot_capable"]:
        raise C.CommandRefused(f"the pilot cannot run on {eng['label']}; WSL2 or Linux is needed")
    C.validate(PILOT_KEY, {"groups": groups})
    identity = _identity_argv(expect_commit, expect_manifest_sha256)
    folder = run_home() / "workbench"
    folder.mkdir(parents=True, exist_ok=True)
    argv = [python, str(REPO_ROOT / "dashboard" / "geo_pilot.py"), "run", "--groups", str(groups), *identity]
    with (folder / f"supervisor-{_stamp()}.log").open("ab") as log:
        return subprocess.Popen(argv, cwd=str(REPO_ROOT), env={**os.environ, "PYTHONUTF8": "1"},
                                stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, shell=False,
                                **popen_kwargs())


# ---- the UI service -------------------------------------------------------------------------------------

def _ui_record_path() -> Path:
    return run_home() / "workbench" / "ui.json"


def _streamlit_argv(port: int, python: str) -> list[str]:
    return [python, "-m", "streamlit", "run", str(REPO_ROOT / "dashboard" / "app.py"), "--server.address",
            "127.0.0.1", "--server.port", str(port), "--server.headless", "true"]


def _port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        if IS_POSIX:
            # Linux refuses this bind while a listener holds the port, but not for TIME_WAIT leftovers.
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind(("127.0.0.1", int(port)))
        except OSError:
            return False
    return True


def ui_status() -> dict:
    """serving: the recorded serve process is alive with its start token and still serves the UI."""
    path = _ui_record_path()
    record = _read_record(path) if path.is_file() else None
    if record is None:
        return {"running": False, "state": "none" if not path.is_file() else "unreadable", "pid": None,
                "port": None, "engine": None, "started_at": None, "expect_commit": None,
                "expect_manifest_sha256": None, "ui_record": str(path)}
    pid = record.get("pid")
    if not pid_alive(pid):
        state = "stale"
    elif not J.process_alive(pid, record.get("start_token")):
        state = "token_mismatch"
    else:
        state = record.get("state", "serving")
    return {"running": state == "serving", "state": state, "pid": pid, "port": record.get("port"),
            "engine": record.get("engine"), "started_at": record.get("started_at"),
            "expect_commit": record.get("expect_commit"),
            "expect_manifest_sha256": record.get("expect_manifest_sha256"), "ui_record": str(path)}


def _ui_environment(expect_commit: str | None, expect_manifest_sha256: str | None) -> dict:
    """The Streamlit child's environment: the package identity it was served for, and nothing inherited."""
    env = {**os.environ, "PYTHONUTF8": "1"}
    for name, value in ((ENV_EXPECT_COMMIT, expect_commit), (ENV_EXPECT_MANIFEST, expect_manifest_sha256)):
        env.pop(name, None)
        if value:
            env[name] = value
    return env


def serve(port, *, python: str = sys.executable, manager: J.JobManager | None = None,
          keepalive_poll_s: float = 5.0, out=print, expect_commit: str | None = None,
          expect_manifest_sha256: str | None = None) -> int:
    """Run the Streamlit UI on 127.0.0.1:port until a signal; then keep the process (and so the WSL instance)
    alive while a pilot still runs. Exit 0 after a signal, 1 when Streamlit exited by itself.

    The expected package identity is exported to the UI as GEO_EXPECT_COMMIT / GEO_EXPECT_MANIFEST_SHA256 and
    recorded in ui.json; the UI's preflight and supervisor check it before any pilot starts.
    """
    port = int(port)
    try:
        _identity_argv(expect_commit, expect_manifest_sha256)
    except C.CommandRefused as error:
        _emit(out, f"REFUSED {error}")
        return EXIT_REFUSED
    current = ui_status()
    if current["state"] == "serving":
        _emit(out, f"ALREADY_RUNNING port={current['port']}")
        return EXIT_UI_RUNNING
    if not _port_free(port):
        _emit(out, f"PORT_BUSY port={port}")
        return EXIT_PORT_BUSY
    folder = run_home() / "workbench"
    folder.mkdir(parents=True, exist_ok=True)
    path = _ui_record_path()
    record = {"pid": os.getpid(), "start_token": process_start_token(os.getpid()), "port": port,
              "engine": engine()["id"], "started_at": _now_iso(), "state": "serving", "child_pid": None,
              "expect_commit": expect_commit, "expect_manifest_sha256": expect_manifest_sha256}
    with _StopFlag() as stop:
        with (folder / "ui.log").open("ab") as log:
            child = subprocess.Popen(_streamlit_argv(port, python), cwd=str(REPO_ROOT),
                                     env=_ui_environment(expect_commit, expect_manifest_sha256),
                                     stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, shell=False,
                                     **popen_kwargs())
        record["child_pid"] = child.pid
        _write_json_atomic(path, record)
        _emit(out, f"SERVING port={port} pid={os.getpid()}")
        while not stop.set and child.poll() is None:
            stop.sleep(0.2)
        exit_code = EXIT_OK
        if child.poll() is None:
            terminate_tree(child.pid, child, J.TERMINATE_GRACE_S)
        else:
            exit_code = 1
            _emit(out, f"UI_EXITED returncode={child.returncode}")
        manager = _default_manager() if manager is None else manager
        if _running_pilot(manager) is not None:
            record.update({"state": "keepalive", "child_pid": None})
            _write_json_atomic(path, record)
            _emit(out, "KEEPALIVE a pilot is running; this process stays until it ends")
            while _running_pilot(manager) is not None:
                time.sleep(keepalive_poll_s)
        mine = _read_record(path)
        if mine is not None and mine.get("pid") == os.getpid():
            path.unlink(missing_ok=True)
    _emit(out, "STOPPED")
    return exit_code


def ui_stop(*, wait_s: float = 30.0, out=print) -> int:
    """Signal the recorded serve process. 0 stopped, 3 none running, 41 its pid belongs to another process,
    42 it still serves once the wait is over."""
    status = ui_status()
    path = _ui_record_path()
    if status["state"] in ("none", "unreadable"):
        _emit(out, "NO_UI_RUNNING")
        return EXIT_NONE
    if status["state"] == "stale":
        path.unlink(missing_ok=True)
        _emit(out, "NO_UI_RUNNING stale record removed")
        return EXIT_NONE
    if status["state"] == "token_mismatch":
        _emit(out, f"OWNERSHIP_UNVERIFIED pid {status['pid']} now belongs to another process; it was not signalled")
        return EXIT_OWNERSHIP
    if status["state"] == "keepalive":
        _emit(out, "STOPPED the UI is already stopped; the process waits for the running pilot")
        return EXIT_OK
    pid = status["pid"]
    if IS_POSIX:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            _emit(out, "NO_UI_RUNNING the serve process ended before it was signalled")
            return EXIT_NONE
    else:
        terminate_tree(pid, None, J.TERMINATE_GRACE_S)
    deadline = time.monotonic() + wait_s
    while time.monotonic() < deadline and ui_status()["state"] == "serving":
        time.sleep(0.2)
    if ui_status()["state"] == "serving":
        _emit(out, f"STOP_TIMEOUT pid {pid} still serves after {wait_s:g} s")
        return EXIT_STOP_TIMEOUT
    _emit(out, "STOPPED")
    return EXIT_OK


# ---- home page states -----------------------------------------------------------------------------------

def _field(latest, name):
    if latest is None:
        return None
    return latest.get(name) if isinstance(latest, dict) else getattr(latest, name, None)


def _is_authorization(value) -> bool:
    return value is True or (isinstance(value, str) and value.strip().upper() in AUTHORIZING_VALUES)


def workbench_states(*, engine: dict, source: dict, latest, gate_rows: list, gpu_present: bool) -> list[str]:
    """Ordered state badges. Never a qualified host or a completed benchmark: neither exists in this repository."""
    states = {"APP_READY", "BENCHMARK_NOT_RUN", "HOST_NOT_QUALIFIED"}
    state = _field(latest, "state")
    if state == J.RUNNING:
        states.add("PILOT_RUNNING")
    elif state in J.FINAL_STATES:
        job_dir = _field(latest, "job_dir")
        verified = state == J.SUCCEEDED and job_dir is not None and C._exercise_success(Path(job_dir))[0]
        states.add("PILOT_COMPLETE" if verified else "PILOT_FAILED")
    if not gate_rows or any(not _is_authorization(row.get("value")) for row in gate_rows):
        states.add("COMPUTE_GATES_CLOSED")
    if not engine.get("pilot_capable") or not source.get("verified") or source.get("mode") == "package-snapshot":
        states.add("PILOT_UNAVAILABLE")
    return [name for name in WORKBENCH_STATES if name in states]


__all__ = ["PILOT_KEY", "PILOT_SCHEMA", "DEVELOPMENT_ROLES", "GOVERNED_PATHS", "PREFLIGHT_CODES", "FINAL_EXIT",
           "WORKBENCH_STATES", "engine", "source_identity", "expected_identity", "preflight", "run_pilot",
           "latest_pilot", "pilot_status_dict", "cancel_pilot", "spawn_supervisor", "serve", "ui_stop", "ui_status",
           "workbench_states", "write_pilot_record", "dumps"]

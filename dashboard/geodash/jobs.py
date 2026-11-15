"""Job manager for allowlisted development commands.

One job runs at a time (an exclusive file lock guards the start). Each job is a child process in its own
session (POSIX) or process group (native Windows), started without a shell, with the fixed environment
from commands.build_environment. Its folder, log and job.json live under run_home(), outside the
repository. Progress is inferred from the files a command writes, and the report says so. A GUI timeout
terminates the whole process tree. All platform-specific mechanics live in geodash.portable.

A recorded pid counts as the job only while its process start token still matches, so a recycled pid is
never signalled. job.json that cannot be read is reported as record_unreadable and left untouched, and no
new job starts until that folder is moved aside: whether its process still runs cannot be known.
"""
from __future__ import annotations

import json
import os
import secrets
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping

from . import commands as C
from .paths import REPO_ROOT, assert_outside_repo
from .portable import exclusive_lock, pid_alive, popen_kwargs, process_start_token, terminate_tree

RUNNING, SUCCEEDED, FAILED, CANCELLED, TIMED_OUT = "running", "succeeded", "failed", "cancelled", "timed_out"
# The process ended, its outputs verified, but no exit status was recorded (the dashboard process that
# started it is gone). Reported as such, never as a success with an exit status of zero.
FINISHED_UNRECORDED = "finished_unrecorded"
# job.json could not be parsed or lacks its fields. Reported, never treated as success, never rewritten.
RECORD_UNREADABLE = "record_unreadable"
FINAL_STATES = frozenset({SUCCEEDED, FAILED, CANCELLED, TIMED_OUT, FINISHED_UNRECORDED, RECORD_UNREADABLE})
REQUIRED_RECORD_FIELDS = ("key", "title", "scope", "state", "values", "argv", "started_at", "started_epoch",
                          "timeout_s", "pid")
CANCEL_REASON = "cancelled by the researcher; process group stopped"
TERMINATE_GRACE_S = 5.0
LOG_TAIL_LINES = 120


class ActiveJobError(RuntimeError):
    """Another job is still running. Only one bounded job runs at a time."""


class RecordUnreadable(ActiveJobError):
    """A job.json cannot be read, so whether its job still runs is unknown. Nothing starts until the
    researcher moves that job folder aside; the record itself is never rewritten."""

    def __init__(self, job_dir: Path, why: str = ""):
        self.job_dir = Path(job_dir)
        super().__init__(f"{self.job_dir / 'job.json'} cannot be read ({why or 'record unreadable'}); no new job "
                         f"starts until the folder {self.job_dir} is moved out of {self.job_dir.parent}")


class UnknownJobError(KeyError):
    pass


@dataclass(frozen=True)
class JobStatus:
    job_id: str
    key: str
    title: str
    scope: str
    state: str
    values: dict
    argv: list
    started_at: str
    elapsed_s: float
    timeout_s: int
    returncode: int | None
    pid: int | None
    stage: str
    stage_detail: str
    reason: str
    job_dir: Path
    log_tail: list = field(default_factory=list)
    generator_log_tail: list = field(default_factory=list)

    @property
    def is_final(self) -> bool:
        return self.state in FINAL_STATES


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _write_json(path: Path, value: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, allow_nan=False), encoding="utf-8")
    os.replace(tmp, path)


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _parse_record(path: Path) -> tuple[dict | None, str]:
    """The job record, or None and the reason it cannot be used."""
    try:
        record = _read_json(path)
    except (OSError, ValueError) as error:
        return None, f"{type(error).__name__}: {error}"
    if not isinstance(record, dict):
        return None, "job.json is not a JSON object"
    missing = [name for name in REQUIRED_RECORD_FIELDS if name not in record]
    if missing:
        return None, f"job.json lacks {missing}"
    try:
        float(record["started_epoch"]), float(record["timeout_s"])
    except (TypeError, ValueError):
        return None, "job.json has a non-numeric started_epoch or timeout_s"
    if not isinstance(record["state"], str) or not isinstance(record["key"], str):
        return None, "job.json has a non-string state or key"
    return record, ""


def process_alive(pid: int | None, recorded_token: str | None) -> bool:
    """A recorded process is alive only if its pid is alive and the process holding that pid now is the one
    that was recorded. When a token was recorded but the current one cannot be read (access denied), the pid
    is not this process and is never signalled. Legacy records without a token keep the pid-only check."""
    if not pid_alive(pid):
        return False
    if recorded_token is None:
        return True
    return process_start_token(pid) == recorded_token


def pid_recycled(pid: int | None, recorded_token: str | None) -> bool:
    """The pid is alive but belongs to a different process than the one recorded."""
    return pid_alive(pid) and not process_alive(pid, recorded_token)


def tail(path: Path, lines: int = LOG_TAIL_LINES, max_bytes: int = 256 * 1024) -> list[str]:
    """The last lines of a log, reading at most max_bytes from the end."""
    if not path.is_file():
        return []
    size = path.stat().st_size
    with path.open("rb") as handle:
        handle.seek(max(0, size - max_bytes))
        data = handle.read().decode("utf-8", errors="replace")
    return data.splitlines()[-lines:]


def infer_stage(key: str, job_dir: Path) -> tuple[str, str]:
    """Progress from files the command writes. Labelled as inferred, because the script prints none."""
    if key != "real-exercise":
        return "", ""
    out = job_dir / "exercise"
    if (out / "exercise.json").is_file():
        return "complete", "exercise.json written"
    if (out / "freeze.json").is_file():
        return "freeze written", "waiting for the backup and report step"
    if (out / "models").is_dir():
        return "training and calibration", "model directory exists; calibration and freeze in progress"
    if (out / "work").is_dir():
        logs = sorted((out / "work").glob("generator-*.log"))
        detail = logs[-1].read_text(encoding="utf-8", errors="replace").splitlines()[-1:] if logs else []
        return "RF generation", (detail[0] if detail else "generator started")
    return "starting", "no output folder yet"


def generator_log_tail(key: str, job_dir: Path) -> list[str]:
    """The RF generator writes its own log; the script itself prints nothing until it finishes."""
    if key != "real-exercise":
        return []
    logs = sorted((job_dir / "exercise" / "work").glob("generator-*.log"))
    return tail(logs[-1], lines=40) if logs else []


# Thin alias kept for callers and tests; the platform-specific logic lives in geodash.portable.
_pid_alive = pid_alive


class JobManager:
    def __init__(self, home: Path, *, registry: Mapping | None = None,
                 popen: Callable[..., subprocess.Popen] = subprocess.Popen,
                 environment: Mapping[str, str] | None = None,
                 argv_guard: Callable[[list, C.CommandSpec], None] | None = None,
                 python: str | None = None, clock: Callable[[], float] = time.time):
        self.home = assert_outside_repo(home)
        self.jobs_dir = self.home / "jobs"
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self.registry = C.REGISTRY if registry is None else registry
        self._popen = popen
        self._environment = dict(environment) if environment is not None else C.build_environment()
        self._guard = C.assert_safe_argv if argv_guard is None else argv_guard
        self._python = python or sys.executable
        self._clock = clock
        self._procs: dict[str, subprocess.Popen] = {}
        self._lock_path = self.home / "manager.lock"
        self._held = threading.local()

    @contextmanager
    def _exclusive(self):
        # Re-entrant per thread: start() holds the lock while list_jobs() may settle (and record) a job.
        if getattr(self._held, "depth", 0):
            self._held.depth += 1
            try:
                yield
            finally:
                self._held.depth -= 1
            return
        with self._lock_path.open("a+") as handle:
            with exclusive_lock(handle):
                self._held.depth = 1
                try:
                    yield
                finally:
                    self._held.depth = 0

    def start(self, key: str, values: Mapping | None = None) -> str:
        with self._exclusive():
            jobs = self.list_jobs()
            for job in jobs:
                if job.state == RUNNING:
                    raise ActiveJobError(f"job {job.job_id} is still running; wait for it or cancel it")
            for job in jobs:
                if job.state == RECORD_UNREADABLE:
                    raise RecordUnreadable(job.job_dir, job.reason)
            spec, resolved = C.validate(key, values, self.registry)
            job_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + secrets.token_hex(3)
            job_dir = self.jobs_dir / job_id
            job_dir.mkdir()
            argv = spec.builder(resolved, job_dir, self._python)
            self._guard(argv, spec)
            with (job_dir / "log.txt").open("wb") as log:
                proc = self._popen(argv, cwd=str(REPO_ROOT), env=self._environment, stdin=subprocess.DEVNULL,
                                   stdout=log, stderr=subprocess.STDOUT, shell=False, **popen_kwargs())
            self._procs[job_id] = proc
            _write_json(job_dir / "job.json", {
                "job_id": job_id, "key": key, "title": spec.title, "scope": spec.scope, "values": resolved,
                "argv": argv, "pid": proc.pid, "owner_pid": os.getpid(),
                "pid_start_token": process_start_token(proc.pid), "owner_start_token": process_start_token(os.getpid()),
                "started_at": _now_iso(), "started_epoch": self._clock(),
                "timeout_s": spec.timeout_s, "state": RUNNING, "returncode": None, "reason": "",
            })
            return job_id

    def _spec(self, key: str) -> C.CommandSpec | None:
        return self.registry.get(key)

    def owned_process(self, job_id: str) -> subprocess.Popen | None:
        """The Popen handle when this manager started the job, else None."""
        return self._procs.get(job_id)

    def _finish(self, job_id: str, record: dict, state: str, returncode: int | None, reason: str) -> dict:
        """Record the outcome and return the record as it stands on disk afterwards.

        The first final state written wins: a supervisor and a cancelling process may both settle the same
        job. A cancellation requested before the process ended is recorded as such, never as a failure or
        a success. The one later change allowed: the manager that owns the reaped process fills in the exit
        status a non-owning canceller could not know, keeping the CANCELLED state. An unreadable record is
        left untouched.
        """
        path = self.jobs_dir / job_id / "job.json"
        with self._exclusive():
            current, why = _parse_record(path)
            if current is None:
                return {**record, "state": RECORD_UNREADABLE, "returncode": None,
                        "reason": f"job.json could not be read: {why}; the record is left unchanged"}
            if current["state"] in FINAL_STATES:
                proc = self._procs.get(job_id)
                if current["state"] == CANCELLED == state and current.get("returncode") is None \
                        and returncode is not None and proc is not None and proc.returncode == returncode:
                    current["returncode"] = returncode
                    _write_json(path, current)
                return current
            if current.get("cancel_requested_at") and state != CANCELLED:
                state, reason = CANCELLED, CANCEL_REASON
            current.update({"state": state, "returncode": returncode, "reason": reason, "finished_at": _now_iso()})
            _write_json(path, current)
            return current

    def _stop(self, job_id: str, pid: int) -> None:
        """Terminate the process tree, then reap the child so its pid is no longer reported as alive."""
        terminate_tree(pid, self._procs.get(job_id), TERMINATE_GRACE_S, self._clock)

    def _unreadable(self, job_id: str, why: str) -> JobStatus:
        job_dir = self.jobs_dir / job_id
        return JobStatus(
            job_id=job_id, key="", title="unreadable job record", scope="", state=RECORD_UNREADABLE, values={},
            argv=[], started_at="", elapsed_s=0.0, timeout_s=0, returncode=None, pid=None, stage="",
            stage_detail="", reason=f"job.json could not be read: {why}; the record is left unchanged",
            job_dir=job_dir, log_tail=tail(job_dir / "log.txt"),
        )

    def status(self, job_id: str) -> JobStatus:
        path = self.jobs_dir / job_id / "job.json"
        if not path.is_file():
            raise UnknownJobError(job_id)
        record, why = _parse_record(path)
        if record is None:
            return self._unreadable(job_id, why)
        job_dir = self.jobs_dir / job_id
        elapsed = max(0.0, self._clock() - float(record["started_epoch"]))
        returncode = record.get("returncode")
        state = record["state"]
        reason = record.get("reason", "")
        if state == RUNNING:
            proc = self._procs.get(job_id)
            if proc is not None and proc.poll() is not None:
                returncode = proc.returncode
            alive = returncode is None and process_alive(record["pid"], record.get("pid_start_token"))
            if alive and elapsed > record["timeout_s"]:
                self._stop(job_id, record["pid"])
                record = self._finish(job_id, record, TIMED_OUT, returncode,
                                      f"exceeded the {record['timeout_s']} s GUI timeout; process group stopped")
                state, returncode, reason = record["state"], record.get("returncode"), record.get("reason", "")
            elif not alive and self._owner_still_watching(record, proc is not None):
                # Another live dashboard process started this job and holds its exit status. Report it as
                # running, and write nothing: only the owner may record the outcome.
                state = RUNNING
                reason = "the process has ended; the dashboard process that started it will record the exit status"
            elif not alive:
                spec = self._spec(record["key"])
                ok, why = spec.success(job_dir) if spec else (returncode == 0, "exit status")
                if returncode is None:
                    state = FINISHED_UNRECORDED if ok else FAILED
                    reason = (f"{why}; exit status not recorded because the job outlived the dashboard process "
                              "that started it" if ok else
                              f"process ended with no recorded exit status and its outputs did not verify: {why}")
                else:
                    ok_rcs = spec.ok_returncodes if spec else (0,)
                    state = SUCCEEDED if (returncode in ok_rcs and ok) else FAILED
                    # A non-zero accepted exit status (the preflight scripts' documented BLOCKED=4)
                    # stays visible in the reason even on success; it is a reading, not an authorization.
                    reason = why if (state == SUCCEEDED and returncode == 0) else f"exit status {returncode}; {why}"
                record = self._finish(job_id, record, state, returncode, reason)
                state, returncode, reason = record["state"], record.get("returncode"), record.get("reason", "")
        elif state == CANCELLED and returncode is None:
            proc = self._procs.get(job_id)
            if proc is not None and proc.poll() is not None:
                record = self._finish(job_id, record, CANCELLED, proc.returncode, reason)
                returncode = record.get("returncode")
        stage, detail = infer_stage(record["key"], job_dir)
        return JobStatus(
            job_id=job_id, key=record["key"], title=record["title"], scope=record["scope"], state=state,
            values=record["values"], argv=record["argv"], started_at=record["started_at"], elapsed_s=elapsed,
            timeout_s=record["timeout_s"], returncode=returncode, pid=record["pid"], stage=stage,
            stage_detail=detail, reason=reason, job_dir=job_dir, log_tail=tail(job_dir / "log.txt"),
            generator_log_tail=generator_log_tail(record["key"], job_dir),
        )

    @staticmethod
    def _owner_still_watching(record: dict, owned_here: bool) -> bool:
        owner = record.get("owner_pid")
        if owned_here or owner is None or owner == os.getpid():
            return False
        return process_alive(owner, record.get("owner_start_token"))

    def cancel(self, job_id: str) -> JobStatus:
        """Stop a running job's process tree. A pid that now belongs to another process is never signalled;
        the job then settles by the ordinary rules, because the recorded process is gone."""
        path = self.jobs_dir / job_id / "job.json"
        if not path.is_file():
            raise UnknownJobError(job_id)
        record, _ = _parse_record(path)
        if record is not None and record["state"] == RUNNING \
                and process_alive(record["pid"], record.get("pid_start_token")):
            with self._exclusive():
                current, _ = _parse_record(path)
                marked = current is not None and current["state"] == RUNNING
                if marked:
                    current["cancel_requested_at"] = _now_iso()
                    _write_json(path, current)
            if marked:
                self._stop(job_id, record["pid"])
                proc = self._procs.get(job_id)
                if proc is not None:
                    proc.poll()
                self._finish(job_id, record, CANCELLED, proc.returncode if proc is not None else None,
                             CANCEL_REASON)
        return self.status(job_id)

    def list_jobs(self) -> list[JobStatus]:
        out = []
        for path in sorted(self.jobs_dir.iterdir(), reverse=True):
            if (path / "job.json").is_file():
                out.append(self.status(path.name))
        return out


def read_host_report(job_dir: Path) -> dict | None:
    path = job_dir / "host.json"
    return _read_json(path) if path.is_file() else None


__all__ = ["JobManager", "JobStatus", "ActiveJobError", "RecordUnreadable", "UnknownJobError", "infer_stage", "tail",
           "process_alive", "pid_recycled", "RUNNING", "SUCCEEDED", "FAILED", "CANCELLED", "TIMED_OUT", "FINISHED_UNRECORDED",
           "RECORD_UNREADABLE", "FINAL_STATES"]

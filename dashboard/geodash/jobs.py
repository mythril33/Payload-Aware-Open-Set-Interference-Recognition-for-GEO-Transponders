"""Job manager for allowlisted development commands.

One job runs at a time (an exclusive file lock guards the start). Each job is a child process in its own
session (POSIX) or process group (native Windows), started without a shell, with the fixed environment
from commands.build_environment. Its folder, log and job.json live under run_home(), outside the
repository. Progress is inferred from the files a command writes, and the report says so. A GUI timeout
terminates the whole process tree. All platform-specific mechanics live in geodash.portable.
"""
from __future__ import annotations

import json
import os
import secrets
import subprocess
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping

from . import commands as C
from .paths import REPO_ROOT, assert_outside_repo
from .portable import exclusive_lock, pid_alive, popen_kwargs, terminate_tree

RUNNING, SUCCEEDED, FAILED, CANCELLED, TIMED_OUT = "running", "succeeded", "failed", "cancelled", "timed_out"
# The process ended, its outputs verified, but no exit status was recorded (the dashboard process that
# started it is gone). Reported as such, never as a success with an exit status of zero.
FINISHED_UNRECORDED = "finished_unrecorded"
FINAL_STATES = frozenset({SUCCEEDED, FAILED, CANCELLED, TIMED_OUT, FINISHED_UNRECORDED})
TERMINATE_GRACE_S = 5.0
LOG_TAIL_LINES = 120


class ActiveJobError(RuntimeError):
    """Another job is still running. Only one bounded job runs at a time."""


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

    @contextmanager
    def _exclusive(self):
        with self._lock_path.open("a+") as handle:
            with exclusive_lock(handle):
                yield

    def _record(self, job_id: str) -> dict:
        path = self.jobs_dir / job_id / "job.json"
        if not path.is_file():
            raise UnknownJobError(job_id)
        return _read_json(path)

    def start(self, key: str, values: Mapping | None = None) -> str:
        with self._exclusive():
            for job in self.list_jobs():
                if job.state == RUNNING:
                    raise ActiveJobError(f"job {job.job_id} is still running; wait for it or cancel it")
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
                "started_at": _now_iso(), "started_epoch": self._clock(),
                "timeout_s": spec.timeout_s, "state": RUNNING, "returncode": None, "reason": "",
            })
            return job_id

    def _spec(self, key: str) -> C.CommandSpec | None:
        return self.registry.get(key)

    def _finish(self, job_id: str, record: dict, state: str, returncode: int | None, reason: str) -> None:
        record.update({"state": state, "returncode": returncode, "reason": reason, "finished_at": _now_iso()})
        _write_json(self.jobs_dir / job_id / "job.json", record)

    def _stop(self, job_id: str, pid: int) -> None:
        """Terminate the process tree, then reap the child so its pid is no longer reported as alive."""
        terminate_tree(pid, self._procs.get(job_id), TERMINATE_GRACE_S, self._clock)

    def status(self, job_id: str) -> JobStatus:
        record = self._record(job_id)
        job_dir = self.jobs_dir / job_id
        elapsed = max(0.0, self._clock() - float(record["started_epoch"]))
        returncode = record.get("returncode")
        state = record["state"]
        reason = record.get("reason", "")
        if state == RUNNING:
            proc = self._procs.get(job_id)
            if proc is not None and proc.poll() is not None:
                returncode = proc.returncode
            alive = returncode is None and _pid_alive(record["pid"])
            if alive and elapsed > record["timeout_s"]:
                self._stop(job_id, record["pid"])
                state, reason = TIMED_OUT, f"exceeded the {record['timeout_s']} s GUI timeout; process group stopped"
                self._finish(job_id, record, state, returncode, reason)
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
                    state = SUCCEEDED if (returncode == 0 and ok) else FAILED
                    reason = why if state == SUCCEEDED else f"exit status {returncode}; {why}"
                self._finish(job_id, record, state, returncode, reason)
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
        return _pid_alive(owner)

    def cancel(self, job_id: str) -> JobStatus:
        record = self._record(job_id)
        if record["state"] == RUNNING and _pid_alive(record["pid"]):
            self._stop(job_id, record["pid"])
            proc = self._procs.get(job_id)
            if proc is not None:
                proc.poll()
            self._finish(job_id, record, CANCELLED, None, "cancelled by the researcher; process group stopped")
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


__all__ = ["JobManager", "JobStatus", "ActiveJobError", "UnknownJobError", "infer_stage", "tail",
           "RUNNING", "SUCCEEDED", "FAILED", "CANCELLED", "TIMED_OUT", "FINISHED_UNRECORDED", "FINAL_STATES"]

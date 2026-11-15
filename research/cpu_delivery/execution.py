"""Process lifecycle for the bounded CPU campaign; no ML dependencies."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import signal
import subprocess
import time


@contextmanager
def campaign_lock(out):
    """Serialize writers to a resolved output path, including --resume.

    Keep the sibling file: unlinking a lock file can split contenders across
    different inodes. The OS releases the lock when this handle is closed.
    """
    out = Path(out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    path = out.with_name(f".{out.name}.cpu-delivery.lock")
    with path.open("a+b") as lock:
        if os.name == "posix":
            import fcntl
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise RuntimeError(f"campaign already running: {out}") from error
        elif os.name == "nt":
            import msvcrt
            if path.stat().st_size == 0:
                lock.write(b"\0")
                lock.flush()
            lock.seek(0)
            try:
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as error:
                raise RuntimeError(f"campaign already running: {out}") from error
        else:
            raise RuntimeError("campaign locking requires POSIX or Windows")
        # Closing the file unlocks it on both platforms, including exceptions.
        yield


@contextmanager
def termination_signals():
    """Let normal exception unwinding clean up on TERM/HUP, like Ctrl-C."""
    def stop(signum, frame):
        raise SystemExit(128 + signum)

    previous = {}
    try:
        for name in ("SIGTERM", "SIGHUP"):
            sig = getattr(signal, name, None)
            if sig is not None:
                previous[sig] = signal.signal(sig, stop)
        yield
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)


def stop_process_tree(process, log):
    """Kill descendants in the step's private process group and reap its root."""
    if os.name == "posix":
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    else:
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                       stdout=log, stderr=subprocess.STDOUT, check=False)
    process.wait()


def run_step(out, name, command, *, cwd, env, timeout, resume=False):
    """Record every completed/failed/interrupted attempt before propagating it."""
    out = Path(out)
    status = {"step": name, "command": list(command), "resume": resume,
              "started_at": datetime.now(timezone.utc).isoformat(),
              "returncode": None, "timed_out": False, "interrupted": False}
    start = time.monotonic()
    with (out / f"{name}.log").open("a", encoding="utf-8") as log:
        process = None
        try:
            process = subprocess.Popen(command, cwd=cwd, env=env, stdout=log,
                                       stderr=subprocess.STDOUT,
                                       start_new_session=(os.name == "posix"))
            status["returncode"] = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            status["timed_out"] = True
            stop_process_tree(process, log)
            status["returncode"] = process.returncode
        except BaseException as error:
            status["interrupted"] = isinstance(error, (KeyboardInterrupt, SystemExit))
            status["error_type"] = type(error).__name__
            if process is not None:
                stop_process_tree(process, log)
                status["returncode"] = process.returncode
            raise
        finally:
            status["elapsed_s"] = time.monotonic() - start
            with (out / "execution.jsonl").open("a", encoding="utf-8") as ledger:
                ledger.write(json.dumps(status, allow_nan=False) + "\n")
    if status["timed_out"] or status["returncode"] != 0:
        raise RuntimeError(f"{name} failed/timed out; inspect its log; campaign incomplete")
    return status

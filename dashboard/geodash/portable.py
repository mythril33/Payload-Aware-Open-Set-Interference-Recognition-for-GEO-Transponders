"""Platform seam for the dashboard job manager.

On POSIX (Linux, WSL2) every primitive keeps the exact semantics the dashboard has always had:
``fcntl.flock`` for the manager lock, ``start_new_session`` for child isolation, ``os.kill(pid, 0)``
plus the /proc zombie check for liveness, and ``os.killpg`` SIGTERM/SIGKILL for termination.

On native Windows the same four primitives are provided with Windows mechanisms: ``msvcrt.locking``
on one guard byte, ``CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW`` creation flags, a ctypes
``OpenProcess``/``GetExitCodeProcess`` probe (``os.kill(pid, 0)`` must NEVER be used on Windows:
there it TERMINATES the target via TerminateProcess), and ``taskkill /T /F`` for the process tree.
"""
from __future__ import annotations

import errno
import os
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Callable

IS_POSIX = os.name == "posix"

if IS_POSIX:
    import fcntl
    import signal
else:  # native Windows
    import ctypes
    import ctypes.wintypes
    import msvcrt

# Windows constants (kernel32).
STILL_ACTIVE = 259
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
ERROR_ACCESS_DENIED = 5


def _kernel32():
    return ctypes.WinDLL("kernel32", use_last_error=True)


@contextmanager
def exclusive_lock(handle):
    """Exclusive lock on an open, writable file handle, held for the duration of the block.

    POSIX: fcntl.flock LOCK_EX, released with LOCK_UN (unchanged from the original jobs.py code).
    Windows: msvcrt.locking of one byte at offset 0. LK_LOCK retries about 10 times at 1 s
    intervals and then raises OSError, so the acquisition loops until the byte is locked.
    """
    if IS_POSIX:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    else:
        while True:
            handle.seek(0)
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
                break
            except OSError as error:
                # LK_LOCK raises EACCES (or EDEADLOCK) after its ~10 s of internal retries while the
                # byte is held elsewhere: keep waiting. Any other errno (bad handle, invalid region)
                # is a real error and must propagate, as the POSIX flock branch would.
                if error.errno not in (errno.EACCES, getattr(errno, "EDEADLOCK", errno.EACCES)):
                    raise
                time.sleep(0.2)
        try:
            yield
        finally:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)


def popen_kwargs() -> dict:
    """Popen keyword arguments that put the child in its own session (POSIX) or process group and
    hide any console window (Windows), so the whole tree can be terminated as one unit."""
    if IS_POSIX:
        return {"start_new_session": True}
    return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW}


def pid_alive(pid: int | None) -> bool:
    """True only for a live process. A zombie (exited, not yet reaped) is not running.

    POSIX: os.kill(pid, 0) plus the /proc/<pid>/stat zombie check, exactly as before.
    Windows: ctypes OpenProcess + GetExitCodeProcess; alive iff the exit code is STILL_ACTIVE.
    os.kill(pid, 0) is never called here on Windows, where it would TERMINATE the process.
    """
    if not pid:
        return False
    if IS_POSIX:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        stat = Path(f"/proc/{pid}/stat")
        if stat.is_file():
            try:
                state = stat.read_text(encoding="utf-8").rsplit(")", 1)[1].split()[0]
            except (OSError, IndexError):
                return True
            return state != "Z"
        return True
    kernel32 = _kernel32()
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
    if not handle:
        # Access denied means the process exists but is not ours; any other failure means gone.
        return ctypes.get_last_error() == ERROR_ACCESS_DENIED
    try:
        code = ctypes.wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return False
        return code.value == STILL_ACTIVE
    finally:
        kernel32.CloseHandle(handle)


def terminate_tree(pid: int, proc: subprocess.Popen | None, grace_s: float,
                   clock: Callable[[], float] = time.time) -> None:
    """Terminate the process tree rooted at pid, then reap the child when a handle exists.

    POSIX: SIGTERM to the process group, wait up to grace_s (polling pid_alive when no Popen
    handle exists), then SIGKILL to the group — the exact semantics jobs.py always had.
    Windows: ``taskkill /PID <pid> /T /F`` kills the tree forcefully; then wait on the handle,
    or poll pid_alive until the process is dead or the deadline passes.
    """
    if IS_POSIX:
        _signal_group(pid, signal.SIGTERM)
        try:
            if proc is not None:
                proc.wait(timeout=grace_s)
            else:
                deadline = clock() + grace_s
                while pid_alive(pid) and clock() < deadline:
                    time.sleep(0.1)
                if pid_alive(pid):
                    raise subprocess.TimeoutExpired(cmd=str(pid), timeout=grace_s)
        except subprocess.TimeoutExpired:
            _signal_group(pid, signal.SIGKILL)
            if proc is not None:
                proc.wait(timeout=grace_s)
        return
    # pid-reuse caveat (shared with the POSIX killpg path after a dashboard restart): only the pid
    # from job.json identifies the tree, so a recycled pid could name an unrelated process.
    subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
    try:
        if proc is not None:
            proc.wait(timeout=grace_s)
        else:
            deadline = clock() + grace_s
            while pid_alive(pid) and clock() < deadline:
                time.sleep(0.1)
    except subprocess.TimeoutExpired:
        pass
    if pid_alive(pid):
        # One escalation retry, mirroring the POSIX SIGTERM -> SIGKILL second attempt.
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
        if proc is not None:
            try:
                proc.wait(timeout=grace_s)
            except subprocess.TimeoutExpired:
                pass
        else:
            deadline = clock() + grace_s
            while pid_alive(pid) and clock() < deadline:
                time.sleep(0.1)


def _signal_group(pid: int, sig: int) -> None:
    try:
        os.killpg(pid, sig)
    except ProcessLookupError:
        pass


__all__ = ["IS_POSIX", "exclusive_lock", "popen_kwargs", "pid_alive", "terminate_tree"]

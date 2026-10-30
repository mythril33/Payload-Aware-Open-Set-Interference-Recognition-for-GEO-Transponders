"""Platform seam tests: exclusive file lock, Popen isolation kwargs, pid liveness, process-tree
termination, and the platform gate on POSIX-only commands.

Platform-neutral tests run on both Linux and native Windows CI; branch-specific behaviour is gated
with skipif markers so the same file passes on both.
"""
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "dashboard"), str(ROOT / "src"), str(ROOT)]

from geodash import commands as C  # noqa: E402
from geodash import jobs as J  # noqa: E402
from geodash import portable as P  # noqa: E402

posix_only = pytest.mark.skipif(os.name != "posix", reason="POSIX-only behaviour")
windows_only = pytest.mark.skipif(os.name != "nt", reason="native-Windows-only behaviour")


# ---- popen kwargs and alias wiring -----------------------------------------------------------------------

def test_popen_kwargs_isolate_the_child_on_this_platform():
    kwargs = P.popen_kwargs()
    if os.name == "posix":
        assert kwargs == {"start_new_session": True}
    else:
        assert kwargs["creationflags"] & subprocess.CREATE_NEW_PROCESS_GROUP
        assert kwargs["creationflags"] & subprocess.CREATE_NO_WINDOW


def test_the_job_manager_pid_alive_is_the_portable_one():
    assert J._pid_alive is P.pid_alive


# ---- exclusive lock ---------------------------------------------------------------------------------------

# A second process tries to take the same lock without blocking and reports the outcome. Run as a
# separate process because both flock and msvcrt locks are held per process/file region.
LOCK_PROBE = r"""
import sys
handle = open(sys.argv[1], "a+")
try:
    if sys.platform == "win32":
        import msvcrt
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        print("acquired")
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        print("acquired")
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
except OSError:
    print("blocked")
"""


def _probe_lock(path: Path) -> str:
    result = subprocess.run([sys.executable, "-c", LOCK_PROBE, str(path)],
                            capture_output=True, text=True, timeout=60)
    return result.stdout.strip()


def test_exclusive_lock_excludes_a_second_holder_and_releases_on_exit(tmp_path):
    path = tmp_path / "manager.lock"
    with path.open("a+") as handle:
        with P.exclusive_lock(handle):
            assert _probe_lock(path) == "blocked"
        assert _probe_lock(path) == "acquired"


def test_exclusive_lock_can_be_taken_again_by_the_same_handle(tmp_path):
    path = tmp_path / "manager.lock"
    with path.open("a+") as handle:
        for _ in range(2):
            with P.exclusive_lock(handle):
                pass
    assert _probe_lock(path) == "acquired"


# ---- pid_alive --------------------------------------------------------------------------------------------

def test_pid_alive_is_false_for_missing_pids():
    assert P.pid_alive(None) is False
    assert P.pid_alive(0) is False


def test_pid_alive_sees_a_live_child_and_not_an_exited_one():
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:
        assert P.pid_alive(proc.pid) is True
    finally:
        proc.terminate()
        proc.wait(timeout=30)
    deadline = time.time() + 10
    while P.pid_alive(proc.pid) and time.time() < deadline:
        time.sleep(0.1)
    assert P.pid_alive(proc.pid) is False


@posix_only
def test_pid_alive_treats_a_posix_zombie_as_not_running():
    # The child exits but is not reaped (no poll/wait), so it stays a zombie owned by this process.
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    stat = Path(f"/proc/{proc.pid}/stat")
    state, deadline = "", time.time() + 10
    while state != "Z" and time.time() < deadline:
        state = stat.read_text(encoding="utf-8").rsplit(")", 1)[1].split()[0]
        time.sleep(0.05)
    assert state == "Z", "the child did not become a zombie in time"
    assert P.pid_alive(proc.pid) is False
    proc.wait(timeout=10)


# ---- terminate_tree ---------------------------------------------------------------------------------------

# The child starts a grandchild, prints the grandchild's pid and sleeps.
TREE_PROGRAM = ("import subprocess, sys, time; "
                "g = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)']); "
                "print(g.pid, flush=True); time.sleep(120)")


def _start_tree():
    proc = subprocess.Popen([sys.executable, "-c", TREE_PROGRAM], stdout=subprocess.PIPE,
                            text=True, **P.popen_kwargs())
    grandchild_pid = int(proc.stdout.readline())
    assert P.pid_alive(proc.pid) and P.pid_alive(grandchild_pid)
    return proc, grandchild_pid


def _assert_tree_dead(proc, grandchild_pid):
    assert not P.pid_alive(proc.pid)
    deadline = time.time() + 15
    while P.pid_alive(grandchild_pid) and time.time() < deadline:
        time.sleep(0.1)
    assert not P.pid_alive(grandchild_pid)


@posix_only
def test_terminate_tree_kills_the_child_and_its_grandchild_on_posix():
    proc, grandchild_pid = _start_tree()
    P.terminate_tree(proc.pid, proc, 10.0, time.time)
    _assert_tree_dead(proc, grandchild_pid)


@posix_only
def test_terminate_tree_without_a_popen_handle_polls_until_the_group_is_dead():
    proc, grandchild_pid = _start_tree()
    try:
        P.terminate_tree(proc.pid, None, 10.0, time.time)
    finally:
        proc.wait(timeout=30)  # reap in this test; the real no-handle caller has no handle to reap
    _assert_tree_dead(proc, grandchild_pid)


@windows_only
def test_terminate_tree_kills_the_child_and_its_grandchild_on_windows():
    proc, grandchild_pid = _start_tree()
    P.terminate_tree(proc.pid, proc, 30.0, time.time)
    _assert_tree_dead(proc, grandchild_pid)


@windows_only
def test_terminate_tree_without_a_popen_handle_on_windows():
    proc, grandchild_pid = _start_tree()
    try:
        P.terminate_tree(proc.pid, None, 30.0, time.time)
    finally:
        proc.wait(timeout=60)
    _assert_tree_dead(proc, grandchild_pid)


# ---- the platform gate on POSIX-only commands -------------------------------------------------------------

def test_validate_refuses_real_exercise_when_the_platform_is_not_posix(monkeypatch):
    monkeypatch.setattr(C, "current_platform_is_posix", lambda: False)
    with pytest.raises(C.CommandRefused, match=r"requires a POSIX system \(Linux or WSL2\)"):
        C.validate("real-exercise")
    ok, reason = C.is_available(C.REGISTRY["real-exercise"])
    assert ok is False and "native Windows" in reason and "POSIX-only file locks" in reason


def test_platform_independent_commands_stay_available_off_posix(monkeypatch):
    monkeypatch.setattr(C, "current_platform_is_posix", lambda: False)
    for key in ("preflight-gates", "host-inventory", "test-dashboard", "test-cpu-execution"):
        assert C.is_available(C.REGISTRY[key]) == (True, "")
        C.validate(key)  # does not raise


def test_real_exercise_is_available_when_the_platform_check_says_posix(monkeypatch):
    monkeypatch.setattr(C, "current_platform_is_posix", lambda: True)
    assert C.is_available(C.REGISTRY["real-exercise"]) == (True, "")
    spec, resolved = C.validate("real-exercise")
    assert resolved == {"groups": 1}


def test_only_real_exercise_requires_posix():
    assert [key for key, spec in C.REGISTRY.items() if spec.requires_posix] == ["real-exercise"]

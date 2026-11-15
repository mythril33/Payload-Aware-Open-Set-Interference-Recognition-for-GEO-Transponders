"""One-click pilot backend tests: engine and source identity, preflight codes, the supervisor, cancellation,
restart recovery, the UI service and the home-page states.

Child processes are harmless `sys.executable -c` programs injected as a test "real-exercise" spec; the argv
guard is disabled only for those injected specs. The real registry is only validated and its argv built and
inspected, never executed. Runs on Linux and native Windows; POSIX-only and git-dependent tests are marked.
"""
import hashlib
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "dashboard"), str(ROOT / "src"), str(ROOT)]

from geodash import commands as C  # noqa: E402
from geodash import jobs as J  # noqa: E402
from geodash import pilot as P  # noqa: E402
from geodash import repo_status  # noqa: E402

ORIGINAL_SOURCE_IDENTITY = P.source_identity

posix_only = pytest.mark.skipif(os.name != "posix", reason="POSIX signals and sessions")
needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git is not installed")

REPORT = {"schema": C.EXERCISE_SCHEMA, "scope": C.SCOPE_DEVELOPMENT, "heldout_reads": 0, "gpu_exercised": False,
          "production_authorized": False, "benchmark_complete": False}

# argv: exercise folder, seconds, mode. Writes the outputs real-exercise writes, in the same order.
PROGRAM = r"""
import json, os, sys, time
out, seconds, mode = sys.argv[1], float(sys.argv[2]), sys.argv[3]
os.makedirs(os.path.join(out, "work"), exist_ok=True)
print("generator started", flush=True)
if mode == "corrupt-record":
    time.sleep(0.3)
    with open(os.path.join(os.path.dirname(out), "job.json"), "w") as handle:
        handle.write("{corrupt")
if mode == "delete-record":
    time.sleep(0.3)
    os.remove(os.path.join(os.path.dirname(out), "job.json"))
time.sleep(seconds)
if mode == "fail":
    sys.exit(5)
report = %s
if mode == "breach":
    report.update({"heldout_reads": 3, "gpu_exercised": float("nan")})
with open(os.path.join(out, "freeze.json"), "w") as handle:
    handle.write("{}")
with open(os.path.join(out, "exercise.json"), "w") as handle:
    handle.write("{truncated" if mode == "corrupt" else json.dumps(report))
print("finished", flush=True)
""" % repr(REPORT)


def _pilot_spec(seconds=0.3, mode="ok", timeout_s=60):
    def builder(values, job_dir, python):
        return [sys.executable, "-c", PROGRAM, str(job_dir / "exercise"), str(seconds), mode]
    return C.CommandSpec(key=P.PILOT_KEY, title="injected pilot", scope=C.SCOPE_DEVELOPMENT,
                         description="injected test program", params=(C._groups_choice(),), builder=builder,
                         timeout_s=timeout_s, success=C._exercise_success, outputs=P.PILOT_OUTPUTS)


def _quick_spec(key, seconds):
    return C.CommandSpec(key=key, title=key, scope=C.SCOPE_CPU_TEST, description="", params=(),
                         builder=lambda v, d, p: [sys.executable, "-c", f"import time; time.sleep({seconds})"],
                         timeout_s=60, success=C._exit_zero)


def _manager_at(home, *specs):
    return J.JobManager(Path(home), registry={spec.key: spec for spec in specs}, argv_guard=lambda argv, spec: None)


def _manager(tmp_path, *specs):
    return _manager_at(tmp_path / "home", *specs)


def _verified_source(*args, **kwargs):
    return {"mode": "git", "commit": "0" * 40, "verified": True, "problems": [], "manifest_sha256": None,
            "limitations": "test"}


def _capable_engine(**kwargs):
    return {"id": "linux", "label": "Linux", "label_tr": "Linux", "pilot_capable": True}


def apply_ready(target):
    """Every preflight check passes. Used in-process (monkeypatch) and in supervisor subprocesses (setattr)."""
    target(P, "engine", _capable_engine)
    target(P, "source_identity", _verified_source)
    target(P, "find_spec", lambda name: object())
    target(P, "_disk_free_gib", lambda path: 100.0)


@pytest.fixture
def ready(monkeypatch):
    apply_ready(monkeypatch.setattr)


def _wait(predicate, limit_s=20.0):
    deadline = time.time() + limit_s
    while not predicate() and time.time() < deadline:
        time.sleep(0.05)
    return predicate()


def _log_has(job_dir, text):
    path = job_dir / "log.txt"
    return path.is_file() and text in path.read_text(encoding="utf-8", errors="replace")


def _strict_loads(text):
    def refuse(constant):
        raise ValueError(f"non-strict JSON constant {constant}")
    return json.loads(text, parse_constant=refuse)


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _dead_pid():
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait(timeout=30)
    return proc.pid


# ---- engine ----------------------------------------------------------------------------------------------

@pytest.mark.parametrize("osrelease,os_name,environ,expected,capable", [
    ("5.15.167.4-microsoft-standard-WSL2\n", "posix", {}, "wsl2", True),
    ("4.4.0-19041-Microsoft", "posix", {}, "wsl1", False),
    ("5.10.16.3-microsoft-standard", "posix", {"WSL_INTEROP": "/run/WSL/1_interop"}, "wsl2", True),
    ("4.4.0-19041-Microsoft", "posix", {"WSL_INTEROP": "/run/WSL/1_interop"}, "wsl1", False),
    ("5.4.72-microsoft-custom", "posix", {"WSL_INTEROP": "/run/WSL/1_interop"}, "wsl1", False),
    ("6.6.36.6-custom-WSL2+", "posix", {}, "wsl2", True),
    ("6.8.0-45-generic", "posix", {}, "linux", True),
    ("", "nt", {}, "native-windows", False),
    ("", "java", {}, "other", False),
])
def test_engine_detection(osrelease, os_name, environ, expected, capable):
    eng = P.engine(osrelease=osrelease, os_name=os_name, environ=environ)
    assert eng["id"] == expected and eng["pilot_capable"] is capable
    assert eng["label"] and eng["label_tr"] and eng["label"].isascii()


def test_engine_labels_are_proper_turkish_and_never_claim_more_than_inspection_on_windows():
    native = P.engine(osrelease="", os_name="nt", environ={})
    assert native["label_tr"] == "Yerel Windows (yalnız inceleme)" and "inspection only" in native["label"]
    assert "ğ" in P.engine(osrelease="4.4.0-Microsoft", os_name="posix", environ={})["label_tr"]


def test_engine_of_this_process_matches_the_platform():
    eng = P.engine()
    if os.name == "nt":
        assert eng["id"] == "native-windows" and eng["pilot_capable"] is False
        return
    assert os.name == "posix"
    try:
        release = Path("/proc/sys/kernel/osrelease").read_text(encoding="utf-8").lower()
    except OSError:
        release = ""
    if "microsoft" in release:
        wsl2 = "microsoft-standard" in release or "wsl2" in release
        assert eng["id"] == ("wsl2" if wsl2 else "wsl1") and eng["pilot_capable"] is wsl2
    else:
        assert eng["id"] == "linux" and eng["pilot_capable"] is True


# ---- source identity: git checkout -----------------------------------------------------------------------

def _git(root, *args):
    return subprocess.run(["git", "-c", "user.email=test@example.invalid", "-c", "user.name=test",
                           "-c", "commit.gpgsign=false", "-c", "core.autocrlf=false", *args],
                          cwd=str(root), capture_output=True, text=True, check=True).stdout.strip()


TREE = {"src/geosim/a.py": "A = 1\n", "scripts/s.py": "print('s')\n", "configs/c.json": "{}\n",
        "dashboard/d.py": "D = 1\n", "pyproject.toml": "[project]\nname = 'x'\n", "docs/x.md": "# x\n",
        "tests/test_x.py": "def test_x():\n    pass\n"}


def _write_tree(root):
    for rel, text in TREE.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))


@pytest.fixture
def git_repo(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    _write_tree(root)
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "init")
    return root, _git(root, "rev-parse", "HEAD")


@needs_git
def test_a_clean_git_checkout_is_verified(git_repo):
    root, head = git_repo
    identity = P.source_identity(root)
    assert identity["mode"] == "git" and identity["commit"] == head and identity["verified"] is True
    assert identity["problems"] == [] and identity["manifest_sha256"] is None
    assert P.source_identity(root, expect_commit=head)["verified"] is True


@needs_git
@pytest.mark.parametrize("rel", ["src/geosim/a.py", "scripts/s.py", "configs/c.json", "dashboard/d.py",
                                 "pyproject.toml"])
def test_a_modified_governed_file_is_a_problem(git_repo, rel):
    root, _ = git_repo
    (root / rel).write_text("changed = True\n", encoding="utf-8")
    identity = P.source_identity(root)
    assert identity["verified"] is False
    assert any(p.startswith("governed files modified") and rel in p for p in identity["problems"])


@needs_git
def test_a_wrong_expected_commit_is_a_problem(git_repo):
    root, _ = git_repo
    identity = P.source_identity(root, expect_commit="f" * 40)
    assert identity["verified"] is False and any("does not match" in p for p in identity["problems"])


@needs_git
def test_a_modified_or_untracked_non_governed_file_keeps_the_checkout_verified(git_repo):
    root, _ = git_repo
    (root / "docs" / "x.md").write_text("# edited\n", encoding="utf-8")
    (root / "tests" / "test_x.py").write_text("# edited\n", encoding="utf-8")
    (root / "notes.txt").write_text("untracked\n", encoding="utf-8")
    assert P.source_identity(root)["verified"] is True


# ---- source identity: package snapshot -------------------------------------------------------------------

COMMIT = "a" * 40


def _manifest(root, **overrides):
    files = {}
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.name != P.MANIFEST_NAME:
            files[path.relative_to(root).as_posix()] = _sha256(path)
    manifest = {"schema": P.MANIFEST_SCHEMA, "commit": COMMIT, "source": "git archive HEAD", "files": files}
    manifest.update(overrides)
    data = json.dumps(manifest, indent=2).encode("utf-8")
    (root / P.MANIFEST_NAME).write_bytes(data)
    return hashlib.sha256(data).hexdigest()


@pytest.fixture
def snapshot(tmp_path):
    root = tmp_path / "pkg"
    root.mkdir()
    _write_tree(root)
    return root, _manifest(root)


def test_a_valid_package_snapshot_is_verified(snapshot):
    root, digest = snapshot
    identity = P.source_identity(root, expect_commit=COMMIT, expect_manifest_sha256=digest)
    assert identity["mode"] == "package-snapshot" and identity["verified"] is True, identity["problems"]
    assert identity["commit"] == COMMIT and identity["manifest_sha256"] == digest
    assert "no Git history" in identity["limitations"] and "not a production lock" in identity["limitations"]


def test_a_tampered_snapshot_file_is_a_problem(snapshot):
    root, _ = snapshot
    (root / "docs" / "x.md").write_text("# tampered\n", encoding="utf-8")
    identity = P.source_identity(root)
    assert identity["verified"] is False and "modified file: docs/x.md" in identity["problems"]


def test_a_missing_snapshot_file_is_a_problem(snapshot):
    root, _ = snapshot
    (root / "scripts" / "s.py").unlink()
    assert "missing file: scripts/s.py" in P.source_identity(root)["problems"]


def test_an_unexpected_file_under_a_governed_tree_is_a_problem_but_bytecode_and_build_metadata_are_not(snapshot):
    root, _ = snapshot
    (root / "src" / "geosim" / "__pycache__").mkdir()
    (root / "src" / "geosim" / "__pycache__" / "a.cpython-312.pyc").write_bytes(b"\0")
    (root / "src" / "geosim.egg-info").mkdir()
    (root / "src" / "geosim.egg-info" / "PKG-INFO").write_text("Name: geosim\n", encoding="utf-8")
    assert P.source_identity(root)["verified"] is True
    (root / "src" / "geosim" / "extra.py").write_text("EXTRA = 1\n", encoding="utf-8")
    identity = P.source_identity(root)
    assert identity["verified"] is False and "unexpected file: src/geosim/extra.py" in identity["problems"]


def test_a_wrong_commit_or_manifest_digest_is_a_problem(snapshot):
    root, digest = snapshot
    assert not P.source_identity(root, expect_commit="b" * 40)["verified"]
    wrong = P.source_identity(root, expect_manifest_sha256="0" * 64)
    assert not wrong["verified"] and any("manifest sha256" in p for p in wrong["problems"])
    assert P.source_identity(root, expect_manifest_sha256=digest.upper())["verified"] is True


def test_a_worktree_overlay_package_is_unverified(snapshot):
    root, _ = snapshot
    _manifest(root, source="worktree-overlay")
    identity = P.source_identity(root)
    assert identity["mode"] == "package-snapshot" and identity["verified"] is False
    assert any("worktree-overlay" in p for p in identity["problems"])


def test_a_manifest_path_outside_the_tree_is_a_problem(snapshot):
    root, _ = snapshot
    _manifest(root, files={"../outside.txt": "0" * 64})
    assert any("outside the tree" in p for p in P.source_identity(root)["problems"])


def test_a_corrupt_manifest_and_a_tree_without_identity_are_unverified(tmp_path, snapshot):
    root, _ = snapshot
    (root / P.MANIFEST_NAME).write_text("{corrupt", encoding="utf-8")
    assert P.source_identity(root)["verified"] is False
    bare = tmp_path / "bare"
    bare.mkdir()
    identity = P.source_identity(bare)
    assert identity["mode"] == "unverified" and identity["verified"] is False and identity["commit"] is None


# ---- preflight -------------------------------------------------------------------------------------------

def test_preflight_passes_when_every_check_passes(tmp_path, ready):
    report = P.preflight(1, manager=_manager(tmp_path, _pilot_spec()))
    assert report["ok"] is True and report["exit_code"] == 0 and report["codes"] == []
    assert report["runner_ready"] is True and report["running_job"] is None and report["groups"] == 1
    _strict_loads(P.dumps(report))


def _corrupt_job(manager, name="20260101T000000-bad000"):
    folder = manager.jobs_dir / name
    folder.mkdir()
    (folder / "job.json").write_text("{corrupt", encoding="utf-8")
    return folder


def test_the_preflight_precedence_is_the_stable_windows_order():
    assert [P.PREFLIGHT_CODES[code] for code in P.PREFLIGHT_PRECEDENCE] == [10, 18, 21, 24, 22, 20, 25, 19, 23]


def test_preflight_reports_every_code_and_exits_with_the_first_by_precedence(tmp_path, monkeypatch, ready):
    manager = _manager(tmp_path, _pilot_spec(30))
    running = manager.start(P.PILOT_KEY, {"groups": 1})
    bad = _corrupt_job(manager)
    snapshot = {**_verified_source(), "mode": "package-snapshot", "manifest_sha256": "0" * 64}
    monkeypatch.setattr(P, "engine", lambda **k: {**_capable_engine(), "id": "native-windows",
                                                  "pilot_capable": False})
    monkeypatch.setattr(P, "find_spec", lambda name: None)
    monkeypatch.setattr(P, "source_identity", lambda *a, **k: {**_verified_source(), "verified": False,
                                                                "problems": ["governed files modified: x"]})
    monkeypatch.setattr(P, "_disk_free_gib", lambda path: 0.5)
    state = {"groups": 3}
    steps = [
        (10, None),
        (21, lambda: manager.cancel(running)),
        (24, lambda: monkeypatch.setattr(P, "engine", _capable_engine)),
        (22, lambda: state.update(groups=1)),
        (20, lambda: monkeypatch.setattr(P, "find_spec", lambda name: object())),
        (25, lambda: monkeypatch.setattr(P, "source_identity", lambda *a, **k: dict(snapshot))),
        (19, lambda: monkeypatch.setattr(P, "source_identity", _verified_source)),
        (23, lambda: bad.rename(tmp_path / "moved-aside")),
        (0, lambda: monkeypatch.setattr(P, "_disk_free_gib", lambda path: 100.0)),
    ]
    try:
        for expected, fix in steps:
            if fix is not None:
                fix()
            report = P.preflight(state["groups"], manager=manager)
            assert report["exit_code"] == expected and report["ok"] is (expected == 0), report["codes"]
            assert report["codes"] == [c for c in P.PREFLIGHT_PRECEDENCE if c in report["codes"]]
            assert len(report["reasons"]) == len(report["codes"])
            if expected == 10:
                assert report["codes"] == ["PILOT_ALREADY_RUNNING", "PLATFORM_NOT_POSIX", "GROUPS_REFUSED",
                                           "DEPENDENCIES_MISSING", "SOURCE_NOT_VERIFIED", "JOB_RECORD_UNREADABLE",
                                           "DISK_INSUFFICIENT"]
                assert report["running_job"] == running and report["running_job_key"] == P.PILOT_KEY
                assert report["unreadable_job_dirs"] == [str(bad)]
            else:
                assert report["running_job"] is None and report["running_job_key"] is None
    finally:
        manager.cancel(running)


def test_another_running_job_is_reported_as_18_with_its_id_and_key(tmp_path, ready):
    manager = _manager(tmp_path, _pilot_spec(), _quick_spec("other", 30))
    other = manager.start("other")
    try:
        report = P.preflight(1, manager=manager)
        assert report["exit_code"] == 18 and report["codes"] == ["OTHER_JOB_RUNNING"]
        assert report["running_job"] == other and report["running_job_key"] == "other"
        assert other in report["reasons"][0]
    finally:
        manager.cancel(other)


def test_a_verified_snapshot_source_is_refused_as_not_git(tmp_path, monkeypatch, ready):
    monkeypatch.setattr(P, "source_identity", lambda *a, **k: {**_verified_source(), "mode": "package-snapshot"})
    report = P.preflight(1, manager=_manager(tmp_path, _pilot_spec()))
    assert report["exit_code"] == 25 and report["codes"] == ["SOURCE_NOT_GIT"] and report["source"]["verified"]
    assert "Git" in report["reasons"][0]


def test_a_real_verified_snapshot_tree_is_refused_as_not_git(tmp_path, monkeypatch, snapshot, ready):
    root, digest = snapshot
    monkeypatch.setattr(P, "REPO_ROOT", root)
    monkeypatch.setattr(P, "source_identity", ORIGINAL_SOURCE_IDENTITY)
    report = P.preflight(1, COMMIT, digest, manager=_manager(tmp_path, _pilot_spec()))
    assert report["source"]["mode"] == "package-snapshot" and report["source"]["verified"] is True
    assert report["exit_code"] == 25 and report["codes"] == ["SOURCE_NOT_GIT"]


def test_an_unreadable_job_record_blocks_preflight_with_19_and_names_the_folder(tmp_path, ready):
    manager = _manager(tmp_path, _pilot_spec())
    bad = _corrupt_job(manager)
    report = P.preflight(1, manager=manager)
    assert report["exit_code"] == 19 and report["codes"] == ["JOB_RECORD_UNREADABLE"]
    assert str(bad) in report["reasons"][0] and report["unreadable_job_dirs"] == [str(bad)]
    lines = []
    assert P.run_pilot(1, manager=manager, out=lines.append) == 19
    assert [p.name for p in manager.jobs_dir.iterdir()] == [bad.name]
    assert (bad / "job.json").read_text(encoding="utf-8") == "{corrupt"


def test_the_real_registry_on_a_non_posix_platform_is_refused_as_platform_not_groups(tmp_path, monkeypatch, ready):
    monkeypatch.setattr(C, "current_platform_is_posix", lambda: False)
    manager = J.JobManager(tmp_path / "home")
    report = P.preflight(1, manager=manager)
    assert report["codes"] == ["PLATFORM_NOT_POSIX"] and report["exit_code"] == 21
    assert "POSIX" in report["reasons"][0]


def test_preflight_minimum_free_space_is_configurable(tmp_path, monkeypatch, ready):
    monkeypatch.setattr(P, "_disk_free_gib", lambda path: 4.0)
    manager = _manager(tmp_path, _pilot_spec())
    assert P.preflight(1, manager=manager)["exit_code"] == 23
    assert P.preflight(1, manager=manager, min_free_gib=3.0)["exit_code"] == 0


# ---- the supervisor --------------------------------------------------------------------------------------

def _job_id(lines):
    found = [line.split("=", 1)[1] for line in lines if line.startswith("JOB_ID=")]
    assert found, lines
    return found[0]


def _pilot_record(manager, job_id):
    text = (manager.jobs_dir / job_id / "pilot.json").read_text(encoding="utf-8")
    assert text.isascii()
    return _strict_loads(text)


def _job_record(manager, job_id):
    return json.loads((manager.jobs_dir / job_id / "job.json").read_text(encoding="utf-8"))


def test_a_successful_pilot_exits_0_and_writes_a_complete_pilot_record(tmp_path, ready):
    manager = _manager(tmp_path, _pilot_spec(0.3))
    lines = []
    assert P.run_pilot(1, manager=manager, poll_s=0.1, out=lines.append) == 0
    assert lines[0].startswith("JOB_ID=")
    job_id = _job_id(lines)
    record = _pilot_record(manager, job_id)
    job = _job_record(manager, job_id)
    assert record["schema"] == P.PILOT_SCHEMA == "GEO-workbench-pilot-record/1"
    assert record["job_id"] == job_id and record["state"] == job["state"] == J.SUCCEEDED
    assert record["returncode"] == 0 and record["groups"] == 1
    assert record["roles"] == ["train", "val-select", "val-calib"] and record["argv"] == job["argv"]
    assert record["started_at"] == job["started_at"] and record["finished_at"]
    assert record["engine"]["id"] == "linux" and record["source"]["verified"] is True
    assert set(record["python"]) == {"version", "executable", "platform"}
    job_dir = manager.jobs_dir / job_id
    assert record["outputs"] == {"exercise/exercise.json": _sha256(job_dir / "exercise" / "exercise.json"),
                                 "exercise/freeze.json": _sha256(job_dir / "exercise" / "freeze.json")}
    assert "boundary" not in record
    assert record["requested_boundary"] == {"scope": "BOUNDED_DEVELOPMENT", "cpu_only": True, "heldout_reads": 0,
                                            "production_authorized": False, "benchmark_complete": False}
    assert record["observed_boundary"] == {"schema": C.EXERCISE_SCHEMA, "scope": "BOUNDED_DEVELOPMENT",
                                           "gpu_exercised": False, "heldout_reads": 0,
                                           "production_authorized": False, "benchmark_complete": False}
    assert record["boundary_check"] == {"ok": True, "reason": "exercise.json matches the bounded-development boundary"}
    assert "not a recognition-performance result" in record["note"]
    assert "not the 21,350-observation benchmark" in record["note"]
    assert record["verified"] is True
    latest = P.latest_pilot(manager)
    summary = P.pilot_status_dict(latest)
    assert summary["job_id"] == job_id and summary["verified"] is True and summary["stage"] == "complete"
    assert summary["report_path"] and summary["pilot_record_path"]
    _strict_loads(P.dumps(summary))


def test_a_two_group_pilot_records_its_groups(tmp_path, ready):
    manager = _manager(tmp_path, _pilot_spec(0.1))
    lines = []
    assert P.run_pilot(2, manager=manager, poll_s=0.1, out=lines.append) == 0
    assert _pilot_record(manager, _job_id(lines))["groups"] == 2


def test_a_failing_pilot_exits_30_and_records_failed(tmp_path, ready):
    manager = _manager(tmp_path, _pilot_spec(0.1, mode="fail"))
    lines = []
    assert P.run_pilot(1, manager=manager, poll_s=0.1, out=lines.append) == 30
    job_id = _job_id(lines)
    record = _pilot_record(manager, job_id)
    assert record["state"] == _job_record(manager, job_id)["state"] == J.FAILED
    assert record["returncode"] == 5 and record["verified"] is False
    assert record["outputs"]["exercise/exercise.json"] is None


def test_the_pilot_record_reports_the_observed_boundary_not_the_requested_one(tmp_path, ready):
    manager = _manager(tmp_path, _pilot_spec(0.1, mode="breach"))
    lines = []
    assert P.run_pilot(1, manager=manager, poll_s=0.1, out=lines.append) == 30
    record = _pilot_record(manager, _job_id(lines))
    assert record["state"] == J.FAILED and record["verified"] is False
    assert record["requested_boundary"]["heldout_reads"] == 0
    assert record["observed_boundary"]["heldout_reads"] == 3
    assert record["observed_boundary"]["gpu_exercised"] is None  # NaN in the report is not strict JSON
    assert record["boundary_check"]["ok"] is False
    reason = record["boundary_check"]["reason"]
    assert "gpu_exercised" in reason and "heldout_reads" in reason


def test_the_observed_boundary_is_null_when_the_report_is_missing_or_unreadable(tmp_path, ready):
    for mode, why in (("fail", "was not written"), ("corrupt", "not readable JSON")):
        manager = _manager(tmp_path / mode, _pilot_spec(0.1, mode=mode))
        lines = []
        assert P.run_pilot(1, manager=manager, poll_s=0.1, out=lines.append) == 30
        record = _pilot_record(manager, _job_id(lines))
        assert record["observed_boundary"] == {name: None for name in P.OBSERVED_BOUNDARY_FIELDS}, mode
        assert record["boundary_check"]["ok"] is False and why in record["boundary_check"]["reason"]


def test_a_corrupt_exercise_report_is_not_success_even_with_exit_status_0(tmp_path, ready):
    manager = _manager(tmp_path, _pilot_spec(0.1, mode="corrupt"))
    lines = []
    assert P.run_pilot(1, manager=manager, poll_s=0.1, out=lines.append) == 30
    job_id = _job_id(lines)
    record = _pilot_record(manager, job_id)
    assert record["state"] == J.FAILED and record["returncode"] == 0 and record["verified"] is False
    assert "not readable JSON" in record["reason"]
    assert P.pilot_status_dict(manager.status(job_id))["verified"] is False


def test_a_job_record_that_becomes_unreadable_exits_34_and_is_not_rewritten(tmp_path, ready):
    manager = _manager(tmp_path, _pilot_spec(0.6, mode="corrupt-record"))
    lines = []
    assert P.run_pilot(1, manager=manager, poll_s=0.1, out=lines.append) == 34
    job_id = _job_id(lines)
    assert (manager.jobs_dir / job_id / "job.json").read_text() == "{corrupt"
    record = _pilot_record(manager, job_id)
    assert record["state"] == J.RECORD_UNREADABLE and record["verified"] is False
    assert manager.owned_process(job_id).poll() is not None, "the supervisor waited for its process"


def test_an_unreadable_record_does_not_lift_the_timeout_of_the_owned_process(tmp_path, ready):
    manager = _manager(tmp_path, _pilot_spec(120, mode="corrupt-record", timeout_s=3))
    lines = []
    began = time.monotonic()
    assert P.run_pilot(1, manager=manager, poll_s=0.1, out=lines.append) == 34
    assert time.monotonic() - began < 60
    job_id = _job_id(lines)
    assert manager.owned_process(job_id).poll() is not None, "the tree was stopped at the deadline"
    assert any(line.startswith("TIMEOUT") for line in lines)
    assert (manager.jobs_dir / job_id / "job.json").read_text() == "{corrupt"
    assert _pilot_record(manager, job_id)["returncode"] is not None


def test_a_job_record_that_disappears_still_waits_for_the_owned_process_until_its_deadline(tmp_path, ready):
    manager = _manager(tmp_path, _pilot_spec(120, mode="delete-record", timeout_s=3))
    lines = []
    began = time.monotonic()
    assert P.run_pilot(1, manager=manager, poll_s=0.1, out=lines.append) == 34
    assert time.monotonic() - began < 60
    job_id = _job_id(lines)
    assert manager.owned_process(job_id).poll() is not None, "the supervisor did not abandon its process"
    assert any("disappeared" in line for line in lines)
    record = _pilot_record(manager, job_id)
    assert record["state"] == J.RECORD_UNREADABLE and record["verified"] is False


def test_a_job_record_that_disappears_is_waited_for_until_the_process_exits(tmp_path, ready):
    manager = _manager(tmp_path, _pilot_spec(1.0, mode="delete-record"))
    lines = []
    assert P.run_pilot(1, manager=manager, poll_s=0.1, out=lines.append) == 34
    proc = manager.owned_process(_job_id(lines))
    assert proc.poll() == 0 and not any(line.startswith("TIMEOUT") for line in lines)


def test_a_second_run_while_a_pilot_runs_exits_10_and_names_the_existing_job(tmp_path, ready):
    """W-04: no second job; the existing job id is printed."""
    manager = _manager(tmp_path, _pilot_spec(30))
    first = manager.start(P.PILOT_KEY, {"groups": 1})
    try:
        lines = []
        assert P.run_pilot(1, manager=manager, poll_s=0.1, out=lines.append) == 10
        assert f"JOB_ID={first}" in lines
        assert [p.name for p in manager.jobs_dir.iterdir()] == [first]
    finally:
        manager.cancel(first)


def test_a_run_while_another_command_runs_exits_18_names_that_job_and_starts_nothing(tmp_path, ready):
    manager = _manager(tmp_path, _pilot_spec(), _quick_spec("other", 30))
    other = manager.start("other")
    try:
        lines = []
        assert P.run_pilot(1, manager=manager, poll_s=0.1, out=lines.append) == 18
        assert f"JOB_ID={other}" in lines and any("OTHER_JOB_RUNNING" in line for line in lines)
        assert [p.name for p in manager.jobs_dir.iterdir()] == [other]
    finally:
        manager.cancel(other)


def _passing_preflight(*args, **kwargs):
    return {"ok": True, "exit_code": 0, "codes": [], "reasons": [], "running_job": None, "running_job_key": None,
            "source": _verified_source(), "engine": _capable_engine()}


@pytest.mark.parametrize("key,expected", [("other", 18), (P.PILOT_KEY, 10)])
def test_a_job_started_between_preflight_and_start_is_named_with_its_own_code(tmp_path, monkeypatch, ready,
                                                                               key, expected):
    spec = _pilot_spec(30) if key == P.PILOT_KEY else _quick_spec(key, 30)
    manager = _manager(tmp_path, spec) if key == P.PILOT_KEY else _manager(tmp_path, _pilot_spec(), spec)
    first = manager.start(key, {"groups": 1} if key == P.PILOT_KEY else None)
    monkeypatch.setattr(P, "preflight", _passing_preflight)
    try:
        lines = []
        assert P.run_pilot(1, manager=manager, poll_s=0.1, out=lines.append) == expected
        assert f"JOB_ID={first}" in lines and any(line.startswith("ACTIVE_JOB") for line in lines)
        assert [p.name for p in manager.jobs_dir.iterdir()] == [first]
    finally:
        manager.cancel(first)


def test_an_unreadable_record_found_by_start_exits_19(tmp_path, monkeypatch, ready):
    manager = _manager(tmp_path, _pilot_spec())
    bad = _corrupt_job(manager)
    monkeypatch.setattr(P, "preflight", _passing_preflight)
    lines = []
    assert P.run_pilot(1, manager=manager, out=lines.append) == 19
    assert any(line.startswith("JOB_RECORD_UNREADABLE") and str(bad) in line for line in lines)
    assert [p.name for p in manager.jobs_dir.iterdir()] == [bad.name]


@posix_only
def test_sighup_with_a_dead_output_still_cancels_the_owned_job(tmp_path, ready):
    """The hidden wsl.exe relay dies: SIGHUP arrives and every later write raises. The job must be cancelled."""
    manager = _manager(tmp_path, _pilot_spec(30))
    lines, hung_up = [], []

    def out(line):
        if hung_up:
            raise OSError(5, "Input/output error")
        lines.append(line)
        if line.startswith("JOB_ID="):
            hung_up.append(True)
            signal.raise_signal(signal.SIGHUP)

    before = signal.getsignal(signal.SIGHUP)
    assert P.run_pilot(1, manager=manager, poll_s=0.1, out=out) == 31
    assert signal.getsignal(signal.SIGHUP) == before
    job_id = _job_id(lines)
    assert _job_record(manager, job_id)["state"] == J.CANCELLED
    assert _pilot_record(manager, job_id)["state"] == J.CANCELLED
    assert manager.owned_process(job_id).poll() is not None


def test_emit_swallows_output_errors():
    for error in (OSError(5, "EIO"), BrokenPipeError(), ValueError("I/O operation on closed file")):
        def broken(line, error=error):
            raise error
        P._emit(broken, "line")


def test_a_refused_preflight_starts_nothing(tmp_path, monkeypatch, ready):
    monkeypatch.setattr(P, "source_identity", lambda *a, **k: {**_verified_source(), "verified": False})
    manager = _manager(tmp_path, _pilot_spec())
    lines = []
    assert P.run_pilot(1, manager=manager, out=lines.append) == 20
    assert manager.list_jobs() == [] and any("SOURCE_NOT_VERIFIED" in line for line in lines)


# ---- cancellation ----------------------------------------------------------------------------------------

def test_cancel_pilot_stops_the_job_and_preserves_its_folder_and_log(tmp_path, ready):
    """W-05: the owned tree is stopped, the job is CANCELLED (not SUCCEEDED), evidence stays."""
    manager = _manager(tmp_path, _pilot_spec(30))
    job_id = manager.start(P.PILOT_KEY, {"groups": 1})
    job_dir = manager.jobs_dir / job_id
    assert _wait(lambda: _log_has(job_dir, "generator started"))
    pid = _job_record(manager, job_id)["pid"]
    lines = []
    assert P.cancel_pilot(manager=_manager(tmp_path, _pilot_spec(30)), out=lines.append) == 0
    assert f"CANCELLED JOB_ID={job_id}" in lines
    assert manager.status(job_id).state == J.CANCELLED and _job_record(manager, job_id)["state"] == J.CANCELLED
    assert job_dir.is_dir() and _log_has(job_dir, "generator started") and (job_dir / "exercise" / "work").is_dir()
    assert not J.process_alive(pid, None)
    assert P.cancel_pilot(manager=manager, out=lines.append) == 3
    assert P.cancel_pilot(job_id, manager=manager, out=lines.append) == 3


def test_cancel_pilot_with_nothing_running_exits_3(tmp_path):
    assert P.cancel_pilot(manager=_manager(tmp_path, _pilot_spec()), out=lambda line: None) == 3
    assert P.cancel_pilot("20260101T000000-000000", manager=_manager(tmp_path, _pilot_spec()),
                          out=lambda line: None) == 3


def test_a_cancelled_pilot_records_the_real_exit_status_of_its_process(tmp_path):
    manager = _manager(tmp_path, _pilot_spec(30))
    job_id = manager.start(P.PILOT_KEY, {"groups": 1})
    assert _wait(lambda: _log_has(manager.jobs_dir / job_id, "generator started"))
    # A non-owning canceller (the CLI) cannot know the exit status; the owner fills it in later.
    assert P.cancel_pilot(manager=_manager(tmp_path, _pilot_spec(30)), out=lambda line: None) == 0
    assert _job_record(manager, job_id)["returncode"] is None
    status = manager.status(job_id)
    assert status.state == J.CANCELLED and status.returncode is not None and status.returncode != 0
    assert _job_record(manager, job_id)["state"] == J.CANCELLED
    assert _job_record(manager, job_id)["returncode"] == manager.owned_process(job_id).returncode


def test_cancel_pilot_refuses_to_signal_a_pid_whose_start_token_differs(tmp_path):
    """Stale or recycled pid: the recorded token does not match the live process, so it is not signalled."""
    manager = _manager(tmp_path, _pilot_spec(30))
    job_id = manager.start(P.PILOT_KEY, {"groups": 1})
    proc = manager.owned_process(job_id)
    try:
        path = manager.jobs_dir / job_id / "job.json"
        record = json.loads(path.read_text())
        record["pid_start_token"] = "1"
        path.write_text(json.dumps(record))
        lines = []
        assert P.cancel_pilot(manager=_manager(tmp_path, _pilot_spec(30)), out=lines.append) == 41
        assert any(line.startswith("OWNERSHIP_UNVERIFIED") for line in lines)
        time.sleep(0.3)
        assert proc.poll() is None and J._pid_alive(proc.pid), "the process must not be signalled"
    finally:
        proc.kill()
        proc.wait(timeout=30)


SUPERVISOR = r"""
import sys
sys.path.insert(0, sys.argv[1])
import test_geo_pilot as T
T.apply_ready(setattr)
manager = T._manager_at(sys.argv[2], T._pilot_spec(30))
sys.exit(T.P.run_pilot(1, manager=manager, poll_s=0.1))
"""


@posix_only
def test_sigterm_to_the_supervisor_cancels_its_job_and_exits_31(tmp_path):
    home = tmp_path / "home"
    proc = subprocess.Popen([sys.executable, "-c", SUPERVISOR, str(ROOT / "tests"), str(home)],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, cwd=str(tmp_path))
    try:
        first = proc.stdout.readline().strip()
        assert first.startswith("JOB_ID="), first
        job_id = first.split("=", 1)[1]
        job_dir = home / "jobs" / job_id
        assert _wait(lambda: _log_has(job_dir, "generator started"))
        pid = json.loads((job_dir / "job.json").read_text())["pid"]
        proc.send_signal(signal.SIGTERM)
        assert proc.wait(timeout=60) == 31
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=30)
    job = json.loads((job_dir / "job.json").read_text())
    pilot = json.loads((job_dir / "pilot.json").read_text())
    assert job["state"] == pilot["state"] == J.CANCELLED
    assert not J.process_alive(pid, None) and _log_has(job_dir, "generator started")


# ---- restart recovery (W-08) and unreadable records ------------------------------------------------------

def _orphan(tmp_path, mode="ok", owner=None):
    """A pilot whose process ended while its record still says running and its owner is gone."""
    manager = _manager(tmp_path, _pilot_spec(0.1, mode=mode))
    job_id = manager.start(P.PILOT_KEY, {"groups": 1})
    proc = manager.owned_process(job_id)
    proc.wait(timeout=30)
    path = manager.jobs_dir / job_id / "job.json"
    record = json.loads(path.read_text())
    owner_pid, owner_token = owner if owner is not None else (_dead_pid(), "1")
    record.update({"owner_pid": owner_pid, "owner_start_token": owner_token, "state": J.RUNNING,
                   "returncode": None})
    path.write_text(json.dumps(record))
    return job_id


def test_a_job_left_running_by_a_dead_owner_settles_as_finished_unrecorded_never_succeeded(tmp_path):
    job_id = _orphan(tmp_path)
    status = _manager(tmp_path, _pilot_spec()).status(job_id)
    assert status.state == J.FINISHED_UNRECORDED and status.returncode is None
    assert P.pilot_status_dict(status)["verified"] is False


def test_a_job_left_running_by_a_dead_owner_without_valid_outputs_settles_as_failed(tmp_path):
    job_id = _orphan(tmp_path, mode="corrupt")
    assert _manager(tmp_path, _pilot_spec()).status(job_id).state == J.FAILED


def test_an_owner_pid_recycled_by_another_process_does_not_keep_the_job_running(tmp_path):
    stranger = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:
        job_id = _orphan(tmp_path, owner=(stranger.pid, "1"))
        assert _manager(tmp_path, _pilot_spec()).status(job_id).state == J.FINISHED_UNRECORDED
        assert stranger.poll() is None
    finally:
        stranger.kill()
        stranger.wait(timeout=30)


def test_a_corrupt_job_record_is_record_unreadable_and_listing_does_not_crash(tmp_path):
    manager = _manager(tmp_path, _pilot_spec())
    bad = manager.jobs_dir / "20260101T000000-bad000"
    bad.mkdir()
    (bad / "job.json").write_text("{corrupt", encoding="utf-8")
    jobs = manager.list_jobs()
    assert [(j.job_id, j.state) for j in jobs] == [(bad.name, J.RECORD_UNREADABLE)]
    assert P.latest_pilot(manager) is None  # its key cannot be read, so it is not presented as a pilot
    summary = P.pilot_status_dict(jobs[0])
    assert summary["state"] == J.RECORD_UNREADABLE and summary["verified"] is False
    assert (bad / "job.json").read_text() == "{corrupt"


# ---- command safety through the real registry (W-09); nothing is executed ---------------------------------

@pytest.mark.parametrize("extra", [["--production"], ["--device", "cuda"], ["--cuda"], ["--gpu"], ["--loko"],
                                   ["--roles", "test"], ["--roles", "test-matched"], ["--test-matched"],
                                   ["--execute"], ["--authorize"], ["--stage", "matched"]])
def test_forbidden_flags_appended_to_the_real_pilot_argv_are_refused(tmp_path, monkeypatch, extra):
    monkeypatch.setattr(C, "current_platform_is_posix", lambda: True)
    spec = C.REGISTRY[P.PILOT_KEY]
    argv = C.build_argv(P.PILOT_KEY, {"groups": 1}, tmp_path / "job")
    assert argv[1:3] == ["scripts/b2_real_execution.py", "--out"] and argv[-2:] == ["--groups", "1"]
    with pytest.raises(C.CommandRefused):
        C.assert_safe_argv(argv + extra, spec)


@pytest.mark.parametrize("groups", [3, 0, -1, "1", True, 1.0, None])
def test_the_real_pilot_refuses_groups_outside_one_or_two(tmp_path, monkeypatch, groups):
    monkeypatch.setattr(C, "current_platform_is_posix", lambda: True)
    with pytest.raises(C.CommandRefused):
        C.validate(P.PILOT_KEY, {"groups": groups})
    with pytest.raises(C.CommandRefused):
        C.build_argv(P.PILOT_KEY, {"groups": groups}, tmp_path / "job")


def test_the_real_registry_manager_refuses_groups_3_before_creating_a_job(tmp_path, monkeypatch, ready):
    monkeypatch.setattr(C, "current_platform_is_posix", lambda: True)
    manager = J.JobManager(tmp_path / "home")
    with pytest.raises(C.CommandRefused):
        manager.start(P.PILOT_KEY, {"groups": 3})
    lines = []
    assert P.run_pilot(3, manager=manager, out=lines.append) == 24
    assert manager.list_jobs() == []


def test_the_pilot_key_and_roles_are_the_bounded_development_ones():
    spec = C.REGISTRY[P.PILOT_KEY]
    assert spec.scope == C.SCOPE_DEVELOPMENT and spec.requires_posix is True and spec.timeout_s == 5400
    assert spec.params[0].choices == (1, 2)
    assert P.DEVELOPMENT_ROLES == ("train", "val-select", "val-calib")
    assert P.BOUNDARY["benchmark_complete"] is False and P.BOUNDARY["production_authorized"] is False


# ---- spawning the supervisor -----------------------------------------------------------------------------

def test_spawn_supervisor_refuses_an_engine_that_cannot_run_the_pilot(tmp_path, monkeypatch):
    monkeypatch.setenv("GEO_DASHBOARD_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(P, "engine", lambda **k: {**_capable_engine(), "id": "native-windows",
                                                  "pilot_capable": False})
    with pytest.raises(C.CommandRefused):
        P.spawn_supervisor(1)
    assert not (tmp_path / "home" / "workbench").exists()


def test_spawn_supervisor_starts_the_fixed_cli_detached_without_a_shell(tmp_path, monkeypatch):
    monkeypatch.setenv("GEO_DASHBOARD_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(P, "engine", _capable_engine)
    monkeypatch.setattr(C, "current_platform_is_posix", lambda: True)
    seen = {}

    def fake_popen(argv, **kwargs):
        seen.update(kwargs, argv=argv, log=kwargs["stdout"].name)
        return "proc"

    monkeypatch.setattr(P.subprocess, "Popen", fake_popen)
    assert P.spawn_supervisor(2, python="py") == "proc"
    assert seen["argv"] == ["py", str(ROOT / "dashboard" / "geo_pilot.py"), "run", "--groups", "2"]
    assert seen["shell"] is False and seen["cwd"] == str(ROOT) and seen["stdin"] is subprocess.DEVNULL
    assert Path(seen["log"]).parent == tmp_path / "home" / "workbench"
    assert Path(seen["log"]).name.startswith("supervisor-")
    with pytest.raises(C.CommandRefused):
        P.spawn_supervisor(3)


def test_spawn_supervisor_forwards_the_expected_package_identity(tmp_path, monkeypatch):
    monkeypatch.setenv("GEO_DASHBOARD_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(P, "engine", _capable_engine)
    monkeypatch.setattr(C, "current_platform_is_posix", lambda: True)
    seen = []
    monkeypatch.setattr(P.subprocess, "Popen", lambda argv, **kwargs: seen.append(argv) or "proc")
    P.spawn_supervisor(1, python="py", expect_commit=COMMIT, expect_manifest_sha256="b" * 64)
    assert seen[-1][2:] == ["run", "--groups", "1", "--expect-commit", COMMIT, "--expect-manifest-sha256", "b" * 64]
    P.spawn_supervisor(1, python="py", expect_commit=COMMIT)
    assert seen[-1][-2:] == ["--expect-commit", COMMIT] and "--expect-manifest-sha256" not in seen[-1]
    for bad in ("--production", "a" * 65, "xyz", ""):
        with pytest.raises(C.CommandRefused):
            P.spawn_supervisor(1, python="py", expect_commit=bad)
    assert len(seen) == 2


# ---- the UI service --------------------------------------------------------------------------------------

def _free_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


SERVE = r"""
import sys
sys.path.insert(0, sys.argv[1])
from geodash import pilot as P
P._streamlit_argv = lambda port, python: [python, "-c", "import time; time.sleep(120)"]
sys.exit(P.serve(int(sys.argv[2]), keepalive_poll_s=0.2))
"""


def _start_serve(tmp_path, port):
    env = {**os.environ, "GEO_DASHBOARD_HOME": str(tmp_path / "home")}
    return subprocess.Popen([sys.executable, "-c", SERVE, str(ROOT / "dashboard"), str(port)], env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)


@posix_only
def test_serve_records_itself_refuses_a_second_instance_and_stops_on_ui_stop(tmp_path, monkeypatch):
    monkeypatch.setenv("GEO_DASHBOARD_HOME", str(tmp_path / "home"))
    port = _free_port()
    server = _start_serve(tmp_path, port)
    try:
        assert _wait(lambda: P.ui_status()["running"]), server.stdout.read() if server.poll() is not None else ""
        status = P.ui_status()
        assert status["state"] == "serving" and status["port"] == port and status["pid"] == server.pid
        record = json.loads((tmp_path / "home" / "workbench" / "ui.json").read_text())
        assert record["start_token"] == J.process_start_token(server.pid) and record["engine"] == P.engine()["id"]
        child = record["child_pid"]
        assert J._pid_alive(child)
        lines = []
        assert P.serve(port + 1, out=lines.append) == 11 and lines == [f"ALREADY_RUNNING port={port}"]
        assert P.ui_stop(out=lines.append) == 0
        assert server.wait(timeout=60) == 0
    finally:
        if server.poll() is None:
            server.kill()
            server.wait(timeout=30)
    assert not (tmp_path / "home" / "workbench" / "ui.json").exists()
    assert _wait(lambda: not J._pid_alive(child))
    assert P.ui_stop(out=lambda line: None) == 3 and P.ui_status()["state"] == "none"


@posix_only
def test_serve_stays_alive_while_a_pilot_runs_after_the_ui_is_stopped(tmp_path, monkeypatch):
    monkeypatch.setenv("GEO_DASHBOARD_HOME", str(tmp_path / "home"))
    manager = _manager(tmp_path, _pilot_spec(30))
    job_id = manager.start(P.PILOT_KEY, {"groups": 1})
    server = _start_serve(tmp_path, _free_port())
    try:
        assert _wait(lambda: P.ui_status()["running"])
        assert P.ui_stop(out=lambda line: None) == 0
        assert _wait(lambda: P.ui_status()["state"] == "keepalive")
        assert server.poll() is None and P.ui_status()["running"] is False
        manager.cancel(job_id)
        assert server.wait(timeout=60) == 0
    finally:
        if server.poll() is None:
            server.kill()
            server.wait(timeout=30)
        manager.cancel(job_id)
    assert P.ui_status()["state"] == "none"


def test_serve_refuses_a_busy_port(tmp_path, monkeypatch):
    monkeypatch.setenv("GEO_DASHBOARD_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(P, "_streamlit_argv", lambda port, python: pytest.fail("must not start the UI"))
    with socket.socket() as holder:
        holder.bind(("127.0.0.1", 0))
        holder.listen(1)
        lines = []
        assert P.serve(holder.getsockname()[1], out=lines.append) == 12
        assert lines[0].startswith("PORT_BUSY")
    assert not (tmp_path / "home" / "workbench" / "ui.json").exists()


class _FakeChild:
    """Stands for the Streamlit child; it exits at its first poll, after capturing ui.json."""
    pid = 999999
    returncode = 0

    def __init__(self, argv, **kwargs):
        self.argv, self.kwargs = argv, kwargs
        self.ui_record = None
        _FakeChild.last = self

    def poll(self):
        if self.ui_record is None:
            self.ui_record = json.loads(P._ui_record_path().read_text(encoding="utf-8"))
        return 0


def test_serve_exports_the_expected_identity_to_the_ui_and_records_it(tmp_path, monkeypatch):
    monkeypatch.setenv("GEO_DASHBOARD_HOME", str(tmp_path / "home"))
    monkeypatch.setenv(P.ENV_EXPECT_MANIFEST, "stale-from-the-parent")
    monkeypatch.setattr(P.subprocess, "Popen", _FakeChild)
    lines = []
    code = P.serve(_free_port(), manager=_manager(tmp_path, _pilot_spec()), out=lines.append, expect_commit=COMMIT)
    assert code == 1 and lines[-1] == "STOPPED"
    child = _FakeChild.last
    assert child.kwargs["env"][P.ENV_EXPECT_COMMIT] == COMMIT
    assert P.ENV_EXPECT_MANIFEST not in child.kwargs["env"], "an inherited expectation must not leak into the UI"
    assert child.kwargs["shell"] is False and child.kwargs["env"]["PYTHONUTF8"] == "1"
    assert child.ui_record["expect_commit"] == COMMIT and child.ui_record["expect_manifest_sha256"] is None
    P.serve(_free_port(), manager=_manager(tmp_path, _pilot_spec()), out=lines.append, expect_commit=COMMIT,
            expect_manifest_sha256="c" * 64)
    assert _FakeChild.last.kwargs["env"][P.ENV_EXPECT_MANIFEST] == "c" * 64
    assert _FakeChild.last.ui_record["expect_manifest_sha256"] == "c" * 64


def test_serve_refuses_a_malformed_expected_identity(tmp_path, monkeypatch):
    monkeypatch.setenv("GEO_DASHBOARD_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(P.subprocess, "Popen", lambda *a, **k: pytest.fail("must not start the UI"))
    lines = []
    assert P.serve(_free_port(), out=lines.append, expect_commit="--server.address=0.0.0.0") == 40
    assert lines[0].startswith("REFUSED")


def test_the_ui_reads_the_expected_identity_from_its_environment():
    assert P.expected_identity({}) == (None, None)
    assert P.expected_identity({P.ENV_EXPECT_COMMIT: COMMIT, P.ENV_EXPECT_MANIFEST: ""}) == (COMMIT, None)
    assert P.expected_identity({P.ENV_EXPECT_COMMIT: COMMIT, P.ENV_EXPECT_MANIFEST: "d" * 64}) == (COMMIT, "d" * 64)


def _serving_record(tmp_path, pid):
    folder = tmp_path / "home" / "workbench"
    folder.mkdir(parents=True)
    (folder / "ui.json").write_text(json.dumps({"pid": pid, "start_token": J.process_start_token(pid), "port": 8531,
                                                "engine": "wsl2", "started_at": "", "state": "serving"}))


def test_ui_stop_reports_42_when_the_ui_still_serves_after_the_wait(tmp_path, monkeypatch):
    monkeypatch.setenv("GEO_DASHBOARD_HOME", str(tmp_path / "home"))
    stranger = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:
        _serving_record(tmp_path, stranger.pid)
        assert P.ui_status()["state"] == "serving"
        signalled, real_kill = [], os.kill

        def record_stop(pid, sig):
            if sig == 0:
                return real_kill(pid, sig)
            signalled.append(pid)

        monkeypatch.setattr(P.os, "kill", record_stop)
        monkeypatch.setattr(P, "terminate_tree", lambda pid, proc, grace: signalled.append(pid))
        lines = []
        assert P.ui_stop(wait_s=0.3, out=lines.append) == 42
        assert signalled == [stranger.pid] and lines[-1].startswith("STOP_TIMEOUT")
        assert (tmp_path / "home" / "workbench" / "ui.json").is_file()
    finally:
        monkeypatch.undo()
        stranger.kill()
        stranger.wait(timeout=30)


def test_ui_stop_reports_3_when_the_serve_process_ends_before_the_signal(tmp_path, monkeypatch):
    monkeypatch.setenv("GEO_DASHBOARD_HOME", str(tmp_path / "home"))
    stranger = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:
        _serving_record(tmp_path, stranger.pid)
        assert P.ui_status()["state"] == "serving"
        real_kill = os.kill
        monkeypatch.setattr(P, "ui_status", lambda: {"state": "serving", "pid": stranger.pid, "running": True})
        monkeypatch.setattr(P, "IS_POSIX", True)

        def gone(pid, sig):
            if sig == 0:
                return real_kill(pid, sig)
            raise ProcessLookupError(pid)

        monkeypatch.setattr(P.os, "kill", gone)
        lines = []
        assert P.ui_stop(wait_s=0.3, out=lines.append) == 3
        assert lines[-1].startswith("NO_UI_RUNNING") and "ended before" in lines[-1]
    finally:
        monkeypatch.undo()
        stranger.kill()
        stranger.wait(timeout=30)


def test_ui_stop_refuses_to_signal_a_recorded_pid_with_another_start_token(tmp_path, monkeypatch):
    monkeypatch.setenv("GEO_DASHBOARD_HOME", str(tmp_path / "home"))
    stranger = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:
        folder = tmp_path / "home" / "workbench"
        folder.mkdir(parents=True)
        (folder / "ui.json").write_text(json.dumps({"pid": stranger.pid, "start_token": "1", "port": 8531,
                                                    "engine": "wsl2", "started_at": "", "state": "serving"}))
        assert P.ui_status()["state"] == "token_mismatch" and P.ui_status()["running"] is False
        assert P.ui_stop(out=lambda line: None) == 41
        time.sleep(0.3)
        assert stranger.poll() is None
    finally:
        stranger.kill()
        stranger.wait(timeout=30)


def test_ui_stop_removes_a_stale_record_of_a_dead_process(tmp_path, monkeypatch):
    monkeypatch.setenv("GEO_DASHBOARD_HOME", str(tmp_path / "home"))
    folder = tmp_path / "home" / "workbench"
    folder.mkdir(parents=True)
    (folder / "ui.json").write_text(json.dumps({"pid": _dead_pid(), "start_token": "1", "port": 8531}))
    assert P.ui_status()["state"] == "stale"
    assert P.ui_stop(out=lambda line: None) == 3 and not (folder / "ui.json").exists()


def test_the_streamlit_argv_binds_loopback_only():
    argv = P._streamlit_argv(8531, "py")
    assert argv[:4] == ["py", "-m", "streamlit", "run"] and argv[4] == str(ROOT / "dashboard" / "app.py")
    assert argv[argv.index("--server.address") + 1] == "127.0.0.1"
    assert argv[argv.index("--server.port") + 1] == "8531" and argv[argv.index("--server.headless") + 1] == "true"


# ---- home-page states ------------------------------------------------------------------------------------

LINUX = {"id": "linux", "label": "Linux", "label_tr": "Linux", "pilot_capable": True}
NATIVE = {"id": "native-windows", "label": "native Windows", "label_tr": "Yerel Windows", "pilot_capable": False}


def _states(latest=None, engine=LINUX, verified=True, rows=None, gpu=False):
    return P.workbench_states(engine=engine, source={"verified": verified}, latest=latest,
                              gate_rows=repo_status.gate_rows() if rows is None else rows, gpu_present=gpu)


def test_the_home_states_of_an_idle_capable_workbench():
    assert _states() == ["APP_READY", "BENCHMARK_NOT_RUN", "COMPUTE_GATES_CLOSED", "HOST_NOT_QUALIFIED"]


def test_the_pilot_is_unavailable_on_native_windows_or_with_an_unverified_source():
    assert "PILOT_UNAVAILABLE" in _states(engine=NATIVE)
    assert "PILOT_UNAVAILABLE" in _states(verified=False)


def test_the_pilot_is_unavailable_from_a_verified_package_snapshot():
    states = P.workbench_states(engine=LINUX, source={"verified": True, "mode": "package-snapshot"}, latest=None,
                                gate_rows=repo_status.gate_rows(), gpu_present=False)
    assert "PILOT_UNAVAILABLE" in states
    assert "PILOT_UNAVAILABLE" not in P.workbench_states(engine=LINUX, source={"verified": True, "mode": "git"},
                                                         latest=None, gate_rows=[], gpu_present=False)


def test_pilot_states_follow_the_job_and_only_a_verified_success_is_complete(tmp_path):
    job_dir = tmp_path / "job"
    (job_dir / "exercise").mkdir(parents=True)
    assert "PILOT_RUNNING" in _states({"state": J.RUNNING, "job_dir": str(job_dir)})
    assert "PILOT_FAILED" in _states({"state": J.SUCCEEDED, "job_dir": str(job_dir)})  # no report: not verified
    (job_dir / "exercise" / "exercise.json").write_text(json.dumps(REPORT))
    assert "PILOT_COMPLETE" in _states({"state": J.SUCCEEDED, "job_dir": str(job_dir)})
    for state in (J.FAILED, J.CANCELLED, J.TIMED_OUT, J.FINISHED_UNRECORDED, J.RECORD_UNREADABLE):
        states = _states({"state": state, "job_dir": str(job_dir)})
        assert "PILOT_FAILED" in states and "PILOT_COMPLETE" not in states, state


def test_no_input_can_produce_a_qualified_host_or_a_completed_benchmark(tmp_path):
    open_rows = [{"gate": "g", "value": "AUTHORIZED"}, {"gate": "h", "value": True}]
    for rows in (open_rows, [], [{"gate": "g", "value": False}]):
        for gpu in (True, False):
            states = _states(rows=rows, gpu=gpu)
            assert "BENCHMARK_NOT_RUN" in states and "HOST_NOT_QUALIFIED" in states
            assert set(states) <= set(P.WORKBENCH_STATES)
            assert not [s for s in states if "QUALIFIED" in s and s != "HOST_NOT_QUALIFIED"]
    assert "COMPUTE_GATES_CLOSED" not in _states(rows=open_rows)
    assert "COMPUTE_GATES_CLOSED" in _states(rows=[])
    assert "COMPUTE_GATES_CLOSED" in _states()  # the committed gate records are closed


# ---- the command line ------------------------------------------------------------------------------------

def _cli(tmp_path, *args):
    env = {**os.environ, "GEO_DASHBOARD_HOME": str(tmp_path / "home")}
    return subprocess.run([sys.executable, str(ROOT / "dashboard" / "geo_pilot.py"), *args], cwd=str(tmp_path),
                          env=env, capture_output=True, text=True, timeout=300)


def _one_json_line(done):
    lines = done.stdout.splitlines()
    assert len(lines) == 1, done.stdout + done.stderr
    assert lines[0].isascii()
    return _strict_loads(lines[0])


def test_cli_preflight_json_prints_one_strict_ascii_line(tmp_path):
    done = _cli(tmp_path, "preflight", "--json")
    report = _one_json_line(done)
    assert done.returncode == report["exit_code"] and done.returncode in (0, 10, 18, 19, 20, 21, 22, 23, 25)
    assert set(report) >= {"ok", "exit_code", "codes", "engine", "source", "running_job", "disk_free_gib",
                           "runner_ready", "groups"}
    if os.name == "nt":
        assert report["exit_code"] == 21 and report["engine"]["id"] == "native-windows"


def test_cli_preflight_refuses_three_groups(tmp_path):
    done = _cli(tmp_path, "preflight", "--groups", "3", "--json")
    report = _one_json_line(done)
    assert "GROUPS_REFUSED" in report["codes"] and done.returncode in (10, 18, 21, 24)


def test_cli_status_cancel_and_ui_commands_exit_3_with_an_empty_run_home(tmp_path):
    done = _cli(tmp_path, "status", "--json")
    assert done.returncode == 3 and _one_json_line(done)["found"] is False
    assert _cli(tmp_path, "status").returncode == 3
    assert _cli(tmp_path, "cancel").returncode == 3
    done = _cli(tmp_path, "ui-status", "--json")
    assert done.returncode == 3 and _one_json_line(done)["running"] is False
    assert _cli(tmp_path, "ui-stop").returncode == 3


def _geo_pilot_module():
    import geo_pilot
    return geo_pilot


def test_cli_serve_passes_the_expected_identity(monkeypatch):
    seen = {}
    monkeypatch.setattr(P, "serve", lambda port, **kwargs: seen.update(kwargs, port=port) or 0)
    cli = _geo_pilot_module()
    assert cli.main(["serve", "--port", "8531", "--expect-commit", COMMIT, "--expect-manifest-sha256", "e" * 64]) == 0
    assert seen["port"] == 8531 and seen["expect_commit"] == COMMIT and seen["expect_manifest_sha256"] == "e" * 64
    assert cli.main(["serve", "--port", "8532"]) == 0
    assert seen["expect_commit"] is None and seen["expect_manifest_sha256"] is None


def test_cli_preflight_text_names_the_running_job(monkeypatch, capsys):
    report = {"ok": False, "exit_code": 23, "codes": ["DISK_INSUFFICIENT"], "reasons": ["0.1 GiB free"],
              "running_job": "20261105T000000-abc123", "running_job_key": "other", "source": _verified_source(),
              "engine": _capable_engine()}
    monkeypatch.setattr(P, "preflight", lambda *a, **k: report)
    cli = _geo_pilot_module()
    assert cli.main(["preflight"]) == 23
    assert "JOB_ID=20261105T000000-abc123" in capsys.readouterr().out.splitlines()
    assert cli.main(["preflight", "--json"]) == 23
    assert len(capsys.readouterr().out.splitlines()) == 1


def test_cli_rejects_unknown_subcommands(tmp_path):
    assert _cli(tmp_path, "production").returncode == 2
    assert _cli(tmp_path, "run", "--device", "cuda").returncode == 2


# ---- Track B isolation -----------------------------------------------------------------------------------

@pytest.mark.parametrize("relative", ["dashboard/geodash/pilot.py", "dashboard/geo_pilot.py"])
def test_the_pilot_backend_does_not_touch_the_learning_track(relative):
    source = (ROOT / relative).read_text(encoding="utf-8")
    assert "learning/" not in source and "rfml" not in source.lower()
    assert "--device" not in source and "--execute" not in source and "shell=True" not in source

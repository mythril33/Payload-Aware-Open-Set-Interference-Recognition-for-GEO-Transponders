"""WSL bootstrap (windows/wsl/geo_wsl_setup.py): verify / install / venv.

Most tests run on synthetic package trees whose SOURCE_MANIFEST.json and VERSION.json are written
by the package builder's own functions; one end-to-end test extracts a package built from the
committed HEAD. The venv tests inject the subprocess runner, so nothing is installed.
"""
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


W = _load("geo_wsl_setup", ROOT / "windows" / "wsl" / "geo_wsl_setup.py")
BW = _load("build_windows_package", ROOT / "scripts" / "build_windows_package.py")

COMMIT = "a" * 40
FILES = {
    ".gitignore": b"__pycache__/\n",
    "pyproject.toml": b"[project]\nname = 'geosim'\n",
    "README.md": b"readme\n",
    "src/geosim/__init__.py": b"VERSION = 1\n",
    "src/geoml/train.py": b"def train():\n    return 0\n",
    "scripts/b2_real_execution.py": b"print('exercise')\n",
    "configs/b2_feat.json": b"{}\n",
    "dashboard/app.py": b"print('app')\n",
    "dashboard/geo_pilot.py": b"print('pilot')\n",
    "dashboard/requirements.txt": b"streamlit==1.65.0\n",
    "windows/KURULUM.bat": b"@echo off\r\n",
    "windows/wsl/geo_wsl_setup.py": b"print('setup')\n",
}


def make_package(root: Path, files=None, source: str = W.REQUIRED_SOURCE, commit: str = COMMIT) -> Path:
    files = dict(FILES if files is None else files)
    for rel, data in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    manifest = BW.build_source_manifest(files, commit, source)
    (root / W.MANIFEST_NAME).write_bytes(manifest)
    (root / W.VERSION_NAME).write_bytes(
        BW.build_version_json("t", commit, "2026-11-05T00:00:00Z", source, manifest))
    return root


@pytest.fixture
def pkg(tmp_path):
    return make_package(tmp_path / "pkg")


def _json_line(capsys) -> dict:
    out = capsys.readouterr().out
    lines = out.splitlines()
    assert len(lines) == 1, out
    out.encode("ascii")
    return json.loads(lines[0])


def _fixed_now():
    return datetime(2026, 11, 5, 12, 0, 0, tzinfo=timezone.utc)


# ---- verify ------------------------------------------------------------------------------------------

def test_a_builder_written_tree_verifies(pkg, capsys):
    check = W.verify_tree(pkg)
    assert check["verified"] and check["problems"] == []
    assert check["commit"] == COMMIT and check["files"] == len(FILES)
    assert check["manifest_sha256"] == hashlib.sha256((pkg / W.MANIFEST_NAME).read_bytes()).hexdigest()
    assert "not a production lock" in check["limitations"]

    assert W.main(["verify", "--root", str(pkg), "--expect-commit", COMMIT,
                   "--expect-manifest-sha256", check["manifest_sha256"], "--json"]) == 0
    out = _json_line(capsys)
    assert out["exit_code"] == 0 and out["code"] == "OK" and out["verified"] is True


def test_a_tampered_listed_file_fails(pkg, capsys):
    (pkg / "src" / "geosim" / "__init__.py").write_bytes(b"VERSION = 2\n")
    assert W.main(["verify", "--root", str(pkg), "--json"]) == 20
    out = _json_line(capsys)
    assert out["code"] == "NOT_VERIFIED"
    assert out["problems"] == ["hash mismatch: src/geosim/__init__.py"]


def test_a_missing_listed_file_fails(pkg):
    (pkg / "configs" / "b2_feat.json").unlink()
    assert W.verify_tree(pkg)["problems"] == ["missing file: configs/b2_feat.json"]


@pytest.mark.parametrize("top", W.SCANNED_DIRS)
def test_an_unlisted_file_under_a_governed_dir_fails(pkg, top):
    extra = pkg / top / "sub" / "extra.py"
    extra.parent.mkdir(parents=True, exist_ok=True)
    extra.write_bytes(b"x\n")
    assert W.verify_tree(pkg)["problems"] == [f"unexpected file: {top}/sub/extra.py"]


def test_generated_bytecode_and_editable_metadata_are_ignored(pkg):
    cache = pkg / "src" / "geosim" / "__pycache__"
    cache.mkdir()
    (cache / "__init__.cpython-312.pyc").write_bytes(b"\0")
    (pkg / "dashboard" / "stray.pyc").write_bytes(b"\0")
    egg = pkg / "src" / "geosim.egg-info"
    egg.mkdir()
    (egg / "PKG-INFO").write_bytes(b"Name: geosim\n")
    (pkg / ".venv" / "bin").mkdir(parents=True)
    (pkg / ".venv" / "bin" / "python").write_bytes(b"")
    assert W.verify_tree(pkg)["verified"]


def test_unlisted_files_outside_governed_dirs_are_not_scanned(pkg):
    (pkg / "docs").mkdir()
    (pkg / "docs" / "note.md").write_bytes(b"note\n")
    assert W.verify_tree(pkg)["verified"]


def test_only_a_git_archive_head_manifest_verifies(tmp_path):
    tree = make_package(tmp_path / "wt", source="worktree-overlay")
    check = W.verify_tree(tree)
    assert not check["verified"]
    assert check["problems"] == ["manifest source is 'worktree-overlay', expected 'git archive HEAD'"]


def test_expectation_mismatches_fail(pkg):
    assert W.verify_tree(pkg, expect_commit="b" * 40)["problems"][0].startswith("commit mismatch")
    assert W.verify_tree(pkg, expect_manifest_sha256="0" * 64)["problems"][0].startswith(
        "manifest sha256 mismatch")


def test_version_json_must_carry_the_manifest_digest(pkg):
    version = json.loads((pkg / W.VERSION_NAME).read_text())
    version["source_manifest_sha256"] = "0" * 64
    (pkg / W.VERSION_NAME).write_text(json.dumps(version))
    assert W.verify_tree(pkg)["problems"] == [
        "VERSION.json source_manifest_sha256 does not match SOURCE_MANIFEST.json"]


def test_missing_or_corrupt_manifest_fails(tmp_path, pkg):
    (tmp_path / "empty").mkdir()
    assert W.verify_tree(tmp_path / "empty")["problems"] == ["missing SOURCE_MANIFEST.json"]
    (pkg / W.MANIFEST_NAME).write_bytes(b"{not json")
    check = W.verify_tree(pkg)
    assert not check["verified"] and "not readable JSON" in check["problems"][0]
    assert W.verify_tree(tmp_path / "absent")["problems"][0].startswith("not a directory")


def test_unsafe_manifest_paths_are_refused(tmp_path):
    root = tmp_path / "pkg"
    make_package(root)
    manifest = json.loads((root / W.MANIFEST_NAME).read_text())
    manifest["files"]["../outside.txt"] = "0" * 64
    manifest["files"]["/etc/passwd"] = "0" * 64
    (root / W.MANIFEST_NAME).write_text(json.dumps(manifest))
    problems = W.verify_tree(root)["problems"]
    assert "unsafe manifest path: '../outside.txt'" in problems
    assert "unsafe manifest path: '/etc/passwd'" in problems
    result = W.install(root, tmp_path / "dest")
    assert result["exit_code"] == 20
    assert not (tmp_path / "dest").exists() and not (tmp_path / "outside.txt").exists()


@pytest.mark.skipif(os.name != "posix", reason="symlink creation")
def test_symlinks_in_governed_dirs_fail(pkg, tmp_path):
    (tmp_path / "elsewhere.py").write_bytes(b"x\n")
    os.symlink(tmp_path / "elsewhere.py", pkg / "src" / "geosim" / "link.py")
    os.symlink(tmp_path, pkg / "dashboard" / "linkdir")
    problems = W.verify_tree(pkg)["problems"]
    assert "unexpected file: src/geosim/link.py" in problems
    assert "unexpected file: dashboard/linkdir" in problems


# ---- install -----------------------------------------------------------------------------------------

def test_install_copies_exactly_the_listed_files_and_reverifies(pkg, tmp_path, capsys):
    (pkg / "notes.txt").write_bytes(b"not in the manifest\n")
    dest = tmp_path / "home" / "geo-workbench-src"
    assert W.main(["install", "--from", str(pkg), "--to", str(dest), "--json"]) == 0
    out = _json_line(capsys)
    assert out["code"] == "OK" and out["commit"] == COMMIT and out["previous"] is None
    copied = {p.relative_to(dest).as_posix() for p in dest.rglob("*") if p.is_file()}
    assert copied == set(FILES) | {W.MANIFEST_NAME, W.VERSION_NAME}
    assert W.main(["verify", "--root", str(dest), "--expect-commit", COMMIT]) == 0
    assert not list(tmp_path.joinpath("home").glob(".*installing*"))


def test_tampering_the_installed_tree_fails_verification(pkg, tmp_path):
    dest = tmp_path / "dest"
    assert W.install(pkg, dest)["exit_code"] == 0
    (dest / "dashboard" / "app.py").write_bytes(b"print('changed')\n")
    assert W.main(["verify", "--root", str(dest)]) == 20


def test_an_extra_src_file_in_the_installed_tree_fails(pkg, tmp_path):
    dest = tmp_path / "dest"
    assert W.install(pkg, dest)["exit_code"] == 0
    (dest / "src" / "geoml" / "shortcut.py").write_bytes(b"x\n")
    assert W.main(["verify", "--root", str(dest)]) == 20


def test_install_never_overwrites_without_replace(pkg, tmp_path):
    dest = tmp_path / "dest"
    assert W.install(pkg, dest)["exit_code"] == 0
    (dest / "marker.txt").write_bytes(b"old install\n")
    result = W.install(pkg, dest)
    assert result["exit_code"] == 13 and result["code"] == "EXISTS"
    assert result["existing_commit"] == COMMIT
    assert (dest / "marker.txt").read_bytes() == b"old install\n"


def test_replace_moves_the_old_tree_aside_and_keeps_it(pkg, tmp_path):
    dest = tmp_path / "dest"
    assert W.install(pkg, dest)["exit_code"] == 0
    (dest / "marker.txt").write_bytes(b"old install\n")
    result = W.install(pkg, dest, replace=True, now=_fixed_now)
    assert result["exit_code"] == 0
    previous = tmp_path / "dest.previous-20261105T120000Z"
    assert result["previous"] == str(previous)
    assert (previous / "marker.txt").read_bytes() == b"old install\n"
    assert W.verify_tree(previous)["verified"]
    assert not (dest / "marker.txt").exists() and W.verify_tree(dest)["verified"]

    again = W.install(pkg, dest, replace=True, now=_fixed_now)
    assert again["exit_code"] == 0 and again["previous"] == str(previous) + "-1"
    assert previous.is_dir()


def test_install_refuses_an_unverified_package(tmp_path):
    bad = make_package(tmp_path / "pkg", source="worktree-overlay")
    result = W.install(bad, tmp_path / "dest")
    assert result["exit_code"] == 20 and result["code"] == "NOT_VERIFIED"
    assert not (tmp_path / "dest").exists()


def test_install_refuses_dest_under_mnt(pkg, tmp_path, monkeypatch, capsys):
    fake_mnt = tmp_path / "mnt"
    (fake_mnt / "c").mkdir(parents=True)
    monkeypatch.setattr(W, "MNT_ROOT", fake_mnt)
    for dest in (fake_mnt / "c" / "Users" / "x" / "geo", fake_mnt):
        assert W.main(["install", "--from", str(pkg), "--to", str(dest), "--json"]) == 14
        assert _json_line(capsys)["code"] == "DEST_REFUSED"
    assert not (fake_mnt / "c" / "Users").exists()


@pytest.mark.skipif(os.name != "posix", reason="symlink creation")
def test_install_refuses_a_symlink_into_mnt(pkg, tmp_path, monkeypatch):
    fake_mnt = tmp_path / "mnt"
    (fake_mnt / "c").mkdir(parents=True)
    monkeypatch.setattr(W, "MNT_ROOT", fake_mnt)
    os.symlink(fake_mnt / "c", tmp_path / "winlink")
    assert W.install(pkg, tmp_path / "winlink" / "geo")["exit_code"] == 14


def test_install_refuses_overlapping_package_and_dest(pkg):
    assert W.install(pkg, pkg / "nested")["exit_code"] == 14
    assert W.install(pkg, pkg)["exit_code"] == 14
    assert W.install(pkg, pkg.parent, replace=True)["exit_code"] == 14


# ---- venv (injected runner; nothing is installed) ----------------------------------------------------

class FakeRunner:
    def __init__(self, fail=None, venv_output=""):
        self.calls = []
        self.fail = fail or (lambda argv: False)
        self.venv_output = venv_output

    def __call__(self, argv):
        self.calls.append(list(argv))
        assert isinstance(argv, list) and all(isinstance(a, str) for a in argv)
        if argv[1:3] == ["-m", "venv"]:
            if self.fail(argv):
                return W.RunResult(1, self.venv_output)
            python = W.venv_python(Path(argv[3]))
            python.parent.mkdir(parents=True, exist_ok=True)
            python.write_bytes(b"")
            return W.RunResult(0, "")
        return W.RunResult(1 if self.fail(argv) else 0, "")


def _expected(dest: Path, python: str, fallback: bool = False) -> list:
    vpy = str(W.venv_python(dest / ".venv"))
    pip = [vpy, "-m", "pip", "install"]
    calls = [[python, "-m", "venv", str(dest / ".venv")],
             pip + ["torch==2.14.1+cpu", "--index-url", "https://download.pytorch.org/whl/cpu"]]
    if fallback:
        calls.append(pip + ["torch>=2.2"])
    return calls + [pip + ["-e", f"{dest}[dev,ml]"],
                    pip + ["-r", str(dest / "dashboard" / "requirements.txt")]]


def test_venv_success_issues_the_expected_commands(pkg):
    runner = FakeRunner()
    result = W.setup_venv(pkg, runner=runner, python="/usr/bin/python3")
    assert result["exit_code"] == 0 and result["warnings"] == []
    assert runner.calls == _expected(pkg, "/usr/bin/python3")
    assert [s["argv"] for s in result["steps"]] == runner.calls
    assert W.verify_tree(pkg)["verified"]


def test_venv_falls_back_to_pypi_torch_only_after_the_cpu_index_fails(pkg, capsys):
    runner = FakeRunner(fail=lambda argv: "--index-url" in argv)
    result = W.setup_venv(pkg, runner=runner, python="py3")
    assert result["exit_code"] == 0
    assert runner.calls == _expected(pkg, "py3", fallback=True)
    assert "large" in result["warnings"][0]
    assert "PyPI Linux wheel is large" in capsys.readouterr().err


def test_venv_reports_pip_failure_when_both_torch_sources_fail(pkg):
    runner = FakeRunner(fail=lambda argv: any(a.startswith("torch") for a in argv))
    result = W.setup_venv(pkg, runner=runner, python="py3")
    assert result["exit_code"] == 16 and result["code"] == "PIP_FAILED"
    assert runner.calls == _expected(pkg, "py3", fallback=True)[:3]


@pytest.mark.parametrize("failing,issued", [("-e", 3), ("-r", 4)])
def test_venv_stops_at_the_first_pip_failure(pkg, failing, issued):
    runner = FakeRunner(fail=lambda argv: failing in argv)
    result = W.setup_venv(pkg, runner=runner, python="py3")
    assert result["exit_code"] == 16
    assert runner.calls == _expected(pkg, "py3")[:issued]


def test_venv_without_ensurepip_asks_for_python3_venv(pkg):
    debian = ("The virtual environment was not created successfully because ensurepip is not\n"
              "available.  On Debian/Ubuntu systems, you need to install the python3-venv package\n")
    runner = FakeRunner(fail=lambda argv: True, venv_output=debian)
    result = W.setup_venv(pkg, runner=runner, python="python3")
    assert result["exit_code"] == 15 and result["code"] == "VENV_UNAVAILABLE"
    assert result["ensurepip_missing"] is True
    assert "sudo apt-get install -y python3-venv" in result["message"]
    assert runner.calls == [["python3", "-m", "venv", str(pkg / ".venv")]]


def test_venv_refuses_an_unverified_tree(pkg):
    (pkg / "scripts" / "added.py").write_bytes(b"x\n")
    runner = FakeRunner()
    assert W.setup_venv(pkg, runner=runner)["exit_code"] == 20
    assert runner.calls == []


def test_venv_cli_prints_one_json_line(pkg, monkeypatch, capsys):
    runner = FakeRunner()
    monkeypatch.setattr(W, "run_streaming", runner)
    assert W.main(["venv", "--src", str(pkg), "--json"]) == 0
    out = _json_line(capsys)
    assert out["code"] == "OK" and len(out["steps"]) == 4


def test_the_default_runner_uses_no_shell_and_reports_exit_codes(capsys):
    ok = W.run_streaming([sys.executable, "-c", "print('hi; echo nope')"])
    assert ok.returncode == 0 and ok.output == "hi; echo nope\n"
    assert "hi; echo nope" in capsys.readouterr().err
    assert W.run_streaming([sys.executable, "-c", "raise SystemExit(7)"]).returncode == 7
    assert W.run_streaming([str(Path("/nonexistent") / "prog")]).returncode == 127


# ---- end to end: a package built from the committed HEAD ---------------------------------------------

def _in_git_checkout() -> bool:
    return shutil.which("git") is not None and subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True).returncode == 0


@pytest.fixture(scope="module")
def head_tree(tmp_path_factory):
    if not _in_git_checkout():
        pytest.skip("needs git and a git checkout")
    out = tmp_path_factory.mktemp("pkg-head")
    proc = subprocess.run([sys.executable, str(ROOT / "scripts" / "build_windows_package.py"),
                           "--out", str(out), "--version", "pytest"],
                          capture_output=True, text=True, timeout=600)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    extracted = tmp_path_factory.mktemp("extracted")
    with zipfile.ZipFile(out / BW.ZIP_NAME) as zf:
        zf.extractall(extracted)
    return extracted / BW.ZIP_ROOT


def test_the_head_package_verifies_installs_and_reverifies(head_tree, tmp_path):
    head = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"],
                          capture_output=True, text=True).stdout.strip()
    check = W.verify_tree(head_tree, expect_commit=head)
    assert check["verified"], check["problems"]
    dest = tmp_path / "geo-workbench-src"
    result = W.install(head_tree, dest)
    assert result["exit_code"] == 0, result
    assert W.verify_tree(dest, expect_commit=head,
                         expect_manifest_sha256=check["manifest_sha256"])["verified"]


# ---- agreement with geodash.pilot.source_identity (package-snapshot mode) ----------------------------

def _pilot():
    if not (ROOT / "dashboard" / "geodash" / "pilot.py").is_file():
        pytest.skip("dashboard/geodash/pilot.py not present")
    sys.path[:0] = [str(ROOT / "dashboard"), str(ROOT / "src")]
    from geodash import pilot
    return pilot


def _case_ok(root): pass
def _case_tampered(root): (root / "src" / "geosim" / "__init__.py").write_bytes(b"changed\n")
def _case_extra_src(root): (root / "src" / "geosim" / "extra.py").write_bytes(b"x\n")
def _case_extra_dashboard(root): (root / "dashboard" / "extra.py").write_bytes(b"x\n")
def _case_missing(root): (root / "dashboard" / "app.py").unlink()


def _case_bytecode(root):
    (root / "dashboard" / "__pycache__").mkdir()
    (root / "dashboard" / "__pycache__" / "app.cpython-312.pyc").write_bytes(b"\0")


def _case_editable_metadata(root):
    # `pip install -e DEST[dev,ml]` (the venv step) writes this into src/; the preflight that
    # follows must still verify the tree.
    (root / "src" / "geosim.egg-info").mkdir()
    (root / "src" / "geosim.egg-info" / "PKG-INFO").write_bytes(b"Name: geosim\n")


@pytest.mark.parametrize("case", [_case_ok, _case_tampered, _case_extra_src, _case_extra_dashboard,
                                  _case_missing, _case_bytecode, _case_editable_metadata])
def test_verify_agrees_with_pilot_source_identity(tmp_path, case):
    pilot = _pilot()
    root = make_package(tmp_path / "tree")
    case(root)
    mine = W.verify_tree(root, expect_commit=COMMIT)
    theirs = pilot.source_identity(repo_root=root, expect_commit=COMMIT)
    assert theirs["mode"] == "package-snapshot"
    assert theirs["verified"] == mine["verified"], (mine["problems"], theirs["problems"])
    assert theirs["manifest_sha256"] == mine["manifest_sha256"]
    assert theirs["commit"] == mine["commit"]

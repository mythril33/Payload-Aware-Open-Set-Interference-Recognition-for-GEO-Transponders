"""Windows package builder: SOURCE_MANIFEST.json / VERSION.json consistency and self-verification.

The end-to-end tests build from the committed HEAD (``git archive HEAD``) and from the working
tree (``--worktree``); both need a git checkout. The tamper tests run on synthetic zips written
with the builder's own manifest functions.
"""
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build_windows_package.py"
WSL_SETUP_REL = "windows/wsl/geo_wsl_setup.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


BW = _load("build_windows_package", SCRIPT)


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True)


def _in_git_checkout() -> bool:
    if shutil.which("git") is None:
        return False
    return _git("rev-parse", "HEAD").returncode == 0


needs_git = pytest.mark.skipif(not _in_git_checkout(), reason="needs git and a git checkout")


def _build(out: Path, *extra: str) -> Path:
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--out", str(out), "--version", "pytest", *extra],
        capture_output=True, text=True, timeout=600,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return out / BW.ZIP_NAME


def _members(zip_path: Path) -> dict:
    prefix = BW.ZIP_ROOT + "/"
    with zipfile.ZipFile(zip_path) as zf:
        return {name[len(prefix):]: zf.read(name) for name in zf.namelist()}


@pytest.fixture(scope="module")
def head_zip(tmp_path_factory):
    if not _in_git_checkout():
        pytest.skip("needs git and a git checkout")
    return _build(tmp_path_factory.mktemp("pkg-head"))


def _head_blobs() -> set:
    out = _git("ls-tree", "-r", "-z", "HEAD").stdout.decode("utf-8")
    blobs = set()
    for entry in filter(None, out.split("\0")):
        meta, path = entry.split("\t", 1)
        if meta.split()[0] in ("100644", "100755"):
            blobs.add(path)
    return blobs


# ---- end to end: committed HEAD -------------------------------------------------------------------------

@needs_git
def test_head_package_manifest_lists_exactly_the_packaged_bytes(head_zip):
    members = _members(head_zip)
    manifest_bytes = members[BW.MANIFEST_NAME]
    manifest = json.loads(manifest_bytes)
    version = json.loads(members[BW.VERSION_NAME])
    head = _git("rev-parse", "HEAD").stdout.decode().strip()

    assert manifest["schema"] == "GEO-workbench-source-manifest/1"
    assert manifest["source"] == "git archive HEAD"
    assert manifest["commit"] == head == version["commit"]
    assert version["source"] == "git archive HEAD"
    assert version["source_manifest_sha256"] == hashlib.sha256(manifest_bytes).hexdigest()
    payload = {rel: data for rel, data in members.items() if rel not in BW.GENERATED_NAMES}
    assert set(manifest["files"]) == set(payload)
    for rel, data in payload.items():
        assert manifest["files"][rel] == hashlib.sha256(data).hexdigest(), rel
    assert BW.verify_zip(head_zip) == []


@needs_git
def test_head_package_is_the_committed_tree_minus_exclusions(head_zip):
    members = _members(head_zip)
    packaged = set(members) - BW.GENERATED_NAMES
    assert packaged == {rel for rel in _head_blobs() if not BW.is_excluded(rel)}
    assert not any(rel.startswith("deliverables/") for rel in members)
    assert ".gitignore" in members and "windows/KURULUM.bat" in members
    assert not BW.is_excluded(WSL_SETUP_REL)
    # The WSL bootstrap is packaged as soon as it is committed.
    assert (WSL_SETUP_REL in members) == (WSL_SETUP_REL in _head_blobs())


@needs_git
def test_worktree_package_is_marked_overlay_and_carries_the_wsl_bootstrap(tmp_path):
    members = _members(_build(tmp_path, "--worktree"))
    manifest = json.loads(members[BW.MANIFEST_NAME])
    assert manifest["source"] == "worktree-overlay"
    assert WSL_SETUP_REL in members and WSL_SETUP_REL in manifest["files"]
    assert members[BW.MANIFEST_NAME] and BW.MANIFEST_NAME not in manifest["files"]
    assert BW.VERSION_NAME not in manifest["files"]
    assert not any(rel.startswith("deliverables/") for rel in members)


# ---- synthetic zips: self-verification catches every inconsistency ----------------------------------

SYNTH = {
    ".gitignore": b"__pycache__/\n",
    "windows/KURULUM.bat": b"@echo off\r\necho ok\r\n",
    "src/geosim/__init__.py": b"VERSION = 1\n",
    "dashboard/app.py": b"print('app')\n",
}


def _write_zip(path: Path, files: dict, manifest: bytes | None, version: bytes | None,
               extra: dict | None = None) -> Path:
    with zipfile.ZipFile(path, "w") as zf:
        if version is not None:
            zf.writestr(f"{BW.ZIP_ROOT}/{BW.VERSION_NAME}", version)
        if manifest is not None:
            zf.writestr(f"{BW.ZIP_ROOT}/{BW.MANIFEST_NAME}", manifest)
        for rel, data in {**files, **(extra or {})}.items():
            zf.writestr(f"{BW.ZIP_ROOT}/{rel}", data)
    return path


def _synth(path: Path, files=None, extra=None, manifest=None, version=None,
           source=BW.SOURCE_HEAD) -> Path:
    files = dict(SYNTH if files is None else files)
    manifest = BW.build_source_manifest(files, "c" * 40, source) if manifest is None else manifest
    if version is None:
        version = BW.build_version_json("v", "c" * 40, "2026-11-05T00:00:00Z", source, manifest)
    return _write_zip(path, files, manifest, version, extra)


def test_manifest_bytes_are_canonical_ascii_and_sorted():
    a = BW.build_source_manifest(dict(SYNTH), "c" * 40, BW.SOURCE_HEAD)
    b = BW.build_source_manifest(dict(reversed(list(SYNTH.items()))), "c" * 40, BW.SOURCE_HEAD)
    assert a == b and a.decode("ascii").endswith("}\n")
    files = json.loads(a)["files"]
    assert list(files) == sorted(SYNTH)
    assert files["dashboard/app.py"] == hashlib.sha256(SYNTH["dashboard/app.py"]).hexdigest()
    version = json.loads(BW.build_version_json("v", "c" * 40, "t", BW.SOURCE_HEAD, a))
    assert version["source_manifest_sha256"] == hashlib.sha256(a).hexdigest()


def test_consistent_synthetic_zip_self_verifies(tmp_path):
    assert BW.verify_zip(_synth(tmp_path / "ok.zip")) == []
    assert BW.verify_zip(_synth(tmp_path / "wt.zip", source=BW.SOURCE_WORKTREE)) == []


def test_self_verify_rejects_a_changed_file(tmp_path):
    manifest = BW.build_source_manifest(dict(SYNTH), "c" * 40, BW.SOURCE_HEAD)
    changed = {**SYNTH, "src/geosim/__init__.py": b"VERSION = 2\n"}
    problems = BW.verify_zip(_synth(tmp_path / "z.zip", files=changed, manifest=manifest))
    assert problems == ["manifest hash mismatch: src/geosim/__init__.py"]


def test_self_verify_rejects_unlisted_and_missing_files(tmp_path):
    manifest = BW.build_source_manifest(dict(SYNTH), "c" * 40, BW.SOURCE_HEAD)
    extra = BW.verify_zip(_synth(tmp_path / "a.zip", manifest=manifest,
                                 extra={"src/geosim/extra.py": b"x\n"}))
    assert extra == ["zip file not listed in the manifest: src/geosim/extra.py"]
    fewer = {k: v for k, v in SYNTH.items() if k != "dashboard/app.py"}
    missing = BW.verify_zip(_synth(tmp_path / "b.zip", files=fewer, manifest=manifest))
    assert missing == ["manifest lists a file absent from the zip: dashboard/app.py"]


def test_self_verify_rejects_version_and_manifest_defects(tmp_path):
    bad_version = BW.build_version_json("v", "c" * 40, "t", BW.SOURCE_HEAD, b"other bytes")
    assert BW.verify_zip(_synth(tmp_path / "v.zip", version=bad_version)) == [
        "VERSION.json source_manifest_sha256 does not match SOURCE_MANIFEST.json"]

    no_manifest = _write_zip(tmp_path / "m.zip", dict(SYNTH), None,
                             BW.build_version_json("v", "c", "t", BW.SOURCE_HEAD, b""))
    assert BW.verify_zip(no_manifest) == ["missing SOURCE_MANIFEST.json"]

    wrong_schema = json.dumps({"schema": "other/1", "commit": "c", "source": "elsewhere",
                               "files": {}}).encode()
    problems = BW.verify_zip(_synth(tmp_path / "s.zip", manifest=wrong_schema))
    assert any("schema" in p for p in problems)
    assert any("source is 'elsewhere'" in p for p in problems)
    assert sum("not listed in the manifest" in p for p in problems) == len(SYNTH)


def test_self_verify_keeps_the_existing_crlf_dotfile_and_exclusion_checks(tmp_path):
    lf_bat = {**SYNTH, "windows/KURULUM.bat": b"@echo off\necho ok\n"}
    assert "KURULUM.bat inside the zip has no CRLF line endings" in BW.verify_zip(
        _synth(tmp_path / "lf.zip", files=lf_bat))
    no_dot = {k: v for k, v in SYNTH.items() if k != ".gitignore"}
    assert any("dotfile check failed" in p for p in BW.verify_zip(_synth(tmp_path / "d.zip", files=no_dot)))
    leaked = {**SYNTH, "deliverables/report.docx": b"x"}
    assert "excluded path present in zip: deliverables/report.docx" in BW.verify_zip(
        _synth(tmp_path / "x.zip", files=leaked))

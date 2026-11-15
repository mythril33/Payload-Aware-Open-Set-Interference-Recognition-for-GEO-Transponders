"""Windows package builder: SOURCE_MANIFEST.json / VERSION.json / geo-source.bundle consistency.

The end-to-end tests build from the committed HEAD (``git archive HEAD``) and from the working
tree (``--worktree``); both need a full-history git checkout, so on a shallow checkout (the
readiness CI) they are replaced by the shallow-refusal check. A small temporary full-history
repository covers the bundle path everywhere. The tamper tests run on synthetic zips written
with the builder's own manifest functions and a real bundle of that small repository.
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


def _is_shallow() -> bool:
    return _git("rev-parse", "--is-shallow-repository").stdout.decode().strip() == "true"


needs_git = pytest.mark.skipif(not _in_git_checkout(), reason="needs git and a git checkout")
needs_full_history = pytest.mark.skipif(
    not _in_git_checkout() or _is_shallow(),
    reason="needs a full-history git checkout (the shallow case is tested for refusal)")


def _run_git(repo: Path, *args: str) -> str:
    proc = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return proc.stdout.strip()


def make_git_repo(repo: Path, commits: list[dict]) -> list[str]:
    """A throwaway repository with one commit per ``{relpath: bytes}`` dict; returns the commit ids."""
    repo.mkdir(parents=True)
    _run_git(repo, "init", "-q")
    ids = []
    for n, files in enumerate(commits):
        for rel, data in files.items():
            (repo / rel).parent.mkdir(parents=True, exist_ok=True)
            (repo / rel).write_bytes(data)
        _run_git(repo, "add", "-A")
        _run_git(repo, "-c", "user.name=t", "-c", "user.email=t@example.invalid",
                 "-c", "commit.gpgsign=false", "commit", "-q", "-m", f"commit {n}")
        ids.append(_run_git(repo, "rev-parse", "HEAD"))
    return ids


def _run_builder(script: Path, out: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(script), "--out", str(out), "--version", "pytest", *extra],
        capture_output=True, text=True, timeout=600,
    )


def _build(out: Path, *extra: str, script: Path = SCRIPT) -> Path:
    proc = _run_builder(script, out, *extra)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return out / BW.ZIP_NAME


def _members(zip_path: Path) -> dict:
    prefix = BW.ZIP_ROOT + "/"
    with zipfile.ZipFile(zip_path) as zf:
        return {name[len(prefix):]: zf.read(name) for name in zf.namelist()}


@pytest.fixture(scope="module")
def head_zip(tmp_path_factory):
    if not _in_git_checkout() or _is_shallow():
        pytest.skip("needs a full-history git checkout")
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

@needs_full_history
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


@needs_full_history
def test_head_package_carries_a_full_history_bundle_of_head(head_zip, tmp_path):
    members = _members(head_zip)
    version = json.loads(members[BW.VERSION_NAME])
    head = _git("rev-parse", "HEAD").stdout.decode().strip()
    bundle = members[BW.BUNDLE_NAME]
    assert version["source_bundle"] == BW.BUNDLE_NAME == "geo-source.bundle"
    assert version["source_bundle_sha256"] == hashlib.sha256(bundle).hexdigest()
    assert version["source_bundle_head"] == head == version["commit"]
    assert BW.BUNDLE_NAME in json.loads(members[BW.MANIFEST_NAME])["files"]
    assert BW.bundle_prerequisites(bundle) == []
    (tmp_path / BW.BUNDLE_NAME).write_bytes(bundle)
    heads = subprocess.run(["git", "bundle", "list-heads", str(tmp_path / BW.BUNDLE_NAME)],
                           capture_output=True, text=True, check=True).stdout.splitlines()
    assert f"{head} HEAD" in heads


@needs_git
def test_the_real_checkout_is_refused_exactly_when_it_is_shallow(tmp_path):
    if not _is_shallow():
        pytest.skip("full-history checkout: the build itself is tested above")
    proc = _run_builder(SCRIPT, tmp_path / "out")
    assert proc.returncode == 3
    assert BW.SHALLOW_MESSAGE in proc.stderr
    assert not (tmp_path / "out" / BW.ZIP_NAME).exists()


@needs_git
def test_a_shallow_clone_refuses_with_exit_3(tmp_path):
    clone = tmp_path / "shallow"
    proc = subprocess.run(["git", "clone", "-q", "--depth", "1", ROOT.as_uri(), str(clone)],
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert _run_git(clone, "rev-parse", "--is-shallow-repository") == "true"
    # The current builder, run from inside the shallow clone (it packages its own repository).
    shutil.copyfile(SCRIPT, clone / "scripts" / SCRIPT.name)
    for extra in ((), ("--worktree",)):
        proc = _run_builder(clone / "scripts" / SCRIPT.name, tmp_path / "out", *extra)
        assert proc.returncode == 3, proc.stdout + proc.stderr
        assert ("full Git history is required to build geo-source.bundle "
                "(use fetch-depth: 0)") in proc.stderr
    assert not (tmp_path / "out" / BW.ZIP_NAME).exists()


@needs_full_history
def test_head_package_is_the_committed_tree_minus_exclusions(head_zip):
    members = _members(head_zip)
    packaged = set(members) - BW.GENERATED_NAMES - {BW.BUNDLE_NAME}
    assert packaged == {rel for rel in _head_blobs() if not BW.is_excluded(rel)}
    assert not any(rel.startswith("deliverables/") for rel in members)
    assert ".gitignore" in members and "windows/KURULUM.bat" in members
    assert not BW.is_excluded(WSL_SETUP_REL)
    # The WSL bootstrap is packaged as soon as it is committed.
    assert (WSL_SETUP_REL in members) == (WSL_SETUP_REL in _head_blobs())


@needs_full_history
def test_worktree_package_is_marked_overlay_and_carries_the_wsl_bootstrap(tmp_path):
    members = _members(_build(tmp_path, "--worktree"))
    manifest = json.loads(members[BW.MANIFEST_NAME])
    assert manifest["source"] == "worktree-overlay"
    assert WSL_SETUP_REL in members and WSL_SETUP_REL in manifest["files"]
    assert members[BW.MANIFEST_NAME] and BW.MANIFEST_NAME not in manifest["files"]
    assert BW.VERSION_NAME not in manifest["files"]
    assert BW.BUNDLE_NAME in manifest["files"]
    assert json.loads(members[BW.VERSION_NAME])["source_bundle_head"] == _git(
        "rev-parse", "HEAD").stdout.decode().strip()
    assert not any(rel.startswith("deliverables/") for rel in members)


# ---- a small full-history repository: the bundle path on every checkout --------------------------

SMALL_REPO_COMMITS = [
    {".gitignore": b"__pycache__/\n", "windows/KURULUM.bat": b"@echo off\r\necho ok\r\n"},
    {"src/geosim/x.py": b"X = 1\n"},
    {"src/geosim/x.py": b"X = 2\n", "dashboard/app.py": b"print('app')\n"},
]


@pytest.fixture(scope="module")
def small_repo(tmp_path_factory):
    if shutil.which("git") is None:
        pytest.skip("needs git")
    repo = tmp_path_factory.mktemp("small") / "repo"
    ids = make_git_repo(repo, SMALL_REPO_COMMITS)
    (repo / "scripts").mkdir()
    shutil.copyfile(SCRIPT, repo / "scripts" / SCRIPT.name)
    return repo, ids


def test_a_full_history_repository_packages_a_complete_bundle(small_repo, tmp_path):
    repo, ids = small_repo
    members = _members(_build(tmp_path / "out", script=repo / "scripts" / SCRIPT.name))
    version = json.loads(members[BW.VERSION_NAME])
    bundle = members[BW.BUNDLE_NAME]
    assert version["commit"] == version["source_bundle_head"] == ids[-1]
    assert version["source_bundle_sha256"] == hashlib.sha256(bundle).hexdigest()
    assert json.loads(members[BW.MANIFEST_NAME])["files"][BW.BUNDLE_NAME] == version[
        "source_bundle_sha256"]
    clone = tmp_path / "clone"
    (tmp_path / "b.bundle").write_bytes(bundle)
    subprocess.run(["git", "clone", "-q", str(tmp_path / "b.bundle"), str(clone)], check=True)
    assert _run_git(clone, "rev-list", "--count", "HEAD") == str(len(ids))
    assert subprocess.run(["git", "-C", str(clone), "fsck", "--connectivity-only"],
                          capture_output=True).returncode == 0
    notes = (tmp_path / "out" / "RELEASE_NOTES.md").read_text(encoding="utf-8")
    assert "full Git history" in notes and "as private as the repository itself" in notes


def test_commit_override_other_than_head_is_refused(small_repo, tmp_path):
    repo, ids = small_repo
    proc = _run_builder(repo / "scripts" / SCRIPT.name, tmp_path / "out", "--commit", ids[0])
    assert proc.returncode == 1 and "is not HEAD" in proc.stderr


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


@pytest.fixture(scope="module")
def bundled(small_repo):
    """(bundle bytes, head commit) of the small repository, made with the builder's function."""
    repo, ids = small_repo
    return BW.create_bundle(repo), ids[-1]


@pytest.fixture
def synth(bundled):
    bundle, head = bundled

    def make(path: Path, files=None, extra=None, manifest=None, version=None,
             source=BW.SOURCE_HEAD, bundle_bytes=bundle, commit=head) -> Path:
        files = dict(SYNTH if files is None else files)
        if bundle_bytes is not None:
            files.setdefault(BW.BUNDLE_NAME, bundle_bytes)
        manifest = BW.build_source_manifest(files, commit, source) if manifest is None else manifest
        if version is None:
            version = BW.build_version_json("v", commit, "2026-11-05T00:00:00Z", source, manifest,
                                            files.get(BW.BUNDLE_NAME))
        return _write_zip(path, files, manifest, version, extra)
    return make


def test_manifest_bytes_are_canonical_ascii_and_sorted():
    a = BW.build_source_manifest(dict(SYNTH), "c" * 40, BW.SOURCE_HEAD)
    b = BW.build_source_manifest(dict(reversed(list(SYNTH.items()))), "c" * 40, BW.SOURCE_HEAD)
    assert a == b and a.decode("ascii").endswith("}\n")
    files = json.loads(a)["files"]
    assert list(files) == sorted(SYNTH)
    assert files["dashboard/app.py"] == hashlib.sha256(SYNTH["dashboard/app.py"]).hexdigest()
    version = json.loads(BW.build_version_json("v", "c" * 40, "t", BW.SOURCE_HEAD, a))
    assert version["source_manifest_sha256"] == hashlib.sha256(a).hexdigest()


def test_consistent_synthetic_zip_self_verifies(tmp_path, synth):
    assert BW.verify_zip(synth(tmp_path / "ok.zip")) == []
    assert BW.verify_zip(synth(tmp_path / "wt.zip", source=BW.SOURCE_WORKTREE)) == []


def test_self_verify_rejects_a_changed_file(tmp_path, synth, bundled):
    files = {**SYNTH, BW.BUNDLE_NAME: bundled[0]}
    manifest = BW.build_source_manifest(files, bundled[1], BW.SOURCE_HEAD)
    changed = {**files, "src/geosim/__init__.py": b"VERSION = 2\n"}
    problems = BW.verify_zip(synth(tmp_path / "z.zip", files=changed, manifest=manifest))
    assert problems == ["manifest hash mismatch: src/geosim/__init__.py"]


def test_self_verify_rejects_unlisted_and_missing_files(tmp_path, synth, bundled):
    files = {**SYNTH, BW.BUNDLE_NAME: bundled[0]}
    manifest = BW.build_source_manifest(files, bundled[1], BW.SOURCE_HEAD)
    extra = BW.verify_zip(synth(tmp_path / "a.zip", manifest=manifest,
                                extra={"src/geosim/extra.py": b"x\n"}))
    assert extra == ["zip file not listed in the manifest: src/geosim/extra.py"]
    fewer = {k: v for k, v in files.items() if k != "dashboard/app.py"}
    missing = BW.verify_zip(synth(tmp_path / "b.zip", files=fewer, manifest=manifest))
    assert missing == ["manifest lists a file absent from the zip: dashboard/app.py"]


def test_self_verify_rejects_version_and_manifest_defects(tmp_path, synth, bundled):
    bundle, head = bundled
    bad_version = BW.build_version_json("v", head, "t", BW.SOURCE_HEAD, b"other bytes", bundle)
    assert BW.verify_zip(synth(tmp_path / "v.zip", version=bad_version)) == [
        "VERSION.json source_manifest_sha256 does not match SOURCE_MANIFEST.json"]

    no_manifest = _write_zip(tmp_path / "m.zip", {**SYNTH, BW.BUNDLE_NAME: bundle}, None,
                             BW.build_version_json("v", head, "t", BW.SOURCE_HEAD, b"", bundle))
    assert BW.verify_zip(no_manifest) == ["missing SOURCE_MANIFEST.json"]

    wrong_schema = json.dumps({"schema": "other/1", "commit": "c", "source": "elsewhere",
                               "files": {}}).encode()
    problems = BW.verify_zip(synth(tmp_path / "s.zip", manifest=wrong_schema))
    assert any("schema" in p for p in problems)
    assert any("source is 'elsewhere'" in p for p in problems)
    assert sum("not listed in the manifest" in p for p in problems) == len(SYNTH) + 1


def test_self_verify_keeps_the_existing_crlf_dotfile_and_exclusion_checks(tmp_path, synth):
    lf_bat = {**SYNTH, "windows/KURULUM.bat": b"@echo off\necho ok\n"}
    assert "KURULUM.bat inside the zip has no CRLF line endings" in BW.verify_zip(
        synth(tmp_path / "lf.zip", files=lf_bat))
    no_dot = {k: v for k, v in SYNTH.items() if k != ".gitignore"}
    assert any("dotfile check failed" in p for p in BW.verify_zip(synth(tmp_path / "d.zip", files=no_dot)))
    leaked = {**SYNTH, "deliverables/report.docx": b"x"}
    assert "excluded path present in zip: deliverables/report.docx" in BW.verify_zip(
        synth(tmp_path / "x.zip", files=leaked))


# ---- synthetic zips: the bundle checks -------------------------------------------------------------

def test_self_verify_requires_the_bundle(tmp_path, synth):
    assert BW.verify_zip(synth(tmp_path / "nb.zip", bundle_bytes=None)) == ["missing geo-source.bundle"]


def test_self_verify_rejects_a_bundle_that_does_not_match_version_json(tmp_path, synth, bundled):
    bundle, head = bundled
    files = {**SYNTH, BW.BUNDLE_NAME: bundle}
    manifest = BW.build_source_manifest(files, head, BW.SOURCE_HEAD)
    version = json.loads(BW.build_version_json("v", head, "t", BW.SOURCE_HEAD, manifest, bundle))
    version["source_bundle_sha256"] = "0" * 64
    problems = BW.verify_zip(synth(tmp_path / "sha.zip", files=files, manifest=manifest,
                                   version=json.dumps(version).encode()))
    assert problems == ["VERSION.json source_bundle_sha256 does not match geo-source.bundle"]


def test_self_verify_rejects_a_bundle_without_the_packaged_commit(tmp_path, synth, small_repo):
    _, ids = small_repo
    # VERSION.json names an older commit than the bundle's HEAD.
    problems = BW.verify_zip(synth(tmp_path / "old.zip", commit=ids[0]))
    assert problems == [f"git bundle list-heads does not contain '{ids[0]} HEAD'"]


def test_self_verify_rejects_bytes_that_are_not_a_bundle(tmp_path, synth):
    problems = BW.verify_zip(synth(tmp_path / "junk.zip", bundle_bytes=b"not a bundle\n"))
    assert problems == ["geo-source.bundle is not a git bundle: no bundle header terminator"]


def test_bundle_prerequisites_are_reported(tmp_path):
    header = b"# v2 git bundle\n-" + b"1" * 40 + b" parent\n" + b"2" * 40 + b" HEAD\n\nPACK"
    assert BW.bundle_prerequisites(header) == ["-" + "1" * 40 + " parent"]
    with pytest.raises(ValueError):
        BW.bundle_prerequisites(b"# v9 git bundle\n\n")

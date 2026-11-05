#!/usr/bin/env python3
"""Build the Windows installer zip for the Payload-Aware GEO Workbench.

Stdlib only; runs on Linux and Windows.

Packaging rule
--------------
* Default mode packages the tracked content of **git HEAD** (via ``git archive``),
  so the zip reproduces a committed state exactly.
* ``--worktree`` overlays the current working tree: the file list is
  ``git ls-files --cached --others --exclude-standard`` (tracked plus untracked,
  minus gitignored) and file bytes are read from the working tree. Use this
  while the ``windows/`` packaging files are not yet committed (parallel agents
  add untracked files); the contract exclusion list below still applies, which
  keeps the unrelated uncommitted work under ``deliverables/`` out.

Exclusions (both modes): ``deliverables/``, root-level ``*.docx``/``*.pdf``/
``*.xlsx``, ``geo_proje_ozeti.html``, ``data/``, ``runs/``, ``dist/``,
``.venv*``, ``windows/logs/``.

Outputs (under ``--out``):
* ``Payload-Aware-GEO-Workbench-Windows.zip`` — root folder
  ``Payload-Aware-GEO-Workbench/``, forward-slash arcnames, sorted order,
  plus ``VERSION.json``, ``SOURCE_MANIFEST.json`` and ``geo-source.bundle`` at
  the zip root folder.
* ``Payload-Aware-GEO-Workbench-Windows.zip.sha256`` — lowercase hex, two
  spaces, filename.
* ``RELEASE_NOTES.md`` — ``windows/SURUM_NOTLARI.md`` with a
  version/commit/date header prepended.

Source bundle
-------------
``geo-source.bundle`` is ``git bundle create <file> HEAD``: the full Git
history of the packaged commit, as private as the repository itself. The WSL
setup (``geo_wsl_setup.py install-git``) clones it, so the WSL source is a
genuine Git checkout whose ``git rev-parse HEAD`` is the packaged commit
(training records Git provenance). A bundle made in a shallow repository
clones into a repository with missing parents, so a shallow checkout is
refused (exit 3; CI must check out with ``fetch-depth: 0``). ``VERSION.json``
records ``source_bundle``, ``source_bundle_sha256`` and ``source_bundle_head``;
the bundle is listed in ``SOURCE_MANIFEST.json`` like any other file. The same
rule applies in ``--worktree`` mode (the bundle is still HEAD).

Source manifest
---------------
``SOURCE_MANIFEST.json`` (schema ``GEO-workbench-source-manifest/1``) lists the
sha256 of every packaged file except ``VERSION.json`` and itself, with the
commit and the source (``git archive HEAD`` by default, ``worktree-overlay``
with ``--worktree``). ``VERSION.json`` records ``source_manifest_sha256``, the
sha256 of the manifest file bytes. The WSL bootstrap
(``windows/wsl/geo_wsl_setup.py``) and ``geodash.pilot.source_identity`` verify
an extracted tree against this manifest; only a ``git archive HEAD`` manifest
counts as verified, so a ``--worktree`` package is for local testing only.

Self-verification: the zip must contain
``Payload-Aware-GEO-Workbench/windows/KURULUM.bat`` (with CRLF line endings
inside the zip) and no excluded path; every manifest hash must match the zip
bytes, the manifest must list exactly the packaged files, and
``VERSION.json`` must carry the manifest's sha256. The bundle must be present,
match ``source_bundle_sha256``, have no prerequisite commits and list
``<commit> HEAD`` (``git bundle list-heads``). Exit codes: 0 ok, 1 build
error, 2 self-verification failed, 3 shallow repository.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ZIP_ROOT = "Payload-Aware-GEO-Workbench"
ZIP_NAME = "Payload-Aware-GEO-Workbench-Windows.zip"
RELEASE_NOTES_SOURCE = "windows/SURUM_NOTLARI.md"
KURULUM_ARCNAME = f"{ZIP_ROOT}/windows/KURULUM.bat"
VERSION_NAME = "VERSION.json"
MANIFEST_NAME = "SOURCE_MANIFEST.json"
MANIFEST_SCHEMA = "GEO-workbench-source-manifest/1"
SOURCE_HEAD = "git archive HEAD"
SOURCE_WORKTREE = "worktree-overlay"
GENERATED_NAMES = frozenset({VERSION_NAME, MANIFEST_NAME})
BUNDLE_NAME = "geo-source.bundle"
SHALLOW_MESSAGE = "full Git history is required to build geo-source.bundle (use fetch-depth: 0)"
EXIT_SHALLOW = 3

EXCLUDED_PREFIXES = ("deliverables/", "data/", "runs/", "dist/", "windows/logs/")
ROOT_EXCLUDED_SUFFIXES = (".docx", ".pdf", ".xlsx")
ROOT_EXCLUDED_NAMES = frozenset({"geo_proje_ozeti.html"})


def is_excluded(rel_posix: str) -> bool:
    """Contract exclusion list, applied to a posix path relative to repo root."""
    if rel_posix.startswith(EXCLUDED_PREFIXES):
        return True
    first = rel_posix.split("/", 1)[0]
    if first.startswith(".venv"):
        return True
    if "/" not in rel_posix:
        if rel_posix in ROOT_EXCLUDED_NAMES:
            return True
        if rel_posix.lower().endswith(ROOT_EXCLUDED_SUFFIXES):
            return True
    return False


def run_git(repo: Path, *args: str) -> bytes:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True
    )
    return proc.stdout


def is_shallow(repo: Path) -> bool:
    return run_git(repo, "rev-parse", "--is-shallow-repository").decode().strip() == "true"


def create_bundle(repo: Path) -> bytes:
    """``git bundle create <tmp> HEAD`` bytes: every object reachable from HEAD."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / BUNDLE_NAME
        run_git(repo, "bundle", "create", str(path), "HEAD")
        return path.read_bytes()


def bundle_prerequisites(bundle: bytes) -> list[str]:
    """Prerequisite (``-<sha>``) lines of a v2/v3 bundle header; ValueError if it is not one."""
    end = bundle.find(b"\n\n")
    if end < 0:
        raise ValueError("no bundle header terminator")
    lines = bundle[:end].decode("ascii").split("\n")
    if lines[0] not in ("# v2 git bundle", "# v3 git bundle"):
        raise ValueError(f"unknown bundle signature {lines[0]!r}")
    return [line for line in lines[1:] if line.startswith("-")]


def bundle_problems(bundle: bytes | None, commit: str, version: dict) -> list[str]:
    """Check ``geo-source.bundle`` against ``VERSION.json`` and ``git bundle list-heads``."""
    if bundle is None:
        return [f"missing {BUNDLE_NAME}"]
    problems: list[str] = []
    if version.get("source_bundle") != BUNDLE_NAME:
        problems.append(f"{VERSION_NAME} source_bundle is {version.get('source_bundle')!r}")
    if version.get("source_bundle_sha256") != hashlib.sha256(bundle).hexdigest():
        problems.append(f"{VERSION_NAME} source_bundle_sha256 does not match {BUNDLE_NAME}")
    if version.get("source_bundle_head") != commit:
        problems.append(f"{VERSION_NAME} source_bundle_head is {version.get('source_bundle_head')!r}, "
                        f"expected the packaged commit {commit!r}")
    try:
        prerequisites = bundle_prerequisites(bundle)
    except (UnicodeDecodeError, ValueError) as exc:
        return problems + [f"{BUNDLE_NAME} is not a git bundle: {exc}"]
    if prerequisites:
        problems.append(f"{BUNDLE_NAME} is incomplete (prerequisite commits: {len(prerequisites)})")
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / BUNDLE_NAME
        path.write_bytes(bundle)
        try:
            proc = subprocess.run(["git", "bundle", "list-heads", str(path)], capture_output=True)
        except OSError as exc:
            return problems + [f"git bundle list-heads could not run: {exc}"]
    heads = proc.stdout.decode("utf-8", "replace").splitlines()
    if proc.returncode != 0:
        problems.append(f"git bundle list-heads failed (exit {proc.returncode})")
    elif f"{commit} HEAD" not in heads:
        problems.append(f"git bundle list-heads does not contain '{commit} HEAD'")
    return problems


def collect_head_files(repo: Path) -> dict[str, bytes]:
    """Tracked content of HEAD via git archive (no working-tree reads)."""
    files: dict[str, bytes] = {}
    with tempfile.TemporaryDirectory() as tmp:
        tar_path = Path(tmp) / "head.tar"
        with open(tar_path, "wb") as fh:
            fh.write(run_git(repo, "archive", "--format=tar", "HEAD"))
        with tarfile.open(tar_path) as tar:
            for member in tar.getmembers():
                if not member.isreg():
                    continue
                # Strip only a literal "./" prefix: lstrip("./") would also eat the leading dot of
                # dotfiles (".gitignore" -> "gitignore", ".github/..." -> "github/...").
                rel = member.name[2:] if member.name.startswith("./") else member.name
                if not rel or is_excluded(rel):
                    continue
                extracted = tar.extractfile(member)
                if extracted is None:
                    continue
                files[rel] = extracted.read()
    return files


def collect_worktree_files(repo: Path) -> dict[str, bytes]:
    """Tracked + untracked (non-ignored) files, bytes from the working tree."""
    raw = run_git(
        repo, "ls-files", "--cached", "--others", "--exclude-standard", "-z"
    )
    files: dict[str, bytes] = {}
    for rel in sorted({p for p in raw.decode("utf-8").split("\0") if p}):
        if is_excluded(rel):
            continue
        path = repo / rel
        if not path.is_file():
            # Deleted from the working tree, or a submodule/directory entry.
            continue
        files[rel] = path.read_bytes()
    return files


def build_source_manifest(files: dict[str, bytes], commit: str, source: str) -> bytes:
    """Canonical SOURCE_MANIFEST.json bytes for the packaged ``files``."""
    manifest = {
        "schema": MANIFEST_SCHEMA,
        "commit": commit,
        "source": source,
        "files": {rel: hashlib.sha256(files[rel]).hexdigest() for rel in sorted(files)},
    }
    return (json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=True) + "\n").encode("ascii")


def build_version_json(version: str, commit: str, built_utc: str, source: str,
                       manifest_bytes: bytes, bundle: bytes | None = None) -> bytes:
    record = {
        "version": version,
        "commit": commit,
        "built_utc": built_utc,
        "source": source,
        "source_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
    }
    if bundle is not None:
        record.update({
            "source_bundle": BUNDLE_NAME,
            "source_bundle_sha256": hashlib.sha256(bundle).hexdigest(),
            "source_bundle_head": commit,
        })
    return (json.dumps(record, indent=2) + "\n").encode("utf-8")


def manifest_problems(payload: dict[str, bytes], manifest_bytes: bytes | None,
                      version_bytes: bytes | None) -> list[str]:
    """Check the manifest against the packaged bytes (``payload`` excludes the two generated files)."""
    if manifest_bytes is None:
        return [f"missing {MANIFEST_NAME}"]
    try:
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        return [f"{MANIFEST_NAME} is not readable JSON: {exc}"]
    if not isinstance(manifest, dict):
        return [f"{MANIFEST_NAME} is not a JSON object"]
    problems: list[str] = []
    if manifest.get("schema") != MANIFEST_SCHEMA:
        problems.append(f"{MANIFEST_NAME} schema is {manifest.get('schema')!r}, expected {MANIFEST_SCHEMA!r}")
    if manifest.get("source") not in (SOURCE_HEAD, SOURCE_WORKTREE):
        problems.append(f"{MANIFEST_NAME} source is {manifest.get('source')!r}")
    if not isinstance(manifest.get("commit"), str) or not manifest.get("commit"):
        problems.append(f"{MANIFEST_NAME} has no commit")
    listed = manifest.get("files")
    if not isinstance(listed, dict):
        problems.append(f"{MANIFEST_NAME} has no files mapping")
        listed = {}
    for rel in sorted(set(listed) - set(payload)):
        problems.append(f"manifest lists a file absent from the zip: {rel}")
    for rel in sorted(set(payload) - set(listed)):
        problems.append(f"zip file not listed in the manifest: {rel}")
    for rel in sorted(set(listed) & set(payload)):
        if listed[rel] != hashlib.sha256(payload[rel]).hexdigest():
            problems.append(f"manifest hash mismatch: {rel}")
    if version_bytes is None:
        problems.append(f"missing {VERSION_NAME}")
    else:
        try:
            recorded = json.loads(version_bytes.decode("utf-8")).get("source_manifest_sha256")
        except (UnicodeDecodeError, ValueError, AttributeError):
            recorded = None
        if recorded != hashlib.sha256(manifest_bytes).hexdigest():
            problems.append(f"{VERSION_NAME} source_manifest_sha256 does not match {MANIFEST_NAME}")
    return problems


def build_release_notes(files: dict[str, bytes], repo: Path, version: str,
                        commit: str, built_utc: str) -> str:
    if RELEASE_NOTES_SOURCE in files:
        body = files[RELEASE_NOTES_SOURCE].decode("utf-8")
    else:
        source = repo / RELEASE_NOTES_SOURCE
        body = (
            source.read_text(encoding="utf-8")
            if source.is_file()
            else f"({RELEASE_NOTES_SOURCE} was not found in this build.)\n"
        )
    header = (
        "# Payload-Aware GEO Workbench — Windows package\n\n"
        f"- Version: {version}\n"
        f"- Commit: {commit}\n"
        f"- Built (UTC): {built_utc}\n"
        f"- Source bundle: `{BUNDLE_NAME}` carries the repository's full Git history up to this "
        "commit (as private as the repository itself); the WSL setup clones it so the WSL source "
        "is a genuine Git checkout of this commit.\n\n"
        "---\n\n"
    )
    return header + body


def verify_zip(zip_path: Path) -> list[str]:
    """Return a list of self-verification failures (empty = pass)."""
    import zipfile

    problems: list[str] = []
    prefix = ZIP_ROOT + "/"
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        if len(names) != len(set(names)):
            problems.append("duplicate arcnames in the zip")
        if KURULUM_ARCNAME not in names:
            problems.append(f"missing {KURULUM_ARCNAME}")
        else:
            data = zf.read(KURULUM_ARCNAME)
            if b"\r\n" not in data:
                problems.append("KURULUM.bat inside the zip has no CRLF line endings")
        if f"{ZIP_ROOT}/.gitignore" not in names:
            problems.append("dotfile check failed: .gitignore missing from the zip (dot-path mangling?)")
        notes_arcname = f"{ZIP_ROOT}/windows/SURUM_NOTLARI.md"
        if notes_arcname in names and b"CI_RUN_URL_PLACEHOLDER" in zf.read(notes_arcname):
            problems.append("windows/SURUM_NOTLARI.md still contains CI_RUN_URL_PLACEHOLDER")
        payload: dict[str, bytes] = {}
        for name in names:
            if not name.startswith(prefix):
                problems.append(f"arcname outside root folder: {name}")
                continue
            rel = name[len(prefix):]
            if not rel or rel in GENERATED_NAMES:
                continue
            if "\\" in rel:
                problems.append(f"backslash in arcname: {name}")
            if is_excluded(rel):
                problems.append(f"excluded path present in zip: {rel}")
            payload[rel] = zf.read(name)

        def _root_member(rel: str) -> bytes | None:
            arcname = prefix + rel
            return zf.read(arcname) if arcname in names else None

        version_bytes = _root_member(VERSION_NAME)
        problems.extend(manifest_problems(payload, _root_member(MANIFEST_NAME), version_bytes))
        try:
            version = json.loads(version_bytes.decode("utf-8")) if version_bytes is not None else {}
        except (UnicodeDecodeError, ValueError):
            version = {}
        if not isinstance(version, dict):
            version = {}
        commit = version.get("commit")
        if not isinstance(commit, str) or not commit:
            if version_bytes is not None:
                problems.append(f"{VERSION_NAME} has no commit")
        else:
            problems.extend(bundle_problems(payload.get(BUNDLE_NAME), commit, version))
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default="dist", help="output directory (default: dist)")
    parser.add_argument("--version", required=True, help="package version string")
    parser.add_argument("--commit", default=None,
                        help="commit id recorded in VERSION.json (default: git rev-parse HEAD)")
    parser.add_argument("--worktree", action="store_true",
                        help="overlay the current working tree (tracked + untracked, "
                             "non-ignored) instead of packaging git HEAD content")
    args = parser.parse_args(argv)

    repo = Path(__file__).resolve().parents[1]
    if is_shallow(repo):
        print(f"error: {SHALLOW_MESSAGE}", file=sys.stderr)
        return EXIT_SHALLOW
    head = run_git(repo, "rev-parse", "HEAD").decode().strip()
    commit = args.commit or head
    if commit != head:
        print(f"error: --commit {commit} is not HEAD {head}; {BUNDLE_NAME} carries HEAD",
              file=sys.stderr)
        return 1
    built_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    if args.worktree:
        files = collect_worktree_files(repo)
        source = "worktree overlay (git ls-files --cached --others --exclude-standard)"
        manifest_source = SOURCE_WORKTREE
    else:
        files = collect_head_files(repo)
        source = SOURCE_HEAD
        manifest_source = SOURCE_HEAD
    if not files:
        print("error: no files collected", file=sys.stderr)
        return 1
    clashing = sorted((GENERATED_NAMES | {BUNDLE_NAME}) & set(files))
    if clashing:
        print(f"error: repository root contains generated package names: {clashing}", file=sys.stderr)
        return 1
    bundle = create_bundle(repo)
    files[BUNDLE_NAME] = bundle

    manifest_bytes = build_source_manifest(files, commit, manifest_source)
    version_json = build_version_json(args.version, commit, built_utc, source, manifest_bytes,
                                      bundle)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    zip_path = out_dir / ZIP_NAME

    import zipfile

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"{ZIP_ROOT}/{VERSION_NAME}", version_json)
        zf.writestr(f"{ZIP_ROOT}/{MANIFEST_NAME}", manifest_bytes)
        for rel in sorted(files):
            zf.writestr(f"{ZIP_ROOT}/{rel}", files[rel])

    digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    sha_path = out_dir / (ZIP_NAME + ".sha256")
    sha_path.write_text(f"{digest}  {ZIP_NAME}\n", encoding="ascii")

    notes_path = out_dir / "RELEASE_NOTES.md"
    notes_path.write_text(
        build_release_notes(files, repo, args.version, commit, built_utc),
        encoding="utf-8",
    )

    problems = verify_zip(zip_path)
    size = zip_path.stat().st_size
    print(f"zip:    {zip_path}")
    print(f"size:   {size} bytes ({size / 1e6:.1f} MB)")
    print(f"sha256: {digest}")
    print(f"files:  {len(files)} (+ VERSION.json, SOURCE_MANIFEST.json), source: {source}")
    print(f"bundle: {BUNDLE_NAME} {len(bundle)} bytes, sha256 {hashlib.sha256(bundle).hexdigest()}, "
          f"head {commit}")
    print(f"manifest sha256: {hashlib.sha256(manifest_bytes).hexdigest()} ({manifest_source})")
    print(f"notes:  {notes_path}")
    if problems:
        for p in problems:
            print(f"self-verify FAILED: {p}", file=sys.stderr)
        return 2
    print("self-verify: OK (KURULUM.bat present with CRLF, no excluded paths, "
          "source manifest matches the zip bytes and VERSION.json, "
          f"{BUNDLE_NAME} matches VERSION.json and lists '{commit} HEAD')")
    return 0


if __name__ == "__main__":
    sys.exit(main())

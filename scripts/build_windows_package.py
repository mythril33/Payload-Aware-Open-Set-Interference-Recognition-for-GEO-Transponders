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
  plus ``VERSION.json`` and ``SOURCE_MANIFEST.json`` at the zip root folder.
* ``Payload-Aware-GEO-Workbench-Windows.zip.sha256`` — lowercase hex, two
  spaces, filename.
* ``RELEASE_NOTES.md`` — ``windows/SURUM_NOTLARI.md`` with a
  version/commit/date header prepended.

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
``VERSION.json`` must carry the manifest's sha256. The script exits nonzero
otherwise.
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
                       manifest_bytes: bytes) -> bytes:
    return (json.dumps(
        {
            "version": version,
            "commit": commit,
            "built_utc": built_utc,
            "source": source,
            "source_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        },
        indent=2,
    ) + "\n").encode("utf-8")


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
        f"- Built (UTC): {built_utc}\n\n"
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

        problems.extend(manifest_problems(
            payload, _root_member(MANIFEST_NAME), _root_member(VERSION_NAME)))
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
    commit = args.commit or run_git(repo, "rev-parse", "HEAD").decode().strip()
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
    clashing = sorted(GENERATED_NAMES & set(files))
    if clashing:
        print(f"error: repository root contains generated package names: {clashing}", file=sys.stderr)
        return 1

    manifest_bytes = build_source_manifest(files, commit, manifest_source)
    version_json = build_version_json(args.version, commit, built_utc, source, manifest_bytes)

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
    print(f"manifest sha256: {hashlib.sha256(manifest_bytes).hexdigest()} ({manifest_source})")
    print(f"notes:  {notes_path}")
    if problems:
        for p in problems:
            print(f"self-verify FAILED: {p}", file=sys.stderr)
        return 2
    print("self-verify: OK (KURULUM.bat present with CRLF, no excluded paths, "
          "source manifest matches the zip bytes and VERSION.json)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

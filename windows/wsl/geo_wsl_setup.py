#!/usr/bin/env python3
"""WSL-side bootstrap for the GEO Workbench package (stdlib only, Python >= 3.10).

Run by the distro's system ``python3`` from ``windows/setup_wsl_backend.ps1``,
before any virtual environment exists, so it must not import ``geodash``.

Subcommands
-----------
``verify --root DIR [--expect-commit SHA] [--expect-manifest-sha256 HEX] [--json]``
    Verify a tree against its ``SOURCE_MANIFEST.json`` with the package-snapshot
    rules of ``geodash.pilot.source_identity``: every listed file exists and
    matches its sha256; no unlisted file under ``src/``, ``scripts/``,
    ``configs/`` or ``dashboard/`` (``__pycache__``, ``*.pyc`` and the
    ``*.egg-info`` metadata written by ``pip install -e`` are ignored); the
    manifest source is ``git archive HEAD``. Exit 0 verified, 20 not verified.
``install --from PKGDIR [--to DEST] [--replace] [--json]``
    Verify PKGDIR, copy exactly the listed files plus ``SOURCE_MANIFEST.json``
    and ``VERSION.json`` into a fresh DEST (default ``~/geo-workbench-src``) and
    re-verify it. An existing DEST is never deleted: without ``--replace`` the
    command exits 13; with it DEST is moved to ``DEST.previous-<UTC ts>``.
    DEST under ``/mnt/`` (a Windows drive, not WSL ext4) is refused with 14.
``venv [--src DEST] [--json]``
    Create ``DEST/.venv`` with ``python3 -m venv`` (exit 15 when that fails,
    e.g. ensurepip missing: install ``python3-venv``; nothing is downloaded to
    replace it), then pip-install CPU torch (PyTorch CPU index first, PyPI
    ``torch>=2.2`` only as a warned fallback), ``-e DEST[dev,ml]`` and
    ``dashboard/requirements.txt``. Exit 0, or 16 when pip fails.

``--json`` prints exactly one ASCII JSON line on stdout; subprocess output goes
to stderr. No command runs through a shell.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

MANIFEST_NAME = "SOURCE_MANIFEST.json"
VERSION_NAME = "VERSION.json"
MANIFEST_SCHEMA = "GEO-workbench-source-manifest/1"
REQUIRED_SOURCE = "git archive HEAD"
SCANNED_DIRS = ("src", "scripts", "configs", "dashboard")
DEFAULT_DEST = "~/geo-workbench-src"
MNT_ROOT = Path("/mnt")
LIMITATIONS = (
    "Integrity is relative to the CI-built package manifest (SOURCE_MANIFEST.json); "
    "a package snapshot has no Git history; this is not a production lock."
)

TORCH_CPU_SPEC = "torch==2.14.1+cpu"
TORCH_CPU_INDEX = "https://download.pytorch.org/whl/cpu"
TORCH_FALLBACK_SPEC = "torch>=2.2"
VENV_PACKAGE_HINT = "sudo apt-get install -y python3-venv"

EXIT_OK = 0
EXIT_EXISTS = 13
EXIT_DEST_REFUSED = 14
EXIT_VENV_UNAVAILABLE = 15
EXIT_PIP_FAILED = 16
EXIT_NOT_VERIFIED = 20
EXIT_PYTHON_TOO_OLD = 2
CODE_NAMES = {
    EXIT_OK: "OK",
    EXIT_EXISTS: "EXISTS",
    EXIT_DEST_REFUSED: "DEST_REFUSED",
    EXIT_VENV_UNAVAILABLE: "VENV_UNAVAILABLE",
    EXIT_PIP_FAILED: "PIP_FAILED",
    EXIT_NOT_VERIFIED: "NOT_VERIFIED",
}

RunResult = collections.namedtuple("RunResult", ["returncode", "output"])


# ---- verification ------------------------------------------------------------------------------------

def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def is_ignored(rel_posix: str) -> bool:
    """Generated, gitignored by-products that may appear under the scanned dirs after use."""
    parts = rel_posix.split("/")
    if any(part == "__pycache__" or part.endswith(".egg-info") for part in parts[:-1]):
        return True
    return parts[-1].endswith(".pyc")


def is_safe_rel(rel: object) -> bool:
    if not isinstance(rel, str) or not rel or rel.startswith("/") or "\\" in rel or ":" in rel:
        return False
    return all(part not in ("", ".", "..") for part in rel.split("/"))


def _is_hex64(value: object) -> bool:
    return (isinstance(value, str) and len(value) == 64
            and all(c in "0123456789abcdef" for c in value))


def load_manifest(root: Path) -> tuple[dict | None, bytes | None, list[str]]:
    path = root / MANIFEST_NAME
    if path.is_symlink() or not path.is_file():
        return None, None, [f"missing {MANIFEST_NAME}"]
    raw = path.read_bytes()
    try:
        manifest = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        return None, raw, [f"{MANIFEST_NAME} is not readable JSON: {exc}"]
    if not isinstance(manifest, dict):
        return None, raw, [f"{MANIFEST_NAME} is not a JSON object"]
    return manifest, raw, []


def unexpected_files(root: Path, listed: set[str]) -> list[str]:
    found: list[str] = []
    for top in SCANNED_DIRS:
        top_path = root / top
        if top_path.is_symlink():
            found.append(top)
            continue
        if not top_path.is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(top_path, followlinks=False):
            base = Path(dirpath).relative_to(root).as_posix()
            for name in list(dirnames):
                if (Path(dirpath) / name).is_symlink():
                    found.append(f"{base}/{name}")
            for name in filenames:
                rel = f"{base}/{name}"
                if rel not in listed and not is_ignored(rel):
                    found.append(rel)
    return sorted(found)


def verify_tree(root: Path | str, expect_commit: str | None = None,
                expect_manifest_sha256: str | None = None) -> dict:
    root = Path(root)
    result = {
        "root": str(root),
        "verified": False,
        "commit": None,
        "source": None,
        "manifest_sha256": None,
        "files": 0,
        "problems": [],
        "limitations": LIMITATIONS,
    }
    problems: list[str] = result["problems"]
    if not root.is_dir():
        problems.append(f"not a directory: {root}")
        return result
    manifest, raw, load_problems = load_manifest(root)
    if raw is not None:
        result["manifest_sha256"] = hashlib.sha256(raw).hexdigest()
    if manifest is None:
        problems.extend(load_problems)
        return result

    if manifest.get("schema") != MANIFEST_SCHEMA:
        problems.append(f"manifest schema is {manifest.get('schema')!r}, expected {MANIFEST_SCHEMA!r}")
    commit = manifest.get("commit")
    result["commit"] = commit if isinstance(commit, str) else None
    if not result["commit"]:
        problems.append("manifest has no commit")
    source = manifest.get("source")
    result["source"] = source if isinstance(source, str) else None
    if source != REQUIRED_SOURCE:
        problems.append(f"manifest source is {source!r}, expected {REQUIRED_SOURCE!r}")
    if expect_commit is not None and commit != expect_commit:
        problems.append(f"commit mismatch: manifest {commit!r}, expected {expect_commit!r}")
    if expect_manifest_sha256 is not None and result["manifest_sha256"] != expect_manifest_sha256.lower():
        problems.append(f"manifest sha256 mismatch: {result['manifest_sha256']}, "
                        f"expected {expect_manifest_sha256}")

    files = manifest.get("files")
    if not isinstance(files, dict) or not files:
        problems.append("manifest has no files mapping")
        files = {}
    result["files"] = len(files)
    for rel in sorted(files):
        digest = files[rel]
        if not is_safe_rel(rel) or rel in (MANIFEST_NAME, VERSION_NAME):
            problems.append(f"unsafe manifest path: {rel!r}")
            continue
        if not _is_hex64(digest):
            problems.append(f"malformed manifest hash: {rel}")
            continue
        path = root / rel
        if path.is_symlink() or (path.exists() and not path.is_file()):
            problems.append(f"not a regular file: {rel}")
        elif not path.exists():
            problems.append(f"missing file: {rel}")
        elif sha256_file(path) != digest:
            problems.append(f"hash mismatch: {rel}")
    for rel in unexpected_files(root, set(files)):
        problems.append(f"unexpected file: {rel}")

    version_path = root / VERSION_NAME
    if version_path.is_file() and not version_path.is_symlink():
        try:
            version = json.loads(version_path.read_bytes().decode("utf-8"))
            recorded = version.get("source_manifest_sha256") if isinstance(version, dict) else None
        except (UnicodeDecodeError, ValueError):
            recorded = None
            problems.append(f"{VERSION_NAME} is not readable JSON")
        if recorded is not None and recorded != result["manifest_sha256"]:
            problems.append(f"{VERSION_NAME} source_manifest_sha256 does not match {MANIFEST_NAME}")

    result["verified"] = not problems
    return result


# ---- install -----------------------------------------------------------------------------------------

def _outcome(command: str, exit_code: int, message: str, **extra) -> dict:
    out = {"command": command, "exit_code": exit_code, "code": CODE_NAMES[exit_code],
           "ok": exit_code == EXIT_OK, "message": message}
    out.update(extra)
    return out


def _utc_stamp(now=None) -> str:
    moment = now() if now is not None else datetime.now(timezone.utc)
    return moment.strftime("%Y%m%dT%H%M%SZ")


def _unused(path: Path) -> Path:
    candidate, n = path, 0
    while os.path.lexists(candidate):
        n += 1
        candidate = path.with_name(f"{path.name}-{n}")
    return candidate


def _within(path: Path, ancestor: Path) -> bool:
    return path == ancestor or ancestor in path.parents


def under_mnt(dest: Path) -> bool:
    candidates = {Path(os.path.abspath(dest)), dest.resolve()}
    roots = {Path(os.path.abspath(MNT_ROOT)), MNT_ROOT.resolve()}
    return any(_within(c, r) for c in candidates for r in roots)


def install(pkg: Path | str, dest: Path | str = DEFAULT_DEST, *, replace: bool = False,
            now=None) -> dict:
    pkg = Path(pkg).expanduser()
    dest = Path(dest).expanduser()
    if under_mnt(dest):
        return _outcome("install", EXIT_DEST_REFUSED,
                        f"DEST {dest} is under {MNT_ROOT}/ (a Windows drive); install into the WSL "
                        f"ext4 home instead, e.g. {DEFAULT_DEST}", dest=str(dest))
    pkg_real, dest_real = pkg.resolve(), dest.resolve()
    if _within(pkg_real, dest_real) or _within(dest_real, pkg_real):
        return _outcome("install", EXIT_DEST_REFUSED,
                        "DEST and the package directory must not contain each other", dest=str(dest))

    check = verify_tree(pkg)
    if not check["verified"]:
        return _outcome("install", EXIT_NOT_VERIFIED, f"package {pkg} is not verified",
                        package=check, dest=str(dest))
    if os.path.lexists(dest) and not replace:
        existing = verify_tree(dest)
        return _outcome("install", EXIT_EXISTS,
                        f"DEST {dest} already exists; rerun with --replace to move it aside",
                        dest=str(dest), existing_commit=existing["commit"],
                        existing_verified=existing["verified"], package=check)

    stamp = _utc_stamp(now)
    dest.parent.mkdir(parents=True, exist_ok=True)
    staging = _unused(dest.with_name(f".{dest.name}.installing-{stamp}"))
    manifest, _, _ = load_manifest(pkg)
    names = sorted(manifest["files"]) + [MANIFEST_NAME]
    if (pkg / VERSION_NAME).is_file():
        names.append(VERSION_NAME)
    for rel in names:
        target = staging / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(pkg / rel, target)
    staged = verify_tree(staging, expect_commit=check["commit"],
                         expect_manifest_sha256=check["manifest_sha256"])
    if not staged["verified"]:
        return _outcome("install", EXIT_NOT_VERIFIED,
                        f"the copied tree did not verify; it is kept for inspection at {staging}",
                        dest=str(dest), staging=str(staging), installed=staged)

    previous = None
    if os.path.lexists(dest):
        previous = _unused(dest.with_name(f"{dest.name}.previous-{stamp}"))
        os.rename(dest, previous)
    os.rename(staging, dest)
    final = verify_tree(dest, expect_commit=check["commit"],
                        expect_manifest_sha256=check["manifest_sha256"])
    if not final["verified"]:
        return _outcome("install", EXIT_NOT_VERIFIED, f"installed tree {dest} did not re-verify",
                        dest=str(dest), previous=str(previous) if previous else None, installed=final)
    return _outcome("install", EXIT_OK, f"installed commit {final['commit']} into {dest}",
                    dest=str(dest), previous=str(previous) if previous else None,
                    commit=final["commit"], manifest_sha256=final["manifest_sha256"],
                    files=final["files"])


# ---- venv --------------------------------------------------------------------------------------------

def run_streaming(argv: list[str]) -> RunResult:
    """Run ``argv`` (no shell), echo its combined output to stderr, keep the tail."""
    tail: collections.deque = collections.deque(maxlen=400)
    try:
        proc = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                                errors="replace")
    except OSError as exc:
        return RunResult(127, f"could not start {argv[0]}: {exc}")
    assert proc.stdout is not None
    for line in proc.stdout:
        sys.stderr.write(line)
        tail.append(line)
    sys.stderr.flush()
    return RunResult(proc.wait(), "".join(tail))


def venv_python(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def setup_venv(src: Path | str = DEFAULT_DEST, *, runner=None, python: str | None = None) -> dict:
    src = Path(os.path.abspath(Path(src).expanduser()))
    runner = runner or run_streaming
    python = python or sys.executable
    steps: list[dict] = []
    warnings: list[str] = []

    def step(argv: list[str]) -> RunResult:
        res = runner(argv)
        steps.append({"argv": argv, "returncode": res.returncode})
        return res

    check = verify_tree(src)
    if not check["verified"]:
        return _outcome("venv", EXIT_NOT_VERIFIED, f"source tree {src} is not verified",
                        tree=check, steps=steps)

    venv_dir = src / ".venv"
    created = step([python, "-m", "venv", str(venv_dir)])
    vpy = venv_python(venv_dir)
    if created.returncode != 0 or not vpy.exists():
        ensurepip_missing = "ensurepip" in (created.output or "").lower()
        reason = ("ensurepip is not available" if ensurepip_missing
                  else f"python3 -m venv failed (exit {created.returncode})")
        return _outcome("venv", EXIT_VENV_UNAVAILABLE,
                        f"could not create {venv_dir}: {reason}. Install the distro venv package "
                        f"and retry: {VENV_PACKAGE_HINT}",
                        ensurepip_missing=ensurepip_missing, install_hint=VENV_PACKAGE_HINT,
                        steps=steps)

    pip = [str(vpy), "-m", "pip", "install"]
    torch = step(pip + [TORCH_CPU_SPEC, "--index-url", TORCH_CPU_INDEX])
    if torch.returncode != 0:
        warning = (f"warning: the PyTorch CPU index install of {TORCH_CPU_SPEC} failed; falling back "
                   f"to PyPI {TORCH_FALLBACK_SPEC}. The PyPI Linux wheel is large (it pulls CUDA "
                   "libraries, several GB); training stays CPU-only.")
        print(warning, file=sys.stderr, flush=True)
        warnings.append(warning)
        torch = step(pip + [TORCH_FALLBACK_SPEC])
        if torch.returncode != 0:
            return _outcome("venv", EXIT_PIP_FAILED, "pip could not install torch",
                            steps=steps, warnings=warnings)
    for argv, what in (
        (pip + ["-e", f"{src}[dev,ml]"], "the geosim/geoml editable install"),
        (pip + ["-r", str(src / "dashboard" / "requirements.txt")], "the dashboard requirements"),
    ):
        if step(argv).returncode != 0:
            return _outcome("venv", EXIT_PIP_FAILED, f"pip failed on {what}",
                            steps=steps, warnings=warnings)
    return _outcome("venv", EXIT_OK, f"virtual environment ready at {venv_dir}",
                    venv=str(venv_dir), python=str(vpy), steps=steps, warnings=warnings)


# ---- CLI ---------------------------------------------------------------------------------------------

def _emit(result: dict, as_json: bool) -> int:
    if as_json:
        print(json.dumps(result, ensure_ascii=True, allow_nan=False, sort_keys=True), flush=True)
        return result["exit_code"]
    status = "OK" if result["exit_code"] == EXIT_OK else f"ERROR [{result['code']}]"
    print(f"{status}: {result['message']}")
    nested = result if result["command"] == "verify" else (
        result.get("installed") or result.get("package") or result.get("tree") or {})
    for problem in nested.get("problems", []):
        print(f"  - {problem}")
    return result["exit_code"]


def main(argv: list[str] | None = None) -> int:
    if sys.version_info < (3, 10):
        print("error: geo_wsl_setup.py needs Python >= 3.10", file=sys.stderr)
        return EXIT_PYTHON_TOO_OLD
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    p_verify = sub.add_parser("verify", help="verify a tree against its SOURCE_MANIFEST.json")
    p_verify.add_argument("--root", required=True)
    p_verify.add_argument("--expect-commit", default=None)
    p_verify.add_argument("--expect-manifest-sha256", default=None)
    p_verify.add_argument("--json", action="store_true")

    p_install = sub.add_parser("install", help="install a verified package into WSL ext4")
    p_install.add_argument("--from", dest="pkg", required=True)
    p_install.add_argument("--to", dest="dest", default=DEFAULT_DEST)
    p_install.add_argument("--replace", action="store_true")
    p_install.add_argument("--json", action="store_true")

    p_venv = sub.add_parser("venv", help="create DEST/.venv and install the CPU dependencies")
    p_venv.add_argument("--src", default=DEFAULT_DEST)
    p_venv.add_argument("--json", action="store_true")

    args = parser.parse_args(argv)
    if args.command == "verify":
        check = verify_tree(args.root, args.expect_commit, args.expect_manifest_sha256)
        code = EXIT_OK if check["verified"] else EXIT_NOT_VERIFIED
        message = (f"verified commit {check['commit']}" if check["verified"]
                   else f"{args.root} is not verified")
        result = _outcome("verify", code, message, **check)
    elif args.command == "install":
        result = install(args.pkg, args.dest, replace=args.replace)
    else:
        result = setup_venv(args.src)
    return _emit(result, args.json)


if __name__ == "__main__":
    sys.exit(main())

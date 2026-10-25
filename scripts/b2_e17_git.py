"""Read-only E17 Git-object lineage evidence; never an execution permission.

Only literal SHA-1 object IDs are accepted. Replacement/graft/alternate/shallow
histories and linked worktrees are refused. Object bytes are rehashed before use;
Git's textual signature or author claims are not treated as authentication here.
The caller must supply independently reviewed ``reviewed`` and approval IDs.
"""
from __future__ import annotations

import configparser
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import stat
import subprocess
import time

GIT = "/usr/bin/git"
MAX_BYTES = 8 * 2**20
MAX_PATHS = 10000
MAX_DEPTH = 40
TIMEOUT = 15
SHA = re.compile(r"[0-9a-f]{40}\Z")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
GATES_PATH = "docs/plan/b2_readiness_gates_2026-10-21.json"
MEMO_PATH = "docs/plan/b2_e5_decision_recommendations.json"
LOCK_CONFIGS = ("configs/b2_base.json", "configs/cancellation.json", "configs/b2_feat.json", "pyproject.toml", GATES_PATH)
SCIENCE_RECORDS = frozenset({
    "docs/plan/P18_b2_protocol.md", "docs/plan/b2_e9_approved_scientific_protocol.json",
    "docs/plan/B2_E9_SCIENTIFIC_DECISION_APPROVAL_2026-10-24.md",
    "docs/plan/B2_E12_D1_D8_SCIENTIFIC_APPROVAL_2026-10-24.md",
    "docs/plan/b2_e12_d1_d8_decisions_2026-10-24.json",
    "docs/results/b2_e10_k17d_identity.json", "docs/results/k17d_drift_audit.json",
})


class GitEvidenceError(ValueError):
    pass


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def _sha(value):
    if not isinstance(value, str) or not SHA.fullmatch(value):
        raise GitEvidenceError("literal 40-hex Git object ID required")
    return value


def _path(value):
    if (not isinstance(value, str) or not value or len(value) > 1024 or "\\" in value
            or value.startswith("/") or any(ord(c) < 32 or ord(c) == 127 for c in value)
            or any(c in ("", ".", "..") for c in value.split("/"))):
        raise GitEvidenceError("unsafe repository-relative path")
    return value


def _regular(path, maximum=MAX_BYTES):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > maximum:
            raise GitEvidenceError("not a bounded unique regular file")
        chunks, size = [], 0
        while True:
            chunk = os.read(fd, min(65536, maximum + 1 - size))
            if not chunk:
                break
            chunks.append(chunk)
            size += len(chunk)
            if size > maximum:
                raise GitEvidenceError("file exceeds bound")
        after = os.fstat(fd)
        fields = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns, s.st_nlink)
        if fields(before) != fields(after):
            raise GitEvidenceError("file changed during read")
        return b"".join(chunks)
    finally:
        os.close(fd)


def _repo(value):
    root = Path(value).absolute()
    if ".." in root.parts or root.resolve() != root or not root.is_dir():
        raise GitEvidenceError("repository path aliases or traversal refused")
    gitdir = root / ".git"
    if gitdir.is_symlink() or not gitdir.is_dir():
        raise GitEvidenceError("ordinary repository .git directory required")
    for name in ("commondir", "shallow", "info/grafts", "objects/info/alternates", "objects/info/http-alternates"):
        if os.path.lexists(gitdir / name):
            raise GitEvidenceError("alternate, grafted, shallow or linked history refused")
    for name in ("objects", "refs"):
        path = gitdir / name
        if path.resolve() != path:
            raise GitEvidenceError("Git database alias refused")
    parser = configparser.RawConfigParser(strict=True)
    parser.read_string(_regular(gitdir / "config", 65536).decode())
    for section in parser.sections():
        lower = section.lower()
        if lower.startswith(("include", "filter ", "diff ")) or lower in {"include", "extensions"}:
            raise GitEvidenceError("unsupported local Git configuration indirection")
        if lower == "core" and any(key in parser[section] for key in ("worktree", "gitproxy", "sshcommand")):
            raise GitEvidenceError("local Git worktree or command override refused")
    return root


def _run(repo, *arguments):
    """Read-only fixed-tool invocation with bounded output/time and a fresh env."""
    environment = {"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C", "GIT_CONFIG_NOSYSTEM": "1",
                   "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_NO_REPLACE_OBJECTS": "1", "GIT_OPTIONAL_LOCKS": "0",
                   "GIT_TERMINAL_PROMPT": "0", "GIT_ATTR_NOSYSTEM": "1"}
    command = [GIT, "--no-replace-objects", "-c", "core.fsmonitor=false", "-c", "core.hooksPath=/dev/null",
               "-c", "core.attributesFile=/dev/null", "-c", "protocol.allow=never", *arguments]
    process = subprocess.Popen(command, cwd=repo, env=environment, stdin=subprocess.DEVNULL,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=False)
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    pieces, count, deadline = [], 0, time.monotonic() + TIMEOUT
    try:
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise GitEvidenceError("Git read timed out")
            for key, _ in selector.select(remaining):
                raw = os.read(key.fd, min(65536, MAX_BYTES + 1 - count))
                if not raw:
                    selector.unregister(key.fileobj)
                    continue
                pieces.append(raw)
                count += len(raw)
                if count > MAX_BYTES:
                    raise GitEvidenceError("Git output exceeds bound")
        if process.wait(timeout=max(0.001, deadline - time.monotonic())) != 0:
            raise GitEvidenceError("Git object/read command failed")
        return b"".join(pieces)
    finally:
        selector.close()
        if process.poll() is None:
            process.kill()
        process.wait()
        process.stdout.close()


def _object(repo, oid, kind):
    _sha(oid)
    if _run(repo, "cat-file", "-t", oid).strip() != kind.encode():
        raise GitEvidenceError("unexpected Git object type")
    size = int(_run(repo, "cat-file", "-s", oid))
    if not 0 <= size <= MAX_BYTES:
        raise GitEvidenceError("Git object exceeds bound")
    raw = _run(repo, "cat-file", kind, oid)
    actual = hashlib.sha1(kind.encode() + b" " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
    if len(raw) != size or actual != oid:
        raise GitEvidenceError("Git object content does not match exact object ID")
    return raw


def _commit(repo, oid):
    raw = _object(repo, oid, "commit")
    headers = raw.split(b"\n\n", 1)[0].splitlines()
    trees = [line[5:].decode("ascii") for line in headers if line.startswith(b"tree ")]
    parents = [line[7:].decode("ascii") for line in headers if line.startswith(b"parent ")]
    if len(trees) != 1:
        raise GitEvidenceError("malformed commit tree")
    return _sha(trees[0]), [_sha(parent) for parent in parents]


def _entries(repo, commit):
    tree, _ = _commit(repo, commit)
    pending, result, entry_count = [(tree, "", 0)], {}, 0
    while pending:
        oid, prefix, depth = pending.pop()
        if depth > MAX_DEPTH:
            raise GitEvidenceError("tree exceeds depth bound")
        raw, position = _object(repo, oid, "tree"), 0
        names = set()
        while position < len(raw):
            delimiter = raw.find(b"\0", position)
            if delimiter < 0 or delimiter + 21 > len(raw):
                raise GitEvidenceError("malformed Git tree")
            mode, name = raw[position:delimiter].split(b" ", 1)
            text = name.decode("utf-8", errors="strict")
            if "/" in text or text in names:
                raise GitEvidenceError("malformed or duplicate tree path")
            names.add(text)
            path = _path(prefix + text)
            entry_count += 1
            if entry_count > MAX_PATHS:
                raise GitEvidenceError("tree exceeds entry bound (including directories)")
            child = raw[delimiter + 1:delimiter + 21].hex()
            position = delimiter + 21
            if mode == b"40000":
                pending.append((child, path + "/", depth + 1))
            elif mode in (b"100644", b"100755"):
                result[path] = (mode.decode(), child)
                if len(result) > MAX_PATHS:
                    raise GitEvidenceError("tree exceeds path bound")
            else:
                raise GitEvidenceError("symlink, submodule or unsupported tree mode refused")
    return result


def read_blob(repo, commit, path):
    """Read exact committed regular-file bytes without checkout or filtering."""
    root, commit, path = _repo(repo), _sha(commit), _path(path)
    _history(root)
    entries = _entries(root, commit)
    if path not in entries or entries[path][0] != "100644":
        raise GitEvidenceError("record is absent or not a regular non-executable blob")
    return _object(root, entries[path][1], "blob")


def _history(repo):
    if _run(repo, "for-each-ref", "--format=%(refname)", "refs/replace").strip():
        raise GitEvidenceError("replacement history refused")


def _clean(repo, approval):
    if _run(repo, "rev-parse", "--verify", "HEAD").strip().decode() != approval:
        raise GitEvidenceError("checkout HEAD is not the exact approval commit")
    if _run(repo, "status", "--porcelain=v1", "-z", "--untracked-files=all", "--ignore-submodules=all"):
        raise GitEvidenceError("repository is not clean")
    # These index flags can conceal worktree changes from porcelain status.
    flags = _run(repo, "ls-files", "-v", "-z").split(b"\0")
    if any(entry and entry[:2] != b"H " for entry in flags):
        raise GitEvidenceError("index skip-worktree or assume-unchanged flags refused")
    # Porcelain omits ignored paths. Do not let an untracked importable or an
    # ignored alternate config ride along. Python bytecode is executable: even
    # a timestamp-valid __pycache__ entry can override unchanged source bytes.
    # Evidence verification requires a cache-free source checkout; it never
    # removes caches itself. Only inert test/build metadata may be present.
    untracked = _run(repo, "ls-files", "--others", "-z").split(b"\0")
    metadata = re.compile(r"src/[^/]+\.egg-info/(PKG-INFO|SOURCES\.txt|dependency_links\.txt|requires\.txt|top_level\.txt)\Z")
    for raw in untracked:
        if not raw:
            continue
        path = raw.decode("utf-8", errors="strict")
        if path.startswith(".pytest_cache/") or metadata.fullmatch(path):
            continue
        raise GitEvidenceError("untracked or ignored non-cache repository content refused")


def verify_checkout(repo, commit, expected_sha256):
    """Bind a closed-gate report to a clean exact checkout, without an approval.

    This is a read-only snapshot check, not an authorization or a substitute for
    approval lineage. The caller must compare the parsed authoritative documents
    with its reference and supply their exact committed byte hashes here.
    """
    result = {"schema": "B2-E17-checkout/1", "ok": False, "status": "DENIED",
              "failures": [], "execution_permitted": False, "authorizes_nothing": True}
    try:
        root, commit = _repo(repo), _sha(commit)
        if type(expected_sha256) is not dict or not 0 < len(expected_sha256) <= 20:
            raise GitEvidenceError("bounded expected document hashes required")
        for path, digest in expected_sha256.items():
            _path(path)
            if type(digest) is not str or not SHA256.fullmatch(digest):
                raise GitEvidenceError("malformed document hash")
        _history(root)
        _clean(root, commit)
        entries = _entries(root, commit)
        for path, digest in expected_sha256.items():
            if path not in entries or entries[path][0] != "100644":
                raise GitEvidenceError("document absent or unsafe mode")
            if hashlib.sha256(_object(root, entries[path][1], "blob")).hexdigest() != digest:
                raise GitEvidenceError("document differs from exact committed bytes")
        _live_matches(root, expected_sha256)
        _clean(root, commit)
        _history(root)
        _repo(root)
        _live_matches(root, expected_sha256)
        result.update(ok=True, status="VERIFIED_CHECKOUT_NOT_AUTHORITY", commit=commit)
    except Exception as error:
        result["failures"].append("Checkout refused: " + type(error).__name__ + ": " + str(error)[:200])
    return result


def _maps(repo, entries):
    source, configs, tools = {}, {}, {}
    for path, (_, oid) in entries.items():
        is_source = path.startswith("src/") and (path.endswith(".py") or path.startswith("src/geosim/data/"))
        if is_source or path in LOCK_CONFIGS or path.startswith("scripts/") and path.endswith(".py"):
            value = hashlib.sha256(_object(repo, oid, "blob")).hexdigest()
            if is_source:
                source[path] = value
            if path in LOCK_CONFIGS:
                configs[path] = value
            if path.startswith("scripts/") and path.endswith(".py"):
                tools[path] = value
    return source, configs, tools


def _live_matches(repo, hashes):
    for path, expected in hashes.items():
        target = repo / path
        if target.resolve() != target or hashlib.sha256(_regular(target)).hexdigest() != expected:
            raise GitEvidenceError("working-tree source or record differs from exact committed bytes")


def _lock(lock, commit, source, configs):
    keys = {"schema", "benchmark_complete", "git", "source_sha256", "generator_provenance", "generator_provenance_fingerprint",
            "configs_sha256", "parsed", "environment", "production", "lock_fingerprint"}
    if not isinstance(lock, dict) or set(lock) != keys or lock["schema"] != "B2-production-lock/1" or lock["benchmark_complete"] is not False:
        raise GitEvidenceError("unexpected production lock schema")
    if lock["lock_fingerprint"] != _digest({k: v for k, v in lock.items() if k != "lock_fingerprint"}):
        raise GitEvidenceError("modified lock fingerprint")
    git = lock["git"]
    if not isinstance(git, dict) or set(git) != {"commit", "branch", "clean"} or git["commit"] != commit or git["clean"] is not True:
        raise GitEvidenceError("lock commit/clean identity mismatch")
    if lock["source_sha256"] != source or lock["configs_sha256"] != configs:
        raise GitEvidenceError("lock source/config identity mismatch")
    generator = {k.removeprefix("src/geosim/"): v for k, v in source.items() if k.startswith("src/geosim/")}
    if lock["generator_provenance"] != generator or lock["generator_provenance_fingerprint"] != _digest(generator):
        raise GitEvidenceError("lock generator identity mismatch")


def verify_lineage(repo, reviewed, approval, record_path, *, expected_record_sha256=None, lock=None):
    """Require an exact clean, direct-child approval changing three metadata files.

    E6 lock comparison covers commit/source/config/generator identity and its own
    fingerprint. Current environment/parsed physics still require the existing E13
    lock verifier; no environment assertion is manufactured by this adapter.
    """
    result = {"schema": "B2-E17-Git-lineage/1", "ok": False, "status": "DENIED", "is_ancestor": False,
              "changed_paths": [], "record_sha256": None, "reviewed_commit": None, "approval_commit": None,
              "source_sha256": {}, "configs_sha256": {}, "tools_sha256": {}, "lock_checked": False,
              "failures": [], "execution_permitted": False, "authorizes_nothing": True}
    try:
        root, reviewed, approval, record_path = _repo(repo), _sha(reviewed), _sha(approval), _path(record_path)
        root_identity = (root.stat().st_dev, root.stat().st_ino, (root / ".git").stat().st_dev, (root / ".git").stat().st_ino)
        if not record_path.startswith("docs/") or record_path in SCIENCE_RECORDS or record_path in (GATES_PATH, MEMO_PATH):
            raise GitEvidenceError("record must be a distinct non-scientific docs record")
        if expected_record_sha256 is not None and (not isinstance(expected_record_sha256, str) or not SHA256.fullmatch(expected_record_sha256)):
            raise GitEvidenceError("record SHA-256 malformed")
        _history(root)
        _clean(root, approval)
        _, parents = _commit(root, approval)
        if reviewed == approval or parents != [reviewed]:
            raise GitEvidenceError("approval must be a direct single-parent child of reviewed commit")
        before, after = _entries(root, reviewed), _entries(root, approval)
        if record_path in before:
            raise GitEvidenceError("approval record must be new; historical documents cannot be overwritten")
        changed = sorted(path for path in set(before) | set(after) if before.get(path) != after.get(path))
        if set(changed) != {GATES_PATH, MEMO_PATH, record_path}:
            raise GitEvidenceError("changed paths differ from the strict gate/memorandum/record allowlist")
        for path in (GATES_PATH, MEMO_PATH):
            if path not in before or path not in after or before[path][0] != after[path][0] or after[path][0] != "100644":
                raise GitEvidenceError("gate or memorandum was deleted or changed type/mode")
        if record_path not in after or after[record_path][0] != "100644":
            raise GitEvidenceError("approval record must be a regular non-executable file")
        record = _object(root, after[record_path][1], "blob")
        actual_hash = hashlib.sha256(record).hexdigest()
        if expected_record_sha256 is not None and expected_record_sha256 != actual_hash:
            raise GitEvidenceError("committed record bytes differ from expected SHA-256")
        source, configs, tools = _maps(root, after)
        live = {**source, **configs, **tools, record_path: actual_hash}
        for path in (GATES_PATH, MEMO_PATH):
            live[path] = hashlib.sha256(_object(root, after[path][1], "blob")).hexdigest()
        _live_matches(root, live)
        if lock is not None:
            _lock(lock, approval, source, configs)
        _clean(root, approval)
        _history(root)
        # Check policy files again to detect concurrent repository indirection.
        _repo(root)
        if root_identity != (root.stat().st_dev, root.stat().st_ino, (root / ".git").stat().st_dev, (root / ".git").stat().st_ino):
            raise GitEvidenceError("repository namespace changed during verification")
        _live_matches(root, live)
        result.update(ok=True, status="VERIFIED_LINEAGE_NOT_AUTHORITY", is_ancestor=True, changed_paths=changed,
                      record_sha256=actual_hash, reviewed_commit=reviewed, approval_commit=approval,
                      source_sha256=source, configs_sha256=configs, tools_sha256=tools, lock_checked=lock is not None)
    except (Exception, RecursionError) as error:
        result["failures"].append("Git evidence refused: " + type(error).__name__ + ": " + str(error)[:200])
    canonical(result)
    return result

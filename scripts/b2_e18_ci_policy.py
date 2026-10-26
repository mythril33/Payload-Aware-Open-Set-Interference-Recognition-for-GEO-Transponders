#!/usr/bin/env python3
"""E18 CI/provenance policy: classify repository changes, lint workflows and decide what a green CI may mean.

Pure functions plus a small CLI. Nothing here authorizes, launches or edits anything. Three questions are kept apart:

* **Scope** (``check-diff``): which paths may a milestone branch touch? The comparison base is the PR's merge base (the *current
  reviewed* tree), never a frozen historical snapshot, so a legitimate earlier-merged change is not an "alteration" of history
  while a change to a frozen scientific record, a canonical gate, a historical dossier or a reviewed contract module still fails.
* **Workflow hygiene** (``lint``): a text-level tripwire against widening permissions, secrets, a self-hosted runner, third-party
  actions, or calling a generator, trainer, production supervisor or GPU, and against dropping the E18 guard steps by accident.
  It is not a proof (variables and here-documents can defeat a line scan), and it cannot protect the workflow that runs it: a pull
  request that rewrites the workflow rewrites what executes on that pull request. That protection can only come from repository
  settings (required reviews, rulesets or CODEOWNERS on ``.github/workflows``), which no script here can configure or verify.
* **Gate state** (``gate-decision``): the real gates are CLOSED_CANONICAL and that is the only state this build accepts. The
  matrix for an eventual DR-04-approved state is written down and tested here, but an approved-shaped gate can never pass CI
  without trusted evidence under a *production* trust root, which does not exist today.
"""
from __future__ import annotations

import argparse
from fnmatch import fnmatchcase
import json
from pathlib import Path
import re
import subprocess
import sys

SCHEMA_DIFF = "B2-E18-ci-diff-report/1"
SCHEMA_LINT = "B2-E18-workflow-lint/1"
SCHEMA_GATE = "B2-E18-ci-gate-decision/1"
NO_AUTHORITY = {"verdict": "NO-GO", "execution_permitted": False, "authorizes_nothing": True, "production_launch_enabled": False}

# Frozen scientific, physics and approval records: a milestone branch never changes these (E15/E16/E17 protect the same set).
FROZEN_SCIENCE = (
    "configs/*", "pyproject.toml", "src/*",
    "docs/plan/P18_b2_protocol.md", "docs/plan/P19_b2_base_observations.md", "docs/plan/P20_b2_cancellation_residual.md",
    "docs/plan/P21_b2_test_families.md", "docs/plan/P21_b2_observed_receiver.md", "docs/plan/P22_b2_matched_asi.md",
    "docs/plan/P31_b2_e7b_isolated_execution.md",
    "docs/plan/b2_e9_approved_scientific_protocol.json", "docs/plan/B2_E9_SCIENTIFIC_DECISION_APPROVAL_2026-10-24.md",
    "docs/plan/B2_E12_D1_D8_SCIENTIFIC_APPROVAL_2026-10-24.md", "docs/plan/b2_e12_d1_d8_decisions_2026-10-24.json",
    "docs/results/b2_e10_k17d_identity.json", "docs/results/k17d_drift_audit.json",
)
# Canonical authority: the compute gates and their twin. Editing either is the only way the real state could be opened.
CANONICAL_AUTHORITY = (
    "docs/plan/b2_readiness_gates_2026-10-21.json", "docs/plan/b2_e5_decision_recommendations.json",
    "docs/plan/B2_E8_*", "docs/plan/b2_e8_*",
)
# Historical dossiers and verification reports: immutable evidence of what was true when they were written.
HISTORICAL_EVIDENCE = (
    "docs/plan/B2_E13_*", "docs/plan/B2_E14_*", "docs/plan/B2_E15_*", "docs/plan/B2_E16_*", "docs/plan/B2_E17_*",
    "docs/operations/B2_E13_*", "docs/operations/B2_E14_*", "docs/operations/B2_E15_*", "docs/operations/B2_E16_*", "docs/operations/B2_E17_*",
    "docs/results/B2_E13_*", "docs/results/B2_E14_*", "docs/results/B2_E15_*", "docs/results/B2_E16_*", "docs/results/B2_E17_*",
)
# Reviewed contracts E18 builds on. A later milestone may change them through its own review; E18 may not.
REVIEWED_CONTRACTS = (
    ".github/workflows/b2-readiness-ci.yml", ".github/workflows/b2-e15-operational-ci.yml", ".github/workflows/b2-e16-integration-ci.yml",
    ".github/workflows/b2-e17-evidence-ci.yml",
    "scripts/b2_e13_*", "scripts/b2_e14_*", "scripts/b2_e16_*", "scripts/b2_e17_*", "scripts/b2_e9_*", "scripts/b2_e12_*", "scripts/b2_e10_*",
    "scripts/b2_production_*", "scripts/b2_host_inventory.py",
    "tests/test_b2_e9_*", "tests/test_b2_e12_*", "tests/test_b2_e13_*", "tests/test_b2_e14_*", "tests/test_b2_e16_*", "tests/test_b2_e17_*",
)
CLASSES = (("frozen_science", FROZEN_SCIENCE), ("canonical_authority", CANONICAL_AUTHORITY), ("historical_evidence", HISTORICAL_EVIDENCE),
           ("reviewed_contract", REVIEWED_CONTRACTS))
PROFILES = {
    "e18": {
        "milestone": "E18 synthetic executor lifecycle",
        "allow": ("scripts/b2_e18_*.py", "tests/test_b2_e18_*.py", "tests/e18_support.py",
                  "docs/plan/B2_E18_*.md", "docs/operations/B2_E18_*.md", "docs/results/B2_E18_*.md",
                  "docs/plan/DURUM.md"),                 # not the workflow: a milestone PR that edits its own CI file also edits what judges it
    },
}
SAFE_PATH = re.compile(r"[A-Za-z0-9._@+=,-]+(/[A-Za-z0-9._@+=,-]+)*\Z")
# Files that change how Python or pytest behave for a whole directory tree: never allowed, whatever glob they would match.
IMPLICIT_CODE = frozenset({"conftest.py", "sitecustomize.py", "usercustomize.py", "__init__.py", "setup.py", "pytest.ini", "tox.ini", "setup.cfg", "pyproject.toml"})
IMPLICIT_SUFFIXES = (".pth", ".so", ".pyc")


def allowed_by(path, patterns):
    """Glob match in which ``*`` never crosses a directory separator (unlike fnmatch): ``scripts/b2_e18_*.py`` is one file name."""
    parts = path.split("/")
    return any(len(parts) == len(pattern.split("/")) and all(fnmatchcase(a, b) for a, b in zip(parts, pattern.split("/"))) for pattern in patterns)


def classify(path):
    """Name the strongest protection class a path falls under ('unclassified' when none)."""
    for name, patterns in CLASSES:
        if any(fnmatchcase(path, pattern) for pattern in patterns):
            return name
    return "unclassified"


def check_diff(changed, profile="e18"):
    """Every changed path must be allowed by the milestone profile and must not fall in a protected class."""
    if profile not in PROFILES:
        raise ValueError("unknown profile")
    allow = PROFILES[profile]["allow"]
    violations, classes = [], {}
    for path in changed:
        if not isinstance(path, str) or ".." in path.split("/") or path.startswith("/") or not SAFE_PATH.fullmatch(path):
            violations.append({"path": str(path)[:120], "class": "unsafe_path", "reason": "path is not a normalized repository-relative name"})
            continue
        name = classify(path)
        classes[path] = name
        if name != "unclassified":
            violations.append({"path": path, "class": name, "reason": f"{name.replace('_', ' ')} may not change in this milestone"})
        elif path.rsplit("/", 1)[-1] in IMPLICIT_CODE or path.endswith(IMPLICIT_SUFFIXES):
            violations.append({"path": path, "class": "implicit_code", "reason": "a file that silently changes how Python or pytest run is never an allowed addition"})
        elif not allowed_by(path, allow):
            violations.append({"path": path, "class": "outside_scope", "reason": "not an allowed path of the " + PROFILES[profile]["milestone"]})
    return {"schema": SCHEMA_DIFF, "profile": profile, "ok": not violations, "changed": len(changed), "violations": violations, "classes": classes,
            "base_is": "the PR merge base (current reviewed tree), not a frozen snapshot", **NO_AUTHORITY}


# ---- workflow hygiene ---------------------------------------------------------------------------------------------------

ALLOWED_ACTIONS = ("actions/checkout@v4", "actions/setup-python@v5")
FORBIDDEN_COMMANDS = (
    r"geosim\.b2_dataset", r"geoml\.b2_experiment", r"geoml\.train\b", r"b2_production_supervisor\.py", r"--mode\s+production",
    r"b2_production_preflight\.py\s+(lock-create|drill|run)", r"\bnvidia-smi\b", r"\btorch\.cuda\b", r"\bcurl\b", r"\bwget\b", r"\bscp\b",
    r"\bsudo\b", r"\bdocker\s+(run|exec)\b", r"\bgh\s+(api|release|workflow)\b", r"\bgit\s+push\b",
    r"\bpython3?\s+(-\w*c\b|-m\s+(b2_|geosim|geoml))", r"b2_production_supervisor", r"\bimportlib\b", r"\bos\.system\b", r"\bexec\(",
    r"git\+(https?|ssh)", r"\b(from|import)[ \t]+(geosim|geoml)\b", r"\bpython3?[ \t]+-m[ \t]+\S*\$",
)
# Steps the E18 workflow must keep (a tripwire for accidental removal; a deliberate rewrite of the file defeats it, see the module docstring).
GUARD_REQUIREMENTS = {
    "b2-e18-lifecycle-ci.yml": (
        r'git show "\$BASE:scripts/b2_e18_ci_policy\.py"', r'"\$POLICY" check-diff --base "\$BASE" --profile e18', r'"\$POLICY" lint \.github/workflows',
        r"scripts/b2_e16_policy\.py ci-gate", r"scripts/b2_e18_ci_policy\.py gate-decision",
    ),
}
FIXED_SHA = re.compile(r"git diff --exit-code ([0-9a-f]{40})\b")
PR_BASE = re.compile(r"github\.event\.pull_request\.base\.sha")


ON_LINES = (re.compile(r"  pull_request:\Z"), re.compile(r"    branches: \[main\]\Z"), re.compile(r"    paths:\Z"),
            re.compile(r'      - "[A-Za-z0-9_./*-]+"\Z'), re.compile(r"  workflow_dispatch:\Z"))
MAX_TIMEOUT_MINUTES = 60
# Reviewed document-rendering dependencies only. This exception neither permits
# scientific execution nor applies to any other workflow or command variant.
DOCUMENT_PACKAGE_COMMANDS = (
    "sudo apt-get update -qq",
    "sudo apt-get install -y --no-install-recommends pandoc texlive-latex-extra texlive-fonts-recommended lmodern poppler-utils",
)


def on_block(text):
    match = re.search(r"^on:[ ]*\n((?:(?:[ ]+\S.*|[ ]*)\n)*)", text, re.M)
    return None if match is None else match.group(1)


def lint_workflow(text, name="workflow"):
    """Static, text-level problems. An empty list means no known drift pattern matched, not that the workflow is safe."""
    problems = []
    code = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
    head = text.split("\njobs:", 1)[0]
    if not re.search(r"^permissions:\n  contents: read(?:\n(?!  )|\Z)", head, re.M):
        problems.append("top-level permissions must be exactly 'contents: read'")
    if re.search(r":\s*write\b", code):
        problems.append("a write permission is requested")
    triggers = on_block(text)
    if triggers is None:
        problems.append("no block-style 'on:' trigger section")
    else:                                            # only the reviewed shape is accepted: a flow map or list can hide a trigger from a line scan
        for line in triggers.splitlines():
            if line.strip() and not line.lstrip().startswith("#") and not any(pattern.fullmatch(line) for pattern in ON_LINES):
                problems.append(f"trigger line outside the reviewed shape: {line.strip()[:60]}")
    for word in ("pull_request_target", "workflow_run", "repository_dispatch", "issue_comment", "schedule"):
        if re.search(r"\b" + word + r"\b", code):
            problems.append(f"forbidden trigger: {word}")
    for pattern, label in ((r"\bsecrets\b", "secrets are referenced"), (r"github\.token", "the workflow token is referenced"),
                           (r"^\s*container:", "a job container"), (r"^\s*services:", "service containers"), (r"continue-on-error", "continue-on-error hides failures")):
        if re.search(pattern, code, re.M):
            problems.append(label)
    runners = re.findall(r"^\s*runs-on:\s*(\S+)", code, re.M)
    if not runners or any(r != "ubuntu-latest" for r in runners):
        problems.append("only the hosted ubuntu-latest runner is allowed")
    for action in re.findall(r"^\s*-?\s*uses:\s*(\S+)", code, re.M):
        if action not in ALLOWED_ACTIONS:
            problems.append(f"action not on the allow list: {action}")
    for pattern in FORBIDDEN_COMMANDS:
        inspected = code
        if name == "manuscript-ci.yml" and pattern == r"\bsudo\b":
            inspected = "\n".join(line for line in code.splitlines()
                                  if line.strip() not in DOCUMENT_PACKAGE_COMMANDS)
        if re.search(pattern, inspected):
            problems.append(f"forbidden command: {pattern}")
    timeouts = [int(m) for m in re.findall(r"^\s*timeout-minutes:\s*(\d+)\s*$", code, re.M)]
    if len(timeouts) != len(runners) or any(not 1 <= t <= MAX_TIMEOUT_MINUTES for t in timeouts):
        problems.append(f"every job needs a timeout of at most {MAX_TIMEOUT_MINUTES} minutes")
    for pattern in GUARD_REQUIREMENTS.get(name, ()):
        if not re.search(pattern, code):
            problems.append(f"a required guard step is missing: {pattern}")
    return problems


def workflow_guard_kind(text):
    """How a workflow's protection step chooses its comparison base: a hard-coded historical commit or the PR base."""
    fixed = FIXED_SHA.findall(text)
    return {"fixed_historical_commits": sorted(set(fixed)), "pr_relative": bool(PR_BASE.search(text))}


def lint_directory(directory):
    results = {}
    for path in sorted(Path(directory).glob("*.yml")):
        results[path.name] = {"problems": lint_workflow(path.read_text(), path.name), **workflow_guard_kind(path.read_text())}
    return {"schema": SCHEMA_LINT, "ok": all(not r["problems"] for r in results.values()), "workflows": results, **NO_AUTHORITY}


# ---- what a green CI may mean for the gate state --------------------------------------------------------------------------

def gate_decision(gates, memo, protocol, trusted=None):
    """CI's answer about the canonical gates. ``trusted`` is an E17 report; only a PRODUCTION-root VALID report can ever matter.

    * CLOSED_CANONICAL -> accepted (today's real state).
    * open candidate while this build configures no production trust root (``PINNED_TRUST_ROOT is None``, as today) -> rejected,
      whatever report is supplied: a caller-made dictionary cannot stand in for a trust root.
    * open candidate without a verified record -> rejected: a gate edit cannot pass CI on its own.
    * open candidate with a SYNTHETIC_TEST_ROOT report -> rejected: fabricated test authorities do not validate a real branch.
    * open candidate with a production-root VALID report -> accepted as a *document-level* result only; never execution.
    * anything else -> rejected.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import b2_e16_policy as P
    import b2_e17_evidence as E
    state = P.classify_gates(gates, memo, protocol)["state"]
    decision = {"schema": SCHEMA_GATE, "gate_state": state, "accepted": False, "accepted_as": None, "reason": None, **NO_AUTHORITY}
    if state == P.STATE_CLOSED:
        decision.update(accepted=True, accepted_as="closed_canonical", reason="every compute gate is exactly canonical-closed")
    elif state == P.STATE_CANDIDATE:
        scope = None if not isinstance(trusted, dict) else trusted.get("evidence_scope")
        if E.PINNED_TRUST_ROOT is None:
            decision["reason"] = "no production trust root is configured in this build: an approved-shaped gate cannot be validated"
        elif not isinstance(trusted, dict) or trusted.get("ok") is not True or trusted.get("state") != P.STATE_VALID:
            decision["reason"] = "an approved-shaped gate has no verified record: a gate edit cannot pass CI on its own"
        elif scope != "PRODUCTION_ROOT":
            decision["reason"] = f"evidence scope {scope!r} is not a production trust root: fabricated authorities cannot validate a real branch"
        else:
            decision.update(accepted=True, accepted_as="document_level_dr04_record_only",
                            reason="a production-root verified record exists; this is a statement about documents, never permission to run")
    else:
        decision["reason"] = "gates, memorandum and scientific approvals are inconsistent or over-broad"
    return decision


# ---- CLI -----------------------------------------------------------------------------------------------------------------------

def _git(*args):
    return subprocess.run(["git", "-c", "core.fsmonitor=false", *args], capture_output=True, text=True, timeout=60, check=True).stdout


def changed_paths(base):
    """Paths that differ between the merge base of ``base`` and HEAD (renames split into delete + add so both sides are judged)."""
    merge_base = _git("merge-base", base, "HEAD").strip()
    raw = _git("diff", "--name-only", "--no-renames", "-z", merge_base, "HEAD")
    return sorted(p for p in raw.split("\0") if p)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0], allow_abbrev=False)
    commands = parser.add_subparsers(dest="action", required=True)
    diff = commands.add_parser("check-diff", allow_abbrev=False)
    diff.add_argument("--base", required=True)
    diff.add_argument("--profile", default="e18", choices=sorted(PROFILES))
    lint = commands.add_parser("lint", allow_abbrev=False)
    lint.add_argument("directory", nargs="?", default=".github/workflows")
    gate = commands.add_parser("gate-decision", allow_abbrev=False)
    gate.add_argument("--repo", default=str(Path(__file__).resolve().parents[1]))
    args = parser.parse_args(argv)
    try:
        if args.action == "check-diff":
            report = check_diff(changed_paths(args.base), args.profile)
        elif args.action == "lint":
            report = lint_directory(args.directory)
        else:
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            import b2_e13_generation_plan as G
            import b2_e16_policy as P
            repo = Path(args.repo)
            report = gate_decision(*(P._read_strict(repo / name) for name in (P.pre.GATES_PATH, P.pre.MEMO_PATH, G.PROTOCOL_JSON)))
        print(json.dumps(report, sort_keys=True, indent=1, allow_nan=False))
        return 0 if report.get("ok", report.get("accepted")) else 1
    except Exception as error:
        print(json.dumps({"verdict": "NO-GO", "execution_permitted": False, "authorizes_nothing": True, "error": "invalid input: " + type(error).__name__}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

"""Execute the actual CI guards on bounded temporary Git histories/metadata.

These tests never generate RF or change canonical records. Only fixed workflow
commands and exact synthetic commit IDs are executed, in temporary repositories.
"""
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import textwrap

import pytest

ROOT = Path(__file__).resolve().parents[1]
E15 = ROOT / ".github/workflows/b2-e15-operational-ci.yml"
E16 = ROOT / ".github/workflows/b2-e16-integration-ci.yml"
E17 = ROOT / ".github/workflows/b2-e17-evidence-ci.yml"
GATES = "docs/plan/b2_readiness_gates_2026-10-21.json"
MEMO = "docs/plan/b2_e5_decision_recommendations.json"
PROTOCOL = "docs/plan/b2_e9_approved_scientific_protocol.json"


def step(path, name):
    source = path.read_text()
    marker = "      - name: " + name + "\n        run: |\n"
    assert source.count(marker) == 1
    body = source.split(marker, 1)[1].split("\n      - ", 1)[0]
    return textwrap.dedent(body)


E15_SNAPSHOT = "Preserve the historical E15 dossier and frozen scientific records"
E16_SNAPSHOT = "Preserve historical evidence and frozen scientific authority"
DOCUMENTS = "Validate blank qualification fields, documents and closed gates"


def command_paths(body):
    argv = shlex.split(body[body.index("git diff --exit-code"):].replace("\\\n", " "))
    return argv[3], argv[argv.index("--") + 1:]


def git(repo, *args):
    result = subprocess.run(["git", "-c", "core.fsmonitor=false", *args], cwd=repo,
                            capture_output=True, text=True, timeout=15, check=True)
    return result.stdout.strip()


def commit(repo):
    git(repo, "add", ".")
    git(repo, "-c", "user.name=E17 Synthetic Fixture", "-c", "user.email=synthetic@example.invalid",
        "commit", "-q", "-m", "synthetic metadata fixture")
    return git(repo, "rev-parse", "HEAD")


@pytest.fixture
def fixture(tmp_path):
    root = tmp_path / "metadata-repository"
    root.mkdir()
    paths = {GATES, MEMO, PROTOCOL, "docs/plan/DURUM.md"}
    for workflow, name in ((E15, E15_SNAPSHOT), (E16, E16_SNAPSHOT)):
        _, patterns = command_paths(step(workflow, name))
        for pattern in patterns:
            paths.update(path.relative_to(ROOT).as_posix() for path in ROOT.glob(pattern) if path.is_file())
    for relative in paths:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / relative).read_bytes())
    git(root, "init", "-q")
    return root, commit(root)


def snapshot_check(fixture, workflow, name):
    repo, baseline = fixture
    body = step(workflow, name)
    old_sha, _ = command_paths(body)
    assert len(old_sha) == 40 and body.count(old_sha) == 1
    # Only the fixture's initial commit substitutes for the hard-coded, reviewed
    # archival commit. There is no runtime baseline override in the workflow.
    body = body.replace(old_sha, baseline)
    return subprocess.run(["bash", "-e", "-c", body], cwd=repo, capture_output=True,
                          text=True, timeout=15)


def document_check(fixture):
    repo, _ = fixture
    body = step(E15, DOCUMENTS)
    assert body.startswith("python - <<'E15'\n") and body.rstrip().endswith("\nE15")
    code = body.split("\n", 1)[1].rsplit("\nE15", 1)[0]
    env = dict(os.environ, PYTHONPATH=str(ROOT / "scripts") + os.pathsep + str(ROOT / "src"),
               OMP_NUM_THREADS="2", OPENBLAS_NUM_THREADS="2", MKL_NUM_THREADS="2", CUDA_VISIBLE_DEVICES="")
    return subprocess.run([sys.executable, "-c", code], cwd=repo, env=env,
                          capture_output=True, text=True, timeout=45)


def change(repo, relative, raw):
    target = repo / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(raw)


def rewrite_json(repo, relative, change_object):
    path = repo / relative
    value = json.loads(path.read_text())
    change_object(value)
    path.write_text(json.dumps(value))


@pytest.mark.parametrize("workflow,name", [(E15, E15_SNAPSHOT), (E16, E16_SNAPSHOT)])
def test_reviewed_living_code_and_workflow_additions_are_not_historical_violations(fixture, workflow, name):
    repo, _ = fixture
    for relative in ("src/geoml/new_reviewed.py", "scripts/b2_e17_new.py", "tests/test_b2_e17_new.py",
                     ".github/workflows/b2-e15-operational-ci.yml"):
        change(repo, relative, "# synthetic reviewed change; never executed\n")
    (repo / "docs/plan/DURUM.md").write_text("# Later milestone status\n")
    commit(repo)
    assert snapshot_check(fixture, workflow, name).returncode == 0
    assert document_check(fixture).returncode == 0


@pytest.mark.parametrize("relative", [
    "docs/plan/P18_b2_protocol.md", "configs/b2_base.json", "configs/cancellation.json",
    "configs/b2_feat.json", PROTOCOL,
    "docs/plan/B2_E12_D1_D8_SCIENTIFIC_APPROVAL_2026-10-24.md",
    "docs/plan/b2_e12_d1_d8_decisions_2026-10-24.json",
    "docs/results/b2_e10_k17d_identity.json", "docs/results/k17d_drift_audit.json",
    "docs/operations/B2_E15_HOST_QUALIFICATION.md", "docs/plan/B2_E15_DR04_DECISION_DOSSIER.md",
])
@pytest.mark.parametrize("workflow,name", [(E15, E15_SNAPSHOT), (E16, E16_SNAPSHOT)])
def test_changed_scientific_or_archival_record_fails_closed(fixture, relative, workflow, name):
    repo, _ = fixture
    path = repo / relative
    path.write_bytes(path.read_bytes() + b"\nALTERED SYNTHETIC RECORD\n")
    commit(repo)
    assert snapshot_check(fixture, workflow, name).returncode != 0


def test_e16_evidence_cannot_be_silently_rewritten(fixture):
    repo, _ = fixture
    change(repo, "docs/results/B2_E16_VERIFICATION.md", "# Replaced evidence\n")
    commit(repo)
    assert snapshot_check(fixture, E16, E16_SNAPSHOT).returncode != 0


@pytest.mark.parametrize("key", ["full_generation", "full_gpu_training", "full_loko_sweep"])
def test_current_compute_gate_edit_cannot_hide_behind_historical_snapshot(fixture, key):
    repo, _ = fixture
    rewrite_json(repo, GATES, lambda value: value["decisions"][key].update(status="AUTHORIZED"))
    commit(repo)
    assert snapshot_check(fixture, E15, E15_SNAPSHOT).returncode == 0
    assert document_check(fixture).returncode != 0


def test_current_memorandum_mismatch_is_rejected(fixture):
    repo, _ = fixture
    rewrite_json(repo, MEMO, lambda value: value["decisions"]["K18"].update(status="PENDING_RESEARCHER"))
    assert document_check(fixture).returncode != 0


@pytest.mark.parametrize("raw", ['{"benchmark_complete":false,"benchmark_complete":false}',
                                 '{"benchmark_complete":NaN}', '{"benchmark_complete":1e999}'])
def test_current_gate_parser_rejects_duplicate_and_nonfinite_json(fixture, raw):
    repo, _ = fixture
    change(repo, GATES, raw)
    assert document_check(fixture).returncode != 0


def test_fabricated_measurement_in_historical_host_template_is_rejected(fixture):
    repo, _ = fixture
    path = repo / "docs/operations/B2_E15_HOST_QUALIFICATION.md"
    path.write_text(path.read_text().replace('"hostname": null', '"hostname": "fabricated-host"'))
    assert document_check(fixture).returncode != 0


def test_blank_researcher_worksheet_cannot_become_an_approval(fixture):
    repo, _ = fixture
    path = repo / "docs/plan/B2_E15_DR04_DECISION_DOSSIER.md"
    path.write_text(path.read_text().replace('"researcher_decision": null', '"researcher_decision": "APPROVE"'))
    assert document_check(fixture).returncode != 0


def test_current_e16_policy_classifier_is_called_and_future_code_not_frozen():
    body = step(E15, DOCUMENTS)
    assert "policy.ci_gate_check(gates, memo, protocol)" in body
    assert 'current["state"] == "CLOSED_CANONICAL"' in body
    for workflow, name in ((E15, E15_SNAPSHOT), (E16, E16_SNAPSHOT)):
        _, paths = command_paths(step(workflow, name))
        assert not {"src", "scripts", "tests", "configs", "pyproject.toml"}.intersection(paths)
        assert ".github/workflows/b2-readiness-ci.yml" not in paths


def test_e17_workflow_has_fixed_metadata_only_test_selection():
    body = step(E17, "Compile code and verify evidence with synthetic tests only")
    files = [part for part in shlex.split(body.replace("\\\n", " ")) if part.startswith("tests/")]
    assert len(files) == 17 and len(set(files)) == len(files)
    assert all(part.endswith(".py") and "*" not in part for part in files)
    assert not any("a5_replay" in part or "production_supervisor" in part for part in files)
    assert "torch==2.14.1+cpu" in E17.read_text()
    assert 'CUDA_VISIBLE_DEVICES: ""' in E17.read_text()
    assert "contents: read" in E17.read_text()

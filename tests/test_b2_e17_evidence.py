"""E17 synthetic trust custody and read-only integration, never real approval.

Three fabricated private keys and a temporary Git history live outside the
checkout. Only committed metadata/source are copied: no observations, waveform
synthesis, GPU discovery or production child is used. The positive configured
test root is explicitly synthetic; the real public entry point has no root.
"""
import ast
import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import b2_e17_evidence as E
from test_b2_e13_generation_plan import (APPROVER, NOW, RECORD, complete, decision_record,  # noqa: F401,E402
                                         k17d_report, record_text, reference)
from test_b2_e16_policy import operational_block

P, G, S, Git = E.P, E.P.G, E.Sig, E.Git
CLOCK = "2026-10-30T12:05:00+00:00"
CHALLENGE = "c" * 64
WORKFLOW = ".github/workflows/b2-e17-evidence-ci.yml"
REPOSITORY = "mythril33/Payload-Aware-Open-Set-Interference-Recognition-for-GEO-Transponders"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(document):
    return S.canonical(document).encode()


def git(repo, *args):
    return subprocess.run(["/usr/bin/git", "-c", "core.hooksPath=/dev/null", *args], cwd=repo,
                          check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout.decode().strip()


@pytest.fixture(scope="module")
def custody(tmp_path_factory):
    # The test authority is fabricated, not the actual researcher credential.
    directory = tmp_path_factory.mktemp("e17-fabricated-custody-only")
    principals = {"auth": APPROVER, "revocation": "independent-fixture-revocation", "ci": "independent-fixture-ci"}
    namespaces = {"auth": "b2-dr04", "revocation": "b2-revocation", "ci": "b2-ci"}
    keys, signers = {}, []
    for role, principal in principals.items():
        key = directory / role
        subprocess.run(["/usr/bin/ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "E17-FABRICATED-TEST-ONLY", "-f", str(key)],
                       check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        public = " ".join(key.with_suffix(".pub").read_text().split()[:2])
        keys[role] = key
        signers.append({"principal": principal, "public_key": public, "namespaces": [namespaces[role]]})
    policy = {"schema": "B2-E17-allowed-signers/1", "signers": signers}
    root = E.TrustRoot(sha(encoded(policy)), principals["revocation"], principals["ci"], REPOSITORY, (WORKFLOW,))
    counter = 0

    def sign(raw, role):
        nonlocal counter
        counter += 1
        target = directory / f"FABRICATED_EVIDENCE_ONLY_{counter}"
        target.write_bytes(raw)
        subprocess.run(["/usr/bin/ssh-keygen", "-Y", "sign", "-f", str(keys[role]), "-n", namespaces[role], str(target)],
                       check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return Path(str(target) + ".sig").read_bytes()

    return {"policy": policy, "root": root, "sign": sign}


def grant():
    return {"revocation_id": "fabricated-grant", "record_sha256": "a" * 64,
            "approved_plan_digest": "b" * 64, "reviewed_code_commit": "1" * 40, "approval_commit": "2" * 40}


def revocation_document(expected=None):
    return {"schema": "B2-E17-revocation-status/1", "issuer": "independent-fixture-revocation",
            "grant": grant() if expected is None else expected, "status": "ACTIVE", "issued_at": CLOCK,
            "expires_at": "2026-10-30T12:09:00+00:00", "sequence": 12, "challenge": CHALLENGE}


def ci_document(head="2" * 40):
    return {"schema": "B2-E17-ci-snapshot/1", "issuer": "independent-fixture-ci", "repository": REPOSITORY,
            "head_sha": head, "issued_at": CLOCK, "expires_at": "2026-10-30T12:09:00+00:00",
            "sequence": 12, "challenge": CHALLENGE, "runs": [
                {"workflow": WORKFLOW, "run_id": 1, "job_id": 2, "job_status": "completed", "job_conclusion": "success",
                 "attempt": 1, "head_sha": head, "event": "pull_request", "status": "completed", "conclusion": "success"}]}


def assert_no_authority(report):
    assert report["execution_permitted"] is False and report["authorizes_nothing"] is True
    assert report["benchmark_complete"] is False and report["production_launch_enabled"] is False
    assert report["verdict"] == "NO-GO" and report["replay_state_updated"] is False
    json.dumps(report, allow_nan=False)


def revocation(custody, document=None, **overrides):
    raw = encoded(revocation_document() if document is None else document)
    args = dict(policy=custody["policy"], root=custody["root"], expected=grant(), now=CLOCK,
                challenge=CHALLENGE, sequence_floor=12)
    args.update(overrides)
    report = E.verify_revocation(raw, custody["sign"](raw, "revocation"), **args)
    assert_no_authority(report)
    return report


def ci(custody, document=None, **overrides):
    raw = encoded(ci_document() if document is None else document)
    args = dict(policy=custody["policy"], root=custody["root"], source_head="2" * 40, now=CLOCK,
                challenge=CHALLENGE, sequence_floor=12)
    args.update(overrides)
    report = E.verify_ci_snapshot(raw, custody["sign"](raw, "ci"), **args)
    assert_no_authority(report)
    return report


def test_signed_explicit_active_is_read_only_document_evidence(custody):
    report = revocation(custody)
    assert report["ok"] and report["status"] == "VERIFIED_ACTIVE"


@pytest.mark.parametrize("field,value", [
    ("status", "REVOKED"), ("status", "UNKNOWN"), ("status", []), ("grant", {}),
    ("issuer", "researcher-self-issued"), ("schema", "unknown"), ("sequence", 11), ("sequence", True),
    ("challenge", "d" * 64), ("issued_at", "2026-10-30T12:05:06Z"),
    ("issued_at", "2026-10-30T11:59:59Z"), ("expires_at", CLOCK),
    ("expires_at", "2026-10-30T12:10:01Z"), ("expires_at", "2026-10-30T12:06:00"),
])
def test_authenticated_bad_revocation_is_still_refused(custody, field, value):
    document = revocation_document()
    document[field] = value
    assert not revocation(custody, document)["ok"]


@pytest.mark.parametrize("field", tuple(grant()))
def test_revocation_cannot_transfer_to_other_grant_identity(custody, field):
    document = revocation_document()
    document["grant"][field] = "different"
    assert not revocation(custody, document)["ok"]


@pytest.mark.parametrize("override", [dict(root=None), dict(now="2026-10-30T12:09:00Z"), dict(challenge=""),
                                     dict(sequence_floor=13), dict(sequence_floor=0), dict(sequence_floor=True)])
def test_missing_custody_or_stale_challenge_cannot_default_active(custody, override):
    assert not revocation(custody, **override)["ok"]


def test_actual_signed_exact_head_and_job_snapshot(custody):
    assert ci(custody)["status"] == "VERIFIED_CI_SNAPSHOT"


@pytest.mark.parametrize("field,value", [
    ("repository", "attacker/substitute"), ("head_sha", "3" * 40), ("issuer", APPROVER),
    ("schema", "unknown"), ("runs", []), ("sequence", 11), ("challenge", "d" * 64),
    ("expires_at", CLOCK), ("expires_at", "2026-10-30T12:10:01Z"),
])
def test_signed_but_incompatible_ci_snapshot_is_refused(custody, field, value):
    document = ci_document()
    document[field] = value
    assert not ci(custody, document)["ok"]


@pytest.mark.parametrize("field,value", [
    ("workflow", ".github/workflows/attacker.yml"), ("run_id", True), ("run_id", 0),
    ("job_id", True), ("job_id", 0), ("job_status", "in_progress"), ("job_conclusion", "failure"),
    ("attempt", 0), ("attempt", True), ("head_sha", "3" * 40), ("event", "push"),
    ("status", "in_progress"), ("conclusion", "failure"), ("conclusion", "Verified"),
])
def test_ci_head_job_conclusion_and_workflow_are_exact(custody, field, value):
    document = ci_document()
    document["runs"][0][field] = value
    assert not ci(custody, document)["ok"]


@pytest.mark.parametrize("kind", ["revocation", "ci"])
@pytest.mark.parametrize("raw", [None, b"", b"unreachable", b'{"x":1,"x":2}', b'{"x":NaN}', b"x" * (E.MAX_BYTES + 1)])
def test_unavailable_malformed_or_unsigned_source_fails_closed(custody, kind, raw):
    kwargs = dict(policy=custody["policy"], root=custody["root"], now=CLOCK, challenge=CHALLENGE, sequence_floor=12)
    if kind == "ci":
        kwargs["source_head"] = "2" * 40
        report = E.verify_ci_snapshot(raw, b"forged-signature", **kwargs)
    else:
        kwargs["expected"] = grant()
        report = E.verify_revocation(raw, b"forged-signature", **kwargs)
    assert not report["ok"]
    assert_no_authority(report)


@pytest.fixture(scope="module")
def integrated(tmp_path_factory, custody):
    repo = tmp_path_factory.mktemp("e17-source-metadata-repo")
    shutil.copytree(ROOT / "src", repo / "src", ignore=shutil.ignore_patterns("__pycache__", "*.egg-info"))
    (repo / "scripts").mkdir()
    for path in (ROOT / "scripts").glob("*.py"):
        shutil.copy2(path, repo / "scripts" / path.name)
    shutil.copytree(ROOT / "configs", repo / "configs")
    shutil.copy2(ROOT / "pyproject.toml", repo / "pyproject.toml")
    for name in set(G.INPUT_FILES) | set(G.SCIENTIFIC_RECORDS):
        target = repo / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, target)
    git(repo, "init", "-q")
    git(repo, "config", "user.name", "E17 fabricated history")
    git(repo, "config", "user.email", "fixture@example.invalid")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "Fabricated reviewed source and scientific metadata")
    reviewed = git(repo, "rev-parse", "HEAD")
    ref = G.collect_reference(repo, rederive=False, evaluated_at=NOW)
    # Re-derivation is outside this signature test: explicit synthetic fixture
    # marker, never presented as an independent host or K17d measurement.
    ref["k17d_verification"]["generator_rederived"] = True
    plan = complete(ref)
    # This remains a fabricated host, but its environment must match the
    # validating process on both local and CI patch releases. The older E13
    # helper intentionally hardcodes its historical synthetic environment.
    synthetic_inventory = plan["host"]["inventory"]["inventory"]
    synthetic_inventory["python"] = plan["environment"]["python"]
    for library in ("numpy", "scipy"):
        synthetic_inventory["libraries"][library] = plan["environment"][library]
    synthetic_inventory["environment"].update(plan["environment"]["thread_environment"])
    fake_host = copy.deepcopy(ref["host_measurements"])
    digest = G.approved_plan_digest(plan)
    block = operational_block(plan, reviewed_code_commit=reviewed,
                              signature={"scheme": "ssh-signature", "evidence_sha256": custody["root"].policy_sha256})
    raw = (record_text(digest) + "\n```json\n" + S.canonical(block) + "\n```\n").encode()
    (repo / RECORD).parent.mkdir(parents=True, exist_ok=True)
    (repo / RECORD).write_bytes(raw)
    (repo / P.pre.GATES_PATH).write_text(S.canonical(ref["gates"]))
    (repo / P.pre.MEMO_PATH).write_text(S.canonical(ref["memo"]))
    git(repo, "add", P.pre.GATES_PATH, P.pre.MEMO_PATH, RECORD)
    git(repo, "commit", "-qm", "Fabricated DR04 metadata-only approval; no real authority")
    approval = git(repo, "rev-parse", "HEAD")
    # The persisted lock boundary is strict JSON; build_lock's in-process
    # production roles tuple is represented as its JSON array on disk.
    lock = json.loads(json.dumps(P.pre.build_lock(repo), allow_nan=False))
    ref = G.collect_reference(repo, rederive=False, evaluated_at=NOW, record_paths=(RECORD,))
    ref["k17d_verification"]["generator_rederived"] = True
    ref["lock"], ref["lock_problems"] = lock, P.pre.verify_lock(lock, repo, require_clean=True)
    ref["host_measurements"] = fake_host
    plan["source"] = G.make_template(ref)["source"]
    plan["lock"] = {"lock_fingerprint": lock["lock_fingerprint"]}
    plan["release_evidence"]["exact_head_ci"]["head_sha"] = approval
    plan["release_evidence"]["independent_review"]["reviewed_head"] = approval
    plan["authorization"].update(git_commit=approval, lock_fingerprint=lock["lock_fingerprint"], record_sha256=sha(raw))
    plan["plan_fingerprint"] = G.plan_fingerprint(plan)
    plan["authorization"]["plan_fingerprint"] = plan["plan_fingerprint"]
    assert G.approved_plan_digest(plan) == digest
    expected = {"revocation_id": block["revocation_id"], "record_sha256": sha(raw), "approved_plan_digest": digest,
                "reviewed_code_commit": reviewed, "approval_commit": approval}
    rev = encoded(revocation_document(expected))
    ci_raw = encoded(ci_document(approval))
    evidence = {"policy": custody["policy"], "authorization_signature": custody["sign"](raw, "auth"),
                "revocation": rev, "revocation_signature": custody["sign"](rev, "revocation"),
                "ci": ci_raw, "ci_signature": custody["sign"](ci_raw, "ci")}
    return {"repo": repo, "plan": plan, "reference": ref, "evidence": evidence, "root": custody["root"]}


def integrated_run(bundle, *, public=False, **override):
    args = dict(repo=bundle["repo"], evidence=bundle["evidence"], now=CLOCK, challenge=CHALLENGE,
                revocation_floor=12, ci_floor=12, requested_scope=copy.deepcopy(P.GRANTED_SCOPE))
    if not public:
        args["root"] = bundle["root"]
    args.update(override)
    function = E.evaluate_trusted_authorization if public else E._evaluate_with_root
    result = function(bundle["plan"], bundle["reference"], **args)
    assert_no_authority(result)
    return result


def test_genuine_ssh_and_git_bridge_validates_synthetic_record_without_authority(integrated):
    before = copy.deepcopy((integrated["plan"], integrated["reference"], integrated["evidence"]))
    report = integrated_run(integrated)
    assert report["state"] == P.STATE_VALID, json.dumps(report, indent=2)
    assert report["ok"] and report["evidence_scope"] == "SYNTHETIC_TEST_ROOT"
    assert report["lineage"]["lock_checked"] and report["signature"]["ok"]
    assert (integrated["plan"], integrated["reference"], integrated["evidence"]) == before


def test_real_public_entry_refuses_self_selected_policy_even_if_validly_signed(integrated):
    assert E.PINNED_TRUST_ROOT is None
    report = integrated_run(integrated, public=True)
    assert report["status"] == "BLOCKED_TRUST_ROOT_MISSING" and not report["ok"]
    assert report["state"] == P.STATE_DENIED and report["gate_state"] == P.STATE_CANDIDATE


def test_canonical_closed_state_requires_no_external_authority(reference, tmp_path):
    for name, document in ((P.pre.GATES_PATH, reference["gates"]), (P.pre.MEMO_PATH, reference["memo"]),
                           (G.PROTOCOL_JSON, reference["scientific_protocol"])):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(S.canonical(document))
    git(tmp_path, "init", "-q")
    git(tmp_path, "-c", "user.name=E17fixture", "-c", "user.email=fixture@example.invalid", "add", ".")
    git(tmp_path, "-c", "user.name=E17fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "Closed metadata fixture")
    reference["head"] = git(tmp_path, "rev-parse", "HEAD")
    report = E.ci_authority_check(G.make_template(reference), reference, repo=tmp_path, evidence=None, now=CLOCK,
                                challenge=CHALLENGE, revocation_floor=12, ci_floor=12)
    assert report["state"] == P.STATE_CLOSED and report["accepted_for_ci"]
    assert_no_authority(report)


def test_caller_closed_snapshot_cannot_hide_actual_open_checkout(integrated, reference):
    reference["head"] = integrated["plan"]["source"]["git_commit"]
    report = E.ci_authority_check(G.make_template(reference), reference, repo=integrated["repo"], evidence=None,
                                now=CLOCK, challenge=CHALLENGE, revocation_floor=12, ci_floor=12)
    assert not report["ok"] and not report["accepted_for_ci"] and report["state"] == P.STATE_DENIED
    assert_no_authority(report)


def test_ci_different_workflows_cannot_reuse_same_job(custody):
    root = E.TrustRoot(custody["root"].policy_sha256, custody["root"].revocation_principal, custody["root"].ci_principal,
                       REPOSITORY, (WORKFLOW, ".github/workflows/another.yml"))
    document = ci_document()
    document["runs"].append({**document["runs"][0], "workflow": root.required_workflows[1], "run_id": 3})
    assert not ci(custody, document, root=root)["ok"]


@pytest.mark.parametrize("scope", [dict(gate="gpu_probe", stages=[]), dict(gate="full_gpu_training", stages=[]),
                                  dict(gate="full_loko_sweep", stages=[]), dict(gate="held_out_final_evaluation", stages=["test"])])
def test_other_compute_scopes_are_denied_even_with_synthetic_verified_evidence(integrated, scope):
    assert not integrated_run(integrated, requested_scope=scope)["ok"]


@pytest.mark.parametrize("field", ["authorization_signature", "revocation_signature", "ci_signature"])
def test_no_unsigned_adapter_can_reach_valid_record(integrated, field):
    evidence = copy.deepcopy(integrated["evidence"])
    evidence[field] = b"forged"
    assert not integrated_run(integrated, evidence=evidence)["ok"]


def test_self_authored_trust_root_identity_is_not_accepted(integrated):
    evidence = copy.deepcopy(integrated["evidence"])
    evidence["policy"]["signers"][0]["principal"] = "attacker"
    assert not integrated_run(integrated, evidence=evidence)["ok"]


def test_claimed_source_map_must_equal_actual_git_objects(integrated):
    bundle = {**integrated, "plan": copy.deepcopy(integrated["plan"]), "reference": copy.deepcopy(integrated["reference"])}
    path = next(iter(bundle["plan"]["source"]["files_sha256"]))
    bundle["plan"]["source"]["files_sha256"][path] = "0" * 64
    bundle["reference"]["files_sha256"][path] = "0" * 64
    bundle["plan"]["source"]["source_tree_sha256"] = G.sha256_of(bundle["plan"]["source"]["files_sha256"])
    bundle["plan"]["plan_fingerprint"] = G.plan_fingerprint(bundle["plan"])
    bundle["plan"]["authorization"]["plan_fingerprint"] = bundle["plan"]["plan_fingerprint"]
    report = integrated_run(bundle)
    assert not report["ok"] and report["failures"] == ["plan source identity differs from Git objects: files_sha256"]


@pytest.mark.parametrize("records", [{}, {"docs/plan/attacker.json": "0" * 64}])
def test_same_omitted_or_substituted_record_map_in_plan_and_reference_is_rejected(integrated, records):
    bundle = {**integrated, "plan": copy.deepcopy(integrated["plan"]), "reference": copy.deepcopy(integrated["reference"])}
    bundle["plan"]["source"]["records_sha256"] = records
    bundle["reference"]["records_sha256"] = records
    bundle["plan"]["plan_fingerprint"] = G.plan_fingerprint(bundle["plan"])
    bundle["plan"]["authorization"]["plan_fingerprint"] = bundle["plan"]["plan_fingerprint"]
    report = integrated_run(bundle)
    assert not report["ok"] and report["failures"] == ["scientific record map incomplete or unexpected"]


@pytest.mark.parametrize("field,value", [("path", "docs/plan/forged.json"), ("sha256", "0" * 64),
                                         ("document", {"schema": "forged", "D-1": "pristine"})])
def test_parsed_decision_is_bound_to_committed_record_bytes(integrated, field, value):
    bundle = {**integrated, "reference": copy.deepcopy(integrated["reference"])}
    bundle["reference"]["decision_record"][field] = value
    report = integrated_run(bundle)
    assert not report["ok"] and report["failures"] == ["parsed scientific decision differs from committed bytes"]


def test_scientific_markdown_approval_hashes_cannot_be_omitted(integrated):
    bundle = {**integrated, "reference": copy.deepcopy(integrated["reference"])}
    bundle["reference"]["scientific_record_sha256"] = []
    report = integrated_run(bundle)
    assert not report["ok"] and report["failures"] == ["scientific approval record set differs from Git"]


def test_record_byte_and_design_modification_is_refused(integrated):
    bundle = {**integrated, "plan": copy.deepcopy(integrated["plan"]), "reference": copy.deepcopy(integrated["reference"])}
    bundle["reference"]["record_texts"][RECORD] += "modified after verification"
    assert not integrated_run(bundle)["ok"]
    bundle["reference"] = integrated["reference"]
    bundle["plan"]["authorization"]["approved_plan_digest"] = "0" * 64
    assert not integrated_run(bundle)["ok"]


def test_release_job_claim_must_equal_independently_signed_job(integrated):
    bundle = {**integrated, "plan": copy.deepcopy(integrated["plan"])}
    bundle["plan"]["release_evidence"]["exact_head_ci"]["job_id"] = 999
    bundle["plan"]["plan_fingerprint"] = G.plan_fingerprint(bundle["plan"])
    bundle["plan"]["authorization"]["plan_fingerprint"] = bundle["plan"]["plan_fingerprint"]
    report = integrated_run(bundle)
    assert not report["ok"] and report["failures"] == ["E13 CI claim differs from authenticated CI"]


def test_all_fenced_json_is_strict_even_with_whitespace_crlf_and_unknown_schema(integrated, monkeypatch):
    original = (integrated["repo"] / RECORD).read_bytes()
    malformed = original + b'\n```json \t\r\n{"schema":"unused","x":1,"x":2}\r\n``` \t\r\n'
    monkeypatch.setattr(Git, "read_blob", lambda *args: malformed)
    report = integrated_run(integrated)
    assert not report["ok"] and report["failures"] == ["invalid strict JSON"]


def test_bridge_exposes_no_executor_or_subprocess_callback():
    tree = ast.parse((ROOT / "scripts/b2_e17_evidence.py").read_text())
    assert not any(isinstance(node, (ast.Import, ast.ImportFrom)) and "subprocess" in ast.unparse(node) for node in ast.walk(tree))
    assert "adapters" not in __import__("inspect").signature(E.evaluate_trusted_authorization).parameters
    assert "root" not in __import__("inspect").signature(E.evaluate_trusted_authorization).parameters

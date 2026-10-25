"""Read-only E17 evidence -> E16 policy. No executor, network client or launch API.

Production trust configuration is deliberately absent. The application, never an
approval document, must pin a reviewed policy and independent issuer identities.
Signed snapshots are supported instead of silently trusting unauthenticated HTTP.
Request nonces and monotonic floors must come from external trusted custody;
this read-only verifier cannot persist a replay ledger or establish host facts.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import b2_e16_policy as P
import b2_e17_git as Git
import b2_e17_signatures as Sig

HEX = re.compile(r"[0-9a-f]{64}\Z")
HEAD = re.compile(r"[0-9a-f]{40}\Z")
MAX_BYTES = 256 * 1024
NO_AUTHORITY = dict(P.NO_AUTHORITY)


@dataclass(frozen=True)
class TrustRoot:
    policy_sha256: str
    revocation_principal: str
    ci_principal: str
    repository: str
    required_workflows: tuple[str, ...]


# No researcher key, issuer or CI credential has been independently provisioned.
# Changing this requires a separate reviewed trust-root configuration change.
# There is no environment variable or approval-JSON override.
PINNED_TRUST_ROOT = None


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _need(condition, message):
    if not condition:
        raise ValueError(message)


def _instant(value):
    _need(type(value) is str, "timestamp must be text")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    _need(result.tzinfo is not None and result.utcoffset() is not None, "timezone required")
    return result.astimezone(timezone.utc)


def _bounded(raw):
    _need(type(raw) is bytes and 0 < len(raw) <= MAX_BYTES, "bounded exact evidence bytes required")
    return raw


def _clock(document, now, challenge, floor, *, max_age_s=300, skew_s=5):
    _need(type(challenge) is str and HEX.fullmatch(challenge), "trusted request challenge required")
    _need(type(floor) is int and floor > 0, "trusted monotonic sequence floor required")
    _need(type(document["sequence"]) is int and document["sequence"] >= floor, "replayed evidence sequence")
    _need(document["challenge"] == challenge, "request challenge mismatch")
    issued = _instant(document["issued_at"])
    expires = _instant(document["expires_at"])
    # Explicit bounds prevent enormous times or a timestamp without an expiry
    # from being mistaken for a current answer.
    clock = _instant(now)
    _need(0 < (expires - issued).total_seconds() <= max_age_s, "evidence validity exceeds freshness policy")
    _need(-skew_s <= (clock - issued).total_seconds() <= max_age_s, "stale/future evidence")
    _need(clock < expires, "evidence expired")


def _signed(raw, signature, policy, root, principal, namespace):
    _bounded(raw)
    report = Sig.verify_signature(raw, signature, policy=policy, policy_sha256=root.policy_sha256,
                                  principal=principal, namespace=namespace)
    _need(report["ok"] is True, "cryptographic evidence verification failed: " + report["status"])
    return Sig.strict_json(raw)


def _report(kind, ok=False, status="DENIED", failures=(), **extra):
    return {"schema": "B2-E17-evidence/1", "kind": kind, "ok": ok, "status": status,
            "failures": list(failures), "replay_state_updated": False, **extra, **NO_AUTHORITY}


def verify_revocation(raw, signature, *, policy, root, expected, now, challenge, sequence_floor):
    """Require an authenticated, fresh explicit ACTIVE answer for this exact grant.

    Absence from a revocation list is insufficient. No local cache/default ACTIVE,
    network retry downgrade or status creation exists in this reader.
    """
    if root is None:
        return _report("revocation", status="BLOCKED_TRUST_ROOT_MISSING")
    try:
        doc = _signed(raw, signature, policy, root, root.revocation_principal, "b2-revocation")
        _need(set(doc) == {"schema", "issuer", "grant", "status", "issued_at", "expires_at", "sequence", "challenge"}, "revocation fields differ")
        _need(doc["schema"] == "B2-E17-revocation-status/1" and doc["issuer"] == root.revocation_principal, "wrong revocation issuer")
        _need(Sig.canonical(doc["grant"]) == Sig.canonical(expected), "revocation bound to a different grant")
        _clock(doc, now, challenge, sequence_floor)
        _need(doc["status"] == "ACTIVE", "revoked or unknown grant")
        return _report("revocation", True, "VERIFIED_ACTIVE", checked_at=doc["issued_at"], evidence_sha256=_sha(raw))
    except Exception as error:
        return _report("revocation", failures=(str(error)[:200],))


def verify_ci_snapshot(raw, signature, *, policy, root, source_head, now, challenge, sequence_floor):
    """Verify an independently signed CI observation, not a claimed success string.

    The attestor must retrieve authenticated GitHub results independently, retain
    raw evidence and sign a challenge-specific snapshot. No such service/key is
    configured today; user-supplied JSON without its trusted signature is refused.
    """
    if root is None:
        return _report("ci", status="BLOCKED_TRUST_ROOT_MISSING")
    try:
        doc = _signed(raw, signature, policy, root, root.ci_principal, "b2-ci")
        _need(set(doc) == {"schema", "issuer", "repository", "head_sha", "runs", "issued_at", "expires_at", "sequence", "challenge"}, "CI fields differ")
        _need(doc["schema"] == "B2-E17-ci-snapshot/1" and doc["issuer"] == root.ci_principal, "wrong CI attestor")
        _need(doc["repository"] == root.repository and doc["head_sha"] == source_head and HEAD.fullmatch(source_head), "wrong CI repository/head")
        _clock(doc, now, challenge, sequence_floor)
        _need(type(doc["runs"]) is list and len(doc["runs"]) == len(root.required_workflows), "missing/extra CI workflow")
        seen, ids, jobs = set(), set(), set()
        for run in doc["runs"]:
            _need(type(run) is dict and set(run) == {"workflow", "run_id", "job_id", "job_status", "job_conclusion", "attempt", "head_sha", "event", "status", "conclusion"}, "CI run fields differ")
            _need(run["workflow"] in root.required_workflows and run["workflow"] not in seen, "duplicate/untrusted workflow")
            _need(type(run["run_id"]) is int and run["run_id"] > 0 and run["run_id"] not in ids, "invalid/replayed CI run id")
            _need(type(run["attempt"]) is int and run["attempt"] > 0, "invalid CI attempt")
            _need(type(run["job_id"]) is int and run["job_id"] > 0 and run["job_id"] not in jobs
                  and run["job_status"] == "completed" and run["job_conclusion"] == "success", "CI job duplicated or not completed/success")
            _need(run["head_sha"] == source_head and run["event"] in ("pull_request", "workflow_dispatch"), "CI source/event mismatch")
            _need(run["status"] == "completed" and run["conclusion"] == "success", "CI not completed/success")
            seen.add(run["workflow"])
            ids.add(run["run_id"])
            jobs.add(run["job_id"])
        return _report("ci", True, "VERIFIED_CI_SNAPSHOT", evidence_sha256=_sha(raw), runs=doc["runs"])
    except Exception as error:
        return _report("ci", failures=(str(error)[:200],))


def _validate_root(root, policy, researcher):
    _need(isinstance(root, TrustRoot), "trusted application root required")
    _need(HEX.fullmatch(root.policy_sha256) and _sha(Sig.canonical(policy).encode()) == root.policy_sha256, "untrusted signer policy")
    _need(type(root.required_workflows) is tuple and root.required_workflows and len(set(root.required_workflows)) == len(root.required_workflows), "pinned CI workflow set missing")
    _need(all(type(w) is str and re.fullmatch(r"\.github/workflows/[a-z0-9_-]+\.yml", w) for w in root.required_workflows), "invalid pinned CI workflow")
    _need(type(root.repository) is str and re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", root.repository), "pinned repository missing")
    principals = (researcher, root.revocation_principal, root.ci_principal)
    _need(len(set(principals)) == 3, "independent authorization/revocation/CI principals required")
    keys = []
    for principal, namespace in zip(principals, ("b2-dr04", "b2-revocation", "b2-ci")):
        entries = [s for s in policy["signers"] if s["principal"] == principal and namespace in s["namespaces"]]
        _need(len(entries) == 1, "trusted signer role missing/ambiguous")
        keys.append(entries[0]["public_key"])
    _need(len(set(keys)) == 3, "independent issuer keys required")


def _bind_scientific_reference(repo, head, reference):
    """Bind complete scientific identities, including parsed decision bytes.

    Comparing a plan with a caller-provided reference is insufficient: both
    could omit the same record or substitute the same parsed decision object.
    The expected record set comes from the frozen E13 contract, never input.
    """
    expected = set(P.G.INPUT_FILES) - {P.pre.GATES_PATH}
    claimed = reference["records_sha256"]
    _need(type(claimed) is dict and set(claimed) == expected, "scientific record map incomplete or unexpected")
    raw_records = {path: Git.read_blob(repo, head, path) for path in expected | set(P.G.SCIENTIFIC_RECORDS)}
    _need(all(_sha(raw_records[path]) == claimed[path] for path in expected), "reference scientific/history digest differs from Git")
    decision = reference["decision_record"]
    _need(type(decision) is dict and set(decision) == {"path", "sha256", "document"}, "decision record reference fields differ")
    _need(decision["path"] == P.G.DECISIONS and decision["sha256"] == _sha(raw_records[P.G.DECISIONS])
          and Sig.canonical(decision["document"]) == Sig.canonical(Sig.strict_json(raw_records[P.G.DECISIONS])),
          "parsed scientific decision differs from committed bytes")
    _need(type(reference["scientific_record_sha256"]) is list
          and reference["scientific_record_sha256"] == sorted(_sha(raw_records[path]) for path in P.G.SCIENTIFIC_RECORDS),
          "scientific approval record set differs from Git")


def evaluate_trusted_authorization(plan, reference, *, repo, evidence, now, challenge, revocation_floor, ci_floor,
                                   requested_scope=None):
    """Real entry point: no caller-provided trust-root or callback override."""
    return _evaluate_with_root(plan, reference, repo=repo, evidence=evidence, now=now, challenge=challenge,
                               revocation_floor=revocation_floor, ci_floor=ci_floor,
                               requested_scope=P.GRANTED_SCOPE if requested_scope is None else requested_scope,
                               root=PINNED_TRUST_ROOT, test_root=False)


def _evaluate_with_root(plan, reference, *, repo, evidence, now, challenge, revocation_floor, ci_floor,
                        requested_scope, root, test_root=True):
    """Internal configured-root harness; synthetic tests are marked explicitly."""
    base = _report("operational", state=P.STATE_DENIED, evidence_scope="SYNTHETIC_TEST_ROOT" if test_root else "PRODUCTION_ROOT")
    # No caller callbacks are accepted. E16's old injectable interface remains
    # useful for its unit contracts; this adapter constructs its own closures.
    try:
        classified = P.classify_gates(reference["gates"], reference["memo"], reference["scientific_protocol"])
        if classified["state"] == P.STATE_CLOSED:
            # A caller-controlled closed snapshot cannot hide an open checkout.
            # No approval lineage is expected here, but identity and cleanliness
            # are real Git/worktree observations rather than asserted JSON.
            head = reference["head"]
            identities = {}
            for path, document in ((P.pre.GATES_PATH, reference["gates"]), (P.pre.MEMO_PATH, reference["memo"]),
                                   (P.G.PROTOCOL_JSON, reference["scientific_protocol"])):
                raw = Git.read_blob(repo, head, path)
                _need(Sig.canonical(Sig.strict_json(raw)) == Sig.canonical(document), "closed reference differs from committed authority")
                identities[path] = _sha(raw)
            checkout = Git.verify_checkout(repo, head, identities)
            _need(checkout["ok"] is True, "closed checkout identity/cleanliness refused")
            result = P.evaluate_operational_authorization(plan, reference, requested_scope=requested_scope, now=now)
            return {**base, "state": result["state"], "ok": result["state"] == P.STATE_CLOSED,
                    "status": result["state"], "policy_report": result, "checkout": checkout}
        _need(classified["state"] == P.STATE_CANDIDATE, "inconsistent/overbroad compute authority")
        if root is None:
            return {**base, "status": "BLOCKED_TRUST_ROOT_MISSING", "gate_state": classified["state"]}
        ref = P.C._document(reference)
        p = P.C._check_plan(plan)
        _need(type(evidence) is dict and set(evidence) == {"policy", "authorization_signature", "revocation", "revocation_signature", "ci", "ci_signature"}, "unexpected/missing evidence")
        researcher = ref["scientific_protocol"]["approved_by"]
        _validate_root(root, evidence["policy"], researcher)
        auth = p["authorization"]
        record_path, head = auth["record"], p["source"]["git_commit"]
        raw = Git.read_blob(repo, head, record_path)
        _bounded(raw)
        # Parse all fenced JSON blocks strictly, even those of another schema.
        for block in re.findall(rb"^```json[ \t]*\r?\n(.*?)\r?\n```[ \t]*(?:\r?\n|\Z)", raw, re.S | re.M):
            Sig.strict_json(block)
        blocks = P._blocks_of(raw.decode("utf-8"), P.SCHEMA_BLOCK)
        _need(len(blocks) == 1, "exactly one operational block required")
        block = blocks[0]
        _need(_sha(raw) == auth["record_sha256"] and raw.decode("utf-8") == ref["record_texts"][record_path], "record bytes modified/substituted")
        _need(block["signature"] == {"scheme": "ssh-signature", "evidence_sha256": root.policy_sha256}, "signature policy reference mismatch")
        _bind_scientific_reference(repo, head, ref)
        lineage = Git.verify_lineage(repo, block["reviewed_code_commit"], head, record_path,
                                      expected_record_sha256=_sha(raw), lock=ref.get("lock"))
        _need(lineage["ok"] is True, "Git lineage/clean lock verification refused")
        actual_tools = {name.removeprefix("scripts/"): value for name, value in lineage["tools_sha256"].items()}
        for field, actual in (("files_sha256", lineage["source_sha256"]), ("configs_sha256", lineage["configs_sha256"]),
                              ("tools_sha256", actual_tools)):
            _need(Sig.canonical(p["source"][field]) == Sig.canonical(actual), "plan source identity differs from Git objects: " + field)
            _need(Sig.canonical(ref[field]) == Sig.canonical(actual), "reference source identity differs from Git objects: " + field)
        _need(block["approved_plan_digest"] == auth["approved_plan_digest"] == P.G.approved_plan_digest(p), "design digest mismatch")
        for path, expected_doc in ((P.pre.GATES_PATH, ref["gates"]), (P.pre.MEMO_PATH, ref["memo"]),
                                   (P.G.PROTOCOL_JSON, ref["scientific_protocol"])):
            _need(Sig.canonical(Sig.strict_json(Git.read_blob(repo, head, path))) == Sig.canonical(expected_doc), "reference document differs from committed bytes")
        signed = Sig.verify_signature(raw, evidence["authorization_signature"], policy=evidence["policy"],
                                      policy_sha256=root.policy_sha256, principal=researcher, namespace="b2-dr04")
        _need(signed["ok"] is True, "researcher signature refused")
        expected = {"revocation_id": block["revocation_id"], "record_sha256": _sha(raw),
                    "approved_plan_digest": block["approved_plan_digest"], "reviewed_code_commit": block["reviewed_code_commit"],
                    "approval_commit": head}
        rev = verify_revocation(evidence["revocation"], evidence["revocation_signature"], policy=evidence["policy"], root=root,
                                expected=expected, now=now, challenge=challenge, sequence_floor=revocation_floor)
        ci = verify_ci_snapshot(evidence["ci"], evidence["ci_signature"], policy=evidence["policy"], root=root,
                                source_head=head, now=now, challenge=challenge, sequence_floor=ci_floor)
        _need(rev["ok"] and ci["ok"], "authenticated revocation/CI evidence unavailable or refused")
        # Bind the E13 release-CI claim to an actually authenticated required run.
        claimed = p["release_evidence"]["exact_head_ci"]
        _need(any(r["run_id"] == claimed["run_id"] and r["job_id"] == claimed["job_id"] and r["job_conclusion"] == claimed["conclusion"]
                  and r["head_sha"] == claimed["head_sha"] for r in ci["runs"]), "E13 CI claim differs from authenticated CI")
        adapters = {
            "signature_verifier": lambda sha, principal, signature: sha == _sha(raw) and principal == researcher and signature == block["signature"],
            "ancestry_checker": lambda reviewed, approval: {"is_ancestor": lineage["is_ancestor"] and reviewed == block["reviewed_code_commit"] and approval == head,
                                                           "changed_paths": lineage["changed_paths"]},
            "revocation_checker": lambda grant: {"revoked": grant != block["revocation_id"], "checked_at": rev["checked_at"]},
        }
        result = P.evaluate_operational_authorization(p, ref, requested_scope=requested_scope, now=now, adapters=adapters)
        _need(Git.read_blob(repo, head, record_path) == raw, "record object changed during verification")
        again = Git.verify_lineage(repo, block["reviewed_code_commit"], head, record_path, expected_record_sha256=_sha(raw), lock=ref.get("lock"))
        _need(again["ok"] is True, "Git checkout changed during verification")
        return {**base, "state": result["state"], "ok": result["state"] == P.STATE_VALID,
                "status": result["state"], "policy_report": result, "signature": signed, "lineage": lineage, "revocation": rev, "ci": ci}
    except Exception as error:
        return {**base, "failures": [str(error)[:200]]}


def ci_authority_check(plan, reference, **context):
    """Scoped CI acceptance is never runtime permission, even for VALID records."""
    report = evaluate_trusted_authorization(plan, reference, **context)
    report["accepted_for_ci"] = report["ok"] and report["state"] in (P.STATE_CLOSED, P.STATE_VALID)
    return report

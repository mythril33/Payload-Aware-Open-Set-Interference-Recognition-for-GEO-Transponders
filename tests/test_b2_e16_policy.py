"""E16 scoped DR-04 operational-authorization policy: approved-shaped and denied states, all synthetic.

The approved-shaped fixture exists only in memory (a fabricated record text, a fabricated gate approval, fake adapters). It is
there to prove that a valid record can be told from forged, partial, stale and contradictory ones. Even the valid fixture ends in
NO-GO: nothing here authorizes, schedules or starts anything, and no canonical gate or scientific record is edited.
"""
import ast
import copy
import hashlib
import importlib.util
import io
import json
import shutil
import sys
from contextlib import redirect_stdout
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
SPEC = importlib.util.spec_from_file_location("b2_e16_policy", ROOT / "scripts/b2_e16_policy.py")
P = importlib.util.module_from_spec(SPEC)
sys.modules["b2_e16_policy"] = P
SPEC.loader.exec_module(P)
from test_b2_e13_generation_plan import (reference, decision_record, k17d_report, complete, gates_with_dr04, record_text,  # noqa: E402,F401
                                         H, HEAD, NOW, RECORD, APPROVER)

G, pre = P.G, P.pre
CLOCK = "2026-10-30T12:05:00+00:00"                        # five minutes after the fixture reference
REVIEWED = "b" * 40
SCOPE = {"gate": "full_generation", "stages": ["known", "test", "matched"]}


def operational_block(plan, **override):
    ceilings = plan["ceilings"]
    block = {"schema": P.SCHEMA_BLOCK, "scope": copy.deepcopy(SCOPE), "approved_by": APPROVER, "expires_at": plan["authorization"]["expires_at"],
             "approved_plan_digest": plan["authorization"]["approved_plan_digest"], "reviewed_code_commit": REVIEWED, "host_id": plan["host"]["host_id"],
             "working_storage_id": plan["working"]["storage_id"], "backup_storage_id": plan["backup"]["storage_id"],
             "ceilings": {k: ceilings[k] for k in P.BLOCK_CEILING_KEYS}, "revocation_id": "rev-2026-11-01",
             "signature": {"scheme": "ssh-signature", "evidence_sha256": H("signature")}}
    block.update(override)
    return block


def seal(plan, ref, text):
    sha = hashlib.sha256(text.encode()).hexdigest()
    plan["authorization"]["record_sha256"] = sha
    ref["record_files"] = {RECORD: sha}
    ref["record_texts"] = {RECORD: text}
    return plan, ref


def approved(ref, **block_override):
    plan = complete(ref)
    text = record_text(plan["authorization"]["approved_plan_digest"]) + "\n```json\n" + json.dumps(operational_block(plan, **block_override)) + "\n```\n"
    return seal(plan, ref, text)


def adapters(**override):
    value = {"signature_verifier": lambda record_sha, signer, signature: True,
             "ancestry_checker": lambda reviewed, head: {"is_ancestor": True, "changed_paths": [pre.GATES_PATH, pre.MEMO_PATH, RECORD]},
             "revocation_checker": lambda revocation_id: {"revoked": False, "checked_at": CLOCK}}
    value.update(override)
    return value


UNSET = object()


def run(plan, ref, *, scope=UNSET, now=CLOCK, adapter=None, **kwargs):
    report = P.evaluate_operational_authorization(plan, ref, requested_scope=copy.deepcopy(SCOPE) if scope is UNSET else scope, now=now,
                                                  adapters=adapters() if adapter is None else adapter, **kwargs)
    json.dumps(report, allow_nan=False)
    assert report["verdict"] == "NO-GO" and report["execution_permitted"] is False and report["authorizes_nothing"] is True
    assert report["production_launch_enabled"] is False and report["benchmark_complete"] is False and report["executor_implemented"] is False
    assert report["scientific_approvals_modified"] is False and report["canonical_gates_modified"] is False
    return report


def failed(report):
    return sorted(i["id"] for i in report["findings"] if i["status"] == P.FAIL)


# ---- canonical gates: closed today ----------------------------------------------------------------------------

def real_documents():
    return tuple(json.loads((ROOT / path).read_text()) for path in (pre.GATES_PATH, pre.MEMO_PATH, G.PROTOCOL_JSON))


def test_the_real_gates_are_canonical_closed_and_the_only_accepted_state():
    report = P.ci_gate_check(*real_documents())
    assert report["state"] == P.STATE_CLOSED and report["accepted_by_this_build"] is True and report["problems"] == []
    assert report["verdict"] == "NO-GO" and report["execution_permitted"] is False


def test_cli_gate_check_accepts_only_the_closed_state(tmp_path, capsys):
    assert P.main(["ci-gate"]) == 0
    assert json.loads(capsys.readouterr().out)["state"] == P.STATE_CLOSED
    copy_root = tmp_path / "repo"
    for path in (pre.GATES_PATH, pre.MEMO_PATH, G.PROTOCOL_JSON):
        (copy_root / path).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / path, copy_root / path)
    assert P.main(["ci-gate", "--repo", str(copy_root)]) == 0
    gates, memo = gates_with_dr04(True)                    # an approved-shaped gate edit alone must not satisfy CI
    (copy_root / pre.GATES_PATH).write_text(json.dumps(gates))
    (copy_root / pre.MEMO_PATH).write_text(json.dumps(memo))
    assert P.main(["ci-gate", "--repo", str(copy_root)]) == 3
    assert json.loads(capsys.readouterr().out.splitlines()[-1])["accepted_by_this_build"] is False
    gates["decisions"]["full_gpu_training"]["status"] = "AUTHORIZED"
    (copy_root / pre.GATES_PATH).write_text(json.dumps(gates))
    assert P.main(["ci-gate", "--repo", str(copy_root)]) == 2
    (copy_root / pre.GATES_PATH).write_text("{")
    assert P.main(["ci-gate", "--repo", str(copy_root)]) == 2
    assert P.main(["ci-gate", "--repo", str(tmp_path / "missing")]) == 2


def test_closed_canonical_state_with_the_correct_scope(reference):
    plan = G.make_template(reference)
    report = run(plan, reference)
    assert report["state"] == P.STATE_CLOSED and failed(report) == []
    assert {i["id"]: i["status"] for i in report["findings"]}["record"] == P.NOT_RUN
    assert report["launch_decision"].startswith("NOT_MADE")


@pytest.mark.parametrize("scope", [
    {"gate": "gpu_probe", "stages": ["known", "test", "matched"]}, {"gate": "full_gpu_training", "stages": ["known", "test", "matched"]},
    {"gate": "full_loko_sweep", "stages": ["known", "test", "matched"]}, {"gate": "held_out_final_evaluation", "stages": ["test"]},
    {"gate": "nine_cell_freeze", "stages": ["known"]}, {"gate": "production_launch_flag_change", "stages": []}, {"gate": "d5_sweep", "stages": []},
    {"gate": "full_generation", "stages": ["known"]}, {"gate": "full_generation", "stages": ["known", "test"]},
    {"gate": "full_generation", "stages": ["matched", "test", "known"]}, {"gate": "full_generation", "stages": ["known", "test", "matched", "train"]},
    {"gate": "full_generation", "stages": ["known", "test", "matched"], "extra": 1}, {"gate": "full_generation"}, "full_generation", None, ["full_generation"], {},
])
def test_every_other_scope_is_refused_in_every_state(reference, scope):
    assert run(G.make_template(reference), reference, scope=scope)["state"] == P.STATE_DENIED
    plan, ref = approved(reference)
    report = run(plan, ref, scope=scope)
    assert report["state"] == P.STATE_DENIED and "scope.request" in failed(report)


def test_refused_scopes_name_every_other_compute_stage():
    assert set(P.REFUSED_SCOPES) == {"gpu_probe", "full_gpu_training", "full_loko_sweep", "nine_cell_freeze", "held_out_final_evaluation",
                                      "production_launch_flag_change", "d5_sweep"}


# ---- approved-shaped record: valid is still NO-GO ----------------------------------------------------------------

def test_a_fully_provenanced_record_is_valid_as_a_document_and_still_launches_nothing(reference):
    plan, ref = approved(reference)
    before = copy.deepcopy((plan, ref))
    report = run(plan, ref)
    assert report["state"] == P.STATE_VALID, [i for i in report["findings"] if i["status"] != P.PASS]
    assert all(i["status"] == P.PASS for i in report["findings"])
    assert report["launch_decision"].startswith("NOT_MADE") and len(report["still_required_before_any_launch"]) == 4
    assert report["details"]["gate_state"] == P.STATE_CANDIDATE and report["details"]["e13_plan_status"] == G.DOCUMENT_OK
    assert (plan, ref) == before
    gates = P.classify_gates(ref["gates"], ref["memo"], ref["scientific_protocol"])
    assert gates["state"] == P.STATE_CANDIDATE and P.ci_gate_check(ref["gates"], ref["memo"], ref["scientific_protocol"])["accepted_by_this_build"] is False


def test_green_ci_scientific_approval_and_a_consistent_plan_without_a_record_are_not_authorization(reference):
    plan, ref = approved(reference)
    plan["authorization"] = None
    assert run(plan, ref)["state"] == P.STATE_DENIED                     # gate claims approval, plan carries none
    ref["gates"], ref["memo"] = gates_with_dr04(False)
    plan2 = G.make_template(ref)
    assert run(plan2, ref)["state"] == P.STATE_CLOSED                    # all science approved, still closed
    plan2["authorization"] = copy.deepcopy(approved(copy.deepcopy(ref))[0]["authorization"])
    assert run(plan2, ref)["state"] == P.STATE_DENIED                    # a record in a plan is not a gate


@pytest.mark.parametrize("name", P.ADAPTER_NAMES)
def test_every_adapter_is_mandatory_for_a_valid_state(reference, name):
    plan, ref = approved(reference)
    remaining = {k: v for k, v in adapters().items() if k != name}
    report = run(plan, ref, adapter=remaining)
    assert report["state"] == P.STATE_DENIED
    assert failed(report) == {"signature_verifier": ["signer.verified"], "ancestry_checker": ["code.unchanged_since_review"],
                              "revocation_checker": ["authorization.not_revoked"]}[name]


@pytest.mark.parametrize("answer", [False, None, 1, "yes", "True", [True], {"ok": True}])
def test_signature_must_be_exactly_true(reference, answer):
    plan, ref = approved(reference)
    assert failed(run(plan, ref, adapter=adapters(signature_verifier=lambda *a: answer))) == ["signer.verified"]


def test_signature_adapter_failure_and_arguments(reference):
    plan, ref = approved(reference)
    seen = []

    def boom(*args):
        raise RuntimeError("verifier unavailable")
    assert failed(run(plan, ref, adapter=adapters(signature_verifier=boom))) == ["signer.verified"]

    def record(sha, signer, signature):
        seen.append((sha, signer, copy.deepcopy(signature)))
        signature["scheme"] = "tampered"                                  # a mutating verifier cannot change what the policy reads
        return True
    assert run(plan, ref, adapter=adapters(signature_verifier=record))["state"] == P.STATE_VALID
    assert seen == [(plan["authorization"]["record_sha256"], APPROVER, {"scheme": "ssh-signature", "evidence_sha256": H("signature")})]


@pytest.mark.parametrize("answer", [
    {"is_ancestor": False, "changed_paths": []},
    {"is_ancestor": True, "changed_paths": ["src/geosim/dataset.py"]},
    {"is_ancestor": True, "changed_paths": [pre.GATES_PATH, "scripts/b2_e16_policy.py"]},
    {"is_ancestor": True, "changed_paths": [".github/workflows/b2-readiness-ci.yml"]},
    {"is_ancestor": True, "changed_paths": ["configs/b2_base.json"]},
    {"is_ancestor": True, "changed_paths": ["tests/test_b2_e16_policy.py"]},
    {"is_ancestor": True, "changed_paths": ["docs/plan/OTHER.md"]},
    {"is_ancestor": True, "changed_paths": ["/etc/passwd"]},
    {"is_ancestor": True, "changed_paths": ["docs/../src/x.py"]},
    {"is_ancestor": True, "changed_paths": [pre.GATES_PATH, pre.GATES_PATH]},
    {"is_ancestor": True, "changed_paths": "docs"}, {"is_ancestor": 1, "changed_paths": []}, {"is_ancestor": True},
    {"is_ancestor": True, "changed_paths": [], "extra": 1}, [], None, "ancestor", {"is_ancestor": True, "changed_paths": [str(i) for i in range(65)]},
])
def test_only_the_gate_its_twin_and_the_record_may_change_after_the_reviewed_commit(reference, answer):
    plan, ref = approved(reference)
    report = run(plan, ref, adapter=adapters(ancestry_checker=lambda reviewed, head: answer))
    assert report["state"] == P.STATE_DENIED and failed(report) == ["code.unchanged_since_review"]


def test_reviewed_commit_cannot_be_the_plan_commit_and_ancestry_failures_deny(reference):
    plan, ref = approved(reference, reviewed_code_commit=HEAD)
    assert failed(run(plan, ref)) == ["code.unchanged_since_review"]
    plan, ref = approved(reference)
    seen = []
    assert run(plan, ref, adapter=adapters(ancestry_checker=lambda r, h: (seen.append((r, h)), {"is_ancestor": True, "changed_paths": [RECORD]})[1]))["state"] == P.STATE_VALID
    assert seen == [(REVIEWED, HEAD)]

    def boom(*args):
        raise OSError("git unavailable")
    assert failed(run(plan, ref, adapter=adapters(ancestry_checker=boom))) == ["code.unchanged_since_review"]


@pytest.mark.parametrize("answer", [
    {"revoked": True, "checked_at": CLOCK}, {"revoked": False, "checked_at": "2026-10-30T10:00:00+00:00"},
    {"revoked": False, "checked_at": "2026-10-30T12:30:00+00:00"}, {"revoked": False, "checked_at": "later"}, {"revoked": False},
    {"revoked": "no", "checked_at": CLOCK}, {"revoked": 0, "checked_at": CLOCK}, {"revoked": False, "checked_at": CLOCK, "extra": 1}, None, [], "no",
])
def test_non_revocation_must_be_freshly_established(reference, answer):
    plan, ref = approved(reference)
    assert failed(run(plan, ref, adapter=adapters(revocation_checker=lambda rid: answer))) == ["authorization.not_revoked"]


def test_revocation_adapter_failure_denies(reference):
    plan, ref = approved(reference)

    def boom(rid):
        raise TimeoutError("revocation list unreachable")
    assert failed(run(plan, ref, adapter=adapters(revocation_checker=boom))) == ["authorization.not_revoked"]


@pytest.mark.parametrize("bad", [{"extra": 1}, {"signature_verifier": "yes"}, {"execute": lambda: None}, {"launcher": lambda: None}])
def test_unknown_or_non_callable_adapters_are_refused(reference, bad):
    plan, ref = approved(reference)
    assert run(plan, ref, adapter=dict(adapters(), **bad))["state"] == P.STATE_DENIED


# ---- record content, forgery, contradiction --------------------------------------------------------------------

def block_mutations():
    yield "scope_stage", lambda b: b["scope"].update(stages=["known"])
    yield "scope_gate", lambda b: b["scope"].update(gate="full_gpu_training")
    yield "approver", lambda b: b.update(approved_by="someone-else")
    yield "expiry", lambda b: b.update(expires_at="2026-12-01T00:00:00Z")
    yield "digest", lambda b: b.update(approved_plan_digest=H("other design"))
    yield "host", lambda b: b.update(host_id="other-host")
    yield "working", lambda b: b.update(working_storage_id="disk-X")
    yield "backup", lambda b: b.update(backup_storage_id="disk-X")
    for key in P.BLOCK_CEILING_KEYS:
        yield f"ceiling_{key}", (lambda k: lambda b: b["ceilings"].update({k: b["ceilings"][k] + 1}))(key)
        yield f"ceiling_drop_{key}", (lambda k: lambda b: b["ceilings"].pop(k))(key)
    yield "ceiling_extra", lambda b: b["ceilings"].update(extra=1)
    yield "reviewed_short", lambda b: b.update(reviewed_code_commit="b" * 39)
    yield "reviewed_upper", lambda b: b.update(reviewed_code_commit="B" * 40)
    yield "revocation_blank", lambda b: b.update(revocation_id="")
    yield "revocation_space", lambda b: b.update(revocation_id=" rev")
    yield "revocation_long", lambda b: b.update(revocation_id="r" * 121)
    yield "scheme", lambda b: b["signature"].update(scheme="none")
    yield "evidence", lambda b: b["signature"].update(evidence_sha256="abc")
    yield "signature_extra", lambda b: b["signature"].update(extra=1)
    yield "signature_missing", lambda b: b.pop("signature")
    yield "extra_field", lambda b: b.update(extra=1)
    yield "missing_field", lambda b: b.pop("revocation_id")


@pytest.mark.parametrize("label,change", list(block_mutations()), ids=[x[0] for x in block_mutations()])
def test_every_field_of_the_operational_block_is_enforced(reference, label, change):
    plan = complete(reference)
    block = operational_block(plan)
    change(block)
    text = record_text(plan["authorization"]["approved_plan_digest"]) + "\n```json\n" + json.dumps(block) + "\n```\n"
    plan, ref = seal(plan, reference, text)
    report = run(plan, ref)
    assert report["state"] == P.STATE_DENIED and failed(report), label


def test_missing_duplicate_or_quoted_blocks_are_refused(reference):
    plan = complete(reference)
    digest = plan["authorization"]["approved_plan_digest"]
    base = record_text(digest)
    block = json.dumps(operational_block(plan))
    for text in (base,
                 base + "\n```json\n" + block + "\n```\n" + "\n```json\n" + block + "\n```\n",
                 base + "\n````json\n" + block + "\n````\n",
                 base + "\n```json\n" + block + "\n",
                 base + "\n```yaml\n" + block + "\n```\n",
                 base + "\n```json\n" + block.replace('"scope"', '"scope", "scope"') + "\n```\n"):
        plan2, ref2 = seal(copy.deepcopy(plan), copy.deepcopy(reference), text)
        assert run(plan2, ref2)["state"] == P.STATE_DENIED


def test_record_text_must_be_the_hashed_document(reference):
    plan, ref = approved(reference)
    ref["record_texts"][RECORD] += " "
    assert "record.bytes_match_hash" in failed(run(plan, ref))
    plan, ref = approved(reference)
    ref["record_texts"][RECORD] = ref["record_texts"][RECORD][:-30]
    assert "record.bytes_match_hash" in failed(run(plan, ref))
    plan, ref = approved(reference)
    plan["authorization"]["record_sha256"] = H("different record")
    assert run(plan, ref)["state"] == P.STATE_DENIED
    plan, ref = approved(reference)
    ref["record_texts"][RECORD] = "x" * (P.MAX_RECORD_CHARS + 1)
    assert "record.bytes_match_hash" in failed(run(plan, ref))
    plan, ref = approved(reference)
    ref["record_texts"] = {}
    assert "record.bytes_match_hash" in failed(run(plan, ref))


def test_contradictory_records_are_refused(reference):
    for field, value in (("approved_by", "intruder"), ("decision", "another decision"), ("approved_at", "2026-10-28T08:00:00Z"), ("record", "docs/other.md")):
        plan, ref = approved(copy.deepcopy(reference))
        plan["authorization"][field] = value
        assert run(plan, ref)["state"] == P.STATE_DENIED, field
    plan, ref = approved(reference)
    ref["memo"]["decisions"]["full_generation"]["approved_by"] = "intruder"
    assert run(plan, ref)["state"] == P.STATE_DENIED
    plan, ref = approved(reference)
    ref["gates"]["decisions"]["full_generation"]["status"] = "NOT_AUTHORIZED"
    assert run(plan, ref)["state"] == P.STATE_DENIED


def test_gate_opened_without_provenance_or_with_other_compute_gates_is_denied(reference):
    plan, ref = approved(reference)
    ref["gates"]["decisions"]["full_generation"]["approval"].pop("core_hours")
    assert run(plan, ref)["state"] == P.STATE_DENIED
    for gate in P.COMPUTE_GATES_STAYING_CLOSED:
        plan, ref = approved(copy.deepcopy(reference))             # opened consistently in the gate AND its twin: only this policy catches it
        for source in ("gates", "memo"):
            ref[source]["decisions"][gate]["status"] = "AUTHORIZED"
        assert run(plan, ref)["state"] == P.STATE_DENIED, gate
        assert any("not exactly NOT_AUTHORIZED" in problem for problem in P.classify_gates(ref["gates"], ref["memo"], ref["scientific_protocol"])["problems"])
        for source in ("gates", "memo"):
            plan, ref = approved(copy.deepcopy(reference))
            ref[source]["decisions"][gate]["status"] = "AUTHORIZED"
            assert run(plan, ref)["state"] == P.STATE_DENIED, (gate, source)
        plan, ref = approved(copy.deepcopy(reference))
        ref["gates"]["decisions"][gate]["approval"] = {"approved_by": APPROVER}
        assert run(plan, ref)["state"] == P.STATE_DENIED
    for status in ("AUTHORIZED_PARTIAL", "PENDING", "", None, 1):
        plan, ref = approved(copy.deepcopy(reference))
        ref["gates"]["decisions"]["full_generation"]["status"] = status
        assert run(plan, ref)["state"] == P.STATE_DENIED, status


def test_scientific_approvals_must_stay_intact_and_unrelated_flags_stay_false(reference):
    mutations = [lambda r: r["gates"]["decisions"]["K18"].update(status="NOT_AUTHORIZED"),
                 lambda r: r["memo"]["decisions"]["K17d"].update(approved_by="intruder"),
                 lambda r: r["gates"].update(benchmark_complete=True),
                 lambda r: r["scientific_protocol"].update(production_authorized=True),
                 lambda r: r["scientific_protocol"].update(activation=True),
                 lambda r: r["scientific_protocol"]["unresolved_operational_decisions"].update(gpu_probe="AUTHORIZED"),
                 lambda r: r["scientific_protocol"]["unresolved_operational_decisions"].update(production_launch="ENABLED"),
                 lambda r: r["gates"]["decisions"]["merge_to_main"].update(status="AUTHORIZED"),
                 lambda r: r["memo"]["decisions"]["K18"].update(approved_at="2026-01-01T00:00:00Z"),
                 lambda r: r["memo"]["decisions"]["OBS-CANCEL-2"].update(approved_by=None),
                 lambda r: r["gates"]["decisions"]["K17d"]["approval"].update(decision=" "),
                 lambda r: r["scientific_protocol"]["decisions"]["K17d"].update(choice="B"),
                 lambda r: r["scientific_protocol"]["decisions"].pop("R1"),
                 lambda r: r["scientific_protocol"].update(approved_by="someone-else")]
    for index, mutate in enumerate(mutations):
        plan, ref = approved(copy.deepcopy(reference))
        mutate(ref)
        assert run(plan, ref)["state"] == P.STATE_DENIED, index


def test_stale_future_and_expired_evidence_is_refused(reference):
    plan, ref = approved(reference)
    assert run(plan, ref, now="2026-10-30T13:30:00+00:00", adapter=adapters(revocation_checker=lambda r: {"revoked": False, "checked_at": "2026-10-30T13:30:00+00:00"}))["state"] == P.STATE_DENIED
    assert "evidence.fresh" in failed(run(plan, ref, now="2026-10-30T11:00:00+00:00"))
    assert "evidence.fresh" in failed(run(plan, ref, max_reference_age_s=60))
    assert run(plan, ref, max_reference_age_s=600)["state"] == P.STATE_VALID
    expiry = plan["authorization"]["expires_at"]
    late = "2026-11-20T00:00:00+00:00"
    ref["evaluated_at"] = late
    assert "authorization.unexpired" in failed(run(plan, ref, now=late, adapter=adapters(revocation_checker=lambda r: {"revoked": False, "checked_at": late})))
    assert expiry.startswith("2026-11-20")
    for bad in ("soon", "2026-10-30T12:05:00", None, 5, "", "2026-13-40T00:00:00Z"):
        assert run(*approved(copy.deepcopy(reference)), now=bad)["state"] == P.STATE_DENIED
    for bad in (0, -1, 86401, True, 1.5, None):
        assert run(*approved(copy.deepcopy(reference)), max_reference_age_s=bad)["state"] == P.STATE_DENIED


def test_e13_failures_propagate_as_denial(reference):
    cases = [lambda p, r: r.update(tree_clean=False), lambda p, r: p.update(lock=None), lambda p, r: r.update(head="c" * 40),
             lambda p, r: p["ceilings"].update(wall_hours=1), lambda p, r: p.update(host=None),
             lambda p, r: r["environment"].update(python="3.11.0"), lambda p, r: r.update(lock_problems=["stale lock"]),
             lambda p, r: p["source"]["files_sha256"].update({"src/geosim/alpha.py": "0" * 64}),
             lambda p, r: p["release_evidence"].update(self_asserted=False)]
    for index, change in enumerate(cases):
        plan, ref = approved(copy.deepcopy(reference))
        change(plan, ref)
        assert run(plan, ref)["state"] == P.STATE_DENIED, index


def test_every_authorization_field_is_enforced(reference):
    base_plan, base_ref = approved(reference)
    for key in G.AUTH_KEYS:
        plan, ref = copy.deepcopy(base_plan), copy.deepcopy(base_ref)
        if key == "does_not_grant":
            plan["authorization"][key] = plan["authorization"][key][:-1]
        elif key == "grants":
            plan["authorization"][key] = ["full_generation", "full_gpu_training"]
        else:
            plan["authorization"][key] = None
        assert run(plan, ref)["state"] == P.STATE_DENIED, key
        plan2, ref2 = copy.deepcopy(base_plan), copy.deepcopy(base_ref)
        plan2["authorization"].pop(key)
        assert run(plan2, ref2)["state"] == P.STATE_DENIED, key


def test_hostile_inputs_become_findings_not_crashes_or_approvals(reference):
    plan, ref = approved(reference)
    nested = value = {}
    for _ in range(200):
        value["x"] = {}
        value = value["x"]
    for bad_plan, bad_ref in ((None, ref), ([], ref), (plan, None), (plan, "x"), (dict(plan, extra=nested), ref), (plan, dict(ref, extra=float("nan"))),
                              (plan, dict(ref, extra=object())), ({}, {})):
        assert run(bad_plan, bad_ref)["state"] == P.STATE_DENIED


# ---- release order ----------------------------------------------------------------------------------------------

def events(**override):
    base = [{"step": "final_reviewed_code", "at": "2026-10-30T09:00:00Z", "commit": REVIEWED},
            {"step": "design_digest", "at": "2026-10-30T09:10:00Z", "digest": H("design")},
            {"step": "researcher_authorization", "at": "2026-10-30T10:00:00Z", "digest": H("design")},
            {"step": "authorization_commit", "at": "2026-10-30T10:05:00Z", "commit": "c" * 40, "parent": REVIEWED},
            {"step": "final_lock", "at": "2026-10-30T10:30:00Z", "commit": "c" * 40, "lock_fingerprint": H("lock")},
            {"step": "revalidation", "at": "2026-10-30T11:00:00Z", "digest": H("design"), "lock_fingerprint": H("lock")}]
    for step, change in override.items():
        for event in base:
            if event["step"] == step:
                event.update(change)
    return base


def test_release_order_accepts_the_documented_sequence_and_records_no_launch():
    report = P.check_release_order(events())
    assert report["ok"] is True and report["next_step"] == "launch_decision" and report["launch_decision_recorded"] is False
    assert report["omits_no_hash"] is True and report["execution_permitted"] is False
    for count in range(len(events()) + 1):
        assert P.check_release_order(events()[:count])["ok"] is True


@pytest.mark.parametrize("label,build", [
    ("swapped", lambda: [events()[1], events()[0]] + events()[2:]),
    ("repeated", lambda: events() + [events()[5]]),
    ("skipped_digest", lambda: [e for e in events() if e["step"] != "design_digest"]),
    ("skipped_commit", lambda: [e for e in events() if e["step"] != "authorization_commit"]),
    ("time_travel", lambda: events(final_lock={"at": "2026-10-30T09:30:00Z"})),
    ("digest_changed_after_approval", lambda: events(revalidation={"digest": H("edited design")})),
    ("digest_changed_before_approval", lambda: events(researcher_authorization={"digest": H("edited design")})),
    ("not_a_child", lambda: events(authorization_commit={"parent": "d" * 40})),
    ("lock_on_other_commit", lambda: events(final_lock={"commit": "e" * 40})),
    ("lock_not_used", lambda: events(revalidation={"lock_fingerprint": H("other lock")})),
    ("launch_recorded", lambda: events() + [{"step": "launch_decision", "at": "2026-10-30T12:00:00Z"}]),
    ("unknown_step", lambda: events() + [{"step": "start_now", "at": "2026-10-30T12:00:00Z"}]),
    ("bad_time", lambda: events(final_lock={"at": "soon"})),
    ("short_commit", lambda: events(final_reviewed_code={"commit": "b" * 8})),
    ("missing_digest", lambda: events(design_digest={"digest": None})),
    ("not_a_list", lambda: {"step": "final_reviewed_code"}),
    ("too_many", lambda: events() * 6),
    ("not_dicts", lambda: ["final_reviewed_code"]),
])
def test_release_order_violations_are_refused(label, build):
    report = P.check_release_order(build())
    assert report["ok"] is False and report["problems"], label
    assert report["execution_permitted"] is False


# ---- structure ---------------------------------------------------------------------------------------------------

def test_policy_has_no_process_environment_or_file_writing_surface():
    tree = ast.parse((ROOT / "scripts/b2_e16_policy.py").read_text())
    imported = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    imported |= {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    assert not imported & {"subprocess", "multiprocessing", "socket", "shutil", "ctypes", "os", "time", "platform", "importlib"}
    attributes = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    assert not attributes & {"system", "popen", "Popen", "run", "environ", "getenv", "write_text", "write_bytes", "unlink", "rename", "now", "utcnow"}
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    assert not names & {"eval", "exec", "compile", "__import__", "open"}


def test_this_build_cannot_be_made_to_launch_by_any_valid_document(reference):
    plan, ref = approved(reference)
    assert run(plan, ref)["state"] == P.STATE_VALID
    assert G.sup.PRODUCTION_LAUNCH_ENABLED is False
    with pytest.raises(G.e9.ExecutionNotAuthorized):
        G.e9.guard_execution("generation")
    with pytest.raises(P.C.ExecutionUnavailable):
        P.C.deny_execution(plan["authorization"], plan, ref)


# ---- review findings E16-01 and E16-05 ------------------------------------------------------------------------------------

@pytest.mark.parametrize("extra", [
    {"gpu_training": {"module": "geoml.train", "options": {"device": "cuda", "epochs": 30}}},
    {"known2": {"module": "geosim.b2_dataset", "options": {}}}, {"": None}, {"loko": {}},
])
def test_an_extra_stage_cannot_ride_along_in_the_standalone_api(reference, extra):
    plan, ref = approved(reference)
    assert run(plan, ref)["state"] == P.STATE_VALID
    evil = copy.deepcopy(plan)
    evil["stages"].update(copy.deepcopy(extra))
    report = run(evil, ref)
    assert report["state"] == P.STATE_DENIED and "input" in failed(report)
    closed = G.make_template(reference)
    closed["stages"].update(copy.deepcopy(extra))
    assert run(closed, reference)["state"] == P.STATE_DENIED


def test_missing_or_renamed_stages_are_denied(reference):
    plan, ref = approved(reference)
    for change in (lambda p: p["stages"].pop("matched"), lambda p: p["stages"].update(matched=p["stages"].pop("test")), lambda p: p.update(stages={})):
        evil = copy.deepcopy(plan)
        change(evil)
        assert run(evil, ref)["state"] == P.STATE_DENIED


def write_repo(tmp_path, gates, memo, protocol, raw=None):
    root = tmp_path / "repo"
    for path, value in ((pre.GATES_PATH, gates), (pre.MEMO_PATH, memo), (G.PROTOCOL_JSON, protocol)):
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        (root / path).write_text(raw[path] if raw and path in raw else json.dumps(value))
    return root


def real_json():
    return tuple(json.loads((ROOT / path).read_text()) for path in (pre.GATES_PATH, pre.MEMO_PATH, G.PROTOCOL_JSON))


def test_ci_gate_reads_strictly_and_rejects_duplicate_keys(tmp_path, capsys):
    gates, memo, protocol = real_json()
    text = (ROOT / pre.GATES_PATH).read_text()
    duplicated = text.replace('"full_generation": {', '"full_generation": {"status": "AUTHORIZED"}, "full_generation": {', 1)
    assert duplicated != text and json.loads(duplicated) == gates          # a lenient reader would keep the last, closed, value
    root = write_repo(tmp_path, gates, memo, protocol, raw={pre.GATES_PATH: duplicated})
    assert P.main(["ci-gate", "--repo", str(root)]) == 2
    assert P.main(["ci-gate", "--repo", str(write_repo(tmp_path / "ok", gates, memo, protocol))]) == 0
    big = write_repo(tmp_path / "big", gates, memo, protocol, raw={pre.GATES_PATH: '{"x": "' + "a" * P.MAX_DOCUMENT_BYTES + '"}'})
    assert P.main(["ci-gate", "--repo", str(big)]) == 2
    nan = write_repo(tmp_path / "nan", gates, memo, protocol, raw={pre.GATES_PATH: '{"benchmark_complete": NaN}'})
    assert P.main(["ci-gate", "--repo", str(nan)]) == 2
    linked = write_repo(tmp_path / "link", gates, memo, protocol)
    (linked / pre.GATES_PATH).unlink()
    (linked / pre.GATES_PATH).symlink_to(ROOT / pre.GATES_PATH)
    assert P.main(["ci-gate", "--repo", str(linked)]) == 2


@pytest.mark.parametrize("label,change", [
    ("gpu_probe_decision_open", lambda g, m, p: g["decisions"].update(gpu_probe={"status": "AUTHORIZED", "approval": None})),
    ("nine_cell_freeze_open", lambda g, m, p: g["decisions"].update(nine_cell_freeze={"status": "APPROVED", "approval": None})),
    ("memo_extra_open_decision", lambda g, m, p: m["decisions"].update(held_out_final_evaluation={"status": "AUTHORIZED"})),
    ("protocol_gpu_training_open", lambda g, m, p: p["unresolved_operational_decisions"].update(full_gpu_training="AUTHORIZED")),
    ("protocol_loko_open", lambda g, m, p: p["unresolved_operational_decisions"].update(full_loko_sweep="AUTHORIZED")),
    ("protocol_generation_open", lambda g, m, p: p["unresolved_operational_decisions"].update(full_generation="AUTHORIZED")),
    ("protocol_probe_open", lambda g, m, p: p["unresolved_operational_decisions"].update(gpu_probe="AUTHORIZED")),
    ("protocol_control_false", lambda g, m, p: p["controls"].update(no_gpu_use=False)),
    ("protocol_controls_empty", lambda g, m, p: p.update(controls={})),
    ("protocol_extra_field", lambda g, m, p: p.update(production_launch_enabled=True)),
    ("memo_extra_field", lambda g, m, p: m.update(production_launch_enabled=True)),
    ("gates_launch_field", lambda g, m, p: g.update(production_launch_enabled=True)),
    ("gates_execute_field", lambda g, m, p: g.update(execute_now=True)),
    ("decision_launcher_field", lambda g, m, p: g["decisions"]["full_generation"].update(launcher="run.sh")),
    ("memo_decision_argv", lambda g, m, p: m["decisions"]["full_generation"].update(argv=["python"])),
])
def test_ci_gate_is_an_enumerated_check_and_rejects_every_enumerated_opening(tmp_path, label, change):
    gates, memo, protocol = real_json()
    change(gates, memo, protocol)
    report = P.ci_gate_check(gates, memo, protocol)
    assert report["state"] == P.STATE_DENIED and report["accepted_by_this_build"] is False, label
    assert P.main(["ci-gate", "--repo", str(write_repo(tmp_path, gates, memo, protocol))]) == 2


@pytest.mark.parametrize("label,change", [
    ("gpu_probe_status_open", lambda g, m, p: g["decisions"].update(gpu_probe={"status": "OPEN", "approval": None})),
    ("gpu_probe_granted", lambda g, m, p: g["decisions"].update(gpu_probe={"status": "GRANTED", "approval": None})),
    ("gpu_probe_true", lambda g, m, p: g["decisions"].update(gpu_probe={"status": True})),
    ("decision_without_status", lambda g, m, p: g["decisions"].update(gpu_probe={})),
    ("memo_extra_decision", lambda g, m, p: m["decisions"].update(gpu_probe={"status": "APPROVED"})),
    ("generation_extra_key", lambda g, m, p: g["decisions"]["full_generation"].update(go=True)),
    ("compute_gate_extra_key", lambda g, m, p: g["decisions"]["full_loko_sweep"].update(note="ok")),
    ("memo_decision_extra_key", lambda g, m, p: m["decisions"]["full_generation"].update(go=True)),
    ("memo_decision_missing_key", lambda g, m, p: m["decisions"]["full_generation"].pop("authority")),
    ("missing_decision", lambda g, m, p: g["decisions"].pop("merge_to_main")),
    ("controls_key_missing", lambda g, m, p: p["controls"].pop("no_training")),
    ("controls_key_extra", lambda g, m, p: p["controls"].update(extra=True)),
])
def test_decision_and_control_sets_are_allow_listed_not_deny_listed(label, change):
    gates, memo, protocol = real_json()
    change(gates, memo, protocol)
    report = P.ci_gate_check(gates, memo, protocol)
    assert report["state"] == P.STATE_DENIED and report["accepted_by_this_build"] is False, label


def test_the_allow_lists_equal_the_real_documents_today():
    gates, memo, protocol = real_json()
    assert {k: set(v) for k, v in gates["decisions"].items()} == P.GATE_DECISION_KEYS
    assert {k: set(v) for k, v in memo["decisions"].items()} == P.MEMO_DECISION_KEYS
    assert set(protocol["controls"]) == P.CONTROL_KEYS and set(protocol) == P.PROTOCOL_KEYS and set(memo) == P.MEMO_KEYS

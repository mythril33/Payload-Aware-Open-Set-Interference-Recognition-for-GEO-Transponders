#!/usr/bin/env python3
"""E16 scoped DR-04 operational-authorization policy. Classifies documents; it never authorizes or launches anything.

Three things are kept apart on purpose:

* the **scientific approvals** (K18, K17d, OBS-CANCEL-2, R1-R10, D-1..D-8): immutable history, never touched here;
* the **canonical gates**: today ``full_generation``, ``full_gpu_training`` and ``full_loko_sweep`` are all
  ``NOT_AUTHORIZED``; the readiness CI asserts exactly that, and this module does not edit that workflow;
* the **DR-04 operational record**: a researcher-written, committed record that could one day open *only* the
  ``full_generation`` gate for the three frozen stages. ``evaluate_operational_authorization`` tells an
  approved-shaped, fully provenanced record from a forged, partial, stale or contradictory one.

A valid record yields the state ``DR04_GENERATION_RECORD_VALID``, which is a statement about documents. The report still
says NO-GO: launching needs a separate decision, a reviewed executor that does not exist, and
``PRODUCTION_LAUNCH_ENABLED`` (False). Nothing here reads the environment, runs a process or touches a host.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import b2_e13_generation_plan as G
import b2_e14_launch_contract as C
import b2_e14_storage as S
import b2_production_preflight as pre

SCHEMA_BLOCK = "B2-E16-dr04-operational-block/1"
SCHEMA_REPORT = "B2-E16-operational-authorization-report/1"
SCHEMA_GATES = "B2-E16-gate-state-report/1"
SCHEMA_ORDER = "B2-E16-release-order-report/1"
STATE_CLOSED = "CLOSED_CANONICAL"
STATE_CANDIDATE = "OPEN_CANDIDATE_REQUIRES_RECORD"
STATE_VALID = "DR04_GENERATION_RECORD_VALID"
STATE_DENIED = "DENIED"
PASS, FAIL, NOT_RUN = "PASS", "FAIL", "NOT_RUN"
STAGES = ("known", "test", "matched")
GRANTED_SCOPE = {"gate": "full_generation", "stages": list(STAGES)}
REFUSED_SCOPES = ("gpu_probe", "full_gpu_training", "full_loko_sweep", "nine_cell_freeze", "held_out_final_evaluation",
                  "production_launch_flag_change", "d5_sweep")
SIGNATURE_SCHEMES = ("git-signed-commit", "ssh-signature", "gpg-detached-signature")
BLOCK_KEYS = ("schema", "scope", "approved_by", "expires_at", "approved_plan_digest", "reviewed_code_commit", "host_id",
              "working_storage_id", "backup_storage_id", "ceilings", "revocation_id", "signature")
BLOCK_CEILING_KEYS = ("wall_hours", "core_hours", "max_rss_gib", "min_free_disk_gib", "backup_disk_gb",
                      "max_failed_attempts_per_stage", "max_interruptions_per_stage")
ADAPTER_NAMES = ("signature_verifier", "ancestry_checker", "revocation_checker")
CODE_ROOTS = ("src", "scripts", "configs", "tests", ".github", "pyproject.toml")
COMPUTE_GATES_STAYING_CLOSED = ("full_gpu_training", "full_loko_sweep")
SCIENTIFIC_GATES = ("K18", "K17d", "OBS-CANCEL-2")
MEMO_KEYS = frozenset({"schema", "benchmark_complete", "decisions"})
PROTOCOL_KEYS = frozenset({"schema", "status", "scientific_approval", "activation", "production_authorized", "benchmark_complete", "approved_by", "approved_at",
                           "source_main_sha", "approval_record", "source_candidate", "profile_id", "decisions", "parameter_records",
                           "unresolved_operational_decisions", "controls"})
GATE_DECISION_KEYS = {"K18": {"approval", "observed", "proposal", "status"}, "K17d": {"approval", "observed", "proposal", "status"},
                      "OBS-CANCEL-2": {"approval", "observed", "proposal", "status"}, "full_generation": {"approval", "estimate", "status"},
                      "full_gpu_training": {"approval", "status"}, "full_loko_sweep": {"approval", "status"}, "merge_to_main": {"approval", "status"}}
MEMO_DECISION_KEYS = {name: {"approved_at", "approved_by", "authority", "record", "status"} for name in
                      ("K18", "K17d", "OBS-CANCEL-2", "full_generation", "full_gpu_training", "full_loko_sweep")}
CONTROL_KEYS = frozenset({"no_data_generation", "no_gpu_use", "no_loko", "no_runner_consumes_this_file", "no_test_read", "no_training", "not_under_configs"})
GATES_TOP_FORBIDDEN = ("launch", "execut", "authorized", "enabled")     # substrings no top-level key of the living gates document may carry
MAX_DOCUMENT_BYTES = 4 * 2 ** 20
# The scientific half of the readiness CI step, restated: the existing validators compare twin *status* only.
SCIENTIFIC_CHOICES = {"K18": "A", "K17d": "A+C", "OBS-CANCEL-2": "A"}
HEX40, HEX64 = re.compile(r"[0-9a-f]{40}\Z"), re.compile(r"[0-9a-f]{64}\Z")
MAX_RECORD_CHARS = 256 * 1024
RELEASE_STEPS = ("final_reviewed_code", "design_digest", "researcher_authorization", "authorization_commit", "final_lock",
                 "revalidation", "launch_decision")
NO_AUTHORITY = {"verdict": "NO-GO", "execution_permitted": False, "authorizes_nothing": True, "production_launch_enabled": False,
                "benchmark_complete": False, "executor_implemented": False}
STILL_REQUIRED = ("a separate launch decision by the researcher after final lock revalidation",
                  "an independently reviewed production executor (none exists; E9 guard_execution and E14 deny_execution always raise)",
                  "a separately reviewed change that sets PRODUCTION_LAUNCH_ENABLED, with its own review and CI",
                  "the designated host, an independent persistent backup, run-bound ceilings and the external journal, all measured")


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _same(left, right):
    return canonical(left) == canonical(right)


class _Findings:
    def __init__(self):
        self.items = []

    def add(self, identifier, status, message):
        self.items.append({"id": identifier, "status": status, "message": message})

    def check(self, identifier, condition, message):
        self.add(identifier, PASS if condition else FAIL, message if condition else "does not hold: " + message)
        return bool(condition)

    def fail(self, identifier, message):
        self.add(identifier, FAIL, message)

    @property
    def failed(self):
        return [item["id"] for item in self.items if item["status"] == FAIL]


def _text(value):
    return isinstance(value, str) and bool(value) and value.strip() == value and all(ord(c) >= 32 for c in value)


def _number_equal(a, b):
    return (isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool) and not isinstance(b, bool)
            and math.isfinite(a) and math.isfinite(b) and float(a) == float(b))


# ---- gate classification (no record needed) -------------------------------------------------------------------

def _decision(source, key):
    decisions = source.get("decisions") if isinstance(source, dict) else None
    entry = decisions.get(key) if isinstance(decisions, dict) else None
    return entry if isinstance(entry, dict) else {}


def classify_gates(gates, memo, protocol):
    """State of the canonical gates. ``CLOSED_CANONICAL`` is the only state the current CI and this build accept."""
    problems = []
    try:
        if not (isinstance(gates, dict) and isinstance(memo, dict) and isinstance(protocol, dict)):
            raise ValueError("gate documents must be objects")
        if not (gates.get("benchmark_complete") is memo.get("benchmark_complete") is protocol.get("benchmark_complete") is False):
            problems.append("benchmark_complete is not False in every document")
        if protocol.get("activation") is not False or protocol.get("production_authorized") is not False:
            problems.append("the scientific protocol record claims activation or production authorization")
        unresolved = protocol.get("unresolved_operational_decisions") if isinstance(protocol.get("unresolved_operational_decisions"), dict) else {}
        if (any(unresolved.get(k) != "NOT_AUTHORIZED" for k in ("full_generation", "gpu_probe", *COMPUTE_GATES_STAYING_CLOSED))
                or unresolved.get("production_launch") != "DISABLED"):
            problems.append("the immutable scientific record does not hold every compute stage NOT_AUTHORIZED and production launch DISABLED")
        controls = protocol.get("controls")
        if not isinstance(controls, dict) or set(controls) != CONTROL_KEYS or any(v is not True for v in controls.values()):
            problems.append("the scientific record's controls (no data generation, GPU, training, LOKO or test read) are not all true")
        if set(protocol) != PROTOCOL_KEYS or set(memo) != MEMO_KEYS:
            problems.append("the immutable memorandum or scientific record carries unexpected or missing top-level fields")
        if any(isinstance(k, str) and any(s in k.lower() for s in GATES_TOP_FORBIDDEN) for k in gates):
            problems.append("the readiness JSON carries a launch/execution/authorization/enabled top-level field")
        for label, source, allowed in (("readiness JSON", gates, GATE_DECISION_KEYS), ("memorandum", memo, MEMO_DECISION_KEYS)):
            decisions = source.get("decisions") if isinstance(source.get("decisions"), dict) else {}
            if set(decisions) != set(allowed) or any(not isinstance(decisions[k], dict) or set(decisions[k]) != allowed[k] for k in decisions if k in allowed):
                problems.append(f"the {label} decisions are not exactly the reviewed set of decisions and fields")
            opened = sorted(k for k, v in decisions.items() if isinstance(v, dict) and v.get("status") in pre.APPROVED_STATUSES)
            if set(opened) - set(SCIENTIFIC_GATES) - {"full_generation"}:
                problems.append(f"an unexpected decision is open in the {label}: {sorted(set(opened) - set(SCIENTIFIC_GATES) - {'full_generation'})[:3]}")
            if G._forbidden_keys(decisions):
                problems.append(f"the {label} decisions carry execution, launcher or override fields")
        merge = _decision(gates, "merge_to_main")
        if merge.get("status") != "NOT_AUTHORIZED_BY_THIS_PLAN" or merge.get("approval") is not None:
            problems.append("merge_to_main is not closed")
        problems += G.e9.scientific_gate_problems(gates, protocol) + G.e9.memo_twin_problems(gates, memo)
        decisions = protocol.get("decisions")
        if not isinstance(decisions, dict) or len(decisions) != 13:
            problems.append("the scientific protocol does not hold its 13 ratified decisions")
        for key, choice in SCIENTIFIC_CHOICES.items():
            gate, twin = _decision(gates, key), _decision(memo, key)
            approval = gate.get("approval") if isinstance(gate.get("approval"), dict) else {}
            entry = decisions.get(key) if isinstance(decisions, dict) and isinstance(decisions.get(key), dict) else {}
            if not (gate.get("status") == twin.get("status") == "APPROVED" and entry.get("choice") == choice and _text(approval.get("decision"))
                    and approval.get("approved_by") == twin.get("approved_by") == protocol.get("approved_by")
                    and approval.get("approved_at") == twin.get("approved_at") == protocol.get("approved_at")
                    and approval.get("record") == protocol.get("approval_record")):
                problems.append(f"scientific approval {key} differs between the gate, its memorandum twin and the ratified protocol")
        for key in COMPUTE_GATES_STAYING_CLOSED:
            for source, label in ((gates, "readiness JSON"), (memo, "memorandum")):
                entry = _decision(source, key)
                if (entry.get("status") != "NOT_AUTHORIZED" or entry.get("approval") not in (None, {})
                        or entry.get("approved_by") not in (None, "") or entry.get("approved_at") not in (None, "")):
                    problems.append(f"{key} is not exactly NOT_AUTHORIZED in the {label}")
        gate, twin = _decision(gates, "full_generation"), _decision(memo, "full_generation")
        closed = (gate.get("status") == twin.get("status") == "NOT_AUTHORIZED" and gate.get("approval") is None
                  and twin.get("approved_by") is None and twin.get("approved_at") is None)
        approval = gate.get("approval")
        opened = (gate.get("status") in pre.APPROVED_STATUSES and twin.get("status") == gate.get("status") and isinstance(approval, dict)
                  and not pre.approval_problems(approval, True) and twin.get("approved_by") == approval.get("approved_by")
                  and twin.get("approved_at") == approval.get("approved_at") and twin.get("record") == approval.get("record"))
        if not closed and not opened:
            problems.append("full_generation gate and memorandum twin are neither exactly closed nor consistently approved with provenance")
    except (ValueError, TypeError, KeyError, AttributeError, RecursionError) as error:
        problems.append("gate documents could not be evaluated: " + type(error).__name__)
        closed = opened = False
    state = STATE_DENIED if problems else STATE_CLOSED if closed else STATE_CANDIDATE
    return {"schema": SCHEMA_GATES, "state": state, "problems": problems, "scientific_approvals_modified": False,
            "canonical_gates_modified": False, **NO_AUTHORITY}


# ---- the committed record ---------------------------------------------------------------------------------------

def _blocks_of(text, schema):
    """Fenced strict-JSON objects of one schema: a line that is exactly three backticks plus ``json`` opens, three close."""
    blocks, current = [], None
    for line in (text if isinstance(text, str) else "").replace("\r\n", "\n").split("\n"):
        if current is None:
            if line.rstrip(" \t") == "```json":
                current = []
        elif line == "```":
            try:
                block = S._strict("\n".join(current).encode("utf-8"))
            except (S.StorageRefused, RecursionError, UnicodeError, ValueError):
                block = None
            if isinstance(block, dict) and block.get("schema") == schema:
                blocks.append(block)
            current = None
        else:
            current.append(line)
    return blocks


def _adapters(adapters):
    adapters = {} if adapters is None else adapters
    if not isinstance(adapters, dict) or set(adapters) - set(ADAPTER_NAMES) or not all(callable(v) for v in adapters.values()):
        raise ValueError("adapters must be callables named " + ", ".join(ADAPTER_NAMES))
    return adapters


def _ancestry(raw, plan_commit, reviewed, record_path):
    if (not isinstance(raw, dict) or set(raw) != {"is_ancestor", "changed_paths"} or type(raw["is_ancestor"]) is not bool
            or not isinstance(raw["changed_paths"], list) or len(raw["changed_paths"]) > 64
            or not all(isinstance(p, str) and p and not p.startswith("/") and ".." not in Path(p).parts and "\\" not in p for p in raw["changed_paths"])
            or len(set(raw["changed_paths"])) != len(raw["changed_paths"])):
        return ["ancestry adapter returned a malformed answer"]
    problems = []
    if not raw["is_ancestor"] or reviewed == plan_commit:
        problems.append("the reviewed code commit is not a strict ancestor of the plan commit")
    allowed = {pre.GATES_PATH, pre.MEMO_PATH, record_path}
    outside = sorted(set(raw["changed_paths"]) - allowed)
    if outside:
        touched = [p for p in outside if p.split("/")[0] in CODE_ROOTS]
        problems.append("paths changed after the reviewed commit beyond the gate, its twin and the record"
                        + (f" (code changed: {touched[:4]})" if touched else f": {outside[:4]}"))
    return problems


def evaluate_operational_authorization(plan, reference, *, requested_scope, now, adapters=None, max_reference_age_s=3600):
    """Classify a plan + reference + committed record. Returns a report whose verdict is always NO-GO."""
    f = _Findings()
    state, details = STATE_DENIED, {}
    try:
        adapters = _adapters(adapters)
        clock = S._instant(now)
        if type(max_reference_age_s) is not int or not 1 <= max_reference_age_s <= 86400:
            raise ValueError("freshness bound must be 1..86400 seconds")
        p, ref = C._check_plan(plan), C._document(reference)     # exact keys, fingerprint, inventory, stages (no extra stage can ride along)
        p["stages"] = {name: p["stages"][name] for name in STAGES}
        f.check("scope.request", _same(requested_scope, GRANTED_SCOPE),
                "the request is exactly full_generation for known, test and matched; every other compute stage "
                f"({', '.join(REFUSED_SCOPES)}) is refused")
        gates = classify_gates(ref.get("gates"), ref.get("memo"), ref.get("scientific_protocol"))
        details["gate_state"] = gates["state"]
        f.check("gates.state", gates["state"] != STATE_DENIED, "canonical gates are internally consistent, scientific approvals intact and "
                "every other compute stage closed" + ("" if not gates["problems"] else ": " + "; ".join(gates["problems"][:3])))
        has_record = p.get("authorization") is not None
        if gates["state"] == STATE_CLOSED:
            if has_record:
                f.fail("record.consistency", "a record in the plan is not a gate: the canonical gate is closed, so a plan that carries an authorization is contradictory")
            else:
                f.add("record", NOT_RUN, "no DR-04 operational record: the canonical gates are closed, which is the required state today")
        elif gates["state"] == STATE_CANDIDATE:
            if has_record:
                _evaluate_record(p, ref, f, adapters, clock, max_reference_age_s, details)
            else:
                f.fail("record.consistency", "the canonical gate claims an approval but the plan carries no authorization record")
        state = STATE_DENIED if f.failed else STATE_CLOSED if gates["state"] == STATE_CLOSED else STATE_VALID
    except (Exception, RecursionError) as error:           # hostile input must become a finding, never a crash or an allow
        f.fail("input", "input could not be evaluated: " + type(error).__name__)
        state = STATE_DENIED
    report = {"schema": SCHEMA_REPORT, "state": state, "findings": f.items, "details": details,
              "scientific_approvals_modified": False, "canonical_gates_modified": False,
              "launch_decision": "NOT_MADE_REQUIRES_SEPARATE_DECISION", "still_required_before_any_launch": list(STILL_REQUIRED),
              "note": "A valid record is a statement about documents. It does not authorize, schedule or start generation.", **NO_AUTHORITY}
    canonical(report)
    return report


def _evaluate_record(plan, ref, f, adapters, clock, max_age, details):
    auth = plan["authorization"]
    report = G.validate_plan(plan, ref)
    details["e13_plan_status"] = report["plan_status"]
    f.check("plan.e13", report["plan_status"] == G.DOCUMENT_OK and report["counts"][G.FAIL] == 0,
            "the E13 validator finds the plan complete and consistent with no failure and no blocked prerequisite (host, backup, lock, ceilings, record)")
    authorization_findings = [i for i in report["findings"] if i["id"].startswith("authorization.")]
    f.check("authorization.e13", bool(authorization_findings) and all(i["status"] == G.PASS for i in authorization_findings),
            "every E13 authorization check passes (basis, record, approver, provenance, binding, ceilings, scope, gate, supervisor view, isolation)")
    evaluated = S._instant(ref.get("evaluated_at"))
    age = (clock - evaluated).total_seconds()
    f.check("evidence.fresh", 0 <= age <= max_age, "the reference (checkout, lock and host measurements) was collected within the freshness bound "
            "and not in the future: a stale environment lock or stale host report is refused")
    f.check("authorization.unexpired", clock < S._instant(auth.get("expires_at")), "the authorization has not expired at the injected current time")
    record_path = auth.get("record")
    text = ref["record_texts"].get(record_path) if isinstance(ref.get("record_texts"), dict) else None
    f.check("record.bytes_match_hash", isinstance(text, str) and len(text) <= MAX_RECORD_CHARS
            and hashlib.sha256(text.encode("utf-8")).hexdigest() == auth.get("record_sha256"),
            "the text that is parsed is byte-for-byte the document whose hash the authorization cites (no time-of-check/time-of-use gap, no truncation)")
    blocks = _blocks_of(text, SCHEMA_BLOCK)
    block = blocks[0] if len(blocks) == 1 else None
    if not f.check("record.e16_block", block is not None and set(block) == set(BLOCK_KEYS),
                   "the committed record holds exactly one operational block with exactly the contract fields"):
        return
    ceilings = plan["ceilings"]
    exact = {"scope": _same(block["scope"], GRANTED_SCOPE), "approved_by": block["approved_by"] == auth["approved_by"],
             "expires_at": block["expires_at"] == auth["expires_at"], "digest": block["approved_plan_digest"] == auth["approved_plan_digest"] == G.approved_plan_digest(plan),
             "host": block["host_id"] == auth["host_id"] == plan["host"]["host_id"],
             "working": block["working_storage_id"] == auth["working_storage_id"] == plan["working"]["storage_id"],
             "backup": block["backup_storage_id"] == auth["backup_storage_id"] == plan["backup"]["storage_id"],
             "ceilings": (isinstance(block["ceilings"], dict) and set(block["ceilings"]) == set(BLOCK_CEILING_KEYS)
                          and all(_number_equal(block["ceilings"][k], ceilings.get(k)) for k in BLOCK_CEILING_KEYS)),
             "shapes": (isinstance(block["reviewed_code_commit"], str) and HEX40.fullmatch(block["reviewed_code_commit"]) is not None
                        and _text(block["revocation_id"]) and len(block["revocation_id"]) <= 120)}
    f.check("record.matches_plan", all(exact.values()), "the operational block restates exactly the plan's scope, approver, expiry, design digest, host, "
            "both storage ids and every ceiling" + ("" if all(exact.values()) else f" (differs: {sorted(k for k, v in exact.items() if not v)})"))
    gate = ref["gates"]["decisions"]["full_generation"]["approval"]
    f.check("record.agrees_with_gate", all(_same(gate.get(k), auth.get(k)) for k in ("approved_by", "approved_at", "decision", "record"))
            and auth["approved_by"] == ref["scientific_protocol"].get("approved_by"),
            "approver, instant, decision text and record path agree in the record block, the plan, the gate approval and the ratified protocol: "
            "contradictory records are refused")
    signature = block["signature"]
    shape = (isinstance(signature, dict) and set(signature) == {"scheme", "evidence_sha256"} and signature["scheme"] in SIGNATURE_SCHEMES
             and isinstance(signature["evidence_sha256"], str) and HEX64.fullmatch(signature["evidence_sha256"]) is not None)
    verified = False
    if shape and "signature_verifier" in adapters:
        try:
            verified = adapters["signature_verifier"](auth["record_sha256"], auth["approved_by"], copy.deepcopy(signature)) is True
        except Exception:
            verified = False
    f.check("signer.verified", verified, "an injected signature verifier confirmed that the named approver signed this exact record (a name in a "
            "document is not a signature; with no verifier the record is refused)")
    reviewed = block["reviewed_code_commit"]
    problems = ["no ancestry adapter"]
    if "ancestry_checker" in adapters and exact["shapes"]:
        try:
            problems = _ancestry(adapters["ancestry_checker"](reviewed, plan["source"]["git_commit"]), plan["source"]["git_commit"], reviewed, record_path)
        except Exception:
            problems = ["ancestry adapter failed"]
    f.check("code.unchanged_since_review", not problems, "the reviewed code commit is a strict ancestor of the plan commit and only the gate JSON, its "
            "memorandum twin and the record changed since: later code, config, test or workflow edits void the authorization"
            + ("" if not problems else " (" + "; ".join(problems) + ")"))
    revoked = True
    if "revocation_checker" in adapters and exact["shapes"]:
        try:
            answer = adapters["revocation_checker"](block["revocation_id"])
            checked = S._instant(answer["checked_at"])
            revoked = not (isinstance(answer, dict) and set(answer) == {"revoked", "checked_at"} and answer["revoked"] is False
                           and 0 <= (clock - checked).total_seconds() <= max_age)
        except Exception:
            revoked = True
    f.check("authorization.not_revoked", not revoked, "a fresh revocation query answered that the authorization is not revoked (no answer is a refusal)")
    details["reviewed_code_commit"] = reviewed if exact["shapes"] else None


# ---- release ordering ---------------------------------------------------------------------------------------------

def check_release_order(events):
    """Validate the order and cross-binding of the release steps without dropping a hash or bypassing a guard.

    reviewed code -> design digest -> researcher authorization -> authorization commit -> final lock -> revalidation ->
    (separate) launch decision. The design digest excludes exactly what the later steps create (the authorization commit,
    the gate JSON, the lock), so it can be written first; every later step restates and is checked against it.
    """
    problems, seen = [], {}
    if not isinstance(events, list) or len(events) > 32:
        return _order_report(["events must be a bounded list"], {})
    last_index, last_time = -1, None
    for position, event in enumerate(events):
        try:
            if not isinstance(event, dict) or event.get("step") not in RELEASE_STEPS:
                raise ValueError("unknown release step")
            index = RELEASE_STEPS.index(event["step"])
            moment = S._instant(event.get("at"))
            if index <= last_index:
                raise ValueError(f"step {event['step']} is out of order or repeated")
            if last_time is not None and moment < last_time:
                raise ValueError(f"step {event['step']} is dated before its predecessor")
            last_index, last_time = index, moment
            seen[event["step"]] = event
        except (ValueError, S.StorageRefused) as error:
            problems.append(f"event {position}: {error}")
            break
    if not problems:
        sequence = [name for name in RELEASE_STEPS if name in seen]
        if sequence != list(RELEASE_STEPS[:len(sequence)]):
            problems.append("a step was skipped: " + ", ".join(name for name in RELEASE_STEPS[:RELEASE_STEPS.index(sequence[-1])] if name not in seen))
    commit = lambda step, key="commit": seen.get(step, {}).get(key)             # noqa: E731
    digest = lambda step: seen.get(step, {}).get("digest")                        # noqa: E731
    if not problems:
        for step, key, pattern in (("final_reviewed_code", "commit", HEX40), ("authorization_commit", "commit", HEX40), ("authorization_commit", "parent", HEX40),
                                    ("final_lock", "commit", HEX40), ("final_lock", "lock_fingerprint", HEX64)):
            if step in seen and not (isinstance(seen[step].get(key), str) and pattern.fullmatch(seen[step][key])):
                problems.append(f"{step}.{key} is missing or malformed")
        for step in ("design_digest", "researcher_authorization", "revalidation"):
            if step in seen and not (isinstance(digest(step), str) and HEX64.fullmatch(digest(step))):
                problems.append(f"{step}.digest is missing or malformed")
    if not problems:
        digests = {digest(s) for s in ("design_digest", "researcher_authorization", "revalidation") if s in seen}
        if len(digests) > 1:
            problems.append("the design digest differs between the design, the researcher's authorization and the revalidation")
        if "authorization_commit" in seen and commit("authorization_commit", "parent") != commit("final_reviewed_code"):
            problems.append("the authorization commit is not a direct child of the reviewed code commit")
        if "final_lock" in seen and commit("final_lock") != commit("authorization_commit"):
            problems.append("the final lock was not created on the authorization commit (the gate JSON is hashed into the lock)")
        if "revalidation" in seen and seen["revalidation"].get("lock_fingerprint") != seen.get("final_lock", {}).get("lock_fingerprint"):
            problems.append("the revalidation did not use the final lock")
        if "launch_decision" in seen:
            problems.append("a launch decision cannot be recorded by this build: production execution is unavailable")
    return _order_report(problems, seen)


def _order_report(problems, seen):
    done = [name for name in RELEASE_STEPS if name in seen]
    return {"schema": SCHEMA_ORDER, "ok": not problems, "problems": problems, "steps_present": done,
            "next_step": next((n for n in RELEASE_STEPS if n not in seen), None), "launch_decision_recorded": "launch_decision" in seen,
            "omits_no_hash": True, "bypasses_no_guard": True, **NO_AUTHORITY}


# ---- CI-facing gate check ---------------------------------------------------------------------------------------

def ci_gate_check(gates, memo, protocol):
    """What a CI step may ask: are the gates exactly the canonical closed state? Only that answer is accepted today.

    A future readiness workflow would call ``evaluate_operational_authorization`` with real adapters for the approved
    shape; this build accepts no approved-shaped gate on its own, so a gate edit without a full record cannot pass.
    """
    report = classify_gates(gates, memo, protocol)
    report["accepted_by_this_build"] = report["state"] == STATE_CLOSED
    return report


def _read_strict(path):
    """Bounded, strict (no duplicate keys, no NaN) JSON read of one regular file."""
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_DOCUMENT_BYTES:
        raise ValueError("not a bounded regular file")
    return S._strict(path.read_bytes())


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0], allow_abbrev=False)
    commands = parser.add_subparsers(dest="action", required=True)
    gate = commands.add_parser("ci-gate", allow_abbrev=False, help="exit 0 only if every compute gate is exactly canonical-closed")
    gate.add_argument("--repo", default=str(G.ROOT))
    args = parser.parse_args(argv)
    try:
        repo = Path(args.repo)
        report = ci_gate_check(*(_read_strict(repo / name) for name in (pre.GATES_PATH, pre.MEMO_PATH, G.PROTOCOL_JSON)))
        print(canonical(report))
        return 0 if report["accepted_by_this_build"] else 3 if report["state"] == STATE_CANDIDATE else 2
    except Exception as error:
        print(canonical({"verdict": "NO-GO", "execution_permitted": False, "authorizes_nothing": True, "error": "invalid input: " + type(error).__name__}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

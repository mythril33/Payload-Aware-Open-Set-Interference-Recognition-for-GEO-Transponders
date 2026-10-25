#!/usr/bin/env python3
"""E16 data-only release-boundary integration. It connects the E13 plan, the E14 sealed specification, the E16
durability/ledger/policy contracts and injected evidence into one report. It cannot execute anything.

The report is built from documents and from *evidence documents returned by injected read-only adapters* (shard state,
backup state, journal state, K17d comparison, resource observation, consumer declaration and the policy adapters).
Nothing here opens a generator, spawns a process, reads the host or reads an observation. Evidence is as truthful as the
adapter that produced it; the integration's job is to refuse inconsistent, stale, out-of-order or self-contradicting
evidence and to bind independent records (working tree, backup copy, external journal) to each other, so that a forgery
has to be consistent everywhere at once.

Every report ends in NO-GO. ``document_conditions_met`` is a statement about documents; ``execution.boundary`` is a
permanent BLOCKED condition because no executor exists and production launch is disabled.
"""
from __future__ import annotations

import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import b2_e13_generation_plan as G
import b2_e14_launch_contract as C
import b2_e14_storage as S
import b2_e16_durability as D
import b2_e16_ledger as L
import b2_e16_policy as P

SCHEMA_REPORT = "B2-E16-integration-report/1"
SCHEMA_STAGE = "B2-E16-stage-evidence/1"
SCHEMA_BACKUP = "B2-E16-backup-evidence/1"
SCHEMA_JOURNAL = "B2-E16-journal-evidence/1"
PASS, FAIL, BLOCKED, NOT_RUN = "PASS", "FAIL", "BLOCKED", "NOT_RUN"
STAGES = ("known", "test", "matched")
BOUNDARIES = {"pre_launch": (), "after_known": ("known",), "after_test": ("known", "test"), "after_matched": ("known", "test", "matched")}
NEXT_STAGE = {"pre_launch": "known", "after_known": "test", "after_test": "matched", "after_matched": None}
STAGE_ROLES = {"known": ("train", "val-select", "val-calib", "test"), "test": ("test",), "matched": ("test-matched",)}
EVIDENCE_ADAPTERS = ("shard_state", "backup_state", "journal_state", "k17d_metadata", "resource_state", "consumer_declaration")
ADAPTER_NAMES = EVIDENCE_ADAPTERS + P.ADAPTER_NAMES
STAGE_EVIDENCE_KEYS = {"schema", "stage", "collected_at", "root", "request_fingerprint", "roles", "unexpected_root_entries"}
ROLE_EVIDENCE_KEYS = {"exists", "directory", "classification", "admissions", "manifest", "immutability"}
BACKUP_EVIDENCE_KEYS = {"schema", "stage", "collected_at", "devices", "restores", "copies"}
JOURNAL_EVIDENCE_KEYS = {"schema", "collected_at", "entries", "anchor", "location"}
JOURNAL_ORDER = ("known:stage_completed", "known:backup_verified", "k17d_check", "test:stage_bound", "test:stage_completed",
                 "test:backup_verified", "matched:stage_bound", "matched:stage_completed", "matched:backup_verified")
ALLOWED_CONSUMERS = {"train": [["known", "train"]], "val_select": [["known", "val-select"]], "val_calib": [["known", "val-calib"]]}
HELD_OUT = (("known", "test"), ("test", "test"), ("matched", "test-matched"))
K17D_COUNTS = {"co_feed_missing": 35, "cross_feed_missing": 43, "headline": 500, "missing_total": 78, "sensitivity": 465}
K17D_SCHEMA = "B2-E14-K17d-production-metadata-verification/1"
BARRIER = "fsync_files_then_directory_chain_then_reverify"
PERMANENT = "execution.boundary"
NO_AUTHORITY = {"verdict": "NO-GO", "execution_permitted": False, "authorizes_nothing": True, "production_launch_enabled": False,
                "benchmark_complete": False, "executor_implemented": False}


class ExecutionUnavailable(RuntimeError):
    pass


def deny_execution(*args, **kwargs):
    """Unconditional refusal. No release state, authorization, evidence or flag reaches an executor from here."""
    raise ExecutionUnavailable("E16 has no production execution path; DR-04 NO-GO")


# ---- small helpers ---------------------------------------------------------------------------------------------

def _same(left, right):
    return C.canonical(left) == C.canonical(right)


def _fresh(doc, now, max_age, label):
    age = (S._instant(now) - S._instant(doc["collected_at"])).total_seconds()
    if not 0 <= age <= max_age:
        raise D.DurabilityRefused(f"{label} evidence is stale or from the future")


def _identity(value):
    return (isinstance(value, dict) and type(value.get("st_dev")) is int and type(value.get("st_ino")) is int
            and value["st_dev"] >= 0 and value["st_ino"] > 0)


def _inode(value):
    return {"st_dev": value["st_dev"], "st_ino": value["st_ino"]}


def _condition(identifier, status, message, *, applicable=True, details=None):
    return {"id": identifier, "status": status, "applicable": applicable, "message": message, "details": details or {}}


def _from_problems(identifier, problems, ok_message):
    if problems:
        return _condition(identifier, FAIL, "; ".join(problems[:4]), details={"problem_count": len(problems)})
    return _condition(identifier, PASS, ok_message)


def _e13_status(report, prefixes):
    items = [i for i in report["findings"] if i["id"].split(".")[0] in prefixes]
    if not items or any(i["status"] == G.FAIL for i in items):
        return FAIL, [i["id"] for i in items if i["status"] == G.FAIL]
    if any(i["status"] == G.BLOCKED for i in items):
        return BLOCKED, [i["id"] for i in items if i["status"] == G.BLOCKED]
    return PASS, []


def _call(adapters, name, *args):
    """(document, status, message): status None on success, NOT_RUN when absent, FAIL when it raised or returned non-JSON."""
    if name not in adapters:
        return None, NOT_RUN, f"adapter {name} was not supplied; the evidence does not exist"
    try:
        return C._document(adapters[name](*args)), None, None
    except (Exception, RecursionError) as error:
        return None, FAIL, f"adapter {name} failed or returned non-JSON: {type(error).__name__}"


def expected_states(boundary):
    done = BOUNDARIES[boundary]
    return {stage: "COMPLETE" if stage in done else "NOT_STARTED" for stage in STAGES}


def _layout(spec_stage):
    roles = {}
    for shard in spec_stage["shards"]:
        roles.setdefault(shard["role"], {})[shard["ordinal"]] = shard
    return roles


def _expected_for(shard, fingerprint):
    return {"role": shard["role"], "scenario_seeds": list(shard["groups"]), "n_samples": shard["observations"], "request_fingerprint": fingerprint}


# ---- stage (working tree) evidence -----------------------------------------------------------------------------

def _stage_problems(stage, evidence, spec_stage, plan, state, fingerprint, now, max_age):
    problems = []
    try:
        if not isinstance(evidence, dict) or evidence.get("schema") != SCHEMA_STAGE or evidence.get("stage") != stage or set(evidence) != STAGE_EVIDENCE_KEYS:
            return ["stage evidence has the wrong schema, stage or fields"]
        _fresh(evidence, now, max_age, stage)
        root = evidence["root"]
        if (not isinstance(root, dict) or root.get("path") != str(Path(plan["working"]["root"]) / stage)
                or (state == "COMPLETE" and not _identity(root)) or ("st_dev" in root and not _identity(root))):
            problems.append("stage root is not the planned working root / stage name, or has no directory identity (path substitution)")
        if evidence["unexpected_root_entries"] != []:
            problems.append("unexpected entries beside the stage's role directories")
        layout = _layout(spec_stage)
        if (not isinstance(evidence["roles"], dict) or set(evidence["roles"]) != set(STAGE_ROLES[stage])
                or set(layout) != set(STAGE_ROLES[stage])):
            return problems + ["role directories differ from the planned roles of this stage"]
        for role, entry in evidence["roles"].items():
            if not isinstance(entry, dict) or set(entry) != ROLE_EVIDENCE_KEYS or type(entry["exists"]) is not bool:
                problems.append(f"{role}: role evidence has the wrong fields")
            elif state == "NOT_STARTED":
                started = entry["exists"] and (not isinstance(entry["classification"], dict)
                                               or entry["classification"].get("resume_state") != "NOT_STARTED")
                if started or entry["admissions"] not in (None, []) or entry["manifest"] is not None:
                    problems.append(f"{role}: data exists although this stage must not have started at this boundary (stage order)")
        if problems or state == "NOT_STARTED":
            return problems
        if not (isinstance(fingerprint, str) and S.HEX.fullmatch(fingerprint)) or evidence["request_fingerprint"] != fingerprint:
            return ["no consistent request fingerprint is bound for this stage"]
        root = Path(plan["working"]["root"]) / stage
        for role, shards in layout.items():
            problems += [f"{role}: {item}" for item in _role_problems(role, shards, evidence["roles"][role], fingerprint, root / role)]
    except (D.DurabilityRefused, S.StorageRefused, KeyError, TypeError, ValueError, AttributeError) as error:
        problems.append("stage evidence is malformed: " + type(error).__name__)
    return problems


def _role_problems(role, shards, entry, fingerprint, expected_path):
    problems = []
    if entry["exists"] is not True or not _identity(entry["directory"]):
        return ["role directory is missing or has no identity"]
    if entry["directory"].get("path") != str(expected_path):
        problems.append("role directory is not the planned <working root>/<stage>/<role> (path substitution)")
    ordinals = sorted(shards)
    directory = _inode(entry["directory"])
    classification = entry["classification"]
    if (not isinstance(classification, dict) or classification.get("schema") != D.SCHEMA_CLASSIFICATION or classification.get("deep") is not True
            or classification.get("resume_state") != "COMPLETE" or classification.get("planned") != len(ordinals)
            or classification.get("unexpected_entries") != [] or classification.get("quarantine_required") != []
            or classification.get("cleanup_may_delete_evidence") is not False
            or not _same(classification.get("directory_identity"), directory)):
        problems.append("classification is not a deep, complete, orphan-free report for this directory")
    else:
        states = classification.get("shards")
        if (not isinstance(states, dict) or set(states) != {str(o) for o in ordinals}
                or any(not isinstance(states[str(o)], dict) or states[str(o)].get("state") != "COMMITTED" for o in ordinals)
                or classification.get("counts", {}).get("COMMITTED") != len(ordinals)):
            problems.append("not every planned shard is COMMITTED, or the counts disagree with the per-shard states")
    admissions = entry["admissions"]
    if not isinstance(admissions, list) or len(admissions) != len(ordinals) or not all(isinstance(a, dict) and type(a.get("ordinal")) is int for a in admissions):
        return problems + ["every planned shard needs exactly one durable-admission record"]
    admitted = set()
    for ordinal, record in zip(ordinals, sorted(admissions, key=lambda a: a["ordinal"])):
        want, names = _expected_for(shards[ordinal], fingerprint), D.shard_names(ordinal)
        if (record.get("schema") != D.SCHEMA_ADMISSION or record["ordinal"] != ordinal or record.get("role") != want["role"]
                or not _same(record.get("scenario_seeds"), want["scenario_seeds"]) or record.get("n_samples") != want["n_samples"]
                or record.get("request_fingerprint") != fingerprint or record.get("barrier") != BARRIER or record.get("media_verified") is not False
                or record.get("authorizes_nothing") is not True or record.get("execution_permitted") is not False
                or not _same(record.get("directory_identity"), directory) or not isinstance(record.get("files"), dict)
                or set(record["files"]) != set(names)):
            problems.append(f"admission record for shard {ordinal} does not match the sealed plan or the directory")
            continue
        for name in names:
            info = record["files"][name]
            if not (isinstance(info, dict) and set(info) == {"bytes", "sha256"} and type(info["bytes"]) is int and info["bytes"] > 0
                    and isinstance(info["sha256"], str) and S.HEX.fullmatch(info["sha256"])):
                problems.append(f"admission record for shard {ordinal} has malformed file entries")
            else:
                admitted.add((name, info["bytes"], info["sha256"]))
    manifest = entry["manifest"]
    try:
        D._manifest_check(manifest)
        listed = {(e["name"], e["bytes"], e["sha256"]) for e in manifest["entries"]}
        if manifest["role"] != role or manifest["shards"] != ordinals or listed != admitted:
            problems.append("manifest does not describe exactly the admitted bytes of this role")
    except (D.DurabilityRefused, KeyError, TypeError):
        problems.append("manifest is missing or invalid")
    immutability = entry["immutability"]
    if not (isinstance(immutability, dict) and immutability.get("ok") is True and immutability.get("worm_proven") is False
            and immutability.get("findings") == []):
        problems.append("published files are not read-only and unaliased (or the report claims proven WORM)")
    return problems


def _isolation_problems(stage_docs):
    problems, seen = [], {}
    for stage, doc in stage_docs.items():
        if not isinstance(doc, dict) or not isinstance(doc.get("roles"), dict):
            continue
        found = [((stage, "<root>"), doc.get("root"))]
        found += [((stage, role), entry.get("directory")) for role, entry in doc["roles"].items() if isinstance(entry, dict)]
        for key, identity in found:
            if not _identity(identity):
                continue
            inode = (identity["st_dev"], identity["st_ino"])
            if inode in seen:
                problems.append(f"{key} and {seen[inode]} are the same directory (role aliasing, bind mount or symlink)")
            seen[inode] = key
    return problems


def check_consumer_isolation(declaration):
    """Which (stage, role) directories each training-time consumer reads. Held-out roles may never appear."""
    if not isinstance(declaration, dict) or set(declaration) != set(ALLOWED_CONSUMERS):
        return ["consumer declaration must name exactly train, val_select and val_calib"]
    problems = []
    for consumer, allowed in ALLOWED_CONSUMERS.items():
        value = declaration[consumer]
        if not isinstance(value, list) or not all(isinstance(v, list) and len(v) == 2 and all(isinstance(x, str) for x in v) for v in value):
            problems.append(f"{consumer}: malformed input list")
        elif any(tuple(v) in HELD_OUT for v in value):
            problems.append(f"{consumer} reads a held-out role (test or matched data may never reach training, selection or calibration)")
        elif value != allowed:
            problems.append(f"{consumer} reads {value} instead of exactly {allowed}")
    return problems


# ---- backup evidence -------------------------------------------------------------------------------------------

def _backup_problems(stage, evidence, stage_doc, plan, now, max_age):
    problems = []
    try:
        if (not isinstance(evidence, dict) or evidence.get("schema") != SCHEMA_BACKUP or evidence.get("stage") != stage
                or set(evidence) != BACKUP_EVIDENCE_KEYS):
            return ["backup evidence has the wrong schema or fields"]
        _fresh(evidence, now, max_age, "backup")
        devices = evidence["devices"]
        if not isinstance(devices, dict) or set(devices) != {"working", "backup", "observed_working", "observed_backup"}:
            return ["device records differ from the contract"]
        ceilings = plan["ceilings"]
        verdict = S.validate_backup_devices(
            devices["working"], devices["backup"], observed_working=devices["observed_working"], observed_backup=devices["observed_backup"], now=now,
            max_age_seconds=max_age, working_floor_bytes=int(math.ceil(G.required_free_gib(21350, ceilings["min_free_disk_gib"]) * 2 ** 30)),
            backup_floor_bytes=int(math.ceil(ceilings["backup_disk_gb"] * 10 ** 9)))
        if not verdict["ok"]:
            problems.append("device validation failed: " + "; ".join(verdict["failures"][:2]))
        disks = {d.get("path"): d for d in plan["host"]["inventory"]["inventory"]["disks"] if isinstance(d, dict)}
        for label, side in (("working", plan["working"]), ("backup", plan["backup"])):
            record, disk = devices[label], disks.get(side["root"], {})
            if record.get("root") != side["root"] or record.get("physical_storage_id") != side["storage_id"] or record.get("host_id") != plan["host"]["host_id"]:
                problems.append(f"{label} device is not the planned root, storage id and host")
            if record.get("filesystem_device") != disk.get("device") or record.get("filesystem_type") != disk.get("fstype"):
                problems.append(f"{label} device record differs from the measured host inventory the plan was approved with")
        roles = set(stage_doc["roles"])
        if set(evidence["restores"]) != roles or set(evidence["copies"]) != roles:
            return problems + ["restore evidence does not cover exactly this stage's roles"]
        for role, entry in stage_doc["roles"].items():
            restore, where, manifest = evidence["restores"][role], evidence["copies"][role], entry["manifest"]
            if (not isinstance(restore, dict) or restore.get("schema") != D.SCHEMA_RESTORE or restore.get("ok") is not True
                    or restore.get("restore_reverified") is not True or restore.get("manifest_sha256") != manifest["manifest_sha256"]
                    or restore.get("files") != len(manifest["entries"]) or restore.get("bytes") != manifest["total_bytes"]):
                problems.append(f"{role}: no restore re-verification against this manifest")
            elif restore.get("disaster_recovery_qualified") is not False:
                problems.append(f"{role}: a byte-consistent copy claimed disaster-recovery qualification, which a one-off check cannot establish")
            if not (_identity(where) and where.get("path") == str(Path(plan["backup"]["root"]) / stage / role)
                    and where["st_dev"] == devices["backup"]["filesystem_device"]
                    and entry["directory"]["st_dev"] == devices["working"]["filesystem_device"] and where["st_dev"] != entry["directory"]["st_dev"]):
                problems.append(f"{role}: the verified copy is not on the planned backup device, distinct from the working directory")
    except (D.DurabilityRefused, S.StorageRefused, KeyError, TypeError, ValueError, AttributeError) as error:
        problems.append("backup evidence is malformed: " + type(error).__name__)
    return problems


# ---- external journal ------------------------------------------------------------------------------------------

def _journal_problems(evidence, done, plan, specification, stage_docs, k17d, fingerprints, now, max_age, record_sha256):
    try:
        if not isinstance(evidence, dict) or evidence.get("schema") != SCHEMA_JOURNAL or set(evidence) != JOURNAL_EVIDENCE_KEYS:
            return ["journal evidence has the wrong schema or fields"]
        _fresh(evidence, now, max_age, "journal")
        entries = evidence["entries"]
        if not isinstance(entries, list) or len(entries) > L.MAX_ENTRIES:
            return ["journal entries are missing or unbounded"]
        # Rebuild the exact bytes from the entries: nothing but the entries is trusted, including the reported head.
        verified = L.verify_chain(b"".join(L.canonical(e).encode() + b"\n" for e in entries), expected_head=evidence["anchor"])
        if not verified["ok"]:
            return ["external journal fails verification: " + "; ".join(verified["failures"][:2])]
        problems = []
        if evidence["anchor"] is None:
            problems.append("no independently retained anchor: truncation of the journal cannot be detected")
        location = evidence["location"]
        if not (isinstance(location, dict) and location.get("ok") is True and location.get("physical_independence_proven") is False):
            problems.append("journal location is not verified as separate from the working tree")
        kinds = {}
        for index, entry in enumerate(entries):
            kinds.setdefault((entry["stage"], entry["kind"]), []).append((index, entry))
        opened = kinds.get((None, "run_opened"), [])
        if len(opened) != 1 or opened[0][0] != 0:
            return problems + ["the journal must begin with exactly one run_opened entry"]
        identity = {"plan_fingerprint": plan["plan_fingerprint"], "specification_sha256": specification["specification_sha256"]}
        if not _same({k: opened[0][1]["data"].get(k) for k in identity}, identity):
            problems.append("run_opened is bound to a different plan or specification")
        snapshot = kinds.get((None, "authorization_snapshot"), [])
        if len(snapshot) != 1 or snapshot[0][1]["data"].get("record_sha256") != record_sha256:
            problems.append("authorization_snapshot is missing or names a different record")
        for index, entry in enumerate(entries):
            if entry["kind"] == "incident" and entry["data"].get("action") == "resume_only_under_identical_request":
                if not any(later["kind"] == "resume" and _same({k: later["data"].get(k) for k in identity}, identity) for later in entries[index + 1:]):
                    problems.append("an interruption has no later resume under the identical plan and specification")
            elif entry["kind"] == "incident":
                problems.append(f"incident {entry['data'].get('incident')} halted the run; it cannot continue within this authorization")
            elif entry["kind"] == "stop":
                problems.append("a stop entry ends the run")
        positions = {}
        for stage in STAGES:
            for kind in ("stage_bound", "stage_completed", "backup_verified"):
                found = kinds.get((stage, kind), [])
                required = stage in done and not (kind == "stage_bound" and stage == "known")
                if required and len(found) != 1:
                    problems.append(f"{stage}: exactly one {kind} entry is required at this boundary")
                elif not required and found:
                    problems.append(f"{stage}: {kind} is recorded although it is not expected at this boundary")
                elif found:
                    positions[f"{stage}:{kind}"] = found[0]
        for stage in done:
            bound = positions.get(f"{stage}:stage_bound")
            if bound is not None and bound[1]["data"].get("request_fingerprint") != fingerprints.get(stage):
                problems.append(f"{stage}: the journaled request binding differs from the one the shards carry")
            manifests = {role: entry["manifest"]["manifest_sha256"] for role, entry in stage_docs[stage]["roles"].items()}
            for kind in ("stage_completed", "backup_verified"):
                record = positions.get(f"{stage}:{kind}")
                if record is not None and not _same(record[1]["data"].get("manifests"), manifests):
                    problems.append(f"{stage}: the journal's {kind} manifests differ from the working-tree evidence")
        check = kinds.get((None, "k17d_check"), [])
        if done:
            if len(check) != 1 or k17d is None or check[0][1]["data"].get("identity_sha256") != k17d.get("identity_sha256"):
                problems.append("the journal lacks exactly one k17d_check entry that matches the metadata comparison")
            else:
                positions["k17d_check"] = check[0]
        elif check:
            problems.append("k17d_check is recorded before the known stage is complete")
        previous = -1
        for label in JOURNAL_ORDER:
            if label in positions:
                if positions[label][0] <= previous:
                    problems.append(f"journal order violates the stage sequence at {label}")
                previous = positions[label][0]
        return problems
    except (KeyError, TypeError, ValueError, AttributeError, L.LedgerRefused, S.StorageRefused, D.DurabilityRefused) as error:
        return ["journal evidence is malformed: " + type(error).__name__]


# ---- K17d metadata comparison ----------------------------------------------------------------------------------

def _k17d_problems(doc, plan, now, max_age):
    problems = []
    try:
        if not isinstance(doc, dict) or doc.get("schema") != K17D_SCHEMA:
            return ["not an E14 production metadata verification report"]
        d8, d1 = plan["scientific"]["d8_k17d"], plan["scientific"]["d1_exposure"]
        if doc.get("metadata_status") == "SYNTHETIC_FIXTURE_ONLY" or doc.get("production_cross_verification_performed") is not True:
            problems.append("a synthetic or fabricated comparison cannot satisfy the production K17d cross-check")
        elif doc.get("metadata_status") != "ACCEPTED_IDENTITY_METADATA_MATCH":
            problems.append("metadata do not match the accepted K17d identity")
        if not _same(doc.get("counts"), K17D_COUNTS) or doc.get("identity_sha256") != d8["identity_sha256"]:
            problems.append("K17d counts or accepted identity differ (D-8)")
        if doc.get("request_fingerprint") != plan["source"]["known_request_fingerprint"] or doc.get("source_head") != plan["source"]["git_commit"]:
            problems.append("the comparison used a different request or source commit than the sealed plan")
        zero = lambda value: type(value) is int and value == 0               # noqa: E731  (False and 0.0 are not zero reads)
        if not zero(doc.get("observation_reads")) or not zero(doc.get("waveform_synthesis_calls")) or doc.get("execution_authorized") is not False or doc.get("verdict") != "NO-GO":
            problems.append("the comparison read observations, synthesized waveforms or claims authority")
        obligations = doc.get("d1_obligations")
        if not (isinstance(obligations, dict) and obligations.get("existing_test_pristine") is False
                and _same(obligations.get("exposure_excluded_groups"), d1["mandatory_exclusion_rows"])
                and obligations.get("exposed_test_ids") == d1["exposed_test_ids"] and obligations.get("exposed_matched_ids") == d1["exposed_matched_ids"]):
            problems.append("the D-1 exposed-group disclosure is missing or altered")
        if "collected_at" in doc:                            # the E14 report carries no clock; a wrapping adapter must add one
            _fresh(doc, now, max_age, "K17d")
        else:
            problems.append("the comparison has no collection time, so staleness cannot be judged")
    except (KeyError, TypeError, S.StorageRefused, D.DurabilityRefused) as error:
        problems.append("K17d comparison is malformed: " + type(error).__name__)
    return problems


# ---- the integration -------------------------------------------------------------------------------------------

def evaluate_release_boundary(plan, reference, specification, *, boundary, requested_scope, now, adapters=None, max_evidence_age_s=3600):
    """One report per boundary. Always NO-GO; no condition can make it anything else."""
    conditions = []
    try:
        if boundary not in BOUNDARIES:
            raise ValueError("unknown boundary")
        adapters = {} if adapters is None else adapters
        if not isinstance(adapters, dict) or set(adapters) - set(ADAPTER_NAMES) or not all(callable(v) for v in adapters.values()):
            raise ValueError("adapters must be callables named " + ", ".join(ADAPTER_NAMES))
        if type(max_evidence_age_s) is not int or not 1 <= max_evidence_age_s <= 86400:
            raise ValueError("evidence freshness bound must be 1..86400 seconds")
        S._instant(now)
        p = C._check_plan(plan)
        submitted = C._document(specification)
        static, policy_state = _static_conditions(plan, reference, specification, p, submitted, requested_scope, now, adapters, max_evidence_age_s)
        conditions += static
        conditions += _evidence_conditions(p, submitted, boundary, now, adapters, max_evidence_age_s, policy_state)
    except (Exception, RecursionError) as error:            # hostile or malformed input becomes a failed condition, never an allow
        conditions.append(_condition("input", FAIL, "input could not be evaluated: " + type(error).__name__))
    conditions.append(_execution_boundary())
    conditions = [_serializable(c) for c in conditions]
    document = [c for c in conditions if c["id"] != PERMANENT and c["applicable"]]
    report = {"schema": SCHEMA_REPORT, "boundary": boundary if boundary in BOUNDARIES else None, "conditions": conditions,
              "counts": {status: sum(1 for c in conditions if c["status"] == status) for status in (PASS, FAIL, BLOCKED, NOT_RUN)},
              "document_conditions_met": bool(document) and all(c["status"] == PASS for c in document), "execution_conditions_met": False,
              "next_stage": NEXT_STAGE.get(boundary), "scientific_approvals_modified": False, "canonical_gates_modified": False,
              "mandatory_reporting": {"d1_existing_test_pristine": False, "d1_exclusion_rows": {"test": 498, "test-matched": 148},
                                      "d8_k17d_counts": dict(K17D_COUNTS)},
              "note": "Structural validity is not execution authority. Evidence is as truthful as the adapter that supplied it.", **NO_AUTHORITY}
    try:
        C.canonical(report)
    except (ValueError, TypeError, OverflowError, RecursionError):
        report = dict(report, conditions=[_condition("report", FAIL, "the report could not be serialized as strict JSON")],
                      counts={PASS: 0, FAIL: 1, BLOCKED: 0, NOT_RUN: 0}, document_conditions_met=False)
    return report


def _serializable(condition):
    try:
        C.canonical(condition)
        return condition
    except (ValueError, TypeError, OverflowError, RecursionError):
        return _condition(condition.get("id", "unknown") if isinstance(condition, dict) else "unknown", FAIL, "condition details were not strict JSON")


def _execution_boundary():
    reasons = []
    if G.sup.PRODUCTION_LAUNCH_ENABLED is not False:
        reasons.append("PRODUCTION_LAUNCH_ENABLED is not False")
    if G.sup.FIXTURE_MAX_GROUPS != 2:
        reasons.append("fixture cap is not two groups")
    for label, call in (("E9 guard", lambda: G.e9.guard_execution("generation")), ("E14 refusal", C.deny_execution), ("E16 refusal", deny_execution)):
        try:
            call()
            reasons.append(f"{label} returned instead of refusing")
        except (G.e9.ExecutionNotAuthorized, C.ExecutionUnavailable, ExecutionUnavailable):
            pass
        except Exception as error:
            reasons.append(f"{label} behaved unexpectedly: {type(error).__name__}")
    probe = Path("/nonexistent-e16-boundary-probe")
    try:
        G.sup.stage_argv("known", G.sup.build_plan(probe, mode="production", groups_per_shard=4), probe)
        reasons.append("the supervisor built an unbounded production command")
    except G.sup.SupervisorError:
        pass
    except Exception as error:
        reasons.append("supervisor refusal changed: " + type(error).__name__)
    if reasons:
        return _condition(PERMANENT, FAIL, "the execution boundary changed: " + "; ".join(reasons))
    return _condition(PERMANENT, BLOCKED, "no executor exists, PRODUCTION_LAUNCH_ENABLED is False, the E9 and E14 refusals hold and the supervisor builds no "
                      "unbounded command: a document can never satisfy this condition", details={"permanent": True})


def _static_conditions(plan, reference, specification, p, submitted, requested_scope, now, adapters, max_age):
    out = [_condition("inventory.frozen", PASS, "21,350 observations in 739 four-group shards over 2,450 groups, derived from the frozen protocol and equal to the plan")]
    expected = C.build_specification(p)
    out.append(_from_problems("spec.sealed", [] if _same(submitted, expected) else ["the submitted specification differs from the one sealed from the plan"],
                              "the specification equals the one rebuilt from the plan, including its hash and runtime policy"))
    stages = expected["stages"]
    chain = ([s["name"] for s in stages] == list(STAGES) and [s["requires_completed_stage"] for s in stages] == [None, "known", "test"]
             and [s["known_artifact_binding_required"] for s in stages] == [False, True, True])
    out.append(_from_problems("sequence.stages", [] if chain else ["stages are not a known -> test -> matched dependency chain"],
                              "known -> test -> matched, with deferred request bindings for test and matched"))
    admitted = C.admit(specification, plan, reference)
    report = admitted["e13_report"]
    if report is None:
        for identifier in ("plan.dr04", "identity.source_config_environment", "reporting.d1_d8"):
            out.append(_condition(identifier, FAIL, "the E13 validator could not evaluate the plan: " + "; ".join(admitted["failures"][:2])))
    else:
        status, ids = _e13_status(report, ("plan", "host", "backup", "ceilings", "timing", "stop_rules", "obligations", "release", "authorization"))
        if status == PASS and not admitted["document_consistent"]:
            status, ids = FAIL, admitted["failures"][:3]
        out.append(_condition("plan.dr04", status, f"E13 plan status {report['plan_status']}" + (f"; not passing: {ids[:5]}" if ids else ""),
                              details={"e14_failures": admitted["failures"]}))
        status, ids = _e13_status(report, ("source", "environment", "lock"))
        out.append(_condition("identity.source_config_environment", status, "source, configuration, environment and lock identity"
                              + (f"; not passing: {ids[:5]}" if ids else " all agree with the checkout")))
        status, ids = _e13_status(report, ("scientific",))
        out.append(_condition("reporting.d1_d8", status, "D-1 exposure disclosure and D-8 K17d identity are preserved" + (f"; not passing: {ids[:5]}" if ids else "")))
    policy = P.evaluate_operational_authorization(plan, reference, requested_scope=requested_scope, now=now,
                                                  adapters={k: v for k, v in adapters.items() if k in P.ADAPTER_NAMES}, max_reference_age_s=max_age)
    scope = [i for i in policy["findings"] if i["id"] == "scope.request"]
    out.append(_condition("authorization.scope", PASS if scope and scope[0]["status"] == P.PASS else FAIL,
                          "only full_generation for known, test and matched is requestable; every other compute stage is refused"))
    status = PASS if policy["state"] == P.STATE_VALID else BLOCKED if policy["state"] == P.STATE_CLOSED else FAIL
    out.append(_condition("authorization.policy", status, f"operational authorization state {policy['state']}",
                          details={"state": policy["state"], "failed": [i["id"] for i in policy["findings"] if i["status"] == P.FAIL]}))
    return out, policy["state"]


def _evidence_conditions(p, spec, boundary, now, adapters, max_age, policy_state):
    out, done = [], BOUNDARIES[boundary]
    expectations = expected_states(boundary)
    layout = {s["name"]: s for s in spec["stages"]}
    stage_docs, fingerprints = {}, {"known": p["source"]["known_request_fingerprint"]}
    for stage in STAGES:
        doc, status, message = _call(adapters, "shard_state", stage)
        if status:
            out.append(_condition(f"durability.{stage}", status, message))
            continue
        stage_docs[stage] = doc
        if stage != "known" and isinstance(doc, dict):
            fingerprints[stage] = doc.get("request_fingerprint")
    for stage, doc in stage_docs.items():
        problems = _stage_problems(stage, doc, layout[stage], p, expectations[stage], fingerprints.get(stage), now, max_age)
        if stage != "known" and stage in done and fingerprints.get(stage) in {fingerprints["known"], *(fingerprints.get(s) for s in done if s not in (stage, "known"))}:
            problems.append("the deferred request fingerprint equals another stage's (request aliasing)")
        out.append(_from_problems(f"durability.{stage}", problems, "every shard is committed, hash-verified, durably admitted and read-only"
                                  if expectations[stage] == "COMPLETE" else "the stage has not started and holds no data (stage order)"))
    out.append(_from_problems("isolation.roles", _isolation_problems(stage_docs), "every stage root and role directory is a distinct directory"))
    declaration, status, message = _call(adapters, "consumer_declaration")
    out.append(_condition("isolation.consumers", status, message) if status else
               _from_problems("isolation.consumers", check_consumer_isolation(declaration),
                              "train, val-select and val-calib read only their own known roles; no test or matched role reaches them"))
    for stage in done:
        if stage not in stage_docs:
            continue
        doc, status, message = _call(adapters, "backup_state", stage)
        out.append(_condition(f"backup.{stage}", status, message) if status else
                   _from_problems(f"backup.{stage}", _backup_problems(stage, doc, stage_docs[stage], p, now, max_age),
                                  "independent persistent backup device and a byte-verified restore copy for every role; no qualification claimed"))
    if not done:
        out.append(_condition("backup.devices", NOT_RUN, "no stage is complete yet; backup evidence starts at the first boundary", applicable=False))
    k17d = None
    if done:
        k17d, status, message = _call(adapters, "k17d_metadata")
        out.append(_condition("k17d.metadata", status, message) if status else
                   _from_problems("k17d.metadata", _k17d_problems(k17d, p, now, max_age),
                                  "production metadata match the accepted K17d identity (500/35/43/78/465), metadata-only, zero observation reads"))
    else:
        out.append(_condition("k17d.metadata", NOT_RUN, "needs the committed known test-role metadata; mandatory from the after_known boundary", applicable=False))
    journal, status, message = _call(adapters, "journal_state")
    if status:
        out.append(_condition("journal.external", status, message))
    elif not all(stage in stage_docs for stage in STAGES):
        out.append(_condition("journal.external", FAIL, "stage evidence is missing, so the journal cannot be bound to it"))
    else:
        auth = p["authorization"]
        problems = _journal_problems(journal, done, p, spec, stage_docs, k17d, fingerprints, now, max_age, auth["record_sha256"] if isinstance(auth, dict) else None)
        out.append(_from_problems("journal.external", problems, "hash-chained, anchored, outside the working tree; stage completion, backup and K17d entries "
                                  "are ordered and bound to the working-tree evidence"))
    stage = NEXT_STAGE[boundary] or "matched"
    resource, status, message = _call(adapters, "resource_state", stage)
    if policy_state != P.STATE_VALID:
        out.append(_condition("runtime.stop_conditions", BLOCKED, "no valid operational authorization exists to evaluate stop conditions against"))
    elif status:
        out.append(_condition("runtime.stop_conditions", status, message))
    else:
        # A VALID policy state already required a fresh non-revocation answer and an unexpired record at ``now``.
        stop = L.evaluate_stop_conditions(resource, p["ceilings"], {"expires_at": p["authorization"]["expires_at"], "revoked": False, "revocation_id": "checked-by-policy"},
                                          now=now, stage=stage, timing=p["timing"])
        out.append(_condition("runtime.stop_conditions", PASS if stop["decision"] != "STOP" else FAIL,
                              "no stop condition triggered at this boundary" if stop["decision"] != "STOP" else "stop: " + ", ".join(stop["reasons"][:4]),
                              details={"reasons": stop["reasons"], "projections": stop["projections"]}))
    return out

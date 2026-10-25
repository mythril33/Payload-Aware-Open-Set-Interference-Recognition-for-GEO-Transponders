#!/usr/bin/env python3
"""Sealed E14 planning/admission, never execution. No production argv or child API.

The serialized specification is the immutable boundary (ordinary Python dicts are
not immutable). Admission recomputes it from the complete E13 plan. Source, host
and approval facts are snapshots; a future separately reviewed executor must
recheck them. No E14 result is an authorization, even with consistent DR-04 data.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import b2_e13_generation_plan as G

SCHEMA = "B2-E14-sealed-launch-specification/1"
REPORT = "B2-E14-admission-report/1"
MAX_BYTES = 4 * 2**20
STAGE_NAMES = ("known", "test", "matched")
ARTIFACTS = {"known": "B2-feat/1", "test": "B2-test/1", "matched": "B2-match/1"}
RELEASE_CONTROLS = (
    "researcher_dr04_authorization", "reviewed_exact_source_head", "green_exact_head_ci",
    "independently_reviewed_execution_path", "run_bound_approved_ceilings",
    "designated_measured_host", "persistent_independent_backup", "clean_pinned_lock",
    "first_shard_and_remaining_budget_stop", "external_append_only_run_journal",
    "approval_expiry_and_strict_stop_conditions", "separate_production_release_review",
)
RUNTIME_POLICY = {
    "production_launch_enabled": False, "execution_available": False,
    "fixture_max_groups": 2, "authorizes_nothing": True, "benchmark_complete": False,
}


class PlanError(ValueError):
    pass


class ExecutionUnavailable(RuntimeError):
    pass


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def _document(value):
    """Bounded strict JSON copy; no foreign objects, nonfinite values or duplicate keys."""
    if not isinstance(value, dict) or G._depth_exceeds(value):
        raise PlanError("expected a bounded JSON object")
    raw = canonical(value).encode()
    if len(raw) > MAX_BYTES:
        raise PlanError("metadata exceeds four MiB")
    result = G.k17d_check._strict(raw)
    # json.dumps accepts tuples and integer keys: reject that silent normalization.
    def types(item):
        if item is None or type(item) in (str, bool, int, float):
            return
        if type(item) is dict and all(type(k) is str for k in item):
            for child in item.values():
                types(child)
        elif type(item) is list:
            for child in item:
                types(child)
        else:
            raise PlanError("non-JSON metadata type")
    types(value)
    return result


def _check_plan(plan):
    p = _document(plan)
    if set(p) != set(G.PLAN_KEYS) or p["schema"] != G.SCHEMA_PLAN or p["stage"] != "DR-04":
        raise PlanError("unknown or missing E13 plan fields")
    if p["mode"] != G.MODE or p["benchmark_complete"] is not False or G._forbidden_keys(p):
        raise PlanError("execution options are not permitted")
    if p["plan_fingerprint"] != G.plan_fingerprint(p):
        raise PlanError("modified plan fingerprint")
    expected = {"total_observations": 21350, "stage_order": list(STAGE_NAMES),
                "groups_per_shard": 4, "rows": G.pre.derive_inventory()}
    if canonical(p["inventory"]) != canonical(expected):
        raise PlanError("wrong role/group/shard inventory")
    # JSON object key order is irrelevant; the stage_order array is authoritative.
    if canonical(p["stages"]) != canonical(G.expected_stages()):
        raise PlanError("stage modules or options differ")
    if canonical(p["generator_assumptions"]) != canonical(G.expected_assumptions()):
        raise PlanError("frozen generator assumptions differ")
    s = p["source"]
    if type(s) is not dict or set(s) != set(G.SOURCE_KEYS) or not isinstance(s["git_commit"], str) or not G.HEX40.fullmatch(s["git_commit"]):
        raise PlanError("source identity incomplete")
    if s["source_tree_sha256"] != G.sha256_of(s["files_sha256"]):
        raise PlanError("source tree digest differs")
    if canonical(p["timing"]) != canonical(G.sup.DEFAULT_TIMING) or canonical(p["stop_rules"]) != canonical(G.STOP_RULES):
        raise PlanError("timing or interruption stop policy differs")
    if canonical(p["post_generation_obligations"]) != canonical(G.OBLIGATIONS):
        raise PlanError("D-1/D-8 reporting obligations differ")
    return p


def build_specification(plan):
    """Construct data only. Does not inspect a host, approve a plan or open artifacts."""
    p = _check_plan(plan)
    binding = {"source": p["source"], "environment": p["environment"],
               "scientific": p["scientific"], "lock": p["lock"]}
    stages = []
    for stage in STAGE_NAMES:
        shards = []
        for row in p["inventory"]["rows"]:
            if row["stage"] != ARTIFACTS[stage]:
                continue
            for number, first in enumerate(range(row["first_group"], row["last_group"] + 1, 4)):
                groups = list(range(first, min(first + 4, row["last_group"] + 1)))
                shard = {"role": row["role"], "ordinal": number, "groups": groups,
                         "variants_per_group": row["variants_per_group"],
                         "observations": len(groups) * row["variants_per_group"],
                         "binding_sha256": digest(binding), "payload_checksum": None,
                         "metadata_checksum": None, "commit_status": "NOT_GENERATED"}
                shard["planned_identity_sha256"] = digest(shard)
                shards.append(shard)
        stages.append({"name": stage, "kind": "NON_RUNNABLE_DECLARATIVE_SPECIFICATION",
                       "generator": p["stages"][stage], "identity": copy.deepcopy(binding),
                       "requires_completed_stage": {"known": None, "test": "known", "matched": "test"}[stage],
                       "known_artifact_binding_required": stage != "known",
                       "request_binding": {"status": "FROZEN" if stage == "known" else "DEFERRED_UNTIL_KNOWN_VERIFIED",
                                           "fingerprint": p["source"]["known_request_fingerprint"] if stage == "known" else None},
                       "shards": shards})
    spec = {"schema": SCHEMA, "plan_fingerprint": p["plan_fingerprint"],
            "approved_design_digest": G.approved_plan_digest(p), "stages": stages,
            "runtime_policy": dict(RUNTIME_POLICY), "required_future_release_controls": list(RELEASE_CONTROLS),
            "disk_policy": {"meaning": "reserve_remaining_after_projected_artifacts",
                            "reserve_gib": p["ceilings"]["min_free_disk_gib"],
                            "estimated_artifact_bytes": 21350 * G.sup.ARTIFACT_BYTES_PER_OBSERVATION,
                            "startup_free_gib": G.required_free_gib(21350, p["ceilings"]["min_free_disk_gib"])},
            "stage_boundary_recheck_required": True, "remaining_wall_and_core_projection_required": True,
            "append_only_external_journal_required": True,
            "no_permission": "A specification, review or green CI cannot authorize execution."}
    spec["specification_sha256"] = digest(spec)
    # Return no callables, Paths, arrays or mutable object aliases into the input.
    return _document(spec)


def admit(specification, plan, reference):
    """Validate a frozen snapshot, never authorize or launch work. No process creation."""
    failures = []
    e13_report = None
    spec_sha = None
    try:
        p, ref, submitted = _check_plan(plan), _document(reference), _document(specification)
        expected = build_specification(p)
        if canonical(submitted) != canonical(expected):
            raise PlanError("specification differs from the sealed plan, including hash or runtime policy")
        spec_sha = expected["specification_sha256"]
        # E13's historical validator inspects dict insertion order. Preserve its
        # documented stage order after strict JSON round-tripping sorted keys.
        p["stages"] = {name: p["stages"][name] for name in STAGE_NAMES}
        e13_report = G.validate_plan(p, ref)
        if not G.e9.validate_protocol_record(ref.get("scientific_protocol"))["ok"]:
            failures.append("R1-R10 scientific protocol mismatch")
        if p["scientific"]["d1_exposure"] != G._d1_from(ref["decision_record"]["document"]):
            failures.append("D-1 disclosure mismatch")
        if p["scientific"]["d8_k17d"] != G._d8_from(ref["decision_record"]["document"]):
            failures.append("D-8 identity mismatch")
        # All E13 checks, including DR-04/source/environment/host/device/lock,
        # must pass before the document can be called consistent.
        if e13_report["plan_status"] != G.DOCUMENT_OK:
            failures.append("E13 admission prerequisites incomplete or inconsistent")
    except (Exception, RecursionError) as error:
        # Input may be malformed; do not reflect arbitrary input in JSON/errors.
        failures.append("invalid metadata: " + type(error).__name__)
    result = {"schema": REPORT, "verdict": "NO-GO", "execution_permitted": False,
              "authorizes_nothing": True, "production_launch_enabled": False,
              "executor_implemented": False, "benchmark_complete": False,
              "document_consistent": not failures, "specification_sha256": spec_sha,
              "failures": failures, "e13_report": e13_report,
              "release_status": "UNAVAILABLE_REQUIRES_SEPARATE_REVIEW_AND_DR04",
              "snapshot_only": True, "production_metadata_cross_verification": "NOT_RUN"}
    canonical(result)
    return result


def deny_execution(*args, **kwargs):
    """Unconditional refusal before examining any supplied approval or command."""
    raise ExecutionUnavailable("E14 has no production execution adapter; DR-04 NO-GO")


def _parent_handle(p):
    directory = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for name in p.parts[1:-1]:
            child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            os.close(directory)
            directory = child
        return directory
    except BaseException:
        os.close(directory)
        raise


def _read(path):
    """Read bounded metadata through no-follow handles for every path component."""
    p = Path(os.path.abspath(path))
    if any(part in ("", ".", "..") for part in Path(path).parts) or "\\" in str(path):
        raise PlanError("unsafe metadata path")
    directory = _parent_handle(p)
    try:
        fd = os.open(p.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        with os.fdopen(fd, "rb") as stream:
            before = os.fstat(stream.fileno())
            if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_BYTES or before.st_nlink != 1:
                raise PlanError("input must be a bounded, unaliased regular metadata file")
            raw = stream.read(MAX_BYTES + 1)
            after = os.fstat(stream.fileno())
            stable = lambda value: (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns, value.st_nlink)
            if stable(before) != stable(after) or len(raw) > MAX_BYTES:
                raise PlanError("metadata changed during read")
        # Reopen the entire namespace, rather than just the old pinned parent.
        current_parent = _parent_handle(p)
        try:
            linked = os.stat(p.name, dir_fd=current_parent, follow_symlinks=False)
            if stable(after) != stable(linked):
                raise PlanError("metadata path substituted during read")
        finally:
            os.close(current_parent)
        return _document(G.k17d_check._strict(raw))
    finally:
        os.close(directory)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    commands = parser.add_subparsers(dest="action", required=True)
    for action in ("specification", "admission"):
        command = commands.add_parser(action, allow_abbrev=False)
        command.add_argument("--plan", required=True)
        if action == "admission":
            command.add_argument("--specification", required=True)
    args = parser.parse_args(argv)
    try:
        plan = _read(args.plan)
        if args.action == "specification":
            output = {"specification": build_specification(plan), "verdict": "NO-GO", "execution_permitted": False}
        else:
            reference = G.collect_reference(record_paths=(() if plan.get("authorization") is None else (plan["authorization"]["record"],)),
                                            roots=tuple(plan[k]["root"] for k in ("working", "backup") if isinstance(plan.get(k), dict)))
            output = admit(_read(args.specification), plan, reference)
        print(canonical(output))
        return 4
    except Exception as error:
        print(canonical({"verdict": "NO-GO", "execution_permitted": False, "authorizes_nothing": True,
                         "error": "invalid metadata: " + type(error).__name__}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

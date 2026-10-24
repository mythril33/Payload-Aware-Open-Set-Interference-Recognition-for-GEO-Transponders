"""Fail-closed supervisor for the staged B2/1 generation (E7a, P30).

    python scripts/b2_production_supervisor.py plan   --workdir W --max-groups 2        # dry run (default behaviour)
    python scripts/b2_production_supervisor.py plan   --workdir W --production          # validation only, never launches
    python scripts/b2_production_supervisor.py run    --workdir W --max-groups 2 --execute
    python scripts/b2_production_supervisor.py status   --workdir W
    python scripts/b2_production_supervisor.py verify   --workdir W
    python scripts/b2_production_supervisor.py complete --workdir W

The supervisor drives the existing generator CLIs (known, then test-only, then matched) as child processes and refuses
everything that is not provably safe. It is separate from the E4 matrix runner and deliberately cannot start the full
production run in this build: ``PRODUCTION_LAUNCH_ENABLED`` is False and every spawned command must carry
``--limit-groups`` of at most two groups. Dry-run is the default; children are spawned only by ``run --execute``.

Guarantees (each is exercised by tests/test_b2_production_supervisor.py on capped fixtures):
 * immutable source/config/environment lock created once and re-verified before every stage and attempt;
 * restart only under the identical plan (incl. launcher), lock, ceilings and an intact, anchored, hash-chained journal
   (``journal.jsonl`` + ``journal.head``) that belongs to this run.json/lock.json;
 * exit codes, elapsed (monotonic) / CPU time and peak RSS of every child from ``wait4``, journaled per attempt, plus heartbeats;
 * wall/CPU/RSS/attempt/disk ceilings enforced live and after the fact (a lost attempt is charged from its last heartbeat);
   first-shard throughput gate; an unreadable host probe fails closed;
 * SIGINT/SIGTERM stop the child group cleanly and leave a resumable root; the child dies with the supervisor;
 * orphaned shard files are moved to ``quarantine/`` with hashes, never deleted; INVALID roots are never touched;
 * a stage is complete only if its root audits COMPLETE with the exact planned inventory, was requested under the plan and
   the last supervised attempt ended cleanly; the completion marker needs all three.
Nothing here approves a researcher gate; ``benchmark_complete`` is always false.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import math
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import b2_production_preflight as pre  # noqa: E402

REPO = pre.REPO
PLAN_SCHEMA = "B2-production-plan/1"
RUN_SCHEMA = "B2-production-run/1"
JOURNAL_SCHEMA = "B2-production-journal/1"
COMPLETION_SCHEMA = "B2-production-completion/1"
STAGE_ORDER = ("known", "test", "matched")
MODULES = {"known": "geosim.b2_dataset", "test": "geosim.b2_test_dataset", "matched": "geosim.b2_matched_dataset"}
FIXTURE_MAX_GROUPS = 2                    # hard cap on --limit-groups of every spawned child in this build
FIXTURE_GROUPS_PER_SHARD = (1, 2)
PRODUCTION_LAUNCH_ENABLED = False         # E7a: the full production launch is not implemented; flipping this is a code change
EXIT_OK, EXIT_REFUSED, EXIT_FAILED, EXIT_BLOCKED, EXIT_INTERRUPTED = 0, 2, 3, 4, 6
CEILING_KEYS = ("wall_hours", "core_hours", "max_failed_attempts_per_stage", "max_interruptions_per_stage", "max_rss_gib",
                "min_free_disk_gib", "grace_s")
INTEGER_CEILINGS = ("max_failed_attempts_per_stage", "max_interruptions_per_stage")
FIXTURE_CEILINGS = {"wall_hours": 1.0, "core_hours": 2.0, "max_failed_attempts_per_stage": 2, "max_interruptions_per_stage": 10,
                    "max_rss_gib": 4.0, "min_free_disk_gib": 1.0, "grace_s": 10.0}
# A two-group fixture can never need more; a ceilings file may not stretch a fixture beyond these.
FIXTURE_CEILING_LIMITS = {"wall_hours": 4.0, "core_hours": 16.0, "max_failed_attempts_per_stage": 5,
                          "max_interruptions_per_stage": 50, "max_rss_gib": 16.0, "grace_s": 120.0}
PRODUCTION_CEILINGS = {"wall_hours": float(pre.PROPOSED_CEILINGS["generation_wall_hours"]),
                       "core_hours": float(pre.PROPOSED_CEILINGS["generation_core_hours"]), "max_failed_attempts_per_stage": 2,
                       "max_interruptions_per_stage": 20,
                       "max_rss_gib": float(pre.PROPOSED_CEILINGS["generator_ram_gib_per_process"]),
                       "min_free_disk_gib": float(pre.PROPOSED_CEILINGS["working_disk_gib"]), "grace_s": 60.0}
# A production plan may lower the proposed ceilings but never raise them: raising needs a researcher-approved record, and
# the launch that would consume one does not exist in this build.
PRODUCTION_CEILING_LIMITS = {key: PRODUCTION_CEILINGS[key] for key in
                             ("wall_hours", "core_hours", "max_failed_attempts_per_stage", "max_interruptions_per_stage", "max_rss_gib")}
PRODUCTION_CEILING_LIMITS["grace_s"] = 600.0
MAX_TOTAL_ATTEMPTS_PER_STAGE = 60         # a backstop independent of the ceilings
TIMING_LIMITS = {"tolerance": (0.0, 2.0), "startup_s": (0.0, 3600.0), "resume_verify_s_per_observation": (0.0, 1.0)}
HEARTBEAT_DEFAULT = {"fixture": 10.0, "production": 60.0}
THREAD_COUNT_ENV = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")     # PYTHONHASHSEED is not a thread count
DEFAULT_TIMING = {"enabled": True, "band_s_per_observation": [3.8, 5.0], "tolerance": 0.25, "startup_s": 30.0,
                  "resume_verify_s_per_observation": 0.01, "gate_shards": 1}
ARTIFACT_BYTES_PER_OBSERVATION = pre.BUDGET["measured_artifact_bytes_per_observation"]
POLL_S = 0.2


class SupervisorError(Exception):
    """A refusal or failure with a stable exit code; the message is journaled and printed, never swallowed."""

    def __init__(self, message, code=EXIT_FAILED):
        super().__init__(message)
        self.code = code


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def tools_sha256():
    """The supervisor and the preflight it relies on are part of the run identity: editing either between restarts is refused."""
    return {name: pre._file_hash(HERE / name) for name in ("b2_production_supervisor.py", "b2_production_preflight.py")}


# ---- hash-chained journal ----------------------------------------------------------------------------------

class Journal:
    """Append-only JSON-lines journal; every record carries its sequence number, the previous record's SHA-256 and its own.

    The chain detects accidental modification, gaps and reordering of records. A separate ``journal.head`` file (seq and
    hash of the newest record, replaced atomically after every append) anchors the tail, so a missing, emptied or
    tail-truncated journal is detected too; a crash between an append and its anchor update leaves a lag of one record,
    which is accepted. Neither file is authenticated: both detect accidental modification only.
    """

    HEAD_NAME = "journal.head"

    def __init__(self, path):
        self.path = Path(path)
        self.head_path = self.path.with_name(self.HEAD_NAME)
        self.seq = 0
        self.head = None

    @staticmethod
    def read(path):
        """Return (records, problems); a torn last line or any broken link is a problem, never silently repaired."""
        path = Path(path)
        if not path.exists():
            return [], []
        records, problems, previous = [], [], None
        lines = path.read_text().split("\n")
        if lines and lines[-1] == "":
            lines.pop()
        elif lines:
            problems.append("last journal line is incomplete (no terminating newline)")
        for number, line in enumerate(lines, start=1):
            try:
                record = pre._strict_json(line)
            except ValueError as error:
                problems.append(f"line {number}: not strict JSON ({error})")
                break
            if not isinstance(record, dict):
                problems.append(f"line {number}: not an object")
                break
            body = {key: value for key, value in record.items() if key != "sha256"}
            if record.get("seq") != number or record.get("prev") != previous or digest(body) != record.get("sha256"):
                problems.append(f"line {number}: broken chain (sequence, previous hash or content hash)")
                break
            records.append(record)
            previous = record["sha256"]
        return records, problems

    @staticmethod
    def anchor_problems(path, records):
        """Compare the verified records with journal.head: truncation, replacement and a missing anchor are problems."""
        head_path = Path(path).with_name(Journal.HEAD_NAME)
        count = len(records)
        if not head_path.exists():
            quiet = {"run.json", "lock.json", "journal.jsonl", Journal.HEAD_NAME + ".tmp", ".supervisor.lock"}
            parent = Path(path).parent
            if count <= 1 and (not parent.is_dir() or {p.name for p in parent.iterdir()} <= quiet):
                return []                                    # a workdir that crashed right after its first record, nothing run yet
            return ["journal.head is missing: the journal cannot be shown to be untruncated"]
        try:
            head = pre._strict_json(head_path.read_text())
            seq, sha = head["seq"], head["sha256"]
        except (OSError, ValueError, KeyError, TypeError):
            return ["journal.head is unreadable or malformed"]
        if isinstance(seq, bool) or not isinstance(seq, int) or seq < 1:
            return ["journal.head holds an invalid sequence number"]
        if seq > count:
            return [f"journal has {count} records but its anchor is at {seq}: truncated, emptied or replaced"]
        if records[seq - 1]["sha256"] != sha:
            return ["journal.head does not match the journal: the journal was rewritten"]
        if count - seq > 1:
            return [f"journal has {count - seq} records beyond its anchor (at most one is explained by a crash)"]
        return []

    @classmethod
    def load(cls, path):
        """``read`` plus the tail anchor: (records, problems)."""
        records, problems = cls.read(path)
        return records, problems or cls.anchor_problems(path, records)

    def open(self):
        records, problems = self.load(self.path)
        if problems:
            raise SupervisorError("journal is damaged: " + "; ".join(problems) + " - restore it from a backup or start a new "
                                  "workdir; the supervisor never repairs, resets or continues over damaged evidence", EXIT_REFUSED)
        self.seq = len(records)
        self.head = records[-1]["sha256"] if records else None
        return records

    def _tail_problem(self):
        """Cheap check before every append: the file must still end with the record this supervisor wrote last."""
        if self.seq == 0:
            return None if not self.path.exists() or self.path.stat().st_size == 0 else "the journal appeared while the supervisor held none"
        try:
            with open(self.path, "rb") as stream:
                stream.seek(0, os.SEEK_END)
                position = size = stream.tell()
                data = b""
                while position > 0 and data.count(b"\n") < 2:         # read backwards until the last line is complete
                    step = min(65536, position)
                    position -= step
                    stream.seek(position)
                    data = stream.read(step) + data
            lines = data.split(b"\n")
            if lines and lines[-1] == b"":
                lines.pop()
            last = pre._strict_json(lines[-1].decode()) if lines and size else None
        except (OSError, ValueError, UnicodeDecodeError):
            return "the journal tail is unreadable"
        if not isinstance(last, dict) or last.get("seq") != self.seq or last.get("sha256") != self.head:
            return "the journal no longer ends with the record this supervisor wrote last"
        return None

    def append(self, event, **fields):
        problem = self._tail_problem()
        if problem:
            raise SupervisorError(f"journal damaged during the run: {problem}; nothing more is appended to it", EXIT_FAILED)
        record = {"seq": self.seq + 1, "time": utc_now(), "event": event, "schema": JOURNAL_SCHEMA, **fields, "prev": self.head}
        record["sha256"] = digest(record)
        first = not self.path.exists()
        with open(self.path, "a") as stream:
            stream.write(json.dumps(record, sort_keys=True, allow_nan=False) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        if first:
            _fsync_directory(self.path.parent)
        self.seq, self.head = record["seq"], record["sha256"]
        self._write_head(record)
        return record

    def _write_head(self, record):
        temporary = self.head_path.with_name(self.HEAD_NAME + ".tmp")
        with open(temporary, "w") as stream:
            stream.write(json.dumps({"seq": record["seq"], "sha256": record["sha256"]}))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, self.head_path)
        _fsync_directory(self.path.parent)


def _fsync_directory(path):
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def check_run_journal(records, identity, lock):
    """Problems if the journal does not belong to this run.json/lock.json (missing, emptied, foreign or re-planned)."""
    if not records:
        return ["journal.jsonl is missing or empty although run.json exists"]
    problems = []
    if records[0]["event"] != "supervisor_start" or records[0].get("restart") is not False:
        problems.append("the first journal record is not the original supervisor_start")
    for record in records:
        if record["event"] != "supervisor_start":
            continue
        if record.get("plan_fingerprint") != identity["plan_fingerprint"]:
            problems.append(f"record {record['seq']}: plan fingerprint differs from run.json")
        if record.get("lock_fingerprint") != lock["lock_fingerprint"]:
            problems.append(f"record {record['seq']}: lock fingerprint differs from lock.json")
    return problems


def usage_from(records):
    """Cumulative wall/CPU seconds and per-stage attempt counts from the journal.

    ``attempts`` counts every started attempt; ``failed_attempts`` only attempts that ended in a child failure or a
    supervisor-enforced stop; operator interruptions and a lost supervisor are counted separately, so pausing a healthy
    run does not consume the failure budget. ``last_attempt_end`` is the newest attempt_end per stage.
    """
    usage = {"wall_s": 0.0, "cpu_s": 0.0, "open_attempt": None, "open_attempt_heartbeat": None,
             "attempts": {stage: 0 for stage in STAGE_ORDER}, "failed_attempts": {stage: 0 for stage in STAGE_ORDER},
             "interruptions": {stage: 0 for stage in STAGE_ORDER}, "lost_attempts": {stage: 0 for stage in STAGE_ORDER},
             "last_attempt_end": {stage: None for stage in STAGE_ORDER}}
    open_attempts, beats = {}, {}
    for record in records:
        event = record["event"]
        if event == "attempt_start":
            usage["attempts"][record["stage"]] += 1
            open_attempts[record["attempt_id"]] = record
        elif event == "heartbeat":
            beats[record["attempt_id"]] = record
        elif event == "attempt_end":
            stage, reason = record["stage"], record["reason"]
            open_attempts.pop(record["attempt_id"], None)
            usage["wall_s"] += max(0.0, record["elapsed_s"])
            usage["cpu_s"] += max(0.0, record["cpu_user_s"] + record["cpu_sys_s"])
            usage["last_attempt_end"][stage] = {"attempt_id": record["attempt_id"], "reason": reason,
                                                "exit_code": record.get("exit_code")}
            if reason == "interrupted":
                usage["interruptions"][stage] += 1
            elif reason == "supervisor_lost":
                usage["lost_attempts"][stage] += 1
            elif not (reason == "exited" and record.get("exit_code") == 0):
                usage["failed_attempts"][stage] += 1
    if open_attempts:
        usage["open_attempt"] = list(open_attempts.values())[-1]
        usage["open_attempt_heartbeat"] = beats.get(usage["open_attempt"]["attempt_id"])
    return usage


def last_attempt_acceptable(usage, stage):
    """A stage may be accepted as COMPLETE only if its last supervised attempt exited 0.

    An interrupted or lost attempt proves nothing about the root that is there now (it may have been replaced meanwhile),
    a non-zero exit, a supervisor-enforced stop or a failed wait are failures, and a root that no supervised attempt
    produced is an adoption. In all those cases the supervisor runs one more attempt (the generators treat a finished
    root as a no-op) and accepts the root only if that attempt exits 0.
    """
    last = usage["last_attempt_end"][stage]
    if last is None:
        return False, "no supervised attempt produced this root (adoption of foreign data is refused)"
    if last["reason"] == "exited" and last["exit_code"] == 0:
        return True, ""
    return False, (f"the last supervised attempt {last['attempt_id']} ended with reason {last['reason']!r}, exit code "
                   f"{last['exit_code']}: a root that verifies COMPLETE is accepted only after an attempt that exits 0")


def plan_root_problems(plan, audit):
    """A root whose request (group limit, shard size) is not the plan's was not produced under this plan."""
    summary = audit.get("request_summary")
    if audit["state"] in ("NOT_STARTED", "INVALID") or not summary:
        return []
    return [f"{key} is {summary.get(key)!r} in the root's request but {plan[key]!r} in the plan"
            for key in ("limit_groups", "groups_per_shard") if summary.get(key) != plan[key]]


# ---- plan ----------------------------------------------------------------------------------------------------

def expected_inventory(mode, limit_groups):
    """Observations per stage/role the plan must end with (production: the frozen 21,350 inventory)."""
    rows = pre.derive_inventory()
    table = {}
    for row in rows:
        groups = row["groups"] if limit_groups is None else min(limit_groups, row["groups"])
        stage = {"B2-feat/1": "known", "B2-test/1": "test", "B2-match/1": "matched"}[row["stage"]]
        table.setdefault(stage, {})[row["role"]] = groups * row["variants_per_group"]
    return table


def merge_ceilings(base, override, *, fixture=False):
    if override is None:
        return dict(base)
    if not isinstance(override, dict) or set(override) - set(CEILING_KEYS):
        raise SupervisorError(f"ceilings must be an object with keys from {CEILING_KEYS}", EXIT_REFUSED)
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise SupervisorError(f"ceiling {key} must be a finite positive number", EXIT_REFUSED)
        if key in INTEGER_CEILINGS and value != int(value):
            raise SupervisorError(f"ceiling {key} must be a whole number", EXIT_REFUSED)
        if fixture and key in FIXTURE_CEILING_LIMITS and value > FIXTURE_CEILING_LIMITS[key]:
            raise SupervisorError(f"ceiling {key}={value} exceeds the fixture limit {FIXTURE_CEILING_LIMITS[key]}: a capped "
                                  "two-group fixture never needs more and a ceilings file may not stretch it", EXIT_REFUSED)
        if not fixture and key == "min_free_disk_gib" and value < PRODUCTION_CEILINGS[key]:
            raise SupervisorError(f"ceiling {key}={value} is below the proposed production reserve {PRODUCTION_CEILINGS[key]}", EXIT_REFUSED)
        if not fixture and key in PRODUCTION_CEILING_LIMITS and value > PRODUCTION_CEILING_LIMITS[key]:
            raise SupervisorError(f"ceiling {key}={value} exceeds the proposed production ceiling {PRODUCTION_CEILING_LIMITS[key]}: "
                                  "raising it needs a researcher-approved record", EXIT_REFUSED)
        merged[key] = value
    for key in INTEGER_CEILINGS:
        merged[key] = int(merged[key])
    return merged


def _validated_timing(timing):
    merged = dict(DEFAULT_TIMING)
    for key, value in (timing or {}).items():
        if key not in DEFAULT_TIMING:
            raise SupervisorError(f"unknown timing option {key!r}", EXIT_REFUSED)
        merged[key] = value
    low, high = merged["band_s_per_observation"]
    if not (isinstance(low, (int, float)) and isinstance(high, (int, float)) and not isinstance(low, bool)
            and not isinstance(high, bool) and math.isfinite(low) and math.isfinite(high) and 0 <= low < high):
        raise SupervisorError("timing band must be two finite numbers 0 <= low < high", EXIT_REFUSED)
    for key, (lo, hi) in TIMING_LIMITS.items():
        value = merged[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not lo <= value <= hi:
            raise SupervisorError(f"timing {key} must be a finite number in [{lo}, {hi}]", EXIT_REFUSED)
    if isinstance(merged["gate_shards"], bool) or not isinstance(merged["gate_shards"], int) or not 1 <= merged["gate_shards"] <= 4:
        raise SupervisorError("timing gate_shards must be an integer 1..4", EXIT_REFUSED)
    if not isinstance(merged["enabled"], bool):
        raise SupervisorError("timing enabled must be true or false", EXIT_REFUSED)
    return merged


def expected_shards(plan, stage):
    """Shards the plan expects for a stage, independent of how much of the root exists yet."""
    samples = pre.STAGES[stage]["samples"]
    return sum(-(-(observations // samples) // plan["groups_per_shard"])
               for observations in plan["expected_observations"][stage].values())


def build_plan(workdir, *, mode, max_groups=None, groups_per_shard=1, ceilings=None, timing=None, launcher="generators",
               heartbeat_s=None):
    """Validate and freeze the request. Capped fixtures need 1..2 groups; production has no limit but cannot be launched.

    ``launcher`` names how children are started (``generators`` or ``child-wrapper:<name>:<sha256>`` for fixture
    diagnostics) and is part of the run identity, so a stand-in workdir can never be mistaken for a real one.
    """
    if mode not in ("fixture", "production"):
        raise SupervisorError("mode must be fixture or production", EXIT_REFUSED)
    if not (launcher == "generators" or (mode == "fixture" and isinstance(launcher, str) and launcher.startswith("child-wrapper:"))):
        raise SupervisorError("the launcher must be the real generators (a diagnostic wrapper is allowed for fixtures only)",
                              EXIT_REFUSED)
    heartbeat_s = HEARTBEAT_DEFAULT[mode] if heartbeat_s is None else heartbeat_s
    if isinstance(heartbeat_s, bool) or not isinstance(heartbeat_s, (int, float)) or not math.isfinite(heartbeat_s) \
            or not 0.05 <= heartbeat_s <= 3600:
        raise SupervisorError("heartbeat_s must be a finite number of seconds in [0.05, 3600]", EXIT_REFUSED)
    if mode == "fixture":
        if isinstance(max_groups, bool) or not isinstance(max_groups, int) or not 1 <= max_groups <= FIXTURE_MAX_GROUPS:
            raise SupervisorError(f"a bounded run needs --max-groups 1..{FIXTURE_MAX_GROUPS}; unbounded generation is not "
                                  "available in this build", EXIT_REFUSED)
        if groups_per_shard not in FIXTURE_GROUPS_PER_SHARD:
            raise SupervisorError(f"fixture runs use groups-per-shard in {FIXTURE_GROUPS_PER_SHARD}", EXIT_REFUSED)
        limit = max_groups
        base_ceilings = FIXTURE_CEILINGS
    else:
        if max_groups is not None:
            raise SupervisorError("--production and --max-groups are mutually exclusive", EXIT_REFUSED)
        if timing:
            raise SupervisorError("a production plan uses the E6 timing band as is; timing options are fixture diagnostics", EXIT_REFUSED)
        if groups_per_shard != pre.PRODUCTION["groups_per_shard"]:
            raise SupervisorError("the production plan uses four groups per shard", EXIT_REFUSED)
        limit = None
        base_ceilings = PRODUCTION_CEILINGS
    merged_timing = _validated_timing(timing)
    inventory = expected_inventory(mode, limit)
    return {"schema": PLAN_SCHEMA, "mode": mode, "limit_groups": limit, "groups_per_shard": groups_per_shard,
            "roots": {stage: stage for stage in STAGE_ORDER}, "stage_order": list(STAGE_ORDER),
            "expected_observations": inventory,
            "total_observations": sum(sum(roles.values()) for roles in inventory.values()),
            "ceilings": merge_ceilings(base_ceilings, ceilings, fixture=mode == "fixture"), "timing": merged_timing,
            "launcher": launcher, "heartbeat_s": float(heartbeat_s),
            "configs": {"b2": "configs/b2_base.json", "cancellation": "configs/cancellation.json"},
            "production_launch_enabled": PRODUCTION_LAUNCH_ENABLED, "benchmark_complete": False}


def stage_argv(stage, plan, work, python=sys.executable):
    """The exact generator command for a stage; every command is bounded by --limit-groups in fixture mode."""
    if plan["limit_groups"] is None:
        raise SupervisorError("an unbounded stage command is never built in this build", EXIT_REFUSED)
    argv = [python, "-m", MODULES[stage], "--out", str(Path(work) / plan["roots"][stage]), "--config", str(REPO / plan["configs"]["b2"]),
            "--cancellation", str(REPO / plan["configs"]["cancellation"]), "--groups-per-shard",
            str(plan["groups_per_shard"]), "--limit-groups", str(plan["limit_groups"])]
    if stage != "known":
        argv += ["--known", str(Path(work) / plan["roots"]["known"])]
    return argv


def wrapper_launcher(wrapper, python=sys.executable):
    """Diagnostic launcher: ``python WRAPPER STAGE <generator args>`` instead of ``python -m MODULE <args>``."""
    def launch(stage, plan, work):
        return [python, str(wrapper), stage, *stage_argv(stage, plan, work, python)[3:]]
    return launch


def default_launcher(stage, plan, work):
    return stage_argv(stage, plan, work)


def assert_bounded(argv):
    """Defense in depth: no child is ever spawned without a --limit-groups of 1..FIXTURE_MAX_GROUPS."""
    if "--limit-groups" not in argv:
        raise SupervisorError("refusing to spawn a child without --limit-groups (unbounded generation)", EXIT_REFUSED)
    try:
        value = int(argv[argv.index("--limit-groups") + 1])
    except (IndexError, ValueError):
        raise SupervisorError("--limit-groups must be an integer", EXIT_REFUSED) from None
    if not 1 <= value <= FIXTURE_MAX_GROUPS:
        raise SupervisorError(f"refusing to spawn a child with --limit-groups {value} (cap {FIXTURE_MAX_GROUPS})", EXIT_REFUSED)


# ---- authorization and dry-run checks ------------------------------------------------------------------------

PRODUCTION_GATES = ("K18", "K17d", "OBS-CANCEL-2", "full_generation")


def authorization(gates, memo):
    """(authorized, reasons): production needs every gate PASS in the preflight sense; it never infers approval."""
    checks = {item["id"]: item for item in pre.check_gates(gates, memo)}
    reasons = [f"{key}: {checks[f'gates.{key}']['status']} ({checks[f'gates.{key}']['message']})"
               for key in PRODUCTION_GATES if checks[f"gates.{key}"]["status"] != pre.PASS]
    if checks["gates.benchmark_complete"]["status"] != pre.PASS:
        reasons.append("benchmark_complete is not false")
    reasons += [f"{item['id']}: {item['message']}" for item in checks.values() if item["id"].endswith(".consistency")]
    return not reasons, reasons


def dry_run_checks(plan, workdir, *, lock_builder=pre.build_lock, gates=None, memo=None, disk_usage=shutil.disk_usage,
                   probe=pre.probe_resources):
    gates = gates if gates is not None else pre._read_json(REPO / pre.GATES_PATH)
    memo = memo if memo is not None else pre._read_json(REPO / pre.MEMO_PATH)
    out = []
    lock = lock_builder()
    clean = lock["git"]["clean"]
    out.append(pre.check("supervisor.lock", "Source/config/environment lock can be created",
                         pre.PASS if clean or plan["mode"] == "fixture" else pre.FAIL,
                         f"git {lock['git']['commit'][:12]}, tree {'clean' if clean else 'DIRTY'}; a production lock requires a "
                         "clean tree, a bounded fixture may record a dirty one", lock_fingerprint=lock["lock_fingerprint"]))
    ceilings = plan["ceilings"]
    target = Path(workdir)
    while not target.exists() and target != target.parent:
        target = target.parent
    out.append(pre.check("supervisor.caps", "Plan is bounded", pre.PASS if plan["mode"] == "fixture" else pre.BLOCKED,
                         f"limit_groups={plan['limit_groups']}, groups_per_shard={plan['groups_per_shard']}, "
                         f"{plan['total_observations']} observations" if plan["mode"] == "fixture"
                         else "production plan has no group limit; launching it is not implemented in this build"))
    low, high = plan["timing"]["band_s_per_observation"]
    wall_high_h = plan["total_observations"] * high / 3600
    out.append(pre.check("supervisor.wall_budget", "Estimated wall time fits the wall ceiling",
                         pre.PASS if wall_high_h <= ceilings["wall_hours"] else pre.FAIL,
                         f"{wall_high_h:.3f} h at {high} s/observation (high end of the timing band) versus ceiling "
                         f"{ceilings['wall_hours']} h; the band is an extrapolation, not a measurement of this plan"))
    need_gib = plan["total_observations"] * ARTIFACT_BYTES_PER_OBSERVATION / 2 ** 30
    free_gib = disk_usage(target).free / 2 ** 30
    out.append(pre.check("supervisor.disk_budget", "Free disk covers the estimated artifacts plus the reserve",
                         pre.PASS if free_gib >= need_gib * 1.1 + ceilings["min_free_disk_gib"] else pre.FAIL,
                         f"{free_gib:.2f} GiB free; estimated {need_gib:.3f} GiB artifacts (+10 %) plus a "
                         f"{ceilings['min_free_disk_gib']} GiB reserve"))
    resource_ceilings = dict(pre.PROPOSED_CEILINGS, working_disk_gib=ceilings["min_free_disk_gib"],
                             host_ram_gib_generation=ceilings["max_rss_gib"])
    out += [item for item in probe(target, resource_ceilings) if item["id"] != "resources.gpu"]
    authorized, reasons = authorization(gates, memo)
    out.append(pre.check("supervisor.authorization", "Researcher authorization for the unbounded production run",
                         pre.PASS if authorized else pre.BLOCKED,
                         "all production gates are approved with provenance" if authorized
                         else "not authorized: " + "; ".join(reasons[:6]), authorized=authorized))
    if plan["mode"] == "production":
        out.append(pre.check("supervisor.production_launch", "Production launch implemented in this build", pre.BLOCKED,
                             "PRODUCTION_LAUNCH_ENABLED is False: the E7a supervisor validates and journals bounded fixtures only"))
    return out


# ---- child supervision -----------------------------------------------------------------------------------------

def _die_with_parent():                      # runs in the child between fork and exec (Linux PR_SET_PDEATHSIG)
    try:
        import ctypes
        ctypes.CDLL(None, use_errno=True).prctl(1, signal.SIGKILL)      # PR_SET_PDEATHSIG: not ignorable
    except Exception:
        pass


def pid_alive(pid):
    """True while the process exists and is not a zombie/dead entry (an unreaped dead child is not a live writer)."""
    try:
        state = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0]
        return state not in ("Z", "X")
    except (OSError, IndexError):
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True


def proc_status_kib(pid, field):
    try:
        for line in Path(f"/proc/{pid}/status").read_text().splitlines():
            if line.startswith(field + ":"):
                return int(line.split()[1])
    except (OSError, ValueError, IndexError):
        pass
    return None


def proc_vmrss_kib(pid):
    return proc_status_kib(pid, "VmRSS")


def proc_vmhwm_kib(pid):
    """Peak resident set of a live process; exec resets it, so for a child it is the child's own high-water mark."""
    return proc_status_kib(pid, "VmHWM")


def proc_cpu_s(pid):
    try:
        fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
        return sum(int(fields[i]) for i in (11, 12, 13, 14)) / os.sysconf("SC_CLK_TCK")      # utime stime cutime cstime
    except (OSError, ValueError, IndexError):
        return None


class Outcome(dict):
    """Result of one supervised child: exit_code, reason, elapsed/cpu/rss, signal."""


def run_child(argv, *, cwd, env, log_path, timeout_s, cpu_budget_s, rss_limit_kib, grace_s, interrupted, on_poll=None,
              on_start=None, on_heartbeat=None, heartbeat_s=None, poll_s=POLL_S, sleep=time.sleep):
    """Spawn ``argv`` in its own process group and supervise it; exit status and resources come from ``wait4``.

    Elapsed time and deadlines use the monotonic clock. A signal that arrived before the spawn raises (no log, no child).
    ``peak_rss_kib`` is ``ru_maxrss`` (an upper bound: fork copies the supervisor's own peak into it); the live polling of
    ``VmHWM`` (reset by exec) gives ``peak_rss_polled_kib``, a lower bound, and enforcement uses the polled value live and
    ``ru_maxrss`` afterwards only when it exceeds what the supervisor itself held at the spawn.
    """
    assert_bounded(argv)
    if interrupted():
        raise SupervisorError("interrupted before the child was started; nothing was spawned", EXIT_INTERRUPTED)
    supervisor_hwm = proc_vmhwm_kib(os.getpid()) or 0
    log = open(log_path, "xb")
    started = time.monotonic()
    try:
        proc = subprocess.Popen(argv, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
                                preexec_fn=_die_with_parent)
    finally:
        log.close()
    reason, status, rusage, killed_at, polled_peak, last_beat = "exited", None, None, None, 0, started
    try:
        if on_start:
            on_start(proc.pid)

        def reap(block):
            try:
                pid, state, usage = os.wait4(proc.pid, 0 if block else os.WNOHANG)
            except ChildProcessError:
                return True, None, None
            return pid != 0, state, usage

        def terminate(why):
            nonlocal reason, killed_at
            reason, killed_at = why, time.monotonic()
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass

        while True:
            done, state, usage = reap(False)
            if done:
                status, rusage = state, usage
                break
            now = time.monotonic()
            peak = proc_vmhwm_kib(proc.pid)
            if peak is not None:
                polled_peak = max(polled_peak, peak)
            if killed_at is not None:
                if now - killed_at > grace_s:
                    try:
                        os.killpg(proc.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
            elif interrupted():
                terminate("interrupted")
            elif now - started > timeout_s:
                terminate("timeout")
            else:
                cpu = proc_cpu_s(proc.pid)
                if polled_peak > rss_limit_kib:
                    terminate("rss_limit")
                elif cpu is not None and cpu > cpu_budget_s:
                    terminate("cpu_limit")
                else:
                    if on_heartbeat is not None and heartbeat_s and now - last_beat >= heartbeat_s:
                        last_beat = now
                        on_heartbeat({"elapsed_s": round(now - started, 3), "cpu_s": round(cpu or 0.0, 3),
                                      "rss_kib": proc_vmrss_kib(proc.pid) or 0, "peak_rss_polled_kib": polled_peak})
                    if on_poll is not None:
                        verdict = on_poll(now - started)
                        if verdict:
                            terminate(verdict)
            sleep(poll_s)
    except BaseException:                                   # supervision failed (e.g. a damaged journal): never leave the child running
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        try:
            os.wait4(proc.pid, 0)
        except ChildProcessError:
            pass
        proc.returncode = -9
        raise
    elapsed = max(0.0, time.monotonic() - started)
    stragglers = False                                      # nothing may outlive an attempt: the group is emptied once its leader is gone
    try:
        os.killpg(proc.pid, 0)
        stragglers = True
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass
    code = os.waitstatus_to_exitcode(status) if status is not None else None
    proc.returncode = code if code is not None else -1      # the pid was reaped here; keep Popen.__del__ quiet
    if code is None and reason == "exited":
        reason = "wait_failed"                              # e.g. an inherited SIGCHLD=SIG_IGN: the exit status is unknown
    maxrss = int(getattr(rusage, "ru_maxrss", 0))
    outcome = Outcome(exit_code=code, reason=reason, elapsed_s=round(elapsed, 3),
                      cpu_user_s=round(getattr(rusage, "ru_utime", 0.0), 3), cpu_sys_s=round(getattr(rusage, "ru_stime", 0.0), 3),
                      peak_rss_kib=maxrss, peak_rss_polled_kib=int(polled_peak), supervisor_peak_rss_kib=int(supervisor_hwm),
                      stragglers_killed=stragglers, pid=proc.pid, log=str(log_path))
    if code is not None and code < 0:
        try:
            outcome["signal"] = signal.Signals(-code).name
        except ValueError:
            outcome["signal"] = f"SIG{-code}"                   # e.g. a real-time signal
    return outcome


def rss_exceeded(outcome, limit_kib):
    """Polled VmHWM counts as measured; ``ru_maxrss`` only when above what the supervisor itself held at the spawn.

    fork copies the supervisor's own peak into the child's ``ru_maxrss``, so a large supervisor must not be blamed on its child.
    """
    return (outcome["peak_rss_polled_kib"] > limit_kib
            or (outcome["peak_rss_kib"] > limit_kib and outcome["peak_rss_kib"] > outcome["supervisor_peak_rss_kib"]))


class TimingGate:
    """Compares the first newly committed shard of an attempt with the per-observation timing band."""

    def __init__(self, root, timing, *, started, committed_observations, first_shard_observations, remaining_shards):
        self.root, self.timing, self.started = Path(root), timing, started
        self.startup = timing["startup_s"] + timing["resume_verify_s_per_observation"] * committed_observations
        self.first_shard_observations = first_shard_observations
        self.active = bool(timing["enabled"]) and remaining_shards > 0
        self.decision = None
        self.record = None

    def __call__(self, elapsed):
        if not self.active or self.decision is not None:
            return None
        low, high = self.timing["band_s_per_observation"]
        slack = 1 + self.timing["tolerance"]
        new = []
        for path in self.root.glob("*/shard-*.json"):
            try:
                mtime = path.stat().st_mtime
            except OSError:
                continue
            if mtime >= self.started - 0.5:
                new.append((mtime, path))
        if len(new) >= self.timing["gate_shards"]:
            new.sort()
            mtime, path = new[self.timing["gate_shards"] - 1]
            try:
                n = pre._read_json(path)["n_samples"]
            except (OSError, ValueError, KeyError):
                return None                                     # the descriptor is written atomically; re-read next poll
            span = max(0.0, mtime - self.started - self.startup)
            per_observation = span / (n * self.timing["gate_shards"])
            if per_observation > high * slack:
                self.decision, self.record = "timing_gate", {"outcome": "too_slow", "s_per_observation": per_observation}
            else:
                outcome = "faster_than_band" if per_observation < low / slack else "within_band"
                self.decision, self.record = "pass", {"outcome": outcome, "s_per_observation": per_observation}
            self.record.update(band=[low, high], tolerance=self.timing["tolerance"], startup_allowance_s=self.startup,
                               observations=n * self.timing["gate_shards"])
            return self.decision if self.decision == "timing_gate" else None
        deadline = self.startup + self.first_shard_observations * self.timing["gate_shards"] * high * slack
        if elapsed > deadline:
            self.decision = "timing_gate"
            self.record = {"outcome": "no_shard_before_deadline", "deadline_s": deadline, "band": [low, high]}
            return "timing_gate"
        return None


# ---- quarantine ------------------------------------------------------------------------------------------------

def quarantine_orphans(root, audit, journal, stage):
    """Move uncommitted shard data files into quarantine/<stamp>/<role>/ with hashes; nothing is ever deleted."""
    root = Path(root)
    moved = []
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    for role, info in audit["roles"].items():
        for index in info["orphan"]:
            for name in (f"part-{index:05d}.npz", f"meta-{index:05d}.jsonl"):
                source = root / role / name
                if not source.exists():
                    continue
                target_dir = root / "quarantine" / f"{stamp}-{journal.seq + 1:04d}" / role
                target_dir.mkdir(parents=True, exist_ok=True)
                moved.append({"role": role, "file": name, "bytes": source.stat().st_size, "sha256": pre._file_hash(source),
                              "to": str((target_dir / name).relative_to(root))})
                os.rename(source, target_dir / name)
    if not moved:
        raise SupervisorError("quarantine requested but no orphan files were found", EXIT_FAILED)
    note = root / "quarantine" / moved[0]["to"].split("/")[1] / "QUARANTINE.json"
    pre._write_new(note, json.dumps({"reason": "data files without a committed descriptor", "files": moved}, indent=1) + "\n")
    journal.append("quarantine", stage=stage, files=moved)
    return moved


# ---- the supervisor --------------------------------------------------------------------------------------------

class Supervisor:
    def __init__(self, workdir, plan, *, launcher=default_launcher, lock_builder=pre.build_lock, allow_dirty=False,
                 disk_usage=shutil.disk_usage, gates=None, memo=None, audit_depth="checksum", poll_s=POLL_S,
                 sleep=time.sleep, environ=None, probe=pre.probe_resources):
        self.work = Path(workdir)
        self.plan = plan
        self.launcher = launcher
        self.lock_builder = lock_builder
        self.allow_dirty = allow_dirty
        self.disk_usage = disk_usage
        self.gates, self.memo = gates, memo
        self.audit_depth = audit_depth
        self.probe = probe
        self.poll_s, self.sleep = poll_s, sleep
        self.environ = dict(os.environ if environ is None else environ)
        self.journal = Journal(self.work / "journal.jsonl")
        self.lock = None
        self.interrupt = None
        self._flock = None
        self._journal_open = False

    def _root(self, stage):
        return self.work / self.plan["roots"][stage]

    # -- identity, lock, journal -------------------------------------------------------------------------------
    def _acquire(self):
        self.work.mkdir(parents=True, exist_ok=True)
        self._flock = open(self.work / ".supervisor.lock", "a")
        try:
            fcntl.flock(self._flock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise SupervisorError("another supervisor holds this workdir", EXIT_REFUSED) from None

    def _identity(self):
        return {"schema": RUN_SCHEMA, "plan": self.plan, "plan_fingerprint": digest(self.plan), "tools_sha256": tools_sha256()}

    def _init_or_verify_identity(self):
        path = self.work / "run.json"
        if path.exists():
            stored = pre._read_json(path)
            if stored != self._identity():
                raise SupervisorError("restart refused: the requested plan (limits, shard size, ceilings, timing, paths) differs "
                                      "or the supervisor/preflight code differs from the one this workdir was started with", EXIT_REFUSED)
            return True
        entries = [p.name for p in self.work.iterdir() if p.name != ".supervisor.lock"]
        if entries:
            raise SupervisorError(f"workdir is not empty and has no run.json: {sorted(entries)[:5]}", EXIT_REFUSED)
        pre._write_new(path, json.dumps(self._identity(), indent=1, allow_nan=False) + "\n")
        return False

    def _never_started(self):
        """run.json (and maybe the lock) exist but nothing else: a crash before the first journal record."""
        return {p.name for p in self.work.iterdir()} <= {"run.json", "lock.json", ".supervisor.lock"}

    def _init_or_verify_lock(self, restart, never_started=False):
        path = self.work / "lock.json"
        if restart and (path.exists() or not never_started):
            self.lock = pre._read_json(path)
            self._check_lock()
            return
        lock = self.lock_builder()
        if not lock["git"]["clean"] and not self.allow_dirty:
            raise SupervisorError("working tree has uncommitted edits under src/configs/pyproject; commit first or pass "
                                  "--allow-dirty-fixture for a bounded fixture", EXIT_REFUSED)
        if not lock["git"]["clean"] and self.plan["mode"] != "fixture":
            raise SupervisorError("a production lock requires a clean tree", EXIT_REFUSED)
        pre._write_new(path, json.dumps(lock, indent=1, allow_nan=False) + "\n")
        self.lock = lock

    def _check_lock(self):
        problems = pre.verify_lock(self.lock, require_clean=self.plan["mode"] != "fixture")
        if problems:
            raise SupervisorError("source/config/environment drift since the lock was created: " + "; ".join(problems[:6]),
                                  EXIT_FAILED)

    # -- budgets -----------------------------------------------------------------------------------------------
    def _usage(self):
        records, problems = Journal.load(self.journal.path)
        if problems:
            raise SupervisorError("journal damaged during the run: " + "; ".join(problems), EXIT_FAILED)
        return usage_from(records)

    def _check_budgets(self, usage, remaining_observations):
        ceilings = self.plan["ceilings"]
        if usage["wall_s"] >= ceilings["wall_hours"] * 3600:
            raise SupervisorError("wall-time ceiling exhausted", EXIT_FAILED)
        if usage["cpu_s"] >= ceilings["core_hours"] * 3600:
            raise SupervisorError("CPU-time ceiling exhausted", EXIT_FAILED)
        free = self.disk_usage(self.work).free / 2 ** 30
        need = remaining_observations * ARTIFACT_BYTES_PER_OBSERVATION / 2 ** 30 * 1.1 + ceilings["min_free_disk_gib"]
        if free < need:
            raise SupervisorError(f"free disk {free:.2f} GiB is below the {need:.2f} GiB needed for the remaining "
                                  "observations plus the reserve", EXIT_FAILED)

    # -- audits ------------------------------------------------------------------------------------------------
    def _audit(self, stage, *, depth=None):
        known = self._root("known") if stage != "known" else None
        audit = pre.audit_artifact(self._root(stage), stage, depth=depth or self.audit_depth, lock=self.lock,
                                   known=known, production=self.plan["mode"] == "production")
        self.journal.append("stage_audit", stage=stage, state=audit["state"], depth=audit["depth"],
                            roles={role: {k: info[k] for k in ("expected_shards", "committed", "missing")} for role, info in audit["roles"].items()},
                            problems=[{"code": p["code"], "severity": p["severity"]} for p in audit["problems"]],
                            hashed_bytes=audit["hashed_bytes"])
        mismatches = plan_root_problems(self.plan, audit)
        if mismatches:
            raise SupervisorError(f"{stage} root was not produced under this plan ({'; '.join(mismatches)}); not touching it",
                                  EXIT_FAILED)
        return audit

    def _prior_stages_intact(self, stage):
        order = STAGE_ORDER
        for earlier in order[:order.index(stage)]:
            audit = self._audit(earlier)
            if audit["state"] != "COMPLETE":
                raise SupervisorError(f"stage {earlier} is {audit['state']}, not COMPLETE: refusing to continue with {stage}",
                                      EXIT_FAILED)

    def _no_later_stage_data(self, stage):
        """Called only when this stage still has work to do: data of a later stage then proves an out-of-order run."""
        order = STAGE_ORDER
        for later in order[order.index(stage) + 1:]:
            later_root = self._root(later)
            if later_root.is_dir() and any(later_root.iterdir()):
                raise SupervisorError(f"ordering violation: {later} data exists before {stage} is complete", EXIT_FAILED)

    # -- one stage ---------------------------------------------------------------------------------------------
    def _remaining_observations(self, audit, stage):
        done = sum(info["observations_committed"] for info in audit["roles"].values())
        return max(0, sum(self.plan["expected_observations"][stage].values()) - done)

    def _check_attempt_budgets(self, usage, stage, verifying_complete_root=False):
        ceilings = self.plan["ceilings"]
        if usage["failed_attempts"][stage] >= ceilings["max_failed_attempts_per_stage"]:
            raise SupervisorError(f"attempt budget exhausted for {stage}: {usage['failed_attempts'][stage]} failed attempts "
                                  f"(ceiling {ceilings['max_failed_attempts_per_stage']})", EXIT_FAILED)
        paused = usage["interruptions"][stage] + usage["lost_attempts"][stage]
        # the no-op attempt that verifies an already finished root cannot add an interruption's worth of lost work
        if paused >= ceilings["max_interruptions_per_stage"] and not verifying_complete_root:
            raise SupervisorError(f"interruption budget exhausted for {stage}: {paused} interrupted or lost attempts "
                                  f"(ceiling {ceilings['max_interruptions_per_stage']})", EXIT_FAILED)
        if usage["attempts"][stage] >= MAX_TOTAL_ATTEMPTS_PER_STAGE:
            raise SupervisorError(f"total attempt backstop reached for {stage} ({MAX_TOTAL_ATTEMPTS_PER_STAGE})", EXIT_FAILED)

    def _run_stage(self, stage):
        self.journal.append("stage_start", stage=stage)
        quarantined = False
        while True:
            if self.interrupt is not None:
                raise SupervisorError("interrupted between attempts; the root is left resumable", EXIT_INTERRUPTED)
            self._check_lock()
            self._prior_stages_intact(stage)
            audit = self._audit(stage)
            if audit["state"] == "INVALID":
                raise SupervisorError(f"{stage} root is INVALID ({', '.join(sorted({p['code'] for p in audit['problems']}))}); "
                                      "not touching it - use a fresh workdir or a documented restoration", EXIT_FAILED)
            if audit["state"] != "COMPLETE":
                self._no_later_stage_data(stage)
            if audit["state"] == "NEEDS_QUARANTINE":
                if quarantined:
                    raise SupervisorError("orphan files reappeared after quarantine", EXIT_FAILED)
                quarantine_orphans(self._root(stage), audit, self.journal, stage)
                quarantined = True
                continue
            usage = self._usage()
            complete_root = audit["state"] == "COMPLETE"
            if complete_root:
                self._verify_inventory(stage, audit)
                acceptable, why = last_attempt_acceptable(usage, stage)
                if acceptable:
                    self.journal.append("stage_complete", stage=stage)
                    return
                # A root that verifies but was not produced by a clean supervised attempt gets one (the generators treat a
                # finished root as a no-op); it is accepted only if that attempt exits 0, and retried within the failure budget.
                self.journal.append("stage_needs_supervised_attempt", stage=stage, reason=why)
            self._check_attempt_budgets(usage, stage, verifying_complete_root=complete_root)
            self._check_budgets(usage, self._remaining_observations(audit, stage))
            outcome = self._attempt(stage, audit, usage)
            if outcome["reason"] == "interrupted":
                raise SupervisorError("interrupted; the root is left resumable", EXIT_INTERRUPTED)
            if outcome["reason"] != "exited":
                raise SupervisorError(f"{stage} attempt stopped by the supervisor: {outcome['reason']}", EXIT_FAILED)
            if outcome["exit_code"] != 0:
                self.journal.append("attempt_failed", stage=stage, exit_code=outcome["exit_code"],
                                    signal=outcome.get("signal"))
                continue                                       # re-audit; the failure budget bounds the retries
            after = self._audit(stage)
            if after["state"] != "COMPLETE":
                raise SupervisorError(f"{stage} child exited 0 but the root is {after['state']}", EXIT_FAILED)
            self._verify_inventory(stage, after)
            self.journal.append("stage_complete", stage=stage)
            return

    def _verify_inventory(self, stage, audit):
        found = {role: info["observations_committed"] for role, info in audit["roles"].items()}
        if found != self.plan["expected_observations"][stage]:
            raise SupervisorError(f"{stage} inventory {found} differs from the plan "
                                  f"{self.plan['expected_observations'][stage]}", EXIT_FAILED)

    def _attempt(self, stage, audit, usage):
        argv = self.launcher(stage, self.plan, self.work)
        assert_bounded(argv)
        logs = self.work / "logs"
        logs.mkdir(exist_ok=True)
        numbers = [int(m.group(1)) for p in logs.glob(f"{stage}-*.log") if (m := re.fullmatch(rf"{stage}-(\d+)\.log", p.name))]
        ids = [r["attempt"] for r in self.journal.read(self.journal.path)[0] if r["event"] == "attempt_start" and r["stage"] == stage
               and isinstance(r.get("attempt"), int)]
        attempt_no = max([usage["attempts"][stage]] + numbers + ids) + 1  # neither a failed spawn's log nor a journaled id is reused
        attempt_id = f"{stage}-{attempt_no:02d}"
        ceilings = self.plan["ceilings"]
        committed = sum(info["observations_committed"] for info in audit["roles"].values())
        remaining_shards = expected_shards(self.plan, stage) - sum(info["committed"] for info in audit["roles"].values())
        per_shard = self.plan["groups_per_shard"] * pre.STAGES[stage]["samples"]
        env = dict(self.environ)
        env.update({name: value for name, value in self.lock["environment"]["threads"].items() if value is not None})
        env["CUDA_VISIBLE_DEVICES"] = ""
        env["PYTHONPATH"] = os.pathsep.join([str(REPO / "src"), *([env["PYTHONPATH"]] if env.get("PYTHONPATH") else [])])   # the locked tree
        started = time.time()
        gate = TimingGate(self._root(stage), self.plan["timing"], started=started, committed_observations=committed,
                          first_shard_observations=per_shard, remaining_shards=remaining_shards)

        def on_start(pid):
            self.journal.append("attempt_start", stage=stage, attempt_id=attempt_id, attempt=attempt_no, argv=argv, pid=pid,
                                committed_observations=committed, remaining_shards=remaining_shards)

        def on_heartbeat(beat):
            self.journal.append("heartbeat", stage=stage, attempt_id=attempt_id, **beat)

        outcome = run_child(argv, cwd=str(REPO), env=env, log_path=logs / f"{attempt_id}.log",
                            timeout_s=ceilings["wall_hours"] * 3600 - usage["wall_s"],
                            cpu_budget_s=ceilings["core_hours"] * 3600 - usage["cpu_s"],
                            rss_limit_kib=int(ceilings["max_rss_gib"] * 2 ** 20), grace_s=ceilings["grace_s"],
                            interrupted=lambda: self.interrupt is not None, on_poll=gate, on_start=on_start,
                            on_heartbeat=on_heartbeat, heartbeat_s=self.plan["heartbeat_s"],
                            poll_s=self.poll_s, sleep=self.sleep)
        if gate.record is None and gate.active and outcome["reason"] == "exited":
            gate.record = {"outcome": "not_evaluated", "band": list(self.plan["timing"]["band_s_per_observation"]),
                           "note": "the attempt ended before the gate saw a committed shard; no throughput check was possible"}
        if gate.record is not None:
            self.journal.append("timing_gate", stage=stage, attempt_id=attempt_id, **gate.record)
        if rss_exceeded(outcome, ceilings["max_rss_gib"] * 2 ** 20) and outcome["reason"] == "exited":
            outcome["reason"] = "rss_limit"                    # the live poll can miss a short spike; wait4 cannot
        self.journal.append("attempt_end", stage=stage, attempt_id=attempt_id,
                            **{k: v for k, v in outcome.items() if k not in ("pid",)})
        return outcome

    # -- run ---------------------------------------------------------------------------------------------------
    def _recover_unterminated(self, records):
        """Close an attempt whose supervisor died; its resources are charged conservatively from the last heartbeat."""
        usage = usage_from(records)
        open_attempt = usage["open_attempt"]
        if open_attempt is None:
            return
        pid = open_attempt.get("pid")
        if isinstance(pid, int) and pid_alive(pid):
            raise SupervisorError(f"attempt {open_attempt['attempt_id']} has no end record and pid {pid} is still alive: "
                                  "refusing to start a second writer", EXIT_REFUSED)
        beat = usage["open_attempt_heartbeat"]
        slack = float(self.plan["heartbeat_s"]) + 1.0          # the child may have run this long after its last heartbeat
        threads = max([1] + [int(value) for name, value in self.lock["environment"]["threads"].items()
                             if name in THREAD_COUNT_ENV and value is not None and str(value).isdigit()])
        elapsed = (beat["elapsed_s"] if beat else 0.0) + slack
        cpu = (beat["cpu_s"] if beat else 0.0) + slack * threads
        self.journal.append("attempt_end", stage=open_attempt["stage"], attempt_id=open_attempt["attempt_id"],
                            exit_code=None, reason="supervisor_lost", elapsed_s=round(elapsed, 3), cpu_user_s=round(cpu, 3),
                            cpu_sys_s=0.0, peak_rss_kib=beat["peak_rss_polled_kib"] if beat else 0, estimated=True,
                            note="the supervisor died without recording the end; wall and CPU are an upper-bound estimate "
                                 "from the last heartbeat plus one interval, not a measurement")

    def run(self, handler_signals=True):
        """Execute the staged run; returns the result dict (exit_code, status, reasons). Never raises for expected refusals."""
        if self.plan["mode"] != "fixture" or self.plan["limit_groups"] is None:
            return {"exit_code": EXIT_REFUSED, "status": "REFUSED", "benchmark_complete": False,
                    "reasons": ["production execution is not implemented in this build (bounded fixtures only); nothing was "
                                "created or launched"]}
        old = {}
        if handler_signals:
            def handle(number, frame):
                self.interrupt = number
            for number in (signal.SIGINT, signal.SIGTERM):
                old[number] = signal.signal(number, handle)
            old[signal.SIGCHLD] = signal.signal(signal.SIGCHLD, signal.SIG_DFL)    # SIG_IGN would lose every child's status
        try:
            self._acquire()
            restart = self._init_or_verify_identity()
            never_started = restart and self._never_started()
            self._init_or_verify_lock(restart, never_started)
            records = self.journal.open()
            if restart and not never_started:
                problems = check_run_journal(records, self._identity(), self.lock)
                if problems:
                    raise SupervisorError("the journal does not belong to this run: " + "; ".join(problems[:6]), EXIT_REFUSED)
            self._journal_open = True
            self._recover_unterminated(records)
            self.journal.append("supervisor_start", restart=bool(records), plan_fingerprint=digest(self.plan),
                                lock_fingerprint=self.lock["lock_fingerprint"], mode=self.plan["mode"])
            failed = [c for c in dry_run_checks(self.plan, self.work, lock_builder=lambda: self.lock, gates=self.gates,
                                                memo=self.memo, disk_usage=self.disk_usage, probe=self.probe)
                      if c["status"] in (pre.FAIL, pre.NOT_RUN)]
            if failed:
                raise SupervisorError("host/resource checks failed or could not be run (unknown is not safe): "
                                      + "; ".join(f"{c['id']}: {c['message']}" for c in failed), EXIT_FAILED)
            self.journal.append("host_checked", ok=True)
            for stage in STAGE_ORDER:
                self._run_stage(stage)
            self._usage()                                    # verifies the whole chain: damage during the last attempt ends the run
            self.journal.append("stages_complete", plan_fingerprint=digest(self.plan))
            return {"exit_code": EXIT_OK, "status": "STAGES_COMPLETE", "reasons": [], "benchmark_complete": False}
        except (SupervisorError, OSError, KeyError, TypeError, AttributeError) as error:   # unexpected: a failed run, never a traceback
            code = error.code if isinstance(error, SupervisorError) else EXIT_FAILED
            message = str(error) if isinstance(error, SupervisorError) else f"{type(error).__name__}: {error}"
            event = "interrupted" if code == EXIT_INTERRUPTED else "run_failed"
            if self._journal_open:                          # a refusal before the journal was verified writes nothing
                try:
                    self.journal.append(event, reason=message, exit_code=code)
                except (OSError, SupervisorError):          # a damaged journal is never appended to, not even to say so
                    pass
            return {"exit_code": code, "status": "INTERRUPTED" if code == EXIT_INTERRUPTED else "FAILED",
                    "reasons": [message], "benchmark_complete": False}
        finally:
            for number, handler in old.items():
                signal.signal(number, handler)
            if self._flock is not None:
                self._flock.close()


# ---- read-only verification, completion ------------------------------------------------------------------------

def load_run(workdir):
    path = Path(workdir) / "run.json"
    if not path.exists():
        raise SupervisorError("no run.json: not a supervisor workdir", EXIT_REFUSED)
    run = pre._read_json(path)
    if run.get("schema") != RUN_SCHEMA or run.get("plan_fingerprint") != digest(run.get("plan")):
        raise SupervisorError("run.json is not a B2-production-run/1 record or fails its fingerprint", EXIT_REFUSED)
    return run


def verify_workdir(workdir, *, depth="checksum", max_full=2, require_clean=None):
    """Read-only: journal chain and anchor, journal/run/lock identity, lock, and every stage audit. Returns checks."""
    work = Path(workdir)
    run = load_run(work)
    plan = run["plan"]
    checks = []
    lock = pre._read_json(work / "lock.json")
    records, problems = Journal.load(work / "journal.jsonl")
    if not problems:
        problems = check_run_journal(records, run, lock)
    checks.append(pre.check("workdir.journal", "Journal chain, anchor and run identity are intact", pre.FAIL if problems else pre.PASS,
                            "; ".join(problems) or f"{len(records)} records, head {records[-1]['sha256'][:12] if records else 'none'}"))
    lock_problems = pre.verify_lock(lock, require_clean=plan["mode"] != "fixture" if require_clean is None else require_clean)
    checks.append(pre.check("workdir.lock", "Source/config/environment equal the lock", pre.FAIL if lock_problems else pre.PASS,
                            "; ".join(lock_problems[:6]) or "identical", problems=lock_problems))
    current_tools = tools_sha256()
    checks.append(pre.check("workdir.tools", "Supervisor and preflight code equal the run's", pre.PASS if run.get("tools_sha256") == current_tools else pre.FAIL,
                            "identical" if run.get("tools_sha256") == current_tools else "the supervisor or preflight script changed since the run started"))
    marker_path = work / "completion.json"
    if marker_path.exists():
        marker = pre._read_json(marker_path)
        sound = (marker.get("plan_fingerprint") == run["plan_fingerprint"] and marker.get("lock_fingerprint") == lock["lock_fingerprint"]
                 and marker.get("journal_head") in {r["sha256"] for r in records})
        checks.append(pre.check("workdir.completion", "completion.json belongs to this run and to this journal", pre.PASS if sound else pre.FAIL,
                                "plan, lock and journal head are consistent (a head older than the newest record is expected after a later run)"
                                if sound else "completion.json names another plan, lock or journal head"))
    usage = usage_from(records)
    for stage in STAGE_ORDER:
        known = work / plan["roots"]["known"] if stage != "known" else None
        audit = pre.audit_artifact(work / plan["roots"][stage], stage, depth=depth, lock=lock, known=known, max_full=max_full,
                                   production=plan["mode"] == "production")
        item = pre.audit_check(audit)
        found = {role: info["observations_committed"] for role, info in audit["roles"].items()}
        mismatches = plan_root_problems(plan, audit)
        if audit["state"] == "RESUMABLE":                      # e.g. every shard committed but the manifest is missing
            item = pre.check(item["id"], item["title"], pre.NOT_RUN,
                             f"stage is not COMPLETE ({item['message']}): the generator still has work to do", **audit)
        if mismatches:
            item = pre.check(item["id"], item["title"], pre.FAIL, "root was not produced under this plan: " + "; ".join(mismatches),
                             **audit)
        elif audit["state"] == "COMPLETE" and found != plan["expected_observations"][stage]:
            item = pre.check(item["id"], item["title"], pre.FAIL, f"inventory {found} differs from the plan "
                             f"{plan['expected_observations'][stage]}", **audit)
        elif audit["state"] == "COMPLETE" and item["status"] == pre.PASS:
            acceptable, why = last_attempt_acceptable(usage, stage)
            if not acceptable:
                item = pre.check(item["id"], item["title"], pre.FAIL, "root verifies COMPLETE but " + why, **audit)
        checks.append(item)
    return run, lock, records, checks


def complete_workdir(workdir, *, gates=None, memo=None):
    """Write completion.json only if the journal, lock and all three stages verify COMPLETE with the exact planned inventory."""
    work = Path(workdir)
    run, lock, records, checks = verify_workdir(work, depth="full", max_full=2)
    if (work / "completion.json").exists():
        raise SupervisorError("completion.json already exists; refusing to overwrite evidence", EXIT_REFUSED)
    bad = [c for c in checks if c["status"] != pre.PASS]
    if bad:
        raise SupervisorError("not complete: " + "; ".join(f"{c['id']} {c['status']}: {c['message']}" for c in bad), EXIT_FAILED)
    events = [r["event"] for r in records]
    if "stages_complete" not in events:
        raise SupervisorError("the journal has no stages_complete record", EXIT_FAILED)
    gates = gates if gates is not None else pre._read_json(REPO / pre.GATES_PATH)
    memo = memo if memo is not None else pre._read_json(REPO / pre.MEMO_PATH)
    authorized, _ = authorization(gates, memo)
    plan = run["plan"]
    marker = {"schema": COMPLETION_SCHEMA, "generation_complete": True, "scope": plan["mode"],
              "production_complete": False,
              "benchmark_complete": False, "production_authorized": authorized and plan["mode"] == "production",
              "plan_fingerprint": run["plan_fingerprint"], "lock_fingerprint": lock["lock_fingerprint"],
              "child_launcher": plan["launcher"], "tools_sha256": run["tools_sha256"],
              "journal_head": records[-1]["sha256"], "observations": plan["expected_observations"],
              "stage_manifest_fingerprints": {s: pre._fingerprint(pre._read_json(work / plan["roots"][s] / "manifest.json"))
                                              for s in STAGE_ORDER},
              "note": "data generation of the planned scope is complete and verified; this is not benchmark completion"
                      + ("" if plan["launcher"] == "generators" else
                         "; the children were started through a diagnostic wrapper, so the shards may not come from the real "
                         "physics chain")}
    pre._write_new(work / "completion.json", json.dumps(marker, indent=1, allow_nan=False) + "\n")
    return marker


# ---- command line ------------------------------------------------------------------------------------------------

def launcher_name(wrapper):
    """Run-identity string for the launcher: the real generators, or a hashed diagnostic wrapper under ``tests/``.

    The wrapper is a fixture diagnostic (the test stand-in); only ``tests/b2_supervisor_standin.py`` may be started in place of
    the generator CLIs, so the supervisor cannot be pointed at an arbitrary program.
    """
    if not wrapper:
        return "generators"
    path = Path(wrapper).resolve()
    if path != (REPO / "tests" / "b2_supervisor_standin.py").resolve():
        raise SupervisorError("--child-wrapper accepts only this repository's tests/b2_supervisor_standin.py (fixture diagnostic)",
                              EXIT_REFUSED)
    return f"child-wrapper:{path.name}:{pre._file_hash(path)[:16]}"


def _plan_from_args(args):
    ceilings = pre._read_json(args.ceilings) if getattr(args, "ceilings", None) else None
    timing = {}
    if getattr(args, "timing_band", None):
        timing["band_s_per_observation"] = list(args.timing_band)
    for name in ("timing_startup_s", "timing_tolerance"):
        if getattr(args, name, None) is not None:
            timing[name.replace("timing_", "")] = getattr(args, name)
    if getattr(args, "no_timing_gate", False):
        timing["enabled"] = False
    mode = "production" if args.production else "fixture"
    return build_plan(args.workdir, mode=mode, max_groups=args.max_groups,
                      groups_per_shard=args.groups_per_shard if args.groups_per_shard is not None
                      else (pre.PRODUCTION["groups_per_shard"] if args.production else 1),
                      ceilings=ceilings, timing=timing, launcher=launcher_name(getattr(args, "child_wrapper", None)),
                      heartbeat_s=getattr(args, "heartbeat_s", None))


def _print(value):
    sys.stdout.write(json.dumps(value, indent=1, allow_nan=False) + "\n")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("plan", "run"):
        sp = sub.add_parser(name)
        sp.add_argument("--workdir", required=True)
        sp.add_argument("--max-groups", type=int, help=f"bounded fixture: 1..{FIXTURE_MAX_GROUPS} groups per role")
        sp.add_argument("--production", action="store_true", help="validate the full plan; it can never be launched in this build")
        sp.add_argument("--groups-per-shard", type=int)
        sp.add_argument("--ceilings", help="JSON file overriding the default ceilings")
        sp.add_argument("--timing-band", nargs=2, type=float, metavar=("LOW", "HIGH"))
        sp.add_argument("--timing-startup-s", type=float)
        sp.add_argument("--timing-tolerance", type=float)
        sp.add_argument("--no-timing-gate", action="store_true", help="fixture diagnostics only; refused for --production")
        sp.add_argument("--heartbeat-s", type=float, help="seconds between heartbeat records of a running child")
        sp.add_argument("--child-wrapper", help="diagnostic wrapper script receiving '<stage> <generator args>' (fixtures only)")
    sub.choices["run"].add_argument("--execute", action="store_true", help="actually spawn children (default is a dry run)")
    sub.choices["run"].add_argument("--allow-dirty-fixture", action="store_true")
    for name in ("status", "verify", "complete"):
        sub.add_parser(name).add_argument("--workdir", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command in ("status", "verify"):
            run, lock, records, checks = verify_workdir(args.workdir)
            usage = usage_from(records)
            result = pre.report(checks, command=args.command, plan=run["plan"], usage=usage, journal_events=len(records),
                                last_event=records[-1]["event"] if records else None)
            result["all_stages_verified"] = all(c["status"] == pre.PASS for c in checks)
            _print(result)
            statuses = {c["status"] for c in checks}
            return (EXIT_FAILED if pre.FAIL in statuses else EXIT_BLOCKED if pre.BLOCKED in statuses
                    else 5 if statuses - {pre.PASS} else EXIT_OK)
        if args.command == "complete":
            _print(complete_workdir(args.workdir))
            return EXIT_OK
        if args.production and (args.child_wrapper or args.no_timing_gate):
            raise SupervisorError("--child-wrapper and --no-timing-gate are fixture diagnostics only", EXIT_REFUSED)
        plan = _plan_from_args(args)
        if args.command == "plan" or not args.execute:
            checks = dry_run_checks(plan, args.workdir)
            commands = None
            if plan["mode"] == "fixture":
                launcher = wrapper_launcher(args.child_wrapper) if args.child_wrapper else default_launcher
                commands = {stage: launcher(stage, plan, Path(args.workdir)) for stage in STAGE_ORDER}
            result = pre.report(checks, command="plan", dry_run=True, plan=plan, commands=commands)
            _print(result)
            return pre._exit_code(result)
        if plan["mode"] == "production":
            authorized, reasons = authorization(pre._read_json(REPO / pre.GATES_PATH), pre._read_json(REPO / pre.MEMO_PATH))
            raise SupervisorError("production execution refused: " + ("; ".join(reasons) if reasons else
                                  "all gates are approved but the production launch is not implemented in this build"),
                                  EXIT_REFUSED)
        launcher = wrapper_launcher(args.child_wrapper) if args.child_wrapper else default_launcher
        supervisor = Supervisor(args.workdir, plan, launcher=launcher, allow_dirty=args.allow_dirty_fixture)
        result = supervisor.run()
        _print(result)
        return result["exit_code"]
    except SupervisorError as error:
        _print({"status": "REFUSED" if error.code == EXIT_REFUSED else "FAILED", "reasons": [str(error)], "benchmark_complete": False,
                "exit_code": error.code})
        return error.code
    except (KeyError, TypeError, AttributeError) as error:           # a malformed run.json / lock.json / completion.json
        _print({"status": "REFUSED", "reasons": [f"malformed workdir state ({type(error).__name__}: {error})"], "benchmark_complete": False,
                "exit_code": EXIT_REFUSED})
        return EXIT_REFUSED
    except (ValueError, OSError) as error:
        _print({"status": "FAILED", "reasons": [str(error)], "benchmark_complete": False, "exit_code": EXIT_FAILED})
        return EXIT_FAILED


if __name__ == "__main__":
    sys.exit(main())

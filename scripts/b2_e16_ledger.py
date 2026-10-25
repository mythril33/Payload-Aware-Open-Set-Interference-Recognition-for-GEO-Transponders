"""E16 external run ledger, incident specification and stop-condition evaluation. Pure data; nothing here runs work.

* ``verify_chain`` / ``Ledger``: a hash-chained JSONL journal meant to live *outside* the working tree and on a
  different filesystem. The chain detects edits, reordering and (with an independently retained head) truncation. It
  cannot enforce append-only semantics: that needs an immutable-attribute or remote sink chosen by the operator.
* ``INCIDENTS``: which events stop a run, which preserve evidence, and which fields every journal entry must carry.
* ``evaluate_stop_conditions``: a pure function over *injected* observations (clock, resource readings). It never
  reads the host. "No stop condition triggered" is not permission to continue; it is the absence of one reason to stop.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import stat
import sys
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parent))
import b2_e14_storage as S
import b2_e16_durability as D
import b2_production_preflight as pre
import b2_production_supervisor as sup

SCHEMA_ENTRY = "B2-E16-ledger-entry/1"
SCHEMA_REPORT = "B2-E16-ledger-report/1"
SCHEMA_STOP = "B2-E16-stop-evaluation/1"
SCHEMA_OBSERVATION = "B2-E16-resource-observation/1"
LEDGER_NAME = "ledger.jsonl"
GENESIS = "0" * 64
MAX_LEDGER_BYTES = 16 * 2 ** 20
MAX_ENTRY_BYTES = 64 * 1024
MAX_ENTRIES = 100_000
STAGES = ("known", "test", "matched")
KINDS = ("run_opened", "authorization_snapshot", "stage_bound", "shard_admitted", "stage_completed", "backup_verified",
         "boundary_check", "incident", "stop", "resume", "k17d_check")
ENTRY_KEYS = ("schema", "seq", "prev_sha256", "at", "kind", "stage", "data", "entry_sha256")
CORE_TO_WALL = pre.BUDGET["cpu_to_wall_ratio"]
BYTES_PER_OBSERVATION = sup.ARTIFACT_BYTES_PER_OBSERVATION
MAX_TOTAL_ATTEMPTS = sup.MAX_TOTAL_ATTEMPTS_PER_STAGE
NO_AUTHORITY = {"authorizes_nothing": True, "execution_permitted": False}

# kind -> (mandatory action, required data fields). ``stop_and_quarantine`` never deletes or repairs evidence.
INCIDENTS = {
    "shard_corruption": ("stop_and_quarantine", ("role", "ordinal", "expected_sha256", "observed_sha256")),
    "orphan_files": ("stop_and_quarantine", ("role", "files")),
    "partial_commit": ("stop_and_quarantine", ("role", "ordinal")),
    "identity_mismatch": ("stop", ("what", "expected_sha256", "observed_sha256")),
    "backup_mismatch": ("stop_and_quarantine", ("role", "manifest_sha256")),
    "backup_unavailable": ("stop", ("reason",)),
    "ceiling_breach": ("stop", ("ceiling", "limit", "observed")),
    "projection_breach": ("stop", ("projection", "limit", "projected")),
    "timing_gate_failure": ("stop", ("s_per_observation", "band")),
    "authorization_expired": ("stop", ("expires_at",)),
    "authorization_revoked": ("stop", ("revocation_id",)),
    "stage_order_violation": ("stop", ("stage", "required_predecessor")),
    "k17d_mismatch": ("fail_closed_and_rederive_with_independent_review", ("expected_sha256", "observed_sha256")),
    "resource_observation_missing": ("stop", ("field",)),
    "journal_integrity_failure": ("stop", ("reason",)),
    "interruption": ("resume_only_under_identical_request", ("attempt", "signal")),
}


class LedgerRefused(ValueError):
    pass


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def instant(value):
    if not isinstance(value, str) or len(value) > 40:
        raise LedgerRefused("timestamp must be an ISO-8601 string with a timezone")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise LedgerRefused("invalid timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise LedgerRefused("timestamp must include a timezone")
    return parsed.astimezone(timezone.utc)


def _finite(value, *, minimum=0.0, name="value"):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < minimum:
        raise LedgerRefused(f"{name} must be a finite number >= {minimum}")
    return float(value)


def _count(value, name):
    if type(value) is not int or not 0 <= value <= 2 ** 40:
        raise LedgerRefused(f"{name} must be a bounded non-negative integer")
    return value


# ---- incident specification -------------------------------------------------------------------------------------

def required_action(kind):
    if kind not in INCIDENTS:
        raise LedgerRefused("unknown incident kind: stop")
    return INCIDENTS[kind][0]


def incident_data(kind, details):
    """Validate an incident record's fields; the mandatory action is derived, never supplied."""
    action, fields = INCIDENTS[kind] if kind in INCIDENTS else (None, None)
    if action is None:
        raise LedgerRefused("unknown incident kind: stop")
    if not isinstance(details, dict) or set(details) != set(fields):
        raise LedgerRefused(f"incident {kind} requires exactly {sorted(fields)}")
    data = {"incident": kind, "action": action, "details": details}
    if len(canonical(data)) > MAX_ENTRY_BYTES:
        raise LedgerRefused("incident record too large")
    return data


# ---- hash chain -------------------------------------------------------------------------------------------------

def make_entry(seq, prev_sha256, at, kind, stage, data):
    if kind not in KINDS:
        raise LedgerRefused("unknown ledger entry kind")
    if stage is not None and stage not in STAGES:
        raise LedgerRefused("unknown stage")
    if not isinstance(data, dict):
        raise LedgerRefused("entry data must be an object")
    instant(at)
    entry = {"schema": SCHEMA_ENTRY, "seq": seq, "prev_sha256": prev_sha256, "at": at, "kind": kind, "stage": stage, "data": data}
    entry["entry_sha256"] = _digest(entry)
    if len(canonical(entry)) > MAX_ENTRY_BYTES:
        raise LedgerRefused("ledger entry too large")
    return entry


def verify_chain(raw, *, expected_head=None):
    """Verify a whole ledger. ``expected_head`` is an independently retained {"seq", "entry_sha256"} anchor."""
    failures = []
    entries = []
    if not isinstance(raw, (bytes, bytearray)) or len(raw) > MAX_LEDGER_BYTES:
        return _report(False, 0, None, ["ledger is not bytes or exceeds the byte bound"])
    if raw and not raw.endswith(b"\n"):
        failures.append("last line is not newline-terminated (torn write)")
    lines = bytes(raw).split(b"\n")
    if lines and lines[-1] == b"":
        lines.pop()
    if len(lines) > MAX_ENTRIES:
        return _report(False, 0, None, ["too many entries"])
    previous, last_at = GENESIS, None
    for index, line in enumerate(lines):
        try:
            if not line or len(line) > MAX_ENTRY_BYTES:
                raise LedgerRefused("empty or oversized line")
            entry = S._strict(line)
            if not isinstance(entry, dict) or tuple(sorted(entry)) != tuple(sorted(ENTRY_KEYS)) or entry["schema"] != SCHEMA_ENTRY:
                raise LedgerRefused("entry fields differ from the ledger contract")
            body = {k: v for k, v in entry.items() if k != "entry_sha256"}
            if entry["seq"] != index or type(entry["seq"]) is not int:
                raise LedgerRefused("sequence gap, repeat or reorder")
            if entry["prev_sha256"] != previous:
                raise LedgerRefused("hash chain broken")
            if entry["entry_sha256"] != _digest(body):
                raise LedgerRefused("entry content differs from its checksum")
            if entry["kind"] not in KINDS or (entry["stage"] is not None and entry["stage"] not in STAGES) or not isinstance(entry["data"], dict):
                raise LedgerRefused("unknown kind, stage or data type")
            moment = instant(entry["at"])
            if last_at is not None and moment < last_at:
                raise LedgerRefused("timestamps run backwards")
            last_at, previous = moment, entry["entry_sha256"]
            entries.append(entry)
        except (LedgerRefused, S.StorageRefused) as error:
            failures.append(f"entry {index}: {error}")
            break
    head = {"seq": entries[-1]["seq"], "entry_sha256": entries[-1]["entry_sha256"]} if entries else None
    if expected_head is not None:
        if (not isinstance(expected_head, dict) or set(expected_head) != {"seq", "entry_sha256"}
                or type(expected_head["seq"]) is not int or expected_head["seq"] < 0):
            failures.append("anchor is malformed")
        elif expected_head["seq"] >= len(entries):
            failures.append("ledger is shorter than the independently retained anchor (truncation)")
        elif entries[expected_head["seq"]]["entry_sha256"] != expected_head["entry_sha256"]:
            failures.append("ledger does not contain the independently retained anchor (rewritten history)")
    return _report(not failures, len(entries), head, failures, entries)


def _report(ok, count, head, failures, entries=None):
    return {"schema": SCHEMA_REPORT, "ok": ok, "count": count, "head": head, "failures": failures,
            "append_only_enforced": False,
            "limitation": "a hash chain detects edits; only an operator-chosen immutable sink prevents them",
            "entries": entries if ok and entries is not None else [], **NO_AUTHORITY}


def check_independent_location(ledger_directory, working_root, backup_root):
    """The journal must outlive the working tree: separate filesystem from the work, no nesting with either root."""
    where = {name: D.directory_identity(path) for name, path in
             (("ledger", ledger_directory), ("working", working_root), ("backup", backup_root))}
    paths = {name: Path(info["path"]) for name, info in where.items()}
    failures = []
    for other in ("working", "backup"):
        if paths["ledger"] == paths[other] or paths[other] in paths["ledger"].parents or paths["ledger"] in paths[other].parents:
            failures.append(f"ledger directory is the same as, or nested with, the {other} root")
    if where["ledger"]["st_dev"] == where["working"]["st_dev"]:
        failures.append("ledger shares a filesystem with the working tree")
    return {"ok": not failures, "failures": failures,
            "shares_device_with_backup": where["ledger"]["st_dev"] == where["backup"]["st_dev"],
            "physical_independence_proven": False, **NO_AUTHORITY}


class Ledger:
    """Appends to ``<directory>/ledger.jsonl`` under an exclusive lock after verifying the whole existing chain."""

    def __init__(self, directory):
        self.directory = directory

    def _open(self, *, create):
        fds = D._chain(self.directory)
        try:
            flags = os.O_RDWR | os.O_APPEND | os.O_NOFOLLOW | (os.O_CREAT if create else 0)
            fd = os.open(LEDGER_NAME, flags, 0o600, dir_fd=fds[-1])
        except BaseException:
            D._close(fds)
            raise
        return fds, fd

    def read(self):
        """Raw bytes of an existing ledger; never creates one."""
        fds, fd = self._open(create=False)
        try:
            return self._contents(fd)
        finally:
            os.close(fd)
            D._close(fds)

    @staticmethod
    def _contents(fd):
        status = os.fstat(fd)
        if not stat.S_ISREG(status.st_mode) or status.st_nlink != 1 or status.st_size > MAX_LEDGER_BYTES:
            raise LedgerRefused("ledger must be a bounded, regular, unaliased file")
        os.lseek(fd, 0, os.SEEK_SET)
        chunks, total = [], 0
        while True:
            block = os.read(fd, 1 << 20)
            if not block:
                break
            total += len(block)
            if total > MAX_LEDGER_BYTES:
                raise LedgerRefused("ledger exceeds its byte bound")
            chunks.append(block)
        return b"".join(chunks)

    def append(self, kind, stage, data, at, *, expected_head=None):
        fds, fd = self._open(create=True)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            report = verify_chain(self._contents(fd), expected_head=expected_head)
            if not report["ok"]:
                raise LedgerRefused("existing ledger fails verification: " + "; ".join(report["failures"]))
            head = report["head"]
            entry = make_entry(0 if head is None else head["seq"] + 1, GENESIS if head is None else head["entry_sha256"], at, kind, stage, data)
            if report["entries"] and instant(at) < instant(report["entries"][-1]["at"]):
                raise LedgerRefused("timestamps run backwards")
            line = (canonical(entry) + "\n").encode()
            if os.write(fd, line) != len(line):
                raise LedgerRefused("short ledger write")
            os.fsync(fd)
            os.fsync(fds[-1])
            return entry
        finally:
            os.close(fd)
            D._close(fds)


# ---- resource observation and stop conditions ------------------------------------------------------------------

OBSERVATION_KEYS = ("schema", "collected_at", "elapsed_wall_s", "cpu_core_s", "peak_rss_gib", "working_free_gib", "backup_free_gb",
                    "failed_attempts", "interruptions", "total_attempts", "observations_committed", "observations_remaining",
                    "admitted_shards_this_attempt", "first_shard")
FIRST_SHARD_KEYS = ("s_per_observation", "observations")
CEILING_REQUIRED = ("wall_hours", "core_hours", "max_failed_attempts_per_stage", "max_interruptions_per_stage", "max_rss_gib",
                    "min_free_disk_gib", "backup_disk_gb")
AUTH_REQUIRED = ("expires_at", "revoked", "revocation_id")


def _checked_observation(observation):
    if not isinstance(observation, dict) or tuple(sorted(observation)) != tuple(sorted(OBSERVATION_KEYS)) or observation["schema"] != SCHEMA_OBSERVATION:
        raise LedgerRefused("resource observation fields differ from the contract")
    seen = {"collected_at": instant(observation["collected_at"])}
    for name in ("elapsed_wall_s", "cpu_core_s", "peak_rss_gib", "working_free_gib", "backup_free_gb"):
        seen[name] = _finite(observation[name], name=name)
    for name in ("failed_attempts", "interruptions", "total_attempts", "observations_committed", "observations_remaining", "admitted_shards_this_attempt"):
        seen[name] = _count(observation[name], name)
    first = observation["first_shard"]
    if first is not None:
        if not isinstance(first, dict) or set(first) != set(FIRST_SHARD_KEYS):
            raise LedgerRefused("first_shard fields differ from the contract")
        seen["first_s_per_observation"] = _finite(first["s_per_observation"], minimum=0.0, name="first_shard.s_per_observation")
        seen["first_observations"] = _count(first["observations"], "first_shard.observations")
        if seen["first_observations"] < 1:
            raise LedgerRefused("first_shard.observations must be positive")
    return seen


def _checked_ceilings(ceilings):
    if not isinstance(ceilings, dict) or not set(CEILING_REQUIRED) <= set(ceilings):
        raise LedgerRefused("ceilings are incomplete")
    out = {}
    for name in CEILING_REQUIRED:
        out[name] = _count(ceilings[name], name) if name.startswith("max_failed") or name.startswith("max_interruptions") else _finite(ceilings[name], minimum=1e-9, name=name)
    return out


def _checked_timing(timing):
    band = timing.get("band_s_per_observation") if isinstance(timing, dict) else None
    if (not isinstance(band, list) or len(band) != 2 or not all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in band)
            or not 0 < band[0] <= band[1] or not isinstance(timing.get("tolerance"), (int, float)) or isinstance(timing["tolerance"], bool)
            or not math.isfinite(timing["tolerance"]) or not 0 <= timing["tolerance"] <= 2
            or type(timing.get("gate_shards")) is not int or not 1 <= timing["gate_shards"] <= 100):
        raise LedgerRefused("timing policy is malformed")
    return float(band[0]), float(band[1]), 1 + float(timing["tolerance"]), timing["gate_shards"]


def _checked_authorization(authorization):
    if not isinstance(authorization, dict) or set(authorization) != set(AUTH_REQUIRED) or type(authorization["revoked"]) is not bool:
        raise LedgerRefused("authorization state fields differ from the contract")
    return instant(authorization["expires_at"]), authorization["revoked"]


def evaluate_stop_conditions(observation, ceilings, authorization, *, now, stage, restarting=False,
                             timing=None, max_observation_age_s=300):
    """Return every reason to stop. Malformed, missing, stale or contradictory input is itself a reason to stop."""
    timing = sup.DEFAULT_TIMING if timing is None else timing
    reasons, projections = [], {}
    try:
        moment = instant(now)
        if stage not in STAGES:
            raise LedgerRefused("unknown stage")
        if type(max_observation_age_s) is not int or not 1 <= max_observation_age_s <= 3600:
            raise LedgerRefused("observation freshness bound must be 1..3600 seconds")
        seen = _checked_observation(observation)
        limits = _checked_ceilings(ceilings)
        expires, revoked = _checked_authorization(authorization)
        low, high, slack, gate_shards = _checked_timing(timing)
    except (LedgerRefused, TypeError, KeyError) as error:
        return _stop_result(["input.malformed: " + str(error)], projections, stage, now)
    age = (moment - seen["collected_at"]).total_seconds()
    if not 0 <= age <= max_observation_age_s:
        reasons.append("observation.stale_or_from_the_future")
    if moment >= expires:
        reasons.append("authorization.expired")
    if revoked:
        reasons.append("authorization.revoked")
    wall_limit_s, core_limit_s = limits["wall_hours"] * 3600, limits["core_hours"] * 3600
    if seen["elapsed_wall_s"] >= wall_limit_s:
        reasons.append("ceiling.wall_hours")
    if seen["cpu_core_s"] >= core_limit_s:
        reasons.append("ceiling.core_hours")
    if seen["peak_rss_gib"] > limits["max_rss_gib"]:
        reasons.append("ceiling.max_rss_gib")
    if seen["failed_attempts"] > limits["max_failed_attempts_per_stage"]:
        reasons.append("ceiling.failed_attempts")
    if seen["interruptions"] > limits["max_interruptions_per_stage"]:
        reasons.append("ceiling.interruptions")
    if seen["total_attempts"] > MAX_TOTAL_ATTEMPTS:
        reasons.append("ceiling.total_attempts")
    if restarting and (seen["failed_attempts"] >= limits["max_failed_attempts_per_stage"]
                       or seen["interruptions"] >= limits["max_interruptions_per_stage"] or seen["total_attempts"] >= MAX_TOTAL_ATTEMPTS):
        reasons.append("restart.allowance_exhausted")
    if seen["admitted_shards_this_attempt"] >= gate_shards and "first_s_per_observation" not in seen:
        reasons.append("timing.gate_measurement_missing")
    rate = seen.get("first_s_per_observation", high)       # conservative until the first shard is measured
    if "first_s_per_observation" in seen and rate > high * slack:
        reasons.append("timing.too_slow")
    remaining = seen["observations_remaining"]
    projected_wall_s = seen["elapsed_wall_s"] + remaining * rate
    projected_core_s = seen["cpu_core_s"] + remaining * rate * CORE_TO_WALL
    projected_bytes = remaining * BYTES_PER_OBSERVATION
    projections.update(projected_wall_hours=projected_wall_s / 3600, projected_core_hours=projected_core_s / 3600,
                       projected_artifact_gib=projected_bytes / 2 ** 30, seconds_per_observation_used=rate,
                       rate_is_measured="first_s_per_observation" in seen)
    if projected_wall_s > wall_limit_s:
        reasons.append("projection.wall_hours")
    if projected_core_s > core_limit_s:
        reasons.append("projection.core_hours")
    if seen["working_free_gib"] - projected_bytes / 2 ** 30 < limits["min_free_disk_gib"]:
        reasons.append("projection.working_disk")
    if seen["backup_free_gb"] * 1e9 < projected_bytes or seen["backup_free_gb"] < 0:
        reasons.append("projection.backup_space")
    return _stop_result(reasons, projections, stage, now, restart={
        "failed_attempts_left": max(0, limits["max_failed_attempts_per_stage"] - seen["failed_attempts"]),
        "interruptions_left": max(0, limits["max_interruptions_per_stage"] - seen["interruptions"]),
        "total_attempts_left": max(0, MAX_TOTAL_ATTEMPTS - seen["total_attempts"])})


def _echo_instant(now):
    try:
        instant(now)
    except LedgerRefused:
        return None
    return now


def _stop_result(reasons, projections, stage, now, restart=None):
    return {"schema": SCHEMA_STOP, "decision": "STOP" if reasons else "NO_STOP_CONDITION_TRIGGERED", "reasons": reasons,
            "projections": projections, "restart_allowance": restart, "stage": stage if stage in STAGES else None,
            "evaluated_at": _echo_instant(now),
            "absence_of_a_stop_reason_is_not_permission": True, **NO_AUTHORITY}

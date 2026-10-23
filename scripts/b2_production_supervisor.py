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
 * restart only under the identical plan, lock, ceilings and an intact hash-chained journal (``journal.jsonl``);
 * exit codes, elapsed/CPU time and peak RSS of every child from ``wait4``, journaled per attempt;
 * wall/CPU/RSS/attempt/disk ceilings enforced live and after the fact; first-shard throughput gate;
 * SIGINT/SIGTERM stop the child group cleanly and leave a resumable root; the child dies with the supervisor;
 * orphaned shard files are moved to ``quarantine/`` with hashes, never deleted; INVALID roots are never touched;
 * a completion marker is written only when all three stages audit COMPLETE with the exact planned inventory.
Nothing here approves a researcher gate; ``benchmark_complete`` is always false.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import math
import os
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
CEILING_KEYS = ("wall_hours", "core_hours", "max_attempts_per_stage", "max_rss_gib", "min_free_disk_gib", "grace_s")
FIXTURE_CEILINGS = {"wall_hours": 1.0, "core_hours": 2.0, "max_attempts_per_stage": 2, "max_rss_gib": 4.0,
                    "min_free_disk_gib": 1.0, "grace_s": 10.0}
PRODUCTION_CEILINGS = {"wall_hours": float(pre.PROPOSED_CEILINGS["generation_wall_hours"]),
                       "core_hours": float(pre.PROPOSED_CEILINGS["generation_core_hours"]), "max_attempts_per_stage": 2,
                       "max_rss_gib": float(pre.PROPOSED_CEILINGS["generator_ram_gib_per_process"]),
                       "min_free_disk_gib": float(pre.PROPOSED_CEILINGS["working_disk_gib"]), "grace_s": 60.0}
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


# ---- hash-chained journal ----------------------------------------------------------------------------------

class Journal:
    """Append-only JSON-lines journal; every record carries its sequence number, the previous record's SHA-256 and its own.

    The chain detects accidental modification, truncation and reordering. It is not authentication.
    """

    def __init__(self, path):
        self.path = Path(path)
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

    def open(self):
        records, problems = self.read(self.path)
        if problems:
            raise SupervisorError("journal is damaged: " + "; ".join(problems) + " - inspect it, move it aside and decide; "
                                  "the supervisor will not repair evidence", EXIT_REFUSED)
        self.seq = len(records)
        self.head = records[-1]["sha256"] if records else None
        return records

    def append(self, event, **fields):
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
        return record


def _fsync_directory(path):
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def usage_from(records):
    """Cumulative wall/CPU seconds and attempts per stage from the journal; an unterminated attempt counts as started."""
    usage = {"wall_s": 0.0, "cpu_s": 0.0, "attempts": {stage: 0 for stage in STAGE_ORDER}, "open_attempt": None}
    open_attempts = {}
    for record in records:
        if record["event"] == "attempt_start":
            usage["attempts"][record["stage"]] += 1
            open_attempts[record["attempt_id"]] = record
        elif record["event"] == "attempt_end":
            open_attempts.pop(record["attempt_id"], None)
            usage["wall_s"] += record["elapsed_s"]
            usage["cpu_s"] += record["cpu_user_s"] + record["cpu_sys_s"]
    if open_attempts:
        usage["open_attempt"] = list(open_attempts.values())[-1]
    return usage


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


def merge_ceilings(base, override):
    if override is None:
        return dict(base)
    if not isinstance(override, dict) or set(override) - set(CEILING_KEYS):
        raise SupervisorError(f"ceilings must be an object with keys from {CEILING_KEYS}", EXIT_REFUSED)
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise SupervisorError(f"ceiling {key} must be a finite positive number", EXIT_REFUSED)
        merged[key] = value
    merged["max_attempts_per_stage"] = int(merged["max_attempts_per_stage"])
    return merged


def expected_shards(plan, stage):
    """Shards the plan expects for a stage, independent of how much of the root exists yet."""
    samples = pre.STAGES[stage]["samples"]
    return sum(-(-(observations // samples) // plan["groups_per_shard"])
               for observations in plan["expected_observations"][stage].values())


def build_plan(workdir, *, mode, max_groups=None, groups_per_shard=1, ceilings=None, timing=None):
    """Validate and freeze the request. Capped fixtures need 1..2 groups; production has no limit but cannot be launched."""
    if mode not in ("fixture", "production"):
        raise SupervisorError("mode must be fixture or production", EXIT_REFUSED)
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
        if groups_per_shard != pre.PRODUCTION["groups_per_shard"]:
            raise SupervisorError("the production plan uses four groups per shard", EXIT_REFUSED)
        limit = None
        base_ceilings = PRODUCTION_CEILINGS
    merged_timing = dict(DEFAULT_TIMING)
    for key, value in (timing or {}).items():
        if key not in DEFAULT_TIMING:
            raise SupervisorError(f"unknown timing option {key!r}", EXIT_REFUSED)
        merged_timing[key] = value
    low, high = merged_timing["band_s_per_observation"]
    if not (isinstance(low, (int, float)) and isinstance(high, (int, float)) and 0 <= low < high and math.isfinite(high)):
        raise SupervisorError("timing band must be two finite numbers 0 <= low < high", EXIT_REFUSED)
    inventory = expected_inventory(mode, limit)
    return {"schema": PLAN_SCHEMA, "mode": mode, "limit_groups": limit, "groups_per_shard": groups_per_shard,
            "roots": {stage: stage for stage in STAGE_ORDER}, "stage_order": list(STAGE_ORDER),
            "expected_observations": inventory,
            "total_observations": sum(sum(roles.values()) for roles in inventory.values()),
            "ceilings": merge_ceilings(base_ceilings, ceilings), "timing": merged_timing,
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
        ctypes.CDLL(None, use_errno=True).prctl(1, signal.SIGTERM)
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


def proc_vmrss_kib(pid):
    try:
        for line in Path(f"/proc/{pid}/status").read_text().splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1])
    except (OSError, ValueError, IndexError):
        pass
    return None


def proc_cpu_s(pid):
    try:
        fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
        return sum(int(fields[i]) for i in (11, 12, 13, 14)) / os.sysconf("SC_CLK_TCK")      # utime stime cutime cstime
    except (OSError, ValueError, IndexError):
        return None


class Outcome(dict):
    """Result of one supervised child: exit_code, reason, elapsed/cpu/rss, signal."""


def run_child(argv, *, cwd, env, log_path, timeout_s, cpu_budget_s, rss_limit_kib, grace_s, interrupted, on_poll=None,
              on_start=None, poll_s=POLL_S, sleep=time.sleep):
    """Spawn ``argv`` in its own process group and supervise it; exit status and resources come from ``wait4``."""
    assert_bounded(argv)
    log = open(log_path, "xb")
    started = time.time()
    try:
        proc = subprocess.Popen(argv, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
                                preexec_fn=_die_with_parent)
    finally:
        log.close()
    if on_start:
        on_start(proc.pid)
    reason, status, rusage, killed_at = "exited", None, None, None

    def reap(block):
        try:
            pid, state, usage = os.wait4(proc.pid, 0 if block else os.WNOHANG)
        except ChildProcessError:
            return True, None, None
        return pid != 0, state, usage

    def terminate(why):
        nonlocal reason, killed_at
        reason, killed_at = why, time.time()
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass

    while True:
        done, state, usage = reap(False)
        if done:
            status, rusage = state, usage
            break
        now = time.time()
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
            rss, cpu = proc_vmrss_kib(proc.pid), proc_cpu_s(proc.pid)
            if rss is not None and rss > rss_limit_kib:
                terminate("rss_limit")
            elif cpu is not None and cpu > cpu_budget_s:
                terminate("cpu_limit")
            elif on_poll is not None:
                verdict = on_poll(now - started)
                if verdict:
                    terminate(verdict)
        sleep(poll_s)
    code = os.waitstatus_to_exitcode(status) if status is not None else None
    proc.returncode = code if code is not None else -1      # the pid was reaped here; keep Popen.__del__ quiet
    outcome = Outcome(exit_code=code, reason=reason, elapsed_s=round(time.time() - started, 3),
                      cpu_user_s=round(getattr(rusage, "ru_utime", 0.0), 3), cpu_sys_s=round(getattr(rusage, "ru_stime", 0.0), 3),
                      peak_rss_kib=int(getattr(rusage, "ru_maxrss", 0)), pid=proc.pid, log=str(log_path))
    if code is not None and code < 0:
        outcome["signal"] = signal.Signals(-code).name
    return outcome


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
                 sleep=time.sleep, environ=None):
        self.work = Path(workdir)
        self.plan = plan
        self.launcher = launcher
        self.lock_builder = lock_builder
        self.allow_dirty = allow_dirty
        self.disk_usage = disk_usage
        self.gates, self.memo = gates, memo
        self.audit_depth = audit_depth
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
        return {"schema": RUN_SCHEMA, "plan": self.plan, "plan_fingerprint": digest(self.plan)}

    def _init_or_verify_identity(self):
        path = self.work / "run.json"
        if path.exists():
            stored = pre._read_json(path)
            if stored != self._identity():
                raise SupervisorError("restart refused: the requested plan (limits, shard size, ceilings, timing, paths) differs "
                                      "from the one this workdir was started with", EXIT_REFUSED)
            return True
        entries = [p.name for p in self.work.iterdir() if p.name != ".supervisor.lock"]
        if entries:
            raise SupervisorError(f"workdir is not empty and has no run.json: {sorted(entries)[:5]}", EXIT_REFUSED)
        pre._write_new(path, json.dumps(self._identity(), indent=1, allow_nan=False) + "\n")
        return False

    def _init_or_verify_lock(self, restart):
        path = self.work / "lock.json"
        if restart:
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
        records, problems = Journal.read(self.journal.path)
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
            if audit["state"] == "COMPLETE":
                self._verify_inventory(stage, audit)
                self.journal.append("stage_complete", stage=stage)
                return
            usage = self._usage()
            if usage["attempts"][stage] >= self.plan["ceilings"]["max_attempts_per_stage"]:
                raise SupervisorError(f"attempt budget exhausted for {stage}", EXIT_FAILED)
            self._check_budgets(usage, self._remaining_observations(audit, stage))
            outcome = self._attempt(stage, audit, usage)
            if outcome["reason"] == "interrupted":
                raise SupervisorError("interrupted; the root is left resumable", EXIT_INTERRUPTED)
            if outcome["reason"] != "exited":
                raise SupervisorError(f"{stage} attempt stopped by the supervisor: {outcome['reason']}", EXIT_FAILED)
            if outcome["exit_code"] != 0:
                self.journal.append("attempt_failed", stage=stage, exit_code=outcome["exit_code"],
                                    signal=outcome.get("signal"))
                continue                                       # re-audit; the attempt budget bounds the retries
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
        attempt_no = usage["attempts"][stage] + 1
        attempt_id = f"{stage}-{attempt_no:02d}"
        ceilings = self.plan["ceilings"]
        committed = sum(info["observations_committed"] for info in audit["roles"].values())
        remaining_shards = expected_shards(self.plan, stage) - sum(info["committed"] for info in audit["roles"].values())
        per_shard = self.plan["groups_per_shard"] * pre.STAGES[stage]["samples"]
        env = dict(self.environ)
        env.update({name: value for name, value in self.lock["environment"]["threads"].items() if value is not None})
        env["CUDA_VISIBLE_DEVICES"] = ""
        logs = self.work / "logs"
        logs.mkdir(exist_ok=True)
        started = time.time()
        gate = TimingGate(self._root(stage), self.plan["timing"], started=started, committed_observations=committed,
                          first_shard_observations=per_shard, remaining_shards=remaining_shards)

        def on_start(pid):
            self.journal.append("attempt_start", stage=stage, attempt_id=attempt_id, attempt=attempt_no, argv=argv, pid=pid,
                                committed_observations=committed, remaining_shards=remaining_shards)

        outcome = run_child(argv, cwd=str(REPO), env=env, log_path=logs / f"{attempt_id}.log",
                            timeout_s=ceilings["wall_hours"] * 3600 - usage["wall_s"],
                            cpu_budget_s=ceilings["core_hours"] * 3600 - usage["cpu_s"],
                            rss_limit_kib=int(ceilings["max_rss_gib"] * 2 ** 20), grace_s=ceilings["grace_s"],
                            interrupted=lambda: self.interrupt is not None, on_poll=gate, on_start=on_start,
                            poll_s=self.poll_s, sleep=self.sleep)
        if gate.record is not None:
            self.journal.append("timing_gate", stage=stage, attempt_id=attempt_id, **gate.record)
        peak_over = outcome["peak_rss_kib"] > ceilings["max_rss_gib"] * 2 ** 20
        if peak_over and outcome["reason"] == "exited":
            outcome["reason"] = "rss_limit"                    # the live poll can miss a short spike; wait4 cannot
        self.journal.append("attempt_end", stage=stage, attempt_id=attempt_id,
                            **{k: v for k, v in outcome.items() if k not in ("pid",)})
        return outcome

    # -- run ---------------------------------------------------------------------------------------------------
    def _recover_unterminated(self, records):
        usage = usage_from(records)
        open_attempt = usage["open_attempt"]
        if open_attempt is None:
            return
        pid = open_attempt.get("pid")
        if isinstance(pid, int) and pid_alive(pid):
            raise SupervisorError(f"attempt {open_attempt['attempt_id']} has no end record and pid {pid} is still alive: "
                                  "refusing to start a second writer", EXIT_REFUSED)
        self.journal.append("attempt_end", stage=open_attempt["stage"], attempt_id=open_attempt["attempt_id"],
                            exit_code=None, reason="supervisor_lost", elapsed_s=0.0, cpu_user_s=0.0, cpu_sys_s=0.0,
                            peak_rss_kib=0, note="the supervisor died without recording the end; resources unknown")

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
        try:
            self._acquire()
            restart = self._init_or_verify_identity()
            self._init_or_verify_lock(restart)
            records = self.journal.open()
            self._journal_open = True
            self._recover_unterminated(records)
            self.journal.append("supervisor_start", restart=restart, plan_fingerprint=digest(self.plan),
                                lock_fingerprint=self.lock["lock_fingerprint"], mode=self.plan["mode"])
            failed = [c for c in dry_run_checks(self.plan, self.work, lock_builder=lambda: self.lock, gates=self.gates,
                                                memo=self.memo, disk_usage=self.disk_usage)
                      if c["status"] == pre.FAIL]
            if failed:
                raise SupervisorError("host/resource checks failed: " + "; ".join(f"{c['id']}: {c['message']}" for c in failed),
                                      EXIT_FAILED)
            self.journal.append("host_checked", ok=True)
            for stage in STAGE_ORDER:
                self._run_stage(stage)
            self.journal.append("stages_complete", plan_fingerprint=digest(self.plan))
            return {"exit_code": EXIT_OK, "status": "STAGES_COMPLETE", "reasons": [], "benchmark_complete": False}
        except SupervisorError as error:
            event = "interrupted" if error.code == EXIT_INTERRUPTED else "run_failed"
            if self._journal_open:                          # a refusal before the journal was verified writes nothing
                try:
                    self.journal.append(event, reason=str(error), exit_code=error.code)
                except OSError:
                    pass
            return {"exit_code": error.code, "status": "INTERRUPTED" if error.code == EXIT_INTERRUPTED else "FAILED",
                    "reasons": [str(error)], "benchmark_complete": False}
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
    """Read-only: journal chain, lock, and every stage audit. Returns checks."""
    work = Path(workdir)
    run = load_run(work)
    plan = run["plan"]
    checks = []
    records, problems = Journal.read(work / "journal.jsonl")
    checks.append(pre.check("workdir.journal", "Journal chain is intact", pre.FAIL if problems else pre.PASS,
                            "; ".join(problems) or f"{len(records)} records, head {records[-1]['sha256'][:12] if records else 'none'}"))
    lock = pre._read_json(work / "lock.json")
    lock_problems = pre.verify_lock(lock, require_clean=plan["mode"] != "fixture" if require_clean is None else require_clean)
    checks.append(pre.check("workdir.lock", "Source/config/environment equal the lock", pre.FAIL if lock_problems else pre.PASS,
                            "; ".join(lock_problems[:6]) or "identical", problems=lock_problems))
    for stage in STAGE_ORDER:
        known = work / plan["roots"]["known"] if stage != "known" else None
        audit = pre.audit_artifact(work / plan["roots"][stage], stage, depth=depth, lock=lock, known=known, max_full=max_full,
                                   production=plan["mode"] == "production")
        item = pre.audit_check(audit)
        found = {role: info["observations_committed"] for role, info in audit["roles"].items()}
        if audit["state"] == "RESUMABLE":                      # e.g. every shard committed but the manifest is missing
            item = pre.check(item["id"], item["title"], pre.NOT_RUN,
                             f"stage is not COMPLETE ({item['message']}): the generator still has work to do", **audit)
        if audit["state"] == "COMPLETE" and found != plan["expected_observations"][stage]:
            item = pre.check(item["id"], item["title"], pre.FAIL, f"inventory {found} differs from the plan "
                             f"{plan['expected_observations'][stage]}", **audit)
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
              "journal_head": records[-1]["sha256"], "observations": plan["expected_observations"],
              "stage_manifest_fingerprints": {s: pre._fingerprint(pre._read_json(work / plan["roots"][s] / "manifest.json"))
                                              for s in STAGE_ORDER},
              "note": "data generation of the planned scope is complete and verified; this is not benchmark completion"}
    pre._write_new(work / "completion.json", json.dumps(marker, indent=1, allow_nan=False) + "\n")
    return marker


# ---- command line ------------------------------------------------------------------------------------------------

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
                      ceilings=ceilings, timing=timing)


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
    except (ValueError, OSError) as error:
        _print({"status": "FAILED", "reasons": [str(error)], "benchmark_complete": False, "exit_code": EXIT_FAILED})
        return EXIT_FAILED


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""E13 DR-04 generation launch-PLAN validation: data-free, non-launching, never an authorizer.

    python scripts/b2_e13_generation_plan.py status                    # readiness of this checkout (always NO-GO today)
    python scripts/b2_e13_generation_plan.py template [--out FILE]     # plan skeleton derived from this checkout
    python scripts/b2_e13_generation_plan.py digest   --plan FILE                    # the digest an approver commits (not an approval)
    python scripts/b2_e13_generation_plan.py validate --plan FILE [--lock FILE] [--out FILE]

A *plan* is a strict-JSON document that names exactly what a future, separately reviewed and separately authorized
full-generation run would do: the frozen 21,350-observation inventory, the source/config/environment identities, the
host, the independent backup device, explicit ceilings, the first-shard timing and stop rules, the E12 D-1 exposure
and D-8 K17d obligations and a DR-04 authorization record. ``validate_plan`` compares that document with a reference
snapshot of the checkout and returns a structured report.

What this module is not:
 * it starts nothing: it has no argv builder, no generator callback and no execute flag; the stage options of a plan are
   declarative data that nothing in this repository can turn into a command. ``validate_plan`` itself creates no
   process. Collecting the reference runs read-only ``git`` queries (an injectable callable) and, with ``--lock``, the
   preflight's lock builder (``git`` and ``uname``); nothing here runs a generator;
 * it synthesizes no waveform and opens no observation (the K17d identity is re-derived from scene metadata only);
 * it never reports GO: the verdict is NO-GO by construction, ``execution_permitted`` is always false and the
   structural blockers (launch flag, no unbounded supervisor command, fixture cap, E9 guard) are re-checked on every call.
   A plan that is consistent is a statement about a document, not a permission;
 * it does not touch ``PRODUCTION_LAUNCH_ENABLED``, the supervisor caps, ``guard_execution`` or any gate.

Exit codes: 2 usage or unreadable/malformed input, 3 a FAIL finding (plan or structural), 4 NO-GO. Never 0 for
``status`` and ``validate``: there is no success state that could be mistaken for permission.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
import platform
import re
import shutil
import stat
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath

import numpy as np
import scipy

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import b2_e12_verify_k17d as k17d_check  # noqa: E402
import b2_host_inventory as host_inventory  # noqa: E402
import b2_production_preflight as pre  # noqa: E402
import b2_production_supervisor as sup  # noqa: E402

from geoml import b2_e9_contract as e9  # noqa: E402
from geosim import b2_dataset  # noqa: E402
from geosim.b2_protocol import LABELS, ROLE_COUNTS, ROLE_STARTS, B2Config, protocol_contract  # noqa: E402
from geosim.b2_scenarios import MATCHED_LABELS, TEST_FAMILIES  # noqa: E402
from geosim.cancellation import CancellationConfig  # noqa: E402

ROOT = pre.REPO
SCHEMA_PLAN = "B2-E13-generation-plan/1"
SCHEMA_REFERENCE = "B2-E13-generation-reference/1"
SCHEMA_AUTHORIZATION = "B2-E13-dr04-authorization-record/1"
SCHEMA_REPORT = "B2-E13-generation-plan-report/1"
STAGE_ID = "DR-04"
MODE = "production_plan"
DOCUMENT_OK, DOCUMENT_NOT_OK = "DOCUMENT_CONSISTENT_NOT_A_PERMISSION", "INCOMPLETE_OR_INCONSISTENT"
DECISIONS = "docs/plan/b2_e12_d1_d8_decisions_2026-10-24.json"
PROTOCOL_JSON = "docs/plan/b2_e9_approved_scientific_protocol.json"
# Records that ratify the *scientific* protocol. None of them can be the basis of a compute authorization.
SCIENTIFIC_RECORDS = ("docs/plan/B2_E9_SCIENTIFIC_DECISION_APPROVAL_2026-10-24.md", PROTOCOL_JSON,
                      "docs/plan/B2_E12_D1_D8_SCIENTIFIC_APPROVAL_2026-10-24.md", DECISIONS)
INPUT_FILES = (pre.GATES_PATH, pre.MEMO_PATH, DECISIONS, k17d_check.IDENTITY, k17d_check.AUDIT, PROTOCOL_JSON)
TOOLS = ("b2_e13_generation_plan.py", "b2_production_supervisor.py", "b2_production_preflight.py", "b2_host_inventory.py", "b2_e12_verify_k17d.py")
PASS, FAIL, BLOCKED = "PASS", "FAIL", "BLOCKED"
HEX40, HEX64 = re.compile(r"[0-9a-f]{40}"), re.compile(r"[0-9a-f]{64}")
MAX_PLAN_BYTES = 4 * 2 ** 20
MAX_DEPTH = 40
MAX_RECORD_BYTES = 256 * 1024
MEASURED_GENERATOR_PEAK_GIB = 601 / 1024          # E5 single-process profile; E7a child peaks were 566 - 582 MiB (2 groups)
CORE_TO_WALL = pre.BUDGET["cpu_to_wall_ratio"]
DISK_MARGIN = 1.1                                  # the supervisor's own artifact margin (dry_run_checks)
AUTH_MAX_VALIDITY = timedelta(days=30)             # E13 rule: an authorization is a short-lived, re-issuable record
INVENTORY_MAX_AGE = timedelta(days=14)             # E13 rule: a host report older than this describes some other day
VOLATILE_PREFIXES = ("/dev", "/proc", "/sys", "/run", "/tmp", "/var/tmp", "/var/run")
DURABLE_UNDER_VOLATILE = ("/run/media", "/run/mount")      # removable drives are mounted there; the filesystem type still has to be durable
VOLATILE_FSTYPES = frozenset({"tmpfs", "ramfs", "devtmpfs", "proc", "sysfs", "cgroup", "cgroup2", "devpts", "mqueue", "securityfs", "debugfs",
                              "tracefs", "configfs", "fusectl", "pstore", "bpf", "hugetlbfs", "autofs", "binfmt_misc", "efivarfs"})
BACKUP_REFUSED_FSTYPES = VOLATILE_FSTYPES | {"overlay", "squashfs"}
# Option names (without dashes) a plan may declare per stage; nothing here limits groups, so there is no group-limit option.
STAGE_OPTIONS = {"known": ("out", "config", "cancellation", "groups_per_shard"),
                 "test": ("out", "known", "config", "cancellation", "groups_per_shard"),
                 "matched": ("out", "known", "config", "cancellation", "groups_per_shard")}
FORBIDDEN_KEYS = frozenset({"argv", "args", "command", "cmd", "execute", "exec", "run", "launch", "launcher", "callback", "hook",
                            "shell", "subprocess", "child", "spawn", "limit_groups", "max_groups", "allow_dirty", "override",
                            "bypass", "fixture", "force", "skip_gates", "skip_checks"})
PLAN_KEYS = ("schema", "stage", "mode", "benchmark_complete", "plan_fingerprint", "inventory", "stages", "generator_assumptions",
             "source", "environment", "lock", "scientific", "host", "working", "backup", "ceilings", "ceilings_status",
             "timing", "stop_rules", "post_generation_obligations", "release_evidence", "authorization")
SOURCE_KEYS = ("git_commit", "tree_clean", "files_sha256", "source_tree_sha256", "configs_sha256", "generator_provenance_fingerprint",
               "parsed_config_sha256", "known_request_fingerprint", "tools_sha256", "records_sha256")
CEILING_KEYS = ("wall_hours", "core_hours", "max_failed_attempts_per_stage", "max_interruptions_per_stage", "max_rss_gib",
                "min_free_disk_gib", "grace_s", "backup_disk_gb", "host_ram_gib")
CEILINGS_STATUS = ("PROPOSED_NOT_APPROVED", "RESEARCHER_APPROVED_IN_DR04_RECORD")
THREAD_VARIABLES = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "PYTHONHASHSEED")
AUTH_KEYS = ("schema", "kind", "gate", "stage", "observations", "basis", "approved_by", "approved_at", "expires_at", "decision",
             "record", "record_sha256", "plan_fingerprint", "approved_plan_digest", "git_commit", "lock_fingerprint", "host_id",
             "working_storage_id", "backup_storage_id", "ceilings", "grants", "does_not_grant")
AUTH_GATE_CEILINGS = ("wall_hours", "core_hours", "working_disk_gib", "backup_disk_gb")
AUTH_BASIS = "researcher_written_compute_authorization"
APPROVAL_BLOCK_SCHEMA = "B2-E13-dr04-approval-block/1"
APPROVAL_BLOCK_KEYS = ("schema", "decision", "approved_by", "approved_plan_digest", "host_id", "expires_at")
FENCED_JSON = re.compile(r"```json[ \t]*\n(.*?)\n```", re.DOTALL)
OTHER_COMPUTE_GATES = ("full_gpu_training", "full_loko_sweep")
NOT_GRANTED = ("gpu_probe", "full_gpu_training", "full_loko_sweep", "nine_cell_freeze", "held_out_final_evaluation",
               "production_launch_flag_change")
STOP_RULES = {"max_failed_attempts_per_stage": sup.PRODUCTION_CEILINGS["max_failed_attempts_per_stage"],
              "max_interruptions_per_stage": sup.PRODUCTION_CEILINGS["max_interruptions_per_stage"],
              "max_total_attempts_per_stage": sup.MAX_TOTAL_ATTEMPTS_PER_STAGE,
              "on_first_shard_timing_gate_failure": "stop", "on_damaged_committed_shard": "stop_and_quarantine",
              "on_validator_refusal": "stop", "on_ceiling_breach": "stop", "on_interruption": "resume_only_under_identical_request",
              "resume_requires_identical_request_source_environment": True, "cleanup_may_delete_evidence": False,
              "orphan_shard_files": "quarantine_never_delete"}
OBLIGATIONS = {"k17d_production_metadata_cross_check": {
                   "status": "REQUIRED_NOT_RUN", "before": "any separately authorized final evaluation",
                   "must_agree": ["headline membership", "unique sorted IDs", "role", "co/cross drop predicate",
                                  "source and audit identity"], "on_disagreement": "fail_closed_and_rederive_with_independent_review"},
               "exposure_disclosure": {"status": "REQUIRED_IN_EVERY_FINAL_REPORT", "existing_test_pristine": False,
                                       "mandatory_exclusion_rows": {"test": 498, "test-matched": 148}},
               "backup_checksum_verified_before_data_is_made_read_only": True}
RELEASE_KEYS = ("independent_review", "exact_head_ci", "self_asserted")


# ---- helpers ------------------------------------------------------------------------------------------------------

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def sha256_of(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def _same(left, right):
    """Equality that does not let 4.0 stand for 4 or True for 1 (compares canonical JSON)."""
    try:
        return canonical(left) == canonical(right)
    except (TypeError, ValueError, RecursionError):
        return False


def _same_numbers(left, right, keys):
    """Numeric (not textual) equality of the named fields: 36 and 36.0 are the same ceiling, True and 1 are not a number at all."""
    return (isinstance(left, dict) and isinstance(right, dict) and all(_num(left.get(k)) and _num(right.get(k)) and left[k] == right[k] for k in keys))


def _short(value, limit=120):
    text = repr(value)
    return text if len(text) <= limit else text[:limit] + "..."


def _num(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def _hex64(value):
    return isinstance(value, str) and HEX64.fullmatch(value) is not None


def _instant(value):
    if not _text(value):
        return None
    try:
        moment = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment if moment.tzinfo is not None else None


def _safe_abs_path(value):
    """An absolute, normalized POSIX path with no traversal, NUL, empty or dot components; None when unsafe."""
    if not isinstance(value, str) or not value.startswith("/") or "\x00" in value or len(value) > 4096 or value.endswith("/"):
        return None
    parts = value.split("/")[1:]
    if len(parts) < 2 or any(part in ("", ".", "..") for part in parts):
        return None
    return PurePosixPath(value)


def _under(path, prefix):
    return path == prefix or path.startswith(prefix + "/")


def _volatile(path):
    return any(_under(path, prefix) for prefix in VOLATILE_PREFIXES) and not any(_under(path, ok) for ok in DURABLE_UNDER_VOLATILE)


def _safe_repo_relative(value):
    if not isinstance(value, str) or not value or "\x00" in value or value.startswith("/") or len(value) > 512:
        return None
    parts = value.split("/")
    return None if any(part in ("", ".", "..") for part in parts) else PurePosixPath(value)


def _depth_exceeds(value, limit=MAX_DEPTH):
    """Iterative depth test (a recursive walk would itself be the denial of service)."""
    stack = [(value, 1)]
    while stack:
        item, depth = stack.pop()
        if isinstance(item, (dict, list)):
            if depth > limit:
                return True
            stack.extend((child, depth + 1) for child in (item.values() if isinstance(item, dict) else item))
    return False


def _forbidden_keys(value, limit=8):
    """Paths of dictionary keys that name an execution, launcher, callback or group-limit field. Iterative, case-insensitive.

    Each stack entry keeps a link to its parent instead of a path string, so memory stays linear in the document size
    whatever the key lengths are; a path is rendered only for the (at most ``limit``) keys that are reported.
    """
    found, stack = [], [(value, None)]
    while stack and len(found) < limit:
        item, link = stack.pop()
        if isinstance(item, dict):
            for key, child in item.items():
                if isinstance(key, str) and key.lower() in FORBIDDEN_KEYS:
                    found.append((key, link))
                    if len(found) >= limit:
                        break
                stack.append((child, (key, link)))
        elif isinstance(item, list):
            stack.extend((child, (index, link)) for index, child in enumerate(item))

    def render(key, link):
        parts = [key]
        while link is not None:
            parts.append(link[0])
            link = link[1]
        return "$" + "".join(f"[{part}]" if isinstance(part, int) else "." + str(part)[:60] for part in reversed(parts))
    return sorted(render(key, link) for key, link in found)


def plan_fingerprint(plan):
    """Identity of the proposal itself: everything except the fingerprint and the authorization that refers to it."""
    return sha256_of({key: value for key, value in plan.items() if key not in ("plan_fingerprint", "authorization")})


def approved_plan_digest(plan):
    """Digest of what an approver reads: the plan *design* and the code identity, but nothing the approval commit itself changes.

    Included: inventory, stages, environment, host id, roots, ceilings, rules, the D-1/D-8 identities and the code identity
    (source tree, generator provenance, known-stage request, parsed physics, tool hashes, the configs other than the gates JSON
    and the records other than the memorandum). Left out: the commit, the gates JSON and memorandum hashes, the lock, the
    measured host report and the release evidence, which change when the approval is committed. The approval therefore
    cannot be carried over to a later source tree, and a researcher can still write the digest into a committed record
    before the lock exists.
    """
    scientific = plan.get("scientific") if isinstance(plan.get("scientific"), dict) else {}
    host = plan.get("host") if isinstance(plan.get("host"), dict) else {}
    source = plan.get("source") if isinstance(plan.get("source"), dict) else {}

    def without(mapping, *names):
        return {k: v for k, v in mapping.items() if k not in names} if isinstance(mapping, dict) else mapping
    code = {"source_tree_sha256": source.get("source_tree_sha256"), "generator_provenance_fingerprint": source.get("generator_provenance_fingerprint"),
            "known_request_fingerprint": source.get("known_request_fingerprint"), "parsed_config_sha256": source.get("parsed_config_sha256"),
            "tools_sha256": source.get("tools_sha256"), "configs_sha256": without(source.get("configs_sha256"), pre.GATES_PATH),
            "records_sha256": without(source.get("records_sha256"), pre.MEMO_PATH)}
    return sha256_of({"stage": plan.get("stage"), "mode": plan.get("mode"), "inventory": plan.get("inventory"), "stages": plan.get("stages"),
                      "generator_assumptions": plan.get("generator_assumptions"), "environment": plan.get("environment"),
                      "d1_exposure": scientific.get("d1_exposure"), "d8_k17d": scientific.get("d8_k17d"), "host_id": host.get("host_id"),
                      "working": plan.get("working"), "backup": plan.get("backup"), "ceilings": plan.get("ceilings"), "timing": plan.get("timing"),
                      "stop_rules": plan.get("stop_rules"), "post_generation_obligations": plan.get("post_generation_obligations"), "code": code})


def approval_block(plan):
    """The strict-JSON block the approver's committed record must contain (a template: the researcher fills approved_by/decision)."""
    host = plan.get("host") if isinstance(plan.get("host"), dict) else {}
    return {"schema": APPROVAL_BLOCK_SCHEMA, "decision": "APPROVE", "approved_by": "<the approver>", "approved_plan_digest": approved_plan_digest(plan),
            "host_id": host.get("host_id"), "expires_at": "<ISO-8601 instant within 30 days>"}


def _approval_blocks(text):
    """Valid fenced strict-JSON objects of the approval-block schema found in a record."""
    blocks = []
    for match in FENCED_JSON.finditer(text if isinstance(text, str) else ""):
        try:
            block = k17d_check._strict(match.group(1).encode("utf-8"))
        except (k17d_check.K.K17dError, RecursionError):
            continue
        if block.get("schema") == APPROVAL_BLOCK_SCHEMA:
            blocks.append(block)
    return blocks


class _Findings:
    def __init__(self):
        self.items = []

    def add(self, identifier, status, message, **evidence):
        self.items.append({"id": identifier, "status": status, "message": message, "evidence": evidence})

    def ok(self, identifier, message, **evidence):
        self.add(identifier, PASS, message, **evidence)

    def fail(self, identifier, message, expected=None, actual=None):
        self.add(identifier, FAIL, message, expected=_short(expected), actual=_short(actual))

    def blocked(self, identifier, message):
        self.add(identifier, BLOCKED, message)

    def check(self, identifier, condition, message, expected=None, actual=None):
        (self.ok(identifier, message) if condition else self.fail(identifier, "does not hold: " + message, expected, actual))
        return bool(condition)


def _exact_keys(findings, identifier, value, keys, label):
    if not isinstance(value, dict):
        findings.fail(identifier, f"{label} must be an object", "object", type(value).__name__)
        return False
    missing, extra = [k for k in keys if k not in value], sorted(repr(k) for k in value if k not in keys)
    if missing or extra:
        findings.fail(identifier, f"{label} fields differ from the contract", {"missing": missing, "unexpected": extra}, sorted(map(str, value)))
        return False
    return True


# ---- expected (derived, never copied from documents) ---------------------------------------------------------------

def expected_assumptions():
    return {"groups_per_shard": pre.PRODUCTION["groups_per_shard"], "window_shards": pre.PRODUCTION["window_shards"],
            "known_protocol": pre.PRODUCTION["known_protocol"], "canceller_version": pre.PRODUCTION["canceller_version"],
            "group_limit": "none_full_frozen_counts", "labels": list(LABELS), "test_families": list(TEST_FAMILIES),
            "matched_labels": list(MATCHED_LABELS), "role_starts": dict(ROLE_STARTS), "role_counts": dict(ROLE_COUNTS),
            "protocol_contract_sha256": sha256_of(protocol_contract())}


def expected_stages():
    stages = {}
    for stage in sup.STAGE_ORDER:
        options = {"out": stage, "config": "configs/b2_base.json", "cancellation": "configs/cancellation.json",
                   "groups_per_shard": pre.PRODUCTION["groups_per_shard"]}
        if stage != "known":
            options["known"] = "known"
        stages[stage] = {"module": sup.MODULES[stage], "options": options}
    return stages


def required_free_gib(observations, reserve_gib):
    """The supervisor's start condition: the estimated artifacts plus 10 % plus the reserve (dry_run_checks)."""
    return observations * sup.ARTIFACT_BYTES_PER_OBSERVATION / 2 ** 30 * DISK_MARGIN + reserve_gib


def estimated_hours():
    """High-end single-process estimate: the larger of the supervisor's flat rate and the preflight's (CID overlays at 8 s)."""
    total = sum(row["observations"] for row in pre.derive_inventory())
    high = sup.DEFAULT_TIMING["band_s_per_observation"][1]
    wall = max(total * high / 3600, pre.wall_hours(high))
    return {"observations": total, "wall_high_hours": wall, "core_high_hours": wall * CORE_TO_WALL}


def proposed_ceilings():
    """The E5 proposals as the supervisor holds them, plus the two host-side figures. Proposals, not authorizations."""
    base = dict(sup.PRODUCTION_CEILINGS)
    base.update(backup_disk_gb=pre.PROPOSED_CEILINGS["backup_disk_gb"], host_ram_gib=pre.PROPOSED_CEILINGS["host_ram_gib_generation"])
    return base


# ---- reference snapshot of the checkout (reads files; never an observation, a waveform or a model) ------------------

def _environment():
    """The pinned facts of the validating process. No subprocess (platform.platform() runs uname) and no heavy imports."""
    return {"python": platform.python_version(), "numpy": np.__version__, "scipy": scipy.__version__,
            "threads": {name: os.environ.get(name) for name in THREAD_VARIABLES}}


def _git(git, repo, *args):
    return git("-c", "core.fsmonitor=false", *args, repo=repo)


def _committed(git, repo, relative):
    """True only for a regular, non-symlink, tracked file whose working-tree blob equals HEAD's. Any git failure is False."""
    try:
        path = Path(repo) / relative
        if not stat.S_ISREG(os.lstat(path).st_mode):
            return False
        _git(git, repo, "ls-files", "--error-unmatch", "--", relative)
        return _git(git, repo, "rev-parse", f"HEAD:{relative}") == _git(git, repo, "hash-object", "--", relative)
    except Exception:
        return False


def _measure_root(root):
    """Stat-only facts about a declared root, taken on the machine that validates (nothing is created)."""
    try:
        status = os.stat(root)
        return {"exists": True, "device": status.st_dev, "fstype": host_inventory.fstype_of(root), "free_gib": round(shutil.disk_usage(root).free / 2 ** 30, 2)}
    except OSError:
        return {"exists": False, "device": None, "fstype": None, "free_gib": None}


def _file_hash_or_none(path):
    try:
        return pre._file_hash(path) if Path(path).is_file() else None
    except OSError:
        return None


def _source_files(repo, files):
    """Every file the lock and the plan hash: src, the locked configs and the tools. All must be committed, not only the inputs."""
    return sorted(set(files) | set(pre.LOCKED_CONFIGS) | {f"scripts/{name}" for name in TOOLS})


def collect_reference(repo=ROOT, *, rederive=True, git=pre.run_git, evaluated_at=None, lock_path=None, record_paths=(), roots=()):
    """Facts about the checkout against which a plan is compared. ``git`` is injectable; nothing else is executed.

    The snapshot is taken twice (HEAD, cleanliness and input hashes) and refused if the checkout changed in between.
    """
    repo = Path(repo)
    now = evaluated_at or datetime.now(timezone.utc).isoformat()

    def state():
        try:
            head = _git(git, repo, "rev-parse", "HEAD")
            dirty = _git(git, repo, "status", "--porcelain", "--untracked-files=all")
        except Exception:                               # a checkout without git is simply not clean/identified
            head, dirty = "unknown", "unknown"
        return head, dirty == "", {name: _file_hash_or_none(repo / name) for name in INPUT_FILES}

    first = state()
    config = B2Config.from_file(repo / "configs/b2_base.json")
    cancellation = CancellationConfig(**pre._read_json(repo / "configs/cancellation.json"))
    request = b2_dataset._request(config, b2_dataset.BASE_ROLES, None, pre.PRODUCTION["groups_per_shard"], cancellation)
    decisions_raw = (repo / DECISIONS).read_bytes()
    reference = {
        "schema": SCHEMA_REFERENCE, "evaluated_at": now, "head": first[0], "tree_clean": first[1],
        "files_sha256": pre.tree_hashes(repo),
        "configs_sha256": {name: pre._file_hash(repo / name) for name in pre.LOCKED_CONFIGS},
        "generator_provenance_fingerprint": pre._fingerprint(pre._generator_provenance()),
        "parsed_config_sha256": {"b2_config": sha256_of(config.to_dict()), "cancellation": sha256_of(cancellation.to_dict())},
        "known_request_fingerprint": pre._fingerprint(request), "environment": _environment(),
        "tools_sha256": {name: pre._file_hash(HERE / name) for name in TOOLS},
        "records_sha256": {name: first[2][name] for name in INPUT_FILES if name != pre.GATES_PATH},
        "committed_inputs": {name: _committed(git, repo, name) for name in INPUT_FILES},
        "uncommitted_source": [], "host_measurements": {"node": platform.node(), "roots": {root: _measure_root(root) for root in roots if _safe_abs_path(root)}},
        "gates": pre._read_json(repo / pre.GATES_PATH), "memo": pre._read_json(repo / pre.MEMO_PATH),
        "scientific_protocol": pre._read_json(repo / PROTOCOL_JSON),
        "scientific_record_sha256": sorted(h for h in (_file_hash_or_none(repo / name) for name in SCIENTIFIC_RECORDS) if h),
        "decision_record": {"path": DECISIONS, "sha256": hashlib.sha256(decisions_raw).hexdigest(),
                            "document": k17d_check._strict(decisions_raw)},
        "k17d_verification": k17d_check.verify_identity(root=repo, acceptance_path=DECISIONS, rederive=rederive),
        "record_files": {}, "record_texts": {}, "lock": None, "lock_problems": None}
    reference["uncommitted_source"] = [name for name in _source_files(repo, reference["files_sha256"]) if not _committed(git, repo, name)]
    for path in record_paths:
        relative = _safe_repo_relative(path)
        if relative is not None and relative.parts[0] == "docs" and _committed(git, repo, path):
            reference["record_files"][path] = pre._file_hash(repo / relative)
            with open(repo / relative, "rb") as stream:
                reference["record_texts"][path] = stream.read(MAX_RECORD_BYTES).decode("utf-8", errors="replace")
    if lock_path is not None:
        lock = pre._read_json(lock_path)
        reference["lock"] = lock
        reference["lock_problems"] = pre.verify_lock(lock, repo, require_clean=True)
    if state() != first:
        raise ValueError("the checkout changed while the reference was collected; run again on a quiescent tree")
    return reference


def make_template(reference):
    """A skeleton derived from the reference. Host, backup, lock, evidence and authorization are deliberately absent."""
    files = reference["files_sha256"]
    plan = {"schema": SCHEMA_PLAN, "stage": STAGE_ID, "mode": MODE, "benchmark_complete": False, "plan_fingerprint": None,
            "inventory": {"total_observations": pre.PLAN_TOTAL, "stage_order": list(sup.STAGE_ORDER),
                          "groups_per_shard": pre.PRODUCTION["groups_per_shard"], "rows": pre.derive_inventory()},
            "stages": expected_stages(), "generator_assumptions": expected_assumptions(),
            "source": {"git_commit": reference["head"], "tree_clean": reference["tree_clean"], "files_sha256": dict(files),
                       "source_tree_sha256": sha256_of(files), "configs_sha256": dict(reference["configs_sha256"]),
                       "generator_provenance_fingerprint": reference["generator_provenance_fingerprint"],
                       "parsed_config_sha256": dict(reference["parsed_config_sha256"]),
                       "known_request_fingerprint": reference["known_request_fingerprint"],
                       "tools_sha256": dict(reference["tools_sha256"]), "records_sha256": dict(reference["records_sha256"])},
            "environment": {"python": reference["environment"]["python"], "numpy": reference["environment"]["numpy"],
                            "scipy": reference["environment"]["scipy"],
                            "thread_environment": dict(reference["environment"]["threads"])},
            "lock": None,
            "scientific": {"decision_record": {"path": DECISIONS, "sha256": reference["decision_record"]["sha256"]},
                           "d1_exposure": _d1_from(reference["decision_record"]["document"]),
                           "d8_k17d": _d8_from(reference["decision_record"]["document"]),
                           "k17d_verification": copy.deepcopy(reference["k17d_verification"])},
            "host": None, "working": None, "backup": None, "ceilings": proposed_ceilings(),
            "ceilings_status": "PROPOSED_NOT_APPROVED", "timing": copy.deepcopy(sup.DEFAULT_TIMING),
            "stop_rules": copy.deepcopy(STOP_RULES), "post_generation_obligations": copy.deepcopy(OBLIGATIONS),
            "release_evidence": None, "authorization": None}
    plan["plan_fingerprint"] = plan_fingerprint(plan)
    return plan


def _d1_from(document):
    d1 = document["decisions"]["D-1"]
    return {"choice": d1["choice"], "existing_test_pristine": d1["existing_test_pristine"],
            "exposed_test_ids": list(d1["exposed_test_ids"]), "exposed_matched_ids": list(d1["exposed_matched_ids"]),
            "mandatory_exclusion_rows": dict(d1["mandatory_exposure_excluded_groups"])}


def _d8_from(document):
    d8 = document["decisions"]["D-8"]
    return {"choice": d8["choice"], "counts": dict(d8["counts"]), "identity_sha256": document["k17d_identity"]["sha256"],
            "future_production_metadata_cross_check": d8["future_production_metadata_cross_check"]}


# ---- validation sections ------------------------------------------------------------------------------------------

def _check_shape(plan, f):
    if not _exact_keys(f, "plan.shape", plan, PLAN_KEYS, "plan"):
        return
    f.check("plan.shape", plan["schema"] == SCHEMA_PLAN and plan["stage"] == STAGE_ID and plan["benchmark_complete"] is False,
            "schema, stage DR-04 and benchmark_complete=false", (SCHEMA_PLAN, STAGE_ID, False), (plan["schema"], plan["stage"], plan["benchmark_complete"]))
    f.check("plan.mode", plan["mode"] == MODE, "mode is the data-free production plan (no fixture or execution mode exists)", MODE, plan["mode"])
    f.check("plan.fingerprint", plan["plan_fingerprint"] == plan_fingerprint(plan), "plan_fingerprint equals the digest of the plan body",
            plan_fingerprint(plan), plan["plan_fingerprint"])


def _check_inventory(plan, f):
    inventory = plan["inventory"]
    expected = {"total_observations": pre.PLAN_TOTAL, "stage_order": list(sup.STAGE_ORDER),
                "groups_per_shard": pre.PRODUCTION["groups_per_shard"], "rows": pre.derive_inventory()}
    if not f.check("plan.inventory", _same(inventory, expected), "inventory equals the 21,350-observation frozen inventory derived from code constants "
                   "(roles, group ranges, variants, shards)", expected["total_observations"],
                   inventory if not isinstance(inventory, dict) else {k: v for k, v in inventory.items() if k != "rows"}):
        return
    rows = inventory["rows"]
    baseline = pre.check_inventory()
    f.check("plan.inventory_independent", all(item["status"] == pre.PASS for item in baseline) and sum(r["observations"] for r in rows) == pre.PLAN_TOTAL,
            "the code-derived inventory still equals the independent literal E5 table (a committed edit of ROLE_COUNTS or the label sets cannot validate itself)",
            "21350 and all inventory checks PASS", [item["id"] for item in baseline if item["status"] != pre.PASS])
    known_groups = {(row["role"]) for row in rows if row["stage"] == "B2-feat/1"}
    f.check("plan.roles", known_groups == {"train", "val-select", "val-calib", "test"} and
            {row["role"] for row in rows if row["stage"] == "B2-match/1"} == {"test-matched"}, "no role mixing: the known stage holds the four base roles, "
            "matched holds test-matched only")


def _check_stages(plan, f):
    stages, expected = plan["stages"], expected_stages()
    if not isinstance(stages, dict) or list(stages) != list(sup.STAGE_ORDER):
        f.fail("plan.stage_order", "stages must be exactly known, test, matched in that order", list(sup.STAGE_ORDER),
               list(stages) if isinstance(stages, dict) else stages)
        return
    f.ok("plan.stage_order", "known -> test-only -> matched ordering")
    problems = []
    for stage in sup.STAGE_ORDER:
        entry = stages[stage]
        if not isinstance(entry, dict) or set(entry) != {"module", "options"}:
            problems.append(f"{stage}: fields differ")
            continue
        if entry["module"] != expected[stage]["module"]:
            problems.append(f"{stage}: module {_short(entry['module'])}")
        options = entry["options"]
        if not isinstance(options, dict):
            problems.append(f"{stage}: options must be an object")
            continue
        unknown = sorted(map(repr, set(options) - set(STAGE_OPTIONS[stage])))
        if unknown:
            problems.append(f"{stage}: unknown options {unknown}")
        for name, value in expected[stage]["options"].items():
            if name in options and not _same(options[name], value) and name in STAGE_OPTIONS[stage]:
                problems.append(f"{stage}: option {name} is {_short(options[name])}, expected {_short(value)}")
        for name in STAGE_OPTIONS[stage]:
            if name not in options:
                problems.append(f"{stage}: option {name} missing")
    roots = [stages[s]["options"].get("out") for s in sup.STAGE_ORDER if isinstance(stages[s], dict) and isinstance(stages[s].get("options"), dict)]
    if len(set(map(repr, roots))) != len(roots):
        problems.append("stage roots must be distinct (role mixing)")
    f.check("plan.stage_options", not problems, "stage options are the declarative frozen set: relative root names, the two configs, four groups "
            "per shard, no group-limit option, no unknown flag", [], problems[:6])
    f.check("plan.paths", all(_safe_repo_relative(stages[s]["options"].get(k)) is not None for s in sup.STAGE_ORDER
                              if isinstance(stages[s], dict) and isinstance(stages[s].get("options"), dict)
                              for k in ("out", "config", "cancellation", "known") if k in stages[s]["options"]),
            "stage paths are relative, normalized and free of traversal")


def _check_assumptions(plan, f):
    f.check("plan.generator_assumptions", _same(plan["generator_assumptions"], expected_assumptions()),
            "frozen seeds, role ranges, labels, families, shard size and canceller version equal the code-derived values",
            "expected_assumptions()", plan["generator_assumptions"])


def _check_source(plan, ref, f):
    source = plan["source"]
    if not _exact_keys(f, "source.shape", source, SOURCE_KEYS, "source"):
        return
    f.check("source.git", isinstance(source["git_commit"], str) and HEX40.fullmatch(source["git_commit"]) is not None
            and source["git_commit"] == ref["head"], "plan git commit is a 40-hex SHA equal to the checkout HEAD", ref["head"], source["git_commit"])
    f.check("source.clean", source["tree_clean"] is True and ref["tree_clean"] is True,
            "the whole working tree is clean (git status --porcelain --untracked-files=all is empty)", True, (source["tree_clean"], ref["tree_clean"]))
    hidden = list(ref["uncommitted_source"])
    f.check("source.committed_source", not hidden, "every src file, locked config and tool the plan hashes is tracked and equal to HEAD's blob (catches "
            "skip-worktree edits and ignored extra files that git status does not show)", [], hidden[:6])
    uncommitted = sorted(name for name, committed in ref["committed_inputs"].items() if committed is not True)
    f.check("source.committed_inputs", not uncommitted, "the gates JSON, memorandum, decision register, K17d identity and audit and the scientific protocol "
            "record are regular tracked files equal to HEAD's blobs (not symlinks, not uncommitted edits)", [], uncommitted)
    files = source["files_sha256"]
    if isinstance(files, dict) and all(isinstance(v, str) and HEX64.fullmatch(v) for v in files.values()):
        names = sorted(set(files) | set(ref["files_sha256"]))
        diff = [("modified" if n in files and n in ref["files_sha256"] else "added" if n in files else "removed") + ":" + n
                for n in names if files.get(n) != ref["files_sha256"].get(n)]
        f.check("source.files", not diff, "per-file src/ hashes equal the checkout (the production lock hashes the same tree)", [], diff[:8])
        f.check("source.tree_digest", source["source_tree_sha256"] == sha256_of(files), "source_tree_sha256 is the digest of the per-file map")
    else:
        f.fail("source.files", "files_sha256 must map paths to sha256", "dict of hex64", _short(files))
    f.check("source.configs", _same(source["configs_sha256"], ref["configs_sha256"]),
            "locked configuration files (b2_base, cancellation, b2_feat, pyproject, gates JSON) equal the checkout")
    f.check("source.generator", source["generator_provenance_fingerprint"] == ref["generator_provenance_fingerprint"]
            and _same(source["parsed_config_sha256"], ref["parsed_config_sha256"]), "generator provenance and parsed physical/canceller configuration are frozen")
    f.check("source.known_request", source["known_request_fingerprint"] == ref["known_request_fingerprint"],
            "the known-stage request fingerprint the generator would write today equals the plan's (binds config, source, numpy/scipy)")
    f.check("source.tools", _same(source["tools_sha256"], ref["tools_sha256"]),
            "the supervisor, preflight, host-inventory, K17d verifier and this validator are the files the plan was made with")
    f.check("source.records", _same(source["records_sha256"], ref["records_sha256"]),
            "memorandum twin, decision register, K17d identity and audit and the scientific protocol record equal the checkout")


def _check_environment(plan, ref, f):
    env = plan["environment"]
    if not _exact_keys(f, "environment.pin", env, ("python", "numpy", "scipy", "thread_environment"), "environment"):
        return
    pins = all(_text(env[k]) and re.fullmatch(r"\d+(\.\d+){1,3}([a-z0-9+.]*)?", env[k].strip()) for k in ("python", "numpy", "scipy"))
    threads = env["thread_environment"]
    thread_ok = (isinstance(threads, dict) and set(threads) == set(THREAD_VARIABLES)
                 and all(isinstance(threads[k], str) and threads[k].isdigit() and int(threads[k]) >= 1 for k in THREAD_VARIABLES[:3])
                 and isinstance(threads["PYTHONHASHSEED"], str) and threads["PYTHONHASHSEED"].isdigit())
    f.check("environment.pin", pins and thread_ok, "exact python/numpy/scipy versions (no ranges or 'latest') and an explicit value for "
            f"{THREAD_VARIABLES}", "pinned", _short(env))
    if pins and thread_ok:
        mismatch = {k: (env[k], ref["environment"][k]) for k in ("python", "numpy", "scipy") if env[k] != ref["environment"][k]}
        if threads != ref["environment"]["threads"]:
            mismatch["thread_environment"] = (threads, ref["environment"]["threads"])
        f.check("environment.matches_host", not mismatch, "the pinned environment equals the environment the plan was checked in", {}, mismatch)


def _check_lock(plan, ref, f):
    lock = plan["lock"]
    if lock is None or ref["lock"] is None:
        f.blocked("lock.document", "no production lock document was supplied or created (create it with lock-create on a clean tree after the last "
                  "executor edit and after the DR-04 approval is committed: the gates JSON is hashed into the lock)")
        return
    if not _exact_keys(f, "lock.shape", lock, ("lock_fingerprint",), "lock") or not _hex64(lock["lock_fingerprint"]):
        f.fail("lock.shape", "lock must be {lock_fingerprint: hex64}", "hex64", _short(lock))
        return
    f.check("lock.verify", not ref["lock_problems"] and ref["lock"].get("lock_fingerprint") == lock["lock_fingerprint"],
            "the lock document verifies against the clean checkout and its fingerprint equals the plan's", [], (ref["lock_problems"] or [])[:6])


def _check_scientific(plan, ref, f):
    sci = plan["scientific"]
    if not _exact_keys(f, "scientific.shape", sci, ("decision_record", "d1_exposure", "d8_k17d", "k17d_verification"), "scientific"):
        return
    record, document = ref["decision_record"], ref["decision_record"]["document"]
    f.check("scientific.record", _same(sci["decision_record"], {"path": record["path"], "sha256": record["sha256"]}),
            "the plan cites the E12 decision register by path and content hash", record["sha256"], _short(sci["decision_record"]))
    gates_block = document.get("compute_gates") if isinstance(document.get("compute_gates"), dict) else {}
    compute_keys = ("full_generation", "full_gpu_training", "full_loko_sweep", "gpu_probe")
    f.check("scientific.ratified_no_execution", document.get("scientific_decisions_ratified") is True and document.get("execution_authorized") is False
            and document.get("production_authorized") is False and document.get("benchmark_complete") is False
            and all(isinstance(gates_block.get(k), dict) and "approval" in gates_block[k] and gates_block[k]["approval"] is None for k in compute_keys),
            "the E12 register ratifies the science and itself authorizes no compute (all four compute approvals present and null)")
    expected_d1, expected_d8 = _d1_from(document), _d8_from(document)
    d1 = sci["d1_exposure"]
    f.check("scientific.d1_exposure", _same(d1, expected_d1) and isinstance(d1, dict) and d1.get("existing_test_pristine") is False and _same(d1.get("mandatory_exclusion_rows"), {"test": 498, "test-matched": 148})
            and set(d1.get("exposed_test_ids", [])) <= set(range(ROLE_STARTS["test"], ROLE_STARTS["test"] + ROLE_COUNTS["test"]))
            and set(d1.get("exposed_matched_ids", [])) <= set(range(ROLE_STARTS["test-matched"], ROLE_STARTS["test-matched"] + ROLE_COUNTS["test-matched"])),
            "D-1 disclosure preserved: test not pristine, four exposed IDs inside their roles, 498/148 exclusion rows mandatory", expected_d1, d1)
    d8 = sci["d8_k17d"]
    f.check("scientific.d8_identity", _same(d8, expected_d8) and isinstance(d8, dict) and _same(d8.get("counts"), {"co_feed_missing": 35, "cross_feed_missing": 43, "headline": 500, "missing_total": 78, "sensitivity": 465}),
            "D-8 K17d identity preserved: 500 headline / 35 co-feed / 465 sensitivity / 43 cross-feed / 78 total", expected_d8, d8)
    report, accepted = sci["k17d_verification"], ref["k17d_verification"]
    f.check("scientific.k17d_verification", isinstance(report, dict) and _same(report, accepted) and report.get("generator_rederived") is True
            and report.get("observation_reads") == 0 and report.get("waveform_synthesis_calls") == 0 and report.get("execution_authorized") is False
            and report.get("production_metadata_cross_check") == "NOT_RUN_REQUIRES_SEPARATE_AUTHORIZATION",
            "the metadata-only K17d verification is complete (re-derived from the frozen generator, zero observation reads and waveform calls) and "
            "equals the checkout's; the production metadata cross-check stays NOT_RUN", _short(accepted.get("counts")), _short(report))
    bindings = document.get("k17d_bindings") if isinstance(document.get("k17d_bindings"), dict) else {}
    pairs = ("package_sha256", "source_sha256", "fingerprints", "audit_sha256")
    f.check("scientific.k17d_bindings", isinstance(report, dict) and all(bindings.get(k) not in (None, {}, "") and report.get(k) == bindings.get(k) for k in pairs),
            "source, package, audit and fingerprint hashes are present in the ratified bindings and equal the verification")


def _host_facts(report):
    facts = report["inventory"]
    cpu, mem = facts["cpu"], facts["memory"]
    cpus = min(v for v in (cpu["logical_cpus"], cpu["schedulable_cpus"], cpu["cgroup_cpu_quota"]) if v is not None)
    ram = None if mem["available_gib"] is None else min(v for v in (mem["available_gib"], mem["cgroup_limit_gib"]) if v is not None)
    return facts, cpus, ram, {row["path"]: row for row in facts["disks"]}


def _check_host_backup(plan, ref, f):
    """Host, working-root and backup facts. All embedded inventory facts are the plan author's JSON until ``host.remeasured`` passes."""
    host, working, backup, ceilings = plan["host"], plan["working"], plan["backup"], plan["ceilings"]
    if host is None or working is None or backup is None:
        f.blocked("host.inventory", "no measured generation-host inventory, working root or backup was declared (run scripts/b2_host_inventory.py "
                  "--role generation on the designated host; this checkout designates none)")
        f.blocked("backup.device", "no independently identified backup device was declared")
        return
    ok = _exact_keys(f, "host.shape", host, ("host_id", "inventory"), "host")
    ok &= _exact_keys(f, "working.shape", working, ("root", "storage_id"), "working")
    ok &= _exact_keys(f, "backup.shape", backup, ("root", "storage_id", "capacity_gb"), "backup")
    if not ok:
        return
    if not (_text(host["host_id"]) and _text(working["storage_id"]) and _text(backup["storage_id"])):
        f.fail("host.identity", "host_id and both storage ids must be non-empty strings", "strings", _short((host["host_id"], working["storage_id"], backup["storage_id"])))
        return
    work_path, backup_path = _safe_abs_path(working["root"]), _safe_abs_path(backup["root"])
    if work_path is None or backup_path is None or _volatile(working["root"]) or _volatile(backup["root"]):
        f.fail("plan.paths_host", "working and backup roots must be absolute, normalized paths without traversal and outside the volatile trees "
               f"{VOLATILE_PREFIXES}", "/abs/normalized/durable", _short((working["root"], backup["root"])))
        return
    f.ok("plan.paths_host", "working and backup roots are absolute, free of traversal and outside the volatile trees")
    nested = work_path == backup_path or work_path in backup_path.parents or backup_path in work_path.parents
    report = host["inventory"]
    shape = isinstance(report, dict) and report.get("schema") == host_inventory.SCHEMA and report.get("role") == "generation" \
        and report.get("read_only") is True and report.get("gpu_computation_performed") is False \
        and report.get("production_authorized") is False and report.get("benchmark_complete") is False
    if not f.check("host.inventory", shape, "a read-only B2-host-inventory/1 report for the generation role that authorizes nothing", "B2-host-inventory/1", _short(report)[:100]):
        return
    try:
        facts, cpus, ram, disks = _host_facts(report)
        collected, evaluated = _instant(facts.get("collected_at")), _instant(ref["evaluated_at"])
        libraries = facts["libraries"]
        environment = plan["environment"] if isinstance(plan["environment"], dict) else {}
        threads = environment.get("thread_environment") if isinstance(environment.get("thread_environment"), dict) else {}
        identity = (facts.get("node") == host["host_id"] and collected is not None and evaluated is not None
                    and timedelta(0) <= evaluated - collected <= INVENTORY_MAX_AGE
                    and facts.get("python") == environment.get("python") and libraries.get("numpy") == environment.get("numpy")
                    and libraries.get("scipy") == environment.get("scipy")
                    and all(facts["environment"].get(k) == threads.get(k) for k in THREAD_VARIABLES))
    except (KeyError, TypeError, ValueError, AttributeError) as error:
        f.fail("host.inventory", f"host inventory is malformed: {error}", "cpu/memory/disks/environment facts", _short(report)[:100])
        return
    f.check("host.identity", identity, "the inventory was taken on the declared host (node name equals host_id), no more than 14 days before and never after "
            "this evaluation, and its python, numpy, scipy and thread variables equal the plan's pins", "host_id/node/collected_at/pins agree",
            _short((facts.get("node"), host["host_id"], facts.get("collected_at"))))
    need_cpus = host_inventory.REQUIREMENTS["generation"]["logical_cpus"]
    f.check("host.cpu", cpus >= need_cpus, "usable CPUs cover the 4-vCPU generation profile", need_cpus, cpus)
    host_ram = ceilings["host_ram_gib"] if isinstance(ceilings, dict) and _num(ceilings.get("host_ram_gib")) else pre.PROPOSED_CEILINGS["host_ram_gib_generation"]
    f.check("host.ram", ram is not None and ram >= host_ram, "available RAM covers the host-RAM ceiling", host_ram, ram)
    work_row, backup_row = disks.get(working["root"]), disks.get(backup["root"])
    if work_row is None or backup_row is None:
        f.fail("backup.device", "the inventory must contain disk rows for the declared working and backup roots", [working["root"], backup["root"]], sorted(disks))
        return
    measured = (work_row.get("queried") == working["root"] and backup_row.get("queried") == backup["root"])
    f.check("host.roots_exist", measured, "both roots exist and were measured themselves (not an ancestor that may be another mount); create the empty "
            "directories before taking the inventory", "queried == root", _short((work_row.get("queried"), backup_row.get("queried"))))
    work_fs, backup_fs = work_row.get("fstype"), backup_row.get("fstype")
    norm = lambda value: value.strip().lower() if isinstance(value, str) and value.strip() else None            # noqa: E731
    f.check("host.filesystems", norm(work_fs) is not None and norm(backup_fs) is not None and norm(work_fs) not in VOLATILE_FSTYPES
            and norm(backup_fs) not in BACKUP_REFUSED_FSTYPES,
            "the inventory reports filesystem types; the working root is not a volatile or pseudo filesystem and the backup is neither volatile, pseudo, "
            "overlay nor read-only squashfs", {"working": "not in " + str(sorted(VOLATILE_FSTYPES)), "backup": "not in " + str(sorted(BACKUP_REFUSED_FSTYPES))},
            {"working": work_fs, "backup": backup_fs})
    reserve = ceilings["min_free_disk_gib"] if isinstance(ceilings, dict) and _num(ceilings.get("min_free_disk_gib")) else sup.PRODUCTION_CEILINGS["min_free_disk_gib"]
    need = required_free_gib(pre.PLAN_TOTAL, reserve)
    f.check("host.disk", _num(work_row.get("free_gib")) and work_row["free_gib"] >= need,
            f"free space at the working root covers {pre.PLAN_TOTAL} observations + 10 % + the {reserve} GiB reserve ({need:.1f} GiB)", round(need, 2), work_row.get("free_gib"))
    work_dev, backup_dev = work_row.get("device"), backup_row.get("device")
    independent = (type(work_dev) is int and type(backup_dev) is int and work_dev != backup_dev and not nested
                   and working["storage_id"].strip() != backup["storage_id"].strip())
    f.check("backup.device", independent, "backup is on a different device (st_dev), a different declared storage id and not nested in the working root "
            "(self-asserted ids; a bind mount or partition of the same disk can fool st_dev)", {"different": True}, {"working": work_dev, "backup": backup_dev, "nested": nested})
    gb = ceilings.get("backup_disk_gb") if isinstance(ceilings, dict) else None
    f.check("backup.capacity", _num(gb) and _num(backup["capacity_gb"]) and backup["capacity_gb"] >= gb
            and _num(backup_row.get("total_gib")) and backup["capacity_gb"] <= backup_row["total_gib"] * 2 ** 30 / 1e9 * 1.005 and
            _num(backup_row.get("free_gib")) and backup_row["free_gib"] * 2 ** 30 / 1e9 >= gb,
            "backup capacity and free space cover the backup ceiling and do not exceed the measured device",
            gb, _short((backup["capacity_gb"], backup_row.get("total_gib"), backup_row.get("free_gib"))))
    measured_here = ref.get("host_measurements") if isinstance(ref.get("host_measurements"), dict) else {}
    if measured_here.get("node") != host["host_id"]:
        f.blocked("host.remeasured", "the embedded inventory is the plan author's JSON; validate on the designated host (node name equal to host_id) so the "
                  "working and backup roots can be re-measured (device, filesystem type, free space) by this process")
    else:
        mine = measured_here.get("roots") if isinstance(measured_here.get("roots"), dict) else {}
        gb_needed = gb * 1e9 / 2 ** 30 if _num(gb) else None
        f.check("host.remeasured", all(isinstance(mine.get(root), dict) and mine[root].get("exists") is True and mine[root].get("device") == row.get("device")
                                       and norm(mine[root].get("fstype")) == norm(row.get("fstype")) for root, row in ((working["root"], work_row), (backup["root"], backup_row)))
                and _num(mine.get(working["root"], {}).get("free_gib")) and mine[working["root"]]["free_gib"] >= need
                and gb_needed is not None and _num(mine.get(backup["root"], {}).get("free_gib")) and mine[backup["root"]]["free_gib"] >= gb_needed,
                "this process re-measured both roots on the declared host: same device and filesystem type as the inventory, enough free space now",
                "device/fstype equal, free >= need", _short(mine))


def _check_ceilings(plan, f):
    ceilings = plan["ceilings"]
    if not _exact_keys(f, "ceilings.shape", ceilings, CEILING_KEYS, "ceilings"):
        return
    if not all(_num(ceilings[k]) and ceilings[k] > 0 for k in CEILING_KEYS):
        f.fail("ceilings.values", "every ceiling must be a finite positive number", "positive numbers", _short(ceilings))
        return
    proposals, est = proposed_ceilings(), estimated_hours()
    problems = []
    for key in ("wall_hours", "core_hours", "max_rss_gib", "max_failed_attempts_per_stage", "max_interruptions_per_stage"):
        if ceilings[key] > proposals[key]:
            problems.append(f"{key} {ceilings[key]} exceeds the proposed {proposals[key]} (the supervisor refuses ceilings above the proposals)")
    for key in ("max_failed_attempts_per_stage", "max_interruptions_per_stage"):
        if ceilings[key] != int(ceilings[key]):
            problems.append(f"{key} must be whole")
    if ceilings["min_free_disk_gib"] < proposals["min_free_disk_gib"]:
        problems.append(f"min_free_disk_gib {ceilings['min_free_disk_gib']} is below the proposed reserve {proposals['min_free_disk_gib']}")
    if ceilings["wall_hours"] < est["wall_high_hours"]:
        problems.append(f"wall_hours {ceilings['wall_hours']} cannot cover the high estimate {est['wall_high_hours']:.2f} h")
    if ceilings["core_hours"] < est["core_high_hours"]:
        problems.append(f"core_hours {ceilings['core_hours']} cannot cover the high estimate {est['core_high_hours']:.2f} core-h")
    if ceilings["max_rss_gib"] < MEASURED_GENERATOR_PEAK_GIB:
        problems.append(f"max_rss_gib {ceilings['max_rss_gib']} is below the measured single-process peak {MEASURED_GENERATOR_PEAK_GIB:.3f} GiB")
    if ceilings["host_ram_gib"] < proposals["host_ram_gib"]:
        problems.append(f"host_ram_gib {ceilings['host_ram_gib']} is below the proposed {proposals['host_ram_gib']}")
    if ceilings["backup_disk_gb"] < proposals["backup_disk_gb"]:
        problems.append(f"backup_disk_gb {ceilings['backup_disk_gb']} is below the proposed floor {proposals['backup_disk_gb']}")
    if ceilings["grace_s"] > sup.PRODUCTION_CEILING_LIMITS["grace_s"]:
        problems.append("grace_s exceeds the supervisor limit")
    f.check("ceilings.explicit", not problems, "explicit ceilings lie between the estimated requirement and the proposed ceilings (never above, never "
            "below what the plan needs)", [], problems[:6])
    f.check("ceilings.status", plan["ceilings_status"] in CEILINGS_STATUS and (plan["ceilings_status"] == CEILINGS_STATUS[0] or plan["authorization"] is not None),
            "ceilings_status names whether the numbers are proposals or recorded in a DR-04 record, and cannot claim a record that is absent",
            CEILINGS_STATUS, plan["ceilings_status"])


def _check_timing_and_stops(plan, f):
    f.check("timing.first_shard", _same(plan["timing"], sup.DEFAULT_TIMING) and plan["timing"].get("enabled") is True,
            "the first-shard timing gate is enabled with the E6 band as is (a production plan takes no timing options)", sup.DEFAULT_TIMING, plan["timing"])
    f.check("stop_rules.defined", _same(plan["stop_rules"], STOP_RULES), "interruption and stop rules are the fail-closed set (stop on a damaged shard, validator "
            "refusal, timing-gate failure or ceiling breach; resume only under an identical request; never delete evidence)", STOP_RULES, plan["stop_rules"])
    f.check("obligations.post_generation", _same(plan["post_generation_obligations"], OBLIGATIONS), "D-8 production-metadata cross-check and D-1 exposure "
            "disclosure remain mandatory later obligations", OBLIGATIONS, plan["post_generation_obligations"])


def _check_release_evidence(plan, f):
    evidence = plan["release_evidence"]
    if evidence is None:
        f.blocked("release.evidence", "no independent-review or exact-head CI evidence is attached (the release gate is a process step)")
        return
    if not _exact_keys(f, "release.evidence", evidence, RELEASE_KEYS, "release_evidence"):
        return
    review, ci, head = evidence["independent_review"], evidence["exact_head_ci"], plan["source"].get("git_commit") if isinstance(plan["source"], dict) else None
    ok = (isinstance(review, dict) and set(review) == {"path", "reviewed_head", "open_material_findings"} and _safe_repo_relative(review["path"]) is not None
          and review["reviewed_head"] == head and type(review["open_material_findings"]) is int and review["open_material_findings"] == 0
          and isinstance(ci, dict) and set(ci) == {"run_id", "job_id", "head_sha", "conclusion"} and ci["head_sha"] == head and ci["conclusion"] == "success"
          and type(ci["run_id"]) is int and type(ci["job_id"]) is int and evidence["self_asserted"] is True)
    f.check("release.evidence", ok, "independent review (no open material finding) and green CI refer to the exact plan head; both are self-asserted "
            "evidence, never an authorization", head, _short(evidence)[:140])


def _check_authorization(plan, ref, f):
    auth = plan["authorization"]
    gates, memo = ref["gates"], ref["memo"]
    if auth is None:
        f.blocked("authorization.dr04", "no DR-04 compute authorization record: scientific approval, K18/K17d/OBS-CANCEL-2 approvals, green CI and a "
                  "consistent plan are all evidence, none of them authorizes generation")
        return
    if not _exact_keys(f, "authorization.shape", auth, AUTH_KEYS, "authorization"):
        return
    f.check("authorization.basis", auth["schema"] == SCHEMA_AUTHORIZATION and auth["kind"] == "compute_generation" and auth["gate"] == "full_generation"
            and auth["stage"] == STAGE_ID and auth["basis"] == AUTH_BASIS and auth["observations"] == pre.PLAN_TOTAL and type(auth["observations"]) is int,
            "the record is a compute authorization for full_generation (21,350 observations) and cites no scientific approval or CI result as its basis",
            AUTH_BASIS, _short((auth["kind"], auth["gate"], auth["basis"])))
    path = _safe_repo_relative(auth["record"])
    text = ref["record_texts"].get(auth["record"]) if isinstance(auth["record"], str) else None
    record_ok = (path is not None and path.parts[0] == "docs" and auth["record"] not in SCIENTIFIC_RECORDS and _hex64(auth["record_sha256"])
                 and auth["record_sha256"] not in ref["scientific_record_sha256"] and ref["record_files"].get(auth["record"]) == auth["record_sha256"])
    f.check("authorization.record", record_ok, "the record is a tracked, committed document under docs/ (equal to HEAD's blob), is not one of the "
            "scientific-approval records or a copy of one, and its content hash matches", "committed docs record with matching sha256",
            _short((auth["record"], auth["record_sha256"])))
    blocks = _approval_blocks(text)
    expected_block = {"schema": APPROVAL_BLOCK_SCHEMA, "decision": "APPROVE", "approved_by": auth["approved_by"], "approved_plan_digest": auth["approved_plan_digest"],
                      "host_id": auth["host_id"], "expires_at": auth["expires_at"]}
    f.check("authorization.record_content", len(blocks) == 1 and _same(blocks[0], expected_block),
            "the approver's committed record holds exactly one fenced strict-JSON approval block with decision APPROVE and exactly this approver, approved-plan "
            "digest, host and expiry (the plan author cannot write them into a record the approver committed)", expected_block, _short(blocks)[:160])
    approved, expires, now = _instant(auth["approved_at"]), _instant(auth["expires_at"]), _instant(ref["evaluated_at"])
    register_date = _instant(str(ref["decision_record"]["document"].get("date")) + "T00:00:00+00:00")
    f.check("authorization.provenance", _text(auth["approved_by"]) and _text(auth["decision"]) and approved is not None and expires is not None
            and now is not None and register_date is not None and register_date <= approved < now <= expires and expires - approved <= AUTH_MAX_VALIDITY,
            "named approver, decision text, an approval instant not before the E12 register and in the past, an unexpired expiry and a validity of at most 30 days",
            "register<=approved_at<now<=expires_at<=approved_at+30d", _short((auth["approved_by"], auth["approved_at"], auth["expires_at"])))
    host, working, backup = plan["host"], plan["working"], plan["backup"]
    bound = (auth["plan_fingerprint"] == plan["plan_fingerprint"] == plan_fingerprint(plan) and auth["approved_plan_digest"] == approved_plan_digest(plan)
             and auth["git_commit"] == plan["source"]["git_commit"]
             and plan["lock"] is not None and auth["lock_fingerprint"] == plan["lock"].get("lock_fingerprint")
             and host is not None and working is not None and backup is not None and auth["host_id"] == host.get("host_id")
             and auth["working_storage_id"] == working.get("storage_id") and auth["backup_storage_id"] == backup.get("storage_id"))
    f.check("authorization.binding", bound, "the authorization is bound to this plan fingerprint and approved-plan digest, source commit, lock, host and both storage ids")
    ceilings = plan["ceilings"]
    mapped = {"wall_hours": ceilings.get("wall_hours"), "core_hours": ceilings.get("core_hours"), "working_disk_gib": ceilings.get("min_free_disk_gib"),
              "backup_disk_gb": ceilings.get("backup_disk_gb")}
    f.check("authorization.ceilings", _same_numbers(auth["ceilings"], mapped, AUTH_GATE_CEILINGS) and set(auth["ceilings"]) == set(AUTH_GATE_CEILINGS)
            and plan["ceilings_status"] == CEILINGS_STATUS[1],
            "the authorization restates exactly the plan's ceilings (working_disk_gib is the supervisor's min_free_disk_gib) and the plan marks them as recorded",
            mapped, auth["ceilings"])
    f.check("authorization.scope", _same(auth["grants"], ["full_generation"]) and isinstance(auth["does_not_grant"], list)
            and set(NOT_GRANTED) <= set(auth["does_not_grant"]), "it grants full_generation only and names what it does not grant (probe, training, LOKO, "
            "freeze, final evaluation, launch-flag change)", ["full_generation"], _short(auth["grants"]))
    gate = gates.get("decisions", {}).get("full_generation", {})
    twin = memo.get("decisions", {}).get("full_generation", {})
    recorded = gate.get("approval") if isinstance(gate.get("approval"), dict) else {}
    gate_ok = (gate.get("status") in pre.APPROVED_STATUSES and twin.get("status") == gate.get("status")
               and twin.get("approved_by") == recorded.get("approved_by") and twin.get("approved_at") == recorded.get("approved_at")
               and twin.get("record") == recorded.get("record")
               and not pre.approval_problems(recorded, True)
               and all(_same(recorded.get(k), auth[k]) for k in ("approved_by", "approved_at", "decision", "record"))
               and _same_numbers(recorded, auth["ceilings"], AUTH_GATE_CEILINGS))
    f.check("authorization.gate", gate_ok, "the full_generation gate in the readiness JSON and its memorandum twin carry the same approval; a "
            "record in the plan alone is not a gate", "gate approved with the same record", gate.get("status"))
    authorized, reasons = sup.authorization(gates, memo)
    f.check("authorization.supervisor_view", authorized is True, "the supervisor's own authorization() reads K18, K17d, OBS-CANCEL-2 and full_generation as "
            "approved with provenance and the twins consistent", [], reasons[:4])
    protocol_problems = e9.scientific_gate_problems(gates, ref["scientific_protocol"]) + e9.memo_twin_problems(gates, memo)
    f.check("authorization.scientific_prerequisites", not protocol_problems and gates.get("benchmark_complete") is False,
            "K18, K17d and OBS-CANCEL-2 carry the approval the scientific record names, memorandum twins agree and benchmark_complete=false "
            "(prerequisites, not authorization)", [], protocol_problems[:4])
    approved_elsewhere = [k for k in OTHER_COMPUTE_GATES for source in (gates, memo)
                          if source.get("decisions", {}).get(k, {}).get("status") != "NOT_AUTHORIZED"
                          or source.get("decisions", {}).get(k, {}).get("approval") not in (None, {})
                          or source.get("decisions", {}).get(k, {}).get("approved_by") not in (None, "")]
    f.check("authorization.scope_isolation", not approved_elsewhere, "the other compute gates (GPU training, LOKO) are exactly NOT_AUTHORIZED with no approval material in the "
            "readiness JSON and the memorandum while this DR-04 plan is validated; approving them is a separate decision that needs its own validation", [], sorted(set(approved_elsewhere)))


def structural_blockers():
    """Re-checked on every call. They cannot be satisfied by any plan: they describe this build."""
    blockers = []
    if sup.PRODUCTION_LAUNCH_ENABLED is not False:
        blockers.append({"id": "release.launch_flag_changed", "status": FAIL,
                         "message": "PRODUCTION_LAUNCH_ENABLED is not False: this validation is defined for the disabled build only; re-review required"})
    else:
        blockers.append({"id": "release.launch_disabled", "status": BLOCKED, "message": "PRODUCTION_LAUNCH_ENABLED is False: the supervisor validates "
                         "and journals bounded fixtures only (scripts/b2_production_supervisor.py)"})
    try:
        sup.stage_argv("known", sup.build_plan(Path("/nonexistent-e13-plan"), mode="production", groups_per_shard=pre.PRODUCTION["groups_per_shard"]),
                       Path("/nonexistent-e13-plan"))
    except sup.SupervisorError:
        blockers.append({"id": "release.no_unbounded_launcher", "status": BLOCKED, "message": "the supervisor's stage_argv refuses to build an unbounded "
                         "stage command; no production launcher exists"})
    else:
        blockers.append({"id": "release.boundary_changed", "status": FAIL, "message": "stage_argv built a production command: the unbounded-command "
                         "refusal was removed; re-review required"})
    cap_ok = sup.FIXTURE_MAX_GROUPS == 2
    blockers.append({"id": "release.fixture_cap", "status": BLOCKED if cap_ok else FAIL,
                     "message": "fixture runs stay capped at two groups per role" if cap_ok else f"FIXTURE_MAX_GROUPS is {sup.FIXTURE_MAX_GROUPS}, not 2"})
    try:
        e9.guard_execution("generation")
    except e9.ExecutionNotAuthorized:
        blockers.append({"id": "release.e9_guard", "status": BLOCKED, "message": "E9 guard_execution('generation') raises ExecutionNotAuthorized: "
                         "there is no runnable state"})
    except Exception as error:                         # an unknown action name or any other change is a changed boundary
        blockers.append({"id": "release.e9_guard_changed", "status": FAIL, "message": f"guard_execution behaved unexpectedly: {_short(error)}"})
    else:
        blockers.append({"id": "release.e9_guard_changed", "status": FAIL, "message": "guard_execution returned instead of raising"})
    return blockers


SECTIONS = (("plan.shape", _check_shape, 0), ("plan.inventory", _check_inventory, 0), ("plan.stages", _check_stages, 0),
            ("plan.generator_assumptions", _check_assumptions, 0), ("source", _check_source, 1), ("environment", _check_environment, 1),
            ("lock", _check_lock, 1), ("scientific", _check_scientific, 1), ("host_backup", _check_host_backup, 1), ("ceilings", _check_ceilings, 0),
            ("timing_stop", _check_timing_and_stops, 0), ("release_evidence", _check_release_evidence, 0), ("authorization", _check_authorization, 1))


def validate_plan(plan, reference):
    """Compare a plan with the reference. Returns a strict-JSON report whose verdict is always NO-GO."""
    f = _Findings()
    if not isinstance(plan, dict):
        f.fail("plan.shape", "the plan must be a JSON object", "object", type(plan).__name__)
    elif _depth_exceeds(plan):
        f.fail("plan.depth", f"the plan nests deeper than {MAX_DEPTH} levels", MAX_DEPTH, "deeper")
    else:
        hostile = _forbidden_keys(plan)
        if hostile:
            f.fail("plan.forbidden_key", "the plan declares execution, launcher, callback, group-limit or override fields; none exists in this build "
                   "and none can be added by a document", [], hostile[:8])
        shape_ok = _exact_keys(_Findings(), "plan.shape", plan, PLAN_KEYS, "plan")
        for name, func, wants_reference in SECTIONS:
            if not shape_ok and name != "plan.shape":
                continue
            try:
                func(plan, reference, f) if wants_reference else func(plan, f)
            except Exception as error:                  # hostile or malformed content must produce a finding, never a crash
                f.fail(name, f"section could not be evaluated: {type(error).__name__}", "well-formed section", _short(error))
    blockers = structural_blockers()
    counts = {PASS: 0, FAIL: 0, BLOCKED: 0}
    for item in [*f.items, *blockers]:
        counts[item["status"]] += 1
    consistent = counts[FAIL] == 0 and not any(i["status"] == BLOCKED for i in f.items)
    fingerprint = plan.get("plan_fingerprint") if isinstance(plan, dict) else None
    report = {"schema": SCHEMA_REPORT, "stage": STAGE_ID, "plan_status": DOCUMENT_OK if consistent else DOCUMENT_NOT_OK,
              "verdict": "NO-GO", "execution_permitted": False, "authorizes_nothing": True, "executor_implemented": False,
              "production_launch_enabled": sup.PRODUCTION_LAUNCH_ENABLED, "benchmark_complete": False,
              "plan_fingerprint": fingerprint if _hex64(fingerprint) else None,
              "evaluated_at": reference.get("evaluated_at"), "reference_head": reference.get("head"),
              "reference_sha256": sha256_of(reference), "counts": counts,
              "findings": f.items, "structural_blockers": blockers,
              "note": "A consistent plan is a statement about a document. It is not a permission: generation needs the researcher's DR-04 record in the gate, "
                      "a reviewed launcher that does not exist, and PRODUCTION_LAUNCH_ENABLED, none of which this tool can supply."}
    json.dumps(report, allow_nan=False)
    return report


# ---- command line (reads files; writes only an optional new --out file) --------------------------------------------

def _load_plan(path):
    with open(path, "rb") as stream:
        raw = stream.read(MAX_PLAN_BYTES + 1)
    if len(raw) > MAX_PLAN_BYTES:
        raise ValueError(f"plan larger than {MAX_PLAN_BYTES} bytes")
    try:
        return k17d_check._strict(raw)
    except RecursionError:
        raise ValueError("plan nesting too deep") from None


def _emit(value, out):
    text = json.dumps(value, indent=1, sort_keys=True, allow_nan=False) + "\n"
    if out:
        with open(out, "x", encoding="utf-8") as stream:
            stream.write(text)
    else:
        sys.stdout.write(text)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status").add_argument("--out")
    sub.add_parser("template").add_argument("--out")
    sub.add_parser("digest").add_argument("--plan", required=True)
    validate = sub.add_parser("validate")
    validate.add_argument("--plan", required=True)
    validate.add_argument("--lock")
    validate.add_argument("--out")
    args = parser.parse_args(argv)
    if getattr(args, "out", None) and Path(args.out).exists():
        parser.exit(2, f"error: {args.out} already exists; refusing to overwrite evidence\n")
    try:
        plan = _load_plan(args.plan) if args.command in ("validate", "digest") else None
        if args.command == "digest":
            if not isinstance(plan, dict):
                raise ValueError("the plan must be a JSON object")
            _emit({"plan_fingerprint": plan_fingerprint(plan), "approved_plan_digest": approved_plan_digest(plan), "approval_block_template": approval_block(plan),
                   "note": "a digest is not an approval; the approver writes the block into a committed docs/ record"}, None)
            return 0
        auth = plan.get("authorization") if isinstance(plan, dict) else None
        record_paths = [auth["record"]] if isinstance(auth, dict) and isinstance(auth.get("record"), str) else []
        roots = [plan[k]["root"] for k in ("working", "backup") if isinstance(plan, dict) and isinstance(plan.get(k), dict) and isinstance(plan[k].get("root"), str)]
        reference = collect_reference(lock_path=getattr(args, "lock", None), record_paths=record_paths, roots=roots)
        if args.command == "template":
            _emit(make_template(reference), args.out)
            return 0
        report = validate_plan(make_template(reference) if args.command == "status" else plan, reference)
        _emit(report, args.out)
    except (Exception, RecursionError) as error:          # any input problem is a usage error (2), never a traceback or a success
        parser.exit(2, f"error: {type(error).__name__}: {error}\n")
    return 3 if report["counts"][FAIL] else 4


if __name__ == "__main__":
    sys.exit(main())

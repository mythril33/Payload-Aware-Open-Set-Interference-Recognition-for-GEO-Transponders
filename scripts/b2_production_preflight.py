"""Bounded, read-only production preflight for the frozen B2/1 benchmark (E6, P29).

    python scripts/b2_production_preflight.py inventory
    python scripts/b2_production_preflight.py gates
    python scripts/b2_production_preflight.py lock-create --out production.lock.json
    python scripts/b2_production_preflight.py lock-verify --lock production.lock.json --require-clean
    python scripts/b2_production_preflight.py audit --stage known --root data/b2-feat --lock production.lock.json
    python scripts/b2_production_preflight.py transfer-manifest --root data/b2-feat --out transfer.json
    python scripts/b2_production_preflight.py drill --workdir runs/preflight-drill
    python scripts/b2_production_preflight.py checklist

Nothing here generates the full dataset, trains a model or approves a gate. ``audit`` only reads (hashing is
bounded by the artifact size), ``lock-create``/``transfer-manifest`` write one new file, ``drill`` generates
at most two groups of one stage in a scratch directory. Every status is PASS, FAIL (a verified defect or
mismatch), BLOCKED (needs a researcher decision, authorization, hardware or a measurement) or NOT_RUN.
It sits in ``scripts/`` on purpose: ``src/geosim/*.py`` is hashed into every artifact request and every
``src/**/*.py`` into checkpoint provenance, so a new source file would change frozen identities.
"""
from __future__ import annotations

import argparse
import importlib
import inspect
import json
import math
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from geosim.b2_dataset import _READ_ERRORS  # noqa: E402
from geosim.b2_protocol import (BASE_ROLES, LABELS, ROLE_COUNTS, ROLE_STARTS, B2Config, protocol_contract,  # noqa: E402
                                role_for_group, scenario_ids)
from geosim.b2_scenarios import MATCHED_LABELS, TEST_FAMILIES  # noqa: E402
from geosim.cancellation import CancellationConfig  # noqa: E402
from geosim.dataset import _file_hash, _fingerprint, _generator_provenance  # noqa: E402
from geosim.event_dataset import _strict_json  # noqa: E402

SCHEMA = "B2-production-preflight/1"
LOCK_SCHEMA = "B2-production-lock/1"
TRANSFER_SCHEMA = "B2-transfer-manifest/1"
PASS, FAIL, BLOCKED, NOT_RUN = "PASS", "FAIL", "BLOCKED", "NOT_RUN"
STATUSES = (PASS, FAIL, BLOCKED, NOT_RUN)
GATES_PATH = "docs/plan/b2_readiness_gates_2026-10-21.json"
MEMO_PATH = "docs/plan/b2_e5_decision_recommendations.json"
PLAN_PATH = "docs/plan/B2_E5_PRODUCTION_EXECUTION_PLAN.md"
FINDINGS_PATH = "docs/plan/b2_e6_audit_findings.json"
LOCKED_CONFIGS = ("configs/b2_base.json", "configs/cancellation.json", "configs/b2_feat.json", "pyproject.toml", GATES_PATH)
THREAD_ENV = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "PYTHONHASHSEED")

# Frozen production request choices (E5 execution plan): all roles, no group limit, four groups per shard.
PRODUCTION = {"groups_per_shard": 4, "window_shards": 4, "limit_groups": None, "known_protocol": "B2-feat/1",
              "canceller_version": "obs-cancel/1"}
# E5 plan inventory: (stage, role, groups, variants per group, observations).
PLAN_INVENTORY = (("B2-feat/1", "train", 1500, 8, 12000), ("B2-feat/1", "val-select", 150, 8, 1200),
                  ("B2-feat/1", "val-calib", 150, 8, 1200), ("B2-feat/1", "test", 500, 8, 4000),
                  ("B2-test/1", "test", 500, 5, 2500), ("B2-match/1", "test-matched", 150, 3, 450))
PLAN_TOTAL = 21350
# Measured/derived constants quoted by the E5 plan (docs/results/b2_production_budget.md, E1 notes).
BUDGET = {"float16_bytes_per_observation": 395264, "measured_artifact_bytes_per_observation": 406000,
          "seconds_per_observation": {"low": 3.8, "central": 4.4, "high": 5.0}, "cid_seconds_per_observation": 8.0,
          "cpu_to_wall_ratio": 300.2 / 262.0, "reserved_wall_hours": 36.0, "reserved_core_hours": 42.0,
          "documented_wall_hours": {"low": 23.0, "central": 26.6, "high": 30.2}, "wall_tolerance_hours": 0.25,
          "documented_storage_gb": 8.7}
# Proposed (NOT authorized) ceilings quoted by the E5 plan; PRODUCTION_AUTHORIZED stays false in this file.
PROPOSED_CEILINGS = {"authorized": False, "source": PLAN_PATH, "generation_wall_hours": 36, "generation_core_hours": 42,
                     "working_disk_gib": 25, "backup_disk_gb": 9, "generator_ram_gib_per_process": 2,
                     "host_ram_gib_generation": 8, "host_ram_gib_training": 16, "gpu_vram_gib_minimum": 8,
                     "gpu_vram_gib_preferred": 12, "main_training_gpu_hours": 6}
GATE_KEYS = ("K18", "K17d", "OBS-CANCEL-2", "full_generation", "full_gpu_training", "full_loko_sweep")
PENDING_STATUSES = ("PENDING_RESEARCHER", "NOT_AUTHORIZED")
APPROVED_STATUSES = ("APPROVED", "AUTHORIZED")
APPROVAL_FIELDS = ("approved_by", "approved_at", "decision", "record")
CEILING_FIELDS = ("wall_hours", "core_hours", "working_disk_gib", "backup_disk_gb")

STAGES = {"known": {"module": "geosim.b2_dataset", "samples": len(LABELS)},
          "test": {"module": "geosim.b2_test_dataset", "samples": len(TEST_FAMILIES), "role": "test",
                   "protocol": "B2-test/1"},
          "matched": {"module": "geosim.b2_matched_dataset", "samples": len(MATCHED_LABELS), "role": "test-matched",
                      "protocol": "B2-match/1"}}


def check(identifier, title, status, message, **evidence):
    if status not in STATUSES:
        raise ValueError(f"unknown status {status!r}")
    return {"id": identifier, "title": title, "status": status, "message": message, "evidence": evidence}


def verdict(checks):
    counts = {status: sum(item["status"] == status for item in checks) for status in STATUSES}
    overall = FAIL if counts[FAIL] else BLOCKED if counts[BLOCKED] else PASS if counts[PASS] else NOT_RUN
    return {"counts": counts, "verdict": overall}


def report(checks, **extra):
    """Strict-JSON report; the preflight never grants authorization and never completes the benchmark."""
    return {**extra, "schema": SCHEMA, "benchmark_complete": False, "production_authorized": False, **verdict(checks),
            "checks": checks}


def _read_json(path):
    return _strict_json(Path(path).read_text())


# ---- inventory and plan arithmetic -------------------------------------------------------------------------

def derive_inventory(groups_per_shard=PRODUCTION["groups_per_shard"]):
    """Role/stage inventory computed from the frozen code constants (never from documentation)."""
    rows = []
    stages = [("B2-feat/1", role, ROLE_COUNTS[role], len(LABELS)) for role in BASE_ROLES]
    stages += [("B2-test/1", "test", ROLE_COUNTS["test"], len(TEST_FAMILIES)),
               ("B2-match/1", "test-matched", ROLE_COUNTS["test-matched"], len(MATCHED_LABELS))]
    for stage, role, groups, variants in stages:
        start = ROLE_STARTS[role]
        rows.append({"stage": stage, "role": role, "groups": groups, "variants_per_group": variants,
                     "observations": groups * variants, "first_group": start, "last_group": start + groups - 1,
                     "shards": -(-groups // groups_per_shard), "max_loss_observations": groups_per_shard * variants})
    return rows


def parse_plan_inventory(markdown):
    """Rows ``| stage | groups | variants | observations | use |`` of the E5 plan's inventory table."""
    rows = []
    for line in markdown.splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) >= 4 and cells[0].startswith("B2-") and "/" in cells[0]:
            numbers = []
            for cell in cells[1:4]:
                digits = "".join(char for char in cell.split()[0] if char.isdigit()) if cell else ""
                numbers.append(int(digits) if digits else None)
            rows.append((cells[0].split()[0], *numbers))
    return rows


def check_inventory(plan_markdown=None, groups_per_shard=PRODUCTION["groups_per_shard"]):
    rows = derive_inventory(groups_per_shard)
    derived = {(row["stage"], row["role"]): (row["groups"], row["variants_per_group"], row["observations"])
               for row in rows}
    expected = {(stage, role): (groups, variants, observations)
                for stage, role, groups, variants, observations in PLAN_INVENTORY}
    total = sum(row["observations"] for row in rows)
    out = [check("inventory.counts", "Role/stage inventory equals the E5 plan table",
                 PASS if derived == expected and total == PLAN_TOTAL else FAIL,
                 f"{total} observations derived from frozen constants (plan {PLAN_TOTAL})",
                 derived={f"{s}:{r}": list(v) for (s, r), v in derived.items()}, total=total)]
    ranges = sorted((row["first_group"], row["last_group"], row["role"]) for row in rows
                    if row["stage"] != "B2-test/1")      # B2-test/1 deliberately shares the known test groups
    disjoint = all(left[1] < right[0] for left, right in zip(ranges, ranges[1:]))
    mapped = all(role_for_group(first) == role == role_for_group(last) for first, last, role in ranges)
    out.append(check("inventory.roles", "Role group ranges are disjoint, reserved and map back to their role",
                     PASS if disjoint and mapped and ranges[0][0] >= 3_000_000 else FAIL,
                     "train/val-select/val-calib/test/test-matched ids never overlap and sit above the legacy namespaces",
                     ranges=[list(item) for item in ranges]))
    from geosim import b2_matched_dataset, b2_test_dataset
    known_groups = {role: set(scenario_ids(role)) for role in BASE_ROLES}
    shared = (b2_test_dataset.ROLE == "test" and set(scenario_ids(b2_test_dataset.ROLE)) == known_groups["test"]
              and b2_matched_dataset.ROLE == "test-matched"
              and not set(scenario_ids(b2_matched_dataset.ROLE)) & set().union(*known_groups.values()))
    out.append(check("inventory.shared_test_groups", "B2-test/1 pairs with exactly the known test groups; B2-match/1 shares none",
                     PASS if shared else FAIL, "the 500 test-only groups are the known test groups; the 150 matched groups "
                     "are disjoint from every known role"))
    bound = {row["stage"] + ":" + row["role"]: row["max_loss_observations"] for row in rows}
    wanted_bound = {f"{stage}:{role}": groups_per_shard * variants for stage, role, _, variants, _ in PLAN_INVENTORY}
    out.append(check("inventory.interruption_bound", "Interruption loses at most one shard per stage",
                     PASS if bound == wanted_bound else FAIL,
                     f"{groups_per_shard} groups per shard bound the loss to {groups_per_shard * len(LABELS)} known / "
                     f"{groups_per_shard * len(TEST_FAMILIES)} test-only / {groups_per_shard * len(MATCHED_LABELS)} matched "
                     "observations", bound=bound))
    if plan_markdown is not None:
        parsed = {(stage, groups, variants, observations) for stage, groups, variants, observations
                  in parse_plan_inventory(plan_markdown)}
        wanted = {(stage, groups, variants, observations) for stage, _, groups, variants, observations in PLAN_INVENTORY}
        out.append(check("inventory.plan_document", "The E5 plan document states the same inventory table",
                         PASS if wanted <= parsed else FAIL,
                         "plan table rows parsed from markdown and compared with the code-derived inventory",
                         missing=sorted(map(list, wanted - parsed))))
    return out


def storage_estimate():
    shapes = {"spec": (2, 128, 512), "mask": (2, 512), "residual": (128, 512)}
    float16 = sum(2 * math.prod(shape) for shape in shapes.values())
    observations = sum(row["observations"] for row in derive_inventory())
    return {"float16_bytes_per_observation": float16, "observations": observations,
            "raw_array_bytes": float16 * observations,
            "estimated_artifact_bytes": BUDGET["measured_artifact_bytes_per_observation"] * observations}


def wall_hours(seconds):
    known = sum(row["observations"] for row in derive_inventory() if row["stage"] == "B2-feat/1")
    test_cid = ROLE_COUNTS["test"]
    test_other = ROLE_COUNTS["test"] * (len(TEST_FAMILIES) - 1)
    matched = ROLE_COUNTS["test-matched"] * len(MATCHED_LABELS)
    return (known * seconds + test_other * seconds + test_cid * BUDGET["cid_seconds_per_observation"]
            + matched * seconds) / 3600


def check_estimates():
    storage = storage_estimate()
    out = [check("estimates.storage", "Storage estimate reproduces from array shapes and the measured artifact size",
                 PASS if storage["float16_bytes_per_observation"] == BUDGET["float16_bytes_per_observation"]
                 and round(storage["estimated_artifact_bytes"] / 1e9, 1) == BUDGET["documented_storage_gb"] else FAIL,
                 f"{storage['float16_bytes_per_observation']} B float16 arrays/observation; "
                 f"{storage['estimated_artifact_bytes'] / 1e9:.2f} GB estimated artifact (documented "
                 f"{BUDGET['documented_storage_gb']} GB); estimate, not a full-scale measurement", **storage)]
    hours = {name: wall_hours(seconds) for name, seconds in BUDGET["seconds_per_observation"].items()}
    close = all(abs(hours[name] - BUDGET["documented_wall_hours"][name]) <= BUDGET["wall_tolerance_hours"] for name in hours)
    out.append(check("estimates.wall", "Single-process wall-time range reproduces from the per-observation costs",
                     PASS if close else FAIL,
                     "recomputed " + " / ".join(f"{hours[name]:.2f}" for name in hours) + " h versus documented "
                     + " / ".join(f"{BUDGET['documented_wall_hours'][name]}" for name in hours)
                     + f" h (tolerance {BUDGET['wall_tolerance_hours']} h; the documented test-only rows differ by up to "
                     "0.12 h from the same per-observation costs); estimate only, no full-scale generation was timed",
                     recomputed_hours=hours, documented_hours=BUDGET["documented_wall_hours"]))
    core = hours["high"] * BUDGET["cpu_to_wall_ratio"]
    out.append(check("estimates.reservation", "Reserved wall/core hours cover the high estimate with margin",
                     PASS if BUDGET["reserved_wall_hours"] >= hours["high"] * 1.15
                     and BUDGET["reserved_core_hours"] >= core * 1.15 else FAIL,
                     f"36 h vs {hours['high']:.1f} h high wall; 42 core-h vs {core:.1f} core-h high CPU "
                     "(extrapolated from a 60-observation matched profile)", high_core_hours=core))
    passes = 3 * 3 * 30 * ROLE_COUNTS["train"] * len(LABELS)
    loko = 7 * 3 * 30 * ROLE_COUNTS["train"] * len(LABELS)
    out.append(check("estimates.training_arithmetic", "Plan sample-pass arithmetic (3 views x 3 seeds x 30 epochs)",
                     PASS if (passes, loko) == (3_240_000, 7_560_000) else FAIL,
                     "arithmetic only: 30 epochs and 3 main seeds are plan assumptions, not frozen in a config",
                     main_sample_passes=passes, loko_sample_passes=loko))
    from geoml import data as geoml_data
    shard = PRODUCTION["groups_per_shard"] * len(LABELS)
    pool = inspect.signature(geoml_data.preprocess).parameters["time_pool"].default
    channels = geoml_data.VIEW_CHANNELS["dual_residual"]
    prepared = channels * (128 // pool) * 512 * 4                # float32 model input per observation
    out.append(check("estimates.window_memory", "E1 window memory arithmetic at four groups per shard",
                     PASS if round(shard * storage["float16_bytes_per_observation"] / 2 ** 20, 2) == 12.06
                     and shard * prepared / 2 ** 20 == 20.0 else FAIL,
                     f"{shard * storage['float16_bytes_per_observation'] / 2 ** 20:.2f} MiB raw and "
                     f"{shard * prepared / 2 ** 20:.1f} MiB preprocessed ({channels} channels, time_pool {pool}) per "
                     f"{shard}-observation shard", shard=shard))
    return out


# ---- researcher gates --------------------------------------------------------------------------------------

def _text(value):
    return isinstance(value, str) and bool(value.strip())


def _instant(value):
    try:
        return _text(value) and datetime.fromisoformat(value.strip().replace("Z", "+00:00")) is not None
    except ValueError:
        return False


def approval_problems(approval, needs_ceilings):
    """Structural checks only: the tool cannot judge whether a human really approved, only that a record exists."""
    if not isinstance(approval, dict):
        return ["no approval record"]
    problems = [f"{name} must be a non-empty string" for name in ("approved_by", "decision", "record")
                if not _text(approval.get(name))]
    if not _instant(approval.get("approved_at")):
        problems.append("approved_at must be an ISO-8601 timestamp")
    if needs_ceilings:
        for name in CEILING_FIELDS:
            value = approval.get(name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                problems.append(f"{name} must be a finite positive number")
    return problems


def check_gates(gates, memo):
    """Read-only: reports gate states, never changes them, and refuses an approval without provenance."""
    out = []
    flags = {"gates": gates.get("benchmark_complete"), "memo": memo.get("benchmark_complete")}
    out.append(check("gates.benchmark_complete", "benchmark_complete is false everywhere",
                     PASS if flags == {"gates": False, "memo": False} else FAIL, "scientific completion is never inferred",
                     **flags))
    for key in GATE_KEYS:
        record = gates.get("decisions", {}).get(key)
        twin = memo.get("decisions", {}).get(key)
        if not isinstance(record, dict) or not isinstance(twin, dict):
            out.append(check(f"gates.{key}", f"Gate {key}", FAIL, "gate missing from the readiness JSON or the memorandum"))
            continue
        status, approval = record.get("status"), record.get("approval")
        if status in PENDING_STATUSES:
            ambiguous = approval not in (None, {}) or twin.get("approved_by") or twin.get("approved_at")
            out.append(check(f"gates.{key}", f"Gate {key}", FAIL if ambiguous else BLOCKED,
                             "approval material is attached to a pending gate" if ambiguous
                             else f"{status}: needs an explicit researcher decision", gate_status=status))
        elif status in APPROVED_STATUSES:
            problems = approval_problems(approval, key.startswith("full_"))
            out.append(check(f"gates.{key}", f"Gate {key}", FAIL if problems else PASS,
                             "approved with provenance" if not problems else "approval is incomplete: " + "; ".join(problems),
                             gate_status=status))
        else:
            out.append(check(f"gates.{key}", f"Gate {key}", FAIL, f"unknown status {status!r}"))
        if twin.get("status") != status:
            out.append(check(f"gates.{key}.consistency", f"Gate {key} agrees with the E5 memorandum", FAIL,
                             f"readiness JSON says {status!r}, memorandum says {twin.get('status')!r}"))
    return out


# ---- source/environment/config lock ------------------------------------------------------------------------

def run_git(*args, repo=REPO):
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True).stdout.strip()


def tree_hashes(repo=REPO):
    root = Path(repo)
    files = sorted((root / "src").rglob("*.py")) + sorted((root / "src" / "geosim" / "data").glob("*"))
    return {str(path.relative_to(root)): _file_hash(path) for path in files if path.is_file()}


def environment():
    modules = {}
    for name in ("numpy", "scipy", "torch", "xgboost"):
        try:
            modules[name] = importlib.import_module(name).__version__
        except ImportError:
            modules[name] = None
    return {"python": platform.python_version(), "implementation": platform.python_implementation(),
            "platform": platform.platform(), **modules, "threads": {name: os.environ.get(name) for name in THREAD_ENV}}


def build_lock(repo=REPO, *, git=run_git, provenance=_generator_provenance, env=environment):
    root = Path(repo)
    try:
        commit = git("rev-parse", "HEAD", repo=root)
        dirty = git("status", "--porcelain", "--", "src", "configs", "pyproject.toml", repo=root)
        branch = git("rev-parse", "--abbrev-ref", "HEAD", repo=root)
    except (OSError, subprocess.SubprocessError):
        commit, dirty, branch = "unknown", "unknown", "unknown"
    generator = provenance()
    configs = {name: _file_hash(root / name) for name in LOCKED_CONFIGS}
    parsed = {"b2_config": B2Config.from_file(root / "configs/b2_base.json").to_dict(),
              "cancellation": CancellationConfig(**_read_json(root / "configs/cancellation.json")).to_dict()}
    body = {"schema": LOCK_SCHEMA, "benchmark_complete": False, "git": {"commit": commit, "branch": branch,
            "clean": dirty == ""}, "source_sha256": tree_hashes(root), "generator_provenance": generator,
            "generator_provenance_fingerprint": _fingerprint(generator), "configs_sha256": configs, "parsed": parsed,
            "environment": env(), "production": dict(PRODUCTION)}
    return {**body, "lock_fingerprint": _fingerprint(body)}


def verify_lock(lock, repo=REPO, *, require_clean=False, **overrides):
    """Return (problems); an empty list means the current checkout/environment equals the lock."""
    if not isinstance(lock, dict) or lock.get("schema") != LOCK_SCHEMA:
        return ["not a B2-production-lock/1 document"]
    body = {key: value for key, value in lock.items() if key != "lock_fingerprint"}
    problems = [] if _fingerprint(body) == lock.get("lock_fingerprint") else ["lock content does not match its own fingerprint"]
    now = build_lock(repo, **overrides)
    if require_clean and not (lock["git"]["clean"] and now["git"]["clean"]):
        problems.append("lock or current tree is not clean (uncommitted edits under src/configs/pyproject)")
    if lock["git"]["commit"] != now["git"]["commit"]:
        problems.append(f"git commit {now['git']['commit'][:12]} differs from locked {lock['git']['commit'][:12]}")
    for section, label in (("source_sha256", "source"), ("configs_sha256", "config"), ("generator_provenance", "generator")):
        locked, current = lock[section], now[section]
        for name in sorted(set(locked) | set(current)):
            if locked.get(name) != current.get(name):
                kind = "added" if name not in locked else "removed" if name not in current else "modified"
                problems.append(f"{label} file {kind}: {name}")
    for key in ("python", "numpy", "scipy"):
        if lock["environment"].get(key) != now["environment"].get(key):
            problems.append(f"environment {key} {now['environment'].get(key)!r} differs from locked "
                            f"{lock['environment'].get(key)!r}")
    if lock["environment"].get("threads") != now["environment"].get("threads"):
        problems.append("BLAS/hash-seed thread environment differs from the lock")
    if lock["parsed"] != now["parsed"]:
        problems.append("parsed physical or canceller configuration differs from the lock")
    return problems


# ---- artifact audit (read-only) ----------------------------------------------------------------------------

def _module(stage):
    return importlib.import_module(STAGES[stage]["module"])


def _expected_request(stage, request):
    """The request the generator would build today for this root; equality is its own resume condition."""
    module = _module(stage)
    config = B2Config(**request["config"])
    if stage == "known":
        cancellation = module._stage(request)[2]
        return module._request(config, request["roles"], request["limit_groups"], request["groups_per_shard"], cancellation)
    cancellation = module._cancellation_of(request)[0]
    return module._request(config, request["limit_groups"], request["groups_per_shard"], cancellation, request["known"])


def request_diff(expected, actual):
    diff = []
    for key in sorted(set(expected) | set(actual)):
        if expected.get(key) == actual.get(key):
            continue
        if isinstance(expected.get(key), dict) and isinstance(actual.get(key), dict) and key == "source_sha256":
            diff += [f"source_sha256:{name}" for name in sorted(set(expected[key]) | set(actual[key]))
                     if expected[key].get(name) != actual[key].get(name)]
        else:
            diff.append(key)
    return diff


def _layout(stage, request):
    if stage == "known":
        return [(role, request["scenario_groups"][role]) for role in request["roles"]]
    return [(STAGES[stage]["role"], request["scenario_groups"])]


def _tmp(name):
    return name.endswith((".tmp.npz", ".jsonl.tmp", ".json.tmp"))


def audit_artifact(root, stage, *, depth="checksum", lock=None, known=None, production=False, max_full=2):
    """Classify an artifact root without writing to it.

    States: NOT_STARTED, RESUMABLE (the generator would continue), COMPLETE, NEEDS_QUARANTINE (the generator would
    refuse because an uncommitted shard file exists; nothing is deleted here) and INVALID (modified, foreign,
    role-crossing or source-drifted data; use a fresh root).
    """
    if stage not in STAGES or depth not in ("structure", "checksum", "full"):
        raise ValueError("stage must be known/test/matched and depth structure/checksum/full")
    if max_full is not None and (isinstance(max_full, bool) or not isinstance(max_full, int) or max_full < 1):
        raise ValueError("max_full must be None or a positive integer (zero would silently skip deep verification)")
    root = Path(root)
    result = {"stage": stage, "root": str(root), "depth": depth, "state": None, "problems": [], "roles": {},
              "request_fingerprint": None, "request_summary": None, "hashed_bytes": 0, "leftover_temporaries": []}

    def problem(code, severity, message, **extra):
        result["problems"].append({"code": code, "severity": severity, "message": message, **extra})

    if not root.is_dir() or not any(root.iterdir()):
        result["state"] = "NOT_STARTED"
        return result
    try:
        _audit(result, problem, root, stage, depth, lock, known, production, max_full)
    except (AttributeError, KeyError, TypeError, IndexError, ValueError, OSError) as error:
        # Wrong-typed JSON (a list where an object is expected, ...) must not crash the audit into a false PASS or a traceback.
        problem("malformed_artifact", "fail", f"unexpected structure while auditing ({type(error).__name__}: {error}); "
                "the root is unusable")
        result["state"] = "INVALID"
    return result


def production_gaps(stage, request):
    """Names of the frozen production-request conditions this request does not meet (empty = production request)."""
    module = _module(stage)
    known_stage = stage == "known"
    canceller = module._stage(request)[2] if known_stage else module._cancellation_of(request)[0]
    gaps = []
    if request.get("limit_groups") is not None:
        gaps.append("limit_groups")
    if request.get("groups_per_shard") != PRODUCTION["groups_per_shard"]:
        gaps.append("groups_per_shard")
    if canceller is None or canceller.version != PRODUCTION["canceller_version"]:
        gaps.append("canceller")
    if known_stage and request.get("roles") != list(BASE_ROLES):
        gaps.append("roles")
    if known_stage and request.get("protocol") != PRODUCTION["known_protocol"]:
        gaps.append("protocol")
    return gaps


def _audit(result, problem, root, stage, depth, lock, known, production, max_full):
    module = _module(stage)
    try:
        request = _read_json(root / "request.json")
        expected = _expected_request(stage, request)
    except (OSError, ValueError, KeyError, TypeError) as error:
        problem("request_invalid", "fail", f"request.json is missing, malformed or not a B2 request: {error}")
        result["state"] = "INVALID"
        return result
    request_id = _fingerprint(request)
    result["request_fingerprint"] = request_id
    result["request_summary"] = {key: request.get(key) for key in ("protocol", "limit_groups", "groups_per_shard", "roles")}
    diff = request_diff(expected, request)
    if diff:
        problem("generator_would_refuse_resume", "fail",
                "the generator run today would reject this request (source, environment or content changed); "
                "use a fresh root", keys=diff[:20], n_keys=len(diff))
    if request.get("benchmark_complete") is not False or request.get("contract") != protocol_contract():
        problem("protocol_contract", "fail", "request does not carry the frozen B2/1 contract with benchmark_complete=false")
    if stage != "known" and request.get("protocol") != STAGES[stage]["protocol"]:
        problem("protocol_name", "fail", f"request protocol {request.get('protocol')!r} is not {STAGES[stage]['protocol']}")
    if production:
        gaps = production_gaps(stage, request)
        if gaps:
            problem("not_production_request", "fail", "request is not the full frozen production request "
                    "(all roles, no group limit, four groups per shard, obs-cancel/1 feature stage)", unmet=gaps)
    if lock is not None:
        mismatches = [name for name, same in (
            ("generator source", request.get("source_sha256") == lock["generator_provenance"]),
            ("numpy version", request.get("numpy_version") == lock["environment"]["numpy"]),
            ("scipy version", request.get("scipy_version") == lock["environment"]["scipy"]),
            ("physical config", request.get("config") == lock["parsed"]["b2_config"]),
            ("canceller config", (request.get("cancellation") or {}) == lock["parsed"]["cancellation"])) if not same]
        if mismatches:
            problem("lock_mismatch", "fail", "request differs from the production lock", fields=mismatches)
    try:
        calibration_ok = (module._calibration(root, request_id, request["protocol"]) if stage == "known"
                          else module._calibration(root, request))
        calibration_metadata = calibration_ok[0].to_dict()
    except (OSError, ValueError, KeyError, TypeError) as error:
        problem("calibration", "fail", f"receiver calibration is missing, modified or unbound: {error}")
        calibration_metadata = None
    committed, seen_groups = {}, {}
    for role, groups in _layout(stage, request):
        size = request["groups_per_shard"]
        count = -(-len(groups) // size)
        directory = root / role
        names = sorted(path.name for path in directory.iterdir()) if directory.is_dir() else []
        expected_names = {template.format(i=i) for i in range(count)
                          for template in ("part-{i:05d}.npz", "meta-{i:05d}.jsonl", "shard-{i:05d}.json")}
        leftovers = [name for name in names if _tmp(name)]
        stray = [name for name in names if name not in expected_names and not _tmp(name)]
        result["leftover_temporaries"] += [f"{role}/{name}" for name in leftovers]
        if stray:
            problem("unexpected_files", "fail", f"files outside the request in {role}", files=stray[:10])
        info = {"expected_shards": count, "committed": 0, "missing": 0, "orphan": [], "observations_committed": 0}
        if set(groups) != set(scenario_ids(role, request.get("limit_groups"))):
            problem("role_groups", "fail", f"{role} groups differ from the frozen reserved range")
        for index in range(count):
            part, meta, descriptor_path = (directory / f"part-{index:05d}.npz", directory / f"meta-{index:05d}.jsonl",
                                           directory / f"shard-{index:05d}.json")
            part_groups = groups[index * size:(index + 1) * size]
            if not descriptor_path.is_file():
                if part.exists() or meta.exists():
                    info["orphan"].append(index)
                    problem("orphan_shard", "blocked", f"{role} shard {index} has data files but no committed "
                            "descriptor; the generator refuses (move them to a quarantine directory, never delete)",
                            files=[path.name for path in (part, meta) if path.exists()])
                else:
                    info["missing"] += 1
                continue
            try:
                descriptor = _read_json(descriptor_path)
            except (OSError, ValueError) as error:
                problem("descriptor_unreadable", "fail", f"{role} shard {index}: {error}")
                continue
            samples = STAGES[stage]["samples"]
            if (descriptor.get("part") != part.name or descriptor.get("meta") != meta.name or descriptor.get("role") != role
                    or descriptor.get("scenario_seeds") != part_groups or descriptor.get("n_samples") != len(part_groups) * samples
                    or descriptor.get("request_fingerprint") != request_id):
                problem("descriptor_mismatch", "fail", f"{role} shard {index} descriptor is not bound to this request")
                continue
            hashes = descriptor.get("sha256", {})
            if depth != "structure":
                for path in (part, meta):
                    if not path.is_file():
                        problem("missing_file", "fail", f"{role} shard {index} lacks {path.name} after commit")
                    else:
                        result["hashed_bytes"] += path.stat().st_size
                        if hashes.get(path.name) != _file_hash(path):
                            problem("checksum_mismatch", "fail", f"{role} shard {index}: {path.name} was modified")
            elif not (part.is_file() and meta.is_file()):
                problem("missing_file", "fail", f"{role} shard {index} lacks data files after commit")
            for group in part_groups:
                try:
                    wrong = role_for_group(group) != role
                except ValueError:
                    wrong = True
                if wrong or group in seen_groups:
                    problem("role_isolation", "fail", f"group {group} crosses roles or repeats",
                            role=role, first_seen=seen_groups.get(group))
                seen_groups[group] = role
            committed.setdefault(role, {})[index] = descriptor
            info["committed"] += 1
            info["observations_committed"] += descriptor["n_samples"]
        result["roles"][role] = info
    _audit_manifest(result, root, stage, request, request_id, committed, problem)
    if (root / "manifest.json").is_file() and all(
            info["committed"] == info["expected_shards"] for info in result["roles"].values()):
        try:
            module._header(root)         # the loaders' own manifest/request/root-level validation
        except (*_READ_ERRORS, AttributeError) as error:
            problem("manifest_header", "fail", f"the generator's own manifest validation rejects this root: {error}")
    if depth == "full" and calibration_metadata is not None:
        _audit_full(result, root, stage, module, request, committed, calibration_metadata, max_full, problem)
    if known is not None and stage != "known":
        _audit_binding(root, stage, request, Path(known), problem)
    severities = {item["severity"] for item in result["problems"]}
    complete = (root / "manifest.json").is_file() and all(
        info["committed"] == info["expected_shards"] for info in result["roles"].values())
    result["state"] = ("INVALID" if "fail" in severities else "NEEDS_QUARANTINE" if "blocked" in severities
                      else "COMPLETE" if complete else "RESUMABLE")
    return result


def _audit_manifest(result, root, stage, request, request_id, committed, problem):
    path = root / "manifest.json"
    if not path.is_file():
        return
    try:
        manifest = _read_json(path)
    except (OSError, ValueError) as error:
        problem("manifest_unreadable", "fail", f"manifest.json: {error}")
        return
    full = all(info["committed"] == info["expected_shards"] for info in result["roles"].values())
    if manifest.get("request") != request or manifest.get("request_fingerprint") != request_id:
        problem("manifest_request", "fail", "manifest.json is not bound to request.json")
    elif not full:
        problem("manifest_incomplete", "fail", "manifest.json exists although shards are missing")
    else:
        listed = ({role: info.get("shards") for role, info in manifest.get("roles", {}).items()} if stage == "known"
                  else {STAGES[stage]["role"]: manifest.get("shards")})
        wanted = {role: [committed[role][i] for i in sorted(committed.get(role, {}))] for role in committed}
        if listed != wanted:
            problem("manifest_shards", "fail", "manifest.json lists shard descriptors that differ from the committed ones")


def _audit_full(result, root, stage, module, request, committed, calibration_metadata, max_full, problem):
    config = B2Config(**request["config"])
    for role, shards in committed.items():
        indices = sorted(shards)
        if max_full is not None and len(indices) > max_full:
            step = (len(indices) - 1) / max(max_full - 1, 1)
            indices = sorted({indices[round(i * step)] for i in range(max_full)})
        for index in indices:
            try:
                if stage == "known":
                    module._verify_part(root, request, role, index, shards[index], config, calibration_metadata)
                else:
                    module._verify_part(root, request, index, shards[index], config, calibration_metadata)
            except _READ_ERRORS as error:
                problem("deep_verification", "fail", f"{role} shard {index} fails the generator's own validator: {error}")
        result.setdefault("deep_verified", {})[role] = indices


def _audit_binding(root, stage, request, known, problem):
    try:
        manifest = _read_json(known / "manifest.json")
        binding = request["known"]
        same = {"known_request_fingerprint": binding["known_request_fingerprint"] == manifest["request_fingerprint"],
                "known_data_fingerprint": binding["known_data_fingerprint"] == _fingerprint(manifest),
                "known_calibration": binding["known_calibration"] == manifest["calibration"],
                "known_protocol": binding["known_protocol"] == manifest["protocol"] == PRODUCTION["known_protocol"]}
        if stage == "test":
            same["known_test_groups"] = binding["known_test_groups"] == manifest["roles"]["test"]["scenario_seeds"]
        else:
            same["known_roles"] = binding["known_roles"] == sorted(manifest["roles"])
        # The generators bind fingerprints, not sources: a stage built from different code still verifies.
        for key in ("source_sha256", "numpy_version", "scipy_version", "config", "cancellation", "fifth_channel"):
            same[f"cross_stage_{key}"] = request.get(key) == manifest["request"].get(key)
        failed = sorted(name for name, ok in same.items() if not ok)
        if failed:
            problem("known_binding", "fail", "stage is not bound to, or was generated from different code than, the "
                    "given known root", fields=failed)
    except (OSError, ValueError, KeyError, TypeError) as error:
        problem("known_binding", "fail", f"known root is not a usable binding: {error}")


def audit_check(result):
    status = {"INVALID": FAIL, "NEEDS_QUARANTINE": BLOCKED, "NOT_STARTED": NOT_RUN}.get(result["state"], PASS)
    committed = sum(info["committed"] for info in result["roles"].values())
    expected = sum(info["expected_shards"] for info in result["roles"].values())
    note = ""
    if result["state"] == "NOT_STARTED":
        note = "; nothing was verified (absent or empty root: check the path)"
    elif result["depth"] == "structure" and status == PASS:
        note = "; structure depth does not read checksums and cannot detect modified bytes"
    return check(f"artifact.{result['stage']}", f"{result['stage']} artifact root", status,
                 f"{result['state']}: {committed}/{expected} shards committed{note}", **result)


# ---- transfer manifest -------------------------------------------------------------------------------------

def create_transfer_manifest(root):
    root = Path(root)
    if not root.is_dir():
        raise ValueError("root is not a directory")
    files = [{"path": str(path.relative_to(root)), "bytes": path.stat().st_size, "sha256": _file_hash(path)}
             for path in sorted(root.rglob("*")) if path.is_file()]
    fingerprint = None
    if (root / "manifest.json").is_file():
        fingerprint = _fingerprint(_read_json(root / "manifest.json"))
    return {"schema": TRANSFER_SCHEMA, "benchmark_complete": False, "artifact_fingerprint": fingerprint,
            "n_files": len(files), "total_bytes": sum(item["bytes"] for item in files), "files": files}


def verify_transfer_manifest(manifest, root):
    """Problems (empty = identical): missing, extra, resized or modified files after a copy/restore."""
    if not isinstance(manifest, dict) or manifest.get("schema") != TRANSFER_SCHEMA:
        return ["not a B2-transfer-manifest/1 document"]
    root = Path(root)
    listed = {item["path"]: item for item in manifest["files"]}
    present = {str(path.relative_to(root)): path for path in sorted(root.rglob("*")) if path.is_file()}
    problems = [f"missing: {name}" for name in sorted(set(listed) - set(present))]
    problems += [f"extra: {name}" for name in sorted(set(present) - set(listed))]
    for name in sorted(set(listed) & set(present)):
        if present[name].stat().st_size != listed[name]["bytes"]:
            problems.append(f"size differs: {name}")
        elif _file_hash(present[name]) != listed[name]["sha256"]:
            problems.append(f"sha256 differs: {name}")
    return problems


# ---- host resources ----------------------------------------------------------------------------------------

def _meminfo_gib(path="/proc/meminfo"):
    try:
        for line in Path(path).read_text().splitlines():
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) / 2 ** 20
    except (OSError, ValueError, IndexError):
        pass
    return None


def atomic_rename_probe(directory):
    """Write, fsync and os.replace one scratch file on the target filesystem (the generator's commit primitive)."""
    probe = None
    try:
        probe = Path(tempfile.mkdtemp(prefix=".b2_preflight_probe_", dir=directory))      # never a pre-existing directory
        source, target = probe / "a.tmp", probe / "a"
        with open(source, "wb") as stream:
            stream.write(b"x" * 4096)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(source, target)
        descriptor = os.open(probe, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        return target.read_bytes() == b"x" * 4096
    except OSError:
        return False
    finally:
        if probe is not None:
            shutil.rmtree(probe, ignore_errors=True)


def probe_resources(root, ceilings=PROPOSED_CEILINGS, *, disk_usage=shutil.disk_usage, memory_gib=_meminfo_gib,
                    cpu_count=os.cpu_count, rename_probe=atomic_rename_probe):
    """Compare this host with the PROPOSED ceilings; an unrelated machine only proves it is the wrong host."""
    root = Path(root)
    target = root if root.exists() else root.parent
    free_gib = disk_usage(target).free / 2 ** 30
    ram = memory_gib()
    out = [check("resources.disk", "Working space for the output root",
                 PASS if free_gib >= ceilings["working_disk_gib"] else FAIL,
                 f"{free_gib:.1f} GiB free at {target} (proposed working space {ceilings['working_disk_gib']} GiB)",
                 free_gib=round(free_gib, 2)),
           check("resources.atomic_rename", "Atomic rename and fsync on the output filesystem",
                 PASS if rename_probe(target) else FAIL, "write, fsync and os.replace of a scratch file"),
           check("resources.ram", "Host RAM for one generator process",
                 NOT_RUN if ram is None else PASS if ram >= ceilings["host_ram_gib_generation"] else FAIL,
                 "MemAvailable unreadable" if ram is None else
                 f"{ram:.1f} GiB available (proposed {ceilings['host_ram_gib_generation']} GiB host RAM)"),
           check("resources.cpu", "CPU cores for one generator process at two BLAS threads",
                 PASS if (cpu_count() or 0) >= 2 else FAIL, f"{cpu_count()} logical CPUs"),
           check("resources.gpu", "GPU for the bounded throughput/VRAM probe", BLOCKED,
                 "no GPU access or probe authorization was provided; training numbers are assumptions")]
    return out


# ---- interruption and corruption drill ---------------------------------------------------------------------

def _flip_byte(path):
    data = bytearray(Path(path).read_bytes())
    data[len(data) // 2] ^= 0xFF
    Path(path).write_bytes(bytes(data))


def resume_drill(workdir, generate, load_arrays, *, groups=2):
    """Interrupt/corrupt copies of one tiny finished known root; ``generate(root)`` must build the same request.

    Returns a list of checks. The drill never touches the finished original and uses at most ``groups`` groups.
    """
    if groups != 2:
        raise ValueError("the drill is capped at exactly two groups of one role (two one-group shards)")
    work = Path(workdir)
    if work.exists() and any(work.iterdir()):
        raise ValueError("drill workdir must be new or empty (it writes five sub-directories)")
    work.mkdir(parents=True, exist_ok=True)
    original = work / "original"
    generate(original)
    reference = load_arrays(original)
    out = []

    def clone(name):
        target = work / name
        shutil.copytree(original, target)
        return target

    audit = audit_artifact(original, "known", depth="checksum")
    out.append(check("drill.complete", "A finished capped root audits as COMPLETE", PASS if audit["state"] == "COMPLETE" else FAIL,
                     f"state {audit['state']}", hashed_bytes=audit["hashed_bytes"]))

    killed = clone("killed")        # a kill after shard 0 was committed: no manifest, no shard 1 at all
    for name in ("manifest.json", "train/shard-00001.json", "train/part-00001.npz", "train/meta-00001.jsonl"):
        (killed / name).unlink()
    first = {path.name: _file_hash(path) for path in (killed / "train").glob("*-00000.*")}
    audit = audit_artifact(killed, "known")
    generate(killed)
    after = {path.name: _file_hash(path) for path in (killed / "train").glob("*-00000.*")}
    same = all(np_equal(reference[key], load_arrays(killed)[key]) for key in reference)
    out.append(check("drill.resume", "An interrupted root is RESUMABLE and the verified shard is never rewritten",
                     PASS if audit["state"] == "RESUMABLE" and first == after and same
                     and audit_artifact(killed, "known")["state"] == "COMPLETE" else FAIL,
                     f"pre-resume state {audit['state']}; shard 0 unchanged {first == after}; arrays equal {same}"))

    corrupt = clone("corrupt")
    _flip_byte(corrupt / "train/part-00000.npz")
    audit = audit_artifact(corrupt, "known")
    before = _file_hash(corrupt / "train/part-00000.npz")
    try:
        generate(corrupt)
        refused = False
    except ValueError:
        refused = True
    out.append(check("drill.corruption", "A flipped byte is INVALID and the generator refuses without repairing it",
                     PASS if audit["state"] == "INVALID" and refused
                     and before == _file_hash(corrupt / "train/part-00000.npz") else FAIL,
                     f"state {audit['state']}; generator refused {refused}"))

    orphan = clone("orphan")
    (orphan / "manifest.json").unlink()
    (orphan / "train/shard-00001.json").unlink()
    audit = audit_artifact(orphan, "known")
    try:
        generate(orphan)
        refused = False
    except ValueError:
        refused = True
    quarantine = orphan / "quarantine"
    quarantine.mkdir()
    for name in ("part-00001.npz", "meta-00001.jsonl"):
        shutil.move(str(orphan / "train" / name), str(quarantine / name))
    resumable = audit_artifact(orphan, "known")["state"]
    generate(orphan)
    same = all(np_equal(reference[key], load_arrays(orphan)[key]) for key in reference)
    out.append(check("drill.orphan", "An orphaned shard blocks the generator; quarantine restores a bit-equal resume",
                     PASS if audit["state"] == "NEEDS_QUARANTINE" and refused and resumable == "RESUMABLE" and same
                     else FAIL, f"state {audit['state']}; refused {refused}; after quarantine {resumable}; arrays equal {same}"))

    changed = clone("changed")
    try:
        generate(changed, groups_per_shard=2)
        refused = False
    except ValueError as error:
        refused = "request changed" in str(error)
    out.append(check("drill.request_lock", "A changed request is refused on a finished root", PASS if refused else FAIL,
                     "groups_per_shard changed from the locked request"))
    return out


def np_equal(left, right):
    return bool(np.array_equal(left, right))


def real_drill_hooks(groups=2):
    """Real-physics generator and loader for the CLI drill (feature stage, train role, <= two groups)."""
    from geosim import b2_dataset as known

    def generate(root, groups_per_shard=1):
        known.generate_b2_dataset(root, B2Config(), roles=("train",), limit_groups=groups,
                                  groups_per_shard=groups_per_shard, cancellation=CancellationConfig())

    def load(root):
        data = known.load_b2_split(root, "train")
        return {key: data[key] for key in ("spec", "mask", "label", "seed", "residual")}

    return generate, load


# ---- audit findings and checklist --------------------------------------------------------------------------

def load_findings(path=REPO / FINDINGS_PATH):
    data = _read_json(path)
    items = data["items"]
    ids = [item["id"] for item in items]
    if len(ids) != len(set(ids)) or data.get("schema") != "B2-E6-audit-findings/1":
        raise ValueError("audit findings must have unique ids and the B2-E6-audit-findings/1 schema")
    for item in items:
        if (item["status"] not in STATUSES or not item.get("evidence") or not item.get("message")
                or (item["status"] == PASS and not item.get("verified_by"))):
            raise ValueError(f"audit finding {item.get('id')!r} lacks a valid status, evidence, message or verifier")
    return data


def static_checks(repo=REPO):
    root = Path(repo)
    gates, memo = _read_json(root / GATES_PATH), _read_json(root / MEMO_PATH)
    checks = check_inventory((root / PLAN_PATH).read_text())
    checks += check_estimates()
    checks += check_gates(gates, memo)
    findings = load_findings(root / FINDINGS_PATH)
    checks += [check(item["id"], item["title"], item["status"], item["message"], evidence=item["evidence"],
                     verified_by=item.get("verified_by"), source="manual-audit") for item in findings["items"]]
    return checks


def render_markdown(checks):
    lines = ["# B2/1 production-readiness checklist (E6)", "",
             "Generated by `scripts/b2_production_preflight.py checklist`; `benchmark_complete=false`, "
             "`production_authorized=false`. PASS = verified here, FAIL = verified defect, gap or mismatch that engineering "
             "can fix without a researcher decision, BLOCKED = needs a researcher decision, authorization, hardware, a "
             "measurement or an operator action, NOT_RUN = not executed.", ""]
    summary = verdict(checks)
    lines.append("Counts: " + ", ".join(f"{name} {summary['counts'][name]}" for name in STATUSES)
                 + f" — overall **{summary['verdict']}**.")
    lines += ["", "| Status | ID | Item | Evidence |", "|---|---|---|---|"]
    for item in checks:
        message = " ".join(item["message"].split()).replace("|", "/")
        lines.append(f"| **{item['status']}** | `{item['id']}` | {item['title']} | {message} |")
    return "\n".join(lines) + "\n"


# ---- command line ------------------------------------------------------------------------------------------

def _write_new(path, text):
    """Exclusive creation: an existing file is never replaced, even by a racing writer."""
    try:
        with open(path, "x") as stream:
            stream.write(text)
    except FileExistsError:
        raise ValueError(f"{path} already exists; refusing to overwrite evidence") from None


def _emit(value, out=None):
    text = json.dumps(value, indent=1, allow_nan=False) + "\n"
    if out:
        _write_new(out, text)
    else:
        sys.stdout.write(text)


def _exit_code(summary, allow_blocked=False):
    """0 PASS, 3 FAIL, 4 BLOCKED (0 if allowed), 5 NOT_RUN: a verdict that verified nothing is not a success."""
    return {FAIL: 3, BLOCKED: 0 if allow_blocked else 4, NOT_RUN: 5}.get(summary["verdict"], 0)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--allow-blocked", action="store_true", help="exit 0 when the worst status is BLOCKED")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("inventory")
    sub.add_parser("gates")
    for name in ("lock-create", "lock-verify", "audit", "transfer-manifest", "resources", "drill", "checklist"):
        sub.add_parser(name)
    for name, sp in sub.choices.items():
        if name in ("lock-create", "audit", "transfer-manifest", "checklist", "resources", "inventory", "gates", "drill"):
            sp.add_argument("--out", help="write the strict-JSON result to a new file")
    sub.choices["lock-create"].add_argument("--allow-dirty", action="store_true")
    sub.choices["lock-verify"].add_argument("--lock", required=True)
    sub.choices["lock-verify"].add_argument("--require-clean", action="store_true")
    audit = sub.choices["audit"]
    audit.add_argument("--stage", required=True, choices=sorted(STAGES))
    audit.add_argument("--root", required=True)
    audit.add_argument("--lock")
    audit.add_argument("--known", help="known root a test/matched root must be bound to")
    audit.add_argument("--depth", default="checksum", choices=("structure", "checksum", "full"))
    audit.add_argument("--max-full-shards", type=int, default=2)
    audit.add_argument("--production", action="store_true", help="require the full frozen production request")
    tm = sub.choices["transfer-manifest"]
    tm.add_argument("--root", required=True)
    tm.add_argument("--verify", help="existing transfer manifest to verify --root against")
    sub.choices["resources"].add_argument("--root", required=True)
    sub.choices["drill"].add_argument("--workdir", required=True)
    sub.choices["checklist"].add_argument("--markdown", help="also write the rendered checklist to a new file")
    sub.choices["checklist"].add_argument("--host-root", help="add host-resource probes for this output root")
    args = parser.parse_args(argv)
    for target in (getattr(args, "out", None), getattr(args, "markdown", None)):
        if target and Path(target).exists():           # fail before any hashing; evidence is never overwritten
            parser.exit(2, f"error: {target} already exists; refusing to overwrite evidence\n")
    try:
        if args.command == "inventory":
            checks = check_inventory((REPO / PLAN_PATH).read_text()) + check_estimates()
        elif args.command == "gates":
            checks = check_gates(_read_json(REPO / GATES_PATH), _read_json(REPO / MEMO_PATH))
        elif args.command == "lock-create":
            lock = build_lock()
            if not lock["git"]["clean"] and not args.allow_dirty:
                raise ValueError("working tree has uncommitted edits under src/configs/pyproject; commit first "
                                 "or pass --allow-dirty (a dirty lock cannot be used with --require-clean)")
            _emit(lock, args.out)
            return 0
        elif args.command == "lock-verify":
            problems = verify_lock(_read_json(args.lock), require_clean=args.require_clean)
            checks = [check("lock.verify", "Checkout and environment equal the production lock",
                            FAIL if problems else PASS, "; ".join(problems[:10]) or "identical", problems=problems)]
        elif args.command == "audit":
            lock = _read_json(args.lock) if args.lock else None
            checks = [audit_check(audit_artifact(args.root, args.stage, depth=args.depth, lock=lock, known=args.known,
                                                 production=args.production, max_full=args.max_full_shards))]
        elif args.command == "transfer-manifest":
            if args.verify:
                problems = verify_transfer_manifest(_read_json(args.verify), args.root)
                checks = [check("transfer.verify", "Copied root equals the transfer manifest", FAIL if problems else PASS,
                                "; ".join(problems[:10]) or "identical", problems=problems[:100])]
            else:
                _emit(create_transfer_manifest(args.root), args.out)
                return 0
        elif args.command == "resources":
            checks = probe_resources(args.root)
        elif args.command == "drill":
            generate, load = real_drill_hooks()
            checks = resume_drill(args.workdir, generate, load)
        else:
            checks = static_checks()
            if args.host_root:
                checks += probe_resources(args.host_root)
            if args.markdown:
                _write_new(args.markdown, render_markdown(checks))
    except (ValueError, OSError, KeyError, TypeError) as error:
        parser.exit(2, f"error: {error}\n")
    result = report(checks)
    try:
        _emit(result, getattr(args, "out", None))
    except (ValueError, OSError) as error:
        parser.exit(2, f"error: {error}\n")
    # An audit's BLOCKED means the generator would refuse the root; only the informational commands may waive it.
    return _exit_code(result, args.allow_blocked and args.command in ("gates", "checklist", "inventory"))


if __name__ == "__main__":
    sys.exit(main())

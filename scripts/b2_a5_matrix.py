"""Fail-closed orchestration of the fixed P28 A5 pilot inventory.

Every selected invocation enters geoml.b2_a5, including completed ones: that
runner validates current data/source/frozen-model provenance before reuse.
Exit0 means all25 complete; exit3 means a completed explicit subset; exit1
means failure; exit2 a rejected budget; exit130 interruption. --plan runs none.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time


def inventory():
    entries = []
    def add(stage, perturbation, scope):
        entries.append({"name": f"{stage}_{perturbation}_{scope}", "stage": stage,
                        "perturbation": perturbation, "scope": scope,
                        "config": f"configs/b2_a5_{'matched_' if stage == 'matched' else ''}smoke.json"})
    add("known", "none", "both")
    for perturbation in ("shift_plus", "shift_minus", "drop_one", "phantom", "authorize_intruder", "stale_plan"):
        for scope in ("co_only", "cross_only", "both"):
            add("known", perturbation, scope)
    for perturbation in ("drop_one", "phantom", "authorize_intruder"):
        for scope in ("co_only", "both"):
            add("matched", perturbation, scope)
    return entries


def _write(path, value):
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    os.replace(temporary, path)


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _strict_json(text):
    def invalid(value):
        raise ValueError(f"non-finite JSON value: {value}")
    value = json.loads(text, object_pairs_hook=_pairs, parse_constant=invalid)
    json.dumps(value, allow_nan=False)
    return value


def _result(directory, invocation):
    path = directory / "results.json"
    sidecar = directory / "results.json.sha256"
    if not path.is_file() or not sidecar.is_file():
        raise FileNotFoundError("zero-exit invocation did not produce results.json and checksum")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if sidecar.read_text().strip() != digest:
        raise ValueError("result checksum does not match")
    value = _strict_json(path.read_text())
    if not isinstance(value, dict) or value.get("contract") != "B2-A5-eval/1" or value.get("benchmark_complete") is not False:
        raise ValueError("foreign contract or benchmark flag")
    config = value["configuration"]
    if not isinstance(config, dict):
        raise ValueError("result configuration must be an object")
    for key in ("stage", "perturbation", "scope"):
        if config[key] != invocation[key]:
            raise ValueError(f"result configuration differs from requested {key}")
    labels = ["adjacent_satellite", "unauthorized"] if invocation["stage"] == "matched" else ["clean", "unauthorized"]
    if config["n_groups"] != 2 or config["labels"] != labels:
        raise ValueError("result configuration differs from frozen pilot groups/classes")
    identity = value.get("experiment_fingerprint")
    if not isinstance(identity, str) or len(identity) != 64 or any(c not in "0123456789abcdef" for c in identity):
        raise ValueError("result lacks a complete experiment fingerprint")
    counts = value["counts"]
    if not isinstance(counts, dict):
        raise ValueError("result counts must be an object")
    for key, cap in (("physical_replays", 16), ("cancellation_evaluations", 24)):
        if type(counts[key]) is not int or not 0 <= counts[key] <= cap:
            raise ValueError(f"result exceeds P28 {key} cap")
    populations = value["populations"]
    if (not isinstance(populations, dict) or not isinstance(populations.get("not_applicable"), dict)
            or not isinstance(populations.get("blocked"), dict)):
        raise ValueError("result population/reason counts must be objects")
    selected, applied = populations["selected"], populations["applied"]
    reasons = list(populations["not_applicable"].values()) + list(populations["blocked"].values())
    if any(type(n) is not int or n < 0 for n in (selected, applied, *reasons)):
        raise ValueError("invalid population denominator")
    if applied + sum(reasons) != selected:
        raise ValueError("inconsistent applied/non-applicable/blocked denominators")
    views = value["views"]
    if not isinstance(views, dict) or any(not isinstance(v, dict) or type(v.get("available")) is not bool for v in views.values()):
        raise ValueError("result views must have explicit Boolean availability")
    return value, digest


def _totals(entries):
    completed = [entry for entry in entries if entry["status"] == "completed"]
    count = lambda status: sum(entry["status"] == status for entry in entries)
    return {"inventory": len(entries), "selected": sum(entry["selected"] for entry in entries),
            "completed": len(completed), "failed": count("failed"), "missing": count("missing"),
            "skipped": count("skipped"), "blocked": count("blocked_budget"),
            "pending": sum(entry["status"] in ("pending", "running", "skipped", "blocked_budget") for entry in entries),
            "applied_scenes": sum(entry["populations"]["applied"] for entry in completed),
            "not_applicable_scenes": sum(sum(entry["populations"]["not_applicable"].values()) for entry in completed),
            "blocked_scenes": sum(sum(entry["populations"]["blocked"].values()) for entry in completed),
            "unavailable_views": sum(entry["unavailable_views"] for entry in completed),
            "physical_replays": sum(entry["counts"]["physical_replays"] for entry in completed),
            "cancellation_evaluations": sum(entry["counts"]["cancellation_evaluations"] for entry in completed)}


def run_matrix(data, matched, runs, out, *, only=None, max_invocations=6,
               max_physical_replays=96, max_cancellations=144, max_wall_seconds=900,
               plan=False, runner=subprocess.run, clock=time.monotonic):
    entries = inventory()
    names = {entry["name"] for entry in entries}
    selection = names if only is None else set(only)
    if not selection <= names or (only is not None and len(selection) != len(only)) or not selection:
        raise ValueError("selection must contain unique names from the frozen 25-invocation inventory")
    for limit, upper in ((max_invocations, 25), (max_physical_replays, 400), (max_cancellations, 600)):
        if type(limit) is not int or not 0 <= limit <= upper:
            raise ValueError("overall budget must be a nonnegative integer within the bounded matrix")
    if type(max_wall_seconds) not in (int, float) or not math.isfinite(max_wall_seconds) or not 0 < max_wall_seconds <= 3600:
        raise ValueError("wall budget must be finite and in (0,3600] seconds")
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    started = clock()
    for entry in entries:
        entry.update(selected=entry["name"] in selection, status="pending" if entry["name"] in selection else "skipped",
                     reason=None if entry["name"] in selection else "not selected; remains pending, not evaluated")
    planned = {"invocations": len(selection), "physical_replays": 16 * len(selection),
               "cancellation_evaluations": 24 * len(selection)}
    report = {"schema": "B2-A5-matrix-status/1", "benchmark_complete": False,
              "matrix_status": "PLANNED", "matrix_complete": False, "selection_complete": False,
              "budgets": {"max_invocations": max_invocations, "max_physical_replays": max_physical_replays,
                          "max_cancellations": max_cancellations, "max_wall_seconds": max_wall_seconds},
              "planned_upper_bounds": planned, "invocations": entries,
              "resume_policy": "Every selected invocation calls geoml.b2_a5; current provenance validation precedes any completed-result or scene-state reuse",
              "notes": ["Logical work totals include verified reused state; no claim of recognition performance.",
                        "Skipped invocation slots are pending, not non-applicable samples."]}
    def save():
        report["elapsed_s"] = clock() - started
        report["totals"] = _totals(entries)
        _write(out / ("matrix_plan.json" if plan else "matrix_status.json"), report)
    rejected = (len(selection) > max_invocations or planned["physical_replays"] > max_physical_replays
                or planned["cancellation_evaluations"] > max_cancellations)
    if rejected:
        report["matrix_status"] = "BUDGET_REJECTED"
        for entry in entries:
            if entry["selected"]:
                entry.update(status="blocked_budget", reason="conservative selected upper bound exceeds explicit overall budget")
        save()
        return report, 2
    if plan:
        save()
        return report, 0
    interrupted = False
    for entry in entries:
        if not entry["selected"]:
            continue
        remaining = max_wall_seconds - (clock() - started)
        if remaining <= 0:
            entry.update(status="blocked_budget", reason="overall wall budget exhausted before invocation")
            save()
            continue
        directory = out / entry["name"]
        directory.mkdir(parents=True, exist_ok=True)
        attempt = 1
        while (directory / f"matrix_attempt_{attempt:04d}.log").exists():
            attempt += 1
        log = directory / f"matrix_attempt_{attempt:04d}.log"
        command = [sys.executable, "-m", "geoml.b2_a5", "--data", str(data), "--runs", str(runs),
                   "--out", str(directory), "--config", entry["config"], "--perturbation", entry["perturbation"],
                   "--scope", entry["scope"]]
        if entry["stage"] == "matched":
            command += ["--matched-data", str(matched)]
        entry.update(status="running", attempt=attempt, command=command, log_path=str(log), exit_code=None)
        report["matrix_status"] = "RUNNING"
        save()
        call_started = clock()
        with log.open("w") as stream:
            try:
                result = runner(command, stdout=stream, stderr=subprocess.STDOUT, timeout=remaining, check=False)
                entry["exit_code"] = result.returncode
                if result.returncode != 0:
                    entry.update(status="failed", reason=f"Python invocation exited {result.returncode}; see complete log")
                else:
                    value, digest = _result(directory, entry)
                    entry.update(status="completed", reason=None, results_sha256=digest,
                                 experiment_fingerprint=value["experiment_fingerprint"], populations=value["populations"],
                                 counts=value["counts"], unavailable_views=sum(not v.get("available") for v in value["views"].values()))
            except subprocess.TimeoutExpired:
                stream.write("\nMATRIX ERROR: Python invocation exceeded remaining overall wall budget\n")
                entry.update(status="failed", reason="overall wall timeout", exit_code=124)
            except KeyboardInterrupt:
                stream.write("\nMATRIX ERROR: invocation interrupted; re-entry must validate existing state\n")
                entry.update(status="failed", reason="interrupted", exit_code=130)
                interrupted = True
            except (OSError, ValueError, KeyError, TypeError) as error:
                stream.write(f"\nMATRIX ERROR: {error}\n")
                entry.update(status="missing" if isinstance(error, FileNotFoundError) else "failed", reason=str(error))
        entry["wall_seconds"] = clock() - call_started
        save()
        if interrupted:
            break
    completed = sum(entry["status"] == "completed" for entry in entries)
    report["selection_complete"] = completed == len(selection)
    report["matrix_complete"] = completed == len(entries)
    if interrupted:
        report["matrix_status"], code = "INTERRUPTED", 130
    elif not report["selection_complete"]:
        report["matrix_status"], code = "FAILED", 1
    elif report["matrix_complete"]:
        report["matrix_status"], code = "COMPLETE", 0
    else:
        report["matrix_status"], code = "PARTIAL", 3
    save()
    return report, code


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for name, default in (("data", "data/b2-feat-pilot"), ("matched", "data/b2-match-pilot"),
                          ("runs", "runs/b2-feat-pilot"), ("out", "runs/b2-a5-pilot")):
        parser.add_argument(name, nargs="?", default=default)
    parser.add_argument("--only", action="append", help="one exact inventory name; repeat to select a bounded subset")
    parser.add_argument("--max-invocations", type=int, default=6)
    parser.add_argument("--max-physical-replays", type=int, default=96)
    parser.add_argument("--max-cancellations", type=int, default=144)
    parser.add_argument("--max-wall-seconds", type=float, default=900)
    parser.add_argument("--plan", action="store_true", help="write matrix_plan.json only; no Python evaluation subprocess")
    args = vars(parser.parse_args(argv))
    try:
        report, code = run_matrix(**args)
    except (OSError, ValueError) as error:
        parser.exit(2, f"error: {error}\n")
    print(f"MATRIX_{report['matrix_status']} completed={report['totals']['completed']}/{report['totals']['inventory']} "
          f"pending={report['totals']['pending']} failed={report['totals']['failed']} missing={report['totals']['missing']}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())

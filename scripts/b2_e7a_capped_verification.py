"""Capped real-physics verification of the E7a supervisor (two groups per stage, one workdir, three supervisor starts).

    python scripts/b2_e7a_capped_verification.py --workdir W --out-dir docs/results [--allow-dirty-fixture]

It drives ``scripts/b2_production_supervisor.py`` through the real generator CLIs (no stand-in) on the frozen B2/1 physics:
  1. dry run (nothing created, exit 4 because the researcher authorization is BLOCKED);
  2. ``run --execute`` until the first known shard is committed, then SIGINT (exit 6, resumable);
  3. ``verify`` (exit 5: started, unfinished) and ``complete`` (refused);
  4. ``run --execute`` again until two heartbeats of the new attempt exist, then SIGKILL of the supervisor (its child must die);
  5. ``run --execute`` to the end (records ``supervisor_lost`` with an estimated charge, then finishes all three stages);
  6. ``verify`` and ``complete``.
It writes the raw ``journal.jsonl`` and ``journal.head`` byte for byte next to a JSON summary, so the committed journal can be
re-verified with ``Journal.load``. The cap is built in: ``--max-groups 2``, ``--groups-per-shard 1``; nothing here can run more.
This is an execution/recovery demonstration of a fixture, not a measurement of production behavior or recognition quality.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "b2_production_supervisor.py"
sys.path.insert(0, str(REPO / "scripts"))
import b2_production_supervisor as sup  # noqa: E402

CAP = ["--max-groups", "2", "--groups-per-shard", "1"]
HEARTBEAT_S = "5"
STARTUP_S = "6"


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def journal(work):
    records, _ = sup.Journal.read(Path(work) / "journal.jsonl")        # tolerant: it is being appended to
    return records


def wait_for(predicate, timeout_s, interval=0.5):
    end = time.time() + timeout_s
    while time.time() < end:
        if predicate():
            return True
        time.sleep(interval)
    return False


def render_markdown(summary):
    lock, journal = summary["lock"], summary["journal"]
    rows = "\n".join(f"| {a['attempt_id']} | {a['reason']} | {a['exit_code']} | {a['elapsed_s']} | {round(a['cpu_user_s'] + a['cpu_sys_s'], 1)} | "
                     f"{a.get('peak_rss_polled_kib', 0) // 1024} | {a.get('peak_rss_kib', 0) // 1024} | {'yes' if a.get('estimated') else 'no'} |"
                     for a in summary["attempts"])
    stages = "\n".join(f"| {stage} | {e['attempts']} | {e['observations']} | {e['attempt_wall_s']} | {e['cpu_s']} | "
                       f"{e['wall_s_per_observation_including_startup_and_repeated_restarts']} |"
                       for stage, e in summary["per_stage_attempts"].items())
    gates = "\n".join(f"| {g['attempt_id']} | {g['outcome']} | {round(g.get('s_per_observation', float('nan')), 2) if 's_per_observation' in g else '-'} | "
                      f"{g.get('startup_allowance_s', '-')} | {g.get('observations', '-')} |" for g in summary["timing_gates"])
    steps = "\n".join(f"| {i + 1} | {st['step']} | {st.get('exit', '-')} | {st['t_s']} |" for i, st in enumerate(summary["steps"]))
    return f"""# E7a supervisor - capped real-physics verification

Status: **fixture execution/recovery demonstration, not production behavior.** `benchmark_complete=false`, `production_complete=false`; no
researcher gate was touched. Two scenario groups per stage (80 observations in total: 64 known, 10 test-only, 6 matched), real generator
CLIs and the real physics chain (no stand-in), driven by [`scripts/b2_e7a_capped_verification.py`](../../scripts/b2_e7a_capped_verification.py)
through [`scripts/b2_production_supervisor.py`](../../scripts/b2_production_supervisor.py) ([P30](../plan/P30_b2_e7a_production_supervisor.md)).
Machine-readable twin: [`b2_e7a_supervisor_verification.json`](b2_e7a_supervisor_verification.json); the raw journal is committed byte for
byte ([`{journal['file']}`]({journal['file']}) + [`{journal['head_file']}`]({journal['head_file']}), sha256 `{journal['sha256'][:16]}...`,
{journal['records']} records, head `{journal['head'][:16]}...`) and verifies with `Journal.load`. Its argv/log fields hold scratch paths.

Lock: git commit `{lock['git_commit'][:12]}`, tree {'clean' if lock['git_clean'] else 'DIRTY (--allow-dirty-fixture)'}, lock `{lock['lock_fingerprint'][:16]}...`.

## Steps (one workdir, three supervisor starts)

| # | Step | Exit | t (s) |
|---|---|---|---|
{steps}

Exit codes: 4 = dry run BLOCKED (authorization), 6 = interrupted and resumable, 5 = verify found unfinished stages, 3 = `complete` refused,
-9 = the SIGKILLed supervisor, 0 = success. The SIGKILLed supervisor's child died with it; the next start recorded the missing end as
`supervisor_lost` and charged an upper-bound estimate (`estimated` below).

## Attempts

`peak (polled)` is the child's own `VmHWM` sampled while it ran (a lower bound); `peak (ru_maxrss)` is `wait4`'s figure, an **upper bound** that
also carries the supervisor's own memory at fork (so it is near-constant across attempts and must not be read as the child's peak).

| Attempt | Reason | Exit | Wall (s) | CPU (s) | Peak polled (MiB) | Peak ru_maxrss (MiB) | Estimated |
|---|---|---|---|---|---|---|---|
{rows}

Whole-attempt cost per stage (start-up and the repeated start-up of every restart included; **this is not a validation of the 3.8-5.0 s/observation band**):

| Stage | Attempts | Observations | Attempt wall (s) | CPU (s) | Wall per observation (s) |
|---|---|---|---|---|---|
{stages}

First-shard timing gate records (each subtracts a fixed `--timing-startup-s 6` from a 3-8 observation first shard, so the per-observation figure is
distorted; they show that the gate evaluates, not what a stage costs):

| Attempt | Outcome | s/observation after allowance | Allowance (s) | Observations |
|---|---|---|---|---|
{gates}

## Limitations (also in the JSON)

""" + "\n".join(f"- {text}" for text in summary["limitations"]) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--workdir", required=True, help="must not exist")
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--allow-dirty-fixture", action="store_true", help="record a dirty tree in the lock (off by default)")
    args = parser.parse_args(argv)
    work, out_dir = Path(args.workdir), Path(args.out_dir)
    if work.exists():
        raise SystemExit("the workdir must not exist")
    out_dir.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, OMP_NUM_THREADS="2", OPENBLAS_NUM_THREADS="2", MKL_NUM_THREADS="2", CUDA_VISIBLE_DEVICES="",
               PYTHONHASHSEED="0", MPLBACKEND="Agg")
    flags = ["--workdir", str(work), *CAP, "--heartbeat-s", HEARTBEAT_S, "--timing-startup-s", STARTUP_S]
    run_flags = ["run", *flags, "--execute", *(["--allow-dirty-fixture"] if args.allow_dirty_fixture else [])]
    steps, started = [], time.time()

    def step(name, **fields):
        steps.append({"step": name, "t_s": round(time.time() - started, 1), **fields})
        print(name, {k: v for k, v in fields.items() if k != "result"}, flush=True)

    def call(*arguments, timeout=3600):
        return subprocess.run([sys.executable, str(SCRIPT), *arguments], cwd=REPO, env=env, capture_output=True, text=True, timeout=timeout)

    def start(*arguments):
        return subprocess.Popen([sys.executable, str(SCRIPT), *arguments], cwd=REPO, env=env, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True)

    dry = call("plan", "--workdir", str(work), *CAP, "--heartbeat-s", HEARTBEAT_S, "--timing-startup-s", STARTUP_S)
    plan = json.loads(dry.stdout)
    step("dry_run", exit=dry.returncode, counts=plan["counts"], workdir_created=work.exists())
    assert dry.returncode == 4 and not work.exists()

    first = start(*run_flags)
    assert wait_for(lambda: list(work.glob("known/*/shard-*.json")), 1800), "no shard was committed"
    first.send_signal(signal.SIGINT)
    out, _ = first.communicate(timeout=300)
    step("interrupted_after_first_shard", exit=first.returncode, result=json.loads(out))
    assert first.returncode == sup.EXIT_INTERRUPTED

    verify = call("verify", "--workdir", str(work))
    step("verify_while_unfinished", exit=verify.returncode)
    complete = call("complete", "--workdir", str(work))
    step("complete_refused_while_unfinished", exit=complete.returncode, marker_written=(work / "completion.json").exists())

    second = start(*run_flags)
    restart_at = len(journal(work))
    assert wait_for(lambda: sum(r["event"] == "heartbeat" for r in journal(work)[restart_at:]) >= 2, 1800), "no heartbeats"
    pid = [r for r in journal(work) if r["event"] == "attempt_start"][-1]["pid"]
    second.kill()
    second.communicate(timeout=60)
    gone = wait_for(lambda: not sup.pid_alive(pid), 30)
    step("supervisor_sigkilled_mid_attempt", exit=second.returncode, child_pid=pid, child_gone=gone)
    assert gone

    third = start(*run_flags)
    out, err = third.communicate(timeout=7200)
    step("resumed_to_completion", exit=third.returncode, result=json.loads(out) if out.strip() else None)
    assert third.returncode == 0, (out, err)

    verify = call("verify", "--workdir", str(work))
    verified = json.loads(verify.stdout)
    step("verify_complete", exit=verify.returncode, all_stages_verified=verified["all_stages_verified"])
    complete = call("complete", "--workdir", str(work))
    marker = json.loads(complete.stdout)
    step("complete", exit=complete.returncode)

    records = journal(work)
    plan_run = json.loads((work / "run.json").read_text())["plan"]
    lock = json.loads((work / "lock.json").read_text())
    ends = [r for r in records if r["event"] == "attempt_end"]
    obs = {stage: sum(plan_run["expected_observations"][stage].values()) for stage in sup.STAGE_ORDER}
    by_stage = {}
    for r in ends:
        entry = by_stage.setdefault(r["stage"], {"attempts": 0, "attempt_wall_s": 0.0, "cpu_s": 0.0})
        entry["attempts"] += 1
        entry["attempt_wall_s"] += r["elapsed_s"]
        entry["cpu_s"] += r["cpu_user_s"] + r["cpu_sys_s"]
    for stage, entry in by_stage.items():
        entry.update(observations=obs[stage], attempt_wall_s=round(entry["attempt_wall_s"], 1), cpu_s=round(entry["cpu_s"], 1),
                     wall_s_per_observation_including_startup_and_repeated_restarts=round(entry["attempt_wall_s"] / obs[stage], 2))
    journal_copy = out_dir / "b2_e7a_supervisor_journal.jsonl"
    head_copy = out_dir / "b2_e7a_supervisor_journal.head"
    journal_copy.write_bytes((work / "journal.jsonl").read_bytes())
    head_copy.write_bytes((work / "journal.head").read_bytes())
    summary = {
        "schema": "B2-e7a-supervisor-verification/2", "benchmark_complete": False, "scope": "fixture", "production_complete": False,
        "statement": ("Capped real-physics execution/recovery demonstration of the supervisor: 2 groups per stage, three supervisor starts, one "
                      "operator interruption, one supervisor SIGKILL. Not production behavior, throughput, memory or recognition quality."),
        "commands": {"dry_run": ["python", "scripts/b2_production_supervisor.py", "plan", "--workdir", "W", *CAP, "--heartbeat-s", HEARTBEAT_S,
                                 "--timing-startup-s", STARTUP_S],
                     "run": ["python", "scripts/b2_production_supervisor.py", *run_flags[:1], "--workdir", "W", *run_flags[3:]],
                     "driver": ["python", "scripts/b2_e7a_capped_verification.py", "--workdir", "W", "--out-dir", "docs/results"]},
        "lock": {"git_commit": lock["git"]["commit"], "git_clean": lock["git"]["clean"], "lock_fingerprint": lock["lock_fingerprint"],
                 "dirty_fixture_allowed": args.allow_dirty_fixture, "environment": lock["environment"]},
        "steps": steps, "journal": {"file": journal_copy.name, "head_file": head_copy.name, "records": len(records),
                                    "sha256": sha256(journal_copy), "head": records[-1]["sha256"]},
        "plan_fingerprint": marker["plan_fingerprint"], "completion_marker": marker, "usage": sup.usage_from(records),
        "per_stage_attempts": by_stage,
        "attempts": [{k: r[k] for k in ("attempt_id", "stage", "reason", "exit_code", "elapsed_s", "cpu_user_s", "cpu_sys_s", "peak_rss_kib",
                                          "peak_rss_polled_kib", "supervisor_peak_rss_kib", "estimated") if k in r} for r in ends],
        "timing_gates": [{k: r[k] for k in r if k not in ("prev", "schema", "sha256", "seq")} for r in records if r["event"] == "timing_gate"],
        "limitations": [
            "The journal holds scratch paths in argv/log fields; its chain verifies as committed (Journal.load on the two committed files).",
            "peak_rss_kib is ru_maxrss, an upper bound that carries the supervisor's own peak at fork; peak_rss_polled_kib is a lower bound.",
            "The timing-gate figures subtract a fixed --timing-startup-s from 3-8 observation first shards; they are not per-observation costs and "
            "do not validate the 3.8-5.0 s/observation band. Use per_stage_attempts for whole-attempt wall per observation.",
            "A supervisor_lost attempt is charged by an upper-bound estimate (last heartbeat + one interval), not measured.",
            "Two groups per stage say nothing about production-size memory, throughput or disk.",
        ],
        "total_wall_s": round(time.time() - started, 1)}
    (out_dir / "b2_e7a_supervisor_verification.json").write_text(json.dumps(summary, indent=1, allow_nan=False) + "\n")
    (out_dir / "b2_e7a_supervisor_verification.md").write_text(render_markdown(summary))
    print("DONE", summary["total_wall_s"], flush=True)


if __name__ == "__main__":
    main()

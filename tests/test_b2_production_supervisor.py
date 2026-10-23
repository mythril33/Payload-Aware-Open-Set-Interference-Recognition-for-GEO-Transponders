"""E7a production supervisor: stage order, journaling, interruption, quarantine, drift, budgets and refusals.

Every run here is capped at two groups per stage and uses the stand-in child (tests/b2_supervisor_standin.py): fast
fake physics under the REAL generator CLIs, so shards, descriptors and manifests are genuine while no benchmark data
is produced. No test can start unbounded generation; several tests assert exactly that.
"""
import copy
import fcntl
import importlib.util
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pytest

from geosim import b2_dataset as known_ds

ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts" / "b2_production_supervisor.py"
STANDIN = ROOT / "tests" / "b2_supervisor_standin.py"
spec = importlib.util.spec_from_file_location("b2_production_supervisor", SCRIPT)
sup = importlib.util.module_from_spec(spec)
sys.modules["b2_production_supervisor"] = sup
spec.loader.exec_module(sup)
pre = sup.pre

TIMING = {"band_s_per_observation": [0.0001, 30.0], "startup_s": 0.5, "tolerance": 0.25}
CLI_FLAGS = ["--max-groups", "2", "--execute", "--allow-dirty-fixture", "--child-wrapper", str(STANDIN),
             "--timing-band", "0.0001", "30", "--timing-startup-s", "0.5"]


def strict(text):
    def reject(constant):
        raise ValueError(constant)
    return json.loads(text, parse_constant=reject)


def make(work, *, groups=2, ceilings=None, timing=None, **kwargs):
    plan = sup.build_plan(work, mode="fixture", max_groups=groups, groups_per_shard=1, ceilings=ceilings,
                          timing=dict(TIMING, **(timing or {})))
    kwargs.setdefault("poll_s", 0.05)
    return sup.Supervisor(work, plan, launcher=sup.wrapper_launcher(STANDIN), allow_dirty=True, **kwargs)


def records(work, event=None):
    found, problems = sup.Journal.read(Path(work) / "journal.jsonl")
    assert not problems, problems
    return [r for r in found if event is None or r["event"] == event]


def pid_gone(pid, timeout=10.0):
    end = time.time() + timeout
    while time.time() < end:
        if not sup.pid_alive(pid):
            return True
        time.sleep(0.1)
    return False


def flip_byte(path):
    data = bytearray(Path(path).read_bytes())
    data[len(data) // 2] ^= 0xFF
    Path(path).write_bytes(bytes(data))


def refingerprint(lock):
    body = {key: value for key, value in lock.items() if key != "lock_fingerprint"}
    return {**body, "lock_fingerprint": pre._fingerprint(body)}


def arrays(work, stage="known", role="train"):
    root = Path(work) / stage
    if stage == "known":
        data = known_ds.load_b2_split(root, role)
    elif stage == "test":
        from geosim import b2_test_dataset
        data = b2_test_dataset.load_b2_test_split(root)
    else:
        from geosim import b2_matched_dataset
        data = b2_matched_dataset.load_b2_matched_split(root)
    return {key: data[key] for key in ("spec", "mask", "seed", "residual")}


@pytest.fixture(scope="module")
def baseline(tmp_path_factory):
    work = tmp_path_factory.mktemp("supervisor") / "baseline"
    result = make(work).run()
    assert result["exit_code"] == 0 and result["status"] == "STAGES_COMPLETE", result
    return work


@pytest.fixture
def clone(baseline, tmp_path):
    target = tmp_path / "clone"
    shutil.copytree(baseline, target)
    return target


def cli(*args, env=None, **kwargs):
    environment = dict(os.environ, **(env or {}))
    return subprocess.Popen([sys.executable, str(SCRIPT), *args], cwd=ROOT, env=environment, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, **kwargs)


def wait_for(predicate, timeout=60.0, interval=0.1):
    end = time.time() + timeout
    while time.time() < end:
        if predicate():
            return True
        time.sleep(interval)
    return False


# ---- 1 stage order, journal, resources ------------------------------------------------------------------------

def test_stages_run_in_order_with_journaled_exit_codes_and_resources(baseline):
    starts = records(baseline, "attempt_start")
    assert [r["stage"] for r in starts] == ["known", "test", "matched"]
    modules = [[a for a in r["argv"] if a.endswith(".py")] for r in starts]
    assert all(m == [str(STANDIN)] for m in modules)
    for record in starts:
        assert record["argv"][record["argv"].index("--limit-groups") + 1] == "2"
        assert record["argv"][record["argv"].index("--groups-per-shard") + 1] == "1"
    ends = records(baseline, "attempt_end")
    assert [(r["stage"], r["exit_code"], r["reason"]) for r in ends] == [("known", 0, "exited"), ("test", 0, "exited"),
                                                                       ("matched", 0, "exited")]
    for r in ends:
        assert r["elapsed_s"] > 0 and r["peak_rss_kib"] > 0 and r["cpu_user_s"] + r["cpu_sys_s"] > 0
    events = [r["event"] for r in records(baseline)]
    assert events[0] == "supervisor_start" and events[-1] == "stages_complete" and "host_checked" in events
    assert [events.index(e) for e in ("stage_complete",)] and [r["stage"] for r in records(baseline, "stage_complete")] == list(sup.STAGE_ORDER)
    gates = records(baseline, "timing_gate")
    assert [r["stage"] for r in gates] == list(sup.STAGE_ORDER)
    assert all(r["outcome"] in ("within_band", "faster_than_band") for r in gates)
    assert sup.Journal.read(baseline / "journal.jsonl")[1] == []


def test_children_run_with_a_scrubbed_gpu_environment_and_unique_exclusive_logs(baseline):
    logs = sorted((baseline / "logs").glob("*.log"))
    assert [p.name for p in logs] == ["known-01.log", "matched-01.log", "test-01.log"]
    assert "CUDA_VISIBLE_DEVICES=''" in logs[0].read_text()


def test_the_inventory_is_exactly_the_planned_two_groups_per_stage(baseline):
    run = sup.load_run(baseline)
    assert run["plan"]["expected_observations"] == {
        "known": {"train": 16, "val-select": 16, "val-calib": 16, "test": 16}, "test": {"test": 10}, "matched": {"test-matched": 6}}
    assert run["plan"]["total_observations"] == 80 and run["plan"]["benchmark_complete"] is False
    assert run["plan"]["roots"] == {"known": "known", "test": "test", "matched": "matched"}      # relocatable identity


def test_a_later_stage_directory_before_its_turn_is_an_ordering_violation(tmp_path, monkeypatch):
    work = tmp_path / "w"
    monkeypatch.setenv("STANDIN_EXIT_AFTER_OBS", "3")
    assert make(work).run()["exit_code"] == 3                                              # known never completes
    monkeypatch.delenv("STANDIN_EXIT_AFTER_OBS")
    (work / "test").mkdir()
    (work / "test" / "stray.txt").write_text("x")                                           # test-only data before known is done
    before = len(records(work, "attempt_start"))
    result = make(work).run()
    assert result["exit_code"] == 3 and "ordering violation" in result["reasons"][0]
    assert len(records(work, "attempt_start")) == before


# ---- 2 interruption and continuation ----------------------------------------------------------------------------

@pytest.mark.parametrize("number", [signal.SIGINT, signal.SIGTERM])
def test_a_signal_stops_the_child_cleanly_and_the_run_continues_bit_equal(tmp_path, baseline, number):
    work = tmp_path / "interrupted"
    process = cli("run", "--workdir", str(work), *CLI_FLAGS, env={"STANDIN_OBS_DELAY_S": "0.4"})
    committed = lambda: bool(list(work.glob("known/*/shard-*.json")))                   # noqa: E731
    assert wait_for(committed, 90), process.poll()
    child_pid = records(work, "attempt_start")[0]["pid"]
    process.send_signal(number)
    process.communicate(timeout=60)
    assert process.returncode == sup.EXIT_INTERRUPTED
    assert pid_gone(child_pid)
    end = records(work, "attempt_end")[-1]
    assert end["reason"] == "interrupted" and end["stage"] == "known"
    assert records(work)[-1]["event"] == "interrupted"
    assert not (work / "known" / "quarantine").exists()
    audit = pre.audit_artifact(work / "known", "known")
    assert audit["state"] == "RESUMABLE" and 0 < sum(i["committed"] for i in audit["roles"].values()) < 8
    assert sup.Journal.read(work / "journal.jsonl")[1] == []
    with pytest.raises(sup.SupervisorError, match="not complete"):
        sup.complete_workdir(work)
    assert not (work / "completion.json").exists()
    assert cli("verify", "--workdir", str(work)).wait(timeout=60) == 5                   # started but unfinished is not a success
    again = cli("run", "--workdir", str(work), *CLI_FLAGS)
    out, err = again.communicate(timeout=240)
    assert again.returncode == 0, (out, err)
    restart = [r for r in records(work, "supervisor_start")]
    assert [r["restart"] for r in restart] == [False, True]
    assert sup.usage_from(records(work))["attempts"]["known"] == 2
    for stage in ("known", "test", "matched"):
        for role in (("train", "test") if stage == "known" else ("train",)):
            assert all(np.array_equal(a, b) for a, b in zip(arrays(work, stage, role).values(), arrays(baseline, stage, role).values()))
    assert sup.complete_workdir(work)["generation_complete"] is True


def test_killing_the_supervisor_kills_the_child_and_a_restart_records_the_loss(tmp_path):
    work = tmp_path / "killed"
    process = cli("run", "--workdir", str(work), *CLI_FLAGS, env={"STANDIN_START_DELAY_S": "120"})
    assert wait_for(lambda: (work / "journal.jsonl").exists() and records(work, "attempt_start"), 90)
    child_pid = records(work, "attempt_start")[0]["pid"]
    assert sup.pid_alive(child_pid)
    process.kill()
    process.communicate(timeout=30)
    assert pid_gone(child_pid), "PR_SET_PDEATHSIG should end the child with its supervisor"
    assert records(work)[-1]["event"] == "attempt_start"                                  # no end record: SIGKILL cannot be handled
    again = cli("run", "--workdir", str(work), *CLI_FLAGS)
    out, err = again.communicate(timeout=240)
    assert again.returncode == 0, (out, err)
    lost = [r for r in records(work, "attempt_end") if r["reason"] == "supervisor_lost"]
    assert len(lost) == 1 and lost[0]["exit_code"] is None and lost[0]["attempt_id"] == "known-01"


def test_a_live_unterminated_attempt_refuses_a_second_writer(clone):
    holder = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:
        journal = sup.Journal(clone / "journal.jsonl")
        journal.open()
        journal.append("attempt_start", stage="known", attempt_id="known-09", attempt=9, argv=["x", "--limit-groups", "1"],
                       pid=holder.pid, committed_observations=0, remaining_shards=1)
        result = make(clone).run()
        assert result["exit_code"] == 2 and "second writer" in result["reasons"][0]
        assert [r["event"] for r in records(clone)[-2:]] == ["attempt_start", "run_failed"]  # journaled, no new attempt
        assert len(records(clone, "attempt_start")) == 4
    finally:
        holder.kill()
        holder.wait()


def test_a_second_supervisor_on_the_same_workdir_is_refused(tmp_path):
    work = tmp_path / "busy"
    work.mkdir()
    with open(work / ".supervisor.lock", "a") as held:
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = make(work).run()
    assert result["exit_code"] == 2 and "another supervisor" in result["reasons"][0]


# ---- 3 corruption, 6 wrong role / duplicate group ------------------------------------------------------------------

def run_expecting_invalid(work, code=3):
    before = len(records(work))
    result = make(work).run()
    assert result["exit_code"] == code, result
    new = records(work)[before:]
    assert not [r for r in new if r["event"] == "attempt_start"], "no child may be started on an invalid root"
    return result, new


def test_a_corrupted_committed_shard_is_rejected_and_never_modified(clone):
    target = clone / "known" / "train" / "part-00000.npz"
    flip_byte(target)
    modified = target.read_bytes()
    result, new = run_expecting_invalid(clone)
    assert "INVALID" in result["reasons"][0] and "checksum_mismatch" in result["reasons"][0]
    audits = [r for r in new if r["event"] == "stage_audit"]
    assert audits[-1]["state"] == "INVALID" and new[-1]["event"] == "run_failed"
    assert target.read_bytes() == modified
    with pytest.raises(sup.SupervisorError):
        sup.complete_workdir(clone)


def test_a_committed_shard_from_the_wrong_role_is_rejected(clone):
    path = clone / "known" / "train" / "shard-00000.json"
    descriptor = json.loads(path.read_text())
    descriptor["scenario_seeds"] = [3_100_000]                                            # a val-select group inside train
    path.write_text(json.dumps(descriptor))
    result, new = run_expecting_invalid(clone)
    assert "descriptor_mismatch" in result["reasons"][0]


def test_duplicate_or_foreign_scenario_groups_in_the_request_are_rejected(clone):
    request = json.loads((clone / "known" / "request.json").read_text())
    request["scenario_groups"]["train"] = [request["scenario_groups"]["train"][0]] * 2    # a repeated group
    (clone / "known" / "request.json").write_text(json.dumps(request))
    result, new = run_expecting_invalid(clone)
    codes = {p["code"] for r in new if r["event"] == "stage_audit" for p in r["problems"]}
    assert {"role_groups", "generator_would_refuse_resume"} <= codes
    other = json.loads((clone / "test" / "request.json").read_text())
    assert other["scenario_groups"][0] // 100_000 == 32                                    # test stage groups stay in the test range


def test_a_modified_stage_marks_the_run_failed_even_when_only_a_later_stage_is_next(clone):
    shutil.rmtree(clone / "matched")                                                      # matched must be redone ...
    flip_byte(clone / "known" / "test" / "part-00001.npz")                                # ... but known is tampered first
    result, new = run_expecting_invalid(clone)
    assert not (clone / "matched").exists(), "nothing may be regenerated on top of a tampered earlier stage"


# ---- 4 orphan quarantine ------------------------------------------------------------------------------------------

def test_an_orphaned_shard_from_a_real_crash_is_quarantined_with_hashes_never_deleted(tmp_path, baseline, monkeypatch):
    monkeypatch.setenv("STANDIN_ORPHAN_AT", "1")
    monkeypatch.setenv("STANDIN_ONLY_STAGE", "known")
    monkeypatch.setenv("STANDIN_ONCE_MARKER", str(tmp_path / "fired"))
    work = tmp_path / "orphan"
    result = make(work).run()
    assert result["exit_code"] == 0, result
    ends = [r for r in records(work, "attempt_end") if r["stage"] == "known"]
    assert [(r["exit_code"], r["reason"]) for r in ends] == [(9, "exited"), (0, "exited")]
    assert records(work, "attempt_failed")[0]["exit_code"] == 9
    moved = records(work, "quarantine")
    assert len(moved) == 1 and len(moved[0]["files"]) == 2
    note = next((work / "known" / "quarantine").glob("*/QUARANTINE.json"))
    listed = json.loads(note.read_text())["files"]
    assert listed == moved[0]["files"]
    for item in listed:
        kept = work / "known" / item["to"]
        assert kept.is_file() and pre._file_hash(kept) == item["sha256"] and kept.stat().st_size == item["bytes"]
    states = [r["state"] for r in records(work, "stage_audit") if r["stage"] == "known"]
    assert states[:3] == ["NOT_STARTED", "NEEDS_QUARANTINE", "RESUMABLE"]
    assert all(np.array_equal(a, b) for a, b in zip(arrays(work).values(), arrays(baseline).values()))
    assert sup.usage_from(records(work))["attempts"]["known"] == 2


def test_quarantine_refuses_to_run_without_orphans_and_never_touches_invalid_roots(clone):
    audit = pre.audit_artifact(clone / "known", "known")
    journal = sup.Journal(clone / "journal.jsonl")
    journal.open()
    with pytest.raises(sup.SupervisorError, match="no orphan files"):
        sup.quarantine_orphans(clone / "known", audit, journal, "known")


# ---- 5 drift ----------------------------------------------------------------------------------------------------------

def rewrite_lock(work, mutate):
    path = work / "lock.json"
    lock = json.loads(path.read_text())
    mutate(lock)
    path.write_text(json.dumps(refingerprint(lock)))


@pytest.mark.parametrize("name,mutate,needle", [
    ("source", lambda l: l["source_sha256"].update({"src/geoml/train.py": "f" * 64}), "source file modified"),
    ("config", lambda l: l["configs_sha256"].update({"configs/cancellation.json": "f" * 64}), "config file modified"),
    ("generator", lambda l: l["generator_provenance"].update({sorted(l["generator_provenance"])[0]: "f" * 64}), "generator file modified"),
    ("numpy", lambda l: l["environment"].update(numpy="0.0.1"), "environment numpy"),
    ("python", lambda l: l["environment"].update(python="2.7.0"), "environment python"),
    ("commit", lambda l: l["git"].update(commit="0" * 40), "git commit"),
    ("parsed", lambda l: l["parsed"]["cancellation"].update(iterations=99), "parsed physical or canceller"),
])
def test_source_config_and_environment_drift_refuse_a_restart_before_anything_runs(clone, name, mutate, needle):
    before = (clone / "journal.jsonl").read_bytes()
    rewrite_lock(clone, mutate)
    result = make(clone).run()
    assert result["exit_code"] == 3 and "drift" in result["reasons"][0] and needle in result["reasons"][0], result
    assert (clone / "journal.jsonl").read_bytes() == before                               # a refusal before the journal is verified writes nothing


def test_thread_environment_drift_is_refused(clone, monkeypatch):
    monkeypatch.setenv("OMP_NUM_THREADS", "7" if os.environ.get("OMP_NUM_THREADS") != "7" else "3")
    result = make(clone).run()
    assert result["exit_code"] == 3 and "thread environment" in result["reasons"][0]


def test_drift_between_two_stages_stops_before_the_next_stage_starts(tmp_path, monkeypatch):
    work = tmp_path / "midrun"
    real = pre.verify_lock

    def drifting(lock, *args, **kwargs):
        done = (work / "journal.jsonl").exists() and any(r["event"] == "stage_complete" for r in records(work))
        return ["source file modified: src/geosim/dual.py"] if done else real(lock, *args, **kwargs)

    monkeypatch.setattr(pre, "verify_lock", drifting)
    result = make(work).run()
    assert result["exit_code"] == 3 and "drift" in result["reasons"][0]
    assert [r["stage"] for r in records(work, "attempt_start")] == ["known"]


def test_a_different_plan_is_refused_on_restart(clone):
    for kwargs in ({"groups": 1}, {"ceilings": {"wall_hours": 2.0}}, {"timing": {"tolerance": 0.5}}):
        result = make(clone, **kwargs).run()
        assert result["exit_code"] == 2 and "restart refused" in result["reasons"][0], kwargs
    assert make(clone).run()["exit_code"] == 0                                              # the identical plan is accepted


def test_a_damaged_journal_is_never_repaired_or_appended_to(clone):
    path = clone / "journal.jsonl"
    original = path.read_text()
    lines = original.splitlines()
    tampered = json.loads(lines[2])
    tampered["stage"] = "matched"
    for broken in ("\n".join([*lines[:2], json.dumps(tampered), *lines[3:]]) + "\n",         # content changed
                   "\n".join(lines[:5] + lines[6:]) + "\n",                                    # a record removed
                   original + '{"seq": 99',                                                    # torn last line
                   original.replace("\n", "\n\n", 1)):                                         # blank line injected
        path.write_text(broken)
        result = make(clone).run()
        assert result["exit_code"] == 2 and "journal is damaged" in result["reasons"][0]
        assert path.read_text() == broken
    path.write_text(original)
    assert make(clone).run()["exit_code"] == 0


def test_a_workdir_without_run_json_is_not_adopted(tmp_path):
    work = tmp_path / "foreign"
    work.mkdir()
    (work / "something.txt").write_text("x")
    result = make(work).run()
    assert result["exit_code"] == 2 and "no run.json" in result["reasons"][0]
    assert not (work / "run.json").exists() and not (work / "journal.jsonl").exists()


# ---- 7 budgets, slow first shard -----------------------------------------------------------------------------------

def last_end(work):
    return records(work, "attempt_end")[-1]


@pytest.mark.parametrize("case", ["wall", "cpu", "rss"])
def test_a_live_ceiling_overflow_terminates_the_child_and_fails_the_run(tmp_path, monkeypatch, case):
    env, ceilings, reason = {
        "wall": ({"STANDIN_OBS_DELAY_S": "0.5"}, {"wall_hours": 0.0006}, "timeout"),
        "cpu": ({"STANDIN_BURN_CPU_S": "30"}, {"core_hours": 0.0006}, "cpu_limit"),
        "rss": ({"STANDIN_ALLOC_MB": "900", "STANDIN_START_DELAY_S": "30"}, {"max_rss_gib": 0.55}, "rss_limit")}[case]
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    work = tmp_path / case
    result = make(work, ceilings=ceilings, timing={"enabled": False, "band_s_per_observation": [0.0001, 0.001]}).run()
    assert result["exit_code"] == 3 and reason in result["reasons"][0], result
    end = last_end(work)
    assert end["reason"] == reason
    assert pid_gone(records(work, "attempt_start")[-1]["pid"])
    assert records(work)[-1]["event"] == "run_failed" and sup.Journal.read(work / "journal.jsonl")[1] == []
    assert records(work, "stage_complete") == []


def test_the_attempt_budget_bounds_retries_after_a_failing_child(tmp_path, monkeypatch):
    monkeypatch.setenv("STANDIN_EXIT_AFTER_OBS", "3")
    work = tmp_path / "attempts"
    result = make(work, ceilings={"max_attempts_per_stage": 2}).run()
    assert result["exit_code"] == 3 and "attempt budget exhausted" in result["reasons"][0]
    assert [r["exit_code"] for r in records(work, "attempt_end")] == [7, 7]
    assert sup.usage_from(records(work))["attempts"] == {"known": 2, "test": 0, "matched": 0}


def test_cumulative_wall_and_cpu_usage_survive_restarts(clone):
    usage = sup.usage_from(records(clone))
    assert usage["wall_s"] > 0 and usage["cpu_s"] > 0 and usage["open_attempt"] is None
    tight = make(clone, ceilings={"wall_hours": usage["wall_s"] / 3600 / 2})               # the same plan identity needs the old ceilings
    assert tight.run()["exit_code"] == 2


def test_low_free_disk_stops_the_run_before_a_child_is_started(tmp_path):
    work = tmp_path / "disk"
    supervisor = make(work, disk_usage=lambda path: type("U", (), {"free": 1 * 2 ** 20})())
    result = supervisor.run()
    assert result["exit_code"] == 3 and "disk" in result["reasons"][0]
    assert records(work, "attempt_start") == [] and records(work, "stage_start") == []


def test_free_disk_is_rechecked_before_each_attempt(tmp_path):
    work = tmp_path / "disk-late"
    state = {"calls": 0}

    def shrinking(path):
        state["calls"] += 1
        free = 50 * 2 ** 30 if state["calls"] <= 1 else 1024                                 # fine for the host check, gone before the attempt
        return type("U", (), {"free": free})()

    result = make(work, disk_usage=shrinking).run()
    assert result["exit_code"] == 3 and "free disk" in result["reasons"][0]
    assert records(work, "attempt_start") == []


def test_a_slow_first_shard_fails_the_timing_gate_and_stops_the_child(tmp_path, monkeypatch):
    monkeypatch.setenv("STANDIN_OBS_DELAY_S", "1.0")
    work = tmp_path / "slow"
    result = make(work, timing={"band_s_per_observation": [0.01, 0.05], "tolerance": 0.0, "startup_s": 4.0}).run()
    assert result["exit_code"] == 3 and "timing_gate" in result["reasons"][0]
    gate = records(work, "timing_gate")[0]
    assert gate["outcome"] in ("too_slow", "no_shard_before_deadline") and gate["band"] == [0.01, 0.05]
    assert last_end(work)["reason"] == "timing_gate" and pid_gone(records(work, "attempt_start")[0]["pid"])
    assert not (work / "test").exists()


def test_a_run_inside_the_band_passes_and_a_faster_one_is_only_flagged(tmp_path, monkeypatch):
    monkeypatch.setenv("STANDIN_OBS_DELAY_S", "0.05")
    fast = make(tmp_path / "fast", timing={"band_s_per_observation": [2.0, 3.0], "startup_s": 0.0}).run()
    assert fast["exit_code"] == 0
    assert {r["outcome"] for r in records(tmp_path / "fast", "timing_gate")} == {"faster_than_band"}


# ---- 8 exit-code propagation -----------------------------------------------------------------------------------------

def test_a_nonzero_child_exit_code_is_journaled_exactly_and_fails_the_run(tmp_path, monkeypatch):
    monkeypatch.setenv("STANDIN_EXIT_AFTER_OBS", "2")
    monkeypatch.setenv("STANDIN_EXIT_CODE", "42")
    work = tmp_path / "exit42"
    result = make(work, ceilings={"max_attempts_per_stage": 1}).run()
    assert result["exit_code"] == 3
    end = last_end(work)
    assert end["exit_code"] == 42 and end["reason"] == "exited" and "signal" not in end
    assert records(work, "attempt_failed")[0]["exit_code"] == 42
    assert records(work, "stage_complete") == []


def test_a_child_killed_by_a_signal_is_reported_as_the_signal(tmp_path, monkeypatch):
    monkeypatch.setenv("STANDIN_SELF_SIGNAL", str(int(signal.SIGKILL)))
    work = tmp_path / "sigkill"
    result = make(work, ceilings={"max_attempts_per_stage": 1}).run()
    end = last_end(work)
    assert result["exit_code"] == 3 and end["exit_code"] == -9 and end["signal"] == "SIGKILL"


def test_a_clean_exit_with_an_incomplete_root_is_a_failure(tmp_path):
    work = tmp_path / "lying"
    supervisor = make(work)
    real = supervisor.launcher
    supervisor.launcher = lambda stage, plan, w: [sys.executable, "-c", "import sys; sys.exit(0)", "--limit-groups", "1"]
    result = supervisor.run()
    assert result["exit_code"] == 3 and "exited 0 but the root is" in result["reasons"][0]
    assert last_end(work)["exit_code"] == 0 and real is not supervisor.launcher


# ---- 9 authorization / 10 no accidental production -------------------------------------------------------------------

def approved(real_gates, real_memo):
    gates, memo = copy.deepcopy(real_gates), copy.deepcopy(real_memo)
    record = {"approved_by": "researcher", "approved_at": "2026-10-30T00:00:00Z", "decision": "x", "record": "r"}
    for key in sup.PRODUCTION_GATES:
        status = "AUTHORIZED" if key == "full_generation" else "APPROVED"
        approval = dict(record, wall_hours=36, core_hours=42, working_disk_gib=25, backup_disk_gb=9) if key == "full_generation" else record
        gates["decisions"][key].update(status=status, approval=approval)
        memo["decisions"][key].update(status=status)
    return gates, memo


@pytest.fixture
def spy(monkeypatch):
    calls = []
    real = subprocess.Popen

    def guarded(argv, *args, **kwargs):
        if isinstance(argv, (list, tuple)) and argv and Path(str(argv[0])).name == "git":
            return real(argv, *args, **kwargs)                                              # the lock reads git state only
        calls.append(argv)
        raise AssertionError("a child process must not be spawned")

    monkeypatch.setattr(subprocess, "Popen", guarded)
    return calls


def test_the_committed_gates_do_not_authorize_and_synthetic_approvals_are_judged_structurally():
    gates, memo = pre._read_json(ROOT / pre.GATES_PATH), pre._read_json(ROOT / pre.MEMO_PATH)
    ok, reasons = sup.authorization(gates, memo)
    assert ok is False and len(reasons) == 4 and all("BLOCKED" in r for r in reasons)
    ok, reasons = sup.authorization(*approved(gates, memo))
    assert ok is True and reasons == []
    bad_gates, bad_memo = approved(gates, memo)
    bad_gates["decisions"]["K18"]["approval"].pop("approved_by")
    assert sup.authorization(bad_gates, bad_memo)[0] is False
    inconsistent_gates, inconsistent_memo = approved(gates, memo)
    inconsistent_memo["decisions"]["K17d"]["status"] = "PENDING_RESEARCHER"
    assert sup.authorization(inconsistent_gates, inconsistent_memo)[0] is False


def test_production_execution_is_refused_without_authorization_and_spawns_nothing(tmp_path, spy, capsys):
    work = tmp_path / "prod"
    code = sup.main(["run", "--workdir", str(work), "--production", "--execute"])
    out = strict(capsys.readouterr().out)
    assert code == 2 and out["status"] == "REFUSED" and "K18" in out["reasons"][0] and not work.exists() and spy == []


def test_production_execution_stays_refused_even_with_every_gate_approved(tmp_path, spy, capsys, monkeypatch):
    gates, memo = approved(pre._read_json(ROOT / pre.GATES_PATH), pre._read_json(ROOT / pre.MEMO_PATH))
    fake = tmp_path / "repo"
    (fake / "docs/plan").mkdir(parents=True)
    (fake / pre.GATES_PATH).write_text(json.dumps(gates))
    (fake / pre.MEMO_PATH).write_text(json.dumps(memo))
    monkeypatch.setattr(sup, "REPO", fake)
    work = tmp_path / "prod"
    assert sup.main(["run", "--workdir", str(work), "--production", "--execute"]) == 2
    assert "not implemented in this build" in strict(capsys.readouterr().out)["reasons"][0]
    monkeypatch.setattr(sup, "PRODUCTION_LAUNCH_ENABLED", True)                               # even a flipped constant ...
    assert sup.main(["run", "--workdir", str(work), "--production", "--execute"]) == 2        # ... does not create a launch path
    plan = sup.build_plan(work, mode="production", groups_per_shard=4)
    result = sup.Supervisor(work, plan).run()
    assert result["exit_code"] == 2 and not work.exists() and spy == []
    with pytest.raises(sup.SupervisorError, match="unbounded stage command"):
        sup.stage_argv("known", plan, work)


def test_run_without_execute_is_a_dry_run_that_creates_and_spawns_nothing(tmp_path, spy, capsys):
    work = tmp_path / "dry"
    code = sup.main(["run", "--workdir", str(work), "--max-groups", "2", "--child-wrapper", str(STANDIN)])
    out = strict(capsys.readouterr().out)
    assert code in (3, 4) and out["dry_run"] is True and not work.exists() and spy == []
    assert out["production_authorized"] is False and out["benchmark_complete"] is False
    commands = out["commands"]
    assert list(commands) == ["known", "test", "matched"]
    assert all(c[c.index("--limit-groups") + 1] == "2" for c in commands.values())
    assert any(c["id"] == "supervisor.authorization" and c["status"] == "BLOCKED" for c in out["checks"])


def test_plan_for_production_validates_but_offers_no_commands(tmp_path, spy, capsys):
    code = sup.main(["plan", "--workdir", str(tmp_path / "w"), "--production"])
    out = strict(capsys.readouterr().out)
    status = {c["id"]: c["status"] for c in out["checks"]}
    assert code != 0 and out["commands"] is None and out["plan"]["limit_groups"] is None
    assert status["supervisor.caps"] == pre.BLOCKED and status["supervisor.production_launch"] == pre.BLOCKED
    assert status["supervisor.authorization"] == pre.BLOCKED and spy == [] and not (tmp_path / "w").exists()


@pytest.mark.parametrize("value", [None, 0, 3, -1, True, 2.0, "2"])
def test_a_bounded_run_needs_one_or_two_groups(tmp_path, value):
    with pytest.raises(sup.SupervisorError, match="--max-groups"):
        sup.build_plan(tmp_path, mode="fixture", max_groups=value, groups_per_shard=1)


def test_plan_validation_rejects_unsafe_combinations(tmp_path):
    for kwargs in ({"mode": "production", "max_groups": 2, "groups_per_shard": 4},
                   {"mode": "production", "groups_per_shard": 1}, {"mode": "fixture", "max_groups": 2, "groups_per_shard": 3},
                   {"mode": "other"}, {"mode": "fixture", "max_groups": 1, "groups_per_shard": 1, "ceilings": {"wall_hours": -1}},
                   {"mode": "fixture", "max_groups": 1, "groups_per_shard": 1, "ceilings": {"nonsense": 1}},
                   {"mode": "fixture", "max_groups": 1, "groups_per_shard": 1, "ceilings": {"wall_hours": float("inf")}},
                   {"mode": "fixture", "max_groups": 1, "groups_per_shard": 1, "timing": {"band_s_per_observation": [5, 1]}},
                   {"mode": "fixture", "max_groups": 1, "groups_per_shard": 1, "timing": {"bogus": 1}}):
        with pytest.raises(sup.SupervisorError):
            sup.build_plan(tmp_path, **kwargs)
    assert sup.PRODUCTION_LAUNCH_ENABLED is False and sup.FIXTURE_MAX_GROUPS == 2


@pytest.mark.parametrize("argv", [["python", "-m", "geosim.b2_dataset", "--out", "x"],
                                  ["python", "--limit-groups", "3"], ["python", "--limit-groups", "0"],
                                  ["python", "--limit-groups", "many"], ["python", "--limit-groups"]])
def test_no_child_is_ever_spawned_without_a_small_group_limit(argv, spy, tmp_path):
    with pytest.raises(sup.SupervisorError):
        sup.assert_bounded(argv)
    with pytest.raises(sup.SupervisorError):
        sup.run_child(argv, cwd=str(tmp_path), env={}, log_path=tmp_path / "log", timeout_s=1, cpu_budget_s=1,
                      rss_limit_kib=1, grace_s=1, interrupted=lambda: False)
    assert spy == [] and not (tmp_path / "log").exists()


def test_every_command_the_supervisor_builds_is_bounded(tmp_path):
    plan = sup.build_plan(tmp_path, mode="fixture", max_groups=2, groups_per_shard=1)
    for stage in sup.STAGE_ORDER:
        argv = sup.stage_argv(stage, plan, tmp_path)
        sup.assert_bounded(argv)
        assert argv[2] == sup.MODULES[stage] and ("--known" in argv) == (stage != "known")


# ---- completion, status ------------------------------------------------------------------------------------------------

def test_completion_is_written_once_only_for_a_verified_complete_scope(clone):
    marker = sup.complete_workdir(clone)
    assert marker["generation_complete"] is True and marker["scope"] == "fixture"
    assert marker["production_complete"] is False and marker["benchmark_complete"] is False
    assert marker["production_authorized"] is False and marker["observations"]["known"]["train"] == 16
    assert set(marker["stage_manifest_fingerprints"]) == set(sup.STAGE_ORDER)
    strict((clone / "completion.json").read_text())
    with pytest.raises(sup.SupervisorError, match="already exists"):
        sup.complete_workdir(clone)


@pytest.mark.parametrize("damage", ["missing_stage", "missing_manifest", "missing_role", "short_inventory", "no_final_record"])
def test_completion_is_refused_while_any_stage_role_or_manifest_is_missing(clone, damage):
    if damage == "missing_stage":
        shutil.rmtree(clone / "matched")
    elif damage == "missing_manifest":
        (clone / "test" / "manifest.json").unlink()
    elif damage == "missing_role":
        shutil.rmtree(clone / "known" / "val-calib")
    elif damage == "short_inventory":
        run = json.loads((clone / "run.json").read_text())
        run["plan"]["expected_observations"]["known"]["train"] = 24
        run["plan_fingerprint"] = sup.digest(run["plan"])
        (clone / "run.json").write_text(json.dumps(run))
    else:
        lines = (clone / "journal.jsonl").read_text().splitlines()
        (clone / "journal.jsonl").write_text("\n".join(lines[:-1]) + "\n")                  # drops stages_complete, chain stays valid
    with pytest.raises(sup.SupervisorError):
        sup.complete_workdir(clone)
    assert not (clone / "completion.json").exists()


def test_status_and_verify_report_strict_json_and_distinguish_incomplete_and_tampered(clone, capsys):
    assert sup.main(["verify", "--workdir", str(clone)]) == 0
    out = strict(capsys.readouterr().out)
    assert out["all_stages_verified"] is True and out["usage"]["attempts"] == {"known": 1, "test": 1, "matched": 1}
    flip_byte(clone / "test" / "test" / "part-00000.npz")
    assert sup.main(["status", "--workdir", str(clone)]) == 3
    assert strict(capsys.readouterr().out)["all_stages_verified"] is False
    assert sup.main(["verify", "--workdir", str(clone.parent / "absent")]) == 2
    capsys.readouterr()


# ---- journal unit tests ------------------------------------------------------------------------------------------------

def test_journal_chain_detects_tampering_gaps_and_torn_records(tmp_path):
    journal = sup.Journal(tmp_path / "j.jsonl")
    journal.open()
    for number in range(4):
        journal.append("event", n=number)
    records_, problems = sup.Journal.read(tmp_path / "j.jsonl")
    assert len(records_) == 4 and problems == [] and records_[0]["prev"] is None
    lines = (tmp_path / "j.jsonl").read_text().splitlines()
    cases = {"edited": [lines[0], lines[1].replace('"n": 1', '"n": 9'), *lines[2:]], "gap": [lines[0], *lines[2:]],
             "reordered": [lines[1], lines[0], *lines[2:]], "garbage": [*lines, "not json"],
             "nan": [*lines[:3], lines[3].replace('"n": 3', '"n": NaN')]}
    for name, variant in cases.items():
        path = tmp_path / f"{name}.jsonl"
        path.write_text("\n".join(variant) + "\n")
        assert sup.Journal.read(path)[1], name
    torn = tmp_path / "torn.jsonl"
    torn.write_text("\n".join(lines) + "\n" + lines[0][:20])
    assert any("incomplete" in p for p in sup.Journal.read(torn)[1])
    with pytest.raises(sup.SupervisorError, match="damaged"):
        sup.Journal(torn).open()
    with pytest.raises(ValueError):
        journal.append("event", bad=float("nan"))                                           # strict JSON only
    assert sup.Journal.read(tmp_path / "j.jsonl")[1] == []


def test_usage_accumulates_ended_attempts_and_exposes_an_open_one():
    base = {"schema": sup.JOURNAL_SCHEMA}
    start = {**base, "event": "attempt_start", "stage": "known", "attempt_id": "known-01", "pid": 5}
    end = {**base, "event": "attempt_end", "stage": "known", "attempt_id": "known-01", "elapsed_s": 3.0,
           "cpu_user_s": 1.0, "cpu_sys_s": 0.5}
    assert sup.usage_from([start, end])["open_attempt"] is None
    usage = sup.usage_from([start, end, {**start, "attempt_id": "known-02"}])
    assert usage["wall_s"] == 3.0 and usage["cpu_s"] == 1.5 and usage["attempts"]["known"] == 2
    assert usage["open_attempt"]["attempt_id"] == "known-02"


def test_pid_liveness_ignores_dead_children_and_resource_readers_are_defensive():
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait()
    assert sup.pid_alive(os.getpid()) and not sup.pid_alive(child.pid)
    assert sup.proc_vmrss_kib(os.getpid()) > 0 and sup.proc_vmrss_kib(2 ** 30) is None
    assert sup.proc_cpu_s(2 ** 30) is None


def test_dry_run_flags_budgets_that_the_plan_cannot_meet(tmp_path):
    plan = sup.build_plan(tmp_path / "w", mode="fixture", max_groups=2, groups_per_shard=1, ceilings={"wall_hours": 0.001})
    checks = {c["id"]: c for c in sup.dry_run_checks(plan, tmp_path / "w")}
    assert checks["supervisor.wall_budget"]["status"] == pre.FAIL
    tiny = sup.dry_run_checks(sup.build_plan(tmp_path / "w", mode="fixture", max_groups=2, groups_per_shard=1),
                              tmp_path / "w", disk_usage=lambda p: type("U", (), {"free": 2 ** 20})())
    assert {c["id"]: c["status"] for c in tiny}["supervisor.disk_budget"] == pre.FAIL

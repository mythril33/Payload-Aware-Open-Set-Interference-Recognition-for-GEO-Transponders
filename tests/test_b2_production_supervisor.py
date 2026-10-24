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

pytestmark = pytest.mark.skipif(not Path("/proc/self/stat").exists(), reason="the supervisor needs Linux /proc and PR_SET_PDEATHSIG")

TIMING = {"band_s_per_observation": [0.0001, 30.0], "startup_s": 0.5, "tolerance": 0.25}
CLI_FLAGS = ["--max-groups", "2", "--execute", "--allow-dirty-fixture", "--child-wrapper", str(STANDIN),
             "--timing-band", "0.0001", "30", "--timing-startup-s", "0.5"]


def strict(text):
    def reject(constant):
        raise ValueError(constant)
    return json.loads(text, parse_constant=reject)


def make(work, *, groups=2, groups_per_shard=1, ceilings=None, timing=None, heartbeat_s=None, launcher=None, **kwargs):
    plan = sup.build_plan(work, mode="fixture", max_groups=groups, groups_per_shard=groups_per_shard, ceilings=ceilings,
                          timing=dict(TIMING, **(timing or {})), launcher=launcher or sup.launcher_name(STANDIN),
                          heartbeat_s=heartbeat_s)
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


STARTED = []


def cli(*args, env=None, **kwargs):
    environment = dict(os.environ, **(env or {}))
    process = subprocess.Popen([sys.executable, str(SCRIPT), *args], cwd=ROOT, env=environment, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True, **kwargs)
    STARTED.append(process)
    return process


@pytest.fixture(autouse=True)
def no_supervisor_outlives_its_test():
    yield
    while STARTED:
        process = STARTED.pop()
        if process.poll() is None:                              # a failed assertion must not leave a supervisor (and its child) running
            process.kill()
            process.communicate(timeout=60)


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
        assert 0 < r["peak_rss_polled_kib"] and r["supervisor_peak_rss_kib"] > 0    # ru_maxrss is an upper bound, VmHWM a lower one
    events = [r["event"] for r in records(baseline)]
    assert events[0] == "supervisor_start" and events[-1] == "stages_complete" and "host_checked" in events
    assert [r["stage"] for r in records(baseline, "stage_complete")] == list(sup.STAGE_ORDER)
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


def heartbeats(work):
    found, _ = sup.Journal.read(Path(work) / "journal.jsonl")                  # tolerant: the journal is being appended to
    return [r for r in found if r["event"] == "heartbeat"]


def test_killing_the_supervisor_kills_the_child_and_a_restart_records_the_loss(tmp_path):
    work = tmp_path / "killed"
    flags = [*CLI_FLAGS, "--heartbeat-s", "0.4"]
    process = cli("run", "--workdir", str(work), *flags, env={"STANDIN_START_DELAY_S": "120"})
    assert wait_for(lambda: (work / "journal.jsonl").exists() and records(work, "attempt_start"), 90)
    child_pid = records(work, "attempt_start")[0]["pid"]
    assert sup.pid_alive(child_pid)
    assert wait_for(lambda: len(heartbeats(work)) >= 3, 60)
    last_beat = heartbeats(work)[-1]
    process.kill()
    process.communicate(timeout=30)
    assert pid_gone(child_pid), "PR_SET_PDEATHSIG should end the child with its supervisor"
    assert records(work)[-1]["event"] in ("attempt_start", "heartbeat")                   # no end record: SIGKILL cannot be handled
    again = cli("run", "--workdir", str(work), *flags)
    out, err = again.communicate(timeout=240)
    assert again.returncode == 0, (out, err)
    lost = [r for r in records(work, "attempt_end") if r["reason"] == "supervisor_lost"]
    assert len(lost) == 1 and lost[0]["exit_code"] is None and lost[0]["attempt_id"] == "known-01"
    assert lost[0]["estimated"] is True                                                    # an upper bound, not a measurement
    assert lost[0]["elapsed_s"] >= last_beat["elapsed_s"] + 0.4 and lost[0]["cpu_user_s"] > 0
    assert sup.usage_from(records(work))["wall_s"] >= lost[0]["elapsed_s"]


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
    original_request = (clone / "known" / "request.json").read_text()
    request = json.loads(original_request)
    request["scenario_groups"]["train"] = [request["scenario_groups"]["train"][0]] * 2    # a repeated group
    (clone / "known" / "request.json").write_text(json.dumps(request))
    result, new = run_expecting_invalid(clone)
    codes = {p["code"] for r in new if r["event"] == "stage_audit" for p in r["problems"]}
    assert {"role_groups", "generator_would_refuse_resume"} <= codes
    (clone / "known" / "request.json").write_text(json.dumps(json.loads(original_request)))               # restore, then inject a foreign group
    foreign = json.loads(original_request)
    foreign["scenario_groups"]["train"][0] = foreign["scenario_groups"]["val-select"][0]                  # a val-select id inside train
    (clone / "known" / "request.json").write_text(json.dumps(foreign))
    result, new = run_expecting_invalid(clone)
    codes = {p["code"] for r in new if r["event"] == "stage_audit" for p in r["problems"]}
    assert "role_groups" in codes


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


def test_an_invalid_root_with_orphans_is_not_quarantined_or_touched(clone):
    (clone / "known" / "train" / "shard-00001.json").unlink()                              # shard 1 becomes an orphan ...
    flip_byte(clone / "known" / "train" / "part-00000.npz")                                # ... while shard 0 is damaged
    before = {p.name: p.read_bytes() for p in (clone / "known" / "train").iterdir()}
    result, new = run_expecting_invalid(clone)
    assert "INVALID" in result["reasons"][0] and not (clone / "known" / "quarantine").exists()
    assert {p.name: p.read_bytes() for p in (clone / "known" / "train").iterdir()} == before   # nothing moved, nothing deleted
    assert not [r for r in new if r["event"] == "quarantine"]


def test_quarantine_refuses_to_run_without_orphans(clone):
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
    for kwargs in ({"groups": 1}, {"ceilings": {"wall_hours": 2.0}}, {"timing": {"tolerance": 0.5}}, {"heartbeat_s": 5.0},
                   {"launcher": "child-wrapper:other.py:0123456789abcdef"}, {"groups_per_shard": 2}):
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
    if case == "rss":
        assert end["elapsed_s"] < 25 and end["exit_code"] == -15, end      # stopped while running (the child would sleep 30 s), by SIGTERM
    assert pid_gone(records(work, "attempt_start")[-1]["pid"])
    assert records(work)[-1]["event"] == "run_failed" and sup.Journal.read(work / "journal.jsonl")[1] == []
    assert records(work, "stage_complete") == []


def test_the_attempt_budget_bounds_retries_after_a_failing_child(tmp_path, monkeypatch):
    monkeypatch.setenv("STANDIN_EXIT_AFTER_OBS", "3")
    work = tmp_path / "attempts"
    result = make(work, ceilings={"max_failed_attempts_per_stage": 2}).run()
    assert result["exit_code"] == 3 and "attempt budget exhausted" in result["reasons"][0]
    assert [r["exit_code"] for r in records(work, "attempt_end")] == [7, 7]
    assert sup.usage_from(records(work))["attempts"] == {"known": 2, "test": 0, "matched": 0}


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
    fast = make(tmp_path / "fast", timing={"band_s_per_observation": [10.0, 20.0], "startup_s": 0.0}).run()
    assert fast["exit_code"] == 0                                                      # measured cost is far below 10 / 1.25 = 8 s per observation
    assert {r["outcome"] for r in records(tmp_path / "fast", "timing_gate")} <= {"faster_than_band", "not_evaluated"}
    assert "faster_than_band" in {r["outcome"] for r in records(tmp_path / "fast", "timing_gate")}


# ---- 8 exit-code propagation -----------------------------------------------------------------------------------------

def test_a_nonzero_child_exit_code_is_journaled_exactly_and_fails_the_run(tmp_path, monkeypatch):
    monkeypatch.setenv("STANDIN_EXIT_AFTER_OBS", "2")
    monkeypatch.setenv("STANDIN_EXIT_CODE", "42")
    work = tmp_path / "exit42"
    result = make(work, ceilings={"max_failed_attempts_per_stage": 1}).run()
    assert result["exit_code"] == 3
    end = last_end(work)
    assert end["exit_code"] == 42 and end["reason"] == "exited" and "signal" not in end
    assert records(work, "attempt_failed")[0]["exit_code"] == 42
    assert records(work, "stage_complete") == []


def test_a_child_killed_by_a_signal_is_reported_as_the_signal(tmp_path, monkeypatch):
    monkeypatch.setenv("STANDIN_SELF_SIGNAL", str(int(signal.SIGKILL)))
    work = tmp_path / "sigkill"
    result = make(work, ceilings={"max_failed_attempts_per_stage": 1}).run()
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
    for name in ("numpy", "scipy", "torch", "xgboost"):         # the lock reads their versions; importing torch itself runs ldconfig
        try:
            __import__(name)
        except ImportError:
            pass
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
                   {"mode": "fixture", "max_groups": 1, "groups_per_shard": 1, "timing": {"bogus": 1}},
                   {"mode": "fixture", "max_groups": 1, "groups_per_shard": 1, "ceilings": {"max_attempts_per_stage": 2}},
                   {"mode": "fixture", "max_groups": 1, "groups_per_shard": 1, "ceilings": {"wall_hours": 1000}},
                   {"mode": "fixture", "max_groups": 1, "groups_per_shard": 1, "ceilings": {"core_hours": 1000}},
                   {"mode": "fixture", "max_groups": 1, "groups_per_shard": 1, "ceilings": {"max_rss_gib": 512}},
                   {"mode": "fixture", "max_groups": 1, "groups_per_shard": 1, "ceilings": {"max_failed_attempts_per_stage": 99}},
                   {"mode": "fixture", "max_groups": 1, "groups_per_shard": 1, "ceilings": {"max_failed_attempts_per_stage": 1.5}},
                   {"mode": "fixture", "max_groups": 1, "groups_per_shard": 1, "timing": {"tolerance": -0.5}},
                   {"mode": "fixture", "max_groups": 1, "groups_per_shard": 1, "timing": {"tolerance": 50}},
                   {"mode": "fixture", "max_groups": 1, "groups_per_shard": 1, "timing": {"startup_s": 1e9}},
                   {"mode": "fixture", "max_groups": 1, "groups_per_shard": 1, "timing": {"gate_shards": 0}},
                   {"mode": "fixture", "max_groups": 1, "groups_per_shard": 1, "timing": {"enabled": "yes"}},
                   {"mode": "fixture", "max_groups": 1, "groups_per_shard": 1, "heartbeat_s": 0},
                   {"mode": "fixture", "max_groups": 1, "groups_per_shard": 1, "launcher": "somewhere-else"},
                   {"mode": "production", "groups_per_shard": 4, "launcher": "child-wrapper:x:y"}):
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
        assert argv[2] == {"known": "geosim.b2_dataset", "test": "geosim.b2_test_dataset",
                           "matched": "geosim.b2_matched_dataset"}[stage] and ("--known" in argv) == (stage != "known")


# ---- completion, status ------------------------------------------------------------------------------------------------

def test_completion_is_written_once_only_for_a_verified_complete_scope(clone):
    marker = sup.complete_workdir(clone)
    assert marker["generation_complete"] is True and marker["scope"] == "fixture"
    assert marker["production_complete"] is False and marker["benchmark_complete"] is False
    assert marker["production_authorized"] is False and marker["observations"]["known"]["train"] == 16
    assert marker["child_launcher"].startswith("child-wrapper:b2_supervisor_standin.py:") and "diagnostic wrapper" in marker["note"]
    assert set(marker["stage_manifest_fingerprints"]) == set(sup.STAGE_ORDER)
    strict((clone / "completion.json").read_text())
    with pytest.raises(sup.SupervisorError, match="already exists"):
        sup.complete_workdir(clone)


@pytest.mark.parametrize("damage", ["missing_stage", "missing_manifest", "missing_role", "short_inventory", "no_final_record",
                                    "truncated_tail"])
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
        if damage == "no_final_record":                                                      # an anchor re-written to match the cut
            (clone / "journal.head").write_text(json.dumps({"seq": len(lines) - 1, "sha256": json.loads(lines[-2])["sha256"]}))
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
           "cpu_user_s": 1.0, "cpu_sys_s": 0.5, "reason": "exited", "exit_code": 0}
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


# ---- 11 independent-review regressions (E7a): false success, adoption, journal anchor, budgets ---------------------------

def test_a_child_that_finishes_the_work_then_exits_nonzero_is_never_a_silent_success(tmp_path, monkeypatch):
    monkeypatch.setenv("STANDIN_EXIT_AFTER_FINISH", "5")
    work = tmp_path / "late-failure"
    result = make(work, ceilings={"max_failed_attempts_per_stage": 2}).run()
    assert result["exit_code"] == 3 and "attempt budget exhausted" in result["reasons"][0], result
    assert [(r["exit_code"], r["reason"]) for r in records(work, "attempt_end")] == [(5, "exited"), (5, "exited")]
    assert records(work, "stage_complete") == [] and records(work, "stages_complete") == [] and not (work / "test").exists()
    assert records(work, "stage_needs_supervised_attempt")                                  # the root verified, the child did not
    checks = {c["id"]: c for c in sup.verify_workdir(work)[3]}
    assert checks["artifact.known"]["status"] == pre.FAIL and "last supervised attempt" in checks["artifact.known"]["message"]
    with pytest.raises(sup.SupervisorError):
        sup.complete_workdir(work)


def test_a_failing_child_is_retried_and_only_a_clean_supervised_attempt_completes_the_stage(tmp_path, monkeypatch):
    monkeypatch.setenv("STANDIN_EXIT_AFTER_FINISH", "5")
    monkeypatch.setenv("STANDIN_ONLY_STAGE", "known")
    monkeypatch.setenv("STANDIN_ONCE_MARKER", str(tmp_path / "fired"))
    work = tmp_path / "retry"
    result = make(work).run()
    assert result["exit_code"] == 0, result
    ends = [(r["exit_code"], r["reason"]) for r in records(work, "attempt_end") if r["stage"] == "known"]
    assert ends == [(5, "exited"), (0, "exited")]
    assert sup.usage_from(records(work))["failed_attempts"]["known"] == 1
    assert sup.complete_workdir(work)["generation_complete"] is True


def test_an_inherited_sigchld_ignore_cannot_hide_the_exit_status(tmp_path):
    work = tmp_path / "sigchld"
    process = cli("run", "--workdir", str(work), *CLI_FLAGS, preexec_fn=lambda: signal.signal(signal.SIGCHLD, signal.SIG_IGN))
    out, err = process.communicate(timeout=300)
    assert process.returncode == 0, (out, err)
    ends = records(work, "attempt_end")
    assert [r["exit_code"] for r in ends] == [0, 0, 0] and all(r["cpu_user_s"] + r["cpu_sys_s"] > 0 for r in ends)


def test_run_child_reports_wait_failed_when_the_exit_status_is_unobservable(tmp_path):
    previous = signal.signal(signal.SIGCHLD, signal.SIG_IGN)
    try:
        outcome = sup.run_child([sys.executable, "-c", "pass", "--limit-groups", "1"], cwd=str(tmp_path), env=dict(os.environ),
                                log_path=tmp_path / "w.log", timeout_s=60, cpu_budget_s=60, rss_limit_kib=2 ** 30, grace_s=2,
                                interrupted=lambda: False)
    finally:
        signal.signal(signal.SIGCHLD, previous)
    assert outcome["reason"] == "wait_failed" and outcome["exit_code"] is None


def test_child_deadlines_use_the_monotonic_clock_not_the_wall_clock(tmp_path, monkeypatch):
    import itertools
    ticks = itertools.count(10 ** 9, -1000)                                                 # a wall clock that jumps back on every read
    monkeypatch.setattr(time, "time", lambda: next(ticks))
    outcome = sup.run_child([sys.executable, "-c", "import time; time.sleep(30)", "--limit-groups", "1"], cwd=str(tmp_path),
                            env=dict(os.environ), log_path=tmp_path / "m.log", timeout_s=1.0, cpu_budget_s=60,
                            rss_limit_kib=2 ** 30, grace_s=5, interrupted=lambda: False)
    assert outcome["reason"] == "timeout" and 0.9 <= outcome["elapsed_s"] < 20, outcome


def test_a_signal_that_arrived_before_the_spawn_creates_no_child_log_or_attempt(tmp_path, spy):
    with pytest.raises(sup.SupervisorError) as caught:
        sup.run_child([sys.executable, "-c", "pass", "--limit-groups", "1"], cwd=str(tmp_path), env={}, log_path=tmp_path / "p.log",
                      timeout_s=60, cpu_budget_s=60, rss_limit_kib=2 ** 30, grace_s=2, interrupted=lambda: True)
    assert caught.value.code == sup.EXIT_INTERRUPTED and spy == [] and not (tmp_path / "p.log").exists()


def test_the_rss_rule_never_blames_a_child_for_the_supervisors_own_peak():
    limit = 1000
    inherited = {"peak_rss_polled_kib": 200, "peak_rss_kib": 5000, "supervisor_peak_rss_kib": 5000}      # ru_maxrss = the parent's
    own = {"peak_rss_polled_kib": 200, "peak_rss_kib": 5000, "supervisor_peak_rss_kib": 800}
    spike = {"peak_rss_polled_kib": 1500, "peak_rss_kib": 1500, "supervisor_peak_rss_kib": 9000}
    assert not sup.rss_exceeded(inherited, limit) and sup.rss_exceeded(own, limit) and sup.rss_exceeded(spike, limit)


def adopted(tmp_path, baseline, **kwargs):
    """A supervisor workdir that started but never ran a child, with someone else's finished roots copied in."""
    work = tmp_path / "adopted"
    work.mkdir()
    supervisor = make(work, **kwargs)
    pre._write_new(work / "run.json", json.dumps(supervisor._identity(), indent=1) + "\n")
    shutil.copy(baseline / "lock.json", work / "lock.json")
    journal = sup.Journal(work / "journal.jsonl")
    journal.open()
    journal.append("supervisor_start", restart=False, plan_fingerprint=supervisor._identity()["plan_fingerprint"],
                   lock_fingerprint=json.loads((work / "lock.json").read_text())["lock_fingerprint"], mode="fixture")
    for stage in sup.STAGE_ORDER:
        shutil.copytree(baseline / stage, work / stage)
    return work


def test_roots_built_with_another_shard_size_are_not_adopted(tmp_path, baseline):
    work = adopted(tmp_path, baseline, groups_per_shard=2)                                  # the plan says 2, the roots say 1
    checks = {c["id"]: c for c in sup.verify_workdir(work)[3]}
    assert checks["artifact.known"]["status"] == pre.FAIL and "not produced under this plan" in checks["artifact.known"]["message"]
    result = make(work, groups_per_shard=2).run()
    assert result["exit_code"] == 3 and "not produced under this plan" in result["reasons"][0], result
    assert "groups_per_shard" in result["reasons"][0] and records(work, "attempt_start") == []
    with pytest.raises(sup.SupervisorError):
        sup.complete_workdir(work)


def test_a_verified_foreign_root_is_accepted_only_after_a_clean_supervised_attempt(tmp_path, baseline):
    work = adopted(tmp_path, baseline)
    checks = {c["id"]: c for c in sup.verify_workdir(work)[3]}
    assert [checks[f"artifact.{s}"]["status"] for s in sup.STAGE_ORDER] == [pre.FAIL] * 3          # no supervised attempt produced them
    with pytest.raises(sup.SupervisorError):
        sup.complete_workdir(work)
    result = make(work).run()
    assert result["exit_code"] == 0, result
    assert [r["stage"] for r in records(work, "stage_needs_supervised_attempt")] == list(sup.STAGE_ORDER)
    assert [(r["stage"], r["exit_code"]) for r in records(work, "attempt_end")] == [("known", 0), ("test", 0), ("matched", 0)]
    assert sup.complete_workdir(work)["generation_complete"] is True


@pytest.mark.parametrize("damage,needle", [("deleted", "damaged"), ("emptied", "damaged"), ("tail_cut", "damaged"),
                                           ("head_two_behind", "damaged"), ("head_rewritten", "damaged"),
                                           ("both_deleted", "journal.head is missing")])
def test_a_missing_emptied_or_truncated_journal_is_refused_by_restart_and_verify(clone, damage, needle):
    journal, head = clone / "journal.jsonl", clone / "journal.head"
    lines = journal.read_text().splitlines()
    if damage == "deleted":
        journal.unlink()
    elif damage == "emptied":
        journal.write_text("")
    elif damage == "tail_cut":
        journal.write_text("\n".join(lines[:6]) + "\n")
    elif damage == "head_two_behind":
        head.write_text(json.dumps({"seq": len(lines) - 2, "sha256": json.loads(lines[-3])["sha256"]}))
    elif damage == "head_rewritten":
        head.write_text(json.dumps({"seq": len(lines), "sha256": "0" * 64}))
    else:
        journal.unlink()
        head.unlink()
    before = {p.name: p.read_bytes() for p in clone.glob("journal*")}
    result = make(clone).run()
    assert result["exit_code"] == 2 and needle in result["reasons"][0], result
    assert {p.name: p.read_bytes() for p in clone.glob("journal*")} == before               # a refusal writes nothing
    assert {c["id"]: c["status"] for c in sup.verify_workdir(clone)[3]}["workdir.journal"] == pre.FAIL
    with pytest.raises(sup.SupervisorError):
        sup.complete_workdir(clone)


def test_a_crash_between_a_journal_append_and_its_anchor_update_is_tolerated_once(clone):
    journal, head = clone / "journal.jsonl", clone / "journal.head"
    lines = journal.read_text().splitlines()
    head.write_text(json.dumps({"seq": len(lines) - 1, "sha256": json.loads(lines[-2])["sha256"]}))     # one record ahead
    assert make(clone).run()["exit_code"] == 0
    assert json.loads(head.read_text())["seq"] == len(records(clone))                       # the anchor catches up on the next append


def test_a_hand_edited_plan_with_a_recomputed_fingerprint_does_not_belong_to_the_journal(clone):
    run = json.loads((clone / "run.json").read_text())
    run["plan"]["ceilings"]["max_failed_attempts_per_stage"] = 4
    run["plan_fingerprint"] = sup.digest(run["plan"])
    (clone / "run.json").write_text(json.dumps(run))
    before = (clone / "journal.jsonl").read_bytes()
    result = make(clone, ceilings={"max_failed_attempts_per_stage": 4}).run()
    assert result["exit_code"] == 2 and "plan fingerprint differs from run.json" in result["reasons"][0], result
    assert (clone / "journal.jsonl").read_bytes() == before
    assert {c["id"]: c["status"] for c in sup.verify_workdir(clone)[3]}["workdir.journal"] == pre.FAIL


def test_a_workdir_that_crashed_before_its_first_journal_record_can_be_started_again(tmp_path, baseline):
    work = tmp_path / "never-started"
    work.mkdir()
    for name in ("run.json", "lock.json"):
        shutil.copy(baseline / name, work / name)
    result = make(work).run()
    assert result["exit_code"] == 0, result
    assert records(work, "supervisor_start")[0]["restart"] is False


def test_a_lost_attempt_is_charged_from_its_last_heartbeat_and_can_exhaust_the_budget(clone):
    shutil.rmtree(clone / "matched")                                                        # matched needs an attempt again
    pid = subprocess.run([sys.executable, "-c", "import os; print(os.getpid())"], capture_output=True, text=True).stdout.strip()
    journal = sup.Journal(clone / "journal.jsonl")
    journal.open()
    journal.append("attempt_start", stage="matched", attempt_id="matched-09", attempt=9, argv=["x", "--limit-groups", "1"],
                   pid=int(pid), committed_observations=0, remaining_shards=1)
    journal.append("heartbeat", stage="matched", attempt_id="matched-09", elapsed_s=3600.0, cpu_s=7000.0, rss_kib=1, peak_rss_polled_kib=1)
    result = make(clone).run()
    lost = [r for r in records(clone, "attempt_end") if r["reason"] == "supervisor_lost"][0]
    threads = max(int(v) for v in json.loads((clone / "lock.json").read_text())["environment"]["threads"].values() if v)
    assert lost["estimated"] is True and lost["elapsed_s"] == 3600.0 + 10.0 + 1.0 and lost["cpu_user_s"] == 7000.0 + 11.0 * threads
    assert result["exit_code"] == 3 and "ceiling exhausted" in result["reasons"][0], result       # the wall ceiling is one hour
    assert sup.usage_from(records(clone))["lost_attempts"]["matched"] == 1


def test_operator_interruptions_do_not_consume_the_failure_budget(tmp_path):
    work = tmp_path / "pauses"
    for _ in range(2):
        before = len(list(work.glob("known/*/shard-*.json")))
        process = cli("run", "--workdir", str(work), *CLI_FLAGS, env={"STANDIN_OBS_DELAY_S": "0.4"})
        assert wait_for(lambda: len(list(work.glob("known/*/shard-*.json"))) > before, 120), process.poll()
        process.send_signal(signal.SIGINT)
        process.communicate(timeout=60)
        assert process.returncode == sup.EXIT_INTERRUPTED
    final = cli("run", "--workdir", str(work), *CLI_FLAGS)
    out, err = final.communicate(timeout=300)
    assert final.returncode == 0, (out, err)                                                # the old limit of two attempts would stop here
    usage = sup.usage_from(records(work))
    assert usage["attempts"]["known"] == 3 and usage["interruptions"]["known"] == 2 and usage["failed_attempts"]["known"] == 0


def test_attempt_budgets_separate_failures_from_pauses():
    base = {"schema": sup.JOURNAL_SCHEMA, "stage": "known"}
    def end(number, reason, code):
        return [{**base, "event": "attempt_start", "attempt_id": f"known-{number:02d}", "pid": 5},
                {**base, "event": "attempt_end", "attempt_id": f"known-{number:02d}", "elapsed_s": 1.0, "cpu_user_s": 1.0,
                 "cpu_sys_s": 0.0, "reason": reason, "exit_code": code}]
    rows = end(1, "interrupted", -15) + end(2, "supervisor_lost", None) + end(3, "exited", 0) + end(4, "timing_gate", -15) \
        + end(5, "exited", 7) + end(6, "wait_failed", None)
    usage = sup.usage_from(rows)
    assert (usage["failed_attempts"]["known"], usage["interruptions"]["known"], usage["lost_attempts"]["known"]) == (3, 1, 1)
    assert usage["last_attempt_end"]["known"]["reason"] == "wait_failed" and usage["attempts"]["known"] == 6
    assert sup.last_attempt_acceptable(usage, "known")[0] is False and sup.last_attempt_acceptable(usage, "test")[0] is False
    assert sup.last_attempt_acceptable(sup.usage_from(end(1, "exited", 0)), "known")[0] is True
    assert sup.last_attempt_acceptable(sup.usage_from(end(1, "interrupted", -15)), "known")[0] is False      # proves nothing about today's root
    assert sup.last_attempt_acceptable(sup.usage_from(end(1, "supervisor_lost", None)), "known")[0] is False
    assert sup.last_attempt_acceptable(sup.usage_from(end(1, "exited", 3)), "known")[0] is False
    supervisor = sup.Supervisor.__new__(sup.Supervisor)
    supervisor.plan = {"ceilings": dict(sup.FIXTURE_CEILINGS)}
    many_pauses = {"attempts": {"known": 9}, "failed_attempts": {"known": 1}, "interruptions": {"known": 9}, "lost_attempts": {"known": 0}}
    supervisor._check_attempt_budgets(many_pauses, "known")                                  # nine pauses and one failure: fine
    for key, value, needle in (("failed_attempts", 2, "attempt budget exhausted"), ("interruptions", 10, "interruption budget"),
                               ("attempts", sup.MAX_TOTAL_ATTEMPTS_PER_STAGE, "backstop")):
        with pytest.raises(sup.SupervisorError, match=needle):
            supervisor._check_attempt_budgets({**many_pauses, key: {"known": value}}, "known")


def test_an_unreadable_host_probe_stops_the_run_before_any_child(tmp_path):
    work = tmp_path / "unknown-host"
    probe = lambda root, ceilings: [pre.check("resources.ram", "Host RAM", pre.NOT_RUN, "MemAvailable unreadable")]   # noqa: E731
    result = make(work, probe=probe).run()
    assert result["exit_code"] == 3 and "unknown is not safe" in result["reasons"][0], result
    assert records(work, "attempt_start") == [] and records(work)[-1]["event"] == "run_failed"


def test_an_attempt_that_ends_before_the_timing_gate_could_look_is_journaled_as_not_evaluated(tmp_path, monkeypatch):
    work = tmp_path / "unevaluated"
    outcome = sup.Outcome(exit_code=0, reason="exited", elapsed_s=0.1, cpu_user_s=0.1, cpu_sys_s=0.0, peak_rss_kib=10,
                          peak_rss_polled_kib=5, supervisor_peak_rss_kib=1, pid=1, log="x")
    monkeypatch.setattr(sup, "run_child", lambda *a, **k: outcome)
    result = make(work).run()                                                                # no shards: the run fails afterwards
    assert result["exit_code"] == 3 and "exited 0 but the root is" in result["reasons"][0]
    gate = records(work, "timing_gate")[0]
    assert gate["outcome"] == "not_evaluated" and "no throughput check was possible" in gate["note"]


def test_a_production_plan_can_lower_but_never_raise_the_proposed_ceilings(tmp_path):
    for key, value in (("wall_hours", 100000), ("core_hours", 1e6), ("max_rss_gib", 512), ("max_failed_attempts_per_stage", 50),
                       ("max_interruptions_per_stage", 500), ("grace_s", 5000)):
        with pytest.raises(sup.SupervisorError, match="proposed production ceiling"):
            sup.build_plan(tmp_path, mode="production", groups_per_shard=4, ceilings={key: value})
    lowered = sup.build_plan(tmp_path, mode="production", groups_per_shard=4, ceilings={"wall_hours": 1.0, "min_free_disk_gib": 500})
    assert lowered["ceilings"]["wall_hours"] == 1.0 and lowered["ceilings"]["min_free_disk_gib"] == 500


# ---- 12 damage during a run, wrapper restriction, supervision failure ----------------------------------------------------

def test_a_journal_damaged_during_a_run_is_never_appended_to_and_the_child_is_stopped(tmp_path, monkeypatch):
    monkeypatch.setenv("STANDIN_OBS_DELAY_S", "0.5")
    work = tmp_path / "damaged-midrun"
    state = {"damaged": False}

    def damaging_sleep(seconds):
        time.sleep(seconds)
        path = work / "journal.jsonl"
        if not state["damaged"] and path.exists() and '"event": "heartbeat"' in path.read_text():
            state["damaged"] = True
            with open(path, "a") as stream:
                stream.write("garbage written by someone else\n")

    result = make(work, heartbeat_s=0.2, sleep=damaging_sleep, ceilings={"max_failed_attempts_per_stage": 1}).run()
    assert result["exit_code"] == 3 and "journal damaged during the run" in result["reasons"][0], result
    text = (work / "journal.jsonl").read_text()
    assert text.endswith("garbage written by someone else\n") and '"event": "run_failed"' not in text   # not even run_failed
    child_pid = json.loads(next(line for line in text.splitlines() if '"event": "attempt_start"' in line))["pid"]
    assert pid_gone(child_pid), "a failed supervision must not leave the child running"


def test_run_child_kills_its_child_when_a_callback_fails(tmp_path):
    seen = {}

    def boom(beat):
        raise RuntimeError("journal write failed")

    with pytest.raises(RuntimeError, match="journal write failed"):
        sup.run_child([sys.executable, "-c", "import time; time.sleep(60)", "--limit-groups", "1"], cwd=str(tmp_path), env=dict(os.environ),
                      log_path=tmp_path / "c.log", timeout_s=120, cpu_budget_s=120, rss_limit_kib=2 ** 30, grace_s=5,
                      interrupted=lambda: False, on_start=lambda pid: seen.setdefault("pid", pid), on_heartbeat=boom,
                      heartbeat_s=0.05, poll_s=0.05)
    assert pid_gone(seen["pid"])


def test_the_journal_tail_check_handles_records_larger_than_a_read_chunk(tmp_path):
    journal = sup.Journal(tmp_path / "j.jsonl")
    journal.open()
    journal.append("big", blob="x" * 200_000)
    journal.append("after")
    journal.append("again")
    records_, problems = sup.Journal.load(tmp_path / "j.jsonl")
    assert [r["event"] for r in records_] == ["big", "after", "again"] and problems == []
    (tmp_path / "j.jsonl").write_text((tmp_path / "j.jsonl").read_text().rsplit("\n", 2)[0] + "\n")      # last record removed behind its back
    with pytest.raises(sup.SupervisorError, match="journal damaged during the run"):
        journal.append("never")


@pytest.mark.parametrize("command", ["plan", "run"])
def test_a_child_wrapper_outside_the_tests_directory_is_refused(tmp_path, command, capsys):
    script = tmp_path / "evil.py"
    script.write_text("import sys; open('marker', 'w').write('ran')\\n")
    argv = [command, "--workdir", str(tmp_path / "w"), "--max-groups", "2", "--child-wrapper", str(script)]
    assert sup.main(argv + (["--execute", "--allow-dirty-fixture"] if command == "run" else [])) == 2
    out = strict(capsys.readouterr().out)
    assert out["status"] == "REFUSED" and "tests/" in out["reasons"][0]
    assert not (tmp_path / "w").exists() and not (tmp_path / "marker").exists() and not (ROOT / "marker").exists()


# ---- 13 mutation-survivor regressions: signals, timing gate, budgets, environment, completion ------------------------------

def child_argv(code):
    return [sys.executable, "-c", code, "--limit-groups", "1"]


def supervise(tmp_path, code, *, interrupt_after=0.5, grace_s=30, **kwargs):
    """run_child on a throw-away python child; ``interrupt_after`` seconds after the spawn the interrupt flag is raised."""
    state = {"spawned": None}
    params = dict(timeout_s=300, cpu_budget_s=300, rss_limit_kib=2 ** 30, grace_s=grace_s, poll_s=0.05)
    params.update(kwargs)

    def interrupted():
        return state["spawned"] is not None and time.monotonic() - state["spawned"] > interrupt_after

    outcome = sup.run_child(child_argv(code), cwd=str(tmp_path), env=dict(os.environ), log_path=tmp_path / "child.log",
                            interrupted=interrupted, on_start=lambda pid: state.update(spawned=time.monotonic(), pid=pid), **params)
    return outcome, state


def test_an_interrupt_delivers_sigterm_and_the_child_exits_by_it_not_by_the_escalation(tmp_path):
    outcome, state = supervise(tmp_path, "import time; time.sleep(60)", grace_s=30)
    assert outcome["reason"] == "interrupted" and outcome["exit_code"] == -15 and outcome["signal"] == "SIGTERM"
    assert outcome["elapsed_s"] < 20 and pid_gone(state["pid"])


def test_a_child_that_ignores_sigterm_is_killed_after_the_grace_period(tmp_path):
    code = "import signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(40)"
    outcome, state = supervise(tmp_path, code, grace_s=1.0)
    assert outcome["reason"] == "interrupted" and outcome["exit_code"] == -9 and outcome["signal"] == "SIGKILL"
    assert 1.0 <= outcome["elapsed_s"] - 0.5 < 15 and pid_gone(state["pid"])


def test_the_whole_process_group_is_stopped_not_only_its_leader(tmp_path):
    code = ("import subprocess, sys, time\n"
            "grandchild = subprocess.Popen([sys.executable, '-c', 'import signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(60)'])\n"
            "print(grandchild.pid, flush=True)\ntime.sleep(60)")
    outcome, state = supervise(tmp_path, code, grace_s=1.0, interrupt_after=1.5)
    grandchild = int((tmp_path / "child.log").read_text().split()[0])
    assert outcome["reason"] == "interrupted"
    assert pid_gone(grandchild, timeout=15), "SIGTERM and SIGKILL go to the group, so a grandchild that ignores SIGTERM dies too"
    assert outcome["stragglers_killed"] is True                               # it outlived its leader and was removed at the end


def test_nothing_outlives_a_child_that_exits_normally(tmp_path):
    code = ("import subprocess, sys\n"
            "grandchild = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
            "print(grandchild.pid, flush=True)")
    outcome, state = supervise(tmp_path, code, interrupt_after=1e9)
    assert outcome["reason"] == "exited" and outcome["exit_code"] == 0 and outcome["stragglers_killed"] is True
    assert pid_gone(int((tmp_path / "child.log").read_text().split()[0]), timeout=15)
    (tmp_path / "clean").mkdir()
    clean, _ = supervise(tmp_path / "clean", "pass", interrupt_after=1e9)
    assert clean["stragglers_killed"] is False


def test_the_rss_ceiling_stops_a_running_child_and_is_measured_not_guessed(tmp_path):
    code = "b = bytearray(300 * 2**20); b[::4096] = b'x' * len(b[::4096]); import time; time.sleep(40)"
    outcome, state = supervise(tmp_path, code, rss_limit_kib=150 * 1024, interrupt_after=1e9, grace_s=10)
    assert outcome["reason"] == "rss_limit" and outcome["exit_code"] == -15 and outcome["elapsed_s"] < 25
    assert outcome["peak_rss_polled_kib"] > 150 * 1024                        # the polled VmHWM saw the allocation that crossed the limit


def test_resource_figures_come_from_wait4_unchanged(tmp_path, monkeypatch):
    real = os.wait4

    def fake(pid, options):
        done, status, usage = real(pid, options)
        if done:
            usage = type("R", (), {"ru_maxrss": 123456, "ru_utime": 1.5, "ru_stime": 0.25})()
        return done, status, usage

    monkeypatch.setattr(os, "wait4", fake)
    outcome, _ = supervise(tmp_path, "pass", interrupt_after=1e9)
    assert (outcome["peak_rss_kib"], outcome["cpu_user_s"], outcome["cpu_sys_s"]) == (123456, 1.5, 0.25)


def test_an_existing_log_is_never_overwritten(tmp_path):
    (tmp_path / "child.log").write_text("evidence")
    with pytest.raises(FileExistsError):
        supervise(tmp_path, "pass", interrupt_after=1e9)
    assert (tmp_path / "child.log").read_text() == "evidence"


def test_an_unexpected_io_error_is_a_failed_run_not_a_traceback(tmp_path, monkeypatch):
    work = tmp_path / "io"

    def broken(*args, **kwargs):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(sup, "run_child", broken)
    result = make(work).run()
    assert result["exit_code"] == 3 and "OSError" in result["reasons"][0] and "No space left" in result["reasons"][0], result
    assert records(work)[-1]["event"] == "run_failed" and records(work, "stage_complete") == []


# -- timing gate, unit level ------------------------------------------------------------------------------------------------

def gate_for(tmp_path, *, tolerance=0.5, startup=10.0, remaining=4, **timing):
    options = dict(sup.DEFAULT_TIMING, band_s_per_observation=[1.0, 2.0], tolerance=tolerance, startup_s=startup,
                   resume_verify_s_per_observation=0.0, **timing)
    started = 1_000_000.0
    return sup.TimingGate(tmp_path, options, started=started, committed_observations=0, first_shard_observations=32,
                          remaining_shards=remaining), started


def commit_shard(root, started, seconds_after_start, observations=10, name="shard-00000.json"):
    (root / "train").mkdir(parents=True, exist_ok=True)
    path = root / "train" / name
    path.write_text(json.dumps({"n_samples": observations}))
    os.utime(path, (started + seconds_after_start, started + seconds_after_start))


def test_the_gate_stops_a_shard_slower_than_the_band_plus_tolerance(tmp_path):
    gate, started = gate_for(tmp_path)                      # high 2.0 s/obs, tolerance 50 % -> limit 3.0 s/obs after the 10 s startup
    commit_shard(tmp_path, started, 10 + 10 * 3.5)
    assert gate(50.0) == "timing_gate" and gate.record["outcome"] == "too_slow"
    assert gate.record["s_per_observation"] == pytest.approx(3.5) and gate.record["observations"] == 10


def test_the_gate_subtracts_the_startup_allowance_and_honours_the_tolerance(tmp_path):
    gate, started = gate_for(tmp_path)
    commit_shard(tmp_path, started, 10 + 10 * 2.9)          # 2.9 s/obs: inside 2.0 x 1.5 only with the allowance subtracted
    assert gate(50.0) is None and gate.record["outcome"] == "within_band"
    tight, started = gate_for(tmp_path / "t", tolerance=0.0)
    commit_shard(tmp_path / "t", started, 10 + 10 * 2.9)    # the same shard with no tolerance is too slow
    assert tight(50.0) == "timing_gate"
    no_allowance, started = gate_for(tmp_path / "n", startup=0.0)
    commit_shard(tmp_path / "n", started, 10 + 10 * 2.9)    # and without the allowance it reads as 3.9 s/obs
    assert no_allowance(50.0) == "timing_gate"


def test_the_gate_flags_but_does_not_stop_a_faster_shard(tmp_path):
    gate, started = gate_for(tmp_path)
    commit_shard(tmp_path, started, 10 + 10 * 0.5)          # 0.5 < low / (1 + tolerance) = 0.667
    assert gate(30.0) is None and gate.record["outcome"] == "faster_than_band"


def test_the_gate_stops_a_child_that_commits_no_shard_before_the_deadline(tmp_path):
    gate, started = gate_for(tmp_path)                      # deadline = 10 + 32 x 2.0 x 1.5 = 106 s
    assert gate(105.0) is None and gate.record is None
    assert gate(107.0) == "timing_gate" and gate.record["outcome"] == "no_shard_before_deadline" and gate.record["deadline_s"] == 106.0


def test_the_gate_ignores_old_shards_and_is_inert_when_disabled_or_finished(tmp_path):
    gate, started = gate_for(tmp_path)
    commit_shard(tmp_path, started, -100.0)                 # committed before this attempt started
    assert gate(50.0) is None and gate.record is None
    for kwargs in ({"enabled": False}, {"remaining": 0}):
        quiet, started = gate_for(tmp_path / "q", **kwargs)
        assert quiet(1e9) is None and quiet.record is None


# -- budgets, interruption, completion, environment ---------------------------------------------------------------------------

def stub_child(monkeypatch, supervisor=None, **overrides):
    calls = []
    fields = dict(exit_code=0, reason="exited", elapsed_s=0.1, cpu_user_s=0.1, cpu_sys_s=0.0, peak_rss_kib=10, peak_rss_polled_kib=5,
                  supervisor_peak_rss_kib=1, pid=1, log="x")
    fields.update(overrides)

    def fake(argv, **kwargs):
        calls.append(kwargs)
        if supervisor is not None and "interrupt" in overrides:
            supervisor.interrupt = overrides["interrupt"]
        return sup.Outcome({k: v for k, v in fields.items() if k != "interrupt"})

    monkeypatch.setattr(sup, "run_child", fake)
    return calls


def test_wall_and_cpu_budgets_given_to_a_child_are_what_the_journal_has_left(clone, monkeypatch):
    shutil.rmtree(clone / "matched")
    usage = sup.usage_from(records(clone))
    calls = stub_child(monkeypatch)
    result = make(clone).run()                              # the stub produces nothing, so the run fails after one call
    assert result["exit_code"] == 3 and len(calls) == 1
    assert calls[0]["timeout_s"] == pytest.approx(3600.0 - usage["wall_s"]) and usage["wall_s"] > 0
    assert calls[0]["cpu_budget_s"] == pytest.approx(7200.0 - usage["cpu_s"]) and usage["cpu_s"] > 0


@pytest.mark.parametrize("field,needle", [("elapsed_s", "wall-time ceiling exhausted"), ("cpu_user_s", "CPU-time ceiling exhausted")])
def test_an_exhausted_wall_or_cpu_budget_stops_the_run_before_a_child_is_started(clone, monkeypatch, field, needle):
    shutil.rmtree(clone / "matched")
    journal = sup.Journal(clone / "journal.jsonl")
    journal.open()
    spent = {"elapsed_s": 1.0, "cpu_user_s": 1.0, "cpu_sys_s": 0.0}
    spent[field] = 20_000.0
    journal.append("attempt_start", stage="matched", attempt_id="matched-09", attempt=9, argv=["x", "--limit-groups", "1"], pid=1,
                   committed_observations=0, remaining_shards=1)
    journal.append("attempt_end", stage="matched", attempt_id="matched-09", reason="interrupted", exit_code=-15, **spent)
    calls = stub_child(monkeypatch)
    result = make(clone).run()
    assert result["exit_code"] == 3 and needle in result["reasons"][0] and calls == []


def test_a_spike_missed_by_polling_is_still_an_rss_failure_after_the_fact(tmp_path, monkeypatch):
    work = tmp_path / "spike"
    stub_child(monkeypatch, peak_rss_kib=5_000_000, peak_rss_polled_kib=0, supervisor_peak_rss_kib=1000)
    result = make(work, ceilings={"max_rss_gib": 1.0, "max_failed_attempts_per_stage": 1}).run()
    assert result["exit_code"] == 3 and last_end(work)["reason"] == "rss_limit" and "rss_limit" in result["reasons"][0]
    blameless = tmp_path / "blameless"
    stub_child(monkeypatch, peak_rss_kib=5_000_000, peak_rss_polled_kib=10, supervisor_peak_rss_kib=6_000_000)    # fork copied the parent's peak
    result = make(blameless, ceilings={"max_rss_gib": 1.0, "max_failed_attempts_per_stage": 1}).run()
    assert last_end(blameless)["reason"] == "exited"                                          # not blamed on the child


def test_a_signal_between_attempts_stops_the_run_before_another_child_starts(tmp_path, monkeypatch):
    work = tmp_path / "between"
    supervisor = make(work, ceilings={"max_failed_attempts_per_stage": 5})
    calls = stub_child(monkeypatch, supervisor, exit_code=7, interrupt=signal.SIGTERM)       # the child fails, and a signal arrives meanwhile
    result = supervisor.run(handler_signals=False)
    assert result["exit_code"] == sup.EXIT_INTERRUPTED and len(calls) == 1 and records(work)[-1]["event"] == "interrupted"


def test_the_budget_reader_refuses_a_journal_damaged_after_the_run_started(clone):
    supervisor = make(clone)
    supervisor.journal.open()
    lines = (clone / "journal.jsonl").read_text().splitlines()
    (clone / "journal.jsonl").write_text("\n".join([lines[0], "{}", *lines[2:]]) + "\n")
    with pytest.raises(sup.SupervisorError, match="journal damaged during the run"):
        supervisor._usage()


def test_the_inventory_check_compares_every_role_with_the_plan(tmp_path):
    supervisor = make(tmp_path / "w")
    good = {"roles": {role: {"observations_committed": n} for role, n in supervisor.plan["expected_observations"]["known"].items()}}
    supervisor._verify_inventory("known", good)
    short = {"roles": {role: {"observations_committed": n - 1 if role == "train" else n} for role, n in
                       supervisor.plan["expected_observations"]["known"].items()}}
    with pytest.raises(sup.SupervisorError, match="inventory"):
        supervisor._verify_inventory("known", short)


def test_completion_deep_verifies_a_sample_of_every_stage(clone, monkeypatch):
    seen = []
    real = pre.audit_artifact

    def spy(root, stage, **kwargs):
        seen.append((stage, kwargs.get("depth"), kwargs.get("max_full")))
        return real(root, stage, **kwargs)

    monkeypatch.setattr(pre, "audit_artifact", spy)
    sup.complete_workdir(clone)
    assert seen == [(stage, "full", 2) for stage in sup.STAGE_ORDER]


def test_a_fixture_marker_never_claims_production_authorization_even_if_every_gate_is_approved(clone):
    gates, memo = approved(pre._read_json(ROOT / pre.GATES_PATH), pre._read_json(ROOT / pre.MEMO_PATH))
    assert sup.authorization(gates, memo)[0] is True
    assert sup.complete_workdir(clone, gates=gates, memo=memo)["production_authorized"] is False


def test_children_get_a_scrubbed_gpu_and_the_locked_thread_environment_whatever_the_supervisor_inherited(tmp_path):
    work = tmp_path / "env"
    hostile = dict(os.environ, CUDA_VISIBLE_DEVICES="0", OMP_NUM_THREADS="7", OPENBLAS_NUM_THREADS="7")
    result = make(work, environ=hostile).run()
    assert result["exit_code"] == 0, result
    line = next(l for l in (work / "logs" / "known-01.log").read_text().splitlines() if l.startswith("standin env"))
    assert "CUDA_VISIBLE_DEVICES=''" in line and f"OMP_NUM_THREADS={os.environ['OMP_NUM_THREADS']!r}" in line


# ---- 14 prior-stage tampering, per-attempt drift, honest child RSS ---------------------------------------------------------

def test_a_stage_damaged_while_the_next_one_runs_blocks_the_stage_after_it(tmp_path, monkeypatch):
    monkeypatch.setenv("STANDIN_OBS_DELAY_S", "0.3")
    work = tmp_path / "tamper-behind"
    state = {"done": False}

    def tampering_sleep(seconds):
        time.sleep(seconds)
        started = [r for r in sup.Journal.read(work / "journal.jsonl")[0] if r["event"] == "attempt_start"] if (work / "journal.jsonl").exists() else []
        if not state["done"] and any(r["stage"] == "test" for r in started):
            state["done"] = True
            flip_byte(work / "known" / "train" / "part-00000.npz")                          # an earlier stage is damaged behind the supervisor

    result = make(work, sleep=tampering_sleep).run()
    assert result["exit_code"] == 3 and "known" in result["reasons"][0] and "INVALID" in result["reasons"][0], result
    assert [r["stage"] for r in records(work, "attempt_start")] == ["known", "test"]      # matched was never built on top of it


def test_drift_between_two_attempts_of_one_stage_stops_the_second_attempt(tmp_path, monkeypatch):
    monkeypatch.setenv("STANDIN_EXIT_AFTER_OBS", "3")
    work = tmp_path / "drift-between-attempts"
    real = pre.verify_lock

    def drifting(lock, *args, **kwargs):
        ended = (work / "journal.jsonl").exists() and any(r["event"] == "attempt_end" for r in sup.Journal.read(work / "journal.jsonl")[0])
        return ["source file modified: src/geosim/dual.py"] if ended else real(lock, *args, **kwargs)

    monkeypatch.setattr(pre, "verify_lock", drifting)
    result = make(work, ceilings={"max_failed_attempts_per_stage": 2}).run()
    assert result["exit_code"] == 3 and "drift" in result["reasons"][0], result
    assert len(records(work, "attempt_start")) == 1                                           # the retry never started


def test_a_small_child_reports_its_own_small_peak_even_when_the_supervisor_is_large(tmp_path):
    hold = bytearray(400 * 2 ** 20)                                                        # the supervisor's own memory at fork
    hold[::4096] = b"x" * len(hold[::4096])
    outcome, _ = supervise(tmp_path, "import time; time.sleep(1.0)", interrupt_after=1e9, rss_limit_kib=200 * 1024)
    assert outcome["reason"] == "exited" and outcome["exit_code"] == 0                       # not failed for the supervisor's memory
    assert 0 < outcome["peak_rss_polled_kib"] < 100 * 1024 and outcome["supervisor_peak_rss_kib"] >= 400 * 1024
    del hold


def test_a_child_that_touches_300_mib_reports_at_least_that(tmp_path):
    code = "b = bytearray(300 * 2**20); b[::4096] = b'x' * len(b[::4096]); import time; time.sleep(1.0)"
    outcome, _ = supervise(tmp_path, code, interrupt_after=1e9)
    assert outcome["reason"] == "exited" and outcome["peak_rss_polled_kib"] >= 300 * 1024 * 0.98
    assert outcome["peak_rss_kib"] >= outcome["peak_rss_polled_kib"] * 0.95


# ---- 15 the committed capped real-physics evidence ----------------------------------------------------------------------------

def test_the_committed_real_physics_journal_verifies_and_matches_its_summary(tmp_path):
    results = ROOT / "docs" / "results"
    summary = strict((results / "b2_e7a_supervisor_verification.json").read_text())
    shutil.copy(results / summary["journal"]["file"], tmp_path / "journal.jsonl")
    shutil.copy(results / summary["journal"]["head_file"], tmp_path / "journal.head")
    found, problems = sup.Journal.load(tmp_path / "journal.jsonl")
    assert problems == [] and len(found) == summary["journal"]["records"] and found[-1]["sha256"] == summary["journal"]["head"]
    assert pre._file_hash(tmp_path / "journal.jsonl") == summary["journal"]["sha256"]
    assert found[0]["event"] == "supervisor_start" and found[0]["restart"] is False and found[-1]["event"] == "stages_complete"
    assert [r["restart"] for r in found if r["event"] == "supervisor_start"] == [False, True, True]       # three supervisor starts
    ends = [r for r in found if r["event"] == "attempt_end"]
    assert [(r["attempt_id"], r["reason"]) for r in ends] == [("known-01", "interrupted"), ("known-02", "supervisor_lost"),
                                                             ("known-03", "exited"), ("test-01", "exited"), ("matched-01", "exited")]
    assert next(r for r in ends if r["reason"] == "supervisor_lost")["estimated"] is True
    assert sup.usage_from(found) == summary["usage"] and summary["lock"]["git_clean"] is True
    assert summary["benchmark_complete"] is False and summary["production_complete"] is False
    assert summary["completion_marker"]["production_authorized"] is False and summary["completion_marker"]["scope"] == "fixture"
    spec = importlib.util.spec_from_file_location("b2_e7a_capped_verification", ROOT / "scripts" / "b2_e7a_capped_verification.py")
    driver = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(driver)
    assert (results / "b2_e7a_supervisor_verification.md").read_text() == driver.render_markdown(summary)       # the report is its JSON


# ---- 16 post-merge audit (hotfix): lost-attempt thread count, spawn failures, adoption after interruption, provenance ----------

def test_a_lost_attempt_cpu_charge_uses_thread_counts_not_the_hash_seed(tmp_path):
    work = tmp_path / "w"
    supervisor = make(work)
    supervisor.lock = {"environment": {"threads": {"OMP_NUM_THREADS": "2", "OPENBLAS_NUM_THREADS": "2", "MKL_NUM_THREADS": "2",
                                                   "PYTHONHASHSEED": "1234"}}}
    work.mkdir()
    journal = supervisor.journal
    journal.open()
    journal.append("attempt_start", stage="known", attempt_id="known-01", attempt=1, argv=["x", "--limit-groups", "1"], pid=2 ** 22 + 7,
                   committed_observations=0, remaining_shards=1)
    supervisor._recover_unterminated(sup.Journal.read(work / "journal.jsonl")[0])
    lost = records(work, "attempt_end")[-1]
    assert lost["reason"] == "supervisor_lost" and lost["elapsed_s"] == 11.0 and lost["cpu_user_s"] == 22.0     # (10 s + 1 s) x 2 threads


def test_damage_in_the_middle_of_the_journal_during_the_last_attempt_still_ends_the_run_with_exit_3(tmp_path, monkeypatch):
    monkeypatch.setenv("STANDIN_OBS_DELAY_S", "0.5")
    monkeypatch.setenv("STANDIN_ONLY_STAGE", "matched")
    work = tmp_path / "late-damage"
    state = {"done": False}

    def damaging_sleep(seconds):
        time.sleep(seconds)
        started = [r for r in sup.Journal.read(work / "journal.jsonl")[0] if r["event"] == "attempt_start"] if (work / "journal.jsonl").exists() else []
        if not state["done"] and any(r["stage"] == "matched" for r in started):
            state["done"] = True
            path = work / "journal.jsonl"
            lines = path.read_text().split("\n")
            lines[1] = lines[1].replace("host_checked", "host_checkeX").replace("supervisor_start", "supervisor_starX")
            path.write_text("\n".join(lines))

    result = make(work, sleep=damaging_sleep).run()
    assert state["done"] and result["exit_code"] == 3 and "journal damaged during the run" in result["reasons"][0], result
    assert '"event": "stages_complete"' not in (work / "journal.jsonl").read_text()


def test_a_failed_spawn_does_not_wedge_the_workdir(tmp_path):
    work = tmp_path / "spawn"
    broken = make(work, ceilings={"max_failed_attempts_per_stage": 3})
    broken.launcher = lambda stage, plan, w: ["/nonexistent/python", "--limit-groups", "1"]
    first = broken.run()
    assert first["exit_code"] == 3 and (work / "logs" / "known-01.log").exists()               # the empty log of the failed spawn stays
    second = make(work, ceilings={"max_failed_attempts_per_stage": 3}).run()
    assert second["exit_code"] == 0, second
    assert (work / "logs" / "known-02.log").exists() and [r["attempt_id"] for r in records(work, "attempt_start")][0] == "known-02"


def test_a_child_that_ignores_sigterm_still_dies_with_a_killed_supervisor(tmp_path):
    script = tmp_path / "holder.py"
    script.write_text(
        "import os, sys, signal\n"
        f"sys.path.insert(0, {str(ROOT / 'scripts')!r})\n"
        "import b2_production_supervisor as sup\n"
        "from pathlib import Path\n"
        "tmp = Path(sys.argv[1])\n"
        "sup.run_child([sys.executable, '-c', 'import signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(120)', '--limit-groups', '1'],\n"
        "              cwd=str(tmp), env=dict(os.environ), log_path=tmp / 'h.log', timeout_s=300, cpu_budget_s=300, rss_limit_kib=2**30, grace_s=60,\n"
        "              interrupted=lambda: False, on_start=lambda pid: (tmp / 'pid').write_text(str(pid)), poll_s=0.05)\n")
    process = subprocess.Popen([sys.executable, str(script), str(tmp_path)], env=dict(os.environ))
    try:
        assert wait_for(lambda: (tmp_path / "pid").exists(), 60)
        child = int((tmp_path / "pid").read_text())
        time.sleep(1.0)
        process.kill()
        process.wait(timeout=30)
        assert pid_gone(child, timeout=15), "PR_SET_PDEATHSIG must be SIGKILL: a SIGTERM-ignoring child would outlive its supervisor"
    finally:
        if process.poll() is None:
            process.kill()


def test_a_verifying_root_after_an_interruption_still_needs_a_clean_supervised_attempt(tmp_path, baseline):
    work = adopted(tmp_path, baseline)
    journal = sup.Journal(work / "journal.jsonl")
    journal.open()
    journal.append("attempt_start", stage="known", attempt_id="known-01", attempt=1, argv=["x", "--limit-groups", "1"], pid=1,
                   committed_observations=0, remaining_shards=1)
    journal.append("attempt_end", stage="known", attempt_id="known-01", reason="interrupted", exit_code=-15, elapsed_s=1.0,
                   cpu_user_s=1.0, cpu_sys_s=0.0)
    checks = {c["id"]: c for c in sup.verify_workdir(work)[3]}
    assert checks["artifact.known"]["status"] == pre.FAIL and "interrupted" in checks["artifact.known"]["message"]
    result = make(work).run()
    assert result["exit_code"] == 0, result
    needed = records(work, "stage_needs_supervised_attempt")
    assert needed[0]["stage"] == "known" and "interrupted" in needed[0]["reason"]
    assert [(r["attempt_id"], r["exit_code"]) for r in records(work, "attempt_end") if r["stage"] == "known"] == [("known-01", -15), ("known-02", 0)]


def test_children_import_the_locked_source_tree_whatever_the_environment_says(tmp_path):
    work = tmp_path / "pythonpath"
    hostile = dict(os.environ, PYTHONPATH="/somewhere/else")
    assert make(work, environ=hostile).run()["exit_code"] == 0
    line = next(l for l in (work / "logs" / "known-01.log").read_text().splitlines() if l.startswith("standin env"))
    assert f"PYTHONPATH={str(ROOT / 'src') + os.pathsep + '/somewhere/else'!r}" in line


def test_a_production_plan_cannot_loosen_timing_or_the_disk_reserve(tmp_path):
    with pytest.raises(sup.SupervisorError, match="timing"):
        sup.build_plan(tmp_path, mode="production", groups_per_shard=4, timing={"band_s_per_observation": [0.1, 0.2]})
    with pytest.raises(sup.SupervisorError, match="reserve"):
        sup.build_plan(tmp_path, mode="production", groups_per_shard=4, ceilings={"min_free_disk_gib": 0.001})
    assert sup.build_plan(tmp_path, mode="production", groups_per_shard=4, ceilings={"min_free_disk_gib": 500})["ceilings"]["min_free_disk_gib"] == 500


def test_the_supervisor_and_preflight_code_are_part_of_the_run_identity(clone):
    stored = json.loads((clone / "run.json").read_text())
    assert set(stored["tools_sha256"]) == {"b2_production_supervisor.py", "b2_production_preflight.py"}
    stored["tools_sha256"]["b2_production_supervisor.py"] = "0" * 64
    (clone / "run.json").write_text(json.dumps(stored))
    result = make(clone).run()
    assert result["exit_code"] == 2 and "supervisor/preflight code differs" in result["reasons"][0]
    assert {c["id"]: c["status"] for c in sup.verify_workdir(clone)[3]}["workdir.tools"] == pre.FAIL
    with pytest.raises(sup.SupervisorError):
        sup.complete_workdir(clone)


def test_a_missing_anchor_is_tolerated_for_one_record_only_in_a_workdir_that_never_ran(tmp_path):
    quiet = tmp_path / "quiet"
    quiet.mkdir()
    journal = sup.Journal(quiet / "journal.jsonl")
    journal.open()
    journal.append("supervisor_start", restart=False)
    (quiet / "journal.head").unlink()
    (quiet / "run.json").write_text("{}")
    assert sup.Journal.load(quiet / "journal.jsonl")[1] == []
    (quiet / "known").mkdir()                                                        # anything else in the workdir: no tolerance
    assert sup.Journal.load(quiet / "journal.jsonl")[1]


def test_the_completion_marker_must_belong_to_the_run_and_its_journal(clone):
    sup.complete_workdir(clone)
    assert {c["id"]: c["status"] for c in sup.verify_workdir(clone)[3]}["workdir.completion"] == pre.PASS
    assert make(clone).run()["exit_code"] == 0                                      # the journal grows past the marker's head ...
    assert {c["id"]: c["status"] for c in sup.verify_workdir(clone)[3]}["workdir.completion"] == pre.PASS     # ... which stays in the chain
    marker = json.loads((clone / "completion.json").read_text())
    marker["journal_head"] = "f" * 64
    (clone / "completion.json").write_text(json.dumps(marker))
    assert {c["id"]: c["status"] for c in sup.verify_workdir(clone)[3]}["workdir.completion"] == pre.FAIL


def test_malformed_state_files_are_refusals_not_tracebacks(clone, capsys):
    (clone / "lock.json").write_text("{}")
    assert sup.main(["verify", "--workdir", str(clone)]) == 2
    assert strict(capsys.readouterr().out)["status"] == "REFUSED"
    (clone / "run.json").write_text("[]")
    assert sup.main(["status", "--workdir", str(clone)]) == 2
    capsys.readouterr()


def test_a_real_time_signal_death_is_reported_by_number(tmp_path):
    outcome, _ = supervise(tmp_path, "import os, time; os.kill(os.getpid(), 40); time.sleep(5)", interrupt_after=1e9)
    assert outcome["exit_code"] == -40 and outcome["signal"] == "SIG40"


def test_a_child_wrapper_must_be_the_stand_in_itself(tmp_path, capsys):
    other = ROOT / "tests" / "test_b2_production_supervisor.py"
    assert sup.main(["plan", "--workdir", str(tmp_path / "w"), "--max-groups", "2", "--child-wrapper", str(other)]) == 2
    assert "b2_supervisor_standin.py" in strict(capsys.readouterr().out)["reasons"][0]


# -- limits at their boundaries, durability, budgets that mutants could loosen ---------------------------------------------------

@pytest.mark.parametrize("key", sorted(sup.FIXTURE_CEILING_LIMITS))
def test_fixture_ceiling_limits_hold_at_their_boundary(tmp_path, key):
    limit = sup.FIXTURE_CEILING_LIMITS[key]
    at = sup.build_plan(tmp_path, mode="fixture", max_groups=1, groups_per_shard=1, ceilings={key: limit})
    assert at["ceilings"][key] == limit
    with pytest.raises(sup.SupervisorError):
        sup.build_plan(tmp_path, mode="fixture", max_groups=1, groups_per_shard=1, ceilings={key: limit * 1.01 if limit > 100 else limit + 1})


@pytest.mark.parametrize("key", sorted(sup.PRODUCTION_CEILING_LIMITS))
def test_production_ceiling_limits_hold_at_their_boundary(tmp_path, key):
    limit = sup.PRODUCTION_CEILING_LIMITS[key]
    assert sup.build_plan(tmp_path, mode="production", groups_per_shard=4, ceilings={key: limit})["ceilings"][key] == limit
    with pytest.raises(sup.SupervisorError):
        sup.build_plan(tmp_path, mode="production", groups_per_shard=4, ceilings={key: limit + 1})


@pytest.mark.parametrize("key,ok,bad", [("tolerance", 2.0, 2.01), ("startup_s", 3600.0, 3601.0), ("resume_verify_s_per_observation", 1.0, 1.01)])
def test_timing_limits_hold_at_their_boundary(tmp_path, key, ok, bad):
    assert sup.build_plan(tmp_path, mode="fixture", max_groups=1, groups_per_shard=1, timing={key: ok})["timing"][key] == ok
    with pytest.raises(sup.SupervisorError):
        sup.build_plan(tmp_path, mode="fixture", max_groups=1, groups_per_shard=1, timing={key: bad})


def test_the_journal_and_its_anchor_are_fsynced(tmp_path, monkeypatch):
    calls = []
    real = os.fsync
    monkeypatch.setattr(os, "fsync", lambda fd: (calls.append(fd), real(fd))[1])
    journal = sup.Journal(tmp_path / "j.jsonl")
    journal.open()
    journal.append("one")
    first = len(calls)
    journal.append("two")
    assert first >= 4 and len(calls) - first >= 2          # record + directory + anchor + directory the first time, record + anchor after


def test_lost_supervisors_count_against_the_interruption_budget():
    supervisor = sup.Supervisor.__new__(sup.Supervisor)
    supervisor.plan = {"ceilings": dict(sup.FIXTURE_CEILINGS)}
    usage = {"attempts": {"known": 10}, "failed_attempts": {"known": 0}, "interruptions": {"known": 5}, "lost_attempts": {"known": 5}}
    with pytest.raises(sup.SupervisorError, match="interruption budget"):
        supervisor._check_attempt_budgets(usage, "known")


def test_the_disk_check_keeps_its_ten_percent_margin(tmp_path):
    supervisor = make(tmp_path / "w")
    remaining = 2_000_000
    need = remaining * sup.ARTIFACT_BYTES_PER_OBSERVATION / 2 ** 30
    reserve = supervisor.plan["ceilings"]["min_free_disk_gib"]
    usage = {"wall_s": 0.0, "cpu_s": 0.0}
    supervisor.disk_usage = lambda path: type("U", (), {"free": int((need * 1.05 + reserve) * 2 ** 30)})()
    with pytest.raises(sup.SupervisorError, match="free disk"):
        supervisor._check_budgets(usage, remaining)
    supervisor.disk_usage = lambda path: type("U", (), {"free": int((need * 1.15 + reserve) * 2 ** 30)})()
    supervisor._check_budgets(usage, remaining)


def test_cpu_time_of_a_running_child_includes_the_children_it_has_waited_for():
    code = "import subprocess, sys, time; subprocess.run([sys.executable, '-c', 'sum(range(4 * 10**7))']); time.sleep(4)"
    process = subprocess.Popen([sys.executable, "-c", code])
    try:
        assert wait_for(lambda: (sup.proc_cpu_s(process.pid) or 0) > 0.3, 3.5, 0.1), sup.proc_cpu_s(process.pid)
    finally:
        process.kill()
        process.wait()


def test_the_journal_tail_check_notices_a_swapped_last_record_and_a_foreign_journal(tmp_path):
    journal = sup.Journal(tmp_path / "j.jsonl")
    journal.open()
    journal.append("one")
    journal.append("two")
    lines = (tmp_path / "j.jsonl").read_text().split("\n")
    last = json.loads(lines[1])
    last["sha256"] = "0" * 64
    (tmp_path / "j.jsonl").write_text(lines[0] + "\n" + json.dumps(last, sort_keys=True) + "\n")          # same seq, different hash
    with pytest.raises(sup.SupervisorError, match="journal damaged during the run"):
        journal.append("three")
    stranger = sup.Journal(tmp_path / "j.jsonl")                                                          # holds no records but the file exists
    with pytest.raises(sup.SupervisorError, match="journal damaged during the run"):
        stranger.append("x")


def test_the_run_journal_check_demands_an_original_start_and_matching_fingerprints():
    identity, lock = {"plan_fingerprint": "p"}, {"lock_fingerprint": "l"}
    good = [{"event": "supervisor_start", "restart": False, "plan_fingerprint": "p", "lock_fingerprint": "l", "seq": 1}]
    assert sup.check_run_journal(good, identity, lock) == []
    assert sup.check_run_journal([{**good[0], "restart": True}], identity, lock)
    assert sup.check_run_journal([{**good[0], "lock_fingerprint": "other"}], identity, lock)
    assert sup.check_run_journal([{**good[0], "plan_fingerprint": "other"}], identity, lock)


def test_the_limit_constants_are_pinned_to_literals():
    """The boundary tests read the constants; these literals make loosening a constant itself a visible, reviewed change."""
    assert sup.FIXTURE_CEILING_LIMITS == {"wall_hours": 4.0, "core_hours": 16.0, "max_failed_attempts_per_stage": 5,
                                         "max_interruptions_per_stage": 50, "max_rss_gib": 16.0, "grace_s": 120.0}
    assert sup.PRODUCTION_CEILING_LIMITS == {"wall_hours": 36.0, "core_hours": 42.0, "max_failed_attempts_per_stage": 2,
                                            "max_interruptions_per_stage": 20, "max_rss_gib": 2.0, "grace_s": 600.0}
    assert sup.FIXTURE_CEILINGS == {"wall_hours": 1.0, "core_hours": 2.0, "max_failed_attempts_per_stage": 2, "max_interruptions_per_stage": 10,
                                   "max_rss_gib": 4.0, "min_free_disk_gib": 1.0, "grace_s": 10.0}
    assert sup.TIMING_LIMITS == {"tolerance": (0.0, 2.0), "startup_s": (0.0, 3600.0), "resume_verify_s_per_observation": (0.0, 1.0)}
    assert sup.MAX_TOTAL_ATTEMPTS_PER_STAGE == 60 and sup.FIXTURE_MAX_GROUPS == 2 and sup.PRODUCTION_LAUNCH_ENABLED is False


# -- review of the hotfix (second independent read) ------------------------------------------------------------------------------

def test_a_finished_root_is_verified_even_when_the_interruption_budget_is_spent(clone):
    ceiling = json.loads((clone / "run.json").read_text())["plan"]["ceilings"]["max_interruptions_per_stage"]
    journal = sup.Journal(clone / "journal.jsonl")
    journal.open()
    for number in range(2, 2 + ceiling):
        journal.append("attempt_start", stage="matched", attempt_id=f"matched-{number:02d}", attempt=number,
                       argv=["x", "--limit-groups", "1"], pid=1, committed_observations=0, remaining_shards=0)
        journal.append("attempt_end", stage="matched", attempt_id=f"matched-{number:02d}", reason="interrupted", exit_code=-15,
                       elapsed_s=1.0, cpu_user_s=1.0, cpu_sys_s=0.0)
    result = make(clone).run()
    assert result["exit_code"] == 0, result                 # a no-op verification adds no lost work, so the ceiling does not apply to it
    assert records(clone, "stage_needs_supervised_attempt")[-1]["stage"] == "matched"


def test_the_first_record_anchor_tolerance_covers_the_head_temp_file_and_a_missing_directory(tmp_path):
    work = tmp_path / "w"
    work.mkdir()
    journal = sup.Journal(work / "journal.jsonl")
    journal.open()
    journal.append("supervisor_start")
    (work / "journal.head.tmp").write_text("{}")             # the crash between writing the temp head and replacing it
    (work / "journal.head").unlink()
    assert sup.Journal.load(work / "journal.jsonl")[1] == []
    (work / "marker.txt").write_text("something ran")
    assert any("journal.head is missing" in p for p in sup.Journal.load(work / "journal.jsonl")[1])
    assert sup.Journal.load(tmp_path / "nowhere" / "journal.jsonl") == ([], [])


def test_an_internal_error_during_a_run_is_a_journaled_failed_run_not_a_refusal(tmp_path, monkeypatch):
    work = tmp_path / "w"
    supervisor = make(work)
    monkeypatch.setattr(supervisor, "_attempt", lambda *args, **kwargs: {}["missing"])
    result = supervisor.run()
    assert result["exit_code"] == 3 and result["status"] == "FAILED" and "KeyError" in result["reasons"][0]
    assert records(work)[-1]["event"] == "run_failed"


def test_attempt_ids_never_reuse_a_journaled_number_even_without_logs(tmp_path, baseline):
    work = adopted(tmp_path, baseline)
    journal = sup.Journal(work / "journal.jsonl")
    journal.open()
    journal.append("attempt_start", stage="known", attempt_id="known-03", attempt=3, argv=["x", "--limit-groups", "1"], pid=1,
                   committed_observations=0, remaining_shards=1)
    journal.append("attempt_end", stage="known", attempt_id="known-03", reason="interrupted", exit_code=-15, elapsed_s=1.0,
                   cpu_user_s=1.0, cpu_sys_s=0.0)
    assert make(work).run()["exit_code"] == 0
    assert [r["attempt_id"] for r in records(work, "attempt_start") if r["stage"] == "known"] == ["known-03", "known-04"]

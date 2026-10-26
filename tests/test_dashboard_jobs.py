"""Job manager tests: one job at a time, cancel, timeout, recovery after a restart, boundary checks.

Child processes are harmless `sys.executable -c` programs injected through a test registry. The argv guard
is disabled only for those injected specs; the production registry is always guarded (see the commands tests).
"""
import json
import os
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "dashboard"), str(ROOT / "src"), str(ROOT)]

from geodash import commands as C  # noqa: E402
from geodash import jobs as J  # noqa: E402
from geodash.paths import LocationError  # noqa: E402


def _program(seconds, text="ok"):
    return [sys.executable, "-c",
            f"import time,sys;print({text!r},flush=True);time.sleep({seconds});print('finished',flush=True)"]


def _spec(key, seconds, timeout_s=60, success=C._exit_zero):
    return C.CommandSpec(key=key, title=f"test {key}", scope=C.SCOPE_CPU_TEST, description="injected test program",
                         params=(), builder=lambda values, job_dir, python: _program(seconds, key),
                         timeout_s=timeout_s, success=success)


def _manager(tmp_path, registry, clock=time.time):
    return J.JobManager(tmp_path / "home", registry=registry, argv_guard=lambda argv, spec: None, clock=clock)


def _wait_for(manager, job_id, states, limit_s=20.0):
    deadline = time.time() + limit_s
    status = manager.status(job_id)
    while status.state not in states and time.time() < deadline:
        time.sleep(0.2)
        status = manager.status(job_id)
    return status


def test_a_successful_job_is_recorded_with_its_output_and_exit_status(tmp_path):
    manager = _manager(tmp_path, {"quick": _spec("quick", 0.3)})
    job_id = manager.start("quick")
    status = _wait_for(manager, job_id, {J.SUCCEEDED, J.FAILED})
    assert status.state == J.SUCCEEDED and status.returncode == 0
    assert any("quick" in line for line in status.log_tail)
    recorded = json.loads((tmp_path / "home" / "jobs" / job_id / "job.json").read_text())
    assert recorded["state"] == J.SUCCEEDED and recorded["argv"][0] == sys.executable


def test_a_failing_program_is_reported_as_failed_with_its_exit_status(tmp_path):
    failing = C.CommandSpec(key="boom", title="boom", scope=C.SCOPE_CPU_TEST, description="",
                            params=(), builder=lambda v, d, p: [sys.executable, "-c", "import sys;sys.exit(3)"],
                            timeout_s=60, success=C._exit_zero)
    manager = _manager(tmp_path, {"boom": failing})
    status = _wait_for(manager, manager.start("boom"), {J.SUCCEEDED, J.FAILED})
    assert status.state == J.FAILED and status.returncode == 3
    assert "exit status 3" in status.reason


def test_only_one_job_runs_at_a_time(tmp_path):
    manager = _manager(tmp_path, {"slow": _spec("slow", 30)})
    first = manager.start("slow")
    try:
        with pytest.raises(J.ActiveJobError):
            manager.start("slow")
    finally:
        manager.cancel(first)


def test_cancel_stops_the_process_group_and_records_the_cancellation(tmp_path):
    manager = _manager(tmp_path, {"slow": _spec("slow", 30)})
    job_id = manager.start("slow")
    status = manager.cancel(job_id)
    assert status.state == J.CANCELLED
    assert not J._pid_alive(status.pid)


def test_a_job_that_exceeds_its_gui_timeout_is_stopped_and_marked_timed_out(tmp_path):
    manager = _manager(tmp_path, {"forever": _spec("forever", 60, timeout_s=1)})
    job_id = manager.start("forever")
    status = _wait_for(manager, job_id, {J.TIMED_OUT, J.FAILED, J.SUCCEEDED}, limit_s=30)
    assert status.state == J.TIMED_OUT
    assert "GUI timeout" in status.reason
    assert not J._pid_alive(status.pid)


def test_a_restarted_gui_recovers_a_running_job_from_its_record(tmp_path):
    registry = {"slow": _spec("slow", 30)}
    first = _manager(tmp_path, registry)
    job_id = first.start("slow")
    second = _manager(tmp_path, registry)  # a new manager, as after a GUI restart
    assert second.status(job_id).state == J.RUNNING
    cancelled = second.cancel(job_id)
    assert cancelled.state == J.CANCELLED


def test_a_second_manager_refuses_to_start_while_a_job_runs(tmp_path):
    registry = {"slow": _spec("slow", 30)}
    first = _manager(tmp_path, registry)
    job_id = first.start("slow")
    try:
        with pytest.raises(J.ActiveJobError):
            _manager(tmp_path, registry).start("slow")
    finally:
        first.cancel(job_id)


def test_unknown_commands_and_extra_parameters_never_start(tmp_path):
    manager = _manager(tmp_path, {"quick": _spec("quick", 0.1)})
    with pytest.raises(C.CommandRefused):
        manager.start("not-listed")
    with pytest.raises(C.CommandRefused):
        manager.start("quick", {"argv": ["rm", "-rf", "/"]})
    assert manager.list_jobs() == []


def test_the_run_folder_inside_the_repository_is_refused(tmp_path):
    with pytest.raises(LocationError):
        J.JobManager(ROOT / "runs" / "inside-repo", registry={}, argv_guard=lambda a, s: None)


def test_the_gui_passes_a_fixed_environment_with_cuda_hidden(tmp_path):
    seen = {}

    def fake_popen(argv, **kwargs):
        seen.update(kwargs)
        return J.subprocess.Popen([sys.executable, "-c", "pass"], **{k: v for k, v in kwargs.items()
                                                                   if k in ("stdin", "stdout", "stderr", "cwd",
                                                                            "start_new_session")})

    manager = J.JobManager(tmp_path / "home", registry={"quick": _spec("quick", 0.1)},
                           popen=fake_popen, argv_guard=lambda a, s: None)
    manager.start("quick")
    assert seen["shell"] is False and seen["start_new_session"] is True
    assert seen["env"]["CUDA_VISIBLE_DEVICES"] == "" and seen["cwd"] == str(ROOT)


# ---- progress inference and boundary checks, from synthetic output folders ------------------------------

def test_stage_is_inferred_from_output_files_in_order(tmp_path):
    job = tmp_path / "job"
    assert J.infer_stage("real-exercise", job)[0] == "starting"
    (job / "exercise" / "work").mkdir(parents=True)
    (job / "exercise" / "work" / "generator-1.log").write_text("line one\nline two\n")
    assert J.infer_stage("real-exercise", job) == ("RF generation", "line two")
    (job / "exercise" / "models").mkdir()
    assert J.infer_stage("real-exercise", job)[0] == "training and calibration"
    (job / "exercise" / "freeze.json").write_text("{}")
    assert J.infer_stage("real-exercise", job)[0] == "freeze written"
    (job / "exercise" / "exercise.json").write_text("{}")
    assert J.infer_stage("real-exercise", job)[0] == "complete"
    assert J.infer_stage("host-inventory", job) == ("", "")


def _exercise_report(**overrides):
    report = {"schema": "B2-real-kernel-exercise/1", "scope": "BOUNDED_DEVELOPMENT", "heldout_reads": 0,
              "gpu_exercised": False, "production_authorized": False, "benchmark_complete": False}
    report.update(overrides)
    return report


def _job_with_report(tmp_path, report):
    job = tmp_path / "job"
    (job / "exercise").mkdir(parents=True)
    (job / "exercise" / "exercise.json").write_text(json.dumps(report))
    return job


def test_a_clean_boundary_report_is_accepted(tmp_path):
    ok, reason = C._exercise_success(_job_with_report(tmp_path, _exercise_report()))
    assert ok and "boundary" in reason


@pytest.mark.parametrize("field,value", [
    ("heldout_reads", 1), ("gpu_exercised", True), ("production_authorized", True),
    ("benchmark_complete", True), ("scope", "PRODUCTION"), ("schema", "other/1"),
])
def test_a_report_that_crosses_the_boundary_is_refused(tmp_path, field, value):
    ok, reason = C._exercise_success(_job_with_report(tmp_path / field, _exercise_report(**{field: value})))
    assert not ok and field in reason


def test_a_missing_report_is_not_success(tmp_path):
    ok, reason = C._exercise_success(tmp_path)
    assert not ok and "not written" in reason


def test_the_exercise_job_is_only_successful_with_a_valid_report(tmp_path):
    spec = C.REGISTRY["real-exercise"]
    job = tmp_path / "job"
    assert spec.success is C._exercise_success
    (job / "exercise").mkdir(parents=True)
    assert not spec.success(job)[0]


def test_a_finished_job_without_a_recorded_exit_status_is_not_reported_as_success(tmp_path):
    """A job that outlived the dashboard process that started it: outputs verified, exit status unknown."""
    registry = {"quick": _spec("quick", 0.2, success=lambda job_dir: (True, "outputs verified"))}
    first = _manager(tmp_path, registry)
    job_id = first.start("quick")
    deadline = time.time() + 20
    while J._pid_alive(json.loads((tmp_path / "home" / "jobs" / job_id / "job.json").read_text())["pid"]) \
            and time.time() < deadline:
        time.sleep(0.1)
    orphan = _manager(tmp_path, registry)  # no Popen handle: the exit status cannot be known
    status = orphan.status(job_id)
    assert status.state == J.FINISHED_UNRECORDED
    assert "exit status not recorded" in status.reason and status.returncode is None


def test_a_finished_job_without_a_recorded_exit_status_and_no_outputs_is_failed(tmp_path):
    registry = {"quick": _spec("quick", 0.2, success=lambda job_dir: (False, "no output"))}
    first = _manager(tmp_path, registry)
    job_id = first.start("quick")
    deadline = time.time() + 20
    while J._pid_alive(json.loads((tmp_path / "home" / "jobs" / job_id / "job.json").read_text())["pid"]) \
            and time.time() < deadline:
        time.sleep(0.1)
    status = _manager(tmp_path, registry).status(job_id)
    assert status.state == J.FAILED and "did not verify" in status.reason


def test_a_non_owner_process_does_not_record_the_outcome_of_a_job_it_did_not_start(tmp_path):
    """Only the dashboard process that owns a job may finalise it. A second process must leave the record alone."""
    registry = {"quick": _spec("quick", 0.2, success=lambda job_dir: (True, "outputs verified"))}
    owner = _manager(tmp_path, registry)
    job_id = owner.start("quick")
    deadline = time.time() + 20
    while J._pid_alive(json.loads((tmp_path / "home" / "jobs" / job_id / "job.json").read_text())["pid"]) \
            and time.time() < deadline:
        time.sleep(0.1)
    job_json = tmp_path / "home" / "jobs" / job_id / "job.json"
    record = json.loads(job_json.read_text())
    record["owner_pid"] = os.getppid()  # a different, live process owns it
    job_json.write_text(json.dumps(record))
    other = _manager(tmp_path, registry)
    seen = other.status(job_id)
    assert seen.state == J.RUNNING and "will record the exit status" in seen.reason
    assert json.loads(job_json.read_text())["state"] == J.RUNNING, "a non-owner must not write the outcome"

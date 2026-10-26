"""Diagnostics and provenance: parsing, readiness logic, digest agreement with the K17d script, staleness detection."""
import importlib.util
import json
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "dashboard"), str(ROOT / "src"), str(ROOT)]

from geodash import diagnostics as D  # noqa: E402
from geodash import provenance as P  # noqa: E402


def _script_module():
    spec = importlib.util.spec_from_file_location("b2_e10_k17d_identity", ROOT / "scripts" / "b2_e10_k17d_identity.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_provenance_digest_is_the_same_algorithm_as_the_k17d_script():
    assert P.package_digest()[0] == _script_module().package_digest()[0]


def test_memory_facts_are_parsed_from_meminfo_in_gib(tmp_path):
    meminfo = tmp_path / "meminfo"
    meminfo.write_text("MemTotal:       16777216 kB\nMemFree:  100 kB\nMemAvailable:    8388608 kB\n")
    facts = D.memory_facts(meminfo)
    assert facts["total_gib"] == 16.0 and facts["available_gib"] == 8.0


def test_missing_meminfo_is_reported_as_unknown_not_as_zero(tmp_path):
    facts = D.memory_facts(tmp_path / "absent")
    assert facts["total_gib"] is None and facts["available_gib"] is None


def test_storage_facts_report_free_space_and_refuse_nothing(tmp_path):
    facts = D.storage_facts({"here": tmp_path, "not-yet": tmp_path / "later" / "folder"})
    assert facts["here"]["free_gib"] is not None and facts["here"]["free_gib"] > 0
    assert facts["not-yet"]["free_gib"] is not None


def test_readiness_names_the_missing_packages_for_each_role():
    deps = {"numpy": "2", "scipy": None, "matplotlib": "3", "streamlit": "1.65", "torch": None}
    ready = D.readiness(deps)
    assert ready["gui_ready"] is False and ready["gui_missing"] == ["scipy"]
    assert ready["runner_ready"] is False and ready["runner_missing"] == ["torch"]


def test_readiness_is_true_only_when_every_required_package_is_present():
    deps = {"numpy": "2", "scipy": "1", "matplotlib": "3", "streamlit": "1.65", "torch": "2"}
    assert D.readiness(deps)["gui_ready"] and D.readiness(deps)["runner_ready"]


def test_test_results_show_the_pass_count_printed_by_pytest():
    jobs = [SimpleNamespace(key="test-dashboard", state="succeeded", job_id="j1", reason="ok",
                            log_tail=["...", "76 passed in 12.3s"])]
    rows = {r["key"]: r for r in D.last_test_results(jobs)}
    assert rows["test-dashboard"]["summary"] == "76 passed in 12.3s"
    assert rows["test-cpu-execution"]["state"] == "never run"


def test_gpu_presence_is_reported_as_cpu_only_and_says_no_gpu_work_runs(tmp_path):
    empty_dev = tmp_path / "dev"
    empty_dev.mkdir()
    gpu = D.gpu_facts(which=lambda name: None, device_dir=empty_dev)
    assert gpu["mode"] == "CPU only"
    assert gpu["status"] == "no NVIDIA driver tool or device found"
    (empty_dev / "nvidia0").write_text("")
    present = D.gpu_facts(which=lambda name: None, device_dir=empty_dev)
    assert "no GPU work is run" in present["status"] and present["device_nodes"] == ["nvidia0"]


def test_committed_k17d_record_agrees_with_the_current_source_tree():
    checks = {c.name: c for c in P.check_k17d_record()}
    assert checks["K17d record bound to current src/geosim"].status == P.OK
    assert all(c.status == P.OK for c in checks.values() if c.name.startswith("source hash"))


def test_a_record_from_different_source_is_reported_stale_not_repaired(tmp_path):
    fake = tmp_path / "repo"
    shutil.copytree(ROOT / "src" / "geosim", fake / "src" / "geosim", ignore=shutil.ignore_patterns("__pycache__", "data"))
    (fake / "docs" / "results").mkdir(parents=True)
    record = {"schema": "B2-E10-k17d-identity-record/1", "package_sha256": "0" * 64,
              "source_sha256": {}, "observation_reads": 0, "waveform_synthesis_calls": 0}
    path = fake / "docs" / "results" / "b2_e10_k17d_identity.json"
    path.write_text(json.dumps(record))
    checks = {c.name: c for c in P.check_k17d_record(fake)}
    assert checks["K17d record bound to current src/geosim"].status == P.STALE
    assert json.loads(path.read_text()) == record, "the dashboard must never edit a record"


def test_a_record_that_crosses_the_observation_boundary_fails(tmp_path):
    fake = tmp_path / "repo"
    (fake / "docs" / "results").mkdir(parents=True)
    record = {"schema": "x", "package_sha256": P.package_digest(ROOT)[0], "source_sha256": {},
              "observation_reads": 2, "waveform_synthesis_calls": 0}
    (fake / "docs" / "results" / "b2_e10_k17d_identity.json").write_text(json.dumps(record))
    shutil.copytree(ROOT / "src" / "geosim", fake / "src" / "geosim", ignore=shutil.ignore_patterns("__pycache__"))
    checks = {c.name: c for c in P.check_k17d_record(fake)}
    boundary = [c for c in checks.values() if "boundary" in c.name]
    assert boundary and boundary[0].status == P.FAILED


def test_the_gate_invariants_hold_on_the_committed_records():
    check = P.check_gate_invariants()
    assert check.status == P.OK, check.detail


def test_no_provenance_check_fails_on_the_committed_repository():
    failed = [c for c in P.all_checks() if c.status == P.FAILED]
    assert failed == [], [f"{c.name}: {c.detail}" for c in failed]

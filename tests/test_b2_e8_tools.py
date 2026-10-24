"""E8 (P32): read-only host inventory, width-explicit budget arithmetic, the UNAPPROVED candidate configuration, the probe
specification and the repository facts the E8 documents cite. Nothing here generates data, trains, or touches a GPU.
"""
import copy
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).parents[1]
PLAN = ROOT / "docs" / "plan"
sys.path.insert(0, str(ROOT / "scripts"))


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


inv = load("b2_host_inventory")
bud = load("b2_e8_budget")
pre = inv.pre
GIB = 2 ** 30


def facts(cpus=4, ram=16.0, free=40.0, gpu=None, wheels=("nvidia-cublas",), device=1, cgroup_cpu=None, cgroup_ram=None):
    return {"cpu": {"logical_cpus": cpus, "schedulable_cpus": cpus, "model": "x", "cgroup_cpu_quota": cgroup_cpu},
            "memory": {"total_gib": ram, "available_gib": ram, "cgroup_limit_gib": cgroup_ram},
            "disks": [{"path": "ROOT", "queried": "/", "device": device, "total_gib": 100.0, "free_gib": free},
                      {"path": "BACKUP", "queried": "/", "device": device + 1, "total_gib": 100.0, "free_gib": 50.0}],
            "gpu": {"devices": gpu or [], "device_nodes": [], "note": None if gpu else "nvidia-smi is not installed or not on PATH"},
            "libraries": {"torch": "2.14.1", "numpy": "2.5.4", "scipy": "1.18.1", "xgboost-cpu": "3.4.1", "nvidia_runtime_wheels": list(wheels)}}


def status(report):
    return {c["id"]: c["status"] for c in report["checks"]}


# ---- host inventory -------------------------------------------------------------------------------------------

def test_host_inventory_is_read_only_and_never_designates_a_host(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    before = sorted(p.name for p in tmp_path.iterdir())
    report = inv.build_report("training", ["ROOT"], "BACKUP", facts=facts())
    assert sorted(p.name for p in tmp_path.iterdir()) == before
    inv.collect(["ROOT", "nested/ROOT"], "BACKUP")                       # the real collectors, not injected facts
    assert sorted(p.name for p in tmp_path.iterdir()) == before          # nothing was created, not even the queried paths
    done = subprocess.run([sys.executable, "-I", "-c", "import sys; sys.path.insert(0, %r); import b2_host_inventory; "
                           "raise SystemExit(int('torch' in sys.modules))" % str(ROOT / "scripts")], capture_output=True)
    assert done.returncode == 0                                          # importing the inventory never loads torch
    assert report["read_only"] is True and report["gpu_computation_performed"] is False
    assert report["host_designated"] is False and report["production_authorized"] is False and report["benchmark_complete"] is False
    assert report["requirements_status"] == "PROPOSED_UNAPPROVED" and status(report)["host.designation"] == pre.BLOCKED
    json.dumps(report, allow_nan=False)
    source = (ROOT / "scripts" / "b2_host_inventory.py").read_text()
    assert "import torch" not in source and "mkdtemp" not in source and "os.replace" not in source


def test_a_missing_gpu_is_blocked_and_a_measured_shortfall_fails():
    training = inv.build_report("training", ["ROOT"], facts=facts())
    assert status(training)["host.gpu"] == pre.BLOCKED and training["verdict"] == pre.BLOCKED
    short = inv.build_report("training", ["ROOT"], facts=facts(ram=8.0, free=10.0))
    assert status(short)["host.ram"] == pre.FAIL and status(short)["host.working_disk"] == pre.FAIL and short["verdict"] == pre.FAIL
    small = inv.build_report("training", ["ROOT"], facts=facts(gpu=[{"name": "g", "memory_gib": 6.0, "driver": "1", "compute_capability": "8.0"}]))
    assert status(small)["host.gpu"] == pre.FAIL
    fine = inv.build_report("training", ["ROOT"], facts=facts(gpu=[{"name": "g", "memory_gib": 24.0, "driver": "1", "compute_capability": "8.0"}]))
    assert status(fine)["host.gpu"] == pre.PASS and fine["verdict"] == pre.BLOCKED      # still undesignated: never PASS overall


def test_backup_must_be_a_different_device_and_container_limits_count():
    same = facts()
    same["disks"][1]["device"] = same["disks"][0]["device"]
    assert status(inv.build_report("generation", ["ROOT"], "BACKUP", facts=same))["host.backup"] == pre.FAIL
    assert status(inv.build_report("generation", ["ROOT"], "BACKUP", facts=facts()))["host.backup"] == pre.PASS
    assert status(inv.build_report("generation", ["ROOT"], facts=facts()))["host.backup"] == pre.BLOCKED
    assert status(inv.build_report("generation", ["ROOT"], "BACKUP", facts=facts(cgroup_cpu=1.5)))["host.cpu"] == pre.FAIL
    assert status(inv.build_report("generation", ["ROOT"], "BACKUP", facts=facts(ram=64.0, cgroup_ram=4.0)))["host.ram"] == pre.FAIL


def test_requirements_are_the_proposed_ceilings_of_the_e5_plan():
    c = pre.PROPOSED_CEILINGS
    assert inv.REQUIREMENTS["generation"]["working_disk_gib"] == c["working_disk_gib"] == 25
    assert inv.REQUIREMENTS["generation"]["backup_disk_gb"] == c["backup_disk_gb"] == 9
    assert inv.REQUIREMENTS["training"]["ram_gib"] == c["host_ram_gib_training"] == 16
    assert inv.REQUIREMENTS["training"]["gpu_vram_gib_minimum"] == 8 and c["authorized"] is False


def test_gpu_query_is_one_fixed_driver_call_and_parses_output():
    calls = []

    def run(argv, **kwargs):
        calls.append((argv, kwargs))
        return SimpleNamespace(returncode=0, stdout="NVIDIA A100, 40960, 550.54, 8.0\n")

    found = inv.gpu_facts(which=lambda name: "/usr/bin/nvidia-smi", run=run, glob=lambda: ["nvidia0"])
    assert found["devices"] == [{"name": "NVIDIA A100", "memory_gib": 40.0, "driver": "550.54", "compute_capability": "8.0"}]
    assert len(calls) == 1 and calls[0][0][1:] == inv.GPU_QUERY[1:] and calls[0][1]["timeout"] == inv.GPU_QUERY_TIMEOUT_S
    never = inv.gpu_facts(which=lambda name: None, run=lambda *a, **k: pytest.fail("must not run without nvidia-smi"), glob=lambda: [])
    assert never["devices"] == [] and "not installed" in never["note"]
    broken = inv.gpu_facts(which=lambda name: "/x", run=lambda *a, **k: SimpleNamespace(returncode=9, stdout=""), glob=lambda: [])
    assert broken["devices"] == [] and "exited 9" in broken["note"]


def test_cli_creates_the_report_exclusively_and_exits_by_verdict(tmp_path, capsys):
    out = tmp_path / "report.json"
    code = inv.main(["--role", "generation", "--path", str(tmp_path / "root"), "--out", str(out), "--allow-blocked"])
    assert code in (0, 3) and json.loads(out.read_text())["schema"] == inv.SCHEMA
    assert inv.main(["--role", "generation", "--path", str(tmp_path), "--out", str(out)]) == 2          # no overwrite
    assert not (tmp_path / "root").exists()                                                             # nothing created for the path


# ---- budget ---------------------------------------------------------------------------------------------------

def test_budget_withdraws_the_width8_reservation_and_scales_by_the_mac_ratio():
    out = bud.build()
    assert out["status"] == "ARITHMETIC_NOT_A_RESERVATION" and out["production_authorized"] is False and "6 GPU-h" in out["withdrawn_figure"]
    w8, w16 = (out["widths"][k]["campaigns"][0] for k in ("8", "16"))
    assert w8["train_sample_passes"] == w16["train_sample_passes"] == 3_240_000
    ratio = bud.MACS_G[16] / bud.MACS_G[8]
    assert w8["gpu_pure_compute_hours_screening"] == [0.9, 4.5]
    assert w16["gpu_pure_compute_hours_screening"][0] == pytest.approx(0.9 * ratio, abs=0.02)
    assert w16["gpu_pure_compute_hours_screening"][1] == pytest.approx(4.5 * ratio, abs=0.02)
    assert w16["synchronous_loader_hours"] == w8["synchronous_loader_hours"] == pytest.approx(6.97, abs=0.01)
    low, high = w16["gpu_compute_plus_loader_hours_screening"]
    assert low / 6.0 == pytest.approx(1.66, abs=0.02) and high / 6.0 == pytest.approx(3.65, abs=0.02)   # the '1.7 - 3.7 x the old 6 GPU-h' of the assessment
    assert out["widths"]["16"]["center_term_ratio_p20_over_p21b"] == 128 and out["widths"]["8"]["center_term_ratio_p20_over_p21b"] == 64
    assert [c["fits"] for c in out["widths"]["16"]["campaigns"]] == [9, 21, 63]
    json.dumps(out, allow_nan=False)


def test_budget_inputs_still_match_the_cited_proposal_and_the_committed_result():
    proposal_text = (PLAN / "B2_E7_TRAINING_SPEC_PROPOSAL.md").read_text()
    for value in bud.MACS_G.values():
        assert f"{value:g}" in (PLAN / "b2_e7_training_proposal.json").read_text() or f"{value:.3f}" in proposal_text
    assert "93 s per epoch" in proposal_text and bud.LOADER_S_PER_EPOCH == 93.0
    committed = json.loads((ROOT / "docs/results/b2_e8_resource_budget.json").read_text())
    assert committed == bud.build()


# ---- candidate configuration and probe specification -----------------------------------------------------------

CANDIDATE = PLAN / "b2_e8_candidate_production_config.json"


def test_candidate_config_is_unapproved_and_equals_the_e7_proposal_values():
    cfg = json.loads(CANDIDATE.read_text())
    proposal = json.loads((PLAN / "b2_e7_training_proposal.json").read_text())["parameters"]
    assert cfg["status"] == "UNAPPROVED_NOT_FROZEN" and cfg["frozen"] is False and cfg["approved"] is False and cfg["benchmark_complete"] is False
    assert cfg["p18_section_10_entry_needed_if_approved_as_is"].startswith("NONE_FOR_HYPERPARAMETERS")
    for key, record in cfg["training"].items():
        if key not in proposal:                                              # plan_consistency: added by E8, not an E7 record
            assert key == "plan_consistency" and record["status"] == "UNAPPROVED"
            continue
        assert record["value"] == proposal[key]["value"], key
        if proposal[key]["needs_researcher_approval"]:
            assert record["status"] == "UNAPPROVED" and record["decision"], key
        else:
            assert record["status"] == "FROZEN_BY_PROTOCOL", key
    assert cfg["training"]["model_width"]["value"] == 16 and cfg["training"]["epochs"]["value"] == 30
    assert cfg["training"]["batch_size"]["value"] == 32 and cfg["training"]["training_seed_values"]["value"] == [0, 1, 2]
    assert all(v["status"] == "UNAPPROVED" for v in cfg["decision_recommendations"].values())
    assert cfg["numerics_pin"]["status"] == "UNAPPROVED" and cfg["numerics_pin"]["cudnn_allow_tf32"]["recommended"] is False
    assert cfg["authorization"] == {"K18": "PENDING_RESEARCHER", "K17d": "PENDING_RESEARCHER", "OBS-CANCEL-2": "PENDING_RESEARCHER",
                                    "full_generation": "NOT_AUTHORIZED", "full_gpu_training": "NOT_AUTHORIZED", "full_loko_sweep": "NOT_AUTHORIZED"}


def test_candidate_recipe_values_are_trainconfig_defaults_and_loss_values_are_the_p20_config():
    from geoml.train import TrainConfig
    default, cfg = TrainConfig(labels=("a", "b")), json.loads(CANDIDATE.read_text())["training"]
    assert (default.width, default.epochs, default.batch) == (cfg["model_width"]["value"], cfg["epochs"]["value"], cfg["batch_size"]["value"])
    assert default.plan_consistency is False and cfg["plan_consistency"]["value"] is True        # code default: plan head inactive
    assert default.time_pool == cfg["time_pool"]["value"] and default.level == cfg["level"]["value"] and default.plan_loss_weight == 1.0
    assert default.center_loss_weight == 0.0 and default.plan_shift_fraction == 0.0          # NOT code defaults: they come from the P20 config
    pilot = json.loads((ROOT / "configs/b2_feat.json").read_text())["training"]
    assert pilot["center_loss_weight"] == cfg["center_loss_weight"]["value"] and pilot["plan_loss_weight"] == cfg["plan_loss_weight"]["value"]
    assert pilot["plan_shift_fraction"] == cfg["plan_shift_augmentation"]["value"]["fraction"]
    assert pilot["plan_shift_max_hz"] == cfg["plan_shift_augmentation"]["value"]["max_hz"]


def test_candidate_config_cannot_be_loaded_by_any_runner_and_is_not_under_configs():
    from geoml.b2_experiment import B2ExperimentConfig
    assert CANDIDATE.parent.name == "plan" and not list((ROOT / "configs").glob("*e8*"))
    with pytest.raises((ValueError, KeyError, TypeError)):
        B2ExperimentConfig.from_file(CANDIDATE)


def test_gpu_probe_is_a_specification_without_an_executor():
    spec = json.loads((PLAN / "b2_e8_gpu_probe_spec.json").read_text())
    assert spec["status"] == "SPECIFICATION_ONLY" and spec["executor"] == "NOT_IMPLEMENTED" and spec["authorized"] is False and spec["approval"] is None
    assert set(spec["preconditions"]["data_roles_forbidden"]) == {"val-calib", "test", "B2-test/1", "B2-match/1"}
    assert set(spec["preconditions"]["data_roles_allowed"]) == {"train", "val-select"}
    caps = spec["caps"]
    assert caps["max_wall_seconds_total"] <= 1800 and caps["max_gpu_devices"] == 1 and caps["retained_checkpoints"] == 0
    assert caps["max_timed_steps_per_configuration"] <= 400 and caps["max_epochs_equivalent"] <= 2
    assert {c["width"] for c in spec["configurations"]} <= {8, 16} and any(c["width"] == 16 for c in spec["configurations"])
    assert "applies no pass/fail" in spec["pre_registered_use_of_results"]["ceilings"]
    # Tripwire, not a permanent rule: the E9 executor milestone adds a probe harness and must update this assertion and the spec's `executor` field.
    assert not [p for p in ROOT.glob("scripts/*probe*") if p.name != "opendpd_probe.py"] and not list(ROOT.glob("src/**/*probe*"))
    assert len(spec["configurations"]) * caps["max_wall_seconds_per_configuration"] <= caps["max_wall_seconds_total"]


# ---- fail-closed facts and records the E8 documents cite -------------------------------------------------------------

def test_authorization_reads_only_the_four_gate_approvals_so_the_release_gate_is_a_process_step():
    sup = load("b2_production_supervisor")
    gates, memo = pre._read_json(ROOT / pre.GATES_PATH), pre._read_json(ROOT / pre.MEMO_PATH)
    assert sup.authorization(gates, memo)[0] is False and sup.PRODUCTION_LAUNCH_ENABLED is False
    assert sup.PRODUCTION_GATES == ("K18", "K17d", "OBS-CANCEL-2", "full_generation")
    gates, memo = copy.deepcopy(gates), copy.deepcopy(memo)
    record = {"approved_by": "researcher", "approved_at": "2026-10-30T00:00:00Z", "decision": "x", "record": "r"}
    for key in sup.PRODUCTION_GATES:
        full = key == "full_generation"
        gates["decisions"][key].update(status="AUTHORIZED" if full else "APPROVED",
                                       approval=dict(record, wall_hours=36, core_hours=42, working_disk_gib=25, backup_disk_gb=9) if full else record)
        memo["decisions"][key].update(status="AUTHORIZED" if full else "APPROVED")
    assert sup.authorization(gates, memo)[0] is True                         # no R1-R10 or review record is consulted ...
    with pytest.raises(sup.SupervisorError, match="unbounded stage command"):   # ... which is why launch itself is impossible in this build
        sup.stage_argv("known", sup.build_plan(Path("/nonexistent"), mode="production", groups_per_shard=4), Path("/nonexistent"))


def test_execution_caps_and_device_refusal_cited_by_the_documents_still_hold():
    from geoml import b2_execution, b2_experiment
    assert b2_execution.CAPS == {"groups_per_role": 2, "epochs": 2, "width": 8, "batch": 32}
    with pytest.raises(ValueError, match="CPU-only"):
        b2_execution._cpu("cuda")
    assert b2_experiment.LEGACY_MAX_GROUPS == 12


def test_no_source_pins_tf32_or_deterministic_algorithms_yet():
    """The R6 numerics pin belongs to the executor milestone; if it lands, update the documents and this test with it."""
    pattern = re.compile(r"allow_tf32|use_deterministic_algorithms|cudnn\.deterministic")
    own = {"b2_host_inventory.py", "b2_training_footprint.py"}                     # mention the flags in prose/reporting only
    hits = [str(path.relative_to(ROOT)) for path in [*(ROOT / "src").rglob("*.py"), *(ROOT / "scripts").glob("*.py")]
            if path.name not in own and pattern.search(path.read_text())]
    assert hits == []


def test_records_carry_the_pr24_ci_and_leave_every_gate_unchanged():
    gates = json.loads((PLAN / "b2_readiness_gates_2026-10-21.json").read_text())
    ci = gates["engineering"]["e7b_head_ci"]
    assert ci["run_id"] == 40064513568 and ci["job_id"] == 120784837702 and ci["total_passed"] == 1771 and ci["total_skipped"] == 7
    assert ci["status"] == "VERIFIED_SUCCESS_ON_MERGED_PR_24_HEAD" and gates["verified_remote_main"]["sha"].startswith("4a1cc95")
    assert gates["benchmark_complete"] is False and gates["engineering"]["e8_freeze_preparation"]["go_no_go"] == "NO_GO"
    expected = {"K18": "PENDING_RESEARCHER", "K17d": "PENDING_RESEARCHER", "OBS-CANCEL-2": "PENDING_RESEARCHER",
                "full_generation": "NOT_AUTHORIZED", "full_gpu_training": "NOT_AUTHORIZED", "full_loko_sweep": "NOT_AUTHORIZED"}
    assert {k: gates["decisions"][k]["status"] for k in expected} == expected
    assert all(gates["decisions"][k]["approval"] is None for k in expected)
    proposal = json.loads((PLAN / "b2_e7_training_proposal.json").read_text())
    assert proposal["frozen"] is False and proposal["approved"] is False and all(r["approval"] is None for r in proposal["parameters"].values())


def test_the_documents_link_only_files_that_exist():
    for name in ("B2_E8_DECISION_APPROVAL.md", "B2_E8_HOST_RESOURCE_ASSESSMENT.md", "B2_E8_GO_NO_GO.md", "P32_b2_e8_freeze_preparation.md"):
        text = (PLAN / name).read_text()
        for target in re.findall(r"\]\(([^)#]+?)(?:#[^)]*)?\)", text):
            if not target.startswith("http"):
                assert (PLAN / target).resolve().exists(), (name, target)

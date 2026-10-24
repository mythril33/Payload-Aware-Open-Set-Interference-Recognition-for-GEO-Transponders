"""E9: static scientific protocol approval only; no generation, GPU, fitting or LOKO."""
import json
from pathlib import Path

from geoml import b2_execution

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "docs" / "plan"


def _data(filename):
    return json.loads((PLAN / filename).read_text())


def test_researcher_scientific_decisions_match_both_gate_records():
    freeze = _data("b2_e9_approved_scientific_protocol.json")
    gates = _data("b2_readiness_gates_2026-10-21.json")
    memo = _data("b2_e5_decision_recommendations.json")
    assert freeze["schema"] == "B2-E9-scientific-freeze/1"
    assert freeze["scientific_approval"] is True
    assert freeze["activation"] is False and freeze["production_authorized"] is False
    assert freeze["benchmark_complete"] is gates["benchmark_complete"] is memo["benchmark_complete"] is False
    assert len(freeze["decisions"]) == 13
    for key in ("K18", "K17d", "OBS-CANCEL-2"):
        approval = gates["decisions"][key]["approval"]
        assert gates["decisions"][key]["status"] == memo["decisions"][key]["status"] == "APPROVED"
        assert approval["record"] == freeze["approval_record"]
        assert approval["approved_by"] == memo["decisions"][key]["approved_by"] == freeze["approved_by"]
        assert approval["approved_at"] == memo["decisions"][key]["approved_at"] == freeze["approved_at"]
    for key in ("full_generation", "full_gpu_training", "full_loko_sweep"):
        assert gates["decisions"][key]["status"] == memo["decisions"][key]["status"] == "NOT_AUTHORIZED"
        assert gates["decisions"][key]["approval"] is None
    assert freeze["unresolved_operational_decisions"]["gpu_probe"] == "NOT_AUTHORIZED"


def test_all_e7_parameters_have_status_and_resource_estimates_remain_unapproved():
    freeze = _data("b2_e9_approved_scientific_protocol.json")
    proposal = _data("b2_e7_training_proposal.json")
    candidate = _data("b2_e8_candidate_production_config.json")
    params = freeze["parameter_records"]
    assert len(params) == len(proposal["parameters"]) == 29
    assert set(params) == set(proposal["parameters"])
    for key, item in proposal["parameters"].items():
        status = params[key]["status"]
        if item.get("approval_group") == "DR-05":
            assert status == "RESOURCE_NOT_AUTHORIZED"
            assert params[key]["approved_by"] is None
        elif item["needs_researcher_approval"]:
            assert status == "RESEARCHER_APPROVED"
            assert params[key]["approval_group"] in ("R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8", "R9", "R10")
        else:
            assert status == "EXISTING_FROZEN_CONTRACT"
    assert candidate["status"] == "UNAPPROVED_NOT_FROZEN"
    assert candidate["frozen"] is False and candidate["approved"] is False
    assert candidate["authorization"]["full_generation"] == "NOT_AUTHORIZED"
    assert freeze["parameter_records"]["precision_and_determinism"]["value"]["cudnn_allow_tf32"] is False
    assert freeze["parameter_records"]["precision_and_determinism"]["value"]["matmul_allow_tf32"] is False


def test_r6_and_r8_security_contracts_are_explicit_and_production_stays_capped():
    freeze = _data("b2_e9_approved_scientific_protocol.json")
    d = freeze["decisions"]
    assert d["R1"]["n_fits"] == 9
    assert d["R2"]["width"] == 16
    assert d["R4"]["epochs"] == 30 and d["R5"]["batch_size"] == 32
    assert d["R6"]["cudnn_allow_tf32"] is d["R6"]["matmul_allow_tf32"] is False
    assert d["R8"]["test_driven_retuning"] is False
    assert d["R9"]["carry_partial_state"] is False and d["R9"]["restart_epoch"] == 0
    assert d["R10"]["known_acceptance_target"] == 0.95
    assert d["R10"]["clean_alarm_pfa"] == 0.05
    assert d["R10"]["mahalanobis_regularization"] == 0.1
    assert b2_execution.CAPS == {"groups_per_role": 2, "epochs": 2, "width": 8, "batch": 32}
    assert "B2-R6-fp32-tf32-off/1" in (PLAN / "P18_b2_protocol.md").read_text()

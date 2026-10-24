"""E10 committed-record tests: K17d identity record self-consistency, metadata tampering, and gate invariants.

CPU-only. Reads only committed JSON summaries. No held-out observation, checkpoint or artifact is opened.
"""
import copy
import json
from pathlib import Path

import pytest

from geosim import b2_k17d as K

ROOT = Path(__file__).parents[1]
RECORD = ROOT / "docs" / "results" / "b2_e10_k17d_identity.json"
AUDIT = ROOT / "docs" / "results" / "k17d_drift_audit.json"
APPROVED = ROOT / "docs" / "plan" / "b2_e9_approved_scientific_protocol.json"


@pytest.fixture(scope="module")
def record():
    return json.loads(RECORD.read_text())


@pytest.fixture(scope="module")
def audit():
    return json.loads(AUDIT.read_text())


def test_record_declares_no_observation_read_and_no_authorization(record):
    assert record["observation_reads"] == 0
    assert record["waveform_synthesis_calls"] == 0
    assert record["authorizes"].startswith("nothing")
    assert record["status"].endswith("PENDING_RESEARCHER_ACCEPTANCE")


def test_record_counts_are_the_approved_arithmetic(record):
    assert record["counts"] == {"headline": 500, "co_feed_missing": 35, "sensitivity": 465,
                                "cross_feed_missing": 43, "missing_total": 78}
    assert len(record["co_feed_missing_ids"]) == 35
    assert len(record["sensitivity_ids"]) == 465
    assert len(record["co_feed_missing_ids"]) + len(record["sensitivity_ids"]) == 500


def test_record_fingerprints_recompute_from_its_own_lists(record):
    ids = record["co_feed_missing_ids"]
    assert record["fingerprints"]["co_feed_missing_ids"] == K.sha256_of(ids)
    assert record["fingerprints"]["sensitivity_ids"] == K.sha256_of(record["sensitivity_ids"])
    assert ids == sorted(ids) and len(set(ids)) == len(ids)


def test_record_agrees_with_the_committed_audit(record, audit):
    assert record["audit_cross_check"]["agrees"] is True
    assert K.cross_check_audit({"co_feed_missing_ids": record["co_feed_missing_ids"],
                                "cross_feed_missing_ids": record["cross_feed_missing_ids"]}, audit)["agrees"]


def test_tampering_with_one_co_feed_id_is_detected(record, audit):
    tampered = copy.deepcopy(record)
    tampered["co_feed_missing_ids"][0] = tampered["co_feed_missing_ids"][0] + 1  # keeps 35, moves one ID
    assert K.sha256_of(tampered["co_feed_missing_ids"]) != record["fingerprints"]["co_feed_missing_ids"]
    with pytest.raises(K.K17dError):
        K.cross_check_audit({"co_feed_missing_ids": sorted(tampered["co_feed_missing_ids"]),
                             "cross_feed_missing_ids": record["cross_feed_missing_ids"]}, audit)


def test_tampering_with_an_audit_polarization_is_detected(record, audit):
    tampered = copy.deepcopy(audit)
    tampered["rows"][0]["pol"] = 1 - tampered["rows"][0]["pol"]
    with pytest.raises(K.K17dError):
        K.cross_check_audit({"co_feed_missing_ids": record["co_feed_missing_ids"],
                             "cross_feed_missing_ids": record["cross_feed_missing_ids"]}, tampered)


def test_gate_invariants_are_unchanged_by_this_change():
    approved = json.loads(APPROVED.read_text())
    assert approved["benchmark_complete"] is False
    assert approved["production_authorized"] is False
    assert approved["activation"] is False
    assert approved["unresolved_operational_decisions"] == {
        "full_generation": "NOT_AUTHORIZED", "gpu_probe": "NOT_AUTHORIZED", "full_gpu_training": "NOT_AUTHORIZED",
        "full_loko_sweep": "NOT_AUTHORIZED", "production_launch": "DISABLED", "merge_to_main": "REVIEW_REQUIRED"}


def test_contract_still_refuses_every_execution_action():
    from geoml import b2_e9_contract as contract
    assert contract.runtime_permitted() is False
    for action in contract.ACTIONS:
        with pytest.raises(contract.ExecutionNotAuthorized):
            contract.guard_execution(action)

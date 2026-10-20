"""Paired B2 scenes, event stages and independent missing-carrier semantics."""
from copy import deepcopy
from dataclasses import asdict
import json

import numpy as np
import pytest

from geosim import b2_scenarios as scenes
from geosim.b2_protocol import BASE_PROTOCOL, PROTOCOL, B2Config, LABELS
from geosim.dual import DualScenarioResult
from geosim.scenario import default_plan
from geosim.waveform import Carrier

GROUP = 3_000_000


def canonical_scene(scene):
    cfg = deepcopy(scene.cfg.to_dict())
    cfg["co"]["ibo_db"] = scene.metadata["nominal_ibo_db"][0]
    cfg["uplink_xpd_db"] = 30.0
    return cfg


def test_eight_variants_share_plans_link_noise_phase_and_missing_state():
    variants = [scenes.prepare_scene(label, GROUP, missing_carrier=True) for label in LABELS]
    reference = variants[0]
    for label, scene in zip(LABELS, variants):
        assert canonical_scene(scene) == canonical_scene(reference)
        assert scene.plans == reference.plans
        assert scene.active_carriers == reference.active_carriers
        assert scene.metadata["operator_plan_source"] == reference.metadata["operator_plan_source"]
        assert scene.metadata["nominal_ibo_db"] == reference.metadata["nominal_ibo_db"]
        assert scene.plan_consistency == 1
        assert sum(not item for mask in scene.active_carriers for item in mask) == 1
        assert scene.metadata["protocol"] == BASE_PROTOCOL
        assert scene.metadata["parent_protocol"] == PROTOCOL
        assert scene.metadata["label"] == label
        assert scene.metadata["scenario_id"] == GROUP
        assert scene.metadata["role"] == "train"
        assert scene.interferers[1] is None
        json.dumps(scene.metadata, allow_nan=False)
    assert variants[LABELS.index("cross_pol")].cfg.uplink_xpd_db == 10.0
    assert 1 <= variants[LABELS.index("overdrive")].cfg.co.ibo_db <= 4
    assert all(9 <= variant.cfg.co.ibo_db <= 13 for label, variant in zip(LABELS, variants) if label != "overdrive")
    assert variants[LABELS.index("adjacent_satellite")].event["injection_stage"] == "uplink"
    assert variants[LABELS.index("carrier_under_carrier")].event["victim_active"] is True


def test_missing_override_preserves_plan_event_and_link_parameters():
    all_active = scenes.prepare_scene("cw", GROUP, missing_carrier=False)
    missing = scenes.prepare_scene("cw", GROUP, missing_carrier=True)
    assert all_active.cfg.to_dict() == missing.cfg.to_dict()
    assert all_active.plans == missing.plans
    assert all_active.event == missing.event
    assert all_active.plan_consistency == 0
    assert missing.plan_consistency == 1
    assert all(all(mask) for mask in all_active.active_carriers)
    assert sum(not flag for mask in missing.active_carriers for flag in mask) == 1
    assert any(missing.active_carriers[0])
    assert all(np.isclose(sum(carrier.power for carrier in plan), 1) for plan in missing.plans)


def test_event_ranges_and_replay_include_observable_power_conventions():
    for label in LABELS:
        first = scenes.prepare_scene(label, 3_100_000)
        again = scenes.prepare_scene(label, 3_100_000)
        assert first.metadata == again.metadata
        assert first.cfg.to_dict() == again.cfg.to_dict()
        assert first.active_carriers == again.active_carriers
        event = first.event
        if label in ("cw", "swept_cw"):
            assert 5 <= event["c_over_i_db"] <= 35
        if label == "cw":
            assert abs(event["f0"]) <= 0.48 * 36e6
            assert abs(event["drift_hz_per_s"]) <= 5e4
        elif label == "swept_cw":
            assert 1e6 <= event["f_hi"] - event["f_lo"] <= 0.9 * 36e6
            assert 0.1 <= event["period"] <= 1.28
        elif label == "unauthorized":
            assert -10 <= event["psd_offset_db"] <= 3
            assert event["c_over_i_psd_db"] == -event["psd_offset_db"]
            assert not scenes.it.overlaps_plan(event["f_lo"], event["f_hi"], first.plans[0])
        elif label == "carrier_under_carrier":
            assert 5 <= event["c_over_i_db"] <= 30
            assert first.active_carriers[0][event["victim_index"]]
        elif label == "adjacent_satellite":
            assert 0.2 <= event["overlap_fraction"] <= 0.8
            assert event["geometry"]["c_over_i_psd_db"] == event["c_over_i_psd_db"]
        if first.interferers[0] is not None:
            assert event["power_reference"] == "total_planned_uplink"
            assert event["injection_stage"] == "uplink"


def test_common_plan_retry_is_bounded_and_catches_only_explicit_infeasibility(monkeypatch):
    actual = scenes.it.random_unauthorized
    attempts = []

    def fail_once(*args, **kwargs):
        attempts.append(1)
        if len(attempts) == 1:
            raise scenes.it.InfeasibleCarrierError("forced gap test")
        return actual(*args, **kwargs)

    monkeypatch.setattr(scenes.it, "random_unauthorized", fail_once)
    plans, source = scenes._plans(GROUP, 36e6)
    assert source["co_rejected_plan_draws"] == 1
    assert source["co_retry_rng_entropy"] == [GROUP, 1810, 1]
    assert plans[1] == default_plan(2 * GROUP + 1, 36e6)
    assert plans[0] != default_plan(2 * GROUP, 36e6)

    def broken(*args, **kwargs):
        raise RuntimeError("waveform implementation bug")

    monkeypatch.setattr(scenes.it, "random_unauthorized", broken)
    with pytest.raises(RuntimeError, match="implementation bug"):
        scenes._plans(GROUP, 36e6)


def test_plan_search_has_a_finite_limit(monkeypatch):
    calls = []

    def infeasible(*args, **kwargs):
        calls.append(1)
        raise scenes.it.InfeasibleCarrierError("no gap")

    monkeypatch.setattr(scenes.it, "random_unauthorized", infeasible)
    with pytest.raises(scenes.it.InfeasibleCarrierError, match="bounded"):
        scenes._plans(GROUP, 36e6)
    assert len(calls) == scenes.MAX_PLAN_DRAWS


def test_cuc_redraw_excludes_inactive_victim_without_changing_ci(monkeypatch):
    draws = []

    def draw(rng, plan, bandwidth, ci):
        draws.append(ci)
        return object(), {"victim_index": 0 if len(draws) == 1 else 1, "c_over_i_db": ci}

    monkeypatch.setattr(scenes, "carrier_under_carrier", draw)
    _, info = scenes._event("carrier_under_carrier", GROUP, [object(), object()], 36e6, [False, True])
    assert len(draws) == 2 and draws[0] == draws[1]
    assert info["victim_index"] == 1
    assert info["inactive_victim_rejected_draws"] == 1
    assert info["victim_active"] is True


def test_single_co_carrier_is_never_dropped():
    plans = ([Carrier(0, 1e6, 0.2, "QPSK", 1)], [Carrier(0, 1e6, 0.2, "QPSK", 1)])
    active, dropped = scenes._activity(GROUP, plans, B2Config(), True)
    assert active == ([True], [False])
    assert dropped == {"polarization": 1, "index": 0}


def test_sample_wires_physics_and_keeps_truth_in_metadata(monkeypatch):
    seen = {}

    def simulate(cfg, **kwargs):
        seen.update(cfg=cfg, **kwargs)
        return DualScenarioResult(np.zeros((2, 128, 512), np.float32), np.zeros((2, 512), np.float32),
                                  {"receiver_calibration_applied": True})

    monkeypatch.setattr(scenes, "simulate_dual", simulate)
    output = scenes.sample_scene("adjacent_satellite", GROUP, missing_carrier=True, keep_iq=True)
    assert seen["interferers"][0] is not None
    assert seen["interferers"][1] is None
    assert "downlink_interferers" not in seen
    assert seen["keep_iq"] is True
    assert sum(not flag for mask in seen["active_carriers"] for flag in mask) == 1
    assert output.meta["label"] == "adjacent_satellite"
    assert output.meta["plan_consistency"] == 1
    assert output.meta["receiver_calibration_applied"] is True
    assert output.spec_db.shape == (2, 128, 512)


@pytest.mark.parametrize("label,group,kwargs", [("pulsed", GROUP, {}), ("cid_overlay", GROUP, {}),
                                               ("clean", 3_300_000, {}), ("clean", 7, {}),
                                               ("clean", True, {}), ("clean", GROUP, {"missing_carrier": 1}),
                                               ("clean", GROUP, {"config": {}})])
def test_reject_unknown_family_role_or_invalid_contract(label, group, kwargs):
    with pytest.raises(ValueError):
        scenes.prepare_scene(label, group, **kwargs)

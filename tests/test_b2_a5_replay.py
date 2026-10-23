"""E4 deterministic physical replay and the frozen receiver (P28 §2, §5) on real simulator physics.

One real B2-feat/1 test-role group is generated once (the production writer, real payload chain and the real
``obs-cancel/1``); its scenes are replayed and compared with the stored shard. These tests prove execution
and physical invariants, not recognition quality.
"""
from dataclasses import replace

import numpy as np
import pytest

from geoml import b2_a5_replay as rp
from geoml.b2_a5_plan import corrupt_operator_plan, rebuild_masks
from geosim import b2_dataset as ds
from geosim import b2_matched_dataset as md
from geosim.b2_protocol import B2Config
from geosim import b2_scenarios as scenes
from geosim.cancellation import CancellationConfig, cancel_planned_carriers

GROUP = 3_200_000


@pytest.fixture(scope="module")
def artifact(tmp_path_factory):
    root = tmp_path_factory.mktemp("a5-real") / "feat"
    ds.generate_b2_dataset(root, roles=("test",), limit_groups=1, groups_per_shard=1, cancellation=CancellationConfig())
    return root


@pytest.fixture(scope="module")
def source(artifact):
    return rp.open_replay_source(artifact, "known", "test")


@pytest.fixture(scope="module")
def replayed(source):
    """Two real replays: the unauthorized scene (intruder present) and the clean scene."""
    return {label: rp.replay_scene(source, label, GROUP) for label in ("unauthorized", "clean")}


def _corruption(replay, perturbation, scope):
    context = replay.intervention_context() if perturbation == "authorize_intruder" else None
    return corrupt_operator_plan(replay.plans, perturbation=perturbation, scope=scope, scenario_id=replay.group,
                                 allowed_intervention_context=context)


def test_none_replay_reproduces_the_stored_shard_exactly(source, replayed):
    for label, replay in replayed.items():
        report = rp.check_parity(replay, source.stored(GROUP, label))
        assert report["exact"] is True
        assert report["spec"]["n_mismatch"] == report["mask"]["n_mismatch"] == report["residual"]["n_mismatch"] == 0
        assert report["metadata"]["matches"] and report["metadata"]["scenario_id"] == GROUP and report["metadata"]["label"] == label


def test_replay_is_deterministic(source, replayed):
    again = rp.replay_scene(source, "clean", GROUP)
    first = replayed["clean"]
    assert again.iq_sha256 == first.iq_sha256 and np.array_equal(again.iq, first.iq)
    assert np.array_equal(again.spec, first.spec) and np.array_equal(again.residual, first.residual)
    assert again.record == first.record


def test_replay_uses_the_artifacts_own_verified_calibration_and_cancellation(source, replayed):
    record = replayed["clean"].record
    assert record["receiver_calibration"] == source.manifest["calibration"] and record["receiver_calibration_applied"] is True
    assert record["cancellation"]["version"] == "obs-cancel/1" and record["cancellation"]["config"] == source.cancellation.to_dict()
    assert source.protocol == "B2-feat/1" and source.role == "test" and source.groups == (GROUP,)


def test_iq_is_read_only_transient_and_unchanged_by_any_belief(source, replayed):
    replay = replayed["unauthorized"]
    with pytest.raises(ValueError):
        replay.iq[0, 0, 0] = 0
    receiver = rp.FrozenReceiver(source.cancellation)
    stored = source.stored(GROUP, "unauthorized")
    before = rp._iq_hash(replay.iq)
    for perturbation, scope in (("none", "both"), ("shift_plus", "cross_only"), ("drop_one", "cross_only"),
                                ("phantom", "cross_only"), ("stale_plan", "cross_only")):
        corruption = _corruption(replay, perturbation, scope)
        assert corruption.applied
        rp.build_conditions(replay, stored, corruption, receiver)
        replay.assert_iq_unchanged()
        assert rp._iq_hash(replay.iq) == before == replay.iq_sha256
    assert "iq" not in replay.record and receiver.calls == 0


def test_none_conditions_equal_the_stored_observation(source, replayed):
    replay, stored = replayed["unauthorized"], source.stored(GROUP, "unauthorized")
    receiver = rp.FrozenReceiver(source.cancellation)
    conditions = rp.build_conditions(replay, stored, _corruption(replay, "none", "both"), receiver)
    assert receiver.calls == 0 and conditions["residual_recomputed"] is False
    for name in ("original", "MASK_ONLY", "RECEIVER_CONSISTENT"):
        observed = conditions[name]
        assert np.array_equal(observed.spec, stored.spec) and np.array_equal(observed.mask, stored.mask)
        assert np.array_equal(observed.residual, stored.residual)


def test_cross_only_keeps_the_co_residual_and_never_invokes_the_canceller(source, replayed, monkeypatch):
    calls = []
    monkeypatch.setattr(rp, "cancel_planned_carriers", lambda *a, **k: calls.append(a) or pytest.fail("canceller invoked"))
    replay, stored = replayed["unauthorized"], source.stored(GROUP, "unauthorized")
    receiver = rp.FrozenReceiver(source.cancellation)
    corruption = _corruption(replay, "drop_one", "cross_only")
    conditions = rp.build_conditions(replay, stored, corruption, receiver)
    assert not calls and receiver.calls == 0 and conditions["residual_recomputed"] is False
    assert np.array_equal(conditions["RECEIVER_CONSISTENT"].residual, stored.residual)
    assert np.array_equal(conditions["MASK_ONLY"].residual, stored.residual)
    masks = rebuild_masks(corruption.plans)
    assert np.array_equal(conditions["RECEIVER_CONSISTENT"].mask[0], stored.mask[0])          # co mask untouched
    assert not np.array_equal(conditions["RECEIVER_CONSISTENT"].mask[1], stored.mask[1])      # cross mask rebuilt
    assert np.array_equal(conditions["RECEIVER_CONSISTENT"].mask, masks)


def test_co_belief_change_recomputes_the_residual_with_the_frozen_canceller_only(source, replayed, monkeypatch):
    seen = []

    def spy(iq, plan, config=None):
        seen.append((np.array(iq), list(plan), config))
        return cancel_planned_carriers(iq, plan, config)

    monkeypatch.setattr(rp, "cancel_planned_carriers", spy)
    replay, stored = replayed["unauthorized"], source.stored(GROUP, "unauthorized")
    receiver = rp.FrozenReceiver(source.cancellation)
    corruption = _corruption(replay, "drop_one", "co_only")
    conditions = rp.build_conditions(replay, stored, corruption, receiver)
    assert receiver.calls == 1 and len(seen) == 1 and conditions["residual_recomputed"] is True
    iq, plan, config = seen[0]
    assert iq.shape == (128, 4096) and np.array_equal(iq, replay.iq[0])        # co-pol IQ only, never the cross feed
    assert plan == list(corruption.plans.co) and plan != list(replay.plans.co)  # the CORRUPTED co belief
    assert config == source.cancellation and config.version == "obs-cancel/1"
    direct = cancel_planned_carriers(replay.iq[0], list(corruption.plans.co), source.cancellation).residual_db.astype(np.float16)
    assert np.array_equal(conditions["RECEIVER_CONSISTENT"].residual, direct)
    assert not np.array_equal(conditions["RECEIVER_CONSISTENT"].residual, stored.residual)     # not the stale stored residual
    assert np.array_equal(conditions["MASK_ONLY"].residual, stored.residual)                    # the weaker control keeps it
    assert np.array_equal(conditions["MASK_ONLY"].spec, conditions["RECEIVER_CONSISTENT"].spec)
    assert np.array_equal(conditions["MASK_ONLY"].mask, conditions["RECEIVER_CONSISTENT"].mask)


def _band_db(psd, lo_hz, hi_hz):
    from geosim.plan import monitor_freqs
    f = monitor_freqs()
    inside = (f >= lo_hz) & (f <= hi_hz)
    return float(10 * np.log10(np.mean(10 ** (psd.astype(np.float64)[:, inside] / 10))))


def test_an_undeclared_transmitted_carrier_stays_in_the_recomputed_residual(source, replayed):
    """Physics sanity (not a recognition claim): the receiver cannot cancel what the plan does not declare."""
    replay, stored = replayed["clean"], source.stored(GROUP, "clean")
    corruption = _corruption(replay, "drop_one", "co_only")
    assert rp.reporting_flags(replay, corruption)["co_dropped_carrier_transmitted"] is True
    dropped = replay.plans.co[corruption.descriptors["co"]["removed_indices"][0]]
    lo, hi = dropped.f0 - dropped.occupied_bw / 2, dropped.f0 + dropped.occupied_bw / 2
    recomputed = rp.build_conditions(replay, stored, corruption, rp.FrozenReceiver(source.cancellation))["RECEIVER_CONSISTENT"]
    observed, cancelled_before, left_after = (_band_db(stored.spec[0], lo, hi), _band_db(stored.residual, lo, hi),
                                              _band_db(recomputed.residual, lo, hi))
    assert cancelled_before < observed - 8.0                    # the true plan cancels this carrier ...
    assert left_after > cancelled_before + 8.0                  # ... the corrupted plan leaves it ...
    assert abs(left_after - observed) < 1.0                     # ... at about its observed level


def test_both_scope_recomputes_once_and_rebuilds_both_masks(source, replayed):
    replay, stored = replayed["clean"], source.stored(GROUP, "clean")
    receiver = rp.FrozenReceiver(source.cancellation)
    corruption = _corruption(replay, "shift_minus", "both")
    conditions = rp.build_conditions(replay, stored, corruption, receiver)
    assert receiver.calls == 1
    observed = conditions["RECEIVER_CONSISTENT"]
    assert not np.array_equal(observed.mask[0], stored.mask[0]) and not np.array_equal(observed.mask[1], stored.mask[1])
    assert np.array_equal(observed.spec, stored.spec)                         # physical PSD is untouched


def test_simulator_is_never_given_a_belief(source, monkeypatch):
    plans_seen = []
    real = scenes.simulate_dual

    def spy(cfg, **kwargs):
        plans_seen.append(kwargs["plans"])
        return real(cfg, **kwargs)

    monkeypatch.setattr(scenes, "simulate_dual", spy)
    replay = rp.replay_scene(source, "clean", GROUP)
    assert len(plans_seen) == 1 and [list(p) for p in plans_seen[0]] == [list(replay.plans.co), list(replay.plans.cross)]
    stored = source.stored(GROUP, "clean")
    for perturbation in ("drop_one", "authorize_intruder", "stale_plan"):
        corruption = _corruption(replay, perturbation, "both")
        if corruption.applied:
            rp.build_conditions(replay, stored, corruption, rp.FrozenReceiver(source.cancellation, rp.Budget(1, 1)))
    assert len(plans_seen) == 1                                               # building conditions never simulates


def test_replay_function_has_no_belief_parameter():
    import inspect
    assert list(inspect.signature(rp.replay_scene).parameters) == ["source", "label", "group", "budget"]
    assert list(inspect.signature(rp.FrozenReceiver.residual_db).parameters) == ["self", "co_iq", "co_belief"]
    assert {f for f in rp.ObservedInputs.__dataclass_fields__} == {"spec", "mask", "residual"}


def test_parity_tolerance_policy_is_fail_closed(source, replayed):
    replay, stored = replayed["clean"], source.stored(GROUP, "clean")
    nudged = replace(replay, spec=(replay.spec.astype(np.float32) + 0.0625).astype(np.float16))
    report = rp.check_parity(nudged, stored)
    assert report["exact"] is False and report["spec"]["max_abs_diff_db"] <= rp.PARITY_ATOL_DB
    far = replace(replay, residual=(replay.residual.astype(np.float32) + 1.0).astype(np.float16))
    with pytest.raises(rp.ReplayError, match="residual: replay differs"):
        rp.check_parity(far, stored)
    with pytest.raises(rp.ReplayError, match="mask"):
        rp.check_parity(replace(replay, mask=(replay.mask.astype(np.float32) + 0.01).astype(np.float16)), stored)
    wrong_scene = source.stored(GROUP, "unauthorized")
    with pytest.raises(rp.ReplayError, match="different scenes"):
        rp.check_parity(replay, wrong_scene)
    altered = dict(replay.record, nominal_ibo_db=[9.0, 9.0])
    with pytest.raises(rp.ReplayError, match="metadata differs"):
        rp.check_parity(replace(replay, record=altered), stored)
    with pytest.raises(rp.ReplayError, match="plan-consistency"):
        rp.check_parity(replace(replay, plan_consistency=1 - replay.plan_consistency), stored)


def test_caps_are_enforced_before_the_expensive_work(source, monkeypatch):
    monkeypatch.setattr(rp, "sample_scene", lambda *a, **k: pytest.fail("simulator started despite exhausted budget"))
    with pytest.raises(rp.BudgetExceeded, match="replay cap"):
        rp.replay_scene(source, "clean", GROUP, rp.Budget(0, 5))
    with pytest.raises(rp.BudgetExceeded, match="cancellation cap"):
        rp.replay_scene(source, "clean", GROUP, rp.Budget(5, 0))
    budget = rp.Budget(2, 1)
    budget.charge_cancellation()
    with pytest.raises(rp.BudgetExceeded):
        rp.FrozenReceiver(source.cancellation, budget).residual_db(np.zeros((128, 4096), np.complex64), [])


def test_unknown_scene_requests_fail_closed(source):
    with pytest.raises(rp.ReplayError, match="not part of"):
        rp.replay_scene(source, "clean", GROUP + 1)
    with pytest.raises(rp.ReplayError, match="not part of"):
        source.sample("not_a_label", GROUP)
    with pytest.raises(rp.ReplayError, match="not part of"):
        source.stored(GROUP + 5, "clean")


def test_receiver_rejects_a_belief_the_frozen_canceller_cannot_process(source, replayed):
    from geosim.waveform import Carrier
    receiver = rp.FrozenReceiver(source.cancellation)
    with pytest.raises(rp.ReplayError, match="rejected the operator belief"):
        receiver.residual_db(replayed["clean"].iq[0], [Carrier(0.0, 7e6, 0.2, "QPSK", 1.0)])
    with pytest.raises(rp.ReplayError):
        rp.FrozenReceiver("obs-cancel/2")


def test_authorize_intruder_declares_the_physical_intruder_and_it_is_cancelled(source, replayed):
    replay, stored = replayed["unauthorized"], source.stored(GROUP, "unauthorized")
    corruption = _corruption(replay, "authorize_intruder", "co_only")
    assert corruption.applied and len(corruption.plans.co) == len(replay.plans.co) + 1
    assert replay.intervention_context() == stored.intervention_context()
    conditions = rp.build_conditions(replay, stored, corruption, rp.FrozenReceiver(source.cancellation))
    event = replay.event
    before = _band_db(stored.residual, event["f_lo"], event["f_hi"])
    after = _band_db(conditions["RECEIVER_CONSISTENT"].residual, event["f_lo"], event["f_hi"])
    assert after < before - 5.0                       # the declared carrier is now cancelled instead of left behind
    assert np.array_equal(conditions["MASK_ONLY"].residual, stored.residual)        # the weaker control cannot show this


@pytest.fixture(scope="module")
def matched_source(artifact, tmp_path_factory):
    root = tmp_path_factory.mktemp("a5-real-matched") / "matched"
    md.generate_b2_matched_dataset(root, artifact, B2Config(), limit_groups=1, groups_per_shard=1, cancellation=CancellationConfig())
    return rp.open_replay_source(root, "matched")


def test_matched_stage_replays_the_real_physics_exactly_and_authorizes_the_intruder(matched_source):
    group = matched_source.groups[0]
    assert matched_source.role == "test-matched" and matched_source.protocol == "B2-match/1"
    replay = rp.replay_scene(matched_source, "unauthorized", group)
    stored = matched_source.stored(group, "unauthorized")
    assert rp.check_parity(replay, stored)["exact"] is True
    assert replay.intervention_context() == stored.intervention_context() and "intruder" in stored.intervention_context()
    corruption = _corruption(replay, "authorize_intruder", "co_only")
    assert corruption.applied
    conditions = rp.build_conditions(replay, stored, corruption, rp.FrozenReceiver(matched_source.cancellation))
    event = replay.event
    before = _band_db(stored.residual, event["f_lo"], event["f_hi"])
    after = _band_db(conditions["RECEIVER_CONSISTENT"].residual, event["f_lo"], event["f_hi"])
    assert after < before - 5.0 and np.array_equal(conditions["MASK_ONLY"].residual, stored.residual)
    assert _corruption(rp.replay_scene(matched_source, "adjacent_satellite", group), "authorize_intruder", "co_only").status == "not_applicable"

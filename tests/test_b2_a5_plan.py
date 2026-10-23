"""E4 A5 operator-belief corruption (P28 B2-A5-plan/1): definitions, scopes, determinism, validity.

Pure tests: no simulator, no IQ, no model. A corrupted belief is a counterfactual claim to the monitor; it
is never a physical plan, so none of these tests require unit total power.
"""
import json
from dataclasses import asdict, replace

import numpy as np
import pytest

from geoml import b2_a5_plan as ap
from geoml.b2_a5_plan import OperatorPlans, corrupt_operator_plan, rebuild_masks, validate_belief
from geosim.plan import monitor_freqs, plan_mask_db
from geosim.scenario import default_plan
from geosim.waveform import Carrier

GROUP = 3_200_000


def _original(group=GROUP):
    return OperatorPlans(tuple(default_plan(2 * group, 36e6)), tuple(default_plan(2 * group + 1, 36e6)))


def _intruder_context():
    return {"label": "unauthorized", "intruder": {"f0": -7.4e6, "symbol_rate": 1.5e6, "alpha": 0.2,
                                                  "mod": "16APSK", "c_over_i_db": 17.0}}


def _apply(perturbation, scope="both", original=None, group=GROUP, context=None):
    return corrupt_operator_plan(original or _original(group), perturbation=perturbation, scope=scope,
                                 scenario_id=group, allowed_intervention_context=context)


def test_registry_is_frozen():
    assert ap.PERTURBATIONS == ("none", "shift_plus", "shift_minus", "drop_one", "phantom", "authorize_intruder", "stale_plan")
    assert ap.SCOPES == ("co_only", "cross_only", "both")
    assert ap.CONTRACT == "B2-A5-plan/1" and ap.SHIFT_HZ == 0.5e6 and ap.RNG_NAMESPACE == 1850
    assert ap.RNG_NAMESPACE not in (1801, 1810, 1813, 1820, 1830, 1840, 7051, 7052)


def test_none_returns_the_original_belief_unchanged():
    result = _apply("none")
    assert result.applied and result.plans == result.original
    assert not result.co_changed and not result.cross_changed
    assert result.to_dict()["corrupted_identity"] == result.to_dict()["original_identity"]


@pytest.mark.parametrize("name,sign", [("shift_plus", 1), ("shift_minus", -1)])
def test_shift_moves_every_carrier_by_exactly_half_a_megahertz_hz_units(name, sign):
    original = _original()
    result = _apply(name, "co_only")
    assert result.applied and result.cross_changed is False and result.co_changed
    for before, after in zip(original.co, result.plans.co):
        assert after.f0 - before.f0 == pytest.approx(sign * 500_000.0, abs=1e-6)       # Hz, not MHz
        assert replace(after, f0=before.f0) == before                                 # nothing else changes
    assert result.plans.cross == original.cross
    assert sum(c.power for c in result.plans.co) == pytest.approx(1.0)               # shift keeps the load


def test_shift_visible_in_the_mask_as_about_2_7_bins():
    original = _original()
    result = _apply("shift_plus", "co_only")
    before, after = rebuild_masks(original)[0].astype(np.float32), rebuild_masks(result.plans)[0].astype(np.float32)
    f = monitor_freqs()
    centre = lambda m: float(np.sum(f * 10 ** (m / 10)) / np.sum(10 ** (m / 10)))
    assert centre(after) - centre(before) == pytest.approx(0.5e6, rel=0.1)


def test_drop_one_removes_exactly_one_without_renormalizing():
    original = _original()
    result = _apply("drop_one", "co_only")
    assert result.applied and len(result.plans.co) == len(original.co) - 1
    removed = result.descriptors["co"]["removed_indices"]
    assert len(removed) == 1
    kept = [c for i, c in enumerate(original.co) if i != removed[0]]
    assert list(result.plans.co) == kept                                              # powers untouched, order kept
    assert sum(c.power for c in result.plans.co) < 1.0 - 1e-9                         # no undocumented renormalization
    assert result.plans.cross == original.cross


def test_drop_one_is_not_applicable_to_a_single_carrier_descriptor():
    single = OperatorPlans((Carrier(0.0, 12e6, 0.2, "QPSK", 1.0),), tuple(default_plan(5, 36e6)))
    result = _apply("drop_one", "co_only", original=single)
    assert result.status == "not_applicable" and "fewer than two" in result.reason and result.plans is None
    assert _apply("drop_one", "cross_only", original=single).applied


def test_phantom_adds_one_declared_carrier_in_a_free_gap():
    original = _original()
    result = _apply("phantom", "co_only")
    assert result.applied and len(result.plans.co) == len(original.co) + 1
    assert result.plans.co[:-1] == original.co
    added = result.plans.co[-1]
    assert added.f0 - added.occupied_bw / 2 >= -18e6 - 1e-6 and added.f0 + added.occupied_bw / 2 <= 18e6 + 1e-6
    for carrier in original.co:     # the free gap does not overlap a declared carrier
        assert (added.f0 + added.occupied_bw / 2 <= carrier.f0 - carrier.occupied_bw / 2 + 1e-6
                or added.f0 - added.occupied_bw / 2 >= carrier.f0 + carrier.occupied_bw / 2 - 1e-6)
    assert sum(c.power for c in result.plans.co) > 1.0                                # declared load grew; not renormalized


def test_phantom_without_free_gap_is_not_applicable():
    full = OperatorPlans((Carrier(0.0, 36e6 / 1.2 * 0.999, 0.2, "QPSK", 1.0),), tuple(default_plan(5, 36e6)))
    result = _apply("phantom", "co_only", original=full)
    assert result.status == "not_applicable" and "free gap" in result.reason


def test_authorize_intruder_needs_the_whitelisted_unauthorized_context():
    original = _original()
    assert _apply("authorize_intruder", "co_only").status == "not_applicable"                       # no context
    assert _apply("authorize_intruder", "co_only", context={"label": "clean"}).status == "not_applicable"
    result = _apply("authorize_intruder", "co_only", context=_intruder_context())
    assert result.applied and len(result.plans.co) == len(original.co) + 1
    added = result.plans.co[-1]
    assert (added.f0, added.symbol_rate, added.alpha, added.mod) == (-7.4e6, 1.5e6, 0.2, "16APSK")
    assert added.power == pytest.approx(10 ** (-17.0 / 10))
    assert result.plans.cross == original.cross
    both = _apply("authorize_intruder", "both", context=_intruder_context())
    assert both.descriptors["cross"]["declared_on_cross_feed"] is True and both.descriptors["co"]["declared_on_cross_feed"] is False


def test_intervention_context_is_whitelisted():
    with pytest.raises(ValueError, match="keys must be a subset"):
        _apply("authorize_intruder", context={"label": "unauthorized", "active_carriers": [[True]]})
    with pytest.raises(ValueError, match="exactly the keys"):
        _apply("authorize_intruder", context={"label": "unauthorized", "intruder": {"f0": 0.0}})


def test_stale_plan_is_the_plan_of_the_preceding_scenario_id():
    original = _original()
    result = _apply("stale_plan", "both")
    assert result.applied
    assert result.plans.co == tuple(default_plan(2 * (GROUP - 1) + 0, 36e6))
    assert result.plans.cross == tuple(default_plan(2 * (GROUP - 1) + 1, 36e6))
    assert result.plans.co != original.co
    same = OperatorPlans(tuple(default_plan(2 * (GROUP - 1), 36e6)), tuple(default_plan(2 * (GROUP - 1) + 1, 36e6)))
    assert _apply("stale_plan", "both", original=same).status == "not_applicable"


@pytest.mark.parametrize("perturbation", [p for p in ap.PERTURBATIONS if p not in ("none", "authorize_intruder")])
def test_scope_both_is_exactly_the_union_of_the_two_single_feed_scopes(perturbation):
    co, cross, both = (_apply(perturbation, scope) for scope in ap.SCOPES[:3])
    assert co.applied and cross.applied and both.applied
    assert both.plans.co == co.plans.co and both.plans.cross == cross.plans.cross
    assert co.plans.cross == co.original.cross and cross.plans.co == cross.original.co     # one feed never touches the other


def test_co_and_cross_use_independent_random_streams_and_are_never_swapped():
    original = OperatorPlans(tuple(default_plan(11, 36e6)), tuple(default_plan(12, 36e6)))
    result = _apply("drop_one", "both", original=original)
    assert result.descriptors["co"]["removed_indices"] != [] and result.descriptors["cross"]["removed_indices"] != []
    assert all(c in original.co for c in result.plans.co) and all(c in original.cross for c in result.plans.cross)
    rng = lambda pol: np.random.default_rng([GROUP, 1850, ap.PERTURBATIONS.index("drop_one"), pol])
    assert result.descriptors["co"]["removed_indices"] == [int(rng(0).integers(len(original.co)))]
    assert result.descriptors["cross"]["removed_indices"] == [int(rng(1).integers(len(original.cross)))]


def test_determinism_and_dependence_on_scenario_id():
    first, second = _apply("phantom", "both"), _apply("phantom", "both")
    assert first.plans == second.plans and first.to_dict() == second.to_dict()
    other = corrupt_operator_plan(_original(), perturbation="phantom", scope="both", scenario_id=GROUP + 1)
    assert other.plans != first.plans


def test_corrupted_beliefs_are_not_physical_plans_and_are_validated_by_the_frozen_canceller():
    validate_belief(_apply("phantom", "co_only").plans.co)                 # total power > 1 is fine for a belief
    bad_rate = Carrier(0.0, 7e6, 0.2, "QPSK", 1.0)                          # 288e6 / 7e6 is not an integer
    blocked = _apply("none", "co_only", original=OperatorPlans((bad_rate,), tuple(default_plan(5, 36e6))))
    assert blocked.status == "blocked" and "co belief rejected" in blocked.reason and blocked.plans is None
    out_of_band = OperatorPlans((Carrier(47e6, 6e6, 0.2, "QPSK", 1.0),), tuple(default_plan(5, 36e6)))
    assert _apply("none", "co_only", original=out_of_band).status == "blocked"
    bad_mod = OperatorPlans((Carrier(0.0, 6e6, 0.2, "BPSK", 1.0),), tuple(default_plan(5, 36e6)))
    assert _apply("none", "co_only", original=bad_mod).status == "blocked"
    for value in (float("nan"), float("inf")):
        nonfinite = OperatorPlans((Carrier(value, 6e6, 0.2, "QPSK", 1.0),), tuple(default_plan(5, 36e6)))
        assert _apply("none", "co_only", original=nonfinite).status == "blocked"


def test_input_validation_is_strict():
    with pytest.raises(ValueError):
        corrupt_operator_plan(_original(), perturbation="shift", scope="both", scenario_id=1)
    with pytest.raises(ValueError):
        corrupt_operator_plan(_original(), perturbation="none", scope="neither", scenario_id=1)
    with pytest.raises(ValueError):
        corrupt_operator_plan(_original(), perturbation="none", scope="both", scenario_id=-1)
    with pytest.raises(ValueError):
        corrupt_operator_plan(_original(), perturbation="none", scope="both", scenario_id=True)
    with pytest.raises(ValueError):
        corrupt_operator_plan([[], []], perturbation="none", scope="both", scenario_id=1)
    with pytest.raises(ValueError):
        OperatorPlans([1], [2])


def test_masks_are_float16_unit_peak_and_unchanged_for_none():
    original = _original()
    masks = rebuild_masks(original)
    assert masks.shape == (2, 512) and masks.dtype == np.float16
    expected = np.stack([plan_mask_db(list(original.co)), plan_mask_db(list(original.cross))]).astype(np.float16)
    assert np.array_equal(masks, expected)
    assert float(masks.max()) == pytest.approx(0.0, abs=1e-3)
    assert np.array_equal(rebuild_masks(_apply("none").plans), masks)
    cross_only = rebuild_masks(_apply("drop_one", "cross_only").plans)
    assert np.array_equal(cross_only[0], masks[0]) and not np.array_equal(cross_only[1], masks[1])


def test_identity_and_dictionary_are_strict_json_and_deterministic():
    result = _apply("drop_one", "both")
    text = json.dumps(result.to_dict(), allow_nan=False)
    assert json.loads(text)["perturbation"] == "drop_one" and result.original.identity() == _original().identity()
    assert result.plans.identity() != result.original.identity()
    assert asdict(result.plans.co[0])["code_rate"] is None or isinstance(asdict(result.plans.co[0])["code_rate"], str)


def test_exceeding_the_transponder_edge_is_flagged_not_removed():
    edge = Carrier(17.0e6, 1.2e6, 0.2, "QPSK", 0.5)                   # band edge 17.72 MHz; 18.22 MHz after +0.5 MHz
    plan = OperatorPlans((edge, Carrier(-10e6, 6e6, 0.2, "QPSK", 0.5)), tuple(default_plan(5, 36e6)))
    result = _apply("shift_plus", "co_only", original=plan)
    assert result.applied and result.descriptors["co"]["exceeds_transponder_edge"] == [0]

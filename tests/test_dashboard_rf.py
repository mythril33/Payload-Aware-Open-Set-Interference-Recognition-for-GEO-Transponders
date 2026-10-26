"""RF Explorer adapter: development roles only, refusal before any simulation, units and axes.

One real simulator scene from the train role is generated (about 7 seconds on a 4-core CPU). Everything else
is refusal logic with the simulator replaced by a function that fails if it is ever reached.
"""
import ast
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "dashboard"), str(ROOT / "src"), str(ROOT)]

from geodash import rf  # noqa: E402


def _simulator_must_not_run(*args, **kwargs):
    raise AssertionError("the simulator was reached for a refused group")


@pytest.fixture
def no_simulation(monkeypatch):
    from geosim import b2_scenarios, cancellation
    monkeypatch.setattr(b2_scenarios, "prepare_scene", _simulator_must_not_run)
    monkeypatch.setattr(b2_scenarios, "sample_scene", _simulator_must_not_run)
    monkeypatch.setattr(b2_scenarios, "simulate_dual", _simulator_must_not_run)
    monkeypatch.setattr(cancellation, "cancel_planned_carriers", _simulator_must_not_run)
    return monkeypatch


@pytest.mark.parametrize("group", [3200000, 3200499, 3300000, 3300149])
def test_test_and_test_matched_groups_are_refused_before_any_simulation(no_simulation, group):
    with pytest.raises(rf.DevelopmentRoleRefused):
        rf.build_scene(group)


def test_group_outside_every_reserved_role_is_refused_by_the_protocol(no_simulation):
    with pytest.raises(ValueError):
        rf.build_scene(9_999_999)


def test_unknown_scene_label_is_refused_before_simulation(no_simulation):
    with pytest.raises(ValueError):
        rf.build_scene(3000000, label="not-a-label")


@pytest.mark.parametrize("role", ["test", "test-matched", "unknown"])
def test_development_group_listing_refuses_non_development_roles(role):
    with pytest.raises(rf.DevelopmentRoleRefused):
        rf.development_group_ids(role)


def test_development_roles_match_the_roles_the_generation_script_allows():
    tree = ast.parse((ROOT / "scripts" / "b2_real_generation.py").read_text(encoding="utf-8"))
    values = None
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "DEVELOPMENT_ROLES" for t in node.targets):
            values = tuple(ast.literal_eval(node.value))
    assert values == rf.DEVELOPMENT_ROLES


def test_development_group_listing_is_the_protocol_prefix():
    from geosim import b2_protocol as P
    assert rf.development_group_ids("train", 3) == list(P.scenario_ids("train", 3))
    assert all(P.role_for_group(g) == "train" for g in rf.development_group_ids("train", 5))


@pytest.fixture(scope="module")
def train_scene():
    return rf.build_scene(3000000, "clean")


def test_spectrum_arrays_have_the_documented_shapes(train_scene):
    scene = train_scene
    n_snap = scene.spec_db.shape[1]
    assert scene.spec_db.shape == (2, n_snap, 512)
    assert scene.mean_psd_db.shape == (2, 512)
    assert scene.plan_mask_db.shape == (2, 512)
    assert scene.residual_spec_db.shape == (n_snap, 512)
    assert scene.residual_mean_psd_db.shape == (512,)
    assert all(np.isfinite(a).all() for a in (scene.spec_db, scene.mean_psd_db, scene.plan_mask_db,
                                              scene.residual_spec_db))


def test_frequency_and_time_axes_are_in_documented_units(train_scene):
    scene = train_scene
    assert scene.freq_mhz[0] == pytest.approx(-48.0)
    assert scene.freq_mhz[-1] == pytest.approx(47.8125)
    assert np.allclose(np.diff(scene.freq_mhz), 0.1875)  # 187.5 kHz bins
    assert scene.time_s[0] == 0.0 and scene.time_s[1] == pytest.approx(0.01)


def test_units_travel_with_the_scene_and_say_they_are_not_dbm(train_scene):
    units = train_scene.units
    assert "not calibrated to dBm" in units["spectrum"]
    assert units["frequency"].startswith("MHz")
    assert "dB relative to the plan" in units["plan_mask"]


def test_carrier_rows_are_engineering_units_and_cover_both_feeds(train_scene):
    rows = rf.carriers_frame(train_scene)
    assert rows and {r["feed"] for r in rows} <= {"co-pol", "cross-pol"}
    for row in rows:
        assert row["symbol rate (Msym/s)"] > 0
        assert row["occupied BW (MHz)"] == pytest.approx(
            row["symbol rate (Msym/s)"] * (1 + row["roll-off"]), rel=1e-3)
        assert row["modulation"] in ("QPSK", "8PSK", "16APSK", "32APSK")
        assert row["roll-off"] in (0.2, 0.25, 0.35)


def test_the_residual_is_computed_from_the_co_pol_plan_and_co_pol_monitor_iq(monkeypatch):
    from geosim import b2_scenarios, cancellation
    seen = {}
    real = cancellation.cancel_planned_carriers

    def spy(iq, plan, config=None):
        seen["iq_shape"] = np.asarray(iq).shape
        seen["plan_len"] = len(plan)
        seen["plan"] = plan
        return real(iq, plan, config)

    monkeypatch.setattr(cancellation, "cancel_planned_carriers", spy)
    scene = rf.build_scene(3000001, "clean")
    expected_plan = b2_scenarios.prepare_scene("clean", 3000001).plans[0]
    assert seen["iq_shape"][1] == 4096 and seen["iq_shape"][0] == scene.spec_db.shape[1]
    assert [c.f0 for c in seen["plan"]] == [c.f0 for c in expected_plan]
    assert len(scene.cancellation) == len(expected_plan)


def test_truth_is_labelled_as_metadata_and_not_as_an_input(train_scene):
    assert "never model inputs" in train_scene.truth["note"]
    assert "event" in train_scene.truth

"""Physical limiting cases for distinct uplink, payload and receiver mixing."""
from dataclasses import replace
import json

import numpy as np
import pytest

from geosim.dual import DualScenarioConfig, simulate_dual
from geosim.interferers import cw
from geosim.polarization import fit_receiver_calibration
from geosim.scenario import ScenarioConfig, simulate
from geosim.waveform import Carrier, generate_carrier


def paths(*, bandwidth=36e6, linear=False, noisy=True):
    return (ScenarioConfig(bandwidth=bandwidth, seed=3, n_snap=4, ibo_db=4.0, linear=linear,
                           cn_up_db=24.0 if noisy else np.inf, cn_dn_db=22.0 if noisy else np.inf),
            ScenarioConfig(bandwidth=bandwidth, seed=11, n_snap=4, ibo_db=4.0, linear=linear,
                           cn_up_db=24.0 if noisy else np.inf, cn_dn_db=22.0 if noisy else np.inf))


PLANS = ([Carrier(-4e6, 4e6, 0.25, "QPSK", 1.0)],
         [Carrier(4e6, 4e6, 0.25, "8PSK", 1.0)])


@pytest.mark.parametrize("bandwidth", [36e6, 72e6])
def test_identity_coupling_reduces_to_two_a1_simulations(bandwidth):
    co, cross = paths(bandwidth=bandwidth)
    config = DualScenarioConfig(co, cross, uplink_xpd_db=np.inf, downlink_xpd_db=np.inf)
    result = simulate_dual(config, plans=PLANS, keep_iq=True)
    assert result.spec_db.shape == (2, 4, 512)
    assert result.mask_db.shape == (2, 512)
    assert result.iq.shape == (2, 4, 4096) and result.iq.dtype == np.complex64
    for i, path in enumerate((co, cross)):
        reference = simulate(path, plan=PLANS[i], keep_iq=True)
        np.testing.assert_allclose(result.iq[i], reference.iq, rtol=1e-6, atol=1e-7)
        np.testing.assert_allclose(result.spec_db[i], reference.spec_db, rtol=1e-6, atol=2e-5)
        np.testing.assert_array_equal(result.mask_db[i], reference.mask_db)
        assert result.meta["paths"][i]["actual_ibo_db"] == pytest.approx(reference.meta["actual_ibo_db"], rel=1e-6)
    assert result.meta["config"]["uplink_xpd_db"] == "ideal"
    json.dumps(result.meta, allow_nan=False)


def test_uplink_mixing_is_before_nonlinearity_and_downlink_is_after_it():
    def compare(linear):
        co, cross = paths(linear=linear, noisy=False)
        upstream = simulate_dual(DualScenarioConfig(co, cross, uplink_xpd_db=10., downlink_xpd_db=np.inf,
                                                    uplink_phase_rad=0.7), plans=PLANS, keep_iq=True)
        downstream = simulate_dual(DualScenarioConfig(co, cross, uplink_xpd_db=np.inf, downlink_xpd_db=10.,
                                                      downlink_phase_rad=0.7), plans=PLANS, keep_iq=True)
        return np.linalg.norm(upstream.iq - downstream.iq) / np.linalg.norm(upstream.iq)

    # Identical linear paths commute with a frequency-flat Jones matrix. A
    # per-feed nonlinear TWTA must not: mixing changes each drive envelope.
    assert compare(True) < 2e-6
    assert compare(False) > 0.01


def test_receiver_calibration_corrects_instrument_without_removing_physical_leakage():
    co, cross = paths(noisy=False)
    config = DualScenarioConfig(co, cross, uplink_xpd_db=12., downlink_xpd_db=26.,
                                 uplink_phase_rad=0.5, downlink_phase_rad=-0.2)
    reference = simulate_dual(config, plans=PLANS, keep_iq=True)
    h = np.array([[1.4 * np.exp(0.3j), 0.1 + 0.02j], [-0.07j, 0.8 * np.exp(-0.2j)]])
    rng = np.random.default_rng(923)
    pilots = rng.normal(size=(2, 256)) + 1j * rng.normal(size=(2, 256))
    calibration = fit_receiver_calibration(pilots, h @ pilots, provenance="independent-lab-pilots")
    corrected = simulate_dual(replace(config, receiver_response=h), plans=PLANS,
                               calibration=calibration, keep_iq=True)
    np.testing.assert_allclose(corrected.iq, reference.iq, rtol=2e-5, atol=2e-7)
    no_physical_leakage = simulate_dual(replace(config, uplink_xpd_db=np.inf, downlink_xpd_db=np.inf),
                                        plans=PLANS, keep_iq=True)
    assert np.linalg.norm(corrected.iq - no_physical_leakage.iq) / np.linalg.norm(corrected.iq) > 0.1
    assert corrected.meta["receiver_calibration_applied"] is True
    assert corrected.meta["receiver_calibration"]["provenance"] == "independent-lab-pilots"
    json.dumps(corrected.meta, allow_nan=False)


def test_receiver_noise_is_not_rescaled_to_hide_instrument_gain():
    co, cross = paths(noisy=False)
    co, cross = replace(co, cn_dn_db=0.0), replace(cross, cn_dn_db=0.0)
    config = DualScenarioConfig(co, cross, uplink_xpd_db=np.inf, downlink_xpd_db=np.inf)
    unit = simulate_dual(config, plans=PLANS, keep_iq=True)
    amplified = simulate_dual(replace(config, receiver_response=2 * np.eye(2)), plans=PLANS, keep_iq=True)
    clean = simulate_dual(replace(config, co=replace(co, cn_dn_db=np.inf), cross=replace(cross, cn_dn_db=np.inf)),
                          plans=PLANS, keep_iq=True)
    assert [path["receiver_noise_psd"] for path in unit.meta["paths"]] == [path["receiver_noise_psd"] for path in amplified.meta["paths"]]
    np.testing.assert_allclose(amplified.iq - 2 * clean.iq, unit.iq - clean.iq, rtol=2e-5, atol=2e-6)


def test_interference_injection_is_per_feed_and_deterministic():
    co, cross = paths(noisy=False)
    config = DualScenarioConfig(co, cross, uplink_xpd_db=np.inf, downlink_xpd_db=np.inf)
    base = simulate_dual(config, plans=PLANS, keep_iq=True)
    event, _ = cw(-3e6, 5.0)
    polluted = simulate_dual(config, plans=PLANS, interferers=(event, None), keep_iq=True)
    repeated = simulate_dual(config, plans=PLANS, interferers=(event, None), keep_iq=True)
    np.testing.assert_array_equal(polluted.iq, repeated.iq)
    np.testing.assert_array_equal(polluted.iq[1], base.iq[1])
    assert not np.array_equal(polluted.iq[0], base.iq[0])
    assert polluted.meta["has_interferer"] == [True, False]


def test_coherent_mixing_cancellation_remains_a_finite_physical_observation():
    co, _ = paths(noisy=False)
    config = DualScenarioConfig(co, co, uplink_xpd_db=0., downlink_xpd_db=np.inf)
    result = simulate_dual(config, plans=(PLANS[0], PLANS[0]), keep_iq=True)
    assert np.isfinite(result.spec_db).all()
    # BLAS may leave a float64-rounding residual after equal opposite terms.
    assert np.linalg.norm(result.iq[1]) / np.linalg.norm(result.iq[0]) < 1e-12
    assert result.meta["paths"][0]["omux_output_power"] > 0
    json.dumps(result.meta, allow_nan=False)


def test_exact_zero_drive_has_explicit_missing_backoff_and_a_finite_psd_floor():
    co, cross = paths(noisy=False)

    def cancel_co_carrier(rng, t0, n, fs):
        carrier_stream = np.random.SeedSequence(co.seed).spawn(5)[1]
        return -generate_carrier(np.random.default_rng(carrier_stream), PLANS[0][0], co.n_snap, n, fs)

    result = simulate_dual(DualScenarioConfig(co, cross, uplink_xpd_db=np.inf, downlink_xpd_db=np.inf),
                            plans=PLANS, interferers=(cancel_co_carrier, None), keep_iq=True)
    assert np.isfinite(result.spec_db).all()
    assert np.max(np.abs(result.iq[0])) == 0
    assert result.meta["paths"][0]["actual_ibo_db"] is None
    assert result.meta["paths"][0]["obo_db"] is None
    assert result.meta["paths"][0]["zero_drive"] is True
    assert result.meta["paths"][1]["omux_output_power"] > 0
    json.dumps(result.meta, allow_nan=False)


def test_default_plans_and_streams_are_independent_and_iq_is_optional():
    co, cross = paths()
    result = simulate_dual(DualScenarioConfig(co, cross))
    assert result.iq is None
    assert not np.array_equal(result.mask_db[0], result.mask_db[1])
    assert not np.array_equal(result.spec_db[0], result.spec_db[1])
    assert result.meta["plans"][0] != result.meta["plans"][1]


@pytest.mark.parametrize("change", [{"seed": -1}, {"seed": True}, {"n_snap": 0}, {"cn_up_db": np.nan},
                                    {"cn_dn_db": -np.inf}, {"ibo_db": 1e9}, {"snap_interval": 0},
                                    {"linear": "yes"}, {"amplifier": "undefined"}])
def test_invalid_path_config_fails_before_generation(change):
    with pytest.raises(ValueError):
        DualScenarioConfig(co=ScenarioConfig(**change))


@pytest.mark.parametrize("change", [{"uplink_xpd_db": -1}, {"downlink_phase_rad": np.nan},
                                    {"receiver_response": np.ones((2, 2))},
                                    {"receiver_response": np.eye(3)}, {"receiver_response": [[1, 0], [0, np.inf]]},
                                    {"cross": ScenarioConfig(seed=1, bandwidth=72e6)},
                                    {"cross": ScenarioConfig(seed=1, n_snap=16)}])
def test_invalid_joint_configuration_fails(change):
    with pytest.raises(ValueError):
        DualScenarioConfig(**change)


@pytest.mark.parametrize("plan", [[], [Carrier(0, 4e6, 0.25, "QPSK", -1.)],
                                  [Carrier(0, 4e6, 0.25, "QPSK", 0.9)],
                                  [Carrier(20e6, 4e6, 0.25, "QPSK", 1.)],
                                  [Carrier(0, 4e6, 0.25, "undefined", 1.)]])
def test_invalid_plan_fails_before_waveform_generation(plan):
    co, cross = paths()
    with pytest.raises(ValueError):
        simulate_dual(DualScenarioConfig(co, cross), plans=(plan, PLANS[1]))


def test_mutated_nested_config_and_invalid_interferer_outputs_are_rejected():
    co, cross = paths()
    config = DualScenarioConfig(co, cross)
    config.co.n_snap = 0
    with pytest.raises(ValueError, match="n_snap"):
        simulate_dual(config)
    with pytest.raises(ValueError, match="interferer"):
        simulate_dual(DualScenarioConfig(co, cross), interferers=(lambda *args: np.zeros((1, 3)), None))


def test_valid_numpy_scalar_metadata_is_strict_json_and_huge_receiver_gain_fails():
    co, cross = paths()
    plans = ([replace(PLANS[0][0], power=np.float32(1), f0=np.float32(-4e6))], PLANS[1])
    result = simulate_dual(DualScenarioConfig(co, cross), plans=plans)
    json.dumps(result.meta, allow_nan=False)
    with pytest.raises(ValueError, match="complex64"):
        simulate_dual(DualScenarioConfig(co, cross, receiver_response=1e100 * np.eye(2)), plans=PLANS)

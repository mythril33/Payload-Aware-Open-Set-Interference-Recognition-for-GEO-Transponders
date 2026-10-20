"""Operator plans and transmitted loading stay distinct under fixed gain."""
from dataclasses import replace
import json

import numpy as np
import pytest

from geosim import FS_SIM, dual, sensor
from geosim.dual import DualScenarioConfig, simulate_dual
from geosim.polarization import jones_matrix
from geosim.scenario import ScenarioConfig
from geosim.waveform import Carrier, generate_carrier


PLANS = ([Carrier(-8e6, 2e6, .25, "QPSK", .25),
          Carrier(-1e6, 2e6, .25, "8PSK", .35),
          Carrier(8e6, 2e6, .25, "QPSK", .40)],
         [Carrier(4e6, 4e6, .25, "QPSK", 1.)])
ACTIVITY_KEYS = {"active_carriers", "active_planned_power", "nominal_planned_power", "gain_mode"}


def config(*, noisy=False, linear=False):
    paths = [ScenarioConfig(seed=seed, n_snap=3, ibo_db=8., linear=linear,
                            cn_up_db=20. if noisy else np.inf,
                            cn_dn_db=22. if noisy else np.inf) for seed in (3, 11)]
    return DualScenarioConfig(*paths, uplink_xpd_db=np.inf, downlink_xpd_db=np.inf)


def test_implicit_activity_keeps_legacy_metadata_and_explicit_all_on_is_exact():
    cfg = replace(config(noisy=True), satellite_linewidth_hz=100., receiver_linewidth_hz=50.)
    implicit = simulate_dual(cfg, plans=PLANS, keep_iq=True)
    explicit = simulate_dual(cfg, plans=PLANS, keep_iq=True,
                             active_carriers=([True, True, True], np.array([True])))
    np.testing.assert_array_equal(implicit.iq, explicit.iq)
    np.testing.assert_array_equal(implicit.spec_db, explicit.spec_db)
    np.testing.assert_array_equal(implicit.mask_db, explicit.mask_db)
    assert ACTIVITY_KEYS.isdisjoint(implicit.meta)
    assert {key: value for key, value in explicit.meta.items() if key not in ACTIVITY_KEYS} == implicit.meta
    assert explicit.meta["active_carriers"] == [[True, True, True], [True]]
    assert explicit.meta["active_planned_power"] == [1., 1.]
    assert explicit.meta["nominal_planned_power"] == [1., 1.]
    assert explicit.meta["gain_mode"] == "fixed_nominal_planned_power"


def test_drop_preserves_remaining_carrier_symbols_and_uplink_noise(monkeypatch):
    cfg = config(noisy=True)
    captured, actual_imux = [], dual.pl.imux

    def imux(*args, **kwargs):
        response = actual_imux(*args, **kwargs)

        class Capture:
            def apply(self, iq):
                captured.append(iq.copy())
                return response.apply(iq)
        return Capture()

    monkeypatch.setattr(dual.pl, "imux", imux)
    full = simulate_dual(cfg, plans=PLANS)
    dropped = simulate_dual(cfg, plans=PLANS, active_carriers=([False, True, True], [True]))
    streams = np.random.SeedSequence(cfg.co.seed).spawn(5)
    rng = np.random.default_rng(streams[1])
    waves = [generate_carrier(rng, carrier, cfg.co.n_snap, sensor.N_SIM, FS_SIM) for carrier in PLANS[0]]
    noise = sensor.awgn(np.random.default_rng(streams[2]), waves[0].shape,
                        1 / (cfg.co.bandwidth * 10 ** (cfg.co.cn_up_db / 10)), FS_SIM)
    expected = (waves[1] + waves[2]).astype(np.complex64) + noise
    np.testing.assert_array_equal(captured[2], expected)
    np.testing.assert_allclose(captured[0] - captured[2], waves[0], rtol=2e-5, atol=5e-7)
    np.testing.assert_array_equal(captured[1], captured[3])
    np.testing.assert_array_equal(full.mask_db, dropped.mask_db)
    assert dropped.meta["plans"] == full.meta["plans"]
    assert dropped.meta["active_planned_power"] == [.75, 1.]


def test_drop_reduces_payload_loading_without_gain_renormalization():
    cfg = config()
    full = simulate_dual(cfg, plans=PLANS, keep_iq=True)
    dropped = simulate_dual(cfg, plans=PLANS, keep_iq=True,
                            active_carriers=([False, False, True], [True]))
    assert dropped.meta["config"] == full.meta["config"]
    assert dropped.meta["active_planned_power"] == [.4, 1.]
    assert dropped.meta["paths"][0]["actual_ibo_db"] > full.meta["paths"][0]["actual_ibo_db"] + 3
    assert dropped.meta["paths"][0]["omux_output_power"] < full.meta["paths"][0]["omux_output_power"]
    np.testing.assert_array_equal(dropped.iq[1], full.iq[1])
    np.testing.assert_array_equal(dropped.mask_db, full.mask_db)
    assert dropped.meta["plans"] == full.meta["plans"]


def test_all_inactive_is_explicit_zero_load_with_finite_observations():
    result = simulate_dual(config(), plans=PLANS, keep_iq=True,
                            active_carriers=([False, False, False], [True]))
    assert result.meta["active_planned_power"] == [0., 1.]
    assert result.meta["paths"][0]["actual_ibo_db"] is None
    assert result.meta["paths"][0]["zero_drive"] is True
    assert np.max(np.abs(result.iq[0])) == 0
    assert np.isfinite(result.spec_db).all()
    assert result.meta["paths"][1]["omux_output_power"] > 0
    json.dumps(result.meta, allow_nan=False)


def test_dropped_carrier_still_obeys_coherent_uplink_jones_coupling(monkeypatch):
    cfg = replace(config(linear=True), uplink_xpd_db=12., uplink_phase_rad=.4)
    captured, actual_imux = [], dual.pl.imux

    def imux(*args, **kwargs):
        response = actual_imux(*args, **kwargs)

        class Capture:
            def apply(self, iq):
                captured.append(iq.copy())
                return response.apply(iq)
        return Capture()

    monkeypatch.setattr(dual.pl, "imux", imux)
    simulate_dual(cfg, plans=PLANS)
    simulate_dual(cfg, plans=PLANS, active_carriers=([True, False, True], [True]))
    rng = np.random.default_rng(np.random.SeedSequence(cfg.co.seed).spawn(5)[1])
    generate_carrier(rng, PLANS[0][0], cfg.co.n_snap, sensor.N_SIM, FS_SIM)
    removed = generate_carrier(rng, PLANS[0][1], cfg.co.n_snap, sensor.N_SIM, FS_SIM)
    column = jones_matrix(cfg.uplink_xpd_db, cfg.uplink_phase_rad)[:, 0]
    np.testing.assert_allclose(np.stack(captured[:2]) - np.stack(captured[2:]),
                               column[:, None, None] * removed, rtol=4e-5, atol=8e-7)


@pytest.mark.parametrize("masks", [True, "bad", (), ([True],),
                                    ([True, True, True], [True], [True]),
                                    ([1, 1, 1], [True]), ([True, 0, True], [True]),
                                    ([True, True], [True]), ([True, True, True], []),
                                    ([[True, True, True]], [True]),
                                    ([True, True, True], [None]),
                                    (np.ones(3, dtype=float), [True])])
def test_invalid_activity_fails_before_generation(monkeypatch, masks):
    def forbidden(*args, **kwargs):
        raise AssertionError("invalid activity must fail before waveform generation")

    monkeypatch.setattr(dual, "generate_carrier", forbidden)
    with pytest.raises(ValueError, match="active_carriers"):
        simulate_dual(config(), plans=PLANS, active_carriers=masks)

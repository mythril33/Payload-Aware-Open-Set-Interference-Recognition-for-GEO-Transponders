"""Injection-site, reference-power and shared-LO checks for dual observations."""
from dataclasses import replace
import json

import numpy as np
import pytest

from geosim import FS_SIM, sensor
from geosim import dual
from geosim.dual import DualScenarioConfig, simulate_dual
from geosim.interferers import cw
from geosim.phase_noise import rotate_phase, wiener_phase
from geosim.polarization import fit_receiver_calibration
from geosim.scenario import ScenarioConfig, simulate
from geosim.waveform import Carrier


PLANS = ([Carrier(-4e6, 4e6, .25, "QPSK", 1.)],
         [Carrier(4e6, 4e6, .25, "8PSK", 1.)])


def config(**changes):
    paths = [ScenarioConfig(seed=seed, n_snap=3, ibo_db=4.,
                            cn_up_db=np.inf, cn_dn_db=np.inf) for seed in (3, 11)]
    return DualScenarioConfig(*paths, uplink_xpd_db=np.inf, downlink_xpd_db=np.inf, **changes)


def capture_monitor(monkeypatch):
    captured = []
    original = sensor.to_monitor

    def monitor(iq):
        captured.append(iq.copy())
        return original(iq)

    monkeypatch.setattr(sensor, "to_monitor", monitor)
    return captured


def test_zero_linewidth_preserves_a1_exactly_and_skips_phase_rng(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("disabled phase noise must not draw a phase path")

    monkeypatch.setattr(dual, "wiener_phase", forbidden)
    cfg = config()
    result = simulate_dual(cfg, plans=PLANS, keep_iq=True)
    explicit = simulate_dual(replace(cfg, satellite_linewidth_hz=0., receiver_linewidth_hz=0.),
                             plans=PLANS, downlink_interferers=(None, None), keep_iq=True)
    np.testing.assert_array_equal(result.iq, explicit.iq)
    for pol, path in enumerate((cfg.co, cfg.cross)):
        expected = simulate(path, plan=PLANS[pol], keep_iq=True)
        np.testing.assert_allclose(result.iq[pol], expected.iq, rtol=1e-6, atol=1e-7)
    assert result.meta["has_downlink_interferer"] == [False, False]
    json.dumps(result.meta, allow_nan=False)


def test_downlink_event_bypasses_payload_and_uses_wanted_feed_reference(monkeypatch):
    captured = capture_monitor(monkeypatch)
    cfg = config()
    base = simulate_dual(cfg, plans=PLANS, keep_iq=True)
    event, _ = cw(1e6, 7.)
    polluted = simulate_dual(cfg, plans=PLANS, downlink_interferers=(event, None), keep_iq=True)
    assert polluted.meta["paths"] == base.meta["paths"]
    assert polluted.meta["downlink_interference_reference_power"] == base.meta["downlink_interference_reference_power"]
    wanted = base.meta["downlink_interference_reference_power"][0]
    np.testing.assert_allclose(wanted, np.mean(np.abs(captured[0][0, :, sensor.WARMUP_SIM:]) ** 2), rtol=2e-7)
    t0 = np.arange(cfg.co.n_snap) * cfg.co.snap_interval
    event_rng = np.random.default_rng(np.random.SeedSequence([cfg.co.seed, cfg.cross.seed, 7052, 0]))
    nominal = event(event_rng, t0, sensor.N_SIM, FS_SIM)
    expected = (nominal * np.sqrt(wanted)).astype(np.complex64)
    # Event addition casts to float32 at the instrument boundary.
    np.testing.assert_allclose(captured[1][0] - captured[0][0], expected, rtol=5e-5, atol=1e-7)
    measured_ratio = np.mean(np.abs(expected[:, sensor.WARMUP_SIM:]) ** 2) / wanted
    assert measured_ratio == pytest.approx(10 ** (-7 / 10), rel=2e-7)
    np.testing.assert_array_equal(polluted.iq[1], base.iq[1])
    upstream = simulate_dual(cfg, plans=PLANS, interferers=(event, None))
    assert upstream.meta["paths"][0] != base.meta["paths"][0]
    assert polluted.meta["has_downlink_interferer"] == [True, False]


def test_both_downlink_events_use_pre_event_reference_and_independent_streams():
    cfg = config(receiver_linewidth_hz=50.)
    draws = []

    def random_event(rng, t0, n, fs):
        draw = rng.standard_normal((len(t0), n)) + 1j * rng.standard_normal((len(t0), n))
        draws.append(draw.copy())
        return .03 * draw

    left = simulate_dual(cfg, plans=PLANS, downlink_interferers=(random_event, None), keep_iq=True)
    both = simulate_dual(cfg, plans=PLANS, downlink_interferers=(random_event, random_event), keep_iq=True)
    repeated = simulate_dual(cfg, plans=PLANS, downlink_interferers=(random_event, random_event), keep_iq=True)
    assert left.meta["downlink_interference_reference_power"] == both.meta["downlink_interference_reference_power"]
    np.testing.assert_array_equal(draws[0], draws[1])
    assert not np.array_equal(draws[1], draws[2])
    np.testing.assert_array_equal(left.iq[0], both.iq[0])
    np.testing.assert_array_equal(both.iq, repeated.iq)


def test_receiver_lo_rotates_combined_wanted_and_external_event_common_to_feeds(monkeypatch):
    captured = capture_monitor(monkeypatch)
    cfg = config()
    event, _ = cw(1e6, 3.)
    base = simulate_dual(cfg, plans=PLANS, downlink_interferers=(event, None))
    noisy_cfg = replace(cfg, receiver_linewidth_hz=1000.)
    noisy = simulate_dual(noisy_cfg, plans=PLANS, downlink_interferers=(event, None))
    rng = np.random.default_rng(np.random.SeedSequence([cfg.co.seed, cfg.cross.seed, 7051, 1]))
    phase = wiener_phase(rng, np.arange(cfg.co.n_snap) * cfg.co.snap_interval,
                         sensor.N_SIM, FS_SIM, noisy_cfg.receiver_linewidth_hz)
    np.testing.assert_allclose(captured[1], rotate_phase(captured[0], phase), rtol=5e-6, atol=1e-7)
    np.testing.assert_allclose(np.abs(captured[1]), np.abs(captured[0]), rtol=3e-7, atol=1e-7)
    assert noisy.meta["paths"] == base.meta["paths"]
    assert noisy.meta["phase_noise"]["common_to_polarizations"] is True


def test_satellite_lo_is_common_power_preserving_rotation_before_payload(monkeypatch):
    calls = []
    original = dual.rotate_phase

    def rotate(iq, phase):
        result = original(iq, phase)
        calls.append((iq.copy(), result.copy(), phase.copy()))
        return result

    monkeypatch.setattr(dual, "rotate_phase", rotate)
    cfg = config(satellite_linewidth_hz=50000.)
    noisy = simulate_dual(cfg, plans=PLANS, keep_iq=True)
    base = simulate_dual(replace(cfg, satellite_linewidth_hz=0.), plans=PLANS, keep_iq=True)
    assert len(calls) == 1
    before, after, phase = calls[0]
    assert before.shape == (2, cfg.co.n_snap, sensor.N_SIM)
    np.testing.assert_allclose(np.abs(after), np.abs(before), rtol=3e-7, atol=1e-7)
    np.testing.assert_allclose(after, before * np.exp(1j * phase), rtol=3e-7, atol=1e-7)
    assert np.linalg.norm(noisy.iq - base.iq) / np.linalg.norm(base.iq) > .1
    assert noisy.meta["paths"] != base.meta["paths"]


def test_static_calibration_retains_receiver_phase_noise():
    cfg = config(satellite_linewidth_hz=100., receiver_linewidth_hz=80.)
    h = np.array([[1.3 * np.exp(.3j), .1j], [.03, .7 * np.exp(-.2j)]])
    rng = np.random.default_rng(902)
    reference = rng.normal(size=(2, 64)) + 1j * rng.normal(size=(2, 64))
    calibration = fit_receiver_calibration(reference, h @ reference, provenance="independent-phase-test")
    expected = simulate_dual(cfg, plans=PLANS, keep_iq=True)
    corrected = simulate_dual(replace(cfg, receiver_response=h), plans=PLANS,
                              calibration=calibration, keep_iq=True)
    np.testing.assert_allclose(corrected.iq, expected.iq, rtol=2e-5, atol=3e-7)
    no_phase = simulate_dual(replace(cfg, satellite_linewidth_hz=0., receiver_linewidth_hz=0.),
                             plans=PLANS, keep_iq=True)
    assert np.linalg.norm(corrected.iq - no_phase.iq) / np.linalg.norm(no_phase.iq) > .1


@pytest.mark.parametrize("field", ["satellite_linewidth_hz", "receiver_linewidth_hz"])
@pytest.mark.parametrize("value", [-1., np.inf, np.nan, True, "10", 10 ** 400])
def test_invalid_linewidth_fails_before_generation(field, value):
    with pytest.raises(ValueError, match=field):
        config(**{field: value})


@pytest.mark.parametrize("events", [(None,), (False, None), (None, None, None), "bad"])
def test_invalid_downlink_callback_container_fails(events):
    with pytest.raises(ValueError, match="downlink_interferers"):
        simulate_dual(config(), plans=PLANS, downlink_interferers=events)


@pytest.mark.parametrize("value", [np.zeros((1, 3)), np.full((3, sensor.N_SIM), np.nan),
                                  np.full((3, sensor.N_SIM), "x")])
def test_invalid_downlink_samples_fail(value):
    with pytest.raises(ValueError, match="downlink interferer"):
        simulate_dual(config(), plans=PLANS, downlink_interferers=(lambda *args: value, None))


def test_excessive_downlink_amplitude_fails_complex64_guard():
    with pytest.raises(ValueError, match="downlink interferer.*complex64"):
        simulate_dual(config(), plans=PLANS,
                      downlink_interferers=(lambda rng, t0, n, fs: np.full((len(t0), n), 1e100), None))

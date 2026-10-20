"""Observation-based carrier cancellation: inputs, depth, failure modes and provenance."""
import inspect

import numpy as np
import pytest

from geosim import FS_SIM
from geosim import sensor as sn
from geosim.cancellation import (CancellationConfig, band_power_db, cancel_planned_carriers, srrc_taps,
                                 _decide, _timing)
from geosim.waveform import Carrier, constellation, generate_carrier


def _observe(rng, carriers, cn_db, n_snap=8, transmit=None):
    """Monitor IQ of planned carriers plus white noise; ``transmit`` mutes planned carriers."""
    x = np.zeros((n_snap, sn.N_SIM), np.complex64)
    for index, carrier in enumerate(carriers):
        waveform = generate_carrier(rng, carrier, n_snap, sn.N_SIM, FS_SIM)
        if transmit is None or transmit[index]:
            x += waveform
    n0 = 1.0 / (36e6 * 10 ** (cn_db / 10))
    x += sn.awgn(rng, x.shape, n0, FS_SIM)
    return sn.to_monitor(x)


def _core(carrier):
    half = carrier.symbol_rate * (1 - carrier.alpha) / 2
    return carrier.f0 - half, carrier.f0 + half


def _depth(iq, result, carrier):
    guard = result.config.edge_guard
    original = sn.spectrogram_db(iq[:, guard:iq.shape[1] - guard])
    lo, hi = _core(carrier)
    return band_power_db(original, lo, hi) - band_power_db(result.residual_db, lo, hi)


def test_only_observations_and_operator_plan_enter_the_canceller():
    parameters = inspect.signature(cancel_planned_carriers).parameters
    assert list(parameters) == ["iq", "plan", "config"]
    for forbidden in ("active", "label", "event", "ibo", "xpd", "symbols", "meta"):
        assert all(forbidden not in name for name in parameters)


def test_srrc_matched_pair_has_unit_peak_and_unit_energy():
    taps = srrc_taps(4.8e6, 0.2, FS_SIM, 10)
    assert taps.shape == (10 * 60 + 1,)
    assert np.isclose(np.sum(taps ** 2), 1.0)
    pulse = np.convolve(taps, taps)
    centre = len(pulse) // 2
    assert np.isclose(pulse[centre], 1.0, atol=2e-3)
    sps = 60
    zero_crossings = pulse[centre + sps::sps]
    assert np.all(np.abs(zero_crossings[:3]) < 2e-2)


def test_timing_estimator_recovers_a_known_integer_offset():
    rng = np.random.default_rng(3)
    sps = 20
    taps = srrc_taps(FS_SIM / sps, 0.25, FS_SIM, 10)
    points = constellation("QPSK")
    for offset in (0, 7, 13, 19):
        symbols = points[rng.integers(0, 4, size=(2, 400))]
        impulses = np.zeros((2, 400 * sps), np.complex128)
        impulses[:, offset::sps] = symbols
        matched = np.stack([np.convolve(np.convolve(row, taps, mode="same"), taps, mode="same") for row in impulses])
        assert np.all(_timing(matched, sps) == offset)


def test_decisions_pick_nearest_constellation_point():
    points = constellation("16APSK", "3/4")
    z = points[[0, 5, 15, 7]] * 1.02 + 0.01j
    assert _decide(z, points).tolist() == [0, 5, 15, 7]


@pytest.mark.parametrize("mod,rate,alpha,rate_code", [("QPSK", 4.8e6, 0.20, None), ("8PSK", 2.4e6, 0.35, None),
                                                      ("16APSK", 9.6e6, 0.25, "3/4"), ("32APSK", 3.6e6, 0.20, "4/5")])
def test_cancellation_reaches_the_noise_floor_at_moderate_cn(mod, rate, alpha, rate_code):
    rng = np.random.default_rng(11)
    carrier = Carrier(f0=-5.1e6, symbol_rate=rate, alpha=alpha, mod=mod, power=1.0, code_rate=rate_code)
    iq = _observe(rng, [carrier], cn_db=25)
    result = cancel_planned_carriers(iq, [carrier])
    assert result.residual_iq.shape == iq.shape and result.residual_iq.dtype == np.complex64
    assert result.residual_db.shape == (iq.shape[0], 512) and result.residual_db.dtype == np.float32
    depth = _depth(iq, result, carrier)
    assert depth > 20.0
    floor = band_power_db(sn.spectrogram_db(iq[:, 512:-512]), 30e6, 40e6)
    lo, hi = _core(carrier)
    assert abs(band_power_db(result.residual_db, lo, hi) - floor) < 1.5
    assert result.carriers[0]["decision_snr_db_median"] > 20


def test_fractional_monitor_rate_carrier_is_cancelled():
    # 3.6 Mbaud is 26.67 samples/symbol at 96 MHz but an integer 80 at 288 MHz.
    rng = np.random.default_rng(5)
    carrier = Carrier(f0=7.0e6, symbol_rate=3.6e6, alpha=0.25, mod="QPSK", power=1.0)
    iq = _observe(rng, [carrier], cn_db=25)
    assert _depth(iq, cancel_planned_carriers(iq, [carrier]), carrier) > 25.0


def test_two_carriers_are_cancelled_and_an_unplanned_carrier_survives():
    rng = np.random.default_rng(17)
    plan = [Carrier(f0=-9e6, symbol_rate=4.8e6, alpha=0.2, mod="QPSK", power=0.6),
            Carrier(f0=4e6, symbol_rate=3.0e6, alpha=0.25, mod="8PSK", power=0.4)]
    intruder = Carrier(f0=12e6, symbol_rate=2.0e6, alpha=0.2, mod="QPSK", power=0.3)
    iq = _observe(rng, plan + [intruder], cn_db=25)
    result = cancel_planned_carriers(iq, plan)
    assert all(_depth(iq, result, carrier) > 15.0 for carrier in plan)
    assert abs(_depth(iq, result, intruder)) < 1.0


def test_under_carrier_interference_becomes_visible_after_cancellation():
    rng = np.random.default_rng(23)
    victim = Carrier(f0=0.0, symbol_rate=9.6e6, alpha=0.2, mod="QPSK", power=1.0)
    hidden = Carrier(f0=0.5e6, symbol_rate=2.4e6, alpha=0.2, mod="QPSK", power=10 ** (-25 / 10))
    seeds = np.random.SeedSequence(23).spawn(2)
    clean = _observe(np.random.default_rng(seeds[0]), [victim], cn_db=25)
    # Same victim/noise streams; the hidden carrier consumes the independent remainder.
    interfered = clean + sn.to_monitor(generate_carrier(np.random.default_rng(seeds[1]), hidden, 8, sn.N_SIM, FS_SIM))
    lo, hi = _core(hidden)
    before = band_power_db(sn.spectrogram_db(interfered[:, 512:-512]), lo, hi) - band_power_db(sn.spectrogram_db(clean[:, 512:-512]), lo, hi)
    after = (band_power_db(cancel_planned_carriers(interfered, [victim]).residual_db, lo, hi)
             - band_power_db(cancel_planned_carriers(clean, [victim]).residual_db, lo, hi))
    assert before < 0.3
    assert after > 3.0


def test_missing_planned_carrier_does_not_create_a_large_residual_change():
    rng = np.random.default_rng(29)
    plan = [Carrier(f0=-9e6, symbol_rate=4.8e6, alpha=0.2, mod="QPSK", power=0.5),
            Carrier(f0=6e6, symbol_rate=4.8e6, alpha=0.2, mod="QPSK", power=0.5)]
    iq = _observe(rng, plan, cn_db=25, transmit=[True, False])
    result = cancel_planned_carriers(iq, plan)
    lo, hi = _core(plan[1])
    guard = result.config.edge_guard
    original = band_power_db(sn.spectrogram_db(iq[:, guard:-guard]), lo, hi)
    # Decision-directed fitting on noise can only lower the in-band residual, never raise it much.
    assert -6.0 < band_power_db(result.residual_db, lo, hi) - original < 1.0
    assert result.carriers[1]["decision_snr_db_median"] < result.carriers[0]["decision_snr_db_median"] - 10


def test_result_is_deterministic_and_independent_of_extra_context():
    rng = np.random.default_rng(31)
    carrier = Carrier(f0=2e6, symbol_rate=6e6, alpha=0.35, mod="8PSK", power=1.0)
    iq = _observe(rng, [carrier], cn_db=20, n_snap=3)
    first = cancel_planned_carriers(iq, [carrier])
    second = cancel_planned_carriers(iq.copy(), [Carrier(**{**carrier.__dict__, "power": 0.01})])
    assert np.array_equal(first.residual_db, second.residual_db)
    assert first.carriers[0]["basis"] == "observed IQ and operator plan only"
    assert set(first.carriers[0]) == {"plan_index", "f0", "symbol_rate", "mod", "samples_per_symbol",
                                      "symbols_per_snapshot", "timing_samples", "gain_power_db_mean",
                                      "decision_snr_db_median", "basis"}


def test_config_validation_and_identity():
    assert CancellationConfig().to_dict() == {"srrc_span_symbols": 10, "phase_grid": 16, "iterations": 3,
                                              "edge_guard": 512, "version": "obs-cancel/1"}
    for bad in ({"srrc_span_symbols": 1}, {"phase_grid": 0}, {"iterations": 0}, {"edge_guard": 2048},
                {"edge_guard": 1.5}, {"version": "other"}, {"iterations": True}):
        with pytest.raises(ValueError):
            CancellationConfig(**bad)


def test_invalid_inputs_are_rejected():
    carrier = Carrier(f0=0.0, symbol_rate=4.8e6, alpha=0.2, mod="QPSK", power=1.0)
    iq = np.zeros((2, sn.SNAP_MON), np.complex64)
    with pytest.raises(ValueError):
        cancel_planned_carriers(iq[:, :100], [carrier])
    with pytest.raises(ValueError):
        cancel_planned_carriers(iq, [])
    with pytest.raises(ValueError):
        cancel_planned_carriers(iq, [Carrier(f0=0.0, symbol_rate=4.8e6, alpha=0.2, mod="BPSK", power=1.0)])
    with pytest.raises(ValueError):
        cancel_planned_carriers(iq, [Carrier(f0=50e6, symbol_rate=4.8e6, alpha=0.2, mod="QPSK", power=1.0)])
    with pytest.raises(ValueError):
        cancel_planned_carriers(iq, [carrier], config={"iterations": 3})
    bad = iq.copy()
    bad[0, 0] = np.nan
    with pytest.raises(ValueError):
        cancel_planned_carriers(bad, [carrier])
    # Zero input is a valid, degenerate observation: finite residual, no crash.
    result = cancel_planned_carriers(iq, [carrier])
    assert np.isfinite(result.residual_db).all()


def test_untracked_phase_noise_caps_depth_independently_of_cn():
    """obs-cancel/1 fits one gain per snapshot; a 150 Hz Wiener walk bounds the depth (reviewer finding)."""
    from geosim.phase_noise import rotate_phase, wiener_phase
    rng = np.random.default_rng(41)
    carrier = Carrier(f0=2e6, symbol_rate=9.6e6, alpha=0.2, mod="QPSK", power=1.0)
    x = generate_carrier(rng, carrier, 6, sn.N_SIM, FS_SIM)
    t0 = np.arange(6) * 0.01
    depths = {}
    for linewidth in (0.0, 150.0):
        y = x if linewidth == 0 else rotate_phase(x, wiener_phase(np.random.default_rng(1), t0, sn.N_SIM, FS_SIM, linewidth))
        y = y + sn.awgn(np.random.default_rng(2), x.shape, 1.0 / (36e6 * 10 ** (40 / 10)), FS_SIM)
        iq = sn.to_monitor(y)
        depths[linewidth] = _depth(iq, cancel_planned_carriers(iq, [carrier]), carrier)
    assert depths[0.0] > 35.0
    assert 15.0 < depths[150.0] < 30.0

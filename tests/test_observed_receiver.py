"""Physical controls and input contracts for the observation-only receiver."""
from dataclasses import fields
import json

import numpy as np
import pytest

from geosim import FS_MON, FS_SIM
from geosim.observed_receiver import (
    ALGORITHM, CancellationConfig, ReceiverCarrier, cancel_observed,
)
from geosim.sensor import N_SIM, to_monitor
from geosim.waveform import Carrier, generate_carrier


def _control(mod="QPSK", symbol_rate=4e6, f0=7.2e6, seed=42):
    """Independent transmitter truth stays in this fixture, outside the receiver API."""
    transmitter = Carrier(f0, symbol_rate, 0.25, mod, 0.37, "3/4")
    iq = to_monitor(generate_carrier(np.random.default_rng(seed), transmitter, 4, N_SIM, FS_SIM))
    descriptor = ReceiverCarrier(f0, symbol_rate, 0.25, mod, "3/4")
    return iq, descriptor


def _suppression(iq, residual):
    return float(10 * np.log10(np.mean(np.abs(iq)**2) / np.mean(np.abs(residual)**2)))


@pytest.mark.parametrize("mod", ["QPSK", "8PSK", "16APSK", "32APSK"])
def test_observed_decisions_cancel_linear_carriers(mod):
    iq, descriptor = _control(mod)
    original = iq.copy()
    result = cancel_observed(iq, [descriptor])
    assert _suppression(iq, result.residual_iq) > 12
    assert result.meta["carriers"][0]["accepted_windows"] == len(iq)
    assert result.meta["algorithm"] == ALGORITHM
    np.testing.assert_array_equal(iq, original)
    np.testing.assert_allclose(result.residual_iq + result.reconstruction, iq, atol=2e-7)
    assert result.residual_iq.dtype == iq.dtype == result.reconstruction.dtype
    json.dumps(result.meta, allow_nan=False)


@pytest.mark.parametrize("symbol_rate", [7.2e6, 14.4e6, 24e6])
def test_fractional_monitor_samples_per_symbol(symbol_rate):
    iq, descriptor = _control("32APSK", symbol_rate=symbol_rate)
    result = cancel_observed(iq, [descriptor])
    assert _suppression(iq, result.residual_iq) > 12
    assert result.meta["carriers"][0]["accepted_windows"] == len(iq)


def test_off_plan_tone_survives_when_carrier_is_cancelled():
    iq, descriptor = _control(f0=-6e6)
    # Exact monitor DFT bin, well outside the occupied operator band.
    tone = np.sqrt(1e-3) * np.exp(2j * np.pi * 12e6 * np.arange(iq.shape[1]) / FS_MON)
    observed = (iq + tone).astype(np.complex64)
    result = cancel_observed(observed, [descriptor])
    assert result.meta["carriers"][0]["accepted_windows"] == len(iq)
    assert _suppression(iq, result.residual_iq - tone) > 12
    before = np.mean(observed * tone.conj(), axis=1)
    after = np.mean(result.residual_iq * tone.conj(), axis=1)
    np.testing.assert_allclose(after, before, rtol=1e-5, atol=1e-8)


@pytest.mark.parametrize("offset", [0., 0.1e6, 1e6])
def test_centered_or_in_band_tone_does_not_impersonate_carrier(offset):
    descriptor = ReceiverCarrier(0., 4e6, .25, "QPSK")
    tone = np.exp(2j * np.pi * offset * np.arange(4096) / FS_MON)
    iq = np.broadcast_to(tone, (3, 4096)).astype(np.complex64).copy()
    result = cancel_observed(iq, [descriptor])
    np.testing.assert_array_equal(result.residual_iq, iq)
    np.testing.assert_array_equal(result.reconstruction, 0)
    assert result.meta["carriers"][0]["accepted_windows"] == 0


@pytest.mark.parametrize("kind", ["zeros", "noise", "empty_plan"])
def test_absent_carrier_and_empty_plan_leave_observation_unchanged(kind):
    rng = np.random.default_rng(19)
    iq = (rng.normal(size=(4, 4096)) + 1j * rng.normal(size=(4, 4096))).astype(np.complex64)
    if kind == "zeros":
        iq[:] = 0
    plan = [] if kind == "empty_plan" else [ReceiverCarrier(7.2e6, 4e6, .25, "QPSK")]
    result = cancel_observed(iq, plan)
    np.testing.assert_array_equal(result.residual_iq, iq)
    np.testing.assert_array_equal(result.reconstruction, 0)
    assert not np.shares_memory(result.residual_iq, iq)
    json.dumps(result.meta, allow_nan=False)


def test_deterministic_replay_and_complex128_are_supported():
    iq, descriptor = _control()
    iq = iq.astype(np.complex128) * (0.4 - 0.7j)
    first = cancel_observed(iq, [descriptor])
    second = cancel_observed(iq, [descriptor])
    assert first.residual_iq.dtype == first.reconstruction.dtype == np.complex128
    np.testing.assert_array_equal(first.residual_iq, second.residual_iq)
    np.testing.assert_array_equal(first.reconstruction, second.reconstruction)
    assert first.meta == second.meta
    assert _suppression(iq, first.residual_iq) > 12


def test_descriptors_cannot_supply_transmitter_symbols_or_power():
    assert {field.name for field in fields(ReceiverCarrier)} == {
        "f0", "symbol_rate", "alpha", "mod", "code_rate"}
    with pytest.raises(TypeError):
        ReceiverCarrier(0., 4e6, .25, "QPSK", power=1.)


@pytest.mark.parametrize("change", [
    {"f0": np.inf}, {"f0": True}, {"symbol_rate": 0}, {"symbol_rate": np.nan},
    {"symbol_rate": FS_MON}, {"alpha": 0}, {"alpha": 1.1},
    {"alpha": "0.25"}, {"f0": 47e6}, {"mod": "AM"},
    {"mod": "32APSK", "code_rate": "1/2"}, {"code_rate": 3},
])
def test_invalid_operator_descriptors_fail_before_processing(change):
    values = dict(f0=0., symbol_rate=4e6, alpha=.25, mod="QPSK")
    values.update(change)
    with pytest.raises(ValueError):
        ReceiverCarrier(**values)


@pytest.mark.parametrize("iq", [
    np.zeros((1, 64)), np.zeros(64, complex), np.zeros((0, 64), complex),
    np.zeros((1, 63), complex), np.full((1, 64), np.nan + 0j),
    np.full((1, 64), np.inf + 0j), np.full((1, 64), 1e154 + 0j),
])
def test_invalid_iq_is_rejected(iq):
    with pytest.raises(ValueError):
        cancel_observed(iq, [])


def test_invalid_plan_and_config_are_rejected():
    iq = np.zeros((1, 64), np.complex64)
    carrier = ReceiverCarrier(0., 4e6, .25, "QPSK")
    for plan in (None, {}, [dict(f0=0)], [carrier] * 33, [carrier, carrier]):
        with pytest.raises(ValueError):
            cancel_observed(iq, plan)
    with pytest.raises(ValueError):
        cancel_observed(iq, [], config={})


def test_short_window_rejects_insufficient_symbols_with_finite_large_input():
    # Regression: signal/noise division previously overflowed although IQ was finite.
    iq = np.full((1, 64), 1e140 + 0j, dtype=np.complex128)
    result = cancel_observed(iq, [ReceiverCarrier(0., 4e6, .25, "QPSK")])
    assert result.meta["carriers"][0]["status"] == "too_few_guarded_symbols"
    np.testing.assert_array_equal(result.residual_iq, iq)
    json.dumps(result.meta, allow_nan=False)


def test_config_json_roundtrip(tmp_path):
    path = tmp_path / "receiver.json"
    config = CancellationConfig(timing_steps=16, fir_taps=3)
    path.write_text(json.dumps(config.to_dict(), allow_nan=False))
    assert CancellationConfig.from_file(path) == config


@pytest.mark.parametrize("change", [
    {"timing_steps": True}, {"timing_steps": 3}, {"phase_steps": 8.5},
    {"timing_refinements": 4}, {"fir_taps": 4}, {"ridge": 0},
    {"ridge": np.inf}, {"min_snr_db": np.nan}, {"min_timing_contrast": -.1},
    {"max_decision_error": 0}, {"min_relative_power": 2},
    {"max_symbol_tone_fraction": "0.5"},
])
def test_invalid_config_values(change):
    with pytest.raises(ValueError):
        CancellationConfig(**change)


@pytest.mark.parametrize("raw", ["[]", '{"ridge": NaN}', '{"ridge": 1e999}', '{"unknown": 1}'])
def test_config_rejects_nonfinite_and_unknown_json_fields(tmp_path, raw):
    path = tmp_path / "invalid.json"
    path.write_text(raw)
    with pytest.raises(ValueError):
        CancellationConfig.from_file(path)

"""Event power conventions, occupied-band placement and waveform contracts."""
from dataclasses import replace
import json

import numpy as np
import pytest

from geosim import FS_SIM
from geosim.events import adjacent_satellite, carrier_under_carrier
from geosim.interferers import InfeasibleCarrierError
from geosim.plan import random_plan
from geosim.waveform import Carrier


FACTORIES = (carrier_under_carrier, adjacent_satellite)
PLAN = [Carrier(-4e6, 3e6, 0.25, "QPSK", 0.3), Carrier(4e6, 6e6, 0.35, "16APSK", 0.7)]


@pytest.mark.parametrize("factory", FACTORIES)
def test_requested_power_and_ci_scaling_use_total_reference(factory):
    first, info = factory(np.random.default_rng(13), PLAN, 36e6, 10)
    second, other = factory(np.random.default_rng(13), PLAN, 36e6, 20)
    starts = np.arange(64) * 0.01
    a = first(np.random.default_rng(24), starts, 18432, FS_SIM)
    b = second(np.random.default_rng(24), starts, 18432, FS_SIM)
    assert a.shape == (64, 18432) and a.dtype == np.complex64
    assert np.isfinite(a).all()
    assert np.mean(np.abs(a) ** 2) == pytest.approx(0.1, rel=0.04)
    np.testing.assert_allclose(b, a / np.sqrt(10), rtol=2e-6, atol=2e-8)
    assert info["carrier"]["power"] == pytest.approx(0.1)
    assert other["carrier"]["power"] == pytest.approx(0.01)
    assert info["kind"] == factory.__name__
    assert "not uniquely identifiable" in info["identifiability"]
    json.dumps(info, allow_nan=False)


def test_under_carrier_stays_inside_chosen_victim_and_preserves_input_plan():
    before = repr(PLAN)
    for seed in range(80):
        _, info = carrier_under_carrier(np.random.default_rng(seed), PLAN, 36e6, 12)
        victim = PLAN[info["victim_index"]]
        assert info["f_lo"] >= victim.f0 - victim.occupied_bw / 2 - 1e-8
        assert info["f_hi"] <= victim.f0 + victim.occupied_bw / 2 + 1e-8
        assert info["victim_c_over_i_db"] == pytest.approx(12 + 10 * np.log10(victim.power))
        assert info["injection_stage"] == "uplink"
        assert info["power_reference"] == "total_planned_uplink"
    assert repr(PLAN) == before


def test_smallest_supported_victim_allows_equal_width_and_generates_contained_spectrum():
    victim = Carrier(0, 1e6, 0.2, "QPSK", 1)
    generate, info = carrier_under_carrier(np.random.default_rng(2), [victim], 36e6, 10)
    assert info["f_lo"] == -0.6e6 and info["f_hi"] == 0.6e6
    waveform = generate(np.random.default_rng(1), np.arange(8) * 0.01, 18432, FS_SIM)
    # This block has an integer number of symbols and a bin-centred carrier,
    # so its ideal periodic SRRC spectrum has no finite-window leakage.
    power = np.abs(np.fft.fft(waveform, axis=-1)) ** 2
    outside = np.abs(np.fft.fftfreq(waveform.shape[-1], 1 / FS_SIM)) > 0.6e6
    assert power[:, outside].sum() / power.sum() < 1e-12


@pytest.mark.parametrize("bandwidth", (36e6, 72e6))
def test_factories_accept_real_plans_and_place_carriers_inside_band(bandwidth):
    for seed in range(24):
        plan = random_plan(np.random.default_rng(seed), bandwidth)
        for factory in FACTORIES:
            _, info = factory(np.random.default_rng(seed + 500), plan, bandwidth, 8)
            assert -bandwidth / 2 <= info["f_lo"] < info["f_hi"] <= bandwidth / 2


def test_adjacent_satellite_placement_is_independent_of_wanted_plan():
    other_plan = [Carrier(1e6, 12e6, 0.2, "QPSK", 1)]
    generate, info = adjacent_satellite(np.random.default_rng(30), PLAN, 36e6, 11)
    repeated, other = adjacent_satellite(np.random.default_rng(30), other_plan, 36e6, 11)
    assert info == other
    assert info["injection_stage"] == "downlink"
    assert info["power_reference"] == "wanted_receiver_feed"
    starts = np.arange(3) * 0.01
    np.testing.assert_array_equal(generate(np.random.default_rng(7), starts, 4096, FS_SIM),
                                  repeated(np.random.default_rng(7), starts, 4096, FS_SIM))


@pytest.mark.parametrize("factory", FACTORIES)
def test_factory_and_callback_are_deterministic(factory):
    generate, info = factory(np.random.default_rng(40), PLAN, 36e6, 6)
    repeated, other = factory(np.random.default_rng(40), PLAN, 36e6, 6)
    starts = np.arange(3) * 0.01
    assert info == other
    np.testing.assert_array_equal(generate(np.random.default_rng(5), starts, 8192, FS_SIM),
                                  repeated(np.random.default_rng(5), starts, 8192, FS_SIM))


@pytest.mark.parametrize("factory", FACTORIES)
@pytest.mark.parametrize("ci", (np.nan, np.inf, -np.inf, True, "10", -101, 101))
def test_invalid_ci_rejected(factory, ci):
    with pytest.raises(ValueError, match="c_over_i_db"):
        factory(np.random.default_rng(0), PLAN, 36e6, ci)


@pytest.mark.parametrize("factory", FACTORIES)
@pytest.mark.parametrize("plan", ([], [1], [replace(PLAN[0], power=0)],
                                  [replace(PLAN[0], power=0.5)],
                                  [replace(PLAN[0], f0=18e6, power=1)],
                                  [replace(PLAN[0], symbol_rate=np.nan)],
                                  [replace(PLAN[0], symbol_rate=1.1e6, power=1)],
                                  [replace(PLAN[0], mod="bad", power=1)],
                                  [replace(PLAN[0], mod="16APSK", code_rate="bad", power=1)]))
def test_invalid_plan_rejected(factory, plan):
    with pytest.raises(ValueError):
        factory(np.random.default_rng(0), plan, 36e6, 10)


@pytest.mark.parametrize("factory", FACTORIES)
def test_invalid_factory_rng_and_bandwidth_rejected(factory):
    with pytest.raises(ValueError, match="rng"):
        factory(1, PLAN, 36e6, 10)
    for bandwidth in (np.nan, True, 1e6):
        with pytest.raises(ValueError, match="bandwidth"):
            factory(np.random.default_rng(0), PLAN, bandwidth, 10)


@pytest.mark.parametrize("factory", FACTORIES)
@pytest.mark.parametrize("change", ({"t0": []}, {"t0": [[0]]}, {"t0": [np.nan]},
                                    {"t0": [-1]}, {"t0": [1, 0]}, {"t0": [0, 0]},
                                    {"t0": ["0"]}, {"n": 0}, {"n": True}, {"n": 1.5},
                                    {"fs": 0}, {"fs": np.inf}, {"fs": True},
                                    {"fs": 1e6}, {"rng": 1}))
def test_invalid_callback_request_rejected(factory, change):
    generate, _ = factory(np.random.default_rng(0), PLAN, 36e6, 10)
    request = dict(rng=np.random.default_rng(0), t0=[0, 0.01], n=4096, fs=FS_SIM)
    request.update(change)
    with pytest.raises(ValueError):
        generate(**request)


def test_physically_valid_but_too_narrow_victim_is_explicitly_infeasible():
    plan = [Carrier(0, 0.5e6, 0.2, "QPSK", 1)]
    with pytest.raises(InfeasibleCarrierError, match="no planned victim"):
        carrier_under_carrier(np.random.default_rng(0), plan, 36e6, 10)

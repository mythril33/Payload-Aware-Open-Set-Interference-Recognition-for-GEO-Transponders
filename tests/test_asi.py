"""Uplink adjacent-satellite interference: ITU antenna patterns, geometry and carrier placement."""
import json

import numpy as np
import pytest

from geosim import asi
from geosim.interferers import InfeasibleCarrierError
from geosim.plan import monitor_freqs
from geosim.scenario import ScenarioConfig, default_plan, simulate
from geosim.waveform import Carrier

DL_12 = 1.2 * 14.25e9 / asi.C_LIGHT          # 57.0, ITU-R S.1428-1 branch 25 < D/lambda <= 100
DL_24 = 2.4 * 14.25e9 / asi.C_LIGHT          # 114.1, branch D/lambda > 100


def test_s1428_matches_hand_values_and_is_continuous():
    gmax = 20 * np.log10(DL_12) + 7.7
    assert asi.max_gain_dbi(DL_12) == pytest.approx(gmax)
    assert asi.s1428_gain_dbi(2.0, DL_12) == (pytest.approx(29 - 25 * np.log10(2.0)), "sidelobe")
    g1 = 29 - 25 * np.log10(95 / DL_12)
    phi_m = 20 / DL_12 * np.sqrt(gmax - g1)
    assert asi.s1428_gain_dbi(phi_m - 1e-9, DL_12)[0] == pytest.approx(g1, abs=1e-6)
    assert asi.s1428_gain_dbi(95 / DL_12 - 1e-9, DL_12) == (pytest.approx(g1), "first_sidelobe")
    assert asi.s1428_gain_dbi(95 / DL_12 + 1e-9, DL_12)[0] == pytest.approx(g1, abs=1e-6)
    assert asi.s1428_gain_dbi(50.0, DL_12) == (-9.0, "far")
    assert asi.max_gain_dbi(DL_24) == pytest.approx(20 * np.log10(DL_24) + 8.4)
    assert asi.s1428_gain_dbi(5.0, DL_24)[0] == pytest.approx(29 - 25 * np.log10(5.0))
    assert asi.s1428_gain_dbi(20.0, DL_24)[0] == pytest.approx(34 - 30 * np.log10(20.0))
    with pytest.raises(ValueError, match="D/lambda = 20"):
        asi.s1428_gain_dbi(2.0, 15.0)


def test_s465_envelope_and_phi_min():
    assert asi.s465_phi_min_deg(DL_12) == pytest.approx(max(1.0, 100 / DL_12))
    assert asi.s465_phi_min_deg(40.0) == pytest.approx(max(2.0, 114 * 40.0 ** -1.09))
    assert asi.gain_dbi(2.2, DL_12, "S.465") == (pytest.approx(32 - 25 * np.log10(2.2)), "s465_envelope")
    held = 32 - 25 * np.log10(asi.s465_phi_min_deg(DL_12))
    assert asi.gain_dbi(1.6, DL_12, "S.465")[0] == pytest.approx(max(asi.s1428_gain_dbi(1.6, DL_12)[0], held))
    assert asi.gain_dbi(0.0, DL_12, "S.465")[0] == pytest.approx(asi.max_gain_dbi(DL_12))
    with pytest.raises(ValueError, match="pattern"):
        asi.gain_dbi(2.0, DL_12, "S.580")


@pytest.mark.parametrize("diameter", asi.DEFAULT_RANGES.diameters_m)
@pytest.mark.parametrize("pattern", asi.PATTERNS)
def test_gain_never_rises_off_axis(diameter, pattern):
    dl = diameter * 14.25e9 / asi.C_LIGHT
    gains = [asi.gain_dbi(phi, dl, pattern)[0] for phi in np.linspace(0, 30, 3001)]
    assert np.all(np.diff(gains) <= 1e-9)
    assert asi.gain_dbi(2.0, dl, "S.465")[0] >= asi.gain_dbi(2.0, dl, "S.1428")[0]


def test_geometry_is_consistent_and_within_sources():
    rng = np.random.default_rng(5)
    seen = set()
    for _ in range(500):
        g = asi.draw_geometry(rng)
        seen.add(g["pattern_region"])
        assert g["c_over_i_psd_db"] == pytest.approx(g["max_gain_dbi"] - g["gain_toward_victim_dbi"] - g["delta_eirp_density_db"])
        assert g["discrimination_db"] >= 0
        assert g["pointing_error_deg"] <= 0.4 * g["beamwidth_deg"] + 1e-12
        assert g["own_link_pointing_loss_db"] <= 12 * 0.4 ** 2 + 1e-9
        assert g["separation_deg"] - g["pointing_error_deg"] - 1e-12 <= g["off_axis_deg"] <= g["separation_deg"] + g["pointing_error_deg"] + 1e-12
        assert 2.06 <= g["separation_deg"] <= 2.36 and -3 <= g["delta_eirp_density_db"] <= 6
        assert -5 < g["c_over_i_psd_db"] < 40
    assert {"main_lobe", "sidelobe", "s465_envelope"} <= seen


def test_ranges_are_validated():
    with pytest.raises(ValueError, match="33.3"):
        asi.AsiRanges(diameters_m=(0.6,))
    with pytest.raises(ValueError, match="ordered"):
        asi.AsiRanges(overlap=(0.8, 0.2))
    with pytest.raises(ValueError, match="10.7-30 GHz"):
        asi.AsiRanges(frequency_hz=6e9)


@pytest.mark.parametrize("bandwidth", [36e6, 72e6])
def test_uplink_carrier_power_placement_and_metadata(bandwidth):
    for seed in range(40):
        plan = default_plan(seed, bandwidth)
        generate, info = asi.adjacent_satellite_uplink(np.random.default_rng(seed), plan, bandwidth)
        c = Carrier(**info["carrier"])
        mean_psd = 1.0 / sum(p.symbol_rate for p in plan)
        assert 10 * np.log10(mean_psd / (c.power / c.symbol_rate)) == pytest.approx(info["c_over_i_psd_db"])
        assert info["c_over_i_db"] == pytest.approx(-10 * np.log10(c.power))
        assert abs(c.f0) + c.occupied_bw / 2 <= bandwidth / 2 + 1e-6
        assert 0.2 - 1e-9 <= info["overlap_fraction"] <= 0.8 + 1e-9
        assert info["kind"] == "adjacent_satellite" and info["injection_stage"] == "uplink"
        assert info["power_reference"] == "total_planned_uplink"
        json.dumps(info, allow_nan=False)
    _, again = asi.adjacent_satellite_uplink(np.random.default_rng(seed), plan, bandwidth)
    assert again == info
    x = generate(np.random.default_rng(1), np.arange(64) * 1e-3, 4096, 288e6)
    assert x.shape == (64, 4096) and np.mean(np.abs(x) ** 2) == pytest.approx(c.power, rel=0.1)


def test_overlap_range_that_no_carrier_meets_is_infeasible():
    full = [Carrier(f0=0.0, symbol_rate=28.8e6, alpha=0.25, mod="QPSK", power=1.0)]   # occupies all 36 MHz
    with pytest.raises(InfeasibleCarrierError, match="overlap"):
        asi.adjacent_satellite_uplink(np.random.default_rng(0), full, 36e6)
    _, info = asi.adjacent_satellite_uplink(np.random.default_rng(0), full, 36e6, asi.AsiRanges(overlap=(0.9, 1.0)))
    assert info["overlap_fraction"] == pytest.approx(1.0)


def test_uplink_event_raises_psd_in_its_band_through_the_payload():
    seed = 610_500
    cfg = ScenarioConfig(bandwidth=36e6, ibo_db=11.0, cn_up_db=25.0, cn_dn_db=25.0, seed=seed)
    plan = default_plan(seed, 36e6)
    ranges = asi.AsiRanges(delta_eirp_density_db=(6.0, 6.0), diameters_m=(0.75,))
    generate, info = asi.adjacent_satellite_uplink(np.random.default_rng(3), plan, 36e6, ranges)
    clean, event = simulate(cfg, plan=plan), simulate(cfg, plan=plan, interferer=generate)
    freqs = monitor_freqs()
    band = (freqs >= info["f_lo"]) & (freqs <= info["f_hi"])
    outside = (freqs < info["f_lo"] - 2e6) | (freqs > info["f_hi"] + 2e6)
    power = lambda r, sel: np.mean(10 ** (r.spec_db[:, sel].astype(float) / 10))
    assert 10 * np.log10(power(event, band) / power(clean, band)) > 0.3
    assert abs(10 * np.log10(power(event, outside) / power(clean, outside))) < 0.3

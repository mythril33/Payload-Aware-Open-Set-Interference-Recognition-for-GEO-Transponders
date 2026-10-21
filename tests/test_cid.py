"""DVB-CID overlay: ETSI TS 103 129 test vectors, waveform accuracy, PSD level and continuity."""
import json

import numpy as np
import pytest
from scipy.signal import welch

from geosim import cid
from geosim.plan import monitor_freqs
from geosim.scenario import ScenarioConfig, default_plan, simulate
from geosim.waveform import Carrier

FS = 288e6
EXAMPLE_GUID = 0x0006B0FFFF01AC07                  # clause 4.1 example 2


def test_specification_test_vectors():
    assert cid.check_digits(EXAMPLE_GUID) == 0x75                  # clause 4.1 example 4
    chips = cid.chip_pattern()
    assert chips.size == 4096 and int("".join(map(str, chips[:32])), 2) == 0x5091E364   # clause 5.5
    g = cid.bch_generator()
    assert g.bit_length() - 1 == 42 and cid._poly_mod((1 << 127) | 1, g) == 0           # cyclic (127, 85) code
    data = list(np.random.default_rng(0).integers(0, 2, 69))
    codeword = int("".join(map(str, data + cid.bch_parity(data))), 2)
    assert cid._poly_mod(codeword, g) == 0


def test_frame_structure():
    first, second = cid.frame_bits(EXAMPLE_GUID, 0), cid.frame_bits(EXAMPLE_GUID, 1)
    assert len(first) == 244
    assert int("".join(map(str, first[:22])), 2) == 0x147147 and int("".join(map(str, second[:22])), 2) == 0x2B8EB8
    assert first[22:] == second[22:]                                  # scrambler reset per frame
    stream = cid.bit_stream(EXAMPLE_GUID)
    assert stream.size == 2 * 2 * 244 * 4
    raw = np.array((first * 4 + second * 4) * 2, np.uint8)
    assert np.array_equal(stream, np.bitwise_xor.accumulate(raw))


def test_table6_levels_and_chip_rates():
    assert cid.relative_psd_db(200e3) == -27.5 and cid.relative_psd_db(1.5e6) == -27.5
    assert cid.relative_psd_db(3e6) == -24.5 and cid.relative_psd_db(6e6) == -21.5
    assert cid.relative_psd_db(9.6e6) == -18.5 and cid.relative_psd_db(28.8e6) == -17.5
    assert cid.chip_rate(256e3) == 112e3 and cid.chip_rate(1e6) == 224e3
    with pytest.raises(ValueError, match="128 kBd"):
        cid.relative_psd_db(100e3)


def _rrc(t):
    a = cid.ROLLOFF
    out = np.empty_like(t)
    zero, edge = np.isclose(t, 0), np.isclose(np.abs(t), 1 / (4 * a))
    r = ~(zero | edge)
    out[r] = (np.sin(np.pi * t[r] * (1 - a)) + 4 * a * t[r] * np.cos(np.pi * t[r] * (1 + a))) / (np.pi * t[r] * (1 - (4 * a * t[r]) ** 2))
    out[zero] = 1 - a + 4 * a / np.pi
    out[edge] = a / np.sqrt(2) * ((1 + 2 / np.pi) * np.sin(np.pi / (4 * a)) + (1 - 2 / np.pi) * np.cos(np.pi / (4 * a)))
    return out


def test_window_matches_direct_rrc_sum_and_is_continuous():
    host = Carrier(f0=0.0, symbol_rate=4e6, alpha=0.2, mod="QPSK", power=1.0)
    c = cid._Cid(host, EXAMPLE_GUID, start_chip=123_456, start_sample=4321, phase=0.0)
    s0, n = 2_880_000, 3000
    got = c.window(s0, n)
    per_chip = FS / c.rc
    t_chips = (s0 + np.arange(n) - c.start_sample) / per_chip
    ks = np.arange(int(t_chips[0]) - 40, int(t_chips[-1]) + 41)
    ref = sum(c.chips(np.array([k]))[0] * _rrc(t_chips - k) for k in ks)
    assert np.sqrt(np.mean((got - ref) ** 2) / np.mean(ref ** 2)) < 0.02
    later = c.window(s0 + 1000, n)
    assert np.allclose(later[: n - 1000], got[1000:], atol=1e-6)


def test_cid_psd_is_table6_level_below_host_centre():
    for rs in (1.5e6, 9.6e6):
        host = Carrier(f0=3e6, symbol_rate=rs, alpha=0.2, mod="QPSK", power=1.0)
        generate, info = cid.cid_overlay(np.random.default_rng(2), [host], 36e6)
        x = generate(np.random.default_rng(0), np.arange(64) * 10e-3, 14592, FS)
        f, p = welch(x, fs=FS, nperseg=8192, return_onesided=False, axis=-1)
        p = p.mean(axis=0)
        info_cid = info["cids"][0]
        centre = np.abs(f - info_cid["f_center"]) < 0.25 * info_cid["chip_rate"]
        level = 10 * np.log10(np.mean(p[centre]) / (host.power / host.symbol_rate))
        assert level == pytest.approx(cid.relative_psd_db(rs), abs=0.5)        # Table 6 accuracy +/-0.5 dB
        band = np.abs(f - info_cid["f_center"]) < 0.5 * info_cid["chip_rate"] * (1 + cid.ROLLOFF)
        assert p[band].sum() / p.sum() > 0.98


def test_overlay_metadata_and_validation():
    plan = default_plan(7, 36e6)
    generate, info = cid.cid_overlay(np.random.default_rng(1), plan, 36e6)
    assert info["legitimate"] and info["expected_label"] == "clean" and len(info["cids"]) == len(plan)
    for entry, host in zip(info["cids"], plan):
        guid = int(entry["guid"], 16)
        assert (guid >> 24) & 0xFFFF == 0xFFFF and (guid >> 56) & 0x03 == 0x02     # MAC-48, unicast, local
        assert entry["f_center"] == pytest.approx(host.f0 + 220.0)
    json.dumps(info, allow_nan=False)
    with pytest.raises(ValueError, match="sample grid"):
        generate(np.random.default_rng(0), np.array([0.5e-9]), 100, FS)
    with pytest.raises(ValueError, match="FS_SIM"):
        generate(np.random.default_rng(0), np.array([0.0]), 100, 96e6)


def test_cid_scene_passes_the_payload_with_small_in_band_change():
    seed = 610_700
    cfg = ScenarioConfig(bandwidth=36e6, ibo_db=11.0, cn_up_db=25.0, cn_dn_db=25.0, seed=seed)
    plan = default_plan(seed, 36e6)
    generate, info = cid.cid_overlay(np.random.default_rng(3), plan, 36e6)
    clean, event = simulate(cfg, plan=plan), simulate(cfg, plan=plan, interferer=generate)
    freqs = monitor_freqs()
    band = np.abs(freqs - info["cids"][0]["f_center"]) < 150e3
    power = lambda r: np.mean(10 ** (r.spec_db[:, band].astype(float) / 10))
    delta = 10 * np.log10(power(event) / power(clean))
    assert 0 < delta < 0.5                                             # CID sits well below its host


def test_cid_overlay_mutes_cids_of_inactive_hosts_but_keeps_identifier_draws():
    import numpy as np
    from geosim.cid import cid_overlay
    from geosim.scenario import default_plan
    plan = default_plan(5, 36e6)
    assert len(plan) >= 2
    full_gen, full_meta = cid_overlay(np.random.default_rng(1), plan, 36e6)
    active = [True] * len(plan)
    active[0] = False
    part_gen, part_meta = cid_overlay(np.random.default_rng(1), plan, 36e6, active=active)
    assert [c["guid"] for c in full_meta["cids"]] == [c["guid"] for c in part_meta["cids"]]
    assert part_meta["n_transmitted"] == len(plan) - 1 and part_meta["cids"][0]["host_active"] is False
    t0 = np.arange(2) * 0.01
    full = full_gen(np.random.default_rng(0), t0, 6000, 288e6)
    part = part_gen(np.random.default_rng(0), t0, 6000, 288e6)
    assert np.mean(np.abs(part) ** 2) < np.mean(np.abs(full) ** 2)
    with pytest.raises(ValueError):
        cid_overlay(np.random.default_rng(1), plan, 36e6, active=[True])

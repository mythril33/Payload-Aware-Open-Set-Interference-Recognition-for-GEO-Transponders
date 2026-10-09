"""Checks for interferer generators and class sampling (docs/plan/P3_taksonomi.md §5)."""
import numpy as np
import pytest

from geosim import FS_SIM as FS
from geosim import interferers as it
from geosim import sensor as sn
from geosim.classes import DEFAULT_RANGES, LABELS, sample
from geosim.plan import monitor_freqs
from geosim.scenario import default_plan
from geosim.waveform import Carrier

T0 = np.arange(16) * 10e-3
N = 1 << 14


def _peak_freq(x):
    spec = np.abs(np.fft.fft(x, axis=-1)) ** 2
    return np.fft.fftfreq(x.shape[-1], 1 / FS)[np.argmax(spec, axis=-1)]


def test_cw_frequency_and_power():
    gen, meta = it.cw(7.3e6, 12.0)
    x = gen(np.random.default_rng(0), T0, N, FS)
    assert x.shape == (16, N) and np.allclose(_peak_freq(x), 7.3e6, atol=FS / N)
    assert abs(10 * np.log10(np.mean(np.abs(x) ** 2)) + 12.0) < 1e-3
    assert meta["kind"] == "cw" and meta["f_lo"] == meta["f_hi"] == 7.3e6


@pytest.mark.parametrize("shape", ["sawtooth", "triangle"])
def test_swept_cw_follows_its_sweep(shape):
    gen, meta = it.swept_cw(-8e6, 6e6, 0.4, 20.0, shape, t_offset=0.05)
    x = gen(np.random.default_rng(1), T0, N, FS)
    expected = it.sweep_frequency(T0 + 0.5 * N / FS, -8e6, 6e6, 0.4, shape, 0.05)
    assert np.allclose(_peak_freq(x), expected, atol=3 * FS / N)
    assert np.ptp(_peak_freq(x)) > 5e6                       # it moves between snapshots
    assert abs(10 * np.log10(np.mean(np.abs(x) ** 2)) + 20.0) < 1e-3
    f = it.sweep_frequency(np.linspace(0, 3, 10001), -8e6, 6e6, 0.4, shape)
    assert f.min() >= -8e6 and f.max() <= 6e6


def test_free_gaps_and_unauthorized_placement():
    plan = [Carrier(-10e6, 6e6, 0.2, "QPSK", 0.5), Carrier(8e6, 9e6, 0.25, "8PSK", 0.5)]
    gaps = it.free_gaps(plan, 36e6)
    assert np.allclose(gaps, [(-18e6, -13.6e6), (-6.4e6, 2.375e6), (13.625e6, 18e6)])
    for seed in range(50):
        c = it.random_unauthorized(np.random.default_rng(seed), plan, 36e6, -3.0)
        lo, hi = c.f0 - c.occupied_bw / 2, c.f0 + c.occupied_bw / 2
        assert not it.overlaps_plan(lo, hi, plan) and -18e6 <= lo and hi <= 18e6
        mean_psd = 1.0 / (6e6 + 9e6)
        assert abs(10 * np.log10(c.power / c.symbol_rate / mean_psd) + 3.0) < 1e-9
    full = [Carrier(0.0, 28.8e6, 0.2, "QPSK", 1.0)]          # 34.56 MHz occupied: 0.72 MHz free each side
    with pytest.raises(ValueError):
        it.random_unauthorized(np.random.default_rng(0), full, 36e6, 0.0)


def test_classes_share_everything_but_the_interferer():
    res = {lab: sample(lab, 36e6, seed=3, n_snap=8) for lab in LABELS}
    plans = [r.meta["plan"] for r in res.values()]
    assert all(p == plans[0] for p in plans)
    for lab in ("cw", "swept_cw", "unauthorized"):
        cfg, ref = res[lab].meta["config"], res["clean"].meta["config"]
        assert cfg == ref and res[lab].meta["has_interferer"]
    lo, hi = DEFAULT_RANGES.ibo_overdrive_db
    assert lo <= res["overdrive"].meta["config"]["ibo_db"] <= hi
    lo, hi = DEFAULT_RANGES.ibo_nominal_db
    assert lo <= res["clean"].meta["config"]["ibo_db"] <= hi
    assert res["overdrive"].meta["obo_db"] < res["clean"].meta["obo_db"] - 1.0
    assert np.array_equal(sample("cw", 36e6, seed=3, n_snap=8).spec_db, res["cw"].spec_db)


def test_strong_cw_shows_up_where_it_was_injected():
    """Paired clean/CW scenarios differ at the CW's frequency bin after the whole chain."""
    f = monitor_freqs()
    plan = default_plan(5, 36e6)
    gap_lo, gap_hi = max(it.free_gaps(plan, 36e6), key=lambda g: g[1] - g[0])
    f0 = 0.5 * (gap_lo + gap_hi)
    from geosim.scenario import ScenarioConfig, simulate
    cfg = ScenarioConfig(bandwidth=36e6, ibo_db=11, n_snap=16, seed=5)
    clean = simulate(cfg, plan=plan)
    dirty = simulate(cfg, plan=plan, interferer=it.cw(f0, 15.0)[0])
    diff = np.mean(dirty.spec_db - clean.spec_db, axis=0)
    assert abs(f[np.argmax(diff)] - f0) <= 187.5e3 and diff.max() > 10
    far = np.abs(f - f0) > 5e6
    assert np.abs(diff[far & (np.abs(f) < 16e6)]).mean() < 1.0


def test_interferer_drives_the_amplifier_harder():
    """Fixed-gain mode: a strong uplink CW lowers the actual input back-off (spec P2 §2.5)."""
    from geosim.scenario import ScenarioConfig, simulate
    cfg = ScenarioConfig(bandwidth=36e6, ibo_db=8, n_snap=8, seed=2)
    clean = simulate(cfg)
    dirty = simulate(cfg, interferer=it.cw(1e6, 0.0)[0])       # as strong as all carriers together
    assert abs((clean.meta["actual_ibo_db"] - dirty.meta["actual_ibo_db"]) - 3.0) < 0.3


@pytest.mark.parametrize("bw", [36e6, 72e6])
def test_sampled_parameters_stay_in_range(bw):
    r = DEFAULT_RANGES
    for seed in range(40):
        for lab in ("cw", "swept_cw"):
            info = _info(lab, bw, seed)
            assert r.c_over_i_db[0] <= info["c_over_i_db"] <= r.c_over_i_db[1]
            assert -r.band_fraction * bw <= info["f_lo"] <= info["f_hi"] <= r.band_fraction * bw
        info = _info("swept_cw", bw, seed)
        assert info["f_hi"] - info["f_lo"] >= 1e6 and 0.1 <= info["period"] <= 1.28


def _info(label, bw, seed):
    """Interferer parameters without running the chain."""
    import geosim.classes as c
    captured = {}
    original = c.simulate
    c.simulate = lambda cfg, plan=None, interferer=None, keep_iq=False: type(
        "R", (), {"meta": captured})()
    try:
        return c.sample(label, bw, seed).meta["interferer"]
    finally:
        c.simulate = original

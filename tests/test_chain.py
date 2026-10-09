"""Validation tests T1-T12 from docs/plan/P2_sistem_modeli.md §4."""
import numpy as np
import pytest
from scipy.signal import resample_poly, sosfreqz, welch

from geosim import FS_MON, FS_SIM
from geosim import payload as pl
from geosim import sensor as sn
from geosim.plan import plan_mask_db, random_plan
from geosim.scenario import ScenarioConfig, simulate
from geosim.waveform import Carrier, constellation, generate_carrier, shape, srrc_taps

FS = FS_SIM


def db(x):
    return 10 * np.log10(x)


@pytest.mark.parametrize("alpha", [0.20, 0.25, 0.35])
def test_t1_bandwidths(alpha):
    rs = 12e6
    c = Carrier(0.0, rs, alpha, "QPSK", 1.0)
    x = generate_carrier(np.random.default_rng(1), c, 64, 1 << 16, FS).ravel()
    f, p = welch(x, fs=FS, nperseg=4096, return_onesided=False, detrend=False)
    f, p = np.fft.fftshift(f), np.fft.fftshift(p)
    p = np.convolve(p, np.ones(9) / 9, mode="same")
    half = f[p >= 0.5 * np.median(p[np.abs(f) < 0.3 * rs])]
    assert abs((half.max() - half.min()) / rs - 1) <= 0.02            # -3 dB bandwidth = Rs
    inside = np.abs(f) <= rs * (1 + alpha) / 2
    assert p[inside].sum() / p.sum() >= 0.999                          # occupied bandwidth = Rs(1+alpha)
    assert abs(np.mean(np.abs(x) ** 2) - 1.0) <= 0.02                  # configured power


@pytest.mark.parametrize("mod", ["QPSK", "8PSK", "16APSK", "32APSK"])
@pytest.mark.parametrize("alpha", [0.20, 0.35])
def test_t2_evm(mod, alpha):
    sps, rng = 8, np.random.default_rng(2)
    pts = constellation(mod)
    assert abs(np.mean(np.abs(pts) ** 2) - 1) < 1e-12
    a = pts[rng.integers(0, len(pts), 4000)]
    taps = srrc_taps(alpha, sps)
    rx = np.convolve(shape(a, alpha, sps), taps)[len(taps) - 1::sps][:len(a)]
    evm = np.sqrt(np.mean(np.abs(rx - a) ** 2) / np.mean(np.abs(a) ** 2))
    assert evm <= 0.01


def test_t3_noise_density():
    n0, bw = 1 / (36e6 * 10 ** 2.5), 36e6
    w = sn.awgn(np.random.default_rng(3), (64, 1 << 15), n0, FS)
    f, p = welch(w.ravel(), fs=FS, nperseg=2048, return_onesided=False, detrend=False)
    in_band = p[np.abs(f) <= bw / 2].mean() * bw
    assert abs(db(1.0 / in_band) - 25.0) <= 0.2


def _group_delay_ns(sos, offsets_hz):
    f = np.linspace(-0.6, 0.6, 24001) * offsets_hz[-1] / 0.5
    _, h = sosfreqz(sos, worN=2 * np.pi * f / FS)
    gd = -np.gradient(np.unwrap(np.angle(h)), 2 * np.pi * f)
    centre = gd[np.argmin(np.abs(f))]
    return [(gd[np.argmin(np.abs(f - o))] - centre) * 1e9 for o in offsets_hz]


@pytest.mark.parametrize("model,bw,imux,omux", [
    ("dvbs2x", 36e6, [4.9, 20.4, 35.8, 64.7], [4.0, 16.2, 30.8]),
    ("dvbs2x", 72e6, [2.4, 9.5, 16.4, 30.9], [1.7, 6.7, 15.1]),
    ("generic", 36e6, [6.8, 28.7, 48.1, 136.5], [2.1, 4.4, 10.8]),
    ("generic", 72e6, [3.6, 15.0, 25.6, 75.4], [1.3, 2.8, 6.8]),
])
def test_t4_group_delay(model, bw, imux, omux):
    got = _group_delay_ns(pl.imux_sos(bw, FS, model), [0.25 * bw, 0.40 * bw, 0.45 * bw, 0.50 * bw])
    assert np.allclose(got, imux, atol=1.0)
    got = _group_delay_ns(pl.omux_sos(bw, FS, model), [0.25 * bw, 0.40 * bw, 0.50 * bw])
    assert np.allclose(got, omux, atol=1.0)


def test_t4_reference_filter_selectivity():
    """36 MHz reference filters: flat to +/-14 MHz, about -34 / -38 dB at the stop-band edges."""
    def gain_db(sos, f):
        return 20 * np.log10(np.abs(sosfreqz(sos, worN=2 * np.pi * np.array([f]) / FS)[1][0]))
    assert gain_db(pl.imux_sos(36e6, FS), 14e6) > -0.1 and abs(gain_db(pl.imux_sos(36e6, FS), 23e6) + 34) < 0.1
    assert gain_db(pl.omux_sos(36e6, FS), 14e6) > -0.2 and abs(gain_db(pl.omux_sos(36e6, FS), 28.6e6) + 38) < 0.1


def test_t5_am_am_am_pm():
    r = np.linspace(1e-3, 2.0, 2000)
    y = pl.saleh((r * np.exp(1j * 0.7)).astype(np.complex128))
    assert np.max(np.abs(db(np.abs(y) ** 2) - db((2.1587 * r / (1 + 1.1517 * r ** 2)) ** 2))) <= 0.01
    phase = np.degrees(np.angle(y * np.exp(-1j * 0.7)))
    assert np.max(np.abs(phase - np.degrees(4.0033 * r ** 2 / (1 + 9.1040 * r ** 2)))) <= 0.1
    assert abs(r[np.argmax(np.abs(y))] - pl.R_SAT) < 2e-3 and abs(np.abs(y).max() - 1.0058) < 1e-3


@pytest.mark.parametrize("ibo,obo", [(0, 0.00), (3, 0.51), (6, 1.93), (10, 4.81), (15, 9.25)])
def test_t6_tone_ibo_obo(ibo, obo):
    tone = np.exp(2j * np.pi * 0.01 * np.arange(4096)).astype(np.complex64)
    assert abs(pl.obo_db(pl.saleh(pl.drive_gain(1.0, ibo) * tone)) - obo) <= 0.02


def _two_tone_c_im3(ibo):
    n, k1, k2 = 1 << 14, 400, 520
    x = (np.exp(2j * np.pi * k1 * np.arange(n) / n) + np.exp(2j * np.pi * k2 * np.arange(n) / n)) / np.sqrt(2)
    s = np.abs(np.fft.fft(pl.saleh((pl.drive_gain(1.0, ibo) * x).astype(np.complex128)))) ** 2
    return s, k1, k2


def test_t7_im3_location():
    s, k1, k2 = _two_tone_c_im3(6.0)
    s[[k1, k2]] = 0
    assert set(np.argsort(s)[-2:]) == {2 * k1 - k2, 2 * k2 - k1}


def test_t8_im3_slope():
    def c_im3(ibo):
        s, k1, k2 = _two_tone_c_im3(ibo)
        return db(s[k1] / s[2 * k1 - k2])
    # Saleh reaches the 2 dB/dB small-signal slope only below about 30 dB back-off
    assert abs((c_im3(35.0) - c_im3(30.0)) / 5.0 - 2.0) <= 0.05
    assert 1.0 < (c_im3(8.0) - c_im3(3.0)) / 5.0 < 1.5      # operating range: much shallower


def test_t9_multicarrier_c_im_monotonic():
    plan = [Carrier(-9e6, 6e6, 0.2, "QPSK", 0.5), Carrier(9e6, 6e6, 0.2, "8PSK", 0.5)]
    rng = np.random.default_rng(9)
    x = sum(generate_carrier(rng, c, 32, 1 << 14, FS) for c in plan)
    ratios = []
    for ibo in (3, 6, 9, 12, 15):
        y = pl.saleh(pl.drive_gain(1.0, ibo) * x).ravel()
        f, p = welch(y, fs=FS, nperseg=2048, return_onesided=False, detrend=False)
        ratios.append(db(p[np.abs(np.abs(f) - 9e6) < 2e6].mean() / p[np.abs(f) < 2e6].mean()))
    assert np.all(np.diff(ratios) > 0)


@pytest.mark.parametrize("bw", [36e6, 72e6])
def test_t10_aliasing(bw):
    plan = random_plan(np.random.default_rng(10), bw)
    rng = np.random.default_rng(11)
    hi = sum(generate_carrier(rng, c, 16, 1 << 15, 2 * FS) for c in plan)   # 576 MHz
    lo = hi[:, ::2]                                                        # same waveform at 288 MHz
    g = pl.drive_gain(1.0, 3.0)

    def band_power(y, fs, nperseg):
        f, p = welch(y, fs=fs, nperseg=nperseg, return_onesided=False, detrend=False, window="boxcar",
                     noverlap=0, axis=-1)
        edges = np.linspace(-bw / 2, bw / 2, 19)
        return np.array([p[:, (f >= a) & (f < b)].mean() for a, b in zip(edges[:-1], edges[1:])])
    d = db(band_power(pl.saleh(g * hi), 2 * FS, 4096)) - db(band_power(pl.saleh(g * lo), FS, 2048))
    assert np.max(np.abs(d)) <= 0.1


def test_t11_sensor_noise_floor():
    n0 = 3e-9
    w = sn.awgn(np.random.default_rng(12), (128, sn.N_SIM), n0, FS)
    s = sn.spectrogram_db(sn.to_monitor(w))
    f = np.fft.fftshift(np.fft.fftfreq(sn.NFFT, 1 / FS_MON))
    assert s.shape == (128, 512)
    assert abs(db(np.mean(10 ** (s[:, np.abs(f) <= 40e6] / 10))) - db(n0)) <= 0.2


def test_t12_reproducible_and_interferer_isolated():
    cfg = ScenarioConfig(bandwidth=36e6, n_snap=8, seed=5)
    a, b = simulate(cfg), simulate(cfg)
    assert np.array_equal(a.spec_db, b.spec_db) and np.array_equal(a.mask_db, b.mask_db)
    assert a.meta["plan"] == simulate(cfg, interferer=lambda rng, t0, n, fs: np.zeros((8, n))).meta["plan"]
    assert not np.array_equal(a.spec_db, simulate(ScenarioConfig(bandwidth=36e6, n_snap=8, seed=6)).spec_db)


def test_mask_matches_clean_linear_spectrum():
    cfg = ScenarioConfig(bandwidth=72e6, ibo_db=15, cn_up_db=40, cn_dn_db=40, linear=True, n_snap=64, seed=7)
    r = simulate(cfg)
    mean_db = db(np.mean(10 ** (r.spec_db / 10), axis=0))
    core = r.mask_db > -3
    assert np.std((mean_db - r.mask_db)[core]) <= 1.0     # same shape where carriers are planned
    assert np.array_equal(r.mask_db, plan_mask_db([Carrier(**c) for c in r.meta["plan"]]))

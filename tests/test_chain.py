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


def _rel_delay_ns(filt, offsets_hz):
    span = 1.3 * max(abs(o) for o in offsets_hz)
    f = np.linspace(-span, span, 8001)
    gd = -np.gradient(np.unwrap(np.angle(filt.response(f))), 2 * np.pi * f)
    centre = gd[np.argmin(np.abs(f))]
    return [(gd[np.argmin(np.abs(f - o))] - centre) * 1e9 for o in offsets_hz]


def _gain_db(filt, f):
    return 20 * np.log10(np.abs(filt.response(np.atleast_1d(f))))


# Values copied from the ETSI TR 102 376-2 Annex E tables (36 MHz): offset MHz -> (gain dB, delay ns
# relative to band centre).
ETSI_IMUX = {-18.0: (-1.18, 36.8), 18.0: (-1.34, 39.9), -15.075: (-0.377, 10.0), 13.5: (-0.185, 4.4),
             20.025: (-5.57, 94.9)}
ETSI_OMUX = {-18.0: (-1.073, 40.1), 18.0: (-1.013, 34.9), 14.0: (-0.204, 11.5), -14.0: (-0.314, 13.5),
             20.0: (-3.866, 45.2)}


@pytest.mark.parametrize("kind,table", [("imux", ETSI_IMUX), ("omux", ETSI_OMUX)])
@pytest.mark.parametrize("bw", [36e6, 72e6])
def test_t4_etsi_filters_match_tables(kind, table, bw):
    """Default filters reproduce the reference tables; 72 MHz follows the H.7 scaling rule."""
    k = bw / 36e6
    filt = getattr(pl, kind)(bw, FS)
    offs = [o * 1e6 * k for o in table]
    assert np.allclose(_gain_db(filt, offs), [v[0] for v in table.values()], atol=0.1)
    assert np.allclose(_rel_delay_ns(filt, offs), [v[1] / k for v in table.values()], atol=2.0)


@pytest.mark.parametrize("model,bw,imux,omux", [
    ("cheby2", 36e6, [4.9, 20.4, 35.8, 64.7], [4.0, 16.2, 30.8]),
    ("cheby2", 72e6, [2.4, 9.5, 16.4, 30.9], [1.7, 6.7, 15.1]),
    ("generic", 36e6, [6.8, 28.7, 48.1, 136.5], [2.1, 4.4, 10.8]),
    ("generic", 72e6, [3.6, 15.0, 25.6, 75.4], [1.3, 2.8, 6.8]),
])
def test_t4_parametric_filters(model, bw, imux, omux):
    got = _rel_delay_ns(pl.imux(bw, FS, model), [0.25 * bw, 0.40 * bw, 0.45 * bw, 0.50 * bw])
    assert np.allclose(got, imux, atol=1.0)
    got = _rel_delay_ns(pl.omux(bw, FS, model), [0.25 * bw, 0.40 * bw, 0.50 * bw])
    assert np.allclose(got, omux, atol=1.0)


def test_t4_filter_apply_matches_response():
    """Filtering a tone scales it by the filter's response (checks the FIR and IIR code paths)."""
    n, f0 = 1 << 14, 15e6
    tone = np.exp(2j * np.pi * f0 * np.arange(n) / FS).astype(np.complex64)
    for model in ("etsi", "cheby2"):
        filt = pl.imux(36e6, FS, model)
        y = filt.apply(tone[None, :])[0, 4096:]
        assert abs(20 * np.log10(np.sqrt(np.mean(np.abs(y) ** 2))) - _gain_db(filt, f0)[0]) < 0.02


SALEH = pl.amplifier("saleh")


def test_t5_am_am_am_pm():
    r = np.linspace(1e-3, 2.0, 2000)
    y = SALEH((r * np.exp(1j * 0.7)).astype(np.complex128))
    assert np.max(np.abs(db(np.abs(y) ** 2) - db((2.1587 * r / (1 + 1.1517 * r ** 2)) ** 2))) <= 0.01
    phase = np.degrees(np.angle(y * np.exp(-1j * 0.7)))
    assert np.max(np.abs(phase - np.degrees(4.0033 * r ** 2 / (1 + 9.1040 * r ** 2)))) <= 0.1
    assert abs(r[np.argmax(np.abs(y))] - SALEH.r_sat) < 2e-3 and abs(np.abs(y).max() - 1.0058) < 1e-3


@pytest.mark.parametrize("ibo,obo", [(0, 0.00), (3, 0.51), (6, 1.93), (10, 4.81), (15, 9.25)])
def test_t6_tone_ibo_obo(ibo, obo):
    tone = np.exp(2j * np.pi * 0.01 * np.arange(4096)).astype(np.complex64)
    assert abs(SALEH.obo_db(SALEH(SALEH.drive_gain(1.0, ibo) * tone)) - obo) <= 0.02


# EN 302 307-1 Figure H.3 / H.2 values read off the digitized curves: IBO dB -> (OBO dB, phase deg)
@pytest.mark.parametrize("name,points", [
    ("dvbs2_nl", {0: (0.00, 42.0), 6: (1.43, 21.3), 10: (3.92, 10.5), 20: (13.19, 0.0)}),
    ("dvbs2_lin", {0: (0.00, 12.3), 6: (1.24, 10.4), 10: (4.47, 8.7), 20: (16.91, 1.3)}),
])
def test_t5_table_amplifiers(name, points):
    amp = pl.amplifier(name)
    assert amp.r_sat == 1.0 and amp.a_max == 1.0
    for ibo, (obo, phase) in points.items():
        y = amp(amp.drive_gain(1.0, ibo) * np.ones(4, np.complex128))
        assert abs(amp.obo_db(y) - obo) <= 0.05 and abs(np.degrees(np.angle(y[0])) - phase) <= 0.3
    weak = amp(np.full(4, 1e-4, np.complex128))          # far below the table: linear, no phase shift
    assert abs(np.abs(weak[0]) / 1e-4 - amp.small_signal_gain) < 1e-9 and abs(np.angle(weak[0])) < 1e-3
    assert np.all(np.isfinite(amp(np.array([0.0, 5.0, 50.0], np.complex128))))


def _two_tone_c_im3(ibo):
    n, k1, k2 = 1 << 14, 400, 520
    x = (np.exp(2j * np.pi * k1 * np.arange(n) / n) + np.exp(2j * np.pi * k2 * np.arange(n) / n)) / np.sqrt(2)
    s = np.abs(np.fft.fft(SALEH((SALEH.drive_gain(1.0, ibo) * x).astype(np.complex128)))) ** 2
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


def _gap_c_im(amp_name, ibos):
    amp = pl.amplifier(amp_name)
    plan = [Carrier(-9e6, 6e6, 0.2, "QPSK", 0.5), Carrier(9e6, 6e6, 0.2, "8PSK", 0.5)]
    x = sum(generate_carrier(np.random.default_rng(9), c, 32, 1 << 14, FS) for c in plan)
    out = []
    for ibo in ibos:
        f, p = welch(amp(amp.drive_gain(1.0, ibo) * x).ravel(), fs=FS, nperseg=2048, return_onesided=False,
                     detrend=False)
        out.append(db(p[np.abs(np.abs(f) - 9e6) < 2e6].mean() / p[np.abs(f) < 2e6].mean()))
    return np.array(out)


@pytest.mark.parametrize("amp_name", ["dvbs2_nl", "saleh"])
def test_t9_multicarrier_c_im_monotonic(amp_name):
    assert np.all(np.diff(_gap_c_im(amp_name, (0, 3, 6, 9, 12, 15))) > 0)


def test_t9_linearized_twta_is_cleaner_near_saturation():
    """The linearized tube gives higher C/IM than the non-linearized one at practical back-off.

    Its C/IM is not monotonic in back-off: the figure gives one point per dB with a stepped phase.
    """
    ibos = (0, 3, 6, 9)
    assert np.all(_gap_c_im("dvbs2_lin", ibos) > _gap_c_im("dvbs2_nl", ibos))


@pytest.mark.parametrize("amp_name", ["dvbs2_nl", "saleh"])
@pytest.mark.parametrize("bw", [36e6, 72e6])
def test_t10_aliasing(bw, amp_name):
    amp = pl.amplifier(amp_name)
    plan = random_plan(np.random.default_rng(10), bw)
    rng = np.random.default_rng(11)
    hi = sum(generate_carrier(rng, c, 16, 1 << 15, 2 * FS) for c in plan)   # 576 MHz
    lo = hi[:, ::2]                                                        # same waveform at 288 MHz
    g = amp.drive_gain(1.0, 3.0)

    def band_power(y, fs, nperseg):
        f, p = welch(y, fs=fs, nperseg=nperseg, return_onesided=False, detrend=False, window="boxcar",
                     noverlap=0, axis=-1)
        edges = np.linspace(-bw / 2, bw / 2, 19)
        return np.array([p[:, (f >= a) & (f < b)].mean() for a, b in zip(edges[:-1], edges[1:])])
    d = db(band_power(amp(g * hi), 2 * FS, 4096)) - db(band_power(amp(g * lo), FS, 2048))
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

"""Tests for rfml.signals: constellations, pulse shaping, impairments and frames."""

from __future__ import annotations

import math

import numpy as np
import pytest

from rfml.signals import (
    MODULATIONS,
    Transmitter,
    _add_awgn,
    apply_impairments,
    constellation,
    iq_channels,
    make_frame,
    root_raised_cosine,
)

EXPECTED_SIZES = {
    "BPSK": 2,
    "QPSK": 4,
    "8PSK": 8,
    "16QAM": 16,
    "64QAM": 64,
    "4PAM": 4,
    "16PSK": 16,
    "8PAM": 8,
}


# ---- constellations -------------------------------------------------------


@pytest.mark.parametrize("name", MODULATIONS)
def test_constellation_size(name: str) -> None:
    assert constellation(name).size == EXPECTED_SIZES[name]


@pytest.mark.parametrize("name", MODULATIONS)
def test_constellation_unit_average_power(name: str) -> None:
    # Unit power makes one SNR value mean the same for every modulation.
    pts = constellation(name)
    assert pts.dtype == np.complex128
    assert np.mean(np.abs(pts) ** 2) == pytest.approx(1.0, abs=1e-12)


@pytest.mark.parametrize("name", MODULATIONS)
def test_constellation_points_distinct_and_zero_mean(name: str) -> None:
    # Distinct points: no two symbols collapse. Zero mean: no DC bias from the symbol set.
    pts = constellation(name)
    assert len(np.unique(np.round(pts, 9))) == pts.size
    assert abs(np.mean(pts)) < 1e-12


@pytest.mark.parametrize("name", ["4PAM", "8PAM"])
def test_pam_is_real_valued(name: str) -> None:
    assert np.all(constellation(name).imag == 0.0)


def test_unknown_modulation_is_rejected() -> None:
    with pytest.raises(ValueError):
        constellation("OFDM")


# ---- root-raised-cosine pulse --------------------------------------------


@pytest.mark.parametrize("rolloff", [0.0, 0.22, 0.35, 0.5, 1.0])
def test_rrc_unit_energy_and_symmetric(rolloff: float) -> None:
    h = root_raised_cosine(sps=8, rolloff=rolloff, span=6)
    assert h.size == 6 * 8 + 1
    assert h.dtype == np.float64
    assert np.sum(h**2) == pytest.approx(1.0, abs=1e-12)
    np.testing.assert_allclose(h, h[::-1], atol=1e-12)


@pytest.mark.parametrize("rolloff", [0.35, 0.5, 1.0])
def test_rrc_matched_filter_is_isi_free_at_symbol_spacing(rolloff: float) -> None:
    # TX RRC convolved with the matched RX RRC is a raised cosine. Its zero crossings
    # at multiples of the symbol period mean no ISI at the sampling instants.
    # Span 6 truncation leaks ~1e-3 relative ISI at beta=0.35, so the 2e-2 tolerance
    # is loose but meaningful. Small rolloffs (near sinc) leak more and are not used here.
    sps = 8
    h = root_raised_cosine(sps=sps, rolloff=rolloff, span=6)
    combined = np.convolve(h, h, mode="full")
    centre = h.size - 1
    peak = combined[centre]
    assert peak == pytest.approx(1.0, abs=1e-12)  # unit energy: matched peak is 1
    for k in range(-3, 4):
        if k == 0:
            continue
        assert abs(combined[centre + k * sps]) < 2e-2 * peak


def test_rrc_singularity_is_finite_and_continuous() -> None:
    # At beta=0.25 and sps=8 the sample t=1 symbol hits |4*beta*t| = 1 (0/0 in the
    # closed form). Compare with beta nudged slightly: a wrong special-case value
    # would show up as an O(1e-2) jump.
    h_exact = root_raised_cosine(sps=8, rolloff=0.25, span=6)
    h_nudged = root_raised_cosine(sps=8, rolloff=0.25 + 1e-7, span=6)
    assert np.all(np.isfinite(h_exact))
    assert np.max(np.abs(h_exact - h_nudged)) < 1e-5


def test_rrc_rejects_invalid_arguments() -> None:
    with pytest.raises(ValueError):
        root_raised_cosine(sps=8, rolloff=1.5, span=6)
    with pytest.raises(ValueError):
        root_raised_cosine(sps=0, rolloff=0.35, span=6)


# ---- transmitter draws ----------------------------------------------------


def test_ideal_transmitter_has_no_impairments() -> None:
    tx = Transmitter.random("QPSK", np.random.default_rng(0), impaired=False)
    assert tx.modulation == "QPSK"
    assert tx.iq_gain == 1.0
    assert tx.iq_phase_deg == 0.0
    assert tx.dc_offset == 0j
    assert tx.phase_noise_std == 0.0
    assert math.isinf(tx.pa_saturation)


def test_impaired_transmitter_values_stay_in_documented_ranges() -> None:
    rng = np.random.default_rng(1)
    txs = [Transmitter.random("8PSK", rng, impaired=True) for _ in range(500)]
    gains = np.array([t.iq_gain for t in txs])
    phases = np.array([t.iq_phase_deg for t in txs])
    dc_re = np.array([t.dc_offset.real for t in txs])
    dc_im = np.array([t.dc_offset.imag for t in txs])
    stds = np.array([t.phase_noise_std for t in txs])
    sats = np.array([t.pa_saturation for t in txs])
    smooth = np.array([t.pa_smoothness for t in txs])

    assert gains.min() >= 0.9 and gains.max() <= 1.1
    assert phases.min() >= -5.0 and phases.max() <= 5.0
    assert np.abs(dc_re).max() <= 0.05 and np.abs(dc_im).max() <= 0.05
    assert stds.min() >= 2e-3 and stds.max() <= 1e-2
    assert sats.min() >= 1.0 and sats.max() <= 1.6
    assert smooth.min() >= 2.0 and smooth.max() <= 3.0
    # Draws must actually vary, otherwise the fingerprint would carry no information.
    assert gains.std() > 0.02 and phases.std() > 1.0 and sats.std() > 0.05
    # Log-uniform phase noise: mean of log(std) sits at the midpoint of the log range.
    mid = 0.5 * (np.log(2e-3) + np.log(1e-2))
    assert abs(np.mean(np.log(stds)) - mid) < 0.1


# ---- impairments ----------------------------------------------------------


def test_apply_impairments_identity_for_ideal_device() -> None:
    rng = np.random.default_rng(2)
    x = rng.standard_normal(256) + 1j * rng.standard_normal(256)
    y = apply_impairments(x, Transmitter("QPSK"), rng)
    np.testing.assert_allclose(y, x, rtol=0, atol=0)


def test_dc_offset_is_added_exactly() -> None:
    rng = np.random.default_rng(3)
    x = rng.standard_normal(64) + 1j * rng.standard_normal(64)
    tx = Transmitter("QPSK", dc_offset=0.1 + 0.2j)
    y = apply_impairments(x, tx, rng)
    np.testing.assert_allclose(y - x, 0.1 + 0.2j, atol=1e-12)


@pytest.mark.parametrize(
    "gain,phase_deg,expected_ratio",
    [
        # Pure quadrature skew (g=1): |nu|/|mu| = tan(phi/2), 10 deg -> tan(5 deg).
        (1.0, 10.0, math.tan(math.radians(5.0))),
        # Pure gain error (phi=0): |nu|/|mu| = |1-g|/|1+g|, g=1.1 -> 0.1/2.1.
        (1.1, 0.0, 0.1 / 2.1),
    ],
)
def test_iq_imbalance_image_ratio_matches_closed_form(
    gain: float, phase_deg: float, expected_ratio: float
) -> None:
    # A tone at +f through y = mu*x + nu*conj(x) also produces an image at -f with
    # amplitude |nu|. The image-to-signal ratio |nu|/|mu| is the physical quantity
    # that the spectrum shows, so this checks the formula's effect, not its text.
    n = 1000
    cycles = 100  # exactly on FFT bin 100, so there is no leakage
    x = np.exp(2j * np.pi * cycles * np.arange(n) / n)
    tx = Transmitter("QPSK", iq_gain=gain, iq_phase_deg=phase_deg)
    y = apply_impairments(x, tx, np.random.default_rng(0))
    spec = np.fft.fft(y)
    ratio = abs(spec[n - cycles]) / abs(spec[cycles])
    assert ratio == pytest.approx(expected_ratio, rel=1e-9)


def test_rapp_pa_never_increases_amplitude_and_saturates() -> None:
    sat = 1.2
    tx = Transmitter("16QAM", pa_saturation=sat, pa_smoothness=2.5)
    r = np.logspace(-3, 2, 400)
    x = r * np.exp(0.3j)
    y = apply_impairments(x, tx, np.random.default_rng(0))
    amp_in = np.abs(x)
    amp_out = np.abs(y)
    # Never amplifies: |y| <= |x| for every sample.
    assert np.all(amp_out <= amp_in * (1 + 1e-12))
    # Monotone AM/AM: a larger input never gives a smaller output.
    assert np.all(np.diff(amp_out) >= -1e-15)
    # Bounded by saturation for every input, and close to it for very large inputs.
    assert np.all(amp_out < sat)
    assert amp_out[-1] == pytest.approx(sat, rel=1e-3)
    # Phase is untouched (no AM/PM): the Rapp model is pure AM/AM.
    np.testing.assert_allclose(np.angle(y), np.angle(x), atol=1e-12)


def test_rapp_pa_is_linear_for_small_signals() -> None:
    tx = Transmitter("QPSK", pa_saturation=1.0, pa_smoothness=2.0)
    x = np.array([1e-3 + 2e-3j, -4e-4 + 1e-4j])
    y = apply_impairments(x, tx, np.random.default_rng(0))
    np.testing.assert_allclose(y, x, rtol=1e-7)


def test_phase_noise_keeps_amplitude_and_random_walk_variance() -> None:
    # Phase noise rotates samples and leaves amplitude alone. Its phase is a random walk,
    # so Var[phase_n] = (n+1) * sigma^2. We check this across independent realisations.
    sigma = 0.01
    n = 500
    n_real = 4000
    tx = Transmitter("QPSK", phase_noise_std=sigma)
    rng = np.random.default_rng(4)
    x = np.ones(n, dtype=np.complex128)
    final_phase = np.empty(n_real)
    for i in range(n_real):
        y = apply_impairments(x, tx, rng)
        np.testing.assert_allclose(np.abs(y), 1.0, rtol=1e-12)
        final_phase[i] = np.angle(y[-1])
    expected_var = n * sigma**2  # 0.05
    assert np.var(final_phase) == pytest.approx(expected_var, rel=0.1)


# ---- noise and frames -----------------------------------------------------


def test_awgn_power_matches_snr() -> None:
    # Noise power must be P/10^(snr/10). At 10 dB this is P/10, measured over many
    # samples so sampling error is well under the 10% tolerance.
    rng = np.random.default_rng(5)
    x = constellation("QPSK")[rng.integers(0, 4, size=200_000)]
    p_sig = np.mean(np.abs(x) ** 2)
    noisy = _add_awgn(x, snr_db=10.0, rng=rng)
    noise = noisy - x
    p_noise = np.mean(np.abs(noise) ** 2)
    assert p_noise == pytest.approx(p_sig / 10.0, rel=0.1)


def test_awgn_is_circular() -> None:
    # Real and imaginary noise each carry half the variance, so they are equal in power.
    rng = np.random.default_rng(6)
    x = np.zeros(100_000, dtype=np.complex128) + 1.0
    noise = _add_awgn(x, snr_db=0.0, rng=rng) - x
    p_re = np.var(noise.real)
    p_im = np.var(noise.imag)
    assert p_re == pytest.approx(p_im, rel=0.05)
    assert p_re + p_im == pytest.approx(1.0, rel=0.05)  # total noise power = P at 0 dB


def test_make_frame_length_and_dtype() -> None:
    tx = Transmitter("16QAM")
    frame = make_frame(tx, 512, snr_db=10.0, rng=np.random.default_rng(7))
    assert frame.shape == (512,)
    assert frame.dtype == np.complex128


def test_make_frame_unit_power_at_high_snr() -> None:
    # With an ideal device and SNR 60 dB, noise is negligible. Each frame is
    # normalised to unit power before CFO, which does not change power.
    rng = np.random.default_rng(8)
    tx = Transmitter("8PSK")
    for _ in range(5):
        frame = make_frame(tx, 2048, snr_db=60.0, rng=rng)
        assert np.mean(np.abs(frame) ** 2) == pytest.approx(1.0, rel=0.05)


def test_make_frame_is_reproducible_with_same_seed() -> None:
    tx = Transmitter.random("QPSK", np.random.default_rng(9))
    a = make_frame(tx, 256, 5.0, np.random.default_rng(10))
    b = make_frame(tx, 256, 5.0, np.random.default_rng(10))
    np.testing.assert_array_equal(a, b)


def test_make_frame_rejects_empty_request() -> None:
    with pytest.raises(ValueError):
        make_frame(Transmitter("BPSK"), 0, 10.0, np.random.default_rng(0))


def test_iq_channels_layout() -> None:
    x = np.array([1 + 2j, -3 + 4j, 0.5 - 0.5j])
    out = iq_channels(x)
    assert out.shape == (2, 3)
    assert out.dtype == np.float32
    np.testing.assert_array_equal(out[0], np.array([1.0, -3.0, 0.5], dtype=np.float32))
    np.testing.assert_array_equal(out[1], np.array([2.0, 4.0, -0.5], dtype=np.float32))

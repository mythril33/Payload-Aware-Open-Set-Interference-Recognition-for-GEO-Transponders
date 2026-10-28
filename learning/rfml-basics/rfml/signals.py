"""Baseband signal model: constellations, pulse shaping, hardware impairments, frames.

Everything here is simulation. The impairments (Rapp PA, IQ imbalance, phase noise,
DC offset) are per-transmitter hardware fingerprints. Because they belong to the
transmitter, dataset.py keeps every frame of one transmitter in one split.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

MODULATIONS = ("BPSK", "QPSK", "8PSK", "16QAM", "64QAM", "4PAM", "16PSK", "8PAM")
KNOWN_MODULATIONS = ("BPSK", "QPSK", "8PSK", "16QAM")  # training classes
UNKNOWN_MODULATIONS = ("64QAM", "4PAM")  # held-out test-only unknowns
AUX_OUTLIER_MODULATIONS = ("16PSK", "8PAM")  # train-only outlier pool (Objectosphere)


def _pam_levels(n_levels: int) -> np.ndarray:
    """Symmetric odd-integer levels, e.g. 4 -> [-3, -1, 1, 3]."""
    return 2.0 * np.arange(n_levels) - (n_levels - 1)


def constellation(name: str) -> np.ndarray:
    """Return the complex points of a modulation, scaled to unit average power.

    Unit power makes SNR the only power scale in the chain, so one SNR value means
    the same thing for every modulation. Labels are not Gray-coded: symbols are
    drawn uniformly and no bit-error metric is computed, so label order is irrelevant.
    """
    if name == "BPSK":
        pts = np.array([-1.0, 1.0], dtype=np.complex128)
    elif name == "QPSK":
        pts = np.array([1 + 1j, -1 + 1j, -1 - 1j, 1 - 1j], dtype=np.complex128)
    elif name in ("8PSK", "16PSK"):
        m = 8 if name == "8PSK" else 16
        k = np.arange(m)
        # The +pi/M offset keeps points off the axes; it has no effect on power.
        pts = np.exp(1j * (2.0 * np.pi * k / m + np.pi / m))
    elif name in ("16QAM", "64QAM"):
        side = 4 if name == "16QAM" else 8
        levels = _pam_levels(side)
        re, im = np.meshgrid(levels, levels, indexing="ij")
        pts = (re + 1j * im).ravel().astype(np.complex128)
    elif name in ("4PAM", "8PAM"):
        levels = _pam_levels(4 if name == "4PAM" else 8)
        pts = levels.astype(np.complex128)  # real-valued: imaginary part is exactly 0
    else:
        raise ValueError(f"unknown modulation {name!r}; expected one of {MODULATIONS}")
    return pts / np.sqrt(np.mean(np.abs(pts) ** 2))


def root_raised_cosine(sps: int, rolloff: float, span: int) -> np.ndarray:
    """Unit-energy root-raised-cosine pulse, length span*sps+1, symmetric about the middle of its length.

    A sample sits on the centre only when span*sps is even; for odd span*sps the two central
    taps are equal and the peak falls half a sample off the array centre.

    The RRC pair (TX pulse, matched RX filter) gives zero inter-symbol interference
    at symbol spacing: the cascade is a raised cosine with zero crossings at k*T.
    Truncating to `span` symbols leaks a little ISI; the leak grows as rolloff shrinks.
    """
    if sps < 1 or span < 1:
        raise ValueError("sps and span must be >= 1")
    if not 0.0 <= rolloff <= 1.0:
        raise ValueError("rolloff must lie in [0, 1]")
    n_taps = span * sps + 1
    t = (np.arange(n_taps) - (n_taps - 1) / 2.0) / sps  # time in symbol periods
    beta = float(rolloff)

    t_zero = np.abs(t) < 1e-12
    # The closed form has a removable 0/0 at |4*beta*t| = 1; use its limit there.
    if beta > 0.0:
        t_sing = np.abs(np.abs(4.0 * beta * t) - 1.0) < 1e-9
    else:
        t_sing = np.zeros(n_taps, dtype=bool)
    general = ~(t_zero | t_sing)

    h = np.empty(n_taps, dtype=np.float64)
    tg = t[general]
    h[general] = (np.sin(np.pi * tg * (1.0 - beta)) + 4.0 * beta * tg * np.cos(np.pi * tg * (1.0 + beta))) / (
        np.pi * tg * (1.0 - (4.0 * beta * tg) ** 2)
    )
    h[t_zero] = 1.0 - beta + 4.0 * beta / np.pi
    if np.any(t_sing):
        h[t_sing] = (
            beta
            / np.sqrt(2.0)
            * (
                (1.0 + 2.0 / np.pi) * np.sin(np.pi / (4.0 * beta))
                + (1.0 - 2.0 / np.pi) * np.cos(np.pi / (4.0 * beta))
            )
        )
    return h / np.sqrt(np.sum(h**2))


@dataclass(frozen=True)
class Transmitter:
    """One physical transmitter: a modulation plus its hardware impairments.

    Defaults are the ideal device. All fields are simulator truth, never model inputs.
    """

    modulation: str
    iq_gain: float = 1.0  # Q-branch gain relative to I-branch
    iq_phase_deg: float = 0.0  # quadrature skew between I and Q, degrees
    dc_offset: complex = 0j  # carrier leakage / DC bias
    phase_noise_std: float = 0.0  # rad std of each per-sample phase increment
    pa_saturation: float = math.inf  # Rapp saturation amplitude (relative to unit RMS input)
    pa_smoothness: float = 2.0  # Rapp knee sharpness p

    @classmethod
    def random(cls, modulation: str, rng: np.random.Generator, impaired: bool = True) -> "Transmitter":
        """Draw one device. impaired=False returns the ideal device with no randomness."""
        if not impaired:
            return cls(modulation=modulation)
        gain = rng.uniform(0.9, 1.1)
        phase_deg = rng.uniform(-5.0, 5.0)
        dc = complex(rng.uniform(-0.05, 0.05), rng.uniform(-0.05, 0.05))
        # Log-uniform: oscillator quality spans a decade, and a linear draw would
        # under-sample the strong-noise devices.
        phase_std = float(np.exp(rng.uniform(np.log(2e-3), np.log(1e-2))))
        saturation = rng.uniform(1.0, 1.6)
        smoothness = rng.uniform(2.0, 3.0)
        return cls(
            modulation=modulation,
            iq_gain=float(gain),
            iq_phase_deg=float(phase_deg),
            dc_offset=dc,
            phase_noise_std=phase_std,
            pa_saturation=float(saturation),
            pa_smoothness=float(smoothness),
        )


def apply_impairments(x: np.ndarray, tx: Transmitter, rng: np.random.Generator) -> np.ndarray:
    """Apply PA compression, IQ imbalance, phase noise and DC offset, in that order.

    Each stage is the identity when its parameter is ideal, so an ideal Transmitter
    returns the input unchanged.
    """
    y = np.asarray(x, dtype=np.complex128)

    # (1) Rapp AM/AM model of a solid-state PA: amplitude is compressed toward the
    # saturation level A. Phase is untouched (no AM/PM here). Output amplitude is
    # always below A and never exceeds |x|.
    p = tx.pa_smoothness
    ratio = (np.abs(y) / tx.pa_saturation) ** (2.0 * p)
    y = y / (1.0 + ratio) ** (1.0 / (2.0 * p))

    # (2) IQ imbalance: y = mu*x + nu*conj(x). The conj(x) term is the image that
    # appears at the mirror frequency. Its size relative to mu sets the image rejection.
    g = tx.iq_gain
    phi = np.deg2rad(tx.iq_phase_deg)
    mu = (1.0 + g * np.exp(-1j * phi)) / 2.0
    nu = (1.0 - g * np.exp(1j * phi)) / 2.0
    y = mu * y + nu * np.conj(y)

    # (3) Phase noise: a random walk (sum of i.i.d. increments), so the phase variance
    # grows linearly with time, as for a free-running oscillator. Amplitude is unchanged.
    increments = rng.normal(0.0, tx.phase_noise_std, size=y.shape[-1])
    y = y * np.exp(1j * np.cumsum(increments))

    # (4) DC offset: a per-device complex bias (carrier leakage). It is added before the
    # frame CFO, so make_frame rotates it; its frame-mean is not a fixed device value.
    return y + tx.dc_offset


def _add_awgn(x: np.ndarray, snr_db: float, rng: np.random.Generator) -> np.ndarray:
    """Add complex AWGN so that mean|x|^2 / mean|noise|^2 = 10^(snr_db/10).

    SNR is defined on the signal it receives (impaired, CFO-shifted), so the noise
    power is computed from the input's own power. Each of I and Q gets half the
    variance, which makes the noise circular.
    """
    x = np.asarray(x, dtype=np.complex128)
    p_signal = float(np.mean(np.abs(x) ** 2))
    p_noise = p_signal / 10.0 ** (snr_db / 10.0)
    sigma = np.sqrt(p_noise / 2.0)
    noise = sigma * (rng.standard_normal(x.shape) + 1j * rng.standard_normal(x.shape))
    return x + noise


def make_frame(
    tx: Transmitter,
    n_samples: int,
    snr_db: float,
    rng: np.random.Generator,
    sps: int = 8,
    rolloff: float = 0.35,
    span: int = 6,
    max_cfo: float = 0.01,
) -> np.ndarray:
    """Generate one complex baseband frame of n_samples from transmitter `tx`.

    The window is taken from the steady-state region of the pulse-shaped stream, where
    every output sample is built from real symbols. This avoids the filter start-up and
    tail transients, which would otherwise look like a class-independent edge artefact.
    """
    if n_samples < 1:
        raise ValueError("n_samples must be >= 1")
    pulse = root_raised_cosine(sps, rolloff, span)
    pulse_len = pulse.size  # span*sps + 1

    # Enough symbols that the steady region holds n_samples plus one symbol of slack.
    # The slack gives a random start offset that covers every symbol-timing phase.
    n_sym = span + int(np.ceil(n_samples / sps)) + 1
    const = constellation(tx.modulation)
    symbols = const[rng.integers(0, const.size, size=n_sym)]
    upsampled = np.zeros(n_sym * sps, dtype=np.complex128)
    upsampled[::sps] = symbols
    stream = np.convolve(upsampled, pulse, mode="full")

    # stream[k] uses only real symbols for k in [pulse_len-1, n_sym*sps-1]. The length
    # of that region is steady = (n_sym - span) * sps.
    steady = (n_sym - span) * sps
    start = (pulse_len - 1) + int(rng.integers(0, steady - n_samples + 1))
    x = stream[start : start + n_samples]
    x = x / np.sqrt(np.mean(np.abs(x) ** 2))  # step 2: unit average power

    x = apply_impairments(x, tx, rng)  # step 3

    # Step 4: CFO and random initial phase. |exp| = 1, so power is unchanged.
    f = rng.uniform(-max_cfo, max_cfo)  # cycles per sample
    phi0 = rng.uniform(0.0, 2.0 * np.pi)
    x = x * np.exp(1j * (2.0 * np.pi * f * np.arange(n_samples) + phi0))

    return _add_awgn(x, snr_db, rng)  # step 5


def iq_channels(x: np.ndarray) -> np.ndarray:
    """Split complex samples into a float32 array of shape (2, n): row 0 I, row 1 Q."""
    x = np.asarray(x, dtype=np.complex128)
    return np.stack([x.real, x.imag]).astype(np.float32)

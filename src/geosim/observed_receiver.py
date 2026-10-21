"""Observation-only, decision-directed linear carrier cancellation.

The receiver uses declared frequency/rate/roll-off/modulation information, but
never transmitter symbols, carrier powers, seeds, timing or payload truth.
Matched-filter timing/phase recovery and constellation decisions produce a new
SRRC waveform. A short linear FIR is fitted in the received domain, then that
waveform is subtracted. This is not a notch filter applied to the observation.

Independent finite snapshots have unknown boundary symbols. Edge guards and a
planned-band constraint on the *synthesized estimate* limit their contribution.
This baseline does not invert nonlinear payload distortion, decode DVB frames,
or track arbitrary clock/carrier offsets. Lock diagnostics are estimates, not
proof that a physical carrier exists or that overlapping interference survives.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from numbers import Integral, Real
from pathlib import Path

import numpy as np

from . import FS_MON
from .waveform import constellation, srrc_response

ALGORITHM = "observed-dd-rrc-fir/1"


def _real(value, name, lower=None, upper=None):
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real):
        raise ValueError(f"{name} must be a finite real number")
    try:
        value = float(value)
    except OverflowError as error:
        raise ValueError(f"{name} must be finite") from error
    if not np.isfinite(value) or (lower is not None and value < lower) or (upper is not None and value > upper):
        raise ValueError(f"{name} is outside its finite supported range")
    return value


def _integer(value, name, lower, upper):
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Integral) or not lower <= value <= upper:
        raise ValueError(f"{name} must be an integer in [{lower}, {upper}]")
    return int(value)


@dataclass(frozen=True)
class ReceiverCarrier:
    f0: float
    symbol_rate: float
    alpha: float
    mod: str
    code_rate: str | None = None

    def __post_init__(self):
        for key in ("f0", "symbol_rate", "alpha"):
            object.__setattr__(self, key, _real(getattr(self, key), key))
        if not 0 < self.symbol_rate <= FS_MON / 2 or not 0 < self.alpha <= 1:
            raise ValueError("receiver rate and roll-off must be positive and supported")
        if abs(self.f0) + self.occupied_bw / 2 >= FS_MON / 2:
            raise ValueError("the complete receiver carrier must fit below Nyquist")
        if not isinstance(self.mod, str) or (self.code_rate is not None and not isinstance(self.code_rate, str)):
            raise ValueError("modulation/code_rate must be declared strings")
        try:
            constellation(self.mod, self.code_rate)
        except (KeyError, ValueError) as error:
            raise ValueError("unsupported receiver constellation") from error

    @property
    def occupied_bw(self):
        return self.symbol_rate * (1 + self.alpha)


@dataclass(frozen=True)
class CancellationConfig:
    timing_steps: int = 12
    timing_refinements: int = 2
    timing_windows: int = 4
    phase_steps: int = 32
    pulse_span_symbols: int = 8
    guard_symbols: int = 4
    fir_taps: int = 5
    ridge: float = 0.001
    min_snr_db: float = 3.0
    max_decision_error: float = 0.15
    min_timing_contrast: float = 0.04
    min_relative_power: float = 1e-6
    max_symbol_tone_fraction: float = 0.5

    def __post_init__(self):
        limits = {"timing_steps": (4, 64), "timing_refinements": (0, 3), "timing_windows": (1, 32),
                  "phase_steps": (8, 128), "pulse_span_symbols": (3, 16), "guard_symbols": (2, 16),
                  "fir_taps": (1, 9)}
        for name, (lower, upper) in limits.items():
            object.__setattr__(self, name, _integer(getattr(self, name), name, lower, upper))
        if self.fir_taps % 2 != 1:
            raise ValueError("fir_taps must be odd")
        for name, lower, upper in (("ridge", 1e-8, 1.), ("min_snr_db", -20., 60.),
                                   ("max_decision_error", 1e-6, 1.), ("min_timing_contrast", 0., 1.),
                                   ("min_relative_power", 0., 1.), ("max_symbol_tone_fraction", 0., 1.)):
            object.__setattr__(self, name, _real(getattr(self, name), name, lower, upper))

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_file(cls, path):
        def reject(value):
            raise ValueError(f"nonfinite JSON constant {value}")
        raw = json.loads(Path(path).read_text(), parse_constant=reject)
        if not isinstance(raw, dict):
            raise ValueError("cancellation config must be a JSON object")
        try:
            return cls(**raw)
        except TypeError as error:
            raise ValueError(f"invalid cancellation configuration: {error}") from error


@dataclass(frozen=True)
class CancellationResult:
    residual_iq: np.ndarray
    reconstruction: np.ndarray
    meta: dict


def _rings(points):
    radii = np.abs(points)
    groups = []
    for radius in np.unique(np.round(radii, 12)):
        indices = np.flatnonzero(np.isclose(radii, radius, rtol=0, atol=1e-10))
        phase0 = float(np.angle(points[indices[0]]))
        groups.append((float(radii[indices[0]]), len(indices), phase0))
    return groups


def _slice(values, rings):
    amplitude, angle = np.abs(values), np.angle(values)
    best, output = np.full(values.shape, np.inf), np.zeros(values.shape, np.complex128)
    for radius, count, phase0 in rings:
        phase = phase0 + 2 * np.pi / count * np.rint((angle - phase0) * count / (2 * np.pi))
        error = amplitude**2 + radius**2 - 2 * amplitude * radius * np.cos(angle - phase)
        selected = error < best
        best = np.where(selected, error, best)
        output = np.where(selected, radius * np.exp(1j * phase), output)
    return output


def _lock(samples, rings, symmetry, phase_steps):
    """Blind phase search followed by two complex-gain/decision refinements."""
    scale = np.sqrt(np.mean(np.abs(samples)**2, axis=1, keepdims=True))
    normalized = samples / np.maximum(scale, np.finfo(float).tiny)
    amplitude, angle = np.abs(normalized), np.angle(normalized)
    best_cost = np.full(len(samples), np.inf)
    best_phase = np.zeros(len(samples))
    for phase in np.arange(phase_steps) * (2 * np.pi / symmetry / phase_steps):
        shifted = angle - phase
        errors = np.full(samples.shape, np.inf)
        for radius, count, phase0 in rings:
            deviation = (shifted - phase0 + np.pi / count) % (2 * np.pi / count) - np.pi / count
            errors = np.minimum(errors, amplitude**2 + radius**2 - 2 * amplitude * radius * np.cos(deviation))
        cost = errors.mean(axis=1)
        choose = cost < best_cost
        best_cost = np.where(choose, cost, best_cost)
        best_phase = np.where(choose, phase, best_phase)
    gain = scale[:, 0] * np.exp(1j * best_phase)
    decisions = _slice(samples / np.maximum(np.abs(gain), np.finfo(float).tiny)[:, None]
                        * np.exp(-1j * np.angle(gain))[:, None], rings)
    for _ in range(2):
        gain = np.sum(samples * decisions.conj(), axis=1) / np.maximum(np.sum(np.abs(decisions)**2, axis=1), 1e-30)
        safe = np.where(np.abs(gain) > 1e-30, gain, 1.)
        decisions = _slice(samples / safe[:, None], rings)
    error = np.mean(np.abs(samples - gain[:, None] * decisions)**2, axis=1)
    error /= np.maximum(np.mean(np.abs(samples)**2, axis=1), 1e-30)
    return decisions, gain, error


def _interpolate(values, positions):
    """Four-point Lagrange samples, with callers excluding window edges."""
    index = np.floor(positions).astype(int)
    frac = positions - index
    weights = (-frac * (frac - 1) * (frac - 2) / 6,
               (frac + 1) * (frac - 1) * (frac - 2) / 2,
               -(frac + 1) * frac * (frac - 2) / 2,
               (frac + 1) * frac * (frac - 1) / 6)
    return sum(values[:, index + offset] * weight for offset, weight in zip((-1, 0, 1, 2), weights))


def _timing(matched, sps, rings, symmetry, cfg):
    n = matched.shape[1]
    guard = max(3., cfg.guard_symbols * sps)
    if n <= 2 * guard + 8 * sps:
        return None
    core_k = np.arange(int(np.ceil(guard / sps)), int(np.floor((n - guard - sps) / sps)))
    probe = matched[:cfg.timing_windows]
    candidates = np.arange(cfg.timing_steps) * sps / cfg.timing_steps
    costs = []
    for tau in candidates:
        _, _, error = _lock(_interpolate(probe, tau + core_k * sps), rings, symmetry, cfg.phase_steps)
        costs.append(float(np.mean(error)))
    best_index = int(np.argmin(costs))
    tau, best = float(candidates[best_index]), costs[best_index]
    contrast = max(0., (float(np.median(costs)) - best) / max(float(np.median(costs)), 1e-30))
    spacing = sps / cfg.timing_steps
    for _ in range(cfg.timing_refinements):
        candidates = tau + np.arange(-2, 3) * spacing / 4
        refined = []
        for candidate in candidates:
            _, _, error = _lock(_interpolate(probe, candidate + core_k * sps), rings, symmetry, cfg.phase_steps)
            refined.append(float(np.mean(error)))
        selected = int(np.argmin(refined))
        if refined[selected] < best:
            tau, best = float(candidates[selected]), refined[selected]
        spacing /= 4
    return tau, contrast


def _rrc_time(t, alpha):
    t = np.asarray(t, dtype=float)
    zero = np.abs(t) < 1e-10
    singular = np.abs(np.abs(t) - 1 / (4 * alpha)) < 1e-8
    safe = np.where(zero | singular, 0.123456789, t)
    output = (np.sin(np.pi * (1 - alpha) * safe) + 4 * alpha * safe * np.cos(np.pi * (1 + alpha) * safe))
    output /= np.pi * safe * (1 - (4 * alpha * safe)**2)
    output = np.where(zero, 1 + alpha * (4 / np.pi - 1), output)
    limit = alpha / np.sqrt(2) * ((1 + 2 / np.pi) * np.sin(np.pi / (4 * alpha))
                                + (1 - 2 / np.pi) * np.cos(np.pi / (4 * alpha)))
    return np.where(singular, limit, output)


def _remodulate(decisions, symbol_indices, tau, sps, n, alpha, span):
    positions = (np.arange(n) - tau) / sps
    left = np.floor(positions).astype(int)
    start = int(symbol_indices[0])
    output = np.zeros((len(decisions), n), np.complex128)
    for offset in range(-span, span + 1):
        index = left + offset
        valid = (index >= start) & (index < start + decisions.shape[1])
        clipped = np.clip(index - start, 0, decisions.shape[1] - 1)
        pulse = _rrc_time(positions - index, alpha) * valid
        output += decisions[:, clipped] * pulse
    return output


def _received_fit(reference, target, support, guard, cfg):
    """Ridge FIR on a remodulated reference, never observation-band removal."""
    n = reference.shape[1]
    taper = np.ones(n)
    edge = min(int(np.ceil(guard)), n // 4)
    if edge:
        taper[:edge] = np.sin(np.linspace(0, np.pi / 2, edge))**2
        taper[-edge:] = taper[:edge][::-1]
    reference *= taper
    # The synthesized carrier is physically restricted to its declared band.
    reference = np.fft.ifft(np.fft.fft(reference, axis=1) * support, axis=1)
    half = cfg.fir_taps // 2
    design = np.stack([np.roll(reference, shift, axis=1) for shift in range(-half, half + 1)], axis=2)
    gram = np.einsum("tnk,tnl->tkl", design.conj(), design, optimize=True)
    rhs = np.einsum("tnk,tn->tk", design.conj(), target, optimize=True)
    ridge = cfg.ridge * np.real(np.trace(gram, axis1=1, axis2=2)) / cfg.fir_taps
    gram += np.maximum(ridge, 1e-30)[:, None, None] * np.eye(cfg.fir_taps)
    coefficients = np.linalg.solve(gram, rhs[..., None])[..., 0]
    return np.einsum("tnk,tk->tn", design, coefficients, optimize=True)


def cancel_observed(iq: np.ndarray, carriers: list[ReceiverCarrier],
                    config: CancellationConfig | None = None) -> CancellationResult:
    """Cancel declared carriers from finite calibrated monitor windows.

    Timing is shared across windows and inferred from the first timing_windows;
    phase/gain and symbol decisions are estimated separately in every window.
    The monitor rate is fixed at 96 MHz. Empty plans return exact input copies.
    """
    config = CancellationConfig() if config is None else config
    if not isinstance(config, CancellationConfig):
        raise ValueError("config must be a CancellationConfig")
    observed = np.asarray(iq)
    if (observed.ndim != 2 or not observed.size or observed.shape[1] < 64 or observed.dtype.kind != "c"
            or not np.isfinite(observed).all()):
        raise ValueError("iq must be a finite nonempty complex [windows,samples>=64] array")
    if (not isinstance(carriers, (list, tuple)) or len(carriers) > 32
            or any(not isinstance(carrier, ReceiverCarrier) for carrier in carriers)):
        raise ValueError("carriers must be ReceiverCarrier descriptors, without simulator truth")
    bands = sorted((c.f0 - c.occupied_bw / 2, c.f0 + c.occupied_bw / 2) for c in carriers)
    if any(right > next_left for (_, right), (next_left, _) in zip(bands, bands[1:])):
        raise ValueError("overlapping operator carrier bands are not supported")
    with np.errstate(over="ignore", invalid="ignore"):
        values = observed.astype(np.complex128)
    n = values.shape[1]
    if (not np.isfinite(values).all()
            or np.max(np.abs(values)) > np.sqrt(np.finfo(float).max) / (4 * n)):
        raise ValueError("iq exceeds the receiver's supported finite numeric range")
    times = np.arange(n) / FS_MON
    frequencies = np.fft.fftfreq(n, 1 / FS_MON)
    transform = np.fft.fft(values, axis=1)
    power = np.abs(transform)**2 / n**2
    outside = np.ones(n, bool)
    for carrier in carriers:
        outside &= np.abs(frequencies - carrier.f0) > carrier.occupied_bw / 2 + FS_MON / n * 2
    noise_bin = (np.median(power[:, outside], axis=1) / np.log(2) if outside.any()
                 else np.mean(power, axis=1))
    global_power = np.mean(np.abs(values)**2, axis=1)
    total = np.zeros(values.shape, np.complex128)
    diagnostics = []
    for carrier in carriers:
        band = np.abs(frequencies - carrier.f0) <= carrier.occupied_bw / 2
        band_power = power[:, band].sum(axis=1)
        noise_power = noise_bin * int(band.sum())
        signal_power = np.maximum(band_power - noise_power, 0)
        # A finite large signal divided by the noise floor can overflow even
        # though its SNR in dB is representable. Keep the diagnostic finite.
        snr = np.full(signal_power.shape, -300.)
        positive = signal_power > 0
        snr[positive] = np.maximum(10 * (np.log10(signal_power[positive])
                                       - np.log10(np.maximum(noise_power[positive], 1e-30))), -300.)
        strong = (snr >= config.min_snr_db) & (band_power > config.min_relative_power * global_power) & (band_power > 1e-30)
        info = {"descriptor": asdict(carrier), "accepted_windows": 0, "n_windows": len(values),
                "estimated_snr_db": [float(v) for v in snr], "timing_samples": None,
                "timing_contrast": None, "decision_error": None, "symbol_tone_fraction": None,
                "status": "below_observed_presence_threshold"}
        if not strong.any():
            diagnostics.append(info)
            continue
        rotation = np.exp(-2j * np.pi * carrier.f0 * times)
        baseband = values * rotation
        base_transform = np.fft.fft(baseband, axis=1)
        support = np.abs(frequencies) <= carrier.occupied_bw / 2
        target = np.fft.ifft(base_transform * support, axis=1)
        matched = np.fft.ifft(base_transform * srrc_response(frequencies, carrier.symbol_rate, carrier.alpha), axis=1)
        points = constellation(carrier.mod, carrier.code_rate)
        rings = _rings(points)
        symmetry = 8 if carrier.mod == "8PSK" else 4
        sps = FS_MON / carrier.symbol_rate
        timing = _timing(matched, sps, rings, symmetry, config)
        if timing is None:
            info["status"] = "too_few_guarded_symbols"
            diagnostics.append(info)
            continue
        tau, contrast = timing
        info.update(timing_samples=float(tau), timing_contrast=float(contrast))
        indices = np.arange(int(np.ceil((2 - tau) / sps)), int(np.floor((n - 3 - tau) / sps)) + 1)
        samples = _interpolate(matched, tau + indices * sps)
        decisions, _, error = _lock(samples, rings, symmetry, config.phase_steps)
        decision_spectrum = np.abs(np.fft.fft(decisions, axis=1))**2
        tone_fraction = decision_spectrum.max(axis=1) / np.maximum(decision_spectrum.sum(axis=1), 1e-30)
        accept = (strong & (error <= config.max_decision_error) & (contrast >= config.min_timing_contrast)
                  & (tone_fraction <= config.max_symbol_tone_fraction))
        info.update(decision_error=[float(v) for v in error], accepted_windows=int(accept.sum()),
                    symbol_tone_fraction=[float(v) for v in tone_fraction],
                    status="decision_directed_fit" if accept.any() else "no_constellation_clock_lock")
        if accept.any():
            reference = _remodulate(decisions, indices, tau, sps, n, carrier.alpha, config.pulse_span_symbols)
            estimate = _received_fit(reference, target, support, config.guard_symbols * sps, config)
            estimate[~accept] = 0
            total += estimate / rotation
        diagnostics.append(info)
    residual = values - total
    with np.errstate(over="ignore", invalid="ignore"):
        reconstruction = total.astype(observed.dtype)
        residual = residual.astype(observed.dtype)
    if not np.isfinite(residual).all() or not np.isfinite(reconstruction).all():
        raise ValueError("cancellation output exceeds the finite input dtype range")
    meta = {"algorithm": ALGORITHM, "config": config.to_dict(), "input_shape": list(observed.shape),
            "n_carriers": len(carriers), "carriers": diagnostics,
            "input_power": float(np.mean(np.abs(values)**2)),
            "residual_power": float(np.mean(np.abs(residual.astype(np.complex128))**2)),
            "limitations": "Linear decision-directed receiver; finite-window edge guards, shared timing, no framing/payload-truth or arbitrary CFO inversion. Tone-like symbol sequences are rejected. Overlapping unplanned signals may be partly cancelled."}
    return CancellationResult(residual, reconstruction, meta)

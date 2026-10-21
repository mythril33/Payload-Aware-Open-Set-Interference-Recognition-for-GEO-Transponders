"""Observation-based carrier cancellation for the B2 fifth input channel (P18 §5, K9).

The canceller sees only what a monitoring operator sees: the calibrated co-pol
monitor IQ of one observation and the operator carrier plan (centre frequency,
symbol rate, roll-off, MODCOD and relative power of each *planned* carrier).
It never receives transmitted symbols, activity masks, the realized back-off,
XPD, event labels or event parameters. Every planned carrier is processed,
whether or not it was actually transmitted, because the operator cannot know
that in advance; the residual therefore also carries plan-inconsistency
evidence.

Per planned carrier and monitor snapshot the receiver performs decision-directed
remodulation: resample to the simulation rate so that samples/symbol is an
integer, mix to baseband, SRRC matched filtering, non-data-aided symbol timing
(Oerder-Meyr spectral-line estimator, quantized to the resampled grid), a coarse
phase search over the constellation's symmetry sector followed by iterative
hard decisions with complex least-squares gain, and SRRC remodulation. The sum
of remodulated carriers is subtracted from the observed IQ. Residual power from
decision errors, payload nonlinearity, intersymbol leakage at the block edges
and timing quantization remains in the residual; it is measured, not hidden.
An oracle canceller that uses simulator symbols is not implemented here and
must never feed a model input.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from numbers import Integral, Real

import numpy as np
from scipy.signal import fftconvolve, resample_poly

from . import FS_MON, FS_SIM
from . import sensor as sn
from .waveform import Carrier, constellation, samples_per_symbol

VERSION = "obs-cancel/1"
UPSAMPLE = int(round(FS_SIM / FS_MON))
SYMMETRY = {"QPSK": 4, "8PSK": 8, "16APSK": 4, "32APSK": 4}


def _integer(value, name, minimum, maximum):
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Integral) or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be an integer in [{minimum}, {maximum}]")
    return int(value)


@dataclass(frozen=True)
class CancellationConfig:
    """Frozen receiver settings; bound into artifact requests and fingerprints."""
    srrc_span_symbols: int = 10      # truncated SRRC span, symbols
    phase_grid: int = 16             # coarse phase candidates per symmetry sector
    iterations: int = 3              # decision-directed gain refinements
    edge_guard: int = 512            # monitor samples dropped at each block edge for the residual PSD
    version: str = VERSION

    def __post_init__(self):
        object.__setattr__(self, "srrc_span_symbols", _integer(self.srrc_span_symbols, "srrc_span_symbols", 2, 64))
        object.__setattr__(self, "phase_grid", _integer(self.phase_grid, "phase_grid", 1, 256))
        object.__setattr__(self, "iterations", _integer(self.iterations, "iterations", 1, 20))
        object.__setattr__(self, "edge_guard", _integer(self.edge_guard, "edge_guard", 0, sn.SNAP_MON // 2 - sn.NFFT // 2))
        if self.version != VERSION:
            raise ValueError(f"cancellation version must be {VERSION}")

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class CancellationResult:
    residual_iq: np.ndarray        # [n_snap, SNAP_MON] complex64 at the monitor rate, full block
    residual_db: np.ndarray        # [n_snap, 512] float32 Welch PSD of the edge-guarded residual
    carriers: list                 # per-planned-carrier observation-derived diagnostics (JSON-safe)
    config: CancellationConfig


def srrc_taps(symbol_rate: float, alpha: float, fs: float, span_symbols: int) -> np.ndarray:
    """Unit-energy time-domain SRRC pulse truncated to ``span_symbols`` (odd length).

    Matched filtering the ideal transmitted SRRC pulse with this response gives a
    raised-cosine pulse with unit peak at the correct symbol instants.
    """
    sps = samples_per_symbol(symbol_rate, fs)
    half = span_symbols * sps // 2
    t = np.arange(-half, half + 1) / sps                 # time in symbols
    with np.errstate(divide="ignore", invalid="ignore"):
        num = np.sin(np.pi * t * (1 - alpha)) + 4 * alpha * t * np.cos(np.pi * t * (1 + alpha))
        den = np.pi * t * (1 - (4 * alpha * t) ** 2)
        h = num / den
    h[t == 0] = 1 - alpha + 4 * alpha / np.pi
    singular = np.isclose(np.abs(4 * alpha * t), 1.0)
    if singular.any():
        h[singular] = (alpha / np.sqrt(2)) * ((1 + 2 / np.pi) * np.sin(np.pi / (4 * alpha))
                                              + (1 - 2 / np.pi) * np.cos(np.pi / (4 * alpha)))
    return (h / np.sqrt(np.sum(h ** 2))).astype(np.float64)


def _decide(z: np.ndarray, points: np.ndarray) -> np.ndarray:
    """Nearest constellation index for every sample of ``z`` (any shape)."""
    flat = z.reshape(-1)
    out = np.empty(flat.shape, np.int64)
    step = max(1, 2_000_000 // len(points))
    for start in range(0, len(flat), step):
        block = flat[start:start + step]
        # |z - p|^2 = |z|^2 + |p|^2 - 2 Re(z p*); |z|^2 is common per sample
        metric = np.abs(points)[None, :] ** 2 - 2 * np.real(block[:, None] * np.conj(points)[None, :])
        out[start:start + step] = np.argmin(metric, axis=1)
    return out.reshape(z.shape)


def _timing(y: np.ndarray, sps: int) -> np.ndarray:
    """Oerder-Meyr non-data-aided timing per snapshot, integer samples in [0, sps)."""
    n = np.arange(y.shape[-1])
    line = np.sum(np.abs(y) ** 2 * np.exp(-2j * np.pi * n / sps), axis=-1)
    tau = -np.angle(line) / (2 * np.pi) * sps
    return np.mod(np.rint(tau).astype(np.int64), sps)


def _validate_iq(iq) -> np.ndarray:
    values = np.asarray(iq)
    if values.ndim != 2 or values.shape[1] != sn.SNAP_MON or values.dtype.kind not in "cfiu" or not values.size:
        raise ValueError(f"monitor IQ must be a nonempty [n_snap, {sn.SNAP_MON}] complex array")
    values = np.asarray(values, dtype=np.complex128)
    if not np.isfinite(values).all():
        raise ValueError("monitor IQ must be finite")
    return values


def _validate_plan(plan) -> list[Carrier]:
    if not isinstance(plan, (tuple, list)) or not plan or any(not isinstance(c, Carrier) for c in plan):
        raise ValueError("plan must be a nonempty list of operator Carrier entries")
    for carrier in plan:
        for key in ("f0", "symbol_rate", "alpha", "power"):
            value = getattr(carrier, key)
            if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real) or not np.isfinite(value):
                raise ValueError(f"carrier {key} must be a finite real number")
        if carrier.symbol_rate <= 0 or not 0 < carrier.alpha <= 1 or carrier.power <= 0:
            raise ValueError("carrier rate, roll-off and power must be positive")
        if carrier.mod not in SYMMETRY:
            raise ValueError(f"unsupported planned modulation {carrier.mod!r}")
        samples_per_symbol(carrier.symbol_rate, FS_SIM)
        constellation(carrier.mod, carrier.code_rate)
        if abs(carrier.f0) + carrier.occupied_bw / 2 > FS_MON / 2:
            raise ValueError("planned carrier lies outside the monitor bandwidth")
    return list(plan)


def cancel_planned_carriers(iq, plan, config: CancellationConfig | None = None) -> CancellationResult:
    """Subtract decision-directed remodulations of all planned carriers from monitor IQ.

    ``iq``: calibrated co-pol monitor samples ``[n_snap, 4096]`` at 96 MHz.
    ``plan``: the operator's carrier plan for that feed. Nothing else is used.
    """
    config = CancellationConfig() if config is None else config
    if not isinstance(config, CancellationConfig):
        raise ValueError("config must be a CancellationConfig")
    iq = _validate_iq(iq)
    plan = _validate_plan(plan)
    n_snap, length = iq.shape
    fs = FS_SIM
    high = resample_poly(iq, UPSAMPLE, 1, axis=-1)                      # [n_snap, 12288] at 288 MHz
    n_high = high.shape[-1]
    time_index = np.arange(n_high)
    rows = np.arange(n_snap)[:, None]
    remodulated = np.zeros_like(high)
    diagnostics = []
    for position, carrier in enumerate(plan):
        sps = samples_per_symbol(carrier.symbol_rate, fs)
        points = constellation(carrier.mod, carrier.code_rate)
        taps = srrc_taps(carrier.symbol_rate, carrier.alpha, fs, config.srrc_span_symbols)
        mixer = np.exp(-2j * np.pi * carrier.f0 * time_index / fs)
        matched = fftconvolve(high * mixer, taps[None, :], mode="same", axes=-1)
        tau = _timing(matched, sps)
        n_sym = (n_high - sps) // sps
        index = tau[:, None] + sps * np.arange(n_sym)[None, :]
        symbols = matched[rows, index]                                   # [n_snap, n_sym]
        rms = np.sqrt(np.mean(np.abs(symbols) ** 2, axis=1, keepdims=True))
        rms = np.where(rms > 0, rms, 1.0)
        normalized = symbols / rms
        # Coarse phase over one symmetry sector; the remaining rotation ambiguity
        # is absorbed by the complex gain and does not change the remodulation.
        sector = 2 * np.pi / SYMMETRY[carrier.mod]
        best_error, best_phase = None, np.zeros(n_snap)
        for candidate in np.arange(config.phase_grid) * sector / config.phase_grid:
            rotated = normalized * np.exp(-1j * candidate)
            decided = points[_decide(rotated, points)]
            error = np.sum(np.abs(rotated - decided) ** 2, axis=1)
            if best_error is None:
                best_error, best_phase = error, np.full(n_snap, candidate)
            else:
                better = error < best_error
                best_error = np.where(better, error, best_error)
                best_phase = np.where(better, candidate, best_phase)
        gain = (rms[:, 0] * np.exp(1j * best_phase))                     # initial complex gain per snapshot
        decided = None
        for _ in range(config.iterations):
            safe_gain = np.where(np.abs(gain) > 0, gain, 1.0)
            decided = points[_decide(symbols / safe_gain[:, None], points)]
            denominator = np.sum(np.abs(decided) ** 2, axis=1)
            gain = np.sum(np.conj(decided) * symbols, axis=1) / np.where(denominator > 0, denominator, 1.0)
        estimate = gain[:, None] * decided
        error_power = np.mean(np.abs(symbols - estimate) ** 2, axis=1)
        signal_power = np.mean(np.abs(estimate) ** 2, axis=1)
        impulses = np.zeros_like(high)
        impulses[rows, index] = estimate
        shaped = fftconvolve(impulses, taps[None, :], mode="same", axes=-1)
        remodulated += shaped * np.conj(mixer)
        with np.errstate(divide="ignore"):
            est_snr_db = 10 * np.log10(signal_power / np.where(error_power > 0, error_power, np.nan))
        diagnostics.append({"plan_index": position, "f0": float(carrier.f0), "symbol_rate": float(carrier.symbol_rate),
                            "mod": carrier.mod, "samples_per_symbol": int(sps), "symbols_per_snapshot": int(n_sym),
                            "timing_samples": tau.astype(int).tolist(),
                            "gain_power_db_mean": float(np.mean(20 * np.log10(np.maximum(np.abs(gain), 1e-30)))),
                            "decision_snr_db_median": None if not np.isfinite(est_snr_db).any()
                            else float(np.nanmedian(est_snr_db)),
                            "basis": "observed IQ and operator plan only"})
    cancelled = resample_poly(remodulated, 1, UPSAMPLE, axis=-1)
    if cancelled.shape != iq.shape:
        raise ValueError("resampling changed the monitor block length")
    residual = (iq - cancelled).astype(np.complex64)
    if not np.isfinite(residual).all():
        raise ValueError("cancellation produced nonfinite residual samples")
    guard = config.edge_guard
    window = residual[:, guard:length - guard] if guard else residual
    residual_db = sn.spectrogram_db(window)
    if not np.isfinite(residual_db).all():
        raise ValueError("residual spectrogram is not finite")
    return CancellationResult(residual, residual_db, diagnostics, config)


def band_power_db(spec_db: np.ndarray, f_lo: float, f_hi: float) -> float:
    """Mean linear PSD in dB over the monitor bins inside [f_lo, f_hi]; a diagnostic helper."""
    from .plan import monitor_freqs
    f = monitor_freqs()
    inside = (f >= f_lo) & (f <= f_hi)
    if not inside.any():
        raise ValueError("band contains no monitor bins")
    return float(10 * np.log10(np.mean(10 ** (np.asarray(spec_db, np.float64)[..., inside] / 10))))

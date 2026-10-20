"""Two polarization paths with explicit physical and instrument mixing.

The symmetric unitary uplink Jones matrix precedes the two IMUX/TWTA/OMUX
paths. Optional satellite LO phase noise is common to both paths before IMUX.
Downlink Jones mixing follows OMUX; external downlink interferers are added
after that mixing, without passing through this satellite's payload. Receiver
LO phase noise rotates the combined signal before the independent receiver
response and receiver noise. A separately
fitted receiver calibration corrects that instrument response only; it does
not remove the physical uplink or downlink mixing.

Per-feed receiver noise is referenced to that feed's pre-downlink-mixing OMUX
output, following A1's output-C/N convention. Its power is not renormalized
after downlink or instrument mixing. These are ideal basis-coupling blocks,
not a complete lossy antenna or propagation model. LO linewidths describe an
effective Lorentzian/Wiener model, not a measured oscillator phase-noise mask.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from numbers import Integral, Real

import numpy as np

from . import FS_SIM
from . import payload as pl
from . import sensor as sn
from .plan import plan_mask_db
from .phase_noise import rotate_phase, wiener_phase
from .polarization import ReceiverCalibration, apply_jones, jones_matrix
from .scenario import Interferer, ScenarioConfig, default_plan
from .waveform import Carrier, constellation, generate_carrier, samples_per_symbol


def _real(value, name: str, *, ideal: bool = False) -> float:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real):
        raise ValueError(f"{name} must be a real number")
    try:
        number = float(value)
    except OverflowError as error:
        raise ValueError(f"{name} must be representable as a finite real number") from error
    if not np.isfinite(number) and not (ideal and number == np.inf):
        raise ValueError(f"{name} must be finite" + (" or positive infinity" if ideal else ""))
    return number


def _validate_path(cfg: ScenarioConfig, name: str) -> None:
    if not isinstance(cfg, ScenarioConfig):
        raise ValueError(f"{name} must be a ScenarioConfig")
    if cfg.bandwidth not in (36e6, 72e6):
        raise ValueError(f"{name}.bandwidth must be 36e6 or 72e6 Hz")
    if isinstance(cfg.seed, (bool, np.bool_)) or not isinstance(cfg.seed, Integral) or not 0 <= cfg.seed < 2**63:
        raise ValueError(f"{name}.seed must be a nonnegative int64 integer")
    if isinstance(cfg.n_snap, (bool, np.bool_)) or not isinstance(cfg.n_snap, Integral) or cfg.n_snap < 1:
        raise ValueError(f"{name}.n_snap must be a positive integer")
    interval = _real(cfg.snap_interval, f"{name}.snap_interval")
    if interval <= sn.N_SIM / FS_SIM:
        raise ValueError(f"{name}.snap_interval must exceed the simulated snapshot duration")
    if not -20 <= _real(cfg.ibo_db, f"{name}.ibo_db") <= 100:
        raise ValueError(f"{name}.ibo_db must be in [-20, 100] dB")
    for key in ("cn_up_db", "cn_dn_db"):
        cn = _real(getattr(cfg, key), f"{name}.{key}", ideal=True)
        if np.isfinite(cn) and not -100 <= cn <= 300:
            raise ValueError(f"{name}.{key} must be in [-100, 300] dB or positive infinity")
    if not isinstance(cfg.linear, (bool, np.bool_)):
        raise ValueError(f"{name}.linear must be a boolean")
    # Resolve supported models now, before generating any observations.
    pl.amplifier(cfg.amplifier)
    pl.imux(cfg.bandwidth, FS_SIM, cfg.filter_model)
    pl.omux(cfg.bandwidth, FS_SIM, cfg.filter_model)


def _response(value) -> np.ndarray:
    matrix = np.eye(2, dtype=np.complex128) if value is None else np.asarray(value)
    if matrix.shape != (2, 2) or matrix.dtype.kind not in "iufc" or not np.isfinite(matrix).all():
        raise ValueError("receiver_response must be a finite numeric 2x2 matrix")
    matrix = np.array(matrix, dtype=np.complex128, copy=True)
    condition = float(np.linalg.cond(matrix))
    if not np.isfinite(condition) or condition > 1e6:
        raise ValueError("receiver_response must be nonsingular with condition number <= 1e6")
    matrix.setflags(write=False)
    return matrix


def _complex64(values, name: str) -> np.ndarray:
    with np.errstate(over="ignore", invalid="ignore"):
        converted = np.asarray(values, dtype=np.complex64)
    if not np.isfinite(converted).all():
        raise ValueError(f"{name} exceeds the simulator's finite complex64 range")
    return converted


def _json_safe(value):
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (float, np.floating)):
        return "ideal" if value == np.inf else float(value)
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, np.integer):
        return int(value)
    return value


@dataclass(frozen=True)
class DualScenarioConfig:
    co: ScenarioConfig = field(default_factory=lambda: ScenarioConfig(seed=0))
    cross: ScenarioConfig = field(default_factory=lambda: ScenarioConfig(seed=1))
    uplink_xpd_db: float = 30.0
    downlink_xpd_db: float = 30.0
    uplink_phase_rad: float = 0.0
    downlink_phase_rad: float = 0.0
    receiver_response: np.ndarray | None = None
    satellite_linewidth_hz: float = 0.0
    receiver_linewidth_hz: float = 0.0

    def __post_init__(self):
        _validate_path(self.co, "co")
        _validate_path(self.cross, "cross")
        for key in ("bandwidth", "n_snap", "snap_interval"):
            if getattr(self.co, key) != getattr(self.cross, key):
                raise ValueError(f"co and cross must have matching {key}")
        jones_matrix(self.uplink_xpd_db, self.uplink_phase_rad)
        jones_matrix(self.downlink_xpd_db, self.downlink_phase_rad)
        for key in ("satellite_linewidth_hz", "receiver_linewidth_hz"):
            linewidth = _real(getattr(self, key), key)
            if linewidth < 0:
                raise ValueError(f"{key} must be nonnegative")
            object.__setattr__(self, key, linewidth)
        object.__setattr__(self, "co", replace(self.co))
        object.__setattr__(self, "cross", replace(self.cross))
        object.__setattr__(self, "receiver_response", _response(self.receiver_response))

    def to_dict(self) -> dict:
        """Strict-JSON truth configuration; ideal isolation is the string 'ideal'."""
        return _json_safe({"co": asdict(self.co), "cross": asdict(self.cross),
                           "uplink_xpd_db": self.uplink_xpd_db,
                           "downlink_xpd_db": self.downlink_xpd_db,
                           "uplink_phase_rad": self.uplink_phase_rad,
                           "downlink_phase_rad": self.downlink_phase_rad,
                           "satellite_linewidth_hz": self.satellite_linewidth_hz,
                           "receiver_linewidth_hz": self.receiver_linewidth_hz,
                           "receiver_response": {"real": self.receiver_response.real.tolist(),
                                                 "imag": self.receiver_response.imag.tolist()}})


@dataclass
class DualScenarioResult:
    spec_db: np.ndarray            # [2, n_snap, 512] float32
    mask_db: np.ndarray            # [2, 512] float32, one independent carrier plan per feed
    meta: dict = field(default_factory=dict)
    iq: np.ndarray | None = None   # calibrated if requested, [2, n_snap, 4096] complex64


def _validate_plan(plan, cfg: ScenarioConfig, name: str) -> list[Carrier]:
    if not isinstance(plan, (tuple, list)) or not plan:
        raise ValueError(f"{name} plan must contain at least one Carrier")
    result = list(plan)
    for carrier in result:
        if not isinstance(carrier, Carrier):
            raise ValueError(f"{name} plan entries must be Carrier objects")
        for key in ("f0", "symbol_rate", "alpha", "power"):
            _real(getattr(carrier, key), f"{name} carrier {key}")
        if carrier.symbol_rate <= 0 or not 0 < carrier.alpha <= 1 or carrier.power <= 0:
            raise ValueError(f"{name} carrier rate, roll-off and power must be positive")
        if abs(carrier.f0) + carrier.occupied_bw / 2 > cfg.bandwidth / 2 + 1e-6:
            raise ValueError(f"{name} carrier occupied spectrum exceeds its transponder bandwidth")
        samples_per_symbol(carrier.symbol_rate, FS_SIM)
        try:
            constellation(carrier.mod, carrier.code_rate)
        except (KeyError, ValueError) as error:
            raise ValueError(f"{name} carrier has an invalid modulation/code rate") from error
    if not np.isclose(sum(carrier.power for carrier in result), 1.0, rtol=1e-6, atol=1e-8):
        raise ValueError(f"{name} plan powers must sum to the unit nominal carrier load")
    return result


def simulate_dual(cfg: DualScenarioConfig, plans: tuple[list[Carrier], list[Carrier]] | None = None,
                  interferers: tuple[Interferer | None, Interferer | None] | None = None,
                  calibration: ReceiverCalibration | None = None, keep_iq: bool = False,
                  downlink_interferers: tuple[Interferer | None, Interferer | None] | None = None) -> DualScenarioResult:
    """Generate paired complex observations with explicit physical injection sites.

    Each polarization uses its own ScenarioConfig seed and the exact A1 stream
    layout. Identity coupling and instrument response therefore reduce to two
    independent A1 runs. Reusing a seed intentionally makes the random streams
    coherent; distinct seeds are required for independent loading.

    Uplink interferers are referenced to unit planned uplink power. Downlink
    callbacks use the same nominal unit-power convention, then their output
    is scaled by sqrt(wanted feed power) after physical downlink mixing, before
    either feed receives an external event. This uses retained simulation
    samples for the reference and leaves payload/noise powers unchanged.
    Default-zero linewidths and absent downlink events retain the A1 streams.
    """
    if not isinstance(cfg, DualScenarioConfig):
        raise ValueError("cfg must be a DualScenarioConfig")
    # Nested ScenarioConfig is mutable: revalidate it if a caller changed it.
    cfg = replace(cfg)
    configs = (cfg.co, cfg.cross)
    if plans is None:
        plans = tuple(default_plan(int(path.seed), path.bandwidth) for path in configs)
    if not isinstance(plans, (tuple, list)) or len(plans) != 2:
        raise ValueError("plans must contain one carrier plan per polarization")
    plans = tuple(_validate_plan(plan, path, name) for plan, path, name in zip(plans, configs, ("co", "cross")))
    if interferers is None:
        interferers = (None, None)
    if not isinstance(interferers, (tuple, list)) or len(interferers) != 2 or any(event is not None and not callable(event) for event in interferers):
        raise ValueError("interferers must contain two callables or None entries")
    if downlink_interferers is None:
        downlink_interferers = (None, None)
    if (not isinstance(downlink_interferers, (tuple, list)) or len(downlink_interferers) != 2
            or any(event is not None and not callable(event) for event in downlink_interferers)):
        raise ValueError("downlink_interferers must contain two callables or None entries")
    if calibration is not None and not isinstance(calibration, ReceiverCalibration):
        raise ValueError("calibration must be a ReceiverCalibration fitted from independent pilots")
    if not isinstance(keep_iq, (bool, np.bool_)):
        raise ValueError("keep_iq must be boolean")

    fs, n = FS_SIM, sn.N_SIM
    shape = (cfg.co.n_snap, n)
    t0 = np.arange(cfg.co.n_snap) * cfg.co.snap_interval

    def lo_phase(values, linewidth, stage):
        if linewidth == 0:
            return values
        rng = np.random.default_rng(np.random.SeedSequence([int(cfg.co.seed), int(cfg.cross.seed), 7051, stage]))
        return rotate_phase(values, wiener_phase(rng, t0, n, fs, linewidth))

    streams, uplinks = [], []
    for path, plan, event in zip(configs, plans, interferers):
        seeds = np.random.SeedSequence(path.seed).spawn(5)
        streams.append(seeds)
        rng = np.random.default_rng(seeds[1])
        x = np.zeros(shape, np.complex64)
        for carrier in plan:
            x += generate_carrier(rng, carrier, path.n_snap, n, fs)
        if event is not None:
            generated = np.asarray(event(np.random.default_rng(seeds[4]), np.arange(path.n_snap) * path.snap_interval, n, fs))
            if generated.shape != shape or generated.dtype.kind not in "iufc" or not np.isfinite(generated).all():
                raise ValueError("uplink interferer must return finite numeric [n_snap, N_SIM] samples")
            x += _complex64(generated, "uplink interferer")
        n0_up = 1.0 / (path.bandwidth * 10 ** (path.cn_up_db / 10))
        x += sn.awgn(np.random.default_rng(seeds[2]), shape, n0_up, fs)
        uplinks.append(x)
    mixed_uplink = _complex64(apply_jones(jones_matrix(cfg.uplink_xpd_db, cfg.uplink_phase_rad), np.stack(uplinks)), "mixed uplink")
    mixed_uplink = lo_phase(mixed_uplink, cfg.satellite_linewidth_hz, 0)

    payload_outputs, path_meta = [], []
    retained = slice(sn.WARMUP_SIM, None)
    for path, x in zip(configs, mixed_uplink):
        amp = pl.amplifier(path.amplifier)
        x = pl.imux(path.bandwidth, fs, path.filter_model).apply(x)
        x *= amp.drive_gain(1.0, path.ibo_db)
        drive_power = float(np.mean(np.abs(x[:, retained]) ** 2))
        drive_ibo = float(10 * np.log10(amp.r_sat ** 2 / drive_power)) if drive_power > 0 else None
        y = amp.linear(x) if path.linear else amp(x)
        amplifier_power = float(np.mean(np.abs(y[:, retained]) ** 2))
        obo = amp.obo_db(y[:, retained]) if amplifier_power > 0 else None
        y = pl.omux(path.bandwidth, fs, path.filter_model).apply(y)
        p_out = float(np.mean(np.abs(y[:, retained]) ** 2))
        n0_dn = p_out / (path.bandwidth * 10 ** (path.cn_dn_db / 10))
        finite_statistics = [value for value in (drive_ibo, obo, p_out, n0_dn) if value is not None]
        if not all(np.isfinite(value) for value in finite_statistics) or drive_power < 0 or p_out < 0:
            raise ValueError("payload produced an invalid-power observation")
        path_meta.append({"actual_ibo_db": drive_ibo, "obo_db": obo,
                          "omux_output_power": p_out, "receiver_noise_psd": n0_dn,
                          "zero_drive": drive_power == 0})
        payload_outputs.append(y)
    physical = apply_jones(jones_matrix(cfg.downlink_xpd_db, cfg.downlink_phase_rad), np.stack(payload_outputs))
    reference_powers = [float(np.mean(np.abs(feed[:, retained]) ** 2)) for feed in physical]
    if not all(np.isfinite(power) and power >= 0 for power in reference_powers):
        raise ValueError("downlink mixing produced an invalid wanted-feed power")
    for pol, event in enumerate(downlink_interferers):
        if event is not None:
            rng = np.random.default_rng(np.random.SeedSequence([int(cfg.co.seed), int(cfg.cross.seed), 7052, pol]))
            generated = np.asarray(event(rng, t0, n, fs))
            if generated.shape != shape or generated.dtype.kind not in "iufc" or not np.isfinite(generated).all():
                raise ValueError("downlink interferer must return finite numeric [n_snap, N_SIM] samples")
            scaled = _complex64(generated * np.sqrt(reference_powers[pol]), "downlink interferer")
            physical[pol] += scaled
    physical = lo_phase(physical, cfg.receiver_linewidth_hz, 1)
    measured = _complex64(apply_jones(cfg.receiver_response, physical), "instrument observation")
    for i, (path, seeds) in enumerate(zip(configs, streams)):
        measured[i] += sn.awgn(np.random.default_rng(seeds[3]), shape, path_meta[i]["receiver_noise_psd"], fs)
    if calibration is not None:
        measured = _complex64(calibration.correct(measured), "corrected observation")
    iq = sn.to_monitor(measured)
    if not np.isfinite(iq).all():
        raise ValueError("monitoring produced nonfinite IQ")
    metadata = {"config": cfg.to_dict(), "polarizations": ["co", "cross"],
                "plans": [[asdict(carrier) for carrier in plan] for plan in plans],
                "paths": path_meta, "has_interferer": [event is not None for event in interferers],
                "has_downlink_interferer": [event is not None for event in downlink_interferers],
                "downlink_interference_reference_power": reference_powers,
                "downlink_interference_reference": "per-feed wanted power after physical downlink mixing, before external events; retained simulation samples",
                "phase_noise": {"model": "effective Lorentzian/Wiener; increment variance 2*pi*linewidth_hz*elapsed_seconds",
                                "common_to_polarizations": True,
                                "satellite_stage": "after uplink mixing, before IMUX",
                                "receiver_stage": "after downlink mixing and external events, before instrument response and receiver noise",
                                "time_reference": "continuous sparse-window walk; first simulated sample phase zero"},
                "mixing_model": "symmetric unitary ideal basis coupling",
                "receiver_noise_reference": "per-feed pre-downlink-mixing OMUX power; not renormalized after physical/instrument mixing",
                "receiver_calibration_applied": calibration is not None,
                "receiver_calibration": calibration.to_dict() if calibration is not None else None}
    return DualScenarioResult(sn.spectrogram_db(iq), np.stack([plan_mask_db(plan) for plan in plans]),
                              _json_safe(metadata), iq if keep_iq else None)

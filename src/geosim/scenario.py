"""One scenario end to end: plan -> uplink -> payload -> downlink -> spectrogram."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Callable

import numpy as np

from . import FS_SIM
from . import payload as pl
from . import sensor as sn
from .plan import plan_mask_db, random_plan
from .waveform import Carrier, generate_carrier

# interferer(rng, t0, n, fs) -> (n_snap, n) complex uplink samples; t0 = snapshot start times, s.
# Carrier power totals 1 at the uplink, so interferer power is its C/I directly.
Interferer = Callable[[np.random.Generator, np.ndarray, int, float], np.ndarray]


@dataclass
class ScenarioConfig:
    bandwidth: float = 36e6       # Hz, 36e6 or 72e6
    ibo_db: float = 6.0           # input back-off of the interference-free carrier load
    cn_up_db: float = 25.0        # carrier power / uplink noise in `bandwidth`
    cn_dn_db: float = 20.0        # OMUX output power / downlink noise in `bandwidth`
    linear: bool = False          # True: replace the TWTA by its small-signal gain
    filter_model: str = "dvbs2x"  # IMUX/OMUX model, see payload.imux_sos
    n_snap: int = 128
    snap_interval: float = 10e-3  # s between snapshot starts
    seed: int = 0


@dataclass
class ScenarioResult:
    spec_db: np.ndarray           # (n_snap, 512) float32
    mask_db: np.ndarray           # (512,) float32
    meta: dict = field(default_factory=dict)
    iq: np.ndarray | None = None  # (n_snap, 4096) complex64 at 96 MHz, if requested


def simulate(cfg: ScenarioConfig, plan: list[Carrier] | None = None,
             interferer: Interferer | None = None, keep_iq: bool = False) -> ScenarioResult:
    # independent streams, so adding an interferer leaves carriers and noise unchanged
    s_plan, s_car, s_up, s_dn, s_int = np.random.SeedSequence(cfg.seed).spawn(5)
    if plan is None:
        plan = random_plan(np.random.default_rng(s_plan), cfg.bandwidth)
    fs, n, shape = FS_SIM, sn.N_SIM, (cfg.n_snap, sn.N_SIM)

    rng = np.random.default_rng(s_car)
    x = np.zeros(shape, np.complex64)
    for c in plan:
        x += generate_carrier(rng, c, cfg.n_snap, n, fs)
    if interferer is not None:
        t0 = np.arange(cfg.n_snap) * cfg.snap_interval
        x += interferer(np.random.default_rng(s_int), t0, n, fs).astype(np.complex64)
    n0_up = 1.0 / (cfg.bandwidth * 10 ** (cfg.cn_up_db / 10))
    x += sn.awgn(np.random.default_rng(s_up), shape, n0_up, fs)

    x = pl.apply_filter(pl.imux_sos(cfg.bandwidth, fs, cfg.filter_model), x)
    x *= pl.drive_gain(1.0, cfg.ibo_db)          # fixed gain, set for the carriers alone
    drive_ibo = 10 * np.log10(pl.R_SAT ** 2 / np.mean(np.abs(x) ** 2))
    y = pl.linear_amp(x) if cfg.linear else pl.saleh(x)
    obo = pl.obo_db(y)
    y = pl.apply_filter(pl.omux_sos(cfg.bandwidth, fs, cfg.filter_model), y)

    p_out = float(np.mean(np.abs(y[:, sn.WARMUP_SIM:]) ** 2))
    n0_dn = p_out / (cfg.bandwidth * 10 ** (cfg.cn_dn_db / 10))
    y += sn.awgn(np.random.default_rng(s_dn), shape, n0_dn, fs)

    z = sn.to_monitor(y)
    meta = {"config": asdict(cfg), "plan": [asdict(c) for c in plan],
            "actual_ibo_db": float(drive_ibo), "obo_db": obo, "has_interferer": interferer is not None}
    return ScenarioResult(sn.spectrogram_db(z), plan_mask_db(plan), meta, z if keep_iq else None)

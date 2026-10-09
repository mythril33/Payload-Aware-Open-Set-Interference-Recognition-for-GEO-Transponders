"""Stage-A class definitions and class-conditional scenario sampling (docs/plan/P3_taksonomi.md)."""
from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np

from . import interferers as it
from .scenario import ScenarioConfig, ScenarioResult, default_plan, simulate

LABELS = ("clean", "cw", "swept_cw", "unauthorized", "overdrive")


@dataclass(frozen=True)
class Ranges:
    """Sampling ranges; all uniform. P5 narrows these per split."""
    ibo_nominal_db: tuple = (8.0, 14.0)      # every class except overdrive
    ibo_overdrive_db: tuple = (0.0, 5.0)     # 5-8 dB is left unused so the two do not touch
    cn_up_db: tuple = (15.0, 30.0)
    cn_dn_db: tuple = (15.0, 30.0)
    c_over_i_db: tuple = (5.0, 35.0)         # cw and swept_cw, against total carrier power
    psd_offset_db: tuple = (-10.0, 3.0)      # unauthorized carrier PSD against the plan's mean PSD
    cw_drift_hz_per_s: tuple = (-5e4, 5e4)
    sweep_span_hz: tuple = (1e6, None)       # None -> 0.9 * bandwidth
    sweep_period_s: tuple = (0.1, 1.28)
    band_fraction: float = 0.48              # interferer frequencies stay within +/- this * bandwidth


DEFAULT_RANGES = Ranges()


def sample(label: str, bandwidth: float, seed: int, ranges: Ranges = DEFAULT_RANGES, linear: bool = False,
           keep_iq: bool = False, **cfg_overrides) -> ScenarioResult:
    """One labelled scenario.

    For a given (seed, bandwidth) the plan, carrier symbols, noise and link parameters are the same
    for every label; only the interferer (or the drive level, for overdrive) differs.
    """
    if label not in LABELS:
        raise ValueError(f"unknown label {label!r}")
    link = np.random.default_rng([seed, 101])            # shared by all labels
    par = np.random.default_rng([seed, 202, LABELS.index(label)])
    u = lambda rng, r: float(rng.uniform(*r))
    ibo_nominal, cn_up, cn_dn = u(link, ranges.ibo_nominal_db), u(link, ranges.cn_up_db), u(link, ranges.cn_dn_db)
    ibo = u(par, ranges.ibo_overdrive_db) if label == "overdrive" else ibo_nominal
    cfg = replace(ScenarioConfig(bandwidth=bandwidth, ibo_db=ibo, cn_up_db=cn_up, cn_dn_db=cn_dn, linear=linear,
                                 seed=seed), **cfg_overrides)
    plan = default_plan(seed, bandwidth)
    half = ranges.band_fraction * bandwidth

    gen, info = None, {"kind": label}
    if label == "cw":
        gen, info = it.cw(u(par, (-half, half)), u(par, ranges.c_over_i_db), u(par, ranges.cw_drift_hz_per_s))
    elif label == "swept_cw":
        span = u(par, (ranges.sweep_span_hz[0], ranges.sweep_span_hz[1] or 0.9 * bandwidth))
        centre = u(par, (-half + span / 2, half - span / 2)) if span < 2 * half else 0.0
        period = u(par, ranges.sweep_period_s)
        gen, info = it.swept_cw(centre - span / 2, centre + span / 2, period, u(par, ranges.c_over_i_db),
                                ("sawtooth", "triangle")[par.integers(2)], u(par, (0.0, period)))
    elif label == "unauthorized":
        gen, info = it.modulated(it.random_unauthorized(par, plan, bandwidth, u(par, ranges.psd_offset_db)))
    if gen is not None:
        n0_up = 1.0 / (bandwidth * 10 ** (cn_up / 10))
        width = max(info["f_hi"] - info["f_lo"], 187.5e3) if label != "swept_cw" else 187.5e3
        info["inr_db"] = float(-info["c_over_i_db"] - 10 * np.log10(n0_up * width))
        info["on_carrier"] = it.overlaps_plan(info["f_lo"], info["f_hi"], plan)

    res = simulate(cfg, plan=plan, interferer=gen, keep_iq=keep_iq)
    res.meta.update(label=label, interferer=info, ibo_nominal_db=ibo_nominal)
    return res

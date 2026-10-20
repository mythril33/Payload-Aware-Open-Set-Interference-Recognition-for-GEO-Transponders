"""Paired known-class scenes for the B2 physical-observation foundation.

All eight variants retain operator plans, carrier/noise RNG streams, physical
link settings and the independently drawn missing-carrier state. Only the
named primary event changes. This module does not compute cancellation
features or create final unknown-test families.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np

from . import interferers as it
from .asi import adjacent_satellite_uplink
from .b2_protocol import BASE_PROTOCOL, PROTOCOL, B2Config, LABELS, require_base_group
from .dual import DualScenarioConfig, DualScenarioResult, simulate_dual
from .events import carrier_under_carrier
from .plan import random_plan
from .polarization import ReceiverCalibration, jones_matrix
from .scenario import ScenarioConfig, default_plan
from .waveform import Carrier

MAX_PLAN_DRAWS = 64
MAX_VICTIM_DRAWS = 64


@dataclass(frozen=True)
class B2Scene:
    cfg: DualScenarioConfig
    plans: tuple[list[Carrier], list[Carrier]]
    interferers: tuple[object | None, object | None]
    active_carriers: tuple[list[bool], list[bool]]
    event: dict
    plan_consistency: int
    metadata: dict


def receiver_response(config: B2Config) -> np.ndarray:
    """Known synthetic instrument response; scene truth, never a model feature."""
    gains = 10 ** (np.asarray(config.receiver_gain_db) / 20) * np.exp(1j * np.asarray(config.receiver_phase_rad))
    return np.diag(gains) @ jones_matrix(config.receiver_xpd_db, config.receiver_coupling_phase_rad)


def _parameters(group: int, label: str) -> np.random.Generator:
    return np.random.default_rng([group, 1820, LABELS.index(label)])


def _event(label: str, group: int, plan, bandwidth: float, active=None):
    rng = _parameters(group, label)
    draw = lambda lo, hi: float(rng.uniform(lo, hi))
    half = 0.48 * bandwidth
    if label == "cw":
        callback, info = it.cw(draw(-half, half), draw(5, 35), draw(-5e4, 5e4))
    elif label == "swept_cw":
        width = draw(1e6, 0.9 * bandwidth)
        centre = draw(-half + width / 2, half - width / 2)
        period = draw(0.1, 1.28)
        callback, info = it.swept_cw(centre - width / 2, centre + width / 2, period, draw(5, 35),
                                     ("sawtooth", "triangle")[int(rng.integers(2))], draw(0, period))
    elif label == "unauthorized":
        offset = draw(-10, 3)
        callback, info = it.modulated(it.random_unauthorized(rng, plan, bandwidth, offset))
        info.update(psd_offset_db=offset, c_over_i_psd_db=-offset)
    elif label == "adjacent_satellite":
        return adjacent_satellite_uplink(rng, plan, bandwidth)
    elif label == "carrier_under_carrier":
        ci = draw(5, 30)
        for rejected in range(MAX_VICTIM_DRAWS):
            callback, info = carrier_under_carrier(rng, plan, bandwidth, ci)
            if active is None or active[info["victim_index"]]:
                info.update(victim_active=True, inactive_victim_rejected_draws=rejected,
                            victim_conditioning="victim must remain active after the shared missing-carrier event")
                return callback, info
        raise it.InfeasibleCarrierError("no active under-carrier victim after bounded parameter draws")
    else:
        return None, {"kind": label, "injection_stage": "payload" if label == "overdrive" else
                      ("uplink_coupling" if label == "cross_pol" else "none")}
    info.update(injection_stage="uplink", power_reference="total_planned_uplink")
    return callback, info


def _plans(group: int, bandwidth: float):
    """Condition every label on the same physically feasible operator plans.

    Only explicit placement infeasibility triggers a bounded new co-pol plan.
    Simulator errors never enter this loop. Retries do not alter carrier/noise
    seeds or the independent opposite-polarization plan.
    """
    cross = default_plan(2 * group + 1, bandwidth)
    for retry in range(MAX_PLAN_DRAWS):
        co = (default_plan(2 * group, bandwidth) if retry == 0 else
              random_plan(np.random.default_rng([group, 1810, retry]), bandwidth))
        try:
            _event("unauthorized", group, co, bandwidth)
            _event("adjacent_satellite", group, co, bandwidth)
            _event("carrier_under_carrier", group, co, bandwidth)
        except it.InfeasibleCarrierError:
            continue
        source = {"co_initial_seed": 2 * group, "cross_seed": 2 * group + 1,
                  "co_rejected_plan_draws": retry,
                  "co_retry_rng_entropy": [group, 1810, retry] if retry else None,
                  "conditioning": "all eight known variants require feasible unauthorized, ASI and under-carrier placement"}
        return (co, cross), source
    raise it.InfeasibleCarrierError("B2 group has no common feasible plan after bounded draws")


def _activity(group: int, plans, config: B2Config, missing_carrier):
    rng = np.random.default_rng([group, 1813])
    sampled_missing = bool(rng.uniform() < config.drop_probability)
    missing = sampled_missing if missing_carrier is None else missing_carrier
    active = ([True] * len(plans[0]), [True] * len(plans[1]))
    # Retain at least one co carrier so every CuC + consistency combination
    # still has a physical victim. Both feeds may otherwise lose one carrier.
    positions = [(pol, index) for pol, plan in enumerate(plans) for index in range(len(plan))
                 if pol != 0 or len(plan) > 1]
    selected = positions[int(rng.integers(len(positions)))]
    dropped = None
    if missing:
        pol, index = selected
        active[pol][index] = False
        dropped = {"polarization": pol, "index": index}
    return active, dropped


def prepare_scene(label: str, group: int, config: B2Config | None = None, *,
                  missing_carrier: bool | None = None) -> B2Scene:
    """Resolve one known scene without running the expensive waveform chain.

    ``missing_carrier`` is an explicit diagnostic override. Dataset generation
    leaves it unset and uses the predeclared shared group draw.
    """
    config = B2Config() if config is None else config
    if not isinstance(config, B2Config):
        raise ValueError("config must be a B2Config")
    if label not in LABELS:
        raise ValueError("B2 base scenes support only the eight known labels")
    role = require_base_group(group)
    if missing_carrier is not None and not isinstance(missing_carrier, bool):
        raise ValueError("missing_carrier must be a boolean or None")
    group = int(group)
    link = np.random.default_rng([group, 1801])
    paths = [ScenarioConfig(bandwidth=config.bandwidth, seed=2 * group + pol,
                            n_snap=config.n_snap, snap_interval=config.snap_interval,
                            ibo_db=float(link.uniform(9, 13)), cn_up_db=float(link.uniform(15, 30)),
                            cn_dn_db=float(link.uniform(15, 30))) for pol in range(2)]
    nominal_ibo = [path.ibo_db for path in paths]
    if label == "overdrive":
        paths[0] = replace(paths[0], ibo_db=float(_parameters(group, label).uniform(1, 4)))
    cfg = DualScenarioConfig(co=paths[0], cross=paths[1],
                              uplink_xpd_db=10.0 if label == "cross_pol" else config.nominal_xpd_db,
                              downlink_xpd_db=config.downlink_xpd_db,
                              receiver_response=receiver_response(config),
                              satellite_linewidth_hz=config.satellite_linewidth_hz,
                              receiver_linewidth_hz=config.receiver_linewidth_hz)
    plans, source = _plans(group, config.bandwidth)
    active, dropped = _activity(group, plans, config, missing_carrier)
    callback, event = _event(label, group, plans[0], config.bandwidth, active[0])
    consistency = int(dropped is not None)
    metadata = {"protocol": BASE_PROTOCOL, "parent_protocol": PROTOCOL, "label": label,
                "scenario_id": group, "role": role, "event": event,
                "plan_consistency": consistency, "nominal_ibo_db": nominal_ibo,
                "operator_plan_source": source, "dropped_carrier": dropped,
                "missing_carrier_override": missing_carrier,
                "missing_carrier_convention": "one planned carrier absent; nominal-load gain fixed; no power renormalization"}
    return B2Scene(cfg, plans, (callback, None), active, event, consistency, metadata)


def sample_scene(label: str, group: int, config: B2Config | None = None, *,
                 missing_carrier: bool | None = None, calibration: ReceiverCalibration | None = None,
                 keep_iq: bool = False) -> DualScenarioResult:
    """Simulate a scene; hidden parameters stay in metadata, never extra inputs."""
    scene = prepare_scene(label, group, config, missing_carrier=missing_carrier)
    result = simulate_dual(scene.cfg, plans=scene.plans, interferers=scene.interferers,
                           active_carriers=scene.active_carriers, calibration=calibration, keep_iq=keep_iq)
    result.meta.update(scene.metadata)
    return result

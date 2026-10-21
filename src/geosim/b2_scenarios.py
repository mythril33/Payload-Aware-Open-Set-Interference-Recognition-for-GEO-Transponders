"""Paired scenes for the B2 stages: eight known classes and the test-only families.

All variants of a scenario group retain operator plans, carrier/noise RNG
streams, physical link settings and the independently drawn missing-carrier
state. Only the named primary event changes. Test-only families (P18 §3) use a
separate event-RNG namespace, are generated only for test-role groups and never
enter training, checkpoint selection or threshold calibration. This module does
not compute cancellation features.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np

from . import interferers as it
from .asi import DEFAULT_RANGES, adjacent_satellite_downlink, adjacent_satellite_uplink, adjacent_satellite_uplink_at_level, overlap_positions
from .b2_protocol import (BASE_PROTOCOL, BENIGN_TEST_FAMILIES, EQUIVALENCE_LIMITED_UNKNOWN, NEAR_UNKNOWN,
                          PROTOCOL, B2Config, LABELS, require_base_group, role_for_group)
from .cid import cid_overlay
from .unknowns import unknown_interferer
from .dual import DualScenarioConfig, DualScenarioResult, simulate_dual
from .events import carrier_under_carrier
from .plan import SYMBOL_RATES, random_plan
from .polarization import ReceiverCalibration, jones_matrix
from .scenario import ScenarioConfig, default_plan
from .waveform import MODULATIONS, ROLLOFFS, Carrier

MAX_PLAN_DRAWS = 64
MAX_VICTIM_DRAWS = 64
TEST_FAMILIES = NEAR_UNKNOWN + EQUIVALENCE_LIMITED_UNKNOWN + BENIGN_TEST_FAMILIES
TEST_PROTOCOL = "B2-test/1"
MATCHED_PROTOCOL = "B2-match/1"
MATCHED_LABELS = ("clean", "adjacent_satellite", "unauthorized")
MATCHED_CI_RANGE = (4.0, 13.0)                       # K17c: shared C/I_psd ~ U(4, 13) dB
MATCHED_BINS = ((4.0, 7.0), (7.0, 10.0), (10.0, 13.0))   # frozen reporting bins, [lo, hi); 13 falls in the last bin
MATCHED_BIN_NAMES = ("4-7", "7-10", "10-13")
NATURAL_CI_PSD_RANGES = {"adjacent_satellite": (2.5, 33.0), "unauthorized": (-3.0, 10.0)}
EXPECTED_DECISION = {**{family: "unknown" for family in NEAR_UNKNOWN + EQUIVALENCE_LIMITED_UNKNOWN},
                     **{family: "clean" for family in BENIGN_TEST_FAMILIES}}


@dataclass(frozen=True)
class B2Scene:
    cfg: DualScenarioConfig
    plans: tuple[list[Carrier], list[Carrier]]
    interferers: tuple[object | None, object | None]
    active_carriers: tuple[list[bool], list[bool]]
    event: dict
    plan_consistency: int
    metadata: dict
    downlink_interferers: tuple[object | None, object | None] = (None, None)


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


def _shared_scene(group: int, config: B2Config, missing_carrier):
    """Group-level draws shared by every known and test-only variant of a scenario."""
    group = int(group)
    link = np.random.default_rng([group, 1801])
    paths = [ScenarioConfig(bandwidth=config.bandwidth, seed=2 * group + pol,
                            n_snap=config.n_snap, snap_interval=config.snap_interval,
                            ibo_db=float(link.uniform(9, 13)), cn_up_db=float(link.uniform(15, 30)),
                            cn_dn_db=float(link.uniform(15, 30))) for pol in range(2)]
    nominal_ibo = [path.ibo_db for path in paths]
    plans, source = _plans(group, config.bandwidth)
    active, dropped = _activity(group, plans, config, missing_carrier)
    return paths, nominal_ibo, plans, source, active, dropped


def _dual_config(paths, uplink_xpd_db, config: B2Config) -> DualScenarioConfig:
    return DualScenarioConfig(co=paths[0], cross=paths[1], uplink_xpd_db=uplink_xpd_db,
                              downlink_xpd_db=config.downlink_xpd_db,
                              receiver_response=receiver_response(config),
                              satellite_linewidth_hz=config.satellite_linewidth_hz,
                              receiver_linewidth_hz=config.receiver_linewidth_hz)


def _metadata(protocol, label, group, role, event, consistency, nominal_ibo, source, dropped, missing_carrier):
    return {"protocol": protocol, "parent_protocol": PROTOCOL, "label": label,
            "scenario_id": int(group), "role": role, "event": event,
            "plan_consistency": consistency, "nominal_ibo_db": nominal_ibo,
            "operator_plan_source": source, "dropped_carrier": dropped,
            "missing_carrier_override": missing_carrier,
            "missing_carrier_convention": "one planned carrier absent; nominal-load gain fixed; no power renormalization"}


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
    paths, nominal_ibo, plans, source, active, dropped = _shared_scene(group, config, missing_carrier)
    if label == "overdrive":
        paths[0] = replace(paths[0], ibo_db=float(_parameters(group, label).uniform(1, 4)))
    cfg = _dual_config(paths, 10.0 if label == "cross_pol" else config.nominal_xpd_db, config)
    callback, event = _event(label, group, plans[0], config.bandwidth, active[0])
    consistency = int(dropped is not None)
    metadata = _metadata(BASE_PROTOCOL, label, group, role, event, consistency, nominal_ibo, source, dropped,
                         missing_carrier)
    return B2Scene(cfg, plans, (callback, None), active, event, consistency, metadata)


def matched_bin(c_over_i_psd_db: float) -> int:
    """Index of the frozen K17c reporting bin; the upper edge 13 dB belongs to the last bin."""
    for index, (lo, hi) in enumerate(MATCHED_BINS):
        if lo <= c_over_i_psd_db < hi:
            return index
    if c_over_i_psd_db == MATCHED_BINS[-1][1]:
        return len(MATCHED_BINS) - 1
    raise ValueError("C/I_psd is outside the frozen matched range")


def _gap_options(plan, bandwidth, symbol_rate, alpha):
    """Free gaps that hold an unauthorized carrier of this (Rs, alpha) with the A1 guard convention."""
    need = symbol_rate * (1 + alpha) + 2 * 0.05 * symbol_rate
    return [(lo, hi, need) for lo, hi in it.free_gaps(plan, bandwidth) if need <= hi - lo]


def _matched_options(plan, bandwidth):
    """(Rs, alpha) pairs that admit BOTH an overlapping ASI placement and a gap placement."""
    options = []
    for rs in SYMBOL_RATES:
        for alpha in ROLLOFFS:
            if overlap_positions(plan, bandwidth, rs, alpha).size and _gap_options(plan, bandwidth, rs, alpha):
                options.append((float(rs), float(alpha)))
    return options


def _matched_plans(group: int, bandwidth: float):
    """Operator plans for a matched group: the base conditioning plus joint matched feasibility.

    Same seed convention as :func:`_plans` (initial ``default_plan(2 * group)``, retries in the
    ``[group, 1810, retry]`` namespace, at most 64 draws). The opposite-polarization plan is fixed.
    """
    cross = default_plan(2 * group + 1, bandwidth)
    for retry in range(MAX_PLAN_DRAWS):
        co = (default_plan(2 * group, bandwidth) if retry == 0 else
              random_plan(np.random.default_rng([group, 1810, retry]), bandwidth))
        options = _matched_options(co, bandwidth)
        if options:
            source = {"co_initial_seed": 2 * group, "cross_seed": 2 * group + 1, "co_rejected_plan_draws": retry,
                      "co_retry_rng_entropy": [group, 1810, retry] if retry else None,
                      "n_matched_rate_rolloff_options": len(options),
                      "conditioning": "matched set: at least one (Rs, alpha) with both an overlapping ASI placement and a free-gap unauthorized placement"}
            return (co, cross), source
    raise it.InfeasibleCarrierError("matched group has no plan admitting both placements after bounded draws")


def _matched_draw(group: int, plan, bandwidth: float) -> dict:
    """Group-level matched intervention, RNG namespace ``[group, 1840]``.

    One shared C/I_psd ~ U(4, 13) dB, one (Rs, alpha, modulation); ASI centre uniform among the
    overlap-feasible grid positions, unauthorized centre uniform inside a feasible free gap.
    """
    rng = np.random.default_rng([group, 1840])
    ci_psd = float(rng.uniform(*MATCHED_CI_RANGE))
    options = _matched_options(plan, bandwidth)
    if not options:
        raise it.InfeasibleCarrierError("matched plan lost joint feasibility")
    rs, alpha = options[int(rng.integers(len(options)))]
    mod = MODULATIONS[int(rng.integers(len(MODULATIONS)))]
    positions = overlap_positions(plan, bandwidth, rs, alpha)
    asi_f0 = float(positions[int(rng.integers(positions.size))])
    gaps = _gap_options(plan, bandwidth, rs, alpha)
    lo, hi, need = gaps[int(rng.integers(len(gaps)))]
    lo, hi = float(lo), float(hi)
    unauthorized_f0 = float(rng.uniform(lo + need / 2, hi - need / 2))
    mean_psd = sum(c.power for c in plan) / sum(c.symbol_rate for c in plan)
    natural = {name: bool(lo_ <= ci_psd <= hi_) for name, (lo_, hi_) in NATURAL_CI_PSD_RANGES.items()}
    return {"pair_id": f"{MATCHED_PROTOCOL}:{group}", "target_c_over_i_psd_db": ci_psd, "bin": matched_bin(ci_psd),
            "bin_name": MATCHED_BIN_NAMES[matched_bin(ci_psd)], "symbol_rate": rs, "alpha": alpha, "mod": mod,
            "requested_power": float(mean_psd * rs * 10 ** (-ci_psd / 10)),
            "power_reference": "total_planned_uplink (unit nominal load); PSD relative to the plan's mean PSD",
            "asi_f0": asi_f0, "unauthorized_f0": unauthorized_f0, "unauthorized_gap_hz": [lo, hi],
            "within_natural_range": natural, "n_rate_rolloff_options": len(options),
            "limitation": "controlled intervention: the two classes share level, carrier and plan by construction; "
                          "this conditional distribution does not represent natural operating levels"}


def _matched_event(label: str, matched: dict, plan, bandwidth: float):
    carrier = Carrier(f0=matched["asi_f0"] if label == "adjacent_satellite" else matched["unauthorized_f0"],
                      symbol_rate=matched["symbol_rate"], alpha=matched["alpha"], mod=matched["mod"],
                      power=matched["requested_power"])
    if label == "adjacent_satellite":
        callback, info = adjacent_satellite_uplink_at_level(plan, bandwidth, carrier, matched["target_c_over_i_psd_db"])
    elif label == "unauthorized":
        callback, info = it.modulated(carrier)
        info.update(psd_offset_db=-matched["target_c_over_i_psd_db"], c_over_i_psd_db=matched["target_c_over_i_psd_db"])
        if it.overlaps_plan(info["f_lo"], info["f_hi"], plan):
            raise it.InfeasibleCarrierError("matched unauthorized placement overlaps the plan")
    else:
        return None, {"kind": "clean", "injection_stage": "none"}
    info.update(injection_stage="uplink", power_reference="total_planned_uplink", matched=True)
    return callback, info


def prepare_matched_scene(label: str, group: int, config: B2Config | None = None) -> B2Scene:
    """Resolve one K17c matched variant; only groups of the frozen ``test-matched`` role are accepted."""
    config = B2Config() if config is None else config
    if not isinstance(config, B2Config):
        raise ValueError("config must be a B2Config")
    if label not in MATCHED_LABELS:
        raise ValueError(f"matched variants are {MATCHED_LABELS}")
    if role_for_group(group) != "test-matched":
        raise ValueError("matched variants are generated for frozen test-matched groups only")
    group = int(group)
    link = np.random.default_rng([group, 1801])
    paths = [ScenarioConfig(bandwidth=config.bandwidth, seed=2 * group + pol, n_snap=config.n_snap,
                            snap_interval=config.snap_interval, ibo_db=float(link.uniform(9, 13)),
                            cn_up_db=float(link.uniform(15, 30)), cn_dn_db=float(link.uniform(15, 30))) for pol in range(2)]
    nominal_ibo = [path.ibo_db for path in paths]
    plans, source = _matched_plans(group, config.bandwidth)
    active, dropped = _activity(group, plans, config, None)
    matched = _matched_draw(group, plans[0], config.bandwidth)
    cfg = _dual_config(paths, config.nominal_xpd_db, config)
    callback, event = _matched_event(label, matched, plans[0], config.bandwidth)
    consistency = int(dropped is not None)
    metadata = _metadata(MATCHED_PROTOCOL, label, group, "test-matched", event, consistency, nominal_ibo, source,
                         dropped, None)
    metadata.update(test_only=True, matched=matched)
    return B2Scene(cfg, plans, (callback, None), active, event, consistency, metadata)


def sample_matched_scene(label: str, group: int, config: B2Config | None = None, *,
                         calibration: ReceiverCalibration | None = None, keep_iq: bool = False) -> DualScenarioResult:
    """Simulate one matched variant; the matched intervention stays in metadata."""
    return _simulate(prepare_matched_scene(label, group, config), calibration, keep_iq)


def _test_parameters(group: int, family: str) -> np.random.Generator:
    """Separate RNG namespace for test-only families (P18 §4); the downlink ASI is the K17d exception."""
    return np.random.default_rng([group, 1830, TEST_FAMILIES.index(family)])


def _test_event(family: str, group: int, plan, bandwidth: float, active, config: B2Config):
    """Return (uplink callback, downlink callback, metadata) for one test-only family."""
    rng = _test_parameters(group, family)
    if family in ("pulsed", "intermittent_bursts", "wideband_noise"):
        # U1-dev/1 generators with a group-specific seed; C/I is relative to the unit planned uplink load.
        callback, info = unknown_interferer(family, bandwidth, int(rng.integers(0, 2**62)),
                                            n_snap=config.n_snap, snap_interval=config.snap_interval)
        info.update(injection_stage="uplink", power_reference="total_planned_uplink", test_only=True)
        return callback, None, info
    if family == "adjacent_satellite_downlink":
        # K17d control: scenario, plan, link AND C/I_psd matched to the known uplink ASI of the
        # same group, so the two differ only in injection point. This reuses the known event's
        # RNG stream deliberately (test groups only); the other families keep their own namespace.
        callback, info = adjacent_satellite_downlink(_parameters(group, "adjacent_satellite"), plan, bandwidth)
        info.update(paired_with_known="adjacent_satellite", pairing="same group RNG stream: identical geometry, C/I_psd, carrier and placement")
        return None, callback, info
    if family == "cid_overlay":
        callback, info = cid_overlay(rng, plan, bandwidth, active=list(active))
        info.update(test_only=True)
        return callback, None, info
    raise ValueError(f"test-only family must be one of {TEST_FAMILIES}")


def prepare_test_scene(family: str, group: int, config: B2Config | None = None) -> B2Scene:
    """Resolve one test-only variant sharing the group's plans, link, activity and streams.

    Only groups of the frozen ``test`` role are accepted; unknown families and the
    benign CID overlay never exist for train, val-select or val-calib groups.
    """
    config = B2Config() if config is None else config
    if not isinstance(config, B2Config):
        raise ValueError("config must be a B2Config")
    if family not in TEST_FAMILIES:
        raise ValueError(f"test-only family must be one of {TEST_FAMILIES}")
    if role_for_group(group) != "test":
        raise ValueError("test-only families are generated for frozen test-role groups only")
    group = int(group)
    paths, nominal_ibo, plans, source, active, dropped = _shared_scene(group, config, None)
    cfg = _dual_config(paths, config.nominal_xpd_db, config)
    uplink, downlink, event = _test_event(family, group, plans[0], config.bandwidth, active[0], config)
    consistency = int(dropped is not None)
    metadata = _metadata(TEST_PROTOCOL, family, group, "test", event, consistency, nominal_ibo, source, dropped, None)
    metadata.update(test_only=True, expected_decision=EXPECTED_DECISION[family],
                    family_group=("near" if family in NEAR_UNKNOWN else
                                  "equivalence_limited" if family in EQUIVALENCE_LIMITED_UNKNOWN else "benign"))
    return B2Scene(cfg, plans, (uplink, None), active, event, consistency, metadata, (downlink, None))


def sample_scene(label: str, group: int, config: B2Config | None = None, *,
                 missing_carrier: bool | None = None, calibration: ReceiverCalibration | None = None,
                 keep_iq: bool = False) -> DualScenarioResult:
    """Simulate a scene; hidden parameters stay in metadata, never extra inputs."""
    scene = prepare_scene(label, group, config, missing_carrier=missing_carrier)
    return _simulate(scene, calibration, keep_iq)


def _simulate(scene: B2Scene, calibration, keep_iq: bool) -> DualScenarioResult:
    kwargs = {}
    if any(event is not None for event in scene.downlink_interferers):
        kwargs["downlink_interferers"] = scene.downlink_interferers
    result = simulate_dual(scene.cfg, plans=scene.plans, interferers=scene.interferers,
                           active_carriers=scene.active_carriers, calibration=calibration, keep_iq=keep_iq, **kwargs)
    result.meta.update(scene.metadata)
    if kwargs:
        # The downlink event is scaled by the realized co feed power; with a missing carrier that
        # power is below the nominal load, so the effective level relative to the planned mean PSD
        # drifts by the dropped carrier's fraction. Record it instead of hiding it.
        active = result.meta["active_planned_power"][0]
        result.meta["event"] = {**result.meta["event"],
                                "feed_reference_power": result.meta["downlink_interference_reference_power"][0],
                                "active_planned_power_co": active,
                                "effective_c_over_i_psd_db": float(result.meta["event"]["c_over_i_psd_db"] - 10 * np.log10(active)),
                                "level_note": "nominal C/I_psd is relative to the unit planned load; the realized feed power scales the event"}
    return result


def sample_test_scene(family: str, group: int, config: B2Config | None = None, *,
                      calibration: ReceiverCalibration | None = None, keep_iq: bool = False) -> DualScenarioResult:
    """Simulate one test-only variant; event truth stays in metadata."""
    return _simulate(prepare_test_scene(family, group, config), calibration, keep_iq)

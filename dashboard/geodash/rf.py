"""RF Explorer adapter: simulator-generated scenes for development roles only.

The geosim generators accept test-role identifiers, so this module enforces the development-role rule
itself, before any generator is called: a group outside train, val-select or val-calib is refused and
nothing is simulated. The adapter reuses geosim unchanged. Units are carried with every array.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from .paths import ensure_import_paths

DEVELOPMENT_ROLES = ("train", "val-select", "val-calib")
SPECTRUM_UNIT = "dB(power/Hz), simulator-normalised (relative; not calibrated to dBm)"
UNITS = {
    "frequency": "MHz, offset from the transponder centre",
    "time": "s from the start of the scene",
    "spectrum": SPECTRUM_UNIT,
    "plan_mask": "dB relative to the plan's own peak, floored at -60 dB",
    "residual": "dB(power/Hz), same simulator-normalised scale as the spectrum",
    "carrier_power": "dB relative to the unit planned load (linear powers sum to 1)",
    "symbol_rate": "Msymbol/s",
    "bandwidth": "MHz",
}
FEEDS = ("co-pol", "cross-pol")


class DevelopmentRoleRefused(ValueError):
    """The group belongs to a role the RF Explorer does not show (test or test-matched)."""


def _protocol():
    ensure_import_paths()
    from geosim import b2_protocol
    return b2_protocol


def role_of(group: int) -> str:
    return _protocol().role_for_group(group)


def assert_development_group(group: int) -> str:
    role = role_of(group)
    if role not in DEVELOPMENT_ROLES:
        raise DevelopmentRoleRefused(
            f"group {group} belongs to the {role!r} role; the RF Explorer shows development roles only "
            f"({', '.join(DEVELOPMENT_ROLES)})")
    return role


def development_group_ids(role: str, limit: int = 20) -> list[int]:
    if role not in DEVELOPMENT_ROLES:
        raise DevelopmentRoleRefused(f"role {role!r} is not a development role")
    return list(_protocol().scenario_ids(role, limit))


def labels() -> tuple[str, ...]:
    return tuple(_protocol().LABELS)


def _plain(value: Any, depth: int = 0) -> Any:
    """JSON-safe copy of simulator metadata. Large arrays are summarised, never embedded."""
    if depth > 6:
        return "<nested>"
    if isinstance(value, dict):
        return {str(k): _plain(v, depth + 1) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        if len(value) > 32:
            return f"<list of {len(value)} items>"
        return [_plain(v, depth + 1) for v in value]
    if isinstance(value, np.ndarray):
        return f"<array shape {tuple(value.shape)} dtype {value.dtype}>"
    if isinstance(value, (np.floating, float)):
        return float(value) if np.isfinite(value) else None
    if isinstance(value, (np.integer, int)) and not isinstance(value, bool):
        return int(value)
    if isinstance(value, (str, bool)) or value is None:
        return value
    return f"<{type(value).__name__}>"


def _mean_psd_db(spec_db: np.ndarray) -> np.ndarray:
    """Average power over snapshots, then convert to dB. Averaging is done in linear power."""
    linear = np.power(10.0, np.asarray(spec_db, dtype=float) / 10.0)
    return 10.0 * np.log10(np.maximum(linear.mean(axis=-2), 1e-30))


@dataclass(frozen=True)
class CarrierRow:
    feed: str
    f0_mhz: float
    symbol_rate_msps: float
    occupied_bw_mhz: float
    alpha: float
    modulation: str
    power_db: float


@dataclass(frozen=True)
class SceneView:
    group: int
    role: str
    label: str
    freq_mhz: np.ndarray            # [512]
    time_s: np.ndarray              # [n_snap]
    spec_db: np.ndarray             # [2, n_snap, 512]
    mean_psd_db: np.ndarray         # [2, 512]
    plan_mask_db: np.ndarray        # [2, 512]
    carriers: tuple[CarrierRow, ...]
    residual_spec_db: np.ndarray    # [n_snap, 512], co-pol obs-cancel/1 residual
    residual_mean_psd_db: np.ndarray  # [512]
    cancellation: tuple[dict, ...]
    truth: dict                     # simulator truth from metadata; never a model input
    units: dict


def build_scene(group: int, label: str = "clean") -> SceneView:
    """Simulate one development-role scene. Refuses before any generation for other roles."""
    role = assert_development_group(group)
    if label not in labels():
        raise ValueError(f"label {label!r} is not one of {labels()}")
    ensure_import_paths()
    from geosim import b2_scenarios, cancellation, plan as planlib
    protocol = _protocol()
    scene = b2_scenarios.prepare_scene(label, group)
    result = b2_scenarios.sample_scene(label, group, keep_iq=True)
    if result.iq is None:
        raise RuntimeError("the simulator returned no IQ; the residual cannot be computed")
    residual = cancellation.cancel_planned_carriers(result.iq[0], scene.plans[0])
    spec_db = np.asarray(result.spec_db, dtype=float)
    n_snap = spec_db.shape[1]
    time_s = np.arange(n_snap) * protocol.B2Config().snap_interval
    rows = []
    for feed, carriers in zip(FEEDS, scene.plans):
        for c in carriers:
            rows.append(CarrierRow(feed, float(c.f0) / 1e6, float(c.symbol_rate) / 1e6,
                                   float(c.occupied_bw) / 1e6, float(c.alpha), str(c.mod),
                                   10.0 * float(np.log10(c.power))))
    masks = np.stack([np.asarray(planlib.plan_mask_db(list(p)), dtype=float) for p in scene.plans])
    residual_db = np.asarray(residual.residual_db, dtype=float)
    return SceneView(
        group=group, role=role, label=label,
        freq_mhz=np.asarray(planlib.monitor_freqs(), dtype=float) / 1e6,
        time_s=time_s, spec_db=spec_db, mean_psd_db=_mean_psd_db(spec_db), plan_mask_db=masks,
        carriers=tuple(rows), residual_spec_db=residual_db, residual_mean_psd_db=_mean_psd_db(residual_db),
        cancellation=tuple(_plain(c) for c in residual.carriers),
        truth={"event": _plain(result.meta.get("event")),
               "plan_consistency": _plain(scene.plan_consistency),
               "dropped_carrier": _plain(result.meta.get("dropped_carrier")),
               "note": "simulator truth; hidden parameters are never model inputs"},
        units=dict(UNITS),
    )


def carriers_frame(scene: SceneView) -> list[dict]:
    return [{"feed": r.feed, "centre (MHz)": round(r.f0_mhz, 3), "symbol rate (Msym/s)": round(r.symbol_rate_msps, 3),
             "occupied BW (MHz)": round(r.occupied_bw_mhz, 3), "roll-off": r.alpha, "modulation": r.modulation,
             "power (dB, unit load)": round(r.power_db, 2)} for r in scene.carriers]


__all__ = ["DEVELOPMENT_ROLES", "DevelopmentRoleRefused", "assert_development_group", "build_scene",
           "development_group_ids", "labels", "SceneView", "CarrierRow", "UNITS", "carriers_frame", "role_of"]

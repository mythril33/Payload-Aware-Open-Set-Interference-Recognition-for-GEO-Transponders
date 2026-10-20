"""Frozen B2/1 contracts and the first, known-observation artifact stage.

B2-base/1 contains physical observations only. It is not the completed five-
channel B2 benchmark: cancellation, final unknowns and matched tests follow.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from numbers import Integral
from pathlib import Path

import numpy as np

from .event_dataset import EventDatasetConfig, _strict_json, receiver_response

PROTOCOL = "B2/1"
BASE_PROTOCOL = "B2-base/1"
LABELS = ("clean", "cw", "swept_cw", "unauthorized", "overdrive", "cross_pol",
          "adjacent_satellite", "carrier_under_carrier")
BASE_ROLES = ("train", "val-select", "val-calib", "test")
ROLE_STARTS = {"train": 3_000_000, "val-select": 3_100_000, "val-calib": 3_150_000,
               "test": 3_200_000, "test-matched": 3_300_000}
ROLE_COUNTS = {"train": 1500, "val-select": 150, "val-calib": 150, "test": 500, "test-matched": 150}
NEAR_UNKNOWN = ("pulsed", "intermittent_bursts", "adjacent_satellite_downlink")
EQUIVALENCE_LIMITED_UNKNOWN = ("wideband_noise",)
BENIGN_TEST_FAMILIES = ("cid_overlay",)
PLAN_CONSISTENCY = ("consistent", "planned_carrier_missing")


def _integer(value, name, minimum, maximum):
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Integral) or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be an integer in [{minimum}, {maximum}]")
    return int(value)


def scenario_ids(role: str, limit: int | None = None) -> list[int]:
    """Return a prefix of one reserved role; pilot limits do not redefine it."""
    if not isinstance(role, str) or role not in ROLE_STARTS:
        raise ValueError(f"role must be one of {tuple(ROLE_STARTS)}")
    count = ROLE_COUNTS[role] if limit is None else _integer(limit, "limit", 1, ROLE_COUNTS[role])
    return list(range(ROLE_STARTS[role], ROLE_STARTS[role] + count))


def role_for_group(group: int) -> str:
    group = _integer(group, "scenario group", 0, 2**63 - 1)
    for role, start in ROLE_STARTS.items():
        if start <= group < start + ROLE_COUNTS[role]:
            return role
    raise ValueError("scenario group is outside the reserved B2/1 roles")


def require_base_group(group: int) -> str:
    role = role_for_group(group)
    if role not in BASE_ROLES:
        raise ValueError("test-matched is reserved for its separate controlled generator")
    return role


@dataclass(frozen=True)
class B2Config:
    bandwidth: float = 36e6
    n_snap: int = 128
    snap_interval: float = 0.01
    nominal_xpd_db: float = 30.0
    downlink_xpd_db: float = 35.0
    satellite_linewidth_hz: float = 100.0
    receiver_linewidth_hz: float = 50.0
    receiver_xpd_db: float = 25.0
    receiver_gain_db: tuple[float, float] = (1.5, -1.0)
    receiver_phase_rad: tuple[float, float] = (0.2, -0.4)
    receiver_coupling_phase_rad: float = 0.3
    calibration_seed: int = 424242
    calibration_samples: int = 64
    calibration_noise_std: float = 0.001
    drop_probability: float = 0.15

    def __post_init__(self):
        # Use the existing validated instrument contract, never its E1 sampler
        # or E1 calibration provenance. B2 uses its own independent pilot fit.
        names = ("bandwidth", "nominal_xpd_db", "downlink_xpd_db", "satellite_linewidth_hz",
                 "receiver_linewidth_hz", "receiver_xpd_db", "receiver_gain_db", "receiver_phase_rad",
                 "receiver_coupling_phase_rad", "calibration_seed", "calibration_samples", "calibration_noise_std")
        validated = EventDatasetConfig(n_seeds=2, **{name: getattr(self, name) for name in names})
        for name in names:
            object.__setattr__(self, name, getattr(validated, name))
        fixed = {"bandwidth": 36e6, "n_snap": 128, "snap_interval": 0.01,
                 "nominal_xpd_db": 30.0, "downlink_xpd_db": 35.0, "satellite_linewidth_hz": 100.0,
                 "receiver_linewidth_hz": 50.0, "receiver_xpd_db": 25.0,
                 "receiver_gain_db": (1.5, -1.0), "receiver_phase_rad": (0.2, -0.4),
                 "receiver_coupling_phase_rad": 0.3, "drop_probability": 0.15}
        object.__setattr__(self, "n_snap", _integer(self.n_snap, "n_snap", 128, 128))
        for name, expected in fixed.items():
            value = getattr(self, name)
            if isinstance(value, (bool, np.bool_)) or value != expected:
                raise ValueError(f"B2/1 fixes {name}={expected}; changed physics requires a separate evaluation protocol")

    def to_dict(self) -> dict:
        return json.loads(json.dumps(asdict(self), allow_nan=False))

    @classmethod
    def from_file(cls, path):
        raw = _strict_json(Path(path).read_text())
        if not isinstance(raw, dict):
            raise ValueError("B2 configuration must be a JSON object")
        try:
            return cls(**raw)
        except TypeError as error:
            raise ValueError(f"invalid B2 configuration: {error}") from error


def protocol_contract() -> dict:
    """JSON-safe role and family rules bound into each generation request."""
    return {"protocol": PROTOCOL, "base_protocol": BASE_PROTOCOL, "labels": list(LABELS),
            "role_starts": dict(ROLE_STARTS), "role_counts": dict(ROLE_COUNTS),
            "base_roles": list(BASE_ROLES), "near_unknown": list(NEAR_UNKNOWN),
            "equivalence_limited_unknown": list(EQUIVALENCE_LIMITED_UNKNOWN),
            "benign_test_families": list(BENIGN_TEST_FAMILIES),
            "plan_consistency": list(PLAN_CONSISTENCY), "benchmark_complete": False}

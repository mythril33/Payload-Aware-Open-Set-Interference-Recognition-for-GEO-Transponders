"""Privileged deterministic replay of B2 scenes and the frozen receiver front end (P28 §2, §5).

Everything that may know simulator truth lives here and nowhere else in the E4 path: the replay
re-creates a scene with the *source artifact's own* request (configuration, verified receiver
calibration, ``obs-cancel/1`` settings), keeps the calibrated IQ transiently, and checks that the
``none`` replay equals the stored shard before any counterfactual is built. The operator belief never
enters the simulator: ``replay_scene`` has no belief parameter and ``simulate_dual`` is never called
with one.

What leaves this module towards models is only ``ObservedInputs`` (calibrated co/cross PSD, the two
operator masks built from the belief, the observation-derived residual). The residual is produced by
the frozen canceller from the co-pol IQ and the co-pol belief alone. Raw IQ is read-only, never
stored and never serialized.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from geosim import b2_dataset as _known
from geosim import b2_matched_dataset as _matched
from geosim.b2_protocol import BASE_PROTOCOL, FEATURE_PROTOCOL, LABELS, B2Config
from geosim.b2_scenarios import MATCHED_LABELS, sample_matched_scene, sample_scene
from geosim.cancellation import CancellationConfig, cancel_planned_carriers
from geosim.event_dataset import _stored_carrier
from geosim.polarization import ReceiverCalibration

from .b2_a5_plan import OperatorPlans, PlanCorruption, rebuild_masks

STAGES = ("known", "matched")
PARITY_ATOL_DB = 0.125            # P28 §5: two float16 ulps at |x| in [64, 128); masks must be exact
EVENT_KEYS = ("f0", "symbol_rate", "alpha", "mod", "c_over_i_db")


class ReplayError(ValueError):
    """Replay, source verification or parity failed; no receiver-consistent claim may follow."""


class BudgetExceeded(ReplayError):
    """A bounded-execution cap would be exceeded; raised before the expensive work starts."""


@dataclass
class Budget:
    """Caps on physical replays and cancellation evaluations (P28 §9)."""

    max_replays: int
    max_cancellations: int
    replays: int = 0
    cancellations: int = 0

    def charge_replay(self):
        if self.replays + 1 > self.max_replays:
            raise BudgetExceeded(f"replay cap of {self.max_replays} would be exceeded")
        self.replays += 1

    def charge_cancellation(self):
        if self.cancellations + 1 > self.max_cancellations:
            raise BudgetExceeded(f"cancellation cap of {self.max_cancellations} would be exceeded")
        self.cancellations += 1


@dataclass(frozen=True)
class ReplaySource:
    """A verified artifact header plus everything needed to re-create its scenes."""

    root: Path
    stage: str
    protocol: str
    role: str
    labels: tuple
    groups: tuple
    groups_per_shard: int
    request: dict
    request_fingerprint: str
    config: B2Config
    calibration: ReceiverCalibration
    cancellation: CancellationConfig
    manifest: dict = field(repr=False)

    def label_index(self, name: str) -> int:
        return LABELS.index(name)

    def sample(self, label: str, group: int):
        if label not in self.labels:
            raise ReplayError(f"label {label!r} is not part of this {self.stage} artifact")
        if group not in self.groups:
            raise ReplayError(f"scenario group {group} is not part of this artifact's role {self.role}")
        sampler = sample_scene if self.stage == "known" else sample_matched_scene
        return sampler(label, int(group), self.config, calibration=self.calibration, keep_iq=True)

    def stored(self, group: int, label: str) -> "StoredObservation":
        """The verified stored row (arrays + metadata record) of one scene."""
        if group not in self.groups:
            raise ReplayError(f"scenario group {group} is not part of this artifact's role {self.role}")
        index = self.groups.index(group) // self.groups_per_shard
        if self.stage == "known":
            reader = _known.iter_b2_shards(self.root, self.role, [index])
        else:
            reader = _matched.iter_b2_matched_shards(self.root, [index])
        try:
            shard = next(iter(reader))
        except (ValueError, StopIteration) as error:
            raise ReplayError(f"stored shard {index} could not be verified: {error}") from error
        rows = np.flatnonzero((shard["seed"] == group) & (shard["label"] == self.label_index(label)))
        if len(rows) != 1:
            raise ReplayError("stored shard does not hold exactly one row for this scene")
        row = int(rows[0])
        return StoredObservation(int(group), label, shard["spec"][row].copy(), shard["mask"][row].copy(),
                                 shard["residual"][row].copy(), int(shard["plan_consistency"][row]),
                                 shard["meta"][row])

    def finalize_meta(self, meta: dict) -> dict:
        if self.stage == "known":
            meta.update(protocol=self.protocol, base_protocol=BASE_PROTOCOL)
        return meta


@dataclass(frozen=True, eq=False)
class StoredObservation:
    group: int
    label: str
    spec: np.ndarray            # [2,128,512] float16
    mask: np.ndarray            # [2,512] float16
    residual: np.ndarray        # [128,512] float16
    plan_consistency: int
    record: dict = field(repr=False)

    def original_plans(self) -> OperatorPlans:
        """The belief the artifact was generated with (stored operator plans)."""
        return OperatorPlans.from_records(self.record["plans"])

    def intervention_context(self) -> dict:
        """Whitelisted ``authorize_intruder`` description taken from the stored record (dataset layer)."""
        return _intervention_context(self.label, self.record.get("event") or {})


def _intervention_context(label: str, event: dict) -> dict:
    if label != "unauthorized" or any(key not in event for key in EVENT_KEYS):
        return {"label": label}
    return {"label": label, "intruder": {key: event[key] for key in EVENT_KEYS}}


def open_replay_source(root, stage: str = "known", role: str = "test") -> ReplaySource:
    """Verify an artifact header for replay; fails closed on every mismatch (P28 §5).

    Requires a stage with the stored fifth channel and ``obs-cancel/1`` settings (B2-feat/1 known, or a
    B2-match/1 artifact generated with cancellation). Reads descriptors and the calibration artifact only;
    shards are verified when they are read.
    """
    root = Path(root)
    if stage not in STAGES:
        raise ReplayError(f"stage must be one of {STAGES}")
    try:
        if stage == "known":
            manifest, config = _known._header(root)
            request = manifest["request"]
            protocol, _, cancellation, _ = _known._stage(request)
            if protocol != FEATURE_PROTOCOL or cancellation is None:
                raise ReplayError(f"replay requires the {FEATURE_PROTOCOL} stage (stored residual and cancellation settings)")
            if role not in manifest["roles"]:
                raise ReplayError(f"role {role!r} was not generated in this artifact")
            calibration, _ = _known._calibration(root, manifest["request_fingerprint"], protocol)
            labels, groups = tuple(LABELS), tuple(request["scenario_groups"][role])
        else:
            manifest, config = _matched._header(root)
            request = manifest["request"]
            cancellation, _ = _matched._cancellation_of(request)
            if cancellation is None:
                raise ReplayError("replay requires a matched artifact generated with the cancellation residual")
            role, protocol = _matched.ROLE, manifest["protocol"]
            calibration, _ = _matched._calibration(root, request)
            labels, groups = tuple(MATCHED_LABELS), tuple(request["scenario_groups"])
    except ReplayError:
        raise
    except _known._READ_ERRORS as error:
        raise ReplayError(f"invalid replay source {root}: {error}") from error
    current = (_known if stage == "known" else _matched)._generator_provenance()    # what that generator would record now
    if request["source_sha256"] != current:
        raise ReplayError("simulator source has changed since this artifact was generated; replay would not be "
                          "bit-comparable. Regenerate the artifact in a fresh directory (never relax this check)")
    if calibration.to_dict() != manifest["calibration"]:
        raise ReplayError("receiver calibration differs from the artifact manifest")
    if not isinstance(cancellation, CancellationConfig):
        raise ReplayError("cancellation settings are missing")
    return ReplaySource(root, stage, protocol, role, labels, groups, int(request["groups_per_shard"]), request,
                        manifest["request_fingerprint"], config, calibration, cancellation, manifest)


@dataclass(frozen=True, eq=False)
class SceneObservation:
    """One scene as the monitor sees it."""

    spec: np.ndarray            # [2,128,512] float16 calibrated co/cross PSD
    mask: np.ndarray            # [2,512] float16 operator masks (from the belief)
    residual: np.ndarray        # [128,512] float16 observation-derived co-pol residual


@dataclass(frozen=True, eq=False)
class ObservedInputs:
    """The only object handed to models: observable channels, nothing else."""

    spec: np.ndarray            # [N,2,128,512] float16
    mask: np.ndarray            # [N,2,512] float16
    residual: np.ndarray        # [N,128,512] float16

    def __post_init__(self):
        n = len(self.spec) if np.ndim(self.spec) else 0
        shapes = {"spec": (n, 2, 128, 512), "mask": (n, 2, 512), "residual": (n, 128, 512)}
        for name, shape in shapes.items():
            value = np.asarray(getattr(self, name))
            if n < 1 or value.shape != shape or value.dtype != np.float16 or not np.isfinite(value).all():
                raise ValueError(f"observed {name} must be a finite float16 array of shape {shape}")

    @classmethod
    def stack(cls, scenes) -> "ObservedInputs":
        scenes = list(scenes)
        if not scenes or any(not isinstance(item, SceneObservation) for item in scenes):
            raise ValueError("stack needs a nonempty list of SceneObservation")
        return cls(np.stack([item.spec for item in scenes]), np.stack([item.mask for item in scenes]),
                   np.stack([item.residual for item in scenes]))


@dataclass(frozen=True, eq=False)
class PhysicalReplay:
    """PRIVILEGED replay state: physical truth that must never reach a model or the canceller."""

    group: int
    label: str
    role: str
    iq: np.ndarray = field(repr=False)              # [2,128,4096] complex64, read-only, transient
    iq_sha256: str
    spec: np.ndarray = field(repr=False)            # [2,128,512] float16
    mask: np.ndarray = field(repr=False)            # [2,512] float16 (from the true plan)
    residual: np.ndarray = field(repr=False)        # [128,512] float16 (true plan, frozen canceller)
    plans: OperatorPlans                            # the original belief equals the generation plan
    plan_consistency: int
    event: dict = field(repr=False)
    active_carriers: tuple = field(repr=False)
    record: dict = field(repr=False)                # metadata exactly as the generator would store it

    def intervention_context(self) -> dict | None:
        """Whitelisted description for ``authorize_intruder`` (a controlled test intervention)."""
        return _intervention_context(self.label, self.event)

    def assert_iq_unchanged(self) -> None:
        if _iq_hash(self.iq) != self.iq_sha256:
            raise ReplayError("calibrated IQ changed after replay")


def _iq_hash(iq) -> str:
    return hashlib.sha256(np.ascontiguousarray(iq).tobytes()).hexdigest()


def _compare(name, replayed, stored, *, atol):
    a, b = np.asarray(replayed), np.asarray(stored)
    if a.shape != b.shape or a.dtype != b.dtype:
        raise ReplayError(f"{name}: replay shape/dtype differs from the stored shard")
    if not np.isfinite(a.astype(np.float32)).all():
        raise ReplayError(f"{name}: replay is not finite")
    diff = np.abs(a.astype(np.float32) - b.astype(np.float32))
    report = {"exact": bool(np.array_equal(a, b)), "max_abs_diff_db": float(diff.max()), "n_mismatch": int((a != b).sum()),
              "n_elements": int(a.size), "atol_db": atol}
    if report["max_abs_diff_db"] > atol:
        raise ReplayError(f"{name}: replay differs from the stored shard by {report['max_abs_diff_db']:.4f} dB "
                          f"(tolerance {atol}); no receiver-consistent claim is possible")
    return report


def _records_match(a, b, tolerance=1e-9):
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(_records_match(a[key], b[key], tolerance) for key in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_records_match(x, y, tolerance) for x, y in zip(a, b))
    if isinstance(a, bool) or isinstance(b, bool) or a is None or b is None:
        return a is b or a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return a == b or abs(a - b) <= tolerance * max(1.0, abs(a), abs(b))
    return a == b


def check_parity(replay: PhysicalReplay, stored: StoredObservation) -> dict:
    """The ``none`` replay against the stored shard row; raises ``ReplayError`` beyond the P28 tolerance."""
    if (replay.group, replay.label) != (stored.group, stored.label):
        raise ReplayError("replay and stored observation describe different scenes")
    report = {"spec": _compare("spec", replay.spec, stored.spec, atol=PARITY_ATOL_DB),
              "mask": _compare("mask", replay.mask, stored.mask, atol=0.0),
              "residual": _compare("residual", replay.residual, stored.residual, atol=PARITY_ATOL_DB)}
    if replay.plan_consistency != stored.plan_consistency:
        raise ReplayError("replay plan-consistency target differs from the stored shard")
    expected = json.loads(json.dumps(replay.record, allow_nan=False))
    if not _records_match(expected, stored.record):
        keys = sorted(key for key in set(expected) | set(stored.record)
                      if not _records_match(expected.get(key), stored.record.get(key)))
        raise ReplayError(f"replay metadata differs from the stored record in {keys}")
    report["metadata"] = {"matches": True, "scenario_id": replay.group, "label": replay.label,
                          "compared_keys": len(expected)}
    report["exact"] = all(report[key]["exact"] for key in ("spec", "mask", "residual"))
    return report


def replay_scene(source: ReplaySource, label: str, group: int, budget: Budget | None = None) -> PhysicalReplay:
    """Re-create one scene and its true-plan residual exactly as the generator did (no belief involved)."""
    if budget is not None:
        budget.charge_replay()
        budget.charge_cancellation()      # the generator's own residual call (parity reference)
    result = source.sample(label, int(group))
    if result.iq is None or np.shape(result.iq) != (2, source.config.n_snap, 4096):
        raise ReplayError("simulator did not return the calibrated two-polarization monitor IQ")
    iq = np.array(result.iq, copy=True)
    iq.setflags(write=False)
    plans = [[_stored_carrier(item, source.config.bandwidth) for item in plan] for plan in result.meta["plans"]]
    residual = _known._residual(result, plans, source.cancellation)       # the generator's own function
    record = source.finalize_meta(result.meta)
    return PhysicalReplay(int(group), label, source.role, iq, _iq_hash(iq), result.spec_db.astype(np.float16),
                          result.mask_db.astype(np.float16), residual, OperatorPlans.from_records(result.meta["plans"]),
                          int(result.meta["plan_consistency"]), dict(result.meta["event"]),
                          tuple(tuple(bool(v) for v in mask) for mask in result.meta["active_carriers"]), record)


class FrozenReceiver:
    """The frozen ``obs-cancel/1`` front end: co-pol IQ and co-pol belief in, residual PSD out."""

    def __init__(self, cancellation: CancellationConfig, budget: Budget | None = None):
        if not isinstance(cancellation, CancellationConfig):
            raise ReplayError("the receiver needs the source artifact's CancellationConfig")
        self.cancellation, self.budget, self.calls = cancellation, budget, 0

    def residual_db(self, co_iq, co_belief) -> np.ndarray:
        if self.budget is not None:
            self.budget.charge_cancellation()
        self.calls += 1
        try:
            outcome = cancel_planned_carriers(co_iq, list(co_belief), self.cancellation)
        except ValueError as error:
            raise ReplayError(f"frozen canceller rejected the operator belief: {error}") from error
        return outcome.residual_db.astype(np.float16)


def build_conditions(replay: PhysicalReplay, stored: StoredObservation, corruption: PlanCorruption,
                     receiver: FrozenReceiver) -> dict:
    """``original`` / ``MASK_ONLY`` / ``RECEIVER_CONSISTENT`` observations of one scene (P28 §2).

    The residual is recomputed only when the co-pol belief changed; otherwise it is provably the
    original one (the canceller never reads the cross belief or the cross IQ).
    """
    if not corruption.applied:
        raise ReplayError(f"corruption is {corruption.status}: {corruption.reason}")
    if corruption.scenario_id != replay.group or corruption.original != replay.plans:
        raise ReplayError("corruption was built for a different scene or original belief")
    replay.assert_iq_unchanged()
    masks = rebuild_masks(corruption.plans)
    recomputed = bool(corruption.co_changed)
    residual = receiver.residual_db(replay.iq[0], corruption.plans.co) if recomputed else replay.residual
    return {"original": SceneObservation(stored.spec, stored.mask, stored.residual),
            "MASK_ONLY": SceneObservation(stored.spec, masks, stored.residual),
            "RECEIVER_CONSISTENT": SceneObservation(replay.spec, masks, residual),
            "residual_recomputed": recomputed}


def reporting_flags(replay: PhysicalReplay, corruption: PlanCorruption) -> dict:
    """Privileged stratification flags for reporting only (never inputs)."""
    flags = {}
    for pol, name in enumerate(("co", "cross")):
        entry = corruption.descriptors.get(name) or {}
        removed = entry.get("removed_indices") or []
        if removed:
            flags[f"{name}_dropped_carrier_transmitted"] = bool(replay.active_carriers[pol][removed[0]])
    added = (corruption.descriptors.get("co") or {}).get("added") or []
    if corruption.perturbation == "phantom" and added and "f_lo" in replay.event:
        carrier = added[0]
        half = carrier["symbol_rate"] * (1 + carrier["alpha"]) / 2
        flags["phantom_overlaps_physical_event"] = bool(carrier["f0"] + half >= replay.event["f_lo"]
                                                       and carrier["f0"] - half <= replay.event["f_hi"])
    return flags


__all__ = ["Budget", "BudgetExceeded", "FrozenReceiver", "ObservedInputs", "PARITY_ATOL_DB", "PhysicalReplay",
           "ReplayError", "ReplaySource", "SceneObservation", "StoredObservation", "build_conditions",
           "check_parity", "open_replay_source", "replay_scene", "reporting_flags"]

"""Operator-belief plan corruption for the E4 A5 evaluation (P28, ``B2-A5-plan/1``).

The operator belief (``OperatorPlans``) is what the monitoring system is *told*; it is a
different object from the physical plan the simulator transmits. Corrupting it never touches
the physical scene: this module is pure (no simulator, no model, no IQ) and every result is a
deterministic function of ``(original belief, perturbation, scope, scenario_id)``.

Each polarization descriptor is transformed independently from its own plan with its own RNG
stream ``[scenario_id, 1850, perturbation_index, polarization]``; scope ``both`` is therefore
exactly the union of ``co_only`` and ``cross_only``. Corrupted descriptors are *not* renormalized
to unit power. Validity is decided by the frozen canceller's own plan check, so a belief the
frozen ``obs-cancel/1`` would reject is reported ``blocked`` with its message instead of being
repaired. The only hidden information that can enter is the optional, explicitly whitelisted
``allowed_intervention_context`` used by ``authorize_intruder``; it models a wrong operator claim
and is never a deployable receiver feature.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from numbers import Integral

import numpy as np

from geosim.cancellation import _validate_plan as _canceller_accepts
from geosim.interferers import InfeasibleCarrierError, random_unauthorized
from geosim.plan import plan_mask_db
from geosim.scenario import default_plan
from geosim.waveform import Carrier

from .artifacts import fingerprint
from .data import CORE_DB

CONTRACT = "B2-A5-plan/1"
PERTURBATIONS = ("none", "shift_plus", "shift_minus", "drop_one", "phantom", "authorize_intruder", "stale_plan")
SCOPES = ("co_only", "cross_only", "both")
POLARIZATIONS = ("co", "cross")
SHIFT_HZ = 0.5e6                     # P18 K17b / plan_shortcut value (about 2.7 monitor bins)
RNG_NAMESPACE = 1850                 # unused by the frozen namespaces 1801-1840 and by the simulator
BANDWIDTH = 36e6                     # fixed by B2/1
INTERVENTION_KEYS = ("label", "intruder")
INTRUDER_KEYS = ("f0", "symbol_rate", "alpha", "mod", "c_over_i_db")
STATUSES = ("applied", "not_applicable", "blocked")


@dataclass(frozen=True)
class OperatorPlans:
    """The operator's declared carriers per feed. Not a physical plan: no unit-power constraint."""

    co: tuple
    cross: tuple

    def __post_init__(self):
        for name in POLARIZATIONS:
            plan = getattr(self, name)
            if not isinstance(plan, (tuple, list)) or any(not isinstance(c, Carrier) for c in plan):
                raise ValueError(f"operator {name} descriptor must be a sequence of Carrier entries")
            object.__setattr__(self, name, tuple(plan))

    @classmethod
    def from_records(cls, records) -> "OperatorPlans":
        """From the stored ``meta['plans']`` layout: two lists of carrier dictionaries (co, cross)."""
        if not isinstance(records, (list, tuple)) or len(records) != 2:
            raise ValueError("operator plan records must hold one carrier list per polarization")
        return cls(*(tuple(Carrier(**dict(item)) for item in plan) for plan in records))

    def descriptor(self, polarization: int) -> tuple:
        return (self.co, self.cross)[polarization]

    def to_records(self) -> list:
        return [[asdict(c) for c in self.co], [asdict(c) for c in self.cross]]

    def identity(self) -> str:
        return fingerprint(self.to_records())


def validate_belief(plan) -> None:
    """Raise ``ValueError`` unless the frozen canceller and the mask pipeline accept this descriptor."""
    _canceller_accepts(plan)
    mask = plan_mask_db(list(plan))
    if not np.isfinite(mask).all() or not (mask > CORE_DB).any():
        raise ValueError("operator plan mask has no finite planned carrier core")


def rebuild_masks(plans: OperatorPlans) -> np.ndarray:
    """``[2, 512]`` float16 masks from the belief, the same convention as the stored masks."""
    return np.stack([plan_mask_db(list(plans.descriptor(pol))) for pol in range(2)]).astype(np.float16)


@dataclass(frozen=True)
class PlanCorruption:
    perturbation: str
    scope: str
    scenario_id: int
    status: str
    reason: str | None
    original: OperatorPlans
    plans: OperatorPlans | None           # None unless status == "applied"
    descriptors: dict = field(default_factory=dict)   # per polarization: changes and flags
    contract: str = CONTRACT

    @property
    def applied(self) -> bool:
        return self.status == "applied"

    @property
    def co_changed(self) -> bool:
        return self.applied and self.plans.co != self.original.co

    @property
    def cross_changed(self) -> bool:
        return self.applied and self.plans.cross != self.original.cross

    def to_dict(self) -> dict:
        return {"contract": self.contract, "perturbation": self.perturbation, "scope": self.scope,
                "scenario_id": self.scenario_id, "status": self.status, "reason": self.reason,
                "original_identity": self.original.identity(),
                "corrupted_identity": None if self.plans is None else self.plans.identity(),
                "co_changed": self.co_changed, "cross_changed": self.cross_changed,
                "descriptors": self.descriptors}


def _integer(value, name):
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Integral) or value < 0:
        raise ValueError(f"{name} must be a nonnegative integer")
    return int(value)


def _context(allowed):
    if allowed is None:
        return None
    if not isinstance(allowed, dict) or set(allowed) - set(INTERVENTION_KEYS):
        raise ValueError(f"allowed_intervention_context keys must be a subset of {INTERVENTION_KEYS}")
    intruder = allowed.get("intruder")
    if intruder is not None and (not isinstance(intruder, dict) or set(intruder) != set(INTRUDER_KEYS)):
        raise ValueError(f"intruder description must have exactly the keys {INTRUDER_KEYS}")
    return allowed


class _NotApplicable(Exception):
    pass


def _intruder_carrier(context) -> Carrier:
    if context is None or context.get("label") != "unauthorized" or context.get("intruder") is None:
        raise _NotApplicable("authorize_intruder applies to unauthorized scenes only (frozen A5 definition)")
    item = context["intruder"]
    return Carrier(f0=float(item["f0"]), symbol_rate=float(item["symbol_rate"]), alpha=float(item["alpha"]),
                   mod=str(item["mod"]), power=float(10 ** (-float(item["c_over_i_db"]) / 10)))


def _transform(perturbation, plan, scenario_id, polarization, context, bandwidth):
    """New descriptor and its change record for one polarization (raises ``_NotApplicable``)."""
    plan = tuple(plan)
    index = PERTURBATIONS.index(perturbation)
    rng = np.random.default_rng([scenario_id, RNG_NAMESPACE, index, polarization])
    record = {"removed_indices": [], "added": [], "frequency_changes_hz": []}
    if perturbation == "none":
        return plan, record
    if perturbation in ("shift_plus", "shift_minus"):
        step = SHIFT_HZ if perturbation == "shift_plus" else -SHIFT_HZ
        record["frequency_changes_hz"] = [[i, c.f0, c.f0 + step] for i, c in enumerate(plan)]
        return tuple(replace(c, f0=c.f0 + step) for c in plan), record
    if perturbation == "drop_one":
        if len(plan) < 2:
            raise _NotApplicable("descriptor has fewer than two carriers")
        drop = int(rng.integers(len(plan)))
        record["removed_indices"] = [drop]
        return tuple(c for i, c in enumerate(plan) if i != drop), record
    if perturbation == "phantom":
        try:
            phantom = random_unauthorized(rng, list(plan), bandwidth, 0.0)
        except InfeasibleCarrierError as error:
            raise _NotApplicable(f"no free gap for a phantom carrier: {error}") from error
        record["added"] = [asdict(phantom)]
        return plan + (phantom,), record
    if perturbation == "authorize_intruder":
        intruder = _intruder_carrier(context)
        record["added"] = [asdict(intruder)]
        return plan + (intruder,), record
    if perturbation == "stale_plan":
        stale = tuple(default_plan(2 * (scenario_id - 1) + polarization, bandwidth))
        if stale == plan:
            raise _NotApplicable("stale descriptor equals the current descriptor")
        record["replaced_by"] = {"source": f"default_plan(seed={2 * (scenario_id - 1) + polarization})",
                                 "n_carriers": len(stale)}
        return stale, record
    raise ValueError(f"unknown perturbation {perturbation!r}")


def _edge_flags(plan, bandwidth):
    return [i for i, c in enumerate(plan) if abs(c.f0) + c.occupied_bw / 2 > bandwidth / 2 + 1e-6]


def corrupt_operator_plan(original: OperatorPlans, *, perturbation: str, scope: str, scenario_id: int,
                          allowed_intervention_context: dict | None = None,
                          bandwidth: float = BANDWIDTH) -> PlanCorruption:
    """Counterfactual operator belief for one scene; never modifies the physical scene.

    ``scope`` selects which descriptors are transformed. The result is ``applied``,
    ``not_applicable`` (the perturbation is undefined for this scene or descriptor) or ``blocked``
    (the corrupted belief is rejected by the frozen validity check). Nothing is resampled.
    """
    if not isinstance(original, OperatorPlans):
        raise ValueError("original must be OperatorPlans")
    if perturbation not in PERTURBATIONS:
        raise ValueError(f"perturbation must be one of {PERTURBATIONS}")
    if scope not in SCOPES:
        raise ValueError(f"scope must be one of {SCOPES}")
    scenario_id = _integer(scenario_id, "scenario_id")
    context = _context(allowed_intervention_context)
    selected = {"co_only": (0,), "cross_only": (1,), "both": (0, 1)}[scope]
    new, descriptors = [original.co, original.cross], {}
    try:
        for pol in selected:
            plan, record = _transform(perturbation, original.descriptor(pol), scenario_id, pol, context, bandwidth)
            new[pol] = plan
            descriptors[POLARIZATIONS[pol]] = record
    except _NotApplicable as error:
        return PlanCorruption(perturbation, scope, scenario_id, "not_applicable", str(error), original, None,
                              {POLARIZATIONS[pol]: {} for pol in selected})
    result = OperatorPlans(*new)
    try:
        for pol, plan in enumerate((result.co, result.cross)):
            validate_belief(plan)
    except ValueError as error:
        return PlanCorruption(perturbation, scope, scenario_id, "blocked",
                              f"{POLARIZATIONS[pol]} belief rejected: {error}", original, None, descriptors)
    for pol in selected:
        descriptors[POLARIZATIONS[pol]]["exceeds_transponder_edge"] = _edge_flags(result.descriptor(pol), bandwidth)
        if perturbation == "authorize_intruder":
            descriptors[POLARIZATIONS[pol]]["declared_on_cross_feed"] = bool(pol == 1)
    return PlanCorruption(perturbation, scope, scenario_id, "applied", None, original, result, descriptors)


__all__ = ["CONTRACT", "PERTURBATIONS", "SCOPES", "OperatorPlans", "PlanCorruption", "corrupt_operator_plan",
           "rebuild_masks", "validate_belief"]

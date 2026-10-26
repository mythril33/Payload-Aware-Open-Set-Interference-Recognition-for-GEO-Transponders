"""Pre-test binding of the required nine canonical and six matched fits.

This artifact records a researcher's explicit scorer designation; it cannot
authenticate the researcher or grant a held-out read. Production readers must
use ``evaluation_step`` with the separately supplied authorization and E16/E18
external journal custody ports. Existing bounded-fixture readers are unchanged.
There is deliberately no default primary scorer: Mahalanobis remains a proposal.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
import json
import os
from pathlib import Path

from .artifacts import fingerprint
from .experiment import _sha256

CONTRACT = "B2-required-campaign/1"
ORDER = ("proposed-full", "c2-h3-dual")
ROSTERS = {"proposed-full": ("co", "dual", "dual_residual"),
           "c2-h3-dual": ("dual_planmask", "dual_noplan")}
SCORERS = ("msp", "energy", "mahalanobis")
_FIELDS = {"contract", "scope", "benchmark_complete", "authorizes_nothing",
           "primary_scorer", "designation", "evaluation_order", "optional_co_controls",
           "fits", "inventories", "common", "artifact_id"}


def _strict(path):
    from .b2_execution import _strict as read
    return read(path)


def _inventory(path, profile):
    """Revalidate trained objects without opening any dataset role."""
    raw = _strict(path)
    if not isinstance(raw, dict):
        raise ValueError("inventory must be a JSON object")
    if raw.get("contract") == "B2-production-training/1":
        from .b2_production_training import verify_inventory
        return verify_inventory(path, profile)
    from .b2_execution import _load_inventory
    return _load_inventory(path, profile)[0]


def _designation(primary_scorer, designation):
    if primary_scorer not in SCORERS:
        raise ValueError("an explicit researcher-designated primary scorer is required; no scorer is approved by default")
    fields = {"primary_scorer", "approved_by", "approved_at", "record"}
    if (not isinstance(designation, dict) or set(designation) != fields
            or designation["primary_scorer"] != primary_scorer
            or any(not isinstance(designation[key], str) or not designation[key].strip()
                   for key in fields)):
        raise ValueError("bind the explicit scorer designation, researcher, timestamp and approval record")
    try:
        at = datetime.fromisoformat(designation["approved_at"].replace("Z", "+00:00"))
        if at.tzinfo is None or at.utcoffset() is None:
            raise ValueError("timestamp lacks timezone")
    except (ValueError, OverflowError) as error:
        raise ValueError("designation timestamp must include a timezone") from error
    return dict(designation)


def _bindings(inventories):
    if not isinstance(inventories, dict) or set(inventories) != set(ORDER):
        raise ValueError("required campaign needs canonical nine plus matched dual six inventories")
    bindings = []
    reference = None
    scope = None
    for profile in ORDER:
        path = Path(inventories[profile]).resolve()
        before = _sha256(path)
        inventory = _inventory(path, profile)
        if before != _sha256(path):
            raise ValueError("inventory changed during campaign verification")
        if inventory.get("scope") not in ("BOUNDED_FIXTURE", "PRODUCTION"):
            raise ValueError("inventory scope is missing or incompatible")
        if scope is None:
            scope = inventory["scope"]
        if scope != inventory["scope"]:
            raise ValueError("campaign cannot mix fixture and production scopes")
        required = {(seed, view) for seed in (0, 1, 2) for view in ROSTERS[profile]}
        cells = inventory.get("cells", [])
        observed = {(cell["seed"], cell["view"]) for cell in cells}
        if (inventory.get("seeds") != [0, 1, 2] or observed != required
                or len(cells) != len(required)):
            raise ValueError("campaign requires exact seeds 0,1,2 and the complete nine/six cell rosters")
        common = inventory["common"]
        # Canonical and matched recipes differ in their declared plan settings.
        # Provenance, population, runtime and the actual compute budget must agree.
        budget_names = ("epochs", "batch", "width", "time_pool", "lr", "weight_decay", "augment", "center_loss_weight")
        training = common["config"]["training"]
        identity = {key: common[key] for key in ("source", "runtime", "data_identity", "roles")}
        identity["training_budget"] = {key: training[key] for key in budget_names}
        if reference is None:
            reference = identity
        if reference != identity:
            raise ValueError("campaign inventories mix source, runtime, data, roles or training budgets")
        bindings.append({"profile": profile, "path": str(path), "sha256": before,
                         "artifact_id": inventory["artifact_id"], "fits": len(cells)})
    return bindings, reference, scope


def freeze_campaign(inventories, out, *, primary_scorer=None, designation=None):
    """Publish a complete, immutable 15-fit binding before any held-out read.

    ``designation`` is a bound record reference, not a credential. Its real
    authenticity and held-out authorization are checked by the external
    authority when ``evaluation_step`` is entered.
    """
    designation = _designation(primary_scorer, designation)
    bindings, common, scope = _bindings(inventories)
    path = Path(out).resolve()
    for item in bindings:
        source = Path(item["path"])
        if path == source or path in source.parents or source in path.parents:
            raise ValueError("campaign output must be separate from input inventories")
    value = {"contract": CONTRACT, "scope": scope, "benchmark_complete": False,
             "authorizes_nothing": True, "primary_scorer": primary_scorer,
             "designation": designation, "evaluation_order": list(ORDER),
             "optional_co_controls": "DEFERRED_BEFORE_HELDOUT", "fits": 15,
             "inventories": bindings, "common": common}
    value["artifact_id"] = fingerprint(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    # A campaign must never overwrite an earlier primary or sequence choice.
    # File plus parent fsync makes publication durable on the selected filesystem.
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    try:
        raw = (json.dumps(value, indent=2, allow_nan=False) + "\n").encode()
        with os.fdopen(fd, "wb", closefd=False) as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(fd)
    finally:
        os.close(fd)
    parent = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(parent)
    finally:
        os.close(parent)
    return value


def verify_campaign(path):
    """Verify both frozen inventories and all their models before test access."""
    value = _strict(path)
    if (not isinstance(value, dict) or set(value) != _FIELDS
            or value["contract"] != CONTRACT or value["benchmark_complete"] is not False
            or value["authorizes_nothing"] is not True
            or value["evaluation_order"] != list(ORDER)
            or value["optional_co_controls"] != "DEFERRED_BEFORE_HELDOUT" or value["fits"] != 15
            or value["artifact_id"] != fingerprint({key: item for key, item in value.items() if key != "artifact_id"})):
        raise ValueError("campaign binding is incomplete or modified")
    _designation(value["primary_scorer"], value["designation"])
    entries = value["inventories"]
    if (not isinstance(entries, list) or len(entries) != len(ORDER)
            or [item.get("profile") for item in entries] != list(ORDER)):
        raise ValueError("campaign inventory sequence differs from its frozen order")
    bindings, common, scope = _bindings({item["profile"]: item["path"] for item in entries})
    if bindings != entries or common != value["common"] or scope != value["scope"]:
        raise ValueError("campaign inventory, source, runtime or population changed")
    return value


@contextmanager
def evaluation_step(path, profile, *, authorization, journal):
    """Admit one future production read in the predeclared order.

    The authority port must raise on anything except a separately approved
    ``heldout`` request bound to this campaign's exact artifact ID. The journal
    port must supply ``locked()`` (exclusive custody for the whole read),
    ``read_verified()`` (verified E16 entries including E18's
    independent anchor) and ``append(kind, data)`` (durably append and anchor).
    No default authority/custody is supplied. Neither a local boolean nor the
    designation record grants access. A failed/partial read is consumed and
    cannot be silently retried. This function opens no dataset itself.
    """
    campaign = verify_campaign(path)
    if campaign["scope"] != "PRODUCTION":
        raise ValueError("campaign production admission rejects bounded-fixture artifacts")
    authorization.require("heldout", campaign["artifact_id"])
    with journal.locked():
        events = [entry["data"] for entry in journal.read_verified()
                  if entry.get("data", {}).get("campaign_id") == campaign["artifact_id"]]
        expected = []
        for previous in ORDER:
            expected.extend(({"campaign_id": campaign["artifact_id"], "event": "evaluation_started", "profile": previous},
                             {"campaign_id": campaign["artifact_id"], "event": "evaluation_completed", "profile": previous}))
        if len(events) % 2 or events != expected[:len(events)]:
            raise ValueError("campaign has a partial, repeated or reordered held-out read; external recovery required")
        position = len(events) // 2
        if position >= len(ORDER) or profile != ORDER[position]:
            raise ValueError("held-out evaluation must run canonical then matched dual once in the frozen order")
        claim = {"campaign_id": campaign["artifact_id"], "event": "evaluation_started", "profile": profile}
        journal.append("boundary_check", claim)
        # Revalidate after recording the claim, immediately before the reader runs.
        # Failure preserves the started entry; no retry or choice change is inferred.
        if verify_campaign(path) != campaign:
            raise ValueError("campaign changed after authorization; held-out read refused")
        yield campaign, campaign["inventories"][position]
        journal.append("boundary_check", {**claim, "event": "evaluation_completed"})

"""B2 K17d identity derivation and validation (E10): metadata only, fail closed.

The approved K17d reporting rule (docs/plan/B2_E9_SCIENTIFIC_DECISION_APPROVAL_2026-10-24.md) uses the
500 headline test-role scenario groups, a predeclared subrow of 35 co-feed (``pol == 0``) missing-carrier
groups and a 465-group sensitivity row that excludes them. The identities must be derived from the frozen
generation metadata before any test observation is opened, and never from recognition outcomes.

This module is pure. ``derive`` and ``cross_check_audit`` take plain metadata mappings and never read a
file, observation array, prediction, score or metric. Each record must carry exactly the fields in
``RECORD_KEYS``; any other key (for example a prediction, a score or an accuracy) is refused, so outcome data
cannot enter the derivation by accident. ``derive_from_generator`` is the only function that touches the
generator, and it calls ``prepare_scene``, which resolves plans, link and carrier activity from the group
seeds without synthesising a waveform.
"""
from __future__ import annotations

import hashlib
import json
from numbers import Integral

from . import b2_protocol as P

SCHEMA = "B2-K17d-identity/1"
ROLE = "test"
HEADLINE_GROUPS = 500
CO_FEED_GROUPS = 35
SENSITIVITY_GROUPS = 465
CO_FEED_POLARIZATION = 0
CROSS_FEED_POLARIZATION = 1
TEST_IDS = range(P.ROLE_STARTS[ROLE], P.ROLE_STARTS[ROLE] + P.ROLE_COUNTS[ROLE])
PREDICATE = "dropped_carrier is not None and dropped_carrier['polarization'] == 0 (co feed); natural draw only"
RECORD_KEYS = ("scenario_id", "role", "protocol", "plan_consistency", "dropped_carrier", "missing_carrier_override")
DROP_KEYS = ("polarization", "index")


class K17dError(ValueError):
    """Any input that cannot yield the approved 500 / 35 / 465 identities. The derivation refuses instead of guessing."""


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def sha256_of(value) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def _integer(value, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise K17dError(f"{name} must be an integer, not {type(value).__name__}")
    return int(value)


def _check_record(record, position: int):
    if not isinstance(record, dict):
        raise K17dError(f"record {position} is not a mapping")
    keys = set(record)
    missing = sorted(set(RECORD_KEYS) - keys)
    unexpected = sorted(keys - set(RECORD_KEYS))
    if missing:
        raise K17dError(f"record {position} lacks required fields {missing}")
    if unexpected:
        raise K17dError(f"record {position} carries fields outside the metadata contract {unexpected}")
    group = _integer(record["scenario_id"], "scenario_id")
    if group not in TEST_IDS:
        raise K17dError(f"scenario {group} lies outside the frozen test range {TEST_IDS.start}-{TEST_IDS.stop - 1}")
    if record["role"] != ROLE:
        raise K17dError(f"scenario {group} has role {record['role']!r}; K17d is defined on the test role only")
    if record["protocol"] != P.BASE_PROTOCOL:
        raise K17dError(f"scenario {group} carries protocol {record['protocol']!r}; expected {P.BASE_PROTOCOL!r}")
    if record["missing_carrier_override"] is not None:
        raise K17dError(f"scenario {group} carries a diagnostic missing_carrier_override; K17d uses natural draws only")
    dropped = record["dropped_carrier"]
    if dropped is None:
        consistency = 0
    else:
        if not isinstance(dropped, dict) or tuple(sorted(dropped)) != tuple(sorted(DROP_KEYS)):
            raise K17dError(f"scenario {group} has a malformed dropped_carrier {dropped!r}")
        polarization = _integer(dropped["polarization"], "dropped_carrier.polarization")
        if polarization not in (CO_FEED_POLARIZATION, CROSS_FEED_POLARIZATION):
            raise K17dError(f"scenario {group} drops polarization {polarization}; expected 0 (co) or 1 (cross)")
        index = _integer(dropped["index"], "dropped_carrier.index")
        if index < 0:
            raise K17dError(f"scenario {group} drops a negative carrier index")
        consistency = 1
    if _integer(record["plan_consistency"], "plan_consistency") != consistency:
        raise K17dError(f"scenario {group}: plan_consistency disagrees with dropped_carrier")
    return group, dropped


def derive(records, *, expected_headline: int = HEADLINE_GROUPS) -> dict:
    """Derive the headline, co-feed and sensitivity identity lists from frozen scene metadata records."""
    if not isinstance(records, (list, tuple)):
        raise K17dError("records must be a list of metadata mappings")
    if len(records) != expected_headline:
        raise K17dError(f"expected {expected_headline} headline groups, got {len(records)}")
    table = {}
    for position, record in enumerate(records):
        group, dropped = _check_record(record, position)
        if group in table:
            raise K17dError(f"duplicate scenario {group}")
        table[group] = dropped
    ids = sorted(table)
    co = sorted(g for g, d in table.items() if d is not None and d["polarization"] == CO_FEED_POLARIZATION)
    cross = sorted(g for g, d in table.items() if d is not None and d["polarization"] == CROSS_FEED_POLARIZATION)
    if len(co) != CO_FEED_GROUPS:
        raise K17dError(f"expected {CO_FEED_GROUPS} co-feed missing-carrier groups, derived {len(co)}")
    co_set = set(co)
    sensitivity = [g for g in ids if g not in co_set]
    if len(sensitivity) != SENSITIVITY_GROUPS:
        raise K17dError(f"expected {SENSITIVITY_GROUPS} sensitivity groups, derived {len(sensitivity)}")
    if len(co) + len(sensitivity) != expected_headline or set(co) | set(sensitivity) != set(ids) or co_set & set(sensitivity):
        raise K17dError("headline, co-feed and sensitivity sets are not an exact partition")
    metadata = [{"scenario_id": g, "dropped_carrier": table[g]} for g in ids]
    return {
        "schema": SCHEMA,
        "role": ROLE,
        "predicate": PREDICATE,
        "counts": {"headline": len(ids), "co_feed_missing": len(co), "sensitivity": len(sensitivity),
                   "cross_feed_missing": len(cross), "missing_total": len(co) + len(cross)},
        "headline_ids": ids,
        "co_feed_missing_ids": co,
        "sensitivity_ids": sensitivity,
        "cross_feed_missing_ids": cross,
        "fingerprints": {"headline_ids": sha256_of(ids), "co_feed_missing_ids": sha256_of(co),
                         "sensitivity_ids": sha256_of(sensitivity), "scene_metadata": sha256_of(metadata)},
    }


def cross_check_audit(derived: dict, audit: dict) -> dict:
    """Compare a derivation with a committed audit document (docs/results/k17d_drift_audit.json format).

    Fails closed unless the audit's group set, polarization of each group and missing-group count agree exactly.
    """
    if not isinstance(audit, dict) or not isinstance(audit.get("rows"), list):
        raise K17dError("audit document must carry a rows list")
    if audit.get("n_test_groups") != HEADLINE_GROUPS:
        raise K17dError(f"audit n_test_groups is {audit.get('n_test_groups')!r}, expected {HEADLINE_GROUPS}")
    audit_pol = {}
    for row in audit["rows"]:
        group = _integer(row.get("group"), "audit group")
        pol = _integer(row.get("pol"), "audit pol")
        if group in audit_pol:
            raise K17dError(f"audit lists group {group} twice")
        audit_pol[group] = pol
    derived_missing = {g: CO_FEED_POLARIZATION for g in derived["co_feed_missing_ids"]}
    derived_missing.update({g: CROSS_FEED_POLARIZATION for g in derived["cross_feed_missing_ids"]})
    only_derived = sorted(set(derived_missing) - set(audit_pol))
    only_audit = sorted(set(audit_pol) - set(derived_missing))
    pol_mismatch = sorted(g for g in set(derived_missing) & set(audit_pol) if derived_missing[g] != audit_pol[g])
    report = {
        "schema": SCHEMA + "/audit-cross-check",
        "audit_rows": len(audit_pol),
        "audit_co_feed": sum(1 for p in audit_pol.values() if p == CO_FEED_POLARIZATION),
        "audit_cross_feed": sum(1 for p in audit_pol.values() if p == CROSS_FEED_POLARIZATION),
        "only_in_derived": only_derived,
        "only_in_audit": only_audit,
        "polarization_mismatch": pol_mismatch,
        "agrees": not (only_derived or only_audit or pol_mismatch),
    }
    if not report["agrees"]:
        raise K17dError(f"derivation disagrees with the audit: {len(only_derived)} derived-only, "
                        f"{len(only_audit)} audit-only, {len(pol_mismatch)} polarization mismatches")
    return report


def scene_metadata(group: int, config=None) -> dict:
    """Metadata record of one test-role scene, resolved without a waveform (no simulate_dual call)."""
    from . import b2_scenarios
    scene = b2_scenarios.prepare_scene("clean", _integer(group, "scenario_id"), config)
    return {key: scene.metadata[key] for key in RECORD_KEYS}


def derive_from_generator(groups=None, config=None) -> dict:
    """Derive the K17d identities from the frozen generator's scene metadata for the given test groups."""
    chosen = list(TEST_IDS) if groups is None else list(groups)
    return derive([scene_metadata(group, config) for group in chosen])

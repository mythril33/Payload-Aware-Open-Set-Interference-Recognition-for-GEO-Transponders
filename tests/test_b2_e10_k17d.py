"""E10 K17d identity validator (metadata only, fail closed).

Synthetic metadata fixtures only: no observation, prediction, score or waveform is created or read. The generator
path is exercised only through scene metadata, with ``simulate_dual`` patched to fail so that any waveform
synthesis is a test failure.
"""
import ast
import copy
import json
from pathlib import Path

import pytest

from geosim import b2_k17d as K
from geosim import b2_protocol as P
from geosim import b2_scenarios

ROOT = Path(__file__).parents[1]
TEST_IDS = list(K.TEST_IDS)


def record(group, *, drop=None, consistent=None, override=None, role="test", protocol=P.BASE_PROTOCOL):
    return {"scenario_id": group, "role": role, "protocol": protocol,
            "plan_consistency": (0 if drop is None else 1) if consistent is None else consistent,
            "dropped_carrier": drop, "missing_carrier_override": override}


def fixture_records(co=35, cross=43, total=500):
    """Synthetic 500-group test role: the first ``co`` groups drop a co carrier, the next ``cross`` a cross carrier."""
    records = []
    for position, group in enumerate(TEST_IDS[:total]):
        if position < co:
            drop = {"polarization": 0, "index": position % 5}
        elif position < co + cross:
            drop = {"polarization": 1, "index": position % 7}
        else:
            drop = None
        records.append(record(group, drop=drop))
    return records


def fixture_audit(records):
    rows = [{"group": r["scenario_id"], "pol": r["dropped_carrier"]["polarization"]}
            for r in records if r["dropped_carrier"] is not None]
    return {"n_test_groups": 500, "n_missing_groups": len(rows), "rows": rows}


# ---- derivation: exact arithmetic and canonical output -------------------------------------------

def test_derives_exact_500_35_465_partition():
    derived = K.derive(fixture_records())
    assert derived["counts"] == {"headline": 500, "co_feed_missing": 35, "sensitivity": 465,
                                 "cross_feed_missing": 43, "missing_total": 78}
    assert derived["headline_ids"] == sorted(TEST_IDS)
    assert set(derived["co_feed_missing_ids"]) | set(derived["sensitivity_ids"]) == set(TEST_IDS)
    assert not set(derived["co_feed_missing_ids"]) & set(derived["sensitivity_ids"])
    assert derived["co_feed_missing_ids"] == sorted(derived["co_feed_missing_ids"])
    assert derived["sensitivity_ids"] == sorted(derived["sensitivity_ids"])


def test_output_is_canonical_and_independent_of_input_order():
    records = fixture_records()
    shuffled = list(reversed(records))
    first, second = K.derive(records), K.derive(shuffled)
    assert first == second
    assert first["fingerprints"] == second["fingerprints"]
    assert K.canonical(first)  # strict JSON, no NaN or infinity
    json.loads(K.canonical(first))


def test_fingerprints_detect_a_changed_identity_with_unchanged_counts():
    records = fixture_records()
    baseline = K.derive(records)
    swapped = copy.deepcopy(records)
    # Move the co-feed drop from group 0 to group 40: still 35 co-feed groups, different identities.
    swapped[0]["dropped_carrier"], swapped[0]["plan_consistency"] = None, 0
    swapped[40]["dropped_carrier"], swapped[40]["plan_consistency"] = {"polarization": 0, "index": 1}, 1
    changed = K.derive(swapped)
    assert changed["counts"]["co_feed_missing"] == 35
    assert changed["fingerprints"]["co_feed_missing_ids"] != baseline["fingerprints"]["co_feed_missing_ids"]
    assert changed["fingerprints"]["scene_metadata"] != baseline["fingerprints"]["scene_metadata"]


def test_cross_feed_drops_are_not_counted_as_co_feed():
    derived = K.derive(fixture_records(co=35, cross=43))
    assert set(derived["cross_feed_missing_ids"]).isdisjoint(derived["co_feed_missing_ids"])
    assert all(g in derived["sensitivity_ids"] for g in derived["cross_feed_missing_ids"])


# ---- fail closed: arithmetic and identity -----------------------------------------------------------

@pytest.mark.parametrize("records", [
    fixture_records()[:-1],                       # 499 groups
    fixture_records() + [record(TEST_IDS[0])],    # 501 groups, duplicate included
], ids=["short", "long"])
def test_group_count_must_be_exactly_500(records):
    with pytest.raises(K.K17dError, match="headline groups"):
        K.derive(records)


def test_duplicate_scenario_is_refused():
    records = fixture_records()
    records[1] = copy.deepcopy(records[0])
    with pytest.raises(K.K17dError, match="duplicate"):
        K.derive(records)


def test_co_feed_count_must_be_exactly_35_not_34_or_36():
    with pytest.raises(K.K17dError, match="expected 35"):
        K.derive(fixture_records(co=34, cross=44))
    with pytest.raises(K.K17dError, match="expected 35"):
        K.derive(fixture_records(co=36, cross=42))


def test_sensitivity_count_is_checked_even_when_headline_and_co_feed_are_consistent(monkeypatch):
    monkeypatch.setattr(K, "SENSITIVITY_GROUPS", 464)
    with pytest.raises(K.K17dError, match="sensitivity"):
        K.derive(fixture_records())


# ---- fail closed: metadata contract ------------------------------------------------------------------

@pytest.mark.parametrize("mutate, pattern", [
    (lambda r: r.update(scenario_id=3199999), "outside the frozen test range"),
    (lambda r: r.update(scenario_id=3200500), "outside the frozen test range"),
    (lambda r: r.update(scenario_id=True), "must be an integer"),
    (lambda r: r.update(scenario_id=3200000.0), "must be an integer"),
    (lambda r: r.update(role="val-calib"), "test role only"),
    (lambda r: r.update(protocol="B2-test/1"), "expected 'B2-base/1'"),
    (lambda r: r.update(missing_carrier_override=True), "diagnostic missing_carrier_override"),
    (lambda r: r.update(missing_carrier_override=False), "diagnostic missing_carrier_override"),
    (lambda r: r.update(plan_consistency=True), "must be an integer"),
    (lambda r: r.update(plan_consistency=0), "disagrees with dropped_carrier"),
    (lambda r: r.update(dropped_carrier={"polarization": 2, "index": 0}, plan_consistency=1), "expected 0"),
    (lambda r: r.update(dropped_carrier={"polarization": 0, "index": -1}, plan_consistency=1), "negative"),
    (lambda r: r.update(dropped_carrier={"polarization": 0}, plan_consistency=1), "malformed"),
    (lambda r: r.update(dropped_carrier="pol0", plan_consistency=1), "malformed"),
    (lambda r: r.update(accuracy=0.125), "outside the metadata contract"),
    (lambda r: r.update(prediction=3), "outside the metadata contract"),
    (lambda r: r.update(unknown_score=0.7), "outside the metadata contract"),
    (lambda r: r.pop("protocol"), "lacks required fields"),
    (lambda r: r.pop("missing_carrier_override"), "lacks required fields"),
])
def test_malformed_or_outcome_bearing_metadata_is_refused(mutate, pattern):
    records = fixture_records()
    mutate(records[5])
    with pytest.raises(K.K17dError, match=pattern):
        K.derive(records)


def test_non_mapping_record_is_refused():
    records = fixture_records()
    records[3] = ["not", "a", "mapping"]
    with pytest.raises(K.K17dError, match="not a mapping"):
        K.derive(records)


def test_records_must_be_a_sequence():
    with pytest.raises(K.K17dError, match="list of metadata"):
        K.derive({"not": "a list"})


# ---- audit cross-check (committed evidence, not a source of truth) -----------------------------------

def test_cross_check_agrees_with_an_identical_audit():
    records = fixture_records()
    report = K.cross_check_audit(K.derive(records), fixture_audit(records))
    assert report["agrees"] is True
    assert report["audit_co_feed"] == 35 and report["audit_cross_feed"] == 43


def test_cross_check_refuses_an_audit_missing_one_group():
    records = fixture_records()
    audit = fixture_audit(records)
    audit["rows"] = audit["rows"][:-1]
    with pytest.raises(K.K17dError, match="only_in_derived|disagrees"):
        K.cross_check_audit(K.derive(records), audit)


def test_cross_check_refuses_a_polarization_mismatch():
    records = fixture_records()
    audit = fixture_audit(records)
    audit["rows"][0]["pol"] = 1
    with pytest.raises(K.K17dError, match="polarization mismatches"):
        K.cross_check_audit(K.derive(records), audit)


def test_cross_check_refuses_wrong_test_group_total_and_duplicate_rows():
    records = fixture_records()
    audit = fixture_audit(records)
    bad_total = dict(audit, n_test_groups=499)
    with pytest.raises(K.K17dError, match="n_test_groups"):
        K.cross_check_audit(K.derive(records), bad_total)
    duplicated = dict(audit, rows=audit["rows"] + [audit["rows"][0]])
    with pytest.raises(K.K17dError, match="twice"):
        K.cross_check_audit(K.derive(records), duplicated)


# ---- generator adapter: metadata only ----------------------------------------------------------------

def test_scene_metadata_path_never_reaches_waveform_synthesis(monkeypatch):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("waveform synthesis reached from the K17d metadata path")

    monkeypatch.setattr(b2_scenarios, "simulate_dual", forbidden)
    metadata = K.scene_metadata(TEST_IDS[0])
    assert set(metadata) == set(K.RECORD_KEYS)
    assert metadata["scenario_id"] == TEST_IDS[0] and metadata["role"] == "test"
    assert metadata["missing_carrier_override"] is None


def test_a_train_group_is_refused_by_the_validator_not_the_adapter(monkeypatch):
    monkeypatch.setattr(b2_scenarios, "simulate_dual", lambda *a, **k: pytest.fail("simulated"))
    metadata = K.scene_metadata(3000000)          # resolves (train is a base role) but is out of scope for K17d
    assert metadata["role"] == "train"
    with pytest.raises(K.K17dError, match="outside the frozen test range"):
        K._check_record(metadata, 0)


def test_derive_from_generator_uses_only_the_supplied_subset(monkeypatch):
    seen = []

    class FakeScene:
        def __init__(self, group):
            drop = {"polarization": 0, "index": 0} if group < TEST_IDS[0] + 35 else None
            self.metadata = {"scenario_id": group, "role": "test", "protocol": P.BASE_PROTOCOL,
                             "plan_consistency": 0 if drop is None else 1, "dropped_carrier": drop,
                             "missing_carrier_override": None, "label": "clean", "ibo_db": 11.0}

    def fake_prepare(label, group, config=None):
        seen.append(group)
        return FakeScene(group)

    monkeypatch.setattr(b2_scenarios, "prepare_scene", fake_prepare)
    monkeypatch.setattr(b2_scenarios, "simulate_dual", lambda *a, **k: pytest.fail("simulated"))
    with pytest.raises(K.K17dError, match="expected 500"):
        K.derive_from_generator(TEST_IDS[:10])
    assert seen == TEST_IDS[:10]


def test_validator_module_has_no_model_metric_or_observation_imports():
    tree = ast.parse((ROOT / "src" / "geosim" / "b2_k17d.py").read_text())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported.add(("." * node.level) + (node.module or ""))
        elif isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
    # Relative `from . import x` appears as the bare "." module name; the set is the whole allow-list.
    assert imported <= {".", "__future__", "hashlib", "json", "numbers"}
    for banned in ("torch", "geoml", "metrics", "openset", "calibration", "predict", "numpy"):
        assert not any(banned in name for name in imported)

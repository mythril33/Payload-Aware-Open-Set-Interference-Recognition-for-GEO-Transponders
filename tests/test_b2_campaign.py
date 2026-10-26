"""Pre-test campaign binding over fabricated inventory metadata; no held-out data."""
from contextlib import contextmanager
from copy import deepcopy
import json

import pytest

from geoml import b2_campaign as campaign
from geoml.artifacts import fingerprint


DESIGNATION = {"primary_scorer": "mahalanobis", "approved_by": "fabricated-researcher",
               "approved_at": "2026-10-26T00:00:00+00:00", "record": "fabricated-test-only"}


def write(path, value):
    value = deepcopy(value)
    value.pop("artifact_id", None)
    value["artifact_id"] = fingerprint(value)
    path.write_text(json.dumps(value))
    return value


@pytest.fixture
def inventories(tmp_path, monkeypatch):
    paths = {}
    common = {"source": {"fabricated.py": "a" * 64}, "runtime": {"device": "cpu"},
              "data_identity": "b" * 64, "roles": {"train": [1], "val-select": [2], "val-calib": [3]},
              "config": {"training": {"epochs": 30, "batch": 32, "width": 16, "time_pool": 2,
                                        "lr": .001, "weight_decay": .0001, "augment": True,
                                        "center_loss_weight": .005}}}
    for profile in campaign.ORDER:
        path = tmp_path / f"{profile}.json"
        write(path, {"contract": "fabricated-inventory", "scope": "PRODUCTION", "profile": profile,
                     "seeds": [0, 1, 2], "common": common,
                     "cells": [{"seed": seed, "view": view} for seed in range(3) for view in campaign.ROSTERS[profile]]})
        paths[profile] = path

    def loader(path, profile):
        value = json.loads(path.read_text())
        assert value["profile"] == profile
        assert value["artifact_id"] == fingerprint({key: item for key, item in value.items() if key != "artifact_id"})
        return value

    monkeypatch.setattr(campaign, "_inventory", loader)
    return paths


def freeze(inventories, out, **kwargs):
    return campaign.freeze_campaign(inventories, out, primary_scorer="mahalanobis", designation=DESIGNATION, **kwargs)


def test_complete_fifteen_fit_binding_has_explicit_scorer_and_fixed_sequence(inventories, tmp_path):
    out = tmp_path / "campaign.json"
    result = freeze(inventories, out)
    assert campaign.verify_campaign(out) == result
    assert result["fits"] == sum(item["fits"] for item in result["inventories"]) == 15
    assert result["primary_scorer"] == "mahalanobis"
    assert result["evaluation_order"] == ["proposed-full", "c2-h3-dual"]
    assert result["optional_co_controls"] == "DEFERRED_BEFORE_HELDOUT"
    assert result["authorizes_nothing"] is True and result["benchmark_complete"] is False
    before = out.read_bytes()
    with pytest.raises(FileExistsError):
        freeze(inventories, out)
    assert out.read_bytes() == before


@pytest.mark.parametrize("scorer,designation", [(None, None), ("invalid", DESIGNATION),
    ("energy", DESIGNATION), ("mahalanobis", {**DESIGNATION, "approved_by": ""}),
    ("mahalanobis", {**DESIGNATION, "approved_at": "2026-10-26T00:00:00"})])
def test_recommendation_or_incomplete_designation_does_not_freeze(inventories, tmp_path, scorer, designation):
    out = tmp_path / "campaign.json"
    with pytest.raises(ValueError):
        campaign.freeze_campaign(inventories, out, primary_scorer=scorer, designation=designation)
    assert not out.exists()


@pytest.mark.parametrize("mutation", ["missing_cell", "duplicate_cell", "different_seed", "source", "runtime",
                                     "data_identity", "roles", "budget", "scope"])
def test_incompatible_or_incomplete_roster_cannot_be_bound(inventories, tmp_path, mutation):
    path = inventories["c2-h3-dual"]
    value = json.loads(path.read_text())
    if mutation == "missing_cell":
        value["cells"].pop()
    elif mutation == "duplicate_cell":
        value["cells"].append(value["cells"][0])
    elif mutation == "different_seed":
        value["seeds"] = [0, 1, 3]
    elif mutation == "scope":
        value["scope"] = "BOUNDED_FIXTURE"
    elif mutation == "budget":
        value["common"]["config"]["training"]["epochs"] = 29
    else:
        value["common"][mutation] = "different"
    write(path, value)
    with pytest.raises(ValueError):
        freeze(inventories, tmp_path / "bad.json")


def test_re_signed_inventory_change_cannot_change_a_frozen_campaign(inventories, tmp_path):
    out = tmp_path / "campaign.json"
    freeze(inventories, out)
    path = inventories["proposed-full"]
    value = json.loads(path.read_text())
    value["extra"] = "an otherwise valid inventory revision"
    write(path, value)
    with pytest.raises(ValueError, match="changed"):
        campaign.verify_campaign(out)


def test_campaign_rejects_re_signed_reordering_or_optional_controls(inventories, tmp_path):
    out = tmp_path / "campaign.json"
    value = freeze(inventories, out)
    value["evaluation_order"].reverse()
    write(out, value)
    with pytest.raises(ValueError, match="modified"):
        campaign.verify_campaign(out)


class Authority:
    def __init__(self, allowed=False):
        self.allowed = allowed
        self.calls = []

    def require(self, action, identity):
        self.calls.append((action, identity))
        if not self.allowed:
            raise PermissionError("fabricated heldout authority denies")


class Journal:
    """Test stand-in for verified E16 ledger / independently anchored custody."""
    def __init__(self):
        self.events = []
        self.held = False

    @contextmanager
    def locked(self):
        assert not self.held
        self.held = True
        try:
            yield
        finally:
            self.held = False

    def read_verified(self):
        assert self.held
        return deepcopy(self.events)

    def append(self, kind, data):
        assert self.held and kind == "boundary_check"
        self.events.append({"kind": kind, "data": deepcopy(data)})


def test_separate_heldout_authorization_precedes_reader_or_journal(inventories, tmp_path):
    out = tmp_path / "campaign.json"
    value = freeze(inventories, out)
    journal, authority = Journal(), Authority()
    with pytest.raises(PermissionError):
        with campaign.evaluation_step(out, "proposed-full", authorization=authority, journal=journal):
            pytest.fail("reader admitted without authorization")
    assert authority.calls == [("heldout", value["artifact_id"])]
    assert journal.events == []


def test_future_evaluation_sequence_is_canonical_then_matched_once(inventories, tmp_path):
    out = tmp_path / "campaign.json"
    freeze(inventories, out)
    journal, authority = Journal(), Authority(True)
    with pytest.raises(ValueError, match="order"):
        with campaign.evaluation_step(out, "c2-h3-dual", authorization=authority, journal=journal):
            pytest.fail("out of order read admitted")
    for profile in campaign.ORDER:
        with campaign.evaluation_step(out, profile, authorization=authority, journal=journal) as (value, inventory):
            assert inventory["profile"] == profile
            assert value["primary_scorer"] == "mahalanobis"
            assert journal.held and journal.events[-1]["data"]["event"] == "evaluation_started"
    assert len(journal.events) == 4
    with pytest.raises(ValueError, match="once"):
        with campaign.evaluation_step(out, "proposed-full", authorization=authority, journal=journal):
            pytest.fail("repeat read admitted")


def test_failed_read_burns_attempt_and_requires_external_recovery(inventories, tmp_path):
    out = tmp_path / "campaign.json"
    freeze(inventories, out)
    journal, authority = Journal(), Authority(True)
    with pytest.raises(RuntimeError, match="interrupted"):
        with campaign.evaluation_step(out, "proposed-full", authorization=authority, journal=journal):
            raise RuntimeError("fabricated reader interrupted")
    assert len(journal.events) == 1
    with pytest.raises(ValueError, match="external recovery"):
        with campaign.evaluation_step(out, "proposed-full", authorization=authority, journal=journal):
            pytest.fail("partial read silently retried")


def test_valid_campaign_replacement_after_authorization_burns_claim_without_read(inventories, tmp_path):
    out = tmp_path / "campaign.json"
    original = freeze(inventories, out)
    journal, authority = Journal(), Authority(True)
    append = journal.append

    def replace_after_claim(kind, data):
        append(kind, data)
        replacement = deepcopy(original)
        replacement["primary_scorer"] = "energy"
        replacement["designation"]["primary_scorer"] = "energy"
        write(out, replacement)

    journal.append = replace_after_claim
    with pytest.raises(ValueError, match="changed after authorization"):
        with campaign.evaluation_step(out, "proposed-full", authorization=authority, journal=journal):
            pytest.fail("reader admitted after valid campaign replacement")
    assert authority.calls == [("heldout", original["artifact_id"])]
    assert len(journal.events) == 1
    assert journal.events[0]["data"] == {"campaign_id": original["artifact_id"],
        "event": "evaluation_started", "profile": "proposed-full"}


def test_fixture_campaign_cannot_admit_production_read(inventories, tmp_path):
    for path in inventories.values():
        value = json.loads(path.read_text())
        value["scope"] = "BOUNDED_FIXTURE"
        write(path, value)
    out = tmp_path / "campaign.json"
    freeze(inventories, out)
    authority = Authority(True)
    with pytest.raises(ValueError, match="fixture"):
        with campaign.evaluation_step(out, "proposed-full", authorization=authority, journal=Journal()):
            pytest.fail("fixture relabelled as production")
    assert authority.calls == []


def test_production_inventory_adapter_and_campaign_bind_the_same_fifteen_cells(tmp_path, monkeypatch):
    """Exercise actual inventory freeze/verification; calibrated bundles are metadata stand-ins."""
    from geoml import b2_production_training as production

    bundles = {}
    paths = {}
    for profile, views in production.PROFILES.items():
        roots = []
        for seed in range(3):
            root = tmp_path / profile / f"seed-{seed}"
            root.mkdir(parents=True)
            (root / "training.json").write_text('{"stand_in":"training"}')
            (root / "calibration.json").write_text('{"stand_in":"calibration"}')
            cfg = production.production_config(views, seed)
            trained = {"artifact_id": f"training-{profile}-{seed}", "data_identity": "f" * 64,
                       "source": {"files_sha256": {"fabricated.py": "a" * 64}},
                       "roles": {"train": [1], "val-select": [2], "val-calib": [3]},
                       "runtime": {"device": "cpu", "profile": production.R6_PROFILE}}
            calibrated = {"artifact_id": f"calibration-{profile}-{seed}"}
            bundles[root] = calibrated, trained, cfg
            roots.append(root)
        paths[profile] = tmp_path / f"inventory-{profile}.json"
        monkeypatch.setattr(production, "_calibration", lambda root: bundles[root])
        production.freeze_inventory(roots, paths[profile], profile=profile)
    frozen = freeze(paths, tmp_path / "campaign.json")
    verified = campaign.verify_campaign(tmp_path / "campaign.json")
    assert verified == frozen
    assert [item["fits"] for item in frozen["inventories"]] == [9, 6]

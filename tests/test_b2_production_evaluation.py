"""Synthetic indices and deterministic outputs; no RF or operational authority."""
from contextlib import contextmanager
from copy import deepcopy
import json
from types import SimpleNamespace

import numpy as np
import pytest

from geosim.b2_protocol import LABELS, scenario_ids
from geosim.b2_scenarios import TEST_FAMILIES
from geoml import b2_production_evaluation as ev
from geoml import b2_production_training as prod
from geoml.artifacts import fingerprint
from geoml.calibration import RejectionCalibration


class SyntheticSource:
    def __init__(self, kind, role, variants):
        self.kind, self.role, self.has_residual = kind, role, True
        self.groups = np.array(scenario_ids(role))
        n = len(self.groups) * len(variants)
        self.index = {"seed": np.repeat(self.groups, len(variants)),
                      "family" if kind == "test" else "label": np.tile(variants, len(self.groups)),
                      "plan_consistency": np.zeros(n, dtype=int), "meta": [{} for _ in range(n)]}
        if kind == "matched":
            self.index["matched_bin"] = np.repeat(np.arange(len(self.groups)) % 3, len(variants))

    def __len__(self):
        return len(self.index["seed"])

    def split(self):
        return {**self.index, **({"families": TEST_FAMILIES} if self.kind == "test" else {})}


class FakeAuthority:
    def __init__(self):
        self.calls = []

    def require(self, action, identity):
        self.calls.append((action, identity))


class FakeJournal:
    def __init__(self):
        self.entries, self.held, self.fail_completion = [], False, False

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
        return deepcopy(self.entries)

    def append(self, kind, data):
        assert self.held
        if self.fail_completion and data["event"] == "evaluation_completed":
            raise OSError("synthetic custody failure")
        self.entries.append({"kind": kind, "data": deepcopy(data)})


@pytest.fixture
def campaign(tmp_path, monkeypatch):
    # Production readers/verifiers have their own artifact suites. This fixture
    # replaces their storage/model boundary, retaining the actual ordered journal
    # context, population validation, scoring, reporting and publication code.
    known = SyntheticSource("known", "test", list(range(8)))
    unknown = SyntheticSource("test", "test", list(range(5)))
    matched = SyntheticSource("matched", "test-matched", [0, 6, 3])
    roles = {r: scenario_ids(r) for r in ("train", "val-select", "val-calib", "test")}
    with prod.r6_fp32():
        runtime = prod.runtime_identity("cpu")
    manifest = {"protocol": "B2-feat/1", "request": {}, "roles": {}, "config": {}}
    common = {"data_identity": fingerprint(manifest), "roles": roles, "runtime": runtime,
              "source": ev._source_identity()["files_sha256"]}
    inventories, bindings, bundles = {}, [], {}
    for profile, views in prod.PROFILES.items():
        cfg = prod.production_config(views)
        inv = {"common": {**common, "config": ev.kernels._base_config(cfg)}, "cells": []}
        path = tmp_path / (profile + ".json")
        path.write_text(profile)
        for seed in range(3):
            root = tmp_path / f"runs-{profile}-{seed}"
            config = prod.production_config(views, seed)
            trained = {"files": {f"model_{v}.pt": "a" * 64 for v in views}}
            scorer = SimpleNamespace(score=lambda x: np.square(x).sum(1))
            loaded = {v: ({"view": v}, scorer) for v in views}
            calibrated = {"views": {v: {"alarm": {"threshold": .5}, "rejection": {
                m: RejectionCalibration(m, .5, .95, 1200).to_dict() for m in config.methods}} for v in views}}
            bundles[str(root)] = trained, config, loaded, calibrated
            inv["cells"].extend({"seed": seed, "view": v, "runs": str(root)} for v in views)
        inventories[str(path)] = inv
        bindings.append({"profile": profile, "path": str(path), "sha256": ev._sha256(path),
                         "artifact_id": fingerprint(inv), "fits": len(inv["cells"])})
    common["training_budget"] = {k: prod.production_config().training[k] for k in (
        "epochs", "batch", "width", "time_pool", "lr", "weight_decay", "augment", "center_loss_weight")}
    bound = {"contract": ev.campaign_api.CONTRACT, "scope": "PRODUCTION", "common": common,
             "benchmark_complete": False, "authorizes_nothing": True,
             "primary_scorer": "mahalanobis", "inventories": bindings,
             "designation": {"primary_scorer": "mahalanobis", "approved_by": "synthetic test fixture",
                 "approved_at": "2000-01-01T00:00:00Z", "record": "test fixture, not operational approval"},
             "evaluation_order": list(ev.campaign_api.ORDER), "optional_co_controls": "DEFERRED_BEFORE_HELDOUT",
             "fits": 15}
    bound["artifact_id"] = fingerprint(bound)
    path = tmp_path / "campaign.json"
    path.write_text("synthetic binding")
    journal, authority, calls = FakeJournal(), FakeAuthority(), []
    monkeypatch.setattr(ev.campaign_api, "verify_campaign", lambda _: deepcopy(bound))
    monkeypatch.setattr(prod, "verify_inventory", lambda p, profile: deepcopy(inventories[str(p)]))
    monkeypatch.setattr(prod, "_training", lambda p, device="cpu": bundles[str(p)][:3])
    monkeypatch.setattr(prod, "_calibration", lambda p: (bundles[str(p)][3], *bundles[str(p)][:2]))
    identity = json.loads((ev.ROOT / "docs/results/b2_e10_k17d_identity.json").read_text())
    metadata = {"verification": {"synthetic": True},
                "co_feed_missing_ids": identity["co_feed_missing_ids"],
                "sensitivity_ids": identity["sensitivity_ids"],
                "excluded_test_ids": [3200000, 3200001], "excluded_matched_ids": [3300000, 3300001]}
    def meta(*_):
        assert journal.held
        calls.append("metadata")
        return deepcopy(metadata)
    monkeypatch.setattr(ev, "_metadata_check", meta)
    def opener(*_):
        assert journal.held and calls and "metadata" in calls
        calls.append("open")
        return common["data_identity"], roles, {"test": known}, {"test": known.split()}
    monkeypatch.setattr(prod, "_open", opener)
    monkeypatch.setattr(ev.kernels, "_known_header", lambda _: (manifest, None))
    monkeypatch.setattr(ev.ex, "_load_unknown", lambda *a: (manifest, "unknown-id", unknown))
    monkeypatch.setattr(ev.ex, "_load_matched", lambda *a: (manifest, "matched-id", matched))
    # The unchanged bootstrap kernel is tested elsewhere; keep this orchestration
    # fixture inexpensive while using the real scoring and ranking kernels.
    monkeypatch.setattr(ev.ex, "cluster_ci", lambda values, groups: (0., 1.))
    def infer(fitted, source):
        assert journal.held
        calls.append("infer")
        n = len(source)
        logits = np.zeros((n, 8))
        if source.kind != "test":
            logits[np.arange(n), source.index["label"]] = 5.
        return {"logits": logits, "embedding": np.full((n, 2), source.kind == "test", dtype=float),
                "plan_logits": None}
    monkeypatch.setattr(ev, "infer_streaming", infer)
    def run(profile="proposed-full", name="output", **kwargs):
        return ev.evaluate_campaign_profile(tmp_path / "known", path, tmp_path / name,
            unknown_data=tmp_path / "unknown", matched_data=tmp_path / "matched",
            profile=profile, authorization=authority, journal=journal, log=lambda _: None, **kwargs)
    return SimpleNamespace(run=run, path=path, root=tmp_path, journal=journal, authority=authority,
                           bound=bound, inventories=inventories, metadata=metadata, calls=calls,
                           known=known, unknown=unknown, matched=matched)


def test_all_fifteen_cells_evaluate_in_order_with_fixed_subgroups_and_matched_predictions(campaign):
    first = campaign.run()
    second = campaign.run("c2-h3-dual", "matched-output")
    assert len(first["models"]) == 9 and len(second["models"]) == 6
    for result in (first, second):
        assert result["contract"] == ev.CONTRACT and result["benchmark_complete"] is False
        metric = result["models"][0]["metrics"]
        assert metric["accuracy"]["mean"] == 1.
        assert metric["rejection"]["mahalanobis"]["n_unknown"] == 1500
        assert metric["rejection"]["mahalanobis"]["n_unknown_equivalence_limited"] == 500
        assert set(metric["rejection"]["mahalanobis"]["pooled_near"]["families"]) == set(TEST_FAMILIES[:3])
        sub = metric["sensitivity"]
        assert sub["d1_exposure_excluded"]["n_known"] == 498 * 8
        assert sub["d1_exposure_excluded"]["n_test_only"] == 498 * 5
        assert sub["d1_exposure_excluded"]["matched"]["n_groups"] == 148
        assert sub["k17d_co_feed_missing"]["n_groups"] == 35
        assert sub["k17d_excluding_co_feed_missing"]["n_groups"] == 465
    predictions = json.loads((campaign.root / "output/predictions.json").read_text())
    assert len(predictions[0]["matched"]["sample_ids"]) == 450
    assert set(predictions[0]["matched"]["scores"]) == {"msp", "energy", "mahalanobis"}
    completion = json.loads((campaign.root / "output/completion.json").read_text())
    assert completion["journal_completion_recorded"] is True
    assert len(campaign.journal.entries) == 4


@pytest.mark.parametrize("field", ["authority", "journal"])
def test_missing_ports_refuse_before_any_data_read(tmp_path, monkeypatch, field):
    monkeypatch.setattr(ev.campaign_api, "verify_campaign", lambda _: pytest.fail("unexpected read"))
    with pytest.raises(prod.AuthorizationRequired):
        ev.evaluate_campaign_profile("known", "campaign", tmp_path / "out", unknown_data="unknown",
            matched_data="matched", profile="proposed-full", authorization=None if field == "authority" else object(),
            journal=None if field == "journal" else object())


def test_fixture_scope_rejected_before_opening(campaign):
    campaign.bound["scope"] = "BOUNDED_FIXTURE"
    with pytest.raises(ValueError, match="bounded-fixture"):
        campaign.run()
    assert not campaign.calls


def test_order_and_repeated_reads_refused(campaign):
    with pytest.raises(ValueError, match="canonical then matched"):
        campaign.run("c2-h3-dual")
    assert not campaign.calls
    campaign.run()
    with pytest.raises(ValueError, match="canonical then matched"):
        campaign.run(name="repeat")


@pytest.mark.parametrize("kind", ["known", "unknown", "matched"])
def test_missing_variant_refused_before_inference(campaign, kind):
    source = getattr(campaign, kind)
    key = "family" if kind == "unknown" else "label"
    source.index[key][0] = source.index[key][1]
    with pytest.raises(ValueError, match="every frozen group/variant"):
        campaign.run()
    assert "infer" not in campaign.calls
    assert len(campaign.journal.entries) == 1


def test_metadata_failure_consumes_read_without_opening_observations(campaign, monkeypatch):
    monkeypatch.setattr(ev, "_metadata_check", lambda *_: (_ for _ in ()).throw(ValueError("K17d mismatch")))
    with pytest.raises(ValueError, match="K17d"):
        campaign.run()
    assert not campaign.calls
    assert len(campaign.journal.entries) == 1
    with pytest.raises(ValueError, match="partial"):
        campaign.run(name="retry")


def test_runtime_mismatch_refused_before_opening(campaign):
    campaign.bound["common"]["runtime"] = {"different": True}
    with pytest.raises(ValueError, match="runtime differs"):
        campaign.run()
    assert not campaign.calls


def test_nonfinite_inference_does_not_publish(campaign, monkeypatch):
    def infer(_, source):
        return {"logits": np.full((len(source), 8), np.nan), "embedding": np.zeros((len(source), 2)), "plan_logits": None}
    monkeypatch.setattr(ev, "infer_streaming", infer)
    with pytest.raises(ValueError, match="nonfinite"):
        campaign.run()
    assert not (campaign.root / "output").exists()


def test_journal_completion_failure_leaves_no_completion_marker(campaign):
    campaign.journal.fail_completion = True
    with pytest.raises(OSError, match="custody failure"):
        campaign.run()
    assert (campaign.root / "output/results.json").exists()
    assert not (campaign.root / "output/completion.json").exists()


def test_drift_after_inference_refuses_publication(campaign, monkeypatch):
    original = ev.infer_streaming
    def infer(*args):
        values = original(*args)
        campaign.path.write_text("changed after read")
        return values
    monkeypatch.setattr(ev, "infer_streaming", infer)
    with pytest.raises(ValueError, match="frozen inputs changed"):
        campaign.run()
    assert not (campaign.root / "output/completion.json").exists()


def test_matched_alarm_uses_same_d6_arithmetic_as_persisted_decisions():
    part = {"label": np.array([0, 6, 3]), "seed": np.array([3300000] * 3),
            "matched_bin": np.zeros(3, dtype=int), "plan_consistency": np.zeros(3, dtype=int),
            "meta": [{} for _ in range(3)]}
    logits = np.zeros((3, 8))
    logits[:, 0] = 100.
    output = {"logits": logits, "embedding": np.zeros((3, 2)), "plan_logits": None}
    threshold = 1e-44
    assert not (1. - ev.ex._softmax(logits)[:, 0]).any()  # subtraction loses all small event mass
    record = ev._prediction_record(part, output, None, {}, {"threshold": threshold})
    metrics = ev._matched_metrics(part, output, {}, None, threshold, None, None)
    assert record["alarm"] == [True, True, True]
    assert metrics["clean_false_alarm"]["mean"] == metrics["event_alarm"]["mean"] == 1.


def test_source_mismatch_refused_before_opening(campaign):
    campaign.bound["common"]["source"] = {"changed.py": "0" * 64}
    with pytest.raises(ValueError, match="source differs"):
        campaign.run()
    assert not campaign.calls


def test_explicit_authority_denial_precedes_metadata_and_journal(campaign):
    def deny(*_):
        raise PermissionError("synthetic denied authority")
    campaign.authority.require = deny
    with pytest.raises(PermissionError, match="denied authority"):
        campaign.run()
    assert not campaign.calls and not campaign.journal.entries

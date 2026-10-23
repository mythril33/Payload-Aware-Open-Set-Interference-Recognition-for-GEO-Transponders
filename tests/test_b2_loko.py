"""A8 LOKO engineering fixtures; no recognition-quality claims."""
import json
from dataclasses import replace

import numpy as np
import pytest

from geoml import b2_loko as lk
from geoml.b2_stream import B2Source
from geosim.b2_protocol import LABELS
from test_b2_experiment import _config, _split
from test_b2_artifacts import feature_generator, generator  # noqa: F401


@pytest.fixture
def dataset(monkeypatch, tmp_path):
    parts = {role: _split(role, 2, i) for i, role in enumerate(lk.ROLES)}
    manifest = {"protocol": "B2-feat/1", "labels": list(LABELS), "benchmark_complete": False}
    monkeypatch.setattr(lk, "open_b2_known", lambda _: (manifest, "f" * 64,
        {role: B2Source.from_arrays(part, role=role) for role, part in parts.items()}))
    monkeypatch.setattr(lk, "_source_identity", lambda: {"revision": "test", "files_sha256": {"fixture": "0" * 64}})
    return parts, manifest, tmp_path / "data"


def config(**kwargs):
    return _config(views=("dual_residual",), **kwargs)


def test_plan_has_seven_folds_three_seeds_explicit_remaps_and_stable_identity(dataset):
    _, _, data = dataset
    _, identity, sources = lk._open(data, config())
    plan = lk.build_plan(sources, identity, config())
    assert plan == lk.build_plan(sources, identity, config())
    assert plan["total_planned_fits"] == 21 and plan["training_seeds"] == [0, 1, 2]
    assert plan["benchmark_complete"] is False and plan["full_sweep_authorized"] is False
    for fold in plan["folds"]:
        assert fold["known_labels"][0] == "clean" and fold["holdout_label"] not in fold["known_labels"]
        assert list(fold["original_to_local"].values()) == list(range(7))
        assert all(p["n_retained_known"] == 14 and p["n_heldout"] == 2 for p in fold["partitions"].values())
    changed = lk.build_plan(sources, "e" * 64, config())
    assert changed["plan_fingerprint"] != plan["plan_fingerprint"]
    assert lk.build_plan(sources, identity, config(), seeds=(3, 4, 5))["plan_fingerprint"] != plan["plan_fingerprint"]
    with pytest.raises(ValueError, match="three distinct"):
        lk.build_plan(sources, identity, config(), seeds=(0, 0, 1))
    with pytest.raises(ValueError, match="non-clean"):
        lk.known_labels("clean")


def test_fold_filter_preserves_shard_values_order_groups_and_rechecks_source(dataset):
    parts, _, data = dataset
    _, _, sources = lk._open(data, config())
    source = sources["train"]
    held = "cw"
    fold = lk.fold_source(source, held)
    expected = parts["train"]["label"] != LABELS.index(held)
    assert fold.shard_counts == [14] and fold.groups.tolist() == source.groups.tolist()
    shard = next(fold.shards())
    assert np.array_equal(shard["spec"], parts["train"]["spec"][expected])
    assert np.array_equal(shard["residual"], parts["train"]["residual"][expected])
    assert shard["label"].tolist() == list(range(7)) * 2
    assert np.array_equal(fold.fetch([13, 0])["spec"], shard["spec"][[13, 0]])
    parts["train"]["label"][0] = 1
    with pytest.raises(ValueError, match="changed since"):
        list(fold.shards())


def test_filter_handles_empty_shard_reordered_reads_and_partial_group_shards(dataset):
    parts, _, _ = dataset
    part = parts["train"]
    # Put both held-out rows in a first shard, then split retained rows across shards.
    order = np.r_[np.flatnonzero(part["label"] == 3), np.flatnonzero(part["label"] != 3)]
    ordered = {k: (np.asarray(v)[order] if k != "meta" else [v[i] for i in order]) for k, v in part.items()}
    reference = B2Source.from_arrays(ordered, role="train")
    counts = [2, 5, 9]
    starts = [0, 2, 7]
    def reader(indices):
        for i in indices:
            a, b = starts[i], starts[i] + counts[i]
            yield {k: v[a:b] for k, v in ordered.items()}
    source = B2Source("known", reference.index, counts, reader, role="train", has_residual=True)
    fold = lk.fold_source(source, "unauthorized")
    assert fold.shard_counts == [5, 9]
    shards = list(fold.shards([1, 0]))
    assert [len(s["label"]) for s in shards] == [9, 5]
    assert np.array_equal(fold.fetch([0, 13, 6])["spec"], ordered["spec"][[2, 15, 8]])


def test_group_integrity_and_role_failures_before_training(dataset, tmp_path, monkeypatch):
    parts, _, data = dataset
    monkeypatch.setattr(lk, "fit_streaming", lambda *_a, **_k: pytest.fail("must fail before fitting"))
    parts["val-calib"]["seed"][:] += 50000
    with pytest.raises(ValueError, match="outside its frozen"):
        lk.run_smoke(config(), data, tmp_path / "leak", holdout="cw")
    # One missing variant in a group, with every label still present in the role.
    parts["val-calib"] = _split("val-calib", 2, 0)
    part = parts["train"]
    parts["train"] = {k: v[1:] for k, v in part.items()}
    with pytest.raises(ValueError, match="incomplete paired"):
        lk.run_smoke(config(), data, tmp_path / "partial", holdout="cw")


def test_smoke_caps_and_manifest_protocol_are_fail_closed(dataset, tmp_path, monkeypatch):
    parts, manifest, data = dataset
    monkeypatch.setattr(lk, "fit_streaming", lambda *_a, **_k: pytest.fail("must not fit"))
    with pytest.raises(ValueError, match="exactly one view"):
        lk.run_smoke(_config(), data, tmp_path / "views", holdout="cw")
    for key, val in (("epochs", 3), ("width", 16), ("batch", 64)):
        c = config()
        with pytest.raises(ValueError, match="smoke caps"):
            lk.run_smoke(replace(c, training={**c.training, key: val}), data, tmp_path / key, holdout="cw")
    with pytest.raises(ValueError, match="bootstrap"):
        lk.run_smoke(config(), data, tmp_path / "bootstrap", holdout="cw", bootstrap=0)
    manifest["protocol"] = "B2-features/1"
    with pytest.raises(ValueError, match="does not match"):
        lk.run_smoke(config(), data, tmp_path / "stage", holdout="cw")
    manifest["protocol"] = "B2-feat/1"
    parts["train"] = _split("train", 3, 0)
    with pytest.raises(ValueError, match="at most 2 groups"):
        lk.run_smoke(config(), data, tmp_path / "large", holdout="cw")


def test_ranking_group_bootstrap_denominators_ties_and_empty_populations():
    original = np.tile(np.arange(8), 2)
    groups = np.repeat([3200000, 3200001], 8)
    held = original == 1
    local = np.where(original > 1, original - 1, original)
    scores = held.astype(float)
    result = lk._ranking(scores, original, local, groups, "cw", bootstrap=20)
    assert result["n_known"] == 14 and result["n_unknown"] == 2
    assert result["unknown_auroc"] == result["unknown_aupr"] == result["oscr_auc"] == 1
    assert result["ci95"]["unknown_auroc"] == [1, 1]
    assert result["bootstrap"]["unit"] == "scenario group, paired known/held-out"
    ties = lk._ranking(np.zeros(16), original, local, groups, "cw", bootstrap=20)
    assert ties["unknown_auroc"] == .5 and ties["unknown_aupr"] == pytest.approx(2 / 16)
    assert lk._ranking(scores[:8], original[:8], local[:8], groups[:8], "cw")["ci95"] is None
    empty = lk._ranking(scores[~held], original[~held], local[~held], groups[~held], "cw")
    assert empty["unknown_auroc"] is None and empty["n_unknown"] == 0
    # A group-specific model failure must survive paired bootstrap, unlike an
    # observation-wise CI that would dilute correlation among the seven variants.
    pred = local.copy()
    pred[8:] = (pred[8:] + 1) % 7
    paired = lk._ranking(scores, original, pred, groups, "cw", bootstrap=200)
    assert paired["ci95"]["oscr_auc"] == [0, 1]


def test_end_to_end_smoke_excludes_heldout_from_every_fit_calibrates_before_test_and_reuses(dataset, tmp_path, monkeypatch):
    _, _, data = dataset
    events = []
    real_fit, real_infer, real_scorer, real_calib = lk.fit_streaming, lk.infer_streaming, lk.fit_mahalanobis, lk.calibrate_scores
    def fit(train, val, cfg, **kw):
        assert cfg.labels == tuple(n for n in LABELS if n != "cw")
        assert set(train.index["label"]) == set(val.index["label"]) == set(range(7))
        assert len(train) == len(val) == 14
        events.append("fit")
        return real_fit(train, val, cfg, **kw)
    def infer(fitted, source, **kw):
        events.append(source.role)
        if source.role != "test":
            assert len(source) == 14 and source.index["label"].max() == 6
        return real_infer(fitted, source, **kw)
    def scorer(embedding, labels, n_classes, *a, **kw):
        assert len(embedding) == len(labels) == 14 and n_classes == 7
        events.append("scorer")
        return real_scorer(embedding, labels, n_classes, *a, **kw)
    def calibrate(scores, *a, **kw):
        assert len(scores) == 14
        events.append("calibrate")
        return real_calib(scores, *a, **kw)
    monkeypatch.setattr(lk, "fit_streaming", fit)
    monkeypatch.setattr(lk, "infer_streaming", infer)
    monkeypatch.setattr(lk, "fit_mahalanobis", scorer)
    monkeypatch.setattr(lk, "calibrate_scores", calibrate)
    out = tmp_path / "smoke"
    result = lk.run_smoke(config(), data, out, holdout="cw", bootstrap=20, log=lambda *_: None)
    assert events.count("calibrate") == 3 and events.index("test") > max(i for i,e in enumerate(events) if e == "calibrate")
    assert result["benchmark_complete"] is False and result["n_mahalanobis_training"] == 14
    diagnostics = result["train_diagnostics"]                       # K18: observation-only, training batches only
    assert diagnostics["schema"] == "B2-train-diagnostics/1" and diagnostics["split"] == "train"
    assert diagnostics["observation_only"] is True and diagnostics["affects_training"] is False
    assert len(diagnostics["epochs"]) == len(result["history"])
    assert diagnostics["epochs"][result["best_epoch"]]["epoch"] == result["best_epoch"] and result["best_val_macro_f1"] >= 0.0
    for method in result["methods"].values():
        assert method["calibration"]["n_calibration"] == 14
        assert method["ranking"]["n_known"] == method["known_acceptance"]["n_samples"] == 14
        assert method["ranking"]["n_unknown"] == method["unknown_rejection"]["n_samples"] == 2
    rows = json.loads((out / "predictions.json").read_text())
    assert len(rows) == 16 and sum(row["is_unknown"] for row in rows) == 2
    assert all(row["prediction"] != "cw" for row in rows)
    json.dumps(result, allow_nan=False)
    with pytest.raises(ValueError, match="already exists"):
        lk.run_smoke(config(), data, out, holdout="cw")
    again = lk.run_smoke(config(), data, out, holdout="cw", bootstrap=20, reuse=True, log=lambda *_: None)
    assert again["checkpoint_sha256"] == result["checkpoint_sha256"] and again["methods"] == result["methods"]
    with pytest.raises(ValueError, match="does not match"):
        lk.run_smoke(config(), data, out, holdout="swept_cw", reuse=True)
    c = config()
    with pytest.raises(ValueError, match="does not match"):
        lk.run_smoke(replace(c, window_shards=1), data, out, holdout="cw", reuse=True)
    calibration = out / "rejection_msp.json"
    good = calibration.read_text()
    corrupted = json.loads(good)
    corrupted["provenance"] = "foreign"
    calibration.write_text(json.dumps(corrupted))
    with pytest.raises(ValueError, match="existing rejection calibration"):
        lk.run_smoke(config(), data, out, holdout="cw", reuse=True, log=lambda *_: None)
    assert json.loads(calibration.read_text())["provenance"] == "foreign"
    calibration.write_text(good)
    (out / "mahalanobis.npz").write_bytes(b"invalid scorer")
    with pytest.raises(ValueError, match="invalid Mahalanobis"):
        lk.run_smoke(config(), data, out, holdout="cw", reuse=True, log=lambda *_: None)
    incomplete = tmp_path / "incomplete"
    incomplete.mkdir()
    (incomplete / "unrelated.txt").write_text("preserve")
    with pytest.raises(ValueError, match="no compatible checkpoint"):
        lk.run_smoke(config(), data, incomplete, holdout="cw", reuse=True)
    assert (incomplete / "unrelated.txt").read_text() == "preserve"


def test_cli_defaults_to_plan_only(dataset, tmp_path, monkeypatch):
    _, _, data = dataset
    cpath = tmp_path / "config.json"
    cpath.write_text(json.dumps(config().resolved()))
    monkeypatch.setattr(lk, "run_smoke", lambda *_a, **_k: pytest.fail("default must never execute a fold"))
    out = tmp_path / "plan"
    args = ["--config", str(cpath), "--data", str(data), "--out", str(out)]
    lk.main(args)
    assert sorted(p.name for p in out.iterdir()) == ["plan.json"]
    with pytest.raises(ValueError, match="already exists"):
        lk.main(args)
    lk.main(args + ["--reuse"])


def test_disk_artifact_fold_smoke_and_corrupted_shard_rejection(tmp_path, feature_generator):
    from geosim import b2_dataset as ds
    from geosim.cancellation import CancellationConfig
    # Real writer, manifest, checksum and streaming loader; stand-in physics and
    # cancellation from the shared artifact fixture, explicitly not RF evidence.
    root = tmp_path / "disk"
    ds.generate_b2_dataset(root, limit_groups=1, groups_per_shard=1,
                           cancellation=CancellationConfig())
    c = config()
    c = replace(c, views=("co",), training={**c.training, "width": 1, "time_pool": 128,
                                           "batch": 7, "plan_shift_fraction": 0})
    result = lk.run_smoke(c, root, tmp_path / "run", holdout="carrier_under_carrier", log=lambda *_: None)
    assert result["n_mahalanobis_training"] == 7
    assert result["methods"]["msp"]["ranking"]["n_unknown"] == 1
    assert result["methods"]["msp"]["ranking"]["ci95"] is None
    _, _, sources = lk._open(root, c)
    fold = lk.fold_source(sources["train"], "carrier_under_carrier")
    shard = root / "train" / "part-00000.npz"
    with shard.open("ab") as stream:
        stream.write(b"tampered")
    with pytest.raises(ValueError, match="modified"):
        list(fold.shards())

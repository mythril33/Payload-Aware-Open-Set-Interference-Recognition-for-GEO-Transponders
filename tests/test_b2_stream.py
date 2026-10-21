"""E1 streaming loader for the canonical B2 runner: parity, determinism, roles, provenance, corruption, memory.

The on-disk fixtures are real B2-feat/1 artifacts written and verified by the
production writer; only the physics is a stand-in (random spectra, fake
canceller), so nothing here is a recognition result.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
import torch

from geoml import b2_stream as st
from geoml import train as legacy
from geoml.b2_experiment import B2ExperimentConfig, run_b2_experiment
from geoml.b2_stream import B2Source, fit_streaming, infer_streaming, open_b2_known
from geoml.train import TrainConfig
from geosim import b2_dataset as ds
from geosim import b2_scenarios as scenes
from geosim.b2_protocol import BASE_ROLES, LABELS, ROLE_STARTS, scenario_ids
from geosim.cancellation import CancellationConfig
from test_b2_artifacts import feature_generator, generator  # noqa: F401  (pytest fixtures reused by name)

CANCELLATION = CancellationConfig(**json.loads((Path(__file__).parent.parent / "configs" / "cancellation.json").read_text()))


def _randomize_spectra(monkeypatch):
    """Wrap the fake simulator so every observation gets its own random spectrum (deterministic per call)."""
    inner = scenes.simulate_dual
    calls = {"n": 0}

    def simulate(cfg, **kwargs):
        result = inner(cfg, **kwargs)
        rng = np.random.default_rng([int(cfg.co.seed), calls["n"]])
        calls["n"] += 1
        result.spec_db = rng.normal(-80, 2, (2, 128, 512)).astype(np.float32)
        return result

    monkeypatch.setattr(scenes, "simulate_dual", simulate)


@pytest.fixture
def artifact(tmp_path, monkeypatch, feature_generator):
    """B2-feat/1 artifact: three groups per role, two groups per shard -> shard counts [16, 8] (last shard partial)."""
    _randomize_spectra(monkeypatch)
    root = tmp_path / "feat"
    ds.generate_b2_dataset(root, roles=BASE_ROLES, limit_groups=3, groups_per_shard=2, cancellation=CANCELLATION)
    return root


def _cfg(**overrides):
    base = dict(labels=LABELS, input_mode="dual_residual", plan_consistency=True, center_loss_weight=0.005,
                plan_shift_fraction=0.5, epochs=2, batch=8, width=4, augment=True)
    return TrainConfig(**{**base, **overrides})


def _state_equal(a, b):
    return all(torch.equal(a.state_dict()[k], b.state_dict()[k]) for k in a.state_dict())


# ---- 1. sample parity, provenance identity -------------------------------------------------------

def test_open_known_matches_legacy_split_fingerprint_and_fetch(artifact):
    manifest, identity, sources = open_b2_known(artifact)
    assert identity == ds.b2_fingerprint(artifact) and manifest["protocol"] == "B2-feat/1"
    assert set(sources) == set(BASE_ROLES)
    for role, source in sources.items():
        loaded = ds.load_b2_split(artifact, role)
        assert source.shard_counts == [16, 8] and source.has_residual and len(source) == 24
        streamed = {key: np.concatenate([shard[key] for shard in source.shards()]) for key in ("spec", "mask", "residual", "label", "seed", "plan_consistency")}
        for key, values in streamed.items():
            np.testing.assert_array_equal(values, loaded[key])
        split = source.split()
        assert split["label"].tolist() == loaded["label"].tolist() and split["seed"].tolist() == loaded["seed"].tolist()
        assert [record["scenario_id"] for record in split["meta"]] == [record["scenario_id"] for record in loaded["meta"]]
        assert "plans" not in split["meta"][0]                    # only a small projection stays resident
        assert source.groups.tolist() == scenario_ids(role, 3)
        rows = source.fetch([17, 0, 5])
        for key in ("spec", "mask", "residual"):
            np.testing.assert_array_equal(rows[key], loaded[key][[17, 0, 5]])
    with pytest.raises(ValueError, match="valid sample positions"):
        sources["train"].fetch([24])


def test_iter_b2_shards_accepts_orders_and_rejects_bad_indices(artifact):
    canonical = [shard["seed"][0] for shard in ds.iter_b2_shards(artifact, "train")]
    assert [shard["seed"][0] for shard in ds.iter_b2_shards(artifact, "train", [1, 0])] == canonical[::-1]
    assert [shard["seed"][0] for shard in ds.iter_b2_shards(artifact, "train", [1])] == canonical[1:]
    for bad in ([0, 0], [2], [True], [0.5]):
        with pytest.raises(ValueError, match="shard ind"):
            list(ds.iter_b2_shards(artifact, "train", bad))
    _, _, sources = open_b2_known(artifact)
    for bad in ([0, 0], [True, False], [2]):
        with pytest.raises(ValueError, match="distinct shard indices"):
            list(sources["train"].shards(bad))


def test_streaming_inference_matches_legacy_inference(artifact):
    _, _, sources = open_b2_known(artifact)
    train, val = ds.load_b2_split(artifact, "train"), ds.load_b2_split(artifact, "val-select")
    fitted = legacy.fit(train, val, _cfg(epochs=1, plan_shift_fraction=0.0, augment=False), device="cpu", log=lambda *_: None)
    reference, streamed = legacy.infer(fitted, val), infer_streaming(fitted, sources["val-select"])
    # Eval-mode networks are per-sample; batch boundaries differ (64 vs one shard), so float tolerance 1e-5.
    np.testing.assert_allclose(streamed["logits"], reference["logits"], atol=1e-5)
    np.testing.assert_allclose(streamed["embedding"], reference["embedding"], atol=1e-5)
    np.testing.assert_allclose(streamed["plan_logits"], reference["plan_logits"], atol=1e-5)
    with pytest.raises(ValueError, match="stored cancellation residual"):
        infer_streaming(fitted, B2Source.from_arrays({k: v for k, v in val.items() if k != "residual"}))


def test_single_window_training_is_bit_identical_to_legacy_including_k17b_and_augmentation(artifact):
    _, _, sources = open_b2_known(artifact)
    cfg = _cfg()
    reference = legacy.fit(ds.load_b2_split(artifact, "train"), ds.load_b2_split(artifact, "val-select"), cfg,
                           device="cpu", log=lambda *_: None)
    streamed = fit_streaming(sources["train"], sources["val-select"], cfg, window_shards=2, device="cpu", log=lambda *_: None)
    assert _state_equal(reference["model"], streamed["model"])
    assert streamed["history"] == reference["history"] and streamed["absolute_ref_db"] == reference["absolute_ref_db"]
    assert streamed["best_epoch"] == reference["best_epoch"]
    assert streamed["streaming"]["shard_orders"] == [[0, 1], [0, 1]] and streamed["streaming"]["window_shards"] == 2


# ---- 2. deterministic ordering, carry across windows, replay ---------------------------------------

def _epoch_batches(source, cfg, window_shards, seed, order=None):
    gen = torch.Generator().manual_seed(seed)
    ref = st._training_reference(source, cfg)
    order = list(range(source.n_shards)) if order is None else order
    return [batch["seed"].tolist() for batch in st._batches(source, cfg, ref, gen, window_shards, cfg.plan_shift_fraction > 0, order)]


def test_batches_cover_every_sample_once_with_exact_batch_sizes_and_carry(artifact):
    _, _, sources = open_b2_known(artifact)
    train = sources["train"]
    for batch_size, expected_sizes in ((8, [8, 8, 8]), (12, [12, 12]), (10, [10, 10, 4]), (16, [16, 8]), (5, [5] * 4 + [4])):
        cfg = _cfg(batch=batch_size, plan_shift_fraction=0.0)
        batches = _epoch_batches(train, cfg, 1, seed=3)
        assert [len(batch) for batch in batches] == expected_sizes         # remainders carried across the two shards
        assert sorted(seed for batch in batches for seed in batch) == sorted(train.index["seed"].tolist())
        assert sum(len(b) for b in batches) == 24 and len(batches) == -(-24 // batch_size)
    # Within a one-shard window the first batch holds only that shard's groups (before the carry).
    first = _epoch_batches(train, _cfg(batch=8, plan_shift_fraction=0.0), 1, seed=3)[0]
    assert set(first) <= set(train.index["seed"][:16].tolist())
    # Window at least as large as the shard count with N % batch != 0: one window, the remainder is the final batch.
    single = _epoch_batches(train, _cfg(batch=10, plan_shift_fraction=0.0), 2, seed=3)
    assert [len(batch) for batch in single] == [10, 10, 4]
    assert sorted(seed for batch in single for seed in batch) == sorted(train.index["seed"].tolist())


def test_batch_order_is_reproducible_per_seed_and_recorded(artifact):
    _, _, sources = open_b2_known(artifact)
    cfg = _cfg(batch=8, plan_shift_fraction=0.0)
    assert _epoch_batches(sources["train"], cfg, 1, seed=11) == _epoch_batches(sources["train"], cfg, 1, seed=11)
    assert _epoch_batches(sources["train"], cfg, 1, seed=11) != _epoch_batches(sources["train"], cfg, 1, seed=12)
    assert _epoch_batches(sources["train"], cfg, 1, seed=11, order=[1, 0]) != _epoch_batches(sources["train"], cfg, 1, seed=11)
    one = fit_streaming(sources["train"], sources["val-select"], _cfg(epochs=1, batch=8), window_shards=1, device="cpu", log=lambda *_: None)
    two = fit_streaming(sources["train"], sources["val-select"], _cfg(epochs=1, batch=8), window_shards=1, device="cpu", log=lambda *_: None)
    assert _state_equal(one["model"], two["model"]) and one["history"] == two["history"]
    assert one["streaming"]["shard_orders"] == two["streaming"]["shard_orders"]
    assert sorted(one["streaming"]["shard_orders"][0]) == [0, 1] and one["streaming"]["train_shard_counts"] == [16, 8]


# ---- 3. roles and leakage ---------------------------------------------------------------------------

def test_fit_refuses_group_leakage_wrong_roles_and_test_only_sources(artifact):
    _, _, sources = open_b2_known(artifact)
    cfg = _cfg(epochs=1)
    # The source carries its frozen role: only train fits weights, only val-select selects.
    for bad_train, bad_val, message in ((sources["test"], sources["val-select"], "'train' role"),
                                        (sources["val-calib"], sources["val-select"], "'train' role"),
                                        (sources["train"], sources["test"], "'val-select' role"),
                                        (sources["train"], sources["val-calib"], "'val-select' role")):
        with pytest.raises(ValueError, match=message):
            fit_streaming(bad_train, bad_val, cfg, device="cpu", log=lambda *_: None)
    with pytest.raises(ValueError, match="disjoint"):
        fit_streaming(B2Source.from_arrays(ds.load_b2_split(artifact, "train")),
                      B2Source.from_arrays(ds.load_b2_split(artifact, "train")), cfg, device="cpu", log=lambda *_: None)
    from test_b2_experiment import _matched_split
    matched = B2Source.from_arrays(_matched_split(2, 1), kind="matched", role="test-matched")
    with pytest.raises(ValueError, match="matched evaluation set"):
        fit_streaming(matched, sources["val-select"], cfg, device="cpu", log=lambda *_: None)
    train = ds.load_b2_split(artifact, "train")
    with pytest.raises(ValueError, match="outside its frozen"):
        B2Source.from_arrays(train, role="val-select")
    mixed = dict(train)
    mixed["seed"] = train["seed"].copy()
    mixed["seed"][:8] = ROLE_STARTS["test"]
    with pytest.raises(ValueError, match="outside its frozen"):
        B2Source.from_arrays(mixed, role="train")
    from test_b2_experiment import _unknown_split
    unknown = B2Source.from_arrays(_unknown_split(2, 1), kind="test", role="test")
    with pytest.raises(ValueError, match="test-only families"):
        fit_streaming(unknown, sources["val-select"], cfg, device="cpu", log=lambda *_: None)
    with pytest.raises(ValueError, match="test-matched role"):
        B2Source.from_arrays({**train, "matched_bin": np.zeros(24, np.int8)}, kind="matched", role="test-matched")


# ---- 4. provenance and stage ---------------------------------------------------------------------------

def test_tampered_request_or_manifest_fails_closed(artifact):
    request = artifact / "request.json"
    original = request.read_text()
    request.write_text(original.replace('"limit_groups": 3', '"limit_groups": 2'))
    with pytest.raises(ValueError, match="invalid B2 base dataset"):
        open_b2_known(artifact)
    request.write_text(original)
    manifest = artifact / "manifest.json"
    text = manifest.read_text()
    manifest.write_text(text.replace('"benchmark_complete": false', '"benchmark_complete": true'))
    with pytest.raises(ValueError, match="invalid B2 base dataset"):
        open_b2_known(artifact)
    manifest.write_text(text)
    assert open_b2_known(artifact)[1] == ds.b2_fingerprint(artifact)


def test_base_stage_artifact_has_no_residual_and_feature_experiments_refuse_it(tmp_path, monkeypatch, generator):
    _randomize_spectra(monkeypatch)
    root = tmp_path / "base"
    ds.generate_b2_dataset(root, roles=BASE_ROLES, limit_groups=1, groups_per_shard=1)
    manifest, identity, sources = open_b2_known(root)
    assert manifest["protocol"] == "B2-base/1" and not sources["train"].has_residual
    with pytest.raises(ValueError, match="stored cancellation residual"):
        fit_streaming(sources["train"], sources["val-select"], _cfg(epochs=1), device="cpu", log=lambda *_: None)
    config = B2ExperimentConfig(views=("dual_residual",), training={"epochs": 1, "batch": 8, "width": 4, "seed": 0,
                                                                   "center_loss_weight": 0.005, "augment": False})
    # The protocol check precedes the residual check; a feature stage without residual cannot exist by construction.
    with pytest.raises(ValueError, match="does not match"):
        run_b2_experiment(config, root, tmp_path / "run", log=lambda *_: None)
    # A manifest retagged as the feature stage is inconsistent with its request and never verifies.
    manifest = root / "manifest.json"
    text = manifest.read_text()
    manifest.write_text(text.replace('"protocol": "B2-base/1"', '"protocol": "B2-feat/1"', 1))
    with pytest.raises(ValueError, match="invalid B2 base dataset"):
        open_b2_known(root)
    manifest.write_text(text)
    base_config = B2ExperimentConfig(protocol="B2-base/1", views=("co",), window_shards=1, training=config.training)
    result = run_b2_experiment(base_config, root, tmp_path / "base-run", log=lambda *_: None)
    assert result["protocol"] == "B2-base/1" and result["methods"]["co"]["input_channels"] == 2


# ---- 5./6./7. corruption, duplicates, incomplete artifacts, resume ----------------------------------------

def test_corrupted_missing_or_incomplete_shards_fail_closed_before_and_during_streaming(artifact):
    _, _, sources = open_b2_known(artifact)
    part = artifact / "train" / "part-00001.npz"
    payload = part.read_bytes()
    with part.open("ab") as stream:
        stream.write(b"x")
    with pytest.raises(ValueError, match="modified"):
        list(sources["train"].shards())            # verified again at read time, after the index was built
    with pytest.raises(ValueError, match="modified"):
        open_b2_known(artifact)
    part.write_bytes(payload)
    assert len(list(sources["train"].shards())) == 2
    meta = artifact / "val-calib" / "meta-00000.jsonl"
    saved = meta.read_bytes()
    meta.unlink()
    with pytest.raises(ValueError, match="missing"):
        open_b2_known(artifact)
    meta.write_bytes(saved)
    manifest = artifact / "manifest.json"
    saved_manifest = manifest.read_bytes()
    manifest.unlink()
    with pytest.raises(ValueError, match="invalid B2 base dataset"):
        open_b2_known(artifact)              # incomplete (unfinished) generation never streams
    manifest.write_bytes(saved_manifest)
    # Resume of a finished artifact is a verified no-op and keeps the identity.
    ds.generate_b2_dataset(artifact, roles=BASE_ROLES, limit_groups=3, groups_per_shard=2, cancellation=CANCELLATION)
    assert open_b2_known(artifact)[1] == ds.b2_fingerprint(artifact)


def test_duplicate_groups_and_index_drift_are_rejected(artifact, monkeypatch):
    train = ds.load_b2_split(artifact, "train")
    duplicated = {**train, "seed": train["seed"].copy()}
    duplicated["seed"][8:16] = duplicated["seed"][:8]
    with pytest.raises(ValueError, match="duplicate scenario-group/label"):
        B2Source.from_arrays(duplicated, role="train")
    _, _, sources = open_b2_known(artifact)
    real = ds.iter_b2_shards

    def swapped(root, role, indices=None):           # a reader that ignores the requested order
        yield from real(root, role, [1, 0])

    monkeypatch.setattr(st, "iter_b2_shards", swapped)
    _, _, drifted = open_b2_known(artifact)
    with pytest.raises(ValueError, match="changed since the artifact was indexed"):
        list(drifted["train"].shards())
    monkeypatch.setattr(st, "iter_b2_shards", real)
    assert len(list(sources["train"].shards())) == 2


def test_in_memory_source_contract():
    from test_b2_experiment import _split
    split = _split("train", 2, 0)
    source = B2Source.from_arrays(split, role="train")
    assert source.n_shards == 1 and len(source) == 16 and source.has_residual
    assert [shard["offset"] for shard in source.shards()] == [0]
    with pytest.raises(ValueError, match="needs spec and mask"):
        B2Source.from_arrays({"label": split["label"]})
    bad = dict(split)
    bad["plan_consistency"] = np.full(16, 2, np.int8)
    with pytest.raises(ValueError, match="plan_consistency"):
        B2Source.from_arrays(bad)
    bad = dict(split)
    bad["label"] = np.full(16, 9, np.int8)
    with pytest.raises(ValueError, match="out-of-range"):
        B2Source.from_arrays(bad)
    with pytest.raises(ValueError, match="kind must be"):
        B2Source("other", source.index, [16], lambda order: iter([]), has_residual=True)


# ---- 8.-11. end-to-end runner on a disk artifact: thresholds, Mahalanobis, outputs, reuse ----------------

def test_runner_streams_a_disk_artifact_with_frozen_roles_thresholds_and_compatible_outputs(artifact, tmp_path):
    config = B2ExperimentConfig(views=("co", "dual_residual"), window_shards=1,
                                training={"epochs": 1, "batch": 8, "width": 4, "seed": 0, "center_loss_weight": 0.005,
                                          "augment": False, "plan_shift_fraction": 0.5})
    out = tmp_path / "run"
    logs = []
    result = run_b2_experiment(config, artifact, out, log=logs.append)
    assert result["data_fingerprint"] == ds.b2_fingerprint(artifact) and result["benchmark_complete"] is False
    assert result["runtime"]["loader"] == {"mode": "streaming", "window_shards": 1,
                                           "shard_counts": {role: [16, 8] for role in BASE_ROLES},
                                           "note": result["runtime"]["loader"]["note"]}
    for role in BASE_ROLES:
        assert result["partitions"][role]["scenario_ids"] == scenario_ids(role, 3)
        assert result["partitions"][role]["n_samples"] == 24
    for view in config.views:
        values = result["methods"][view]
        scorer = values["mahalanobis_scorer"]
        assert scorer["n_training"] == 24 and scorer["class_counts"] == [3] * 8      # train role only
        for metrics in values["rejection"].values():
            assert metrics["calibration"]["n_calibration"] == 24                      # val-calib known only
        assert values["alarm"]["n_clean_calibration"] == 3
        assert sum(sum(row) for row in values["confusion"]) == 24
        assert values["plan_consistency"]["n_samples"] == 24
    assert len(json.loads((out / "predictions.json").read_text())) == 24
    summary = json.loads((out / "results_summary.json").read_text())
    assert summary["summary_rule"]["dropped_keys"] == list(__import__("geoml.b2_experiment", fromlist=["x"]).SUMMARY_DROPPED)
    assert set(summary["methods"]["co"]) == set(result["methods"]["co"]) - {"history", "confusion", "mahalanobis_scorer"}
    assert "## Partitions" in (out / "results.md").read_text()
    assert any("streaming 1 shard" in line for line in logs)
    # Frozen thresholds and checkpoints are reused unchanged; a different window policy changes the fingerprint only.
    again = run_b2_experiment(config, artifact, out, reuse=True, log=logs.append)
    assert again["methods"]["co"]["checkpoint_sha256"] == result["methods"]["co"]["checkpoint_sha256"]
    for view in config.views:
        for method in config.methods:
            assert again["methods"][view]["rejection"][method]["calibration"] == result["methods"][view]["rejection"][method]["calibration"]
    other = B2ExperimentConfig(**{**json.loads(json.dumps(config.resolved())), "window_shards": 2})
    assert other.resolved()["window_shards"] == 2 and other.resolved() != config.resolved()
    with pytest.raises(ValueError, match="window_shards"):
        B2ExperimentConfig(window_shards=0, training=config.training)


# ---- 12. bounded memory --------------------------------------------------------------------------------

_MEASURE = r"""
import json, resource, sys, time
sys.path.insert(0, "src")
import numpy as np, torch
from geoml.train import TrainConfig
from geosim.b2_protocol import LABELS
mode, root, out = sys.argv[1], sys.argv[2], sys.argv[3]
cfg = TrainConfig(labels=LABELS, input_mode="dual_residual", plan_consistency=True, center_loss_weight=0.005,
                  epochs=1, batch=8, width=4, augment=False)
def status(key):
    for line in open("/proc/self/status"):
        if line.startswith(key):
            return int(line.split()[1]) / 1024
baseline = status("VmRSS")
try:
    open("/proc/self/clear_refs", "w").write("5")    # reset the peak-RSS high-water mark after the imports
    reset = True
except OSError:
    reset = False
t = time.perf_counter()
if mode == "legacy":
    from geoml import train
    from geosim.b2_dataset import load_b2_split
    tr, va = load_b2_split(root, "train"), load_b2_split(root, "val-select")
    fitted = train.fit(tr, va, cfg, device="cpu", log=lambda *_: None)
    train.infer(fitted, tr)
else:
    from geoml.b2_stream import open_b2_known, fit_streaming, infer_streaming
    _, _, sources = open_b2_known(root)
    fitted = fit_streaming(sources["train"], sources["val-select"], cfg, window_shards=1, device="cpu", log=lambda *_: None)
    infer_streaming(fitted, sources["train"])
json.dump({"mode": mode, "baseline_mib": baseline, "peak_mib": status("VmHWM"), "wall_s": time.perf_counter() - t,
           "peak_reset": reset, "lifetime_peak_mib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024}, open(out, "w"))
"""


def test_streaming_peak_memory_stays_below_the_whole_dataset_footprint(tmp_path, monkeypatch, feature_generator):
    """Measured in fresh subprocesses: legacy loads whole roles, streaming holds one shard window.

    Train and val-select: 12 groups × 8 = 96 observations each (6 shards of 16). Legacy
    materializes both float16 roles (≈38 MB each) plus their float32 inputs (≈63 MB each);
    streaming's window is one shard. The peak is the resident high-water mark *after* the
    imports (``/proc/self/clear_refs`` reset), so the torch import baseline drops out; the
    gap must exceed half of the preprocessed training tensor, a bound implied by the
    allocation pattern rather than a tuned number.
    """
    if not Path("/proc/self/clear_refs").exists():
        pytest.skip("peak-RSS reset needs Linux procfs")
    _randomize_spectra(monkeypatch)
    root = tmp_path / "big"
    ds.generate_b2_dataset(root, roles=("train", "val-select"), limit_groups=12, groups_per_shard=2, cancellation=CANCELLATION)
    env = {**os.environ, "OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1", "MPLBACKEND": "Agg"}
    results = {}
    for mode in ("legacy", "streaming"):
        out = tmp_path / f"{mode}.json"
        completed = subprocess.run([sys.executable, "-c", _MEASURE, mode, str(root), str(out)], env=env,
                                   cwd=Path(__file__).parent.parent, capture_output=True, text=True, timeout=600)
        assert completed.returncode == 0, completed.stderr[-2000:]
        results[mode] = json.loads(out.read_text())
        if not results[mode]["peak_reset"]:
            pytest.skip("this runner does not allow resetting the peak-RSS counter (/proc/self/clear_refs)")
    preprocessed_train_bytes = 96 * 5 * 64 * 512 * 4
    # Both increments contain the same fixed torch kernel/optimizer overhead (≈300 MiB on CPU builds, independent of
    # the data); only the data-dependent part differs, so the assertion is on the gap, not on an absolute number.
    legacy_increment = results["legacy"]["peak_mib"] - results["legacy"]["baseline_mib"]
    streaming_increment = results["streaming"]["peak_mib"] - results["streaming"]["baseline_mib"]
    assert legacy_increment - streaming_increment > 0.5 * preprocessed_train_bytes / 2**20, results

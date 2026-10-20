"""B2 known-base shards, frozen role boundaries and independent calibration."""
from dataclasses import asdict
import json
from types import SimpleNamespace

import numpy as np
import pytest

from geosim import b2_dataset as ds
from geosim import b2_scenarios as scenes
from geosim.b2_protocol import BASE_ROLES, LABELS, ROLE_STARTS, B2Config
from geosim.plan import plan_mask_db
from geosim.waveform import Carrier


@pytest.fixture
def generator(monkeypatch):
    calls = {"fit": 0, "simulate": []}
    real_fit = ds.fit_receiver_calibration

    def fit(*args, **kwargs):
        calls["fit"] += 1
        return real_fit(*args, **kwargs)

    def simulate(cfg, *, plans, interferers, active_carriers, calibration, keep_iq):
        calls["simulate"].append((cfg, plans, active_carriers, calibration))
        power = [sum(c.power for c, keep in zip(plan, active) if keep) for plan, active in zip(plans, active_carriers)]
        return SimpleNamespace(spec_db=np.full((2, 128, 512), -80, np.float32),
                               mask_db=np.stack([plan_mask_db(plan) for plan in plans]),
                               meta={"config": cfg.to_dict(), "plans": [[asdict(c) for c in plan] for plan in plans],
                                     "has_interferer": [event is not None for event in interferers],
                                     "has_downlink_interferer": [False, False],
                                     "active_carriers": [list(active) for active in active_carriers],
                                     "active_planned_power": power, "nominal_planned_power": [1., 1.],
                                     "gain_mode": "fixed_nominal_planned_power",
                                     "paths": [{"actual_ibo_db": cfg.co.ibo_db, "obo_db": 10.,
                                                "omux_output_power": 0.1, "receiver_noise_psd": 1e-10,
                                                "zero_drive": False} for _ in range(2)],
                                     "receiver_calibration_applied": True,
                                     "receiver_calibration": calibration.to_dict()})

    monkeypatch.setattr(ds, "fit_receiver_calibration", fit)
    monkeypatch.setattr(scenes, "simulate_dual", simulate)
    monkeypatch.setattr(ds, "_generator_provenance", lambda: {"unit_fixture": "0" * 64})
    return calls


@pytest.fixture
def generated(tmp_path, generator):
    root = tmp_path / "b2"
    ds.generate_b2_dataset(root, roles=("train",), limit_groups=2, groups_per_shard=1)
    return root, generator


def test_roles_known_labels_scope_and_pairing(tmp_path, generator):
    root = tmp_path / "all-roles"
    ds.generate_b2_dataset(root, limit_groups=1)
    manifest = ds.read_b2_manifest(root)
    assert manifest["protocol"] == "B2-base/1" and manifest["parent_protocol"] == "B2/1"
    assert manifest["benchmark_complete"] is False
    assert manifest["artifact_stage"] == "known_physical_observations"
    assert manifest["labels"] == list(LABELS)
    groups = []
    for role in BASE_ROLES:
        data = ds.load_b2_split(root, role)
        assert data["spec"].shape == (8, 2, 128, 512) and data["spec"].dtype == np.float16
        assert data["mask"].shape == (8, 2, 512)
        assert data["label"].tolist() == list(range(8))
        assert data["seed"].tolist() == [ROLE_STARTS[role]] * 8
        assert set(data["plan_consistency"]) <= {0, 1}
        assert all(not set(data["seed"]) & earlier for earlier in groups)
        groups.append(set(data["seed"]))
    assert len(generator["simulate"]) == 32 and generator["fit"] == 1
    assert len(ds.b2_fingerprint(root)) == 64
    assert "cid_overlay" not in manifest["labels"]


def test_independent_calibration_shared_and_bound_to_base_request(generated):
    root, calls = generated
    calibration = calls["simulate"][0][3]
    assert calls["fit"] == 1 and all(call[3] is calibration for call in calls["simulate"])
    assert calibration.provenance.startswith("B2-base/1:")
    assert calibration.provenance.endswith(":independent_pilots")
    np.testing.assert_allclose(calibration.response, ds.receiver_response(B2Config()), atol=1e-3)
    assert ds.read_b2_manifest(root)["calibration"] == calibration.to_dict()


def test_natural_missing_carrier_survives_verified_artifact_round_trip(tmp_path, generator):
    root = tmp_path / "natural-missing"
    # The first natural missing-carrier group is 3000008. Preserve the frozen
    # RNG and role prefix rather than forcing a diagnostic override.
    ds.generate_b2_dataset(root, roles=("train",), limit_groups=9, groups_per_shard=8)
    manifest = ds.read_b2_manifest(root)
    assert manifest["roles"]["train"]["n_scenarios"] == 9
    assert manifest["roles"]["train"]["n_samples"] == 72
    parts = list(ds.iter_b2_shards(root, "train"))
    assert [len(part["label"]) for part in parts] == [64, 8]
    assert parts[0]["plan_consistency"].tolist() == [0] * 64
    assert parts[1]["plan_consistency"].tolist() == [1] * 8
    loaded = ds.load_b2_split(root, "train")
    assert loaded["plan_consistency"].tolist() == [0] * 64 + [1] * 8
    assert loaded["seed"][-8:].tolist() == [3_000_008] * 8
    for mask, record in zip(loaded["mask"][-8:], loaded["meta"][-8:]):
        assert record["missing_carrier_override"] is None
        assert record["gain_mode"] == "fixed_nominal_planned_power"
        assert record["nominal_planned_power"] == [1., 1.]
        dropped = record["dropped_carrier"]
        pol, index = dropped["polarization"], dropped["index"]
        assert record["active_carriers"][pol][index] is False
        plans = [[Carrier(**item) for item in plan] for plan in record["plans"]]
        np.testing.assert_allclose([sum(c.power for c in plan) for plan in plans], [1., 1.], atol=1e-12)
        expected_mask = np.stack([plan_mask_db(plan) for plan in plans]).astype(np.float16)
        np.testing.assert_array_equal(mask, expected_mask)
        assert record["active_planned_power"][pol] < 1
        np.testing.assert_allclose(record["active_planned_power"][pol], 1 - plans[pol][index].power, atol=1e-12)


def test_pilot_namespace_remains_distinct_when_calibration_seed_equals_scene_group(monkeypatch):
    config = B2Config(calibration_seed=ROLE_STARTS["train"])
    captured = []
    real_fit = ds.fit_receiver_calibration

    def fit(reference, measured, **kwargs):
        captured.append(reference)
        return real_fit(reference, measured, **kwargs)

    monkeypatch.setattr(ds, "fit_receiver_calibration", fit)
    ds._fit_calibration(config, "request")
    scene_rng = np.random.default_rng([config.calibration_seed, 1801])
    link_stream = scene_rng.standard_normal((2, config.calibration_samples))
    assert not np.array_equal(captured[0].real * np.sqrt(2), link_stream)
    pilot_rng = np.random.default_rng([config.calibration_seed, 18001])
    np.testing.assert_allclose(captured[0].real * np.sqrt(2),
                               pilot_rng.standard_normal((2, config.calibration_samples)), rtol=1e-15, atol=0)


def test_completed_resume_is_immutable_and_historical_read_does_not_replay(generated, monkeypatch):
    root, calls = generated
    contents = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    identity = ds.b2_fingerprint(root)
    monkeypatch.setattr(ds, "_commit", lambda: "later-docs-commit")
    ds.generate_b2_dataset(root, roles=("train",), limit_groups=2, groups_per_shard=1)
    assert {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()} == contents
    assert calls["fit"] == 1 and len(calls["simulate"]) == 16
    monkeypatch.setattr(ds, "_generator_provenance", lambda: {"new_source": "1" * 64})
    monkeypatch.setattr(ds, "sample_scene", lambda *a, **k: pytest.fail("historical reads must not replay scenes"))
    monkeypatch.setattr(scenes, "_plans", lambda *a, **k: pytest.fail("historical reads must not replay plans"))
    assert ds.b2_fingerprint(root) == identity
    with pytest.raises(ValueError, match="request changed"):
        ds.generate_b2_dataset(root, roles=("train",), limit_groups=2, groups_per_shard=1)


def test_partial_resume_reuses_verified_shards_and_calibration(generated):
    root, calls = generated
    (root / "manifest.json").unlink()
    contents = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    ds.generate_b2_dataset(root, roles=("train",), limit_groups=2, groups_per_shard=1)
    assert all((root / path).read_bytes() == value for path, value in contents.items())
    assert calls["fit"] == 1 and len(calls["simulate"]) == 16


@pytest.mark.parametrize("change", [{"roles": ("test",)}, {"limit_groups": 1}, {"groups_per_shard": 2},
                                    {"config": B2Config(calibration_seed=99)}])
def test_changed_generation_request_cannot_rewrite(generated, change):
    root, _ = generated
    kwargs = {"roles": ("train",), "limit_groups": 2, "groups_per_shard": 1, **change}
    before = (root / "manifest.json").read_bytes()
    with pytest.raises(ValueError, match="request changed"):
        ds.generate_b2_dataset(root, **kwargs)
    assert (root / "manifest.json").read_bytes() == before


@pytest.mark.parametrize("filename", ["receiver_calibration.npz", "train/part-00000.npz", "train/meta-00000.jsonl"])
def test_corruption_rejected_by_all_complete_readers_and_resume(generated, filename):
    root, _ = generated
    with (root / filename).open("ab") as stream:
        stream.write(b"modified")
    for action in (lambda: ds.read_b2_manifest(root), lambda: ds.load_b2_split(root, "train"),
                   lambda: ds.b2_fingerprint(root),
                   lambda: ds.generate_b2_dataset(root, roles=("train",), limit_groups=2, groups_per_shard=1)):
        with pytest.raises(ValueError, match="modified"):
            action()


def test_lazy_iterator_loads_only_requested_shard_at_each_step(generated, monkeypatch):
    root, _ = generated
    loaded, real_read = [], ds._read_part

    def read(part, *args, **kwargs):
        loaded.append(part.name)
        return real_read(part, *args, **kwargs)

    monkeypatch.setattr(ds, "_read_part", read)
    iterator = ds.iter_b2_shards(root, "train")
    assert loaded == []
    assert next(iterator)["spec"].shape[0] == 8
    assert loaded == ["part-00000.npz"]
    assert next(iterator)["spec"].shape[0] == 8
    assert loaded == ["part-00000.npz", "part-00001.npz"]
    with pytest.raises(StopIteration):
        next(iterator)


def _rewrite_metadata(root, records):
    path = root / "train/meta-00000.jsonl"
    path.write_text("".join(json.dumps(record) + "\n" for record in records).replace('"overflow_fixture"', "1e999"))
    descriptor_path = root / "train/shard-00000.json"
    descriptor = json.loads(descriptor_path.read_text())
    descriptor["sha256"][path.name] = ds._file_hash(path)
    descriptor_path.write_text(json.dumps(descriptor))
    manifest = json.loads((root / "manifest.json").read_text())
    manifest["roles"]["train"]["shards"][0] = descriptor
    (root / "manifest.json").write_text(json.dumps(manifest))


@pytest.mark.parametrize("mutation,match", [("role", "metadata"), ("stage", "injection stage"),
                                           ("phase", "configuration"), ("nominal", "nominal payload"),
                                           ("pairing", "paired B2"), ("consistency", "metadata"),
                                           ("active", "active-carrier"), ("gain", "fixed-gain"),
                                           ("victim", "active planned victim"),
                                           ("plan_source", "conditioning provenance"),
                                           ("unauthorized_power", "PSD convention"),
                                           ("asi_power", "PSD convention"), ("asi_overlap", "PSD convention"),
                                           ("nan", "nonfinite JSON"), ("overflow", "nonfinite JSON")])
def test_rehashed_metadata_still_rejects_semantic_corruption(generated, mutation, match):
    root, _ = generated
    records = [json.loads(line) for line in (root / "train/meta-00000.jsonl").read_text().splitlines()]
    if mutation == "role":
        records[0]["role"] = "test"
    elif mutation == "stage":
        records[6]["event"]["injection_stage"] = "downlink"
    elif mutation == "phase":
        records[1]["config"]["satellite_linewidth_hz"] = 0
    elif mutation == "nominal":
        records[1]["config"]["co"]["ibo_db"] += 0.1
    elif mutation == "pairing":
        records[1]["config"]["co"]["cn_up_db"] += 0.01
    elif mutation == "consistency":
        records[1]["plan_consistency"] = 1
    elif mutation == "active":
        records[0]["active_carriers"][0][0] = 1
    elif mutation == "gain":
        records[0]["gain_mode"] = "renormalized"
    elif mutation == "victim":
        records[7]["event"]["victim_active"] = False
    elif mutation == "plan_source":
        records[1]["operator_plan_source"]["co_initial_seed"] += 1
    elif mutation == "unauthorized_power":
        records[3]["event"]["c_over_i_db"] += 1
    elif mutation == "asi_power":
        records[6]["event"]["carrier"]["power"] *= 2
        records[6]["event"]["c_over_i_db"] -= 10 * np.log10(2)
    elif mutation == "asi_overlap":
        old = records[6]["event"]["overlap_fraction"]
        records[6]["event"]["overlap_fraction"] = .3 if old != .3 else .4
    elif mutation == "nan":
        records[0]["unused_truth"] = float("nan")
    else:
        records[0]["unused_truth"] = "overflow_fixture"
    _rewrite_metadata(root, records)
    with pytest.raises(ValueError, match=match):
        ds.read_b2_manifest(root)


def test_unverified_partial_shard_is_not_silently_overwritten(generated):
    root, _ = generated
    (root / "manifest.json").unlink()
    (root / "train/shard-00000.json").unlink()
    before = (root / "train/part-00000.npz").read_bytes()
    with pytest.raises(ValueError, match="unverified partial B2 shard"):
        ds.generate_b2_dataset(root, roles=("train",), limit_groups=2, groups_per_shard=1)
    assert (root / "train/part-00000.npz").read_bytes() == before


@pytest.mark.parametrize("kwargs", [{"roles": []}, {"roles": ["test-matched"]}, {"roles": ["train", "train"]},
                                    {"roles": ["unknown"]}, {"limit_groups": 0}, {"limit_groups": True},
                                    {"limit_groups": 151}, {"groups_per_shard": 0}, {"groups_per_shard": 101}])
def test_invalid_selection_writes_nothing(tmp_path, kwargs):
    with pytest.raises(ValueError):
        ds.generate_b2_dataset(tmp_path / "bad", **kwargs)
    assert not list(tmp_path.iterdir())


def test_missing_and_reserved_roles_rejected(generated):
    root, _ = generated
    for role in ("validation", "test-matched", "val-calib"):
        with pytest.raises(ValueError, match="role"):
            ds.load_b2_split(root, role)
    (root / "test-matched").mkdir()
    with pytest.raises(ValueError, match="reserved role"):
        ds.read_b2_manifest(root)


def test_cli_preserves_config_and_limits(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"calibration_seed": 7}))
    calls = []
    monkeypatch.setattr(ds, "generate_b2_dataset", lambda out, cfg, **kwargs: calls.append((out, cfg, kwargs)))
    ds.main(["--out", str(tmp_path / "data"), "--config", str(path), "--roles", "train", "test",
             "--limit-groups", "2", "--groups-per-shard", "1"])
    assert calls[0][1].calibration_seed == 7
    assert calls[0][2] == {"roles": ["train", "test"], "limit_groups": 2, "groups_per_shard": 1, "cancellation": None}


def test_numpy_integer_limits_are_normalized_for_request_json(tmp_path, generator):
    root = tmp_path / "integer-selection"
    ds.generate_b2_dataset(root, roles=("train",), limit_groups=np.int64(1), groups_per_shard=np.int64(1))
    request = json.loads((root / "request.json").read_text())
    assert type(request["limit_groups"]) is int and type(request["groups_per_shard"]) is int


# ---- B2-feat/1: stored observation-based cancellation residual (fifth channel) ----

@pytest.fixture
def feature_generator(monkeypatch, generator):
    """Fake simulator with IQ and a fake canceller that records exactly what it was given."""
    from types import SimpleNamespace as NS
    from geosim import cancellation as cx
    calls = {"cancel": []}
    inner = scenes.simulate_dual          # the base fixture's fake, captured before patching again

    def simulate(cfg, *, plans, interferers, active_carriers, calibration, keep_iq):
        base = inner(cfg, plans=plans, interferers=interferers, active_carriers=active_carriers,
                     calibration=calibration, keep_iq=False)
        iq = None
        if keep_iq:
            rng = np.random.default_rng([int(cfg.co.seed), 99])
            iq = (rng.standard_normal((2, 128, 4096)) + 1j * rng.standard_normal((2, 128, 4096))).astype(np.complex64)
        return NS(spec_db=base.spec_db, mask_db=base.mask_db, meta=dict(base.meta), iq=iq)

    def cancel(iq, plan, config=None):
        calls["cancel"].append((np.asarray(iq).copy(), list(plan), config))
        rng = np.random.default_rng(int(np.abs(iq[0, 0].real) * 1e6) % 1000)
        return NS(residual_iq=iq, residual_db=rng.normal(-95, 1, (128, 512)).astype(np.float32),
                  carriers=[{"plan_index": i, "f0": c.f0, "symbol_rate": c.symbol_rate, "mod": c.mod,
                             "samples_per_symbol": 60, "symbols_per_snapshot": 200, "timing_samples": [0] * 128,
                             "gain_power_db_mean": 0.0, "decision_snr_db_median": 20.0,
                             "basis": "observed IQ and operator plan only"} for i, c in enumerate(plan)],
                  config=config)

    monkeypatch.setattr(scenes, "simulate_dual", simulate)
    monkeypatch.setattr(ds, "cancel_planned_carriers", cancel)
    return {**generator, **calls}


def test_feature_stage_stores_residual_from_co_iq_and_co_plan_only(tmp_path, feature_generator):
    from geosim.cancellation import CancellationConfig
    root = tmp_path / "feat"
    config = CancellationConfig(iterations=2)
    ds.generate_b2_dataset(root, roles=("train", "test"), limit_groups=1, groups_per_shard=1, cancellation=config)
    manifest = ds.read_b2_manifest(root)
    assert manifest["protocol"] == "B2-feat/1" and manifest["parent_protocol"] == "B2/1"
    assert manifest["artifact_stage"] == "known_physical_observations_with_cancellation_residual"
    assert manifest["benchmark_complete"] is False
    assert manifest["cancellation"] == config.to_dict() and manifest["request"]["cancellation"] == config.to_dict()
    assert manifest["fifth_channel"]["name"] == "co_pol_cancellation_residual"
    data = ds.load_b2_split(root, "train")
    assert data["residual"].shape == (8, 128, 512) and data["residual"].dtype == np.float16
    assert data["spec"].shape == (8, 2, 128, 512)
    assert len(feature_generator["cancel"]) == 16
    for (iq, plan, used), record in zip(feature_generator["cancel"], data["meta"] + ds.load_b2_split(root, "test")["meta"]):
        assert iq.shape == (128, 4096) and used == config
        assert [asdict(c) for c in plan] == record["plans"][0]            # co-pol operator plan, not activity
        assert record["cancellation"]["inputs"].startswith("calibrated co-pol monitor IQ")
        assert len(record["cancellation"]["carriers"]) == len(record["plans"][0])
    # Every simulate call for the feature stage asked for IQ; raw IQ is not stored.
    with np.load(root / "train" / "part-00000.npz") as archive:
        assert set(archive.files) == {"spec", "mask", "label", "seed", "plan_consistency", "residual"}
    assert "iq" not in json.loads((root / "train" / "meta-00000.jsonl").read_text().splitlines()[0])
    assert manifest["request_fingerprint"] != ds._fingerprint(ds._request(B2Config(), ["train", "test"], 1, 1))


def test_feature_stage_resume_and_cross_stage_rejection(tmp_path, feature_generator):
    from geosim.cancellation import CancellationConfig
    root = tmp_path / "feat"
    ds.generate_b2_dataset(root, roles=("train",), limit_groups=1, groups_per_shard=1,
                           cancellation=CancellationConfig())
    before = ds.b2_fingerprint(root)
    n_cancel = len(feature_generator["cancel"])
    ds.generate_b2_dataset(root, roles=("train",), limit_groups=1, groups_per_shard=1,
                           cancellation=CancellationConfig())
    assert ds.b2_fingerprint(root) == before and len(feature_generator["cancel"]) == n_cancel
    with pytest.raises(ValueError, match="request changed"):
        ds.generate_b2_dataset(root, roles=("train",), limit_groups=1, groups_per_shard=1)
    with pytest.raises(ValueError, match="request changed"):
        ds.generate_b2_dataset(root, roles=("train",), limit_groups=1, groups_per_shard=1,
                               cancellation=CancellationConfig(iterations=5))


def test_base_stage_is_unchanged_and_rejects_residual_or_cancellation_metadata(tmp_path, generator):
    root = tmp_path / "base"
    ds.generate_b2_dataset(root, roles=("train",), limit_groups=1, groups_per_shard=1)
    request = json.loads((root / "request.json").read_text())
    assert request["protocol"] == "B2-base/1" and "cancellation" not in request and "fifth_channel" not in request
    manifest = json.loads((root / "manifest.json").read_text())
    assert "cancellation" not in manifest and "residual" not in ds.load_b2_split(root, "train")
    part = root / "train" / "part-00000.npz"
    with np.load(part) as archive:
        arrays = {key: archive[key] for key in archive.files}
    np.savez(part, **arrays, residual=np.zeros((8, 128, 512), np.float16))
    with pytest.raises(ValueError, match="modified|array keys"):
        ds.read_b2_manifest(root)


def test_feature_stage_detects_corrupt_residual_and_provenance(tmp_path, feature_generator):
    from geosim.cancellation import CancellationConfig
    root = tmp_path / "feat"
    ds.generate_b2_dataset(root, roles=("train",), limit_groups=1, groups_per_shard=1,
                           cancellation=CancellationConfig())
    part = root / "train" / "part-00000.npz"
    descriptor = root / "train" / "shard-00000.json"
    with np.load(part) as archive:
        arrays = {key: archive[key] for key in archive.files}
    arrays["residual"][0, 0, 0] = np.float16(np.inf)
    np.savez(part, **arrays)
    info = json.loads(descriptor.read_text())
    info["sha256"][part.name] = ds._file_hash(part)
    descriptor.write_text(json.dumps(info))
    manifest = json.loads((root / "manifest.json").read_text())
    manifest["roles"]["train"]["shards"][0] = info
    (root / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="residual"):
        ds.read_b2_manifest(root)
    arrays["residual"][0, 0, 0] = np.float16(-95)
    np.savez(part, **arrays)
    info["sha256"][part.name] = ds._file_hash(part)
    descriptor.write_text(json.dumps(info))
    manifest["roles"]["train"]["shards"][0] = info
    (root / "manifest.json").write_text(json.dumps(manifest))
    meta = root / "train" / "meta-00000.jsonl"
    records = [json.loads(line) for line in meta.read_text().splitlines()]
    records[0]["cancellation"]["config"]["iterations"] = 9
    meta.write_text("".join(json.dumps(r) + "\n" for r in records))
    info["sha256"][meta.name] = ds._file_hash(meta)
    descriptor.write_text(json.dumps(info))
    manifest["roles"]["train"]["shards"][0] = info
    (root / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="cancellation provenance"):
        ds.read_b2_manifest(root)


def test_cli_selects_feature_stage_from_cancellation_json(tmp_path, monkeypatch):
    from geosim.cancellation import CancellationConfig
    path = tmp_path / "cancel.json"
    path.write_text(json.dumps({"iterations": 4}))
    calls = []
    monkeypatch.setattr(ds, "generate_b2_dataset", lambda out, cfg, **kwargs: calls.append(kwargs))
    ds.main(["--out", str(tmp_path / "data"), "--cancellation", str(path), "--limit-groups", "1"])
    assert calls[0]["cancellation"] == CancellationConfig(iterations=4)
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"iterations": 0}))
    with pytest.raises(SystemExit):
        ds.main(["--out", str(tmp_path / "data2"), "--cancellation", str(bad)])

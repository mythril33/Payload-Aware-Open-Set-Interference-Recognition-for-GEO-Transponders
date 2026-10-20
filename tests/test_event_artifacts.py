"""E1 event pairing, calibration independence and immutable artifact contracts."""
from dataclasses import asdict, replace
import json
from types import SimpleNamespace

import numpy as np
import pytest

from geosim import event_dataset as ds
from geosim.plan import plan_mask_db


@pytest.fixture
def generated(tmp_path, monkeypatch):
    calls = {"fit": 0, "simulate": []}
    real_fit = ds.fit_receiver_calibration

    def fit(*args, **kwargs):
        calls["fit"] += 1
        return real_fit(*args, **kwargs)

    def simulate(cfg, *, plans, calibration, interferers, downlink_interferers):
        calls["simulate"].append((cfg, plans, calibration, interferers, downlink_interferers))
        return SimpleNamespace(spec_db=np.full((2, 128, 512), -80, np.float32),
                               mask_db=np.stack([plan_mask_db(plan) for plan in plans]),
                               meta={"config": cfg.to_dict(), "plans": [[asdict(c) for c in plan] for plan in plans],
                                     "has_interferer": [event is not None for event in interferers or (None, None)],
                                     "has_downlink_interferer": [event is not None for event in downlink_interferers or (None, None)],
                                     "receiver_calibration_applied": True,
                                     "receiver_calibration": calibration.to_dict()})

    monkeypatch.setattr(ds, "fit_receiver_calibration", fit)
    monkeypatch.setattr(ds, "simulate_dual", simulate)
    # Other agents can edit source files while these isolated storage tests run.
    monkeypatch.setattr(ds, "_generator_provenance", lambda: {"unit_fixture": "stable"})
    root = tmp_path / "events"
    config = ds.EventDatasetConfig(n_seeds=2)
    ds.generate_event_dataset(root, config)
    return root, config, calls


def test_three_class_contract_and_disjoint_roles(generated):
    root, _, calls = generated
    manifest = ds.read_event_manifest(root)
    assert manifest["protocol"] == "E1-dev/1"
    assert manifest["labels"] == ["clean", "carrier_under_carrier", "adjacent_satellite"]
    groups = []
    for role in ds.ROLE_STARTS:
        data = ds.load_event_split(root, role)
        assert data["spec"].shape == (6, 2, 128, 512) and data["spec"].dtype == np.float16
        assert data["mask"].shape == (6, 2, 512)
        assert data["label"].tolist() == [0, 1, 2, 0, 1, 2]
        group = set(data["seed"].tolist())
        assert len(group) == 2 and all(not group & existing for existing in groups)
        groups.append(group)
    assert len(ds.event_fingerprint(root)) == 64
    assert len(calls["simulate"]) == 18


def test_pairs_share_phase_noise_carriers_links_and_thermal_streams(generated):
    root, config, calls = generated
    for index in range(0, len(calls["simulate"]), 3):
        clean, under, adjacent = calls["simulate"][index:index + 3]
        assert clean[0].to_dict() == under[0].to_dict() == adjacent[0].to_dict()
        assert clean[1] == under[1] == adjacent[1]
        assert clean[0].satellite_linewidth_hz == config.satellite_linewidth_hz
        assert clean[0].receiver_linewidth_hz == config.receiver_linewidth_hz
        assert clean[3] is None and clean[4] is None
        assert callable(under[3][0]) and under[3][1] is None and under[4] is None
        assert adjacent[3] is None and callable(adjacent[4][0]) and adjacent[4][1] is None
    data = ds.load_event_split(root, "train")
    clean, under, adjacent = data["meta"][:3]
    assert clean["event"] is None
    assert under["event"]["injection_stage"] == "uplink"
    assert adjacent["event"]["injection_stage"] == "downlink"
    assert under["event"]["c_over_i_db"] == adjacent["event"]["c_over_i_db"]


def test_independent_calibration_is_fitted_once_shared_and_bound_to_e1(generated):
    root, config, calls = generated
    assert calls["fit"] == 1
    calibration = calls["simulate"][0][2]
    assert all(call[2] is calibration for call in calls["simulate"])
    assert calibration.provenance.startswith("E1-dev/1:")
    assert calibration.provenance.endswith(":independent_pilots")
    assert ds.read_event_manifest(root)["calibration"] == calibration.to_dict()
    assert calibration.to_dict()["n_pilots"] == config.calibration_samples
    np.testing.assert_allclose(calibration.response, ds.receiver_response(config), atol=1e-3)


def test_verified_resume_and_historical_read_preserve_provenance(generated, monkeypatch):
    root, config, calls = generated
    content = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    identity = ds.event_fingerprint(root)
    monkeypatch.setattr(ds, "_commit", lambda: "later-docs-commit")
    ds.generate_event_dataset(root, config)
    assert {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()} == content
    assert calls["fit"] == 1 and len(calls["simulate"]) == 18
    monkeypatch.setattr(ds, "_generator_provenance", lambda: {"changed_generator": "new"})
    monkeypatch.setattr(ds, "default_plan", lambda *args, **kwargs: pytest.fail("historical reads must not replay plans"))
    monkeypatch.setattr(ds, "_event", lambda *args, **kwargs: pytest.fail("historical reads must not replay events"))
    assert ds.event_fingerprint(root) == identity
    with pytest.raises(ValueError, match="request changed"):
        ds.generate_event_dataset(root, config)


def test_incomplete_resume_reuses_verified_calibration_and_shards(generated):
    root, config, calls = generated
    (root / "manifest.json").unlink()
    content = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    ds.generate_event_dataset(root, config)
    assert all((root / path).read_bytes() == value for path, value in content.items())
    assert calls["fit"] == 1 and len(calls["simulate"]) == 18


@pytest.mark.parametrize("change", [{"n_seeds": 3}, {"bandwidth": 72e6}, {"satellite_linewidth_hz": 0},
                                    {"receiver_linewidth_hz": 0}, {"c_over_i_max_db": 20},
                                    {"calibration_seed": 99}, {"receiver_gain_db": (0., 0.)}])
def test_changed_request_cannot_rewrite_completed_data(generated, change):
    root, config, _ = generated
    manifest = (root / "manifest.json").read_bytes()
    with pytest.raises(ValueError, match="request changed"):
        ds.generate_event_dataset(root, replace(config, **change))
    assert (root / "manifest.json").read_bytes() == manifest


@pytest.mark.parametrize("filename", ["receiver_calibration.npz", "train/part-00000.npz", "test/meta-00000.jsonl"])
def test_modified_data_or_calibration_rejected(generated, filename):
    root, config, _ = generated
    with (root / filename).open("ab") as stream:
        stream.write(b"modified")
    for action in (lambda: ds.read_event_manifest(root), lambda: ds.load_event_split(root, "train"),
                   lambda: ds.event_fingerprint(root), lambda: ds.generate_event_dataset(root, config)):
        with pytest.raises(ValueError, match="modified"):
            action()


def _rewrite_metadata(root, records):
    path = root / "train/meta-00000.jsonl"
    text = "".join(json.dumps(record) + "\n" for record in records)
    path.write_text(text.replace('"1e999_fixture"', "1e999"))
    descriptor_path = root / "train/shard-00000.json"
    descriptor = json.loads(descriptor_path.read_text())
    descriptor["sha256"][path.name] = ds._file_hash(path)
    descriptor_path.write_text(json.dumps(descriptor))
    manifest = json.loads((root / "manifest.json").read_text())
    manifest["roles"]["train"]["shards"][0] = descriptor
    (root / "manifest.json").write_text(json.dumps(manifest))


@pytest.mark.parametrize("mutation,match", [("link", "differ beyond"), ("phase", "phase noise"),
                                           ("stage", "injection stage"), ("event", "event parameters"),
                                           ("plan", "differ beyond"), ("nonfinite", "nonfinite JSON"),
                                           ("overflow", "nonfinite JSON")])
def test_semantic_checks_survive_rehashed_metadata(generated, mutation, match):
    root, _, _ = generated
    records = [json.loads(line) for line in (root / "train/meta-00000.jsonl").read_text().splitlines()]
    if mutation == "link":
        records[1]["config"]["co"]["ibo_db"] += .01
    elif mutation == "phase":
        records[1]["config"]["receiver_linewidth_hz"] += 1
    elif mutation == "stage":
        records[1]["has_interferer"] = [False, False]
    elif mutation == "event":
        records[1]["event"]["carrier"]["power"] *= 2
    elif mutation == "plan":
        records[0]["plans"][0][0]["f0"] += 10
    elif mutation == "nonfinite":
        records[1]["unused_truth"] = float("nan")
    else:
        records[1]["unused_truth"] = "1e999_fixture"
    _rewrite_metadata(root, records)
    with pytest.raises(ValueError, match=match):
        ds.read_event_manifest(root)


@pytest.mark.parametrize("change", [{"n_seeds": 1}, {"n_seeds": 100001}, {"n_seeds": True},
                                    {"satellite_linewidth_hz": -1}, {"receiver_linewidth_hz": np.inf},
                                    {"c_over_i_min_db": 16}, {"c_over_i_min_db": -21},
                                    {"c_over_i_max_db": 101}, {"receiver_gain_db": (1,)},
                                    {"calibration_samples": 1}, {"calibration_noise_std": -1}])
def test_invalid_config_writes_nothing(tmp_path, change):
    with pytest.raises(ValueError):
        ds.generate_event_dataset(tmp_path / "bad", ds.EventDatasetConfig(**change))
    assert not list(tmp_path.iterdir())


def test_json_config_and_cli_overrides(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"n_seeds": 3, "receiver_linewidth_hz": 7}))
    assert ds.EventDatasetConfig.from_file(path).receiver_linewidth_hz == 7
    calls = []
    monkeypatch.setattr(ds, "generate_event_dataset", lambda out, cfg: calls.append((out, cfg)))
    ds.main(["--out", str(tmp_path / "data"), "--config", str(path), "--n-seeds", "4"])
    assert calls[0][1].n_seeds == 4 and calls[0][1].receiver_linewidth_hz == 7


def test_unknown_role_rejected_before_reading(tmp_path):
    with pytest.raises(ValueError, match="role must"):
        ds.load_event_split(tmp_path, "training")

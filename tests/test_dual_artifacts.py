"""Integrity, role separation and calibration provenance for dual observations."""
from dataclasses import replace
import json
from types import SimpleNamespace

import numpy as np
import pytest

from geosim import dual_dataset as ds


@pytest.fixture
def generated(tmp_path, monkeypatch):
    """Actual calibration/storage, cheap observations; simulator has physical tests."""
    calls = {"fit": 0, "simulate": []}
    real_fit = ds.fit_receiver_calibration

    def fit(*args, **kwargs):
        calls["fit"] += 1
        return real_fit(*args, **kwargs)

    def simulate(cfg, calibration):
        calls["simulate"].append((cfg, calibration))
        spec = np.full((2, 128, 512), -80., np.float32)
        spec[1] -= 3
        mask = np.full((2, 512), -60., np.float32)
        mask[0, 200:260] = 0
        mask[1, 100:180] = 0
        return SimpleNamespace(spec_db=spec, mask_db=mask,
                               meta={"config": cfg.to_dict(), "receiver_calibration_applied": True,
                                     "receiver_calibration": calibration.to_dict()})

    monkeypatch.setattr(ds, "fit_receiver_calibration", fit)
    monkeypatch.setattr(ds, "simulate_dual", simulate)
    root = tmp_path / "dual"
    config = ds.DualDatasetConfig(n_seeds=2)
    ds.generate_dual_dataset(root, config)
    return root, config, calls


def test_observation_contract_and_disjoint_role_groups(generated):
    root, config, calls = generated
    manifest = ds.read_dual_manifest(root)
    assert manifest["protocol"] == ds.PROTOCOL
    assert manifest["labels"] == list(ds.LABELS)
    assert manifest["config"]["n_seeds"] == config.n_seeds
    groups = []
    for role in ds.ROLE_STARTS:
        data = ds.load_dual_split(root, role)
        assert data["spec"].shape == (4, 2, 128, 512) and data["spec"].dtype == np.float16
        assert data["mask"].shape == (4, 2, 512)
        assert data["label"].tolist() == [0, 1, 0, 1]
        assert len(data["meta"]) == 4
        group = set(data["seed"].tolist())
        assert len(group) == 2 and group == set(manifest["roles"][role]["scenario_seeds"])
        assert all(not group & existing for existing in groups)
        groups.append(group)
    assert len(ds.dual_fingerprint(root)) == 64
    assert len(calls["simulate"]) == 12


def test_calibration_is_fitted_once_from_independent_pilots_and_shared_across_roles(generated):
    root, config, calls = generated
    manifest = ds.read_dual_manifest(root)
    assert calls["fit"] == 1
    calibration = calls["simulate"][0][1]
    assert all(current is calibration for _, current in calls["simulate"])
    assert manifest["calibration"] == calibration.to_dict()
    assert calibration.to_dict()["n_pilots"] == config.calibration_samples
    assert calibration.provenance.endswith(":independent_pilots")
    np.testing.assert_allclose(calibration.response, ds.receiver_response(config), atol=1e-3)


def test_paired_labels_change_only_uplink_physical_coupling(generated):
    _, config, calls = generated
    for index in range(0, len(calls["simulate"]), 2):
        clean, event = calls["simulate"][index][0].to_dict(), calls["simulate"][index + 1][0].to_dict()
        assert clean.pop("uplink_xpd_db") == config.nominal_xpd_db
        assert event.pop("uplink_xpd_db") == config.event_xpd_db
        assert clean == event
        assert clean["cross"]["seed"] == clean["co"]["seed"] + 1


def test_completed_resume_preserves_original_provenance_and_fits_nothing(generated, monkeypatch):
    root, config, calls = generated
    manifest = (root / "manifest.json").read_bytes()
    identity = ds.dual_fingerprint(root)
    calibration = (root / "receiver_calibration.npz").read_bytes()
    timestamps = {str(p.relative_to(root)): p.stat().st_mtime_ns for p in root.glob("*/*")}
    monkeypatch.setattr(ds, "_commit", lambda: "later-documentation-commit")
    ds.generate_dual_dataset(root, config)
    assert (root / "manifest.json").read_bytes() == manifest
    assert (root / "receiver_calibration.npz").read_bytes() == calibration
    assert ds.dual_fingerprint(root) == identity
    assert {str(p.relative_to(root)): p.stat().st_mtime_ns for p in root.glob("*/*")} == timestamps
    assert calls["fit"] == 1 and len(calls["simulate"]) == 12


@pytest.mark.parametrize("change", [{"n_seeds": 3}, {"event_xpd_db": 9.}, {"bandwidth": 72e6},
                                    {"receiver_gain_db": (1., 0.)}, {"calibration_seed": 7}])
def test_stale_generation_request_is_rejected_without_rewriting(generated, change):
    root, config, _ = generated
    manifest = (root / "manifest.json").read_bytes()
    with pytest.raises(ValueError, match="request changed"):
        ds.generate_dual_dataset(root, replace(config, **change))
    assert (root / "manifest.json").read_bytes() == manifest


@pytest.mark.parametrize("filename", ["receiver_calibration.npz", "train/part-00000.npz", "validation/meta-00000.jsonl"])
def test_modified_calibration_or_observations_are_rejected(generated, filename):
    root, config, _ = generated
    with (root / filename).open("ab") as stream:
        stream.write(b"modified")
    for action in (lambda: ds.read_dual_manifest(root), lambda: ds.load_dual_split(root, "train"),
                   lambda: ds.dual_fingerprint(root), lambda: ds.generate_dual_dataset(root, config)):
        with pytest.raises(ValueError, match="modified"):
            action()


def test_incomplete_generation_reuses_verified_calibration_and_shards(generated):
    root, config, calls = generated
    (root / "manifest.json").unlink()
    calibration = (root / "receiver_calibration.npz").read_bytes()
    timestamps = {str(p.relative_to(root)): p.stat().st_mtime_ns for p in root.glob("*/*")}
    ds.generate_dual_dataset(root, config)
    assert (root / "receiver_calibration.npz").read_bytes() == calibration
    assert {str(p.relative_to(root)): p.stat().st_mtime_ns for p in root.glob("*/*")} == timestamps
    assert calls["fit"] == 1 and len(calls["simulate"]) == 12


def test_manifest_count_and_calibration_metadata_must_match_artifacts(generated):
    root, _, _ = generated
    manifest = json.loads((root / "manifest.json").read_text())
    manifest["roles"]["train"]["n_samples"] += 1
    (root / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="counts"):
        ds.read_dual_manifest(root)


def test_unexpected_or_missing_shards_fail(generated):
    root, _, _ = generated
    extra = root / "train/part-00001.npz"
    extra.write_bytes(b"unexpected")
    with pytest.raises(ValueError, match="unexpected or missing"):
        ds.read_dual_manifest(root)
    extra.unlink()
    (root / "test/meta-00000.jsonl").unlink()
    with pytest.raises(ValueError, match="unexpected or missing"):
        ds.read_dual_manifest(root)


def test_read_checks_pair_semantics_even_when_metadata_hash_is_updated(generated):
    root, _, _ = generated
    meta_path = root / "train/meta-00000.jsonl"
    records = [json.loads(line) for line in meta_path.read_text().splitlines()]
    records[1]["config"]["co"]["ibo_db"] += 0.01
    meta_path.write_text("".join(json.dumps(record) + "\n" for record in records))
    descriptor_path = root / "train/shard-00000.json"
    descriptor = json.loads(descriptor_path.read_text())
    descriptor["sha256"][meta_path.name] = ds._file_hash(meta_path)
    descriptor_path.write_text(json.dumps(descriptor))
    manifest = json.loads((root / "manifest.json").read_text())
    manifest["roles"]["train"]["shards"][0] = descriptor
    (root / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="differ beyond"):
        ds.read_dual_manifest(root)


@pytest.mark.parametrize("change", [{"n_seeds": 0}, {"n_seeds": 100001}, {"n_seeds": True},
                                    {"event_xpd_db": 30}, {"event_xpd_db": -1}, {"nominal_xpd_db": np.inf},
                                    {"receiver_gain_db": (1,)}, {"calibration_samples": 1},
                                    {"calibration_noise_std": -1}, {"calibration_seed": -1}])
def test_invalid_configuration_writes_nothing(tmp_path, change):
    with pytest.raises(ValueError):
        ds.generate_dual_dataset(tmp_path / "bad", ds.DualDatasetConfig(**change))
    assert not list(tmp_path.iterdir())


def test_unknown_role_is_rejected_before_reading(tmp_path):
    with pytest.raises(ValueError, match="role must"):
        ds.load_dual_split(tmp_path, "training")

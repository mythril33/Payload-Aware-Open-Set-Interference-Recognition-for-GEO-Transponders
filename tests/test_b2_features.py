"""Observed-only residual extraction, role provenance and verified feature shards."""
from dataclasses import asdict, dataclass
import json
from types import SimpleNamespace

import numpy as np
import pytest

from geosim import b2_features as ds
from geosim import b2_scenarios as scenes
from geosim.b2_protocol import B2Config, BASE_ROLES, LABELS
from geosim.plan import plan_mask_db
from geosim.sensor import spectrogram_db


@dataclass(frozen=True)
class ReceiverConfig:
    timing_steps: int = 8

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_file(cls, path):
        return cls(**json.loads(path.read_text()))


@dataclass(frozen=True)
class DeclaredCarrier:
    f0: float
    symbol_rate: float
    alpha: float
    mod: str
    code_rate: str | None = None


@pytest.fixture
def generator(monkeypatch):
    calls = {"simulate": [], "cancel": [], "fit": 0}
    fit = ds.base._fit_calibration

    def calibration(*args):
        calls["fit"] += 1
        return fit(*args)

    def simulate(cfg, *, plans, interferers, active_carriers, calibration, keep_iq):
        assert keep_iq is True
        phase = np.arange(4096) * 2 * np.pi / 127
        co = (np.exp(1j * phase) + .3 * np.exp(1j * phase * 3)).astype(np.complex64)
        iq = np.stack([np.tile(co, (128, 1)), np.full((128, 4096), 11 + 7j, np.complex64)])
        calls["simulate"].append({"iq": iq, "calibration": calibration})
        powers = [sum(c.power for c, flag in zip(plan, active) if flag) for plan, active in zip(plans, active_carriers)]
        return SimpleNamespace(spec_db=spectrogram_db(iq),
                               mask_db=np.stack([plan_mask_db(plan) for plan in plans]), iq=iq,
                               meta={"config": cfg.to_dict(), "plans": [[asdict(c) for c in plan] for plan in plans],
                                     "has_interferer": [event is not None for event in interferers],
                                     "has_downlink_interferer": [False, False],
                                     "active_carriers": [list(active) for active in active_carriers],
                                     "active_planned_power": powers, "nominal_planned_power": [1., 1.],
                                     "gain_mode": "fixed_nominal_planned_power",
                                     "paths": [{"actual_ibo_db": cfg.co.ibo_db, "obo_db": 10.,
                                                "omux_output_power": .1, "receiver_noise_psd": 1e-10,
                                                "zero_drive": False} for _ in range(2)],
                                     "receiver_calibration_applied": True,
                                     "receiver_calibration": calibration.to_dict()})

    def cancel(iq, carriers, config):
        calls["cancel"].append((iq, carriers, config))
        assert all(type(carrier) is DeclaredCarrier for carrier in carriers)
        assert all(set(vars(carrier)) == set(ds.RECEIVER_FIELDS) for carrier in carriers)
        return SimpleNamespace(residual_iq=iq / 2,
                               meta={"algorithm": ds.RECEIVER_ALGORITHM, "config": config.to_dict(),
                                     "input_shape": list(iq.shape), "n_carriers": len(carriers),
                                     "input_power": float(np.mean(np.abs(iq) ** 2)),
                                     "residual_power": float(np.mean(np.abs(iq / 2) ** 2)),
                                     "carriers": [{"accepted_windows": len(iq)} for _ in carriers]})

    receiver = SimpleNamespace(ALGORITHM=ds.RECEIVER_ALGORITHM, CancellationConfig=ReceiverConfig,
                               ReceiverCarrier=DeclaredCarrier, cancel_observed=cancel)
    monkeypatch.setattr(ds, "_receiver", lambda: receiver)
    monkeypatch.setattr(ds.base, "_fit_calibration", calibration)
    monkeypatch.setattr(scenes, "simulate_dual", simulate)
    monkeypatch.setattr(ds, "_generator_provenance", lambda: {"fixture": "0" * 64})
    return calls, receiver


@pytest.fixture
def generated(tmp_path, generator):
    root = tmp_path / "features"
    ds.generate_b2_features(root, roles=("train",), limit_groups=2, groups_per_shard=1)
    return root, generator


def test_receiver_receives_only_observed_co_iq_and_declared_operator_fields(generated):
    root, (calls, _) = generated
    manifest = ds.read_feature_manifest(root)
    data = ds.load_feature_split(root, "train")
    assert len(calls["cancel"]) == len(calls["simulate"]) == 16
    for simulated, (iq, carriers, config) in zip(calls["simulate"], calls["cancel"]):
        np.testing.assert_array_equal(iq, simulated["iq"][0])
        assert not np.array_equal(iq, simulated["iq"][1])
        assert all(not hasattr(carrier, "power") and not hasattr(carrier, "seed") for carrier in carriers)
        assert isinstance(config, ReceiverConfig)
    expected = spectrogram_db(calls["simulate"][0]["iq"][0] / 2).astype(np.float16)
    np.testing.assert_array_equal(data["residual"][0], expected)
    peak = int(data["spec"][0, 0, 0].argmax())
    assert float(data["residual"][0, 0, peak] - data["spec"][0, 0, 0, peak]) == pytest.approx(-6.02, abs=.05)
    assert data["residual"].shape == (16, 128, 512) and data["residual"].dtype == np.float16
    assert set(data) == set(ds.ARRAY_KEYS) | {"meta"}
    assert manifest["protocol"] == "B2-features/1" and manifest["parent_protocol"] == "B2/1"
    assert manifest["benchmark_complete"] is False
    assert manifest["cancellation"]["receiver_fields"] == list(ds.RECEIVER_FIELDS)
    with np.load(root / "train/part-00000.npz", allow_pickle=False) as archive:
        assert "iq" not in archive.files


def test_independent_calibration_has_feature_request_provenance(generated):
    root, (calls, _) = generated
    manifest = ds.read_feature_manifest(root)
    calibration = calls["simulate"][0]["calibration"]
    assert calls["fit"] == 1
    assert all(call["calibration"] is calibration for call in calls["simulate"])
    assert calibration.provenance == f"{ds.PROTOCOL}:{manifest['request_fingerprint']}:independent_pilots"
    assert manifest["calibration"] == calibration.to_dict()


def test_per_role_prefixes_and_known_only_selection(tmp_path, generator):
    root = tmp_path / "roles"
    limits = {"train": 2, "val-select": 1, "val-calib": 1, "test": 1}
    ds.generate_b2_features(root, limit_groups=limits, groups_per_shard=1)
    manifest = ds.read_feature_manifest(root)
    groups = set()
    for role in BASE_ROLES:
        info = manifest["roles"][role]
        assert info["n_samples"] == 8 * limits[role]
        assert not groups.intersection(info["scenario_seeds"])
        groups.update(info["scenario_seeds"])
        assert set(ds.load_feature_split(root, role)["label"]) == set(range(8))
    assert manifest["request"]["limit_groups"] == limits
    assert manifest["labels"] == list(LABELS)


def test_resume_and_historical_read_do_not_recompute_observations_or_receiver(generated, monkeypatch):
    root, (calls, receiver) = generated
    original = (root / "manifest.json").read_bytes()
    identity = ds.feature_fingerprint(root)
    ds.generate_b2_features(root, roles=("train",), limit_groups=2, groups_per_shard=1)
    assert len(calls["cancel"]) == 16 and calls["fit"] == 1
    assert (root / "manifest.json").read_bytes() == original

    def forbidden(*args, **kwargs):
        raise AssertionError("historical feature read must not replay a receiver or sampler")

    monkeypatch.setattr(ds, "sample_scene", forbidden)
    monkeypatch.setattr(ds, "_receiver", forbidden)
    monkeypatch.setattr(ds, "_generator_provenance", lambda: {"new_source": "1" * 64})
    assert ds.feature_fingerprint(root) == identity
    assert len(ds.load_feature_split(root, "train")["label"]) == 16
    monkeypatch.setattr(ds, "_receiver", lambda: receiver)
    with pytest.raises(ValueError, match="request changed"):
        ds.generate_b2_features(root, roles=("train",), limit_groups=2, groups_per_shard=1)


def test_partial_resume_preserves_verified_calibration_and_shards(generated):
    root, (calls, _) = generated
    calibration_hash = ds._file_hash(root / "receiver_calibration.npz")
    (root / "manifest.json").unlink()
    ds.generate_b2_features(root, roles=("train",), limit_groups=2, groups_per_shard=1)
    assert len(calls["cancel"]) == 16 and calls["fit"] == 1
    assert ds._file_hash(root / "receiver_calibration.npz") == calibration_hash


@pytest.mark.parametrize("change", [{"limit_groups": 1}, {"groups_per_shard": 2},
                                    {"roles": ("test",)}, {"cancellation_config": ReceiverConfig(16)},
                                    {"config": B2Config(calibration_seed=99)}])
def test_changed_request_cannot_reuse(generated, change):
    root, _ = generated
    kwargs = {"roles": ("train",), "limit_groups": 2, "groups_per_shard": 1, **change}
    with pytest.raises(ValueError, match="request changed"):
        ds.generate_b2_features(root, **kwargs)


@pytest.mark.parametrize("filename", ["train/part-00000.npz", "train/meta-00000.jsonl",
                                      "receiver_calibration.npz", "calibration.json"])
def test_corruption_rejected_by_readers_and_generation_resume(generated, filename):
    root, _ = generated
    path = root / filename
    path.write_bytes(path.read_bytes() + b"corrupt")
    for call in (lambda: ds.read_feature_manifest(root), lambda: ds.feature_fingerprint(root),
                 lambda: ds.load_feature_split(root, "train"),
                 lambda: ds.generate_b2_features(root, roles=("train",), limit_groups=2, groups_per_shard=1)):
        with pytest.raises(ValueError):
            call()


def rehash_metadata(root, mutate):
    path = root / "train/meta-00000.jsonl"
    records = [json.loads(line) for line in path.read_text().splitlines()]
    mutate(records)
    path.write_text("".join(json.dumps(record, allow_nan=False) + "\n" for record in records))
    descriptor_path = root / "train/shard-00000.json"
    descriptor = json.loads(descriptor_path.read_text())
    descriptor["sha256"][path.name] = ds._file_hash(path)
    descriptor_path.write_text(json.dumps(descriptor))
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["roles"]["train"]["shards"][0] = descriptor
    manifest_path.write_text(json.dumps(manifest))


@pytest.mark.parametrize("mutate,match", [
    (lambda rows: rows[0]["cancellation"].update(algorithm="oracle"), "receiver features"),
    (lambda rows: rows[0]["cancellation"]["receiver_carriers"][0].update(power=1), "operator information"),
    (lambda rows: rows[0]["cancellation"]["receiver_carriers"][0].update(f0=0), "operator information"),
    (lambda rows: rows[0]["cancellation"]["diagnostics"].update(input_shape=[2, 128, 4096]), "diagnostics"),
    (lambda rows: rows[0].update(role="test"), "calibrated sample and role"),
])
def test_rehashed_feature_truth_or_role_tampering_is_still_rejected(generated, mutate, match):
    root, _ = generated
    rehash_metadata(root, mutate)
    with pytest.raises(ValueError, match=match):
        ds.read_feature_manifest(root)


def test_residual_array_has_checksum_and_semantic_validation(generated):
    root, _ = generated
    path = root / "train/part-00000.npz"
    with np.load(path, allow_pickle=False) as archive:
        arrays = {key: archive[key] for key in archive.files}
    arrays["residual"][0, 0, 0] = np.nan
    np.savez(path, **arrays)
    descriptor_path = root / "train/shard-00000.json"
    descriptor = json.loads(descriptor_path.read_text())
    descriptor["sha256"][path.name] = ds._file_hash(path)
    descriptor_path.write_text(json.dumps(descriptor))
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["roles"]["train"]["shards"][0] = descriptor
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="dimensions, dtypes, values"):
        ds.read_feature_manifest(root)


def test_lazy_shard_order_and_loading_stay_bounded(generated, monkeypatch):
    root, _ = generated
    actual, loaded = ds.np.load, []

    def load(path, *args, **kwargs):
        if "/train/part-" in str(path):
            loaded.append(str(path))
        return actual(path, *args, **kwargs)

    monkeypatch.setattr(ds.np, "load", load)
    iterator = ds.iter_feature_shards(root, "train", indices=[1, 0])
    assert loaded == []
    assert next(iterator)["seed"].tolist() == [3_000_001] * 8
    assert loaded == [str(root / "train/part-00001.npz")]
    assert next(iterator)["seed"].tolist() == [3_000_000] * 8
    assert len(loaded) == 2
    with pytest.raises(StopIteration):
        next(iterator)


@pytest.mark.parametrize("indices", [[], [True], [True, 0], [0, 0], [-1], [2], [[0]], [0.5]])
def test_invalid_shard_indices_fail(generated, indices):
    root, _ = generated
    with pytest.raises(ValueError, match="shard indices"):
        list(ds.iter_feature_shards(root, "train", indices=indices))


@pytest.mark.parametrize("kwargs", [{"roles": ("test-matched",)}, {"roles": ("train", "train")},
                                    {"limit_groups": 0}, {"limit_groups": True},
                                    {"groups_per_shard": 0}, {"limit_groups": {"train": 1}},
                                    {"roles": ("train",), "limit_groups": {"train": 1501}},
                                    {"roles": ("train",), "limit_groups": {"train": 1, "test": 1}}])
def test_invalid_selection_writes_nothing(tmp_path, generator, kwargs):
    root = tmp_path / "invalid"
    with pytest.raises(ValueError):
        ds.generate_b2_features(root, **kwargs)
    assert not root.exists()


def test_invalid_observation_fails_without_saving_a_feature_shard(tmp_path, generator, monkeypatch):
    root = tmp_path / "bad-iq"
    actual = ds.sample_scene

    def sample(*args, **kwargs):
        result = actual(*args, **kwargs)
        result.iq = result.iq.real
        return result

    monkeypatch.setattr(ds, "sample_scene", sample)
    with pytest.raises(ValueError, match="calibrated monitor IQ"):
        ds.generate_b2_features(root, roles=("train",), limit_groups=1)
    assert not list(root.rglob("part-*.npz"))


def test_cli_reads_per_role_limit_file(tmp_path, generator, monkeypatch):
    path = tmp_path / "limits.json"
    path.write_text(json.dumps({"train": 1, "test": 2}))
    captured = {}
    monkeypatch.setattr(ds, "generate_b2_features", lambda *args, **kwargs: captured.update(kwargs))
    ds.main(["--out", str(tmp_path / "out"), "--roles", "train", "test", "--role-limits", str(path)])
    assert captured["limit_groups"] == {"train": 1, "test": 2}
    assert captured["roles"] == ["train", "test"]

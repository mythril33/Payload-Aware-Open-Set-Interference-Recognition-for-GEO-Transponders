"""Real B2 optimizer/checkpoint execution and separation of fitting roles."""
from dataclasses import replace

import numpy as np
import pytest

torch = pytest.importorskip("torch")

from geoml import b2_train as train
from geoml.b2_model import B2Model
from geosim.b2_protocol import LABELS


def observations(groups, role=None):
    labels = np.tile(np.arange(8), len(groups))
    rng = np.random.default_rng(int(groups[0]))
    spec = (-90 + rng.normal(size=(len(labels), 2, 16, 64))).astype(np.float32)
    mask = np.full((len(labels), 2, 64), -60., np.float32)
    mask[:, 0, 10:20] = 0
    mask[:, 1, 32:42] = 0
    spec[:, 0, :, 10:20] += 25
    spec[:, 1, :, 32:42] += 25
    residual = spec[:, 0] - 8
    auxiliary = np.repeat(np.arange(len(groups)) % 2, 8).astype(np.int64)
    result = {"spec": spec, "mask": mask, "residual": residual, "label": labels,
              "seed": np.repeat(groups, 8), "plan_consistency": auxiliary,
              "meta": [{"true_event": LABELS[int(label)], "true_power": 1000} for label in labels]}
    if role is not None:
        result["role"] = role
    return result


def config(**changes):
    return train.B2TrainConfig(epochs=1, width=2, batch=4, time_pool=2, augment=False, **changes)


def test_fit_updates_both_outputs_and_centers_using_training_only(monkeypatch):
    training = observations([3_000_000, 3_000_001], "train")
    validation = observations([3_100_000], "val-select")
    cfg = config()
    torch.manual_seed(cfg.seed)
    initial = B2Model(width=cfg.width).state_dict()
    center_calls, actual_center = [], B2Model.center_loss
    actual_infer = train._infer

    def center_loss(model, embedding, labels):
        center_calls.append(labels.detach().cpu().tolist())
        return actual_center(model, embedding, labels)

    def validation_without_updates(model, source, *args, **kwargs):
        before = {key: value.clone() for key, value in model.state_dict().items()}
        result = actual_infer(model, source, *args, **kwargs)
        assert all(torch.equal(before[key], value) for key, value in model.state_dict().items())
        return result

    monkeypatch.setattr(B2Model, "center_loss", center_loss)
    monkeypatch.setattr(train, "_infer", validation_without_updates)
    fitted = train.fit(training, validation, cfg, provenance={"train": "known-only"}, log=lambda _: None)
    assert len(center_calls) == len(training["label"]) // cfg.batch
    assert sorted(value for batch in center_calls for value in batch) == sorted(training["label"].tolist())
    for name in ("head.weight", "consistency_head.weight", "class_centers", "stem.0.weight"):
        assert not torch.equal(fitted["model"].state_dict()[name], initial[name])
    assert torch.count_nonzero(fitted["model"].class_centers) > 0
    assert fitted["training_groups"] == [3_000_000, 3_000_001]
    assert fitted["selection_groups"] == [3_100_000]
    assert fitted["selection_metric"] == "val_select_class_macro_f1"
    history = fitted["history"][0]
    assert history["train_loss"] == pytest.approx(
        history["train_class_loss"] + cfg.consistency_weight * history["train_consistency_loss"]
        + cfg.center_weight * history["train_center_loss"], rel=1e-6)


def test_cpu_replay_and_checkpoint_reload_preserve_both_outputs_and_source_order(tmp_path):
    training = observations([100, 101])
    validation = observations([200])
    cfg, provenance = config(), {"data_identity": "observed-feature-test"}
    fitted = train.fit(training, validation, cfg, provenance=provenance, log=lambda _: None)
    result = train.infer(fitted, validation, batch=3)
    assert result["logits"].shape == (8, 8)
    assert result["consistency_logits"].shape == (8, 2)
    assert result["embedding"].shape == (8, 32)
    for key in ("label", "seed", "plan_consistency"):
        np.testing.assert_array_equal(result[key], validation[key])
    second = train.fit(training, validation, cfg, provenance=provenance, log=lambda _: None)
    for name, tensor in fitted["model"].state_dict().items():
        torch.testing.assert_close(second["model"].state_dict()[name], tensor, rtol=0, atol=0)
    path = tmp_path / "model.pt"
    train.save(fitted, path)
    restored = train.load(path, expected_config=cfg, expected_provenance=provenance)
    reloaded = train.infer(restored, validation, batch=3)
    for key in result:
        np.testing.assert_array_equal(reloaded[key], result[key])
    torch.testing.assert_close(restored["model"].class_centers, fitted["model"].class_centers, rtol=0, atol=0)
    with pytest.raises(ValueError, match="configuration"):
        train.load(path, expected_config=replace(cfg, view="dual"))
    with pytest.raises(ValueError, match="provenance"):
        train.load(path, expected_provenance={"data_identity": "other"})
    artifact = torch.load(path, weights_only=True)
    artifact["absolute_ref_db"] += 1
    torch.save(artifact, path)
    with pytest.raises(ValueError, match="metadata"):
        train.load(path)


def test_hidden_metadata_does_not_change_model_predictions():
    training, validation = observations([100, 101]), observations([200])
    fitted = train.fit(training, validation, config(), log=lambda _: None)
    original = train.infer(fitted, validation)
    changed = dict(validation, meta=[{"true_power": -999, "active": False} for _ in validation["label"]],
                   event="secret-family", true_xpd_db=0)
    modified = train.infer(fitted, changed)
    for key in original:
        np.testing.assert_array_equal(original[key], modified[key])


@pytest.mark.parametrize("train_groups,val_groups,train_role,val_role", [
    ([100], [100], None, None),
    ([3_150_000], [3_100_000], None, None),
    ([3_000_000], [3_200_000], None, None),
    ([100], [200], "test", "val-select"),
    ([100], [200], "train", "val-calib"),
])
def test_reserved_roles_or_group_leakage_fail_before_optimizer(monkeypatch, train_groups, val_groups, train_role, val_role):
    def forbidden(*args, **kwargs):
        raise AssertionError("invalid fitting roles must fail before allocating a model")

    monkeypatch.setattr(train, "B2Model", forbidden)
    with pytest.raises(ValueError):
        train.fit(observations(train_groups, train_role), observations(val_groups, val_role), config(), log=lambda _: None)


def test_missing_training_class_rejected_before_model_allocation(monkeypatch):
    data = observations([100])
    keep = data["label"] != 7
    for key in ("spec", "mask", "residual", "label", "seed", "plan_consistency"):
        data[key] = data[key][keep]
    monkeypatch.setattr(train, "B2Model", lambda *a, **k: pytest.fail("must reject missing class before model"))
    with pytest.raises(ValueError, match="every known class"):
        train.fit(data, observations([200]), config(), log=lambda _: None)


def test_absolute_reference_is_fitted_only_on_training_observations():
    training, validation = observations([100, 101]), observations([200])
    shifted = dict(validation, spec=validation["spec"] + 200, residual=validation["residual"] + 200)
    cfg = config(level="absolute")
    first = train.fit(training, validation, cfg, log=lambda _: None)
    second = train.fit(training, shifted, cfg, log=lambda _: None)
    assert first["absolute_ref_db"] == second["absolute_ref_db"]


def test_real_streaming_fit_uses_indexed_shards_and_only_augments_training(tmp_path, monkeypatch):
    from geoml import b2_data
    from geosim import b2_features

    shards = {"train": [observations([3_000_000]), observations([3_000_001])],
              "val-select": [observations([3_100_000])]}
    manifest = {"protocol": "B2-features/1", "labels": list(LABELS), "roles": {}}
    for role, items in shards.items():
        manifest["roles"][role] = {
            "scenario_seeds": [int(item["seed"][0]) for item in items],
            "n_samples": sum(len(item["label"]) for item in items),
            "shards": [{"n_samples": len(item["label"])} for item in items],
        }
    reads, iterations, augmented = [], [], []

    def read_manifest(path):
        reads.append(path)
        return manifest

    def read_shards(path, role, *, indices=None):
        order = list(range(len(shards[role]))) if indices is None else list(indices)
        iterations.append((role, indices, order))
        yield from (shards[role][index] for index in order)

    real_augment = b2_data.augment_inputs

    def track_augmentation(values, **kwargs):
        augmented.append(len(values))
        return real_augment(values, **kwargs)

    monkeypatch.setattr(b2_features, "read_feature_manifest", read_manifest)
    monkeypatch.setattr(b2_features, "iter_feature_shards", read_shards)
    monkeypatch.setattr(b2_data, "augment_inputs", track_augmentation)
    cfg = replace(config(), augment=True)
    fitted = train.fit((tmp_path, "train"), (tmp_path, "val-select"), cfg, log=lambda _: None)
    assert len(reads) == 1  # One validated manifest is shared between fitting roles.
    assert [(role, sorted(order)) for role, indices, order in iterations if indices is not None] == [
        ("train", [0, 1])
    ]
    assert sum(augmented) == 16
    assert len(augmented) == 4
    result = train.infer(fitted, (tmp_path, "val-select"))
    np.testing.assert_array_equal(result["seed"], shards["val-select"][0]["seed"])
    assert result["logits"].shape == (8, 8)
    assert len(augmented) == 4  # Neither selection nor later inference augments data.


@pytest.mark.parametrize("change", [
    {"view": "other"}, {"labels": tuple(reversed(LABELS))}, {"epochs": 0}, {"batch": True},
    {"lr": 0}, {"lr": np.inf}, {"center_weight": -1}, {"consistency_weight": np.nan},
    {"plan_shift_probability": 1.1}, {"max_plan_shift_hz": -1}, {"augment": 1}, {"seed": -1},
])
def test_invalid_training_contract_fails(change):
    with pytest.raises(ValueError):
        train.B2TrainConfig(**change)

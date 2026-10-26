"""B2-C2-ablation/1: the no-plan control must be unable to see the operator plan, and the matched arms must differ in nothing else.

Every invariance test has a positive control (the same perturbation DOES change the arms that may use the plan), so none of
these checks can pass vacuously. Data are deterministic stand-ins; nothing here measures recognition quality.
"""
from dataclasses import asdict
import copy

import numpy as np
import pytest
import torch

from geosim.b2_protocol import LABELS, ROLE_STARTS
from geoml import b2_c2, b2_execution as execution, b2_stream
from geoml.b2_experiment import ALL_VIEWS, PROFILE_CHOICES, VIEWS, B2ExperimentConfig
from geoml.b2_stream import B2Source, fit_streaming, infer_streaming
from geoml.data import (C2_NOPLAN_VIEWS, C2_PLANMASK_VIEWS, C2_VIEWS, OBSERVED_LEVEL_PERCENTILE, VIEW_CHANNELS, observed_level_db,
                        preprocess, preprocess_c2, preprocess_dual)
from geoml.model import SmallResNet
from geoml.train import TrainConfig, _inputs, _training_reference, fit

FORBIDDEN = frozenset({"mask", "residual", "plan_consistency", "meta", "plans"})


def split(role, *, seed, n_groups=2, planned=True):
    """Deterministic known-class stand-in: spectra depend on ``seed``; every plan-derived array is separately controllable."""
    rng = np.random.default_rng(seed)
    start = ROLE_STARTS[role]
    groups = np.repeat(np.arange(start, start + n_groups), len(LABELS))
    labels = np.tile(np.arange(len(LABELS)), n_groups).astype(np.int8)
    n = len(labels)
    spec = rng.normal(-80, 2, (n, 2, 8, 32)).astype(np.float16)
    spec[:, 0, :, 4:12] += 10 + labels[:, None, None]                  # class-dependent structure so training has a signal
    spec[:, 1, :, 20:28] += 3 * (labels[:, None, None] % 3)
    mask = np.full((n, 2, 32), -60, np.float16)
    mask[:, :, 4:12] = 0
    return {"spec": spec, "mask": mask, "residual": (spec[:, 0].astype(np.float32) - 12).astype(np.float16),
            "seed": groups.astype(np.int64), "label": labels, "plan_consistency": (groups % 2).astype(np.int8),
            "meta": [{"scenario_id": int(g)} for g in groups]}


def planless(data, *, mask_seed=99):
    """The same observations with every plan-derived array replaced: shifted/random masks, junk residual, flipped targets."""
    other = copy.deepcopy(data)
    rng = np.random.default_rng(mask_seed)
    other["mask"] = np.roll(np.asarray(data["mask"]), 5, axis=2) + rng.choice([0.0, 0.5], size=np.shape(data["mask"])).astype(np.float16)
    other["mask"][:, :, 14:18] = 0                                      # still a valid plan (has a core bin), just a different one
    other["residual"] = rng.normal(-50, 9, np.shape(data["residual"])).astype(np.float16)
    other["plan_consistency"] = (1 - np.asarray(data["plan_consistency"])).astype(np.int8)
    other["meta"] = [{"scenario_id": -1, "plans": "unrelated"} for _ in data["meta"]]
    return other


class Spy(dict):
    """A shard that fails the test the moment a plan-derived key is read in any way."""

    def __getitem__(self, key):
        assert key not in FORBIDDEN, f"plan-derived key {key!r} was read"
        return super().__getitem__(key)

    def get(self, key, default=None):
        assert key not in FORBIDDEN, f"plan-derived key {key!r} was read"
        return super().get(key, default)

    def __contains__(self, key):
        assert key not in FORBIDDEN, f"plan-derived key {key!r} was probed"
        return super().__contains__(key)


def config(view, **changes):
    values = dict(labels=LABELS, input_mode=view, level="absolute" if view in C2_VIEWS else "carrier", epochs=1, batch=8, width=2,
                  time_pool=2, seed=3, center_loss_weight=0.005, augment=True)
    if view not in C2_VIEWS:
        values.update(plan_consistency=True, plan_shift_fraction=0.0)
    values.update(changes)
    return TrainConfig(**values)


def reference(view):
    return _training_reference(split("train", seed=1), config(view))


# ---- the views and their inputs ----------------------------------------------------------------------------------------

def test_view_channels_and_canonical_names_are_exactly_as_declared():
    assert VIEW_CHANNELS == {"single": 2, "co": 2, "dual": 4, "dual_residual": 5,
                             "co_noplan": 1, "dual_noplan": 2, "co_planmask": 2, "dual_planmask": 4}
    assert VIEWS == ("co", "dual", "dual_residual") and ALL_VIEWS == VIEWS + C2_VIEWS
    assert set(C2_NOPLAN_VIEWS) | set(C2_PLANMASK_VIEWS) == set(C2_VIEWS) and not set(C2_VIEWS) & set(VIEWS)


def test_training_config_fields_are_unchanged_so_canonical_configurations_keep_their_identity():
    assert list(asdict(config("dual"))) == ["labels", "level", "time_pool", "width", "epochs", "batch", "lr", "augment", "weight_decay",
                                           "seed", "input_mode", "plan_consistency", "plan_loss_weight", "center_loss_weight",
                                           "plan_shift_fraction", "plan_shift_max_hz"]


@pytest.mark.parametrize("view", C2_VIEWS)
def test_each_c2_view_produces_its_declared_channels_with_finite_values(view):
    data = split("train", seed=1)
    x = _inputs(data, config(view), reference(view))
    assert tuple(x.shape) == (16, VIEW_CHANNELS[view], 4, 32) and x.dtype == torch.float32 and torch.isfinite(x).all()


@pytest.mark.parametrize("view,canonical", [("co", lambda d, c, r: preprocess(d["spec"][:, 0], d["mask"][:, 0], "carrier", 2, None)),
                                           ("dual", lambda d, c, r: preprocess_dual(d["spec"], d["mask"], "carrier", 2, None, view="dual")),
                                           ("dual_residual", lambda d, c, r: preprocess_dual(d["spec"], d["mask"], "carrier", 2, None,
                                                                                            view="dual_residual", residual_db=d["residual"]))])
def test_canonical_views_are_routed_exactly_as_before(view, canonical):
    data = split("train", seed=1)
    cfg = config(view)
    np.testing.assert_array_equal(_inputs(data, cfg, 0.0).numpy(), canonical(data, cfg, 0.0))


# ---- source isolation: the no-plan arms cannot see the plan --------------------------------------------------------------

@pytest.mark.parametrize("view", C2_NOPLAN_VIEWS)
def test_noplan_inputs_are_bitwise_independent_of_every_plan_derived_array(view):
    data = split("train", seed=1)
    cfg, ref = config(view), reference(view)
    base = _inputs(data, cfg, ref).numpy()
    for mask_seed in (1, 2, 3):
        other = planless(data, mask_seed=mask_seed)
        np.testing.assert_array_equal(_inputs(other, cfg, ref).numpy(), base)
    stripped = {"spec": data["spec"]}                      # no mask/residual/target at all
    np.testing.assert_array_equal(_inputs(stripped, cfg, ref).numpy(), base)


@pytest.mark.parametrize("view", ["co", "dual", "dual_residual", "co_planmask", "dual_planmask"])
def test_positive_control_arms_that_may_use_the_plan_do_react_to_it(view):
    data = split("train", seed=1)
    cfg, ref = config(view), reference(view)
    assert not np.array_equal(_inputs(planless(data), cfg, ref).numpy(), _inputs(data, cfg, ref).numpy())


@pytest.mark.parametrize("view", C2_NOPLAN_VIEWS)
def test_noplan_view_reads_no_plan_key_in_any_path(view, monkeypatch):
    data, cfg = split("train", seed=1), config(view)
    shard = Spy(data)
    ref = _training_reference(shard, cfg)                  # in-memory plan-free reference
    _inputs(shard, cfg, ref)
    fit(Spy(split("train", seed=1)), Spy(split("val-select", seed=2)), cfg, device="cpu", log=lambda *_: None)   # in-memory trainer
    original = B2Source.shards

    def spied(self, order=None):
        for item in original(self, order):
            yield Spy(item)
    monkeypatch.setattr(B2Source, "shards", spied)
    train, val = B2Source.from_arrays(split("train", seed=1), role="train"), B2Source.from_arrays(split("val-select", seed=2), role="val-select")
    fitted = fit_streaming(train, val, cfg, device="cpu", log=lambda *_: None)            # streaming trainer, shard by shard
    infer_streaming(fitted, B2Source.from_arrays(split("val-calib", seed=4), role="val-calib"))


def test_the_spy_would_catch_a_plan_reading_view(monkeypatch):
    with pytest.raises(AssertionError, match="plan-derived key"):
        _inputs(Spy(split("train", seed=1)), config("dual"), 0.0)


@pytest.mark.parametrize("view", C2_NOPLAN_VIEWS)
def test_plan_free_reference_ignores_the_plan_and_matches_in_memory_and_streaming(view):
    data = split("train", seed=1)
    cfg = config(view)
    a = _training_reference(data, cfg)
    assert a == _training_reference(planless(data), cfg) == float(observed_level_db(data["spec"][:, 0]).mean())
    source = B2Source.from_arrays(data, role="train")
    assert b2_stream._training_reference(source, cfg) == a
    carrier = config("dual")
    assert _training_reference(planless(data), carrier) != _training_reference(data, carrier)   # the plan-referenced one does depend on it


@pytest.mark.parametrize("view", C2_NOPLAN_VIEWS)
def test_the_streaming_layer_drops_plan_arrays_for_plan_free_views(view):
    shard = {"spec": 1, "mask": 2, "residual": 3, "label": 4}
    assert b2_stream._shard_arrays(shard, config(view)) == {"spec": 1}
    assert b2_stream._shard_arrays(shard, config("dual_planmask")) == {"spec": 1, "mask": 2, "residual": 3}
    assert b2_stream._shard_arrays(shard) == {"spec": 1, "mask": 2, "residual": 3}


def train_state(view, train, val, **changes):
    cfg = config(view, **changes)
    fitted = fit_streaming(B2Source.from_arrays(train, role="train"), B2Source.from_arrays(val, role="val-select"), cfg,
                           device="cpu", log=lambda *_: None)
    return fitted, cfg


@pytest.mark.parametrize("view", C2_NOPLAN_VIEWS)
def test_changing_every_plan_derived_array_cannot_change_a_noplan_model(view):
    """Weights, history, embeddings and predictions are bit-identical when masks, residuals, targets and metadata change."""
    train, val, test = split("train", seed=1), split("val-select", seed=2), split("val-calib", seed=4)
    first, _ = train_state(view, train, val)
    second, _ = train_state(view, planless(train, mask_seed=7), planless(val, mask_seed=8))
    assert first["history"] == second["history"] and first["absolute_ref_db"] == second["absolute_ref_db"]
    for key, tensor in first["model"].state_dict().items():
        assert torch.equal(tensor, second["model"].state_dict()[key]), key
    a = infer_streaming(first, B2Source.from_arrays(test, role="val-calib"))
    b = infer_streaming(second, B2Source.from_arrays(planless(test, mask_seed=9), role="val-calib"))
    np.testing.assert_array_equal(a["logits"], b["logits"])
    np.testing.assert_array_equal(a["embedding"], b["embedding"])
    assert a["plan_logits"] is None and b["plan_logits"] is None


def test_positive_control_a_planmask_model_does_change_when_the_plan_changes():
    train, val = split("train", seed=1), split("val-select", seed=2)
    first, _ = train_state("dual_planmask", train, val)
    second, _ = train_state("dual_planmask", planless(train), planless(val))
    assert any(not torch.equal(tensor, second["model"].state_dict()[key]) for key, tensor in first["model"].state_dict().items())


def test_a5_style_plan_corruption_is_invisible_to_the_noplan_model_and_visible_to_the_plan_arm():
    train, val, test = split("train", seed=1), split("val-select", seed=2), split("val-calib", seed=4)
    shifted = copy.deepcopy(test)
    shifted["mask"] = np.roll(np.asarray(test["mask"]), 3, axis=2)                  # a stale / shifted operator belief
    outputs = {}
    for view in ("dual_noplan", "dual_planmask"):
        fitted, _ = train_state(view, train, val)
        outputs[view] = (infer_streaming(fitted, B2Source.from_arrays(test, role="val-calib"))["logits"],
                         infer_streaming(fitted, B2Source.from_arrays(shifted, role="val-calib"))["logits"])
    np.testing.assert_array_equal(*outputs["dual_noplan"])
    assert not np.array_equal(*outputs["dual_planmask"])


# ---- fairness: the matched arms differ in the operator-plan mask channels and in nothing else ---------------------------------

@pytest.mark.parametrize("pair", [("dual_planmask", "dual_noplan"), ("co_planmask", "co_noplan")])
def test_matched_arms_share_spectral_channels_bit_for_bit_and_add_only_mask_channels(pair):
    plan, noplan = pair
    data = split("train", seed=1)
    ref = reference(noplan)
    assert reference(plan) == ref
    x_plan, x_noplan = _inputs(data, config(plan), ref).numpy(), _inputs(data, config(noplan), ref).numpy()
    n_spectral = VIEW_CHANNELS[noplan]
    np.testing.assert_array_equal(x_plan[:, :n_spectral], x_noplan)
    assert x_plan.shape[1] == n_spectral * 2
    canonical = {"dual_planmask": "dual", "co_planmask": "co"}[plan]
    expected_masks = _inputs(data, config(canonical), 0.0).numpy()[:, n_spectral:2 * n_spectral]   # canonical mask channels, same order
    np.testing.assert_array_equal(x_plan[:, n_spectral:], expected_masks)


@pytest.mark.parametrize("pair", [("dual_planmask", "dual_noplan"), ("co_planmask", "co_noplan")])
def test_matched_arms_have_the_same_budget_objective_and_differ_in_capacity_only_by_the_stem_channels(pair):
    plan, noplan = pair
    a, b = asdict(config(plan)), asdict(config(noplan))
    assert {k for k in a if a[k] != b[k]} == {"input_mode"}
    train, val = split("train", seed=1), split("val-select", seed=2)
    fa, _ = train_state(plan, train, val)
    fb, _ = train_state(noplan, train, val)
    assert len(fa["history"]) == len(fb["history"]) == 1
    width = a["width"]
    assert fa["n_parameters"] - fb["n_parameters"] == (VIEW_CHANNELS[plan] - VIEW_CHANNELS[noplan]) * width * 25
    assert fa["streaming"]["shard_orders"] == fb["streaming"]["shard_orders"]               # same data order and steps
    assert fa["train_diagnostics"]["schema"] == fb["train_diagnostics"]["schema"] if "train_diagnostics" in fa and fa["train_diagnostics"] else True


@pytest.mark.parametrize("view", C2_VIEWS)
@pytest.mark.parametrize("bad", [dict(level="carrier"), dict(plan_consistency=True), dict(plan_shift_fraction=0.15)])
def test_c2_views_refuse_plan_derived_settings(view, bad):
    with pytest.raises(ValueError, match="C2|plan|level"):
        TrainConfig(labels=LABELS, input_mode=view, **{"level": "absolute", **bad})


def test_noplan_preprocessing_refuses_masks_and_planmask_preprocessing_requires_them():
    data = split("train", seed=1)
    with pytest.raises(ValueError, match="takes no plan masks"):
        preprocess_c2(data["spec"], data["mask"], "dual_noplan", 2, -70.0)
    with pytest.raises(ValueError, match="plan masks"):
        preprocess_c2(data["spec"], None, "dual_planmask", 2, -70.0)
    bad = np.full_like(data["mask"], -60)
    with pytest.raises(ValueError, match="core bin"):
        preprocess_c2(data["spec"], bad, "dual_planmask", 2, -70.0)
    with pytest.raises(ValueError, match="C2 view"):
        preprocess_c2(data["spec"], None, "dual", 2, -70.0)


def test_observed_level_follows_its_declared_definition_by_independent_arithmetic():
    """90th percentile over frequency of the time-averaged linear co-pol PSD, in dB: the frozen plan-free reference of the C2 views."""
    assert OBSERVED_LEVEL_PERCENTILE == 90.0
    spec = split("train", seed=1)["spec"][:, 0].astype(np.float64)
    expected = np.percentile(10 * np.log10(np.mean(10 ** (spec / 10), axis=1)), 90.0, axis=1)
    np.testing.assert_allclose(observed_level_db(spec), expected, atol=1e-3)
    assert not np.allclose(expected, np.percentile(10 * np.log10(np.mean(10 ** (spec / 10), axis=1)), 50.0, axis=1), atol=1e-3)


def test_observed_level_is_a_plan_free_per_sample_statistic():
    spec = split("train", seed=1)["spec"][:, 0]
    level = observed_level_db(spec)
    assert level.shape == (len(spec),) and np.isfinite(level).all()
    shifted = (spec.astype(np.float32) + 7).astype(np.float16)
    np.testing.assert_allclose(observed_level_db(shifted) - level, 7, atol=0.05)           # a pure level shift moves the reference by that shift
    with pytest.raises(ValueError):
        observed_level_db(np.full((2, 4, 8), np.nan))


# ---- configuration, rosters and the executor -----------------------------------------------------------------------------------

def test_experiment_config_accepts_homogeneous_c2_configs_and_refuses_mixtures_and_plan_targets():
    cfg = B2ExperimentConfig(**b2_c2.bundle_config(["dual_planmask", "dual_noplan"], 0, "smoke"))
    assert cfg.views == ("dual_planmask", "dual_noplan") and B2ExperimentConfig(**cfg.resolved()).resolved() == cfg.resolved()
    mixed = b2_c2.bundle_config(["dual_noplan"], 0)
    mixed["views"] = ["dual", "dual_noplan"]
    with pytest.raises(ValueError, match="must not share"):
        B2ExperimentConfig(**mixed)
    with pytest.raises(ValueError, match="consistency"):
        B2ExperimentConfig(**{**b2_c2.bundle_config(["dual_noplan"], 0), "plan_consistency": True})


def test_cli_profile_choices_equal_the_executor_profiles():
    assert tuple(PROFILE_CHOICES) == tuple(execution.PROFILES)


def test_production_scale_canonical_arms_equal_the_approved_r1_r10_parameters():
    from geoml import b2_e9_contract as e9
    approved = e9.approved_config()
    for arm in ("co", "dual", "dual_residual"):
        cfg = b2_c2.arm_config(arm, 1, "production")
        t = cfg["training"]
        assert (t["width"], t["time_pool"], t["level"], t["batch"], t["epochs"]) == (
            approved["model"]["width"], approved["model"]["time_pool"], approved["model"]["level"],
            approved["training"]["batch_size"], approved["training"]["epochs"])
        assert (t["lr"], t["weight_decay"]) == (approved["optimizer"]["peak_lr"], approved["optimizer"]["weight_decay"])
        assert (t["center_loss_weight"], t["plan_loss_weight"], cfg["plan_consistency"]) == (
            approved["loss"]["center_loss_weight"], approved["loss"]["plan_loss_weight"], approved["loss"]["plan_consistency"])
        assert (t["plan_shift_fraction"], t["plan_shift_max_hz"]) == (approved["augmentation"]["plan_shift_fraction"],
                                                                       approved["augmentation"]["plan_shift_max_hz"])
        assert cfg["target_acceptance"] == approved["calibration"]["known_acceptance_target"]
        assert cfg["pfa"] == approved["calibration"]["clean_alarm_pfa"]
        assert cfg["mahalanobis_regularization"] == approved["calibration"]["mahalanobis_shrinkage"]


def test_matched_arms_differ_from_the_canonical_recipe_in_exactly_three_declared_settings():
    assert sorted(b2_c2.matched_deltas()) == ["plan_consistency", "training.level", "training.plan_shift_fraction"]
    for scale in ("smoke", "production"):
        a, b = b2_c2.arm_config("dual_planmask", 2, scale), b2_c2.arm_config("dual_noplan", 2, scale)
        assert {k for k in a if a[k] != b[k]} == {"views"} and a["training"] == b["training"]


def test_production_scale_configs_cannot_run_in_the_bounded_executor():
    for arm in b2_c2.ARMS:
        cfg = B2ExperimentConfig(**b2_c2.arm_config(arm, 0, "production"))
        with pytest.raises(ValueError, match="bounded CPU smoke caps"):
            execution._caps(cfg)
        execution._caps(B2ExperimentConfig(**b2_c2.arm_config(arm, 0, "smoke")))


def test_inventory_rosters_are_complete_six_cell_sets_for_the_matched_pairs(tmp_path):
    for profile, views in execution.C2_ROSTERS.items():
        assert execution._roster(profile) == views and len(views) == 2
    assert execution._roster("proposed-full") == VIEWS and execution._roster("fixture") == ALL_VIEWS
    with pytest.raises(ValueError, match="three seeds"):
        execution._profile("c2-h3-dual", [0, 1])
    assert execution._profile("c2-h3-dual", [0, 1, 2]) == [0, 1, 2]
    with pytest.raises(ValueError):
        execution._profile("c2-unknown", [0, 1, 2])

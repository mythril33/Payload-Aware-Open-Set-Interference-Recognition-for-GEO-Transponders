"""Five-channel inputs, independent plan-consistency head, center loss and checkpoint parity."""
import numpy as np
import pytest
import torch

from geoml.data import VIEW_CHANNELS, preprocess_dual, select
from geoml.model import CenterLoss, SmallResNet
from geoml.train import TrainConfig, fit, infer, load, run, save

LABELS = ("clean", "cw", "swept_cw", "unauthorized")


def _data(n, seed, with_residual=True, with_plan=True):
    rng = np.random.default_rng(seed)
    spec = rng.normal(-80, 3, (n, 2, 8, 32)).astype(np.float32)
    mask = np.full((n, 2, 32), -60, np.float32)
    mask[:, :, 8:16] = 0.0
    labels = np.arange(n) % len(LABELS)
    spec[labels == 1, 0, :, 20] += 25          # a line the classes can be told apart by
    d = {"spec": spec, "mask": mask, "label": labels.astype(np.int64), "seed": np.arange(n), "meta": [{}] * n}
    if with_residual:
        d["residual"] = (spec[:, 0] - 15 + rng.normal(0, 1, (n, 8, 32))).astype(np.float32)
    if with_plan:
        d["plan_consistency"] = (np.arange(n) % 3 == 0).astype(np.int64)
    return d


def test_dual_residual_view_appends_fifth_channel_with_shared_co_reference():
    d = _data(6, 0)
    four = preprocess_dual(d["spec"], d["mask"], time_pool=2, view="dual")
    five = preprocess_dual(d["spec"], d["mask"], time_pool=2, view="dual_residual", residual_db=d["residual"])
    assert four.shape == (6, 4, 4, 32) and five.shape == (6, 5, 4, 32)
    assert np.array_equal(five[:, :4], four)
    # Residual sits below the co spectrum by about 15 dB relative to the same reference.
    gap = (five[:, 0] - five[:, 4]).mean() * 20
    assert 13 < gap < 17
    assert VIEW_CHANNELS["dual_residual"] == 5


def test_dual_residual_view_validates_residual_presence_and_shape():
    d = _data(4, 1)
    with pytest.raises(ValueError, match="requires the stored cancellation residual"):
        preprocess_dual(d["spec"], d["mask"], view="dual_residual")
    with pytest.raises(ValueError, match="does not take a residual"):
        preprocess_dual(d["spec"], d["mask"], view="dual", residual_db=d["residual"])
    with pytest.raises(ValueError, match="residual must be"):
        preprocess_dual(d["spec"], d["mask"], view="dual_residual", residual_db=d["residual"][:, :4])
    bad = d["residual"].copy()
    bad[0, 0, 0] = np.inf
    with pytest.raises(ValueError, match="residual must be"):
        preprocess_dual(d["spec"], d["mask"], view="dual_residual", residual_db=bad)


def test_select_carries_residual_and_plan_targets():
    d = _data(8, 2)
    kept = select(d, ("cw", "clean"), LABELS)
    assert kept["label"].tolist() == [1, 0, 1, 0]
    assert kept["residual"].shape == (4, 8, 32)
    assert kept["plan_consistency"].tolist() == [1, 0, 0, 0]
    plain = select({k: v for k, v in d.items() if k not in ("residual", "plan_consistency")}, ("cw",), LABELS)
    assert "residual" not in plain and "plan_consistency" not in plain


def test_model_forward_is_unchanged_and_forward_all_exposes_auxiliary_head():
    torch.manual_seed(0)
    model = SmallResNet(4, width=4, in_ch=5, aux_outputs=1).eval()
    x = torch.randn(3, 5, 4, 32)
    logits, aux, embedding = model.forward_all(x)
    assert torch.equal(model(x), logits) and aux.shape == (3, 1) and embedding.shape == (3, 64)
    plain = SmallResNet(4, width=4, in_ch=4)
    assert plain.aux_head is None and plain.forward_all(torch.randn(2, 4, 4, 32))[1] is None
    with pytest.raises(ValueError):
        SmallResNet(4, aux_outputs=-1)


def test_center_loss_is_zero_at_centers_and_positive_elsewhere():
    loss = CenterLoss(3, 2)
    with torch.no_grad():
        loss.centers.copy_(torch.tensor([[0., 0.], [1., 1.], [2., 2.]]))
    labels = torch.tensor([1, 2])
    assert loss(torch.tensor([[1., 1.], [2., 2.]]), labels).item() == 0.0
    assert loss(torch.tensor([[1., 1.], [2., 3.]]), labels).item() == pytest.approx(0.5)


def test_config_validation():
    for bad in ({"input_mode": "triple"}, {"plan_consistency": 1}, {"center_loss_weight": -0.1},
                {"plan_loss_weight": float("nan")}, {"center_loss_weight": True}):
        with pytest.raises(ValueError):
            TrainConfig(labels=LABELS, **bad)
    cfg = TrainConfig(labels=LABELS, input_mode="dual_residual", plan_consistency=True, center_loss_weight=0.005)
    assert cfg.center_loss_weight == 0.005 and cfg.plan_loss_weight == 1.0


def test_fit_with_residual_plan_head_and_center_loss_round_trips_through_checkpoint(tmp_path):
    train, val = _data(16, 3), _data(8, 4)
    cfg = TrainConfig(labels=LABELS, input_mode="dual_residual", plan_consistency=True, center_loss_weight=0.01,
                      epochs=2, batch=8, width=4, augment=False)
    fitted = fit(train, val, cfg, device="cpu", log=lambda *_: None)
    assert fitted["model"].stem[0].in_channels == 5 and fitted["model"].aux_head is not None
    assert all("val_plan_accuracy" in record for record in fitted["history"])
    out = infer(fitted, val)
    assert out["logits"].shape == (8, 4) and out["plan_logits"].shape == (8, 1) and out["embedding"].shape == (8, 64)
    path = tmp_path / "model.pt"
    save(fitted, path)
    loaded = load(path, device="cpu", expected_config=cfg)
    again = infer(loaded, val)
    assert np.allclose(out["logits"], again["logits"], atol=1e-5)
    assert np.allclose(out["plan_logits"], again["plan_logits"], atol=1e-5)
    assert loaded["config"]["center_loss_weight"] == 0.01 and loaded["config"]["plan_consistency"] is True
    assert run(loaded, val).shape == (8, 4)


def test_fit_rejects_missing_residual_or_plan_targets():
    cfg = TrainConfig(labels=LABELS, input_mode="dual_residual", epochs=1, batch=8, width=4)
    with pytest.raises(ValueError, match="requires the stored cancellation residual"):
        fit(_data(8, 5, with_residual=False), _data(8, 6, with_residual=False), cfg, device="cpu", log=lambda *_: None)
    cfg = TrainConfig(labels=LABELS, input_mode="dual", plan_consistency=True, epochs=1, batch=8, width=4)
    with pytest.raises(ValueError, match="plan_consistency"):
        fit(_data(8, 5, with_plan=False), _data(8, 6, with_plan=False), cfg, device="cpu", log=lambda *_: None)


def test_models_without_auxiliary_head_report_no_plan_logits():
    cfg = TrainConfig(labels=LABELS, input_mode="dual", epochs=1, batch=8, width=4, augment=False)
    fitted = fit(_data(8, 7), _data(8, 8), cfg, device="cpu", log=lambda *_: None)
    assert infer(fitted, _data(4, 9))["plan_logits"] is None
    assert "val_plan_accuracy" not in fitted["history"][0]


def test_checkpoint_selection_ignores_plan_head(monkeypatch):
    """Selection follows known-class macro-F1 even when plan accuracy moves the other way."""
    import geoml.train as tr
    values = iter([0.2, 0.9, 0.5])
    monkeypatch.setattr(tr, "macro_f1", lambda *args, **kwargs: next(values))
    cfg = TrainConfig(labels=LABELS, input_mode="dual_residual", plan_consistency=True, epochs=3, batch=8,
                      width=4, augment=False)
    snapshots = []
    original_load = tr.SmallResNet.load_state_dict

    def recording_load(self, state, *args, **kwargs):
        snapshots.append({k: v.clone() for k, v in state.items()})
        return original_load(self, state, *args, **kwargs)

    monkeypatch.setattr(tr.SmallResNet, "load_state_dict", recording_load)
    fitted = fit(_data(8, 10), _data(8, 11), cfg, device="cpu", log=lambda *_: None)
    assert [r["val_macro_f1"] for r in fitted["history"]] == [0.2, 0.9, 0.5]
    assert fitted["best_epoch"] == 1 and fitted["best_val_macro_f1"] == 0.9
    # The restored weights are the epoch-2 snapshot, not the final epoch's.
    restored = snapshots[-1]
    assert all(torch.equal(restored[k], v) for k, v in fitted["model"].state_dict().items())


# ---- K17b: training-only operator-plan shift augmentation ----

def _b2_like(n, seed):
    """Dual data with real random plans in metadata so masks can be rebuilt."""
    from geosim.plan import plan_mask_db, random_plan
    from dataclasses import asdict
    rng = np.random.default_rng(seed)
    plans, masks = [], []
    for _ in range(n):
        pair = [random_plan(rng, 36e6), random_plan(rng, 36e6)]
        plans.append([[asdict(c) for c in plan] for plan in pair])
        masks.append(np.stack([plan_mask_db(plan) for plan in pair]).astype(np.float16))
    spec = rng.normal(-80, 3, (n, 2, 8, 512)).astype(np.float32)
    return {"spec": spec, "mask": np.stack(masks), "label": (np.arange(n) % 4).astype(np.int64),
            "seed": np.arange(n), "plan_consistency": np.zeros(n, np.int64),
            "residual": (spec[:, 0] - 15).astype(np.float32), "meta": [{"plans": p} for p in plans]}


def test_zero_shift_reproduces_stored_masks_and_nonzero_shift_moves_them():
    from geoml.train import shifted_mask_channels
    from geoml.data import SCALE_DB
    from geosim.waveform import Carrier
    d = _b2_like(3, 0)
    plans = [[Carrier(**c) for c in plan] for plan in d["meta"][0]["plans"]]
    rebuilt = shifted_mask_channels(plans, 0.0) * SCALE_DB
    assert np.abs(rebuilt - d["mask"][0].astype(np.float32)).max() < 0.02      # float16 storage rounding
    shifted = shifted_mask_channels(plans, 0.5e6) * SCALE_DB
    # A 0.5 MHz move is ~2.67 monitor bins; the mask moves right by that amount.
    core = rebuilt[0] > -3
    moved = np.roll(core, 3)
    assert np.mean((shifted[0] > -3) == moved) > 0.97 and not np.array_equal(shifted[0] > -3, core)


def test_plan_shift_only_touches_mask_channels_of_selected_training_rows():
    import geoml.train as tr
    d = _b2_like(6, 1)
    cfg = TrainConfig(labels=LABELS, input_mode="dual_residual", plan_shift_fraction=0.5, epochs=1, batch=6, width=4)
    plans = tr._training_plans(d, cfg)
    x = tr._inputs(d, cfg, None)
    gen = torch.Generator().manual_seed(5)
    expected = torch.rand(6, generator=torch.Generator().manual_seed(5)) < 0.5     # replay the selection draw
    out = tr._apply_plan_shift(x, plans, cfg, gen)
    changed = (out != x).any(dim=(1, 2, 3))
    assert torch.equal(changed, expected) and 0 < int(changed.sum())
    for row in range(6):
        assert torch.equal(out[row, [0, 1, 4]], x[row, [0, 1, 4]])        # spectra and residual untouched
        if changed[row]:
            assert not torch.equal(out[row, 2], x[row, 2]) or not torch.equal(out[row, 3], x[row, 3])
    assert torch.equal(tr._apply_plan_shift(x, plans, TrainConfig(labels=LABELS, input_mode="dual_residual",
                                                                  plan_shift_fraction=0.0), torch.Generator()), x)


def test_plan_shift_changes_training_but_never_validation_inputs():
    import geoml.train as tr
    train, val = _b2_like(8, 4), _b2_like(8, 5)
    seen = []
    original = tr._apply_plan_shift

    def spy(xb, plans, cfg, gen):
        out = original(xb, plans, cfg, gen)
        seen.append(len(plans))
        return out

    monkeypatch_target = tr
    monkeypatch_target._apply_plan_shift = spy
    try:
        cfg = TrainConfig(labels=LABELS, input_mode="dual", plan_shift_fraction=1.0, epochs=1, batch=4, width=4, augment=False)
        fitted = fit(train, val, cfg, device="cpu", log=lambda *_: None)
    finally:
        monkeypatch_target._apply_plan_shift = original
    assert seen == [4, 4]                     # two training batches, no validation batch
    assert np.array_equal(tr._inputs(val, cfg, fitted["absolute_ref_db"]).numpy(),
                          tr._inputs(val, TrainConfig(labels=LABELS, input_mode="dual"), fitted["absolute_ref_db"]).numpy())


def test_plan_shift_supports_the_co_view_with_the_co_plan_only():
    import geoml.train as tr
    d = _b2_like(3, 7)
    cfg = TrainConfig(labels=LABELS, input_mode="co", plan_shift_fraction=1.0, epochs=1, batch=3, width=4)
    plans = tr._training_plans(d, cfg)
    assert all(len(p) == 1 for p in plans)
    x = tr._inputs(d, cfg, None)
    out = tr._apply_plan_shift(x, plans, cfg, torch.Generator().manual_seed(0))
    assert torch.equal(out[:, 0], x[:, 0]) and not torch.equal(out[:, 1], x[:, 1])


def test_plan_shift_requires_metadata_plans_and_valid_config():
    d = _b2_like(4, 6)
    stripped = {**d, "meta": [{} for _ in range(4)]}
    cfg = TrainConfig(labels=LABELS, input_mode="dual", plan_shift_fraction=0.15, epochs=1, batch=4, width=4)
    with pytest.raises(ValueError, match="operator plans"):
        fit(stripped, d, cfg, device="cpu", log=lambda *_: None)
    with pytest.raises(ValueError, match="plan_shift_fraction"):
        TrainConfig(labels=LABELS, plan_shift_fraction=1.5)
    with pytest.raises(ValueError):
        TrainConfig(labels=LABELS, plan_shift_max_hz=-1.0)
    # Disabled by default: legacy configurations are unchanged.
    assert TrainConfig(labels=LABELS).plan_shift_fraction == 0.0

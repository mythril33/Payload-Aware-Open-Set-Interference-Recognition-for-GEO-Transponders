"""Independent B2 outputs and train-only learned class centers."""
from copy import deepcopy

import numpy as np
import pytest

torch = pytest.importorskip("torch")
from torch.nn import functional as F

from geoml.b2_model import B2Model


@pytest.mark.parametrize("channels", [2, 4, 5])
def test_observable_views_have_independent_heads_and_expected_shapes(channels):
    torch.manual_seed(7)
    model = B2Model(n_classes=8, width=2, in_channels=channels).eval()
    x = torch.randn(3, channels, 16, 64)
    result = model(x)
    assert set(result) == {"logits", "consistency_logits", "embedding"}
    assert result["logits"].shape == (3, 8)
    assert result["consistency_logits"].shape == (3, 2)
    assert result["embedding"].shape == (3, 32)
    assert model.class_centers.shape == (8, 32)
    assert torch.count_nonzero(model.class_centers) == 0
    before = {key: value.detach().clone() for key, value in result.items()}
    with torch.no_grad():
        model.head.weight.zero_()
        model.head.bias.fill_(9)
    changed = model(x)
    assert not torch.equal(before["logits"], changed["logits"])
    torch.testing.assert_close(before["consistency_logits"], changed["consistency_logits"], rtol=0, atol=0)
    torch.testing.assert_close(before["embedding"], changed["embedding"], rtol=0, atol=0)


def test_real_optimizer_updates_both_heads_backbone_and_selected_centers():
    torch.manual_seed(3)
    model = B2Model(width=2)
    x = torch.randn(4, 5, 16, 64)
    labels = torch.tensor([0, 1, 0, 1])
    consistency = torch.tensor([0, 0, 1, 1])
    original = {key: value.detach().clone() for key, value in model.state_dict().items()}
    output = model(x)
    loss = F.cross_entropy(output["logits"], labels) + F.cross_entropy(output["consistency_logits"], consistency)
    loss = loss + 0.01 * model.center_loss(output["embedding"], labels)
    opt = torch.optim.SGD(model.parameters(), lr=0.1)
    opt.zero_grad()
    loss.backward()
    for name in ("head.weight", "consistency_head.weight", "stem.0.weight", "class_centers"):
        parameter = dict(model.named_parameters())[name]
        assert parameter.grad is not None and torch.isfinite(parameter.grad).all()
        assert torch.count_nonzero(parameter.grad) > 0
    opt.step()
    for name in ("head.weight", "consistency_head.weight", "stem.0.weight", "class_centers"):
        assert not torch.equal(model.state_dict()[name], original[name])
    assert torch.count_nonzero(model.class_centers[2:]) == 0


def test_center_loss_is_mean_over_features_and_batch_and_not_sum():
    model = B2Model(n_classes=3, width=1)
    with torch.no_grad():
        model.class_centers[0].fill_(1)
        model.class_centers[1].fill_(-2)
    features = torch.stack([torch.full((16,), 3.), torch.full((16,), 1.)]).requires_grad_()
    labels = torch.tensor([0, 1])
    loss = model.center_loss(features, labels)
    assert loss.item() == pytest.approx((4 + 9) / 2)
    loss.backward()
    assert features.grad.abs().sum() > 0
    assert model.class_centers.grad[0].abs().sum() > 0
    assert model.class_centers.grad[1].abs().sum() > 0
    assert torch.count_nonzero(model.class_centers.grad[2]) == 0


def test_state_reload_preserves_both_outputs_and_centers_exactly():
    torch.manual_seed(13)
    model = B2Model(width=2).eval()
    with torch.no_grad():
        model.class_centers.copy_(torch.randn_like(model.class_centers))
    restored = B2Model(width=2).eval()
    restored.load_state_dict(deepcopy(model.state_dict()))
    x = torch.randn(2, 5, 16, 64)
    for name, value in model(x).items():
        torch.testing.assert_close(restored(x)[name], value, rtol=0, atol=0)
    torch.testing.assert_close(restored.class_centers, model.class_centers, rtol=0, atol=0)
    assert list(name for name, _ in model.named_parameters()).count("class_centers") == 1
    assert "head.weight" in model.state_dict() and "consistency_head.weight" in model.state_dict()


@pytest.mark.parametrize("change", [{"n_classes": 1}, {"n_classes": True}, {"n_classes": 2.5},
                                    {"width": 0}, {"width": True}, {"in_channels": 3},
                                    {"in_channels": False}, {"in_channels": 5.0}])
def test_invalid_architecture_fails_before_module_allocation(change):
    with pytest.raises(ValueError):
        B2Model(**change)


@pytest.mark.parametrize("shape,dtype", [((0, 5, 8, 64), torch.float32),
                                        ((2, 4, 8, 64), torch.float32),
                                        ((2, 5, 0, 64), torch.float32),
                                        ((2, 5, 64), torch.float32),
                                        ((2, 5, 8, 64), torch.int64)])
def test_invalid_observable_input_fails(shape, dtype):
    with pytest.raises(ValueError, match="input"):
        B2Model(width=1).eval()(torch.zeros(shape, dtype=dtype))


def test_nonfinite_inputs_or_parameters_do_not_produce_silent_nan_outputs():
    model = B2Model(width=1).eval()
    x = torch.zeros(2, 5, 8, 64)
    x[0, 0, 0, 0] = np.nan
    with pytest.raises(ValueError, match="finite"):
        model(x)
    x.zero_()
    with torch.no_grad():
        model.consistency_head.bias[0] = float("inf")
    with pytest.raises(ValueError, match="logits"):
        model(x)


@pytest.mark.parametrize("labels", [torch.tensor([0.0, 1.0]), torch.tensor([-1, 0]),
                                    torch.tensor([0, 8]), torch.tensor([[0], [1]]),
                                    torch.tensor([True, False])])
def test_invalid_center_targets_fail(labels):
    model = B2Model(width=1)
    with pytest.raises(ValueError):
        model.center_loss(torch.zeros(2, 16), labels)


def test_nonfinite_or_wrong_shape_center_features_fail():
    model = B2Model(width=1)
    for features in (torch.zeros(0, 16), torch.zeros(2, 15), torch.full((2, 16), float("nan"))):
        with pytest.raises(ValueError):
            model.center_loss(features, torch.zeros(len(features), dtype=torch.long))

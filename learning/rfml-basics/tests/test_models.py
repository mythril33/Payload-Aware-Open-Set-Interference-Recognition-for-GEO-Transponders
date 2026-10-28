"""Shape, gradient and mode checks for the three architectures.

Inputs are random tensors, not simulator output, so these tests exercise the
networks in isolation from the signal chain.
"""

from __future__ import annotations

import pytest
import torch

from rfml.models import CNN1D, MLP, ResNet1D

C = 4  # number of classes used throughout


def _build(name: str, L: int):
    if name == "mlp":
        return MLP(C, n_samples=L, hidden=(32, 16), dropout=0.1), 16  # embed = last hidden
    if name == "cnn":
        return CNN1D(C, width=8), 4 * 8
    if name == "resnet":
        return ResNet1D(C, base_width=8), 8 * 8
    raise AssertionError(name)


@pytest.mark.parametrize("name, L", [("mlp", 128), ("cnn", 128), ("resnet", 512), ("resnet", 256)])
def test_forward_and_embed_shapes(name: str, L: int) -> None:
    torch.manual_seed(0)
    model, expected_dim = _build(name, L)
    x = torch.randn(5, 2, L)
    model.eval()
    logits = model(x)
    emb = model.embed(x)
    assert tuple(logits.shape) == (5, C)
    assert tuple(emb.shape) == (5, expected_dim)
    assert model.embed_dim == expected_dim
    assert logits.dtype == torch.float32
    # The head must be exactly fc(embed), otherwise open-set scores computed on
    # embeddings would not match the logits they are paired with.
    assert torch.allclose(logits, model.fc(emb), atol=1e-6)


@pytest.mark.parametrize("name, L", [("mlp", 128), ("cnn", 128), ("resnet", 512), ("resnet", 256)])
def test_backward_gives_finite_nonzero_grads(name: str, L: int) -> None:
    torch.manual_seed(1)
    model, _ = _build(name, L)
    model.train()
    x = torch.randn(6, 2, L)
    y = torch.tensor([0, 1, 2, 3, 0, 1])
    loss = torch.nn.functional.cross_entropy(model(x), y)
    loss.backward()
    grads = [p.grad for p in model.parameters() if p.grad is not None]
    assert len(grads) > 0
    assert all(torch.isfinite(g).all() for g in grads)
    # At least one parameter must actually receive signal, not just zeros.
    assert any(float(g.abs().sum()) > 0.0 for g in grads)


def test_resnet_default_embed_dim_is_8w() -> None:
    # Documented contract: embed dim = 8 * base_width, default base_width = 16.
    model = ResNet1D(C)
    assert model.embed_dim == 128
    model.eval()
    assert tuple(model.embed(torch.randn(2, 2, 512)).shape) == (2, 128)


def test_resnet_handles_both_lengths_with_projection_shortcuts() -> None:
    # Stages 2-4 have stride-2 projection shortcuts. Both the body and the
    # shortcut must produce the same length or the addition would fail.
    model = ResNet1D(C, base_width=4, blocks=(1, 1, 1, 1))
    model.eval()
    for L in (512, 256, 130):
        assert tuple(model(torch.randn(3, 2, L)).shape) == (3, C)


def test_mlp_dropout_active_only_in_train_mode() -> None:
    # Dropout is the usual reason predictions differ between two calls. Eval
    # mode must make the output deterministic, and train mode must not.
    torch.manual_seed(2)
    model = MLP(C, n_samples=64, hidden=(32,), dropout=0.5)
    x = torch.randn(8, 2, 64)
    model.eval()
    assert torch.equal(model(x), model(x))
    model.train()
    torch.manual_seed(3)
    a = model(x)
    torch.manual_seed(4)
    b = model(x)
    assert not torch.equal(a, b)


@pytest.mark.parametrize("name, L", [("mlp", 128), ("cnn", 128), ("resnet", 128)])
def test_rejects_channel_last_layout(name: str, L: int) -> None:
    # (B, L, 2) is the classic silent error. The MLP would otherwise flatten it
    # without complaint and learn from scrambled data.
    model, _ = _build(name, L)
    with pytest.raises(ValueError, match=r"\(B, 2, L\)"):
        model(torch.randn(2, L, 2))


def test_mlp_rejects_wrong_length() -> None:
    model = MLP(C, n_samples=64)
    with pytest.raises(ValueError, match="L=64"):
        model(torch.randn(2, 2, 65))


def test_cnn_width_controls_embed_dim() -> None:
    assert CNN1D(C, width=32).embed_dim == 128
    assert CNN1D(C, width=8).embed_dim == 32


def test_resnet_rejects_bad_block_spec() -> None:
    with pytest.raises(ValueError):
        ResNet1D(C, blocks=(2, 2, 2))
    with pytest.raises(ValueError):
        ResNet1D(C, blocks=(2, 0, 2, 2))

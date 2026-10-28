"""Three 1D architectures for raw IQ frames.

Every model takes a float32 tensor of shape (B, 2, L): row 0 is the real part,
row 1 the imaginary part of the baseband frame. Every model exposes

    embed(x)   -> (B, D)   penultimate features, D = self.embed_dim
    forward(x) -> (B, C)   logits, always computed as self.fc(self.embed(x))

and the classifier head is the single layer self.fc = Linear(D, C). Open-set
code relies on this split: distances are measured on embed(x), while the
softmax/logit scores come from the same forward pass.
"""

from __future__ import annotations

import torch
from torch import nn


def _check_iq(x: torch.Tensor, n_samples: int | None = None) -> None:
    # The easiest silent bug in IQ code is passing (B, L, 2) instead of (B, 2, L).
    # A convolution would fail loudly on it, but an MLP that flattens the input
    # would happily accept it and learn from scrambled data. Check explicitly.
    if x.dim() != 3 or x.shape[1] != 2:
        raise ValueError(f"expected (B, 2, L) IQ input, got shape {tuple(x.shape)}")
    if n_samples is not None and x.shape[2] != n_samples:
        raise ValueError(f"expected L={n_samples} samples, got {x.shape[2]}")


class _IQClassifier(nn.Module):
    """Shared forward: logits are the linear head applied to the embedding.

    Subclasses set self.embed_dim and self.fc, and implement embed().
    """

    embed_dim: int
    fc: nn.Linear

    def embed(self, x: torch.Tensor) -> torch.Tensor:  # pragma: no cover - abstract
        raise NotImplementedError

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.fc(self.embed(x))


class MLP(_IQClassifier):
    """Flatten (2, L) to 2L features, then Linear/ReLU/Dropout stacks.

    A baseline that ignores the temporal structure. It is only valid for one
    fixed frame length, so n_samples is part of the architecture.
    """

    def __init__(
        self,
        n_classes: int,
        n_samples: int,
        hidden: tuple[int, ...] = (256, 128),
        dropout: float = 0.1,
    ) -> None:
        super().__init__()
        if len(hidden) == 0:
            raise ValueError("hidden must contain at least one layer width")
        self.n_samples = n_samples
        layers: list[nn.Module] = []
        d_in = 2 * n_samples
        for width in hidden:
            layers += [nn.Linear(d_in, width), nn.ReLU(), nn.Dropout(dropout)]
            d_in = width
        self.body = nn.Sequential(*layers)
        self.embed_dim = d_in  # the last hidden activation is the embedding
        self.fc = nn.Linear(self.embed_dim, n_classes)

    def embed(self, x: torch.Tensor) -> torch.Tensor:
        _check_iq(x, self.n_samples)
        # (B, 2, L) -> (B, 2L): real samples first, then imaginary samples.
        return self.body(x.flatten(1))


def _conv_bn_relu_pool(c_in: int, c_out: int) -> nn.Sequential:
    # Kernel 7 covers a few symbol periods at sps=8, so each layer sees a
    # symbol-scale neighbourhood. BN makes the conv bias redundant, so bias=False.
    return nn.Sequential(
        nn.Conv1d(c_in, c_out, kernel_size=7, padding=3, bias=False),
        nn.BatchNorm1d(c_out),
        nn.ReLU(),
        nn.MaxPool1d(2),
    )


class CNN1D(_IQClassifier):
    """Three conv blocks with channels w, 2w, 4w and global average pooling.

    Global average pooling over time makes the embedding independent of where
    the frame starts. The start offset is random in the simulator, so the
    network must not rely on absolute sample position.
    """

    def __init__(self, n_classes: int, width: int = 32) -> None:
        super().__init__()
        w = width
        self.features = nn.Sequential(
            _conv_bn_relu_pool(2, w),
            _conv_bn_relu_pool(w, 2 * w),
            _conv_bn_relu_pool(2 * w, 4 * w),
        )
        self.embed_dim = 4 * w
        self.fc = nn.Linear(self.embed_dim, n_classes)

    def embed(self, x: torch.Tensor) -> torch.Tensor:
        _check_iq(x)
        return self.features(x).mean(dim=-1)  # (B, 4w, L') -> (B, 4w)


class BasicBlock1D(nn.Module):
    """Two k=3 convolutions with a skip connection (ResNet-18 style).

    The skip path is the identity when shapes match. When the block changes
    channels or downsamples, a 1x1 strided projection makes the two paths
    agree in length and channel count. Both branches yield the same output
    length for any L, because k=3/p=1/s=2 and k=1/p=0/s=2 both give
    floor((L-1)/2)+1.
    """

    def __init__(self, c_in: int, c_out: int, stride: int) -> None:
        super().__init__()
        self.body = nn.Sequential(
            nn.Conv1d(c_in, c_out, kernel_size=3, stride=stride, padding=1, bias=False),
            nn.BatchNorm1d(c_out),
            nn.ReLU(),
            nn.Conv1d(c_out, c_out, kernel_size=3, stride=1, padding=1, bias=False),
            nn.BatchNorm1d(c_out),
        )
        if stride != 1 or c_in != c_out:
            self.shortcut: nn.Module = nn.Sequential(
                nn.Conv1d(c_in, c_out, kernel_size=1, stride=stride, bias=False),
                nn.BatchNorm1d(c_out),
            )
        else:
            self.shortcut = nn.Identity()
        self.relu = nn.ReLU()

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.relu(self.body(x) + self.shortcut(x))


class ResNet1D(_IQClassifier):
    """1D ResNet-18 layout for IQ frames.

    The stem's stride-2 convolution plus max-pool shrink L by 4 before the
    stages, which keeps the cost manageable on CPU for L=512. Stage widths are
    w, 2w, 4w and 8w. Stages 2-4 start with a stride-2 block, so the final
    length is about L/32 (16 for L=512, 8 for L=256). Global average pooling
    then gives the 8w-dimensional embedding.
    """

    def __init__(
        self,
        n_classes: int,
        base_width: int = 16,
        blocks: tuple[int, ...] = (2, 2, 2, 2),
    ) -> None:
        super().__init__()
        if len(blocks) != 4 or min(blocks) < 1:
            raise ValueError("blocks must give a block count >= 1 for each of 4 stages")
        w = base_width
        self.stem = nn.Sequential(
            nn.Conv1d(2, w, kernel_size=7, stride=2, padding=3, bias=False),
            nn.BatchNorm1d(w),
            nn.ReLU(),
            nn.MaxPool1d(3, stride=2, padding=1),
        )
        stages: list[nn.Module] = []
        c_in = w
        for stage_idx, (n_blocks, c_out) in enumerate(zip(blocks, (w, 2 * w, 4 * w, 8 * w))):
            stride = 1 if stage_idx == 0 else 2
            stages.append(BasicBlock1D(c_in, c_out, stride))
            stages += [BasicBlock1D(c_out, c_out, 1) for _ in range(n_blocks - 1)]
            c_in = c_out
        self.stages = nn.Sequential(*stages)
        self.embed_dim = 8 * w
        self.fc = nn.Linear(self.embed_dim, n_classes)

    def embed(self, x: torch.Tensor) -> torch.Tensor:
        _check_iq(x)
        x = self.stages(self.stem(x))
        return x.mean(dim=-1)  # (B, 8w, L'') -> (B, 8w)

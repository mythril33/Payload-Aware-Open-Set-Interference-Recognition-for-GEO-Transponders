"""Small ResNet with 2 (single/co-pol), 4 (dual-pol) or 5 (dual-pol + cancellation residual) channels.

An optional auxiliary head gives independent binary logits (B2/1 ``plan_consistency``,
P18 §7a). ``forward`` keeps returning known-class logits only, so every existing
caller and checkpoint remains valid; ``forward_all`` exposes the auxiliary logits.
"""
from __future__ import annotations

import torch
from torch import nn


class Block(nn.Module):
    def __init__(self, cin: int, cout: int, stride):
        super().__init__()
        self.c1 = nn.Conv2d(cin, cout, 3, stride, 1, bias=False)
        self.b1 = nn.BatchNorm2d(cout)
        self.c2 = nn.Conv2d(cout, cout, 3, 1, 1, bias=False)
        self.b2 = nn.BatchNorm2d(cout)
        self.skip = None if stride in (1, (1, 1)) and cin == cout else nn.Sequential(
            nn.Conv2d(cin, cout, 1, stride, bias=False), nn.BatchNorm2d(cout))

    def forward(self, x):
        y = torch.relu(self.b1(self.c1(x)))
        y = self.b2(self.c2(y))
        return torch.relu(y + (x if self.skip is None else self.skip(x)))


class SmallResNet(nn.Module):
    """Full-resolution stem + four residual stages; global mean and max pooling.

    The stem keeps every frequency bin so a one-bin line (a CW) reaches a non-linearity before any
    down-sampling, and max pooling keeps it from being averaged away at the end.
    """

    def __init__(self, n_classes: int, width: int = 16, in_ch: int = 2, aux_outputs: int = 0):
        super().__init__()
        if isinstance(aux_outputs, bool) or not isinstance(aux_outputs, int) or aux_outputs < 0:
            raise ValueError("aux_outputs must be a nonnegative integer")
        w = width
        self.stem = nn.Sequential(nn.Conv2d(in_ch, w, 5, 1, 2, bias=False), nn.BatchNorm2d(w), nn.ReLU())
        self.stages = nn.Sequential(Block(w, w, (1, 2)), Block(w, 2 * w, 2), Block(2 * w, 4 * w, 2),
                                    Block(4 * w, 8 * w, 2))
        self.head = nn.Linear(16 * w, n_classes)
        self.aux_head = nn.Linear(16 * w, aux_outputs) if aux_outputs else None

    @property
    def embedding_dim(self) -> int:
        return self.head.in_features

    def embed(self, x):
        y = self.stages(self.stem(x))
        return torch.cat([y.mean(dim=(2, 3)), y.amax(dim=(2, 3))], dim=1)

    def forward(self, x):
        return self.head(self.embed(x))

    def forward_all(self, x):
        """Return (known-class logits, auxiliary logits or None, embedding)."""
        features = self.embed(x)
        return self.head(features), (None if self.aux_head is None else self.aux_head(features)), features


class CenterLoss(nn.Module):
    """Prototype/center loss (Wen et al. 2016 form): mean squared distance to the class center.

    Centers are trainable parameters optimized with the network. The weight is a
    frozen training hyperparameter recorded in the experiment configuration; it is
    never tuned on test data.
    """

    def __init__(self, n_classes: int, dim: int):
        super().__init__()
        self.centers = nn.Parameter(torch.zeros(n_classes, dim))

    def forward(self, embedding, labels):
        return ((embedding - self.centers[labels]) ** 2).sum(dim=1).mean()


def n_parameters(model: nn.Module) -> int:
    return sum(p.numel() for p in model.parameters())

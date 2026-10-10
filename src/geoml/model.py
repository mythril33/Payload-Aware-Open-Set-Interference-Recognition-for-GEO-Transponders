"""Small ResNet for 2-channel (spectrogram, plan mask) inputs (P6 §3)."""
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

    def __init__(self, n_classes: int, width: int = 16, in_ch: int = 2):
        super().__init__()
        w = width
        self.stem = nn.Sequential(nn.Conv2d(in_ch, w, 5, 1, 2, bias=False), nn.BatchNorm2d(w), nn.ReLU())
        self.stages = nn.Sequential(Block(w, w, (1, 2)), Block(w, 2 * w, 2), Block(2 * w, 4 * w, 2),
                                    Block(4 * w, 8 * w, 2))
        self.head = nn.Linear(16 * w, n_classes)

    def embed(self, x):
        y = self.stages(self.stem(x))
        return torch.cat([y.mean(dim=(2, 3)), y.amax(dim=(2, 3))], dim=1)

    def forward(self, x):
        return self.head(self.embed(x))


def n_parameters(model: nn.Module) -> int:
    return sum(p.numel() for p in model.parameters())

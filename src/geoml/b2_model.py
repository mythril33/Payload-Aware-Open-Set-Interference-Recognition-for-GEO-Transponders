"""B2 observable-input ResNet with independent cause/plan-consistency outputs.

The shared embedding supports a learned class-center penalty during training.
Centers are ordinary model parameters, saved with both heads; no validation or
test feature statistics enter their definition.
"""
from __future__ import annotations

from numbers import Integral

import torch
from torch import nn

from .model import SmallResNet


def _positive_integer(value, name: str, minimum: int = 1) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral) or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return int(value)


class B2Model(SmallResNet):
    """Five-channel main model or matched two-/four-channel observable views.

    Outputs contain primary-class logits, two-class plan-consistency logits
    and the shared embedding. The consistency head is independent of the cause
    head: neither output is derived from the other's predicted class.
    """

    def __init__(self, n_classes: int = 8, width: int = 8, in_channels: int = 5):
        n_classes = _positive_integer(n_classes, "n_classes", 2)
        width = _positive_integer(width, "width")
        in_channels = _positive_integer(in_channels, "in_channels")
        if in_channels not in (2, 4, 5):
            raise ValueError("in_channels must be one of 2, 4 or 5")
        super().__init__(n_classes=n_classes, width=width, in_ch=in_channels)
        self.n_classes = n_classes
        self.in_channels = in_channels
        self.consistency_head = nn.Linear(self.embedding_dim, 2)
        self.class_centers = nn.Parameter(torch.zeros(n_classes, self.embedding_dim))

    def embed(self, x: torch.Tensor) -> torch.Tensor:
        if (not isinstance(x, torch.Tensor) or x.ndim != 4 or x.shape[0] < 1
                or x.shape[1] != self.in_channels or x.shape[2] < 1 or x.shape[3] < 1
                or not x.is_floating_point()):
            raise ValueError(f"input must be a nonempty floating [N,{self.in_channels},T,F] tensor")
        if not torch.isfinite(x).all():
            raise ValueError("model inputs must be finite")
        features = super().embed(x)
        if not torch.isfinite(features).all():
            raise ValueError("model embedding exceeds the finite numeric range")
        return features

    def forward(self, x: torch.Tensor) -> dict[str, torch.Tensor]:
        features = self.embed(x)
        logits = self.head(features)
        consistency = self.consistency_head(features)
        if not torch.isfinite(logits).all() or not torch.isfinite(consistency).all():
            raise ValueError("model logits exceed the finite numeric range")
        return {"logits": logits, "consistency_logits": consistency, "embedding": features}

    def center_loss(self, embedding: torch.Tensor, labels: torch.Tensor) -> torch.Tensor:
        """Mean squared distance, averaged over features and then samples.

        The scale is independent of embedding width. Gradients update both the
        observed embedding and selected learned centers.
        """
        if (not isinstance(embedding, torch.Tensor) or embedding.ndim != 2
                or embedding.shape[0] < 1 or embedding.shape[1] != self.embedding_dim
                or not embedding.is_floating_point() or not torch.isfinite(embedding).all()):
            raise ValueError(f"embedding must be finite floating [N,{self.embedding_dim}]")
        if (not isinstance(labels, torch.Tensor) or labels.shape != (embedding.shape[0],)
                or labels.dtype not in (torch.uint8, torch.int8, torch.int16, torch.int32, torch.int64)
                or labels.device != embedding.device or self.class_centers.device != embedding.device):
            raise ValueError("labels must be one integer class index per embedding on the model device")
        if torch.any(labels < 0) or torch.any(labels >= self.n_classes):
            raise ValueError("center-loss labels are outside the configured class range")
        distance = (embedding - self.class_centers[labels.long()]).square().mean()
        if not torch.isfinite(distance):
            raise ValueError("center loss exceeds the finite numeric range")
        return distance

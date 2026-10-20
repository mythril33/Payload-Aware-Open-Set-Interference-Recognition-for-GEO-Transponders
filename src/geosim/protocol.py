"""Development open-set protocol on top of frozen A1 observations.

B1-dev/1 holds out one non-clean A1 family. It is not the final eight-class B1
benchmark. Validation scenario groups are split into model selection and
rejection calibration, so neither calibration nor final unknowns select weights.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .classes import LABELS

PROTOCOL = "B1-dev/1"


def _subset(data: dict, keep: np.ndarray, labels: tuple[str, ...]) -> dict:
    indices = {LABELS.index(label): i for i, label in enumerate(labels)}
    keep = keep & np.isin(data["label"], list(indices))
    return {"spec": data["spec"][keep], "mask": data["mask"][keep],
            "label": np.array([indices[int(label)] for label in data["label"][keep]], dtype=np.int64),
            "seed": data["seed"][keep],
            "meta": [meta for meta, selected in zip(data["meta"], keep) if selected]}


@dataclass(frozen=True)
class HoldoutProtocol:
    holdout_label: str = "swept_cw"
    calibration_fraction: float = 0.5
    split_seed: int = 0

    def __post_init__(self):
        if self.holdout_label not in LABELS[1:]:
            raise ValueError(f"holdout_label must be a non-clean family from {LABELS[1:]}")
        if not 0 < self.calibration_fraction < 1:
            raise ValueError("calibration_fraction must be between 0 and 1")
        if isinstance(self.split_seed, bool) or not isinstance(self.split_seed, int) or self.split_seed < 0:
            raise ValueError("split_seed must be a nonnegative integer")

    @property
    def known_labels(self) -> tuple[str, ...]:
        return tuple(label for label in LABELS if label != self.holdout_label)

    def partition(self, train: dict, validation: dict, test: dict) -> dict[str, dict]:
        """Return train/validation/calibration/known_test/unknown_test datasets.

        All variants of one A1 seed form one scenario group. Known and unknown
        test samples may intentionally share a group, never with another role.
        Unknown-family samples in source train/validation are discarded.
        """
        sources = {"train": train, "validation": validation, "test": test}
        groups = {}
        for name, data in sources.items():
            n = len(data["label"])
            if n == 0 or any(len(data[key]) != n for key in ("spec", "mask", "seed", "meta")):
                raise ValueError(f"{name} has empty or inconsistent sample arrays")
            if not np.issubdtype(data["label"].dtype, np.integer) or not np.all(np.isin(data["label"], range(len(LABELS)))):
                raise ValueError(f"{name} contains invalid A1 label indices")
            if not np.issubdtype(data["seed"].dtype, np.integer):
                raise ValueError(f"{name} scenario seeds must be integers")
            groups[name] = np.unique(data["seed"])
        for left, right in (("train", "validation"), ("train", "test"), ("validation", "test")):
            if np.intersect1d(groups[left], groups[right]).size:
                raise ValueError(f"scenario group leakage between {left} and {right}")
        if len(groups["validation"]) < 2:
            raise ValueError("validation needs at least two scenario groups for separate calibration")
        shuffled = np.random.default_rng(self.split_seed).permutation(groups["validation"])
        count = max(1, min(len(shuffled) - 1, int(np.ceil(len(shuffled) * self.calibration_fraction))))
        calibration_groups = shuffled[:count]
        is_calibration = np.isin(validation["seed"], calibration_groups)
        parts = {
            "train": _subset(train, np.ones(len(train["label"]), bool), self.known_labels),
            "validation": _subset(validation, ~is_calibration, self.known_labels),
            "calibration": _subset(validation, is_calibration, self.known_labels),
            "known_test": _subset(test, np.ones(len(test["label"]), bool), self.known_labels),
            "unknown_test": _subset(test, np.ones(len(test["label"]), bool), (self.holdout_label,)),
        }
        for name, data in parts.items():
            expected = 1 if name == "unknown_test" else len(self.known_labels)
            if set(data["label"].tolist()) != set(range(expected)):
                raise ValueError(f"{name} must contain every requested class; generate more scenario seeds")
        return parts


def partition_summary(parts: dict[str, dict]) -> dict:
    return {name: {"n_samples": len(data["label"]),
                   "scenario_ids": [int(seed) for seed in np.unique(data["seed"])],
                   "per_class": np.bincount(data["label"]).tolist()}
            for name, data in parts.items()}

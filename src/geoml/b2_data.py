"""Observed B2 channels and bounded-memory feature-shard access.

Cancellation residuals use the same co-feed reference as both measured PSDs.
Only the six declared observation/target arrays enter this module; simulator
metadata are deliberately ignored.
"""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import numpy as np

from geosim import FS_MON
from geosim.b2_protocol import LABELS

from .data import CLIP_DB, CORE_DB, SCALE_DB, preprocess_dual, reference_level

ARRAY_KEYS = ("spec", "mask", "residual", "label", "seed", "plan_consistency")
CHANNELS = {"b2": 5, "dual": 4, "co": 2}


def validate_observations(data, n_classes=len(LABELS)):
    """Check one physical shard or an in-memory development batch."""
    if not isinstance(data, Mapping) or any(key not in data for key in ARRAY_KEYS):
        raise ValueError("B2 data require spec, mask, residual, label, seed and plan_consistency")
    arrays = {key: np.asarray(data[key]) for key in ARRAY_KEYS}
    spec, mask, residual = (arrays[key] for key in ("spec", "mask", "residual"))
    if (spec.ndim != 4 or spec.shape[1] != 2 or not spec.shape[0]
            or not spec.shape[2] or not spec.shape[3] or spec.dtype.kind not in "iuf"):
        raise ValueError("B2 spec must be nonempty numeric [N,2,T,F]")
    if mask.shape != (len(spec), 2, spec.shape[3]) or mask.dtype.kind not in "iuf":
        raise ValueError("B2 masks must match [N,2,F]")
    if residual.shape != (len(spec), spec.shape[2], spec.shape[3]) or residual.dtype.kind not in "iuf":
        raise ValueError("B2 residual PSD must match [N,T,F]")
    if not all(np.isfinite(value).all() for value in (spec, mask, residual)):
        raise ValueError("B2 observed arrays must be finite")
    if np.any(~np.any(mask > CORE_DB, axis=2)):
        raise ValueError("each B2 operator plan must contain a carrier core bin")
    for key, low, high in (("label", 0, n_classes - 1), ("plan_consistency", 0, 1),
                           ("seed", 0, np.iinfo(np.int64).max)):
        values = arrays[key]
        if (values.shape != (len(spec),) or values.dtype.kind not in "iu"
                or np.any(values < low) or np.any(values > high)):
            raise ValueError(f"B2 {key} must contain one valid integer per observation")
    return arrays


def preprocess_b2(spec, mask, residual, *, level="carrier", time_pool=2,
                  absolute_ref_db=None, view="b2"):
    """Build co-only, four-channel or five-channel observed inputs.

    Five-channel order: co PSD, cross PSD, co plan, cross plan, co residual.
    The residual retains physical dB(power/Hz) units until common-reference
    normalization. Time pooling always averages linear power.
    """
    if view not in CHANNELS:
        raise ValueError("B2 view must be b2, dual or co")
    values, plans, leftover = np.asarray(spec), np.asarray(mask), np.asarray(residual)
    # Reuse the validated dual preprocessing contract for the first channels.
    first = preprocess_dual(values, plans, level, time_pool, absolute_ref_db,
                            view="co" if view == "co" else "dual")
    if (leftover.shape != (len(values), values.shape[2], values.shape[3])
            or leftover.dtype.kind not in "iuf" or not np.isfinite(leftover).all()):
        raise ValueError("B2 residual PSD must be finite [N,T,F] matching observed spectra")
    if view != "b2":
        return first
    try:
        with np.errstate(over="raise", invalid="raise", divide="raise", under="ignore"):
            ref = (reference_level(values[:, 0], plans[:, 0])[:, None, None]
                   if level == "carrier" else np.float32(absolute_ref_db))
            leftover = leftover.astype(np.float32)
            n, t, f = leftover.shape
            if time_pool > 1:
                power = 10 ** (leftover.reshape(n, t // time_pool, time_pool, f) / 10)
                leftover = 10 * np.log10(power.mean(axis=2))
            normalized = np.clip(leftover - ref, *CLIP_DB) / SCALE_DB
            result = np.concatenate((first, normalized[:, None]), axis=1).astype(np.float32)
    except FloatingPointError as error:
        raise ValueError("B2 residual exceeds finite preprocessing range") from error
    if not np.isfinite(result).all():
        raise ValueError("preprocessed B2 observations must be finite")
    return result


def augment_inputs(values, *, view, rng, plan_shift_probability=0.15,
                   max_plan_shift_hz=0.5e6, mirror=True, time_shift=True,
                   return_shifts=False):
    """Training-only mask jitter plus matched mirroring and time rolling.

    Mask jitter acts on model mask channels after frontend preprocessing. It
    does not recompute receiver cancellation and is not a full receiver-plan-
    error experiment. Interpolation occurs in mask power, with floor padding.
    """
    x = np.array(values, dtype=np.float32, copy=True)
    if view not in CHANNELS or x.ndim != 4 or x.shape[1] != CHANNELS[view] or not len(x):
        raise ValueError("augmentation inputs do not match the selected B2 view")
    if not isinstance(rng, np.random.Generator):
        raise ValueError("augmentation requires a numpy Generator")
    if mirror:
        flip = rng.random(len(x)) < 0.5
        x[flip] = x[flip, :, :, ::-1]
    if time_shift:
        x = np.roll(x, int(rng.integers(x.shape[2])), axis=2)
    shifts = np.zeros(len(x), dtype=np.float64)
    selected = np.flatnonzero(rng.random(len(x)) < plan_shift_probability)
    shifts[selected] = rng.uniform(-max_plan_shift_hz, max_plan_shift_hz, len(selected))
    masks = (1,) if view == "co" else (2, 3)
    frequencies = np.fft.fftshift(np.fft.fftfreq(x.shape[-1], 1 / FS_MON))
    floor_power = 10 ** (-60 / 10)
    for row in selected:
        for channel in masks:
            power = 10 ** (x[row, channel, 0].astype(np.float64) * SCALE_DB / 10)
            shifted = np.interp(frequencies - shifts[row], frequencies, power,
                                left=floor_power, right=floor_power)
            plan = 10 * np.log10(np.maximum(shifted, floor_power)) / SCALE_DB
            x[row, channel] = plan[None]
    return (x, shifts) if return_shifts else x


class FeatureRole:
    """A validated in-memory batch or lazily read role from B2-features/1."""

    def __init__(self, data, *, manifest_cache=None):
        self.root = None
        self.role = None
        self._arrays = None
        if isinstance(data, Mapping):
            self._arrays = validate_observations(data)
            self.role = data.get("role")
            self.groups = np.unique(self._arrays["seed"])
            self.n_samples = len(self._arrays["label"])
            self.shard_counts = [self.n_samples]
        elif isinstance(data, (tuple, list)) and len(data) == 2:
            from geosim.b2_features import read_feature_manifest

            root, role = data
            if not isinstance(role, str) or role not in ("train", "val-select", "val-calib", "test"):
                raise ValueError("feature role must be train, val-select, val-calib or test")
            self.root, self.role = Path(root), role
            key = str(self.root.resolve())
            manifest = (manifest_cache or {}).get(key)
            if manifest is None:
                manifest = read_feature_manifest(self.root)
                if manifest_cache is not None:
                    manifest_cache[key] = manifest
            if manifest.get("protocol") != "B2-features/1" or tuple(manifest.get("labels", ())) != LABELS:
                raise ValueError("B2 training requires the compatible observed-feature artifact")
            if role not in manifest["roles"]:
                raise ValueError(f"feature role {role!r} was not generated")
            info = manifest["roles"][role]
            self.groups = np.asarray(info["scenario_seeds"], dtype=np.int64)
            self.n_samples = int(info["n_samples"])
            self.shard_counts = [int(shard["n_samples"]) for shard in info["shards"]]
            if not self.n_samples or sum(self.shard_counts) != self.n_samples:
                raise ValueError("feature role has invalid shard sample counts")
        else:
            raise ValueError("B2 data must be an array mapping or (feature directory, role)")

    def __len__(self):
        return self.n_samples

    def shards(self, order=None):
        if self._arrays is not None:
            yield self._arrays
        else:
            from geosim.b2_features import iter_feature_shards

            for shard in iter_feature_shards(self.root, self.role, indices=order):
                yield validate_observations(shard)

    def n_batches(self, batch):
        return sum(-(-count // batch) for count in self.shard_counts)


def as_role(data, *, manifest_cache=None):
    return data if isinstance(data, FeatureRole) else FeatureRole(data, manifest_cache=manifest_cache)


def iter_batches(source, config, absolute_ref_db, *, shuffle=False, rng=None, augment=False,
                 batch=None):
    """Bound memory to a raw shard plus one preprocessed batch."""
    size = config.batch if batch is None else batch
    order = rng.permutation(len(source.shard_counts)).tolist() if shuffle else None
    for shard in source.shards(order):
        indices = rng.permutation(len(shard["label"])) if shuffle else np.arange(len(shard["label"]))
        for start in range(0, len(indices), size):
            selection = indices[start:start + size]
            x = preprocess_b2(shard["spec"][selection], shard["mask"][selection], shard["residual"][selection],
                              level=config.level, time_pool=config.time_pool,
                              absolute_ref_db=absolute_ref_db, view=config.view)
            if augment:
                x = augment_inputs(x, view=config.view, rng=rng,
                                   plan_shift_probability=config.plan_shift_probability,
                                   max_plan_shift_hz=config.max_plan_shift_hz)
            yield {"x": x, **{key: shard[key][selection] for key in ("label", "seed", "plan_consistency")}}

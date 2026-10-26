"""Turning stored spectrograms into model inputs (P6 §2)."""
from __future__ import annotations

import numpy as np

CORE_DB = -3.0          # mask level above which a bin counts as "inside a planned carrier"
CLIP_DB = (-60.0, 20.0)
SCALE_DB = 20.0


def reference_level(spec_db: np.ndarray, mask_db: np.ndarray) -> np.ndarray:
    """Per-sample mean PSD (dB) over the planned carriers' core bins: the level everything is referred to."""
    psd = np.mean(10 ** (spec_db.astype(np.float32) / 10), axis=1)            # (N, F), time-averaged
    core = mask_db > CORE_DB
    return 10 * np.log10((psd * core).sum(axis=1) / core.sum(axis=1))


def preprocess(spec_db: np.ndarray, mask_db: np.ndarray, level: str = "carrier", time_pool: int = 2,
               absolute_ref_db: float | None = None) -> np.ndarray:
    """(N,128,512) dB spectrograms and (N,512) masks -> (N,2,128/time_pool,512) float32.

    level="carrier":  each sample is referred to its own planned-carrier level, so absolute power
                      (downlink fade, amplifier compression, calibration) is not visible to the model.
    level="absolute": one fixed reference for all samples (absolute_ref_db, taken from training data).
    """
    spec = spec_db.astype(np.float32)
    if level == "carrier":
        ref = reference_level(spec_db, mask_db)[:, None, None]
    elif level == "absolute":
        if absolute_ref_db is None:
            raise ValueError("absolute level needs absolute_ref_db from the training split")
        ref = np.float32(absolute_ref_db)
    else:
        raise ValueError(f"unknown level mode {level!r}")
    n, t, f = spec.shape
    if time_pool > 1:                      # longer integration: average power, not dB
        spec = 10 * np.log10(np.mean(10 ** (spec.reshape(n, t // time_pool, time_pool, f) / 10), axis=2))
    x = np.clip(spec - ref, *CLIP_DB) / SCALE_DB
    m = np.broadcast_to((mask_db.astype(np.float32) / SCALE_DB)[:, None, :], x.shape)
    return np.stack([x, m], axis=1).astype(np.float32)


VIEWS = ("co", "dual", "dual_residual")

# B2-C2-ablation/1: matched views that isolate operator-plan availability (separately versioned; the three canonical
# views above and their preprocessing are unchanged). ``*_noplan`` receive no plan-derived channel and no plan-derived
# level reference; ``*_planmask`` receive exactly the same spectral channels plus the operator-plan mask channels.
C2_NOPLAN_VIEWS = ("co_noplan", "dual_noplan")
C2_PLANMASK_VIEWS = ("co_planmask", "dual_planmask")
C2_VIEWS = C2_NOPLAN_VIEWS + C2_PLANMASK_VIEWS
VIEW_CHANNELS = {"single": 2, "co": 2, "dual": 4, "dual_residual": 5,
                 "co_noplan": 1, "dual_noplan": 2, "co_planmask": 2, "dual_planmask": 4}
OBSERVED_LEVEL_PERCENTILE = 90.0   # C2 plan-free level reference: carriers sit near 0 dB without being told where they are


def preprocess_dual(spec_db: np.ndarray, mask_db: np.ndarray, level: str = "carrier", time_pool: int = 2,
                    absolute_ref_db: float | None = None, view: str = "dual",
                    residual_db: np.ndarray | None = None) -> np.ndarray:
    """Two observed polarizations and their independent plans -> model channels.

    Inputs are spectra ``[N,2,T,F]`` and plan masks ``[N,2,F]``. ``view='dual'``
    returns ``[co PSD, cross PSD, co plan, cross plan]``; ``view='co'`` returns
    the existing two-channel co-pol preprocessing as a matched ablation;
    ``view='dual_residual'`` appends the stored observation-based co-pol
    cancellation residual PSD ``residual_db`` ``[N,T,F]`` as a fifth channel
    (P18 §5), referred to the same co-pol planned-carrier level so that
    cancellation depth is visible relative to the carriers.

    Both PSDs share the co-pol planned-carrier reference. Independent per-pol
    normalization would erase the relative polarization power needed to study
    leakage. Time pooling averages linear power, not dB. The inputs contain
    observable spectra, operator masks and the observation-derived residual
    only, never the generating XPD, back-off or event truth.
    """
    spec, mask = np.asarray(spec_db), np.asarray(mask_db)
    if (spec.dtype.kind not in "iuf" or spec.ndim != 4 or not len(spec)
            or spec.shape[1] != 2 or not spec.shape[2] or not spec.shape[3]):
        raise ValueError("dual spec must be a nonempty numeric [N,2,time,frequency] array")
    if mask.dtype.kind not in "iuf" or mask.shape != (len(spec), 2, spec.shape[3]):
        raise ValueError("dual mask must be a numeric [N,2,frequency] array matching spec")
    if not np.isfinite(spec).all() or not np.isfinite(mask).all():
        raise ValueError("dual model observations and masks must be finite")
    if isinstance(time_pool, bool) or not isinstance(time_pool, int) or time_pool < 1:
        raise ValueError("time_pool must be a positive integer")
    if spec.shape[2] % time_pool:
        raise ValueError("time_pool must divide the spectrogram time dimension")
    if np.any(~np.any(mask > CORE_DB, axis=2)):
        raise ValueError("each polarization plan mask must contain a planned carrier core bin")
    if view not in VIEWS:
        raise ValueError(f"dual view must be one of {VIEWS}")
    if view == "dual_residual":
        if residual_db is None:
            raise ValueError("view 'dual_residual' requires the stored cancellation residual")
        residual = np.asarray(residual_db)
        if (residual.dtype.kind not in "iuf" or residual.shape != (len(spec), spec.shape[2], spec.shape[3])
                or not np.isfinite(residual).all()):
            raise ValueError("residual must be a finite numeric [N,time,frequency] array matching spec")
    elif residual_db is not None:
        raise ValueError(f"view {view!r} does not take a residual channel")
    if level not in ("carrier", "absolute"):
        raise ValueError(f"unknown level mode {level!r}")
    if level == "absolute":
        raw_ref = np.asarray(absolute_ref_db)
        if raw_ref.shape != () or raw_ref.dtype.kind not in "iuf" or not np.isfinite(raw_ref):
            raise ValueError("absolute level needs a finite absolute_ref_db from the training split")
    try:
        with np.errstate(over="raise", invalid="raise", divide="raise", under="ignore"):
            if view == "co":
                result = preprocess(spec[:, 0], mask[:, 0], level, time_pool, absolute_ref_db)
            else:
                values = spec.astype(np.float32)
                if level == "carrier":
                    ref = reference_level(values[:, 0], mask[:, 0])[:, None, None, None]
                else:
                    ref = np.float32(absolute_ref_db)
                n, _, t, f = values.shape
                if view == "dual_residual":
                    values = np.concatenate([values, residual.astype(np.float32)[:, None]], axis=1)
                if time_pool > 1:
                    power = 10 ** (values.reshape(n, values.shape[1], t // time_pool, time_pool, f) / 10)
                    values = 10 * np.log10(power.mean(axis=3))
                normalized = np.clip(values - ref, *CLIP_DB) / SCALE_DB
                plans = np.broadcast_to(mask.astype(np.float32)[:, :, None, :] / SCALE_DB, normalized[:, :2].shape)
                channels = [normalized[:, :2], plans]
                if view == "dual_residual":
                    channels.append(normalized[:, 2:3])
                result = np.concatenate(channels, axis=1).astype(np.float32)
    except FloatingPointError as error:
        raise ValueError("dual observations exceed the supported finite preprocessing range") from error
    if not np.isfinite(result).all():
        raise ValueError("preprocessed dual observations must be finite")
    return result


EXTRA_ARRAYS = ("residual", "plan_consistency")


def select(d: dict, labels: tuple, all_labels: tuple) -> dict:
    """Keep the samples whose label is in `labels` and re-index labels to that order.

    Optional per-sample arrays (``residual``, ``plan_consistency``) are carried along.
    """
    keep_idx = [all_labels.index(lab) for lab in labels]
    keep = np.isin(d["label"], keep_idx)
    remap = {old: new for new, old in enumerate(keep_idx)}
    result = {"spec": d["spec"][keep], "mask": d["mask"][keep], "seed": d["seed"][keep],
              "label": np.array([remap[v] for v in d["label"][keep]], np.int64),
              "meta": [m for m, k in zip(d["meta"], keep) if k]}
    for key in EXTRA_ARRAYS:
        if key in d:
            result[key] = np.asarray(d[key])[keep]
    return result


def observed_level_db(spec_db: np.ndarray) -> np.ndarray:
    """Plan-free per-sample level (dB) of co-pol spectrograms ``[N,T,F]``.

    The ``OBSERVED_LEVEL_PERCENTILE`` of the time-averaged linear PSD over frequency. It reads the observed spectrum only,
    never an operator plan, so it can reference the level of a model that must not know the plan. Unlike
    ``reference_level`` it is not tied to planned-carrier bins and is therefore not shifted by a wrong or missing plan.
    """
    spec = np.asarray(spec_db)
    if spec.dtype.kind not in "iuf" or spec.ndim != 3 or not len(spec) or not spec.shape[1] or not spec.shape[2]:
        raise ValueError("observed level needs a nonempty numeric [N,time,frequency] spectrogram")
    if not np.isfinite(spec).all():
        raise ValueError("observed level needs finite spectra")
    try:
        with np.errstate(over="raise", invalid="raise", divide="raise", under="ignore"):
            level = 10 * np.log10(np.mean(10 ** (spec.astype(np.float32) / 10), axis=1))
    except FloatingPointError as error:
        raise ValueError("observed level exceeds the supported finite range") from error
    return np.percentile(level.astype(np.float64), OBSERVED_LEVEL_PERCENTILE, axis=1)


def preprocess_c2(spec_db: np.ndarray, mask_db: np.ndarray | None, view: str, time_pool: int,
                  absolute_ref_db: float) -> np.ndarray:
    """Model channels of a B2-C2-ablation/1 view.

    ``spec_db`` is ``[N,2,T,F]``; only the polarizations the view uses are read. All four views share one plan-free
    absolute reference ``absolute_ref_db`` (the training mean of ``observed_level_db``). ``*_noplan`` views must be called
    with ``mask_db=None`` and return spectra only; ``*_planmask`` views append the operator-plan mask channels in the
    canonical order, so their leading channels are bit-identical to the matching ``*_noplan`` view.
    """
    if view not in C2_VIEWS:
        raise ValueError(f"C2 view must be one of {C2_VIEWS}")
    spec = np.asarray(spec_db)
    if (spec.dtype.kind not in "iuf" or spec.ndim != 4 or not len(spec) or spec.shape[1] != 2
            or not spec.shape[2] or not spec.shape[3]):
        raise ValueError("C2 spec must be a nonempty numeric [N,2,time,frequency] array")
    if isinstance(time_pool, bool) or not isinstance(time_pool, int) or time_pool < 1 or spec.shape[2] % time_pool:
        raise ValueError("time_pool must be a positive integer dividing the spectrogram time dimension")
    reference = np.asarray(absolute_ref_db)
    if reference.shape != () or reference.dtype.kind not in "iuf" or not np.isfinite(reference):
        raise ValueError("C2 views need a finite plan-free absolute_ref_db from the training split")
    n_pol = 1 if view.startswith("co_") else 2
    if view in C2_NOPLAN_VIEWS:
        if mask_db is not None:
            raise ValueError(f"view {view!r} is plan-free and takes no plan masks")
        plans = None
    else:
        plans = np.asarray(mask_db)
        if plans.dtype.kind not in "iuf" or plans.shape != (len(spec), 2, spec.shape[3]) or not np.isfinite(plans).all():
            raise ValueError("planmask views need finite numeric [N,2,frequency] plan masks matching spec")
        if np.any(~np.any(plans[:, :n_pol] > CORE_DB, axis=2)):
            raise ValueError("each used plan mask must contain a planned carrier core bin")
    if not np.isfinite(spec[:, :n_pol]).all():
        raise ValueError("C2 observations must be finite")
    try:
        with np.errstate(over="raise", invalid="raise", divide="raise", under="ignore"):
            values = spec[:, :n_pol].astype(np.float32)
            n, pols, t, f = values.shape
            if time_pool > 1:
                power = 10 ** (values.reshape(n, pols, t // time_pool, time_pool, f) / 10)
                values = 10 * np.log10(power.mean(axis=3))
            channels = [np.clip(values - np.float32(reference), *CLIP_DB) / SCALE_DB]
            if plans is not None:
                channels.append(np.broadcast_to(plans[:, :n_pol].astype(np.float32)[:, :, None, :] / SCALE_DB, channels[0].shape))
            result = np.concatenate(channels, axis=1).astype(np.float32)
    except FloatingPointError as error:
        raise ValueError("C2 observations exceed the supported finite preprocessing range") from error
    if not np.isfinite(result).all():
        raise ValueError("preprocessed C2 observations must be finite")
    return result

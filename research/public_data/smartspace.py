"""Small SmartSpace MAT loaders following the published observation/label shapes.

The two official download folders currently require authentication. Consequently
these are explicit, fixture-tested MAT import contracts, not a claim that the
unavailable official files or their variable names have been inspected. Callers
must supply exact keys and verify the file/label convention before real results.
No B2 data, operator plans, polarization or physical power units are inferred.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
from scipy.io import loadmat, whosmat


MAX_FILE_BYTES = 256 * 1024 * 1024
MAX_ROWS = 20_000
ONBOARD_REPRESENTATIONS = {
    "full_magnitude": (1000, False), "full_complex": (1000, True),
    "reduced_magnitude": (100, False), "reduced_complex": (100, True),
}
ONBOARD_URL = "https://fnr-smartspace-project.uni.lu/satellite-on-board-interference-detection/"
NGSO_URL = "https://fnr-smartspace-project.uni.lu/ngso-to-gsos-users-interference/"


def _file(path):
    value = Path(path)
    if not value.is_file() or not 0 < value.stat().st_size <= MAX_FILE_BYTES:
        raise ValueError("MAT file must be a nonempty regular file of at most 256 MiB")
    return value


def _key(value):
    if type(value) is not str or not value or value.startswith("__"):
        raise ValueError("explicit MAT variable name required")
    return value


def _shape(shape, width, axis):
    if type(axis) is not int or axis not in (0, 1):
        raise ValueError("samples_axis must explicitly be 0 or 1")
    if len(shape) != 2 or shape[1 - axis] != width or not 1 <= shape[axis] <= MAX_ROWS:
        raise ValueError(f"expected 1..{MAX_ROWS} samples and exactly {width} observed bins")


def _variables(path, names, *, expected_shapes):
    path = _file(path)
    names = [_key(name) for name in names]
    if len(set(names)) != len(names):
        raise ValueError("feature and label variables must be distinct")
    try:
        headers = whosmat(path)
        info = {name: (shape, kind) for name, shape, kind in headers}
        if len(info) != len(headers):
            raise ValueError("duplicate MAT variable names")
        for name in names:
            if name not in info:
                raise ValueError(f"explicit MAT variable is absent: {name}")
            shape, kind = info[name]
            if kind not in {"double", "single", "int8", "uint8", "int16", "uint16", "int32", "uint32", "int64", "uint64", "logical"}:
                raise ValueError("plain numeric MAT arrays required")
            expected_shapes[name](shape)
        values = loadmat(path, variable_names=names, squeeze_me=False, struct_as_record=True)
    except NotImplementedError as error:
        raise ValueError("MATLAB v7.3/HDF5 is not supported by this loader; inspect and convert explicitly") from error
    except (IndexError, OSError) as error:
        raise ValueError("invalid or truncated MAT file; HTML login pages are not data") from error
    return path, values


def _numeric(value, *, complex_allowed=False, nonnegative=False):
    if (not isinstance(value, np.ndarray) or value.dtype.kind not in "fiucb"
            or (np.iscomplexobj(value) and not complex_allowed) or not np.isfinite(value).all()):
        raise ValueError("finite numeric observations with the declared representation required")
    if nonnegative and np.any(value < 0):
        raise ValueError("magnitude observations cannot be negative")
    return value


def _sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _metadata(path, source, representation, features_key, samples_axis):
    return {"path": str(path.resolve()), "sha256": _sha(path), "source_url": source,
            "representation": representation, "features_key": features_key,
            "samples_axis": samples_axis, "units": "native numerical amplitude; absolute RF power calibration unavailable",
            "sample_rate_hz": None, "frequency_grid_hz": None, "recording_groups_available": False,
            "operator_plan_available": False, "dual_polarization_available": False,
            "source_authenticity_verified": False,
            "raw_format_status": "MAT import contract; official raw files not accessible during implementation"}


def load_onboard_mat(path, *, features_key, labels_key, representation, samples_axis=0):
    """Preserve FFT values and the official five-indicator subband labels.

    Five zeros mean clean; one bit identifies subband 1..5. ``labels`` returns
    those six documented location classes, not interferer-type or B2 classes.
    No numeric-class vector is guessed or accepted instead of native indicators.
    Complex FFT phase is retained; a detector must explicitly choose its own
    observation-derived statistic (e.g. mean squared magnitude).
    """
    if representation not in ONBOARD_REPRESENTATIONS:
        raise ValueError("unknown on-board FFT representation")
    width, complex_allowed = ONBOARD_REPRESENTATIONS[representation]
    path, values = _variables(path, [features_key, labels_key], expected_shapes={
        features_key: lambda shape: _shape(shape, width, samples_axis),
        labels_key: lambda shape: _shape(shape, 5, samples_axis)})
    features = values[features_key] if samples_axis == 0 else values[features_key].T
    native = values[labels_key] if samples_axis == 0 else values[labels_key].T
    _numeric(features, complex_allowed=complex_allowed, nonnegative=not complex_allowed)
    _numeric(native)
    if native.shape[0] != features.shape[0] or not np.isin(native, [0, 1]).all() or np.any(native.sum(axis=1) > 1):
        raise ValueError("one five-bit all-zero/one-hot subband label per sample required")
    native = native.astype(np.int8, copy=False)
    labels = np.where(native.sum(axis=1) == 0, 0, native.argmax(axis=1) + 1).astype(np.int8)
    metadata = _metadata(path, ONBOARD_URL, representation, features_key, samples_axis)
    metadata.update(labels_key=labels_key, label_meaning="0 clean; 1..5 interference subband location",
                    label_encoding="five indicators: all-zero clean, otherwise exactly one subband bit",
                    official_split_counts={"train": 12000, "validation": 3000},
                    official_test_partition="not published on the source page")
    return {"features": features, "labels": labels, "native_labels": native, "groups": None, "metadata": metadata}


def load_ngso_mat(path, *, features_key, split, labels_path=None, labels_key=None,
                  positive_label=None, samples_axis=0):
    """Import 800 time- or frequency-domain magnitudes, never IQ or metadata.

    Official train/validation populations are clean-only. Mixed test label
    direction is not documented on the public page: ``positive_label`` must be
    supplied after its meaning is verified, not inferred from test performance.
    The 801/802-column comparison sets are intentionally not accepted here.
    """
    if split not in ("train", "validation", "test"):
        raise ValueError("split must be train, validation or test")
    path, values = _variables(path, [features_key], expected_shapes={
        features_key: lambda shape: _shape(shape, 800, samples_axis)})
    features = values[features_key] if samples_axis == 0 else values[features_key].T
    _numeric(features, nonnegative=True)
    metadata = _metadata(path, NGSO_URL, "time-or-frequency magnitude, 800 observed bins", features_key, samples_axis)
    metadata.update(split=split, official_split_counts={"train": 11500, "validation": 1302, "test": 4470})
    if split in ("train", "validation"):
        if labels_path is not None or labels_key is not None or positive_label is not None:
            raise ValueError("clean-only train/validation use the documented split declaration, not test label arguments")
        native = None
        labels = np.zeros(features.shape[0], dtype=np.int8)
        metadata.update(labels_source="official clean-only split declaration; no per-row native labels read")
    else:
        if labels_path is None or labels_key is None or type(positive_label) not in (int, float) or not np.isfinite(positive_label):
            raise ValueError("mixed test requires explicit label file/key and verified positive_label; no default convention")
        def label_shape(shape):
            if len(shape) != 2 or 1 not in shape or np.prod(shape) != features.shape[0]:
                raise ValueError("one native binary test label per feature row required")
        label_file, label_values = _variables(labels_path, [labels_key], expected_shapes={labels_key: label_shape})
        native = _numeric(label_values[labels_key]).reshape(-1)
        unique = np.unique(native)
        if len(unique) != 2 or positive_label not in unique:
            raise ValueError("exactly two native label values and an explicitly identified positive value required")
        labels = (native == positive_label).astype(np.int8)
        metadata.update(labels_path=str(label_file.resolve()), labels_sha256=_sha(label_file), labels_key=labels_key,
                        positive_label=positive_label, label_convention="caller-supplied; verify from source before experiments")
    return {"features": features, "labels": labels, "native_labels": native, "groups": None, "metadata": metadata}

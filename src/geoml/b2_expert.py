"""Fixed, observation-only B2-expert/1 features preregistered in P27.

No fitting occurs here. The pure extractor sees calibrated PSDs, operator
plan masks and the P20 residual only. Labels/groups accompany the resulting
small feature table solely for downstream supervision and role checks.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from geosim.b2_protocol import BASE_ROLES, LABELS, role_for_group
from geosim.b2_scenarios import TEST_FAMILIES

FEATURE_VERSION = 'B2-expert/1'
_SUFFIXES = ('band_level_db', 'core_level_db', 'noncore_level_db',
             'steady_peak_db', 'transient_peak_db', 'temporal_cv',
             'spectral_flatness', 'centroid_std_mhz')
FEATURE_NAMES = tuple(f'{stream}_{name}' for stream in ('co', 'cross', 'residual')
                      for name in _SUFFIXES) + ('co_core_fraction', 'cross_core_fraction')
FEATURE_UNITS = ('dB', 'dB', 'dB', 'dB', 'dB', 'dimensionless',
                 'dimensionless', 'MHz') * 3 + ('dimensionless', 'dimensionless')
FREQUENCIES_MHZ = (np.arange(512, dtype=np.float64) - 256) * (96 / 512)
IN_BAND = np.abs(FREQUENCIES_MHZ) <= 18
MAX_GROUPS, MAX_SHARD_SAMPLES = 32, 256


def _array(values, name, shape):
    result = np.asarray(values)
    if (result.shape != shape or result.dtype.kind not in 'iuf'
            or not np.isfinite(result).all()):
        raise ValueError(f'{name} must be a finite real numeric array with shape {shape}')
    return result


def _power(db):
    result = np.power(10., np.asarray(db, dtype=np.float64) / 10.)
    if np.any(result <= 0) or not np.isfinite(result).all():
        raise ValueError('features require finite, strictly positive linear PSD')
    return result


def _stream_features(power, core, log_reference):
    average = float(power.mean())
    steady = power.mean(axis=0)
    temporal = power.mean(axis=1)
    normalized_temporal = temporal / average
    # Per-snapshot density normalization prevents large absolute PSD values
    # overflowing the centroid arithmetic without changing its definition.
    normalized = power / temporal[:, None]
    centroid = np.mean(normalized * FREQUENCIES_MHZ[IN_BAND][None, :], axis=1)
    log_average = np.log10(average)
    return (10*(log_average-log_reference),
            10*(np.log10(power[:, core].mean())-log_reference),
            10*(np.log10(power[:, ~core].mean())-log_reference),
            10*(np.log10(steady.max())-log_average),
            10*(np.log10(power.max())-log_average),
            float(normalized_temporal.std(ddof=0)),
            float(np.exp(np.mean(np.log(steady))-np.log(average))),
            float(centroid.std(ddof=0)))


def extract_features(spec, mask, residual):
    """Return finite float64 ``[N,26]`` features from exactly three observations.

    Regions, aggregation, feature order and units are fixed in P27. The
    reference is observed co-pol core mean PSD, shared by all streams. Core
    means mask > -3 dB, not actual carrier activity. Only one observation's
    linear-power arrays exist at a time; no fitted statistics or metadata.
    """
    raw = np.asarray(spec)
    if raw.ndim != 4 or not len(raw):
        raise ValueError('expert features require nonempty [N,2,128,512] spectra')
    n = len(raw)
    spec = _array(raw, 'spec', (n, 2, 128, 512))
    mask = _array(mask, 'mask', (n, 2, 512))
    residual = _array(residual, 'residual', (n, 128, 512))
    output = np.empty((n, len(FEATURE_NAMES)), dtype=np.float64)
    try:
        with np.errstate(over='raise', invalid='raise', divide='raise', under='ignore'):
            for row in range(n):
                cores = mask[row][:, IN_BAND] > -3
                if np.any(~cores.any(axis=1)) or np.any(cores.all(axis=1)):
                    raise ValueError('each operator plan needs in-band core and noncore bins')
                co = _power(spec[row, 0][:, IN_BAND])
                reference = float(co[:, cores[0]].mean())
                if reference <= 0 or not np.isfinite(reference):
                    raise ValueError('expert feature reference must be finite and positive')
                log_reference = np.log10(reference)
                output[row, :8] = _stream_features(co, cores[0], log_reference)
                output[row, 8:16] = _stream_features(
                    _power(spec[row, 1][:, IN_BAND]), cores[1], log_reference)
                output[row, 16:24] = _stream_features(
                    _power(residual[row][:, IN_BAND]), cores[0], log_reference)
                output[row, -2:] = cores.mean(axis=1)
    except FloatingPointError as error:
        raise ValueError('expert observations exceed the finite power/arithmetic range') from error
    if not np.isfinite(output).all():
        raise ValueError('expert feature rows must remain finite')
    return output


def _population(labels, groups, role, kind):
    labels, groups = np.asarray(labels), np.asarray(groups)
    if (labels.ndim != 1 or groups.shape != labels.shape or not len(labels)
            or labels.dtype.kind not in 'iu' or groups.dtype.kind not in 'iu'):
        raise ValueError('feature labels and groups must be nonempty matching integer vectors')
    populations = {'known': tuple(range(len(LABELS))), 'test': tuple(range(len(TEST_FAMILIES))),
                   'matched': (0, 3, 6)}
    if not isinstance(kind, str) or kind not in populations:
        raise ValueError('feature table kind must be known, test or matched')
    if ((kind == 'known' and role not in BASE_ROLES) or
            (kind == 'test' and role != 'test') or (kind == 'matched' and role != 'test-matched')):
        raise ValueError('feature table kind and role disagree')
    ids = np.unique(groups)
    if len(ids) > MAX_GROUPS:
        raise ValueError(f'feature table exceeds {MAX_GROUPS} scenario groups per role')
    if any(role_for_group(int(group)) != role for group in ids):
        raise ValueError('feature table contains groups outside its frozen role')
    if len(set(zip(groups.tolist(), labels.tolist()))) != len(labels):
        raise ValueError('duplicate feature scenario-group/label pair')
    expected = populations[kind]
    for group in ids:
        if sorted(labels[groups == group].tolist()) != list(expected):
            raise ValueError('feature table requires complete paired variants per scenario group')
    return labels.astype(np.int64, copy=True), groups.astype(np.int64, copy=True)


@dataclass(frozen=True)
class FeatureTable:
    """An immutable, validated small feature matrix with explicit population identity."""

    values: np.ndarray
    labels: np.ndarray
    groups: np.ndarray
    role: str
    kind: str
    identity: str
    feature_names: tuple = FEATURE_NAMES
    feature_version: str = FEATURE_VERSION

    def __post_init__(self):
        if (not isinstance(self.feature_version, str) or
                not isinstance(self.feature_names, (list, tuple)) or
                self.feature_version != FEATURE_VERSION or
                tuple(self.feature_names) != FEATURE_NAMES):
            raise ValueError('feature schema version/order differs from B2-expert/1')
        if not isinstance(self.identity, str) or not self.identity.strip():
            raise ValueError('feature table needs a nonempty artifact identity')
        labels, groups = _population(self.labels, self.groups, self.role, self.kind)
        values = _array(self.values, 'features', (len(labels), len(FEATURE_NAMES))).astype(np.float64, copy=True)
        for name, value in (('values', values), ('labels', labels), ('groups', groups)):
            value.setflags(write=False)
            object.__setattr__(self, name, value)
        object.__setattr__(self, 'feature_names', FEATURE_NAMES)

    def __len__(self):
        return len(self.labels)


def extract_source(source, identity):
    """Preallocate ``N*26`` numbers and fill from verified E1 shards individually.

    The caller opens/validates canonical P20 stages before this function. Each
    streamed shard is still reverified by E1. Table population checks and
    coverage checks reject spoofed roles, index drift or incomplete iteration.
    No record metadata is retained or inspected as a feature input.
    """
    if not getattr(source, 'has_residual', False):
        raise ValueError('expert features require the stored P20 residual')
    kind, role = source.kind, source.role
    key = 'family' if kind == 'test' else 'label'
    labels, groups = _population(source.index[key], source.index['seed'], role, kind)
    n = len(labels)
    if getattr(source, 'n_samples', n) != n:
        raise ValueError('source sample count differs from the feature index')
    values, covered = np.empty((n, len(FEATURE_NAMES)), dtype=np.float64), np.zeros(n, dtype=bool)
    for shard in source.shards():
        start = shard.get('offset')
        if isinstance(start, (bool, np.bool_)) or not isinstance(start, (int, np.integer)):
            raise ValueError('feature shard offset must be an integer')
        count = len(shard['seed'])
        stop = int(start) + count
        if not 1 <= count <= MAX_SHARD_SAMPLES or start < 0 or stop > n or covered[start:stop].any():
            raise ValueError('invalid feature shard coverage or bounded shard size')
        shard_labels, shard_groups = np.asarray(shard[key]), np.asarray(shard['seed'])
        if (shard_labels.dtype.kind not in 'iu' or shard_groups.dtype.kind not in 'iu' or
                not np.array_equal(shard_labels, labels[start:stop]) or
                not np.array_equal(shard_groups, groups[start:stop])):
            raise ValueError('streamed feature shard differs from its source index')
        values[start:stop] = extract_features(shard['spec'], shard['mask'], shard.get('residual'))
        covered[start:stop] = True
    if not covered.all():
        raise ValueError('incomplete feature shard coverage')
    return FeatureTable(values, labels, groups, role, kind, identity)

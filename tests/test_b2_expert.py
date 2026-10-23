"""P27 observable features and role-bound, small streaming feature tables."""
from dataclasses import replace
from types import SimpleNamespace
import inspect

import numpy as np
import pytest

from geoml import b2_expert as expert
from geosim.b2_protocol import ROLE_STARTS


def observation(n=1):
    spec = np.full((n, 2, 128, 512), -80., dtype=np.float64)
    mask = np.full((n, 2, 512), -60., dtype=np.float64)
    mask[:, :, 240:272] = 0.
    residual = np.full((n, 128, 512), -100., dtype=np.float64)
    return spec, mask, residual


def table(role='train', kind='known', n_groups=2):
    labels = np.tile([0, 3, 6] if kind == 'matched' else np.arange(5 if kind == 'test' else 8), n_groups)
    groups = np.repeat(np.arange(ROLE_STARTS[role], ROLE_STARTS[role] + n_groups), len(labels)//n_groups)
    values = np.arange(len(labels)*26, dtype=float).reshape(-1, 26)
    return expert.FeatureTable(values, labels, groups, role, kind, 'artifact-identity')


def test_exact_schema_pure_signature_uniform_density_features_and_units():
    assert list(inspect.signature(expert.extract_features).parameters) == ['spec', 'mask', 'residual']
    assert expert.FEATURE_VERSION == 'B2-expert/1'
    assert len(set(expert.FEATURE_NAMES)) == len(expert.FEATURE_UNITS) == 26
    assert expert.FEATURE_NAMES[:3] == ('co_band_level_db', 'co_core_level_db', 'co_noncore_level_db')
    assert expert.FEATURE_NAMES[-2:] == ('co_core_fraction', 'cross_core_fraction')
    x = expert.extract_features(*observation())
    assert x.dtype == np.float64 and x.shape == (1, 26)
    for offset, level in ((0, 0), (8, 0), (16, -20)):
        assert x[0, offset:offset+3] == pytest.approx([level]*3, abs=1e-12)
        assert x[0, offset+3:offset+8] == pytest.approx([0, 0, 0, 1, 0], abs=1e-12)
    assert x[0, -2:] == pytest.approx([32/193]*2)
    with pytest.raises(TypeError):
        expert.extract_features(*observation(), actual_ibo_db=0)


def test_reference_is_observed_co_core_and_all_streams_share_it():
    spec, mask, residual = observation()
    spec[:, 1] += 6
    spec[:, 0, :, 240:272] += 3
    x = expert.extract_features(spec, mask, residual)[0]
    assert x[1] == pytest.approx(0, abs=1e-12)
    assert x[2] == pytest.approx(-3)
    assert x[8] == pytest.approx(3)
    assert x[16] == pytest.approx(-23)
    shifted = expert.extract_features(spec+123, mask, residual+123)
    np.testing.assert_allclose(shifted, x[None], atol=3e-13, rtol=0)


def test_time_aggregation_is_linear_power_and_temporal_variation_is_population_sd():
    spec, mask, residual = observation()
    residual[:, 64:] += 10  # half frames power1, half power10; mean5.5, sd4.5.
    x = expert.extract_features(spec, mask, residual)[0]
    assert x[16] == pytest.approx(-20+10*np.log10(5.5))
    assert x[19] == pytest.approx(0, abs=1e-12)  # no spectral peak
    assert x[20] == pytest.approx(10*np.log10(10/5.5))
    assert x[21] == pytest.approx(4.5/5.5)


def test_moving_energy_centroid_and_spectral_flatness_are_observable():
    spec, mask, residual = observation()
    # A narrowband component at +-9MHz, alternated between independent snapshots.
    residual[:, :64, 208] += 20
    residual[:, 64:, 304] += 20
    x = expert.extract_features(spec, mask, residual)[0]
    expected_centroid_std = 9*99/(193+99)
    assert x[23] == pytest.approx(expected_centroid_std)
    assert 0 < x[22] < 1
    assert x[19] > 0 and x[20] > x[19]
    assert x[21] == pytest.approx(0, abs=1e-12)
    # Common gain and arbitrary out-of-band changes do not alter the feature evidence.
    spec[..., :100] += 9
    residual[..., 400:] += 12
    np.testing.assert_allclose(expert.extract_features(spec, mask, residual)[0], x, atol=1e-12)


@pytest.mark.parametrize('which,value', [('spec', np.nan), ('mask', np.inf), ('residual', -np.inf),
                                        ('spec', 4000.), ('residual', -4000.)])
def test_nonfinite_or_unrepresentable_observations_fail_closed(which, value):
    a = dict(zip(('spec', 'mask', 'residual'), observation()))
    a[which].flat[0] = value
    if np.isfinite(value):
        # Ensure unsupported powers occur in the fixed observation band/core.
        a[which][...] = value
    with pytest.raises(ValueError):
        expert.extract_features(**a)


@pytest.mark.parametrize('mutation', ['empty', 'wrong_grid', 'no_residual', 'no_core', 'no_noncore', 'complex'])
def test_missing_regions_and_incompatible_shapes_rejected(mutation):
    spec, mask, residual = observation()
    if mutation == 'empty': spec, mask, residual = spec[:0], mask[:0], residual[:0]
    elif mutation == 'wrong_grid': spec = spec[:, :, :64]
    elif mutation == 'no_residual': residual = None
    elif mutation == 'no_core': mask[:, 1] = -60
    elif mutation == 'no_noncore': mask[:, 0] = 0
    elif mutation == 'complex': spec = spec.astype(complex)
    with pytest.raises(ValueError):
        expert.extract_features(spec, mask, residual)


def test_feature_table_is_role_bound_complete_and_keeps_owned_immutable_values():
    t = table()
    assert t.feature_names == expert.FEATURE_NAMES and t.feature_version == expert.FEATURE_VERSION
    assert t.values.dtype == np.float64 and t.labels.dtype == t.groups.dtype == np.int64
    with pytest.raises(ValueError): t.values[0, 0] = 1
    original = np.array(t.values)
    independent = expert.FeatureTable(original, t.labels, t.groups, t.role, t.kind, t.identity)
    original[0, 0] = -999
    assert independent.values[0, 0] != -999
    with pytest.raises(ValueError, match='role'):
        replace(t, role='test')
    with pytest.raises(ValueError, match='paired'):
        replace(t, values=t.values[1:], labels=t.labels[1:], groups=t.groups[1:])
    with pytest.raises(ValueError, match='duplicate'):
        replace(t, labels=np.r_[0, t.labels[0:-1]], groups=np.r_[t.groups[0], t.groups[0:-1]])
    with pytest.raises(ValueError, match='schema'):
        replace(t, feature_names=tuple(reversed(expert.FEATURE_NAMES)))
    with pytest.raises(ValueError, match='schema'):
        replace(t, feature_version='oracle-features/1')
    with pytest.raises(ValueError, match='schema'):
        replace(t, feature_names=None)
    with pytest.raises(ValueError, match='kind'):
        replace(t, kind=['known'])


@pytest.mark.parametrize('mutation', ['float_labels', 'bool_groups', 'nonfinite_features', 'bad_label',
                                     'blank_identity', 'empty', 'too_many_groups'])
def test_feature_table_adversarial_inputs(mutation):
    t = table()
    kw = dict(values=t.values, labels=t.labels, groups=t.groups, role=t.role, kind=t.kind, identity=t.identity)
    if mutation == 'float_labels': kw['labels'] = t.labels.astype(float)
    elif mutation == 'bool_groups': kw['groups'] = t.groups.astype(bool)
    elif mutation == 'nonfinite_features': kw['values'] = np.full_like(t.values, np.nan)
    elif mutation == 'bad_label': kw['labels'] = t.labels+1
    elif mutation == 'blank_identity': kw['identity'] = ' '
    elif mutation == 'empty': kw.update(values=t.values[:0], labels=t.labels[:0], groups=t.groups[:0])
    elif mutation == 'too_many_groups':
        labels=np.tile(np.arange(8), 33)
        kw.update(values=np.zeros((264,26)), labels=labels, groups=np.repeat(np.arange(3000000,3000033),8))
    with pytest.raises(ValueError): expert.FeatureTable(**kw)


def test_test_only_and_matched_tables_have_distinct_complete_populations():
    unknown = table('test', 'test')
    matched = table('test-matched', 'matched')
    assert set(unknown.labels) == set(range(5))
    assert set(matched.labels) == {0,3,6}
    with pytest.raises(ValueError): replace(unknown, role='val-calib')
    with pytest.raises(ValueError): replace(matched, kind='known')


def test_streaming_preallocates_only_features_and_rejects_drift_or_missing_residual(monkeypatch):
    t = table('test')
    spec, mask, residual = observation(len(t.labels))
    part = {'spec':spec,'mask':mask,'residual':residual,'seed':t.groups,'label':t.labels}
    def shards():
        for start in (0,8):
            yield {**{k:v[start:start+8] for k,v in part.items()},'offset':start}
    source = SimpleNamespace(kind='known',role='test',has_residual=True,index={'label':t.labels,'seed':t.groups},
                             n_samples=len(t.labels),shards=shards)
    # An implementation must not concatenate a role's spectra just to get features.
    monkeypatch.setattr(np, 'concatenate', lambda *_a, **_k: pytest.fail('whole-role concatenate forbidden'))
    out = expert.extract_source(source, 'same-data')
    assert out.values.shape == (16,26) and out.identity == 'same-data'
    assert out.labels.tolist() == t.labels.tolist()
    source.has_residual = False
    with pytest.raises(ValueError, match='residual'): expert.extract_source(source,'same-data')
    source.has_residual = True
    part['label'] = t.labels.copy(); part['label'][0] = 1
    with pytest.raises(ValueError, match='index'): expert.extract_source(source,'same-data')


def test_streaming_refuses_missing_duplicate_and_oversize_shards():
    t = table()
    spec,mask,residual = observation(len(t.labels))
    shard = {'spec':spec,'mask':mask,'residual':residual,'seed':t.groups,'label':t.labels,'offset':0}
    source = SimpleNamespace(kind='known',role='train',has_residual=True,index={'label':t.labels,'seed':t.groups},
                             n_samples=len(t.labels),shards=lambda:iter([shard]))
    source.shards = lambda:iter([])
    with pytest.raises(ValueError, match='coverage'): expert.extract_source(source,'data')
    source.shards = lambda:iter([shard,shard])
    with pytest.raises(ValueError, match='coverage'): expert.extract_source(source,'data')
    source.shards = lambda:iter([{**shard,'offset':True}])
    with pytest.raises(ValueError, match='offset'): expert.extract_source(source,'data')

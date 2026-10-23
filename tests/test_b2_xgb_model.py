"""P27 bounded CPU model, role separation and checkpoint integrity checks."""
import hashlib
import json

import numpy as np
import pytest

from geoml.artifacts import fingerprint
from geoml.b2_expert import FEATURE_NAMES, FeatureTable
from geoml import b2_xgb_model as model


STARTS = {'train': 3000000, 'val-select': 3100000, 'val-calib': 3150000, 'test': 3200000}


def table(role='train', *, offset=0., identity='known-artifact', seed=0):
    rng = np.random.default_rng(seed)
    labels = np.tile(np.arange(8), 2)
    values = rng.normal(0, .01, (16, 26)) + labels[:, None] + offset
    values[:, -1] = 3.
    return FeatureTable(values, labels, np.repeat(np.arange(STARTS[role], STARTS[role]+2), 8),
                        role, 'known', identity)


def fit(monkeypatch=None):
    return model.fit_xgb(table(), table('val-select', seed=1),
                         config=model.XGBConfig(), provenance={'data': 'known-artifact', 'source': 'fixture'})


def rehash_metadata(path):
    data = json.loads(path.read_text())
    data['metadata_fingerprint'] = fingerprint({k:v for k,v in data.items() if k != 'metadata_fingerprint'})
    path.write_text(json.dumps(data, allow_nan=False))


def test_train_only_statistics_and_training_matrix_selection_only_validation(monkeypatch):
    train, selection = table(), table('val-select', offset=100.)
    calls = []
    original = model.xgb.train
    def observed(params, dtrain, **kwargs):
        calls.append(dtrain.get_label())
        assert not kwargs.get('evals')
        assert params['device'] == 'cpu' and params['nthread'] == 1
        assert kwargs['num_boost_round'] == 16
        return original(params, dtrain, **kwargs)
    monkeypatch.setattr(model.xgb, 'train', observed)
    fitted = model.fit_xgb(train, selection, config=model.XGBConfig(), provenance={'source':'fixture'})
    assert len(calls) == 1 and np.array_equal(calls[0], train.labels)
    assert np.array_equal(fitted.normalizer_mean, train.values.mean(0))
    expected = train.values.std(0)
    expected[expected == 0] = 1
    assert np.array_equal(fitted.normalizer_scale, expected)
    assert fitted.normalizer_scale[-1] == 1
    assert [entry['rounds'] for entry in fitted.selection_history] == [8, 16]
    assert fitted.populations['train']['role'] == 'train'
    assert fitted.populations['selection']['role'] == 'val-select'


def test_fixed_tie_rule_chooses_eight_rounds_and_probabilities_are_normalized(monkeypatch):
    monkeypatch.setattr(model, 'macro_f1', lambda *_args: .25)
    fitted = fit()
    assert fitted.selected_rounds == fitted.booster.num_boosted_rounds() == 8
    probability = fitted.predict_proba(table('test'))
    assert probability.shape == (16, 8)
    assert np.all((probability >= 0) & (probability <= 1))
    assert np.allclose(probability.sum(1), 1, atol=1e-6)


def test_deterministic_model_replay_and_native_load_parity(tmp_path):
    first, second = fit(), fit()
    assert first.scorer_identity == second.scorer_identity
    assert first.selection_history == second.selection_history
    assert np.array_equal(first.normalizer_mean, second.normalizer_mean)
    assert np.array_equal(first.predict_proba(table('test')), second.predict_proba(table('test')))
    out = tmp_path/'model'
    model.save_model(first, out)
    restored = model.load_model(out, expected_provenance=first.provenance, expected_config=first.config)
    assert restored.scorer_identity == first.scorer_identity
    assert np.array_equal(restored.predict_proba(table('test')), first.predict_proba(table('test')))
    json.loads((out/'metadata.json').read_text(), parse_constant=lambda s: pytest.fail(s))
    with pytest.raises(ValueError, match='nonempty'):
        model.save_model(second, out)


@pytest.mark.parametrize('key,value', [('seed',1),('nthread',2),('max_rounds',17),('candidates',(4,8)),
    ('max_depth',3),('eta',.1),('max_bin',128),('subsample',.9),('reg_lambda',0),('seed',False)])
def test_fixed_config_refuses_undocumented_budget_or_boolean_scalars(key,value):
    with pytest.raises(ValueError, match='P27|fixed'):
        model.XGBConfig(**{key:value})


def test_config_file_and_runtime_version_fail_closed(tmp_path, monkeypatch):
    path = tmp_path/'config.json'
    path.write_text(json.dumps(model.XGBConfig().resolved()))
    assert model.XGBConfig.from_file(path) == model.XGBConfig()
    path.write_text('{"seed":0,"seed":0}')
    with pytest.raises(ValueError, match='duplicate'):
        model.XGBConfig.from_file(path)
    monkeypatch.setattr(model.xgb, '__version__', '99.0.0')
    with pytest.raises(ValueError, match='3.4.1'):
        fit()


def test_role_identity_and_mutated_group_isolation(monkeypatch):
    monkeypatch.setattr(model.xgb, 'train', lambda *_a, **_k: pytest.fail('invalid roles must not fit'))
    with pytest.raises(ValueError, match='train'):
        model.fit_xgb(table('test'), table('val-select'), config=model.XGBConfig(), provenance={'p':1})
    with pytest.raises(ValueError, match='val-select'):
        model.fit_xgb(table(), table('val-calib'), config=model.XGBConfig(), provenance={'p':1})
    with pytest.raises(ValueError, match='identity'):
        model.fit_xgb(table(), table('val-select', identity='foreign'), config=model.XGBConfig(), provenance={'p':1})
    selection = table('val-select')
    object.__setattr__(selection, 'groups', table().groups)
    with pytest.raises(ValueError):
        model.fit_xgb(table(), selection, config=model.XGBConfig(), provenance={'p':1})


def test_inference_revalidates_feature_order_and_values():
    fitted = fit()
    malformed = table('test')
    object.__setattr__(malformed, 'feature_names', FEATURE_NAMES[::-1])
    with pytest.raises(ValueError, match='feature|schema'):
        fitted.predict_proba(malformed)
    malformed = table('test')
    changed = malformed.values.copy(); changed[0,0] = np.nan
    object.__setattr__(malformed, 'values', changed)
    with pytest.raises(ValueError):
        fitted.predict_proba(malformed)


def test_checkpoint_rejects_foreign_partial_native_and_metadata_corruption(tmp_path):
    fitted = fit()
    out = tmp_path/'good'; model.save_model(fitted, out)
    with pytest.raises(ValueError, match='provenance'):
        model.load_model(out, expected_provenance={'foreign':1}, expected_config=fitted.config)
    partial = tmp_path/'partial'; partial.mkdir()
    (partial/'model.ubj').write_bytes(b'invalid')
    with pytest.raises(ValueError):
        model.load_model(partial, expected_provenance=fitted.provenance, expected_config=fitted.config)
    native = out/'model.ubj'; good = native.read_bytes()
    native.write_bytes(good+b'corrupt')
    with pytest.raises(ValueError, match='checksum'):
        model.load_model(out, expected_provenance=fitted.provenance, expected_config=fitted.config)
    native.write_bytes(good)
    metadata = out/'metadata.json'; good_metadata = metadata.read_text()
    data = json.loads(good_metadata); data['normalizer_mean'][0] += 1
    metadata.write_text(json.dumps(data)); rehash_metadata(metadata)
    with pytest.raises(ValueError, match='binding'):
        model.load_model(out, expected_provenance=fitted.provenance, expected_config=fitted.config)
    metadata.write_text(good_metadata)
    data = json.loads(good_metadata); data['feature_names'] = list(FEATURE_NAMES[::-1])
    metadata.write_text(json.dumps(data)); rehash_metadata(metadata)
    with pytest.raises(ValueError, match='feature|schema'):
        model.load_model(out, expected_provenance=fitted.provenance, expected_config=fitted.config)
    metadata.write_text('{"bad":NaN}')
    with pytest.raises(ValueError):
        model.load_model(out, expected_provenance=fitted.provenance, expected_config=fitted.config)


def test_rehashed_native_model_with_wrong_round_count_is_rejected(tmp_path):
    fitted = fit()
    out = tmp_path/'model'; model.save_model(fitted, out)
    (out/'model.ubj').write_bytes(bytes(fitted.booster[:2].save_raw(raw_format='ubj')))
    p = out/'metadata.json'; data = json.loads(p.read_text())
    data['model_sha256'] = hashlib.sha256((out/'model.ubj').read_bytes()).hexdigest()
    data['scorer_identity'] = fingerprint({'binding':data['binding'], 'model_sha256':data['model_sha256']})
    p.write_text(json.dumps(data)); rehash_metadata(p)
    with pytest.raises(ValueError, match='round|native'):
        model.load_model(out, expected_provenance=fitted.provenance, expected_config=fitted.config)


@pytest.mark.parametrize('field,value', [('normalizer_mean',True),('normalizer_scale',0.)])
def test_rehashed_invalid_normalizer_is_rejected(tmp_path,field,value):
    fitted = fit(); out = tmp_path/'model'; model.save_model(fitted,out)
    path = out/'metadata.json'; data = json.loads(path.read_text()); data[field][0] = value
    path.write_text(json.dumps(data)); rehash_metadata(path)
    with pytest.raises(ValueError,match=field):
        model.load_model(out,expected_provenance=fitted.provenance,expected_config=fitted.config)


def test_in_memory_fitted_state_tamper_is_rejected():
    fitted = fit()
    changed = fitted.normalizer_mean.copy(); changed[0] += 1
    object.__setattr__(fitted,'normalizer_mean',changed)
    with pytest.raises(ValueError,match='binding'):
        fitted.predict_proba(table('test'))

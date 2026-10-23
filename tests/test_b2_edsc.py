"""Bounded E3a harness isolation, provenance and real artifact-reader tests."""
import json
from copy import deepcopy

import numpy as np
import pytest

from geoml import b2_edsc as runner
from geoml.b2_stream import B2Source
from geosim.b2_protocol import LABELS
from geosim.cancellation import CancellationConfig
from test_b2_experiment import _split
from test_b2_artifacts import feature_generator, generator  # noqa: F401


@pytest.fixture
def sources(monkeypatch):
    parts = {r: _split(r, 2, i) for i, r in enumerate(runner.ROLES)}
    # Canonical grid; the legacy fast ML fixture uses smaller dimensions.
    for part in parts.values():
        n = len(part['seed'])
        part['spec'] = np.full((n, 2, 128, 512), -80., np.float16)
        part['mask'] = np.full((n, 2, 512), -60., np.float16)
        part['mask'][:, :, 240:272] = 0
        part['residual'] = np.full((n, 128, 512), -100., np.float16)
    manifest = {'protocol': 'B2-feat/1', 'labels': list(LABELS),
                'benchmark_complete': False, 'cancellation': CancellationConfig().to_dict()}
    monkeypatch.setattr(runner, '_preflight', lambda *_a, **_k: None)
    monkeypatch.setattr(runner, 'open_b2_known', lambda _: (manifest, 'f'*64,
        {r: B2Source.from_arrays(p, role=r) for r, p in parts.items()}))
    return parts, manifest


def test_no_train_select_scoring_calibration_precedes_test_and_strict_reuse(sources, monkeypatch, tmp_path):
    events = []
    original = runner.score_source
    def score(source, **kw):
        events.append(source.role)
        assert source.role not in ('train', 'val-select')
        if source.role == 'test':
            assert (tmp_path/'calibration.json').is_file()
        return original(source, **kw)
    monkeypatch.setattr(runner, 'score_source', score)
    result = runner.run_edsc('unused', tmp_path, smoke=True, bootstrap=5, with_cfar=True)
    assert events == ['val-calib', 'test']
    assert result['benchmark_complete'] is False
    assert result['sample_counts']['test'] == 16
    assert set(result['methods']) == {'edsc', 'cfar_plan', 'cfar_blind'}
    json.loads((tmp_path/'results.json').read_text(), parse_constant=lambda s: pytest.fail(s))
    runner.run_edsc('unused', tmp_path, smoke=True, bootstrap=5, with_cfar=True, reuse=True)
    with pytest.raises(ValueError, match='nonempty'):
        runner.run_edsc('unused', tmp_path, smoke=True, bootstrap=5, with_cfar=True)
    with pytest.raises(ValueError, match='provenance'):
        runner.run_edsc('unused', tmp_path, smoke=True, bootstrap=6, with_cfar=True, reuse=True)
    (tmp_path/'calibration.json').write_text('{}')
    with pytest.raises(ValueError, match='checksum'):
        runner.run_edsc('unused', tmp_path, smoke=True, bootstrap=5, with_cfar=True, reuse=True)


def test_stage_residual_role_and_pair_integrity(sources, tmp_path):
    parts, manifest = sources
    manifest['protocol'] = 'B2-features/1'
    with pytest.raises(ValueError, match='B2-feat/1'):
        runner.run_edsc('unused', tmp_path, bootstrap=5)
    manifest['protocol'] = 'B2-feat/1'
    del parts['val-calib']['residual']
    with pytest.raises(ValueError, match='residual'):
        runner.run_edsc('unused', tmp_path, bootstrap=5)
    parts['val-calib']['residual'] = np.full((16,128,512), -100., np.float16)
    manifest['cancellation']['iterations'] = 2
    with pytest.raises(ValueError, match='obs-cancel/1'):
        runner.run_edsc('unused', tmp_path, bootstrap=5)
    manifest['cancellation'] = CancellationConfig().to_dict()
    parts['train'] = {k:v[1:] for k,v in parts['train'].items()}
    with pytest.raises(ValueError, match='paired'):
        runner.run_edsc('unused', tmp_path, bootstrap=5)


def test_preflight_caps_before_loading_arrays_and_empty_output_refusal(tmp_path):
    m = {'protocol':'B2-feat/1','roles':{'train':{'scenario_seeds':list(range(33)),
         'shards':[{'n_samples':8}]} }}
    (tmp_path/'manifest.json').write_text(json.dumps(m))
    with pytest.raises(ValueError, match='cap'):
        runner._preflight(tmp_path, 'B2-feat/1', 32)
    m['roles']['train']['scenario_seeds'] = [3000000]
    m['roles']['train']['shards'][0]['n_samples'] = 257
    (tmp_path/'manifest.json').write_text(json.dumps(m))
    with pytest.raises(ValueError, match='shard'):
        runner._preflight(tmp_path, 'B2-feat/1', 32)
    (tmp_path/'manifest.json').write_text('{"protocol":NaN}')
    with pytest.raises(ValueError):
        runner._preflight(tmp_path, 'B2-feat/1', 32)


def test_streamed_scores_ignore_metadata_and_cross_polarization(sources):
    parts, _ = sources
    part = parts['test']
    a = runner.score_source(B2Source.from_arrays(part, role='test'))
    altered = deepcopy(part)
    altered['meta'] = [{'event':{'kind':'oracle'},'actual_ibo_db':-999} for _ in part['meta']]
    altered['spec'][:, 1] += 50
    b = runner.score_source(B2Source.from_arrays(altered, role='test'))
    assert np.array_equal(a['edsc'], b['edsc'])


def test_operator_plan_mismatch_refused_and_incomplete_output_preserved(sources, tmp_path):
    parts, _ = sources
    parts['test']['mask'][1, 0, 240] = -60
    with pytest.raises(ValueError, match='operator plan mismatch'):
        runner.score_source(B2Source.from_arrays(parts['test'], role='test'))
    (tmp_path/'foreign.txt').write_text('preserve')
    with pytest.raises(ValueError, match='provenance'):
        runner.run_edsc('unused', tmp_path, reuse=True, bootstrap=5)
    assert (tmp_path/'foreign.txt').read_text() == 'preserve'


def test_bound_artifact_provenance_and_missing_residual_fail_before_scoring(sources, monkeypatch):
    parts, _ = sources
    source = B2Source.from_arrays(parts['test'], role='test')
    manifest = {'request':{'known':{'known_data_fingerprint':'wrong'}},
                'config':{}, 'cancellation':CancellationConfig().to_dict(), 'benchmark_complete':False}
    monkeypatch.setattr(runner, 'open_b2_test', lambda _: (manifest, 'test', source))
    known = {'config':{}, 'cancellation':CancellationConfig().to_dict(),
             'protocol':'B2-feat/1', 'request_fingerprint':'request',
             'roles':{'test':{'scenario_seeds':[3200000,3200001]}}, 'calibration':{'identity':'receiver'}}
    with pytest.raises(ValueError, match='provenance'):
        runner._bound('unused', 'test', known, 'expected', 2)
    manifest['request']['known'] = {'known_protocol':'B2-feat/1','known_data_fingerprint':'expected',
        'known_request_fingerprint':'request', 'known_test_groups':[3200000,3200001],
        'known_calibration':{'identity':'receiver'}}
    manifest['calibration'] = {'identity':'foreign'}
    with pytest.raises(ValueError, match='provenance'):
        runner._bound('unused', 'test', known, 'expected', 2)
    manifest['calibration'] = known['calibration']
    for field in ('known_calibration','known_request_fingerprint','known_protocol','known_test_groups'):
        original = manifest['request']['known'][field]
        manifest['request']['known'][field] = 'foreign'
        with pytest.raises(ValueError, match='provenance'):
            runner._bound('unused', 'test', known, 'expected', 2)
        manifest['request']['known'][field] = original
    source.has_residual = False
    with pytest.raises(ValueError, match='residual'):
        runner._bound('unused', 'test', known, 'expected', 2)


def test_disk_writer_validator_stream_smoke_and_corruption(feature_generator, tmp_path):
    from geosim.b2_dataset import generate_b2_dataset
    from geosim.b2_protocol import B2Config
    data, out = tmp_path/'data', tmp_path/'run'
    generate_b2_dataset(data, B2Config(), cancellation=CancellationConfig(),
                        limit_groups=2, groups_per_shard=1)
    result = runner.run_edsc(data, out, smoke=True, bootstrap=5)
    assert result['sample_counts']['val-calib'] == 16
    part = next((data/'test').glob('part-*.npz'))
    with part.open('ab') as stream:
        stream.write(b'corrupt')
    with pytest.raises(ValueError):
        runner.run_edsc(data, tmp_path/'corrupt', smoke=True, bootstrap=5)

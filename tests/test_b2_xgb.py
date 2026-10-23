"""Bounded E3b runner isolation/provenance integration; fixtures are not RF evidence."""
import json
import numpy as np
import pytest

from geoml import b2_xgb as runner
from geoml.b2_stream import B2Source
from geosim.b2_protocol import LABELS
from geosim.cancellation import CancellationConfig
from test_b2_experiment import _split
from test_b2_artifacts import feature_generator, generator  # noqa: F401


@pytest.fixture
def sources(monkeypatch):
    parts = {r:_split(r,2,i) for i,r in enumerate(runner.ROLES)}
    for part in parts.values():
        n=len(part['seed'])
        part['spec']=np.full((n,2,128,512),-80.,np.float16)
        part['mask']=np.full((n,2,512),-60.,np.float16)
        part['mask'][:,:,240:272]=0
        part['residual']=np.full((n,128,512),-100.,np.float16)
    manifest={'protocol':'B2-feat/1','labels':list(LABELS),'benchmark_complete':False,
              'cancellation':CancellationConfig().to_dict()}
    monkeypatch.setattr(runner,'_preflight',lambda *_a,**_k:None)
    monkeypatch.setattr(runner,'open_b2_known',lambda _:(manifest,'f'*64,
        {r:B2Source.from_arrays(p,role=r) for r,p in parts.items()}))
    return parts,manifest


def test_pipeline_fit_roles_frozen_calibration_before_test_reuse_and_strict_json(sources,tmp_path,monkeypatch):
    events=[]
    fit,extract=runner.fit_xgb,runner.extract_source
    def checked_fit(train,selection,**kw):
        assert train.role=='train' and selection.role=='val-select'
        events.append('fit')
        return fit(train,selection,**kw)
    def checked_extract(source,identity):
        events.append(source.role)
        if source.role=='test': assert (tmp_path/'calibration.json').is_file()
        return extract(source,identity)
    monkeypatch.setattr(runner,'fit_xgb',checked_fit)
    monkeypatch.setattr(runner,'extract_source',checked_extract)
    result=runner.run_xgb('unused',tmp_path,smoke=True,bootstrap=5,with_baselines=True)
    assert events==['train','val-select','fit','val-calib','test']
    assert result['benchmark_complete'] is False
    assert set(result['binary'])=={'xgboost','edsc','cfar_plan','cfar_blind'}
    assert result['calibration']['xgboost']['n_calibration']==2
    assert result['binary']['xgboost']['known']['clean_false_alarm']['count']==0
    assert result['binary']['edsc']['unsupported']['oscr_auc'] is None
    assert result['classifier']['known']['n']==16
    json.loads((tmp_path/'results.json').read_text(),parse_constant=lambda x:pytest.fail(x))
    monkeypatch.setattr(runner,'fit_xgb',lambda *_a,**_k:pytest.fail('reuse must not refit'))
    runner.run_xgb('unused',tmp_path,smoke=True,bootstrap=5,with_baselines=True,reuse=True)
    with pytest.raises(ValueError,match='nonempty'):
        runner.run_xgb('unused',tmp_path,smoke=True,bootstrap=5)
    with pytest.raises(ValueError,match='provenance'):
        runner.run_xgb('unused',tmp_path,smoke=True,bootstrap=6,with_baselines=True,reuse=True)
    (tmp_path/'model'/'model.ubj').write_bytes(b'corrupt')
    with pytest.raises(ValueError,match='checksum'):
        runner.run_xgb('unused',tmp_path,smoke=True,bootstrap=5,with_baselines=True,reuse=True)


def test_stage_missing_residual_and_incomplete_population_refused(sources,tmp_path):
    parts,manifest=sources
    manifest['protocol']='B2-features/1'
    with pytest.raises(ValueError,match='B2-feat/1'):
        runner.run_xgb('unused',tmp_path)
    manifest['protocol']='B2-feat/1'
    del parts['val-calib']['residual']
    with pytest.raises(ValueError,match='residual'):
        runner.run_xgb('unused',tmp_path)


def test_reuse_crosschecks_fitted_populations_against_current_verified_sources(sources,tmp_path,monkeypatch):
    runner.run_xgb('unused',tmp_path,smoke=True,bootstrap=5)
    original=runner.load_model
    def foreign_population(*args,**kwargs):
        fitted=original(*args,**kwargs)
        fitted.populations['train']['sample_ids'][0][0] += 1
        return fitted
    monkeypatch.setattr(runner,'load_model',foreign_population)
    monkeypatch.setattr(runner,'calibrate_clean',lambda *_a,**_k:pytest.fail('foreign populations must fail before calibration'))
    with pytest.raises(ValueError,match='populations'):
        runner.run_xgb('unused',tmp_path,smoke=True,bootstrap=5,reuse=True)


def test_disk_stream_model_calibration_and_corrupt_artifact(feature_generator,tmp_path):
    from geosim.b2_dataset import generate_b2_dataset
    root=tmp_path/'data'
    generate_b2_dataset(root,limit_groups=2,groups_per_shard=1,cancellation=CancellationConfig())
    result=runner.run_xgb(root,tmp_path/'out',smoke=True,bootstrap=5)
    assert result['sample_counts']['train']==16
    assert result['model']['selected_rounds'] in (8,16)
    shard=next((root/'test').glob('part-*.npz'))
    with shard.open('ab') as f:f.write(b'corrupt')
    with pytest.raises(ValueError):runner.run_xgb(root,tmp_path/'bad',smoke=True,bootstrap=5)

"""Fixed P27 CPU XGBoost fitting and provenance-bound native checkpoints.

Only train rows fit normalizers/trees. Val-select chooses between the two
preregistered prefixes; calibration and final test observations never fit here.
"""
from __future__ import annotations

import hashlib
import importlib.metadata
import json
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import xgboost as xgb

from geosim.b2_protocol import LABELS
from .artifacts import fingerprint
from .b2_expert import FEATURE_NAMES, FEATURE_UNITS, FEATURE_VERSION, FeatureTable
from .metrics import macro_f1

PROTOCOL = 'B2-XGB/1'
XGBOOST_VERSION = '3.4.1'
_BINDING_KEYS = ('protocol','feature_version','feature_names','feature_units','labels','config',
                 'dependency','provenance','normalizer_mean','normalizer_scale','selected_rounds',
                 'selection_history','populations')
_METADATA_KEYS = set(_BINDING_KEYS) | {'binding','model_sha256','scorer_identity','metadata_fingerprint'}


def _strict_json(text):
    def pairs(items):
        result = {}
        for key,value in items:
            if key in result:
                raise ValueError(f'duplicate JSON key {key}')
            result[key] = value
        return result
    def invalid(value):
        raise ValueError(f'nonfinite JSON number {value}')
    return json.loads(text, object_pairs_hook=pairs, parse_constant=invalid)


def _json_copy(value):
    return _strict_json(json.dumps(value, allow_nan=False))


@dataclass(frozen=True)
class XGBConfig:
    """Exactly the preregistered P27 budget; this is not a tuning interface."""
    seed: int = 0
    nthread: int = 1
    max_rounds: int = 16
    candidates: tuple = (8,16)
    max_depth: int = 2
    eta: float = .3
    max_bin: int = 64
    min_child_weight: float = 1.
    reg_lambda: float = 1.
    reg_alpha: float = 0.
    subsample: float = 1.
    colsample_bytree: float = 1.

    def __post_init__(self):
        fixed = {'seed':0,'nthread':1,'max_rounds':16,'max_depth':2,'eta':.3,'max_bin':64,
                 'min_child_weight':1.,'reg_lambda':1.,'reg_alpha':0.,'subsample':1.,'colsample_bytree':1.}
        for name,expected in fixed.items():
            value = getattr(self,name)
            if (isinstance(value,(bool,np.bool_)) or not isinstance(value,(int,float)) or
                    not np.isfinite(value) or value != expected or
                    (name in ('seed','nthread','max_rounds','max_depth','max_bin') and type(value) is not int)):
                raise ValueError(f'P27 fixed configuration requires {name}={expected}')
        if (not isinstance(self.candidates,(tuple,list)) or len(self.candidates) != 2 or
                any(type(n) is not int for n in self.candidates) or tuple(self.candidates) != (8,16)):
            raise ValueError('P27 fixed candidates are exactly8 and16 rounds')
        object.__setattr__(self,'candidates',tuple(self.candidates))

    def resolved(self):
        data = asdict(self)
        data['candidates'] = list(self.candidates)
        return data

    @classmethod
    def from_file(cls,path):
        data = _strict_json(Path(path).read_text())
        if not isinstance(data,dict):
            raise ValueError('P27 fixed configuration must be a JSON object')
        try:
            return cls(**data)
        except TypeError as exc:
            raise ValueError('invalid P27 fixed configuration fields') from exc

    def parameters(self):
        return {'seed':self.seed,'nthread':self.nthread,'device':'cpu','tree_method':'hist',
                'objective':'multi:softprob','num_class':len(LABELS),'max_depth':self.max_depth,
                'eta':self.eta,'max_bin':self.max_bin,'min_child_weight':self.min_child_weight,
                'lambda':self.reg_lambda,'alpha':self.reg_alpha,'subsample':self.subsample,
                'colsample_bytree':self.colsample_bytree,'verbosity':0,'validate_parameters':True}


def _dependency():
    try:
        installed = importlib.metadata.version('xgboost-cpu')
    except importlib.metadata.PackageNotFoundError as exc:
        raise ValueError(f'P27 requires xgboost-cpu=={XGBOOST_VERSION}') from exc
    if xgb.__version__ != XGBOOST_VERSION or installed != XGBOOST_VERSION:
        raise ValueError(f'P27 requires xgboost-cpu=={XGBOOST_VERSION} at runtime')
    return {'distribution':'xgboost-cpu','version':installed,'numpy_version':np.__version__}


def _table(table, *, role=None):
    if not isinstance(table,FeatureTable):
        raise ValueError('model inputs require a versioned FeatureTable')
    # Validate again: a caller may have mutated arrays after constructing a table.
    checked = FeatureTable(table.values,table.labels,table.groups,table.role,table.kind,table.identity,
                           feature_names=table.feature_names,feature_version=table.feature_version)
    if role is not None and (checked.kind != 'known' or checked.role != role):
        raise ValueError(f'XGBoost requires known {role} observations for this operation')
    return checked


def _population(table):
    return {'kind':table.kind,'role':table.role,'data_identity':table.identity,
            'n_samples':len(table.values),'n_groups':len(np.unique(table.groups)),
            'sample_ids':np.column_stack((table.groups,table.labels)).tolist()}


def _standardize(values,mean,scale):
    try:
        with np.errstate(over='raise',invalid='raise',divide='raise',under='ignore'):
            result = ((np.asarray(values,dtype=np.float64)-mean)/scale).astype(np.float32)
    except FloatingPointError as exc:
        raise ValueError('features exceed finite supported normalization range') from exc
    if not np.isfinite(result).all():
        raise ValueError('standardized features must be finite')
    return result


def _matrix(values,labels=None):
    return xgb.DMatrix(values,label=labels,feature_names=list(FEATURE_NAMES),nthread=1)


def _probabilities(booster,data,**kwargs):
    result = np.asarray(booster.predict(data,strict_shape=True,**kwargs),dtype=np.float64)
    if (result.ndim != 2 or result.shape[1] != len(LABELS) or not np.isfinite(result).all() or
            np.any(result < 0) or np.any(result > 1) or not np.allclose(result.sum(1),1,rtol=0,atol=2e-6)):
        raise ValueError('native classifier must output finite normalized Nx8 probabilities')
    return result


def _binding(data):
    return fingerprint({key:data[key] for key in _BINDING_KEYS})


def _native_bytes(booster):
    return bytes(booster.save_raw(raw_format='ubj'))


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _metadata_fingerprint(data):
    return fingerprint({key:value for key,value in data.items() if key != 'metadata_fingerprint'})


def _normalizer_vector(values,name,*,positive=False):
    if (not isinstance(values,list) or len(values) != len(FEATURE_NAMES) or
            any(isinstance(v,bool) or not isinstance(v,(int,float)) for v in values)):
        raise ValueError(f'invalid {name} metadata')
    vector = np.asarray(values,dtype=np.float64)
    if not np.isfinite(vector).all() or (positive and np.any(vector <= 0)):
        raise ValueError(f'invalid {name} metadata')
    return vector


def _validate_metadata(data,*,expected_provenance,expected_config):
    if not isinstance(data,dict) or set(data) != _METADATA_KEYS:
        raise ValueError('incomplete or unsupported XGBoost metadata fields')
    if data['metadata_fingerprint'] != _metadata_fingerprint(data):
        raise ValueError('XGBoost metadata checksum mismatch')
    if (data['protocol'] != PROTOCOL or data['feature_version'] != FEATURE_VERSION or
            data['feature_names'] != list(FEATURE_NAMES) or data['feature_units'] != list(FEATURE_UNITS) or
            data['labels'] != list(LABELS)):
        raise ValueError('incompatible feature schema/order or class order')
    if not isinstance(expected_config,XGBConfig) or data['config'] != expected_config.resolved():
        raise ValueError('incompatible fixed XGBoost configuration')
    if data['dependency'] != _dependency():
        raise ValueError('incompatible XGBoost dependency/runtime identity')
    if data['provenance'] != _json_copy(expected_provenance):
        raise ValueError('XGBoost provenance mismatch')
    _normalizer_vector(data['normalizer_mean'],'normalizer_mean')
    _normalizer_vector(data['normalizer_scale'],'normalizer_scale',positive=True)
    selected = data['selected_rounds']
    history = data['selection_history']
    if (type(selected) is not int or selected not in expected_config.candidates or
            not isinstance(history,list) or len(history) != len(expected_config.candidates)):
        raise ValueError('invalid selected round/selection history')
    for candidate,entry in zip(expected_config.candidates,history):
        if (not isinstance(entry,dict) or set(entry) != {'rounds','macro_f1'} or
                type(entry['rounds']) is not int or entry['rounds'] != candidate or
                isinstance(entry['macro_f1'],bool) or not isinstance(entry['macro_f1'],(int,float)) or
                not np.isfinite(entry['macro_f1']) or not 0 <= entry['macro_f1'] <= 1):
            raise ValueError('invalid selection history')
    if selected != max(history,key=lambda h:(h['macro_f1'],-h['rounds']))['rounds']:
        raise ValueError('selected round violates fixed val-select rule')
    populations = data['populations']
    if not isinstance(populations,dict) or set(populations) != {'train','selection'}:
        raise ValueError('invalid fitted populations')
    identities = []
    for key,role in (('train','train'),('selection','val-select')):
        pop = populations[key]
        if not isinstance(pop,dict) or set(pop) != {'kind','role','data_identity','n_samples','n_groups','sample_ids'}:
            raise ValueError('invalid fitted population metadata')
        ids = np.asarray(pop['sample_ids'])
        if (ids.ndim != 2 or ids.shape[1] != 2 or ids.dtype.kind not in 'iu' or not len(ids)):
            raise ValueError('invalid fitted population sample IDs')
        checked = FeatureTable(np.zeros((len(ids),len(FEATURE_NAMES))),ids[:,1],ids[:,0],
                               pop['role'],pop['kind'],pop['data_identity'])
        if (checked.kind != 'known' or checked.role != role or type(pop['n_samples']) is not int or
                type(pop['n_groups']) is not int or pop['n_samples'] != len(ids) or
                pop['n_groups'] != len(np.unique(ids[:,0]))):
            raise ValueError('invalid fitted population role/counts')
        identities.append(checked.identity)
    if identities[0] != identities[1]:
        raise ValueError('train and selection artifact identity mismatch')
    if data['binding'] != _binding(data):
        raise ValueError('XGBoost metadata binding mismatch')
    if data['scorer_identity'] != fingerprint({'binding':data['binding'],'model_sha256':data['model_sha256']}):
        raise ValueError('XGBoost scorer identity mismatch')


def _validate_native(booster,data):
    if (booster.num_features() != len(FEATURE_NAMES) or booster.feature_names != list(FEATURE_NAMES) or
            booster.num_boosted_rounds() != data['selected_rounds']):
        raise ValueError('native XGBoost feature order/count or round count mismatch')
    if booster.attr('b2_xgb_binding') != data['binding']:
        raise ValueError('native XGBoost binding mismatch')
    configuration = json.loads(booster.save_config())['learner']
    if (configuration['objective']['name'] != 'multi:softprob' or
            int(configuration['learner_model_param']['num_class']) != len(LABELS)):
        raise ValueError('native XGBoost objective/class count mismatch')


@dataclass(frozen=True)
class FittedXGB:
    booster: object
    normalizer_mean: np.ndarray
    normalizer_scale: np.ndarray
    selected_rounds: int
    selection_history: list
    config: XGBConfig
    provenance: dict
    populations: dict
    dependency: dict
    binding: str
    model_sha256: str
    scorer_identity: str

    def metadata(self):
        data = {'protocol':PROTOCOL,'feature_version':FEATURE_VERSION,'feature_names':list(FEATURE_NAMES),
            'feature_units':list(FEATURE_UNITS),'labels':list(LABELS),'config':self.config.resolved(),
            'dependency':self.dependency,'provenance':self.provenance,
            'normalizer_mean':self.normalizer_mean.tolist(),'normalizer_scale':self.normalizer_scale.tolist(),
            'selected_rounds':self.selected_rounds,'selection_history':self.selection_history,
            'populations':self.populations,'binding':self.binding,'model_sha256':self.model_sha256,
            'scorer_identity':self.scorer_identity}
        data['metadata_fingerprint'] = _metadata_fingerprint(data)
        return data

    def predict_proba(self,table):
        table = _table(table)
        metadata = self.metadata()
        _validate_metadata(metadata,expected_provenance=self.provenance,expected_config=self.config)
        _validate_native(self.booster,metadata)
        if _sha(_native_bytes(self.booster)) != self.model_sha256:
            raise ValueError('native fitted model checksum mismatch')
        return _probabilities(self.booster,_matrix(_standardize(table.values,self.normalizer_mean,self.normalizer_scale)))


def _fitted(booster,data,config):
    mean = np.array(data['normalizer_mean'],dtype=np.float64,copy=True)
    scale = np.array(data['normalizer_scale'],dtype=np.float64,copy=True)
    mean.setflags(write=False); scale.setflags(write=False)
    return FittedXGB(booster,mean,scale,data['selected_rounds'],_json_copy(data['selection_history']),config,
                     _json_copy(data['provenance']),_json_copy(data['populations']),_json_copy(data['dependency']),
                     data['binding'],data['model_sha256'],data['scorer_identity'])


def fit_xgb(train,selection,*,config,provenance):
    """Fit exactly16 train-only rounds, then select8 or16 using val-select macro-F1."""
    if not isinstance(config,XGBConfig):
        raise ValueError('fit requires the fixed P27 XGBConfig')
    train,selection = _table(train,role='train'),_table(selection,role='val-select')
    if train.identity != selection.identity:
        raise ValueError('train and selection must share their known artifact identity')
    if not isinstance(provenance,dict) or not provenance:
        raise ValueError('fitting requires nonempty bound provenance')
    provenance = _json_copy(provenance)
    dependency = _dependency()
    try:
        with np.errstate(over='raise',invalid='raise',divide='raise'):
            mean,scale = train.values.mean(0,dtype=np.float64),train.values.std(0,dtype=np.float64)
    except FloatingPointError as exc:
        raise ValueError('train-only normalization exceeds finite supported range') from exc
    scale[scale == 0] = 1
    dtrain = _matrix(_standardize(train.values,mean,scale),train.labels)
    dselect = _matrix(_standardize(selection.values,mean,scale))
    booster = xgb.train(config.parameters(),dtrain,num_boost_round=config.max_rounds)
    history = []
    for rounds in config.candidates:
        probability = _probabilities(booster,dselect,iteration_range=(0,rounds))
        history.append({'rounds':rounds,'macro_f1':float(macro_f1(selection.labels,probability.argmax(1),len(LABELS)))})
    selected = max(history,key=lambda h:(h['macro_f1'],-h['rounds']))['rounds']
    booster = booster[:selected]
    data = {'protocol':PROTOCOL,'feature_version':FEATURE_VERSION,'feature_names':list(FEATURE_NAMES),
            'feature_units':list(FEATURE_UNITS),'labels':list(LABELS),'config':config.resolved(),
            'dependency':dependency,'provenance':provenance,'normalizer_mean':mean.tolist(),
            'normalizer_scale':scale.tolist(),'selected_rounds':selected,'selection_history':history,
            'populations':{'train':_population(train),'selection':_population(selection)}}
    data['binding'] = _binding(data)
    booster.set_attr(b2_xgb_binding=data['binding'])
    data['model_sha256'] = _sha(_native_bytes(booster))
    data['scorer_identity'] = fingerprint({'binding':data['binding'],'model_sha256':data['model_sha256']})
    data['metadata_fingerprint'] = _metadata_fingerprint(data)
    _validate_metadata(data,expected_provenance=provenance,expected_config=config)
    _validate_native(booster,data)
    return _fitted(booster,data,config)


def save_model(fitted,directory):
    """Save a native model and strictly bound metadata, refusing any nonempty directory."""
    destination = Path(directory)
    if destination.exists() and any(destination.iterdir()):
        raise ValueError('refusing nonempty model directory')
    data = fitted.metadata()
    _validate_metadata(data,expected_provenance=fitted.provenance,expected_config=fitted.config)
    _validate_native(fitted.booster,data)
    raw = _native_bytes(fitted.booster)
    if _sha(raw) != data['model_sha256']:
        raise ValueError('native fitted model checksum mismatch')
    destination.mkdir(parents=True,exist_ok=True)
    (destination/'model.ubj').write_bytes(raw)
    (destination/'metadata.json').write_text(json.dumps(data,indent=2,allow_nan=False)+'\n')


def load_model(directory,*,expected_provenance,expected_config):
    """Fail closed on foreign, partial, altered or inconsistent native/model metadata."""
    try:
        root = Path(directory)
        data = _strict_json((root/'metadata.json').read_text())
        _validate_metadata(data,expected_provenance=expected_provenance,expected_config=expected_config)
        raw = (root/'model.ubj').read_bytes()
        if _sha(raw) != data['model_sha256']:
            raise ValueError('native XGBoost checksum mismatch')
        booster = xgb.Booster(params={'nthread':1,'device':'cpu'})
        booster.load_model(bytearray(raw))
        _validate_native(booster,data)
        if _sha(_native_bytes(booster)) != data['model_sha256']:
            raise ValueError('native XGBoost serialization checksum mismatch')
        return _fitted(booster,data,expected_config)
    except (OSError,KeyError,TypeError,ValueError,xgb.core.XGBoostError) as exc:
        raise ValueError(f'invalid XGBoost checkpoint: {exc}') from exc

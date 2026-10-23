"""P27 bounded B2 expert-feature/XGBoost baseline, on verified P20 artifacts.

CPU only. No generation path. Features stream one verified E1 shard at a time;
only small matrices, model probabilities and reporting indexes survive.
"""
from __future__ import annotations

import argparse
import json
import platform
import resource
import time
from pathlib import Path

import numpy as np

from geosim.b2_protocol import LABELS
from geosim.cancellation import CancellationConfig
from geosim.event_dataset import _strict_json
from .artifacts import fingerprint
from .b2_edsc import (ROLES, MAX_GROUPS, RULE, _preflight, _check_sources, _bound,
                      _sample_ids, _source_identity, _hash, _write, score_source)
from .b2_stream import open_b2_known
from .b2_expert import FEATURE_VERSION, FEATURE_NAMES, FEATURE_UNITS, extract_source
from .b2_xgb_model import XGBConfig, fit_xgb, save_model, load_model
from .b2_xgb_metrics import classifier_report
from .b2_edsc_metrics import evaluate_binary, compare_score_bundles
from .edsc import calibrate_clean

PROTOCOL = 'B2-XGB/1'
FILES = ('calibration.json', 'scores.json', 'results.json',
         'model/model.ubj', 'model/metadata.json')


def _report_split(source):
    """Evaluation-only metadata whitelist; never passed to extraction or fitting."""
    records = [None] * len(source)
    for shard in source.shards():
        for i, record in enumerate(shard.get('meta', [{}] * len(shard['seed']))):
            co = record.get('config', {}).get('co', {})
            records[shard['offset'] + i] = {
                'event': {k:record.get('event', {})[k] for k in
                          ('kind','c_over_i_db','c_over_i_psd_db','effective_c_over_i_psd_db')
                          if k in record.get('event', {})},
                'matched': record.get('matched', {}),
                'operating_condition': {k:co[k] for k in ('ibo_db','cn_up_db','cn_dn_db') if k in co}}
    return {**source.split(), 'meta':records}


def _output_reuse(destination, run_id, reuse):
    if not destination.exists() or not any(destination.iterdir()):
        return None
    if not reuse:
        raise ValueError('refusing nonempty output directory without --reuse')
    try:
        state = _strict_json((destination/'state.json').read_text())
        if state.get('run_id') != run_id or set(state.get('sha256', {})) != set(FILES):
            raise ValueError('reuse provenance mismatch or incomplete output directory')
        for name in FILES:
            if not (destination/name).is_file() or _hash(destination/name) != state['sha256'][name]:
                raise ValueError('reuse output/model checksum mismatch')
        return _strict_json((destination/'calibration.json').read_text())
    except OSError as exc:
        raise ValueError('reuse provenance missing or incomplete') from exc


def run_xgb(data, out, *, config=None, unknown_data=None, matched_data=None,
            smoke=False, bootstrap=200, with_baselines=False, reuse=False):
    """Fit only train, select only val-select, freeze clean calibration before test."""
    started = time.perf_counter()
    if type(bootstrap) is not int or not 1 <= bootstrap <= 1000:
        raise ValueError('bootstrap must be an integer in [1,1000]')
    if any(type(value) is not bool for value in (smoke,with_baselines,reuse)):
        raise ValueError('smoke, with_baselines and reuse must be booleans')
    config = XGBConfig() if config is None else config
    if not isinstance(config, XGBConfig):
        raise ValueError('config must be a frozen P27 XGBConfig')
    cap = 2 if smoke else MAX_GROUPS
    _preflight(data, 'B2-feat/1', cap)
    manifest, identity, sources = open_b2_known(data)
    if (manifest.get('protocol') != 'B2-feat/1' or manifest.get('labels') != list(LABELS)
            or manifest.get('benchmark_complete') is not False):
        raise ValueError('XGBoost requires canonical incomplete B2-feat/1 artifacts')
    if manifest.get('cancellation') != CancellationConfig().to_dict():
        raise ValueError('XGBoost requires the frozen P20 obs-cancel/1 settings')
    _check_sources(sources, cap)
    identities = {'known':identity, 'unknown':None, 'matched':None}
    evaluation = {'known':sources['test']}
    for kind, root in (('unknown',unknown_data), ('matched',matched_data)):
        if root is not None:
            identities[kind], evaluation[kind] = _bound(root, 'test' if kind=='unknown' else kind,
                                                       manifest, identity, cap)
    if 'unknown' in evaluation and not set(evaluation['unknown'].groups) <= set(sources['test'].groups):
        raise ValueError('test-only groups differ from known test groups')
    provenance = {'protocol':PROTOCOL, 'feature_version':FEATURE_VERSION,
        'feature_names':list(FEATURE_NAMES), 'feature_units':list(FEATURE_UNITS),
        'class_order':list(LABELS), 'config':config.resolved(),
        'evaluation_identity':identities, 'source_sha256':_source_identity(),
        'role_groups':{r:s.groups.tolist() for r,s in sources.items()},
        'smoke':smoke, 'group_cap':cap, 'bootstrap':bootstrap,
        'with_baselines':with_baselines, 'calibration_rule':RULE,
        'binary_score':'1-P(clean)', 'classifier_unknown_score':'1-max(P)'}
    run_id = fingerprint(provenance)
    destination = Path(out)
    previous = _output_reuse(destination, run_id, reuse)
    destination.mkdir(parents=True, exist_ok=True)
    train = extract_source(sources['train'], identity)
    selection = extract_source(sources['val-select'], identity)
    if previous is None:
        fitted = fit_xgb(train, selection, config=config, provenance=provenance)
        save_model(fitted, destination/'model')
    else:
        fitted = load_model(destination/'model', expected_provenance=provenance, expected_config=config)
        # Recompute permitted train statistics, never refit a booster during reuse.
        mean = train.values.mean(axis=0)
        scale = train.values.std(axis=0)
        scale = np.where(scale == 0, 1., scale)
        if not np.array_equal(mean, fitted.normalizer_mean) or not np.array_equal(scale, fitted.normalizer_scale):
            raise ValueError('reused train normalizer differs from source provenance')
        for key, table in (('train',train), ('selection',selection)):
            expected = {'kind':table.kind,'role':table.role,'data_identity':table.identity,
                        'n_samples':len(table),'n_groups':len(np.unique(table.groups)),
                        'sample_ids':np.column_stack((table.groups,table.labels)).tolist()}
            if fitted.populations.get(key) != expected:
                raise ValueError('reused fitted populations differ from verified source provenance')
    model_frozen_seconds = time.perf_counter()-started
    calibration_source = sources['val-calib']
    table = extract_source(calibration_source, identity)
    calibration_probabilities = fitted.predict_proba(table)
    calibration_values = {'xgboost':1.-calibration_probabilities[:,0]}
    cf_stats = {}
    if with_baselines:
        calibration_values.update(score_source(calibration_source, with_cfar=True))
    labels, groups = calibration_source.index['label'], calibration_source.index['seed']
    clean = labels == 0
    methods = ['xgboost'] + (['edsc','cfar_plan','cfar_blind'] if with_baselines else [])
    calibrations, scorer_ids = {}, {}
    for name in methods:
        values = calibration_values[name]
        if name.startswith('cfar'):
            mu, scale = values[clean].mean(0), values[clean].std(0)+1e-6
            cf_stats[name] = {'mean':mu.tolist(),'scale':scale.tolist()}
            values = ((values-mu)/scale).max(axis=1)
        scorer_ids[name] = (fitted.scorer_identity if name=='xgboost' else
                           fingerprint({'run_id':run_id,'method':name,'statistics':cf_stats.get(name)}))
        calibrations[name] = {**calibrate_clean(values, labels, groups, role=calibration_source.role,
                                              provenance=scorer_ids[name]),
                              'method':name,'score_statistics':cf_stats.get(name)}
    frozen = {'run_id':run_id,'model_scorer_identity':fitted.scorer_identity,'methods':calibrations}
    if previous is not None and previous != frozen:
        raise ValueError('recomputed calibration differs from bound provenance')
    _write(destination/'calibration.json', frozen)
    # First test feature extraction/inference occurs after every threshold is frozen.
    probabilities, scores, splits, plan_hashes = {}, {}, {}, {}
    for kind, source in evaluation.items():
        table = extract_source(source, identities[kind])
        probabilities[kind] = fitted.predict_proba(table)
        scores[kind] = {'xgboost':1.-probabilities[kind][:,0]}
        if with_baselines:
            values = score_source(source, with_cfar=True)
            plan_hashes[kind] = values['_plans']
            scores[kind].update({name:values[name] for name in methods if name!='xgboost'})
            for name, stats in cf_stats.items():
                scores[kind][name] = ((scores[kind][name]-np.asarray(stats['mean'])) /
                                     np.asarray(stats['scale'])).max(axis=1)
        else:
            # Operator-plan equality across stages is checked even without comparators.
            plans = {}
            for shard in source.shards():
                for i, group in enumerate(shard['seed']):
                    value = fingerprint(np.asarray(shard['mask'][i]).tolist())
                    if int(group) in plans and plans[int(group)] != value:
                        raise ValueError('operator plan mismatch within scenario group')
                    plans[int(group)] = value
            plan_hashes[kind] = plans
        splits[kind] = _report_split(source)
    if 'unknown' in plan_hashes and any(plan_hashes['known'].get(g)!=h for g,h in plan_hashes['unknown'].items()):
        raise ValueError('test-only operator plan mismatch against known test')
    sample_ids = {kind:_sample_ids(evaluation[kind]) if kind in evaluation else []
                  for kind in ('known','unknown','matched')}
    calibration_ids = [[int(g),0] for g in groups[clean]]
    bundles = []
    for name in methods:
        metrics = evaluate_binary(splits['known'], scores['known'][name], calibrations[name]['threshold'],
            unknown_split=splits.get('unknown'), unknown_scores=scores.get('unknown',{}).get(name),
            matched_split=splits.get('matched'), matched_scores=scores.get('matched',{}).get(name),
            bootstrap=bootstrap)
        bundles.append({'method':name,'scorer_identity':scorer_ids[name],
            'score_direction':'higher_is_more_anomalous','evaluation_identity':identities,
            'sample_ids':sample_ids,'calibration':{'population':'clean-only val-calib','nominal_pfa':.05,
                'rule':RULE,'data_identity':identity,'sample_ids':calibration_ids,
                'threshold':calibrations[name]['threshold']},'metrics':metrics})
    binary = compare_score_bundles(bundles)
    classification = classifier_report(splits['known'], probabilities['known'],
        unknown_split=splits.get('unknown'), unknown_probabilities=probabilities.get('unknown'),
        matched_split=splits.get('matched'), matched_probabilities=probabilities.get('matched'),
        bootstrap=bootstrap)
    result = {'protocol':PROTOCOL,'feature_version':FEATURE_VERSION,'benchmark_complete':False,
        'run_id':run_id,'provenance':provenance,'calibration':calibrations,
        'model':{'scorer_identity':fitted.scorer_identity,'selected_rounds':fitted.selected_rounds,
                 'selection_history':fitted.selection_history,
                 'normalizer_mean':fitted.normalizer_mean.tolist(),
                 'normalizer_scale':fitted.normalizer_scale.tolist()},
        'sample_counts':{**{r:len(s) for r,s in sources.items()},
                         **{k:len(s) for k,s in evaluation.items()}},
        'binary':binary,'classifier':classification,
        'runtime':{'wall_seconds':time.perf_counter()-started,'model_frozen_seconds':model_frozen_seconds,
            'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            'python':platform.python_version(),'platform':platform.platform(),
            'numpy':np.__version__,'device':'cpu','xgboost_threads':1,'loader':'E1 verified shard streaming'},
        'limitations':['Bounded engineering pilot; no recognition-performance claim.',
            'Two clean calibration samples cannot establish population Pfa=5%.',
            'Bootstrap fixes scorer/threshold; training, calibration and physical uncertainty omitted.',
            'P20 cancellation depth/errors and missing-carrier normalization limits remain.',
            'Binary anomaly A=1-P(clean) and classifier MSP U=1-max(P) have distinct meanings.']}
    _write(destination/'scores.json', {'run_id':run_id,'sample_ids':sample_ids,'bundles':bundles,
        'probabilities':{k:v.tolist() for k,v in probabilities.items()},
        'binary_scores':{k:{n:v.tolist() for n,v in values.items()} for k,values in scores.items()},
        'classifier_predictions':{k:v.argmax(axis=1).tolist() for k,v in probabilities.items()}})
    _write(destination/'results.json', result)
    _write(destination/'state.json', {'run_id':run_id,'sha256':{name:_hash(destination/name) for name in FILES}})
    return result


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    for arg in ('data','out'): p.add_argument('--'+arg,required=True)
    p.add_argument('--config',default='configs/b2_xgb_smoke.json')
    p.add_argument('--unknown-data');p.add_argument('--matched-data')
    p.add_argument('--smoke',action='store_true');p.add_argument('--with-baselines',action='store_true')
    p.add_argument('--reuse',action='store_true');p.add_argument('--bootstrap',type=int,default=200)
    a=p.parse_args(argv)
    run_xgb(a.data,a.out,config=XGBConfig.from_file(a.config),unknown_data=a.unknown_data,
            matched_data=a.matched_data,smoke=a.smoke,with_baselines=a.with_baselines,
            reuse=a.reuse,bootstrap=a.bootstrap)


if __name__=='__main__':
    main()

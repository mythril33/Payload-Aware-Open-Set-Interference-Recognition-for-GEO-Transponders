"""EDSC/1 bounded binary baseline on verified P20 artifacts (P26).

No generation or neural fitting. E1 readers verify artifacts shard by shard;
only O(N) scalar scores/indexes survive. CLI smoke refuses >2 groups/role.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import resource
import time
from pathlib import Path

import numpy as np

from geosim.b2_protocol import LABELS, role_for_group
from geosim.b2_scenarios import MATCHED_LABELS, TEST_FAMILIES
from geosim.cancellation import CancellationConfig
from geosim.event_dataset import _strict_json

from . import cfar
from .artifacts import fingerprint
from .b2_stream import open_b2_known, open_b2_matched, open_b2_test
from .b2_edsc_metrics import compare_score_bundles, evaluate_binary
from .edsc import FREQUENCIES_HZ, calibrate_clean, residual_energy

VERSION = 'EDSC/1'
ROLES = ('train', 'val-select', 'val-calib', 'test')
MAX_GROUPS = 32
MAX_SHARD_SAMPLES = 256
RULE = 'quantile_higher_0.95_strict_gt'


def _write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def _hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _source_identity():
    root = Path(__file__).parents[1]
    # Include transitive validator/plan/calibration helpers, not only the runner.
    paths = sorted(p for package in ('geoml', 'geosim') for p in (root/package).rglob('*.py'))
    return {str(path.relative_to(root)): _hash(path) for path in paths}


def _preflight(root, protocol, cap):
    """Refuse production-sized declared layouts before opening any NPZ arrays."""
    manifest = _strict_json((Path(root)/'manifest.json').read_text())
    if manifest.get('protocol') != protocol:
        raise ValueError(f'EDSC requires {protocol} artifacts, never the separate P21b stage')
    descriptors = manifest.get('roles', {'evaluation': manifest})
    for descriptor in descriptors.values():
        groups = descriptor.get('scenario_seeds', [])
        if not groups or len(groups) > cap:
            raise ValueError(f'EDSC bounded group cap is {cap} per role')
        shards = descriptor.get('shards', [])
        if not shards or any(type(s.get('n_samples')) is not int or
                             not 1 <= s['n_samples'] <= MAX_SHARD_SAMPLES for s in shards):
            raise ValueError(f'EDSC shard cap is {MAX_SHARD_SAMPLES} observations')


def _check_sources(sources, cap):
    if set(sources) != set(ROLES):
        raise ValueError(f'EDSC needs exactly the frozen known roles {ROLES}')
    for role, source in sources.items():
        if source.kind != 'known' or source.role != role or not source.has_residual:
            raise ValueError('known roles require their stored observation-only residual')
        _complete(source, range(len(LABELS)), cap)


def _complete(source, expected, cap):
    if not 1 <= len(source.groups) <= cap or max(source.shard_counts) > MAX_SHARD_SAMPLES:
        raise ValueError('EDSC source exceeds the bounded group/shard cap')
    if any(role_for_group(int(g)) != source.role for g in source.groups):
        raise ValueError('EDSC frozen role mismatch')
    key = 'family' if source.kind == 'test' else 'label'
    for group in source.groups:
        values = source.index[key][source.index['seed'] == group]
        if sorted(values.tolist()) != sorted(expected):
            raise ValueError('EDSC requires complete paired variants in each scenario group')


def _bound(root, kind, known_manifest, identity, cap):
    protocol = 'B2-test/1' if kind == 'test' else 'B2-match/1'
    _preflight(root, protocol, cap)
    manifest, other_identity, source = (open_b2_test(root) if kind == 'test' else open_b2_matched(root))
    binding = {'known_protocol': known_manifest['protocol'], 'known_data_fingerprint': identity,
               'known_request_fingerprint': known_manifest['request_fingerprint'],
               'known_calibration': known_manifest['calibration']}
    if kind == 'test':
        binding['known_test_groups'] = known_manifest['roles']['test']['scenario_seeds']
    else:
        binding['known_roles'] = sorted(known_manifest['roles'])
    if (manifest['request']['known'] != binding or manifest.get('calibration') != known_manifest['calibration'] or
            manifest['config'] != known_manifest['config'] or
            manifest.get('cancellation') != known_manifest.get('cancellation')):
        raise ValueError('evaluation artifact provenance/physics differs from known artifact')
    if manifest.get('benchmark_complete') is not False or not source.has_residual:
        raise ValueError('evaluation artifact must have the stored residual and benchmark_complete=false')
    expected = range(len(TEST_FAMILIES)) if kind == 'test' else [LABELS.index(n) for n in MATCHED_LABELS]
    _complete(source, expected, cap)
    return other_identity, source


def score_source(source, *, with_cfar=False):
    """Score only arrays; collect reporting truth separately after each score call."""
    if not source.has_residual:
        raise ValueError('EDSC requires a stored residual')
    out = {name: np.empty(len(source), np.float64) for name in
           ('edsc', 'planned_db', 'unplanned_db', 'reference_db')}
    if with_cfar:
        out.update({name: np.empty((len(source), 2), np.float64) for name in ('cfar_plan', 'cfar_blind')})
    report_meta, plans = [None]*len(source), {}
    for shard in source.shards():
        start, n = shard['offset'], len(shard['seed'])
        if n > MAX_SHARD_SAMPLES:
            raise ValueError('EDSC shard cap exceeded')
        # Deliberately whitelist the three observable arrays at the scorer boundary.
        values = residual_energy(shard['spec'], shard['mask'], shard.get('residual'))
        for name, value in values.items():
            out['edsc' if name == 'score_db' else name][start:start+n] = value
        if with_cfar:
            for name, use_plan in (('cfar_plan', True), ('cfar_blind', False)):
                out[name][start:start+n] = cfar.features(shard['spec'][:, 0], shard['mask'][:, 0],
                    FREQUENCIES_HZ, np.full(n, 36e6), use_plan)
                if not np.isfinite(out[name][start:start+n]).all():
                    raise ValueError('CFAR produced nonfinite scores')
        for i, record in enumerate(shard.get('meta', [{}]*n)):
            group = int(shard['seed'][i])
            plan_hash = hashlib.sha256(np.asarray(shard['mask'][i]).tobytes()).hexdigest()
            if group in plans and plans[group] != plan_hash:
                raise ValueError('operator plan mismatch within a paired scenario group')
            plans[group] = plan_hash
            co = record.get('config', {}).get('co', {})
            # Simulation conditions are report-only; they never enter score/calibration APIs.
            report_meta[start+i] = {'event': {k: record.get('event', {})[k] for k in
                ('kind', 'c_over_i_psd_db', 'effective_c_over_i_psd_db', 'c_over_i_db') if k in record.get('event', {})},
                'matched': record.get('matched', {}), 'operating_condition': {
                    k: co[k] for k in ('ibo_db', 'cn_up_db', 'cn_dn_db') if k in co}}
    out['_meta'], out['_plans'] = report_meta, plans
    return out


def _sample_ids(source):
    key = 'family' if source.kind == 'test' else 'label'
    return np.column_stack((source.index['seed'], source.index[key])).tolist()


def run_edsc(data, out, *, unknown_data=None, matched_data=None, smoke=False,
             bootstrap=200, with_cfar=False, reuse=False):
    """Execute one capped CPU evaluation; reuse revalidates/recomputes, never trusts a checkpoint."""
    started = time.perf_counter()
    if type(bootstrap) is not int or not 1 <= bootstrap <= 1000:
        raise ValueError('bootstrap must be an integer in [1,1000]')
    if any(type(v) is not bool for v in (smoke, with_cfar, reuse)):
        raise ValueError('smoke, with_cfar and reuse must be booleans')
    cap = 2 if smoke else MAX_GROUPS
    _preflight(data, 'B2-feat/1', cap)
    manifest, identity, sources = open_b2_known(data)
    if (manifest.get('protocol') != 'B2-feat/1' or manifest.get('labels') != list(LABELS)
            or manifest.get('benchmark_complete') is not False):
        raise ValueError('EDSC requires canonical incomplete B2-feat/1 with frozen known labels')
    if manifest.get('cancellation') != CancellationConfig().to_dict():
        raise ValueError('EDSC/1 requires the frozen P20 obs-cancel/1 settings')
    _check_sources(sources, cap)
    evaluation = {'known': identity, 'unknown': None, 'matched': None}
    eval_sources = {'known': sources['test']}
    for kind, root in (('unknown', unknown_data), ('matched', matched_data)):
        if root is not None:
            evaluation[kind], eval_sources[kind] = _bound(root, 'test' if kind == 'unknown' else kind,
                                                        manifest, identity, cap)
    if 'unknown' in eval_sources and not set(eval_sources['unknown'].groups) <= set(sources['test'].groups):
        raise ValueError('test-only groups differ from the bound known test role')
    provenance = {'protocol': VERSION, 'evaluation_identity': evaluation,
                  'sources': _source_identity(), 'numpy': np.__version__,
                  'bootstrap': bootstrap, 'smoke': smoke, 'with_cfar': with_cfar,
                  'calibration_rule': RULE, 'group_cap': cap, 'shard_cap': MAX_SHARD_SAMPLES}
    run_id = fingerprint(provenance)
    destination = Path(out)
    previous = None
    if destination.exists() and any(destination.iterdir()):
        if not reuse:
            raise ValueError('refusing nonempty output directory without --reuse')
        state = _strict_json((destination/'state.json').read_text()) if (destination/'state.json').is_file() else {}
        if state.get('run_id') != run_id:
            raise ValueError('reuse provenance mismatch or incomplete output directory')
        for name in ('calibration.json', 'scores.json', 'results.json'):
            if not (destination/name).is_file() or _hash(destination/name) != state.get('sha256', {}).get(name):
                raise ValueError('reuse output checksum mismatch')
        previous = _strict_json((destination/'calibration.json').read_text())
    destination.mkdir(parents=True, exist_ok=True)
    calib_source = sources['val-calib']
    calibration_values = score_source(calib_source, with_cfar=with_cfar)
    labels, groups = calib_source.index['label'], calib_source.index['seed']
    clean = labels == 0
    calibrations, cfar_stats = {}, {}
    methods = ['edsc'] + (['cfar_plan', 'cfar_blind'] if with_cfar else [])
    for name in methods:
        values = calibration_values[name]
        if name.startswith('cfar'):
            mu, sd = values[clean].mean(0), values[clean].std(0) + 1e-6
            cfar_stats[name] = {'mean': mu.tolist(), 'std_plus_1e_minus6': sd.tolist()}
            values = ((values-mu)/sd).max(axis=1)
        calibrations[name] = {**calibrate_clean(values, labels, groups, role=calib_source.role, provenance=run_id),
                              'method': name, 'score_statistics': cfar_stats.get(name)}
    frozen = {'run_id': run_id, 'methods': calibrations}
    if previous is not None and previous != frozen:
        raise ValueError('recomputed calibration differs from bound provenance')
    # Freeze and persist all thresholds before the first evaluation score is computed.
    _write(destination/'calibration.json', frozen)
    scored = {kind: score_source(source, with_cfar=with_cfar) for kind, source in eval_sources.items()}
    if 'unknown' in scored:
        if any(scored['known']['_plans'].get(g) != h for g,h in scored['unknown']['_plans'].items()):
            raise ValueError('test-only operator plan mismatch against known test observation')
    for value in scored.values():
        for name, stats in cfar_stats.items():
            value[name] = ((value[name]-np.asarray(stats['mean']))/np.asarray(stats['std_plus_1e_minus6'])).max(axis=1)
    splits = {kind: {**source.split(), 'meta': scored[kind]['_meta']} for kind, source in eval_sources.items()}
    sample_ids = {kind: _sample_ids(eval_sources[kind]) if kind in eval_sources else []
                  for kind in ('known', 'unknown', 'matched')}
    calibration_ids = [[int(g), 0] for g in groups[clean]]
    bundles = []
    for name in methods:
        metrics = evaluate_binary(splits['known'], scored['known'][name], calibrations[name]['threshold'],
            unknown_split=splits.get('unknown'), unknown_scores=scored.get('unknown', {}).get(name),
            matched_split=splits.get('matched'), matched_scores=scored.get('matched', {}).get(name), bootstrap=bootstrap)
        bundles.append({'method': name, 'score_direction': 'higher_is_more_anomalous',
            'scorer_identity': fingerprint({'run_id': run_id, 'method': name, 'statistics': cfar_stats.get(name)}),
            'evaluation_identity': evaluation, 'sample_ids': sample_ids,
            'calibration': {'population': 'clean-only val-calib', 'nominal_pfa': .05, 'rule': RULE,
                            'data_identity': identity, 'sample_ids': calibration_ids,
                            'threshold': calibrations[name]['threshold']}, 'metrics': metrics})
    comparison = compare_score_bundles(bundles)
    scores = {'run_id': run_id, 'sample_ids': sample_ids, 'methods': {
        name: {kind: value[name].tolist() for kind, value in scored.items()} for name in methods},
        'edsc_diagnostics': {kind: {key: value[key].tolist() for key in
            ('planned_db', 'unplanned_db', 'reference_db')} for kind,value in scored.items()}, 'bundles': bundles}
    result = {'protocol': VERSION, 'benchmark_complete': False, 'run_id': run_id,
        'provenance': provenance, 'calibration': calibrations, 'methods': comparison,
        'sample_counts': {**{role:len(source) for role,source in sources.items()},
                          **{kind:len(source) for kind,source in eval_sources.items()}},
        'runtime': {'wall_seconds': time.perf_counter()-started,
                    'peak_rss_kib': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                    'python': platform.python_version(), 'platform': platform.platform(),
                    'numpy': np.__version__, 'device': 'cpu', 'loader': 'E1 verified one-shard streaming'},
        'limitations': ['Bounded engineering/pilot evidence only; no recognition performance claim.',
            'Two clean calibration groups are permitted for smoke; nominal Pfa is not a population guarantee.',
            'Group bootstrap conditions on frozen scorer and threshold; no calibration or physical-model uncertainty.',
            'obs-cancel/1 residual includes cancellation error, phase noise and payload distortion.',
            'No neural model fitted or compared using its known-acceptance rejection threshold.']}
    _write(destination/'scores.json', scores)
    _write(destination/'results.json', result)
    _write(destination/'state.json', {'run_id':run_id, 'sha256':{n:_hash(destination/n) for n in
        ('calibration.json','scores.json','results.json')}})
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--unknown-data')
    parser.add_argument('--matched-data')
    parser.add_argument('--smoke', action='store_true')
    parser.add_argument('--with-cfar', action='store_true')
    parser.add_argument('--reuse', action='store_true')
    parser.add_argument('--bootstrap', type=int, default=200)
    args = parser.parse_args(argv)
    run_edsc(args.data, args.out, unknown_data=args.unknown_data, matched_data=args.matched_data,
             smoke=args.smoke, with_cfar=args.with_cfar, reuse=args.reuse, bootstrap=args.bootstrap)


if __name__ == '__main__':
    main()

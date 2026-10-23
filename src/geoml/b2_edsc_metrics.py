"""Binary anomaly reporting for P26, shared by EDSC and comparable score providers.

Labels and operating metadata are used here only after scores and thresholds are
frozen. This module never fits a detector. Unknown-positive ranking compares
unknown families against *all eight* known test classes; event detection compares
non-clean scenes with clean scenes at a clean-only calibrated alarm threshold.
"""
from __future__ import annotations

import numpy as np

from geosim.b2_protocol import LABELS, NEAR_UNKNOWN, role_for_group
from geosim.b2_scenarios import MATCHED_BINS, TEST_FAMILIES
from .openset_metrics import _fpr_at_tpr, _roc, _trapezoid

RANK_KEYS = ('unknown_auroc', 'unknown_aupr', 'unknown_fpr_at_95_tpr')
BIN_NAMES = ('[4,7)', '[7,10)', '[10,13]')
BOOTSTRAP_NOTE = 'scenario groups resampled with all variants together; threshold and scorer fixed'


def _bootstrap_count(value):
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, np.integer)) or not 1 <= value <= 2000:
        raise ValueError('bootstrap must be an integer in [1,2000]')
    return int(value)


def _vector(values, name, *, kind='score'):
    raw = np.asarray(values)
    if raw.ndim != 1:
        raise ValueError(f'{name} must be a vector')
    # Empty Python lists have float dtype; accept them for group/boolean inputs.
    if not len(raw):
        return np.asarray([], dtype=bool if kind == 'boolean' else np.int64 if kind == 'group' else float)
    if kind == 'boolean':
        if raw.dtype.kind != 'b':
            raise ValueError(f'{name} must be a boolean vector')
        return raw
    if kind == 'group':
        if raw.dtype.kind not in 'iu':
            raise ValueError(f'{name} must be an integer vector')
        return raw.astype(np.int64)
    if raw.dtype.kind not in 'iuf' or not np.isfinite(raw).all():
        raise ValueError(f'{name} must be a finite real numeric vector')
    return raw.astype(float)


def _paired_vectors(values, groups, *, kind='score'):
    a, g = _vector(values, 'values', kind=kind), _vector(groups, 'groups', kind='group')
    if a.shape != g.shape:
        raise ValueError('values and groups must have the same length')
    return a, g


def _interval(values):
    return [float(x) for x in np.percentile(values, [2.5, 97.5])]


def _mean(values, groups, *, bootstrap=200, seed=20261022):
    bootstrap = _bootstrap_count(bootstrap)
    values, groups = _paired_vectors(values, groups)
    ids, inverse = np.unique(groups, return_inverse=True)
    n = len(values)
    result = {'mean':float(values.mean()) if n else None, 'n':n, 'n_groups':len(ids),
              'ci95':None, 'reason':None, 'bootstrap':{'unit':BOOTSTRAP_NOTE,
                  'requested':bootstrap, 'valid':0, 'seed':seed}}
    if len(ids) < 2:
        result['reason'] = 'empty selection' if not n else 'fewer than two scenario groups'
        return result
    sums = np.bincount(inverse, weights=values, minlength=len(ids))
    counts = np.bincount(inverse, minlength=len(ids))
    rng = np.random.default_rng(seed)
    means = []
    for _ in range(bootstrap):
        draw = rng.integers(0, len(ids), size=len(ids))
        means.append(float(sums[draw].sum() / counts[draw].sum()))
    result['ci95'] = _interval(means)
    result['bootstrap']['valid'] = bootstrap
    return result


def rate(alarms, groups, *, bootstrap=200, seed=20261022):
    """Count / denominator and cluster-bootstrap CI for a boolean outcome."""
    alarms, groups = _paired_vectors(alarms, groups, kind='boolean')
    result = _mean(alarms.astype(float), groups, bootstrap=bootstrap, seed=seed)
    result['rate'] = result.pop('mean')
    result['count'] = int(alarms.sum())
    return result


def _rank(known, unknown):
    fpr, tpr, tp, detected = _roc(known, unknown)
    return {'unknown_auroc':_trapezoid(tpr, fpr),
            'unknown_aupr':float(np.sum(np.diff(tpr) * (tp / detected))),
            'unknown_fpr_at_95_tpr':_fpr_at_tpr(fpr, tpr, .95)}


def ranking(known_scores, unknown_scores, known_groups, unknown_groups, *, bootstrap=200, seed=20261022):
    """Unknown-positive AUROC/AP/FPR95, preserving paired scenario variants.

    AP is the recall-weighted step integral; tied scores enter together. FPR95
    is a ranking diagnostic, not the clean-calibrated operational false alarm.
    """
    bootstrap = _bootstrap_count(bootstrap)
    known, kg = _paired_vectors(known_scores, known_groups)
    unknown, ug = _paired_vectors(unknown_scores, unknown_groups)
    ids = np.union1d(kg, ug)
    result = {**dict.fromkeys(RANK_KEYS), 'n_known':len(known), 'n_unknown':len(unknown),
              'unknown_prevalence':len(unknown)/(len(known)+len(unknown)) if len(known)+len(unknown) else None,
              'ci95':None, 'reason':None, 'bootstrap':{'unit':BOOTSTRAP_NOTE,
                  'requested':bootstrap, 'valid':0, 'seed':seed, 'n_groups':len(ids)},
              'conventions':{'positive':'unknown', 'negative':'all known test scenes, including known interference',
                  'score_direction':'higher_is_more_anomalous', 'aupr':'average_precision_step_integral',
                  'ties':'equal scores enter together',
                  'fpr95_denominator':'all known test scenes at first grouped threshold with >=95% unknown TPR'}}
    if not len(known) or not len(unknown):
        result['reason'] = 'ranking requires nonempty known and unknown populations'
        return result
    result.update(_rank(known, unknown))
    if len(ids) < 2:
        result['reason'] = 'fewer than two scenario groups'
        return result
    ki, ui = np.searchsorted(ids, kg), np.searchsorted(ids, ug)
    rng, estimates = np.random.default_rng(seed), {k:[] for k in RANK_KEYS}
    for _ in range(bootstrap):
        frequencies = np.bincount(rng.integers(0, len(ids), size=len(ids)), minlength=len(ids))
        # Only one bootstrap score vector exists at a time, never all draws.
        k, u = np.repeat(known, frequencies[ki]), np.repeat(unknown, frequencies[ui])
        if not len(k) or not len(u):
            continue
        metrics = _rank(k, u)
        for key in RANK_KEYS:
            estimates[key].append(metrics[key])
    valid = len(estimates[RANK_KEYS[0]])
    result['bootstrap']['valid'] = valid
    if valid:
        result['ci95'] = {key:_interval(values) for key, values in estimates.items()}
    else:
        result['reason'] = 'no bootstrap draw retained both populations'
    return result


def _split(split, scores, *, role, labels='label'):
    if not isinstance(split, dict):
        raise ValueError('evaluation split must be a dictionary')
    scores, groups = _paired_vectors(scores, split.get('seed', []))
    truth = _vector(split.get(labels, []), labels, kind='group')
    if truth.shape != scores.shape:
        raise ValueError('evaluation scores and labels must have the same length')
    if any(role_for_group(int(g)) != role for g in np.unique(groups)):
        raise ValueError(f'evaluation groups must belong to {role}')
    maximum = len(TEST_FAMILIES) if labels == 'family' else len(LABELS)
    if np.any(truth < 0) or np.any(truth >= maximum):
        raise ValueError('evaluation label out of range')
    if len(set(zip(groups.tolist(), truth.tolist()))) != len(groups):
        raise ValueError(f'duplicate {role} evaluation group/label pair')
    return truth, groups, scores


def _bin_select(values, edges, index):
    lo, hi = edges[index]
    return np.isfinite(values) & (values >= lo) & ((values <= hi) if index == len(edges)-1 else (values < hi))


def _binned(alarms, groups, values, edges, *, bootstrap):
    values = np.asarray(values, dtype=float)
    return {'n':len(values), 'n_missing':int((~np.isfinite(values)).sum()),
            'n_outside_bins':int((np.isfinite(values) & ~np.logical_or.reduce([
                _bin_select(values, edges, b) for b in range(len(edges))])).sum()),
            'bins':{f'[{lo:g},{hi:g}{"]" if b == len(edges)-1 else ")"}':
                rate(alarms[_bin_select(values, edges, b)], groups[_bin_select(values, edges, b)], bootstrap=bootstrap)
                for b, (lo, hi) in enumerate(edges)}}


def _condition_report(split, labels, groups, alarms, *, bootstrap):
    meta = split.get('meta', [{} for _ in labels])
    if len(meta) != len(labels):
        raise ValueError('operating metadata must match evaluation samples')
    out = {}
    for index, name in enumerate(LABELS):
        keep = labels == index
        records = [m for m, k in zip(meta, keep) if k]
        entry = {}
        for field, edges in [('ibo_db', ((1,4),(4,9),(9,11),(11,13))),
                             ('cn_up_db', ((15,20),(20,25),(25,30))),
                             ('cn_dn_db', ((15,20),(20,25),(25,30)))]:
            values = [m.get('operating_condition', {}).get(field, np.nan) for m in records]
            entry[field] = _binned(alarms[keep], groups[keep], values, edges, bootstrap=bootstrap)
        # P18 CuC C/I bins are distinct from the K17c PSD-level bins.
        if name == 'carrier_under_carrier':
            values = [m.get('event', {}).get('c_over_i_db', np.nan) for m in records]
            entry['c_over_i_db'] = _binned(alarms[keep], groups[keep], values,
                                         ((5,15),(15,25),(25,30)), bootstrap=bootstrap)
        if name in ('adjacent_satellite', 'unauthorized'):
            values = [m.get('event', {}).get('c_over_i_psd_db', np.nan) for m in records]
            entry['c_over_i_psd_db'] = _binned(alarms[keep], groups[keep], values,
                                             MATCHED_BINS, bootstrap=bootstrap)
        out[name] = entry
    return out


def _matched(split, scores, threshold, *, bootstrap):
    labels, groups, scores = _split(split, scores, role='test-matched')
    bins = _vector(split.get('matched_bin', []), 'matched_bin', kind='group')
    if bins.shape != labels.shape or np.any(bins < 0) or np.any(bins > 2):
        raise ValueError('matched bins must identify the three frozen K17c bins')
    for group in np.unique(groups):
        keep = groups == group
        if set(labels[keep]) != {0, 3, 6} or len(labels[keep]) != 3 or len(set(bins[keep])) != 1:
            raise ValueError('matched group must contain exactly one clean, ASI and unauthorized variant in one bin')
    alarms = scores > threshold

    def subset(keep):
        ids = np.unique(groups[keep])
        asi, unauthorized, score_gaps = [], [], []
        for group in ids:
            a, u = (groups == group) & (labels == 6), (groups == group) & (labels == 3)
            asi.append(bool(alarms[a][0]))
            unauthorized.append(bool(alarms[u][0]))
            score_gaps.append(float(scores[u][0] - scores[a][0]))
        differences = np.asarray(unauthorized, dtype=float)-np.asarray(asi, dtype=float)
        return {'n_samples':int(keep.sum()), 'n_groups':len(ids),
                'clean_false_alarm':rate(alarms[keep & (labels == 0)], groups[keep & (labels == 0)], bootstrap=bootstrap),
                'pair':{'n_pairs':len(ids),
                    'adjacent_satellite_detection':rate(np.asarray(asi, dtype=bool), ids, bootstrap=bootstrap),
                    'unauthorized_detection':rate(np.asarray(unauthorized, dtype=bool), ids, bootstrap=bootstrap),
                    'difference_unauthorized_minus_asi':_mean(differences, ids, bootstrap=bootstrap),
                    'score_difference_unauthorized_minus_asi':_mean(score_gaps, ids, bootstrap=bootstrap)}}
    return {**subset(np.ones(len(labels), dtype=bool)),
            'per_bin':{name:subset(bins == b) for b,name in enumerate(BIN_NAMES)},
            'conventions':{'bin_edges':'frozen K17c C/I_psd [4,7), [7,10), [10,13]',
                'comparison':'paired binary alarm difference, unauthorized minus ASI; no class discrimination claim',
                'limitation':'matched carrier widths and level distribution differ from natural test scenes'}}


def evaluate_binary(known_split, known_scores, threshold, *, unknown_split=None, unknown_scores=None,
                    matched_split=None, matched_scores=None, bootstrap=200):
    """Report binary alarms and unknown ranking with explicit populations/counts."""
    bootstrap = _bootstrap_count(bootstrap)
    if isinstance(threshold, (bool, np.bool_)) or not isinstance(threshold, (int,float,np.integer,np.floating)) or not np.isfinite(threshold):
        raise ValueError('threshold must be finite')
    labels, groups, scores = _split(known_split, known_scores, role='test')
    alarms = scores > threshold
    result = {'metric_protocol':'B2-binary-anomaly/1', 'threshold':float(threshold), 'alarm_rule':'score > threshold',
        'known':{'n':len(scores), 'n_groups':len(np.unique(groups)),
            'clean_false_alarm':rate(alarms[labels == 0], groups[labels == 0], bootstrap=bootstrap),
            'event_detection':rate(alarms[labels != 0], groups[labels != 0], bootstrap=bootstrap),
            'per_class':{name:rate(alarms[labels == i], groups[labels == i], bootstrap=bootstrap)
                         for i,name in enumerate(LABELS)},
            'operating_conditions':_condition_report(known_split, labels, groups, alarms, bootstrap=bootstrap)},
        'unknown':{'families':{}, 'pooled_near':None}, 'matched':None,
        'unsupported':{'multiclass_accuracy':None, 'oscr_auc':None, 'class_predictions':None,
            'n_known':len(scores), 'reason':'binary anomaly scores provide no known-class predictions; OSCR requires correct class decisions'},
        'uncertainty':'pilot cluster-bootstrap intervals are conditional on fixed scores and threshold; tiny group counts do not establish population performance'}
    if unknown_split is None:
        if unknown_scores is not None:
            raise ValueError('unknown scores require an unknown split')
        family, ug, us = np.array([],dtype=int), np.array([],dtype=int), np.array([],dtype=float)
    else:
        family, ug, us = _split(unknown_split, unknown_scores, role='test', labels='family')
        if tuple(unknown_split.get('families', TEST_FAMILIES)) != TEST_FAMILIES:
            raise ValueError('unknown family order must equal the frozen B2-test/1 order')
    for i,name in enumerate(TEST_FAMILIES):
        keep = family == i
        benign = name == 'cid_overlay'
        result['unknown']['families'][name] = {'n':int(keep.sum()),
            'pre_registered_group':'benign' if benign else 'near' if name in NEAR_UNKNOWN else 'equivalence_limited',
            'alarm':rate(us[keep] > threshold, ug[keep], bootstrap=bootstrap),
            'ranking':None if benign else ranking(scores, us[keep], groups, ug[keep], bootstrap=bootstrap),
            'ranking_reason':'benign CID is excluded from unknown-positive ranking' if benign else None,
            'expected_binary_decision':'no alarm' if benign else 'alarm'}
    near = np.isin(family, [TEST_FAMILIES.index(name) for name in NEAR_UNKNOWN])
    result['unknown']['pooled_near'] = {'families':list(NEAR_UNKNOWN),
        'ranking':ranking(scores, us[near], groups, ug[near], bootstrap=bootstrap),
        'alarm':rate(us[near] > threshold, ug[near], bootstrap=bootstrap),
        'exclusions':'wideband_noise is reported separately; cid_overlay is benign'}
    if matched_split is not None:
        result['matched'] = _matched(matched_split, matched_scores, threshold, bootstrap=bootstrap)
        result['matched']['natural_comparison'] = {
            'limitation':'natural and matched distributions differ in carrier width and levels',
            'classes':{name:{'detection':result['known']['per_class'][name],
                'c_over_i_psd_db':result['known']['operating_conditions'][name]['c_over_i_psd_db']}
                for name in ('adjacent_satellite','unauthorized')}}
    elif matched_scores is not None:
        raise ValueError('matched scores require a matched split')
    return result


def _comparison_ids(sample_ids, *, role, label_limit):
    if not isinstance(sample_ids,list):
        return False
    seen = set()
    for row in sample_ids:
        if not (isinstance(row,(list,tuple)) and len(row) == 2 and
                all(isinstance(v,int) and not isinstance(v,bool) for v in row) and
                role_for_group(row[0]) == role and 0 <= row[1] < label_limit):
            return False
        pair = tuple(row)
        if pair in seen:
            return False
        seen.add(pair)
    return True



def _reported_populations_match(metrics, samples):
    """Check every common report population against the ordered sample IDs."""
    nk = len(samples['known'])
    known = metrics['known']
    expected_known = np.bincount([row[1] for row in samples['known']], minlength=len(LABELS))
    if (known['n'] != nk or known['clean_false_alarm']['n'] != int(expected_known[0]) or
            known['event_detection']['n'] != nk-int(expected_known[0]) or
            any(known['per_class'][name]['n'] != int(expected_known[i]) for i,name in enumerate(LABELS))):
        return False
    expected_unknown = np.bincount([row[1] for row in samples['unknown']], minlength=len(TEST_FAMILIES))
    families = metrics['unknown']['families']
    if set(families) != set(TEST_FAMILIES):
        return False
    for i,name in enumerate(TEST_FAMILIES):
        family = families[name]
        count = int(expected_unknown[i])
        if family['n'] != count or family['alarm']['n'] != count:
            return False
        rank = family['ranking']
        if name == 'cid_overlay':
            if rank is not None:
                return False
        elif rank['n_known'] != nk or rank['n_unknown'] != count:
            return False
    near_count = sum(int(expected_unknown[TEST_FAMILIES.index(name)]) for name in NEAR_UNKNOWN)
    pooled = metrics['unknown']['pooled_near']
    if (pooled['ranking']['n_known'] != nk or pooled['ranking']['n_unknown'] != near_count or
            pooled['alarm']['n'] != near_count):
        return False
    matched = metrics['matched']
    if not samples['matched']:
        return matched is None
    ids = {row[0] for row in samples['matched']}
    return (isinstance(matched,dict) and matched['n_samples'] == len(samples['matched']) and
            matched['n_groups'] == len(ids) and matched['pair']['n_pairs'] == len(ids) and
            matched['clean_false_alarm']['n'] == len(ids) and
            matched['pair']['adjacent_satellite_detection']['n'] == len(ids) and
            matched['pair']['unauthorized_detection']['n'] == len(ids))


def compare_score_bundles(bundles):
    """Accept comparison only for identical scenes and clean-calibration rules.

    Learned-model known-acceptance rejection thresholds are incompatible with
    this operational alarm comparison. A learned score can enter after its own
    fixed clean-only val-calib threshold is computed with the same rule/rows.
    A required method-specific scorer identity binds the provider's frozen
    feature/scorer/checkpoint state; identities may differ between methods.
    This interface consumes frozen scores' reports; it does not recalibrate.
    """
    if not isinstance(bundles, (list,tuple)) or not bundles:
        raise ValueError('comparison requires at least one score bundle')
    reference, output = None, {}
    for bundle in bundles:
        if not isinstance(bundle, dict):
            raise ValueError('comparison bundle must be a dictionary')
        try:
            method, calibration = bundle['method'], bundle['calibration']
            scorer_identity = bundle['scorer_identity']
            invariant = {key:bundle[key] for key in ('score_direction','evaluation_identity','sample_ids')}
            invariant['calibration'] = {key:calibration[key] for key in ('population','nominal_pfa','rule','data_identity','sample_ids')}
            ids = calibration['sample_ids']
            valid_ids = (isinstance(ids,list) and len(ids) >= 2 and
                _comparison_ids(ids, role='val-calib', label_limit=1))
            evaluation, samples = invariant['evaluation_identity'], invariant['sample_ids']
            valid_evaluation = (isinstance(evaluation,dict) and isinstance(samples,dict) and
                set(evaluation) == set(samples) == {'known','unknown','matched'})
            if valid_evaluation:
                for source, role, maximum in [('known','test',len(LABELS)),
                        ('unknown','test',len(TEST_FAMILIES)), ('matched','test-matched',len(LABELS))]:
                    identity = evaluation[source]
                    if source == 'known' and not (isinstance(identity,str) and identity):
                        valid_evaluation = False
                    if identity is not None and not (isinstance(identity,str) and identity):
                        valid_evaluation = False
                    if bool(samples[source]) != (identity is not None):
                        valid_evaluation = False
                    if not _comparison_ids(samples[source], role=role, label_limit=maximum):
                        valid_evaluation = False
            threshold = calibration['threshold']
            valid_threshold = (not isinstance(threshold,(bool,np.bool_)) and
                isinstance(threshold,(int,float)) and np.isfinite(threshold))
            if 'calibration_groups' in calibration:
                valid_ids = valid_ids and calibration['calibration_groups'] == [row[0] for row in ids]
            valid = (isinstance(scorer_identity,str) and bool(scorer_identity.strip()) and
                isinstance(method,str) and method and method not in output and valid_ids and valid_evaluation and valid_threshold and
                invariant['score_direction'] == 'higher_is_more_anomalous' and
                calibration['population'] == 'clean-only val-calib' and calibration['nominal_pfa'] == .05 and
                calibration['rule'] == 'quantile_higher_0.95_strict_gt' and
                isinstance(calibration['data_identity'],str) and calibration['data_identity'])
            metrics = bundle['metrics']
            valid_metrics = (isinstance(metrics,dict) and
                metrics.get('metric_protocol') == 'B2-binary-anomaly/1' and
                metrics.get('alarm_rule') == 'score > threshold' and
                metrics.get('threshold') == threshold and
                isinstance(metrics.get('known'),dict) and
                metrics['known'].get('n') == len(samples['known']) and
                calibration['data_identity'] == evaluation['known'] and
                _reported_populations_match(metrics, samples))
        except (KeyError,TypeError,ValueError,AttributeError) as exc:
            raise ValueError('incomplete or invalid comparison bundle') from exc
        if not valid or not valid_metrics or (reference is not None and invariant != reference):
            raise ValueError('incompatible comparison populations, calibration or score direction')
        reference = invariant
        output[method] = metrics
    return output

"""P27 classifier reporting, separate from the P26 binary anomaly interface.

All labels and groups below are report-only. No model fitting, feature
selection or threshold calibration occurs here. The classifier's unknown
score is MSP U=1-max(P), whereas the separate binary alarm score is
A=1-P(clean). An alarm score never supplies artificial class predictions.
"""
from __future__ import annotations

import numpy as np

from geosim.b2_protocol import LABELS, NEAR_UNKNOWN
from geosim.b2_scenarios import TEST_FAMILIES
from .b2_edsc_metrics import BIN_NAMES, _bootstrap_count, _split, _vector, rate
from .metrics import confusion, macro_f1
from .openset_metrics import ranking_metrics

_RANK_KEYS = ('unknown_auroc', 'unknown_aupr', 'unknown_fpr_at_95_tpr', 'oscr_auc')
_SEED = 20261022


def _probabilities(values):
    raw = np.asarray(values)
    if (raw.dtype.kind not in 'iuf' or raw.ndim != 2 or raw.shape[1] != len(LABELS)
            or not np.isfinite(raw).all() or np.any(raw < 0) or np.any(raw > 1)
            or not np.allclose(raw.sum(axis=1), 1, rtol=1e-6, atol=1e-6)):
        raise ValueError('probabilities must be finite normalized [N,8] numeric probabilities')
    return raw.astype(np.float64)


def _population(split, probabilities, *, role, labels='label'):
    probabilities = _probabilities(probabilities)
    truth, groups, _ = _split(split, np.zeros(len(probabilities)), role=role, labels=labels)
    return truth, groups, probabilities


def _percentile(values):
    return [float(value) for value in np.percentile(values, [2.5, 97.5])]


def _macro_report(truth, predictions, groups, *, bootstrap):
    ids = np.unique(groups)
    result = {'value': macro_f1(truth, predictions, len(LABELS)) if len(truth) else None,
              'n': len(truth), 'n_groups': len(ids), 'ci95': None, 'reason': None,
              'average': 'classes with ground-truth support; absent true classes excluded',
              'bootstrap': {'unit': 'scenario group, all known variants',
                            'requested': bootstrap, 'valid': 0, 'seed': _SEED}}
    if len(ids) < 2:
        result['reason'] = 'empty selection' if not len(truth) else 'fewer than two scenario groups'
        return result
    inverse = np.searchsorted(ids, groups)
    rng, estimates = np.random.default_rng(_SEED), []
    for _ in range(bootstrap):
        frequency = np.bincount(rng.integers(0, len(ids), size=len(ids)), minlength=len(ids))
        repeats = frequency[inverse]
        estimates.append(macro_f1(np.repeat(truth, repeats), np.repeat(predictions, repeats), len(LABELS)))
    result['ci95'] = _percentile(estimates)
    result['bootstrap']['valid'] = bootstrap
    return result


def _closed(truth, groups, probabilities, *, bootstrap, row_indices=tuple(range(8))):
    predictions = probabilities.argmax(axis=1)
    matrix = confusion(truth, predictions, len(LABELS))
    return {'n': len(truth), 'n_groups': len(np.unique(groups)),
            'accuracy': rate(predictions == truth, groups, bootstrap=bootstrap),
            'macro_f1': _macro_report(truth, predictions, groups, bootstrap=bootstrap),
            'confusion': {'row_labels': [LABELS[i] for i in row_indices],
                          'column_labels': list(LABELS),
                          'counts': matrix[list(row_indices)].tolist(),
                          'denominator': 'all evaluated labelled scenes; no accepted-only filter'},
            'per_class': {LABELS[i]: {
                'n_true': int(np.sum(truth == i)), 'n_predicted': int(np.sum(predictions == i)),
                'recall': rate(predictions[truth == i] == i, groups[truth == i], bootstrap=bootstrap)}
                for i in row_indices}}


def _open_ranking(known, unknown, correct, known_groups, unknown_groups, *, bootstrap):
    ids = np.union1d(known_groups, unknown_groups)
    result = {**dict.fromkeys(_RANK_KEYS), 'n_known': len(known), 'n_unknown': len(unknown),
              'known_closed_accuracy': float(correct.mean()) if len(correct) else None,
              'ci95': None, 'reason': None,
              'bootstrap': {'unit': 'scenario group, paired known/unknown variants',
                            'n_groups': len(ids), 'requested': bootstrap, 'valid': 0, 'seed': _SEED},
              'conventions': {'score': 'U=1-max_k P(k)', 'positive_population': 'unknown',
                              'score_direction': 'higher_is_more_unknown_like',
                              'known_denominator': 'all known test scenes, including known interference',
                              'oscr_correctness': 'actual eight-class argmax matches the known label',
                              'ties': 'equal scores enter together; grouped endpoint OSCR interpolation'}}
    if not len(known) or not len(unknown):
        result['reason'] = 'ranking requires nonempty known and unknown populations'
        return result
    point = ranking_metrics(known, unknown, correct)
    # Curve arrays are available from the existing metric implementation; this
    # bounded report retains point metrics and intervals, not repeated curves.
    result.update({key: value for key, value in point.items() if key != 'curves'})
    if len(ids) < 2:
        result['reason'] = 'fewer than two scenario groups'
        return result
    ki, ui = np.searchsorted(ids, known_groups), np.searchsorted(ids, unknown_groups)
    rng, estimates = np.random.default_rng(_SEED), {key: [] for key in _RANK_KEYS}
    for _ in range(bootstrap):
        frequency = np.bincount(rng.integers(0, len(ids), size=len(ids)), minlength=len(ids))
        kr, ur = frequency[ki], frequency[ui]
        k, u = np.repeat(known, kr), np.repeat(unknown, ur)
        if not len(k) or not len(u):
            continue
        sample = ranking_metrics(k, u, np.repeat(correct, kr))
        for key in _RANK_KEYS:
            estimates[key].append(sample[key])
    valid = len(estimates[_RANK_KEYS[0]])
    result['bootstrap']['valid'] = valid
    if valid:
        result['ci95'] = {key: _percentile(values) for key, values in estimates.items()}
    else:
        result['reason'] = 'no bootstrap draw retained both populations'
    return result


def classifier_report(known_split, known_probabilities, *, unknown_split=None,
                      unknown_probabilities=None, matched_split=None,
                      matched_probabilities=None, bootstrap=200):
    """Describe the frozen eight-class predictor; no operating U threshold is fit.

    Known/test-only rows are in the frozen test role; matched rows are complete
    0/6/3 triples in test-matched with one frozen level bin per scenario. Empty
    selections return strict-JSON nulls plus counts. Argmax ties select the
    first class in P18 order. Conditional bootstrap holds the fitted model fixed.
    """
    bootstrap = _bootstrap_count(bootstrap)
    labels, groups, known = _population(known_split, known_probabilities, role='test')
    predictions = known.argmax(axis=1)
    correct, known_u = predictions == labels, 1 - known.max(axis=1)
    result = {'metric_protocol': 'B2-XGB-classifier/1', 'class_order': list(LABELS),
              'prediction_rule': 'first argmax in frozen P18 class order',
              'known': _closed(labels, groups, known, bootstrap=bootstrap),
              'unknown': {'score_definition': '1-max_k P(k)',
                          'operating_threshold': None,
                          'threshold_reason': 'descriptive MSP ranking only; no U operating threshold is fitted',
                          'families': {}, 'pooled_near': None},
              'matched': None,
              'binary_anomaly': {'score_definition': '1-P(clean)',
                                 'report_location': 'separate P26 binary score bundle'},
              'uncertainty': 'scenario bootstrap conditions on the fitted model; no training/calibration or physics uncertainty'}
    if unknown_split is None:
        if unknown_probabilities is not None:
            raise ValueError('unknown probabilities require an unknown split')
        families, ug, unknown = np.array([], dtype=int), np.array([], dtype=int), np.empty((0, 8))
    else:
        families, ug, unknown = _population(unknown_split, unknown_probabilities, role='test', labels='family')
        if tuple(unknown_split.get('families', TEST_FAMILIES)) != TEST_FAMILIES:
            raise ValueError('unknown family order must equal the frozen B2-test/1 order')
    unknown_u = 1 - unknown.max(axis=1)
    result['unknown']['n'] = len(unknown)
    for index, name in enumerate(TEST_FAMILIES):
        selected = families == index
        benign = name == 'cid_overlay'
        item = {'n': int(selected.sum()),
                'pre_registered_group': 'benign' if benign else 'near' if name in NEAR_UNKNOWN else 'equivalence_limited',
                'ranking': None if benign else _open_ranking(known_u, unknown_u[selected], correct,
                    groups, ug[selected], bootstrap=bootstrap),
                'reason': 'benign CID excluded from unknown-positive ranking' if benign else None}
        if benign:
            cid_predictions = unknown[selected].argmax(axis=1)
            item['predicted_clean'] = rate(cid_predictions == 0, ug[selected], bootstrap=bootstrap)
            item['carrier_under_carrier_calls'] = rate(
                cid_predictions == LABELS.index('carrier_under_carrier'), ug[selected], bootstrap=bootstrap)
        result['unknown']['families'][name] = item
    near = np.isin(families, [TEST_FAMILIES.index(name) for name in NEAR_UNKNOWN])
    result['unknown']['pooled_near'] = {'families': list(NEAR_UNKNOWN),
        'ranking': _open_ranking(known_u, unknown_u[near], correct, groups, ug[near], bootstrap=bootstrap),
        'exclusions': 'wideband_noise separate; benign cid_overlay excluded'}
    if matched_split is None:
        if matched_probabilities is not None:
            raise ValueError('matched probabilities require a matched split')
    else:
        truth, mg, matched = _population(matched_split, matched_probabilities, role='test-matched')
        bins = _vector(matched_split.get('matched_bin', []), 'matched_bin', kind='group')
        if bins.shape != truth.shape or np.any(bins < 0) or np.any(bins > 2):
            raise ValueError('matched bins must identify the three frozen K17c bins')
        for group in np.unique(mg):
            selected = mg == group
            if (len(truth[selected]) != 3 or set(truth[selected]) != {0, 3, 6}
                    or len(set(bins[selected])) != 1):
                raise ValueError('matched groups require complete clean/ASI/unauthorized triples in one frozen bin')
        result['matched'] = _closed(truth, mg, matched, bootstrap=bootstrap, row_indices=(0, 3, 6))
        result['matched']['per_bin'] = {name: _closed(truth[bins == index], mg[bins == index],
            matched[bins == index], bootstrap=bootstrap, row_indices=(0, 3, 6))
            for index, name in enumerate(BIN_NAMES)}
        result['matched']['limitation'] = 'classifier decisions are separate from paired P26 binary detection differences'
    return result

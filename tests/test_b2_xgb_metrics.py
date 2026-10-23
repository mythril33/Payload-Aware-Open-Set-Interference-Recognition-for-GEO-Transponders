"""Classifier metrics remain distinct from P26 binary anomaly metrics."""
import json
from copy import deepcopy

import numpy as np
import pytest

from geosim.b2_protocol import LABELS
from geosim.b2_scenarios import TEST_FAMILIES
from geoml.b2_xgb_metrics import classifier_report


def _known():
    labels = np.tile(np.arange(8), 2)
    groups = np.repeat([3200000, 3200001], 8)
    predictions = labels.copy()
    predictions[8:] = (predictions[8:] + 1) % 8
    probabilities = np.full((16, 8), .2 / 7)
    probabilities[np.arange(16), predictions] = .8
    return {'label': labels, 'seed': groups}, probabilities


def _unknown():
    return {'family': np.tile(np.arange(5), 2),
            'seed': np.repeat([3200000, 3200001], 5),
            'families': list(TEST_FAMILIES)}, np.full((10, 8), 1 / 8)


def test_closed_denominators_and_actual_correctness_control_oscr_with_paired_bootstrap():
    known, kp = _known()
    unknown, up = _unknown()
    result = classifier_report(known, kp, unknown_split=unknown, unknown_probabilities=up, bootstrap=200)
    closed = result['known']
    assert closed['accuracy']['count'] == 8 and closed['accuracy']['n'] == 16
    assert closed['accuracy']['rate'] == .5 and closed['accuracy']['ci95'] == [0, 1]
    assert closed['macro_f1']['value'] == .5 and closed['macro_f1']['ci95'] == [0, 1]
    assert np.asarray(closed['confusion']['counts']).sum() == 16
    for name in LABELS:
        assert closed['per_class'][name]['recall']['n'] == 2
        assert closed['per_class'][name]['recall']['count'] == 1
    pooled = result['unknown']['pooled_near']['ranking']
    assert pooled['n_known'] == 16 and pooled['n_unknown'] == 6
    assert pooled['unknown_auroc'] == pooled['unknown_aupr'] == 1
    assert pooled['oscr_auc'] == .5
    assert pooled['ci95']['oscr_auc'] == [0, 1]
    assert pooled['bootstrap']['unit'] == 'scenario group, paired known/unknown variants'
    assert result['unknown']['families']['wideband_noise']['ranking']['n_unknown'] == 2
    assert result['unknown']['families']['cid_overlay']['ranking'] is None
    assert result['unknown']['score_definition'] == '1-max_k P(k)'


def test_probability_ties_argmax_order_and_oscr_are_not_binary_alarm_accuracy():
    known, _ = _known()
    unknown, up = _unknown()
    result = classifier_report(known, np.full((16, 8), 1 / 8),
                               unknown_split=unknown, unknown_probabilities=up, bootstrap=20)
    assert result['known']['accuracy']['rate'] == 2 / 16
    ranking = result['unknown']['pooled_near']['ranking']
    assert ranking['unknown_auroc'] == .5
    assert ranking['unknown_aupr'] == pytest.approx(6 / 22)
    assert ranking['oscr_auc'] == 1 / 16
    cid = result['unknown']['families']['cid_overlay']
    assert cid['predicted_clean']['count'] == cid['predicted_clean']['n'] == 2
    assert cid['carrier_under_carrier_calls']['count'] == 0


def test_empty_and_one_group_populations_are_strict_json_nulls_with_counts():
    empty = classifier_report({'label': [], 'seed': []}, np.empty((0, 8)), bootstrap=10)
    assert empty['known']['accuracy']['rate'] is None
    assert empty['known']['macro_f1']['value'] is None
    assert empty['unknown']['pooled_near']['ranking']['oscr_auc'] is None
    assert empty['unknown']['pooled_near']['ranking']['n_known'] == 0
    json.dumps(empty, allow_nan=False)
    known = {'label': np.array([0]), 'seed': np.array([3200000])}
    unknown = {'family': np.array([0]), 'seed': np.array([3200000])}
    one = classifier_report(known, np.eye(8)[[0]], unknown_split=unknown,
                            unknown_probabilities=np.full((1, 8), 1 / 8), bootstrap=10)
    assert one['known']['accuracy']['ci95'] is None
    rank = one['unknown']['families']['pulsed']['ranking']
    assert rank['oscr_auc'] == 1 and rank['ci95'] is None
    assert rank['reason'] == 'fewer than two scenario groups'
    json.dumps(one, allow_nan=False)


def test_matched_class_report_keeps_all_three_variants_and_frozen_bins():
    known, kp = _known()
    labels = np.tile([0, 6, 3], 2)
    matched = {'label': labels, 'seed': np.repeat([3300000, 3300001], 3),
               'matched_bin': np.repeat([0, 1], 3)}
    result = classifier_report(known, kp, matched_split=matched,
                               matched_probabilities=np.eye(8)[labels], bootstrap=20)
    closed = result['matched']
    assert closed['accuracy']['count'] == closed['accuracy']['n'] == 6
    assert closed['confusion']['row_labels'] == ['clean', 'unauthorized', 'adjacent_satellite']
    assert np.shape(closed['confusion']['counts']) == (3, 8)
    assert closed['per_bin']['[4,7)']['n'] == 3
    assert closed['per_bin']['[4,7)']['accuracy']['ci95'] is None
    assert closed['per_bin']['[10,13]']['accuracy']['n'] == 0
    assert closed['per_bin']['[10,13]']['accuracy']['rate'] is None


@pytest.mark.parametrize('mutation', [
    lambda p: p.__setitem__((0, 0), np.nan),
    lambda p: p.__setitem__((0, 0), np.inf),
    lambda p: p.__setitem__((0, 0), -1.),
    lambda p: p.__setitem__((0, 0), 1.1),
    lambda p: p.__setitem__(0, np.zeros(8)),
])
def test_nonprobabilities_fail_closed(mutation):
    known, probabilities = _known()
    mutation(probabilities)
    with pytest.raises(ValueError, match='probabilit'):
        classifier_report(known, probabilities)


def test_roles_labels_family_order_and_duplicate_ids_fail_closed():
    known, kp = _known()
    for key, change in [('seed', 3000000), ('label', 8)]:
        altered = deepcopy(known)
        altered[key][0] = change
        with pytest.raises(ValueError):
            classifier_report(altered, kp)
    duplicate = deepcopy(known)
    duplicate['label'][1] = duplicate['label'][0]
    with pytest.raises(ValueError, match='duplicate'):
        classifier_report(duplicate, kp)
    unknown, up = _unknown()
    unknown['families'] = list(reversed(TEST_FAMILIES))
    with pytest.raises(ValueError, match='family order'):
        classifier_report(known, kp, unknown_split=unknown, unknown_probabilities=up)
    with pytest.raises(ValueError, match='probabilit'):
        classifier_report(known, kp[:, :7])
    with pytest.raises(ValueError):
        classifier_report(known, kp, unknown_probabilities=up)
    with pytest.raises(ValueError):
        classifier_report(known, kp, unknown_split=_unknown()[0])


def test_matched_incomplete_or_inconsistent_pairing_is_rejected():
    known, kp = _known()
    matched = {'label': np.array([0, 6, 3]), 'seed': np.repeat(3300000, 3),
               'matched_bin': np.array([0, 1, 0])}
    with pytest.raises(ValueError, match='matched'):
        classifier_report(known, kp, matched_split=matched,
                           matched_probabilities=np.eye(8)[[0, 6, 3]])
    matched = {'label': np.array([0, 6]), 'seed': np.repeat(3300000, 2),
               'matched_bin': np.array([0, 0])}
    with pytest.raises(ValueError, match='matched'):
        classifier_report(known, kp, matched_split=matched,
                           matched_probabilities=np.eye(8)[[0, 6]])


def test_bootstrap_is_deterministic_and_bool_counts_are_not_configuration():
    known, kp = _known()
    unknown, up = _unknown()
    kwargs = dict(unknown_split=unknown, unknown_probabilities=up, bootstrap=40)
    assert classifier_report(known, kp, **kwargs) == classifier_report(known, kp, **kwargs)
    for invalid in (0, True, 2001):
        with pytest.raises(ValueError, match='bootstrap'):
            classifier_report(known, kp, bootstrap=invalid)

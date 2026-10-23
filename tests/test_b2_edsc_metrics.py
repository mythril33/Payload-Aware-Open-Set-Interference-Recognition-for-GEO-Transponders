"""Binary EDSC reporting conventions and paired uncertainty; no RF inference claims."""
from copy import deepcopy
import json

import numpy as np
import pytest

from geoml.b2_edsc_metrics import compare_score_bundles, evaluate_binary, ranking, rate
from geosim.b2_protocol import LABELS
from geosim.b2_scenarios import TEST_FAMILIES


def test_rate_counts_empty_and_whole_scenario_bootstrap():
    result = rate(np.array([False, False, True, True]), [1, 1, 2, 2], bootstrap=100)
    assert (result['count'], result['n'], result['rate']) == (2, 4, .5)
    assert result['ci95'] == [0., 1.]
    assert rate(np.array([], dtype=bool), [], bootstrap=20)['rate'] is None
    assert rate(np.array([True]), [1], bootstrap=20)['ci95'] is None
    with pytest.raises(ValueError, match='boolean'):
        rate([0, 1], [1, 2])
    with pytest.raises(ValueError, match='bootstrap'):
        rate([True], [1], bootstrap=0)


def test_ranking_ties_counts_empty_and_group_correlation():
    result = ranking([0, 0], [1, 1], [1, 2], [1, 2], bootstrap=100)
    assert result['unknown_auroc'] == result['unknown_aupr'] == 1.
    assert result['unknown_fpr_at_95_tpr'] == 0.
    assert result['ci95']['unknown_auroc'] == [1., 1.]
    tied = ranking([0, 0], [0, 0], [1, 2], [1, 2], bootstrap=20)
    assert tied['unknown_auroc'] == tied['unknown_aupr'] == .5
    assert tied['unknown_fpr_at_95_tpr'] == 1.
    empty = ranking([0], [], [1], [], bootstrap=20)
    assert empty['unknown_auroc'] is None and empty['n_unknown'] == 0
    correlated = ranking([0, 1], [1, 0], [1, 2], [1, 2], bootstrap=100)
    assert correlated['ci95']['unknown_auroc'] == [0., 1.]
    assert 'oscr_auc' not in result
    with pytest.raises(ValueError, match='finite'):
        ranking([0], [np.nan], [1], [1])


def splits():
    known = {'label':np.tile(np.arange(8), 2), 'seed':np.repeat([3200000, 3200001], 8),
             'meta':[{} for _ in range(16)]}
    unknown = {'family':np.tile(np.arange(5), 2), 'families':list(TEST_FAMILIES),
               'seed':np.repeat([3200000, 3200001], 5)}
    matched = {'label':np.tile([0, 6, 3], 2), 'seed':np.repeat([3300000, 3300001], 3),
               'matched_bin':np.repeat([0, 1], 3), 'meta':[{} for _ in range(6)]}
    return known, unknown, matched


def test_binary_evaluation_excludes_benign_and_equivalence_from_near_pool():
    known, unknown, matched = splits()
    report = evaluate_binary(known, np.tile(np.arange(8), 2), 2., unknown_split=unknown,
                             unknown_scores=np.full(10, 10.), matched_split=matched,
                             matched_scores=[0, 0, 4, 0, 4, 0], bootstrap=30)
    assert report['known']['clean_false_alarm']['n'] == 2
    assert report['known']['event_detection']['count'] == 10
    assert report['unknown']['pooled_near']['ranking']['n_unknown'] == 6
    assert report['unknown']['families']['cid_overlay']['ranking'] is None
    assert report['unknown']['families']['cid_overlay']['alarm']['count'] == 2
    assert report['unknown']['families']['wideband_noise']['ranking']['n_unknown'] == 2
    assert report['matched']['pair']['n_pairs'] == 2
    assert report['matched']['pair']['difference_unauthorized_minus_asi']['mean'] == 0.
    assert report['matched']['pair']['difference_unauthorized_minus_asi']['ci95'] == [-1., 1.]
    assert report['matched']['per_bin']['[4,7)']['pair']['n_pairs'] == 1
    assert report['matched']['per_bin']['[10,13]']['pair']['n_pairs'] == 0
    for key in ('multiclass_accuracy', 'oscr_auc', 'class_predictions'):
        assert report['unsupported'][key] is None
    json.dumps(report, allow_nan=False)


def test_matched_pair_integrity_rejects_missing_duplicate_or_bin_disagreement():
    known, _, matched = splits()
    for change in ('missing', 'duplicate', 'bin'):
        broken = deepcopy(matched)
        if change == 'missing':
            broken = {k:v[:-1] for k,v in broken.items()}
        elif change == 'duplicate':
            broken['label'][-1] = 6
        else:
            broken['matched_bin'][-1] = 0
        with pytest.raises(ValueError, match='matched'):
            evaluate_binary(known, np.zeros(16), 0., matched_split=broken,
                            matched_scores=np.zeros(len(broken['label'])))


def test_operating_bins_are_reporting_only_fixed_edges_and_missing_counts():
    known, _, _ = splits()
    for i in (7, 15):
        known['meta'][i] = {'event': {'c_over_i_db':25. if i == 7 else 30.}}
    report = evaluate_binary(known, np.tile(np.arange(8), 2), 2., bootstrap=20)
    cuc = report['known']['operating_conditions']['carrier_under_carrier']['c_over_i_db']
    assert cuc['bins']['[25,30]']['n'] == 2
    assert cuc['n_missing'] == 0
    assert report['unknown']['pooled_near']['ranking']['unknown_auroc'] is None
    assert report['matched'] is None


def bundle(method='EDSC'):
    return {'method':method, 'scorer_identity':'fingerprint-'+method,
            'score_direction':'higher_is_more_anomalous',
            'evaluation_identity':{'known':'a', 'unknown':None, 'matched':None},
            'sample_ids':{'known':[[3200000,0]], 'unknown':[], 'matched':[]},
            'calibration':{'population':'clean-only val-calib', 'nominal_pfa':.05,
              'rule':'quantile_higher_0.95_strict_gt', 'data_identity':'a',
              'sample_ids':[[3150000,0],[3150001,0]], 'threshold':0.},
            'metrics':evaluate_binary({'label':np.array([0]),'seed':np.array([3200000])},
                                      [0.], 0., bootstrap=5)}


def test_fair_comparison_accepts_distinct_thresholds_rejects_population_and_identity_changes():
    a, b = bundle(), bundle('CA-CFAR')
    b['calibration']['threshold'] = 10.
    b['metrics']['threshold'] = 10.
    assert set(compare_score_bundles([a,b])) == {'EDSC','CA-CFAR'}
    for field, value in [('score_direction','lower'), ('evaluation_identity',{'known':'wrong'}),
                         ('sample_ids',{'known':[[3200001,0]]})]:
        bad = deepcopy(b)
        bad[field] = value
        with pytest.raises(ValueError, match='compar'):
            compare_score_bundles([a,bad])
    for field, value in [('population','all-known val-calib'), ('nominal_pfa',.1),
                         ('rule','95pct_known_acceptance'), ('sample_ids',[[3200000,0]])]:
        bad = deepcopy(b)
        bad['calibration'][field] = value
        with pytest.raises(ValueError, match='compar'):
            compare_score_bundles([a,bad])


def test_comparison_rejects_matching_but_invalid_sample_population_and_thresholds():
    for mutate in (
        lambda x:x['sample_ids'].update(known=[[3150000,0]]),
        lambda x:x['sample_ids'].update(known=[[3200000,0],[3200000,0]]),
        lambda x:x['calibration'].update(sample_ids=[[3150000,False],[3150001,0]]),
        lambda x:x['calibration'].update(calibration_groups=[3150000,3150002]),
        lambda x:x['calibration'].update(threshold=float('nan')),
        lambda x:x['calibration'].update(threshold=True),
    ):
        a, b = bundle(), bundle('neural_energy')
        mutate(a)
        mutate(b)
        with pytest.raises(ValueError, match='compar'):
            compare_score_bundles([a,b])


def test_rate_missing_bootstrap_populations_are_counted_without_nonfinite_json():
    result = ranking([0.], [1.], [1], [2], bootstrap=100)
    assert 0 < result['bootstrap']['valid'] < 100
    assert result['ci95']['unknown_auroc'] == [1.,1.]
    json.dumps(result, allow_nan=False)


def test_operational_threshold_is_strict_and_distinct_from_unknown_ranking():
    known, unknown, _ = splits()
    result = evaluate_binary(known, np.ones(16), 1., unknown_split=unknown,
                             unknown_scores=np.ones(10), bootstrap=20)
    assert result['known']['clean_false_alarm']['count'] == 0
    assert result['known']['event_detection']['count'] == 0
    assert result['unknown']['pooled_near']['alarm']['count'] == 0
    assert result['unknown']['pooled_near']['ranking']['unknown_fpr_at_95_tpr'] == 1.
    assert result['unknown']['pooled_near']['ranking']['unknown_auroc'] == .5


def test_comparison_refuses_raw_classifier_metrics_and_mismatched_threshold_report():
    for metrics in ({'accuracy':.9,'oscr_auc':.8},
                    {**bundle()['metrics'], 'threshold':10.}):
        b = bundle('NN')
        b['metrics'] = metrics
        with pytest.raises(ValueError, match='compar'):
            compare_score_bundles([bundle(),b])


def test_comparison_requires_method_specific_scorer_identity_and_consistent_populations():
    for value in (None, '', '   ', 3):
        a = bundle()
        if value is None:
            del a['scorer_identity']
        else:
            a['scorer_identity'] = value
        with pytest.raises(ValueError, match='compar'):
            compare_score_bundles([a])
    a = bundle()
    a['metrics']['unknown']['families']['pulsed']['n'] = 1
    with pytest.raises(ValueError, match='compar'):
        compare_score_bundles([a])
    a = bundle()
    a['metrics']['unknown']['pooled_near']['ranking']['n_unknown'] = 1
    with pytest.raises(ValueError, match='compar'):
        compare_score_bundles([a])
    a = bundle()
    a['metrics']['matched'] = {'n_samples':3,'n_groups':1,'pair':{'n_pairs':1}}
    with pytest.raises(ValueError, match='compar'):
        compare_score_bundles([a])


def test_comparison_checks_populated_unknown_and_matched_counts_against_ids():
    known, unknown, matched = splits()
    a = bundle()
    a['evaluation_identity'].update(unknown='u', matched='m')
    a['sample_ids'] = {'known':np.column_stack((known['seed'],known['label'])).tolist(),
                       'unknown':np.column_stack((unknown['seed'],unknown['family'])).tolist(),
                       'matched':np.column_stack((matched['seed'],matched['label'])).tolist()}
    a['metrics'] = evaluate_binary(known, np.zeros(16), 0., unknown_split=unknown,
        unknown_scores=np.ones(10), matched_split=matched, matched_scores=np.ones(6), bootstrap=5)
    assert compare_score_bundles([a])['EDSC']['matched']['pair']['n_pairs'] == 2
    for section, field in [('unknown','families'),('matched','n_samples')]:
        bad = deepcopy(a)
        if section == 'unknown':
            bad['metrics'][section][field]['pulsed']['ranking']['n_unknown'] = 99
        else:
            bad['metrics'][section][field] = 99
        with pytest.raises(ValueError, match='compar'):
            compare_score_bundles([bad])

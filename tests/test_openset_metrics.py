"""Hand-computable ranking, classification and tied-threshold cases."""
import json

import numpy as np
import pytest

from geoml.openset_metrics import ranking_metrics


def test_perfect_ranking_and_classification_has_unit_auc_and_correct_anchors():
    result = ranking_metrics(np.array([-2., -1.]), np.array([1., 2.]), np.array([True, True]))
    assert result["unknown_auroc"] == 1
    assert result["unknown_aupr"] == 1
    assert result["oscr_auc"] == 1
    for curve in (result["curves"]["unknown_roc"], result["curves"]["oscr"]):
        x, y = curve.values()
        assert (x[0], y[0]) == (0, 0)
        assert (x[-1], y[-1]) == (1, 1)
    assert result["curves"]["unknown_pr"]["precision"][0] == 1
    assert result["curves"]["unknown_pr"]["recall"][0] == 0
    json.dumps(result, allow_nan=False)


def test_hand_computable_interleaved_ranking():
    result = ranking_metrics(np.array([0., 2.]), np.array([1., 3.]), np.array([True, True]))
    # Unknown outranks a known in three of four pairs. Unknown precisions at
    # recalls 1/2 and 1 are 1 and 2/3, respectively.
    assert result["unknown_auroc"] == pytest.approx(3 / 4)
    assert result["unknown_aupr"] == pytest.approx(5 / 6)
    assert result["oscr_auc"] == pytest.approx(3 / 4)


def test_oscr_penalizes_incorrect_known_predictions_without_changing_roc():
    perfect = ranking_metrics(np.array([0., 2.]), np.array([1., 3.]), np.array([True, True]))
    imperfect = ranking_metrics(np.array([0., 2.]), np.array([1., 3.]), np.array([True, False]))
    assert imperfect["unknown_auroc"] == perfect["unknown_auroc"]
    assert imperfect["unknown_aupr"] == perfect["unknown_aupr"]
    assert imperfect["oscr_auc"] == pytest.approx(1 / 2)
    assert imperfect["curves"]["oscr"]["known_correct_acceptance"][-1] == 0.5
    none_correct = ranking_metrics(np.array([0., 2.]), np.array([1., 3.]), np.array([False, False]))
    assert none_correct["oscr_auc"] == 0


def test_all_ties_have_half_credit_roc_prevalence_ap_and_scaled_oscr():
    result = ranking_metrics(np.ones(3), np.ones(2), np.array([True, False, True]))
    assert result["unknown_auroc"] == pytest.approx(0.5)
    assert result["unknown_aupr"] == pytest.approx(2 / 5)
    assert result["oscr_auc"] == pytest.approx(1 / 3)
    assert result["curves"]["unknown_roc"] == {"fpr": [0., 1.], "tpr": [0., 1.]}
    assert result["curves"]["oscr"] == {"unknown_false_acceptance": [0., 1.],
                                          "known_correct_acceptance": [0., 2 / 3]}


def test_mixed_ties_group_before_integrating_and_ignore_sample_order():
    # Pairwise ROC credit is (1 + 1/2 + 1)/4 = 5/8. At descending score
    # 2: TP=1 FP=1; score 1 adds the other TP; score 0 adds the other FP.
    known = np.array([0., 2.])
    unknown = np.array([1., 2.])
    correct = np.array([True, False])
    result = ranking_metrics(known, unknown, correct)
    assert result["unknown_auroc"] == pytest.approx(5 / 8)
    assert result["unknown_aupr"] == pytest.approx(7 / 12)
    assert result["oscr_auc"] == pytest.approx(1 / 2)
    reversed_result = ranking_metrics(known[::-1], unknown[::-1], correct[::-1])
    assert reversed_result == result
    assert result["curves"]["unknown_roc"] == {"fpr": [0., .5, .5, 1.], "tpr": [0., .5, 1., 1.]}


def test_reversed_separation_is_not_silently_flipped_to_good_scores():
    result = ranking_metrics(np.array([2., 3.]), np.array([0., 1.]), np.array([True, True]))
    assert result["unknown_auroc"] == 0
    assert result["oscr_auc"] == 0
    assert result["unknown_aupr"] == pytest.approx((1 / 3 + 2 / 4) / 2)


def test_metric_invariance_to_joint_monotonic_score_transformation():
    known = np.array([-10., 2., 2., 9.])
    unknown = np.array([1., 2., 20.])
    correct = np.array([True, False, True, True])
    result = ranking_metrics(known, unknown, correct)
    shifted = ranking_metrics(known * 3 + 200, unknown * 3 + 200, correct)
    assert result == shifted


@pytest.mark.parametrize("bad", [[], [np.nan], [np.inf], [[1., 2.]], [1 + 2j], ["1"], [True]])
def test_rejects_invalid_known_or_unknown_score_vectors(bad):
    with pytest.raises(ValueError):
        ranking_metrics(np.asarray(bad), np.array([1.]), np.array([True]))
    with pytest.raises(ValueError):
        ranking_metrics(np.array([1.]), np.asarray(bad), np.array([True]))


@pytest.mark.parametrize("correct", [np.array([1, 0]), np.array([1., 0.]), np.array([True]),
                                    np.array([[True, False]]), np.array(["yes", "no"])])
def test_correctness_requires_one_boolean_per_known_event(correct):
    with pytest.raises(ValueError, match="known_correct"):
        ranking_metrics(np.array([0., 1.]), np.array([2.]), correct)

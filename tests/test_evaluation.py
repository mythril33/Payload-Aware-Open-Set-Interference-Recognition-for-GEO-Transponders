"""Check actual acceptance/rejection decisions and metric denominators."""
import json

import numpy as np
import pytest

from geoml.calibration import RejectionCalibration
from geoml.evaluation import evaluate


def test_decisions_use_frozen_threshold_and_report_conditional_accuracy():
    calibration = RejectionCalibration("msp", 0.2, 0.95, 10)
    # Correct accepted, wrong accepted, correct rejected. Unknowns both rejected.
    known = np.array([[5., 0.], [0., 5.], [0.1, 0.]])
    unknown = np.zeros((2, 2))
    result = evaluate(known, unknown, np.array([0, 0, 0]), np.array([1, 2, 3]), np.array([4, 5]), calibration)
    assert result["known_acceptance"]["mean"] == pytest.approx(2 / 3)
    assert result["known_closed_accuracy"]["mean"] == pytest.approx(2 / 3)
    assert result["accepted_known_accuracy"]["mean"] == pytest.approx(1 / 2)
    assert result["accepted_known_accuracy"]["n_samples"] == 2
    assert result["known_correct_acceptance"]["mean"] == pytest.approx(1 / 3)
    assert result["unknown_rejection"]["mean"] == 1
    assert result["false_alarm_on_clean"]["mean"] == pytest.approx(2 / 3)


def test_no_accepted_knowns_yields_explicit_missing_accuracy_and_strict_json():
    result = evaluate(np.zeros((2, 2)), np.zeros((2, 2)), np.array([0, 1]),
                      np.array([1, 2]), np.array([3, 4]), RejectionCalibration("msp", 0., 0.95, 2))
    assert result["accepted_known_accuracy"] == {"mean": None, "ci95": None, "n_samples": 0, "n_scenarios": 0}
    assert result["known_macro_f1_after_rejection"] == 0
    json.dumps(result, allow_nan=False)


def test_known_and_unknown_class_order_must_have_same_size():
    with pytest.raises(ValueError, match="same class order"):
        evaluate(np.zeros((2, 2)), np.zeros((2, 3)), np.array([0, 1]),
                 np.array([1, 2]), np.array([3, 4]), RejectionCalibration("msp", 0.4, 0.95, 2))

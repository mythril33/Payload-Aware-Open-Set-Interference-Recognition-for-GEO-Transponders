"""Numerical and serialization contracts for known-validation rejection."""
import json
from dataclasses import FrozenInstanceError

import numpy as np
import pytest

from geoml.calibration import RejectionCalibration, calibrate, calibrate_scores
from geoml.openset import unknown_scores


def test_uncertain_logits_have_larger_unknown_scores():
    logits = np.array([[8.0, -8.0, -8.0], [0.0, 0.0, 0.0]])
    msp = unknown_scores(logits, "msp")
    energy = unknown_scores(logits, "energy")
    assert msp[0] < msp[1] == pytest.approx(2 / 3)
    assert energy[0] < energy[1] == pytest.approx(-np.log(3))
    assert energy[0] == pytest.approx(-8 - np.log1p(2 * np.exp(-16)))


def test_logits_shift_affects_energy_but_not_msp():
    logits = np.array([[4.0, 1.0], [-2.0, 0.0]])
    np.testing.assert_allclose(unknown_scores(logits + 20, "msp"), unknown_scores(logits, "msp"))
    np.testing.assert_allclose(unknown_scores(logits + 20, "energy"), unknown_scores(logits, "energy") - 20)


def test_temperature_and_extreme_logits_are_stable():
    logits = np.array([[1e300, -1e300], [-1e300, -1e300], [1e4, 1e4]])
    for method in ("msp", "energy"):
        for temperature in (1e-300, 1.0, 100.0):
            assert np.isfinite(unknown_scores(logits, method, temperature)).all()
    logits = np.array([[2.0, 0.0]])
    assert unknown_scores(logits, "msp", 2.0)[0] == pytest.approx(1 / (1 + np.e))
    assert unknown_scores(logits, "energy", 2.0)[0] == pytest.approx(-2 * np.log(np.e + 1))


@pytest.mark.parametrize("method", ["msp", "energy"])
def test_known_calibration_target_threshold_and_ties(method):
    logits = np.column_stack([np.linspace(0, 5, 10), np.zeros(10)])
    result = calibrate(logits, method, target_acceptance=0.8, provenance="known-val-fingerprint")
    scores = unknown_scores(logits, method)
    assert result.accept(scores).mean() >= 0.8
    assert result.threshold == np.sort(scores)[8]
    tied = calibrate(np.zeros((4, 3)), method, target_acceptance=0.2)
    assert tied.accept(unknown_scores(np.zeros((4, 3)), method)).all()
    assert tied.accept(np.array([tied.threshold]))[0]


def test_calibration_roundtrip_and_unknown_decision(tmp_path):
    known = np.array([[5.0, 0.0], [6.0, 0.0], [7.0, 0.0]])
    calibration = calibrate(known, "msp", target_acceptance=1.0, provenance="known-only-validation")
    calibration.save(tmp_path / "calibration.json")
    restored = RejectionCalibration.load(tmp_path / "calibration.json")
    assert restored == calibration
    assert json.loads((tmp_path / "calibration.json").read_text()) == calibration.to_dict()
    np.testing.assert_array_equal(restored.accept(unknown_scores(np.array([[9.0, 0.0], [0.0, 0.0]]), "msp")),
                                  [True, False])
    with pytest.raises(FrozenInstanceError):
        restored.threshold = 0


@pytest.mark.parametrize("logits", [np.zeros((0, 2)), np.zeros((2, 1)), np.zeros(3),
                                    [[np.nan, 0]], [[np.inf, 0]], [[1j, 0]], [["1", "2"]]])
def test_invalid_logits_fail(logits):
    with pytest.raises(ValueError):
        unknown_scores(logits, "msp")


@pytest.mark.parametrize("temperature", [0, -1, np.nan, np.inf, True, "1"])
def test_invalid_temperature_fails(temperature):
    with pytest.raises(ValueError):
        unknown_scores([[1.0, 0.0]], "energy", temperature)


@pytest.mark.parametrize("target", [0, -0.1, 1.1, np.inf, np.nan, True, "0.9"])
def test_invalid_acceptance_fails(target):
    with pytest.raises(ValueError):
        calibrate([[1.0, 0.0]], "msp", target)


def test_unknown_method_and_invalid_serialized_calibration_fail():
    with pytest.raises(ValueError, match="method"):
        unknown_scores([[1.0, 0.0]], "entropy")
    base = calibrate([[1.0, 0.0]], "msp").to_dict()
    for key, bad in [("threshold", np.nan), ("threshold", -1), ("n_calibration", 0),
                     ("n_calibration", 1.0), ("provenance", 123)]:
        with pytest.raises(ValueError):
            RejectionCalibration.from_dict({**base, key: bad})
    with pytest.raises(ValueError):
        RejectionCalibration.from_dict({**base, "extra": 1})
    del base["temperature"]
    with pytest.raises(ValueError):
        RejectionCalibration.from_dict(base)


def test_accept_rejects_invalid_or_mismatched_score_arrays():
    c = calibrate([[2.0, 0.0]], "msp")
    for scores in ([np.nan], [[0.1]], ["0.1"], [-0.1], [1.1]):
        with pytest.raises(ValueError):
            c.accept(scores)


def test_precomputed_distances_calibrate_without_logit_or_unknown_inputs(tmp_path):
    calibration = calibrate_scores(np.array([1., 3., 2., 4.]), "mahalanobis", 0.5, provenance="known-calibration")
    assert calibration.threshold == 3
    np.testing.assert_array_equal(calibration.accept(np.array([0., 3., 10.])), [True, True, False])
    calibration.save(tmp_path / "distance.json")
    assert RejectionCalibration.load(tmp_path / "distance.json") == calibration
    with pytest.raises(ValueError, match="temperature"):
        calibrate_scores(np.array([1., 2.]), "mahalanobis", temperature=2)
    with pytest.raises(ValueError, match="nonnegative"):
        calibrate_scores(np.array([-1., 2.]), "mahalanobis")


@pytest.mark.parametrize("scores", [[], [np.nan], [[1.]], ["1"]])
def test_invalid_precomputed_calibration_scores_fail(scores):
    with pytest.raises(ValueError, match="scores"):
        calibrate_scores(scores, "energy")

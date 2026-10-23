"""Hand-computable EDSC scoring and adversarial clean-only calibration tests."""
import inspect
import json

import numpy as np
import pytest

from geoml.edsc import calibrate_clean, residual_energy


def observations(n=2):
    spec = np.full((n, 2, 128, 512), -70.0)
    mask = np.full((n, 2, 512), -60.0)
    mask[:, :, 240:273] = 0.0
    spec[:, 0, :, 240:273] = -50.0
    residual = np.full((n, 128, 512), -80.0)
    return spec, mask, residual


def test_statistic_uses_linear_power_averaging_and_observed_carrier_reference():
    spec, mask, residual = observations()
    residual[1, :64] = -70
    result = residual_energy(spec, mask, residual)
    expected = 10 * np.log10((10.0 ** -8 + 10.0 ** -7) / 2) + 50
    assert result["score_db"].tolist() == pytest.approx([-30, expected])
    assert result["reference_db"].tolist() == pytest.approx([-50, -50])
    assert set(result) == {"score_db", "planned_db", "unplanned_db", "reference_db"}
    for key in ("planned_db", "unplanned_db"):
        assert result[key].tolist() == pytest.approx(result["score_db"].tolist())


def test_residual_increase_is_monotone_and_common_gain_cancels_without_clipping():
    spec, mask, residual = observations()
    base = residual_energy(spec, mask, residual)["score_db"]
    residual[1] += 17.25
    elevated = residual_energy(spec, mask, residual)["score_db"]
    assert elevated.tolist() == pytest.approx([base[0], base[1] + 17.25])
    shifted = residual_energy(spec + 125, mask, residual + 125)["score_db"]
    assert shifted.tolist() == pytest.approx(elevated.tolist())


def test_ignores_out_of_band_energy_cross_pol_and_truth_not_in_signature():
    spec, mask, residual = observations()
    base = residual_energy(spec, mask, residual)
    residual[:, :, :100] += 100
    spec[:, 1] += 100
    changed = residual_energy(spec, mask, residual)
    assert np.array_equal(changed["score_db"], base["score_db"])
    assert tuple(inspect.signature(residual_energy).parameters) == ("spec_db", "mask_db", "residual_db")
    with pytest.raises(TypeError):
        residual_energy(spec, mask, residual, activity=np.ones(2))


@pytest.mark.parametrize("case", ["empty", "missing", "shape", "nan", "infinite", "bool", "no_core", "no_gap", "overflow", "underflow"])
def test_rejects_invalid_observations_and_normalization(case):
    spec, mask, residual = observations()
    if case == "empty":
        spec, mask, residual = spec[:0], mask[:0], residual[:0]
    elif case == "missing":
        residual = None
    elif case == "shape":
        residual = residual[:, :127]
    elif case == "nan":
        residual[0, 0, 0] = np.nan
    elif case == "infinite":
        spec[0, 0, 0, 0] = np.inf
    elif case == "bool":
        mask = mask.astype(bool)
    elif case == "no_core":
        mask[:] = -60
    elif case == "no_gap":
        mask[:] = 0
    elif case == "overflow":
        spec[:] = 10000
    elif case == "underflow":
        spec[:] = -10000
    with pytest.raises(ValueError):
        residual_energy(spec, mask, residual)


def test_threshold_is_clean_only_deterministic_higher_quantile_strict_alarm_json():
    scores = np.array([1., 1000., 2., -1000.])
    labels = np.array([0, 1, 0, 1])
    groups = np.array([3150000, 3150000, 3150001, 3150001])
    result = calibrate_clean(scores, labels, groups, role="val-calib", provenance="abc")
    assert result["threshold"] == 2
    assert result["nominal_pfa"] == .05
    assert result["n_calibration"] == 2
    assert result["false_alarm_count"] == 0 and result["false_alarm_rate"] == 0
    assert result["empirical_resolution"] == .5
    assert result["small_population"] is True
    assert result["comparison"] == ">"
    assert json.loads(json.dumps(result, allow_nan=False)) == result
    assert result == calibrate_clean(scores[::-1], labels[::-1], groups[::-1], role="val-calib", provenance="abc")
    scores[labels != 0] *= 1e20
    assert result == calibrate_clean(scores, labels, groups, role="val-calib", provenance="abc")


def test_exact_twenty_clean_threshold_ties_and_observed_false_alarm_counts():
    scores = np.arange(20.)
    groups = np.arange(3150000, 3150020)
    labels = np.zeros(20, dtype=int)
    result = calibrate_clean(scores, labels, groups, role="val-calib", provenance="abc")
    # NumPy's higher empirical quantile uses ceil((n-1)*.95), not a population Pfa guarantee.
    assert result["threshold"] == 19 and result["false_alarm_count"] == 0
    assert result["small_population"] is False
    result = calibrate_clean(np.ones(20), labels, groups, role="val-calib", provenance="abc")
    assert result["false_alarm_count"] == 0


@pytest.mark.parametrize("case", ["train", "test", "test-matched", "wrong_group", "fractional_group", "family", "missing_clean", "one_clean", "duplicate", "nan", "empty", "provenance"])
def test_calibration_rejects_roles_unknowns_duplicates_and_insufficient_clean(case):
    scores = np.array([1., 2.])
    labels = np.zeros(2, dtype=int)
    groups = np.array([3150000, 3150001])
    role, provenance = "val-calib", "abc"
    if case in ("train", "test", "test-matched"):
        role = case
    elif case == "wrong_group":
        groups[1] = 3200000
    elif case == "fractional_group":
        groups = groups.astype(float)
    elif case == "family":
        labels[1] = 8
    elif case == "missing_clean":
        labels[:] = 1
    elif case == "one_clean":
        labels[1] = 1
    elif case == "duplicate":
        groups[1] = groups[0]
    elif case == "nan":
        scores[1] = np.nan
    elif case == "empty":
        scores, labels, groups = scores[:0], labels[:0], groups[:0]
    elif case == "provenance":
        provenance = ""
    with pytest.raises(ValueError):
        calibrate_clean(scores, labels, groups, role=role, provenance=provenance)

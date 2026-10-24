"""E10 regression tests for the approved R10 clean-alarm threshold (higher empirical quantile).

CPU-only, synthetic score vectors. No held-out observation, checkpoint or artifact is read. The historical
linear-quantile helper is tested too, so that frozen stages keep their meaning and cannot be relabelled.
"""
import ast
import inspect
import textwrap

import numpy as np
import pytest

from geoml import b2_execution as execution
from geoml import b2_stream
from geoml.calibration import calibrate_scores
from geoml.metrics import CLEAN_ALARM_QUANTILE_METHOD, clean_alarm_threshold, threshold_at_pfa
from geoml.train import TrainConfig


# ---- the approved quantile rule, with hand-computed values ----------------------------------------------

def test_method_is_the_approved_higher_quantile():
    assert CLEAN_ALARM_QUANTILE_METHOD == "higher"


def test_higher_quantile_hand_value_on_0_to_99():
    # n = 100, level 0.95: higher index = ceil(0.95 * 99) = ceil(94.05) = 95 -> value 95.0
    assert clean_alarm_threshold(np.arange(100.0), 0.05) == 95.0


def test_historical_linear_helper_is_unchanged_and_differs_from_the_approved_rule():
    # Linear interpolation: 0.95 * 99 = 94.05 -> 94.05. This is the archived behaviour; it must not change.
    assert threshold_at_pfa(np.arange(100.0), 0.05) == pytest.approx(94.05)
    assert threshold_at_pfa(np.arange(100.0), 0.05) != clean_alarm_threshold(np.arange(100.0), 0.05)


def test_threshold_is_an_order_statistic_of_the_calibration_scores():
    rng = np.random.default_rng(12345)
    scores = rng.normal(size=137)
    value = clean_alarm_threshold(scores, 0.05)
    assert value in set(scores.tolist())            # higher quantile never interpolates between samples
    assert np.mean(scores > value) <= 0.05 + 1e-12  # strict alarm rate on the calibration set does not exceed Pfa


def test_threshold_is_non_increasing_in_pfa():
    scores = np.random.default_rng(7).uniform(size=500)
    levels = [clean_alarm_threshold(scores, pfa) for pfa in (0.5, 0.2, 0.05, 0.01)]
    assert levels == sorted(levels)


# ---- ties, small samples ---------------------------------------------------------------------------------

def test_equal_scores_give_that_score_and_strict_alarm_never_fires_on_ties():
    scores = np.full(10, 0.5)
    threshold = clean_alarm_threshold(scores, 0.05)
    assert threshold == 0.5
    assert int(np.sum(scores > threshold)) == 0    # strict '>' : ties at the threshold are not alarms


def test_plateau_at_the_threshold_is_not_an_alarm():
    scores = np.array([0.0, 0.0, 0.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0])
    threshold = clean_alarm_threshold(scores, 0.2)  # index ceil(0.8 * 9) = 8 -> 1.0
    assert threshold == 1.0
    assert int(np.sum(scores > threshold)) == 0


@pytest.mark.parametrize("n, expected_index", [(1, 0), (2, 1), (20, 19)])
def test_small_samples_use_the_largest_value_at_the_higher_index(n, expected_index):
    scores = np.arange(float(n))
    assert clean_alarm_threshold(scores, 0.05) == float(expected_index)


def test_order_of_inputs_does_not_matter():
    scores = np.random.default_rng(3).normal(size=60)
    assert clean_alarm_threshold(scores, 0.05) == clean_alarm_threshold(scores[::-1], 0.05)


# ---- finite inputs and parameter bounds fail closed ---------------------------------------------------

@pytest.mark.parametrize("bad", [
    np.array([]),
    np.zeros((3, 2)),
    np.array([0.1, np.nan, 0.3]),
    np.array([0.1, np.inf]),
    np.array([0.1, -np.inf]),
], ids=["empty", "two-dimensional", "nan", "+inf", "-inf"])
def test_invalid_score_vectors_are_refused(bad):
    with pytest.raises(ValueError):
        clean_alarm_threshold(bad, 0.05)


@pytest.mark.parametrize("pfa", [0.0, 1.0, -0.05, 1.5, float("nan"), True, "0.05", None])
def test_invalid_pfa_is_refused(pfa):
    with pytest.raises(ValueError):
        clean_alarm_threshold(np.arange(10.0), pfa)


# ---- the alarm score keeps its ordering for confidently clean samples -----------------------------------

def test_saturated_clean_margin_keeps_a_positive_score_and_its_ordering():
    # Clean logit 40 and 45 nats above the other classes. 1 - P(clean) by subtraction rounds to exactly 0.0 here.
    logits = np.array([[40.0, 0.0, 0.0], [45.0, 0.0, 0.0]])
    shifted = logits - logits.max(axis=1, keepdims=True)
    probabilities = np.exp(shifted) / np.exp(shifted).sum(axis=1, keepdims=True)
    assert np.all(1.-probabilities[:,0] == 0.0)                 # the historical subtraction saturates
    scores = execution.clean_alarm_score(probabilities)
    assert np.all(scores > 0.0)                                 # the non-clean sum still resolves the margin
    assert scores[1] < scores[0]                                # the larger clean margin has the smaller score
    assert scores[0] == pytest.approx(2*np.exp(-40.0)/(1+2*np.exp(-40.0)), rel=1e-12)


def test_both_alarm_call_sites_use_the_saturation_free_score():
    # The calibrate path and the evaluation path must score alarms with the same helper, never 1 - P(clean).
    for function in (execution.calibrate_b2_models, execution.evaluate_b2_inventory):
        source = inspect.getsource(function)
        assert "clean_alarm_score(" in source
        assert "1.-probabilities" not in source


# ---- distinct known-acceptance and clean-alarm thresholds ----------------------------------------------

def test_acceptance_and_clean_alarm_are_distinct_populations():
    # Clean scores are low; the other seven known classes are high. The rejection threshold is fitted on all
    # known scores, the clean-alarm threshold on clean scores only. They must not coincide.
    rng = np.random.default_rng(11)
    clean = rng.uniform(0.0, 0.4, size=150)
    others = rng.uniform(0.6, 1.0, size=150 * 7)
    rejection = calibrate_scores(np.concatenate([clean, others]), "msp", 0.95).threshold
    alarm = clean_alarm_threshold(clean, 0.05)
    assert alarm <= 0.4 < rejection


# ---- leakage: calibration and test data cannot enter optimizer fitting ---------------------------------

def _source(kind, role):
    source = object.__new__(b2_stream.B2Source)
    source.kind, source.role, source.has_residual = kind, role, True
    return source


def _config():
    return TrainConfig(labels=("clean", "cw", "swept_cw", "unauthorized", "overdrive", "cross_pol",
                               "adjacent_satellite", "carrier_under_carrier"))


@pytest.mark.parametrize("role", ["val-calib", "test", "test-matched"])
def test_training_refuses_calibration_and_evaluation_sources(role):
    kind = "test" if role == "test" else "matched" if role == "test-matched" else "known"
    with pytest.raises(ValueError):
        b2_stream._require(_source(kind, role), _config(), "training", "train")


def test_training_refuses_validation_as_training_data():
    with pytest.raises(ValueError):
        b2_stream._require(_source("known", "val-select"), _config(), "training", "train")


def test_training_accepts_only_the_train_role_known_source():
    source = _source("known", "train")
    source.index = {"label": np.zeros(4, dtype=int)}
    b2_stream._require(source, _config(), "training", "train")


def test_calibrate_path_opens_only_the_val_calib_role():
    body = textwrap.dedent(inspect.getsource(execution.calibrate_b2_models))
    calls = [node for node in ast.walk(ast.parse(body)) if isinstance(node, ast.Call)
             and getattr(node.func, "id", "") == "open_b2_known_roles"]
    assert len(calls) == 1
    role_arg = ast.literal_eval(calls[0].args[1])
    assert tuple(role_arg) == ("val-calib",)
    role_literals = {node.value for node in ast.walk(ast.parse(body))
                     if isinstance(node, ast.Constant) and isinstance(node.value, str)}
    assert not role_literals & {"test", "test-matched", "train", "val-select"}  # no other role on the calibrate path


def test_calibrate_path_uses_the_approved_threshold_not_the_historical_one():
    body = textwrap.dedent(inspect.getsource(execution.calibrate_b2_models))
    names = {node.id for node in ast.walk(ast.parse(body)) if isinstance(node, ast.Name)}
    assert "clean_alarm_threshold" in names
    assert "threshold_at_pfa" not in names


def test_alarm_rule_label_changed_so_historical_alarm_files_are_refused():
    historical = "P20 threshold_at_pfa; alarm strictly score > threshold"
    assert execution.ALARM_RULE != historical
    assert "R10" in execution.ALARM_RULE and "higher" in execution.ALARM_RULE

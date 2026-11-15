"""Tests for campaign 2 (scorer bench): new scores, OSCR and run_scorer_bench.

Unit tests use small hand-built arrays. The stage tests use a tiny Scale (the
pre-registered rule allows "quick scale or smaller" for tests), so the whole
file stays fast while every honesty property is still checked for real.
"""

from __future__ import annotations

import json
import math
from dataclasses import replace
from itertools import pairwise

import numpy as np
import pytest
import torch

from rfml import experiments as ex
from rfml.openset import (
    distance_unknown_score,
    energy_unknown_score,
    fit_shared_covariance,
    mahalanobis_unknown_score,
    maxlogit_unknown_score,
    msp_unknown_score,
)

TINY = ex.Scale(
    name="tiny",
    description="test only",
    tx_train=2,
    tx_val=2,
    tx_test=2,
    tx_aux=1,
    tx_unknown=1,
    frames_train=2,
    frames_val=2,
    frames_test=2,
    fp_devices=2,
    fp_frames=10,
    epochs=1,
)
SEED = 4


@pytest.fixture(scope="module", autouse=True)
def _single_torch_thread():
    """Tiny runs are faster on one thread, and it avoids OpenMP spin-wait stalls under load."""
    previous = torch.get_num_threads()
    torch.set_num_threads(1)
    yield
    torch.set_num_threads(previous)


@pytest.fixture(scope="module")
def bench() -> dict:
    return ex.run_scorer_bench(TINY, SEED, xi=10.0, lam=0.1, target_known_accept=0.95)


# ---------------------------------------------------------------------------
# energy and max-logit scores
# ---------------------------------------------------------------------------


def test_energy_and_maxlogit_direction():
    # A confident one-hot logit row must score LESS unknown than a flat row.
    logits = np.array([[10.0, 0.0, 0.0, 0.0], [1.0, 1.0, 1.0, 1.0]])
    energy = energy_unknown_score(logits)
    maxlogit = maxlogit_unknown_score(logits)
    assert energy[0] < energy[1]
    assert maxlogit[0] < maxlogit[1]
    assert maxlogit.tolist() == [-10.0, -1.0]


def test_energy_matches_naive_reference_and_is_stable():
    rng = np.random.default_rng(0)
    z = rng.normal(0.0, 3.0, size=(16, 4))  # small values: the naive formula is exact here
    naive = -np.log(np.sum(np.exp(z), axis=1))
    assert np.allclose(energy_unknown_score(z), naive, rtol=0, atol=1e-12)
    # Stability: logits of 1000 overflow exp() in the naive formula, not here.
    big = energy_unknown_score(np.array([[1000.0, 1000.0]]))
    assert np.allclose(big, -(1000.0 + math.log(2.0)))


def test_energy_is_not_shift_invariant_unlike_msp():
    """Documented property: energy(z + c) = energy(z) - c, while MSP ignores the shift.

    Shift invariance is NOT expected for energy: the score keeps the logit
    magnitude that the softmax normalises away, which is the whole point of
    comparing it with MSP on the same model.
    """
    rng = np.random.default_rng(1)
    z = rng.normal(0.0, 2.0, size=(8, 4))
    shifted = z + 5.0
    assert np.allclose(energy_unknown_score(shifted), energy_unknown_score(z) - 5.0)
    assert np.allclose(msp_unknown_score(shifted), msp_unknown_score(z))


def test_logit_scores_reject_non_2d_input():
    for fn in (energy_unknown_score, maxlogit_unknown_score):
        with pytest.raises(ValueError, match="logits"):
            fn(np.zeros(4))


# ---------------------------------------------------------------------------
# shared covariance and Mahalanobis score
# ---------------------------------------------------------------------------


def _gaussian_clusters(seed: int = 0, n_per: int = 400):
    rng = np.random.default_rng(seed)
    true_means = np.array([[0.0, 0.0, 0.0], [6.0, 0.0, 0.0], [0.0, 6.0, 0.0]])
    mixing = np.array([[1.0, 0.3, 0.0], [0.0, 0.8, 0.2], [0.1, 0.0, 0.5]])  # shared covariance
    emb = np.concatenate([mu + rng.standard_normal((n_per, 3)) @ mixing.T for mu in true_means])
    labels = np.repeat(np.arange(3), n_per)
    return emb, labels, true_means


def test_fit_shared_covariance_recovers_means_and_inverts_shrunk_sigma():
    emb, labels, true_means = _gaussian_clusters()
    means, precision = fit_shared_covariance(emb, labels, 3, shrinkage=0.1)
    assert means.shape == (3, 3) and precision.shape == (3, 3)
    assert np.allclose(means, true_means, atol=0.25)  # sample means at n=400 per class

    # Hand-computed pooled covariance with denominator N - C, then the shrink formula.
    centered = emb - means[labels]
    sigma = centered.T @ centered / (emb.shape[0] - 3)
    sigma_s = 0.9 * sigma + 0.1 * (np.trace(sigma) / 3) * np.eye(3)
    assert np.allclose(precision @ sigma_s, np.eye(3), atol=1e-10)  # P really is inv(Sigma_s)


def test_fit_shared_covariance_ignores_outliers_and_validates():
    emb, labels, _ = _gaussian_clusters()
    means, precision = fit_shared_covariance(emb, labels, 3)
    # A -1 outlier row must change nothing: the fit uses labels >= 0 only.
    emb_out = np.concatenate([emb, [[1e6, -1e6, 1e6]]])
    labels_out = np.concatenate([labels, [-1]])
    means_b, precision_b = fit_shared_covariance(emb_out, labels_out, 3)
    assert np.array_equal(means, means_b) and np.array_equal(precision, precision_b)

    with pytest.raises(ValueError, match="no known samples"):
        fit_shared_covariance(emb, np.where(labels == 2, 1, labels), 3)  # class 2 empty
    with pytest.raises(ValueError, match="N > C"):
        fit_shared_covariance(np.eye(3), np.arange(3), 3)  # N == C
    with pytest.raises(ValueError, match="shrinkage"):
        fit_shared_covariance(emb, labels, 3, shrinkage=1.5)


def test_mahalanobis_zero_at_mean_and_identity_equals_euclidean():
    means = np.array([[0.0, 0.0], [4.0, 0.0], [0.0, 4.0]])
    assert np.array_equal(mahalanobis_unknown_score(means, means, np.eye(2)), np.zeros(3))
    rng = np.random.default_rng(2)
    x = rng.normal(0.0, 3.0, size=(32, 2))
    assert np.allclose(
        mahalanobis_unknown_score(x, means, np.eye(2)),
        distance_unknown_score(x, means),  # identity precision = plain Euclidean distance
    )


def test_mahalanobis_identity_pooled_covariance_survives_shrinkage():
    # One class, samples mu +/- s*e_i with s^2 = (N - C)/2 and N = 2D, so the pooled
    # covariance is EXACTLY the identity; the shrink maps identity to identity
    # (trace/D = 1), hence precision = I and the score equals the Euclidean distance.
    d = 3
    s = math.sqrt((2 * d - 1) / 2.0)
    emb = np.concatenate([s * np.eye(d), -s * np.eye(d)])
    labels = np.zeros(2 * d, dtype=np.int64)
    means, precision = fit_shared_covariance(emb, labels, 1, shrinkage=0.1)
    assert np.allclose(means, np.zeros((1, d)))
    assert np.allclose(precision, np.eye(d))
    x = np.array([[1.0, 2.0, 2.0]])
    assert np.allclose(mahalanobis_unknown_score(x, means, precision), [3.0])


def test_mahalanobis_monotone_under_scaling():
    # Against a single mean the score is exactly linear in the deviation scale:
    # score(mu + t*v) = t * sqrt(v^T P v), so scaling the deviation raises it.
    emb, labels, _ = _gaussian_clusters()
    means, precision = fit_shared_covariance(emb, labels, 3)
    v = np.array([1.0, -2.0, 0.5])
    points = np.stack([means[0] + t * v for t in (1.0, 2.0, 4.0)])
    scores = mahalanobis_unknown_score(points, means[:1], precision)
    assert scores[0] < scores[1] < scores[2]  # moving away from the mean raises the score
    assert np.allclose(scores, scores[0] * np.array([1.0, 2.0, 4.0]))


# ---------------------------------------------------------------------------
# OSCR points
# ---------------------------------------------------------------------------

HAND_KNOWN = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6]
HAND_CORRECT = [True, True, False, True, False, True]
HAND_UNKNOWN = [0.25, 0.35, 0.55, 0.7]


def test_oscr_points_hand_example():
    out = ex.oscr_points(HAND_KNOWN, HAND_CORRECT, HAND_UNKNOWN)
    # Endpoints present: (0, 0) at t = -inf, (1, 4/6) at t = +inf.
    assert (out["fpr"][0], out["ccr"][0]) == (0.0, 0.0)
    assert (out["fpr"][-1], out["ccr"][-1]) == (1.0, 4 / 6)
    assert out["fpr"] == sorted(out["fpr"])
    assert len(out["fpr"]) == len(out["ccr"]) == len(set(HAND_KNOWN + HAND_UNKNOWN)) + 2
    # Hand computation: area segments 0.25*(2/6) + 0.25*(2/6) + 0.25*(3/6) + 0.25*(4/6).
    assert math.isclose(out["oscr_auc"], 11 / 24)
    assert 0.0 <= out["oscr_auc"] <= 1.0
    # Points with FPR <= 0.10 are the thresholds 0.1 and 0.2 (and the (0,0) endpoint):
    # best CCR among them is 2/6.
    assert math.isclose(out["ccr_at_fpr10"], 2 / 6)


def test_oscr_points_brute_force_cross_check():
    known, correct, unknown = HAND_KNOWN, HAND_CORRECT, HAND_UNKNOWN
    pts = [(0.0, 0.0)]
    for t in sorted(set(known + unknown)):
        fpr = sum(u <= t for u in unknown) / len(unknown)
        ccr = sum(k <= t and c for k, c in zip(known, correct)) / len(known)
        pts.append((fpr, ccr))
    pts.append((1.0, sum(correct) / len(known)))
    brute_auc = sum((x2 - x1) * (y1 + y2) / 2 for (x1, y1), (x2, y2) in pairwise(pts))
    out = ex.oscr_points(known, correct, unknown)
    assert math.isclose(out["oscr_auc"], brute_auc)
    assert list(zip(out["fpr"], out["ccr"])) == pts


def test_oscr_points_validates_input():
    with pytest.raises(ValueError, match="disagree"):
        ex.oscr_points([0.1, 0.2], [True], [0.3])
    with pytest.raises(ValueError, match="at least one"):
        ex.oscr_points([0.1], [True], [])
    with pytest.raises(ValueError, match="NaN or inf"):
        ex.oscr_points([0.1, float("nan")], [True, True], [0.3])


# ---------------------------------------------------------------------------
# run_scorer_bench on a tiny scale
# ---------------------------------------------------------------------------

ALL_VARIANTS = (
    "CE+MSP",
    "CE+maxlogit",
    "CE+energy",
    "CE+distance",
    "CE+mahalanobis",
    "OS-full+MSP",
    "OS-16PSK+MSP",
    "OS-8PAM+MSP",
)


def test_scorer_bench_strict_json_without_stripping(bench):
    json.dumps(bench, allow_nan=False)  # full result, nothing stripped
    assert bench["stage"] == "scorer_bench"
    assert bench["chance"] == {"closed_set": 0.25, "auroc": 0.5}


def test_scorer_bench_variant_keys_counts_and_leakage_guard(bench):
    assert tuple(bench["variants"]) == ALL_VARIANTS
    n_known = bench["frames"]["test_known"]  # 4 classes x 2 devices x 2 frames = 16
    n_unknown = bench["frames"]["test_unknown"]  # 2 classes x 1 device x 2 frames = 4
    assert (n_known, n_unknown) == (16, 4)
    for name, v in bench["variants"].items():
        assert v["kind"] == ("objectosphere" if name.startswith("OS-") else "posthoc")
        rep = v["report"]
        assert (rep["n_known"], rep["n_unknown"]) == (n_known, n_unknown)
        assert np.isfinite(v["threshold"]) and v["threshold"] == rep["threshold"]
        # Unknown-leakage guard: the only unknown classes anywhere are the test-only pair.
        assert set(v["per_unknown_class"]) == {"64QAM", "4PAM"}
        assert sum(c["n"] for c in v["per_unknown_class"].values()) == rep["n_unknown"]
        assert set(v["scores"]["unknown_class"]) <= {"64QAM", "4PAM"}
        for cls, c in v["per_unknown_class"].items():
            assert c["n"] == v["scores"]["unknown_class"].count(cls)
        # Scores arrays align with the reported denominators.
        s = v["scores"]
        assert len(s["known"]) == len(s["known_snr"]) == len(s["known_correct"]) == n_known
        assert len(s["unknown"]) == len(s["unknown_snr"]) == len(s["unknown_class"]) == n_unknown
        assert set(s["known_correct"]) <= {0, 1}
        # Per-SNR rows cover exactly the training grid, with counts that sum to the totals.
        assert [row["snr_db"] for row in v["per_snr_auroc"]] == list(ex.TRAIN_SNRS)
        assert sum(row["n_known"] for row in v["per_snr_auroc"]) == n_known
        assert sum(row["n_unknown"] for row in v["per_snr_auroc"]) == n_unknown
        band = v["snr_band_auroc"]
        assert band["n_known_low"] == sum(x <= 2 for x in s["known_snr"])
        assert band["n_unknown_high"] == sum(x >= 10 for x in s["unknown_snr"])
        assert 0.0 <= v["oscr"]["oscr_auc"] <= 1.0
        assert 0.0 <= v["oscr"]["ccr_at_fpr10"] <= 1.0
        acc = v["closed_set_on_accepted"]
        assert acc["n"] <= n_known and acc["n_correct"] <= acc["n"]


def test_scorer_bench_threshold_calibrated_on_known_val_calib_only(bench):
    # The sanctioned check: the calibration pool is the known val-calib split
    # (its size is exposed as n_calib_known, like run_open_set), never unknowns.
    expected_calib = bench["frames"]["val_calib"]  # 4 classes x 1 device x 2 frames = 8
    assert expected_calib == 8
    for v in bench["variants"].values():
        assert v["n_calib_known"] == expected_calib


def test_scorer_bench_posthoc_variants_share_one_model(bench):
    posthoc = [bench["variants"][k] for k in ALL_VARIANTS[:5]]
    for key in ("epochs_run", "best_epoch", "val_select_accuracy_best", "train_frames"):
        assert len({v[key] for v in posthoc}) == 1, key
    assert all(v["train_outliers"] == 0 for v in posthoc)
    # The five scorers share the CE model, so the closed-set predictions match too.
    assert len({tuple(v["scores"]["known_correct"]) for v in posthoc}) == 1


def test_scorer_bench_arm_outlier_frame_counts(bench):
    full = bench["variants"]["OS-full+MSP"]
    psk = bench["variants"]["OS-16PSK+MSP"]
    pam = bench["variants"]["OS-8PAM+MSP"]
    per_class = TINY.tx_aux * TINY.frames_train  # 1 device x 2 frames
    assert psk["train_outliers"] == pam["train_outliers"] == per_class
    assert full["train_outliers"] == psk["train_outliers"] + pam["train_outliers"]
    n_known_train = bench["frames"]["train_known"]
    for v in (full, psk, pam):
        assert v["train_frames"] == n_known_train + v["train_outliers"]


def test_scorer_bench_is_deterministic_per_seed(bench):
    again = ex.run_scorer_bench(TINY, SEED, xi=10.0, lam=0.1, target_known_accept=0.95)
    assert ex.to_strict_json(again) == ex.to_strict_json(bench)


def test_scorer_bench_unknown_pool_cannot_move_thresholds(bench):
    """Honesty rule: unknown frames are scored after calibration, so a larger
    unknown pool changes n_unknown but neither thresholds nor known-side numbers."""
    larger = ex.run_scorer_bench(replace(TINY, tx_unknown=2), SEED, 10.0, 0.1, 0.95)
    for name in ALL_VARIANTS:
        a, b = bench["variants"][name], larger["variants"][name]
        assert a["threshold"] == b["threshold"]
        assert a["n_calib_known"] == b["n_calib_known"]
        assert a["scores"]["known"] == b["scores"]["known"]
        assert a["report"]["n_known"] == b["report"]["n_known"]
        assert a["report"]["n_unknown"] != b["report"]["n_unknown"]


def test_scorer_bench_rejects_bad_arguments():
    with pytest.raises(ValueError):
        ex.run_scorer_bench(TINY, SEED, xi=0.0)
    with pytest.raises(ValueError):
        ex.run_scorer_bench(TINY, SEED, target_known_accept=0.0)
    with pytest.raises(ValueError):
        ex.run_scorer_bench(TINY, -1)

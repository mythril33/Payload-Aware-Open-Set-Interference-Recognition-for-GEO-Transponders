"""Training-only feature distances, regularization and safe persistence."""
import json

import numpy as np
import pytest

from geoml.mahalanobis import MahalanobisScorer, fit_mahalanobis


def test_one_dimensional_distance_matches_pooled_within_class_variance():
    scorer = fit_mahalanobis(np.array([[-1.], [1.], [9.], [11.]]), np.array([0, 0, 1, 1]), 2)
    # Residual scatter 4, N-K=2: variance 2; trace-shrinkage has no effect in 1D.
    expected = np.array([0., 1., 16.]) / (2 + 2e-6)
    assert scorer.score(np.array([[0.], [1.], [6.]])) == pytest.approx(expected)
    assert scorer.to_dict()["class_counts"] == [2, 2]
    assert scorer.to_dict()["n_training"] == 4


def test_far_events_score_above_training_clusters_and_fit_ignores_query_data():
    rng = np.random.default_rng(7)
    train = np.concatenate([rng.normal(-2, 0.1, (10, 3)), rng.normal(2, 0.1, (10, 3))])
    scorer = fit_mahalanobis(train, np.repeat([0, 1], 10), 2, provenance="training-only")
    before = scorer.to_dict()
    known = scorer.score(np.array([[-2., -2., -2.], [2., 2., 2.]]))
    unknown = scorer.score(np.array([[20., 0., -20.]]))
    assert unknown.min() > known.max() * 100
    assert scorer.to_dict() == before
    assert scorer.provenance == "training-only"


def test_singular_high_dimensional_small_sample_covariance_remains_finite():
    # D=32 > N=4, with repeated features and a rank-deficient pooled covariance.
    train = np.repeat(np.array([[-1.], [1.], [9.], [11.]]), 32, axis=1)
    scorer = fit_mahalanobis(train, np.array([0, 0, 1, 1]), 2)
    assert np.isfinite(scorer.score(train)).all()
    assert np.all(np.diag(scorer.cholesky) > 0)
    off_manifold = np.full((1, 32), 0.)
    off_manifold[0, 0] = 10
    assert scorer.score(off_manifold)[0] > scorer.score(train).max()


def test_zero_within_class_variance_uses_positive_floor():
    scorer = fit_mahalanobis(np.array([[0., 0.], [10., 10.]]), np.array([0, 1]), 2)
    assert scorer.covariance_floor == 1e-8
    assert scorer.score(np.array([[0., 0.], [10., 10.]])) == pytest.approx([0., 0.])
    assert np.isfinite(scorer.score(np.ones((1, 2)))).all()


def test_class_relabeling_and_training_row_order_do_not_change_distances():
    train = np.array([[-1., 0.], [1., 0.], [9., 2.], [11., 2.]])
    y = np.array([0, 0, 1, 1])
    original = fit_mahalanobis(train, y, 2)
    reordered = fit_mahalanobis(train[::-1], 1 - y[::-1], 2)
    query = np.array([[0., 0.], [10., 2.], [4., 3.]])
    assert original.score(query) == pytest.approx(reordered.score(query))


def test_fit_copies_parameters_and_public_arrays_are_read_only():
    train = np.array([[-1.], [1.], [9.], [11.]])
    scorer = fit_mahalanobis(train, np.array([0, 0, 1, 1]), 2)
    before = scorer.score(np.array([[1.]]))
    train[:] = 99
    assert scorer.score(np.array([[1.]])) == pytest.approx(before)
    with pytest.raises(ValueError):
        scorer.means[0, 0] = 99


def test_plain_array_persistence_preserves_scores_and_provenance(tmp_path):
    scorer = fit_mahalanobis(np.array([[-1.], [1.], [9.], [11.]]), np.array([0, 0, 1, 1]), 2,
                             provenance="checkpoint-sha/train-fingerprint")
    path = tmp_path / "mahalanobis.npz"
    scorer.save(path)
    reloaded = MahalanobisScorer.load(path)
    assert reloaded.to_dict() == scorer.to_dict()
    assert np.array_equal(reloaded.score(np.array([[2.], [20.]])), scorer.score(np.array([[2.], [20.]])))
    with np.load(path, allow_pickle=False) as artifact:
        assert artifact["metadata"].dtype.kind == "U"


def test_modified_parameters_are_rejected_against_persisted_checksum(tmp_path):
    scorer = fit_mahalanobis(np.array([[0.], [1.]]), np.array([0, 1]), 2)
    path = tmp_path / "mahalanobis.npz"
    scorer.save(path)
    with np.load(path, allow_pickle=False) as artifact:
        arrays = {name: artifact[name] for name in artifact.files}
    arrays["means"] += 1
    np.savez(path, **arrays)
    with pytest.raises(ValueError, match="checksum"):
        MahalanobisScorer.load(path)


def test_modified_metadata_is_rejected_even_when_array_parameters_are_unchanged(tmp_path):
    scorer = fit_mahalanobis(np.array([[0.], [1.]]), np.array([0, 1]), 2)
    path = tmp_path / "mahalanobis.npz"
    scorer.save(path)
    with np.load(path, allow_pickle=False) as artifact:
        arrays = {name: artifact[name] for name in artifact.files}
    metadata = json.loads(arrays["metadata"].item())
    metadata["regularization"] = 0.2
    arrays["metadata"] = np.array(json.dumps(metadata))
    np.savez(path, **arrays)
    with pytest.raises(ValueError, match="checksum"):
        MahalanobisScorer.load(path)


@pytest.mark.parametrize("embeddings, labels, n_classes", [
    ([], [], 2), ([[0.], [float("nan")]], [0, 1], 2),
    ([[0.], [float("inf")]], [0, 1], 2), ([[0.], [1.]], [0., 1.], 2),
    ([[0.], [1.]], [0], 2), ([[0.], [1.]], [0, 0], 2),
    ([[0.], [1.]], [0, 2], 2), ([[0.], [1.]], [0, -1], 2),
    ([[0.], [1.]], [0, 1], 1), ([[0.], [1.]], [0, 1], True),
])
def test_invalid_training_observations_fail(embeddings, labels, n_classes):
    with pytest.raises(ValueError):
        fit_mahalanobis(np.asarray(embeddings), np.asarray(labels), n_classes)


@pytest.mark.parametrize("regularization", [0, -0.1, 1.1, float("nan"), True, "0.1"])
def test_invalid_regularization_fails(regularization):
    with pytest.raises(ValueError, match="regularization"):
        fit_mahalanobis(np.array([[0.], [1.]]), np.array([0, 1]), 2, regularization)


@pytest.mark.parametrize("query", [np.empty((0, 1)), np.ones((1, 2)), np.array([[np.nan]]), np.array([[1e308]])])
def test_invalid_or_unrepresentable_queries_fail(query):
    scorer = fit_mahalanobis(np.array([[0.], [1.]]), np.array([0, 1]), 2)
    with pytest.raises(ValueError):
        scorer.score(query)


def test_nonfinite_training_covariance_is_rejected():
    with pytest.raises(ValueError, match="covariance"):
        fit_mahalanobis(np.array([[-1e308], [1e308], [0.], [1.]]), np.array([0, 0, 1, 1]), 2)


def test_corrupt_or_wrong_schema_artifact_is_rejected(tmp_path):
    path = tmp_path / "bad.npz"
    np.savez(path, metadata=np.array(json.dumps({"artifact_version": 99})))
    with pytest.raises(ValueError, match="artifact"):
        MahalanobisScorer.load(path)

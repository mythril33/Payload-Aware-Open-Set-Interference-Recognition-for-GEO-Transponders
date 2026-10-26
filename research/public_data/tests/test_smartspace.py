"""Synthetic MAT fixtures test import contracts, not SmartSpace performance."""
import json
from pathlib import Path

import numpy as np
import pytest
from scipy.io import savemat


from research.public_data import smartspace as M


def onboard(tmp_path, *, representation="reduced_magnitude", axis=0, features=None, labels=None):
    width, complex_allowed = M.ONBOARD_REPRESENTATIONS[representation]
    features = np.ones((6, width)) if features is None else features
    if complex_allowed and not np.iscomplexobj(features):
        features = features + 2j
    labels = np.vstack((np.zeros(5), np.eye(5))) if labels is None else labels
    path = tmp_path / "synthetic-onboard.mat"
    savemat(path, {"observed": features if axis == 0 else features.T,
                   "band_bits": labels if axis == 0 else labels.T}, do_compression=True)
    return path


@pytest.mark.parametrize("representation", M.ONBOARD_REPRESENTATIONS)
@pytest.mark.parametrize("axis", [0, 1])
def test_official_five_bit_label_mapping_and_explicit_axes(tmp_path, representation, axis):
    path = onboard(tmp_path, representation=representation, axis=axis)
    result = M.load_onboard_mat(path, features_key="observed", labels_key="band_bits",
                               representation=representation, samples_axis=axis)
    assert result["features"].shape == (6, M.ONBOARD_REPRESENTATIONS[representation][0])
    np.testing.assert_array_equal(result["labels"], np.arange(6))
    assert np.iscomplexobj(result["features"]) == M.ONBOARD_REPRESENTATIONS[representation][1]
    assert result["groups"] is None
    assert result["metadata"]["source_authenticity_verified"] is False
    json.dumps(result["metadata"], allow_nan=False)


@pytest.mark.parametrize("bad_labels", [np.ones((6, 5)), np.full((6, 5), 0.5), np.full((6, 5), np.nan),
                                       np.zeros((5, 5)), np.arange(6).reshape(-1, 1)])
def test_bad_native_indicators_and_guessed_six_class_vector_rejected(tmp_path, bad_labels):
    path = onboard(tmp_path, labels=bad_labels)
    with pytest.raises(ValueError):
        M.load_onboard_mat(path, features_key="observed", labels_key="band_bits", representation="reduced_magnitude")


@pytest.mark.parametrize("bad", [np.full((6, 100), -1.0), np.full((6, 100), np.inf),
                                 np.full((6, 100), np.nan), np.ones((6, 101)), np.ones((6, 100)) * 1j])
def test_magnitude_values_and_width_are_not_silently_coerced(tmp_path, bad):
    path = onboard(tmp_path, features=bad)
    with pytest.raises(ValueError):
        M.load_onboard_mat(path, features_key="observed", labels_key="band_bits", representation="reduced_magnitude")


def test_no_variable_or_orientation_guessing(tmp_path):
    path = onboard(tmp_path)
    for overrides in ({"features_key": "missing"}, {"labels_key": "observed"}, {"samples_axis": 1},
                      {"samples_axis": True}, {"representation": "IQ"}):
        args = {"features_key": "observed", "labels_key": "band_bits", "representation": "reduced_magnitude"}
        args.update(overrides)
        with pytest.raises(ValueError):
            M.load_onboard_mat(path, **args)


@pytest.mark.parametrize("split", ["train", "validation"])
def test_clean_only_ngso_split_uses_documented_population(tmp_path, split):
    path = tmp_path / "clean.mat"
    savemat(path, {"amplitude": np.ones((4, 800))})
    result = M.load_ngso_mat(path, features_key="amplitude", split=split)
    np.testing.assert_array_equal(result["labels"], np.zeros(4))
    assert result["native_labels"] is None and result["groups"] is None
    assert "split declaration" in result["metadata"]["labels_source"]
    with pytest.raises(ValueError):
        M.load_ngso_mat(path, features_key="amplitude", split=split, positive_label=1)


@pytest.mark.parametrize("width", [799, 801, 802])
def test_ngso_never_uses_appended_labels_inr_or_offaxis_as_features(tmp_path, width):
    path = tmp_path / "wrong-width.mat"
    savemat(path, {"x": np.ones((3, width))})
    with pytest.raises(ValueError, match="800"):
        M.load_ngso_mat(path, features_key="x", split="train")


def test_ngso_binary_test_direction_is_explicit_and_original_values_retained(tmp_path):
    data, labels = tmp_path / "test.mat", tmp_path / "labels.mat"
    savemat(data, {"amplitudes": np.ones((800, 4))})
    savemat(labels, {"truth": np.array([[-1, 7, -1, 7]])})
    with pytest.raises(ValueError, match="positive_label"):
        M.load_ngso_mat(data, features_key="amplitudes", split="test", labels_path=labels,
                        labels_key="truth", samples_axis=1)
    result = M.load_ngso_mat(data, features_key="amplitudes", split="test", labels_path=labels,
                            labels_key="truth", positive_label=7, samples_axis=1)
    np.testing.assert_array_equal(result["labels"], [0, 1, 0, 1])
    np.testing.assert_array_equal(result["native_labels"], [-1, 7, -1, 7])
    assert result["metadata"]["labels_sha256"] != result["metadata"]["sha256"]


@pytest.mark.parametrize("native,positive", [([0, 0, 0, 0], 1), ([0, 1, 2, 0], 1),
                                           ([0, 1, 0, 1], 2), ([0, np.nan, 0, 1], 1),
                                           ([0, 1, 0], 1)])
def test_invalid_binary_labels_not_repaired(tmp_path, native, positive):
    data, labels = tmp_path / "test.mat", tmp_path / "labels.mat"
    savemat(data, {"x": np.ones((4, 800))})
    savemat(labels, {"y": np.asarray(native).reshape(1, -1)})
    with pytest.raises(ValueError):
        M.load_ngso_mat(data, features_key="x", split="test", labels_path=labels, labels_key="y", positive_label=positive)


def test_file_bound_checked_before_parsing_and_html_is_not_data(tmp_path, monkeypatch):
    path = tmp_path / "login.mat"
    path.write_text("<html><title>Sign in to your account</title></html>")
    with pytest.raises(ValueError):
        M.load_ngso_mat(path, features_key="x", split="train")
    monkeypatch.setattr(M, "MAX_FILE_BYTES", 1)
    with pytest.raises(ValueError, match="256 MiB"):
        M.load_ngso_mat(path, features_key="x", split="train")


def test_declared_sample_bound_precedes_array_loading(tmp_path, monkeypatch):
    path = tmp_path / "shape.mat"
    savemat(path, {"x": np.ones((4, 800))})
    monkeypatch.setattr(M, "MAX_ROWS", 3)
    monkeypatch.setattr(M, "loadmat", lambda *args, **kwargs: pytest.fail("must reject header before loading array"))
    with pytest.raises(ValueError, match="samples"):
        M.load_ngso_mat(path, features_key="x", split="train")


def test_matlab_v73_is_explicitly_unsupported_instead_of_guessed(tmp_path):
    path = tmp_path / "v73.mat"
    savemat(path, {"x": np.ones((4, 800))})
    header = path.read_bytes()[:128]
    path.write_bytes(header[:124] + b"\x00\x02IM")
    with pytest.raises(ValueError, match="v7.3/HDF5"):
        M.load_ngso_mat(path, features_key="x", split="train")

"""Publisher-shaped small fixtures; no external samples are committed."""
from pathlib import Path

import numpy as np
import pytest

from research.public_data.fraunhofer import DataError, SplitLeakage, audit_partitions, iter_records, parse_split


def metadata(tmp_path, text, *, kind="lc", name="split.txt"):
    path = tmp_path / name
    path.write_text(text)
    return parse_split(path, kind=kind)


def test_published_fields_are_metadata_and_native_labels_are_preserved(tmp_path):
    rows = metadata(tmp_path, "data_LC/00566.npy\t0\t-1\t-1\ndata_LC/00000.npy\t2\t3\t-40\n")
    assert (rows[0].recording_id, rows[0].label, rows[0].crop) == ("00566", 0, None)
    assert (rows[1].label, rows[1].subjammer, rows[1].power) == (2, 3, -40.0)


@pytest.mark.parametrize("line", ["data_LC/../00566.npy 0 -1 -1", "other/00566.npy 0 -1 -1",
                                 "data_LC/00566.npy 9 -1 -1", "data_LC/00566.npy 0 -1 nan",
                                 "data_LC/00566.npy 0 -2 -1", "data_LC/00566.npy 0", ""])
def test_invalid_metadata_and_invented_labels_are_refused(tmp_path, line):
    with pytest.raises(DataError):
        metadata(tmp_path, line)


def test_repeated_path_is_not_an_independent_sample(tmp_path):
    with pytest.raises(DataError, match="repeated"):
        metadata(tmp_path, "data_LC/00566.npy 0 -1 -1\ndata_LC/00566.npy 0 -1 -1")


def test_six_crops_of_one_recording_must_not_cross_partitions(tmp_path):
    train = metadata(tmp_path, "data_FIOT/00566_0.npy 0 -1 -1", kind="fiot", name="train.txt")
    test = metadata(tmp_path, "data_FIOT/00566_5.npy 0 -1 -1", kind="fiot", name="test.txt")
    with pytest.raises(SplitLeakage, match="recording"):
        audit_partitions(train, test)


def test_cross_modality_pairs_are_the_same_recording(tmp_path):
    train = metadata(tmp_path, "data_LC/00566.npy 0 -1 -1", name="train.txt")
    test = metadata(tmp_path, "data_FIOT/00566_0.npy 0 -1 -1", kind="fiot", name="test.txt")
    with pytest.raises(SplitLeakage):
        audit_partitions(train, test)


def test_partition_report_counts_recordings_and_crops_separately(tmp_path):
    train = metadata(tmp_path, "data_FIOT/00566_0.npy 0 -1 -1\ndata_FIOT/00566_1.npy 0 -1 -1", kind="fiot", name="train.txt")
    test = metadata(tmp_path, "data_FIOT/00000_0.npy 2 3 -40", kind="fiot", name="test.txt")
    report = audit_partitions(train, test)
    assert report["train"]["samples"] == 2 and report["train"]["recordings"] == 1
    assert report["recording_overlap"] == 0 and report["session_independence"].startswith("UNKNOWN")


@pytest.mark.parametrize("timesteps", [0, 9, 10])
def test_actual_empty_and_short_lc_shapes_are_explicit_not_silently_dropped(tmp_path, timesteps):
    rows = metadata(tmp_path, "data_LC/00566.npy 0 -1 -1")
    np.save(tmp_path / "00566.npy", np.zeros((timesteps, 308), dtype=np.float64))
    samples = list(iter_records(tmp_path, rows))
    assert len(samples) == 1 and samples[0].values.shape == (timesteps, 308)
    assert samples[0].label == 0 and len(samples[0].sha256) == 64
    # Label, subjammer, power and recording ID are never appended to values.
    assert samples[0].values.shape[1] == 308


@pytest.mark.parametrize("array", [np.zeros((10, 307)), np.zeros((11, 308)), np.full((10, 308), np.nan),
                                  np.array([[{"unsafe": "object"}]], dtype=object)])
def test_incompatible_nonfinite_and_pickle_arrays_are_refused(tmp_path, array):
    rows = metadata(tmp_path, "data_LC/00566.npy 0 -1 -1")
    np.save(tmp_path / "00566.npy", array)
    with pytest.raises(DataError):
        list(iter_records(tmp_path, rows))


def test_missing_and_symlinked_npy_are_refused(tmp_path):
    rows = metadata(tmp_path, "data_LC/00566.npy 0 -1 -1")
    with pytest.raises(DataError):
        list(iter_records(tmp_path, rows))
    np.save(tmp_path / "other.npy", np.zeros((10, 308)))
    (tmp_path / "00566.npy").symlink_to(tmp_path / "other.npy")
    with pytest.raises(DataError):
        list(iter_records(tmp_path, rows))


def test_record_budget_is_not_implicit_prefix_selection(tmp_path):
    rows = metadata(tmp_path, "data_LC/00566.npy 0 -1 -1\ndata_LC/00000.npy 2 3 -40")
    with pytest.raises(DataError, match="select"):
        list(iter_records(tmp_path, rows, max_records=1))


def test_released_fiot_representation_is_rendered_rgb_not_dual_polarization(tmp_path):
    rows = metadata(tmp_path, "data_FIOT/00566_0.npy 0 -1 -1", kind="fiot")
    np.save(tmp_path / "00566_0.npy", np.full((512, 243, 3), 127, dtype=np.int32))
    sample, = iter_records(tmp_path, rows, kind="fiot")
    assert sample.values.shape == (512, 243, 3) and sample.values.dtype == np.dtype("int32")
    assert sample.recording_id == "00566" and sample.crop == 0


@pytest.mark.parametrize("array", [np.zeros((512, 243)), np.zeros((512, 243, 3), dtype=np.float32),
                                  np.full((512, 243, 3), 256, dtype=np.int32)])
def test_iq_or_arbitrary_spectrum_cannot_be_misread_as_released_rgb_fiot(tmp_path, array):
    rows = metadata(tmp_path, "data_FIOT/00566_0.npy 0 -1 -1", kind="fiot")
    np.save(tmp_path / "00566_0.npy", array)
    with pytest.raises(DataError, match="RGB"):
        list(iter_records(tmp_path, rows, kind="fiot"))


def test_wrong_modality_rows_cannot_load_coincidentally_matching_filename(tmp_path):
    rows = metadata(tmp_path, "data_FIOT/00566_0.npy 0 -1 -1", kind="fiot")
    np.save(tmp_path / "00566_0.npy", np.zeros((10, 308)))
    with pytest.raises(DataError, match="representation"):
        list(iter_records(tmp_path, rows, kind="lc"))

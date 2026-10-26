"""Result readers: strict parsing, explicit absence, validated matrices and curves.

Synthetic fixtures below are labelled SYNTHETIC and are not results. The committed-record checks only verify
that catalog key paths resolve; they never assert or display a recognition value.
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "dashboard"), str(ROOT / "src"), str(ROOT)]

from geodash import results as R  # noqa: E402


def _write(tmp_path, payload, name="synthetic.json", raw=None):
    path = tmp_path / name
    path.write_text(raw if raw is not None else json.dumps(payload), encoding="utf-8")
    return path


# ---- strict loading ----------------------------------------------------------------------------------------

@pytest.mark.parametrize("raw", ['{"a": NaN}', '{"a": Infinity}', '{"a": -Infinity}'])
def test_non_finite_json_constants_are_refused(tmp_path, raw):
    with pytest.raises(R.RecordError):
        R.load_record(_write(tmp_path, None, raw=raw))


def test_a_json_array_is_not_a_record(tmp_path):
    with pytest.raises(R.RecordError):
        R.load_record(_write(tmp_path, [1, 2, 3]))


def test_oversized_records_are_refused_before_parsing(tmp_path, monkeypatch):
    monkeypatch.setattr(R, "MAX_RECORD_BYTES", 10)
    with pytest.raises(R.RecordError):
        R.load_record(_write(tmp_path, {"padding": "x" * 100}))


# ---- explicit absence and null, never filled in -------------------------------------------------------------

def test_absent_key_paths_are_reported_as_absent_with_their_path():
    reads = R.scalar_reads({"methods": {"co": {}}}, "AUROC", "methods.*.open_set.unknown_auroc")
    assert reads == [R.Read("AUROC", "methods.*.open_set.unknown_auroc", R.ABSENT,
                            note="key path not stored in this record")]


def test_a_stored_null_is_reported_as_null_not_as_zero():
    reads = R.scalar_reads({"methods": {"co": {"open_set": {"fpr_at_95_tpr": None}}}}, "FPR",
                           "methods.*.open_set.fpr_at_95_tpr")
    assert len(reads) == 1 and reads[0].status == R.NULL and reads[0].value is None


def test_a_non_numeric_scalar_is_not_coerced():
    reads = R.scalar_reads({"x": {"a": "0.9"}}, "X", "x.*")
    assert reads[0].status == R.ABSENT and reads[0].value is None


def test_wildcards_expand_in_sorted_key_order():
    record = {"methods": {"msp": {"threshold": 0.7}, "energy": {"threshold": -1.4}}}
    paths = [p for p, _ in R.resolve(record, "methods.*.threshold")]
    assert paths == ["methods.energy.threshold", "methods.msp.threshold"]


# ---- confusion matrices ----------------------------------------------------------------------------------------

def test_a_square_matrix_yields_counts_labels_total_and_accuracy(tmp_path):
    record = {"labels": ["a", "b"], "m": {"confusion": [[3, 1], [0, 4]]}}
    (view,) = R.confusion_reads(record, "m.confusion", "labels")
    assert isinstance(view, R.Confusion)
    assert view.labels == ("a", "b") and view.total == 8
    assert view.accuracy == pytest.approx(7 / 8)


def test_a_matrix_without_matching_labels_gets_numeric_names():
    (view,) = R.confusion_reads({"m": {"confusion": [[1, 0, 0], [0, 1, 0], [0, 0, 1]]}}, "m.confusion", None)
    assert view.labels == ("0", "1", "2")


@pytest.mark.parametrize("matrix", [[[1, 2], [3]], [[1, -1], [0, 1]], [[1.5, 0], [0, 1]], [[True, 0], [0, 1]]])
def test_malformed_confusion_matrices_are_refused(matrix):
    with pytest.raises(R.RecordError):
        R.confusion_reads({"m": {"confusion": matrix}}, "m.confusion", None)


def test_an_empty_matrix_has_no_accuracy_rather_than_zero():
    (view,) = R.confusion_reads({"m": {"confusion": [[0, 0], [0, 0]]}}, "m.confusion", None)
    assert view.total == 0 and view.accuracy is None


# ---- ROC curves -------------------------------------------------------------------------------------------------

def test_roc_arrays_are_read_as_stored():
    (curve,) = R.roc_reads({"s": {"unknown_roc": {"fpr": [0.0, 0.5, 1.0], "tpr": [0.0, 0.8, 1.0]}}},
                           "s.unknown_roc")
    assert curve.fpr == (0.0, 0.5, 1.0) and curve.tpr == (0.0, 0.8, 1.0)


@pytest.mark.parametrize("fpr,tpr", [([0.0, 1.2], [0.0, 1.0]), ([0.0], [0.0, 1.0]), ([], []),
                                     ([0.0, float("nan")], [0.0, 1.0])])
def test_invalid_roc_arrays_are_refused(fpr, tpr):
    with pytest.raises(R.RecordError):
        R.roc_reads({"s": {"roc": {"fpr": fpr, "tpr": tpr}}}, "s.roc")


def test_a_missing_roc_is_reported_absent():
    (read,) = R.roc_reads({"s": {}}, "s.roc")
    assert isinstance(read, R.Read) and read.status == R.ABSENT


# ---- training history and calibration bins -----------------------------------------------------------------

def test_training_history_must_be_a_list_of_objects():
    (read,) = R.history_reads({"h": "not a list"}, "h")
    assert isinstance(read, R.Read) and read.status == R.ABSENT
    (path, rows) = R.history_reads({"h": [{"epoch": 1, "loss": 0.5}]}, "h")[0]
    assert path == "h" and rows == [{"epoch": 1, "loss": 0.5}]


def test_calibration_bins_keep_empty_bins_with_null_values():
    bins = [{"lo": 0.0, "hi": 0.5, "n": 0, "accuracy": None, "confidence": None},
            {"lo": 0.5, "hi": 1.0, "n": 4, "accuracy": 0.75, "confidence": 0.8}]
    ((path, parsed),) = R.calibration_reads({"c": bins}, "c")
    assert parsed[0].n == 0 and parsed[0].accuracy is None
    assert parsed[1].accuracy == pytest.approx(0.75)


@pytest.mark.parametrize("bad", [[{"n": -1}], [{"n": 1.5}], [{"n": True}], ["not a dict"]])
def test_malformed_calibration_bins_are_refused(bad):
    with pytest.raises(R.RecordError):
        R.calibration_reads({"c": bad}, "c")


# ---- the committed records: key paths resolve, values are not asserted --------------------------------------

def test_every_catalog_record_is_present_and_resolves_at_least_one_key_path():
    coverage = R.catalog_coverage()
    assert len(coverage) == len(R.CATALOG)
    for row in coverage:
        assert row["present"], row["file"]
        assert row["resolved"] >= 1, f"no catalog key path resolves in {row['file']}"


def test_every_catalog_record_is_read_through_the_strict_reader():
    for spec in R.CATALOG:
        data = R.read_record(spec)
        assert data["error"] is None, spec.file
        assert data["items"], spec.file


def test_restricted_observation_files_are_never_in_the_catalog():
    from geodash import evidence
    restricted = {e.path for e in evidence.inventory() if e.evidence_class == evidence.RESTRICTED}
    assert restricted and not restricted & {spec.file for spec in R.CATALOG}

"""Group leakage and held-out-family exclusion in the development protocol."""
import numpy as np
import pytest

from geosim.classes import LABELS
from geosim.protocol import HoldoutProtocol, partition_summary


def source(seeds):
    labels = np.tile(np.arange(len(LABELS)), len(seeds))
    return {"spec": np.zeros((len(labels), 2, 3)), "mask": np.zeros((len(labels), 3)),
            "label": labels, "seed": np.repeat(seeds, len(LABELS)),
            "meta": [{"label": LABELS[label]} for label in labels]}


@pytest.mark.parametrize("holdout", LABELS[1:])
def test_group_partition_excludes_holdout_and_preserves_all_related_samples(holdout):
    protocol = HoldoutProtocol(holdout)
    parts = protocol.partition(source([1, 2]), source([10, 11, 12, 13]), source([20, 21]))
    for role in ("train", "validation", "calibration", "known_test"):
        assert all(meta["label"] != holdout for meta in parts[role]["meta"])
        assert set(parts[role]["label"]) == set(range(4))
    assert {meta["label"] for meta in parts["unknown_test"]["meta"]} == {holdout}
    summary = partition_summary(parts)
    groups = {name: set(values["scenario_ids"]) for name, values in summary.items()}
    assert groups["validation"].isdisjoint(groups["calibration"])
    assert groups["validation"] | groups["calibration"] == {10, 11, 12, 13}
    assert groups["known_test"] == groups["unknown_test"] == {20, 21}
    for role in ("validation", "calibration"):
        assert summary[role]["n_samples"] == len(groups[role]) * 4
    assert partition_summary(protocol.partition(source([1, 2]), source([10, 11, 12, 13]), source([20, 21]))) == summary


@pytest.mark.parametrize("other", ("validation", "test"))
def test_rejects_related_scenarios_crossing_partitions(other):
    sources = {"train": source([1, 2]), "validation": source([10, 11]), "test": source([20, 21])}
    sources[other] = source([1, 10])
    with pytest.raises(ValueError, match="leakage"):
        HoldoutProtocol().partition(**sources)


def test_requires_separate_selection_and_calibration_groups():
    with pytest.raises(ValueError, match="at least two"):
        HoldoutProtocol().partition(source([1]), source([10]), source([20]))


def test_cannot_hold_out_clean_or_an_undefined_family():
    for holdout in ("clean", "unknown", ""):
        with pytest.raises(ValueError, match="non-clean"):
            HoldoutProtocol(holdout)


def test_missing_family_is_an_error_instead_of_silent_zero_sample_evaluation():
    test = source([20])
    test["label"][:] = 0
    with pytest.raises(ValueError, match="every requested class"):
        HoldoutProtocol().partition(source([1]), source([10, 11]), test)

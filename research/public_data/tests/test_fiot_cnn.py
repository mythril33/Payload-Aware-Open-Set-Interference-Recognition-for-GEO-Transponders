from collections import Counter

import numpy as np
import pytest

pytest.importorskip("torch")

from research.public_data import fiot_cnn as cnn
from research.public_data.fraunhofer import FIOT_SHAPE, SampleRef, SplitLeakage


def refs(first_id, labels, crops=(0, 1)):
    return [SampleRef(f"data_FIOT/{i:05d}_{crop}.npy", label, f"{i:05d}", crop, -1, -1.)
            for i, label in enumerate(labels, first_id) for crop in crops]


def test_partition_filters_chirp_and_preserves_disjoint_stratified_roles():
    train = refs(0, [0] * 6 + [1] * 5 + [2] * 3)
    test = refs(20, [0, 1, 2, 2])
    roles, labels, excluded = cnn.partition_rows(train, test)
    assert cnn.partition_rows(list(reversed(train)), test)[0] == roles
    assert labels == (0, 1) and excluded == 3
    assert Counter(r.label for r in roles["fit"]) == {0: 4, 1: 3}
    for role in ("selection", "calibration"):
        assert Counter(r.label for r in roles[role]) == {0: 1, 1: 1}
    assert [r.label for r in roles["unknown_test"]] == [2, 2]
    used = [r.recording_id for rows in roles.values() for r in rows]
    assert len(used) == len(set(used)) and all(r.crop == 0 for rows in roles.values() for r in rows)


def test_identical_rgb_payloads_in_distinct_roles_are_refused(tmp_path):
    first, duplicate = refs(41, [0, 0], crops=(0,))
    for row in (first, duplicate):
        np.save(tmp_path / f"{row.recording_id}_0.npy", np.full(FIOT_SHAPE, [0, 128, 255], dtype=np.int32))
    seen = {}
    tensor, _ = cnn.load_images(tmp_path, [first], seen, "fit")
    assert tuple(tensor.shape) == (1, 3, 128, 64)
    np.testing.assert_allclose(tensor[0, :, 0, 0], [0., 128 / 255, 1.], atol=1e-6)
    with pytest.raises(SplitLeakage, match="identical image bytes"):
        cnn.load_images(tmp_path, [duplicate], seen, "calibration")

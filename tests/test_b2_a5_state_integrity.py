"""Adversarial scene metadata checks; no RF generation or model fitting."""
import json

import numpy as np
import pytest

from geoml.artifacts import fingerprint
from geoml.b2_a5 import SceneState


def saved(tmp_path):
    state = SceneState(tmp_path, "a" * 64, log=lambda *_: None)
    state.save(3200000, "clean", record={"status": "applied", "residual_recomputed": False},
               parity={"exact": True}, work={"replays": 1, "cancellations": 1, "recomputations": 0},
               arrays={"spec": np.zeros((2, 128, 512), np.float16),
                       "residual": np.zeros((128, 512), np.float16)})
    return state, tmp_path / "scene-3200000-clean.json"


@pytest.mark.parametrize("field", ["parity", "work", "record"])
def test_committed_metadata_tampering_is_rejected(tmp_path, field):
    state, path = saved(tmp_path)
    meta = json.loads(path.read_text())
    if field == "parity":
        meta[field]["exact"] = False
    elif field == "work":
        meta[field]["replays"] = 999
    else:
        meta[field]["residual_recomputed"] = True
    path.write_text(json.dumps(meta))
    with pytest.raises(ValueError, match="metadata.*(checksum|schema)"):
        state.load(3200000, "clean")


def test_legacy_unsigned_state_is_not_silently_trusted(tmp_path):
    state, path = saved(tmp_path)
    meta = json.loads(path.read_text())
    meta.pop("metadata_sha256", None)
    meta.pop("state_contract", None)
    path.write_text(json.dumps(meta))
    with pytest.raises(ValueError, match="metadata.*(checksum|schema)"):
        state.load(3200000, "clean")


@pytest.mark.parametrize("case", ["version", "extra", "work", "nan", "duplicate", "applied_without_replay"])
def test_invalid_schema_or_resigned_invalid_work_fails_closed(tmp_path, case):
    state, path = saved(tmp_path)
    meta = json.loads(path.read_text())
    if case == "version": meta["state_contract"] = "foreign/9"
    if case == "extra": meta["unexpected"] = 1
    if case == "work": meta["work"]["cancellations"] = 4
    if case == "nan": meta["parity"]["bad"] = float("nan")
    if case == "applied_without_replay":
        meta.update(parity=None, arrays_sha256=None, work={"replays": 0, "cancellations": 0, "recomputations": 0})
    if case != "nan":
        meta["metadata_sha256"] = fingerprint({k:v for k,v in meta.items() if k != "metadata_sha256"})
    text = json.dumps(meta)
    if case == "duplicate": text = text.replace('"label": "clean"', '"label": "clean", "label": "clean"')
    path.write_text(text)
    with pytest.raises(ValueError):
        state.load(3200000, "clean")


def test_compatible_state_reuses_arrays_and_work(tmp_path):
    state, path = saved(tmp_path)
    loaded = state.load(3200000, "clean")
    assert loaded["work"] == {"replays": 1, "cancellations": 1, "recomputations": 0}
    assert loaded["parity"]["exact"] is True
    assert loaded["arrays"]["residual"].shape == (128, 512)

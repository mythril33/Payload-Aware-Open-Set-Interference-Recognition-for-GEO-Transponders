"""R1-eval/1 test-only splits: separate protocol, seeds and single-condition changes (P17)."""
import json
from types import SimpleNamespace

import numpy as np
import pytest

from geosim import dataset as ds
from geosim import dual_dataset, event_dataset, unknowns

FIELDS = ("bandwidth", "amplifier", "linear", "labels", "ibo_nominal", "ibo_overdrive")


def fake_sample(label, bandwidth, seed, ranges=None, linear=False, amplifier="dvbs2_nl"):
    rng = np.random.default_rng(seed + ds.LABELS.index(label))
    spec = (-85 + rng.normal(size=(128, 512))).astype(np.float32)
    mask = np.full(512, -60., np.float32)
    mask[200:260] = 0
    return SimpleNamespace(spec_db=spec, mask_db=mask,
                           meta={"label": label, "config": {"seed": seed, "bandwidth": bandwidth, "linear": linear,
                                                          "amplifier": amplifier, "ibo_db": 10.0}})


def test_a1_is_unchanged_and_r1_is_a_separate_protocol():
    assert ds.PROTOCOL == "A1, frozen 2026-10-09" and ds.R1_PROTOCOL == "R1-eval/1"
    assert list(ds.SPLITS) == ["train_nl", "train_lin", "val_nl", "val_lin", "test_id_nl", "test_id_lin",
                               "test_ibo", "test_bw72", "test_amp_lin", "test_amp_saleh"]
    assert ds.PROTOCOLS == {ds.PROTOCOL: ds.SPLITS, ds.R1_PROTOCOL: ds.R1_SPLITS}
    assert not set(ds.SPLITS) & set(ds.R1_SPLITS)


def test_r1_seeds_never_overlap_other_protocols():
    r1 = set().union(*(set(s.seeds) for s in ds.R1_SPLITS.values()))
    a1 = set().union(*(set(s.seeds) for s in ds.SPLITS.values()))
    assert not r1 & a1
    assert max(r1) < 900000                                           # unknowns start here by default
    assert max(r1) < min(dual_dataset.ROLE_STARTS.values()) and max(r1) < min(event_dataset.ROLE_STARTS.values())
    splits = list(ds.R1_SPLITS.values())
    for i, a in enumerate(splits):
        for b in splits[i + 1:]:
            assert not set(a.seeds) & set(b.seeds), (a.name, b.name)
    assert unknowns.generate_unknowns.__defaults__[1] == 900000


def test_each_r1_split_changes_only_its_declared_condition():
    ref = ds.SPLITS["test_id_nl"]
    declared = {"r1_ibo_sweep": {"ibo_nominal", "ibo_overdrive"}, "r1_amp_rapp": {"amplifier"},
                "r1_amp_opendpd_apa": {"amplifier", "labels"}, "r1_amp_opendpd_dpa": {"amplifier", "labels"}}
    assert set(declared) == set(ds.R1_SPLITS)
    for name, fields in declared.items():
        split = ds.R1_SPLITS[name]
        assert {f for f in FIELDS if getattr(split, f) != getattr(ref, f)} == fields, name
    for name in ("r1_amp_opendpd_apa", "r1_amp_opendpd_dpa"):        # measured PAs never in overdrive (K11)
        assert "overdrive" not in ds.R1_SPLITS[name].labels
    sweep = ds.R1_SPLITS["r1_ibo_sweep"]
    assert sweep.ibo_nominal == ((5.0, 14.0),) and sweep.ibo_overdrive == ((0.0, 5.0),)


def test_r1_generation_round_trip_and_protocol_isolation(tmp_path, monkeypatch):
    monkeypatch.setattr(ds, "sample", fake_sample)
    ds.generate(str(tmp_path), ["r1_amp_rapp"], limit_seeds=1, protocol=ds.R1_PROTOCOL)
    data = ds.load_split(tmp_path / "r1_amp_rapp")
    manifest = ds.read_manifest(tmp_path / "r1_amp_rapp")
    assert manifest["protocol"] == "R1-eval/1" and manifest["complete"] is False
    assert set(data["seed"]) == {410000} and len(data["label"]) == 5
    assert {m["config"]["amplifier"] for m in data["meta"]} == {"rapp_p2"}
    with pytest.raises(ValueError, match="split names of A1"):
        ds.generate(str(tmp_path), ["r1_amp_rapp"], limit_seeds=1)
    with pytest.raises(ValueError, match="protocol must be one of"):
        ds.generate(str(tmp_path), ["r1_amp_rapp"], limit_seeds=1, protocol="R2")
    # an R1 artifact relabelled as A1 is rejected
    path = tmp_path / "r1_amp_rapp" / "manifest.json"
    tampered = json.loads(path.read_text())
    tampered["protocol"] = ds.PROTOCOL
    path.write_text(json.dumps(tampered))
    with pytest.raises(ValueError, match="does not match A1"):
        ds.load_split(tmp_path / "r1_amp_rapp")


def test_ibo_sweep_draws_cover_gap_and_training_ranges():
    split = ds.R1_SPLITS["r1_ibo_sweep"]
    for seed in list(split.seeds)[:50]:
        r = ds.ranges_for(split, seed)
        assert r.ibo_nominal_db == (5.0, 14.0) and r.ibo_overdrive_db == (0.0, 5.0)

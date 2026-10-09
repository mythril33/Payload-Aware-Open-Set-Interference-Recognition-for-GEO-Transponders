"""Split protocol checks (docs/plan/P5_veri_protokol.md §6)."""
import json

import numpy as np

from geosim.classes import LABELS
from geosim.dataset import ID_NOMINAL, ID_OVERDRIVE, SPLITS, generate, load_split, ranges_for


def _paired(a, b):
    return a.name.rsplit("_", 1)[0] == b.name.rsplit("_", 1)[0] and {a.linear, b.linear} == {True, False}


def test_seed_ranges_are_disjoint_except_linear_pairs():
    splits = list(SPLITS.values())
    for i, a in enumerate(splits):
        for b in splits[i + 1:]:
            overlap = set(a.seeds) & set(b.seeds)
            if _paired(a, b):
                assert a.seeds == b.seeds
            else:
                assert not overlap, (a.name, b.name)


def test_only_one_condition_changes_per_test_split():
    ref = SPLITS["test_id_nl"]
    changed = {"test_ibo": {"ibo_nominal", "ibo_overdrive"}, "test_bw72": {"bandwidth"},
               "test_amp_lin": {"amplifier"}, "test_amp_saleh": {"amplifier"}}
    for name, fields in changed.items():
        s = SPLITS[name]
        diff = {f for f in ("bandwidth", "amplifier", "linear", "labels", "ibo_nominal", "ibo_overdrive")
                if getattr(s, f) != getattr(ref, f)}
        assert diff == fields, name
    for name in ("train_nl", "val_nl", "test_id_nl"):
        s = SPLITS[name]
        assert (s.ibo_nominal, s.ibo_overdrive, s.bandwidth, s.amplifier) == (ID_NOMINAL, ID_OVERDRIVE, 36e6, "dvbs2_nl")
    for name in ("train_lin", "val_lin", "test_id_lin"):
        assert SPLITS[name].linear and "overdrive" not in SPLITS[name].labels


def test_unseen_ibo_split_never_draws_training_back_off():
    s = SPLITS["test_ibo"]
    for seed in list(s.seeds)[:200]:
        r = ranges_for(s, seed)
        assert r.ibo_nominal_db in s.ibo_nominal and r.ibo_overdrive_db in s.ibo_overdrive
        assert r.ibo_nominal_db[1] <= 9.0 or r.ibo_nominal_db[0] >= 13.0
        assert r.ibo_overdrive_db[1] <= 1.0 or r.ibo_overdrive_db[0] >= 4.0


def test_generate_writes_resumable_shards(tmp_path):
    generate(str(tmp_path), ["val_nl", "val_lin"], limit_seeds=2)
    nl, lin = load_split(tmp_path / "val_nl"), load_split(tmp_path / "val_lin")
    assert nl["spec"].dtype == np.float16 and nl["spec"].shape[1:] == (128, 512) and nl["mask"].shape[1:] == (512,)
    assert len(nl["meta"]) == len(nl["label"]) == len(nl["seed"])
    assert set(nl["seed"]) == set(lin["seed"]) == {200_000, 200_001}
    assert LABELS.index("overdrive") in nl["label"] and LABELS.index("overdrive") not in lin["label"]
    for d, linear in ((nl, False), (lin, True)):
        for m, lab in zip(d["meta"], d["label"]):
            assert m["label"] == LABELS[lab] and m["config"]["linear"] is linear
            lo, hi = (1.0, 4.0) if m["label"] == "overdrive" else (9.0, 13.0)
            assert lo <= m["config"]["ibo_db"] <= hi
    # the linear and non-linear versions of a seed share the carrier plan
    plan = {m["config"]["seed"]: m["plan"] for m in nl["meta"]}
    assert all(m["plan"] == plan[m["config"]["seed"]] for m in lin["meta"])
    manifest = json.loads((tmp_path / "val_nl" / "manifest.json").read_text())
    assert manifest["n_samples"] == len(nl["label"]) and manifest["complete"] is False
    before = (tmp_path / "val_nl" / "part-00000.npz").stat().st_mtime_ns
    generate(str(tmp_path), ["val_nl"], limit_seeds=2)                      # second run reuses the shard
    assert (tmp_path / "val_nl" / "part-00000.npz").stat().st_mtime_ns == before

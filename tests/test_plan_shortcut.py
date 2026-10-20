"""Plan-mask shortcut test (A5): perturbations change only the operator plan, as declared."""
import json
from dataclasses import asdict
from types import SimpleNamespace

import numpy as np
import pytest

pytest.importorskip("torch")

from geosim import dataset as ds
from geosim.classes import sample
from geosim.interferers import overlaps_plan
from geosim.plan import plan_mask_db
from geosim.scenario import default_plan
from geoml import pipeline, plan_shortcut as ps

UNAUTHORIZED = sample("unauthorized", 36e6, 300003)
CLEAN = sample("clean", 36e6, 300003)


def _meta(result):
    return json.loads(json.dumps(result.meta, default=float))


def test_shift_drop_phantom_and_authorize_change_the_plan_as_declared():
    meta = _meta(UNAUTHORIZED)
    plan = ps._plan(meta)
    shifted = ps.perturbed_plan(meta, "shift_plus", 1)
    assert [c.f0 - ps.SHIFT_HZ for c in shifted] == pytest.approx([c.f0 for c in plan])
    dropped = ps.perturbed_plan(meta, "drop_one", 1)
    assert len(dropped) == len(plan) - 1 and all(c in plan for c in dropped)
    phantom = ps.perturbed_plan(meta, "phantom", 1)
    extra = phantom[-1]
    assert phantom[:-1] == plan and not overlaps_plan(extra.f0 - extra.occupied_bw / 2, extra.f0 + extra.occupied_bw / 2, plan)
    authorized = ps.perturbed_plan(meta, "authorize_intruder", 1)
    assert authorized[-1].f0 == pytest.approx(meta["interferer"]["f0"])
    assert ps.perturbed_plan(_meta(CLEAN), "authorize_intruder", 1) is None
    assert ps.perturbed_plan(meta, "none", 1) == plan


def test_stored_masks_are_rebuilt_from_metadata_plans():
    d = {"mask": np.stack([r.mask_db.astype(np.float16) for r in (CLEAN, UNAUTHORIZED)]),
         "meta": [_meta(CLEAN), _meta(UNAUTHORIZED)]}
    assert ps.check_stored_masks(d) < 0.05
    d["mask"][0, :] += 1.0
    with pytest.raises(ValueError, match="differ from metadata plans"):
        ps.check_stored_masks(d)


def fake_sample(label, bandwidth, seed, ranges=None, linear=False, amplifier="dvbs2_nl"):
    rng = np.random.default_rng(seed + 11 * ds.LABELS.index(label))
    plan = default_plan(seed, bandwidth)
    mask = plan_mask_db(plan)
    spec = (-85 + rng.normal(size=(128, 512))).astype(np.float32) + np.maximum(mask, -40)[None, :]
    spec[:, 30 + 20 * ds.LABELS.index(label)] += 15
    interferer = {"kind": label}
    if label in ("cw", "swept_cw"):
        interferer["c_over_i_db"] = 10.0
    if label == "unauthorized":
        interferer.update(f0=-17e6, symbol_rate=1e6, alpha=0.2, mod="QPSK", c_over_i_db=20.0)
    return SimpleNamespace(spec_db=spec, mask_db=mask,
                           meta={"label": label, "interferer": interferer, "plan": [asdict(c) for c in plan],
                                 "config": {"seed": seed, "bandwidth": bandwidth, "linear": linear,
                                            "amplifier": amplifier, "ibo_db": 10.0}})


def test_shortcut_evaluation_reuses_stage_a_checkpoints(tmp_path, monkeypatch):
    monkeypatch.setattr(ds, "sample", fake_sample)
    data, runs, out = tmp_path / "data", tmp_path / "runs", tmp_path / "out"
    ds.generate(str(data), ["train_nl", "train_lin", "val_nl", "val_lin", "test_id_nl", "test_id_lin"], limit_seeds=4)
    pipeline.main(str(data), str(runs), epochs=1, seeds=[0], level="carrier", time_pool=8, log=lambda _: None)
    result = ps.main(str(data), str(runs), str(out), log=lambda _: None)
    perturbations = result["perturbations"]
    assert set(perturbations) == set(ps.PERTURBATIONS)
    assert perturbations["none"]["changed_vs_unperturbed"]["mean"] == 0.0
    assert perturbations["authorize_intruder"]["n_samples"] == 4          # unauthorized samples only
    assert perturbations["drop_one"]["n_samples"] == perturbations["none"]["n_samples"]
    json.loads((out / "results.json").read_text())
    assert "A5" in (out / "results.md").read_text()

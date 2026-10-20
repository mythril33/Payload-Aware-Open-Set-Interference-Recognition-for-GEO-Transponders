"""R1-eval/1 evaluator: calibration and ranking metrics, back-off regions, end-to-end reuse of Stage A."""
import json
from types import SimpleNamespace

import numpy as np
import pytest

pytest.importorskip("torch")

from geosim import dataset as ds
from geoml import pipeline, robustness
from geoml.metrics import expected_calibration_error
from geoml.openset_metrics import detection_ranking, ranking_metrics


def test_ece_matches_hand_computed_bins():
    probs = np.array([[0.9, 0.1], [0.8, 0.2], [0.6, 0.4], [0.55, 0.45]])
    labels = np.array([0, 1, 0, 0])
    result = expected_calibration_error(probs, labels, n_bins=2)
    # bin (0.5, 1]: confidences .9 .8 .6 .55 -> mean .7125, accuracy 3/4
    assert result["ece"] == pytest.approx(abs(0.75 - 0.7125))
    assert result["bins"][0] == {"lo": 0.0, "hi": 0.5, "n": 0, "accuracy": None, "confidence": None}
    assert result["bins"][1]["n"] == 4
    assert expected_calibration_error(np.eye(3), np.arange(3))["ece"] == 0.0
    with pytest.raises(ValueError):
        expected_calibration_error(np.array([[np.nan, 1.0]]), np.array([0]))


def test_fpr_at_95_tpr_uses_grouped_thresholds():
    # positives 1..20; negatives at 0.5 and 1.5 -> 95 % of positives need threshold <= 2
    positive = np.arange(1.0, 21.0)
    negative = np.array([0.5, 1.5, 30.0])
    result = detection_ranking(negative, positive)
    assert result["fpr_at_95_tpr"] == pytest.approx(1 / 3)
    assert detection_ranking(np.zeros(4), np.ones(4))["fpr_at_95_tpr"] == 0.0
    tied = detection_ranking(np.ones(3), np.ones(2))
    assert tied["fpr_at_95_tpr"] == 1.0 and tied["auroc"] == pytest.approx(0.5)
    open_set = ranking_metrics(negative, positive, np.ones(3, bool))
    assert open_set["unknown_fpr_at_95_tpr"] == result["fpr_at_95_tpr"]


@pytest.mark.parametrize("label,ibo,region,distance", [
    ("clean", 11.0, "train", 0.0), ("cw", 13.5, "near", 0.5), ("clean", 6.0, "gap", 3.0),
    ("unauthorized", 8.5, "near", 0.5), ("overdrive", 0.5, "near", 0.5), ("overdrive", 2.0, "train", 0.0),
    ("overdrive", 4.8, "near", 0.8), ("clean", 4.0, "far", 5.0)])
def test_ibo_regions_follow_the_a1_training_ranges(label, ibo, region, distance):
    assert robustness.ibo_region(label, ibo) == (region, pytest.approx(distance))


def fake_sample(label, bandwidth, seed, ranges=None, linear=False, amplifier="dvbs2_nl"):
    rng = np.random.default_rng(seed + 7 * ds.LABELS.index(label))
    spec = (-85 + rng.normal(size=(128, 512))).astype(np.float32)
    spec[:, 200:260] += 25
    spec[:, 30 + 20 * ds.LABELS.index(label)] += 15
    mask = np.full(512, -60., np.float32)
    mask[200:260] = 0
    lo, hi = ranges.ibo_overdrive_db if label == "overdrive" else ranges.ibo_nominal_db
    interferer = {"kind": label, "c_over_i_db": 10.0} if label in ("cw", "swept_cw") else {"kind": label}
    return SimpleNamespace(spec_db=spec, mask_db=mask,
                           meta={"label": label, "interferer": interferer,
                                 "config": {"seed": seed, "bandwidth": bandwidth, "linear": linear,
                                            "amplifier": amplifier, "ibo_db": float(rng.uniform(lo, hi))}})


def test_r1_evaluator_reuses_stage_a_checkpoints_and_writes_strict_json(tmp_path, monkeypatch):
    monkeypatch.setattr(ds, "sample", fake_sample)
    data, runs, r1, out = (tmp_path / name for name in ("data", "runs", "r1", "out"))
    a1 = ["train_nl", "train_lin", "val_nl", "val_lin", "test_id_nl", "test_id_lin"]
    ds.generate(str(data), a1, limit_seeds=4)
    ds.generate(str(r1), ["r1_ibo_sweep", "r1_amp_opendpd_dpa"], limit_seeds=6, protocol=ds.R1_PROTOCOL)
    pipeline.main(str(data), str(runs), epochs=1, seeds=[0], level="carrier", time_pool=8, log=lambda _: None)
    result = robustness.main(str(data), str(runs), str(r1), str(out), log=lambda _: None)
    stored = json.loads((out / "results.json").read_text())
    assert stored["protocol"] == "R1-eval/1" and set(stored["splits"]) == {"r1_ibo_sweep", "r1_amp_opendpd_dpa"}
    sweep = result["splits"]["r1_ibo_sweep"]
    assert sweep["n_samples"] == 30 and sweep["overdrive_as"] is not None
    assert result["splits"]["r1_amp_opendpd_dpa"]["overdrive_as"] is None
    assert sum(row["n_samples"] for row in sweep["ibo_bins"]) == sweep["n_samples"]
    assert {r for row in sweep["ibo_bins"] for r in row["regions"]} <= {"train", "near", "gap", "far"}
    assert 0 <= sweep["five_class"]["ece"]["mean"] <= 1
    assert sweep["detection"]["threshold_source"].startswith("val_nl")
    assert "R1-eval/1" in (out / "results.md").read_text()
    # a changed Stage A training split invalidates the evaluation instead of silently reusing weights
    stage_a = json.loads((runs / "results.json").read_text())
    stage_a["data_fingerprints"]["train_nl"] = "0" * 64
    (runs / "results.json").write_text(json.dumps(stage_a))
    with pytest.raises(ValueError, match="train_nl differs"):
        robustness.main(str(data), str(runs), str(r1), str(out), log=lambda _: None)
    # R1 data must not be mixed with A1 splits
    ds.generate(str(r1), ["val_nl"], limit_seeds=1)
    stage_a["data_fingerprints"]["train_nl"] = pipeline.split_fingerprint(data / "train_nl")
    (runs / "results.json").write_text(json.dumps(stage_a))
    with pytest.raises(ValueError, match="only R1-eval/1 splits"):
        robustness.main(str(data), str(runs), str(r1), str(out), log=lambda _: None)

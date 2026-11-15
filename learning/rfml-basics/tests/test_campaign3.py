"""Campaign-3 stages, runner and the replication pooling (PREREGISTRATION_V3.md)."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from rfml import experiments as ex
from rfml import experiments_v3 as v3

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "experiments" / "run_campaign3.py"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "experiments" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def arm_result():
    return v3.run_arm_control(ex.get_scale("quick"), seed=0)


@pytest.fixture(scope="module")
def split_result():
    return v3.run_split_counterfactual(ex.get_scale("quick"), seed=0)


def test_arm_control_is_strict_json_and_complete(arm_result):
    json.loads(ex.to_strict_json(arm_result))  # raises on NaN / Infinity
    variants = arm_result["variants"]
    expected = {"CE+distance", *(f"CE+mahalanobis@{s:g}" for s in v3.SHRINKAGE_SWEEP)}
    expected |= {name for name, _c, _o in ex.SCORER_BENCH_ARMS}
    assert set(variants) == expected
    for v in variants.values():
        assert set(v["per_unknown_class"]) == set(ex.UNKNOWN)
        assert sum(c["n"] for c in v["per_unknown_class"].values()) == v["report"]["n_unknown"]


def test_arms_share_one_training_seed(arm_result):
    seeds = {arm_result["variants"][name]["train_seed"] for name, _c, _o in ex.SCORER_BENCH_ARMS}
    assert seeds == {0 + v3.ARM_SHARED_OFFSET} == {arm_result["arm_train_seed"]}


def test_arms_differ_only_in_the_outlier_pool(arm_result):
    """Same known frames in every arm; the outlier counts are the manipulation."""
    arms = {name: arm_result["variants"][name] for name, _c, _o in ex.SCORER_BENCH_ARMS}
    known = {v["train_frames"] - v["train_outliers"] for v in arms.values()}
    assert len(known) == 1
    full, psk, pam = (arms[n]["train_outliers"] for n in ("OS-full+MSP", "OS-16PSK+MSP", "OS-8PAM+MSP"))
    assert psk > 0 and pam > 0 and full == psk + pam


def test_shrinkage_one_ranks_like_euclidean(arm_result):
    """At shrinkage 1 the covariance is a scaled identity: Mahalanobis = Euclidean / const."""
    euclid = arm_result["variants"]["CE+distance"]
    mahal = arm_result["variants"]["CE+mahalanobis@1"]
    assert mahal["report"]["auroc"] == pytest.approx(euclid["report"]["auroc"], abs=1e-12)
    ratio = np.asarray(mahal["scores"]["unknown"]) / np.asarray(euclid["scores"]["unknown"])
    assert np.allclose(ratio, ratio[0], rtol=1e-9)


def test_full_arm_reproduces_campaign2(arm_result):
    """Check of the pre-registration: same seed and data as campaign 2's full arm."""
    bench = ex.run_scorer_bench(ex.get_scale("quick"), seed=0)
    a, b = arm_result["variants"]["OS-full+MSP"], bench["variants"]["OS-full+MSP"]
    assert a["report"] == b["report"]
    assert a["scores"]["unknown"] == b["scores"]["unknown"]


def test_arm_control_is_deterministic(arm_result):
    again = v3.run_arm_control(ex.get_scale("quick"), seed=0)
    assert ex.to_strict_json(again) == ex.to_strict_json(arm_result)


def test_split_counterfactual_structure(split_result):
    json.loads(ex.to_strict_json(split_result))
    scale = ex.get_scale("quick")
    n_seen = len(ex.KNOWN) * scale.tx_train * v3.SEEN_FRAMES_PER_DEVICE * len(ex.MOD_TEST_SNRS)
    for name in ex.MODULATION_MODELS:
        m = split_result["models"][name]
        assert m["seen_devices_new_frames"]["overall"]["n"] == n_seen
        assert len(m["seen_devices_new_frames"]["per_snr"]) == len(ex.MOD_TEST_SNRS)
        for key in ("train_accuracy",):
            assert 0.0 <= m[key] <= 1.0


def test_unseen_accuracy_equals_campaign1(split_result):
    """Check of the pre-registration: the models are campaign 1's."""
    reference = ex.run_modulation(ex.get_scale("quick"), impaired=True, seed=0)
    for name in ex.MODULATION_MODELS:
        ours = split_result["models"][name]
        theirs = reference["models"][name]
        assert ours["unseen_devices"]["overall"] == theirs["overall"]
        assert ours["train_accuracy"] == theirs["train_accuracy"]


def test_seen_stream_does_not_touch_role_streams():
    """The seen-device stream must be independent of every role stream."""
    seen = np.random.default_rng(np.random.SeedSequence(entropy=0, spawn_key=v3.SEEN_SPAWN_KEY))
    draws = seen.standard_normal(8)
    for rng in ex.role_rngs(0).values():
        assert not np.allclose(rng.standard_normal(8), draws)


def test_runner_resumes_and_aggregates(tmp_path):
    out = tmp_path / "c3"
    cmd = [sys.executable, str(RUNNER), "--scale", "quick", "--seeds", "0", "1", "--out", str(out), "--threads", "2"]
    first = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=900, check=False)
    assert first.returncode == 0, first.stdout + first.stderr
    agg1 = json.loads((out / "aggregate.json").read_text())
    assert agg1["failures"] == []
    assert set(agg1["hypotheses"]) == {
        "H7s_pamarm_minus_pskarm_4pam_reject_shared_seed",
        "H9_mlp_seen_minus_unseen_acc",
        "H10_cnn_seen_minus_unseen_acc",
    }
    for h in agg1["hypotheses"].values():
        assert h["n_seeds"] == 2 and h["supported"] is None  # verdict only at 5 or 10 seeds
        assert h["n_positive"] == sum(d > 0 for d in h["per_seed_diff"])
    assert "scores" not in json.loads((out / "arm_control_seed0.json").read_text())["variants"]["CE+distance"]

    second = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=900, check=False)
    assert second.returncode == 0, second.stdout + second.stderr
    assert "loaded arm_control_seed0.json" in second.stdout
    agg2 = json.loads((out / "aggregate.json").read_text())
    assert agg2["metrics"] == agg1["metrics"] and agg2["hypotheses"] == agg1["hypotheses"]


def _fake_aggregate(seeds, diffs):
    return {
        "provenance": {"seeds": seeds, "scale": {"name": "full"}},
        "failures": [],
        "metrics": {"stage": {"m": {"per_seed": [float(s) for s in seeds]}}},
        "hypotheses": {
            "H": {
                "per_seed_diff": diffs,
                "n_positive": sum(d > 0 for d in diffs),
                "n_seeds": len(diffs),
                "supported": sum(d > 0 for d in diffs) >= 4,
            }
        },
    }


def test_pooling_counts_and_verdicts():
    pool = _load("pool_replication").pool
    pooled = pool(
        _fake_aggregate([0, 1, 2, 3, 4], [0.1, 0.2, 0.3, 0.4, -0.1]),
        _fake_aggregate([5, 6, 7, 8, 9], [0.1, -0.2, -0.3, 0.4, 0.5]),
    )
    h = pooled["hypotheses"]["H"]
    assert h["original"]["supported"] is True
    assert h["replication"]["n_positive"] == 3 and h["replicated"] is False
    assert h["pooled"] == {"n_positive": 7, "n_seeds": 10, "required_positive": 8, "supported": False}
    assert pooled["metrics"]["stage"]["m"]["mean"] == pytest.approx(4.5)
    assert pooled["metrics"]["stage"]["m"]["sd"] == pytest.approx(np.std(np.arange(10), ddof=1))


def test_pooling_refuses_overlap_and_failures():
    pool = _load("pool_replication").pool
    a = _fake_aggregate([0, 1, 2, 3, 4], [0.1] * 5)
    with pytest.raises(ValueError, match="overlap"):
        pool(a, _fake_aggregate([4, 5, 6, 7, 8], [0.1] * 5))
    failed = _fake_aggregate([5, 6, 7, 8, 9], [0.1] * 5)
    failed["failures"] = [{"seed": 5, "stage": "x", "error": "boom"}]
    with pytest.raises(ValueError, match="failures"):
        pool(a, failed)


def test_required_positive_matches_the_preregistration():
    need = _load("run_campaign3").required_positive
    assert need(5) == 4 and need(10) == 8

"""Checks for model inputs, metrics and the CFAR baseline (P6, P7)."""
import numpy as np
import pytest

from geoml import cfar
from geoml.data import preprocess, reference_level, select
from geoml.metrics import cluster_ci, confusion, macro_f1, threshold_at_pfa
from geosim.plan import monitor_freqs


def _toy(n=6, seed=0):
    rng = np.random.default_rng(seed)
    mask = np.full((n, 512), -60.0, np.float16)
    mask[:, 200:260] = 0.0
    spec = (-90 + rng.normal(0, 1, (n, 128, 512))).astype(np.float16)
    spec[:, :, 200:260] += 25
    return spec, mask


def test_carrier_level_normalisation_removes_absolute_power():
    spec, mask = _toy()
    a = preprocess(spec, mask)
    b = preprocess((spec.astype(np.float32) + 7.5).astype(np.float16), mask)       # a 7.5 dB fade
    assert a.shape == (6, 2, 64, 512) and a.dtype == np.float32
    assert np.abs(a - b).max() < 0.01
    assert abs(reference_level(spec, mask).mean() + 65) < 1.0
    c = preprocess(spec, mask, level="absolute", absolute_ref_db=-65.0)
    d = preprocess((spec.astype(np.float32) + 7.5).astype(np.float16), mask, level="absolute", absolute_ref_db=-65.0)
    assert np.abs((d - c)[:, 0].mean() - 7.5 / 20) < 0.02                           # absolute mode keeps it


def test_select_reindexes_labels():
    d = {"spec": np.zeros((4, 1, 1)), "mask": np.zeros((4, 1)), "seed": np.arange(4),
         "label": np.array([0, 4, 1, 3]), "meta": list("abcd")}
    s = select(d, ("clean", "unauthorized"), ("clean", "cw", "swept_cw", "unauthorized", "overdrive"))
    assert s["label"].tolist() == [0, 1] and s["meta"] == ["a", "d"]


def test_metrics():
    y, p = np.array([0, 0, 1, 1, 2, 2]), np.array([0, 1, 1, 1, 2, 0])
    assert confusion(y, p, 3).tolist() == [[1, 1, 0], [0, 2, 0], [1, 0, 1]]
    assert abs(macro_f1(y, p, 3) - np.mean([0.5, 0.8, 2 / 3])) < 1e-9
    assert macro_f1(np.array([0, 0]), np.array([0, 1]), 3) == pytest.approx(2 / 3)   # absent classes ignored
    lo, hi = cluster_ci(np.array([1, 1, 0, 0, 1, 0.0]), np.array([1, 1, 2, 2, 3, 3]))
    assert 0 <= lo < 0.5 < hi <= 1
    assert threshold_at_pfa(np.arange(100.0), 0.05) == pytest.approx(94.05)


def test_cfar_finds_a_tone_and_plan_awareness_ignores_carrier_edges():
    spec, mask = _toy()
    f, bw = monitor_freqs(), np.full(6, 72e6)
    plain = cfar.features(spec, mask, f, bw, use_plan=False)
    aware = cfar.features(spec, mask, f, bw, use_plan=True)
    # at a 25 dB carrier edge half the training cells are high, so a plain CA-CFAR reads about 3 dB
    assert 2.5 < plain[:, 0].mean() < 3.6 and aware[:, 0].mean() < 1.5
    spec[3, :, 120] += 12                                              # a steady tone in a gap
    aware = cfar.features(spec, mask, f, bw, use_plan=True)
    s = cfar.scores(aware, np.delete(aware, 3, axis=0))
    assert s.argmax() == 3 and s[3] > 10


def test_model_forward():
    torch = pytest.importorskip("torch")
    from geoml.model import SmallResNet, n_parameters
    m = SmallResNet(5)
    assert m(torch.zeros(2, 2, 64, 512)).shape == (2, 5) and 2e5 < n_parameters(m) < 2e6

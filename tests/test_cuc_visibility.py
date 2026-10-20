"""Carrier-under-carrier visibility script: estimation noise and a strong-event sanity check."""
import importlib.util
import pathlib

import numpy as np

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "cuc_visibility.py"
spec = importlib.util.spec_from_file_location("cuc_visibility", SCRIPT)
cuc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cuc)


def test_band_mean_has_no_noise_for_a_constant_spectrum():
    spec = np.full((128, 512), -20.0)
    sel = np.zeros(512, bool)
    sel[10:20] = True
    mean, rel_sigma = cuc.band_mean(spec, sel)
    assert np.isclose(mean, 0.01) and rel_sigma == 0.0


def test_strong_under_carrier_raises_its_band_and_is_visible():
    result = cuc.measure(seeds=(600_000,), levels=(5.0,))
    row = result["rows"][0]
    assert row["n_bins"] > 0 and row["delta_db"] > 1.0 and row["visible_3sigma"]
    assert result["summary"][0]["n"] == 1

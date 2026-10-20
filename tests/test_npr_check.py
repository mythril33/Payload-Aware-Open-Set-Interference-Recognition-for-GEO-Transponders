"""NPR script: measurement floor, monotone TWTA curve and the Rapp fifth-order slope."""
import importlib.util
import pathlib

import numpy as np

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "npr_check.py"
spec = importlib.util.spec_from_file_location("npr_check", SCRIPT)
npr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(npr)


def test_notched_noise_has_unit_power_and_a_deep_notch():
    x = npr.notched_noise(np.random.default_rng(1))
    assert abs(np.mean(np.abs(x) ** 2) - 1) < 1e-9
    assert npr.npr_db(x) > 45


def test_npr_rises_with_back_off_and_follows_the_leading_distortion_order():
    result = npr.sweep(names=("dvbs2_nl", "rapp_p2"), ibos=(10.0, 12.0, 14.0))
    twta = [r["npr_db"] for r in result["amplifiers"]["dvbs2_nl"]["rows"]]
    assert twta == sorted(twta) and all(r["linear_npr_db"] > 45 for r in result["amplifiers"]["dvbs2_nl"]["rows"])
    # Rapp p = 2 has no third-order term: its leading product is fifth order (towards 4 dB/dB)
    assert result["amplifiers"]["rapp_p2"]["slope_db_per_db_ibo_10_14"] > 2.5
    assert result["amplifiers"]["rapp_p2"]["rows"][0]["input_beyond_measured"] is None

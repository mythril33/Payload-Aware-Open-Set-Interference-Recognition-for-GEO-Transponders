"""OpenDPD probe script: basis construction and recovery of a known memory polynomial."""
import importlib.util
import json
import pathlib

import numpy as np

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "opendpd_probe.py"
spec = importlib.util.spec_from_file_location("opendpd_probe", SCRIPT)
probe_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe_mod)


def _write(path, z):
    np.savetxt(path, np.c_[z.real, z.imag], delimiter=",", header="I,Q", comments="")


def test_basis_delays_with_zero_initial_state():
    x = np.array([1 + 1j, 2, 3j])
    b = probe_mod.basis(x, 2, 1)
    assert b.shape == (3, 4)
    np.testing.assert_allclose(b[:, 2], [0, 1 + 1j, 2])            # x[n-1]
    np.testing.assert_allclose(b[:, 3], [0, (1 + 1j) * np.sqrt(2), 4])  # x[n-1]|x[n-1]|


def test_probe_recovers_memory_polynomial_and_reports_strict_json(tmp_path):
    rng = np.random.default_rng(0)
    x = (rng.standard_normal(6000) + 1j * rng.standard_normal(6000)) * 0.3
    c = np.zeros(5 * 5, complex)
    c[0], c[2], c[5], c[7] = 1.0, -0.2 + 0.05j, 0.1j, -0.03
    # Each split is a separate record with zero initial state, as the probe assumes.
    for split, sl in (("train", slice(0, 4000)), ("test", slice(4000, None))):
        _write(tmp_path / f"{split}_input.csv", x[sl])
        _write(tmp_path / f"{split}_output.csv", probe_mod.basis(x[sl], 5, 4) @ c)
    out = probe_mod.probe(tmp_path)
    json.dumps(out, allow_nan=False)
    assert out["n_train"] == 4000 and out["n_test"] == 2000
    assert out["nmse_memory_poly_K5_M4_db"] < -100
    assert out["nmse_memoryless_K5_db"] > out["nmse_memory_poly_K5_M4_db"] + 10

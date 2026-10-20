"""R1-eval/1 amplifier families: Rapp SSPA and OpenDPD-derived memory polynomials."""
import json

import numpy as np
import pytest

from geosim import payload as pl
from geosim.classes import sample

DATA = json.loads((pl.DATA / "opendpd_mp.json").read_text())


def test_rapp_matches_closed_form_and_saturates_without_am_pm():
    amp = pl.amplifier("rapp_p2")
    r = np.array([1e-3, 0.3, 1.0, 2.0, 10.0])
    y = amp(r.astype(np.complex128))
    expected = r / (1 + r ** (2 * pl.RAPP_P)) ** (1 / (2 * pl.RAPP_P))
    np.testing.assert_allclose(np.abs(y), expected, rtol=2e-3)
    assert np.allclose(np.angle(y), 0.0)
    assert np.all(np.diff(np.abs(amp(np.linspace(0, 20, 400).astype(np.complex128)))) >= 0)
    assert np.abs(amp(np.array([1e3 + 0j]))).max() <= 1.0 + 1e-9
    assert amp.r_sat == amp.a_max == amp.small_signal_gain == 1.0


def test_memory_polynomial_matches_its_regression_basis():
    rng = np.random.default_rng(0)
    order, delays = 3, (0, 2, 5)
    c = rng.normal(size=(len(delays), order)) + 1j * rng.normal(size=(len(delays), order))
    amp = pl.MemoryPolynomialAmplifier("test", 1.0, 1.0, 1.0, None, tuple(map(tuple, c)), delays)
    x = (rng.normal(size=(3, 64)) + 1j * rng.normal(size=(3, 64))).astype(np.complex128)
    np.testing.assert_allclose(amp(x), pl.mp_basis(x, order, delays) @ c.reshape(-1), rtol=1e-12, atol=1e-12)
    # each record starts from a zero state: a later record never leaks into an earlier one
    np.testing.assert_allclose(amp(x[1:2]), amp(x)[1:2])


def test_memory_polynomial_holds_edge_gain_beyond_measured_amplitude():
    c = ((1.0, 0.0, -0.1),)
    amp = pl.MemoryPolynomialAmplifier("test", 1.0, 1.0, 1.0, None, c, (0,), 2.0)
    x = np.array([1.0, 2.0, 4.0, 8.0], np.complex128)
    y = amp(x)
    edge_gain = 1.0 - 0.1 * 2.0 ** 2
    np.testing.assert_allclose(y[2:], x[2:] * edge_gain)
    np.testing.assert_allclose(y[:2], x[:2] * (1 - 0.1 * np.abs(x[:2]) ** 2))
    assert amp.out_of_range_fraction(x) == 0.5


@pytest.mark.parametrize("name", ["opendpd_apa", "opendpd_dpa"])
def test_opendpd_models_are_traceable_and_selected_on_validation(name):
    source, model = DATA["source"], DATA["models"][name]
    assert source["license"] == "Apache-2.0" and len(source["commit"]) == 40
    assert set(model["files_sha256"]) == {f"{s}_{io}.csv" for s in ("train", "val", "test") for io in ("input", "output")}
    n = model["order"] * (model["memory"] + 1)
    assert len(model["coefficients_re"]) == len(model["coefficients_im"]) == n
    grid = model["selection"]["grid"]
    best = min(g["val_nmse_db"] for g in grid)
    eligible = [g for g in grid if g["val_nmse_db"] <= best + 0.1]
    assert n == min(g["n_coefficients"] for g in eligible)
    assert "test_nmse_db" not in json.dumps(grid)
    amp = pl.amplifier(name)
    assert list(amp.delays) == sorted(set(amp.delays)) and amp.delays[0] == 0
    assert np.isfinite(amp.clip) and amp.r_sat == pytest.approx(10 ** (pl.OPENDPD_IBO_REF_DB / 20))


@pytest.mark.parametrize("name", ["opendpd_apa", "opendpd_dpa", "rapp_p2"])
def test_new_amplifiers_run_through_the_chain(name):
    result = sample("clean", 36e6, 420001, amplifier=name)
    assert np.isfinite(result.spec_db).all() and result.meta["config"]["amplifier"] == name
    beyond = result.meta.get("amplifier_input_beyond_measured")
    if name.startswith("opendpd"):
        assert 0.0 <= beyond < 0.01
    else:
        assert beyond is None


def test_a1_amplifiers_keep_their_metadata():
    result = sample("cw", 36e6, 300001)
    assert "amplifier_input_beyond_measured" not in result.meta
    assert set(result.meta) == {"config", "plan", "actual_ibo_db", "obo_db", "has_interferer",
                                "label", "interferer", "ibo_nominal_db"}

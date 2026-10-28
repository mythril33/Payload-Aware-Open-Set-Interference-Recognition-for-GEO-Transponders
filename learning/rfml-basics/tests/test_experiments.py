"""Fast tests for rfml.experiments: the stage logic behind app.py and the lessons.

Tests use a tiny custom Scale (a few devices, one epoch) so that the whole file runs in
well under a minute. The sizes of the real presets are checked against the lessons.
"""

from __future__ import annotations

import io
import json
from dataclasses import replace

import numpy as np
import pytest
import torch
from matplotlib.figure import Figure
from rfml import experiments as ex
from rfml.signals import constellation

TINY = ex.Scale(
    name="tiny",
    description="test only",
    tx_train=2,
    tx_val=2,
    tx_test=2,
    tx_aux=1,
    tx_unknown=1,
    frames_train=2,
    frames_val=2,
    frames_test=2,
    fp_devices=2,
    fp_frames=10,
    epochs=1,
)


@pytest.fixture(autouse=True)
def _single_torch_thread():
    """Tiny runs are faster on one thread, and it avoids OpenMP spin-wait stalls under load."""
    previous = torch.get_num_threads()
    torch.set_num_threads(1)
    yield
    torch.set_num_threads(previous)


def _strict(result: dict) -> str:
    """Round-trip through strict JSON. A NaN or inf anywhere raises ValueError."""
    return json.dumps(result, allow_nan=False)


def _same_frames(a: dict, b: dict) -> bool:
    return all(np.array_equal(a[k], b[k]) for k in ("iq", "label", "tx_id", "snr_db"))


# ---------------------------------------------------------------------------
# Scales and seeds
# ---------------------------------------------------------------------------


def test_presets_match_lesson_sizes():
    full = ex.get_scale("full")
    assert (full.tx_train, full.tx_val, full.tx_test) == (40, 10, 10)
    assert (full.frames_train, full.frames_val, full.frames_test) == (20, 10, 10)
    assert (full.tx_aux, full.tx_unknown) == (20, 10)
    assert (full.fp_devices, full.fp_frames) == (10, 300)
    assert (full.epochs, full.patience) == (25, 5)

    quick = ex.get_scale("quick")  # mirrors --quick in lessons 02-04
    assert (quick.tx_train, quick.tx_val, quick.tx_test) == (6, 3, 3)
    assert (quick.frames_train, quick.frames_val, quick.frames_test) == (5, 3, 3)
    assert (quick.tx_aux, quick.tx_unknown, quick.epochs) == (3, 3, 2)
    assert (quick.fp_devices, quick.fp_frames) == (4, 40)


def test_get_scale_rejects_unknown_name():
    with pytest.raises(ValueError, match="unknown scale"):
        ex.get_scale("huge")


def test_scale_rejects_bad_sizes():
    with pytest.raises(ValueError, match="tx_val"):
        replace(TINY, tx_val=1)  # validation devices must split into select and calib
    with pytest.raises(ValueError, match="epochs"):
        replace(TINY, epochs=0)


def test_role_rngs_are_stable_and_independent():
    a = ex.role_rngs(7)
    b = ex.role_rngs(7)
    assert a.keys() == set(ex.ROLES)
    assert a["os.train"].integers(0, 10**9) == b["os.train"].integers(0, 10**9)
    first = {name: ex.role_rngs(7)[name].integers(0, 10**9) for name in ex.ROLES}
    assert len(set(first.values())) == len(first)  # every role starts from its own stream
    assert ex.role_rngs(8)["os.train"].integers(0, 10**9) != first["os.train"]


def test_to_strict_json_rejects_nan():
    assert json.loads(ex.to_strict_json({"a": 1.5}))["a"] == 1.5
    with pytest.raises(ValueError):
        ex.to_strict_json({"a": float("nan")})


# ---------------------------------------------------------------------------
# Stage 1: gradient demo and frame display
# ---------------------------------------------------------------------------


def test_gradient_demo_strict_json_and_gradient_check():
    result = ex.run_gradient_demo(0.1, 200, 0)
    _strict(result)
    assert result["diverged"] is False and result["diverged_at_step"] is None
    assert len(result["loss_history"]) == 201  # loss before any update, then one per update
    assert result["loss_history"][-1] < result["loss_history"][0]
    assert result["grad_check_max_abs_diff"] < 1e-4  # hand formula matches autograd
    assert abs(result["w"] - result["least_squares"]["w"]) < 1e-2
    assert abs(result["b"] - result["least_squares"]["b"]) < 1e-2


def test_gradient_demo_reports_divergence_above_stability_bound():
    result = ex.run_gradient_demo(1.5, 200, 0)  # bound is about 1.0 for this design matrix
    assert result["stability_lr_bound"] < 1.5
    assert result["diverged"] is True
    assert result["w"] is None and result["b"] is None
    _strict(result)


def test_gradient_demo_rejects_bad_arguments():
    for lr in (0.0, -0.1, float("nan")):
        with pytest.raises(ValueError):
            ex.run_gradient_demo(lr, 10, 0)
    with pytest.raises(ValueError):
        ex.run_gradient_demo(0.1, 0, 0)


def test_show_frames_arrays_and_spectrum():
    frames = ex.show_frames(("BPSK", "16QAM"), 10.0, True, 256, 1)
    assert frames["freq"].shape == (256,) and frames["freq"].min() >= -0.5 and frames["freq"].max() < 0.5
    assert [f["modulation"] for f in frames["frames"]] == ["BPSK", "16QAM"]
    for frame in frames["frames"]:
        assert frame["i"].shape == frame["q"].shape == (256,)
        assert np.all(np.isfinite(frame["psd_db"]))
        assert np.array_equal(frame["ideal"], constellation(frame["modulation"]))
        assert set(frame["device"]) >= {"iq_gain", "pa_saturation", "phase_noise_std"}


def test_show_frames_ideal_device_has_no_impairments():
    frames = ex.show_frames(("QPSK",), 20.0, False, 128, 0)
    device = frames["frames"][0]["device"]
    assert device["iq_gain"] == 1.0 and device["iq_phase_deg"] == 0.0
    assert device["pa_saturation"] is None  # None means no compression
    with pytest.raises(ValueError):
        ex.show_frames(("XX",), 10.0, True, 128, 0)


# ---------------------------------------------------------------------------
# Stages 2-4: strict output, progress and counts
# ---------------------------------------------------------------------------


def test_run_modulation_strict_json_progress_and_counts():
    messages: list[str] = []
    result = ex.run_modulation(TINY, True, 2, ("MLP", "CNN1D"), progress=messages.append)
    _strict(result)
    assert result["chance_level"] == 0.25
    assert set(result["models"]) == {"MLP", "CNN1D"}
    cnn = result["models"]["CNN1D"]
    assert len(cnn["per_snr"]) == len(ex.MOD_TEST_SNRS)
    assert all(row["n"] == 4 * 2 * 2 for row in cnn["per_snr"])  # 4 modulations x 2 devices x 2 frames
    assert cnn["overall"]["n"] == sum(row["n"] for row in cnn["per_snr"])
    assert int(np.sum(cnn["confusion_overall"])) == cnn["overall"]["n"]
    assert any("dönem" in m for m in messages)  # progress reached the callback


def test_run_modulation_reports_none_for_empty_bins():
    # With no test frames, accuracy must be None (with n = 0), never NaN.
    per_snr, overall, _ = ex._evaluate_modulation(
        ex.MODEL_BUILDERS["CNN1D"](),
        {
            snr: {
                "iq": np.zeros((0, 2, ex.N_SAMPLES), dtype=np.float32),
                "label": np.zeros(0, dtype=np.int64),
            }
            for snr in ex.MOD_TEST_SNRS
        },
    )
    assert per_snr[0] == {"snr_db": ex.MOD_TEST_SNRS[0], "n": 0, "accuracy": None}
    assert overall == {"n": 0, "accuracy": None}


def test_run_fingerprint_strict_json_and_counts():
    for impaired in (True, False):
        result = ex.run_fingerprint(TINY, impaired, 3)
        _strict(result)
        assert result["chance_level"] == 0.5
        assert sum(result["frames"].values()) == 2 * 10  # 2 devices x 10 frames, no frame lost
        assert result["overall"]["n"] == result["frames"]["test"]
        assert result["devices_in_test"] <= 2


def test_run_open_set_strict_json_and_counts():
    result = ex.run_open_set(TINY, 4, 10.0, 0.1, 0.95)
    _strict(result)
    assert set(result["variants"]) == {"CE + MSP", "CE + distance", "Objectosphere + MSP"}
    assert result["chance"] == {"closed_set": 0.25, "auroc": 0.5}
    for v in result["variants"].values():
        rep = v["report"]
        assert rep["n_known"] == len(v["scores"]["known"]) == 16  # 4 classes x 2 devices x 2 frames
        assert rep["n_unknown"] == len(v["scores"]["unknown"]) == 4  # 2 classes x 1 device x 2 frames
        assert np.isfinite(v["threshold"]) and v["threshold"] == rep["threshold"]
        assert v["known_accepted"] == v["closed_set_on_accepted"]["n"]  # accepted known frames
        assert 0 <= v["known_accepted"] <= rep["n_known"]
        assert 0 <= v["unknown_rejected"] <= rep["n_unknown"]


def test_run_open_set_rejects_bad_arguments():
    with pytest.raises(ValueError):
        ex.run_open_set(TINY, 0, 10.0, 0.1, 0.0)  # target must lie in (0, 1]
    with pytest.raises(ValueError):
        ex.run_open_set(TINY, 0, 0.0, 0.1, 0.95)  # xi must be positive


def test_same_seed_gives_identical_numbers():
    assert ex.run_gradient_demo(0.1, 50, 5) == ex.run_gradient_demo(0.1, 50, 5)
    assert ex.run_modulation(TINY, True, 3, ("CNN1D",)) == ex.run_modulation(TINY, True, 3, ("CNN1D",))
    assert ex.run_fingerprint(TINY, True, 3) == ex.run_fingerprint(TINY, True, 3)
    assert ex.run_open_set(TINY, 4, 10.0, 0.1, 0.95) == ex.run_open_set(TINY, 4, 10.0, 0.1, 0.95)


def test_different_seed_changes_numbers():
    a = ex.run_gradient_demo(0.1, 50, 0)
    b = ex.run_gradient_demo(0.1, 50, 1)
    assert a["x"] != b["x"]


# ---------------------------------------------------------------------------
# Role independence (the seed scheme), through the public build_* helpers
# ---------------------------------------------------------------------------


def test_build_modulation_roles_are_independent():
    train, val, test_a = ex.build_modulation_data(TINY, True, 5)
    train_b, val_b, test_b = ex.build_modulation_data(replace(TINY, tx_test=5), True, 5)
    assert _same_frames(train, train_b)  # the test pool size cannot touch training data
    assert _same_frames(val, val_b)
    snr = ex.MOD_TEST_SNRS[0]
    assert test_a[snr]["label"].size != test_b[snr]["label"].size


def test_build_open_set_roles_are_independent():
    base = ex.build_open_set_data(TINY, 9)
    unknown_bigger = ex.build_open_set_data(replace(TINY, tx_unknown=3), 9)
    for key in ("train_known", "train_aux", "val_select", "val_calib", "test_known"):
        assert _same_frames(base[key], unknown_bigger[key]), key
    assert base["test_unknown"]["label"].size != unknown_bigger["test_unknown"]["label"].size

    aux_bigger = ex.build_open_set_data(replace(TINY, tx_aux=2), 9)
    assert _same_frames(base["train_known"], aux_bigger["train_known"])
    assert _same_frames(base["val_calib"], aux_bigger["val_calib"])


def test_unknown_pool_size_does_not_change_threshold():
    """Unknown frames are scored only after calibration, so their count cannot move the threshold."""
    small = ex.run_open_set(TINY, 4, 10.0, 0.1, 0.95)
    large = ex.run_open_set(replace(TINY, tx_unknown=3), 4, 10.0, 0.1, 0.95)
    for name in small["variants"]:
        a, b = small["variants"][name], large["variants"][name]
        assert a["threshold"] == b["threshold"]
        assert a["n_calib_known"] == b["n_calib_known"]
        assert a["known_accepted"] == b["known_accepted"]
        assert a["report"]["n_known"] == b["report"]["n_known"]
        assert a["report"]["n_unknown"] != b["report"]["n_unknown"]


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------


def _render(fig: Figure) -> None:
    assert isinstance(fig, Figure)
    buf = io.BytesIO()
    fig.savefig(buf, format="png")  # proves the figure renders without pyplot
    assert buf.getbuffer().nbytes > 1000


def test_figure_helpers_return_renderable_figures():
    gradient = ex.run_gradient_demo(0.1, 30, 0)
    _render(ex.fig_gradient(gradient))
    _render(ex.fig_frames(ex.show_frames(("BPSK", "QPSK"), 10.0, True, 128, 0)))
    modulation = ex.run_modulation(TINY, True, 2, ("CNN1D",))
    _render(ex.fig_modulation(modulation))
    _render(ex.fig_fingerprint([ex.run_fingerprint(TINY, True, 2), ex.run_fingerprint(TINY, False, 2)]))
    _render(ex.fig_open_set(ex.run_open_set(TINY, 2, 10.0, 0.1, 0.95)))


def test_figure_helper_handles_diverged_gradient_run():
    _render(ex.fig_gradient(ex.run_gradient_demo(1.5, 100, 0)))


def test_experiments_module_does_not_import_pyplot():
    """Figures must not touch pyplot's global state (Streamlit and lessons both rely on this)."""
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(ex))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""] + [f"{node.module}.{alias.name}" for alias in node.names]
        else:
            continue
        assert not any(name == "matplotlib.pyplot" or name.startswith("matplotlib.pyplot.") for name in names)

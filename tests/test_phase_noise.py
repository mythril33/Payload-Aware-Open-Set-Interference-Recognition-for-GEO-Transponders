"""Wiener increment laws, sparse-window continuity and common-LO rotations."""
import copy

import numpy as np
import pytest

from geosim.phase_noise import rotate_phase, wiener_phase


def test_within_window_and_gap_increments_have_declared_variance():
    fs, linewidth = 2000., .7
    count, n, interval = 40000, 4, .01
    phase = wiener_phase(np.random.default_rng(381), np.arange(count) * interval, n, fs, linewidth)
    within = np.diff(phase, axis=1).reshape(-1)
    gaps = phase[1:, 0] - phase[:-1, -1]
    for increments, elapsed in ((within, 1 / fs), (gaps, interval - (n - 1) / fs)):
        variance = 2 * np.pi * linewidth * elapsed
        assert np.mean(increments) == pytest.approx(0., abs=5 * np.sqrt(variance / increments.size))
        assert np.var(increments, ddof=1) == pytest.approx(variance, rel=.025)
    assert phase.dtype == np.float64 and phase[0, 0] == 0.


def test_single_sample_windows_walk_across_long_unobserved_intervals():
    # Only 12000 values are requested even though the corresponding dense
    # simulation at 288 MHz would span over ten trillion samples.
    interval, linewidth = 10., .2
    starts = np.arange(12000) * interval + 123.
    phase = wiener_phase(np.random.default_rng(95), starts, 1, 288e6, linewidth)
    increments = np.diff(phase[:, 0])
    assert phase.shape == (starts.size, 1) and phase[0, 0] == 0.
    assert np.var(increments, ddof=1) == pytest.approx(2 * np.pi * linewidth * interval, rel=.04)
    assert np.count_nonzero(phase[1:, 0]) == starts.size - 1


def test_dense_and_split_sampling_obey_the_same_brownian_increment_law():
    # Independent draws need not be bit-identical when sample grouping changes.
    count, fs, linewidth = 30000, 1000., .5
    dense = wiener_phase(np.random.default_rng(73), [0.], 2 * count - 1, fs, linewidth)[0, ::2]
    sparse = wiener_phase(np.random.default_rng(74), np.arange(count) * 2 / fs, 1, fs, linewidth)[:, 0]
    variance = 2 * np.pi * linewidth * 2 / fs
    assert np.var(np.diff(dense), ddof=1) == pytest.approx(variance, rel=.035)
    assert np.var(np.diff(sparse), ddof=1) == pytest.approx(variance, rel=.035)


def test_seed_replay_and_arbitrary_first_time_reference():
    starts = np.array([.02, .03, .07])
    first = wiener_phase(np.random.default_rng(4), starts, 7, 1000., 3.)
    second = wiener_phase(np.random.default_rng(4), starts, 7, 1000., 3.)
    shifted = wiener_phase(np.random.default_rng(4), starts - starts[0], 7, 1000., 3.)
    np.testing.assert_array_equal(first, second)
    np.testing.assert_allclose(first, shifted, rtol=0, atol=2e-15)
    assert first[0, 0] == 0.
    assert not np.all(first[:, 0] == 0.)


def test_zero_linewidth_is_exact_and_does_not_consume_rng():
    rng = np.random.default_rng(190)
    state = copy.deepcopy(rng.bit_generator.state)
    phase = wiener_phase(rng, [0., .01, .02], 17, 288e6, 0.)
    np.testing.assert_array_equal(phase, np.zeros((3, 17), dtype=np.float64))
    assert rng.bit_generator.state == state
    assert rng.normal() == np.random.default_rng(190).normal()


def test_contiguous_windows_and_a_single_reference_sample_are_valid():
    phase = wiener_phase(np.random.default_rng(10), [0., .003], 3, 1000., .2)
    assert phase.shape == (2, 3) and np.isfinite(phase).all()
    np.testing.assert_array_equal(wiener_phase(np.random.default_rng(10), [7.], 1, 1000., .2), [[0.]])


@pytest.mark.parametrize("dtype", [np.complex64, np.complex128])
def test_common_phase_rotation_preserves_sample_power_and_polarization_ratio(dtype):
    rng = np.random.default_rng(76)
    iq = (rng.normal(size=(2, 3, 15)) + 1j * rng.normal(size=(2, 3, 15))).astype(dtype)
    phase = wiener_phase(rng, [0., .01, .02], 15, 288e6, 30.)
    before, angle_before = iq.copy(), phase.copy()
    rotated = rotate_phase(iq, phase)
    tolerance = 5e-7 if dtype == np.complex64 else 1e-14
    assert rotated.shape == iq.shape and rotated.dtype == iq.dtype
    np.testing.assert_allclose(abs(rotated)**2, abs(iq)**2, rtol=tolerance)
    np.testing.assert_allclose(rotated[0] / rotated[1], iq[0] / iq[1], rtol=tolerance)
    np.testing.assert_array_equal(iq, before)
    np.testing.assert_array_equal(phase, angle_before)


def test_unit_input_is_unit_modulus_and_leading_dimensions_broadcast():
    phase = np.arange(12).reshape(3, 4) * 1.37
    rotated = rotate_phase(np.ones((5, 2, 3, 4), complex), phase)
    np.testing.assert_allclose(abs(rotated), 1., atol=2e-16, rtol=0)
    np.testing.assert_array_equal(rotated[0, 0], rotated[-1, -1])
    zero = np.array([[0., 1. + 2.j]], dtype=np.complex64)
    np.testing.assert_array_equal(rotate_phase(zero, np.zeros((1, 2))), zero)


@pytest.mark.parametrize("starts", [[], [0., 0.], [1., 0.], [-1.], [np.nan], [np.inf],
                                     [[0., 1.]], [0., .001], [0., .002], [True], ["0"], [1j]])
def test_invalid_snapshot_times_fail(starts):
    with pytest.raises(ValueError):
        wiener_phase(np.random.default_rng(1), starts, 3, 1000., .1)


@pytest.mark.parametrize("parameter,value", [("n", 0), ("n", -1), ("n", 1.5), ("n", True),
                                              ("n", np.inf), ("fs", 0), ("fs", -1),
                                              ("fs", np.nan), ("fs", np.inf), ("fs", True),
                                              ("fs", "1000"), ("fs", 10**400), ("linewidth_hz", -1),
                                              ("linewidth_hz", np.nan), ("linewidth_hz", np.inf),
                                              ("linewidth_hz", True), ("linewidth_hz", ".1")])
def test_invalid_scalar_parameters_fail(parameter, value):
    arguments = dict(rng=np.random.default_rng(1), t0=[0., .01], n=3, fs=1000., linewidth_hz=.1)
    arguments[parameter] = value
    with pytest.raises(ValueError):
        wiener_phase(**arguments)


def test_invalid_rng_and_unrepresentable_times_or_phase_fail():
    with pytest.raises(ValueError, match="Generator"):
        wiener_phase(np.random.RandomState(1), [0.], 2, 1000., 1.)
    with pytest.raises(ValueError, match="numeric range"):
        wiener_phase(np.random.default_rng(1), [1e308], 3, 1e-308, 1.)
    with pytest.raises(ValueError, match="numeric range"):
        wiener_phase(np.random.default_rng(1), [0., 1e308], 1, 1., 1e308)


@pytest.mark.parametrize("iq,phase", [(np.ones((2, 3)), np.zeros((2, 3))),
                                      (np.ones((2, 3), complex), np.zeros((1, 3))),
                                      (np.ones(3, complex), np.zeros((1, 3))),
                                      (np.ones((2, 3), complex), np.zeros(3)),
                                      (np.ones((2, 3), complex), np.zeros((2, 3), complex)),
                                      (np.ones((2, 3), complex), np.full((2, 3), np.nan)),
                                      (np.full((2, 3), np.inf + 0j), np.zeros((2, 3))),
                                      (np.ones((2, 0), complex), np.zeros((2, 0))),
                                      ([["1j"]], [[0.]]), (np.ones((1, 1), complex), [[True]])])
def test_invalid_iq_or_phase_fails(iq, phase):
    with pytest.raises(ValueError):
        rotate_phase(iq, phase)


def test_rotation_rejects_nonfinite_result_from_finite_extreme_iq():
    maximum = np.finfo(np.float64).max
    with pytest.raises(ValueError, match="numeric range"):
        rotate_phase(np.array([[complex(maximum, maximum)]]), [[np.pi / 4]])

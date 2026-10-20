"""Physical polarization limiting cases and independently measured calibration."""
import json

import numpy as np
import pytest

from geosim.polarization import ReceiverCalibration, apply_jones, fit_receiver_calibration, jones_matrix


def _complex(rng, shape):
    return (rng.normal(size=shape) + 1j * rng.normal(size=shape)) / np.sqrt(2)


@pytest.mark.parametrize("xpd", [0., 3., 10., 30., 100., np.inf])
def test_jones_mixing_conserves_total_power_in_every_sample(xpd):
    rng = np.random.default_rng(10)
    iq = _complex(rng, (2, 3, 20))
    jones = jones_matrix(xpd, phase_rad=0.71)
    mixed = apply_jones(jones, iq)
    np.testing.assert_allclose(np.sum(abs(mixed)**2, axis=0), np.sum(abs(iq)**2, axis=0), rtol=1e-14)
    np.testing.assert_allclose(jones.conj().T @ jones, np.eye(2), atol=1e-15)


@pytest.mark.parametrize("xpd", [0., 10., 30., 60.])
def test_isolated_carrier_recovers_declared_xpd_for_both_polarizations(xpd):
    for source in (0, 1):
        iq = np.zeros((2, 16), complex)
        iq[source] = np.exp(1j * np.arange(16))
        output = apply_jones(jones_matrix(xpd, phase_rad=0.31), iq)
        ratio = np.mean(abs(output[source])**2) / np.mean(abs(output[1 - source])**2)
        assert 10 * np.log10(ratio) == pytest.approx(xpd, abs=1e-12)


def test_ideal_xpd_is_identity_and_phase_changes_relative_leakage():
    np.testing.assert_array_equal(jones_matrix(np.inf), np.eye(2))
    zero, phased = jones_matrix(10), jones_matrix(10, np.pi / 2)
    assert phased[0, 1] == pytest.approx(1j * zero[0, 1])
    assert phased[1, 0] == pytest.approx(-1j * zero[1, 0])
    np.testing.assert_allclose(abs(phased), abs(zero), atol=1e-15)


def test_complex_least_squares_fit_corrects_instrument_only():
    rng = np.random.default_rng(11)
    pilots = _complex(rng, (2, 200))
    receiver = np.diag([1.4 * np.exp(0.3j), 0.7 * np.exp(-0.4j)]) @ jones_matrix(17, 0.6)
    calibration = fit_receiver_calibration(pilots, apply_jones(receiver, pilots), provenance="independent-pilots")
    np.testing.assert_allclose(calibration.response, receiver, atol=1e-15)
    assert calibration.n_pilots == 200 and calibration.residual_rms < 1e-14
    physical = apply_jones(jones_matrix(8, 0.2), _complex(rng, (2, 3, 20)))
    measured = apply_jones(receiver, physical)
    np.testing.assert_allclose(calibration.correct(measured), physical, atol=2e-15)
    assert not np.allclose(physical[0], physical[1])
    with pytest.raises(ValueError):
        calibration.response[0, 0] = 0


def test_noisy_reference_fit_uses_all_pilots_and_retains_measurement_noise():
    rng = np.random.default_rng(12)
    pilots = _complex(rng, (2, 10000))
    response = np.array([[1.2 + .2j, .03 - .04j], [-.02 + .01j, .8 - .3j]])
    noise = .03 * _complex(rng, pilots.shape)
    calibration = fit_receiver_calibration(pilots, apply_jones(response, pilots) + noise)
    np.testing.assert_allclose(calibration.response, response, atol=.001)
    assert .02 < calibration.residual_rms < .04
    independent = _complex(rng, (2, 30))
    added = .03 * _complex(rng, independent.shape)
    corrected = calibration.correct(apply_jones(response, independent) + added)
    assert np.mean(abs(corrected - independent)**2) > 1e-5


def test_calibration_roundtrip_and_content_tamper(tmp_path):
    response = np.array([[1.2, .1j], [-.05j, .8 * np.exp(.2j)]])
    calibration = fit_receiver_calibration(np.eye(2), response, provenance="separate-fixture")
    path = tmp_path / "receiver.npz"
    calibration.save(path)
    loaded = ReceiverCalibration.load(path)
    assert loaded.to_dict() == calibration.to_dict()
    np.testing.assert_array_equal(loaded.response, calibration.response)
    json.dumps(loaded.to_dict(), allow_nan=False)
    with np.load(path, allow_pickle=False) as data:
        original_response, metadata = data["response"], data["metadata"]
    original_response[0, 0] += .01
    np.savez(path, response=original_response, metadata=metadata)
    with pytest.raises(ValueError, match="checksum"):
        ReceiverCalibration.load(path)


def test_calibration_rejects_metadata_tamper_and_invalid_container(tmp_path):
    path = tmp_path / "receiver.npz"
    calibration = ReceiverCalibration(np.eye(2), provenance="original")
    calibration.save(path)
    with np.load(path, allow_pickle=False) as data:
        response, metadata = data["response"], json.loads(data["metadata"].item())
    metadata["provenance"] = "modified"
    np.savez(path, response=response, metadata=np.array(json.dumps(metadata)))
    with pytest.raises(ValueError, match="checksum"):
        ReceiverCalibration.load(path)
    path.write_bytes(b"not a calibration")
    with pytest.raises(ValueError, match="invalid receiver calibration"):
        ReceiverCalibration.load(path)


@pytest.mark.parametrize("reference, measured", [(np.ones((2, 4)), np.ones((2, 4))),
                                               (np.eye(2), np.ones((2, 2))),
                                               (np.eye(2), np.diag([1., 1e-8])),
                                               (np.diag([1., 1e-8]), np.eye(2)),
                                               (np.ones((2, 1)), np.ones((2, 1))),
                                               (np.eye(2), np.ones((2, 3)))])
def test_rank_shape_and_conditioning_failures_are_explicit(reference, measured):
    with pytest.raises(ValueError):
        fit_receiver_calibration(reference, measured)


@pytest.mark.parametrize("xpd, phase", [(-1, 0), (-np.inf, 0), (np.nan, 0), (True, 0),
                                       (10, np.inf), (10, np.nan), ("30", 0)])
def test_invalid_jones_parameters_fail(xpd, phase):
    with pytest.raises(ValueError):
        jones_matrix(xpd, phase)


@pytest.mark.parametrize("matrix, iq", [(np.eye(3), np.ones((2, 3))),
                                      (np.eye(2), np.ones((3, 4))),
                                      (np.eye(2), np.ones((2, 0))),
                                      (np.eye(2), [[1., np.inf], [2., 3.]]),
                                      ([[1, np.nan], [0, 1]], np.ones((2, 4)))])
def test_invalid_responses_and_iq_fail(matrix, iq):
    with pytest.raises(ValueError):
        apply_jones(matrix, iq)


@pytest.mark.parametrize("maximum", [0., .5, np.inf, np.nan, True])
def test_invalid_condition_budget_fails(maximum):
    with pytest.raises(ValueError):
        fit_receiver_calibration(np.eye(2), np.eye(2), max_condition=maximum)

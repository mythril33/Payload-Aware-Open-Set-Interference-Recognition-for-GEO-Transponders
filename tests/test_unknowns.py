"""Physical timing/power, actual payload execution and unknown artifact integrity."""
import json
from types import SimpleNamespace

import numpy as np
import pytest

from geosim import FS_SIM
from geosim import unknowns as unknown


@pytest.mark.parametrize("family", ("pulsed", "intermittent_bursts"))
def test_temporal_events_have_visible_gaps_and_preserve_active_power(family):
    generate, info = unknown.unknown_interferer(family, 36e6, 900000)
    waveform = generate(np.random.default_rng(12), np.arange(128) * 0.01, 64, FS_SIM)
    active = np.abs(waveform) > 0
    assert active.any() and (~active.any(axis=1)).any()
    assert np.mean(np.abs(waveform[active]) ** 2) == pytest.approx(info["active_power"], rel=1e-6)
    duty = info["observed_sample_duty_fraction"]
    assert np.mean(np.abs(waveform) ** 2) == pytest.approx(info["active_power"] * duty, rel=1e-6)
    assert info["observed_average_c_over_i_db"] == pytest.approx(info["active_c_over_i_db"] - 10 * np.log10(duty))
    if family == "pulsed":
        assert 0.006 <= info["on_duration_s"] < 0.020
        assert info["period_s"] >= 0.040
    else:
        assert all(hi - lo >= 0.08 - 1e-12 for lo, hi in info["intervals_s"])
        assert all(right[0] - left[1] >= 0.12 for left, right in zip(info["intervals_s"], info["intervals_s"][1:]))


def test_bandlimited_noise_has_requested_expected_power_and_no_out_of_band_source_energy():
    generate, info = unknown.unknown_interferer("wideband_noise", 36e6, 900000)
    waveform = generate(np.random.default_rng(5), np.arange(64) * 0.01, 8192, FS_SIM)
    spectrum = np.fft.fft(waveform, axis=-1)
    outside = np.abs(np.fft.fftfreq(waveform.shape[1], 1 / FS_SIM)) >= info["bandwidth_hz"] / 2
    assert np.sum(np.abs(spectrum[:, outside]) ** 2) / np.sum(np.abs(spectrum) ** 2) < 1e-12
    assert np.mean(np.abs(waveform) ** 2) == pytest.approx(info["active_power"], rel=0.03)
    assert info["observed_snapshot_occupancy"] == 1
    assert "indistinguishable" in info["identifiability"]


@pytest.mark.parametrize("family", unknown.UNKNOWN_LABELS)
def test_unknown_runs_through_actual_transponder_and_monitor(family):
    result = unknown.sample_unknown(family, 36e6, 900000, keep_iq=True, n_snap=16)
    assert result.spec_db.shape == (16, 512) and result.iq.shape == (16, 4096)
    assert np.isfinite(result.spec_db).all()
    assert result.meta["test_only"] is True and result.meta["protocol"] == unknown.PROTOCOL
    assert result.meta["interferer"]["injection_point"] == "uplink"


def test_real_generation_is_deterministic_and_families_share_link_and_plan():
    a = unknown.sample_unknown("pulsed", 36e6, 900001, n_snap=16)
    b = unknown.sample_unknown("pulsed", 36e6, 900001, n_snap=16)
    c = unknown.sample_unknown("intermittent_bursts", 36e6, 900001, n_snap=16)
    np.testing.assert_array_equal(a.spec_db, b.spec_db)
    assert a.meta == b.meta
    assert a.meta["config"] == c.meta["config"]
    assert a.meta["plan"] == c.meta["plan"]


@pytest.fixture
def generated(tmp_path, monkeypatch):
    def fake_sample(family, bandwidth, seed):
        return SimpleNamespace(spec_db=np.full((128, 512), -80, np.float32),
                               mask_db=np.zeros(512, np.float32),
                               meta={"label": family, "config": {"seed": seed, "bandwidth": bandwidth},
                                     "protocol": unknown.PROTOCOL, "test_only": True,
                                     "interferer": {"injection_point": "uplink"}})
    monkeypatch.setattr(unknown, "sample_unknown", fake_sample)
    unknown.generate_unknowns(tmp_path, n_seeds=2)
    return tmp_path


def test_artifact_roundtrip_and_completed_resume_preserve_provenance(generated, monkeypatch):
    data = unknown.load_unknowns(generated)
    assert data["spec"].shape == (6, 128, 512) and data["spec"].dtype == np.float16
    assert data["family"].tolist() == list(unknown.UNKNOWN_LABELS) * 2
    assert data["seed"].tolist() == [900000] * 3 + [900001] * 3
    manifest_path = generated / "manifest.json"
    before, identity = manifest_path.read_bytes(), unknown.unknown_fingerprint(generated)
    monkeypatch.setattr(unknown, "_commit", lambda: "a-new-documentation-commit")
    unknown.generate_unknowns(generated, n_seeds=2)
    assert manifest_path.read_bytes() == before
    assert unknown.unknown_fingerprint(generated) == identity


@pytest.mark.parametrize("change", [{"n_seeds": 3}, {"first_seed": 900001}, {"bandwidth": 72e6},
                                    {"families": ("pulsed",)}])
def test_resume_rejects_changed_requests_without_overwriting(generated, change):
    before = (generated / "manifest.json").read_bytes()
    with pytest.raises(ValueError, match="request changed"):
        unknown.generate_unknowns(generated, **{"n_seeds": 2, **change})
    assert (generated / "manifest.json").read_bytes() == before


@pytest.mark.parametrize("filename", ["part-00000.npz", "meta-00000.jsonl"])
def test_modified_artifacts_cannot_be_loaded_or_resumed(generated, filename):
    with (generated / filename).open("ab") as stream:
        stream.write(b"corruption")
    for action in (lambda: unknown.load_unknowns(generated), lambda: unknown.read_unknown_manifest(generated),
                   lambda: unknown.unknown_fingerprint(generated), lambda: unknown.generate_unknowns(generated, n_seeds=2)):
        with pytest.raises(ValueError, match="modified unknown"):
            action()


def test_missing_extra_and_misdeclared_counts_fail(generated):
    extra = generated / "part-00001.npz"
    extra.write_bytes(b"extra")
    with pytest.raises(ValueError, match="unexpected or missing"):
        unknown.load_unknowns(generated)
    extra.unlink()
    manifest_path = generated / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["n_samples"] += 1
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="sample counts"):
        unknown.load_unknowns(generated)


def test_interrupted_generation_reuses_verified_shards(generated):
    (generated / "manifest.json").unlink()
    before = (generated / "part-00000.npz").stat().st_mtime_ns
    unknown.generate_unknowns(generated, n_seeds=2)
    assert (generated / "part-00000.npz").stat().st_mtime_ns == before
    assert unknown.read_unknown_manifest(generated)["n_samples"] == 6


@pytest.mark.parametrize("change", [{"n_seeds": 0}, {"first_seed": -1}, {"bandwidth": 1e6},
                                    {"families": ()}, {"families": ("pulsed", "pulsed")}])
def test_invalid_generation_request_writes_nothing(tmp_path, change):
    with pytest.raises(ValueError):
        unknown.generate_unknowns(tmp_path, **change)
    assert not list(tmp_path.iterdir())


def test_temporal_sampling_must_resolve_both_states():
    with pytest.raises(ValueError, match="at least 16"):
        unknown.sample_unknown("pulsed", 36e6, 900000, n_snap=2)


def test_temporal_defaults_keep_both_states_over_many_parameter_seeds():
    from geosim.sensor import WARMUP_SIM
    for family in ("pulsed", "intermittent_bursts"):
        for seed in range(101):
            generate, info = unknown.unknown_interferer(family, 36e6, seed)
            generate(np.random.default_rng(seed), np.arange(128) * 0.01 + WARMUP_SIM / FS_SIM, 64, FS_SIM)
            assert 0 < info["observed_snapshot_occupancy"] < 1


def test_observation_metadata_excludes_simulator_warmup():
    from geosim.sensor import N_SIM, WARMUP_SIM
    generate, info = unknown.unknown_interferer("pulsed", 36e6, 900004)
    waveform = generate(np.random.default_rng(1), np.arange(128) * 0.01, N_SIM, FS_SIM)
    observed = waveform[:, WARMUP_SIM:]
    assert info["discarded_source_warmup_samples"] == WARMUP_SIM
    assert info["observed_sample_duty_fraction"] == pytest.approx(np.mean(np.abs(observed) > 0))
    assert info["observed_mean_source_power"] == pytest.approx(np.mean(np.abs(observed) ** 2), rel=1e-6)


@pytest.mark.parametrize("seed,n_snap", [(273, 128), (704, 128), (6, 16)])
def test_pulse_alias_seeds_are_retried_deterministically_on_actual_retained_windows(seed, n_snap):
    from geosim.sensor import N_SIM, WARMUP_SIM
    generate, info = unknown.unknown_interferer("pulsed", 36e6, seed, n_snap=n_snap)
    repeated, repeated_info = unknown.unknown_interferer("pulsed", 36e6, seed, n_snap=n_snap)
    waveform = generate(np.random.default_rng(seed), np.arange(n_snap) * 0.01, N_SIM, FS_SIM)
    again = repeated(np.random.default_rng(seed), np.arange(n_snap) * 0.01, N_SIM, FS_SIM)
    np.testing.assert_array_equal(waveform, again)
    assert info == repeated_info
    observed = np.abs(waveform[:, WARMUP_SIM:]) > 0
    assert observed.all(axis=1).any() and (~observed.any(axis=1)).any()
    assert 1 <= info["visibility_rejected_draws"] <= unknown.MAX_VISIBILITY_DRAWS
    assert info["active_power"] == pytest.approx(10 ** (-info["active_c_over_i_db"] / 10))


def test_bounded_pulse_fallback_resolves_repeated_aliased_draws(monkeypatch):
    class AliasedParameters:
        def uniform(self, lo, hi):
            if (lo, hi) == (0.04, 0.09):
                return 0.05
            if (lo, hi) == (0.006, 0.018):
                return 0.006
            if (lo, hi) == (0, 0.05):
                return 0.008
            return (lo + hi) / 2

    real_rng = np.random.default_rng(3)
    monkeypatch.setattr(unknown.np.random, "default_rng", lambda _: AliasedParameters())
    generate, info = unknown.unknown_interferer("pulsed", 36e6, 0)
    waveform = generate(real_rng, np.arange(128) * 0.01, 64, FS_SIM)
    assert info["visibility_fallback"] is True
    assert info["visibility_rejected_draws"] == unknown.MAX_VISIBILITY_DRAWS
    assert (np.abs(waveform) > 0).any() and (~(np.abs(waveform) > 0).any(axis=1)).any()

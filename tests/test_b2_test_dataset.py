"""B2-test/1: test-only families bound to a known artifact, role discipline and corruption checks."""
from dataclasses import asdict
import json
from types import SimpleNamespace as NS

import numpy as np
import pytest

from geosim import b2_dataset as known_ds
from geosim import b2_scenarios as scenes
from geosim import b2_test_dataset as ds
from geosim.b2_protocol import B2Config, ROLE_STARTS
from geosim.b2_scenarios import TEST_FAMILIES, prepare_scene, prepare_test_scene
from geosim.cancellation import CancellationConfig
from geosim.plan import plan_mask_db


def test_test_scenes_share_group_draws_and_are_restricted_to_the_test_role():
    group = ROLE_STARTS["test"] + 3
    clean = prepare_scene("clean", group)
    for family in TEST_FAMILIES:
        scene = prepare_test_scene(family, group)
        assert scene.plans == clean.plans and scene.active_carriers == clean.active_carriers
        assert scene.cfg.co.ibo_db == clean.cfg.co.ibo_db and scene.cfg.uplink_xpd_db == clean.cfg.uplink_xpd_db
        assert scene.metadata["protocol"] == "B2-test/1" and scene.metadata["test_only"] is True
        assert scene.metadata["label"] == family and scene.metadata["role"] == "test"
        downlink = family == "adjacent_satellite_downlink"
        assert (scene.interferers[0] is None) == downlink and (scene.downlink_interferers[0] is not None) == downlink
        assert scene.metadata["expected_decision"] == ("clean" if family == "cid_overlay" else "unknown")
    assert prepare_test_scene("pulsed", group).event != prepare_test_scene("intermittent_bursts", group).event
    # K17d: the downlink ASI is pair-matched to the known uplink ASI of the same group.
    known_asi = prepare_scene("adjacent_satellite", group).event
    downlink = prepare_test_scene("adjacent_satellite_downlink", group).event
    assert downlink["carrier"] == known_asi["carrier"] and downlink["geometry"] == known_asi["geometry"]
    assert downlink["c_over_i_psd_db"] == known_asi["c_over_i_psd_db"] and downlink["paired_with_known"] == "adjacent_satellite"
    for role in ("train", "val-select", "val-calib", "test-matched"):
        with pytest.raises(ValueError, match="test-role"):
            prepare_test_scene("pulsed", ROLE_STARTS[role])
    with pytest.raises(ValueError):
        prepare_test_scene("cw", group)
    # Known scenes are unchanged by the shared-scene refactor (downlink field defaults to none).
    assert clean.downlink_interferers == (None, None) and clean.metadata["protocol"] == "B2-base/1"


def _fake_meta(cfg, plans, interferers, active_carriers, calibration, downlink):
    power = [sum(c.power for c, keep in zip(plan, active) if keep) for plan, active in zip(plans, active_carriers)]
    return {"config": cfg.to_dict(), "plans": [[asdict(c) for c in plan] for plan in plans],
            "has_interferer": [event is not None for event in interferers],
            "has_downlink_interferer": [event is not None for event in downlink],
            "downlink_interference_reference_power": [0.1, 0.1],
            "active_carriers": [list(active) for active in active_carriers],
            "active_planned_power": power, "nominal_planned_power": [1., 1.],
            "gain_mode": "fixed_nominal_planned_power",
            "paths": [{"actual_ibo_db": cfg.co.ibo_db, "obo_db": 10., "omux_output_power": 0.1,
                       "receiver_noise_psd": 1e-10, "zero_drive": False} for _ in range(2)],
            "receiver_calibration_applied": True, "receiver_calibration": calibration.to_dict()}


@pytest.fixture
def fakes(monkeypatch):
    calls = {"cancel": []}

    def simulate(cfg, *, plans, interferers, active_carriers, calibration, keep_iq, downlink_interferers=(None, None)):
        # Evaluate the event callbacks on a short window so they populate their observed metadata.
        t0 = np.arange(cfg.co.n_snap) * cfg.co.snap_interval
        for event in (*interferers, *downlink_interferers):
            if event is not None:
                event(np.random.default_rng(0), t0, 512, 288e6)
        iq = None
        if keep_iq:
            rng = np.random.default_rng([int(cfg.co.seed), 7])
            iq = (rng.standard_normal((2, 128, 4096)) + 1j * rng.standard_normal((2, 128, 4096))).astype(np.complex64)
        return NS(spec_db=np.full((2, 128, 512), -80, np.float32),
                  mask_db=np.stack([plan_mask_db(plan) for plan in plans]),
                  meta=_fake_meta(cfg, plans, interferers, active_carriers, calibration, downlink_interferers), iq=iq)

    def cancel(iq, plan, config=None):
        calls["cancel"].append(list(plan))
        return NS(residual_iq=iq, residual_db=np.full((128, 512), -95, np.float32),
                  carriers=[{"plan_index": i, "f0": c.f0, "symbol_rate": c.symbol_rate, "mod": c.mod,
                             "samples_per_symbol": 60, "symbols_per_snapshot": 200, "timing_samples": [0] * 128,
                             "gain_power_db_mean": 0.0, "decision_snr_db_median": 20.0,
                             "basis": "observed IQ and operator plan only"} for i, c in enumerate(plan)], config=config)

    monkeypatch.setattr(scenes, "simulate_dual", simulate)
    monkeypatch.setattr(known_ds, "cancel_planned_carriers", cancel)
    monkeypatch.setattr(known_ds, "_generator_provenance", lambda: {"unit_fixture": "0" * 64})
    monkeypatch.setattr(ds, "_generator_provenance", lambda: {"unit_fixture": "0" * 64})
    return calls


@pytest.fixture
def known(tmp_path, fakes):
    root = tmp_path / "known"
    known_ds.generate_b2_dataset(root, roles=("train", "test"), limit_groups=2, groups_per_shard=1,
                                 cancellation=CancellationConfig())
    return root


def test_generation_binds_to_known_artifact_and_stores_only_test_families(tmp_path, fakes, known):
    root = tmp_path / "test-only"
    ds.generate_b2_test_dataset(root, known, limit_groups=2, groups_per_shard=1, cancellation=CancellationConfig())
    manifest = ds.read_b2_test_manifest(root)
    assert manifest["protocol"] == "B2-test/1" and manifest["benchmark_complete"] is False
    assert manifest["families"] == list(TEST_FAMILIES) and manifest["n_samples"] == 10
    assert manifest["request"]["known"]["known_protocol"] == "B2-feat/1"
    assert manifest["calibration"] == known_ds.read_b2_manifest(known)["calibration"]     # same receiver calibration
    data = ds.load_b2_test_split(root)
    assert data["spec"].shape == (10, 2, 128, 512) and data["residual"].shape == (10, 128, 512)
    assert sorted(data["family"].tolist()) == sorted(list(range(5)) * 2)
    assert set(data["seed"].tolist()) == {ROLE_STARTS["test"], ROLE_STARTS["test"] + 1}
    assert all(record["test_only"] and record["role"] == "test" for record in data["meta"])
    assert {record["expected_decision"] for record in data["meta"]} == {"unknown", "clean"}
    assert not (root / "train").exists()
    before = ds.b2_test_fingerprint(root)
    ds.generate_b2_test_dataset(root, known, limit_groups=2, groups_per_shard=1, cancellation=CancellationConfig())
    assert ds.b2_test_fingerprint(root) == before
    with pytest.raises(ValueError, match="request changed"):
        ds.generate_b2_test_dataset(root, known, limit_groups=1, groups_per_shard=1, cancellation=CancellationConfig())


def test_binding_mismatches_are_rejected(tmp_path, fakes, known):
    with pytest.raises(ValueError, match="cancellation setting"):
        ds.generate_b2_test_dataset(tmp_path / "a", known, limit_groups=1, groups_per_shard=1)
    with pytest.raises(ValueError, match="physical configuration"):
        ds.generate_b2_test_dataset(tmp_path / "b", known, B2Config(calibration_seed=5), limit_groups=1,
                                    groups_per_shard=1, cancellation=CancellationConfig())
    with pytest.raises(ValueError, match="not all present"):
        ds.generate_b2_test_dataset(tmp_path / "c", known, limit_groups=3, groups_per_shard=1,
                                    cancellation=CancellationConfig())
    base = tmp_path / "base-known"
    known_ds.generate_b2_dataset(base, roles=("train",), limit_groups=1, groups_per_shard=1)
    with pytest.raises(ValueError, match="test role"):
        ds.generate_b2_test_dataset(tmp_path / "d", base, limit_groups=1, groups_per_shard=1)


def test_corruption_and_foreign_roles_are_detected(tmp_path, fakes, known):
    root = tmp_path / "test-only"
    ds.generate_b2_test_dataset(root, known, limit_groups=1, groups_per_shard=1, cancellation=CancellationConfig())
    (root / "train").mkdir()
    with pytest.raises(ValueError, match="never occupy"):
        ds.read_b2_test_manifest(root)
    (root / "train").rmdir()
    meta = root / "test" / "meta-00000.jsonl"
    records = [json.loads(line) for line in meta.read_text().splitlines()]
    records[0]["expected_decision"] = "clean"
    meta.write_text("".join(json.dumps(r) + "\n" for r in records))
    descriptor = root / "test" / "shard-00000.json"
    info = json.loads(descriptor.read_text())
    info["sha256"][meta.name] = ds._file_hash(meta)
    descriptor.write_text(json.dumps(info))
    manifest = json.loads((root / "manifest.json").read_text())
    manifest["shards"][0] = info
    (root / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="family, group or calibration"):
        ds.read_b2_test_manifest(root)


def test_cli_passes_binding_and_settings(tmp_path, monkeypatch):
    path = tmp_path / "cancel.json"
    path.write_text(json.dumps({"iterations": 2}))
    calls = []
    monkeypatch.setattr(ds, "generate_b2_test_dataset", lambda out, known, cfg, **kwargs: calls.append((out, known, cfg, kwargs)))
    ds.main(["--out", str(tmp_path / "out"), "--known", str(tmp_path / "known"), "--cancellation", str(path),
             "--limit-groups", "2", "--groups-per-shard", "1"])
    assert calls[0][1] == str(tmp_path / "known")
    assert calls[0][3] == {"limit_groups": 2, "groups_per_shard": 1, "cancellation": CancellationConfig(iterations=2)}


def test_real_chain_downlink_family_raises_only_its_band_and_keeps_known_streams():
    """One real test group (~10 s): the downlink ASI appears in its band on the co feed; the
    clean twin's carriers, noise and phase streams are untouched elsewhere."""
    from geosim.b2_scenarios import sample_scene, sample_test_scene
    from geosim.cancellation import band_power_db
    group = ROLE_STARTS["test"]
    clean = sample_scene("clean", group)
    down = sample_test_scene("adjacent_satellite_downlink", group)
    event = down.meta["event"]
    assert down.meta["has_downlink_interferer"] == [True, False] and down.meta["has_interferer"] == [False, False]
    assert np.array_equal(down.mask_db, clean.mask_db)
    lo, hi = event["f_lo"], event["f_hi"]
    inside = band_power_db(down.spec_db[0], lo, hi) - band_power_db(clean.spec_db[0], lo, hi)
    assert inside > 0.0
    # Far from the event band the co spectrum is numerically the clean twin's (same streams).
    from geosim.plan import monitor_freqs
    f = monitor_freqs()
    far = (f < lo - 4e6) | (f > hi + 4e6)
    assert far.any()
    difference = np.abs(down.spec_db[0][:, far] - clean.spec_db[0][:, far])
    assert np.median(difference) < 0.02 and difference.max() < 0.2        # Welch sidelobe leakage only
    assert event["effective_c_over_i_psd_db"] == pytest.approx(
        event["c_over_i_psd_db"] - 10 * np.log10(down.meta["active_planned_power"][0]))

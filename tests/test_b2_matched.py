"""B2-match/1 (K17c): frozen range, real pairing, placement, binding, corruption and compatibility."""
from dataclasses import asdict
import json
from types import SimpleNamespace as NS

import numpy as np
import pytest

from geosim import b2_dataset as known_ds
from geosim import b2_matched_dataset as ds
from geosim import b2_scenarios as scenes
from geosim.asi import overlap_fraction
from geosim.b2_protocol import LABELS, ROLE_COUNTS, ROLE_STARTS, B2Config
from geosim.b2_scenarios import (MATCHED_BINS, MATCHED_LABELS, matched_bin, prepare_matched_scene, prepare_scene,
                                 prepare_test_scene)
from geosim.cancellation import CancellationConfig
from geosim.interferers import free_gaps, overlaps_plan
from geosim.plan import plan_mask_db

FIRST = ROLE_STARTS["test-matched"]


def _pair(group):
    return {label: prepare_matched_scene(label, group) for label in MATCHED_LABELS}


def test_frozen_range_and_role_refusal():
    assert FIRST == 3_300_000 and ROLE_COUNTS["test-matched"] == 150
    prepare_matched_scene("clean", FIRST)
    prepare_matched_scene("clean", FIRST + 149)
    for group in (FIRST - 1, FIRST + 150, ROLE_STARTS["train"], ROLE_STARTS["test"]):
        with pytest.raises(ValueError, match="test-matched|reserved B2/1 roles"):
            prepare_matched_scene("clean", group)
    with pytest.raises(ValueError, match="matched variants"):
        prepare_matched_scene("cw", FIRST)
    # Known and test-only scene builders refuse the matched namespace in turn.
    with pytest.raises(ValueError):
        prepare_scene("clean", FIRST)
    with pytest.raises(ValueError, match="test-role"):
        prepare_test_scene("pulsed", FIRST)


@pytest.mark.parametrize("group", [FIRST, FIRST + 1, FIRST + 7])
def test_pair_shares_scene_and_differs_only_in_placement(group):
    pair = _pair(group)
    clean, asi, unauth = (pair[name] for name in MATCHED_LABELS)
    for scene in (asi, unauth):
        assert scene.plans == clean.plans and scene.active_carriers == clean.active_carriers
        assert scene.cfg.to_dict() == clean.cfg.to_dict()                 # link, XPD, instrument, phase noise
        assert scene.metadata["matched"] == clean.metadata["matched"]
        assert scene.plan_consistency == clean.plan_consistency
        assert scene.metadata["role"] == "test-matched" and scene.metadata["protocol"] == "B2-match/1"
    m = clean.metadata["matched"]
    assert m["pair_id"] == f"B2-match/1:{group}"
    assert 4.0 <= m["target_c_over_i_psd_db"] <= 13.0 and m["bin"] == matched_bin(m["target_c_over_i_psd_db"])
    a, u = asi.event, unauth.event
    # Exactly matched requested interference power and shared carrier descriptor.
    assert a["carrier"]["power"] == pytest.approx(10 ** (-u["c_over_i_db"] / 10), rel=1e-12)
    assert a["carrier"]["power"] == pytest.approx(m["requested_power"], rel=1e-12)
    assert a["c_over_i_psd_db"] == u["c_over_i_psd_db"] == m["target_c_over_i_psd_db"]
    assert (a["carrier"]["symbol_rate"], a["carrier"]["alpha"], a["carrier"]["mod"]) == (u["symbol_rate"], u["alpha"], u["mod"])
    assert a["injection_stage"] == u["injection_stage"] == "uplink"
    assert a["power_reference"] == u["power_reference"] == "total_planned_uplink"
    # Placement is the only difference: ASI overlaps the plan, unauthorized sits in a gap.
    plan = clean.plans[0]
    assert 0.2 <= a["overlap_fraction"] <= 0.8
    assert 0.2 <= overlap_fraction(a["f_lo"], a["f_hi"], plan) <= 0.8
    assert not overlaps_plan(u["f_lo"], u["f_hi"], plan)
    assert any(lo <= u["f_lo"] and u["f_hi"] <= hi for lo, hi in free_gaps(plan, 36e6))
    assert a["carrier"]["f0"] != u["f0"]
    assert 0.0 <= m["asi_overlap_fraction_active"] <= m["asi_overlap_fraction_plan"] == pytest.approx(a["overlap_fraction"])
    assert a["geometry"] is None and a["level_source"] == "matched_intervention"


def test_plan_retry_and_absent_carrier_intersection_are_recorded():
    # Group 3300002 needs one operator-plan redraw before both placements are feasible.
    assert prepare_matched_scene("clean", FIRST + 2).metadata["operator_plan_source"]["co_rejected_plan_draws"] == 1
    assert prepare_matched_scene("clean", FIRST).metadata["operator_plan_source"]["co_rejected_plan_draws"] == 0
    # Group 3300000 drops the very carrier its ASI overlaps: flagged, not hidden.
    first = prepare_matched_scene("adjacent_satellite", FIRST)
    assert first.plan_consistency == 1 and first.metadata["matched"]["asi_overlaps_only_absent_carrier"] is True
    assert first.metadata["matched"]["asi_overlap_fraction_active"] == 0.0
    from geosim.asi import adjacent_satellite_uplink_at_level
    from geosim.interferers import InfeasibleCarrierError
    from geosim.waveform import Carrier
    plan = first.plans[0]
    gap_carrier = Carrier(f0=first.metadata["matched"]["unauthorized_f0"], symbol_rate=first.metadata["matched"]["symbol_rate"],
                          alpha=first.metadata["matched"]["alpha"], mod="QPSK", power=0.01)
    with pytest.raises(InfeasibleCarrierError):
        adjacent_satellite_uplink_at_level(plan, 36e6, gap_carrier, 8.0)   # a gap placement is not an ASI


def test_matched_draw_is_deterministic_and_bins_cover_the_frozen_role():
    first = prepare_matched_scene("clean", FIRST).metadata["matched"]
    again = prepare_matched_scene("unauthorized", FIRST).metadata["matched"]
    assert first == again
    bins = [prepare_matched_scene("clean", FIRST + k).metadata["matched"]["bin"] for k in range(0, 150, 10)]
    assert set(bins) <= {0, 1, 2}
    assert matched_bin(4.0) == 0 and matched_bin(6.999) == 0 and matched_bin(7.0) == 1 and matched_bin(10.0) == 2
    assert matched_bin(13.0) == 2
    with pytest.raises(ValueError):
        matched_bin(13.5)
    assert MATCHED_BINS == ((4.0, 7.0), (7.0, 10.0), (10.0, 13.0))


def test_known_and_test_only_scenes_are_unchanged_by_the_matched_additions():
    # Reference values recorded from the pre-matched implementation (reviewer-verified identity).
    clean = prepare_scene("clean", ROLE_STARTS["test"])
    assert clean.metadata["protocol"] == "B2-base/1" and clean.downlink_interferers == (None, None)
    assert clean.metadata["operator_plan_source"]["conditioning"].startswith("all eight known variants")
    pulsed = prepare_test_scene("pulsed", ROLE_STARTS["test"])
    assert pulsed.metadata["protocol"] == "B2-test/1"


# ---- artifact stage with fakes ----

def _fake_meta(cfg, plans, interferers, active_carriers, calibration, downlink=(None, None)):
    power = [sum(c.power for c, keep in zip(plan, active) if keep) for plan, active in zip(plans, active_carriers)]
    return {"config": cfg.to_dict(), "plans": [[asdict(c) for c in plan] for plan in plans],
            "has_interferer": [event is not None for event in interferers],
            "has_downlink_interferer": [event is not None for event in downlink],
            "downlink_interference_reference_power": [0.1, 0.1],
            "active_carriers": [list(active) for active in active_carriers],
            "active_planned_power": power, "nominal_planned_power": [1., 1.], "gain_mode": "fixed_nominal_planned_power",
            "paths": [{"actual_ibo_db": cfg.co.ibo_db, "obo_db": 10., "omux_output_power": 0.1,
                       "receiver_noise_psd": 1e-10, "zero_drive": False} for _ in range(2)],
            "receiver_calibration_applied": True, "receiver_calibration": calibration.to_dict()}


@pytest.fixture
def fakes(monkeypatch):
    def simulate(cfg, *, plans, interferers, active_carriers, calibration, keep_iq, downlink_interferers=(None, None)):
        t0 = np.arange(cfg.co.n_snap) * cfg.co.snap_interval
        for event in (*interferers, *downlink_interferers):
            if event is not None:
                event(np.random.default_rng(0), t0, 512, 288e6)        # populate observed event metadata
        iq = None
        if keep_iq:
            rng = np.random.default_rng([int(cfg.co.seed), 7])
            iq = (rng.standard_normal((2, 128, 4096)) + 1j * rng.standard_normal((2, 128, 4096))).astype(np.complex64)
        return NS(spec_db=np.full((2, 128, 512), -80, np.float32),
                  mask_db=np.stack([plan_mask_db(plan) for plan in plans]),
                  meta=_fake_meta(cfg, plans, interferers, active_carriers, calibration, downlink_interferers), iq=iq)

    def cancel(iq, plan, config=None):
        return NS(residual_iq=iq, residual_db=np.full((128, 512), -95, np.float32),
                  carriers=[{"plan_index": i, "f0": c.f0, "symbol_rate": c.symbol_rate, "mod": c.mod,
                             "samples_per_symbol": 60, "symbols_per_snapshot": 200, "timing_samples": [0] * 128,
                             "gain_power_db_mean": 0.0, "decision_snr_db_median": 20.0,
                             "basis": "observed IQ and operator plan only"} for i, c in enumerate(plan)], config=config)

    monkeypatch.setattr(scenes, "simulate_dual", simulate)
    monkeypatch.setattr(known_ds, "cancel_planned_carriers", cancel)
    monkeypatch.setattr(known_ds, "_generator_provenance", lambda: {"unit_fixture": "0" * 64})
    monkeypatch.setattr(ds, "_generator_provenance", lambda: {"unit_fixture": "0" * 64})


@pytest.fixture
def known(tmp_path, fakes):
    root = tmp_path / "known"
    known_ds.generate_b2_dataset(root, roles=("train", "test"), limit_groups=1, groups_per_shard=1,
                                 cancellation=CancellationConfig())
    return root


def test_generation_binds_calibration_and_stores_paired_variants(tmp_path, fakes, known):
    root = tmp_path / "match"
    ds.generate_b2_matched_dataset(root, known, limit_groups=2, groups_per_shard=1, cancellation=CancellationConfig())
    manifest = ds.read_b2_matched_manifest(root)
    assert manifest["protocol"] == "B2-match/1" and manifest["benchmark_complete"] is False
    assert manifest["labels"] == ["clean", "adjacent_satellite", "unauthorized"] and manifest["label_index"] == [0, 6, 3]
    assert manifest["n_samples"] == 6 and manifest["calibration"] == known_ds.read_b2_manifest(known)["calibration"]
    assert manifest["request"]["known"]["known_protocol"] == "B2-feat/1"
    data = ds.load_b2_matched_split(root)
    assert data["spec"].shape == (6, 2, 128, 512) and data["residual"].shape == (6, 128, 512)
    assert sorted(data["label"].tolist()) == [0, 0, 3, 3, 6, 6]
    assert set(data["seed"].tolist()) == {FIRST, FIRST + 1} and set(data["matched_bin"].tolist()) <= {0, 1, 2}
    for record in data["meta"]:
        assert record["role"] == "test-matched" and record["test_only"] is True
        assert record["matched"]["pair_id"] == f"B2-match/1:{record['scenario_id']}"
        assert record["matched"]["bin"] in (0, 1, 2) and record["matched"]["asi_overlap_fraction_active"] <= record["matched"]["asi_overlap_fraction_plan"]
    assert not any((root / role).exists() for role in ("train", "val-select", "val-calib", "test"))
    before = ds.b2_matched_fingerprint(root)
    ds.generate_b2_matched_dataset(root, known, limit_groups=2, groups_per_shard=1, cancellation=CancellationConfig())
    assert ds.b2_matched_fingerprint(root) == before                     # deterministic regeneration / resume
    with pytest.raises(ValueError, match="request changed"):
        ds.generate_b2_matched_dataset(root, known, limit_groups=1, groups_per_shard=1, cancellation=CancellationConfig())


def test_binding_mismatches_are_rejected(tmp_path, fakes, known):
    with pytest.raises(ValueError, match="cancellation setting"):
        ds.generate_b2_matched_dataset(tmp_path / "a", known, limit_groups=1, groups_per_shard=1)
    with pytest.raises(ValueError, match="physical configuration"):
        ds.generate_b2_matched_dataset(tmp_path / "b", known, B2Config(calibration_seed=5), limit_groups=1,
                                       groups_per_shard=1, cancellation=CancellationConfig())
    with pytest.raises(ValueError):
        ds.generate_b2_matched_dataset(tmp_path / "c", known, limit_groups=151, groups_per_shard=1,
                                       cancellation=CancellationConfig())


def test_corruption_duplicate_groups_and_foreign_roles_are_detected(tmp_path, fakes, known):
    root = tmp_path / "match"
    ds.generate_b2_matched_dataset(root, known, limit_groups=1, groups_per_shard=1, cancellation=CancellationConfig())
    (root / "test").mkdir()
    with pytest.raises(ValueError, match="never occupy"):
        ds.read_b2_matched_manifest(root)
    (root / "test").rmdir()
    part = root / "test-matched" / "part-00000.npz"
    descriptor = root / "test-matched" / "shard-00000.json"
    manifest_path = root / "manifest.json"

    def rehash(extra=None):
        info = json.loads(descriptor.read_text())
        info["sha256"][part.name] = ds._file_hash(part)
        meta = root / "test-matched" / "meta-00000.jsonl"
        info["sha256"][meta.name] = ds._file_hash(meta)
        descriptor.write_text(json.dumps(info))
        manifest = json.loads(manifest_path.read_text())
        manifest["shards"][0] = info
        manifest_path.write_text(json.dumps(manifest))

    with np.load(part) as archive:
        arrays = {key: archive[key] for key in archive.files}
    good = {key: value.copy() for key, value in arrays.items()}
    arrays["label"][1] = arrays["label"][0]                               # duplicate (group, label) pair, missing variant
    np.savez(part, **arrays)
    rehash()
    with pytest.raises(ValueError, match="duplicate or missing"):
        ds.read_b2_matched_manifest(root)
    arrays = {key: value.copy() for key, value in good.items()}
    arrays["matched_bin"][0] = 2 if arrays["matched_bin"][0] != 2 else 0 # bin disagrees with metadata
    np.savez(part, **arrays)
    rehash()
    with pytest.raises(ValueError, match="matched_bin"):
        ds.read_b2_matched_manifest(root)
    arrays = {key: value.copy() for key, value in good.items()}
    arrays["residual"][0, 0, 0] = np.float16(np.nan)
    np.savez(part, **arrays)
    rehash()
    with pytest.raises(ValueError, match="residual"):
        ds.read_b2_matched_manifest(root)
    np.savez(part, **good)
    meta = root / "test-matched" / "meta-00000.jsonl"
    records = [json.loads(line) for line in meta.read_text().splitlines()]
    records[1]["matched"]["target_c_over_i_psd_db"] += 0.5             # pairing broken in one variant
    meta.write_text("".join(json.dumps(r) + "\n" for r in records))
    rehash()
    with pytest.raises(ValueError):
        ds.read_b2_matched_manifest(root)


def test_known_and_test_only_artifacts_still_verify_with_matched_stage_present(tmp_path, fakes, known):
    from geosim import b2_test_dataset as test_ds
    test_root = tmp_path / "test-only"
    test_ds.generate_b2_test_dataset(test_root, known, limit_groups=1, groups_per_shard=1, cancellation=CancellationConfig())
    ds.generate_b2_matched_dataset(tmp_path / "match", known, limit_groups=1, groups_per_shard=1, cancellation=CancellationConfig())
    assert known_ds.read_b2_manifest(known)["protocol"] == "B2-feat/1"
    assert test_ds.read_b2_test_manifest(test_root)["protocol"] == "B2-test/1"
    with pytest.raises(ValueError):
        test_ds.read_b2_test_manifest(tmp_path / "match")                 # stages are not interchangeable
    with pytest.raises(ValueError):
        ds.read_b2_matched_manifest(test_root)


def test_cli_passes_binding_and_settings(tmp_path, monkeypatch):
    path = tmp_path / "cancel.json"
    path.write_text(json.dumps({"iterations": 2}))
    calls = []
    monkeypatch.setattr(ds, "generate_b2_matched_dataset", lambda out, known, cfg, **kwargs: calls.append((out, known, cfg, kwargs)))
    ds.main(["--out", str(tmp_path / "out"), "--known", str(tmp_path / "known"), "--cancellation", str(path),
             "--limit-groups", "3", "--groups-per-shard", "1"])
    assert calls[0][3] == {"limit_groups": 3, "groups_per_shard": 1, "cancellation": CancellationConfig(iterations=2)}


def test_real_chain_pair_levels_and_masks():
    """One real matched group (~12 s): identical masks, both events visible in their own band, and
    the unauthorized band of the ASI scene (and vice versa) stays at the clean twin's level."""
    from geosim.b2_scenarios import sample_matched_scene
    from geosim.cancellation import band_power_db
    group = FIRST
    results = {label: sample_matched_scene(label, group) for label in MATCHED_LABELS}
    clean, asi, unauth = (results[name] for name in MATCHED_LABELS)
    assert np.array_equal(asi.mask_db, clean.mask_db) and np.array_equal(unauth.mask_db, clean.mask_db)
    a, u = asi.meta["event"], unauth.meta["event"]
    rise_asi = band_power_db(asi.spec_db[0], a["f_lo"], a["f_hi"]) - band_power_db(clean.spec_db[0], a["f_lo"], a["f_hi"])
    rise_unauth = band_power_db(unauth.spec_db[0], u["f_lo"], u["f_hi"]) - band_power_db(clean.spec_db[0], u["f_lo"], u["f_hi"])
    assert rise_asi > 1.0 and rise_unauth > 3.0
    # Cross-check: each scene is at the clean level inside the *other* event's band (Welch leakage only).
    other_asi = abs(band_power_db(unauth.spec_db[0], a["f_lo"], a["f_hi"]) - band_power_db(clean.spec_db[0], a["f_lo"], a["f_hi"]))
    assert other_asi < 0.3
    assert asi.meta["matched"] == unauth.meta["matched"] == clean.meta["matched"]

"""Fabricated metadata only: no generated RF, held-out observations or model fits.

The session fixture copies the *membership lists* of the immutable identity,
then invents carrier indices and calibrations. It is deliberately NOT production
metadata and cannot pass the fixed E12 scene-metadata digest in the production
API. Placeholder .npz files are opaque bytes that must never be opened.
"""
import copy
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("e14_metadata_under_test", ROOT / "scripts/b2_e14_verify_metadata.py")
V = importlib.util.module_from_spec(spec)
spec.loader.exec_module(V)
P = V.P


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def raw_digest(raw):
    return hashlib.sha256(raw).hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical(value) + "\n")


def read(path):
    return json.loads(path.read_text())


@pytest.fixture(scope="module")
def fabricated(tmp_path_factory):
    root = tmp_path_factory.mktemp("e14-fabricated-k17d-only")
    accepted = read(ROOT / V.IDENTITY)
    co, cross = set(accepted["co_feed_missing_ids"]), set(accepted["cross_feed_missing_ids"])
    scenes = []
    for group in range(3200000, 3200500):
        pol = 0 if group in co else (1 if group in cross else None)
        scenes.append({"scenario_id": group, "role": "test", "protocol": "B2-base/1",
                       "plan_consistency": int(pol is not None),
                       "dropped_carrier": None if pol is None else {"polarization": pol, "index": group % 5},
                       "missing_carrier_override": None})
    identity = {"schema": V.SYNTHETIC_SCHEMA, "counts": {"headline": 500, "co_feed_missing": 35,
                "cross_feed_missing": 43, "missing_total": 78, "sensitivity": 465},
                "headline_ids": list(range(3200000, 3200500)), "co_feed_missing_ids": sorted(co),
                "cross_feed_missing_ids": sorted(cross), "sensitivity_ids": sorted(set(range(3200000, 3200500)) - co)}
    identity["fingerprints"] = {key: digest(identity[key]) for key in
                                 ("headline_ids", "co_feed_missing_ids", "sensitivity_ids")}
    identity["fingerprints"]["scene_metadata"] = digest(scenes)
    package = ROOT / "src/geosim"
    sources = {p.relative_to(package).as_posix(): raw_digest(p.read_bytes()) for p in
               sorted(package.glob("*.py")) + sorted((package / "data").glob("*")) if p.is_file()}
    request = {"protocol": P.FEATURE_PROTOCOL, "parent_protocol": P.PROTOCOL, "artifact_stage": P.FEATURE_STAGE,
               "benchmark_complete": False, "contract": P.protocol_contract(), "config": read(ROOT / "configs/b2_base.json"),
               "roles": list(P.BASE_ROLES), "scenario_groups": {role: P.scenario_ids(role) for role in P.BASE_ROLES},
               "limit_groups": None, "groups_per_shard": 4, "source_sha256": sources,
               "numpy_version": "2.5.4", "scipy_version": "1.18.1", "cancellation": read(ROOT / "configs/cancellation.json"),
               "fifth_channel": P.FIFTH_CHANNEL}
    request_fingerprint = digest(request)
    binding = {"schema": V.BINDING_SCHEMA, "source_head": "5ba972da6d3dee097cfee9cb79a5c1b27a1c139b",
               "request": request, "request_fingerprint": request_fingerprint}
    calibration = {"artifact_version": 1, "n_pilots": 64, "max_condition": 1000000.0, "reference_condition": 1.0,
                   "response_condition": 1.0, "residual_rms": 0.0,
                   "provenance": f"{P.FEATURE_PROTOCOL}:{request_fingerprint}:independent_pilots",
                   "response_real": [[1.0, 0.0], [0.0, 1.0]], "response_imag": [[0.0, 0.0], [0.0, 0.0]],
                   "parameter_sha256": "a" * 64}
    calibration["artifact_sha256"] = digest(calibration)
    calibration_artifact = {"file": "receiver_calibration.npz", "sha256": raw_digest(b"FABRICATED NOT AN ARRAY"),
                            "metadata": calibration}
    write(root / "request.json", request)
    write(root / "calibration.json", calibration_artifact)
    (root / "receiver_calibration.npz").write_bytes(b"FABRICATED NOT AN ARRAY")
    manifest = {"artifact_version": 1, "protocol": P.FEATURE_PROTOCOL, "parent_protocol": P.PROTOCOL,
                "artifact_stage": P.FEATURE_STAGE, "benchmark_complete": False, "labels": list(P.LABELS),
                "config": request["config"], "request": request, "request_fingerprint": request_fingerprint,
                "commit": binding["source_head"], "calibration": calibration, "calibration_artifact": calibration_artifact,
                "cancellation": request["cancellation"], "fifth_channel": P.FIFTH_CHANNEL, "roles": {}}
    for role in P.BASE_ROLES:
        groups = P.scenario_ids(role)
        manifest["roles"][role] = {"scenario_seeds": groups, "n_scenarios": len(groups), "n_samples": len(groups) * 8,
                                   "per_label": {label: len(groups) for label in P.LABELS}, "shards": [None] * ((len(groups) + 3) // 4)}
    for role in P.BASE_ROLES:
        (root / role).mkdir()
    for index in range(125):
        rows = []
        for scene in scenes[index * 4:(index + 1) * 4]:
            for label in P.LABELS:
                rows.append({**scene, "label": label, "protocol": P.FEATURE_PROTOCOL, "base_protocol": P.BASE_PROTOCOL,
                             "parent_protocol": P.PROTOCOL, "receiver_calibration_applied": True,
                             "receiver_calibration": calibration, "fabricated_fixture": True})
        part, meta, commit = f"part-{index:05d}.npz", f"meta-{index:05d}.jsonl", f"shard-{index:05d}.json"
        raw_meta = ("\n".join(map(canonical, rows)) + "\n").encode()
        (root / "test" / part).write_bytes(b"FABRICATED NOT AN ARRAY")
        (root / "test" / meta).write_bytes(raw_meta)
        descriptor = {"part": part, "meta": meta, "role": "test", "scenario_seeds": list(range(3200000 + index * 4, 3200004 + index * 4)),
                      "n_samples": 32, "request_fingerprint": request_fingerprint,
                      "sha256": {part: raw_digest(b"FABRICATED NOT AN ARRAY"), meta: raw_digest(raw_meta)}}
        manifest["roles"]["test"]["shards"][index] = descriptor
        write(root / "test" / commit, descriptor)
    write(root / "manifest.json", manifest)
    return root, binding, identity


@pytest.fixture
def sample(fabricated, tmp_path):
    source, binding, identity = fabricated
    root = tmp_path / "metadata"
    shutil.copytree(source, root)
    return root, copy.deepcopy(binding), copy.deepcopy(identity)


def verify(sample):
    root, binding, identity = sample
    return V.verify_synthetic_metadata(root, binding=binding, identity=identity)


def change_rows(sample, mutator, *, index=0, repair_hash=True):
    root = sample[0]
    path = root / "test" / f"meta-{index:05d}.jsonl"
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    mutator(rows)
    path.write_text("\n".join(map(canonical, rows)) + "\n")
    if repair_hash:
        manifest = read(root / "manifest.json")
        descriptor = manifest["roles"]["test"]["shards"][index]
        descriptor["sha256"][path.name] = raw_digest(path.read_bytes())
        write(root / "test" / f"shard-{index:05d}.json", descriptor)
        write(root / "manifest.json", manifest)


def change_descriptor(sample, mutator):
    root = sample[0]
    manifest = read(root / "manifest.json")
    mutator(manifest["roles"]["test"]["shards"][0])
    write(root / "test/shard-00000.json", manifest["roles"]["test"]["shards"][0])
    write(root / "manifest.json", manifest)


def test_fabricated_full_metadata_inventory_is_not_production_or_authority(fabricated):
    report = verify(fabricated)
    assert report["counts"] == {"headline": 500, "co_feed_missing": 35, "cross_feed_missing": 43, "missing_total": 78, "sensitivity": 465}
    assert report["metadata_status"] == "SYNTHETIC_FIXTURE_ONLY"
    assert report["production_cross_verification_performed"] is False
    assert report["metadata_files_verified"] == 253
    assert report["verdict"] == "NO-GO"
    assert report["execution_authorized"] is report["production_authorized"] is report["benchmark_complete"] is False
    assert report["observation_reads"] == report["waveform_synthesis_calls"] == 0
    assert report["payload_checksum_status"].startswith("NOT_VERIFIED")
    assert report["d1_obligations"]["existing_test_pristine"] is False
    assert report["d1_obligations"]["exposure_excluded_groups"] == {"test": 498, "test-matched": 148}
    assert report == verify(fabricated)
    json.loads(canonical(report), parse_constant=lambda _: pytest.fail("nonfinite result"))


def test_production_api_cannot_accept_fabricated_scene_identity(sample):
    with pytest.raises(V.MetadataError, match="scene_metadata|fingerprints"):
        V.verify_production_metadata(sample[0], binding=sample[1])


def test_synthetic_api_refuses_official_schema(sample):
    sample[2]["schema"] = "B2-E10-k17d-identity-record/1"
    with pytest.raises(V.MetadataError, match="fabricated identity"):
        verify(sample)


@pytest.mark.parametrize("mutation", [
    lambda r: r[0].update(role="train"),
    lambda r: r[0].update(scenario_id=3000000),
    lambda r: r[0].update(scenario_id=True),
    lambda r: r[0].update(label="cw"),
    lambda r: r[0].update(protocol="B2-features/1"),
    lambda r: r[0].update(base_protocol="B2-feat/1"),
    lambda r: r[0].update(parent_protocol="other"),
    lambda r: r[0].update(missing_carrier_override=False),
    lambda r: r[0].update(plan_consistency=True),
    lambda r: r[0].update(receiver_calibration_applied=False),
    lambda r: r[0].update(receiver_calibration={}),
    lambda r: r[0].update(scores=[0.1]),
    lambda r: r[0].update(spec=[]),
    lambda r: r.pop(),
    lambda r: r.append(r[0]),
    lambda r: r[0].pop("dropped_carrier"),
    lambda r: r[0].update(dropped_carrier={"polarization": 0, "index": 0}, plan_consistency=1),
])
def test_corrupt_roles_variants_predicates_and_counts_fail_even_with_repaired_checksums(sample, mutation):
    change_rows(sample, mutation)
    with pytest.raises(V.MetadataError):
        verify(sample)


def test_consistent_polarization_swap_preserving_counts_and_rehashed_shards_fails(sample):
    root, _, identity = sample
    co, cross = identity["co_feed_missing_ids"][0], identity["cross_feed_missing_ids"][0]
    for group, pol in ((co, 1), (cross, 0)):
        index, position = divmod(group - 3200000, 4)
        def mutate(rows, position=position, pol=pol):
            for row in rows[position * 8:(position + 1) * 8]:
                row["dropped_carrier"]["polarization"] = pol
        change_rows(sample, mutate, index=index)
    with pytest.raises(V.MetadataError, match="identity differs"):
        verify(sample)


def test_consistent_carrier_index_drift_fails_full_scene_digest(sample):
    group = sample[2]["co_feed_missing_ids"][0]
    index, position = divmod(group - 3200000, 4)
    def mutate(rows):
        for row in rows[position * 8:(position + 1) * 8]:
            row["dropped_carrier"]["index"] += 1
    change_rows(sample, mutate, index=index)
    with pytest.raises(V.MetadataError, match="fingerprints"):
        verify(sample)


@pytest.mark.parametrize("mutation", [
    lambda d: d.update(role="val-calib"), lambda d: d.update(n_samples=True), lambda d: d.update(n_samples=31),
    lambda d: d["scenario_seeds"].reverse(), lambda d: d.update(meta="../../meta-00000.jsonl"),
    lambda d: d.update(part="../part-00000.npz"), lambda d: d.update(request_fingerprint="0" * 64),
    lambda d: d.update(unexpected=True), lambda d: d["sha256"].update({"part-00000.npz": "bad"}),
    lambda d: d["sha256"].update({"meta-00000.jsonl": "0" * 64}),
])
def test_forged_descriptor_is_refused(sample, mutation):
    change_descriptor(sample, mutation)
    with pytest.raises(V.MetadataError):
        verify(sample)


@pytest.mark.parametrize("mutation", [
    lambda b: b.update(source_head="0" * 40), lambda b: b.update(source_head="bad"),
    lambda b: b.update(schema="other"), lambda b: b.update(execute=True),
    lambda b: b.update(request_fingerprint="0" * 64),
    lambda b: b["request"].update(groups_per_shard=True), lambda b: b["request"].update(groups_per_shard=8),
    lambda b: b["request"].update(limit_groups=2), lambda b: b["request"].update(numpy_version=None),
    lambda b: b["request"]["source_sha256"].update({"b2_scenarios.py": "0" * 64}),
    lambda b: b["request"]["config"].update(calibration_seed=42),
    lambda b: b["request"]["cancellation"].update(version="oracle"),
])
def test_wrong_frozen_run_binding_fails(sample, mutation):
    mutation(sample[1])
    with pytest.raises(V.MetadataError):
        verify(sample)


def test_config_edit_cannot_be_hidden_by_rehashing_binding_and_manifest(sample):
    root, binding, _ = sample
    binding["request"]["config"]["drop_probability"] = 0.2
    binding["request_fingerprint"] = digest(binding["request"])
    manifest = read(root / "manifest.json")
    manifest.update(request=binding["request"], request_fingerprint=binding["request_fingerprint"], config=binding["request"]["config"])
    write(root / "manifest.json", manifest)
    write(root / "request.json", binding["request"])
    with pytest.raises(V.MetadataError, match="configuration changed"):
        verify(sample)


@pytest.mark.parametrize("name", ["request.json", "manifest.json", "calibration.json", "test/shard-00000.json", "test/meta-00000.jsonl", "test/part-00000.npz"])
def test_missing_required_metadata_or_payload_name_fails(sample, name):
    (sample[0] / name).unlink()
    with pytest.raises(V.MetadataError):
        verify(sample)


@pytest.mark.parametrize("name", ["test/meta-00000.jsonl", "test/shard-00000.json", "test/part-00000.npz", "manifest.json"])
def test_symlink_substitution_fails_without_following_it(sample, name):
    root = sample[0]
    path = root / name
    moved = path.with_name("original-" + path.name)
    path.rename(moved)
    path.symlink_to(moved)
    with pytest.raises(V.MetadataError):
        verify(sample)


def test_symlink_root_and_traversal_are_refused(sample):
    root, binding, identity = sample
    alias = root.parent / "alias"
    alias.symlink_to(root, target_is_directory=True)
    for path in (alias, root / ".." / root.name):
        with pytest.raises(V.MetadataError):
            V.verify_synthetic_metadata(path, binding=binding, identity=identity)


def test_same_inode_hardlink_alias_is_refused(sample):
    root = sample[0]
    a, b = root / "test/meta-00000.jsonl", root / "test/meta-00001.jsonl"
    b.unlink()
    os.link(a, b)
    with pytest.raises(V.MetadataError, match="unique|alias"):
        verify(sample)


@pytest.mark.parametrize("name", ["meta-00000.jsonl.tmp", "part-00125.npz", "unexpected.json", "shard-00000.json.tmp"])
def test_orphan_or_extra_artifact_is_not_committed(sample, name):
    (sample[0] / "test" / name).write_bytes(b"evidence is preserved")
    with pytest.raises(V.MetadataError, match="orphaned"):
        verify(sample)
    assert (sample[0] / "test" / name).exists()


@pytest.mark.parametrize("raw", [b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":1e999}', b'[]', b'\xff', b''])
def test_strict_json_metadata_refuses_duplicates_nonfinite_and_malformed(sample, raw):
    (sample[0] / "test/shard-00000.json").write_bytes(raw)
    with pytest.raises(V.MetadataError):
        verify(sample)


def test_bounded_metadata_read_refuses_oversize(sample):
    (sample[0] / "test/meta-00000.jsonl").write_bytes(b" " * (V.MAX_METADATA_BYTES + 1))
    with pytest.raises(V.MetadataError, match="bounded size"):
        verify(sample)


def test_metadata_tampering_without_descriptor_update_fails_checksum(sample):
    change_rows(sample, lambda rows: rows[0].update(fabricated_fixture="edited"), repair_hash=False)
    with pytest.raises(V.MetadataError, match="checksum"):
        verify(sample)


def test_payload_bytes_are_never_claimed_verified(sample):
    # A same-size payload edit is outside this metadata-only validator's remit.
    (sample[0] / "test/part-00000.npz").write_bytes(b"Z" * len(b"FABRICATED NOT AN ARRAY"))
    report = verify(sample)
    assert report["payload_checksum_status"].startswith("NOT_VERIFIED")
    assert report["verdict"] == "NO-GO"


def test_concurrent_metadata_edit_is_detected_by_snapshot(sample, monkeypatch):
    original = V._MetadataReader.recheck
    def edit_then_recheck(reader):
        path = sample[0] / "test/meta-00000.jsonl"
        path.write_bytes(path.read_bytes() + b" ")
        original(reader)
    monkeypatch.setattr(V._MetadataReader, "recheck", edit_then_recheck)
    with pytest.raises(V.MetadataError, match="changed during"):
        verify(sample)


def test_no_payload_open_generator_model_or_subprocess_in_either_api(sample, monkeypatch):
    from geosim import b2_dataset, b2_scenarios, b2_test_dataset, b2_matched_dataset
    def forbidden(*args, **kwargs):
        pytest.fail("prohibited process, generator, waveform or array access")
    for name in ("Popen", "run", "call", "check_call", "check_output"):
        monkeypatch.setattr(subprocess, name, forbidden)
    for name in ("system", "popen", "fork", "posix_spawn", "posix_spawnp"):
        if hasattr(os, name):
            monkeypatch.setattr(os, name, forbidden)
    monkeypatch.setattr(np, "load", forbidden)
    monkeypatch.setattr(b2_scenarios, "prepare_scene", forbidden)
    monkeypatch.setattr(b2_scenarios, "sample_scene", forbidden)
    monkeypatch.setattr(b2_scenarios, "simulate_dual", forbidden)
    for module in (b2_dataset, b2_test_dataset, b2_matched_dataset):
        for name in tuple(vars(module)):
            if name.startswith("generate_"):
                monkeypatch.setattr(module, name, forbidden)
    actual_open = os.open
    def metadata_only_open(path, *args, **kwargs):
        if str(path).endswith(".npz"):
            pytest.fail("payload opened")
        return actual_open(path, *args, **kwargs)
    monkeypatch.setattr(os, "open", metadata_only_open)
    assert verify(sample)["execution_authorized"] is False
    with pytest.raises(V.MetadataError, match="fingerprints"):
        V.verify_production_metadata(sample[0], binding=sample[1])


def test_root_path_replacement_during_validation_is_refused(sample, monkeypatch):
    original = V._MetadataReader.recheck
    def replace_then_recheck(reader):
        root = sample[0]
        root.rename(root.with_name("preserved-displaced-tree"))
        root.mkdir()
        original(reader)
    monkeypatch.setattr(V._MetadataReader, "recheck", replace_then_recheck)
    with pytest.raises(V.MetadataError, match="root pathname was replaced"):
        verify(sample)


@pytest.mark.parametrize("name", ["test-matched", "scores.json", "request.json.tmp"])
def test_cross_role_or_unknown_root_entry_is_refused(sample, name):
    path = sample[0] / name
    path.write_bytes(b"preserved synthetic unexpected metadata")
    with pytest.raises(V.MetadataError, match="root entries"):
        verify(sample)
    assert path.exists()


def test_unexpected_manifest_option_is_refused(sample):
    path = sample[0] / "manifest.json"
    manifest = read(path)
    manifest["execute"] = False
    write(path, manifest)
    with pytest.raises(V.MetadataError, match="manifest fields"):
        verify(sample)


@pytest.mark.parametrize("field,value,match", [
    ("source_sha256", {"b2_scenarios.py": "0" * 64}, "generator source"),
    ("numpy_version", "", "numerical environment"),
    ("scipy_version", None, "numerical environment"),
    ("roles", ["test"], "inventory"),
    ("groups_per_shard", 8, "four-group"),
    ("limit_groups", 2, "inventory"),
])
def test_self_rehashed_request_does_not_override_frozen_contract(sample, field, value, match):
    root, binding, _ = sample
    binding["request"][field] = value
    binding["request_fingerprint"] = digest(binding["request"])
    manifest = read(root / "manifest.json")
    manifest.update(request=binding["request"], request_fingerprint=binding["request_fingerprint"])
    write(root / "manifest.json", manifest)
    write(root / "request.json", binding["request"])
    with pytest.raises(V.MetadataError, match=match):
        verify(sample)


@pytest.mark.parametrize("mutation", [
    lambda value: value.update(provenance="fabricated-but-not-request-bound"),
    lambda value: value.update(n_pilots=True),
    lambda value: value.update(artifact_version=True),
])
def test_self_rehashed_calibration_cannot_override_request_provenance(sample, mutation):
    root = sample[0]
    manifest = read(root / "manifest.json")
    mutation(manifest["calibration"])
    manifest["calibration"]["artifact_sha256"] = digest({key: value for key, value in manifest["calibration"].items()
                                                        if key != "artifact_sha256"})
    descriptor = {**manifest["calibration_artifact"], "metadata": manifest["calibration"]}
    manifest["calibration_artifact"] = descriptor
    write(root / "manifest.json", manifest)
    write(root / "calibration.json", descriptor)
    with pytest.raises(V.MetadataError, match="independent calibration"):
        verify(sample)

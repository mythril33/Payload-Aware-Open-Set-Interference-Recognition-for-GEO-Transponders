"""Test-only B2 families bound to a verified known-stage artifact (P18 §3).

    python -m geosim.b2_test_dataset --out data/b2-test-pilot --known data/b2-feat-pilot \
        --config configs/b2_base.json --cancellation configs/cancellation.json --limit-groups 2

The B2-test/1 stage generates, for frozen ``test``-role groups only, the five
test-only variants ``pulsed``, ``intermittent_bursts``, ``adjacent_satellite_downlink``
(near unknowns), ``wideband_noise`` (equivalence-limited unknown) and
``cid_overlay`` (benign, expected decision ``clean``). Every variant shares its
group's operator plans, link settings, carrier/noise streams, phase realizations
and missing-carrier state with the known variants of the same group, and uses the
*same* receiver calibration as the known artifact it is bound to. These samples
never enter training, checkpoint selection or threshold calibration; the reader
exposes them for evaluation only. The ``family`` array indexes ``TEST_FAMILIES``,
not the known label set.
"""
from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path

import numpy as np
import scipy

from .b2_dataset import (_READ_ERRORS, _activity, _cancellation_record, _file_hash, _fingerprint, _paths,
                         _positive_int, _residual, _stage, read_b2_manifest)
from .b2_protocol import (FIFTH_CHANNEL, PROTOCOL, B2Config, protocol_contract, receiver_response, scenario_ids)
from .b2_scenarios import EXPECTED_DECISION, TEST_FAMILIES, TEST_PROTOCOL, sample_test_scene
from .cancellation import CancellationConfig
from .dataset import _atomic_json, _commit, _generator_provenance
from .event_dataset import _real, _stored_carrier, _strict_json
from .plan import plan_mask_db
from .polarization import ReceiverCalibration

ROLE = "test"
STAGE = "test_only_families"
ARRAY_KEYS = ("spec", "mask", "family", "seed", "plan_consistency")
FEATURE_ARRAY_KEYS = ARRAY_KEYS + ("residual",)
GROUPS_PER_SHARD = 8
FAMILY_GROUPS = {"pulsed": "near", "intermittent_bursts": "near", "adjacent_satellite_downlink": "near",
                 "wideband_noise": "equivalence_limited", "cid_overlay": "benign"}


def _known_binding(known_root: Path, config: B2Config, cancellation):
    """Verify the known-stage artifact and return what the test stage must share with it."""
    manifest = read_b2_manifest(known_root)
    known_protocol, _, known_cancellation, _ = _stage(manifest["request"])
    if manifest["request"]["config"] != config.to_dict():
        raise ValueError("test-only families must use the known artifact's physical configuration")
    if (known_cancellation is None) != (cancellation is None) or (
            cancellation is not None and known_cancellation.to_dict() != cancellation.to_dict()):
        raise ValueError("test-only families must use the known artifact's cancellation setting")
    if ROLE not in manifest["roles"]:
        raise ValueError("the known artifact must contain the frozen test role")
    return {"known_protocol": known_protocol, "known_data_fingerprint": _fingerprint(manifest),
            "known_request_fingerprint": manifest["request_fingerprint"],
            "known_test_groups": manifest["roles"][ROLE]["scenario_seeds"],
            "known_calibration": manifest["calibration"]}


def _request(config, limit_groups, groups_per_shard, cancellation, binding):
    groups_per_shard = _positive_int(groups_per_shard, "groups_per_shard", 100)
    if limit_groups is not None:
        limit_groups = _positive_int(limit_groups, "limit_groups")
    groups = scenario_ids(ROLE, limit_groups)
    if not set(groups) <= set(binding["known_test_groups"]):
        raise ValueError("requested test groups are not all present in the known artifact's test role")
    if cancellation is not None and not isinstance(cancellation, CancellationConfig):
        raise ValueError("cancellation must be a CancellationConfig or None")
    request = {"protocol": TEST_PROTOCOL, "parent_protocol": PROTOCOL, "artifact_stage": STAGE,
               "benchmark_complete": False, "contract": protocol_contract(), "config": config.to_dict(),
               "families": list(TEST_FAMILIES), "expected_decision": dict(EXPECTED_DECISION),
               "family_groups": dict(FAMILY_GROUPS), "role": ROLE, "scenario_groups": groups,
               "limit_groups": limit_groups, "groups_per_shard": groups_per_shard,
               "known": binding, "source_sha256": _generator_provenance(),
               "numpy_version": np.__version__, "scipy_version": scipy.__version__}
    if cancellation is not None:
        request.update(cancellation=cancellation.to_dict(), fifth_channel=dict(FIFTH_CHANNEL))
    return request


def _cancellation_of(request):
    if "cancellation" not in request:
        return None, ARRAY_KEYS
    if request.get("fifth_channel") != FIFTH_CHANNEL or not isinstance(request["cancellation"], dict):
        raise ValueError("B2 test request has an inconsistent fifth-channel contract")
    try:
        return CancellationConfig(**request["cancellation"]), FEATURE_ARRAY_KEYS
    except TypeError as error:
        raise ValueError(f"invalid B2 cancellation settings: {error}") from error


def _groups(request, index=None):
    groups = request["scenario_groups"]
    size = request["groups_per_shard"]
    return groups if index is None else groups[index * size:(index + 1) * size]


def _n_shards(request):
    return -(-len(_groups(request)) // request["groups_per_shard"])


def _names(root, request, *, complete):
    count = _n_shards(request)
    for pattern, template in (("part-*.npz", "part-{i:05d}.npz"), ("meta-*.jsonl", "meta-{i:05d}.jsonl"),
                              ("shard-*.json", "shard-{i:05d}.json")):
        actual = {path.name for path in (root / ROLE).glob(pattern) if not path.name.endswith(".tmp.npz")}
        expected = {template.format(i=index) for index in range(count)}
        if not actual <= expected or (complete and actual != expected):
            raise ValueError(f"unexpected or missing B2 test artifacts: {pattern}")


def _save_calibration(root, calibration):
    path = root / "receiver_calibration.npz"
    calibration.save(path)
    _atomic_json(root / "calibration.json", {"file": path.name, "sha256": _file_hash(path),
                                             "metadata": calibration.to_dict()})


def _calibration(root, request):
    descriptor = _strict_json((root / "calibration.json").read_text())
    path = root / "receiver_calibration.npz"
    if descriptor.get("file") != path.name or descriptor.get("sha256") != _file_hash(path):
        raise ValueError("missing or modified B2 test receiver calibration")
    calibration = ReceiverCalibration.load(path)
    if calibration.to_dict() != descriptor.get("metadata") or calibration.to_dict() != request["known"]["known_calibration"]:
        raise ValueError("B2 test calibration is not the known artifact's receiver calibration")
    return calibration, descriptor


def _event(record, family, plans, active, bandwidth):
    event = record["event"]
    downlink = family == "adjacent_satellite_downlink"
    if (event["kind"] != family or event["injection_stage"] != ("downlink" if downlink else "uplink")
            or record["has_interferer"] != [not downlink, False]
            or record["has_downlink_interferer"] != [downlink, False]
            or event.get("test_only") is not True):
        raise ValueError("B2 test-only event has the wrong family, injection stage or flags")
    if family in ("pulsed", "intermittent_bursts", "wideband_noise"):
        if event["power_reference"] != "total_planned_uplink":
            raise ValueError("unknown family has the wrong power reference")
        _real(event["active_c_over_i_db"], "active C/I", minimum=5, maximum=35)
        if family != "wideband_noise":
            occupied = event["occupied_snapshots"]
            if not isinstance(occupied, list) or not any(occupied) or all(occupied):
                raise ValueError("temporal unknown family must have active and inactive snapshots")
    elif downlink:
        if event["power_reference"] != "wanted_receiver_feed" or event.get("bypasses_wanted_payload") is not True:
            raise ValueError("downlink ASI must bypass the wanted payload with the feed-power reference")
        carrier = _stored_carrier(event["carrier"], bandwidth)
        mean_psd = sum(c.power for c in plans[0]) / sum(c.symbol_rate for c in plans[0])
        geometry = event["geometry"]
        expected_ci = geometry["max_gain_dbi"] - geometry["gain_toward_victim_dbi"] - geometry["delta_eirp_density_db"]
        if (not np.isclose(event["c_over_i_psd_db"], expected_ci, rtol=0, atol=1e-10)
                or not np.isclose(carrier.power, mean_psd * carrier.symbol_rate * 10 ** (-expected_ci / 10), rtol=1e-12, atol=0)
                or not 0.2 - 1e-10 <= event["overlap_fraction"] <= 0.8 + 1e-10):
            raise ValueError("downlink ASI geometry, level or placement differs from the known uplink convention")
    else:
        if (event.get("legitimate") is not True or event.get("expected_label") != "clean"
                or len(event["cids"]) != len(plans[0]) or event["n_transmitted"] != sum(active[0])
                or any(entry["host_active"] != flag for entry, flag in zip(event["cids"], active[0]))
                or any(entry["host_f0"] != c.f0 for entry, c in zip(event["cids"], plans[0]))):
            raise ValueError("CID overlay must ride on exactly the transmitted planned carriers")


def _record(record, config, group, family_index, consistency, calibration_metadata, cancellation):
    family = TEST_FAMILIES[family_index]
    if (record["protocol"] != TEST_PROTOCOL or record["parent_protocol"] != PROTOCOL
            or record["label"] != family or record["role"] != ROLE or record["scenario_id"] != group
            or record["test_only"] is not True or record["expected_decision"] != EXPECTED_DECISION[family]
            or record["family_group"] != FAMILY_GROUPS[family]
            or type(record["plan_consistency"]) is not int or record["plan_consistency"] != consistency
            or record["receiver_calibration_applied"] is not True
            or record["receiver_calibration"] != calibration_metadata):
        raise ValueError("B2 test metadata does not match the family, group or calibration")
    scene = record["config"]
    if (scene["uplink_xpd_db"] != config.nominal_xpd_db or scene["downlink_xpd_db"] != config.downlink_xpd_db
            or scene["satellite_linewidth_hz"] != config.satellite_linewidth_hz
            or scene["receiver_linewidth_hz"] != config.receiver_linewidth_hz):
        raise ValueError("B2 test-only scene changed a nominal physical setting")
    response = scene["receiver_response"]
    matrix = np.asarray(response["real"]) + 1j * np.asarray(response["imag"])
    if matrix.shape != (2, 2) or not np.allclose(matrix, receiver_response(config), rtol=1e-12, atol=1e-12):
        raise ValueError("B2 test instrument response differs from the request")
    nominal = record["nominal_ibo_db"]
    for pol, key in enumerate(("co", "cross")):
        path = scene[key]
        _real(nominal[pol], "nominal back-off", minimum=9, maximum=13)
        if (path["seed"] != 2 * group + pol or path["bandwidth"] != config.bandwidth or path["ibo_db"] != nominal[pol]
                or path["n_snap"] != config.n_snap or path["snap_interval"] != config.snap_interval
                or path["linear"] is not False or path["filter_model"] != "etsi" or path["amplifier"] != "dvbs2_nl"):
            raise ValueError("B2 test-only path differs from the shared nominal scene")
        for key_cn in ("cn_up_db", "cn_dn_db"):
            _real(path[key_cn], key_cn, minimum=15, maximum=30)
    plans = [[_stored_carrier(item, config.bandwidth) for item in plan] for plan in record["plans"]]
    if (len(plans) != 2 or any(not plan for plan in plans)
            or any(not np.isclose(sum(c.power for c in plan), 1, rtol=1e-6, atol=1e-8) for plan in plans)):
        raise ValueError("B2 test operator plans must contain two unit nominal loads")
    active = _activity(record, plans, consistency)
    _event(record, family, plans, active, config.bandwidth)
    _cancellation_record(record, plans, cancellation)
    common = {key: record[key] for key in ("plans", "active_carriers", "active_planned_power", "nominal_ibo_db",
                                           "operator_plan_source", "dropped_carrier", "missing_carrier_convention", "config")}
    return common, np.stack([plan_mask_db(plan) for plan in plans]).astype(np.float16)


def _read_part(part, metadata, config, groups, calibration_metadata, cancellation, keys):
    with np.load(part, allow_pickle=False) as archive:
        if set(archive.files) != set(keys):
            raise ValueError("unexpected B2 test array keys")
        data = {key: archive[key] for key in keys}
    records = [_strict_json(line) for line in metadata.read_text().splitlines()]
    n = len(groups) * len(TEST_FAMILIES)
    if (data["spec"].shape != (n, 2, 128, 512) or data["mask"].shape != (n, 2, 512)
            or data["spec"].dtype != np.float16 or data["mask"].dtype != np.float16
            or any(data[key].shape != (n,) or data[key].dtype.kind not in "iu" for key in ("family", "seed", "plan_consistency"))
            or not np.isfinite(data["spec"]).all() or not np.isfinite(data["mask"]).all()
            or not np.isin(data["plan_consistency"], [0, 1]).all() or len(records) != n):
        raise ValueError("invalid B2 test dimensions, dtypes, values or metadata count")
    if cancellation is not None and (data["residual"].shape != (n, 128, 512) or data["residual"].dtype != np.float16
                                     or not np.isfinite(data["residual"]).all()):
        raise ValueError("invalid B2 test cancellation-residual array")
    pairs = list(zip(data["seed"].tolist(), data["family"].tolist()))
    if len(set(pairs)) != n or set(pairs) != {(seed, index) for seed in groups for index in range(len(TEST_FAMILIES))}:
        raise ValueError("B2 test scenario-family pairs differ from the requested groups")
    paired = {}
    for seed, index, consistency, mask, record in zip(data["seed"], data["family"], data["plan_consistency"], data["mask"], records):
        common, expected_mask = _record(record, config, int(seed), int(index), int(consistency), calibration_metadata, cancellation)
        if not np.array_equal(mask, expected_mask):
            raise ValueError("B2 test masks differ from full operator plans")
        if int(seed) in paired and paired[int(seed)] != common:
            raise ValueError("test-only variants of one group differ beyond their family event")
        paired[int(seed)] = common
    return {**data, "meta": records}


def _verify_part(root, request, index, descriptor, config, calibration_metadata):
    part, metadata, descriptor_path = _paths(root, ROLE, index)
    groups = _groups(request, index)
    cancellation, keys = _cancellation_of(request)
    if (descriptor.get("part") != part.name or descriptor.get("meta") != metadata.name or descriptor.get("role") != ROLE
            or descriptor.get("scenario_seeds") != groups or descriptor.get("n_samples") != len(groups) * len(TEST_FAMILIES)
            or descriptor.get("request_fingerprint") != _fingerprint(request)):
        raise ValueError("incompatible B2 test shard descriptor")
    if descriptor_path.exists() and _strict_json(descriptor_path.read_text()) != descriptor:
        raise ValueError("B2 test shard descriptor differs from manifest")
    for path in (part, metadata):
        if not path.is_file() or descriptor.get("sha256", {}).get(path.name) != _file_hash(path):
            raise ValueError(f"missing or modified B2 test artifact: {path}")
    return _read_part(part, metadata, config, groups, calibration_metadata, cancellation, keys)


def generate_b2_test_dataset(out_dir, known_dir, config: B2Config | None = None, *, limit_groups=None,
                             groups_per_shard=GROUPS_PER_SHARD, cancellation: CancellationConfig | None = None) -> None:
    """Generate the test-only families for frozen test groups, bound to a verified known artifact."""
    config = B2Config() if config is None else config
    if not isinstance(config, B2Config):
        raise ValueError("config must be a B2Config")
    known_root = Path(known_dir)
    binding = _known_binding(known_root, config, cancellation)
    request = _request(config, limit_groups, groups_per_shard, cancellation, binding)
    cancellation, keys = _cancellation_of(request)
    request_id = _fingerprint(request)
    root = Path(out_dir)
    request_path = root / "request.json"
    if request_path.exists():
        if _strict_json(request_path.read_text()) != request:
            raise ValueError("B2 test generation request changed; use a fresh output directory")
    elif root.exists() and any(root.iterdir()):
        raise ValueError("unverified B2 test output directory; use a fresh directory")
    else:
        root.mkdir(parents=True, exist_ok=True)
        _atomic_json(request_path, request)
        _save_calibration(root, ReceiverCalibration.load(known_root / "receiver_calibration.npz"))
    if (root / "manifest.json").exists():
        manifest = read_b2_test_manifest(root)
        print(f"reusing verified {TEST_PROTOCOL} dataset ({manifest['n_samples']} samples)", flush=True)
        return
    if not (root / "calibration.json").exists():
        if (root / "receiver_calibration.npz").exists():
            raise ValueError("unverified partial B2 test calibration; use a fresh output directory")
        _save_calibration(root, ReceiverCalibration.load(known_root / "receiver_calibration.npz"))
    calibration, calibration_artifact = _calibration(root, request)
    (root / ROLE).mkdir(exist_ok=True)
    _names(root, request, complete=False)
    descriptors = []
    for index in range(_n_shards(request)):
        part, metadata, descriptor_path = _paths(root, ROLE, index)
        if descriptor_path.exists():
            descriptor = _strict_json(descriptor_path.read_text())
            _verify_part(root, request, index, descriptor, config, calibration.to_dict())
        else:
            if part.exists() or metadata.exists():
                raise ValueError("unverified partial B2 test shard; use a fresh output directory")
            arrays, records = {key: [] for key in keys}, []
            for group in _groups(request, index):
                for family_index, family in enumerate(TEST_FAMILIES):
                    result = sample_test_scene(family, group, config, calibration=calibration,
                                               keep_iq=cancellation is not None)
                    if cancellation is not None:
                        plans = [[_stored_carrier(item, config.bandwidth) for item in plan] for plan in result.meta["plans"]]
                        arrays["residual"].append(_residual(result, plans, cancellation))
                        result.iq = None
                    arrays["spec"].append(result.spec_db.astype(np.float16))
                    arrays["mask"].append(result.mask_db.astype(np.float16))
                    arrays["family"].append(family_index)
                    arrays["seed"].append(group)
                    arrays["plan_consistency"].append(result.meta["plan_consistency"])
                    records.append(result.meta)
            stacked = {"spec": np.stack(arrays["spec"]), "mask": np.stack(arrays["mask"]),
                       "family": np.asarray(arrays["family"], np.int8), "seed": np.asarray(arrays["seed"], np.int64),
                       "plan_consistency": np.asarray(arrays["plan_consistency"], np.int8)}
            if cancellation is not None:
                stacked["residual"] = np.stack(arrays["residual"])
            temporary_part, temporary_meta = part.with_suffix(".tmp.npz"), metadata.with_suffix(".jsonl.tmp")
            np.savez(temporary_part, **stacked)
            temporary_meta.write_text("".join(json.dumps(record, allow_nan=False) + "\n" for record in records))
            _read_part(temporary_part, temporary_meta, config, _groups(request, index), calibration.to_dict(), cancellation, keys)
            temporary_part.replace(part)
            temporary_meta.replace(metadata)
            descriptor = {"part": part.name, "meta": metadata.name, "role": ROLE,
                          "scenario_seeds": _groups(request, index), "n_samples": len(records),
                          "request_fingerprint": request_id,
                          "sha256": {path.name: _file_hash(path) for path in (part, metadata)}}
            _atomic_json(descriptor_path, descriptor)
        descriptors.append(descriptor)
    count = len(_groups(request))
    manifest = {"artifact_version": 1, "protocol": TEST_PROTOCOL, "parent_protocol": PROTOCOL, "artifact_stage": STAGE,
                "benchmark_complete": False, "families": list(TEST_FAMILIES), "expected_decision": dict(EXPECTED_DECISION),
                "family_groups": dict(FAMILY_GROUPS), "config": config.to_dict(), "request": request,
                "request_fingerprint": request_id, "commit": _commit(), "calibration": calibration.to_dict(),
                "calibration_artifact": calibration_artifact, "role": ROLE, "scenario_seeds": _groups(request),
                "n_scenarios": count, "n_samples": count * len(TEST_FAMILIES),
                "per_family": {family: count for family in TEST_FAMILIES}, "shards": descriptors}
    if cancellation is not None:
        manifest.update(cancellation=cancellation.to_dict(), fifth_channel=dict(FIFTH_CHANNEL))
    _atomic_json(root / "manifest.json", manifest)
    read_b2_test_manifest(root)
    print(f"{ROLE}: {count * len(TEST_FAMILIES)} calibrated B2 test-only samples", flush=True)


def _header(root):
    manifest = _strict_json((root / "manifest.json").read_text())
    request = manifest["request"]
    config = B2Config(**request["config"])
    cancellation, _ = _cancellation_of(request)
    limit = request["limit_groups"]
    groups = scenario_ids(ROLE, None if limit is None else _positive_int(limit, "limit_groups"))
    _positive_int(request["groups_per_shard"], "groups_per_shard", 100)
    source_hashes = request["source_sha256"]
    if (not isinstance(source_hashes, dict) or not source_hashes
            or any(not isinstance(name, str) or not isinstance(digest, str) or len(digest) != 64 for name, digest in source_hashes.items())):
        raise ValueError("B2 test request must retain generator source hashes")
    known = request["known"]
    if (request["protocol"] != TEST_PROTOCOL or request["parent_protocol"] != PROTOCOL or request["artifact_stage"] != STAGE
            or request["benchmark_complete"] is not False or request["contract"] != protocol_contract()
            or request["families"] != list(TEST_FAMILIES) or request["expected_decision"] != EXPECTED_DECISION
            or request["family_groups"] != FAMILY_GROUPS or request["role"] != ROLE
            or request["scenario_groups"] != groups or not set(groups) <= set(known["known_test_groups"])
            or request["config"] != config.to_dict()
            or _strict_json((root / "request.json").read_text()) != request
            or manifest["artifact_version"] != 1 or manifest["protocol"] != TEST_PROTOCOL
            or manifest["parent_protocol"] != PROTOCOL or manifest["artifact_stage"] != STAGE
            or manifest["benchmark_complete"] is not False or manifest["families"] != list(TEST_FAMILIES)
            or manifest["config"] != config.to_dict() or manifest["request_fingerprint"] != _fingerprint(request)
            or manifest.get("cancellation") != (None if cancellation is None else cancellation.to_dict())
            or manifest.get("fifth_channel") != (None if cancellation is None else FIFTH_CHANNEL)
            or manifest["role"] != ROLE or manifest["scenario_seeds"] != groups or manifest["n_scenarios"] != len(groups)
            or manifest["n_samples"] != len(groups) * len(TEST_FAMILIES)
            or manifest["per_family"] != {family: len(groups) for family in TEST_FAMILIES}
            or len(manifest["shards"]) != _n_shards(request)):
        raise ValueError("inconsistent B2 test manifest/request")
    calibration, descriptor = _calibration(root, request)
    if descriptor != manifest["calibration_artifact"] or calibration.to_dict() != manifest["calibration"]:
        raise ValueError("B2 test manifest differs from the receiver calibration artifact")
    _names(root, request, complete=True)
    if any((root / name).is_dir() for name in ("train", "val-select", "val-calib", "test-matched")):
        raise ValueError("B2 test output contains a role that test-only families must never occupy")
    return manifest, config


def read_b2_test_manifest(path) -> dict:
    root = Path(path)
    try:
        manifest, config = _header(root)
        for index, descriptor in enumerate(manifest["shards"]):
            _verify_part(root, manifest["request"], index, descriptor, config, manifest["calibration"])
        return manifest
    except _READ_ERRORS as error:
        raise ValueError(f"invalid B2 test dataset {root}: {error}") from error


def iter_b2_test_shards(root):
    root = Path(root)
    try:
        manifest, config = _header(root)
        for index, descriptor in enumerate(manifest["shards"]):
            yield _verify_part(root, manifest["request"], index, descriptor, config, manifest["calibration"])
    except _READ_ERRORS as error:
        raise ValueError(f"invalid B2 test dataset {root}: {error}") from error


def load_b2_test_split(root) -> dict:
    """Load the test-only families into memory; ``family`` indexes ``TEST_FAMILIES``."""
    parts = list(iter_b2_test_shards(root))
    keys = [key for key in FEATURE_ARRAY_KEYS if all(key in part for part in parts)]
    return {**{key: np.concatenate([part[key] for part in parts]) for key in keys},
            "meta": [record for part in parts for record in part["meta"]], "families": list(TEST_FAMILIES)}


def b2_test_fingerprint(path) -> str:
    return _fingerprint(read_b2_test_manifest(path))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", required=True)
    parser.add_argument("--known", required=True, help="verified B2-base/1 or B2-feat/1 artifact to bind to")
    parser.add_argument("--config", help="JSON physical/instrument settings; must equal the known artifact's")
    parser.add_argument("--cancellation", help="JSON canceller settings; must equal the known artifact's")
    parser.add_argument("--limit-groups", type=int, help="pilot prefix of the frozen test role")
    parser.add_argument("--groups-per-shard", type=int, default=GROUPS_PER_SHARD)
    args = parser.parse_args(argv)
    try:
        config = B2Config.from_file(args.config) if args.config else B2Config()
        cancellation = None
        if args.cancellation:
            raw = _strict_json(Path(args.cancellation).read_text())
            if not isinstance(raw, dict):
                raise ValueError("cancellation configuration must be a JSON object")
            try:
                cancellation = CancellationConfig(**raw)
            except TypeError as error:
                raise ValueError(f"invalid cancellation configuration: {error}") from error
        generate_b2_test_dataset(args.out, args.known, config, limit_groups=args.limit_groups,
                                 groups_per_shard=args.groups_per_shard, cancellation=cancellation)
    except (ValueError, OSError) as error:
        parser.exit(2, f"error: {error}\n")


if __name__ == "__main__":
    main()

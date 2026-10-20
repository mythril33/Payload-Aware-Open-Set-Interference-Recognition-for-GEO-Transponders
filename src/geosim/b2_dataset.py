"""Verified known-class physical observations for the B2 foundation.

    python -m geosim.b2_dataset --out data/b2-base-pilot --limit-groups 2

This B2-base/1 stage stores two calibrated PSD streams and two operator plans.
It does not fabricate cancellation features or implement the final B2/1
unknown/CID/matched-test generation or five-channel learning benchmark.
"""
from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path
from zipfile import BadZipFile

import numpy as np
import scipy

from .b2_protocol import (BASE_PROTOCOL, BASE_ROLES, LABELS, PROTOCOL, B2Config,
                          protocol_contract, receiver_response, scenario_ids)
from .b2_scenarios import sample_scene
from .asi import overlap_fraction
from .dataset import _atomic_json, _commit, _file_hash, _fingerprint, _generator_provenance
from .event_dataset import _real, _stored_carrier, _strict_json
from .plan import plan_mask_db
from .polarization import ReceiverCalibration, fit_receiver_calibration

ARRAY_KEYS = ("spec", "mask", "label", "seed", "plan_consistency")
GROUPS_PER_SHARD = 8
ARTIFACT_STAGE = "known_physical_observations"
_WAVEFORM_LABELS = {"cw", "swept_cw", "unauthorized", "adjacent_satellite", "carrier_under_carrier"}
_READ_ERRORS = (OSError, KeyError, TypeError, ValueError, IndexError, EOFError, BadZipFile)


def _positive_int(value, name, maximum=100_000):
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, np.integer)) or not 1 <= value <= maximum:
        raise ValueError(f"{name} must be an integer in [1, {maximum}]")
    return int(value)


def _selection(roles, limit_groups, groups_per_shard):
    if (not isinstance(roles, (tuple, list)) or not roles
            or any(not isinstance(role, str) or role not in BASE_ROLES for role in roles)
            or len(set(roles)) != len(roles)):
        raise ValueError(f"roles must be unique choices from {BASE_ROLES}; test-matched is a separate stage")
    groups_per_shard = _positive_int(groups_per_shard, "groups_per_shard", 100)
    if limit_groups is not None:
        limit_groups = _positive_int(limit_groups, "limit_groups")
    return list(roles), {role: scenario_ids(role, limit_groups) for role in roles}, groups_per_shard


def _request(config, roles, limit_groups, groups_per_shard):
    roles, groups, groups_per_shard = _selection(roles, limit_groups, groups_per_shard)
    limit_groups = None if limit_groups is None else int(limit_groups)
    return {"protocol": BASE_PROTOCOL, "parent_protocol": PROTOCOL, "artifact_stage": ARTIFACT_STAGE,
            "benchmark_complete": False, "contract": protocol_contract(), "config": config.to_dict(),
            "roles": roles, "scenario_groups": groups, "limit_groups": limit_groups,
            "groups_per_shard": groups_per_shard, "source_sha256": _generator_provenance(),
            "numpy_version": np.__version__, "scipy_version": scipy.__version__}


def _fit_calibration(config, request_id):
    rng = np.random.default_rng([config.calibration_seed, 18001])
    reference = (rng.standard_normal((2, config.calibration_samples))
                 + 1j * rng.standard_normal((2, config.calibration_samples))) / np.sqrt(2)
    noise = config.calibration_noise_std * (rng.standard_normal(reference.shape)
                                            + 1j * rng.standard_normal(reference.shape)) / np.sqrt(2)
    return fit_receiver_calibration(reference, receiver_response(config) @ reference + noise,
                                    provenance=f"{BASE_PROTOCOL}:{request_id}:independent_pilots")


def _save_calibration(root, calibration):
    path = root / "receiver_calibration.npz"
    calibration.save(path)
    _atomic_json(root / "calibration.json", {"file": path.name, "sha256": _file_hash(path),
                                             "metadata": calibration.to_dict()})


def _calibration(root, request_id):
    descriptor = _strict_json((root / "calibration.json").read_text())
    path = root / "receiver_calibration.npz"
    if descriptor.get("file") != path.name or descriptor.get("sha256") != _file_hash(path):
        raise ValueError("missing or modified B2 receiver calibration")
    calibration = ReceiverCalibration.load(path)
    if (calibration.to_dict() != descriptor.get("metadata")
            or calibration.provenance != f"{BASE_PROTOCOL}:{request_id}:independent_pilots"):
        raise ValueError("B2 receiver calibration is not bound to this independent pilot request")
    return calibration, descriptor


def _paths(root, role, index):
    directory = root / role
    return (directory / f"part-{index:05d}.npz", directory / f"meta-{index:05d}.jsonl",
            directory / f"shard-{index:05d}.json")


def _groups(request, role, index=None):
    groups = request["scenario_groups"][role]
    size = request["groups_per_shard"]
    return groups if index is None else groups[index * size:(index + 1) * size]


def _n_shards(request, role):
    return -(-len(_groups(request, role)) // request["groups_per_shard"])


def _names(root, request, role, *, complete):
    count = _n_shards(request, role)
    for pattern, template in (("part-*.npz", "part-{i:05d}.npz"), ("meta-*.jsonl", "meta-{i:05d}.jsonl"),
                              ("shard-*.json", "shard-{i:05d}.json")):
        actual = {path.name for path in (root / role).glob(pattern) if not path.name.endswith(".tmp.npz")}
        expected = {template.format(i=index) for index in range(count)}
        if not actual <= expected or (complete and actual != expected):
            raise ValueError(f"unexpected or missing B2 artifacts in {role}: {pattern}")


def _activity(record, plans, consistency):
    active = record["active_carriers"]
    if (not isinstance(active, list) or len(active) != 2
            or any(not isinstance(mask, list) or len(mask) != len(plan)
                   or any(type(value) is not bool for value in mask) for mask, plan in zip(active, plans))):
        raise ValueError("B2 active-carrier masks do not match operator plans")
    missing = [(pol, index) for pol, mask in enumerate(active) for index, keep in enumerate(mask) if not keep]
    if len(missing) != consistency or not any(active[0]):
        raise ValueError("B2 missing-carrier label is inconsistent with active broadcasts")
    dropped = {"polarization": missing[0][0], "index": missing[0][1]} if missing else None
    if record["dropped_carrier"] != dropped or record["missing_carrier_override"] is not None:
        raise ValueError("B2 missing-carrier state differs from the sampled dataset convention")
    powers = [sum(carrier.power for carrier, keep in zip(plan, mask) if keep) for plan, mask in zip(plans, active)]
    for value in record["nominal_planned_power"]:
        _real(value, "nominal planned power", minimum=1, maximum=1)
    for value in record["active_planned_power"]:
        _real(value, "active planned power", minimum=0, maximum=1 + 1e-6)
    if (record["nominal_planned_power"] != [1, 1]
            or record["gain_mode"] != "fixed_nominal_planned_power"
            or np.shape(record["active_planned_power"]) != (2,)
            or not np.allclose(record["active_planned_power"], powers, rtol=1e-12, atol=1e-12)):
        raise ValueError("B2 active load was renormalized or has the wrong fixed-gain reference")
    return active


def _event(record, name, plans, active, bandwidth):
    event = record["event"]
    stage = "uplink" if name in _WAVEFORM_LABELS else {
        "clean": "none", "overdrive": "payload", "cross_pol": "uplink_coupling"}[name]
    if (event["kind"] != name or event["injection_stage"] != stage
            or record["has_interferer"] != [name in _WAVEFORM_LABELS, False]
            or record["has_downlink_interferer"] != [False, False]):
        raise ValueError("B2 primary event has the wrong label or injection stage")
    if name not in _WAVEFORM_LABELS:
        return
    if event["power_reference"] != "total_planned_uplink":
        raise ValueError("B2 uplink event has the wrong power reference")
    ci_range = (5, 30) if name == "carrier_under_carrier" else ((5, 35) if name in ("cw", "swept_cw") else (-100, 100))
    ci = _real(event["c_over_i_db"], "event C/I", minimum=ci_range[0], maximum=ci_range[1])
    if name == "cw":
        _real(event["f0"], "CW frequency", minimum=-0.48 * bandwidth, maximum=0.48 * bandwidth)
        _real(event["drift_hz_per_s"], "CW drift", minimum=-5e4, maximum=5e4)
    elif name == "swept_cw":
        width = event["f_hi"] - event["f_lo"]
        _real(width, "sweep width", minimum=1e6, maximum=0.9 * bandwidth)
        _real(event["period"], "sweep period", minimum=0.1, maximum=1.28)
        if event["shape"] not in ("triangle", "sawtooth"):
            raise ValueError("unsupported B2 sweep shape")
    elif name == "unauthorized":
        offset = _real(event["psd_offset_db"], "unauthorized PSD offset", minimum=-10, maximum=3)
        if not np.isclose(event["c_over_i_psd_db"], -offset, rtol=0, atol=1e-12):
            raise ValueError("unauthorized PSD convention differs from its C/I")
        carrier = _stored_carrier({"f0": event["f0"], "symbol_rate": event["symbol_rate"],
                                   "alpha": event["alpha"], "mod": event["mod"],
                                   "power": 10 ** (-ci / 10)}, bandwidth)
        expected_edges = [carrier.f0 - carrier.occupied_bw / 2, carrier.f0 + carrier.occupied_bw / 2]
        mean_psd = sum(c.power for c in plans[0]) / sum(c.symbol_rate for c in plans[0])
        expected_power = mean_psd * carrier.symbol_rate * 10 ** (offset / 10)
        if (not np.isclose(carrier.power, expected_power, rtol=1e-12, atol=0)
                or not np.allclose([event["f_lo"], event["f_hi"]], expected_edges, rtol=0, atol=1e-6)):
            raise ValueError("unauthorized carrier power or occupied band differs from its PSD convention")
        if any(event["f_hi"] > c.f0 - c.occupied_bw / 2 and event["f_lo"] < c.f0 + c.occupied_bw / 2 for c in plans[0]):
            raise ValueError("unauthorized event is not in an operator-plan gap")
    else:
        carrier = _stored_carrier(event["carrier"], bandwidth)
        if not np.isclose(carrier.power, 10 ** (-ci / 10), rtol=1e-12, atol=0):
            raise ValueError("B2 modulated event has inconsistent power and C/I")
        edges = [carrier.f0 - carrier.occupied_bw / 2, carrier.f0 + carrier.occupied_bw / 2]
        if not np.allclose([event["f_lo"], event["f_hi"]], edges, rtol=0, atol=1e-6):
            raise ValueError("B2 modulated event occupied band is inconsistent")
        if name == "carrier_under_carrier":
            index = event["victim_index"]
            if type(index) is not int or not 0 <= index < len(plans[0]) or not active[0][index] or event["victim_active"] is not True:
                raise ValueError("under-carrier event has no active planned victim")
            victim = plans[0][index]
            if (event["victim"] != record["plans"][0][index]
                    or edges[0] < victim.f0 - victim.occupied_bw / 2 - 1e-6
                    or edges[1] > victim.f0 + victim.occupied_bw / 2 + 1e-6):
                raise ValueError("under-carrier event is not contained in its active victim")
            if not np.isclose(event["victim_c_over_i_db"], ci + 10 * np.log10(victim.power), rtol=0, atol=1e-10):
                raise ValueError("under-carrier victim power reference is inconsistent")
        else:
            overlap = _real(event["overlap_fraction"], "ASI overlap", minimum=0.2, maximum=0.8)
            actual_overlap = overlap_fraction(edges[0], edges[1], plans[0])
            ci_psd = _real(event["c_over_i_psd_db"], "ASI PSD C/I")
            mean_psd = sum(c.power for c in plans[0]) / sum(c.symbol_rate for c in plans[0])
            expected_power = mean_psd * carrier.symbol_rate * 10 ** (-ci_psd / 10)
            if (not np.isclose(overlap, actual_overlap, rtol=0, atol=1e-10)
                    or not np.isclose(carrier.power, expected_power, rtol=1e-12, atol=0)):
                raise ValueError("ASI placement or power differs from its PSD convention")
            geometry = event["geometry"]
            expected_ci = geometry["max_gain_dbi"] - geometry["gain_toward_victim_dbi"] - geometry["delta_eirp_density_db"]
            if not np.isclose(ci_psd, expected_ci, rtol=0, atol=1e-10):
                raise ValueError("ASI geometry and PSD power reference disagree")


def _record(record, config, role, group, index, consistency, calibration_metadata):
    name = LABELS[index]
    if (record["protocol"] != BASE_PROTOCOL or record["parent_protocol"] != PROTOCOL
            or record["label"] != name or record["role"] != role or record["scenario_id"] != group
            or type(record["plan_consistency"]) is not int or record["plan_consistency"] != consistency
            or record["receiver_calibration_applied"] is not True
            or record["receiver_calibration"] != calibration_metadata):
        raise ValueError("B2 metadata does not match the calibrated sample and role")
    scene = record["config"]
    if (scene["uplink_xpd_db"] != (10 if name == "cross_pol" else config.nominal_xpd_db)
            or scene["downlink_xpd_db"] != config.downlink_xpd_db
            or scene["satellite_linewidth_hz"] != config.satellite_linewidth_hz
            or scene["receiver_linewidth_hz"] != config.receiver_linewidth_hz
            or scene["uplink_phase_rad"] != 0 or scene["downlink_phase_rad"] != 0):
        raise ValueError("B2 physical configuration differs from the frozen scene")
    response = scene["receiver_response"]
    matrix = np.asarray(response["real"]) + 1j * np.asarray(response["imag"])
    if matrix.shape != (2, 2) or not np.allclose(matrix, receiver_response(config), rtol=1e-12, atol=1e-12):
        raise ValueError("B2 instrument response differs from the request")
    nominal = record["nominal_ibo_db"]
    if not isinstance(nominal, list) or len(nominal) != 2:
        raise ValueError("B2 nominal back-off must describe both payload paths")
    for pol, key in enumerate(("co", "cross")):
        path = scene[key]
        _real(nominal[pol], "nominal back-off", minimum=9, maximum=13)
        if (path["seed"] != 2 * group + pol or path["bandwidth"] != config.bandwidth
                or path["n_snap"] != config.n_snap or path["snap_interval"] != config.snap_interval
                or path["linear"] is not False or path["filter_model"] != "etsi" or path["amplifier"] != "dvbs2_nl"):
            raise ValueError("B2 path seeds, sampling or payload differ from the request")
        for key_cn in ("cn_up_db", "cn_dn_db"):
            _real(path[key_cn], key_cn, minimum=15, maximum=30)
        if pol == 0 and name == "overdrive":
            _real(path["ibo_db"], "overdrive back-off", minimum=1, maximum=4)
        elif path["ibo_db"] != nominal[pol]:
            raise ValueError("B2 event changed a nominal payload setting")
    if not isinstance(record["paths"], list) or len(record["paths"]) != 2:
        raise ValueError("B2 realized payload statistics must describe both paths")
    for statistics in record["paths"]:
        if type(statistics["zero_drive"]) is not bool:
            raise ValueError("B2 zero-drive state must be a boolean")
        for name_stat in ("actual_ibo_db", "obo_db"):
            if statistics[name_stat] is not None:
                _real(statistics[name_stat], name_stat)
        for name_stat in ("omux_output_power", "receiver_noise_psd"):
            _real(statistics[name_stat], name_stat, minimum=0)
    plans = [[_stored_carrier(item, config.bandwidth) for item in plan] for plan in record["plans"]]
    if (len(plans) != 2 or any(not plan for plan in plans)
            or any(not np.isclose(sum(c.power for c in plan), 1, rtol=1e-6, atol=1e-8) for plan in plans)):
        raise ValueError("B2 operator plans must contain two unit nominal loads")
    active = _activity(record, plans, consistency)
    _event(record, name, plans, active, config.bandwidth)
    source = record["operator_plan_source"]
    rejected = source["co_rejected_plan_draws"]
    if (source["co_initial_seed"] != 2 * group or source["cross_seed"] != 2 * group + 1
            or type(rejected) is not int or not 0 <= rejected < 64
            or source["co_retry_rng_entropy"] != ([group, 1810, rejected] if rejected else None)
            or not isinstance(source["conditioning"], str) or not source["conditioning"]):
        raise ValueError("B2 operator-plan conditioning provenance is inconsistent")
    common_config = deepcopy(scene)
    common_config["co"]["ibo_db"] = nominal[0]
    common_config["uplink_xpd_db"] = config.nominal_xpd_db
    common = {key: record[key] for key in ("plans", "active_carriers", "active_planned_power", "nominal_ibo_db",
                                           "operator_plan_source", "dropped_carrier", "missing_carrier_convention")}
    return {**common, "config": common_config}, np.stack([plan_mask_db(plan) for plan in plans]).astype(np.float16)


def _read_part(part, metadata, config, role, groups, calibration_metadata):
    with np.load(part, allow_pickle=False) as archive:
        if set(archive.files) != set(ARRAY_KEYS):
            raise ValueError("unexpected B2 array keys")
        data = {key: archive[key] for key in ARRAY_KEYS}
    records = [_strict_json(line) for line in metadata.read_text().splitlines()]
    n = len(groups) * len(LABELS)
    if (data["spec"].shape != (n, 2, 128, 512) or data["mask"].shape != (n, 2, 512)
            or data["spec"].dtype != np.float16 or data["mask"].dtype != np.float16
            or any(data[key].shape != (n,) or data[key].dtype.kind not in "iu" for key in ("label", "seed", "plan_consistency"))
            or not np.isfinite(data["spec"]).all() or not np.isfinite(data["mask"]).all()
            or not np.isin(data["plan_consistency"], [0, 1]).all() or len(records) != n):
        raise ValueError("invalid B2 dimensions, dtypes, values or metadata count")
    pairs = list(zip(data["seed"].tolist(), data["label"].tolist()))
    if len(set(pairs)) != n or set(pairs) != {(seed, label) for seed in groups for label in range(len(LABELS))}:
        raise ValueError("B2 scenario-label pairs differ from the requested known groups")
    paired = {}
    for seed, label, consistency, mask, record in zip(data["seed"], data["label"], data["plan_consistency"], data["mask"], records):
        common, expected_mask = _record(record, config, role, int(seed), int(label), int(consistency), calibration_metadata)
        if not np.array_equal(mask, expected_mask):
            raise ValueError("B2 masks differ from full operator plans")
        if int(seed) in paired and paired[int(seed)] != common:
            raise ValueError("paired B2 variants differ beyond their named primary event")
        paired[int(seed)] = common
    return {**data, "meta": records}


def _verify_part(root, request, role, index, descriptor, config, calibration_metadata):
    part, metadata, descriptor_path = _paths(root, role, index)
    groups = _groups(request, role, index)
    if (descriptor.get("part") != part.name or descriptor.get("meta") != metadata.name
            or descriptor.get("role") != role or descriptor.get("scenario_seeds") != groups
            or descriptor.get("n_samples") != len(groups) * len(LABELS)
            or descriptor.get("request_fingerprint") != _fingerprint(request)):
        raise ValueError("incompatible B2 shard descriptor")
    if descriptor_path.exists() and _strict_json(descriptor_path.read_text()) != descriptor:
        raise ValueError("B2 shard descriptor differs from manifest")
    for path in (part, metadata):
        if not path.is_file() or descriptor.get("sha256", {}).get(path.name) != _file_hash(path):
            raise ValueError(f"missing or modified B2 artifact: {path}")
    return _read_part(part, metadata, config, role, groups, calibration_metadata)


def generate_b2_dataset(out_dir, config: B2Config | None = None, *, roles=BASE_ROLES,
                        limit_groups=None, groups_per_shard=GROUPS_PER_SHARD) -> None:
    """Generate known physical observations; all eight variants stay together."""
    config = B2Config() if config is None else config
    if not isinstance(config, B2Config):
        raise ValueError("config must be a B2Config")
    request = _request(config, roles, limit_groups, groups_per_shard)
    request_id = _fingerprint(request)
    root = Path(out_dir)
    request_path = root / "request.json"
    if request_path.exists():
        if _strict_json(request_path.read_text()) != request:
            raise ValueError("B2 generation request changed; use a fresh output directory")
    elif root.exists() and any(root.iterdir()):
        raise ValueError("unverified B2 output directory; use a fresh directory")
    else:
        calibration = _fit_calibration(config, request_id)
        root.mkdir(parents=True, exist_ok=True)
        _atomic_json(request_path, request)
        _save_calibration(root, calibration)
    if (root / "manifest.json").exists():
        manifest = read_b2_manifest(root)
        print(f"reusing verified B2 base dataset ({sum(info['n_samples'] for info in manifest['roles'].values())} samples)", flush=True)
        return
    if not (root / "calibration.json").exists():
        if (root / "receiver_calibration.npz").exists():
            raise ValueError("unverified partial B2 calibration; use a fresh output directory")
        _save_calibration(root, _fit_calibration(config, request_id))
    calibration, calibration_artifact = _calibration(root, request_id)
    role_info = {}
    for role in request["roles"]:
        (root / role).mkdir(exist_ok=True)
        _names(root, request, role, complete=False)
        descriptors = []
        for index in range(_n_shards(request, role)):
            part, metadata, descriptor_path = _paths(root, role, index)
            if descriptor_path.exists():
                descriptor = _strict_json(descriptor_path.read_text())
                _verify_part(root, request, role, index, descriptor, config, calibration.to_dict())
            else:
                if part.exists() or metadata.exists():
                    raise ValueError("unverified partial B2 shard; use a fresh output directory")
                arrays, records = {key: [] for key in ARRAY_KEYS}, []
                for group in _groups(request, role, index):
                    for label, name in enumerate(LABELS):
                        result = sample_scene(name, group, config, calibration=calibration)
                        arrays["spec"].append(result.spec_db.astype(np.float16))
                        arrays["mask"].append(result.mask_db.astype(np.float16))
                        arrays["label"].append(label)
                        arrays["seed"].append(group)
                        arrays["plan_consistency"].append(result.meta["plan_consistency"])
                        records.append(result.meta)
                temporary_part, temporary_meta = part.with_suffix(".tmp.npz"), metadata.with_suffix(".jsonl.tmp")
                np.savez(temporary_part, spec=np.stack(arrays["spec"]), mask=np.stack(arrays["mask"]),
                         label=np.asarray(arrays["label"], np.int8), seed=np.asarray(arrays["seed"], np.int64),
                         plan_consistency=np.asarray(arrays["plan_consistency"], np.int8))
                temporary_meta.write_text("".join(json.dumps(record, allow_nan=False) + "\n" for record in records))
                _read_part(temporary_part, temporary_meta, config, role, _groups(request, role, index), calibration.to_dict())
                temporary_part.replace(part)
                temporary_meta.replace(metadata)
                descriptor = {"part": part.name, "meta": metadata.name, "role": role,
                              "scenario_seeds": _groups(request, role, index), "n_samples": len(records),
                              "request_fingerprint": request_id,
                              "sha256": {path.name: _file_hash(path) for path in (part, metadata)}}
                _atomic_json(descriptor_path, descriptor)
            descriptors.append(descriptor)
        count = len(_groups(request, role))
        role_info[role] = {"scenario_seeds": _groups(request, role), "n_scenarios": count,
                           "n_samples": count * len(LABELS), "per_label": {name: count for name in LABELS},
                           "shards": descriptors}
        print(f"{role}: {count * len(LABELS)} calibrated B2 base samples", flush=True)
    manifest = {"artifact_version": 1, "protocol": BASE_PROTOCOL, "parent_protocol": PROTOCOL,
                "artifact_stage": ARTIFACT_STAGE, "benchmark_complete": False, "labels": list(LABELS),
                "config": config.to_dict(), "request": request, "request_fingerprint": request_id,
                "commit": _commit(), "calibration": calibration.to_dict(),
                "calibration_artifact": calibration_artifact, "roles": role_info}
    _atomic_json(root / "manifest.json", manifest)
    read_b2_manifest(root)


def _header(root):
    """Validate small descriptors only, allowing bounded-memory shard iteration."""
    manifest = _strict_json((root / "manifest.json").read_text())
    request = manifest["request"]
    config = B2Config(**request["config"])
    roles, groups, _ = _selection(request["roles"], request["limit_groups"], request["groups_per_shard"])
    source_hashes = request["source_sha256"]
    if (not isinstance(source_hashes, dict) or not source_hashes
            or any(not isinstance(name, str) or not isinstance(digest, str) or len(digest) != 64
                   or any(char not in "0123456789abcdef" for char in digest)
                   for name, digest in source_hashes.items())):
        raise ValueError("B2 request must retain generator source hashes")
    if (request["protocol"] != BASE_PROTOCOL or request["parent_protocol"] != PROTOCOL
            or request["artifact_stage"] != ARTIFACT_STAGE or request["benchmark_complete"] is not False
            or request["contract"] != protocol_contract() or request["scenario_groups"] != groups
            or request["config"] != config.to_dict()
            or _strict_json((root / "request.json").read_text()) != request
            or manifest["artifact_version"] != 1 or manifest["protocol"] != BASE_PROTOCOL
            or manifest["parent_protocol"] != PROTOCOL or manifest["artifact_stage"] != ARTIFACT_STAGE
            or manifest["benchmark_complete"] is not False or manifest["labels"] != list(LABELS)
            or manifest["config"] != config.to_dict() or manifest["request_fingerprint"] != _fingerprint(request)
            or set(manifest["roles"]) != set(roles)):
        raise ValueError("inconsistent B2 manifest/request")
    calibration, descriptor = _calibration(root, _fingerprint(request))
    if (descriptor != manifest["calibration_artifact"] or calibration.to_dict() != manifest["calibration"]
            or calibration.n_pilots != config.calibration_samples):
        raise ValueError("B2 manifest differs from the independent calibration artifact")
    for role in roles:
        info, seeds = manifest["roles"][role], groups[role]
        if (info["scenario_seeds"] != seeds or info["n_scenarios"] != len(seeds)
                or info["n_samples"] != len(seeds) * len(LABELS)
                or info["per_label"] != {name: len(seeds) for name in LABELS}
                or len(info["shards"]) != _n_shards(request, role)):
            raise ValueError("B2 role counts or scenario groups differ from the request")
        _names(root, request, role, complete=True)
    # A directory from an unselected role must not accidentally become data.
    if any((root / role).exists() for role in BASE_ROLES if role not in roles) or (root / "test-matched").exists():
        raise ValueError("B2 output contains an unrequested or reserved role")
    return manifest, config


def read_b2_manifest(path) -> dict:
    """Verify every shard and calibration while keeping one shard in memory."""
    root = Path(path)
    try:
        manifest, config = _header(root)
        for role, info in manifest["roles"].items():
            for index, descriptor in enumerate(info["shards"]):
                _verify_part(root, manifest["request"], role, index, descriptor, config, manifest["calibration"])
        return manifest
    except _READ_ERRORS as error:
        raise ValueError(f"invalid B2 base dataset {root}: {error}") from error


def iter_b2_shards(root, role: str):
    """Yield verified shards lazily; other roles' arrays are not loaded.

    Use read_b2_manifest when all roles must be fully verified up front. Each
    yielded shard checks its descriptor, checksums, arrays and metadata.
    """
    root = Path(root)
    try:
        if not isinstance(role, str) or role not in BASE_ROLES:
            raise ValueError(f"role must be one of {BASE_ROLES}")
        manifest, config = _header(root)
        if role not in manifest["roles"]:
            raise ValueError(f"role {role!r} was not generated")
        for index, descriptor in enumerate(manifest["roles"][role]["shards"]):
            yield _verify_part(root, manifest["request"], role, index, descriptor, config, manifest["calibration"])
    except _READ_ERRORS as error:
        raise ValueError(f"invalid B2 base dataset {root}: {error}") from error


def load_b2_split(root, role: str) -> dict:
    """Load one role into memory; prefer iter_b2_shards for full-scale data."""
    parts = list(iter_b2_shards(root, role))
    return {**{key: np.concatenate([part[key] for part in parts]) for key in ARRAY_KEYS},
            "meta": [record for part in parts for record in part["meta"]]}


def b2_fingerprint(path) -> str:
    """Content identity after complete, bounded-memory artifact verification."""
    return _fingerprint(read_b2_manifest(path))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", required=True)
    parser.add_argument("--config", help="JSON physical/instrument settings")
    parser.add_argument("--roles", nargs="+", choices=BASE_ROLES, default=BASE_ROLES)
    parser.add_argument("--limit-groups", type=int, help="pilot prefix per selected role; default full frozen counts")
    parser.add_argument("--groups-per-shard", type=int, default=GROUPS_PER_SHARD)
    args = parser.parse_args(argv)
    try:
        config = B2Config.from_file(args.config) if args.config else B2Config()
        generate_b2_dataset(args.out, config, roles=args.roles, limit_groups=args.limit_groups,
                            groups_per_shard=args.groups_per_shard)
    except (ValueError, OSError) as error:
        parser.exit(2, f"error: {error}\n")


if __name__ == "__main__":
    main()

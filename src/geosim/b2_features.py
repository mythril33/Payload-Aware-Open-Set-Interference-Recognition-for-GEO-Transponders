"""Verified B2 observations with decision-directed receiver residual spectra.

    python -m geosim.b2_features --out data/b2-features-pilot --limit-groups 1

This stage re-simulates calibrated monitor IQ, passes only that observation and
declared co-polarization carrier descriptors to the receiver, and stores the
residual PSD. Neither hidden symbols nor raw IQ are persisted as model inputs.
The final unknown/CID/matched-test benchmark is still incomplete.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import asdict, replace
import json
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import scipy

from . import FS_MON
from . import b2_dataset as base
from .b2_protocol import (BASE_PROTOCOL, BASE_ROLES, LABELS, PROTOCOL as PARENT_PROTOCOL,
                          B2Config, protocol_contract, scenario_ids)
from .b2_scenarios import sample_scene
from .dataset import _atomic_json, _commit, _file_hash, _fingerprint, _generator_provenance
from .event_dataset import _strict_json
from .polarization import ReceiverCalibration
from .sensor import SNAP_MON, spectrogram_db

if TYPE_CHECKING:
    from .observed_receiver import CancellationConfig

PROTOCOL = "B2-features/1"
FEATURE_PROTOCOL = PROTOCOL
ARTIFACT_STAGE = "observed_receiver_features"
GROUPS_PER_SHARD = 4
ARRAY_KEYS = (*base.ARRAY_KEYS, "residual")
RECEIVER_FIELDS = ("f0", "symbol_rate", "alpha", "mod", "code_rate")
RECEIVER_ALGORITHM = "observed-dd-rrc-fir/1"
_READ_ERRORS = base._READ_ERRORS


def _receiver():
    # Lazy import keeps artifact metadata APIs independent of receiver startup.
    from . import observed_receiver as cancellation
    return cancellation


def _selection(roles, limit_groups, groups_per_shard):
    roles, groups, size = base._selection(roles, None, groups_per_shard)
    if isinstance(limit_groups, dict):
        if set(limit_groups) != set(roles):
            raise ValueError("per-role limits must name exactly the selected roles")
        limits = {role: base._positive_int(limit_groups[role], f"{role} limit") for role in roles}
        groups = {role: scenario_ids(role, limits[role]) for role in roles}
    elif limit_groups is None:
        limits = None
    else:
        limits = base._positive_int(limit_groups, "limit_groups")
        groups = {role: scenario_ids(role, limits) for role in roles}
    return roles, groups, size, limits


def _cancellation_contract(config):
    receiver = _receiver()
    if config is None:
        config = receiver.CancellationConfig()
    if not isinstance(config, receiver.CancellationConfig):
        raise ValueError("cancellation_config must be a CancellationConfig")
    if receiver.ALGORITHM != RECEIVER_ALGORITHM:
        raise ValueError("receiver algorithm changed; use a separately versioned feature stage")
    # A plain, fully resolved JSON config is bound to every generated residual.
    settings = config.to_dict() if hasattr(config, "to_dict") else asdict(config)
    settings = _strict_json(json.dumps(settings, allow_nan=False))
    return config, {"algorithm": RECEIVER_ALGORITHM, "config": settings,
                    "receiver_fields": list(RECEIVER_FIELDS), "sample_rate_hz": FS_MON,
                    "observation": "calibrated_co_polarization_monitor_iq",
                    "residual_units": "dB(power/Hz); same monitor Welch estimator as spec"}


def _request(config, cancellation_config, roles, limit_groups, groups_per_shard):
    roles, groups, size, limits = _selection(roles, limit_groups, groups_per_shard)
    cancellation_config, contract = _cancellation_contract(cancellation_config)
    return cancellation_config, {
        "protocol": PROTOCOL, "parent_protocol": PARENT_PROTOCOL, "artifact_stage": ARTIFACT_STAGE,
        "benchmark_complete": False, "contract": protocol_contract(), "config": config.to_dict(),
        "cancellation": contract, "roles": roles, "scenario_groups": groups, "limit_groups": limits,
        "groups_per_shard": size, "source_sha256": _generator_provenance(),
        "numpy_version": np.__version__, "scipy_version": scipy.__version__}


def _fit_calibration(config, request_id):
    # Reuse exactly the independent [calibration_seed, 18001] pilot experiment,
    # then give its verified estimate this feature request's own provenance.
    return replace(base._fit_calibration(config, request_id),
                   provenance=f"{PROTOCOL}:{request_id}:independent_pilots")


def _calibration(root, request_id):
    descriptor = _strict_json((root / "calibration.json").read_text())
    path = root / "receiver_calibration.npz"
    if descriptor.get("file") != path.name or descriptor.get("sha256") != _file_hash(path):
        raise ValueError("missing or modified feature receiver calibration")
    calibration = ReceiverCalibration.load(path)
    if (calibration.to_dict() != descriptor.get("metadata")
            or calibration.provenance != f"{PROTOCOL}:{request_id}:independent_pilots"):
        raise ValueError("feature receiver calibration is not bound to this independent pilot request")
    return calibration, descriptor


def _declared_carriers(plan):
    """Drop simulator power and all other truth before constructing the receiver API."""
    receiver = _receiver()
    return [receiver.ReceiverCarrier(**{name: item.get(name) for name in RECEIVER_FIELDS}) for item in plan]


def _feature_record(record, contract):
    if record["protocol"] != PROTOCOL or record["parent_protocol"] != PARENT_PROTOCOL:
        raise ValueError("feature metadata has an incompatible protocol")
    feature = record["cancellation"]
    expected = [{name: item.get(name) for name in RECEIVER_FIELDS} for item in record["plans"][0]]
    if (feature["algorithm"] != contract["algorithm"] or feature["config"] != contract["config"]
            or feature["receiver_fields"] != list(RECEIVER_FIELDS)
            or feature["receiver_carriers"] != expected):
        raise ValueError("receiver features differ from their declared operator information or configuration")
    diagnostics = feature["diagnostics"]
    if (not isinstance(diagnostics, dict) or diagnostics.get("algorithm") != contract["algorithm"]
            or diagnostics.get("config") != contract["config"]
            or diagnostics.get("input_shape") != [128, SNAP_MON]
            or diagnostics.get("n_carriers") != len(expected)):
        raise ValueError("receiver diagnostics differ from the observed feature contract")
    # Detailed lock diagnostics are historical receiver output, never replayed
    # with a newer implementation and never used as classifier inputs.
    _strict_json(json.dumps(diagnostics, allow_nan=False))


def _read_part(part, metadata, config, role, groups, calibration_metadata, contract):
    with np.load(part, allow_pickle=False) as archive:
        if set(archive.files) != set(ARRAY_KEYS):
            raise ValueError("unexpected feature array keys")
        data = {key: archive[key] for key in ARRAY_KEYS}
    records = [_strict_json(line) for line in metadata.read_text().splitlines()]
    n = len(groups) * len(LABELS)
    if (data["spec"].shape != (n, 2, 128, 512) or data["mask"].shape != (n, 2, 512)
            or data["residual"].shape != (n, 128, 512)
            or any(data[key].dtype != np.float16 or not np.isfinite(data[key]).all()
                   for key in ("spec", "mask", "residual"))
            or any(data[key].shape != (n,) or data[key].dtype.kind not in "iu"
                   for key in ("label", "seed", "plan_consistency"))
            or not np.isin(data["plan_consistency"], [0, 1]).all() or len(records) != n):
        raise ValueError("invalid feature dimensions, dtypes, values or metadata count")
    pairs = list(zip(data["seed"].tolist(), data["label"].tolist()))
    if len(set(pairs)) != n or set(pairs) != {(group, label) for group in groups for label in range(len(LABELS))}:
        raise ValueError("feature scenario-label pairs differ from the requested known groups")
    paired = {}
    for seed, label, consistency, mask, record in zip(
            data["seed"], data["label"], data["plan_consistency"], data["mask"], records):
        _feature_record(record, contract)
        # The base scene contract is identical. Translate only its artifact
        # protocol in a detached copy, retaining feature calibration identity.
        translated = dict(record, protocol=BASE_PROTOCOL)
        translated.pop("cancellation")  # Already validated above; not a base-stage field.
        common, expected_mask = base._record(translated, config, role, int(seed), int(label),
                                             int(consistency), calibration_metadata)
        if not np.array_equal(mask, expected_mask):
            raise ValueError("feature masks differ from full operator plans")
        if int(seed) in paired and paired[int(seed)] != common:
            raise ValueError("paired feature scenes differ beyond the named primary event")
        paired[int(seed)] = common
    return {**data, "meta": records}


def _verify_part(root, request, role, index, descriptor, config, calibration_metadata):
    part, metadata, descriptor_path = base._paths(root, role, index)
    groups = base._groups(request, role, index)
    if (descriptor.get("part") != part.name or descriptor.get("meta") != metadata.name
            or descriptor.get("role") != role or descriptor.get("scenario_seeds") != groups
            or descriptor.get("n_samples") != len(groups) * len(LABELS)
            or descriptor.get("request_fingerprint") != _fingerprint(request)):
        raise ValueError("incompatible feature shard descriptor")
    if descriptor_path.exists() and _strict_json(descriptor_path.read_text()) != descriptor:
        raise ValueError("feature shard descriptor differs from manifest")
    for path in (part, metadata):
        if not path.is_file() or descriptor.get("sha256", {}).get(path.name) != _file_hash(path):
            raise ValueError(f"missing or modified feature artifact: {path}")
    return _read_part(part, metadata, config, role, groups, calibration_metadata, request["cancellation"])


def generate_b2_features(out_dir, config: B2Config | None = None, *, cancellation_config=None,
                         roles=BASE_ROLES, limit_groups=None, groups_per_shard=GROUPS_PER_SHARD):
    """Generate observed residual PSDs with only known labels and no persisted IQ."""
    config = B2Config() if config is None else config
    if not isinstance(config, B2Config):
        raise ValueError("config must be a B2Config")
    cancellation_config, request = _request(config, cancellation_config, roles, limit_groups, groups_per_shard)
    request_id = _fingerprint(request)
    root, receiver = Path(out_dir), _receiver()
    request_path = root / "request.json"
    if request_path.exists():
        if _strict_json(request_path.read_text()) != request:
            raise ValueError("feature generation request changed; use a fresh output directory")
    elif root.exists() and any(root.iterdir()):
        raise ValueError("unverified feature output directory; use a fresh directory")
    else:
        calibration = _fit_calibration(config, request_id)
        root.mkdir(parents=True, exist_ok=True)
        _atomic_json(request_path, request)
        base._save_calibration(root, calibration)
    if (root / "manifest.json").exists():
        manifest = read_feature_manifest(root)
        count = sum(info["n_samples"] for info in manifest["roles"].values())
        print(f"reusing verified B2 feature dataset ({count} samples)", flush=True)
        return
    if not (root / "calibration.json").exists():
        if (root / "receiver_calibration.npz").exists():
            raise ValueError("unverified partial feature calibration; use a fresh output directory")
        base._save_calibration(root, _fit_calibration(config, request_id))
    calibration, calibration_artifact = _calibration(root, request_id)
    role_info = {}
    for role in request["roles"]:
        (root / role).mkdir(exist_ok=True)
        base._names(root, request, role, complete=False)
        descriptors = []
        for index in range(base._n_shards(request, role)):
            part, metadata, descriptor_path = base._paths(root, role, index)
            if descriptor_path.exists():
                descriptor = _strict_json(descriptor_path.read_text())
                _verify_part(root, request, role, index, descriptor, config, calibration.to_dict())
            else:
                if part.exists() or metadata.exists():
                    raise ValueError("unverified partial feature shard; use a fresh output directory")
                arrays, records = {key: [] for key in ARRAY_KEYS}, []
                for group in base._groups(request, role, index):
                    for label, name in enumerate(LABELS):
                        result = sample_scene(name, group, config, calibration=calibration, keep_iq=True)
                        iq = np.asarray(result.iq)
                        if (iq.shape != (2, config.n_snap, SNAP_MON) or iq.dtype.kind != "c"
                                or not np.isfinite(iq).all()):
                            raise ValueError("feature generation requires finite calibrated monitor IQ from both feeds")
                        declared = _declared_carriers(result.meta["plans"][0])
                        cancelled = receiver.cancel_observed(iq[0], declared, cancellation_config)
                        residual_iq = np.asarray(cancelled.residual_iq)
                        if (residual_iq.shape != iq[0].shape or residual_iq.dtype.kind != "c"
                                or not np.isfinite(residual_iq).all()):
                            raise ValueError("receiver must return finite complex residuals matching observed co IQ")
                        record = deepcopy(result.meta)
                        record["protocol"] = PROTOCOL
                        record["cancellation"] = {
                            "algorithm": request["cancellation"]["algorithm"],
                            "config": request["cancellation"]["config"],
                            "receiver_fields": list(RECEIVER_FIELDS),
                            "receiver_carriers": [asdict(carrier) for carrier in declared],
                            "diagnostics": deepcopy(cancelled.meta)}
                        arrays["spec"].append(result.spec_db.astype(np.float16))
                        arrays["mask"].append(result.mask_db.astype(np.float16))
                        arrays["residual"].append(spectrogram_db(residual_iq).astype(np.float16))
                        arrays["label"].append(label)
                        arrays["seed"].append(group)
                        arrays["plan_consistency"].append(record["plan_consistency"])
                        records.append(record)
                temporary_part, temporary_meta = part.with_suffix(".tmp.npz"), metadata.with_suffix(".jsonl.tmp")
                np.savez(temporary_part, spec=np.stack(arrays["spec"]), mask=np.stack(arrays["mask"]),
                         residual=np.stack(arrays["residual"]), label=np.asarray(arrays["label"], np.int8),
                         seed=np.asarray(arrays["seed"], np.int64),
                         plan_consistency=np.asarray(arrays["plan_consistency"], np.int8))
                temporary_meta.write_text("".join(json.dumps(record, allow_nan=False) + "\n" for record in records))
                _read_part(temporary_part, temporary_meta, config, role, base._groups(request, role, index),
                           calibration.to_dict(), request["cancellation"])
                temporary_part.replace(part)
                temporary_meta.replace(metadata)
                descriptor = {"part": part.name, "meta": metadata.name, "role": role,
                              "scenario_seeds": base._groups(request, role, index), "n_samples": len(records),
                              "request_fingerprint": request_id,
                              "sha256": {path.name: _file_hash(path) for path in (part, metadata)}}
                _atomic_json(descriptor_path, descriptor)
            descriptors.append(descriptor)
        count = len(base._groups(request, role))
        role_info[role] = {"scenario_seeds": base._groups(request, role), "n_scenarios": count,
                           "n_samples": count * len(LABELS), "per_label": {name: count for name in LABELS},
                           "shards": descriptors}
        print(f"{role}: {count * len(LABELS)} calibrated B2 feature samples", flush=True)
    manifest = {"artifact_version": 1, "protocol": PROTOCOL, "parent_protocol": PARENT_PROTOCOL,
                "artifact_stage": ARTIFACT_STAGE, "benchmark_complete": False, "labels": list(LABELS),
                "config": config.to_dict(), "cancellation": request["cancellation"],
                "request": request, "request_fingerprint": request_id, "commit": _commit(),
                "calibration": calibration.to_dict(), "calibration_artifact": calibration_artifact, "roles": role_info}
    _atomic_json(root / "manifest.json", manifest)
    read_feature_manifest(root)


def _header(root):
    """Validate request, small descriptors and calibration without loading arrays."""
    manifest = _strict_json((root / "manifest.json").read_text())
    request = manifest["request"]
    config = B2Config(**request["config"])
    roles, groups, _, limits = _selection(request["roles"], request["limit_groups"], request["groups_per_shard"])
    contract = request["cancellation"]
    if (contract["algorithm"] != RECEIVER_ALGORITHM or not isinstance(contract["config"], dict)
            or not contract["config"] or contract["receiver_fields"] != list(RECEIVER_FIELDS)
            or contract["sample_rate_hz"] != FS_MON
            or contract["observation"] != "calibrated_co_polarization_monitor_iq"
            or contract["residual_units"] != "dB(power/Hz); same monitor Welch estimator as spec"):
        raise ValueError("incompatible observed receiver contract")
    source_hashes = request["source_sha256"]
    if (not isinstance(source_hashes, dict) or not source_hashes
            or any(not isinstance(name, str) or not isinstance(digest, str) or len(digest) != 64
                   or any(char not in "0123456789abcdef" for char in digest)
                   for name, digest in source_hashes.items())):
        raise ValueError("feature request must retain generator source hashes")
    if (request["protocol"] != PROTOCOL or request["parent_protocol"] != PARENT_PROTOCOL
            or request["artifact_stage"] != ARTIFACT_STAGE or request["benchmark_complete"] is not False
            or request["contract"] != protocol_contract() or request["scenario_groups"] != groups
            or request["limit_groups"] != limits or request["config"] != config.to_dict()
            or _strict_json((root / "request.json").read_text()) != request
            or manifest["artifact_version"] != 1 or manifest["protocol"] != PROTOCOL
            or manifest["parent_protocol"] != PARENT_PROTOCOL or manifest["artifact_stage"] != ARTIFACT_STAGE
            or manifest["benchmark_complete"] is not False or manifest["labels"] != list(LABELS)
            or manifest["config"] != config.to_dict() or manifest["cancellation"] != contract
            or manifest["request_fingerprint"] != _fingerprint(request)
            or set(manifest["roles"]) != set(roles)):
        raise ValueError("inconsistent feature manifest/request")
    calibration, descriptor = _calibration(root, _fingerprint(request))
    if (descriptor != manifest["calibration_artifact"] or calibration.to_dict() != manifest["calibration"]
            or calibration.n_pilots != config.calibration_samples):
        raise ValueError("feature manifest differs from independent calibration artifact")
    for role in roles:
        info, seeds = manifest["roles"][role], groups[role]
        if (info["scenario_seeds"] != seeds or info["n_scenarios"] != len(seeds)
                or info["n_samples"] != len(seeds) * len(LABELS)
                or info["per_label"] != {name: len(seeds) for name in LABELS}
                or len(info["shards"]) != base._n_shards(request, role)):
            raise ValueError("feature role counts or scenario groups differ from the request")
        base._names(root, request, role, complete=True)
    if any(path.is_dir() and path.name not in roles for path in root.iterdir()):
        raise ValueError("feature output contains an unrequested or reserved role")
    return manifest, config


def read_feature_manifest(path) -> dict:
    """Verify all referenced shards with one shard resident at a time."""
    root = Path(path)
    try:
        manifest, config = _header(root)
        for role, info in manifest["roles"].items():
            for index, descriptor in enumerate(info["shards"]):
                _verify_part(root, manifest["request"], role, index, descriptor, config, manifest["calibration"])
        return manifest
    except _READ_ERRORS as error:
        raise ValueError(f"invalid B2 feature dataset {root}: {error}") from error


def iter_feature_shards(root, role: str, *, indices=None):
    """Yield verified shards in natural order or a requested unique index order."""
    root = Path(root)
    try:
        if not isinstance(role, str) or role not in BASE_ROLES:
            raise ValueError(f"role must be one of {BASE_ROLES}")
        manifest, config = _header(root)
        if role not in manifest["roles"]:
            raise ValueError(f"role {role!r} was not generated")
        descriptors = manifest["roles"][role]["shards"]
        if indices is None:
            selected = range(len(descriptors))
        else:
            if isinstance(indices, (list, tuple)) and any(isinstance(value, (bool, np.bool_)) for value in indices):
                raise ValueError("shard indices must be distinct in-range integers")
            raw = np.asarray(indices)
            if (raw.ndim != 1 or raw.dtype.kind not in "iu" or not len(raw)
                    or len(np.unique(raw)) != len(raw) or np.any(raw >= len(descriptors)) or np.any(raw < 0)):
                raise ValueError("shard indices must be distinct in-range integers")
            selected = raw.tolist()
        for index in selected:
            yield _verify_part(root, manifest["request"], role, index, descriptors[index], config, manifest["calibration"])
    except _READ_ERRORS as error:
        raise ValueError(f"invalid B2 feature dataset {root}: {error}") from error


def load_feature_split(root, role: str) -> dict:
    """Eager convenience for pilots; full-scale training should iterate shards."""
    parts = list(iter_feature_shards(root, role))
    return {**{key: np.concatenate([part[key] for part in parts]) for key in ARRAY_KEYS},
            "meta": [record for part in parts for record in part["meta"]]}


def feature_fingerprint(path) -> str:
    return _fingerprint(read_feature_manifest(path))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", required=True)
    parser.add_argument("--config", help="JSON physical/instrument settings")
    parser.add_argument("--cancellation-config", help="JSON observed receiver settings")
    parser.add_argument("--roles", nargs="+", choices=BASE_ROLES, default=BASE_ROLES)
    limits = parser.add_mutually_exclusive_group()
    limits.add_argument("--limit-groups", type=int, help="pilot prefix in each selected role")
    limits.add_argument("--role-limits", help="JSON file mapping every selected role to a pilot prefix count")
    parser.add_argument("--groups-per-shard", type=int, default=GROUPS_PER_SHARD)
    args = parser.parse_args(argv)
    try:
        config = B2Config.from_file(args.config) if args.config else B2Config()
        cancellation_config = _receiver().CancellationConfig.from_file(args.cancellation_config) if args.cancellation_config else None
        selected_limits = _strict_json(Path(args.role_limits).read_text()) if args.role_limits else args.limit_groups
        if args.role_limits and not isinstance(selected_limits, dict):
            raise ValueError("role-limits JSON must be an object")
        generate_b2_features(args.out, config, cancellation_config=cancellation_config, roles=args.roles,
                             limit_groups=selected_limits, groups_per_shard=args.groups_per_shard)
    except (ValueError, OSError) as error:
        parser.exit(2, f"error: {error}\n")


if __name__ == "__main__":
    main()

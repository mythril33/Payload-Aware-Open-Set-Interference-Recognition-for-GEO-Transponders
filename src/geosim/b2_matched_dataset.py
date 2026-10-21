"""K17c level-matched ASI versus unauthorized set, bound to a verified known artifact (P18 §7a).

    python -m geosim.b2_matched_dataset --out data/b2-match-pilot --known data/b2-feat-pilot \
        --config configs/b2_base.json --cancellation configs/cancellation.json --limit-groups 2

The B2-match/1 stage generates, for the frozen ``test-matched`` role only (groups
3 300 000-3 300 149), three paired variants per group: ``clean``, ``adjacent_satellite``
and ``unauthorized``. Within a group the two interference variants share the
physical scenario, operator plans, link settings, carrier/noise/phase streams,
missing-carrier state, receiver calibration, cancellation settings, symbol rate,
roll-off, modulation and one C/I_psd target drawn from U(4, 13) dB. They differ
only in frequency placement: the ASI overlaps the plan (20-80 %), the unauthorized
carrier sits in a free gap. This is a controlled intervention, not the natural
operating distribution; the matched block in every record says so. The set is
test-only: it never enters training, checkpoint selection, threshold calibration
or Mahalanobis fitting. ``label`` stores the known-class index (clean 0,
unauthorized 3, adjacent_satellite 6) so evaluation code can reuse the known
label order; ``matched_bin`` stores the frozen reporting bin (0: 4-7, 1: 7-10,
2: 10-13 dB).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import scipy

from .b2_dataset import (_READ_ERRORS, _activity, _cancellation_record, _file_hash, _fingerprint, _paths,
                         _positive_int, _residual, _stage, read_b2_manifest)
from .b2_protocol import (FIFTH_CHANNEL, LABELS, PROTOCOL, B2Config, protocol_contract, receiver_response, scenario_ids)
from .b2_scenarios import (MATCHED_BIN_NAMES, MATCHED_BINS, MATCHED_CI_RANGE, MATCHED_LABELS, MATCHED_PROTOCOL,
                           NATURAL_CI_PSD_RANGES, matched_bin, sample_matched_scene)
from .b2_test_dataset import _cancellation_of as _test_cancellation_of
from .b2_test_dataset import _save_calibration
from .cancellation import CancellationConfig
from .dataset import _atomic_json, _commit, _generator_provenance
from .event_dataset import _real, _stored_carrier, _strict_json
from .interferers import overlaps_plan
from .asi import overlap_fraction
from .plan import plan_mask_db
from .polarization import ReceiverCalibration

ROLE = "test-matched"
STAGE = "level_matched_asi_unauthorized"
ARRAY_KEYS = ("spec", "mask", "label", "seed", "plan_consistency", "matched_bin")
FEATURE_ARRAY_KEYS = ARRAY_KEYS + ("residual",)
GROUPS_PER_SHARD = 8
LABEL_INDEX = tuple(LABELS.index(name) for name in MATCHED_LABELS)


def _known_binding(known_root: Path, config: B2Config, cancellation):
    manifest = read_b2_manifest(known_root)
    known_protocol, _, known_cancellation, _ = _stage(manifest["request"])
    if manifest["request"]["config"] != config.to_dict():
        raise ValueError("the matched set must use the known artifact's physical configuration")
    if (known_cancellation is None) != (cancellation is None) or (
            cancellation is not None and known_cancellation.to_dict() != cancellation.to_dict()):
        raise ValueError("the matched set must use the known artifact's cancellation setting")
    return {"known_protocol": known_protocol, "known_data_fingerprint": _fingerprint(manifest),
            "known_request_fingerprint": manifest["request_fingerprint"],
            "known_roles": sorted(manifest["roles"]), "known_calibration": manifest["calibration"]}


def _request(config, limit_groups, groups_per_shard, cancellation, binding):
    groups_per_shard = _positive_int(groups_per_shard, "groups_per_shard", 100)
    if limit_groups is not None:
        limit_groups = _positive_int(limit_groups, "limit_groups")
    if cancellation is not None and not isinstance(cancellation, CancellationConfig):
        raise ValueError("cancellation must be a CancellationConfig or None")
    request = {"protocol": MATCHED_PROTOCOL, "parent_protocol": PROTOCOL, "artifact_stage": STAGE,
               "benchmark_complete": False, "contract": protocol_contract(), "config": config.to_dict(),
               "labels": list(MATCHED_LABELS), "label_index": list(LABEL_INDEX), "role": ROLE,
               "matched": {"c_over_i_psd_range_db": list(MATCHED_CI_RANGE), "bins_db": [list(b) for b in MATCHED_BINS],
                           "bin_names": list(MATCHED_BIN_NAMES), "natural_ranges_db": {k: list(v) for k, v in NATURAL_CI_PSD_RANGES.items()},
                           "shared": ["plans", "link", "streams", "phase", "activity", "calibration", "cancellation",
                                      "symbol_rate", "alpha", "mod", "target_c_over_i_psd_db", "requested_power"],
                           "differs": ["frequency placement: ASI overlaps the plan 20-80 %; unauthorized sits in a free gap"],
                           "rng_namespace": "[group, 1840]"},
               "scenario_groups": scenario_ids(ROLE, limit_groups), "limit_groups": limit_groups,
               "groups_per_shard": groups_per_shard, "known": binding, "source_sha256": _generator_provenance(),
               "numpy_version": np.__version__, "scipy_version": scipy.__version__}
    if cancellation is not None:
        request.update(cancellation=cancellation.to_dict(), fifth_channel=dict(FIFTH_CHANNEL))
    return request


def _cancellation_of(request):
    cancellation, keys = _test_cancellation_of(request)
    return cancellation, (ARRAY_KEYS if cancellation is None else FEATURE_ARRAY_KEYS)


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
            raise ValueError(f"unexpected or missing B2 matched artifacts: {pattern}")


def _calibration(root, request):
    descriptor = _strict_json((root / "calibration.json").read_text())
    path = root / "receiver_calibration.npz"
    if descriptor.get("file") != path.name or descriptor.get("sha256") != _file_hash(path):
        raise ValueError("missing or modified B2 matched receiver calibration")
    calibration = ReceiverCalibration.load(path)
    if calibration.to_dict() != descriptor.get("metadata") or calibration.to_dict() != request["known"]["known_calibration"]:
        raise ValueError("B2 matched calibration is not the known artifact's receiver calibration")
    return calibration, descriptor


def _matched_block(record, plans, bandwidth, active):
    """Validate the group-level matched intervention stored in every variant."""
    matched = record["matched"]
    ci = _real(matched["target_c_over_i_psd_db"], "matched C/I_psd", minimum=MATCHED_CI_RANGE[0], maximum=MATCHED_CI_RANGE[1])
    if matched["pair_id"] != f"{MATCHED_PROTOCOL}:{record['scenario_id']}" or matched["bin"] != matched_bin(ci) \
            or matched["bin_name"] != MATCHED_BIN_NAMES[matched["bin"]]:
        raise ValueError("matched pair identity or bin is inconsistent")
    rs, alpha = _real(matched["symbol_rate"], "symbol rate", minimum=1e5), _real(matched["alpha"], "roll-off", minimum=0.05, maximum=1)
    mean_psd = sum(c.power for c in plans[0]) / sum(c.symbol_rate for c in plans[0])
    if not np.isclose(matched["requested_power"], mean_psd * rs * 10 ** (-ci / 10), rtol=1e-12, atol=0):
        raise ValueError("matched requested power differs from the shared PSD convention")
    natural = {name: bool(lo <= ci <= hi) for name, (lo, hi) in NATURAL_CI_PSD_RANGES.items()}
    if matched["within_natural_range"] != natural:
        raise ValueError("matched natural-range flags are inconsistent")
    half = rs * (1 + alpha) / 2
    plan_overlap = overlap_fraction(matched["asi_f0"] - half, matched["asi_f0"] + half, plans[0])
    transmitted = [c for c, keep in zip(plans[0], active[0]) if keep]
    active_overlap = overlap_fraction(matched["asi_f0"] - half, matched["asi_f0"] + half, transmitted) if transmitted else 0.0
    if (not np.isclose(matched["asi_overlap_fraction_plan"], plan_overlap, rtol=0, atol=1e-10)
            or not np.isclose(matched["asi_overlap_fraction_active"], active_overlap, rtol=0, atol=1e-10)
            or matched["asi_overlaps_only_absent_carrier"] != (active_overlap == 0.0)):
        raise ValueError("matched ASI overlap with planned/transmitted carriers is inconsistent")
    return matched


def _event(record, name, plans, matched, bandwidth):
    event = record["event"]
    if name == "clean":
        if event["kind"] != "clean" or record["has_interferer"] != [False, False]:
            raise ValueError("matched clean variant must carry no event")
        return
    if (event["kind"] != name or event["injection_stage"] != "uplink" or event.get("matched") is not True
            or record["has_interferer"] != [True, False] or record["has_downlink_interferer"] != [False, False]
            or event["power_reference"] != "total_planned_uplink"):
        raise ValueError("matched event has the wrong kind, injection stage or power reference")
    if name == "adjacent_satellite":
        carrier = _stored_carrier(event["carrier"], bandwidth)
        f0 = matched["asi_f0"]
        if (event.get("geometry") is not None or event.get("level_source") != "matched_intervention"
                or not np.isclose(event["c_over_i_psd_db"], matched["target_c_over_i_psd_db"], rtol=0, atol=0)):
            raise ValueError("matched ASI must carry the imposed level and no drawn geometry")
        edges = [carrier.f0 - carrier.occupied_bw / 2, carrier.f0 + carrier.occupied_bw / 2]
        fraction = overlap_fraction(edges[0], edges[1], plans[0])
        if not np.isclose(event["overlap_fraction"], fraction, rtol=0, atol=1e-10) or not 0.2 - 1e-9 <= fraction <= 0.8 + 1e-9:
            raise ValueError("matched ASI placement does not overlap the plan within 20-80 %")
    else:
        carrier = _stored_carrier({"f0": event["f0"], "symbol_rate": event["symbol_rate"], "alpha": event["alpha"],
                                   "mod": event["mod"], "power": 10 ** (-event["c_over_i_db"] / 10)}, bandwidth)
        f0 = matched["unauthorized_f0"]
        if (not np.isclose(event["c_over_i_psd_db"], matched["target_c_over_i_psd_db"], rtol=0, atol=0)
                or not np.isclose(event["psd_offset_db"], -matched["target_c_over_i_psd_db"], rtol=0, atol=1e-12)
                or overlaps_plan(event["f_lo"], event["f_hi"], plans[0])):
            raise ValueError("matched unauthorized carrier must sit in a free gap at the shared level")
        lo, hi = matched["unauthorized_gap_hz"]
        need = carrier.symbol_rate * (1 + carrier.alpha) + 0.1 * carrier.symbol_rate
        if not lo + need / 2 - 1e-6 <= carrier.f0 <= hi - need / 2 + 1e-6:
            raise ValueError("matched unauthorized carrier violates the gap guard convention")
    edges = [carrier.f0 - carrier.occupied_bw / 2, carrier.f0 + carrier.occupied_bw / 2]
    if not np.allclose([event["f_lo"], event["f_hi"]], edges, rtol=0, atol=1e-6):
        raise ValueError("matched event occupied band differs from its carrier")
    if (carrier.f0 != f0 or carrier.symbol_rate != matched["symbol_rate"] or carrier.alpha != matched["alpha"]
            or carrier.mod != matched["mod"] or not np.isclose(carrier.power, matched["requested_power"], rtol=1e-12, atol=0)):
        raise ValueError("matched event carrier differs from the shared matched draw")


def _record(record, config, group, label_index, consistency, bin_value, calibration_metadata, cancellation):
    name = LABELS[label_index]
    if name not in MATCHED_LABELS:
        raise ValueError("matched records carry only clean, adjacent_satellite and unauthorized labels")
    if (record["protocol"] != MATCHED_PROTOCOL or record["parent_protocol"] != PROTOCOL
            or record["label"] != name or record["role"] != ROLE or record["scenario_id"] != group
            or record["test_only"] is not True
            or type(record["plan_consistency"]) is not int or record["plan_consistency"] != consistency
            or record["receiver_calibration_applied"] is not True
            or record["receiver_calibration"] != calibration_metadata):
        raise ValueError("B2 matched metadata does not match the label, group or calibration")
    scene = record["config"]
    if (scene["uplink_xpd_db"] != config.nominal_xpd_db or scene["downlink_xpd_db"] != config.downlink_xpd_db
            or scene["satellite_linewidth_hz"] != config.satellite_linewidth_hz
            or scene["receiver_linewidth_hz"] != config.receiver_linewidth_hz):
        raise ValueError("B2 matched scene changed a nominal physical setting")
    response = scene["receiver_response"]
    matrix = np.asarray(response["real"]) + 1j * np.asarray(response["imag"])
    if matrix.shape != (2, 2) or not np.allclose(matrix, receiver_response(config), rtol=1e-12, atol=1e-12):
        raise ValueError("B2 matched instrument response differs from the request")
    nominal = record["nominal_ibo_db"]
    for pol, key in enumerate(("co", "cross")):
        path = scene[key]
        _real(nominal[pol], "nominal back-off", minimum=9, maximum=13)
        if (path["seed"] != 2 * group + pol or path["bandwidth"] != config.bandwidth or path["ibo_db"] != nominal[pol]
                or path["n_snap"] != config.n_snap or path["snap_interval"] != config.snap_interval
                or path["linear"] is not False or path["filter_model"] != "etsi" or path["amplifier"] != "dvbs2_nl"):
            raise ValueError("B2 matched path differs from the shared nominal scene")
        for key_cn in ("cn_up_db", "cn_dn_db"):
            _real(path[key_cn], key_cn, minimum=15, maximum=30)
    plans = [[_stored_carrier(item, config.bandwidth) for item in plan] for plan in record["plans"]]
    if (len(plans) != 2 or any(not plan for plan in plans)
            or any(not np.isclose(sum(c.power for c in plan), 1, rtol=1e-6, atol=1e-8) for plan in plans)):
        raise ValueError("B2 matched operator plans must contain two unit nominal loads")
    active = _activity(record, plans, consistency)
    matched = _matched_block(record, plans, config.bandwidth, active)
    if int(bin_value) != matched["bin"]:
        raise ValueError("stored matched_bin differs from the metadata bin")
    _event(record, name, plans, matched, config.bandwidth)
    _cancellation_record(record, plans, cancellation)
    source = record["operator_plan_source"]
    if (source["co_initial_seed"] != 2 * group or source["cross_seed"] != 2 * group + 1
            or type(source["co_rejected_plan_draws"]) is not int or not 0 <= source["co_rejected_plan_draws"] < 64
            or type(source["n_matched_rate_rolloff_options"]) is not int or source["n_matched_rate_rolloff_options"] < 1):
        raise ValueError("B2 matched plan conditioning provenance is inconsistent")
    common = {key: record[key] for key in ("plans", "active_carriers", "active_planned_power", "nominal_ibo_db",
                                           "operator_plan_source", "dropped_carrier", "missing_carrier_convention",
                                           "config", "matched")}
    return common, np.stack([plan_mask_db(plan) for plan in plans]).astype(np.float16)


def _read_part(part, metadata, config, groups, calibration_metadata, cancellation, keys):
    with np.load(part, allow_pickle=False) as archive:
        if set(archive.files) != set(keys):
            raise ValueError("unexpected B2 matched array keys")
        data = {key: archive[key] for key in keys}
    records = [_strict_json(line) for line in metadata.read_text().splitlines()]
    n = len(groups) * len(MATCHED_LABELS)
    if (data["spec"].shape != (n, 2, 128, 512) or data["mask"].shape != (n, 2, 512)
            or data["spec"].dtype != np.float16 or data["mask"].dtype != np.float16
            or any(data[key].shape != (n,) or data[key].dtype.kind not in "iu" for key in ("label", "seed", "plan_consistency", "matched_bin"))
            or not np.isfinite(data["spec"]).all() or not np.isfinite(data["mask"]).all()
            or not np.isin(data["plan_consistency"], [0, 1]).all() or not np.isin(data["matched_bin"], [0, 1, 2]).all()
            or len(records) != n):
        raise ValueError("invalid B2 matched dimensions, dtypes, values or metadata count")
    if cancellation is not None and (data["residual"].shape != (n, 128, 512) or data["residual"].dtype != np.float16
                                     or not np.isfinite(data["residual"]).all()):
        raise ValueError("invalid B2 matched cancellation-residual array")
    pairs = list(zip(data["seed"].tolist(), data["label"].tolist()))
    if len(set(pairs)) != n or set(pairs) != {(seed, index) for seed in groups for index in LABEL_INDEX}:
        raise ValueError("B2 matched scenario-label pairs differ from the requested groups (duplicate or missing variant)")
    paired = {}
    for seed, index, consistency, bin_value, mask, record in zip(data["seed"], data["label"], data["plan_consistency"],
                                                                 data["matched_bin"], data["mask"], records):
        common, expected_mask = _record(record, config, int(seed), int(index), int(consistency), int(bin_value),
                                        calibration_metadata, cancellation)
        if not np.array_equal(mask, expected_mask):
            raise ValueError("B2 matched masks differ from full operator plans")
        if int(seed) in paired and paired[int(seed)] != common:
            raise ValueError("matched variants of one group differ beyond their event placement")
        paired[int(seed)] = common
    return {**data, "meta": records}


def _verify_part(root, request, index, descriptor, config, calibration_metadata):
    part, metadata, descriptor_path = _paths(root, ROLE, index)
    groups = _groups(request, index)
    cancellation, keys = _cancellation_of(request)
    if (descriptor.get("part") != part.name or descriptor.get("meta") != metadata.name or descriptor.get("role") != ROLE
            or descriptor.get("scenario_seeds") != groups or descriptor.get("n_samples") != len(groups) * len(MATCHED_LABELS)
            or descriptor.get("request_fingerprint") != _fingerprint(request)):
        raise ValueError("incompatible B2 matched shard descriptor")
    if descriptor_path.exists() and _strict_json(descriptor_path.read_text()) != descriptor:
        raise ValueError("B2 matched shard descriptor differs from manifest")
    for path in (part, metadata):
        if not path.is_file() or descriptor.get("sha256", {}).get(path.name) != _file_hash(path):
            raise ValueError(f"missing or modified B2 matched artifact: {path}")
    return _read_part(part, metadata, config, groups, calibration_metadata, cancellation, keys)


def generate_b2_matched_dataset(out_dir, known_dir, config: B2Config | None = None, *, limit_groups=None,
                                groups_per_shard=GROUPS_PER_SHARD, cancellation: CancellationConfig | None = None) -> None:
    """Generate the K17c matched set for frozen test-matched groups, bound to a verified known artifact."""
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
            raise ValueError("B2 matched generation request changed; use a fresh output directory")
    elif root.exists() and any(root.iterdir()):
        raise ValueError("unverified B2 matched output directory; use a fresh directory")
    else:
        root.mkdir(parents=True, exist_ok=True)
        _atomic_json(request_path, request)
        _save_calibration(root, ReceiverCalibration.load(known_root / "receiver_calibration.npz"))
    if (root / "manifest.json").exists():
        manifest = read_b2_matched_manifest(root)
        print(f"reusing verified {MATCHED_PROTOCOL} dataset ({manifest['n_samples']} samples)", flush=True)
        return
    if not (root / "calibration.json").exists():
        if (root / "receiver_calibration.npz").exists():
            raise ValueError("unverified partial B2 matched calibration; use a fresh output directory")
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
                raise ValueError("unverified partial B2 matched shard; use a fresh output directory")
            arrays, records = {key: [] for key in keys}, []
            for group in _groups(request, index):
                for name, label_index in zip(MATCHED_LABELS, LABEL_INDEX):
                    result = sample_matched_scene(name, group, config, calibration=calibration,
                                                  keep_iq=cancellation is not None)
                    if cancellation is not None:
                        plans = [[_stored_carrier(item, config.bandwidth) for item in plan] for plan in result.meta["plans"]]
                        arrays["residual"].append(_residual(result, plans, cancellation))
                        result.iq = None
                    arrays["spec"].append(result.spec_db.astype(np.float16))
                    arrays["mask"].append(result.mask_db.astype(np.float16))
                    arrays["label"].append(label_index)
                    arrays["seed"].append(group)
                    arrays["plan_consistency"].append(result.meta["plan_consistency"])
                    arrays["matched_bin"].append(result.meta["matched"]["bin"])
                    records.append(result.meta)
            stacked = {"spec": np.stack(arrays["spec"]), "mask": np.stack(arrays["mask"]),
                       "label": np.asarray(arrays["label"], np.int8), "seed": np.asarray(arrays["seed"], np.int64),
                       "plan_consistency": np.asarray(arrays["plan_consistency"], np.int8),
                       "matched_bin": np.asarray(arrays["matched_bin"], np.int8)}
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
    manifest = {"artifact_version": 1, "protocol": MATCHED_PROTOCOL, "parent_protocol": PROTOCOL, "artifact_stage": STAGE,
                "benchmark_complete": False, "labels": list(MATCHED_LABELS), "label_index": list(LABEL_INDEX),
                "matched": request["matched"], "config": config.to_dict(), "request": request,
                "request_fingerprint": request_id, "commit": _commit(), "calibration": calibration.to_dict(),
                "calibration_artifact": calibration_artifact, "role": ROLE, "scenario_seeds": _groups(request),
                "n_scenarios": count, "n_samples": count * len(MATCHED_LABELS),
                "per_label": {name: count for name in MATCHED_LABELS}, "shards": descriptors}
    if cancellation is not None:
        manifest.update(cancellation=cancellation.to_dict(), fifth_channel=dict(FIFTH_CHANNEL))
    _atomic_json(root / "manifest.json", manifest)
    read_b2_matched_manifest(root)
    print(f"{ROLE}: {count * len(MATCHED_LABELS)} calibrated B2 matched samples", flush=True)


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
        raise ValueError("B2 matched request must retain generator source hashes")
    expected_matched = _request(config, limit, request["groups_per_shard"], cancellation, request["known"])["matched"]
    if (request["protocol"] != MATCHED_PROTOCOL or request["parent_protocol"] != PROTOCOL or request["artifact_stage"] != STAGE
            or request["benchmark_complete"] is not False or request["contract"] != protocol_contract()
            or request["labels"] != list(MATCHED_LABELS) or request["label_index"] != list(LABEL_INDEX)
            or request["role"] != ROLE or request["matched"] != expected_matched
            or request["scenario_groups"] != groups or request["config"] != config.to_dict()
            or _strict_json((root / "request.json").read_text()) != request
            or manifest["artifact_version"] != 1 or manifest["protocol"] != MATCHED_PROTOCOL
            or manifest["parent_protocol"] != PROTOCOL or manifest["artifact_stage"] != STAGE
            or manifest["benchmark_complete"] is not False or manifest["labels"] != list(MATCHED_LABELS)
            or manifest["label_index"] != list(LABEL_INDEX) or manifest["matched"] != expected_matched
            or manifest["config"] != config.to_dict() or manifest["request_fingerprint"] != _fingerprint(request)
            or manifest.get("cancellation") != (None if cancellation is None else cancellation.to_dict())
            or manifest.get("fifth_channel") != (None if cancellation is None else FIFTH_CHANNEL)
            or manifest["role"] != ROLE or manifest["scenario_seeds"] != groups or manifest["n_scenarios"] != len(groups)
            or manifest["n_samples"] != len(groups) * len(MATCHED_LABELS)
            or manifest["per_label"] != {name: len(groups) for name in MATCHED_LABELS}
            or len(manifest["shards"]) != _n_shards(request)):
        raise ValueError("inconsistent B2 matched manifest/request")
    calibration, descriptor = _calibration(root, request)
    if descriptor != manifest["calibration_artifact"] or calibration.to_dict() != manifest["calibration"]:
        raise ValueError("B2 matched manifest differs from the receiver calibration artifact")
    _names(root, request, complete=True)
    if any((root / name).is_dir() for name in ("train", "val-select", "val-calib", "test")):
        raise ValueError("B2 matched output contains a role that the matched set must never occupy")
    return manifest, config


def read_b2_matched_manifest(path) -> dict:
    root = Path(path)
    try:
        manifest, config = _header(root)
        for index, descriptor in enumerate(manifest["shards"]):
            _verify_part(root, manifest["request"], index, descriptor, config, manifest["calibration"])
        return manifest
    except _READ_ERRORS as error:
        raise ValueError(f"invalid B2 matched dataset {root}: {error}") from error


def iter_b2_matched_shards(root):
    root = Path(root)
    try:
        manifest, config = _header(root)
        for index, descriptor in enumerate(manifest["shards"]):
            yield _verify_part(root, manifest["request"], index, descriptor, config, manifest["calibration"])
    except _READ_ERRORS as error:
        raise ValueError(f"invalid B2 matched dataset {root}: {error}") from error


def load_b2_matched_split(root) -> dict:
    """Load the matched set into memory; ``label`` uses the known LABELS indices (0, 6, 3)."""
    parts = list(iter_b2_matched_shards(root))
    keys = [key for key in FEATURE_ARRAY_KEYS if all(key in part for part in parts)]
    return {**{key: np.concatenate([part[key] for part in parts]) for key in keys},
            "meta": [record for part in parts for record in part["meta"]], "labels": list(MATCHED_LABELS)}


def b2_matched_fingerprint(path) -> str:
    return _fingerprint(read_b2_matched_manifest(path))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", required=True)
    parser.add_argument("--known", required=True, help="verified B2-base/1 or B2-feat/1 artifact to bind to")
    parser.add_argument("--config", help="JSON physical/instrument settings; must equal the known artifact's")
    parser.add_argument("--cancellation", help="JSON canceller settings; must equal the known artifact's")
    parser.add_argument("--limit-groups", type=int, help="pilot prefix of the frozen test-matched role (150 groups)")
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
        generate_b2_matched_dataset(args.out, args.known, config, limit_groups=args.limit_groups,
                                    groups_per_shard=args.groups_per_shard, cancellation=cancellation)
    except (ValueError, OSError) as error:
        parser.exit(2, f"error: {error}\n")


if __name__ == "__main__":
    main()

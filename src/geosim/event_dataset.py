"""E1-dev/1 paired, calibrated event-polarization development observations.

    python -m geosim.event_dataset --out data/events-pilot --n-seeds 6

Three controlled labels distinguish an overlapping uplink carrier and a received
downlink carrier. They describe simulated mechanisms, not uniquely identifiable
physical sources. Phase noise is a matched nuisance in every class. Separate
synthetic instrument pilots calibrate once; A1 and D1 semantics stay unchanged.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass, replace
from numbers import Real
from pathlib import Path
from zipfile import BadZipFile

import numpy as np
import scipy

from .dataset import _atomic_json, _canonical, _commit, _file_hash, _fingerprint, _generator_provenance
from .dual import DualScenarioConfig, simulate_dual
from .polarization import ReceiverCalibration, fit_receiver_calibration, jones_matrix
from .scenario import ScenarioConfig, default_plan
from .events import adjacent_satellite, carrier_under_carrier
from .plan import plan_mask_db
from . import FS_SIM
from .waveform import Carrier, constellation, samples_per_symbol

PROTOCOL = "E1-dev/1"
LABELS = ("clean", "carrier_under_carrier", "adjacent_satellite")
ROLE_STARTS = {"train": 2_000_000, "validation": 2_100_000, "test": 2_200_000}
SEEDS_PER_SHARD = 100
ARRAY_KEYS = ("spec", "mask", "label", "seed")


def _real(value, name: str, *, minimum=None, maximum=None) -> float:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real) or not np.isfinite(value):
        raise ValueError(f"{name} must be a finite real number")
    value = float(value)
    if (minimum is not None and value < minimum) or (maximum is not None and value > maximum):
        raise ValueError(f"{name} is outside the supported range")
    return value


@dataclass(frozen=True)
class EventDatasetConfig:
    """Exploratory engineering settings, not a measured oscillator specification."""
    n_seeds: int = 6
    bandwidth: float = 36e6
    nominal_xpd_db: float = 30.0
    c_over_i_min_db: float = 5.0
    c_over_i_max_db: float = 15.0
    satellite_linewidth_hz: float = 100.0
    receiver_linewidth_hz: float = 50.0
    downlink_xpd_db: float = 35.0
    receiver_xpd_db: float = 25.0
    receiver_gain_db: tuple[float, float] = (1.5, -1.0)
    receiver_phase_rad: tuple[float, float] = (0.2, -0.4)
    receiver_coupling_phase_rad: float = 0.3
    calibration_seed: int = 424242
    calibration_samples: int = 64
    calibration_noise_std: float = 0.001

    def __post_init__(self):
        if isinstance(self.n_seeds, bool) or not isinstance(self.n_seeds, int) or not 2 <= self.n_seeds <= 100_000:
            raise ValueError("n_seeds must be an integer in [2, 100000] to keep scenario roles disjoint")
        if isinstance(self.bandwidth, bool) or self.bandwidth not in (36e6, 72e6):
            raise ValueError("bandwidth must be 36e6 or 72e6 Hz")
        for name in ("nominal_xpd_db", "downlink_xpd_db", "receiver_xpd_db",
                     "satellite_linewidth_hz", "receiver_linewidth_hz"):
            object.__setattr__(self, name, _real(getattr(self, name), name, minimum=0))
        for name in ("c_over_i_min_db", "c_over_i_max_db"):
            object.__setattr__(self, name, _real(getattr(self, name), name, minimum=-20, maximum=100))
        if self.c_over_i_min_db > self.c_over_i_max_db:
            raise ValueError("c_over_i_min_db must not exceed c_over_i_max_db")
        for name in ("receiver_gain_db", "receiver_phase_rad"):
            values = getattr(self, name)
            if not isinstance(values, (list, tuple)) or len(values) != 2:
                raise ValueError(f"{name} must contain two finite values")
            pair = tuple(_real(value, name) for value in values)
            if name == "receiver_gain_db" and max(map(abs, pair)) > 100:
                raise ValueError("receiver_gain_db magnitude must not exceed 100 dB")
            object.__setattr__(self, name, pair)
        object.__setattr__(self, "receiver_coupling_phase_rad", _real(self.receiver_coupling_phase_rad, "receiver_coupling_phase_rad"))
        object.__setattr__(self, "calibration_noise_std", _real(self.calibration_noise_std, "calibration_noise_std", minimum=0))
        if (isinstance(self.calibration_seed, bool) or not isinstance(self.calibration_seed, int)
                or not 0 <= self.calibration_seed < 2**63):
            raise ValueError("calibration_seed must be a nonnegative int64 integer")
        if (isinstance(self.calibration_samples, bool) or not isinstance(self.calibration_samples, int)
                or self.calibration_samples < 2):
            raise ValueError("calibration_samples must be an integer >= 2")

    @classmethod
    def from_file(cls, path):
        try:
            raw = _strict_json(Path(path).read_text())
            if not isinstance(raw, dict):
                raise ValueError("event generation configuration must be a JSON object")
            return cls(**raw)
        except TypeError as error:
            raise ValueError(f"invalid event generation configuration: {error}") from error


def receiver_response(config: EventDatasetConfig) -> np.ndarray:
    gains = 10 ** (np.asarray(config.receiver_gain_db) / 20) * np.exp(1j * np.asarray(config.receiver_phase_rad))
    return np.diag(gains) @ jones_matrix(config.receiver_xpd_db, config.receiver_coupling_phase_rad)


def _request(config: EventDatasetConfig) -> dict:
    return json.loads(_canonical({"protocol": PROTOCOL, "labels": LABELS, "config": asdict(config),
                                 "role_starts": ROLE_STARTS, "seeds_per_shard": SEEDS_PER_SHARD,
                                 "source_sha256": _generator_provenance(),
                                 "numpy_version": np.__version__, "scipy_version": scipy.__version__}))


def _fit_calibration(config: EventDatasetConfig, request_id: str) -> ReceiverCalibration:
    rng = np.random.default_rng([config.calibration_seed, 1901])
    reference = (rng.standard_normal((2, config.calibration_samples))
                 + 1j * rng.standard_normal((2, config.calibration_samples))) / np.sqrt(2)
    noise = config.calibration_noise_std * (rng.standard_normal(reference.shape)
                                            + 1j * rng.standard_normal(reference.shape)) / np.sqrt(2)
    measured = receiver_response(config) @ reference + noise
    return fit_receiver_calibration(reference, measured,
                                    provenance=f"{PROTOCOL}:{request_id}:independent_pilots")


def _calibration(root: Path, request_id: str):
    descriptor = _strict_json((root / "calibration.json").read_text())
    path = root / "receiver_calibration.npz"
    if descriptor.get("file") != path.name or descriptor.get("sha256") != _file_hash(path):
        raise ValueError("missing or modified receiver calibration artifact")
    calibration = ReceiverCalibration.load(path)
    if calibration.to_dict() != descriptor.get("metadata"):
        raise ValueError("receiver calibration metadata differs from descriptor")
    if calibration.provenance != f"{PROTOCOL}:{request_id}:independent_pilots":
        raise ValueError("receiver calibration is not bound to this independent pilot request")
    return calibration, descriptor


def _scene_config(config: EventDatasetConfig, group: int, label: str) -> DualScenarioConfig:
    if label not in LABELS:
        raise ValueError("unsupported event label")
    rng = np.random.default_rng([group, 601])
    paths = [ScenarioConfig(bandwidth=config.bandwidth, seed=2 * group + p,
                            ibo_db=float(rng.uniform(9, 13)), cn_up_db=float(rng.uniform(15, 30)),
                            cn_dn_db=float(rng.uniform(15, 30))) for p in range(2)]
    return DualScenarioConfig(co=paths[0], cross=paths[1],
                              uplink_xpd_db=config.nominal_xpd_db,
                              downlink_xpd_db=config.downlink_xpd_db,
                              receiver_response=receiver_response(config),
                              satellite_linewidth_hz=config.satellite_linewidth_hz,
                              receiver_linewidth_hz=config.receiver_linewidth_hz)


def _event(config: EventDatasetConfig, group: int, label: str, plan):
    """Draw event parameters without consuming carrier, noise or phase streams."""
    if label == "clean":
        return None, None
    if label not in LABELS:
        raise ValueError("unsupported event label")
    ci = float(np.random.default_rng([group, 7100]).uniform(config.c_over_i_min_db, config.c_over_i_max_db))
    rng = np.random.default_rng([group, 7101, LABELS.index(label)])
    factory = carrier_under_carrier if label == "carrier_under_carrier" else adjacent_satellite
    return factory(rng, plan, config.bandwidth, ci)


def _strict_json(value: str):
    def reject(constant):
        raise ValueError(f"nonfinite JSON constant {constant}")
    def finite_float(number):
        parsed = float(number)
        if not np.isfinite(parsed):
            raise ValueError("nonfinite JSON numeric value")
        return parsed
    return json.loads(value, parse_constant=reject, parse_float=finite_float)


def _stored_carrier(value: dict, bandwidth: float) -> Carrier:
    """Check physical metadata without replaying a possibly newer sampler."""
    carrier = Carrier(**value)
    for key in ("f0", "symbol_rate", "alpha", "power"):
        _real(getattr(carrier, key), f"stored carrier {key}")
    if carrier.symbol_rate <= 0 or not 0 < carrier.alpha <= 1 or carrier.power <= 0:
        raise ValueError("stored carrier rate, roll-off and power must be positive")
    if abs(carrier.f0) + carrier.occupied_bw / 2 > bandwidth / 2 + 1e-6:
        raise ValueError("stored carrier occupied spectrum exceeds bandwidth")
    samples_per_symbol(carrier.symbol_rate, FS_SIM)
    try:
        constellation(carrier.mod, carrier.code_rate)
    except (KeyError, ValueError) as error:
        raise ValueError("stored carrier modulation or code rate is invalid") from error
    return carrier


def _check_event(event, config: EventDatasetConfig, name: str, plan):
    if name == "clean":
        if event is not None:
            raise ValueError("clean scene contains event parameters")
        return
    stage, reference = (("uplink", "total_planned_uplink") if name == "carrier_under_carrier"
                        else ("downlink", "wanted_receiver_feed"))
    if (not isinstance(event, dict) or event["kind"] != name or event["injection_stage"] != stage
            or event["power_reference"] != reference):
        raise ValueError("event parameters have the wrong kind, stage or power reference")
    ci = _real(event["c_over_i_db"], "event C/I", minimum=config.c_over_i_min_db,
               maximum=config.c_over_i_max_db)
    carrier = _stored_carrier(event["carrier"], config.bandwidth)
    if not np.isclose(carrier.power, 10 ** (-ci / 10), rtol=1e-12, atol=0):
        raise ValueError("event parameters have inconsistent C/I and nominal power")
    f_lo, f_hi = carrier.f0 - carrier.occupied_bw / 2, carrier.f0 + carrier.occupied_bw / 2
    if not np.allclose([event["f_lo"], event["f_hi"]], [f_lo, f_hi], rtol=0, atol=1e-6):
        raise ValueError("event parameters have inconsistent occupied band edges")
    if name == "carrier_under_carrier":
        index = event["victim_index"]
        if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(plan):
            raise ValueError("event victim index does not identify a planned carrier")
        victim = plan[index]
        if event["victim"] != asdict(victim):
            raise ValueError("event victim differs from the operator plan")
        if f_lo < victim.f0 - victim.occupied_bw / 2 - 1e-6 or f_hi > victim.f0 + victim.occupied_bw / 2 + 1e-6:
            raise ValueError("under-carrier event is not contained in its victim")
        victim_ci = _real(event["victim_c_over_i_db"], "victim C/I")
        if not np.isclose(victim_ci, ci + 10 * np.log10(victim.power), rtol=0, atol=1e-10):
            raise ValueError("event victim C/I has an inconsistent power reference")


def _paths(root: Path, role: str, index: int):
    directory = root / role
    return (directory / f"part-{index:05d}.npz", directory / f"meta-{index:05d}.jsonl",
            directory / f"shard-{index:05d}.json")


def _seeds(role: str, config: EventDatasetConfig, index: int | None = None) -> list[int]:
    first = 0 if index is None else index * SEEDS_PER_SHARD
    last = config.n_seeds if index is None else min((index + 1) * SEEDS_PER_SHARD, config.n_seeds)
    return list(range(ROLE_STARTS[role] + first, ROLE_STARTS[role] + last))


def _names(root: Path, role: str, n_shards: int, *, complete: bool):
    for pattern, template in (("part-*.npz", "part-{i:05d}.npz"), ("meta-*.jsonl", "meta-{i:05d}.jsonl"),
                              ("shard-*.json", "shard-{i:05d}.json")):
        actual = {p.name for p in (root / role).glob(pattern) if not p.name.endswith(".tmp.npz")}
        expected = {template.format(i=i) for i in range(n_shards)}
        if not actual <= expected or (complete and actual != expected):
            raise ValueError(f"unexpected or missing event artifacts in {role}: {pattern}")


def _read_part(part: Path, metadata: Path, config: EventDatasetConfig, role: str, seeds: list[int],
               calibration_metadata: dict) -> dict:
    with np.load(part, allow_pickle=False) as archive:
        if set(archive.files) != set(ARRAY_KEYS):
            raise ValueError("unexpected event array keys")
        data = {key: archive[key] for key in ARRAY_KEYS}
    records = [_strict_json(line) for line in metadata.read_text().splitlines()]
    n = len(LABELS) * len(seeds)
    if (data["spec"].shape != (n, 2, 128, 512) or data["mask"].shape != (n, 2, 512)
            or data["spec"].dtype != np.float16 or data["mask"].dtype != np.float16
            or data["label"].shape != (n,) or data["seed"].shape != (n,) or len(records) != n
            or data["label"].dtype.kind not in "iu" or data["seed"].dtype.kind not in "iu"
            or not np.isfinite(data["spec"]).all() or not np.isfinite(data["mask"]).all()):
        raise ValueError("invalid event dimensions, dtypes, values or metadata counts")
    pairs = list(zip(data["seed"].tolist(), data["label"].tolist()))
    if len(set(pairs)) != n or set(pairs) != {(seed, label) for seed in seeds for label in range(len(LABELS))}:
        raise ValueError("event scenario-label pairs differ from the request")
    paired, paired_ci = {}, {}
    for seed, label, record in zip(data["seed"], data["label"], records):
        name = LABELS[int(label)]
        if (record["protocol"] != PROTOCOL or record["label"] != name or record["role"] != role
                or record["scenario_id"] != int(seed)
                or record["receiver_calibration_applied"] is not True
                or record["receiver_calibration"] != calibration_metadata):
            raise ValueError("event metadata does not match the calibrated sample")
        scene = record["config"]
        if (scene["uplink_xpd_db"] != config.nominal_xpd_db
                or scene["downlink_xpd_db"] != config.downlink_xpd_db
                or scene["satellite_linewidth_hz"] != config.satellite_linewidth_hz
                or scene["receiver_linewidth_hz"] != config.receiver_linewidth_hz):
            raise ValueError("event physical mixing or phase noise differs from the request")
        response = scene["receiver_response"]
        receiver = np.asarray(response["real"]) + 1j * np.asarray(response["imag"])
        if (receiver.shape != (2, 2) or not np.allclose(receiver, receiver_response(config), rtol=1e-12, atol=1e-12)
                or scene["uplink_phase_rad"] != 0 or scene["downlink_phase_rad"] != 0):
            raise ValueError("event physical/instrument mixing differs from the request")
        for pol, key in enumerate(("co", "cross")):
            path = scene[key]
            if (path["seed"] != 2 * int(seed) + pol or path["bandwidth"] != config.bandwidth
                    or path["n_snap"] != 128 or path["snap_interval"] != 0.01
                    or path["linear"] is not False or path["filter_model"] != "etsi" or path["amplifier"] != "dvbs2_nl"
                    or not 9 <= path["ibo_db"] <= 13
                    or not 15 <= path["cn_up_db"] <= 30 or not 15 <= path["cn_dn_db"] <= 30):
                raise ValueError("event path configuration does not match the scenario group")
        if (record["has_interferer"] != [name == "carrier_under_carrier", False]
                or record["has_downlink_interferer"] != [name == "adjacent_satellite", False]):
            raise ValueError("event injection stage differs from the requested label")
        plans = [[_stored_carrier(carrier, config.bandwidth) for carrier in plan] for plan in record["plans"]]
        if len(plans) != 2 or any(not plan for plan in plans):
            raise ValueError("each event scene must contain two carrier plans")
        if any(not np.isclose(sum(carrier.power for carrier in plan), 1, rtol=1e-6, atol=1e-8) for plan in plans):
            raise ValueError("event carrier plan powers must sum to one")
        _check_event(record["event"], config, name, plans[0])
        if name != "clean":
            ci = record["event"]["c_over_i_db"]
            if int(seed) in paired_ci and paired_ci[int(seed)] != ci:
                raise ValueError("paired event C/I differs between physical mechanisms")
            paired_ci[int(seed)] = ci
        # Paired labels must change only the physical event, never the carrier
        # realization, thermal-noise streams, link settings or receiver response.
        common = {"config": scene, "plans": record["plans"]}
        if int(seed) in paired and paired[int(seed)] != common:
            raise ValueError("paired event scenes differ beyond the injected event")
        paired[int(seed)] = common
    for mask, record in zip(data["mask"], records):
        expected_mask = np.stack([plan_mask_db([Carrier(**item) for item in plan]) for plan in record["plans"]])
        if not np.array_equal(mask, expected_mask.astype(np.float16)):
            raise ValueError("event plan masks differ from the operator plans")
    return {**data, "meta": records}


def _verify_part(root: Path, role: str, index: int, descriptor: dict, request: dict,
                 config: EventDatasetConfig, calibration_metadata: dict) -> dict:
    part, metadata, _ = _paths(root, role, index)
    seeds = _seeds(role, config, index)
    if (descriptor.get("part") != part.name or descriptor.get("meta") != metadata.name
            or descriptor.get("role") != role or descriptor.get("scenario_seeds") != seeds
            or descriptor.get("request_fingerprint") != _fingerprint(request)):
        raise ValueError("incompatible event shard descriptor")
    for path in (part, metadata):
        if not path.is_file() or descriptor.get("sha256", {}).get(path.name) != _file_hash(path):
            raise ValueError(f"missing or modified event artifact: {path}")
    data = _read_part(part, metadata, config, role, seeds, calibration_metadata)
    if descriptor.get("n_samples") != len(data["label"]):
        raise ValueError("wrong event shard sample count")
    return data


def generate_event_dataset(out_dir, config: EventDatasetConfig | None = None) -> None:
    """Generate immutable, paired observations with one independent calibration."""
    config = EventDatasetConfig() if config is None else config
    if not isinstance(config, EventDatasetConfig):
        raise ValueError("config must be an EventDatasetConfig")
    request = _request(config)
    request_id = _fingerprint(request)
    root = Path(out_dir)
    request_path = root / "request.json"
    if request_path.exists():
        if _strict_json(request_path.read_text()) != request:
            raise ValueError("event generation request changed; use a fresh output directory")
    elif root.exists() and any(root.iterdir()):
        raise ValueError("unverified event output directory; use a fresh directory")
    else:
        # Validate the independent pilot fit before making persistent state.
        calibration = _fit_calibration(config, request_id)
        root.mkdir(parents=True, exist_ok=True)
        _atomic_json(request_path, request)
        calibration.save(root / "receiver_calibration.npz")
        _atomic_json(root / "calibration.json", {"file": "receiver_calibration.npz",
                                                 "sha256": _file_hash(root / "receiver_calibration.npz"),
                                                 "metadata": calibration.to_dict()})
    if (root / "manifest.json").exists():
        manifest = read_event_manifest(root)
        print(f"reusing verified event dataset ({sum(v['n_samples'] for v in manifest['roles'].values())} samples)", flush=True)
        return
    if not (root / "calibration.json").exists():
        if (root / "receiver_calibration.npz").exists():
            raise ValueError("unverified partial receiver calibration; use a fresh directory")
        calibration = _fit_calibration(config, request_id)
        calibration.save(root / "receiver_calibration.npz")
        _atomic_json(root / "calibration.json", {"file": "receiver_calibration.npz",
                                                 "sha256": _file_hash(root / "receiver_calibration.npz"),
                                                 "metadata": calibration.to_dict()})
    calibration, calibration_artifact = _calibration(root, request_id)
    n_shards = -(-config.n_seeds // SEEDS_PER_SHARD)
    roles = {}
    for role in ROLE_STARTS:
        (root / role).mkdir(exist_ok=True)
        _names(root, role, n_shards, complete=False)
        descriptors = []
        for index in range(n_shards):
            part, metadata, descriptor_path = _paths(root, role, index)
            if descriptor_path.exists():
                descriptor = _strict_json(descriptor_path.read_text())
                _verify_part(root, role, index, descriptor, request, config, calibration.to_dict())
            else:
                if part.exists() or metadata.exists():
                    raise ValueError("unverified partial event shard; use a fresh output directory")
                arrays = {key: [] for key in ARRAY_KEYS}
                records = []
                for seed in _seeds(role, config, index):
                    for label, name in enumerate(LABELS):
                        scene = _scene_config(config, seed, name)
                        plans = tuple(default_plan(path.seed, path.bandwidth) for path in (scene.co, scene.cross))
                        event, event_metadata = _event(config, seed, name, plans[0])
                        result = simulate_dual(scene, plans=plans, calibration=calibration,
                                               interferers=(event, None) if name == "carrier_under_carrier" else None,
                                               downlink_interferers=(event, None) if name == "adjacent_satellite" else None)
                        result.meta.update(protocol=PROTOCOL, label=name, role=role, scenario_id=seed,
                                           event=event_metadata)
                        arrays["spec"].append(result.spec_db.astype(np.float16))
                        arrays["mask"].append(result.mask_db.astype(np.float16))
                        arrays["label"].append(label)
                        arrays["seed"].append(seed)
                        records.append(result.meta)
                temporary_part, temporary_meta = part.with_suffix(".tmp.npz"), metadata.with_suffix(".jsonl.tmp")
                np.savez(temporary_part, spec=np.stack(arrays["spec"]), mask=np.stack(arrays["mask"]),
                         label=np.array(arrays["label"], np.int8), seed=np.array(arrays["seed"], np.int64))
                temporary_meta.write_text("".join(json.dumps(record, allow_nan=False) + "\n" for record in records))
                _read_part(temporary_part, temporary_meta, config, role, _seeds(role, config, index), calibration.to_dict())
                temporary_part.replace(part)
                temporary_meta.replace(metadata)
                descriptor = {"part": part.name, "meta": metadata.name, "role": role,
                              "scenario_seeds": _seeds(role, config, index), "n_samples": len(records),
                              "request_fingerprint": request_id,
                              "sha256": {p.name: _file_hash(p) for p in (part, metadata)}}
                _atomic_json(descriptor_path, descriptor)
            descriptors.append(descriptor)
        roles[role] = {"scenario_seeds": _seeds(role, config), "n_scenarios": config.n_seeds,
                       "n_samples": len(LABELS) * config.n_seeds, "per_label": {label: config.n_seeds for label in LABELS},
                       "shards": descriptors}
        print(f"{role}: {len(LABELS) * config.n_seeds} calibrated event samples", flush=True)
    manifest = {"artifact_version": 1, "protocol": PROTOCOL, "labels": list(LABELS),
                "bandwidth": config.bandwidth, "n_seeds": config.n_seeds,
                "config": request["config"],
                "request": request, "request_fingerprint": request_id, "commit": _commit(),
                "calibration": calibration.to_dict(), "calibration_artifact": calibration_artifact,
                "roles": roles}
    _atomic_json(root / "manifest.json", manifest)
    read_event_manifest(root)


def _inspect(path, collect_role=None):
    root = Path(path)
    try:
        manifest = _strict_json((root / "manifest.json").read_text())
        request = manifest["request"]
        config = EventDatasetConfig(**request["config"])
        if (request["protocol"] != PROTOCOL or request["labels"] != list(LABELS)
                or request["role_starts"] != ROLE_STARTS or request["seeds_per_shard"] != SEEDS_PER_SHARD
                or json.loads(_canonical(asdict(config))) != request["config"]
                or _strict_json((root / "request.json").read_text()) != request
                or manifest["artifact_version"] != 1 or manifest["protocol"] != PROTOCOL
                or manifest["labels"] != list(LABELS) or manifest["bandwidth"] != config.bandwidth
                or manifest["config"] != request["config"]
                or manifest["n_seeds"] != config.n_seeds or manifest["request_fingerprint"] != _fingerprint(request)
                or set(manifest["roles"]) != set(ROLE_STARTS)):
            raise ValueError("inconsistent event manifest/request")
        calibration, descriptor = _calibration(root, _fingerprint(request))
        if descriptor != manifest["calibration_artifact"] or calibration.to_dict() != manifest["calibration"]:
            raise ValueError("event manifest calibration differs from the stored independent calibration")
        if calibration.to_dict()["n_pilots"] != config.calibration_samples:
            raise ValueError("event receiver calibration pilot count differs from request")
        n_shards = -(-config.n_seeds // SEEDS_PER_SHARD)
        arrays, records = {key: [] for key in ARRAY_KEYS}, []
        for role in ROLE_STARTS:
            info = manifest["roles"][role]
            if (info["scenario_seeds"] != _seeds(role, config) or info["n_scenarios"] != config.n_seeds
                    or info["n_samples"] != len(LABELS) * config.n_seeds
                    or info["per_label"] != {label: config.n_seeds for label in LABELS}
                    or len(info["shards"]) != n_shards):
                raise ValueError("event role counts or scenario groups differ from request")
            _names(root, role, n_shards, complete=True)
            for index, shard in enumerate(info["shards"]):
                if _strict_json(_paths(root, role, index)[2].read_text()) != shard:
                    raise ValueError("event shard descriptor differs from manifest")
                data = _verify_part(root, role, index, shard, request, config, calibration.to_dict())
                if collect_role == role:
                    for key in ARRAY_KEYS:
                        arrays[key].append(data[key])
                    records.extend(data["meta"])
        data = {**{key: np.concatenate(parts) for key, parts in arrays.items()}, "meta": records} if collect_role else None
        return manifest, data, _fingerprint(manifest)
    except (OSError, KeyError, TypeError, ValueError, IndexError, BadZipFile) as error:
        raise ValueError(f"invalid event dataset {root}: {error}") from error


def read_event_manifest(path) -> dict:
    """Validate calibration and every referenced role/shard before returning metadata."""
    return _inspect(path)[0]


def load_event_split(root, role: str) -> dict:
    if role not in ROLE_STARTS:
        raise ValueError(f"role must be one of {tuple(ROLE_STARTS)}")
    return _inspect(root, collect_role=role)[1]


def event_fingerprint(path) -> str:
    """Validated content identity including independent calibration and all roles."""
    return _inspect(path)[2]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", required=True)
    parser.add_argument("--config", help="optional JSON generation configuration")
    parser.add_argument("--n-seeds", type=int, help="override groups per role (default 6)")
    parser.add_argument("--bandwidth", type=float, choices=(36e6, 72e6), help="override transponder bandwidth in Hz")
    args = parser.parse_args(argv)
    try:
        config = EventDatasetConfig.from_file(args.config) if args.config else EventDatasetConfig()
        overrides = {key: value for key, value in {"n_seeds": args.n_seeds, "bandwidth": args.bandwidth}.items()
                     if value is not None}
        generate_event_dataset(args.out, replace(config, **overrides))
    except (ValueError, OSError) as error:
        parser.exit(2, f"error: {error}\n")


if __name__ == "__main__":
    main()

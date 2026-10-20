"""D1-dev/1 paired, calibrated dual-polarization development observations.

    python -m geosim.dual_dataset --out data/dual-pilot --n-seeds 6

The controlled binary event changes uplink XPD only. Receiver calibration uses
separate synthetic pilots once, never scene labels or training/test samples.
Frozen A1 classes, sampling and artifacts are untouched.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from numbers import Real
from pathlib import Path
from zipfile import BadZipFile

import numpy as np
import scipy

from .dataset import _atomic_json, _canonical, _commit, _file_hash, _fingerprint, _generator_provenance
from .dual import DualScenarioConfig, simulate_dual
from .polarization import ReceiverCalibration, fit_receiver_calibration, jones_matrix
from .scenario import ScenarioConfig

PROTOCOL = "D1-dev/1"
LABELS = ("clean", "cross_pol")
ROLE_STARTS = {"train": 1_000_000, "validation": 1_100_000, "test": 1_200_000}
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
class DualDatasetConfig:
    n_seeds: int = 6
    bandwidth: float = 36e6
    nominal_xpd_db: float = 30.0
    event_xpd_db: float = 10.0
    downlink_xpd_db: float = 35.0
    receiver_xpd_db: float = 25.0
    receiver_gain_db: tuple[float, float] = (1.5, -1.0)
    receiver_phase_rad: tuple[float, float] = (0.2, -0.4)
    receiver_coupling_phase_rad: float = 0.3
    calibration_seed: int = 424242
    calibration_samples: int = 64
    calibration_noise_std: float = 0.001

    def __post_init__(self):
        if isinstance(self.n_seeds, bool) or not isinstance(self.n_seeds, int) or not 1 <= self.n_seeds <= 100_000:
            raise ValueError("n_seeds must be an integer in [1, 100000] to keep scenario roles disjoint")
        if isinstance(self.bandwidth, bool) or self.bandwidth not in (36e6, 72e6):
            raise ValueError("bandwidth must be 36e6 or 72e6 Hz")
        for name in ("nominal_xpd_db", "event_xpd_db", "downlink_xpd_db", "receiver_xpd_db"):
            object.__setattr__(self, name, _real(getattr(self, name), name, minimum=0))
        if self.event_xpd_db >= self.nominal_xpd_db:
            raise ValueError("event_xpd_db must be lower than nominal_xpd_db")
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


def receiver_response(config: DualDatasetConfig) -> np.ndarray:
    gains = 10 ** (np.asarray(config.receiver_gain_db) / 20) * np.exp(1j * np.asarray(config.receiver_phase_rad))
    return np.diag(gains) @ jones_matrix(config.receiver_xpd_db, config.receiver_coupling_phase_rad)


def _request(config: DualDatasetConfig) -> dict:
    return json.loads(_canonical({"protocol": PROTOCOL, "labels": LABELS, "config": asdict(config),
                                 "role_starts": ROLE_STARTS, "seeds_per_shard": SEEDS_PER_SHARD,
                                 "source_sha256": _generator_provenance(),
                                 "numpy_version": np.__version__, "scipy_version": scipy.__version__}))


def _fit_calibration(config: DualDatasetConfig, request_id: str) -> ReceiverCalibration:
    rng = np.random.default_rng([config.calibration_seed, 1901])
    reference = (rng.standard_normal((2, config.calibration_samples))
                 + 1j * rng.standard_normal((2, config.calibration_samples))) / np.sqrt(2)
    noise = config.calibration_noise_std * (rng.standard_normal(reference.shape)
                                            + 1j * rng.standard_normal(reference.shape)) / np.sqrt(2)
    measured = receiver_response(config) @ reference + noise
    return fit_receiver_calibration(reference, measured,
                                    provenance=f"{PROTOCOL}:{request_id}:independent_pilots")


def _calibration(root: Path, request_id: str):
    descriptor = json.loads((root / "calibration.json").read_text())
    path = root / "receiver_calibration.npz"
    if descriptor.get("file") != path.name or descriptor.get("sha256") != _file_hash(path):
        raise ValueError("missing or modified receiver calibration artifact")
    calibration = ReceiverCalibration.load(path)
    if calibration.to_dict() != descriptor.get("metadata"):
        raise ValueError("receiver calibration metadata differs from descriptor")
    if calibration.provenance != f"{PROTOCOL}:{request_id}:independent_pilots":
        raise ValueError("receiver calibration is not bound to this independent pilot request")
    return calibration, descriptor


def _scene_config(config: DualDatasetConfig, group: int, label: str) -> DualScenarioConfig:
    rng = np.random.default_rng([group, 601])
    paths = [ScenarioConfig(bandwidth=config.bandwidth, seed=2 * group + p,
                            ibo_db=float(rng.uniform(9, 13)), cn_up_db=float(rng.uniform(15, 30)),
                            cn_dn_db=float(rng.uniform(15, 30))) for p in range(2)]
    return DualScenarioConfig(co=paths[0], cross=paths[1],
                              uplink_xpd_db=config.nominal_xpd_db if label == "clean" else config.event_xpd_db,
                              downlink_xpd_db=config.downlink_xpd_db,
                              receiver_response=receiver_response(config))


def _paths(root: Path, role: str, index: int):
    directory = root / role
    return (directory / f"part-{index:05d}.npz", directory / f"meta-{index:05d}.jsonl",
            directory / f"shard-{index:05d}.json")


def _seeds(role: str, config: DualDatasetConfig, index: int | None = None) -> list[int]:
    first = 0 if index is None else index * SEEDS_PER_SHARD
    last = config.n_seeds if index is None else min((index + 1) * SEEDS_PER_SHARD, config.n_seeds)
    return list(range(ROLE_STARTS[role] + first, ROLE_STARTS[role] + last))


def _names(root: Path, role: str, n_shards: int, *, complete: bool):
    for pattern, template in (("part-*.npz", "part-{i:05d}.npz"), ("meta-*.jsonl", "meta-{i:05d}.jsonl"),
                              ("shard-*.json", "shard-{i:05d}.json")):
        actual = {p.name for p in (root / role).glob(pattern) if not p.name.endswith(".tmp.npz")}
        expected = {template.format(i=i) for i in range(n_shards)}
        if not actual <= expected or (complete and actual != expected):
            raise ValueError(f"unexpected or missing dual artifacts in {role}: {pattern}")


def _read_part(part: Path, metadata: Path, config: DualDatasetConfig, role: str, seeds: list[int],
               calibration_metadata: dict) -> dict:
    with np.load(part, allow_pickle=False) as archive:
        if set(archive.files) != set(ARRAY_KEYS):
            raise ValueError("unexpected dual array keys")
        data = {key: archive[key] for key in ARRAY_KEYS}
    records = [json.loads(line) for line in metadata.read_text().splitlines()]
    n = 2 * len(seeds)
    if (data["spec"].shape != (n, 2, 128, 512) or data["mask"].shape != (n, 2, 512)
            or data["spec"].dtype != np.float16 or data["mask"].dtype != np.float16
            or data["label"].shape != (n,) or data["seed"].shape != (n,) or len(records) != n
            or data["label"].dtype.kind not in "iu" or data["seed"].dtype.kind not in "iu"
            or not np.isfinite(data["spec"]).all() or not np.isfinite(data["mask"]).all()):
        raise ValueError("invalid dual dimensions, dtypes, values or metadata counts")
    pairs = list(zip(data["seed"].tolist(), data["label"].tolist()))
    if len(set(pairs)) != n or set(pairs) != {(seed, label) for seed in seeds for label in range(2)}:
        raise ValueError("dual scenario-label pairs differ from the request")
    paired = {}
    for seed, label, record in zip(data["seed"], data["label"], records):
        name = LABELS[int(label)]
        expected_xpd = config.nominal_xpd_db if name == "clean" else config.event_xpd_db
        if (record["protocol"] != PROTOCOL or record["label"] != name or record["role"] != role
                or record["scenario_id"] != int(seed)
                or record["receiver_calibration_applied"] is not True
                or record["receiver_calibration"] != calibration_metadata):
            raise ValueError("dual metadata does not match the calibrated sample")
        scene = record["config"]
        if scene["uplink_xpd_db"] != expected_xpd or scene["downlink_xpd_db"] != config.downlink_xpd_db:
            raise ValueError("dual physical XPD differs from the requested label")
        response = scene["receiver_response"]
        receiver = np.asarray(response["real"]) + 1j * np.asarray(response["imag"])
        if (receiver.shape != (2, 2) or not np.allclose(receiver, receiver_response(config), rtol=1e-12, atol=1e-12)
                or scene["uplink_phase_rad"] != 0 or scene["downlink_phase_rad"] != 0):
            raise ValueError("dual physical/instrument mixing differs from the request")
        for pol, key in enumerate(("co", "cross")):
            path = scene[key]
            if (path["seed"] != 2 * int(seed) + pol or path["bandwidth"] != config.bandwidth
                    or path["n_snap"] != 128 or path["snap_interval"] != 0.01
                    or path["linear"] is not False or path["filter_model"] != "etsi" or path["amplifier"] != "dvbs2_nl"
                    or not 9 <= path["ibo_db"] <= 13
                    or not 15 <= path["cn_up_db"] <= 30 or not 15 <= path["cn_dn_db"] <= 30):
                raise ValueError("dual path configuration does not match the scenario group")
        # Paired labels must change only the physical event, never the carrier
        # realization, thermal-noise streams, link settings or receiver response.
        common = {key: value for key, value in scene.items() if key != "uplink_xpd_db"}
        if int(seed) in paired and paired[int(seed)] != common:
            raise ValueError("paired dual scenes differ beyond uplink leakage")
        paired[int(seed)] = common
    return {**data, "meta": records}


def _verify_part(root: Path, role: str, index: int, descriptor: dict, request: dict,
                 config: DualDatasetConfig, calibration_metadata: dict) -> dict:
    part, metadata, _ = _paths(root, role, index)
    seeds = _seeds(role, config, index)
    if (descriptor.get("part") != part.name or descriptor.get("meta") != metadata.name
            or descriptor.get("role") != role or descriptor.get("scenario_seeds") != seeds
            or descriptor.get("request_fingerprint") != _fingerprint(request)):
        raise ValueError("incompatible dual shard descriptor")
    for path in (part, metadata):
        if not path.is_file() or descriptor.get("sha256", {}).get(path.name) != _file_hash(path):
            raise ValueError(f"missing or modified dual artifact: {path}")
    data = _read_part(part, metadata, config, role, seeds, calibration_metadata)
    if descriptor.get("n_samples") != len(data["label"]):
        raise ValueError("wrong dual shard sample count")
    return data


def generate_dual_dataset(out_dir, config: DualDatasetConfig | None = None) -> None:
    """Generate immutable, paired observations with one independent calibration."""
    config = DualDatasetConfig() if config is None else config
    if not isinstance(config, DualDatasetConfig):
        raise ValueError("config must be a DualDatasetConfig")
    request = _request(config)
    request_id = _fingerprint(request)
    root = Path(out_dir)
    request_path = root / "request.json"
    if request_path.exists():
        if json.loads(request_path.read_text()) != request:
            raise ValueError("dual generation request changed; use a fresh output directory")
    elif root.exists() and any(root.iterdir()):
        raise ValueError("unverified dual output directory; use a fresh directory")
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
        manifest = read_dual_manifest(root)
        print(f"reusing verified dual dataset ({sum(v['n_samples'] for v in manifest['roles'].values())} samples)", flush=True)
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
                descriptor = json.loads(descriptor_path.read_text())
                _verify_part(root, role, index, descriptor, request, config, calibration.to_dict())
            else:
                if part.exists() or metadata.exists():
                    raise ValueError("unverified partial dual shard; use a fresh output directory")
                arrays = {key: [] for key in ARRAY_KEYS}
                records = []
                for seed in _seeds(role, config, index):
                    for label, name in enumerate(LABELS):
                        scene = _scene_config(config, seed, name)
                        result = simulate_dual(scene, calibration=calibration)
                        result.meta.update(protocol=PROTOCOL, label=name, role=role, scenario_id=seed)
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
                       "n_samples": 2 * config.n_seeds, "per_label": {label: config.n_seeds for label in LABELS},
                       "shards": descriptors}
        print(f"{role}: {2 * config.n_seeds} calibrated dual samples", flush=True)
    manifest = {"artifact_version": 1, "protocol": PROTOCOL, "labels": list(LABELS),
                "bandwidth": config.bandwidth, "n_seeds": config.n_seeds,
                "config": request["config"],
                "request": request, "request_fingerprint": request_id, "commit": _commit(),
                "calibration": calibration.to_dict(), "calibration_artifact": calibration_artifact,
                "roles": roles}
    _atomic_json(root / "manifest.json", manifest)
    read_dual_manifest(root)


def _inspect(path, collect_role=None):
    root = Path(path)
    try:
        manifest = json.loads((root / "manifest.json").read_text())
        request = manifest["request"]
        config = DualDatasetConfig(**request["config"])
        if (request["protocol"] != PROTOCOL or request["labels"] != list(LABELS)
                or request["role_starts"] != ROLE_STARTS or request["seeds_per_shard"] != SEEDS_PER_SHARD
                or json.loads(_canonical(asdict(config))) != request["config"]
                or json.loads((root / "request.json").read_text()) != request
                or manifest["artifact_version"] != 1 or manifest["protocol"] != PROTOCOL
                or manifest["labels"] != list(LABELS) or manifest["bandwidth"] != config.bandwidth
                or manifest["config"] != request["config"]
                or manifest["n_seeds"] != config.n_seeds or manifest["request_fingerprint"] != _fingerprint(request)
                or set(manifest["roles"]) != set(ROLE_STARTS)):
            raise ValueError("inconsistent dual manifest/request")
        calibration, descriptor = _calibration(root, _fingerprint(request))
        if descriptor != manifest["calibration_artifact"] or calibration.to_dict() != manifest["calibration"]:
            raise ValueError("dual manifest calibration differs from the stored independent calibration")
        if calibration.to_dict()["n_pilots"] != config.calibration_samples:
            raise ValueError("dual receiver calibration pilot count differs from request")
        n_shards = -(-config.n_seeds // SEEDS_PER_SHARD)
        arrays, records = {key: [] for key in ARRAY_KEYS}, []
        for role in ROLE_STARTS:
            info = manifest["roles"][role]
            if (info["scenario_seeds"] != _seeds(role, config) or info["n_scenarios"] != config.n_seeds
                    or info["n_samples"] != 2 * config.n_seeds
                    or info["per_label"] != {label: config.n_seeds for label in LABELS}
                    or len(info["shards"]) != n_shards):
                raise ValueError("dual role counts or scenario groups differ from request")
            _names(root, role, n_shards, complete=True)
            for index, shard in enumerate(info["shards"]):
                if json.loads(_paths(root, role, index)[2].read_text()) != shard:
                    raise ValueError("dual shard descriptor differs from manifest")
                data = _verify_part(root, role, index, shard, request, config, calibration.to_dict())
                if collect_role == role:
                    for key in ARRAY_KEYS:
                        arrays[key].append(data[key])
                    records.extend(data["meta"])
        data = {**{key: np.concatenate(parts) for key, parts in arrays.items()}, "meta": records} if collect_role else None
        return manifest, data, _fingerprint(manifest)
    except (OSError, KeyError, TypeError, ValueError, IndexError, BadZipFile) as error:
        raise ValueError(f"invalid dual dataset {root}: {error}") from error


def read_dual_manifest(path) -> dict:
    """Validate calibration and every referenced role/shard before returning metadata."""
    return _inspect(path)[0]


def load_dual_split(root, role: str) -> dict:
    if role not in ROLE_STARTS:
        raise ValueError(f"role must be one of {tuple(ROLE_STARTS)}")
    return _inspect(root, collect_role=role)[1]


def dual_fingerprint(path) -> str:
    """Validated content identity including independent calibration and all roles."""
    return _inspect(path)[2]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", required=True)
    parser.add_argument("--n-seeds", type=int, default=6)
    parser.add_argument("--bandwidth", type=float, choices=(36e6, 72e6), default=36e6)
    args = parser.parse_args(argv)
    try:
        generate_dual_dataset(args.out, DualDatasetConfig(n_seeds=args.n_seeds, bandwidth=args.bandwidth))
    except ValueError as error:
        parser.exit(2, f"error: {error}\n")


if __name__ == "__main__":
    main()

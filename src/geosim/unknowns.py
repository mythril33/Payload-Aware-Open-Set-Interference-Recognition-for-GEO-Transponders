"""Test-only unknown events, separate from the frozen A1 class taxonomy.

    python -m geosim.unknowns --out data/unknowns-pilot --n-seeds 6

U1-dev/1 injects all events on the uplink. Pulse/burst timing is defined in
physical seconds, not array row indices. C/I is referenced to *active* source
power against the unit-power planned carrier load; duty is never normalized
away. Extra noise may be indistinguishable from a changed uplink noise floor.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path
from zipfile import BadZipFile

import numpy as np
import scipy

from . import FS_SIM
from .dataset import _atomic_json, _commit, _file_hash, _fingerprint, _generator_provenance
from .scenario import ScenarioConfig, ScenarioResult, default_plan, simulate
from .sensor import N_SIM, WARMUP_SIM

PROTOCOL = "U1-dev/1"
UNKNOWN_LABELS = ("pulsed", "wideband_noise", "intermittent_bursts")
SEEDS_PER_SHARD = 100
ARRAY_KEYS = ("spec", "mask", "label", "seed")
MAX_VISIBILITY_DRAWS = 64


def _positive_int(value, name):
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{name} must be a positive integer")


def _seed(value, name="seed"):
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value < 2**63 - 1:
        raise ValueError(f"{name} must be a nonnegative int64 seed")


def _visible_pulse(period, on, offset, n_snap, snap_interval):
    """Resolve full ON and OFF windows after the actual monitor warm-up crop."""
    starts = np.arange(n_snap) * snap_interval + WARMUP_SIM / FS_SIM
    duration = (N_SIM - WARMUP_SIM - 1) / FS_SIM
    phase = (starts + offset) % period
    fully_active = phase + duration < on
    fully_inactive = (phase >= on) & (phase + duration < period)
    return bool(fully_active.any() and fully_inactive.any())


def _pulse_parameters(rng, n_snap, snap_interval):
    """Condition draws on sampled visibility, without changing source power.

    Rare period/phase aliases otherwise miss every narrow ON interval. Record
    this conditioning because it changes the distribution from unconditional
    physical pulse occurrence to observable pulse events.
    """
    for rejected in range(MAX_VISIBILITY_DRAWS):
        period = float(rng.uniform(0.04, 0.09))
        on = float(rng.uniform(0.006, 0.018))
        offset = float(rng.uniform(0, period))
        if _visible_pulse(period, on, offset, n_snap, snap_interval):
            return period, on, offset, rejected, False
    # Deterministic in-range alternatives align the first retained window ON.
    # An arbitrary sampling configuration can still fail to resolve any OFF
    # state; fail explicitly after this finite search rather than looping.
    for period in (0.041, 0.047, 0.053, 0.061, 0.073, 0.089):
        on = 0.012
        offset = (on / 2 - WARMUP_SIM / FS_SIM) % period
        if _visible_pulse(period, on, offset, n_snap, snap_interval):
            return period, on, offset, MAX_VISIBILITY_DRAWS, True
    raise ValueError("sampling configuration cannot resolve active and inactive pulse windows after bounded parameter search")


def unknown_interferer(label: str, bandwidth: float, seed: int, *, n_snap: int = 128,
                       snap_interval: float = 0.01):
    """Return an uplink callable and mutable event metadata for one unknown.

    Metadata occupancy is populated when the callable is actually evaluated.
    The existing simulator calls it once for the observed snapshot windows.
    """
    if label not in UNKNOWN_LABELS:
        raise ValueError(f"unknown family must be one of {UNKNOWN_LABELS}")
    _seed(seed)
    _positive_int(n_snap, "n_snap")
    if bandwidth not in (36e6, 72e6):
        raise ValueError("bandwidth must be 36e6 or 72e6 Hz")
    if not np.isfinite(snap_interval) or snap_interval <= N_SIM / FS_SIM:
        raise ValueError("snap_interval must exceed one simulated snapshot duration")
    if label != "wideband_noise" and (n_snap < 16 or (n_snap - 1) * snap_interval < 0.15 - 1e-12):
        raise ValueError("temporal families need at least 16 snapshots spanning at least 150 ms")
    rng = np.random.default_rng([seed, 404, UNKNOWN_LABELS.index(label)])
    active_ci = float(rng.uniform(5, 35))
    power = 10 ** (-active_ci / 10)
    frequency = float(rng.uniform(-0.35 * bandwidth, 0.35 * bandwidth))
    info = {"kind": label, "injection_point": "uplink", "active_c_over_i_db": active_ci,
            "c_over_i_db": active_ci,
            "power_convention": "C/I = total planned carrier power / active source power; carrier load has unit power",
            "active_power": power}

    if label == "pulsed":
        period, on, offset, rejected, fallback = _pulse_parameters(rng, n_snap, snap_interval)
        gate = lambda times: ((times + offset) % period) < on
        info.update(f0=frequency, period_s=period, on_duration_s=on, offset_s=offset,
                    continuous_duty_fraction=on / period, carrier_shape="cw",
                    visibility_conditioning="at least one fully active and one fully inactive retained monitor window",
                    visibility_rejected_draws=rejected, visibility_fallback=fallback)
    elif label == "intermittent_bursts":
        horizon = (n_snap - 1) * snap_interval
        intervals, start = [], min(float(rng.uniform(0.03, 0.08)), horizon - 0.10)
        while start + 0.08 <= horizon - 0.01 + 1e-12:
            end = min(start + float(rng.uniform(0.08, 0.16)), horizon - 0.01)
            intervals.append((start, end))
            start = end + float(rng.uniform(0.12, 0.30))

        def gate(times):
            result = np.zeros(times.shape, bool)
            for lo, hi in intervals:
                result |= (times >= lo) & (times < hi)
            return result

        info.update(f0=frequency, intervals_s=intervals, carrier_shape="cw",
                    continuous_duty_fraction=sum(hi - lo for lo, hi in intervals) / horizon)
    else:
        width = float(rng.uniform(0.6, 0.9) * bandwidth)
        info.update(center_hz=0.0, bandwidth_hz=width,
                    identifiability="may be indistinguishable from an elevated bandlimited uplink noise floor")

    def generate(event_rng, t0, n, fs):
        times = np.asarray(t0)[:, None] + np.arange(n)[None, :] / fs
        if label == "wideband_noise":
            bins = np.abs(np.fft.fftfreq(n, 1 / fs)) < info["bandwidth_hz"] / 2
            if not np.any(bins):
                raise ValueError("noise bandwidth contains no FFT bins at this sampling configuration")
            white = (event_rng.standard_normal(times.shape) + 1j * event_rng.standard_normal(times.shape)) / np.sqrt(2)
            waveform = np.fft.ifft(np.fft.fft(white, axis=-1) * bins, axis=-1)
            # Expected active power, without per-snapshot amplitude renormalization.
            waveform *= np.sqrt(power * n / bins.sum())
            occupancy = np.ones(times.shape, bool)
        else:
            occupancy = gate(times)
            phase = 2 * np.pi * frequency * times + event_rng.uniform(0, 2 * np.pi)
            waveform = np.sqrt(power) * np.exp(1j * phase) * occupancy
        # simulate() supplies extra leading input samples to settle filters;
        # the monitoring receiver discards that warm-up time region.
        first = WARMUP_SIM if n == N_SIM and fs == FS_SIM else 0
        observed_occupancy = occupancy[:, first:]
        observed_waveform = waveform[:, first:]
        duty = float(observed_occupancy.mean())
        sampled_rows = observed_occupancy.any(axis=1)
        if label != "wideband_noise" and (not sampled_rows.any() or sampled_rows.all()):
            raise ValueError("temporal event is not identifiable in these observed windows: need active and inactive snapshots")
        info.update(observed_sample_duty_fraction=duty,
                    occupied_snapshots=sampled_rows.tolist(),
                    observed_snapshot_occupancy=float(sampled_rows.mean()),
                    observed_average_c_over_i_db=active_ci - 10 * np.log10(duty),
                    observed_mean_source_power=float(np.mean(np.abs(observed_waveform) ** 2)),
                    discarded_source_warmup_samples=first)
        return waveform.astype(np.complex64)

    return generate, info


def sample_unknown(label: str, bandwidth: float, seed: int, keep_iq: bool = False,
                   **cfg_overrides) -> ScenarioResult:
    """Simulate a test-only event with nominal A1-like link settings.

    All unknown families of one seed share the carrier plan, symbols, link
    settings and thermal-noise realization. Event parameters have a separate RNG.
    """
    _seed(seed)
    if "seed" in cfg_overrides:
        raise ValueError("seed must be supplied through the explicit seed argument")
    link = np.random.default_rng([seed, 101])
    cfg = replace(ScenarioConfig(bandwidth=bandwidth, seed=seed,
                                 ibo_db=float(link.uniform(9, 13)),
                                 cn_up_db=float(link.uniform(15, 30)),
                                 cn_dn_db=float(link.uniform(15, 30))), **cfg_overrides)
    event, info = unknown_interferer(label, bandwidth, seed, n_snap=cfg.n_snap, snap_interval=cfg.snap_interval)
    result = simulate(cfg, plan=default_plan(seed, bandwidth), interferer=event, keep_iq=keep_iq)
    result.meta.update(label=label, protocol=PROTOCOL, test_only=True, interferer=info)
    return result


def _request(n_seeds, first_seed, bandwidth, families):
    _positive_int(n_seeds, "n_seeds")
    _seed(first_seed, "first_seed")
    _seed(first_seed + n_seeds - 1, "last_seed")
    if bandwidth not in (36e6, 72e6):
        raise ValueError("bandwidth must be 36e6 or 72e6 Hz")
    families = tuple(families)
    if not families or len(set(families)) != len(families) or any(f not in UNKNOWN_LABELS for f in families):
        raise ValueError("families must be nonempty distinct known unknown-family names")
    return {"protocol": PROTOCOL, "test_only": True, "n_seeds": n_seeds, "first_seed": first_seed,
            "bandwidth": float(bandwidth), "families": list(families), "seeds_per_shard": SEEDS_PER_SHARD,
            "generator": _generator_provenance(), "numpy_version": np.__version__, "scipy_version": scipy.__version__}


def _paths(root, index):
    return root / f"part-{index:05d}.npz", root / f"meta-{index:05d}.jsonl", root / f"shard-{index:05d}.json"


def _expected_seeds(request, index):
    return list(range(request["first_seed"] + index * SEEDS_PER_SHARD,
                      request["first_seed"] + min((index + 1) * SEEDS_PER_SHARD, request["n_seeds"])))


def _names(root, n_shards, complete):
    for pattern, template in (("part-*.npz", "part-{i:05d}.npz"), ("meta-*.jsonl", "meta-{i:05d}.jsonl"),
                              ("shard-*.json", "shard-{i:05d}.json")):
        actual = {p.name for p in root.glob(pattern) if not p.name.endswith(".tmp.npz")}
        expected = {template.format(i=i) for i in range(n_shards)}
        if not actual <= expected or (complete and actual != expected):
            raise ValueError(f"unexpected or missing unknown artifact files in {root}")


def _read_part(part, metadata, request, seeds):
    with np.load(part, allow_pickle=False) as stored:
        if set(stored.files) != set(ARRAY_KEYS):
            raise ValueError("invalid unknown array keys")
        data = {key: stored[key] for key in ARRAY_KEYS}
    meta = [json.loads(line) for line in metadata.read_text().splitlines()]
    n = len(seeds) * len(request["families"])
    if (data["spec"].shape != (n, 128, 512) or data["mask"].shape != (n, 512)
            or data["spec"].dtype != np.float16 or data["mask"].dtype != np.float16
            or data["label"].shape != (n,) or data["seed"].shape != (n,) or len(meta) != n
            or data["label"].dtype.kind not in "iu" or data["seed"].dtype.kind not in "iu"
            or not np.isfinite(data["spec"]).all() or not np.isfinite(data["mask"]).all()):
        raise ValueError("invalid unknown array shapes, types, values or counts")
    pairs = list(zip(data["seed"].tolist(), data["label"].tolist()))
    if len(set(pairs)) != n or set(pairs) != {(seed, label) for seed in seeds for label in range(len(request["families"]))}:
        raise ValueError("unknown scenario/label pairs do not match request")
    for seed, label, record in zip(data["seed"], data["label"], meta):
        if (record["label"] != request["families"][label] or record["config"]["seed"] != int(seed)
                or record["config"]["bandwidth"] != request["bandwidth"]
                or record["protocol"] != PROTOCOL or record["test_only"] is not True
                or record["interferer"]["injection_point"] != "uplink"):
            raise ValueError("unknown metadata does not match observations")
    return {**data, "meta": meta}


def _verify_part(root, index, descriptor, request):
    part, metadata, _ = _paths(root, index)
    seeds = _expected_seeds(request, index)
    if (descriptor.get("part") != part.name or descriptor.get("meta") != metadata.name
            or descriptor.get("seeds") != seeds or descriptor.get("request_fingerprint") != _fingerprint(request)):
        raise ValueError("incompatible unknown shard descriptor")
    for path in (part, metadata):
        if not path.is_file() or descriptor.get("sha256", {}).get(path.name) != _file_hash(path):
            raise ValueError(f"missing or modified unknown artifact: {path}")
    data = _read_part(part, metadata, request, seeds)
    if descriptor.get("n_samples") != len(data["label"]):
        raise ValueError("wrong unknown shard sample count")
    return data


def generate_unknowns(out_dir, n_seeds: int = 6, first_seed: int = 900000,
                      bandwidth: float = 36e6, families=UNKNOWN_LABELS) -> None:
    """Generate immutable, resumable test-only shards; never add unknowns to A1."""
    request = _request(n_seeds, first_seed, bandwidth, families)
    root = Path(out_dir)
    request_path = root / "request.json"
    if request_path.exists():
        if json.loads(request_path.read_text()) != request:
            raise ValueError("unknown generation request changed; use a fresh output directory")
    elif root.exists() and any(root.iterdir()):
        raise ValueError("unverified unknown output directory; use a fresh directory")
    else:
        root.mkdir(parents=True, exist_ok=True)
        _atomic_json(request_path, request)
    n_shards = -(-n_seeds // SEEDS_PER_SHARD)
    _names(root, n_shards, False)
    if (root / "manifest.json").exists():
        manifest = read_unknown_manifest(root)
        print(f"reusing verified unknown dataset ({manifest['n_samples']} samples)", flush=True)
        return
    descriptors = []
    for index in range(n_shards):
        part, metadata, descriptor_path = _paths(root, index)
        if descriptor_path.exists():
            descriptor = json.loads(descriptor_path.read_text())
            _verify_part(root, index, descriptor, request)
        else:
            if part.exists() or metadata.exists():
                raise ValueError("unverified partial unknown shard; use a fresh output directory")
            arrays = {key: [] for key in ARRAY_KEYS}
            records = []
            for seed in _expected_seeds(request, index):
                for label, family in enumerate(request["families"]):
                    result = sample_unknown(family, bandwidth, seed)
                    arrays["spec"].append(result.spec_db.astype(np.float16))
                    arrays["mask"].append(result.mask_db.astype(np.float16))
                    arrays["label"].append(label)
                    arrays["seed"].append(seed)
                    records.append(result.meta)
            temporary_part, temporary_meta = part.with_suffix(".tmp.npz"), metadata.with_suffix(".jsonl.tmp")
            np.savez(temporary_part, spec=np.stack(arrays["spec"]), mask=np.stack(arrays["mask"]),
                     label=np.array(arrays["label"], np.int8), seed=np.array(arrays["seed"], np.int64))
            temporary_meta.write_text("".join(json.dumps(record, default=float, allow_nan=False) + "\n" for record in records))
            _read_part(temporary_part, temporary_meta, request, _expected_seeds(request, index))
            temporary_part.replace(part)
            temporary_meta.replace(metadata)
            descriptor = {"part": part.name, "meta": metadata.name, "seeds": _expected_seeds(request, index),
                          "request_fingerprint": _fingerprint(request), "n_samples": len(records),
                          "sha256": {path.name: _file_hash(path) for path in (part, metadata)}}
            _atomic_json(descriptor_path, descriptor)
        descriptors.append(descriptor)
    manifest = {"artifact_version": 1, "protocol": PROTOCOL, "test_only": True, "commit": _commit(),
                "families": request["families"], "labels": request["families"], "bandwidth": float(bandwidth),
                "n_seeds": n_seeds, "first_seed": first_seed,
                "scenario_seeds": list(range(first_seed, first_seed + n_seeds)),
                "n_samples": n_seeds * len(request["families"]),
                "per_family": {family: n_seeds for family in request["families"]},
                "request": request, "request_fingerprint": _fingerprint(request), "shards": descriptors}
    _atomic_json(root / "manifest.json", manifest)
    read_unknown_manifest(root)
    print(f"generated {manifest['n_samples']} unknown samples from {n_seeds} scenario seeds", flush=True)


def _inspect(path, collect):
    root = Path(path)
    try:
        manifest = json.loads((root / "manifest.json").read_text())
        request = manifest["request"]
        # Validate declared semantics without comparing historical source hashes
        # to currently checked-out code: old immutable artifacts remain readable.
        _positive_int(request["n_seeds"], "n_seeds")
        _seed(request["first_seed"], "first_seed")
        _seed(request["first_seed"] + request["n_seeds"] - 1, "last_seed")
        families = request["families"]
        if (request["protocol"] != PROTOCOL or request["test_only"] is not True
                or request["bandwidth"] not in (36e6, 72e6) or request["seeds_per_shard"] != SEEDS_PER_SHARD
                or not families or len(set(families)) != len(families) or any(f not in UNKNOWN_LABELS for f in families)):
            raise ValueError("unsupported unknown protocol request")
        n_shards = -(-request["n_seeds"] // SEEDS_PER_SHARD)
        if (manifest["artifact_version"] != 1 or manifest["protocol"] != PROTOCOL or manifest["test_only"] is not True
                or manifest["families"] != families or manifest["labels"] != families
                or manifest["bandwidth"] != request["bandwidth"] or manifest["n_seeds"] != request["n_seeds"]
                or manifest["first_seed"] != request["first_seed"]
                or manifest["scenario_seeds"] != list(range(request["first_seed"], request["first_seed"] + request["n_seeds"]))
                or manifest["request_fingerprint"] != _fingerprint(request)
                or json.loads((root / "request.json").read_text()) != request
                or len(manifest["shards"]) != n_shards):
            raise ValueError("inconsistent unknown manifest/request")
        _names(root, n_shards, True)
        arrays, records = {key: [] for key in ARRAY_KEYS}, []
        for index, descriptor in enumerate(manifest["shards"]):
            if json.loads(_paths(root, index)[2].read_text()) != descriptor:
                raise ValueError("unknown shard descriptor differs from manifest")
            data = _verify_part(root, index, descriptor, request)
            if collect:
                for key in ARRAY_KEYS:
                    arrays[key].append(data[key])
                records.extend(data["meta"])
        if (manifest["n_samples"] != request["n_seeds"] * len(families)
                or manifest["per_family"] != {family: request["n_seeds"] for family in families}):
            raise ValueError("wrong unknown manifest sample counts")
        data = None
        if collect:
            data = {key: np.concatenate(parts) for key, parts in arrays.items()}
            data.update(meta=records, family=np.array([families[label] for label in data["label"]]))
        return manifest, data, _fingerprint(manifest)
    except (OSError, KeyError, TypeError, ValueError, IndexError, BadZipFile) as error:
        raise ValueError(f"invalid unknown dataset {root}: {error}") from error


def load_unknowns(path) -> dict:
    return _inspect(path, True)[1]


def read_unknown_manifest(path) -> dict:
    return _inspect(path, False)[0]


def unknown_fingerprint(path) -> str:
    return _inspect(path, False)[2]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", required=True)
    parser.add_argument("--n-seeds", type=int, default=6)
    parser.add_argument("--first-seed", type=int, default=900000)
    parser.add_argument("--bandwidth", type=float, default=36e6, choices=(36e6, 72e6))
    parser.add_argument("--families", nargs="+", choices=UNKNOWN_LABELS, default=list(UNKNOWN_LABELS))
    args = parser.parse_args(argv)
    try:
        generate_unknowns(args.out, args.n_seeds, args.first_seed, args.bandwidth, args.families)
    except ValueError as error:
        parser.exit(2, f"error: {error}\n")


if __name__ == "__main__":
    main()

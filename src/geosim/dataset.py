"""Stage-A dataset splits and generation (protocol: docs/plan/P5_veri_protokol.md).

    python -m geosim.dataset --out data/stageA --workers 4            # everything
    python -m geosim.dataset --out data/pilot --limit-seeds 10        # quick pilot
    python -m geosim.dataset --protocol R1-eval/1 --out data/r1       # test-only robustness splits

A1 is frozen. R1-eval/1 (docs/plan/P17_r1_robustness_eval.md) adds test-only
splits with their own seed ranges and protocol name; it does not change A1.

Each split is a directory of shards: part-XXXXX.npz (spec, mask, label, seed) and
meta-XXXXX.jsonl (one JSON object per sample), plus manifest.json. Finished shards are skipped
on re-run, so generation can be interrupted and resumed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import time
from zipfile import BadZipFile
from dataclasses import asdict, dataclass, replace
from multiprocessing import Pool
from pathlib import Path

import numpy as np

from .classes import DEFAULT_RANGES, LABELS, sample
from .interferers import InfeasibleCarrierError

PROTOCOL = "A1, frozen 2026-10-09"
SEEDS_PER_SHARD = 100
ALL5 = LABELS
NO_OVERDRIVE = tuple(lab for lab in LABELS if lab != "overdrive")
ID_NOMINAL, ID_OVERDRIVE = ((9.0, 13.0),), ((1.0, 4.0),)


@dataclass(frozen=True)
class Split:
    name: str
    first_seed: int
    n_seeds: int
    bandwidth: float = 36e6
    amplifier: str = "dvbs2_nl"
    linear: bool = False
    labels: tuple = ALL5
    ibo_nominal: tuple = ID_NOMINAL          # union of intervals, dB
    ibo_overdrive: tuple = ID_OVERDRIVE

    @property
    def seeds(self) -> range:
        return range(self.first_seed, self.first_seed + self.n_seeds)


SPLITS = {s.name: s for s in (
    Split("train_nl", 100_000, 2000),
    Split("train_lin", 100_000, 2000, linear=True, labels=NO_OVERDRIVE),
    Split("val_nl", 200_000, 300),
    Split("val_lin", 200_000, 300, linear=True, labels=NO_OVERDRIVE),
    Split("test_id_nl", 300_000, 500),
    Split("test_id_lin", 300_000, 500, linear=True, labels=NO_OVERDRIVE),
    Split("test_ibo", 310_000, 300, ibo_nominal=((8.0, 9.0), (13.0, 14.0)), ibo_overdrive=((0.0, 1.0), (4.0, 5.0))),
    Split("test_bw72", 320_000, 300, bandwidth=72e6),
    Split("test_amp_lin", 330_000, 300, amplifier="dvbs2_lin"),
    Split("test_amp_saleh", 340_000, 300, amplifier="saleh"),
)}

# Test-only robustness splits. Each changes one condition against test_id_nl.
R1_PROTOCOL = "R1-eval/1"
R1_SPLITS = {s.name: s for s in (
    Split("r1_ibo_sweep", 400_000, 300, ibo_nominal=((5.0, 14.0),), ibo_overdrive=((0.0, 5.0),)),
    Split("r1_amp_rapp", 410_000, 300, amplifier="rapp_p2"),
    Split("r1_amp_opendpd_apa", 420_000, 300, amplifier="opendpd_apa", labels=NO_OVERDRIVE),
    Split("r1_amp_opendpd_dpa", 430_000, 300, amplifier="opendpd_dpa", labels=NO_OVERDRIVE),
)}
PROTOCOLS = {PROTOCOL: SPLITS, R1_PROTOCOL: R1_SPLITS}


def _pick(rng: np.random.Generator, intervals: tuple) -> tuple:
    """One interval of a union, chosen with probability proportional to its length."""
    w = np.array([hi - lo for lo, hi in intervals])
    return intervals[rng.choice(len(intervals), p=w / w.sum())]


def ranges_for(split: Split, seed: int):
    rng = np.random.default_rng([seed, 303])
    return replace(DEFAULT_RANGES, ibo_nominal_db=_pick(rng, split.ibo_nominal),
                   ibo_overdrive_db=_pick(rng, split.ibo_overdrive))


def generate_seed(split: Split, seed: int) -> list:
    """All labelled samples of one seed; a label is skipped when it cannot be realised."""
    out = []
    for label in split.labels:
        try:
            out.append(sample(label, split.bandwidth, seed, ranges_for(split, seed), linear=split.linear,
                              amplifier=split.amplifier))
        except InfeasibleCarrierError:         # only physically infeasible unauthorized scenes may be skipped
            if label != "unauthorized":
                raise
    return out


ARTIFACT_VERSION = 2
ARRAY_KEYS = ("spec", "mask", "label", "seed")


def _canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _fingerprint(value) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _atomic_json(path: Path, value) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=1, allow_nan=False))
    temporary.replace(path)


def _generator_provenance() -> dict:
    """Fingerprint source and bundled reference data, including uncommitted edits."""
    root = Path(__file__).parent
    files = sorted(root.glob("*.py")) + sorted((root / "data").glob("*"))
    return {str(p.relative_to(root)): _file_hash(p) for p in files if p.is_file()}


def _request(split: Split, seeds: list[int], protocol: str = PROTOCOL) -> dict:
    return json.loads(_canonical({"protocol": protocol, "split": asdict(split),
                                 "labels": list(LABELS), "seeds": seeds,
                                 "seeds_per_shard": SEEDS_PER_SHARD,
                                 "generator": _generator_provenance(),
                                 "numpy_version": np.__version__}))


def _read_shard(part: Path, meta_path: Path, split: dict, allowed_seeds: list[int]) -> dict:
    try:
        with np.load(part, allow_pickle=False) as stored:
            if set(stored.files) != set(ARRAY_KEYS):
                raise ValueError("unexpected array keys")
            d = {k: stored[k] for k in ARRAY_KEYS}
        meta = [json.loads(line) for line in meta_path.read_text().splitlines()]
        n = len(d["label"])
        if not n or d["spec"].shape != (n, 128, 512) or d["mask"].shape != (n, 512):
            raise ValueError("invalid spectrum/mask dimensions or empty shard")
        if d["spec"].dtype != np.float16 or d["mask"].dtype != np.float16:
            raise ValueError("stored spectra and masks must be float16")
        if d["label"].shape != (n,) or d["seed"].shape != (n,) or len(meta) != n:
            raise ValueError("array/metadata lengths differ")
        if d["label"].dtype.kind not in "iu" or d["seed"].dtype.kind not in "iu":
            raise ValueError("labels and seeds must be integer arrays")
        if not np.isfinite(d["spec"]).all() or not np.isfinite(d["mask"]).all():
            raise ValueError("nonfinite observations")
        pairs = list(zip(d["seed"].tolist(), d["label"].tolist()))
        if len(set(pairs)) != n or set(d["seed"].tolist()) != set(allowed_seeds):
            raise ValueError("duplicate samples or unexpected scenario seed groups")
        required_labels = {LABELS.index(lab) for lab in split["labels"] if lab != "unauthorized"}
        for seed in allowed_seeds:
            if not required_labels <= set(d["label"][d["seed"] == seed].tolist()):
                raise ValueError("missing required label for a scenario seed")
        for seed, label, m in zip(d["seed"], d["label"], meta):
            if label < 0 or label >= len(LABELS) or LABELS[label] not in split["labels"]:
                raise ValueError("label outside declared taxonomy")
            cfg = m["config"]
            if m["label"] != LABELS[label] or cfg["seed"] != int(seed):
                raise ValueError("metadata label/seed does not match arrays")
            if any(cfg[k] != split[k] for k in ("bandwidth", "amplifier", "linear")):
                raise ValueError("metadata physical configuration does not match split")
        return {**d, "meta": meta}
    except (OSError, KeyError, TypeError, ValueError, IndexError, BadZipFile) as exc:
        raise ValueError(f"Invalid dataset shard {part}: {exc}") from exc


def _shard_paths(directory: Path, shard: int):
    return (directory / f"part-{shard:05d}.npz", directory / f"meta-{shard:05d}.jsonl",
            directory / f"shard-{shard:05d}.json")


def _verify_shard(directory: Path, descriptor: dict, request: dict, shard: int) -> dict:
    part, meta_path, index = _shard_paths(directory, shard)
    expected_seeds = request["seeds"][shard * SEEDS_PER_SHARD:(shard + 1) * SEEDS_PER_SHARD]
    if (descriptor.get("part") != part.name or descriptor.get("meta") != meta_path.name
            or descriptor.get("seeds") != expected_seeds
            or descriptor.get("request_fingerprint") != _fingerprint(request)):
        raise ValueError(f"Incompatible shard descriptor: {index}")
    for path in (part, meta_path):
        if not path.is_file() or descriptor.get("sha256", {}).get(path.name) != _file_hash(path):
            raise ValueError(f"Missing or modified dataset artifact: {path}")
    d = _read_shard(part, meta_path, request["split"], expected_seeds)
    if descriptor.get("n_samples") != len(d["label"]):
        raise ValueError(f"Wrong shard sample count: {part}")
    return d


def _write_shard(args) -> dict:
    split, shard, seeds, out_dir, request = args
    directory = Path(out_dir) / split.name
    part, meta_path, index = _shard_paths(directory, shard)
    if index.exists():
        descriptor = json.loads(index.read_text())
        _verify_shard(directory, descriptor, request, shard)
        return descriptor
    if part.exists() or meta_path.exists():
        raise ValueError(f"Unverified partial shard in {directory}; use a fresh output directory")
    spec, mask, label, seed_col, metas = [], [], [], [], []
    for seed in seeds:
        for r in generate_seed(split, seed):
            spec.append(r.spec_db.astype(np.float16))
            mask.append(r.mask_db.astype(np.float16))
            label.append(LABELS.index(r.meta["label"]))
            seed_col.append(seed)
            metas.append(r.meta)
    if not label:
        raise ValueError(f"No realizable samples for {split.name}, shard {shard}")
    temporary_meta = meta_path.with_suffix(".jsonl.tmp")
    temporary_meta.write_text("".join(json.dumps(m, default=float, allow_nan=False) + "\n" for m in metas))
    temporary_part = part.with_suffix(".tmp.npz")
    np.savez(temporary_part, spec=np.stack(spec), mask=np.stack(mask), label=np.array(label, np.int8),
             seed=np.array(seed_col, np.int64))
    _read_shard(temporary_part, temporary_meta, request["split"], seeds)
    temporary_meta.replace(meta_path)
    temporary_part.replace(part)
    descriptor = {"part": part.name, "meta": meta_path.name, "seeds": seeds,
                  "n_samples": len(label), "request_fingerprint": _fingerprint(request),
                  "sha256": {p.name: _file_hash(p) for p in (part, meta_path)}}
    _atomic_json(index, descriptor)
    return descriptor


def _commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True,
                              cwd=Path(__file__).parent).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def _check_names(directory: Path, n_shards: int, *, complete: bool) -> None:
    for pattern, template in (("part-*.npz", "part-{i:05d}.npz"),
                              ("meta-*.jsonl", "meta-{i:05d}.jsonl"),
                              ("shard-*.json", "shard-{i:05d}.json")):
        expected = {template.format(i=i) for i in range(n_shards)}
        actual = {p.name for p in directory.glob(pattern) if not p.name.endswith(".tmp.npz")}
        if not actual <= expected or (complete and actual != expected):
            raise ValueError(f"Unexpected or missing dataset files in {directory}: {pattern}")


def generate(out_dir: str, names=None, workers: int = 1, limit_seeds: int | None = None,
             protocol: str = PROTOCOL) -> None:
    if not isinstance(workers, int) or isinstance(workers, bool) or workers < 1:
        raise ValueError("workers must be a positive integer")
    if limit_seeds is not None and (not isinstance(limit_seeds, int) or isinstance(limit_seeds, bool)
                                    or limit_seeds < 1):
        raise ValueError("limit_seeds must be a positive integer or None")
    if protocol not in PROTOCOLS:
        raise ValueError(f"protocol must be one of {list(PROTOCOLS)}")
    splits = PROTOCOLS[protocol]
    names = list(splits) if names is None else list(names)
    if not names or len(set(names)) != len(names) or any(n not in splits for n in names):
        raise ValueError(f"names must be nonempty, unique split names of {protocol}")
    for name in names:
        split = splits[name]
        seeds = list(split.seeds)[:limit_seeds]
        request = _request(split, seeds, protocol)
        directory = Path(out_dir) / name
        request_path = directory / "request.json"
        if request_path.exists():
            if json.loads(request_path.read_text()) != request:
                raise ValueError(f"Dataset request changed in {directory}; use a fresh output directory")
        elif directory.exists() and any(directory.iterdir()):
            raise ValueError(f"Legacy/unverified dataset in {directory}; use a fresh output directory")
        else:
            directory.mkdir(parents=True, exist_ok=True)
            _atomic_json(request_path, request)
        n_shards = -(-len(seeds) // SEEDS_PER_SHARD)
        _check_names(directory, n_shards, complete=False)
        if (directory / "manifest.json").exists():
            # A verified completed artifact is immutable. In particular, a later
            # docs-only commit must not rewrite its original generation revision.
            manifest = read_manifest(directory)
            print(f"{name}: reusing verified dataset ({manifest['n_samples']} samples)", flush=True)
            continue
        jobs = [(split, i, seeds[j:j + SEEDS_PER_SHARD], out_dir, request)
                for i, j in enumerate(range(0, len(seeds), SEEDS_PER_SHARD))]
        t = time.time()
        if workers > 1:
            with Pool(workers) as pool:
                done = pool.map(_write_shard, jobs, chunksize=1)
        else:
            done = [_write_shard(j) for j in jobs]
        labels = []
        for i, descriptor in enumerate(done):
            labels.extend(_verify_shard(directory, descriptor, request, i)["label"].tolist())
        counts = {lab: labels.count(i) for i, lab in enumerate(LABELS) if lab in split.labels}
        manifest = {"artifact_version": ARTIFACT_VERSION, "protocol": protocol, "commit": _commit(),
                    "split": request["split"], "n_seeds": len(seeds), "scenario_seeds": seeds,
                    "n_samples": len(labels), "per_label": counts, "labels": list(LABELS),
                    "complete": len(seeds) == split.n_seeds,
                    "request": request, "request_fingerprint": _fingerprint(request), "shards": done}
        _atomic_json(directory / "manifest.json", manifest)
        print(f"{name}: {len(labels)} samples from {len(seeds)} seeds in {time.time() - t:.0f} s  {counts}", flush=True)


def _inspect_split(path: Path, *, collect: bool):
    try:
        manifest = json.loads((path / "manifest.json").read_text())
        split = manifest["split"]
        protocol = manifest["protocol"]
        if protocol not in PROTOCOLS or manifest["labels"] != list(LABELS):
            raise ValueError("unsupported protocol or label order")
        splits = PROTOCOLS[protocol]
        if split["name"] not in splits or split != json.loads(_canonical(asdict(splits[split["name"]]))):
            raise ValueError(f"split configuration does not match {protocol}")
        n_seeds = manifest["n_seeds"]
        if not isinstance(n_seeds, int) or isinstance(n_seeds, bool) or not 1 <= n_seeds <= split["n_seeds"]:
            raise ValueError("invalid scenario seed count")
        seeds = list(splits[split["name"]].seeds)[:n_seeds]
        n_shards = -(-n_seeds // SEEDS_PER_SHARD)
        arrays = {k: [] for k in ARRAY_KEYS}
        meta, labels, content_hashes = [], [], {}
        version = manifest.get("artifact_version", 1)
        if version not in (1, ARTIFACT_VERSION):
            raise ValueError("unsupported artifact version")
        if version == ARTIFACT_VERSION:
            request = manifest["request"]
            if (request["protocol"] != protocol or request["split"] != split or request["seeds"] != seeds
                    or request["labels"] != list(LABELS) or request["seeds_per_shard"] != SEEDS_PER_SHARD
                    or manifest["request_fingerprint"] != _fingerprint(request)
                    or json.loads((path / "request.json").read_text()) != request
                    or manifest["scenario_seeds"] != seeds
                    or manifest["complete"] != (n_seeds == split["n_seeds"])
                    or len(manifest["shards"]) != n_shards):
                raise ValueError("inconsistent request/manifest")
            _check_names(path, n_shards, complete=True)
        else:
            # Legacy data have no historical checksums. Validate their contents but never resume them.
            if protocol != PROTOCOL:
                raise ValueError("legacy artifacts exist only for A1")
            if not isinstance(manifest["complete"], bool) or (manifest["complete"] and n_seeds != split["n_seeds"]):
                raise ValueError("invalid legacy completeness flag")
            for pattern, template in (("part-*.npz", "part-{i:05d}.npz"), ("meta-*.jsonl", "meta-{i:05d}.jsonl")):
                if {p.name for p in path.glob(pattern)} != {template.format(i=i) for i in range(n_shards)}:
                    raise ValueError("unexpected legacy shard files")
        for i in range(n_shards):
            part, meta_path, index = _shard_paths(path, i)
            if version == ARTIFACT_VERSION:
                descriptor = manifest["shards"][i]
                if descriptor != json.loads(index.read_text()):
                    raise ValueError("shard index differs from manifest")
                d = _verify_shard(path, descriptor, request, i)
                content_hashes.update(descriptor["sha256"])
            else:
                d = _read_shard(part, meta_path, split, seeds[i * SEEDS_PER_SHARD:(i + 1) * SEEDS_PER_SHARD])
                content_hashes.update({p.name: _file_hash(p) for p in (part, meta_path)})
            labels.extend(d["label"].tolist())
            if collect:
                for key in ARRAY_KEYS:
                    arrays[key].append(d[key])
                meta.extend(d["meta"])
        expected_counts = {lab: labels.count(i) for i, lab in enumerate(LABELS) if lab in split["labels"]}
        if manifest["n_samples"] != len(labels) or manifest["per_label"] != expected_counts:
            raise ValueError("manifest sample counts do not match shards")
        data = {**{k: np.concatenate(v) for k, v in arrays.items()}, "meta": meta} if collect else None
        return manifest, data, _fingerprint({"manifest": manifest, "contents": content_hashes})
    except (OSError, KeyError, TypeError, ValueError, IndexError) as exc:
        raise ValueError(f"Invalid dataset {path}: {exc}") from exc


def read_manifest(path: str | Path) -> dict:
    """Read metadata only after validating all referenced shards and checksums."""
    return _inspect_split(Path(path), collect=False)[0]


def split_fingerprint(path: str | Path) -> str:
    """Validated content identity for dataset/checkpoint compatibility."""
    return _inspect_split(Path(path), collect=False)[2]


def load_split(path: str | Path) -> dict:
    """Load a validated A1 split; old manifests are structurally checked, never rewritten."""
    return _inspect_split(Path(path), collect=True)[1]


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True)
    ap.add_argument("--protocol", choices=list(PROTOCOLS), default=PROTOCOL)
    ap.add_argument("--splits", nargs="*", choices=[name for splits in PROTOCOLS.values() for name in splits])
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--limit-seeds", type=int)
    a = ap.parse_args()
    generate(a.out, a.splits, a.workers, a.limit_seeds, a.protocol)

"""Stage-A dataset splits and generation (protocol: docs/plan/P5_veri_protokol.md).

    python -m geosim.dataset --out data/stageA --workers 4            # everything
    python -m geosim.dataset --out data/pilot --limit-seeds 10        # quick pilot

Each split is a directory of shards: part-XXXXX.npz (spec, mask, label, seed) and
meta-XXXXX.jsonl (one JSON object per sample), plus manifest.json. Finished shards are skipped
on re-run, so generation can be interrupted and resumed.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import time
from dataclasses import asdict, dataclass, replace
from multiprocessing import Pool
from pathlib import Path

import numpy as np

from .classes import DEFAULT_RANGES, LABELS, sample

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
        except ValueError:                    # no free gap for an unauthorized carrier
            continue
    return out


def _write_shard(args) -> dict:
    split, shard, seeds, out_dir = args
    part = Path(out_dir) / split.name / f"part-{shard:05d}.npz"
    meta_path = part.with_name(f"meta-{shard:05d}.jsonl")
    if part.exists() and meta_path.exists():
        with np.load(part) as d:
            return {"shard": shard, "labels": d["label"].tolist(), "skipped": True}
    t = time.time()
    spec, mask, label, seed_col, metas = [], [], [], [], []
    for seed in seeds:
        for r in generate_seed(split, seed):
            spec.append(r.spec_db.astype(np.float16))
            mask.append(r.mask_db.astype(np.float16))
            label.append(LABELS.index(r.meta["label"]))
            seed_col.append(seed)
            metas.append(r.meta)
    part.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text("".join(json.dumps(m, default=float) + "\n" for m in metas))
    tmp = part.with_suffix(".tmp.npz")
    np.savez(tmp, spec=np.stack(spec), mask=np.stack(mask), label=np.array(label, np.int8),
             seed=np.array(seed_col, np.int64))
    tmp.rename(part)                          # the shard appears only when complete
    return {"shard": shard, "labels": label, "seconds": time.time() - t, "skipped": False}


def _commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True,
                              cwd=Path(__file__).parent).stdout.strip()
    except Exception:
        return "unknown"


def generate(out_dir: str, names=None, workers: int = 1, limit_seeds: int | None = None) -> None:
    for name in names or SPLITS:
        split = SPLITS[name]
        seeds = list(split.seeds)[:limit_seeds]
        jobs = [(split, i, seeds[j:j + SEEDS_PER_SHARD], out_dir)
                for i, j in enumerate(range(0, len(seeds), SEEDS_PER_SHARD))]
        t = time.time()
        if workers > 1:
            with Pool(workers) as pool:
                done = pool.map(_write_shard, jobs, chunksize=1)
        else:
            done = [_write_shard(j) for j in jobs]
        labels = np.concatenate([np.array(d["labels"], int) for d in done])
        counts = {lab: int((labels == i).sum()) for i, lab in enumerate(LABELS) if lab in split.labels}
        manifest = {"protocol": PROTOCOL, "commit": _commit(), "split": asdict(split), "n_seeds": len(seeds),
                    "n_samples": int(len(labels)), "per_label": counts, "labels": list(LABELS),
                    "complete": limit_seeds is None}
        (Path(out_dir) / name / "manifest.json").write_text(json.dumps(manifest, indent=1))
        print(f"{name}: {len(labels)} samples from {len(seeds)} seeds in {time.time() - t:.0f} s  {counts}", flush=True)


def load_split(path: str) -> dict:
    """Concatenate a split's shards: spec, mask, label, seed arrays and a list of meta dicts."""
    path = Path(path)
    parts = sorted(path.glob("part-*.npz"))
    arrays = {k: [] for k in ("spec", "mask", "label", "seed")}
    meta = []
    for p in parts:
        with np.load(p) as d:
            for k in arrays:
                arrays[k].append(d[k])
        meta += [json.loads(line) for line in p.with_name(p.name.replace("part", "meta").replace(".npz", ".jsonl"))
                 .read_text().splitlines()]
    return {**{k: np.concatenate(v) for k, v in arrays.items()}, "meta": meta}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True)
    ap.add_argument("--splits", nargs="*", choices=list(SPLITS))
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--limit-seeds", type=int)
    a = ap.parse_args()
    generate(a.out, a.splits, a.workers, a.limit_seeds)

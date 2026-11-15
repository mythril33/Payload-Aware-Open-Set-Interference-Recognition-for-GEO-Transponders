"""Campaign 3 (experiments/PREREGISTRATION_V3.md, part B).

Per seed: the shared-seed Objectosphere arms with the Mahalanobis shrinkage
sweep (stage arm_control) and the seen-device counterfactual (stage
split_counterfactual). Writes, under --out:

    raw/<stage>_seed<k>.json   full stage results (per-frame scores included)
    <stage>_seed<k>.json       the same without the score arrays (committed)
    aggregate.json             per-seed metrics, mean/sd/min/max, H7s / H9 / H10
                               paired differences, the checks, provenance
    aggregate_summary.md       the same as a table (generated)

Usage:
    .venv/bin/python experiments/run_campaign3.py --scale full --seeds 0 1 2 3 4 5 6 7 8 9

A stage whose raw file already exists is loaded instead of rerun (--no-resume
turns that off), so a restarted machine continues where it stopped; results
are deterministic, so a loaded stage equals a rerun one. A stage that raises
is recorded under "failures" and never hidden.
"""

from __future__ import annotations

import argparse
import copy
import json
import math
import platform
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np
import torch

from rfml import experiments as ex
from rfml import experiments_v3 as v3

STAGES = ("arm_control", "split_counterfactual")
ARMS = tuple(name for name, _classes, _offset in ex.SCORER_BENCH_ARMS)
SWEEP_KEYS = tuple(f"CE+mahalanobis@{s:g}" for s in v3.SHRINKAGE_SWEEP)


def _arm_metrics() -> dict:
    out = {}
    for arm in ARMS:
        out[f"{arm}:auroc"] = lambda r, a=arm: r["variants"][a]["report"]["auroc"]
        out[f"{arm}:unk_reject"] = lambda r, a=arm: r["variants"][a]["report"]["unknown_reject_rate"]
        for cls in ex.UNKNOWN:
            out[f"{arm}:reject_{cls}"] = (
                lambda r, a=arm, c=cls: r["variants"][a]["per_unknown_class"][c]["reject_rate"]
            )
    out["CE+distance:auroc"] = lambda r: r["variants"]["CE+distance"]["report"]["auroc"]
    for key in SWEEP_KEYS:
        out[f"{key}:auroc"] = lambda r, k=key: r["variants"][k]["report"]["auroc"]
    return out


def _split_metrics() -> dict:
    out = {}
    for model in ex.MODULATION_MODELS:
        out[f"{model}:train_acc"] = lambda r, m=model: r["models"][m]["train_accuracy"]
        out[f"{model}:unseen_acc"] = lambda r, m=model: r["models"][m]["unseen_devices"]["overall"]["accuracy"]
        out[f"{model}:seen_acc"] = (
            lambda r, m=model: r["models"][m]["seen_devices_new_frames"]["overall"]["accuracy"]
        )
    return out


METRICS = {"arm_control": _arm_metrics(), "split_counterfactual": _split_metrics()}

# Pre-registered paired per-seed differences (a - b, predicted > 0).
HYPOTHESES = {
    "H7s_pamarm_minus_pskarm_4pam_reject_shared_seed": (
        "arm_control", "OS-8PAM+MSP:reject_4PAM", "arm_control", "OS-16PSK+MSP:reject_4PAM"),
    "H9_mlp_seen_minus_unseen_acc": (
        "split_counterfactual", "MLP:seen_acc", "split_counterfactual", "MLP:unseen_acc"),
    "H10_cnn_seen_minus_unseen_acc": (
        "split_counterfactual", "CNN1D:seen_acc", "split_counterfactual", "CNN1D:unseen_acc"),
}


def required_positive(n_seeds: int) -> int:
    """Pre-registered criterion: the predicted sign in at least 80% of the seeds (8 of 10, 4 of 5)."""
    return math.ceil(0.8 * n_seeds)


def run_stage(stage: str, scale: ex.Scale, seed: int) -> dict:
    def progress(msg: str) -> None:
        print(f"[seed {seed}] {stage}: {msg}", flush=True)

    if stage == "arm_control":
        return v3.run_arm_control(scale, seed, progress=progress)
    if stage == "split_counterfactual":
        return v3.run_split_counterfactual(scale, seed, progress=progress)
    raise ValueError(f"unknown stage {stage!r}")


def slim(result: dict) -> dict:
    out = copy.deepcopy(result)
    for variant in out.get("variants", {}).values():
        variant.pop("scores", None)
    return out


def summarize(values: list[float]) -> dict:
    arr = np.asarray(values, dtype=np.float64)
    return {
        "per_seed": [float(v) for v in arr],
        "mean": float(arr.mean()),
        "sd": float(arr.std(ddof=1)) if arr.size > 1 else None,
        "min": float(arr.min()),
        "max": float(arr.max()),
    }


def provenance(scale: ex.Scale, seeds: list[int], started_utc: str) -> dict:
    try:
        rev = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        rev = None
    return {
        "git_commit": rev,
        "python": platform.python_version(),
        "torch": torch.__version__,
        "numpy": np.__version__,
        "torch_threads": torch.get_num_threads(),
        "scale": ex._scale_dict(scale),
        "seeds": seeds,
        "arm_shared_offset": v3.ARM_SHARED_OFFSET,
        "shrinkage_sweep": list(v3.SHRINKAGE_SWEEP),
        "seen_frames_per_device_per_snr": v3.SEEN_FRAMES_PER_DEVICE,
        "started_utc": started_utc,
    }


def write_summary_md(aggregate: dict, path: Path) -> None:
    prov = aggregate["provenance"]
    lines = [
        "# Campaign 3 summary (generated by run_campaign3.py — do not edit)",
        "",
        f"Scale `{prov['scale']['name']}`, seeds {prov['seeds']}, commit `{prov['git_commit']}`.",
        "",
        "| stage | metric | mean | sd | min | max |",
        "|---|---|---|---|---|---|",
    ]
    for stage, metrics in aggregate["metrics"].items():
        for name, s in metrics.items():
            sd = f"{s['sd']:.3f}" if s["sd"] is not None else "-"
            lines.append(f"| {stage} | {name} | {s['mean']:.3f} | {sd} | {s['min']:.3f} | {s['max']:.3f} |")
    lines += ["", "## Pre-registered paired differences (a - b, predicted > 0)", ""]
    lines += ["| hypothesis | per-seed diff | mean | positive seeds | required | supported |", "|---|---|---|---|---|---|"]
    for name, h in aggregate["hypotheses"].items():
        per_seed = ", ".join(f"{v:+.3f}" for v in h["per_seed_diff"])
        lines.append(
            f"| {name} | {per_seed} | {h['mean_diff']:+.3f} | {h['n_positive']}/{h['n_seeds']} "
            f"| {h['required_positive']} | {h['supported']} |"
        )
    if aggregate["failures"]:
        lines += ["", "## Failures", ""]
        lines += [f"- seed {f['seed']} {f['stage']}: {f['error']}" for f in aggregate["failures"]]
    lines += ["", f"Total wall time of this invocation: {aggregate['wall_time_s']:.0f} s", ""]
    path.write_text("\n".join(lines))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seeds", type=int, nargs="+", default=list(range(10)))
    ap.add_argument("--scale", default="full", choices=sorted(ex.SCALES))
    ap.add_argument("--out", type=Path, default=ROOT / "experiments" / "campaign3")
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--no-resume", action="store_true", help="rerun stages whose raw file already exists")
    args = ap.parse_args()

    started_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    torch.set_num_threads(args.threads)
    scale = ex.get_scale(args.scale)
    out: Path = args.out
    (out / "raw").mkdir(parents=True, exist_ok=True)
    # Provenance is taken now, so the recorded commit is the one the run started from.
    prov = provenance(scale, list(args.seeds), started_utc)

    t0 = time.perf_counter()
    results: dict[str, dict[int, dict]] = {s: {} for s in STAGES}
    failures: list[dict] = []
    for seed in args.seeds:
        for stage in STAGES:
            raw_path = out / "raw" / f"{stage}_seed{seed}.json"
            if raw_path.exists() and not args.no_resume:
                loaded = json.loads(raw_path.read_text())
                if loaded.get("scale", {}).get("name") == scale.name and loaded.get("seed") == seed:
                    results[stage][seed] = loaded
                    print(f"[seed {seed}] {stage}: loaded {raw_path.name}", flush=True)
                    continue
            t = time.perf_counter()
            try:
                r = run_stage(stage, scale, seed)
            except Exception as exc:  # noqa: BLE001 — any failure is recorded, never hidden (pre-registration rule)
                failures.append({"seed": seed, "stage": stage, "error": f"{type(exc).__name__}: {exc}"})
                print(f"[seed {seed}] {stage}: FAILED {exc}", flush=True)
                continue
            r["campaign"] = {"stage_wall_time_s": round(time.perf_counter() - t, 1)}
            raw_path.write_text(ex.to_strict_json(r))
            (out / f"{stage}_seed{seed}.json").write_text(ex.to_strict_json(slim(r)))
            results[stage][seed] = r
            print(f"[seed {seed}] {stage}: done in {r['campaign']['stage_wall_time_s']} s", flush=True)

    aggregate: dict = {
        "provenance": prov,
        "metrics": {},
        "hypotheses": {},
        "failures": failures,
    }
    for stage, metrics in METRICS.items():
        seeds_done = sorted(results[stage])
        if seeds_done:
            aggregate["metrics"][stage] = {
                name: summarize([fn(results[stage][s]) for s in seeds_done]) for name, fn in metrics.items()
            }
    for name, (st_a, m_a, st_b, m_b) in HYPOTHESES.items():
        seeds_done = sorted(set(results[st_a]) & set(results[st_b]))
        if not seeds_done:
            continue
        diffs = [
            float(METRICS[st_a][m_a](results[st_a][s]) - METRICS[st_b][m_b](results[st_b][s]))
            for s in seeds_done
        ]
        n_pos = sum(d > 0 for d in diffs)
        need = required_positive(len(diffs))
        aggregate["hypotheses"][name] = {
            "seeds": seeds_done,
            "per_seed_diff": diffs,
            "mean_diff": float(np.mean(diffs)),
            "sd_diff": float(np.std(diffs, ddof=1)) if len(diffs) > 1 else None,
            "n_positive": n_pos,
            "n_seeds": len(diffs),
            "required_positive": need,
            # The verdict is defined for the pre-registered seed counts only.
            "supported": bool(n_pos >= need) if len(diffs) in (5, 10) else None,
        }
    aggregate["wall_time_s"] = round(time.perf_counter() - t0, 1)

    (out / "aggregate.json").write_text(json.dumps(aggregate, indent=2, allow_nan=False))
    write_summary_md(aggregate, out / "aggregate_summary.md")
    print(f"campaign 3 done in {aggregate['wall_time_s']} s; failures: {len(failures)}", flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

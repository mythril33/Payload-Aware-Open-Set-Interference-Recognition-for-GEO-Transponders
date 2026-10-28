"""Multi-seed campaign over the rfml experiment stages.

Runs the pre-registered design in experiments/PREREGISTRATION.md: for each
seed, the modulation stage (impaired and ideal), both fingerprint runs and the
open-set stage, all on the chosen scale preset. Writes, under --out:

    raw/<stage>_seed<k>.json   full stage results (includes per-frame scores)
    <stage>_seed<k>.json       same minus bulky arrays (committed to Git)
    aggregate.json             per-seed metric table, mean/sd/min/max, paired
                               per-seed differences for H1-H4, provenance
    aggregate_summary.md       the same as a readable table

Usage:
    .venv/bin/python experiments/run_campaign.py --scale full --seeds 0 1 2 3 4
    .venv/bin/python experiments/run_campaign.py --scale quick --seeds 0 1 \
        --out experiments/campaign_smoke        # smoke test

Re-running with the same arguments reproduces the same JSON numbers (torch
CPU, fixed thread count). A stage that raises is recorded under "failures"
and does not abort the campaign: the pre-registration forbids hiding it.
"""

from __future__ import annotations

import argparse
import copy
import json
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

# Metric extractors: stage name -> {metric name: callable(result) -> float|None}.
# Kept flat and explicit so the aggregate is auditable against the raw JSON.
METRICS = {
    "modulation": {
        "cnn_overall_acc": lambda r: r["models"]["CNN1D"]["overall"]["accuracy"],
        "cnn_train_acc": lambda r: r["models"]["CNN1D"]["train_accuracy"],
        "mlp_overall_acc": lambda r: r["models"]["MLP"]["overall"]["accuracy"],
        "mlp_train_acc": lambda r: r["models"]["MLP"]["train_accuracy"],
    },
    "modulation_ideal": {
        "cnn_overall_acc": lambda r: r["models"]["CNN1D"]["overall"]["accuracy"],
        "mlp_overall_acc": lambda r: r["models"]["MLP"]["overall"]["accuracy"],
    },
    "fingerprint": {
        "test_acc": lambda r: r["overall"]["accuracy"],
        "test_n": lambda r: r["overall"]["n"],
    },
    "fingerprint_ideal": {
        "test_acc": lambda r: r["overall"]["accuracy"],
        "test_n": lambda r: r["overall"]["n"],
    },
    "open_set": {
        "msp_auroc": lambda r: r["variants"]["CE + MSP"]["report"]["auroc"],
        "dist_auroc": lambda r: r["variants"]["CE + distance"]["report"]["auroc"],
        "obj_auroc": lambda r: r["variants"]["Objectosphere + MSP"]["report"]["auroc"],
        "msp_unk_reject": lambda r: r["variants"]["CE + MSP"]["report"]["unknown_reject_rate"],
        "dist_unk_reject": lambda r: r["variants"]["CE + distance"]["report"]["unknown_reject_rate"],
        "obj_unk_reject": lambda r: r["variants"]["Objectosphere + MSP"]["report"]["unknown_reject_rate"],
        "msp_known_accept": lambda r: r["variants"]["CE + MSP"]["report"]["known_accept_rate"],
        "dist_known_accept": lambda r: r["variants"]["CE + distance"]["report"]["known_accept_rate"],
        "obj_known_accept": lambda r: r["variants"]["Objectosphere + MSP"]["report"]["known_accept_rate"],
        "msp_closed_acc_accepted": lambda r: r["variants"]["CE + MSP"]["closed_set_on_accepted"]["accuracy"],
        "dist_closed_acc_accepted": lambda r: r["variants"]["CE + distance"]["closed_set_on_accepted"]["accuracy"],
        "obj_closed_acc_accepted": lambda r: r["variants"]["Objectosphere + MSP"]["closed_set_on_accepted"]["accuracy"],
    },
}

# Pre-registered paired per-seed differences (PREREGISTRATION.md H1-H4):
# name -> (stage_a, metric_a, stage_b, metric_b); value = a - b, predicted > 0.
HYPOTHESES = {
    "H1_dist_minus_msp_auroc": ("open_set", "dist_auroc", "open_set", "msp_auroc"),
    "H2_obj_minus_msp_unk_reject": ("open_set", "obj_unk_reject", "open_set", "msp_unk_reject"),
    "H3_fp_impaired_minus_ideal_acc": ("fingerprint", "test_acc", "fingerprint_ideal", "test_acc"),
    "H4_mod_ideal_minus_impaired_cnn": ("modulation_ideal", "cnn_overall_acc", "modulation", "cnn_overall_acc"),
}


def _progress(stage: str, seed: int):
    def emit(msg: str) -> None:
        print(f"[seed {seed}] {stage}: {msg}", flush=True)

    return emit


def run_stage(stage: str, scale: ex.Scale, seed: int) -> dict:
    p = _progress(stage, seed)
    if stage == "modulation":
        return ex.run_modulation(scale, impaired=True, seed=seed, progress=p)
    if stage == "modulation_ideal":
        return ex.run_modulation(scale, impaired=False, seed=seed, progress=p)
    if stage == "fingerprint":
        return ex.run_fingerprint(scale, impaired=True, seed=seed, progress=p)
    if stage == "fingerprint_ideal":
        return ex.run_fingerprint(scale, impaired=False, seed=seed, progress=p)
    if stage == "open_set":
        return ex.run_open_set(scale, seed=seed, xi=10.0, lam=0.1, target_known_accept=0.95, progress=p)
    raise ValueError(f"unknown stage {stage!r}")


def slim(result: dict) -> dict:
    """The committed copy: drop per-frame score arrays, keep every metric."""
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
        "open_set_params": {"xi": 10.0, "lam": 0.1, "target_known_accept": 0.95},
        "started_utc": started_utc,
    }


def write_summary_md(aggregate: dict, path: Path) -> None:
    lines = [
        "# Campaign summary (generated by run_campaign.py — do not edit)",
        "",
        (
            f"Scale `{aggregate['provenance']['scale']['name']}`, seeds {aggregate['provenance']['seeds']}, "
            f"commit `{aggregate['provenance']['git_commit']}`."
        ),
        "",
        "| stage | metric | per-seed | mean | sd |",
        "|---|---|---|---|---|",
    ]
    for stage, metrics in aggregate["metrics"].items():
        for name, s in metrics.items():
            per_seed = ", ".join(f"{v:.3f}" for v in s["per_seed"])
            sd = f"{s['sd']:.3f}" if s["sd"] is not None else "-"
            lines.append(f"| {stage} | {name} | {per_seed} | {s['mean']:.3f} | {sd} |")
    lines += ["", "## Pre-registered paired differences (a - b, predicted > 0)", ""]
    lines += ["| hypothesis | per-seed diff | mean | positive seeds | supported (>=4/5) |", "|---|---|---|---|---|"]
    for name, h in aggregate["hypotheses"].items():
        per_seed = ", ".join(f"{v:+.3f}" for v in h["per_seed_diff"])
        lines.append(
            f"| {name} | {per_seed} | {h['mean_diff']:+.3f} | {h['n_positive']}/{h['n_seeds']} | {h['supported']} |"
        )
    if aggregate["failures"]:
        lines += ["", "## Failures", ""]
        lines += [f"- seed {f['seed']} {f['stage']}: {f['error']}" for f in aggregate["failures"]]
    lines += ["", f"Total wall time: {aggregate['wall_time_s']:.0f} s", ""]
    path.write_text("\n".join(lines))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seeds", type=int, nargs="+", default=[0, 1, 2, 3, 4])
    ap.add_argument("--scale", default="full", choices=sorted(ex.SCALES))
    ap.add_argument("--out", type=Path, default=ROOT / "experiments" / "campaign")
    ap.add_argument("--threads", type=int, default=4)
    args = ap.parse_args()

    started_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    torch.set_num_threads(args.threads)
    scale = ex.get_scale(args.scale)
    out: Path = args.out
    (out / "raw").mkdir(parents=True, exist_ok=True)

    t0 = time.perf_counter()
    results: dict[str, dict[int, dict]] = {s: {} for s in METRICS}
    failures: list[dict] = []
    for seed in args.seeds:
        for stage in METRICS:
            t = time.perf_counter()
            try:
                r = run_stage(stage, scale, seed)
            except Exception as exc:  # noqa: BLE001 — any failure is recorded, never hidden (pre-registration rule)
                failures.append({"seed": seed, "stage": stage, "error": f"{type(exc).__name__}: {exc}"})
                print(f"[seed {seed}] {stage}: FAILED {exc}", flush=True)
                continue
            r["campaign"] = {"stage_wall_time_s": round(time.perf_counter() - t, 1)}
            (out / "raw" / f"{stage}_seed{seed}.json").write_text(ex.to_strict_json(r))
            (out / f"{stage}_seed{seed}.json").write_text(ex.to_strict_json(slim(r)))
            results[stage][seed] = r
            print(f"[seed {seed}] {stage}: done in {r['campaign']['stage_wall_time_s']} s", flush=True)

    aggregate = {
        "provenance": provenance(scale, list(args.seeds), started_utc),
        "metrics": {},
        "hypotheses": {},
        "failures": failures,
    }
    for stage, metrics in METRICS.items():
        seeds_done = sorted(results[stage])
        if not seeds_done:
            continue
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
        aggregate["hypotheses"][name] = {
            "seeds": seeds_done,
            "per_seed_diff": diffs,
            "mean_diff": float(np.mean(diffs)),
            "n_positive": n_pos,
            "n_seeds": len(diffs),
            # Pre-registered criterion: predicted sign in >= 4 of 5 seeds.
            "supported": bool(n_pos >= 4) if len(diffs) == 5 else None,
        }
    aggregate["wall_time_s"] = round(time.perf_counter() - t0, 1)

    (out / "aggregate.json").write_text(json.dumps(aggregate, indent=2, allow_nan=False))
    write_summary_md(aggregate, out / "aggregate_summary.md")
    print(f"campaign done in {aggregate['wall_time_s']} s; failures: {len(failures)}", flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Multi-seed campaign 2 over the scorer-bench stage.

Runs the pre-registered design in experiments/PREREGISTRATION_V2.md: for each
seed, one scorer_bench stage (one CE model with five post-hoc scorers plus
three Objectosphere arms) on the chosen scale preset. Writes, under --out:

    raw/scorer_bench_seed<k>.json   full stage results (includes per-frame scores)
    scorer_bench_seed<k>.json       same minus bulky arrays (committed to Git)
    aggregate.json                  per-seed metric table, mean/sd/min/max, paired
                                    per-seed differences for H5-H8, provenance
    aggregate_summary.md            the same as a readable table

Usage:
    .venv/bin/python experiments/run_campaign2.py --scale full --seeds 0 1 2 3 4
    .venv/bin/python experiments/run_campaign2.py --scale quick --seeds 0 \
        --out experiments/campaign2_smoke        # smoke test

Re-running with the same arguments reproduces the same JSON numbers (torch
CPU, fixed thread count). A stage that raises is recorded under "failures"
and does not abort the campaign: the pre-registration forbids hiding it.
Campaign 1 (run_campaign.py, experiments/campaign/) is closed and untouched.
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

STAGE = "scorer_bench"
SCORER_BENCH_PARAMS = {"xi": 10.0, "lam": 0.1, "target_known_accept": 0.95}

# The eight pre-registered variant keys (PREREGISTRATION_V2.md).
VARIANT_KEYS = (
    "CE+MSP",
    "CE+maxlogit",
    "CE+energy",
    "CE+distance",
    "CE+mahalanobis",
    "OS-full+MSP",
    "OS-16PSK+MSP",
    "OS-8PAM+MSP",
)
OS_ARMS = ("OS-full+MSP", "OS-16PSK+MSP", "OS-8PAM+MSP")


def _get(variant: str, path: tuple[str, ...]):
    """Extractor for one variant field; explicit so the aggregate stays auditable."""

    def fn(result: dict):
        node = result["variants"][variant]
        for key in path:
            node = node[key]
        return node

    return fn


def _metrics2() -> dict:
    m: dict = {}
    for v in VARIANT_KEYS:
        m[f"{v}:auroc"] = _get(v, ("report", "auroc"))
        m[f"{v}:unk_reject"] = _get(v, ("report", "unknown_reject_rate"))
        m[f"{v}:known_accept"] = _get(v, ("report", "known_accept_rate"))
        m[f"{v}:oscr_auc"] = _get(v, ("oscr", "oscr_auc"))
    for v in ("CE+MSP",) + OS_ARMS:
        m[f"{v}:reject_4PAM"] = _get(v, ("per_unknown_class", "4PAM", "reject_rate"))
        m[f"{v}:reject_64QAM"] = _get(v, ("per_unknown_class", "64QAM", "reject_rate"))
    m["CE+MSP:auroc_low_le2"] = _get("CE+MSP", ("snr_band_auroc", "low_le2"))
    m["CE+MSP:auroc_high_ge10"] = _get("CE+MSP", ("snr_band_auroc", "high_ge10"))
    return m


# Metric extractors: stage name -> {metric name: callable(result) -> float|None}.
METRICS = {STAGE: _metrics2()}

# Pre-registered paired per-seed differences (PREREGISTRATION_V2.md H5-H8):
# name -> (metric_a, metric_b), both in the scorer_bench stage;
# value = a - b, predicted > 0, supported iff positive in >= 4 of 5 seeds.
HYPOTHESES = {
    "H5_mahal_minus_euclid_auroc": ("CE+mahalanobis:auroc", "CE+distance:auroc"),
    "H6_energy_minus_msp_auroc": ("CE+energy:auroc", "CE+MSP:auroc"),
    "H7_pamarm_minus_pskarm_4pam_reject": ("OS-8PAM+MSP:reject_4PAM", "OS-16PSK+MSP:reject_4PAM"),
    "H8_msp_low_minus_high_auroc": ("CE+MSP:auroc_low_le2", "CE+MSP:auroc_high_ge10"),
}


def _progress(stage: str, seed: int):
    def emit(msg: str) -> None:
        print(f"[seed {seed}] {stage}: {msg}", flush=True)

    return emit


def run_stage(stage: str, scale: ex.Scale, seed: int) -> dict:
    if stage == STAGE:
        return ex.run_scorer_bench(
            scale,
            seed=seed,
            xi=SCORER_BENCH_PARAMS["xi"],
            lam=SCORER_BENCH_PARAMS["lam"],
            target_known_accept=SCORER_BENCH_PARAMS["target_known_accept"],
            progress=_progress(stage, seed),
        )
    raise ValueError(f"unknown stage {stage!r}")


def slim(result: dict) -> dict:
    """The committed copy: drop per-frame score arrays, keep every metric."""
    out = copy.deepcopy(result)
    for variant in out.get("variants", {}).values():
        variant.pop("scores", None)
    return out


def summarize(values: list[float | None]) -> dict:
    """Mean/sd/min/max over defined values; None entries stay null with counts."""
    defined = [float(v) for v in values if v is not None]
    arr = np.asarray(defined, dtype=np.float64)
    return {
        "per_seed": [None if v is None else float(v) for v in values],
        "n_defined": len(defined),
        "n_null": len(values) - len(defined),
        "mean": float(arr.mean()) if arr.size else None,
        "sd": float(arr.std(ddof=1)) if arr.size > 1 else None,
        "min": float(arr.min()) if arr.size else None,
        "max": float(arr.max()) if arr.size else None,
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
        "scorer_bench_params": dict(SCORER_BENCH_PARAMS),
        "preregistration": "experiments/PREREGISTRATION_V2.md",
        "started_utc": started_utc,
    }


def _fmt(v: float | None, spec: str = ".3f") -> str:
    return "-" if v is None else format(v, spec)


def write_summary_md(aggregate: dict, path: Path) -> None:
    lines = [
        "# Campaign 2 summary (generated by run_campaign2.py — do not edit)",
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
            per_seed = ", ".join(_fmt(v) for v in s["per_seed"])
            lines.append(f"| {stage} | {name} | {per_seed} | {_fmt(s['mean'])} | {_fmt(s['sd'])} |")
    lines += ["", "## Pre-registered paired differences (a - b, predicted > 0)", ""]
    lines += ["| hypothesis | per-seed diff | mean | positive seeds | supported (>=4/5) |", "|---|---|---|---|---|"]
    for name, h in aggregate["hypotheses"].items():
        per_seed = ", ".join(_fmt(v, "+.3f") for v in h["per_seed_diff"])
        mean = _fmt(h["mean_diff"], "+.3f")
        lines.append(f"| {name} | {per_seed} | {mean} | {h['n_positive']}/{h['n_seeds']} | {h['supported']} |")
    if aggregate["failures"]:
        lines += ["", "## Failures", ""]
        lines += [f"- seed {f['seed']} {f['stage']}: {f['error']}" for f in aggregate["failures"]]
    lines += ["", f"Total wall time: {aggregate['wall_time_s']:.0f} s", ""]
    path.write_text("\n".join(lines))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seeds", type=int, nargs="+", default=[0, 1, 2, 3, 4])
    ap.add_argument("--scale", default="full", choices=sorted(ex.SCALES))
    ap.add_argument("--out", type=Path, default=ROOT / "experiments" / "campaign2")
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
    for name, (m_a, m_b) in HYPOTHESES.items():
        seeds_done = sorted(results[STAGE])
        if not seeds_done:
            continue
        diffs: list[float | None] = []
        for s in seeds_done:
            a = METRICS[STAGE][m_a](results[STAGE][s])
            b = METRICS[STAGE][m_b](results[STAGE][s])
            diffs.append(None if a is None or b is None else float(a - b))
        defined = [d for d in diffs if d is not None]
        n_pos = sum(d > 0 for d in defined)
        aggregate["hypotheses"][name] = {
            "seeds": seeds_done,
            "a_minus_b": [m_a, m_b],
            "per_seed_diff": diffs,
            "mean_diff": float(np.mean(defined)) if defined else None,
            "n_positive": n_pos,
            "n_seeds": len(diffs),
            "n_defined": len(defined),
            # Pre-registered criterion: predicted sign in >= 4 of 5 seeds (all defined).
            "supported": bool(n_pos >= 4) if len(diffs) == 5 and len(defined) == 5 else None,
        }
    aggregate["wall_time_s"] = round(time.perf_counter() - t0, 1)

    (out / "aggregate.json").write_text(json.dumps(aggregate, indent=2, allow_nan=False))
    write_summary_md(aggregate, out / "aggregate_summary.md")
    print(f"campaign 2 done in {aggregate['wall_time_s']} s; failures: {len(failures)}", flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

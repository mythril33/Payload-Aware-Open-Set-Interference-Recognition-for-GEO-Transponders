"""Generate the paper's figures from campaign results (real data only).

Reads experiments/campaign/ (campaign 1) and experiments/campaign2/
(campaign 2, scorer bench) and writes paper/figures/fig*.png. Figures whose
source data are missing are skipped with a message, never faked. Every value
plotted comes from the committed aggregates or the local raw score files;
captions in the paper state seed and n for anything single-seed.

Usage:  .venv/bin/python experiments/make_figures.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

C1 = ROOT / "experiments" / "campaign"
C2 = ROOT / "experiments" / "campaign2"
OUT = ROOT / "paper" / "figures"

# Validated categorical palette (dataviz reference, light mode, fixed order).
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
INK, MUTED, GRID = "#1a1a19", "#6b6a63", "#e3e2da"

plt.rcParams.update(
    {
        "figure.dpi": 150,
        "font.size": 9,
        "axes.edgecolor": MUTED,
        "axes.labelcolor": INK,
        "text.color": INK,
        "xtick.color": MUTED,
        "ytick.color": MUTED,
        "axes.grid": True,
        "grid.color": GRID,
        "grid.linewidth": 0.6,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "legend.frameon": False,
        "savefig.bbox": "tight",
    }
)


def load(path: Path) -> dict | None:
    if not path.exists():
        print(f"skip: {path} missing")
        return None
    return json.loads(path.read_text())


def fig1_auroc_dots(agg2: dict) -> None:
    """Per-seed AUROC for every campaign-2 variant; identity by position, not color."""
    order = ["CE+MSP", "CE+maxlogit", "CE+energy", "CE+distance", "CE+mahalanobis",
             "OS-full+MSP", "OS-16PSK+MSP", "OS-8PAM+MSP"]
    m = agg2["metrics"]["scorer_bench"]
    fig, ax = plt.subplots(figsize=(7.0, 3.2))
    for i, v in enumerate(order):
        vals = m[f"{v}:auroc"]["per_seed"]
        ax.scatter([i] * len(vals), vals, s=22, color=BLUE, alpha=0.75, zorder=3)
        ax.hlines(float(np.mean(vals)), i - 0.28, i + 0.28, color=INK, lw=1.6, zorder=4)
    ax.axhline(0.5, color=MUTED, lw=1, ls="--")
    ax.text(len(order) - 0.45, 0.505, "chance", color=MUTED, fontsize=8, va="bottom", ha="right")
    ax.set_xticks(range(len(order)))
    ax.set_xticklabels([v.replace("+", "\n+") for v in order], fontsize=7.5)
    ax.set_ylabel("AUROC (unknown = positive)")
    ax.set_ylim(0, 1)
    ax.set_title("Open-set AUROC per seed (dots) and mean (bar), 5 seeds, scale full", fontsize=9)
    fig.savefig(OUT / "fig1_auroc.png")
    plt.close(fig)
    print("wrote fig1_auroc.png")


def _oscr_curve(raw_variant: dict) -> tuple[np.ndarray, np.ndarray]:
    from rfml.experiments import oscr_points

    s = raw_variant["scores"]
    pts = oscr_points(
        np.asarray(s["known"], dtype=np.float64),
        np.asarray(s["known_correct"], dtype=bool),
        np.asarray(s["unknown"], dtype=np.float64),
    )
    return np.asarray(pts["fpr"]), np.asarray(pts["ccr"])


def fig2_oscr(raw2_seed0: dict) -> None:
    """OSCR curves for the three main scores on the same CE model (seed 0)."""
    fig, ax = plt.subplots(figsize=(4.6, 3.4))
    for name, color in (("CE+MSP", BLUE), ("CE+distance", ORANGE), ("CE+mahalanobis", AQUA)):
        fpr, ccr = _oscr_curve(raw2_seed0["variants"][name])
        ax.plot(fpr, ccr, color=color, lw=2, label=name)
    ax.set_xlabel("Unknown false-accept rate (n = 200)")
    ax.set_ylabel("Correct classification rate (n = 400)")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_title("OSCR, one CE model, seed 0", fontsize=9)
    ax.legend(loc="lower right", fontsize=8)
    fig.savefig(OUT / "fig2_oscr.png")
    plt.close(fig)
    print("wrote fig2_oscr.png")


def fig3_snr_auroc(c2dir: Path, seeds: list[int]) -> None:
    """Per-SNR AUROC, mean +/- sd across seeds, CE+MSP vs CE+distance."""
    series: dict[str, dict[float, list[float]]] = {"CE+MSP": {}, "CE+distance": {}}
    for seed in seeds:
        r = load(c2dir / f"scorer_bench_seed{seed}.json")
        if r is None:
            return
        for name in series:
            for row in r["variants"][name]["per_snr_auroc"]:
                if row["auroc"] is not None:
                    series[name].setdefault(row["snr_db"], []).append(row["auroc"])
    fig, ax = plt.subplots(figsize=(5.4, 3.3))
    for name, color in (("CE+MSP", BLUE), ("CE+distance", ORANGE)):
        snrs = sorted(series[name])
        mean = np.array([np.mean(series[name][s]) for s in snrs])
        sd = np.array([np.std(series[name][s], ddof=1) for s in snrs])
        ax.plot(snrs, mean, color=color, lw=2, label=name, marker="o", ms=3.5)
        ax.fill_between(snrs, mean - sd, mean + sd, color=color, alpha=0.15, lw=0)
    ax.axhline(0.5, color=MUTED, lw=1, ls="--")
    ax.set_xlabel("SNR (dB)")
    ax.set_ylabel("AUROC (unknown = positive)")
    ax.set_ylim(0, 1)
    ax.set_title("AUROC per SNR, mean ± sd over 5 seeds", fontsize=9)
    ax.legend(loc="center left", fontsize=8)
    fig.savefig(OUT / "fig3_snr_auroc.png")
    plt.close(fig)
    print("wrote fig3_snr_auroc.png")


def fig4_confound(agg2: dict) -> None:
    """H7: per-unknown-class rejection under the three Objectosphere arms."""
    m = agg2["metrics"]["scorer_bench"]
    arms = [("OS-full+MSP", BLUE), ("OS-16PSK+MSP", ORANGE), ("OS-8PAM+MSP", AQUA)]
    classes = ["64QAM", "4PAM"]
    fig, ax = plt.subplots(figsize=(5.2, 3.2))
    width = 0.24
    for j, (arm, color) in enumerate(arms):
        for i, cls in enumerate(classes):
            vals = m[f"{arm}:reject_{cls}"]["per_seed"]
            x = i + (j - 1) * width
            ax.bar(x, float(np.mean(vals)), width=width - 0.02, color=color,
                   label=arm if i == 0 else None, zorder=2)
            ax.scatter([x] * len(vals), vals, s=12, color=INK, alpha=0.6, zorder=3)
    ax.set_xticks(range(len(classes)))
    ax.set_xticklabels([f"{c} unknowns (n = 100/seed)" for c in classes])
    ax.set_ylabel("Unknown rejection rate")
    ax.set_ylim(0, 1)
    ax.set_title("Rejection by unknown class and auxiliary-outlier arm (dots: seeds)", fontsize=9)
    ax.legend(fontsize=8)
    fig.savefig(OUT / "fig4_confound.png")
    plt.close(fig)
    print("wrote fig4_confound.png")


def fig5_modulation(c1dir: Path, seeds: list[int]) -> None:
    """Campaign 1: closed-set accuracy vs SNR, CNN1D and MLP, with chance."""
    series: dict[str, dict[float, list[float]]] = {"CNN1D": {}, "MLP": {}}
    for seed in seeds:
        r = load(c1dir / f"modulation_seed{seed}.json")
        if r is None:
            return
        for name in series:
            for row in r["models"][name]["per_snr"]:
                if row["accuracy"] is not None:
                    series[name].setdefault(row["snr_db"], []).append(row["accuracy"])
    fig, ax = plt.subplots(figsize=(5.4, 3.3))
    for name, color in (("CNN1D", BLUE), ("MLP", ORANGE)):
        snrs = sorted(series[name])
        mean = np.array([np.mean(series[name][s]) for s in snrs])
        sd = np.array([np.std(series[name][s], ddof=1) for s in snrs])
        ax.plot(snrs, mean, color=color, lw=2, label=name, marker="o", ms=3.5)
        ax.fill_between(snrs, mean - sd, mean + sd, color=color, alpha=0.15, lw=0)
    ax.axhline(0.25, color=MUTED, lw=1, ls="--")
    ax.text(19.5, 0.26, "chance", color=MUTED, fontsize=8, ha="right")
    ax.set_xlabel("Test SNR (dB)")
    ax.set_ylabel("Accuracy on unseen devices (n = 400/SNR/seed)")
    ax.set_ylim(0, 1)
    ax.set_title("Closed-set accuracy vs SNR, mean ± sd over 5 seeds", fontsize=9)
    ax.legend(loc="upper left", fontsize=8)
    fig.savefig(OUT / "fig5_modulation.png")
    plt.close(fig)
    print("wrote fig5_modulation.png")


def fig6_hists(raw2_seed0: dict) -> None:
    """Known vs unknown score distributions with the calibrated threshold (seed 0)."""
    fig, axes = plt.subplots(1, 2, figsize=(7.2, 3.0))
    for ax, name in zip(axes, ("CE+MSP", "CE+distance")):
        v = raw2_seed0["variants"][name]
        known = np.asarray(v["scores"]["known"])
        unknown = np.asarray(v["scores"]["unknown"])
        bins = np.histogram_bin_edges(np.concatenate([known, unknown]), bins=40)
        ax.hist(known, bins=bins, color=BLUE, alpha=0.65, label="known (n = 400)")
        ax.hist(unknown, bins=bins, color=ORANGE, alpha=0.65, label="unknown (n = 200)")
        ax.axvline(v["threshold"], color=INK, lw=1.4, ls="--")
        ax.text(v["threshold"], ax.get_ylim()[1] * 0.95, " threshold", fontsize=7.5, va="top")
        ax.set_title(name, fontsize=9)
        ax.set_xlabel("score (larger = more unknown-like)")
    axes[0].set_ylabel("frames")
    axes[0].legend(fontsize=8)
    fig.suptitle("Score distributions on one CE model, seed 0", fontsize=9, y=1.02)
    fig.savefig(OUT / "fig6_hists.png")
    plt.close(fig)
    print("wrote fig6_hists.png")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    agg1 = load(C1 / "aggregate.json")
    if agg1 is not None:
        fig5_modulation(C1, agg1["provenance"]["seeds"])
    agg2 = load(C2 / "aggregate.json")
    if agg2 is not None:
        fig1_auroc_dots(agg2)
        fig3_snr_auroc(C2, agg2["provenance"]["seeds"])
        fig4_confound(agg2)
        raw0 = load(C2 / "raw" / "scorer_bench_seed0.json")
        if raw0 is not None:
            fig2_oscr(raw0)
            fig6_hists(raw0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

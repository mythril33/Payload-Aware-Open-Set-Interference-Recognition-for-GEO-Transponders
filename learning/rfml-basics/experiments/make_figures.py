"""Generate the paper's figures from campaign results (real data only).

Reads the per-seed result files of campaigns 1-3 and the two replication
campaigns and writes paper/figures/<name>.pdf (vector, used by the paper) and
<name>.png (preview). A figure whose source data are missing stops the script
with the missing path: nothing is drawn from placeholder values.

Single-seed figures (score histograms, OSCR curves) use the committed raw
score file of seed 0 and say so in their captions.

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

EXP = ROOT / "experiments"
OUT = ROOT / "paper" / "figures"

ORIGINAL_SEEDS = (0, 1, 2, 3, 4)
REPLICATION_SEEDS = (5, 6, 7, 8, 9)
ALL_SEEDS = ORIGINAL_SEEDS + REPLICATION_SEEDS

# Validated categorical palette (fixed order), ink and grid tones.
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
INK, MUTED, GRID = "#1a1a19", "#6b6a63", "#e3e2da"
COL, WIDE = 3.45, 7.1  # IEEE column and page widths in inches

plt.rcParams.update(
    {
        "font.size": 8,
        "axes.titlesize": 8,
        "axes.labelsize": 8,
        "xtick.labelsize": 7,
        "ytick.labelsize": 7,
        "legend.fontsize": 7,
        "axes.edgecolor": MUTED,
        "axes.labelcolor": INK,
        "text.color": INK,
        "xtick.color": MUTED,
        "ytick.color": MUTED,
        "axes.grid": True,
        "grid.color": GRID,
        "grid.linewidth": 0.5,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "legend.frameon": False,
        "savefig.bbox": "tight",
        "savefig.pad_inches": 0.02,
        "pdf.fonttype": 42,  # embed TrueType fonts (publisher requirement)
    }
)


def load(path: Path) -> dict:
    if not path.exists():
        sys.exit(f"missing {path}: run the campaigns first (experiments/README.md)")
    return json.loads(path.read_text())


def seed_file(original: str, replication: str, stage: str, seed: int) -> dict:
    folder = original if seed in ORIGINAL_SEEDS else replication
    return load(EXP / folder / f"{stage}_seed{seed}.json")


def save(fig, name: str) -> None:
    fig.savefig(OUT / f"{name}.pdf")
    fig.savefig(OUT / f"{name}.png", dpi=200)
    plt.close(fig)
    print(f"wrote {name}.pdf / .png")


def seed_dots(ax, x: float, values, color: str = BLUE) -> None:
    """Original seeds filled, replication seeds open; the mean of all as a bar."""
    values = np.asarray(values, dtype=float)
    n_orig = len(ORIGINAL_SEEDS)
    ax.scatter([x - 0.09] * n_orig, values[:n_orig], s=11, color=color, zorder=3, linewidths=0)
    ax.scatter([x + 0.09] * (len(values) - n_orig), values[n_orig:], s=11, facecolors="white",
               edgecolors=color, linewidths=0.9, zorder=3)
    ax.hlines(values.mean(), x - 0.3, x + 0.3, color=INK, lw=1.3, zorder=4)


def fig_auroc() -> None:
    """Per-seed AUROC of every campaign-2 variant, original and replication seeds."""
    order = ["CE+MSP", "CE+maxlogit", "CE+energy", "CE+distance", "CE+mahalanobis",
             "OS-full+MSP", "OS-16PSK+MSP", "OS-8PAM+MSP"]
    labels = ["MSP", "max-logit", "energy", "Euclidean\ndistance", "Mahalanobis",
              "Objectosph.\nfull aux", "Objectosph.\n16PSK aux", "Objectosph.\n8PAM aux"]
    runs = [seed_file("campaign2", "campaign2_rep", "scorer_bench", s) for s in ALL_SEEDS]
    fig, ax = plt.subplots(figsize=(WIDE, 2.3))
    for i, v in enumerate(order):
        seed_dots(ax, i, [r["variants"][v]["report"]["auroc"] for r in runs])
    ax.axhline(0.5, color=MUTED, lw=0.8, ls="--")
    ax.text(len(order) - 0.55, 0.51, "chance", color=MUTED, fontsize=7, va="bottom", ha="right")
    ax.axvline(4.5, color=GRID, lw=0.8)
    ax.text(2.0, 0.965, "post-hoc scores on one CE model", fontsize=7, color=MUTED, ha="center")
    ax.text(6.0, 0.965, "separately trained", fontsize=7, color=MUTED, ha="center")
    ax.set_xticks(range(len(order)))
    ax.set_xticklabels(labels)
    ax.set_ylabel("AUROC (unknown = positive)")
    ax.set_ylim(0, 1)
    ax.set_xlim(-0.6, len(order) - 0.4)
    ax.scatter([], [], s=11, color=BLUE, label="seeds 0-4 (original)")
    ax.scatter([], [], s=11, facecolors="white", edgecolors=BLUE, linewidths=0.9, label="seeds 5-9 (replication)")
    ax.plot([], [], color=INK, lw=1.3, label="mean of 10 seeds")
    ax.legend(loc="lower left", ncols=3, bbox_to_anchor=(0.0, 0.0))
    save(fig, "fig_auroc")


def fig_hists(raw0: dict) -> None:
    """Known vs unknown score distributions with the calibrated threshold (seed 0)."""
    fig, axes = plt.subplots(1, 2, figsize=(COL, 1.75))
    for ax, name, title in zip(axes, ("CE+MSP", "CE+distance"), ("MSP score", "Euclidean distance")):
        v = raw0["variants"][name]
        known = np.asarray(v["scores"]["known"])
        unknown = np.asarray(v["scores"]["unknown"])
        bins = np.histogram_bin_edges(np.concatenate([known, unknown]), bins=36)
        ax.hist(known, bins=bins, color=BLUE, alpha=0.7, label="known")
        ax.hist(unknown, bins=bins, color=ORANGE, alpha=0.7, label="unknown")
        ax.axvline(v["threshold"], color=INK, lw=1.0, ls="--")
        ax.set_title(title)
        ax.set_xlabel("score (larger = more unknown)")
    axes[0].set_ylabel("frames")
    axes[0].legend(loc="upper right")
    fig.tight_layout(w_pad=0.6)
    save(fig, "fig_hists")


def fig_oscr(raw0: dict) -> None:
    """OSCR curves of three scores on the same CE model (seed 0)."""
    from rfml.experiments import oscr_points

    fig, ax = plt.subplots(figsize=(COL, 2.2))
    for name, label, color in (("CE+MSP", "MSP", BLUE), ("CE+distance", "Euclidean distance", ORANGE),
                               ("CE+mahalanobis", "Mahalanobis", AQUA)):
        s = raw0["variants"][name]["scores"]
        pts = oscr_points(np.asarray(s["known"], dtype=np.float64), np.asarray(s["known_correct"], dtype=bool),
                          np.asarray(s["unknown"], dtype=np.float64))
        ax.plot(pts["fpr"], pts["ccr"], color=color, lw=1.5, label=label)
    ax.set_xlabel("unknown false-accept rate")
    ax.set_ylabel("correct classification rate")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.legend(loc="lower right")
    save(fig, "fig_oscr")


def _mean_sd_curve(ax, series: dict[float, list[float]], color: str, label: str) -> None:
    xs = sorted(series)
    mean = np.array([np.mean(series[x]) for x in xs])
    sd = np.array([np.std(series[x], ddof=1) for x in xs])
    ax.plot(xs, mean, color=color, lw=1.5, label=label, marker="o", ms=2.5)
    ax.fill_between(xs, mean - sd, mean + sd, color=color, alpha=0.15, lw=0)


def fig_snr_auroc() -> None:
    """AUROC per SNR, mean and sd over ten seeds, MSP vs Euclidean distance."""
    series: dict[str, dict[float, list[float]]] = {"CE+MSP": {}, "CE+distance": {}}
    for seed in ALL_SEEDS:
        r = seed_file("campaign2", "campaign2_rep", "scorer_bench", seed)
        for name in series:
            for row in r["variants"][name]["per_snr_auroc"]:
                if row["auroc"] is not None:
                    series[name].setdefault(row["snr_db"], []).append(row["auroc"])
    fig, ax = plt.subplots(figsize=(COL, 2.1))
    _mean_sd_curve(ax, series["CE+distance"], ORANGE, "Euclidean distance")
    _mean_sd_curve(ax, series["CE+MSP"], BLUE, "MSP")
    ax.axhline(0.5, color=MUTED, lw=0.8, ls="--")
    ax.set_xlabel("SNR (dB)")
    ax.set_ylabel("AUROC (unknown = positive)")
    ax.set_ylim(0, 1)
    ax.legend(loc="center right")
    save(fig, "fig_snr_auroc")


def fig_confound() -> None:
    """Shared-seed arms (campaign 3): rejection per unknown class and outlier pool."""
    runs = [load(EXP / "campaign3" / f"arm_control_seed{s}.json") for s in ALL_SEEDS]
    arms = [("OS-full+MSP", "16PSK + 8PAM", BLUE), ("OS-16PSK+MSP", "16PSK only", ORANGE),
            ("OS-8PAM+MSP", "8PAM only", AQUA)]
    classes = ["64QAM", "4PAM"]
    fig, ax = plt.subplots(figsize=(COL, 2.1))
    width = 0.25
    for j, (arm, label, color) in enumerate(arms):
        for i, cls in enumerate(classes):
            vals = [r["variants"][arm]["per_unknown_class"][cls]["reject_rate"] for r in runs]
            x = i + (j - 1) * width
            ax.bar(x, float(np.mean(vals)), width=width - 0.03, color=color, label=label if i == 0 else None, zorder=2)
            ax.scatter([x] * len(vals), vals, s=5, color=INK, alpha=0.55, zorder=3, linewidths=0)
    ax.set_xticks(range(len(classes)))
    ax.set_xticklabels([f"{c} unknowns" for c in classes])
    ax.set_ylabel("unknown rejection rate")
    ax.set_ylim(0, 1)
    ax.legend(title="auxiliary outlier pool", title_fontsize=7, loc="upper left")
    save(fig, "fig_confound")


def fig_seen_unseen() -> None:
    """Campaign 3: accuracy on training frames, new frames of seen devices, unseen devices."""
    runs = [load(EXP / "campaign3" / f"split_counterfactual_seed{s}.json") for s in ALL_SEEDS]
    kinds = [("train_accuracy", "training frames", BLUE),
             ("seen", "new frames,\nseen devices", ORANGE),
             ("unseen", "unseen devices", AQUA)]
    fig, ax = plt.subplots(figsize=(COL, 2.1))
    width = 0.25
    for i, model in enumerate(("MLP", "CNN1D")):
        for j, (kind, label, color) in enumerate(kinds):
            if kind == "train_accuracy":
                vals = [r["models"][model]["train_accuracy"] for r in runs]
            elif kind == "seen":
                vals = [r["models"][model]["seen_devices_new_frames"]["overall"]["accuracy"] for r in runs]
            else:
                vals = [r["models"][model]["unseen_devices"]["overall"]["accuracy"] for r in runs]
            x = i + (j - 1) * width
            ax.bar(x, float(np.mean(vals)), width=width - 0.03, color=color, label=label if i == 0 else None, zorder=2)
            ax.scatter([x] * len(vals), vals, s=5, color=INK, alpha=0.55, zorder=3, linewidths=0)
    ax.axhline(0.25, color=MUTED, lw=0.8, ls="--")
    ax.text(1.42, 0.265, "chance", color=MUTED, fontsize=7, ha="right")
    ax.set_xticks([0, 1])
    ax.set_xticklabels(["MLP", "CNN1D"])
    ax.set_ylabel("accuracy")
    ax.set_ylim(0, 1.18)
    ax.set_yticks([0, 0.2, 0.4, 0.6, 0.8, 1.0])
    ax.legend(loc="upper center", ncols=3, columnspacing=0.8, handlelength=1.2)
    save(fig, "fig_seen_unseen")


def fig_shrinkage() -> None:
    """Campaign 3 (exploratory): Mahalanobis AUROC against the shrinkage."""
    agg = load(EXP / "campaign3" / "aggregate.json")
    metrics = agg["metrics"]["arm_control"]
    shrinkages = agg["provenance"]["shrinkage_sweep"]
    mean = np.array([metrics[f"CE+mahalanobis@{s:g}:auroc"]["mean"] for s in shrinkages])
    sd = np.array([metrics[f"CE+mahalanobis@{s:g}:auroc"]["sd"] for s in shrinkages])
    fig, ax = plt.subplots(figsize=(COL, 1.9))
    xs = np.arange(len(shrinkages))
    ax.errorbar(xs, mean, yerr=sd, color=AQUA, lw=1.5, marker="o", ms=3, capsize=2, label="Mahalanobis")
    euclid = metrics["CE+distance:auroc"]["mean"]
    ax.axhline(euclid, color=ORANGE, lw=1.2, ls="--", label="Euclidean distance")
    ax.set_xticks(xs)
    ax.set_xticklabels([f"{s:g}" for s in shrinkages])
    ax.set_xlabel("shrinkage toward the scaled identity")
    ax.set_ylabel("AUROC")
    lo = float(min((mean - sd).min(), euclid)) - 0.02
    ax.set_ylim(lo, float(max((mean + sd).max(), euclid)) + 0.02)
    ax.legend(loc="lower right")
    save(fig, "fig_shrinkage")


def fig_modulation() -> None:
    """Campaign 1 and its replication: closed-set accuracy against the test SNR."""
    series: dict[str, dict[float, list[float]]] = {"CNN1D": {}, "MLP": {}}
    for seed in ALL_SEEDS:
        r = seed_file("campaign", "campaign_rep", "modulation", seed)
        for name in series:
            for row in r["models"][name]["per_snr"]:
                series[name].setdefault(row["snr_db"], []).append(row["accuracy"])
    fig, ax = plt.subplots(figsize=(COL, 2.1))
    _mean_sd_curve(ax, series["CNN1D"], BLUE, "CNN1D")
    _mean_sd_curve(ax, series["MLP"], ORANGE, "MLP")
    ax.axhline(0.25, color=MUTED, lw=0.8, ls="--")
    ax.text(19.5, 0.265, "chance", color=MUTED, fontsize=7, ha="right")
    ax.set_xlabel("test SNR (dB)")
    ax.set_ylabel("accuracy, unseen devices")
    ax.set_ylim(0, 1)
    ax.legend(loc="center right")
    save(fig, "fig_modulation")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    raw0 = load(EXP / "campaign2" / "raw" / "scorer_bench_seed0.json")
    fig_auroc()
    fig_hists(raw0)
    fig_oscr(raw0)
    fig_snr_auroc()
    fig_confound()
    fig_seen_unseen()
    fig_shrinkage()
    fig_modulation()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

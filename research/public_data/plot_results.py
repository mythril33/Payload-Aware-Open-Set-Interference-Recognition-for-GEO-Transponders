"""Recreate aggregate public-data figures; never opens raw observations."""
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def plot(source, directory):
    report = json.loads(Path(source).read_text())
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    names = ("native_level", "clean_diagonal_distance", "binary_centroid_margin")
    colors = ("#d97706", "#2563eb", "#6b7280")
    labels = ("Native level (fixed direction)", "Clean diagonal distance", "Binary centroid margin")
    titles = ("LC receiver features: 120 nonempty parents", "FIOT RGB crop 0: 243 parents")
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5), constrained_layout=True)
    for ax, key, title in zip(axes, ("lc", "fiot"), titles):
        results = report["datasets"][key]["experiment"]["results"]
        for name, color, label in zip(names, colors, labels):
            r = results[name]
            ax.plot(r["roc"]["fpr"], r["roc"]["tpr"], color=color, label=f'{label} (AUC {r["auroc"]:.3f})')
            ax.scatter(r["false_alarm"]["rate"], r["detection"]["rate"], color=color, s=25, zorder=4)
        ax.plot([0, 1], [0, 1], "k--", lw=.8, alpha=.4)
        ax.set(xlim=(-.02, 1.02), ylim=(-.02, 1.02), xlabel="False-alarm fraction of clean test parents",
               ylabel="Detected fraction of interference test parents", title=title)
        ax.legend(fontsize=8, loc="lower right")
        ax.grid(alpha=.2)
    fig.suptitle("Measured GNSS data: independent models per representation; not GEO validation", fontsize=11)
    fig.savefig(directory/"public_data_roc.png", dpi=180)
    fig.savefig(directory/"public_data_roc.pdf", metadata={"CreationDate": None, "ModDate": None})
    plt.close(fig)

    fig, axes = plt.subplots(2, 1, figsize=(11, 6), constrained_layout=True)
    for ax, key, title in zip(axes, ("lc", "fiot"), titles):
        classes = report["datasets"][key]["experiment"]["results"]["clean_diagonal_distance"]["per_native_class"]
        for i, (native, row) in enumerate(classes.items()):
            if row["rate"] is None:
                ax.text(i, .04, "NA\n(n=0)", ha="center", va="bottom", color="#666666", fontsize=9)
            else:
                ax.bar(i, row["rate"], color="#6b7280" if native == "0" else "#2563eb", width=.7)
                ax.text(i, min(row["rate"] + .035, 1.03), f'{row["count"]}/{row["denominator"]}', ha="center", fontsize=9)
        ax.set_xticks(np.arange(len(classes)), ["Clean (FA)" if n == "0" else row["name"] for n, row in classes.items()])
        ax.set(ylim=(0, 1.15), ylabel="Alarm fraction", title=title+" — clean diagonal distance")
        ax.grid(axis="y", alpha=.2)
    fig.suptitle("Native GNSS labels; clean bar is false alarms, other bars are detections", fontsize=11)
    fig.savefig(directory/"public_data_per_class.png", dpi=180)
    fig.savefig(directory/"public_data_per_class.pdf", metadata={"CreationDate": None, "ModDate": None})
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    plot(args.source, args.directory)

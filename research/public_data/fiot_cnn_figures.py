"""Plot aggregate FIOT-CNN/1 results without reading spectrogram files.

Run from the repository root:
    python -m research.public_data.fiot_cnn_figures --summary /path/to/summary.json --out /path/to/figures
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter
import numpy as np


SCORE_STYLES = {
    "msp": ("MSP", "#176b88"),
    "energy": ("Energy", "#ba4b24"),
    "mahalanobis": ("Mahalanobis", "#72479a"),
}


def plot(summary_path, directory):
    report = json.loads(Path(summary_path).read_text(encoding="utf-8"))
    if report["protocol"] != "FIOT-CNN/1":
        raise ValueError("expected a FIOT-CNN/1 summary")
    runs = report["results_by_seed"]
    if sorted(r["seed"] for r in runs) != report["recipe"]["seeds"]:
        raise ValueError("summary must include every configured training seed exactly once")

    label_ids = sorted(report["known_labels"], key=int)
    names = ["Clean" if label == "0" else report["known_labels"][label] for label in label_ids]
    known = report["partitions"]["known_test"]
    unknown = report["partitions"]["unknown_test"]["n"]
    counts = np.array([known["class_counts"].get(label, 0) for label in label_ids])
    matrices = np.array([r["known_confusion"] for r in runs])
    if (matrices.shape != (len(runs), len(label_ids), len(label_ids))
            or matrices.dtype.kind not in "iu" or (matrices < 0).any()
            or not np.all(matrices.sum(axis=2) == counts) or counts.sum() != known["n"]):
        raise ValueError("confusion matrices do not match the published test counts")

    fig, (recall_ax, roc_ax) = plt.subplots(1, 2, figsize=(9.6, 4), layout="constrained")
    positions = np.arange(len(names))
    supported = counts > 0
    recall = np.diagonal(matrices, axis1=1, axis2=2)[:, supported] / counts[supported]
    mean = recall.mean(axis=0)
    limits = np.maximum(0, np.vstack((mean - recall.min(axis=0), recall.max(axis=0) - mean)))
    recall_ax.errorbar(mean, positions[supported], xerr=limits, fmt="o", color="#176b88",
                       ecolor="#747f89", capsize=3, markersize=5)
    for y in positions[~supported]:
        recall_ax.text(.04, y, "No test records", color="#747f89", va="center", fontsize=8)
    recall_ax.set_yticks(positions, [f"{name} (n={n})" for name, n in zip(names, counts)])
    recall_ax.set(xlim=(-.03, 1.03), xlabel="Recall before rejection (mean and seed range)",
                  title="A. Known-class recall")
    recall_ax.invert_yaxis()
    recall_ax.xaxis.set_major_formatter(PercentFormatter(xmax=1))
    recall_ax.grid(axis="x", alpha=.2)

    roc_ax.plot([0, 1], [0, 1], color="#919aa3", linestyle="--", linewidth=.85, zorder=1)
    for method, (name, color) in SCORE_STYLES.items():
        for i, run in enumerate(runs):
            ranking = run["metrics"][method]["ranking"]
            if ranking["n_known"] != known["n"] or ranking["n_unknown"] != unknown:
                raise ValueError("ROC denominators differ from the test partition")
            curve = ranking["curves"]["unknown_roc"]
            mean_auc = report["mean_open_set"][method]["auroc"]
            label = f"{name} ({mean_auc:.3f})" if i == 0 else None
            roc_ax.plot(curve["fpr"], curve["tpr"], color=color, alpha=.72,
                        linewidth=1.25, label=label)
    roc_ax.set(xlim=(-.02, 1.02), ylim=(-.02, 1.02),
               xlabel=f"Known flagged as unknown (n={known['n']})",
               ylabel=f"Chirp flagged as unknown (n={unknown})", title="B. Unknown-positive ROC")
    for axis in (roc_ax.xaxis, roc_ax.yaxis):
        axis.set_major_formatter(PercentFormatter(xmax=1))
    roc_ax.grid(alpha=.2)
    roc_ax.legend(loc="lower right", fontsize=8, title="Mean AUROC over seeds", title_fontsize=8)
    fig.suptitle("Fraunhofer FIOT lab recordings · same test records for all three seeds", fontsize=11)

    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    fig.savefig(directory / "fiot_cnn_results.png", dpi=240)
    fig.savefig(directory / "fiot_cnn_results.pdf", metadata={"CreationDate": None, "ModDate": None})
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    plot(args.summary, args.out)

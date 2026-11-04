"""Aggregate fixed CPU campaign outputs without fitting or choosing a scorer."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


def summarize(out):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    out = Path(out)
    campaign = json.loads((out / "campaign.json").read_text())
    cfg = campaign["config"]
    seeds, methods = cfg["training_seeds"], cfg["methods"]
    results = []
    for seed, expected in zip(seeds, campaign["resolved_fits"]):
        path = out / f"seed-{seed}/results.json"
        result = json.loads(path.read_text())
        if (result["config"] != expected or result["runtime"]["device"] != "cpu"
                or result["source"]["files_sha256"] != campaign["scientific_sources_sha256"]):
            raise ValueError("fit does not match the frozen campaign")
        if results and (result["partitions"] != results[0]["partitions"]
                        or result["data_fingerprints"] != results[0]["data_fingerprints"]):
            raise ValueError("seeds do not share identical datasets and partitions")
        results.append(result)
    rows, family_rows = [], []
    for seed, result in zip(seeds, results):
        for method in methods:
            m = result["methods"][method]
            r = m["ranking"]
            rows.append({"seed": seed, "method": method,
                         **{key: r[key] for key in ("unknown_auroc", "unknown_aupr", "oscr_auc",
                                                   "unknown_fpr_at_95_tpr", "n_known", "n_unknown")},
                         **{key: m[key]["mean"] for key in ("known_closed_accuracy", "known_acceptance",
                                                            "unknown_rejection", "false_alarm_on_clean")},
                         "known_macro_f1": m["known_macro_f1_before_rejection"],
                         "threshold": m["threshold"]})
            for family in result["unknown_families"]:
                values = result["methods_by_family"][family][method]
                family_rows.append({"seed": seed, "method": method, "family": family,
                                    **{key: values["ranking"][key] for key in
                                       ("unknown_auroc", "unknown_aupr", "oscr_auc", "n_known", "n_unknown")},
                                    "unknown_rejection": values["unknown_rejection"]["mean"]})
    descriptive = {}
    for method in methods:
        selected = [row for row in rows if row["method"] == method]
        descriptive[method] = {}
        for metric in ("known_closed_accuracy", "unknown_auroc", "unknown_aupr", "oscr_auc",
                       "known_acceptance", "unknown_rejection"):
            values = [row[metric] for row in selected]
            descriptive[method][metric] = {"mean": float(np.mean(values)),
                                           "min": min(values), "max": max(values)}
    summary = {"schema": "CPU-delivery-B1-summary/1", "campaign": cfg["campaign"],
               "campaign_complete": True, "benchmark_complete": False,
               "scope": "Single-polarization B1-dev/2 development; not B2/1",
               "positive_class": "unknown", "score_direction": "higher_is_more_unknown_like",
               "uncertainty": "Three seeds share data. Means/ranges are descriptive; no seed CI or AUROC CI.",
               "campaign_sha256": hashlib.sha256((out / "campaign.json").read_bytes()).hexdigest(),
               "result_sha256": {str(seed): hashlib.sha256((out / f"seed-{seed}/results.json").read_bytes()).hexdigest()
                                 for seed in seeds},
               "config": cfg, "partitions": results[0]["partitions"],
               "unknown_family_counts": results[0]["unknown_family_counts"],
               "runtime": results[0]["runtime"], "data_fingerprints": results[0]["data_fingerprints"],
               "pooled_rows": rows, "family_rows": family_rows, "descriptive_seed_summary": descriptive,
               "execution": [json.loads(line) for line in (out / "execution.jsonl").read_text().splitlines()]}
    (out / "summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n")
    lines = ["# CPU-delivery-B1/1: actual development results", "",
             "Single-polarization B1-dev/2. Not the full eight-class B2 benchmark.",
             "Unknown is positive; larger scores mean more unknown-like. All three seeds and scorers retained.", "",
             "| Seed | Scorer | Known accuracy | Unknown AUROC | AP | OSCR | Known acceptance | Unknown rejection |",
             "|---|---|---|---|---|---|---|---|"]
    for row in rows:
        vals = [row[k] for k in ("known_closed_accuracy", "unknown_auroc", "unknown_aupr", "oscr_auc",
                                "known_acceptance", "unknown_rejection")]
        lines.append(f"| {row['seed']} | {row['method']} | " + " | ".join(f"{v:.4f}" for v in vals) + " |")
    lines += ["", "## Actual populations", "", "| Role | Samples | Scenario groups |", "|---|---|---|"]
    for role, part in summary["partitions"].items():
        lines.append(f"| {role} | {part['n_samples']} | {len(part['scenario_ids'])} |")
    lines += ["", "## Unknown families", "", "| Seed | Scorer | Family | n unknown | AUROC | Rejection |",
              "|---|---|---|---|---|---|"]
    for row in family_rows:
        lines.append(f"| {row['seed']} | {row['method']} | {row['family']} | {row['n_unknown']} | "
                     f"{row['unknown_auroc']:.4f} | {row['unknown_rejection']:.4f} |")
    lines += ["", "## Limits", "", summary["uncertainty"],
              "Known acceptance and accuracy use all known test samples; rejection uses all unknown samples.",
              "Wideband noise can be equivalent to a higher noise floor; pooled and per-family results differ.",
              "No H1/H2/H3 B2 advantage, measured GEO transfer or production performance is established.",
              "Negative results are preserved; no test-driven threshold, score-direction or model change was made.", ""]
    (out / "summary.md").write_text("\n".join(lines))
    figures = out / "figures"
    figures.mkdir(exist_ok=True)

    def save(fig, name):
        for extension in ("png", "pdf"):
            fig.savefig(figures / f"{name}.{extension}", dpi=180, bbox_inches="tight")
        plt.close(fig)

    fig, axes = plt.subplots(1, len(seeds), figsize=(12, 3.6), constrained_layout=True)
    for ax, seed, result in zip(axes, seeds, results):
        for method in methods:
            rank = result["methods"][method]["ranking"]
            curve = rank["curves"]["unknown_roc"]
            ax.plot(curve["fpr"], curve["tpr"], label=f"{method}: {rank['unknown_auroc']:.3f}")
        ax.plot([0, 1], [0, 1], "k--", linewidth=.7)
        ax.set(title=f"Training seed {seed}", xlabel="Known false-positive fraction",
               ylabel="Unknown true-positive fraction", xlim=(0, 1), ylim=(0, 1))
        ax.legend(fontsize=8)
    fig.suptitle("B1 development: pooled unknown ROC (fixed data, three training seeds)")
    save(fig, "cpu_unknown_roc")
    families = results[0]["unknown_families"]
    fig, axes = plt.subplots(1, len(seeds), figsize=(12, 3.8), constrained_layout=True)
    for ax, seed, result in zip(axes, seeds, results):
        values = np.array([[result["methods_by_family"][family][method]["ranking"]["unknown_auroc"]
                            for method in methods] for family in families])
        ax.imshow(values, vmin=0, vmax=1, cmap="viridis", aspect="auto")
        ax.set_xticks(range(len(methods)), methods, rotation=20)
        ax.set_yticks(range(len(families)), families if seed == seeds[0] else [""] * len(families))
        ax.set_title(f"Training seed {seed}")
        for i in range(len(families)):
            for j in range(len(methods)):
                ax.text(j, i, f"{values[i,j]:.3f}", ha="center", va="center",
                        color="black" if values[i,j] > .65 else "white")
    fig.suptitle("B1 development: per-family unknown AUROC (chance = 0.5)")
    save(fig, "cpu_family_auroc")
    print(f"Wrote {out / 'summary.md'} and four PNG/PDF figure files", flush=True)
    return summary

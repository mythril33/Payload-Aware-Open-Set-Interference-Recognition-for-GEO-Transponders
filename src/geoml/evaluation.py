"""Known-class accuracy and held-out-family rejection for the first open-set slice."""
from __future__ import annotations

import numpy as np

from .calibration import RejectionCalibration
from .metrics import cluster_ci, macro_f1
from .openset import unknown_scores
from .openset_metrics import ranking_metrics


def _rate(values: np.ndarray, groups: np.ndarray) -> dict:
    n = len(values)
    return {"mean": float(np.mean(values)) if n else None,
            "ci95": list(cluster_ci(values.astype(float), groups)) if n else None,
            "n_samples": n, "n_scenarios": int(len(np.unique(groups)))}


def evaluate(known_logits: np.ndarray, unknown_logits: np.ndarray, labels: np.ndarray,
             known_groups: np.ndarray, unknown_groups: np.ndarray,
             calibration: RejectionCalibration) -> dict:
    """Evaluate a frozen calibrator. Unknown rejection has unknown as positive.

    Intervals resample scenario groups at a fixed model and threshold; they do
    not include model-training or threshold-estimation uncertainty.
    """
    known_scores = unknown_scores(known_logits, calibration.method, calibration.temperature)
    unknown = unknown_scores(unknown_logits, calibration.method, calibration.temperature)
    if known_logits.shape[1] != unknown_logits.shape[1]:
        raise ValueError("known and unknown logits must use the same class order")
    return evaluate_scores(known_logits, known_scores, unknown, labels, known_groups, unknown_groups, calibration)


def evaluate_scores(known_logits: np.ndarray, known_scores: np.ndarray, unknown: np.ndarray,
                    labels: np.ndarray, known_groups: np.ndarray, unknown_groups: np.ndarray,
                    calibration: RejectionCalibration) -> dict:
    """Evaluate precomputed unknown scores with fixed known-class predictions."""
    known_logits = np.asarray(known_logits)
    if (known_logits.ndim != 2 or known_logits.shape[1] < 2 or not len(known_logits)
            or known_logits.dtype.kind not in "iuf" or not np.isfinite(known_logits).all()):
        raise ValueError("known logits must be finite numeric [N,K] with K >= 2")
    known_scores, unknown = np.asarray(known_scores), np.asarray(unknown)
    labels, known_groups, unknown_groups = map(np.asarray, (labels, known_groups, unknown_groups))
    if (labels.shape != (len(known_logits),) or labels.shape != known_scores.shape
            or known_groups.shape != labels.shape or unknown_groups.shape != unknown.shape):
        raise ValueError("labels and scenario groups must match the score arrays")
    k = known_logits.shape[1]
    if not np.issubdtype(labels.dtype, np.integer) or not np.all((labels >= 0) & (labels < k)):
        raise ValueError("known labels must be valid integer class indices")
    prediction = known_logits.argmax(axis=1)
    accepted = calibration.accept(known_scores)
    correct = prediction == labels
    clean = labels == 0
    return {
        "threshold": calibration.threshold,
        "target_known_acceptance": calibration.target_acceptance,
        "known_acceptance": _rate(accepted, known_groups),
        "known_closed_accuracy": _rate(correct, known_groups),
        "accepted_known_accuracy": _rate(correct[accepted], known_groups[accepted]),
        "known_correct_acceptance": _rate(accepted & correct, known_groups),
        "known_macro_f1_before_rejection": macro_f1(labels, prediction, k),
        "known_macro_f1_after_rejection": macro_f1(labels, np.where(accepted, prediction, k), k + 1),
        "unknown_rejection": _rate(~calibration.accept(unknown), unknown_groups),
        "false_alarm_on_clean": _rate((~accepted | (prediction != 0))[clean], known_groups[clean]),
        "ranking": ranking_metrics(known_scores, unknown, correct),
    }


def report(result: dict) -> str:
    def percentage(value):
        return "—" if value is None else f"{100 * value:.1f}%"

    lines = ["# Open-set development experiment", "",
             f"Protocol: `{result['protocol']}`. Held-out family: `{result['holdout_label']}`.",
             f"Known classes: {', '.join(result['known_labels'])}.", "",
             f"Unknown families: {', '.join(result.get('unknown_families', [result['holdout_label']]))}.", "",
             "Development run using single-polarization A1 observations; not the final eight-class benchmark.",
             "Unknown-family samples are excluded from optimization, model selection and rejection calibration.",
             "Validation scenario groups for model selection and calibration are disjoint.", "",
             "| Method | Known acceptance | Accepted-known accuracy | Unknown rejection | Clean false alarm |",
             "|---|---|---|---|---|"]
    for name, values in result["methods"].items():
        rates = [values[key]["mean"] for key in ("known_acceptance", "accepted_known_accuracy", "unknown_rejection", "false_alarm_on_clean")]
        lines.append(f"| {name} | " + " | ".join(percentage(value) for value in rates) + " |")
    if all("ranking" in values for values in result["methods"].values()):
        lines += ["", "## Unknown ranking and open-set classification", "",
                  "AUROC and average precision use unknown as positive. OSCR combines correct known classification with unknown false acceptance.",
                  "The curves summarize test ranking; deployment thresholds remain fixed from known calibration data.", "",
                  "| Population | Method | Unknown AUROC | Unknown AP | OSCR AUC |", "|---|---|---|---|---|"]
        for population, methods in [("pooled", result["methods"]), *result.get("methods_by_family", {}).items()]:
            for method, values in methods.items():
                metric = values["ranking"]
                lines.append(f"| {population} | {method} | {metric['unknown_auroc']:.3f} | {metric['unknown_aupr']:.3f} | {metric['oscr_auc']:.3f} |")
    lines += ["", "Known acceptance counts all known test events; accepted-known accuracy is conditional on acceptance.",
              "Clean false alarm includes rejection of clean samples and predictions of a non-clean known class.",
              "JSON includes counts and scenario-bootstrap intervals at a fixed trained model and threshold.",
              "A validation acceptance target does not guarantee the same test acceptance.", "", "## Partitions", "",
              "| Role | Samples | Scenario groups |", "|---|---|---|"]
    for role, values in result["partitions"].items():
        lines.append(f"| {role} | {values['n_samples']} | {len(values['scenario_ids'])} |")
    lines += ["", f"Source data complete: `{result['source_data_complete']}`.",
              f"Experiment fingerprint: `{result['experiment_fingerprint']}`.", ""]
    return "\n".join(lines)

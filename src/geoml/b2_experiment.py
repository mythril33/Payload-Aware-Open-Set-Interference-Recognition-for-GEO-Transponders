"""Known-class B2 learning slice on frozen roles with the five-channel model.

    python -m geoml.b2_experiment --config configs/b2_feat.json \
        --data data/b2-feat-pilot --out runs/b2-feat-pilot

Roles follow P18 §4 exactly: ``train`` fits weights and Mahalanobis statistics,
``val-select`` picks the checkpoint, ``val-calib`` (known classes only) sets the
MSP/energy/Mahalanobis acceptance thresholds and the clean alarm threshold, and
``test`` is evaluated once. Matched views (``co``, ``dual``, ``dual_residual``)
share data, budget and seeds. The optional independent ``plan_consistency``
head is trained and reported separately (P18 §7a).

With ``--unknown-data`` pointing at a verified B2-test/1 artifact bound to the
same known data, the test-only families are scored with the *same* frozen
checkpoints, scorers and thresholds: per-family and pre-registered-group AUROC,
AP, OSCR and FPR@95TPR (unknown positive), thresholded rejection, and the benign
``cid_overlay`` control (expected decision ``clean``). Without it those metrics
are ``null`` with zero counts. The matched ASI set is a later stage.
"""
from __future__ import annotations

import argparse
import json
import platform
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
import torch

from geosim.b2_dataset import b2_fingerprint, load_b2_split, read_b2_manifest
from geosim.b2_protocol import (BASE_PROTOCOL, BENIGN_TEST_FAMILIES, EQUIVALENCE_LIMITED_UNKNOWN, FEATURE_PROTOCOL,
                                LABELS, NEAR_UNKNOWN, PLAN_CONSISTENCY, role_for_group)
from geosim.b2_matched_dataset import b2_matched_fingerprint, load_b2_matched_split, read_b2_matched_manifest
from geosim.b2_scenarios import MATCHED_BIN_NAMES, MATCHED_BINS, MATCHED_LABELS
from geosim.b2_test_dataset import b2_test_fingerprint, load_b2_test_split, read_b2_test_manifest

from .artifacts import fingerprint
from .calibration import RejectionCalibration, calibrate_scores
from .data import VIEW_CHANNELS
from .experiment import _sha256, _source_identity, _write_json
from .mahalanobis import MahalanobisScorer, fit_mahalanobis
from .metrics import cluster_ci, confusion, expected_calibration_error, macro_f1, threshold_at_pfa
from .openset import unknown_scores
from .openset_metrics import ranking_metrics
from .train import TrainConfig, fit, infer, load, save

ROLES = ("train", "val-select", "val-calib", "test")
METHODS = ("msp", "energy", "mahalanobis")
VIEWS = ("co", "dual", "dual_residual")


@dataclass(frozen=True)
class B2ExperimentConfig:
    protocol: str = FEATURE_PROTOCOL
    views: tuple[str, ...] = VIEWS
    plan_consistency: bool = True
    methods: tuple[str, ...] = METHODS
    target_acceptance: float = 0.95
    pfa: float = 0.05
    mahalanobis_regularization: float = 0.1
    training: dict = field(default_factory=lambda: {"epochs": 3, "batch": 8, "width": 8, "seed": 0,
                                                    "center_loss_weight": 0.005})

    def __post_init__(self):
        if self.protocol not in (BASE_PROTOCOL, FEATURE_PROTOCOL):
            raise ValueError(f"protocol must be {BASE_PROTOCOL} or {FEATURE_PROTOCOL}")
        if (not isinstance(self.views, (list, tuple)) or not self.views
                or any(view not in VIEWS for view in self.views) or len(set(self.views)) != len(self.views)):
            raise ValueError(f"views must be unique choices from {VIEWS}")
        if self.protocol == BASE_PROTOCOL and "dual_residual" in self.views:
            raise ValueError("the dual_residual view requires the B2-feat/1 stage with a stored residual")
        if (not isinstance(self.methods, (list, tuple)) or not self.methods
                or any(method not in METHODS for method in self.methods) or len(set(self.methods)) != len(self.methods)):
            raise ValueError(f"methods must be unique choices from {METHODS}")
        for name in ("target_acceptance", "pfa"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 < value < 1:
                raise ValueError(f"{name} must be between 0 and 1")
        if (isinstance(self.mahalanobis_regularization, bool) or not isinstance(self.mahalanobis_regularization, (int, float))
                or not 0 < self.mahalanobis_regularization <= 1):
            raise ValueError("mahalanobis_regularization must be in (0, 1]")
        if not isinstance(self.plan_consistency, bool):
            raise ValueError("plan_consistency must be a boolean")
        if not isinstance(self.training, dict) or set(self.training) & {"labels", "input_mode", "plan_consistency"}:
            raise ValueError("labels, input_mode and plan_consistency are set by the experiment, not the training block")
        if "center_loss_weight" not in self.training:
            raise ValueError("center_loss_weight must be frozen explicitly in the training configuration before training")
        object.__setattr__(self, "views", tuple(self.views))
        object.__setattr__(self, "methods", tuple(self.methods))
        for view in self.views:
            self.train_config(view)

    def train_config(self, view: str) -> TrainConfig:
        return TrainConfig(labels=LABELS, input_mode=view, plan_consistency=self.plan_consistency, **self.training)

    def resolved(self) -> dict:
        training = asdict(self.train_config(self.views[0]))
        for name in ("labels", "input_mode", "plan_consistency"):
            training.pop(name)
        return {**asdict(self), "training": training}

    @classmethod
    def from_file(cls, path):
        try:
            raw = json.loads(Path(path).read_text())
            if not isinstance(raw, dict):
                raise ValueError("experiment configuration must be a JSON object")
            return cls(**raw)
        except TypeError as error:
            raise ValueError(f"invalid experiment configuration: {error}") from error


def _check_roles(parts):
    for role, part in parts.items():
        seeds = np.unique(part["seed"])
        if any(role_for_group(int(seed)) != role for seed in seeds):
            raise ValueError(f"{role} contains scenario groups outside its frozen B2/1 range")
        if set(part["label"].tolist()) != set(range(len(LABELS))):
            raise ValueError(f"{role} must include every known label")
    names = list(parts)
    for i, left in enumerate(names):
        for right in names[i + 1:]:
            if np.intersect1d(parts[left]["seed"], parts[right]["seed"]).size:
                raise ValueError(f"scenario group leakage between {left} and {right}")


def _summary(parts):
    return {role: {"n_samples": int(len(part["label"])), "scenario_ids": [int(s) for s in np.unique(part["seed"])],
                   "per_label": {label: int(np.sum(part["label"] == index)) for index, label in enumerate(LABELS)},
                   "n_planned_carrier_missing": int(np.sum(part["plan_consistency"] == 1))}
            for role, part in parts.items()}


def _rate(values, groups):
    values = np.asarray(values, dtype=float)
    if not len(values):
        return {"mean": None, "ci95": None, "n_samples": 0, "n_scenarios": 0}
    ci = list(cluster_ci(values, groups)) if len(np.unique(groups)) > 1 else None
    return {"mean": float(values.mean()), "ci95": ci, "n_samples": int(len(values)),
            "n_scenarios": int(len(np.unique(groups)))}


def _softmax(logits):
    shifted = logits.astype(np.float64) - logits.max(axis=1, keepdims=True)
    exponent = np.exp(shifted)
    return exponent / exponent.sum(axis=1, keepdims=True)


def _plan_metrics(plan_logits, targets, groups):
    if plan_logits is None:
        return None
    predicted = plan_logits[:, 0] > 0
    actual = targets == 1
    positives = int(actual.sum())
    both_classes = 0 < positives < len(targets)
    # A constant head scores 100 % when one class is absent; report null instead (AGENTS.md).
    accuracy = _rate(predicted == actual, groups) if both_classes else {
        "mean": None, "ci95": None, "n_samples": int(len(targets)), "n_scenarios": int(len(np.unique(groups))),
        "note": "undefined: only one plan-consistency class present"}
    return {"positive_class": PLAN_CONSISTENCY[1], "decision_rule": "auxiliary logit > 0",
            "accuracy": accuracy,
            "recall": None if not positives else float(np.mean(predicted[actual])),
            "precision": None if not predicted.any() else float(np.mean(actual[predicted])),
            "n_positive": positives, "n_predicted_positive": int(predicted.sum()), "n_samples": int(len(targets))}


def _rejection(method, calib_scores, test_scores, labels, predictions, groups, provenance, config, families=None):
    calibration = calibrate_scores(calib_scores, method, config.target_acceptance, provenance=provenance)
    accepted = calibration.accept(test_scores)
    metrics = {
        "calibration": calibration.to_dict(),
        "known_acceptance": _rate(accepted, groups),
        "accepted_known_accuracy": _rate((predictions == labels)[accepted], groups[accepted]),
        "per_class_acceptance": {label: _rate(accepted[labels == index], groups[labels == index])
                                 for index, label in enumerate(LABELS)},
        "unknown_rejection": None, "n_unknown": 0, "families": None,
        "note": "no unknown or benign test-only families were supplied"}
    if families is not None:
        metrics.update(_family_metrics(method, calibration, test_scores, labels, predictions, families))
    return calibration, metrics


def _unknown_families(unknown):
    """Split the B2-test/1 split into named families with their pre-registered groups."""
    names = unknown["families"]
    return {name: {"index": index, "group": ("near" if name in NEAR_UNKNOWN else
                                             "equivalence_limited" if name in EQUIVALENCE_LIMITED_UNKNOWN else "benign"),
                   "mask": unknown["family"] == index}
            for index, name in enumerate(names)}


def _family_metrics(method, calibration, known_test_scores, labels, predictions, families):
    """Open-set metrics per family and per pre-registered group; unknown is the positive class.

    ``cid_overlay`` is a benign control and is excluded from every pooled unknown
    number: for it the reported quantities are the clean-acceptance rate (predicted
    clean and accepted) and the carrier-under-carrier call rate.
    """
    correct = predictions == labels
    scores, groups, info = families["scores"], families["groups"], families["info"]
    per_family, pooled_scores, pooled_groups = {}, [], []
    for name, item in info.items():
        mask = item["mask"]
        family_scores, family_groups = scores[mask], groups[mask]
        rejected = ~calibration.accept(family_scores)
        entry = {"pre_registered_group": item["group"], "n": int(mask.sum()),
                 "ranking": ranking_metrics(known_test_scores, family_scores, correct) if mask.any() else None,
                 "rejection_at_threshold": _rate(rejected, family_groups)}
        if item["group"] == "benign":
            family_predictions = families["predictions"][mask]
            entry.update(expected_decision="clean",
                         clean_acceptance=_rate((family_predictions == 0) & ~rejected, family_groups),
                         carrier_under_carrier_calls=_rate(family_predictions == LABELS.index("carrier_under_carrier"), family_groups),
                         rejected_as_unknown=_rate(rejected, family_groups))
        else:
            entry["expected_decision"] = "unknown"
        if item["group"] == "near" and mask.any():
            pooled_scores.append(family_scores)
            pooled_groups.append(family_groups)
        per_family[name] = entry
    pooled = None
    if pooled_scores:
        pooled_scores, pooled_groups = np.concatenate(pooled_scores), np.concatenate(pooled_groups)
        pooled = {"families": [name for name, item in info.items() if item["group"] == "near" and item["mask"].any()],
                  "ranking": ranking_metrics(known_test_scores, pooled_scores, correct),
                  "rejection_at_threshold": _rate(~calibration.accept(pooled_scores), pooled_groups)}
    unknown_mask = np.concatenate([item["mask"] for name, item in info.items() if item["group"] != "benign"]).any() if info else False
    n_near = int(sum(int(item["mask"].sum()) for item in info.values() if item["group"] == "near"))
    n_equivalence = int(sum(int(item["mask"].sum()) for item in info.values() if item["group"] == "equivalence_limited"))
    return {"families": per_family, "pooled_near": pooled, "n_unknown": n_near,
            "n_unknown_equivalence_limited": n_equivalence, "n_unknown_all_families": n_near + n_equivalence,
            "unknown_rejection": pooled["rejection_at_threshold"] if pooled else None,
            "unknown_rejection_denominator": "pooled near families only",
            "note": "pooled numbers use near families only; wideband_noise is equivalence-limited and reported separately; "
                    "cid_overlay is a benign control" if unknown_mask else "no unknown families"}


def _load_unknown(unknown_data, manifest, identity, config):
    """Verify the B2-test/1 artifact and its binding to the known data in use."""
    test_manifest = read_b2_test_manifest(unknown_data)
    binding = test_manifest["request"]["known"]
    if binding["known_data_fingerprint"] != identity:
        raise ValueError("the test-only artifact is bound to a different known dataset")
    if test_manifest["config"] != manifest["config"] or test_manifest.get("cancellation") != manifest.get("cancellation"):
        raise ValueError("test-only artifact physics or cancellation differ from the known data")
    unknown = load_b2_test_split(unknown_data)
    if config.protocol == FEATURE_PROTOCOL and "residual" not in unknown:
        raise ValueError("B2-feat/1 experiments require the stored residual in the test-only artifact")
    return test_manifest, unknown


def _load_matched(matched_data, manifest, identity, config):
    """Verify the B2-match/1 artifact and its binding to the known data in use (test-matched role only)."""
    matched_manifest = read_b2_matched_manifest(matched_data)
    binding = matched_manifest["request"]["known"]
    if binding["known_data_fingerprint"] != identity:
        raise ValueError("the matched artifact is bound to a different known dataset")
    if matched_manifest["config"] != manifest["config"] or matched_manifest.get("cancellation") != manifest.get("cancellation"):
        raise ValueError("matched artifact physics or cancellation differ from the known data")
    matched = load_b2_matched_split(matched_data)
    if any(role_for_group(int(seed)) != "test-matched" for seed in np.unique(matched["seed"])):
        raise ValueError("matched groups must belong to the frozen test-matched role")
    if config.protocol == FEATURE_PROTOCOL and "residual" not in matched:
        raise ValueError("B2-feat/1 experiments require the stored residual in the matched artifact")
    return matched_manifest, matched


def _pair_metrics(predictions, accepted, labels, groups, mask):
    """ASI-versus-unauthorized decisions among matched pair samples; nothing is dropped from the denominator."""
    asi, unauth = LABELS.index("adjacent_satellite"), LABELS.index("unauthorized")
    out = {"denominator": "all matched adjacent_satellite and unauthorized samples (clean variants excluded)",
           "n_samples": int(mask.sum()), "n_scenarios": int(len(np.unique(groups[mask])))}
    if not mask.any():
        return {**out, "two_by_two": None, "prediction_breakdown": None, "pair_accuracy": None,
                "pair_accuracy_among_pair_predictions": None, "pair_accuracy_accepted_only": None,
                "rejected_fraction": None, "note": "no matched pair samples"}
    truth, pred, acc, grp = labels[mask], predictions[mask], accepted[mask], groups[mask]
    two_by_two = {t_name: {p_name: int(np.sum((truth == t) & (pred == p))) for p_name, p in (("adjacent_satellite", asi), ("unauthorized", unauth))}
                  for t_name, t in (("adjacent_satellite", asi), ("unauthorized", unauth))}
    breakdown = {t_name: {"predicted_clean": int(np.sum((truth == t) & (pred == 0))),
                          "predicted_other_known": int(np.sum((truth == t) & (pred != 0) & (pred != asi) & (pred != unauth))),
                          "predicted_pair_class": int(np.sum((truth == t) & ((pred == asi) | (pred == unauth)))),
                          "rejected_as_unknown": int(np.sum((truth == t) & ~acc)), "n": int(np.sum(truth == t))}
                 for t_name, t in (("adjacent_satellite", asi), ("unauthorized", unauth))}
    within = (pred == asi) | (pred == unauth)
    return {**out, "two_by_two": two_by_two, "prediction_breakdown": breakdown,
            "pair_accuracy": _rate(pred == truth, grp),
            "pair_accuracy_among_pair_predictions": _rate((pred == truth)[within], grp[within]),
            "pair_accuracy_accepted_only": _rate((pred == truth)[acc], grp[acc]),
            "rejected_fraction": _rate(~acc, grp)}


def _matched_metrics(matched, outputs, calibrations, scorer, alarm_threshold, natural_test, natural_predictions):
    """Metrics for the K17c matched set with the frozen checkpoint and thresholds of one view."""
    labels = matched["label"].astype(np.int64)
    groups = matched["seed"]
    bins = matched["matched_bin"].astype(np.int64)
    consistency = np.asarray(matched["plan_consistency"]).astype(np.int64)
    asi_active = np.array([record.get("matched", {}).get("asi_overlap_fraction_active", np.nan) for record in matched["meta"]], dtype=float)
    predictions = outputs["logits"].argmax(axis=1)
    probabilities = _softmax(outputs["logits"])
    alarm = 1.0 - probabilities[:, 0] > alarm_threshold
    pair_mask = labels != 0
    per_method = {}
    for method, calibration in calibrations.items():
        scores = scorer.score(outputs["embedding"]) if method == "mahalanobis" else unknown_scores(outputs["logits"], method)
        accepted = calibration.accept(scores)
        per_method[method] = {
            "confusion_with_rejection": {LABELS[t]: {**{LABELS[p]: int(np.sum((labels == t) & (predictions == p) & accepted)) for p in range(len(LABELS))},
                                                     "rejected": int(np.sum((labels == t) & ~accepted))}
                                         for t in sorted(set(labels.tolist()))},
            "pair": _pair_metrics(predictions, accepted, labels, groups, pair_mask),
            "per_bin": {name: _pair_metrics(predictions, accepted, labels, groups, pair_mask & (bins == index))
                        for index, name in enumerate(MATCHED_BIN_NAMES)},
            # P18 §7a K17c intersections: groups with a missing planned carrier, and ASI variants whose band
            # holds no transmitted carrier (observationally an unauthorized-like carrier under a "planned" mask).
            "per_plan_consistency": {PLAN_CONSISTENCY[value]: _pair_metrics(predictions, accepted, labels, groups, pair_mask & (consistency == value))
                                     for value in (0, 1)},
            "asi_over_absent_carrier": _pair_metrics(predictions, accepted, labels, groups,
                                                     pair_mask & np.isfinite(asi_active) & (asi_active == 0.0)),
            "known_acceptance_matched": _rate(accepted, groups)}
    confusion_full = {LABELS[t]: {LABELS[p]: int(np.sum((labels == t) & (predictions == p))) for p in range(len(LABELS))}
                      for t in sorted(set(labels.tolist()))}
    per_class = {}
    for index in sorted(set(labels.tolist())):
        name = LABELS[index]
        true_mask, pred_mask = labels == index, predictions == index
        per_class[name] = {"recall": _rate(pred_mask[true_mask], groups[true_mask]),
                           "precision": _rate(true_mask[pred_mask], groups[pred_mask]) if pred_mask.any() else
                           {"mean": None, "ci95": None, "n_samples": 0, "n_scenarios": 0, "note": "never predicted"},
                           "n_true": int(true_mask.sum()), "n_predicted": int(pred_mask.sum())}
    per_bin_unconditional = {}
    for index, name in enumerate(MATCHED_BIN_NAMES):
        sel = bins == index
        per_bin_unconditional[name] = {"n_samples": int(sel.sum()), "n_groups": int(len(np.unique(groups[sel]))),
                                       "accuracy": _rate((predictions == labels)[sel], groups[sel]),
                                       "recall": {LABELS[t]: _rate((predictions == labels)[sel & (labels == t)], groups[sel & (labels == t)])
                                                  for t in sorted(set(labels.tolist()))}}
    natural = None
    if natural_test is not None:
        n_labels, n_groups, n_pred = natural_test["label"].astype(np.int64), natural_test["seed"], natural_predictions
        natural = {"denominator": "natural test role, same checkpoint; natural carriers are wider (1-28.8 Mbaud) than the matched ones (<= 6 Mbaud)", "classes": {}}
        for name in ("adjacent_satellite", "unauthorized"):
            index = LABELS.index(name)
            ci = np.array([record.get("event", {}).get("c_over_i_psd_db", np.nan) if lab == index else np.nan
                           for record, lab in zip(natural_test["meta"], n_labels)], dtype=float)
            sel = n_labels == index
            entry = {"recall_overall": _rate((n_pred == n_labels)[sel], n_groups[sel]),
                     "recall_by_matched_bin": {}}
            for b_index, b_name in enumerate(MATCHED_BIN_NAMES):
                lo, hi = MATCHED_BINS[b_index]
                in_bin = sel & np.isfinite(ci) & (ci >= lo) & ((ci < hi) if b_index < 2 else (ci <= hi))
                entry["recall_by_matched_bin"][b_name] = _rate((n_pred == n_labels)[in_bin], n_groups[in_bin])
            natural["classes"][name] = entry
    return {"n_samples": int(len(labels)), "n_groups": int(len(np.unique(groups))),
            "per_bin_groups": {name: int(len(np.unique(groups[bins == index]))) for index, name in enumerate(MATCHED_BIN_NAMES)},
            "unconditional_accuracy": _rate(predictions == labels, groups),
            "confusion": confusion_full, "per_class": per_class, "per_bin": per_bin_unconditional,
            "clean_false_alarm": _rate(alarm[labels == 0], groups[labels == 0]),
            "event_alarm": _rate(alarm[pair_mask], groups[pair_mask]),
            "by_method": per_method, "natural_comparison": natural,
            "n_asi_over_absent_carrier": int(np.sum(np.isfinite(asi_active) & (asi_active == 0.0) & (labels == LABELS.index("adjacent_satellite")))),
            "conventions": {"unconditional": "argmax over the eight known classes, no rejection",
                            "pair": "2x2 among samples whose true label is adjacent_satellite or unauthorized; clean/other/rejected predictions are counted, not dropped; pair_accuracy is threshold-free argmax, pair_accuracy_accepted_only uses the method's threshold",
                            "bin_edges": "frozen K17c C/I_psd bins [4,7), [7,10), [10,13]",
                            "natural_comparison": "natural test role scored with the same checkpoint; natural events differ from the matched set in level AND carrier width (matched Rs <= 6 Mbaud by joint feasibility)",
                            "ci": "scenario-group bootstrap with fixed weights and thresholds; null below two groups"}}


def _select_representatives(matched, seed=20261021, per_bin=3):
    """Predeclared selection rule for paired spectrogram figures: fixed seed, up to three groups per bin."""
    rng = np.random.default_rng([seed])
    groups_by_bin = {}
    for group, bin_index in zip(matched["seed"].tolist(), matched["matched_bin"].tolist()):
        groups_by_bin.setdefault(int(bin_index), set()).add(int(group))
    selected = {}
    for index, name in enumerate(MATCHED_BIN_NAMES):
        candidates = sorted(groups_by_bin.get(index, ()))
        if candidates:
            picked = rng.choice(candidates, size=min(per_bin, len(candidates)), replace=False)
            selected[name] = sorted(int(g) for g in picked)
        else:
            selected[name] = []
    return {"rule": f"numpy default_rng([{seed}]) choice without replacement, up to {per_bin} groups per frozen bin, bins in order",
            "groups": selected}


def _paired_figures(matched, selection, out_dir, view):
    """Co-pol spectrogram triplets (clean / ASI / unauthorized) and the shared mask for the selected groups."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as error:   # pragma: no cover - optional dependency
        return {"written": [], "error": f"matplotlib unavailable: {error}"}
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    index = {(int(seed), int(label)): i for i, (seed, label) in enumerate(zip(matched["seed"], matched["label"]))}
    for bin_name, groups in selection["groups"].items():
        for group in groups:
            fig, axes = plt.subplots(1, 4, figsize=(16, 3.2), constrained_layout=True)
            vmin = vmax = None
            for ax, name in zip(axes[:3], MATCHED_LABELS):
                spec = matched["spec"][index[(group, LABELS.index(name))], 0].astype(np.float32)
                if vmin is None:
                    vmin, vmax = float(np.percentile(spec, 1)), float(np.percentile(spec, 99))
                ax.imshow(spec, aspect="auto", origin="lower", vmin=vmin, vmax=vmax, extent=[-48, 48, 0, spec.shape[0]])
                ax.set_title(f"{name} (group {group}, bin {bin_name} dB)")
                ax.set_xlabel("MHz")
            mask = matched["mask"][index[(group, 0)], 0].astype(np.float32)
            axes[3].plot(np.linspace(-48, 48, mask.shape[-1]), mask)
            axes[3].set_title("co-pol operator plan mask (dB)")
            axes[3].set_xlabel("MHz")
            path = out_dir / f"matched_{view}_{bin_name.replace('-', '_')}_{group}.png"
            fig.savefig(path, dpi=90)
            plt.close(fig)
            written.append(path.name)
    return {"written": written, "directory": str(out_dir)}


def run_b2_experiment(config: B2ExperimentConfig, data, out, *, reuse=False, device="cpu", log=print,
                      unknown_data=None, matched_data=None):
    data, out = Path(data), Path(out)
    manifest = read_b2_manifest(data)
    if manifest["protocol"] != config.protocol or list(manifest["labels"]) != list(LABELS):
        raise ValueError(f"dataset protocol {manifest['protocol']!r} does not match the experiment {config.protocol!r}")
    if manifest["benchmark_complete"] is not False:
        raise ValueError("B2 artifacts must declare benchmark_complete=false in this stage")
    identity = b2_fingerprint(data)
    parts = {role: load_b2_split(data, role) for role in ROLES}
    if config.protocol == FEATURE_PROTOCOL and any("residual" not in part for part in parts.values()):
        raise ValueError("B2-feat/1 splits must carry the stored residual")
    _check_roles(parts)
    summary = _summary(parts)
    test_manifest = unknown = None
    if unknown_data is not None:
        test_manifest, unknown = _load_unknown(unknown_data, manifest, identity, config)
        if not set(np.unique(unknown["seed"]).tolist()) <= set(summary["test"]["scenario_ids"]):
            raise ValueError("test-only families must belong to the known test groups")
        summary["test_only"] = {"n_samples": int(len(unknown["seed"])),
                                "scenario_ids": [int(s) for s in np.unique(unknown["seed"])],
                                "per_family": {name: int(np.sum(unknown["family"] == index))
                                               for index, name in enumerate(unknown["families"])},
                                "n_planned_carrier_missing": int(np.sum(unknown["plan_consistency"] == 1))}
    matched_manifest = matched = None
    if matched_data is not None:
        matched_manifest, matched = _load_matched(matched_data, manifest, identity, config)
        summary["test_matched"] = {"n_samples": int(len(matched["seed"])),
                                   "scenario_ids": [int(s) for s in np.unique(matched["seed"])],
                                   "per_label": {name: int(np.sum(matched["label"] == LABELS.index(name))) for name in MATCHED_LABELS},
                                   "per_bin_groups": {name: int(len(np.unique(matched["seed"][matched["matched_bin"] == i])))
                                                      for i, name in enumerate(MATCHED_BIN_NAMES)},
                                   "n_planned_carrier_missing": int(np.sum(matched["plan_consistency"] == 1))}
    source = _source_identity()
    provenance = {"protocol": config.protocol, "data_fingerprint": identity,
                  "roles": {role: summary[role]["scenario_ids"] for role in ROLES},
                  "source_files_sha256": source["files_sha256"]}
    experiment_identity = fingerprint({"config": config.resolved(), "data": identity,
                                       "source_files_sha256": source["files_sha256"]})
    out.mkdir(parents=True, exist_ok=True)
    methods, decisions = {}, {}
    test = parts["test"]
    labels, groups = test["label"].astype(np.int64), test["seed"]
    clean = labels == 0
    for view in config.views:
        cfg = config.train_config(view)
        path = out / f"model_{view}.pt"
        if path.exists():
            if not reuse:
                raise ValueError(f"{path} already exists; use --reuse or a new output directory")
            fitted = load(path, device=device, expected_config=cfg, expected_provenance=provenance)
            log(f"reusing compatible {view} checkpoint")
        else:
            log(f"training {view} model ({VIEW_CHANNELS[view]} channels)")
            fitted = fit(parts["train"], parts["val-select"], cfg, device=device, log=log)
            fitted.update(provenance=provenance, source_revision=source["revision"])
            save(fitted, path)
            fitted = load(path, device=device, expected_config=cfg, expected_provenance=provenance)
        checkpoint_sha = _sha256(path)
        train_out = infer(fitted, parts["train"])
        calib_out = infer(fitted, parts["val-calib"])
        test_out = infer(fitted, test)
        unknown_out = infer(fitted, unknown) if unknown is not None else None
        matched_out = infer(fitted, matched) if matched is not None else None
        view_calibrations = {}
        scorer_path = out / f"mahalanobis_{view}.npz"
        scorer_provenance = fingerprint({"checkpoint_sha256": checkpoint_sha, "data": identity,
                                         "groups": summary["train"]["scenario_ids"],
                                         "regularization": config.mahalanobis_regularization})
        if scorer_path.exists():
            scorer = MahalanobisScorer.load(scorer_path)
            if scorer.provenance != scorer_provenance:
                raise ValueError(f"{scorer_path} is not bound to this checkpoint and training data")
        else:
            scorer = fit_mahalanobis(train_out["embedding"], parts["train"]["label"].astype(np.int64), len(LABELS),
                                     config.mahalanobis_regularization, provenance=scorer_provenance)
            scorer.save(scorer_path)
        probabilities = _softmax(test_out["logits"])
        predictions = test_out["logits"].argmax(axis=1)
        event_probability = 1.0 - probabilities[:, 0]
        calib_probability = 1.0 - _softmax(calib_out["logits"])[:, 0]
        clean_calibration = parts["val-calib"]["label"] == 0
        alarm_threshold = threshold_at_pfa(calib_probability[clean_calibration], config.pfa)
        alarm = event_probability > alarm_threshold
        rejection = {}
        for method in config.methods:
            if method == "mahalanobis":
                calib_scores, test_scores = scorer.score(calib_out["embedding"]), scorer.score(test_out["embedding"])
            else:
                calib_scores, test_scores = unknown_scores(calib_out["logits"], method), unknown_scores(test_out["logits"], method)
            families = None
            if unknown_out is not None:
                family_scores = (scorer.score(unknown_out["embedding"]) if method == "mahalanobis"
                                 else unknown_scores(unknown_out["logits"], method))
                families = {"scores": family_scores, "groups": unknown["seed"], "info": _unknown_families(unknown),
                            "predictions": unknown_out["logits"].argmax(axis=1)}
            rejection_provenance = fingerprint({"checkpoint_sha256": checkpoint_sha, "data": identity, "method": method,
                                                "groups": summary["val-calib"]["scenario_ids"],
                                                "target_acceptance": config.target_acceptance})
            calibration, metrics = _rejection(method, calib_scores, test_scores, labels, predictions, groups,
                                              rejection_provenance, config, families)
            calibration_path = out / f"rejection_{view}_{method}.json"
            if calibration_path.exists():
                if RejectionCalibration.load(calibration_path) != calibration:
                    raise ValueError(f"{calibration_path} is incompatible with this checkpoint/calibration data")
            else:
                calibration.save(calibration_path)
            rejection[method] = metrics
            view_calibrations[method] = calibration
            decisions.setdefault(view, {})[method] = test_scores
        methods[view] = {"input_channels": VIEW_CHANNELS[view],
                         "accuracy": _rate(predictions == labels, groups),
                         "macro_f1": macro_f1(labels, predictions, len(LABELS)),
                         "confusion": confusion(labels, predictions, len(LABELS)).tolist(),
                         "per_class_recall": {label: _rate((predictions == labels)[labels == index], groups[labels == index])
                                              for index, label in enumerate(LABELS)},
                         "ece": expected_calibration_error(probabilities, labels, 15),
                         "clean_false_alarm": _rate(alarm[clean], groups[clean]),
                         "event_detection": _rate(alarm[~clean], groups[~clean]),
                         "alarm": {"score": "one_minus_softmax_clean", "threshold": alarm_threshold,
                                   "target_clean_pfa": config.pfa, "n_clean_calibration": int(clean_calibration.sum())},
                         "plan_consistency": _plan_metrics(test_out["plan_logits"], test["plan_consistency"], groups),
                         "rejection": rejection, "mahalanobis_scorer": scorer.to_dict(),
                         "open_set": _open_set_summary(rejection),
                         "test_only_alarm": None if unknown_out is None else {
                             name: _rate((1.0 - _softmax(unknown_out["logits"])[:, 0] > alarm_threshold)[item["mask"]],
                                         unknown["seed"][item["mask"]])
                             for name, item in _unknown_families(unknown).items()},
                         "matched": None if matched_out is None else _matched_metrics(
                             matched, matched_out, view_calibrations, scorer, alarm_threshold, test, predictions),
                         "checkpoint_sha256": checkpoint_sha, "training_source_revision": fitted.get("source_revision"),
                         "n_parameters": fitted["n_parameters"], "history": fitted["history"]}
        if matched_out is not None:
            selection = _select_representatives(matched)
            methods[view]["matched"]["representatives"] = {**selection, "figures": _paired_figures(matched, selection, out / "figures", view),
                                                            "predictions": {str(g): {LABELS[int(l)]: LABELS[int(p)] for l, p in
                                                                                     zip(matched["label"][matched["seed"] == g], matched_out["logits"].argmax(axis=1)[matched["seed"] == g])}
                                                                            for groups_ in selection["groups"].values() for g in groups_}}
        decisions[view]["prediction"] = predictions
        decisions[view]["event_probability"] = event_probability
        decisions[view]["alarm"] = alarm
        decisions[view]["plan_logit"] = None if test_out["plan_logits"] is None else test_out["plan_logits"][:, 0]
    result = {"protocol": config.protocol, "parent_protocol": manifest["parent_protocol"], "benchmark_complete": False,
              "test_only_protocol": None if test_manifest is None else test_manifest["protocol"],
              "test_only_fingerprint": None if unknown_data is None else b2_test_fingerprint(unknown_data),
              "matched_protocol": None if matched_manifest is None else matched_manifest["protocol"],
              "matched_fingerprint": None if matched_data is None else b2_matched_fingerprint(matched_data),
              "labels": list(LABELS), "config": config.resolved(), "experiment_fingerprint": experiment_identity,
              "data_fingerprint": identity, "source": source, "partitions": summary, "methods": methods,
              "generation": manifest["config"], "cancellation": manifest.get("cancellation"),
              "receiver_calibration": manifest["calibration"],
              "runtime": {"python": platform.python_version(), "numpy": np.__version__,
                          "torch": str(torch.__version__), "device": device},
              "scope": "Known-class learning slice on frozen B2/1 roles; not the complete open-set benchmark."}
    rows = []
    for index, (label, group, target) in enumerate(zip(labels, groups, test["plan_consistency"])):
        rows.append({"scenario_id": int(group), "true_label": LABELS[int(label)],
                     "plan_consistency": PLAN_CONSISTENCY[int(target)],
                     "views": {view: {"prediction": LABELS[int(values["prediction"][index])],
                                       "event_probability": float(values["event_probability"][index]),
                                       "alarm": bool(values["alarm"][index]),
                                       "plan_logit": None if values["plan_logit"] is None else float(values["plan_logit"][index]),
                                       "unknown_scores": {method: float(values[method][index]) for method in config.methods}}
                               for view, values in decisions.items()}})
    _write_json(out / "config.json", config.resolved())
    _write_json(out / "results.json", result)
    _write_json(out / "results_summary.json", summarize(result))
    _write_json(out / "predictions.json", rows)
    (out / "results.md").write_text(report(result))
    log(f"wrote {out / 'results.md'}")
    return result


SUMMARY_DROPPED = ("curves", "history", "per_class_acceptance", "bins", "files_sha256", "generation",
                   "receiver_calibration", "mahalanobis_scorer", "confusion")


def summarize(result):
    """Small committed copy of ``results.json``: drops only the keys in ``SUMMARY_DROPPED`` (recursively).

    Fingerprints, counts, every rate and every ``null`` are kept, so the committed
    summary traces back to the full run output by identity.
    """
    def prune(value):
        if isinstance(value, dict):
            return {key: prune(item) for key, item in value.items() if key not in SUMMARY_DROPPED}
        if isinstance(value, list):
            return [prune(item) for item in value]
        return value
    return {**prune(result), "summary_rule": {"dropped_keys": list(SUMMARY_DROPPED), "source": "results.json"}}


def _open_set_summary(rejection):
    """Compact per-method ranking numbers (pooled near families); null when no unknowns were supplied."""
    summary = {}
    for method, metrics in rejection.items():
        pooled = metrics.get("pooled_near")
        summary[method] = {"unknown_auroc": None, "unknown_ap": None, "oscr": None, "fpr_at_95_tpr": None,
                           "n_unknown": 0 if not pooled else pooled["ranking"]["n_unknown"],
                           "n_known": None if not pooled else pooled["ranking"]["n_known"],
                           "n_unknown_all_families": metrics.get("n_unknown_all_families", 0),
                           "positive_class": "unknown (near families pooled)"}
        if pooled:
            summary[method].update(unknown_auroc=pooled["ranking"]["unknown_auroc"], unknown_ap=pooled["ranking"]["unknown_aupr"],
                                   oscr=pooled["ranking"]["oscr_auc"], fpr_at_95_tpr=pooled["ranking"]["unknown_fpr_at_95_tpr"])
    return summary


def _percent(rate):
    return "n/a" if rate is None or rate.get("mean") is None else f"{100 * rate['mean']:.1f}% (n={rate['n_samples']})"


def _plan_cell(plan):
    if plan is None:
        return "n/a"
    if plan["accuracy"]["mean"] is None:
        return f"n/a (positives n={plan['n_positive']} of {plan['n_samples']}; undefined)"
    return f"{_percent(plan['accuracy'])} (positives n={plan['n_positive']})"


def report(result):
    lines = [f"# B2 known-class learning slice ({result['protocol']})", "",
             f"Parent protocol `{result['parent_protocol']}`; eight known labels; benchmark complete: **{result['benchmark_complete']}**.", "",
             "Roles are the frozen P18 §4 groups: train fits weights and Mahalanobis statistics, val-select picks the",
             "checkpoint, val-calib (known only) fits acceptance and alarm thresholds, test is evaluated once.",
             ("Test-only families come from a bound B2-test/1 artifact and are scored with the frozen thresholds; the"
              " matched ASI set is a later stage." if result.get("test_only_protocol") else
              "No unknown families, CID overlays or matched ASI sets were supplied; their metrics are null."), "",
             "| View | Channels | Accuracy | Macro-F1 | ECE | Clean false alarm | Event detection | Plan-consistency accuracy |",
             "|---|---|---|---|---|---|---|---|"]
    for view, values in result["methods"].items():
        plan = values["plan_consistency"]
        lines.append(f"| {view} | {values['input_channels']} | {_percent(values['accuracy'])} | {values['macro_f1']:.3f} | "
                     f"{values['ece']['ece']:.3f} | {_percent(values['clean_false_alarm'])} | {_percent(values['event_detection'])} | "
                     f"{_plan_cell(plan)} |")
    lines += ["", "| View | Method | Known acceptance at calibrated threshold | Accuracy on accepted | Unknown rejection (pooled near) |",
              "|---|---|---|---|---|"]
    for view, values in result["methods"].items():
        for method, metrics in values["rejection"].items():
            rejection = metrics["unknown_rejection"]
            lines.append(f"| {view} | {method} | {_percent(metrics['known_acceptance'])} | "
                         f"{_percent(metrics['accepted_known_accuracy'])} | "
                         f"{'null (n_unknown=0)' if rejection is None else _percent(rejection)} |")
    if result.get("test_only_protocol"):
        lines += ["", f"## Test-only families ({result['test_only_protocol']}; unknown is the positive class)", "",
                  "| View | Method | Family | Group | n | AUROC | AP | OSCR | FPR@95TPR | Rejected at threshold |",
                  "|---|---|---|---|---|---|---|---|---|---|"]
        for view, values in result["methods"].items():
            for method, metrics in values["rejection"].items():
                for name, entry in (metrics.get("families") or {}).items():
                    ranking = entry["ranking"]
                    if entry["pre_registered_group"] == "benign":
                        alarm = (values.get("test_only_alarm") or {}).get(name)
                        lines.append(f"| {view} | {method} | {name} | benign (expect clean) | {entry['n']} | – | – | – | – | "
                                     f"{_percent(entry['rejected_as_unknown'])}; clean accepted {_percent(entry['clean_acceptance'])}; "
                                     f"CuC calls {_percent(entry['carrier_under_carrier_calls'])}; event alarm {_percent(alarm)} |")
                    elif ranking is not None:
                        lines.append(f"| {view} | {method} | {name} | {entry['pre_registered_group']} | {entry['n']} | "
                                     f"{ranking['unknown_auroc']:.3f} | {ranking['unknown_aupr']:.3f} | {ranking['oscr_auc']:.3f} | "
                                     f"{ranking['unknown_fpr_at_95_tpr']:.3f} | {_percent(entry['rejection_at_threshold'])} |")
                pooled = metrics.get("pooled_near")
                if pooled:
                    r = pooled["ranking"]
                    lines.append(f"| {view} | {method} | **pooled near** | near | {r['n_unknown']} | {r['unknown_auroc']:.3f} | "
                                 f"{r['unknown_aupr']:.3f} | {r['oscr_auc']:.3f} | {r['unknown_fpr_at_95_tpr']:.3f} | "
                                 f"{_percent(pooled['rejection_at_threshold'])} |")
        lines += ["", "Pooled numbers use the pre-registered near families only; `wideband_noise` is equivalence-limited and",
                  "listed separately; `cid_overlay` is a benign control whose expected decision is `clean`. Thresholds are",
                  "the val-calib known-only thresholds above; nothing was tuned on these families."]
    if result.get("matched_protocol"):
        lines += ["", f"## K17c level-matched ASI versus unauthorized ({result['matched_protocol']})", "",
                  "Unconditional = argmax over eight classes; pair = among samples whose true label is one of the pair, with",
                  "clean / other-known / rejected predictions counted in the denominator (never dropped). Bins are the frozen",
                  "C/I_psd ranges; thresholds are the val-calib ones. The matched set never trained, selected or calibrated anything.", "",
                  "| View | n | Unconditional accuracy | ASI recall | Unauthorized recall | Pair accuracy (argmax, no rejection) | Pair accuracy among accepted (MSP) | ASI→unauth / unauth→ASI | pred clean | rejected (MSP) |",
                  "|---|---|---|---|---|---|---|---|---|---|"]
        for view, values in result["methods"].items():
            m = values.get("matched")
            if not m:
                continue
            pair = m["by_method"].get("msp", next(iter(m["by_method"].values())))["pair"]
            tt = pair["two_by_two"] or {}
            bd = pair["prediction_breakdown"] or {}
            lines.append(f"| {view} | {m['n_samples']} | {_percent(m['unconditional_accuracy'])} | "
                         f"{_percent(m['per_class']['adjacent_satellite']['recall'])} | {_percent(m['per_class']['unauthorized']['recall'])} | "
                         f"{_percent(pair['pair_accuracy'])} | {_percent(pair.get('pair_accuracy_accepted_only'))} | "
                         f"{tt.get('adjacent_satellite', {}).get('unauthorized', 'n/a')} / {tt.get('unauthorized', {}).get('adjacent_satellite', 'n/a')} | "
                         f"{sum(v['predicted_clean'] for v in bd.values()) if bd else 'n/a'} | "
                         f"{sum(v['rejected_as_unknown'] for v in bd.values()) if bd else 'n/a'} |")
        lines += ["", "| View | Bin (dB) | Groups | Pair samples | Pair accuracy (argmax) | Natural ASI recall in bin | Natural unauthorized recall in bin |",
                  "|---|---|---|---|---|---|---|"]
        for view, values in result["methods"].items():
            m = values.get("matched")
            if not m:
                continue
            method = "msp" if "msp" in m["by_method"] else next(iter(m["by_method"]))
            for name in MATCHED_BIN_NAMES:
                pair = m["by_method"][method]["per_bin"][name]
                natural = m.get("natural_comparison") or {"classes": {}}
                nat_asi = natural["classes"].get("adjacent_satellite", {}).get("recall_by_matched_bin", {}).get(name)
                nat_un = natural["classes"].get("unauthorized", {}).get("recall_by_matched_bin", {}).get(name)
                lines.append(f"| {view} | {name} | {m['per_bin_groups'][name]} | {pair['n_samples']} | {_percent(pair['pair_accuracy'])} | "
                             f"{_percent(nat_asi)} | {_percent(nat_un)} |")
        for view, values in result["methods"].items():
            m = values.get("matched")
            if m:
                lines += ["", f"Intersections ({view}, MSP): matched groups with a missing planned carrier = "
                          f"{m['by_method'][next(iter(m['by_method']))]['per_plan_consistency']['planned_carrier_missing']['n_samples']} pair samples; "
                          f"ASI variants over an absent carrier = {m['n_asi_over_absent_carrier']} (reported separately in results.json)."]
        lines += ["", "Representative paired spectrograms (fixed-seed rule, up to three groups per bin) are written under `figures/`;",
                  "the selected groups are listed in results.json. Natural events also differ from the matched ones in carrier width.",
                  "A pilot with two groups cannot establish separability."]
    lines += ["", "Positive class of the alarm is any non-clean label; its threshold comes from clean val-calib scenes only.",
              "Plan-consistency positive class is `planned_carrier_missing` (auxiliary logit > 0); it does not affect checkpoint selection.",
              "Intervals in JSON resample scenario groups with fixed weights and thresholds; training-seed uncertainty is separate.",
              "A pilot with few scenario groups validates execution and data flow, not recognition quality.", "",
              "## Partitions", "", "| Role | Samples | Scenario groups | Planned carrier missing |", "|---|---|---|---|"]
    for role, values in result["partitions"].items():
        lines.append(f"| {role} | {values['n_samples']} | {len(values['scenario_ids'])} | {values['n_planned_carrier_missing']} |")
    lines += ["", f"Experiment fingerprint: `{result['experiment_fingerprint']}`; data fingerprint: `{result['data_fingerprint']}`.", ""]
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", required=True)
    parser.add_argument("--data", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--reuse", action="store_true")
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument("--unknown-data", help="verified B2-test/1 artifact bound to --data (test-only families)")
    parser.add_argument("--matched-data", help="verified B2-match/1 artifact bound to --data (K17c matched set)")
    args = parser.parse_args(argv)
    try:
        run_b2_experiment(B2ExperimentConfig.from_file(args.config), args.data, args.out,
                          reuse=args.reuse, device=args.device, unknown_data=args.unknown_data,
                          matched_data=args.matched_data)
    except (ValueError, FileNotFoundError) as error:
        parser.exit(2, f"error: {error}\n")


if __name__ == "__main__":
    main()

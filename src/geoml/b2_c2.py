"""B2-C2-ablation/1: the C2 comparison roster, matched-arm configurations and paired scenario-group contrasts.

C2 asks three separate questions (never merge their evidence):

* **H1 dual polarization** - ``dual`` against ``co`` (both with operator-plan masks).
* **H2 cancellation residual** - ``dual_residual`` against ``dual``. The residual is computed from the co-pol IQ *and the
  operator plan*, so H2 lives inside the plan-available regime by construction.
* **H3 operator-plan information** - ``dual_planmask`` against ``dual_noplan`` (and ``co_planmask`` against ``co_noplan``).
  The two arms receive bit-identical plan-free spectral channels, the same plan-free level reference, the same objective
  (cross-entropy + center loss, no plan-consistency target, no plan shift) and the same budget; the only difference is
  that one also receives the operator-plan mask channels. A plan-corruption test (A5) is *not* evidence for H3.

The canonical nine fits (``co``/``dual``/``dual_residual`` x seeds 0,1,2) are the approved design and are not modified.
The matched arms are additional, separately versioned fits. Contrasts are computed offline from the per-sample outputs that
the frozen evaluation persists; this module opens no dataset, fits nothing and calibrates nothing.

Metric convention: ``near_fpr95`` is the known-test fraction scored unknown at the first threshold detecting 95 % of the
pooled near-family unknowns (unknown positive, larger score = more unknown-like); lower is better. The operating point is
chosen from the test unknowns themselves (decision D-4): it is a descriptive ranking statistic, not a deployable threshold
(deployable thresholds are the val-calib ones frozen before evaluation). A contrast is
``richer - baseline``; for ``near_fpr95`` a negative value favours the richer arm.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from geosim.b2_protocol import LABELS, NEAR_UNKNOWN

from .metrics import macro_f1
from .openset_metrics import detection_ranking

VERSION = "B2-C2-ablation/1"
SEEDS = (0, 1, 2)
SCORERS = ("msp", "energy", "mahalanobis")
BOOTSTRAP_SEED = 20261026
DEFAULT_BOOTSTRAPS = 2000
PRODUCTION_EPOCHS = 30          # R1-R10 (B2_E9_SCIENTIFIC_DECISION_APPROVAL_2026-10-24)
TRAIN_OBSERVATIONS = 1500 * len(LABELS)      # 1500 train groups x 8 paired variants (P18 roles)

# ---- the roster: every fit that the comparison needs, declared before any execution -----------------------------------

ARMS = {
    "co": dict(view="co", recipe="canonical", tier=1, plan_masks=True, plan_level_reference=True, plan_target=True, plan_shift=True),
    "dual": dict(view="dual", recipe="canonical", tier=1, plan_masks=True, plan_level_reference=True, plan_target=True, plan_shift=True),
    "dual_residual": dict(view="dual_residual", recipe="canonical", tier=1, plan_masks=True, plan_level_reference=True,
                          plan_target=True, plan_shift=True),
    "dual_planmask": dict(view="dual_planmask", recipe="c2-matched", tier=2, plan_masks=True, plan_level_reference=False,
                          plan_target=False, plan_shift=False),
    "dual_noplan": dict(view="dual_noplan", recipe="c2-matched", tier=2, plan_masks=False, plan_level_reference=False,
                        plan_target=False, plan_shift=False),
    "co_planmask": dict(view="co_planmask", recipe="c2-matched", tier=3, plan_masks=True, plan_level_reference=False,
                        plan_target=False, plan_shift=False),
    "co_noplan": dict(view="co_noplan", recipe="c2-matched", tier=3, plan_masks=False, plan_level_reference=False,
                      plan_target=False, plan_shift=False),
}
TIERS = {1: "approved primary design (R1: three views x three seeds)",
         2: "H3 primary matched control (dual-pol): required to answer H3",
         3: "H3 secondary matched control (co-pol): optional, gives the H1-without-plan contrast"}

# Pre-declared contrasts. ``role`` separates the confirmatory-style primary question from descriptive decompositions.
CONTRASTS = {
    "H1_dual_vs_co": dict(hypothesis="H1", richer="dual", baseline="co", role="primary",
                          isolates="cross-pol spectrum and its operator-plan mask channel (the canonical dual view carries both), canonical recipe in both arms"),
    "H2_residual_vs_dual": dict(hypothesis="H2", richer="dual_residual", baseline="dual", role="primary",
                                isolates="observed cancellation residual channel (itself plan-dependent), canonical recipe"),
    "H3_planmask_vs_noplan_dual": dict(hypothesis="H3", richer="dual_planmask", baseline="dual_noplan", role="primary",
                                       isolates="operator-plan mask channels only; identical spectra, level reference, objective, budget"),
    "H3_planmask_vs_noplan_co": dict(hypothesis="H3", richer="co_planmask", baseline="co_noplan", role="secondary",
                                     isolates="operator-plan mask channel only, co-pol"),
    "H1_dual_vs_co_noplan": dict(hypothesis="H1", richer="dual_noplan", baseline="co_noplan", role="secondary",
                                 isolates="cross-pol channel when no plan information exists in either arm"),
    "D1_canonical_vs_matched_planmask": dict(hypothesis="decomposition", richer="dual", baseline="dual_planmask", role="descriptive",
                                             isolates="plan-referenced level + plan-consistency target + plan shift (canonical recipe) versus the matched recipe"),
    "D2_canonical_vs_noplan": dict(hypothesis="decomposition", richer="dual", baseline="dual_noplan", role="descriptive",
                                   isolates="everything the canonical recipe derives from the plan (masks, per-sample carrier-referenced level, plan-consistency target, plan shift) versus no plan access and one global plan-free reference; upper-bounds the value of plan access"),
}
METRICS = {"near_fpr95": ("lower_is_better", "pooled near-family unknown-positive FPR at 95 % TPR; known test events are the negatives"),
           "near_auroc": ("higher_is_better", "pooled near-family unknown-positive AUROC"),
           "known_macro_f1": ("higher_is_better", "closed-set macro-F1 on known test events"),
           "known_accuracy": ("higher_is_better", "closed-set accuracy on known test events")}
PRIMARY_METRIC = "near_fpr95"


def declared_fits():
    """Exact number of fits per tier. Three seeds each; nothing is added or dropped after execution starts."""
    per_tier = {tier: sum(1 for arm in ARMS.values() if arm["tier"] == tier) * len(SEEDS) for tier in TIERS}
    return {"per_tier": {str(tier): {"fits": count, "meaning": TIERS[tier]} for tier, count in per_tier.items()},
            "total_fits": sum(per_tier.values()), "approved_primary_fits": per_tier[1],
            "additional_matched_control_fits": per_tier[2] + per_tier[3], "required_for_h3_primary": per_tier[1] + per_tier[2]}


def roster():
    arms = {name: {**spec, "channels": _channels(spec["view"])} for name, spec in ARMS.items()}
    return {"version": VERSION, "seeds": list(SEEDS), "arms": arms, "contrasts": copy.deepcopy(CONTRASTS),
            "metrics": {name: {"direction": direction, "definition": text} for name, (direction, text) in METRICS.items()},
            "declared_fits": declared_fits(), "scorers": list(SCORERS),
            "primary_scorer": None, "primary_scorer_note": "OPEN: requires explicit researcher approval before any final test read"}


def _channels(view):
    from .data import VIEW_CHANNELS
    return VIEW_CHANNELS[view]


# ---- matched configurations ---------------------------------------------------------------------------------------------

def arm_config(arm, seed, scale="smoke"):
    """``B2ExperimentConfig`` keyword dict for one arm and seed.

    ``scale='production'`` carries the researcher-approved R1-R10 parameters (width 16, 30 epochs, batch 32, time-pool 2,
    carrier level for canonical arms); the isolated executor still refuses it (its caps are bounded smoke caps and the E9
    guard refuses every production action). ``scale='smoke'`` uses the executor's bounded caps. Matched arms differ from the
    canonical recipe in exactly three declared fields: ``level='absolute'`` (plan-free observed reference), no
    plan-consistency target and no plan shift.
    """
    if arm not in ARMS:
        raise ValueError(f"arm must be one of {tuple(ARMS)}")
    if type(seed) is not int or seed < 0:
        raise ValueError("seed must be a nonnegative integer")
    if scale not in ("smoke", "production"):
        raise ValueError("scale must be 'smoke' or 'production'")
    spec = ARMS[arm]
    training = {"epochs": PRODUCTION_EPOCHS if scale == "production" else 2, "batch": 32, "width": 16 if scale == "production" else 8,
                "time_pool": 2, "lr": 1e-3, "weight_decay": 1e-4, "seed": seed, "augment": True,
                "center_loss_weight": 0.005, "plan_loss_weight": 1.0}
    training["plan_shift_max_hz"] = 500000.0      # inert when plan_shift_fraction is 0, kept identical so only declared fields differ
    if spec["recipe"] == "canonical":
        training.update(level="carrier", plan_shift_fraction=0.15)
    else:
        training.update(level="absolute", plan_shift_fraction=0.0)
    return {"protocol": "B2-feat/1", "views": [spec["view"]], "plan_consistency": spec["plan_target"],
            "methods": list(SCORERS), "target_acceptance": 0.95, "pfa": 0.05, "mahalanobis_regularization": 0.1,
            "training": training}


def bundle_config(arms, seed, scale="smoke"):
    """One ``B2ExperimentConfig`` keyword dict that fits several arms of the same recipe in one training bundle per seed."""
    configs = [arm_config(arm, seed, scale) for arm in arms]
    if not configs or len({ARMS[a]["recipe"] for a in arms}) != 1 or len(set(arms)) != len(arms):
        raise ValueError("a bundle needs distinct arms of a single recipe")
    merged = copy.deepcopy(configs[0])
    merged["views"] = [view for config in configs for view in config["views"]]
    return merged


def matched_deltas():
    """The complete list of settings in which the matched arms differ from the canonical recipe."""
    canonical = arm_config("dual", 0, "production")
    matched = arm_config("dual_planmask", 0, "production")
    delta = {}
    for key in ("plan_consistency",):
        if canonical[key] != matched[key]:
            delta[key] = {"canonical": canonical[key], "matched": matched[key]}
    for key in sorted(set(canonical["training"]) | set(matched["training"])):
        if canonical["training"].get(key) != matched["training"].get(key):
            delta[f"training.{key}"] = {"canonical": canonical["training"].get(key), "matched": matched["training"].get(key)}
    return delta


def matrix():
    """The complete pre-declared experiment matrix as strict JSON: every fit, its smoke and production-scale configuration.

    ``docs/plan/b2_c2_experiment_matrix.json`` is this output. It is a plan, not a configuration: it is not accepted by
    ``B2ExperimentConfig`` or any runner, and nothing in it is approved or executable (the isolated executor caps at the smoke
    scale and the E9 guard refuses every production action).
    """
    arms = {name: {"smoke": [arm_config(name, seed, "smoke") for seed in SEEDS],
                   "production": [arm_config(name, seed, "production") for seed in SEEDS]} for name in ARMS}
    passes = PRODUCTION_EPOCHS * TRAIN_OBSERVATIONS
    fits = [{"arm": name, "seed": seed, "tier": spec["tier"], "profile": _PROFILE_OF_TIER.get(spec["tier"])}
            for name, spec in ARMS.items() for seed in SEEDS]
    return {"schema": "B2-C2-experiment-matrix/1", "version": VERSION,
            "status": "UNAPPROVED_NOT_EXECUTABLE", "benchmark_complete": False, "production_authorized": False,
            "roster": roster(), "fits": fits, "matched_recipe_deltas": matched_deltas(), "arms": arms,
            "bundles": {"canonical": {"views": ["co", "dual", "dual_residual"], "profile": "proposed-full"},
                        "c2-h3-dual": {"views": ["dual_planmask", "dual_noplan"], "profile": "c2-h3-dual"},
                        "c2-h3-co": {"views": ["co_planmask", "co_noplan"], "profile": "c2-h3-co"}},
            "sample_passes": {"train_observations_per_fit": TRAIN_OBSERVATIONS, "epochs": PRODUCTION_EPOCHS,
                              "per_fit": passes, "canonical_9_fits": 9 * passes, "matched_dual_6_fits": 6 * passes,
                              "matched_co_6_fits": 6 * passes, "all_21_fits": 21 * passes,
                              "basis": "analytic: fits x epochs x train observations (1500 groups x 8 variants)"}}


_PROFILE_OF_TIER = {1: "proposed-full", 2: "c2-h3-dual", 3: "c2-h3-co"}


# ---- loading frozen evaluation outputs --------------------------------------------------------------------------------

@dataclass(frozen=True)
class Cell:
    seed: int
    view: str
    known_groups: np.ndarray
    known_labels: np.ndarray
    known_prediction: np.ndarray
    known_scores: dict
    unknown_groups: np.ndarray       # near-family unknown samples only
    unknown_scores: dict
    population: str                  # digest of the exact evaluated sample ids and family names
    training: dict | None = None     # the cell's TrainConfig as recorded by the evaluation (budget fairness across evaluations)


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _strict_json(path):
    def reject(value):
        raise ValueError(f"nonfinite JSON value {value} in {path}")
    return json.loads(Path(path).read_text(), parse_constant=reject)


def load_evaluation(directory):
    """Cells of one completed frozen evaluation, after verifying its completion record. Reads only the two output files."""
    root = Path(directory)
    completion = _strict_json(root / "completion.json")
    if (completion.get("results_sha256") != _sha(root / "results.json")
            or completion.get("predictions_sha256") != _sha(root / "predictions.json")):
        raise ValueError(f"{root}: results or predictions differ from the completion record")
    results, predictions = _strict_json(root / "results.json"), _strict_json(root / "predictions.json")
    if results.get("contract") != "B2-isolated-execution/1" or results.get("benchmark_complete") is not False:
        raise ValueError(f"{root}: not a B2-isolated-execution/1 evaluation or it claims a completed benchmark")
    cells, models = {}, {(m["seed"], m["view"]): m for m in results["models"]}
    for entry in predictions:
        key = (entry["seed"], entry["view"])
        model = models.get(key)
        family = entry.get("unknown_families")
        if family is None:
            raise ValueError(f"{root}: evaluation lacks test-only family scores; contrasts need the near-family populations")
        known_ids = np.asarray(entry["sample_ids"], dtype=np.int64)
        names = list(family["families"])
        unknown_ids = np.asarray(family["sample_ids"], dtype=np.int64).reshape(-1, 2)
        near = np.isin(unknown_ids[:, 1], [i for i, name in enumerate(names) if name in NEAR_UNKNOWN])
        cell = Cell(seed=key[0], view=key[1], known_groups=known_ids[:, 0], known_labels=known_ids[:, 1],
                    known_prediction=np.asarray(entry["prediction"], dtype=np.int64),
                    known_scores={m: np.asarray(v, dtype=np.float64) for m, v in entry["unknown_scores"].items()},
                    unknown_groups=unknown_ids[near, 0],
                    unknown_scores={m: np.asarray(v, dtype=np.float64)[near] for m, v in family["scores"].items()},
                    population=hashlib.sha256(json.dumps([entry["sample_ids"], family["sample_ids"], names], separators=(",", ":")).encode()).hexdigest(),
                    training=None if model is None else model.get("training"))
        _check_against_results(cell, model, root)
        cells[key] = cell
    return cells, results


def _check_against_results(cell, model, root):
    """The recomputed point estimate must equal the one the evaluation itself stored (guards against schema or ordering drift)."""
    if model is None:
        raise ValueError(f"{root}: predictions contain a cell without a result record")
    for scorer in cell.known_scores:
        pooled = (model["metrics"]["rejection"].get(scorer) or {}).get("pooled_near")
        if not pooled or not len(cell.unknown_groups):
            continue
        stored = pooled["ranking"]["unknown_fpr_at_95_tpr"]
        again = detection_ranking(cell.known_scores[scorer], cell.unknown_scores[scorer], 0.95)["fpr_at_95_tpr"]
        if abs(stored - again) > 1e-12:
            raise ValueError(f"{root}: recomputed near-family FPR@95TPR {again} differs from the stored {stored}")


BUDGET_FIELDS = ("epochs", "batch", "width", "time_pool", "lr", "weight_decay", "augment", "center_loss_weight")


def merge_cells(evaluations):
    """Cells of several evaluations as one roster, only if they are comparable.

    Every cell must have been evaluated on the identical population and artifacts, by the same source revision and runtime on
    the same known data, and fitted with the same training budget (``BUDGET_FIELDS``): the declared recipe differences
    (level reference, plan target, plan shift) are the only training settings allowed to differ between arms."""
    cells, scopes, populations, artifacts, provenance = {}, set(), set(), set(), set()
    for directory in evaluations:
        part, results = load_evaluation(directory)
        scopes.add((results.get("scope"), results.get("profile")))
        artifacts.add(json.dumps(results.get("evaluation_artifacts"), sort_keys=True))
        provenance.add(json.dumps({k: results.get(k) for k in ("source", "runtime", "data_identity")}, sort_keys=True))
        for key, cell in part.items():
            if key in cells:
                raise ValueError(f"duplicate seed/view cell {key}")
            cells[key] = cell
            populations.add(cell.population)
    if len(populations) > 1 or len(artifacts) > 1:
        raise ValueError("cells were evaluated on different populations or artifacts: contrasts are only defined on identical evaluation populations")
    if len(provenance) > 1:
        raise ValueError("evaluations differ in source revision, runtime or known-data identity: arms are only comparable when fitted and evaluated by the same code and environment")
    if any(cell.training is None for cell in cells.values()):
        raise ValueError("an evaluation lacks the per-model training configuration: its training budget cannot be compared")
    budgets = {json.dumps({field: cell.training.get(field) for field in BUDGET_FIELDS}, sort_keys=True) for cell in cells.values()}
    if len(budgets) > 1:
        raise ValueError(f"cells were fitted with different training budgets {BUDGET_FIELDS}: contrasts would confound capacity or compute with the compared factor")
    return cells, sorted(scopes, key=str)


# ---- statistics -------------------------------------------------------------------------------------------------------

def _statistic(metric, cell, scorer, known_index, unknown_index):
    if metric in ("near_fpr95", "near_auroc"):
        if not len(unknown_index) or not len(known_index):
            return None
        ranking = detection_ranking(cell.known_scores[scorer][known_index], cell.unknown_scores[scorer][unknown_index], 0.95)
        return ranking["fpr_at_95_tpr"] if metric == "near_fpr95" else ranking["auroc"]
    if not len(known_index):
        return None
    truth, predicted = cell.known_labels[known_index], cell.known_prediction[known_index]
    if metric == "known_accuracy":
        return float(np.mean(truth == predicted))
    return float(macro_f1(truth, predicted, len(LABELS)))


def _group_indices(groups, universe):
    order = np.argsort(groups, kind="stable")
    sorted_groups = groups[order]
    start = np.searchsorted(sorted_groups, universe, side="left")
    stop = np.searchsorted(sorted_groups, universe, side="right")
    return [order[a:b] for a, b in zip(start, stop)]


def _percentile_ci(values):
    values = np.asarray([v for v in values if v is not None and np.isfinite(v)], dtype=np.float64)
    if len(values) < 2:
        return None
    low, high = np.percentile(values, [2.5, 97.5])
    return [float(low), float(high)]


def _require_aligned(cells):
    """The group index of one reference cell is applied to every cell, so all cells must share one evaluated population."""
    reference = next(iter(cells.values()))
    for key, cell in cells.items():
        if cell.population != reference.population:
            raise ValueError(f"cell {key} was evaluated on a different population than the others; per-group resampling would misalign")


def paired_contrasts(cells, *, scorer, metric=PRIMARY_METRIC, contrasts=None, n_boot=DEFAULT_BOOTSTRAPS, seed=BOOTSTRAP_SEED,
                     seeds=SEEDS):
    """Paired scenario-group bootstrap of ``richer - baseline`` for each contrast whose six cells are present.

    Whole scenario groups (with all their paired variants and test-only families) are resampled once per replicate and
    shared by every arm and seed, so arms are compared on identical resamples. The interval is conditional on the frozen
    models and calibrators; it contains no training-seed uncertainty. Seed-level values are reported individually and
    summarized descriptively (mean, min, max, sample SD with n=3), never as a seed confidence interval.
    """
    if scorer not in SCORERS or metric not in METRICS:
        raise ValueError("unknown scorer or metric")
    if isinstance(n_boot, bool) or not isinstance(n_boot, int) or n_boot < 1:
        raise ValueError("n_boot must be a positive integer")
    wanted = CONTRASTS if contrasts is None else {name: CONTRASTS[name] for name in contrasts}
    reference = next(iter(cells.values()), None)
    if reference is None:
        return {name: _not_run(name, spec, scorer, metric, "no evaluated cells") for name, spec in wanted.items()}
    _require_aligned(cells)
    universe = np.unique(np.concatenate([reference.known_groups, reference.unknown_groups]))
    known_by_group = _group_indices(reference.known_groups, universe)
    unknown_by_group = _group_indices(reference.unknown_groups, universe)
    runnable = {name: spec for name, spec in wanted.items()
                if all((s, ARMS[arm]["view"]) in cells for s in seeds for arm in (spec["richer"], spec["baseline"]))}
    out = {name: _not_run(name, spec, scorer, metric, "required arms/seeds were not evaluated") for name, spec in wanted.items() if name not in runnable}
    rng = np.random.default_rng(seed)
    use_ci = len(universe) >= 2
    estimates = {name: [] for name in runnable}
    if runnable and use_ci:
        for _ in range(n_boot):
            pick = rng.integers(0, len(universe), len(universe))
            known_index = np.concatenate([known_by_group[g] for g in pick])
            unknown_index = np.concatenate([unknown_by_group[g] for g in pick])
            memo = {}
            for name, spec in runnable.items():
                rows = []
                for s in seeds:
                    pair = []
                    for arm in (spec["richer"], spec["baseline"]):
                        key = (s, ARMS[arm]["view"])
                        if key not in memo:
                            memo[key] = _statistic(metric, cells[key], scorer, known_index, unknown_index)
                        pair.append(memo[key])
                    rows.append(None if None in pair else pair[0] - pair[1])
                estimates[name].append(rows)
    all_known, all_unknown = np.arange(len(reference.known_groups)), np.arange(len(reference.unknown_groups))
    for name, spec in runnable.items():
        per_seed = []
        for position, s in enumerate(seeds):
            values = [_statistic(metric, cells[(s, ARMS[arm]["view"])], scorer, all_known, all_unknown) for arm in (spec["richer"], spec["baseline"])]
            delta = None if None in values else values[0] - values[1]
            replicate = [row[position] for row in estimates[name]]
            per_seed.append({"seed": s, "richer": values[0], "baseline": values[1], "delta": delta,
                             "ci95_conditional_on_frozen_models": _percentile_ci(replicate) if use_ci else None,
                             "undefined_replicates": int(sum(v is None for v in replicate)) if use_ci else None})
        deltas = [row["delta"] for row in per_seed if row["delta"] is not None]
        unavailable = None if deltas else _unavailable_reason(reference)
        seed_means = [None if None in row else float(np.mean(row)) for row in estimates[name]]
        out[name] = {"id": name, **{k: spec[k] for k in ("hypothesis", "richer", "baseline", "role", "isolates")},
                     "scorer": scorer, "metric": metric, "direction": METRICS[metric][0], "delta_definition": "richer - baseline",
                     "status": "MEASURED" if deltas else "UNAVAILABLE", "unavailable_reason": unavailable, "per_seed": per_seed,
                     "seed_summary": None if len(deltas) != len(per_seed) else {
                         "mean_delta": float(np.mean(deltas)), "min_delta": float(np.min(deltas)), "max_delta": float(np.max(deltas)),
                         "sd_delta": float(np.std(deltas, ddof=1)) if len(deltas) > 1 else None, "n_seeds": len(deltas),
                         "ci95_of_mean_conditional_on_frozen_models": _percentile_ci(seed_means) if use_ci else None,
                         "note": "descriptive over the three fitted seeds; the interval resamples scenario groups only and is not a seed interval"},
                     "n_scenario_groups": int(len(universe)), "n_known": int(len(reference.known_groups)),
                     "n_unknown_near": int(len(reference.unknown_groups)), "bootstrap_replicates": n_boot if use_ci else 0,
                     "interval_unavailable_reason": None if use_ci else "fewer than two scenario groups"}
    return out


def _unavailable_reason(reference):
    if not len(reference.unknown_groups):
        return "no near-family unknown events in the evaluated population"
    if not len(reference.known_groups):
        return "no known test events in the evaluated population"
    return "the metric is undefined for the evaluated population"


def _not_run(name, spec, scorer, metric, reason):
    return {"id": name, **{k: spec[k] for k in ("hypothesis", "richer", "baseline", "role", "isolates")}, "scorer": scorer,
            "metric": metric, "status": "NOT_RUN", "reason": reason, "per_seed": None, "seed_summary": None}


def endpoint(cells, *, scorer, n_boot=DEFAULT_BOOTSTRAPS, seed=BOOTSTRAP_SEED, seeds=SEEDS):
    """The D-4 headline: near-family pooled FPR@95TPR of ``dual_residual`` per seed, with a descriptive mean."""
    keys = [(s, "dual_residual") for s in seeds]
    if not all(k in cells for k in keys):
        return {"status": "NOT_RUN", "reason": f"dual_residual cells for seeds {list(seeds)} were not evaluated", "scorer": scorer}
    _require_aligned({k: cells[k] for k in keys})
    reference = cells[keys[0]]
    universe = np.unique(np.concatenate([reference.known_groups, reference.unknown_groups]))
    known_by_group, unknown_by_group = _group_indices(reference.known_groups, universe), _group_indices(reference.unknown_groups, universe)
    rng, use_ci = np.random.default_rng(seed), len(universe) >= 2
    replicate = {k: [] for k in keys}
    if use_ci:
        for _ in range(n_boot):
            pick = rng.integers(0, len(universe), len(universe))
            known_index = np.concatenate([known_by_group[g] for g in pick])
            unknown_index = np.concatenate([unknown_by_group[g] for g in pick])
            for k in keys:
                replicate[k].append(_statistic(PRIMARY_METRIC, cells[k], scorer, known_index, unknown_index))
    all_known, all_unknown = np.arange(len(reference.known_groups)), np.arange(len(reference.unknown_groups))
    rows = [{"seed": k[0], "fpr_at_95_tpr": _statistic(PRIMARY_METRIC, cells[k], scorer, all_known, all_unknown),
             "ci95_conditional_on_frozen_models": _percentile_ci(replicate[k]) if use_ci else None} for k in keys]
    values = [r["fpr_at_95_tpr"] for r in rows]
    mean = None if None in values else float(np.mean(values))
    return {"status": "MEASURED" if mean is not None else "UNAVAILABLE",
            "unavailable_reason": None if mean is not None else _unavailable_reason(reference), "scorer": scorer, "metric": PRIMARY_METRIC, "view": "dual_residual", "per_seed": rows,
            "descriptive_mean": mean, "min": None if mean is None else float(min(values)), "max": None if mean is None else float(max(values)),
            "n_scenario_groups": int(len(universe)), "n_known": int(len(reference.known_groups)),
            "n_unknown_near": int(len(reference.unknown_groups)),
            "note": "seed mean is descriptive; intervals resample scenario groups conditional on frozen models"}


# ---- the single comparison table ------------------------------------------------------------------------------------

def _cell(value, digits=3):
    return "—" if value is None else f"{value:+.{digits}f}"


def comparison_table(results=None, *, scope_note=None, primary_scorer=None):
    """Markdown comparison table. With ``results=None`` every row reads NOT RUN: the template to be filled by a real run."""
    lines = ["# C2 comparison table — " + VERSION, "",
             f"Metric: `{PRIMARY_METRIC}` ({METRICS[PRIMARY_METRIC][1]}); lower is better; contrast = richer − baseline, so a negative value favours the richer arm.",
             f"Primary scorer: {primary_scorer or 'NOT DESIGNATED (requires explicit researcher approval before any final test read)'}; all three scorers are always reported.",
             f"Scope: {scope_note or 'NO EXPERIMENT RUN — template'}", "",
             "| Contrast | Question | Isolates | Scorer | seed 0 | seed 1 | seed 2 | mean Δ (descriptive) | 95 % CI of mean (groups only) | n groups | Status |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    for name, spec in CONTRASTS.items():
        for scorer in SCORERS:
            row = None if results is None else results.get(scorer, {}).get(name)
            if row is not None and row["status"] == "UNAVAILABLE":
                lines.append(f"| `{name}` | {spec['hypothesis']} ({spec['role']}): `{spec['richer']}` − `{spec['baseline']}` | {spec['isolates']} | {scorer} | — | — | — | — | — | {row['n_scenario_groups']} | **UNAVAILABLE** ({row['unavailable_reason']}) |")
                continue
            if row is None or row["status"] != "MEASURED":
                lines.append(f"| `{name}` | {spec['hypothesis']} ({spec['role']}): `{spec['richer']}` − `{spec['baseline']}` | {spec['isolates']} | {scorer} | — | — | — | — | — | — | **NOT RUN** |")
                continue
            summary = row["seed_summary"] or {}
            ci = summary.get("ci95_of_mean_conditional_on_frozen_models")
            lines.append(f"| `{name}` | {spec['hypothesis']} ({spec['role']}): `{spec['richer']}` − `{spec['baseline']}` | {spec['isolates']} | {scorer} | "
                         + " | ".join(_cell(item["delta"]) for item in row["per_seed"]) + f" | {_cell(summary.get('mean_delta'))} | "
                         + ("—" if ci is None else f"[{ci[0]:+.3f}, {ci[1]:+.3f}]") + f" | {row['n_scenario_groups']} | MEASURED |")
    lines += ["", "No cell of this table is a research conclusion unless its scope line says a production-scale authorized run produced it.",
              "Bounded fixtures (two scenario groups per role) establish functional and arithmetic correctness only."]
    return "\n".join(lines) + "\n"


def run_contrasts(evaluations, *, n_boot=DEFAULT_BOOTSTRAPS, primary_scorer=None):
    """``primary_scorer`` only records a designation made (and approved) before the final read; it selects nothing."""
    if primary_scorer is not None and primary_scorer not in SCORERS:
        raise ValueError(f"primary scorer must be one of {SCORERS}")
    cells, scopes = merge_cells(evaluations)
    results = {scorer: paired_contrasts(cells, scorer=scorer, n_boot=n_boot) for scorer in SCORERS}
    headline = {scorer: endpoint(cells, scorer=scorer, n_boot=n_boot) for scorer in SCORERS}
    return {"version": VERSION, "scopes": scopes, "cells": sorted(f"{s}/{v}" for s, v in cells), "contrasts": results,
            "endpoint": headline, "primary_scorer": primary_scorer, "bootstrap_seed": BOOTSTRAP_SEED, "n_boot": n_boot,
            "limitations": ["conditional on the frozen models; no training-seed interval", "exploratory: no multiplicity adjustment, no confirmatory superiority claim",
                            "bounded fixtures establish functional and arithmetic correctness only"]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    commands = parser.add_subparsers(dest="action", required=True)
    commands.add_parser("roster")
    commands.add_parser("matrix")
    template = commands.add_parser("template")
    template.add_argument("--out", required=True)
    contrasts = commands.add_parser("contrasts")
    contrasts.add_argument("--evaluation", nargs="+", required=True, help="completed frozen evaluation directories")
    contrasts.add_argument("--out", required=True)
    contrasts.add_argument("--table")
    contrasts.add_argument("--n-boot", type=int, default=DEFAULT_BOOTSTRAPS)
    contrasts.add_argument("--primary-scorer", choices=SCORERS,
                           help="record the researcher-approved designation made before the final read; omitted = NOT DESIGNATED")
    args = parser.parse_args(argv)
    try:
        if args.action == "roster":
            print(json.dumps(roster(), indent=1, sort_keys=True))
        elif args.action == "matrix":
            print(json.dumps(matrix(), indent=1, sort_keys=True, allow_nan=False))
        elif args.action == "template":
            Path(args.out).write_text(comparison_table())
        else:
            result = run_contrasts(args.evaluation, n_boot=args.n_boot, primary_scorer=args.primary_scorer)
            Path(args.out).write_text(json.dumps(result, indent=1, sort_keys=True, allow_nan=False))
            if args.table:
                scope = "; ".join(f"{s} / {p}" for s, p in result["scopes"])
                Path(args.table).write_text(comparison_table(result["contrasts"], scope_note=scope, primary_scorer=args.primary_scorer))
    except (ValueError, FileNotFoundError, KeyError) as error:
        parser.exit(2, f"error: {error}\n")


if __name__ == "__main__":
    main()

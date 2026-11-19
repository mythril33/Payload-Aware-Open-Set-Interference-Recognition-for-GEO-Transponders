"""Verify completed B2 production outputs and report frozen paired comparisons.

Reads evaluation output files only: no datasets, checkpoints, fitting or renewed
test inference. The primary scorer comes from the pre-test campaign designation.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, replace
from pathlib import Path

import numpy as np

from geosim.b2_protocol import LABELS, NEAR_UNKNOWN, scenario_ids
from geosim.b2_scenarios import MATCHED_LABELS, TEST_FAMILIES
from . import b2_c2 as c2
from . import b2_campaign as campaigns
from . import b2_production_training as production
from .artifacts import fingerprint
from .b2_execution import _separate, _strict
from .b2_production_evaluation import CONTRACT, ROOT
from .experiment import _sha256, _write_json

REPORT_CONTRACT = "B2-production-report/1"
SUBGROUPS = ("d1_exposure_excluded", "k17d_co_feed_missing", "k17d_excluding_co_feed_missing")


def _require(ok, message):
    if not ok:
        raise ValueError(message)


def _rows(rows, expected, name):
    _require(isinstance(rows, list), f"invalid {name} roster")
    result = {}
    for row in rows:
        _require(isinstance(row, dict) and type(row.get("seed")) is int
                 and isinstance(row.get("view"), str), f"invalid {name} cell")
        key = row["seed"], row["view"]
        _require(key in expected and key not in result, f"duplicate/unexpected {name} cell")
        result[key] = row
    _require(set(result) == expected, f"incomplete {name} roster")
    return result


def _population(row, artifact, role, variants, *, score_key="scores"):
    raw_ids = row["sample_ids"]
    ids = np.asarray(raw_ids)
    expected = {(g, v) for g in scenario_ids(role) for v in variants}
    _require(ids.dtype.kind in "iu" and ids.shape == (len(expected), 2), "invalid sample ID shape/type")
    _require(set(map(tuple, ids)) == expected, "duplicate/missing/unexpected scenario variant")
    _require(artifact["sample_ids"] == raw_ids and artifact["n_samples"] == len(ids)
             and artifact["scenario_ids"] == scenario_ids(role) and artifact["role"] == role,
             "predictions differ from their evaluated artifact population")
    n = len(ids)
    predicted = np.asarray(row["prediction"])
    _require(predicted.dtype.kind in "iu" and predicted.shape == (n,)
             and ((predicted >= 0) & (predicted < len(LABELS))).all(), "invalid class predictions")
    raw_scores = row[score_key]
    _require(isinstance(raw_scores, dict) and set(raw_scores) == set(c2.SCORERS), "all three scorers are required")
    scores = {}
    for method, raw in raw_scores.items():
        values = np.asarray(raw)
        _require(values.dtype.kind in "fiu" and values.shape == (n,) and np.isfinite(values).all(),
                 "invalid/nonfinite score vector")
        scores[method] = values.astype(np.float64)
    return ids, predicted, scores


def _campaign(result):
    campaign = result["campaign"]
    _require(set(campaign) == campaigns._FIELDS
             and campaign["contract"] == campaigns.CONTRACT
             and campaign["scope"] == "PRODUCTION" and campaign["benchmark_complete"] is False
             and campaign["authorizes_nothing"] is True and campaign["fits"] == 15
             and campaign["optional_co_controls"] == "DEFERRED_BEFORE_HELDOUT"
             and campaign["evaluation_order"] == list(campaigns.ORDER), "invalid frozen campaign")
    campaigns._designation(campaign["primary_scorer"], campaign["designation"])
    _require(campaign["artifact_id"] == fingerprint({k: v for k, v in campaign.items() if k != "artifact_id"})
             and result["campaign_id"] == campaign["artifact_id"]
             and result["primary_scorer"] == campaign["primary_scorer"], "campaign designation/binding differs")
    _require(result["source"]["files_sha256"] == campaign["common"]["source"]
             and all(result[k] == campaign["common"][k] for k in ("runtime", "data_identity")),
             "evaluation differs from frozen campaign provenance")
    bindings = campaign["inventories"]
    _require(len(bindings) == 2 and [r["profile"] for r in bindings] == list(campaigns.ORDER),
             "incomplete campaign inventories")
    binding = next(r for r in bindings if r["profile"] == result["profile"])
    _require(binding["sha256"] == result["inventory_sha256"], "evaluation inventory binding differs")
    return campaign


def load_evaluation(directory):
    """Strict production-only reader; completion hashes are integrity, not authority."""
    root = Path(directory)
    completion = _strict(root / "completion.json")
    _require(completion.get("results_sha256") == _sha256(root / "results.json")
             and completion.get("predictions_sha256") == _sha256(root / "predictions.json"),
             "results or predictions differ from completion hashes")
    result, predictions = _strict(root / "results.json"), _strict(root / "predictions.json")
    for record in (completion, result):
        _require(record.get("contract") == CONTRACT and record.get("scope") == "PRODUCTION"
                 and record.get("benchmark_complete") is False, "not a completed production profile")
    profile = result["profile"]
    _require(profile in campaigns.ORDER and completion["profile"] == profile
             and completion["campaign_id"] == result["campaign_id"]
             and completion.get("journal_completion_recorded") is True, "missing profile/journal completion")
    _require(result["score_direction"] == "higher_is_more_unknown_like" and result["positive_class"] == "unknown",
             "incompatible metric convention")
    artifacts = result["evaluation_artifacts"]
    _require(set(artifacts) == {"known", "test_only", "matched"}
             and fingerprint(artifacts) == completion["evaluation_artifacts_sha256"], "evaluation artifact binding differs")
    campaign = _campaign(result)
    expected = {(s, v) for s in c2.SEEDS for v in campaigns.ROSTERS[profile]}
    _require(result["inventory_cells"] == len(expected), "wrong inventory size")
    models, predicted = _rows(result["models"], expected, "model"), _rows(predictions, expected, "prediction")
    cells = {}
    for key, row in predicted.items():
        model = models[key]
        training = asdict(production.production_config(campaigns.ROSTERS[profile], key[0]).train_config(key[1]))
        _require(fingerprint(model["training"]) == fingerprint(training), "model differs from the frozen training recipe")
        _require({k: training[k] for k in c2.BUDGET_FIELDS} == campaign["common"]["training_budget"],
                 "model training budget differs from campaign")
        known_ids, kp, ks = _population(row, artifacts["known"], "test", range(8), score_key="unknown_scores")
        unknown = row["unknown_families"]
        _require(unknown["families"] == list(TEST_FAMILIES), "test-only family order differs")
        unknown_ids, _, us = _population(unknown, artifacts["test_only"], "test", range(len(TEST_FAMILIES)))
        _population(row["matched"], artifacts["matched"], "test-matched", [LABELS.index(x) for x in MATCHED_LABELS])
        near = np.isin(unknown_ids[:, 1], [i for i, name in enumerate(TEST_FAMILIES) if name in NEAR_UNKNOWN])
        cell = c2.Cell(key[0], key[1], known_ids[:, 0], known_ids[:, 1], kp, ks, unknown_ids[near, 0],
            {m: v[near] for m, v in us.items()}, fingerprint([row["sample_ids"], unknown["sample_ids"], unknown["families"]]),
            model["training"])
        for method in c2.SCORERS:
            pooled = model["metrics"]["rejection"][method]["pooled_near"]
            _require(set(pooled["families"]) == set(NEAR_UNKNOWN), "wrong near-family metric population")
            stored = pooled["ranking"]["unknown_fpr_at_95_tpr"]
            _require(type(stored) in (int, float) and np.isfinite(stored), "missing/nonfinite near-family point estimate")
        c2._check_against_results(cell, model, root)
        cells[key] = cell
    return cells, result


def _subset(cells, ids):
    """Resample complete scenario groups, retaining every paired class/family."""
    subset = {}
    for key, cell in cells.items():
        k, u = np.isin(cell.known_groups, ids), np.isin(cell.unknown_groups, ids)
        subset[key] = replace(cell, known_groups=cell.known_groups[k], known_labels=cell.known_labels[k],
            known_prediction=cell.known_prediction[k], known_scores={m: s[k] for m, s in cell.known_scores.items()},
            unknown_groups=cell.unknown_groups[u], unknown_scores={m: s[u] for m, s in cell.unknown_scores.items()},
            population=fingerprint([cell.population, ids]))
    return subset


def _subgroup_ids(metadata):
    groups = scenario_ids("test")
    _require(metadata["excluded_test_ids"] == groups[:2]
             and metadata["excluded_matched_ids"] == scenario_ids("test-matched")[:2], "D-1 exclusion differs")
    missing, remaining = metadata["co_feed_missing_ids"], metadata["sensitivity_ids"]
    _require(len(missing) == 35 and len(set(missing)) == 35 and len(remaining) == 465
             and len(set(remaining)) == 465 and not set(missing) & set(remaining)
             and set(missing) | set(remaining) == set(groups), "K17d populations differ")
    return dict(zip(SUBGROUPS, (groups[2:], sorted(missing), sorted(remaining))))


def run_report(evaluations, *, n_boot=c2.DEFAULT_BOOTSTRAPS, log=print):
    """Combine exactly the nine and six fit profiles; no primary scorer override."""
    _require(type(n_boot) is int and n_boot > 0, "n_boot must be a positive integer")
    _require(len(evaluations) == 2, "both production profiles are required")
    cells, records, hashes = {}, {}, []
    for path in evaluations:
        part, result = load_evaluation(path)
        profile = result["profile"]
        _require(profile not in records, "duplicate evaluation profile")
        cells.update(part)
        records[profile] = result
        hashes.append({"profile": profile, "completion_sha256": _sha256(Path(path) / "completion.json")})
    _require(set(records) == set(campaigns.ORDER), "both production profiles are required")
    first, second = (records[p] for p in campaigns.ORDER)
    for name in ("campaign", "campaign_sha256", "source", "runtime", "data_identity", "evaluation_artifacts", "metadata_verification"):
        _require(first[name] == second[name], f"profiles differ in {name}")
    _require(len({c.population for c in cells.values()}) == 1, "scenario ordering differs across cells")
    populations = {"headline": cells, **{name: _subset(cells, ids) for name, ids in _subgroup_ids(first["metadata_verification"]).items()}}
    rows = {}
    for name, selected in populations.items():
        log(f"reporting {name}")
        rows[name] = {"endpoint": {m: c2.endpoint(selected, scorer=m, n_boot=n_boot) for m in c2.SCORERS},
                      "contrasts": {m: c2.paired_contrasts(selected, scorer=m, n_boot=n_boot) for m in c2.SCORERS}}
    return {"contract": REPORT_CONTRACT, "scope": "PRODUCTION", "benchmark_complete": False,
        "required_comparison_complete": True, "campaign_id": first["campaign_id"],
        "primary_scorer": first["primary_scorer"], "designation": first["campaign"]["designation"],
        "input_completions": sorted(hashes, key=lambda x: x["profile"]), "fits": len(cells),
        "n_boot": n_boot, "bootstrap_seed": c2.BOOTSTRAP_SEED, "populations": rows,
        "limitations": [
            "FPR@95TPR is unknown-positive, near families only; known test samples are negatives. Lower is better.",
            "The ranking operating point is descriptive; deployment rejection thresholds remain frozen from val-calib.",
            "Intervals resample scenario groups, conditional on the frozen models; three-seed summaries are descriptive.",
            "Historical exposure exclusions and K17d subgroups are sensitivities, not fresh independent tests.",
            "Optional co controls remain NOT_RUN; no multiplicity adjustment or confirmatory superiority claim.",
            "A completed required comparison does not certify the broader B2 benchmark or operational authorization."]}


def _plot(report, out):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(8, 4.5))
    rows = report["populations"]["headline"]["endpoint"]
    offsets = (-.12, 0., .12)
    for i, method in enumerate(c2.SCORERS):
        for j, row in enumerate(rows[method]["per_seed"]):
            y, interval = row["fpr_at_95_tpr"], row["ci95_conditional_on_frozen_models"]
            x = i + offsets[j]
            if interval is not None:
                ax.vlines(x, *interval, color=f"C{j}", alpha=.7)
            ax.scatter(x, y, color=f"C{j}", label=f"Seed {row['seed']}" if i == 0 else None)
    ax.set_xticks(range(3), [m + (" (primary)" if m == report["primary_scorer"] else "") for m in c2.SCORERS])
    ax.set(ylabel="Known-negative FPR at 95% near-unknown TPR", ylim=(-.03, 1.03),
           title="Dual + residual: 500 paired scenario groups")
    ax.legend()
    ax.grid(axis="y", alpha=.2)
    fig.text(.5, .01, "95% scenario-group intervals conditional on frozen models; lower is better.", ha="center", fontsize=9)
    fig.tight_layout(rect=(0, .04, 1, 1))
    for extension in ("png", "pdf"):
        fig.savefig(out / f"near_fpr95.{extension}", dpi=180)
    plt.close(fig)


def write_report(evaluations, out, *, n_boot=c2.DEFAULT_BOOTSTRAPS, log=print):
    out = Path(out).resolve()
    _require(out != ROOT and ROOT not in out.parents, "report output must be outside the repository")
    _require(not out.exists(), "report output must be fresh")
    _separate(out, evaluations)
    report = run_report(evaluations, n_boot=n_boot, log=log)
    out.mkdir(parents=True, exist_ok=False)
    _write_json(out / "report.json", report)
    sections = ["# B2 required comparison\n", f"Primary scorer: {report['primary_scorer']}. Required fits: 15.\n"]
    for name, row in report["populations"].items():
        sections.append(c2.comparison_table(row["contrasts"], scope_note=f"PRODUCTION / {name}", primary_scorer=report["primary_scorer"]))
    sections.extend(report["limitations"])
    (out / "comparison.md").write_text("\n\n".join(sections) + "\n", encoding="utf-8")
    _plot(report, out)
    files = {name: _sha256(out / name) for name in ("report.json", "comparison.md", "near_fpr95.png", "near_fpr95.pdf")}
    _write_json(out / "completion.json", {"contract": REPORT_CONTRACT, "files": files})
    production._sync(out)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--evaluation", nargs=2, required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--n-boot", type=int, default=c2.DEFAULT_BOOTSTRAPS)
    args = parser.parse_args(argv)
    try:
        write_report(args.evaluation, args.out, n_boot=args.n_boot)
    except (ValueError, KeyError, TypeError, OSError) as error:
        parser.exit(2, f"error: {error}\n")


if __name__ == "__main__":
    main()

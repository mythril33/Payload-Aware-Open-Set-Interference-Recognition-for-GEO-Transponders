"""B2-C2-ablation/1: paired scenario-group contrasts, evaluation loading and the bounded train -> calibrate -> freeze -> evaluate flow.

Synthetic cells check the arithmetic against independently computed metrics; the stand-in flow runs the real isolated executor
on deterministic stand-in observations (never real held-out data). Nothing here measures recognition quality.
"""
import json
from pathlib import Path

import numpy as np
import pytest

from geosim.b2_protocol import LABELS, ROLE_STARTS
from geoml import b2_c2, b2_execution as execution
from geoml.b2_experiment import B2ExperimentConfig
from geoml.metrics import macro_f1
from geoml.openset_metrics import detection_ranking
from test_b2_execution import fixture, install_optional_artifacts, resign, _sha  # noqa: F401  (pytest fixture and stand-in helpers)

VIEW_SHIFT = {"co": .5, "dual": 1., "dual_residual": 1.5, "co_noplan": .3, "dual_noplan": .8, "co_planmask": .5, "dual_planmask": 1.2}
N_GROUPS, N_KNOWN, N_UNKNOWN = 6, len(LABELS), 3


def make_cell(seed, view, *, shift=None, n_groups=N_GROUPS, n_unknown=N_UNKNOWN, noise=None, error_rate=.25):
    """Synthetic frozen-evaluation cell: known events ~ N(0,1), near-family unknown events ~ N(shift,1) (larger = more unknown-like)."""
    rng = np.random.default_rng((seed, abs(hash(view)) % 1000 if noise is None else noise))
    groups = ROLE_STARTS["test"] + np.arange(n_groups)
    known_groups, known_labels = np.repeat(groups, N_KNOWN), np.tile(np.arange(N_KNOWN), n_groups)
    unknown_groups = np.repeat(groups, n_unknown)
    shift = VIEW_SHIFT[view] if shift is None else shift
    prediction = np.where(rng.random(len(known_labels)) < error_rate, (known_labels + 1) % N_KNOWN, known_labels)
    return b2_c2.Cell(seed=seed, view=view, known_groups=known_groups, known_labels=known_labels, known_prediction=prediction,
                      known_scores={m: rng.normal(0, 1, len(known_groups)) for m in b2_c2.SCORERS},
                      unknown_groups=unknown_groups, unknown_scores={m: rng.normal(shift, 1, len(unknown_groups)) for m in b2_c2.SCORERS},
                      population="p" * 64)


def make_cells(views=tuple(VIEW_SHIFT), seeds=b2_c2.SEEDS, **kwargs):
    return {(s, v): make_cell(s, v, **kwargs) for s in seeds for v in views}


def full(cell):
    return np.arange(len(cell.known_groups)), np.arange(len(cell.unknown_groups))


# ---- the roster -------------------------------------------------------------------------------------------------------------

def test_declared_fit_counts_are_fixed_before_any_execution():
    declared = b2_c2.declared_fits()
    assert declared["total_fits"] == 21 and declared["approved_primary_fits"] == 9
    assert declared["additional_matched_control_fits"] == 12 and declared["required_for_h3_primary"] == 15
    assert {tier: row["fits"] for tier, row in declared["per_tier"].items()} == {"1": 9, "2": 6, "3": 6}
    roster = b2_c2.roster()
    assert roster["primary_scorer"] is None and "OPEN" in roster["primary_scorer_note"]
    assert roster["seeds"] == [0, 1, 2] and set(roster["scorers"]) == {"msp", "energy", "mahalanobis"}
    assert {a for a, row in roster["arms"].items() if not row["plan_masks"]} == {"dual_noplan", "co_noplan"}
    assert all(not row["plan_level_reference"] and not row["plan_target"] and not row["plan_shift"]
               for row in roster["arms"].values() if row["recipe"] == "c2-matched")


def test_every_contrast_names_declared_arms_and_h3_is_only_ever_the_matched_pair():
    for name, spec in b2_c2.CONTRASTS.items():
        assert spec["richer"] in b2_c2.ARMS and spec["baseline"] in b2_c2.ARMS and spec["richer"] != spec["baseline"], name
    for name, spec in b2_c2.CONTRASTS.items():
        if spec["hypothesis"] == "H3":
            assert spec["richer"].endswith("_planmask") and spec["baseline"] == spec["richer"].replace("_planmask", "_noplan")
        if spec["hypothesis"] in ("H1", "H2"):                      # H1/H2 are never evidence for plan information (H3)
            assert spec["richer"] not in ("dual_planmask", "co_planmask")
    assert {n for n, s in b2_c2.CONTRASTS.items() if s["role"] == "primary"} == {"H1_dual_vs_co", "H2_residual_vs_dual", "H3_planmask_vs_noplan_dual"}


# ---- paired scenario-group contrasts ---------------------------------------------------------------------------------------

def test_point_estimates_equal_independently_computed_ranking_metrics():
    cells = make_cells()
    result = b2_c2.paired_contrasts(cells, scorer="mahalanobis", n_boot=20)["H3_planmask_vs_noplan_dual"]
    assert result["status"] == "MEASURED" and result["delta_definition"] == "richer - baseline"
    for row in result["per_seed"]:
        rich, base = cells[(row["seed"], "dual_planmask")], cells[(row["seed"], "dual_noplan")]
        expected = [detection_ranking(c.known_scores["mahalanobis"], c.unknown_scores["mahalanobis"], .95)["fpr_at_95_tpr"] for c in (rich, base)]
        assert (row["richer"], row["baseline"]) == (expected[0], expected[1]) and row["delta"] == expected[0] - expected[1]
    deltas = [r["delta"] for r in result["per_seed"]]
    assert result["seed_summary"]["mean_delta"] == pytest.approx(np.mean(deltas)) and result["seed_summary"]["n_seeds"] == 3
    assert result["seed_summary"]["sd_delta"] == pytest.approx(np.std(deltas, ddof=1))
    assert (result["n_scenario_groups"], result["n_known"], result["n_unknown_near"]) == (N_GROUPS, N_GROUPS * N_KNOWN, N_GROUPS * N_UNKNOWN)


def test_score_direction_is_unknown_positive_larger_is_more_unknown_like():
    perfect = make_cell(0, "dual", shift=12)             # unknowns score far above every known event
    inverted = make_cell(0, "dual", shift=-12)
    for cell, auroc, fpr in ((perfect, 1.0, 0.0), (inverted, 0.0, 1.0)):
        assert b2_c2._statistic("near_auroc", cell, "msp", *full(cell)) == auroc
        assert b2_c2._statistic("near_fpr95", cell, "msp", *full(cell)) == fpr


def test_known_closed_set_metrics_use_the_known_events_only():
    cell = make_cell(1, "dual")
    known = np.arange(len(cell.known_labels))
    assert b2_c2._statistic("known_accuracy", cell, "msp", known, np.array([], dtype=int)) == float(np.mean(cell.known_labels == cell.known_prediction))
    assert b2_c2._statistic("known_macro_f1", cell, "msp", known, np.array([], dtype=int)) == float(macro_f1(cell.known_labels, cell.known_prediction, len(LABELS)))
    assert b2_c2._statistic("known_accuracy", cell, "msp", np.array([], dtype=int), known) is None      # no known events -> null, not 0


def test_contrast_is_antisymmetric_and_its_interval_mirrors(monkeypatch):
    spec = b2_c2.CONTRASTS["H3_planmask_vs_noplan_dual"]
    monkeypatch.setitem(b2_c2.CONTRASTS, "reverse", {**spec, "richer": spec["baseline"], "baseline": spec["richer"]})
    cells = make_cells()
    out = b2_c2.paired_contrasts(cells, scorer="energy", contrasts=["H3_planmask_vs_noplan_dual", "reverse"], n_boot=200)
    forward, backward = out["H3_planmask_vs_noplan_dual"], out["reverse"]
    for a, b in zip(forward["per_seed"], backward["per_seed"]):
        assert a["delta"] == -b["delta"]
        lo, hi = a["ci95_conditional_on_frozen_models"]
        assert b["ci95_conditional_on_frozen_models"] == pytest.approx([-hi, -lo])
    assert forward["seed_summary"]["mean_delta"] == -backward["seed_summary"]["mean_delta"]


def test_bootstrap_is_deterministic_and_depends_on_the_declared_seed():
    cells = make_cells()
    first = b2_c2.paired_contrasts(cells, scorer="msp", n_boot=60)
    assert first == b2_c2.paired_contrasts(cells, scorer="msp", n_boot=60)
    other = b2_c2.paired_contrasts(cells, scorer="msp", n_boot=60, seed=b2_c2.BOOTSTRAP_SEED + 1)
    assert first["H1_dual_vs_co"]["per_seed"][0]["delta"] == other["H1_dual_vs_co"]["per_seed"][0]["delta"]     # point estimate seed-free
    assert first["H1_dual_vs_co"]["per_seed"][0]["ci95_conditional_on_frozen_models"] != other["H1_dual_vs_co"]["per_seed"][0]["ci95_conditional_on_frozen_models"]


def test_replicates_resample_whole_scenario_groups_and_share_them_between_arms(monkeypatch):
    calls, original = [], b2_c2._statistic

    def spy(metric, cell, scorer, known_index, unknown_index):
        calls.append((cell.seed, cell.view, known_index.copy(), unknown_index.copy()))
        return original(metric, cell, scorer, known_index, unknown_index)
    monkeypatch.setattr(b2_c2, "_statistic", spy)
    cells = make_cells()
    n_boot = 4
    b2_c2.paired_contrasts(cells, scorer="msp", contrasts=["H1_dual_vs_co"], n_boot=n_boot)
    replicate_calls = calls[:n_boot * 6]                          # 3 seeds x 2 arms per replicate, memoized per cell
    assert len(replicate_calls) == n_boot * 6 and len(calls) == n_boot * 6 + 6          # + the six full-sample point estimates
    duplicated = False
    for r in range(n_boot):
        chunk = replicate_calls[r * 6:(r + 1) * 6]
        assert {c[1] for c in chunk} == {"dual", "co"} and {c[0] for c in chunk} == {0, 1, 2}
        for _, _, known_index, unknown_index in chunk:            # one identical resample for every arm and seed
            np.testing.assert_array_equal(known_index, chunk[0][2])
            np.testing.assert_array_equal(unknown_index, chunk[0][3])
        counts = np.bincount(cells[(0, "dual")].known_groups[chunk[0][2]] - ROLE_STARTS["test"], minlength=N_GROUPS)
        assert counts.sum() == N_GROUPS * N_KNOWN and set(counts % N_KNOWN) == {0}      # groups enter as complete blocks of all eight variants
        unknown_counts = np.bincount(cells[(0, "dual")].unknown_groups[chunk[0][3]] - ROLE_STARTS["test"], minlength=N_GROUPS)
        np.testing.assert_array_equal(unknown_counts // N_UNKNOWN, counts // N_KNOWN)  # the same groups carry their test-only families
        duplicated |= bool((counts > N_KNOWN).any())
    assert duplicated                                             # sampled with replacement


def test_identical_arms_give_a_zero_delta_with_a_zero_width_interval_and_a_clear_gap_gives_a_one_sided_interval():
    cells = make_cells(views=("dual_planmask", "dual_noplan"))
    for s in b2_c2.SEEDS:
        cells[(s, "dual_noplan")] = make_cell(s, "dual_planmask", noise=7)
        cells[(s, "dual_planmask")] = make_cell(s, "dual_planmask", noise=7)
    same = b2_c2.paired_contrasts(cells, scorer="msp", contrasts=["H3_planmask_vs_noplan_dual"], n_boot=50)["H3_planmask_vs_noplan_dual"]
    assert all(r["delta"] == 0 and r["ci95_conditional_on_frozen_models"] == [0, 0] for r in same["per_seed"])
    apart = {(s, "dual_planmask"): make_cell(s, "dual_planmask", shift=6, noise=3, n_groups=12) for s in b2_c2.SEEDS}
    apart.update({(s, "dual_noplan"): make_cell(s, "dual_noplan", shift=0, noise=3, n_groups=12) for s in b2_c2.SEEDS})
    gap = b2_c2.paired_contrasts(apart, scorer="msp", contrasts=["H3_planmask_vs_noplan_dual"], n_boot=200)["H3_planmask_vs_noplan_dual"]
    assert all(r["delta"] < 0 and r["ci95_conditional_on_frozen_models"][1] < 0 for r in gap["per_seed"])     # richer arm has the lower FPR


def test_missing_arms_or_seeds_are_reported_as_not_run_and_never_filled_in():
    cells = make_cells(views=("co", "dual", "dual_residual"))
    out = b2_c2.paired_contrasts(cells, scorer="msp", n_boot=10)
    assert {n for n, r in out.items() if r["status"] == "MEASURED"} == {"H1_dual_vs_co", "H2_residual_vs_dual"}
    assert all(r["per_seed"] is None and r["reason"] for r in out.values() if r["status"] == "NOT_RUN")
    partial = {k: v for k, v in make_cells().items() if k != (2, "dual_noplan")}
    assert b2_c2.paired_contrasts(partial, scorer="msp", n_boot=10)["H3_planmask_vs_noplan_dual"]["status"] == "NOT_RUN"
    assert all(r["status"] == "NOT_RUN" for r in b2_c2.paired_contrasts({}, scorer="msp", n_boot=10).values())
    assert b2_c2.endpoint(make_cells(views=("co",)), scorer="msp")["status"] == "NOT_RUN"


def test_requested_seed_subset_is_honoured_and_per_seed_rows_follow_the_cells():
    cells = make_cells()
    out = b2_c2.paired_contrasts(cells, scorer="msp", contrasts=["H1_dual_vs_co"], n_boot=10, seeds=(0, 2))["H1_dual_vs_co"]
    assert [r["seed"] for r in out["per_seed"]] == [0, 2] and out["seed_summary"]["n_seeds"] == 2
    assert [r["seed"] for r in b2_c2.paired_contrasts(cells, scorer="msp", contrasts=["H1_dual_vs_co"], n_boot=10)["H1_dual_vs_co"]["per_seed"]] == [0, 1, 2]


def test_one_scenario_group_keeps_the_point_estimate_but_reports_no_interval():
    cells = make_cells(n_groups=1)
    out = b2_c2.paired_contrasts(cells, scorer="msp", contrasts=["H1_dual_vs_co"], n_boot=10)["H1_dual_vs_co"]
    assert out["status"] == "MEASURED" and out["bootstrap_replicates"] == 0 and "fewer than two" in out["interval_unavailable_reason"]
    assert all(r["delta"] is not None and r["ci95_conditional_on_frozen_models"] is None for r in out["per_seed"])
    assert out["seed_summary"]["ci95_of_mean_conditional_on_frozen_models"] is None


def test_an_empty_unknown_population_gives_null_not_zero_and_strict_json():
    cells = make_cells(n_unknown=0)
    out = b2_c2.paired_contrasts(cells, scorer="msp", contrasts=["H1_dual_vs_co"], n_boot=10)["H1_dual_vs_co"]
    assert all(r["delta"] is None and r["richer"] is None for r in out["per_seed"]) and out["seed_summary"] is None
    assert out["status"] == "UNAVAILABLE"
    json.dumps(out, allow_nan=False)
    assert b2_c2.paired_contrasts(cells, scorer="msp", contrasts=["H1_dual_vs_co"], n_boot=10, )["H1_dual_vs_co"]["n_unknown_near"] == 0


def test_cells_of_different_populations_are_refused_by_the_public_statistics():
    import dataclasses
    cells = make_cells()
    cells[(1, "dual")] = dataclasses.replace(cells[(1, "dual")], population="q" * 64)
    with pytest.raises(ValueError, match="different population"):
        b2_c2.paired_contrasts(cells, scorer="msp", n_boot=5)
    with pytest.raises(ValueError, match="different population"):
        b2_c2.endpoint({(s, "dual_residual"): (cells[(s, "dual_residual")] if s else dataclasses.replace(cells[(0, "dual_residual")], population="q" * 64))
                        for s in b2_c2.SEEDS}, scorer="msp", n_boot=5)


def test_an_unavailable_endpoint_or_contrast_says_so_and_is_not_labelled_measured():
    cells = make_cells(n_unknown=0)
    contrast = b2_c2.paired_contrasts(cells, scorer="msp", contrasts=["H1_dual_vs_co"], n_boot=5)["H1_dual_vs_co"]
    assert contrast["status"] == "UNAVAILABLE" and "no near-family unknown" in contrast["unavailable_reason"]
    endpoint = b2_c2.endpoint(cells, scorer="msp", n_boot=5)
    assert endpoint["status"] == "UNAVAILABLE" and endpoint["descriptive_mean"] is None and "no near-family unknown" in endpoint["unavailable_reason"]
    table = b2_c2.comparison_table({s: b2_c2.paired_contrasts(cells, scorer=s, n_boot=5) for s in b2_c2.SCORERS})
    assert any(line.endswith("**UNAVAILABLE** (no near-family unknown events in the evaluated population) |") for line in table.splitlines())
    assert make_cell(0, "dual", n_unknown=3) and b2_c2.endpoint(make_cells(), scorer="msp", n_boot=5)["status"] == "MEASURED"


def test_invalid_requests_are_refused():
    cells = make_cells()
    for bad in (dict(scorer="softmax"), dict(scorer="msp", metric="auc"), dict(scorer="msp", n_boot=0), dict(scorer="msp", n_boot=True)):
        with pytest.raises(ValueError):
            b2_c2.paired_contrasts(cells, **bad)


def test_endpoint_is_the_dual_residual_near_family_fpr_with_a_descriptive_seed_mean():
    cells = make_cells()
    out = b2_c2.endpoint(cells, scorer="mahalanobis", n_boot=30)
    values = [detection_ranking(cells[(s, "dual_residual")].known_scores["mahalanobis"], cells[(s, "dual_residual")].unknown_scores["mahalanobis"], .95)["fpr_at_95_tpr"]
              for s in b2_c2.SEEDS]
    assert out["view"] == "dual_residual" and out["metric"] == "near_fpr95" and [r["fpr_at_95_tpr"] for r in out["per_seed"]] == values
    assert out["descriptive_mean"] == pytest.approx(np.mean(values)) and out["min"] == min(values) and out["max"] == max(values)
    json.dumps(out, allow_nan=False)


# ---- the single comparison table ------------------------------------------------------------------------------------------

def test_the_table_template_claims_no_result_and_a_measured_table_marks_only_what_ran():
    template = b2_c2.comparison_table()
    rows = [line for line in template.splitlines() if line.startswith("| `")]
    assert len(rows) == len(b2_c2.CONTRASTS) * len(b2_c2.SCORERS) and all(row.endswith("**NOT RUN** |") for row in rows)
    assert "NOT DESIGNATED" in template and "NO EXPERIMENT RUN" in template and "negative value favours the richer arm" in template
    cells = make_cells(views=("co", "dual", "dual_residual"))
    results = {s: b2_c2.paired_contrasts(cells, scorer=s, n_boot=20) for s in b2_c2.SCORERS}
    table = b2_c2.comparison_table(results, scope_note="stand-in")
    measured = [line for line in table.splitlines() if line.endswith("| MEASURED |")]
    assert len(measured) == 2 * len(b2_c2.SCORERS) and sum(line.endswith("**NOT RUN** |") for line in table.splitlines()) == 5 * len(b2_c2.SCORERS)
    assert "Bounded fixtures" in table


# ---- the bounded train -> calibrate -> freeze -> evaluate flow on stand-in observations --------------------------------------------

def tiny(arms, seed):
    config = b2_c2.bundle_config(arms, seed, "smoke")
    config["training"].update(epochs=1, batch=8, width=2, augment=False)
    return B2ExperimentConfig(**config)


def fit_roster(fixture, tmp_path, *, arms=("dual_planmask", "dual_noplan"), profile="c2-h3-dual", tag="dual"):
    runs = []
    for seed in b2_c2.SEEDS:
        out = tmp_path / f"fit-{tag}-seed-{seed}"
        execution.fit_b2_models(tiny(arms, seed), fixture[3], out, log=lambda *_: None)
        execution.calibrate_b2_models(fixture[3], out, log=lambda *_: None)
        runs.append(out)
    inventory = tmp_path / f"inventory-{tag}.json"
    execution.freeze_inventory(runs, inventory, seeds=b2_c2.SEEDS, profile=profile)
    return runs, inventory


def evaluate_roster(fixture, tmp_path, inventory, *, profile="c2-h3-dual", unknown=True, name="evaluation"):
    kwargs = dict(unknown_data=tmp_path / "unknown", matched_data=tmp_path / "matched") if unknown else {}
    result = execution.evaluate_b2_inventory(fixture[3], inventory, tmp_path / name, profile=profile, log=lambda *_: None, **kwargs)
    return tmp_path / name, result


def produce(fixture, tmp_path, monkeypatch, *, unknown=True, name="evaluation"):
    install_optional_artifacts(fixture, monkeypatch)
    runs, inventory = fit_roster(fixture, tmp_path)
    out, result = evaluate_roster(fixture, tmp_path, inventory, unknown=unknown, name=name)
    return runs, inventory, out, result


def test_c2_h3_flow_fits_calibrates_freezes_and_evaluates_all_six_cells(fixture, tmp_path, monkeypatch):
    runs, inventory, out, result = produce(fixture, tmp_path, monkeypatch)
    assert result["profile"] == "c2-h3-dual" and result["inventory_cells"] == 6 and len(result["models"]) == 6
    assert result["benchmark_complete"] is False and sorted((m["seed"], m["view"]) for m in result["models"]) == sorted(
        (s, v) for s in b2_c2.SEEDS for v in ("dual_planmask", "dual_noplan"))
    frozen = json.loads(inventory.read_text())
    assert frozen["profile"] == "c2-h3-dual" and frozen["full_protocol_admission"] is False and len(frozen["cells"]) == 6
    for run in runs:
        training = json.loads((run / "training.json").read_text())
        assert set(training["views"]) == {"dual_planmask", "dual_noplan"}
        assert training["views"]["dual_noplan"].keys() == training["views"]["dual_planmask"].keys()
    cells, results = b2_c2.load_evaluation(out)
    assert len(cells) == 6 and len({c.population for c in cells.values()}) == 1
    report = b2_c2.run_contrasts([out], n_boot=40)
    assert report["primary_scorer"] is None and report["cells"] == sorted(f"{s}/{v}" for s in b2_c2.SEEDS for v in ("dual_noplan", "dual_planmask"))
    for scorer in b2_c2.SCORERS:
        statuses = {n: r["status"] for n, r in report["contrasts"][scorer].items()}
        assert statuses["H3_planmask_vs_noplan_dual"] == "MEASURED" and sum(s == "MEASURED" for s in statuses.values()) == 1
        assert report["endpoint"][scorer]["status"] == "NOT_RUN"
    json.dumps(report, allow_nan=False)


def test_contrasts_read_only_the_two_evaluation_outputs(fixture, tmp_path, monkeypatch):
    _, _, out, _ = produce(fixture, tmp_path, monkeypatch)
    for name in ("open_b2_known_roles",):
        monkeypatch.setattr(execution, name, lambda *_a, **_k: pytest.fail("contrasts opened a dataset"))
    for name in ("open_b2_test", "open_b2_matched"):
        monkeypatch.setattr(execution.ex, name, lambda *_a, **_k: pytest.fail("contrasts opened a dataset"))
    monkeypatch.setattr(execution, "fit_streaming", lambda *_a, **_k: pytest.fail("contrasts fitted"))
    before = {str(p): _sha(p) for p in out.rglob("*") if p.is_file()}
    b2_c2.run_contrasts([out], n_boot=10)
    assert {str(p): _sha(p) for p in out.rglob("*") if p.is_file()} == before


def test_a_plan_change_at_evaluation_cannot_move_the_noplan_cells_and_does_move_the_planmask_cells(fixture, tmp_path, monkeypatch):
    runs, inventory, first, _ = produce(fixture, tmp_path, monkeypatch)
    test = fixture[0]["test"]
    test["mask"] = np.roll(test["mask"], 4, axis=2)                       # a stale / shifted operator belief for every test event
    test["residual"] = np.full_like(test["residual"], -40)
    test["plan_consistency"] = 1 - test["plan_consistency"]
    second = tmp_path / "evaluation-shifted-plan"
    execution.evaluate_b2_inventory(fixture[3], inventory, second, profile="c2-h3-dual", unknown_data=tmp_path / "unknown",
                                    matched_data=tmp_path / "matched", log=lambda *_: None)
    a, b = (json.loads((root / "predictions.json").read_text()) for root in (first, second))
    by_view = {v: [(x, y) for x, y in zip(a, b) if x["view"] == v] for v in ("dual_noplan", "dual_planmask")}
    assert all(len(rows) == 3 for rows in by_view.values())
    for x, y in by_view["dual_noplan"]:
        assert x["unknown_scores"] == y["unknown_scores"] and x["prediction"] == y["prediction"] and x["event_probability"] == y["event_probability"]
    assert any(x["unknown_scores"] != y["unknown_scores"] for x, y in by_view["dual_planmask"])     # positive control: the test is not vacuous


def test_evaluation_without_test_only_families_is_refused_by_the_contrast_loader(fixture, tmp_path, monkeypatch):
    _, _, out, _ = produce(fixture, tmp_path, monkeypatch, unknown=False)
    with pytest.raises(ValueError, match="test-only family scores"):
        b2_c2.load_evaluation(out)


def test_loader_refuses_tampered_outputs(fixture, tmp_path, monkeypatch):
    _, _, out, _ = produce(fixture, tmp_path, monkeypatch)
    assert len(b2_c2.load_evaluation(out)[0]) == 6
    for name, change in (("results.json", lambda raw: raw.replace('"benchmark_complete": false', '"benchmark_complete": true')),
                         ("predictions.json", lambda raw: raw.replace('"seed": 0', '"seed": 9', 1))):
        path = out / name
        raw = path.read_text()
        assert change(raw) != raw
        path.write_text(change(raw))
        with pytest.raises(ValueError, match="completion record"):
            b2_c2.load_evaluation(out)
        path.write_text(raw)
    assert len(b2_c2.load_evaluation(out)[0]) == 6


def test_loader_refuses_a_nonfinite_or_foreign_contract_even_when_the_completion_record_is_regenerated(fixture, tmp_path, monkeypatch):
    _, _, out, _ = produce(fixture, tmp_path, monkeypatch)
    results = json.loads((out / "results.json").read_text())
    for label, change, message in (("contract", lambda r: r.update(contract="B2-other/1"), "not a B2-isolated-execution/1"),
                                   ("complete", lambda r: r.update(benchmark_complete=True), "not a B2-isolated-execution/1")):
        mutated = json.loads(json.dumps(results))
        change(mutated)
        (out / "results.json").write_text(json.dumps(mutated))
        completion = json.loads((out / "completion.json").read_text())
        completion["results_sha256"] = _sha(out / "results.json")
        (out / "completion.json").write_text(json.dumps(completion))
        with pytest.raises(ValueError, match=message):
            b2_c2.load_evaluation(out)
    (out / "results.json").write_text(json.dumps(results).replace('"seed": 0', '"seed": NaN', 1))
    completion["results_sha256"] = _sha(out / "results.json")
    (out / "completion.json").write_text(json.dumps(completion))
    with pytest.raises(ValueError, match="nonfinite"):
        b2_c2.load_evaluation(out)


def test_loader_recomputes_the_stored_near_family_estimate_and_refuses_a_disagreement(fixture, tmp_path, monkeypatch):
    _, _, out, _ = produce(fixture, tmp_path, monkeypatch)
    results = json.loads((out / "results.json").read_text())
    ranking = results["models"][0]["metrics"]["rejection"]["msp"]["pooled_near"]["ranking"]      # must exist: the check is not skipped
    ranking["unknown_fpr_at_95_tpr"] = 0.5 if ranking["unknown_fpr_at_95_tpr"] != 0.5 else 0.25
    (out / "results.json").write_text(json.dumps(results))
    completion = json.loads((out / "completion.json").read_text())
    completion["results_sha256"] = _sha(out / "results.json")
    (out / "completion.json").write_text(json.dumps(completion))
    with pytest.raises(ValueError, match="differs from the stored"):
        b2_c2.load_evaluation(out)


@pytest.mark.parametrize("change", ["drop_cell", "claim_full_admission"])
def test_a_resigned_inventory_that_is_not_the_complete_six_cell_roster_opens_no_held_out_data(fixture, tmp_path, monkeypatch, change):
    _, inventory, _, _ = produce(fixture, tmp_path, monkeypatch)
    payload = json.loads(inventory.read_text())
    if change == "drop_cell":
        payload["cells"] = payload["cells"][:-1]
    else:
        payload["full_protocol_admission"] = True
    resign(inventory, payload)
    fixture[2].clear()
    with pytest.raises(ValueError, match="complete six-cell"):
        execution.evaluate_b2_inventory(fixture[3], inventory, tmp_path / f"refused-{change}", profile="c2-h3-dual", log=lambda *_: None)
    assert not (tmp_path / f"refused-{change}").exists()


def fake_evaluations(monkeypatch, *, specs):
    """Register synthetic evaluation directories: ``specs`` maps a name to (views, results overrides, training overrides)."""
    base_training = dict(epochs=2, batch=32, width=8, time_pool=2, lr=1e-3, weight_decay=1e-4, augment=True, center_loss_weight=0.005,
                         level="absolute", plan_consistency=False, plan_shift_fraction=0.0)
    loaded = {}
    for name, (views, results_over, training_over) in specs.items():
        cells = {(s, v): dataclasses.replace(make_cell(s, v), training={**base_training, **training_over}) for s in b2_c2.SEEDS for v in views}
        results = {"scope": "BOUNDED_FIXTURE", "profile": name, "evaluation_artifacts": {"known": "k"}, "source": {"files": "A"},
                   "runtime": {"torch": "2.9", "threads": 1}, "data_identity": "d" * 8, **results_over}
        loaded[name] = (cells, results)
    monkeypatch.setattr(b2_c2, "load_evaluation", lambda directory: loaded[directory])
    return list(specs)


import dataclasses  # noqa: E402


def test_merge_requires_one_source_runtime_data_identity_and_training_budget(monkeypatch):
    ok = fake_evaluations(monkeypatch, specs={"a": (("dual_planmask", "dual_noplan"), {}, {}),
                                              "b": (("co", "dual", "dual_residual"), {}, dict(level="carrier", plan_consistency=True, plan_shift_fraction=0.15))})
    cells, _ = b2_c2.merge_cells(ok)                                   # the declared recipe differences are allowed
    assert len(cells) == 15
    for label, over, training, message in (("source", {"source": {"files": "B"}}, {}, "source revision, runtime or known-data"),
                                           ("runtime", {"runtime": {"torch": "2.4", "threads": 8}}, {}, "source revision, runtime or known-data"),
                                           ("data", {"data_identity": "e" * 8}, {}, "source revision, runtime or known-data"),
                                           ("width", {}, {"width": 16}, "different training budgets"),
                                           ("epochs", {}, {"epochs": 30}, "different training budgets"),
                                           ("lr", {}, {"lr": 3e-3}, "different training budgets")):
        bad = fake_evaluations(monkeypatch, specs={"a": (("dual_planmask", "dual_noplan"), {}, {}), "b": (("co", "dual", "dual_residual"), over, training)})
        with pytest.raises(ValueError, match=message):
            b2_c2.merge_cells(bad)
    missing = fake_evaluations(monkeypatch, specs={"a": (("dual_planmask", "dual_noplan"), {}, {})})
    cells, results = b2_c2.load_evaluation("a")
    cells[(0, "dual_noplan")] = dataclasses.replace(cells[(0, "dual_noplan")], training=None)
    with pytest.raises(ValueError, match="lacks the per-model training configuration"):
        b2_c2.merge_cells(missing)


def test_each_evaluated_model_records_its_training_configuration(fixture, tmp_path, monkeypatch):
    _, _, out, _ = produce(fixture, tmp_path, monkeypatch)
    cells, results = b2_c2.load_evaluation(out)
    assert len(cells) == 6
    for model in results["models"]:
        assert model["training"]["input_mode"] == model["view"] and model["training"]["plan_consistency"] is False
        assert model["training"]["level"] == "absolute" and model["training"]["plan_shift_fraction"] == 0.0
    assert all(c.training is not None and c.training["epochs"] == 1 for c in cells.values())


def test_two_rosters_on_one_population_merge_into_twelve_cells_and_a_foreign_population_is_refused(fixture, tmp_path, monkeypatch):
    states = install_optional_artifacts(fixture, monkeypatch)
    _, dual_inventory = fit_roster(fixture, tmp_path)
    _, co_inventory = fit_roster(fixture, tmp_path, arms=("co_planmask", "co_noplan"), profile="c2-h3-co", tag="co")
    dual, _ = evaluate_roster(fixture, tmp_path, dual_inventory, name="evaluation-dual")
    co, _ = evaluate_roster(fixture, tmp_path, co_inventory, profile="c2-h3-co", name="evaluation-co")
    cells, scopes = b2_c2.merge_cells([dual, co])
    assert len(cells) == 12 and {p for _, p in scopes} == {"c2-h3-dual", "c2-h3-co"}
    report = b2_c2.run_contrasts([dual, co], n_boot=20)
    assert {n for n, r in report["contrasts"]["msp"].items() if r["status"] == "MEASURED"} == {
        "H3_planmask_vs_noplan_dual", "H3_planmask_vs_noplan_co", "H1_dual_vs_co_noplan"}
    with pytest.raises(ValueError, match="duplicate"):
        b2_c2.merge_cells([dual, dual])
    states["test_only"]["identity"] = "9" * 64                       # the same inventory scored on a different test-only artifact
    foreign, _ = evaluate_roster(fixture, tmp_path, co_inventory, profile="c2-h3-co", name="evaluation-foreign")
    with pytest.raises(ValueError, match="different populations or artifacts"):
        b2_c2.merge_cells([dual, foreign])


def test_inventory_for_a_matched_pair_must_be_the_complete_six_cell_roster(fixture, tmp_path, monkeypatch):
    install_optional_artifacts(fixture, monkeypatch)
    runs = []
    for seed in b2_c2.SEEDS:
        out = tmp_path / f"fit-{seed}"
        execution.fit_b2_models(tiny(("dual_planmask",), seed), fixture[3], out, log=lambda *_: None)
        execution.calibrate_b2_models(fixture[3], out, log=lambda *_: None)
        runs.append(out)
    with pytest.raises(ValueError, match="all six cells"):
        execution.freeze_inventory(runs, tmp_path / "half.json", seeds=b2_c2.SEEDS, profile="c2-h3-dual")
    assert not (tmp_path / "half.json").exists()
    with pytest.raises(ValueError, match="three seeds"):
        execution.freeze_inventory(runs[:2], tmp_path / "two.json", seeds=(0, 1), profile="c2-h3-dual")


def test_a_c2_inventory_cannot_be_evaluated_under_another_profile_and_opens_nothing_when_refused(fixture, tmp_path, monkeypatch):
    runs, inventory, out, _ = produce(fixture, tmp_path, monkeypatch)
    fixture[2].clear()
    for profile in ("proposed-full", "c2-h3-co"):
        with pytest.raises(ValueError):
            execution.evaluate_b2_inventory(fixture[3], inventory, tmp_path / f"refused-{profile}", profile=profile, log=lambda *_: None)
        assert fixture[2] == [] and not (tmp_path / f"refused-{profile}").exists()


def test_same_seed_matched_arms_share_data_order_and_budget_in_the_executor(fixture, tmp_path, monkeypatch):
    runs, *_ = produce(fixture, tmp_path, monkeypatch)
    for run in runs:
        plan, noplan = (execution.load(run / f"model_{v}.pt", device="cpu") for v in ("dual_planmask", "dual_noplan"))
        assert len(plan["history"]) == len(noplan["history"]) and plan["absolute_ref_db"] == noplan["absolute_ref_db"]
        assert plan["streaming"]["shard_orders"] == noplan["streaming"]["shard_orders"]
        keys = ("epochs", "batch", "width", "lr", "weight_decay", "seed", "level", "time_pool", "center_loss_weight",
                "plan_consistency", "plan_shift_fraction", "plan_shift_max_hz", "augment")
        assert {k: plan["config"][k] for k in keys} == {k: noplan["config"][k] for k in keys}
        assert plan["config"]["plan_consistency"] is False and plan["config"]["plan_shift_fraction"] == 0.0
        assert plan["n_parameters"] - noplan["n_parameters"] == 2 * 2 * 25          # only the two extra stem input channels (width 2, 5x5)


def test_a_primary_scorer_is_only_recorded_when_given_and_must_be_a_declared_scorer(fixture, tmp_path, monkeypatch):
    _, _, out, _ = produce(fixture, tmp_path, monkeypatch)
    assert b2_c2.run_contrasts([out], n_boot=5)["primary_scorer"] is None
    report, table = tmp_path / "r.json", tmp_path / "t.md"
    b2_c2.main(["contrasts", "--evaluation", str(out), "--out", str(report), "--table", str(table), "--n-boot", "5", "--primary-scorer", "mahalanobis"])
    assert json.loads(report.read_text())["primary_scorer"] == "mahalanobis" and "Primary scorer: mahalanobis" in table.read_text()
    with pytest.raises(ValueError):
        b2_c2.run_contrasts([out], n_boot=5, primary_scorer="softmax")
    with pytest.raises(SystemExit) as raised:
        b2_c2.main(["contrasts", "--evaluation", str(out), "--out", str(tmp_path / "x.json"), "--primary-scorer", "softmax"])
    assert raised.value.code == 2


def test_cli_roster_template_and_contrasts_write_strict_files(fixture, tmp_path, monkeypatch, capsys):
    _, _, out, _ = produce(fixture, tmp_path, monkeypatch)
    b2_c2.main(["roster"])
    assert json.loads(capsys.readouterr().out)["declared_fits"]["total_fits"] == 21
    template = tmp_path / "template.md"
    b2_c2.main(["template", "--out", str(template)])
    assert template.read_text() == b2_c2.comparison_table()
    report, table = tmp_path / "contrasts.json", tmp_path / "table.md"
    b2_c2.main(["contrasts", "--evaluation", str(out), "--out", str(report), "--table", str(table), "--n-boot", "20"])
    assert json.loads(report.read_text())["version"] == b2_c2.VERSION and "MEASURED" in table.read_text()
    with pytest.raises(SystemExit) as raised:
        b2_c2.main(["contrasts", "--evaluation", str(tmp_path / "missing"), "--out", str(tmp_path / "x.json")])
    assert raised.value.code == 2

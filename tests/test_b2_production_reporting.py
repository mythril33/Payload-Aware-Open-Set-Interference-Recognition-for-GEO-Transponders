"""Offline output validation and paired reporting, using synthetic inference only."""
import json

import pytest

from geoml import b2_production_reporting as report
from test_b2_production_evaluation import campaign  # noqa: F401


@pytest.fixture
def evaluated(campaign):
    campaign.run()
    campaign.run("c2-h3-dual", "matched-output")
    return [campaign.root / "output", campaign.root / "matched-output"]


def rewrite(root, filename, change):
    path = root / filename
    data = json.loads(path.read_text())
    change(data)
    path.write_text(json.dumps(data, allow_nan=False))
    marker = root / "completion.json"
    completion = json.loads(marker.read_text())
    completion[filename.replace(".json", "_sha256")] = report._sha256(path)
    marker.write_text(json.dumps(completion))


def test_report_all_fits_subgroups_primary_and_figures_without_model_or_data_reads(evaluated, monkeypatch, tmp_path):
    # The offline reporter must not revisit campaigns, weights or observations.
    def refuse(*_, **__):
        pytest.fail("offline report attempted a model/dataset read")
    monkeypatch.setattr(report.campaigns, "verify_campaign", refuse)
    monkeypatch.setattr(report.production, "_open", refuse)
    monkeypatch.setattr(report.production, "_training", refuse)
    result = report.write_report(evaluated, tmp_path / "report", n_boot=4, log=lambda _: None)
    assert result["primary_scorer"] == "mahalanobis" and result["fits"] == 15
    assert result["required_comparison_complete"] is True and result["benchmark_complete"] is False
    counts = {"headline": 500, "d1_exposure_excluded": 498, "k17d_co_feed_missing": 35,
              "k17d_excluding_co_feed_missing": 465}
    for name, n in counts.items():
        population = result["populations"][name]
        for method in report.c2.SCORERS:
            endpoint = population["endpoint"][method]
            assert endpoint["n_known"] == 8 * n and endpoint["n_unknown_near"] == 3 * n
            assert endpoint["descriptive_mean"] == 0.
            contrasts = population["contrasts"][method]
            for key in ("H1_dual_vs_co", "H2_residual_vs_dual", "H3_planmask_vs_noplan_dual"):
                assert contrasts[key]["status"] == "MEASURED"
                assert contrasts[key]["seed_summary"]["mean_delta"] == 0.
            assert contrasts["H3_planmask_vs_noplan_co"]["status"] == "NOT_RUN"
    output = tmp_path / "report"
    completion = json.loads((output / "completion.json").read_text())
    for name, digest in completion["files"].items():
        assert report._sha256(output / name) == digest
    assert (output / "near_fpr95.png").read_bytes().startswith(b"\x89PNG")
    assert (output / "near_fpr95.pdf").read_bytes().startswith(b"%PDF")
    assert "mahalanobis" in (output / "comparison.md").read_text()


def test_paired_h3_direction_known_negative_denominator_and_seed_mean(evaluated):
    def scores(rows):
        for row in rows:
            if row["view"] == "dual_planmask":
                row["unknown_scores"]["mahalanobis"] = [3.] * 4000
    def estimates(result):
        for row in result["models"]:
            if row["view"] == "dual_planmask":
                row["metrics"]["rejection"]["mahalanobis"]["pooled_near"]["ranking"]["unknown_fpr_at_95_tpr"] = 1.
    rewrite(evaluated[1], "predictions.json", scores)
    rewrite(evaluated[1], "results.json", estimates)
    result = report.run_report(evaluated, n_boot=2, log=lambda _: None)
    contrast = result["populations"]["headline"]["contrasts"]["mahalanobis"]["H3_planmask_vs_noplan_dual"]
    assert contrast["direction"] == "lower_is_better" and contrast["seed_summary"]["mean_delta"] == 1.
    assert contrast["seed_summary"]["ci95_of_mean_conditional_on_frozen_models"] == [1., 1.]
    assert all(r["baseline"] == 0. and r["richer"] == 1. for r in contrast["per_seed"])


def test_hash_tampering_rejected(evaluated):
    with (evaluated[0] / "predictions.json").open("a") as stream:
        stream.write(" ")
    with pytest.raises(ValueError, match="completion hashes"):
        report.load_evaluation(evaluated[0])


@pytest.mark.parametrize("change,match", [
    (lambda rows: rows.append(rows[0]), "duplicate"),
    (lambda rows: rows.pop(), "incomplete"),
    (lambda rows: rows[0]["sample_ids"].__setitem__(0, rows[0]["sample_ids"][1]), "scenario variant"),
    (lambda rows: rows[0]["matched"]["sample_ids"].pop(), "sample ID"),
    (lambda rows: rows[0]["unknown_families"]["families"].reverse(), "family order"),
    (lambda rows: rows[0]["unknown_scores"].pop("energy"), "three scorers"),
    (lambda rows: rows[0]["unknown_scores"]["mahalanobis"].pop(), "score vector"),
    (lambda rows: rows[0]["prediction"].__setitem__(0, 9), "class predictions"),
])
def test_semantic_corruption_refused_even_with_refreshed_hashes(evaluated, change, match):
    rewrite(evaluated[0], "predictions.json", change)
    with pytest.raises(ValueError, match=match):
        report.load_evaluation(evaluated[0])


def test_recomputed_point_estimate_must_match_persisted_result(evaluated):
    def change(result):
        result["models"][0]["metrics"]["rejection"]["mahalanobis"]["pooled_near"]["ranking"]["unknown_fpr_at_95_tpr"] = .8
    rewrite(evaluated[0], "results.json", change)
    with pytest.raises(ValueError, match="recomputed near-family"):
        report.load_evaluation(evaluated[0])


def test_primary_scorer_cannot_be_changed_after_campaign_freeze(evaluated):
    rewrite(evaluated[0], "results.json", lambda r: r.update(primary_scorer="msp"))
    with pytest.raises(ValueError, match="designation/binding"):
        report.load_evaluation(evaluated[0])


def test_partial_journal_completion_refused(evaluated):
    path = evaluated[0] / "completion.json"
    value = json.loads(path.read_text())
    value["journal_completion_recorded"] = False
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="journal completion"):
        report.load_evaluation(evaluated[0])


def test_profile_and_campaign_cannot_be_mixed(evaluated):
    with pytest.raises(ValueError, match="duplicate evaluation profile"):
        report.run_report([evaluated[0], evaluated[0]], n_boot=2)
    rewrite(evaluated[1], "results.json", lambda r: r.update(campaign_sha256="0" * 64))
    with pytest.raises(ValueError, match="profiles differ in campaign_sha256"):
        report.run_report(evaluated, n_boot=2)


@pytest.mark.parametrize("n_boot", [0, True, -1, 1.5])
def test_invalid_bootstrap_budget_refused_before_loading(n_boot):
    with pytest.raises(ValueError, match="positive integer"):
        report.run_report(["missing", "missing"], n_boot=n_boot)


def test_output_cannot_replace_evaluation_or_source(evaluated):
    for out in (evaluated[0], report.ROOT / "report-forbidden"):
        with pytest.raises(ValueError):
            report.write_report(evaluated, out, n_boot=2)


def test_recorded_primary_designation_is_accepted_without_fallback():
    path = report.ROOT / "docs/plan/b2_primary_scorer_2026-11-17.json"
    designation = report._strict(path)
    assert report.campaigns._designation("mahalanobis", designation) == designation
    with pytest.raises(ValueError):
        report.campaigns._designation("msp", designation)

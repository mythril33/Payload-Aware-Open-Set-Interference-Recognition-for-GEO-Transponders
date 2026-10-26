"""Evidence classes: every scanned file is classified, nothing is verified by default, restricted values stay hidden."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "dashboard"), str(ROOT / "src"), str(ROOT)]

from geodash import evidence as E  # noqa: E402

MAP_PATH = ROOT / "dashboard" / "data" / "evidence_map.json"


def _map():
    return json.loads(MAP_PATH.read_text(encoding="utf-8"))


def test_the_committed_map_has_a_known_schema_and_only_known_classes():
    data = _map()
    assert data["schema"] == "geo-dashboard-evidence-map/1"
    known = set(data["classes"])
    assert {"VERIFIED_HISTORICAL", "DEVELOPMENT_PILOT", "UNEXECUTED", "GATE_OR_APPROVAL",
            "DERIVED_DOCUMENTATION", "VERIFICATION_LOG", "RESTRICTED_HELDOUT_OBSERVATION",
            "PROTECTED_PRODUCTION", "UNCLASSIFIED"} <= known
    for path, row in data["entries"].items():
        assert row["class"] in known, path
        assert row["rationale"], path


def test_every_scanned_result_and_gate_file_is_classified_and_no_entry_is_stale():
    entries = E.inventory()
    assert not [e.path for e in entries if e.evidence_class == E.UNCLASSIFIED], "unclassified files exist"
    assert not [e.path for e in entries if e.evidence_class == E.STALE], "map entries point at missing files"


def test_scanning_covers_results_and_json_plans_but_not_figures_or_narrative_plans():
    scanned = E.scanned_files()
    assert any(p.startswith("docs/results/") for p in scanned)
    assert all(p.endswith(".json") for p in scanned if p.startswith("docs/plan/"))
    assert not any("/figures/" in p for p in scanned)
    assert "docs/plan/DURUM.md" not in scanned


def test_restricted_entries_never_display_their_values():
    for entry in E.inventory():
        if entry.evidence_class == E.RESTRICTED:
            assert entry.values_displayable is False
    restricted = [e.path for e in E.inventory() if e.evidence_class == E.RESTRICTED]
    assert "docs/results/b2_physical_figure_data.json" in restricted
    assert "docs/results/b2_observed_predictions.json" in restricted


def test_unexecuted_experiments_are_the_proposals_and_specs_that_are_not_run():
    unexecuted = {e.path for e in E.inventory() if e.evidence_class == E.UNEXECUTED}
    assert unexecuted == {
        "docs/plan/b2_c2_experiment_matrix.json",
        "docs/plan/b2_e7_training_proposal.json",
        "docs/plan/b2_e8_gpu_probe_spec.json",
        "docs/plan/b2_e9_approved_scientific_protocol.json",
    }


def test_no_protected_production_evaluation_is_recorded():
    protected = [e.path for e in E.inventory() if e.evidence_class == E.PROTECTED_PRODUCTION]
    assert protected == [], "a protected production evaluation would have to be authorized and recorded first"
    assert all(row["class"] != "PROTECTED_PRODUCTION" for row in _map()["entries"].values())


def test_unmapped_files_are_unclassified_and_map_rows_for_missing_files_are_stale(tmp_path):
    results = tmp_path / "docs" / "results"
    plan = tmp_path / "docs" / "plan"
    results.mkdir(parents=True)
    plan.mkdir(parents=True)
    (results / "new_run.json").write_text("{}")
    evidence_map = {"schema": "geo-dashboard-evidence-map/1",
                    "classes": {"DEVELOPMENT_PILOT": "pilot", "UNCLASSIFIED": "unknown"},
                    "entries": {"docs/results/gone.json": {"class": "DEVELOPMENT_PILOT", "rationale": "x",
                                                          "heldout_raw_matches": {}}}}
    entries = {e.path: e.evidence_class for e in E.inventory(evidence_map, repo_root=tmp_path)}
    assert entries == {"docs/results/new_run.json": E.UNCLASSIFIED, "docs/results/gone.json": E.STALE}


def test_an_unknown_class_in_the_map_is_refused(tmp_path):
    (tmp_path / "docs" / "results").mkdir(parents=True)
    (tmp_path / "docs" / "results" / "x.json").write_text("{}")
    evidence_map = {"schema": "geo-dashboard-evidence-map/1", "classes": {"A": "a"},
                    "entries": {"docs/results/x.json": {"class": "VERIFIED", "rationale": "x",
                                                        "heldout_raw_matches": {}}}}
    with pytest.raises(ValueError, match="unknown evidence class"):
        E.inventory(evidence_map, repo_root=tmp_path)


def test_counts_by_class_add_up_to_the_number_of_files():
    entries = E.inventory()
    assert sum(E.counts_by_class(entries).values()) == len(entries)

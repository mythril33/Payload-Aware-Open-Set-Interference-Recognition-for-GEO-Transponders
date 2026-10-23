"""The E6 decision packet's numbers are reproducible from committed evidence and approve nothing."""
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location("b2_e6_decision_evidence", ROOT / "scripts" / "b2_e6_decision_evidence.py")
ev = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ev)
COMMITTED = ROOT / "docs" / "results" / "b2_e6_decision_evidence.json"


def test_k17d_recomputes_the_committed_summary_from_the_raw_rows():
    result = ev.k17d()
    assert result["matches_committed_summary"] is True
    assert (result["n_test_groups"], result["missing_carrier_groups"]) == (500, 78)
    assert (result["co_feed_drops"], result["cross_feed_drops"]) == (35, 43)
    assert result["cross_feed_max_abs_drift_db"] < 1e-12
    assert result["co_feed_groups_at_least_db"] == {"0.5": 19, "1.0": 15, "3.0": 4}
    assert result["share_of_test_groups_at_least_bin_width"] == pytest.approx(4 / 500)
    assert result["co_feed_drift_db"]["max"] == pytest.approx(5.912131896846286)


def test_k18_ratio_between_the_two_conventions_is_half_the_embedding_dimension():
    result = ev.k18()
    assert result["ratio_equals_half_embedding_dim"] is True
    assert {view["embedding_dim"] for view in result["views"].values()} == {128}
    assert all(view["p20_fraction_of_ce"] < 1e-4 for view in result["views"].values())     # negligible at the pilot scale


def test_phase_ceiling_formula_agrees_with_a_seeded_monte_carlo():
    for duration in (ev.SNAPSHOT_S, 6.4e-6, 1.78e-6):
        assert ev.monte_carlo_ceiling_db(duration, n=6000) == pytest.approx(ev.ceiling_db(duration), abs=0.15)
    assert ev.ceiling_db(ev.SNAPSHOT_S) == pytest.approx(21.74, abs=0.01)         # the documented 21-25 dB ceiling
    assert ev.monte_carlo_ceiling_db(6.4e-6, n=2000, seed=1) == ev.monte_carlo_ceiling_db(6.4e-6, n=2000, seed=1)


def test_the_35_db_proposal_is_reachable_only_for_the_widest_carriers():
    result = ev.obs_cancel(n=2000)
    assert result["min_symbol_rate_mbaud_for_target"] == {"64_symbols": 31.8, "128_symbols": 63.6}
    assert result["segment_duration_for_target_us"] == pytest.approx(2.01, abs=0.01)
    rows = {row["symbol_rate_mbaud"]: row for row in result["ceiling_by_symbol_rate"]}
    assert rows[36.0]["segment_64_symbols"]["meets_target"] is True
    assert rows[36.0]["segment_128_symbols"]["meets_target"] is False
    assert not any(rows[rate][f"segment_{n}_symbols"]["meets_target"] for rate in (1.0, 1.5, 3.6, 6.0, 10.0, 20.0, 28.8) for n in (64, 128))
    assert rows[1.0]["segment_64_symbols"]["ceiling_db"] == pytest.approx(result["obs_cancel_1_ceiling_db"], abs=0.05)
    assert result["added_canceller_hours_if_twice_obs_cancel_1"] == pytest.approx(7.95, abs=0.01)
    assert result["raw_iq_stored"] is False


def test_evidence_is_strict_json_approves_nothing_and_matches_the_committed_record():
    fresh = ev.evidence(mc_samples=2000)
    json.loads(json.dumps(fresh, allow_nan=False))
    assert fresh["approves_nothing"] is True and fresh["benchmark_complete"] is False
    committed = json.loads(COMMITTED.read_text())
    assert committed["approves_nothing"] is True and committed["benchmark_complete"] is False
    assert committed["k17d"] == fresh["k17d"] and committed["k18"] == fresh["k18"]
    for key in ("linewidth_hz", "snapshot_us", "obs_cancel_1_ceiling_db", "segment_duration_for_target_us",
                "min_symbol_rate_mbaud_for_target", "ceiling_by_symbol_rate", "added_canceller_hours_if_twice_obs_cancel_1"):
        assert committed["obs_cancel_2"][key] == fresh["obs_cancel_2"][key]
    for old, new in zip(committed["obs_cancel_2"]["cross_check"], fresh["obs_cancel_2"]["cross_check"]):
        assert old["analytic_db"] == new["analytic_db"] and abs(old["monte_carlo_db"] - old["analytic_db"]) < 0.1


def test_the_script_refuses_to_overwrite_evidence(tmp_path):
    target = tmp_path / "evidence.json"
    target.write_text("{}")
    with pytest.raises(SystemExit) as refused:
        ev.main(["--out", str(target), "--mc-samples", "100"])
    assert refused.value.code == 2 and target.read_text() == "{}"

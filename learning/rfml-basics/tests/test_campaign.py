"""Smoke test for experiments/run_campaign.py: runs the real runner as a
subprocess on the quick scale with one seed, then checks the aggregate's
structure, strictness and hypothesis bookkeeping."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "experiments" / "run_campaign.py"


def test_campaign_quick_single_seed(tmp_path):
    out = tmp_path / "campaign"
    proc = subprocess.run(
        [sys.executable, str(RUNNER), "--scale", "quick", "--seeds", "0", "--out", str(out), "--threads", "2"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr

    agg = json.loads((out / "aggregate.json").read_text())
    assert agg["failures"] == []
    assert agg["provenance"]["seeds"] == [0]
    assert agg["provenance"]["scale"]["name"] == "quick"

    # Every declared stage produced every declared metric for the one seed.
    for stage in ("modulation", "modulation_ideal", "fingerprint", "fingerprint_ideal", "open_set"):
        assert stage in agg["metrics"], stage
        for name, s in agg["metrics"][stage].items():
            assert len(s["per_seed"]) == 1, (stage, name)
            assert s["sd"] is None  # single seed: no sample sd

    # Hypotheses: computed, sign bookkeeping consistent, no support verdict at n=1.
    for h in (
        "H1_dist_minus_msp_auroc",
        "H2_obj_minus_msp_unk_reject",
        "H3_fp_impaired_minus_ideal_acc",
        "H4_mod_ideal_minus_impaired_cnn",
    ):
        rec = agg["hypotheses"][h]
        assert rec["n_seeds"] == 1
        assert rec["n_positive"] == sum(d > 0 for d in rec["per_seed_diff"])
        assert rec["supported"] is None

    # Slim per-seed files are strict JSON and carry no bulky score arrays.
    slim = json.loads((out / "open_set_seed0.json").read_text())
    for variant in slim["variants"].values():
        assert "scores" not in variant
    # Raw keeps the scores for recomputation.
    raw = json.loads((out / "raw" / "open_set_seed0.json").read_text())
    assert all("scores" in v for v in raw["variants"].values())

    # The generated summary table exists and mentions every stage.
    summary = (out / "aggregate_summary.md").read_text()
    for stage in ("modulation", "fingerprint", "open_set"):
        assert stage in summary

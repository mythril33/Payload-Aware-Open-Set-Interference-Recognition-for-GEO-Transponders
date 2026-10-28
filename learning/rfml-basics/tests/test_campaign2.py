"""Smoke test for experiments/run_campaign2.py: runs the real runner as a
subprocess on the quick scale with one seed, then checks the aggregate's
structure, strictness and hypothesis bookkeeping.

Builder note: rfml.experiments.run_scorer_bench is being added in parallel.
Until it lands, this module skips cleanly instead of failing."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ex = pytest.importorskip("rfml.experiments")

pytestmark = pytest.mark.skipif(
    not hasattr(ex, "run_scorer_bench"),
    reason="rfml.experiments.run_scorer_bench not yet available (campaign-2 builder A in flight)",
)

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "experiments" / "run_campaign2.py"

VARIANT_KEYS = (
    "CE+MSP",
    "CE+maxlogit",
    "CE+energy",
    "CE+distance",
    "CE+mahalanobis",
    "OS-full+MSP",
    "OS-16PSK+MSP",
    "OS-8PAM+MSP",
)
OS_ARMS = ("OS-full+MSP", "OS-16PSK+MSP", "OS-8PAM+MSP")
HYPOTHESES2 = (
    "H5_mahal_minus_euclid_auroc",
    "H6_energy_minus_msp_auroc",
    "H7_pamarm_minus_pskarm_4pam_reject",
    "H8_msp_low_minus_high_auroc",
)


def test_campaign2_quick_single_seed(tmp_path):
    out = tmp_path / "campaign2"
    proc = subprocess.run(
        [sys.executable, str(RUNNER), "--scale", "quick", "--seeds", "0", "--out", str(out), "--threads", "2"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=900,
        check=False,  # the return code is asserted below with the captured output
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr

    agg = json.loads((out / "aggregate.json").read_text())
    assert agg["failures"] == []
    assert agg["provenance"]["seeds"] == [0]
    assert agg["provenance"]["scale"]["name"] == "quick"

    # Every pre-registered METRICS2 key is present for the one seed.
    metrics = agg["metrics"]["scorer_bench"]
    expected = []
    for v in VARIANT_KEYS:
        expected += [f"{v}:auroc", f"{v}:unk_reject", f"{v}:known_accept", f"{v}:oscr_auc"]
    for v in ("CE+MSP",) + OS_ARMS:
        expected += [f"{v}:reject_4PAM", f"{v}:reject_64QAM"]
    expected += ["CE+MSP:auroc_low_le2", "CE+MSP:auroc_high_ge10"]
    for name in expected:
        assert name in metrics, name
        assert len(metrics[name]["per_seed"]) == 1, name

    # Hypotheses: computed, no support verdict at n=1.
    for h in HYPOTHESES2:
        rec = agg["hypotheses"][h]
        assert rec["n_seeds"] == 1
        assert rec["supported"] is None

    # Slim per-seed file is strict JSON and carries no bulky score arrays.
    slim = json.loads((out / "scorer_bench_seed0.json").read_text())
    for variant in slim["variants"].values():
        assert "scores" not in variant
    # Raw keeps the scores for recomputation.
    raw = json.loads((out / "raw" / "scorer_bench_seed0.json").read_text())
    assert all("scores" in v for v in raw["variants"].values())

    # The generated summary table exists and mentions the stage.
    summary = (out / "aggregate_summary.md").read_text()
    assert "scorer_bench" in summary

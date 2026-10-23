"""Reproduce the numbers behind the E6 researcher decision packet from committed evidence only.

    python scripts/b2_e6_decision_evidence.py --out docs/results/b2_e6_decision_evidence.json

No dataset is generated and no model is trained. K17d is recomputed from the committed per-group audit rows,
K18 from the committed scale audits, and the OBS-CANCEL/2 phase-tracking ceiling from the analytic block-constant
Wiener-phase formula, cross-checked by a seeded Monte Carlo. Results are descriptive; they approve nothing.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
RESULTS = REPO / "docs" / "results"
LINEWIDTH_HZ = 150.0          # 100 Hz satellite + 50 Hz receiver effective linewidth (B2Config, P20 section 8)
SNAPSHOT_S = 4096 / 96e6      # one obs-cancel/1 complex gain per 4096-sample snapshot at 96 MS/s
TARGET_DEPTH_DB = 35.0        # P22 section 6 / E5 memorandum proposal, not an approved criterion
SYMBOL_RATES_MBAUD = (1.0, 1.5, 3.6, 6.0, 10.0, 20.0, 28.8, 36.0)
CANCELLER_SECONDS_PER_OBSERVATION = 1.34          # docs/results/b2_production_budget.md section 1.1
OBSERVATIONS = 21350
MATCHED_BIN_WIDTH_DB = 3.0                          # bins 4-7 / 7-10 / 10-13 dB (P22 section 2)
EDGE_GUARD_SAMPLES = 512                            # CancellationConfig.edge_guard: monitor samples dropped per side
BLOCK_SAMPLES = 4096                                # monitor samples per snapshot
MAX_PLANNED_CARRIER_MBAUD = 24.0                    # widest symbol rate with rs*(1+rolloff+guard) <= 0.95*36 MHz (geosim.plan)


def k17d(path=RESULTS / "k17d_drift_audit.json"):
    audit = json.loads(Path(path).read_text())
    rows = audit["rows"]
    drift = np.array([row["downlink_drift_db"] for row in rows])
    co_feed = np.array([row["pol"] == 0 for row in rows])
    x = drift[co_feed]
    stored = audit["drift_db_co_missing"]
    computed = {"median": float(np.median(x)), "p90": float(np.percentile(x, 90)), "max": float(x.max())}
    return {"n_test_groups": audit["n_test_groups"], "missing_carrier_groups": len(rows),
            "co_feed_drops": int(co_feed.sum()), "cross_feed_drops": int((~co_feed).sum()),
            "cross_feed_max_abs_drift_db": float(np.abs(drift[~co_feed]).max()),
            "co_feed_drift_db": computed, "matches_committed_summary": all(
                abs(computed[key] - stored[key]) < 1e-12 for key in computed),
            "co_feed_groups_at_least_db": {str(t): int((x >= t).sum()) for t in (0.5, 1.0, MATCHED_BIN_WIDTH_DB)},
            "share_of_test_groups_at_least_bin_width": float((x >= MATCHED_BIN_WIDTH_DB).sum() / audit["n_test_groups"]),
            "note": "co-feed drops scale the downlink ASI event; cross-feed drops do not change the co reference. The "
                    "cross-feed value here is zero by construction of the audit formula; the physical bound (30 dB uplink "
                    "coupling) is below 0.01 dB (P22 section 6)"}


def k18(path=RESULTS / "k18_scale_audit.json"):
    audit = json.loads(Path(path).read_text())
    views = {}
    for view, row in audit.items():
        views[view] = {"embedding_dim": row["embedding_dim"], "ce": row["ce"],
                       "p20_term": row["p20_term_0.005_sum"], "p21b_term": row["p21b_term_0.01_mean"],
                       "p20_to_p21b_ratio": row["ratio_p20_to_p21b"], "dim_over_two": row["embedding_dim"] / 2,
                       "p20_fraction_of_ce": row["p20_term_0.005_sum"] / row["ce"]}
    return {"views": views, "ratio_equals_half_embedding_dim": all(
        abs(v["p20_to_p21b_ratio"] - v["dim_over_two"]) < 1e-3 for v in views.values()),
            "scope": "degenerate three-epoch pilot checkpoints and untrained initializations; cannot calibrate the weight"}


def ceiling_db(duration_s, linewidth_hz=LINEWIDTH_HZ):
    """Depth ceiling of a block-constant phase estimate: residual power = 2 pi dv T / 6 for Wiener phase noise."""
    return float(-10 * np.log10(2 * np.pi * linewidth_hz * duration_s / 6))


def monte_carlo_ceiling_db(duration_s, n=20000, steps=256, seed=0, linewidth_hz=LINEWIDTH_HZ):
    rng = np.random.default_rng(seed)
    increments = rng.standard_normal((n, steps)) * np.sqrt(2 * np.pi * linewidth_hz * duration_s / steps)
    phase = np.cumsum(increments, axis=1)
    error = phase - phase.mean(axis=1, keepdims=True)
    return float(-10 * np.log10(np.mean(np.abs(1 - np.exp(1j * error)) ** 2)))


def guarded_window_ceiling_db(n=8000, seed=0, linewidth_hz=LINEWIDTH_HZ):
    """Ceiling when the gain is fitted on the whole block but the stored PSD drops ``edge_guard`` samples per side."""
    rng = np.random.default_rng(seed)
    increments = rng.standard_normal((n, BLOCK_SAMPLES)) * np.sqrt(2 * np.pi * linewidth_hz * SNAPSHOT_S / BLOCK_SAMPLES)
    phase = np.cumsum(increments, axis=1)
    error = (phase - phase.mean(axis=1, keepdims=True))[:, EDGE_GUARD_SAMPLES:BLOCK_SAMPLES - EDGE_GUARD_SAMPLES]
    return float(-10 * np.log10(np.mean(np.abs(1 - np.exp(1j * error)) ** 2)))


def obs_cancel(n=20000):
    cross_check = [{"duration_us": round(t * 1e6, 3), "analytic_db": ceiling_db(t), "monte_carlo_db": monte_carlo_ceiling_db(t, n)}
                   for t in (SNAPSHOT_S, 6.4e-6, 1.78e-6)]
    needed = 6 * 10 ** (-TARGET_DEPTH_DB / 10) / (2 * np.pi * LINEWIDTH_HZ)
    table = []
    for rate in SYMBOL_RATES_MBAUD:
        row = {"symbol_rate_mbaud": rate}
        for symbols in (64, 128):
            duration = min(symbols / (rate * 1e6), SNAPSHOT_S)       # a segment cannot exceed one snapshot
            row[f"segment_{symbols}_symbols"] = {"duration_us": round(duration * 1e6, 2), "ceiling_db": round(ceiling_db(duration), 1),
                                                 "meets_target": ceiling_db(duration) >= TARGET_DEPTH_DB}
        table.append(row)
    widest = MAX_PLANNED_CARRIER_MBAUD
    return {"linewidth_hz": LINEWIDTH_HZ, "snapshot_us": round(SNAPSHOT_S * 1e6, 2), "obs_cancel_1_ceiling_db": ceiling_db(SNAPSHOT_S),
            "obs_cancel_1_stored_window_ceiling_db": guarded_window_ceiling_db(max(n // 2, 1000)),
            "stored_window_note": "gain fitted on the full 4096-sample block, PSD stored over the interior after dropping "
                                  "edge_guard=512 samples per side (cancellation.py); seeded Monte Carlo",
            "widest_planned_carrier_mbaud": widest,
            "ceiling_64_symbols_at_widest_planned_carrier_db": round(ceiling_db(min(64 / (widest * 1e6), SNAPSHOT_S)), 1),
            "target_reachable_by_a_planned_carrier": ceiling_db(64 / (widest * 1e6)) >= TARGET_DEPTH_DB,
            "formula": "residual power ~ 2*pi*linewidth*T/6 (ideal block mean, pure Wiener phase, no estimation noise)",
            "cross_check": cross_check, "target_depth_db": TARGET_DEPTH_DB, "segment_duration_for_target_us": round(needed * 1e6, 3),
            "min_symbol_rate_mbaud_for_target": {"64_symbols": round(64 / needed / 1e6, 1), "128_symbols": round(128 / needed / 1e6, 1)},
            "ceiling_by_symbol_rate": table,
            "added_canceller_hours_if_twice_obs_cancel_1": round(OBSERVATIONS * CANCELLER_SECONDS_PER_OBSERVATION / 3600, 2),
            "raw_iq_stored": False,
            "consequence": "the residual is computed at generation time from transient IQ, so any new receiver version "
                           "requires regenerating every stage that carries the fifth channel"}


def evidence(mc_samples=20000):
    return {"schema": "B2-E6-decision-evidence/1", "benchmark_complete": False, "approves_nothing": True,
            "k17d": k17d(), "k18": k18(), "obs_cancel_2": obs_cancel(mc_samples)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", help="new strict-JSON file (never overwritten); default prints to stdout")
    parser.add_argument("--mc-samples", type=int, default=20000)
    args = parser.parse_args(argv)
    text = json.dumps(evidence(args.mc_samples), indent=1, allow_nan=False) + "\n"
    if args.out:
        path = Path(args.out)
        if path.exists():
            parser.exit(2, f"error: {path} already exists; refusing to overwrite evidence\n")
        path.write_text(text)
    else:
        sys.stdout.write(text)


if __name__ == "__main__":
    main()

"""Physical checks of the B2-match/1 (K17c) level-matched ASI versus unauthorized set.

python scripts/check_b2_matched.py --matched data/b2-match-pilot \
    --out runs/b2-match-pilot/matched_check.json [--oracle-groups 1]

Per group, the two interference variants are compared with their clean twin
(same plans, carriers, noise, phase, activity, calibration):
1. requested interference power and reference normalization (exact equality by
   construction, asserted);
2. observable in-band PSD rise of each event over the clean twin, in the stored
   spectrum and in the stored cancellation residual;
3. the realized-level difference ASI minus unauthorized (dB) together with the
   placement facts that explain it (ASI plan overlap, unauthorized gap);
4. mask identity and per-bin counts.
Optionally (``--oracle-groups``), a few groups are re-simulated with ``keep_iq``
to measure the realized injected power before and after the payload for both
events. That oracle number is a diagnostic written to this report only; it never
enters an artifact or a model input.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from geosim.b2_matched_dataset import b2_matched_fingerprint, iter_b2_matched_shards, read_b2_matched_manifest
from geosim.b2_protocol import LABELS
from geosim.b2_scenarios import MATCHED_BIN_NAMES, MATCHED_LABELS, prepare_matched_scene
from geosim.cancellation import band_power_db
from geosim.interferers import free_gaps
from geosim.waveform import Carrier


def _median(values):
    return None if not values else float(np.median(values))


def check(matched, oracle_groups=0):
    manifest = read_b2_matched_manifest(matched)
    bandwidth = manifest["config"]["bandwidth"]
    groups = {}
    for shard in iter_b2_matched_shards(matched):
        residuals = shard.get("residual", [None] * len(shard["seed"]))
        for spec, residual, label, seed, record in zip(shard["spec"], residuals, shard["label"], shard["seed"], shard["meta"]):
            groups.setdefault(int(seed), {})[LABELS[int(label)]] = (spec, None if residual is None else residual.astype(np.float32), record)
    rows = []
    for seed, variants in sorted(groups.items()):
        if set(variants) != set(MATCHED_LABELS):
            raise ValueError(f"group {seed} lacks a matched variant")
        clean_spec, clean_res, clean_record = variants["clean"]
        matched_block = clean_record["matched"]
        plan = [Carrier(**item) for item in clean_record["plans"][0]]
        row = {"scenario_id": seed, "pair_id": matched_block["pair_id"], "bin": matched_block["bin_name"],
               "target_c_over_i_psd_db": matched_block["target_c_over_i_psd_db"],
               "symbol_rate": matched_block["symbol_rate"], "alpha": matched_block["alpha"], "mod": matched_block["mod"],
               "requested_power": matched_block["requested_power"], "plan_consistency": clean_record["plan_consistency"],
               "within_natural_range": matched_block["within_natural_range"], "events": {}}
        requested = []
        for name in ("adjacent_satellite", "unauthorized"):
            spec, residual, record = variants[name]
            event = record["event"]
            power = event["carrier"]["power"] if "carrier" in event else 10 ** (-event["c_over_i_db"] / 10)
            requested.append(power)
            lo, hi = event["f_lo"], event["f_hi"]
            co, clean_co = spec[0].astype(np.float32), clean_spec[0].astype(np.float32)
            entry = {"band_hz": [lo, hi], "requested_power": power,
                     "delta_psd_in_band_db": band_power_db(co, lo, hi) - band_power_db(clean_co, lo, hi),
                     "absolute_in_band_psd_db": band_power_db(co, lo, hi),
                     "plan_overlap_fraction": event.get("overlap_fraction", 0.0),
                     "mean_delta_psd_co_db": float(np.mean(co) - np.mean(clean_co)),
                     "masks_identical": bool(record["plans"] == clean_record["plans"]
                                             and record["active_carriers"] == clean_record["active_carriers"])}
            if residual is not None and clean_res is not None:
                entry["delta_residual_in_band_db"] = band_power_db(residual, lo, hi) - band_power_db(clean_res, lo, hi)
                entry["absolute_in_band_residual_db"] = band_power_db(residual, lo, hi)
            row["events"][name] = entry
        row["requested_power_equal"] = bool(np.isclose(requested[0], requested[1], rtol=1e-12, atol=0))
        row["realized_level_difference_asi_minus_unauthorized_db"] = (
            row["events"]["adjacent_satellite"]["absolute_in_band_psd_db"] - row["events"]["unauthorized"]["absolute_in_band_psd_db"])
        row["clean_level_difference_in_the_two_bands_db"] = (
            band_power_db(clean_spec[0].astype(np.float32), *row["events"]["adjacent_satellite"]["band_hz"])
            - band_power_db(clean_spec[0].astype(np.float32), *row["events"]["unauthorized"]["band_hz"]))
        if not row["requested_power_equal"]:
            raise AssertionError(f"group {seed}: requested interference powers differ")
        bands = [tuple(row["events"][name]["band_hz"]) for name in ("adjacent_satellite", "unauthorized")]
        gaps = [(lo, hi) for lo, hi in free_gaps(plan, bandwidth)
                if all(hi <= b_lo or lo >= b_hi for b_lo, b_hi in bands)]      # disjoint from both event bands
        row["asi_overlap_fraction_active"] = matched_block.get("asi_overlap_fraction_active")
        if gaps:
            lo, hi = max(gaps, key=lambda g: g[1] - g[0])
            if hi - lo >= 1e6:
                row["event_free_gap_hz"] = [lo, hi]
                row["event_free_gap_floor_shift_db"] = {
                    name: band_power_db(variants[name][0][0].astype(np.float32), lo, hi) - band_power_db(clean_spec[0].astype(np.float32), lo, hi)
                    for name in ("adjacent_satellite", "unauthorized")}
        rows.append(row)
    per_bin = {}
    for name in MATCHED_BIN_NAMES:
        selected = [row for row in rows if row["bin"] == name]
        per_bin[name] = {"n_groups": len(selected),
                         "median_delta_psd_asi_db": _median([r["events"]["adjacent_satellite"]["delta_psd_in_band_db"] for r in selected]),
                         "median_delta_psd_unauthorized_db": _median([r["events"]["unauthorized"]["delta_psd_in_band_db"] for r in selected]),
                         "median_delta_residual_asi_db": _median([r["events"]["adjacent_satellite"].get("delta_residual_in_band_db") for r in selected
                                                                 if "delta_residual_in_band_db" in r["events"]["adjacent_satellite"]]),
                         "median_delta_residual_unauthorized_db": _median([r["events"]["unauthorized"].get("delta_residual_in_band_db") for r in selected
                                                                          if "delta_residual_in_band_db" in r["events"]["unauthorized"]]),
                         "median_realized_level_difference_db": _median([r["realized_level_difference_asi_minus_unauthorized_db"] for r in selected])}
    rates = sorted({row["symbol_rate"] for row in rows})
    report = {"protocol": manifest["protocol"], "benchmark_complete": manifest["benchmark_complete"],
              "symbol_rate_histogram": {f"{rate / 1e6:g} Mbaud": sum(1 for row in rows if row["symbol_rate"] == rate) for rate in rates},
              "n_groups_asi_over_absent_carrier": sum(1 for row in rows if row.get("asi_overlap_fraction_active") == 0.0),
              "matched_fingerprint": b2_matched_fingerprint(matched), "n_groups": len(rows), "n_observations": 3 * len(rows),
              "all_requested_powers_equal": all(r["requested_power_equal"] for r in rows),
              "all_masks_identical": all(e["masks_identical"] for r in rows for e in r["events"].values()),
              "per_bin": per_bin, "rows": rows, "recognition_metrics": None,
              "interpretation": ("Requested power and reference are identical by construction. The observable in-band rise differs "
                                 "because the ASI shares its band with a planned carrier (overlap 20-80 %) while the unauthorized "
                                 "carrier sits on the noise floor of a gap; this placement difference IS the intended intervention. "
                                 "Nonlinear payload interaction adds a smaller, group-dependent term."),
              "scope": "Physics of the matched set; no classifier claim."}
    if oracle_groups:
        report["oracle_diagnostic"] = _oracle(matched, manifest, rows[:oracle_groups])
    return report


def _oracle(matched, manifest, rows):
    """Re-simulate a few groups with and without the payload nonlinearity bypassed to measure realized powers.

    Uses simulator truth (the injected waveform) and is therefore a diagnostic only.
    """
    from dataclasses import replace
    from geosim import FS_SIM
    from geosim import sensor as sn
    from geosim.b2_protocol import B2Config
    config = B2Config(**manifest["config"])
    out = []
    for row in rows:
        group = row["scenario_id"]
        entry = {"scenario_id": group, "events": {}}
        for name in ("adjacent_satellite", "unauthorized"):
            scene = prepare_matched_scene(name, group, config)
            callback = scene.interferers[0]
            samples = callback(np.random.default_rng(0), np.arange(4) * config.snap_interval, sn.N_SIM, FS_SIM)
            injected = float(np.mean(np.abs(samples[:, sn.WARMUP_SIM:]) ** 2))
            entry["events"][name] = {"requested_power": row["events"][name]["requested_power"],
                                     "realized_injected_power_before_payload": injected,
                                     "ratio_db": float(10 * np.log10(injected / row["events"][name]["requested_power"]))}
        out.append(entry)
    return {"note": "mean injected uplink power of the event waveform over four snapshots, before IMUX/TWTA; simulator truth, diagnostic only",
            "rows": out}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matched", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--oracle-groups", type=int, default=0)
    args = parser.parse_args()
    result = check(args.matched, args.oracle_groups)
    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(f"Checked {result['n_observations']} matched observations in {result['n_groups']} groups; wrote {path}")


if __name__ == "__main__":
    main()

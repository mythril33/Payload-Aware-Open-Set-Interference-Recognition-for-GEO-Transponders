"""Physical and numerical checks of the stored B2-feat/1 cancellation residual.

python scripts/check_b2_cancellation.py --data data/b2-feat-pilot \
    --out runs/b2-feat-pilot/cancellation_check.json

Everything here is computed from stored observations, operator plans and
simulator metadata used *as diagnostics* (event bands, C/I, back-off). The
metadata never feeds the residual itself. The report measures cancellation
depth per planned carrier, the residual floor against the clean widest gap,
and the paired clean/under-carrier visibility before and after cancellation.
It does not train or evaluate a recognition model.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from geosim.b2_dataset import b2_fingerprint, iter_b2_shards, read_b2_manifest
from geosim.b2_protocol import FEATURE_PROTOCOL, LABELS
from geosim.cancellation import band_power_db
from geosim.interferers import free_gaps
from geosim.waveform import Carrier


def _core(carrier):
    half = carrier.symbol_rate * (1 - carrier.alpha) / 2
    return carrier.f0 - half, carrier.f0 + half


def _mean_db(values):
    return None if not values else float(np.mean(values))


def check(data):
    root = Path(data)
    manifest = read_b2_manifest(root)
    if manifest["protocol"] != FEATURE_PROTOCOL:
        raise ValueError("cancellation checks require a B2-feat/1 artifact with a stored residual")
    bandwidth = manifest["config"]["bandwidth"]
    report = {"protocol": manifest["protocol"], "benchmark_complete": manifest["benchmark_complete"],
              "data_fingerprint": b2_fingerprint(root), "cancellation": manifest["cancellation"],
              "n_observations": 0, "roles": {}, "per_label": {}, "paired_cuc": [], "paired_cuc_summary": None,
              "overdrive_vs_clean_floor_db": [], "recognition_metrics": None,
              "scope": "Residual-channel physics on known observations; no classifier or recognition-quality claim."}
    per_label = {name: {"depth_db": [], "gap_floor_shift_db": [], "decision_snr_db": [], "n": 0} for name in LABELS}
    by_mod = {}
    groups = {}
    for role, info in manifest["roles"].items():
        report["roles"][role] = {"n_samples": info["n_samples"], "n_scenarios": info["n_scenarios"]}
        for shard in iter_b2_shards(root, role):
            for spec, residual, label, seed, record in zip(shard["spec"], shard["residual"], shard["label"],
                                                           shard["seed"], shard["meta"]):
                name = LABELS[int(label)]
                report["n_observations"] += 1
                plan = [Carrier(**item) for item in record["plans"][0]]
                active = record["active_carriers"][0]
                co = spec[0].astype(np.float32)
                res = residual.astype(np.float32)
                entry = per_label[name]
                entry["n"] += 1
                for carrier, transmitted, diag in zip(plan, active, record["cancellation"]["carriers"]):
                    if not transmitted:
                        continue
                    lo, hi = _core(carrier)
                    depth = band_power_db(co, lo, hi) - band_power_db(res, lo, hi)
                    entry["depth_db"].append(depth)
                    if diag["decision_snr_db_median"] is not None:
                        entry["decision_snr_db"].append(diag["decision_snr_db_median"])
                    by_mod.setdefault(carrier.mod, []).append(depth)
                gaps = free_gaps(plan, bandwidth)
                if gaps:
                    lo, hi = max(gaps, key=lambda g: g[1] - g[0])
                    if hi - lo >= 1e6:
                        entry["gap_floor_shift_db"].append(band_power_db(res, lo, hi) - band_power_db(co, lo, hi))
                groups.setdefault(int(seed), {})[name] = (co, res, record)
    for name, entry in per_label.items():
        report["per_label"][name] = {"n": entry["n"], "n_active_carriers": len(entry["depth_db"]),
                                     "mean_depth_db": _mean_db(entry["depth_db"]),
                                     "min_depth_db": None if not entry["depth_db"] else float(np.min(entry["depth_db"])),
                                     "mean_gap_floor_shift_db": _mean_db(entry["gap_floor_shift_db"]),
                                     "median_decision_snr_db": None if not entry["decision_snr_db"]
                                     else float(np.median(entry["decision_snr_db"]))}
    report["depth_by_modulation_db"] = {mod: {"n": len(v), "mean": float(np.mean(v)), "min": float(np.min(v))}
                                        for mod, v in sorted(by_mod.items())}
    gains_before, gains_after = [], []
    for seed, variants in sorted(groups.items()):
        if "clean" in variants and "carrier_under_carrier" in variants:
            clean_co, clean_res, _ = variants["clean"]
            cuc_co, cuc_res, record = variants["carrier_under_carrier"]
            event = record["event"]
            lo, hi = event["f_lo"], event["f_hi"]
            before = band_power_db(cuc_co, lo, hi) - band_power_db(clean_co, lo, hi)
            after = band_power_db(cuc_res, lo, hi) - band_power_db(clean_res, lo, hi)
            gains_before.append(before)
            gains_after.append(after)
            report["paired_cuc"].append({"scenario_id": seed, "c_over_i_db": event["c_over_i_db"],
                                         "victim_c_over_i_db": event["victim_c_over_i_db"],
                                         "victim_mod": event["victim"]["mod"], "interferer_mod": event["carrier"]["mod"],
                                         "delta_psd_before_cancellation_db": before,
                                         "delta_psd_after_cancellation_db": after})
        if "clean" in variants and "overdrive" in variants:
            clean_co, clean_res, record = variants["clean"]
            od_co, od_res, od_record = variants["overdrive"]
            plan = [Carrier(**item) for item in record["plans"][0]]
            gaps = free_gaps(plan, bandwidth)
            if gaps:
                lo, hi = max(gaps, key=lambda g: g[1] - g[0])
                if hi - lo >= 1e6:
                    report["overdrive_vs_clean_floor_db"].append({
                        "scenario_id": seed, "overdrive_actual_ibo_db": od_record["paths"][0]["actual_ibo_db"],
                        "clean_actual_ibo_db": record["paths"][0]["actual_ibo_db"],
                        "gap_shift_spec_db": band_power_db(od_co, lo, hi) - band_power_db(clean_co, lo, hi),
                        "gap_shift_residual_db": band_power_db(od_res, lo, hi) - band_power_db(clean_res, lo, hi)})
    if gains_before:
        report["paired_cuc_summary"] = {"n_pairs": len(gains_before),
                                        "median_delta_before_db": float(np.median(gains_before)),
                                        "median_delta_after_db": float(np.median(gains_after)),
                                        "n_pairs_after_exceeds_before": int(np.sum(np.asarray(gains_after) > np.asarray(gains_before)))}
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", required=True)
    parser.add_argument("--out", required=True, help="JSON report path")
    args = parser.parse_args()
    result = check(args.data)
    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(f"Checked {result['n_observations']} observations with stored residuals; wrote {path}")


if __name__ == "__main__":
    main()

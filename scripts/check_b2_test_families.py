"""Physical checks of B2-test/1 families against their clean known twins.

python scripts/check_b2_test_families.py --known data/b2-feat-pilot --test data/b2-test-pilot \
    --out runs/b2-test-pilot/family_check.json

For every test group, each test-only variant is compared with the ``clean`` known
variant of the same group (same plans, carriers, noise, phase and activity):
mean co-pol PSD change, PSD change inside the event band (where defined), and the
same quantities on the stored cancellation residual. Event metadata is used only
as a diagnostic reference; nothing here trains or evaluates a model.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from geosim.b2_dataset import b2_fingerprint, iter_b2_shards
from geosim.b2_protocol import LABELS
from geosim.b2_test_dataset import b2_test_fingerprint, iter_b2_test_shards, read_b2_test_manifest
from geosim.cancellation import band_power_db


def _band(event):
    if "f_lo" in event and "f_hi" in event and event["f_hi"] > event["f_lo"]:
        return event["f_lo"], event["f_hi"]
    if event["kind"] in ("pulsed", "intermittent_bursts"):
        return event["f0"] - 2e5, event["f0"] + 2e5
    if event["kind"] == "wideband_noise":
        return -event["bandwidth_hz"] / 2, event["bandwidth_hz"] / 2
    return None


def check(known, test):
    manifest = read_b2_test_manifest(test)
    clean = {}
    for shard in iter_b2_shards(Path(known), "test"):
        for spec, residual, label, seed in zip(shard["spec"], shard.get("residual", [None] * len(shard["seed"])),
                                               shard["label"], shard["seed"]):
            if LABELS[int(label)] == "clean":
                clean[int(seed)] = (spec[0].astype(np.float32), None if residual is None else residual.astype(np.float32))
    rows = []
    for shard in iter_b2_test_shards(test):
        for spec, residual, index, seed, record in zip(shard["spec"], shard.get("residual", [None] * len(shard["seed"])),
                                                       shard["family"], shard["seed"], shard["meta"]):
            if int(seed) not in clean:
                raise ValueError(f"known artifact lacks the clean twin of test group {int(seed)}")
            co, co_res = clean[int(seed)]
            event = record["event"]
            family = manifest["families"][int(index)]
            own = spec[0].astype(np.float32)
            row = {"scenario_id": int(seed), "family": family, "group": record["family_group"],
                   "expected_decision": record["expected_decision"], "injection_stage": event["injection_stage"],
                   "mean_delta_psd_co_db": float(np.mean(own) - np.mean(co))}
            band = _band(event)
            if band is not None:
                row["event_band_hz"] = list(band)
                row["delta_psd_in_band_db"] = band_power_db(own, *band) - band_power_db(co, *band)
                if residual is not None and co_res is not None:
                    row["delta_residual_in_band_db"] = band_power_db(residual.astype(np.float32), *band) - band_power_db(co_res, *band)
            if family in ("pulsed", "intermittent_bursts"):
                row.update(active_c_over_i_db=event["active_c_over_i_db"],
                           observed_snapshot_occupancy=event["observed_snapshot_occupancy"])
            elif family == "adjacent_satellite_downlink":
                row.update(c_over_i_psd_db=event["c_over_i_psd_db"], overlap_fraction=event["overlap_fraction"])
            elif family == "wideband_noise":
                row.update(active_c_over_i_db=event["active_c_over_i_db"], bandwidth_hz=event["bandwidth_hz"])
            else:
                row.update(n_cids_transmitted=event["n_transmitted"],
                           relative_psd_db=[c["relative_psd_db"] for c in event["cids"]])
            if family == "adjacent_satellite_downlink":
                row["effective_c_over_i_psd_db"] = event["effective_c_over_i_psd_db"]
            rows.append(row)
    per_family = {}
    for family in manifest["families"]:
        selected = [row for row in rows if row["family"] == family]
        in_band = [row["delta_psd_in_band_db"] for row in selected if "delta_psd_in_band_db" in row]
        in_res = [row["delta_residual_in_band_db"] for row in selected if "delta_residual_in_band_db" in row]
        per_family[family] = {"n": len(selected),
                              "median_delta_psd_in_band_db": None if not in_band else float(np.median(in_band)),
                              "median_delta_residual_in_band_db": None if not in_res else float(np.median(in_res)),
                              "mean_delta_psd_co_db": float(np.mean([row["mean_delta_psd_co_db"] for row in selected]))}
    return {"protocol": manifest["protocol"], "benchmark_complete": manifest["benchmark_complete"],
            "test_fingerprint": b2_test_fingerprint(test), "known_fingerprint": b2_fingerprint(known),
            "n_observations": len(rows), "per_family": per_family, "rows": rows, "recognition_metrics": None,
            "scope": "Physics of test-only families against clean twins; no classifier claim."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--known", required=True)
    parser.add_argument("--test", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    result = check(args.known, args.test)
    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(f"Checked {result['n_observations']} test-only observations; wrote {path}")


if __name__ == "__main__":
    main()

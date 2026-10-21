"""Verify completed observed-receiver data and replay both trained B2 views.

python scripts/check_b2_features.py --data data/b2-features-pilot \
    --run runs/b2-observed-pilot --out docs/results/b2_observed_pilot.json

This produces a small report; raw IQ, shards and checkpoints stay outside Git.
Total received-power reduction is a receiver diagnostic, not recognition gain.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import time

import numpy as np

from geosim.b2_features import feature_fingerprint, generate_b2_features, iter_feature_shards, read_feature_manifest
from geosim.b2_protocol import B2Config, LABELS
from geosim.observed_receiver import CancellationConfig
from geosim.dataset import _generator_provenance
from geosim.event_dataset import _strict_json
from geoml.b2_observed_experiment import B2ExperimentConfig, run_b2_experiment
from geoml.experiment import _source_identity, _write_json


def _timing(path):
    return _strict_json(path.read_text()) if path.exists() else None


def check(data, run):
    data, run = Path(data), Path(run)
    manifest = read_feature_manifest(data)
    previous = _strict_json((run / "results.json").read_text())
    predictions = _strict_json((run / "predictions.json").read_text())
    if manifest["request"]["source_sha256"] != _generator_provenance():
        raise ValueError("replay requires the original, unchanged feature-generator source")
    if (previous["data_fingerprint"] != feature_fingerprint(data)
            or previous["source"]["files_sha256"] != _source_identity()["files_sha256"]):
        raise ValueError("experiment does not match the feature artifact/current model source")
    request = manifest["request"]
    started = time.perf_counter()
    generate_b2_features(data, B2Config(**manifest["config"]),
                         cancellation_config=CancellationConfig(**manifest["cancellation"]["config"]),
                         roles=request["roles"], limit_groups=request["limit_groups"],
                         groups_per_shard=request["groups_per_shard"])
    replayed = run_b2_experiment(B2ExperimentConfig.from_file(run / "config.json"), data, run, reuse=True)
    if (replayed["methods"] != previous["methods"]
            or _strict_json((run / "predictions.json").read_text()) != predictions):
        raise AssertionError("model/threshold reload changed predictions or evaluation")
    replay_seconds = time.perf_counter() - started
    rows = {label: [] for label in LABELS}
    missing_scenarios = {}
    missing, n_samples, n_groups = 0, 0, 0
    for role, info in manifest["roles"].items():
        n_samples += info["n_samples"]
        n_groups += info["n_scenarios"]
        for shard in iter_feature_shards(data, role):
            missing += int(shard["plan_consistency"].sum())
            for label, record in zip(shard["label"], shard["meta"]):
                if record["plan_consistency"] == 1:
                    item = missing_scenarios.setdefault(record["scenario_id"], {
                        "scenario_id": record["scenario_id"], "role": role,
                        "dropped_carrier": record["dropped_carrier"], "n_observations": 0})
                    item["n_observations"] += 1
                diagnostics = record["cancellation"]["diagnostics"]
                before, after = diagnostics["input_power"], diagnostics["residual_power"]
                reduction = 10 * np.log10(before / after) if before > 0 and after > 0 else None
                rows[LABELS[int(label)]].append({
                    "total_power_reduction_db": float(reduction) if reduction is not None else None,
                    "accepted_carrier_windows": sum(item["accepted_windows"] for item in diagnostics["carriers"]),
                    "declared_carrier_windows": sum(item["n_windows"] for item in diagnostics["carriers"])})
    diagnostics = {}
    for label, values in rows.items():
        reduction = [row["total_power_reduction_db"] for row in values if row["total_power_reduction_db"] is not None]
        diagnostics[label] = {
            "n_observations": len(values), "n_finite_reductions": len(reduction),
            "total_power_reduction_db": {
                "median": float(np.median(reduction)) if reduction else None,
                "min": min(reduction) if reduction else None, "max": max(reduction) if reduction else None},
            "accepted_carrier_windows": sum(row["accepted_carrier_windows"] for row in values),
            "declared_carrier_windows": sum(row["declared_carrier_windows"] for row in values)}
    return {"protocol": manifest["protocol"], "parent_protocol": manifest["parent_protocol"],
            "benchmark_complete": False, "n_observations": n_samples, "n_scenario_groups": n_groups,
            "n_missing_carrier_observations": missing,
            "missing_scenarios": list(missing_scenarios.values()),
            "request_fingerprint": manifest["request_fingerprint"],
            "artifact_bytes": sum(path.stat().st_size for path in data.rglob("*") if path.is_file()),
            "integrity": {"generator_source_matches_current": True, "generation_resume_verified": True,
                          "checkpoint_detector_reload_identical": True, "replay_seconds": replay_seconds},
            "generation_timing": _timing(run / "generation_time.json"),
            "training_timing": _timing(run / "training_time.json"),
            "receiver_diagnostics": diagnostics,
            "receiver_diagnostic_scope": "Observed total received-power reduction across roles; not symbol-error, interference-preservation or recognition gain. No settings were selected from these diagnostics.",
            "experiment": replayed}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data", required=True)
    parser.add_argument("--run", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    result = check(args.data, args.run)
    _write_json(Path(args.out), result)
    print(f"verified {result['n_observations']} observations, generation resume and model/detector replay")


if __name__ == "__main__":
    main()

"""Bounded cost profile of a B2 artifact generator (measured, not extrapolated).

python scripts/profile_b2_generation.py --stage matched --known data/b2-feat-pilot --groups 20 \
    --out-data data/b2-match-profile --cancellation configs/cancellation.json \
    --report runs/profile/matched_20.json

Wraps one generation run and records wall/CPU time, peak resident memory, artifact
bytes and the time spent inside the simulator, the canceller and shard writing
(monkeypatched timers around ``simulate_dual``, ``cancel_planned_carriers`` and
``numpy.savez``), the startup/calibration time before the first observation, and
the cost of the subsequent resume validation. Hardware, thread counts, commit and
fingerprints are recorded. The report is a pilot measurement for the requested
group count; it does not launch full production.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import resource
import subprocess
import time
from pathlib import Path

import numpy as np

from geosim import b2_dataset, b2_matched_dataset, b2_scenarios, b2_test_dataset
from geosim.b2_protocol import B2Config
from geosim.cancellation import CancellationConfig
from geosim.event_dataset import _strict_json

STAGES = {"known": b2_dataset, "test": b2_test_dataset, "matched": b2_matched_dataset}


class _Timer:
    def __init__(self):
        self.calls, self.seconds = 0, 0.0

    def wrap(self, function):
        def wrapped(*args, **kwargs):
            started = time.perf_counter()
            try:
                return function(*args, **kwargs)
            finally:
                self.seconds += time.perf_counter() - started
                self.calls += 1
        return wrapped


def _du(path):
    return sum(p.stat().st_size for p in Path(path).rglob("*") if p.is_file())


def _commit():
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    except Exception:  # pragma: no cover
        return None


def profile(stage, out_data, known, config, cancellation, groups, groups_per_shard, roles=None):
    module = STAGES[stage]
    simulate, cancel, savez = _Timer(), _Timer(), _Timer()
    original_simulate, original_cancel, original_savez = b2_scenarios.simulate_dual, b2_dataset.cancel_planned_carriers, np.savez
    first_observation = {"t": None}

    def timed_simulate(*args, **kwargs):
        if first_observation["t"] is None:
            first_observation["t"] = time.perf_counter()
        return simulate.wrap(original_simulate)(*args, **kwargs)

    b2_scenarios.simulate_dual = timed_simulate
    b2_dataset.cancel_planned_carriers = cancel.wrap(original_cancel)
    np.savez = savez.wrap(original_savez)
    started_wall, started_cpu = time.perf_counter(), time.process_time()
    try:
        if stage == "known":
            module.generate_b2_dataset(out_data, config, roles=roles or ("train",), limit_groups=groups,
                                       groups_per_shard=groups_per_shard, cancellation=cancellation)
        elif stage == "test":
            module.generate_b2_test_dataset(out_data, known, config, limit_groups=groups,
                                            groups_per_shard=groups_per_shard, cancellation=cancellation)
        else:
            module.generate_b2_matched_dataset(out_data, known, config, limit_groups=groups,
                                               groups_per_shard=groups_per_shard, cancellation=cancellation)
    finally:
        b2_scenarios.simulate_dual, b2_dataset.cancel_planned_carriers, np.savez = original_simulate, original_cancel, original_savez
    wall, cpu = time.perf_counter() - started_wall, time.process_time() - started_cpu
    peak_rss_mib = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    startup = None if first_observation["t"] is None else first_observation["t"] - started_wall
    resume_started = time.perf_counter()
    if stage == "known":
        manifest = module.read_b2_manifest(out_data)
        n_samples = sum(info["n_samples"] for info in manifest["roles"].values())
        fingerprint = module.b2_fingerprint(out_data)
    elif stage == "test":
        manifest = module.read_b2_test_manifest(out_data)
        n_samples, fingerprint = manifest["n_samples"], module.b2_test_fingerprint(out_data)
    else:
        manifest = module.read_b2_matched_manifest(out_data)
        n_samples, fingerprint = manifest["n_samples"], module.b2_matched_fingerprint(out_data)
    resume_seconds = time.perf_counter() - resume_started
    artifact_bytes = _du(out_data)
    per_observation = None if simulate.calls == 0 else {
        "wall_s": (wall - (startup or 0.0)) / simulate.calls,
        "simulate_s": simulate.seconds / simulate.calls,
        "cancellation_s": None if cancel.calls == 0 else cancel.seconds / cancel.calls,
        "shard_write_s_per_observation": savez.seconds / simulate.calls}
    return {"stage": stage, "protocol": manifest["protocol"], "groups": groups, "groups_per_shard": groups_per_shard,
            "n_observations_generated": simulate.calls, "n_samples_in_artifact": n_samples,
            "resumed_without_generation": simulate.calls == 0,
            "wall_s": wall, "cpu_s": cpu, "startup_and_calibration_s": startup, "peak_rss_mib": peak_rss_mib,
            "simulate_total_s": simulate.seconds, "cancellation_total_s": cancel.seconds, "cancellation_calls": cancel.calls,
            "shard_write_total_s": savez.seconds, "shard_writes": savez.calls,
            "resume_validation_s": resume_seconds, "artifact_bytes": artifact_bytes,
            "bytes_per_observation": None if n_samples == 0 else artifact_bytes / n_samples,
            "per_observation": per_observation, "data_fingerprint": fingerprint,
            "request_fingerprint": manifest["request_fingerprint"], "cancellation": manifest.get("cancellation"),
            "hardware": {"cpu_count": os.cpu_count(), "platform": platform.platform(), "python": platform.python_version(),
                         "numpy": np.__version__, "omp_threads": os.environ.get("OMP_NUM_THREADS"),
                         "openblas_threads": os.environ.get("OPENBLAS_NUM_THREADS")},
            "commit": _commit(), "measured": True,
            "note": "single-process pilot measurement; concurrent load on the machine inflates wall time"}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--stage", choices=sorted(STAGES), required=True)
    parser.add_argument("--out-data", required=True)
    parser.add_argument("--known", help="known artifact for the test/matched stages")
    parser.add_argument("--config")
    parser.add_argument("--cancellation")
    parser.add_argument("--groups", type=int, required=True)
    parser.add_argument("--groups-per-shard", type=int, default=4)
    parser.add_argument("--roles", nargs="+", help="known stage only")
    parser.add_argument("--report", required=True)
    args = parser.parse_args()
    config = B2Config.from_file(args.config) if args.config else B2Config()
    cancellation = None
    if args.cancellation:
        cancellation = CancellationConfig(**_strict_json(Path(args.cancellation).read_text()))
    if args.stage != "known" and not args.known:
        parser.error("--known is required for the test and matched stages")
    report = profile(args.stage, args.out_data, args.known, config, cancellation, args.groups, args.groups_per_shard,
                     tuple(args.roles) if args.roles else None)
    path = Path(args.report)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(json.dumps({k: report[k] for k in ("stage", "n_observations_generated", "wall_s", "cpu_s", "peak_rss_mib",
                                             "artifact_bytes", "per_observation")}, indent=1))


if __name__ == "__main__":
    main()

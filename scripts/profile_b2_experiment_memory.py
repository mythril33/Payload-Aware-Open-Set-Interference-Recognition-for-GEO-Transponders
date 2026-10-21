"""Measured memory and throughput of the legacy in-memory B2 path versus the E1 streaming path.

python scripts/profile_b2_experiment_memory.py --data data/b2-feat-pilot --report runs/profile/e1_pilot.json
python scripts/profile_b2_experiment_memory.py --synthetic-groups 48 --fixture-dir data/e1-synthetic-48 \
    --window-shards 1 4 --report runs/profile/e1_synthetic_48.json

Each mode runs in a fresh subprocess so peak resident memory (``ru_maxrss``) is
not polluted by the other mode. ``legacy`` reproduces the pre-E1 data flow of
``geoml.b2_experiment`` (``load_b2_split`` of the roles, ``geoml.train.fit`` on
whole tensors, ``geoml.train.infer``); ``streaming`` uses ``geoml.b2_stream``
(``open_b2_known`` verification pass, ``fit_streaming``, ``infer_streaming``).
Both train the same configuration on the same artifact; the parity of their
outputs is checked here as well (identical weights when the data fit in one
window, otherwise declared as "same algorithm, different sample order").

``--synthetic-groups`` builds a *layout* fixture with the real artifact writer
and validator but a stand-in simulator (random spectra, fake canceller): it has
the exact shard/array layout and sizes of B2-feat/1 and no physics, so it
measures memory and I/O, never recognition. Nothing here launches production.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import resource
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent


def _du(path):
    return sum(p.stat().st_size for p in Path(path).rglob("*") if p.is_file())


def _shard_bytes(root, role):
    return [p.stat().st_size for p in sorted((Path(root) / role).glob("part-*.npz"))]


def build_synthetic_fixture(root, groups, groups_per_shard, roles=("train", "val-select", "val-calib", "test"),
                            small_roles_groups=2):
    """B2-feat/1 layout fixture: real writer/validator, stand-in physics. Not a dataset for science."""
    from types import SimpleNamespace as NS
    from dataclasses import asdict
    from geosim import b2_dataset as ds
    from geosim import b2_scenarios as scenes
    from geosim.b2_protocol import B2Config
    from geosim.cancellation import CancellationConfig
    from geosim.plan import plan_mask_db
    from geosim.event_dataset import _strict_json

    cancellation = CancellationConfig(**_strict_json((ROOT / "configs" / "cancellation.json").read_text()))
    calls = {"n": 0}

    def simulate(cfg, *, plans, interferers, active_carriers, calibration, keep_iq):
        rng = np.random.default_rng([int(cfg.co.seed), calls["n"]])
        calls["n"] += 1
        power = [sum(c.power for c, keep in zip(plan, active) if keep) for plan, active in zip(plans, active_carriers)]
        iq = None
        if keep_iq:
            iq = (rng.standard_normal((2, 128, 4096)) + 1j * rng.standard_normal((2, 128, 4096))).astype(np.complex64)
        return NS(spec_db=rng.normal(-80, 2, (2, 128, 512)).astype(np.float32),
                  mask_db=np.stack([plan_mask_db(plan) for plan in plans]), iq=iq,
                  meta={"config": cfg.to_dict(), "plans": [[asdict(c) for c in plan] for plan in plans],
                        "has_interferer": [event is not None for event in interferers],
                        "has_downlink_interferer": [False, False],
                        "active_carriers": [list(active) for active in active_carriers],
                        "active_planned_power": power, "nominal_planned_power": [1., 1.],
                        "gain_mode": "fixed_nominal_planned_power",
                        "paths": [{"actual_ibo_db": cfg.co.ibo_db, "obo_db": 10., "omux_output_power": 0.1,
                                   "receiver_noise_psd": 1e-10, "zero_drive": False} for _ in range(2)],
                        "receiver_calibration_applied": True, "receiver_calibration": calibration.to_dict()})

    def cancel(iq, plan, config=None):
        rng = np.random.default_rng(int(np.abs(iq[0, 0].real) * 1e6) % 1000)
        return NS(residual_iq=iq, residual_db=rng.normal(-95, 1, (128, 512)).astype(np.float32),
                  carriers=[{"plan_index": i, "f0": c.f0, "symbol_rate": c.symbol_rate, "mod": c.mod,
                             "samples_per_symbol": 60, "symbols_per_snapshot": 200, "timing_samples": [0] * 128,
                             "gain_power_db_mean": 0.0, "decision_snr_db_median": 20.0,
                             "basis": "observed IQ and operator plan only"} for i, c in enumerate(plan)],
                  config=config)

    original = scenes.simulate_dual, ds.cancel_planned_carriers, ds._generator_provenance
    scenes.simulate_dual, ds.cancel_planned_carriers = simulate, cancel
    ds._generator_provenance = lambda: {"synthetic_layout_fixture": "0" * 64}
    try:
        # One request per artifact: the training role gets ``groups`` groups, the other roles a small prefix.
        # geosim requires one limit for all roles in a request, so the fixture holds two artifacts' worth of
        # roles in one directory only when the limits agree; here we keep one directory with the large limit
        # for train and generate the evaluation roles with the same limit (they are small in bytes anyway).
        ds.generate_b2_dataset(root, B2Config(), roles=roles, limit_groups=groups, groups_per_shard=groups_per_shard,
                               cancellation=cancellation)
    finally:
        scenes.simulate_dual, ds.cancel_planned_carriers, ds._generator_provenance = original
    return root


_CHILD = r"""
import json, resource, sys, time
sys.path.insert(0, %(src)r)
import numpy as np, torch
from geoml.train import TrainConfig
from geosim.b2_protocol import LABELS
args = json.loads(sys.argv[1])
cfg = TrainConfig(labels=LABELS, **args["training"])
def status(key):
    try:
        for line in open("/proc/self/status"):
            if line.startswith(key):
                return int(line.split()[1]) / 1024
    except OSError:
        return None
report = {"mode": args["mode"], "window_shards": args.get("window_shards"),
          "imports_rss_mib": status("VmRSS"), "imports_lifetime_peak_mib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024}
try:
    open("/proc/self/clear_refs", "w").write("5")        # Linux: reset the peak-RSS high-water mark after the imports
    report["peak_reset_after_imports"] = True
except OSError:
    report["peak_reset_after_imports"] = False
t0 = time.perf_counter()
if args["mode"] == "legacy":
    from geoml import train
    from geosim.b2_dataset import load_b2_split, b2_fingerprint
    identity = b2_fingerprint(args["data"]); report["verify_s"] = time.perf_counter() - t0
    t = time.perf_counter(); parts = {role: load_b2_split(args["data"], role) for role in ("train", "val-select", "val-calib", "test")}
    report["load_s"] = time.perf_counter() - t
    report["after_load_rss_mib"] = status("VmRSS")
    t = time.perf_counter(); fitted = train.fit(parts["train"], parts["val-select"], cfg, device="cpu", log=lambda *_: None)
    report["fit_s"] = time.perf_counter() - t
    t = time.perf_counter(); out = train.infer(fitted, parts["train"]); report["infer_train_s"] = time.perf_counter() - t
    n_train = len(parts["train"]["label"])
else:
    from geoml.b2_stream import open_b2_known, fit_streaming, infer_streaming
    _, identity, sources = open_b2_known(args["data"]); report["verify_s"] = time.perf_counter() - t0
    report["load_s"] = 0.0
    report["after_load_rss_mib"] = status("VmRSS")
    t = time.perf_counter(); fitted = fit_streaming(sources["train"], sources["val-select"], cfg, window_shards=args["window_shards"], device="cpu", log=lambda *_: None)
    report["fit_s"] = time.perf_counter() - t
    t = time.perf_counter(); out = infer_streaming(fitted, sources["train"]); report["infer_train_s"] = time.perf_counter() - t
    n_train = len(sources["train"])
report.update(n_train=n_train, data_fingerprint=identity, total_s=time.perf_counter() - t0,
              peak_rss_mib=status("VmHWM") if report["peak_reset_after_imports"] else resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024,
              peak_rss_increment_mib=(status("VmHWM") - report["imports_rss_mib"]) if report["peak_reset_after_imports"] else None,
              lifetime_peak_rss_mib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024,
              history=fitted["history"], absolute_ref_db=fitted["absolute_ref_db"],
              state_sha256=__import__("hashlib").sha256(b"".join(v.detach().cpu().numpy().tobytes() for v in fitted["model"].state_dict().values())).hexdigest(),
              train_logits_sha256=__import__("hashlib").sha256(np.ascontiguousarray(out["logits"]).tobytes()).hexdigest(),
              fit_obs_per_s=n_train * cfg.epochs / report["fit_s"], infer_obs_per_s=n_train / report["infer_train_s"])
json.dump(report, open(args["out"], "w"), indent=1, allow_nan=False)
"""


def run_mode(mode, data, training, window_shards, out):
    env = {**os.environ, "OMP_NUM_THREADS": os.environ.get("OMP_NUM_THREADS", "2"), "MPLBACKEND": "Agg"}
    args = {"mode": mode, "data": str(data), "training": training, "window_shards": window_shards, "out": str(out)}
    completed = subprocess.run([sys.executable, "-c", _CHILD % {"src": str(ROOT / "src")}, json.dumps(args)],
                               env=env, cwd=ROOT, capture_output=True, text=True)
    if completed.returncode:
        raise RuntimeError(completed.stderr[-4000:])
    return json.loads(Path(out).read_text())


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data", help="existing B2-base/1 or B2-feat/1 artifact")
    parser.add_argument("--synthetic-groups", type=int, help="build a synthetic-layout B2-feat/1 fixture with this many groups per role")
    parser.add_argument("--fixture-dir", help="directory of the synthetic fixture (outside Git)")
    parser.add_argument("--groups-per-shard", type=int, default=8)
    parser.add_argument("--window-shards", type=int, nargs="+", default=[1, 4])
    parser.add_argument("--epochs", type=int, default=1)
    parser.add_argument("--batch", type=int, default=8)
    parser.add_argument("--width", type=int, default=8)
    parser.add_argument("--skip-legacy", action="store_true")
    parser.add_argument("--report", required=True)
    args = parser.parse_args()
    training = {"input_mode": "dual_residual", "plan_consistency": True, "center_loss_weight": 0.005,
                "plan_shift_fraction": 0.15, "plan_shift_max_hz": 0.5e6, "epochs": args.epochs, "batch": args.batch,
                "width": args.width, "seed": 0, "augment": True}
    if args.synthetic_groups:
        if not args.fixture_dir:
            parser.error("--fixture-dir is required with --synthetic-groups")
        data = Path(args.fixture_dir)
        sys.path.insert(0, str(ROOT / "src"))
        started = time.perf_counter()
        build_synthetic_fixture(data, args.synthetic_groups, args.groups_per_shard)
        fixture_note = {"kind": "synthetic_layout_fixture", "groups_per_role": args.synthetic_groups,
                        "groups_per_shard": args.groups_per_shard, "build_s": time.perf_counter() - started,
                        "physics": "none (random spectra, fake canceller); layout, sizes and validation are the real B2-feat/1"}
    else:
        if not args.data:
            parser.error("--data or --synthetic-groups is required")
        data, fixture_note = Path(args.data), {"kind": "real_artifact"}
    manifest = json.loads((data / "manifest.json").read_text())
    dataset = {"protocol": manifest["protocol"], "roles": {role: {"n_samples": info["n_samples"], "n_shards": len(info["shards"]),
                                                                 "shard_bytes": _shard_bytes(data, role)}
                                                          for role, info in manifest["roles"].items()},
               "artifact_bytes": _du(data)}
    n_train = dataset["roles"]["train"]["n_samples"]
    per_obs = {"raw_float16_bytes": 2 * (2 * 128 * 512 + 2 * 512 + 128 * 512),
               "preprocessed_float32_bytes": 5 * 64 * 512 * 4}
    report_dir = Path(args.report).parent
    report_dir.mkdir(parents=True, exist_ok=True)
    runs = []
    if not args.skip_legacy:
        runs.append(run_mode("legacy", data, training, None, report_dir / "child_legacy.json"))
    for window in args.window_shards:
        runs.append(run_mode("streaming", data, training, int(window), report_dir / f"child_streaming_{window}.json"))
    legacy = next((run for run in runs if run["mode"] == "legacy"), None)
    for run in runs:
        if legacy is not None and run["mode"] == "streaming":
            run["identical_weights_to_legacy"] = run["state_sha256"] == legacy["state_sha256"]
            run["identical_history_to_legacy"] = run["history"] == legacy["history"]
            run["single_window"] = run["window_shards"] >= dataset["roles"]["train"]["n_shards"]
    report = {"measured": True, "fixture": fixture_note, "dataset": dataset, "training": training,
              "bytes_per_observation": per_obs,
              "legacy_resident_estimate_mib": {
                  "note": "pre-E1 flow: every role float16 in memory plus float32 inputs of train and val-select",
                  "train_float16_mib": n_train * per_obs["raw_float16_bytes"] / 2**20,
                  "train_preprocessed_mib": n_train * per_obs["preprocessed_float32_bytes"] / 2**20},
              "streaming_resident_bound_mib": {
                  window: {"note": "window_shards raw shards (float16) + their float32 inputs + one gathered window copy during permutation",
                           "bound_mib": (max(dataset["roles"]["train"]["shard_bytes"]) * window * (1 + 2 * per_obs["preprocessed_float32_bytes"] / per_obs["raw_float16_bytes"])) / 2**20}
                  for window in args.window_shards},
              "runs": runs,
              "hardware": {"cpu_count": os.cpu_count(), "platform": platform.platform(), "python": platform.python_version(),
                           "numpy": np.__version__, "omp_threads": os.environ.get("OMP_NUM_THREADS")},
              "scope": "bounded fixture measurement; peak RSS includes the Python/torch import baseline; no production run"}
    Path(args.report).write_text(json.dumps(report, indent=1, allow_nan=False) + "\n")
    for run in runs:
        print(f"{run['mode']:9s} window={run.get('window_shards')} peak {run['peak_rss_mib']:.0f} MiB "
              f"(imports {run['imports_rss_mib']:.0f}, increment {run['peak_rss_increment_mib']}) verify {run['verify_s']:.1f}s fit {run['fit_s']:.1f}s "
              f"infer {run['infer_obs_per_s']:.1f} obs/s identical_weights={run.get('identical_weights_to_legacy')}")


if __name__ == "__main__":
    main()

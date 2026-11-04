"""Fixed CPU B1-dev/2 campaign; leaves the canonical B2 experiment untouched."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, data):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def stop_process_tree(process, log):
    """Stop child generators too, including on a user's Ctrl-C."""
    if os.name == "posix":
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    else:
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                       stdout=log, stderr=subprocess.STDOUT, check=False)
    process.wait()


def prepare(out, resume=False):
    from geoml.experiment import ExperimentConfig, _source_identity

    out = Path(out).resolve()
    if out == ROOT or ROOT in out.parents:
        raise ValueError("generated data/models must stay outside the repository")
    config_path = ROOT / "configs/cpu_delivery.json"
    cfg = json.loads(config_path.read_text())
    # This fixed delivery recipe is bounded even if a configuration is mistyped.
    if (cfg["training_seeds"] != [0, 1, 2]
            or not 2 <= cfg["groups_per_source_split"] <= 40
            or not 1 <= cfg["unknown_groups"] <= 40
            or cfg["training"]["epochs"] > 10 or cfg["training"]["width"] > 8):
        raise ValueError("campaign exceeds the preregistered CPU budget")
    configs = [ExperimentConfig(
        protocol=cfg["experiment_protocol"], holdout_label=cfg["holdout_label"],
        calibration_fraction=cfg["calibration_fraction"], split_seed=cfg["split_seed"],
        target_acceptance=cfg["target_acceptance"], methods=cfg["methods"],
        mahalanobis_regularization=cfg["mahalanobis_regularization"],
        training={**cfg["training"], "seed": seed}).resolved()
        for seed in cfg["training_seeds"]]
    configs = json.loads(json.dumps(configs, allow_nan=False))
    source = _source_identity()
    record = {"campaign": cfg["campaign"], "config": cfg,
              "config_sha256": digest(config_path), "runner_sha256": digest(__file__),
              "summary_code_sha256": digest(Path(__file__).with_name("summarize.py")),
              "preregistration_sha256": digest(Path(__file__).with_name("PREREGISTRATION.md")),
              "scientific_sources_sha256": source["files_sha256"],
              "resolved_fits": configs, "device": "cpu", "benchmark_complete": False}
    if out.exists():
        if not resume:
            raise ValueError("output already exists; use --resume for identical artifacts")
        if json.loads((out / "campaign.json").read_text()) != record:
            raise ValueError("campaign configuration or source changed; use a fresh output")
        for seed, fit in zip(cfg["training_seeds"], configs):
            if json.loads((out / f"config-{seed}.json").read_text()) != fit:
                raise ValueError("resolved fit configuration changed")
    else:
        if resume:
            raise ValueError("cannot resume an absent campaign")
        out.parent.mkdir(parents=True, exist_ok=True)
        if shutil.disk_usage(out.parent).free < 2**30:
            raise ValueError("at least 1 GiB free disk is required")
        out.mkdir()
        write_json(out / "campaign.json", record)
        for seed, fit in zip(cfg["training_seeds"], configs):
            write_json(out / f"config-{seed}.json", fit)
    return cfg, out


def run(out, resume=False):
    cfg, out = prepare(out, resume)
    env = dict(os.environ)
    env.update(OMP_NUM_THREADS="2", OPENBLAS_NUM_THREADS="2", MKL_NUM_THREADS="2",
               PYTHONHASHSEED="0", CUDA_VISIBLE_DEVICES="", MPLBACKEND="Agg")
    env["PYTHONPATH"] = str(ROOT / "src")
    steps = [
        ("known-generation", ["-m", "geosim.dataset", "--out", str(out / "known"),
          "--splits", "train_nl", "val_nl", "test_id_nl", "--limit-seeds",
          str(cfg["groups_per_source_split"]), "--workers", "1"], 2700),
        ("unknown-generation", ["-m", "geosim.unknowns", "--out", str(out / "unknown"),
          "--n-seeds", str(cfg["unknown_groups"]), "--first-seed",
          str(cfg["unknown_first_seed"])], 2700)]
    for seed in cfg["training_seeds"]:
        args = ["-m", "geoml.experiment", "--config", str(out / f"config-{seed}.json"),
                "--data", str(out / "known"), "--unknown-data", str(out / "unknown"),
                "--out", str(out / f"seed-{seed}"), "--device", "cpu"]
        if resume:
            args.append("--reuse")
        steps.append((f"seed-{seed}", args, 1800))
    for name, args, timeout in steps:
        print(f"Starting {name}; log: {out / (name + '.log')}", flush=True)
        start = time.monotonic()
        with (out / f"{name}.log").open("a") as log:
            process = None
            try:
                process = subprocess.Popen([sys.executable, *args], cwd=ROOT, env=env,
                                           stdout=log, stderr=subprocess.STDOUT,
                                           start_new_session=(os.name == "posix"))
                status = {"returncode": process.wait(timeout=timeout), "timed_out": False}
            except subprocess.TimeoutExpired:
                stop_process_tree(process, log)
                status = {"returncode": None, "timed_out": True}
            except BaseException:
                if process is not None:
                    stop_process_tree(process, log)
                raise
        status.update(step=name, elapsed_s=time.monotonic() - start,
                      command=[sys.executable, *args], resume=resume)
        with (out / "execution.jsonl").open("a") as ledger:
            ledger.write(json.dumps(status, allow_nan=False) + "\n")
        if status["returncode"] != 0:
            raise RuntimeError(f"{name} failed/timed out; inspect its log; campaign incomplete")
        print(f"Completed {name} in {status['elapsed_s']:.1f}s", flush=True)
    # Keep result aggregation separate from model/threshold selection.
    from research.cpu_delivery.summarize import summarize
    summarize(out)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    run(args.out, args.resume)

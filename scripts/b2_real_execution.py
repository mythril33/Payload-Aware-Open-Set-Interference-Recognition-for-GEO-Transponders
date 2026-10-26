"""Bounded real RF -> train -> validation -> calibrate -> freeze exercise.

Only three development roles and CPU kernels are reachable from this command.
It grants no production, GPU or protected evaluation authority.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from b2_real_generation import run_development, _copy_verified, _publish_json
from b2_production_preflight import _file_hash
from b2_e16_ledger import Ledger, verify_chain
from b2_e18_lifecycle import AnchorStore
from b2_production_supervisor import utc_now
from geoml.b2_experiment import B2ExperimentConfig
from geoml.b2_production_training import development_train_calibrate_freeze


def exercise(root, *, groups=1):
    root = Path(root).absolute()
    # The roots are distinct, but this development exercise makes no independent
    # device or disaster-recovery claim for these local directories.
    generation = run_development(root / "work", root / "backup", root / "journal", root / "anchors", groups=groups)
    config = B2ExperimentConfig(views=("dual_residual",), training={
        "epochs": 2, "batch": 8, "width": 2, "time_pool": 2, "seed": 0,
        "center_loss_weight": .005, "plan_loss_weight": 1.,
        "plan_shift_fraction": .15, "plan_shift_max_hz": .5e6,
        "augment": True, "lr": .001, "weight_decay": .0001})
    trained = development_train_calibrate_freeze(config, generation["data_root"], root / "models",
                                                root / "freeze.json", log=lambda *args: None)
    model_names = sorted(path.name for path in (root / "models").iterdir())
    _copy_verified(root / "models", root / "backup" / "models", model_names)
    _copy_verified(root, root / "backup", ["freeze.json"])
    model_hashes = {name: _file_hash(root / "models" / name) for name in model_names}
    if model_hashes != {name: _file_hash(root / "backup" / "models" / name) for name in model_names}:
        raise ValueError("model backup reverification failed")
    freeze_hash = _file_hash(root / "freeze.json")
    if freeze_hash != _file_hash(root / "backup" / "freeze.json"):
        raise ValueError("freeze backup reverification failed")
    ledger, anchors = Ledger(root / "journal"), AnchorStore(root / "anchors")
    if not verify_chain(ledger.read(), expected_head=anchors.latest())["ok"]:
        raise ValueError("generation journal changed before model backup acceptance")
    entry = ledger.append("boundary_check", "known", {
        "scope": "BOUNDED_DEVELOPMENT", "phase": "model_freeze_backup",
        "freeze_sha256": freeze_hash, "model_files_sha256": model_hashes,
        "independent_backup_verified": False}, utc_now(), expected_head=anchors.latest())
    anchors.record({"seq": entry["seq"], "entry_sha256": entry["entry_sha256"]})
    report = {"schema": "B2-real-kernel-exercise/1", "scope": "BOUNDED_DEVELOPMENT",
              "generation": generation, "training": trained["training"],
              "execution_adapter_sha256": _file_hash(Path(__file__)),
              "journal_head": anchors.latest(),
              "calibration": trained["calibration"], "freeze": trained["inventory"],
              "model_backup_sha256": model_hashes, "model_backup_reverified": True,
              "independent_backup_verified": False, "heldout_reads": 0,
              "gpu_exercised": False, "production_authorized": False, "benchmark_complete": False}
    _publish_json(root, "exercise.json", report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, help="fresh directory outside the repository")
    parser.add_argument("--groups", type=int, choices=(1, 2), default=1)
    args = parser.parse_args(argv)
    repo = Path(__file__).resolve().parents[1]
    out = Path(args.out).absolute()
    if out == repo or repo in out.parents:
        parser.error("generated artifacts must be outside the repository")
    if out.exists():
        parser.error("a fresh exercise directory is required")
    report = exercise(out, groups=args.groups)
    print(json.dumps(report, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()

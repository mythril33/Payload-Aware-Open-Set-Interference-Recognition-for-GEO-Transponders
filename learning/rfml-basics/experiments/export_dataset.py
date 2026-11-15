"""Export the synthetic data of one seed as files (the data are otherwise generated on the fly).

Writes, under --out, one compressed .npz per role of the open-set stage (and of
the closed-set stage with --closed-set), plus a manifest with shapes, counts
and SHA-256 sums.
The arrays are exactly what the campaigns train and test on for that seed
(same role streams), so the export can be checked against a rerun.

Each open-set .npz holds:
    iq       float32 (N, 2, 512)   row 0 in-phase, row 1 quadrature
    label    int64   (N,)          index into `classes`, or -1 for outlier / unknown frames
    tx_id    int64   (N,)          device index within the role
    snr_db   float32 (N,)
    classes  str                   the known class names (label index order)
    class_name str   (N,)          the true modulation of every frame

Usage:  .venv/bin/python experiments/export_dataset.py --seed 0 --out experiments/dataset_seed0
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np

from rfml import experiments as ex

# Role -> (class tuple of its devices, devices per class): build_frames groups devices by class in order.
OPEN_SET_ROLES = {
    "train_known": (ex.KNOWN, "tx_train"),
    "train_aux": (ex.AUX, "tx_aux"),
    "test_known": (ex.KNOWN, "tx_test"),
    "test_unknown": (ex.UNKNOWN, "tx_unknown"),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--scale", default="full", choices=sorted(ex.SCALES))
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--closed-set", action="store_true",
                    help="also export the closed-set (campaign 1 modulation) data; roughly triples the size")
    args = ap.parse_args()

    scale = ex.get_scale(args.scale)
    args.out.mkdir(parents=True, exist_ok=True)
    manifest: dict = {
        "seed": args.seed,
        "scale": ex._scale_dict(scale),
        "known_classes": list(ex.KNOWN),
        "unknown_classes_test_only": list(ex.UNKNOWN),
        "aux_outlier_classes_train_only": list(ex.AUX),
        "n_samples": ex.N_SAMPLES,
        "note": "synthetic data from rfml/signals.py; label -1 marks outlier (train_aux) and unknown (test_unknown) frames",
        "files": {},
    }

    def save(name: str, frames: dict, class_name: np.ndarray | None) -> None:
        arrays = {k: frames[k] for k in ("iq", "label", "tx_id", "snr_db")}
        arrays["classes"] = np.array(ex.KNOWN)
        if class_name is not None:
            # Fixed-width strings, so the file loads without pickle.
            arrays["class_name"] = np.asarray(class_name, dtype=str)
        path = args.out / f"{name}.npz"
        np.savez_compressed(path, **arrays)
        manifest["files"][path.name] = {
            "frames": int(frames["label"].size),
            "iq_shape": list(frames["iq"].shape),
            "snr_db_values": sorted({float(s) for s in frames["snr_db"]}),
            "sha256": sha256(path),
        }

    # Open-set stage (campaigns 1-3 open-set and scorer-bench data).
    frames = ex.build_open_set_data(scale, args.seed)
    for role, data in frames.items():
        if role in OPEN_SET_ROLES:
            classes, per_class = OPEN_SET_ROLES[role]
            names = ex._frame_class_names(data["tx_id"], classes, getattr(scale, per_class))
        else:  # val_select, val_calib: known classes, labels give the name
            names = np.array(ex.KNOWN)[data["label"]]
        save(f"openset_{role}", data, names)

    # Closed-set stage (campaign 1 modulation data, impaired devices), on request.
    if args.closed_set:
        train, val, test_by_snr = ex.build_modulation_data(scale, True, args.seed)
        save("closedset_train", train, np.array(ex.KNOWN)[train["label"]])
        save("closedset_val_select", val, np.array(ex.KNOWN)[val["label"]])
        test = ex.concat_frames([test_by_snr[s] for s in ex.MOD_TEST_SNRS])
        save("closedset_test_unseen_devices", test, np.array(ex.KNOWN)[test["label"]])

    (args.out / "MANIFEST.json").write_text(json.dumps(manifest, indent=2))
    total = sum(f["frames"] for f in manifest["files"].values())
    print(f"exported {len(manifest['files'])} files, {total} frames, to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

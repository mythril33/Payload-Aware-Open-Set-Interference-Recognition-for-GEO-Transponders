"""Train and evaluate one fixed CNN recipe on published FIOT RGB spectrograms."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import platform
import time

import numpy as np
import torch
from torch.nn import functional as nnf

from geoml.calibration import calibrate_scores
from geoml.evaluation import evaluate_scores
from geoml.experiment import _source_identity, _write_json
from geoml.mahalanobis import fit_mahalanobis
from geoml.metrics import confusion, macro_f1
from geoml.model import SmallResNet, n_parameters
from geoml.openset import unknown_scores
from geoml.train import _forward
from . import fraunhofer as data
from .baseline import file_sha, digest

ROOT = Path(__file__).resolve().parents[2]
PROTOCOL = "FIOT-CNN/1"
PUBLISHER_REVISION = "2ae2c4d092db5a86de3ecdc058d8c3f2cbf97c26"
SPLIT_SHA = {"train": "d295bababaa6938626be0fd43bc190479b6aec6d730ea4bb7cf3ec94cbb663b5",
             "test": "7fa00209df88ec5bcf42c08f22e5f26dfe02f727be75375f7121360a65a51155"}
HOLDOUT = 2
SEEDS = (0, 1, 2)
METHODS = ("msp", "energy", "mahalanobis")
SIZE = (128, 64)
WIDTH, EPOCHS, BATCH = 8, 10, 16
LR, WEIGHT_DECAY = .001, .0001


def partition_rows(train, test):
    """Choose exactly crop 0 and split known publisher training by parent."""
    data.audit_partitions(train, test)
    train_zero, test_zero = ([r for r in rows if r.crop == 0] for rows in (train, test))
    if any(len(zero) != len({r.recording_id for r in rows})
           for zero, rows in ((train_zero, train), (test_zero, test))):
        raise data.DataError("every publisher parent must have a crop 0")
    labels = tuple(sorted({r.label for r in train_zero} - {HOLDOUT}))
    if (len(labels) < 2 or HOLDOUT not in {r.label for r in train_zero}
            or set(r.label for r in test_zero) - {*labels, HOLDOUT}):
        raise data.DataError("publisher labels cannot support the declared holdout")
    roles = {name: [] for name in ("fit", "selection", "calibration", "known_test", "unknown_test")}
    for label in labels:
        rows = sorted((r for r in train_zero if r.label == label), key=lambda r: (
            hashlib.sha256(("fiot-cnn-split-v1:" + r.recording_id).encode()).digest(), r.recording_id))
        if len(rows) < 3:
            raise data.DataError("each known label needs a fit, selection and calibration parent")
        count = max(1, len(rows) // 5)
        roles["selection"].extend(rows[:count])
        roles["calibration"].extend(rows[count:2 * count])
        roles["fit"].extend(rows[2 * count:])
    for row in test_zero:
        roles["unknown_test" if row.label == HOLDOUT else "known_test"].append(row)
    if not all(roles.values()):
        raise data.DataError("required FIOT evaluation role is empty")
    return roles, labels, len(train_zero) - sum(len(roles[k]) for k in ("fit", "selection", "calibration"))


def load_images(root, refs, seen, role):
    """Convert released RGB images to float tensors without fitting statistics."""
    x = torch.empty((len(refs), 3, *SIZE), dtype=torch.float32)
    hashes = []
    for i, row in enumerate(data.iter_records(root, refs, kind="fiot")):
        other = seen.setdefault(row.sha256, role)
        if other != role:
            raise data.SplitLeakage(f"identical image bytes cross {other} and {role}")
        rgb = torch.from_numpy(row.values).permute(2, 0, 1).float().div_(255)
        x[i] = nnf.interpolate(rgb[None], size=SIZE, mode="area")[0]
        hashes.append((row.path, row.sha256))
    return x, digest(hashes)


def fit_model(x, y, validation, val_y, count, seed):
    torch.manual_seed(seed)
    generator = torch.Generator().manual_seed(seed)
    model = SmallResNet(count, width=WIDTH, in_ch=3)
    optimizer = torch.optim.AdamW(model.parameters(), lr=LR, weight_decay=WEIGHT_DECAY)
    scheduler = torch.optim.lr_scheduler.OneCycleLR(optimizer, max_lr=LR,
        total_steps=EPOCHS * ((len(x) + BATCH - 1) // BATCH))
    targets = torch.from_numpy(y)
    best_f1, best, history = -1., None, []
    for epoch in range(1, EPOCHS + 1):
        model.train()
        loss_sum = 0.
        for indices in torch.randperm(len(x), generator=generator).split(BATCH):
            optimizer.zero_grad()
            loss = nnf.cross_entropy(model(x[indices]), targets[indices])
            loss.backward()
            optimizer.step()
            scheduler.step()
            loss_sum += loss.item() * len(indices)
        outputs = _forward(model, validation, "cpu", BATCH)
        f1 = macro_f1(val_y, outputs["logits"].argmax(1), count)
        history.append({"epoch": epoch, "training_loss": loss_sum / len(x), "selection_macro_f1": f1})
        if f1 > best_f1:
            best_f1 = f1
            best = (epoch, {k: v.clone() for k, v in model.state_dict().items()})
        print(f"seed {seed} epoch {epoch:2d}/{EPOCHS}: selection macro-F1 {f1:.3f}", flush=True)
    model.load_state_dict(best[1])
    return model, best[0], history


def scores(outputs, scorer):
    return {"msp": unknown_scores(outputs["logits"], "msp"),
            "energy": unknown_scores(outputs["logits"], "energy"),
            "mahalanobis": scorer.score(outputs["embedding"])}


def run(root, train_path, test_path, out):
    start = time.perf_counter()
    out = Path(out).resolve()
    inputs = [Path(p).resolve() for p in (root, train_path, test_path)]
    if any(out == p or out in p.parents or p in out.parents for p in [ROOT, *inputs]):
        raise ValueError("choose a fresh output outside the repository and input roots")
    split_hashes = {"train": file_sha(train_path), "test": file_sha(test_path)}
    if split_hashes != SPLIT_SHA:
        raise data.DataError("publisher split hashes differ from the pinned FIOT release")
    train, test = (data.parse_split(p, kind="fiot") for p in (train_path, test_path))
    roles, labels, excluded = partition_rows(train, test)
    torch.set_num_threads(2)
    torch.set_num_interop_threads(1)
    out.mkdir(parents=True, exist_ok=False)
    sources = _source_identity()
    campaign = {"protocol": PROTOCOL, "publisher_revision": PUBLISHER_REVISION, "split_sha256": split_hashes,
        "input": {"format": "rendered RGB spectrogram", "released_shape": list(data.FIOT_SHAPE),
                  "model_shape": [3, *SIZE], "normalization": "byte / 255, area resize"},
        "known_labels": {str(i): data.CLASSES[i] for i in labels}, "unknown_label": {"id": HOLDOUT, "name": data.CLASSES[HOLDOUT]},
        "excluded_publisher_train_chirp": excluded, "publisher_train_parents": len({r.recording_id for r in train}),
        "publisher_test_parents": len({r.recording_id for r in test}),
        "partitions": {name: {"n": len(rows), "class_counts": dict(sorted(Counter(r.label for r in rows).items()))}
                       for name, rows in roles.items()},
        "recipe": {"width": WIDTH, "epochs": EPOCHS, "batch": BATCH, "optimizer": "AdamW + OneCycleLR",
                   "max_lr": LR, "weight_decay": WEIGHT_DECAY, "seeds": list(SEEDS), "augmentation": False,
                   "methods": list(METHODS), "target_known_acceptance": .95, "temperature": 1., "shrinkage": .1},
        "runtime": {"python": platform.python_version(), "torch": str(torch.__version__),
                    "numpy": np.__version__, "device": "cpu", "torch_threads": torch.get_num_threads()},
        "source": {"revision": sources["revision"], "sha256": {p: file_sha(ROOT / p) for p in (
            "research/public_data/fiot_cnn.py", "research/public_data/FIOT_CNN_PROTOCOL.md", "research/public_data/fraunhofer.py",
            "src/geoml/model.py", "src/geoml/train.py", "src/geoml/evaluation.py", "src/geoml/openset_metrics.py",
            "src/geoml/calibration.py", "src/geoml/openset.py", "src/geoml/mahalanobis.py")}},
        "benchmark_complete": False, "scope": "FIOT laboratory GNSS; no GEO transfer"}
    _write_json(out / "campaign.json", campaign)
    tensor, identities, seen = {}, {}, {}
    label_index = {label: i for i, label in enumerate(labels)}

    def targets(role):
        return np.array([label_index[r.label] for r in roles[role]], dtype=np.int64)

    def load(role):
        tensor[role], identities[role] = load_images(root, roles[role], seen, role)
        print(f"loaded {role}: {len(tensor[role])} recordings", flush=True)

    for role in ("fit", "selection", "calibration"):
        load(role)
    y, val_y = targets("fit"), targets("selection")
    frozen = []
    for seed in SEEDS:
        model, epoch, history = fit_model(tensor["fit"], y, tensor["selection"], val_y, len(labels), seed)
        path = out / f"seed-{seed}"
        path.mkdir()
        checkpoint = path / "model.pt"
        torch.save(model.state_dict(), checkpoint)
        model.load_state_dict(torch.load(checkpoint, map_location="cpu", weights_only=True))
        fitted = _forward(model, tensor["fit"], "cpu", BATCH)
        provenance = digest([file_sha(checkpoint), identities["fit"], campaign["recipe"]])
        scorer = fit_mahalanobis(fitted["embedding"], y, len(labels), .1, provenance)
        scorer.save(path / "mahalanobis.npz")
        calibration_scores = scores(_forward(model, tensor["calibration"], "cpu", BATCH), scorer)
        calibrators = {m: calibrate_scores(v, m, .95, provenance=digest([provenance, identities["calibration"], m]))
                       for m, v in calibration_scores.items()}
        _write_json(path / "calibration.json", {m: c.to_dict() for m, c in calibrators.items()})
        frozen.append((seed, model, epoch, history, scorer, calibrators))

    for role in ("known_test", "unknown_test"):
        load(role)
    known_y = targets("known_test")
    known_groups, unknown_groups = ([r.recording_id for r in roles[role]] for role in ("known_test", "unknown_test"))
    results = []
    for seed, model, epoch, history, scorer, calibrators in frozen:
        known = _forward(model, tensor["known_test"], "cpu", BATCH)
        unknown = _forward(model, tensor["unknown_test"], "cpu", BATCH)
        ks, us = scores(known, scorer), scores(unknown, scorer)
        metrics = {m: evaluate_scores(known["logits"], ks[m], us[m], known_y, known_groups, unknown_groups, c)
                   for m, c in calibrators.items()}
        pred = known["logits"].argmax(1)
        result = {"seed": seed, "selected_epoch": epoch, "history": history, "parameters": n_parameters(model),
                  "known_correct": int((pred == known_y).sum()), "known_macro_f1": macro_f1(known_y, pred, len(labels)),
                  "known_confusion": confusion(known_y, pred, len(labels)).tolist(), "metrics": metrics}
        _write_json(out / f"seed-{seed}" / "results.json", result)
        results.append(result)
    summary = {**campaign, "input_manifests_sha256": identities, "elapsed_seconds": time.perf_counter() - start,
               "known_accuracy": float(np.mean([r["known_correct"] / len(known_y) for r in results])),
               "known_macro_f1": float(np.mean([r["known_macro_f1"] for r in results])),
               "mean_open_set": {m: {"auroc": float(np.mean([r["metrics"][m]["ranking"]["unknown_auroc"] for r in results])),
                   **{k: float(np.mean([r["metrics"][m][k]["mean"] for r in results]))
                      for k in ("known_acceptance", "unknown_rejection")}} for m in METHODS},
               "results_by_seed": results}
    _write_json(out / "summary.json", summary)
    print(f"Wrote {out / 'summary.json'}", flush=True)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("data", "train", "test", "out"):
        parser.add_argument(f"--{name}", required=True, type=Path)
    args = parser.parse_args()
    try:
        run(args.data, args.train, args.test, args.out)
    except (ValueError, OSError) as error:
        parser.exit(2, f"error: {error}\n")


if __name__ == "__main__":
    main()

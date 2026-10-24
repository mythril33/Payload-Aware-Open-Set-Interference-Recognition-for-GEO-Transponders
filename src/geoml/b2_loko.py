"""P23 E2: deterministic A8 LOKO plans and a bounded, single-fold CPU smoke.

No production/sweep execution entry point is exposed while researcher gates
remain pending. Source artifacts and frozen P18 sampling are unchanged.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import time
from dataclasses import replace
from pathlib import Path

import numpy as np
import scipy
import torch

from geosim.b2_protocol import FEATURE_PROTOCOL, LABELS
from geosim import b2_dataset as _artifacts
from geosim.cancellation import CancellationConfig

from .artifacts import fingerprint
from .b2_experiment import B2ExperimentConfig, ROLES, _check_roles, _rate
from .b2_stream import B2Source, fit_streaming, infer_streaming, open_b2_known, open_b2_known_roles
from .calibration import RejectionCalibration, calibrate_scores
from .experiment import _sha256, _source_identity, _write_json
from .mahalanobis import MahalanobisScorer, fit_mahalanobis
from .openset import unknown_scores
from .openset_metrics import ranking_metrics
from .train import load, save

PROTOCOL = "B2-LOKO-harness/1"
SMOKE_MAX_GROUPS = 2
RANKING_KEYS = ("unknown_auroc", "unknown_aupr", "oscr_auc", "unknown_fpr_at_95_tpr")


def _runtime_identity():
    return {"python":platform.python_version(), "numpy":np.__version__, "scipy":scipy.__version__,
            "torch":str(torch.__version__), "device":"cpu",
            "torch_threads":torch.get_num_threads(), "torch_interop_threads":torch.get_num_interop_threads(),
            "torch_deterministic_algorithms":torch.are_deterministic_algorithms_enabled(),
            "torch_deterministic_debug_mode":torch.get_deterministic_debug_mode(),
            "mkldnn_enabled":torch.backends.mkldnn.enabled,
            "mkldnn_deterministic":getattr(torch.backends.mkldnn,"deterministic",None),
            "thread_environment":{name:os.environ.get(name) for name in
                ("OMP_NUM_THREADS","OPENBLAS_NUM_THREADS","MKL_NUM_THREADS","NUMEXPR_NUM_THREADS","PYTHONHASHSEED")}}


def _check_stage(manifest, config):
    if (manifest["protocol"] != config.protocol or tuple(manifest["labels"]) != LABELS
            or manifest["benchmark_complete"] is not False):
        raise ValueError("artifact does not match the requested incomplete B2 stage")
    if config.protocol == FEATURE_PROTOCOL and manifest.get("cancellation") != CancellationConfig().to_dict():
        raise ValueError("LOKO requires the frozen P20 obs-cancel/1 settings")


def _check_output_path(data, out):
    data, out = Path(data).resolve(), Path(out).resolve()
    if data == out or data in out.parents or out in data.parents:
        raise ValueError("LOKO data and output paths must be disjoint (no nesting or aliases)")


def _verify_artifact_snapshot(data, identity):
    """Recheck consumed artifact bytes after scoring without any fitting or inference."""
    manifest, current = _plan_header(data)
    if current != identity:
        raise ValueError("LOKO artifact identity changed during execution")
    for role, info in manifest["roles"].items():
        for descriptor in info["shards"]:
            for name, expected in descriptor["sha256"].items():
                if _sha256(Path(data) / role / name) != expected:
                    raise ValueError("LOKO artifact bytes changed during execution")


def _read_json(path):
    def unique(pairs):
        out = {}
        for key, value in pairs:
            if key in out:
                raise ValueError(f"duplicate JSON key: {key}")
            out[key] = value
        return out
    def reject(value):
        raise ValueError(f"nonfinite JSON value: {value}")
    value = json.loads(Path(path).read_text(), object_pairs_hook=unique, parse_constant=reject)
    json.dumps(value, allow_nan=False)
    return value


def _plan_header(data):
    """Canonical metadata identity only; never opens role NPZ/JSONL observations."""
    manifest, _ = _artifacts._header(Path(data))
    request = manifest["request"]
    for role, info in manifest["roles"].items():
        for index, descriptor in enumerate(info["shards"]):
            part, meta, descriptor_path = _artifacts._paths(Path(data), role, index)
            groups = _artifacts._groups(request, role, index)
            if (descriptor.get("part") != part.name or descriptor.get("meta") != meta.name
                    or descriptor.get("role") != role or descriptor.get("scenario_seeds") != groups
                    or descriptor.get("n_samples") != len(groups) * len(LABELS)
                    or descriptor.get("request_fingerprint") != manifest["request_fingerprint"]
                    or _read_json(descriptor_path) != descriptor):
                raise ValueError("incompatible B2 planning shard descriptor")
            hashes = descriptor.get("sha256", {})
            if set(hashes) != {part.name, meta.name} or any(
                    not isinstance(h, str) or len(h) != 64 or set(h) - set("0123456789abcdef") for h in hashes.values()):
                raise ValueError("invalid B2 planning shard hashes")
    return manifest, _artifacts._fingerprint(manifest)


class _DeclaredRole:
    """Bookkeeping declared by the canonical paired artifact contract, not observations."""
    kind = "known"
    def __init__(self, role, groups):
        self.role, self.groups = role, np.asarray(groups, dtype=np.int64)
        self.index = {"seed": np.repeat(self.groups, len(LABELS)),
                      "label": np.tile(np.arange(len(LABELS)), len(self.groups))}
    def split(self):
        return self.index


def metadata_plan(data, config, *, seeds=(0, 1, 2)):
    """Plan from verified request/calibration/descriptors without reading test observations."""
    manifest, identity = _plan_header(data)
    _check_stage(manifest, config)
    if set(manifest["roles"]) != set(ROLES):
        raise ValueError("artifact does not match the requested incomplete B2 stage and roles")
    declared = {role: _DeclaredRole(role, manifest["roles"][role]["scenario_seeds"]) for role in ROLES}
    return manifest, identity, build_plan(declared, identity, config, seeds=seeds)


def _open_roles(data, config, roles, identity):
    manifest, actual, sources = open_b2_known_roles(data, roles)
    _check_stage(manifest, config)
    if actual != identity or manifest["protocol"] != config.protocol or set(sources) != set(roles):
        raise ValueError("scoped LOKO artifact identity or roles changed since planning")
    _check_roles({role: source.split() for role, source in sources.items()})
    for role, source in sources.items():
        expected = manifest["roles"][role]["scenario_seeds"]
        if source.groups.tolist() != expected or any(
                np.sum(source.index["seed"] == group) != len(LABELS) for group in source.groups):
            raise ValueError(f"{role} contains an incomplete paired scenario group")
        if config.protocol == FEATURE_PROTOCOL and not source.has_residual:
            raise ValueError("B2-feat/1 requires the stored observation-derived residual")
    return sources


def known_labels(holdout):
    if holdout not in LABELS[1:]:
        raise ValueError("holdout must be one of the seven non-clean B2 classes")
    return tuple(label for label in LABELS if label != holdout)


def fold_source(source, holdout):
    """Filter before preprocessing; remap labels in verified shards, never in the artifact.

    Only a small index and shard masks remain resident. Every read goes through
    the original source's checksum/index verification before filtering. Empty
    shards are omitted from the derived view (not silently read as empty data).
    """
    labels = known_labels(holdout)
    if source.kind != "known" or source.role not in ROLES:
        raise ValueError("LOKO fitting views require a frozen known-data role")
    held = LABELS.index(holdout)
    mapping = np.array([labels.index(name) if name in labels else -1 for name in LABELS])
    keep = source.index["label"] != held
    positions = np.flatnonzero(keep)
    if not len(positions):
        raise ValueError("no retained known observations in LOKO view")
    index = {key: value[keep] for key, value in source.index.items() if key != "meta"}
    index["label"] = mapping[index["label"]]
    index["meta"] = [source.index["meta"][i] for i in positions]
    shard_map, counts = [], []
    for i, (start, count) in enumerate(zip(source.offsets, source.shard_counts)):
        retained = int(keep[start:start + count].sum())
        if retained:
            shard_map.append(i)
            counts.append(retained)

    def reader(order):
        for shard in source.shards([shard_map[i] for i in order]):
            mask = shard["label"] != held
            selected = np.flatnonzero(mask)
            result = {key: np.asarray(shard[key])[mask] for key in
                      ("spec", "mask", "residual", "label", "seed", "plan_consistency") if key in shard}
            result["label"] = mapping[result["label"]]
            result["meta"] = [shard["meta"][i] for i in selected] if shard.get("meta") is not None else None
            yield result

    return B2Source("known", index, counts, reader, role=source.role,
                    root=source.root, has_residual=source.has_residual)


def build_plan(sources, identity, config, *, seeds=(0, 1, 2)):
    """Describe 7 × 3 fits per view without fitting or evaluating any model."""
    if (not isinstance(seeds, (tuple, list)) or len(seeds) != 3 or
            any(isinstance(seed, bool) or not isinstance(seed, int) or seed < 0 for seed in seeds)
            or len(set(seeds)) != 3):
        raise ValueError("the LOKO plan requires three distinct nonnegative integer training seeds")
    if set(sources) != set(ROLES) or any(s.kind != "known" or s.role != role for role, s in sources.items()):
        raise ValueError("LOKO requires exactly the four frozen known-data roles")
    parts = {role: source.split() for role, source in sources.items()}
    _check_roles(parts)
    # A complete paired group has exactly one instance of each of the eight
    # labels; B2Source already rejects duplicates. Refuse incomplete groups.
    for role, part in parts.items():
        if any(np.sum(part["seed"] == group) != len(LABELS) for group in sources[role].groups):
            raise ValueError(f"{role} contains an incomplete paired scenario group")
    folds = []
    for holdout in LABELS[1:]:
        labels = known_labels(holdout)
        partitions = {}
        for role, source in sources.items():
            held = source.index["label"] == LABELS.index(holdout)
            partitions[role] = {
                "scenario_ids": source.groups.tolist(),
                "n_retained_known": int((~held).sum()),
                "n_heldout": int(held.sum()),
                "heldout_use": "unknown evaluation only" if role == "test" else "excluded before preprocessing",
                "selection_fingerprint": fingerprint({"data": identity, "role": role,
                    "retained_rows": np.flatnonzero(~held).tolist(), "known_labels": labels})}
        folds.append({"holdout_label": holdout, "known_labels": list(labels),
                      "original_to_local": {name: labels.index(name) for name in labels},
                      "partitions": partitions})
    plan = {"protocol": PROTOCOL, "parent_protocol": "B2/1", "benchmark_complete": False,
            "status": "PLAN_ONLY", "data_fingerprint": identity, "config": json.loads(json.dumps(config.resolved())),
            "training_seeds": list(seeds), "seed_policy": "explicit deterministic harness choice; no seed search",
            "folds": folds, "fits_per_view": 21, "total_planned_fits": 21 * len(config.views),
            "full_sweep_authorized": False,
            "test_population": "seven retained known variants and one held-out variant per test scenario; no B2-test/1 families",
            "uncertainty": "paired scenario-group bootstrap with fixed model/scorer/threshold; training-seed uncertainty separate"}
    return {**plan, "plan_fingerprint": fingerprint(plan)}


def _ranking(scores, original_labels, predictions, groups, holdout, *, bootstrap=200, seed=20261022):
    held = original_labels == LABELS.index(holdout)
    names = known_labels(holdout)
    local = np.array([names.index(LABELS[int(i)]) if not h else -1 for i, h in zip(original_labels, held)])
    known = ~held
    correct = predictions[known] == local[known]
    counts = {"n_known": int(known.sum()), "n_unknown": int(held.sum()),
              "n_scenarios": int(len(np.unique(groups)))}
    if not known.any() or not held.any():
        return {**counts, **{key: None for key in RANKING_KEYS}, "ci95": None,
                "note": "both known and held-out populations are required"}
    result = ranking_metrics(scores[known], scores[held], correct)
    ids = np.unique(groups)
    ci = None
    if len(ids) > 1:
        rng = np.random.default_rng(seed)
        samples = {key: [] for key in RANKING_KEYS}
        by_group = {g: np.flatnonzero(groups == g) for g in ids}
        # Resample a group ONCE and use all eight variants together: known and
        # held-out samples are paired, not independently bootstrapped.
        for _ in range(bootstrap):
            rows = np.concatenate([by_group[g] for g in rng.choice(ids, len(ids), replace=True)])
            h = held[rows]
            metrics = ranking_metrics(scores[rows][~h], scores[rows][h], predictions[rows][~h] == local[rows][~h])
            for key in samples:
                samples[key].append(metrics[key])
        ci = {key: np.quantile(values, [0.025, 0.975]).tolist() for key, values in samples.items()}
    return {**result, **counts, "ci95": ci, "bootstrap": {"replicates": bootstrap, "seed": seed,
            "unit": "scenario group, paired known/held-out", "fixed": "model, scorer and val-calib threshold",
            "training_seed_uncertainty_included": False}}


def _open(data, config):
    manifest, identity, sources = open_b2_known(data)
    if (manifest["protocol"] != config.protocol or tuple(manifest["labels"]) != LABELS or
            manifest["benchmark_complete"] is not False):
        raise ValueError("artifact does not match the requested incomplete B2 stage")
    if config.protocol == FEATURE_PROTOCOL and any(not s.has_residual for s in sources.values()):
        raise ValueError("B2-feat/1 requires the stored observation-derived residual")
    return manifest, identity, sources


def run_smoke(config, data, out, *, holdout, reuse=False, bootstrap=200, log=print):
    """One fold, one view, CPU, <=2 groups/role, <=2 epochs; no sweep API."""
    labels = known_labels(holdout)
    if len(config.views) != 1:
        raise ValueError("smoke execution allows exactly one view")
    cfg = replace(config.train_config(config.views[0]), labels=labels)
    if cfg.epochs > 2 or cfg.width > 8 or cfg.batch > 32:
        raise ValueError("smoke caps: epochs<=2, width<=8, batch<=32")
    if isinstance(bootstrap, bool) or not isinstance(bootstrap, int) or not 1 <= bootstrap <= 1000:
        raise ValueError("bootstrap must be an integer in [1, 1000]")
    _check_output_path(data, out)
    manifest, identity, plan = metadata_plan(data, config)
    if any(len(part["scenario_seeds"]) > SMOKE_MAX_GROUPS for part in manifest["roles"].values()):
        raise ValueError("smoke execution requires an artifact with at most 2 groups per role; full LOKO is not authorized")
    sources = _open_roles(data, config, ROLES[:-1], identity)
    fold = next(f for f in plan["folds"] if f["holdout_label"] == holdout)
    filtered = {role: fold_source(sources[role], holdout) for role in ROLES if role != "test"}
    source = _source_identity()
    runtime = _runtime_identity()
    provenance = {"protocol": PROTOCOL, "data_fingerprint": identity, "holdout_label": holdout,
                  "fold": fold, "config": config.resolved(), "window_shards": config.window_shards,
                  "source_files_sha256": source["files_sha256"], "runtime_identity": runtime}
    experiment_id = fingerprint(provenance)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    path = out / "model.pt"
    if any(out.iterdir()) and not reuse:
        raise ValueError("output already exists; use --reuse or a new output directory")
    if any(out.iterdir()) and not path.exists():
        raise ValueError("nonempty output has no compatible checkpoint; use a new output directory")
    started = time.monotonic()
    if path.exists():
        fitted = load(path, device="cpu", expected_config=cfg, expected_provenance=provenance)
    else:
        fitted = fit_streaming(filtered["train"], filtered["val-select"], cfg,
                               window_shards=config.window_shards, device="cpu", log=log)
        fitted.update(provenance=provenance, source_revision=source["revision"])
        save(fitted, path)
        fitted = load(path, device="cpu", expected_config=cfg, expected_provenance=provenance)
    checkpoint_sha = _sha256(path)
    derived_id = fingerprint({"experiment": experiment_id, "checkpoint_sha256": checkpoint_sha})
    train = infer_streaming(fitted, filtered["train"])
    # Freeze scorer and all thresholds BEFORE reading any test inputs.
    scorer = fit_mahalanobis(train["embedding"], filtered["train"].index["label"], len(labels),
                             config.mahalanobis_regularization, provenance=derived_id)
    scorer_path = out / "mahalanobis.npz"
    if scorer_path.exists() and MahalanobisScorer.load(scorer_path).to_dict() != scorer.to_dict():
        raise ValueError("existing Mahalanobis scorer does not match checkpoint/training data")
    if not scorer_path.exists():
        scorer.save(scorer_path)
    calib = infer_streaming(fitted, filtered["val-calib"])
    calibrations = {}
    for method in config.methods:
        scores = scorer.score(calib["embedding"]) if method == "mahalanobis" else unknown_scores(calib["logits"], method)
        calibration = calibrate_scores(scores, method, config.target_acceptance, provenance=derived_id)
        calibration_path = out / f"rejection_{method}.json"
        if calibration_path.exists() and RejectionCalibration.from_dict(_read_json(calibration_path)) != calibration:
            raise ValueError("existing rejection calibration does not match checkpoint/known val-calib data")
        calibrations[method] = calibration
        if not calibration_path.exists():
            calibration.save(calibration_path)
    files = ["model.pt", "mahalanobis.npz"] + [f"rejection_{method}.json" for method in config.methods]
    frozen = {"schema": "B2-LOKO-frozen/1", "benchmark_complete": False,
              "experiment_fingerprint": experiment_id, "data_fingerprint": identity,
              "holdout_label": holdout, "known_labels": list(labels), "fold": fold,
              "config": json.loads(json.dumps(config.resolved())),
              "runtime_identity": runtime,
              "files_sha256": {name: _sha256(out / name) for name in files}}
    frozen["freeze_fingerprint"] = fingerprint(frozen)
    freeze_path = out / "freeze.json"
    if freeze_path.exists() and _read_json(freeze_path) != frozen:
        raise ValueError("existing frozen LOKO files differ from checkpoint/scorer/calibration identity")
    if not freeze_path.exists():
        _write_json(freeze_path, frozen)
    def verify_frozen():
        if _source_identity()["files_sha256"] != source["files_sha256"] or _runtime_identity() != runtime:
            raise ValueError("LOKO source or runtime identity changed during execution")
        if (_sha256(freeze_path) != fingerprint_freeze or _read_json(freeze_path) != frozen
                or any(_sha256(out / name) != digest for name, digest in frozen["files_sha256"].items())):
            raise ValueError("LOKO frozen files changed during evaluation")
    fingerprint_freeze = _sha256(freeze_path)
    verify_frozen()
    # No test observations are opened until the complete disk state is frozen.
    sources.update(_open_roles(data, config, ("test",), identity))
    test = infer_streaming(fitted, sources["test"])
    original = sources["test"].index["label"]
    groups = sources["test"].index["seed"]
    held = original == LABELS.index(holdout)
    predictions = test["logits"].argmax(1)
    local = np.array([labels.index(LABELS[int(i)]) if not h else -1 for i, h in zip(original, held)])
    methods, score_rows = {}, {}
    for method, calibration in calibrations.items():
        scores = scorer.score(test["embedding"]) if method == "mahalanobis" else unknown_scores(test["logits"], method)
        accepted = calibration.accept(scores)
        methods[method] = {"calibration": calibration.to_dict(),
            "ranking": _ranking(scores, original, predictions, groups, holdout, bootstrap=bootstrap),
            "known_acceptance": _rate(accepted[~held], groups[~held]),
            "accepted_known_accuracy": _rate((predictions == local)[~held & accepted], groups[~held & accepted]),
            "known_correct_acceptance": _rate((predictions == local)[~held] & accepted[~held], groups[~held]),
            "unknown_rejection": _rate(~accepted[held], groups[held])}
        score_rows[method] = scores
    verify_frozen()
    _verify_artifact_snapshot(data, identity)
    result = {"protocol": PROTOCOL, "benchmark_complete": False, "mode": "BOUNDED_CPU_SMOKE",
              "holdout_label": holdout, "known_labels": list(labels), "fold": fold,
              "plan_fingerprint": plan["plan_fingerprint"], "experiment_fingerprint": experiment_id,
              "data_fingerprint": identity, "config": config.resolved(), "source": source,
              "checkpoint_sha256": checkpoint_sha, "history": fitted["history"],
              "runtime_identity": runtime,
              "best_epoch": fitted.get("best_epoch"), "best_val_macro_f1": fitted.get("best_val_macro_f1"),
              "freeze_manifest_sha256": _sha256(freeze_path), "frozen_files_sha256": frozen["files_sha256"],
              "train_diagnostics": fitted.get("train_diagnostics"),       # K18, observation only
              "n_mahalanobis_training": len(filtered["train"]), "methods": methods,
              "denominators": {"known_acceptance": "all seven retained test variants per scenario",
                  "accepted_known_accuracy": "accepted retained known test variants only; null when empty",
                  "known_correct_acceptance": "all retained known test variants",
                  "unknown_rejection": "held-out variant of every test scenario",
                  "ranking": "unknown-positive; OSCR known denominator is all retained known test variants"},
              "runtime": {"python": platform.python_version(), "numpy": np.__version__, "torch": str(torch.__version__),
                          "device": "cpu", "elapsed_seconds": time.monotonic() - started},
              "limitation": "execution evidence only; no production sweep, unknown-family evaluation or seed uncertainty"}
    rows = [{"scenario_id": int(g), "true_label": LABELS[int(y)], "is_unknown": bool(h),
             "prediction": labels[int(p)], "unknown_scores": {m: float(s[i]) for m, s in score_rows.items()}}
            for i, (g, y, h, p) in enumerate(zip(groups, original, held, predictions))]
    _write_json(out / "plan.json", plan)
    _write_json(out / "results.json", result)
    _write_json(out / "predictions.json", rows)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--data", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--smoke-holdout", choices=LABELS[1:], help="explicit bounded CPU smoke; default is plan only")
    parser.add_argument("--reuse", action="store_true")
    args = parser.parse_args(argv)
    config = B2ExperimentConfig.from_file(args.config)
    if args.smoke_holdout:
        run_smoke(config, args.data, args.out, holdout=args.smoke_holdout, reuse=args.reuse)
    else:
        _, _, plan = metadata_plan(args.data, config)
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        path = out / "plan.json"
        if path.exists():
            if not args.reuse or json.loads(path.read_text()) != plan:
                raise ValueError("plan already exists or is incompatible; use a new output directory")
        _write_json(path, plan)
        print(f"Wrote plan only ({plan['total_planned_fits']} planned fits; none executed): {path}")


if __name__ == "__main__":
    main()

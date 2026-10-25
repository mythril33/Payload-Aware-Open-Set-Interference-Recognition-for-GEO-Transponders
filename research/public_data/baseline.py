"""Small public-data detection baselines. No B2 data or simulator invocation.

Freeze protocol.json before evaluation. Native class 0 is clean for Fraunhofer
and documented on-board location labels; NGSO test direction is caller-verified.
RGB pixels and receiver quality values never acquire RF power units here.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import time

import numpy as np

from geoml.metrics import clean_alarm_threshold
from geoml.openset_metrics import _roc, _fpr_at_tpr, _trapezoid
from . import fraunhofer as F

PROTOCOL_PATH = Path(__file__).with_name("protocol.json")
SUPPORTED_PROTOCOL_SHA256 = "01a31bdac05438c0e2a81819275030f4d51e6f56f7b58870b3fdb96a30b2ac22"


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def file_sha(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def protocol():
    # This is a fixed pilot, not a configurable search. A changed description
    # must not silently claim that different hard-coded features were executed.
    if file_sha(PROTOCOL_PATH) != SUPPORTED_PROTOCOL_SHA256:
        raise ValueError("protocol differs from implemented fixed pilot; review and version before evaluation")
    return json.loads(PROTOCOL_PATH.read_text())


def calibration_id(recording_id):
    return int(hashlib.sha256(("public-calib-v1:" + str(recording_id)).encode()).hexdigest()[:8], 16) / 2**32 < .25


def lc_features(values):
    x = np.asarray(values)
    if x.ndim != 2 or x.shape[1] != 308 or not len(x) or not np.isfinite(x).all():
        raise ValueError("nonempty finite LC recording required")
    ss = x[:, 57:98].astype(float)
    positive = ss[ss > 0]
    temporal = np.array([row[row > 0].mean() if np.any(row > 0) else 0 for row in ss])
    return np.array([positive.mean() if len(positive) else 0, positive.std() if len(positive) else 0,
                     np.mean(ss > 0), temporal.std(), x[:, 180:244].mean(), x[:, 244:308].mean()], float)


def fiot_features(values):
    x = np.asarray(values)
    if x.shape != (512, 243, 3) or x.dtype.kind not in "iuf" or not np.isfinite(x).all():
        raise ValueError("inspected FIOT 512x243x3 rendered image required")
    x = x.astype(float)
    return np.r_[x.mean(axis=(0, 1)), x.std(axis=(0, 1)), np.abs(np.diff(x, axis=0)).mean(), np.abs(np.diff(x, axis=1)).mean()]


def smartspace_features(values):
    """Magnitude statistics; units are relative native amplitude, never watts."""
    raw = np.asarray(values)
    if raw.ndim != 2 or raw.shape[1] not in (100, 800, 1000) or not np.isfinite(raw).all():
        raise ValueError("finite observed SmartSpace bins required; no appended labels/INR/angles")
    x = np.abs(raw).astype(float)
    return np.c_[np.mean(x*x, axis=1), x.mean(axis=1), x.std(axis=1),
                 np.quantile(x, .95, axis=1), np.median(x, axis=1), np.mean(np.abs(np.diff(x, axis=1)), axis=1)]


def fit_scores(features, labels, *, level_direction=1, level_columns=(0,)):
    """Only fitting-train arrays enter this function. No test-dependent choice."""
    x, y = np.asarray(features, float), np.asarray(labels)
    if x.ndim != 2 or not len(x) or y.shape != (len(x),) or y.dtype.kind not in "iu" or np.any(y < 0) or not np.isfinite(x).all():
        raise ValueError("finite aligned fitting features and native labels required")
    clean = x[y == 0]
    if len(clean) < 2:
        raise ValueError("at least two fitting-clean recordings required")
    center, std = clean.mean(axis=0), clean.std(axis=0)
    if not np.isfinite(center).all() or not np.isfinite(std).all():
        raise ValueError("fitting statistics exceed finite range")
    if level_direction not in (-1, 1) or not level_columns or any(type(c) is not int or not 0 <= c < x.shape[1] for c in level_columns):
        raise ValueError("fixed native-level direction and feature columns required")
    active = std > 1e-12
    if not active.any():
        raise ValueError("no varying clean feature can establish a distance model")
    scale = np.where(active, std, 1.)
    positive = x[y != 0]
    centroid = (((positive - center) / scale)[:, active].mean(axis=0) if len(positive) else None)
    if centroid is not None and not np.isfinite(centroid).all():
        raise ValueError("positive centroid exceeds finite range")
    return {"center": center.tolist(), "scale": scale.tolist(), "active": active.tolist(),
            "positive_centroid": None if centroid is None else centroid.tolist(),
            "level_direction": int(level_direction), "level_columns": list(level_columns),
            "n_fit_clean": len(clean), "n_fit_positive": len(positive)}


def score(features, model):
    x = np.asarray(features, float)
    center, scale, active = np.array(model["center"]), np.array(model["scale"]), np.array(model["active"], bool)
    if x.ndim != 2 or x.shape[1] != len(center) or not np.isfinite(x).all():
        raise ValueError("finite features in the frozen feature order required")
    z = ((x - center) / scale)[:, active]
    distance = (z*z).mean(axis=1)
    result = {"native_level": model["level_direction"] * x[:, model["level_columns"]].mean(axis=1), "clean_diagonal_distance": distance}
    if model["positive_centroid"] is not None:
        result["binary_centroid_margin"] = distance - ((z - np.asarray(model["positive_centroid"]))**2).mean(axis=1)
    if not all(np.isfinite(s).all() for s in result.values()):
        raise ValueError("scores exceed finite numerical range")
    return result


def _rank(labels, scores):
    y, s = np.asarray(labels) != 0, np.asarray(scores, float)
    if not y.any() or y.all():
        return {"auroc": None, "average_precision": None, "fpr_at_95_tpr": None}
    fpr, tpr, tp, detected = _roc(s[~y], s[y])
    return {"auroc": _trapezoid(tpr, fpr), "average_precision": float(np.sum(np.diff(tpr) * tp / detected)),
            "fpr_at_95_tpr": _fpr_at_tpr(fpr, tpr, .95)}


def evaluate(labels, scores, groups, threshold, *, bootstrap=500, seed=20261025, published_counts=None, class_map=None):
    y, s, g = np.asarray(labels), np.asarray(scores, float), np.asarray(groups, str)
    if y.ndim != 1 or y.dtype.kind not in "iu" or np.any(y < 0) or s.shape != y.shape or g.shape != y.shape or not len(y) or not np.isfinite(s).all():
        raise ValueError("aligned finite evaluation scores, labels and parent IDs required")
    if type(bootstrap) is not int or not 1 <= bootstrap <= 2000 or not np.isfinite(threshold):
        raise ValueError("bounded bootstrap and finite frozen threshold required")
    alarm, positive = s > threshold, y != 0
    def rate(mask):
        n = int(mask.sum())
        return {"count": int(alarm[mask].sum()), "denominator": n, "rate": float(alarm[mask].mean()) if n else None,
                "reason": None if n else "no usable observations in this population"}
    class_map = {int(k): str(v) for k, v in (class_map or {k:str(k) for k in np.unique(y)}).items()}
    if not set(y.tolist()) <= set(class_map):
        raise ValueError("native label absent from the declared class map")
    result = {**_rank(y, s), "detection": rate(positive), "false_alarm": rate(~positive),
              "interference_prevalence": float(positive.mean()),
              "per_native_class": {str(label): {"name": name, **rate(y == label)} for label, name in class_map.items()},
              "positive": "native label != 0 (interference)", "score_direction": "higher_is_more_interference_like",
              "oscr": None, "oscr_reason": "binary detector; no known/unknown classifier task defined",
              "ranking_reason": None if positive.any() and not positive.all() else "both clean and interference required",
              "threshold": float(threshold)}
    ids = np.unique(g)
    members = [np.flatnonzero(g == value) for value in ids]
    values = {name: [] for name in ("auroc", "average_precision", "detection", "false_alarm")}
    rng = np.random.default_rng(seed)
    for _ in range(bootstrap):
        pick = np.concatenate([members[i] for i in rng.integers(0, len(ids), size=len(ids))])
        metrics = _rank(y[pick], s[pick])
        for name in ("auroc", "average_precision"):
            if metrics[name] is not None:
                values[name].append(metrics[name])
        for name, mask in (("detection", y[pick] != 0), ("false_alarm", y[pick] == 0)):
            if mask.any():
                values[name].append(float(alarm[pick][mask].mean()))
    result["bootstrap"] = {"unit": "publisher parent-recording ID; all retained crops together", "seed": seed,
                           "requested": bootstrap, "groups": len(ids), "session_independence": "UNKNOWN",
                           "ci95": {k: np.quantile(v, [.025, .975]).tolist() if len(ids) >= 2 and v else None for k, v in values.items()},
                           "valid_draws": {k: len(v) for k, v in values.items()},
                           "reason": None if len(ids) >= 2 else "fewer than two parent IDs; uncertainty not estimable"}
    if published_counts is not None:
        published = sum(int(v) for v in published_counts.values())
        n_positive = sum(int(v) for k, v in published_counts.items() if int(k) != 0)
        result["coverage"] = {"evaluated_nonempty": len(y), "published_selected": published,
                              "abstentions": published-len(y), "fraction": len(y)/published,
                              "detected_positive_over_all_published_positive": {"count": int(alarm[positive].sum()), "denominator": n_positive,
                                  "rate": float(alarm[positive].sum()/n_positive) if n_positive else None,
                                  "convention": "empty recordings counted as undetected, lower-bound sensitivity"}}
    if positive.any() and not positive.all():
        fpr, tpr, *_ = _roc(s[~positive], s[positive])
        result["roc"] = {"fpr": fpr.tolist(), "tpr": tpr.tolist()}
    else:
        result["roc"] = None
    return result


def prepare_fraunhofer(data_root, train_split, test_split, kind):
    train, test = F.parse_split(train_split, kind=kind), F.parse_split(test_split, kind=kind)
    partition_audit = F.audit_partitions(train, test)
    if kind == "fiot":
        train = [r for r in train if r.crop == 0]
        test = [r for r in test if r.crop == 0]
    data, excluded, manifests = {}, {}, {}
    feature_fn = lc_features if kind == "lc" else fiot_features
    for role, refs in (("train", train), ("test", test)):
        rows, skipped, fingerprints = [], Counter(), []
        for sample in F.iter_records(data_root, refs, kind=kind, max_records=1024):
            fingerprints.append({"id": sample.recording_id, "native_label": sample.label, "sha256": sample.sha256})
            if not len(sample.values):
                skipped[sample.label] += 1
                continue
            rows.append((feature_fn(sample.values), sample.label, sample.recording_id, sample.sha256))
        if not rows:
            raise ValueError("no nonempty recordings")
        data[role] = {"x": np.stack([r[0] for r in rows]), "y": np.array([r[1] for r in rows]),
                      "groups": np.array([r[2] for r in rows]), "sha256": [r[3] for r in rows],
                      "published_counts": dict(Counter(r.label for r in refs))}
        excluded[role] = dict(sorted(skipped.items()))
        manifests[role] = digest(fingerprints)
    overlap = set(data["train"]["sha256"]) & set(data["test"]["sha256"])
    if overlap:
        raise ValueError("nonempty train/test bytes overlap")
    return data, {"publisher_partition_audit": partition_audit, "empty_abstentions_by_class": excluded,
                  "selected_published": {"train": len(train), "test": len(test)}, "raw_manifest_sha256": manifests,
                  "nonempty_train_test_hash_overlap": 0, "train_split_sha256": file_sha(train_split), "test_split_sha256": file_sha(test_split)}


def experiment(data, *, level_direction=1, level_columns=(0,), bootstrap=500, class_map=None):
    settings = protocol()
    train, test = data["train"], data["test"]
    if set(train["groups"]) & set(test["groups"]):
        raise ValueError("fitting/calibration groups overlap evaluation groups")
    calibration = np.array([calibration_id(g) for g in train["groups"]])
    fitting = ~calibration
    clean_cal = calibration & (train["y"] == 0)
    if clean_cal.sum() < 2:
        raise ValueError("at least two disjoint clean calibration recordings required; insufficient population")
    model = fit_scores(train["x"][fitting], train["y"][fitting], level_direction=level_direction, level_columns=level_columns)
    cal_scores, test_scores = score(train["x"][clean_cal], model), score(test["x"], model)
    reports = {}
    for name in test_scores:
        threshold = clean_alarm_threshold(cal_scores[name], settings["pfa_target"])
        reports[name] = evaluate(test["y"], test_scores[name], test["groups"], threshold, bootstrap=bootstrap,
                                 published_counts=test.get("published_counts"), class_map=class_map)
        reports[name]["calibration"] = {"nominal_pfa": settings["pfa_target"], "count": int(np.sum(cal_scores[name] > threshold)),
                                         "denominator": int(clean_cal.sum()), "quantile_method": "higher", "alarm_rule": "score > threshold"}
    return {"model": model, "fitting_groups": int(len(set(train["groups"][fitting]))),
            "calibration_groups": int(len(set(train["groups"][calibration]))), "clean_calibration": int(clean_cal.sum()),
            "evaluation_groups": int(len(set(test["groups"]))), "results": reports}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=("lc", "fiot"), required=True)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--train", type=Path, required=True)
    parser.add_argument("--test", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    start = time.perf_counter()
    data, audit = prepare_fraunhofer(args.data, args.train, args.test, args.kind)
    result = {"protocol": protocol(), "protocol_sha256": file_sha(PROTOCOL_PATH),
              "dataset": "Fraunhofer LC laboratory receiver features" if args.kind == "lc" else "Fraunhofer FIOT laboratory RGB crops",
              "native_class_map": F.CLASSES, "audit": audit, "experiment": experiment(data, level_direction=-1 if args.kind == "lc" else 1,
                 level_columns=(0,) if args.kind == "lc" else (0, 1, 2), class_map=F.CLASSES),
              "scope": "measured GNSS public data; not GEO ground truth or B2/1", "benchmark_complete": False,
              "source_sha256": {p.name: file_sha(p) for p in Path(__file__).parent.glob("*.py")},
              "elapsed_seconds": time.perf_counter()-start}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, allow_nan=False)+"\n")
    print(json.dumps({"dataset": result["dataset"], "audit": audit, "counts": {k:len(v["y"]) for k,v in data.items()},
                      "metrics": {k:{name:v[name] for name in ("auroc","average_precision","detection","false_alarm","calibration")} for k,v in result["experiment"]["results"].items()}}, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

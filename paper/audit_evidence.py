#!/usr/bin/env python3
"""Audit committed paper evidence with the Python standard library only.

Reads the declared, small committed summaries and figure bytes. Does not import
research/ML/simulator modules, open raw observations, fit, infer or regenerate.
Run from any directory: python paper/audit_evidence.py
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import statistics

ROOT = Path(__file__).resolve().parents[1]


def strict_json(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    def nonfinite(value):
        raise ValueError(f"nonfinite JSON constant: {value}")

    return json.loads(path.read_text(), object_pairs_hook=unique, parse_constant=nonfinite)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def at(document, pointer):
    for key in pointer.strip("/").split("/") if pointer else []:
        key = key.replace("~1", "/").replace("~0", "~")
        document = document[int(key)] if isinstance(document, list) else document[key]
    return document


def same(actual, expected):
    if not math.isclose(actual, expected, rel_tol=1e-11, abs_tol=1e-12):
        raise AssertionError(f"arithmetic mismatch: {actual} != {expected}")


def verify_sources(evidence):
    documents = {}
    for path, expected in evidence["sources"].items():
        p = ROOT / path
        assert p.resolve().is_relative_to(ROOT), path
        assert sha(p) == expected, f"source hash mismatch: {path}"
        if p.suffix == ".json":
            documents[path] = strict_json(p)
    values = 0
    for claim in evidence["claims"]:
        p = claim["source"]
        for datum in claim.get("values", {}).values():
            assert at(documents[p], datum["pointer"]) == datum["value"], claim["id"]
            values += 1
        for text in claim.get("text_contains", []):
            assert text in (ROOT / p).read_text(), claim["id"]
    print(f"PASS: {len(evidence['sources'])} source hashes; {values} exact JSON-pointer values; {len(evidence['claims'])} claim groups")
    return documents


def verify_public_data(document):
    n_rows = 0
    for dataset in document["datasets"].values():
        exp, audit = dataset["experiment"], dataset["audit"]
        assert audit["publisher_partition_audit"]["recording_overlap"] == 0
        assert audit["nonempty_train_test_hash_overlap"] == 0
        assert exp["model"]["n_fit_clean"] + exp["model"]["n_fit_positive"] == exp["fitting_groups"]
        train_empty = sum(audit["empty_abstentions_by_class"]["train"].values())
        assert exp["fitting_groups"] + exp["calibration_groups"] + train_empty == audit["selected_published"]["train"]
        for result in exp["results"].values():
            n_rows += 1
            pd, fa, cov = result["detection"], result["false_alarm"], result["coverage"]
            for rate in (pd, fa):
                same(rate["rate"], rate["count"] / rate["denominator"])
            assert pd["denominator"] + fa["denominator"] == exp["evaluation_groups"]
            per_class = result["per_native_class"]
            assert sum(row["count"] for key, row in per_class.items() if key != "0") == pd["count"]
            assert sum(row["denominator"] for key, row in per_class.items() if key != "0") == pd["denominator"]
            assert per_class["0"]["count"] == fa["count"]
            for row in per_class.values():
                if row["denominator"]:
                    same(row["rate"], row["count"] / row["denominator"])
                else:
                    assert row["rate"] is None and row["reason"]
            assert cov["evaluated_nonempty"] + cov["abstentions"] == cov["published_selected"]
            same(cov["fraction"], cov["evaluated_nonempty"] / cov["published_selected"])
            lower = cov["detected_positive_over_all_published_positive"]
            same(lower["rate"], lower["count"] / lower["denominator"])
            assert lower["count"] == pd["count"]
            calibration = result["calibration"]
            assert calibration["denominator"] == exp["clean_calibration"]
            assert calibration["nominal_pfa"] == 0.05
            assert calibration["quantile_method"] == "higher"
            assert calibration["alarm_rule"] == "score > threshold"
            upper_alarm_count = calibration["denominator"] - 1 - math.ceil(0.95 * (calibration["denominator"] - 1))
            assert 0 <= calibration["count"] <= upper_alarm_count
            assert result["oscr"] is None and result["oscr_reason"]
            x, y = result["roc"]["fpr"], result["roc"]["tpr"]
            assert len(x) == len(y) and (x[0], y[0], x[-1], y[-1]) == (0, 0, 1, 1)
            assert all(a <= b for a, b in zip(x, x[1:])) and all(a <= b for a, b in zip(y, y[1:]))
            auc = sum((x[i] - x[i-1]) * (y[i] + y[i-1]) / 2 for i in range(1, len(x)))
            ap = 0.0
            for i in range(1, len(x)):
                tp, fp = y[i] * pd["denominator"], x[i] * fa["denominator"]
                if tp + fp:
                    ap += (y[i] - y[i-1]) * tp / (tp + fp)
            same(auc, result["auroc"])
            same(ap, result["average_precision"])
            same(min(a for a, b in zip(x, y) if b >= 0.95), result["fpr_at_95_tpr"])
    assert n_rows == 6
    print("PASS: six complete score rows; counts, coverage, per-class totals, calibration rule/count bounds, and independent ROC AUROC/AP/FPR95 arithmetic")


def verify_physics(documents):
    npr = documents["docs/results/npr_check.json"]["amplifiers"]["dvbs2_nl"]
    rows = [r for r in npr["rows"] if 10 <= r["ibo_db"] <= 14]
    xs, ys = [r["ibo_db"] for r in rows], [r["npr_db"] for r in rows]
    xm, ym = statistics.mean(xs), statistics.mean(ys)
    slope = sum((x-xm) * (y-ym) for x, y in zip(xs, ys)) / sum((x-xm)**2 for x in xs)
    same(slope, npr["slope_db_per_db_ibo_10_14"])
    cuc = documents["docs/results/cuc_visibility.json"]
    for summary in cuc["summary"]:
        selected = [r for r in cuc["rows"] if r["c_over_i_db"] == summary["c_over_i_db"]]
        assert len(selected) == summary["n"] == 24
        same(statistics.median(r["delta_db"] for r in selected), summary["median_delta_db"])
    cancellation = documents["docs/results/b2_feat_cancellation_check.json"]
    pairs = cancellation["paired_cuc"]
    summary = cancellation["paired_cuc_summary"]
    assert len(pairs) == summary["n_pairs"] == 8
    for key, field in [("median_delta_before_db", "delta_psd_before_cancellation_db"), ("median_delta_after_db", "delta_psd_after_cancellation_db")]:
        same(statistics.median(r[field] for r in pairs), summary[key])
    assert sum(r["delta_psd_after_cancellation_db"] > r["delta_psd_before_cancellation_db"] for r in pairs) == summary["n_pairs_after_exceeds_before"]
    print("PASS: existing-summary NPR regression slope, all six CuC medians and eight cancellation pairs")


def verify_figures(evidence):
    for figure in evidence["figures"]:
        assert sha(ROOT / figure["path"]) == figure["sha256"], figure["path"]
        if "manuscript_copy" in figure:
            assert sha(ROOT / figure["manuscript_copy"]) == figure["sha256"], figure["manuscript_copy"]
        for source in figure.get("sources", []):
            assert sha(ROOT / source["path"]) == source["sha256"], source["path"]
    print(f"PASS: {len(evidence['figures'])} figure/source identities and manuscript copies")


def verify_manuscript_tables(document):
    """Catch transcription/rounding errors without rerunning any experiment."""
    manuscript = (ROOT / "paper/manuscript.md").read_text()
    t2 = manuscript.split("**Table T2.", 1)[1].split("**Table T2b.", 1)[0]
    rows = [[field.strip() for field in line.strip().strip("|").split("|")]
            for line in t2.splitlines() if line.startswith(("| LC |", "| FIOT |"))]
    names = ["native_level", "clean_diagonal_distance", "binary_centroid_margin"]
    labels = {"lc": ["Native level", "Clean distance", "Centroid margin"],
              "fiot": ["Native RGB level", "Clean distance", "Centroid margin"]}
    expected = []
    for dataset in ("lc", "fiot"):
        for name, label in zip(names, labels[dataset]):
            result = document["datasets"][dataset]["experiment"]["results"][name]
            expected.append([dataset.upper(), label,
                             *[f"{result[key]:.4f}" for key in ("auroc", "average_precision", "fpr_at_95_tpr")],
                             f"{result['detection']['count']}/{result['detection']['denominator']}",
                             f"{result['false_alarm']['count']}/{result['false_alarm']['denominator']}"])
    assert rows == expected, "manuscript T2 differs from committed score results"
    t2b = manuscript.split("**Table T2b.", 1)[1].split("## Measured amplifier support", 1)[0]
    rows = [[field.strip() for field in line.strip().strip("|").split("|")]
            for line in t2b.splitlines() if line.startswith(("| LC |", "| FIOT |"))]
    expected = []
    for dataset in ("lc", "fiot"):
        intervals = []
        for name in names:
            ci = document["datasets"][dataset]["experiment"]["results"][name]["bootstrap"]["ci95"]["auroc"]
            intervals.append(f"[{ci[0]:.4f}, {ci[1]:.4f}]")
        expected.append([dataset.upper(), *intervals])
    assert rows == expected, "manuscript T2b differs from committed bootstrap endpoints"
    clean_n = document["datasets"]["lc"]["experiment"]["results"]["native_level"]["false_alarm"]["denominator"]
    upper_zero_alarm = 100 * (1 - 0.05 ** (1 / clean_n))
    assert f"{upper_zero_alarm:.2f}%" in manuscript, "zero-alarm binomial-bound transcription differs"
    print("PASS: manuscript T2 six rows and T2b all six AUROC intervals exactly match declared rounding; zero-alarm bound arithmetic")


def main():
    evidence = strict_json(ROOT / "paper/evidence.json")
    assert evidence["benchmark_complete"] is False
    documents = verify_sources(evidence)
    verify_public_data(documents["docs/results/public_data_baselines.json"])
    verify_physics(documents)
    verify_figures(evidence)
    verify_manuscript_tables(documents["docs/results/public_data_baselines.json"])
    print("Audit boundary: committed summaries only; no raw observations, fitting, inference, generation or bootstrap reruns.")


if __name__ == "__main__":
    main()

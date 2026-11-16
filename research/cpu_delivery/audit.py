"""Audit the committed CPU campaign aggregates; standard library, no data/fitting."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ARCHIVE = ROOT / "docs/results/cpu_delivery_2026-11-04"


def read(path):
    def reject(value):
        raise ValueError(f"nonfinite JSON: {value}")
    return json.loads(Path(path).read_text(), parse_constant=reject)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def same(a, b):
    assert math.isclose(a, b, rel_tol=1e-10, abs_tol=1e-12), (a, b)


def area(x, y):
    assert len(x) == len(y) and all(a <= b for a, b in zip(x, x[1:]))
    return sum((b - a) * (c + d) / 2 for a, b, c, d in zip(x, x[1:], y, y[1:]))


def audit():
    manifest = read(ARCHIVE / "archive.json")
    for name, expected in manifest["files_sha256"].items():
        path = (ROOT / name).resolve()
        assert path.is_relative_to(ROOT), name
        assert sha(path) == expected, name
    summary = read(ROOT / "docs/results/cpu_delivery_2026-11-04.json")
    campaign = read(ARCHIVE / "campaign.json")
    assert sha(ARCHIVE / "campaign.json") == summary["campaign_sha256"]
    assert summary["benchmark_complete"] is False and summary["campaign_complete"] is True
    assert summary["config"] == campaign["config"]
    assert sha(ROOT / "configs/cpu_delivery.json") == campaign["config_sha256"]
    # Preserve the actually-used runner. Later process-cleanup repairs do not
    # rewrite a completed campaign's provenance or make its old root resumable.
    assert sha(ARCHIVE / "runner-used.py") == campaign["runner_sha256"]
    for file, key in (("summarize.py", "summary_code_sha256"),
                      ("PREREGISTRATION.md", "preregistration_sha256")):
        assert sha(Path(__file__).with_name(file)) == campaign[key], file
    for name, expected in campaign["scientific_sources_sha256"].items():
        assert sha(ROOT / "src" / name) == expected, name
    assert summary["positive_class"] == "unknown"
    assert summary["score_direction"] == "higher_is_more_unknown_like"
    checked = 0
    for seed, config in zip(campaign["config"]["training_seeds"], campaign["resolved_fits"]):
        path = ARCHIVE / f"seed-{seed}.json"
        assert sha(path) == summary["result_sha256"][str(seed)]
        result = read(path)
        assert result["config"] == config
        assert result["source"]["files_sha256"] == campaign["scientific_sources_sha256"]
        assert result["partitions"] == summary["partitions"]
        assert result["data_fingerprints"] == summary["data_fingerprints"]
        groups = {k: set(v["scenario_ids"]) for k, v in result["partitions"].items()}
        for left in ("train", "validation", "calibration"):
            for right in groups:
                if left != right:
                    assert not groups[left] & groups[right], (left, right)
        for name, values in result["methods"].items():
            row = next(row for row in summary["pooled_rows"] if row["seed"] == seed and row["method"] == name)
            for key in ("unknown_auroc", "unknown_aupr", "oscr_auc", "n_known", "n_unknown"):
                same(row[key], values["ranking"][key])
            for key in ("known_closed_accuracy", "known_acceptance", "unknown_rejection", "false_alarm_on_clean"):
                same(row[key], values[key]["mean"])
            assert result["calibrators"][name]["n_calibration"] == result["partitions"]["calibration"]["n_samples"]
        for family, methods in [(None, result["methods"]), *result["methods_by_family"].items()]:
            for name, values in methods.items():
                ranking = values["ranking"]
                assert ranking["n_known"] == result["partitions"]["known_test"]["n_samples"]
                assert ranking["n_unknown"] == (result["partitions"]["unknown_test"]["n_samples"]
                                                if family is None else result["unknown_family_counts"][family])
                curves = ranking["curves"]
                roc, pr, oscr = curves["unknown_roc"], curves["unknown_pr"], curves["oscr"]
                same(area(roc["fpr"], roc["tpr"]), ranking["unknown_auroc"])
                same(sum((b - a) * p for a, b, p in zip(pr["recall"], pr["recall"][1:], pr["precision"][1:])),
                     ranking["unknown_aupr"])
                same(area(oscr["unknown_false_acceptance"], oscr["known_correct_acceptance"]), ranking["oscr_auc"])
                same(oscr["known_correct_acceptance"][-1], values["known_closed_accuracy"]["mean"])
                if family is not None:
                    row = next(r for r in summary["family_rows"] if (r["seed"], r["method"], r["family"]) == (seed, name, family))
                    same(row["unknown_auroc"], ranking["unknown_auroc"])
                    same(row["unknown_rejection"], values["unknown_rejection"]["mean"])
                checked += 1
    for method, metrics in summary["descriptive_seed_summary"].items():
        for metric, stats in metrics.items():
            values = [row[metric] for row in summary["pooled_rows"] if row["method"] == method]
            same(stats["mean"], sum(values) / len(values))
            assert stats["min"] == min(values) and stats["max"] == max(values)
    print(f"PASS: {len(manifest['files_sha256'])} archive/figure hashes; three fixed fits; "
          f"{checked} ROC/AP/OSCR populations; role separation, calibration counts and descriptive means/ranges.")
    print("Boundary: aggregate arithmetic and identities, not raw-observation or bootstrap reproduction.")


if __name__ == "__main__":
    audit()

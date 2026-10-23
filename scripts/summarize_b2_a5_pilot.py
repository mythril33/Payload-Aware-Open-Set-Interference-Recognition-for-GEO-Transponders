"""Compact, strict-JSON summary of a directory of bounded B2-A5-eval/1 invocations (E4).

    python scripts/summarize_b2_a5_pilot.py --runs runs/b2-a5-pilot \
        --out docs/results/b2_a5_dual_pol_pilot.json --markdown docs/results/b2_a5_dual_pol_pilot_table.md

Every invocation directory must hold a checksummed ``results.json`` (``results.json.sha256``). All invocations
must share the same known-data, request and checkpoint identities, otherwise nothing is summarized. Nothing is
recomputed: values are copied from the per-invocation results, so the summary traces back by hash.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

CONDITIONS = ("original", "MASK_ONLY", "RECEIVER_CONSISTENT")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _mean(rate):
    return None if not rate else rate.get("mean")


def _n(rate):
    return 0 if not rate else rate.get("n_samples", 0)


def _load(directory: Path) -> dict:
    results, sidecar = directory / "results.json", directory / "results.json.sha256"
    if not results.is_file() or not sidecar.is_file() or sidecar.read_text().strip() != _sha(results):
        raise ValueError(f"{directory}: missing or modified results.json")
    data = json.loads(results.read_text())
    if data.get("contract") != "B2-A5-eval/1" or data.get("benchmark_complete") is not False:
        raise ValueError(f"{directory}: not a B2-A5-eval/1 result with benchmark_complete=false")
    return {"directory": directory.name, "sha256": _sha(results), "data": data}


def _view(entry: dict) -> dict:
    if not entry.get("available"):
        return {"available": False, "reason": entry.get("reason")}
    if not entry.get("conditions"):
        return {"available": True, "paired_n": 0, "conditions": None}
    out = {}
    for name in CONDITIONS:
        c = entry["conditions"][name]
        displacement = c.get("residual_displacement_vs_original") or {}
        out[name] = {
            "agreement_with_original_label": _mean(c["agreement_with_original_label"]),
            "prediction_change_vs_original": _mean(c["prediction_change_vs_original"]),
            "max_abs_logit_difference_vs_original": c["max_abs_logit_difference_vs_original"],
            "clean_false_alarm": {"mean": _mean(c["clean_false_alarm"]), "n": _n(c["clean_false_alarm"])},
            "event_detection": {"mean": _mean(c["event_detection"]), "n": _n(c["event_detection"])},
            "residual_total_db_displacement": _mean(displacement.get("residual_total_db")),
            "cancellation_depth_core_db_displacement": _mean(displacement.get("cancellation_depth_core_db")),
            "n_scenes": c["n_scenes"], "n_groups": c["n_groups"]}
    return {"available": True, "paired_n": entry["paired_population"]["n_scenes"], "conditions": out,
            "mask_only_vs_receiver_consistent": entry.get("mask_only_vs_receiver_consistent"),
            "original_selected_accuracy": _mean(entry["original_selected_population"]["accuracy"])}


def summarize(runs: Path) -> dict:
    loaded = [_load(path) for path in sorted(p for p in runs.iterdir() if p.is_dir())]
    if not loaded:
        raise ValueError("no invocation directories found")
    first = loaded[0]["data"]
    identity = lambda d: (d["source"]["known_data_fingerprint"], d["source"]["request_fingerprint"],
                          {k: v.get("checkpoint_sha256") for k, v in d["frozen_models"].items()})
    for item in loaded:
        data = item["data"]
        same_matched = data["source"]["stage"] == "known" or data["source"]["matched_data_fingerprint"]
        if identity(data) != identity(first) and data["source"]["stage"] == first["source"]["stage"] == "known":
            raise ValueError(f"{item['directory']}: identities differ from the first invocation")
        if not same_matched:
            raise ValueError(f"{item['directory']}: matched stage without a matched fingerprint")
    invocations = []
    for item in loaded:
        d = item["data"]
        invocations.append({
            "name": item["directory"], "results_sha256": item["sha256"], "experiment_fingerprint": d["experiment_fingerprint"],
            "stage": d["source"]["stage"], "perturbation": d["configuration"]["perturbation"], "scope": d["configuration"]["scope"],
            "labels": d["configuration"]["labels"], "n_groups": d["configuration"]["n_groups"],
            "populations": d["populations"], "counts": d["counts"], "parity": d["parity_summary"],
            "scenes": [{"scenario_id": s["scenario_id"], "label": s["label"], "status": s["status"], "reason": s["reason"],
                        "co_changed": s["co_changed"], "cross_changed": s["cross_changed"],
                        "residual_recomputed": s["residual_recomputed"], "flags": s["flags"]} for s in d["scenes"]],
            "views": {name: _view(entry) for name, entry in d["views"].items()},
            "elapsed_s": d["cost"]["elapsed_s"], "peak_rss_kib": d["cost"]["peak_rss_kib"]})
    totals = {"invocations": len(invocations), "physical_replays": sum(i["counts"]["physical_replays"] for i in invocations),
              "cancellation_evaluations": sum(i["counts"]["cancellation_evaluations"] for i in invocations),
              "receiver_recomputations": sum(i["counts"]["receiver_recomputations"] for i in invocations),
              "scored_samples": sum(i["counts"]["scored_samples"] for i in invocations),
              "all_parity_exact": all(i["parity"]["all_exact"] in (True, None) for i in invocations),
              "elapsed_s_sum": sum(i["elapsed_s"] for i in invocations),
              "peak_rss_kib_max": max(i["peak_rss_kib"] for i in invocations)}
    return {"contract": "B2-A5-eval/1", "benchmark_complete": False, "evidence_class": "BOUNDED_PILOT",
            "authorization": first["authorization"], "caps": first["caps"],
            "source": {"known_data_fingerprint": first["source"]["known_data_fingerprint"],
                       "request_fingerprint": first["source"]["request_fingerprint"],
                       "matched_data_fingerprints": sorted({i["data"]["source"]["matched_data_fingerprint"] for i in loaded
                                                            if i["data"]["source"]["matched_data_fingerprint"]}),
                       "cancellation": first["source"]["cancellation"], "receiver_calibration": first["source"]["receiver_calibration"]},
            "implementation": first["implementation"], "frozen_models": first["frozen_models"],
            "totals": totals, "invocations": invocations,
            "interpretation": {
                "what_this_is": "bounded execution evidence for replay parity, the receiver-consistent recomputation and the paired data flow",
                "what_this_is_not": ["recognition-quality evidence", "a robustness claim", "population-level false-alarm rates"],
                "checkpoints": "chance-level stand-ins from the documented 3-epoch pilot configuration; their predictions carry no signal",
                "counterfactual_labels": "agreement with the original label is descriptive; accuracy exists only for the stored original condition"}}


def markdown(summary: dict) -> str:
    pct = lambda v: "n/a" if v is None else f"{100 * v:.1f}%"
    num = lambda v: "n/a" if v is None else f"{v:+.2f}"
    lines = ["| Invocation | Applied / selected | Replays | Cancellations | Parity exact | View | Condition | Agreement | Changed | Residual Δ (dB) | Core depth Δ (dB) |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    for inv in summary["invocations"]:
        applied = f"{inv['populations']['applied']} / {inv['populations']['selected']}"
        for view, entry in inv["views"].items():
            if not entry.get("conditions"):
                lines.append(f"| `{inv['name']}` | {applied} | {inv['counts']['physical_replays']} | {inv['counts']['cancellation_evaluations']} | "
                             f"{inv['parity']['all_exact']} | {view} | – | n/a | n/a | n/a | n/a |")
                continue
            for name in ("MASK_ONLY", "RECEIVER_CONSISTENT"):
                c = entry["conditions"][name]
                lines.append(f"| `{inv['name']}` | {applied} | {inv['counts']['physical_replays']} | {inv['counts']['cancellation_evaluations']} | "
                             f"{inv['parity']['all_exact']} | {view} | {name} | {pct(c['agreement_with_original_label'])} | "
                             f"{pct(c['prediction_change_vs_original'])} | {num(c['residual_total_db_displacement'])} | "
                             f"{num(c['cancellation_depth_core_db_displacement'])} |")
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--runs", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--markdown")
    args = parser.parse_args(argv)
    try:
        summary = summarize(Path(args.runs))
    except (ValueError, OSError) as error:
        parser.exit(2, f"error: {error}\n")
    Path(args.out).write_text(json.dumps(summary, indent=1, allow_nan=False) + "\n")
    if args.markdown:
        Path(args.markdown).write_text(markdown(summary))
    print(f"summarized {summary['totals']['invocations']} invocations -> {args.out}")


if __name__ == "__main__":
    main()

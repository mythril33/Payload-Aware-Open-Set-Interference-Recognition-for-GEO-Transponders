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
EXPECTED_INVOCATIONS = ({"known_none_both"}
    | {f"known_{p}_{s}" for p in ("shift_plus", "shift_minus", "drop_one", "phantom", "authorize_intruder", "stale_plan")
       for s in ("co_only", "cross_only", "both")}
    | {f"matched_{p}_{s}" for p in ("drop_one", "phantom", "authorize_intruder") for s in ("co_only", "both")})


def _strict(text):
    def unique(pairs):
        values = {}
        for key, value in pairs:
            if key in values:
                raise ValueError(f"duplicate JSON key: {key}")
            values[key] = value
        return values
    def reject(value):
        raise ValueError(f"nonfinite JSON constant: {value}")
    value = json.loads(text, object_pairs_hook=unique, parse_constant=reject)
    json.dumps(value, allow_nan=False)  # also rejects overflowed JSON exponents
    return value


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
    data = _strict(results.read_text())
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
            "alarm_among_original_clean": {"mean": _mean(c["clean_false_alarm"]), "n": _n(c["clean_false_alarm"])},
            "alarm_among_original_event": {"mean": _mean(c["event_detection"]), "n": _n(c["event_detection"])},
            "residual_total_db_displacement": _mean(displacement.get("residual_total_db")),
            "cancellation_depth_core_db_displacement": _mean(displacement.get("cancellation_depth_core_db")),
            "asi_vs_unauthorized": c.get("asi_vs_unauthorized"),
            "score_displacement": c.get("score_displacement"),
            "agreement_counts_and_group_ci": c["agreement_with_original_label"],
            "n_scenes": c["n_scenes"], "n_groups": c["n_groups"]}
    return {"available": True, "paired_n": entry["paired_population"]["n_scenes"], "conditions": out,
            "mask_only_vs_receiver_consistent": entry.get("mask_only_vs_receiver_consistent"),
            "original_selected_accuracy": _mean(entry["original_selected_population"]["accuracy"])}


def _baselines(data: dict) -> dict | None:
    methods = (data.get("baselines") or {}).get("methods")
    if not methods:
        return None
    out = {}
    for name, entry in methods.items():
        if not entry.get("available"):
            out[name] = {"available": False, "reason": entry.get("reason"), "reads": entry["reads"]}
            continue
        item = {"available": True, "reads": entry["reads"]}
        for condition, values in entry["displacement_vs_original"].items():
            if name == "xgboost_features_26":
                item[condition] = {"n_features_changed": values["n_features_changed"], "n_features": values["n_features"]}
            elif name.startswith("ca_cfar"):
                item[condition] = {"n_scenes_changed": max(v["n_scenes_changed"] for v in values.values())}
            else:
                item[condition] = {"mean_displacement_db": _mean(values["displacement_db"]), "n_scenes_changed": values["n_scenes_changed"]}
        out[name] = item
    return out


def _identity(data: dict) -> dict:
    """Everything that must be shared by every invocation of one pilot (stage-specific parts are compared per stage)."""
    return {"known_data_fingerprint": data["source"]["known_data_fingerprint"],
            "receiver_calibration": data["source"]["receiver_calibration"], "cancellation": data["source"]["cancellation"],
            "checkpoints": {k: v.get("checkpoint_sha256") for k, v in data["frozen_models"].items()},
            "runs_config": data["experiment_reference"]["runs_config"],
            "e4_source_files_sha256": data["implementation"]["e4_source_files_sha256"],
            "source_tree_fingerprint": data["implementation"]["source_tree_fingerprint"],
            "frozen_run_files_sha256": data["implementation"]["frozen_run_files_sha256"],
            "git_sha": data["implementation"]["git_sha"], "caps": data["caps"]}


def summarize(runs: Path, checkpoint_note: str = "supplied by the run directory; not characterized by this summary") -> dict:
    loaded = [_load(path) for path in sorted(p for p in runs.iterdir() if p.is_dir())]
    if not loaded:
        raise ValueError("no invocation directories found")
    coverage = {"matrix_status": "UNINVENTORIED", "matrix_complete": False,
                "reason": "No matrix_status.json; invocation files alone do not establish complete coverage"}
    manifest = runs / "matrix_status.json"
    if manifest.exists():
        coverage = _strict(manifest.read_text())
        if coverage.get("schema") != "B2-A5-matrix-status/1" or coverage.get("benchmark_complete") is not False:
            raise ValueError("foreign matrix manifest")
        entries = coverage["invocations"]
        if {item["name"] for item in entries} != EXPECTED_INVOCATIONS:
            raise ValueError("matrix manifest does not inventory all 25 canonical invocations")
        completed = {item["name"]:item for item in entries if item["status"] == "completed"}
        if len({item["name"] for item in entries}) != len(entries) or set(completed) != {item["directory"] for item in loaded}:
            raise ValueError("matrix inventory/completed invocation population differs from results")
        for item in loaded:
            recorded = completed[item["directory"]]
            data = item["data"]
            canonical = f"{data['source']['stage']}_{data['configuration']['perturbation']}_{data['configuration']['scope']}"
            if item["directory"] != canonical:
                raise ValueError("matrix invocation name differs from result configuration")
            if (recorded["results_sha256"] != item["sha256"]
                    or recorded["experiment_fingerprint"] != item["data"]["experiment_fingerprint"]):
                raise ValueError("matrix result checksum or experiment provenance differs")
        if coverage.get("matrix_complete") != (len(completed) == len(entries)):
            raise ValueError("matrix completion flag disagrees with its inventory")
        if (coverage.get("matrix_status") == "COMPLETE") != coverage["matrix_complete"]:
            raise ValueError("matrix completion status disagrees with its inventory")
        actual = {"inventory": len(entries), "completed": len(completed),
                  "failed": sum(e["status"] == "failed" for e in entries),
                  "missing": sum(e["status"] == "missing" for e in entries),
                  "pending": sum(e["status"] in ("pending", "running", "skipped", "blocked_budget") for e in entries)}
        if any(coverage.get("totals", {}).get(k) != n for k,n in actual.items()):
            raise ValueError("matrix totals disagree with its inventory")
        coverage = {**coverage, "manifest_sha256": _sha(manifest)}
    first = loaded[0]["data"]
    reference, per_stage = _identity(first), {}
    for item in loaded:
        data = item["data"]
        if _identity(data) != reference:
            raise ValueError(f"{item['directory']}: shared identities (known data, checkpoints, calibration, cancellation, "
                             "run config, source) differ from the first invocation")
        stage_identity = (data["source"]["request_fingerprint"], data["source"]["matched_data_fingerprint"])
        if per_stage.setdefault(data["source"]["stage"], stage_identity) != stage_identity:
            raise ValueError(f"{item['directory']}: {data['source']['stage']}-stage request/artifact identity differs "
                             "within the stage")
        if data["source"]["stage"] == "matched" and not stage_identity[1]:
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
            "views": {name: _view(entry) for name, entry in d["views"].items()}, "baseline_inputs": _baselines(d),
            "resume": d["resume"], "elapsed_s": d["cost"]["elapsed_s"], "peak_rss_kib": d["cost"]["peak_rss_kib"]})
    checked = [i for i in invocations if i["parity"]["all_exact"] is not None]
    totals = {"invocations": len(invocations), "physical_replays": sum(i["counts"]["physical_replays"] for i in invocations),
              "cancellation_evaluations": sum(i["counts"]["cancellation_evaluations"] for i in invocations),
              "receiver_recomputations": sum(i["counts"]["receiver_recomputations"] for i in invocations),
              "scored_samples": sum(i["counts"]["scored_samples"] for i in invocations),
              "invocations_with_parity_check": len(checked), "invocations_without_parity_check": len(invocations) - len(checked),
              "all_checked_parity_exact": all(i["parity"]["all_exact"] for i in checked) if checked else None,
              "scenes_parity_checked": sum(i["parity"]["n_scenes_checked"] for i in invocations),
              "elapsed_s_sum": sum(i["elapsed_s"] for i in invocations),
              "peak_rss_kib_max": max(i["peak_rss_kib"] for i in invocations)}
    return {"contract": "B2-A5-eval/1", "benchmark_complete": False, "evidence_class": "BOUNDED_PILOT",
            "authorization": first["authorization"], "caps": first["caps"],
            "source": {"known_data_fingerprint": first["source"]["known_data_fingerprint"],
                       "stage_identities": {stage: {"request_fingerprint": ids[0], "matched_data_fingerprint": ids[1]}
                                            for stage, ids in sorted(per_stage.items())},
                       "cancellation": first["source"]["cancellation"], "receiver_calibration": first["source"]["receiver_calibration"]},
            "implementation": {"git_sha": first["implementation"]["git_sha"],
                               "source_tree_fingerprint": first["implementation"]["source_tree_fingerprint"],
                               "e4_source_files_sha256": first["implementation"]["e4_source_files_sha256"]},
            "frozen_models": first["frozen_models"], "totals": totals, "invocations": invocations,
            "matrix_coverage": coverage,
            "interpretation": {
                "what_this_is": "bounded execution evidence for replay parity, the receiver-consistent recomputation and the paired data flow",
                "what_this_is_not": ["recognition-quality evidence", "a robustness claim", "population-level false-alarm rates"],
                "checkpoints": checkpoint_note,
                "counterfactual_labels": "agreement with the original label is descriptive; accuracy exists only for the stored original condition; "
                                         "alarm columns are rates among scenes whose ORIGINAL label is clean / not clean"}}


def markdown(summary: dict) -> str:
    pct = lambda v: "n/a" if v is None else f"{100 * v:.1f}%"
    num = lambda v: "n/a" if v is None else f"{v:+.2f}"
    receiver = ["| Invocation | Applied / selected | Replays | Cancellations | Parity exact | Core depth Δ (dB) | Residual Δ (dB) | EDSC score Δ MASK_ONLY / RC (dB) | CFAR planned scenes changed | CFAR blind scenes changed | XGB features changed MASK_ONLY / RC |",
                "|---|---|---|---|---|---|---|---|---|---|---|"]
    model = ["| Invocation | View | Condition | n | Agreement | Changed | max abs Δlogit | Alarm among original-clean | Alarm among original-event |",
             "|---|---|---|---|---|---|---|---|---|"]
    for inv in summary["invocations"]:
        applied = f"{inv['populations']['applied']} / {inv['populations']['selected']}"
        views = [v for v in inv["views"].values() if v.get("conditions")]
        rc = views[0]["conditions"]["RECEIVER_CONSISTENT"] if views else None
        b = inv["baseline_inputs"] or {}
        edsc = b.get("edsc_score_db", {})
        edsc_cell = "n/a" if not edsc.get("available") else f"{num(edsc['MASK_ONLY']['mean_displacement_db'])} / {num(edsc['RECEIVER_CONSISTENT']['mean_displacement_db'])}"
        cfar = lambda name: "n/a" if not b.get(name, {}).get("available") else str(b[name]["RECEIVER_CONSISTENT"]["n_scenes_changed"])
        xgb = b.get("xgboost_features_26", {})
        xgb_cell = "n/a" if not xgb.get("available") else f"{xgb['MASK_ONLY']['n_features_changed']} / {xgb['RECEIVER_CONSISTENT']['n_features_changed']} of {xgb['RECEIVER_CONSISTENT']['n_features']}"
        receiver.append(f"| `{inv['name']}` | {applied} | {inv['counts']['physical_replays']} | {inv['counts']['cancellation_evaluations']} | "
                        f"{inv['parity']['all_exact']} | {'n/a' if rc is None else num(rc['cancellation_depth_core_db_displacement'])} | "
                        f"{'n/a' if rc is None else num(rc['residual_total_db_displacement'])} | {edsc_cell} | {cfar('ca_cfar_planned')} | "
                        f"{cfar('ca_cfar_blind')} | {xgb_cell} |")
        for view, entry in inv["views"].items():
            if not entry.get("conditions"):
                model.append(f"| `{inv['name']}` | {view} | – | 0 | n/a | n/a | n/a | n/a | n/a |")
                continue
            for name in ("original", "MASK_ONLY", "RECEIVER_CONSISTENT"):
                c = entry["conditions"][name]
                logit = "n/a" if c["max_abs_logit_difference_vs_original"] is None else f"{c['max_abs_logit_difference_vs_original']:.4f}"
                model.append(f"| `{inv['name']}` | {view} | {name} | {c['n_scenes']} | {pct(c['agreement_with_original_label'])} | "
                             f"{pct(c['prediction_change_vs_original'])} | {logit} | {pct(c['alarm_among_original_clean']['mean'])} (n={c['alarm_among_original_clean']['n']}) | "
                             f"{pct(c['alarm_among_original_event']['mean'])} (n={c['alarm_among_original_event']['n']}) |")
    coverage = summary["matrix_coverage"]
    counts = coverage.get("totals", {})
    banner = (f"Matrix coverage: **{coverage['matrix_status']}**; complete={coverage['matrix_complete']}; "
              f"completed={counts.get('completed', 'unknown')}/{counts.get('inventory', 'unknown')}, "
              f"pending={counts.get('pending', 'unknown')}, failed={counts.get('failed', 'unknown')}, "
              f"missing={counts.get('missing', 'unknown')}. Unexecuted invocation slots are not non-applicable samples.\n\n")
    return (banner + "### Receiver-level and baseline-input displacement (model independent; RC = RECEIVER_CONSISTENT)\n\n" + "\n".join(receiver)
            + "\n\n### Model-level paired conditions (frozen checkpoints supplied by the run directory; see the summary's interpretation block for what they are)\n\n" + "\n".join(model) + "\n")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--runs", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--markdown")
    parser.add_argument("--checkpoint-note", default="supplied by the run directory; not characterized by this summary",
                        help="what the frozen checkpoints are (written into the interpretation block)")
    args = parser.parse_args(argv)
    try:
        summary = summarize(Path(args.runs), args.checkpoint_note)
    except (ValueError, OSError) as error:
        parser.exit(2, f"error: {error}\n")
    Path(args.out).write_text(json.dumps(summary, indent=1, allow_nan=False) + "\n")
    if args.markdown:
        Path(args.markdown).write_text(markdown(summary))
    print(f"summarized {summary['totals']['invocations']} invocations -> {args.out}")


if __name__ == "__main__":
    main()

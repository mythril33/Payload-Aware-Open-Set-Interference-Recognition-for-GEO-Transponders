"""Ordered evaluation of the fifteen frozen B2 fits; no fitting or calibration.

The caller supplies the existing held-out authority and journal custody ports.
This module supplies neither approvals nor a bypass around the fixture caps.
Completion describes one evaluated profile, not a completed research benchmark.
"""
from __future__ import annotations

from dataclasses import asdict
import importlib.util
from pathlib import Path

import numpy as np

from geosim.b2_protocol import LABELS, scenario_ids
from geosim.b2_scenarios import MATCHED_LABELS, TEST_FAMILIES
from . import b2_campaign as campaign_api
from . import b2_execution as kernels
from . import b2_experiment as ex
from . import b2_production_training as production
from .artifacts import fingerprint
from .b2_stream import infer_streaming
from .calibration import RejectionCalibration
from .experiment import _sha256, _source_identity, _write_json
from .metrics import confusion, expected_calibration_error, macro_f1
from .openset import unknown_scores

CONTRACT = "B2-production-evaluation/1"
ROOT = Path(__file__).resolve().parents[2]


def _metadata_check(data, common):
    """Cross-check the actual generation metadata before opening observations."""
    manifest = kernels._known_header(Path(data))[0]
    if fingerprint(manifest) != common["data_identity"]:
        raise ValueError("known metadata differs from the frozen campaign")
    production._role_plan(manifest)
    spec = importlib.util.spec_from_file_location(
        "b2_evaluation_metadata", ROOT / "scripts/b2_e14_verify_metadata.py")
    verifier = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verifier)
    # The manifest is bound to the verified training inventory, not an arbitrary
    # caller-supplied metadata document or a list selected after seeing scores.
    report = verifier.verify_production_metadata(data, binding={
        "schema": verifier.BINDING_SCHEMA, "source_head": manifest["commit"],
        "request": manifest["request"],
        "request_fingerprint": manifest["request_fingerprint"]})
    identity_path = ROOT / verifier.IDENTITY
    identity = kernels._strict(identity_path)
    if (_sha256(identity_path) != report["identity_sha256"]
            or report["production_cross_verification_performed"] is not True
            or report["metadata_status"] != "ACCEPTED_IDENTITY_METADATA_MATCH"):
        raise ValueError("production K17d identity was not verified")
    decisions_path = ROOT / verifier.ACCEPTANCE
    if _sha256(decisions_path) != report["acceptance_record_sha256"]:
        raise ValueError("scientific acceptance changed during metadata verification")
    d1 = kernels._strict(decisions_path)["decisions"]["D-1"]
    return {"verification": report, "co_feed_missing_ids": identity["co_feed_missing_ids"],
            "sensitivity_ids": identity["sensitivity_ids"],
            "excluded_test_ids": d1["exposed_test_ids"],
            "excluded_matched_ids": d1["exposed_matched_ids"]}


def _population(source, kind, role, variants, *, field="label"):
    groups = scenario_ids(role)
    expected = {(group, label) for group in groups for label in variants}
    actual = list(zip(source.index["seed"].tolist(), source.index[field].tolist()))
    if (source.kind != kind or source.role != role or not source.has_residual
            or source.groups.tolist() != groups or len(source) != len(expected)
            or len(actual) != len(expected) or set(actual) != expected):
        raise ValueError(f"{kind} population must contain every frozen group/variant exactly once")


def _open_sources(data, unknown_data, matched_data, frozen, config):
    identity, roles, sources, parts = production._open(
        data, ("test",), frozen["common"]["data_identity"])
    if roles != frozen["common"]["roles"]:
        raise ValueError("test roles differ from the frozen inventory")
    manifest = kernels._known_header(Path(data))[0]
    if fingerprint(manifest) != identity:
        raise ValueError("known manifest changed while opening test data")
    known = sources["test"]
    _population(known, "known", "test", range(len(LABELS)))
    um, ui, unknown = ex._load_unknown(unknown_data, manifest, identity, config)
    mm, mi, matched = ex._load_matched(matched_data, manifest, identity, config)
    _population(unknown, "test", "test", range(len(TEST_FAMILIES)), field="family")
    _population(matched, "matched", "test-matched", [LABELS.index(v) for v in MATCHED_LABELS])
    if tuple(unknown.split()["families"]) != TEST_FAMILIES:
        raise ValueError("test-only family names/order differ from the frozen contract")
    artifacts = {name: kernels._evaluation_artifact(name, m, i, s)
                 for name, m, i, s in (("known", manifest, identity, known),
                                      ("test_only", um, ui, unknown), ("matched", mm, mi, matched))}
    return (known, unknown, matched), (parts["test"], unknown.split(), matched.split()), artifacts


def _outputs(fitted, source):
    values = infer_streaming(fitted, source)
    for name in ("logits", "embedding", "plan_logits"):
        value = values[name]
        if value is None and name == "plan_logits":
            continue
        if (not isinstance(value, np.ndarray) or value.ndim != 2
                or len(value) != len(source) or not np.isfinite(value).all()):
            raise ValueError(f"invalid/nonfinite {name} inference output")
    if values["logits"].shape[1] != len(LABELS):
        raise ValueError("inference output does not cover the eight frozen classes")
    return values


def _take(part, mask):
    n = len(mask)
    return {key: (value[mask] if isinstance(value, np.ndarray) and len(value) == n
                  else [item for item, selected in zip(value, mask) if selected]
                  if key == "meta" else value) for key, value in part.items()}


def _take_outputs(outputs, mask):
    return {key: None if value is None else value[mask] for key, value in outputs.items()}


def _scores(outputs, scorer, method):
    values = (scorer.score(outputs["embedding"]) if method == "mahalanobis"
              else unknown_scores(outputs["logits"], method))
    if values.shape != (len(outputs["logits"]),) or not np.isfinite(values).all():
        raise ValueError("invalid/nonfinite unknown scores")
    return values


def _known_metrics(known, values, unknown, unknown_values, calibrations, scorer, alarm):
    labels, groups = known["label"], known["seed"]
    probabilities = ex._softmax(values["logits"])
    predicted = values["logits"].argmax(1)
    event = kernels.clean_alarm_score(probabilities) > alarm["threshold"]
    clean = labels == 0
    rejection = {}
    for method, calibration in calibrations.items():
        families = {"scores": _scores(unknown_values, scorer, method), "groups": unknown["seed"],
                    "info": ex._unknown_families(unknown),
                    "predictions": unknown_values["logits"].argmax(1)}
        rejection[method] = kernels._rejection_metrics(
            calibration, _scores(values, scorer, method), labels, predicted, groups, families)
    return {"accuracy": ex._rate(predicted == labels, groups),
            "macro_f1": macro_f1(labels, predicted, len(LABELS)),
            "confusion": confusion(labels, predicted, len(LABELS)).tolist(),
            "ece": expected_calibration_error(probabilities, labels, 15),
            "per_class_recall": {name: ex._rate((predicted == labels)[labels == i], groups[labels == i])
                                 for i, name in enumerate(LABELS)},
            "clean_false_alarm": ex._rate(event[clean], groups[clean]),
            "event_detection": ex._rate(event[~clean], groups[~clean]),
            "alarm": alarm, "rejection": rejection,
            "plan_consistency": ex._plan_metrics(values["plan_logits"], known["plan_consistency"], groups)}


def _subgroups(parts, outputs, calibrations, scorer, alarm, metadata):
    known, unknown, matched = parts
    values, uv, mv = outputs
    definitions = {
        "d1_exposure_excluded": (sorted(set(scenario_ids("test")) - set(metadata["excluded_test_ids"])), 498),
        "k17d_co_feed_missing": (metadata["co_feed_missing_ids"], 35),
        "k17d_excluding_co_feed_missing": (metadata["sensitivity_ids"], 465)}
    rows = {}
    for name, (ids, count) in definitions.items():
        if len(ids) != count or len(set(ids)) != count or not set(ids) <= set(scenario_ids("test")):
            raise ValueError("invalid predeclared sensitivity population")
        k, u = np.isin(known["seed"], ids), np.isin(unknown["seed"], ids)
        kp, kv = _take(known, k), _take_outputs(values, k)
        row = {"scenario_ids": ids, "n_groups": count, "n_known": int(k.sum()),
               "n_test_only": int(u.sum()), "metrics": _known_metrics(
                   kp, kv, _take(unknown, u), _take_outputs(uv, u), calibrations, scorer, alarm)}
        if name == "d1_exposure_excluded":
            ids_m = sorted(set(scenario_ids("test-matched")) - set(metadata["excluded_matched_ids"]))
            if len(ids_m) != 148:
                raise ValueError("D-1 matched sensitivity must retain 148 groups")
            m = np.isin(matched["seed"], ids_m)
            row["matched_scenario_ids"] = ids_m
            row["matched"] = _matched_metrics(_take(matched, m), _take_outputs(mv, m),
                calibrations, scorer, alarm["threshold"], kp, kv["logits"].argmax(1))
        rows[name] = row
    return rows


def _matched_metrics(matched, outputs, calibrations, scorer, threshold, natural, predictions):
    """Use the frozen D-6 alarm arithmetic for both aggregates and saved events.

    The historical matched kernel computes 1 - P(clean). At very small scores
    that loses precision relative to sum(P(non-clean)), used in calibration.
    Keep the historical source unchanged and replace its two alarm summaries.
    """
    result = ex._matched_metrics(matched, outputs, calibrations, scorer, threshold, natural, predictions)
    alarm = kernels.clean_alarm_score(ex._softmax(outputs["logits"])) > threshold
    clean, groups = matched["label"] == 0, matched["seed"]
    result["clean_false_alarm"] = ex._rate(alarm[clean], groups[clean])
    result["event_alarm"] = ex._rate(alarm[~clean], groups[~clean])
    result["conventions"]["event_alarm"] = "sum(P(non-clean)) > frozen clean-val-calib threshold (D-6)"
    return result


def _prediction_record(part, values, scorer, calibrations, alarm, *, family=False):
    key = "family" if family else "label"
    event = kernels.clean_alarm_score(ex._softmax(values["logits"]))
    row = {"sample_ids": [[int(g), int(v)] for g, v in zip(part["seed"], part[key])],
           "prediction": values["logits"].argmax(1).tolist(),
           "event_probability": event.tolist(), "alarm": (event > alarm["threshold"]).tolist(),
           "scores": {m: _scores(values, scorer, m).tolist() for m in calibrations}}
    if family:
        row["families"] = list(part["families"])
    else:
        row["plan_consistency"] = part["plan_consistency"].tolist()
    if "matched_bin" in part:
        row["matched_bin"] = part["matched_bin"].tolist()
    return row


def evaluate_campaign_profile(data, campaign, out, *, unknown_data, matched_data,
                              profile, device="cpu", authorization=None, journal=None, log=print):
    """Evaluate one frozen nine/six-fit profile, once, in the declared order.

    No output is complete unless the external journal records completion. A
    failed/partial read is consumed by evaluation_step and cannot be retried.
    All three data stages are mandatory. Caller must retain immutable input roots.
    """
    if profile not in campaign_api.ORDER:
        raise ValueError("evaluation profile must be proposed-full or c2-h3-dual")
    if authorization is None or journal is None:
        raise production.AuthorizationRequired("heldout authority and journal custody are required")
    if unknown_data is None or matched_data is None:
        raise ValueError("full evaluation requires known, test-only and matched artifacts")
    out, campaign = Path(out).resolve(), Path(campaign).resolve()
    if out == ROOT or ROOT in out.parents:
        raise ValueError("observation-level evaluation outputs must stay outside the repository")
    if out.exists():
        raise ValueError("evaluation output must be fresh; no partial-read reuse")
    frozen_campaign = campaign_api.verify_campaign(campaign)
    if frozen_campaign["scope"] != "PRODUCTION":
        raise ValueError("production evaluation rejects bounded-fixture campaigns")
    roots = [Path(cell["path"]) for cell in frozen_campaign["inventories"]]
    inventories = {i["profile"]: production.verify_inventory(i["path"], i["profile"])
                   for i in frozen_campaign["inventories"]}
    model_roots = {Path(c["runs"]).resolve() for v in inventories.values() for c in v["cells"]}
    kernels._separate(out, [campaign, *roots, *model_roots, data, unknown_data, matched_data])
    campaign_hash = _sha256(campaign)
    # The existing context independently verifies all fifteen fits again, obtains
    # heldout authority, locks external custody and consumes this profile read.
    with campaign_api.evaluation_step(campaign, profile, authorization=authorization, journal=journal) as (bound, binding):
        if bound != frozen_campaign:
            raise ValueError("campaign changed before evaluation admission")
        if device != "cpu":
            production._require(authorization, "gpu_qualification", bound["artifact_id"])
            production._require(authorization, "gpu_evaluation", bound["artifact_id"])
        with production.r6_fp32():
            runtime = production.runtime_identity(device)
            if runtime != bound["common"]["runtime"]:
                raise ValueError("evaluation runtime differs from the frozen training environment")
            if _source_identity()["files_sha256"] != bound["common"]["source"]:
                raise ValueError("evaluation source differs from the frozen training source")
            metadata = _metadata_check(data, bound["common"])
            frozen = inventories[profile]
            cfg = production._config({**frozen["common"]["config"], "views": production.PROFILES[profile],
                "training": {**frozen["common"]["config"]["training"], "seed": 0}})
            sources, parts, artifacts = _open_sources(data, unknown_data, matched_data, frozen, cfg)
            models, predictions = [], []
            bundles = {}
            for cell in frozen["cells"]:
                root, view = Path(cell["runs"]), cell["view"]
                if root not in bundles:
                    trained, config, loaded = production._training(root, device)
                    calibrated = production._calibration(root)[0]
                    bundles[root] = trained, config, loaded, calibrated
                trained, config, loaded, calibrated = bundles[root]
                fitted, scorer = loaded[view]
                outputs = tuple(_outputs(fitted, source) for source in sources)
                calibrations = {m: RejectionCalibration.from_dict(c)
                                for m, c in calibrated["views"][view]["rejection"].items()}
                alarm = calibrated["views"][view]["alarm"]
                metrics = _known_metrics(parts[0], outputs[0], parts[1], outputs[1], calibrations, scorer, alarm)
                metrics["matched"] = _matched_metrics(parts[2], outputs[2], calibrations, scorer,
                    alarm["threshold"], parts[0], outputs[0]["logits"].argmax(1))
                metrics["sensitivity"] = _subgroups(parts, outputs, calibrations, scorer, alarm, metadata)
                models.append({"seed": cell["seed"], "view": view,
                    "checkpoint_sha256": trained["files"][f"model_{view}.pt"],
                    "training": asdict(config.train_config(view)), "metrics": metrics})
                known = _prediction_record(parts[0], outputs[0], scorer, calibrations, alarm)
                known["unknown_scores"] = known.pop("scores")
                predictions.append({"seed": cell["seed"], "view": view, **known,
                    "unknown_families": _prediction_record(parts[1], outputs[1], scorer, calibrations, alarm, family=True),
                    "matched": _prediction_record(parts[2], outputs[2], scorer, calibrations, alarm)})
                log(f"evaluated seed={cell['seed']} view={view}")
            # Revalidate every source/artifact/runtime before publishing payloads.
            if (_sha256(campaign) != campaign_hash or campaign_api.verify_campaign(campaign) != bound
                    or production.runtime_identity(device) != runtime
                    or _metadata_check(data, bound["common"]) != metadata):
                raise ValueError("frozen inputs changed during evaluation")
            if _open_sources(data, unknown_data, matched_data, frozen, cfg)[2] != artifacts:
                raise ValueError("evaluation artifact identity changed during inference")
            result = {"contract": CONTRACT, "scope": "PRODUCTION", "benchmark_complete": False,
                "profile": profile, "campaign_id": bound["artifact_id"], "campaign_sha256": campaign_hash,
                "primary_scorer": bound["primary_scorer"], "campaign": bound,
                "inventory_sha256": binding["sha256"],
                "inventory_cells": len(models), "data_identity": frozen["common"]["data_identity"],
                "source": _source_identity(), "runtime": runtime, "evaluation_artifacts": artifacts,
                "metadata_verification": metadata, "partitions": ex._summary({"test": parts[0]}),
                "models": models, "score_direction": "higher_is_more_unknown_like",
                "positive_class": "unknown", "limitations": [
                    "One completed profile is not a completed benchmark; both profiles and contrasts are required.",
                    "All test observations have historical exposure obligations; 498/148 and 35/465 rows are separate.",
                    "Rate intervals are conditional on the frozen model/threshold; no training/calibration uncertainty."]}
            out.mkdir(parents=True, exist_ok=False)
            _write_json(out / "predictions.json", predictions)
            _write_json(out / "results.json", result)
            production._sync(out)
    # This marker can only follow the journal's successful durable completion.
    completion = {"contract": CONTRACT, "scope": "PRODUCTION", "benchmark_complete": False,
        "campaign_id": result["campaign_id"], "profile": profile,
        "results_sha256": _sha256(out / "results.json"),
        "predictions_sha256": _sha256(out / "predictions.json"),
        "evaluation_artifacts_sha256": fingerprint(artifacts), "journal_completion_recorded": True}
    _write_json(out / "completion.json", completion)
    production._sync(out)
    return result

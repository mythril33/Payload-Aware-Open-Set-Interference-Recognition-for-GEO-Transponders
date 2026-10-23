"""Render measured B2 pilot evidence; never simulate, fit, calibrate or pool fixtures.

python scripts/plot_b2_scientific_results.py
Optional offline extraction from an existing verified artifact:
python scripts/plot_b2_scientific_results.py --extract-physical data/b2-readiness-known
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
import platform
import textwrap

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "docs/results"
LOCK = RESULTS / "b2_figure_sources.json"
E4 = "b2_a5_dual_pol_pilot.json"
MODES = ("MASK_ONLY", "RECEIVER_CONSISTENT")
SCOPES = ("co_only", "cross_only", "both")
PERTURBATIONS = ("none", "shift_plus", "shift_minus", "drop_one", "phantom",
                 "authorize_intruder", "stale_plan")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def strict_json(path):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result
    def invalid(value):
        raise ValueError(f"nonfinite JSON: {value}")
    def finite(value):
        number = float(value)
        if not math.isfinite(number):
            return invalid(value)
        return number
    return json.loads(Path(path).read_text(), object_pairs_hook=pairs, parse_constant=invalid, parse_float=finite)


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def extract_physical(root, destination):
    """Small plot summary, not a dataset: 16x128 power-pooled display tiles.

    Selection precedes inspection: lowest test scenario id, clean and CuC.
    Truth is used only to name the two offline diagnostic panels.
    """
    from geosim.b2_dataset import read_b2_manifest, iter_b2_shards, b2_fingerprint
    from geosim.b2_protocol import LABELS
    root = Path(root)
    manifest = read_b2_manifest(root)  # validates all shards, metadata and calibration
    if manifest["protocol"] != "B2-feat/1" or manifest["cancellation"]["version"] != "obs-cancel/1":
        raise ValueError("physical plots require verified P20 obs-cancel/1")
    group = min(manifest["roles"]["test"]["scenario_seeds"])
    records = []
    for shard in iter_b2_shards(root, "test"):
        for i, seed in enumerate(shard["seed"]):
            name = LABELS[int(shard["label"][i])]
            if int(seed) != group or name not in ("clean", "carrier_under_carrier"):
                continue
            spec = shard["spec"][i].astype(np.float64)
            residual = shard["residual"][i].astype(np.float64)
            power = 10 ** (spec / 10)
            tiles = 10 * np.log10(power.reshape(2, 16, 8, 128, 4).mean(axis=(2, 4)))
            records.append({"label": name, "scenario_id": group,
                            "spectrogram_db": tiles.tolist(),
                            "mean_psd_db": (10 * np.log10(power.mean(axis=1))).tolist(),
                            "mean_residual_db": (10 * np.log10((10 ** (residual / 10)).mean(axis=0))).tolist(),
                            "operator_mask_db": shard["mask"][i].astype(float).tolist()})
    if len(records) != 2:
        raise ValueError("missing paired physical observations")
    sources = [root / "manifest.json", root / "request.json", root / "receiver_calibration.npz"]
    for desc in manifest["roles"]["test"]["shards"]:
        if group in desc["scenario_seeds"]:
            sources += [root / "test" / desc["part"], root / "test" / desc["meta"]]
    write_json(destination, {"schema": "B2-physical-plot-summary/1", "benchmark_complete": False,
               "evidence_class": "BOUNDED_PILOT", "stage": "B2-feat/1", "role": "test",
               "data_fingerprint": b2_fingerprint(root), "n_scenes": 2, "n_groups": 1,
               "cancellation": manifest["cancellation"], "selection": "lowest test group, clean and CuC",
               "derivation": "linear-power means: tiles pool 8 snapshots x 4 bins; curves pool time only; no interpolation",
               "frequency_mhz": ((np.arange(512) - 256) * 96 / 512).tolist(),
               "frequency_edges_mhz": [-48.09375, 47.90625],
               "snapshot_interval_s": manifest["config"]["snap_interval"],
               "sources": [{"path": str(p.relative_to(ROOT)), "sha256": sha(p)} for p in sources],
               "extraction_command": f"python scripts/plot_b2_scientific_results.py --extract-physical {root.relative_to(ROOT)}",
               "records": sorted(records, key=lambda x: x["label"])})


class Atlas:
    def __init__(self, output, manifest, only=None):
        self.output, self.manifest_path = Path(output), Path(manifest)
        self.output.mkdir(parents=True, exist_ok=True)
        self.lock = strict_json(LOCK)
        self.figures = []
        self.only = only
        self.versions = {"python": platform.python_version(), **{
            name: importlib.metadata.version(name) for name in ("numpy", "matplotlib", "scipy", "pillow")}}
        plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9,
                             "axes.spines.top": False, "axes.spines.right": False,
                             "svg.hashsalt": "B2-E5-atlas/1", "pdf.fonttype": 42,
                             "savefig.dpi": 300})

    def read(self, name):
        path = RESULTS / name
        expected = self.lock["sources"][name]
        if sha(path) != expected:
            raise ValueError(f"source SHA-256 mismatch: {name}")
        return strict_json(path)

    def emit(self, ident, fig, *, sources, stage, role, n_scenes, n_groups,
             units, values, caption, identity, evidence="BOUNDED_PILOT", model="none"):
        if self.only and ident not in self.only:
            plt.close(fig)
            return
        # No timestamps, absolute directories, Git HEAD or random IDs in outputs.
        fig.suptitle(ident + " | " + evidence, fontsize=12)
        fig.text(.5, .015, textwrap.fill(caption, width=115), ha="center", va="bottom", fontsize=8)
        fig.tight_layout(rect=(0, .13, 1, .95))
        outputs = []
        for ext in ("png", "svg", "pdf"):
            path = self.output / (ident + "." + ext)
            metadata = ({"Date": None} if ext == "svg" else
                        {"CreationDate": None, "ModDate": None} if ext == "pdf" else {})
            fig.savefig(path, dpi=300, metadata=metadata)
            outputs.append({"path": path.name, "sha256": sha(path), "bytes": path.stat().st_size})
        plt.close(fig)
        self.figures.append({"id": ident, "evidence_class": evidence, "dataset_stage": stage,
            "role": role, "n_scenes": n_scenes, "n_groups": n_groups, "units": units,
            "dataset_identity": identity, "model_status": model, "caption": caption,
            "uncertainty": "none displayed; descriptive measured values only",
            "sources": [{"path": "docs/results/" + name, "sha256": self.lock["sources"][name]} for name in sources],
            "plotted_values": values, "outputs": outputs, "png_dpi": 300,
            "regeneration_command": "python scripts/plot_b2_scientific_results.py",
            "package_versions": self.versions})

    def finish(self):
        write_json(self.manifest_path, {"schema": "B2-scientific-figure-manifest/1",
            "benchmark_complete": False, "production_authorized": False,
            "script_sha256": sha(__file__), "source_lock_sha256": sha(LOCK),
            "regeneration_command": "python scripts/plot_b2_scientific_results.py",
            "rendering": "Agg; DejaVu Sans; fixed SVG salt; no timestamps; PNG 300 dpi; vector SVG/PDF",
            "package_versions": self.versions, "figures": self.figures})


def heat(ax, data, rows, cols, title, unit, *, diverging=False, limit=None):
    arr = np.array([[np.nan if v is None else v for v in row] for row in data], float)
    bound = limit if limit is not None else (float(np.nanmax(np.abs(arr))) or 1)
    cmap = plt.get_cmap("RdBu_r" if diverging else "viridis").copy()
    cmap.set_bad("#dddddd")
    im = ax.imshow(np.ma.masked_invalid(arr), aspect="auto", interpolation="none", cmap=cmap,
                   vmin=-bound if diverging else 0, vmax=bound)
    ax.set(xticks=range(len(cols)), xticklabels=cols, yticks=range(len(rows)), yticklabels=rows, title=title)
    for i in range(len(rows)):
        for j in range(len(cols)):
            v = arr[i, j]
            label = "N/A" if np.isnan(v) else f"{v:.2g}"
            rgba = im.cmap(im.norm(0 if np.isnan(v) else v))
            luminance = .2126 * rgba[0] + .7152 * rgba[1] + .0722 * rgba[2]
            ax.text(j, i, label, ha="center", va="center", fontsize=8,
                    color="black" if np.isnan(v) or luminance > .5 else "white")
    ax.figure.colorbar(im, ax=ax, label=unit, fraction=.045)


def physical_figures(a):
    name = "b2_physical_figure_data.json"
    d = a.read(name)
    records = d["records"]
    common = dict(sources=[name], stage=d["stage"], role=d["role"], n_scenes=2, n_groups=1,
                  identity=d["data_fingerprint"])
    fig, axes = plt.subplots(2, 2, figsize=(10, 6))
    arrays = np.array([r["spectrogram_db"] for r in records])
    for i, r in enumerate(records):
        for pol in range(2):
            im = axes[i, pol].imshow(arrays[i, pol], origin="lower", aspect="auto", interpolation="none",
                extent=(*d["frequency_edges_mhz"], -.005, 1.275), vmin=arrays.min(), vmax=arrays.max(), cmap="magma")
            axes[i, pol].set(title=r["label"] + (" co-pol" if pol == 0 else " cross-pol"),
                              xlabel="Frequency (MHz)", ylabel="Snapshot time (s)")
            fig.colorbar(im, ax=axes[i, pol], label="dB(power/Hz)")
    a.emit("A1_physical_spectrograms", fig, **common, units="MHz, s, dB(power/Hz)",
           values={"scenario_id": records[0]["scenario_id"], "display_shape": [16, 128],
                   "color_limits_db": [float(arrays.min()), float(arrays.max())]},
           caption="Paired lowest test group; linear-power pooling 8 snapshots x 4 bins; shared scale. Simulation observations.",)
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))
    f = d["frequency_mhz"]
    for ax, r in zip(axes, records):
        ax.plot(f, r["mean_psd_db"][0], label="co-pol PSD", lw=1)
        ax.plot(f, r["mean_psd_db"][1], label="cross-pol PSD", lw=1)
        ax.plot(f, r["mean_residual_db"], label="obs-cancel/1 residual", lw=1)
        ax.set(xlabel="Frequency (MHz)", ylabel="dB(power/Hz)", title=r["label"], ylim=(-125, -55))
        other = ax.twinx()
        other.plot(f, r["operator_mask_db"][0], color="black", alpha=.4, ls="--", label="co plan")
        other.plot(f, r["operator_mask_db"][1], color="grey", alpha=.5, ls=":", label="cross plan")
        other.set(ylabel="Plan mask (relative dB)", ylim=(-65, 5))
        ax.legend(loc="upper left", fontsize=7); other.legend(loc="lower right", fontsize=7)
    a.emit("A2_psd_plan_residual", fig, **common, units="MHz; PSD dB(power/Hz); mask relative dB",
           values={"scenario_id": records[0]["scenario_id"], "time_pool": "linear power"},
           caption="Same two scenes as A1; masks have a separate relative scale; residual uses observed IQ and co plan only.")
    name = "b2_feat_cancellation_check.json"; d = a.read(name)
    labels = list(d["per_label"]); rows = [d["per_label"][k] for k in labels]
    fig, ax = plt.subplots(figsize=(9, 4.8))
    ax.barh(labels, [r["mean_depth_db"] for r in rows])
    ax.set(xlabel="Mean active-carrier core cancellation depth (dB)")
    a.emit("A3_cancellation_by_class", fig, sources=[name], stage="B2-feat/1", role="offline diagnostic: four roles",
           n_scenes=64, n_groups=8, units="dB", values=d["per_label"], identity=d["data_fingerprint"],
           caption="8 scenes/class; mean over 37 active planned-carrier cores/class, not mean full-band depth. No model fitting.")
    name = "npr_check.json"; d = a.read(name)
    fig, ax = plt.subplots(figsize=(8, 4.8))
    for amp, v in d["amplifiers"].items():
        rows = v["rows"]
        supported = [r for r in rows if not r["input_beyond_measured"]]
        excluded = [r for r in rows if r["input_beyond_measured"]]
        dots = ax.scatter([r["ibo_db"] for r in supported], [r["npr_db"] for r in supported], s=22, label=amp)
        if excluded:
            ax.scatter([r["ibo_db"] for r in excluded], [r["npr_db"] for r in excluded],
                       facecolors="none", edgecolors=dots.get_facecolor()[0], marker="s", s=25)
    ax.set(xlabel="Input back-off (dB)", ylabel="NPR (dB)"); ax.legend(fontsize=8, ncols=2)
    a.emit("A4_npr_amplifiers", fig, sources=[name], stage="standalone NPR diagnostic", role="offline physics",
           n_scenes=None, n_groups=None, units="dB", values=d["amplifiers"], identity="seed=0; 524288 samples; one notched waveform",
           caption="Measured simulation points only. Hollow squares: inputs exceed OpenDPD measured support; no interpolation or CI.",
           evidence="ENGINEERING_VALIDATION")
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.6))
    values = {}
    for ax, name, xkey, title in zip(axes, ("asi_visibility.json", "cuc_visibility.json"),
            ("c_over_i_psd_db", "c_over_i_db"), ("ASI: PSD-level C/I", "CuC: total-plan C/I")):
        d = a.read(name); rows = d["rows"]; values[name] = {"n_rows": len(rows), "n_groups": len(d["seeds"])}
        if "asi" in name:
            for key in ("in_plan", "out_of_plan"):
                points = [r for r in rows if r[key]["n_bins"] > 0]
                ax.scatter([r[xkey] for r in points], [r[key]["delta_db"] for r in points], s=9, alpha=.65, label=key)
        else:
            ax.scatter([r[xkey] for r in rows], [r["delta_db"] for r in rows], s=9, alpha=.65, label="victim band")
        ax.set(title=title, xlabel="C/I (dB; definition in title)", ylabel="Paired oracle-twin PSD difference (dB)")
        ax.legend(fontsize=8)
    a.emit("A5_asi_cuc_observability", fig, sources=list(values), stage="standalone A1-chain diagnostics",
           role="offline truth diagnostic only", n_scenes={"ASI": 120, "CuC": 144},
           n_groups={"ASI": 120, "CuC": 24}, units="dB", values=values,
           identity="ASI seeds 610000..610119; CuC seeds 600000..600023, six levels; separate populations",
           caption="Truth defines diagnostic C/I and event band only; these are not detector scores or model inputs. No pooled population.")


def e4_figures(a):
    d = a.read(E4)
    if d["matrix_coverage"]["totals"]["completed"] != 25 or d["totals"]["scenes_parity_checked"] != 90:
        raise ValueError("unexpected unified E4 inventory")
    known = { (i["perturbation"], i["scope"]): i for i in d["invocations"] if i["stage"] == "known" }
    # none has only the predeclared both scope; absent combinations stay null.
    ns = {i["name"]: i["populations"]["applied"] for i in known.values()}
    base = dict(sources=[E4], stage="B2-A5-eval/1 on B2-feat/1", role="test, known stage only",
        n_scenes=ns, n_groups=2, identity={"known_data_fingerprint": d["source"]["known_data_fingerprint"],
        "stage_identity": d["source"]["stage_identities"]["known"]}, model="three-epoch chance-level stand-ins")
    def grid(getter):
        return [[getter(known[(p, s)]) if (p, s) in known else None for s in SCOPES] for p in PERTURBATIONS]
    for ident, metric, title, unit in (
        ("B1_cancellation_displacement", "cancellation_depth_core_db_displacement", "Original-mask core depth", "dB"),
        ("B2_residual_displacement", "residual_total_db_displacement", "Full-band residual power", "dB")):
        fig, axes = plt.subplots(1, 2, figsize=(10, 5.3)); values = {}
        values = {mode: grid(lambda i: i["views"]["dual_residual"]["conditions"][mode][metric]) for mode in MODES}
        limit = max(abs(v) for matrix in values.values() for row in matrix for v in row if v is not None) or 1
        for ax, mode in zip(axes, MODES):
            heat(ax, values[mode], PERTURBATIONS, SCOPES, mode, unit, diverging=True, limit=limit)
        a.emit(ident, fig, **base, units=unit, values=values,
               caption=title + ": corrupted minus paired original; 2 groups/cell; authorize_intruder n=2, other cells n=4; grey=unregistered.")
    fig, axes = plt.subplots(1, 2, figsize=(10, 5.3)); values = {}
    values = {mode: grid(lambda i: i["baseline_inputs"]["edsc_score_db"][mode]["mean_displacement_db"]) for mode in MODES}
    limit = max(abs(v) for matrix in values.values() for row in matrix for v in row if v is not None) or 1
    for ax, mode in zip(axes, MODES):
        heat(ax, values[mode], PERTURBATIONS, SCOPES, mode, "dB", diverging=True, limit=limit)
    a.emit("B3_edsc_input_score", fig, **base, units="dB", values=values,
           caption="EDSC score recomputed from inputs; no baseline fitting, threshold evaluation or robustness claim; n per cell as B1.")
    items = sorted(known.values(), key=lambda i: i["name"])
    labels = [i["perturbation"] + "/" + i["scope"] for i in items]
    fig, axes = plt.subplots(1, 2, figsize=(11, 7)); values = {}
    for ax, method in zip(axes, ("ca_cfar_planned", "ca_cfar_blind")):
        data = [[i["baseline_inputs"][method][m]["n_scenes_changed"] for m in MODES] for i in items]
        values[method] = data
        heat(ax, data, labels, ["mask", "receiver"], method, "changed scenes (count)", limit=4)
    a.emit("B4_cfar_input_sensitivity", fig, **base, units="scene count", values=values,
           caption="Maximum per-statistic changed-scene count (not union); denominators in manifest; blind CFAR reads PSD only.")
    fig, ax = plt.subplots(figsize=(8, 7))
    values = [[i["baseline_inputs"]["xgboost_features_26"][m]["n_features_changed"] for m in MODES] for i in items]
    heat(ax, values, labels, ["MASK_ONLY", "RECEIVER_CONSISTENT"], "26 expert features: any change across paired scenes", "features (count)")
    a.emit("B5_xgboost_feature_displacement", fig, **base, units="changed feature count / 26", values=values,
           caption="Counts of feature dimensions changed anywhere in the invocation; no feature magnitudes or trained XGBoost A5 scores available.")
    fig, axes = plt.subplots(1, 3, figsize=(14, 5.5)); values = {}
    for ax, method in zip(axes, ("msp", "energy", "mahalanobis")):
        values[method] = grid(lambda i: i["views"]["dual_residual"]["conditions"]["RECEIVER_CONSISTENT"]["score_displacement"][method]["mean"])
        heat(ax, values[method], PERTURBATIONS, SCOPES, method, "raw score delta", diverging=True)
    a.emit("B6_unknown_score_displacement", fig, **base, units="native score units, separate scales", values=values,
           caption="dual_residual stand-in: corrupted minus original unknown score; higher=more unknown-like. No unknown-family metrics in E4.")
    fig, axes = plt.subplots(1, 2, figsize=(11, 7)); values = {}
    for ax, mode in zip(axes, MODES):
        vals = [[i["views"][v]["conditions"][mode]["max_abs_logit_difference_vs_original"] for v in ("co", "dual", "dual_residual")] for i in items]
        values[mode] = vals; heat(ax, vals, labels, ["co", "dual", "dual_residual"], mode, "max absolute logit delta")
    a.emit("B7_mask_receiver_model_input_effect", fig, **base, units="logit units", values=values,
           caption="Output displacement from changed inputs; masks/residual are separate interventions. These stand-ins cannot establish robustness.")
    fig, axes = plt.subplots(2, 1, figsize=(11, 6), sharex=True)
    items = d["invocations"]; names = [i["name"].replace("known_", "K:").replace("matched_", "M:") for i in items]
    counts = [i["parity"]["n_scenes_checked"] for i in items]
    differences = [i["parity"]["max_abs_diff_db"] for i in items]
    axes[0].bar(range(len(items)), counts); axes[0].set(ylabel="Checked scene-slots", title="90/90 exact; repeated scenes across invocations")
    axes[1].scatter(range(len(items)), differences); axes[1].set(ylabel="Max difference (dB)", ylim=(-.01, .13))
    axes[1].axhline(.125, ls="--", color="grey", label="P28 fail-closed tolerance")
    axes[1].set_xticks(range(len(items)), names, rotation=90, fontsize=7); axes[1].legend()
    a.emit("B8_replay_parity", fig, sources=[E4], stage="B2-A5-eval/1", role="known test and matched shown by invocation",
           n_scenes={"checked_scene_slots": 90, "unique_physical_scenes": 8}, n_groups={"known": 2, "matched": 2},
           units="scene-slot count; dB", values={"names": names, "checked": counts, "max_abs_diff_db": differences},
           identity={"known_data_fingerprint": d["source"]["known_data_fingerprint"],
                     "stages": d["source"]["stage_identities"]}, evidence="ENGINEERING_VALIDATION",
           caption="Same-machine parity only; K and M are distinct populations. Raw IQ hashes are not persisted; no cross-machine certificate.")
    items = [i for i in d["invocations"] if i["stage"] == "matched"]
    names = [i["perturbation"] + "/" + i["scope"] for i in items]
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.8)); values = {}
    for ax, metric in zip(axes, ("cancellation_depth_core_db_displacement", "residual_total_db_displacement")):
        vals = [[i["views"]["dual_residual"]["conditions"][m][metric] for m in MODES] for i in items]
        values[metric] = vals
        heat(ax, vals, names, ["mask", "receiver"], metric.replace("_db_displacement", ""), "dB", diverging=True)
    a.emit("B9_matched_receiver_displacement", fig, sources=[E4], stage="B2-A5-eval/1 on B2-match/1",
           role="test-matched only", n_scenes={i["name"]: i["populations"]["applied"] for i in items}, n_groups=2,
           units="dB", values=values, identity=d["source"]["stage_identities"]["matched"],
           model="no model inference used in these physical displacement values",
           caption="Separate matched population: ASI/unauthorized, 2 groups; authorize_intruder applies to unauthorized only; not pooled with known.")


def ml_figures(a):
    name = "b2_xgb_baseline.json"; d = a.read(name)
    labels = d["provenance"]["class_order"]; methods = list(d["binary"])
    values = [[d["binary"][m]["known"]["per_class"][label]["rate"] for label in labels] for m in methods]
    fig, ax = plt.subplots(figsize=(11, 4))
    heat(ax, values, methods, [s.replace("carrier_under_carrier", "CuC").replace("adjacent_satellite", "ASI") for s in labels],
         "Binary alarm rates by original known class", "fraction")
    ax.tick_params(axis="x", rotation=30)
    a.emit("C1_binary_baselines", fig, sources=[name], stage="B2-feat/1, B2-binary-anomaly/1", role="test",
           n_scenes=16, n_groups=2, units="fraction; n=2/class", values=values, identity=d["provenance"]["evaluation_identity"],
           model="16-round bounded XGBoost; deterministic EDSC/CFAR; two clean calibration scenes",
           caption="clean column=alarm on clean; others=event alarm. One common fixture and calibration rule; no population-Pfa claim or ranking.")
    name = "b2_full_pilot.json"; neural = a.read(name)
    fig, axes = plt.subplots(1, 3, figsize=(11, 4)); values = {}
    for ax, metric in zip(axes, ("unknown_auroc", "unknown_ap", "oscr")):
        vals = [[neural["methods"][v]["open_set"][m][metric] for m in ("msp", "energy", "mahalanobis")]
                for v in ("co", "dual", "dual_residual")]
        values[metric] = vals
        heat(ax, vals, ["co", "dual", "dual+res"], ["MSP", "energy", "Maha"], metric, "fraction", limit=1)
    a.emit("C2_neural_open_set", fig, sources=[name], stage="B2-feat/1 + B2-test/1", role="test; near families only",
           n_scenes={"known": 16, "unknown_near": 6}, n_groups=2, units="fraction", values=values,
           identity={"known": neural["data_fingerprint"], "unknown": neural["test_only_fingerprint"]},
           model="chance-level three-epoch neural stand-ins; three post-hoc scorers",
           caption="Unknown positive; AP prevalence=6/22; OSCR known denominator=16. CID excluded, wideband noise separate; no intervals inferred.")
    name = "b2_xgb_baseline.json"
    fig, ax = plt.subplots(figsize=(9, 6))
    cm = d["classifier"]["known"]["confusion"]
    heat(ax, cm["counts"], cm["row_labels"], cm["column_labels"], "XGBoost multiclass: true rows / predicted columns", "scene count")
    ax.tick_params(axis="x", rotation=60)
    a.emit("C3_xgboost_multiclass_confusion", fig, sources=[name], stage="B2-feat/1", role="test",
           n_scenes=16, n_groups=2, units="scene count", values=cm, identity=d["provenance"]["evaluation_identity"]["known"],
           model="bounded trained XGBoost, 16 train scenes; not production",
           caption="All 16 scenes, 2/class; no rejection filter. Stored count matrix, separately audited at E3b; no raw predictions committed here.")
    name = "b2_observed_predictions.json"; preds = a.read(name)
    fig, axes = plt.subplots(1, 2, figsize=(12, 5.8)); values = {}
    for ax, (view, rows) in zip(axes, preds.items()):
        cm = np.zeros((8, 8), dtype=int)
        for row in rows:
            cm[labels.index(row["true_label"]), labels.index(row["prediction"])] += 1
        values[view] = cm.tolist(); heat(ax, cm, labels, labels, view + ": true rows / predicted columns", "scene count")
        ax.tick_params(axis="x", rotation=65)
    a.emit("C4_observed_dev_raw_confusion", fig, sources=[name, "b2_observed_pilot.json"], stage="B2-observed-dev/1 (P21b)",
           role="test", n_scenes=8, n_groups=1, units="scene count", values=values,
           identity="separate P21b raw prediction record; not P20/E4", model="three-epoch development stand-ins",
           caption="Recomputed from raw predictions; 1 scene/class, one group. P21b receiver/loss differs from canonical P20; no cross-fixture comparison.")
    for name, ident in (("b2_streaming_memory_pilot.json", "C5_streaming_real"),
                         ("b2_streaming_memory_synthetic_48.json", "C6_streaming_layout")):
        d = a.read(name); rows = d["runs"]; fig, axes = plt.subplots(1, 2, figsize=(10, 4.5))
        names = [r["mode"] + ("/" + str(r["window_shards"]) if r["window_shards"] else "") for r in rows]
        axes[0].bar(names, [r["peak_rss_mib"] for r in rows]); axes[0].set(ylabel="Peak process RSS (MiB)")
        axes[1].bar(names, [r["total_s"] for r in rows]); axes[1].set(ylabel="Verify + load + fit + infer (s)")
        a.emit(ident, fig, sources=[name], stage=d["dataset"]["protocol"], role="verify/load four roles; fit and infer train only",
               n_scenes={role: info["n_samples"] for role,info in d["dataset"]["roles"].items()},
               n_groups={role: info["n_samples"] // 8 for role,info in d["dataset"]["roles"].items()},
               units="MiB; seconds", values=[{k:r[k] for k in ("mode", "window_shards", "peak_rss_mib", "total_s")} for r in rows],
               identity=rows[0]["data_fingerprint"], evidence="ENGINEERING_VALIDATION", model="bounded timing experiment",
               caption="Single measurements, import baseline included; " + d["fixture"]["kind"] + ". Hardware/package context in source; no extrapolated GPU speed.")
    name = "b2_xgb_baseline.json"; d = a.read(name)
    unknown = d["classifier"]["unknown"]
    names = list(unknown["families"]) + ["pooled_near"]
    ranks = [(unknown["pooled_near"] if f == "pooled_near" else unknown["families"][f])["ranking"] for f in names]
    # Benign CID has no unknown ranking. It is never silently treated as unknown.
    keep = [(f, r) for f, r in zip(names, ranks) if r is not None]
    fig, axes = plt.subplots(1, 3, figsize=(12, 4.8)); values = {}
    for ax, metric in zip(axes, ("unknown_auroc", "unknown_aupr", "oscr_auc")):
        vals = [r[metric] for _, r in keep]; values[metric] = vals
        ax.scatter(vals, range(len(keep))); ax.set(yticks=range(len(keep)), yticklabels=[f for f,_ in keep], xlim=(0,1), title=metric)
    a.emit("C7_xgboost_open_set", fig, sources=[name], stage="B2-feat/1 + B2-test/1", role="test only",
           n_scenes={f:{"known":r["n_known"],"unknown":r["n_unknown"]} for f,r in keep}, n_groups=2,
           units="fraction", values=values, identity=d["provenance"]["evaluation_identity"],
           model="bounded trained XGBoost; classifier MSP 1-max(P)",
           caption="Unknown positive; AP prevalence=2/18 per family,6/22 near pool. CID excluded; wideband noise separate. Same groups, overlapping rows.")
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.5)); values = {}
    for ax, metric in zip(axes, ("unknown_auroc", "unknown_aupr")):
        vals = [d["binary"][m]["unknown"]["pooled_near"]["ranking"][metric] for m in methods]
        values[metric] = vals
        ax.scatter(range(len(methods)), vals); ax.set(xticks=range(len(methods)), xticklabels=methods, ylim=(0,1), title=metric)
    a.emit("C8_binary_unknown_rankings", fig, sources=[name], stage="B2-binary-anomaly/1", role="test, near pool",
           n_scenes={"known":16,"unknown":6}, n_groups=2, units="fraction", values=values,
           identity=d["provenance"]["evaluation_identity"], model="binary anomaly scores; not multiclass rejection",
           caption="Unknown positive against all known (including interference). AP prevalence=6/22; binary scores do not provide OSCR or class predictions.")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "docs/figures/b2")
    parser.add_argument("--manifest", type=Path, default=RESULTS / "b2_figure_manifest.json")
    parser.add_argument("--families", nargs="+", choices=("A", "B", "C"), default=["A", "B", "C"])
    parser.add_argument("--extract-physical", type=Path)
    parser.add_argument("--only", nargs="+", help="render named representative figures only")
    args = parser.parse_args(argv)
    if args.extract_physical:
        extract_physical(args.extract_physical.resolve(), RESULTS / "b2_physical_figure_data.json")
        return
    atlas = Atlas(args.out, args.manifest, args.only)
    for family, renderer in (("A", physical_figures), ("B", e4_figures), ("C", ml_figures)):
        if family in args.families:
            renderer(atlas)
    atlas.finish()
    print(f"Rendered {len(atlas.figures)} figures, three formats each; {args.manifest}")


if __name__ == "__main__":
    main()
